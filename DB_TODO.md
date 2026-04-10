# DB TODO — Multi-Engine Data Separation (Paper / Demo / Live)
# 多引擎數據分離方案
# 最後更新：2026-04-10

---

## 背景

系統未來需要同時運行 Paper / Demo / Live 三種模式。當前除 RiskConfig（`PerEngineRiskStores`）外，引擎狀態和數據庫均無模式隔離。

**核心原則：市場數據保留一份，只在有差異的地方分離**，避免 3x 數據膨脹。

## 當前狀態審計

| 層級 | 分離狀態 | 說明 |
|------|---------|------|
| **Risk Config** | ✅ 已完成 | `PerEngineRiskStores` 3 獨立 ConfigStore，IPC 路由按 engine 參數選擇 |
| **Rust 引擎實例** | ❌ 缺失 | 單一 `TickPipeline`，單一 `PaperState`，切換模式共享狀態 |
| **數據庫** | ❌ 缺失 | `trading.signals/intents/fills/orders/position_snapshots` 均無 `engine_mode` 列 |
| **策略參數** | ❌ 缺失 | 全局一套，無 paper/demo/live 變體 |
| **IPC 狀態** | ❌ 缺失 | `get_paper_state` 返回唯一共享狀態，無模式過濾 |

---

## 核心設計：Signal Diamond

```
Market Data (共享 — 一份)
      ↓
Indicators (共享 — 計算一次)
      ↓
Signals (共享 — 一行/觸發)        ← 客觀市場觀察
    ╱   |   ╲
 Paper  Demo  Live               ← fan-out 分叉點
   |     |     |
Intents (每模式獨立 — 不同風控 → 不同倉位/拒絕)
   |     |     |
Fills / Orders / Positions (每模式獨立)
```

**關鍵洞察：Signal 是共享的（"RSI 在 BTCUSDT 下穿 30"是客觀事實），Intent 開始分叉（不同風控配置 → 不同倉位大小、不同拒絕決策）。**

## 數據量對比（為什麼不怕 3x）

| 層級 | 行數/天 | 大小/天 | 3x 後增量 |
|------|---------|---------|-----------|
| market.tickers | ~17K/symbol | ~50 MB | **不複製** |
| market.klines | ~288 | ~5 MB | **不複製** |
| trading.signals | ~10-100 | 微量 | **不複製（共享）** |
| trading.intents | ~10-100 | 微量 | +2x ≈ 微量 |
| trading.fills | ~5-50 | 微量 | +2x ≈ 微量 |
| trading.contexts | ~10-100 | ~1-10 MB | +2x ≈ 最多 20 MB |

**結論：per-mode 表的 3x 開銷 <1% of total DB writes，可忽略不計。**

---

## 共享 vs 分離 — 完整清單

| 層級 | 共享? | 原因 |
|------|-------|------|
| market.* (所有表) | 共享 | 客觀外部數據 |
| features.online_latest | 共享 | 指標緩存 |
| risk.* | 共享 | 市場級檢測 |
| trading.signals | 共享 | 客觀策略觸發 |
| trading.intents | **分離** | 風控配置不同 → 倉位/拒絕不同 |
| trading.risk_verdicts | **分離** | 不同風控 → 不同判決 |
| trading.orders/fills | **分離** | 模式獨立執行 |
| trading.position_snapshots | **分離** | 獨立持倉追蹤 |
| trading.decision_context* | **分離** | 快照含倉位狀態 |
| KlineManager / SignalEngine | 共享 | 計算一次 |
| Orchestrator（策略） | 共享 | 信號邏輯一致 |
| PaperState（餘額/持倉） | **分離** | 獨立資金管理 |
| IntentProcessor | **分離** | 每模式有自己的風控門 |
| GovernanceCore | **分離** | 獨立熔斷器 |
| RiskConfig | **已分離** | PerEngineRiskStores ✅ |

---

## 實施計劃（5 Phase）

### Phase 1: DB Schema — V015 Migration `[ ]`

新增 `engine_mode TEXT NOT NULL DEFAULT 'paper'` 列。Signal 表不加（共享）。

**文件：** `sql/migrations/V015__engine_mode_separation.sql`（新建）

| 表 | 變更 | 說明 |
|----|------|------|
| `trading.signals` | 不改 | 共享 — 客觀信號 |
| `trading.intents` | +`engine_mode` | 分叉起點 |
| `trading.risk_verdicts` | +`engine_mode` | 不同風控 → 不同判決 |
| `trading.orders` | +`engine_mode` | 模式獨立執行 |
| `trading.order_state_changes` | +`engine_mode` | 跟隨 orders |
| `trading.fills` | +`engine_mode` | 模式獨立成交 |
| `trading.position_snapshots` | +`engine_mode` | 模式獨立持倉 |
| `trading.decision_context_snapshots` | +`engine_mode` | 快照含倉位狀態 |
| `trading.decision_outcomes` | +`engine_mode` | 與 context 聯動 |
| `agent.ai_invocations` | +`engine_mode` (nullable) | AI 成本歸因 |

- 保留 `is_paper` 列（向後兼容 Grafana），加 DEPRECATED 注釋
- 為每個表添加 `(engine_mode, ts DESC)` 索引
- 歷史數據自動通過 `DEFAULT 'paper'` 標記，無需 backfill
- 不用分區（交易數據量 <100 行/天，分區複雜度遠超收益）

**可獨立部署 ✅**

---

### Phase 2: Rust DB Writer — 傳遞 engine_mode `[ ]`

**文件改動：**

- `rust/openclaw_engine/src/database/mod.rs`
  - `TradingMsg::Intent` — 新增 `engine_mode: String`
  - `TradingMsg::Fill` — 新增 `engine_mode: String`
  - `TradingMsg::PositionSnapshot` — 新增 `engine_mode: String`
  - `TradingMsg::Signal` — 不改（共享）
  - `DecisionContextMsg` — 新增 `engine_mode: String`

- `rust/openclaw_engine/src/database/trading_writer.rs`
  - `flush_intents()` — INSERT 加 `engine_mode`
  - `flush_fills()` — INSERT 加 `engine_mode`，`is_paper` 派生自 `engine_mode != "live"`
  - `flush_positions()` — INSERT 加 `engine_mode`

- `rust/openclaw_engine/src/database/context_writer.rs`
  - `flush_contexts()` — INSERT 加 `engine_mode`

**可與 Phase 1 一起部署 ✅** — 所有行寫入 `engine_mode = 'paper'`

---

### Phase 3: Rust Engine — Per-Mode State (ModeState) `[ ]`

**核心變更：** `tick_pipeline.rs`

新增結構體：
```rust
pub struct ModeState {
    pub paper_state: PaperState,
    pub intent_processor: IntentProcessor,
    pub governance: GovernanceCore,
    pub risk_store: Arc<ConfigStore<RiskConfig>>,
    pub recent_intents: VecDeque<TimestampedIntent>,
    pub recent_fills: VecDeque<TimestampedFill>,
    pub consecutive_losses: HashMap<String, u32>,
    pub session_halted: bool,
    pub paper_paused: bool,
}
```

TickPipeline 修改：
```rust
pub struct TickPipeline {
    // 共享（每 tick 計算一次）:
    pub kline_manager: KlineManager,
    pub signal_engine: SignalEngine,
    pub orchestrator: Orchestrator,
    // ...

    // 每模式獨立:
    mode_states: HashMap<TradingMode, ModeState>,
    active_modes: Vec<TradingMode>,
}
```

**on_tick 流程：**
```
on_tick(event):
  // === 共享階段 ===
  1. 更新價格、K線、指標（一次）
  2. 運行 signal_engine → Vec<Signal>（一次）
  3. 廣播信號到 DB（一次，無 engine_mode）

  // === 每模式階段 ===
  for mode in active_modes:
    4. sync_risk_config（該模式的 risk_store）
    5. 策略 dispatch → StrategyAction
    6. intent_processor 處理（該模式的風控閾值）
    7. apply_fill → 該模式的 PaperState
    8. 發送 TradingMsg { engine_mode: mode.to_str() }
    9. check_stops（該模式的止損配置）
```

**不是 3 個管線。** 指標/信號計算（昂貴）做一次。Intent/fill 處理（廉價，<100次/天）做 3 次。

**最高風險項** — tick_pipeline.rs 2400+ 行重構。

---

### Phase 4: IPC + Python Side `[ ]`

- `ipc_server.rs` — `PipelineSnapshot` 新增 `mode_snapshots: HashMap<String, ModeSnapshot>`
- IPC `get_paper_state` 接受可選 `engine` 參數（默認 "paper" 向後兼容）
- `ipc_state_reader.py` — `get_paper_state(mode="paper")` 參數化
- `paper_trading_routes.py` → `get_paper_state("paper")`
- `live_session_routes.py` → `get_paper_state("live")` 或 `get_paper_state("demo")`

---

### Phase 5: Per-Mode Strategy Params（未來）`[ ]`

複用 `PerEngineRiskStores` 模式：
```rust
pub struct PerEngineStrategyParams {
    pub paper: Arc<ConfigStore<StrategyParamsBundle>>,
    pub demo: Arc<ConfigStore<StrategyParamsBundle>>,
    pub live: Arc<ConfigStore<StrategyParamsBundle>>,
}
```

Phase 1-4 中策略參數全局共享，分叉在 intent 層。Agent 自調參數是後續工作。

---

## 實施順序與關鍵文件

| 階段 | 關鍵文件 | 可獨立部署 |
|------|---------|-----------|
| Ph1: V015 Migration | `sql/migrations/V015__engine_mode_separation.sql` (新) | ✅ |
| Ph2: DB Writers | `rust/.../database/mod.rs`, `trading_writer.rs`, `context_writer.rs` | ✅ (與 Ph1 一起) |
| Ph3: ModeState | `rust/.../tick_pipeline.rs`, `main.rs`, `event_consumer/mod.rs` | 需 Ph2 |
| Ph4: IPC + Python | `rust/.../ipc_server.rs`, `ipc_state_reader.py`, `*_routes.py` | 需 Ph3 |
| Ph5: Strategy Params | 未來 | 需 Ph4 |

**預估總工時：~25-35 小時**

---

## 驗證計劃

1. **Ph1+2 部署後：** 檢查新數據行有 `engine_mode = 'paper'`，舊數據也標記 `'paper'`
2. **Ph3 部署後：** 配置 `active_modes = ["paper", "demo"]`，驗證兩模式 PaperState 獨立
3. **Ph4 部署後：** GUI Paper tab 和 Live tab 各自顯示對應模式數據
4. **回歸：** `cargo test --lib` + Python pytest
