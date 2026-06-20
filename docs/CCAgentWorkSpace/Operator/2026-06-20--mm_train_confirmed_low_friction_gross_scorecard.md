# MM train-confirmed low-friction gross scorecard

Date: 2026-06-20

## Operator read

The MM low-friction near miss is now classified more strictly. A holdout-only cell cleared the 4.0bp current-fee round trip, but the same cell is negative on train. It is not a deployable signal.

## Current blocker

- Alpha latest: `18463765c3dd1ad94b36cdfbee9a04b723491ace0a88bfb958257838dd6721ed`
- Global status: `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`
- MM primary blocker: `low_friction_current_fee_holdout_not_train_confirmed`
- Train-confirmed current-fee candidates: `0`
- Best train-confirmed min gross: `1.402bp`
- Current-fee threshold: `4.0bp` round trip
- Gap: `2.598bp`
- Holdout-only current-fee cell: holdout gross `5.868bp` / net `1.868bp`, train gross `-0.336bp`
- Next trigger: `search_train_confirmed_low_friction_mm_signal_with_sample_gated_gross_edge_ge_current_fee_round_trip`

## Boundary

No action is required from the operator. This checkpoint did not change strategy parameters, runtime state, orders, risk, auth, engine/API process state, DB schema, or Bybit private access.
