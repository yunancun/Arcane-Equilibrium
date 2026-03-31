# E4 回歸測試報告 — Sprint 0（G-05 + G-01）

**日期：** 2026-03-31
**執行人：** E4（Test Engineer）
**工作目錄：** `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/`

---

## 1. 全量回歸結果

| 項目 | 數值 |
|------|------|
| **總測試數** | 2579（collected） |
| **PASSED** | **2561** |
| **FAILED** | 17（全部為 pre-existing） |
| **SKIPPED** | 1 |
| **執行時間** | 38.97s |

**總體結論：✅ PASS（2561 passed ≥ 2561，無新增 failure）**

---

## 2. G-05 Decision Lease 測試結果（TestExecutorAgentDecisionLease）

`tests/test_batch11_executor_exchange.py::TestExecutorAgentDecisionLease`

| 測試名稱 | 結果 |
|----------|------|
| test_26_no_governance_hub_allows_execution | ✅ PASS |
| test_27_acquire_lease_returns_none_rejects_execution | ✅ PASS |
| test_28_acquire_lease_success_allows_execution | ✅ PASS |
| test_29_lease_rejection_stats_updated | ✅ PASS |
| test_30_lease_rejection_produces_report | ✅ PASS |
| test_31_governance_hub_stored_as_attribute | ✅ PASS |

**小計：6/6 PASS**

---

## 3. G-01 Layer2 測試結果

`tests/test_layer2.py`

**79/79 PASS**（全部通過，1 個 DeprecationWarning 不影響功能）

---

## 4. 17 個 Pre-existing Failures 核對

| 測試文件 | 失敗數 | 測試名稱 | 狀態 |
|----------|--------|----------|------|
| test_batch10_learning_oms.py | 2 | TestL2CronTrigger::test_cron_does_not_fire_twice_same_week | pre-existing ✅ |
| test_batch10_learning_oms.py | | TestL2CronTrigger::test_cron_fires_on_sunday_utc_0 | pre-existing ✅ |
| test_edge_filter_integration.py | 1 | TestEdgeFilterIntegration::test_edge_filter_respects_timeout | pre-existing ✅ |
| test_integration_phase11.py | 2 | TestEngineTierEnforcement::test_submit_order_rejected_at_l1 | pre-existing ✅ |
| test_integration_phase11.py | | TestEngineTierEnforcement::test_cancel_order_rejected_at_l1 | pre-existing ✅ |
| test_learning_tier_gate.py | 1 | test_l1_capabilities | pre-existing ✅ |
| test_ollama_integration.py | 11 | TestLocalLLMSearchProvider（3）+ TestL1TriageLocalFallback（8） | pre-existing ✅ |

**合計：17 個，與 pre-existing 清單完全一致。無新增 failure。**

---

## 5. 新增 Failure？

**否。** 所有 17 個 failures 均在預期清單內，無任何新增 failure。

---

## 6. 注意事項（非阻斷）

1. **Pydantic V2 Deprecation Warnings**：`scout_routes.py` 中使用了 V1 style `@validator` 和 `max_items`，應在下一個維護 Sprint 遷移至 V2 語法。
2. **asyncio event loop DeprecationWarning**：`test_layer2.py::TestToolExecutor::test_unknown_tool` 和 `pipeline_bridge.py` 中有舊式 `asyncio.get_event_loop()` 調用，不影響當前測試結果。
3. **PytestCollectionWarning**：`fastapi/applications.py` 的 `test_app` 實例觸發收集警告，無需處理。

---

## 7. 結論

**✅ Sprint 0 回歸：PASS**

- 測試基準更新：**2561 passed**（前次基準 2555，+6 新測試）
- G-05 Decision Lease 測試：全部通過（6/6）
- G-01 Layer2 測試：全部通過（79/79）
- 無新增 failure，17 個 pre-existing failures 保持不變
- 系統可安全進入下一個開發 Sprint
