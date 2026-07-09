# E4 測試報告 — Sprint 5b 全量回歸

**日期：** 2026-03-31
**執行人：** E4（Test Engineer）
**工作目錄：** `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/`
**任務：** Sprint 5b 全量回歸驗收（目標 ≥ 2600 passed，≤ 17 failures）

---

## 1. 執行結果摘要

| 指標 | 數值 | 目標 | 結論 |
|------|------|------|------|
| passed | **2610** | ≥ 2600 | ✅ 達成（+10） |
| failed | **17** | ≤ 17 | ✅ 達成（全部 pre-existing） |
| skipped | 1 | — | ✅ 不變 |
| collected | 2628 | — | — |
| 執行時間 | ~59.65s | — | — |

**最終結論：PASS**

---

## 2. 17 個 Pre-existing Failures 確認

所有 17 個 failures 均與上一次基準（Sprint 5b-5，2599 passed）記錄的清單完全一致，無新增 failure。

| 文件 | 測試名稱 | 數量 |
|------|---------|------|
| `test_batch10_learning_oms.py` | `TestL2CronTrigger::test_cron_does_not_fire_twice_same_week` | 1 |
| `test_batch10_learning_oms.py` | `TestL2CronTrigger::test_cron_fires_on_sunday_utc_0` | 1 |
| `test_edge_filter_integration.py` | `TestEdgeFilterIntegration::test_edge_filter_respects_timeout` | 1 |
| `test_integration_phase11.py` | `TestEngineTierEnforcement::test_submit_order_rejected_at_l1` | 1 |
| `test_integration_phase11.py` | `TestEngineTierEnforcement::test_cancel_order_rejected_at_l1` | 1 |
| `test_learning_tier_gate.py` | `test_l1_capabilities` | 1 |
| `test_ollama_integration.py` | `TestLocalLLMSearchProvider` (3 tests) | 3 |
| `test_ollama_integration.py` | `TestL1TriageLocalFallback` (8 tests) | 8 |
| **合計** | | **17** |

---

## 3. 新增測試通過確認（Sprint 5b）

### Step 3：test_h_chain_integration.py + test_scout_worker.py

```
16 passed in 20.07s
```

| 文件 | 測試數 | 結果 |
|------|--------|------|
| `test_h_chain_integration.py` (TestPrinciple14OllamaFallback) | 6 | ✅ 全部 PASS |
| `test_scout_worker.py` | 10 | ✅ 全部 PASS |

### Step 4：roi_basis / cost_tracker / ollama_call 標記測試

```
7 passed, 2621 deselected in 2.92s
```

所有 7 個相關測試通過。

---

## 4. 基準線更新

| 版本 | passed | failed | skipped |
|------|--------|--------|---------|
| Sprint 0 回歸 | 2561 | 17 | 1 |
| Sprint 5a 回歸 | 2576 | 17 | 1 |
| Sprint 5b-5 P14 測試 | 2599 | 17/18* | 1 |
| **Sprint 5b 全量回歸（本次）** | **2610** | **17** | **1** |

*Sprint 5b-5 時記錄 17/18 failed（其中 1 個是臨時新增但隨後修復的）

相較上次基準（2599）新增：**+11 tests**

---

## 5. 結論

**PASS**

- 測試總數 2610 ≥ 2600 目標 ✅
- 17 failures 均為 pre-existing，無新增 failure ✅
- Sprint 5b 新增測試（h_chain_integration × 6 + scout_worker × 10）全部通過 ✅
- roi_basis / cost_tracker / ollama_call 相關測試（7 個）全部通過 ✅
- 系統健康度：demo_only 模式，live_execution_allowed = false，治理 fail-closed 正常
