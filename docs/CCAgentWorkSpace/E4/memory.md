# E4 Memory — 工作記憶

## 項目上下文（2026-03-31）

- 當前 Wave：Wave 5 完成（5a Position Sizing + 5b Paper/Demo 同步修復）
- 測試基準：**2610 passed**（Sprint 5b 全量回歸後更新）
- 系統模式：demo_only

## 工作記憶

### 2026-03-31 Sprint 5b 全量回歸

**結論：PASS**
- 總計：2610 passed, 17 failed（全部 pre-existing）, 1 skipped
- 收集：2628 tests collected
- 執行時間：~59.65s
- 目標 ≥ 2600：✅ 達成（2610 passed）
- 17 pre-existing failures 清單與預期完全一致，無新增 failure
- 測試基準更新：**2610 passed**（較上次 2599 +11）

**新增測試（相較上次基準 2599）：+11 tests**
- test_h_chain_integration.py（TestPrinciple14OllamaFallback × 6）：全部 PASS
- test_scout_worker.py（× 10）：全部 PASS
- roi_basis / cost_tracker / ollama_call 標記測試（7 個）：全部 PASS

### 2026-03-31 Sprint 5b-5 根原則 14 集成測試（Principle 14 Ollama Fallback）

**結論：PASS**
- 新增測試：6（TestPrinciple14OllamaFallback）
- 文件位置：`tests/test_h_chain_integration.py`
- 全量回歸：2599 passed, 17/18 failed（全部 pre-existing），1 skipped
- 目標 ≥ 2576 + 6 = 2582：✅ 達成（2599 passed）

**6 個測試行為驗證：**
1. `test_ollama_unavailable_strategist_uses_heuristic`：is_available=False → judge_edge 不被調用，heuristic_evaluations 遞增
2. `test_ollama_unavailable_h1_budget_check_passes`：cost_tracker=None → _h1_check_budget() 返回 True（fail-open）
3. `test_ollama_unavailable_pipeline_bridge_processes_intents`：PipelineBridge._process_pending_intents() 無 Ollama 時不崩潰
4. `test_ollama_unavailable_h0_gate_still_blocks_bad_intents`：H0 Gate 確定性邏輯不依賴 Ollama，freshness check 仍阻擋
5. `test_ollama_unavailable_executor_still_applies_fail_closed`：acquire_lease()=None → ExecutorAgent 拒絕執行（原則 3 不依賴 Ollama）
6. `test_ollama_crash_mid_evaluation_falls_back`：_ai_evaluate 中 ConnectionError → catch + heuristic fallback + error 計數

**關鍵發現：**
- PipelineBridge 需要 3 個必填位置參數（kline_manager/indicator_engine/signal_engine）
- 所有降級邏輯均在 _evaluate_edge() 中正確實現（is_available=False 或異常均走 heuristic）
- H0 Gate 完全不依賴 Ollama（純確定性）
- ExecutorAgent 的 Principle 3 執行與 Ollama 狀態無關

**測試基準更新：2599 passed**（較上次 2576 +23）

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
| 2026-03-31 | Sprint 5b 全量回歸（2610 passed，Sprint 5b 最終驗收） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--sprint5b_regression.md` |
| 2026-03-31 | Sprint 5b-5 根原則 14 集成測試（Principle 14 Ollama Fallback，6 tests） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--sprint5b_p14_tests.md` |
| 2026-03-31 | Sprint 5a 全量回歸（Position Sizing + Paper/Demo Sync） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--sprint5a_regression.md` |
| 2026-03-31 | Sprint 0 全量回歸（G-05 + G-01） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--sprint0_regression.md` |
