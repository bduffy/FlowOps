# Week-0 Spike — Results & Decision Record

Fill this in after running `./run.sh`. The output of the spike is a **decision**: which
cloud is FlowOps v1's first-class actuation target. Attach this to issue #1.

Run date: ____________   ·   Operator: ____________   ·   OpenTofu version: ____________

## Phase results

| Phase | GCP | AWS | Notes |
|------|-----|-----|-------|
| 1. Isolated provisioning (role/project) | ⬜ pass / fail | ⬜ | |
| 2. Clean apply | ⬜ (___s) | ⬜ (___s) | apply wall-clock |
| 3. Clean destroy (state empty after) | ⬜ (___s) | ⬜ (___s) | |
| 4. Failed-apply accounting | ⬜ | ⬜ | partial resource visible? |
| 5. Orphan detection (state lost) | ⬜ | ⬜ | detector named the orphan? |

## Isolation model — friction & latency

| Question | GCP (project-per-sandbox) | AWS (account/role) |
|---|---|---|
| Time to create the isolated context | | |
| Quota ceiling hit? | | |
| Setup ceremony (OU/SCP/folder/billing/trust) | | |
| OIDC / scoped-role wiring effort (SR4) | | |
| Teardown = delete context? clean? | | |

## What broke / surprised us

-

## DECISION

**First-class cloud for FlowOps v1:** ⬜ GCP   ⬜ AWS

**Because:**

**Implications for the architecture / open issues (#1, #2):**

- Credential isolation approach to standardize on:
- OIDC trust shape (SR4):
- Orphan-detection approach that worked:
- Anything to add to the design doc / new issues:
