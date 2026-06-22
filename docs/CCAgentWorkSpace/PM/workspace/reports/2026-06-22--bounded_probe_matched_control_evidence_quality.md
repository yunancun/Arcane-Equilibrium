# 2026-06-22 — Bounded Probe Matched-Control Evidence Quality

## 結論

`bounded_demo_probe_result_review_v1` 現在會產出 `bounded_demo_probe_evidence_quality_v1`，把未來 bounded demo probe 的實際成交結果與同 side-cell / 同 horizon 的 `blocked_signal_outcome` 對照樣本放在同一個 review artifact 裡。

這使 Cost Gate 逃逸路徑更接近可審計的 Demo mode 學習實驗：正收益 probe 不能只靠幾筆 demo 成交推進；缺 matched control 時會被標記為 `anecdote_risk`，並由 profitability scorecard / runtime killboard / discovery loop / learning worklist 退回 data coverage。

## Source 變更

- `helper_scripts/research/cost_gate_learning_lane/bounded_probe_result_review.py`
  - 新增 matched `blocked_signal_outcome` control 搜集與 `bounded_demo_probe_evidence_quality_v1`。
  - 記錄 matched-control count、avg net、positive pct、`probe_minus_control_avg_net_bps`、`probe_outperforms_matched_control`、`anecdote_risk`。
  - 正收益但缺 control 時，next action 優先要求 `record_matched_blocked_signal_outcomes_for_same_side_cell_and_horizon`。
- `helper_scripts/research/alpha_discovery_throughput/profitability_path_scorecard.py`
  - 將缺 matched control 的正收益 result review 降級為 `BOUNDED_DEMO_PROBE_CONTROL_COMPARISON_REQUIRED`。
- `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`
  - 將 evidence-quality fields 帶入 Cost Gate learning arm。
- `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
  - 正收益 result review 若缺 matched control，主 blocker 改為 `bounded_probe_result_review_needs_matched_blocked_signal_control` / `data_coverage`。
- `helper_scripts/research/alpha_discovery_throughput/learning_worklist.py`
  - learning task evidence 攜帶 matched-control fields。

## 驗證

- Mac py_compile：touched modules passed。
- Mac focused pytest：
  - `test_cost_gate_bounded_probe_result_review.py`
  - `test_profitability_path_scorecard.py`
  - `test_alpha_discovery_throughput.py`
  - `test_alpha_discovery_learning_worklist.py`
  - Result：`74 passed`。
- `git diff --check` passed。

## 邊界

本 checkpoint 仍是 source/test/docs only：no CI run, no PG write/schema migration, no Bybit private/signed/trading call, no deploy/rebuild/restart, no cron install/env/auth/risk/order/strategy/runtime mutation, no Cost Gate lowering, no probe/order authority, no promotion proof。

## 待完成

- Commit / push。
- Linux `trade-core` source sync。
- Linux focused py_compile / pytest / artifact-only smoke。
