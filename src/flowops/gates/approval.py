"""Approval gate. Role-gated, fail-closed.

Undecided -> PENDING (the loop waits). An approval by a role NOT in allowed_roles ->
FAIL (an unknown/unpermitted approver can never grant). Deny -> FAIL.
"""

from __future__ import annotations

from ..models.enums import GateResult, GateType
from .base import GateContext


class ApprovalGate:
    type = GateType.APPROVAL

    def evaluate(self, ctx: GateContext) -> GateResult:
        if ctx.approval is None:
            return GateResult.PENDING
        decision, role = ctx.approval
        # Fail closed: only an allowed role may decide; anything else is a FAIL.
        if role not in ctx.allowed_roles:
            return GateResult.FAIL
        if decision == "approve":
            return GateResult.PASS
        return GateResult.FAIL  # "deny" or anything unrecognized
