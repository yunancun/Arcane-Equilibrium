# 2026-06-22 -- Runtime killboard learning worklist v5

## 結論

v359 已讓 `alpha_discovery` plan 產生 `learning_worklist`，但 runtime killboard 的頂層摘要和 history row 還沒有露出 top learning task。這會讓運營或 cron 歷史只能看到 alpha/probe/actionability flags，不能直接看到下一個學習閉環應該做什麼。

本輪把 runtime killboard schema bump 到：

```text
alpha_discovery_runtime_killboard_v5
```

並把 `learning_worklist` 的狀態與 top task 摘要鏡像到 `killboard` 和 history JSONL。

## 改動

- `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`
  - `RUNTIME_KILLBOARD_SCHEMA_VERSION`：v4 -> v5
  - top-level payload 新增 `learning_worklist`
  - `killboard` 新增：
    - `learning_worklist_status`
    - `learning_task_count`
    - `learning_promotion_ready_count`
    - `learning_operator_required_count`
    - `learning_runtime_mutation_required_count`
    - `learning_engineering_actionable_count`
    - `top_learning_task_*`
  - `_history_row()` 同步寫入 worklist status、task count、top task type/actionability/operator/runtime-mutation flags
- `helper_scripts/research/tests/test_alpha_discovery_throughput.py`
  - 更新 schema v5 expectation
  - 驗證 latest artifact 中 `learning_worklist` 與 `discovery_plan.learning_worklist` 一致
  - 驗證 history JSONL 寫入 top learning task 摘要

## 行為邊界

這只是 runtime artifact summarization。它不刷新 runtime artifact、不安裝 cron、不同步 source、不啟 writer、不寫 PG、不連 Bybit、不下單、不給 probe/order/promotion authority。

## 驗證

- `PYTHONPATH=helper_scripts/research python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/tests/test_alpha_discovery_throughput.py`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py` = `46 passed`
