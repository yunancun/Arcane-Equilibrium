# DB TODO — Multi-Engine Data Separation (Paper / Demo / Live)
# 多引擎數據分離方案
# 最後更新：2026-04-10
#
# ⚠ 歷史術語注意：本文寫於 3E-ARCH 完成前，文中 `TradingMode` 已由 `PipelineKind` 取代（2026-04-11 commit 0f3af65）。

---

## 2026-07-05 剩餘工作核實 / Closure Overlay

本輪核實結論：本文不再包含可直接從此歷史 TODO 派工的剩餘工作。
原 5-phase 目標已完成或被後續 3E-ARCH / 3E-4 架構取代：

- `engine_mode` schema/writer 分離已落地；`is_paper` 兼容列現由
  `engine_mode != "live"` 派生。
- 舊的單 `TickPipeline` 內 `mode_states` / `active_modes` fan-out 設計已被
  per-pipeline 架構取代：每條管線以不可變 `PipelineKind` 啟動，並擁有自己的
  `TickPipeline`、`Orchestrator`、strategy instances、state、risk/governance
  和 DB `effective_engine_mode()` 標籤。
- Phase 5 strategy params 已完成為 per-engine TOML loader：
  `load_strategy_params(PipelineKind)` + `StrategyFactory::create_for_engine(...)`。
- 舊審計中的 `trading.decision_outcomes` / `agent.ai_invocations` 無 writer
  判斷已過期；當前分別有 Rust outcome backfiller 與 Python
  `AgentEventStore.record_ai_invocation()` writer。

若未來要重做「共享市場/指標計算一次，再 fan-out 到多個獨立管線」以節省算力，
那是新的架構需求，必須從根 `TODO.md` / ADR / PM dispatch 重開；不能從本文
直接當作未完成項處理。

---

## 背景

本文原始背景（2026-04-10）：系統需要同時運行 Paper / Demo / Live
三種模式，當時除 RiskConfig（`PerEngineRiskStores`）外，引擎狀態和數據庫
尚未完成模式隔離。後續 3E-ARCH / 3E-4 已改為 per-pipeline 隔離架構。

**核心原則：市場數據保留一份，只在有差異的地方分離**，避免 3x 數據膨脹。

## 當前狀態審計

| 層級 | 分離狀態 | 說明 |
|------|---------|------|
| **Risk Config** | ✅ 已完成 | `PerEngineRiskStores` 3 獨立 ConfigStore，IPC 路由按 engine 參數選擇 |
| **Rust 引擎實例** | ✅ 完成 / superseded | 3E-4 移除 `mode_states` / `active_modes`；現行是每個 `PipelineKind` 對應獨立 `TickPipeline::with_kind(...)` 實例與獨立 `Orchestrator` |
| **數據庫** | ✅ 完成 | V015 遷移 + 當前 writer/backfiller 路徑傳遞 `engine_mode`（Phase 1+2a） |
| **策略參數** | ✅ 完成 | `settings/strategy_params_{paper,demo,live}.toml` + Rust `load_strategy_params(PipelineKind)` 已提供 per-engine 變體；缺檔/壞檔對 Demo/Live fail-closed。 |
| **IPC 狀態** | ✅ 完成 | `get_paper_state(engine=)` + `get_mode_snapshot` + `get_active_modes`（Phase 4） |

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

### Phase 1: DB Schema — V015 Migration `[x]`

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

### Phase 2a: Rust DB Writer — 傳遞 engine_mode `[x]`

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

**歷史 writer 審計（2026-07-05 更新）：**

| 表 | Writer 狀態 | 處理方式 |
|----|------------|---------|
| `trading.risk_verdicts` | 需在新任務中重審 | 不從本文直接派工；若新增/修改 writer，必須在當前根 `TODO.md` 流程下驗證 `engine_mode` |
| `trading.orders` | ✅ Rust writer 路徑存在 | `trading_writer.rs` 寫入 `engine_mode`，兼容 `is_paper` 由 `engine_mode != "live"` 派生 |
| `trading.order_state_changes` | 需在新任務中重審 | 跟隨 orders 的當前需求需另開根 TODO/PA 審計 |
| `trading.decision_outcomes` | ✅ Rust backfiller 存在 | `database/outcome_backfiller.rs` `INSERT INTO trading.decision_outcomes ... engine_mode` |
| `agent.ai_invocations` | ✅ Python event-store writer 存在 | `AgentEventStore.record_ai_invocation(..., engine_mode=...)` 寫入 `agent.ai_invocations` |

**結論：** 原 Phase 2a 已是歷史完成項。上表只保留舊審計演進脈絡；
若要重審 risk/order-state writer，必須作為新的根 TODO 任務進入現行治理流程。

**歷史部署結論：** Phase 2a 可與 Phase 1 一起部署；後續 runtime 已演進為
per-pipeline `effective_engine_mode()` 標籤。

---

### Phase 3: Rust Engine — Per-Mode State (ModeState historical design) `[x / superseded]`

> 2026-07-05 audit：下方 `ModeState` / `mode_states` HashMap 是歷史方案。
> 3E-4 已移除 `mode_states` / `active_modes`；現行 runtime 使用每個
> `PipelineKind` 一個獨立 `TickPipeline` 的 per-pipeline 架構。每條管線
> 自己持有 `paper_state`、`intent_processor`、`governance`、`stop_manager`、
> `orchestrator` 與 strategy instances。下文保留作設計脈絡，不是當前待辦。

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

**歷史方案不是 3 個管線；現行方案已改為獨立 per-pipeline runtime。**
如果未來要重新追求「指標/信號只計算一次」再 fan-out 到多個 pipeline，
那是新的性能/架構需求，不是本文剩餘待辦。

**歷史最高風險項** — 2026-04-10 當時預估為 tick_pipeline.rs 2400+ 行重構。
下列子問題保留作設計脈絡，非當前派工清單：

1. **GovernanceCore 多實例** — `GovernanceCoreWrapper` 使用 `Arc<AtomicBool>` 共享 `session_halted`。per-mode 實例化需要各自獨立的 atomic，確認 `openclaw_core::GovernanceCore` 支持多實例。
2. **IntentProcessor 構造分支** — Live 模式需 `AccountManager`（連真實交易所），Paper 為 None。`kelly_config`、`edge_estimates` 也需 per-mode 初始化。
3. **StopManager** — 計劃表格未提及，但止損觸發依賴持倉狀態，**必須 per-mode**。加入 ModeState。
4. **LinUCB 決策** — `IntentProcessor` 包含 `linucb: Option<Arc<LinUcbRuntime>>`。LinUCB 從 fills 學習，fills 是 per-mode 的。**初期方案：LinUCB Arc 共享（所有模式用同一模型），`last_arm_selection` per-mode。** 長期可考慮 per-mode 獨立學習。
5. **PaperState.latest_prices** — 來自共享市場數據，需在共享階段後 fan-out 到所有 ModeState（步驟 4）。

---

### Phase 4: IPC + Python Side `[x]`

- `ipc_server.rs` — `PipelineSnapshot` 新增 `mode_snapshots: HashMap<String, ModeSnapshot>`
- IPC `get_paper_state` 接受可選 `engine` 參數（默認 "paper" 向後兼容）
- `ipc_state_reader.py` — `get_paper_state(mode="paper")` 參數化
- `paper_trading_routes.py` → `get_paper_state("paper")`
- `live_session_routes.py` → `get_paper_state("live")` 或 `get_paper_state("demo")`

---

### Phase 3 已知限制（2026-07-05 核實：已被 3E-4 取代）

舊限制成立於「同一 `TickPipeline` 內對多個 mode 反覆調用同一個
`Orchestrator`」的方案：strategy 內部狀態可能互相污染。

現行代碼已移除該路徑：`pipeline_kind` 在 `TickPipeline::with_kind(...)`
構造時固定，沒有 runtime `set_trading_mode()`；bootstrap 透過
`StrategyFactory::create_for_engine(pipeline_kind, ...)` 為該管線註冊 strategy
instances。因此 per-mode strategy **instance** 隔離已由 per-pipeline 架構
滿足。若未來要在「共享計算一次」的前提下重新 fan-out 到多個 Orchestrator，
必須以新根 TODO/ADR 重開。

---

### Phase 5: Per-Mode Strategy Params `[x]`

已落地為 TOML-backed per-engine strategy params，而不是新增 `PerEngineStrategyParams`
store type。現行權威路徑：

- `settings/strategy_params_paper.toml`
- `settings/strategy_params_demo.toml`
- `settings/strategy_params_live.toml`
- `rust/openclaw_engine/src/strategies/params.rs::load_strategy_params(kind)`
- `rust/openclaw_engine/src/strategies/registry.rs::StrategyFactory::create_for_engine(kind, ...)`

原設想類型如下，保留作歷史設計草稿：
```rust
pub struct PerEngineStrategyParams {
    pub paper: Arc<ConfigStore<StrategyParamsBundle>>,
    pub demo: Arc<ConfigStore<StrategyParamsBundle>>,
    pub live: Arc<ConfigStore<StrategyParamsBundle>>,
}
```

驗證面：`rust/openclaw_engine/src/strategies/tests.rs` 覆蓋 per-engine TOML load、
Demo/Live missing/invalid TOML fail-closed inactive、Paper missing TOML default fallback，
並檢查真實三端 strategy params 中 `funding_arb.active=false` 與 `bb_breakout` 5m family。
Agent 自調參數仍由後續 promotion / IPC gate 管控；本 Phase 5 不授予 live mutation。

---

## 實施順序與關鍵文件

| 階段 | 關鍵文件 | 可獨立部署 |
|------|---------|-----------|
| Ph1: V015 Migration | `sql/migrations/V015__engine_mode_separation.sql` (新) | ✅ |
| Ph2a: Rust DB Writers | `rust/.../database/mod.rs`, `trading_writer.rs`, `context_writer.rs`（僅 4 已有 writer） | ✅ (與 Ph1 一起) |
| Ph3: ModeState / per-pipeline state | `rust/.../tick_pipeline.rs`, `stop_manager.rs`, `main.rs`, `event_consumer/mod.rs` | ✅ 已由 3E-4 per-pipeline 架構取代 |
| Ph4: IPC + Python | `rust/.../ipc_server.rs`, `ipc_state_reader.py`, `*_routes.py` | 需 Ph3 |
| Ph5: Strategy Params | `settings/strategy_params_{paper,demo,live}.toml`, `strategies/params.rs`, `strategies/registry.rs` | ✅ 已完成 |

**預估總工時：~25-35 小時**

---

## 歷史驗證計劃

本節是原 2026-04-10 驗證思路。現行 per-pipeline 架構驗證應以新的根
`TODO.md` 任務/測試計劃為準，不能按舊 `active_modes` 方案直接派工。

1. **Ph1+2a 部署後：** 檢查新數據行有 `engine_mode = 'paper'`，舊數據也標記 `'paper'`；確認 `is_paper` 在 fills/positions 正確派生
2. **歷史 Ph3：** 原計劃配置 `active_modes = ["paper", "demo"]` 驗證兩模式 PaperState 獨立；現行 3E-4 應改驗獨立 `PipelineKind` 管線、單一 `mode_snapshots[kind]`、以及 per-pipeline state 隔離。
3. **Ph4 部署後：** GUI Paper tab 和 Live tab 各自顯示對應模式數據
4. **回歸：** `cargo test --lib` + Python pytest

---

## 審計備註（2026-04-10 審計發現）

1. **5 個表無 writer（歷史審計已過期）：** `trading.orders`、`trading.decision_outcomes`、`agent.ai_invocations` 已有後續 writer/backfiller 證據；`trading.risk_verdicts`、`trading.order_state_changes` 如需重審，必須另走根 `TODO.md`。
2. **`trading.decision_outcomes` 特殊情況（已更新）：** 現有 `database/outcome_backfiller.rs` 會從 `trading.decision_context_snapshots` + `market.klines` 回填 `trading.decision_outcomes`，並寫入 `engine_mode`。
3. **`is_paper` 硬編碼現狀（已修正）：** `trading_writer.rs` 中 fills / position_snapshots / orders 的兼容 `is_paper` 值由 `engine_mode != "live"` 派生。
