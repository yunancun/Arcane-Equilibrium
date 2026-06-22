# 2026-06-22 Multi-Horizon Cost Gate Learning Review Path

## Summary

v412 turns the learned Cost Gate candidate from v411 into a multi-horizon operator review path. This is not a global Cost Gate lowering request. It is a side-cell/horizon-specific learning path for `ma_crossover|ETHUSDT|Sell`, with no probe/order authority and no promotion proof.

## Runtime Evidence

- Read-only counterfactual artifact: `/tmp/openclaw/cost_gate_counterfactual/cost_gate_reject_counterfactual_20260622T165507Z.json`
- Latest counterfactual status: `MULTI_HORIZON_PROFIT_LEARNING_CANDIDATES_PRESENT`
- Horizons: `15,30,60,120,240`
- Top side-cell: `ma_crossover|ETHUSDT|Sell`
- Side-cell status: `CANDIDATE_MULTI_HORIZON_STABLE`
- Candidate horizons: `[15,30,60,120,240]`
- Best horizon: `120m`
- Best avg net: `121.1121bp`
- Best net-positive pct: `100.0%`
- Best sample count: `10074`

## Source Changes

- `cron/cost_gate_learning_lane_cron.sh` now defaults scorecard stability to `15,30,60,120,240` instead of mirroring only the 60m outcome horizon.
- `cost_gate_learning_lane/decision_packet.py` now merges horizon-stability fields into `counterfactual.top_side_cells`.
- `alpha_discovery_throughput/learning_worklist.py` now routes matched multi-horizon blocked-signal side-cells to `operator_review_multi_horizon_blocked_signal_side_cell_before_bounded_demo_probe`, even if stale learning-loop status still reports `SINGLE_HORIZON_ONLY`.

## Alpha Result

Linux artifact-only alpha smoke after source sync reports:

- schema: `alpha_discovery_runtime_killboard_v8`
- runtime source: `SYNCED_CLEAN`
- worklist status: `OPERATOR_GATED_LEARNING_READY`
- top task: `operator_probe_review`
- primary blocker: `cost_gate_blocked_signal_outcomes_need_demo_probe_authority_review`
- objective: `operator_review_multi_horizon_blocked_signal_side_cell_before_bounded_demo_probe`
- matched cell: `ma_crossover|ETHUSDT|Sell`
- horizon status: `CANDIDATE_MULTI_HORIZON_STABLE`
- candidate horizons: `[15,30,60,120,240]`
- best horizon: `120`
- order/probe authority: false

## Remaining Gates

- The decision packet still records `DATA_FLOW_MONITOR_REQUIRED`; demo data-flow monitor evidence must be restored/refreshed.
- Any bounded demo probe still needs explicit operator authorization.
- Any future filled/proxy outcomes must pass matched-control result review and execution-realism review before Cost Gate changes can be considered.

## Verification

- Mac: py_compile passed.
- Mac: `test_cost_gate_learning_lane_decision_packet.py`, `test_alpha_discovery_throughput.py`, `test_alpha_discovery_learning_worklist.py` = `71 passed`.
- Mac: Cost Gate cron static = `13 passed`.
- Linux: source fast-forwarded to `1f7180a184562caa259719dd512e9c9df1936ffe`.
- Linux: same focused tests = `71 passed` and `13 passed`.
- Linux: read-only multi-horizon scorecard refresh, decision packet refresh, and alpha smoke passed.

## Boundary

Source/test/docs + Linux source sync + read-only PG SELECT for counterfactual + `/tmp/openclaw` artifact-only refresh/smoke only. No CI, no PG write/schema migration, no Bybit private/signed/trading call, no deploy/restart, no crontab install, no env/auth/risk/order/strategy mutation, no Cost Gate lowering, no probe/order authority, no promotion proof.
