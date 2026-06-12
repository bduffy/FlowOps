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


@dataclass(frozen=True)
class Settings:
    profile: Profile
    region: str

    @property
    def is_dev(self) -> bool:
        return self.profile is Profile.DEV


def load_settings() -> Settings:
    raw = os.environ.get("FLOWOPS_PROFILE", Profile.DEV.value).lower()
    try:
        profile = Profile(raw)
    except ValueError:
        profile = Profile.DEV  # unknown profile -> safest default
    return Settings(profile=profile, region=os.environ.get("FLOWOPS_REGION", "us-east-1"))


def get_actuator(settings: Settings) -> Actuator:
    if settings.is_dev:
        return DummyActuator()
    # Imported lazily so the dev profile never depends on cloud code paths.
    from .actuators.real import RealActuator

    return RealActuator()
