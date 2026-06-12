# FlowOps — CLAUDE.md

Open-source **governed self-service provisioning platform** — "the governed actuation layer." A request passes a gate (approval + cloud-enforced budget) and gets *built* (real infra via OpenTofu), then auto-torn-down on a TTL, every step audited. Keeps ITSM's `request → task → action` model; makes a task's fulfiller a human, an automation, or an AI agent — governance constant no matter who does the work. **Status: pre-implementation** (architecture/design/strategy reviews complete). Source of truth for the plan: `docs/ARCHITECTURE_AND_DESIGN.md`. **Read `DESIGN.md` before any visual/UI decision — it is authoritative; flag (don't silently change) anything that deviates.** (`DESIGN.md` is task DS1, not yet written; until it exists, the NYS Design System + the approved mockup at `docs/assets/sandbox-lifecycle-approved.png` are authoritative.)

## Stack & environment
- **Control plane:** Python + FastAPI, PostgreSQL.
- **Execution:** durable queue (SQS / Pub-Sub) → serverless container job (AWS Fargate / GCP Cloud Run Job) running **OpenTofu** (not Terraform).
- **Frontend:** React, themed via NYS Design System tokens (`--nys-color-*`), WCAG 2.1 AA.
- **Default branch:** `trunk` (CI/deploy run on push to `trunk`).
- **Package managers:** `uv` (Python) · `npm` (frontend). *(Verify once scaffolded — code not yet imported.)*

## Commands *(planned — not yet wired; verify exact scripts when scaffolded)*
```bash
uv run pytest                # control-plane tests (fail-path suite is the point)
uv run uvicorn app.main:app --reload   # run the API locally
npm --prefix frontend run dev          # run the board
npm --prefix frontend run a11y         # WCAG AA token/contrast gate — must pass
FLOWOPS_PROFILE=dev docker compose up   # full loop locally, zero cloud creds (dev mode)
tofu fmt -recursive && tofu validate   # blueprint modules
gh issue create|edit|close   # all task operations
codex exec "..."             # independent second opinion (see Multi-model lanes)
```

## Repo map *(current = docs only; rest is the planned layout from the design doc)*
- `docs/` — `ARCHITECTURE_AND_DESIGN.md` (plan SoT), `assets/` (approved mockups), `PoC_UserGuide.md`
- `api/` — FastAPI control plane: intake, board, gates *(planned)*
- `actuators/` — `Actuator` interface + `RealActuator` (container job) + `DummyActuator` (dry-run/test double) *(planned)*
- `gates/` — approval + cloud-enforced budget gates *(planned)*
- `jobs/` — job state machine + queue worker + TTL teardown worker *(planned)*
- `audit/` — append-only event stream *(planned)*
- `infra/` — account/project vending, budget/SCP, OIDC trust; curated OpenTofu blueprint modules *(planned)*
- `frontend/` — React board + sandbox lifecycle view *(planned)*
- `models/` — shared domain model (`request → task → action`) *(planned)*

## Working agreement
- **Plan first:** enter plan mode for any task ≥3 steps or with architectural decisions; write the spec, get approval, then build. If it goes sideways, stop and re-plan — don't push through.
- **Subagents liberally:** offload research/exploration/parallel analysis, one task per subagent, to keep the main context clean.
- **Verify before done:** never mark complete without proving it works (tests, logs, before/after). Ask "would a staff engineer approve this?"
- **Simplicity + root causes:** smallest change that solves it; no temporary patches. Pause on non-trivial work to ask "is there a more elegant way?" — skip that for obvious fixes.
- **Autonomous bug fixing:** given a bug/failing CI, investigate from logs and tests and fix it; don't ask for hand-holding.
- **Learn from corrections:** after any user correction, persist the pattern via `/learn` (and auto-memory) so it doesn't recur.
- **Skill-first:** if a request matches a GStack skill, invoke it as the FIRST action — the skill's workflow beats an ad-hoc answer.

## Skill routing
Full GStack catalog is available; these are the ones in regular rotation. Match the request, invoke the skill first.

**Plan:** `/office-hours` (is this worth building / reframe) · `/plan-ceo-review` (product/scope/strategy) · `/plan-eng-review` (architecture, edge cases, tests) · `/plan-design-review` (rate design dims 0–10, AI-slop check, mockups) · `/autoplan` (CEO→design→eng in one pass) · `/spec` (vague intent → executable spec)
**Build & review:** `/review` (bugs that pass CI but break prod) · `/investigate` (root-cause debugging; no fix without investigation) · `/qa` (test+fix+regression) / `/qa-only` (report only) · `/design-review` (visual audit + fixes) · `/design-consultation` / `/design-shotgun` (build/explore the design system) · `/cso` (OWASP+STRIDE security — important for a tool that holds cloud credentials)
**Ship & monitor:** `/ship` (tests→push→PR) → `/land-and-deploy` (merge→CI→verify) · `/canary` (post-deploy watch)
**Docs & browser:** `/document-release` / `/document-generate` · `/make-pdf` · `/browse` for ALL web browsing · `/retro`, `/learn` (memory)

**Custom command — `/gemini-audit`:** lightweight diff security pass — `git diff trunk --name-only | xargs cat | gemini -p "Review these changed files for security vulnerabilities and output a summary"`, then format the result. Use `/cso` for a full threat model.

## Task management
- **GitHub Issues are the single source of truth** (live at `bduffy/FlowOps` — backlog migrated 2026-06-09; see `TODOS.md` for the epic map). Epics use child-issue checklists (`- [ ] #15 — …`).
- Labels: `P1`/`P2`/`P3`, `feature`, `infrastructure`, `design`, `a11y`, `security`, `backlog`.
- Build tasks already enumerated in `docs/ARCHITECTURE_AND_DESIGN.md` and the gstack task JSONLs (`~/.gstack/projects/EasyITSM/tasks-*.jsonl`). **Start with the week-0 spike (T2).**

## CI/CD *(planned)*
- **CI** (`.github/workflows/ci.yml`): build + control-plane tests + frontend a11y gate + `tofu validate` on every PR and push to `trunk`.
- **Release** (`.github/workflows/release.yml`) on tag: build + publish container images, cut a GitHub Release. Hosted/managed offering deferred.
- **Secrets:** container-registry creds in the GitHub `production` environment. **Cloud provisioning credentials never live in CI** — the runner assumes a scoped role via OIDC at provision time. Never put secrets in CLAUDE.md or code.
- Heuristic: if a rule violation would block a CI merge, enforce it in CI — not just here.

## Conventions (FlowOps-specific — these are load-bearing)
- **Fail closed (global invariant).** Every gate and the teardown guard defaults to **DENY** on ambiguity: missing cost preview → no apply; unknown role → no approve; unparseable handle → no destroy. A gate that can fail open is a critical defect.
- **Cloud-enforced budget, not declared caps.** The budget gate sets a real AWS Budget + SCP / GCP budget + quota + service allowlist on the sandbox account at provision time. A user "declaring" a cap is governance theater — never ship it as the control. (See `[[cloud-enforced-budget]]` memory.)
- **Account-per-sandbox isolation.** Each sandbox = its own AWS account / GCP project; runner assumes a scoped role via **OIDC, no static keys**. **Teardown = delete the account/project.** OpenTofu **state lives in the control-plane account**, encrypted + secret-redacted — *never* in the sandbox account.
- **The `Actuator` interface is the only abstraction in v1.** `plan/apply/destroy/status`, two impls (Real + Dummy). Gates and `fulfiller_type` stay concrete — **do not** add a plugin registry / Gate or Fulfiller interface until a real second instance forces it.
- **Keep `request → task → action` thin.** No ITSM ceremony (no SLAs, categories, queues) until something real needs it. The task *is* the provisioning job; the action *is* the actuator call.
- **Jobs are durable.** Apply and destroy share one job path; require idempotency keys, per-sandbox locks, job leases, and "apply-succeeded-but-callback-failed" reconciliation. `status()` reads the jobs table — never a live cloud poll.
- **Audit is append-only** with correlation IDs, actor provenance, immutable job inputs, and redaction. Not just another table.
- **Module supply-chain:** curated OpenTofu modules are pinned by ref, with a provider lockfile + checksums and a review policy. A "curated" module is still supply chain.
- **Accessibility (WCAG 2.1 AA / Section 508) is mandatory** (gov context): visible focus rings (`#004dd1`), ≥4.5:1 body contrast, 44px touch targets, keyboard nav, ARIA landmarks. **Status is never conveyed by color alone** — pair color + icon + text.

## Design system
- Conform to the **NYS Design System** (USWDS-derived, designsystem.ny.gov). Build all UI on `--nys-color-*` CSS custom properties so it is themeable.
- Tokens: `--nys-color-theme` `#154973` (primary/active) · `--nys-color-link`/`--nys-color-focus` `#004dd1` · `--nys-color-success` `#1e752e` · `--nys-color-text` `#1b1b1b` · `--nys-color-surface` `#ffffff` · Environment theme `#233f2b`.
- The PoC's orange admin accent is **superseded by the NYS blue theme.** Typography: an accessible gov sans (Public Sans family), never `system-ui`.
- Approved reference for the sandbox lifecycle view: `docs/assets/sandbox-lifecycle-approved.png`.

## Known footguns
- **Auto-teardown deletes real infrastructure.** It must never run without its guardrails: dry-run, grace period, owner notification, and a "never-destroy" classification. A teardown worker missing any of these can delete a colleague's data — treat the guardrails as v1-blocking, not polish.
- **A failed `apply` leaves orphaned cloud spend with no clean handle.** Every apply path needs orphan-detection / state reconciliation, not just happy-path destroy. (Account-per-sandbox makes the recovery "delete the account" — but the detection still has to fire.)
- **Account/project vending is slow and quota-limited.** It can silently cap throughput — raise AWS account quotas / confirm GCP project quotas early, and `log()` any cap rather than letting it look like "covered."
- **Secrets land in OpenTofu state.** State is encrypted, secrets redacted, and access isolated to the control plane — a control-plane compromise otherwise exposes every sandbox's state.

## Multi-model lanes
Claude Code is the Driver; other models are used by cognitive lane. For parallel work, give each agent its own `git worktree`/branch; cross-model handoffs must be self-describing (typed interface + tests + a short spec comment).
- **Claude Code (Driver):** scaffolding, integration, repo-wide coherence, convention adherence. Uses subagents for in-repo research.
- **Codex CLI:** independent second opinion on plans and correctness-critical code (the job state machine, the gate/fail-closed logic, the teardown guardrails). Native hooks: the outside-voice step in `/plan-eng-review` and `/plan-ceo-review`, `/spec`'s quality gate, `/pair-agent`.
- **Gemini:** via `/gemini-audit` (diff security pass), `/cso`, and the design skills.
- **Sensitivity note (gov context):** treat cloud credentials, account/project identifiers, and audit data as sensitive. Keep them out of prompts to external models; review any actuator/credential code with a local or isolated model before it touches disk.
