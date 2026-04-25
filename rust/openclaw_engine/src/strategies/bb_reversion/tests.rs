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
        ..Default::default()
    }));
    TickContext {
        symbol: "BTC",
        price: 50000.0,
        timestamp_ms: ts,
        indicators: Some(ind),
        signals: &[],
        h0_allowed: true,
        funding_rate: None,
        index_price: None,
        open_interest: None,
        best_bid: None,
        best_ask: None,
        tick_size: None,
    }
}

#[test]
fn test_long_oversold() {
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    let i = s.on_tick(&ctx_bb(-0.1, 25.0, 0));
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Open(intent) => assert!(intent.is_long),
        other => panic!("expected StrategyAction::Open, got {:?}", other),
    }
}

#[test]
fn test_exit_mean() {
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    s.on_tick(&ctx_bb(-0.1, 25.0, 0));
    let i = s.on_tick(&ctx_bb(0.5, 50.0, 700_000));
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Close { reason, .. } => assert_eq!(reason, "bb_mean_revert"),
        other => panic!("expected StrategyAction::Close, got {:?}", other),
    }
}

// ── RC-07: Limit order tests / RC-07 限價單測試 ──

#[test]
fn test_limit_order_long() {
    // RC-07 + G7-09c Phase 1: use_limit=true, oversold entry produces limit
    // order with BBO-aware passive price. ctx_bb supplies no BBO → helper
    // falls back to last_price ± offset_bps. Pre-G7-09c expected
    // `bb_lower × (1 + offset)` (49_049); post-G7-09c with no BBO uses
    // `last_price × (1 − offset)` = 50_000 × 0.999 = 49_950.
    // RC-07 + G7-09c Phase 1：use_limit=true 在無 BBO 時走 fallback
    // `last_price × (1 − offset)`，取代舊 `bb_lower × (1 + offset)` 公式
    // （RCA `7f0e793` 顯示舊式跨 book → 100% PostOnly reject）。
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;
    s.use_limit = true;
    s.limit_offset_bps = 10.0; // 10 bps = 0.1%
    let i = s.on_tick(&ctx_bb(-0.1, 25.0, 0));
    assert_eq!(i.len(), 1);
    let intent = match &i[0] {
        StrategyAction::Open(intent) => intent,
        other => panic!("expected StrategyAction::Open, got {:?}", other),
    };
    assert!(intent.is_long);
    assert_eq!(intent.order_type, "limit");
    // G7-09c fallback: 50_000 × (1 − 10/10_000) = 49_950.
    // G7-09c fallback：50_000 × 0.999 = 49_950。
    let expected = 50_000.0 * (1.0 - 10.0 / 10_000.0);
    assert!(
        (intent.limit_price.unwrap() - expected).abs() < 1e-6,
        "G7-09c fallback expected limit_price={}, got={}",
        expected,
        intent.limit_price.unwrap()
    );
}

#[test]
fn test_limit_order_short() {
    // RC-07 + G7-09c Phase 1: use_limit=true, overbought entry produces
    // limit order with BBO-aware passive price. No BBO supplied → fallback
    // path uses `last_price × (1 + offset)` = 50_000 × 1.001 = 50_050,
    // replacing pre-G7-09c `upper × (1 − offset)` = 50_949.
    // RC-07 + G7-09c Phase 1：無 BBO 時 fallback `last_price × (1 + offset)`
    // 取代舊 `upper × (1 − offset)`。
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;
    s.use_limit = true;
    s.limit_offset_bps = 10.0;
    let i = s.on_tick(&ctx_bb(1.1, 75.0, 0));
    assert_eq!(i.len(), 1);
    let intent = match &i[0] {
        StrategyAction::Open(intent) => intent,
        other => panic!("expected StrategyAction::Open, got {:?}", other),
    };
    assert!(!intent.is_long);
    assert_eq!(intent.order_type, "limit");
    // G7-09c fallback: 50_000 × (1 + 10/10_000) = 50_050.
    // G7-09c fallback：50_000 × 1.001 = 50_050。
    let expected = 50_000.0 * (1.0 + 10.0 / 10_000.0);
    assert!(
        (intent.limit_price.unwrap() - expected).abs() < 1e-6,
        "G7-09c fallback expected limit_price={}, got={}",
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
    let i = s.on_tick(&ctx_bb(-0.1, 25.0, 0));
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
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    s.use_limit = true;
    // Enter long with limit order / 限價入場做多
    let i = s.on_tick(&ctx_bb(-0.1, 25.0, 0));
    let entry_intent = match &i[0] {
        StrategyAction::Open(intent) => intent,
        other => panic!("expected StrategyAction::Open, got {:?}", other),
    };
    assert_eq!(entry_intent.order_type, "limit");
    // Exit at mean reversion / 均值回歸出場
    let i = s.on_tick(&ctx_bb(0.5, 50.0, 700_000));
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
    // 5 original + 2 funding_rate + 10 confluence = 17
    assert_eq!(
        ranges.len(),
        17,
        "expected 17 param ranges, got {}",
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
        ..Default::default()
    }));
    TickContext {
        symbol: "BTC",
        price: 50000.0,
        timestamp_ms: ts,
        indicators: Some(ind),
        signals: &[],
        h0_allowed: true,
        funding_rate,
        index_price: None,
        open_interest: None,
        best_bid: None,
        best_ask: None,
        tick_size: None,
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
    let actions_with = s.on_tick(&ctx_with);
    assert!(
        !actions_with.is_empty(),
        "should produce short entry with positive funding"
    );
    let conf_with = match &actions_with[0] {
        StrategyAction::Open(intent) => intent.confidence,
        _ => panic!("expected Open"),
    };

    // Same signal without funding rate
    s.positions.clear();
    s.cooldown = TrendCooldown::new(600_000);
    s.persistence = PersistenceTracker::new();
    let ctx_without = ctx_bb_with_funding(1.2, 75.0, 2000, None);
    let actions_without = s.on_tick(&ctx_without);
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
    let actions_with = s.on_tick(&ctx_with);
    assert!(
        !actions_with.is_empty(),
        "should produce long entry with negative funding"
    );
    let conf_with = match &actions_with[0] {
        StrategyAction::Open(intent) => intent.confidence,
        _ => panic!("expected Open"),
    };

    s.positions.clear();
    s.cooldown = TrendCooldown::new(600_000);
    s.persistence = PersistenceTracker::new();
    let ctx_without = ctx_bb_with_funding(-0.1, 25.0, 2000, None);
    let actions_without = s.on_tick(&ctx_without);
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
    let actions_mis = s.on_tick(&ctx_misaligned);
    assert!(!actions_mis.is_empty());
    let conf_mis = match &actions_mis[0] {
        StrategyAction::Open(intent) => intent.confidence,
        _ => panic!("expected Open"),
    };

    s.positions.clear();
    s.cooldown = TrendCooldown::new(600_000);
    s.persistence = PersistenceTracker::new();
    let ctx_none = ctx_bb_with_funding(-0.1, 25.0, 2000, None);
    let actions_none = s.on_tick(&ctx_none);
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
    let actions_small = s.on_tick(&ctx_small);
    assert!(!actions_small.is_empty());
    let conf_small = match &actions_small[0] {
        StrategyAction::Open(intent) => intent.confidence,
        _ => panic!("expected Open"),
    };

    s.positions.clear();
    s.cooldown = TrendCooldown::new(600_000);
    s.persistence = PersistenceTracker::new();
    let ctx_none = ctx_bb_with_funding(1.2, 75.0, 2000, None);
    let actions_none = s.on_tick(&ctx_none);
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
        ..Default::default()
    }));
    TickContext {
        symbol: "BTC",
        price: 50_000.0,
        timestamp_ms: ts,
        indicators: Some(ind),
        signals: &[],
        h0_allowed: true,
        funding_rate: None,
        index_price: None,
        open_interest: None,
        best_bid: Some(bid),
        best_ask: Some(ask),
        tick_size: Some(tick),
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
    let i = s.on_tick(&ctx_bb_with_bbo_g709c(-0.1, 25.0, 0, 49_999.5, 50_000.5, 0.1));
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
    let i = s.on_tick(&ctx_bb_with_bbo_g709c(1.1, 75.0, 0, 49_999.5, 50_000.5, 0.1));
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
    assert!(s.update_params(bad).is_err(), "buffer > 10 must fail validate");
}

/// G7-09c: helper smoke test invoked via bb_reversion module re-export path.
/// G7-09c：透過 bb_reversion 模組路徑呼叫共享 helper 的 smoke test。
#[test]
fn test_g7_09c_bb_reversion_helper_fallback_when_no_bbo() {
    // No BBO → fallback path uses last_price ± offset_bps, identical to
    // pre-G7-09c bb_reversion behaviour. Confirms the helper is reachable
    // from bb_reversion's import surface.
    // 無 BBO → fallback 使用 last_price ± offset_bps，與 pre-G7-09c 一致；
    // 同時確認 helper 從 bb_reversion 的 import 路徑可達。
    let inputs = MakerPriceInputs {
        last_price: 50_000.0,
        best_bid: None,
        best_ask: None,
        tick_size: None,
    };
    let buy = compute_post_only_price(true, inputs, 1.0, 1, "bb_reversion", "BTCUSDT");
    let sell = compute_post_only_price(false, inputs, 1.0, 1, "bb_reversion", "BTCUSDT");
    // 1 bps offset → 50_000 × (1 ∓ 0.0001) = 49_995 / 50_005.
    // 1 bps 偏移 → 49_995 / 50_005。
    assert!((buy - 49_995.0).abs() < 1e-6, "fallback BUY got {buy}");
    assert!((sell - 50_005.0).abs() < 1e-6, "fallback SELL got {sell}");
}
