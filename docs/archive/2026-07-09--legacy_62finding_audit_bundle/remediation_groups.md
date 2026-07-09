# Remediation Groups

Created: 2026-04-28
Source: `docs/audit/audit.md` and segment audit artifacts
Status: synthesis item 3 complete

## Scope

This file groups confirmed audit findings by remediation shape. It does not add new evidence or replace the detailed segment reports.

Group meanings:

- **Release blockers**: must be fixed, explicitly disabled, or formally accepted before live-money operation, production API exposure, or ML-driven autonomy.
- **Quick wins**: localized fixes that reduce risk quickly without broad redesign.
- **Architectural repairs**: cross-cutting design or ownership changes that need a planned workstream.
- **Accepted / monitoring candidates**: can remain temporarily only when the referenced feature is disabled, local-only, or explicitly monitored.

## Release Blockers

These should be treated as the first gate for any live-money or production-facing release.

| Theme | Findings | Rationale |
| --- | --- | --- |
| Live authorization and live write boundary | `LP-001`, `OE-007`, `OS-001` | Live authorization can be renewed or live REST flattening can run outside the intended global-mode / signed-control-plane boundary. |
| Mutating API authorization | `DAPI-001`, `DAPI-006`, `RC-003` | State-changing budget/risk/config routes are not consistently guarded by operator role or route-specific write scopes. |
| Risk fail-closed behavior | `RC-001`, `RC-002`, `RC-004`, `RC-005` | Emergency flatten, H0 cooldown/kill-switch persistence, missing live risk config, and risk-tier enforcement can fail open or become non-durable. |
| Execution ingestion and idempotency | `OE-001`, `OE-002`, `OE-004` | Fill/order ingestion can drop batched private WS events, leave pending orders after failed dispatch, or lack exchange-native fill idempotency. |
| Trading DB durability | `OE-003`, `DBW-002`, `DBW-003` | High-value trading/learning rows can be dropped on channel backpressure or writer failure without a durable fallback. |
| Scheduler / watcher live control | `SW-001`, `SW-002` | Maintenance can race with watchdog restarts, and Live respawn can leave stale background command senders. |
| Destructive operational scripts | `OS-002` | DB reset can run against the configured local database, and `fresh_start.sh --yes` bypasses the intended manual confirmation barrier. |
| Migration coverage / startup safety | `DBW-001`, `DBW-005` | Active runtime schema can be excluded from migration paths, and auto-migrate can report success when the pool is unavailable. |
| Secret and credential baseline | `SC-001`, `SC-002`, `SC-003` | Auto-generated privileged API tokens, weak GUI password validation, and committed bearer credentials are incompatible with production exposure. |
| Strategy and teacher fail-open paths | `SADF-001`, `SADF-003` | Teacher directives can be silently drained when Paper is disabled, and strategy config loading fail-opens outside Paper. |
| ML autonomy / canary release gate | `MLM-001`, `MLM-002`, `MLM-003`, `MLM-004`, `MLM-005` | ML schema enforcement, canary atomicity, label finality, and LinUCB state/reward persistence are not safe enough for autonomous model promotion or live decision use. |

## Quick Wins

These are good early tickets because the fix surface is localized and risk reduction is immediate.

| Findings | Suggested action |
| --- | --- |
| `LP-002` | Replace invalid Cargo package ID `openclaw-engine` with `openclaw_engine` in restart scripts and add a package-ID smoke check. |
| `LP-003` | Update or retire the stale paper auto-start script path and document the required `OPENCLAW_ENABLE_PAPER=1` behavior. |
| `OE-006` | Align close retry timeout implementation with the documented 500 ms budget, or update the documented budget and operator output. |
| `OE-008` | Make close-all/session-stop responses report partial failures and orphan sweep errors as non-success outcomes. |
| `OE-009` | Populate dedicated `trading.risk_verdicts` fields or remove/rename unused columns to prevent false audit confidence. |
| `RC-006` | Return IPC success only after send/application success, and surface failures to operators. |
| `SC-004` | Remove hard-coded Grafana admin password, disable anonymous access by default, and bind monitoring to local/private interfaces. |
| `SC-005` | Move secrets out of argv and long-lived process environments where feasible; prefer files, stdin, or service-owned secret stores. |
| `SC-006` | Remove provider keys from launchd templates and require preflight secret injection. |
| `SC-007` | Base cookie `Secure` behavior on deployment configuration / trusted proxy headers, not raw request scheme alone. |
| `DBW-004` | Roll back or reset psycopg2 connections before returning them to the API pool. |
| `SADF-002` | Validate the full strategy parameter payload before mutating runtime state. |
| `SADF-005` | Return a no-op / unsupported status for `boost_arm` until it has a real LinUCB side effect. |
| `SW-004` | Persist a ledger snapshot after expiring stale hypotheses. |
| `SW-006` | Add overlap locks to cron wrappers. |
| `DAPI-002` | Add auth to model registry read routes and redact DB error details / artifact paths as needed. |
| `DAPI-003` | Strip `Cookie` as well as `Authorization` in the `/openclaw` reverse proxy unless explicitly required. |
| `DAPI-004` | Enforce server-side auth for dashboard HTML routes instead of relying on client-side redirect scripts. |
| `DAPI-005` | Require auth for `/api/v1/health/db` or reduce it to a coarse health signal. |
| `DAPI-007` | Replace API-side ad hoc uvicorn restart with the normal service manager or operator restart script. |
| `OS-003` | Narrow process matching to repo-owned PID files / service labels instead of broad substrings and port 8000 kills. |
| `OS-004` | Add `EXIT` / `ERR` / signal traps around watchdog maintenance flag cleanup. |
| `OS-005` | Add launchd preflight that rejects missing env/secrets before loading services. |
| `OS-006` | Remove application-role `SUPERUSER` and SQL-escape bootstrap password literals. |
| `OS-007` | Build Telegram JSON with a real encoder and avoid placing the bot token in the curl URL argument where possible. |

## Architectural Repairs

These are larger workstreams. Several overlap with release blockers; the grouping here describes the durable repair shape.

| Workstream | Findings | Repair shape |
| --- | --- | --- |
| Single live authorization contract | `LP-001`, `OE-007`, `OS-001`, `RC-003`, `DAPI-001`, `DAPI-006` | Make every live write and high-risk config mutation depend on one signed, mode-bound authorization contract with route-level operator/scope checks. |
| Exchange execution ledger and replay safety | `OE-001`, `OE-002`, `OE-003`, `OE-004`, `OE-005`, `OE-009`, `DBW-002`, `DBW-003` | Use exchange-native IDs, durable queues/fallbacks, explicit failure states, and deterministic fill attribution across WS, REST, DB writers, and recovery. |
| Risk state as durable fail-closed authority | `RC-001`, `RC-002`, `RC-004`, `RC-005`, `RC-006` | Persist H0 cooldown/kill-switch state, enforce tier constraints at admission, and make emergency flatten dispatch real exchange reduce-only orders when in live mode. |
| Migration and DB lifecycle governance | `DBW-001`, `DBW-004`, `DBW-005`, `OS-002`, `OS-006` | Consolidate migration inclusion rules, fail closed on migration uncertainty, restrict DB privileges, and make destructive scripts environment-aware and auditable. |
| Scheduler and service ownership | `SW-001`, `SW-002`, `SW-003`, `SW-005`, `SW-006`, `SW-007`, `DAPI-007`, `OS-003`, `OS-004`, `OS-005` | Introduce leader election / locks, service-manager-owned restarts, repo-owned PID tracking, and reliable maintenance windows. |
| Secrets and deployment trust boundary | `SC-001`, `SC-002`, `SC-003`, `SC-004`, `SC-005`, `SC-006`, `SC-007`, `DAPI-003` | Replace placeholder/autogenerated privileged secrets with explicit provisioning, rotate committed credentials, and keep tokens out of logs, argv, proxy hops, and templates. |
| Strategy / agent decision integrity | `SADF-001`, `SADF-002`, `SADF-003`, `SADF-004`, `SADF-005`, `SADF-006` | Align teacher directives, strategy config hot updates, LinUCB metadata, and Strategist Live promotion with durable state and release-mode guards. |
| ML model governance | `MLM-001`, `MLM-002`, `MLM-003`, `MLM-004`, `MLM-005`, `DAPI-002` | Treat feature schema hashes, q10/q50/q90 trios, label finality, canary promotion, and model metadata access as one governed model-release pipeline. |

## Accepted / Monitoring Candidates

These are not recommended as permanent accepts. They are candidates only when the stated constraint is true and documented in the release checklist.

| Findings | Accept only if | Monitoring / exit condition |
| --- | --- | --- |
| `LP-003` | Paper auto-start is not an authoritative runtime path. | Retire the script or add a smoke test before using it in operations. |
| `SADF-004`, `SADF-006` | LinUCB and Strategist Live promotion remain observation-only / Demo-primary. | Promote to blocker before enabling live per-decision arm selection or Strategist Live metrics. |
| `SW-007` | Legacy telemetry rows are not used for trading, risk, or operator alerts. | Remove duplicate writer or add leader election if telemetry becomes decision-relevant. |
| `DAPI-002`, `DAPI-005` | API is strictly local/private and protected by network controls. | Add auth/redaction before exposing beyond localhost or private admin network. |
| `SC-004`, `OS-007` | Monitoring/reporting endpoints are local-only and credentials have been rotated. | Harden before shared network deployment or operator handoff. |

## Suggested Batch Order

1. Fix the release blockers that can trigger unauthorized live writes, fail-open risk behavior, credential exposure, or trading-state loss.
2. Land quick wins that reduce operational confusion and auth/secret exposure without touching core trading logic.
3. Run the architectural workstreams as separate tracked epics, starting with execution durability and risk-state authority.
4. Keep accepted/monitoring candidates on the release checklist so dormant or local-only assumptions cannot silently become production assumptions.
