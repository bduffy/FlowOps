"""Gate interface + evaluation context. Concrete gates live alongside this file."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..actuators.base import Preview
from ..models.enums import GateResult, GateType, Profile


@dataclass(frozen=True)
class GateContext:
    """Everything a gate needs to decide. Immutable per evaluation."""

    preview: Preview | None
    budget_cap_usd: float
    allowed_roles: tuple[str, ...]
    profile: Profile
    # An approval decision, when one has been made: (decision, role).
    # decision in {"approve", "deny"}. None => not yet decided.
    approval: tuple[str, str] | None = None


@runtime_checkable
class Gate(Protocol):
    type: GateType

    def evaluate(self, ctx: GateContext) -> GateResult: ...
