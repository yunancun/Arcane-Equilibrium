# Cost Gate Multi-Horizon Counterfactual Stability

日期：2026-06-21
角色：PM 主會話，本地 source/test/docs checkpoint
狀態：PASS（source-side only）

## 結論

本 checkpoint 修掉一個實際會影響 demo 學習判斷的缺口：原先 Cost Gate reject counterfactual 只用單一 outcome horizon，容易把「持倉窗口錯」誤讀成「信號無盈利可能」。

現在 scorecard 會比較多個 horizon，將 rejected side-cell 分成：

- `CANDIDATE_MULTI_HORIZON_STABLE`
- `CANDIDATE_HORIZON_SPECIFIC`
- `MIXED_HORIZON_RESPONSE`
- `BLOCK_CONFIRMED_MULTI_HORIZON`

這讓後續 bounded demo-learning lane 可以優先看跨窗口穩定的候選，並把單窗口候選標成需要 horizon review，而不是盲目 lower Cost Gate。

## 改動

- `helper_scripts/db/audit/cost_gate_reject_counterfactual.py`
  - 新增 `--horizon-minutes-list`。
  - 新增 `cost_gate_reject_horizon_stability_v1`。
  - Markdown / JSON payload 均輸出 Horizon Stability 區塊。
  - 保持邊界：`order_authority=NOT_GRANTED`、`main_cost_gate_adjustment=NONE`、`promotion_evidence=false`、`runtime_mutation=NONE`。

- `helper_scripts/research/cost_gate_learning_lane/policy.py`
  - demo-learning plan 的 source metadata 帶入 horizon stability。
  - selected probe candidate 附帶 `horizon_stability` 摘要，包括 candidate horizons 和 best horizon。

- `helper_scripts/cron/cost_gate_learning_lane_cron.sh`
  - 新增 `OPENCLAW_COST_GATE_SCORECARD_HORIZON_MINUTES_LIST`。
  - scorecard refresh 會傳入 `--horizon-minutes-list`。
  - status log 記錄 horizon stability status / next trigger / horizons。

- `helper_scripts/research/cost_gate_learning_lane/status.py`
  - activation preflight / learning-loop summary 讀取 horizon stability status log 欄位。

- `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
  - cost-gate blocker row 顯示 latest scorecard horizon stability fields。

## 驗證

- `python3 -m py_compile helper_scripts/db/audit/cost_gate_reject_counterfactual.py helper_scripts/research/cost_gate_learning_lane/policy.py helper_scripts/research/cost_gate_learning_lane/status.py helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
- `bash -n helper_scripts/cron/cost_gate_learning_lane_cron.sh helper_scripts/cron/install_cost_gate_learning_lane_cron.sh`
- `python3 -m pytest helper_scripts/db/audit/test_cost_gate_reject_counterfactual.py helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q` = `70 passed`
- `python3 -m pytest helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py -q` = `12 passed`
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` = `44 passed`

註：把 cron static test 與其他 `tests/` 目錄混在同一 pytest invocation 時，當前 Python 3.10 環境有既有 namespace collection 問題；拆成同等 focused suites 後全部通過。

## 邊界

本 checkpoint 沒有做以下任何事：

- runtime source sync
- runtime artifact refresh
- cron install / crontab edit
- env edit / writer enablement
- deploy / rebuild / restart
- PG write / schema migration
- Bybit private / signed / trading call
- credential / auth / risk / order / strategy mutation
- order authority grant
- main or global Cost Gate lowering
- execution proof or promotion proof

## Review Attention

`helper_scripts/db/audit/cost_gate_reject_counterfactual.py` 現在約 1031 行，超過 repo 的 800 行 review-attention 閾值但低於 2000 行 hard cap。本次沒有拆分，原因是 horizon stability 直接復用同檔既有 side-cell、priority、classification helper；如果下一輪繼續擴張此 scorecard，應優先把 ranking / horizon stability 拆成同包 helper module。

## 派工說明

按 repo 規則，標準 feature/bug chain 是 `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM`。本次未正式派發子代理，因為範圍是既有 source-side scorecard / policy / cron / status 的窄改，無 runtime 寫入、無交易 API、無 schema migration，且主會話內已完成 focused regression。驗收風險由上述 focused tests 和邊界檢查覆蓋；若後續要 runtime activation，必須另走 runtime/operator gate。

## 下一步

下一個工程閉環不是再加 wrapper，而是 operator 授權後按既有 runbook 做 runtime source reconcile/sync、preflight、cron/writer activation，讓 demo 真正開始持續產生 rejected-signal outcome evidence。
