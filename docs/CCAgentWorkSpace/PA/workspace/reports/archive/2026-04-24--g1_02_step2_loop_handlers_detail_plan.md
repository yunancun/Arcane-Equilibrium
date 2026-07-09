# G1-02 Step 2 — loop_handlers.rs 詳細實裝設計

**Agent**：Plan / PA（sub-agent 產出）
**Date**：2026-04-24
**Task**：Wave 1 G1-02 Step 2 規劃文件（不寫 code，只規劃）
**Context**：Step 1 (`pending_sweep.rs`) 已完成 + Step 3 (`bootstrap.rs`) 同日主 session 並行實裝；本 Step 2 plan 為 **Step 3 完成後的進一步精化路徑**（非 G1-02 <1200 硬上限必要）

---

## Executive summary

Step 2 拆 5 arm 為 handler fn + `LoopState` struct（7 mutable fields）放 `loop_handlers.rs`；強烈建議採方案 **B 分 3 sub-commits**（小 3 arm / cmd arm / 大 2 arm）控 borrow 衝突 + review 顆粒度。Step 3 `BootstrappedRuntime` 需補 5 欄位（`symbol_registry` / `cfg_snapshot` / `bootstrap_client` / `kline_seed_tx` / `known_symbols`）供 Arm F tick handler 使用。**主 session 2026-04-24 Step 3 commit `96f9f92` 已納入這 5 欄位**，Step 2 實裝可直接消費。

---

## 1. mod.rs 5 arm 當前精確邊界（post-Step1 line range，1677 行版）

實測 line number（Step 1 後 `rust/openclaw_engine/src/event_consumer/mod.rs`）：

| Arm | Line range | LOC | 功能 | 引用的外部狀態 |
|---|---|---|---|---|
| cancel | 772 | 1 | `cancel.cancelled() => break` | `cancel` owned |
| **A. cross_engine** | 776–809 | 34 | `cross_engine_rx.recv()` 處理 Crashed/CircuitBreakerTripped，升級本 pipeline risk 至 Cautious | `cross_engine_rx: &mut`, `pipeline: &mut`, `pipeline_kind: Copy` |
| **B. kline_seed** | 813–819 | 7 | `kline_seed_rx.recv()` seed `pipeline.kline_manager.seed_bars` | `kline_seed_rx: &mut`, `pipeline: &mut` |
| **C. exchange_event** | 823–1118 | 296 | `exchange_event_rx.recv()` 處 Fill / OrderUpdate / PositionUpdate / DcpTriggered / Disconnected 5 變體 | `exchange_event_rx: &mut`, `pipeline: &mut`, `seen_exec_set: &mut`, `seen_exec_order: &mut`, `pending_orders: &mut`, `order_id_to_link: &mut`, `snapshot_writer: &mut`, `order_tx: &Option<Sender>`, `pipeline_kind: Copy` |
| **D. pending_reg** | 1121–1158 | 38 | `pending_reg_rx.recv()` 插 `pending_orders` + emit Order + OrderStateChange | `pending_reg_rx: &mut`, `pending_orders: &mut`, `order_tx: &Option<Sender>`, `pipeline: &(for em)` |
| **E. cmd (paper command)** | 1161–1269 | 109 | `pipeline_cmd_rx.recv()` 分派 DisableEdgePredictorAll / ResetDrawdownBaseline / 其他 paper command | `pipeline_cmd_rx: &mut`, `pipeline: &mut`, `snapshot_writer: &mut`, `pending_orders: &mut`, `audit_pool: &Option<Pool>`, `shared_risk_level: &Option<Arc<AtomicU8>>`, `_cross_engine_tx: &Option<Sender>`, `pipeline_kind: Copy`, 且包 1 `.await` on `delete_checkpoint` |
| **F. event (tick)** | 1271–1632 | 362 | `event_rx.recv()` 跑 on_tick / audit fills / shared state sync / pending_orders sweep / status report / D2 registry diff + D3 kline bootstrap spawn | 全部：`event_rx: &mut`, `pipeline: &mut`, `shared_last_tick_ms/bybit_balance/api_pnl: &Option`, `canary_handle: &`, `audit_writer: &`, `pending_orders/order_id_to_link: &mut`, `last_pending_check: &mut`, `last_status: &mut`, `state_writer/snapshot_writer: &mut`, `start_time: &`, `audit_pool: &Option`, `symbol_registry: &Option`, `known_symbols: &mut`, `cfg_snapshot: &`, `bootstrap_client: &Option`, `kline_seed_tx: &`, `shared_client: &Option`（於 maker cancel spawn）, `pipeline_kind: Copy` |

**Arm 內 `tokio::spawn`**：
- Arm F 內 3 處：(1) line 1408 `tokio::spawn(async move { pending_sweep::cancel_resting_maker_order(...) })`；(2) line 1507 `tokio::spawn(async move { crate::paper_state::checkpoint::write_checkpoint(...) })`；(3) line 1567 `tokio::spawn(async move { mdc.get_klines(...) })`。
- Arm C 內 0 處 spawn（純 sync 處理 match）。

**Arm 內 `.await`**：只有 Arm E 的 `delete_checkpoint(...).await`（line 1209）— 這使 Arm E 的 handler fn 必須 `async fn`。

---

## 2. `LoopState` struct 完整設計

Grep 驗證 mod.rs 770–1634 內所有 `let mut` 僅 3 個落在 loop body 內（都是 arm 局部 hot-path 變數 line 1357-1358、1583、其他皆為 bootstrap）。loop-internal 在 loop 頂層（前面 line 735-754）宣告的 mutable state 全量：

```rust
// event_consumer/loop_handlers.rs
/// Loop-internal mutable state owned by `run_event_consumer` between bootstrap
/// and the select! loop. Passed by `&mut` into each arm handler so borrows are
/// scoped per-call (avoids holding multiple mut borrows across arms).
/// 主迴圈的 loop-internal 可變狀態容器。
pub(super) struct LoopState {
    /// EXT-1 pending order tracking
    pub pending_orders: HashMap<String, PendingOrder>,
    /// P0-1 order_id → order_link_id mapping（Fill 匹配用）
    pub order_id_to_link: HashMap<String, String>,
    /// P0-2 + FIX-33 exec_id dedup（HashSet O(1) lookup）
    pub seen_exec_set: std::collections::HashSet<String>,
    /// P0-2 + FIX-33 eviction ordering（VecDeque FIFO）
    pub seen_exec_order: std::collections::VecDeque<String>,
    /// D2 scanner registry diff baseline
    pub known_symbols: std::collections::HashSet<String>,
    /// status report cadence clock
    pub last_status: Instant,
    /// pending sweep cadence clock
    pub last_pending_check: Instant,
}

impl LoopState {
    pub(super) const MAX_SEEN_EXEC_IDS: usize = 500;

    pub(super) fn new(known_symbols: std::collections::HashSet<String>) -> Self {
        Self {
            pending_orders: HashMap::new(),
            order_id_to_link: HashMap::new(),
            seen_exec_set: std::collections::HashSet::new(),
            seen_exec_order: std::collections::VecDeque::new(),
            known_symbols,
            last_status: Instant::now(),
            last_pending_check: Instant::now(),
        }
    }
}
```

**不放進 `LoopState` 的 loop-頂層 let bindings**：
- `start_time: Instant` — 只讀（Arm F uptime 用），由 Step 3 bootstrap 構造、loop 內不變
- `status_interval` / `pending_timeout: Duration` — 常量，放 `const`
- `_cross_engine_tx` / `_pipeline_health` — 只讀 Option，bootstrap 輸出
- `cross_engine_rx` / `exchange_event_rx` / `pending_reg_rx` / `pipeline_cmd_rx` / `event_rx` / `kline_seed_rx` — 本身 `&mut` 要在 select! poll，必須留在 loop 外 owned（不進 `LoopState`，因為 select! 要 direct `&mut` 它們）

---

## 3. 5 個 handler fn 簽章（全量 rustc 可編譯）

放 `event_consumer/loop_handlers.rs`。所有 handler 為 `pub(super)` — 只給 `event_consumer::mod` call。

```rust
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::mpsc;
use crate::persistence::{AuditWriter, DualStateWriter, StateWriter};
use crate::tick_pipeline::{EngineEvent, PipelineCommand, PipelineKind, TickPipeline};
use super::types::{ExchangeEvent, PendingOrder};
use super::pending_sweep::{self, classify_pending_sweep, PendingSweepAction};
use super::handlers;

/// Arm A: cross-engine cascade event.
/// 同步 fn；只 borrow `pipeline` mut（升級 risk）。
pub(super) fn handle_cross_engine_event(
    evt: Result<EngineEvent, tokio::sync::broadcast::error::RecvError>,
    pipeline: &mut TickPipeline,
    pipeline_kind: PipelineKind,
) {
    // body = 原 mod.rs lines 779-808
}

/// Arm B: dynamic kline bootstrap seed.
pub(super) fn handle_kline_seed(
    seed: Option<(String, Vec<openclaw_core::klines::KlineBar>)>,
    pipeline: &mut TickPipeline,
) {
    // body = 原 mod.rs lines 813-819 (除 recv 本身)
}

/// Arm C: exchange fill / order update / position update / DCP / disconnect.
/// Param 分組：msg + pipeline + state + order_tx borrow。
pub(super) fn handle_exchange_event(
    evt: Option<ExchangeEvent>,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut DualStateWriter,
    state: &mut LoopState,
    order_tx: Option<&mpsc::Sender<crate::database::TradingMsg>>,
) {
    // body = 原 mod.rs lines 826-1117
    // 注意：`continue` 語意改為 `return`（因 fn context），用 early return
}

/// Arm D: pending order registration from dispatch task.
pub(super) fn handle_pending_registration(
    reg: Option<PendingOrder>,
    pipeline: &TickPipeline,                // 只讀：取 effective_engine_mode
    state: &mut LoopState,
    order_tx: Option<&mpsc::Sender<crate::database::TradingMsg>>,
) {
    // body = 原 mod.rs lines 1124-1157
}

/// Arm E: IPC paper command dispatch. `async fn` because of `delete_checkpoint().await`.
pub(super) async fn handle_pipeline_command(
    cmd: Option<PipelineCommand>,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut DualStateWriter,
    state: &mut LoopState,
    audit_pool: Option<&sqlx::PgPool>,
    shared_risk_level: Option<&Arc<std::sync::atomic::AtomicU8>>,
    cross_engine_tx: Option<&tokio::sync::broadcast::Sender<EngineEvent>>,
    pipeline_kind: PipelineKind,
) {
    // body = 原 mod.rs lines 1164-1268
}

/// Arm F: main tick event — on_tick, shared state sync, pending sweep, status report, D2/D3.
/// Returns `ControlFlow<()>`：Continue = continue loop；Break = outer loop break
/// （原 `None => break`，用 ControlFlow 表達）。
pub(super) async fn handle_tick_event(
    evt: Option<Arc<openclaw_types::PriceEvent>>,
    pipeline: &mut TickPipeline,
    state_writer: &mut StateWriter,
    snapshot_writer: &mut DualStateWriter,
    audit_writer: &AuditWriter,
    state: &mut LoopState,
    start_time: Instant,
    status_interval: std::time::Duration,
    pending_timeout: std::time::Duration,
    shared_last_tick_ms: Option<&Arc<std::sync::atomic::AtomicU64>>,
    shared_bybit_balance: Option<&Arc<parking_lot::RwLock<Option<f64>>>>,
    shared_api_pnl: Option<&Arc<parking_lot::RwLock<HashMap<String, f64>>>>,
    canary_handle: &crate::canary_writer::CanaryWriterHandle,
    shared_client: Option<&Arc<crate::bybit_rest_client::BybitRestClient>>,
    audit_pool: Option<&sqlx::PgPool>,
    symbol_registry: Option<&Arc<crate::scanner::registry::SymbolRegistry>>,
    cfg_snapshot: &Arc<crate::config::EngineBootstrap>,
    bootstrap_client: Option<&Arc<crate::bybit_rest_client::BybitRestClient>>,
    kline_seed_tx: &mpsc::Sender<(String, Vec<openclaw_core::klines::KlineBar>)>,
) -> std::ops::ControlFlow<()> {
    // body = 原 mod.rs lines 1272-1631
    // None => break 改 return ControlFlow::Break(())
}
```

**Borrow checker 分析**：
- Arm C 同時需 `pipeline: &mut` + `snapshot_writer: &mut` + `state: &mut LoopState`（含 `pending_orders / order_id_to_link / seen_exec_set / seen_exec_order`）+ `order_tx: &Option`。4 個獨立 `&mut` borrow，跨 struct 不衝突（`LoopState` 各欄獨立 field 同時 mut 借可由編譯器 split-borrow；但若全 pass `&mut LoopState` 則合併為 1 個 borrow，更安全）。推薦 pass `&mut LoopState` 讓編譯器檢查一次。
- Arm E 需 `pipeline: &mut` + `snapshot_writer: &mut` + `state: &mut LoopState.pending_orders`（`handle_paper_command` 簽章要 `&mut HashMap`）+ 4 個 `&Option`。為相容現有 `handlers::handle_paper_command(cmd, &mut pipeline, &mut snapshot_writer, &mut pending_orders)` 簽章，fn 內部 `&mut state.pending_orders` 即可。
- Arm F 同時借 `state.known_symbols: &mut` + `state.last_status: &mut` + `state.last_pending_check: &mut` + `state.pending_orders: &mut` + `state.order_id_to_link: &mut`。Pass `&mut state` 再於 fn 內 split-borrow。
- **跨 arm 衝突**：select! 一次只 poll 一個 arm，同一時刻只會執行一個 handler fn，不會有跨 arm 同時 `&mut` 衝突。每個 arm handler borrow 的 lifetime 與該 arm body 相同，arm 結束即 drop，下一 tick 重新 borrow。

---

## 4. mod.rs select! 新骨架（可編譯草稿）

```rust
// mod.rs Step 2 後 loop body（Step 3 bootstrap 已拆 → bootstrap_runtime 回 BootstrappedRuntime）
pub async fn run_event_consumer(deps: EventConsumerDeps) {
    let bootstrap::BootstrappedRuntime {
        mut pipeline, mut state_writer, mut snapshot_writer, audit_writer,
        mut kline_seed_rx, kline_seed_tx, mut pending_reg_rx_slot,
        data_path: _, kind_tag: _, order_tx, mut known_symbols, cfg_snapshot,
        bootstrap_client, symbol_registry,
        pipeline_kind, mut event_rx, cancel, shared_client,
        shared_bybit_balance, shared_api_pnl, shared_last_tick_ms,
        mut exchange_event_rx, mut pipeline_cmd_rx, audit_pool,
        shared_risk_level, cross_engine_tx, mut cross_engine_rx,
        pipeline_health, canary_handle,
    } = bootstrap::bootstrap_runtime(deps).await;

    let mut state = loop_handlers::LoopState::new(known_symbols);
    let start_time = Instant::now();
    let status_interval = std::time::Duration::from_secs(STATUS_INTERVAL_SECS);
    let pending_timeout = std::time::Duration::from_secs(5);

    if let Some(ref h) = pipeline_health {
        h.store(crate::tick_pipeline::PipelineHealth::Running as u8,
                std::sync::atomic::Ordering::Relaxed);
    }

    loop {
        tokio::select! {
            _ = cancel.cancelled() => break,

            engine_evt = async {
                if let Some(ref mut rx) = cross_engine_rx { rx.recv().await }
                else { std::future::pending().await }
            } => {
                loop_handlers::handle_cross_engine_event(engine_evt, &mut pipeline, pipeline_kind);
            }

            seed = kline_seed_rx.recv() => {
                loop_handlers::handle_kline_seed(seed, &mut pipeline);
            }

            exchange_evt = async {
                if let Some(ref mut rx) = exchange_event_rx { rx.recv().await }
                else { std::future::pending().await }
            } => {
                loop_handlers::handle_exchange_event(
                    exchange_evt, &mut pipeline, &mut snapshot_writer,
                    &mut state, order_tx.as_ref(),
                );
            }

            pending_reg = async {
                if let Some(ref mut rx) = pending_reg_rx_slot { rx.recv().await }
                else { std::future::pending().await }
            } => {
                loop_handlers::handle_pending_registration(
                    pending_reg, &pipeline, &mut state, order_tx.as_ref(),
                );
            }

            cmd = async {
                if let Some(ref mut rx) = pipeline_cmd_rx { rx.recv().await }
                else { std::future::pending().await }
            } => {
                loop_handlers::handle_pipeline_command(
                    cmd, &mut pipeline, &mut snapshot_writer, &mut state,
                    audit_pool.as_ref(), shared_risk_level.as_ref(),
                    cross_engine_tx.as_ref(), pipeline_kind,
                ).await;
            }

            event = event_rx.recv() => {
                let flow = loop_handlers::handle_tick_event(
                    event, &mut pipeline, &mut state_writer, &mut snapshot_writer,
                    &audit_writer, &mut state, start_time, status_interval,
                    pending_timeout, shared_last_tick_ms.as_ref(),
                    shared_bybit_balance.as_ref(), shared_api_pnl.as_ref(),
                    &canary_handle, shared_client.as_ref(), audit_pool.as_ref(),
                    symbol_registry.as_ref(), &cfg_snapshot, bootstrap_client.as_ref(),
                    &kline_seed_tx,
                ).await;
                if flow.is_break() { break; }
            }
        }
    }
    // Shutdown（保留在 mod.rs，~40 行）
}
```

---

## 5. 拆分順序 — 推薦方案 B

**方案 A**（PA 原版一次拆 5 arm）：風險 = 一個巨型 commit，review 難，任何 borrow checker 錯誤難定位。

**方案 B（推薦）**：3 個 sub-commit：
1. **Step 2a**：抽小 3 arm（cross_engine A + kline_seed B + pending_reg D）+ 建 `LoopState` struct + `loop_handlers.rs` module skeleton。LOC 影響 mod.rs -70 (+loop_handlers.rs +120)。borrow 最簡單（僅單一 `&mut pipeline` 或單一 `&mut state` field），zero 衝突。
2. **Step 2b**：抽 Arm E (cmd)。`async fn` 首次引入，需驗 `.await` 行為與原版一致（尤其 `delete_checkpoint` 的 DB error path）。涉 `handlers::handle_paper_command` call-through（已存在，不動）。
3. **Step 2c**：抽 Arm C (exchange_event) 和 Arm F (event tick)。這兩個最大 (296 + 362 LOC)。可合並 1 commit 也可分 2 commit；若 borrow 順利合；若 F 的 `cfg_snapshot / bootstrap_client / kline_seed_tx / symbol_registry / known_symbols` 參數太多（9+ 個），考慮將 D2/D3 內部邏輯再抽 1 個 private helper `emit_status_report_and_scanner_diff(...)` 留 Arm F handler 乾淨。

**方案 C 替代**：若 Step 3 bootstrap 已達成 mod.rs < 1200，可只做方案 B 的 2a（拆小 3 arm），mod.rs → ~900s，達標結案。C/F 大 arm 留作 future refactor。

**推薦：方案 B**。理由：(1) review 顆粒度友善（每 commit LOC 可控） (2) borrow 風險逐步暴露，先小後大 (3) Arm C+F 變動最大，獨立 commit 利於 `git bisect`。

**註（2026-04-24 主 session 更新）**：Step 3 `96f9f92` 已將 mod.rs 降至 **1009 行**（< 1200 硬上限 ✅），**G1-02 硬性完成標準已達成**。Step 2 變為可選精進項，優先度降為 P1 — Wave 2 初期執行即可，無阻塞。

---

## 6. Hot-path 性能守衛

| Arm | 調用頻次 | Hot-path | 建議 |
|---|---|---|---|
| A cross_engine | 極低（peer crash 才觸發） | ✩ | 無需 `#[inline]` |
| B kline_seed | 每新符號 1 次 | ✩ | 無需 |
| C exchange_event | per-fill + per-order-update（live 每秒 0–10） | ★★ | `#[inline]` on hot branch（Fill match）非必要；cross-file fn call 經 `--release` LTO 會 inline |
| D pending_reg | per-submit（每秒 0–5） | ★ | 無需 |
| E cmd | per-IPC（低頻） | ✩ | 無需；async await 本就 heap-box |
| F event tick | **per-tick**（500+/sec peak） | ★★★ | **關鍵**。`handle_tick_event` 要確保 LTO inline。建議 (a) `#[inline]` 標在 fn signature (b) Cargo.toml 已有 LTO 設定確認（`lto = "thin"` 或 `"fat"`）。若 benchmark 顯示 regression，退回 inline attr 組合 |

**LTO 驗證方法**：拆完後跑 `cargo bench -p openclaw_engine --release`（若有 benchmark）或對比 `event_consumer_benchmark` 測 p99 latency 前後；差 < 2% 接受。

---

## 7. 預估 LOC 結果

| 檔 | Step 1 後 | Step 3 後（實測）| Step 2 後（方案 B）| §九 狀態 |
|---|---|---|---|---|
| `mod.rs` | 1677 | **1009 ✅** | ~450（shell + shutdown + imports + loop 骨架） | ✅ < 800 理想 |
| `loop_handlers.rs` | — | — | ~1200（5 handler + LoopState + helpers） | ⚠️ 貼 1200 硬上限，需監控 |
| `bootstrap.rs` | — | **847**（Step 3）| 847（不動）| ⚠️ 800 警告線上（新 sibling）|
| `pending_sweep.rs` | 286 | 286 | 286（不動）| ✅ |
| `handlers/mod.rs + 4 子檔` | 1124 | 1124 | 1124（不動）| ⚠️ 已接近 1200，未動 |

**風險點**：`loop_handlers.rs` 若達 1200，需再拆（例 `loop_handlers/mod.rs` + `loop_handlers/exchange.rs` + `loop_handlers/tick.rs`）。建議 Step 2 實裝先做 flat 單檔，若超 1000 行再評估子拆。

**`LoopState` 放哪？** 推薦 **放 `loop_handlers.rs`**（與 handler 強耦合；mod.rs 只 `use loop_handlers::LoopState`）。避免放 mod.rs 造成循環依賴。

---

## 8. 風險點 + 反例

1. **Step 3 已完成 → Step 2 是否可跳？** Step 3 後 mod.rs 1009（實測），已 < 1200 硬上限，**§九 合規達成**。但 1009 > 800 警告線，E2 review 會標記。建議仍做 Step 2（至少方案 B 的 2a 小 3 arm），讓 mod.rs 降到 ~900 以下或最終 ~450。**不強制全做 5 arm**。
2. **Step 2 後 mod.rs < 800？** 方案 B 全跑完 mod.rs ~450，遠低 800 警告線。此時 `loop_handlers.rs` ~1200 接近硬上限，下一輪可能需拆 `loop_handlers/` 子模組。結論：拆完方案 B 整體 LOC 平衡良好，無額外拆分需求。
3. **tests.rs 是否測 run_event_consumer？** 實測 `rust/openclaw_engine/src/event_consumer/tests.rs` 1298 行，grep 結果 **零** `run_event_consumer` direct call；所有 test 走 `handlers::handle_paper_command(...)` mock pipeline（見 line 90, 108, 147 等 17 處）。抽 loop arm 為 fn **不影響現有測試**。新 handler fn 可選擇 `#[cfg(test)]` 加直測（可選 FUP，不強求）。
4. **Arm C 的 `continue` 語意變更**：原代碼 line 832 `continue` 作用於 `loop`（外層），抽 fn 後改 `return` 只退出 fn，下一次 select! 迭代自動進下個 tick。**語意等價**，因為 `continue` 原本也只是跳過當前 arm body 剩餘部分，進下個 iteration。
5. **Arm E 的 `await` 中斷**：若 `delete_checkpoint().await` 正執行中，select! 被 `cancel.cancelled()` 取消會怎樣？答：select! 的 `cancel` arm 只在 handler 未被選中時才 poll；一旦 `cmd` arm 被選中且正 `.await`，這整個 arm 不會被 cancel 打斷（tokio select! 語意）。原代碼行為相同，抽 fn 不變。

---

## 9. 與 Step 3（bootstrap）的接口契約

**Step 3 的 `BootstrappedRuntime` struct 必含欄位**（按 Step 1 report §5.2 + 本設計新發現）：
- 已列：pipeline / state_writer / snapshot_writer / audit_writer / kline_seed_rx / pending_reg_rx / start_time / pipeline_kind / event_rx / cancel / shared_client / shared_last_tick_ms / shared_bybit_balance / shared_api_pnl / trading_tx / exchange_event_rx / pipeline_cmd_rx / audit_pool / shared_risk_level / cross_engine_tx / cross_engine_rx / pipeline_health / canary_handle
- **新增需補（Step 1 report §5.2 未列，本設計 Arm F 實證需要）**：
  - `symbol_registry: Option<Arc<SymbolRegistry>>` — Arm F line 1532 D2 registry diff ✅ 已納入 Step 3
  - `cfg_snapshot: Arc<EngineBootstrap>` — Arm F line 1561 `cfg_snapshot.kline_bootstrap` ✅ 已納入
  - `bootstrap_client: Option<Arc<BybitRestClient>>` — Arm F line 1562 D3 spawn ✅ 已納入
  - `kline_seed_tx: mpsc::Sender<(String, Vec<KlineBar>)>` — Arm F line 1566 send to kline_seed_rx ✅ 已納入
  - `known_symbols: std::collections::HashSet<String>` — Arm F line 1536 D2 diff baseline ✅ 已納入
- **不需要進 BootstrappedRuntime**（bootstrap 內部用完即丟）：`feature_tx / market_data_tx / context_tx / decision_feature_tx / seed_positions / account_manager / linucb_runtime / news_snapshot / risk_store / budget_store / instruments / is_primary / ready_tx / global_exposure_usdt / edge_predictor_store / positions_mirror / endpoint_env / initial_balance / taker_fee_rate`

**Step 3 commit `96f9f92`（2026-04-24，主 session 實裝）已完整納入本 5 欄位**，Step 2 實裝可直接消費 BootstrappedRuntime 欄位。

---

## 10. 簽核 §九 硬上限

- mod.rs Step 3 後 1009 ✅（<1200 硬上限達成）
- mod.rs Step 2 後 ~450（理想終點）
- loop_handlers.rs ~1200（邊界）⚠️ 需監控；若實作超 1200 即分子檔
- bootstrap.rs 847（<1200 OK，>800 警告）
- 無檔超 1200 硬上限

---

**Plan 版本**：1.0 · **產出日期**：2026-04-24 · **Branch**：`g1-02-event-consumer-split` · **依賴**：Step 1 commit `0155c9a` + Step 3 commit `96f9f92`

### Critical Files for Implementation
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/event_consumer/mod.rs`（Step 3 後 1009 行）
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/event_consumer/loop_handlers.rs`（Step 2 新建）
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/event_consumer/pending_sweep.rs`（只 use 不動）
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/event_consumer/bootstrap.rs`（Step 3 新建，不動）
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/event_consumer/handlers/mod.rs`（handle_paper_command 不動）
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/event_consumer/types.rs`（LoopState 可選放這，推薦放 loop_handlers.rs）
