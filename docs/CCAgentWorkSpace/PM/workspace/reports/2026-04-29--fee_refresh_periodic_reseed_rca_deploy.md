# 2026-04-29 Fee Refresh Periodic Re-seed RCA + Deploy

## 1. Scope

- Operator request: complete the recommended three phases: sync Mac commits to origin/Linux, fix the active post-deploy RCA item, and update runtime metadata/reporting.
- Target symptom: `passive_wait_healthcheck.sh --quiet` FAIL `[22] trading_pipeline_silent_gap`, with fills/intents/orders stale while risk verdicts and decision context snapshots were still active.

## 2. RCA

- Runtime logs on `trade-core` showed repeated `cost_gate fail-closed: fee rates stale ... > max_ms=7200000`.
- Startup seeded conservative default fees for demo/LiveDemo when Bybit returned the unsupported fee-rate response (`retCode=10001`, blank `retMsg`).
- The hourly periodic fee refresh path only logged the same unsupported demo error and did not re-seed defaults. After the 2h staleness window, the account manager fee cache became stale and cost_gate blocked all new strategy intents.
- This explained both `[22] trading_pipeline_silent_gap` and `[27] intents_counter_freeze`; it was not a writer wedge.

## 3. Implementation

- Commit `bdd3177` updates `rust/openclaw_engine/src/tasks.rs` so periodic fee refresh re-seeds conservative defaults when the active environment is `Demo` or `LiveDemo` and the Bybit fee-rate endpoint returns the known unsupported response.
- `Mainnet`, `Testnet`, and non-demo/meaningful business errors remain regular refresh failures; live fail-closed behavior was not relaxed.
- `rust/openclaw_engine/src/main_instruments.rs` now passes the shared Bybit environment into `spawn_fee_rate_tasks`, using live bindings first, then demo bindings.
- Added bin tests for demo-only unsupported fee endpoint detection and rejection of other errors.

## 4. Verification

- Mac:
  - `cargo test -p openclaw_engine test_demo_fee_endpoint --bin openclaw-engine` PASS (2 tests).
  - `cargo test -p openclaw_engine fee_rate_staleness --lib` PASS (3 tests).
  - `cargo check -p openclaw_engine` PASS.
  - `git diff --check` PASS.
- Existing Rust unused warnings remain unchanged.

## 5. Deploy

- Phase 1 sync:
  - Pushed Mac ahead commits through `7bf34f6` to origin.
  - Linux `trade-core` fast-forwarded to `7bf34f6`.
- Fix deploy:
  - Pushed `bdd3177` to origin.
  - Linux `trade-core` fast-forwarded to `bdd3177`.
  - Ran `PATH="$HOME/.cargo/bin:$PATH" bash helper_scripts/restart_all.sh --rebuild --keep-auth`.
  - New runtime: engine PID `401632`, API PID `401700`, HEAD `bdd3177`.

## 6. Post-deploy Status

- `engine_watchdog.py --status`: `engine_alive=true`, demo/live/paper snapshots fresh.
- Engine log confirms startup conservative fee defaults seeded for both `LiveDemo` and `Demo`.
- `passive_wait_healthcheck.sh --quiet` at 2026-04-29T09:35:30Z:
  - SUMMARY: WARN.
  - WARN `[12] bb_breakout_post_deadlock_fix`: 7d entries=1, out of permanent dormant but very low.
  - WARN `[11] counterfactual_clean_window_growth`: nonfatal clean-window status.
  - `[22] trading_pipeline_silent_gap` cleared.
  - `[27] intents_counter_freeze` cleared.

## 7. Residuals

- First natural validation of the new periodic path is the next hourly fee refresh log showing `conservative defaults re-seeded`.
- The 2h regression boundary should be watched for absence of fee-rate stale cost_gate self-lock.
- Live auth renewal still requires Operator API flow; do not hand-write `authorization.json`.
