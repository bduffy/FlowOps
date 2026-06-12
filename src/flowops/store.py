"""In-memory store. Replaced by Postgres (the durable jobs table) in issue #5.

Deliberately tiny: enough to run the full loop in dev mode without a database.
"""

from __future__ import annotations

from .models.domain import Blueprint, WorkRequest
from .models.enums import BlueprintAvailability, Cloud


class InMemoryStore:
    def __init__(self) -> None:
        self.blueprints: dict[str, Blueprint] = {}
        self.requests: dict[str, WorkRequest] = {}
        self._seed_dev_blueprint()

    def _seed_dev_blueprint(self) -> None:
        # The v1 wedge: a dev sandbox. Admin-curated; module ref is pinned (SR1).
        bp = Blueprint(
            key="dev-sandbox",
            name="Dev sandbox",
            cloud=Cloud.AWS,
            tofu_module_ref="git::https://github.com/bduffy/flowops-blueprints//dev-sandbox?ref=v0.0.0",
            budget_cap_usd=50.0,
            ttl_hours=24,
            allowed_roles=("admin", "worker"),
            availability=BlueprintAvailability.AVAILABLE,
        )
        self.blueprints[bp.key] = bp

    def add_request(self, request: WorkRequest) -> None:
        self.requests[request.id] = request

    def get_request(self, request_id: str) -> WorkRequest | None:
        return self.requests.get(request_id)
