# E1(worker) — Phase 1b B-2A V094 Schema + Writer

Date: 2026-05-16
Bound role: E1(worker)
Scope: V094 audit persistence only. No deploy, no production SQL apply, no close-maker dispatch behavior.

## Summary

Implemented the V094 audit persistence foundation:

- Added `sql/migrations/V094__fills_close_maker_audit.sql` with `close_maker_attempt`, `close_maker_fallback_reason`, 10-value NOT VALID CHECK enum, partial index, and Guard A/B/C.
- Extended `TradingMsg::Fill` with `details`, `close_maker_attempt`, and `close_maker_fallback_reason`.
- Upgraded `trading_writer.rs` from 23 to 26 fill columns and binds `details`, `close_maker_attempt`, and `close_maker_fallback_reason`.
- Migrated compile-relevant Fill emitters to cold defaults: `details=None`, `close_maker_attempt=false`, `close_maker_fallback_reason=None`.
- Added focused writer payload tests and static V094 migration tests.

`commands.rs` changes were strictly minimal caller/signature migration at two fill emit sites. I did not implement the close-maker classifier, whitelist, PostOnly dispatch, fallback, or dynamic backoff behavior there.

## Files I Changed

- `sql/migrations/V094__fills_close_maker_audit.sql`
- `tests/migrations/test_v094_fills_close_maker_audit.py`
- `rust/openclaw_engine/src/database/mod.rs`
- `rust/openclaw_engine/src/database/trading_writer.rs`
- `rust/openclaw_engine/src/event_consumer/unattributed_emit.rs`
- `rust/openclaw_engine/src/tick_pipeline/commands.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`
- `rust/openclaw_engine/src/tick_pipeline/pipeline_helpers.rs`

Shared memory was not updated because this dispatch explicitly forbids shared memory edits.

## Parallel Work Observed

While this task was in progress, sibling work modified files outside my scope, including:

- `helper_scripts/db/passive_wait_healthcheck/__init__.py`
- `helper_scripts/db/passive_wait_healthcheck/runner.py`
- `helper_scripts/db/passive_wait_healthcheck/checks_close_maker_audit.py`
- `helper_scripts/db/test_close_maker_audit_healthcheck.py`
- `rust/openclaw_engine/src/strategies/maker_rejection.rs`
- `rust/openclaw_engine/src/strategies/grid_trading/*`

I did not revert, stage, stash, or edit those sibling changes. One transient Rust test compile attempt failed while the sibling `close_maker_backoff` field was only partially wired; a later re-run passed after the sibling constructor updates appeared.

## Verification

Passed:

```bash
cargo check -q --lib
```

Result: PASS, with pre-existing warnings in `btc_lead_lag/db_writer.rs` and `ma_crossover/helpers.rs`.

```bash
cargo test -q --lib database::trading_writer::tests
```

Result: PASS, `12 passed; 0 failed`.

```bash
./venvs/mac_dev/bin/python -m pytest tests/migrations/test_v094_fills_close_maker_audit.py -q
```

Result: PASS, `5 passed`.

```bash
rustfmt --edition 2021 --check \
  rust/openclaw_engine/src/database/mod.rs \
  rust/openclaw_engine/src/database/trading_writer.rs \
  rust/openclaw_engine/src/tick_pipeline/pipeline_helpers.rs \
  rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs \
  rust/openclaw_engine/src/event_consumer/unattributed_emit.rs
```

Result: PASS. I did not run rustfmt write mode. `cargo fmt --check` is not usable as a clean gate in the current tree because it reports broad pre-existing formatting drift outside this task; `commands.rs` also has rustfmt drift outside my added lines.

Static guard greps:

```bash
rg -n "(linucb|scorer|quantile|mlde|dl3).*close_maker_(attempt|fallback_reason|initial_limit|final_fill|eligible_reason)" program_code rust helper_scripts tests
```

Result: no matches.

```bash
rg -n "OPENCLAW_ENABLE_PAPER=1|allLiquidation|OPENCLAW_ALLOW_MAINNET|phys_lock.*live|live.*phys_lock" \
  sql/migrations/V094__fills_close_maker_audit.sql \
  tests/migrations/test_v094_fills_close_maker_audit.py \
  rust/openclaw_engine/src/database/mod.rs \
  rust/openclaw_engine/src/database/trading_writer.rs \
  rust/openclaw_engine/src/event_consumer/unattributed_emit.rs \
  rust/openclaw_engine/src/tick_pipeline/commands.rs \
  rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs \
  rust/openclaw_engine/src/tick_pipeline/pipeline_helpers.rs
```

Result: no matches.

## Linux PG Dry-Run SOP

Not run by E1 in this source/test task. For E4/PM on `trade-core`, use a transaction and rollback so production schema is not changed during dry-run.

Round 1:

```bash
ssh trade-core 'cd ~/BybitOpenClaw/srv && psql "$OPENCLAW_TRADING_DB_DSN" -v ON_ERROR_STOP=1' <<'SQL'
BEGIN;
\i sql/migrations/V094__fills_close_maker_audit.sql

SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema='trading' AND table_name='fills'
  AND column_name IN ('close_maker_attempt', 'close_maker_fallback_reason')
ORDER BY column_name;

SELECT conname, convalidated, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='trading.fills'::regclass
  AND conname='chk_fills_close_maker_fallback_reason_v094';

SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname='trading'
  AND indexname='idx_fills_close_maker_attempt_v094';

INSERT INTO trading.fills (
    ts, fill_id, order_id, symbol, side, qty, price, engine_mode,
    close_maker_attempt, close_maker_fallback_reason
) VALUES (
    NOW(), 'V094_DRYRUN_ACCEPT', 'V094_DRYRUN_ORDER', 'BTCUSDT', 'Buy',
    0.001, 100000, 'paper', true, 'timeout_taker'
);

DO $$
BEGIN
    BEGIN
        INSERT INTO trading.fills (
            ts, fill_id, order_id, symbol, side, qty, price, engine_mode,
            close_maker_attempt, close_maker_fallback_reason
        ) VALUES (
            NOW(), 'V094_DRYRUN_REJECT', 'V094_DRYRUN_ORDER', 'BTCUSDT', 'Buy',
            0.001, 100000, 'paper', true, 'INVALID_ENUM_VALUE'
        );
        RAISE EXCEPTION 'V094 dry-run expected INVALID_ENUM_VALUE to be rejected';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;
END $$;

ROLLBACK;
SQL
```

Round 2 idempotency:

```bash
ssh trade-core 'cd ~/BybitOpenClaw/srv && psql "$OPENCLAW_TRADING_DB_DSN" -v ON_ERROR_STOP=1' <<'SQL'
BEGIN;
\i sql/migrations/V094__fills_close_maker_audit.sql
\i sql/migrations/V094__fills_close_maker_audit.sql

SELECT COUNT(*) AS v094_column_count
FROM information_schema.columns
WHERE table_schema='trading' AND table_name='fills'
  AND column_name IN ('close_maker_attempt', 'close_maker_fallback_reason');

SELECT COUNT(*) AS v094_constraint_count
FROM pg_constraint
WHERE conrelid='trading.fills'::regclass
  AND conname='chk_fills_close_maker_fallback_reason_v094';

SELECT COUNT(*) AS v094_index_count
FROM pg_indexes
WHERE schemaname='trading'
  AND indexname='idx_fills_close_maker_attempt_v094';

ROLLBACK;
SQL
```

Expected: both rounds exit 0; round 2 reports column count `2`, constraint count `1`, index count `1`.

## sqlx Checksum Repair SOP

Do not run this until PM approves an actual V094 deployment/apply. If V094 is applied and later edited, repair the recorded checksum before engine restart:

```bash
ssh trade-core 'cd ~/BybitOpenClaw/srv && cargo run --release --bin repair_migration_checksum -- --version 94'
```

Then verify engine restart does not panic on migration checksum validation. This E1 task did not run production SQL, did not repair `_sqlx_migrations`, and did not deploy.
