# Week-0 Spike — Results & Decision Record

Fill this in after running `./run.sh`. The output of the spike is a **decision**: which
cloud is FlowOps v1's first-class actuation target. Attach this to issue #1.

Run date: _6/11/2026__   ·   Operator: __bduffy___   ·   OpenTofu version: ____________

## Phase results

AWS run: 2026-06-11 · run_id `r226635` · **4/4 PASS** (inner loop, via role-assumption).
GCP run: 2026-06-11 · run_id `r229954` · **4/4 PASS** (inner loop, existing project `spike-sandbox-499201`).

| Phase | GCP | AWS | Notes |
|------|-----|-----|-------|
| 1. Isolated provisioning (role/project) | ✅ pass | ✅ pass | GCP into an existing project; AWS via assume-role into an existing account |
| 2. Clean apply | ✅ (5s) | ✅ (6s) | GCP slightly faster across runs (4-5s vs 6s) |
| 3. Clean destroy (state empty after) | ✅ (6s) | ✅ (7s) | both empty after |
| 4. Failed-apply accounting | ✅ | ✅ | injected failure left a partial resource; seen + cleaned (both) |
| 5. Orphan detection (state lost) | ✅ | ✅ | state-rm'd resource found by label/tag + reclaimed — state-independent ✓ |

## Isolation model — friction & latency

| Question | GCP (project-per-sandbox) | AWS (account/role) |
|---|---|---|
| Time to create the isolated context | n/a — existing project (vending not timed); **project creation is ~1 API call** | n/a — existing account via assume-role (vending not tested) |
| Quota ceiling hit? | No. Projects scale to thousands | No (no vending). AWS Org accounts have a ~10 soft cap to raise |
| Setup ceremony | **Light** — a project + billing link; no OU/SCP/Control Tower | **Heavy** (for real vending) — Organizations, OUs, SCPs, account factory |
| OIDC / scoped-role wiring (SR4) | Workload Identity Federation; not yet tested (→ #2) | assume-role/OIDC demonstrated; trust bootstrap → #2 |
| Teardown = delete context? clean? | `deletion_policy=DELETE` wired; project-deletion teardown not timed | Resource destroy clean; account-deletion teardown not tested |

> **Caveat (both):** these runs proved the *inner* loop (provision / destroy /
> failed-apply / orphan-detect) against an *existing* context. Neither tested the *outer*
> loop — real account/project **vending**, the **OIDC trust bootstrap**, or
> **cloud-enforced budget/SCP**. Those are the heavier SR4 parts tracked in issue #2.
> The vending comparison below is based on known platform mechanics, not a timed test.

## What broke / surprised us

- AWS: nothing broke. apply 6s / destroy 7s. State-independent orphan detection works.
- GCP: provisioning clean + fast (4-5s), but two harness bugs surfaced real lessons —
  (1) the orphan detector must **fail loud**, never silent-clean, when it can't query the
  cloud; (2) **gcloud CLI auth is separate from OpenTofu's ADC** — apply succeeds on ADC
  while `gcloud storage` has no account. The production reconciler should query via the
  provider SDK (one credential path), not shell out to `gcloud`. Captured for #13.

## DECISION

**First-class cloud for FlowOps v1:** ✅ **GCP**   ⬜ AWS   _(decided 2026-06-11)_

**Because:** the inner loop is a tie (both 4/4; GCP slightly faster), so the call rests on
**vending** — the part that actually differs. GCP **project-per-sandbox is ~1 API call**
and scales to thousands; AWS account-per-sandbox needs Organizations + OUs + SCPs + an
account factory with a ~10-account soft quota. Choosing GCP avoids the "account factory
becomes the product" trap (cross-model tension 2). AWS is not abandoned — the `Actuator`
seam lets it follow as a second cloud later.

**Implications for the architecture / open issues (#1, #2):**

- **Credential isolation:** project-per-sandbox; runner uses **Workload Identity
  Federation (OIDC)**, no static keys. `deletion_policy=DELETE` for orphan-resistant
  teardown.
- **OIDC trust shape (SR4):** WIF with tight subject + audience conditions; **split the
  project-vending identity from the per-sandbox provisioning identity** (#2).
- **Orphan-detection approach that worked:** list cloud resources by label, **scoped to
  the sandbox project**, diff vs `tofu state`; the detector **must fail loud** if it can't
  query (no silent-clean). Production reconciler (#13): query via the provider SDK, not a
  `gcloud` shell-out (the CLI-vs-ADC auth split is an operability footgun).
- **New issues / design-doc updates:** retarget #2 to GCP-first (project vending + WIF);
  carry the fail-loud + SDK-query lessons into #13; AWS becomes a post-v1 "second cloud"
  item (E9).
