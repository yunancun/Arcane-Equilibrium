# E4 回歸測試報告 — Sprint 5a（Position Sizing + Paper/Demo Sync）

**日期：** 2026-03-31
**執行人：** E4（Test Engineer）
**工作目錄：** `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/`

---

## 1. 全量回歸結果

| 項目 | 數值 |
|------|------|
| **收集總數** | 2594 |
| **PASSED** | **2576** |
| **FAILED** | 17（全部為 pre-existing） |
| **SKIPPED** | 1 |
| **執行時間** | 37.60s |

**總體結論：✅ PASS（2576 passed ≥ 2575 目標，無新增 failure）**

---

## 2. test_strategist_agent.py 測試結果

`tests/test_strategist_agent.py`

| 測試類別 | 測試名稱 | 結果 |
|----------|----------|------|
| TestScoutStrategistChain | test_intel_object_triggers_handle_intel | ✅ PASS |
| TestScoutStrategistChain | test_intel_received_counter_increments | ✅ PASS |
| TestH1ThoughtGate | test_h1_all_pass | ✅ PASS |
| TestH1ThoughtGate | test_h1_budget_skip | ✅ PASS |
| TestH1ThoughtGate | test_h1_complexity_skip | ✅ PASS |
| TestH1ThoughtGate | test_h1_cooldown_hit | ✅ PASS |
| TestH1ThoughtGate | test_h1_timeout_fallback | ✅ PASS |
| TestH1ThoughtGate | test_h2_budget_exceeded | ✅ PASS |
| TestH1ThoughtGate | test_h2_budget_ok | ✅ PASS |
| TestH1ThoughtGate | test_h2_no_cost_tracker | ✅ PASS |
| TestH1ThoughtGate | test_h3_routes_l1_27b | ✅ PASS |
| TestH1ThoughtGate | test_h3_routes_l1_9b | ✅ PASS |
| TestH1ThoughtGate | test_h3_routes_l2_thread | ✅ PASS |
| TestStrategistShadowFalse | test_shadow_false_intent_added_to_pending | ✅ PASS |
| TestStrategistShadowFalse | test_shadow_false_pending_intents_capped | ✅ PASS |

**小計：15/15 PASS**

---

## 3. H0 Gate 測試結果（-k "H0"）

`tests/test_h0_gate.py` 等相關 H0 測試

**94/94 PASS**（全部通過）

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

## 6. 測試基準變化

| 時間點 | Passed | 備注 |
|--------|--------|------|
| Sprint 0 回歸（G-05 + G-01 後） | 2561 | 上一個基準 |
| Sprint 5a 回歸（Wave 5a/5b 後） | **2576** | 本次基準 |
| 差值 | **+15** | 新增 test_strategist_agent.py 15 個測試 |

---

## 7. 注意事項（非阻斷）

1. **Pydantic V2 Deprecation Warnings**：`scout_routes.py` 中使用了 V1 style `@validator` 和 `max_items`，應在下一個維護 Sprint 遷移至 V2 語法。
2. **asyncio event loop DeprecationWarning**：`pipeline_bridge.py` 中有舊式 `asyncio.get_event_loop()` 調用，不影響當前測試結果。
3. **PytestCollectionWarning**：`fastapi/applications.py` 的 `test_app` 實例觸發收集警告，無需處理。

---

## 8. 結論

**✅ Sprint 5a 回歸：PASS**

- 測試基準更新：**2576 passed**（前次基準 2561，+15 新測試）
- test_strategist_agent.py：全部通過（15/15）
- H0 Gate 測試（-k "H0"）：全部通過（94/94）
- 無新增 failure，17 個 pre-existing failures 保持不變
- 目標 ≥ 2575：達成（2576 ≥ 2575）
- 系統可安全進入下一個開發 Sprint（P3 批次：GUI 術語友好化）
