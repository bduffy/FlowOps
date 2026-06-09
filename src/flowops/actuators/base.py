"""The Actuator seam. The ONE abstraction in v1.

  plan(intent)   -> Preview   (pre-flight: what + estimated cost; feeds the budget gate)
  apply(intent)  -> Handle    (provision; returns a state-locating handle)
  destroy(handle)-> Result
  status(handle) -> JobState  (reads tracked state, NOT a live cloud poll)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..models.domain import ActuatorHandle
from ..models.enums import JobState


@dataclass(frozen=True)
class Intent:
    """What to provision. Built from a Blueprint + request. Immutable."""

    blueprint_key: str
    tofu_module_ref: str
    region: str
    budget_cap_usd: float
    ttl_hours: int
    run_id: str
    inject_failure: bool = False  # test/dev lever: force a mid-apply failure


@dataclass(frozen=True)
class Preview:
    """Pre-flight result. cost_usd is None when the estimate is unavailable.

    A None cost is the fail-closed trigger for the budget gate: no estimate -> no apply.
    """

    summary: str
    cost_usd: float | None


@dataclass(frozen=True)
class Result:
    ok: bool
    detail: str = ""


@runtime_checkable
class Actuator(Protocol):
    """Both DummyActuator and RealActuator implement this. Nothing else in v1."""

    def plan(self, intent: Intent) -> Preview: ...
    def apply(self, intent: Intent) -> ActuatorHandle: ...
    def destroy(self, handle: ActuatorHandle) -> Result: ...
    def status(self, handle: ActuatorHandle) -> JobState: ...
