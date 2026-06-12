# Week-0 Spike — Results & Decision Record

Fill this in after running `./run.sh`. The output of the spike is a **decision**: which
cloud is FlowOps v1's first-class actuation target. Attach this to issue #1.

Run date: _6/11/2026__   ·   Operator: __bduffy___   ·   OpenTofu version: ____________

## Phase results

AWS run: 2026-06-11 · run_id `r226635` · **4/4 PASS** (inner loop, via role-assumption).

| Phase | GCP | AWS | Notes |
|------|-----|-----|-------|
| 1. Isolated provisioning (role/project) | ⬜ pass / fail | ✅ pass | AWS via assume-role into an existing sandbox account |
| 2. Clean apply | ⬜ (___s) | ✅ (6s) | bucket `flowops-sbx-r226635-6d2432` |
| 3. Clean destroy (state empty after) | ⬜ (___s) | ✅ (7s) | state empty after |
| 4. Failed-apply accounting | ⬜ | ✅ | injected failure left a partial resource; seen + cleaned |
| 5. Orphan detection (state lost) | ⬜ | ✅ | `state rm` orphan found by tag + reclaimed — state-independent ✓ |

## Isolation model — friction & latency

| Question | GCP (project-per-sandbox) | AWS (account/role) |
|---|---|---|
| Time to create the isolated context | | n/a — used an *existing* account via assume-role (vending not tested; see caveat) |
| Quota ceiling hit? | | No (no account vending in this run) |
| Setup ceremony (OU/SCP/folder/billing/trust) | | Minimal — assume-role + ExternalId only. Full Organizations vending NOT tested (→ #2) |
| OIDC / scoped-role wiring effort (SR4) | | assume-role demonstrated; OIDC trust bootstrap deferred to #2 |
| Teardown = delete context? clean? | | Resource-level destroy clean; **account-deletion teardown not tested** (no vending) |

> **AWS caveat:** this run proved the *inner* loop (provision / destroy / failed-apply /
> orphan-detect) via role-assumption into an existing account. It did NOT test the
> *outer* loop — account vending (Organizations), the OIDC trust bootstrap, or
> cloud-enforced budget/SCP. Those are the heavier SR4 parts tracked in issue #2.

## What broke / surprised us

- AWS: nothing broke. apply 6s / destroy 7s. Orphan detection found a state-divergent
  resource purely by cloud tag — the state-independent safety net works.
-

## DECISION

**First-class cloud for FlowOps v1:** ⬜ GCP   ⬜ AWS

**Because:**

**Implications for the architecture / open issues (#1, #2):**

- Credential isolation approach to standardize on:
- OIDC trust shape (SR4):
- Orphan-detection approach that worked:
- Anything to add to the design doc / new issues:
