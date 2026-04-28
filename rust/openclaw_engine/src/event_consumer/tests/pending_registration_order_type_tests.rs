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

use crate::database::TradingMsg;
use crate::event_consumer::types::PendingOrder;
use crate::order_manager::TimeInForce;
use tokio::sync::mpsc;

use super::make_test_pipeline;
use super::super::loop_handlers::handle_pending_registration;

/// Build a `LoopState` for the handler. We don't read it back here; the
/// handler only inserts into `pending_orders` after emitting the audit row.
/// 構建 LoopState；handler 在 emit audit row 後才插入 pending_orders，
/// 本測試僅檢查 channel 上的 TradingMsg::Order 形狀。
fn make_loop_state() -> super::super::loop_handlers::LoopState {
    super::super::loop_handlers::LoopState::new(std::collections::HashSet::new())
}

/// Drain the channel, find the first `TradingMsg::Order`, and return its
/// `order_type` field. Panics if no Order msg is present (caller must have
/// dispatched something).
/// 抽乾 channel，回傳第一個 `TradingMsg::Order` 的 `order_type`。
/// 若無 Order msg 直接 panic（呼叫方應確認已派發）。
fn first_order_type(rx: &mut mpsc::Receiver<TradingMsg>) -> String {
    while let Ok(msg) = rx.try_recv() {
        if let TradingMsg::Order { order_type, .. } = msg {
            return order_type;
        }
    }
    panic!("no TradingMsg::Order observed on channel / channel 上未見 Order msg");
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
    let pipeline = make_test_pipeline();
    let mut state = make_loop_state();
    let (tx, mut rx) = mpsc::channel::<TradingMsg>(8);

    let po = baseline_pending_order("limit", Some(TimeInForce::PostOnly));
    handle_pending_registration(Some(po), &pipeline, &mut state, Some(&tx));

    let order_type = first_order_type(&mut rx);
    assert_eq!(
        order_type, "Limit",
        "intent.order_type=limit + TIF=PostOnly must emit \"Limit\" audit row \
         (FIX-G7-09B regression — pre-fix hardcoded \"Market\" masked maker submits)"
    );
}

// ───────────────────────────────────────────────────────────────────────────
// Test 2: intent.market → audit row "Market" (legacy path unchanged)
// 測試 2：intent.market → audit row "Market"（legacy 路徑不變）
// ───────────────────────────────────────────────────────────────────────────
#[test]
fn test_handle_pending_registration_market_emits_market_audit_row() {
    let pipeline = make_test_pipeline();
    let mut state = make_loop_state();
    let (tx, mut rx) = mpsc::channel::<TradingMsg>(8);

    let po = baseline_pending_order("market", None);
    handle_pending_registration(Some(po), &pipeline, &mut state, Some(&tx));

    let order_type = first_order_type(&mut rx);
    assert_eq!(
        order_type, "Market",
        "intent.order_type=market must emit \"Market\" audit row \
         (legacy/baseline path — fix must not regress Market dispatches)"
    );
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
    let pipeline = make_test_pipeline();
    let mut state = make_loop_state();
    let (tx, mut rx) = mpsc::channel::<TradingMsg>(8);

    let po = baseline_pending_order("limit", Some(TimeInForce::GTC));
    handle_pending_registration(Some(po), &pipeline, &mut state, Some(&tx));

    let order_type = first_order_type(&mut rx);
    assert_eq!(order_type, "Limit");
}

#[test]
fn test_handle_pending_registration_limit_with_none_tif_still_emits_limit() {
    let pipeline = make_test_pipeline();
    let mut state = make_loop_state();
    let (tx, mut rx) = mpsc::channel::<TradingMsg>(8);

    let po = baseline_pending_order("limit", None);
    handle_pending_registration(Some(po), &pipeline, &mut state, Some(&tx));

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
    let pipeline = make_test_pipeline();
    let mut state = make_loop_state();
    let (tx, mut rx) = mpsc::channel::<TradingMsg>(8);

    let po = baseline_pending_order("conditional", None); // not market/limit
    handle_pending_registration(Some(po), &pipeline, &mut state, Some(&tx));

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
    let pipeline = make_test_pipeline();
    let mut state = make_loop_state();
    let (tx, _rx) = mpsc::channel::<TradingMsg>(8);

    let po = baseline_pending_order("limit", Some(TimeInForce::PostOnly));
    let link_id = po.order_link_id.clone();
    handle_pending_registration(Some(po), &pipeline, &mut state, Some(&tx));

    assert!(
        state.pending_orders.contains_key(&link_id),
        "PendingOrder must be inserted into state.pending_orders for fill matching"
    );
    let stored = &state.pending_orders[&link_id];
    assert_eq!(stored.order_type, "limit");
    assert_eq!(stored.time_in_force, Some(TimeInForce::PostOnly));
}
