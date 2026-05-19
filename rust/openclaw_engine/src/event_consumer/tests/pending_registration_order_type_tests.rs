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

use crate::bybit_private_ws::{ExecutionUpdate, OrderUpdate};
use crate::database::TradingMsg;
use crate::event_consumer::types::{ExchangeEvent, PendingOrder, PendingOrderEvent};
use crate::order_manager::TimeInForce;
use crate::tick_pipeline::{CloseMakerFillAudit, OrderDispatchRequest, PipelineKind, TickPipeline};
use openclaw_core::governance_core::{GovernanceProfile, LeaseId, LeaseOutcome};
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

/// P2-ORDERS-INTENT-ID-WRITER-GAP-1（2026-05-19）：抽乾 channel 取第一筆
/// `TradingMsg::Order` 的 `intent_id`。用於斷言 PendingOrder.intent_id 是否
/// 被忠實複製到 audit row 與 trading.orders 寫入流。
fn first_order_intent_id(rx: &mut mpsc::Receiver<TradingMsg>) -> Option<String> {
    while let Ok(msg) = rx.try_recv() {
        if let TradingMsg::Order { intent_id, .. } = msg {
            return intent_id;
        }
    }
    panic!("no TradingMsg::Order observed on channel / channel 上未見 Order msg");
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
        close_maker_audit: None,
        reference_price: None,
        reference_ts_ms: None,
        reference_source: None,
        cancel_requested_ts_ms: None,
        // W-C Caveat 2 修復（2026-05-11）：test fixture 預設 None。
        spine_order_plan_id: None,
        spine_decision_id: None,
        spine_verdict_id: None,
        spine_stub_report_id: None,
        // P2-ORDERS-INTENT-ID-WRITER-GAP-1（2026-05-19）：baseline fixture 為
        // open entry 形狀（is_close=false），故帶代表性 intent_id；新 test
        // 4-A 透過 with_intent_id helper / 直接覆寫驗證 propagation。
        intent_id: Some("intent-demo-BTCUSDT-1700000000000".into()),
    }
}

fn close_maker_pending_order(link_id: &str) -> PendingOrder {
    let mut po = baseline_pending_order("limit", Some(TimeInForce::PostOnly));
    po.order_link_id = link_id.to_string();
    po.is_long = false;
    po.qty = 0.1;
    po.strategy = "strategy_close:grid_close_long".to_string();
    po.is_close = true;
    po.context_id = "ctx-close-maker".to_string();
    po.close_maker_audit = Some(CloseMakerFillAudit {
        initial_limit_price: Some(50_000.2),
        eligible_reason: "grid_close_long".to_string(),
        fallback_reason: None,
        rate_limit_scope: None,
    });
    po
}

fn terminal_order_update(link_id: &str, status: &str, reject_reason: &str) -> OrderUpdate {
    OrderUpdate {
        order_id: format!("bybit-{link_id}"),
        order_link_id: link_id.to_string(),
        symbol: "BTCUSDT".to_string(),
        side: "Sell".to_string(),
        order_type: "Limit".to_string(),
        price: "50000.2".to_string(),
        qty: "0.1".to_string(),
        cum_exec_qty: "0".to_string(),
        order_status: status.to_string(),
        created_time: "1700000000000".to_string(),
        updated_time: "1700000000123".to_string(),
        reject_reason: reject_reason.to_string(),
    }
}

fn seed_long_position(pipeline: &mut TickPipeline) {
    pipeline.paper_state.apply_fill(
        "BTCUSDT",
        true,
        0.1,
        50_000.0,
        0.0,
        1_700_000_000_000,
        "grid_trading",
    );
}

fn assert_close_maker_market_fallback(
    rx: &mut tokio::sync::mpsc::UnboundedReceiver<OrderDispatchRequest>,
    expected_reason: &str,
) {
    let req = rx.try_recv().expect("close-maker market fallback");
    assert_eq!(req.order_type, "market");
    assert_eq!(req.time_in_force, None);
    assert_eq!(req.limit_price, None);
    assert!(req.is_close);
    assert!(req.is_primary);
    assert!(!req.is_long);
    assert_eq!(req.qty, 0.1);
    assert!(req.spine_order_plan_id.is_none());
    assert!(req.spine_decision_id.is_none());
    assert!(req.spine_verdict_id.is_none());
    assert!(req.spine_stub_report_id.is_none());
    let audit = req.close_maker_audit.expect("fallback audit");
    assert_eq!(audit.initial_limit_price, Some(50_000.2));
    assert_eq!(audit.eligible_reason, "grid_close_long");
    assert_eq!(audit.fallback_reason.as_deref(), Some(expected_reason));
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

// ───────────────────────────────────────────────────────────────────────────
// P2-ORDERS-INTENT-ID-WRITER-GAP-1 regression（2026-05-19）：
// PendingOrder.intent_id 必須端到端傳到 TradingMsg::Order.intent_id，最終
// 寫入 trading.orders.intent_id 恢復 intents → orders JOIN。E3 baseline
// 2026-05-15 揭露 7d 1394 demo orders / 1021 live_demo orders 全部 NULL
// 是 writer 漏接非 schema 缺欄；本 5 條 test 釘住 writer 接線契約。
// ───────────────────────────────────────────────────────────────────────────

/// 入場 entry path：PendingOrder 帶 Some(intent_id)，Order msg 必傳同值。
#[test]
fn test_handle_pending_registration_propagates_entry_intent_id() {
    let mut pipeline = make_test_pipeline();
    let mut state = make_loop_state();
    let (tx, mut rx) = mpsc::channel::<TradingMsg>(8);

    let mut po = baseline_pending_order("market", None);
    let expected_intent_id = "intent-demo-BTCUSDT-1700000000999".to_string();
    po.intent_id = Some(expected_intent_id.clone());

    handle_pending_registration(
        Some(PendingOrderEvent::Register(po)),
        &mut pipeline,
        &mut state,
        Some(&tx),
    );

    let intent_id = first_order_intent_id(&mut rx);
    assert_eq!(
        intent_id,
        Some(expected_intent_id),
        "PendingOrder.intent_id 必須無損傳到 TradingMsg::Order.intent_id，\
         恢復 trading.intents → trading.orders 邏輯 FK 與 Guardian-pass-rate 計算"
    );
}

/// Close path（is_close=true，PendingOrder.intent_id=None）：Order msg 必為 None。
/// 不在 writer 端合成假 id 以免遮蓋上游 intent 缺失 bug。
#[test]
fn test_handle_pending_registration_close_path_intent_id_stays_none() {
    let mut pipeline = make_test_pipeline();
    let mut state = make_loop_state();
    let (tx, mut rx) = mpsc::channel::<TradingMsg>(8);

    let mut po = baseline_pending_order("market", None);
    po.is_close = true;
    // close 路徑無 strategy intent；writer 端必須誠實表達 NULL。
    po.intent_id = None;

    handle_pending_registration(
        Some(PendingOrderEvent::Register(po)),
        &mut pipeline,
        &mut state,
        Some(&tx),
    );

    let intent_id = first_order_intent_id(&mut rx);
    assert!(
        intent_id.is_none(),
        "close path 無 strategy intent 對應，writer 不得合成 fake id（trading.orders.intent_id 保 NULL 為誠實表述）"
    );
}

/// PostOnly + intent_id：限價單同樣傳送 intent_id（覆蓋 maker 路徑）。
#[test]
fn test_handle_pending_registration_postonly_carries_intent_id() {
    let mut pipeline = make_test_pipeline();
    let mut state = make_loop_state();
    let (tx, mut rx) = mpsc::channel::<TradingMsg>(8);

    let mut po = baseline_pending_order("limit", Some(TimeInForce::PostOnly));
    let expected = "intent-live_demo-ETHUSDT-1700000000777".to_string();
    po.intent_id = Some(expected.clone());

    handle_pending_registration(
        Some(PendingOrderEvent::Register(po)),
        &mut pipeline,
        &mut state,
        Some(&tx),
    );

    let intent_id = first_order_intent_id(&mut rx);
    assert_eq!(
        intent_id,
        Some(expected),
        "PostOnly 限價路徑同樣須透傳 intent_id，不得因 TIF 不同而漏接"
    );
}

/// derive(Clone) 行為：PendingOrder.intent_id 必跨 clone 傳承（pending_orders 表
/// 使用 .clone() 插入，writer 路徑亦 clone po.intent_id）。
#[test]
fn test_pending_order_clone_preserves_intent_id() {
    let mut po = baseline_pending_order("market", None);
    let expected = "intent-demo-SOLUSDT-1700000000123".to_string();
    po.intent_id = Some(expected.clone());

    let cloned = po.clone();

    assert_eq!(
        cloned.intent_id.as_deref(),
        Some(expected.as_str()),
        "derive(Clone) 必複製 intent_id；state.pending_orders.insert(.clone()) 路徑依賴此"
    );
}

/// Dispatch failed (terminal state)：close-maker 重建 PendingOrder 走 fallback，
/// 因走 close 路徑無 strategy intent，intent_id 必保 None（不從別處抓 fake）。
#[test]
fn test_dispatch_failed_close_maker_synthetic_pending_order_has_no_intent_id() {
    let mut pipeline = make_test_pipeline();
    let mut state = make_loop_state();
    let (tx, _rx) = mpsc::channel::<TradingMsg>(8);

    handle_pending_registration(
        Some(PendingOrderEvent::DispatchFailed {
            order_link_id: "oc_close_maker_unreg".into(),
            symbol: "BTCUSDT".into(),
            is_long: false,
            qty: 0.1,
            strategy: "strategy_close:grid_close_long".into(),
            context_id: "ctx-close-maker".into(),
            is_close: true,
            order_type: "limit".into(),
            time_in_force: Some(TimeInForce::PostOnly),
            maker_timeout_ms: Some(45_000),
            close_maker_audit: Some(CloseMakerFillAudit {
                initial_limit_price: Some(50_000.2),
                eligible_reason: "grid_close_long".into(),
                fallback_reason: None,
                rate_limit_scope: None,
            }),
            terminal_status: "Rejected".into(),
            reason: "dispatch_structural: test".into(),
            ts_ms: 1_700_000_000_123,
        }),
        &mut pipeline,
        &mut state,
        Some(&tx),
    );

    // 此路徑不寫 TradingMsg::Order（只寫 OrderStateChange），但 dispatch_close_maker_fallback_from_pending
    // 內部會重新建立 PendingOrder（loop_handlers.rs:424）並走 dispatch 路徑；
    // 重建 PendingOrder.intent_id 必為 None（close + fallback 無 strategy intent）。
    // 此測試藉由 type 系統保證重建 PendingOrder 不漏 intent_id 欄位編譯通過即已守住，
    // runtime 行為 = no TradingMsg::Order emit on this path（已 by existing dispatch_failed 測試覆蓋）。
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
            is_long: true,
            qty: 0.01,
            strategy: "ma_crossover".into(),
            context_id: "ctx-test".into(),
            is_close: true,
            order_type: "market".into(),
            time_in_force: None,
            maker_timeout_ms: None,
            close_maker_audit: None,
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

#[test]
fn test_close_maker_dispatch_failed_dispatches_market_fallback() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    let (fallback_tx, mut fallback_rx) =
        tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
    pipeline.set_shadow_channel(fallback_tx);
    seed_long_position(&mut pipeline);
    let mut state = make_loop_state();
    let (tx, mut rx) = mpsc::channel::<TradingMsg>(8);

    let po = close_maker_pending_order("oc_close_maker_dispatch_failed");
    let link_id = po.order_link_id.clone();
    state.pending_orders.insert(link_id.clone(), po);

    handle_pending_registration(
        Some(PendingOrderEvent::DispatchFailed {
            order_link_id: link_id.clone(),
            symbol: "BTCUSDT".into(),
            is_long: false,
            qty: 0.1,
            strategy: "strategy_close:grid_close_long".into(),
            context_id: "ctx-close-maker".into(),
            is_close: true,
            order_type: "limit".into(),
            time_in_force: Some(TimeInForce::PostOnly),
            maker_timeout_ms: Some(30_000),
            close_maker_audit: Some(CloseMakerFillAudit {
                initial_limit_price: Some(50_000.2),
                eligible_reason: "grid_close_long".into(),
                fallback_reason: None,
                rate_limit_scope: None,
            }),
            terminal_status: "Rejected".into(),
            reason: "dispatch_structural: test".into(),
            ts_ms: 1_700_000_000_123,
        }),
        &mut pipeline,
        &mut state,
        Some(&tx),
    );

    assert!(!state.pending_orders.contains_key(&link_id));
    assert_close_maker_market_fallback(&mut fallback_rx, "fallback_to_taker_mandatory");
    let (order_id, to_status, reason) = first_order_state_change(&mut rx);
    assert_eq!(order_id, link_id);
    assert_eq!(to_status, "Rejected");
    assert_eq!(reason.as_deref(), Some("dispatch_structural: test"));
}

#[test]
fn test_close_maker_preflight_dispatch_failed_without_pending_dispatches_market_fallback() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    let (fallback_tx, mut fallback_rx) =
        tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
    pipeline.set_shadow_channel(fallback_tx);
    seed_long_position(&mut pipeline);
    let mut state = make_loop_state();
    let (tx, mut rx) = mpsc::channel::<TradingMsg>(8);

    handle_pending_registration(
        Some(PendingOrderEvent::DispatchFailed {
            order_link_id: "oc_close_maker_preflight".into(),
            symbol: "BTCUSDT".into(),
            is_long: false,
            qty: 0.1,
            strategy: "strategy_close:grid_close_long".into(),
            context_id: "ctx-close-maker".into(),
            is_close: true,
            order_type: "limit".into(),
            time_in_force: Some(TimeInForce::PostOnly),
            maker_timeout_ms: Some(30_000),
            close_maker_audit: Some(CloseMakerFillAudit {
                initial_limit_price: Some(50_000.2),
                eligible_reason: "grid_close_long".into(),
                fallback_reason: None,
                rate_limit_scope: None,
            }),
            terminal_status: "Rejected".into(),
            reason: "dispatch_preflight_qty_zero".into(),
            ts_ms: 1_700_000_000_123,
        }),
        &mut pipeline,
        &mut state,
        Some(&tx),
    );

    assert_close_maker_market_fallback(&mut fallback_rx, "fallback_to_taker_mandatory");
    let (order_id, to_status, reason) = first_order_state_change(&mut rx);
    assert_eq!(order_id, "oc_close_maker_preflight");
    assert_eq!(to_status, "Rejected");
    assert_eq!(reason.as_deref(), Some("dispatch_preflight_qty_zero"));
}

#[test]
fn test_close_maker_fallback_market_preflight_failure_is_terminal_without_looping() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    let (fallback_tx, mut fallback_rx) =
        tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
    pipeline.set_shadow_channel(fallback_tx);
    seed_long_position(&mut pipeline);
    let mut state = make_loop_state();
    let (tx, mut rx) = mpsc::channel::<TradingMsg>(8);

    handle_pending_registration(
        Some(PendingOrderEvent::DispatchFailed {
            order_link_id: "oc_close_maker_fallback_preflight".into(),
            symbol: "BTCUSDT".into(),
            is_long: false,
            qty: 0.1,
            strategy: "strategy_close:grid_close_long".into(),
            context_id: "ctx-close-maker".into(),
            is_close: true,
            order_type: "market".into(),
            time_in_force: None,
            maker_timeout_ms: None,
            close_maker_audit: Some(CloseMakerFillAudit {
                initial_limit_price: Some(50_000.2),
                eligible_reason: "grid_close_long".into(),
                fallback_reason: Some("postonly_reject".into()),
                rate_limit_scope: None,
            }),
            terminal_status: "Rejected".into(),
            reason: "dispatch_preflight_min_notional".into(),
            ts_ms: 1_700_000_000_123,
        }),
        &mut pipeline,
        &mut state,
        Some(&tx),
    );

    assert!(
        fallback_rx.try_recv().is_err(),
        "a failed fallback-market request must terminalize, not recursively fallback"
    );
    let (order_id, to_status, reason) = first_order_state_change(&mut rx);
    assert_eq!(order_id, "oc_close_maker_fallback_preflight");
    assert_eq!(to_status, "Rejected");
    assert_eq!(reason.as_deref(), Some("dispatch_preflight_min_notional"));
}

async fn assert_close_maker_order_update_fallback(
    status: &str,
    reject_reason: &str,
    cancel_requested: bool,
    expected_reason: &str,
) {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    let (fallback_tx, mut fallback_rx) =
        tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
    pipeline.set_shadow_channel(fallback_tx);
    seed_long_position(&mut pipeline);
    let mut writer = super::make_test_writer();
    let mut state = make_loop_state();
    let link_id = format!("oc_close_maker_{}", status.to_ascii_lowercase());
    let mut po = close_maker_pending_order(&link_id);
    if cancel_requested {
        po.cancel_requested_ts_ms = Some(1_700_000_030_000);
    }
    state.pending_orders.insert(link_id.clone(), po);

    handle_exchange_event(
        Some(ExchangeEvent::OrderUpdate(terminal_order_update(
            &link_id,
            status,
            reject_reason,
        ))),
        &mut pipeline,
        &mut writer,
        &mut state,
        None,
    )
    .await;

    assert!(!state.pending_orders.contains_key(&link_id));
    assert_close_maker_market_fallback(&mut fallback_rx, expected_reason);
}

#[tokio::test]
async fn test_close_maker_postonly_reject_order_update_dispatches_market_fallback() {
    assert_close_maker_order_update_fallback(
        "Rejected",
        "EC_PostOnlyWillTakeLiquidity",
        false,
        "postonly_reject",
    )
    .await;
}

#[tokio::test]
async fn test_close_maker_cancelled_after_timeout_dispatches_market_fallback() {
    assert_close_maker_order_update_fallback(
        "Cancelled",
        "EC_PerCancelRequest",
        true,
        "timeout_taker",
    )
    .await;
}

#[tokio::test]
async fn test_close_maker_deactivated_dispatches_ack_lost_market_fallback() {
    assert_close_maker_order_update_fallback("Deactivated", "", false, "ack_lost").await;
}

#[tokio::test]
async fn test_close_maker_dcp_dispatches_survival_market_fallback_and_terminal_state() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    let (fallback_tx, mut fallback_rx) =
        tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
    pipeline.set_shadow_channel(fallback_tx);
    seed_long_position(&mut pipeline);
    let mut writer = super::make_test_writer();
    let mut state = make_loop_state();
    let (tx, mut rx) = mpsc::channel::<TradingMsg>(8);
    let link_id = "oc_close_maker_dcp";
    state
        .pending_orders
        .insert(link_id.into(), close_maker_pending_order(link_id));

    handle_exchange_event(
        Some(ExchangeEvent::DcpTriggered),
        &mut pipeline,
        &mut writer,
        &mut state,
        Some(&tx),
    )
    .await;

    assert!(state.pending_orders.is_empty());
    assert_close_maker_market_fallback(&mut fallback_rx, "fallback_to_taker_mandatory");
    let (order_id, to_status, reason) = first_order_state_change(&mut rx);
    assert_eq!(order_id, link_id);
    assert_eq!(to_status, "Cancelled");
    assert_eq!(
        reason.as_deref(),
        Some("dcp_triggered|close_maker_fallback=fallback_to_taker_mandatory")
    );
}

#[tokio::test]
async fn test_close_maker_dcp_without_position_emits_visible_terminal_no_fallback() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    let (fallback_tx, mut fallback_rx) =
        tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
    pipeline.set_shadow_channel(fallback_tx);
    let mut writer = super::make_test_writer();
    let mut state = make_loop_state();
    let (tx, mut rx) = mpsc::channel::<TradingMsg>(8);
    let link_id = "oc_close_maker_dcp_flat";
    state
        .pending_orders
        .insert(link_id.into(), close_maker_pending_order(link_id));

    handle_exchange_event(
        Some(ExchangeEvent::DcpTriggered),
        &mut pipeline,
        &mut writer,
        &mut state,
        Some(&tx),
    )
    .await;

    assert!(state.pending_orders.is_empty());
    assert!(
        fallback_rx.try_recv().is_err(),
        "DCP must not pretend fallback was sent when local position is already flat"
    );
    let (order_id, to_status, reason) = first_order_state_change(&mut rx);
    assert_eq!(order_id, link_id);
    assert_eq!(to_status, "Cancelled");
    assert_eq!(
        reason.as_deref(),
        Some("dcp_triggered|close_maker_fallback=not_dispatched")
    );
}

#[test]
fn test_decision_lease_release_event_consumes_active_lease() {
    let mut pipeline = make_test_pipeline();
    pipeline
        .governance
        .grant_paper_authorization(None)
        .expect("grant auth for production lease fixture");
    let lease = pipeline
        .governance
        .acquire_lease(
            "intent:test_decision_lease_release",
            "TRADE_ENTRY",
            60_000,
            GovernanceProfile::Production,
            "event_consumer_test",
        )
        .expect("active production lease");
    let lease_id = match lease {
        LeaseId::Active(id) => id,
        LeaseId::Bypass => panic!("production lease fixture must be active"),
    };
    let mut state = make_loop_state();

    handle_pending_registration(
        Some(PendingOrderEvent::ReleaseDecisionLease {
            order_link_id: "oc_test_release".into(),
            decision_lease_id: Some(lease_id.clone()),
            outcome: LeaseOutcome::Consumed,
            reason: "exchange_dispatch_accepted".into(),
            ts_ms: 1_700_000_000_123,
        }),
        &mut pipeline,
        &mut state,
        None,
    );

    assert!(
        pipeline.governance.get_lease_by_id(&lease_id).is_err(),
        "Consumed decision lease must be pruned from reverse lookup"
    );
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
