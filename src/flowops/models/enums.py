"""FlowOps enums. The vocabulary of the governed-actuation loop."""

from __future__ import annotations

from enum import Enum


class Profile(str, Enum):
    """Execution profile. Everything above the actuator is identical across profiles."""

    DEV = "dev"  # DummyActuator, local queue/worker, advisory budget. Zero cloud creds.
    CLOUD = "cloud"  # RealActuator, managed queue + container job, cloud-enforced budget.


class Cloud(str, Enum):
    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"
    MULTI = "multi"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FulfillerType(str, Enum):
    """Who/what fulfills a task. v1 implements human + automation; agent is reserved."""

    HUMAN = "human"
    AUTOMATION = "automation"
    AGENT = "agent"  # the thesis — deliberately unimplemented in v1


class BlueprintAvailability(str, Enum):
    """Capability flag. Absent capabilities are shown as absent, never silently faked."""

    AVAILABLE = "available"
    PREVIEW = "preview"
    DRY_RUN_ONLY = "dry_run_only"


class JobState(str, Enum):
    """The provisioning state machine. One path serves apply AND destroy."""

    QUEUED = "queued"
    PLANNING = "planning"
    AWAITING_GATE = "awaiting_gate"
    APPLYING = "applying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"
    DESTROYING = "destroying"
    DESTROYED = "destroyed"


class GateType(str, Enum):
    APPROVAL = "approval"
    BUDGET = "budget"


class GateResult(str, Enum):
    """Fail-closed: PENDING and anything ambiguous must NOT be treated as PASS."""

    PENDING = "pending"
    PASS = "pass"
    FAIL = "fail"
