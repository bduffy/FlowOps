# VantageWorth (FinCalc2) — CLAUDE.md

Financial-planning destination: narrative education + calculator web app for people navigating inherited IRAs and windfalls. **Read `DESIGN.md` before any visual/UI decision — it is authoritative; flag (don't silently change) anything that deviates.**

## Stack & environment
- **Stack:** Astro 5 + Preact islands + Tailwind v4; Cloudflare Workers + Pages.
- **Default branch:** `trunk` (CI and deploy run on push to `trunk`).
- **Package manager:** `pnpm`.

## Commands
```bash
pnpm build              # production build        (verify exact script)
pnpm test               # vitest                   (verify exact script)
pnpm a11y:contrast      # WCAG AA token gate — must pass
bash scripts/smoke-test.sh   # post-deploy smoke tests (also runs in GHA)
bash scripts/deploy.sh       # manual deploy fallback (emergencies/local)
gh issue create|edit|close   # all task operations
khufu "..."             # local LLM (see Multi-model lanes)
```

## Repo map
- `src/pages/` — Astro routes
- `src/components/ui/` — shared UI components (see list below)
- `src/hooks/` — shared hooks (charts, animation, analytics)
- `src/lib/` — shared logic + types (anything imported by both client and Worker lives here)
- `src/workers/` — **Worker-only IP**; never imported by `components/**` or `hooks/**`
- `src/__tests__/` — tests, incl. `ip-boundary.test.ts` (enforces the rule above)
- `scripts/` — deploy/smoke; `tasks/archive/` — historical TODOs

## Working agreement
- **Plan first:** enter plan mode for any task ≥3 steps or with architectural decisions; write the spec, get approval, then build. If it goes sideways, stop and re-plan — don't push through.
- **Subagents liberally:** offload research/exploration/parallel analysis, one task per subagent, to keep the main context clean.
- **Verify before done:** never mark complete without proving it works (tests, logs, before/after). Ask "would a staff engineer approve this?"
- **Simplicity + root causes:** smallest change that solves it; no temporary patches. Pause on non-trivial work to ask "is there a more elegant way?" — skip that for obvious fixes.
- **Autonomous bug fixing:** given a bug/failing CI, investigate from logs and tests and fix it; don't ask for hand-holding.
- **Learn from corrections:** after any user correction, persist the pattern via `/learn` (and auto-memory) so it doesn't recur.
- **Skill-first:** if a request matches a GStack skill, invoke it as the FIRST action — the skill's workflow beats an ad-hoc answer.

## GStack skill routing
Full GStack catalog is available; these are the ones in regular rotation here. Match the request, invoke the skill first.

**Plan:** `/office-hours` (is this worth building / reframe) · `/plan-ceo-review` (product/scope) · `/plan-eng-review` (architecture, edge cases, tests) · `/plan-design-review` (rate design dims 0–10, AI-slop check) · `/autoplan` (CEO→design→eng in one pass) · `/spec` (vague intent → executable spec, Codex-gated)
**Build & review:** `/review` (bugs that pass CI but break prod) · `/investigate` (root-cause debugging; no fix without investigation) · `/qa` (test+fix+regression) / `/qa-only` (report only) · `/design-review` (visual audit + fixes, screenshots) · `/design-consultation` (build/extend the design system) · `/cso` (OWASP+STRIDE deep security)
**Ship & monitor:** `/ship` (tests→push→PR) → `/land-and-deploy` (merge→CI→verify prod) · `/canary` (post-deploy watch) · `/benchmark` (Core Web Vitals)
**Docs & browser:** `/document-release` / `/document-generate` (Diataxis) · `/browse` for ALL web browsing (never `mcp__claude-in-chrome__*`) · `/retro`, `/learn` (memory)

**Custom command — `/gemini-audit`:** lightweight diff security pass —
`git diff trunk --name-only | xargs cat | gemini -p "Review these changed files for security vulnerabilities and output a summary"`, then format the result. Use `/cso` for a full threat model.

## Task management
- **GitHub Issues are the single source of truth.** Epics use child-issue checklists (`- [ ] #15 — …`).
- Labels: `P1`/`P2`/`P3`, `feature`, `infrastructure`, `design`, `phase-4`, `backlog`. Namespace VantageRisk work with a `vantagerisk` label/epic prefix so it doesn't collide with project `phase-N` numbering.

## CI/CD
- **CI** (`.github/workflows/ci.yml`): build + test on every PR and push to `trunk`.
- **Deploy** (`.github/workflows/deploy.yml`) on push to `trunk`: test → Calculator Worker → Market Worker → Pages → smoke tests.
- **No GitHub branch protection** (needs Pro for private repos — Issue #20, won't-do). Protection comes from `/ship` and `/land-and-deploy` gating merges on CI.
- **Secrets:** `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` in the GitHub `production` environment. Never put secrets in CLAUDE.md or code.
- Heuristic: if a rule violation would block a CI merge, enforce it in CI — not just here.

## Conventions
- **IP boundary (enforced by `ip-boundary.test.ts`):** nothing under `src/components/**` or `src/hooks/**` may import `src/workers/**`. Shared types/logic go in `src/lib/`. Worker-only IP (e.g. `src/workers/brandResidualCurves.ts`) stays in `workers/`.
- **Charts:** use `src/hooks/useChartJs.ts`, never a raw `new Chart()` — it handles StrictMode double-invoke and unmount cleanup.
- **Vehicle TCO:** `src/lib/brands.ts` `BRAND_CODES` is a stable public API (codes embedded in shared URLs). Add freely; never rename/remove without a URL-migration plan. Locked by a regression test.
- **Analytics:** stage events via `stagePendingEvent`, flush on `visibilitychange` via `installVisibilityFlushHandler` (so the final event survives tab close).
- **Accessibility:** `pnpm a11y:contrast` must pass; 44px touch targets; ARIA landmarks; keyboard nav; result tables horizontal-scroll on mobile; respect `prefers-reduced-motion`.

## Shared UI components (`src/components/ui/`)
- `AccordionSection` — collapsible sections (CSS-grid transition, `inert` when collapsed)
- `AnimatedNumber` (+ `src/hooks/useAnimatedNumber.ts`) — animated currency, respects reduced-motion
- `BracketWaterfall` — stacked bar of income filling tax brackets
- `PrefillBanner` — dismissible pathway pre-fill banner (sessionStorage dismiss)
- `PrintButton` — `window.print()`, hidden via `no-print`; pairs with the `@media print` block in `src/styles/global.css`

## Known footguns
- **Guided tours must be wired into the calculator, not just built — missed twice (IRA, Retirement).** The tour component alone does nothing. Required: import it; `useState` for `showTour`/`tourDismissed` (localStorage); `handleTourComplete` mapping tour data → form setters; `dismissTour`; plus 3 JSX elements (entry-point CTA, persistent "Guided Setup" re-entry, the overlay). Reference: `InheritedIraOptimizer.tsx`. *(Detailed checklist → consider a nested `src/components/tour/CLAUDE.md` so it loads only when working on tours.)*

## Multi-model lanes
Claude Code is the Driver; other models are used by cognitive lane. For parallel work, give each agent its own `git worktree`/branch so they don't stomp each other; cross-model handoffs must be self-describing (typed interface + tests + a short spec comment).
- **Claude Code (Driver):** scaffolding, integration, repo-wide coherence, convention adherence. Uses subagents for in-repo research.
- **`khufu` local LLMs (privacy + second opinion):** anything touching real financial data stays here (no cloud egress). Validate architecture / review code before writing to disk.
  - `khufu "…"` → qwen3:14b (reasoning, default) · `khufu qwen2.5-coder:14b "…"` (coding) · `khufu devstral "…"` (agentic 2nd opinion) · `khufu phi4 "…"` (fast analysis)
- **Gemini:** via `/gemini-audit`, `/cso`, the design skills, and `/retro global`.
- **Codex CLI** *(new — evaluating):* isolated, correctness-critical algorithms and bake-off comparisons. Native hooks: `/spec`'s Codex quality gate, `/pair-agent` (shares the browser session), `/retro global`.
- **Antigravity** *(new — evaluating):* separate Gemini-based IDE for long-context research/exploration; bring findings back as GitHub issues or markdown (no native GStack hook).
