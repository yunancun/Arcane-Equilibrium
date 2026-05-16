# E1 B-3A Phase 1b Dynamic Backoff + Close-Maker Fallback State Machine

- Date: 2026-05-16
- Bound role: E1(worker)
- Workgroup: B-3A
- Status: SOURCE/TEST DONE, no commit/push/stage

## Scope

Implemented close-maker fallback/backoff primitives for later close dispatch integration:

- `maker_rejection.rs`
  - Added close-side fallback reason enum aligned to V094 labels.
  - Added side-aware close rejection decision helper.
  - Added in-memory `CloseMakerBackoffState`: per-symbol 1s -> 60s exponential backoff, 5min quiet reset, >=10 distinct symbols in 1min -> 5min global pause.
  - Added tests for race/fallback decisions, classifier reuse, exponential cap, reset, and global cascade.
- `pending_sweep.rs`
  - Added close-maker short cancel grace primitive (`2_000ms`) without changing entry-maker grace.
  - Added `close_maker_sweep_fallback_reason()` for timeout/cancel-grace audit reason mapping.
  - Added tests for close timeout -> `timeout_taker`, close cancel grace -> `cancel_grace_expired`, and entry/close isolation.
- `grid_trading/position_mgmt.rs`
  - Updated close-side `TooManyPending` arm path to use dynamic backoff state.
  - Preserved `PostOnlyCross` no-cooldown immediate market fallback semantics.
  - Preserved other reject categories as 1min default close cooldown.
- `grid_trading/mod.rs` / `constructors.rs`
  - Added the minimal `GridTrading` state field required to persist per-symbol/global close-maker backoff.
  - Added public helper accessors for future close dispatcher integration: active rate-limit scope and global pause deadline.
- `grid_trading/tests.rs`
  - Kept the BB-MF-3 baseline test name `test_close_too_many_pending_5min_cooldown` for E4 grep compatibility, but updated its expectation to the Phase 1b B-3A dynamic semantics.
  - Added per-symbol and global-cascade integration tests.

Compatibility note: the old fixed 5min close `TooManyPending` expectation is superseded only for the close-maker path. Entry cooldown isolation and default close reject cooldown semantics remain isolated.

## Boundary Notes

- Did not edit `tick_pipeline/commands.rs`.
- Did not edit `strategies/common/maker_price.rs`.
- Did not edit database writer/mod files.
- Did not edit healthcheck Python files.
- Did not edit frozen spec/AMD/TODO/CLAUDE/shared memory.
- Did not deploy, run runtime, set `OPENCLAW_ENABLE_PAPER=1`, touch live/mainnet, phys_lock live, or production `allLiquidation`.
- Did not commit, push, stash, clean, revert, or stage.

Adjacent source note: `grid_trading/mod.rs` and `grid_trading/constructors.rs` were touched only because Rust needs a real per-strategy field for dynamic backoff state; encoding exponential state in the old single deadline map would lose consecutive/reset/global cascade semantics.

## Parallel Work Observed

Initial `git status --short` and `git stash list` were clean/empty. During implementation, parallel dirty files appeared and were left untouched:

- database/V094 writer files
- healthcheck files
- `tick_pipeline/commands.rs` and related tick pipeline files
- B-2A / B-3B reports and V094 migration/test files

No unrelated changes were reverted or cleaned.

## Verification

Passed:

```bash
rustfmt --edition 2021 --check rust/openclaw_engine/src/strategies/maker_rejection.rs rust/openclaw_engine/src/strategies/grid_trading/mod.rs rust/openclaw_engine/src/strategies/grid_trading/constructors.rs rust/openclaw_engine/src/strategies/grid_trading/position_mgmt.rs rust/openclaw_engine/src/strategies/grid_trading/tests.rs rust/openclaw_engine/src/event_consumer/pending_sweep.rs

cargo test -q --manifest-path rust/openclaw_engine/Cargo.toml maker_rejection::tests
# 14 passed

cargo test -q --manifest-path rust/openclaw_engine/Cargo.toml pending_sweep::tests
# 16 passed

cargo test -q --manifest-path rust/openclaw_engine/Cargo.toml too_many_pending
# 4 passed

cargo test -q --manifest-path rust/openclaw_engine/Cargo.toml grid_trading::tests::test_
# 62 passed

cargo check -q --manifest-path rust/openclaw_engine/Cargo.toml
# PASS with pre-existing warnings outside this task

git diff --check -- rust/openclaw_engine/src/strategies/maker_rejection.rs rust/openclaw_engine/src/strategies/grid_trading/mod.rs rust/openclaw_engine/src/strategies/grid_trading/constructors.rs rust/openclaw_engine/src/strategies/grid_trading/position_mgmt.rs rust/openclaw_engine/src/strategies/grid_trading/tests.rs rust/openclaw_engine/src/event_consumer/pending_sweep.rs
# PASS
```

Corrected command mistakes / limitations:

```bash
cargo test -q --manifest-path rust/openclaw_engine/Cargo.toml test_close_too_many_pending_5min_cooldown test_close_too_many_pending_dynamic_backoff_per_symbol ...
# FAIL: cargo accepts only one TESTNAME filter. Corrected with `too_many_pending`.

rustfmt rust/openclaw_engine/src/...
# FAIL: rustfmt defaulted to Rust 2015 for standalone files. Corrected with `--edition 2021`.

cargo fmt --manifest-path rust/openclaw_engine/Cargo.toml --check
# FAIL: broad pre-existing rustfmt drift in many unrelated crate files. Scoped rustfmt check on touched files passed.
```

Pre-existing warnings still emitted by Rust checks:

- unused `LEAD_WINDOW_SECS_MAIN` in `panel_aggregator/btc_lead_lag/db_writer.rs`
- unused `make_intent` in `ma_crossover/helpers.rs`
- unused `spawn_position_reconciler` in `tasks.rs`
- private interface warning in `live_auth_watcher_tests.rs`

## Remaining Integration

This patch provides the close-maker fallback/backoff primitives. Production close dispatch still needs the B-side integration in `commands.rs` / close dispatcher ownership to call:

- `close_rejection_fallback_decision()`
- `close_maker_rate_limit_scope()`
- `close_maker_sweep_fallback_reason()`

Until that integration lands, the primitives are source/test ready but not a deployable close-maker fallback path by themselves.
