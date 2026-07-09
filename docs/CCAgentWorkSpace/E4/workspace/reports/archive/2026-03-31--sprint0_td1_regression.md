# E4 回歸報告：Wave 6 Sprint 0 TD-1（pipeline_bridge acquire_lease）

**日期：** 2026-03-31
**任務：** Wave 6 Sprint 0 TD-1 全量回歸
**E2 審查結論：** PASS（無 P0/P1 問題，1 個 P2 追蹤項不影響功能）

---

## E4 回歸結論：PASS

```
測試結果：2614 passed / 17 failed / 1 skipped / 24 warnings
收集總數：2632 tests collected
執行時間：63.27s
新增測試：4 個（TestPipelineBridgeDecisionLease）
新增 failure：0
pre-existing failures：17 個（清單見下）
```

---

## 驗收標準核對

| 標準 | 要求 | 實際 | 結果 |
|------|------|------|------|
| passed 總數 | ≥ 2614 | 2614 | ✅ |
| 新增 failure | 0 | 0 | ✅ |
| pre-existing failures | 17 個允許 | 17 個（完全吻合） | ✅ |
| 4 個 TestPipelineBridgeDecisionLease | 全部通過 | 4/4 PASS | ✅ |

---

## 4 個新增測試詳情

位置：`tests/test_edge_filter_integration.py::TestPipelineBridgeDecisionLease`

| 測試名稱 | 結果 | 驗證行為 |
|---------|------|---------|
| `test_td1_no_hub_fail_open_submit_proceeds` | PASS | hub=None → fail-open，submit 繼續執行 |
| `test_td1_acquire_lease_none_fail_closed_submit_blocked` | PASS | acquire_lease()=None → fail-closed，submit 被阻擋 |
| `test_td1_acquire_lease_success_submit_proceeds` | PASS | acquire_lease() 成功返回 lease → submit 繼續執行 |
| `test_td1_acquire_lease_exception_fail_closed` | PASS | acquire_lease() 拋出異常 → fail-closed，submit 被阻擋 |

---

## Pre-existing Failures（17 個，全部歸屬明確）

| 測試文件 | 測試名稱 | 失敗原因 |
|---------|---------|---------|
| `test_batch10_learning_oms.py` | `TestL2CronTrigger::test_cron_does_not_fire_twice_same_week` | asyncio event loop deprecation |
| `test_batch10_learning_oms.py` | `TestL2CronTrigger::test_cron_fires_on_sunday_utc_0` | asyncio event loop deprecation |
| `test_edge_filter_integration.py` | `TestEdgeFilterIntegration::test_edge_filter_respects_timeout` | pre-existing timeout 問題 |
| `test_integration_phase11.py` | `TestEngineTierEnforcement::test_submit_order_rejected_at_l1` | L1 tier enforcement 測試設計問題 |
| `test_integration_phase11.py` | `TestEngineTierEnforcement::test_cancel_order_rejected_at_l1` | L1 tier enforcement 測試設計問題 |
| `test_learning_tier_gate.py` | `test_l1_capabilities` | AssertionError（設計問題） |
| `test_ollama_integration.py` | `TestLocalLLMSearchProvider::test_search_uses_ollama_client` | LocalLLMSearchProvider 介面問題 |
| `test_ollama_integration.py` | `TestLocalLLMSearchProvider::test_is_available_delegates_to_client` | LocalLLMSearchProvider 介面問題 |
| `test_ollama_integration.py` | `TestLocalLLMSearchProvider::test_search_ollama_failure_returns_error` | LocalLLMSearchProvider 介面問題 |
| `test_ollama_integration.py` | `TestL1TriageLocalFallback::test_triage_falls_back_to_local` | L1TriageLocalFallback 實現問題 |
| `test_ollama_integration.py` | `TestL1TriageLocalFallback::test_triage_local_success` | L1TriageLocalFallback 實現問題 |
| `test_ollama_integration.py` | `TestL1TriageLocalFallback::test_triage_local_freetext_parsing` | L1TriageLocalFallback 實現問題 |
| `test_ollama_integration.py` | `TestL1TriageLocalFallback::test_triage_local_freetext_negative` | L1TriageLocalFallback 實現問題 |
| `test_ollama_integration.py` | `TestL1TriageLocalFallback::test_triage_local_ollama_unavailable` | L1TriageLocalFallback 實現問題 |
| `test_ollama_integration.py` | `TestL1TriageLocalFallback::test_triage_local_timeout` | L1TriageLocalFallback 實現問題 |
| `test_ollama_integration.py` | `TestL1TriageLocalFallback::test_triage_cost_zero_for_local` | L1TriageLocalFallback 實現問題 |
| `test_ollama_integration.py` | `TestL1TriageLocalFallback::test_triage_local_response_truncation` | L1TriageLocalFallback 實現問題 |

---

## 測試基準線更新

- 上次基準（Wave 5 Sprint 5b）：**2610 passed**
- 本次基準（Wave 6 Sprint 0 TD-1）：**2614 passed**
- 新增：+4 tests（TestPipelineBridgeDecisionLease × 4）

---

## 結論

**Wave 6 Sprint 0 TD-1 修復通過全量回歸驗收，可以進行 commit。**

- TD-1 修復（pipeline_bridge acquire_lease）的 4 個新測試全部通過
- 無新增 regression
- 17 個 pre-existing failures 與預期完全一致
- 測試基準線從 2610 提升至 2614
