# REF-21 S1 Calibration Lift

**Date:** 2026-05-07
**Owner:** PM
**Status:** Source and targeted tests complete; Linux sync pending at this checkpoint

## Scope

This checkpoint closes the five quality items that were left after C5 runtime
sign-off:

1. orderbook-depth partial-fill modeling,
2. latency q50/q90 calibration,
3. baseline-vs-candidate comparison,
4. balance curve + stationary block bootstrap run bands,
5. recorder retention and maturity policy.

It does not change live/demo parameters, does not enable a replay applier, and
does not claim historical L2 coverage for windows before local recorder startup.

## Implementation Summary

- Rust replay fixtures now accept local top-5 bid/ask depth fields.
- Rust simulated fills now carry requested quantity, fill ratio/status,
  partial-fill model status, available depth, latency, and effective timestamp.
- Taker fills use deterministic orderbook-depth participation when local
  recorder depth exists; otherwise the fill explicitly remains lower-fidelity.
- Replay execution calibration now derives latency q50/q90 from demo/live_demo
  order-state history and passes conservative latency into the isolated runner.
- Report analytics now build a fill-sequence balance curve, max drawdown,
  stationary block bootstrap q10/q50/q90 run bands, and baseline-vs-candidate
  deltas.
- `/api/v1/replay/advisory/compare` provides read-only comparison data for
  ML/Dream exploration without invoking any applier path.
- Recorder coverage now exposes retention/maturity status, and
  `helper_scripts/cron/ref21_market_recorder_retention.py` provides a bounded
  dry-run/apply retention job for `market.market_tickers` and
  `market.ob_snapshots`.
- The one-click Replay tab now surfaces orderbook-depth coverage, latency,
  run bands, drawdown, partial-fill count, and baseline deltas as trust
  qualifiers.

## Verification

Mac targeted checks passed before this report was written:

- `python3 -m py_compile` for replay routes, analytics, coverage, execution
  calibration, and retention cron.
- Replay targeted pytest suite: **119 passed**.
- Rust targeted replay tests:
  - `cargo test -p openclaw_engine test_apply_fill_taker_open_uses_depth_partial_and_latency_metadata --features replay_isolated --manifest-path rust/Cargo.toml`
  - `cargo test -p openclaw_engine load_fixture_accepts_optional_turnover --features replay_isolated --manifest-path rust/Cargo.toml`

## Remaining Trust Boundary

Replay is now stronger than the prior S2/S2+ sandbox, but empirical confidence
still depends on recorder history:

- old windows before local recorder startup cannot be upgraded with fabricated
  microstructure,
- per-symbol/per-strategy maker and fill-quality calibration still needs longer
  demo/live_demo sample windows,
- operator baseline libraries are still a future product layer,
- Bybit fair-use / ToS review remains an operator compliance item before
  expanding recorder cadence.
