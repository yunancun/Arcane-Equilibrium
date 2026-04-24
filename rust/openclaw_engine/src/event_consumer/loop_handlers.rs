//! Event consumer select! arm handlers + LoopState container.
//! 事件消費者 select! arm handler + LoopState 容器。
//!
//! MODULE_NOTE (EN): G1-02 Step 2 extracts the 5 select! arm bodies from
//!   mod.rs into dedicated handler fns so the main loop stays readable and
//!   each arm can be unit-tested in isolation. `LoopState` owns the 7
//!   loop-internal mutable fields that survive across arms (pending_orders,
//!   order_id_to_link, seen_exec_{set,order}, known_symbols, last_status,
//!   last_pending_check). The select! macro must still `&mut` the channel
//!   receivers directly, so they stay owned in `run_event_consumer`.
//!   Step 2a (2026-04-24) ships LoopState + the 3 small arms (A cross_engine,
//!   B kline_seed, D pending_reg). Arms C/E/F are extracted in 2b/2c.
//! MODULE_NOTE (中): G1-02 Step 2 將 mod.rs 的 5 個 select! arm body 抽成
//!   獨立 handler fn，主迴圈保持可讀、每個 arm 可獨立單測。`LoopState`
//!   擁有跨 arm 存活的 7 個 loop-internal 可變欄位；select! 仍需 `&mut`
//!   channel receiver 本身，故 receiver 留在 `run_event_consumer` 內。
//!   Step 2a（2026-04-24）出貨 LoopState + 3 個小 arm（A cross_engine /
//!   B kline_seed / D pending_reg）；C/E/F 三個大 arm 留待 2b/2c。

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;

use super::handlers;
use super::types::PendingOrder;
use crate::persistence::DualStateWriter;
use crate::tick_pipeline::{EngineEvent, PipelineCommand, PipelineKind, TickPipeline};

/// Loop-internal mutable state owned by `run_event_consumer` between bootstrap
/// and the select! loop. Passed by `&mut` into each arm handler so borrows are
/// scoped per-call (avoids holding multiple mut borrows across arms).
/// 主迴圈的 loop-internal 可變狀態容器；以 `&mut` 傳入各 arm handler，
/// 借用以單次呼叫為單位（避免跨 arm 持有多個 mut borrow）。
pub(super) struct LoopState {
    /// EXT-1 pending order tracking / EXT-1 待處理訂單追蹤
    pub pending_orders: HashMap<String, PendingOrder>,
    /// P0-1 order_id → order_link_id mapping (used for fill matching)
    /// P0-1 order_id → order_link_id 映射（成交匹配用）
    pub order_id_to_link: HashMap<String, String>,
    /// P0-2 + FIX-33 exec_id dedup (HashSet O(1) lookup)
    /// P0-2 + FIX-33 exec_id 去重（HashSet O(1) 查找）
    pub seen_exec_set: std::collections::HashSet<String>,
    /// P0-2 + FIX-33 eviction ordering (VecDeque FIFO)
    /// P0-2 + FIX-33 淘汰順序（VecDeque FIFO）
    pub seen_exec_order: std::collections::VecDeque<String>,
    /// D2 scanner registry diff baseline / D2 掃描器註冊表差分基準
    pub known_symbols: std::collections::HashSet<String>,
    /// Status report cadence clock / 狀態報告節奏時鐘
    pub last_status: Instant,
    /// Pending sweep cadence clock / pending 清理節奏時鐘
    pub last_pending_check: Instant,
}

impl LoopState {
    /// Max exec_id entries tracked for dedup; older entries evicted FIFO.
    /// 追蹤的 exec_id 最大數量；超出時 FIFO 淘汰最舊。
    pub(super) const MAX_SEEN_EXEC_IDS: usize = 500;

    /// Build fresh LoopState seeded with the scanner's initial symbol snapshot.
    /// `known_symbols` is moved in from bootstrap so the first D2 diff has a
    /// valid baseline.
    /// 以掃描器初始 symbol 快照構造 LoopState；`known_symbols` 由 bootstrap
    /// 傳入，使首次 D2 diff 有基準值。
    pub(super) fn new(known_symbols: std::collections::HashSet<String>) -> Self {
        let now = Instant::now();
        Self {
            pending_orders: HashMap::new(),
            order_id_to_link: HashMap::new(),
            seen_exec_set: std::collections::HashSet::new(),
            seen_exec_order: std::collections::VecDeque::new(),
            known_symbols,
            last_status: now,
            last_pending_check: now,
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Arm A: cross-engine cascade event (peer crash / circuit breaker trip).
// Arm A：跨引擎級聯事件（對等管線崩潰 / 熔斷）。
// ─────────────────────────────────────────────────────────────────────────────

/// Arm A handler: receive cross-engine event and escalate this pipeline's
/// risk to Cautious on peer crash or CircuitBreaker trip. Sender-dropped
/// case is silently swallowed (all peers gone → no more events).
/// Arm A handler：接收跨引擎事件；對等管線崩潰 / 熔斷時升級本管線風控至
/// Cautious。Sender 被 drop 時靜默忽略（所有對等已退出）。
pub(super) fn handle_cross_engine_event(
    evt: Result<EngineEvent, tokio::sync::broadcast::error::RecvError>,
    pipeline: &mut TickPipeline,
    pipeline_kind: PipelineKind,
) {
    match evt {
        Ok(EngineEvent::Crashed(crashed_kind)) => {
            tracing::warn!(
                this = %pipeline_kind, crashed = %crashed_kind,
                "BLOCKER-2: peer pipeline crashed — escalating to Cautious (60s) \
                 / 對等管線崩潰 — 升級至 Cautious（60s）"
            );
            // Cascade: escalate this pipeline's risk to Cautious.
            // 級聯：將本管線風控升級至 Cautious。
            let duration_s = if crashed_kind == PipelineKind::Paper {
                60
            } else {
                120
            };
            let _ = pipeline.governance.risk.reconciler_escalate_to(
                openclaw_core::sm::risk_gov::RiskLevel::Cautious,
                &format!(
                    "cross_engine_cascade: {} crashed, hold {}s",
                    crashed_kind, duration_s
                ),
            );
        }
        Ok(EngineEvent::CircuitBreakerTripped(cb_kind)) => {
            tracing::warn!(
                this = %pipeline_kind, cb = %cb_kind,
                "BLOCKER-2: peer pipeline hit circuit breaker — escalating to Cautious \
                 / 對等管線觸發熔斷 — 升級至 Cautious"
            );
            let _ = pipeline.governance.risk.reconciler_escalate_to(
                openclaw_core::sm::risk_gov::RiskLevel::Cautious,
                &format!("cross_engine_cascade: {} circuit_breaker", cb_kind),
            );
        }
        Err(_) => {
            // Sender dropped — all peers gone, no more events.
            // Sender 被 drop — 所有對等已退出，無後續事件。
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Arm B: dynamic kline bootstrap seed.
// Arm B：動態 K 線引導結果植入。
// ─────────────────────────────────────────────────────────────────────────────

/// Arm B handler: seed the kline manager with bars fetched by the async D3
/// bootstrap task. `None` from the channel means sender dropped (bootstrap
/// shutdown) — a no-op is the correct response.
/// Arm B handler：將 D3 異步引導任務抓到的 K 線送進 kline manager。
/// Channel 回 `None` 表 sender 被 drop（引導任務關閉），no-op 即為正解。
pub(super) fn handle_kline_seed(
    seed: Option<(String, Vec<openclaw_core::klines::KlineBar>)>,
    pipeline: &mut TickPipeline,
) {
    if let Some((sym, bars)) = seed {
        let count = pipeline.kline_manager.seed_bars(&sym, "1m", bars);
        tracing::info!(
            symbol = %sym, bars = count,
            "dynamic kline bootstrap complete / 動態 K 線引導完成"
        );
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Arm D: pending order registration from dispatch task.
// Arm D：dispatch task 推送的 pending order 註冊。
// ─────────────────────────────────────────────────────────────────────────────

/// Arm D handler: receive `PendingOrder` from the dispatch task, insert into
/// `state.pending_orders`, and emit two trading-msg rows (Order + Working
/// OrderStateChange) for audit.
/// Arm D handler：從 dispatch task 收 `PendingOrder`，插入
/// `state.pending_orders` 並寫出 Order + Working OrderStateChange 兩筆審計列。
pub(super) fn handle_pending_registration(
    reg: Option<PendingOrder>,
    pipeline: &TickPipeline,
    state: &mut LoopState,
    order_tx: Option<&tokio::sync::mpsc::Sender<crate::database::TradingMsg>>,
) {
    if let Some(po) = reg {
        tracing::info!(
            order_link_id = %po.order_link_id, symbol = %po.symbol,
            qty = %po.qty, strategy = %po.strategy,
            "pending order registered / 待處理訂單已註冊"
        );
        // Emit Order row when exchange confirms Working state.
        // 訂單進入 Working 狀態時寫入 trading.orders。
        if let Some(tx) = order_tx {
            let em = pipeline.effective_engine_mode().to_string();
            let _ = tx.try_send(crate::database::TradingMsg::Order {
                order_id: po.order_link_id.clone(),
                ts_ms: po.sent_ts_ms,
                symbol: po.symbol.clone(),
                side: if po.is_long { "Buy".into() } else { "Sell".into() },
                order_type: "Market".into(),
                qty: po.qty,
                strategy_name: po.strategy.clone(),
                is_close: po.is_close,
                engine_mode: em.clone(),
            });
            let _ = tx.try_send(crate::database::TradingMsg::OrderStateChange {
                order_id: po.order_link_id.clone(),
                ts_ms: po.sent_ts_ms,
                from_status: Some("Submitted".into()),
                to_status: "Working".into(),
                filled_qty: None,
                avg_price: None,
                reason: None,
                engine_mode: em,
            });
        }
        state.pending_orders.insert(po.order_link_id.clone(), po);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Arm E: IPC paper command dispatch (async — delete_checkpoint().await).
// Arm E：IPC paper 命令派遣（async — delete_checkpoint().await）。
// ─────────────────────────────────────────────────────────────────────────────

/// Arm E handler: dispatch a `PipelineCommand` variant received over the IPC
/// pipeline. Two variants are intercepted at this level:
///   - `DisableEdgePredictorAll` — runs full EDGE-P3-1 Step 7e two-phase
///     commit + V014 audit via `handlers::handle_disable_edge_predictor_all`.
///   - `ResetDrawdownBaseline` — P1-5 A2 in-memory reset + awaited DB DELETE
///     on the checkpoint row so Python only sees success once the persisted
///     row is gone.
/// All other variants flow through `handlers::handle_paper_command`. After
/// command handling, governor risk level is synced to `shared_risk_level` and
/// a CircuitBreakerTripped event is broadcast to peer pipelines if the
/// current level is CircuitBreaker.
/// Arm E handler：派遣 IPC `PipelineCommand`。
///   - `DisableEdgePredictorAll` 走 EDGE-P3-1 Step 7e 兩階段 + V014 審計。
///   - `ResetDrawdownBaseline` 走 P1-5 A2 記憶體重置 + DB DELETE 同步 await。
///   - 其餘走 `handlers::handle_paper_command`。
///   命令處理後同步 governor 風控級別到 `shared_risk_level`；若當前級別為
///   CircuitBreaker，向對等管線廣播事件。
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
    let Some(cmd) = cmd else {
        return;
    };
    // EDGE-P3-1 Step 7e: intercept the kill-switch variant so the
    // production path runs the full two-phase commit + V014 audit.
    // All other variants still flow through handle_paper_command.
    // EDGE-P3-1 Step 7e：截獲 kill-switch 變體，跑完整兩階段 + V014 審計；
    // 其餘變體仍走 handle_paper_command。
    match cmd {
        PipelineCommand::DisableEdgePredictorAll {
            operator_token,
            reason,
            response_tx,
        } => {
            let em_for_audit = pipeline.effective_engine_mode();
            handlers::handle_disable_edge_predictor_all(
                operator_token,
                reason,
                response_tx,
                pipeline,
                em_for_audit,
                audit_pool,
            );
        }
        // P1-5 A2: operator-driven drawdown baseline reset.
        // In-memory reset is synchronous; DB row DELETE is awaited
        // inline so Python receives confirmation only AFTER the
        // persisted checkpoint is gone (avoids "looks reset but
        // next restart resurrects old peak" race). If DB write
        // fails, respond Err but keep the in-memory reset — the
        // next writer cycle will try to UPSERT the NEW (= current
        // balance) peak, effectively re-pinning the baseline
        // somewhere safe.
        // P1-5 A2：operator 重置 drawdown 基準。記憶體同步重置、
        // DB DELETE 同步 await，讓 Python 在 row 真正刪除後才收到
        // 確認；DB 失敗時仍保留記憶體重置，下個寫入週期會把新
        // (=當前 balance) peak 重新 UPSERT。
        PipelineCommand::ResetDrawdownBaseline { response_tx } => {
            let em_for_reset = pipeline.effective_engine_mode().to_string();
            let peak_before = pipeline.paper_state.peak_balance();
            let balance_before = pipeline.paper_state.balance();
            pipeline.paper_state.reset_drawdown_baseline();
            let db_result = if let Some(pool) = audit_pool {
                crate::paper_state::checkpoint::delete_checkpoint(pool, &em_for_reset).await
            } else {
                Ok(())
            };
            let reply = match db_result {
                Ok(()) => {
                    tracing::info!(
                        engine_mode = %em_for_reset,
                        peak_before,
                        peak_after = pipeline.paper_state.peak_balance(),
                        balance = balance_before,
                        "P1-5 A2: drawdown baseline reset via IPC \
                         / 已通過 IPC 重置 drawdown 基準"
                    );
                    snapshot_writer.force_write(&pipeline.snapshot());
                    Ok(format!(
                        "reset engine_mode={em_for_reset} \
                         peak_before={peak_before:.2} \
                         peak_after={balance_before:.2}"
                    ))
                }
                Err(e) => {
                    tracing::warn!(
                        engine_mode = %em_for_reset,
                        error = %e,
                        "P1-5 A2: checkpoint DELETE failed (memory already reset) \
                         / checkpoint 刪除失敗（記憶體已重置）"
                    );
                    Err(format!("DB delete failed: {e}"))
                }
            };
            let _ = response_tx.send(reply);
        }
        other => {
            handlers::handle_paper_command(
                other,
                pipeline,
                snapshot_writer,
                &mut state.pending_orders,
            );
        }
    }
    // Phase 6: sync governor risk level to shared atomic for reconciler.
    // Phase 6：同步 governor 風控級別到共享原子量供對帳器讀取。
    let current_level = pipeline.governance.risk.snapshot_level();
    if let Some(rl) = shared_risk_level {
        rl.store(current_level.value(), std::sync::atomic::Ordering::Relaxed);
    }

    // BLOCKER-2 D6: Broadcast CircuitBreaker event to peer pipelines.
    // BLOCKER-2 D6：向對等管線廣播熔斷事件。
    if current_level == openclaw_core::sm::risk_gov::RiskLevel::CircuitBreaker {
        if let Some(tx) = cross_engine_tx {
            let _ = tx.send(EngineEvent::CircuitBreakerTripped(pipeline_kind));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn loop_state_new_has_empty_collections_and_fresh_clocks() {
        let mut seed = std::collections::HashSet::new();
        seed.insert("BTCUSDT".to_string());
        let state = LoopState::new(seed);

        assert!(state.pending_orders.is_empty());
        assert!(state.order_id_to_link.is_empty());
        assert!(state.seen_exec_set.is_empty());
        assert!(state.seen_exec_order.is_empty());
        assert_eq!(state.known_symbols.len(), 1);
        assert!(state.known_symbols.contains("BTCUSDT"));
        // Clocks seeded to same Instant → Duration between them should be near 0.
        // 兩個時鐘以同一 Instant 初始化 → 之間 Duration 應接近 0。
        let gap = state
            .last_pending_check
            .saturating_duration_since(state.last_status);
        assert!(gap.as_millis() <= 2);
    }

    #[test]
    fn max_seen_exec_ids_is_500() {
        // Sentinel test — guards the documented dedup-window size so any
        // accidental downward edit is caught here rather than in prod.
        // 哨兵測試 — 守住 dedup window 尺寸，意外改小不會溜進生產。
        assert_eq!(LoopState::MAX_SEEN_EXEC_IDS, 500);
    }
}
