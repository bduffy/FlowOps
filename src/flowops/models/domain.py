"""FlowOps domain entities. The request -> task -> action spine, kept thin.

No ITSM ceremony (no SLAs, categories, queues) — that's deliberate. The Task IS the
provisioning job; the action IS the actuator call. (See docs/ARCHITECTURE_AND_DESIGN.md
§4.6, cross-model tension 3.)

  WorkRequest ──has──▶ Task ──drives──▶ ActuatorHandle
       │                 │
       │                 └──gated by──▶ GateRecord (approval, budget)
       └──────────── every transition ──▶ AuditEvent (append-only)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from .enums import (
    BlueprintAvailability,
    Cloud,
    FulfillerType,
    GateResult,
    GateType,
    JobState,
    Priority,
)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class Blueprint:
    """What can be provisioned. v1: a dev sandbox. Admin-curated catalog only (SR1)."""

    key: str  # e.g. "dev-sandbox"
    name: str
    cloud: Cloud
    tofu_module_ref: str  # pinned ref — never user-supplied (SR1)
    budget_cap_usd: float
    ttl_hours: int
    version: int = 1  # snapshotted onto the task at apply; destroy runs the snapshot
    allowed_roles: tuple[str, ...] = ("admin", "worker")
    availability: BlueprintAvailability = BlueprintAvailability.AVAILABLE


@dataclass
class GateRecord:
    """A gate evaluated on a task transition. Result defaults PENDING (fail-closed)."""

    type: GateType
    result: GateResult = GateResult.PENDING
    decided_by: str | None = None
    detail: str | None = None


@dataclass
class ActuatorHandle:
    """Locates provisioned state so destroy can find it. Returned by apply()."""

    state_backend_ref: str
    workspace: str
    outputs: dict[str, str] = field(default_factory=dict)
    status: JobState = JobState.QUEUED


@dataclass
class Task:
    """A unit of fulfillment. fulfiller_type may be human | automation | agent."""

    id: str = field(default_factory=lambda: _id("task"))
    fulfiller_type: FulfillerType = FulfillerType.AUTOMATION
    state: JobState = JobState.QUEUED
    gates: list[GateRecord] = field(default_factory=list)
    handle: ActuatorHandle | None = None
    # Durable-job fields (#5). The task IS the job row; 1:1 task<->sandbox means
    # the row lease doubles as the per-sandbox lock.
    idempotency_key: str | None = None
    blueprint_version: int | None = None  # pinned at submit (§4.6)
    run_id: str | None = None  # actuator-run identity, pinned before side effects
    orphan_suspected: bool = False
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None


@dataclass
class WorkRequest:
    """The intake unit. A sandbox request is one of these."""

    id: str = field(default_factory=lambda: _id("wr"))
    blueprint_key: str = ""
    title: str = ""
    priority: Priority = Priority.MEDIUM
    requester: str = ""
    owner: str = ""  # who may extend/destroy (authz; SR7)
    task: Task | None = None


@dataclass(frozen=True)
class AuditEvent:
    """Append-only governance event. Immutable by construction (frozen)."""

    type: str
    actor: str
    request_id: str
    correlation_id: str
    detail: str = ""
    # ts is stamped by the caller/store, not here, to keep this layer time-free.
