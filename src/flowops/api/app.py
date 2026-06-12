"""FastAPI app. Thin adapter over SandboxService.

Run (dev mode, zero cloud creds — Postgres comes from docker compose):
    docker compose up -d db
    FLOWOPS_PROFILE=dev uvicorn flowops.api.app:app --reload

NOTE: auth is NOT wired yet. `actor`/`role` come from the request body for the scaffold;
real authn/authz (JWT + RBAC, no default creds — SR5) lands with the control-plane work.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel

from ..config import load_settings
from ..db import create_pool
from ..db.migrate import run_migrations
from ..jobs.state_machine import InvalidTransition
from ..services import SandboxService
from ..store import ConflictError, Store


def create_app(service: SandboxService | None = None) -> FastAPI:
    """`service` is injectable for tests; otherwise the lifespan owns the DB:
    migrate -> pool -> seed (dev) -> service."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if service is not None:
            app.state.service = service
            yield
            return
        settings = load_settings()
        run_migrations(settings.database_url)
        pool = create_pool(settings.database_url)
        store = Store(pool)
        if settings.is_dev:
            store.seed_dev_blueprint()
        app.state.service = SandboxService(settings, store=store)
        try:
            yield
        finally:
            pool.close()

    app = FastAPI(title="FlowOps", version="0.0.0", lifespan=lifespan)

    def _svc(request: Request) -> SandboxService:
        return request.app.state.service

    def _view(svc: SandboxService, req) -> dict:
        # Takes the already-hydrated WorkRequest the service returned — no re-fetch.
        if req is None or req.task is None:
            raise HTTPException(404, "request not found")
        t = req.task
        return {
            "id": req.id,
            "title": req.title,
            "blueprint": req.blueprint_key,
            "state": t.state.value,
            "orphan_suspected": t.orphan_suspected,
            "gates": [asdict(g) for g in t.gates],
            "outputs": t.handle.outputs if t.handle else {},
            "audit": [asdict(e) for e in svc.audit.for_request(req.id)],
        }

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    @app.get("/api/profile")
    def profile(request: Request) -> dict:
        svc = _svc(request)
        # The UI badges this: dev mode is always visibly dev.
        return {
            "profile": svc.settings.profile.value,
            "actuator": getattr(svc.actuator, "name", "?"),
        }

    @app.get("/api/blueprints")
    def blueprints(request: Request) -> list[dict]:
        return [asdict(b) for b in _svc(request).store.list_blueprints()]

    @app.post("/api/requests", status_code=201)
    def submit(
        request: Request,
        body: SubmitBody,
        response: Response,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        svc = _svc(request)
        try:
            req, created = svc.submit(
                body.blueprint_key, body.title, body.requester, body.owner,
                idempotency_key=idempotency_key,
            )
        except KeyError as e:
            raise HTTPException(404, _detail(e)) from e
        except (ValueError, InvalidTransition, ConflictError) as e:
            raise HTTPException(409, str(e)) from e
        if not created:
            response.status_code = 200  # replay: same resource, not a new one
        return _view(svc, req)

    @app.get("/api/requests/{request_id}")
    def get_request(request: Request, request_id: str) -> dict:
        svc = _svc(request)
        return _view(svc, svc.store.get_request(request_id))

    @app.post("/api/requests/{request_id}/decision")
    def decide(request: Request, request_id: str, body: DecisionBody) -> dict:
        svc = _svc(request)
        try:
            req = svc.decide(request_id, body.decision, body.role, body.actor)
        except KeyError as e:
            raise HTTPException(404, _detail(e)) from e
        except (ValueError, InvalidTransition, ConflictError) as e:
            raise HTTPException(409, str(e)) from e
        return _view(svc, req)

    @app.post("/api/requests/{request_id}/teardown")
    def teardown(request: Request, request_id: str, body: TeardownBody) -> dict:
        svc = _svc(request)
        try:
            req = svc.teardown(request_id, body.actor, body.actor_role)
        except KeyError as e:
            raise HTTPException(404, _detail(e)) from e
        except PermissionError as e:
            raise HTTPException(403, str(e)) from e
        except (ValueError, InvalidTransition, ConflictError) as e:
            raise HTTPException(409, str(e)) from e
        return _view(svc, req)

    return app


def _detail(e: KeyError) -> str:
    # str(KeyError) wraps the message in repr quotes — unwrap for clean API errors.
    return str(e.args[0]) if e.args else "not found"


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


app = create_app()
