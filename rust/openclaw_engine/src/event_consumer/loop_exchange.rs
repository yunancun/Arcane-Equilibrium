//! Exchange-event select! arm handler split from loop_handlers.rs.

use super::execution_fill_helpers::{adverse_slippage_bps, fill_liquidity_role};
use super::funding_settlement::{apply_and_emit_funding_settlement, is_funding_execution};
use super::loop_handlers::{
    dispatch_close_maker_fallback_from_pending, pending_order_accepts_fill, LoopState,
};
use super::pending_sweep;
use super::types::ExchangeEvent;
use super::unattributed_emit::try_emit_unattributed_fill;
use crate::persistence::DualStateWriter;
use crate::strategies::maker_rejection::{
    close_rejection_fallback_decision, CloseMakerFallbackReason, CloseMakerRateLimitScope,
    MakerRejectionCategory,
};
use crate::tick_pipeline::TickPipeline;

fn close_maker_terminal_fallback_reason(
    status: &str,
    reject_category: &MakerRejectionCategory,
    cancel_requested: bool,
) -> (CloseMakerFallbackReason, Option<CloseMakerRateLimitScope>) {
    if cancel_requested && status == "Cancelled" {
        return (CloseMakerFallbackReason::TimeoutTaker, None);
    }
    match reject_category {
        MakerRejectionCategory::PostOnlyCross | MakerRejectionCategory::TooManyPending => {
            let decision = close_rejection_fallback_decision(reject_category);
            (decision.reason, decision.rate_limit_scope)
        }
        MakerRejectionCategory::SelfCancel
        | MakerRejectionCategory::FokCancel
        | MakerRejectionCategory::Other(_) => (CloseMakerFallbackReason::AckLost, None),
    }
}

fn emit_terminal_order_state_change(
    order_tx: Option<&tokio::sync::mpsc::Sender<crate::database::TradingMsg>>,
    pipeline: &TickPipeline,
    po: &super::types::PendingOrder,
    to_status: &str,
    reason: String,
    label: &'static str,
) {
    if let Some(tx) = order_tx {
        let em = pipeline.effective_engine_mode().to_string();
        let _ = crate::database::try_send_trading_msg(
            tx,
            crate::database::TradingMsg::OrderStateChange {
                order_id: po.order_link_id.clone(),
                ts_ms: openclaw_core::now_ms(),
                from_status: Some("Working".into()),
                to_status: to_status.to_string(),
                filled_qty: None,
                avg_price: None,
                reason: Some(reason),
                engine_mode: em,
            },
            label,
        );
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
///   - `DcpTriggered`: exchange auto-cancelled all orders → terminalize rows,
///     clear trackers, and dispatch reduce-only market fallback for close-maker
///     orders when a local position still exists.
///   - `Disconnected`: private WS down → warn with pending-order count.
///
/// Note: original `continue` semantics (line 124 pre-refactor) become early
/// `return` from this fn; next select! iteration naturally enters the next
/// arm — behaviourally equivalent.
/// Arm C handler：分派單個 `ExchangeEvent`。原版 `continue` 語意改為 fn
/// 內 early `return`，下個 select! 迭代自然進下一 arm，行為等價。
// F4-RETURN Issue 2 (2026-04-26): async because F4-1 emitter uses send().await
// for back-pressure. mod.rs Arm C is already async — propagation is just `.await`.
// F4-RETURN Issue 2（2026-04-26）：async — F4-1 emitter 改 send().await 取背壓。
pub(super) async fn handle_exchange_event(
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

            if is_funding_execution(&exec) {
                let emitted = apply_and_emit_funding_settlement(pipeline, &exec, order_tx).await;
                snapshot_writer.force_write(&pipeline.snapshot());
                tracing::info!(
                    exec_id = %exec.exec_id,
                    symbol = %exec.symbol,
                    engine_mode = %pipeline.effective_engine_mode(),
                    ledger_emitted = emitted,
                    "funding settlement applied / 資金費結算已套用"
                );
                return;
            }

            // P0-1 fix: Match fill via order_id → order_link_id mapping.
            // OrderUpdate populates the mapping, Fill uses it.
            // FIX-FEE-POSTONLY-1 (G7-09): hoisted above fee compute so the
            // matched PendingOrder's TimeInForce can drive maker/taker fee
            // selection. Race: Fill may arrive before OrderUpdate has filled
            // `order_id_to_link`; symbol+side fallback still resolves most
            // cases, and unresolved (TIF=None) degrades to taker (safe).
            // FIX-FEE-POSTONLY-1：hoist matched_key 至 fee 計算前，以便
            // 依 PendingOrder.time_in_force 分流 maker/taker 費率。
            let matched_key = state
                .order_id_to_link
                .get(&exec.order_id)
                .cloned()
                .or_else(|| {
                    // Fallback: symbol+side match only when exactly one pending
                    // order is eligible. Picking the first same-side order can
                    // attach fills to the wrong strategy/context when a fill
                    // beats the order update that populates order_id_to_link.
                    let is_buy = exec.side == "Buy";
                    let mut candidates = state
                        .pending_orders
                        .iter()
                        .filter(|(_, po)| {
                            po.symbol == exec.symbol
                                && po.is_long == is_buy
                                && pending_order_accepts_fill(po)
                        });
                    let first = candidates.next().map(|(k, _)| k.clone());
                    if first.is_some() && candidates.next().is_none() {
                        first
                    } else {
                        if first.is_some() {
                            tracing::warn!(
                                exec_id = %exec.exec_id,
                                order_id = %exec.order_id,
                                symbol = %exec.symbol,
                                side = %exec.side,
                                "ambiguous fill-before-order-update fallback — emitting unattributed fill \
                                 / fill 早於 order update 且候選不唯一 — 改落 unattributed fill"
                            );
                        }
                        None
                    }
                });

            // FIX-FEE-POSTONLY-1 (G7-09): look up the matched PendingOrder's
            // TIF so the fee fallback picks maker rate for PostOnly entries.
            // `None` if (a) matched_key unresolved (race) or (b) PendingOrder
            // had TIF=None — both fall through to taker in fee_rate_for_tif.
            let matched_tif = matched_key
                .as_ref()
                .and_then(|k| state.pending_orders.get(k))
                .and_then(|po| po.time_in_force);
            let fallback_fee_rate = pipeline
                .intent_processor
                .fee_rate_for_tif(&exec.symbol, matched_tif);
            let fee_rate_used = exec
                .fee_rate
                .parse::<f64>()
                .ok()
                .filter(|v| v.is_finite() && *v >= 0.0)
                .unwrap_or(fallback_fee_rate);

            // FIX-19: execution.fast topic omits execFee/feeRate fields.
            // When the field is empty or unparseable, estimate fee from
            // notional × per-symbol fee rate so PnL accounting stays correct.
            // FIX-19b: Use pipeline.intent_processor.fee_rate(symbol) for
            // per-symbol resolution (AccountManager → legacy → constant).
            // FIX-FEE-POSTONLY-1 (G7-09): switched to fee_rate_for_tif so
            // PostOnly pending orders get maker rate (~2.75× cheaper) instead
            // of always-taker. Historical pre-fix fills are locked at taker;
            // future baseline analysis must split pre/post window on commit ts.
            // FIX-19：execution.fast 不帶 execFee，空值時用名義值×手續費率估算。
            // FIX-FEE-POSTONLY-1：改經 TIF-aware helper，PostOnly 走 maker。
            let exec_fee: f64 = {
                let parsed = exec.exec_fee.parse::<f64>().unwrap_or(0.0);
                if parsed == 0.0 && exec_qty > 0.0 && exec_price > 0.0 {
                    let estimated = exec_qty * exec_price * fee_rate_used;
                    if estimated > 0.0 {
                        tracing::debug!(
                            exec_id = %exec.exec_id,
                            symbol = %exec.symbol,
                            notional = exec_qty * exec_price,
                            fee_rate = fee_rate_used,
                            tif_known = matched_tif.is_some(),
                            estimated_fee = estimated,
                            "FIX-19b: execFee missing, estimated from TIF-aware rate \
                             / execFee 缺失，使用 TIF-aware 費率估算"
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

            if let Some(key) = matched_key {
                if let Some(po) = state.pending_orders.get_mut(&key) {
                    po.cum_filled_qty += exec_qty;
                    let liquidity_role = fill_liquidity_role(exec.is_maker, matched_tif);
                    let slippage_bps = if liquidity_role == "taker" {
                        adverse_slippage_bps(po.is_long, exec_price, po.reference_price)
                    } else {
                        None
                    };
                    let fill_latency_ms = if exec_ts > 0 {
                        Some(exec_ts.saturating_sub(po.sent_ts_ms))
                    } else {
                        None
                    };
                    let reference_source = po.reference_source.clone();
                    // FILL-CONTEXT-LINKAGE-1: thread signal-time context_id
                    // from PendingOrder into apply_confirmed_fill so
                    // trading.fills.entry_context_id matches
                    // learning.decision_features.context_id.
                    // FILL-CONTEXT-LINKAGE-1：將 PendingOrder 帶的
                    // 訊號時刻 context_id 傳入 apply_confirmed_fill，
                    // 使 trading.fills.entry_context_id 與
                    // learning.decision_features.context_id 對齊。
                    pipeline.apply_confirmed_fill_with_close_maker_audit(
                        &exec.symbol,
                        po.is_long,
                        exec_qty,
                        exec_price,
                        exec_fee,
                        exec_ts,
                        &po.strategy,
                        &po.context_id,
                        &po.order_link_id,
                        Some(fee_rate_used),
                        po.reference_price,
                        po.reference_ts_ms,
                        reference_source.as_deref(),
                        slippage_bps,
                        Some(liquidity_role),
                        fill_latency_ms,
                        Some(&exec.exec_id),
                        po.close_maker_audit.clone(),
                    );
                    snapshot_writer.force_write(&pipeline.snapshot());

                    let fully_filled = po.cum_filled_qty >= po.qty * 0.999;
                    // Emit order state change: Working → Filled / PartiallyFilled.
                    // 發出訂單狀態轉換：Working → Filled / PartiallyFilled。
                    if let Some(tx) = order_tx {
                        let em = pipeline.effective_engine_mode().to_string();
                        let to_status = if fully_filled {
                            "Filled"
                        } else {
                            "PartiallyFilled"
                        };
                        let _ = crate::database::try_send_trading_msg(
                            tx,
                            crate::database::TradingMsg::OrderStateChange {
                                order_id: po.order_link_id.clone(),
                                ts_ms: exec_ts,
                                from_status: Some("Working".into()),
                                to_status: to_status.into(),
                                filled_qty: Some(po.cum_filled_qty),
                                avg_price: Some(exec_price),
                                reason: None,
                                engine_mode: em,
                            },
                            "order_state_fill",
                        );
                    }

                    if fully_filled {
                        // ─────────────────────────────────────────────────────
                        // W-C Caveat 2 修復（2026-05-11）：成交完成後補寫真實
                        // ExecutionReport row 至 Agent Spine。PendingOrder 在
                        // emit_entry_lineage 階段已注入 4 個 spine id
                        // （見 tick_pipeline/on_tick/step_4_5_dispatch.rs），
                        // 此處讀 spine_order_plan_id / spine_decision_id /
                        // spine_stub_report_id 呼叫 emit_fill_completion_lineage。
                        //
                        // 三個必要欄位皆 Some 時才 emit；任一 None 即 short-circuit
                        // （paper shadow path / engine_mode!=demo/live_demo / 舊
                        // path 漏注入皆然），fail-soft 設計與 emit_entry_lineage
                        // 對齊（spine 寫入永不阻塞 hot path）。
                        //
                        // partial fill 不 emit（PA §1.3 / §2.3 by-design），
                        // 此區塊已被外層 `fully_filled` 守門。
                        // ─────────────────────────────────────────────────────
                        if let (Some(plan_id), Some(decision_id), Some(stub_id)) = (
                            po.spine_order_plan_id.as_deref(),
                            po.spine_decision_id.as_deref(),
                            po.spine_stub_report_id.as_deref(),
                        ) {
                            let em_str = pipeline.effective_engine_mode().to_string();
                            crate::agent_spine::runtime_shadow::emit_fill_completion_lineage(
                                pipeline.agent_spine_tx_ref(),
                                pipeline.agent_spine_mode_ref(),
                                crate::agent_spine::runtime_shadow::FillCompletionLineageInput {
                                    order_plan_id: plan_id,
                                    decision_id,
                                    symbol: &exec.symbol,
                                    engine_mode: em_str.as_str(),
                                    strategy: &po.strategy,
                                    ts_ms: exec_ts,
                                    filled_qty: po.cum_filled_qty,
                                    avg_fill_price: exec_price,
                                    fees_paid: exec_fee,
                                    fee_bps: Some(fee_rate_used * 10_000.0),
                                    slippage_bps,
                                    liquidity_role,
                                    fill_latency_ms,
                                    exchange_exec_id: &exec.exec_id,
                                    stub_report_id: stub_id,
                                    order_link_id: Some(po.order_link_id.as_str()),
                                },
                            );
                        }
                        tracing::info!(order_link_id = %key, "pending order fully filled, removing / 待處理訂單完全成交，移除");
                        state.pending_orders.remove(&key);
                    } else if pending_sweep::tighten_postonly_entry_after_partial(po, exec_ts) {
                        tracing::info!(
                            order_link_id = %key,
                            filled_qty = po.cum_filled_qty,
                            total_qty = po.qty,
                            maker_timeout_ms = po.maker_timeout_ms.unwrap_or_default(),
                            "PostOnly entry partially filled — shortened remaining maker timeout / PostOnly entry 部分成交，縮短剩餘掛單等待"
                        );
                    }
                }
            } else {
                // F4-1 (2026-04-26): unmatched WS fill → audit row instead of
                // silent drop. Bybit auto-actions (funding / dust / 补单) land
                // here because ExecutorAgent shadow_mode=true emits 0
                // PendingOrder. Full design context + healthcheck [23] caveat
                // see `unattributed_emit::MODULE_NOTE`. ML training filters via
                // `WHERE strategy_name NOT LIKE 'unattributed:%'` (F4-2).
                // F4-1（2026-04-26）：未匹配 WS 成交 → audit row 取代 silent drop。
                // Bybit 自主動作（funding/dust/补单）因 ExecutorAgent shadow_mode
                // 不發 PendingOrder 而落此。完整設計 + healthcheck [23] caveat 見
                // `unattributed_emit::MODULE_NOTE`；ML 訓練以
                // `strategy_name NOT LIKE 'unattributed:%'` 過濾（F4-2）。
                let em = pipeline.effective_engine_mode();
                // F4-RETURN Issue 2 (2026-04-26): .await — back-pressure handled
                // normally; cap 4096 (tasks.rs:404), blocks only under DB lag.
                let emitted = try_emit_unattributed_fill(
                    em,
                    &exec.exec_id,
                    exec_ts,
                    &exec.order_id,
                    &exec.symbol,
                    &exec.side,
                    exec_qty,
                    exec_price,
                    exec_fee,
                    order_tx,
                )
                .await;
                tracing::warn!(
                    symbol = %exec.symbol, side = %exec.side, exec_id = %exec.exec_id,
                    engine_mode = %em, audit_emitted = emitted,
                    "F4-1: exchange fill has no matching pending order \
                     — audit row {} / 交易所成交無匹配 pending order — \
                     audit row {}",
                    if emitted { "emitted" } else { "skipped (paper/test)" },
                    if emitted { "已落" } else { "已跳過（paper/test）" }
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
                        let reject_category =
                            crate::strategies::maker_rejection::classify(&order.reject_reason);
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
                        let terminal_po = state.pending_orders.get(&order.order_link_id).cloned();
                        if let Some(po) = terminal_po.as_ref() {
                            if po.is_close {
                                pipeline.clear_pending_close(&po.symbol);
                                tracing::warn!(
                                    order_link_id = %order.order_link_id,
                                    symbol = %po.symbol,
                                    "close order {} — clearing pending_close / 平倉訂單{} — 清除待處理平倉",
                                    status, status,
                                );
                                let (fallback_reason, rate_limit_scope) =
                                    close_maker_terminal_fallback_reason(
                                        status,
                                        &reject_category,
                                        po.cancel_requested_ts_ms.is_some(),
                                    );
                                dispatch_close_maker_fallback_from_pending(
                                    state,
                                    pipeline,
                                    po,
                                    fallback_reason,
                                    rate_limit_scope,
                                    "order_update_terminal",
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
                                let _ = crate::database::try_send_trading_msg(
                                    tx,
                                    crate::database::TradingMsg::OrderStateChange {
                                        order_id: po.order_link_id.clone(),
                                        ts_ms: openclaw_core::now_ms(),
                                        from_status: Some("Working".into()),
                                        to_status: status.to_string(),
                                        filled_qty: None,
                                        avg_price: None,
                                        reason: Some(reason_str),
                                        engine_mode: em,
                                    },
                                    "order_state_terminal",
                                );
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
            // DCP is a global exchange-side cancel. Close-maker orders reduce
            // exposure, so survival-first handling tries one reduce-only market
            // fallback when a local open position still exists; every original
            // order also gets an explicit terminal state before trackers clear.
            let pending: Vec<_> = state.pending_orders.values().cloned().collect();
            let count = pending.len();
            pipeline.clear_all_pending_close();
            for po in &pending {
                let mut reason = "dcp_triggered".to_string();
                if po.is_close
                    && po.time_in_force == Some(crate::order_manager::TimeInForce::PostOnly)
                {
                    let fallback_dispatched = dispatch_close_maker_fallback_from_pending(
                        state,
                        pipeline,
                        po,
                        CloseMakerFallbackReason::FallbackToTakerMandatory,
                        None,
                        "dcp_triggered",
                    );
                    reason = if fallback_dispatched {
                        "dcp_triggered|close_maker_fallback=fallback_to_taker_mandatory".to_string()
                    } else {
                        "dcp_triggered|close_maker_fallback=not_dispatched".to_string()
                    };
                }
                emit_terminal_order_state_change(
                    order_tx,
                    pipeline,
                    po,
                    "Cancelled",
                    reason,
                    "order_state_dcp_cancelled",
                );
            }
            if count > 0 {
                tracing::warn!(
                    count = count,
                    "DCP triggered — terminalized and cleared {} pending orders / DCP 觸發，終態化並清除 {} 個待處理訂單",
                    count,
                    count,
                );
                state.pending_orders.clear();
            }
            tracing::warn!(
                "DCP triggered — exchange cancelled active orders, close-maker fallbacks attempted where safe"
            );
        }
        Some(ExchangeEvent::Disconnected) => {
            // Private WS disconnected — pending orders may be in unknown state
            if !state.pending_orders.is_empty() {
                tracing::warn!(
                    pending = state.pending_orders.len(),
                    "private WS disconnected with {} pending orders — reconcile on reconnect \
                    / 私有 WS 斷連，{} 個待處理訂單 — 重連後對賬",
                    state.pending_orders.len(),
                    state.pending_orders.len(),
                );
            }
        }
        None => {} // channel closed
    }
}
