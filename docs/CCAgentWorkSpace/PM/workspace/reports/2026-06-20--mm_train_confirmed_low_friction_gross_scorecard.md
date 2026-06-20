# MM train-confirmed low-friction gross scorecard

Date: 2026-06-20

## Decision

Rank MM low-friction candidates by train-confirmed gross edge before any current-fee review. A low-friction cell that clears 4.0bp in holdout but fails train is now explicitly blocked as holdout-only evidence.

## Runtime evidence

- FillSim latest sha256: `a74353a05a99bd28a04acee932af86d5f7ab72ea3b40e5a497dd0303ec0ff408`
- FillSim generated: `2026-06-20T21:09:29.625230+00:00`
- L1 rows post-filter: `806842`
- Trades rows: `539728`
- Low-friction candidates evaluated: `96`
- Train-confirmed positive-gross candidates: `44`
- Train-confirmed current-fee candidates: `0`
- Train-confirmed scorecard status: `LOW_FRICTION_TRAIN_CONFIRMED_GROSS_BELOW_CURRENT_FEE`
- Best train-confirmed candidate: `quoted_half_spread_bps_train_p75_and_side_touch_size_delta_frac_10s_train_p90`
- Best train gross: `2.009bp`, n=155
- Best holdout gross: `1.402bp`, n=110
- Best min(train, holdout) gross: `1.402bp`
- Gap to current 4.0bp fee round trip: `2.598bp`

## Alpha evidence

- Alpha latest sha256: `18463765c3dd1ad94b36cdfbee9a04b723491ace0a88bfb958257838dd6721ed`
- `created_at_utc`: `2026-06-20T21:18:40.366076+00:00`
- Global status: `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`
- MM blocker class: `feature_family_no_edge`
- MM primary blocker: `low_friction_current_fee_holdout_not_train_confirmed`
- Cost-wall escape status: `CURRENT_FEE_HOLDOUT_GROSS_NOT_TRAIN_CONFIRMED`
- Best current-fee source: `low_friction_signal_holdout`
- Holdout-only current-fee cell: `quoted_half_spread_bps_train_p90_and_side_touch_size_delta_frac_30s_train_p90`
- Holdout-only train gross: `-0.336bp`, n=90
- Holdout-only holdout gross: `5.868bp`, net `1.868bp`, n=43

## Read

The low-friction feature family has useful structure, but not enough stable gross edge at the current maker fee tier. The best train-confirmed cell is still 2.598bp short of the current 4.0bp round trip, and the only current-fee-positive cell is holdout-only. Treat this as a feature-family no-edge blocker, not a promotion candidate.

Next trigger: `search_train_confirmed_low_friction_mm_signal_with_sample_gated_gross_edge_ge_current_fee_round_trip`.

## Verification

- Mac focused: `53 passed`
- Linux focused: `53 passed`
- `py_compile`: passed
- `git diff --check`: passed
- Selective Linux source sync: passed
- Linux read-only fill_sim refresh, MM verdict, and alpha runtime smoke: passed

## Boundary

Artifact-only source/test/docs plus selective Linux source sync and `/tmp/openclaw` artifact writes. Read-only PG SELECT via fill_sim/MM verdict wrappers. No PG table write/schema migration, no Bybit private/signed/trading call, no engine/API rebuild/restart, and no credential/auth/risk/order/strategy mutation. Not signal, execution, or promotion proof.
