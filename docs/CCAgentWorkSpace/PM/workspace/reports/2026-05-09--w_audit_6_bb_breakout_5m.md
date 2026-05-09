# W-AUDIT-6 bb_breakout 5m RFC / IMPL

Date: 2026-05-09
Role: PM
Scope: W-AUDIT-6 / P0-EDGE-1

## Decision

`bb_breakout` 1m rescue is retired. The strategy now has an explicit
`signal_timeframe` parameter and can consume the real 5m indicator snapshot from
the Rust tick pipeline. When configured for `5m`, missing 5m warmup is
fail-closed: the strategy skips the tick and does not fall back to the primary
1m indicator snapshot.

This is an edge-repair source/test checkpoint only. It does not grant true-live
authority, does not change MAG-082 / MAG-083 / MAG-084 state, and does not
override supervised-live gates.

## Why

Prior audit history found `bb_breakout`'s 1m Bollinger-band family structurally
mis-scaled: the old 1m rescue thresholds were only for demo sample collection,
not a promotable edge. AMD-2026-05-09-02 selected the strategy verdict:
reject 1m, revise as 5m. A TOML-only `timeframe = "5m"` would have been a fake
fix because `TickContext` previously carried only the 1m indicator snapshot.

## Implementation

- `TickContext` now exposes `indicators_5m`.
- `TickPipeline` computes 5m indicators from the existing multi-timeframe
  `KlineManager`.
- Initial kline bootstrap fetches and seeds both 1m and 5m REST bars, so planned
  rebuilds do not leave the 5m strategy cold for roughly 150 minutes.
- `BbBreakoutParams` and `strategy_params_*.toml::bb_breakout` now expose
  `signal_timeframe`.
- Runtime `BbBreakout` chooses 1m or 5m indicators by that parameter.
- Invalid TOML `signal_timeframe` falls back to `1m` with a warning.
- Demo is active on revised 5m thresholds; paper/live remain inactive for
  `bb_breakout`. Live stays disabled until demo/live_demo 5m evidence clears
  P0-EDGE-1 and supervised-live gates.

## Parameters

Current 5m family in `strategy_params_{paper,demo,live}.toml`:

- `signal_timeframe = "5m"`
- `squeeze_bw = 0.02`
- `expansion_bw = 0.04`
- `volume_threshold = 1.5`
- `min_persistence_ms = 300000`

Demo has `active = true`. Paper and live keep `active = false`.

## Verification

- `cargo test -p openclaw_engine --lib w_audit_6_bb_breakout -- --nocapture`
- `cargo test -p openclaw_engine --lib test_w_audit_6_real_strategy_params_keep_funding_arb_retired -- --nocapture`
- `cargo test -p openclaw_engine --lib test_e5_p2_4_factory_wires_bbb_new_fields -- --nocapture`
- `cargo test -p openclaw_engine --lib test_w_audit_6_factory_falls_back_on_invalid_bbb_signal_timeframe -- --nocapture`
- `cargo fmt --check`
- `cargo test -p openclaw_engine --lib bb_breakout -- --nocapture` (75 passed)
- `cargo test -p openclaw_engine --lib w_audit_6 -- --nocapture` (18 passed)
- `cargo test -p openclaw_engine --lib` (2584 passed)
- `git diff --check`

Pending before runtime apply:

- operator-authorized three-side sync and rebuild/restart
