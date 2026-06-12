"""Governed-loop tests over the durable jobs table (ported from the in-memory
scaffold's LoopTests — assertions unchanged, persistence real)."""

from __future__ import annotations

import pytest

from flowops.models.enums import JobState
from flowops.services import SandboxService


def test_happy_path_submit_approve_apply_teardown(service):
    req, _ = service.submit("dev-sandbox", "AWS dev sandbox", requester="jdoe", owner="jdoe")
    assert service.state(req.id) is JobState.AWAITING_GATE

    service.decide(req.id, "approve", role="admin", actor="ssmith")
    assert service.state(req.id) is JobState.SUCCEEDED

    service.teardown(req.id, actor="jdoe", actor_role="worker")  # owner may destroy
    assert service.state(req.id) is JobState.DESTROYED

    kinds = [e.type for e in service.audit.for_request(req.id)]
    for expected in ("request.created", "planned", "approved", "applied", "destroyed"):
        assert expected in kinds


def test_deny_rejects(service):
    req, _ = service.submit("dev-sandbox", "x", requester="jdoe", owner="jdoe")
    service.decide(req.id, "deny", role="admin", actor="boss")
    assert service.state(req.id) is JobState.REJECTED


def test_unknown_role_cannot_approve(service):
    req, _ = service.submit("dev-sandbox", "x", requester="jdoe", owner="jdoe")
    service.decide(req.id, "approve", role="intern", actor="intern")
    assert service.state(req.id) is JobState.REJECTED


def test_teardown_authz_fail_closed(service):
    req, _ = service.submit("dev-sandbox", "x", requester="jdoe", owner="jdoe")
    service.decide(req.id, "approve", role="admin", actor="admin")
    with pytest.raises(PermissionError):
        service.teardown(req.id, actor="mallory", actor_role="worker")


def test_budget_gate_fail_rejects_at_submit(dev_settings, store):
    from flowops.actuators.base import Preview
    from flowops.actuators.dummy import DummyActuator
    from flowops.models.enums import GateResult, GateType

    class ExpensiveActuator(DummyActuator):
        def plan(self, intent):
            return Preview(summary="pricey", cost_usd=intent.budget_cap_usd * 10)

    svc = SandboxService(dev_settings, store=store, actuator=ExpensiveActuator())
    req, created = svc.submit("dev-sandbox", "x", requester="jdoe", owner="jdoe")

    assert created is True
    assert svc.state(req.id) is JobState.REJECTED
    assert "rejected" in [e.type for e in svc.audit.for_request(req.id)]
    budget = [g for g in req.task.gates if g.type is GateType.BUDGET]
    assert [g.result for g in budget] == [GateResult.FAIL]


def test_failed_apply_lands_in_failed(dev_settings, store):
    from flowops.actuators.dummy import DummyActuator

    class AlwaysFailActuator(DummyActuator):
        def apply(self, intent):
            from dataclasses import replace

            return super().apply(replace(intent, inject_failure=True))

    svc = SandboxService(dev_settings, store=store, actuator=AlwaysFailActuator())
    req, _ = svc.submit("dev-sandbox", "x", requester="jdoe", owner="jdoe")
    svc.decide(req.id, "approve", role="admin", actor="admin")
    assert svc.state(req.id) is JobState.FAILED
    assert "apply_failed" in [e.type for e in svc.audit.for_request(req.id)]
