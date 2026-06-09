# FlowOps frontend (placeholder)

The React board + sandbox lifecycle view. Not scaffolded yet — tracked in epic **E6**:

- #18 — `DESIGN.md`: NYS Design System token mapping (do this first; it's authoritative)
- #19 — Sandbox lifecycle detail view (build from `docs/assets/sandbox-lifecycle-approved.png`)
- #20 — Interaction states for the 4 new surfaces
- #21 — WCAG 2.1 AA accessibility pass
- #22 — Board card live-status
- #23 — Capability/availability flags

Themed via NYS Design System tokens (`--nys-color-*`); the control-plane API it talks to
is in `src/flowops/api/`. Until this exists, drive the loop via the API directly:

```bash
FLOWOPS_PROFILE=dev uvicorn flowops.api.app:app --reload
curl -s localhost:8000/api/profile
```
