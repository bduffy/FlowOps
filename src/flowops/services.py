"""SandboxService — the governed-actuation loop, profile-agnostic.

  submit ─▶ plan ─▶ [budget gate] ─▶ awaiting approval
                                          │
                       decide(approve) ───┼──▶ apply ─▶ succeeded ─▶ teardown ─▶ destroyed
                       decide(deny)   ────┘     (or failed)
  every transition appends an AuditEvent.

This is identical in dev and cloud — only the injected Actuator differs. State lives
in the durable jobs table (#5): the plan (intent + preview + pinned blueprint version)
is persisted at submit, and apply/destroy run through jobs.executor's claim/lease
protocol — the same code path #8's queue worker will drive.
"""

from __future__ import annotations

from datetime import timedelta

from .actuators.base import Actuator, Intent
from .audit.log import AuditLog
from .config import Settings, get_actuator
from .gates.approval import ApprovalGate
from .gates.base import GateContext
from .gates.budget import BudgetGate
from .jobs import executor
from .models.domain import AuditEvent, GateRecord, Task, WorkRequest
from .models.enums import FulfillerType, GateResult, GateType, JobState
from .store import Store


class SandboxService:
    def __init__(
        self,
        settings: Settings,
        store: Store,
        actuator: Actuator | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.actuator = actuator or get_actuator(settings)
        self.audit = audit or AuditLog()
        self._budget = BudgetGate()
        self._approval = ApprovalGate()
        self._lease_ttl = timedelta(seconds=settings.lease_ttl_seconds)

    # -- internals -----------------------------------------------------------
    def _audit(self, req: WorkRequest, etype: str, actor: str, detail: str = "") -> None:
        self.audit.append(
            AuditEvent(
                type=etype, actor=actor, request_id=req.id, correlation_id=req.id, detail=detail
            )
        )

    def _get(self, request_id: str) -> WorkRequest:
        req = self.store.get_request(request_id)
        if req is None or req.task is None:
            raise KeyError(f"unknown request: {request_id}")
        return req

    # -- the loop ------------------------------------------------------------
    def submit(
        self,
        blueprint_key: str,
        title: str,
        requester: str,
        owner: str,
        idempotency_key: str | None = None,
    ) -> tuple[WorkRequest, bool]:
        """Returns (request, created). A replayed idempotency key returns the
        existing request without re-running plan or gates."""
        bp = self.store.get_blueprint(blueprint_key)
        if bp is None:
            raise KeyError(f"unknown blueprint: {blueprint_key}")

        task = Task(fulfiller_type=FulfillerType.AUTOMATION, idempotency_key=idempotency_key)
        req = WorkRequest(
            blueprint_key=blueprint_key, title=title, requester=requester, owner=owner, task=task
        )
        req, created = self.store.create_request(req, task, idempotency_key)
        if not created:
            self._audit(req, "idempotent_replay", requester, f"key={idempotency_key}")
            return req, False
        self._audit(req, "request.created", requester, title)

        self.store.transition(task.id, JobState.QUEUED, JobState.PLANNING)
        # run_id stays empty in the frozen inputs: the real run identity is pinned
        # by the executor at claim time (store.record_run), a single source of truth.
        intent = Intent(
            blueprint_key=bp.key,
            tofu_module_ref=bp.tofu_module_ref,
            region=self.settings.region,
            budget_cap_usd=bp.budget_cap_usd,
            ttl_hours=bp.ttl_hours,
            run_id="",
        )
        preview = self.actuator.plan(intent)
        # Immutable job inputs, frozen at submit: destroy will run THIS module ref
        # at THIS version, regardless of later blueprint edits.
        self.store.save_plan(task.id, intent, preview, bp.version)
        self._audit(req, "planned", "system", preview.summary)

        self.store.transition(task.id, JobState.PLANNING, JobState.AWAITING_GATE)

        # Budget gate decides immediately from the preview (fail-closed inside the gate).
        budget_ctx = GateContext(
            preview=preview,
            budget_cap_usd=bp.budget_cap_usd,
            allowed_roles=bp.allowed_roles,
            profile=self.settings.profile,
        )
        budget_rec = GateRecord(type=GateType.BUDGET, result=self._budget.evaluate(budget_ctx))
        budget_rec.detail = (
            f"cost={preview.cost_usd} cap={bp.budget_cap_usd} "
            f"({'advisory' if self.settings.is_dev else 'cloud-enforced'})"
        )
        self.store.upsert_gate(task.id, budget_rec)
        if budget_rec.result is GateResult.FAIL:
            self.store.transition(task.id, JobState.AWAITING_GATE, JobState.REJECTED)
            self._audit(req, "rejected", "system", "budget gate failed")
            return self._get(req.id), True

        # Approval gate starts PENDING — the loop waits for decide().
        self.store.upsert_gate(task.id, GateRecord(type=GateType.APPROVAL))
        return self._get(req.id), True

    def decide(self, request_id: str, decision: str, role: str, actor: str) -> WorkRequest:
        req = self._get(request_id)
        task = req.task
        assert task is not None
        if task.state is not JobState.AWAITING_GATE:
            raise ValueError(
                f"request {request_id} is not awaiting a decision ({task.state.value})"
            )

        bp = self.store.get_blueprint(req.blueprint_key)
        if bp is None:  # blueprint deleted between submit and decide — fail closed
            raise KeyError(f"unknown blueprint: {req.blueprint_key}")
        _intent, preview, _version = self.store.load_plan(task.id)
        ctx = GateContext(
            preview=preview,
            budget_cap_usd=bp.budget_cap_usd,
            allowed_roles=bp.allowed_roles,
            profile=self.settings.profile,
            approval=(decision, role),
        )
        rec = GateRecord(type=GateType.APPROVAL, result=self._approval.evaluate(ctx))
        rec.decided_by = actor
        self.store.upsert_gate(task.id, rec)

        if rec.result is not GateResult.PASS:
            self.store.transition(task.id, JobState.AWAITING_GATE, JobState.REJECTED)
            self._audit(req, "rejected", actor, f"approval={rec.result.value} role={role}")
            return self._get(req.id)

        self._audit(req, "approved", actor, f"role={role}")
        executor.run_apply(
            self.store, self.actuator, self.audit, req,
            executor.default_worker_id(), self._lease_ttl,
        )
        return self._get(req.id)

    def teardown(self, request_id: str, actor: str, actor_role: str) -> WorkRequest:
        req = self._get(request_id)
        # SR7: only the owner or an admin may destroy. Fail closed.
        if actor != req.owner and actor_role != "admin":
            raise PermissionError("teardown requires the request owner or an admin")

        self._audit(req, "destroy_requested", actor, f"role={actor_role}")
        executor.run_destroy(
            self.store, self.actuator, self.audit, req,
            executor.default_worker_id(), self._lease_ttl,
        )
        return self._get(req.id)

    def state(self, request_id: str) -> JobState:
        # status() reads the jobs table — never a live cloud poll (arch §4.2).
        req = self._get(request_id)
        assert req.task is not None
        return req.task.state
