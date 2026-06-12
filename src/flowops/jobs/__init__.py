"""Jobs — the provisioning state machine. One path serves apply AND destroy.

Persistence (the durable jobs table with idempotency keys, per-sandbox locks, and
leases) lands in issue #5; this module is the pure state-transition logic it builds on.
"""

from .state_machine import InvalidTransition, can_transition, transition

__all__ = ["InvalidTransition", "can_transition", "transition"]
