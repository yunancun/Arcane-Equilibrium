# Strategy Edge Models Engineering Log

Date: 2026-04-30
Owner: Codex PM/E1 local implementation

## Runtime Baseline

Latest Linux pre-change evidence showed the edge problem is execution and selector quality, not a reason to add another naked price-prediction strategy:

- `[33] maker_fill_rate` WARN: maker-like fill ratio still materially below target, with many rows still effectively taker-like.
- `[38] grid_trading_lifecycle_drift` FAIL: live_demo grid lifecycle remains much shorter than demo, with high re-entry/churn.
- `[40] realized_edge_acceptance` FAIL: 24h MLDE rows were negative post-fee on average, with grid/MA negative cells dominating.

## Implemented Changes

1. Fixed TOML-to-strategy wiring drift:
   - `maker_price_buffer_ticks` now reaches MA and BB breakout from per-engine TOML.
   - grid `maker_price_buffer_ticks`, `reject_cooldown_ms`, `blocked_symbols`, `min_grid_step_bps`, and `cost_floor_multiplier` now reach the runtime `GridTrading` instance.
   - This closes the gap where TOML listed robust-negative grid symbols but the factory did not fully pass them into the strategy instance.

2. Maker execution baseline:
   - demo/live/paper MA and grid now set `maker_price_buffer_ticks = 0`.
   - BB breakout maker config also carries the buffer field where active.
   - Existing BBO/tick-size missing behavior remains fail-closed: maker entry skips rather than falling back to last price.

3. Cost-aware OU grid spacing:
   - Added `compute_ou_step_with_cost_floor`.
   - grid spacing now applies both round-trip fee floor multiplier and a minimum bps step.
   - Baseline config: `min_grid_step_bps = 22.0`, `cost_floor_multiplier = 2.0`, `reject_cooldown_ms = 120000`.

4. Bayesian cell selector:
   - scanner `edge_routing` now supports posterior lower-confidence-bound gating.
   - Config uses `posterior_lcb_z = 1.0`, `posterior_min_std_bps = 20.0`, and routes mature uncertain-positive/negative-LCB cells to `exploration_only`.

5. MA directional SNR gate:
   - MA entry now can require `|KAMA - SMA20| / conservative_ATR >= min_trend_snr`.
   - Baseline config sets `min_trend_snr = 0.75`.
   - Exits are unaffected; this only filters new MA entries in noisy trend separation.

## Verification

- `cargo test -p openclaw_engine --lib`: 2377 passed / 0 failed.
- `cargo check --workspace`: passed.
- Focused tests added for:
  - grid OU bps floor
  - scanner posterior-negative cap
  - MA SNR noisy-entry block

## Observation Plan

After Linux deploy, observe at least 24h before judging the edge effect. Primary gates:

- `[33] maker_fill_rate`: maker-like ratio, fee_drop, reject-rate side effects.
- `[38] grid_trading_lifecycle_drift`: grid lifetime/re-entry/fee-burn.
- `[40] realized_edge_acceptance`: post-fee net edge by strategy/symbol cell.

Expected first 24h caveat: healthchecks use rolling windows, so old fills can keep `[33]`, `[38]`, and `[40]` red until enough post-deploy rows replace the window.
