"""Core loop tests. Pure stdlib — run with: PYTHONPATH=src python3 -m unittest -v

Proves the governed-actuation loop in dev mode with no cloud, no DB, no third-party deps.
"""

import unittest

from flowops.actuators.base import Intent, Preview
from flowops.actuators.dummy import DummyActuator
from flowops.config import Settings
from flowops.gates.approval import ApprovalGate
from flowops.gates.base import GateContext
from flowops.gates.budget import BudgetGate
from flowops.jobs.state_machine import InvalidTransition, can_transition, transition
from flowops.models.enums import GateResult, JobState, Profile
from flowops.services import SandboxService

DEV = Settings(profile=Profile.DEV, region="us-east-1")
ROLES = ("admin", "worker")


def _intent(cap=50.0, fail=False):
    return Intent(
        blueprint_key="dev-sandbox",
        tofu_module_ref="ref",
        region="us-east-1",
        budget_cap_usd=cap,
        ttl_hours=24,
        run_id="r123",
        inject_failure=fail,
    )


class DummyActuatorTests(unittest.TestCase):
    def setUp(self):
        self.a = DummyActuator()

    def test_plan_returns_cost(self):
        p = self.a.plan(_intent(cap=50))
        self.assertEqual(p.cost_usd, 25.0)

    def test_apply_then_destroy(self):
        h = self.a.apply(_intent())
        self.assertIs(h.status, JobState.SUCCEEDED)
        self.assertIn("sandbox_id", h.outputs)
        self.a.destroy(h)
        self.assertIs(self.a.status(h), JobState.DESTROYED)

    def test_inject_failure(self):
        h = self.a.apply(_intent(fail=True))
        self.assertIs(h.status, JobState.FAILED)


class BudgetGateFailClosedTests(unittest.TestCase):
    def setUp(self):
        self.g = BudgetGate()

    def _ctx(self, preview, cap=50.0):
        return GateContext(preview=preview, budget_cap_usd=cap, allowed_roles=ROLES, profile=Profile.DEV)

    def test_missing_preview_fails_closed(self):
        self.assertIs(self.g.evaluate(self._ctx(None)), GateResult.FAIL)

    def test_missing_cost_fails_closed(self):
        self.assertIs(self.g.evaluate(self._ctx(Preview("x", None))), GateResult.FAIL)

    def test_over_cap_fails(self):
        self.assertIs(self.g.evaluate(self._ctx(Preview("x", 80.0))), GateResult.FAIL)

    def test_under_cap_passes(self):
        self.assertIs(self.g.evaluate(self._ctx(Preview("x", 25.0))), GateResult.PASS)


class ApprovalGateFailClosedTests(unittest.TestCase):
    def setUp(self):
        self.g = ApprovalGate()

    def _ctx(self, approval):
        return GateContext(
            preview=Preview("x", 1.0), budget_cap_usd=50, allowed_roles=ROLES, profile=Profile.DEV, approval=approval
        )

    def test_pending_when_undecided(self):
        self.assertIs(self.g.evaluate(self._ctx(None)), GateResult.PENDING)

    def test_unknown_role_fails_closed(self):
        self.assertIs(self.g.evaluate(self._ctx(("approve", "intern"))), GateResult.FAIL)

    def test_deny_fails(self):
        self.assertIs(self.g.evaluate(self._ctx(("deny", "admin"))), GateResult.FAIL)

    def test_approve_by_allowed_role_passes(self):
        self.assertIs(self.g.evaluate(self._ctx(("approve", "admin"))), GateResult.PASS)


class StateMachineTests(unittest.TestCase):
    def test_legal(self):
        self.assertTrue(can_transition(JobState.QUEUED, JobState.PLANNING))
        self.assertEqual(transition(JobState.APPLYING, JobState.SUCCEEDED), JobState.SUCCEEDED)

    def test_illegal_raises(self):
        with self.assertRaises(InvalidTransition):
            transition(JobState.QUEUED, JobState.SUCCEEDED)

    def test_terminal_states_have_no_exits(self):
        self.assertFalse(can_transition(JobState.DESTROYED, JobState.QUEUED))
        self.assertFalse(can_transition(JobState.REJECTED, JobState.APPLYING))


class _AlwaysFailActuator(DummyActuator):
    def apply(self, intent):  # noqa: D401
        return super().apply(_intent(fail=True))


class LoopTests(unittest.TestCase):
    def test_happy_path_submit_approve_apply_teardown(self):
        svc = SandboxService(DEV)
        req = svc.submit("dev-sandbox", "AWS dev sandbox", requester="jdoe", owner="jdoe")
        self.assertIs(svc.state(req.id), JobState.AWAITING_GATE)

        svc.decide(req.id, "approve", role="admin", actor="ssmith")
        self.assertIs(svc.state(req.id), JobState.SUCCEEDED)

        svc.teardown(req.id, actor="jdoe", actor_role="worker")  # owner may destroy
        self.assertIs(svc.state(req.id), JobState.DESTROYED)

        kinds = [e.type for e in svc.audit.for_request(req.id)]
        for expected in ("request.created", "planned", "approved", "applied", "destroyed"):
            self.assertIn(expected, kinds)

    def test_deny_rejects(self):
        svc = SandboxService(DEV)
        req = svc.submit("dev-sandbox", "x", requester="jdoe", owner="jdoe")
        svc.decide(req.id, "deny", role="admin", actor="boss")
        self.assertIs(svc.state(req.id), JobState.REJECTED)

    def test_unknown_role_cannot_approve(self):
        svc = SandboxService(DEV)
        req = svc.submit("dev-sandbox", "x", requester="jdoe", owner="jdoe")
        svc.decide(req.id, "approve", role="intern", actor="intern")
        self.assertIs(svc.state(req.id), JobState.REJECTED)

    def test_teardown_authz_fail_closed(self):
        svc = SandboxService(DEV)
        req = svc.submit("dev-sandbox", "x", requester="jdoe", owner="jdoe")
        svc.decide(req.id, "approve", role="admin", actor="admin")
        with self.assertRaises(PermissionError):
            svc.teardown(req.id, actor="mallory", actor_role="worker")

    def test_failed_apply_lands_in_failed(self):
        svc = SandboxService(DEV, actuator=_AlwaysFailActuator())
        req = svc.submit("dev-sandbox", "x", requester="jdoe", owner="jdoe")
        svc.decide(req.id, "approve", role="admin", actor="admin")
        self.assertIs(svc.state(req.id), JobState.FAILED)
        self.assertIn("apply_failed", [e.type for e in svc.audit.for_request(req.id)])


if __name__ == "__main__":
    unittest.main()
