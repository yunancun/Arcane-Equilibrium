# E4 測試覆蓋評估報告
生成時間：2026-03-31
評估員：E4（Testing Evaluator — Claude Sonnet 4.6）
評估範圍：`program_code/exchange_connectors/bybit_connector/control_api_v1/app/` + `program_code/local_model_tools/`

---

## 執行摘要

| 指標 | 數值 |
|------|------|
| 發現測試文件（項目自有，不含 venv） | 71 個（63 + 8） |
| 預估總測試用例 | 2,480 個（2,229 + 251） |
| App 模塊數量（不含 __init__、main 入口） | 53 個 |
| 完全無直接測試文件的模塊 | 19 個 |
| 估算整體覆蓋率 | ~62%（按 LOC 加權） |
| 高風險未覆蓋模塊 LOC | ~9,268 行（佔總 app LOC ~23%） |
| 關鍵缺口 | 9 項（Governance Routes / Pipeline Bridge / MarketData / Strategist / WS / L0 SLA / 邊界 / 並發 / 回歸） |

**整體評估**：治理核心（GovernanceHub / SM / Decision Lease / RiskManager）測試質量一流（51–84 個用例，含並發和失敗路徑）。但 API 路由層（governance_routes、scout_routes、paper_trading_routes、phase2_strategy_routes）和基礎設施層（market_data_dispatcher、pipeline_bridge 完整功能、WS listener）的測試嚴重不足，形成顯著的業務風險敞口。

---

## 一、覆蓋率矩陣

### 1.1 控制 API 模塊（`control_api_v1/app/`）

| 模塊 | LOC | 直接測試文件 | 間接覆蓋 | 估算覆蓋率 | 風險等級 |
|------|-----|------------|---------|-----------|---------|
| governance_hub.py | ~1,750 | test_governance_hub.py（51 cases） | integration_governance, batch12 | ~80% | LOW |
| authorization_state_machine.py | ~900 | test_authorization_state_machine.py（73 cases） | integration_governance | ~85% | LOW |
| decision_lease_state_machine.py | ~750 | test_decision_lease_state_machine.py（58 cases） | integration_governance | ~82% | LOW |
| risk_governor_state_machine.py | ~700 | test_risk_governor_state_machine.py（56 cases） | integration_governance | ~80% | LOW |
| risk_manager.py | ~1,100 | test_risk_manager.py（84 cases） | batch12 | ~75% | LOW |
| paper_trading_engine.py | ~1,200 | test_paper_trading_engine.py（53 cases）+ test_paper_trading.py（46 cases） | batch12 | ~78% | LOW |
| oms_state_machine.py | ~600 | test_oms_state_machine.py（53 cases） | batch10 | ~80% | LOW |
| paper_live_gate.py | ~800 | test_paper_live_gate.py（58 cases） | integration_governance | ~75% | LOW |
| layer2_types.py | ~400 | test_layer2.py（部分覆蓋） | - | ~90% | LOW |
| layer2_cost_tracker.py | ~300 | test_layer2.py（完整覆蓋） | - | ~85% | LOW |
| layer2_tools.py | ~450 | test_layer2.py（含 degradation） | - | ~78% | LOW |
| layer2_engine.py | ~720 | test_layer2.py + test_ollama_integration.py | - | ~65% | MEDIUM |
| layer2_routes.py | ~350 | test_layer2.py（9 routes via TestClient） | - | ~70% | MEDIUM |
| learning_tier_gate.py | ~600 | test_learning_tier_gate.py（59 cases） | - | ~80% | LOW |
| multi_agent_framework.py | ~800 | test_multi_agent_framework.py（71 cases） | batch7 | ~75% | LOW |
| perception_data_plane.py | ~600 | test_perception_data_plane.py（63 cases） | - | ~78% | LOW |
| reconciliation_engine.py | ~500 | test_reconciliation_engine.py（44 cases） | - | ~75% | LOW |
| recovery_approval_gate.py | ~500 | test_recovery_approval_gate.py（56 cases） | - | ~78% | LOW |
| change_audit_log.py | ~600 | test_change_audit_log.py（44 cases） | - | ~75% | LOW |
| audit_persistence.py | ~400 | test_audit_persistence.py（35 cases） | - | ~72% | LOW |
| portfolio_risk_control.py | ~450 | test_portfolio_risk_control.py（36 cases） | - | ~70% | MEDIUM |
| scanner_rate_limiter.py | ~400 | test_scanner_rate_limiter.py（51 cases） | - | ~80% | LOW |
| trade_attribution.py | ~500 | test_trade_attribution.py（45 cases） | - | ~75% | LOW |
| ttl_enforcer.py | ~400 | test_ttl_enforcer.py（57 cases） | - | ~82% | LOW |
| market_regime.py | ~500 | test_market_regime.py（49 cases） | - | ~75% | LOW |
| shadow_decision_builder.py | ~400 | test_shadow_decision_builder.py（26 cases） | - | ~72% | LOW |
| incident_event_model.py | ~400 | test_incident_event_model.py（51 cases） | - | ~80% | LOW |
| data_source_enforcer.py | ~500 | test_data_source_enforcer.py（58 cases） | - | ~78% | LOW |
| ollama_client.py | ~400 | test_ollama_integration.py（28 cases）| - | ~68% | MEDIUM |
| market_data_dispatcher.py | 431 | test_market_data.py（部分，35 cases） | - | ~35% | **HIGH** |
| pipeline_bridge.py | 1,550 | test_pipeline_bridge.py（5 cases，僅基礎） | edge_filter tests | ~15% | **CRITICAL** |
| governance_routes.py | 1,698 | test_integration_phase9.py（5 cases）+ phase10（4 cases） | - | ~10% | **CRITICAL** |
| scout_routes.py | 718 | test_scout_integration.py（scout 邏輯，非路由） | - | ~40% | **HIGH** |
| phase2_strategy_routes.py | 1,308 | test_phase2_routes.py（27 cases） | - | ~30% | **HIGH** |
| paper_trading_routes.py | 957 | test_paper_trading.py + test_risk_manager.py（路由部分） | - | ~35% | **HIGH** |
| risk_routes.py | 246 | test_risk_manager.py（8 route cases） | - | ~60% | MEDIUM |
| bybit_demo_connector.py | 336 | test_integration_phase7.py（2 cases） | - | ~8% | **HIGH** |
| bybit_demo_sync.py | 269 | test_integration_phase7.py（1 case） | - | ~5% | **HIGH** |
| bybit_public_ws_listener.py | 460 | test_market_data.py（parse tests） | - | ~20% | **HIGH** |
| strategist_agent.py | 585 | test_batch7_conductor_strategist.py（18 cases） | - | ~40% | **HIGH** |
| grafana_data_writer.py | 359 | 無 | - | ~0% | MEDIUM |
| telegram_alerter.py | 172 | test_integration_phase8.py（間接） | - | ~10% | LOW |
| runtime_bridge.py | 179 | test_runtime_snapshot_bridge.py（3 cases） | - | ~50% | MEDIUM |
| lease_ttl_config.py | ~300 | test_lease_ttl_config.py（47 cases） | - | ~85% | LOW |

### 1.2 local_model_tools 模塊

| 模塊 | LOC | 測試文件 | 估算覆蓋率 | 風險等級 |
|------|-----|---------|-----------|---------|
| indicator_engine.py | ~700 | test_indicators.py（58 cases） | ~78% | LOW |
| strategy_orchestrator.py | ~600 | test_strategy_orchestrator.py（18 cases） | ~55% | MEDIUM |
| signal_generator.py | ~500 | test_signal_generator.py（38 cases） | ~72% | LOW |
| kline_manager.py | ~600 | test_kline_manager.py（36 cases） | ~70% | LOW |
| stop_manager.py | ~300 | test_stop_manager.py（17 cases） | ~60% | MEDIUM |
| strategies/*.py | ~800 | test_strategies.py（46 cases） | ~65% | MEDIUM |
| pipeline_bridge（local view） | 1,550 | test_pipeline_bridge.py（5 cases） | ~15% | **CRITICAL** |

---

## 二、完全未測試或嚴重不足的高風險模塊（11 項）

### 2.1 [CRITICAL] pipeline_bridge.py（1,550 行，15% 覆蓋）

**為什麼高風險**：這是策略管線連接紙上交易的核心橋樑。含 Tick Fan-Out、Intent→Order 提交、Stop 管理調用、Scout 掃描觸發、L2 Cron 觸發、Edge Filter 調用、Learning Promotion、Round-trip 完整回調。任何失敗都導致無法成交或止損不觸發。

現有測試（`test_pipeline_bridge.py`）僅測試 5 個基礎用例：activate/deactivate、inactive tick does nothing、active tick feeds KlineManager、stats 結構。核心業務邏輯 `_process_pending_intents()`、`_check_stops()`、`_invoke_scout_scan()`、`_try_l2_cron_trigger()`、`_on_position_open()`、`_on_round_trip_complete()` 完全沒有直接測試。

**建議測試用例**：
```python
def test_intent_submitted_via_governance_gate():
    """GovernanceHub.is_authorized()=False 時，intent 被拒絕"""

def test_stop_check_triggers_close_order():
    """StopManager 觸發止損時，PaperTradingEngine.submit_order() 被調用"""

def test_edge_filter_exception_fail_open_does_not_block():
    """Edge filter 拋出異常時，intent 仍通過（fail-open 行為）"""

def test_round_trip_complete_emits_observation():
    """持倉平倉後，observation 被寫入 perception_plane"""

def test_tick_routes_to_kline_and_orchestrator():
    """tick 事件同時路由到 KlineManager 和 StrategyOrchestrator"""
```

---

### 2.2 [CRITICAL] governance_routes.py（1,698 行，~10% 覆蓋）

**為什麼高風險**：這是操作員控制治理系統的唯一 API 入口，含 24 個端點。包括授權申請/審批、風控等級強制覆蓋、de-escalation 申請、Recovery 審批、Symbol 白名單管理、Active Lease 查詢、Learning Tier 升級。現有測試只覆蓋 `get_governance_events`（5 個用例）和部分狀態查詢。

關鍵未覆蓋端點：`request_authorization`、`approve_authorization`、`override_risk_level`、`request_de_escalation`（HTTP 層）、`approve_de_escalation_request`（HTTP 層）、`approve_recovery_request`、`approve_audit_change`、`reject_audit_change`、`add_symbol_to_whitelist`、`remove_symbol_from_whitelist`、`get_active_leases`、`promote_learning_tier`。

**建議測試用例**：
```python
def test_request_authorization_returns_201():
    """POST /governance/auth/request → 201 + 包含 request_id"""

def test_approve_authorization_transitions_to_active():
    """POST /governance/auth/approve → 授權進入 ACTIVE 狀態"""

def test_override_risk_level_requires_operator_role():
    """POST /governance/risk/override → 無 operator token 時返回 403"""

def test_add_symbol_to_whitelist_persists():
    """POST /governance/whitelist/add → 符號出現在 GET /governance/whitelist 中"""

def test_promote_learning_tier_validates_criteria():
    """POST /governance/learning/promote → 未滿足條件時返回 400"""
```

---

### 2.3 [HIGH] bybit_public_ws_listener.py（460 行，~20% 覆蓋）

**為什麼高風險**：WebSocket 重連邏輯、消息解析、價格快取更新是市場數據的唯一來源。斷線不重連或解析錯誤會導致整個系統無市場數據，所有止損失效。

現有測試只覆蓋 `test_market_data.py` 中的 ticker 解析（`_handle_message`）和價格快取（`get_latest_price`）。`_run_loop()` 中的 `on_open/on_close/on_error` callbacks、訂閱重試、斷線計時器完全未測試。

**建議測試用例**：
```python
def test_ws_reconnect_after_disconnect():
    """模擬 on_close → 驗證重連嘗試發生"""

def test_on_error_callback_logs_and_does_not_raise():
    """WS error callback 不拋出異常"""

def test_handle_message_malformed_json_ignored():
    """畸形 JSON 消息不崩潰，price cache 不更新"""

def test_subscription_sent_on_open():
    """on_open 被調用後，訂閱消息被發送"""
```

---

### 2.4 [HIGH] bybit_demo_connector.py（336 行，~8% 覆蓋）

**為什麼高風險**：Bybit Demo API 的唯一訪問層，含 HMAC 簽名、REST 請求重試、條件單管理。`submit_order()`、`cancel_order()`、`place_conditional_order()`、`_sign()` 幾乎未測試。條件單（交易所端止損）是 Principle #9 的組成部分。

**建議測試用例**：
```python
def test_sign_produces_correct_hmac():
    """_sign(timestamp, params) 返回正確 HMAC-SHA256"""

def test_submit_order_disabled_when_no_api_key():
    """api_key='' 時 is_enabled=False，submit_order 不發出請求"""

def test_place_conditional_order_structure():
    """place_conditional_order 包含 triggerPrice、orderType 正確字段"""

def test_request_handles_timeout_gracefully():
    """_request() 遇到 URLError/timeout 返回 {'retCode': -1} 不拋出"""
```

---

### 2.5 [HIGH] market_data_dispatcher.py（431 行，~35% 覆蓋）

**為什麼高風險**：Tick 分發器，將 WS 價格事件分發給所有消費者（PipelineBridge、Paper Engine tick）。`_assess_attention()`、`_detect_volatility_spike()`、`register_tick_consumer()` 部分覆蓋，但 `_on_price_event()` 的完整分發路徑（含 PipelineBridge 回調）未測試。

**建議測試用例**：
```python
def test_register_tick_consumer_receives_events():
    """register_tick_consumer 注冊的回調在 _on_price_event 後被調用"""

def test_volatility_spike_suppresses_dispatch():
    """spike 檢測觸發後，後續 tick 不立即轉發（spike suppression window）"""

def test_attention_level_critical_when_order_very_close():
    """訂單距當前價 <0.1% 時，attention=CRITICAL"""
```

---

### 2.6 [HIGH] strategist_agent.py（585 行，~40% 覆蓋）

**為什麼高風險**：Scout Intel 的主要消費者，決定是否生成 TradeIntent。`_handle_intel()`（285 行核心處理邏輯）的多數分支在 batch7 中測試，但 `_ai_evaluate()` 的實際 Ollama 調用路徑和超時/失敗回退未充分測試。

**建議測試用例**：
```python
def test_ai_evaluate_ollama_timeout_falls_back_to_heuristic():
    """Ollama 超時時，_ai_evaluate 降級到 _heuristic_evaluate"""

def test_collect_pending_intents_clears_queue():
    """collect_pending_intents() 調用後，隊列清空"""

def test_shadow_mode_generates_intent_but_not_submitted():
    """shadow_mode=True 時，intent 不加入 pending，僅記錄"""
```

---

### 2.7 [HIGH] phase2_strategy_routes.py（1,308 行，~30% 覆蓋）

**為什麼高風險**：策略部署、激活、暫停、停止的 HTTP 入口。`test_phase2_routes.py` 只覆蓋 27 個用例，其中大量是輕量型結構驗證。策略狀態轉換的錯誤路徑（激活不存在策略、非法狀態轉換）需要更多覆蓋。

**建議測試用例**：
```python
def test_activate_already_active_returns_409():
    """激活已激活的策略返回 409 或適當錯誤"""

def test_strategy_config_validation_rejects_negative_qty():
    """部署策略時，qty_usdt 為負數返回 422"""

def test_multi_strategy_deployment_isolated_state():
    """同時部署兩個策略，各自狀態互不干擾"""
```

---

### 2.8 [MEDIUM] grafana_data_writer.py（359 行，~0% 覆蓋）

**為什麼高風險**：直接寫入 PostgreSQL（`_write_snapshot`、`_write_pnl`、`_write_market_tickers`、`_write_trade_executions`）。PostgreSQL 連接失敗無測試，寫入超時無測試。雖然告警失敗不影響交易，但 Grafana 數據損壞會影響 Operator 決策。

**建議測試用例**：
```python
def test_start_loop_not_crash_without_pg():
    """無 PostgreSQL 連接時，start() 優雅降級而不崩潰"""

def test_write_snapshot_handles_connection_error():
    """_write_snapshot 遇到 psycopg2.OperationalError 繼續下一個週期"""
```

---

### 2.9 [MEDIUM] telegram_alerter.py（172 行，~10% 覆蓋）

**為什麼中等風險**：告警系統失效時 Operator 無法收到重要通知。`send()` 的速率限制邏輯和 `send_async()` 的後台線程從未被直接測試。

**建議測試用例**：
```python
def test_rate_limit_blocks_excess_messages():
    """超過 rate_limit_per_min 後，send() 返回 False"""

def test_send_disabled_when_no_token():
    """bot_token='' 時 is_enabled=False，send() 立即返回 False"""

def test_send_network_failure_returns_false_not_raise():
    """urllib.request.urlopen 拋出 URLError 時，send() 返回 False"""
```

---

## 三、現有測試質量問題（14 項）

### 3.1 空洞斷言（assert True）

**文件：** `test_risk_manager.py:666`
```python
assert True  # Just verify no crash; spike behavior is probabilistic
```
**問題**：spike 抑制 soft stop 行為有確定性邊界，應改為在已知觸發條件下斷言 soft stop 不觸發。

**文件：** `test_scout_integration.py:456, 496, 575, 583, 589`
```python
assert True  # Validation passed
assert True  # Verified at API layer
```
**問題**：這些 assert True 掩蓋了應有的行為驗證，用例意義喪失。

---

### 3.2 Pipeline Bridge 測試嚴重不足（test_pipeline_bridge.py）

**文件：** `/home/ncyu/BybitOpenClaw/srv/program_code/local_model_tools/tests/test_pipeline_bridge.py`

5 個用例僅測試基礎 activate/deactivate 和 tick 計數，完全不觸及 PipelineBridge 的核心業務邏輯（intent 處理、止損觸發、governance gate）。

---

### 3.3 StopManager 缺少關鍵邊界測試

**文件：** `/home/ncyu/BybitOpenClaw/srv/program_code/local_model_tools/tests/test_stop_manager.py`

只有 17 個用例。缺少：
- 追蹤同一符號的多個策略（key 衝突）
- `hard_stop_pct=0.0` 的邊界（理論上立即觸發）
- 同時觸發 hard stop 和 time stop 時的優先級
- 浮點精度（如 BTC 進入時 60000.000000001）

---

### 3.4 snapshot 系列測試過於稀少

**文件：** `test_runtime_snapshot_bridge.py`（3 cases）、`test_runtime_snapshot_generation.py`（3 cases）、`test_runtime_snapshot_directory_provider.py`（3 cases）

這些測試僅驗證基本的文件讀寫和 overlay，未測試 snapshot 文件格式錯誤、缺失字段、版本不兼容。

---

### 3.5 Layer2 Engine 的 "not worth" 子串回歸測試位置不當

**文件：** `test_ollama_integration.py:623`（`test_triage_local_freetext_negative`）

P0 Bug 修復（`layer2_engine.py:293-297`）在 `layer2_engine.py` 中，但回歸測試在 `test_ollama_integration.py` 中，且只測試了 Ollama 客戶端層，沒有直接測試 `layer2_engine._l1_triage_local()` 對 "not worth investigating" 文本的解析。`test_layer2.py` 中無相應回歸測試。

---

### 3.6 governance_hub 的 grant_paper_authorization() 未測試 TTL 分級

**文件：** `test_governance_hub.py`

`grant_paper_authorization(ttl_hours=24)` 的邏輯在 CLAUDE.md §11 中描述為 L1=24h、L3=72h、L4=7d、L5=30d 分級，但當前測試未覆蓋 TTL 過期後 is_authorized 的降級。

---

### 3.7 Edge Filter 未測試 fail-open 對授權後 Order 的影響

**文件：** `test_edge_filter_integration.py`

雖然 fail-open 場景有測試，但未測試：當 Governance Hub is_authorized()=True 但 edge filter 拋出異常時，最終 intent 是否被提交（即整個 pipeline 端到端 fail-open）。

---

### 3.8 OMS State Machine 缺少 fail-closed 路徑

**文件：** `test_oms_state_machine.py`

11 個狀態、53 個用例。但缺少：當 OMS SM-03 disabled（`OMS_SM03_ENABLED=False`）時，paper engine 退回到 7 狀態舊版流程的行為測試。

---

### 3.9 並發測試範圍局限於 GovernanceHub

並發測試集中在 `test_governance_hub.py`（TestThreadSafety，3 個並發用例）和 `test_learning_tier_gate.py`（2 個並發用例）。`PipelineBridge._lock`、`ScannerRateLimiter._lock`、`TelegramAlerter._lock` 這些共享狀態在並發壓力下未驗證。

---

### 3.10 Paper Trading 邊界條件不足

**文件：** `test_paper_trading_engine.py`

`submit_order("BTCUSDT", "Buy", "market", qty=0)` 未測試。
`submit_order("BTCUSDT", "Buy", "limit", qty=-0.001)` 未測試。
初始餘額 `0.0001`（test line 192）存在，但 qty 接近 0 的極限訂單被拒絕路徑未完整覆蓋。

---

### 3.11 Reconciliation Engine 不測試高並發寫入

**文件：** `test_reconciliation_engine.py`（44 cases）

無並發測試，但 ReconciliationEngine 在實際系統中由 GovernanceHub 在多線程環境調用。

---

### 3.12 Layer2 Engine 的 Daily Budget 硬上限在 Routes 層未驗證

**文件：** `test_layer2.py`

`TestCostTracker.test_daily_hard_cap_enforcement` 測試了 tracker 層，但未通過 Routes 層（TestClient）驗證：當 daily budget 超限時，`/layer2/analyze` 端點返回正確的拒絕響應。

---

### 3.13 Bybit Demo Connector 的 HMAC 簽名從未直接測試

HMAC 簽名錯誤會導致所有 Bybit Demo 訂單被拒絕（retCode=10003）。`_sign()` 函數在任何測試中均未被直接調用驗證。

---

### 3.14 BybitPublicWSListener 訂閱消息格式未驗證

`_run_loop()` 中 `on_open` 發送的訂閱消息格式（topic、req_id）未驗證，若格式錯誤 Bybit 不回傳數據但不報錯，靜默失敗。

---

## 四、邊界條件缺口（12 項）

### 4.1 數值邊界

| 缺口 | 模塊 | 說明 |
|------|------|------|
| qty=0 下單 | paper_trading_engine.py | 應返回 rejected，現無測試 |
| qty<0 下單 | paper_trading_engine.py | 應返回 rejected |
| price=0 限價單 | paper_trading_engine.py | 應返回 rejected |
| stop_loss_pct=0 | risk_manager.py | 邊界值應等效為"立即觸發" |
| hard_stop_pct=0 | stop_manager.py | 任何 tick 均觸發 |
| float 精度 | stop_manager.py | 60000.0000001 vs 60000.0 止損臨界 |
| max_leverage=0 | risk_manager.py | CategoryRiskConfig 0 值語義 |

### 4.2 空輸入邊界

| 缺口 | 模塊 | 說明 |
|------|------|------|
| on_tick 收到空 symbol | pipeline_bridge.py | event={"symbol": "", "last_price": 0} |
| market_prices={} 空字典 | pipeline_bridge._check_stops() | 無價格時不應觸發止損 |
| IntelObject 空 symbols 列表 | strategist_agent._handle_intel() | 應優雅跳過 |

### 4.3 時間邊界

| 缺口 | 模塊 | 說明 |
|------|------|------|
| Lease TTL 恰好過期（邊界 ±1ms） | decision_lease_state_machine.py | 已有 TTL 測試但未測試邊界 1ms |
| grant_paper_authorization TTL=0 | governance_hub.py | 立即過期的授權行為 |
| L2 Cron trigger 時間窗口邊界 | pipeline_bridge._try_l2_cron_trigger() | 恰好在 cron_interval 內/外 |

### 4.4 仓位大小邊界

| 缺口 | 模塊 | 說明 |
|------|------|------|
| ATR=0 的仓位計算 | stop_manager.compute_atr_position_size() | 已有測試，但 ATR=-1（無效）未測試 |
| 余額不足追加仓（同向成交）| paper_trading_engine.py | 第二筆同向單超出余額 |

---

## 五、異常處理測試缺口（10 項）

### 5.1 API 超時 / 網絡錯誤

| 缺口 | 模塊 | 場景 |
|------|------|------|
| Bybit Demo REST 超時 | bybit_demo_connector._request() | urllib 超時後 retCode=-1 且不拋出 |
| Bybit Demo REST HTTP 500 | bybit_demo_connector._request() | 服務器錯誤 response 解析 |
| Ollama HTTP 500 | ollama_client.generate() | 已有 test_generate_connection_error，但 HTTP 500 body 解析缺失 |
| L2 Engine Anthropic rate limit | layer2_engine._run_session_inner() | RateLimitError 觸發 session 失敗而非崩潰 |

### 5.2 治理 Gate 拒絕場景

| 缺口 | 測試狀態 |
|------|---------|
| GovernanceHub 初始化失敗（磁盤滿） | `test_is_authorized_when_initialization_fails` ✅ 已有 |
| GovernanceHub.acquire_lease 同時 500 請求競爭 | 已有並發測試 3 線程，不足以暴露真實競態 |
| is_authorized cache 在 TTL 邊界的一致性 | `test_is_authorized_cache_expiry_race` ✅ 已有 |
| Pipeline Bridge governance 拒絕後 intent 計數準確 | `test_pipeline_bridge_governance_rejection` ✅ 已有 |

### 5.3 數據庫連接失敗

| 缺口 | 模塊 | 狀態 |
|------|------|------|
| PostgreSQL 連接失敗 | grafana_data_writer.py | **完全無測試** |
| Audit 文件目錄不可寫 | audit_persistence.py | test_audit_dir_created 有，但權限錯誤未測試 |
| StateStore 文件損壞（畸形 JSON） | paper_trading_engine.PaperStateStore | `read()` 的 JSONDecodeError 路徑未測試 |

### 5.4 Market Data Feed 異常

| 缺口 | 模塊 | 說明 |
|------|------|------|
| WS 斷線後 PipelineBridge 繼續處理舊 intent | market_data_dispatcher + pipeline_bridge | 無測試 |
| WS 重連期間 stop 管理的行為 | pipeline_bridge._check_stops() | 無價格 dict 時不觸發（有測試），但重連期間持倉仍存在 |

---

## 六、並發風險點（6 項）

### 6.1 PipelineBridge._lock 競態（**高風險**）

**文件：** `pipeline_bridge.py`，`self._lock = threading.Lock()`

`on_tick()` 持有 `_lock` 時調用 `_process_pending_intents()`，後者又調用 `_check_stops()`。若 StopManager 回調導致 GovernanceHub 操作（GovernanceHub 自身有鎖），存在鎖嵌套死鎖風險。**當前無任何並發測試。**

建議測試：
```python
def test_concurrent_tick_and_deactivate():
    """多線程同時 on_tick 和 deactivate 不死鎖"""
```

### 6.2 ScannerRateLimiter 高頻並發

**文件：** `scanner_rate_limiter.py`，`test_scanner_rate_limiter.py`（51 cases，但未見多線程測試）

650 個符號掃描時，多線程同時訪問 rate limiter 的 token bucket 是否線程安全。

### 6.3 TelegramAlerter 後台線程累積

**文件：** `telegram_alerter.py`，`send_async()` 每次創建 `daemon=True` 線程

高頻告警（如 650 個符號同時觸發止損）會創建大量後台線程。無測試驗證線程累積和速率限制的交互。

### 6.4 ChangeAuditLog 並發寫入

**文件：** `change_audit_log.py`，`test_change_audit_log.py`

44 個用例，但均為順序操作，無並發寫入測試。GovernanceHub 在多次狀態轉換後批量寫入 ChangeAuditLog。

### 6.5 LearnignTierGate 促進競態

**文件：** `test_learning_tier_gate.py`

有 `test_thread_safe_concurrent_promotion`（2 個測試），但未驗證兩個線程同時滿足促進條件時是否只促進一次。

### 6.6 OMS StateMachine 並發轉換

**文件：** `oms_state_machine.py`，`test_oms_state_machine.py`

53 個用例，無並發測試。OMS SM-03 在 ExecutorAgent 和 PaperTradingEngine 雙路徑下更新狀態，可能存在競態。

---

## 七、關鍵業務邏輯測試評估

### 7.1 GovernanceHub（SM-01/SM-02/SM-04/EX-04）

**評分：A-（優秀）**

- fail-closed 行為：`test_is_authorized_when_initialization_fails`、`test_is_authorized_when_frozen` ✅
- Decision Lease fail-closed：`test_lease_acquire_denied_when_not_authorized`、`test_acquire_lease_returns_none_on_error` ✅
- 並發：3 個 ThreadSafety 用例（5 線程）✅
- SM 錯誤韌性：`test_hub_resilient_to_auth_sm_error` ✅
- **缺口**：`grant_paper_authorization` TTL 分級未測試；`_check_de_escalation_gate` 內部邏輯僅通過集成測試覆蓋

### 7.2 Decision Lease 獲取/釋放/過期

**評分：A-（優秀）**

- 9 個狀態完整測試 ✅
- 轉換計數驗證 ✅
- 非法轉換被拒絕 ✅
- TTL 設計：`test_lease_ttl_config.py`（47 cases）✅
- **缺口**：TTL 邊界（±1ms）的時間精度測試

### 7.3 風控框架 P0/P1/P2

**評分：B+（良好）**

- P0 阻塞（session halted、daily loss）✅
- P1 阻塞（leverage、category、position size）✅
- P2 Cooldown 邏輯 ✅
- AI 注意力稅 ✅
- Portfolio Risk（相關性、集中度）✅
- **缺口**：qty=0、price=0 的邊界；CategoryRiskConfig max_leverage=None 時的行為

### 7.4 Paper Trading 7 狀態生命週期

**評分：B+（良好）**

- 7 狀態轉換完整 ✅
- OMS SM-03 11 狀態轉換 ✅
- session start/pause/stop ✅
- 限價單成交邏輯 ✅
- **缺口**：qty=0 下單；StateStore 文件損壞恢復；OMS_SM03_ENABLED=False 退回舊版路徑

### 7.5 StopManager 觸發邏輯

**評分：C+（一般）**

- Hard Stop Long/Short ✅
- Trailing Stop ✅
- Time Stop ✅
- ATR 倉位計算 ✅
- **缺口**：同一符號多策略（key 衝突）；浮點精度；hard_stop_pct=0；Pipeline Bridge 中的 StopManager 調用路徑未直接測試

### 7.6 AI 推理層（L0/L1/L2）降級邏輯

**評分：B（良好）**

- L0 確定性（H0 is_authorized）✅
- L1 Haiku 降級到本地 Ollama ✅
- L1 triage "not worth" 否定解析（ollama integration test）✅
- L2 agent loop（mocked）✅
- Search provider degradation ✅
- Daily budget hard cap（tracker 層）✅
- **缺口**：layer2_engine.py 中 "not worth" 的直接回歸測試缺失；Daily budget 通過 Routes 層的端到端驗證；Anthropic rate limit 處理

### 7.7 市場數據 Feed 異常處理

**評分：C（一般）**

- WS ticker 解析 ✅
- 無效 price 忽略 ✅
- WS 斷線 → DegradationAction.REDUCED（perception plane）✅
- **缺口**：WS 重連回調（on_close、on_error）的行為；WS 斷線期間止損的行為；MarketDataDispatcher 消費者回調異常（一個消費者崩潰不影響其他消費者）

---

## 八、推薦新增測試用例（Top 30，按業務影響排序）

### P1 — 立即執行（與 Live 安全直接相關）

**T01：Pipeline Bridge — Governance Gate Rejection**
```python
# 文件：test_pipeline_bridge.py（擴展）
def test_intent_rejected_when_governance_not_authorized():
    """輸入：bridge 已激活，MockGovernanceHub.is_authorized=False
    期望：intent 不被提交，stats['intents_rejected'] += 1"""
    bridge.set_governance_hub(MockHub(authorized=False))
    bridge.activate()
    intent = make_mock_intent("BTCUSDT", "Buy")
    # inject intent into orchestrator queue
    assert mock_engine.submitted_orders == []
    assert bridge.get_stats()["intents_rejected"] >= 1
```

**T02：Pipeline Bridge — Stop Check Triggers Close**
```python
def test_stop_triggers_paper_close_order():
    """輸入：持倉，price 跌破 hard stop
    期望：submit_order("Sell", ...) 被調用"""
    bridge.activate()
    bridge._stop_mgr = StopManager(StopConfig(hard_stop_pct=5.0))
    bridge._stop_mgr.track_position("BTCUSDT", "long", 60000, 0.001, "MA")
    # Tick with price below hard stop
    bridge.on_tick({"symbol": "BTCUSDT", "last_price": 56000.0, "ts_ms": ts})
    assert len(mock_engine.submitted_orders) == 1
    assert mock_engine.submitted_orders[0]["side"] == "Sell"
```

**T03：GovernanceHub — grant_paper_authorization TTL 過期**
```python
def test_grant_authorization_expires_after_ttl():
    """輸入：TTL=1 秒
    期望：1 秒後 is_authorized() 返回 False"""
    hub.grant_paper_authorization(ttl_hours=0.000278)  # 1 second
    assert hub.is_authorized() is True
    time.sleep(1.1)
    assert hub.is_authorized() is False
```

**T04：Layer2 Engine — "not worth" 直接回歸**
```python
# 文件：test_layer2.py（擴展 TestLayer2Engine）
@patch("app.layer2_engine._get_anthropic_client")
async def test_l1_triage_not_worth_returns_false(mock_client):
    """回歸測試：'not worth investigating' 文本中含 'worth' 子串
    期望：worth_investigating 返回 False（非 True）"""
    mock_response.content = [MagicMock(text="This is not worth investigating.")]
    result = await engine.l1_triage(context={"symbol": "BTCUSDT"})
    assert result["worth_investigating"] is False  # 修復前此處返回 True
```

**T05：BybitDemoConnector — 簽名驗證**
```python
def test_hmac_sign_correctness():
    """驗證 _sign(timestamp, recv_window) 與已知正確值匹配"""
    conn = BybitDemoConnector(api_key="test_key", api_secret="test_secret")
    sig = conn._sign("1000000000000", "5000")
    # 計算期望值：HMAC-SHA256("1000000000000" + "5000" + "test_key", "test_secret")
    expected = hmac.new(b"test_secret", b"1000000000000" + b"test_key" + b"5000", hashlib.sha256).hexdigest()
    assert sig == expected
```

**T06：BybitDemoConnector — REST 超時不崩潰**
```python
def test_request_timeout_returns_error_dict():
    """urlopen 超時時返回 {'retCode': -1, 'retMsg': 'timeout'} 不拋出"""
    with patch("urllib.request.urlopen", side_effect=TimeoutError):
        result = conn._request("GET", "/v5/order/create", {})
    assert result["retCode"] != 0
```

**T07：Paper Trading — qty=0 訂單被拒絕**
```python
def test_submit_zero_qty_rejected(active_engine):
    """qty=0 的訂單應被拒絕"""
    result = active_engine.submit_order("BTCUSDT", "Buy", "market", 0)
    assert result["order"]["state"] == "rejected"
    assert "qty" in result["rejected_reason"]
```

**T08：Paper Trading — StateStore 文件損壞恢復**
```python
def test_state_store_corrupt_file_resets_to_default(tmp_path):
    """state.json 含畸形 JSON 時，PaperStateStore 返回默認狀態"""
    state_file = tmp_path / "paper_state.json"
    state_file.write_text("{ invalid json }")
    store = PaperStateStore(str(state_file))
    state = store.read()
    assert state["session"]["state_version"] == "paper_v1"
```

---

### P2 — 本週執行（業務邏輯完整性）

**T09：MarketDataDispatcher — Tick Consumer 回調異常不影響其他消費者**
```python
def test_tick_consumer_exception_does_not_stop_other_consumers():
    """一個消費者拋出異常，其他消費者仍收到 tick"""
    dispatcher.register_tick_consumer(lambda e: raise_exception())
    received = []
    dispatcher.register_tick_consumer(lambda e: received.append(e))
    dispatcher._on_price_event(make_price_event("BTCUSDT", 60000))
    assert len(received) == 1
```

**T10：WS Listener — 畸形 JSON 不崩潰**
```python
def test_handle_message_malformed_json_ignored(listener):
    """畸形 JSON 消息不崩潰，price cache 不更新"""
    listener._handle_message("{ invalid json }")
    assert listener.get_latest_price("BTCUSDT") is None
```

**T11：WS Listener — on_error callback 不拋出**
```python
def test_on_error_does_not_raise(listener):
    """WS error 回調被調用時，listener 不崩潰"""
    listener._run_loop()  # 使用 mock WS
    mock_ws.on_error(mock_ws, ConnectionResetError("connection reset"))
    assert listener.is_running() is True
```

**T12：GovernanceHub — Daily Loss 跨天重置**
```python
def test_risk_manager_daily_loss_resets_at_midnight():
    """跨天後，daily_loss_triggered 狀態被清除，新訂單可提交"""
    engine_with_risk.risk_manager._state["daily_loss_usd"] = 9999
    engine_with_risk.risk_manager._state["daily_loss_triggered"] = True
    # Simulate midnight reset
    engine_with_risk.risk_manager.reset_daily_counters()
    result = engine_with_risk.submit_order("BTCUSDT", "Buy", "market", 0.01)
    assert result["order"]["state"] != "rejected"
```

**T13：Strategy Orchestrator — 多策略隔離**
```python
def test_multi_strategy_state_isolated():
    """兩個策略（MA + BB）各自維護獨立狀態，不互相干擾"""
    orch.deploy_strategy("MA_Crossover", "BTCUSDT", {})
    orch.deploy_strategy("Bollinger_Breakout", "ETHUSDT", {})
    orch.pause_strategy("MA_Crossover", "BTCUSDT")
    assert orch.get_strategy_status("Bollinger_Breakout", "ETHUSDT")["state"] == "active"
```

**T14：TelegramAlerter — 速率限制**
```python
def test_rate_limit_blocks_excess_messages():
    """rate_limit_per_min=3 時，第 4 條消息被拒絕"""
    alerter = TelegramAlerter(bot_token="x", chat_id="y", rate_limit_per_min=3)
    with patch("urllib.request.urlopen") as mock_url:
        mock_url.return_value.__enter__.return_value.read.return_value = b'{"ok":true}'
        for _ in range(3):
            alerter.send("msg")
        result = alerter.send("blocked")
    assert result is False
    assert alerter.get_stats()["messages_rate_limited"] == 1
```

**T15：GrafanaDataWriter — 無 PG 連接優雅降級**
```python
def test_writer_starts_without_pg(monkeypatch):
    """無 OPENCLAW_GRAFANA_PG_* 環境變量時，writer.start() 不崩潰"""
    monkeypatch.delenv("OPENCLAW_GRAFANA_PG_HOST", raising=False)
    writer = GrafanaDataWriter(engine=mock_engine)
    writer.start()
    time.sleep(0.1)
    writer.stop()
    assert writer.get_stats()["writes_attempted"] == 0
```

**T16：StopManager — 同一符號多策略 Key 衝突**
```python
def test_multiple_strategies_same_symbol():
    """MA_Crossover 和 Grid 都跟蹤 BTCUSDT，各自獨立"""
    sm.track_position("BTCUSDT", "long", 60000, 0.001, "MA_Crossover")
    sm.track_position("BTCUSDT", "short", 60000, 0.001, "Grid")
    status = sm.get_status()
    assert len(status["tracked_positions"]) == 2
```

**T17：Governance Routes — request_authorization HTTP 層**
```python
def test_post_governance_auth_request_returns_201(client):
    """POST /api/v1/governance/auth/request → 201 + request_id"""
    resp = client.post("/api/v1/governance/auth/request",
        headers=auth_headers(),
        json={"scope": "paper_trading", "reason": "test", "requested_by": "operator"})
    assert resp.status_code in (200, 201)
    assert "request_id" in resp.json()["data"]
```

**T18：Governance Routes — Symbol Whitelist CRUD**
```python
def test_whitelist_add_and_remove(client):
    """符號白名單的增刪改查端到端"""
    # Add
    resp = client.post("/api/v1/governance/whitelist/add",
        headers=auth_headers(), json={"symbol": "SOLUSDT", "added_by": "operator"})
    assert resp.status_code == 200
    # Verify
    symbols = client.get("/api/v1/governance/whitelist", headers=auth_headers()).json()["data"]
    assert "SOLUSDT" in symbols
    # Remove
    client.delete("/api/v1/governance/whitelist/SOLUSDT", headers=auth_headers())
    symbols2 = client.get("/api/v1/governance/whitelist", headers=auth_headers()).json()["data"]
    assert "SOLUSDT" not in symbols2
```

---

### P3 — 下週執行（回歸和邊界完善）

**T19：OMS SM-03 Disabled 退回舊版流程**
```python
def test_paper_engine_falls_back_to_7state_when_oms_disabled(tmp_path, monkeypatch):
    """OMS_SM03_ENABLED=False 時，使用 7 狀態舊版生命週期"""
    monkeypatch.setattr("app.paper_trading_engine.OMS_SM03_ENABLED", False)
    # ... order lifecycle uses old 7-state path
```

**T20：Lease TTL ±1ms 邊界**
```python
async def test_lease_expires_exactly_at_ttl():
    """TTL=0.001 秒的 lease 在 1ms 後被視為過期"""
    sm = DecisionLeaseStateMachine()
    lease_id = sm.create_draft("test", "test_scope")
    sm.transition(lease_id, "REGISTERED")
    sm.transition(lease_id, "ACTIVE")
    time.sleep(0.002)
    # lease should be expired
    assert sm.is_expired(lease_id)
```

**T21：Pipeline Bridge 並發 Tick 和 Deactivate**
```python
def test_concurrent_tick_and_deactivate_no_deadlock():
    """多線程同時 on_tick 和 deactivate，無死鎖"""
    bridge.activate()
    errors = []
    def tick_worker():
        for _ in range(100):
            bridge.on_tick({"symbol": "BTCUSDT", "last_price": 60000.0, "ts_ms": ts()})
    def deactivate_worker():
        time.sleep(0.01)
        bridge.deactivate()
    threads = [Thread(target=tick_worker), Thread(target=deactivate_worker)]
    [t.start() for t in threads]
    [t.join(timeout=5) for t in threads]
    assert not any(t.is_alive() for t in threads)  # No deadlock
```

**T22：ScannerRateLimiter 多線程並發**
```python
def test_rate_limiter_thread_safe():
    """50 個線程同時請求 token，總通過數不超過 burst_size"""
    limiter = ScannerRateLimiter(rate=10, burst_size=50)
    granted = []
    lock = threading.Lock()
    def try_acquire():
        if limiter.try_acquire("BTCUSDT"):
            with lock: granted.append(1)
    threads = [Thread(target=try_acquire) for _ in range(200)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(granted) <= 50
```

**T23：Layer2 Daily Budget via Routes**
```python
def test_analyze_endpoint_returns_429_when_budget_exceeded(client):
    """每日預算超限時，/layer2/analyze 返回 429 或 budget_exceeded 響應"""
    tracker.force_daily_spend(999.99)  # Exceed hard cap
    resp = client.post("/api/v1/layer2/analyze", headers=auth_headers(), json={...})
    assert resp.json()["data"]["session_state"] == "budget_exceeded"
```

**T24：ChangeAuditLog 並發寫入**
```python
def test_change_audit_log_concurrent_writes():
    """10 個線程同時寫入，所有條目均持久化"""
    def write_entry(i):
        cal.log_change(ChangeType.CONFIG_CHANGE, f"agent_{i}", {"key": i})
    threads = [Thread(target=write_entry, args=(i,)) for i in range(10)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    history = cal.get_change_history()
    assert len(history) == 10
```

**T25：Paper Trading — 浮點精度累計 PnL**
```python
def test_pnl_float_precision_across_many_trades(active_engine):
    """100 筆小額往返，cumulative PnL 無浮點漂移"""
    for _ in range(100):
        active_engine.submit_order("BTCUSDT", "Buy", "market", 0.001)
        active_engine.tick({"BTCUSDT": 60001.0})
        active_engine.submit_order("BTCUSDT", "Sell", "market", 0.001)
    pnl = active_engine.get_state()["pnl"]["net_realized_pnl"]
    # Net PnL should be deterministic (small positive or negative due to fees)
    assert abs(pnl) < 10.0  # Not blown up due to float errors
```

**T26：Strategist AI Evaluate Timeout**
```python
def test_ai_evaluate_ollama_timeout_falls_back():
    """Ollama generate() 超時時，回退到 heuristic evaluation"""
    mock_ollama = MagicMock()
    mock_ollama.generate.side_effect = TimeoutError
    agent = StrategistAgent(ollama_client=mock_ollama)
    agent.start()
    evaluation = agent._evaluate_edge(make_intel("BTCUSDT"))
    assert evaluation is not None  # Heuristic fallback succeeded
```

**T27：Bybit Public WS — 訂閱消息格式**
```python
def test_subscription_message_sent_on_open():
    """on_open 後，訂閱消息格式符合 Bybit V5 WebSocket 規範"""
    messages_sent = []
    with patch("websocket.WebSocketApp") as mock_ws_class:
        mock_ws = MagicMock()
        mock_ws_class.return_value = mock_ws
        listener = BybitPublicWSListener(symbols=["BTCUSDT"])
        # Extract on_open callback
        on_open_cb = mock_ws_class.call_args[1]["on_open"]
        on_open_cb(mock_ws)
    sent = json.loads(mock_ws.send.call_args[0][0])
    assert sent["op"] == "subscribe"
    assert "tickers.BTCUSDT" in sent["args"]
```

**T28：Recovery Approval Gate — 並發審批**
```python
def test_recovery_request_only_approved_once():
    """同一 request_id 被兩個線程同時 approve，只有第一個成功"""
    request_id = gate.create_request(...)
    results = []
    def approve():
        result = gate.approve(request_id, "operator")
        results.append(result)
    threads = [Thread(target=approve) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count(True) == 1
    assert results.count(False) == 1
```

**T29：Edge Filter — 整個 Pipeline 端到端 Fail-Open**
```python
def test_edge_filter_exception_intent_still_submitted():
    """Edge filter 拋出異常，intent 仍通過（fail-open），order 被提交"""
    mock_ollama = MagicMock()
    mock_ollama.judge_edge.side_effect = RuntimeError("unexpected error")
    bridge.set_ollama_client(mock_ollama)
    bridge.activate()
    # inject intent
    bridge._process_pending_intents()
    assert len(mock_engine.submitted_orders) == 1
```

**T30：BybitDemoSync — 條件單觸發同步**
```python
def test_demo_sync_conditional_order_created_on_fill():
    """Paper Engine 成交後，BybitDemoSync.sync_stop_order() 被調用"""
    mock_connector = MagicMock()
    sync = BybitDemoSync(mock_connector)
    paper_engine.set_demo_sync(sync)
    paper_engine.start_session()
    paper_engine.submit_order("BTCUSDT", "Buy", "market", 0.001)
    paper_engine.tick({"BTCUSDT": 60000.0})
    # Expect conditional stop order placed on demo exchange
    mock_connector.place_conditional_order.assert_called_once()
```

---

## 九、測試框架改進建議

### 9.1 補充 pytest coverage 配置

```ini
# pytest.ini 或 setup.cfg 中添加
[tool:pytest]
addopts = --cov=app --cov-report=html --cov-fail-under=75
```
當前 2,227 個 passing test 在 CI 中未見覆蓋率閾值，建議立即補充。

### 9.2 為 pipeline_bridge.py 建立獨立測試套件

`test_pipeline_bridge.py` 應遷移到 `control_api_v1/tests/`（因 PipelineBridge 依賴 GovernanceHub、PaperTradingEngine），並擴展為 50+ 個測試用例，特別針對：
- Governance Gate Integration
- Stop Manager Integration
- L2 Cron Trigger
- Round-trip PnL callback

### 9.3 建立 "H0 Gate SLA" 性能測試

根據 CLAUDE.md Phase 1 Batch 1A 計劃，H0 Gate 要求 `<1ms` SLA。建議添加：
```python
def test_h0_gate_latency_under_1ms():
    """is_authorized() 在緩存命中時 <1ms"""
    hub.grant_paper_authorization()
    start = time.perf_counter()
    for _ in range(1000):
        hub.is_authorized()
    elapsed = (time.perf_counter() - start) / 1000
    assert elapsed < 0.001  # <1ms per call
```

### 9.4 建立 WS 層 Mock 框架

為 `bybit_public_ws_listener.py` 和 `market_data_dispatcher.py` 的集成測試建立統一 WS Mock：
```python
# tests/conftest.py 中添加
@pytest.fixture
def mock_ws_listener():
    """Mock BybitPublicWSListener，可手動注入 price events"""
    listener = MockWSListener(symbols=["BTCUSDT", "ETHUSDT"])
    yield listener

def inject_price_event(listener, symbol, price):
    event = PriceEvent(symbol=symbol, last_price=price, ts_ms=int(time.time()*1000))
    listener._on_price_event(event)
```

### 9.5 回歸測試標記規範

對所有已修復 bug 的回歸測試添加 `@pytest.mark.regression` 標記，並在 CI 中加 `pytest -m regression` 獨立執行步驟：
```python
@pytest.mark.regression
def test_messagebus_subscribe_2_params():
    """回歸：MessageBus.subscribe() 3→2 參數 bug（Round 2.5 P0 修復）"""
    bus = MessageBus()
    received = []
    bus.subscribe(AgentRole.STRATEGIST, lambda m: received.append(m))  # 2 params
    # Should not raise TypeError
```

### 9.6 添加 E2E 測試環境健康檢查

當前 35 個 E2E smoke tests（test_batch12_e2e_smoke.py）在每次 CI 運行時執行，但若底層 GovernanceHub 初始化失敗，所有 E2E 測試會靜默通過（因為測試中部分用 `hub._enabled = False` mock）。建議加入：
```python
@pytest.fixture(scope="session", autouse=True)
def assert_governance_hub_initializes():
    """每次測試前，驗證 GovernanceHub 可以成功初始化"""
    hub = GovernanceHub(audit_dir=str(tmp_path))
    assert hub.is_enabled is True
```

### 9.7 為 BybitDemoConnector 建立 VCR/Cassette 機制

```python
# 使用 responses 或 vcrpy 錄製 Bybit Demo API 回應
@responses.activate
def test_submit_order_with_real_response_format():
    responses.add(responses.POST, "https://api-demo.bybit.com/v5/order/create",
                  json={"retCode": 0, "retMsg": "OK", "result": {"orderId": "123"}})
    result = connector.submit_order("BTCUSDT", "Buy", "Market", qty=0.001)
    assert result["retCode"] == 0
```

---

## 附錄：未覆蓋模塊優先級矩陣

| 優先級 | 模塊 | LOC | 建議測試數量 | 預估工時 |
|--------|------|-----|------------|---------|
| P1 | pipeline_bridge.py | 1,550 | 50 | 2 天 |
| P1 | governance_routes.py | 1,698 | 40 | 2 天 |
| P1 | bybit_demo_connector.py | 336 | 20 | 0.5 天 |
| P2 | bybit_public_ws_listener.py | 460 | 25 | 1 天 |
| P2 | phase2_strategy_routes.py | 1,308 | 20 | 1 天 |
| P2 | market_data_dispatcher.py（擴展） | 431 | 15 | 0.5 天 |
| P3 | strategist_agent.py（擴展） | 585 | 20 | 1 天 |
| P3 | grafana_data_writer.py | 359 | 10 | 0.5 天 |
| P3 | telegram_alerter.py | 172 | 8 | 0.25 天 |
| P3 | bybit_demo_sync.py（擴展） | 269 | 10 | 0.5 天 |

**預估補齊 P1+P2 缺口總工時：7 天**

---

*報告由 E4（Testing Evaluator）生成。評估基於靜態代碼分析，未運行 coverage 工具。實際覆蓋率可能因 mock 深度而有偏差。*
