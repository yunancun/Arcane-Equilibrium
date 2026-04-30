//! FIX-G7-09B-INTENT-LIMIT-DROP-1 (2026-04-25): regression tests for
//! `handle_pending_registration` audit-row `order_type` derivation. Prior code
//! hardcoded `"Market".into()` — Limit + PostOnly orders that the dispatch
//! layer correctly sent to Bybit (per dispatch.rs:436-443) showed up in
//! `trading.orders.order_type` as "Market", corrupting EDGE-P2-3 maker fee
//! analysis and PostOnly fill-rate KPIs. Fix maps `PendingOrder.order_type`
//! (lowercase mirror of `OrderIntent.order_type`) to PascalCase to match
//! Bybit's `orderType` field and the existing column convention. These tests
//! pin (1) intent.limit + TIF=PostOnly → row "Limit" (2) intent.market →
//! row "Market" (3) edge cases (TIF=None / GTC / unknown raw).
//!
//! FIX-G7-09B-INTENT-LIMIT-DROP-1（2026-04-25）：`handle_pending_registration`
//! audit row 的 `order_type` 推導 regression。先前硬寫 `"Market".into()` →
//! 已正確送達 Bybit 的 Limit + PostOnly 訂單在 `trading.orders.order_type`
//! 全為 "Market"，敗壞 EDGE-P2-3 maker 費分析與 PostOnly 成交率 KPI。
//! 修法：以 `PendingOrder.order_type`（為 `OrderIntent.order_type` 的小寫鏡射）
//! 映成 PascalCase，對齊 Bybit `orderType` 與既有欄位習慣。本測試 pin：
//! (1) intent.limit + TIF=PostOnly → row "Limit"
//! (2) intent.market → row "Market"
//! (3) 邊界（TIF=None / GTC / 未知 raw）。

use crate::bybit_private_ws::ExecutionUpdate;
use crate::database::TradingMsg;
use crate::event_consumer::types::{ExchangeEvent, PendingOrder, PendingOrderEvent};
use crate::order_manager::TimeInForce;
use crate::tick_pipeline::{PipelineKind, TickPipeline};
use tokio::sync::mpsc;

use super::super::loop_handlers::handle_exchange_event;
use super::super::loop_handlers::handle_pending_registration;
use super::make_test_pipeline;

/// Build a `LoopState` for the handler. We don't read it back here; the
/// handler only inserts into `pending_orders` after emitting the audit row.
/// 構建 LoopState；handler 在 emit audit row 後才插入 pending_orders，
/// 本測試僅檢查 channel 上的 TradingMsg::Order 形狀。
fn make_loop_state() -> super::super::loop_handlers::LoopState {
    super::super::loop_handlers::LoopState::new(std::collections::HashSet::new())
}

/// Drain the channel, find the first `TradingMsg::Order`, and return its
/// `order_type` + `time_in_force` fields. Panics if no Order msg is present
/// (caller must have dispatched something).
/// 抽乾 channel，回傳第一個 `TradingMsg::Order` 的 `order_type` + `time_in_force`。
/// 若無 Order msg 直接 panic（呼叫方應確認已派發）。
fn first_order_shape(rx: &mut mpsc::Receiver<TradingMsg>) -> (String, Option<String>) {
    while let Ok(msg) = rx.try_recv() {
        if let TradingMsg::Order {
            order_type,
            time_in_force,
            ..
        } = msg
        {
            return (order_type, time_in_force);
        }
    }
    panic!("no TradingMsg::Order observed on channel / channel 上未見 Order msg");
}

fn first_order_type(rx: &mut mpsc::Receiver<TradingMsg>) -> String {
    first_order_shape(rx).0
}

fn first_order_state_change(
    rx: &mut mpsc::Receiver<TradingMsg>,
) -> (String, String, Option<String>) {
    while let Ok(msg) = rx.try_recv() {
        if let TradingMsg::OrderStateChange {
            order_id,
            to_status,
            reason,
            ..
        } = msg
        {
            return (order_id, to_status, reason);
        }
    }
    panic!("no TradingMsg::OrderStateChange observed on channel / channel 上未見 OrderStateChange");
}

/// Build a baseline `PendingOrder` mirroring what `dispatch.rs:402` constructs
/// from `OrderDispatchRequest`. Caller overrides fields per scenario.
/// 構建 baseline PendingOrder（鏡射 dispatch.rs:402 由 OrderDispatchRequest
/// 構造的形狀），呼叫方依情境覆蓋欄位。
fn baseline_pending_order(order_type: &str, tif: Option<TimeInForce>) -> PendingOrder {
    PendingOrder {
        order_link_id: format!("oc_{}_test", order_type),
        symbol: "BTCUSDT".into(),
        is_long: true,
        qty: 0.01,
        strategy: "ma_crossover".into(),
        sent_ts_ms: 1_700_000_000_000,
        cum_filled_qty: 0.0,
        is_close: false,
        // FILL-CONTEXT-LINKAGE-1 placeholder; Order audit row doesn't read this.
        // FILL-CONTEXT-LINKAGE-1 占位；Order audit row 不讀取此欄位。
        context_id: "ctx-test".into(),
        order_type: order_type.to_string(),
        time_in_force: tif,
        maker_timeout_ms: tif.and(Some(45_000)),
        reference_price: None,
        reference_ts_ms: None,
        reference_source: None,
        cancel_requested_ts_ms: None,
    }
}

// ───────────────────────────────────────────────────────────────────────────
// Test 1: intent.limit + TIF=PostOnly → audit row "Limit" (was "Market" pre-fix)
// 測試 1：intent.limit + TIF=PostOnly → audit row "Limit"（修前為 "Market"）
// ───────────────────────────────────────────────────────────────────────────
#[test]
fn test_handle_pending_registration_limit_postonly_emits_limit_audit_row() {
    let mut pipeline = make_test_pipeline();
    let mut state = make_loop_state();
    let (tx, mut rx) = mpsc::channel::<TradingMsg>(8);

    let po = baseline_pending_order("limit", Some(TimeInForce::PostOnly));
    handle_pending_registration(
        Some(PendingOrderEvent::Register(po)),
        &mut pipeline,
        &mut state,
        Some(&tx),
    );

    let (order_type, time_in_force) = first_order_shape(&mut rx);
    assert_eq!(
        order_type, "Limit",
        "intent.order_type=limit + TIF=PostOnly must emit \"Limit\" audit row \
         (FIX-G7-09B regression — pre-fix hardcoded \"Market\" masked maker submits)"
    );
    assert_eq!(time_in_force.as_deref(), Some("PostOnly"));
}

// ───────────────────────────────────────────────────────────────────────────
// Test 2: intent.market → audit row "Market" (legacy path unchanged)
// 測試 2：intent.market → audit row "Market"（legacy 路徑不變）
// ───────────────────────────────────────────────────────────────────────────
#[test]
fn test_handle_pending_registration_market_emits_market_audit_row() {
    let mut pipeline = make_test_pipeline();
    let mut state = make_loop_state();
    let (tx, mut rx) = mpsc::channel::<TradingMsg>(8);

    let po = baseline_pending_order("market", None);
    handle_pending_registration(
        Some(PendingOrderEvent::Register(po)),
        &mut pipeline,
        &mut state,
        Some(&tx),
    );

    let (order_type, time_in_force) = first_order_shape(&mut rx);
    assert_eq!(
        order_type, "Market",
        "intent.order_type=market must emit \"Market\" audit row \
         (legacy/baseline path — fix must not regress Market dispatches)"
    );
    assert_eq!(time_in_force, None);
}

// ───────────────────────────────────────────────────────────────────────────
// Test 3: edge — limit + TIF=GTC (e.g. future maker variant) → "Limit"
// Test 3a: edge — limit + TIF=None (defensive — dispatch never sends this
//   shape today, but defaults to GTC at place_order; audit row should still
//   reflect order_type honestly).
// 測試 3：邊界 — limit + TIF=GTC（未來 maker variant）→ "Limit"
// 測試 3a：邊界 — limit + TIF=None（防禦性 — dispatch 目前不送此形狀，
//   place_order 預設 GTC；audit row 仍應誠實反映 order_type）。
// ───────────────────────────────────────────────────────────────────────────
#[test]
fn test_handle_pending_registration_limit_with_gtc_emits_limit_audit_row() {
    let mut pipeline = make_test_pipeline();
    let mut state = make_loop_state();
    let (tx, mut rx) = mpsc::channel::<TradingMsg>(8);

    let po = baseline_pending_order("limit", Some(TimeInForce::GTC));
    handle_pending_registration(
        Some(PendingOrderEvent::Register(po)),
        &mut pipeline,
        &mut state,
        Some(&tx),
    );

    let (order_type, time_in_force) = first_order_shape(&mut rx);
    assert_eq!(order_type, "Limit");
    assert_eq!(time_in_force.as_deref(), Some("GTC"));
}

#[test]
fn test_handle_pending_registration_limit_with_none_tif_still_emits_limit() {
    let mut pipeline = make_test_pipeline();
    let mut state = make_loop_state();
    let (tx, mut rx) = mpsc::channel::<TradingMsg>(8);

    let po = baseline_pending_order("limit", None);
    handle_pending_registration(
        Some(PendingOrderEvent::Register(po)),
        &mut pipeline,
        &mut state,
        Some(&tx),
    );

    let order_type = first_order_type(&mut rx);
    assert_eq!(
        order_type, "Limit",
        "TIF=None must not downgrade audit row to Market — order_type alone \
         drives the column (TIF column lives elsewhere if added)"
    );
}

/// Test 4: defensive — unknown raw `order_type` falls back to lowercased raw,
/// not silently to "Market". Surfaces caller bugs in PG instead of hiding them.
/// 測試 4：防禦性 — 未知 raw `order_type` fallback 為 lowercased raw，
/// 不靜默映為 "Market"。caller bug 在 PG 顯露而非被遮蓋。
#[test]
fn test_handle_pending_registration_unknown_order_type_falls_back_to_raw() {
    let mut pipeline = make_test_pipeline();
    let mut state = make_loop_state();
    let (tx, mut rx) = mpsc::channel::<TradingMsg>(8);

    let po = baseline_pending_order("conditional", None); // not market/limit
    handle_pending_registration(
        Some(PendingOrderEvent::Register(po)),
        &mut pipeline,
        &mut state,
        Some(&tx),
    );

    let order_type = first_order_type(&mut rx);
    assert_eq!(
        order_type, "conditional",
        "unknown order_type must NOT silently map to \"Market\" — defensive \
         fallback surfaces caller bugs in PG instead of hiding them"
    );
}

/// Test 5: also verify `handle_pending_registration` still inserts into
/// `state.pending_orders` (so fill-matching path keeps working). This is
/// covered by other tests indirectly but pinning it here protects the fix
/// from accidental refactor regression.
/// 測試 5：驗證 handle_pending_registration 仍把 PendingOrder 插入
/// state.pending_orders（fill 匹配路徑依賴此）。修法不應影響 insert 行為。
#[test]
fn test_handle_pending_registration_still_inserts_pending_order() {
    let mut pipeline = make_test_pipeline();
    let mut state = make_loop_state();
    let (tx, _rx) = mpsc::channel::<TradingMsg>(8);

    let po = baseline_pending_order("limit", Some(TimeInForce::PostOnly));
    let link_id = po.order_link_id.clone();
    handle_pending_registration(
        Some(PendingOrderEvent::Register(po)),
        &mut pipeline,
        &mut state,
        Some(&tx),
    );

    assert!(
        state.pending_orders.contains_key(&link_id),
        "PendingOrder must be inserted into state.pending_orders for fill matching"
    );
    let stored = &state.pending_orders[&link_id];
    assert_eq!(stored.order_type, "limit");
    assert_eq!(stored.time_in_force, Some(TimeInForce::PostOnly));
}

#[test]
fn test_dispatch_failed_removes_pending_order_and_emits_terminal_state() {
    let mut pipeline = make_test_pipeline();
    let mut state = make_loop_state();
    let (tx, mut rx) = mpsc::channel::<TradingMsg>(8);

    let mut po = baseline_pending_order("market", None);
    po.is_close = true;
    let link_id = po.order_link_id.clone();
    state.pending_orders.insert(link_id.clone(), po);

    handle_pending_registration(
        Some(PendingOrderEvent::DispatchFailed {
            order_link_id: link_id.clone(),
            symbol: "BTCUSDT".into(),
            is_close: true,
            terminal_status: "Rejected".into(),
            reason: "dispatch_structural: test".into(),
            ts_ms: 1_700_000_000_123,
        }),
        &mut pipeline,
        &mut state,
        Some(&tx),
    );

    assert!(
        !state.pending_orders.contains_key(&link_id),
        "dispatch-failed terminal event must remove stale pending order"
    );
    let (order_id, to_status, reason) = first_order_state_change(&mut rx);
    assert_eq!(order_id, link_id);
    assert_eq!(to_status, "Rejected");
    assert_eq!(reason.as_deref(), Some("dispatch_structural: test"));
}

#[tokio::test]
async fn test_ambiguous_fill_before_order_update_emits_unattributed_fill() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    let mut writer = super::make_test_writer();
    let mut state = make_loop_state();
    let (tx, mut rx) = mpsc::channel::<TradingMsg>(8);

    let mut po1 = baseline_pending_order("market", None);
    po1.order_link_id = "oc_ambiguous_1".into();
    po1.symbol = "BTCUSDT".into();
    po1.is_long = true;
    let mut po2 = baseline_pending_order("market", None);
    po2.order_link_id = "oc_ambiguous_2".into();
    po2.symbol = "BTCUSDT".into();
    po2.is_long = true;
    state.pending_orders.insert(po1.order_link_id.clone(), po1);
    state.pending_orders.insert(po2.order_link_id.clone(), po2);

    let exec = ExecutionUpdate {
        exec_id: "exec-ambiguous".into(),
        order_id: "bybit-order-without-prior-update".into(),
        symbol: "BTCUSDT".into(),
        side: "Buy".into(),
        exec_price: "100.0".into(),
        exec_qty: "0.01".into(),
        exec_fee: "0.001".into(),
        exec_type: "Trade".into(),
        exec_time: "1700000000123".into(),
        ..Default::default()
    };

    handle_exchange_event(
        Some(ExchangeEvent::Fill(exec)),
        &mut pipeline,
        &mut writer,
        &mut state,
        Some(&tx),
    )
    .await;

    assert_eq!(
        state.pending_orders.len(),
        2,
        "ambiguous fallback must not attach fill to an arbitrary pending order"
    );
    match rx.try_recv().expect("unattributed fill audit row") {
        TradingMsg::Fill {
            fill_id,
            strategy_name,
            ..
        } => {
            assert_eq!(fill_id, "unattrib-exec-ambiguous");
            assert_eq!(strategy_name, "unattributed:bybit_auto");
        }
        other => panic!("expected unattributed Fill, got {other:?}"),
    }
}

#[tokio::test]
async fn test_qty_zero_full_close_fill_before_order_update_matches_pending_order() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    let mut writer = super::make_test_writer();
    let mut state = make_loop_state();
    let (tx, mut rx) = mpsc::channel::<TradingMsg>(8);

    let mut po = baseline_pending_order("market", None);
    po.order_link_id = "oc_qty_zero_close".into();
    po.symbol = "BTCUSDT".into();
    po.is_long = false;
    po.qty = 0.0;
    po.is_close = true;
    state.pending_orders.insert(po.order_link_id.clone(), po);

    let exec = ExecutionUpdate {
        exec_id: "exec-qty-zero-close".into(),
        order_id: "bybit-close-before-order-update".into(),
        symbol: "BTCUSDT".into(),
        side: "Sell".into(),
        exec_price: "100.0".into(),
        exec_qty: "0.01".into(),
        exec_fee: "0.001".into(),
        exec_type: "Trade".into(),
        exec_time: "1700000000456".into(),
        ..Default::default()
    };

    handle_exchange_event(
        Some(ExchangeEvent::Fill(exec)),
        &mut pipeline,
        &mut writer,
        &mut state,
        Some(&tx),
    )
    .await;

    assert!(
        state.pending_orders.is_empty(),
        "qty=0 reduce-only full-close fills must match and remove their PendingOrder"
    );

    let (order_id, to_status, reason) = first_order_state_change(&mut rx);
    assert_eq!(order_id, "oc_qty_zero_close");
    assert_eq!(to_status, "Filled");
    assert_eq!(reason, None);
    assert!(
        rx.try_recv().is_err(),
        "matched qty=0 close fill must not emit an unattributed audit row"
    );
}
