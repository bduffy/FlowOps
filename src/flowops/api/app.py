"""FastAPI app. Thin adapter over SandboxService.

Run (dev mode, zero cloud creds):
    FLOWOPS_PROFILE=dev uvicorn flowops.api.app:app --reload

NOTE: auth is NOT wired yet. `actor`/`role` come from the request body for the scaffold;
real authn/authz (JWT + RBAC, no default creds — SR5) lands with the control-plane work.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ..config import load_settings
from ..jobs.state_machine import InvalidTransition
from ..services import SandboxService

settings = load_settings()
service = SandboxService(settings)  # in-memory; one process. Replaced by DB-backed in #5.

app = FastAPI(title="FlowOps", version="0.0.0")


class SubmitBody(BaseModel):
    blueprint_key: str = "dev-sandbox"
    title: str
    requester: str
    owner: str


class DecisionBody(BaseModel):
    decision: str  # "approve" | "deny"
    role: str
    actor: str


class TeardownBody(BaseModel):
    actor: str
    actor_role: str


def _view(request_id: str) -> dict:
    req = service.store.get_request(request_id)
    if req is None or req.task is None:
        raise HTTPException(404, "request not found")
    t = req.task
    return {
        "id": req.id,
        "title": req.title,
        "blueprint": req.blueprint_key,
        "state": t.state.value,
        "gates": [asdict(g) for g in t.gates],
        "outputs": t.handle.outputs if t.handle else {},
        "audit": [asdict(e) for e in service.audit.for_request(req.id)],
    }


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/api/profile")
def profile() -> dict:
    # The UI badges this: dev mode is always visibly dev.
    return {"profile": settings.profile.value, "actuator": getattr(service.actuator, "name", "?")}


@app.get("/api/blueprints")
def blueprints() -> list[dict]:
    return [asdict(b) for b in service.store.blueprints.values()]


@app.post("/api/requests", status_code=201)
def submit(body: SubmitBody) -> dict:
    try:
        req = service.submit(body.blueprint_key, body.title, body.requester, body.owner)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    return _view(req.id)


@app.get("/api/requests/{request_id}")
def get_request(request_id: str) -> dict:
    return _view(request_id)


@app.post("/api/requests/{request_id}/decision")
def decide(request_id: str, body: DecisionBody) -> dict:
    try:
        service.decide(request_id, body.decision, body.role, body.actor)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    except (ValueError, InvalidTransition) as e:
        raise HTTPException(409, str(e)) from e
    return _view(request_id)


@app.post("/api/requests/{request_id}/teardown")
def teardown(request_id: str, body: TeardownBody) -> dict:
    try:
        service.teardown(request_id, body.actor, body.actor_role)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    except (ValueError, InvalidTransition) as e:
        raise HTTPException(409, str(e)) from e
    return _view(request_id)
