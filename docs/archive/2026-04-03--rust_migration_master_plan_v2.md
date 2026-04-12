> ⚠️ DEPRECATED — 此文件為 V2 草稿，已由 `docs/references/2026-04-03--rust_migration_v3_final.md`（V3-FINAL）取代。保留供歷史參考，請勿作為實施依據。

# OpenClaw Bybit — Rust 遷移總方案

**日期**: 2026-04-03
**版本**: V2-FINAL（一步到位方案）
**基於**: SYSTEM_SNAPSHOT.md + OPENCLAW_IMPROVEMENT_REPORT_V3_FINAL + AGENT_COGNITIVE_ADAPTATION_SPEC
**目標**: Rust 為交易路徑主人，Python 退化為 AI 服務 + GUI 層
**執行方式**: 一步到位 + 灰度驗證（無中間 PyO3 過渡態）

---

# Claude Code 快速入口

```
本文件是 Rust 遷移的完整 SPEC。

核心思想：
  直接建造最終架構——Rust 交易引擎 + Python AI 服務
  無中間態 PyO3 包裝層（省掉一次性技術債）
  通過灰度驗證（雙寫雙算）確保正確性

最終架構：
  Rust 交易引擎（獨立二進制，含快速通道）
    - 自己訂閱 WebSocket
    - 自己跑整條確定性路徑（<0.3ms/tick）
    - 只在需要 AI 時調用 Python
  Python AI + GUI 進程（FastAPI）
    - 接收 Rust 的 AI 請求
    - 調用 Ollama / Claude API
    - 提供 GUI / Control API

閱讀順序：
  §1 — 最終架構全貌
  §2 — Rust 遷移完整清單（每個 Python 文件的歸屬）
  §3 — Rust crate 結構
  §4 — 進程間通信協議
  §5 — 灰度驗證框架
  §6 — 10 週開發路線圖
  §7 — 風險和回退策略
  §8 — 量化總結
```

---

# 第一部分：最終目標架構

## 1.1 進程模型

```
┌──────────────────────────────────────────────────────────────┐
│  Rust 交易引擎 — openclaw_engine（獨立二進制）                 │
│  tokio async runtime · 單一進程 · 無 GC · 確定性延遲          │
│                                                               │
│  ┌─ WebSocket 層 ──────────────────────────────────────────┐ │
│  │ Bybit WS 訂閱（自己連接，不依賴 Python）                  │ │
│  │ 價格解析 → PriceEvent · 自動重連 + 心跳                   │ │
│  └──────────────────────────────────────────────────────────┘ │
│       ↓                                                       │
│  ┌─ 注意力節流 ────────────────────────────────────────────┐ │
│  │ attention 級別（dormant/low/medium/high/critical）        │ │
│  │ 動態 tick 頻率控制                                       │ │
│  └──────────────────────────────────────────────────────────┘ │
│       ↓                                                       │
│  ┌─ 確定性計算鏈路（每 tick <0.3ms）─────────────────────┐  │
│  │  K 線聚合 → 13 指標計算 → 8 信號規則                    │  │
│  │       ↓                                                 │  │
│  │  認知調製（CognitiveModulator）                          │  │
│  │       ↓                                                 │  │
│  │  H0 Gate（5 項門控）                                     │  │
│  │       ↓                                                 │  │
│  │  4 狀態機（授權 + 租約 + 風控 + OMS）                    │  │
│  │       ↓                                                 │  │
│  │  Guardian 確定性審核（4 項數值檢查）                      │  │
│  │       ↓                                                 │  │
│  │  StopManager（hard/trailing/time stop）                  │  │
│  │       ↓                                                 │  │
│  │  組合風控（相關性 + delta + 總暴露）                      │  │
│  │       ↓                                                 │  │
│  │  訂單匹配 ENGINE.tick()                                  │  │
│  │       ↓                                                 │  │
│  │  執行計算（slippage + fee + fill_price）                  │  │
│  │       ↓                                                 │  │
│  │  PnL 歸因 + OpportunityTracker 更新                      │  │
│  └─────────────────────────────────────────────────────────┘  │
│       ↓                                                       │
│  ┌─ 快速通道（優先級最高，不等 AI，不經 Python）──────┐       │
│  │ Risk Governor ≥ DEFENSIVE → 預定義規則 → 直接執行   │       │
│  │ 閃崩 / 保證金危機 → 立即平倉                        │       │
│  │ 和正常通道在同一進程，用優先級隊列區分               │       │
│  └─────────────────────────────────────────────────────┘       │
│       ↓                                                       │
│  ┌─ AI 請求通道（異步，不阻塞 tick）──────────────────┐      │
│  │ 需要 Strategist/Analyst/Conductor AI → 發請求到 Python    │
│  │ AI 回覆後 → 下一個 tick 周期處理結果                      │
│  └─────────────────────────────────────────────────────────┘  │
│       ↓                                                       │
│  ┌─ 後台引擎 ──────────────────────────────────────────┐     │
│  │ DreamEngine（閒置蒙特卡洛）· BacktestEngine           │     │
│  │ MessageBus（Agent 間消息路由）                        │     │
│  └─────────────────────────────────────────────────────────┘  │
│                                                               │
│  持久化：JSON debounced · 審計：JSONL append-only             │
│  IPC：Unix domain socket（雙向 JSON-RPC 2.0）                │
└──────────────────────────────────────────────────────────────┘
        ↕ Unix domain socket
┌──────────────────────────────────────────────────────────────┐
│  Python AI + GUI 進程 — FastAPI                               │
│                                                               │
│  AI 服務：Strategist/Analyst/Conductor/Scout AI 推理          │
│  GUI：FastAPI 126+ routes · Operator 指令 → IPC 轉發          │
│  學習：TSR · ExperimentLedger · EvolutionScheduler            │
│  外部：OllamaClient · Claude API · Telegram · Grafana · Bybit│
│  治理：GovernanceHub 高層業務 · 對賬 · 審計                   │
└──────────────────────────────────────────────────────────────┘
```

## 1.2 設計原則

```
1. Rust 擁有整條確定性路徑——WS 到下單，Python 不介入
2. Python 只做 AI 推理 + GUI + 學習系統 + 審計高層邏輯
3. AI 推理不阻塞 tick——請求後繼續，回覆下一周期消費
4. 兩個進程可獨立重啟——Python 掛了引擎降級 L0 繼續跑
5. 無中間態——不建 PyO3 包裝層，直接到終態
```

---

# 第二部分：Rust 遷移完整清單

## 2.1 計算核心（openclaw_core 庫）

| 源文件 | 提取的邏輯 | Rust 目標 | 行數 |
|--------|-----------|----------|------|
| local_model_tools/indicator_engine.py | 7 指標 + V3 新增 6 指標 | core/indicators.rs | ~500 |
| local_model_tools/signal_generator.py | 8 信號規則 | core/signals.rs | ~300 |
| local_model_tools/kline_manager.py | K 線聚合 | core/klines.rs | ~200 |
| app/h0_gate.py | 5 項門控 + H0HealthWorker | core/h0_gate.rs | ~300 |
| app/risk_manager.py | PriceHistoryTracker + ATR + spike + dynamic stop + cost | core/risk.rs | ~400 |
| app/market_data_dispatcher.py | 注意力級別計算 | core/attention.rs | ~120 |
| app/guardian_agent.py | 4 項確定性檢查 | core/guardian.rs | ~250 |
| app/paper_trading_engine.py | slippage + fill_price + fee | core/execution.rs | ~180 |
| app/paper_trading_engine.py | ENGINE.tick() 訂單匹配 | core/order_match.rs | ~300 |
| app/paper_trading_engine.py | mutate() 計算和驗證 | core/state_compute.rs | ~350 |
| app/portfolio_risk_control.py | 相關性 + delta + 總暴露 | core/portfolio.rs | ~280 |
| local_model_tools/stop_manager.py | hard/trailing/time stop | core/stop_manager.rs | ~250 |
| app/multi_agent_framework.py | MessageBus 核心 | core/message_bus.rs | ~350 |
| app/authorization_state_machine.py | 完整狀態機 | core/sm_auth.rs | ~350 |
| app/decision_lease_state_machine.py | 完整狀態機 | core/sm_lease.rs | ~400 |
| app/risk_governor_state_machine.py | 完整狀態機 | core/sm_risk_gov.rs | ~430 |
| app/oms_state_machine.py | 完整 OMS 11 態 | core/sm_oms.rs | ~350 |
| app/trade_attribution.py | PnL 歸因 | core/attribution.rs | ~220 |
| local_model_tools/backtest_engine.py | 完整回測 | core/backtest.rs | ~450 |
| **新增** | JSON Schema 驗證 | core/schema.rs | ~200 |
| **新增** | CognitiveModulator | core/cognitive.rs | ~150 |
| **新增** | OpportunityTracker | core/opportunity.rs | ~300 |
| **新增** | DreamEngine | core/dream.rs | ~450 |
| | | **core 總計** | **~7,080** |

## 2.2 引擎編排層（openclaw_engine 二進制）

| 源文件 | 遷移的邏輯 | Rust 目標 | 行數 |
|--------|-----------|----------|------|
| app/pipeline_bridge.py | on_tick() 4 步編排 | engine/tick_pipeline.rs | ~600 |
| app/pipeline_bridge.py | 意圖處理流程 | engine/intent_processor.rs | ~400 |
| app/pipeline_bridge.py | 依賴注入 → 構造函數 | engine/config.rs | ~200 |
| app/market_data_dispatcher.py | tick 分發和節流 | engine/dispatcher.rs | ~350 |
| app/bybit_public_ws_listener.py | WS 連接 + 重連 | engine/ws_client.rs | ~300 |
| app/paper_trading_engine.py | 狀態管理 + 持久化 | engine/paper_state.rs | ~400 |
| app/governance_hub.py | is_authorized + lease 確定性部分 | engine/governance.rs | ~350 |
| local_model_tools/strategy_orchestrator.py | dispatch + 部署管理 | engine/orchestrator.rs | ~300 |
| local_model_tools/strategies/*.py | 5 策略 on_tick | engine/strategies/*.rs | ~1,200 |
| **新增** | 快速通道 | engine/fast_track.rs | ~350 |
| **新增** | 主循環 + tokio | engine/main.rs | ~300 |
| **新增** | IPC 服務端 | engine/ipc_server.rs | ~400 |
| **新增** | 持久化管理 | engine/persistence.rs | ~250 |
| **新增** | 審計日誌 | engine/audit.rs | ~200 |
| | | **engine 總計** | **~5,600** |

## 2.3 共享類型（openclaw_types）

| 內容 | Rust 文件 | 行數 |
|------|----------|------|
| PriceEvent, Kline, OHLCV | types/price.rs | ~100 |
| TradeIntent, OrderIntent, RiskVerdict | types/intent.rs | ~150 |
| AgentRole, MessageType, AgentMessage | types/agent.rs | ~120 |
| GovernanceMode, AgentState, OmsState | types/state.rs | ~100 |
| RiskConfig, H0CheckResult, GuardianConfig | types/risk.rs | ~130 |
| CognitiveParams, RegretSummary, DreamInsight | types/cognitive.rs | ~100 |
| EngineConfig 全局配置 | types/config.rs | ~150 |
| | **types 總計** | **~850** |

## 2.4 Python 文件最終歸屬

### 完整刪除（~12,000 行）

```
app/pipeline_bridge.py · app/market_data_dispatcher.py · app/bybit_public_ws_listener.py
app/h0_gate.py · app/authorization_state_machine.py · app/decision_lease_state_machine.py
app/risk_governor_state_machine.py · app/oms_state_machine.py
local_model_tools/indicator_engine.py · signal_generator.py · kline_manager.py
local_model_tools/stop_manager.py · strategy_orchestrator.py
local_model_tools/strategies/*.py（5 個策略文件）
```

### 部分瘦身（~4,500 行 → ~1,500 行）

| 文件 | 遷移到 Rust | 保留 |
|------|------------|------|
| risk_manager.py | 全部計算函數 | GlobalRiskConfig 定義 |
| guardian_agent.py | 4 項確定性檢查 | AI 評估 + Agent 生命週期 |
| paper_trading_engine.py | 計算 + 匹配 + mutate | PaperStateStore I/O + 常量 |
| multi_agent_framework.py | MessageBus 核心 | enum + Agent 基類 + dataclass |
| portfolio_risk_control.py | 計算核心 | 高層規則 |
| governance_hub.py | 確定性邏輯 | 高層業務判斷 |
| trade_attribution.py | 歸因計算 | 刪除或空殼 |
| backtest_engine.py | run() 完整 | 刪除或空殼 |

### 新增 Python（~800 行）

```
app/ai_service.py    — AI 請求處理（~500 行）
app/ipc_client.py    — GUI 讀取 Engine 狀態（~300 行）
```

### 修改 Python（~1,500 行改動）

```
main.py · phase2_strategy_routes.py · paper_trading_routes.py
risk_routes.py · governance_routes.py · 其他 *_routes.py
```

### 完全保留（不動）

```
strategist_agent.py · analyst_agent.py · executor_agent.py · scout_worker.py
ollama_client.py · model_router.py · layer2_engine.py + layer2_*.py
h1_thought_gate.py · h4_validator.py · truth_source_registry.py
experiment_ledger.py · evolution_auto_scheduler.py · learning_*.py
state_compiler.py · state_store.py · state_models.py · state_helpers.py
bybit_demo_connector.py · bybit_demo_sync.py · telegram_alerter.py · grafana_data_writer.py
auth.py · control_ops.py · pnl_ops.py · shadow_decision_builder.py
symbol_category_registry.py · scanner_rate_limiter.py
audit_persistence.py · change_audit_log.py · reconciliation_engine.py
recovery_approval_gate.py · ttl_enforcer.py · incident_event_model.py
perception_data_plane.py · data_source_enforcer.py · protective_order_manager.py
paper_live_gate.py · governance_events.py · 所有 *_routes.py
```

---

# 第三部分：Rust Crate 結構

```
rust/
├── Cargo.toml                          ← workspace root
│
├── openclaw_types/
│   └── src/
│       ├── lib.rs
│       ├── price.rs · intent.rs · agent.rs
│       ├── state.rs · risk.rs · cognitive.rs · config.rs
│
├── openclaw_core/                      ← 純 Rust 庫（無 PyO3）
│   └── src/
│       ├── lib.rs
│       ├── indicators.rs · signals.rs · klines.rs        # 感知
│       ├── h0_gate.rs · risk.rs · attention.rs            # 風控
│       ├── guardian.rs · stop_manager.rs · portfolio.rs    # 審核
│       ├── sm_auth.rs · sm_lease.rs · sm_risk_gov.rs · sm_oms.rs  # 狀態機
│       ├── execution.rs · order_match.rs · state_compute.rs  # 執行
│       ├── cognitive.rs · opportunity.rs · dream.rs        # 認知自適應
│       ├── backtest.rs · attribution.rs · message_bus.rs   # 分析
│       └── schema.rs                                       # JSON 驗證
│
└── openclaw_engine/                    ← 交易引擎二進制
    └── src/
        ├── main.rs                     # tokio runtime + 信號處理
        ├── ws_client.rs · dispatcher.rs                    # 數據接入
        ├── tick_pipeline.rs · intent_processor.rs          # 交易路徑
        ├── fast_track.rs                                    # 快速通道
        ├── orchestrator.rs                                  # 策略調度
        ├── strategies/
        │   ├── mod.rs · ma_crossover.rs · grid_trading.rs
        │   ├── bb_reversion.rs · bb_breakout.rs · funding_arb.rs
        ├── governance.rs · paper_state.rs                   # 治理+狀態
        ├── config.rs · persistence.rs · audit.rs            # 基礎設施
        └── ipc_server.rs                                    # IPC 服務端
```

---

# 第四部分：進程間通信協議

## 4.1 通信方式

```
方式：Unix domain socket · 路徑：/tmp/openclaw_engine.sock
協議：JSON-RPC 2.0（\n 分隔）· 延遲：~0.1ms
```

## 4.2 Rust → Python（AI 請求）

```json
{"jsonrpc":"2.0","id":"req-001","method":"strategist_evaluate","params":{
  "symbol":"BTCUSDT",
  "indicators":{"hurst":0.62,"ewma_vol":0.023,"adx":28.5},
  "signals":[{"name":"MA_Cross","direction":"long","confidence":0.65}],
  "context":{"regime":"trending","pressure":{"confidence_floor":0.68,"qty_ceiling":0.85}},
  "dream":{"MA_Cross":{"stoploss_pct":{"suggested":2.0,"conf":0.71}}}
}}
```

## 4.3 Python → Rust（AI 回覆）

```json
{"jsonrpc":"2.0","id":"req-001","result":{
  "decision":"trade","direction":"long","qty_fraction":0.8,
  "confidence":0.72,"reasoning":"Hurst=0.61 trending"
}}
```

## 4.4 Python → Rust（Operator 控制）

```json
{"jsonrpc":"2.0","id":"ctl-001","method":"operator_command","params":{
  "command":"pause_trading"
}}
```

## 4.5 Rust → Python（狀態推送，每秒 1 次）

```json
{"jsonrpc":"2.0","method":"state_update","params":{
  "ts_ms":1712100000,"prices":{"BTCUSDT":84500},
  "positions_count":3,"unrealized_pnl":25.5,
  "attention_level":"medium","risk_governor":"NORMAL",
  "cognitive":{"confidence_floor":0.63,"qty_ceiling":0.85},
  "dream_cycles":847
}}
```

## 4.6 超時和降級

```
AI 請求 TTL：Strategist 15s · Analyst 30s · Conductor 10s
超時 → L0 確定性邏輯代替
Python 斷連 → ai_available=false → 全部 L0 · 每 5s 重連 · 告警
```

---

# 第五部分：灰度驗證框架

## 5.1 灰度期架構（Week 9-10）

```
Bybit WS ──→ Rust Engine（真正下單到 Paper）→ engine_results.jsonl
       │
       └────→ Python 影子進程（只算不下單）→ shadow_results.jsonl
```

## 5.2 影子進程保留的模組

```
BybitPublicWsListener · MarketDataDispatcher · KlineManager
IndicatorEngine · SignalEngine · H0Gate
RiskManager 計算函數 · StopManager · 4 狀態機
```

## 5.3 每 tick 輸出格式

```json
{"ts_ms":1712100000,"symbol":"BTCUSDT","type":"tick","data":{
  "indicators":{"sma_20":84300,"rsi":55.2,"atr":150.5},
  "signals":[{"name":"MA_Cross","direction":"long","confidence":0.65}],
  "h0":{"passed":true,"checks":{"freshness":true,"health":true,
    "eligibility":true,"envelope":true,"cooldown":true}},
  "attention":"medium",
  "risk":{"atr_pct":0.18,"spike":false,"dynamic_stop":1.8}
}}
```

## 5.4 對比規則

```
嚴格一致（差異 = 0）：
  H0 門控 5 個 bool · 信號方向 · 信號名稱 · attention 級別 · 狀態機轉換

允許浮點誤差（< 1e-6）：
  所有指標值 · confidence · ATR · dynamic_stop · slippage · fee

灰度結束條件：
  連續 7 天 CRITICAL = 0 且 WARNING < 10
```

## 5.5 灰度後處理

```
驗證通過 → 關閉影子進程 → git tag "pre-rust-cleanup"
→ 保留冗餘 Python 代碼 4 週 → 確認穩定後最終刪除
```

---

# 第六部分：10 週開發路線圖

```
Week 1-2: 基礎設施 + IPC + 類型
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Cargo workspace · openclaw_types 全部類型
  IPC 雙端實現（Rust ipc_server + Python ai_service + ipc_client）
  通信驗證（echo + 壓力測試）
  engine/main.rs 骨架（啟動 + WS 連接 + IPC 通信）
  
  ✅ 交付：兩個進程能互發 JSON-RPC

Week 3-4: openclaw_core 上半（感知 + 認知 + 風控）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  indicators.rs(13) · signals.rs(8) · klines.rs
  h0_gate.rs · risk.rs · attention.rs
  cognitive.rs · opportunity.rs · dream.rs
  schema.rs · 全部單元測試

  ✅ 交付：所有感知和認知模組可獨立測試

Week 5-6: openclaw_core 下半 + engine 骨架
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  guardian.rs · execution.rs · order_match.rs · state_compute.rs
  portfolio.rs · stop_manager.rs
  sm_auth.rs · sm_lease.rs · sm_risk_gov.rs · sm_oms.rs
  message_bus.rs · attribution.rs · backtest.rs
  engine: ws_client.rs · dispatcher.rs · fast_track.rs

  ✅ 交付：core 全部完成 · engine 能接收 WS 並做注意力節流

Week 7-8: engine 完整交易路徑
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  tick_pipeline.rs · intent_processor.rs
  orchestrator.rs · strategies/*.rs（5 策略）
  governance.rs · paper_state.rs
  persistence.rs · audit.rs · config.rs
  端到端測試（WS → 計算 → 下單 → 持久化）

  ✅ 交付：Rust Engine 能獨立運行完整 Paper Trading

Week 9-10: Python 改造 + 灰度驗證
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Python GUI 路由改讀 IPC · phase2_strategy_routes 簡化
  main.py 連接 Rust Engine · 影子計算進程搭建
  灰度啟動：雙寫雙算 · 每日對比 · 至少 7 天
  驗證通過 → 關閉影子 → 清理冗餘代碼

  ✅ 交付：完整雙進程架構上線
```

---

# 第七部分：風險和回退策略

## 7.1 風險矩陣

| 風險 | 概率 | 影響 | 緩解 |
|------|------|------|------|
| Rust 計算和 Python 不一致 | 中 | 高 | 灰度 7 天雙寫雙算 |
| IPC 延遲或丟失 | 中 | 高 | TTL + 超時降級 L0 |
| 策略行為差異 | 中 | 高 | 灰度期逐信號對比 |
| Engine 崩潰 | 低 | 高 | systemd RestartSec=2 |
| 狀態文件衝突 | 中 | 中 | flock() + Rust 寫 Python 只讀 |
| GUI 無法讀取引擎 | 中 | 中 | 斷連時顯示最後快照 |
| 開發超期 | 中 | 中 | 每 2 週 checkpoint |

## 7.2 回退策略

```
Week 1-6（開發期）：隨時中止，Python 原始代碼完整
Week 7-8（測試期）：Engine 有問題直接關閉，Python 繼續
Week 9-10（灰度期）：CRITICAL 差異 > 0 → 暫停 Rust 排查
灰度後 +4 週：冗餘代碼保留，可回退
+4 週後刪除：不可回退（git tag 標記）
```

---

# 第八部分：量化總結

## 8.1 代碼量

```
Rust 新增：  types ~850 + core ~7,080 + engine ~5,600 = ~13,530 行（26%）
Python 變化：52,500 → ~38,300 行（74%）
總計：       ~51,830 行
```

## 8.2 性能

```
                     現在              遷移後
─────────────────────────────────────────────────
tick 路徑             15-60ms          0.1-0.3ms
GC 影響 tick          是               否
快速通道              不存在           <0.3ms（Engine 內）
DreamEngine           不存在           ~150k 輪/s
BacktestEngine        ~3k 輪/s         ~150k 輪/s
跨語言邊界/tick        N/A             0
Lock 數量             16+              0
Python 掛了           系統死亡         引擎繼續（L0）
```

## 8.3 時間投入

```
開發：10 週 · 灰度：1-2 週 · 穩定觀察：4 週 · 清理：1 週
總計：~16-17 週
前置：V3 Phase 1-3 完成 + alpha 驗證通過
```

---

# 附錄 A：環境配置

```bash
# Ubuntu 24
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
cd ~/BybitOpenClaw/rust
cargo build --release -p openclaw_engine
sudo cp target/release/openclaw_engine /usr/local/bin/

# Mac Studio 遷移：同一份源碼 cargo build --release，零修改
```

# 附錄 B：systemd 服務

```ini
# /etc/systemd/system/openclaw-engine.service
[Unit]
Description=OpenClaw Trading Engine (Rust)
After=network.target
[Service]
ExecStart=/usr/local/bin/openclaw_engine --config /home/ncyu/BybitOpenClaw/srv/settings/engine.toml
User=ncyu
Restart=always
RestartSec=2
MemoryMax=2G
CPUQuota=400%
Nice=-5
[Install]
WantedBy=multi-user.target

# /etc/systemd/system/openclaw-python.service
[Unit]
Description=OpenClaw AI + GUI (Python)
After=openclaw-engine.service
Requires=openclaw-engine.service
[Service]
ExecStart=/usr/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
WorkingDirectory=/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1
User=ncyu
Restart=always
RestartSec=3
MemoryMax=4G
Environment=OPENCLAW_ENGINE_SOCKET=/tmp/openclaw_engine.sock
[Install]
WantedBy=multi-user.target
```

# 附錄 C：Engine 配置

```toml
# settings/engine.toml
[websocket]
url = "wss://stream.bybit.com/v5/public/linear"
reconnect_delay_ms = 3000
heartbeat_interval_ms = 20000

[attention]
dormant_interval_ms = 60000
low_interval_ms = 10000
medium_interval_ms = 3000
high_interval_ms = 500
critical_interval_ms = 0

[risk]
max_stop_loss_pct = 5.0
max_take_profit_pct = 20.0
max_open_positions = 10
max_total_exposure_pct = 30.0

[cognitive]
base_confidence_floor = 0.60
base_qty_ceiling = 1.0
base_stoploss_multiplier = 1.0
base_scan_interval_s = 1800

[dream]
candle_window_days = 7
cycles_per_batch = 100
max_cycles_per_idle = 10000

[persistence]
state_file = "runtime/openclaw_bybit_control_state.json"
paper_state_file = "runtime/paper_state.json"
debounce_ms = 5000

[ipc]
socket_path = "/tmp/openclaw_engine.sock"
ai_request_ttl_ms = 15000
state_push_interval_ms = 1000
```

# 附錄 D：Rust 外部依賴

```toml
[workspace.dependencies]
tokio = { version = "1", features = ["full"] }
tokio-tungstenite = { version = "0.24", features = ["native-tls"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tracing = "0.1"
tracing-subscriber = "0.3"
thiserror = "2"
anyhow = "1"
rand = "0.8"
chrono = { version = "0.4", features = ["serde"] }
crossbeam-channel = "0.5"
parking_lot = "0.12"
nix = { version = "0.29", features = ["socket", "fs"] }
toml = "0.8"
```
