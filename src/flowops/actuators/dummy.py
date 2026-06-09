"""DummyActuator — simulated provisioning. No cloud, no OpenTofu.

Powers the dev profile, IS the test double, and stands in for not-yet-live
capabilities. Deterministic so tests are stable. The whole governed-actuation loop
(intake -> gate -> status -> teardown) runs against this with zero cloud credentials.
"""

from __future__ import annotations

from ..models.domain import ActuatorHandle
from ..models.enums import JobState
from .base import Actuator, Intent, Preview, Result


class DummyActuator:
    """In-memory simulation of plan/apply/destroy/status."""

    name = "dummy"

    def plan(self, intent: Intent) -> Preview:
        # Deterministic "estimate": a function of the cap so tests can assert on it.
        # NOTE: a real estimate is never fabricated; in cloud, cost is the enforced
        # budget config, not a guess (see BudgetGate / SR2).
        cost = round(intent.budget_cap_usd * 0.5, 2)
        return Preview(summary=f"[dummy] would provision {intent.blueprint_key}", cost_usd=cost)

    def apply(self, intent: Intent) -> ActuatorHandle:
        handle = ActuatorHandle(
            state_backend_ref=f"memory://{intent.run_id}",
            workspace=intent.run_id,
        )
        if intent.inject_failure:
            # Simulate a mid-apply failure AFTER partial work — the dangerous path.
            handle.status = JobState.FAILED
            handle.outputs = {"partial": "true"}
            return handle
        handle.status = JobState.SUCCEEDED
        handle.outputs = {"sandbox_id": f"dummy-{intent.run_id}", "console_url": "about:blank"}
        return handle

    def destroy(self, handle: ActuatorHandle) -> Result:
        handle.status = JobState.DESTROYED
        handle.outputs = {}
        return Result(ok=True, detail="[dummy] destroyed")

    def status(self, handle: ActuatorHandle) -> JobState:
        return handle.status


# Static type check: DummyActuator satisfies the Actuator protocol.
_: Actuator = DummyActuator()
