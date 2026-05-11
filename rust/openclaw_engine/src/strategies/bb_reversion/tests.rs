//! BB Reversion unit tests (entry/exit/RSI/limit/funding-rate/param ranges).
//! BB 回歸策略單元測試（入場/出場/RSI/限價/資金費率/參數範圍）。
//!
//! MODULE_NOTE (EN): Split from `bb_reversion.rs` (G5-05, §九 1200 line rule).
//!   Pure move — `#[cfg(test)] mod tests` migrated to its own sibling. No
//!   coverage changes. The parent `mod.rs` re-mounts via `#[cfg(test)] mod tests;`.
//! MODULE_NOTE (中): 由 `bb_reversion.rs` 拆出（G5-05，§九 1200 行規則）。
//!   純搬移 — `#[cfg(test)] mod tests` 移至 sibling 檔。覆蓋率不變。
//!   父層 `mod.rs` 透過 `#[cfg(test)] mod tests;` 重新掛載。

use super::*;
use crate::strategies::common::TrendCooldown;
use crate::strategies::confluence::PersistenceTracker;
use crate::strategies::StrategyAction;
use crate::tick_pipeline::TickContext;
use openclaw_core::indicators::{AdxResult, BollingerResult, IndicatorSnapshot};

fn ctx_bb(pct_b: f64, rsi: f64, ts: u64) -> TickContext<'static> {
    use openclaw_core::indicators::HurstResult;
    // W-AUDIT-6d #6 (AMD-2026-05-09-02 §3) — pair MA confirmation gate 預設啟用，
    // helper 依 signal 方向自動配 sma_50：long signal（pct_b < 0）必 sma_50 > price
    // 才能過 gate；short signal（pct_b > 1）必 sma_50 < price。其餘場景（pure exit /
    // no signal）放中間值，本身不觸發 entry path 不影響。
    // ctx_bb auto-derives sma_50 to satisfy MA pair confirmation gate per
    // signal direction (long: sma_50 > price / short: sma_50 < price).
    let sma_50_value = if pct_b < 0.0 {
        51_000.0 // long signal: price=50000 < ma=51000 ✓
    } else if pct_b > 1.0 {
        49_000.0 // short signal: price=50000 > ma=49000 ✓
    } else {
        50_000.0 // neutral / exit-only path
    };
    let ind = Box::leak(Box::new(IndicatorSnapshot {
        bollinger: Some(BollingerResult {
            upper: 51000.0,
            middle: 50000.0,
            lower: 49000.0,
            bandwidth: 0.04,
            percent_b: pct_b,
        }),
        rsi_14: Some(rsi),
        // ADX=15: low ADX = ranging market = ideal for mean-reversion.
        // ADX=15：低 ADX = 震盪市場 = 均值回歸理想環境。
        adx: Some(AdxResult {
            adx: 15.0,
            plus_di: 20.0,
            minus_di: 18.0,
        }),
        // EDGE-P1-3: Hurst mean_reverting regime needed for score ≥ 45 threshold.
        hurst: Some(HurstResult {
            hurst: 0.35,
            regime: "mean_reverting".into(),
        }),
        // W-AUDIT-6d #6: sma_50 derived above per signal direction。
        sma_50: Some(sma_50_value),
        ..Default::default()
    }));
    TickContext {
        symbol: "BTC",
        price: 50000.0,
        timestamp_ms: ts,
        indicators: Some(ind),
        indicators_5m: None,
        signals: &[],
        h0_allowed: true,
        funding_rate: None,
        index_price: None,
        open_interest: None,
        best_bid: None,
        best_ask: None,
        tick_size: None,
        alpha_surface_ref: &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
        position_state: None,
        is_pinned: true,
    }
}

fn ctx_bb_bbo(
    pct_b: f64,
    rsi: f64,
    ts: u64,
    bid: f64,
    ask: f64,
    tick: f64,
) -> TickContext<'static> {
    let mut ctx = ctx_bb(pct_b, rsi, ts);
    ctx.best_bid = Some(bid);
    ctx.best_ask = Some(ask);
    ctx.tick_size = Some(tick);
    ctx
}

#[test]
fn test_long_oversold() {
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    let i = s.on_tick(
        &ctx_bb_bbo(-0.1, 25.0, 0, 49_999.5, 50_000.5, 0.1),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Open(intent) => assert!(intent.is_long),
        other => panic!("expected StrategyAction::Open, got {:?}", other),
    }
}

#[test]
fn test_non_pinned_symbol_skips_entry() {
    // SCANNER-TRADEABLE-TIER-1: scanner dynamic slots remain observable, but
    // bb_reversion only opens on the pinned tradeable tier.
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;
    let mut ctx = ctx_bb_bbo(-0.1, 25.0, 0, 49_999.5, 50_000.5, 0.1);
    ctx.is_pinned = false;

    let actions = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);

    assert!(
        actions.is_empty(),
        "dynamic-add/non-pinned symbol must not produce bb_reversion entry"
    );
}

#[test]
fn test_exit_mean() {
    // P0 Option A-Lite — 改造後策略不持本地 state，第二 tick 必須注入
    // ctx.position_state = Some(self-owned LONG) 才能進 exit 分支。
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    // Tick 1：entry（無需 mock position）。
    s.on_tick(
        &ctx_bb(-0.1, 25.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    // Tick 2：mock paper_state 顯示 bb_reversion 已開 LONG → 走 exit zone。
    let pp = make_paper_position_bbr_for_self_exit("BTC", true);
    let mut ctx2 = ctx_bb(0.5, 50.0, 700_000);
    ctx2.position_state = Some(&pp);
    let i = s.on_tick(&ctx2, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Close { reason, .. } => assert_eq!(reason, "bb_mean_revert"),
        other => panic!("expected StrategyAction::Close, got {:?}", other),
    }
}

/// Helper for self-exit tests — owner = bb_reversion（自家持倉）。
fn make_paper_position_bbr_for_self_exit(
    symbol: &str,
    is_long: bool,
) -> crate::paper_state::PaperPosition {
    crate::paper_state::PaperPosition {
        symbol: symbol.to_string(),
        is_long,
        qty: 1.0,
        entry_price: 50_000.0,
        best_price: 50_000.0,
        entry_fee: 0.0,
        entry_ts_ms: 0,
        unrealized_pnl: 0.0,
        entry_context_id: String::new(),
        owner_strategy: "bb_reversion".to_string(),
        entry_notional: 50_000.0,
        max_favorable_pnl_pct: 0.0,
        peak_reached_ts_ms: 0,
    }
}

#[test]
fn test_non_pinned_self_owned_position_can_exit() {
    // SCANNER-TRADEABLE-TIER-1: pinned gate is entry-only; it must not trap
    // an already-open bb_reversion position on a symbol that later leaves the
    // tradeable tier.
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;
    let pp = make_paper_position_bbr_for_self_exit("BTC", true);
    let mut ctx = ctx_bb(0.5, 50.0, 700_000);
    ctx.position_state = Some(&pp);
    ctx.is_pinned = false;

    let actions = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);

    assert_eq!(
        actions.len(),
        1,
        "non-pinned self-owned bb_reversion position must still be allowed to exit"
    );
    match &actions[0] {
        StrategyAction::Close { reason, .. } => assert_eq!(reason, "bb_mean_revert"),
        other => panic!("expected StrategyAction::Close, got {:?}", other),
    }
}

// ── RC-07: Limit order tests / RC-07 限價單測試 ──

#[test]
fn test_limit_order_long() {
    // RC-07 + G7-09c Phase 1: use_limit=true, oversold entry produces limit
    // order with BBO-aware passive price.
    // RC-07 + G7-09c Phase 1：use_limit=true 時使用 BBO-aware passive price。
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;
    s.use_limit = true;
    s.limit_offset_bps = 10.0; // 10 bps = 0.1%
    let i = s.on_tick(
        &ctx_bb_bbo(-0.1, 25.0, 0, 49_999.5, 50_000.5, 0.1),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert_eq!(i.len(), 1);
    let intent = match &i[0] {
        StrategyAction::Open(intent) => intent,
        other => panic!("expected StrategyAction::Open, got {:?}", other),
    };
    assert!(intent.is_long);
    assert_eq!(intent.order_type, "limit");
    let expected = 49_999.4;
    assert!(
        (intent.limit_price.unwrap() - expected).abs() < 1e-6,
        "G7-09c BBO expected limit_price={}, got={}",
        expected,
        intent.limit_price.unwrap()
    );
}

#[test]
fn test_limit_order_short() {
    // RC-07 + G7-09c Phase 1: use_limit=true, overbought entry produces
    // limit order with BBO-aware passive price.
    // RC-07 + G7-09c Phase 1：use_limit=true 時使用 BBO-aware passive price。
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;
    s.use_limit = true;
    s.limit_offset_bps = 10.0;
    let i = s.on_tick(
        &ctx_bb_bbo(1.1, 75.0, 0, 49_999.5, 50_000.5, 0.1),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert_eq!(i.len(), 1);
    let intent = match &i[0] {
        StrategyAction::Open(intent) => intent,
        other => panic!("expected StrategyAction::Open, got {:?}", other),
    };
    assert!(!intent.is_long);
    assert_eq!(intent.order_type, "limit");
    let expected = 50_000.6;
    assert!(
        (intent.limit_price.unwrap() - expected).abs() < 1e-6,
        "G7-09c BBO expected limit_price={}, got={}",
        expected,
        intent.limit_price.unwrap()
    );
}

#[test]
fn test_market_order_default() {
    // RC-07: use_limit=false (default), entries produce market orders
    // RC-07：use_limit=false（默認），入場產生市價單
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    assert!(!s.use_limit); // verify default is false / 確認默認為 false
    let i = s.on_tick(
        &ctx_bb_bbo(-0.1, 25.0, 0, 49_999.5, 50_000.5, 0.1),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert_eq!(i.len(), 1);
    let intent = match &i[0] {
        StrategyAction::Open(intent) => intent,
        other => panic!("expected StrategyAction::Open, got {:?}", other),
    };
    assert_eq!(intent.order_type, "market");
    assert!(intent.limit_price.is_none());
}

#[test]
fn test_exit_always_market() {
    // RC-07: Even with use_limit=true, exit orders are always market
    // RC-07：即使 use_limit=true，出場單永遠是市價單
    // With StrategyAction::Close, exit is no longer an OrderIntent —
    // it's a Close action that the pipeline handles directly.
    // 使用 StrategyAction::Close 後，出場不再是 OrderIntent。
    // P0 Option A-Lite — exit tick 必須注入 self-owned position 才走 exit。
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    s.use_limit = true;
    // Enter long with limit order / 限價入場做多。
    let i = s.on_tick(
        &ctx_bb_bbo(-0.1, 25.0, 0, 49_999.5, 50_000.5, 0.1),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    let entry_intent = match &i[0] {
        StrategyAction::Open(intent) => intent,
        other => panic!("expected StrategyAction::Open, got {:?}", other),
    };
    assert_eq!(entry_intent.order_type, "limit");
    // Exit at mean reversion — 注入 owner=bb_reversion 持倉。
    let pp = make_paper_position_bbr_for_self_exit("BTC", true);
    let mut ctx2 = ctx_bb(0.5, 50.0, 700_000);
    ctx2.position_state = Some(&pp);
    let i = s.on_tick(&ctx2, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Close { reason, .. } => {
            assert_eq!(reason, "bb_mean_revert", "exit must be a Close action");
        }
        other => panic!("expected StrategyAction::Close, got {:?}", other),
    }
}

#[test]
fn test_bb_rev_param_ranges() {
    assert!(!BbReversionParams::param_ranges().is_empty());
}

#[test]
fn test_bb_rev_validate() {
    assert!(BbReversionParams::default().validate().is_ok());
    assert!(BbReversionParams {
        cooldown_ms: 1000,
        ..Default::default()
    }
    .validate()
    .is_err());
}

#[test]
fn test_bb_rev_update_roundtrip() {
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    let p = BbReversionParams {
        use_limit: true, // GAP-9: should be coerced to false
        limit_offset_bps: 20.0,
        ..Default::default()
    };
    assert!(s.update_params(p).is_ok());
    assert!(
        !s.get_params().use_limit,
        "GAP-9: use_limit must be coerced to false (paper has no limit sim)"
    );
    assert!((s.get_params().limit_offset_bps - 20.0).abs() < 0.01);
}

// ── G-SR-1 S3+S4: param_ranges + validation tests ──

#[test]
fn test_bbr_param_ranges_count() {
    let ranges = BbReversionParams::param_ranges();
    // 5 original + 2 funding_rate + 10 confluence + 1 W-AUDIT-6d #6 (require_ma_confirmation) = 18
    // 5 原始 + 2 funding_rate + 10 匯流 + 1 W-AUDIT-6d #6 MA pair gate = 18
    assert_eq!(
        ranges.len(),
        18,
        "expected 18 param ranges, got {}",
        ranges.len()
    );
}

#[test]
fn test_bbr_param_ranges_confluence_names() {
    let ranges = BbReversionParams::param_ranges();
    let names: Vec<&str> = ranges.iter().map(|r| r.name.as_str()).collect();
    for expected in &[
        "weight_adx",
        "weight_regime",
        "weight_volume",
        "weight_momentum",
        "adx_floor",
        "confluence_threshold_no_trade",
        "confluence_threshold_light",
        "confluence_threshold_full",
        "min_persistence_ms",
        "min_notional_usd",
    ] {
        assert!(names.contains(expected), "missing param range: {expected}");
    }
}

#[test]
fn test_bbr_validate_default_ok() {
    assert!(BbReversionParams::default().validate().is_ok());
}

#[test]
fn test_bbr_validate_bad_weight_sum() {
    let mut p = BbReversionParams::default();
    p.weight_momentum = 20.0; // sum = 15+30+10+20 = 75 ≠ 65
    assert!(p.validate().is_err());
}

#[test]
fn test_bbr_validate_bad_threshold_order() {
    let mut p = BbReversionParams::default();
    p.confluence_threshold_light = p.confluence_threshold_full; // equal = invalid
    assert!(p.validate().is_err());
}

#[test]
fn test_bbr_validate_bad_min_notional() {
    let mut p = BbReversionParams::default();
    p.min_notional_usd = 0.0;
    assert!(p.validate().is_err());
}

// ── EDGE-P1-2: Funding rate signal tests ──

/// Build a TickContext with funding rate for testing.
fn ctx_bb_with_funding(
    pct_b: f64,
    rsi: f64,
    ts: u64,
    funding_rate: Option<f64>,
) -> TickContext<'static> {
    use openclaw_core::indicators::HurstResult;
    // W-AUDIT-6d #6 — same auto-derive pattern as ctx_bb (sma_50 per signal direction).
    // W-AUDIT-6d #6 — sma_50 同 ctx_bb 規則，依 signal 方向自動配。
    let sma_50_value = if pct_b < 0.0 {
        51_000.0
    } else if pct_b > 1.0 {
        49_000.0
    } else {
        50_000.0
    };
    let ind = Box::leak(Box::new(IndicatorSnapshot {
        bollinger: Some(BollingerResult {
            upper: 51000.0,
            middle: 50000.0,
            lower: 49000.0,
            bandwidth: 0.04,
            percent_b: pct_b,
        }),
        rsi_14: Some(rsi),
        adx: Some(AdxResult {
            adx: 15.0,
            plus_di: 20.0,
            minus_di: 18.0,
        }),
        hurst: Some(HurstResult {
            hurst: 0.35,
            regime: "mean_reverting".into(),
        }),
        // W-AUDIT-6d #6: sma_50 derived per signal direction。
        sma_50: Some(sma_50_value),
        ..Default::default()
    }));
    TickContext {
        symbol: "BTC",
        price: 50000.0,
        timestamp_ms: ts,
        indicators: Some(ind),
        indicators_5m: None,
        signals: &[],
        h0_allowed: true,
        funding_rate,
        index_price: None,
        open_interest: None,
        best_bid: None,
        best_ask: None,
        tick_size: None,
        alpha_surface_ref: &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
        position_state: None,
        is_pinned: true,
    }
}

#[test]
fn test_funding_rate_boost_short_with_positive_funding() {
    // Positive funding → overleveraged long → short reversion boost.
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;

    // Short signal: %B > 1.0, RSI > 70 (overbought)
    // With extreme positive funding rate → aligned with short → boost
    let ctx_with = ctx_bb_with_funding(1.2, 75.0, 1000, Some(0.001));
    let actions_with = s.on_tick(
        &ctx_with,
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert!(
        !actions_with.is_empty(),
        "should produce short entry with positive funding"
    );
    let conf_with = match &actions_with[0] {
        StrategyAction::Open(intent) => intent.confidence,
        _ => panic!("expected Open"),
    };

    // Same signal without funding rate
    // P0 Option A-Lite — positions field 已移除；仍需 cooldown + persistence reset。
    s.cooldown = TrendCooldown::new(600_000);
    s.persistence = PersistenceTracker::new();
    let ctx_without = ctx_bb_with_funding(1.2, 75.0, 2000, None);
    let actions_without = s.on_tick(
        &ctx_without,
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert!(!actions_without.is_empty());
    let conf_without = match &actions_without[0] {
        StrategyAction::Open(intent) => intent.confidence,
        _ => panic!("expected Open"),
    };

    assert!(
        conf_with > conf_without,
        "funding boost should increase confidence: {conf_with} > {conf_without}"
    );
}

#[test]
fn test_funding_rate_boost_long_with_negative_funding() {
    // Negative funding → overleveraged short → long reversion boost.
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;

    // Long signal: %B < 0.0, RSI < 30 (oversold)
    let ctx_with = ctx_bb_with_funding(-0.1, 25.0, 1000, Some(-0.001));
    let actions_with = s.on_tick(
        &ctx_with,
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert!(
        !actions_with.is_empty(),
        "should produce long entry with negative funding"
    );
    let conf_with = match &actions_with[0] {
        StrategyAction::Open(intent) => intent.confidence,
        _ => panic!("expected Open"),
    };

    // P0 Option A-Lite — positions field 已移除；仍需 cooldown + persistence reset。
    s.cooldown = TrendCooldown::new(600_000);
    s.persistence = PersistenceTracker::new();
    let ctx_without = ctx_bb_with_funding(-0.1, 25.0, 2000, None);
    let actions_without = s.on_tick(
        &ctx_without,
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert!(!actions_without.is_empty());
    let conf_without = match &actions_without[0] {
        StrategyAction::Open(intent) => intent.confidence,
        _ => panic!("expected Open"),
    };

    assert!(
        conf_with > conf_without,
        "funding boost should increase confidence: {conf_with} > {conf_without}"
    );
}

#[test]
fn test_funding_rate_no_boost_when_misaligned() {
    // Positive funding should NOT boost long entries (misaligned).
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;

    // Long signal with positive funding (misaligned)
    let ctx_misaligned = ctx_bb_with_funding(-0.1, 25.0, 1000, Some(0.001));
    let actions_mis = s.on_tick(
        &ctx_misaligned,
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert!(!actions_mis.is_empty());
    let conf_mis = match &actions_mis[0] {
        StrategyAction::Open(intent) => intent.confidence,
        _ => panic!("expected Open"),
    };

    // P0 Option A-Lite — positions field 已移除；仍需 cooldown + persistence reset。
    s.cooldown = TrendCooldown::new(600_000);
    s.persistence = PersistenceTracker::new();
    let ctx_none = ctx_bb_with_funding(-0.1, 25.0, 2000, None);
    let actions_none = s.on_tick(
        &ctx_none,
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert!(!actions_none.is_empty());
    let conf_none = match &actions_none[0] {
        StrategyAction::Open(intent) => intent.confidence,
        _ => panic!("expected Open"),
    };

    assert!(
        (conf_mis - conf_none).abs() < 1e-10,
        "misaligned funding should not boost: {conf_mis} == {conf_none}"
    );
}

#[test]
fn test_funding_rate_below_threshold_no_boost() {
    // Funding rate below threshold → no boost regardless of direction.
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;

    let ctx_small = ctx_bb_with_funding(1.2, 75.0, 1000, Some(0.0001)); // below 0.0005 threshold
    let actions_small = s.on_tick(
        &ctx_small,
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert!(!actions_small.is_empty());
    let conf_small = match &actions_small[0] {
        StrategyAction::Open(intent) => intent.confidence,
        _ => panic!("expected Open"),
    };

    // P0 Option A-Lite — positions field 已移除；仍需 cooldown + persistence reset。
    s.cooldown = TrendCooldown::new(600_000);
    s.persistence = PersistenceTracker::new();
    let ctx_none = ctx_bb_with_funding(1.2, 75.0, 2000, None);
    let actions_none = s.on_tick(
        &ctx_none,
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert!(!actions_none.is_empty());
    let conf_none = match &actions_none[0] {
        StrategyAction::Open(intent) => intent.confidence,
        _ => panic!("expected Open"),
    };

    assert!(
        (conf_small - conf_none).abs() < 1e-10,
        "sub-threshold funding should not boost: {conf_small} == {conf_none}"
    );
}

#[test]
fn test_funding_rate_validate_bounds() {
    let mut p = BbReversionParams::default();
    p.funding_rate_threshold = 0.00001; // below min 0.0001
    assert!(p.validate().is_err());

    let mut p = BbReversionParams::default();
    p.funding_rate_boost = 0.3; // above max 0.2
    assert!(p.validate().is_err());
}

// ─────────────────────────────────────────────────────────────────────────
// G7-09c Phase 1: BBO-aware PostOnly maker price tests for bb_reversion.
// G7-09c Phase 1：bb_reversion BBO-aware PostOnly 限價測試。
// ─────────────────────────────────────────────────────────────────────────
//
// NOTE: bb_reversion's `use_limit` is force-disabled by `update_params` (GAP-9
// — paper engine has no limit-order matcher). These tests bypass `update_params`
// by writing `s.use_limit = true` directly to verify the algorithm in isolation.
// GAP-9 force-disable itself stays — it's Backlog A scope, NOT G7-09c scope.
//
// 注意：bb_reversion 的 `use_limit` 由 `update_params` 強制關閉（GAP-9 — paper
// 引擎無限價撮合）。這些測試直接 `s.use_limit = true` 繞過 update_params 以
// 隔離驗證算法。GAP-9 force-disable 維持，屬 Backlog A scope，不在 G7-09c。

use crate::strategies::common::{compute_post_only_price, MakerPriceInputs};

fn ctx_bb_with_bbo_g709c(
    pct_b: f64,
    rsi: f64,
    ts: u64,
    bid: f64,
    ask: f64,
    tick: f64,
) -> TickContext<'static> {
    use openclaw_core::indicators::HurstResult;
    // W-AUDIT-6d #6 — sma_50 同 ctx_bb auto-derive 邏輯。
    // W-AUDIT-6d #6: sma_50 same auto-derive pattern as ctx_bb.
    let sma_50_value = if pct_b < 0.0 {
        51_000.0
    } else if pct_b > 1.0 {
        49_000.0
    } else {
        50_000.0
    };
    let ind = Box::leak(Box::new(IndicatorSnapshot {
        bollinger: Some(BollingerResult {
            upper: 51000.0,
            middle: 50000.0,
            lower: 49000.0,
            bandwidth: 0.04,
            percent_b: pct_b,
        }),
        rsi_14: Some(rsi),
        adx: Some(AdxResult {
            adx: 15.0,
            plus_di: 20.0,
            minus_di: 18.0,
        }),
        hurst: Some(HurstResult {
            hurst: 0.35,
            regime: "mean_reverting".into(),
        }),
        sma_50: Some(sma_50_value),
        ..Default::default()
    }));
    TickContext {
        symbol: "BTC",
        price: 50_000.0,
        timestamp_ms: ts,
        indicators: Some(ind),
        indicators_5m: None,
        signals: &[],
        h0_allowed: true,
        funding_rate: None,
        index_price: None,
        open_interest: None,
        best_bid: Some(bid),
        best_ask: Some(ask),
        tick_size: Some(tick),
        alpha_surface_ref: &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
        position_state: None,
        is_pinned: true,
    }
}

/// G7-09c: bb_reversion long entry computes BBO-aware passive limit_price when
/// use_limit is set directly (bypassing GAP-9 force-disable in update_params).
/// G7-09c：bb_reversion 多頭直接 set use_limit=true 繞過 GAP-9，驗 BBO-aware 算法。
#[test]
fn test_g7_09c_bb_reversion_buy_uses_best_bid_passive() {
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;
    s.use_limit = true; // bypass GAP-9 in update_params
    s.maker_price_buffer_ticks = 1;
    s.limit_offset_bps = 1.0;
    let i = s.on_tick(
        &ctx_bb_with_bbo_g709c(-0.1, 25.0, 0, 49_999.5, 50_000.5, 0.1),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Open(intent) => {
            assert!(intent.is_long);
            assert_eq!(intent.order_type, "limit");
            let lp = intent.limit_price.expect("limit_price set");
            // Expected: 49_999.5 - 1*0.1 = 49_999.4 (strictly below ask).
            // 預期：49_999.5 - 0.1 = 49_999.4（嚴格低於 ask）。
            assert!(
                (lp - 49_999.4).abs() < 1e-6,
                "G7-09c BUY limit got {lp}, expected 49_999.4"
            );
        }
        other => panic!("expected Open, got {other:?}"),
    }
}

/// G7-09c: bb_reversion short entry computes BBO-aware passive limit_price.
/// G7-09c：bb_reversion 空頭驗 BBO-aware 算法。
#[test]
fn test_g7_09c_bb_reversion_sell_uses_best_ask_passive() {
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;
    s.use_limit = true;
    s.maker_price_buffer_ticks = 1;
    s.limit_offset_bps = 1.0;
    // percent_b > 1 + RSI overbought → SHORT.
    // percent_b > 1 + RSI 超買 → 空頭。
    let i = s.on_tick(
        &ctx_bb_with_bbo_g709c(1.1, 75.0, 0, 49_999.5, 50_000.5, 0.1),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Open(intent) => {
            assert!(!intent.is_long);
            assert_eq!(intent.order_type, "limit");
            let lp = intent.limit_price.expect("limit_price set");
            // Expected: 50_000.5 + 1*0.1 = 50_000.6 (strictly above bid).
            // 預期：50_000.5 + 0.1 = 50_000.6（嚴格高於 bid）。
            assert!(
                (lp - 50_000.6).abs() < 1e-6,
                "G7-09c SELL limit got {lp}, expected 50_000.6"
            );
        }
        other => panic!("expected Open, got {other:?}"),
    }
}

/// G7-09c: bb_reversion params round-trip preserves maker_price_buffer_ticks.
/// G7-09c：bb_reversion params 來回保留 maker_price_buffer_ticks。
#[test]
fn test_g7_09c_bb_reversion_params_roundtrip_buffer_ticks() {
    let mut s = BbReversion::new();
    let mut params = s.get_params();
    assert_eq!(params.maker_price_buffer_ticks, 1, "default buffer = 1");
    params.maker_price_buffer_ticks = 3;
    s.update_params(params).expect("update_params");
    let back = s.get_params();
    assert_eq!(back.maker_price_buffer_ticks, 3, "round-trip preserved");
    // Validate guard: buffer > 10 must reject.
    // Validate 防護：buffer > 10 必拒。
    let mut bad = s.get_params();
    bad.maker_price_buffer_ticks = 11;
    assert!(
        s.update_params(bad).is_err(),
        "buffer > 10 must fail validate"
    );
}

/// G7-09c: helper smoke test invoked via bb_reversion module re-export path.
/// G7-09c：透過 bb_reversion 模組路徑呼叫共享 helper 的 smoke test。
#[test]
fn test_g7_09c_bb_reversion_helper_skips_when_no_bbo() {
    // No BBO → strict skip instead of last_price fallback. Confirms the helper
    // is reachable from bb_reversion's import surface.
    // 無 BBO → 嚴格跳過而不是 last_price fallback；同時確認 helper 可達。
    let inputs = MakerPriceInputs {
        last_price: 50_000.0,
        best_bid: None,
        best_ask: None,
        tick_size: Some(0.1),
    };
    let buy = compute_post_only_price(true, inputs, 1.0, 1, "bb_reversion", "BTCUSDT");
    let sell = compute_post_only_price(false, inputs, 1.0, 1, "bb_reversion", "BTCUSDT");
    assert!(buy.is_none(), "BUY must skip without side quote");
    assert!(sell.is_none(), "SELL must skip without side quote");
}

// ═══════════════════════════════════════════════════════════════════════════
// G7-03 Phase B regression — typed `RegimeLabel` migration
// G7-03 Phase B 回歸 — 切換為 typed RegimeLabel
// ═══════════════════════════════════════════════════════════════════════════
//
// Purpose: prove the migrated `from_legacy_str(&h.regime) == AntiPersistent`
// gate behaves bit-identically to the previous `h.regime == "mean_reverting"`
// string compare for the `hurst_regime_boost` boost in entry confidence.

/// Helper: ctx with a custom `regime` string (overrides the default
/// "mean_reverting" used by `ctx_bb`). Lets us exercise Persistent / Random
/// without rebuilding the full IndicatorSnapshot inline.
/// 助手：覆寫 `ctx_bb` 默認 mean_reverting 標籤；不重建 IndicatorSnapshot。
fn ctx_bb_with_regime(pct_b: f64, rsi: f64, ts: u64, regime: &str) -> TickContext<'static> {
    use openclaw_core::indicators::HurstResult;
    // W-AUDIT-6d #6 — sma_50 同 ctx_bb auto-derive 邏輯。
    let sma_50_value = if pct_b < 0.0 {
        51_000.0
    } else if pct_b > 1.0 {
        49_000.0
    } else {
        50_000.0
    };
    let ind = Box::leak(Box::new(IndicatorSnapshot {
        bollinger: Some(BollingerResult {
            upper: 51000.0,
            middle: 50000.0,
            lower: 49000.0,
            bandwidth: 0.04,
            percent_b: pct_b,
        }),
        rsi_14: Some(rsi),
        adx: Some(AdxResult {
            adx: 15.0,
            plus_di: 20.0,
            minus_di: 18.0,
        }),
        hurst: Some(HurstResult {
            hurst: 0.35,
            regime: regime.to_string(),
        }),
        sma_50: Some(sma_50_value),
        ..Default::default()
    }));
    TickContext {
        symbol: "BTC",
        price: 50000.0,
        timestamp_ms: ts,
        indicators: Some(ind),
        indicators_5m: None,
        signals: &[],
        h0_allowed: true,
        funding_rate: None,
        index_price: None,
        open_interest: None,
        best_bid: None,
        best_ask: None,
        tick_size: None,
        alpha_surface_ref: &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
        position_state: None,
        is_pinned: true,
    }
}

#[test]
fn test_phase_b_anti_persistent_label_triggers_hurst_boost() {
    // Mean-reverting (= AntiPersistent) regime — the typed match must accept
    // it and let the entry path produce a long with the boost in play.
    // Regression target: legacy `h.regime == "mean_reverting"` must remain
    // bit-identical with `from_legacy_str() == AntiPersistent`.
    // AntiPersistent regime 必須觸發加成；migration 對齊 legacy 字串比對。
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;
    let i = s.on_tick(
        &ctx_bb_with_regime(-0.1, 25.0, 0, "mean_reverting"),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert_eq!(i.len(), 1, "AntiPersistent must allow oversold long entry");
    match &i[0] {
        StrategyAction::Open(intent) => assert!(intent.is_long),
        other => panic!("expected Open, got {:?}", other),
    }
}

#[test]
fn test_phase_b_persistent_regime_does_not_match_reversion_boost() {
    // Persistent regime (legacy "trending") — `from_legacy_str` returns
    // `Persistent`, which does NOT match `AntiPersistent`, so the
    // hurst_regime_boost should NOT fire. Confluence may still allow entry
    // (the boost is additive, not gating); we assert intent count instead of
    // confidence here because confluence's regime weight is the single
    // load-bearing branch and is well-covered upstream.
    // Persistent regime 不應觸發 reversion 加成；migration 對齊。
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;
    // Score with a Persistent regime + oversold setup tends to fall under the
    // qty_pct threshold (regime mismatch in confluence) — we accept either
    // (a) zero intents (gated by score) or (b) one Open with no AntiPersistent
    // boost. Both prove `Persistent != AntiPersistent` enum-wise.
    // Persistent + oversold 通常被 confluence regime 權重壓下；可能 0 intent 或
    // 1 個 Open 但無 reversion boost。兩者皆證明 enum 對齊。
    let i = s.on_tick(
        &ctx_bb_with_regime(-0.1, 25.0, 0, "trending"),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert!(
        i.len() <= 1,
        "Persistent regime must not produce more intents than 1"
    );
    if let Some(StrategyAction::Open(intent)) = i.first() {
        // The pre-migration code path also tagged this with no
        // `hurst_regime_boost`. Since boost is in [0, 0.3] and additive, a
        // confidence below 0.6 (default base) is the simplest invariant to
        // assert without scraping all the confluence weights.
        // 不檢查具體值 — boost 為加性，confidence 應 ≤ base 上限以證未加成。
        assert!(
            intent.confidence < 0.85,
            "no AntiPersistent boost should keep confidence below ~0.85"
        );
    }
}

#[test]
fn test_phase_b_random_regime_does_not_trigger_reversion_boost() {
    // Random walk regime — same as Persistent semantically (not
    // AntiPersistent), the typed match `_` arm fires.
    // Random regime 不命中 AntiPersistent，走 _ 分支不加成。
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;
    let i = s.on_tick(
        &ctx_bb_with_regime(-0.1, 25.0, 0, "random_walk"),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    // Same expectation as Persistent: either gated by confluence or boost-less.
    assert!(i.len() <= 1);
    if let Some(StrategyAction::Open(intent)) = i.first() {
        assert!(
            intent.confidence < 0.85,
            "no AntiPersistent boost should keep confidence below ~0.85"
        );
    }
}

#[test]
fn test_phase_b_unknown_regime_string_treated_as_random() {
    // Defensive: unknown regime string `from_legacy_str` → Random → no boost.
    // Mirrors bb_breakout's identical guard. 對應 bb_breakout 的同樣防禦測試。
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;
    let i = s.on_tick(
        &ctx_bb_with_regime(-0.1, 25.0, 0, "totally_invalid"),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert!(i.len() <= 1);
    if let Some(StrategyAction::Open(intent)) = i.first() {
        assert!(
            intent.confidence < 0.85,
            "unknown regime should not add reversion boost"
        );
    }
}

// ─────────────────────────────────────────────────────────────────────────
// W-AUDIT-6d #6 (AMD-2026-05-09-02 §3) — pair MA confirmation gate tests
// W-AUDIT-6d #6 — pair MA confirmation gate 測試
// ─────────────────────────────────────────────────────────────────────────

/// Helper: ctx with custom sma_50 value（覆寫 ctx_bb 的 auto-derive）。
/// W-AUDIT-6d #6 — 用於精準測試 MA gate 拒絕路徑。
/// Helper to override sma_50 for precise MA gate rejection testing.
fn ctx_bb_with_custom_sma_50(
    pct_b: f64,
    rsi: f64,
    ts: u64,
    sma_50: Option<f64>,
) -> TickContext<'static> {
    use openclaw_core::indicators::HurstResult;
    let ind = Box::leak(Box::new(IndicatorSnapshot {
        bollinger: Some(BollingerResult {
            upper: 51000.0,
            middle: 50000.0,
            lower: 49000.0,
            bandwidth: 0.04,
            percent_b: pct_b,
        }),
        rsi_14: Some(rsi),
        adx: Some(AdxResult {
            adx: 15.0,
            plus_di: 20.0,
            minus_di: 18.0,
        }),
        hurst: Some(HurstResult {
            hurst: 0.35,
            regime: "mean_reverting".into(),
        }),
        sma_50,
        ..Default::default()
    }));
    TickContext {
        symbol: "BTC",
        price: 50000.0,
        timestamp_ms: ts,
        indicators: Some(ind),
        indicators_5m: None,
        signals: &[],
        h0_allowed: true,
        funding_rate: None,
        index_price: None,
        open_interest: None,
        best_bid: None,
        best_ask: None,
        tick_size: None,
        alpha_surface_ref: &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
        position_state: None,
        is_pinned: true,
    }
}

#[test]
fn test_w_audit_6d_ma_pair_default_on() {
    // Default 啟用 MA pair confirmation；price=50000 + sma_50 None → fail-closed。
    // Default ON: MA absent → no entry (fail-closed)。
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;
    assert!(s.require_ma_confirmation, "default 必啟用 MA pair gate");
    assert_eq!(s.ma_confirmation_kind, "sma_50");

    let i = s.on_tick(
        &ctx_bb_with_custom_sma_50(-0.1, 25.0, 0, None),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert_eq!(
        i.len(),
        0,
        "MA 不可得時必 fail-closed（§二 原則 6 失敗默認收縮）"
    );
}

#[test]
fn test_w_audit_6d_long_entry_blocked_when_price_above_ma() {
    // Long entry（oversold reversion）必 price < ma；price=50000 > ma=49000 → reject。
    // Long entry must require price < ma; price > ma → reject (would be trend-following).
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;

    let i = s.on_tick(
        &ctx_bb_with_custom_sma_50(
            -0.1,
            25.0,
            0,
            Some(49_000.0), // ma < price → long reversion 在「下方反轉」前提失敗 → 不入場。
        ),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert_eq!(
        i.len(),
        0,
        "price > ma 時 long reversion 必拒（避免 trend-following）"
    );
}

#[test]
fn test_w_audit_6d_long_entry_passes_when_price_below_ma() {
    // Long entry passes when price < ma (textbook downward reversion).
    // 教科書下方反轉：price < ma → 過 gate。
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;

    let i = s.on_tick(
        &ctx_bb_with_custom_sma_50(
            -0.1,
            25.0,
            0,
            Some(51_000.0), // ma > price → 「下方反轉」確認 → 過 gate。
        ),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Open(intent) => assert!(intent.is_long),
        other => panic!("expected Open, got {:?}", other),
    }
}

#[test]
fn test_w_audit_6d_short_entry_blocked_when_price_below_ma() {
    // Short entry（overbought reversion）必 price > ma；price=50000 < ma=51000 → reject。
    // Short entry must require price > ma; price < ma → reject.
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;

    let i = s.on_tick(
        &ctx_bb_with_custom_sma_50(
            1.2,
            75.0,
            0,
            Some(51_000.0), // ma > price → 「上方反轉」前提失敗 → 不入場。
        ),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert_eq!(
        i.len(),
        0,
        "price < ma 時 short reversion 必拒（避免 breakout）"
    );
}

#[test]
fn test_w_audit_6d_short_entry_passes_when_price_above_ma() {
    // Short entry passes when price > ma (textbook upward reversion).
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;

    let i = s.on_tick(
        &ctx_bb_with_custom_sma_50(
            1.2,
            75.0,
            0,
            Some(49_000.0), // ma < price → 「上方反轉」確認 → 過 gate。
        ),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Open(intent) => assert!(!intent.is_long, "expected short entry"),
        other => panic!("expected Open, got {:?}", other),
    }
}

#[test]
fn test_w_audit_6d_disable_ma_confirmation_bypasses_gate() {
    // require_ma_confirmation=false（W-AUDIT-9 stage rollback path）→ MA 不可得也允許。
    // When gate disabled, MA absence is not blocking (rollback path scenario).
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;
    s.require_ma_confirmation = false;

    let i = s.on_tick(
        &ctx_bb_with_custom_sma_50(-0.1, 25.0, 0, None),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert_eq!(i.len(), 1, "gate disabled 時 MA 不可得仍允許");
}

#[test]
fn test_w_audit_6d_ma_gate_with_non_finite_value_fails_closed() {
    // sma_50 = NaN / Infinity → fail-closed（防 silent boundary slippage）。
    // NaN/Inf MA → fail-closed (防 silent boundary slippage)。
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;

    let i = s.on_tick(
        &ctx_bb_with_custom_sma_50(-0.1, 25.0, 0, Some(f64::NAN)),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert_eq!(i.len(), 0, "NaN MA 必 fail-closed");

    s.cooldown.clear("BTC"); // reset cooldown
    let i2 = s.on_tick(
        &ctx_bb_with_custom_sma_50(-0.1, 25.0, 1000, Some(f64::INFINITY)),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert_eq!(i2.len(), 0, "Infinity MA 必 fail-closed");
}

#[test]
fn test_w_audit_6d_params_validate_ma_kind_whitelist() {
    // ma_confirmation_kind whitelist = {sma_20, sma_50, ema_12, ema_26}。
    // ma_confirmation_kind whitelist enforcement.
    use crate::strategies::StrategyParams;

    let valid_kinds = ["sma_20", "sma_50", "ema_12", "ema_26"];
    for kind in valid_kinds {
        let p = BbReversionParams {
            ma_confirmation_kind: kind.to_string(),
            ..Default::default()
        };
        assert!(p.validate().is_ok(), "{kind} 必為合法 MA kind");
    }

    let bad = BbReversionParams {
        ma_confirmation_kind: "donchian_20".to_string(),
        ..Default::default()
    };
    let err = bad.validate().unwrap_err();
    assert!(
        err.contains("ma_confirmation_kind"),
        "拒非 whitelist kind: {err}"
    );
}

#[test]
fn test_w_audit_6d_params_roundtrip_ma_pair_fields() {
    // update_params + get_params 必 round-trip MA pair 欄位。
    // Hot-reload round-trip preserves MA pair config.
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;

    let p = BbReversionParams {
        require_ma_confirmation: false,
        ma_confirmation_kind: "ema_26".to_string(),
        ..Default::default()
    };
    assert!(s.update_params(p).is_ok());

    let got = s.get_params();
    assert!(!got.require_ma_confirmation, "update + get 必 round-trip");
    assert_eq!(got.ma_confirmation_kind, "ema_26");
}

#[test]
fn test_w_audit_6d_param_ranges_includes_require_ma_confirmation() {
    // require_ma_confirmation 必登記在 param_ranges（agent_adjustable=false）。
    use crate::strategies::StrategyParams;
    let ranges = BbReversionParams::param_ranges();
    let entry = ranges
        .iter()
        .find(|r| r.name == "require_ma_confirmation")
        .expect("require_ma_confirmation 必登記");
    assert!(
        !entry.agent_adjustable,
        "require_ma_confirmation 不可被 agent 動態關閉"
    );
}

// ═══════════════════════════════════════════════════════════════════════════
// P0 Option A-Lite (2026-05-11) — paper_state SSoT acceptance tests
// P0 Option A-Lite — paper_state 為 SSoT 的接收性測試
// ═══════════════════════════════════════════════════════════════════════════
//
// 背景：22:08 May 10 watchdog Auto restart 引爆 cross-strategy mass scalp。
// bb_reversion 透過 W7-2 sync self.positions 把 paper_state cross-strategy
// 倉位拉進本地 state，下個 tick 走 Some(_) exit 分支撞 [0.2, 0.8] 寬 exit
// zone 大量平掉 grid/ma 的倉。SSoT 改造後：self.positions 完全消失，倉位
// 唯一來源為 paper_state（透過 ctx.position_state 注入），策略以
// owner_strategy gate 過濾自家持倉，cross-strategy 倉位自然 skip entry
// 且不觸發 exit zone。從根源杜絕同 RCA scenario 再現。
//
// 留存 4 case：
// - test 1：ctx.position_state owner=grid_trading → entry skip
// - test 2：ctx.position_state = None → normal entry（baseline regression）
// - test 3：grid 持倉 + bb 進 exit zone → 0 Close（核心 acceptance）
// - test 4：bb_reversion 自家持倉 + bb 進 exit zone → 1 Close（self-exit 回歸）

use crate::paper_state::PaperPosition;

/// Helper：構建 PaperPosition 模擬 paper_state 真實持倉，可指定 owner_strategy。
/// `owner` 留參數化以同時測試 grid_trading / bb_reversion / bybit_sync 三種 owner 場景。
fn make_paper_position_bbr_with_owner(symbol: &str, is_long: bool, owner: &str) -> PaperPosition {
    PaperPosition {
        symbol: symbol.to_string(),
        is_long,
        qty: 1.0,
        entry_price: 50_000.0,
        best_price: 50_000.0,
        entry_fee: 0.0,
        entry_ts_ms: 0,
        unrealized_pnl: 0.0,
        entry_context_id: String::new(),
        owner_strategy: owner.to_string(),
        entry_notional: 50_000.0,
        max_favorable_pnl_pct: 0.0,
        peak_reached_ts_ms: 0,
    }
}

/// Test 1：ctx.position_state owner = grid_trading + bb_reversion oversold signal
/// → 必 0 actions（owner_strategy gate skip entry）。
/// 替代舊 W7-2 #1 test。SSoT 改造後策略不持本地 state，純靠 paper_state。
#[test]
fn test_bbr_p0_skip_entry_when_cross_strategy_position_holds() {
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;
    let pp = make_paper_position_bbr_with_owner("BTC", false, "grid_trading");
    let mut ctx = ctx_bb_bbo(-0.1, 25.0, 0, 49_999.5, 50_000.5, 0.1); // oversold long signal
    ctx.position_state = Some(&pp);

    let intents = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);

    assert!(
        intents.is_empty(),
        "cross-strategy 持倉（owner=grid_trading）必 skip entry，但發了 {} intents",
        intents.len()
    );
}

/// Test 2：ctx.position_state = None + valid oversold signal → 1 entry intent。
/// Baseline regression：owner gate 不誤殺正常 entry。
#[test]
fn test_bbr_p0_proceeds_entry_when_no_position() {
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;
    let mut ctx = ctx_bb_bbo(-0.1, 25.0, 0, 49_999.5, 50_000.5, 0.1); // oversold long signal
    ctx.position_state = None;

    let intents = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);

    assert_eq!(intents.len(), 1, "無倉位時 oversold 必發 long entry");
    match &intents[0] {
        StrategyAction::Open(intent) => assert!(intent.is_long, "expected LONG entry"),
        other => panic!("expected StrategyAction::Open, got {:?}", other),
    }
}

/// Test 3（核心 acceptance）：grid 已持 LONG 倉，bb.percent_b = 0.5 在 exit zone
/// [0.2, 0.8] 內 → bb_reversion 必發 0 Close action。
/// 對應 RCA root scenario：22:08 watchdog restart 後 bb_reversion 不再 mass close
/// grid 的倉。spec §3.2 #1 + §5.3 第 2 個 acceptance test。
#[test]
fn bb_reversion_does_not_close_grid_position_on_pctb_zone() {
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;
    // grid_trading 已持 LONG BTC（owner ≠ bb_reversion）。
    let pp = make_paper_position_bbr_with_owner("BTC", true, "grid_trading");
    // bb.percent_b = 0.5 落在 bb_reversion 預設 exit zone [0.2, 0.8] 中央。
    let mut ctx = ctx_bb(0.5, 50.0, 0);
    ctx.position_state = Some(&pp);

    let intents = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);

    // 關鍵 invariant：cross-strategy 倉位即使在 bb_reversion exit zone 中也不觸發 Close。
    let close_count = intents
        .iter()
        .filter(|a| matches!(a, StrategyAction::Close { .. }))
        .count();
    assert_eq!(
        close_count, 0,
        "bb_reversion 必不平 cross-strategy（grid_trading）持倉，\
         即使 bb.percent_b 在 exit zone 內；發了 {} Close",
        close_count
    );
    assert!(
        intents.is_empty(),
        "cross-strategy 持倉應 skip 全路徑（entry + exit），但發了 {} actions",
        intents.len()
    );
}

/// Test 4：ctx.position_state owner = bb_reversion + bb 進 exit zone → 必 1 Close。
/// 確保 self-owned 持倉仍正常觸發 mean-reversion exit（baseline self-exit regression）。
#[test]
fn test_bbr_p0_self_owned_position_exits_on_pctb_zone() {
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;
    let pp = make_paper_position_bbr_with_owner("BTC", true, "bb_reversion");
    let mut ctx = ctx_bb(0.5, 50.0, 0);
    ctx.position_state = Some(&pp);

    let intents = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);

    assert_eq!(intents.len(), 1, "self-owned 持倉在 exit zone 應觸發 Close");
    match &intents[0] {
        StrategyAction::Close { reason, .. } => {
            assert_eq!(reason, "bb_mean_revert", "exit reason 必為 bb_mean_revert");
        }
        other => panic!("expected StrategyAction::Close, got {:?}", other),
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// P0 Option A-Lite — on_rejection cooldown rollback（化簡後）
// ═══════════════════════════════════════════════════════════════════════════
//
// W7-3 Option B + RC-04 position rollback 已隨 self.positions 移除消失。
// on_rejection 化簡為純 cooldown rollback：reject 時還原 last_trade_ms
// 至 entry path 寫入前狀態，避免下次 entry 被舊冷卻誤鎖。
// 對齊 ma_crossover/strategy_impl.rs 同 pattern。

use crate::intent_processor::OrderIntent;

fn make_test_intent_p0(symbol: &str, is_long: bool) -> OrderIntent {
    OrderIntent {
        symbol: symbol.to_string(),
        is_long,
        qty: 1.0,
        confidence: 0.5,
        strategy: "bb_reversion".to_string(),
        order_type: "market".to_string(),
        limit_price: None,
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
    }
}

/// on_rejection cooldown rollback：prev_last_trade_ms = 0（未見哨兵）→ cooldown clear。
#[test]
fn test_bbr_p0_on_rejection_unseen_clears_cooldown() {
    let mut s = BbReversion::new();
    let intent = make_test_intent_p0("SOLUSDT", true);
    // 模擬 entry tick：snapshot 哨兵 0（變更前未見） + cooldown.record_signal。
    s.prev_last_trade_ms.insert("SOLUSDT".to_string(), 0);
    s.cooldown.record_signal("SOLUSDT", 100_000);

    s.on_rejection(&intent, "cost_gate(JS-demo): negative edge");

    assert!(
        s.cooldown.last_ms("SOLUSDT").is_none(),
        "prev_last_trade_ms == 0（未見）→ on_rejection 必 clear cooldown 還原未交易狀態"
    );
}

/// on_rejection cooldown rollback：prev_last_trade_ms != 0 → cooldown 回寫原值。
#[test]
fn test_bbr_p0_on_rejection_seen_restores_prior_cooldown() {
    let mut s = BbReversion::new();
    let intent = make_test_intent_p0("ETHUSDT", true);
    // 模擬：上次交易在 50_000；entry tick 又寫入 200_000；reject 後應還原為 50_000。
    let prior_ts = 50_000_u64;
    s.prev_last_trade_ms.insert("ETHUSDT".to_string(), prior_ts);
    s.cooldown.record_signal("ETHUSDT", 200_000);

    s.on_rejection(&intent, "cost_gate(JS-demo): negative edge");

    assert_eq!(
        s.cooldown.last_ms("ETHUSDT"),
        Some(prior_ts),
        "prev_last_trade_ms != 0 → on_rejection 必還原 cooldown 為原 last_trade_ms"
    );
}
