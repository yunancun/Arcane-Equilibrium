# Items 1-6 Completion Report

Date: 2026-04-29 17:54 CEST
Owner: Codex
Status: Implemented, pushed, Linux deployed at commit `53bff07`.

## Scope

User requested the recommended items 1-6:

1. Repair unsafe maker pricing fallback.
2. Quarantine robust-negative grid symbols.
3. Tune bb_breakout Phase 2 demo threshold.
4. Verify and repair fee-refresh follow-through.
5. RCA `[2] label_backfill`.
6. RCA `[27] intents_counter_freeze`.

## Completed

- Maker PostOnly pricing now requires a usable BBO and tick size; it skips instead of falling back to taker-like last price.
- Grid robust-negative symbols are blocked for new opens while existing close/reduce paths remain enabled.
- bb_breakout demo `volume_threshold` was raised to `1.2` from the 14-day sweep; this is a cleaner demo-signal tweak, not live promotion evidence.
- Manual label backfill cleared `[2] label_backfill`: latest observed healthcheck showed labels_24h/close_fills ratio `1.02` and join linkage `100%`.
- `[27] intents_counter_freeze` was traced to demo cost gate fail-closed on stale fee timestamps.
- Fee freshness follow-through now uses one grouped fee-refresh task that registers demo/live targets and refreshes each binding every hour with `engine/env` logging.
- Demo/LiveDemo cost gate now treats cached conservative default fee rates as usable when the demo fee-rate endpoint is unsupported; mainnet remains fail-closed on stale fee rates.

## Verification

- `cargo fmt --manifest-path rust/Cargo.toml --all`
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine --lib`
  - Result: `2363 passed; 0 failed`
- `cargo check --manifest-path rust/Cargo.toml --workspace`
  - Result: pass; existing warnings only

## Deploy Checks

Linux rebuild/restart:

- Commit: `53bff07`
- Engine PID: `620724`
- API PID: `620851`

Verified:

- Startup logs contain two fee bindings:
  - `engine=demo env=Demo`
  - `engine=live env=LiveDemo` when live demo is authorized.
- Post-restart risk verdict query from `2026-04-29 15:59:22Z` showed no fee-stale rejections; remaining rejects were ATR unavailable or JS negative edge.
- `helper_scripts/db/passive_wait_healthcheck.py` reports `[27] intents_counter_freeze` as PASS.
- `trading.signals` recovered after restart and `[24] signals_writer_freshness` reports PASS.
- Post-restart exchange intents had `empty_signal_id=0`.

Still pending natural observation:

- First hourly refresh should log conservative default reseed for every demo endpoint binding, not only `LiveDemo`.
- `[34] intent_signal_attribution` still FAILs on the 30-minute rolling window because it includes pre-restart empty-signal rows; it should clear after the old rows age out if post-restart attribution remains clean.
