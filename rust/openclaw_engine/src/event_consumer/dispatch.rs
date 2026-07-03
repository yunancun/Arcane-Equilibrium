//! Order dispatch task spawn — extracted from event_consumer/mod.rs (I-22).
//! 訂單派發任務 — 從 event_consumer/mod.rs 提取（I-22）。
//!
//! MODULE_NOTE (EN): Spawns the async task that drains the OrderDispatchRequest channel
//!   from TickPipeline and forwards orders to OrderManager. Handles both shadow (paper_only)
//!   and primary (exchange) modes. Returns the PendingOrder receiver used by the event
//!   consumer to track exchange-mode order confirmations.
//! MODULE_NOTE (中): 啟動從 TickPipeline 排出 OrderDispatchRequest 通道並轉發到 OrderManager
//!   的異步任務。同時處理 shadow（紙盤）和 primary（交易所）模式。返回 event consumer
//!   用於追蹤交易所模式訂單確認的 PendingOrder 接收端。

use super::types::{PendingOrder, PendingOrderEvent};
use crate::bybit_rest_client::{BybitApiError, BybitRestClient};
use crate::instrument_info::InstrumentInfoCache;
use crate::order_manager::TimeInForce;
use crate::strategies::common::canonical_close_maker_reason;
use crate::tick_pipeline::{CloseMakerFillAudit, OrderDispatchRequest, TickPipeline};
use openclaw_core::governance_core::LeaseOutcome;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::mpsc;
use tracing::{error, info, warn};

// EVENT-CONSUMER-SPLIT-2（2026-07-03）：retcode 分類 + 重試機械拆至 sibling
// dispatch_retcode.rs（§九 800 行治理）。pub(super) re-export 保持本檔函數體
// 與 dispatch_tests.rs 的引用路徑逐字不變（鏡像 loop_exchange.rs 先例）。
pub(super) use super::dispatch_retcode::{
    close_dispatch_timeout_error, close_dup_is_idempotent_success,
    dispatch_retry_delays_for_intent, noop_is_exchange_zero_position, noop_is_reduce_only_close,
    run_dispatch_retry, DispatchRetryResult, CLOSE_ATTEMPT_TIMEOUT_MS,
};
// OPEN_NO_RETRY 僅 dispatch_tests.rs（留守測試）引用 → test-only re-export，
// 避免非 test build unused-import 警告（鏡像 loop_handlers.rs 對 unattributed_emit
// 的 #[cfg(test)] pub(super) use 先例）。
#[cfg(test)]
pub(super) use super::dispatch_retcode::OPEN_NO_RETRY;

fn send_decision_lease_release(
    pending_reg_tx: &mpsc::UnboundedSender<PendingOrderEvent>,
    req: &OrderDispatchRequest,
    outcome: LeaseOutcome,
    reason: impl Into<String>,
) {
    if !req.is_primary || req.decision_lease_id.is_none() {
        return;
    }
    if let Err(e) = pending_reg_tx.send(PendingOrderEvent::ReleaseDecisionLease {
        order_link_id: req.order_link_id.clone(),
        decision_lease_id: req.decision_lease_id.clone(),
        outcome,
        reason: reason.into(),
        ts_ms: openclaw_core::now_ms(),
    }) {
        warn!(
            order_link_id = %req.order_link_id,
            outcome = ?outcome,
            error = %e,
            "decision lease release event dropped — ExpiryGuardian may need to sweep \
             / 決策租約釋放事件丟失，可能需由 ExpiryGuardian 清理"
        );
    }
}

fn close_maker_audit_for_dispatch_req(req: &OrderDispatchRequest) -> Option<CloseMakerFillAudit> {
    req.close_maker_audit.clone().or_else(|| {
        if req.is_close
            && req.order_type.eq_ignore_ascii_case("limit")
            && req.time_in_force == Some(TimeInForce::PostOnly)
        {
            Some(CloseMakerFillAudit {
                initial_limit_price: req.limit_price,
                eligible_reason: canonical_close_maker_reason(&req.strategy).to_string(),
                fallback_reason: None,
                rate_limit_scope: None,
            })
        } else {
            None
        }
    })
}

fn send_close_maker_dispatch_failed(
    pending_reg_tx: &mpsc::UnboundedSender<PendingOrderEvent>,
    req: &OrderDispatchRequest,
    terminal_status: &str,
    reason: impl Into<String>,
) {
    if !req.is_primary || !req.is_close {
        return;
    }
    let Some(close_maker_audit) = close_maker_audit_for_dispatch_req(req) else {
        return;
    };
    if let Err(e) = pending_reg_tx.send(PendingOrderEvent::DispatchFailed {
        order_link_id: req.order_link_id.clone(),
        symbol: req.symbol.clone(),
        is_long: req.is_long,
        qty: req.qty,
        strategy: req.strategy.clone(),
        context_id: req.context_id.clone(),
        is_close: req.is_close,
        order_type: req.order_type.clone(),
        time_in_force: req.time_in_force,
        maker_timeout_ms: req.maker_timeout_ms,
        close_maker_audit: Some(close_maker_audit),
        terminal_status: terminal_status.to_string(),
        reason: reason.into(),
        ts_ms: openclaw_core::now_ms(),
    }) {
        warn!(
            order_link_id = %req.order_link_id,
            error = %e,
            "close-maker dispatch failure terminal event dropped \
             / close-maker 派發失敗終態事件丟失"
        );
    }
}

/// P1-110017-POSITION-DRIFT-CLOSE-LOOP：對 reduce-only 平倉收到 110017 時，
/// 向 event consumer 發 ExchangeZeroClose，請求本地倉收斂為 flat。
///
/// BB MANDATORY GUARD（2026-05-29 APPROVE-WITH-MANDATORY-GUARD；報告：
/// docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-29--retcode_110017_convergence_semantics.md）：
/// 110017 在 Bybit V5 **不是零倉專屬碼**，是 ReduceOnlyReject 族，三觸發
/// (a) 無倉 (b) 方向反 (c) **qty > 倉量**。其中 (c) C-1 是災難 case：partial
/// reduce-only close（qty>0 但 > 實際倉）會回 110017 但**倉仍在**——此時收斂
/// 會誤刪真倉。因此收斂前必須滿足全部 AND guard（缺一不收斂）：
///   G-1 is_close==true     —— 僅平倉意圖。
///   G-2 reduce_only==true  —— 本系統 close create_req 必設 reduce_only=Some(true)
///                             （dispatch.rs create_req：is_close ⇒ reduce_only），
///                             此處 is_close 即蘊含 reduce_only；BB 要求顯式對齊，
///                             故 helper noop_is_reduce_only_close 顯式檢查兩者。
///   G-4 qty==0 全平 form   —— **最關鍵**。qty=0 全平 form（reduceOnly+closeOnTrigger，
///                             交易所自行 flatten，不送顯式 qty）下 Bybit 不可能因
///                             「qty>size」回 110017，故 110017 在 qty=0 form 下可靠
///                             等價零倉，C-1 結構性排除。qty>0 partial reduce-only
///                             close 收到 110017（倉可能仍在）→ **絕不收斂**。
///   is_primary             —— paper shadow（fire-and-forget，無交易所倉）不收斂。
///   ret_code==110017       —— 110001 維持原 NoOp 不收斂；110009 非 NoOp。
///
/// G-3 hedge-mode 前提守衛：本收斂僅在 **Bybit one-way mode** 安全（BB §3 已以 4
/// 指紋驗：OrderDispatchRequest 無 positionIdx 欄位 / switch_position_mode 0
/// production caller / demo_state position_idx=None / close side 正確反向）。
/// one-way mode 下 §1 corner case C-2（hedge positionIdx/方向不符回 110017 但倉仍在）
/// **結構性不存在**。⚠️ 若未來啟用 hedge mode（switch_position_mode 被接線），
/// 本收斂路徑 = MANDATORY re-review：C-2 會復活，無 positionIdx-aware 比對會誤刪倉。
///
/// ≥2 連續 110017（BB G-5 recommended，非 mandatory）DEFER：見報告論證——
/// qty==0 form + idempotent 收斂（upsert_position_from_exchange size=0 對已 flat 倉
/// 為 no-op；apply_confirmed_fill 對已移除倉 realized=0 不雙記）已足夠安全，C-3
/// just-opened race 即使單發誤收斂亦會被下一筆交易所 WS PositionUpdate 自癒；新增
/// per-symbol 計數需顯著新可變狀態，複雜度不值。列 follow-up。
fn send_exchange_zero_close(
    pending_reg_tx: &mpsc::UnboundedSender<PendingOrderEvent>,
    req: &OrderDispatchRequest,
    last_error: &BybitApiError,
) {
    // BB MANDATORY GUARD（全 AND，缺一不收斂；防 C-1 誤刪真倉）：
    //   is_primary（非 paper shadow）∧ is_close ∧ reduce_only ∧ qty==0 全平 form
    //   ∧ ret_code==110017。
    let is_qty_zero_full_close = req.qty == 0.0;
    if !req.is_primary
        || !noop_is_reduce_only_close(req)
        || !is_qty_zero_full_close
        || !noop_is_exchange_zero_position(last_error)
    {
        return;
    }
    if let Err(e) = pending_reg_tx.send(PendingOrderEvent::ExchangeZeroClose {
        order_link_id: req.order_link_id.clone(),
        symbol: req.symbol.clone(),
        is_long: req.is_long,
        strategy: req.strategy.clone(),
        ts_ms: openclaw_core::now_ms(),
    }) {
        warn!(
            order_link_id = %req.order_link_id,
            symbol = %req.symbol,
            error = %e,
            "exchange-zero close convergence event dropped — local drift position may persist \
             / 交易所 zero 倉收斂事件丟失，本地漂移倉可能殘留"
        );
    }
}

/// Spawn the order dispatch task and return the pending order receiver (exchange mode).
/// 啟動訂單派發任務並返回待處理訂單接收端（交易所模式）。
pub(super) fn spawn_order_dispatch(
    pipeline: &mut TickPipeline,
    shared_client: Option<&Arc<BybitRestClient>>,
    shared_instruments: Option<&Arc<InstrumentInfoCache>>,
    enable_dispatch: bool,
) -> Option<mpsc::UnboundedReceiver<PendingOrderEvent>> {
    if !enable_dispatch {
        return None;
    }
    let client = match shared_client {
        Some(c) => c,
        None => {
            warn!("order dispatch enabled but no API credentials — skipping");
            return None;
        }
    };
    let icache = match shared_instruments {
        Some(i) => i,
        None => {
            warn!("order dispatch enabled but no instrument cache — skipping");
            return None;
        }
    };

    use crate::order_manager::{
        CreateOrderRequest, OrderCategory, OrderManager, OrderSide, OrderType,
    };
    let (shadow_tx, mut shadow_rx) =
        mpsc::unbounded_channel::<crate::tick_pipeline::OrderDispatchRequest>();
    pipeline.set_shadow_channel(shadow_tx);

    // Arc-wrapped so the retry closure can clone it per attempt without
    // consuming the captured binding (FnMut requires repeatable calls).
    // DISPATCH-RETRY-1 (E2 follow-up 2026-04-19).
    //
    // 以 Arc 包裹：重試 closure 每次嘗試可複製 Arc 而不消耗捕獲綁定
    // （FnMut 要求可重複呼叫）。DISPATCH-RETRY-1（E2 後續 2026-04-19）。
    let order_mgr = Arc::new(OrderManager::new(Arc::clone(client), Arc::clone(icache)));
    // P1-03（cold audit pkg B）：把同一 order_mgr Arc 注入 pipeline 供 CancelAllOrders
    // IPC 命令使用（reuse shared live client，不另建客戶端）。在 move 進 spawn 前 clone。
    pipeline.set_cancel_all_order_mgr(Arc::clone(&order_mgr));
    let icache_for_check = Arc::clone(icache);
    let (pending_reg_tx, pending_reg_rx) = mpsc::unbounded_channel::<PendingOrderEvent>();

    tokio::spawn(async move {
        while let Some(req) = shadow_rx.recv().await {
            let is_qty_zero_full_close = req.is_close && req.qty == 0.0;
            if req.qty < 0.0 || (req.qty == 0.0 && !is_qty_zero_full_close) {
                warn!(symbol = %req.symbol, "order dispatch skipped: qty=0");
                send_close_maker_dispatch_failed(
                    &pending_reg_tx,
                    &req,
                    "Rejected",
                    "dispatch_preflight_qty_zero",
                );
                send_decision_lease_release(
                    &pending_reg_tx,
                    &req,
                    LeaseOutcome::Failed,
                    "dispatch_preflight_qty_zero",
                );
                continue;
            }

            // M-1 (2026-04-11) audit fix: pre-flight notional check for Market orders.
            // Bybit V5 enforces a min notional (typically 5 USDT) but local validate_order
            // skips that branch when req.price is None (Market orders carry no limit price).
            // Use OrderDispatchRequest.price (last tick reference price) as a proxy for notional.
            // Without this, sub-min orders round-trip to Bybit only to fail with retCode=10001.
            // M-1 審計修復：市價單的名義值預檢。Bybit V5 強制最小名義值（通常 5 USDT）但
            // 本地 validate_order 在 req.price=None（市價單無限價）時跳過該檢查。使用
            // OrderDispatchRequest.price（最近 tick 參考價）作為名義值代理。
            // 否則低於最小值的訂單會空跑到 Bybit 才被 retCode=10001 拒絕。
            if !is_qty_zero_full_close {
                if let Some(spec) = icache_for_check.get(&req.symbol) {
                    if spec.min_notional > 0.0 && req.price > 0.0 {
                        let est_notional = req.qty * req.price;
                        if est_notional < spec.min_notional {
                            warn!(
                                symbol = %req.symbol,
                                qty = req.qty,
                                ref_price = req.price,
                                est_notional = est_notional,
                                min_notional = spec.min_notional,
                                "order dispatch skipped: notional below exchange minimum / 訂單跳過：名義值低於交易所最小值"
                            );
                            send_close_maker_dispatch_failed(
                                &pending_reg_tx,
                                &req,
                                "Rejected",
                                format!(
                                    "dispatch_preflight_min_notional: est_notional={est_notional}; min_notional={}",
                                    spec.min_notional
                                ),
                            );
                            send_decision_lease_release(
                                &pending_reg_tx,
                                &req,
                                LeaseOutcome::Failed,
                                "dispatch_preflight_min_notional",
                            );
                            continue;
                        }
                    }
                }
            }
            // EXT-1: Register pending order BEFORE placing (for exchange mode)
            if req.is_primary {
                let now_ms = openclaw_core::now_ms();
                let close_maker_audit = close_maker_audit_for_dispatch_req(&req);
                let _ = pending_reg_tx.send(PendingOrderEvent::Register(PendingOrder {
                    order_link_id: req.order_link_id.clone(),
                    symbol: req.symbol.clone(),
                    is_long: req.is_long,
                    qty: req.qty,
                    strategy: req.strategy.clone(),
                    sent_ts_ms: now_ms,
                    signal_ts_ms: req.paper_fill_ts,
                    cum_filled_qty: 0.0,
                    is_close: req.is_close,
                    // FILL-CONTEXT-LINKAGE-1: mirror OrderDispatchRequest.context_id
                    // so the WS-fill handler can pass it to apply_confirmed_fill.
                    // FILL-CONTEXT-LINKAGE-1：鏡射 OrderDispatchRequest.context_id，
                    // WS 成交處理器再傳給 apply_confirmed_fill。
                    context_id: req.context_id.clone(),
                    // EDGE-P2-3 Phase 1B-3.1: mirror order_type + time_in_force
                    // so the sweep can distinguish Market vs resting PostOnly.
                    // EDGE-P2-3 Phase 1B-3.1：鏡射 order_type + time_in_force，
                    // 便於逾時清理區分 Market 與掛中 PostOnly。
                    order_type: req.order_type.clone(),
                    limit_price: req.limit_price,
                    time_in_force: req.time_in_force,
                    // EDGE-P2-3 Phase 1B-3.2: per-order maker sweep timeout.
                    // EDGE-P2-3 Phase 1B-3.2：每單 maker sweep 逾時。
                    maker_timeout_ms: req.maker_timeout_ms,
                    close_maker_audit,
                    reference_price: req.reference_price,
                    reference_ts_ms: req.reference_ts_ms,
                    reference_source: req.reference_source.clone(),
                    cancel_requested_ts_ms: None,
                    // MAKER-CLOSE-REPRICE-1：鏡射 OrderDispatchRequest.reprice_count
                    // （初始 dispatch=0；toward-touch 重掛產生的單帶累計值），
                    // 使 sweep 對重掛單繼續累計至 CLOSE_MAKER_MAX_REPRICES 硬上限。
                    reprice_count: req.reprice_count,
                    // W-C Caveat 2 修復（2026-05-11）：鏡射 OrderDispatchRequest
                    // 帶來的 4 個 Spine id，loop_exchange.rs 成交確認後讀此
                    // 4 欄位呼叫 emit_fill_completion_lineage 補寫真實
                    // ExecutionReport。req.is_primary=false 的 paper shadow
                    // 路徑全為 None，下游自然 short-circuit。
                    spine_order_plan_id: req.spine_order_plan_id.clone(),
                    spine_decision_id: req.spine_decision_id.clone(),
                    spine_verdict_id: req.spine_verdict_id.clone(),
                    spine_stub_report_id: req.spine_stub_report_id.clone(),
                    // P2-ORDERS-INTENT-ID-WRITER-GAP-1（2026-05-19）：鏡射
                    // OrderDispatchRequest.intent_id 到 PendingOrder，下游
                    // handle_pending_registration 從 PendingOrder.intent_id 讀
                    // 寫入 TradingMsg::Order，再進 trading.orders.intent_id。
                    intent_id: req.intent_id.clone(),
                    decision_lease_id: req.decision_lease_id.clone(),
                }));
            }
            let side = if req.is_long {
                OrderSide::Buy
            } else {
                OrderSide::Sell
            };
            let create_req = CreateOrderRequest {
                category: OrderCategory::Linear,
                symbol: req.symbol.clone(),
                side,
                order_type: if req.order_type.eq_ignore_ascii_case("limit") {
                    OrderType::Limit
                } else {
                    OrderType::Market
                },
                qty: req.qty,
                price: req.limit_price,
                time_in_force: req.time_in_force,
                reduce_only: if req.is_close { Some(true) } else { None },
                close_on_trigger: if is_qty_zero_full_close {
                    Some(true)
                } else {
                    None
                },
                order_link_id: Some(req.order_link_id.clone()),
                trigger_price: None,
                trigger_direction: None,
                // I-08 雙軌止損：forward broker-side SL/TP only on primary opens
                take_profit: if req.is_primary && !req.is_close {
                    req.take_profit
                } else {
                    None
                },
                stop_loss: if req.is_primary && !req.is_close {
                    req.stop_loss
                } else {
                    None
                },
                tp_trigger_by: None,
                sl_trigger_by: None,
            };
            let dispatch_type = if req.is_primary { "primary" } else { "shadow" };
            // DISPATCH-RETRY-1 (2026-04-19) + P1-07 (2026-05-29): retry loop via
            // run_dispatch_retry helper.
            //   - Open (create) intents: NO retry (empty delay slice → single attempt,
            //     fail-closed; P1-07 STRICT FAIL-CLOSED, ambiguous create never re-sent).
            //   - Close intents use CLOSE_RETRY_DELAY_MS (2 retries, 500 ms; Q2 fix
            //     avoids amplifying PnL bleed; documented idempotent reduce-only exception).
            //   - Same `create_req` cloned per attempt (order_link_id unchanged =
            //     Bybit idempotency key; `reduce_only=true` adds secondary safety
            //     on close retries).
            //
            // DISPATCH-RETRY-1（2026-04-19）+ P1-07（2026-05-29）：透過 run_dispatch_retry。
            //   - 開倉（create）意圖：不重試（空 delay slice → 單次嘗試，fail-closed；
            //     P1-07 STRICT FAIL-CLOSED，曖昧 create 絕不重發）。
            //   - 關倉意圖使用 CLOSE_RETRY_DELAY_MS（2 次重試，500ms；Q2 修復以避免
            //     出血倉重試放大 PnL；文檔化的 reduce-only 冪等例外）。
            //   - 每次嘗試複製同一 `create_req`（order_link_id 不變 = Bybit 冪等鍵；
            //     關倉重試 `reduce_only=true` 提供二級保護）。
            // P1-07（cold audit pkg B；operator decision STRICT FAIL-CLOSED）：
            //   - OPEN（create）意圖：單次嘗試（空 delay slice → run_dispatch_retry 在
            //     attempt(0) >= len(0) 時立即回 TransientExhausted，等於 0 重試）。任何
            //     timeout / parse / transport / nonzero retCode 直接 fail-closed，
            //     Decision Lease 以非-Consumed（Failed）釋放，不發第二筆 create。
            //     為什麼：mutating create 回應曖昧（timeout/parse/transport）時絕不可重發
            //     —— order_link_id 冪等是 Bybit 側緩解，不是隱藏重試交易效果的許可
            //     （CLAUDE.md §四）。曖昧 create 由 reconciler / pending tracking 對帳。
            //   - CLOSE（reduce-only）意圖：保留有界冪等重試預算（CLOSE_RETRY_DELAY_MS），
            //     是文檔化的唯一例外（root principle 5 survival > profit）：fail-close 一筆
            //     close 會留下未平的活倉，比重試 reduce-only 更危險。
            let delays: &[u64] = dispatch_retry_delays_for_intent(req.is_close);
            let retry_result =
                run_dispatch_retry(delays, &req.symbol, &req.order_link_id, |_attempt| {
                    let req_for_attempt = create_req.clone();
                    let om = Arc::clone(&order_mgr);
                    let is_close = req.is_close;
                    // `async move` captures the Arc clone + cloned request by
                    // value. Each retry gets a fresh Future; the original
                    // `order_mgr` Arc binding stays alive in the outer closure
                    // for the next iteration.
                    //
                    // `async move` 捕獲 Arc 複製與複製後的請求（by value）。
                    // 每次重試產生新的 Future；原始 `order_mgr` Arc 綁定保留在
                    // 外層 closure 供下次迭代使用。
                    async move {
                        if is_close {
                            match tokio::time::timeout(
                                Duration::from_millis(CLOSE_ATTEMPT_TIMEOUT_MS),
                                om.place_order(req_for_attempt),
                            )
                            .await
                            {
                                Ok(result) => result,
                                Err(_) => {
                                    Err(close_dispatch_timeout_error(CLOSE_ATTEMPT_TIMEOUT_MS))
                                }
                            }
                        } else {
                            om.place_order(req_for_attempt).await
                        }
                    }
                })
                .await;

            // Summary logging per outcome. retCode extraction lives here so the
            // generic helper stays untyped over log field shapes.
            //
            // 依結果類型發摘要日誌。retCode 解析集中於此，保留 helper 在日誌欄位
            // 類型上的通用性。
            match retry_result {
                DispatchRetryResult::Ok { value, attempts } => {
                    info!(
                        symbol = %req.symbol,
                        order_id = %value.order_id,
                        order_link_id = %req.order_link_id,
                        dispatch_type = dispatch_type,
                        close = req.is_close,
                        attempts = attempts,
                        "order dispatched / 訂單已派發"
                    );
                    if req.is_primary && !value.order_id.is_empty() && !req.order_link_id.is_empty()
                    {
                        if let Err(e) =
                            pending_reg_tx.send(PendingOrderEvent::ExchangeOrderIdMapped {
                                order_link_id: req.order_link_id.clone(),
                                exchange_order_id: value.order_id.clone(),
                            })
                        {
                            warn!(
                                order_link_id = %req.order_link_id,
                                exchange_order_id = %value.order_id,
                                error = %e,
                                "exchange order id mapping event dropped; OrderUpdate fallback still applies \
                                 / 交易所 orderId 映射事件丟失；仍可等待 OrderUpdate fallback"
                            );
                        }
                    }
                    send_decision_lease_release(
                        &pending_reg_tx,
                        &req,
                        LeaseOutcome::Consumed,
                        "exchange_dispatch_accepted",
                    );
                }
                DispatchRetryResult::NoOp {
                    last_error,
                    attempts,
                } => {
                    let (ret_code_opt, ret_msg_opt): (Option<i64>, Option<String>) =
                        match &last_error {
                            BybitApiError::Business {
                                ret_code, ret_msg, ..
                            } => (Some(*ret_code), Some(ret_msg.clone())),
                            _ => (None, None),
                        };
                    info!(
                        symbol = %req.symbol,
                        order_link_id = %req.order_link_id,
                        dispatch_type = dispatch_type,
                        close = req.is_close,
                        ret_code = ret_code_opt,
                        ret_msg = ret_msg_opt.as_deref(),
                        attempts = attempts,
                        "order dispatch noop / 訂單派發等效成功"
                    );
                    // P1-110017-POSITION-DRIFT-CLOSE-LOOP：reduce-only **qty=0 全平
                    // form** 收到 110017（交易所端倉位已 zero）時，請求 event consumer
                    // 把本地漂移倉收斂為 flat，斷開「每 tick 重發 close → 110017」迴圈。
                    // BB MANDATORY guard 全在 send_exchange_zero_close 內（is_primary ∧
                    // is_close ∧ reduce_only ∧ qty==0 form ∧ 110017）；qty>0 partial
                    // reduce-only close 收到 110017（C-1，倉可能仍在）絕不收斂；
                    // 110001 維持原不收斂行為；110009 非 NoOp（stop-order
                    // limit exceeded，fail-closed）。
                    send_exchange_zero_close(&pending_reg_tx, &req, &last_error);
                    send_decision_lease_release(
                        &pending_reg_tx,
                        &req,
                        LeaseOutcome::Consumed,
                        "exchange_dispatch_noop_success",
                    );
                }
                DispatchRetryResult::Structural {
                    last_error,
                    attempts,
                } => {
                    // P2-ORDERLINKID-110072（+ 2026-06-07 follow-up）：close 重發撞
                    // 重複 order_link_id（110072 專屬碼，或 10001+retMsg "duplicate"
                    // 泛 InvalidParam）= 冪等成功（首次 close attempt 已達 Bybit、
                    // response 丟失，retry 重發同一 id 撞此碼）。走成功收尾（**不**發
                    // DispatchFailed、**不**收斂本地倉），鏡像 Ok/NoOp 成功路徑。
                    // open path 維持 fail-closed：close_dup_is_idempotent_success 僅
                    // is_close 成立（open 撞重複 id = id 撞歷史，開倉未成功，落 else
                    // 失敗路徑）。BB 2026-06-06 APPROVE-WITH-MANDATORY-GUARD；helper
                    // 同時涵蓋 110072 與 10001+duplicate（見其 docstring）。
                    // last_error 在本分支僅被借用（match &last_error / Display），
                    // helper 取 &req,&last_error 在 extract 之前，無 move 衝突。
                    if close_dup_is_idempotent_success(&req, &last_error) {
                        let (ret_code_opt, ret_msg_opt): (Option<i64>, Option<String>) =
                            match &last_error {
                                BybitApiError::Business {
                                    ret_code, ret_msg, ..
                                } => (Some(*ret_code), Some(ret_msg.clone())),
                                _ => (None, None),
                            };
                        info!(
                            symbol = %req.symbol,
                            order_link_id = %req.order_link_id,
                            dispatch_type = dispatch_type,
                            close = req.is_close,
                            ret_code = ret_code_opt,
                            ret_msg = ret_msg_opt.as_deref(),
                            attempts = attempts,
                            "close duplicate order_link_id — idempotent success / 平倉重複 order_link_id 等效成功"
                        );
                        send_decision_lease_release(
                            &pending_reg_tx,
                            &req,
                            LeaseOutcome::Consumed,
                            "exchange_dispatch_close_duplicate_idempotent",
                        );
                    } else {
                        let (ret_code_opt, ret_msg_opt): (Option<i64>, Option<String>) =
                            match &last_error {
                                BybitApiError::Business {
                                    ret_code, ret_msg, ..
                                } => (Some(*ret_code), Some(ret_msg.clone())),
                                _ => (None, None),
                            };
                        error!(
                            symbol = %req.symbol,
                            qty = req.qty,
                            order_link_id = %req.order_link_id,
                            dispatch_type = dispatch_type,
                            close = req.is_close,
                            ret_code = ret_code_opt,
                            ret_msg = ret_msg_opt.as_deref(),
                            error = %last_error,
                            attempts = attempts,
                            "order dispatch failed (structural, no retry) / 訂單派發失敗（結構性，不重試）"
                        );
                        if req.is_primary {
                            let reason =
                                format!("dispatch_structural: attempts={attempts}; error={last_error}");
                            if let Err(e) = pending_reg_tx.send(PendingOrderEvent::DispatchFailed {
                                order_link_id: req.order_link_id.clone(),
                                symbol: req.symbol.clone(),
                                is_long: req.is_long,
                                qty: req.qty,
                                strategy: req.strategy.clone(),
                                context_id: req.context_id.clone(),
                                is_close: req.is_close,
                                order_type: req.order_type.clone(),
                                time_in_force: req.time_in_force,
                                maker_timeout_ms: req.maker_timeout_ms,
                                close_maker_audit: req.close_maker_audit.clone(),
                                terminal_status: "Rejected".to_string(),
                                reason,
                                ts_ms: openclaw_core::now_ms(),
                            }) {
                                warn!(
                                    order_link_id = %req.order_link_id,
                                    error = %e,
                                    "dispatch failure terminal event dropped — pending state may require sweep \
                                     / 派發失敗 terminal event 發送失敗 — pending 狀態可能需 sweep"
                                );
                            }
                            send_decision_lease_release(
                                &pending_reg_tx,
                                &req,
                                LeaseOutcome::Failed,
                                "exchange_dispatch_structural_failed",
                            );
                        }
                    }
                }
                DispatchRetryResult::TransientExhausted {
                    last_error,
                    attempts,
                } => {
                    let (ret_code_opt, ret_msg_opt): (Option<i64>, Option<String>) =
                        match &last_error {
                            BybitApiError::Business {
                                ret_code, ret_msg, ..
                            } => (Some(*ret_code), Some(ret_msg.clone())),
                            _ => (None, None),
                        };
                    error!(
                        symbol = %req.symbol,
                        qty = req.qty,
                        order_link_id = %req.order_link_id,
                        dispatch_type = dispatch_type,
                        close = req.is_close,
                        ret_code = ret_code_opt,
                        ret_msg = ret_msg_opt.as_deref(),
                        error = %last_error,
                        attempts = attempts,
                        "order dispatch failed (transient retry exhausted) / 訂單派發失敗（暫時性重試耗盡）"
                    );
                    if req.is_primary {
                        let reason = format!(
                            "dispatch_transient_exhausted: attempts={attempts}; error={last_error}"
                        );
                        if let Err(e) = pending_reg_tx.send(PendingOrderEvent::DispatchFailed {
                            order_link_id: req.order_link_id.clone(),
                            symbol: req.symbol.clone(),
                            is_long: req.is_long,
                            qty: req.qty,
                            strategy: req.strategy.clone(),
                            context_id: req.context_id.clone(),
                            is_close: req.is_close,
                            order_type: req.order_type.clone(),
                            time_in_force: req.time_in_force,
                            maker_timeout_ms: req.maker_timeout_ms,
                            close_maker_audit: req.close_maker_audit.clone(),
                            terminal_status: "Failed".to_string(),
                            reason,
                            ts_ms: openclaw_core::now_ms(),
                        }) {
                            warn!(
                                order_link_id = %req.order_link_id,
                                error = %e,
                                "dispatch failure terminal event dropped — pending state may require sweep \
                                 / 派發失敗 terminal event 發送失敗 — pending 狀態可能需 sweep"
                            );
                        }
                        send_decision_lease_release(
                            &pending_reg_tx,
                            &req,
                            LeaseOutcome::Failed,
                            "exchange_dispatch_transient_exhausted",
                        );
                    }
                }
            }
        }
    });
    info!("order dispatch mode active / 訂單派發模式已啟用");
    Some(pending_reg_rx)
}

// ---------------------------------------------------------------------------
// Tests / 測試 (DISPATCH-RETRY-1)
// ---------------------------------------------------------------------------

#[cfg(test)]
#[path = "dispatch_tests.rs"]
mod tests;
