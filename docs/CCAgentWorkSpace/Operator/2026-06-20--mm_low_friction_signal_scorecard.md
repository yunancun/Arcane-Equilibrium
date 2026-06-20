# 2026-06-20 -- MM Low-Friction Signal Scorecard

PM source report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-20--mm_low_friction_signal_scorecard.md`.

Runtime read: fill_sim sha256 `7d152298cee8ac81821afe97bf5e3003ac8ed460bce71cb13499e5d989d07e6c`, generated `2026-06-20T19:36:53.831449+00:00`; alpha latest sha256 `c87f9d538a1cf5dc7480d8d6f76e2048fe0278042812aa7dc725a9cea6890bba`, created `2026-06-20T19:46:40.560943+00:00`.

Operator meaning: the new recent-flow/L1-churn MM search found a better near miss: `quoted_half_spread_bps train_p90 AND side_touch_size_delta_frac_30s train_p90` has sample-gated holdout gross edge 2.838bp, net -1.162bp, n=81. This is closer than prior MM surfaces but still below the 4.0bp current-fee gross-edge threshold.

Boundary: artifact-only research tooling and `/tmp/openclaw` evidence refresh. No engine/API restart, no rebuild, no strategy parameter change, no order/auth/risk/runtime mutation, and no Bybit private/signed/trading call.
