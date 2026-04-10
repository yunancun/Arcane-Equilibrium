# 三引擎並行架構遷移計劃 (3E-ARCH)
# Three-Engine Parallel Architecture Migration Plan

**作者 / Authors**: PM + PA + FA  
**日期 / Date**: 2026-04-11  
**優先級 / Priority**: P0 — 下一個主要開發週期首要任務  
**TODO 索引 / TODO ref**: 3E-1 ~ 3E-6  

---

## 一、執行摘要

當前系統使用「單一 TickPipeline + 模式切換」架構（Signal Diamond Phase 3 中間態）。用戶的目標是三個引擎（Paper / Demo / Live）**同時並行運行**，各自接入對應 API，各自寫入 DB，由 `system_mode` 統一治理哪些引擎被允許開單。

`trading_mode`（全局單值配置）是單引擎時代的遺物，在三引擎世界中無意義——每個管線的「模式」是它的固定身份，不是配置項。本計劃完整描述遷移路徑與 `trading_mode` 清除範圍。

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

**Python 側（46 處引用）**：

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
│   ├── 公共 WebSocket（market data fan-out → 三個 event_tx）
│   ├── IPC Server（統一端點，engine 參數路由命令）
│   ├── Scanner / SymbolRegistry（symbol universe 同步三個管線）
│   ├── InstrumentInfoCache（合約規格，共享）
│   └── NewsPipeline（共享，三個管線接收同一新聞快照）
│
├── ── Paper Pipeline ─────────────────────────────────────────
│   ├── pipeline_kind = PipelineKind::Paper（固定，不可更改）
│   ├── 無 REST client（本地模擬，不需要 API）
│   ├── 無 private WS（無真實訂單）
│   ├── initial_balance = Demo 帳戶餘額（紙盤映射 Demo 資金）
│   ├── paper_cmd_tx_paper channel
│   ├── DB engine_mode = "paper"
│   └── 快照 → pipeline_snapshot_paper.json
│
├── ── Demo Pipeline ──────────────────────────────────────────
│   ├── pipeline_kind = PipelineKind::Demo（固定）
│   ├── REST client → api-demo.bybit.com（Demo API key）
│   ├── private WS → api-demo.bybit.com（Demo API key）
│   ├── initial_balance = Demo 帳戶實際餘額
│   ├── paper_cmd_tx_demo channel
│   ├── DB engine_mode = "demo"
│   └── 快照 → pipeline_snapshot_demo.json
│
└── ── Live Pipeline ──────────────────────────────────────────
    ├── pipeline_kind = PipelineKind::Live（固定）
    ├── REST client → 按 bybit_endpoint.json 決定：
    │   ├── endpoint=mainnet → api.bybit.com（Live API key，真實主網）
    │   └── endpoint=live_demo → api-demo.bybit.com（Live API key，Live-Demo 測試）
    ├── private WS → 對應 endpoint
    ├── initial_balance = Live/Live-Demo 帳戶實際餘額
    ├── paper_cmd_tx_live channel
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

## 四、實施計劃（分 6 個子任務）

### 3E-1：`PipelineKind` 枚舉替換 `TradingMode`（Rust 基礎）

**目標**：建立不可變的管線身份枚舉，替換全局可切換的 `TradingMode`。

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
}
impl std::fmt::Display for PipelineKind {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.db_mode())
    }
}
```

**TickPipeline 修改**：
- `trading_mode: TradingMode` → `pipeline_kind: PipelineKind`（不可變，無 setter）
- `with_balance(symbols, balance)` → `with_kind(kind: PipelineKind, symbols, balance)`
- 移除 `mode_states: HashMap<TradingMode, ModeState>`
- 移除 `active_modes: Vec<TradingMode>`
- 移除 `set_trading_mode()` 方法
- 移除 `sync_direct_to_mode_state()` / `load_mode_state_to_direct()` 方法
- 移除 `add_mode()` / `switch_mode()` IPC 命令及 handlers
- 所有 `self.trading_mode` → `self.pipeline_kind`
- 所有 `matches!(self.trading_mode, Demo | Live)` → `self.pipeline_kind.is_exchange()`

**`PipelineSnapshot` 修改**：
- `trading_mode: TradingMode` → `pipeline_kind: String`（序列化為 "paper"/"demo"/"live"）
- 移除 `mode_snapshots: HashMap<String, ModeStateSnapshot>`（三引擎後每個快照就是其 mode snapshot）

**估算規模**：tick_pipeline.rs ~-200 行（移除 mode_states 相關代碼）+ ~+30 行（新 enum）

---

### 3E-2：三管線並行啟動（`main.rs` + `event_consumer`）

**目標**：`main.rs` 同時 spawn 三個 `run_event_consumer()` 實例。

**市場數據 fan-out**：
```rust
// 公共 WS 事件廣播到三個管線
let (event_tx_paper, event_rx_paper) = mpsc::unbounded_channel();
let (event_tx_demo, event_rx_demo) = mpsc::unbounded_channel();
let (event_tx_live, event_rx_live) = mpsc::unbounded_channel();
// WS 事件分發任務（fan-out）
tokio::spawn(async move {
    while let Some(event) = ws_event_rx.recv().await {
        let _ = event_tx_paper.send(event.clone());
        let _ = event_tx_demo.send(event.clone());
        let _ = event_tx_live.send(event);
    }
});
```

**三個獨立 API 客戶端**：
- Paper: `None`（無需 REST client）
- Demo: `BybitRestClient::new(BybitEnvironment::Demo, demo_key, demo_secret)`
- Live: `BybitRestClient::new(live_bybit_environment(), live_key, live_secret)`

**三個獨立 paper_cmd_tx**：
```rust
let (cmd_tx_paper, cmd_rx_paper) = mpsc::unbounded_channel::<PaperSessionCommand>();
let (cmd_tx_demo, cmd_rx_demo) = mpsc::unbounded_channel::<PaperSessionCommand>();
let (cmd_tx_live, cmd_rx_live) = mpsc::unbounded_channel::<PaperSessionCommand>();
```

**三個獨立私有 WS**：
- Paper: 跳過
- Demo: `BybitPrivateWs::new(BybitEnvironment::Demo, demo_key, demo_secret)`
- Live: `BybitPrivateWs::new(live_env, live_key, live_secret)`

**`EventConsumerDeps` 修改**：
- 新增 `pipeline_kind: PipelineKind` 字段（不再從 config 讀取）
- 移除 `paper_initial_balance: Option<f64>` 特殊處理（Paper Pipeline 直接讀 Demo 餘額）

**`run_event_consumer()` 修改**：
- 移除 `set_trading_mode()` 調用
- 使用 `TickPipeline::with_kind(deps.pipeline_kind, SYMBOLS, initial_balance)` 構造
- DB 寫入直接使用 `pipeline.pipeline_kind.db_mode()`

**估算規模**：main.rs ~+150 行（三份初始化），event_consumer/mod.rs ~-50 行（移除 mode 邏輯）

---

### 3E-3：IPC Server 三管線路由（`ipc_server.rs`）

**目標**：IPC 命令按 `engine` 參數精確路由到對應管線的 channel。

**`EngineCommandChannels` 替換 `paper_cmd_tx`**：
```rust
pub struct EngineCommandChannels {
    pub paper: Option<mpsc::UnboundedSender<PaperSessionCommand>>,
    pub demo:  Option<mpsc::UnboundedSender<PaperSessionCommand>>,
    pub live:  Option<mpsc::UnboundedSender<PaperSessionCommand>>,
}
impl EngineCommandChannels {
    pub fn select(&self, engine: &str) -> Option<&mpsc::UnboundedSender<PaperSessionCommand>> {
        match engine {
            "demo" => self.demo.as_ref(),
            "live" => self.live.as_ref(),
            _      => self.paper.as_ref(), // 默認 paper
        }
    }
}
```

**快照路由**：
- `data_dir/pipeline_snapshot_paper.json`
- `data_dir/pipeline_snapshot_demo.json`  
- `data_dir/pipeline_snapshot_live.json`
- `get_paper_state?engine=paper/demo/live` → 讀對應快照文件
- 移除基於 `trading_mode` 的快照路由邏輯

**移除 IPC 命令**：
- `add_engine_mode` — 三引擎後不再需要
- `switch_engine_mode` — 三引擎後不再需要

**估算規模**：ipc_server.rs ~-80 行（移除 mode 相關 handlers + 路由）+ ~+60 行（新 channels struct）

---

### 3E-4：`TradingMode` + `EngineConfig` 完整清除（Rust）

**目標**：從 Rust 代碼和 TOML 配置中完全移除 `TradingMode`。

**`config/mod.rs`**：
- 移除 `pub enum TradingMode { PaperOnly, Demo, Live }`（取而代之的是 `PipelineKind`）
- 移除 `EngineConfig::trading_mode` 字段
- 移除 hot-reload cold 警告邏輯（`config/mod.rs:363-368`）
- 移除所有 `TradingMode` use 引用

**TOML 配置文件清除**（`settings/` 目錄）：
- `engine.toml` / `engine_demo.toml` / `engine_live.toml`：移除 `trading_mode = ...` 行
- 引擎啟動時不再需要這個字段

**其他 Rust 文件**：
- `bybit_rest_client.rs`：移除 `secret_slot()` 對 TradingMode 的引用（傳入 env 即可判斷）
- `mode_state.rs`：評估是否還需要（ModeState 可能在三引擎架構中簡化為單個 Pipeline 的狀態）

**估算規模**：~-100 行（enum + config 字段 + hot-reload + use 引用）

---

### 3E-5：Python 側清除（`live_session_routes.py` 等）

**目標**：移除 Python 中基於 `trading_mode` 的邏輯，改用 `system_mode` 作為唯一的面向 Operator 的模式概念。

**`live_session_routes.py`**：
- 移除 `_get_trading_mode_from_engine()` 函數（讀快照的 `trading_mode` 字段）
- `get_session_status()` 返回：
  - 移除 `"trading_mode"` 字段
  - 保留並突出 `"system_mode"` 字段（已在本次 session 實現）
  - 新增 `"active_engines"` 字段：列出哪些 Pipeline 實際在運行 `["paper", "demo", "live"]`
- Live session start/stop 的 gate 改用 `system_mode` 判斷而非 `trading_mode`
- `_mode_key` 邏輯（`live/demo/paper` 路由快照）改用三個獨立快照文件

**`ipc_state_reader.py`**：
- 移除按 `trading_mode` 路由快照的邏輯
- 改為讀 `pipeline_snapshot_{engine}.json`

**`paper_trading_routes.py`**：
- 移除 `trading_mode` 字段返回

**估算規模**：~-80 行 Python（主要在 live_session_routes.py）

---

### 3E-6：Sidebar + GUI 顯示清理（console.html / common.js）

**目標**：UI 完全不出現 `trading_mode`，Sidebar 顯示 `system_mode`。

**`console.html` `refreshSidebar()`**：
```javascript
// 替換當前邏輯：
const systemMode = d.system_mode || 'unknown';
modeEl.textContent = systemMode.replace(/_/g, ' ');  // "live_reserved" → "live reserved"
```

**模式顏色映射**：
```javascript
const modeColor = {
  live_reserved: '#a855f7',   // 紫色
  demo_reserved: '#3b82f6',   // 藍色
  shadow_only:   '#f59e0b',   // 黃色（限制中）
  observe_only:  '#6b7280',   // 灰色（暫停）
  design_only:   '#6b7280',
}[systemMode] || '';
```

**移除**：`trading_mode.toUpperCase()` 顯示邏輯，`_get_trading_mode_from_engine()` 依賴。

---

## 五、實施時序與依賴圖

```
3E-1 PipelineKind 替換 TradingMode
  ↓
3E-2 三管線並行啟動  ←──── 3E-3 IPC 三管線路由
  ↓                           ↓
3E-4 TradingMode 完整清除（Rust 最終清理）
  ↓
3E-5 Python 側清除
  ↓
3E-6 Sidebar GUI 清理（可提前獨立做）
```

**3E-6 可以現在立即做**（無後端依賴，只改 JS）。  
**3E-1~5 建議一個 Sprint 連續完成**，避免代碼處於半遷移不一致狀態。

---

## 六、工作量估算與建議排期

| 任務 | Rust LOC 變化 | Python LOC 變化 | 風險 |
|------|-------------|----------------|------|
| 3E-1 PipelineKind | -200 / +30 | — | 中（大量 find/replace） |
| 3E-2 三管線啟動 | +150 / -50 | — | 高（私有 WS per-pipeline） |
| 3E-3 IPC 路由 | -80 / +60 | — | 中 |
| 3E-4 TradingMode 清除 | -100 | — | 低（收尾） |
| 3E-5 Python 清除 | — | -80 | 低 |
| 3E-6 Sidebar 修正 | — | +20 JS | 低 |
| **總計** | **~-240** | **~-60** | — |

**建議排期**：W22（2026-05-05~09）—— 在 Phase 6 完整驗收（W21）之後，AI Agent 接線（W23）之前。
**建議執行方式**：E1 並行（3E-1 + 3E-3 可同時進行）→ E2 代碼審查 → E4 測試回歸 → QA。

---

## 七、Live API Key 補充說明

按用戶要求，Live Pipeline **不得框死主網**：

- Live Pipeline 通過 `bybit_endpoint.json`（已有機制，`live_bybit_environment()` 函數）決定連接哪個端點
- 兩種合法配置：
  1. **真實主網**：Live API key + `endpoint=mainnet` → `api.bybit.com`（真實資金）
  2. **Live-Demo 測試**：Demo API key（填入 live 槽）+ `endpoint=live_demo` → `api-demo.bybit.com`（Demo 環境，用 live 路徑測試）
- 這個機制在現有 `read_secret_file(slot)` + `live_bybit_environment()` 中已實現，遷移後繼續保留

---

## 八、測試策略

- **3E-1**：現有 879 lib tests 全部必須繼續通過（`TradingMode` → `PipelineKind` 是 rename，行為不變）
- **3E-2**：新增 3 個 e2e 測試場景：Paper/Demo/Live 並行 tick，驗證各自 DB 寫入 engine_mode 正確
- **3E-3**：IPC `engine=paper/demo/live` 路由測試（各 2 個場景）
- **3E-4~5**：回歸確保移除後無編譯錯誤 + Python 2792 tests pass
- **總目標**：遷移後測試基線不降（879 lib + 18 e2e + 2792 Python）

---

*文件結束 / End of document*
