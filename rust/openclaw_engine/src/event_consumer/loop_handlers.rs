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
use std::ops::ControlFlow;
use std::sync::Arc;
use std::time::{Duration, Instant};

use super::handlers;
use super::pending_sweep::{self, classify_pending_sweep, PendingSweepAction};
use super::types::{ExchangeEvent, PendingOrder};
use crate::persistence::{AuditWriter, DualStateWriter, StateWriter};
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

// ─────────────────────────────────────────────────────────────────────────────
// Arm C: exchange events (fills / order updates / position / DCP / disconnect).
// Arm C：交易所事件（成交 / 訂單狀態 / 持倉 / DCP / 斷連）。
// ─────────────────────────────────────────────────────────────────────────────

/// Arm C handler: dispatch a single `ExchangeEvent` variant:
///   - `Fill`: dedup by exec_id (P0-2 + FIX-33 O(1) HashSet + VecDeque FIFO),
///     parse exec fields, estimate missing exec_fee via per-symbol rate
///     (FIX-19b), match pending order by `order_id → order_link_id` mapping
///     (P0-1 fallback to symbol+side scan), call `pipeline.apply_confirmed_fill`
///     with signal-time context_id (FILL-CONTEXT-LINKAGE-1), emit
///     OrderStateChange Working → Filled/PartiallyFilled, remove fully-filled
///     tracker rows.
///   - `OrderUpdate`: populate `order_id_to_link` mapping; on terminal status
///     (Cancelled/Rejected/Deactivated) classify reject reason (EDGE-P2-3
///     Phase 1B-2), clear pending_close flag for close orders (P0-4), emit
///     OrderStateChange with reject category label, remove tracker row.
///   - `PositionUpdate`: mirror exchange position state into paper_state
///     (B-1 Phase 2); `side="None"` / empty → flat (size=0).
///   - `DcpTriggered`: exchange auto-cancelled all orders → clear tracker rows +
///     `clear_all_pending_close`.
///   - `Disconnected`: private WS down → warn with pending-order count.
///
/// Note: original `continue` semantics (line 124 pre-refactor) become early
/// `return` from this fn; next select! iteration naturally enters the next
/// arm — behaviourally equivalent.
/// Arm C handler：分派單個 `ExchangeEvent`。原版 `continue` 語意改為 fn
/// 內 early `return`，下個 select! 迭代自然進下一 arm，行為等價。
pub(super) fn handle_exchange_event(
    evt: Option<ExchangeEvent>,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut DualStateWriter,
    state: &mut LoopState,
    order_tx: Option<&tokio::sync::mpsc::Sender<crate::database::TradingMsg>>,
) {
    match evt {
        Some(ExchangeEvent::Fill(exec)) => {
            // P0-2: Dedup by exec_id (prevent duplicate fill on WS reconnect)
            // FIX-33: O(1) HashSet lookup instead of O(n) VecDeque scan.
            if state.seen_exec_set.contains(&exec.exec_id) {
                tracing::warn!(exec_id = %exec.exec_id, "duplicate fill skipped / 重複成交已跳過");
                return;
            }
            state.seen_exec_set.insert(exec.exec_id.clone());
            state.seen_exec_order.push_back(exec.exec_id.clone());
            if state.seen_exec_order.len() > LoopState::MAX_SEEN_EXEC_IDS {
                if let Some(old) = state.seen_exec_order.pop_front() {
                    state.seen_exec_set.remove(&old);
                }
            }

            let exec_qty: f64 = exec.exec_qty.parse().unwrap_or(0.0);
            let exec_price: f64 = exec.exec_price.parse().unwrap_or(0.0);
            let exec_ts: u64 = exec.exec_time.parse().unwrap_or(0);

            // FIX-19: execution.fast topic omits execFee/feeRate fields.
            // When the field is empty or unparseable, estimate fee from
            // notional × per-symbol fee rate so PnL accounting stays correct.
            // FIX-19b: Use pipeline.intent_processor.fee_rate(symbol) for
            // per-symbol resolution (AccountManager → legacy → constant).
            // FIX-19：execution.fast 不帶 execFee，空值時用名義值×手續費率估算。
            // FIX-19b：改用 per-symbol 費率（AccountManager → 單一費率 → 常量）。
            let exec_fee: f64 = {
                let parsed = exec.exec_fee.parse::<f64>().unwrap_or(0.0);
                if parsed == 0.0 && exec_qty > 0.0 && exec_price > 0.0 {
                    let fee_rate = pipeline.intent_processor.fee_rate(&exec.symbol);
                    let estimated = exec_qty * exec_price * fee_rate;
                    if estimated > 0.0 {
                        tracing::debug!(
                            exec_id = %exec.exec_id,
                            symbol = %exec.symbol,
                            notional = exec_qty * exec_price,
                            fee_rate,
                            estimated_fee = estimated,
                            "FIX-19b: execFee missing, estimated from per-symbol rate \
                             / execFee 缺失，使用 per-symbol 費率估算"
                        );
                    }
                    estimated
                } else {
                    parsed
                }
            };

            tracing::info!(
                exec_id = %exec.exec_id,
                order_id = %exec.order_id,
                symbol = %exec.symbol,
                side = %exec.side,
                qty = exec_qty,
                price = exec_price,
                fee = exec_fee,
                "exchange fill received / 收到交易所成交"
            );

            // P0-1 fix: Match fill via order_id → order_link_id mapping
            // OrderUpdate populates the mapping, Fill uses it
            let matched_key = state
                .order_id_to_link
                .get(&exec.order_id)
                .cloned()
                .or_else(|| {
                    // Fallback: symbol+side match if no order_id mapping yet
                    let is_buy = exec.side == "Buy";
                    state
                        .pending_orders
                        .iter()
                        .find(|(_, po)| {
                            po.symbol == exec.symbol
                                && po.is_long == is_buy
                                && po.cum_filled_qty < po.qty
                        })
                        .map(|(k, _)| k.clone())
                });

            if let Some(key) = matched_key {
                if let Some(po) = state.pending_orders.get_mut(&key) {
                    po.cum_filled_qty += exec_qty;
                    // FILL-CONTEXT-LINKAGE-1: thread signal-time context_id
                    // from PendingOrder into apply_confirmed_fill so
                    // trading.fills.entry_context_id matches
                    // learning.decision_features.context_id.
                    // FILL-CONTEXT-LINKAGE-1：將 PendingOrder 帶的
                    // 訊號時刻 context_id 傳入 apply_confirmed_fill，
                    // 使 trading.fills.entry_context_id 與
                    // learning.decision_features.context_id 對齊。
                    pipeline.apply_confirmed_fill(
                        &exec.symbol,
                        po.is_long,
                        exec_qty,
                        exec_price,
                        exec_fee,
                        exec_ts,
                        &po.strategy,
                        &po.context_id,
                        &po.order_link_id,
                    );
                    snapshot_writer.force_write(&pipeline.snapshot());

                    let fully_filled = po.cum_filled_qty >= po.qty * 0.999;
                    // Emit order state change: Working → Filled / PartiallyFilled.
                    // 發出訂單狀態轉換：Working → Filled / PartiallyFilled。
                    if let Some(tx) = order_tx {
                        let em = pipeline.effective_engine_mode().to_string();
                        let to_status = if fully_filled { "Filled" } else { "PartiallyFilled" };
                        let _ = tx.try_send(crate::database::TradingMsg::OrderStateChange {
                            order_id: po.order_link_id.clone(),
                            ts_ms: exec_ts,
                            from_status: Some("Working".into()),
                            to_status: to_status.into(),
                            filled_qty: Some(po.cum_filled_qty),
                            avg_price: Some(exec_price),
                            reason: None,
                            engine_mode: em,
                        });
                    }

                    if fully_filled {
                        tracing::info!(order_link_id = %key, "pending order fully filled, removing / 待處理訂單完全成交，移除");
                        state.pending_orders.remove(&key);
                    }
                }
            } else {
                tracing::warn!(
                    symbol = %exec.symbol, side = %exec.side,
                    "exchange fill has no matching pending order / 交易所成交無匹配的待處理訂單"
                );
            }
        }
        Some(ExchangeEvent::OrderUpdate(order)) => {
            // P0-1: Build order_id → order_link_id mapping for fill matching
            if !order.order_link_id.is_empty() && !order.order_id.is_empty() {
                state
                    .order_id_to_link
                    .insert(order.order_id.clone(), order.order_link_id.clone());
            }
            // Match by order_link_id directly
            if !order.order_link_id.is_empty() {
                if state.pending_orders.get_mut(&order.order_link_id).is_some() {
                    let status = &order.order_status;
                    tracing::info!(
                        order_link_id = %order.order_link_id,
                        status = %status,
                        symbol = %order.symbol,
                        "pending order status update / 待處理訂單狀態更新"
                    );
                    if status == "Cancelled" || status == "Rejected" || status == "Deactivated" {
                        // EDGE-P2-3 Phase 1B-2: classify Bybit's rejectReason
                        // string (non-empty only on terminal status). Surface
                        // PostOnly-cross at warn! so it's grep-able; route
                        // the short category label into DB `reason` so the
                        // audit log is queryable without parsing free-form
                        // strings. Strategy callback wiring lands in 1B-3.
                        // EDGE-P2-3 Phase 1B-2：分類 Bybit rejectReason 字串。
                        // PostOnly-cross 以 warn! 顯性記錄；短標籤進 DB reason。
                        let reject_category = crate::strategies::maker_rejection::classify(
                            &order.reject_reason,
                        );
                        let reject_label = reject_category.label();
                        if reject_category.is_post_only_cross() {
                            tracing::warn!(
                                order_link_id = %order.order_link_id,
                                symbol = %order.symbol,
                                status = %status,
                                reject_reason = %order.reject_reason,
                                "maker order rejected: PostOnly would have crossed \
                                 / maker 掛單遭拒：PostOnly 會越過 book"
                            );
                        } else if reject_category.is_backpressure() {
                            tracing::warn!(
                                order_link_id = %order.order_link_id,
                                symbol = %order.symbol,
                                status = %status,
                                reject_reason = %order.reject_reason,
                                "maker order rejected: account-level backpressure \
                                 / maker 掛單遭拒：帳戶級背壓"
                            );
                        }
                        // P0-4: If this was a close order, clear pending_close flag
                        // P0-4：如果是平倉訂單，清除待處理平倉標記
                        if let Some(po) = state.pending_orders.get(&order.order_link_id) {
                            if po.is_close {
                                pipeline.clear_pending_close(&po.symbol);
                                tracing::warn!(
                                    order_link_id = %order.order_link_id,
                                    symbol = %po.symbol,
                                    "close order {} — clearing pending_close / 平倉訂單{} — 清除待處理平倉",
                                    status, status,
                                );
                            }
                            // Emit order state change: Working → Cancelled/Rejected.
                            // EDGE-P2-3 Phase 1B-2: append classified reject label
                            // when Bybit provided a rejectReason; keeps legacy
                            // `exchange_status:{status}` prefix stable for any
                            // consumer grepping the reason column.
                            // 發出訂單狀態轉換：Working → Cancelled/Rejected。
                            // 1B-2：若 Bybit 附 rejectReason，追加分類短標；保留
                            // legacy `exchange_status:{status}` 前綴以維持下游相容。
                            let reason_str = if order.reject_reason.is_empty() {
                                format!("exchange_status:{}", status)
                            } else {
                                format!(
                                    "exchange_status:{}|reject={}|category={}",
                                    status, order.reject_reason, reject_label,
                                )
                            };
                            if let Some(tx) = order_tx {
                                let em = pipeline.effective_engine_mode().to_string();
                                let _ = tx.try_send(crate::database::TradingMsg::OrderStateChange {
                                    order_id: po.order_link_id.clone(),
                                    ts_ms: openclaw_core::now_ms(),
                                    from_status: Some("Working".into()),
                                    to_status: status.to_string(),
                                    filled_qty: None,
                                    avg_price: None,
                                    reason: Some(reason_str),
                                    engine_mode: em,
                                });
                            }
                        }
                        tracing::warn!(
                            order_link_id = %order.order_link_id,
                            status = %status,
                            reject_category = %reject_label,
                            "pending order failed — removing / 待處理訂單失敗，移除"
                        );
                        state.pending_orders.remove(&order.order_link_id);
                    }
                }
            }
        }
        Some(ExchangeEvent::PositionUpdate(pos)) => {
            // B-1 Phase 2: Mirror exchange position state into paper_state.
            // size==0 → remove; size>0 → upsert with avg_price as entry.
            // We treat side=="None" / empty side as "flat" (size==0 path).
            // B-1 Phase 2：將交易所持倉狀態映射回 paper_state。
            // size==0 視為平倉並移除；size>0 則 upsert（avg_price 作為入場價）。
            // side=="None" 或空字串視為 flat（走 size==0 邏輯）。
            let size: f64 = pos.size.parse().unwrap_or(0.0);
            let avg_price: f64 = pos.avg_price.parse().unwrap_or(0.0);
            let is_long = pos.side.eq_ignore_ascii_case("Buy");
            let now_ms = openclaw_core::now_ms();
            // Bybit returns side=="None" when the position is flat — coerce
            // size to 0 so upsert removes any stale local entry.
            // Bybit 在持倉為空時回傳 side=="None"，強制 size 為 0 以移除舊條目。
            let effective_size = if pos.side.eq_ignore_ascii_case("None") || pos.side.is_empty() {
                0.0
            } else {
                size
            };
            let changed = pipeline.paper_state.upsert_position_from_exchange(
                &pos.symbol,
                is_long,
                effective_size,
                avg_price,
                now_ms,
            );
            if changed {
                tracing::info!(
                    symbol = %pos.symbol,
                    side = %pos.side,
                    size = effective_size,
                    avg_price = avg_price,
                    kind = %pipeline.pipeline_kind,
                    "B-1 Phase 2: paper_state synced from WS position update \
                     / paper_state 已根據 WS 持倉更新同步"
                );
                snapshot_writer.force_write(&pipeline.snapshot());
            }
        }
        Some(ExchangeEvent::DcpTriggered) => {
            // DCP: Exchange auto-cancelled all orders
            let count = state.pending_orders.len();
            if count > 0 {
                tracing::warn!(
                    count = count,
                    "DCP triggered — clearing {} pending orders / DCP 觸發，清除 {} 個待處理訂單",
                    count, count,
                );
                state.pending_orders.clear();
            }
            // Also clear pending_close flags since DCP cancelled close orders too
            pipeline.clear_all_pending_close();
            tracing::warn!("DCP triggered — exchange cancelled active orders, pending_close cleared");
        }
        Some(ExchangeEvent::Disconnected) => {
            // Private WS disconnected — pending orders may be in unknown state
            if !state.pending_orders.is_empty() {
                tracing::warn!(
                    pending = state.pending_orders.len(),
                    "private WS disconnected with {} pending orders — reconcile on reconnect \
                    / 私有 WS 斷連，{} 個待處理訂單 — 重連後對賬",
                    state.pending_orders.len(), state.pending_orders.len(),
                );
            }
        }
        None => {} // channel closed
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Arm F: main tick event — on_tick / audit fills / shared state sync /
// pending sweep / status report / D2 registry diff + D3 kline bootstrap spawn.
// Arm F：主 tick 事件 — on_tick / 成交審計 / 共享狀態同步 / pending 掃描 /
// 狀態報告 / D2 註冊表差分 + D3 K 線引導 spawn。
// ─────────────────────────────────────────────────────────────────────────────

/// Arm F handler: process one PriceEvent tick. The signature is wide because
/// Arm F is the tick-level hot path that stitches together a lot of the
/// engine's periodic work (H0Gate risk snapshot, WS shared state sync,
/// per-tick pending sweep + exchange reconciler, status-interval snapshot +
/// checkpoint + scanner D2 diff + D3 kline bootstrap). Returns
/// `ControlFlow::Break(())` when the event channel is closed (mirrors the
/// pre-refactor `None => break` in mod.rs so the outer select! loop exits).
/// Arm F handler：處理單個 PriceEvent tick。簽章寬是因為 Arm F 是 tick 級
/// 熱路徑，縫合許多週期性工作。event channel close 時回
/// `ControlFlow::Break(())` 讓外層 select! loop 退出。
#[allow(clippy::too_many_arguments)]
pub(super) fn handle_tick_event(
    evt: Option<Arc<openclaw_types::PriceEvent>>,
    pipeline: &mut TickPipeline,
    state_writer: &mut StateWriter,
    snapshot_writer: &mut DualStateWriter,
    audit_writer: &AuditWriter,
    state: &mut LoopState,
    start_time: Instant,
    status_interval: Duration,
    pending_timeout: Duration,
    shared_last_tick_ms: Option<&Arc<std::sync::atomic::AtomicU64>>,
    shared_bybit_balance: Option<&Arc<parking_lot::RwLock<Option<f64>>>>,
    shared_api_pnl: Option<&Arc<parking_lot::RwLock<HashMap<String, f64>>>>,
    canary_handle: &crate::canary_writer::CanaryWriterHandle,
    shared_client: Option<&Arc<crate::bybit_rest_client::BybitRestClient>>,
    audit_pool: Option<&sqlx::PgPool>,
    symbol_registry: Option<&Arc<crate::scanner::registry::SymbolRegistry>>,
    cfg_snapshot: &Arc<crate::config::EngineBootstrap>,
    bootstrap_client: Option<&Arc<crate::bybit_rest_client::BybitRestClient>>,
    kline_seed_tx: &tokio::sync::mpsc::Sender<(String, Vec<openclaw_core::klines::KlineBar>)>,
) -> ControlFlow<()> {
    let Some(ev) = evt else {
        return ControlFlow::Break(());
    };

    // F-5: Update shared last_tick_ms for quality monitor
    if let Some(tick_ms) = shared_last_tick_ms {
        tick_ms.store(ev.ts_ms, std::sync::atomic::Ordering::Relaxed);
    }
    let prev_fills = pipeline.stats.total_fills;
    let canary_record = pipeline.on_tick(&ev);

    // ENGINE-HEAL-FIX-PHASE1 R1: Hand the record to the dedicated
    // canary writer task — non-blocking. On channel-full the record
    // is dropped with a warn (handled inside try_send); the event
    // loop never blocks on file I/O.
    // ENGINE-HEAL-FIX-PHASE1 R1：交給專用灰度寫入任務（非阻塞）；
    // 通道滿則 warn 丟棄，事件循環絕不阻塞於檔案 I/O。
    if let Some(record) = canary_record {
        canary_handle.try_send(record);
    }

    // Audit new fills / 審計新成交
    if pipeline.stats.total_fills > prev_fills {
        let snap = pipeline.paper_state.export_state();
        let _ = audit_writer.append(&serde_json::json!({
            "ts": ev.ts_ms,
            "symbol": ev.symbol,
            "price": ev.last_price,
            "fills": pipeline.stats.total_fills,
            "balance": snap.balance,
            "positions": snap.positions.len(),
            "realized_pnl": snap.total_realized_pnl,
        }));
        tracing::info!(
            symbol = %ev.symbol,
            price = ev.last_price,
            fills = pipeline.stats.total_fills,
            balance = format!("{:.2}", snap.balance),
            positions = snap.positions.len(),
            "new fill / 新成交"
        );
    }

    // H1+H2 fix: Sync WS shared state → paper_state
    // BLOCKER-6: parking_lot RwLock — read()/write() return guards directly.
    // BLOCKER-6：parking_lot RwLock — read()/write() 直接回傳 guard。
    if let Some(bal_arc) = shared_bybit_balance {
        let maybe_bal = *bal_arc.read();
        if let Some(bal) = maybe_bal {
            pipeline.paper_state.set_bybit_sync_balance(Some(bal));
            // P0-5: Reconcile local balance from exchange only in exchange pipelines.
            // 3E-4: pipeline_kind is immutable — no dynamic mode check needed.
            // P0-5：僅在交易所管線中對賬本地餘額。3E-4：pipeline_kind 不可變。
            let current_is_exchange = pipeline.pipeline_kind.is_exchange();
            if current_is_exchange {
                if let Some(old_bal) = pipeline.paper_state.reconcile_balance_from_exchange(bal) {
                    tracing::warn!(
                        old = format!("{:.2}", old_bal),
                        new = format!("{:.2}", bal),
                        "balance reconciled from exchange / 餘額已從交易所對賬"
                    );
                }
            }
        }
    }
    if let Some(pnl_arc) = shared_api_pnl {
        let guard = pnl_arc.read();
        for (symbol, &pnl) in guard.iter() {
            pipeline.paper_state.set_api_unrealized_pnl(symbol, pnl);
        }
    }

    // EXT-1 + EDGE-P2-3 Phase 1B-3.2: Sweep timed-out pending orders (every 5s).
    // Branch by TimeInForce:
    //   - PostOnly maker: once elapsed >= po.maker_timeout_ms (default 45s),
    //     spawn non-blocking REST cancel via orderLinkId + remove tracker row.
    //   - Market (legacy): 5s soft warn / 60s hard remove (unchanged).
    // Tracker row removal after cancel is intentional — if a race fills the
    // order between our sweep and Bybit's cancel processing, the existing
    // legacy hard-remove semantics apply (unmatched WS fill goes through the
    // position reconciler). A stricter "wait-for-cancel-ack then remove"
    // pattern is deferred to an FUP.
    // EDGE-P2-3 Phase 1B-3.2：超時 pending order 掃描（每 5s）。
    //   - PostOnly 掛單：elapsed >= maker_timeout_ms（預設 45s）→ 非阻塞 REST 取消 + 移除。
    //   - Market（舊行為）：5s 軟警告 / 60s 硬移除，不變。
    if !state.pending_orders.is_empty() && state.last_pending_check.elapsed() >= pending_timeout {
        let now_ms = openclaw_core::now_ms();
        let mut maker_to_cancel: Vec<(String, String, u64, u64)> = Vec::new();
        let mut legacy_to_remove: Vec<String> = Vec::new();
        for (key, po) in state.pending_orders.iter() {
            let elapsed = now_ms.saturating_sub(po.sent_ts_ms);
            match classify_pending_sweep(po, elapsed) {
                PendingSweepAction::MakerTimeoutCancel => {
                    let deadline_ms = po.maker_timeout_ms.unwrap_or(45_000);
                    maker_to_cancel.push((
                        key.clone(),
                        po.symbol.clone(),
                        elapsed,
                        deadline_ms,
                    ));
                }
                PendingSweepAction::LegacyHardRemove => {
                    tracing::error!(
                        order_link_id = %key,
                        symbol = %po.symbol,
                        elapsed_ms = elapsed,
                        "pending order hard timeout (>60s) — removing / 待處理訂單硬超時，移除"
                    );
                    legacy_to_remove.push(key.clone());
                }
                PendingSweepAction::LegacySoftWarn => {
                    tracing::warn!(
                        order_link_id = %key,
                        symbol = %po.symbol,
                        elapsed_ms = elapsed,
                        filled = %po.cum_filled_qty,
                        requested = %po.qty,
                        "pending order soft timeout (>5s) / 待處理訂單軟超時"
                    );
                }
                PendingSweepAction::Keep => {}
            }
        }
        // Dispatch non-blocking cancels for timed-out PostOnly makers.
        // 非阻塞派發超時 PostOnly 掛單取消。
        for (link_id, symbol, elapsed, deadline_ms) in &maker_to_cancel {
            tracing::warn!(
                order_link_id = %link_id,
                symbol = %symbol,
                elapsed_ms = elapsed,
                deadline_ms = deadline_ms,
                reason = "maker_timeout_cancel",
                "PostOnly maker timed out — cancelling via orderLinkId / PostOnly 掛單超時 — 以 orderLinkId 取消"
            );
            if let Some(client) = shared_client {
                let c = client.clone();
                let sym = symbol.clone();
                let lid = link_id.clone();
                tokio::spawn(async move {
                    pending_sweep::cancel_resting_maker_order(c, sym, lid).await;
                });
            }
        }
        // Remove maker rows we just dispatched cancels for.
        // 移除剛派發取消的 maker 訂單記錄。
        for (link_id, _, _, _) in &maker_to_cancel {
            state.pending_orders.remove(link_id);
        }
        // Remove legacy Market hard-timeout rows.
        // 移除舊 Market 硬超時記錄。
        for key in &legacy_to_remove {
            state.pending_orders.remove(key);
        }
        // Clean stale order_id mappings: only keep those with active pending orders
        // 清理過期 order_id 映射：僅保留有活躍待處理訂單的
        if state.order_id_to_link.len() > 50 {
            let active_links: std::collections::HashSet<&String> =
                state.pending_orders.keys().collect();
            state.order_id_to_link.retain(|_, link| active_links.contains(link));
        }
        state.last_pending_check = Instant::now();
        // R-02: Cross-check pipeline pending_close_symbols against open positions.
        // Clears stale flags for symbols whose close fill was already processed.
        // R-02：與實際持倉交叉驗證，清理已成交但標記未清除的 pending-close 殘留。
        pipeline.reconcile_pending_exchange_orders();
    }

    // RRC-1-A2: Periodic H0Gate risk snapshot update (every status interval).
    // RRC-1-A2：定期更新 H0 門控風控快照（每狀態報告間隔）。
    if state.last_status.elapsed() >= status_interval {
        let positions = pipeline.paper_state.positions();
        let position_count = positions.len() as u32;
        let balance = pipeline.paper_state.export_state().balance;
        let total_exposure_pct = if balance > 0.0 {
            let total_notional: f64 = positions
                .iter()
                .map(|p| {
                    let price = pipeline
                        .latest_prices()
                        .get(&p.symbol)
                        .copied()
                        .unwrap_or(p.entry_price);
                    p.qty * price
                })
                .sum();
            (total_notional / balance * 100.0).min(999.0)
        } else {
            0.0
        };
        pipeline.h0_gate.update_risk(openclaw_types::H0GateRiskSnapshot {
            open_position_count: position_count,
            total_exposure_pct,
            cooldown_until_ts_ms: 0,
            kill_switch_active: false,
            snapshot_ts_ms: openclaw_core::now_ms(),
        });

        let status = pipeline.status();
        let uptime = start_time.elapsed().as_secs();
        let h0_stats = pipeline.h0_gate.get_stats();
        // PNL-2: invariant — every tick must run H0Gate.check.
        // PNL-2：不變量 — 每個 tick 必須走過 H0Gate.check。
        // If ticks > 0 but checks == 0 → stale binary or wiring regression.
        // 若 ticks > 0 而 checks == 0 → stale binary 或接線退化。
        if status.stats.total_ticks > 0 && h0_stats.total_checks == 0 {
            tracing::warn!(
                ticks = status.stats.total_ticks,
                "PNL-2 invariant violated: ticks>0 but H0Gate checks==0 — stale binary? / H0 門控未執行"
            );
        }
        tracing::info!(
            ticks = status.stats.total_ticks,
            fills = status.stats.total_fills,
            intents = status.stats.total_intents,
            stops = status.stats.total_stops,
            balance = format!("{:.2}", status.balance),
            positions = status.positions,
            symbols = status.symbols_tracked,
            uptime_secs = uptime,
            h0_checks = h0_stats.total_checks,
            h0_blocked = h0_stats.total_blocked(),
            h0_shadow_would_block = h0_stats.shadow_would_block,
            "status report / 狀態報告"
        );
        let snap = pipeline.paper_state.export_state();
        state_writer.maybe_write(&snap);
        let full_snap = pipeline.snapshot();
        snapshot_writer.maybe_write(&full_snap);

        // P1-5 A2: piggy-back checkpoint UPSERT on the state-writer
        // cadence (~30s per engine). Detached spawn so the event loop
        // isn't blocked on the DB round-trip. `audit_pool.clone()` is
        // cheap (Arc<Inner>). Fail-soft: warn logs live inside
        // `write_checkpoint`, next tick will retry.
        // P1-5 A2：在狀態寫入週期（每引擎 ~30s）順手 UPSERT checkpoint。
        // 分離 spawn 避免阻塞事件迴圈；pool clone 為 Arc 廉價。
        // fail-soft：write_checkpoint 內部 warn log，下週期重試。
        if let Some(pool) = audit_pool {
            let pool_clone = pool.clone();
            let em = pipeline.effective_engine_mode().to_string();
            let peak = pipeline.paper_state.peak_balance();
            let session_start_ts_ms = pipeline.paper_state.session_start_ts_ms();
            tokio::spawn(async move {
                if let Err(e) = crate::paper_state::checkpoint::write_checkpoint(
                    &pool_clone,
                    &em,
                    peak,
                    session_start_ts_ms,
                )
                .await
                {
                    tracing::warn!(
                        engine_mode = %em,
                        error = %e,
                        "P1-5 A2: checkpoint UPSERT failed (will retry next cycle) \
                         / checkpoint 寫入失敗，下週期重試"
                    );
                }
            });
        }

        // D2: Diff registry vs known_symbols → add/remove from pipeline.
        // Runs every status interval (30s); scanner cycle is 30 min,
        // so changes are reflected within one interval.
        // D2：差分注冊表與 known_symbols → 從管線增減交易對。
        // 每狀態報告間隔（30s）執行；掃描器週期 30 分鐘，
        // 變更在一個間隔內反映。
        if let Some(reg) = symbol_registry {
            let current: std::collections::HashSet<String> = reg.snapshot().into_iter().collect();
            let to_add: Vec<String> = current.difference(&state.known_symbols).cloned().collect();
            let to_remove: Vec<String> =
                state.known_symbols.difference(&current).cloned().collect();

            for sym in &to_remove {
                pipeline.remove_symbol(sym);
                state.known_symbols.remove(sym);
                tracing::info!(symbol = %sym,
                      "D2: scanner removed symbol from pipeline \
                       / 掃描器從管線移除交易對");
            }

            for sym in &to_add {
                pipeline.add_symbol(sym);
                state.known_symbols.insert(sym.clone());
                tracing::info!(symbol = %sym,
                      "D2: scanner added symbol to pipeline \
                       / 掃描器向管線添加交易對");

                // D3: Spawn async kline bootstrap for new symbol.
                // D3：為新交易對生成異步 K 線引導。
                if cfg_snapshot.kline_bootstrap {
                    if let Some(client_arc) = bootstrap_client {
                        let sym_owned = sym.clone();
                        let client_clone = Arc::clone(client_arc);
                        let seed_tx = kline_seed_tx.clone();
                        tokio::spawn(async move {
                            let mdc = crate::market_data_client::MarketDataClient::new(client_clone);
                            match mdc
                                .get_klines("linear", &sym_owned, "1", None, None, Some(200))
                                .await
                            {
                                Ok(bars) => {
                                    let now_ms = openclaw_core::now_ms();
                                    let mut core_bars: Vec<openclaw_core::klines::KlineBar> = bars
                                        .iter()
                                        .filter(|b| b.start_time + 60_000 <= now_ms)
                                        .map(|b| openclaw_core::klines::KlineBar {
                                            open_time_ms: b.start_time,
                                            close_time_ms: b.start_time + 60_000,
                                            open: b.open,
                                            high: b.high,
                                            low: b.low,
                                            close: b.close,
                                            volume: b.volume,
                                            turnover: b.turnover,
                                            tick_count: 1,
                                            is_closed: true,
                                        })
                                        .collect();
                                    core_bars.sort_by_key(|b| b.open_time_ms);
                                    let _ = seed_tx.send((sym_owned, core_bars)).await;
                                }
                                Err(e) => {
                                    tracing::warn!(
                                        symbol = %sym_owned,
                                        error = %e,
                                        "D3: dynamic kline bootstrap failed \
                                         / 動態 K 線引導失敗"
                                    );
                                }
                            }
                        });
                    }
                }
            }
        }

        state.last_status = Instant::now();
    }

    ControlFlow::Continue(())
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
