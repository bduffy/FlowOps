"""Audit — append-only governance event stream.

v1 hardening (correlation IDs, actor provenance, immutable inputs) is here in shape;
tamper-evidence (hash-chaining / WORM mirror, SR3) and durable storage land in #14.
"""

from .log import AuditLog

__all__ = ["AuditLog"]
