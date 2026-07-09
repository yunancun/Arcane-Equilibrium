# TradeBot Full Code Audit

Created: 2026-04-28
Status: complete; all audit segments and final synthesis complete
Owner: Codex audit session

## Purpose

This document is the working ledger for a full repository audit of TradeBot code, excluding tests. It is not a finished audit report yet. It records scope, exclusions, review order, module status, findings, open questions, and verification evidence as the audit progresses.

The audit should prioritize correctness, financial safety, live-trading safety, operational recoverability, and maintainability. Any finding must be grounded in concrete file references and, where possible, a reproducible failure mode.

## Scope

Repository root:

- `/Users/ncyu/Projects/TradeBot/srv`

Primary code and configuration areas currently identified:

- `program_code/`
- `rust/`
- `helper_scripts/`
- `sql/migrations/`
- `docker/`
- `docker_projects/`
- `settings/`
- `scripts/`

Context-only areas:

- `docs/`
- `memory/`
- `research_notes/`
- `TODO.md`
- `README.md`
- Existing audit history under `docs/audits/`

Current inventory artifacts:

- `docs/audit/inventory_summary.md`
- `docs/audit/inventory_manifest.tsv`
- `docs/audit/non_test_manifest.tsv`
- `docs/audit/excluded_manifest.tsv`
- `docs/audit/entry_points_services.md`
- `docs/audit/entry_points_manifest.tsv`
- `docs/audit/live_paper_mode_separation.md`
- `docs/audit/order_execution_reconciliation.md`
- `docs/audit/risk_controls_kill_switches.md`
- `docs/audit/secrets_credentials.md`
- `docs/audit/database_migrations_writes.md`
- `docs/audit/strategy_agent_decision_flow.md`
- `docs/audit/ml_model_registry.md`
- `docs/audit/schedulers_watchdogs.md`
- `docs/audit/dashboards_apis.md`
- `docs/audit/operator_scripts.md`
- `docs/audit/remediation_groups.md`
- `docs/audit/final_summary.md`
- `docs/audit/final_record_zh.md`

Inventory note:

- The authoritative inventory is generated from the Git root with `git ls-files --cached --others --exclude-standard`.
- Current Git-visible files: 2,076.
- Current in-scope code/config/schema/script files: 844.
- Current context files: 977.
- Current excluded files: 255.
- Tests, build artifacts, backups, and archived docs are excluded from code audit scope.
- Audit artifacts themselves are counted as context, not in-scope runtime code.

## Explicit Exclusions

The audit excludes test code unless a test file is needed to understand expected behavior.

Excluded path patterns:

- `test/`
- `tests/`
- `__tests__/`
- `**/test/**`
- `**/tests/**`
- `**/__tests__/**`
- generated output
- vendored dependencies
- virtual environments
- build artifacts
- cache directories
- log directories
- binary backups and dumps

Examples of excluded repository areas:

- `rust/target/`
- `venvs/`
- `.pytest_cache/`
- `log_files/`
- `backups/`

Secrets and secret-adjacent configuration should not be opened unless explicitly needed and approved for a narrowly scoped security review.

## Audit Priorities

Review order should follow operational and financial risk, not directory order.

Priority 0:

- Live trading gates
- Order placement, cancellation, reconciliation, and fill handling
- Risk limits, kill switches, paper/live separation, and mode transitions
- API key, secret, and exchange credential handling
- Database writes that affect positions, fills, decisions, budgets, or model state

Priority 1:

- Strategy signal generation and execution decision flow
- Background schedulers, watchdogs, and cron scripts
- Runtime configuration loading, hot reload, and config persistence
- External API integrations and retry behavior
- Idempotency, concurrency, and partial-failure recovery

Priority 2:

- ML training, inference, model registry, and feature pipelines
- Reporting and dashboard surfaces
- Maintenance scripts and operator tools
- Documentation-to-code consistency

## Method

1. Build a reviewed-file manifest for non-test code.
2. Map executable entry points and long-running services.
3. Map data stores, migrations, and tables touched by runtime code.
4. Map external integrations, especially exchange APIs and model providers.
5. Review high-risk chains end to end before low-risk utilities.
6. Record findings with severity, evidence, impact, and suggested remediation.
7. Record files reviewed even when no issue is found.
8. Re-run targeted validation after fixes are made.

## Finding Format

Use this format for every confirmed issue:

```text
ID:
Severity: P0 | P1 | P2 | P3
Status: open | fixed | false-positive | accepted-risk
Area:
Files:
Summary:
Evidence:
Impact:
Reproduction or trigger:
Recommended fix:
Verification:
```

Severity guidance:

- `P0`: Can cause real money loss, unauthorized live trading, irreversible state corruption, credential exposure, or total production outage.
- `P1`: Can cause incorrect trading decisions, missed safety controls, durable data inconsistency, or serious operational failure.
- `P2`: Meaningful correctness, reliability, or maintainability issue with bounded blast radius.
- `P3`: Low-risk cleanup, documentation mismatch, weak diagnostics, or localized maintainability issue.

## Review Ledger

| Area | Status | Notes |
| --- | --- | --- |
| Repository inventory | complete | Generated inventory manifests and summary under `docs/audit/`. |
| Entry points and services | complete | Mapped service, router, scheduler, launchd, Docker, shell, and Python CLI entry points. |
| Live/paper mode separation | complete | See `docs/audit/live_paper_mode_separation.md`. Confirmed 3 findings. |
| Order execution and reconciliation | complete | See `docs/audit/order_execution_reconciliation.md`. Confirmed 9 findings. |
| Risk controls and kill switches | complete | See `docs/audit/risk_controls_kill_switches.md`. Confirmed 6 findings. |
| Secrets and credentials | complete | See `docs/audit/secrets_credentials.md`. Confirmed 7 findings. |
| Database migrations and writes | complete | See `docs/audit/database_migrations_writes.md`. Confirmed 5 findings. |
| Strategy and agent decision flow | complete | See `docs/audit/strategy_agent_decision_flow.md`. Confirmed 6 findings. |
| ML and model registry | complete | See `docs/audit/ml_model_registry.md`. Confirmed 5 findings. |
| Schedulers and watchdogs | complete | See `docs/audit/schedulers_watchdogs.md`. Confirmed 7 findings. |
| Dashboards and APIs | complete | See `docs/audit/dashboards_apis.md`. Confirmed 7 findings. |
| Operator scripts | complete | See `docs/audit/operator_scripts.md`. Confirmed 7 findings. |
| Remediation grouping | complete | See `docs/audit/remediation_groups.md`. Final synthesis item 3. |
| Final audit summary and fix order | complete | See `docs/audit/final_summary.md`. Final synthesis item 4. |
| Chinese final record | complete | See `docs/audit/final_record_zh.md`. Includes de-duplication, priority ranking, and complete Chinese finding index. |

## Confirmed Findings

### LP-001

Severity: P1
Status: open
Area: Live authorization / global mode separation
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_trust_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py`
- `rust/openclaw_engine/src/live_auth_watcher.rs`
- `rust/openclaw_engine/src/startup/mod.rs`
- `rust/openclaw_engine/src/tick_pipeline/mod.rs`
- `rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`

Summary:

`POST /api/v1/live/auth/renew` and `/auth/renew-review` can write signed `authorization.json` and wake the Rust watcher without requiring `global_mode_state == "live_reserved"`. Rust respawn is driven by authorization validity, and newly constructed pipelines default to `SystemMode::LiveReserved`.

Evidence:

See `docs/audit/live_paper_mode_separation.md#lp-001`.

Impact:

Operator-authenticated renewal can bring up the Live pipeline even while the control-plane global mode is not live-reserved. Mainnet still requires `OPENCLAW_ALLOW_MAINNET=1` and live credentials, but the intended global-mode safety boundary is bypassed.

Recommended fix:

Require exact live-reserved mode before writing signed Live authorization, stop using substring mode checks, and make Rust fail closed or verify the approved mode as part of the signed authorization contract.

Verification:

Static trace only.

### LP-002

Severity: P2
Status: open
Area: Operator restart scripts
Files:

- `helper_scripts/clean_restart.sh`
- `helper_scripts/fresh_start.sh`
- `rust/openclaw_engine/Cargo.toml`

Summary:

`clean_restart.sh` and `fresh_start.sh` rebuild with invalid Cargo package ID `openclaw-engine`; the package is `openclaw_engine`.

Evidence:

`cargo pkgid -p openclaw-engine --manifest-path rust/Cargo.toml` failed; `cargo pkgid -p openclaw_engine --manifest-path rust/Cargo.toml` succeeded. See `docs/audit/live_paper_mode_separation.md#lp-002`.

Impact:

Clean/fresh restart recovery can fail when the release binary is missing or stale.

Recommended fix:

Use `-p openclaw_engine` in both scripts and add a lightweight package-ID check.

Verification:

Static command validation only.

### LP-003

Severity: P3
Status: open
Area: Paper startup automation
Files:

- `helper_scripts/start_paper_trading.sh`
- `helper_scripts/deploy/README.md`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_routes.py`
- `rust/openclaw_engine/src/main_pipelines.rs`

Summary:

`start_paper_trading.sh` is still documented as an auto-start path, but it parses stale response fields and does not account for Rust Paper being disabled unless the engine is launched with `OPENCLAW_ENABLE_PAPER=1`.

Evidence:

See `docs/audit/live_paper_mode_separation.md#lp-003`.

Impact:

Paper startup automation can be misleading or ineffective.

Recommended fix:

Retire or update the script to verify Paper enablement and current response shapes.

Verification:

Static route/script comparison only.

### OE-001

Severity: P1
Status: open
Area: Private WebSocket fill/order ingestion
Files:

- `rust/openclaw_engine/src/bybit_private_ws.rs`
- `rust/openclaw_engine/src/execution_listener.rs`

Summary:

Bybit private WS `data` arrays are parsed into only one `PrivateWsEvent`; later items in the same message are discarded.

Evidence:

See `docs/audit/order_execution_reconciliation.md#oe-001`.

Impact:

Multi-record order, execution, position, or wallet messages can drop fills and terminal order states, leaving runtime and DB state out of sync with Bybit.

Recommended fix:

Change private WS parsing/dispatch to emit all parsed payload items per message.

Verification:

Static trace only.

### OE-002

Severity: P1
Status: open
Area: Order dispatch failure recovery
Files:

- `rust/openclaw_engine/src/event_consumer/dispatch.rs`
- `rust/openclaw_engine/src/event_consumer/loop_handlers.rs`
- `rust/openclaw_engine/src/tick_pipeline/commands.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_6_risk_checks.rs`

Summary:

Primary orders are registered as pending and written as `Working` before REST dispatch succeeds; dispatch failures and close enqueue failures do not reliably clear pending state.

Evidence:

See `docs/audit/order_execution_reconciliation.md#oe-002`.

Impact:

The DB can contain phantom `Working` orders, and close/risk-close paths can be blocked by stale `pending_close_symbols` while the exchange position remains open.

Recommended fix:

Emit a terminal dispatch-failure event and clear pending/pending-close state whenever REST dispatch or channel enqueue fails.

Verification:

Static trace only.

### OE-003

Severity: P1
Status: open
Area: Trading DB durability
Files:

- `rust/openclaw_engine/src/database/batch_insert.rs`
- `rust/openclaw_engine/src/database/trading_writer.rs`

Summary:

Trading writer batch insert failures are logged but not propagated, and buffers are cleared after failed or unavailable DB writes.

Evidence:

See `docs/audit/order_execution_reconciliation.md#oe-003`.

Impact:

Transient DB failures can permanently drop intents, fills, orders, order state changes, and risk verdicts.

Recommended fix:

Return insert failures to callers and retain, retry, or dead-letter failed trading rows with explicit operator alerting.

Verification:

Static trace only.

### OE-004

Severity: P1
Status: open
Area: Fill idempotency and restore correctness
Files:

- `rust/openclaw_engine/src/bybit_private_ws.rs`
- `rust/openclaw_engine/src/event_consumer/loop_handlers.rs`
- `rust/openclaw_engine/src/tick_pipeline/commands.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick_helpers.rs`
- `rust/openclaw_engine/src/database/trading_writer.rs`
- `sql/migrations/V003__trading_agent_tables.sql`

Summary:

Exchange-confirmed fill rows do not use Bybit `exec_id` as the durable idempotency key.

Evidence:

See `docs/audit/order_execution_reconciliation.md#oe-004`.

Impact:

Same-symbol same-millisecond executions can update runtime state while only one fill row persists, causing restart restore and audit accounting gaps.

Recommended fix:

Thread `exec_id` into attributed fill persistence and use it in the fill ID or a dedicated unique column.

Verification:

Static trace only.

### OE-005

Severity: P2
Status: open
Area: Fill attribution race
Files:

- `rust/openclaw_engine/src/event_consumer/loop_handlers.rs`

Summary:

Fill-before-order-update fallback matching chooses the first pending order with the same symbol and side.

Evidence:

See `docs/audit/order_execution_reconciliation.md#oe-005`.

Impact:

Concurrent same-symbol same-side pending orders can receive the wrong strategy, context, fee fallback, and lifecycle attribution.

Recommended fix:

Use fallback matching only for a single unambiguous candidate; otherwise hold or persist the fill as unattributed and reconcile later.

Verification:

Static trace only.

### OE-006

Severity: P2
Status: open
Area: Close order timeout budget
Files:

- `rust/openclaw_engine/src/event_consumer/dispatch.rs`
- `rust/openclaw_engine/src/bybit_rest_client.rs`

Summary:

Close retries document a 500 ms sleep budget, but each REST attempt can wait on the global 10 second HTTP timeout.

Evidence:

See `docs/audit/order_execution_reconciliation.md#oe-006`.

Impact:

Risk exits and operator close commands can take roughly 30 seconds before failure handling continues during REST degradation.

Recommended fix:

Add close-specific per-attempt timeout handling or account for HTTP timeout in the close retry budget.

Verification:

Static trace only.

### OE-007

Severity: P1
Status: open
Area: Live close write guard and REST fallback
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_account_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_routes.py`

Summary:

Live close endpoints can use direct REST fallback with the live key slot when the Rust live engine/channel is unavailable, as long as the live slot is configured.

Evidence:

See `docs/audit/order_execution_reconciliation.md#oe-007`.

Impact:

Reduce-only live exchange mutations can occur outside the primary Rust live dispatch and authorization path.

Recommended fix:

Require explicit live-engine authorized/running state for live writes, or isolate REST emergency close behind separate authorization and acknowledgement.

Verification:

Static trace only.

### OE-008

Severity: P2
Status: open
Area: Operator close-all result reporting
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_ai_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_account_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py`

Summary:

Close-all and session-stop responses can report successful closure even when close or orphan-sweep errors occurred.

Evidence:

See `docs/audit/order_execution_reconciliation.md#oe-008`.

Impact:

Operators and scripts can believe all positions were closed while some positions remain open.

Recommended fix:

Return explicit partial-failure status and include per-symbol orphan sweep failures in the error list.

Verification:

Static trace only.

### OE-009

Severity: P2
Status: open
Area: Risk verdict audit fidelity
Files:

- `sql/migrations/V003__trading_agent_tables.sql`
- `rust/openclaw_engine/src/database/trading_writer.rs`

Summary:

The `trading.risk_verdicts` schema has dedicated risk fields that the writer never populates.

Evidence:

See `docs/audit/order_execution_reconciliation.md#oe-009`.

Impact:

Risk-control dashboards and audits can underreport or misread runtime verdict details when querying structured columns.

Recommended fix:

Populate the dedicated columns or explicitly deprecate them and document `details` as canonical.

Verification:

Static trace only.

### RC-001

Severity: P1
Status: open
Area: Emergency close / exchange flattening
Files:

- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_0_5_h0_gate.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_0_fast_track.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_3_signals.rs`
- `rust/openclaw_engine/src/tick_pipeline/commands.rs`

Summary:

H0 hard-block stops and fast-track CloseAll flatten local state without dispatching exchange reduce-only close orders.

Evidence:

See `docs/audit/risk_controls_kill_switches.md#rc-001`.

Impact:

Demo/live can appear flat locally while exchange positions remain open during emergency conditions.

Recommended fix:

Route automatic emergency full-close paths through the same exchange-aware close primitive as IPC close-all, or dispatch reduce-only closes before mutating local state.

Verification:

Static trace only.

### RC-002

Severity: P1
Status: open
Area: H0 cooldown and kill switch state
Files:

- `rust/openclaw_types/src/risk.rs`
- `rust/openclaw_core/src/h0_gate.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_6_risk_checks.rs`
- `rust/openclaw_engine/src/event_consumer/loop_handlers.rs`
- `rust/openclaw_engine/src/event_consumer/types.rs`

Summary:

The periodic H0 risk snapshot refresh resets `cooldown_until_ts_ms` to `0` and `kill_switch_active` to `false` every 30 seconds.

Evidence:

See `docs/audit/risk_controls_kill_switches.md#rc-002`.

Impact:

Consecutive-loss cooldown can be erased within one status interval, and any H0 snapshot kill switch would be cleared by the heartbeat.

Recommended fix:

Preserve non-expired cooldown and active kill-switch state during exposure/count refresh, or split those fields into separate owned setters.

Verification:

Static trace only.

### RC-003

Severity: P1
Status: open
Area: API authorization for risk controls
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/risk_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_routes.py`

Summary:

Several mutating risk endpoints require authentication but not the operator role, including live per-engine config, cooldown reset, and session unhalt.

Evidence:

See `docs/audit/risk_controls_kill_switches.md#rc-003`.

Impact:

Non-operator authenticated actors can modify safety limits or clear halt/cooldown state.

Recommended fix:

Apply a shared operator guard to all mutating risk/session routes and add route tests for viewer vs operator behavior.

Verification:

Static trace only.

### RC-004

Severity: P1
Status: open
Area: Startup fail-safe defaults
Files:

- `rust/openclaw_engine/src/startup/mod.rs`
- `rust/openclaw_engine/src/config/io.rs`
- `rust/openclaw_engine/src/config/risk_config_advanced.rs`
- `settings/risk_control_rules/risk_config_live.toml`

Summary:

Missing live risk config falls back to `RiskConfig::default()`, whose runtime defaults put H0 in shadow mode.

Evidence:

See `docs/audit/risk_controls_kill_switches.md#rc-004`.

Impact:

A missing or mispointed live config can boot live with H0 observe-only rather than hard-blocking.

Recommended fix:

Require live/demo risk config files to exist, or make the fallback mode-aware and fail closed for live.

Verification:

Static trace only.

### RC-005

Severity: P1
Status: open
Area: Risk governor tier enforcement
Files:

- `rust/openclaw_core/src/sm/risk_gov.rs`
- `rust/openclaw_core/src/governance_core.rs`
- `rust/openclaw_engine/src/event_consumer/handlers/risk.rs`
- `rust/openclaw_engine/src/event_consumer/loop_handlers.rs`
- `rust/openclaw_engine/src/intent_processor/router.rs`
- `rust/openclaw_engine/src/tick_pipeline/commands.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`

Summary:

Risk governor escalations mutate only `governance.risk`; the auth cascade and `constraints_for(level)` are not consistently enforced in order admission.

Evidence:

See `docs/audit/risk_controls_kill_switches.md#rc-005`.

Impact:

Risk tier, governance mode, auth/lease state, and actual order admission can diverge during Reduced, Defensive, CircuitBreaker, or ManualReview states.

Recommended fix:

Route escalations through `GovernanceCore::execute_risk_cascade()` or enforce `constraints_for()` in all admission paths, including external orders.

Verification:

Static trace only.

### RC-006

Severity: P2
Status: open
Area: Legacy runtime risk config IPC
Files:

- `rust/openclaw_engine/src/ipc_server/handlers/risk.rs`
- `rust/openclaw_engine/src/event_consumer/handlers/risk.rs`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ipc_client.py`

Summary:

Legacy `update_risk_config` reports success after enqueueing and ignores send/application failure.

Evidence:

See `docs/audit/risk_controls_kill_switches.md#rc-006`.

Impact:

Operators or tools can receive a successful response even when a risk update was not delivered or was rejected.

Recommended fix:

Deprecate the legacy method in favor of `patch_risk_config`, or add acknowledgement from the event consumer and return send failures as errors.

Verification:

Static trace only.

### SC-001

Severity: P1
Status: open
Area: Control API bearer token lifecycle
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/auth.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main_legacy.py`
- `docker_projects/trading_services/openclaw_bybit_control_api_v1/docker-compose.yml`
- `docker_projects/trading_services/openclaw_bybit_control_api_v1/DEPLOY_README.md`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/API_TOKEN_RESET_GUIDE.md`

Summary:

When the Control API token is missing or placeholder-configured, the server auto-generates a new token and prints the full value to stderr. That token authenticates as the default actor, whose default roles include operator privileges.

Evidence:

See `docs/audit/secrets_credentials.md#sc-001`.

Impact:

First-run or misconfigured deployments can leak an operator-capable bearer token through container logs, launchd logs, terminal scrollback, or log aggregation.

Recommended fix:

Do not print generated token values. For production/docker, fail closed unless a non-placeholder token or explicit token file is provided. Default roles should be least-privilege unless operator roles are explicitly configured.

Verification:

Static trace only.

### SC-002

Severity: P1
Status: open
Area: GUI login credential validation
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/auth_routes_common.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/auth_legacy_routes.py`

Summary:

GUI login credential loading rejects missing or placeholder usernames but accepts a missing, empty, or placeholder password.

Evidence:

See `docs/audit/secrets_credentials.md#sc-002`.

Impact:

If `gui_auth.env` contains a valid username but lacks `GUI_PASSWORD` or has it blank, a login with an empty password succeeds and receives the full Control API bearer cookie.

Recommended fix:

Require a non-empty password, reject known placeholders, and add startup/login tests for missing, blank, and placeholder passwords.

Verification:

Static trace only.

### SC-003

Severity: P1
Status: open
Area: Committed monitoring credential
Files:

- `docker_projects/monitoring_services/provisioning/datasources/fastapi.yml`

Summary:

The Grafana FastAPI datasource provisioning file contains a committed literal bearer credential.

Evidence:

See `docs/audit/secrets_credentials.md#sc-003`.

Impact:

If the token is valid for the Control API, the repository contains an API credential. If it is stale, monitoring can silently fail until the mismatch is discovered.

Recommended fix:

Remove the literal token from the repository, rotate it if it was ever valid, provision Grafana from an injected secret, and add a secret scanner rule for committed bearer literals.

Verification:

Static trace only.

### SC-004

Severity: P2
Status: open
Area: Monitoring access control
Files:

- `docker_projects/monitoring_services/docker-compose.yml`

Summary:

The Grafana compose file hard-codes the admin password and enables anonymous Viewer access while publishing port `3000`.

Evidence:

See `docs/audit/secrets_credentials.md#sc-004`.

Impact:

On any host where this compose stack is reachable beyond localhost or a trusted network, dashboards can be viewed anonymously and admin access is protected by a repository-known password.

Recommended fix:

Move the admin password to an injected secret, disable anonymous access by default, and bind the port to localhost unless explicitly overridden.

Verification:

Static trace only.

### SC-005

Severity: P2
Status: open
Area: Secret propagation through process argv/env
Files:

- `helper_scripts/db/deploy_V017.sh`
- `helper_scripts/db/deploy_V018.sh`
- `helper_scripts/restart_all.sh`
- `helper_scripts/clean_restart.sh`
- `helper_scripts/fresh_start.sh`
- `helper_scripts/cron_daily_report.sh`
- `helper_scripts/start_paper_trading.sh`
- `helper_scripts/deploy/README.md`

Summary:

Several operator scripts pass database passwords, IPC secrets, API bearer tokens, or Telegram bot tokens through command arguments or long-lived process environments.

Evidence:

See `docs/audit/secrets_credentials.md#sc-005`.

Impact:

Local same-user processes, shell history, crash diagnostics, process listings, or launchd environment inspection can expose DB credentials, IPC HMAC secrets, Control API tokens, or Telegram bot tokens.

Recommended fix:

Prefer `.pgpass`, libpq service files, fd-passed secret files, or mounted secret files over DSN arguments and global env values. Load long-lived service secrets from `0600` files inside the process.

Verification:

Static trace only.

### SC-006

Severity: P2
Status: open
Area: Launchd AI provider secret handling
Files:

- `helper_scripts/deploy/com.openclaw.gateway.plist`

Summary:

The gateway launchd template includes AI provider API key fields inside the plist `EnvironmentVariables` block and instructs operators to fill them manually.

Evidence:

See `docs/audit/secrets_credentials.md#sc-006`.

Impact:

This invites operators to write provider keys directly into a plist file that lives in the repository tree before copy/install, increasing accidental commit and backup exposure risk.

Recommended fix:

Remove provider key fields from the plist template and use secret files or Keychain-backed injection for provider API keys.

Verification:

Static trace only.

### SC-007

Severity: P2
Status: open
Area: Auth cookie transport security
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/auth_routes_common.py`

Summary:

The auth cookie `Secure` attribute is based solely on `request.url.scheme == "https"`.

Evidence:

See `docs/audit/secrets_credentials.md#sc-007`.

Impact:

Behind a TLS-terminating proxy that forwards to Uvicorn over HTTP without trusted proxy scheme handling, the app can issue an auth cookie without `Secure`.

Recommended fix:

Add a production setting such as `OPENCLAW_COOKIE_SECURE=1`, configure trusted proxy headers, and fail closed for production non-localhost HTTP.

Verification:

Static trace only.

### DBW-001

Severity: P1
Status: open
Area: Migration coverage for exit feature labels
Files:

- `sql/migrations/V999__exit_features.sql`
- `rust/openclaw_engine/src/database/migrations.rs`
- `helper_scripts/linux_bootstrap_db.sh`
- `helper_scripts/db/audit_migrations.py`
- `rust/openclaw_engine/src/database/exit_feature_writer.rs`
- `rust/openclaw_engine/src/tick_pipeline/pipeline_helpers.rs`

Summary:

`learning.exit_features` is an active runtime table, but its only migration remains named `V999__exit_features.sql` and is excluded by the Linux migration applier, migration audit tool, and Rust auto-migrator.

Evidence:

See `docs/audit/database_migrations_writes.md#dbw-001`.

Impact:

Fresh Linux deployments and auto-migrated databases will miss the table, causing close-path exit label writes to fail and be dropped.

Recommended fix:

Rename the migration to the next real version, update migration tooling, and add a startup schema guard for the exit-feature writer.

Verification:

Static trace only.

### DBW-002

Severity: P1
Status: open
Area: Runtime DB producer backpressure
Files:

- `rust/openclaw_engine/src/tasks.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick_helpers.rs`
- `rust/openclaw_engine/src/tick_pipeline/pipeline_helpers.rs`
- `rust/openclaw_engine/src/event_consumer/loop_handlers.rs`
- `rust/openclaw_engine/src/tick_pipeline/commands.rs`

Summary:

High-value trading and learning rows are sent through bounded channels with `try_send`, but many call sites ignore the error.

Evidence:

See `docs/audit/database_migrations_writes.md#dbw-002`.

Impact:

Channel-full or closed-channel conditions can silently drop fills, orders, order state changes, risk verdicts, intents, and exit labels before any writer or fallback path sees them.

Recommended fix:

Centralize producer send helpers, use awaited send or durable local outbox for critical rows, and expose dropped-row counters per table.

Verification:

Static trace only.

### DBW-003

Severity: P1
Status: open
Area: Writer retry and fallback semantics
Files:

- `rust/openclaw_engine/src/database/batch_insert.rs`
- `rust/openclaw_engine/src/database/trading_writer.rs`
- `rust/openclaw_engine/src/database/context_writer.rs`
- `rust/openclaw_engine/src/database/decision_feature_writer.rs`
- `rust/openclaw_engine/src/database/exit_feature_writer.rs`
- `rust/openclaw_engine/src/database/shadow_fill_writer.rs`
- `rust/openclaw_engine/src/database/shadow_exit_writer.rs`
- `rust/openclaw_engine/src/database/market_writer.rs`

Summary:

Only the market writer has a real JSONL fallback. Other runtime writers clear or drain pending rows on pool unavailability or insert failure.

Evidence:

See `docs/audit/database_migrations_writes.md#dbw-003`.

Impact:

Transient DB outages, missing migrations, constraint errors, or dead connections can permanently drop trading lifecycle records, decision contexts, decision features, exit features, and shadow observations.

Recommended fix:

Move retry/fallback ownership into a shared writer abstraction that retains failed rows, retries with bounded backoff, or writes a replayable durable outbox.

Verification:

Static trace only.

### DBW-004

Severity: P2
Status: open
Area: API PostgreSQL connection lifecycle
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/db_pool.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/phase4_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_demo_sync.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/grafana_data_writer.py`

Summary:

The API pool's `put_conn()` returns psycopg2 connections without rollback/reset, and some direct `get_conn()` write paths can return failed transactions to the pool.

Evidence:

See `docs/audit/database_migrations_writes.md#dbw-004`.

Impact:

An aborted or idle transaction can be reused by later requests, causing follow-on DB failures or long-lived snapshots.

Recommended fix:

Make `put_conn()` defensively rollback, require `get_pg_conn()` for pooled use, or split autocommit read pools from explicit transaction write helpers.

Verification:

Static trace only.

### DBW-005

Severity: P2
Status: open
Area: Auto-migrate fail-closed behavior
Files:

- `rust/openclaw_engine/src/database/migrations.rs`
- `rust/openclaw_engine/src/main.rs`
- `rust/openclaw_engine/src/database/pool.rs`

Summary:

When `OPENCLAW_AUTO_MIGRATE=1` is enabled but the database pool is unavailable, the migration runner returns `Ok(NoPool)` and `main` logs it as completed.

Evidence:

See `docs/audit/database_migrations_writes.md#dbw-005`.

Impact:

Operators can believe auto-migration is active while schema migration and DB writes were skipped due to connection failure.

Recommended fix:

Treat `NoPool` as fatal when auto-migrate is explicitly enabled and DB writes are configured, except behind an explicit DB-less escape hatch.

Verification:

Static trace only.

### SADF-001

Severity: P1
Status: open
Area: Teacher directive routing / disabled Paper channel
Files:

- `rust/openclaw_engine/src/main.rs`
- `rust/openclaw_engine/src/tasks.rs`
- `rust/openclaw_engine/src/main_pipelines.rs`

Summary:

Claude Teacher production directives are routed to `paper_cmd_tx`, but Paper is disabled by default and its disabled-mode task drains and drops commands without sending command responses.

Evidence:

See `docs/audit/strategy_agent_decision_flow.md#sadf-001`.

Impact:

Operator-enabled Teacher directives can time out, report failure, or have no effect while no Demo or Live engine receives the intended strategy parameter mutation.

Recommended fix:

Route Teacher directive application through explicit Demo/Live command targets and make disabled Paper reject commands with responses instead of drain-dropping them.

Verification:

Static trace only.

### SADF-002

Severity: P2
Status: open
Area: Strategy parameter hot update atomicity
Files:

- `rust/openclaw_engine/src/event_consumer/handlers/strategy_params.rs`

Summary:

`handle_update_strategy_params` applies `conf_scale` before validating the remaining typed JSON. If typed validation fails, the runtime `conf_scale` change remains active even though the caller receives a failure and no snapshot is written.

Evidence:

See `docs/audit/strategy_agent_decision_flow.md#sadf-002`.

Impact:

Rejected mixed updates can still alter strategy confidence scaling until restart or a later successful update.

Recommended fix:

Stage updates atomically: validate typed JSON before mutating `conf_scale`, clone-and-validate a candidate, or roll back `conf_scale` on validation failure.

Verification:

Static trace only.

### SADF-003

Severity: P1
Status: open
Area: Strategy config fail-open behavior
Files:

- `rust/openclaw_engine/src/strategies/params.rs`
- `rust/openclaw_engine/src/strategies/strategy_params.rs`
- `rust/openclaw_engine/src/strategies/registry.rs`

Summary:

Strategy parameter loading fail-opens to full defaults for every pipeline kind when TOML is missing or unparseable, even though the comment only justifies Paper fail-open behavior.

Evidence:

See `docs/audit/strategy_agent_decision_flow.md#sadf-003`.

Impact:

Missing or broken Demo/Live strategy config can silently restore default-active strategies and default thresholds.

Recommended fix:

Fail closed for Demo and Live config load errors, or load a last-known-good durable config. Keep Paper fail-open only if intentional.

Verification:

Static trace only.

### SADF-004

Severity: P2
Status: open
Area: LinUCB decision metadata fidelity
Files:

- `rust/openclaw_engine/src/linucb/runtime.rs`
- `rust/openclaw_engine/src/intent_processor/mod.rs`
- `rust/openclaw_engine/src/decision_context_producer.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_3_signals.rs`

Summary:

LinUCB is described as live-path per-decision arm selection, but the wired path is observation-only and derives metadata from the first persisted signal rather than the accepted order intent.

Evidence:

See `docs/audit/strategy_agent_decision_flow.md#sadf-004`.

Impact:

LinUCB telemetry can be missing or detached from actual accepted-intent decisions, which can mislead dashboards and training jobs.

Recommended fix:

Either document LinUCB as signal-level observation telemetry or wire post-gate selection into the accepted-intent path using `OrderIntent.strategy`.

Verification:

Static trace only.

### SADF-005

Severity: P2
Status: open
Area: Teacher directive execution audit fidelity
Files:

- `rust/openclaw_engine/src/claude_teacher/applier.rs`
- `rust/openclaw_engine/src/claude_teacher/writer.rs`

Summary:

The `boost_arm` directive is a stub with no LinUCB side effect, but it returns `Applied` and is persisted as `success = true`.

Evidence:

See `docs/audit/strategy_agent_decision_flow.md#sadf-005`.

Impact:

Operators and reports can believe an arm boost was executed when no model or arm state changed.

Recommended fix:

Return a non-success outcome for `boost_arm` until real LinUCB state mutation is implemented.

Verification:

Static trace only.

### SADF-006

Severity: P3
Status: open
Area: Strategist Live promotion and metric guard
Files:

- `rust/openclaw_engine/src/main_boot_tasks.rs`
- `rust/openclaw_engine/src/strategist_scheduler/mod.rs`

Summary:

The Strategist scheduler is Demo-primary today, but Live promotion and Live metrics are only scaffolded. Live metric support is guarded by `debug_assert`, not a release-mode failure.

Evidence:

See `docs/audit/strategy_agent_decision_flow.md#sadf-006`.

Impact:

Future Live scheduler enablement can restore/promote only partial expected state or learn from an empty/incorrect fill set unless the scaffold is completed first.

Recommended fix:

Before enabling Live strategist tuning, add release-mode fail-fast checks, widen Live metric filters, and add an explicit audited promotion trigger.

Verification:

Static trace only.

### MLM-001

Severity: P1
Status: open
Area: Edge predictor schema/version hash enforcement
Files:

- `rust/openclaw_engine/src/edge_predictor/features.rs`
- `rust/openclaw_engine/src/edge_predictor/ort_backend.rs`
- `program_code/ml_training/run_training_pipeline.py`
- `program_code/ml_training/onnx_exporter.py`

Summary:

The ONNX loader extracts feature definition metadata but does not compare it to runtime feature definitions, while the training pipeline stamps the definition hash as the schema hash.

Evidence:

See `docs/audit/ml_model_registry.md#mlm-001`.

Impact:

A model trained with changed feature formulas, windows, or normalization can be served against the current Rust feature builder as long as feature names and order did not change.

Recommended fix:

Compute and enforce a real feature-definition hash on both Rust and training sides, separate from the feature-name schema hash.

Verification:

Static trace only.

### MLM-002

Severity: P1
Status: open
Area: Model registry canary state / ONNX trio atomicity
Files:

- `sql/migrations/V023__model_registry.sql`
- `program_code/ml_training/model_registry.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ml_routes.py`
- `rust/openclaw_engine/src/edge_predictor/ort_backend.rs`

Summary:

`learning.model_registry` promotes one quantile row at a time, but runtime loading consumes an implicit q10/q50/q90 artifact trio derived from the q50 path.

Evidence:

See `docs/audit/ml_model_registry.md#mlm-002`.

Impact:

Registry state can mark only q50 as production while runtime inference also loads q10/q90 siblings that may remain shadow, rejected, stale, or otherwise unpromoted.

Recommended fix:

Make model registry state transitions atomic at the trio level, or store one serving-unit row containing all three artifact paths and one canary state.

Verification:

Static trace only.

### MLM-003

Severity: P1
Status: open
Area: Decision-feature schema drift in training data
Files:

- `sql/migrations/V017__edge_predictor_tables.sql`
- `rust/openclaw_engine/src/database/decision_feature_writer.rs`
- `program_code/ml_training/parquet_etl.py`
- `program_code/ml_training/quantile_trainer.py`
- `program_code/ml_training/run_training_pipeline.py`

Summary:

Training data loading ignores row-level feature schema/version/definition hashes and zero-fills missing or malformed feature keys.

Evidence:

See `docs/audit/ml_model_registry.md#mlm-003`.

Impact:

Mixed-schema or malformed decision-feature rows can silently enter current training sets, while exported ONNX metadata still advertises the current schema hash.

Recommended fix:

Filter training rows by exact schema version/hash/definition hash and reject incomplete feature JSON unless it has been explicitly migrated.

Verification:

Static trace only.

### MLM-004

Severity: P1
Status: open
Area: Label backfill finality / partial close integrity
Files:

- `program_code/ml_training/edge_label_backfill.py`

Summary:

Label backfill finalizes a decision feature row after any close fill exists, without requiring the position to be fully closed.

Evidence:

See `docs/audit/ml_model_registry.md#mlm-004`.

Impact:

Partial exits can become permanent edge labels and later close fills cannot correct the training label because `label_filled_at` excludes the row from future backfills.

Recommended fix:

Require full close quantity coverage before finalizing labels, or introduce provisional labels that are recomputed until the entry is fully closed.

Verification:

Static trace only.

### MLM-005

Severity: P1
Status: open
Area: LinUCB state persistence / reward feedback / arm-space versioning
Files:

- `rust/openclaw_engine/src/linucb/arms_v1_15.rs`
- `rust/openclaw_engine/src/linucb/runtime.rs`
- `rust/openclaw_engine/src/linucb/state_io.rs`
- `rust/openclaw_engine/src/main.rs`
- `program_code/ml_training/linucb_trainer.py`

Summary:

LinUCB does not form an end-to-end persisted reward loop: Rust cold-starts v1_15 arms, Python training defines a different v1_15 arm space, and runtime boot does not load trained state.

Evidence:

See `docs/audit/ml_model_registry.md#mlm-005`.

Impact:

Runtime selection metadata, trainer rewards, dashboard state, and database state can describe different arm spaces or vintages, and learned state may never affect runtime behavior.

Recommended fix:

Generate Rust and Python arm spaces from one manifest, fix trainer SQL placeholders, and boot the Rust runtime from the active compatible `learning.linucb_state`.

Verification:

Static trace only.

### SW-001

Severity: P1
Status: open
Area: Watchdog/restart behavior
Files:

- `helper_scripts/clean_restart.sh`
- `helper_scripts/canary/engine_watchdog.py`
- `helper_scripts/stop_all.sh`
- `helper_scripts/fresh_start.sh`
- `helper_scripts/restart_all.sh`

Summary:

`clean_restart.sh` kills services and performs flatten/archive/reset work without setting `engine_maintenance.flag`, so the external watchdog can restart the engine during the maintenance window.

Evidence:

See `docs/audit/schedulers_watchdogs.md#sw-001`.

Impact:

Trading logic can come back while positions are being flattened or runtime/DB state is being moved or truncated.

Recommended fix:

Set the maintenance flag at the start of clean restart, preserve it on failures with `trap`, and clear it only immediately before the intentional restart.

Verification:

Static trace only.

### SW-002

Severity: P1
Status: open
Area: Rust Live respawn / stale background command senders
Files:

- `rust/openclaw_engine/src/main.rs`
- `rust/openclaw_engine/src/main_boot_tasks.rs`
- `rust/openclaw_engine/src/main_pipelines.rs`
- `rust/openclaw_engine/src/live_auth_watcher.rs`

Summary:

LiveAuthWatcher respawn rotates dynamic Live command slots, but boot-time background tasks retain stale `live_cmd_tx` clones by value.

Evidence:

See `docs/audit/schedulers_watchdogs.md#sw-002`.

Impact:

After in-process Live revoke/renew respawn, reconciler, strategist promotion, or reload commands can keep targeting the old channel until a full engine restart.

Recommended fix:

Replace boot-time Live sender captures with dynamic slot-based command sinks or re-create Live-scoped background tasks on each Live respawn.

Verification:

Static trace only.

### SW-003

Severity: P2
Status: open
Area: API startup scheduler / duplicate job protection
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/evolution_auto_scheduler.py`
- `helper_scripts/restart_all.sh`
- `helper_scripts/fresh_start.sh`

Summary:

EvolutionScheduler starts in every API worker and is only process-local idempotent, so the default multi-worker deployment can run duplicate scheduler threads.

Evidence:

See `docs/audit/schedulers_watchdogs.md#sw-003`.

Impact:

Weekly evolution and hourly expiry can run once per worker, wasting compute and risking duplicate learning or ledger mutations as dependencies evolve.

Recommended fix:

Add host-local leader election or make the scheduler explicitly single-worker, plus a shutdown event and retained thread handles.

Verification:

Static trace only.

### SW-004

Severity: P2
Status: open
Area: Scheduler state persistence
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/evolution_auto_scheduler.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/experiment_ledger.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/experiment_routes.py`

Summary:

The hourly expiry scheduler marks stale hypotheses as expired, but `ExperimentLedger.expire_stale_hypotheses()` does not schedule a snapshot save.

Evidence:

See `docs/audit/schedulers_watchdogs.md#sw-004`.

Impact:

Expired hypotheses can reload as pending or running after API restart unless another unrelated ledger mutation happened to persist the snapshot.

Recommended fix:

Schedule a debounced save whenever expiry mutates state, or return expired IDs and let the scheduler request persistence.

Verification:

Static trace only.

### SW-005

Severity: P2
Status: open
Area: API startup monitoring / duplicate alert protection
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_wiring.py`
- `helper_scripts/restart_all.sh`

Summary:

`reconciler_alert_monitor()` is scheduled once per API worker and deduplicates only in local coroutine memory.

Evidence:

See `docs/audit/schedulers_watchdogs.md#sw-005`.

Impact:

One governor-tier transition can emit duplicate alerts from every API worker, reducing incident signal quality.

Recommended fix:

Elect one alert-monitor leader per host or move deduplication into a shared store, and explicitly cancel the monitor task on shutdown.

Verification:

Static trace only.

### SW-006

Severity: P2
Status: open
Area: Cron/scheduled wrapper duplicate execution
Files:

- `helper_scripts/cron_observer_cycle.sh`
- `helper_scripts/cron_daily_report.sh`
- `helper_scripts/db/counterfactual_daily_cron.sh`
- `helper_scripts/db/passive_wait_healthcheck_cron.sh`

Summary:

Cron wrappers run scheduled jobs directly without overlap locks.

Evidence:

See `docs/audit/schedulers_watchdogs.md#sw-006`.

Impact:

Long-running or hung scheduled jobs can overlap with the next cron invocation, racing on logs, snapshots, reports, or Telegram notification paths.

Recommended fix:

Add per-job nonblocking `flock` guards under a runtime lock directory, with explicit skipped-run logging and timeout handling for short-period jobs.

Verification:

Static trace only.

### SW-007

Severity: P3
Status: open
Area: API startup telemetry loop / duplicate data writer
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/grafana_data_writer.py`
- `helper_scripts/restart_all.sh`

Summary:

`GrafanaDataWriter` starts during `strategy_wiring` import in every API worker and writes legacy telemetry rows without cross-worker leader election or DB idempotency.

Evidence:

See `docs/audit/schedulers_watchdogs.md#sw-007`.

Impact:

Dashboard tables can receive one sample per worker per interval, inflating storage and distorting panels that expect one sample per time bucket.

Recommended fix:

Make the writer leader-elected, move it to a single service, or add DB idempotency for the relevant time buckets.

Verification:

Static trace only.

### DAPI-001

Severity: P1
Status: open
Area: API authorization / AI budget mutation
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ai_budget_routes.py`

Summary:

`POST /api/v1/ai_budget/config` has no authentication or operator dependency, yet updates AI budget config through Rust IPC.

Evidence:

See `docs/audit/dashboards_apis.md#dapi-001`.

Impact:

Unauthenticated callers can change AI budget limits or spoof `updated_by`, potentially disabling AI workflows or removing intended spend controls.

Recommended fix:

Require authenticated operator access and a dedicated budget-write scope; derive `updated_by` from the authenticated actor.

Verification:

Static trace only.

### DAPI-002

Severity: P2
Status: open
Area: Unauthenticated model registry observability
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ml_routes.py`

Summary:

Model registry read routes are unauthenticated direct PostgreSQL-backed endpoints that expose internal artifact paths, canary state, schema hashes, and DB error details.

Evidence:

See `docs/audit/dashboards_apis.md#dapi-002`.

Impact:

Unauthenticated callers can enumerate model inventory, active strategies/engines, filesystem paths, and database availability.

Recommended fix:

Require authenticated model/learning read scope and return generic DB error bodies while logging details server-side.

Verification:

Static trace only.

### DAPI-003

Severity: P2
Status: open
Area: Authenticated reverse proxy token leakage
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py`

Summary:

The `/openclaw/{path}` reverse proxy strips `Authorization` but forwards `Cookie`, including the HttpOnly API token cookie, to the downstream gateway host.

Evidence:

See `docs/audit/dashboards_apis.md#dapi-003`.

Impact:

The API bearer token can leak to a downstream gateway or misconfigured `OPENCLAW_GATEWAY_HOST`.

Recommended fix:

Use an outbound header allowlist and strip `Cookie` along with `Authorization`.

Verification:

Static trace only.

### DAPI-004

Severity: P2
Status: open
Area: GUI HTML authentication boundary
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/gui_legacy_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main_legacy.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/common.js`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/console.html`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/trading.html`

Summary:

Dashboard HTML routes are unauthenticated and rely on client-side redirects, but the shared redirect script is blocked by the static auth middleware when the user is unauthenticated.

Evidence:

See `docs/audit/dashboards_apis.md#dapi-004`.

Impact:

Unauthenticated users can receive the console/trading dashboard shell instead of a server-side deny or redirect.

Recommended fix:

Guard dashboard HTML routes server-side with `current_actor`, except `/login`.

Verification:

Static trace only.

### DAPI-005

Severity: P2
Status: open
Area: Unauthenticated health/DB metadata
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/system_legacy_routes.py`

Summary:

`GET /api/v1/health/db` is unauthenticated and returns PostgreSQL pool stats plus raw probe exception text.

Evidence:

See `docs/audit/dashboards_apis.md#dapi-005`.

Impact:

Unauthenticated callers can probe DB availability and internal error details beyond the minimal public liveness route.

Recommended fix:

Require authentication for detailed DB health, or reduce the public response to minimal liveness.

Verification:

Static trace only.

### DAPI-006

Severity: P2
Status: open
Area: Inconsistent write-route authorization model
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/auth.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main_legacy.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/control_legacy_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/risk_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_write_routes.py`

Summary:

The code defines a scope-plus-operator-identity contract for writes, but many state-changing routes use only authentication and do not enforce route-specific roles/scopes.

Evidence:

See `docs/audit/dashboards_apis.md#dapi-006`.

Impact:

Authorization is inconsistent and easy to regress; valid tokens can reach operational mutations unless each handler manually adds the correct guard.

Recommended fix:

Move write authorization into reusable FastAPI dependencies by route family and derive audit identity server-side.

Verification:

Static trace only.

### DAPI-007

Severity: P2
Status: open
Area: API-side scheduled restart process control
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/control_legacy_routes.py`
- `helper_scripts/restart_all.sh`

Summary:

`POST /api/v1/system/scheduled-restart` kills only the handling process PID and launches a standalone uvicorn command instead of routing through the normal service manager/restart script.

Evidence:

See `docs/audit/dashboards_apis.md#dapi-007`.

Impact:

In multi-worker deployment it can kill one worker, let the parent respawn it, and start an unmanaged duplicate or failed standalone server with missing environment/worker/log settings.

Recommended fix:

Remove in-process shell restart or replace it with an operator-only service-manager intent handled by the watchdog/restart tooling.

Verification:

Static trace only.

### OS-001

Severity: P1
Status: open
Area: Live exchange flattening
Files:

- `helper_scripts/clean_restart.sh`
- `helper_scripts/fresh_start.sh`
- `helper_scripts/clean_restart_flatten.py`

Summary:

The clean/fresh restart live-flatten path can cancel mainnet orders and place reduce-only mainnet market orders through the Python Bybit REST client without checking the signed Live authorization/global-mode control plane.

Evidence:

See `docs/audit/operator_scripts.md#os-001`.

Impact:

An operator command or automation with live credentials and `OPENCLAW_ALLOW_MAINNET=1` can mutate mainnet exchange state outside the Rust live engine, signed `authorization.json`, `live_reserved` global-mode checks, and normal order audit path.

Recommended fix:

Route live flattening through the signed live-control boundary, require current live authorization/global mode, and require a second non-skippable mainnet confirmation plus dry-run position plan.

Verification:

Static trace only.

### OS-002

Severity: P1
Status: open
Area: Destructive DB reset scripts
Files:

- `helper_scripts/fresh_start.sh`
- `helper_scripts/db/fresh_start_reset.py`
- `helper_scripts/clean_restart.sh`
- `helper_scripts/db/cleanup_v026_partial_state.sh`

Summary:

Destructive DB reset paths can run against the configured local database without a production/environment guard, and `fresh_start.sh --yes` auto-generates the confirmation token that the reset helper was meant to require.

Evidence:

See `docs/audit/operator_scripts.md#os-002`.

Impact:

A wrong shell environment, stale secrets root, pasted command, or automation run can wipe durable trading/learning/audit history in the wrong database.

Recommended fix:

Require explicit target environment/database identity checks and a typed DB-specific confirmation token that wrappers cannot generate automatically; keep dry-run as the default for standalone cleanup.

Verification:

Static trace only.

### OS-003

Severity: P2
Status: open
Area: Process control
Files:

- `helper_scripts/restart_all.sh`
- `helper_scripts/stop_all.sh`
- `helper_scripts/clean_restart.sh`
- `helper_scripts/fresh_start.sh`

Summary:

Lifecycle scripts identify processes by broad command-line substrings and kill any process listening on port 8000, not just processes owned by this repo instance.

Evidence:

See `docs/audit/operator_scripts.md#os-003`.

Impact:

A second checkout, a different Uvicorn app, or a service-manager-controlled instance can be killed by manual lifecycle scripts.

Recommended fix:

Use PID files, service-manager labels, or executable/cwd validation before killing; prefer systemd/launchd for managed services.

Verification:

Static trace only.

### OS-004

Severity: P2
Status: open
Area: Maintenance flag recovery
Files:

- `helper_scripts/fresh_start.sh`

Summary:

`fresh_start.sh` creates the watchdog maintenance flag but does not protect cleanup with an `EXIT`/`ERR`/signal trap, so unexpected failures can leave watchdog recovery disabled.

Evidence:

See `docs/audit/operator_scripts.md#os-004`.

Impact:

If the script is interrupted or fails outside explicitly handled branches, `engine_maintenance.flag` can remain in place while engine/API are down and the watchdog avoids restart.

Recommended fix:

Install a cleanup trap or convert the flag to a TTL-scoped maintenance lease with stale-maintenance alerting.

Verification:

Static trace only.

### OS-005

Severity: P2
Status: open
Area: macOS launchd deployment
Files:

- `helper_scripts/deploy/README.md`
- `helper_scripts/deploy/com.openclaw.engine.plist`
- `helper_scripts/deploy/com.openclaw.trading-api.plist`
- `helper_scripts/deploy/com.openclaw.gateway.plist`

Summary:

The macOS deployment runbook loads launchd services before injecting required secrets/env, and the templates do not include an installer/preflight that rejects missing values or placeholder provider keys.

Evidence:

See `docs/audit/operator_scripts.md#os-005`.

Impact:

Services can start with missing DB/IPC/provider environment, leading to failed startup, fallback behavior, stale auth/IPC assumptions, or placeholder credentials.

Recommended fix:

Add an installer/doctor that sets and verifies launchd env before load, rejects placeholders, and refuses service start on env mismatch.

Verification:

Static trace only.

### OS-006

Severity: P2
Status: open
Area: Database bootstrap privilege and SQL construction
Files:

- `helper_scripts/mac_bootstrap_db.sh`

Summary:

The macOS DB bootstrap creates the application role as PostgreSQL `SUPERUSER` and interpolates the password directly into an SQL string without SQL literal escaping.

Evidence:

See `docs/audit/operator_scripts.md#os-006`.

Impact:

Any runtime/API compromise of `trading_admin` becomes a cluster-level DB compromise on this deployment path, and passwords containing a single quote can break or alter bootstrap SQL.

Recommended fix:

Use separate owner/migration/runtime roles and safe password quoting through `psql` variables or a trusted SQL-literal helper.

Verification:

Static trace only.

### OS-007

Severity: P3
Status: open
Area: Daily report cron robustness
Files:

- `helper_scripts/cron_daily_report.sh`

Summary:

The daily Telegram report builds JSON by shell string interpolation and places the bot token in the curl URL argument.

Evidence:

See `docs/audit/operator_scripts.md#os-007`.

Impact:

Quotes, backslashes, or newlines in report content can produce invalid JSON or malformed Markdown, and the tokenized URL can be visible in process arguments while curl runs.

Recommended fix:

Build the payload with `jq -n` or Python JSON encoding and avoid putting the tokenized URL in argv.

Verification:

Static trace only.

## Open Questions

- Should `docs/audits/` be treated as historical evidence for this audit, or only as background?
- Should the committed monitoring bearer credential be assumed live and rotated outside this audit?
- Should generated reports and old worktree artifacts under `.claude*` and `.codex*` be excluded from the authoritative manifest?

## Inventory Result

First audit segment completed on 2026-04-28.

In-scope categories:

- runtime code: 696
- deployment/configuration: 55
- operator scripts: 65
- migration/schema: 28

Risk buckets for in-scope files:

- P0 candidate: 442
- P1 candidate: 107
- P2 candidate: 295

These are path-based planning buckets, not confirmed findings.

## Entry Point Result

Second audit segment completed on 2026-04-28.

Generated artifacts:

- `docs/audit/entry_points_services.md`
- `docs/audit/entry_points_manifest.tsv`

Entry-point records:

- total records: 238
- Rust binary entry points: 1
- FastAPI app entry points: 3
- FastAPI routers: 23
- API startup background tasks: 5
- launchd services: 4
- Docker Compose services: 6
- shell script entry points: 34
- Python CLI entry points: 162

Primary service-level entry points:

- `rust/openclaw_engine/src/main.rs`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py`
- `helper_scripts/restart_all.sh`
- `helper_scripts/stop_all.sh`
- `helper_scripts/deploy/com.openclaw.engine.plist`
- `helper_scripts/deploy/com.openclaw.trading-api.plist`
- `helper_scripts/deploy/com.openclaw.engine-watchdog.plist`

The entry-point map is a routing and prioritization artifact. It does not record confirmed findings.

## Live/Paper Mode Separation Result

Third audit segment completed on 2026-04-28.

Generated artifact:

- `docs/audit/live_paper_mode_separation.md`

Reviewed boundary areas:

- Rust Live authorization HMAC contract
- Rust live/demo/paper pipeline startup and slot teardown behavior
- API live session and live trust routes
- Paper startup and disabled-by-default behavior
- Restart, clean reset, fresh reset, and exchange flatten scripts
- Docker token default handling

Confirmed findings:

- LP-001: Live auth renewal bypasses exact global-mode gate.
- LP-002: Clean/fresh restart scripts use the wrong Cargo package ID for rebuild.
- LP-003: Paper auto-start script is stale against current Rust/Python behavior.

## Order Execution And Reconciliation Result

Fourth audit segment completed on 2026-04-28.

Generated artifact:

- `docs/audit/order_execution_reconciliation.md`

Reviewed boundary areas:

- Rust exchange order dispatch and retry behavior
- Bybit private WS order, execution, position, wallet, and DCP event handling
- Fill attribution, duplicate suppression, and DB persistence
- Pending order and pending close cleanup
- API close-position, close-all, and orphan sweep behavior
- Trading writer durability for intents, fills, orders, order state changes, and risk verdicts

Confirmed findings:

- OE-001: Private WS batch payloads drop all but the first parsed item.
- OE-002: Dispatch and close enqueue failures can leave false `Working` or pending-close state.
- OE-003: Trading DB writer clears buffers after failed batch inserts.
- OE-004: Attributed exchange fills do not use Bybit `exec_id` as the durable key.
- OE-005: Fill-before-order-update fallback can match the wrong same-side pending order.
- OE-006: Close order timeout budget is materially longer than the retry comments imply.
- OE-007: Live close REST fallback can mutate exchange state while the live engine/channel is unavailable.
- OE-008: Close-all/session-stop responses can report success on partial failure.
- OE-009: Risk verdict schema fields are not populated by the writer.

## Risk Controls And Kill Switches Result

Fifth audit segment completed on 2026-04-28.

Generated artifact:

- `docs/audit/risk_controls_kill_switches.md`

Reviewed boundary areas:

- Per-engine risk config loading and fail-safe defaults
- Runtime risk config mutation through `patch_risk_config` and legacy `update_risk_config`
- H0 gate risk snapshot, cooldown, and kill-switch fields
- Fast-track, pause-gate, H0 hard-block, and Step 6 emergency close paths
- Risk governor tier transitions, auth cascade, and order admission enforcement
- API routes that mutate risk config, cooldown, unhalt, pause/resume, and close-all state

Confirmed findings:

- RC-001: H0 hard-block stops and fast-track CloseAll locally flatten without exchange close dispatch.
- RC-002: H0 cooldown and kill-switch fields are overwritten by the periodic status snapshot.
- RC-003: Mutating risk routes lack operator role enforcement.
- RC-004: Missing live risk config falls back to defaults with H0 shadow mode enabled.
- RC-005: Risk governor tier constraints/cascade are not consistently enforced at runtime.
- RC-006: Legacy `update_risk_config` IPC reports success before application and ignores send failure.

## Secrets And Credentials Result

Sixth audit segment completed on 2026-04-28.

Generated artifact:

- `docs/audit/secrets_credentials.md`

Reviewed boundary areas:

- Control API bearer token lifecycle, actor construction, and GUI auth cookie issuance
- GUI username/password loading and login validation
- Bybit demo/live API key slot loading in Python and Rust
- Live authorization HMAC payload verification and IPC HMAC enforcement
- Docker, launchd, and operator script secret propagation
- Monitoring service credentials and anonymous access configuration
- Git ignore coverage for env files, secret files, and generated token state

Confirmed findings:

- SC-001: Control API can print an auto-generated operator-capable bearer token to logs.
- SC-002: GUI login can accept an empty password when `GUI_PASSWORD` is missing or blank.
- SC-003: Grafana FastAPI datasource provisioning contains a committed literal bearer credential.
- SC-004: Monitoring compose publishes Grafana with a repository-known admin password and anonymous Viewer enabled.
- SC-005: Operator scripts propagate high-value secrets through process argv/env.
- SC-006: Gateway launchd plist template invites provider API keys to be written into the repo tree.
- SC-007: Auth cookie `Secure` depends only on the observed request scheme.

## Database Migrations And Writes Result

Seventh audit segment completed on 2026-04-28.

Generated artifact:

- `docs/audit/database_migrations_writes.md`

Reviewed boundary areas:

- SQL migration ordering, guard coverage, and runtime migration application paths
- Rust auto-migration tracking through `_sqlx_migrations`
- Rust DB pool fail-soft behavior and writer task startup
- Trading, market, decision-context, decision-feature, exit-feature, shadow-fill, and shadow-exit writers
- Paper-state checkpoint restore, write, and delete paths
- API-side psycopg2 pool lifecycle and state-changing DB writes
- Operator migration scripts and schema audit tooling

Confirmed findings:

- DBW-001: Active `learning.exit_features` schema is stuck in a `V999` migration excluded by production migration paths.
- DBW-002: Critical DB producer paths silently drop rows when bounded channels are full or closed.
- DBW-003: Non-market writers drain/clear rows on DB failure without durable retry or fallback.
- DBW-004: API PG pool can return aborted or idle transactions without rollback/reset.
- DBW-005: Explicit auto-migrate can skip as `NoPool` and still be logged as completed.

## Strategy And Agent Decision Flow Result

Eighth audit segment completed on 2026-04-28.

Generated artifact:

- `docs/audit/strategy_agent_decision_flow.md`

Reviewed boundary areas:

- Strategy signal generation and active-strategy dispatch
- Open intent construction, sizing, risk, predictor, and cost-gate behavior
- Close-intent bypass behavior for risk-reducing actions
- Strategy parameter TOML loading, hot mutation, and snapshot persistence
- LinUCB and decision-context metadata wiring
- Strategist scheduler DB restore, Demo tuning, and Live promotion scaffolding
- Claude Teacher directive routing, application, and execution audit rows

Confirmed findings:

- SADF-001: Teacher directives are routed to the disabled Paper drain by default.
- SADF-002: Mixed strategy parameter updates can partially mutate `conf_scale` on validation failure.
- SADF-003: Demo/Live strategy config load errors fail open to default-active strategies.
- SADF-004: LinUCB metadata is observation-only and not tied to accepted order intents.
- SADF-005: `boost_arm` is persisted as successful even though it is a no-op stub.
- SADF-006: Strategist Live promotion and Live metrics remain scaffolded and require release-mode guards before enablement.

## ML And Model Registry Result

Ninth audit segment completed on 2026-04-28.

Generated artifact:

- `docs/audit/ml_model_registry.md`

Reviewed boundary areas:

- Edge predictor feature capture, ONNX trio loading, null fallback, hot swap, and model age gates
- `learning.model_registry` schema, Python registration/promote flows, Control API resolver routes, and Rust resolver context
- Decision-feature writes, label backfill, training-data loading, quantile ONNX export, and artifact registration
- LinUCB arm-space definitions, runtime selection, PG state IO, batch reward trainer, and active-version scaffolding
- Shadow, decision-feature, and label integrity for training rows

Confirmed findings:

- MLM-001: Edge predictor does not enforce feature definition hash compatibility.
- MLM-002: Model registry promotion is per quantile, but runtime loads an implicit q10/q50/q90 trio.
- MLM-003: Training data loader ignores row-level decision-feature schema/hash metadata and zero-fills drift.
- MLM-004: Label backfill can finalize training labels on partial closes.
- MLM-005: LinUCB runtime, trainer, and state persistence have arm-space and reward-query drift.

## Schedulers And Watchdogs Result

Tenth audit segment completed on 2026-04-28.

Generated artifact:

- `docs/audit/schedulers_watchdogs.md`

Reviewed boundary areas:

- Rust background tasks, cancellation, shutdown, LiveAuthWatcher respawn, and dynamic command slots
- FastAPI startup background tasks, daemon threads, multi-worker duplicate protection, and shutdown cleanup
- External engine watchdog, launchd templates, and restart/clean/fresh scripts
- Cron and scheduled shell wrappers
- Scheduler state persistence for ExperimentLedger and edge-estimator flows

Confirmed findings:

- SW-001: `clean_restart.sh` does not set the watchdog maintenance flag before its maintenance window.
- SW-002: LiveAuthWatcher respawn leaves boot-time Live background senders stale.
- SW-003: EvolutionScheduler can start once per API worker.
- SW-004: ExperimentLedger expiry state is not persisted.
- SW-005: Reconciler alert monitor can emit duplicate multi-worker alerts.
- SW-006: Cron wrappers have no overlap locks.
- SW-007: GrafanaDataWriter can duplicate legacy telemetry per API worker.

## Dashboards And APIs Result

Eleventh audit segment completed on 2026-04-28.

Generated artifact:

- `docs/audit/dashboards_apis.md`

Reviewed boundary areas:

- FastAPI app composition, router registration, auth dependencies, and role/scope checks
- State-changing endpoints for AI budget, paper/session controls, strategy/risk config, scheduled restart, model registry, live/trust, governance, experiments, backtests, and evolution
- Dashboard HTML/static auth behavior and GUI fetch assumptions
- Database/model/health dashboard read routes
- API-side process, proxy, file, and shell command surfaces

Confirmed findings:

- DAPI-001: AI budget config write route is unauthenticated.
- DAPI-002: Model registry read routes are unauthenticated and expose internal model/DB metadata.
- DAPI-003: `/openclaw/*` proxy forwards the HttpOnly auth cookie downstream.
- DAPI-004: Dashboard HTML routes are server-side unauthenticated and their client redirect can be blocked.
- DAPI-005: Detailed DB health route is unauthenticated.
- DAPI-006: Multiple write routes bypass the scope-plus-identity authorization contract.
- DAPI-007: Scheduled restart endpoint launches an unmanaged uvicorn process from an API worker.

## Operator Scripts Result

Twelfth audit segment completed on 2026-04-28.

Generated artifact:

- `docs/audit/operator_scripts.md`

Reviewed boundary areas:

- Restart, stop, clean restart, fresh start, and exchange flatten scripts
- Destructive DB reset, archive/truncate, migration cleanup, and migration apply wrappers
- Environment and secret assumptions in shell, cron, launchd, and bootstrap paths
- launchd deployment templates and manual install runbook ordering
- Process matching, maintenance flags, dry-run behavior, and operator prompts

Confirmed findings:

- OS-001: Live flatten scripts can mutate mainnet exchange state outside signed live-control/global-mode checks.
- OS-002: Destructive DB reset paths lack a target-environment guard and can be auto-confirmed.
- OS-003: Lifecycle scripts use broad process-name and port-based kills.
- OS-004: `fresh_start.sh` maintenance flag cleanup is not trap-protected.
- OS-005: launchd runbook can load services before required env injection and placeholder validation.
- OS-006: macOS DB bootstrap creates `trading_admin` as `SUPERUSER` and unsafely constructs password SQL.
- OS-007: Daily Telegram report builds JSON by shell interpolation and exposes the tokenized URL in argv.

## Final Synthesis Result

Completed on 2026-04-28.

Generated artifacts:

- `docs/audit/remediation_groups.md`
- `docs/audit/final_summary.md`
- `docs/audit/final_record_zh.md`

Completed synthesis work:

- De-duplicated overlapping findings across audit segments into remediation workstreams.
- Ranked remediation by live-money, data-integrity, and operational blast radius.
- Grouped fixes into release blockers, quick wins, architectural repairs, and monitoring candidates.
- Produced final English summary and complete Chinese final record.

## Next Step

Audit is complete. Next work should move into remediation execution planning: split Batch A-F from `docs/audit/final_record_zh.md` into tickets, assign owners, add regression tests, and define release gates.
