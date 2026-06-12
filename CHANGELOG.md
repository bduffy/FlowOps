# Changelog

All notable changes to FlowOps are documented here.
Versions follow `MAJOR.MINOR.PATCH.MICRO`.

## [0.1.0.0] - 2026-06-12

### Added
- Durable jobs table: a sandbox request now survives crashes and restarts. The task row in Postgres is the state machine — every transition is a guarded update that fails loud on conflict instead of silently overwriting.
- Idempotency keys on request creation: retrying a `POST /api/requests` with the same `Idempotency-Key` returns the existing request (200) instead of provisioning twice; the same key with a different body is rejected (409). Keys are scoped per requester.
- Crash reconciliation: a `reconcile` sweep (and `python -m flowops.jobs.reconcile`) repairs jobs whose worker died mid-apply or mid-destroy, completing them from recorded evidence or flagging them `orphan_suspected` — never blindly re-applying.
- Per-sandbox locking via job leases: only one apply/destroy can run against a sandbox at a time; a second attempt gets a 409.
- Gate decisions are write-once: a concurrent losing decision can no longer overwrite the recorded approval — governance evidence always matches what actually happened.
- Versioned SQL migrations that run automatically at API startup (`python -m flowops.db.migrate` for ops).
- `docker compose up` now brings up the full durable loop (API + Postgres) with zero cloud credentials.

### Changed
- Outside the dev profile, the control plane refuses to start without an explicit `FLOWOPS_DATABASE_URL` (no default credentials, ever).
- Destroy fails closed on a missing or unparseable handle, and blueprint module refs are pinned at submit — later blueprint edits never change what an existing sandbox runs or destroys.
- Audit entries for provisioning record output names only, never output values.

### Fixed
- Docker image build (the image never copied `README.md`, so `docker compose up --build` failed).
