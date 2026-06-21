# 2026-06-21 -- Cost Gate Historical Scorecard Review

## 結論

本輪補上 cost-gate demo-learning lane 的歷史 counterfactual 審查面：`cost_gate_reject_counterfactual_v2` 產出的 side-cell 候選現在可被轉成 `historical_scorecard_review_latest.json`，並被 status preflight / alpha-discovery killboard 讀取。

關鍵邊界：這不是 `probe_ledger.jsonl`，不是 fill/execution/runtime evidence，不是 promotion proof，不授權 demo probe，不降低主 Cost Gate。它只能回答「哪些被 cost gate 擋掉的 side-cell 值得優先啟用 runtime writer 去捕捉真實後驗 outcome」。

## 變更

- 新增 `helper_scripts/research/cost_gate_learning_lane/historical_review.py`
  - 輸入：`cost_gate_reject_counterfactual_v2` JSON。
  - 輸出：`cost_gate_demo_learning_lane_historical_scorecard_review_v1`。
  - 分類：historical candidates / keep-blocked / data-coverage tasks。
  - 失效條件：schema 錯誤、缺 generated_at、future timestamp、stale scorecard 全部 fail-closed。
- `cost_gate_learning_lane.status`
  - activation preflight 現在包含 `historical_review`。
  - answers 明確暴露 `historical_counterfactual_candidates_present` 與 `historical_counterfactual_is_runtime_evidence=false`。
- `alpha_discovery_throughput.runtime_runner` / `discovery_loop`
  - cost-gate arm 附帶 historical review。
  - ledger missing/empty 且 historical candidates present 時，路由為 `RUN_READ_ONLY_CAPTURE` / `data_coverage`，primary blocker = `historical_cost_gate_candidates_not_runtime_verified`。
  - 不會變成 `READY_FOR_PROBE`。
- `helper_scripts/cron/cost_gate_learning_lane_cron.sh`
  - hourly artifact loop 現在也會從 latest counterfactual scorecard 產生 dated/latest historical review artifact。

## 驗證

- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q` -> `53 passed`
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` -> `34 passed`
- `python3 -m pytest helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py -q` -> `9 passed`
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/historical_review.py helper_scripts/research/cost_gate_learning_lane/status.py helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py` -> passed
- `bash -n helper_scripts/cron/cost_gate_learning_lane_cron.sh` -> passed

## 邊界

Source/test/docs only. No runtime source sync, env edit, deploy, rebuild, restart, cron install, PG table write/schema migration, Bybit private/signed/trading call, order authority, main Cost Gate lowering, credential/auth/risk/order/strategy/runtime mutation, execution proof, or promotion proof.

## 下一步

Runtime 仍需 operator-approved source sync/reconcile、writer enablement、cron install/restart 才會開始累積 `probe_ledger.jsonl` 與 `blocked_signal_outcome` rows。Historical review 只能縮短「先捕捉哪些 side-cell」的選擇時間，不能替代真實 demo blocked-outcome evidence。
