//! Exchange-event select! arm handler split from loop_handlers.rs.

use super::execution_fill_helpers::{fill_liquidity_role, split_markout_by_role};
use super::funding_settlement::{apply_and_emit_funding_settlement, is_funding_execution};
use super::loop_handlers::{
    dispatch_close_maker_fallback_from_pending, pending_order_accepts_fill, LoopState,
};
use super::order_lifecycle::OrderStatus;
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

// ─────────────────────────────────────────────────────────────────────────────
// Arm C: exchange events (fills / order updates / position / DCP / disconnect).
// Arm C：交易所事件（成交 / 訂單狀態 / 持倉 / DCP / 斷連）。
// ─────────────────────────────────────────────────────────────────────────────

/// WS 成交是持倉寫入來源；order topic 推進委託狀態並保留未收齊的 execution。
/// DCP／斷線不能替代單筆終態確認；reduce-only 保護沿既有有界 fallback。
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
            if is_funding_execution(&exec) {
                remember_execution(state, &exec.exec_id);
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

            let valid_positive = |value: &str| {
                value
                    .parse::<f64>()
                    .ok()
                    .filter(|v| v.is_finite() && *v > 0.0)
            };
            let (Some(exec_qty), Some(exec_price), Some(exec_ts)) = (
                valid_positive(&exec.exec_qty),
                valid_positive(&exec.exec_price),
                exec.exec_time.parse::<u64>().ok().filter(|t| *t > 0),
            ) else {
                tracing::error!(exec_id=%exec.exec_id, "Invalid execution values; awaiting valid WS/REST evidence");
                return;
            };
            if exec.exec_id.is_empty()
                || exec.symbol.is_empty()
                || !matches!(exec.side.as_str(), "Buy" | "Sell")
            {
                tracing::error!(exec_id=%exec.exec_id, "Invalid execution identity; retaining pending tracker");
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
            let mut matched_key = if !exec.order_link_id.is_empty() {
                // 明確 orderLinkId 優先，未知 ID 不可落入同 symbol 猜測。
                state
                    .pending_orders
                    .contains_key(&exec.order_link_id)
                    .then(|| exec.order_link_id.clone())
            } else {
                state
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
                })
            };
            if let Some(key) = matched_key.as_ref() {
                if !state.pending_orders.contains_key(key) {
                    state.order_id_to_link.remove(&exec.order_id);
                    tracing::warn!(
                        exec_id = %exec.exec_id,
                        order_id = %exec.order_id,
                        stale_order_link_id = %key,
                        "stale order_id mapping hit — falling back to unattributed audit \
                         / 命中過期 order_id 映射 — 回落 unattributed audit"
                    );
                    matched_key = None;
                }
            }

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
                    if po.progress.applied_execution_ids.contains(&exec.exec_id) {
                        return;
                    }
                    if po.symbol != exec.symbol || po.is_long != (exec.side == "Buy") {
                        tracing::error!(exec_id=%exec.exec_id, "Execution does not match pending order identity");
                        return;
                    }
                    let liquidity_role = fill_liquidity_role(exec.is_maker, matched_tif);
                    // V145：同一純函數 adverse_slippage_bps 按 liquidity_role 互斥
                    // 分流到兩個正交 column —— taker 寫 slippage_bps（穿越 spread 的
                    // 執行劣勢），maker 寫 maker_markout_bps（掛單成交後 mid 朝對我
                    // 不利方向走的 adverse selection）。先前 maker 一律 None（756/756
                    // NULL）就是因為這裡只算 taker。zero 新數學，純記錄面分流。
                    // close-maker 的 po.reference_price 在 commands.rs close emit 已
                    // 改為 mid@submit（reference_source="mid_at_submit"），使 maker
                    // markout 基準正確（非 last price）。
                    let (slippage_bps, maker_markout_bps) = split_markout_by_role(
                        liquidity_role,
                        po.is_long,
                        exec_price,
                        po.reference_price,
                    );
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
                    let preserve_close_guard = po.is_close
                        && (po.progress.replacement_order_link_id.is_some()
                            || state.close_maker_fallback_dispatched.contains(&key))
                        && pipeline.has_pending_close(&po.symbol);
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
                        // V145：maker markout（taker 為 None）按參數順序傳入。
                        maker_markout_bps,
                        Some(liquidity_role),
                        fill_latency_ms,
                        Some(&exec.exec_id),
                        po.close_maker_audit.clone(),
                        // PHANTOM-FILL-FIX-1（PA T2/T3）：透傳這筆成交是否為 reduce-only/平倉。
                        // reduce-only fill 在本地無倉時 no-op（不開幻影倉，§4.3）。
                        po.is_close,
                        Some(po.sent_ts_ms),
                    );
                    // Commit dedup only after validated execution accounting.
                    po.cum_filled_qty += exec_qty;
                    po.progress
                        .applied_execution_ids
                        .insert(exec.exec_id.clone());
                    if preserve_close_guard {
                        pipeline.retain_pending_close(&po.symbol);
                    }
                    snapshot_writer.force_write(&pipeline.snapshot());
                    settle_pending_lease(
                        po,
                        pipeline,
                        openclaw_core::governance_core::LeaseOutcome::Consumed,
                    );

                    let fully_filled = if po.progress.status == OrderStatus::Filled {
                        po.progress.executions_accounted(po.cum_filled_qty)
                    } else {
                        po.qty > 0.0 && po.cum_filled_qty + 1e-10 >= po.qty
                    };
                    let previous_status = po.progress.status;
                    if fully_filled {
                        po.progress.status = OrderStatus::Filled;
                    } else if !po.progress.status.is_terminal() {
                        po.progress.status = OrderStatus::PartiallyFilled;
                    }
                    // Emit order state change: Working → Filled / PartiallyFilled.
                    // 發出訂單狀態轉換：Working → Filled / PartiallyFilled。
                    if let Some(tx) = order_tx {
                        let em = pipeline.effective_engine_mode().to_string();
                        let to_status = po.progress.status.as_str();
                        let _ = crate::database::try_send_trading_msg(
                            tx,
                            crate::database::TradingMsg::OrderStateChange {
                                order_id: po.order_link_id.clone(),
                                ts_ms: exec_ts,
                                from_status: Some(previous_status.as_str().into()),
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
                        state
                            .order_id_to_link
                            .retain(|_, link| link.as_str() != key.as_str());
                        state.pending_orders.remove(&key);
                        pipeline.exchange_submission_guard.resolve(&key);
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
                finish_terminal_pending(&key, state, pipeline);
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
            remember_execution(state, &exec.exec_id);
        }
        Some(ExchangeEvent::OrderUpdate(order)) => {
            let id = &order.order_link_id;
            if let Some(po) = state.pending_orders.get_mut(id) {
                if !order.order_id.is_empty() {
                    state
                        .order_id_to_link
                        .insert(order.order_id.clone(), id.clone());
                }
                let next = match order.order_status.as_str() {
                    "New" | "Untriggered" | "Triggered" if po.cum_filled_qty > 0.0 => {
                        Some(OrderStatus::PartiallyFilled)
                    }
                    "New" | "Untriggered" | "Triggered" => Some(OrderStatus::Working),
                    "PartiallyFilled" => Some(OrderStatus::PartiallyFilled),
                    "Filled" => Some(OrderStatus::Filled),
                    "Cancelled" => Some(OrderStatus::Cancelled),
                    "PartiallyFilledCanceled" => Some(OrderStatus::PartiallyFilledCanceled),
                    "Rejected" => Some(OrderStatus::Rejected),
                    "Deactivated" => Some(OrderStatus::Deactivated),
                    _ => None,
                };
                if let Some(next) = next {
                    let previous = po.progress.status;
                    if (!previous.is_terminal() || previous == next)
                        && !(previous == OrderStatus::PartiallyFilled
                            && next == OrderStatus::Working)
                    {
                        let reported = order.cum_exec_qty.parse::<f64>().ok().filter(|n| {
                            n.is_finite() && *n >= 0.0 && (next != OrderStatus::Filled || *n > 0.0)
                        });
                        po.progress.venue_filled_qty = reported
                            .map(|qty| qty.max(po.progress.venue_filled_qty.unwrap_or(0.0)))
                            .or(po.progress.venue_filled_qty);
                        po.progress.venue_reject_reason = order.reject_reason.clone();
                        po.progress.status = next;
                        if previous != next {
                            let reason = if order.reject_reason.is_empty() {
                                format!("exchange_status:{}", order.order_status)
                            } else {
                                format!(
                                    "exchange_status:{}|reject={}|category={}",
                                    order.order_status,
                                    order.reject_reason,
                                    crate::strategies::maker_rejection::classify(
                                        &order.reject_reason
                                    )
                                    .label()
                                )
                            };
                            if let Some(tx) = order_tx {
                                let _ = crate::database::try_send_trading_msg(
                                    tx,
                                    crate::database::TradingMsg::OrderStateChange {
                                        order_id: id.clone(),
                                        ts_ms: openclaw_core::now_ms(),
                                        from_status: Some(previous.as_str().into()),
                                        to_status: next.as_str().into(),
                                        filled_qty: po.progress.venue_filled_qty,
                                        avg_price: None,
                                        reason: Some(reason),
                                        engine_mode: pipeline.effective_engine_mode().to_string(),
                                    },
                                    "order_state_venue",
                                );
                            }
                        }
                    }
                }
            }
            // Filled／Cancel 回報先到時保留 tracker，直到 execution 數量已入帳。
            finish_terminal_pending(id, state, pipeline);
        }
        Some(ExchangeEvent::PositionUpdate(pos)) => {
            // PHANTOM-FILL-FIX-1（2026-06-07，PA Option A T2）：把 WS PositionUpdate
            // 從「authoritative 寫入 paper_state.positions」降為 **advisory 只讀比對**。
            //
            // 為什麼（根因）：拆分前此分支呼 `upsert_position_from_exchange` 直接
            // add/flip/remove 本地倉，與 execution 流的 `apply_fill` 競爭同一份
            // positions map（兩條 WS 訊息無序）。Bybit 平倉先推 `position(size=0)`
            // → 移除 short → 隨後 close `Buy` fill 落空 → 開出幻影 LONG（TON 事故）。
            //
            // Option A：倉位**唯一 mutating 來源 = `apply_fill`（execution 流）**。
            // PositionUpdate 只做：
            //   - size==0 且本地有倉 → 走既有已測收斂路徑 `converge_exchange_zero_close`
            //     （含 mirror 同步 + 清 pending_close + audit；非裸 positions_remove）。
            //     收斂使 close fill 永遠先於 remove 抵達 → 競態消失。
            //   - size>0 且方向/數量與本地背離 → **大聲 WARN**（advisory，不 mutate）；
            //     真正收斂交給 reconciler / execution 流。
            // 對所有 engine_mode（demo/live_demo/live）一致（private_ws 不分 kind）。
            let size: f64 = pos.size.parse().unwrap_or(0.0);
            let avg_price: f64 = pos.avg_price.parse().unwrap_or(0.0);
            let is_long = pos.side.eq_ignore_ascii_case("Buy");
            let now_ms = openclaw_core::now_ms();
            // Bybit returns side=="None" when the position is flat — coerce
            // size to 0 so the zero path runs.
            // Bybit 在持倉為空時回傳 side=="None"，強制 size 為 0 走 zero 收斂路徑。
            let effective_size = if pos.side.eq_ignore_ascii_case("None") || pos.side.is_empty() {
                0.0
            } else {
                size
            };

            if effective_size <= 0.0 {
                // 交易所端該倉已 flat。若本地仍有倉 → 走已測收斂路徑移除（mirror 同步、
                // 不記假 PnL）。converge_exchange_zero_close 內部對 paper-kind / 無倉皆
                // 二重 noop 守衛，安全。is_long 取本地倉方向避免 side=None 時無方向。
                let local_is_long = pipeline
                    .paper_state
                    .get_position(&pos.symbol)
                    .map(|p| p.is_long)
                    .unwrap_or(is_long);
                let removed =
                    pipeline.converge_exchange_zero_close(&pos.symbol, local_is_long, now_ms);
                if removed {
                    tracing::warn!(
                        symbol = %pos.symbol,
                        side = %pos.side,
                        kind = %pipeline.pipeline_kind,
                        "PHANTOM-FILL-FIX-1: WS position flat — converged drifted local position (advisory) \
                         / WS 倉位已 flat — 收斂本地漂移倉（advisory）"
                    );
                    snapshot_writer.force_write(&pipeline.snapshot());
                }
            } else {
                // size>0：advisory 只讀比對，不 mutate 本地帳。背離大聲 WARN 供觀測；
                // 收斂留給 execution 流（apply_fill）/ reconciler（T5 phantom 偵測軸）。
                match pipeline.paper_state.get_position(&pos.symbol) {
                    Some(local) => {
                        let qty_rel_diff = if local.qty.abs() > f64::EPSILON {
                            (local.qty - effective_size).abs() / local.qty.abs()
                        } else {
                            f64::INFINITY
                        };
                        // 5% 與 reconciler MINOR_DRIFT_THRESHOLD_PCT 同檔，閾下視為
                        // rounding / tick race 噪音不告警。
                        if local.is_long != is_long || qty_rel_diff > 0.05 {
                            tracing::warn!(
                                symbol = %pos.symbol,
                                ws_side = %pos.side,
                                ws_size = effective_size,
                                ws_avg_price = avg_price,
                                local_is_long = local.is_long,
                                local_qty = local.qty,
                                kind = %pipeline.pipeline_kind,
                                "PHANTOM-FILL-FIX-1: WS position diverges from local book (advisory, not mutated) \
                                 / WS 倉位與本地帳背離（advisory，未 mutate）"
                            );
                        }
                    }
                    None => {
                        // 交易所有倉但本地無 —— 可能 fill 漏接 / orphan。advisory WARN；
                        // 收斂交給 reconciler orphan 軸（既有 dispatch_orphan_close）。
                        tracing::warn!(
                            symbol = %pos.symbol,
                            ws_side = %pos.side,
                            ws_size = effective_size,
                            kind = %pipeline.pipeline_kind,
                            "PHANTOM-FILL-FIX-1: WS reports position but local book is flat (advisory; reconciler orphan axis owns convergence) \
                             / WS 報告有倉但本地 flat（advisory；收斂歸 reconciler orphan 軸）"
                        );
                    }
                }
            }
        }
        Some(event @ (ExchangeEvent::DcpTriggered | ExchangeEvent::Disconnected)) => {
            let is_dcp = matches!(event, ExchangeEvent::DcpTriggered);
            let now_ms = openclaw_core::now_ms();
            let pending: Vec<_> = state
                .pending_orders
                .values_mut()
                .map(|po| {
                    // Repeated disconnect/DCP signals cannot bypass the cooldown.
                    po.progress.reconciliation_retry_after_ms.get_or_insert(0);
                    po.clone()
                })
                .collect();
            for po in &pending {
                super::loop_pending_registration::handle_pending_registration(
                    Some(super::types::PendingOrderEvent::ConfirmationUnknown {
                        order_link_id: po.order_link_id.clone(),
                        reason: if is_dcp {
                            "dcp_triggered:await_per_order_confirmation"
                        } else {
                            "ws_disconnected:await_per_order_confirmation"
                        }
                        .into(),
                        ts_ms: now_ms,
                    }),
                    pipeline,
                    state,
                    order_tx,
                );
                if is_dcp {
                    dispatch_close_maker_fallback_from_pending(
                        state,
                        pipeline,
                        po,
                        CloseMakerFallbackReason::FallbackToTakerMandatory,
                        None,
                        "dcp_triggered",
                    );
                }
            }
            super::loop_tick::schedule_pending_reconciliation(state, now_ms);
            if !pending.is_empty() && state.dcp_reconciler.is_none() {
                tracing::error!("Order reconciliation unavailable; retaining unresolved trackers");
            }
        }
        None => {} // channel closed
    }
}

fn remember_execution(state: &mut LoopState, exec_id: &str) {
    state.seen_exec_set.insert(exec_id.to_owned());
    state.seen_exec_order.push_back(exec_id.to_owned());
    if state.seen_exec_order.len() > LoopState::MAX_SEEN_EXEC_IDS {
        if let Some(old) = state.seen_exec_order.pop_front() {
            state.seen_exec_set.remove(&old);
        }
    }
}

/// 終態只結束委託；尚未收齊的 execution 必須仍能匹配原 intent。
fn finish_terminal_pending(id: &str, state: &mut LoopState, pipeline: &mut TickPipeline) {
    let Some(mut po) = state.pending_orders.get(id).cloned() else {
        return;
    };
    if !po.progress.executions_accounted(po.cum_filled_qty) {
        return;
    }
    let outcome = if po.cum_filled_qty > 0.0 {
        openclaw_core::governance_core::LeaseOutcome::Consumed
    } else if po.progress.status == OrderStatus::Rejected {
        openclaw_core::governance_core::LeaseOutcome::Failed
    } else {
        openclaw_core::governance_core::LeaseOutcome::Cancelled
    };
    settle_pending_lease(&mut po, pipeline, outcome);
    if po.is_close
        && po.progress.replacement_order_link_id.is_none()
        && !state.close_maker_fallback_dispatched.contains(id)
    {
        pipeline.clear_pending_close(&po.symbol);
    }
    if po.progress.status != OrderStatus::Filled {
        let category =
            crate::strategies::maker_rejection::classify(&po.progress.venue_reject_reason);
        let (reason, scope) = close_maker_terminal_fallback_reason(
            po.progress.status.as_str(),
            &category,
            po.cancel_requested_ts_ms.is_some(),
        );
        dispatch_close_maker_fallback_from_pending(
            state,
            pipeline,
            &po,
            reason,
            scope,
            "order_terminal",
        );
    }
    state.pending_orders.remove(id);
    state.order_id_to_link.retain(|_, link| link != id);
    pipeline.exchange_submission_guard.resolve(id);
}

fn settle_pending_lease(
    po: &mut super::types::PendingOrder,
    pipeline: &TickPipeline,
    outcome: openclaw_core::governance_core::LeaseOutcome,
) {
    if let Some(id) = po.decision_lease_id.take() {
        // REST ACK may already have settled it; avoid duplicate release events.
        if pipeline.governance.get_lease_by_id(&id).is_ok() {
            pipeline.release_decision_lease(Some(&id), outcome, "venue_confirmation");
        }
    }
}
