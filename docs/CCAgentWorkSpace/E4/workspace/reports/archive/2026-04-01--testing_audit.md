# E4 審計報告：全程序測試覆蓋評估
# E4 Audit: Full-Program Testing Assessment
# 日期：2026-04-01
# 對比基準：2026-03-31 E4 測試報告
# 當前測試基準：3310 passed / 21 failed / 17 errors / 1 skipped（3349 collected）

---

## 執行摘要 / Executive Summary

| 指標 | 2026-03-31 | 2026-04-01 | 變化 |
|------|-----------|-----------|------|
| 測試文件數（項目自有） | 71 | 96 | **+25** |
| 總收集測試 | ~2,480 | 3,349 | **+869** |
| passed | ~2,480 | 3,310 | **+830** |
| failed（pre-existing） | 17 | 17 | 持平 |
| failed（新增） | 0 | 4 | **+4 NEW** |
| errors | 0 | 17 | **+17 NEW** |
| app 模塊數 | 53 | 61 | **+8** |
| 完全無直接測試的模塊 | 19 | 18 | **-1（改善）** |
| 估算整體覆蓋率 | ~62% | **~68%** | **+6pp** |
| 高風險未覆蓋模塊 | 9 項 | 7 項 | **-2（改善）** |

**整體評估**：自 March 31 以來測試數量增長 35%（+869），新增 25 個測試文件。Phase 2/3 新增模塊（TruthSourceRegistry、BacktestEngine、ExperimentLedger、EvolutionEngine）均已有專門測試。governance_routes 從 CRITICAL 10% 提升至約 45%。pipeline_bridge 從 CRITICAL 15% 提升至約 50%（新增 coverage + concurrency + spot 測試文件）。主要風險敞口從路由層轉向 4 個新增回歸失敗和 17 個 test_session9_fixes 收集錯誤。

---

## 一、March 31 問題修復進度核實

### 1.1 CRITICAL 問題（2 項）

| # | March 31 問題 | 狀態 | 說明 |
|---|-------------|------|------|
| 2.1 | pipeline_bridge.py 15% 覆蓋 | **部分修復** | 新增 test_pipeline_bridge_coverage.py（80 cases）+ test_pipeline_bridge_concurrency.py（17 cases）+ test_pipeline_bridge_spot.py（20 cases）= **117 個新測試**。從 5 cases → 125+ cases。估算覆蓋率 15% → ~50%。核心 _process_pending_intents / _check_stops 現已有覆蓋。仍缺少 _invoke_scout_scan / _try_l2_cron_trigger 直接測試 |
| 2.2 | governance_routes.py 10% 覆蓋 | **部分修復** | 新增 test_governance_routes_coverage.py（110 cases）+ test_governance_routes_auth.py（13 cases）= **123 個新測試**。估算覆蓋率 10% → ~45%。仍有端點未覆蓋（promote_learning_tier HTTP 層、部分 de-escalation 路徑） |

### 1.2 HIGH 問題（7 項）

| # | March 31 問題 | 狀態 | 說明 |
|---|-------------|------|------|
| 2.3 | bybit_public_ws_listener 20% | **已修復** | test_ws_listener_coverage.py 新增 50 cases。reconnect/on_close/on_error/malformed JSON 全覆蓋。覆蓋率 20% → ~65% |
| 2.4 | bybit_demo_connector 8% | **已修復** | test_demo_connector_coverage.py 新增 41 cases（含 HMAC _sign 直接測試）。覆蓋率 8% → ~60% |
| 2.5 | market_data_dispatcher 35% | **未修復** | 仍只有 test_market_data.py（35 cases），無直接 dispatcher 測試文件。覆蓋率仍 ~35% |
| 2.6 | strategist_agent 40% | **部分修復** | test_strategist_agent.py 從 18 → 36 cases。新增 shadow=False / H1 ThoughtGate / Scout chain 測試。覆蓋率 40% → ~55% |
| 2.7 | phase2_strategy_routes 30% | **未修復** | test_phase2_routes.py 仍 30 cases。無新增。覆蓋率仍 ~30% |
| 2.8 | paper_trading_routes 35% | **未修復** | 無直接路由測試文件。仍依賴 test_paper_trading.py 間接覆蓋。覆蓋率仍 ~35% |
| 2.9 | scout_routes 40% | **未修復** | 仍只有 test_scout_integration.py（45 cases）覆蓋邏輯層，路由端點未直接測試 |

### 1.3 測試質量問題（14 項）

| # | March 31 問題 | 狀態 |
|---|-------------|------|
| 3.1 | assert True 空洞斷言 | **未修復** — test_risk_manager.py + test_scout_integration.py 仍存在 |
| 3.2 | Pipeline Bridge 測試不足 | **已修復** — 新增 117+ tests |
| 3.3 | StopManager 邊界缺失 | **未修復** — 仍 17 cases |
| 3.4 | snapshot 系列測試稀少 | **未修復** — 仍 3+3+3=9 cases |
| 3.5 | "not worth" 回歸測試位置不當 | **未修復** — 仍在 test_ollama_integration 而非 test_layer2 |
| 3.6 | governance_hub TTL 分級未測試 | **未修復** |
| 3.7 | Edge Filter fail-open 端到端 | **未修復** |
| 3.8 | OMS SM-03 disabled 退回舊版 | **未修復** |
| 3.9 | 並發測試局限 GovernanceHub | **部分修復** — 新增 test_pipeline_bridge_concurrency.py（17 cases）+ test_message_bus_load.py（11 cases） |
| 3.10 | Paper Trading 邊界 qty=0 | **已修復** — risk_manager.py 現有 qty<=0/price<=0 fail-closed 守衛 + 5 邊界測試 |
| 3.11 | Reconciliation 並發 | **未修復** |
| 3.12 | L2 Daily Budget Routes 層 | **未修復** |
| 3.13 | Demo Connector HMAC 簽名 | **已修復** — test_demo_connector_coverage.py 含 _sign() 直接測試 |
| 3.14 | WS 訂閱消息格式 | **已修復** — test_ws_listener_coverage.py 含訂閱測試 |

**修復率：14 項中 6 項已修復或部分修復（43%），8 項未修復**

---

## 二、測試覆蓋率總覽（按模塊）

### 2.1 控制 API 模塊（`control_api_v1/app/`，61 個模塊）

| 模塊 | LOC | 直接測試 cases | 估算覆蓋率 | 風險等級 | vs 3/31 |
|------|-----|---------------|-----------|---------|---------|
| governance_hub.py | 1,889 | 62 | ~82% | LOW | +11 |
| authorization_state_machine.py | 724 | 73 | ~85% | LOW | = |
| decision_lease_state_machine.py | 740 | 58 | ~82% | LOW | = |
| risk_governor_state_machine.py | 858 | 56 | ~80% | LOW | = |
| risk_manager.py | 1,492 | 95 | ~78% | LOW | +11 |
| paper_trading_engine.py | 2,056 | 58+46+32=136 | ~75% | LOW | +32(inverse) |
| oms_state_machine.py | 693 | 53 | ~80% | LOW | = |
| paper_live_gate.py | 738 | 58 | ~75% | LOW | = |
| h0_gate.py | 832 | 94+5=99 | ~85% | LOW | **NEW** |
| truth_source_registry.py | 821 | 52 | ~75% | LOW | **NEW** |
| experiment_ledger.py | 617 | 35 | ~72% | LOW | **NEW** |
| experiment_routes.py | 327 | 25 | ~70% | MEDIUM | **NEW** |
| evolution_routes.py | 220 | 10 | ~60% | MEDIUM | **NEW** |
| symbol_category_registry.py | 153 | 19 | ~80% | LOW | **NEW** |
| scout_worker.py | 187 | 10 | ~65% | MEDIUM | **NEW** |
| layer2_types.py | 477 | (via test_layer2) | ~90% | LOW | = |
| layer2_cost_tracker.py | 610 | (via test_layer2) | ~85% | LOW | = |
| layer2_tools.py | 906 | (via test_layer2) | ~78% | LOW | = |
| layer2_engine.py | 730 | 79+(via ollama) | ~65% | MEDIUM | = |
| layer2_routes.py | 410 | (via test_layer2) | ~70% | MEDIUM | = |
| learning_tier_gate.py | 712 | 59 | ~80% | LOW | = |
| multi_agent_framework.py | 927 | 71 | ~75% | LOW | = |
| perception_data_plane.py | (est 600) | 63 | ~78% | LOW | = |
| reconciliation_engine.py | 938 | 55 | ~78% | LOW | +11 |
| recovery_approval_gate.py | (est 500) | 56 | ~78% | LOW | = |
| change_audit_log.py | (est 600) | 44 | ~75% | LOW | = |
| audit_persistence.py | (est 400) | 35 | ~72% | LOW | = |
| portfolio_risk_control.py | (est 450) | 36 | ~70% | MEDIUM | = |
| scanner_rate_limiter.py | (est 400) | 51 | ~80% | LOW | = |
| trade_attribution.py | 958 | 45+10=55 | ~75% | LOW | = |
| ttl_enforcer.py | (est 400) | 57 | ~82% | LOW | = |
| market_regime.py | (est 500) | 49 | ~75% | LOW | = |
| shadow_decision_builder.py | (est 400) | 26 | ~72% | LOW | = |
| incident_event_model.py | (est 400) | 51 | ~80% | LOW | = |
| data_source_enforcer.py | (est 500) | 58 | ~78% | LOW | = |
| ollama_client.py | 484 | 28 | ~68% | MEDIUM | = |
| strategist_agent.py | 994 | 36 | ~55% | **HIGH** | +18 |
| analyst_agent.py | 790 | 17+23=40 | ~55% | MEDIUM | **NEW**(registry) |
| guardian_agent.py | (est 400) | 21 | ~55% | MEDIUM | = |
| executor_agent.py | (est 350) | 14 | ~50% | MEDIUM | = |
| lease_ttl_config.py | (est 300) | 47 | ~85% | LOW | = |
| protective_order_manager.py | 866 | 46 | ~60% | MEDIUM | = |
| **pipeline_bridge.py** | **1,937** | **125+** | **~50%** | **HIGH** | **+120 ↑** |
| **governance_routes.py** | **1,928** | **123+** | **~45%** | **HIGH** | **+114 ↑** |
| **market_data_dispatcher.py** | **431** | **35** | **~35%** | **HIGH** | = |
| **scout_routes.py** | **718** | **45(indirect)** | **~40%** | **HIGH** | = |
| **phase2_strategy_routes.py** | **1,541** | **30** | **~30%** | **HIGH** | = |
| **paper_trading_routes.py** | **1,006** | **(indirect)** | **~35%** | **HIGH** | = |
| risk_routes.py | 246 | 8(indirect) | ~60% | MEDIUM | = |
| bybit_demo_connector.py | 410 | 41 | ~60% | MEDIUM | **+39 ↑** |
| bybit_demo_sync.py | 269 | 1(indirect) | ~5% | **HIGH** | = |
| bybit_public_ws_listener.py | 460 | 50 | ~65% | MEDIUM | **+48 ↑** |
| backtest_routes.py | 262 | 15 | ~65% | MEDIUM | **NEW** |
| grafana_data_writer.py | 359 | 0 | ~0% | MEDIUM | = |
| telegram_alerter.py | 172 | (indirect) | ~10% | LOW | = |
| runtime_bridge.py | 179 | 3 | ~50% | MEDIUM | = |
| paper_trading_metrics.py | 438 | 22 | ~55% | MEDIUM | = |

### 2.2 local_model_tools 模塊

| 模塊 | LOC | 測試 cases | 估算覆蓋率 | 風險等級 | vs 3/31 |
|------|-----|-----------|-----------|---------|---------|
| backtest_engine.py | 1,209 | 57 | ~65% | MEDIUM | **NEW** |
| evolution_engine.py | 539 | 31 | ~70% | LOW | **NEW** |
| indicator_engine.py | 392 | 58 | ~78% | LOW | = |
| signal_generator.py | 1,212 | 38 | ~55% | MEDIUM | = |
| kline_manager.py | 1,055 | 36 | ~60% | MEDIUM | = |
| stop_manager.py | 319 | 17 | ~60% | MEDIUM | = |
| strategy_orchestrator.py | 471 | 18 | ~55% | MEDIUM | = |
| strategy_auto_deployer.py | 685 | 0 | **~0%** | **HIGH** | = |
| market_scanner.py | 333 | 16 | ~60% | MEDIUM | **NEW** |

---

## 三、正常路徑測試評估

### 3.1 治理核心（GovernanceHub + 4 State Machines）

**評分：A-（優秀）** — 無變化

- SM-01 授權完整生命週期 ✅
- SM-02 Decision Lease 獲取/釋放 ✅
- SM-04 風控等級強制覆蓋 ✅
- EX-04 對賬觸發 ✅
- fail-closed 行為全覆蓋 ✅
- **新增**：H0 Gate 5 類確定性 check 的 happy-path 全覆蓋（94 tests）

### 3.2 交易管線（Pipeline Bridge + Paper Engine + Risk Manager）

**評分：B+（良好）** — 從 B- 提升

- Pipeline Bridge 核心 intent 處理路徑已覆蓋（coverage tests）✅
- Paper Engine 7 狀態生命週期 ✅
- OMS 11 狀態轉換 ✅
- Risk Manager P0/P1/P2 阻塞 ✅ + qty/price 邊界 ✅（NEW）
- Spot category 處理（funding skip、margin 計算）✅（NEW）
- Inverse PnL 公式（幣本位 qty*(1/entry-1/exit)）✅（NEW）

### 3.3 AI 層（H0-H5 + L0/L1/L2）

**評分：B+（良好）** — 從 B 提升

- H0 Gate 5 check 全覆蓋（freshness/health/eligibility/risk/cooldown）✅（NEW）
- H1 ThoughtGate budget/complexity/cooldown ✅（NEW）
- H2 預算門控（cost_tracker）✅
- H3 ModelRouter（complexity routing）✅
- H4 AI 輸出驗證 ✅
- H5 CostLogger ✅
- L0/L1/L2 降級鏈 ✅
- Principle 14 Ollama Fallback（6 tests）✅

### 3.4 Phase 2/3 新增模塊

**評分：B（良好）** — 新模塊

- TruthSourceRegistry：CognitiveLevel 區分 + TTL + AI 信心上限 ✅（52 tests）
- BacktestEngine：純函數指標 + Sharpe 計算 ✅（57 tests）
- ExperimentLedger：假設狀態生命週期 + 65% 閾值 ✅（35 tests）
- ExperimentRoutes：4 端點 CRUD ✅（25 tests）
- EvolutionEngine：網格搜索 + is_simulated 強制 ✅（31 tests）
- EvolutionRoutes：API 端點 ✅（10 tests）
- AnalystAgent registry 集成 ✅（23 tests）
- SymbolCategoryRegistry ✅（19 tests）
- MarketScanner category-aware ✅（16 tests）

### 3.5 Agent 體系

**評分：B-（尚可）** — 從 C+ 提升

- StrategistAgent：shadow=False + H1 + ScoutChain ✅（36 tests）
- GuardianAgent：基本框架 ✅（21 tests）
- ExecutorAgent：Decision Lease 前置 ✅（14 tests）
- AnalystAgent：pattern claims + registry ✅（40 tests total）
- ScoutWorker：daemon 線程 ✅（10 tests）
- **缺口**：Conductor 編排邏輯未有專門測試

---

## 四、邊界條件測試評估

### 4.1 已修復的邊界缺口（vs March 31）

| 缺口 | 狀態 | 說明 |
|------|------|------|
| qty<=0 下單 | **已修復** | risk_manager.py fail-closed 守衛 + 5 邊界測試（Wave 6 Sprint 2）|
| price<=0 限價單 | **已修復** | risk_manager.py fail-closed 守衛 + 測試 |
| HMAC 簽名直接驗證 | **已修復** | test_demo_connector_coverage.py |
| WS 訂閱消息格式 | **已修復** | test_ws_listener_coverage.py |
| Pipeline Bridge 並發 tick+deactivate | **已修復** | test_pipeline_bridge_concurrency.py |

### 4.2 仍未修復的邊界缺口

| 缺口 | 模塊 | 優先級 |
|------|------|--------|
| stop_loss_pct=0 | risk_manager.py | P2 |
| hard_stop_pct=0 | stop_manager.py | P2 |
| float 精度 60000.0000001 | stop_manager.py | P3 |
| max_leverage=0 | risk_manager.py | P2 |
| on_tick 空 symbol | pipeline_bridge.py | P2 |
| Lease TTL 邊界 ±1ms | decision_lease_state_machine.py | P3 |
| grant_paper_authorization TTL=0 | governance_hub.py | P2 |
| ATR=-1（無效）| stop_manager.py | P3 |
| 余額不足追加同向倉 | paper_trading_engine.py | P2 |
| StateStore 畸形 JSON | paper_trading_engine.py | P2 |

### 4.3 新增邊界缺口（Phase 2/3 新模塊）

| 缺口 | 模塊 | 優先級 |
|------|------|--------|
| ExperimentLedger observe() 超過 max_observations | experiment_ledger.py | P3 |
| EvolutionEngine max_combinations=0 | evolution_engine.py | P3 |
| BacktestEngine bars=0（空 kline 列表）| backtest_engine.py | P2 |
| TruthSourceRegistry TTL 恰好過期 | truth_source_registry.py | P3 |
| SymbolCategoryRegistry refresh() 空回應 | symbol_category_registry.py | P3 |

---

## 五、異常處理測試評估

### 5.1 已改善的異常處理覆蓋

| 場景 | 狀態 |
|------|------|
| WS 斷線 reconnect | **已修復** — test_ws_listener_coverage.py 含 reconnect 測試 |
| Demo Connector REST timeout | **部分修復** — test_demo_connector_coverage.py 含錯誤處理 |
| Pipeline Bridge governance 拒絕 | **已修復** — test_pipeline_bridge_coverage.py |
| H0 Gate fail-closed 各路徑 | **已修復** — 94 個 h0_gate tests 含大量 fail-closed |

### 5.2 仍未覆蓋的異常路徑

| 缺口 | 模塊 | 優先級 |
|------|------|--------|
| PostgreSQL 連接失敗 | grafana_data_writer.py | P2 |
| Anthropic rate limit | layer2_engine.py | P2 |
| StateStore 文件損壞 | paper_trading_engine.py | P2 |
| Audit 目錄權限錯誤 | audit_persistence.py | P3 |
| WS 斷線期間止損行為 | pipeline_bridge + market_data | P1 |
| Bybit Demo REST HTTP 500 | bybit_demo_connector.py | P2 |
| EvolutionEngine backtest 全部失敗 | evolution_engine.py | P2 |
| ExperimentRoutes 並發 observe | experiment_routes.py | P3 |

---

## 六、並發安全測試評估

### 6.1 已改善

| 場景 | 狀態 |
|------|------|
| PipelineBridge._lock 競態 | **已修復** — test_pipeline_bridge_concurrency.py（17 cases） |
| MessageBus 並發 publish | **已修復** — test_message_bus_load.py（11 cases，含 ISSUE-1/2 文件化）|
| GovernanceHub 多線程 | 已有 — 3 ThreadSafety cases |
| LearningTierGate 並發促進 | 已有 — 2 cases |

### 6.2 仍未覆蓋

| 缺口 | 模塊 | 優先級 |
|------|------|--------|
| ScannerRateLimiter 高頻並發 | scanner_rate_limiter.py | P2 |
| TelegramAlerter 線程累積 | telegram_alerter.py | P3 |
| ChangeAuditLog 並發寫入 | change_audit_log.py | P2 |
| OMS StateMachine 並發轉換 | oms_state_machine.py | P2 |
| ReconciliationEngine 並發寫入 | reconciliation_engine.py | P3 |
| ExperimentLedger 並發 observe | experiment_ledger.py | P3（有 threading.Lock 但無並發測試）|
| TruthSourceRegistry 並發 register+query | truth_source_registry.py | P3（有鎖但無壓測）|

---

## 七、回歸測試評估

### 7.1 Pre-existing 失敗（17 個，與 March 31 完全一致）

| 測試文件 | 數量 | 根因 |
|---------|------|------|
| test_batch10_learning_oms.py | 2 | asyncio event loop deprecation |
| test_edge_filter_integration.py | 1 | timeout 測試不穩定 |
| test_integration_phase11.py | 2 | L1 tier enforcement reject |
| test_learning_tier_gate.py | 1 | l1_capabilities |
| test_ollama_integration.py | 11 | LocalLLMSearchProvider(3) + L1TriageLocalFallback(8) |

### 7.2 新增失敗（4 個 FAILED + 17 ERRORS = 21 個新問題）

| # | 測試 | 類型 | 優先級 | 分析 |
|---|------|------|--------|------|
| 1 | test_h0_gate::TestRiskManagerH0GateSync::test_h0gate_injected_record_fill_loss_calls_update_risk | FAILED | **P1** | H0 Gate 與 RiskManager 同步測試。可能是 Wave 7b Inverse 修改 RiskManager 後的回歸 |
| 2 | test_paper_trading_engine_inverse::TestInverseRiskConfig::test_inverse_effective_max_leverage | FAILED | **P1** | Inverse 品類 max_leverage 測試。Wave 7b 新增測試，可能與 risk_manager auto-inject 邏輯衝突 |
| 3 | test_session9_fixes::TestActiveCountFix::test_with_two_different_deployed | FAILED | **P2** | 舊測試與新代碼不兼容 |
| 4 | test_strategies::TestOrderIntent::test_create_basic | FAILED | **P2** | OrderIntent 結構變更導致舊測試斷言失敗 |
| 5-21 | test_session9_fixes::TestNetRealizedPnl + TestAiCostAggregation + TestRegimeAwareStops | ERROR(17) | **P2** | 收集錯誤（非運行失敗），可能是 import 路徑或模塊結構變更 |

**回歸風險評估：MEDIUM**
- 4 個新增 FAILED 中 2 個為 P1（影響 risk/h0gate 邏輯正確性）
- 17 個 ERRORS 為收集階段失敗，不影響運行時但表明測試基礎設施與代碼不同步

---

## 八、新模塊測試缺口（March 31 後新增模塊）

### 8.1 Phase 2/3 新增模塊（已有測試）

| 模塊 | LOC | 測試 cases | 覆蓋質量 | 缺口 |
|------|-----|-----------|---------|------|
| truth_source_registry.py | 821 | 52 | 良好 | 並發壓測缺失 |
| experiment_ledger.py | 617 | 35 | 良好 | 並發 observe 缺失 |
| experiment_routes.py | 327 | 25 | 良好 | 認證邊界案例少 |
| evolution_engine.py (local) | 539 | 31 | 良好 | backtest 全失敗場景缺失 |
| evolution_routes.py | 220 | 10 | **偏少** | 端點數 vs 測試數比低 |
| backtest_engine.py (local) | 1,209 | 57 | 良好 | bars=0 邊界缺失 |
| backtest_routes.py | 262 | 15 | 尚可 | 認證/授權邊界少 |
| symbol_category_registry.py | 153 | 19 | 良好 | refresh 失敗邊界 |
| h0_gate.py | 832 | 99 | **優秀** | SLA timeit 壓測已含 |
| scout_worker.py | 187 | 10 | 尚可 | daemon 線程清理未測試 |
| market_scanner.py (local) | 333 | 16 | 尚可 | category 組合覆蓋少 |

### 8.2 仍完全無測試的模塊

| 模塊 | LOC | 風險 | 說明 |
|------|-----|------|------|
| **strategy_auto_deployer.py** | **685** | **HIGH** | 策略自動部署核心邏輯。多幣種管理、弱倉清理、部署判斷 — 零測試 |
| grafana_data_writer.py | 359 | MEDIUM | PostgreSQL 寫入，告警失敗不影響交易 |
| telegram_alerter.py | 172 | LOW | 告警系統，失敗靜默 |
| bybit_demo_sync.py | 269 | **HIGH** | Demo 同步邏輯，僅 1 個間接測試 |

---

## 九、完整問題清單（P0/P1/P2/P3）

### P0（0 項）
無

### P1（6 項）

| # | 問題 | 模塊 | 說明 |
|---|------|------|------|
| P1-1 | 新增回歸：H0Gate-RiskManager 同步失敗 | test_h0_gate.py | test_h0gate_injected_record_fill_loss_calls_update_risk FAILED |
| P1-2 | 新增回歸：Inverse max_leverage 測試失敗 | test_paper_trading_engine_inverse.py | test_inverse_effective_max_leverage FAILED |
| P1-3 | WS 斷線期間止損行為未測試 | pipeline_bridge + market_data | 價格 feed 中斷時持倉止損是否安全 |
| P1-4 | strategy_auto_deployer 零測試 | strategy_auto_deployer.py (685 LOC) | 策略部署核心邏輯完全無覆蓋 |
| P1-5 | bybit_demo_sync 僅 1 間接測試 | bybit_demo_sync.py (269 LOC) | Demo 同步邏輯幾乎無覆蓋 |
| P1-6 | test_session9_fixes 17 個收集錯誤 | test_session9_fixes.py | import/結構問題導致 17 個測試無法運行 |

### P2（14 項）

| # | 問題 | 模塊 |
|---|------|------|
| P2-1 | phase2_strategy_routes 30% 覆蓋未改善 | phase2_strategy_routes.py (1,541 LOC) |
| P2-2 | paper_trading_routes 35% 覆蓋未改善 | paper_trading_routes.py (1,006 LOC) |
| P2-3 | market_data_dispatcher 35% 覆蓋未改善 | market_data_dispatcher.py (431 LOC) |
| P2-4 | scout_routes 路由端點未直接測試 | scout_routes.py (718 LOC) |
| P2-5 | assert True 空洞斷言仍存在 | test_risk_manager.py + test_scout_integration.py |
| P2-6 | StopManager 邊界不足（hard_stop=0, float 精度）| stop_manager.py |
| P2-7 | snapshot 系列測試過少（3+3+3） | runtime_snapshot_*.py |
| P2-8 | OMS SM-03 disabled 退回路徑未測試 | oms_state_machine.py |
| P2-9 | governance_hub TTL 分級未測試 | governance_hub.py |
| P2-10 | L2 Daily Budget Routes 層端到端未驗證 | layer2_routes.py |
| P2-11 | evolution_routes 測試偏少（10 cases / 220 LOC）| evolution_routes.py |
| P2-12 | PostgreSQL 連接失敗未測試 | grafana_data_writer.py |
| P2-13 | Anthropic rate limit 處理未測試 | layer2_engine.py |
| P2-14 | 新增回歸：test_strategies OrderIntent 結構 | test_strategies.py |

### P3（8 項）

| # | 問題 | 模塊 |
|---|------|------|
| P3-1 | "not worth" 回歸測試位置不當 | test_ollama_integration vs test_layer2 |
| P3-2 | Reconciliation 並發寫入未測試 | reconciliation_engine.py |
| P3-3 | Lease TTL 邊界 ±1ms 未測試 | decision_lease_state_machine.py |
| P3-4 | TelegramAlerter 線程累積未測試 | telegram_alerter.py |
| P3-5 | ExperimentLedger/TruthSourceRegistry 並發壓測 | Phase 2/3 modules |
| P3-6 | float 精度止損臨界 | stop_manager.py |
| P3-7 | ATR=-1 無效值 | stop_manager.py |
| P3-8 | Edge Filter fail-open 端到端 | test_edge_filter_integration.py |

---

## 十、改進建議

### 10.1 立即行動（P1，預估 8h）

1. **修復 4 個新增回歸失敗**（P1-1, P1-2, P1-6, P2-14）— 2h
   - 調查 test_h0_gate RiskManager 同步失敗根因
   - 調查 test_inverse max_leverage 斷言不匹配
   - 修復 test_session9_fixes import 錯誤（17 個 ERROR）
   - 修復 test_strategies OrderIntent 結構變更

2. **strategy_auto_deployer 測試補齊**（P1-4）— 3h
   - 685 LOC 零測試，這是自動交易管線的核心部署組件
   - 至少需要 25 個測試覆蓋：部署/暫停/停止/弱倉清理/多幣種/邊界

3. **bybit_demo_sync 測試補齊**（P1-5）— 1.5h
   - 269 LOC 僅 1 間接測試，Demo 同步是 Wave 7 重點

4. **WS 斷線止損行為測試**（P1-3）— 1.5h
   - 模擬價格 feed 中斷，驗證止損安全行為

### 10.2 下一批次（P2，預估 15h）

1. phase2_strategy_routes + paper_trading_routes 端點測試（6h）
2. market_data_dispatcher 直接測試文件（2h）
3. 消除 assert True 空洞斷言（1h）
4. StopManager 邊界 + OMS disabled 路徑（2h）
5. governance_hub TTL 分級 + L2 Routes 端到端（2h）
6. evolution_routes 測試擴充（2h）

### 10.3 質量提升（P3，預估 8h）

1. 並發壓測擴展：Phase 2/3 新模塊 + OMS + ChangeAuditLog
2. "not worth" 回歸測試遷移到 test_layer2
3. Edge Filter 端到端 fail-open
4. 浮點精度邊界測試

---

## 附錄 A：測試文件清單（96 個項目自有測試文件）

### control_api_v1/tests/（85 個）

| 測試文件 | Cases | 新增? |
|---------|-------|-------|
| test_analyst_agent_registry.py | 23 | Phase 2 |
| test_analyst_agent_unit.py | 17 | |
| test_api_contract.py | 18 | |
| test_audit_persistence.py | 35 | |
| test_authorization_state_machine.py | 73 | |
| test_auto_bridge.py | 26 | |
| test_backtest_routes.py | 15 | Phase 2 |
| test_batch10_learning_oms.py | 32 | |
| test_batch11_executor_exchange.py | 31 | |
| test_batch12_e2e_smoke.py | 35 | |
| test_batch7_conductor_strategist.py | 31 | |
| test_batch8_guardian_integration.py | 30 | |
| test_batch9_perception_analyst_integration.py | 25 | |
| test_change_audit_log.py | 44 | |
| test_data_source_enforcer.py | 58 | |
| test_decision_lease_state_machine.py | 58 | |
| test_demo_connector_coverage.py | 41 | Wave 2 |
| test_edge_filter_integration.py | 25 | |
| test_evolution_engine.py | 31 | Phase 3 |
| test_evolution_routes.py | 10 | Phase 3 |
| test_executor_agent_unit.py | 14 | |
| test_experiment_ledger.py | 35 | Phase 3 |
| test_experiment_routes.py | 25 | Phase 3 |
| test_governance_events.py | 45 | |
| test_governance_hub.py | 62 | |
| test_governance_routes_auth.py | 13 | Wave 2 |
| test_governance_routes_coverage.py | 110 | Wave 2 |
| test_guardian_agent_unit.py | 21 | |
| test_h0_gate_cooldown_integration.py | 5 | Wave 6 |
| test_h0_gate.py | 94 | P1-16 |
| test_h_chain_integration.py | 6 | Sprint 5b |
| test_incident_event_model.py | 51 | |
| test_integration_governance.py | 18 | |
| test_integration_phase10.py | 24 | |
| test_integration_phase11.py | 15 | |
| test_integration_phase2.py | 23 | |
| test_integration_phase5.py | 15 | |
| test_integration_phase7.py | 8 | |
| test_integration_phase8.py | 10 | |
| test_integration_phase9.py | 18 | |
| test_layer2.py | 79 | |
| test_learning_chapter.py | 44 | |
| test_learning_promotion_integration.py | 15 | |
| test_learning_tier_gate.py | 59 | |
| test_lease_ttl_config.py | 47 | |
| test_market_data.py | 35 | |
| test_market_regime.py | 49 | |
| test_message_bus_load.py | 11 | Cleanup |
| test_multi_agent_framework.py | 71 | |
| test_ollama_integration.py | 28 | |
| test_oms_state_machine.py | 53 | |
| test_paper_live_gate.py | 58 | |
| test_paper_metrics.py | 22 | |
| test_paper_trading_engine_inverse.py | 32 | Wave 7b |
| test_paper_trading_engine.py | 58 | |
| test_paper_trading.py | 46 | |
| test_perception_data_plane.py | 63 | |
| test_phase2_routes.py | 30 | |
| test_pipeline_bridge_concurrency.py | 17 | Wave 2 |
| test_pipeline_bridge_spot.py | 20 | Wave 7a |
| test_portfolio_risk_control.py | 36 | |
| test_product_family_business_settings.py | 23 | |
| test_protective_order_manager.py | 46 | |
| test_reconciliation_engine.py | 55 | |
| test_recovery_approval_gate.py | 56 | |
| test_risk_governor_state_machine.py | 56 | |
| test_risk_manager.py | 95 | |
| test_runtime_snapshot_bridge.py | 3 | |
| test_runtime_snapshot_directory_provider.py | 3 | |
| test_runtime_snapshot_generation.py | 3 | |
| test_scanner_rate_limiter.py | 51 | |
| test_scout_integration.py | 45 | |
| test_scout_worker.py | 10 | Sprint 5b |
| test_shadow_decision_builder.py | 26 | |
| test_shadow_decision.py | 26 | |
| test_snapshot_stable_entrypoint.py | 3 | |
| test_startup_integrity.py | 6 | Cleanup |
| test_strategist_agent.py | 36 | |
| test_symbol_category_registry.py | 19 | 方案 A |
| test_trade_attribution_integration.py | 10 | |
| test_trade_attribution.py | 45 | |
| test_truth_source_registry.py | 52 | Phase 2 |
| test_ttl_enforcer.py | 57 | |
| test_winrate_param_fixes.py | 23 | |
| test_ws_listener_coverage.py | 50 | Wave 2 |

### local_model_tools/tests/（11 個）

| 測試文件 | Cases | 新增? |
|---------|-------|-------|
| test_backtest_engine.py | 57 | Phase 2 |
| test_indicators.py | 58 | |
| test_kline_manager.py | 36 | |
| test_market_scanner.py | 16 | Wave 7a |
| test_pipeline_bridge_coverage.py | 80 | Wave 2 |
| test_pipeline_bridge.py | 8 | |
| test_session9_fixes.py | 33 | |
| test_signal_generator.py | 38 | |
| test_stop_manager.py | 17 | |
| test_strategies.py | 46 | |
| test_strategy_orchestrator.py | 18 | |

---

## 附錄 B：Pre-existing 17 失敗清單（與 March 31 一致，無變化）

1. test_batch10_learning_oms::TestL2CronTrigger::test_cron_does_not_fire_twice_same_week
2. test_batch10_learning_oms::TestL2CronTrigger::test_cron_fires_on_sunday_utc_0
3. test_edge_filter_integration::TestEdgeFilterIntegration::test_edge_filter_respects_timeout
4. test_integration_phase11::TestEngineTierEnforcement::test_submit_order_rejected_at_l1
5. test_integration_phase11::TestEngineTierEnforcement::test_cancel_order_rejected_at_l1
6. test_learning_tier_gate::test_l1_capabilities
7-9. test_ollama_integration::TestLocalLLMSearchProvider (3)
10-17. test_ollama_integration::TestL1TriageLocalFallback (8)

---

*報告生成：E4 Test Engineer（Claude Opus 4.6）*
*日期：2026-04-01*
*基準對比：2026-03-31 E4 測試報告*
