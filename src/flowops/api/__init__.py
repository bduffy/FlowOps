"""FastAPI adapter over SandboxService. A thin transport layer — no business logic.

The whole governed-actuation loop lives in `flowops.services`; this just exposes it
over HTTP. Persistence, async jobs, and auth are layered on later (#5, #8, auth).
"""
