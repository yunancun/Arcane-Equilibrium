//! Resting-limit-order tests — sweep classifier / FIFO / funding drag guard.
//! 紙盤掛單隊列測試 — sweep classifier / FIFO / funding drag guard。
//!
//! MODULE_NOTE (EN): Extracted from `resting_orders.rs` as Wave 1 G1-03 to
//!   pull `resting_orders.rs` under CLAUDE.md §九 1200-line hard limit. The
//!   test body is included back into the parent via
//!   `#[cfg(test)] #[path = "resting_orders_tests.rs"] mod tests;` at the
//!   foot of `resting_orders.rs`, so every helper / bias-guard test keeps
//!   `use super::*;` semantics — no visibility changes required. Bit-
//!   identical test content vs pre-split (708 asserted LOC).
//! MODULE_NOTE (中): 從 `resting_orders.rs` 抽出（Wave 1 G1-03），讓父檔進
//!   §九 1200 行硬上限。測試主體透過父檔底部
//!   `#[cfg(test)] #[path = "resting_orders_tests.rs"] mod tests;` 重新
//!   納入，`use super::*;` 語義不變、可見性無需調整。行為等價（708 行原樣）。

use super::*;
use crate::paper_state::PaperState;

fn make_order(link_id: &str, symbol: &str, submit_ts: u64, deadline_ms: u64) -> RestingLimitOrder {
    RestingLimitOrder {
        symbol: symbol.to_string(),
        is_long: true,
        qty: 0.1,
        limit_price: 50_000.0,
        time_in_force: TimeInForce::PostOnly,
        submit_ts_ms: submit_ts,
        deadline_ms,
        mid_price_at_submit: 50_001.0,
        order_link_id: link_id.to_string(),
        context_id: "ctx_test".to_string(),
        strategy: "grid_trading".to_string(),
        funding_rate_at_submit: 0.0,
    }
}

#[test]
fn test_resting_queue_empty_by_default() {
    // Fresh PaperState must have an empty queue — 1B-4.1 is zero-behavior.
    // 全新 PaperState 的隊列必須為空 — 1B-4.1 零行為。
    let s = PaperState::new(10_000.0);
    assert_eq!(s.resting_limit_order_count(), 0);
    assert!(s.resting_limit_orders_for("BTCUSDT").is_empty());
}

#[test]
fn test_enqueue_preserves_fifo_per_symbol() {
    let mut s = PaperState::new(10_000.0);
    s.enqueue_resting_limit_order(make_order("oc_1", "BTCUSDT", 1_000, 46_000));
    s.enqueue_resting_limit_order(make_order("oc_2", "BTCUSDT", 2_000, 47_000));
    s.enqueue_resting_limit_order(make_order("oc_3", "ETHUSDT", 3_000, 48_000));
    assert_eq!(s.resting_limit_order_count(), 3);
    assert_eq!(s.resting_limit_order_count_for("BTCUSDT"), 2);
    assert_eq!(s.resting_limit_order_count_for("ETHUSDT"), 1);
    let btc = s.resting_limit_orders_for("BTCUSDT");
    assert_eq!(btc[0].order_link_id, "oc_1");
    assert_eq!(btc[1].order_link_id, "oc_2");
}

#[test]
fn test_enqueue_unseen_symbol_returns_empty_slice() {
    let s = PaperState::new(10_000.0);
    // symbol never enqueued → empty slice, not panic.
    assert!(s.resting_limit_orders_for("DOGEUSDT").is_empty());
    assert_eq!(s.resting_limit_order_count_for("DOGEUSDT"), 0);
}

#[test]
fn test_remove_by_link_id_returns_removed_and_decrements_count() {
    let mut s = PaperState::new(10_000.0);
    s.enqueue_resting_limit_order(make_order("oc_1", "BTCUSDT", 1_000, 46_000));
    s.enqueue_resting_limit_order(make_order("oc_2", "BTCUSDT", 2_000, 47_000));
    let removed = s.remove_resting_limit_order_by_link_id("oc_1");
    assert!(removed.is_some());
    assert_eq!(removed.unwrap().order_link_id, "oc_1");
    assert_eq!(s.resting_limit_order_count_for("BTCUSDT"), 1);
    // Surviving order kept its FIFO position.
    assert_eq!(
        s.resting_limit_orders_for("BTCUSDT")[0].order_link_id,
        "oc_2"
    );
}

#[test]
fn test_remove_by_link_id_missing_returns_none() {
    let mut s = PaperState::new(10_000.0);
    s.enqueue_resting_limit_order(make_order("oc_1", "BTCUSDT", 1_000, 46_000));
    assert!(s
        .remove_resting_limit_order_by_link_id("oc_missing")
        .is_none());
    assert_eq!(s.resting_limit_order_count(), 1);
}

#[test]
fn test_clear_drops_all_queues() {
    let mut s = PaperState::new(10_000.0);
    s.enqueue_resting_limit_order(make_order("oc_1", "BTCUSDT", 1_000, 46_000));
    s.enqueue_resting_limit_order(make_order("oc_2", "ETHUSDT", 2_000, 47_000));
    assert_eq!(s.resting_limit_order_count(), 2);
    s.clear_resting_limit_orders();
    assert_eq!(s.resting_limit_order_count(), 0);
}

/// FUP-1: `clear_resting_limit_orders` must also reset maker_stats so a
/// Degraded verdict or counter residue does not leak across sessions.
/// FUP-1：clear 必須一併重置 maker_stats，避免 Degraded 結論跨 session 污染。
#[test]
fn test_clear_also_resets_maker_stats() {
    let mut s = PaperState::new(10_000.0);
    s.enqueue_resting_limit_order(make_order("oc_1", "BTCUSDT", 1_000, 46_000));
    // Seed terminal stats so Degraded could sticky if not cleared.
    s.test_seed_maker_stats_terminal("BTCUSDT", 0, 25, 10_000);
    s.record_maker_degraded_fallback("BTCUSDT");
    let before = s.maker_stats();
    assert!(before.aggregate.timedout > 0);
    assert!(before.aggregate.degraded_fallbacks > 0);

    s.clear_resting_limit_orders();

    let after = s.maker_stats();
    assert_eq!(after.aggregate.submitted, 0);
    assert_eq!(after.aggregate.filled_full, 0);
    assert_eq!(after.aggregate.filled_partial, 0);
    assert_eq!(after.aggregate.timedout, 0);
    assert_eq!(after.aggregate.degraded_fallbacks, 0);
    assert_eq!(after.aggregate.sum_net_edge_bps, 0.0);
    assert!(after.per_symbol.is_empty());
}

#[test]
fn test_seed_resting_orders_replaces_queue() {
    let mut s = PaperState::new(10_000.0);
    s.enqueue_resting_limit_order(make_order("oc_1", "BTCUSDT", 1_000, 46_000));
    // Seed a different payload; seed must fully replace prior state.
    let mut replacement: HashMap<String, VecDeque<RestingLimitOrder>> = HashMap::new();
    let mut q = VecDeque::new();
    q.push_back(make_order("oc_9", "SOLUSDT", 9_000, 54_000));
    replacement.insert("SOLUSDT".to_string(), q);
    s.seed_resting_limit_orders(replacement);
    assert_eq!(s.resting_limit_order_count(), 1);
    assert_eq!(s.resting_limit_order_count_for("BTCUSDT"), 0);
    assert_eq!(
        s.resting_limit_orders_for("SOLUSDT")[0].order_link_id,
        "oc_9"
    );
}

// ── 1B-4.2: classifier + sweep tests ──
// 1B-4.2：分類器 + sweep 測試

fn order_at(
    link_id: &str,
    symbol: &str,
    is_long: bool,
    limit_price: f64,
    submit_ts: u64,
    deadline_ms: u64,
) -> RestingLimitOrder {
    RestingLimitOrder {
        symbol: symbol.to_string(),
        is_long,
        qty: 0.1,
        limit_price,
        time_in_force: TimeInForce::PostOnly,
        submit_ts_ms: submit_ts,
        deadline_ms,
        mid_price_at_submit: 50_001.0,
        order_link_id: link_id.to_string(),
        context_id: "ctx_test".to_string(),
        strategy: "grid_trading".to_string(),
        funding_rate_at_submit: 0.0,
    }
}

/// 1B-4.3 test helper: build an order with an explicit submit-time funding
/// rate so guard tests can exercise the threshold comparison without
/// touching the other 11 fields. Everything else mirrors `order_at`.
/// 1B-4.3 測試輔助：以顯式 submit-time funding rate 建構訂單，其餘欄位
/// 等同 `order_at`。
fn order_with_funding(
    link_id: &str,
    symbol: &str,
    is_long: bool,
    limit_price: f64,
    submit_ts: u64,
    deadline_ms: u64,
    funding_rate: f64,
) -> RestingLimitOrder {
    let mut o = order_at(
        link_id,
        symbol,
        is_long,
        limit_price,
        submit_ts,
        deadline_ms,
    );
    o.funding_rate_at_submit = funding_rate;
    o
}

#[test]
fn test_classify_timeout_takes_precedence_over_fill() {
    // Deadline expired AND price would cross → still Timeout (conservative).
    // 截止到期且價格會穿越 → 仍 Timeout（保守，對齊 1B-3.2）。
    let o = order_at("oc_t", "BTCUSDT", true, 50_000.0, 1_000, 2_000);
    // 1B-4.3: threshold `0.0` disables funding-drag guard — legacy behaviour.
    let a = classify_resting_order(&o, 49_500.0, 2_500, 0.0);
    assert_eq!(a, RestingSweepAction::Timeout);
}

#[test]
fn test_classify_same_tick_enqueue_stays_kept() {
    // submit_ts_ms == now_ms → Keep (bias guard: resting must wait ≥1 tick).
    // 同 tick 不成交（bias 保護）。
    let o = order_at("oc_same", "BTCUSDT", true, 50_000.0, 1_000, 60_000);
    let a = classify_resting_order(&o, 49_000.0, 1_000, 0.0);
    assert_eq!(a, RestingSweepAction::Keep);
}

#[test]
fn test_classify_buy_tick_below_limit_fills_full() {
    let o = order_at("oc_b_cross", "BTCUSDT", true, 50_000.0, 1_000, 60_000);
    let a = classify_resting_order(&o, 49_999.0, 1_500, 0.0);
    assert_eq!(a, RestingSweepAction::FillFull);
}

#[test]
fn test_classify_buy_tick_equal_limit_fill_partial() {
    let o = order_at("oc_b_touch", "BTCUSDT", true, 50_000.0, 1_000, 60_000);
    let a = classify_resting_order(&o, 50_000.0, 1_500, 0.0);
    assert_eq!(a, RestingSweepAction::FillPartial);
}

#[test]
fn test_classify_buy_tick_above_limit_keeps() {
    let o = order_at("oc_b_keep", "BTCUSDT", true, 50_000.0, 1_000, 60_000);
    let a = classify_resting_order(&o, 50_001.0, 1_500, 0.0);
    assert_eq!(a, RestingSweepAction::Keep);
}

#[test]
fn test_classify_sell_tick_above_limit_fills_full() {
    let o = order_at("oc_s_cross", "BTCUSDT", false, 50_000.0, 1_000, 60_000);
    let a = classify_resting_order(&o, 50_001.0, 1_500, 0.0);
    assert_eq!(a, RestingSweepAction::FillFull);
}

#[test]
fn test_classify_sell_tick_equal_limit_fill_partial() {
    let o = order_at("oc_s_touch", "BTCUSDT", false, 50_000.0, 1_000, 60_000);
    let a = classify_resting_order(&o, 50_000.0, 1_500, 0.0);
    assert_eq!(a, RestingSweepAction::FillPartial);
}

#[test]
fn test_classify_sell_tick_below_limit_keeps() {
    let o = order_at("oc_s_keep", "BTCUSDT", false, 50_000.0, 1_000, 60_000);
    let a = classify_resting_order(&o, 49_999.0, 1_500, 0.0);
    assert_eq!(a, RestingSweepAction::Keep);
}

#[test]
fn test_classify_nonpositive_prices_stay_kept() {
    // tick_price <= 0 → Keep (defensive; sweep caller may pass 0 at boot)
    // 負/零 tick_price 保守 → Keep（防禦性）。
    let o = order_at("oc_bad", "BTCUSDT", true, 50_000.0, 1_000, 60_000);
    assert_eq!(
        classify_resting_order(&o, 0.0, 1_500, 0.0),
        RestingSweepAction::Keep
    );
    assert_eq!(
        classify_resting_order(&o, -1.0, 1_500, 0.0),
        RestingSweepAction::Keep
    );
}

#[test]
fn test_partial_fill_heads_deterministic() {
    // Same id → same outcome every call (reproducibility).
    // 相同 id → 每次調用一致（可重現性）。
    let id = "pop_paper_BTCUSDT_42";
    let a = resting_partial_fill_heads(id);
    let b = resting_partial_fill_heads(id);
    assert_eq!(a, b);
}

#[test]
fn test_sweep_empty_queue_returns_empty_events() {
    let mut s = PaperState::new(10_000.0);
    let events = s.sweep_resting_limit_orders_for_symbol("BTCUSDT", 50_000.0, 2_000, 0.0002, 0.0);
    assert!(events.is_empty());
}

#[test]
fn test_sweep_timeout_drains_without_fill() {
    let mut s = PaperState::new(10_000.0);
    s.set_latest_price("BTCUSDT", 50_000.0);
    s.enqueue_resting_limit_order(order_at("oc_to", "BTCUSDT", true, 49_000.0, 1_000, 2_000));
    let events = s.sweep_resting_limit_orders_for_symbol("BTCUSDT", 48_000.0, 5_000, 0.0002, 0.0);
    assert_eq!(events.len(), 1);
    match &events[0] {
        RestingFillEvent::Timedout { order } => {
            assert_eq!(order.order_link_id, "oc_to");
        }
        _ => panic!("expected Timedout"),
    }
    // No position opened — timeout does not apply_fill.
    assert!(s.get_position("BTCUSDT").is_none());
    assert_eq!(s.resting_limit_order_count_for("BTCUSDT"), 0);
}

#[test]
fn test_sweep_buy_cross_opens_position_at_limit_price() {
    let mut s = PaperState::new(10_000.0);
    s.set_latest_price("BTCUSDT", 50_000.0);
    s.enqueue_resting_limit_order(order_at("oc_b", "BTCUSDT", true, 49_000.0, 1_000, 60_000));
    // Tick drops below limit — buy limit fills at the limit price, not tick.
    // Tick 跌破限價 — buy 限價以限價成交，非 tick 價。
    let events = s.sweep_resting_limit_orders_for_symbol("BTCUSDT", 48_900.0, 2_000, 0.0002, 0.0);
    assert_eq!(events.len(), 1);
    match &events[0] {
        RestingFillEvent::Filled {
            order,
            fill_price,
            fill_qty,
            mid_price_at_fill,
            true_cross,
            fee,
            ..
        } => {
            assert_eq!(order.order_link_id, "oc_b");
            assert_eq!(*fill_price, 49_000.0, "maker fills at limit, not tick");
            assert_eq!(*fill_qty, 0.1);
            assert_eq!(*mid_price_at_fill, 48_900.0);
            assert!(*true_cross, "cross should be true_cross=true");
            // fee = 0.1 * 49_000 * 0.0002 = 0.98
            assert!((fee - 0.98).abs() < 1e-9);
        }
        _ => panic!("expected Filled"),
    }
    let pos = s.get_position("BTCUSDT").expect("position opened");
    assert!(pos.is_long);
    assert_eq!(pos.qty, 0.1);
    assert_eq!(pos.entry_price, 49_000.0);
    // Queue drained.
    assert_eq!(s.resting_limit_order_count_for("BTCUSDT"), 0);
}

#[test]
fn test_sweep_sell_cross_opens_short_at_limit_price() {
    let mut s = PaperState::new(10_000.0);
    s.set_latest_price("ETHUSDT", 3_000.0);
    s.enqueue_resting_limit_order(order_at("oc_s", "ETHUSDT", false, 3_100.0, 1_000, 60_000));
    // Tick rises above limit — sell limit fills at limit price.
    // Tick 升至限價之上 — sell 限價以限價成交。
    let events = s.sweep_resting_limit_orders_for_symbol("ETHUSDT", 3_105.0, 2_000, 0.0002, 0.0);
    assert_eq!(events.len(), 1);
    match &events[0] {
        RestingFillEvent::Filled {
            fill_price,
            true_cross,
            ..
        } => {
            assert_eq!(*fill_price, 3_100.0);
            assert!(*true_cross);
        }
        _ => panic!("expected Filled"),
    }
    let pos = s.get_position("ETHUSDT").expect("short opened");
    assert!(!pos.is_long);
    assert_eq!(pos.entry_price, 3_100.0);
}

#[test]
fn test_sweep_above_limit_buy_keeps_order() {
    let mut s = PaperState::new(10_000.0);
    s.enqueue_resting_limit_order(order_at(
        "oc_keep", "BTCUSDT", true, 49_000.0, 1_000, 60_000,
    ));
    let events = s.sweep_resting_limit_orders_for_symbol("BTCUSDT", 50_000.0, 2_000, 0.0002, 0.0);
    assert!(events.is_empty());
    assert_eq!(s.resting_limit_order_count_for("BTCUSDT"), 1);
    assert!(s.get_position("BTCUSDT").is_none());
}

#[test]
fn test_sweep_same_tick_enqueue_does_not_fill() {
    let mut s = PaperState::new(10_000.0);
    // submit_ts = now_ms — classifier returns Keep even though price crosses.
    // submit_ts 與 now_ms 相等 — 分類器回 Keep 即使價格穿越。
    s.enqueue_resting_limit_order(order_at("oc_st", "BTCUSDT", true, 49_000.0, 2_000, 60_000));
    let events = s.sweep_resting_limit_orders_for_symbol("BTCUSDT", 48_500.0, 2_000, 0.0002, 0.0);
    assert!(events.is_empty());
    assert_eq!(s.resting_limit_order_count_for("BTCUSDT"), 1);
}

#[test]
fn test_sweep_preserves_fifo_for_kept_orders() {
    let mut s = PaperState::new(10_000.0);
    // Three orders — middle one will fill, other two keep.
    // 三筆掛單 — 中間成交、另兩筆保留。
    s.enqueue_resting_limit_order(order_at("oc_1", "BTCUSDT", true, 48_000.0, 1_000, 60_000));
    s.enqueue_resting_limit_order(order_at("oc_2", "BTCUSDT", true, 49_500.0, 1_000, 60_000));
    s.enqueue_resting_limit_order(order_at("oc_3", "BTCUSDT", true, 47_000.0, 1_000, 60_000));
    // Tick = 49_000 — only oc_2 (limit 49_500) fills; oc_1/oc_3 keep.
    let events = s.sweep_resting_limit_orders_for_symbol("BTCUSDT", 49_000.0, 2_000, 0.0002, 0.0);
    assert_eq!(events.len(), 1);
    match &events[0] {
        RestingFillEvent::Filled { order, .. } => {
            assert_eq!(order.order_link_id, "oc_2");
        }
        _ => panic!("expected Filled"),
    }
    let remaining = s.resting_limit_orders_for("BTCUSDT");
    assert_eq!(remaining.len(), 2);
    assert_eq!(remaining[0].order_link_id, "oc_1", "FIFO head preserved");
    assert_eq!(remaining[1].order_link_id, "oc_3", "FIFO tail preserved");
}

#[test]
fn test_sweep_partial_fill_deterministic_by_link_id() {
    // Two touch orders with different ids — one heads, one tails. Exactly
    // one should fill; the other stays in queue. Guarantees deterministic
    // replay even though classifier returned FillPartial for both.
    // 兩筆碰觸掛單不同 id — 一 heads 一 tails，確定性一致。
    let mut s = PaperState::new(10_000.0);
    // "oc_even" (4 bytes summing to 111+99+95+101+118+101+110 = ...) — compute
    // which id goes heads by calling the helper and picking ids accordingly.
    let id_a = "oc_heads_a";
    let id_b = "oc_heads_b";
    let a_heads = resting_partial_fill_heads(id_a);
    let b_heads = resting_partial_fill_heads(id_b);
    s.enqueue_resting_limit_order(order_at(id_a, "SOLUSDT", true, 100.0, 1_000, 60_000));
    s.enqueue_resting_limit_order(order_at(id_b, "SOLUSDT", true, 100.0, 1_000, 60_000));
    let events = s.sweep_resting_limit_orders_for_symbol("SOLUSDT", 100.0, 2_000, 0.0002, 0.0);
    // count expected fills by precomputed coin flips.
    let expected_fills = (a_heads as usize) + (b_heads as usize);
    let actual_fills = events
        .iter()
        .filter(|e| matches!(e, RestingFillEvent::Filled { .. }))
        .count();
    assert_eq!(actual_fills, expected_fills);
    // For every Filled event, `true_cross` must be false because tick == limit.
    for e in &events {
        if let RestingFillEvent::Filled { true_cross, .. } = e {
            assert!(!*true_cross, "touch fills are not true cross");
        }
    }
    // Queue + positions accounting must match.
    let remaining = s.resting_limit_order_count_for("SOLUSDT");
    assert_eq!(remaining, 2 - expected_fills);
}

#[test]
fn test_resting_order_fields_serde_roundtrip() {
    // Serialisation stability: future snapshot wiring (1B-4.2 or beyond)
    // needs this shape to round-trip cleanly.
    // 序列化穩定性：未來快照接線需此形狀乾淨 round-trip。
    let o = make_order("oc_rt", "BTCUSDT", 1_000, 46_000);
    let json = serde_json::to_string(&o).expect("serialise");
    let back: RestingLimitOrder = serde_json::from_str(&json).expect("deserialise");
    assert_eq!(back.order_link_id, o.order_link_id);
    assert_eq!(back.symbol, o.symbol);
    assert_eq!(back.qty, o.qty);
    assert_eq!(back.limit_price, o.limit_price);
    assert_eq!(back.deadline_ms, o.deadline_ms);
    assert_eq!(back.mid_price_at_submit, o.mid_price_at_submit);
    assert_eq!(back.context_id, o.context_id);
    assert_eq!(back.strategy, o.strategy);
    assert_eq!(back.time_in_force, TimeInForce::PostOnly);
    assert_eq!(back.funding_rate_at_submit, o.funding_rate_at_submit);
}

// ── 1B-4.3: funding drag bias guard #3 tests ──
// 1B-4.3：funding drag bias guard #3 測試

#[test]
fn test_funding_drag_adverse_zero_threshold_disables_guard() {
    // threshold = 0.0 must return false regardless of funding magnitude.
    // 0.0 門檻必須一律回 false（guard 關閉）。
    assert!(!funding_drag_adverse(0.10, true, 0.0));
    assert!(!funding_drag_adverse(-0.10, false, 0.0));
}

#[test]
fn test_funding_drag_adverse_negative_threshold_disables_guard() {
    // Defensive: operator accidentally sets negative threshold → disabled.
    // 防禦性：operator 誤設負門檻 → 關閉 guard。
    assert!(!funding_drag_adverse(0.10, true, -0.001));
}

#[test]
fn test_funding_drag_adverse_non_finite_inputs_return_false() {
    // NaN / inf on either arg → guard fails open (don't defer fills on
    // corrupt data — exchange-side maker queue isn't paused either).
    // 非有限輸入 → guard 失效開（腐敗資料下不改變行為）。
    assert!(!funding_drag_adverse(f64::NAN, true, 0.0005));
    assert!(!funding_drag_adverse(f64::INFINITY, true, 0.0005));
    assert!(!funding_drag_adverse(0.001, true, f64::NAN));
    assert!(!funding_drag_adverse(0.001, true, f64::INFINITY));
}

#[test]
fn test_funding_drag_adverse_long_positive_funding_is_adverse() {
    // Positive funding paid by longs → long maker is adverse.
    // 正 funding 由多方支付 → 多 maker 逆向。
    assert!(funding_drag_adverse(0.0010, true, 0.0005));
}

#[test]
fn test_funding_drag_adverse_long_negative_funding_is_favorable() {
    // Negative funding received by longs → long maker favorable.
    // 負 funding 由空方支付 → 多 maker 有利。
    assert!(!funding_drag_adverse(-0.0010, true, 0.0005));
}

#[test]
fn test_funding_drag_adverse_short_negative_funding_is_adverse() {
    // Short pays when funding is negative → short maker adverse.
    // funding < −threshold → 空 maker 逆向。
    assert!(funding_drag_adverse(-0.0010, false, 0.0005));
}

#[test]
fn test_funding_drag_adverse_short_positive_funding_is_favorable() {
    assert!(!funding_drag_adverse(0.0010, false, 0.0005));
}

#[test]
fn test_funding_drag_adverse_boundary_is_strict() {
    // |funding| == threshold must NOT be adverse (strict `>`).
    // An operator setting threshold = 0.0003 can expect 3 bps to still fill.
    // 邊界 (==) 非逆向（嚴格 >），operator 設 0.0003 可期待 3 bps 仍能成交。
    assert!(!funding_drag_adverse(0.0003, true, 0.0003));
    assert!(!funding_drag_adverse(-0.0003, false, 0.0003));
    // One ulp above → adverse.
    assert!(funding_drag_adverse(0.0003 + f64::EPSILON, true, 0.0003));
}

#[test]
fn test_classify_long_adverse_funding_downgrades_partial_to_keep() {
    // FillPartial + long + adverse funding → Keep.
    // Pre-guard raw classifier confirms this would have been FillPartial.
    let o = order_with_funding(
        "oc_fd_long",
        "BTCUSDT",
        /*is_long*/ true,
        50_000.0,
        1_000,
        60_000,
        0.0010,
    );
    assert_eq!(
        classify_resting_order_raw(&o, 50_000.0, 1_500),
        RestingSweepAction::FillPartial
    );
    assert_eq!(
        classify_resting_order(&o, 50_000.0, 1_500, 0.0005),
        RestingSweepAction::Keep
    );
}

#[test]
fn test_classify_short_adverse_funding_downgrades_partial_to_keep() {
    let o = order_with_funding(
        "oc_fd_short",
        "BTCUSDT",
        /*is_long*/ false,
        50_000.0,
        1_000,
        60_000,
        -0.0010,
    );
    assert_eq!(
        classify_resting_order(&o, 50_000.0, 1_500, 0.0005),
        RestingSweepAction::Keep
    );
}

#[test]
fn test_classify_favorable_funding_leaves_partial_unchanged() {
    // Long + negative (favorable) funding → FillPartial stays FillPartial.
    // 多方 + 負（有利）funding → FillPartial 不變。
    let o = order_with_funding(
        "oc_fd_fav",
        "BTCUSDT",
        true,
        50_000.0,
        1_000,
        60_000,
        -0.0010,
    );
    assert_eq!(
        classify_resting_order(&o, 50_000.0, 1_500, 0.0005),
        RestingSweepAction::FillPartial
    );
}

#[test]
fn test_classify_fill_full_not_downgraded_by_adverse_funding() {
    // True cross + adverse funding → still FillFull (the limit was actually
    // crossed; no adverse-selection statistical artefact to protect against).
    // 真實穿越 + 逆向 funding → 仍 FillFull（非統計偏誤，無需保護）。
    let o = order_with_funding(
        "oc_fd_cross",
        "BTCUSDT",
        true,
        50_000.0,
        1_000,
        60_000,
        0.0020,
    );
    assert_eq!(
        classify_resting_order(&o, 49_500.0, 1_500, 0.0005),
        RestingSweepAction::FillFull
    );
}

#[test]
fn test_classify_timeout_precedence_preserved_under_adverse_funding() {
    // Deadline-expired orders must still Timeout even when adverse funding
    // would otherwise trigger the guard. Rule 1 > rule 5.
    // 截止到期 + 逆向 funding → 仍 Timeout（規則 1 勝過規則 5）。
    let o = order_with_funding("oc_fd_to", "BTCUSDT", true, 50_000.0, 1_000, 2_000, 0.0020);
    assert_eq!(
        classify_resting_order(&o, 50_000.0, 3_000, 0.0005),
        RestingSweepAction::Timeout
    );
}

#[test]
fn test_sweep_adverse_funding_keeps_order_and_bumps_skip_counter() {
    // Touch-equal FillPartial on adverse long funding → order stays in
    // queue AND maker_stats.funding_drag_skips increments.
    // 逆向 funding 下的碰觸 → 訂單留隊 + funding_drag_skips += 1。
    let mut s = PaperState::new(10_000.0);
    s.set_latest_price("BTCUSDT", 50_000.0);
    s.enqueue_resting_limit_order(order_with_funding(
        "oc_fd_sweep",
        "BTCUSDT",
        true,
        50_000.0,
        1_000,
        60_000,
        0.0010,
    ));
    let events = s.sweep_resting_limit_orders_for_symbol(
        "BTCUSDT", 50_000.0, 2_000, 0.0002, /*threshold*/ 0.0005,
    );
    // No fills (guard deferred the touch), no events emitted (Keep paths
    // stay silent — events are only for drained orders).
    assert!(events.is_empty(), "guard skip must not emit events");
    // Order still in queue.
    assert_eq!(s.resting_limit_order_count_for("BTCUSDT"), 1);
    // Counter bumped on both scopes.
    let stats = s.maker_stats();
    assert_eq!(stats.aggregate.funding_drag_skips, 1);
    assert_eq!(
        stats.per_symbol.get("BTCUSDT").unwrap().funding_drag_skips,
        1
    );
    // Terminal counters untouched — this is observability only.
    assert_eq!(stats.aggregate.filled_full, 0);
    assert_eq!(stats.aggregate.filled_partial, 0);
    assert_eq!(stats.aggregate.timedout, 0);
}

#[test]
fn test_sweep_favorable_funding_retains_legacy_coin_flip_behaviour() {
    // Favorable funding + touch → coin flip proceeds; guard is a no-op.
    // 有利 funding + 碰觸 → 原本 heads/tails 行為不變；guard 不介入。
    let mut s = PaperState::new(10_000.0);
    // Use favorable funding (long + negative = long receives).
    let link_id = "oc_fd_fav_sweep"; // deterministic coin: check heads below
    s.enqueue_resting_limit_order(order_with_funding(
        link_id, "BTCUSDT", true, 50_000.0, 1_000, 60_000, -0.0010,
    ));
    let events =
        s.sweep_resting_limit_orders_for_symbol("BTCUSDT", 50_000.0, 2_000, 0.0002, 0.0005);
    // Counter stays at zero — guard never fired.
    assert_eq!(s.maker_stats().aggregate.funding_drag_skips, 0);
    // Outcome matches the deterministic coin: heads → Filled, tails → Keep.
    let heads = resting_partial_fill_heads(link_id);
    if heads {
        assert_eq!(events.len(), 1, "heads must fill");
        assert_eq!(s.resting_limit_order_count_for("BTCUSDT"), 0);
    } else {
        assert!(events.is_empty(), "tails must keep");
        assert_eq!(s.resting_limit_order_count_for("BTCUSDT"), 1);
    }
}

#[test]
fn test_sweep_true_cross_ignores_adverse_funding() {
    // True cross + adverse funding → still fills. Guard only shapes the
    // coin-flip branch.
    // 真實穿越 + 逆向 funding → 照常成交；guard 僅作用於碰觸分支。
    let mut s = PaperState::new(10_000.0);
    s.enqueue_resting_limit_order(order_with_funding(
        "oc_fd_cross_sweep",
        "BTCUSDT",
        true,
        50_000.0,
        1_000,
        60_000,
        0.0020,
    ));
    let events =
        s.sweep_resting_limit_orders_for_symbol("BTCUSDT", 49_500.0, 2_000, 0.0002, 0.0005);
    assert_eq!(events.len(), 1);
    match &events[0] {
        RestingFillEvent::Filled { true_cross, .. } => assert!(*true_cross),
        _ => panic!("expected Filled(true_cross=true)"),
    }
    // Counter unchanged — only FillPartial downgrades are counted.
    assert_eq!(s.maker_stats().aggregate.funding_drag_skips, 0);
}

#[test]
fn test_sweep_guard_zero_threshold_is_passthrough() {
    // threshold = 0.0 → guard disabled → behaviour identical to 1B-4.2
    // coin flip regardless of funding_rate_at_submit.
    // threshold = 0.0 → guard 關閉 → 行為同 1B-4.2。
    let mut s = PaperState::new(10_000.0);
    s.enqueue_resting_limit_order(order_with_funding(
        "oc_fd_off",
        "BTCUSDT",
        true,
        50_000.0,
        1_000,
        60_000,
        0.9999,
    ));
    let _ = s.sweep_resting_limit_orders_for_symbol("BTCUSDT", 50_000.0, 2_000, 0.0002, 0.0);
    assert_eq!(
        s.maker_stats().aggregate.funding_drag_skips,
        0,
        "zero threshold must not count skips"
    );
}

#[test]
fn test_router_stamps_funding_rate_from_paper_state_accessor() {
    // Direct accessor test — router uses `latest_funding_rate`. Zero when
    // no ticker seen; reflects the last `set_latest_funding_rate` after.
    // 直接測 accessor — router 於 ticker 未見時讀 0，見過後讀最後值。
    let mut s = PaperState::new(10_000.0);
    assert_eq!(s.latest_funding_rate("BTCUSDT"), None);
    s.set_latest_funding_rate("BTCUSDT", 0.0007);
    assert_eq!(s.latest_funding_rate("BTCUSDT"), Some(0.0007));
    // Overwrite semantics — latest wins.
    s.set_latest_funding_rate("BTCUSDT", -0.0003);
    assert_eq!(s.latest_funding_rate("BTCUSDT"), Some(-0.0003));
}
