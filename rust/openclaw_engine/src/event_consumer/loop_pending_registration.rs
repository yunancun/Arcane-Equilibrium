//! Arm D handler — dispatch task 的 pending order 註冊/終態事件，自
//! loop_handlers.rs 拆出（EVENT-CONSUMER-SPLIT-2，2026-07-03；§九 2000 行治理）。

use super::loop_handlers::{dispatch_close_maker_fallback_from_pending, LoopState};
use super::types::{PendingOrder, PendingOrderEvent};
use crate::order_manager::TimeInForce;
use crate::strategies::maker_rejection::{CloseMakerFallbackReason, CloseMakerRateLimitScope};
use crate::tick_pipeline::TickPipeline;

fn dispatch_failed_close_maker_fallback_decision(
    reason: &str,
) -> (CloseMakerFallbackReason, Option<CloseMakerRateLimitScope>) {
    if reason.contains("rate_limit_pause_global") {
        (
            CloseMakerFallbackReason::RateLimitPauseGlobal,
            Some(CloseMakerRateLimitScope::Global),
        )
    } else if reason.contains("EC_ReachMaxPendingOrders") || reason.contains("too_many_pending") {
        (
            CloseMakerFallbackReason::RateLimitBackoffPerSymbol,
            Some(CloseMakerRateLimitScope::PerSymbol),
        )
    } else {
        (CloseMakerFallbackReason::FallbackToTakerMandatory, None)
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
    reg: Option<PendingOrderEvent>,
    pipeline: &mut TickPipeline,
    state: &mut LoopState,
    order_tx: Option<&tokio::sync::mpsc::Sender<crate::database::TradingMsg>>,
) {
    if let Some(PendingOrderEvent::Register(po)) = reg {
        tracing::info!(
            order_link_id = %po.order_link_id, symbol = %po.symbol,
            qty = %po.qty, strategy = %po.strategy,
            "pending order registered / 待處理訂單已註冊"
        );
        // Emit Order row when exchange confirms Working state.
        // 訂單進入 Working 狀態時寫入 trading.orders。
        //
        // FIX-G7-09B-INTENT-LIMIT-DROP-1 (2026-04-25):
        //   `PendingOrder.order_type` carries the lowercase `"market"` /
        //   `"limit"` mirrored end-to-end from `OrderIntent.order_type` →
        //   `OrderDispatchRequest.order_type` (per dispatch.rs:420). Prior
        //   code hardcoded `"Market".into()` which (a) corrupted observability
        //   (every audit row read "Market" even when the actual Bybit submit
        //   was Limit + PostOnly) and (b) blocked downstream EDGE-P2-3 maker
        //   fee analysis (`trading.orders` join can't tell Limit from Market).
        //   Fix: map `po.order_type` to PascalCase to match Bybit's
        //   `orderType` field and existing column convention; unknown values
        //   fall back to the raw lowercased string (defensive, never silently
        //   overrides — caller bug surfaces in PG instead of hiding behind a
        //   "Market" mask).
        // FIX-G7-09B-INTENT-LIMIT-DROP-1（2026-04-25）：
        //   `PendingOrder.order_type` 為小寫 `"market"` / `"limit"`，由
        //   `OrderIntent.order_type` → `OrderDispatchRequest.order_type` 端到端鏡射
        //   （見 dispatch.rs:420）。先前硬寫 `"Market".into()`：
        //   (a) 敗壞可觀察性：實際 Bybit 已送出 Limit+PostOnly，audit row 卻全為 "Market"；
        //   (b) 阻斷 EDGE-P2-3 maker 費分析：trading.orders join 無法區分 Limit/Market。
        //   修法：將 `po.order_type` 映成 PascalCase 對齊 Bybit `orderType` 與既有欄位習慣；
        //   非已知值 fallback raw（防禦性，不再以 "Market" 遮蓋 caller bug）。
        let order_type_pg = match po.order_type.to_ascii_lowercase().as_str() {
            "market" => "Market".to_string(),
            "limit" => "Limit".to_string(),
            other => other.to_string(),
        };
        let time_in_force_pg = po.time_in_force.map(|tif| tif.as_str().to_string());
        let order_context_id = if po.context_id.is_empty() {
            None
        } else {
            Some(po.context_id.clone())
        };
        let em = pipeline.effective_engine_mode().to_string();
        let order_side = if po.is_long { "Buy" } else { "Sell" };
        let active_bounded_probe_proof_key = if !po.is_close {
            crate::bounded_probe_active_order::candidate_matched_active_bounded_probe_proof_key(
                &em,
                po.signal_ts_ms,
                &po.strategy,
                &po.symbol,
                order_side,
                order_context_id.as_deref(),
                po.intent_id.as_deref(),
                &po.order_link_id,
                po.decision_lease_id.as_deref(),
                po.reference_source.as_deref(),
            )
        } else {
            None
        }
        .map(|key| {
            serde_json::json!({
                "side_cell_key": key.side_cell_key,
                "engine_mode": key.engine_mode,
                "signal_ts_ms": key.signal_ts_ms,
                "context_id": key.context_id,
                "signal_id": key.signal_id,
                "order_link_id": key.order_link_id,
                "decision_lease_id": key.decision_lease_id,
                "reference_source": key.reference_source,
            })
        });
        let details = serde_json::json!({
            "limit_price": po.limit_price,
            "maker_timeout_ms": po.maker_timeout_ms,
            "reference_price": po.reference_price,
            "reference_ts_ms": po.reference_ts_ms,
            "reference_source": po.reference_source,
            "signal_ts_ms": po.signal_ts_ms,
            "decision_lease_id": po.decision_lease_id,
            "active_bounded_probe_proof_key": active_bounded_probe_proof_key,
            "is_close": po.is_close,
        });
        if let Some(tx) = order_tx {
            let _ = crate::database::try_send_trading_msg(
                tx,
                crate::database::TradingMsg::Order {
                    order_id: po.order_link_id.clone(),
                    ts_ms: po.sent_ts_ms,
                    symbol: po.symbol.clone(),
                    side: if po.is_long {
                        "Buy".into()
                    } else {
                        "Sell".into()
                    },
                    order_type: order_type_pg,
                    time_in_force: time_in_force_pg,
                    qty: po.qty,
                    price: po.limit_price,
                    context_id: order_context_id,
                    strategy_name: po.strategy.clone(),
                    is_close: po.is_close,
                    engine_mode: em.clone(),
                    details: Some(details),
                    // P2-ORDERS-INTENT-ID-WRITER-GAP-1（2026-05-19）：寫入
                    // trading.orders.intent_id，恢復 intents → orders JOIN。
                    // entry path 為 Some（step_4_5_dispatch 注入）；close /
                    // ipc / orphan 路徑為 None（誠實表述無 strategy intent）。
                    intent_id: po.intent_id.clone(),
                },
                "order_registered",
            );
            let _ = crate::database::try_send_trading_msg(
                tx,
                crate::database::TradingMsg::OrderStateChange {
                    order_id: po.order_link_id.clone(),
                    ts_ms: po.sent_ts_ms,
                    from_status: Some("Submitted".into()),
                    to_status: "Working".into(),
                    filled_qty: None,
                    avg_price: None,
                    reason: None,
                    engine_mode: em,
                },
                "order_state_working",
            );
        }
        state.pending_orders.insert(po.order_link_id.clone(), po);
    } else if let Some(PendingOrderEvent::ExchangeOrderIdMapped {
        order_link_id,
        exchange_order_id,
    }) = reg
    {
        if order_link_id.is_empty() || exchange_order_id.is_empty() {
            tracing::warn!(
                order_link_id = %order_link_id,
                exchange_order_id = %exchange_order_id,
                "exchange order id mapping ignored because id is empty \
                 / 交易所 orderId 映射因 id 空值被忽略"
            );
            return;
        }
        if state.pending_orders.contains_key(&order_link_id) {
            state
                .order_id_to_link
                .insert(exchange_order_id.clone(), order_link_id.clone());
            tracing::info!(
                order_link_id = %order_link_id,
                exchange_order_id = %exchange_order_id,
                "exchange order id mapping registered from dispatch response \
                 / 已從 dispatch 回應註冊交易所 orderId 映射"
            );
        } else {
            tracing::warn!(
                order_link_id = %order_link_id,
                exchange_order_id = %exchange_order_id,
                "exchange order id mapping ignored because pending order is gone \
                 / pending order 已不存在，忽略交易所 orderId 映射"
            );
        }
    } else if let Some(PendingOrderEvent::ReleaseDecisionLease {
        order_link_id,
        decision_lease_id,
        outcome,
        reason,
        ts_ms,
    }) = reg
    {
        tracing::info!(
            order_link_id = %order_link_id,
            lease_id = decision_lease_id.as_deref().unwrap_or(""),
            outcome = ?outcome,
            reason = %reason,
            ts_ms = ts_ms,
            "decision lease terminal event received / 收到決策租約終態事件"
        );
        pipeline.release_decision_lease(
            decision_lease_id.as_deref(),
            outcome,
            "event_consumer_pending_order",
        );
    } else if let Some(PendingOrderEvent::DispatchFailed {
        order_link_id,
        symbol,
        is_long,
        qty,
        strategy,
        context_id,
        is_close,
        order_type,
        time_in_force,
        maker_timeout_ms,
        close_maker_audit,
        terminal_status,
        reason,
        ts_ms,
    }) = reg
    {
        if is_close {
            pipeline.clear_pending_close(&symbol);
        }
        let removed_po = state.pending_orders.remove(&order_link_id);
        state
            .order_id_to_link
            .retain(|_, link| link.as_str() != order_link_id.as_str());
        let removed = removed_po.is_some();
        let (fallback_reason, rate_limit_scope) =
            dispatch_failed_close_maker_fallback_decision(&reason);
        if let Some(po) = removed_po.as_ref() {
            dispatch_close_maker_fallback_from_pending(
                state,
                pipeline,
                po,
                fallback_reason,
                rate_limit_scope,
                "dispatch_failed",
            );
        } else if is_close
            && time_in_force == Some(TimeInForce::PostOnly)
            && close_maker_audit
                .as_ref()
                .is_some_and(|audit| audit.fallback_reason.is_none())
        {
            let po = PendingOrder {
                order_link_id: order_link_id.clone(),
                symbol: symbol.clone(),
                is_long,
                qty,
                strategy: strategy.clone(),
                sent_ts_ms: ts_ms,
                signal_ts_ms: ts_ms,
                cum_filled_qty: 0.0,
                is_close,
                context_id: context_id.clone(),
                order_type: order_type.clone(),
                limit_price: close_maker_audit
                    .as_ref()
                    .and_then(|audit| audit.initial_limit_price),
                time_in_force,
                maker_timeout_ms,
                close_maker_audit: close_maker_audit.clone(),
                reference_price: None,
                reference_ts_ms: None,
                reference_source: None,
                cancel_requested_ts_ms: None,
                // MAKER-CLOSE-REPRICE-1：dispatch_failed 重建走 market fallback，
                // 不參與 reprice，計數 0。
                reprice_count: 0,
                spine_order_plan_id: None,
                spine_decision_id: None,
                spine_verdict_id: None,
                spine_stub_report_id: None,
                // P2-ORDERS-INTENT-ID-WRITER-GAP-1（2026-05-19）：
                // dispatch_failed close-maker 重建 PendingOrder 為 fallback
                // 路徑，非 strategy intent 對應，保 None。
                intent_id: None,
                decision_lease_id: None,
            };
            dispatch_close_maker_fallback_from_pending(
                state,
                pipeline,
                &po,
                fallback_reason,
                rate_limit_scope,
                "dispatch_failed_unregistered",
            );
        }
        tracing::warn!(
            order_link_id = %order_link_id,
            symbol = %symbol,
            is_close = is_close,
            removed_pending = removed,
            terminal_status = %terminal_status,
            reason = %reason,
            "pending order terminal dispatch failure / 待處理訂單派發失敗並終止"
        );
        if let Some(tx) = order_tx {
            let em = pipeline.effective_engine_mode().to_string();
            let _ = crate::database::try_send_trading_msg(
                tx,
                crate::database::TradingMsg::OrderStateChange {
                    order_id: order_link_id,
                    ts_ms,
                    from_status: Some("Working".into()),
                    to_status: terminal_status,
                    filled_qty: None,
                    avg_price: None,
                    reason: Some(reason),
                    engine_mode: em,
                },
                "order_dispatch_failed",
            );
        }
    } else if let Some(PendingOrderEvent::ExchangeZeroClose {
        order_link_id,
        symbol,
        is_long,
        strategy,
        ts_ms,
    }) = reg
    {
        // P1-110017-POSITION-DRIFT-CLOSE-LOOP：交易所對 reduce-only 平倉回
        // 110017（current position is zero），以交易所 truth 收斂本地漂移倉
        // 為 flat，斷開「每 tick 重發 close → 110017」自持迴圈。
        // 同步移除 pending_orders 追蹤列（若有），避免 sweep 殘留。
        let removed_pending = state.pending_orders.remove(&order_link_id).is_some();
        state
            .order_id_to_link
            .retain(|_, link| link.as_str() != order_link_id.as_str());
        let removed_position = pipeline.converge_exchange_zero_close(&symbol, is_long, ts_ms);
        tracing::warn!(
            order_link_id = %order_link_id,
            symbol = %symbol,
            is_long = is_long,
            strategy = %strategy,
            removed_position = removed_position,
            removed_pending = removed_pending,
            "exchange-zero close convergence applied (Bybit 110017) \
             / 依交易所 110017 收斂本地漂移倉"
        );
        // 寫一筆審計 OrderStateChange：close 因交易所端無倉而終態，標記
        // exchange_zero 以利後續 drift 歸因。to_status=Cancelled（交易所未成交，
        // 但已達終態），reason 帶 110017 收斂上下文。
        if let Some(tx) = order_tx {
            let em = pipeline.effective_engine_mode().to_string();
            let _ = crate::database::try_send_trading_msg(
                tx,
                crate::database::TradingMsg::OrderStateChange {
                    order_id: order_link_id,
                    ts_ms,
                    from_status: Some("Working".into()),
                    to_status: "Cancelled".into(),
                    filled_qty: None,
                    avg_price: None,
                    reason: Some(format!(
                        "exchange_zero_close_converge:110017; removed_position={removed_position}"
                    )),
                    engine_mode: em,
                },
                "exchange_zero_close_converge",
            );
        }
    }
}
