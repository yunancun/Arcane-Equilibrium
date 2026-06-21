# 2026-06-22 -- Alpha learning worklist completion gates

## 結論

v359/v360 讓 `alpha_discovery` 產生 learning worklist，並把 top learning task 顯示到 runtime killboard。下一個缺口是：task 只有「下一步做什麼」，但沒有「什麼證據算做完」。

本輪把 worklist schema 升到：

```text
alpha_learning_worklist_v2
```

每個 task 現在都帶：

- `completion_gate`
- `completion_status`
- `completion_evidence_required`

這讓學習閉環從 suggestion 進一步變成 machine-checkable work item。

## 改動

- `helper_scripts/research/alpha_discovery_throughput/learning_worklist.py`
  - `alpha_learning_worklist_v1` -> `alpha_learning_worklist_v2`
  - 按 task type 生成完成 gate
  - 按 task type 生成必需證據清單
  - 保持 `completion_status=PENDING_EVIDENCE`，不假裝任務已完成
- `helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py`
  - 覆蓋 runtime source reconcile completion gate
  - 覆蓋 MM train-confirmed current-fee signal completion evidence
  - 覆蓋 Polymarket replay-history completion evidence
  - 覆蓋 formal promotion review completion evidence

## 例子

- `runtime_source_reconcile`
  - gate：`runtime_source_synced_clean_expected_head_match`
  - evidence：runtime source activation `SYNCED_CLEAN`、expected head match、dirty/behind = 0、re-run activation preflight
- `mm_signal_search`
  - gate：`train_confirmed_sample_gated_current_fee_gross_edge_found`
  - evidence：train/holdout sample-gated gross edge clears current fee round trip
- `polymarket_replay_history`
  - gate：`dated_replay_history_ready_for_aeg_recheck`
  - evidence：history status ready、days >= min days、PBO/breadth fields present

## 驗證

- `PYTHONPATH=helper_scripts/research python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/learning_worklist.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py` = `2 passed`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_throughput.py` = `44 passed`

## 邊界

Source/test/docs only. No runtime source sync, no artifact refresh, no crontab/env edit, no deploy/rebuild/restart, no PG write/schema migration, no Bybit private/signed/trading call, no credential/auth/risk/order/strategy mutation, no Cost Gate lowering, no order authority, no execution proof, no promotion proof.
