# Cost-Gate Reject Materializer

## 結論

我們不再只做 ranking/report。這次新增 `helper_scripts/research/cost_gate_learning_lane/reject_materializer.py`，把已經被 runtime 寫入 PG 的 `learning.decision_features` cost-gate rejects 轉成現有 learning ledger contract：

`cost_gate_demo_learning_lane_adapter_v1` / `probe_admission_decision`

這讓已記錄但尚未進 learning ledger 的 blocked signals，可以直接進入既有：

`price_observations -> outcome_refresh -> outcome_review`

從而形成 per-signal blocked-outcome evidence，而不是只停留在聚合 scorecard。

## 行為

- Source 可以是 `--source-pg` 或 local `--source-rows`。
- 必須提供 current demo-learning plan。
- 每條 reject 走同一個 `evaluate_probe_admission`。
- Materializer 固定 `adapter_enabled=false`，不暴露任何 order authority。
- 輸出 decision 會是 `ORDER_AUTHORITY_NOT_GRANTED`、`SIDE_CELL_NOT_SELECTED` 等 fail-closed evidence。
- 默認只輸出 batch JSON。
- 只有顯式 `--append-ledger` 才會 append JSONL ledger。

## Runtime Read-Only Probe

在 `trade-core` 上只讀查詢 PG，確認 extractor schema 對得上：

- latest sampled rows time：`2026-06-21 20:47:59+02`
- engine mode：`demo`
- strategy：`ma_crossover`
- symbol：`BTCUSDT`
- side：`Buy`
- reject reason：`cost_gate_js_demo_negative_edge`
- columns：`ts / ts_ms / context_id / engine_mode / strategy_name / symbol / side / reject_reason_code / last_price`

本次沒有執行 ledger append。

## 邊界

- Source/test/docs + read-only runtime PG schema inspection only。
- 不 runtime source sync。
- 不安裝 cron。
- 不啟 writer。
- 不 append ledger。
- 不寫 PG / schema migration。
- 不連 Bybit private/signed/trading API。
- 不下單。
- 不改 auth / risk / strategy / runtime config。
- 不降低 main Cost Gate。
- 不構成 execution proof 或 promotion proof。

## 驗證

- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/db/audit/test_cost_gate_reject_counterfactual.py -q`：100 passed
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/reject_materializer.py helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py helper_scripts/db/audit/cost_gate_reject_counterfactual.py`：PASS
- `git diff --check`：PASS
- Runtime PG read-only extractor-shape probe：PASS
