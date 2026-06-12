"""Job state machine.

  queued ─▶ planning ─▶ awaiting_gate ─▶ applying ─▶ succeeded ─▶ destroying ─▶ destroyed
     │          │             │             │                        ▲
     ▼          ▼             ▼             ▼                        │
  failed     failed       rejected       failed ───── reconcile ─────┘

Illegal transitions raise — the state machine is the guardrail, not a suggestion.
"""

from __future__ import annotations

from ..models.enums import JobState

_LEGAL: dict[JobState, frozenset[JobState]] = {
    JobState.QUEUED: frozenset({JobState.PLANNING, JobState.REJECTED, JobState.FAILED}),
    JobState.PLANNING: frozenset({JobState.AWAITING_GATE, JobState.FAILED}),
    JobState.AWAITING_GATE: frozenset({JobState.APPLYING, JobState.REJECTED}),
    JobState.APPLYING: frozenset({JobState.SUCCEEDED, JobState.FAILED}),
    JobState.SUCCEEDED: frozenset({JobState.DESTROYING}),
    JobState.FAILED: frozenset({JobState.DESTROYING}),  # reconcile / orphan cleanup
    JobState.DESTROYING: frozenset({JobState.DESTROYED, JobState.FAILED}),
    JobState.REJECTED: frozenset(),  # terminal
    JobState.DESTROYED: frozenset(),  # terminal
}


class InvalidTransition(Exception):
    """Raised when a job is asked to make an illegal state transition."""


def can_transition(current: JobState, target: JobState) -> bool:
    return target in _LEGAL.get(current, frozenset())


def transition(current: JobState, target: JobState) -> JobState:
    if not can_transition(current, target):
        raise InvalidTransition(f"{current.value} -> {target.value} is not allowed")
    return target
