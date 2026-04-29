//! Lifecycle / session-level IPC command handlers (Pause / Resume / Reset /
//! CloseAll / CloseSymbol / SubmitOrder / SetStrategyActive / SetSystemMode /
//! AdoptOrphan). Extracted from the legacy `handlers.rs` monolith as part of
//! E5-P1-3 to keep each domain file under the 800-line warning threshold.
//!
//! 生命週期 / 會話級 IPC 命令處理器（暫停 / 恢復 / 重置 / 全部平倉 / 單倉平倉 /
//! 下單 / 策略啟停 / 系統模式 / 孤兒接管）— E5-P1-3 從舊 handlers.rs 拆出，
//! 保持每個檔案低於 800 行警告線。
//!
//! MODULE_NOTE (EN): Behaviour is identical to the pre-split code; each free
//!   function encapsulates exactly one match-arm body from `handle_paper_command`
//!   and keeps the same side-effects (pipeline mutation + snapshot_writer fsync).
//! MODULE_NOTE (中): 行為與拆分前一致；每個自由函式封裝 `handle_paper_command`
//!   中單一 match 分支的主體，副作用保持相同（管線變動 + snapshot_writer fsync）。

use super::super::types::PendingOrder;
use crate::persistence::DualStateWriter;
use crate::tick_pipeline::TickPipeline;
use std::collections::HashMap;
use tracing::info;

/// EN: Pause the paper pipeline. Sets `paper_paused=true` and flushes the
///     snapshot so observers see the new state immediately.
/// 中文: 暫停紙盤管線 — 設定 paper_paused=true 並立即 flush 快照。
pub(super) fn handle_pause(pipeline: &mut TickPipeline, snapshot_writer: &mut DualStateWriter) {
    pipeline.paper_paused = true;
    info!("paper trading PAUSED via IPC / 紙盤交易已通過 IPC 暫停");
    snapshot_writer.force_write(&pipeline.snapshot());
}

/// EN: Resume the paper pipeline. Clears both `paper_paused` and the F2
///     `session_halted` flag so a fresh session starts cleanly.
/// 中文: 恢復紙盤管線 — 同時清除 paper_paused 與 F2 session_halted 旗標。
pub(super) fn handle_resume(pipeline: &mut TickPipeline, snapshot_writer: &mut DualStateWriter) {
    pipeline.paper_paused = false;
    // F2 fix: clear session_halted on Resume / 恢復時清除會話暫停標誌
    pipeline.session_halted = false;
    info!("paper trading RESUMED via IPC / 紙盤交易已通過 IPC 恢復");
    snapshot_writer.force_write(&pipeline.snapshot());
}

/// EN: Close all positions. Exchange mode routes via the shadow reduce_only
///     channel; paper mode clears `paper_state` directly.
/// 中文: 全部平倉 — 交易所模式走 shadow reduce_only 通道；紙盤模式直接清 paper_state。
pub(super) fn handle_close_all(pipeline: &mut TickPipeline, snapshot_writer: &mut DualStateWriter) {
    // Exchange mode (Demo/Live): dispatch reduce_only market orders via shadow channel.
    // Paper mode: clear paper_state directly.
    // 交易所模式（Demo/Live）：通過 shadow 通道發 reduce_only 市價單。
    // 紙盤模式：直接清除 paper_state。
    let count = pipeline.ipc_close_all();
    info!(count, "IPC close_all_positions / IPC 全部平倉");
    snapshot_writer.force_write(&pipeline.snapshot());
}

/// EN: Close a single symbol; hint args let the reconciler clear orphan
///     exchange positions that `paper_state` does not track.
/// 中文: 單倉平倉；hint 參數供對帳器平掉 paper_state 未追蹤的交易所孤兒倉。
pub(super) fn handle_close_symbol(
    symbol: String,
    hint_is_long: Option<bool>,
    hint_qty: Option<f64>,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut DualStateWriter,
) {
    // Exchange mode (Demo/Live): dispatch reduce_only market order via shadow channel.
    // Paper mode: close_position_at_market directly.
    // hint_is_long/hint_qty allow closing orphan exchange positions not in paper_state.
    // 交易所模式：發 reduce_only 市價單；紙盤模式：直接平倉。
    // hint 參數允許平掉 paper_state 沒有追蹤的交易所孤兒倉位。
    let found = pipeline.ipc_close_symbol(&symbol, hint_is_long, hint_qty);
    info!(
        symbol = symbol.as_str(),
        found, "IPC close_position / IPC 單倉平倉"
    );
    snapshot_writer.force_write(&pipeline.snapshot());
}

/// EN: Reset paper state to a fresh `PaperState(new_balance)` while
///     preserving the shared `positions_mirror` `Arc` so the reconciler
///     keeps observing the same handle (ORPHAN-ADOPT-1 FUP). Clears
///     stats / pause / halt / consecutive_losses / pending close / pending
///     orders — a full session wipe.
/// 中文: 重置紙盤狀態 — 保留共享 positions_mirror Arc 以維持對帳器可視性，
///     同時清空統計 / 暫停 / 中止 / 連虧 / 掛平倉 / 掛單。
pub(super) fn handle_reset(
    new_balance: f64,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut DualStateWriter,
    pending_orders: &mut HashMap<String, PendingOrder>,
) {
    // ORPHAN-ADOPT-1 FUP: preserve the shared positions_mirror handle
    // across reset so the reconciler keeps observing the same Arc.
    // set_positions_mirror clears + rehydrates the shared map from the
    // (empty) positions of the freshly-constructed PaperState.
    // ORPHAN-ADOPT-1 FUP：reset 保留共享 positions_mirror handle，
    // 避免對帳器看到的 Arc 與引擎側分離。
    let shared_mirror = pipeline.paper_state.positions_mirror();
    pipeline.paper_state = crate::paper_state::PaperState::new(new_balance);
    pipeline.paper_state.set_positions_mirror(shared_mirror);
    pipeline.stats = crate::tick_pipeline::TickStats::default();
    pipeline.paper_paused = false;
    // F2+F3 fix: clear halt + loss counters on reset / 重置時清除暫停+虧損計數
    pipeline.session_halted = false;
    pipeline.consecutive_losses.clear();
    // P2-4 fix: Clear pending_close_symbols on reset
    pipeline.clear_all_pending_close();
    pending_orders.clear();
    info!(
        balance = format!("{:.2}", new_balance),
        "IPC reset paper state / IPC 重置紙盤狀態"
    );
    snapshot_writer.force_write(&pipeline.snapshot());
}

/// ARCH-RC1 1C-3-F · EN: External paper-side order submission. Normalises
///   side spelling, clamps confidence, and delegates to
///   `pipeline.submit_external_order`. Only flushes the snapshot on success.
/// ARCH-RC1 1C-3-F · 中文：外部紙盤下單入口。正規化 side 拼寫、鉗制
///   confidence 後委派給 submit_external_order；僅成功時 flush 快照。
#[allow(clippy::too_many_arguments)]
pub(super) fn handle_submit_order(
    symbol: String,
    side: String,
    qty: f64,
    order_type: String,
    limit_price: Option<f64>,
    confidence: f64,
    strategy: String,
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut DualStateWriter,
) {
    let result = (|| -> Result<String, String> {
        let is_long = match side.as_str() {
            "Buy" | "buy" | "long" | "LONG" => true,
            "Sell" | "sell" | "short" | "SHORT" => false,
            other => return Err(format!("invalid side: {other}")),
        };
        let conf = if confidence > 0.0 { confidence } else { 1.0 };
        pipeline.submit_external_order(
            &symbol,
            is_long,
            qty,
            &order_type,
            limit_price,
            conf,
            &strategy,
        )
    })();
    if result.is_ok() {
        snapshot_writer.force_write(&pipeline.snapshot());
    }
    let _ = response_tx.send(result);
}

/// RRC-1-E2 · EN: Activate or pause a strategy by name. Flushes snapshot on
///   Ok; surfaces the previous active state as the response payload.
/// RRC-1-E2 · 中文：依名稱啟停策略；成功時 flush 快照，回應帶前一狀態。
pub(super) fn handle_set_strategy_active(
    strategy_name: String,
    active: bool,
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut DualStateWriter,
) {
    let result = pipeline
        .orchestrator
        .set_strategy_active(&strategy_name, active);
    if result.is_ok() {
        let state = if active { "ACTIVATED" } else { "PAUSED" };
        info!(
            strategy = %strategy_name, state,
            "strategy state changed via IPC / 策略狀態已通過 IPC 更改"
        );
        snapshot_writer.force_write(&pipeline.snapshot());
    }
    let _ = response_tx.send(result.map(|was| format!("was_active={was}")));
}

/// EN: Sync the global system mode (from Python GUI) into the engine. Flushes
///   the snapshot on Ok so consumers see the new mode immediately.
/// 中文: 將全局系統模式（由 Python GUI 發起）同步到引擎；成功時立即 flush 快照。
pub(super) fn handle_set_system_mode(
    mode: String,
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut DualStateWriter,
) {
    let result = pipeline.set_system_mode(&mode);
    if result.is_ok() {
        snapshot_writer.force_write(&pipeline.snapshot());
    }
    let _ = response_tx.send(result);
}

/// P1-5 A2 · EN: Test-only direct dispatch of `ResetDrawdownBaseline`. The
///   production path intercepts this variant in `event_consumer/mod.rs` and
///   runs the full in-memory reset + `checkpoint::delete_checkpoint` DB
///   round-trip. This stub mirrors `handle_disable_edge_predictor_all_local`:
///   performs the in-memory reset only, returns Ok so unit tests exercising
///   `handle_paper_command` stay green without a tokio runtime / PG pool.
/// P1-5 A2 · 中文：測試專用的 `ResetDrawdownBaseline` 直接派發。生產在
///   `event_consumer/mod.rs` 攔截並跑完整記憶體重置 + DB DELETE；本 stub
///   沿用 `handle_disable_edge_predictor_all_local` 模式，僅做記憶體重置、
///   回 Ok，讓不啟 tokio / PG pool 的單元測試能通過 `handle_paper_command`。
pub(super) fn handle_reset_drawdown_baseline_local(
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut DualStateWriter,
) {
    let peak_before = pipeline.paper_state.peak_balance();
    let balance = pipeline.paper_state.balance();
    pipeline.paper_state.reset_drawdown_baseline();
    snapshot_writer.force_write(&pipeline.snapshot());
    info!(
        peak_before,
        balance,
        "P1-5 A2: drawdown baseline reset (local test path) / 重置 drawdown 基準（測試路徑）"
    );
    let _ = response_tx.send(Ok(format!(
        "reset_local peak_before={peak_before:.2} peak_after={balance:.2}"
    )));
}

/// ORPHAN-ADOPT-1 Phase 2A · EN: Adopt an exchange-reported orphan position
///   into `paper_state`. `adopt_orphan` is idempotent; a false return means
///   same-direction position already present — treated as success from the
///   reconciler's viewpoint because the side-car mirror reflects it.
/// ORPHAN-ADOPT-1 Phase 2A · 中文：接管交易所孤兒倉位進入 paper_state；
///   adopt_orphan 冪等，false 表同向已存在，reconciler 視角視同成功。
pub(super) fn handle_adopt_orphan(
    symbol: String,
    is_long: bool,
    qty: f64,
    entry_price: f64,
    ts_ms: u64,
    owner_strategy: Option<String>,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut DualStateWriter,
) {
    let inserted = pipeline.paper_state.adopt_orphan(
        &symbol,
        is_long,
        qty,
        entry_price,
        ts_ms,
        owner_strategy.as_deref(),
    );
    info!(
        symbol = symbol.as_str(),
        is_long, qty, entry_price, inserted, "IPC adopt_orphan / IPC 孤兒接管"
    );
    if inserted {
        snapshot_writer.force_write(&pipeline.snapshot());
    }
}
