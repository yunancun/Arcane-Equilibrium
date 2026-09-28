//! Arm F handler — 主 tick 事件熱路徑，自 loop_handlers.rs 依職責拆出
//! （EVENT-CONSUMER-SPLIT-2，2026-07-03）；本檔保留現行 §九 2000 行政策空間。

use std::collections::HashMap;
use std::ops::ControlFlow;
use std::sync::Arc;
use std::time::{Duration, Instant};

use super::loop_handlers::{dispatch_close_maker_fallback_from_pending, LoopState};
use super::pending_sweep::{self, classify_pending_sweep, PendingSweepAction};
use crate::order_manager::TimeInForce;
use crate::persistence::{AuditWriter, DualStateWriter, StateWriter};
use crate::strategies::maker_rejection::CloseMakerFallbackReason;
use crate::tick_pipeline::TickPipeline;

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
    // ENGINE-CRASH-FIX C3 (2026-06-15): 牆鐘時間戳 atomic，與 payload-ts 的
    // shared_last_tick_ms 並存（後者保留供資料品質監控）。watchdog 改讀此 atomic。
    shared_last_processed_wallclock_ms: Option<&Arc<std::sync::atomic::AtomicU64>>,
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
    // shared_last_tick_ms 存的是 Bybit payload 的 `ts`（資料品質監控用），
    // 不是牆鐘時間 — 這正是 Fix-4 watchdog 先前誤報的根因（payload-ts 可能
    // 與牆鐘偏移或在重放/補單時非單調）。保留它不動。
    if let Some(tick_ms) = shared_last_tick_ms {
        tick_ms.store(ev.ts_ms, std::sync::atomic::Ordering::Relaxed);
    }
    // ENGINE-CRASH-FIX C3 (2026-06-15): 另存牆鐘時間戳供 tick-stale watchdog。
    // 為什麼分開：watchdog 要偵測「event_consumer loop 真的卡死」(WS 殭屍 /
    // 此 task 被阻塞)，唯一可靠信號是「處理 tick 的牆鐘時間」是否停止前進。
    // 用 payload-ts 比對牆鐘會在 payload 時鐘偏移時誤報；用牆鐘 now_ms 則只有
    // 此 loop 真凍結時才不再前進，移除假陽性又不弱化真殭屍防護。
    if let Some(wall_ms) = shared_last_processed_wallclock_ms {
        let now_ms = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0);
        wall_ms.store(now_ms, std::sync::atomic::Ordering::Relaxed);
    }
    let prev_fills = pipeline.stats.total_fills;
    let canary_record = pipeline.on_tick_at(&ev, openclaw_core::now_ms());
    super::sm_halt_incident::observe_and_dispatch(pipeline, &mut state.sm_halt_incident, "tick");

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
            "funding_pnl": snap.total_funding_pnl,
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

    // 每輪檢查逾時，保留未知結果與取消競態的 execution 匹配。
    // Market 終態逾時／maker cancel grace 到期均不構成移除依據。
    if !state.pending_orders.is_empty() && state.last_pending_check.elapsed() >= pending_timeout {
        sweep_pending_orders(pipeline, state, shared_client, openclaw_core::now_ms());
        state.last_pending_check = Instant::now();
        // R-02: Cross-check pipeline pending_close_symbols against open positions.
        // Clears stale flags for symbols whose close fill was already processed.
        // R-02：與實際持倉交叉驗證，清理已成交但標記未清除的 pending-close 殘留。
        pipeline.reconcile_pending_exchange_orders();
    }

    super::status_report::handle_status_interval(
        pipeline,
        state_writer,
        snapshot_writer,
        state,
        start_time,
        status_interval,
        audit_pool,
        symbol_registry,
        cfg_snapshot,
        bootstrap_client,
        kline_seed_tx,
    );

    ControlFlow::Continue(())
}

/// H1：超時只標記未知並保留匹配；保護性 close fallback 沿用單次去重邊界。
pub(super) fn sweep_pending_orders(
    pipeline: &mut TickPipeline,
    state: &mut LoopState,
    shared_client: Option<&Arc<crate::bybit_rest_client::BybitRestClient>>,
    now_ms: u64,
) {
    let outcomes = state.maker_cancel_outcome_tx.clone();
    sweep_pending_orders_with_cancel(pipeline, state, now_ms, true, &|po, attempt_ms| {
        dispatch_maker_cancel(shared_client, outcomes.as_ref(), po, attempt_ms)
    });
}

/// The independent timer runs deadline cancellation and bounded protection even
/// when public ticks stop. Quote-based repricing remains on the price-tick path.
pub(super) fn handle_confirmation_interval(
    pipeline: &mut TickPipeline,
    state: &mut LoopState,
    now_ms: u64,
    cancel_maker: &dyn Fn(&super::types::PendingOrder, u64) -> bool,
) {
    sweep_pending_orders_with_cancel(pipeline, state, now_ms, false, cancel_maker);
}

#[derive(Debug)]
pub(super) struct MakerCancelOutcome {
    pub order_link_id: String,
    pub registered_ts_ms: u64,
    pub attempt_ts_ms: u64,
    pub acknowledged: bool,
}

pub(super) fn dispatch_maker_cancel(
    shared_client: Option<&Arc<crate::bybit_rest_client::BybitRestClient>>,
    outcomes: Option<&tokio::sync::mpsc::UnboundedSender<MakerCancelOutcome>>,
    po: &super::types::PendingOrder,
    attempt_ts_ms: u64,
) -> bool {
    let (Some(client), Some(outcomes)) = (shared_client, outcomes) else {
        return false;
    };
    let client = client.clone();
    let outcomes = outcomes.clone();
    let symbol = po.symbol.clone();
    let order_link_id = po.order_link_id.clone();
    let registered_ts_ms = po.sent_ts_ms;
    tokio::spawn(async move {
        // Include transport/rate-limiter waiting in the deadline. Completion is
        // returned to the single state owner even on timeout; no overlapping retry.
        let cancel =
            pending_sweep::cancel_resting_maker_order(client, symbol, order_link_id.clone());
        deliver_maker_cancel_outcome(
            cancel,
            outcomes,
            MakerCancelOutcome {
                order_link_id,
                registered_ts_ms,
                attempt_ts_ms,
                acknowledged: false,
            },
            std::time::Duration::from_secs(15),
        )
        .await;
    });
    true
}

pub(super) async fn deliver_maker_cancel_outcome(
    cancel: impl std::future::Future<Output = bool>,
    outcomes: tokio::sync::mpsc::UnboundedSender<MakerCancelOutcome>,
    mut result: MakerCancelOutcome,
    deadline: std::time::Duration,
) {
    result.acknowledged = tokio::time::timeout(deadline, cancel)
        .await
        .unwrap_or(false);
    let _ = outcomes.send(result);
}

pub(super) fn handle_maker_cancel_outcome(
    state: &mut LoopState,
    result: MakerCancelOutcome,
    now_ms: u64,
) {
    let Some(po) = state.pending_orders.get_mut(&result.order_link_id) else {
        return;
    };
    if po.sent_ts_ms != result.registered_ts_ms
        || po.progress.maker_cancel_attempt_ts_ms != Some(result.attempt_ts_ms)
        || po.progress.status.is_terminal()
    {
        return;
    }
    po.progress.maker_cancel_attempt_ts_ms = None;
    // A successful REST response is still only an ACK. Retry the same idempotent
    // cancellation after cooldown if authoritative evidence has not closed it.
    po.progress.maker_cancel_retry_after_ms = Some(now_ms.saturating_add(30_000));
    po.progress
        .reconciliation_retry_after_ms
        .get_or_insert(now_ms);
    if !result.acknowledged {
        tracing::warn!(order_link_id = %result.order_link_id,
            "maker cancel failed/timed out; retry after cooldown while retaining attribution");
    }
}

fn mark_maker_cancel_attempt(state: &mut LoopState, id: &str, now_ms: u64) {
    if let Some(po) = state.pending_orders.get_mut(id) {
        // Preserve the first cancel's grace anchor across failures/retries so
        // protective close fallback cannot be postponed by repeated REST errors.
        po.cancel_requested_ts_ms.get_or_insert(now_ms);
        po.progress.maker_cancel_attempt_ts_ms = Some(now_ms);
        po.progress.maker_cancel_retry_after_ms = None;
    }
}

fn sweep_pending_orders_with_cancel(
    pipeline: &mut TickPipeline,
    state: &mut LoopState,
    now_ms: u64,
    allow_reprice: bool,
    cancel_maker: &dyn Fn(&super::types::PendingOrder, u64) -> bool,
) {
    let mut maker_to_cancel: Vec<(String, String, u64, u64)> = Vec::new();
    let mut maker_grace_fallback: Vec<String> = Vec::new();
    let mut awaiting_confirmation: Vec<String> = Vec::new();
    // MAKER-CLOSE-REPRICE-1：toward-touch 重掛候選。每元素 = (原 order_link_id,
    // 新限價, reprice_count)。只在 PostOnly close maker 仍 Keep（30s-90s 窗、未
    // 達 max_reprices、book 朝對我方向移動）時收集，後續串行 cancel 舊單 + 重發。
    let mut maker_to_reprice: Vec<(String, f64, u32)> = Vec::new();
    for (key, po) in state.pending_orders.iter() {
        if po.progress.status.is_terminal() {
            continue;
        }
        let elapsed = pending_sweep::pending_elapsed_ms(po, now_ms);
        let retry_cancel = po.progress.maker_cancel_attempt_ts_ms.is_none()
            && po
                .progress
                .maker_cancel_retry_after_ms
                .is_some_and(|next| now_ms >= next);
        if retry_cancel {
            maker_to_cancel.push((
                key.clone(),
                po.symbol.clone(),
                elapsed,
                po.maker_timeout_ms.unwrap_or(45_000),
            ));
        }
        // Reprice predecessors may still need their failed cancel retried, but
        // must never generate another replacement or protective fallback.
        if po.progress.replacement_order_link_id.is_some() {
            continue;
        }
        match classify_pending_sweep(po, now_ms) {
            PendingSweepAction::MakerTimeoutCancel => {
                let deadline_ms = po.maker_timeout_ms.unwrap_or(45_000);
                if !retry_cancel && po.progress.maker_cancel_attempt_ts_ms.is_none() {
                    maker_to_cancel.push((key.clone(), po.symbol.clone(), elapsed, deadline_ms));
                }
            }
            PendingSweepAction::MakerCancelGraceExpired => {
                let grace_ms = if po.is_close {
                    pending_sweep::CLOSE_MAKER_CANCEL_ACK_GRACE_MS
                } else {
                    pending_sweep::MAKER_CANCEL_ACK_GRACE_MS
                };
                tracing::error!(
                    order_link_id = %key,
                    symbol = %po.symbol,
                    elapsed_ms = elapsed,
                    cancel_requested_ts_ms = po.cancel_requested_ts_ms.unwrap_or_default(),
                    grace_ms = grace_ms,
                    "PostOnly maker cancel ack grace expired — awaiting confirmation / PostOnly 取消回報 grace 到期，保留追蹤"
                );
                maker_grace_fallback.push(key.clone());
                awaiting_confirmation.push(key.clone());
            }
            PendingSweepAction::ConfirmationTimeout => {
                tracing::error!(
                    order_link_id = %key,
                    symbol = %po.symbol,
                    elapsed_ms = elapsed,
                    "pending order confirmation timeout (>60s) / 待處理訂單確認逾時，保留追蹤"
                );
                awaiting_confirmation.push(key.clone());
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
            PendingSweepAction::Keep => {
                // MAKER-CLOSE-REPRICE-1：仍 Keep 的 PostOnly close maker 嘗試
                // toward-touch 重掛。compute_close_reprice_limit 讀快取 BBO 經
                // compute_close_limit_price 算新 inside quote（spread guard /
                // crossed-book strict skip 全套）；純函數 close_maker_reprice_decision
                // 判定「未達 max_reprices、在 [reprice_after, timeout) 窗、cancel
                // 未在途、新限價嚴格優於原掛價」才放行。stops/urgent 走 market
                // （tif=None）結構上到不了此分支（A.4 互斥證明）。
                if allow_reprice
                    && po.is_close
                    && po.progress.status == super::order_lifecycle::OrderStatus::Working
                    && po.time_in_force == Some(TimeInForce::PostOnly)
                    && po.cancel_requested_ts_ms.is_none()
                    && po.reprice_count < crate::strategies::common::CLOSE_MAKER_MAX_REPRICES
                {
                    // DIRECTION FIX（2026-06-17 E2/E4 RETURN HIGH）：po.is_long 是
                    // **訂單方向**（close order 已 inverted：平多倉=SELL→is_long=false、
                    // 平空倉=BUY→is_long=true），但 reprice 計價要的是**真實持倉方向**。
                    // 經 *_for_pending 單一收口做 `!po.is_long` 轉換（sweep 與 e2e
                    // 方向測試共用同一條，使「把方向寫反」的 mutation 必被測試抓到）。
                    let new_inside_limit = pipeline.compute_close_reprice_limit_for_pending(po);
                    if let Some(new_limit) = pending_sweep::close_maker_reprice_decision(
                        po,
                        now_ms,
                        new_inside_limit,
                        crate::strategies::common::CLOSE_MAKER_MAX_REPRICES,
                        crate::strategies::common::CLOSE_MAKER_REPRICE_AFTER_MS,
                    ) {
                        maker_to_reprice.push((key.clone(), new_limit, po.reprice_count));
                    }
                }
            }
        }
    }
    // 沿用有界 reduce-only 重掛；取消仍為異步請求，不能宣稱已完成。
    // 新單派發後保留舊 tracker，等待其 cancel／execution 確認。
    for (link_id, new_limit, reprice_count) in &maker_to_reprice {
        let Some(po) = state.pending_orders.get(link_id).cloned() else {
            continue;
        };
        if po.close_maker_audit.is_none() {
            continue;
        }
        // 先 cancel 舊掛單（非阻塞 REST，fail-soft）。
        if cancel_maker(&po, now_ms) {
            mark_maker_cancel_attempt(state, link_id, now_ms);
        }
        // DIRECTION FIX（2026-06-17 E2/E4 RETURN HIGH）：經 *_for_pending 單一收口
        // 做 po.is_long（訂單側）→ 真實持倉方向（`!po.is_long`）轉換，再派發。
        let dispatched = pipeline.dispatch_close_maker_reprice_for_pending(
            &po,
            *new_limit,
            *reprice_count,
            now_ms,
        );
        if let Some(replacement_id) = dispatched {
            // 新單派發不等同舊單取消，舊 tracker 保留。
            awaiting_confirmation.push(link_id.clone());
            if let Some(po) = state.pending_orders.get_mut(link_id) {
                po.cancel_requested_ts_ms = Some(now_ms);
                po.progress.replacement_order_link_id = Some(replacement_id);
            }
        }
    }
    for link_id in &maker_grace_fallback {
        if let Some(po) = state.pending_orders.get(link_id).cloned() {
            let reason = pending_sweep::close_maker_sweep_fallback_reason(&po, now_ms)
                .unwrap_or(CloseMakerFallbackReason::CancelGraceExpired);
            dispatch_close_maker_fallback_from_pending(
                state,
                pipeline,
                &po,
                reason,
                None,
                "maker_cancel_grace_expired",
            );
        }
    }
    // Dispatch non-blocking cancels for timed-out PostOnly makers.
    // 非阻塞派發超時 PostOnly 掛單取消。
    let mut maker_cancel_dispatched: Vec<String> = Vec::new();
    for (link_id, symbol, elapsed, deadline_ms) in &maker_to_cancel {
        tracing::warn!(
            order_link_id = %link_id,
            symbol = %symbol,
            elapsed_ms = elapsed,
            deadline_ms = deadline_ms,
            reason = "maker_timeout_cancel",
            "PostOnly maker timed out — cancelling via orderLinkId / PostOnly 掛單超時 — 以 orderLinkId 取消"
        );
        let po = state
            .pending_orders
            .get(link_id)
            .expect("sweep candidate remains tracked");
        if cancel_maker(po, now_ms) {
            maker_cancel_dispatched.push(link_id.clone());
        } else {
            tracing::error!(
                order_link_id = %link_id,
                symbol = %symbol,
                "PostOnly maker timed out but no REST client is available — retaining tracker / PostOnly 超時但無 REST client，保留追蹤"
            );
            if let Some(po) = state.pending_orders.get(link_id).cloned() {
                let reason = pending_sweep::close_maker_sweep_fallback_reason(&po, now_ms)
                    .unwrap_or(CloseMakerFallbackReason::TimeoutTaker);
                dispatch_close_maker_fallback_from_pending(
                    state,
                    pipeline,
                    &po,
                    reason,
                    None,
                    "maker_timeout_no_rest_client",
                );
            }
            awaiting_confirmation.push(link_id.clone());
        }
    }
    // Mark maker rows we just dispatched cancels for. Keep them in the
    // tracker so racing fills before the WS cancel ack still match context.
    // 標記剛派發 cancel 的 maker 訂單；保留 tracker 讓 ack 前 race 成交仍能匹配。
    for link_id in &maker_cancel_dispatched {
        mark_maker_cancel_attempt(state, link_id, now_ms);
    }
    // Retain legacy Market and maker cancel-grace rows until confirmation.
    // Market／cancel grace 逾時只記未知，仍保留 execution 匹配。
    let order_tx = pipeline.trading_channel();
    for key in &awaiting_confirmation {
        super::loop_pending_registration::handle_pending_registration(
            Some(super::types::PendingOrderEvent::ConfirmationUnknown {
                order_link_id: key.clone(),
                reason: "pending_confirmation_timeout".into(),
                ts_ms: now_ms,
            }),
            pipeline,
            state,
            order_tx.as_ref(),
        );
    }
    schedule_pending_reconciliation(state, now_ms);
    // Clean stale order_id mappings: only keep those with active pending orders
    // 清理過期 order_id 映射：僅保留有活躍待處理訂單的
    let active_links: std::collections::HashSet<&String> = state.pending_orders.keys().collect();
    state
        .order_id_to_link
        .retain(|_, link| active_links.contains(link));
}

/// Read-only confirmation survives WS outages and failed/nonterminal batches.
/// Each order has a 30s cooldown plus the reconciler's in-flight dedup and 3-attempt bound.
pub(super) fn schedule_pending_reconciliation(state: &mut LoopState, now_ms: u64) {
    let Some(reconciler) = &state.dcp_reconciler else {
        return;
    };
    let pending: Vec<_> = state
        .pending_orders
        .values_mut()
        .filter_map(|po| {
            let needs_confirmation = po.progress.reconciliation_retry_after_ms.is_some()
                || if po.progress.replacement_order_link_id.is_some() {
                    po.cancel_requested_ts_ms.is_some_and(|sent| {
                        now_ms.saturating_sub(sent)
                            >= pending_sweep::CLOSE_MAKER_CANCEL_ACK_GRACE_MS
                    })
                } else {
                    po.progress.status == super::order_lifecycle::OrderStatus::Unknown
                        || (po.progress.status.is_terminal()
                            && !po.progress.executions_accounted(po.cum_filled_qty))
                        || (!po.progress.status.is_terminal()
                            && matches!(
                                pending_sweep::classify_pending_sweep(po, now_ms),
                                pending_sweep::PendingSweepAction::ConfirmationTimeout
                                    | pending_sweep::PendingSweepAction::MakerTimeoutCancel
                                    | pending_sweep::PendingSweepAction::MakerCancelGraceExpired
                            ))
                };
            if !needs_confirmation
                || po
                    .progress
                    .reconciliation_retry_after_ms
                    .is_some_and(|next| now_ms < next)
            {
                return None;
            }
            po.progress.reconciliation_retry_after_ms = Some(now_ms.saturating_add(30_000));
            Some(po.clone())
        })
        .collect();
    reconciler.schedule(&pending);
}
