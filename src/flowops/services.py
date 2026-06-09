"""SandboxService — the governed-actuation loop, profile-agnostic.

  submit ─▶ plan ─▶ [budget gate] ─▶ awaiting approval
                                          │
                       decide(approve) ───┼──▶ apply ─▶ succeeded ─▶ teardown ─▶ destroyed
                       decide(deny)   ────┘     (or failed)
  every transition appends an AuditEvent.

This is identical in dev and cloud — only the injected Actuator differs. Persistence,
durable jobs, queue/worker, and the TTL scheduler are layered on later (#5, #8, #13);
here the loop runs synchronously in memory so dev mode works with zero infra.
"""

from __future__ import annotations

import uuid

from .actuators.base import Actuator, Intent, Preview
from .audit.log import AuditLog
from .config import Settings, get_actuator
from .gates.approval import ApprovalGate
from .gates.base import GateContext
from .gates.budget import BudgetGate
from .jobs.state_machine import transition
from .models.domain import AuditEvent, GateRecord, Task, WorkRequest
from .models.enums import FulfillerType, GateResult, GateType, JobState
from .store import InMemoryStore


class SandboxService:
    def __init__(
        self,
        settings: Settings,
        store: InMemoryStore | None = None,
        actuator: Actuator | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        self.settings = settings
        self.store = store or InMemoryStore()
        self.actuator = actuator or get_actuator(settings)
        self.audit = audit or AuditLog()
        self._budget = BudgetGate()
        self._approval = ApprovalGate()
        self._ctx: dict[str, tuple[Intent, Preview]] = {}

    # -- internals -----------------------------------------------------------
    def _audit(self, req: WorkRequest, etype: str, actor: str, detail: str = "") -> None:
        self.audit.append(
            AuditEvent(
                type=etype, actor=actor, request_id=req.id, correlation_id=req.id, detail=detail
            )
        )

    def _move(self, task: Task, target: JobState) -> None:
        task.state = transition(task.state, target)  # raises on illegal transition

    def _gate_record(self, task: Task, gtype: GateType) -> GateRecord:
        for g in task.gates:
            if g.type is gtype:
                return g
        rec = GateRecord(type=gtype)
        task.gates.append(rec)
        return rec

    # -- the loop ------------------------------------------------------------
    def submit(self, blueprint_key: str, title: str, requester: str, owner: str) -> WorkRequest:
        bp = self.store.blueprints.get(blueprint_key)
        if bp is None:
            raise KeyError(f"unknown blueprint: {blueprint_key}")

        task = Task(fulfiller_type=FulfillerType.AUTOMATION)
        req = WorkRequest(
            blueprint_key=blueprint_key, title=title, requester=requester, owner=owner, task=task
        )
        self.store.add_request(req)
        self._audit(req, "request.created", requester, title)

        self._move(task, JobState.PLANNING)
        intent = Intent(
            blueprint_key=bp.key,
            tofu_module_ref=bp.tofu_module_ref,
            region=self.settings.region,
            budget_cap_usd=bp.budget_cap_usd,
            ttl_hours=bp.ttl_hours,
            run_id=uuid.uuid4().hex[:10],
        )
        preview = self.actuator.plan(intent)
        self._ctx[req.id] = (intent, preview)
        self._audit(req, "planned", "system", preview.summary)

        self._move(task, JobState.AWAITING_GATE)

        # Budget gate decides immediately from the preview (fail-closed inside the gate).
        budget_ctx = GateContext(
            preview=preview,
            budget_cap_usd=bp.budget_cap_usd,
            allowed_roles=bp.allowed_roles,
            profile=self.settings.profile,
        )
        budget_rec = self._gate_record(task, GateType.BUDGET)
        budget_rec.result = self._budget.evaluate(budget_ctx)
        budget_rec.detail = (
            f"cost={preview.cost_usd} cap={bp.budget_cap_usd} "
            f"({'advisory' if self.settings.is_dev else 'cloud-enforced'})"
        )
        if budget_rec.result is GateResult.FAIL:
            self._move(task, JobState.REJECTED)
            self._audit(req, "rejected", "system", "budget gate failed")
            return req

        # Approval gate starts PENDING — the loop waits for decide().
        self._gate_record(task, GateType.APPROVAL).result = GateResult.PENDING
        return req

    def decide(self, request_id: str, decision: str, role: str, actor: str) -> WorkRequest:
        req = self.store.get_request(request_id)
        if req is None or req.task is None:
            raise KeyError(f"unknown request: {request_id}")
        task = req.task
        if task.state is not JobState.AWAITING_GATE:
            raise ValueError(f"request {request_id} is not awaiting a decision ({task.state.value})")

        bp = self.store.blueprints[req.blueprint_key]
        ctx = GateContext(
            preview=self._ctx[req.id][1],
            budget_cap_usd=bp.budget_cap_usd,
            allowed_roles=bp.allowed_roles,
            profile=self.settings.profile,
            approval=(decision, role),
        )
        rec = self._gate_record(task, GateType.APPROVAL)
        rec.result = self._approval.evaluate(ctx)
        rec.decided_by = actor

        if rec.result is not GateResult.PASS:
            self._move(task, JobState.REJECTED)
            self._audit(req, "rejected", actor, f"approval={rec.result.value} role={role}")
            return req

        self._audit(req, "approved", actor, f"role={role}")
        self._move(task, JobState.APPLYING)
        handle = self.actuator.apply(self._ctx[req.id][0])
        task.handle = handle
        if handle.status is JobState.SUCCEEDED:
            self._move(task, JobState.SUCCEEDED)
            self._audit(req, "applied", "system", str(handle.outputs))
        else:
            self._move(task, JobState.FAILED)
            self._audit(req, "apply_failed", "system", "partial resources may exist — reconcile")
        return req

    def teardown(self, request_id: str, actor: str, actor_role: str) -> WorkRequest:
        req = self.store.get_request(request_id)
        if req is None or req.task is None:
            raise KeyError(f"unknown request: {request_id}")
        # SR7: only the owner or an admin may destroy. Fail closed.
        if actor != req.owner and actor_role != "admin":
            raise PermissionError("teardown requires the request owner or an admin")
        task = req.task
        if task.handle is None:
            raise ValueError("nothing provisioned to tear down")

        self._move(task, JobState.DESTROYING)
        self._audit(req, "destroy_requested", actor, f"role={actor_role}")
        self.actuator.destroy(task.handle)
        self._move(task, JobState.DESTROYED)
        self._audit(req, "destroyed", "system", "")
        return req

    def state(self, request_id: str) -> JobState:
        req = self.store.get_request(request_id)
        if req is None or req.task is None:
            raise KeyError(f"unknown request: {request_id}")
        return req.task.state
