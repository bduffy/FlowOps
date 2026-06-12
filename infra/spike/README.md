# Week-0 Spike — Dual-Cloud Actuation Foundation

> **Throwaway spike. Not production code.** This exists to answer one question before
> any FlowOps code is written: *can we provision and tear down an isolated sandbox
> safely, on both GCP and AWS, and detect orphaned resources when state is lost?*
> Tracks GitHub issue **#1** (and informs **#2**, OIDC + split identities, SR4).

## Why this is the first thing we build

Everything in FlowOps is downstream of the actuator working safely. The two scariest
problems live here: **credential isolation** and **safe teardown / orphan recovery**.
If we cannot make these safe and fast, nothing else matters. So we prove it in a
throwaway harness first, with real clouds, before committing the architecture.

## What "pass" looks like

For **each** cloud, the harness must demonstrate:

1. **Isolated provisioning** — assume a scoped role / create an isolated context and
   provision a minimal sandbox resource. No long-lived static keys.
2. **Clean apply** — `tofu apply` succeeds and the resource exists.
3. **Clean destroy** — `tofu destroy` removes everything; the context is empty after.
4. **Failed-apply accounting** — a deliberately-failed apply leaves a partial resource;
   we can see what was created.
5. **Orphan detection independent of tofu state** — the hard one. A resource that exists
   in the cloud but is **absent from tofu state** (simulating lost/corrupt state) is
   still found by listing cloud resources by run-tag and diffing against state.

Record timings and friction in `RESULTS.md`. The output is a **decision**: which cloud
is the first-class target for FlowOps v1 (GCP project-per-sandbox vs AWS
account-per-sandbox), based on which factory is demonstrably safe and fast.

## Prerequisites

You run this with **your own** cloud credentials — the harness never stores any.

- [OpenTofu](https://opentofu.org) >= 1.6 (`tofu`)
- **GCP:** `gcloud` authenticated; an Org or Folder ID + a Billing Account ID (for
  project-per-sandbox). Roles: `resourcemanager.projectCreator`,
  `billing.user`, `storage.admin`.
- **AWS:** `aws` CLI authenticated; an existing **sandbox account** and a role to assume
  into it (the spike uses role-assumption, not account vending — see "Real vending" below).

## Run

```bash
cd infra/spike

# one cloud at a time
./run.sh gcp     # uses gcp/  (set TF_VAR_org_id, TF_VAR_billing_account)
./run.sh aws     # uses aws/  (set TF_VAR_assume_role_arn)

# or both, sequentially
./run.sh all
```

`run.sh` walks all five phases above and prints a per-cloud PASS/FAIL summary. It tags
every resource with `flowops-spike-run=<run-id>` so orphan detection is reliable.

## Safety

- Provisions **real, billable** resources (tiny: one storage bucket). The harness
  destroys them; if it dies mid-run, use `detect_orphans.sh` then clean up by hand.
- Everything is tagged/labeled `flowops-spike-run=<run-id>` for easy cleanup.
- No credentials are written to disk. `*.tfstate`, `*.tfvars`, and `.terraform/` are
  gitignored.
- This is **role-assumption / project-creation only** — it does not vend AWS accounts.

## Real vending (the production target — out of spike scope, noted for #1/#2)

Production FlowOps vends a **whole account/project per sandbox** and **deletes it** to
tear down (orphan-resistant). The spike proves the *inner* loop (provision/destroy/detect)
cheaply; the *outer* loop (account vending via AWS Organizations / GCP project creation
+ OIDC trust bootstrap, SR4) is sized here and built in issues #1/#2 proper. GCP project
creation is included (it is ~one API call); AWS account creation is documented but not
run (slow, quota-limited).

## Files

```
infra/spike/
  run.sh               # orchestrates the 5 phases per cloud, prints PASS/FAIL
  RESULTS.md           # fill this in — the cloud-choice decision record
  gcp/
    main.tf            # project-per-sandbox (optional) + a sandbox GCS bucket
    variables.tf
    detect_orphans.sh  # list buckets by run-label, diff vs `tofu state list`
  aws/
    main.tf            # assume-role into sandbox account + a sandbox S3 bucket
    variables.tf
    detect_orphans.sh  # list buckets by run-tag, diff vs `tofu state list`
```
