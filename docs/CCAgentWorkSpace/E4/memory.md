# E4 Memory — 工作記憶

## 項目上下文（2026-03-31）

- 當前 Wave：Wave 5 完成（5a Position Sizing + 5b Paper/Demo 同步修復）
- 測試基準：**2576 passed**（Sprint 5a 回歸後更新）
- 系統模式：demo_only

## 工作記憶

### 2026-03-31 Sprint 5a 回歸（Position Sizing + Paper/Demo Sync）

**結論：PASS**
- 總計：2576 passed, 17 failed（pre-existing）, 1 skipped
- 收集：2594 tests collected
- 執行時間：~37.60s
- 目標 ≥ 2575：✅ 達成（2576 passed）
- 17 pre-existing failures 清單與預期完全一致，無新增 failure

**新增測試（相較上次基準 2561）：+15 tests**
- test_strategist_agent.py：15 tests（TestScoutStrategistChain 2 + TestH1ThoughtGate 11 + TestStrategistShadowFalse 2）
- H0 Gate 測試（test_h0_gate.py）：94 tests，全部通過

**已知 pre-existing failures（17 個，全部歸屬明確）：**
- test_batch10_learning_oms.py（2）：TestL2CronTrigger（asyncio event loop deprecation）
- test_edge_filter_integration.py（1）：test_edge_filter_respects_timeout
- test_integration_phase11.py（2）：TestEngineTierEnforcement（L1 reject submit/cancel）
- test_learning_tier_gate.py（1）：test_l1_capabilities
- test_ollama_integration.py（11）：LocalLLMSearchProvider（3）+ L1TriageLocalFallback（8）

### 2026-03-31 Sprint 0 回歸（G-05 + G-01）

**結論：PASS**
- 總計：2561 passed, 17 failed（pre-existing）, 1 skipped
- G-05 TestExecutorAgentDecisionLease：6/6 PASS（test_26～test_31）
- G-01 test_layer2.py：79/79 PASS
- 17 pre-existing failures 清單與預期完全一致，無新增 failure

**重要教訓：**
- pytest 收集 `test_app` 時有 PytestCollectionWarning（fastapi app instance，非真正問題）
- Pydantic V1 deprecated warnings 在 scout_routes.py（不影響功能）

## 報告索引

| 日期 | 任務 | 文件位置 |
|------|------|---------|
| 2026-03-31 | Sprint 5a 全量回歸（Position Sizing + Paper/Demo Sync） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--sprint5a_regression.md` |
| 2026-03-31 | Sprint 0 全量回歸（G-05 + G-01） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--sprint0_regression.md` |
