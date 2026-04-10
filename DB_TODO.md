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
| Orchestrator（策略） | **共享代碼，每模式執行** | 策略 Close 依賴持倉狀態（per-mode），Open 信號邏輯一致但需 per-mode 持倉上下文 |
| PaperState（餘額/持倉） | **分離** | 獨立資金管理 |
| IntentProcessor | **分離** | 每模式有自己的風控門 |
| GovernanceCore | **分離** | 獨立熔斷器（各自 AtomicBool） |
| StopManager | **分離** | 止損觸發依賴持倉狀態 |
| LinUCB | **共享 Arc，per-mode arm_selection** | 初期共享模型，long-term 可分離 |
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

- `is_paper` 列**僅存在於 3 個表**：`trading.orders`、`trading.fills`、`trading.position_snapshots`（均 DEFAULT FALSE）。保留（向後兼容 Grafana），加 DEPRECATED 注釋。Rust writer 中 fills 和 position_snapshots 當前硬編碼 `is_paper = true`，Phase 2a 改為派生自 `engine_mode != "live"`。orders 目前無 writer，待實現時同理。
- 為每個表添加 `(engine_mode, ts DESC)` 索引
- 歷史數據自動通過 `DEFAULT 'paper'` 標記，無需 backfill
- 不按 `engine_mode` 做 TimescaleDB 分區（表已是 hypertable，交易數據量 <100 行/天，WHERE engine_mode = ? 過濾足夠，分區帶來的 chunk 管理複雜度遠超收益）

**可獨立部署 ✅**

---

### Phase 2a: Rust DB Writer — 傳遞 engine_mode `[ ]`

**已有 writer 的表（4 個）：**

- `rust/openclaw_engine/src/database/mod.rs`
  - `TradingMsg::Intent` — 新增 `engine_mode: String`
  - `TradingMsg::Fill` — 新增 `engine_mode: String`
  - `TradingMsg::PositionSnapshot` — 新增 `engine_mode: String`
  - `TradingMsg::Signal` — 不改（共享）
  - `DecisionContextMsg` — 新增 `engine_mode: String`

- `rust/openclaw_engine/src/database/trading_writer.rs`
  - `flush_intents()` — INSERT 加 `engine_mode`
  - `flush_fills()` — INSERT 加 `engine_mode`，`is_paper` 派生自 `engine_mode != "live"`
  - `flush_positions()` — INSERT 加 `engine_mode`，`is_paper` 同上派生

- `rust/openclaw_engine/src/database/context_writer.rs`
  - `flush_contexts()` — INSERT 加 `engine_mode`

**⚠️ 尚無 writer 的表（5 個 — 審計發現）：**

| 表 | Writer 狀態 | 處理方式 |
|----|------------|---------|
| `trading.risk_verdicts` | ❌ 不存在 | 未來實現 writer 時直接帶 engine_mode |
| `trading.orders` | ❌ 不存在 | 同上（Paper 模式不產生 orders） |
| `trading.order_state_changes` | ❌ 不存在 | 同上（跟隨 orders） |
| `trading.decision_outcomes` | ❌ 不存在（outcomes 寫入 `learning.directive_executions`） | outcome_tracker.rs 未來改寫時帶 engine_mode |
| `agent.ai_invocations` | ❌ 不存在 | 未來 AI 成本追蹤實現時帶 engine_mode |

**結論：** Phase 2a 只需改已有的 4 個 Rust writer。5 個無 writer 的表在 Phase 1 加列後通過 DEFAULT 'paper' 處理，待 writer 實現時自然帶入 engine_mode。無需 Phase 2b。

**可與 Phase 1 一起部署 ✅** — 所有行寫入 `engine_mode = 'paper'`

---

### Phase 3: Rust Engine — Per-Mode State (ModeState) `[ ]`

**核心變更：** `tick_pipeline.rs`

新增結構體：
```rust
pub struct ModeState {
    pub paper_state: PaperState,
    pub intent_processor: IntentProcessor,
    pub governance: GovernanceCore,          // 每模式獨立 atomic（非共享 Arc）
    pub risk_store: Arc<ConfigStore<RiskConfig>>,
    pub stop_manager: StopManager,           // 止損依賴持倉狀態，必須 per-mode
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
  4. fan-out 價格到所有 ModeState:
     for mode in active_modes:
       mode_states[mode].paper_state.update_prices(shared_prices)

  // === 每模式階段 ===
  for mode in active_modes:
    ms = mode_states[mode]
    5. sync_risk_config（該模式的 risk_store）
    6. 策略 dispatch → StrategyAction（共享 Orchestrator 代碼，但傳入該模式的持倉上下文）
    7. intent_processor 處理（該模式的風控閾值）
    8. apply_fill → 該模式的 PaperState
    9. 發送 TradingMsg { engine_mode: mode.to_str() }
   10. check_stops → 該模式的 StopManager（止損依賴持倉狀態）
```

**不是 3 個管線。** 指標/信號計算（昂貴）做一次。Intent/fill 處理（廉價，<100次/天）做 3 次。

**最高風險項** — tick_pipeline.rs 2400+ 行重構。子問題清單：

1. **GovernanceCore 多實例** — `GovernanceCoreWrapper` 使用 `Arc<AtomicBool>` 共享 `session_halted`。per-mode 實例化需要各自獨立的 atomic，確認 `openclaw_core::GovernanceCore` 支持多實例。
2. **IntentProcessor 構造分支** — Live 模式需 `AccountManager`（連真實交易所），Paper 為 None。`kelly_config`、`edge_estimates` 也需 per-mode 初始化。
3. **StopManager** — 計劃表格未提及，但止損觸發依賴持倉狀態，**必須 per-mode**。加入 ModeState。
4. **LinUCB 決策** — `IntentProcessor` 包含 `linucb: Option<Arc<LinUcbRuntime>>`。LinUCB 從 fills 學習，fills 是 per-mode 的。**初期方案：LinUCB Arc 共享（所有模式用同一模型），`last_arm_selection` per-mode。** 長期可考慮 per-mode 獨立學習。
5. **PaperState.latest_prices** — 來自共享市場數據，需在共享階段後 fan-out 到所有 ModeState（步驟 4）。

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
| Ph2a: Rust DB Writers | `rust/.../database/mod.rs`, `trading_writer.rs`, `context_writer.rs`（僅 4 已有 writer） | ✅ (與 Ph1 一起) |
| Ph3: ModeState | `rust/.../tick_pipeline.rs`, `stop_manager.rs`, `main.rs`, `event_consumer/mod.rs` | 需 Ph2a |
| Ph4: IPC + Python | `rust/.../ipc_server.rs`, `ipc_state_reader.py`, `*_routes.py` | 需 Ph3 |
| Ph5: Strategy Params | 未來 | 需 Ph4 |

**預估總工時：~25-35 小時**

---

## 驗證計劃

1. **Ph1+2a 部署後：** 檢查新數據行有 `engine_mode = 'paper'`，舊數據也標記 `'paper'`；確認 `is_paper` 在 fills/positions 正確派生
2. **Ph3 部署後：** 配置 `active_modes = ["paper", "demo"]`，驗證兩模式 PaperState 獨立（不同餘額、不同持倉、不同止損狀態）
3. **Ph4 部署後：** GUI Paper tab 和 Live tab 各自顯示對應模式數據
4. **回歸：** `cargo test --lib` + Python pytest

---

## 審計備註（2026-04-10 審計發現）

1. **5 個表無 writer：** `trading.risk_verdicts`、`trading.orders`、`trading.order_state_changes`、`trading.decision_outcomes`、`agent.ai_invocations` 在整個 codebase 中無 INSERT 實現（MIT 審計已記錄）。Phase 1 加列無害（DEFAULT 處理），writer 實現時自然帶入 engine_mode。
2. **`trading.decision_outcomes` 特殊情況：** outcome 數據實際寫入 `learning.directive_executions`（outcome_tracker.rs），非 `trading.decision_outcomes`。Phase 1 仍加列以備未來正確接線。
3. **`is_paper` 硬編碼現狀：** `trading_writer.rs` 中 `flush_fills()` line 256 和 `flush_positions()` line 308 均硬編碼 `is_paper = true`。Phase 2a 必須改為動態派生。
