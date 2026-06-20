# MM FillSim PIT Conditional Feature Scorecard

Date: 2026-06-20

## Summary

Added and tested a fill-sim reducer that ranks maker edge by placement-time-only conditions.

It did not find a sample-gated positive maker cell.

## Implementation

- `simulate_symbol` now records placement-time `quoted_half_spread_bps`, `book_imb_at_place`, and `side_book_imb`.
- `apply_informed_skip` now preserves raw and side-aligned OFI/BTC-lead signals on each trial.
- `fill_sim_conditional_feature_scorecard` evaluates only pre-fill filters:
  - side
  - quoted half-spread
  - q0 / q_eff
  - side book imbalance
  - side-aligned OFI / BTC-lead
  - limited high-spread combinations
- `recorder_mm_verdict_cron.sh` passes the scorecard through as `fillsim.conditional_feature_scorecard`.

## Verification

- Mac: `program_code/research/tests/test_fill_sim_cost_wall.py` = 8 passed.
- Mac: `helper_scripts/cron/tests/test_fill_sim_refresh_cron_static.py` = 11 passed.
- Mac: fill_sim `py_compile`, recorder MM `bash -n`, targeted diff-check passed.
- Linux selective sync: same focused tests, `py_compile`, `bash -n`, and diff-check passed.

## Linux Smoke

Artifact: `/tmp/openclaw/research/fillsim/fillsim_conditional_feature_smoke_20260620T092837Z.json`

SHA256: `3da43e8d295322727edcfe121716cd3e5520a1337fcea625e572696806208096`

Data:

| Metric | Value |
|---|---:|
| Window | 15m fresh L1 |
| Trades | 76,124 |
| L1 rows post-filter | 139,675 |
| Crossed rows after filter | 0 |
| Symbols | 34 |
| L1 max age | 0.001h |

Conditional scorecard:

| Field | Value |
|---|---|
| Status | `NO_CONDITIONAL_FEATURE_POSITIVE_CELL` |
| Cells evaluated | 30 |
| Best condition | `quoted_half_spread_bps p75 AND side_book_imb p75` |
| n_quotes | 685 |
| n_fill_only | 116 |
| Half-spread | 1.836bp |
| Adverse @15s | 1.020bp |
| Edge before fees | 0.816bp |
| Net after maker RT fee | -3.184bp |

Isolated MM verdict wrapper smoke using the same fill_sim report confirmed passthrough:

- `conditional_status=NO_CONDITIONAL_FEATURE_POSITIVE_CELL`
- `conditional_positive_sample_gate_count=0`
- live-markout best cost-wall row: ARBUSDT net -0.2197bp, `best_n_maker_fills=1`

## Interpretation

This rules out the most obvious current maker rescue path on this fresh-L1 slice: simple PIT spread, imbalance, queue-size, and OFI/BTC-lead filters still do not clear the 4bp maker round-trip fee after fill-only adverse selection.

The maker path remains strategically important because it is still the only current lens that can invert fee sign. The next useful work is not promotion; it is either wider-spread/regime-day evidence, a fee/rebate path, or a materially new placement signal.

## Boundary

No production fill_sim report replacement, no engine/API restart, no rebuild, no strategy parameter change, no PG table write/schema migration, no Bybit private/signed/trading call, and no credential/auth/risk/order/trading mutation.
