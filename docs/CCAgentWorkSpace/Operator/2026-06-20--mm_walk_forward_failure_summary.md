# Operator Note: MM Walk-Forward Failure Summary

v277 adds a compact MM walk-forward failure summary to alpha discovery. No operator action is requested.

Latest trade-core fresh-L1 2h refresh:

- fill_sim report sha256 `b9bdeba681d6182de8eda32031e81320e6f628893aa65c5a645d334aa524a9ca`
- `walk_forward_feature_scorecard.status=NO_WALK_FORWARD_FEATURE_TRAIN_POSITIVE`
- `failure_summary.status=NO_TRAIN_POSITIVE_CELL`
- 51 train-only-threshold candidates evaluated
- train sample-gated positives: 0
- holdout-confirmed candidates: 0
- best train combo `quoted_half_spread_bps train_p75 AND side_book_imb train_p75` still net `-3.524bp`; holdout `-3.260bp`
- alpha-discovery latest sha256 `3a834cad9e3ba3abbdc72014fab4b09dc2647046cfa232379a3d4f3172e787b3` exposes the same summary; MM remains `CAPTURING`, ready/probe=0

Read: current MM failure is not just a missing simple spread/imbalance/OFI filter. Current-fee MM still needs a lower-fee/rebate path, materially new signal family, or non-MM alpha lane. No live/demo parameter change, no risk/order/auth mutation, no engine restart, no Bybit private call, no PG write.
