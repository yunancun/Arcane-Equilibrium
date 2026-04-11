# 三引擎並行架構遷移計劃 (3E-ARCH)
# Three-Engine Parallel Architecture Migration Plan

**作者 / Authors**: PM + PA + FA  
**日期 / Date**: 2026-04-11（v4 修訂 — 嚴格審查：+6 gaps 修復 +4 事實校正）  
**優先級 / Priority**: P0 — 下一個主要開發週期首要任務  
**TODO 索引 / TODO ref**: 3E-1 ~ 3E-9  

---

## 一、執行摘要

當前系統使用「單一 TickPipeline + 模式切換」架構（Signal Diamond Phase 3 中間態）。用戶的目標是三個引擎（Paper / Demo / Live）**同時並行運行**，各自接入對應 API，各自寫入 DB，由 `system_mode` 統一治理哪些引擎被允許開單。

`trading_mode`（全局單值配置）是單引擎時代的遺物，在三引擎世界中無意義——每個管線的「模式」是它的固定身份，不是配置項。本計劃完整描述遷移路徑與 `trading_mode` 清除範圍。

**設計哲學**：三引擎不是三份複製品。每個引擎有不同的**角色定位**：
- **Paper**：激進探索策略，最寬鬆風控，快速試錯積累數據
- **Demo**：穩定策略驗證，中等風控，策略從 Paper 畢業後的驗證場
- **Live**：生產策略執行，最嚴格風控 + 完整治理，只跑經過驗證的策略

---

## 二、現狀診斷

### 2.1 現狀架構

```
main.rs
└── 單一 run_event_consumer()
    └── 單一 TickPipeline
        ├── trading_mode: TradingMode  ← 全局單值，決定「現在是哪個模式」
        ├── mode_states: HashMap<TradingMode, ModeState>  ← 狀態倉庫
        └── active_modes: Vec<TradingMode>

模式切換方式：
  set_trading_mode(new) → std::mem::swap 保存舊狀態、加載新狀態
  → 同一時間只有一個模式在執行 tick（非並行）
```

**核心問題**：Signal Diamond Phase 3 的 `mode_states` / `active_modes` 是「多模式感知的單引擎」，不是「三個獨立引擎並行」。用戶要的是後者。

### 2.2 `trading_mode` Load-bearing 使用點清單

以下每一處在移除前必須有替換方案：

| 文件 + 行號 | 用途 | 替換方案 |
|---|---|---|
| `main.rs:641-643` | 根據 mode 決定 Bybit API 環境（mainnet vs demo） | 每個 Pipeline 構造時固定 `bybit_env` |
| `main.rs:1647-1651` | 路由到對應 RiskConfig store | 每個 Pipeline 直接持有自己的 store Arc |
| `main.rs:657-667` | 讀取初始餘額（Live 模式下也讀 Demo 餘額） | 每個 Pipeline 獨立讀取自己帳戶餘額 |
| `event_consumer/mod.rs:283` | `set_trading_mode()` 初始化調用 | Pipeline 構造時固定 `pipeline_kind`，無需再 set |
| `event_consumer/mod.rs:293,308,313` | Live 模式的 paper balance 鏡像邏輯 | Paper Pipeline 固定讀 Demo 餘額 |
| `event_consumer/mod.rs:533,590,659,768` | `pipeline.trading_mode.db_mode()` 寫 DB 標記 | `self.pipeline_kind.db_mode()` 硬編碼 |
| `tick_pipeline.rs:is_exchange_mode` | 決定訂單走交易所還是本地模擬 | `self.pipeline_kind.is_exchange()` |
| `tick_pipeline.rs:ipc_close_all()` | 根據 mode 分支：exchange→reduce_only / paper→清 state | 同上 |
| `tick_pipeline.rs:snapshot()` | `trading_mode: self.trading_mode` 寫入快照 | `pipeline_kind: self.pipeline_kind.db_mode()` |
| `bybit_rest_client.rs:111-115` | `secret_slot()` 決定讀哪組 API key | Pipeline 構造時傳入 `bybit_env`，client 知道自己的環境 |
| `config/mod.rs:363-368` | cold 參數警告，阻止熱重載 | 整個 `TradingMode` 移除後自然消失 |
| `ipc_server.rs:597` | 快照路由：mode == trading_mode → 返回頂層 paper_state | 每個 Pipeline 有各自快照文件，按 engine 參數路由 |

**Python 側（~35 處引用，集中在 live_session_routes.py）**：

| 文件 | 用途 | 替換方案 |
|---|---|---|
| `live_session_routes.py:240-256` | `_get_trading_mode_from_engine()` 讀快照 | 讀 `system_mode` 或 per-engine endpoint |
| `live_session_routes.py:569,603` | 返回 `trading_mode` 給 GUI | 改返回 `system_mode` |
| `live_session_routes.py:635-637,804-805` | Global mode gate 用 trading_mode | 改用 `system_mode` / `_get_global_mode_state()` |
| `ipc_state_reader.py` | `trading_mode` 路由快照讀取 | 按 `engine` 參數路由到對應快照文件 |

---

## 三、目標架構

```
main.rs
│
├── ── 共享資源（三個 Pipeline 共用）──────────────────────────
│   ├── 公共 WebSocket（market data fan-out → N 個 event_tx）
│   ├── IPC Server（統一端點，engine 參數路由命令）
│   ├── Scanner / SymbolRegistry（symbol universe 同步所有管線）
│   ├── InstrumentInfoCache（合約規格，共享）
│   ├── NewsPipeline（共享，所有管線接收同一新聞快照）
│   └── JS Edge Estimates（per-engine 隔離，見 D9）
│
├── ── Paper Pipeline（永遠啟動）─────────────────────────────
│   ├── pipeline_kind = PipelineKind::Paper（固定，不可更改）
│   ├── 無 REST client（本地模擬，不需要 API）
│   ├── 無 private WS（無真實訂單）
│   ├── initial_balance = Demo 帳戶餘額（有 Demo key 時）/ GUI 配置金額（無 key 時）
│   ├── 治理：無 Authorization gate / 無 Lease / 無 Reconciler
│   ├── 風控：RiskGovernor（獨立 SM，寬鬆）+ RiskConfig paper
│   ├── 策略角色：激進探索（所有策略、寬參數範圍）
│   ├── cost_gate：探索模式（cold-start 放行）
│   ├── pipeline_cmd_tx_paper channel（★ 已統一命名為 PipelineCommand）
│   ├── DB engine_mode = "paper"
│   └── 快照 → pipeline_snapshot_paper.json
│
├── ── Demo Pipeline（需要 Demo API key）─────────────────────
│   ├── pipeline_kind = PipelineKind::Demo（固定）
│   ├── REST client → api-demo.bybit.com（Demo API key）
│   ├── ★ private WS → stream-demo.bybit.com（Demo API key，獨立 supervisor）
│   │   └── 事件路由：fill/order/position → 僅此 Demo pipeline（不進 Live）
│   ├── initial_balance = Demo 帳戶實際餘額
│   ├── 治理：簡化 Authorization（自動授予）/ 無 Lease
│   ├── 風控：RiskGovernor（獨立 SM，中等）+ RiskConfig demo
│   ├── StopManager：獨立實例，綁定 Demo BybitRestClient（★ REST 綁定）
│   ├── Reconciler：獨立實例（對賬 Demo 交易所倉位，持有 Demo cmd_tx）
│   ├── 策略角色：穩定策略驗證（從 Paper 畢業的策略）
│   ├── cost_gate：中等（有 JS 估計時用，無時 ATR gate）
│   ├── pipeline_cmd_tx_demo channel
│   ├── DB engine_mode = "demo"
│   └── 快照 → pipeline_snapshot_demo.json
│
└── ── Live Pipeline（需要 live slot 有自己的 API key）──────
    ├── pipeline_kind = PipelineKind::Live（固定）
    ├── API key 要求：live slot 必須有自己的 key（不降級到 demo slot）
    │   ├── live slot 有 key → 讀 bybit_endpoint metadata 決定環境
    │   └── live slot 無 key → 不啟動（無降級）
    ├── REST client → 按環境決定：
    │   ├── Mainnet → api.bybit.com（真實資金）
    │   └── LiveDemo → api-demo.bybit.com（Live-Demo 測試）
    ├── ★ private WS → 對應 endpoint（獨立 supervisor，獨立 credentials）
    │   └── 事件路由：fill/order/position → 僅此 Live pipeline（不進 Demo）
    ├── initial_balance = Live/Live-Demo 帳戶實際餘額
    ├── 治理：完整 GovernanceCore（Production profile）全流程
    ├── 風控：RiskGovernor（獨立 SM，最嚴格）+ RiskConfig live
    ├── StopManager：獨立實例，綁定 Live BybitRestClient（★ REST 綁定）
    ├── Reconciler：獨立實例（對賬 Live 交易所倉位，持有 Live cmd_tx）
    ├── 策略角色：生產策略（只跑經驗證的策略）
    ├── cost_gate：嚴格 fail-closed（必須有正 JS 估計）
    ├── pipeline_cmd_tx_live channel
    ├── DB engine_mode = "live"
    └── 快照 → pipeline_snapshot_live.json
```

**system_mode 治理層（不變）**：

```
system_mode (GUI global_mode_state) 決定哪些 Pipeline 允許開單：
  live_reserved  → Paper ✓  Demo ✓  Live ✓
  demo_reserved  → Paper ✓  Demo ✓  Live ✗ (封鎖開單)
  shadow_only    → Paper ✓  Demo ✗  Live ✗
  observe_only   → Paper ✗  Demo ✗  Live ✗ (全部暫停)
  design_only    → 同 observe_only
```

---

## 四、關鍵設計決策

### D1: 條件式啟動邏輯

```
Pipeline 啟動決策樹：

Paper：永遠啟動
  ├── 有 Demo API key → initial_balance = Demo 帳戶實際餘額
  └── 無 Demo API key → initial_balance = GUI 配置金額（paper_config.toml）

Demo：需要 demo slot 有 API key
  ├── 有 key → 啟動，連接 api-demo.bybit.com
  └── 無 key → 不啟動，log "Demo Pipeline: skipped (no API key)"

Live：需要 live slot 有自己的 API key（不降級到 demo slot）
  ├── live slot 有 key → 讀 bybit_endpoint metadata
  │   ├── endpoint=mainnet → Mainnet 模式（真實資金）
  │   └── endpoint=demo/live_demo → LiveDemo 模式（live 路徑，demo 伺服器）
  ├── live slot 有 key 但 key == demo slot key → 拒絕啟動（同帳戶衝突）
  └── live slot 無 key → 不啟動，log "Live Pipeline: skipped (no API key)"

額外檢查：
  - system_mode 必須允許該 Pipeline 運行
  - 啟動時 health check（GET /v5/account/wallet-balance），401/403 → 不啟動
```

**不設降級機制的理由**（審查 BB-C2 修正）：如果 Live fallback 到 demo slot key，Demo 和 Live 兩個 Pipeline 會同時對同一個 Bybit 帳戶下單，Reconciler 互相製造 Ghost/Orphan 漂移 → CircuitBreaker 連鎖升級。D2 衝突偵測無法攔截（key 相同因為就是同一組）。用戶想測試 Live 路徑時，應在 live slot 放一組**不同於 demo slot 的** demo API key。

### D2: API Key 衝突偵測（Settings 層）

在 Python `settings_routes.py` 的 API key 更新端點中加入衝突檢測：

```
更新 Demo API key 時：
  → 比對 live slot 已有的 key
  → 如果一致 → 拒絕，返回 409 "API key conflicts with live slot"

更新 Live API key 時：
  → 比對 demo slot 已有的 key
  → 如果一致 → 拒絕，返回 409 "API key conflicts with demo slot"
```

目的：防止兩個 Pipeline 同時對同一個 Bybit 帳戶下單，導致倉位互相干擾。

### D3: 分層治理（核心設計）

三個引擎不是三份相同的治理棧。治理嚴格程度與引擎角色匹配：

| 治理組件 | Paper | Demo | Live |
|---------|-------|------|------|
| **Authorization gate** | 跳過（自動授予） | 跳過（自動授予） | 完整流程（SM-1） |
| **Decision Lease** | 跳過 | 跳過 | 完整流程（SM-2） |
| **Guardian (risk review)** | 運行但寬鬆 | 運行，中等閾值 | 運行，嚴格閾值 |
| **RiskGovernor SM** | 獨立實例，寬鬆 | 獨立實例，中等 | 獨立實例，嚴格 |
| **RiskConfig** | `risk_config_paper.toml` | `risk_config_demo.toml` | `risk_config_live.toml` |
| **StopManager** | 獨立實例 | 獨立實例 | 獨立實例 |
| **Cost gate** | 探索模式 | 中等 | 嚴格 fail-closed |
| **Reconciler** | 不需要 | 獨立實例 | 獨立實例 |
| **Kelly sizing** | 運行 | 運行 | 運行 |
| **P1 cap** | 運行（寬鬆上限） | 運行（中等上限） | 運行（嚴格上限） |

**理由**：Paper 和 Demo 不會造成真實損失。強制它們走完整授權/租約流程只會增加複雜度和 false lockdown 風險，而不提供保護價值。

**實現方式**：不是 if/else 跳過，而是 `GovernanceCore` 構造時接受 `GovernanceProfile`：
```rust
pub enum GovernanceProfile {
    Exploration,  // Paper: auto-grant, no lease, lenient gates
    Validation,   // Demo: auto-grant, no lease, moderate gates
    Production,   // Live: full auth + lease + strict gates
}
```

### D4: 策略角色分層

每個 Pipeline 實例化自己的策略組（4 active strategies × 3 pipelines = 12 instances；FundingRateArb 已定義但未啟用），參數不同：

| 策略 | Paper | Demo | Live |
|------|-------|------|------|
| 參數範圍 | 最寬（Optuna 探索全域） | 中等（驗證過的參數區間） | 最窄（生產固定值） |
| 進入門檻 | 低 confidence | 中等 confidence | 高 confidence |
| 新策略 | 允許未驗證策略 | 只允許 Paper 畢業策略 | 只允許 Demo 畢業策略 |

**策略參數 promotion 驗證**（審查 FM-H7 修正）：PromotionPipeline 不能直接搬運參數。Paper 在寬鬆風控下的績效是 Live 嚴格環境下的**有偏估計**（被 Live cost_gate 拒絕的信號在 Paper 中被執行）。Promote 前必須加一步「模擬 Live 風控約束的 Paper 回測」：重播 Paper 交易記錄，套用目標引擎的 RiskConfig/cost_gate/Guardian 閾值，驗證過濾後的子集績效仍為正。

### D5: 性能指標 + JS Edge 估計隔離

每個引擎的績效和 edge 估計獨立計算，互不影響：

| 指標 | 數據源 | 隔離方式 |
|------|-------|---------|
| 實時 PnL/balance | Rust `PaperState` | 每個 Pipeline 獨立實例（已隔離） |
| Sharpe / drawdown / holding | Python metrics | SQL `WHERE engine_mode = $1` |
| Trade count / win rate | Python metrics | SQL `WHERE engine_mode = $1` |
| JS edge estimates | Rust `EdgeEstimator` | **per-engine 隔離**（見 D9） |

Python metrics 端點改為 `GET /api/v1/{engine}/metrics`（engine = paper/demo/live）。

### D6: 錯誤隔離 + 三級遞減收縮（審查 CC-C4 修正）

**原則 #6 合規**：失敗默認收縮。但不是一刀切——三引擎有層級關係：

```
三級遞減收縮模型：

Paper crash / CB / 風控鎖死：
  → Demo 進入 Cautious 觀察 60s（Paper 激進參數頻繁觸發，幅度小）
  → Live 不受影響（Paper 問題不傳染 Live）
  → 理由：Paper 的 CB 多因激進參數，非市場系統性問題

Demo crash / CB（非 Paper 引起）：
  → Live 進入 Cautious 觀察 120s（Demo 問題更可能反映市場/交易所問題）
  → Paper 不受影響（Paper 只做本地模擬）
  → 理由：Demo 連接真實交易所，崩潰可能暗示 API/市場數據問題

Demo crash / CB（由 Paper 引起的共享資源問題）：
  → 標記為 Paper 引起，Live 不受影響
  → 共享資源（WS、DB）問題才傳染

Live crash / CB：
  → 只影響自己（已是最高級）
  → Paper/Demo 繼續運行積累數據

判斷「是否 Paper 引起」：
  Paper 在 Demo crash 前 30s 內也處於異常狀態 → Paper 引起
  Paper 正常但 Demo 異常 → 非 Paper 引起 → 傳染 Live
```

**技術實現**：
```rust
// 每個 Pipeline 在獨立的 tokio task 中運行
tokio::spawn(async move {
    match run_event_consumer(deps).await {
        Ok(()) => info!("{} pipeline stopped normally", kind),
        Err(e) => {
            error!("{} pipeline crashed: {}", kind, e);
            // 通知其他引擎（三級遞減）
            cross_engine_notify.send(EngineEvent::Crashed(kind));
        }
    }
    pipeline_health.store(PipelineHealth::Down);
})

// 跨引擎通知接收端（每個 Pipeline 持有 receiver）
// Paper crash → demo_receiver 收到 → escalate_to(Cautious, "paper_crash")
// Demo crash → live_receiver 收到 → escalate_to(Cautious, "demo_crash")
```

**有序 shutdown**（審查 BB-M8 修正）：
```
ctrl+c → CancellationToken::cancel()
  → 所有 Pipeline 收到取消信號
  → shutdown 順序：Live 先 drain+flush → Demo → Paper（最後）
  → 理由：Live 數據最重要，優先保證完整性
  → 每個 Pipeline flush 完成後設 barrier，下一個才開始
```

**Watchdog**：檢查 3 個快照文件，per-pipeline 報告。

### D7: Paper 初始餘額配置

新增 GUI 入口：Paper Trading 頁面加一個 "Initial Balance" 輸入框：
- 寫入 `settings/paper_config.toml` 的 `initial_balance_usdt` 字段
- 有 Demo API key 時：忽略此配置，讀 Demo 帳戶真實餘額
- 無 Demo API key 時：使用此配置值（默認 10000.0）

### D8: 策略與管線解耦（核心設計約束）

**原則**：策略是 Agent 的領域（可學習、可進化、可調參），Pipeline 是純基礎設施。對策略代碼的任何改動只需做一次，三條 Pipeline 自動生效。

**分層模型**：
```
┌─────────────────────────────────────────────────────┐
│  策略代碼（Strategy trait + impl）                    │
│  單一源碼，strategies/ 模組                           │
│  改一次 → 三引擎自動生效                              │
│  MaCrossover / BbReversion / BbBreakout / Grid / ... │
└───────────────────────┬─────────────────────────────┘
                        │ StrategyFactory::create_all()
                        │ 一個函數，一個註冊點
                        ▼
┌─────────────────────────────────────────────────────┐
│  策略實例（per-pipeline 獨立實例）                     │
│  每個 Pipeline 持有自己的 Orchestrator + 策略實例      │
│  實例持有可變狀態（positions, indicators）             │
│  三個 Pipeline = 三組獨立實例，互不干擾                │
└───────────────────────┬─────────────────────────────┘
                        │ load_strategy_params(kind, config)
                        ▼
┌─────────────────────────────────────────────────────┐
│  策略參數（per-engine 獨立配置）                      │
│  strategy_params_paper.toml — 寬參數範圍，激進探索    │
│  strategy_params_demo.toml  — 中等範圍，驗證中        │
│  strategy_params_live.toml  — 窄範圍，生產固定值      │
│  Agent 通過 IPC 可動態調整（已有機制）                 │
│  PromotionPipeline 負責 Paper→Demo→Live 參數遷移     │
└─────────────────────────────────────────────────────┘
```

**StrategyFactory（新增）**：
```rust
/// Single registration point for all strategies.
/// 策略唯一註冊點 — 新增/移除策略只改這一個函數。
pub struct StrategyFactory;

impl StrategyFactory {
    /// Create fresh strategy instances for any pipeline.
    /// All pipelines get the same set of strategies with default params.
    /// Per-engine params are loaded afterward via load_strategy_params().
    pub fn create_all() -> Vec<Box<dyn Strategy>> {
        vec![
            Box::new(MaCrossover::new()),
            Box::new(BbReversion::new()),
            Box::new(BbBreakout::new()),
            Box::new(GridTrading::new_adaptive()),
            // Box::new(FundingRateArb::new()),  // uncomment when ready
        ]
    }
}
```

**Per-engine 參數加載**：
```rust
/// Load strategy params from per-engine config file.
/// 從 per-engine 配置文件加載策略參數。
fn load_strategy_params(orchestrator: &mut Orchestrator, kind: PipelineKind) {
    let params_path = match kind {
        PipelineKind::Paper => "settings/strategy_params_paper.toml",
        PipelineKind::Demo  => "settings/strategy_params_demo.toml",
        PipelineKind::Live  => "settings/strategy_params_live.toml",
    };
    if let Ok(config) = std::fs::read_to_string(params_path) {
        // Parse TOML → per-strategy JSON → update_params_json()
        for strategy in orchestrator.strategies_mut() {
            if let Some(params_json) = extract_strategy_section(&config, strategy.name()) {
                if let Err(e) = strategy.update_params_json(&params_json) {
                    warn!("Failed to load params for {}: {}", strategy.name(), e);
                }
            }
        }
    }
    // No config file = strategies run with compiled defaults (safe fallback)
}
```

**Pipeline 構造（event_consumer.rs）**：
```rust
// 舊代碼（硬編碼，加新策略要改 N 處）：
// pipeline.orchestrator.register(Box::new(MaCrossover::new()));
// pipeline.orchestrator.register(Box::new(BbReversion::new()));
// ...

// 新代碼（一行，加新策略只改 StrategyFactory）：
for strategy in StrategyFactory::create_all() {
    pipeline.orchestrator.register(strategy);
}
load_strategy_params(&mut pipeline.orchestrator, deps.pipeline_kind);
```

**Agent 調參流程（已有機制，不需改動）**：
```
Agent → IPC UpdateStrategyParams { engine: "paper", strategy: "ma_crossover", params: {...} }
      → 路由到 Paper Pipeline 的 Orchestrator
      → find_strategy_mut("ma_crossover").update_params_json(...)
      → 只影響 Paper 實例，Demo/Live 不受影響

PromotionPipeline（6-01~03 已建）：
  Paper 參數驗證通過 → 複製到 strategy_params_demo.toml
  Demo 參數驗證通過 → 複製到 strategy_params_live.toml
```

**關鍵保證**：
1. **加新策略**：只改 `StrategyFactory::create_all()` + 策略模組本身（兩處）
2. **改策略邏輯**：只改 `strategies/xxx.rs`（一處）
3. **調策略參數**：Agent IPC / TOML 配置（per-engine 獨立）
4. **策略 promotion**：PromotionPipeline 自動搬運驗證過的參數
5. **Pipeline 代碼**：永遠不需要知道有哪些策略或它們怎麼工作

### D9: JS Edge 估計 per-engine 隔離（審查 FM-C1 修正）

**問題**：Paper 用激進參數（低 confidence、關閉 regime filter）產生的 fill 數據，與 Live 嚴格參數下的交易行為屬於**不同的數據生成過程 (DGP)**。共享 JS 估計會讓 Paper 的高頻低質交易拉偏 Live 的 edge 判斷。

**方案**：`EdgeEstimator` per-engine 獨立實例：
```rust
pub struct PerEngineEdgeEstimates {
    pub paper: Arc<RwLock<EdgeEstimates>>,
    pub demo:  Arc<RwLock<EdgeEstimates>>,
    pub live:  Arc<RwLock<EdgeEstimates>>,
}
```
- 每個 Pipeline 的 `js_estimates` 指向自己的實例
- DB 查詢按 `WHERE engine_mode = $1` 過濾輸入數據
- Paper 的 edge 估計只影響 Paper 的 cost_gate 決策
- Live 的 edge 估計只基於 Live 歷史交易（最保守、最準確）
- Demo 啟動時如果自身數據不足，可選擇從 Paper 估計**只讀複製初始值**（一次性 bootstrap，不持續同步）

### D10: Fan-out Bounded Channel + 背壓保護（審查 BB-C3 修正）

**現狀**：當前 event channel 已是 bounded `mpsc::channel(4096)`（`main.rs:39,561`），但這是單管線的點對點 channel。三引擎需要 1→N fan-out，每條 fan-out leg 各自 bounded：
```rust
let (event_tx_paper, event_rx_paper) = mpsc::channel(1024);  // bounded
let (event_tx_demo, event_rx_demo) = mpsc::channel(1024);
let (event_tx_live, event_rx_live) = mpsc::channel(512);     // Live 更小 buffer，更早預警

// Fan-out with lag detection
tokio::spawn(async move {
    while let Some(event) = ws_event_rx.recv().await {
        for (name, tx) in &senders {
            match tx.try_send(event.clone()) {
                Ok(()) => {},
                Err(TrySendError::Full(_)) => {
                    warn!("{name} pipeline lagging — dropping tick");
                    // 可選：累計 lag 計數，超閾值觸發 Cautious
                }
                Err(TrySendError::Closed(_)) => {
                    // Pipeline 已退出，正常
                }
            }
        }
    }
});
```

### D11: 阻塞式初始化（審查 BB-C5 修正）

策略實例創建和參數加載必須在 Pipeline 開始接收 WsEvent **之前**完成：
```rust
async fn run_event_consumer(deps: EventConsumerDeps) {
    // Phase 1: 阻塞式初始化（無 tick 流入）
    let mut pipeline = TickPipeline::with_kind(deps.pipeline_kind, ...);
    for strategy in StrategyFactory::create_all() {
        pipeline.orchestrator.register(strategy);
    }
    load_strategy_params(&mut pipeline.orchestrator, deps.pipeline_kind);
    // Phase 2: 初始化完成，才開始消費 event_rx
    while let Some(event) = deps.event_rx.recv().await { ... }
}
```
這消除了 `create_all()` 默認參數 → `load_strategy_params()` 覆蓋之間的窗口期。Live Pipeline 不會用 Paper 默認參數下單。

### D12: RwLock 類型統一（審查 FA-H2 修正）

**風險**：`std::sync::RwLock` 在持鎖方 panic 時 poison，導致其他 Pipeline 級聯崩潰。

**強制規則**：所有跨 Pipeline 共享的 `Arc<RwLock<T>>` 必須使用 `parking_lot::RwLock`（不 poison）或 `tokio::sync::RwLock`。開工前審計現有代碼：
```bash
grep -rn "std::sync::RwLock" rust/openclaw_engine/src/ rust/openclaw_core/src/
```
如有 `std::sync::RwLock` 用於共享資源 → 替換為 `parking_lot::RwLock`。

**S0 審計結果（2026-04-11）**：8 處 `std::sync::RwLock` 用法，全部在 `openclaw_engine`：
- `main.rs:525` — `Arc<RwLock<EdgeEstimates>>`（跨 Pipeline 共享市場數據 → **需替換**）
- `main.rs:1003` — `RwLock<HashMap<...>>`（mode_states → 3E-4 清除時一併處理）
- `account_manager.rs:12` — `RwLock<AccountManager>`（per-engine → 不需替換）
- `scanner/runner.rs:54,68` — `Arc<RwLock<EdgeEstimates>>`（共享 → **需替換**）
- `instrument_info.rs:12` — `RwLock<InstrumentInfoCache>`（跨 Pipeline 共享 → **需替換**）
- `event_consumer/types.rs:82-83` — `bybit_balance` + `api_pnl`（per-engine → 不需替換）
- `openclaw_core` — 零 `std::sync::RwLock`。

**結論**：3 處需在 S5（D12 實施步驟）替換為 `parking_lot::RwLock`：EdgeEstimates、InstrumentInfoCache。

### D13: 回滾安全策略（審查 PA-H3 修正）

3E-1 **不立即刪除** `TradingMode` / `mode_states` / `set_trading_mode()`。而是：
1. 3E-1：新增 `PipelineKind` + `GovernanceProfile`，`#[deprecated]` 標記舊 API
2. 3E-2a/2b：新代碼使用 `PipelineKind`，舊代碼 `#[allow(deprecated)]` 保留
3. 3E-4：所有新代碼驗證通過後，才統一移除舊代碼

任意階段都可以 `git revert` 回到單引擎，不會陷入半遷移態。

### D14: 共享 REST Rate Limiter（審查 BB-H5 修正）

Demo + Live Reconciler 各自輪詢 Bybit REST API。加上 health check、balance fetch、order placement，同 IP 的 REST 請求密度可能觸發 429。

**方案**：統一 REST 調用層持有 `Arc<RateLimiter>`（G-5 已實現），Reconciler 的 REST 調用必須經過此 limiter。跨 Pipeline 共享同一個 limiter 實例。

### D15: 全局資本敞口上限（審查 FM-H6 修正）

每個引擎有獨立 P1 cap，但缺跨引擎組合級限制。Paper 用 Demo 餘額（相同資金池）時，Demo + Paper 同時滿倉 = 名義敞口 2× 帳戶餘額。

**方案**：新增 `global_notional_cap_usdt` 配置（`risk_config.toml` 頂層）。IntentProcessor 在 P1 cap 檢查後，額外查詢所有 Pipeline 的 total_exposure（通過共享 `Arc<AtomicU64>` 累計）。超過全局上限 → 拒絕。

**例外**：Paper 的本地模擬倉位不計入全局敞口（因為不佔用真實資金）。只有 Demo + Live 的 exchange-mode 倉位計入。

### D16: Paper P0 硬限不可關閉（審查 CC-M6 修正）

Paper 的 GovernanceProfile::Exploration 跳過 authorization 和 lease，但以下 P0 硬限**永遠生效**，不因 profile 寬鬆而關閉：
- `position_size_max_pct`（單倉上限）
- `total_exposure_max_pct`（總曝險上限）
- `leverage_max`（槓桿上限）
- `session_drawdown_max_pct`（回撤熔斷）

這些硬限從 `risk_config_paper.toml` 讀取，值可以比 Live 寬鬆（如 drawdown 50%），但不可設為 0 或 disabled。

### D17: Live Pipeline 優先級保護（審查 CC-M7 修正）

三引擎共享 tokio runtime。如果 Paper 的激進探索（25 symbols × 4 strategies = 100 潛在併發 intent）佔滿 CPU，可能拖慢 Live tick 處理。

**方案**：Live Pipeline 的 on_tick SLA 不可降級。實現選項：
- 選項 A：Live Pipeline 使用獨立 `tokio::Runtime`（`Runtime::new()` 而非共享 default runtime）
- 選項 B：Paper/Demo 的 tick 處理加 `tokio::task::yield_now()` 週期性讓出（簡單但效果有限）
- **推薦選項 A**：開銷可忽略（一個額外 runtime ~幾 KB），隔離效果最好

### D18: 單一寫入口定義澄清（審查 CC-M5）

原則 #1「單一寫入口」的範圍是 **per-Bybit-account**：每個 Bybit 帳戶最多一條 Pipeline 寫入。
- Demo Pipeline → Demo 帳戶（唯一寫入者）
- Live Pipeline → Live 帳戶（唯一寫入者）
- D2 衝突偵測確保不會兩條管線對同一帳戶下單
- Paper Pipeline 無交易所寫入（本地模擬）→ 不違反

### D19: DB 去重寫入（審查 E5-O2）

market_data / features / ob_aggregator 是相同市場數據，三管線不應重複寫。
- `market_data_tx` / `feature_tx` 只在 Paper Pipeline 啟用（Paper 永遠在線）
- Demo/Live Pipeline 設 `market_data_tx = None`
- trading_tx（intents/fills/positions）per-engine 隔離是正確的
- 預估節省：DB 寫入量 -40%

### D20: Arc\<WsEvent\> 替代 clone（審查 E5-O3）

Fan-out 時 `WsEvent` 改為 `Arc<WsEvent>` 廣播：
```rust
let event = Arc::new(event);
for tx in &senders {
    let _ = tx.try_send(Arc::clone(&event));  // 引用計數，非深拷貝
}
```
當前 `PriceEvent` 只有 `String + f64 + i64`（clone ~100ns），開銷極小。但此改動為未來擴展到 OrderBook depth 等大結構預做準備。

### D21: Private WS per-engine 隔離（v4 新增 — 嚴格審查 GAP-1 修正）

**問題**：計劃架構圖標註了 Demo/Live 各有 private WS，但原始實施步驟未涵蓋。當前系統只有一個 `BybitPrivateWs` supervisor（`main.rs:1100-1158`），綁定一組 API key。三引擎後 Demo 和 Live 各自連不同 Bybit 帳戶，各自需要獨立的 private WS 接收自己帳戶的 fill/order/position 更新。

**影響**：如果不做這步，exchange pipeline 只能靠 Reconciler 30s REST 輪詢感知訂單成交，完全無法滿足 <1s fill 確認 SLA。**這是三引擎方案能否工作的基礎**。

**方案**：
```rust
// 每個 exchange pipeline 持有自己的 private WS supervisor
pub struct PerEnginePrivateWs {
    // Paper: None（無真實訂單）
    // Demo: BybitPrivateWs(demo_key, demo_secret, Demo env)
    // Live:  BybitPrivateWs(live_key, live_secret, Live env)
    ws: Option<BybitPrivateWs>,
    supervisor_handle: Option<JoinHandle<()>>,
}

// 事件路由：每個 private WS 的 event_tx 直連對應 pipeline
// Demo private WS → demo_private_event_tx → Demo pipeline on_private_event()
// Live private WS → live_private_event_tx → Live pipeline on_private_event()
// 絕不跨 pipeline（一個帳戶的 fill 不能觸發另一個 pipeline 的狀態變更）
```

**與 D14 Rate Limiter 的關係**：private WS 是長連接（無 REST rate limit 影響）。但 WS 重連時的 auth 請求仍走 REST，需經過共享 rate limiter。

**歸入 3E-2b 實施**。

### D22: PipelineCommand 統一命名（v4 新增 — 嚴格審查 GAP-3 修正）

**問題**：`PaperSessionCommand` 在三引擎語境下語義錯誤 — Demo/Live pipeline 的 command channel 也用此 enum，但名字暗示只用於 Paper。`paper_cmd_tx` 命名同理。

**方案**：3E-1 階段統一 rename：
```
PaperSessionCommand  →  PipelineCommand
paper_cmd_tx         →  pipeline_cmd_tx
paper_cmd_rx         →  pipeline_cmd_rx
```

純機械替換（`sed`），不改邏輯。在 `#[deprecated]` TradingMode 的同一步完成，避免半新半舊命名。

### D23: Reconciler per-engine 雙實例化（v4 新增 — 嚴格審查 GAP-4 修正）

**問題**：當前 `run_position_reconciler()` 單實例（`main.rs:1604-1611`），clone 同一個 `paper_cmd_tx`。三引擎後 Demo 和 Live 各自有獨立 Bybit 帳戶需要獨立 Reconciler。

**方案**：
```rust
// Demo Reconciler
if demo_pipeline_active {
    let demo_reconciler = Reconciler::new(
        demo_bybit_client.clone(),       // REST → api-demo.bybit.com
        pipeline_cmd_tx_demo.clone(),     // 升降級命令 → Demo pipeline
        instrument_cache.clone(),
        demo_risk_level_reader,           // 讀 Demo pipeline 的 risk level
        rate_limiter.clone(),             // 共享 D14 rate limiter
    );
    tokio::spawn(run_position_reconciler(demo_reconciler, "demo", ...));
}

// Live Reconciler
if live_pipeline_active {
    let live_reconciler = Reconciler::new(
        live_bybit_client.clone(),        // REST → api.bybit.com 或 api-demo
        pipeline_cmd_tx_live.clone(),      // 升降級命令 → Live pipeline
        instrument_cache.clone(),
        live_risk_level_reader,
        rate_limiter.clone(),             // 同一個 limiter（同 IP）
    );
    tokio::spawn(run_position_reconciler(live_reconciler, "live", ...));
}
```

每個 Reconciler 實例擁有獨立的 `ReconcilerState`（baseline / drift_streak / clean_cycles / cooldown timers），互不干擾。V014 audit 事件按 `engine_mode` 標記。

### D24: StopManager / PositionManager REST 綁定（v4 新增 — 嚴格審查 GAP-2 修正）

**問題**：StopManager 通過 REST client 向 Bybit 設置條件止損單。當前只有一個 REST client。三引擎後每個 exchange pipeline 的 StopManager 必須操作正確的帳戶。

**方案**：`EventConsumerDeps` 已有 `bybit_client: Option<Arc<BybitRestClient>>`。確保：
1. `StopManager::new()` 接受 `Option<Arc<BybitRestClient>>` 參數（Paper 傳 None → 本地模擬止損）
2. `StopManager::set_trading_stop()` 使用構造時綁定的 client（不引用全局單例）
3. PositionManager 同理 — 通過構造時注入的 client 與正確帳戶交互

**開工前必做**：
```bash
# 確認 StopManager 和 PositionManager 如何獲取 REST client
grep -n "BybitRestClient\|bybit_client\|rest_client" \
  rust/openclaw_engine/src/stop_manager.rs \
  rust/openclaw_engine/src/position_manager.rs
```

### D25: DB 連接池容量（v4 新增 — 嚴格審查 GAP-5 修正）

**問題**：三 pipeline + 兩 reconciler + scanner 同時寫 DB。D19 減少 market_data 重複寫入（-40%），但 trading 寫入（intents/fills/positions）從 1× 變 3×。

**方案**：
- 3E-2b 實施時檢查 `PgPool` max_connections 設定
- 建議 max_connections ≥ 20（當前可能為 10）
- 每個 pipeline 的 DB writer task 限併發（如 `Semaphore(5)`），避免一個 pipeline 獨佔 pool

### D26: GovernanceCore 多實例安全（v4 新增 — 嚴格審查 GAP-6 修正）

**問題**：計劃用 `GovernanceCore::new_with_profile()` per-engine 創建三個實例。需確認 GovernanceCore 是否持有共享全局狀態（如 GovernanceHub 單例引用），否則 Paper/Demo 的 auto-grant 可能意外修改 Live 的授權狀態。

**開工前必做**：
```bash
# 確認 GovernanceCore 是否引用全局 singleton
grep -n "static\|lazy_static\|OnceCell\|GOVERNANCE" \
  rust/openclaw_engine/src/governance*.rs rust/openclaw_core/src/governance*.rs
```

**要求**：每個 GovernanceCore 實例必須完全獨立（獨立 SM-1 授權狀態、獨立 SM-2 租約追蹤）。如果現有實現有共享全局狀態，3E-2a 必須先重構為 per-instance 狀態。

**S0 審計結果（2026-04-11）**：✅ **確認安全**。`governance_core.rs`（openclaw_core）無 `static`/`lazy_static`/`OnceCell`/`GOVERNANCE` 全局引用。`GovernanceCore::new()` 是純實例方法，所有狀態（SM-1/SM-2/SM-4）存在 struct fields 中。三引擎各自 `new_with_profile()` 不會互相干擾。`openclaw_engine/src/` 下亦無 governance 相關全局狀態。

---

## 五、實施計劃（分 9 個子任務）

### 3E-1：`PipelineKind` + `GovernanceProfile` 枚舉（Rust 基礎）

**目標**：建立不可變的管線身份枚舉 + 治理分層枚舉，替換全局可切換的 `TradingMode`。

**新增 `PipelineKind`（在 `tick_pipeline.rs` 頂部）**：
```rust
/// Immutable pipeline identity — baked in at construction, never changes.
/// 不可變管線身份 — 構造時固定，永不更改。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PipelineKind {
    Paper,
    Demo,
    Live,
}
impl PipelineKind {
    pub fn db_mode(&self) -> &'static str {
        match self { Self::Paper => "paper", Self::Demo => "demo", Self::Live => "live" }
    }
    pub fn is_exchange(&self) -> bool { matches!(self, Self::Demo | Self::Live) }
    pub fn governance_profile(&self) -> GovernanceProfile {
        match self {
            Self::Paper => GovernanceProfile::Exploration,
            Self::Demo  => GovernanceProfile::Validation,
            Self::Live  => GovernanceProfile::Production,
        }
    }
}
```

**新增 `GovernanceProfile`（在 `governance.rs` 或新文件）**：
```rust
/// Governance strictness tier — determines which gates are active.
/// 治理嚴格程度 — 決定哪些 gate 啟用。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GovernanceProfile {
    /// Paper: auto-grant auth, no lease, exploration cost_gate, lenient Guardian.
    Exploration,
    /// Demo: auto-grant auth, no lease, moderate cost_gate, moderate Guardian.
    Validation,
    /// Live: full auth + lease + strict cost_gate + strict Guardian.
    Production,
}
impl GovernanceProfile {
    pub fn requires_authorization(&self) -> bool { matches!(self, Self::Production) }
    pub fn requires_lease(&self) -> bool { matches!(self, Self::Production) }
    pub fn cost_gate_mode(&self) -> CostGateMode { ... }
}
```

**TickPipeline 修改**：
- 新增 `pipeline_kind: PipelineKind`（不可變，無 setter）
- 新增 `governance_profile: GovernanceProfile`（從 pipeline_kind 派生）
- `trading_mode` / `mode_states` / `set_trading_mode()` 等舊 API：**`#[deprecated]` 標記但保留**（D13 回滾安全）
- 3E-4 才統一移除

**PipelineCommand 統一命名**（D22）：
```bash
# 同步 rename — 純機械替換，不改邏輯
# PaperSessionCommand → PipelineCommand
# paper_cmd_tx → pipeline_cmd_tx
# paper_cmd_rx → pipeline_cmd_rx
sed -i 's/PaperSessionCommand/PipelineCommand/g' rust/openclaw_engine/src/**/*.rs
sed -i 's/paper_cmd_tx/pipeline_cmd_tx/g' rust/openclaw_engine/src/**/*.rs
sed -i 's/paper_cmd_rx/pipeline_cmd_rx/g' rust/openclaw_engine/src/**/*.rs
# 同步 Python 側引用
grep -rn "PaperSessionCommand\|paper_cmd" program_code/ --include="*.py"
```

**開工前必做**（審查 PA-H4）：
```bash
# 統計受影響測試數量，確認 3E-1 scope 包含測試改造
grep -rn "TradingMode\|set_trading_mode\|mode_states\|active_modes" \
  rust/openclaw_engine/src/ --include="*.rs" | grep "#\[test\]\|fn test_" | wc -l
```

**估算規模**：~+60 行（新 enum，舊代碼保留不刪）

---

### 3E-2a：單 Pipeline 構造函數重構 + StrategyFactory（event_consumer + tick_pipeline）

**目標**：讓 `run_event_consumer()` 接受 `PipelineKind` + 對應資源，構造完全自足的 Pipeline。策略通過 Factory 統一注入，Pipeline 不關心有哪些策略。

**`StrategyFactory` 新增**（`strategies/mod.rs`）：
```rust
pub struct StrategyFactory;
impl StrategyFactory {
    /// Single registration point — add/remove strategies here ONLY.
    /// 策略唯一註冊點 — 新增/移除策略只改這裡。
    pub fn create_all() -> Vec<Box<dyn Strategy>> {
        vec![
            Box::new(MaCrossover::new()),
            Box::new(BbReversion::new()),
            Box::new(BbBreakout::new()),
            Box::new(GridTrading::new_adaptive()),
        ]
    }
}
```

**`EventConsumerDeps` 重構**：
```rust
pub struct EventConsumerDeps {
    pub pipeline_kind: PipelineKind,
    pub initial_balance: f64,
    pub bybit_client: Option<Arc<BybitRestClient>>,  // None for Paper（★ StopManager/PositionManager 通過此 client 操作正確帳戶 D24）
    pub private_ws_rx: Option<mpsc::Receiver<PrivateWsEvent>>,  // ★ D21: per-engine private WS 事件接收
    pub risk_config: Arc<ConfigStore<RiskConfig>>,    // per-engine
    pub risk_governor: RiskGovernorSm,                // per-engine, 獨立實例
    pub stop_manager: StopManager,                    // per-engine, 綁定對應 bybit_client（D24）
    pub governance_core: GovernanceCore,              // per-engine, 完全獨立實例（D26，無共享全局狀態）
    pub reconciler: Option<Reconciler>,               // None for Paper（★ D23: per-engine 獨立實例）
    pub event_rx: mpsc::Receiver<Arc<WsEvent>>,       // ★ bounded fan-out（D10），Arc<WsEvent>（D20）
    pub cmd_rx: mpsc::UnboundedReceiver<PipelineCommand>,  // ★ D22: renamed
    pub snapshot_path: PathBuf,                       // pipeline_snapshot_{kind}.json
    pub cancellation_token: CancellationToken,
    // ... 共享資源（Arc）
    pub instrument_cache: Arc<InstrumentInfoCache>,
    pub symbol_registry: Arc<parking_lot::RwLock<SymbolRegistry>>,  // ★ D12: parking_lot
    pub js_estimates: Arc<parking_lot::RwLock<EdgeEstimates>>,      // ★ D9: per-engine 隔離 + D12
    pub db_pool: Arc<PgPool>,                         // ★ D25: max_connections ≥ 20
}
```

**GovernanceCore 分層行為**（D26：每個實例完全獨立，無共享全局狀態）：
```rust
impl GovernanceCore {
    /// Creates a fully independent GovernanceCore for one pipeline.
    /// 為單條管線創建完全獨立的 GovernanceCore — 不引用全局 singleton。
    /// D26: 開工前必須 grep 確認無 static/lazy_static/OnceCell 共享狀態。
    pub fn new_with_profile(profile: GovernanceProfile) -> Self {
        let mut core = Self::new();  // 必須是全新實例，不是 clone 全局單例
        match profile {
            Exploration | Validation => {
                // Auto-grant authorization, no lease required
                core.grant_paper_authorization(None).unwrap();
            }
            Production => {
                // Full auth flow — operator must explicitly grant
            }
        }
        core.set_profile(profile);
        core
    }
}
```

**策略注入（event_consumer.rs 改造）**：
```rust
// 舊代碼（硬編碼 4 行，加新策略要改這裡）：
// pipeline.orchestrator.register(Box::new(MaCrossover::new()));
// pipeline.orchestrator.register(Box::new(BbReversion::new()));
// ...

// 新代碼（Pipeline 不知道也不關心有哪些策略）：
for strategy in StrategyFactory::create_all() {
    pipeline.orchestrator.register(strategy);
}
// 加載 per-engine 策略參數（見 3E-9）
load_strategy_params(&mut pipeline.orchestrator, deps.pipeline_kind);
```

**IntentProcessor 分層**（審查 FA-H1 展開）：

IntentProcessor 當前是平坦的 ~900 行 `process()` 函數。改造方式是新增 `profile: GovernanceProfile` 參數（不改 IntentProcessor struct，保持無狀態）：

```rust
// intent_processor.rs
pub fn process(
    &self, intent: &OrderIntent, gov: &GovernanceCore,
    state: &PaperState, atr: f64,
    profile: GovernanceProfile,  // 新增參數
) -> IntentResult {
    // 1. Authorization gate — skip for Exploration/Validation
    if profile.requires_authorization() && !gov.is_authorized() {
        return rejected("not authorized");
    }
    // 2. Guardian — always run, thresholds from per-engine RiskConfig（已自動適配）
    // 3. Kelly sizing — always run
    // 4. P1 cap — always run (limits from per-engine RiskConfig)
    // 5. Global notional cap — exchange-mode only（D15）
    if profile != GovernanceProfile::Exploration {
        check_global_notional_cap(...)?;
    }
    // 6. Cost gate — mode depends on profile
    match profile.cost_gate_mode() {
        CostGateMode::Exploration => self.cost_gate_exploration(strategy, symbol, atr, ...),
        CostGateMode::Moderate    => self.cost_gate_moderate(strategy, symbol, atr, ...),
        CostGateMode::Strict      => self.cost_gate_live(strategy, symbol, atr, ...),
    }
}

// cost_gate_moderate = 有 JS 估計時用 JS，無時 ATR gate（介於 exploration 和 strict 之間）
fn cost_gate_moderate(&self, ...) -> Option<IntentResult> {
    match js_estimate {
        Some(est) if est.shrunk_bps > 0.0 => None,  // 有正 edge → 放行
        Some(est) => Some(rejected("negative edge")),
        None => self.cost_gate_atr_fallback(...),     // 無估計 → ATR gate（不是探索模式放行）
    }
}
```

**調用點**（`tick_pipeline.rs`）：`proc.process(intent, gov, state, atr, self.governance_profile)`

**估算規模**：~+280 / -80 行（含 StrategyFactory + IntentProcessor 改造）

---

### 3E-2b：三管線並行啟動 + 條件式啟動 + 錯誤隔離（`main.rs`）

**目標**：`main.rs` 按條件 spawn 1~3 個 `run_event_consumer()` 實例，互不影響。含 per-engine private WS（D21）、per-engine Reconciler（D23）、DB pool 調整（D25）。

**條件式啟動邏輯**（整合 D1/D10/D11/D12/D13/D17/D21/D23/D25 修正）：
```rust
// ── API Key 讀取（一次性，避免 TOCTOU）──
let demo_keys = read_api_keys("demo");  // Option<(String, String)>
let live_keys = read_api_keys("live");  // Option<(String, String)>

// ── API Key 衝突偵測（hard block，不是警告）──
if let (Some((dk, _)), Some((lk, _))) = (&demo_keys, &live_keys) {
    if dk == lk {
        error!("Demo and Live slots have identical API key — \
               refusing to start both. Remove one or use different keys.");
        // 只啟動 Demo Pipeline，不啟動 Live（保守）
        live_keys = None;
    }
}

// ── Market data fan-out（bounded channel + Arc<WsEvent>）──
let (event_tx_paper, event_rx_paper) = mpsc::channel(1024);   // bounded
let mut senders: Vec<(&str, mpsc::Sender<Arc<WsEvent>>)> = vec![("paper", event_tx_paper)];

// ── DB Pool 容量（D25）──
let db_pool = PgPoolOptions::new()
    .max_connections(20)  // ★ 三 pipeline + 雙 reconciler + scanner（原 10 不夠）
    .connect(&db_url).await?;

// ── Paper Pipeline: 永遠啟動 ──
let paper_balance = match &demo_keys {
    Some(_) => fetch_demo_balance(&demo_client).await.unwrap_or(default_balance),
    None => paper_config.initial_balance_usdt,  // GUI 配置值
};
let paper_handle = tokio::spawn(run_pipeline(PipelineKind::Paper, paper_balance, ...));

// ── Demo Pipeline: 需要 demo slot 有 API key ──
let demo_handle = if let Some((key, secret)) = demo_keys.clone() {
    let demo_client = BybitRestClient::new(BybitEnvironment::Demo, Some(key.clone()), Some(secret.clone()))?;
    match demo_client.get_wallet_balance().await {
        Ok(bal) => {
            let (tx, rx) = mpsc::channel(1024);  // bounded
            senders.push(("demo", tx));

            // ★ D21: Demo private WS（獨立 supervisor，獨立 credentials）
            let (demo_priv_tx, demo_priv_rx) = mpsc::channel(256);
            let demo_priv_ws = BybitPrivateWs::new(
                key.clone(), secret.clone(), BybitEnvironment::Demo, demo_priv_tx,
            );
            let demo_priv_cancel = cancel.clone();
            tokio::spawn(private_ws_supervisor(demo_priv_ws, demo_priv_cancel, "demo"));

            // ★ D23: Demo Reconciler（獨立實例，持有 Demo cmd_tx + Demo REST client）
            let demo_reconciler = Reconciler::new(
                demo_client.clone(), pipeline_cmd_tx_demo.clone(),
                instrument_cache.clone(), demo_risk_level.clone(), rate_limiter.clone(),
            );
            tokio::spawn(run_position_reconciler(demo_reconciler, "demo", cancel.clone()));

            Some(tokio::spawn(run_pipeline(
                PipelineKind::Demo, bal, demo_client, rx,
                demo_priv_rx,  // ★ private WS 事件只進此 pipeline
                ...
            )))
        }
        Err(e) => {
            error!("Demo Pipeline: API key invalid or unreachable: {e} — skipped");
            None
        }
    }
} else {
    info!("Demo Pipeline: skipped (no API key)");
    None
};

// ── Live Pipeline: 需要 live slot 有自己的 key（不降級）──
let live_handle = if let Some((key, secret)) = live_keys {
    let live_env = live_bybit_environment();
    let live_client = BybitRestClient::new(live_env, Some(key.clone()), Some(secret.clone()))?;
    match live_client.get_wallet_balance().await {
        Ok(bal) => {
            let (tx, rx) = mpsc::channel(512);  // bounded，更小 buffer
            senders.push(("live", tx));

            // ★ D21: Live private WS（獨立 supervisor，獨立 credentials）
            let (live_priv_tx, live_priv_rx) = mpsc::channel(256);
            let live_priv_ws = BybitPrivateWs::new(
                key.clone(), secret.clone(), live_env, live_priv_tx,
            );
            // Note: Live WS supervisor 也在獨立 runtime 上運行（D17）
            let live_priv_cancel = cancel.clone();

            // ★ D23: Live Reconciler（獨立實例）
            let live_reconciler = Reconciler::new(
                live_client.clone(), pipeline_cmd_tx_live.clone(),
                instrument_cache.clone(), live_risk_level.clone(), rate_limiter.clone(),
            );

            // Live 使用獨立 tokio Runtime（D17 優先級保護）
            let live_rt = tokio::runtime::Builder::new_multi_thread()
                .worker_threads(2).enable_all().build()?;
            Some(std::thread::spawn(move || {
                live_rt.block_on(async {
                    // Private WS + Reconciler + Pipeline 全在 Live runtime 上
                    tokio::spawn(private_ws_supervisor(live_priv_ws, live_priv_cancel, "live"));
                    tokio::spawn(run_position_reconciler(live_reconciler, "live", cancel.clone()));
                    run_pipeline(PipelineKind::Live, bal, live_client, rx, live_priv_rx, ...).await
                })
            }))
        }
        Err(e) => {
            error!("Live Pipeline: API key invalid: {e} — skipped");
            None
        }
    }
} else {
    info!("Live Pipeline: skipped (no API key in live slot)");
    None
};

// ── Fan-out task（bounded + lag detection + Arc）──
tokio::spawn(async move {
    while let Some(event) = ws_event_rx.recv().await {
        let event = Arc::new(event);
        for (name, tx) in &senders {
            match tx.try_send(Arc::clone(&event)) {
                Ok(()) => {},
                Err(TrySendError::Full(_)) => {
                    warn!("{name} pipeline lagging — dropping tick");
                }
                Err(TrySendError::Closed(_)) => {}  // pipeline exited
            }
        }
    }
});

// ── Graceful shutdown（有序：Live → Demo → Paper）──
let cancel = CancellationToken::new();
tokio::select! {
    _ = signal::ctrl_c() => {
        cancel.cancel();
        // 有序 shutdown：Live 先 drain+flush（數據最重要）
        if let Some(h) = live_handle { let _ = h.join(); }
        if let Some(h) = demo_handle { let _ = h.await; }
        let _ = paper_handle.await;
    }
}
```

**阻塞式初始化**（D11）：每個 Pipeline 的 `run_event_consumer()` 內部，先完成策略創建 + 參數加載，**才開始消費** `event_rx`。見 D11 偽碼。

**Private WS 事件處理**（D21）：每個 exchange pipeline 的主循環需要同時 `select!` market data event_rx 和 private_ws_rx：
```rust
tokio::select! {
    Some(market_event) = event_rx.recv() => { pipeline.on_tick(market_event); }
    Some(priv_event) = private_ws_rx.recv() => { pipeline.on_private_event(priv_event); }
    Some(cmd) = cmd_rx.recv() => { pipeline.handle_command(cmd); }
    _ = cancel.cancelled() => { break; }
}
```

**錯誤隔離 + 三級遞減**（D6）：
- 每個 `tokio::spawn` 內部 catch panic + log
- `PipelineHealth` atomic 狀態（Running / Down / Paused）
- 跨引擎通知 channel：Paper crash → Demo Cautious；Demo crash → Live Cautious
- 所有共享 `RwLock` 使用 `parking_lot`（D12，不 poison）

**估算規模**：main.rs ~+450 / -100 行（含 D21 private WS spawn + D23 dual reconciler + D25 pool）

---

### 3E-3：IPC Server 三管線路由（`ipc_server.rs`）

**目標**：IPC 命令按 `engine` 參數精確路由到對應管線的 channel。

**`EngineCommandChannels` 替換 `pipeline_cmd_tx`**（D22 命名）：
```rust
pub struct EngineCommandChannels {
    pub paper: Option<mpsc::UnboundedSender<PipelineCommand>>,
    pub demo:  Option<mpsc::UnboundedSender<PipelineCommand>>,
    pub live:  Option<mpsc::UnboundedSender<PipelineCommand>>,
}
impl EngineCommandChannels {
    pub fn select(&self, engine: &str) -> Option<&mpsc::UnboundedSender<PipelineCommand>> {
        match engine {
            "demo" => self.demo.as_ref(),
            "live" => self.live.as_ref(),
            _      => self.paper.as_ref(),
        }
    }
    /// Returns list of active engine names.
    pub fn active_engines(&self) -> Vec<&'static str> {
        let mut v = Vec::new();
        if self.paper.is_some() { v.push("paper"); }
        if self.demo.is_some() { v.push("demo"); }
        if self.live.is_some() { v.push("live"); }
        v
    }
}
```

**快照路由**：
- `data_dir/pipeline_snapshot_paper.json`
- `data_dir/pipeline_snapshot_demo.json`
- `data_dir/pipeline_snapshot_live.json`
- `get_paper_state?engine=paper/demo/live` → 讀對應快照文件
- 新增 `get_engine_health` → 返回三個 Pipeline 的健康狀態

**移除 IPC 命令**：`add_engine_mode` / `switch_engine_mode`

**估算規模**：~-80 / +80 行

---

### 3E-4：`TradingMode` + `EngineConfig` 完整清除（Rust）

**目標**：從 Rust 代碼和 TOML 配置中完全移除 `TradingMode`。

**`config/mod.rs`**：
- 移除 `pub enum TradingMode { PaperOnly, Demo, Live }`
- 移除 `EngineConfig::trading_mode` 字段
- 移除 hot-reload cold 警告邏輯

**TOML 配置文件清除**：
- `engine.toml`：移除 `trading_mode = ...` 行（三引擎後每個 Pipeline 身份固定）
- `engine_demo.toml` / `engine_live.toml`：如存在，同步清除

**其他 Rust 文件**：
- `bybit_rest_client.rs`：移除 `secret_slot()` 對 TradingMode 的引用
- `mode_state.rs`：簡化為 Pipeline 的內部狀態容器（移除 TradingMode 引用）

**估算規模**：~-120 行

---

### 3E-5：Python 側清除 + 性能指標隔離

**目標**：移除 Python 中 `trading_mode` 邏輯 + 所有 metrics 端點 per-engine 隔離。

**開工前必做**（審查 PA-M4）：Python 有 ~35 處 `trading_mode` 引用（集中在 `live_session_routes.py` ~27 處），下面只列主要 4 文件。開工前跑全量 grep 確認完整範圍：
```bash
grep -rn "trading_mode" program_code/ --include="*.py" | wc -l
```

**`live_session_routes.py`**：
- 移除 `_get_trading_mode_from_engine()` 函數
- `get_session_status()` 返回：
  - 移除 `"trading_mode"` 字段
  - 保留 `"system_mode"` 字段
  - 新增 `"active_engines": ["paper", "demo", "live"]`（從 IPC 讀取）

**性能指標隔離**：
- `GET /api/v1/{engine}/metrics`（engine = paper/demo/live）
- SQL 查詢全部加 `WHERE engine_mode = $1`
- `compute_full_metrics()` 接受 `engine_mode` 參數
- Sharpe / drawdown / win_rate / holding_period 各自獨立計算

**`paper_trading_routes.py`**：
- 移除 `trading_mode` 字段
- `/api/v1/paper/metrics` → 固定 `engine_mode = 'paper'`

**`ipc_state_reader.py`**：
- 移除按 `trading_mode` 路由邏輯
- 改為讀 `pipeline_snapshot_{engine}.json`

**估算規模**：Python ~-80 / +100 行

---

### 3E-6：Sidebar + GUI 顯示清理

**目標**：UI 完全不出現 `trading_mode`，Sidebar 顯示 `system_mode` + 活躍引擎列表。

**`console.html` `refreshSidebar()`**：
```javascript
const systemMode = d.system_mode || 'unknown';
modeEl.textContent = systemMode.replace(/_/g, ' ');

// 顯示活躍引擎
const engines = d.active_engines || [];
engineListEl.textContent = engines.join(' / ');  // "paper / demo / live"
```

**模式顏色映射**：
```javascript
const modeColor = {
  live_reserved: '#a855f7',
  demo_reserved: '#3b82f6',
  shadow_only:   '#f59e0b',
  observe_only:  '#6b7280',
  design_only:   '#6b7280',
}[systemMode] || '';
```

**估算規模**：~+30 JS 行

---

### 3E-7：API Key 衝突偵測 + 啟動驗證（Settings + Rust）

**目標**：防止同一 API key 被兩個 Pipeline 同時使用。

**Python `settings_routes.py`**：
```python
@app.route("/api/v1/settings/api-key/<slot>", methods=["POST"])
async def update_api_key(slot):
    new_key = request.json["api_key"]
    other_slot = "live" if slot == "demo" else "demo"
    existing_key = read_secret_file(other_slot, "api_key")
    if existing_key and existing_key == new_key:
        return jsonify({"error": f"API key conflicts with {other_slot} slot"}), 409
    # ... proceed with save
```

**Rust 啟動驗證**（`main.rs`）：
- Live Pipeline 啟動時先 `GET /v5/account/wallet-balance` health check
- 401/403 → 標記 key 無效，不啟動 Pipeline（log error），不 panic
- Demo Pipeline 同理

**估算規模**：Python ~+30 / Rust ~+40 行

---

### 3E-8：Watchdog + Paper 初始餘額 GUI

**目標**：watchdog 支持多 Pipeline 監控 + Paper 頁面可配置初始餘額。

**Watchdog 升級**（`helper_scripts/canary/engine_watchdog.py`）：
```python
SNAPSHOT_FILES = [
    "pipeline_snapshot_paper.json",
    "pipeline_snapshot_demo.json",
    "pipeline_snapshot_live.json",
]
# 分別檢查每個快照的 freshness
# 報告格式：Paper: OK / Demo: STALE (45s) / Live: N/A (not running)
```

**Paper 初始餘額 GUI**：
- `tab-paper.html`：新增 "Initial Balance (USDT)" 輸入框
- `POST /api/v1/paper/config` → 寫入 `settings/paper_config.toml`
- 字段：`initial_balance_usdt`（默認 10000.0）
- 僅在無 Demo API key 時使用

**估算規模**：Python ~+60 / JS ~+30 行

---

### 3E-9：Per-Engine 策略參數配置 + 參數加載器

**目標**：每個 Pipeline 從自己的配置文件加載策略參數，Agent 調參寫回對應文件。

**新增配置文件**：
```
settings/strategy_params_paper.toml   # 寬參數範圍，激進探索
settings/strategy_params_demo.toml    # 中等範圍，驗證中的策略
settings/strategy_params_live.toml    # 窄範圍，生產固定值
```

**TOML 格式**：
```toml
# strategy_params_paper.toml — 探索模式
[ma_crossover]
cooldown_ms = 180000       # 更短冷卻，允許更頻繁交易
adx_threshold = 15.0       # 更低門檻，更多信號
regime_filter_enabled = false  # 關閉 regime filter，探索更多場景
conf_scale = 1.0

[bb_reversion]
cooldown_ms = 300000
use_limit = false
conf_scale = 1.0

[bb_breakout]
cooldown_ms = 300000
squeeze_bw = 0.015
expansion_bw = 0.035
conf_scale = 1.0

[grid_trading]
cooldown_ms = 60000
max_inventory = 5
conf_scale = 1.0
```

**參數加載器**（`strategies/mod.rs` 或新文件 `strategies/factory.rs`）：
```rust
/// Load per-engine strategy params from TOML config.
/// 從 per-engine TOML 配置加載策略參數。
/// Missing file = use compiled defaults (safe). Missing section = skip that strategy.
pub fn load_strategy_params(orchestrator: &mut Orchestrator, kind: PipelineKind) {
    let path = strategy_params_path(kind);
    let config = match std::fs::read_to_string(&path) {
        Ok(s) => s,
        Err(_) => {
            info!("{kind}: no strategy params file at {path:?}, using defaults");
            return;
        }
    };
    let table: toml::Table = match config.parse() {
        Ok(t) => t,
        Err(e) => { warn!("{kind}: invalid strategy params TOML: {e}"); return; }
    };
    for strategy in orchestrator.strategies_mut() {
        let name = strategy.name().to_lowercase().replace(' ', "_");
        if let Some(section) = table.get(&name) {
            let json = serde_json::to_string(section).unwrap_or_default();
            match strategy.update_params_json(&json) {
                Ok(()) => info!("{kind}/{name}: params loaded from config"),
                Err(e) => warn!("{kind}/{name}: param load failed: {e}"),
            }
        }
    }
}

fn strategy_params_path(kind: PipelineKind) -> PathBuf {
    let dir = std::env::var("OPENCLAW_SETTINGS_DIR")
        .unwrap_or_else(|_| "settings".into());
    PathBuf::from(dir).join(format!("strategy_params_{}.toml", kind.db_mode()))
}
```

**IPC 參數持久化（可選，Phase 2）**：
Agent 通過 IPC `UpdateStrategyParams` 動態調參後，可選擇持久化回 TOML：
```
UpdateStrategyParams { engine: "paper", strategy: "ma_crossover", params: {...}, persist: true }
→ 更新內存中的策略實例
→ 同時寫回 strategy_params_paper.toml 對應 section
```

**與 PromotionPipeline 的接口**：
PromotionPipeline（6-01~03）在 promote 時：
1. 讀取源引擎的 strategy params（如 `strategy_params_paper.toml [ma_crossover]`）
2. 寫入目標引擎的 strategy params（如 `strategy_params_demo.toml [ma_crossover]`）
3. 發 IPC `UpdateStrategyParams` 通知目標 Pipeline 熱重載

**估算規模**：Rust ~+100 行 + 3 個 TOML 配置文件

---

## 六、實施時序與依賴圖

```
3E-1 PipelineKind + GovernanceProfile + PipelineCommand rename (D22)
  ↓
3E-9 StrategyFactory + per-engine params ←── 3E-3 IPC 三管線路由
  ↓
3E-2a 單 Pipeline 構造重構（含 Factory 注入 + D24 REST 綁定 + D26 GovernanceCore 驗證）
  ↓
3E-2b 三管線並行啟動 + D21 private WS + D23 dual reconciler + D25 DB pool
  ↓
3E-4 TradingMode 完整清除（Rust 收尾）
  ↓
3E-5 Python 清除 + 性能指標隔離
  ↓
3E-6 Sidebar GUI 清理（可提前獨立做）

3E-7 API Key 衝突偵測（可與 3E-2b 並行）
3E-8 Watchdog + Paper GUI（可與 3E-5 並行）
```

**3E-6 可以現在立即做**（無後端依賴，只改 JS）。
**3E-7/3E-8 可與主線並行**。
**3E-1 → 3E-9 → 3E-2a → 3E-2b → 3E-4 → 3E-5 是關鍵路徑**。
**3E-9 排在 3E-2a 之前**，因為 Pipeline 構造重構需要 Factory 先就位。
**3E-1 和 3E-9 不可並行**（PA-M1：3E-9 的 `load_strategy_params()` 依賴 3E-1 的 `PipelineKind` 枚舉）。
**3E-2b 是最大風險點**（v4 新增 D21/D23/D25，拆為 3 sub-days：α 骨架 / β private WS / γ reconciler+隔離）。

---

## 七、工作量估算與建議排期

| 任務 | Rust LOC | Python/JS LOC | 風險 |
|------|---------|---------------|------|
| 3E-1 PipelineKind + Profile + PipelineCommand rename（D22） | +60 / -0（rename 淨零） | — | 低 |
| 3E-9 StrategyFactory + params | +100 | +3 TOML files | 低 |
| 3E-2a Pipeline 構造 + IntentProcessor 分層 + D24/D26 驗證 | +320 / -80 | — | 高（治理分層 + REST 綁定） |
| 3E-2b 三管線啟動 + private WS(D21) + dual reconciler(D23) + pool(D25) | +450 / -100 | — | **最高**（新增 D21/D23/D25） |
| 3E-3 IPC 路由 | -80 / +80 | — | 中 |
| 3E-4 TradingMode 完整清除（含 deprecated 舊代碼） | -300 | — | 低（收尾） |
| 3E-5 Python 清除 + 指標隔離（~35 處 trading_mode） | — | -120 / +120 | 中 |
| 3E-6 Sidebar 修正 | — | +30 JS | 低 |
| 3E-7 Key 衝突偵測（hard block） | +40 | +30 | 低 |
| 3E-8 Watchdog + Paper GUI | — | +90 | 低 |
| **總計** | **~+490 淨增**（v3: +370） | **~+150** | — |

**建議排期**：W22（2026-05-05~12）—— **8 天**（v4：+1 天，D21/D23 增加 3E-2b 工作量）。
**建議執行方式**：
- Day 1: 3E-1（枚舉 + deprecated + PipelineCommand rename D22）→ 3E-9（Factory，依賴 3E-1）+ 3E-6（並行）
- Day 2: 3E-2a（IntentProcessor 改造 + D24 REST 綁定驗證 + D26 GovernanceCore 獨立性驗證）
- Day 3: 3E-2b-α（單管線→多管線 spawn + fan-out + D25 DB pool）
- Day 4: 3E-2b-β（D21 per-engine private WS supervisor + 事件路由接線）
- Day 5: 3E-2b-γ（D23 dual reconciler + 條件啟動 Demo/Live + 錯誤隔離）+ 3E-3（並行）+ 3E-7（並行）
- Day 6: 3E-4（TradingMode 清除）→ 3E-5 + 3E-8（並行）
- Day 7: E2 代碼審查 → E4 測試回歸
- Day 8: Buffer / QA / 修復 E2 發現的問題

---

## 八、Live API Key 補充說明

Live Pipeline **不框死主網**，但**必須有自己的 key**（不降級到 demo slot）：

**路徑 A：Live slot 有 key，且 key ≠ Demo slot key**
- 讀 `bybit_endpoint` metadata → 決定 Mainnet / LiveDemo
- 使用 live slot credentials
- Mainnet：`api.bybit.com`（真實資金）
- LiveDemo：`api-demo.bybit.com`（live 路徑 + demo 伺服器）

**路徑 B：Live slot 無 key**
- Live Pipeline 不啟動
- Log: "Live Pipeline: skipped (no API key in live slot)"

**路徑 C：Live slot key == Demo slot key**
- **拒絕啟動 Live Pipeline**（同帳戶衝突保護，D2）
- Error log: "Live and Demo use same API key — refusing to start Live"

**如何測試 Live 路徑**：在 Settings GUI 為 live slot 配置一組**不同於 demo slot 的** demo API key，設 `bybit_endpoint=demo`。這樣 Demo Pipeline 用一組 key，Live Pipeline 用另一組 key，各自連 demo server，互不衝突。

---

## 九、測試策略

- **3E-1**：現有 879 lib tests 全部必須繼續通過（舊 API deprecated 但保留，不破壞）
- **3E-9**：StrategyFactory::create_all() 返回正確數量 + load_strategy_params 各場景（有文件/無文件/畸形文件）
- **3E-2a**：
  - GovernanceProfile 單元測試（3 profile × authorization/lease/cost_gate 行為）
  - Exploration profile: `requires_authorization()` = false, cost_gate 走 exploration
  - Validation profile: `requires_authorization()` = false, cost_gate 走 moderate
  - Production profile: `requires_authorization()` = true, cost_gate 走 strict
  - IntentProcessor 新增 `profile` 參數的 3 條路徑各有 assert
  - `cost_gate_moderate` 的 3 個分支（正 JS / 負 JS / 無 JS → ATR gate）
- **3E-2b**：
  1. Paper/Demo/Live 並行 tick，各自 DB engine_mode 正確
  2. 無 Demo key → 只 Paper 啟動，balance = 配置值
  3. Demo key == Live key → **hard block**，Live 不啟動（非 warning）
  4. Live slot 無 key → Live 不啟動（無降級）
  5. Bounded channel 背壓測試：慢消費者 → tick 被 drop + warning log
  6. 三級遞減收縮：Paper crash → Demo Cautious / Live 不受影響
  7. 有序 shutdown：Live 先 flush，Paper 最後
- **3E-3**：IPC `engine=paper/demo/live` 路由測試（各 2 場景）
- **3E-4~5**：
  - 回歸 — 無編譯錯誤 + Python tests pass
  - 全量 `grep "trading_mode"` 確認零殘留（Rust + Python）
- **3E-7**：API key 衝突偵測 409 測試
- **3E-8**：Watchdog multi-snapshot 測試
- **D12**：開工前審計 `grep "std::sync::RwLock"` — 共享資源必須用 `parking_lot`（現有 4 處需遷移）
- **D15**：全局 notional cap 測試（Demo+Live 總曝險超限 → 拒絕）
- **D9**：per-engine JS 估計隔離測試（Paper 交易數據不影響 Live 的 edge 計算）
- **D21**（v4 新增）：
  1. Demo private WS 事件只路由到 Demo pipeline（不進 Live）
  2. Live private WS 事件只路由到 Live pipeline（不進 Demo）
  3. Private WS 斷線重連不影響其他 pipeline
  4. Paper pipeline 不持有 private WS（`private_ws_rx = None`）
- **D22**（v4 新增）：`grep "PaperSessionCommand\|paper_cmd"` 確認零殘留
- **D23**（v4 新增）：
  1. Demo Reconciler 對賬 Demo 帳戶倉位（不觸發 Live 動作）
  2. Live Reconciler 對賬 Live 帳戶倉位（不觸發 Demo 動作）
  3. 兩個 Reconciler 共享 rate limiter 但各自冷卻狀態獨立
- **D24**（v4 新增）：Demo StopManager 通過 Demo REST client 設止損（非 Live client）
- **D25**（v4 新增）：DB pool max_connections ≥ 20 + 三管線無連接飢餓
- **D26**（v4 新增）：三個 GovernanceCore 實例互不影響（Paper auto-grant 不改 Live 狀態）
- **總目標**：遷移後測試基線不降 + 新增 ~40 tests（v3: ~30，v4 新增 D21-D26 場景）

---

## 十、六角色審查追蹤矩陣

所有審查發現及其在計劃中的對應修正：

| ID | 來源 | 嚴重度 | 問題 | 修正位置 | 狀態 |
|---|---|---|---|---|---|
| C1 | FM+BB | Critical | JS Edge 估計跨引擎污染 | D9 | ✅ 已整合 |
| C2 | BB | Critical | Live fallback Demo key 同帳戶衝突 | D1+§八 | ✅ 已整合（取消降級） |
| C3 | BB | Critical | Fan-out unbounded_channel OOM | D10 | ✅ 已整合 |
| C4 | CC | Critical | 原則 #6 違反（失敗無收縮） | D6 | ✅ 已整合（三級遞減） |
| C5 | BB | Critical | create_all→load_params 間隙 | D11 | ✅ 已整合 |
| H1 | FA | High | IntentProcessor 改造未展開 | 3E-2a | ✅ 已整合 |
| H2 | FA | High | RwLock poison 級聯崩潰 | D12 | ✅ 已整合 |
| H3 | PA | High | 回滾策略缺失 | D13+3E-1 | ✅ 已整合 |
| H4 | PA | High | 半遷移測試風險 | 3E-1 開工前 grep | ✅ 已整合 |
| H5 | BB | High | 雙 Reconciler rate limit | D14 | ✅ 已整合 |
| H6 | FM | High | 無全局資本敞口上限 | D15 | ✅ 已整合 |
| H7 | FM | High | Promotion 統計無效性 | D4 附註 | ✅ 已整合 |
| M1 | PA | Medium | 3E-9 依賴 3E-1（不可並行） | §六 | ✅ 已整合 |
| M2 | PA | Medium | 3E-2b 需再拆分 | §七 Day 3/4 | ✅ 已整合 |
| M3 | PA+FA | Medium | 5天過於樂觀 | §七 → 7天 | ✅ 已整合 |
| M4 | PA | Medium | Python 46 處引用低估 | 3E-5 grep 前置 | ✅ 已整合 |
| M5 | CC | Medium | 原則 #1 寫入口定義 | D18 | ✅ 已整合 |
| M6 | CC | Medium | Paper P0 硬限不可關閉 | D16 | ✅ 已整合 |
| M7 | CC | Medium | Live 優先級保護 | D17 | ✅ 已整合 |
| M8 | BB | Medium | Shutdown 無序 DB 污染 | D6 有序 shutdown | ✅ 已整合 |
| O1 | E5 | Opt | 共享指標計算層（CPU -60%） | — | ⬜ W23 follow-up |
| O2 | E5 | Opt | DB 去重寫入（-40% I/O） | D19 | ✅ 已整合 |
| O3 | E5 | Opt | Arc\<WsEvent\> 替代 clone | D20 | ✅ 已整合 |
| O4 | E5 | Opt | Paper 降頻 tick | — | ❌ 不實施（破壞 promotion 數據一致性） |

### v4 嚴格審查新增修正

| ID | 來源 | 嚴重度 | 問題 | 修正位置 | 狀態 |
|---|---|---|---|---|---|
| G1 | v4 審查 | **Critical** | Private WS per-engine 缺失 — 無 fill 確認 SLA | D21 + 3E-2b | ✅ 已整合 |
| G2 | v4 審查 | **Critical** | StopManager/PositionManager REST client 未綁定 | D24 + 3E-2a | ✅ 已整合 |
| G3 | v4 審查 | Medium | PaperSessionCommand 命名矛盾 | D22 + 3E-1 | ✅ 已整合 |
| G4 | v4 審查 | Medium | Reconciler 雙實例化細節缺失 | D23 + 3E-2b | ✅ 已整合 |
| G5 | v4 審查 | Medium | DB 連接池容量不足 | D25 + 3E-2b | ✅ 已整合 |
| G6 | v4 審查 | Medium | GovernanceCore 多實例安全未驗證 | D26 + 3E-2a | ✅ 已整合 |
| A1 | v4 審查 | 校正 | D10 前提錯誤（已是 bounded 4096，非 unbounded） | D10 描述修正 | ✅ 已校正 |
| A2 | v4 審查 | 校正 | 策略數 5→4（FundingRateArb 未啟用） | D4 描述修正 | ✅ 已校正 |
| A3 | v4 審查 | 校正 | Python trading_mode 引用數 46→35 | §二/3E-5 修正 | ✅ 已校正 |
| A4 | v4 審查 | 校正 | EdgeEstimates 已有部分 per-component 隔離 | D9 描述不變（仍需 per-engine） | ✅ 已知 |

**未整合 follow-up**（排入 W23）：
- **E5-O1**：共享指標計算層（KlineManager+IndicatorEngine 拆為 shared actor）— 收益最大（CPU -60%）但改動面大，需獨立 Sprint

---

*文件結束 / End of document*
