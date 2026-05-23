//! C10 funding harvest 主邏輯 unit tests。
//! 範圍：entry / exit / rebalance / cooldown / IPC params / cross-strategy fence。

use super::*;
use crate::strategies::Strategy;

fn make_ctx<'a>(
    symbol: &'a str,
    price: f64,
    ts: u64,
    funding_rate: Option<f64>,
    index_price: Option<f64>,
) -> TickContext<'a> {
    TickContext {
        symbol,
        price,
        timestamp_ms: ts,
        indicators: None,
        indicators_5m: None,
        signals: &[],
        h0_allowed: true,
        funding_rate,
        index_price,
        open_interest: None,
        best_bid: Some(price * 0.9999),
        best_ask: Some(price * 1.0001),
        tick_size: Some((price * 0.000_001).max(0.000_1)),
        alpha_surface_ref: &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
        position_state: None,
        is_pinned: true,
    }
}

fn make_position(
    symbol: String,
    is_long: bool,
    qty: f64,
    entry_price: f64,
    entry_ms: u64,
    owner: &str,
) -> crate::paper_state::containers::PaperPosition {
    crate::paper_state::containers::PaperPosition {
        symbol,
        is_long,
        qty,
        entry_price,
        best_price: entry_price,
        entry_fee: 0.0,
        entry_ts_ms: entry_ms,
        unrealized_pnl: 0.0,
        entry_context_id: String::new(),
        owner_strategy: owner.to_string(),
        entry_notional: qty * entry_price,
        peak_reached_ts_ms: entry_ms as i64,
        max_favorable_pnl_pct: 0.0,
    }
}

fn ctx_with_position<'a>(
    base: TickContext<'a>,
    pos: &'a crate::paper_state::containers::PaperPosition,
) -> TickContext<'a> {
    TickContext {
        position_state: Some(pos),
        ..base
    }
}

// ── 純函數：annualized / basis / net edge / should_enter / should_exit ──

#[test]
fn annualized_funding_btc_spot_8h() {
    // 0.0001 per 8h × 3 × 365 ≈ 0.1095 → ~11% APR。
    let a = FundingHarvest::annualized_funding(0.0001);
    assert!((a - 0.1095).abs() < 1e-6);
}

#[test]
fn compute_basis_pct_normal() {
    // perp=50500, index=50000 → 1% basis。
    let bp = FundingHarvest::compute_basis_pct(50_500.0, Some(50_000.0));
    assert!((bp - 1.0).abs() < 1e-9);
}

#[test]
fn compute_basis_pct_missing_index_fail_closed() {
    let bp = FundingHarvest::compute_basis_pct(50_000.0, None);
    assert!(bp == f64::MAX, "missing index → fail-closed sentinel");
}

#[test]
fn compute_basis_pct_zero_index_fail_closed() {
    let bp = FundingHarvest::compute_basis_pct(50_000.0, Some(0.0));
    assert!(bp == f64::MAX);
}

#[test]
fn compute_net_edge_default_high_funding_positive() {
    let s = FundingHarvest::new();
    // funding=0.001 per 8h = 10 bps；amortized = 37/3 ≈ 12.33 → net ≈ -2.33。
    let edge = s.compute_net_edge_bps_per_period(0.001);
    assert!(edge < 0.0);
}

#[test]
fn compute_net_edge_positive_at_high_funding() {
    let s = FundingHarvest::new();
    // funding=0.005 per 8h = 50 bps；amortized ≈ 12.33 → net ≈ 37.67 > 0。
    let edge = s.compute_net_edge_bps_per_period(0.005);
    assert!(edge > 0.0);
}

#[test]
fn should_enter_satisfied_at_high_annualized() {
    let s = FundingHarvest::new();
    // annualized = 0.005 × 3 × 365 ≈ 5.475 > 5% threshold；
    // net edge 正；basis 0.1% < 0.4% gate。
    assert!(s.should_enter(0.005, 0.1));
}

#[test]
fn should_enter_blocked_below_annualized_threshold() {
    let s = FundingHarvest::new();
    // annualized = 0.0001 × 3 × 365 ≈ 0.1095 (10.95%) > 5%；但 net edge < 0 → block。
    assert!(!s.should_enter(0.0001, 0.1));
}

#[test]
fn should_enter_blocked_negative_funding() {
    let s = FundingHarvest::new();
    // 反向 funding（< 0）→ design choice 不入場（funding harvest 只收 +funding）。
    assert!(!s.should_enter(-0.005, 0.1));
}

#[test]
fn should_enter_blocked_wide_basis() {
    let s = FundingHarvest::new();
    // basis = 0.5%；入場門 = 0.5 × 0.8 = 0.4% → block。
    assert!(!s.should_enter(0.005, 0.5));
}

#[test]
fn should_exit_funding_decay() {
    let s = FundingHarvest::new();
    // annualized = 0.00001 × 3 × 365 ≈ 0.01095 (1.1%) < 2% exit → exit。
    assert!(s.should_exit(0.00001, 0.1, 1_000, 0));
}

#[test]
fn should_exit_negative_funding() {
    let s = FundingHarvest::new();
    assert!(s.should_exit(-0.001, 0.1, 1_000, 0));
}

#[test]
fn should_exit_basis_drift() {
    let s = FundingHarvest::new();
    // basis 0.6 > max 0.5 → exit。
    assert!(s.should_exit(0.005, 0.6, 1_000, 0));
}

#[test]
fn should_exit_max_hold() {
    let s = FundingHarvest::new();
    let entry = 1_000_u64;
    let now = entry + s.max_hold_ms + 1;
    assert!(s.should_exit(0.005, 0.1, now, entry));
}

#[test]
fn should_exit_normal_no() {
    let s = FundingHarvest::new();
    // high funding + tight basis + within window → 不平倉。
    assert!(!s.should_exit(0.005, 0.1, 1_000, 0));
}

// ── on_tick entry path ──

#[test]
fn on_tick_inactive_no_action() {
    let mut s = FundingHarvest::new();
    // 預設 active=false。
    let ctx = make_ctx("BTCUSDT", 50_000.0, 100_000, Some(0.005), Some(50_000.0));
    assert!(s
        .on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE)
        .is_empty());
}

#[test]
fn on_tick_non_allowed_symbol_skip() {
    let mut s = FundingHarvest::new();
    s.set_active(true);
    let ctx = make_ctx("SOLUSDT", 100.0, 100_000, Some(0.005), Some(100.0));
    assert!(s
        .on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE)
        .is_empty());
}

#[test]
fn on_tick_missing_funding_rate_skip() {
    let mut s = FundingHarvest::new();
    s.set_active(true);
    let ctx = make_ctx("BTCUSDT", 50_000.0, 100_000, None, Some(50_000.0));
    assert!(s
        .on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE)
        .is_empty());
}

#[test]
fn on_tick_missing_index_price_skip() {
    let mut s = FundingHarvest::new();
    s.set_active(true);
    // index_price None → basis = f64::MAX → should_enter false → skip。
    let ctx = make_ctx("BTCUSDT", 50_000.0, 100_000, Some(0.005), None);
    assert!(s
        .on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE)
        .is_empty());
}

#[test]
fn on_tick_positive_funding_entry_short_postonly() {
    let mut s = FundingHarvest::new();
    s.set_active(true);
    let ctx = make_ctx("BTCUSDT", 50_000.0, 100_000, Some(0.005), Some(50_000.0));
    let actions = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(actions.len(), 1);
    match &actions[0] {
        StrategyAction::Open(intent) => {
            assert_eq!(intent.symbol, "BTCUSDT");
            assert_eq!(intent.strategy, "funding_harvest");
            assert!(!intent.is_long, "funding harvest = perp SHORT");
            assert_eq!(intent.order_type, "limit");
            assert_eq!(intent.time_in_force, Some(TimeInForce::PostOnly));
            assert_eq!(
                intent.maker_timeout_ms,
                Some(FUNDING_HARVEST_MAKER_TIMEOUT_MS)
            );
            assert!(intent.limit_price.is_some());
            // qty = position_cap_usd / price = 100 / 50000 = 0.002。
            assert!((intent.qty - 0.002).abs() < 1e-9);
        }
        other => panic!("expected Open, got {other:?}"),
    }
    // cooldown 已 record。
    assert!(s.cooldown.last_ms("BTCUSDT").is_some());
}

#[test]
fn on_tick_missing_bbo_skips_entry() {
    let mut s = FundingHarvest::new();
    s.set_active(true);
    let mut ctx = make_ctx("BTCUSDT", 50_000.0, 100_000, Some(0.005), Some(50_000.0));
    ctx.best_bid = None;
    ctx.best_ask = None;
    ctx.tick_size = None;
    let actions = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert!(
        actions.is_empty(),
        "missing BBO → PostOnly fail-closed skip"
    );
}

#[test]
fn on_tick_cooldown_blocks_re_entry() {
    let mut s = FundingHarvest::new();
    s.set_active(true);
    let ctx1 = make_ctx("BTCUSDT", 50_000.0, 100_000, Some(0.005), Some(50_000.0));
    assert_eq!(
        s.on_tick(&ctx1, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE)
            .len(),
        1
    );
    // 緊接 200_000ms tick（< cooldown 3.6M）。
    let ctx2 = make_ctx("BTCUSDT", 50_000.0, 200_000, Some(0.005), Some(50_000.0));
    assert!(s
        .on_tick(&ctx2, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE)
        .is_empty());
    // cooldown 後 OK。
    let ctx3 = make_ctx(
        "BTCUSDT",
        50_000.0,
        100_000 + DEFAULT_COOLDOWN_MS + 1,
        Some(0.005),
        Some(50_000.0),
    );
    assert_eq!(
        s.on_tick(&ctx3, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE)
            .len(),
        1
    );
}

#[test]
fn on_tick_h0_blocked() {
    let mut s = FundingHarvest::new();
    s.set_active(true);
    let mut ctx = make_ctx("BTCUSDT", 50_000.0, 100_000, Some(0.005), Some(50_000.0));
    ctx.h0_allowed = false;
    assert!(s
        .on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE)
        .is_empty());
}

// ── on_tick exit path ──

#[test]
fn on_tick_exit_on_funding_decay() {
    let mut s = FundingHarvest::new();
    s.set_active(true);
    let pos = make_position(
        "BTCUSDT".to_string(),
        false,
        0.002,
        50_000.0,
        0,
        "funding_harvest",
    );
    let base = make_ctx("BTCUSDT", 50_000.0, 100_000, Some(0.00001), Some(50_000.0));
    let ctx = ctx_with_position(base, &pos);
    let actions = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(actions.len(), 1);
    match &actions[0] {
        StrategyAction::Close { symbol, reason, .. } => {
            assert_eq!(symbol, "BTCUSDT");
            assert!(reason.contains("funding_harvest_exit"));
        }
        other => panic!("expected Close, got {other:?}"),
    }
}

#[test]
fn on_tick_no_exit_normal_high_funding() {
    let mut s = FundingHarvest::new();
    s.set_active(true);
    let pos = make_position(
        "BTCUSDT".to_string(),
        false,
        0.002,
        50_000.0,
        0,
        "funding_harvest",
    );
    let base = make_ctx("BTCUSDT", 50_000.0, 100_000, Some(0.005), Some(50_000.0));
    let ctx = ctx_with_position(base, &pos);
    assert!(s
        .on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE)
        .is_empty());
}

#[test]
fn on_tick_cross_strategy_position_skip() {
    let mut s = FundingHarvest::new();
    s.set_active(true);
    // 同 symbol 但 owner=ma_crossover → skip entry，不動 cooldown。
    let pos = make_position(
        "BTCUSDT".to_string(),
        true,
        0.001,
        50_000.0,
        0,
        "ma_crossover",
    );
    let base = make_ctx("BTCUSDT", 50_000.0, 100_000, Some(0.005), Some(50_000.0));
    let ctx = ctx_with_position(base, &pos);
    let actions = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert!(actions.is_empty());
    assert!(s.cooldown.last_ms("BTCUSDT").is_none());
}

#[test]
fn on_tick_bybit_sync_owner_treated_as_cross() {
    let mut s = FundingHarvest::new();
    s.set_active(true);
    let pos = make_position(
        "BTCUSDT".to_string(),
        false,
        0.001,
        50_000.0,
        0,
        "bybit_sync",
    );
    let base = make_ctx("BTCUSDT", 50_000.0, 100_000, Some(0.005), Some(50_000.0));
    let ctx = ctx_with_position(base, &pos);
    assert!(s
        .on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE)
        .is_empty());
}

// ── rejection rollback ──

#[test]
fn rejection_rollback_cooldown_only() {
    let mut s = FundingHarvest::new();
    s.set_active(true);
    assert!(s.cooldown.last_ms("BTCUSDT").is_none());
    let ctx = make_ctx("BTCUSDT", 50_000.0, 100_000, Some(0.005), Some(50_000.0));
    let actions = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(actions.len(), 1);
    assert!(s.cooldown.last_ms("BTCUSDT").is_some());

    if let StrategyAction::Open(ref intent) = actions[0] {
        s.on_rejection(intent, "any_reason");
    }
    // prev=0（未見）→ cooldown clear。
    assert!(s.cooldown.last_ms("BTCUSDT").is_none());
}

// ── IPC update_params ──

#[test]
fn update_params_json_toggles_active() {
    let mut s = FundingHarvest::new();
    assert!(!s.is_active());
    let payload = serde_json::to_string(&FundingHarvestUpdateParams {
        active: true,
        ..FundingHarvestUpdateParams::default()
    })
    .unwrap();
    s.update_params_json(&payload).expect("valid payload");
    assert!(s.is_active());
}

#[test]
fn update_params_rejects_position_cap_over_100() {
    let mut s = FundingHarvest::new();
    let bad = FundingHarvestUpdateParams {
        position_cap_usd: 200.0,
        ..FundingHarvestUpdateParams::default()
    };
    let err = s
        .update_params_json(&serde_json::to_string(&bad).unwrap())
        .unwrap_err();
    assert!(err.contains("hard ceiling"), "err: {err}");
}

#[test]
fn update_params_rejects_non_btcusdt() {
    let mut s = FundingHarvest::new();
    let bad = FundingHarvestUpdateParams {
        allowed_symbols: vec!["SOLUSDT".to_string()],
        ..FundingHarvestUpdateParams::default()
    };
    let err = s
        .update_params_json(&serde_json::to_string(&bad).unwrap())
        .unwrap_err();
    assert!(err.contains("BTCUSDT"), "err: {err}");
}

#[test]
fn param_ranges_json_well_formed() {
    let s = FundingHarvest::new();
    let ranges: Vec<ParamRange> =
        serde_json::from_str(&s.param_ranges_json()).expect("valid JSON");
    let names: std::collections::HashSet<_> = ranges.iter().map(|r| r.name.as_str()).collect();
    for req in [
        "funding_threshold_annualized",
        "funding_exit_annualized",
        "max_basis_pct",
        "max_hold_ms",
        "total_cost_bps",
        "position_cap_usd",
        "delta_drift_threshold",
        "rebalance_check_ms",
    ] {
        assert!(names.contains(req), "missing {req}");
    }
    // active / allowed_symbols 故意 omit。
    assert!(!names.contains("active"));
    assert!(!names.contains("allowed_symbols"));
}

#[test]
fn declared_alpha_sources_funding_skew_basis() {
    let s = FundingHarvest::new();
    let tags = s.declared_alpha_sources();
    assert!(tags.contains(&AlphaSourceTag::FundingSkew));
    assert!(tags.contains(&AlphaSourceTag::Basis));
}

#[test]
fn conf_scale_clamps_to_range() {
    let mut s = FundingHarvest::new();
    assert_eq!(s.conf_scale(), 1.0);
    s.set_conf_scale(3.0);
    assert_eq!(s.conf_scale(), 2.0);
    s.set_conf_scale(-1.0);
    assert_eq!(s.conf_scale(), 0.0);
}
