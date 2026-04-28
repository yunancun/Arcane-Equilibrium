# Database Migrations and Writes Audit

Created: 2026-04-28
Status: complete for this audit slice
Scope: SQL migrations, migration runners, PostgreSQL pool lifecycle, Rust runtime writers for market/trading/learning/observability state, paper-state checkpoint restore/write paths, API-side PostgreSQL writes, and operator migration scripts.

## Scope Note

This slice is a static audit. It did not connect to the live database or inspect production data. Tests under `sql/migrations/tests/` and Rust/Python test modules were treated only as context, not as audit scope.

## Flow Summary

Schema changes live under `sql/migrations/V*.sql`. Runtime application has three paths: Linux `helper_scripts/linux_bootstrap_db.sh`, Mac `helper_scripts/mac_bootstrap_db.sh`, and the opt-in Rust auto-migrator behind `OPENCLAW_AUTO_MIGRATE=1`.

The Rust engine uses a `DbPool` wrapper around `sqlx::PgPool`. It starts writer tasks for market data, trading lifecycle rows, decision contexts, decision features, shadow fills, exit features, shadow exits, data quality, drift, LinUCB/features, AI budget, outcome backfill, and cost-edge advisor logs. Most hot-path producers use bounded channels and `try_send` to avoid blocking trading.

The API uses a separate psycopg2 `ThreadedConnectionPool` for dashboards, route reads, and a few state-changing writes such as weekly review approval and service feedback.

## Confirmed Findings

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

`learning.exit_features` is an active runtime table, but its only migration remains named `V999__exit_features.sql` and is excluded by the Linux migration applier, the migration audit tool, and the Rust auto-migrator.

Evidence:

- `V999__exit_features.sql:6-9` says the file is a placeholder that should be renumbered before merge, while `:24-78` creates the active `learning.exit_features` table and indexes.
- `migrations.rs:249-267` treats all `V999` files as test-only fixtures and rejects them from auto-migrate; the unit test at `migrations.rs:597-602` pins rejection of `V999__exit_features.sql`.
- `linux_bootstrap_db.sh:90-91` excludes `^V999`, and `audit_migrations.py:232-238` also skips `V999`.
- The exit-feature writer inserts directly into `learning.exit_features` at `exit_feature_writer.rs:119-127`.
- The close path emits `ExitFeatureRow` through the writer channel at `pipeline_helpers.rs:251-273`.

Impact:

Fresh Linux deployments and any database relying on Rust auto-migrate will not create `learning.exit_features`. Close-path label writes then fail at runtime and are dropped after the writer drains the pending row, leaving Track P/L exit labels, counterfactual tooling, and healthchecks incomplete.

Reproduction or trigger:

Run the Linux migration applier or enable `OPENCLAW_AUTO_MIGRATE=1` on a database that has not manually applied `V999__exit_features.sql`, then trigger a close that emits an exit feature row.

Recommended fix:

Rename `V999__exit_features.sql` to the next real migration number, update migration manifests/tools, and add a startup schema guard that fails loudly when `learning.exit_features` is missing while the exit-feature writer is wired.

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

High-value trading and learning rows are sent through bounded channels with `try_send`, but many call sites ignore the error. Channel-full or closed-channel conditions silently drop rows before they reach any writer or fallback path.

Evidence:

- Writer channels are bounded: trading `4096`, decision context/features/shadow-fill/exit-feature `1024`, shadow-exit `512` in `tasks.rs:381-501`.
- Risk verdict and intent persistence ignore `try_send` results at `on_tick_helpers.rs:159-171` and `:187-225`.
- Close fills and exit feature rows ignore `try_send` results at `pipeline_helpers.rs:173-192` and `:265-273`.
- Order and order-state persistence ignores `try_send` results at `loop_handlers.rs:217-230`, `:559-571`, and `:702-710`.
- IPC/external fill paths ignore `try_send` results at `commands.rs:248-262` and `:530-548`.

Impact:

During DB writer lag, scheduler stalls, bursty exchange events, or a crashed writer task, fills, orders, order state changes, risk verdicts, intents, and exit labels can disappear without a metric or retry. This creates durable audit gaps even when the in-memory trading state continues.

Reproduction or trigger:

Fill a writer channel faster than its consumer can drain, or close the receiver task, then execute a path that calls `try_send` and discards the result.

Recommended fix:

Centralize DB producer send helpers. For critical trading lifecycle rows, either await bounded `send` with a tight timeout, or synchronously enqueue to a durable local outbox/JSONL fallback. At minimum, count and log dropped rows per table and expose them in health/status endpoints.

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

Only the market writer has a real JSONL fallback. Other runtime writers clear or drain pending rows on pool unavailability or insert failure, so transient DB outages and schema drift lose durable trading and learning records.

Evidence:

- `batch_insert.rs:121-192` executes chunks and only records failure; it does not retry or return failed rows to the caller.
- `trading_writer.rs:168-211`, `:276-350`, `:535-638` clear buffers after `batch_insert_chunked`, even if one or more chunks failed.
- `context_writer.rs:71-77` clears pending rows when unavailable and drains rows before insert.
- `decision_feature_writer.rs:76-82` clears/drains pending rows before insert.
- `exit_feature_writer.rs:93-104` clears or drains pending rows before insert; failed rows are only logged at `:175-180`.
- `shadow_fill_writer.rs:94-98` clears/drains pending rows before insert, and `shadow_exit_writer.rs:127-131` clears pending on pool unavailability.
- `market_writer.rs:57-144` is the only reviewed writer path that constructs `FallbackWriter` and writes JSONL fallback records.

Impact:

A short DB outage, a missing migration, a constraint error, or a dead connection can permanently drop fills, orders, risk verdicts, decision contexts, decision features, exit features, and shadow observations. This overlaps OE-003 but is broader than the trading writer alone.

Reproduction or trigger:

Make PostgreSQL unavailable or remove a target table, allow rows to accumulate, then let any non-market writer flush.

Recommended fix:

Move retry/fallback ownership into a shared writer abstraction. Failed rows should remain pending, be retried with bounded backoff, or be written to a durable local outbox that can be replayed. Table-specific writers should return success/failure rather than clearing buffers unconditionally.

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

The API pool's `put_conn()` returns psycopg2 connections without rollback/reset. The `get_pg_conn()` context manager does rollback, but many callers use `get_conn()` directly, and at least one write path catches exceptions and returns the connection without rollback.

Evidence:

- `db_pool.py:115-120` calls `_pool.putconn(conn)` without rollback or reset.
- `db_pool.py:124-145` shows the context manager does rollback before returning a connection, which is the safer path.
- `_update_weekly_review()` uses `db_pool.get_conn()` directly at `phase4_routes.py:785-789`, commits on success at `:805-806`, but on exception logs and returns at `:815-817` before `finally` returns the connection at `:818-819`; there is no rollback in that exception path.
- Other writers such as `bybit_demo_sync.py:149-168` and `grafana_data_writer.py:166-184` explicitly rollback on exception, showing the expected pattern is known but not enforced centrally.

Impact:

A failed statement can leave an aborted transaction in the pool, causing later borrowers to fail with transaction-aborted errors. Even successful read-only callers that return connections without commit/rollback can leave idle transactions and long-lived snapshots, which can interfere with vacuum and operational diagnostics.

Reproduction or trigger:

Cause `_update_weekly_review()` to hit a database error after borrowing a pooled connection, then reuse that same connection for a subsequent request.

Recommended fix:

Make `put_conn()` defensively rollback before returning any connection, or require all callers to use `get_pg_conn()`. Consider enabling autocommit for API read pools and using a separate explicit transaction helper for writes.

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

When `OPENCLAW_AUTO_MIGRATE=1` is explicitly enabled but the database pool is unavailable, the migration runner returns `Ok(NoPool)` and `main` logs the runner as completed. The startup-abort behavior only applies to actual migration errors after a pool exists.

Evidence:

- `DbPool::connect()` returns a disconnected pool instead of an error when the URL is empty, writes are disabled, or connection fails at `pool.rs:30-77`.
- `MigrationRunner::run_if_enabled()` returns `Ok(RunOutcome::NoPool)` when the provided pool is `None` at `migrations.rs:145-150`.
- `main.rs:580-588` treats any `Ok(outcome)` as runner completed; only `Err(e)` aborts startup at `main.rs:590-596`.

Impact:

Operators can believe auto-migration is active while a DB connection failure caused it to skip. In a live or production-like environment this means schema drift and disabled DB writes are tolerated at startup even though the env var was set to make migration state loud.

Reproduction or trigger:

Set `OPENCLAW_AUTO_MIGRATE=1` with a configured but unreachable database, then start the engine.

Recommended fix:

Treat `NoPool` as fatal when auto-migrate is explicitly enabled and DB writes are configured, especially outside local paper-only runs. If optional DB operation is still required, require a separate `OPENCLAW_ALLOW_DBLESS=1` escape hatch and surface the degraded state in health endpoints.

Verification:

Static trace only.

## Controls Confirmed

- The Rust auto-migrator sorts eligible `V###__*.sql` files, detects duplicate versions, uses advisory locking through `sqlx::Migrator`, and refuses ambiguous partial legacy state.
- Several late migrations add schema guards for known `CREATE TABLE IF NOT EXISTS` silent-noop risks, including V021, V023, V024, V026, and V027.
- `trading.paper_state_checkpoint` has a single-row-per-engine schema and runtime code that restores peak drawdown state after `restore_from_db`.
- Funding settlements are separated from ordinary order fills in V027 and through `TradingMsg::FundingSettlement`.
- Market writer has parameter chunking and JSONL fallback, which is the strongest reviewed write durability pattern.
- API write paths that use the `get_pg_conn()` context manager get automatic rollback on return.

## Files Reviewed

- `sql/migrations/README.md`
- `sql/migrations/V001__create_schemas.sql`
- `sql/migrations/V002__market_tables.sql`
- `sql/migrations/V003__trading_agent_tables.sql`
- `sql/migrations/V004__learning_features_obs_risk_tables.sql`
- `sql/migrations/V005__indexes_views.sql`
- `sql/migrations/V006__timescaledb_policies.sql`
- `sql/migrations/V009__phase4_ml_news_tables.sql`
- `sql/migrations/V010__ai_budget_and_linucb_versioning.sql`
- `sql/migrations/V011__foundation_model_features.sql`
- `sql/migrations/V014__engine_events.sql`
- `sql/migrations/V015__engine_mode_separation.sql`
- `sql/migrations/V017__edge_predictor_tables.sql`
- `sql/migrations/V018__paper_state_checkpoint.sql`
- `sql/migrations/V019__strategist_applied_params.sql`
- `sql/migrations/V021__fills_exit_source.sql`
- `sql/migrations/V023__model_registry.sql`
- `sql/migrations/V024__guard_v019_v020_strategist_applied_params.sql`
- `sql/migrations/V025__outcome_backfill_pending_index.sql`
- `sql/migrations/V026__cost_edge_advisor_log.sql`
- `sql/migrations/V027__funding_settlements.sql`
- `sql/migrations/V999__exit_features.sql`
- `helper_scripts/linux_bootstrap_db.sh`
- `helper_scripts/mac_bootstrap_db.sh`
- `helper_scripts/db/audit_migrations.py`
- `helper_scripts/db/deploy_V018.sh`
- `rust/openclaw_engine/src/database/mod.rs`
- `rust/openclaw_engine/src/database/pool.rs`
- `rust/openclaw_engine/src/database/migrations.rs`
- `rust/openclaw_engine/src/database/batch_insert.rs`
- `rust/openclaw_engine/src/database/market_writer.rs`
- `rust/openclaw_engine/src/database/trading_writer.rs`
- `rust/openclaw_engine/src/database/context_writer.rs`
- `rust/openclaw_engine/src/database/decision_feature_writer.rs`
- `rust/openclaw_engine/src/database/shadow_fill_writer.rs`
- `rust/openclaw_engine/src/database/exit_feature_writer.rs`
- `rust/openclaw_engine/src/database/shadow_exit_writer.rs`
- `rust/openclaw_engine/src/database/outcome_backfiller.rs`
- `rust/openclaw_engine/src/database/feature_writer.rs`
- `rust/openclaw_engine/src/database/quality_writer.rs`
- `rust/openclaw_engine/src/database/drift_detector.rs`
- `rust/openclaw_engine/src/paper_state/checkpoint.rs`
- `rust/openclaw_engine/src/event_consumer/bootstrap.rs`
- `rust/openclaw_engine/src/event_consumer/loop_handlers.rs`
- `rust/openclaw_engine/src/event_consumer/paper_state_restore.rs`
- `rust/openclaw_engine/src/event_consumer/funding_settlement.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick_helpers.rs`
- `rust/openclaw_engine/src/tick_pipeline/pipeline_helpers.rs`
- `rust/openclaw_engine/src/tick_pipeline/commands.rs`
- `rust/openclaw_engine/src/main.rs`
- `rust/openclaw_engine/src/tasks.rs`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/db_pool.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/phase4_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_demo_sync.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/grafana_data_writer.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ai_service_feedback.py`
