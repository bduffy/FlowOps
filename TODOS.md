# TODOS — FlowOps

Deferred items surfaced during /office-hours and /plan-eng-review (2026-06-08).
Veto/edit freely. P1 items live in the design doc's Implementation Tasks; these are
post-v1 / out-of-scope-for-now.

## Warm pool of pre-vended accounts/projects
- **What:** Keep a small inventory of already-vended, idle sandbox accounts/projects so a request draws from warm stock instead of waiting on vending.
- **Why:** Account/project vending is minutes-long and quota-limited. The "I want it *built*" experience feels instant only if inventory is warm. This is the single biggest lever on perceived speed.
- **Pros:** Near-instant provisioning UX; smooths quota spikes.
- **Cons:** Idle cost; a pool manager to build/refill/reap; complexity v1 doesn't need yet.
- **Context:** Defer until on-demand vending latency actually hurts. On-demand is fine for v1 throughput. Revisit when concurrent demand or demo polish demands it.
- **Depends on:** The account/project vending path (T2) existing first.

## AI sandbox blueprint definition + agent fulfiller
- **What:** Define exactly what an "AI sandbox" provisions (model/API access + budget cap + compute env + agent runtime), then ship it as blueprint #2 (seam proof). Later: implement `fulfiller_type=agent`.
- **Why:** AI sandbox is the timely, "whoa" blueprint and the proof the Actuator seam works with zero engine changes. The agent fulfiller is the project's actual thesis.
- **Pros:** Validates the abstraction; lands the differentiated story.
- **Cons:** Undefined scope today; agent-in-the-loop governance is its own design problem.
- **Context:** v1 deliberately ships dev-sandbox + human/automation fulfillers only, to keep premise #3 honest. This is fast-follow #1.
- **Depends on:** v1 loop working end-to-end against the dev sandbox.

## Blueprint versioning / live-sandbox migration
- **What:** Version blueprints; define what happens to already-provisioned sandboxes when their blueprint changes.
- **Why:** Once a sandbox outlives a single deploy, blueprint drift is a real correctness problem.
- **Pros:** Avoids silent divergence between blueprint and live infra.
- **Cons:** Migration semantics are fiddly; premature before sandboxes are long-lived.
- **Context:** Sandboxes are short-lived (TTL) in v1, so this matters less early. Capture now so it isn't a surprise.
- **Depends on:** Stable blueprint model.

## Broader gates (destroy, TTL-extension, budget-increase, failed-state repair)
- **What:** Gate transitions beyond apply — destroying, extending TTL, raising budget, repairing a failed sandbox, force-cleanup.
- **Why:** v1 only gates the apply transition; Codex correctly noted destroy/extend/repair are also privileged actions.
- **Pros:** Consistent governance across the lifecycle.
- **Cons:** More gate plumbing; not all needed for the first loop.
- **Context:** v1 = apply-gate only. Add as the lifecycle grows.

## Open-core line + positioning — RESOLVED (CEO review 2026-06-08)
Decided. See the design doc's "Strategy Decisions" section.
- **License:** AGPL-3.0 + commercial dual-license. **Requires a CLA from day one.**
- **Open-core line:** generous core (full single-org governed-actuation loop is OSS);
  commercial = multi-tenancy, SSO/SAML/SCIM, advanced policy, hosted runners, audit
  retention/compliance, support.
- **Positioning:** "governed self-service provisioning / the governed actuation layer."
  Sandbox = demo; AI-native ITSM = vision narrative; batteries-included vs Backstage's BYO.
- **Open follow-ups (P1, before first public commit):**
  - Add `LICENSE` (AGPL-3.0) + a `COMMERCIAL.md` describing the commercial option.
  - Set up a CLA (CLA Assistant or DCO+CLA bot) so contributions are dual-licensable.
  - Write a `LICENSING.md` / README section documenting the open-core line so
    contributors aren't surprised.
