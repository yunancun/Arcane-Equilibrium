# MM low-friction gross stability blocker

Date: 2026-06-20

## Operator read

The MM near miss is now classified more strictly. Latest low-friction holdout gross is `2.838bp`, but the same candidate has train gross `-0.225bp`. Treat this as holdout-only instability, not a deployable signal.

## Current blocker

- Alpha latest: `d6e3a94c94919a564bc0d2667d3e8f229bc4a39e7c3c57cbc1efb6300990f5c2`
- Status: `LOW_FRICTION_HOLDOUT_GROSS_NOT_TRAIN_CONFIRMED`
- Current-fee threshold: `4.0bp` round trip
- Next trigger: `search_train_confirmed_low_friction_mm_signal_with_sample_gated_gross_edge_ge_current_fee_round_trip`

## Boundary

No action is required from the operator. This checkpoint did not change strategy parameters, runtime state, orders, risk, auth, engine/API process state, DB schema, or Bybit private access.
