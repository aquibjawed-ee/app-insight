# app-insight

AS-IS discovery and production-readiness assessment across an organisation's applications.

Point it at repositories (local paths, a folder of repositories, remote URLs, or a `.csv` / `.xlsx` / `.txt` list) and
it produces, for every application:

- **AS-IS inventory**: stack and versions, modules, entry points, data stores, messaging, outbound calls, CI, deployment,
  owners, each fact with the file and line it was read from;
- **the aspect trace**: 13 aspects that matter for production readiness and maturity, each made of controls. Every
  control has a state, how strongly it was shown, the evidence lines, and, when it is not in place, a finding and the
  remedy from the client's remedy pack;
- **a portfolio report** (`report-internal.html`, one self-contained file, internal until reviewed): applications × aspects, findings grouped by aspect,
  a roadmap in dependency order, architecture and change impact.

It is deterministic and offline once the repositories are on disk. No model decides a fact or a verdict, so it gives
the same answer whether a person, Claude Code, Codex or any other agent runs it. See [AGENTS.md](AGENTS.md).

## Quick start

```bash
bin/app-insight doctor
bin/app-insight scan repos.csv --client acme
bin/app-insight scan ~/code/payments ~/code/orders https://gitlab.example.com/grp/billing.git --client acme
bin/app-insight summary ~/app-insight-workspaces/acme
```

Python 3.9+ and git. No other dependencies.

## The aspects

| # | Aspect | Question |
|---|---|---|
| 1 | Build & delivery | Can a change reach production automatically and be undone? |
| 2 | Testing & safety net | Would a regression be caught before it ships? |
| 3 | Security & supply chain | Are code, dependencies and secrets scanned, and is exposure known? |
| 4 | Platform & dependencies | Is the runtime and framework supported, and are libraries current? |
| 5 | Runtime resilience | Does the application survive slow or failing dependencies and restarts? |
| 6 | Deployment & availability | Does it keep serving through rollouts, node loss and load? |
| 7 | Observability & operations | Would the team know it is failing, and why? |
| 8 | API & contracts | Can consumers rely on a published, checked contract? |
| 9 | Data management | Are schema changes controlled and data recoverable? |
| 10 | Architecture & coupling | What does it depend on, and what depends on it? |
| 11 | Code health | Is the code easy and safe to change? |
| 12 | Knowledge & ownership | Who owns it, and could someone new work on it? |
| 13 | Configuration hygiene | Is configuration externalised, consistent and free of secrets? |

The catalogue (`app_insight/packs/aspects.v1.json`) is a **draft**: controls without a detector yet report
`NOT_ASSESSED` with the reason, never a pass. Control states: `PRESENT`, `PARTIAL`, `ABSENT` (not found in the files
read), `ISSUE`, `UNKNOWN`, `NOT_APPLICABLE`, `NOT_ASSESSED`. Evidence levels: declared, configured, enforced in CI,
verified.

## Remedy packs

What to do about a gap depends on the client's tooling, so remedies are packs, chosen per client and remembered in
the client workspace:

- `generic`: tool-neutral steps;
- `modernise-plugin`: the app-modernise Claude Code plugin commands (`/modernise-pipeline`, `/modernise-unit-test`, ...).

`--remedies modernise-plugin,generic` means "use the plugin command where there is one, otherwise the generic step".
A client can supply its own pack file path.

## Status

- **Step 1**: the trace contract, the product shell (ingestion, workspaces, CLI) and the report on top of it.
- **Step 2 (runtime resilience)**: HTTP client timeouts, retries and circuit breakers, message-consumer error handling
  (Kafka, RabbitMQ, JMS, SQS), database query/transaction timeouts and pools, graceful shutdown and structured logging
  are read from `application*.properties|yml`, logging configuration and main source code
  (`engine/scripts/detectors/runtime.py`). A setting supplied only by the platform or the environment at deploy time
  is not visible: those cases report `UNKNOWN`, not a gap.

Still `NOT_ASSESSED`: code health and hotspots, git-history signals, ADRs, secrets in configuration, backup/DR, alerts
and SLOs. Other language adapters come after.
