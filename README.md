# FlowOps

**The governed actuation layer.** Request infrastructure, pass a gate, and have it
actually *built* — with controls (approval, budget, policy, audit) that never come off.

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-blue.svg)](LICENSE)
[![Status: pre-implementation](https://img.shields.io/badge/status-planning%20complete-orange.svg)](docs/ARCHITECTURE_AND_DESIGN.md)

> **Status: pre-implementation.** The product is fully planned (architecture, design,
> and strategy reviews complete) and the build is starting. The commands below describe
> the target experience. Follow the repo to watch it land. See the full
> [Architecture & Design document](docs/ARCHITECTURE_AND_DESIGN.md).

---

## What FlowOps is

FlowOps is an open-source **governed self-service provisioning platform**. A person (or
an AI agent) requests something — say, a developer sandbox — it passes a policy and
budget gate, and the platform *provisions it for real* and tears it down on a schedule,
with a complete audit trail. The controls are the product.

It lives in the unserved middle between two bad options:

- **ClickOps** — manual, ungoverned, doesn't scale.
- **Full CI/CD pipelines** — overkill for self-service, and they get in the way.

FlowOps is the third path: **self-service with guardrails, and no pipeline to babysit.**

## The thesis: AI-native ITSM

This is not "open-source ServiceNow" and not a prettier ticketing board.

ITSM's *skeleton* — `request → task → action`, cleanly linked — is genuinely good. Its
*flesh* — the human bureaucracy that fulfills every task — is pure toil. ServiceNow won
in 2005 because Remedy made you waste your life on care-and-feeding. In 2026, the toil
worth killing is the *human-in-every-step* fulfillment.

FlowOps keeps the `request → task → action` model and makes a task's **fulfiller** a
human, an automation, or an AI agent — while governance (approval, budget, policy, audit)
stays constant no matter who or what does the work.

## How it works

```
  Request  ──▶  Gate  ──▶  Actuate  ──▶  Run  ──▶  Auto-teardown
 (a sandbox)  (approval +   (OpenTofu    (live      (TTL; delete the
              cloud-        in an        sandbox)    sandbox account)
              enforced      isolated
              budget)       account)
       └──────────────── every step audited ────────────────┘
```

- **Blueprints** define what can be provisioned (v1: a dev sandbox).
- **Gates** enforce policy on a task transition. v1 ships two: human approval, and a
  **cloud-enforced budget** (a real account budget + quota + service allowlist — a hard
  ceiling the cloud enforces, not a promise a user makes).
- **Actuators** do the work. v1 ships `RealActuator` (runs OpenTofu in a serverless
  container job) and `DummyActuator` (dry-run — also the test double, and the placeholder
  for capabilities that aren't live yet).
- **Isolation:** each sandbox is its own cloud account/project. Teardown deletes the
  account, which makes orphaned resources structurally hard to leave behind.
- **Audit:** every plan, approval, apply, and destroy is an append-only event.

## Architecture at a glance

```
                          CONTROL PLANE (your account)
  +---------------------------------------------------------------------+
  |  FastAPI  -- enqueue -->  Queue        -- trigger -->  Tofu Runner   |
  |  (intake, board, gates)   (SQS/Pub-Sub)               (Fargate/      |
  |     |                                                  Cloud Run Job)|
  |     v                                                                |
  |  Postgres: work_requests · tasks · jobs (state machine) ·            |
  |            blueprints · audit_events (append-only)                   |
  +---------------------------------------------------------------------+
                                      | OIDC scoped role (no static keys)
                                      v
                      Sandbox = its own AWS account / GCP project
```

Full detail — execution model, the job state machine, the `Actuator` interface, the
data model, failure modes, and the test strategy — is in
[`docs/ARCHITECTURE_AND_DESIGN.md`](docs/ARCHITECTURE_AND_DESIGN.md)
(and as a [PDF](docs/FlowOps-Architecture-and-Design.pdf)).

## Quickstart (target)

> The app runs out of the box. The *actuation* half requires you to wire your cloud
> (credentials + an isolation strategy) — it cannot be zero-config.

```bash
# 1. Run the full control plane in DEV MODE (no cloud credentials needed)
FLOWOPS_PROFILE=dev docker compose up

# 2. Open the board
open http://localhost:5173

# 3. When ready for real provisioning, switch to the cloud profile + wire a cloud
#    FLOWOPS_PROFILE=cloud  (guided cloud setup -> see docs/, coming with the first release)
```

**Dev mode** (`FLOWOPS_PROFILE=dev`) runs the entire loop — request, both gates, the job
state machine, TTL teardown, and the audit trail — on your laptop with **zero cloud
credentials and zero cloud spend**, using a simulated actuator. The budget gate is
advisory and clearly labeled "dev — not enforced." Everything above the actuator is
identical to the cloud profile, so what you build in dev mode is what runs in production.

## Tech stack

- **Control plane:** Python / FastAPI, PostgreSQL
- **Execution:** a durable queue (SQS / Pub-Sub) feeding a serverless container job
- **Provisioning:** [OpenTofu](https://opentofu.org) (the open-source IaC engine)
- **Clouds:** AWS and GCP (one is implemented first; the actuator interface ports the rest)
- **Frontend:** React, themed via the
  [NYS Design System](https://designsystem.ny.gov/) tokens, WCAG 2.1 AA

## Roadmap

| Phase | What | Status |
|---|---|---|
| v1 | Dev-sandbox vending: request → approval + budget gate → OpenTofu → TTL teardown → audit | **Building** |
| Fast-follow | AI sandbox blueprint; the agent fulfiller (agents do tasks inside the gates) | Planned |
| Later | Pluggable policy (OPA/Cedar), multi-cloud, embeddable actuation core | Planned |

The agent fulfiller is the heart of the vision and is deliberately *not* in v1 — v1
proves the governed-actuation loop end to end first.

## Open source & commercial

FlowOps is **open-core**:

- **Free / open source (AGPL-3.0):** the complete single-organization governed-actuation
  loop — request → task → action, the actuator, approval + cloud-enforced budget gates,
  TTL teardown, audit, account/project vending, the dev-sandbox blueprint, the REST API,
  and RBAC. A real team runs this in production.
- **Commercial license:** for organizations that need multi-tenancy, SSO/SAML/SCIM,
  advanced policy, hosted runners, audit retention / compliance evidence, and support —
  or that want to embed FlowOps in a proprietary platform without AGPL's network-copyleft
  obligations.

If the AGPL doesn't fit your use (for example, embedding in a closed-source product),
a commercial license is available. Reach out via the repository's contact channels.

## Contributing

Contributions are welcome. Because FlowOps is dual-licensed (AGPL-3.0 + commercial), all
contributors must sign a **Contributor License Agreement (CLA)** so the project can offer
the commercial license. The CLA bot will prompt you on your first pull request.

Before building anything large, open an issue to discuss it. The architecture and the
open-core boundary are documented in
[`docs/ARCHITECTURE_AND_DESIGN.md`](docs/ARCHITECTURE_AND_DESIGN.md).

## License

FlowOps is licensed under the **GNU Affero General Public License v3.0** — see
[`LICENSE`](LICENSE). The AGPL's network-use clause means if you run a modified FlowOps
as a network service, you must offer your users the modified source.

A separate **commercial license** is available for proprietary embedding and the
enterprise feature set (see *Open source & commercial* above).

`SPDX-License-Identifier: AGPL-3.0-or-later`
