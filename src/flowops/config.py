"""Execution profile + actuator selection.

`FLOWOPS_PROFILE=dev` (default) -> DummyActuator, advisory budget, zero cloud creds.
`FLOWOPS_PROFILE=cloud` -> RealActuator (stub until #8). Everything above the actuator
is identical across profiles (arch §4.7).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .actuators.base import Actuator
from .actuators.dummy import DummyActuator
from .models.enums import Profile

# Local-dev convenience only: NEVER a valid production fallback (see load_settings).
_DEFAULT_DATABASE_URL = "postgresql://flowops:flowops@localhost:5432/flowops"


@dataclass(frozen=True)
class Settings:
    profile: Profile
    region: str
    database_url: str = _DEFAULT_DATABASE_URL
    # Tofu applies are multi-minute; a lease that outlives the slowest apply means
    # reconciliation only ever sees genuinely dead workers, not slow ones.
    lease_ttl_seconds: int = 900

    @property
    def is_dev(self) -> bool:
        return self.profile is Profile.DEV


def load_settings() -> Settings:
    raw = os.environ.get("FLOWOPS_PROFILE", Profile.DEV.value).lower()
    try:
        profile = Profile(raw)
    except ValueError:
        profile = Profile.DEV  # unknown profile -> safest default
    database_url = os.environ.get("FLOWOPS_DATABASE_URL")
    if database_url is None:
        # Fail closed outside dev: silently starting a cloud control plane on
        # default localhost credentials would violate SR5 (no default creds).
        if profile is not Profile.DEV:
            raise RuntimeError(
                "FLOWOPS_DATABASE_URL must be set explicitly outside the dev profile"
            )
        database_url = _DEFAULT_DATABASE_URL
    return Settings(
        profile=profile,
        region=os.environ.get("FLOWOPS_REGION", "us-east-1"),
        database_url=database_url,
        lease_ttl_seconds=int(os.environ.get("FLOWOPS_LEASE_TTL_SECONDS", "900")),
    )


def get_actuator(settings: Settings) -> Actuator:
    if settings.is_dev:
        return DummyActuator()
    # Imported lazily so the dev profile never depends on cloud code paths.
    from .actuators.real import RealActuator

    return RealActuator()
