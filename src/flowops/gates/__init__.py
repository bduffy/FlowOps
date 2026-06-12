"""Gates — concrete, no plugin registry in v1. Approval + budget.

GLOBAL INVARIANT: fail closed. Every gate defaults to DENY on ambiguity. A missing
cost estimate, an unknown approver, an unparseable input -> FAIL, never PASS.
"""

from .approval import ApprovalGate
from .base import Gate, GateContext
from .budget import BudgetGate

__all__ = ["Gate", "GateContext", "ApprovalGate", "BudgetGate"]
