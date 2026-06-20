# MM FillSim Maker Fee Sensitivity

Date: 2026-06-20

## Summary

Added and tested a fill-sim reducer that converts observed maker cells into break-even maker-fee and fee-scenario rows.

Current 2.0bp/side maker fee still does not produce a sample-gated positive cell. At 1.0bp/side, one sample-gated conditional cell barely clears zero.

## Implementation

- `fill_sim_edge_scorecard` now keeps `all_fill_only_cells` for downstream reducers.
- `fill_sim_conditional_feature_scorecard` now keeps `all_cells` for downstream reducers.
- `fill_sim_maker_fee_sensitivity_scorecard` normalizes cells from both scorecards and reports:
  - edge before fees
  - break-even maker fee per side
  - fee reduction needed to breakeven
  - scenario rows for maker fee per side `2.0/1.0/0.5/0.0/-0.5bp`
- `recorder_mm_verdict_cron.sh` passes the scorecard through as `fillsim.maker_fee_sensitivity_scorecard`.

## Verification

- Mac: `program_code/research/tests/test_fill_sim_cost_wall.py` = 11 passed.
- Mac: `helper_scripts/cron/tests/test_fill_sim_refresh_cron_static.py` = 11 passed.
- Mac: fill_sim `py_compile`, recorder MM `bash -n`, targeted diff-check passed.
- Linux selective sync: same focused tests, `py_compile`, `bash -n`, and diff-check passed.

## Linux Smoke

Artifact: `/tmp/openclaw/research/fillsim/fillsim_fee_sensitivity_smoke_20260620T093904Z.json`

SHA256: `33020cceaff59b47ae121dc270c7602c3a4540958eff497ac24975387ef9b5f2`

Data:

| Metric | Value |
|---|---:|
| Window | 15m fresh L1 |
| Trades | 88,555 |
| L1 rows post-filter | 144,418 |
| Crossed rows after filter | 0 |
| Symbols | 34 |
| L1 max age | 0.0h |

Fee sensitivity:

| Field | Value |
|---|---|
| Status | `LOWER_FEE_SAMPLE_GATED_POSITIVE` |
| Cells evaluated | 106 |
| Current 2.0bp/side gated positives | 0 |
| 1.0bp/side gated positives | 1 |
| 0.5bp/side gated positives | 10 |
| 0.0bp/side gated positives | 32 |
| -0.5bp/side gated positives | 83 |

Best sample-gated break-even cell:

| Field | Value |
|---|---|
| Source | `conditional_feature_scorecard` |
| Condition | `quoted_half_spread_bps p75 AND side_book_imb p75` |
| n_fill_only | 116 |
| Edge before fees | 2.057bp |
| Break-even maker fee | 1.028bp/side |
| Fee reduction to breakeven | 0.972bp/side |
| Net at 1.0bp/side | +0.057bp |

Isolated MM verdict wrapper smoke using the same fill_sim report confirmed passthrough:

- `maker_fee_sensitivity_scorecard.status=LOWER_FEE_SAMPLE_GATED_POSITIVE`
- `cells_evaluated=106`
- scenario counts match the direct fill_sim artifact
- live-markout best cost-wall row was still below gate: ARBUSDT net +0.3133bp with `best_n_maker_fills=1`

## Interpretation

This converts the maker cost wall into a quantified business-model lever. Current fees still fail the sample-gated test; the best measured cell needs maker fees at or below roughly 1.03bp/side before strategy fees.

That is not promotion proof. It says the maker path is fee-sensitive and may become viable under a lower-fee, rebate, or market-maker program, but it still needs actual eligibility plus cross-regime CP-3 evidence. Without that, the engineering path must find a stronger placement signal rather than merely tuning the existing filters.

## Boundary

No production fill_sim report replacement, no engine/API restart, no rebuild, no strategy parameter change, no PG table write/schema migration, no Bybit private/signed/trading call, and no credential/auth/risk/order/trading mutation.
