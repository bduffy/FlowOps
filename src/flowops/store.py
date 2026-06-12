"""Durable Postgres store — the jobs table IS the state machine (#5).

The tasks table is the job row (the task is the provisioning job, arch §4.6).
Because task <-> sandbox is 1:1, the row lease is simultaneously the job lease
AND the per-sandbox lock: a destroy cannot claim while an apply lease is live.

Every transition is validated in Python first (state_machine.transition raises on
illegal moves), then written with a guarded UPDATE — zero rows affected means a
concurrent writer got there first, and that surfaces as ConflictError, never as a
silent overwrite. Evidence writes (handle, destroy_result) happen in their own
transactions, separate from completion: a crash between them is exactly the
"apply-succeeded-but-callback-failed" case reconciliation repairs.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, fields
from datetime import timedelta
from typing import Any, TypeVar

from psycopg.rows import dict_row
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

from .actuators.base import Intent, Preview, Result
from .jobs.state_machine import transition as _validate
from .models.domain import ActuatorHandle, Blueprint, GateRecord, Task, WorkRequest
from .models.enums import (
    BlueprintAvailability,
    Cloud,
    FulfillerType,
    GateResult,
    GateType,
    JobState,
    Priority,
)


class ConflictError(Exception):
    """A guarded write matched zero rows: the state moved or another worker holds
    the lease. The caller lost the race — fail closed, never overwrite."""


class _Replay(Exception):
    """Internal: idempotency key already exists; roll back the duplicate insert."""


_T = TypeVar("_T")


def _fingerprint(req: WorkRequest) -> str:
    """Payload fingerprint bound to an idempotency key: same key + different body
    is a conflict, never a silent replay of the wrong resource."""
    payload = json.dumps([req.blueprint_key, req.title, req.requester, req.owner])
    return hashlib.sha256(payload.encode()).hexdigest()


def _decode(cls: type[_T], data: dict[str, Any]) -> _T:
    """Hydrate a dataclass from JSONB, ignoring unknown keys so removing/renaming a
    field can never brick load_plan (and with it every existing sandbox's destroy)."""
    known = {f.name for f in fields(cls)}  # type: ignore[arg-type]
    return cls(**{k: v for k, v in data.items() if k in known})


class Store:
    """All control-plane persistence. One concrete class — the Actuator stays the
    only abstraction in v1."""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    # -- blueprints ------------------------------------------------------------
    def seed_dev_blueprint(self) -> None:
        # The v1 wedge: a dev sandbox. Admin-curated; module ref is pinned (SR1).
        bp = Blueprint(
            key="dev-sandbox",
            name="Dev sandbox",
            cloud=Cloud.AWS,
            tofu_module_ref="git::https://github.com/bduffy/flowops-blueprints//dev-sandbox?ref=v0.0.0",
            budget_cap_usd=50.0,
            ttl_hours=24,
            allowed_roles=("admin", "worker"),
            availability=BlueprintAvailability.AVAILABLE,
        )
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO blueprints
                    (key, version, name, cloud, tofu_module_ref, budget_cap_usd,
                     ttl_hours, allowed_roles, availability)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (key) DO NOTHING
                """,
                (
                    bp.key,
                    bp.version,
                    bp.name,
                    bp.cloud.value,
                    bp.tofu_module_ref,
                    bp.budget_cap_usd,
                    bp.ttl_hours,
                    list(bp.allowed_roles),
                    bp.availability.value,
                ),
            )

    def get_blueprint(self, key: str) -> Blueprint | None:
        row = self._one("SELECT * FROM blueprints WHERE key = %s", (key,))
        return self._blueprint(row) if row else None

    def list_blueprints(self) -> list[Blueprint]:
        with self._pool.connection() as conn:
            cur = conn.cursor(row_factory=dict_row)
            cur.execute("SELECT * FROM blueprints ORDER BY key")
            return [self._blueprint(r) for r in cur.fetchall()]

    # -- intake (idempotent create) ---------------------------------------------
    def create_request(
        self, req: WorkRequest, task: Task, idempotency_key: str | None
    ) -> tuple[WorkRequest, bool]:
        """Insert request + task atomically. A duplicate (requester, key) rolls the
        whole insert back and replays the existing request (created=False) — but only
        if the payload fingerprint matches; a reused key with a different body is a
        ConflictError, never a silent wrong-resource replay."""
        fingerprint = _fingerprint(req)
        try:
            with self._pool.connection() as conn, conn.transaction():
                conn.execute(
                    """
                    INSERT INTO work_requests (id, blueprint_key, title, priority,
                                               requester, owner)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (req.id, req.blueprint_key, req.title, req.priority.value,
                     req.requester, req.owner),
                )
                cur = conn.execute(
                    """
                    INSERT INTO tasks (id, request_id, fulfiller_type, state,
                                       requester, idempotency_key,
                                       idempotency_fingerprint)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (requester, idempotency_key)
                        WHERE idempotency_key IS NOT NULL
                    DO NOTHING
                    """,
                    (task.id, req.id, task.fulfiller_type.value, task.state.value,
                     req.requester, idempotency_key,
                     fingerprint if idempotency_key is not None else None),
                )
                if cur.rowcount == 0:
                    raise _Replay  # rolls back the work_requests insert too
        except _Replay:
            existing = self._one(
                "SELECT request_id, idempotency_fingerprint FROM tasks "
                "WHERE requester = %s AND idempotency_key = %s",
                (req.requester, idempotency_key),
            )
            if existing is None:  # pragma: no cover — key vanished mid-race
                raise ConflictError(
                    f"idempotency key {idempotency_key!r} conflicted but no row found"
                ) from None
            if existing["idempotency_fingerprint"] != fingerprint:
                raise ConflictError(
                    f"idempotency key {idempotency_key!r} was already used with a "
                    "different request body"
                ) from None
            replay = self.get_request(existing["request_id"])
            assert replay is not None
            return replay, False
        created = self.get_request(req.id)
        assert created is not None
        return created, True

    def get_request(self, request_id: str) -> WorkRequest | None:
        row = self._one(
            """
            SELECT wr.id, wr.blueprint_key, wr.title, wr.priority, wr.requester,
                   wr.owner, t.id AS task_id, t.fulfiller_type, t.state,
                   t.idempotency_key, t.blueprint_version, t.run_id, t.handle,
                   t.orphan_suspected, t.lease_owner, t.lease_expires_at
              FROM work_requests wr JOIN tasks t ON t.request_id = wr.id
             WHERE wr.id = %s
            """,
            (request_id,),
        )
        if row is None:
            return None
        task = self._task(row, id_key="task_id")
        task.gates = self._gates(task.id)
        return WorkRequest(
            id=row["id"],
            blueprint_key=row["blueprint_key"],
            title=row["title"],
            priority=Priority(row["priority"]),
            requester=row["requester"],
            owner=row["owner"],
            task=task,
        )

    # -- plan persistence (immutable job inputs; replaces in-process context) ----
    def save_plan(
        self, task_id: str, intent: Intent, preview: Preview, blueprint_version: int
    ) -> None:
        self._exec_one(
            """
            UPDATE tasks
               SET intent = %s, preview = %s, blueprint_version = %s, updated_at = now()
             WHERE id = %s
            """,
            (Json(asdict(intent)), Json(asdict(preview)), blueprint_version, task_id),
        )

    def load_plan(self, task_id: str) -> tuple[Intent, Preview, int]:
        """Fail closed: a task without a persisted plan cannot be applied/destroyed."""
        row = self._one(
            "SELECT intent, preview, blueprint_version FROM tasks WHERE id = %s",
            (task_id,),
        )
        if row is None or row["intent"] is None or row["preview"] is None:
            raise ValueError(f"task {task_id}: no persisted plan — cannot proceed")
        return (
            _decode(Intent, row["intent"]),
            _decode(Preview, row["preview"]),
            row["blueprint_version"],
        )

    # -- gates -------------------------------------------------------------------
    def upsert_gate(self, task_id: str, rec: GateRecord) -> None:
        """Gate decisions are write-once: a decided (non-pending) gate is never
        overwritten — the losing side of a concurrent decision gets ConflictError,
        so durable governance evidence can never contradict what happened."""
        self._exec_one(
            """
            INSERT INTO gate_records (task_id, type, result, decided_by, detail,
                                      decided_at)
            VALUES (%s, %s, %s, %s, %s, now())
            ON CONFLICT (task_id, type) DO UPDATE
               SET result = EXCLUDED.result, decided_by = EXCLUDED.decided_by,
                   detail = EXCLUDED.detail, decided_at = now()
               WHERE gate_records.result = 'pending'
            """,
            (task_id, rec.type.value, rec.result.value, rec.decided_by, rec.detail),
            conflict=f"task {task_id}: {rec.type.value} gate is already decided",
        )

    # -- transitions and the lease/claim protocol ---------------------------------
    def transition(self, task_id: str, expected: JobState, target: JobState) -> None:
        """Unleased transition (intake phase). Refuses to move a leased row."""
        _validate(expected, target)
        self._exec_one(
            """
            UPDATE tasks SET state = %s, updated_at = now()
             WHERE id = %s AND state = %s AND lease_owner IS NULL
            """,
            (target.value, task_id, expected.value),
            conflict=f"task {task_id}: {expected.value} -> {target.value} "
            "(state moved or row is leased)",
        )

    def claim(
        self,
        task_id: str,
        expected: JobState,
        target: JobState,
        lease_owner: str,
        lease_ttl: timedelta,
    ) -> Task:
        """Transition + take the lease in one guarded statement. This single UPDATE
        is the job lease and the per-sandbox lock."""
        _validate(expected, target)
        row = self._one(
            """
            UPDATE tasks
               SET state = %s, lease_owner = %s, lease_expires_at = now() + %s,
                   updated_at = now()
             WHERE id = %s AND state = %s
               AND (lease_expires_at IS NULL OR lease_expires_at < now())
            RETURNING *
            """,
            (target.value, lease_owner, lease_ttl, task_id, expected.value),
        )
        if row is None:
            raise ConflictError(
                f"task {task_id}: cannot claim {expected.value} -> {target.value} "
                "(state moved or another worker holds the lease)"
            )
        return self._task(row)

    def reclaim_expired(
        self, task_id: str, expected: JobState, lease_owner: str, lease_ttl: timedelta
    ) -> Task | None:
        """Take over a dead worker's expired lease without changing state.
        Returns None if the lease is live or the state moved (someone else won)."""
        row = self._one(
            """
            UPDATE tasks
               SET lease_owner = %s, lease_expires_at = now() + %s, updated_at = now()
             WHERE id = %s AND state = %s
               AND lease_expires_at IS NOT NULL AND lease_expires_at < now()
            RETURNING *
            """,
            (lease_owner, lease_ttl, task_id, expected.value),
        )
        return self._task(row) if row else None

    def record_run(self, task_id: str, run_id: str, lease_owner: str) -> None:
        """Pin the actuator-run identity. Write-once, and only by the lease holder:
        re-pinning a run or writing after a lease takeover is a bug, not a retry."""
        self._exec_one(
            "UPDATE tasks SET run_id = %s, updated_at = now() "
            "WHERE id = %s AND run_id IS NULL AND lease_owner = %s",
            (run_id, task_id, lease_owner),
            conflict=f"task {task_id}: run_id already pinned or lease lost",
        )

    def record_handle(self, task_id: str, handle: ActuatorHandle, lease_owner: str) -> None:
        # Owner-guarded like complete(): a fenced-out worker whose lease was taken
        # over must not overwrite the evidence reconciliation settled on.
        self._exec_one(
            "UPDATE tasks SET handle = %s, updated_at = now() "
            "WHERE id = %s AND lease_owner = %s",
            (Json(asdict(handle)), task_id, lease_owner),
            conflict=f"task {task_id}: cannot record handle as {lease_owner} (lease lost)",
        )

    def record_destroy_result(self, task_id: str, result: Result, lease_owner: str) -> None:
        self._exec_one(
            "UPDATE tasks SET destroy_result = %s, updated_at = now() "
            "WHERE id = %s AND lease_owner = %s",
            (Json(asdict(result)), task_id, lease_owner),
            conflict=f"task {task_id}: cannot record destroy result as {lease_owner} "
            "(lease lost)",
        )

    def load_destroy_result(self, task_id: str) -> Result | None:
        row = self._one("SELECT destroy_result FROM tasks WHERE id = %s", (task_id,))
        if row is None or row["destroy_result"] is None:
            return None
        return _decode(Result, row["destroy_result"])

    def complete(
        self, task_id: str, expected: JobState, target: JobState, lease_owner: str
    ) -> None:
        """Finish leased work: transition + release the lease, guarded by owner so a
        stale worker whose lease was taken over cannot complete."""
        _validate(expected, target)
        self._exec_one(
            """
            UPDATE tasks
               SET state = %s, lease_owner = NULL, lease_expires_at = NULL,
                   updated_at = now()
             WHERE id = %s AND state = %s AND lease_owner = %s
            """,
            (target.value, task_id, expected.value, lease_owner),
            conflict=f"task {task_id}: cannot complete {expected.value} -> "
            f"{target.value} as {lease_owner} (lease lost or state moved)",
        )

    def mark_orphan(self, task_id: str) -> None:
        self._exec_one(
            "UPDATE tasks SET orphan_suspected = TRUE, updated_at = now() WHERE id = %s",
            (task_id,),
        )

    def expired_leases(self) -> list[tuple[str, Task]]:
        """(request_id, task) pairs stuck mid-work past their lease — the reconcile
        sweep's input."""
        with self._pool.connection() as conn:
            cur = conn.cursor(row_factory=dict_row)
            cur.execute(
                """
                SELECT * FROM tasks
                 WHERE state IN ('applying', 'destroying')
                   AND lease_expires_at IS NOT NULL AND lease_expires_at < now()
                 ORDER BY updated_at
                """
            )
            return [(r["request_id"], self._task(r)) for r in cur.fetchall()]

    # -- internals -----------------------------------------------------------------
    def _one(self, query: str, params: tuple) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            cur = conn.cursor(row_factory=dict_row)
            cur.execute(query, params)
            return cur.fetchone()

    def _exec_one(self, query: str, params: tuple, conflict: str | None = None) -> None:
        """Execute a guarded UPDATE; zero rows affected raises ConflictError when a
        conflict message is given (otherwise it's a plain missing-row bug)."""
        with self._pool.connection() as conn:
            cur = conn.execute(query, params)
            if cur.rowcount == 0:
                raise ConflictError(conflict or f"no row matched: {query.split()[1]}")

    @staticmethod
    def _blueprint(row: dict[str, Any]) -> Blueprint:
        return Blueprint(
            key=row["key"],
            version=row["version"],
            name=row["name"],
            cloud=Cloud(row["cloud"]),
            tofu_module_ref=row["tofu_module_ref"],
            budget_cap_usd=float(row["budget_cap_usd"]),
            ttl_hours=row["ttl_hours"],
            allowed_roles=tuple(row["allowed_roles"]),
            availability=BlueprintAvailability(row["availability"]),
        )

    @staticmethod
    def _task(row: dict[str, Any], id_key: str = "id") -> Task:
        handle = row.get("handle")
        if handle is not None:
            handle = ActuatorHandle(
                state_backend_ref=handle["state_backend_ref"],
                workspace=handle["workspace"],
                outputs=handle.get("outputs", {}),
                status=JobState(handle["status"]),
            )
        return Task(
            id=row[id_key],
            fulfiller_type=FulfillerType(row["fulfiller_type"]),
            state=JobState(row["state"]),
            gates=[],
            handle=handle,
            idempotency_key=row.get("idempotency_key"),
            blueprint_version=row.get("blueprint_version"),
            run_id=row.get("run_id"),
            orphan_suspected=row.get("orphan_suspected", False),
            lease_owner=row.get("lease_owner"),
            lease_expires_at=row.get("lease_expires_at"),
        )

    def _gates(self, task_id: str) -> list[GateRecord]:
        with self._pool.connection() as conn:
            cur = conn.cursor(row_factory=dict_row)
            cur.execute(
                "SELECT type, result, decided_by, detail FROM gate_records "
                "WHERE task_id = %s ORDER BY id",
                (task_id,),
            )
            return [
                GateRecord(
                    type=GateType(r["type"]),
                    result=GateResult(r["result"]),
                    decided_by=r["decided_by"],
                    detail=r["detail"],
                )
                for r in cur.fetchall()
            ]
