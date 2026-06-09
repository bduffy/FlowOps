"""RealActuator — runs OpenTofu in a serverless container job. STUB.

Wired in issues #7 (interface), #8 (queue + container runner), #10 (state security),
#11 (module supply-chain). Until then it refuses to run rather than pretend — the
DummyActuator covers the dev loop. (Capability flags surface this honestly in the UI.)
"""

from __future__ import annotations

from ..models.domain import ActuatorHandle
from ..models.enums import JobState
from .base import Intent, Preview, Result

_NOT_READY = (
    "RealActuator is not implemented yet (issues #8/#10/#11). "
    "Run with FLOWOPS_PROFILE=dev to use the DummyActuator."
)


class RealActuator:
    name = "real"

    def plan(self, intent: Intent) -> Preview:  # pragma: no cover - stub
        raise NotImplementedError(_NOT_READY)

    def apply(self, intent: Intent) -> ActuatorHandle:  # pragma: no cover - stub
        raise NotImplementedError(_NOT_READY)

    def destroy(self, handle: ActuatorHandle) -> Result:  # pragma: no cover - stub
        raise NotImplementedError(_NOT_READY)

    def status(self, handle: ActuatorHandle) -> JobState:  # pragma: no cover - stub
        raise NotImplementedError(_NOT_READY)
