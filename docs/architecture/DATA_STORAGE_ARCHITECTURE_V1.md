# OpenClaw 數據存儲架構審計與 ML/DL-Ready 方案設計 V1

**Data Storage Architecture Audit & ML/DL-Ready Design V1**

日期 / Date: 2026-04-03
硬件 / Hardware: AMD AI MAX 395 · 128 GB Unified Memory · Ubuntu · 單機部署
原則 / Principles: 零成本可運行（開源工具）· 數據是不可再生資源

---

## 目錄 / Table of Contents

- [Phase 1: 代碼審計](#phase-1-代碼審計)
  - [1.1 JSON 持久化點](#11-json-持久化點)
  - [1.2 PostgreSQL 配置](#12-postgresql-配置)
  - [1.3 數據流全景圖](#13-數據流全景圖)
  - [1.4 數據量估算](#14-數據量估算)
- [Phase 2: 數據分類](#phase-2-數據分類)
- [Phase 3: 架構方案設計](#phase-3-架構方案設計)
  - [3.1 數據架構總覽圖](#31-數據架構總覽圖)
  - [3.2 PostgreSQL + TimescaleDB Schema](#32-postgresql--timescaledb-schema)
  - [3.3 ML/DL 數據管線設計](#33-mldl-數據管線設計)
  - [3.4 遷移計劃](#34-遷移計劃)
  - [3.5 目錄結構建議](#35-目錄結構建議)

---

# Phase 1: 代碼審計

## 1.1 JSON 持久化點

### 1.1.1 核心運行時狀態（Core Runtime State）

| # | 組件 | 檔案位置 | 數據描述 | 寫入頻率 | 讀取模式 | 原子寫入 | 併發保護 |
|---|------|---------|---------|---------|---------|---------|---------|
| 1 | **JsonStateStore** | `control_api_v1/runtime/openclaw_bybit_control_state.json` (253 KB) | 完整控制狀態機快照：schema version、全局 runtime facts、per-product-family 狀態、capability states、audit trails | 每次 HTTP PATCH（按需） | 啟動全量載入 + 每次編譯前讀取 | ✅ tempfile + os.replace | RLock |
| 2 | **PaperTradeStateStore** | `control_api_v1/runtime/paper_trading_state.json` (233 KB) | Paper trading 完整狀態：session、orders[]、fills[]、positions{}、PnL metrics | 防抖寫入（1.0s 間隔）+ 關機強制刷 | 啟動載入 + 內存 dirty cache | ✅ tempfile + os.replace | RLock |
| 3 | **ApiBudgetManager** | `control_api_v1/runtime/api_budget_state.json` (~2 KB) | 月度 API 預算、花費、per-tier 調用冷卻時間戳 | 每次 API 調用（fail-open） | 初始化 + 每次請求檢查 | ✅ .tmp + .replace | 內部鎖 |
| 4 | **Layer2CostTracker** | `control_api_v1/runtime/layer2_cost_state.json` (~2 KB) | AI/搜索成本：config、pricing models、daily spend by date、session history | 每次 cost event（防抖） | 啟動恢復 + 日常查詢 | ✅ .tmp + .replace | RLock |
| 5 | **StrategyState** | `control_api_v1/runtime/strategy_state.json` (空) | 策略狀態（佔位符，未使用） | 從未寫入 | 從未讀取 | — | — |

**代碼位置：**
- JsonStateStore: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/state_store.py:358-402`
- PaperTradeStateStore: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_engine.py:232-287`
- ApiBudgetManager: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/api_budget_manager.py:205-250`
- Layer2CostTracker: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_cost_tracker.py:104-289`

---

### 1.1.2 學習系統（Learning System）

| # | 組件 | 檔案位置 | 數據描述 | 寫入頻率 | 讀取模式 | 原子寫入 | 併發保護 |
|---|------|---------|---------|---------|---------|---------|---------|
| 6 | **TruthSourceRegistry** | `settings/truth_registry_snapshot.json` (~1 KB) | PatternClaim[]：claim_id、pattern_text、cognitive_level (FACT/INFERENCE/HYPOTHESIS)、confidence、regime/strategy applicability、TTL | 手動 save_snapshot() | 啟動 skip-existing 載入 | ❌ 基礎寫入 | Lock（寫在鎖外） |
| 7 | **ExperimentLedger** | `program_code/settings/experiment_ledger_snapshot.json` (13 KB) | Hypothesis[]：hypothesis_id、strategy_name、regime、status (PENDING/RUNNING/CONFIRMED/REFUTED)、observation counts | 防抖 60s save_snapshot() | 啟動 skip-existing 載入 | ❌ 基礎寫入 | Lock（寫在鎖外） |

**⚠️ RACE CONDITION RISK**: TruthSourceRegistry 和 ExperimentLedger 的寫操作在鎖外執行。雖然當前寫入頻率低（手動/60s 防抖），但多 Agent 同時觸發 save 時理論上有競態風險。

**代碼位置：**
- TruthSourceRegistry: `control_api_v1/app/truth_source_registry.py:730-803`
- ExperimentLedger: `control_api_v1/app/experiment_ledger.py:780-854`

---

### 1.1.3 風控配置（Risk Control Config）

| # | 組件 | 檔案位置 | 數據描述 | 寫入頻率 | 讀取模式 | 原子寫入 | 併發保護 |
|---|------|---------|---------|---------|---------|---------|---------|
| 8 | **OperatorRiskManager** | `settings/risk_control_rules/operator_risk_config.json` (3.1 KB) | Operator P1 風控參數：leverage limits、position caps、daily loss limits、per-category configs | GUI/API 修改時 | 僅初始化載入 | ✅ tempfile + os.replace | 無（GUI 串行化） |

**代碼位置：** `control_api_v1/app/risk_manager.py:690-755`

---

### 1.1.4 WebSocket 監控（WebSocket Monitoring）

| # | 組件 | 檔案位置 | 數據描述 | 寫入頻率 | 讀取模式 | 原子寫入 | 併發保護 |
|---|------|---------|---------|---------|---------|---------|---------|
| 9 | **Private WS Status** | `connector_logs/bybit/bybit_private_ws_status.json` | 連接狀態：running、auth_ok、message_count、per-topic counts | 每 5-10s + 關機 | 只寫不讀 | ✅ Path.write_text | Lock |
| 10 | **Private WS Events** | `connector_logs/bybit/bybit_private_ws_events.jsonl` | 追加式事件日誌：event_kind、topic、op、conn_id、raw payload | 每個 WS 事件 | 只寫不讀（追加） | ✅ append | Lock |

**代碼位置：** `io_and_persistence/bybit_private_ws_listener.py:85-206`

---

### 1.1.5 事件驅動報告（Event-Driven Reports）

| # | 組件 | 檔案位置 | 數據描述 | 寫入頻率 | 讀取模式 | 原子寫入 |
|---|------|---------|---------|---------|---------|---------|
| 11 | **Decision Lease Reports** | `runtime/bybit/thought_gate/bybit_decision_lease_*_latest.json` | 決策租約審計報告、schema、最終審計 | 每次批次/報告生成 | 前置依賴載入 | ✅ Path.write_text |
| 12 | **Decision Packets** | `runtime/bybit/decision_packets/bybit/bybit_decision_packet_*.json` (39 files, 164 KB) | 交易決策上下文：account summary、positions、orders、execution summary | 每個 observer cycle | 前置依賴載入 | ✅ Path.write_text |
| 13 | **Observer Verdicts** | `runtime/bybit/verdicts/bybit/bybit_observer_verdict_*.json` (37 files, 156 KB) | 決策裁定：verdict_code、execution_allowed、urgency、risk_flags | 每個 observer cycle | 前置依賴載入 | ✅ Path.write_text |
| 14 | **Transition Engine** | `runtime/bybit/event_driven/transition_engine/*.json` (~10 types) | 狀態轉換：replay matrix、audit trail、rule layers、state graphs、checkpoints | 每次轉換處理 | 依賴鏈載入 | ✅ Path.write_text |
| 15 | **Business Events** | `runtime/bybit/business_events/*.json` + subdirs | 事件 fixtures、replays、regression contracts、validation results | 每次測試/驗證運行 | 測試依賴載入 | ✅ Path.write_text |
| 16 | **Connector Execution Logs** | `connector_logs/bybit/bybit_private_execution_history_*.json` (104 files, 868 KB) | Bybit API 查詢結果：per-category responses、retCode、result counts | 每次 API 查詢 | 按需回查 | ✅ Path.write_text |

**共用模式：** 所有 event-driven 報告同時寫入 `*_latest.json` 和 `*_{timestamp}.json`（dated snapshot），供審計追溯。

**代碼位置：**
- 共用 helpers: `bybit_decision_lease/bybit_decision_lease_common.py:31-92`
- Event-driven: `trading_strategy/bybit_event_driven/` (50+ files)
- Business events: `market_data_processor/bybit_business_events/`

---

### 1.1.6 審計持久化（Audit Persistence）

| # | 組件 | 檔案位置 | 數據描述 | 寫入頻率 | 讀取模式 | 原子寫入 |
|---|------|---------|---------|---------|---------|---------|
| 17 | **AuditPersistence** | `data/audit/audit_*.jsonl` | 不可變審計日誌：audit_id、source、record（JSONL 追加） | 每個治理事件 | 從不讀取（純寫入） | ✅ append + flush |

- 自動輪轉：按日期 + 50 MB + 500K records/file
- 線程安全，立即 flush
- **永久保留，從不刪除**

---

### 1.1.7 靜態配置（Static Configuration）

| # | 檔案 | 用途 |
|---|------|------|
| 18 | `settings/service_configs/bybit_connector_config.json` | 連接器配置：exchange name、environment、mode |
| 19 | `rust/schemas/shared_types.json` (4.3 KB) | Python/Rust IPC 共享類型 golden schema |
| 20 | `docker_projects/monitoring_services/dashboards/*.json` (5 files, ~39 KB) | Grafana 儀表盤定義 |

---

### 1.1.8 Runtime 合約文件（Runtime Contracts）

`runtime/bybit/` 下約 **4,500 個 JSON 文件**，總計 ~26 MB。按子系統組織：

```
runtime/bybit/
├── event_driven/          # 狀態機轉換合約
├── thought_gate/          # AI 成本日誌、決策閘門
├── business_events/       # 事件流驗證
├── demo_gate/             # Paper/demo 合約
├── local_judgment/        # 本地決策一致性
├── regression/            # 回歸測試合約
└── trigger_model/         # 觸發驗證合約
```

這些是 **測試/驗證產物**，非核心業務數據。每個包含 `*_latest.json` + dated snapshots。

---

## 1.2 PostgreSQL 配置

### 1.2.1 基礎設施（Infrastructure）

| 項目 | 值 |
|------|---|
| **Database** | `trading_ai` |
| **User** | `trading_admin` |
| **Port** | 5432 |
| **Host** | `127.0.0.1` (本地) / `trading_postgres` (Docker) |
| **Driver** | psycopg2-binary ≥ 2.9.0（try/except 可選導入） |
| **TimescaleDB** | ❌ 明確禁用（`timescaledb: false`） |

**Docker Compose:** `docker_projects/monitoring_services/docker-compose.yml` — Grafana + PostgreSQL，共用 `pg_net` 網絡。

**環境變量文件：** `settings/environment_files/basic_system_services.env`

### 1.2.2 現有 Schema（11 張表）

**定義文件：** `docker_projects/monitoring_services/init_trading_schema.sql` (204 lines)

| 表名 | 用途 | 索引 | 當前寫入方 |
|------|------|------|-----------|
| `account_snapshots` | 帳戶快照（equity、balance、margin、PnL） | ts | BybitDemoSync (60s) |
| `position_snapshots` | 持倉快照（symbol、side、size、entry/mark price） | ts, symbol | BybitDemoSync (60s) |
| `order_events` | 訂單事件（order lifecycle） | ts, symbol | 未接入（schema only） |
| `trade_executions` | 成交記錄（fills + PnL + strategy attribution） | ts, symbol | GrafanaDataWriter (30s 增量) |
| `ai_cost_events` | AI 調用成本（provider、model、tokens、cost） | ts | 未接入（schema only） |
| `system_health` | 系統健康狀態（component status + metrics） | ts | GrafanaDataWriter (30s) |
| `observer_verdicts` | Observer 決策裁定 | ts | 未接入（schema only） |
| `paper_pnl_snapshots` | Paper PnL 快照（realized/unrealized/fees/Sharpe） | ts | GrafanaDataWriter (30s) |
| `risk_events` | 風控事件（stop/circuit_breaker/kill_switch） | ts | 未接入（schema only） |
| `market_tickers` | 市場行情（last/bid/ask/volume/funding/OI） | ts, symbol | GrafanaDataWriter (30s) |
| `learning_events` | 學習事件（observations/hypotheses） | ts | 未接入（schema only） |

**額外 trading_raw schema 表（由獨立腳本寫入）：**

| 表名 | 用途 | 寫入方 |
|------|------|--------|
| `decision_packets` | 決策包原始數據 | `bybit_decision_packet_to_postgres.py` (手動腳本) |
| `observer_verdicts` (raw) | 裁定原始數據 | `bybit_observer_verdict_to_postgres.py` (手動腳本) |
| `bybit_account_coin_snapshots` | 帳戶幣種快照 | `bybit_normalize_latest_snapshot_to_postgres.py` |
| `bybit_position_snapshots` | 持倉快照（raw） | `bybit_normalize_latest_snapshot_to_postgres.py` |
| `bybit_ws_private_events_raw` | WS 私有事件原始記錄 | `bybit_load_ws_jsonl_to_postgres.py` |

### 1.2.3 寫入者

**自動寫入（daemon threads）：**

1. **GrafanaDataWriter** (`grafana_data_writer.py`) — 30s 循環
   - 寫入：paper_pnl_snapshots, market_tickers, system_health, trade_executions（增量）
   - 所有 paper 數據標記 `is_paper=true`
   - 連接失敗靜默降級

2. **BybitDemoSync** (`bybit_demo_sync.py`) — 60s 循環
   - 寫入：trade_executions, position_snapshots, account_snapshots
   - Demo 數據標記 `is_paper=false, is_demo=true`

**手動腳本（需人工執行）：**
- `bybit_decision_packet_to_postgres.py`
- `bybit_observer_verdict_to_postgres.py`
- `bybit_normalize_latest_snapshot_to_postgres.py`
- `bybit_load_ws_jsonl_to_postgres.py`

### 1.2.4 其他持久化服務

| 服務 | 端口 | 數據目錄 | 用途 |
|------|------|---------|------|
| **Redis** | 6379 | `database_files/redis_data/` | 緩存（代碼中未見 import） |
| **Qdrant** | 6333/6334 | `database_files/vector_database_data/` | 向量數據庫（新聞/AI 記憶） |

---

## 1.3 數據流全景圖

### 1.3.1 市場數據流（Market Data Flow）

```
Bybit Public WS (kline/ticker/orderbook)
       │
       ▼
BybitPublicWsListener → PriceEvent(symbol, price, ts_ms, volume, turnover)
       │
       ▼
MarketDataDispatcher (attention-based throttle: 60s/10s/3s/500ms/即時)
       │
       ├──────────────────────┐
       ▼                      ▼
KlineManager (記憶體環形緩衝)    StrategyOrchestrator
  DEFAULT_BUFFER = 500 bars      │
  多時間框架: 1m/5m/15m/         ▼
  30m/1h/4h/1d              Signal Generation
       │                    (記憶體 only)
       ▼
IndicatorEngine (記憶體 cache)
  16 指標: SMA/EMA/MACD/RSI/
  Stochastic/BB/ATR/KAMA/ADX/
  Hurst/EWMAVol/VolumeRatio/
  DonchianChannel
```

**⚠️ DATA LOSS RISK — 市場數據**：
- **原始價格 tick**：WS 接收後立即處理，**從不持久化**。系統崩潰 = 永久丟失。
- **K 線數據**：只在記憶體環形緩衝中（~500 bars），重啟 = 全部丟失。
- **指標值**：只在記憶體 cache 中，重啟 = 全部丟失。
- **無重放機制**：沒有從歷史 WS feed 或 REST 回填數據的實現。

**部分緩解**：GrafanaDataWriter 每 30s 寫入 `market_tickers` 表（僅 last_price，無 OHLCV/指標）。

### 1.3.2 交易/訂單流（Trade/Order Flow）

```
StrategyOrchestrator → OrderIntent
       │
       ▼
PipelineBridge.process_pending_intents()
       │
       ├─ H0Gate (<1ms 本地檢查)
       ├─ OllamaClient (L1 edge filter)
       ├─ GuardianAgent (風控審批)
       └─ ExecutorAgent (訂單提交)
              │
              ▼
PaperTradingEngine (7-state lifecycle)
  CREATED → SUBMITTED → WORKING → PARTIALLY_FILLED → FILLED
  (or CANCELED / REJECTED)
              │
              ├─ paper_trading_state.json (防抖快照)
              ├─ GrafanaDataWriter → trade_executions 表 (30s 增量)
              └─ TradeAttributionEngine → 歸因數據 (條件性)
```

**⚠️ DATA LOSS RISK — 交易數據**：
- PaperTradeStateStore 使用防抖寫入（1.0s 間隔）。崩潰時 up to 1s 的 fills/orders 可能丟失。
- 沒有獨立的 **實時交易日誌（WAL）**。只有狀態快照，不是事件溯源。
- GrafanaDataWriter 的增量寫入使用 `_last_fill_count` 追蹤，但這是內存計數器——重啟後可能重複寫入。

### 1.3.3 策略狀態流（Strategy State Flow）

```
5 Strategies (ma_crossover/bb_breakout/grid_trading/funding_rate_arb/...)
       │
       ▼
SignalEngine → signals (記憶體 only)
       │
       ▼
MarketRegimeTracker → MarketRegimeSnapshot
  (TRENDING_UP/DOWN, RANGING, SQUEEZE, HIGH_VOL, LOW_VOL, BREAKOUT, REVERSAL)
  (記憶體 only)
```

**⚠️ DATA LOSS RISK — 策略狀態**：
- **策略參數**：`strategy_state.json` 存在但為空，未使用。
- **信號歷史**：完全在記憶體中，從不持久化。
- **市場 regime 狀態**：完全在記憶體中，重啟後丟失全部上下文。

### 1.3.4 風控數據流（Risk Data Flow）

```
GuardianAgent → risk review per TradeIntent
  5 checks: direction conflict / leverage cap /
  correlation / Sharpe threshold / drawdown limit
       │
       ▼
GovernanceHub (4 State Machines)
  SM-01 Authorization (restricted/frozen/normal)
  SM-04 RiskGovernor (NORMAL → REDUCED → CIRCUIT_BREAKER)
  SM-02 Decision Lease (grant/revoke)
  EX-04 Reconciliation
       │
       ├─ 記憶體：_verdict_log (max 200 records, 溢出丟棄)
       ├─ 記憶體：P0/P1/P2 runtime levels (重啟丟失)
       ├─ JSON：operator_risk_config.json (P1 配置定義)
       └─ JSONL：data/audit/audit_*.jsonl (不可變審計日誌)
```

### 1.3.5 學習數據流（Learning Data Flow）

```
Trade Observations (per round-trip close)
       │
       ▼
ExperimentLedger (Hypothesis lifecycle)
  PENDING → RUNNING → CONFIRMED/REFUTED/EXPIRED
  Auto-conclude: 65% threshold + min 20 observations
       │
       ├─ CONFIRMED → TruthSourceRegistry (auto-inject as PatternClaim)
       └─ REFUTED → 不注入 (認知誠實原則)
       
EvolutionEngine (grid search, isolated backtest)
       │
       └─ EvolutionResult → 可選注入 TruthSourceRegistry
```

**⚠️ DATA LOSS RISK — 學習數據**：
- ExperimentLedger 防抖 60s，崩潰可丟失 up to 60s 的 hypothesis observations。
- EvolutionEngine 中間結果完全不持久化，崩潰 = 全部計算丟失。

### 1.3.6 MessageBus（Agent 間通信）

```
Scout ──INTEL_OBJECT──► Strategist
Scout ──EVENT_ALERT───► Guardian
Strategist ─TRADE_INTENT──► Guardian
Guardian ──RISK_VERDICT──► Strategist → Executor
Executor ──EXECUTION_REPORT──► Analyst
Analyst ──PATTERN_INSIGHT──► Strategist
Analyst ──RISK_PATTERN──► Guardian
Conductor ──SYSTEM_DIRECTIVE──► All
```

- **完全記憶體**：無消息隊列、無持久化、無重放。
- 消息同步處理，崩潰 = in-flight 消息丟失。

---

## 1.4 數據量估算

### 假設

- 50 個交易對 (symbols)
- 活躍交易對 ~25 個（被 MarketDataDispatcher attention filter 篩選）
- Paper trading 階段（低交易頻率）
- WebSocket tick 頻率：~2-5 ticks/symbol/second（活躍市場）

### 每日數據量

| 數據類型 | 計算方式 | 每日估算 | 格式 |
|---------|---------|---------|------|
| **原始 tick（如果持久化）** | 25 sym × 3 ticks/s × 86,400s × 100 bytes | ~650 MB | JSONL |
| **1m K 線** | 50 sym × 1,440 bars × 200 bytes | ~14 MB | 結構化行 |
| **5m/15m/1h/4h/1d K 線** | 50 sym × (288+96+24+6+1) bars × 200 bytes | ~4 MB | 結構化行 |
| **指標值（16 指標 × 7 timeframe）** | 50 × 112 × 1,440 intervals × 50 bytes | ~400 MB | 結構化行 |
| **市場 ticker（30s 採樣）** | 50 sym × 2,880 samples × 150 bytes | ~22 MB | PG 行 |
| **Paper 交易記錄** | ~10-50 trades/day × 500 bytes | ~25 KB | PG 行 |
| **風控事件** | ~100-500 events/day × 300 bytes | ~150 KB | PG 行 |
| **AI 成本事件** | ~50-200 calls/day × 200 bytes | ~40 KB | PG 行 |
| **Agent 消息（如果持久化）** | ~1,000-5,000 msgs/day × 500 bytes | ~2.5 MB | JSONL |
| **審計日誌** | ~500-2,000 events/day × 300 bytes | ~600 KB | JSONL |
| **學習事件** | ~10-100 observations/day × 500 bytes | ~50 KB | PG 行 |

### 累計預估

| 時段 | 核心數據（不含 raw tick） | 含 raw tick | 含指標 |
|------|------------------------|------------|--------|
| **1 個月** | ~1.2 GB | ~21 GB | ~13 GB |
| **3 個月** | ~3.6 GB | ~63 GB | ~39 GB |
| **1 年** | ~14.4 GB | ~250 GB | ~160 GB |

> 128 GB RAM 的機器完全可以承載。TimescaleDB 壓縮 + Parquet 歸檔可將長期存儲降低 5-10x。

---

# Phase 2: 數據分類

## 分類矩陣

| 類別 | ID | 數據存儲點 | 當前存儲 | 當前風險 |
|------|---|-----------|---------|---------|
| **T (Time-Series)** | T-1 | 原始 price ticks | ❌ 無（記憶體丟棄） | ⚠️ DATA LOSS |
| | T-2 | K 線 OHLCV（多時間框架） | ❌ 記憶體環形緩衝 | ⚠️ DATA LOSS |
| | T-3 | 技術指標值（16 指標 × 7 TF） | ❌ 記憶體 cache | ⚠️ DATA LOSS |
| | T-4 | 市場 regime 狀態歷史 | ❌ 記憶體 | ⚠️ DATA LOSS |
| | T-5 | market_tickers（30s 快照） | ✅ PostgreSQL | OK（但只有 last_price） |
| | T-6 | system_health（30s 快照） | ✅ PostgreSQL | OK |
| | T-7 | AI cost events | ✅ JSON (Layer2CostTracker) | ⚠️ 部分（非完整事件） |
| | T-8 | WS 私有事件 | ✅ JSONL (append) | OK |
| **B (Business)** | B-1 | Paper orders（完整生命週期） | ✅ JSON (state snapshot) | ⚠️ 非事件溯源 |
| | B-2 | Paper fills（成交記錄） | ✅ JSON + PostgreSQL | OK（雙寫） |
| | B-3 | Positions（持倉） | ✅ JSON (state snapshot) | ⚠️ 非事件溯源 |
| | B-4 | PnL snapshots | ✅ PostgreSQL (30s) | OK |
| | B-5 | Decision packets | ✅ JSON（latest + dated） | OK |
| | B-6 | Observer verdicts | ✅ JSON（latest + dated） | OK |
| | B-7 | Audit trail | ✅ JSONL（不可變追加） | ✅ 最佳 |
| | B-8 | Account snapshots | ✅ PostgreSQL (60s) | OK |
| | B-9 | Guardian verdicts（詳細） | ❌ 記憶體（max 200） | ⚠️ DATA LOSS |
| **S (State)** | S-1 | 控制狀態機（JsonStateStore） | ✅ JSON (253 KB) | OK |
| | S-2 | Paper trading session 狀態 | ✅ JSON (233 KB, 防抖) | ⚠️ 1s 窗口丟失 |
| | S-3 | API budget 狀態 | ✅ JSON (~2 KB) | OK |
| | S-4 | GovernanceHub SM 狀態 | ❌ 記憶體 | ⚠️ 重啟重置 |
| | S-5 | Agent attention levels | ❌ 記憶體 | 低風險（可重算） |
| | S-6 | KlineManager buffer pointers | ❌ 記憶體 | ⚠️ 重啟丟失歷史 |
| **C (Config)** | C-1 | operator_risk_config.json | ✅ JSON (3.1 KB) | OK |
| | C-2 | bybit_connector_config.json | ✅ JSON | OK |
| | C-3 | shared_types.json (IPC schema) | ✅ JSON | OK |
| | C-4 | Grafana dashboards | ✅ JSON | OK |
| | C-5 | 環境變量 (.env files) | ✅ env files | OK |
| **L (Learning)** | L-1 | TruthSourceRegistry (PatternClaims) | ✅ JSON (~1 KB) | ⚠️ RACE CONDITION |
| | L-2 | ExperimentLedger (Hypotheses) | ✅ JSON (13 KB) | ⚠️ 60s 窗口丟失 |
| | L-3 | EvolutionEngine 結果 | ❌ 記憶體 | ⚠️ DATA LOSS |
| | L-4 | 信號歷史（策略回測素材） | ❌ 記憶體 | ⚠️ DATA LOSS |
| | L-5 | Regime 轉換歷史（模型訓練素材） | ❌ 記憶體 | ⚠️ DATA LOSS |
| | L-6 | Trade observations（歸因） | ❌/部分 | ⚠️ 條件性 |

### 風險等級匯總

```
🔴 HIGH (完全丟失，不可恢復):
   T-1  原始 price ticks — 從未持久化
   T-2  K 線歷史 — 記憶體環形緩衝
   T-3  指標值歷史 — 記憶體 cache
   T-4  Regime 狀態歷史 — 記憶體
   L-4  信號歷史 — 記憶體
   L-5  Regime 轉換歷史 — 記憶體

🟡 MEDIUM (部分丟失或有窗口):
   B-1  Paper orders — 快照非事件溯源
   B-9  Guardian verdicts — max 200 溢出丟棄
   S-2  Paper session — 1s 防抖窗口
   S-4  Governance SM — 重啟重置
   L-1  PatternClaims — 競態風險
   L-2  Hypotheses — 60s 窗口
   L-3  Evolution 結果 — 未持久化

🟢 LOW (已有合理持久化):
   T-5/T-6/T-8, B-2~B-8, S-1/S-3, C-1~C-5
```

---

# Phase 3: 架構方案設計

## 3.1 數據架構總覽圖

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        OpenClaw 數據架構 V1                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐    ┌───────────────────────────────────────────────┐  │
│  │  Bybit WS/   │    │       PostgreSQL + TimescaleDB               │  │
│  │  REST API    │    │  ┌─────────────────────────────────────────┐  │  │
│  │              │───►│  │ T (Time-Series)  [hypertables]         │  │  │
│  │  tick/kline/ │    │  │  raw_ticks          7d retain → Parquet│  │  │
│  │  ticker/OB   │    │  │  klines_1m          ∞ retain           │  │  │
│  └──────────────┘    │  │  klines_agg         auto from 1m       │  │  │
│                      │  │  indicator_values   90d retain          │  │  │
│  ┌──────────────┐    │  │  market_tickers     30d retain          │  │  │
│  │  5 Agents    │    │  │  market_regimes     ∞ retain           │  │  │
│  │              │    │  └─────────────────────────────────────────┘  │  │
│  │ Scout        │    │  ┌─────────────────────────────────────────┐  │  │
│  │ Strategist   │───►│  │ B (Business/Transactional)  [regular]  │  │  │
│  │ Guardian     │    │  │  orders             ∞ retain           │  │  │
│  │ Analyst      │    │  │  fills / executions ∞ retain           │  │  │
│  │ Executor     │    │  │  positions          ∞ retain           │  │  │
│  └──────────────┘    │  │  pnl_snapshots      ∞ retain           │  │  │
│                      │  │  risk_events        ∞ retain           │  │  │
│  ┌──────────────┐    │  │  agent_messages     90d retain         │  │  │
│  │ Governance   │    │  │  guardian_verdicts   ∞ retain           │  │  │
│  │ Hub          │───►│  │  audit_events       ∞ retain           │  │  │
│  │              │    │  └─────────────────────────────────────────┘  │  │
│  └──────────────┘    │  ┌─────────────────────────────────────────┐  │  │
│                      │  │ L (Learning)  [regular]                 │  │  │
│  ┌──────────────┐    │  │  pattern_claims      ∞ retain          │  │  │
│  │ Learning     │───►│  │  hypotheses          ∞ retain          │  │  │
│  │ Pipeline     │    │  │  evolution_results   ∞ retain          │  │  │
│  │              │    │  │  trade_observations  ∞ retain          │  │  │
│  └──────────────┘    │  │  signal_log          90d retain        │  │  │
│                      │  └─────────────────────────────────────────┘  │  │
│                      └──────────────┬────────────────────────────────┘  │
│                                     │                                   │
│                           ┌─────────▼─────────┐                        │
│  ┌──────────────┐         │  ETL / Export      │                        │
│  │  C (Config)  │         │  (定時 cron job)    │                        │
│  │              │         └─────────┬─────────┘                        │
│  │ JSON files   │                   │                                   │
│  │ (human-      │         ┌─────────▼─────────┐                        │
│  │  editable)   │         │  Parquet Files     │                        │
│  │              │         │  (ML-Ready)        │                        │
│  │ risk_config  │         │                    │         ┌────────────┐ │
│  │ connector_   │         │  market/klines/    │────────►│  DuckDB    │ │
│  │   config     │         │  market/ticks/     │         │  (feature  │ │
│  │ env files    │         │  features/         │────────►│   engine)  │ │
│  │ IPC schema   │         │  labels/           │         │            │ │
│  └──────────────┘         │  trades/           │────────►│  → PyTorch │ │
│                           └────────────────────┘         │  DataLoader│ │
│  ┌──────────────┐                                        └────────────┘ │
│  │  S (State)   │                                                       │
│  │              │    ┌────────────────────────────────────────────────┐  │
│  │  In-Memory   │◄──►│  Redis (optional, future)                    │  │
│  │  + JSON      │    │  Real-time state sharing if multi-process    │  │
│  │  fallback    │    └────────────────────────────────────────────────┘  │
│  └──────────────┘                                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

### Agent × 數據層交互矩陣

| Agent | T (Time-Series) | B (Business) | S (State) | C (Config) | L (Learning) |
|-------|:---:|:---:|:---:|:---:|:---:|
| **Scout** | 讀 tick/kline/indicator | — | 讀/寫 attention | 讀 connector | — |
| **Strategist** | 讀 kline/indicator/regime | 寫 OrderIntent | 讀 positions | 讀 strategy params | 讀 claims/hypotheses |
| **Guardian** | 讀 regime/volatility | 讀 orders/positions | 讀/寫 SM-04 | 讀 risk_config | 讀 risk patterns |
| **Analyst** | 讀 kline/indicator | 讀 fills/PnL | — | — | 寫 observations/claims |
| **Executor** | — | 讀/寫 orders/fills | 讀 lease | — | — |
| **GrafanaWriter** | 寫 tickers/health | 寫 PnL/fills | — | — | — |

---

## 3.2 PostgreSQL + TimescaleDB Schema

### 3.2.1 安裝 TimescaleDB

```bash
# Ubuntu — TimescaleDB 是 PG 擴展，不需要額外服務
sudo apt install timescaledb-2-postgresql-16
sudo timescaledb-tune --yes  # 自動調優 PG 配置

# 在 trading_ai 數據庫中啟用
psql -U trading_admin -d trading_ai -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"
```

更新 Grafana datasource 配置：`timescaledb: true`

### 3.2.2 T 類表（Time-Series — Hypertables）

```sql
-- =====================================================================
-- T-1: 原始 Price Ticks (⚠️ 當前完全丟失，P0 緊急)
-- Raw price ticks from WebSocket — currently lost on every restart
-- 預估: 50 sym × ~3 ticks/s × 86400s = ~13M rows/day, ~650 MB/day
-- =====================================================================
CREATE TABLE IF NOT EXISTS raw_ticks (
    ts          TIMESTAMPTZ NOT NULL,
    symbol      TEXT        NOT NULL,
    price       NUMERIC(20,8) NOT NULL,
    volume      NUMERIC(30,8),
    turnover    NUMERIC(30,8),
    source      TEXT DEFAULT 'ws'  -- ws/rest
);
SELECT create_hypertable('raw_ticks', 'ts',
    chunk_time_interval => INTERVAL '1 hour');
CREATE INDEX idx_raw_ticks_symbol ON raw_ticks (symbol, ts DESC);

-- 壓縮策略: 7天後壓縮 (降 ~10x 存儲)
ALTER TABLE raw_ticks SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol',
    timescaledb.compress_orderby = 'ts DESC'
);
SELECT add_compression_policy('raw_ticks', INTERVAL '7 days');

-- 保留策略: 30天後刪除 (歸檔到 Parquet)
SELECT add_retention_policy('raw_ticks', INTERVAL '30 days');

-- =====================================================================
-- T-2: K 線 OHLCV (⚠️ 當前完全丟失，P0 緊急)
-- 1-minute klines — base timeframe, others derived via continuous aggregates
-- 預估: 50 sym × 1440 bars/day = 72K rows/day, ~14 MB/day
-- =====================================================================
CREATE TABLE IF NOT EXISTS klines_1m (
    ts          TIMESTAMPTZ NOT NULL,   -- bar open time
    close_ts    TIMESTAMPTZ NOT NULL,   -- bar close time
    symbol      TEXT        NOT NULL,
    open        NUMERIC(20,8) NOT NULL,
    high        NUMERIC(20,8) NOT NULL,
    low         NUMERIC(20,8) NOT NULL,
    close       NUMERIC(20,8) NOT NULL,
    volume      NUMERIC(30,8) NOT NULL,
    turnover    NUMERIC(30,8),
    tick_count  INTEGER DEFAULT 0
);
SELECT create_hypertable('klines_1m', 'ts',
    chunk_time_interval => INTERVAL '1 day');
CREATE UNIQUE INDEX idx_klines_1m_sym_ts ON klines_1m (symbol, ts);

ALTER TABLE klines_1m SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol',
    timescaledb.compress_orderby = 'ts DESC'
);
SELECT add_compression_policy('klines_1m', INTERVAL '30 days');
-- 不設 retention — 1m klines 永久保留 (年增 ~5 GB, 壓縮後 ~0.5 GB)

-- =====================================================================
-- T-2a: 連續聚合 — 自動 5m/15m/1h/4h/1d 從 1m 衍生
-- Continuous Aggregates — automatically derived from klines_1m
-- =====================================================================
CREATE MATERIALIZED VIEW klines_5m
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('5 minutes', ts)    AS ts,
    symbol,
    first(open, ts)                 AS open,
    max(high)                       AS high,
    min(low)                        AS low,
    last(close, ts)                 AS close,
    sum(volume)                     AS volume,
    sum(turnover)                   AS turnover,
    sum(tick_count)                 AS tick_count
FROM klines_1m
GROUP BY time_bucket('5 minutes', ts), symbol
WITH NO DATA;
SELECT add_continuous_aggregate_policy('klines_5m',
    start_offset    => INTERVAL '1 hour',
    end_offset      => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes');

CREATE MATERIALIZED VIEW klines_15m
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('15 minutes', ts)   AS ts,
    symbol,
    first(open, ts) AS open, max(high) AS high,
    min(low) AS low, last(close, ts) AS close,
    sum(volume) AS volume, sum(turnover) AS turnover,
    sum(tick_count) AS tick_count
FROM klines_1m
GROUP BY time_bucket('15 minutes', ts), symbol
WITH NO DATA;
SELECT add_continuous_aggregate_policy('klines_15m',
    start_offset => INTERVAL '2 hours', end_offset => INTERVAL '15 minutes',
    schedule_interval => INTERVAL '15 minutes');

CREATE MATERIALIZED VIEW klines_1h
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', ts)       AS ts,
    symbol,
    first(open, ts) AS open, max(high) AS high,
    min(low) AS low, last(close, ts) AS close,
    sum(volume) AS volume, sum(turnover) AS turnover,
    sum(tick_count) AS tick_count
FROM klines_1m
GROUP BY time_bucket('1 hour', ts), symbol
WITH NO DATA;
SELECT add_continuous_aggregate_policy('klines_1h',
    start_offset => INTERVAL '4 hours', end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');

CREATE MATERIALIZED VIEW klines_4h
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('4 hours', ts)      AS ts,
    symbol,
    first(open, ts) AS open, max(high) AS high,
    min(low) AS low, last(close, ts) AS close,
    sum(volume) AS volume, sum(turnover) AS turnover,
    sum(tick_count) AS tick_count
FROM klines_1m
GROUP BY time_bucket('4 hours', ts), symbol
WITH NO DATA;
SELECT add_continuous_aggregate_policy('klines_4h',
    start_offset => INTERVAL '12 hours', end_offset => INTERVAL '4 hours',
    schedule_interval => INTERVAL '4 hours');

CREATE MATERIALIZED VIEW klines_1d
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', ts)        AS ts,
    symbol,
    first(open, ts) AS open, max(high) AS high,
    min(low) AS low, last(close, ts) AS close,
    sum(volume) AS volume, sum(turnover) AS turnover,
    sum(tick_count) AS tick_count
FROM klines_1m
GROUP BY time_bucket('1 day', ts), symbol
WITH NO DATA;
SELECT add_continuous_aggregate_policy('klines_1d',
    start_offset => INTERVAL '3 days', end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day');

-- =====================================================================
-- T-3: 指標值 (⚠️ 當前完全丟失)
-- Technical indicator values computed per kline close
-- 預估: 50 sym × 7 TF × 16 indicators × 1440/TF ≈ ~200K rows/day
-- =====================================================================
CREATE TABLE IF NOT EXISTS indicator_values (
    ts          TIMESTAMPTZ NOT NULL,
    symbol      TEXT        NOT NULL,
    timeframe   TEXT        NOT NULL,   -- 1m/5m/15m/1h/4h/1d
    indicator   TEXT        NOT NULL,   -- sma_20/rsi_14/macd_signal/...
    value       NUMERIC(30,12),
    extra       JSONB                   -- 多值指標的附加字段 (e.g. BB upper/lower)
);
SELECT create_hypertable('indicator_values', 'ts',
    chunk_time_interval => INTERVAL '1 day');
CREATE INDEX idx_indicator_sym_tf ON indicator_values (symbol, timeframe, indicator, ts DESC);

ALTER TABLE indicator_values SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol,timeframe,indicator',
    timescaledb.compress_orderby = 'ts DESC'
);
SELECT add_compression_policy('indicator_values', INTERVAL '7 days');
SELECT add_retention_policy('indicator_values', INTERVAL '90 days');
-- 90天前數據 → Parquet 歸檔

-- =====================================================================
-- T-4: 市場 Regime 狀態 (⚠️ 當前完全丟失)
-- Market regime transitions — invaluable for ML regime detection models
-- 預估: 50 sym × 7 TF × ~10 transitions/day ≈ 3.5K rows/day
-- =====================================================================
CREATE TABLE IF NOT EXISTS market_regimes (
    ts              TIMESTAMPTZ NOT NULL,
    symbol          TEXT        NOT NULL,
    timeframe       TEXT        NOT NULL,
    regime          TEXT        NOT NULL,   -- TRENDING_UP/DOWN/RANGING/SQUEEZE/etc.
    prev_regime     TEXT,
    confidence      NUMERIC(5,4),
    volatility_pct  NUMERIC(10,4),
    atr_value       NUMERIC(20,8),
    supporting_data JSONB                  -- 支撐指標數據
);
SELECT create_hypertable('market_regimes', 'ts',
    chunk_time_interval => INTERVAL '7 days');
CREATE INDEX idx_regimes_sym_tf ON market_regimes (symbol, timeframe, ts DESC);

-- =====================================================================
-- T-5: market_tickers (已有，升級為 hypertable)
-- =====================================================================
-- 保留現有 market_tickers 表結構，轉為 hypertable:
-- SELECT create_hypertable('market_tickers', 'ts',
--     chunk_time_interval => INTERVAL '1 day',
--     migrate_data => true);
-- ALTER TABLE market_tickers SET (
--     timescaledb.compress,
--     timescaledb.compress_segmentby = 'symbol',
--     timescaledb.compress_orderby = 'ts DESC');
-- SELECT add_compression_policy('market_tickers', INTERVAL '7 days');
-- SELECT add_retention_policy('market_tickers', INTERVAL '30 days');

-- =====================================================================
-- T-7: AI 成本事件 (升級現有 ai_cost_events)
-- =====================================================================
-- 保留現有結構，轉為 hypertable:
-- SELECT create_hypertable('ai_cost_events', 'ts',
--     chunk_time_interval => INTERVAL '7 days',
--     migrate_data => true);

-- =====================================================================
-- T-9: 信號日誌 (⚠️ 當前完全丟失，ML 關鍵素材)
-- Signal generation log — critical for strategy backtesting & ML labels
-- 預估: 50 sym × ~100 signals/day = 5K rows/day
-- =====================================================================
CREATE TABLE IF NOT EXISTS signal_log (
    ts          TIMESTAMPTZ NOT NULL,
    symbol      TEXT        NOT NULL,
    timeframe   TEXT        NOT NULL,
    strategy    TEXT        NOT NULL,
    signal_type TEXT        NOT NULL,   -- BUY/SELL/HOLD/EXIT
    strength    NUMERIC(5,4),           -- 信號強度 0-1
    price       NUMERIC(20,8),
    indicators  JSONB,                  -- 觸發信號的指標值快照
    regime      TEXT,                   -- 當時的 market regime
    metadata    JSONB
);
SELECT create_hypertable('signal_log', 'ts',
    chunk_time_interval => INTERVAL '7 days');
CREATE INDEX idx_signal_sym_strat ON signal_log (symbol, strategy, ts DESC);

ALTER TABLE signal_log SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol,strategy',
    timescaledb.compress_orderby = 'ts DESC'
);
SELECT add_compression_policy('signal_log', INTERVAL '14 days');
SELECT add_retention_policy('signal_log', INTERVAL '90 days');
```

### 3.2.3 B 類表（Business/Transactional — Regular Tables）

```sql
-- =====================================================================
-- B-9: Guardian Verdicts (⚠️ 當前 max 200 溢出丟棄)
-- Full risk review verdicts — not just the last 200
-- =====================================================================
CREATE TABLE IF NOT EXISTS guardian_verdicts (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    trade_intent_id TEXT,
    symbol          TEXT NOT NULL,
    side            TEXT,
    verdict         TEXT NOT NULL,       -- APPROVED/REJECTED/MODIFIED
    checks_passed   TEXT[],              -- which checks passed
    checks_failed   TEXT[],              -- which checks failed
    modifications   JSONB,               -- what was modified (if MODIFIED)
    risk_snapshot   JSONB,               -- current risk state at time of verdict
    detail          TEXT
);
CREATE INDEX idx_guardian_ts ON guardian_verdicts (ts);
CREATE INDEX idx_guardian_symbol ON guardian_verdicts (symbol);

-- =====================================================================
-- B-10: Agent 消息日誌 (⚠️ 當前完全記憶體)
-- Inter-agent message log for debugging & ML conversation analysis
-- =====================================================================
CREATE TABLE IF NOT EXISTS agent_messages (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    message_id      TEXT NOT NULL,
    sender          TEXT NOT NULL,       -- scout/strategist/guardian/analyst/executor/conductor
    receiver        TEXT NOT NULL,
    message_type    TEXT NOT NULL,       -- INTEL_OBJECT/TRADE_INTENT/RISK_VERDICT/etc.
    priority        TEXT DEFAULT 'normal',
    data_quality    TEXT,                -- FACT/INFERENCE/HYPOTHESIS
    payload         JSONB NOT NULL,
    processing_ms   INTEGER
);
CREATE INDEX idx_agent_msg_ts ON agent_messages (ts);
CREATE INDEX idx_agent_msg_type ON agent_messages (message_type);

-- =====================================================================
-- B-11: 審計事件 (從 JSONL 升級到 PG)
-- Immutable audit events — currently append-only JSONL files
-- =====================================================================
CREATE TABLE IF NOT EXISTS audit_events (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    audit_id        TEXT NOT NULL UNIQUE,
    source          TEXT NOT NULL,       -- governance/risk/auth/lease/oms
    event_type      TEXT NOT NULL,
    detail          JSONB NOT NULL,
    severity        TEXT DEFAULT 'info'
);
CREATE INDEX idx_audit_ts ON audit_events (ts);
CREATE INDEX idx_audit_source ON audit_events (source);

-- 現有表保持不變: order_events, trade_executions, position_snapshots,
-- account_snapshots, paper_pnl_snapshots, risk_events, observer_verdicts
```

### 3.2.4 L 類表（Learning）

```sql
-- =====================================================================
-- L-1/L-2: Pattern Claims & Hypotheses (從 JSON 升級)
-- =====================================================================
CREATE TABLE IF NOT EXISTS pattern_claims (
    id              BIGSERIAL PRIMARY KEY,
    claim_id        TEXT NOT NULL UNIQUE,
    pattern_text    TEXT NOT NULL,
    cognitive_level TEXT NOT NULL,        -- FACT/INFERENCE/HYPOTHESIS
    evidence_source TEXT,                 -- statistical_N=XX / ai / manual
    confidence      NUMERIC(5,4) NOT NULL,
    confidence_cap  NUMERIC(5,4),
    applies_to_regime   TEXT,             -- trending/ranging/volatile/all
    applies_to_strategy TEXT,             -- strategy_name / all
    observation_count   INTEGER DEFAULT 0,
    falsification_count INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ,
    superseded_by   TEXT,                 -- claim_id of replacement
    is_active       BOOLEAN DEFAULT TRUE,
    metadata        JSONB
);
CREATE INDEX idx_claims_active ON pattern_claims (is_active, cognitive_level);
CREATE INDEX idx_claims_strategy ON pattern_claims (applies_to_strategy);

CREATE TABLE IF NOT EXISTS hypotheses (
    id              BIGSERIAL PRIMARY KEY,
    hypothesis_id   TEXT NOT NULL UNIQUE,
    description     TEXT NOT NULL,
    strategy_name   TEXT,
    regime          TEXT,
    proposed_by     TEXT,                 -- agent name
    proposed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING/RUNNING/CONFIRMED/REFUTED/EXPIRED
    supporting_count    INTEGER DEFAULT 0,
    refuting_count      INTEGER DEFAULT 0,
    observation_count   INTEGER DEFAULT 0,
    min_observations    INTEGER DEFAULT 20,
    conclusion_threshold NUMERIC(3,2) DEFAULT 0.65,
    concluded_at    TIMESTAMPTZ,
    claim_id        TEXT REFERENCES pattern_claims(claim_id),
    metadata        JSONB
);
CREATE INDEX idx_hypotheses_status ON hypotheses (status);
CREATE INDEX idx_hypotheses_strategy ON hypotheses (strategy_name);

-- =====================================================================
-- L-3: Evolution Results
-- =====================================================================
CREATE TABLE IF NOT EXISTS evolution_results (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    strategy_name   TEXT NOT NULL,
    symbol          TEXT,
    timeframe       TEXT,
    best_params     JSONB NOT NULL,
    best_sharpe     NUMERIC(10,4),
    best_win_rate   NUMERIC(5,4),
    all_results     JSONB,               -- sorted by sharpe desc
    backtest_config JSONB,
    is_simulated    BOOLEAN DEFAULT TRUE,
    claim_id        TEXT                  -- if registered as claim
);
CREATE INDEX idx_evolution_strategy ON evolution_results (strategy_name, ts DESC);

-- =====================================================================
-- L-6: Trade Observations (歸因 + 學習素材)
-- =====================================================================
CREATE TABLE IF NOT EXISTS trade_observations (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol          TEXT NOT NULL,
    strategy_name   TEXT NOT NULL,
    signal_type     TEXT,                 -- entry signal type
    entry_price     NUMERIC(20,8),
    exit_price      NUMERIC(20,8),
    hold_ms         BIGINT,              -- hold duration
    realized_pnl    NUMERIC(20,8),
    regime_at_entry TEXT,
    regime_at_exit  TEXT,
    indicators_at_entry JSONB,
    indicators_at_exit  JSONB,
    hypothesis_id   TEXT,
    metadata        JSONB
);
CREATE INDEX idx_obs_strategy ON trade_observations (strategy_name, ts DESC);
CREATE INDEX idx_obs_symbol ON trade_observations (symbol, ts DESC);
```

### 3.2.5 年增長量預估

| 表 | 每日行數 | 每日大小 | 年增長 (原始) | 年增長 (壓縮後) |
|---|---------|---------|-------------|---------------|
| raw_ticks | ~13M | ~650 MB | ~237 GB | ~24 GB (保留 30d → Parquet) |
| klines_1m | ~72K | ~14 MB | ~5 GB | ~0.5 GB |
| klines_5m/15m/1h/4h/1d | ~21K | ~4 MB | ~1.5 GB | ~150 MB |
| indicator_values | ~200K | ~40 MB | ~14.6 GB | ~1.5 GB (保留 90d → Parquet) |
| market_regimes | ~3.5K | ~1 MB | ~365 MB | ~37 MB |
| signal_log | ~5K | ~2 MB | ~730 MB | ~73 MB (保留 90d → Parquet) |
| market_tickers | ~144K | ~22 MB | ~8 GB | ~0.8 GB (保留 30d) |
| trade_executions | ~50 | ~25 KB | ~9 MB | ~9 MB |
| guardian_verdicts | ~500 | ~250 KB | ~91 MB | ~91 MB |
| agent_messages | ~5K | ~2.5 MB | ~912 MB | ~912 MB (保留 90d) |
| **Total in PG** | | | | **~28 GB/year** |
| **Parquet archive** | | | | **~20 GB/year** |

> 128 GB RAM 系統完全可承載。第一年 PG 活躍數據 <30 GB，Parquet 歸檔 ~20 GB。

---

## 3.3 ML/DL 數據管線設計

### 3.3.1 架構概覽

```
┌──────────────────────────────────────────────────────────────┐
│                     ML/DL Data Pipeline                      │
│                                                              │
│  PostgreSQL (TimescaleDB)                                    │
│  ┌────────────────────┐                                      │
│  │ raw_ticks          │──┐                                   │
│  │ klines_1m/5m/1h... │──┤                                   │
│  │ indicator_values   │──┤    ETL (nightly cron)             │
│  │ market_regimes     │──┼──────────────────┐                │
│  │ signal_log         │──┤                  ▼                │
│  │ trade_observations │──┤    ┌─────────────────────┐        │
│  │ fills/orders       │──┘    │  Parquet Files       │        │
│  └────────────────────┘       │  (partitioned by     │        │
│                               │   date + symbol)     │        │
│                               │                      │        │
│                               │  data/parquet/       │        │
│                               │  ├─ market/          │        │
│                               │  │  ├─ klines/       │        │
│                               │  │  ├─ ticks/        │        │
│                               │  │  └─ regimes/      │        │
│                               │  ├─ features/        │        │
│                               │  │  ├─ v1/           │        │
│                               │  │  └─ v2/           │        │
│                               │  ├─ labels/          │        │
│                               │  │  ├─ direction/    │        │
│                               │  │  ├─ volatility/   │        │
│                               │  │  └─ regime/       │        │
│                               │  └─ trades/          │        │
│                               └──────────┬───────────┘        │
│                                          │                    │
│                               ┌──────────▼───────────┐        │
│                               │  DuckDB              │        │
│                               │  (Feature Engine)    │        │
│                               │                      │        │
│                               │  - Read Parquet      │        │
│                               │  - Window functions  │        │
│                               │  - Feature compute   │        │
│                               │  - Label generation  │        │
│                               │  - Train/val/test    │        │
│                               │    split (temporal)  │        │
│                               └──────────┬───────────┘        │
│                                          │                    │
│                               ┌──────────▼───────────┐        │
│                               │  PyTorch DataLoader  │        │
│                               │                      │        │
│                               │  ParquetDataset      │        │
│                               │  - mmap Parquet      │        │
│                               │  - sliding window    │        │
│                               │  - on-the-fly norm   │        │
│                               └──────────────────────┘        │
└──────────────────────────────────────────────────────────────┘
```

### 3.3.2 Feature Store 設計

```
Feature Store 概念設計
=====================

目標：將原始市場數據轉換為 ML 可消費的特徵矩陣。

1. 特徵類別:
   ┌────────────────┬──────────────────────────────────────────────┐
   │ Category       │ Features                                     │
   ├────────────────┼──────────────────────────────────────────────┤
   │ Price Features │ returns_1m/5m/1h, log_returns, VWAP,        │
   │                │ price_vs_sma20/50, price_vs_bb_upper/lower  │
   ├────────────────┼──────────────────────────────────────────────┤
   │ Momentum       │ RSI(14), MACD(12,26,9), Stochastic(14),    │
   │                │ ADX(14), KAMA(10), rate_of_change            │
   ├────────────────┼──────────────────────────────────────────────┤
   │ Volatility     │ ATR(5,14), BB_width, EWMAVol,               │
   │                │ realized_vol_1h/4h, Hurst exponent          │
   ├────────────────┼──────────────────────────────────────────────┤
   │ Volume         │ volume_ratio, OBV, volume_momentum,         │
   │                │ dollar_volume, VWAP_deviation                │
   ├────────────────┼──────────────────────────────────────────────┤
   │ Market Micro   │ bid_ask_spread, funding_rate,               │
   │                │ open_interest_change, liquidation_level      │
   ├────────────────┼──────────────────────────────────────────────┤
   │ Regime         │ regime_onehot, regime_duration_bars,         │
   │                │ regime_transition_prob                       │
   ├────────────────┼──────────────────────────────────────────────┤
   │ Cross-Symbol   │ BTC_correlation_rolling, sector_momentum,   │
   │                │ relative_strength_vs_BTC                    │
   └────────────────┴──────────────────────────────────────────────┘

2. 版本化:
   每次特徵定義變更 → 新版本目錄 (v1, v2, ...)
   版本 manifest: data/parquet/features/vN/manifest.json
   {
     "version": "v1",
     "created_at": "2026-04-03T...",
     "feature_count": 42,
     "features": ["returns_1m", "rsi_14", ...],
     "source_tables": ["klines_1m", "indicator_values", "market_regimes"],
     "lookback_window": "500 bars",
     "normalization": "per-symbol rolling z-score (252 bars)"
   }

3. 更新策略:
   - 每日 ETL cron: 前一天的原始數據 → 新 Parquet 分區
   - 增量追加: 只處理新數據 (WHERE ts > last_export_ts)
   - 全量重算: 版本升級時才需要
```

### 3.3.3 PostgreSQL → Parquet 導出策略

```python
# 概念代碼 — ETL cron job (nightly)
# 實際實現建議放在 helper_scripts/etl/ 或新的 Rust crate

"""
導出策略:
  - 增量導出: 每日 cron，導出 [yesterday 00:00, today 00:00) 的數據
  - 分區格式: data/parquet/{category}/{table}/dt={YYYY-MM-DD}/{symbol}.parquet
  - 壓縮: Snappy (讀取速度優先) 或 ZSTD (存儲效率優先)
  - 元數據: 每個 Parquet 文件包含 schema version + row count + time range
"""

# 導出路徑模式:
# data/parquet/market/klines/dt=2026-04-03/BTCUSDT.parquet
# data/parquet/market/ticks/dt=2026-04-03/BTCUSDT.parquet
# data/parquet/market/regimes/dt=2026-04-03/BTCUSDT.parquet
# data/parquet/features/v1/dt=2026-04-03/BTCUSDT.parquet
# data/parquet/labels/direction/dt=2026-04-03/BTCUSDT.parquet
# data/parquet/trades/dt=2026-04-03/all.parquet
```

### 3.3.4 DuckDB 在 Feature Engineering 中的角色

```
DuckDB 定位: 嵌入式 OLAP 引擎，Python 進程內運行
            用於離線特徵計算和數據探索，不用於在線服務

使用場景:
  1. 讀取 Parquet → 計算窗口特徵 → 寫入新 Parquet
     DuckDB 原生支持讀寫 Parquet，比 pandas 快 10-100x

  2. 特徵回測驗證
     SELECT symbol, ts,
            avg(close) OVER (PARTITION BY symbol ORDER BY ts ROWS 20 PRECEDING) as sma_20,
            ...
     FROM read_parquet('data/parquet/market/klines/dt=*/BTCUSDT.parquet')

  3. Label 生成
     -- 未來 N 分鐘方向 label
     SELECT *,
       CASE WHEN lead(close, 60) OVER (PARTITION BY symbol ORDER BY ts) > close * 1.005
            THEN 'UP'
            WHEN lead(close, 60) OVER (PARTITION BY symbol ORDER BY ts) < close * 0.995
            THEN 'DOWN'
            ELSE 'FLAT'
       END as label_direction_1h
     FROM read_parquet(...)

  4. 訓練/驗證/測試集切分 (避免 look-ahead bias)
     -- Temporal split: train < val < test
     -- Walk-forward: rolling window validation
     -- Embargo gap: 禁止 train/val 邊界附近的數據 (防止信息洩漏)

DuckDB 數據庫文件: data/duckdb/openclaw_features.duckdb
  - 附加外部 Parquet 文件為 views (不複製數據)
  - 存儲計算中間結果和 feature metadata
```

### 3.3.5 PyTorch DataLoader 接入

```python
# 概念設計 — 直接讀 Parquet, 不經過 DuckDB
# 適合 AMD AI MAX 395 的 128GB 統一記憶體

import pyarrow.parquet as pq
import torch
from torch.utils.data import Dataset, DataLoader

class ParquetTradingDataset(Dataset):
    """
    直接從 Parquet 文件讀取的 PyTorch Dataset。

    設計決策:
    - 使用 pyarrow memory-mapped 讀取，利用 128GB 統一記憶體
    - 支持滑動窗口 (lookback_window bars 作為一個 sample)
    - On-the-fly 正規化 (per-symbol rolling z-score)
    - 支持時間序列 cross-validation
    """

    def __init__(
        self,
        feature_dir: str,      # data/parquet/features/v1/
        label_dir: str,        # data/parquet/labels/direction/
        symbols: list[str],
        date_range: tuple[str, str],   # ('2026-04-01', '2026-06-01')
        lookback_window: int = 500,    # 500 bars context
        label_column: str = 'label_direction_1h',
    ):
        ...

    def __getitem__(self, idx) -> tuple[torch.Tensor, torch.Tensor]:
        # Returns (features_window, label) pair
        # features_window shape: (lookback_window, n_features)
        # label shape: (n_classes,) one-hot
        ...

# 使用:
# train_ds = ParquetTradingDataset(
#     feature_dir='data/parquet/features/v1/',
#     label_dir='data/parquet/labels/direction/',
#     symbols=['BTCUSDT', 'ETHUSDT', ...],
#     date_range=('2026-04-01', '2026-07-01'),
# )
# train_loader = DataLoader(train_ds, batch_size=256, num_workers=4, shuffle=False)
# ★ shuffle=False 因為時間序列不能打亂順序
# ★ 使用 SequentialSampler 或自定義 temporal sampler
```

### 3.3.6 訓練/驗證/測試集時間切分策略

```
避免 Look-Ahead Bias 的時間切分方案:

方案 A: 固定三分 (Fixed Split)
=========================================
|← Train (70%) →|← Val (15%) →|← Test (15%) →|
|  2026-04~07    |  2026-07~08  |  2026-08~09  |

  ★ 簡單但不利用最新數據訓練

方案 B: Walk-Forward (推薦)
=========================================
Round 1: |←Train→|←Val→|       ←Test→|
Round 2:    |←Train→|←Val→|   ←Test→|
Round 3:       |←Train→|←Val→|←Test→|

  ★ 每輪使用更多歷史數據
  ★ 測試集始終是 "最新" 數據
  ★ 可以觀察模型隨時間的表現變化

方案 C: Walk-Forward + Embargo Gap (最嚴格)
=========================================
|←Train→|🚫gap🚫|←Val→|🚫gap🚫|←Test→|

  Embargo gap = max(lookback_window, prediction_horizon)
  防止 train 和 val 之間的數據洩漏

推薦: 方案 C (Walk-Forward + Embargo)
  - embargo_bars = max(500, 60) = 500 bars = ~8.3 hours (1m bars)
  - min_train_bars = 30 * 1440 = 43,200 bars (30 days)
  - val_bars = 7 * 1440 = 10,080 bars (7 days)
  - test_bars = 7 * 1440 = 10,080 bars (7 days)
  - step_bars = 7 * 1440 = 10,080 bars (7 days per round)
```

### 3.3.7 Label 生成邏輯存儲

```
Label 類型 & 存儲位置:

1. Direction Labels (方向預測)
   存儲: data/parquet/labels/direction/dt={date}/{symbol}.parquet
   生成: DuckDB SQL (lead window over close price)
   類別: UP (>+0.5%), DOWN (<-0.5%), FLAT (otherwise)
   時間窗口: 15m, 1h, 4h (多個 columns)

2. Volatility Labels (波動率預測)
   存儲: data/parquet/labels/volatility/dt={date}/{symbol}.parquet
   生成: 未來 N bars 的 realized volatility bucket
   類別: LOW, NORMAL, HIGH, EXTREME

3. Regime Labels (市場狀態分類)
   存儲: data/parquet/labels/regime/dt={date}/{symbol}.parquet
   生成: 從 market_regimes 表直接映射
   類別: TRENDING_UP/DOWN, RANGING, SQUEEZE, BREAKOUT, etc.

4. Optimal Action Labels (最優行動 — Phase 3+)
   存儲: data/parquet/labels/action/dt={date}/{symbol}.parquet
   生成: 回測最優進出場時機 (hindsight)
   類別: ENTER_LONG, ENTER_SHORT, EXIT, HOLD

Label 版本控制:
  每個 label 目錄包含 manifest.json:
  {
    "label_name": "direction_1h",
    "version": "v1",
    "threshold_up": 0.005,
    "threshold_down": -0.005,
    "lookforward_bars": 60,
    "generated_at": "2026-04-03T...",
    "source": "klines_1m.close"
  }
```

---

## 3.4 遷移計劃

### P0 — 立即執行（數據正在流失）

| # | 任務 | 影響範圍 | 改動量 | 說明 |
|---|------|---------|--------|------|
| P0-1 | **raw_ticks 持久化** | `bybit_public_ws_listener.py` 新增 PG 寫入 | ~80 行 | 在 PriceEvent 處理後追加 `INSERT INTO raw_ticks` (batch insert, 每秒 flush) |
| P0-2 | **klines_1m 持久化** | `kline_manager.py` 新增 closed bar 回調 | ~60 行 | 在 `_emit_closed_bar()` 中追加 PG 寫入 |
| P0-3 | **安裝 TimescaleDB** | PostgreSQL 配置 | ops 操作 | `CREATE EXTENSION timescaledb` + 創建 hypertables |
| P0-4 | **indicator_values 持久化** | `indicator_engine.py` 新增計算後回調 | ~80 行 | 在每次 `compute()` 後批量寫入指標值 |

**向後兼容**：P0 是純新增，不修改現有 JSON 邏輯。記憶體緩衝仍然保留用於實時查詢，PG 寫入異步不阻塞。

### P1 — 近期應做（提升系統可靠性）

| # | 任務 | 影響範圍 | 改動量 | 說明 |
|---|------|---------|--------|------|
| P1-1 | **market_regimes 持久化** | `market_regime.py` | ~40 行 | regime 轉換時寫入 PG |
| P1-2 | **signal_log 持久化** | `signal_engine.py` | ~50 行 | 信號生成時寫入 PG |
| P1-3 | **guardian_verdicts 持久化** | `guardian_agent.py` | ~40 行 | verdict 生成時寫入 PG，移除 max 200 限制 |
| P1-4 | **agent_messages 持久化** | `multi_agent_framework.py` | ~50 行 | MessageBus dispatch 時寫入 PG |
| P1-5 | **market_tickers → hypertable** | `init_trading_schema.sql` + migration | ~20 行 SQL | 現有表遷移為 hypertable + 壓縮 |
| P1-6 | **TruthSourceRegistry → PG** | `truth_source_registry.py` | ~100 行 | JSON → PG 雙寫，JSON 降為備份 |
| P1-7 | **ExperimentLedger → PG** | `experiment_ledger.py` | ~100 行 | JSON → PG 雙寫，JSON 降為備份 |

**向後兼容策略**：P1 階段採用 **雙寫模式** — 同時寫 JSON 和 PG。讀取優先 PG，PG 不可用時 fallback 到 JSON。確認 PG 穩定後（1-2 週），逐步移除 JSON 寫入。

### P2 — ML 準備期

| # | 任務 | 影響範圍 | 改動量 | 說明 |
|---|------|---------|--------|------|
| P2-1 | **ETL cron job** | 新增 `helper_scripts/etl/pg_to_parquet.py` | ~200 行 | 每日增量導出 PG → Parquet |
| P2-2 | **Feature Store v1** | 新增 `helper_scripts/etl/compute_features.py` | ~300 行 | DuckDB 讀 Parquet → 計算特徵 → 寫特徵 Parquet |
| P2-3 | **Label 生成器** | 新增 `helper_scripts/etl/generate_labels.py` | ~200 行 | DuckDB 生成 direction/volatility/regime labels |
| P2-4 | **PyTorch Dataset** | 新增 `program_code/ml/dataset.py` | ~150 行 | ParquetTradingDataset 實現 |
| P2-5 | **歷史數據回填** | 新增 `helper_scripts/etl/backfill_klines.py` | ~100 行 | Bybit REST API 拉取歷史 K 線填入 PG |
| P2-6 | **trade_observations 表** | `paper_trading_engine.py` 修改 | ~60 行 | 每次 round-trip close 寫入完整觀察記錄 |

### P3 — 長期優化

| # | 任務 | 說明 |
|---|------|------|
| P3-1 | **JSON 移除** | 確認 PG 穩定後，移除 P1 階段的 JSON 雙寫 |
| P3-2 | **Parquet 壓縮優化** | 根據實際數據量調整壓縮策略 (Snappy → ZSTD) |
| P3-3 | **特徵版本自動化** | CI/CD 中自動驗證特徵 schema 變更 |
| P3-4 | **模型 artifact 管理** | data/models/ 下存儲訓練好的模型 + 元數據 |
| P3-5 | **Grafana ML 儀表盤** | 新增 ML 指標追蹤面板（特徵漂移、模型性能） |

### 遷移時間軸

```
Week 1 (P0):  TimescaleDB 安裝 + raw_ticks/klines/indicators 持久化
Week 2 (P1a): market_regimes + signal_log + guardian_verdicts 持久化
Week 3 (P1b): agent_messages + TruthSourceRegistry/Ledger → PG 雙寫
Week 4 (P2a): ETL cron + 歷史回填
Week 5 (P2b): Feature Store v1 + Label 生成
Week 6 (P2c): PyTorch Dataset + 第一個訓練實驗
Week 7+ (P3): 優化、JSON 移除、自動化
```

---

## 3.5 目錄結構建議

```
/home/ncyu/BybitOpenClaw/
├── srv/                              # 應用代碼（現有）
│   ├── program_code/                 # 核心代碼
│   │   ├── ml/                       # 🆕 ML 代碼 (P2)
│   │   │   ├── dataset.py            # ParquetTradingDataset
│   │   │   ├── features.py           # Feature 定義 & 版本管理
│   │   │   └── labels.py             # Label 生成邏輯
│   │   └── ...
│   ├── helper_scripts/
│   │   ├── etl/                      # 🆕 ETL 腳本 (P2)
│   │   │   ├── pg_to_parquet.py      # PG → Parquet 增量導出
│   │   │   ├── compute_features.py   # 特徵計算 (DuckDB)
│   │   │   ├── generate_labels.py    # Label 生成
│   │   │   └── backfill_klines.py    # 歷史 K 線回填
│   │   └── ...
│   ├── database_files/               # 現有 PG/Redis/Qdrant 數據目錄
│   ├── docker_projects/
│   │   └── monitoring_services/
│   │       ├── init_trading_schema.sql     # 現有 11 表
│   │       └── migrations/                 # 🆕 Schema 遷移
│   │           ├── 001_timescaledb.sql      # TimescaleDB 啟用
│   │           ├── 002_timeseries_tables.sql # T 類 hypertables
│   │           ├── 003_business_tables.sql   # B 類新表
│   │           ├── 004_learning_tables.sql   # L 類新表
│   │           └── 005_continuous_aggs.sql   # 連續聚合
│   └── settings/                     # C 類配置（保持 JSON）
│       ├── risk_control_rules/
│       ├── service_configs/
│       └── environment_files/
│
├── data/                             # 🆕 數據根目錄 (P2)
│   ├── parquet/
│   │   ├── market/
│   │   │   ├── klines/               # dt=YYYY-MM-DD/{symbol}.parquet
│   │   │   ├── ticks/                # dt=YYYY-MM-DD/{symbol}.parquet
│   │   │   └── regimes/              # dt=YYYY-MM-DD/{symbol}.parquet
│   │   ├── features/
│   │   │   ├── v1/                   # 版本化特徵
│   │   │   │   ├── manifest.json
│   │   │   │   └── dt=YYYY-MM-DD/{symbol}.parquet
│   │   │   └── v2/
│   │   ├── labels/
│   │   │   ├── direction/
│   │   │   ├── volatility/
│   │   │   └── regime/
│   │   └── trades/
│   │       └── dt=YYYY-MM-DD/all.parquet
│   ├── models/                       # 訓練好的模型 artifacts (P3)
│   │   ├── direction_v1/
│   │   │   ├── model.pt
│   │   │   ├── config.json
│   │   │   └── metrics.json
│   │   └── regime_v1/
│   └── duckdb/
│       └── openclaw_features.duckdb  # DuckDB 特徵引擎數據庫
│
├── secrets/                          # API 金鑰（現有）
└── config/                           # 🆕 可選：將 C 類從 srv/settings 提升
```

### .gitignore 追加

```gitignore
# Data files (too large for git)
data/parquet/
data/models/
data/duckdb/
database_files/postgres_data/
database_files/redis_data/
database_files/vector_database_data/
```

---

## 附錄 A: 關鍵發現摘要

### ⚠️ DATA LOSS RISK 清單

1. **T-1 原始 price ticks** — WebSocket 接收後從不持久化，每次重啟永久丟失
2. **T-2 K 線歷史** — 只在記憶體環形緩衝 (500 bars)，重啟丟失全部歷史
3. **T-3 指標值歷史** — 只在記憶體 cache，重啟丟失所有計算結果
4. **T-4 Regime 狀態歷史** — 只在記憶體，重啟丟失策略上下文
5. **L-4 信號歷史** — 從不持久化，無法回測信號質量
6. **L-5 Regime 轉換歷史** — ML 模型訓練的關鍵素材，完全丟失

### ⚠️ RACE CONDITION RISK 清單

1. **TruthSourceRegistry** — save_snapshot() 在 Lock 外執行寫入。當前低頻（手動觸發），但多 Agent 並行時有風險。
2. **ExperimentLedger** — 同上，save_snapshot() 在 Lock 外。60s 防抖降低實際風險但不消除。

### 正面發現

- 核心控制狀態（JsonStateStore, PaperTradeStateStore）使用 tempfile + os.replace() **原子寫入** + RLock 線程安全，設計合理。
- PostgreSQL schema 已經設計了 11 張表，基礎在位，只需升級和補充。
- 審計系統（AuditPersistence）使用 JSONL 追加 + 自動輪轉，是最健壯的持久化組件。
- GrafanaDataWriter 和 BybitDemoSync 已經建立了 PG 寫入管線，遷移有基礎。
- 所有 JSON 持久化組件都有 fail-open 降級，不會因持久化失敗而中斷交易。

---

## 附錄 B: 依賴清單

### 當前已有
- PostgreSQL 16 + psycopg2-binary ≥ 2.9.0
- Redis (端口 6379，代碼中未直接使用)
- Qdrant (端口 6333/6334，向量數據庫)

### 需要新增
| 組件 | 用途 | 安裝方式 | 是否必須 |
|------|------|---------|---------|
| **TimescaleDB** | 時間序列 hypertables + 壓縮 + 連續聚合 | `apt install timescaledb-2-postgresql-16` | ✅ P0 |
| **DuckDB** | 離線特徵計算 + Parquet 讀寫 | `pip install duckdb` | P2 |
| **PyArrow** | Parquet 文件操作 + memory-mapped 讀取 | `pip install pyarrow` | P2 |
| **PyTorch** | ML/DL 訓練框架 | `pip install torch` (ROCm for AMD) | P2/P3 |

> 所有新增依賴均為開源、零成本。符合「零外部成本可運行」原則。

---

*文件生成日期: 2026-04-03*
*審計範圍: /home/ncyu/BybitOpenClaw/srv (全部 Python + Rust 代碼)*
*審計深度: 539 Python 文件 + 4 Cargo.toml + 全部 JSON 數據文件*
