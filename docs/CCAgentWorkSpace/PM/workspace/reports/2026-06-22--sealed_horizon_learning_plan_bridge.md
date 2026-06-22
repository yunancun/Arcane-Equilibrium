# Sealed Horizon Learning Plan Bridge

Date: 2026-06-22

## Verdict

`PASS_SOURCE_CHECKPOINT`：sealed horizon replay 已接入 Cost Gate demo-learning plan / ledger / outcome horizon path。這不是盈利證明，也不是 probe/order authority；它把已通過 sealed replay 的 `ma_crossover|BTCUSDT|Sell` 240m retiming 候選轉成後續 runtime learning lane 可以累積 blocked-signal outcome 的候選。

## What Changed

- `helper_scripts/research/cost_gate_learning_lane/policy.py`
  - 新增 `--horizon-sealed-replay-json`。
  - 接受 `horizon_specific_sealed_replay_packet_v1` 且僅在 status/pass/boundary 全綠時轉成 selected candidate。
  - 候選攜帶 `source_kind=horizon_specific_sealed_replay`、`outcome_horizon_minutes=240`、sealed replay source hashes / best-primary metrics / failed gates。
  - 保持 `order_authority=NOT_GRANTED`、`main_cost_gate_adjustment=NONE`。
- `helper_scripts/research/cost_gate_learning_lane/runtime_adapter.py`
  - admission decision 和 JSONL ledger row 現在帶 `candidate_summary`。
- `helper_scripts/research/cost_gate_learning_lane/price_observations.py`
  - price observation windows 優先使用 ledger row 的 candidate horizon。
- `helper_scripts/research/cost_gate_learning_lane/outcome_writer.py`
  - blocked/probe outcome markout 優先使用 row-level candidate horizon。

## Runtime Artifact Smoke

Copied current Linux runtime artifacts to Mac read-only:

- `/tmp/openclaw/profitability_refresh/20260622T031320Z/cost_gate_counterfactual/cost_gate_reject_counterfactual_latest.json`
- `/tmp/openclaw/profitability_refresh/20260622T031320Z/horizon_specific_sealed_replay/horizon_specific_sealed_replay_latest.json`

Generated local smoke plan:

- `/tmp/openclaw_policy_smoke/demo_learning_lane_plan_with_sealed_horizon_latest.json`

Result:

- status `READY_FOR_DEMO_LEARNING_PROBE`
- gate `OPERATOR_REVIEW`
- top candidate `ma_crossover|BTCUSDT|Sell`
- sealed outcome horizon `240`
- sealed avg net `31.8707 bps`
- sample `13819`
- failed sealed gates `[]`
- `order_authority=NOT_GRANTED`
- `main_cost_gate_adjustment=NONE`

## Verification

- `python3 -m py_compile ...` passed for touched Python files.
- `python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py` = `70 passed`.
- `python3 -m pytest -q helper_scripts/research/tests/test_profitability_path_scorecard.py helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py` = `121 passed`.
- `git diff --check` passed.
- Local runtime-artifact smoke selected the intended 240m sealed candidate.

## Boundaries

No PG write/schema migration, no Bybit private/signed/trading call, no deploy/rebuild/restart, no env/auth/risk/order/strategy mutation, no Cost Gate lowering, no probe/order authority, and no promotion proof.

## Next Blocker

Runtime is source-synced but still `NOT_ACCUMULATING`: probe ledger, writer/cron execution, and blocked-signal outcome rows must appear. This checkpoint makes the right candidate/horizon machine-readable; it does not yet prove realized demo learning or profitability.
