"""Budget gate. Fail-closed on a missing estimate.

In the cloud profile, a PASS means "and a real AWS Budget + SCP + quota will be set on
the sandbox account at provision time" — the cap is a hard ceiling the cloud enforces,
not a user's promise (SR2 adds the aggregate cap on top). In dev, the gate is advisory
and clearly labeled, but it STILL fails closed: no cost estimate -> no apply.
"""

from __future__ import annotations

from ..models.enums import GateResult, GateType
from .base import GateContext


class BudgetGate:
    type = GateType.BUDGET

    def evaluate(self, ctx: GateContext) -> GateResult:
        # Fail closed: no preview, or no cost estimate -> DENY. Never assume "probably fine".
        if ctx.preview is None or ctx.preview.cost_usd is None:
            return GateResult.FAIL
        if ctx.preview.cost_usd > ctx.budget_cap_usd:
            return GateResult.FAIL
        return GateResult.PASS
