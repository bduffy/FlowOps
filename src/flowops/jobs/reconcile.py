"""Reconciliation sweep — repairs jobs whose worker died mid-work.

An expired lease on an APPLYING/DESTROYING row means the worker is dead, not slow
(the lease TTL outlives the slowest apply). What happens next depends entirely on
the recorded evidence:

  applying   + handle          -> outcome already happened; re-derive via
                                  actuator.status (tracked state, never a live
                                  cloud poll) and complete.
  applying   + no handle       -> cannot know what exists. FAIL CLOSED AND LOUD:
                                  -> failed, orphan_suspected, audited. Never
                                  blindly re-apply. (failed -> destroying stays
                                  legal for cleanup.)
  destroying + ok result       -> destroyed.
  destroying + no/bad result   -> failed + orphan flag. Never assume destroyed.

No scheduler here — #8's worker loop / #13 invoke it periodically. CLI for ops:
python -m flowops.jobs.reconcile
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from ..actuators.base import Actuator
from ..audit.log import AuditLog
from ..models.enums import JobState
from ..store import Store
from .executor import audit_event, default_worker_id


@dataclass(frozen=True)
class ReconcileOutcome:
    task_id: str
    from_state: JobState
    to_state: JobState
    orphan: bool
    detail: str


def sweep(
    store: Store,
    actuator: Actuator,
    audit: AuditLog,
    worker_id: str | None = None,
    lease_ttl: timedelta = timedelta(seconds=900),
) -> list[ReconcileOutcome]:
    worker_id = worker_id or f"reconcile:{default_worker_id()}"
    outcomes: list[ReconcileOutcome] = []
    for request_id, task in store.expired_leases():
        # One poisoned row (corrupt JSONB, racing completer, actuator error) must
        # not starve reconciliation for every other stuck job — isolate per task.
        try:
            claimed = store.reclaim_expired(task.id, task.state, worker_id, lease_ttl)
            if claimed is None:
                continue  # someone else won the race
            task = claimed
            if task.state is JobState.APPLYING:
                outcomes.append(
                    _repair_apply(store, actuator, audit, request_id, task, worker_id)
                )
            elif task.state is JobState.DESTROYING:
                outcomes.append(_repair_destroy(store, audit, request_id, task, worker_id))
        except Exception as exc:  # noqa: BLE001 — fail loud per row, keep sweeping
            detail = f"reconcile error on task {task.id}: {exc}"
            audit_event(audit, request_id, "reconcile.error", "system", detail)
            outcomes.append(
                ReconcileOutcome(task.id, task.state, task.state, orphan=True, detail=detail)
            )
    return outcomes


def _repair_apply(store, actuator, audit, request_id, task, worker_id) -> ReconcileOutcome:
    if task.handle is not None:
        # Apply finished but the completion write never landed. Only a terminal
        # tracked status is trusted; anything else (an async actuator still mid-
        # flight) is fail-loud: FAILED + orphan flag, evidence retained.
        status = actuator.status(task.handle)
        if status in (JobState.SUCCEEDED, JobState.FAILED):
            store.complete(task.id, JobState.APPLYING, status, worker_id)
            detail = f"completed from recorded handle (run {task.run_id}): {status.value}"
            audit_event(audit, request_id, "job.reconciled", "system", detail)
            return ReconcileOutcome(
                task.id, JobState.APPLYING, status, orphan=False, detail=detail
            )
        store.mark_orphan(task.id)
        store.complete(task.id, JobState.APPLYING, JobState.FAILED, worker_id)
        detail = (
            f"handle status {status.value} is not terminal (run {task.run_id}) — "
            "resources may exist; reconcile/destroy required"
        )
        audit_event(audit, request_id, "orphan_suspected", "system", detail)
        return ReconcileOutcome(
            task.id, JobState.APPLYING, JobState.FAILED, orphan=True, detail=detail
        )
    # No handle: resources may exist with no way to locate them from here.
    store.mark_orphan(task.id)
    store.complete(task.id, JobState.APPLYING, JobState.FAILED, worker_id)
    detail = (
        f"apply died before recording a handle (run {task.run_id}) — "
        "resources may exist; orphan sweep / account teardown required"
    )
    audit_event(audit, request_id, "orphan_suspected", "system", detail)
    return ReconcileOutcome(task.id, JobState.APPLYING, JobState.FAILED, orphan=True, detail=detail)


def _repair_destroy(store, audit, request_id, task, worker_id) -> ReconcileOutcome:
    result = store.load_destroy_result(task.id)
    if result is not None and result.ok:
        store.complete(task.id, JobState.DESTROYING, JobState.DESTROYED, worker_id)
        detail = "completed from recorded destroy result"
        audit_event(audit, request_id, "job.reconciled", "system", detail)
        return ReconcileOutcome(
            task.id, JobState.DESTROYING, JobState.DESTROYED, orphan=False, detail=detail
        )
    store.mark_orphan(task.id)
    store.complete(task.id, JobState.DESTROYING, JobState.FAILED, worker_id)
    detail = "destroy died without a recorded ok — resources may remain"
    audit_event(audit, request_id, "orphan_suspected", "system", detail)
    return ReconcileOutcome(
        task.id, JobState.DESTROYING, JobState.FAILED, orphan=True, detail=detail
    )


def main() -> None:
    from ..config import get_actuator, load_settings
    from ..db import create_pool

    settings = load_settings()
    pool = create_pool(settings.database_url)
    try:
        # NOTE: the CLI's audit events are in-memory until #14 lands — the printed
        # outcomes (and the orphan_suspected column) are the durable trace.
        outcomes = sweep(
            Store(pool),
            get_actuator(settings),
            AuditLog(),
            lease_ttl=timedelta(seconds=settings.lease_ttl_seconds),
        )
        if not outcomes:
            print("reconcile: nothing stuck")
        for o in outcomes:
            flag = " ORPHAN-SUSPECTED" if o.orphan else ""
            print(
                f"reconcile: {o.task_id} {o.from_state.value} -> "
                f"{o.to_state.value}{flag}: {o.detail}"
            )
    finally:
        pool.close()


if __name__ == "__main__":
    main()
