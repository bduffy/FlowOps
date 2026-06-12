"""Failure-path suite for the durable jobs table (#5). Written first — these tests
shape the job model (arch §5.2): crash redelivery, callback-failed reconciliation,
per-sandbox locks, lease expiry, idempotency, fail-closed destroy.

"Crash" is simulated by claiming with a NEGATIVE lease TTL (already expired) and
never calling complete() — durable evidence with a dead worker, exactly what a
real crash leaves behind.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from flowops.actuators.base import Result
from flowops.api.app import create_app
from flowops.jobs import executor, reconcile
from flowops.jobs.state_machine import InvalidTransition
from flowops.models.domain import ActuatorHandle, GateRecord, Task, WorkRequest
from flowops.models.enums import GateResult, GateType, JobState
from flowops.store import ConflictError

LIVE = timedelta(seconds=900)
EXPIRED = timedelta(seconds=-1)  # lease born dead: simulates a crashed worker


def _submit(service, key=None):
    req, created = service.submit(
        "dev-sandbox", "x", requester="jdoe", owner="jdoe", idempotency_key=key
    )
    return req, created


def _crash_after_handle(service, store, actuator):
    """Drive a job to: handle recorded, state stuck APPLYING, lease expired.
    This IS apply-succeeded-but-callback-failed."""
    req, _ = _submit(service)
    task_id = req.task.id
    store.claim(task_id, JobState.AWAITING_GATE, JobState.APPLYING, "worker-dead", EXPIRED)
    store.record_run(task_id, "run-crash", "worker-dead")
    intent, _preview, _v = store.load_plan(task_id)
    handle = actuator.apply(replace(intent, run_id="run-crash"))
    store.record_handle(task_id, handle, "worker-dead")
    # worker dies here: complete() never runs
    return req, task_id


# -- crash redelivery & reconciliation -------------------------------------------


def test_crash_redelivery_no_double_apply(service, store, actuator):
    req, task_id = _crash_after_handle(service, store, actuator)
    assert actuator.apply_calls == 1

    # Redelivery: a second worker picks the job up and must finish, not re-apply.
    state = executor.run_apply(store, actuator, service.audit, req, "worker-2", LIVE)

    assert state is JobState.SUCCEEDED
    assert actuator.apply_calls == 1  # THE invariant: no double-apply
    assert service.state(req.id) is JobState.SUCCEEDED


def test_apply_succeeded_but_callback_failed_reconciles(service, store, actuator):
    req, task_id = _crash_after_handle(service, store, actuator)

    outcomes = reconcile.sweep(store, actuator, service.audit)

    assert [(o.to_state, o.orphan) for o in outcomes] == [(JobState.SUCCEEDED, False)]
    assert service.state(req.id) is JobState.SUCCEEDED
    assert "job.reconciled" in [e.type for e in service.audit.for_request(req.id)]
    assert actuator.apply_calls == 1


def test_mid_apply_crash_without_handle_fails_closed(service, store, actuator):
    req, _ = _submit(service)
    task_id = req.task.id
    store.claim(task_id, JobState.AWAITING_GATE, JobState.APPLYING, "worker-dead", EXPIRED)
    # crashed before recording a handle
    store.record_run(task_id, "run-vanished", "worker-dead")

    outcomes = reconcile.sweep(store, actuator, service.audit)

    assert [(o.to_state, o.orphan) for o in outcomes] == [(JobState.FAILED, True)]
    req = store.get_request(req.id)
    assert req.task.state is JobState.FAILED
    assert req.task.orphan_suspected is True  # loud, not silent
    assert "orphan_suspected" in [e.type for e in service.audit.for_request(req.id)]
    # Recovery stays open: failed -> destroying is legal for cleanup.
    store.claim(task_id, JobState.FAILED, JobState.DESTROYING, "cleaner", LIVE)


def test_stuck_destroy_fails_loud(service, store, actuator):
    req, _ = _submit(service)
    service.decide(req.id, "approve", role="admin", actor="admin")
    task_id = req.task.id
    # Destroy claimed by a worker that died without recording a result.
    store.claim(task_id, JobState.SUCCEEDED, JobState.DESTROYING, "worker-dead", EXPIRED)

    outcomes = reconcile.sweep(store, actuator, service.audit)

    assert [(o.to_state, o.orphan) for o in outcomes] == [(JobState.FAILED, True)]
    assert store.get_request(req.id).task.orphan_suspected is True
    assert "orphan_suspected" in [e.type for e in service.audit.for_request(req.id)]


# -- leases ARE the per-sandbox lock ----------------------------------------------


def test_claim_is_exclusive_per_sandbox_lock(service, store):
    req, _ = _submit(service)
    task_id = req.task.id
    store.claim(task_id, JobState.AWAITING_GATE, JobState.APPLYING, "worker-a", LIVE)

    with pytest.raises(ConflictError):
        store.claim(task_id, JobState.AWAITING_GATE, JobState.APPLYING, "worker-b", LIVE)
    # Teardown can't sneak in while an apply is in flight either.
    with pytest.raises(ConflictError):
        service.teardown(req.id, actor="jdoe", actor_role="worker")


def test_lease_expiry_allows_reclaim(service, store):
    req, _ = _submit(service)
    task_id = req.task.id
    store.claim(task_id, JobState.AWAITING_GATE, JobState.APPLYING, "worker-dead", EXPIRED)

    reclaimed = store.reclaim_expired(task_id, JobState.APPLYING, "worker-2", LIVE)

    assert reclaimed is not None and reclaimed.lease_owner == "worker-2"
    # The new owner can complete; the dead worker no longer can (owner guard).
    with pytest.raises(ConflictError):
        store.complete(task_id, JobState.APPLYING, JobState.FAILED, "worker-dead")
    store.complete(task_id, JobState.APPLYING, JobState.FAILED, "worker-2")


def test_stale_transition_conflicts(service, store):
    req, _ = _submit(service)  # state is AWAITING_GATE now
    task_id = req.task.id
    with pytest.raises(ConflictError):
        store.transition(task_id, JobState.QUEUED, JobState.PLANNING)  # stale expected
    with pytest.raises(InvalidTransition):
        store.transition(task_id, JobState.AWAITING_GATE, JobState.SUCCEEDED)  # illegal


# -- idempotency -------------------------------------------------------------------


def test_idempotent_submit_replays(service, actuator):
    req1, created1 = _submit(service, key="k-1")
    req2, created2 = _submit(service, key="k-1")

    assert (created1, created2) == (True, False)
    assert req1.id == req2.id
    assert actuator.plan_calls == 1  # plan/gates ran once, not twice
    assert "idempotent_replay" in [e.type for e in service.audit.for_request(req1.id)]


def test_absent_idempotency_keys_dont_collide(service):
    req1, _ = _submit(service, key=None)
    req2, _ = _submit(service, key=None)
    assert req1.id != req2.id


def test_api_idempotency_key_replay_returns_200(service):
    app = create_app(service=service)
    body = {"title": "demo", "requester": "jdoe", "owner": "jdoe"}
    with TestClient(app) as client:
        r1 = client.post("/api/requests", json=body, headers={"Idempotency-Key": "api-k1"})
        r2 = client.post("/api/requests", json=body, headers={"Idempotency-Key": "api-k1"})
    assert (r1.status_code, r2.status_code) == (201, 200)
    assert r1.json()["id"] == r2.json()["id"]


# -- status() reads the jobs table ---------------------------------------------------


def test_status_reads_jobs_table_not_the_actuator(service, actuator):
    req, _ = _submit(service)
    service.decide(req.id, "approve", role="admin", actor="admin")
    assert service.state(req.id) is JobState.SUCCEEDED
    assert service.state(req.id) is JobState.SUCCEEDED
    assert actuator.status_calls == 0  # never a live poll


# -- durability across restarts -------------------------------------------------------


def test_survives_restart(dev_settings, store, actuator, service):
    req, _ = _submit(service)

    # "Restart": a brand-new service over the same database; no in-process context.
    from flowops.services import SandboxService

    fresh = SandboxService(dev_settings, store=store, actuator=actuator)
    fresh.decide(req.id, "approve", role="admin", actor="admin")
    assert fresh.state(req.id) is JobState.SUCCEEDED


# -- fail-closed destroy ---------------------------------------------------------------


def test_unparseable_handle_blocks_destroy(service, store, actuator, db_pool):
    req, _ = _submit(service)
    service.decide(req.id, "approve", role="admin", actor="admin")
    # Corrupt the recorded handle directly (evidence writes are owner-guarded now,
    # so corruption has to come from outside the protocol — e.g. a bad migration).
    with db_pool.connection() as conn:
        conn.execute(
            """UPDATE tasks SET handle = '{"state_backend_ref": "", "workspace": "",
               "outputs": {}, "status": "succeeded"}'::jsonb WHERE id = %s""",
            (req.task.id,),
        )

    with pytest.raises(ValueError):
        service.teardown(req.id, actor="jdoe", actor_role="worker")

    assert actuator.destroy_calls == 0  # no destroy without a parseable handle
    assert "destroy_blocked" in [e.type for e in service.audit.for_request(req.id)]


def test_reconcile_completes_destroy_from_recorded_ok_result(service, store, actuator):
    # destroy-succeeded-but-callback-failed: result recorded, worker died before complete().
    req, _ = _submit(service)
    service.decide(req.id, "approve", role="admin", actor="admin")
    task_id = req.task.id
    store.claim(task_id, JobState.SUCCEEDED, JobState.DESTROYING, "worker-dead", EXPIRED)
    store.record_destroy_result(
        task_id, Result(ok=True, detail="[dummy] destroyed"), "worker-dead"
    )

    outcomes = reconcile.sweep(store, actuator, service.audit)

    assert [(o.to_state, o.orphan) for o in outcomes] == [(JobState.DESTROYED, False)]
    assert service.state(req.id) is JobState.DESTROYED
    assert store.get_request(req.id).task.orphan_suspected is False
    assert "job.reconciled" in [e.type for e in service.audit.for_request(req.id)]
    assert actuator.destroy_calls == 0  # completed from evidence, never re-destroyed


def test_reconcile_apply_with_failed_handle_lands_in_failed_not_orphan(service, store, actuator):
    # Crash after recording a FAILED handle: outcome is known — failed, not orphan.
    req, _ = _submit(service)
    task_id = req.task.id
    store.claim(task_id, JobState.AWAITING_GATE, JobState.APPLYING, "worker-dead", EXPIRED)
    store.record_run(task_id, "run-failed", "worker-dead")
    store.record_handle(
        task_id,
        ActuatorHandle(state_backend_ref="memory://run-failed", workspace="run-failed",
                       status=JobState.FAILED),
        "worker-dead",
    )

    outcomes = reconcile.sweep(store, actuator, service.audit)

    assert [(o.to_state, o.orphan) for o in outcomes] == [(JobState.FAILED, False)]
    assert service.state(req.id) is JobState.FAILED
    assert actuator.status_calls == 1  # re-derived from tracked state via status()
    assert actuator.apply_calls == 0  # never re-applied


def test_redelivery_without_handle_fails_closed(service, store, actuator):
    # Redelivery (not the sweep) finds an expired lease and NO handle: must never
    # blindly re-apply — fail loud with the orphan flag.
    req, _ = _submit(service)
    task_id = req.task.id
    store.claim(task_id, JobState.AWAITING_GATE, JobState.APPLYING, "worker-dead", EXPIRED)
    store.record_run(task_id, "run-vanished", "worker-dead")

    state = executor.run_apply(store, actuator, service.audit, req, "worker-2", LIVE)

    assert state is JobState.FAILED
    assert actuator.apply_calls == 0  # THE invariant: no blind re-apply
    task = store.get_request(req.id).task
    assert task.state is JobState.FAILED and task.orphan_suspected is True
    assert "orphan_suspected" in [e.type for e in service.audit.for_request(req.id)]


def test_failed_destroy_marks_orphan(dev_settings, store):
    from flowops.actuators.dummy import DummyActuator
    from flowops.services import SandboxService

    class FailingDestroyActuator(DummyActuator):
        def destroy(self, handle):
            return Result(ok=False, detail="[dummy] destroy blew up")

    svc = SandboxService(dev_settings, store=store, actuator=FailingDestroyActuator())
    req, _ = svc.submit("dev-sandbox", "x", requester="jdoe", owner="jdoe")
    svc.decide(req.id, "approve", role="admin", actor="admin")

    svc.teardown(req.id, actor="jdoe", actor_role="worker")

    task = store.get_request(req.id).task
    assert task.state is JobState.FAILED
    assert task.orphan_suspected is True  # resources may remain — loud, not silent
    assert "destroy_failed" in [e.type for e in svc.audit.for_request(req.id)]


def test_missing_plan_fails_closed(store):
    # Global invariant: a task without a persisted plan cannot be applied/destroyed.
    task = Task()
    req = WorkRequest(blueprint_key="dev-sandbox", title="x", requester="jdoe",
                      owner="jdoe", task=task)
    store.create_request(req, task, None)

    with pytest.raises(ValueError):
        store.load_plan(task.id)


# -- API error mapping ------------------------------------------------------------


def test_api_second_decision_conflicts_409(service):
    app = create_app(service=service)
    body = {"title": "demo", "requester": "jdoe", "owner": "jdoe"}
    decision = {"decision": "approve", "role": "admin", "actor": "admin"}
    with TestClient(app) as client:
        rid = client.post("/api/requests", json=body).json()["id"]
        r1 = client.post(f"/api/requests/{rid}/decision", json=decision)
        r2 = client.post(f"/api/requests/{rid}/decision", json=decision)
    assert (r1.status_code, r2.status_code) == (200, 409)


def test_api_unknowns_return_404(service):
    app = create_app(service=service)
    with TestClient(app) as client:
        r_bp = client.post(
            "/api/requests",
            json={"blueprint_key": "no-such-bp", "title": "x",
                  "requester": "jdoe", "owner": "jdoe"},
        )
        r_get = client.get("/api/requests/wr_missing")
        r_dec = client.post(
            "/api/requests/wr_missing/decision",
            json={"decision": "approve", "role": "admin", "actor": "admin"},
        )
        r_td = client.post(
            "/api/requests/wr_missing/teardown",
            json={"actor": "jdoe", "actor_role": "admin"},
        )
    assert [r.status_code for r in (r_bp, r_get, r_dec, r_td)] == [404, 404, 404, 404]


# -- gate evidence is write-once -----------------------------------------------------


def test_gate_decision_is_write_once(service, store):
    # The losing side of a concurrent decision must not overwrite the durable
    # governance record — evidence can never contradict what happened.
    req, _ = _submit(service)
    service.decide(req.id, "approve", role="admin", actor="ssmith")

    late_deny = GateRecord(type=GateType.APPROVAL, result=GateResult.FAIL, decided_by="mallory")
    with pytest.raises(ConflictError):
        store.upsert_gate(req.task.id, late_deny)

    gates = {g.type: g for g in store.get_request(req.id).task.gates}
    assert gates[GateType.APPROVAL].result is GateResult.PASS
    assert gates[GateType.APPROVAL].decided_by == "ssmith"


# -- idempotency hardening ------------------------------------------------------------


def test_idempotency_payload_mismatch_conflicts(service):
    service.submit("dev-sandbox", "original", requester="jdoe", owner="jdoe",
                   idempotency_key="k-strict")
    with pytest.raises(ConflictError):
        service.submit("dev-sandbox", "DIFFERENT BODY", requester="jdoe", owner="jdoe",
                       idempotency_key="k-strict")


def test_api_idempotency_payload_mismatch_returns_409(service):
    app = create_app(service=service)
    with TestClient(app) as client:
        r1 = client.post("/api/requests",
                         json={"title": "a", "requester": "jdoe", "owner": "jdoe"},
                         headers={"Idempotency-Key": "api-strict"})
        r2 = client.post("/api/requests",
                         json={"title": "b", "requester": "jdoe", "owner": "jdoe"},
                         headers={"Idempotency-Key": "api-strict"})
    assert (r1.status_code, r2.status_code) == (201, 409)


def test_idempotency_keys_scoped_per_requester(service):
    req1, created1 = service.submit("dev-sandbox", "x", requester="alice", owner="alice",
                                    idempotency_key="shared-key")
    req2, created2 = service.submit("dev-sandbox", "x", requester="bob", owner="bob",
                                    idempotency_key="shared-key")
    assert (created1, created2) == (True, True)
    assert req1.id != req2.id  # no cross-requester replay


# -- lease protocol hardening ----------------------------------------------------------


def test_live_lease_redelivery_never_applies(service, store, actuator):
    # Duplicate delivery while a worker is mid-apply: the second worker must
    # raise and make ZERO actuator calls — the live lease IS the lock.
    req, _ = _submit(service)
    task_id = req.task.id
    store.claim(task_id, JobState.AWAITING_GATE, JobState.APPLYING, "worker-a", LIVE)

    with pytest.raises(ConflictError):
        executor.run_apply(store, actuator, service.audit, req, "worker-b", LIVE)

    assert actuator.apply_calls == 0
    task = store.get_request(req.id).task
    assert task.state is JobState.APPLYING and task.lease_owner == "worker-a"


def test_record_run_is_write_once(service, store):
    req, _ = _submit(service)
    task_id = req.task.id
    store.claim(task_id, JobState.AWAITING_GATE, JobState.APPLYING, "worker-a", LIVE)
    store.record_run(task_id, "run-1", "worker-a")

    with pytest.raises(ConflictError):
        store.record_run(task_id, "run-2", "worker-a")
    assert store.get_request(req.id).task.run_id == "run-1"


def test_evidence_writes_are_owner_guarded(service, store, actuator):
    # A fenced-out worker (lease taken over) must not overwrite evidence.
    req, _ = _submit(service)
    task_id = req.task.id
    store.claim(task_id, JobState.AWAITING_GATE, JobState.APPLYING, "worker-a", LIVE)
    handle = ActuatorHandle(state_backend_ref="memory://x", workspace="x",
                            status=JobState.SUCCEEDED)
    with pytest.raises(ConflictError):
        store.record_handle(task_id, handle, "zombie-worker")
    with pytest.raises(ConflictError):
        store.record_destroy_result(task_id, Result(ok=True), "zombie-worker")


def test_transition_refuses_leased_row(service, store):
    req, _ = _submit(service)
    task_id = req.task.id
    store.claim(task_id, JobState.AWAITING_GATE, JobState.APPLYING, "worker-a", LIVE)
    with pytest.raises(ConflictError):
        store.transition(task_id, JobState.APPLYING, JobState.FAILED)  # legal but leased


# -- API authz mapping ------------------------------------------------------------------


def test_api_teardown_authz_returns_403(service):
    app = create_app(service=service)
    with TestClient(app) as client:
        rid = client.post("/api/requests",
                          json={"title": "x", "requester": "jdoe", "owner": "jdoe"}).json()["id"]
        client.post(f"/api/requests/{rid}/decision",
                    json={"decision": "approve", "role": "admin", "actor": "admin"})
        r = client.post(f"/api/requests/{rid}/teardown",
                        json={"actor": "mallory", "actor_role": "worker"})
        state_after = client.get(f"/api/requests/{rid}").json()["state"]
    assert r.status_code == 403
    assert state_after == "succeeded"  # nothing destroyed


# -- migration runner & schema-evolution safety ------------------------------------------


def test_migrations_are_idempotent(db_pool):
    import os

    from flowops.db.migrate import run_migrations

    url = os.environ.get(
        "FLOWOPS_TEST_DATABASE_URL",
        "postgresql://flowops:flowops@localhost:5432/flowops_test",
    )
    assert run_migrations(url) == []  # session fixture already applied everything


def test_load_plan_tolerates_unknown_intent_fields(service, store, db_pool):
    # Schema evolution must never brick the destroy path: unknown JSONB keys
    # (from an older/newer code version) are ignored, not a TypeError.
    req, _ = _submit(service)
    with db_pool.connection() as conn:
        conn.execute(
            "UPDATE tasks SET intent = intent || '{\"legacy_field\": 1}'::jsonb "
            "WHERE id = %s",
            (req.task.id,),
        )
    intent, _preview, _v = store.load_plan(req.task.id)
    assert intent.blueprint_key == "dev-sandbox"


def test_destroy_uses_pinned_blueprint_not_live_row(service, store, db_pool):
    req, _ = _submit(service)
    service.decide(req.id, "approve", role="admin", actor="admin")
    original_intent, _, version = store.load_plan(req.task.id)

    # Mutate the live blueprint after apply — the snapshot must not move.
    with db_pool.connection() as conn:
        conn.execute(
            "UPDATE blueprints SET tofu_module_ref = 'git::tampered', version = 99 "
            "WHERE key = 'dev-sandbox'"
        )

    intent, _, pinned_version = store.load_plan(req.task.id)
    assert intent.tofu_module_ref == original_intent.tofu_module_ref != "git::tampered"
    assert pinned_version == version == 1

    service.teardown(req.id, actor="jdoe", actor_role="worker")
    assert service.state(req.id) is JobState.DESTROYED
