# 2026-06-22 -- Alpha discovery learning worklist

## 結論

本輪把 `alpha_discovery` 從「列 blocker」往「自主學習 backlog」推進了一步。

原本 `profitability_blocker_scorecard` 已能回答為何沒有可推廣 alpha，但下游仍需要人工讀 `primary_blocker` / `next_trigger` 才知道下一輪應該做哪種學習實驗。現在 `build_discovery_plan()` 會附帶 `learning_worklist`，把 blocker rows 轉成可排序的 learning tasks。

## 改動

- 新增 `helper_scripts/research/alpha_discovery_throughput/learning_worklist.py`
  - schema：`alpha_learning_worklist_v1`
  - 從 blocker rows 派生 `task_type`、`learning_objective`、`priority_score`、`actionability`
  - 明確標記 `requires_operator_authorization` 與 `runtime_mutation_required`
  - 保留 compact evidence，例如 MM cost gap、Polymarket replay history 天數、cost-gate source/git/ledger 狀態
- `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
  - 在 discovery plan 中新增 `learning_worklist`
  - 巨型 `discovery_loop.py` 只做接線，新邏輯拆到獨立 module
- 新增 `helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py`
  - 覆蓋 cost-gate runtime source reconcile 優先級
  - 覆蓋 MM train-confirmed low-friction signal search
  - 覆蓋 promotion-ready 任務優先於 Polymarket replay-history 補證

## 行為語義

`learning_worklist` 是 artifact-only recommendation，不是 order authority、probe authority、promotion proof，亦不放寬 Cost Gate。

示例 task type：

- `runtime_source_reconcile`：runtime source/dirty/behind 需要 operator-approved reconcile
- `cost_gate_learning_activation`：先啟用 bounded rejected-signal learning，再談 Cost Gate 調整
- `mm_signal_search`：尋找 train-confirmed、sample-gated、可清 current-fee 的低摩擦 MM signal
- `polymarket_replay_history`：補 dated replay history / PBO / breadth / execution evidence
- `promotion_review`：候選 evidence 已可進 formal AEG/QC/MIT review

## 驗證

- `PYTHONPATH=helper_scripts/research python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/learning_worklist.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py` = `2 passed`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_throughput.py` = `44 passed`

## 邊界

Source/test/docs only. No runtime source sync, no artifact refresh, no crontab/env edit, no deploy/rebuild/restart, no PG write/schema migration, no Bybit private/signed/trading call, no credential/auth/risk/order/strategy mutation, no Cost Gate lowering, no order authority, no execution proof, no promotion proof.

