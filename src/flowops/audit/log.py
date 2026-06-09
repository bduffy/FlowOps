"""Append-only audit log. In-memory for the scaffold; durable + tamper-evident in #14.

Append-only is enforced here by exposing no mutate/delete; events are frozen dataclasses.
SR3 (hash-chain / WORM) will make tampering *detectable* once persisted — an in-memory
list is not tamper-proof, only tamper-discouraging, which is why #14 exists.
"""

from __future__ import annotations

from collections.abc import Iterator

from ..models.domain import AuditEvent


class AuditLog:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self._events.append(event)

    def __iter__(self) -> Iterator[AuditEvent]:
        return iter(tuple(self._events))  # copy — callers cannot mutate the log

    def __len__(self) -> int:
        return len(self._events)

    def for_request(self, request_id: str) -> list[AuditEvent]:
        return [e for e in self._events if e.request_id == request_id]
