"""Actuators — the only abstraction in v1. plan/apply/destroy/status.

Two implementations: DummyActuator (dev, test double, capability placeholder) and
RealActuator (cloud, runs OpenTofu in a container job). Gates and fulfiller_type stay
concrete — no plugin registry until a real second instance forces it.
"""

from .base import Actuator, Intent, Preview
from .dummy import DummyActuator

__all__ = ["Actuator", "Intent", "Preview", "DummyActuator"]
