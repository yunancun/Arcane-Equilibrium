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

use super::types::PendingOrder;
use crate::bybit_rest_client::BybitRestClient;
use crate::instrument_info::InstrumentInfoCache;
use crate::tick_pipeline::TickPipeline;
use std::sync::Arc;
use tokio::sync::mpsc;
use tracing::{info, warn};

/// Spawn the order dispatch task and return the pending order receiver (exchange mode).
/// 啟動訂單派發任務並返回待處理訂單接收端（交易所模式）。
pub(super) fn spawn_order_dispatch(
    pipeline: &mut TickPipeline,
    shared_client: Option<&Arc<BybitRestClient>>,
    shared_instruments: Option<&Arc<InstrumentInfoCache>>,
    enable_dispatch: bool,
) -> Option<mpsc::UnboundedReceiver<PendingOrder>> {
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

    let order_mgr = OrderManager::new(Arc::clone(client), Arc::clone(icache));
    let icache_for_check = Arc::clone(icache);
    let (pending_reg_tx, pending_reg_rx) = mpsc::unbounded_channel::<PendingOrder>();

    tokio::spawn(async move {
        while let Some(req) = shadow_rx.recv().await {
            if req.qty <= 0.0 {
                warn!(symbol = %req.symbol, "order dispatch skipped: qty=0");
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
                        continue;
                    }
                }
            }
            // EXT-1: Register pending order BEFORE placing (for exchange mode)
            if req.is_primary {
                let now_ms = openclaw_core::now_ms();
                let _ = pending_reg_tx.send(PendingOrder {
                    order_link_id: req.order_link_id.clone(),
                    symbol: req.symbol.clone(),
                    is_long: req.is_long,
                    qty: req.qty,
                    strategy: req.strategy.clone(),
                    sent_ts_ms: now_ms,
                    cum_filled_qty: 0.0,
                    is_close: req.is_close,
                    // FILL-CONTEXT-LINKAGE-1: mirror OrderDispatchRequest.context_id
                    // so the WS-fill handler can pass it to apply_confirmed_fill.
                    // FILL-CONTEXT-LINKAGE-1：鏡射 OrderDispatchRequest.context_id，
                    // WS 成交處理器再傳給 apply_confirmed_fill。
                    context_id: req.context_id.clone(),
                });
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
                order_type: OrderType::Market,
                qty: req.qty,
                price: None,
                time_in_force: None,
                reduce_only: if req.is_close { Some(true) } else { None },
                close_on_trigger: None,
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
            match order_mgr.place_order(create_req).await {
                Ok(resp) => {
                    info!(
                        symbol = %req.symbol,
                        order_id = %resp.order_id,
                        order_link_id = %req.order_link_id,
                        dispatch_type = dispatch_type,
                        close = req.is_close,
                        "order dispatched / 訂單已派發"
                    );
                }
                Err(e) => {
                    warn!(
                        symbol = %req.symbol,
                        order_link_id = %req.order_link_id,
                        dispatch_type = dispatch_type,
                        error = %e,
                        "order dispatch failed / 訂單派發失敗"
                    );
                }
            }
        }
    });
    info!("order dispatch mode active / 訂單派發模式已啟用");
    Some(pending_reg_rx)
}
