"""Durable execution protocol: claim -> work -> record evidence -> complete.

This is the code #8's queue worker will call unchanged; today SandboxService calls
it inline. The transaction boundaries are the whole point:

  tx 1  claim(awaiting_gate -> applying)      lease taken = per-sandbox lock held
  tx 2  record_run(uuid)                      run identity pinned BEFORE side effects
  ----  actuator.apply(intent)                the multi-minute, crashable part
  tx 3  record_handle(handle)                 evidence, separate from completion
  tx 4  complete(applying -> succeeded|failed)  "the callback"

A crash between tx 3 and tx 4 IS apply-succeeded-but-callback-failed: durable
handle, stale state, expired lease — exactly what reconcile.sweep() repairs.
"""

from __future__ import annotations

import os
import socket
import uuid
from dataclasses import replace
from datetime import timedelta

from ..actuators.base import Actuator
from ..audit.log import AuditLog
from ..models.domain import AuditEvent, WorkRequest
from ..models.enums import JobState
from ..store import ConflictError, Store


def default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def audit_event(audit: AuditLog, request_id: str, etype: str, actor: str, detail: str) -> None:
    audit.append(
        AuditEvent(
            type=etype, actor=actor, request_id=request_id,
            correlation_id=request_id, detail=detail,
        )
    )


def run_apply(
    store: Store,
    actuator: Actuator,
    audit: AuditLog,
    req: WorkRequest,
    worker_id: str,
    lease_ttl: timedelta,
) -> JobState:
    if req.task is None:
        raise ValueError(f"request {req.id}: no task to apply")
    task_id = req.task.id
    try:
        task = store.claim(
            task_id, JobState.AWAITING_GATE, JobState.APPLYING, worker_id, lease_ttl
        )
    except ConflictError:
        # Not freshly claimable. If a previous worker died mid-apply (expired
        # lease), this delivery must finish that run — never start a second one.
        reclaimed = store.reclaim_expired(task_id, JobState.APPLYING, worker_id, lease_ttl)
        if reclaimed is None:
            raise
        task = reclaimed
        if task.handle is not None:
            # Work finished, callback didn't: complete from the recorded evidence.
            audit_event(audit, req.id, "job.reconciled", "system",
                        f"redelivery completed from recorded handle (run {task.run_id})")
            return _finish_apply(store, audit, req.id, task_id, task.handle, worker_id)
        # The run may have provisioned resources but left no handle. We cannot
        # know what exists — fail closed and loud; never blindly re-apply.
        store.mark_orphan(task_id)
        store.complete(task_id, JobState.APPLYING, JobState.FAILED, worker_id)
        audit_event(audit, req.id, "orphan_suspected", "system",
                    f"apply crashed before recording a handle (run {task.run_id}) — "
                    "resources may exist; reconcile/destroy required")
        return JobState.FAILED

    run_id = task.run_id or uuid.uuid4().hex
    if task.run_id is None:
        store.record_run(task_id, run_id, worker_id)
    intent, _preview, _bp_version = store.load_plan(task_id)  # fail closed if absent
    handle = actuator.apply(replace(intent, run_id=run_id))
    store.record_handle(task_id, handle, worker_id)
    return _finish_apply(store, audit, req.id, task_id, handle, worker_id)


def _finish_apply(
    store: Store,
    audit: AuditLog,
    request_id: str,
    task_id: str,
    handle,
    worker_id: str,
) -> JobState:
    if handle.status is JobState.SUCCEEDED:
        store.complete(task_id, JobState.APPLYING, JobState.SUCCEEDED, worker_id)
        # Output KEYS only — tofu outputs can carry endpoints/credentials, and the
        # audit stream is append-only and broadly readable (redaction convention).
        audit_event(audit, request_id, "applied", "system",
                    f"outputs: {sorted(handle.outputs)}")
        return JobState.SUCCEEDED
    store.complete(task_id, JobState.APPLYING, JobState.FAILED, worker_id)
    audit_event(audit, request_id, "apply_failed", "system",
                "partial resources may exist — reconcile")
    return JobState.FAILED


def run_destroy(
    store: Store,
    actuator: Actuator,
    audit: AuditLog,
    req: WorkRequest,
    worker_id: str,
    lease_ttl: timedelta,
) -> JobState:
    if req.task is None:
        raise ValueError(f"request {req.id}: no task to destroy")
    task = req.task
    # A live apply/destroy holds the lease; destroy may only start from a settled
    # state. Surface as 409, not as an invalid-transition stack trace.
    if task.state not in (JobState.SUCCEEDED, JobState.FAILED):
        raise ConflictError(
            f"task {task.id}: cannot destroy from {task.state.value} (job in flight)"
        )
    # Fail closed: no parseable handle -> no destroy (global invariant).
    handle = task.handle
    if handle is None or not handle.state_backend_ref or not handle.workspace:
        audit_event(audit, req.id, "destroy_blocked", "system",
                    "missing or unparseable actuator handle — fail closed, no destroy")
        raise ValueError(f"task {task.id}: missing/unparseable handle — cannot destroy")

    store.claim(task.id, task.state, JobState.DESTROYING, worker_id, lease_ttl)
    # Fail closed: a task whose persisted plan is missing/corrupt must not be
    # destroyed blind. (RealActuator (#8) will consume the pinned plan itself;
    # DummyActuator destroys from the handle alone.)
    store.load_plan(task.id)
    result = actuator.destroy(handle)
    store.record_destroy_result(task.id, result, worker_id)
    if result.ok:
        store.complete(task.id, JobState.DESTROYING, JobState.DESTROYED, worker_id)
        audit_event(audit, req.id, "destroyed", "system", result.detail)
        return JobState.DESTROYED
    store.mark_orphan(task.id)
    store.complete(task.id, JobState.DESTROYING, JobState.FAILED, worker_id)
    audit_event(audit, req.id, "destroy_failed", "system",
                f"{result.detail} — resources may remain; reconcile required")
    return JobState.FAILED
