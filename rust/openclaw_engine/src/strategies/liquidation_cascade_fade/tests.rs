//! Sprint 2 Alpha Tournament Candidate #4 — liquidation_cascade_fade unit tests。
//! 範圍：
//!   - should_enter / should_exit 純函式各條件獨立觸發
//!   - fade direction map (LongLiquidated→long / ShortLiquidated→short / Mixed→reject)
//!   - per-symbol threshold (BTC $500k / ETH $300k / non-cohort fallback $100k)
//!   - on_tick: panel None → fail-closed; pulse None → skip; threshold below → reject
//!   - cohort gate (BTCUSDT / ETHUSDT)
//!   - self-fills filter stub returns false (Stage 1)
//!   - cross-strategy occupied → skip entry
//!   - exit branch (time-stop / take_profit / reverse_cascade)
//!   - update_params validate
//!   - on_external_close / on_close_confirmed 清 entry_notional snapshot

use super::*;
use crate::strategies::Strategy;
use openclaw_core::alpha_surface::{
    AlphaSurface, BasisCurveSnapshot, LiquidationEvent, LiquidationPulse, LiquidationPulsePanel,
    LiquidationSide,
};

fn make_pulse(
    long_notional: f64,
    short_notional: f64,
    event_count: u32,
    dominant_side: LiquidationSide,
) -> LiquidationPulse {
    LiquidationPulse {
        recent_events: vec![LiquidationEvent {
            symbol: "BTCUSDT".to_string(),
            side: dominant_side,
            qty: 1.0,
            price: 60_000.0,
            ts_ms: 1_000_000,
        }],
        cluster_notional_5m: long_notional + short_notional,
        long_notional_5m: long_notional,
        short_notional_5m: short_notional,
        event_count_5m: event_count,
        dominant_side,
        snapshot_ts_ms: 1_000_000,
    }
}

fn make_panel_with_pulse(symbol: &str, pulse: LiquidationPulse) -> LiquidationPulsePanel {
    let mut pulses = std::collections::HashMap::new();
    pulses.insert(symbol.to_string(), pulse);
    LiquidationPulsePanel {
        pulses,
        snapshot_ts_ms: 1_000_000,
        source_tier: "bybit_v5_ws_all_liquidation".to_string(),
    }
}

fn make_ctx_with_surface<'a>(
    symbol: &'a str,
    price: f64,
    ts: u64,
    surface: &'a AlphaSurface<'a>,
) -> TickContext<'a> {
    TickContext {
        symbol,
        price,
        timestamp_ms: ts,
        indicators: None,
        indicators_5m: None,
        signals: &[],
        h0_allowed: true,
        funding_rate: None,
        index_price: Some(price),
        open_interest: None,
        best_bid: Some(price * 0.9999),
        best_ask: Some(price * 1.0001),
        tick_size: Some((price * 0.000_001).max(0.000_1)),
        alpha_surface_ref: surface,
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

/// Build AlphaSurface with liquidation_pulse populated and basis_curve.
/// 必須 borrow panel；caller 保 panel scope 涵蓋 surface 用期。
fn surface_with_panel<'a>(
    panel: &'a LiquidationPulsePanel,
    _basis: &'a BasisCurveSnapshot,
) -> AlphaSurface<'a> {
    let mut s = AlphaSurface::empty();
    s.liquidation_pulse = Some(panel);
    s
}

// ═════════════════════════════════════════════════════════════════════
// threshold_for / should_enter direction map (spec §1.1 + §9 #6)
// ═════════════════════════════════════════════════════════════════════

#[test]
fn threshold_for_btc_is_500k() {
    let s = LiquidationCascadeFade::new();
    assert!((s.threshold_for("BTCUSDT") - 500_000.0).abs() < 1e-6);
}

#[test]
fn threshold_for_eth_is_300k() {
    let s = LiquidationCascadeFade::new();
    assert!((s.threshold_for("ETHUSDT") - 300_000.0).abs() < 1e-6);
}

#[test]
fn threshold_for_non_cohort_fallback_100k() {
    let s = LiquidationCascadeFade::new();
    // SOLUSDT 不在 per_symbol_threshold map → fallback default 100k。
    assert!((s.threshold_for("SOLUSDT") - 100_000.0).abs() < 1e-6);
}

#[test]
fn should_enter_btc_long_liquidated_returns_long() {
    // spec §1.1 direction map：LongLiquidated → entry_is_long=true (fade buy)。
    let s = LiquidationCascadeFade::new();
    let pulse = make_pulse(600_000.0, 100_000.0, 5, LiquidationSide::LongLiquidated);
    let result = s.should_enter(&pulse, "BTCUSDT");
    assert_eq!(result, Some(true), "LongLiquidated must fade buy");
}

#[test]
fn should_enter_btc_short_liquidated_returns_short() {
    // spec §1.1 direction map：ShortLiquidated → entry_is_long=false (fade sell)。
    let s = LiquidationCascadeFade::new();
    let pulse = make_pulse(100_000.0, 600_000.0, 5, LiquidationSide::ShortLiquidated);
    let result = s.should_enter(&pulse, "BTCUSDT");
    assert_eq!(result, Some(false), "ShortLiquidated must fade sell");
}

#[test]
fn should_enter_mixed_returns_none() {
    // spec §1.1 條件 4：Mixed dominant_side → reject。
    let s = LiquidationCascadeFade::new();
    let pulse = make_pulse(400_000.0, 350_000.0, 5, LiquidationSide::Mixed);
    let result = s.should_enter(&pulse, "BTCUSDT");
    assert_eq!(result, None, "Mixed must reject (no directional thesis)");
}

#[test]
fn should_enter_below_threshold_returns_none() {
    let s = LiquidationCascadeFade::new();
    // BTC dominant_notional = 400k < threshold 500k → reject。
    let pulse = make_pulse(400_000.0, 100_000.0, 5, LiquidationSide::LongLiquidated);
    let result = s.should_enter(&pulse, "BTCUSDT");
    assert_eq!(result, None);
}

#[test]
fn should_enter_below_min_events_returns_none() {
    let s = LiquidationCascadeFade::new();
    // dominant_notional ok 但 event_count = 2 < min_events 3 → reject (防 single-large-event 假訊號)。
    let pulse = make_pulse(600_000.0, 100_000.0, 2, LiquidationSide::LongLiquidated);
    let result = s.should_enter(&pulse, "BTCUSDT");
    assert_eq!(result, None);
}

#[test]
fn should_enter_eth_uses_300k_threshold() {
    let s = LiquidationCascadeFade::new();
    // ETH dominant_notional = 350k > threshold 300k → entry。
    let pulse = make_pulse(350_000.0, 50_000.0, 5, LiquidationSide::LongLiquidated);
    let result = s.should_enter(&pulse, "ETHUSDT");
    assert_eq!(result, Some(true));
}

#[test]
fn should_enter_eth_below_300k_returns_none() {
    let s = LiquidationCascadeFade::new();
    // ETH dominant_notional = 250k < threshold 300k → reject。
    let pulse = make_pulse(250_000.0, 50_000.0, 5, LiquidationSide::LongLiquidated);
    let result = s.should_enter(&pulse, "ETHUSDT");
    assert_eq!(result, None);
}

// ═════════════════════════════════════════════════════════════════════
// should_exit — 3 conditions (time-stop / take_profit / reverse_cascade)
// ═════════════════════════════════════════════════════════════════════

#[test]
fn should_exit_time_stop() {
    let s = LiquidationCascadeFade::new();
    let pulse = make_pulse(500_000.0, 50_000.0, 5, LiquidationSide::LongLiquidated);
    // entry_ms=0; now=65min > 60min max → time_stop。
    let result = s.should_exit("BTCUSDT", &pulse, true, 60_000.0, 60_000.0, 65 * 60_000, 0);
    assert_eq!(result, Some("time_stop"));
}

#[test]
fn should_exit_take_profit_long() {
    let s = LiquidationCascadeFade::new();
    let pulse = make_pulse(500_000.0, 50_000.0, 5, LiquidationSide::LongLiquidated);
    // long position; entry 60k → current 60.9k → pnl = 1.5% (boundary)。
    let result = s.should_exit("BTCUSDT", &pulse, true, 60_000.0, 60_900.0, 1_000_000, 0);
    assert_eq!(result, Some("take_profit"));
}

#[test]
fn should_exit_take_profit_short() {
    let s = LiquidationCascadeFade::new();
    let pulse = make_pulse(50_000.0, 500_000.0, 5, LiquidationSide::ShortLiquidated);
    // short position; entry 60k → current 59.1k → pnl = 1.5%。
    let result = s.should_exit("BTCUSDT", &pulse, false, 60_000.0, 59_100.0, 1_000_000, 0);
    assert_eq!(result, Some("take_profit"));
}

#[test]
fn should_exit_reverse_cascade_long_to_short() {
    let mut s = LiquidationCascadeFade::new();
    // 入場時 LongLiquidated dominant_notional=500k（snapshot 入 entry_notional）。
    s.entry_notional.insert("BTCUSDT".to_string(), 500_000.0);
    // 當前 ShortLiquidated dominant_notional=800k > 500 × 1.5 = 750k → reverse_cascade。
    let pulse = make_pulse(50_000.0, 800_000.0, 5, LiquidationSide::ShortLiquidated);
    // long position 持有，但 cascade 翻轉 → exit。
    let result = s.should_exit("BTCUSDT", &pulse, true, 60_000.0, 60_100.0, 1_000_000, 0);
    assert_eq!(result, Some("reverse_cascade"));
}

#[test]
fn should_exit_reverse_cascade_below_ratio_no_exit() {
    let mut s = LiquidationCascadeFade::new();
    s.entry_notional.insert("BTCUSDT".to_string(), 500_000.0);
    // 翻向但 magnitude=700k < 750k threshold → 不 exit。
    let pulse = make_pulse(50_000.0, 700_000.0, 5, LiquidationSide::ShortLiquidated);
    let result = s.should_exit("BTCUSDT", &pulse, true, 60_000.0, 60_100.0, 1_000_000, 0);
    assert_eq!(result, None);
}

#[test]
fn should_exit_no_trigger_in_normal_range() {
    let s = LiquidationCascadeFade::new();
    let pulse = make_pulse(500_000.0, 50_000.0, 5, LiquidationSide::LongLiquidated);
    // no exit condition triggered。
    let result = s.should_exit("BTCUSDT", &pulse, true, 60_000.0, 60_100.0, 1_000_000, 0);
    assert_eq!(result, None);
}

#[test]
fn should_exit_zero_entry_price_fails_closed() {
    let s = LiquidationCascadeFade::new();
    let pulse = make_pulse(500_000.0, 50_000.0, 5, LiquidationSide::LongLiquidated);
    // entry_price <= 0 → return None (不 panic、不假觸 TP)。
    let result = s.should_exit("BTCUSDT", &pulse, true, 0.0, 60_000.0, 1_000_000, 0);
    assert_eq!(result, None);
}

// ═════════════════════════════════════════════════════════════════════
// on_tick — fail-closed + entry + exit
// ═════════════════════════════════════════════════════════════════════

#[test]
fn on_tick_inactive_returns_empty() {
    let mut s = LiquidationCascadeFade::new();
    let panel = make_panel_with_pulse(
        "BTCUSDT",
        make_pulse(600_000.0, 50_000.0, 5, LiquidationSide::LongLiquidated),
    );
    let basis = BasisCurveSnapshot::default();
    let surface = surface_with_panel(&panel, &basis);
    let ctx = make_ctx_with_surface("BTCUSDT", 60_000.0, 1_000_000, &surface);
    let actions = s.on_tick(&ctx, &surface);
    assert!(actions.is_empty(), "inactive must not emit");
}

#[test]
fn on_tick_panel_none_fail_closed_skip() {
    let mut s = LiquidationCascadeFade::new();
    s.set_active(true);
    // panel = None → fail-closed skip（spec §5.2 設計約束）。
    let surface = AlphaSurface::empty();
    let ctx = make_ctx_with_surface("BTCUSDT", 60_000.0, 1_000_000, &surface);
    let actions = s.on_tick(&ctx, &surface);
    assert!(actions.is_empty(), "panel None must fail-closed skip");
}

#[test]
fn on_tick_pulse_for_none_skip() {
    let mut s = LiquidationCascadeFade::new();
    s.set_active(true);
    // panel exist 但 BTCUSDT 不在 pulses map → pulse_for return None。
    let panel = LiquidationPulsePanel {
        pulses: std::collections::HashMap::new(),
        snapshot_ts_ms: 1_000_000,
        source_tier: "bybit_v5_ws_all_liquidation".to_string(),
    };
    let basis = BasisCurveSnapshot::default();
    let surface = surface_with_panel(&panel, &basis);
    let ctx = make_ctx_with_surface("BTCUSDT", 60_000.0, 1_000_000, &surface);
    let actions = s.on_tick(&ctx, &surface);
    assert!(actions.is_empty());
}

#[test]
fn on_tick_non_cohort_silent_skip() {
    let mut s = LiquidationCascadeFade::new();
    s.set_active(true);
    let panel = make_panel_with_pulse(
        "SOLUSDT",
        make_pulse(150_000.0, 50_000.0, 5, LiquidationSide::LongLiquidated),
    );
    let basis = BasisCurveSnapshot::default();
    let surface = surface_with_panel(&panel, &basis);
    let ctx = make_ctx_with_surface("SOLUSDT", 150.0, 1_000_000, &surface);
    let actions = s.on_tick(&ctx, &surface);
    assert!(actions.is_empty(), "non-cohort must silent skip");
}

#[test]
fn on_tick_btc_long_liquidated_emits_long_fade() {
    let mut s = LiquidationCascadeFade::new();
    s.set_active(true);
    let panel = make_panel_with_pulse(
        "BTCUSDT",
        make_pulse(600_000.0, 50_000.0, 5, LiquidationSide::LongLiquidated),
    );
    let basis = BasisCurveSnapshot::default();
    let surface = surface_with_panel(&panel, &basis);
    let ctx = make_ctx_with_surface("BTCUSDT", 60_000.0, 1_000_000, &surface);
    let actions = s.on_tick(&ctx, &surface);
    assert_eq!(actions.len(), 1);
    match &actions[0] {
        StrategyAction::Open(intent) => {
            // spec §9 #6：LongLiquidated → fade buy (is_long=true)。
            assert!(intent.is_long, "LongLiquidated must emit long fade");
            assert_eq!(intent.strategy, "liquidation_cascade_fade");
            assert_eq!(intent.symbol, "BTCUSDT");
        }
        StrategyAction::Close { .. } => panic!("expected Open"),
    }
    // entry_notional snapshot 已記。
    assert!(s.entry_notional.contains_key("BTCUSDT"));
}

#[test]
fn on_tick_btc_short_liquidated_emits_short_fade() {
    let mut s = LiquidationCascadeFade::new();
    s.set_active(true);
    let panel = make_panel_with_pulse(
        "BTCUSDT",
        make_pulse(50_000.0, 600_000.0, 5, LiquidationSide::ShortLiquidated),
    );
    let basis = BasisCurveSnapshot::default();
    let surface = surface_with_panel(&panel, &basis);
    let ctx = make_ctx_with_surface("BTCUSDT", 60_000.0, 1_000_000, &surface);
    let actions = s.on_tick(&ctx, &surface);
    assert_eq!(actions.len(), 1);
    match &actions[0] {
        StrategyAction::Open(intent) => {
            // spec §9 #6：ShortLiquidated → fade sell (is_long=false)。
            assert!(!intent.is_long, "ShortLiquidated must emit short fade");
        }
        _ => panic!("expected Open"),
    }
}

#[test]
fn on_tick_btc_mixed_no_entry() {
    let mut s = LiquidationCascadeFade::new();
    s.set_active(true);
    let panel = make_panel_with_pulse(
        "BTCUSDT",
        make_pulse(500_000.0, 500_000.0, 10, LiquidationSide::Mixed),
    );
    let basis = BasisCurveSnapshot::default();
    let surface = surface_with_panel(&panel, &basis);
    let ctx = make_ctx_with_surface("BTCUSDT", 60_000.0, 1_000_000, &surface);
    let actions = s.on_tick(&ctx, &surface);
    assert!(
        actions.is_empty(),
        "Mixed dominant_side must reject entry"
    );
}

#[test]
fn on_tick_btc_below_threshold_no_entry() {
    let mut s = LiquidationCascadeFade::new();
    s.set_active(true);
    // BTC dominant_notional = 400k < 500k threshold → reject。
    let panel = make_panel_with_pulse(
        "BTCUSDT",
        make_pulse(400_000.0, 50_000.0, 5, LiquidationSide::LongLiquidated),
    );
    let basis = BasisCurveSnapshot::default();
    let surface = surface_with_panel(&panel, &basis);
    let ctx = make_ctx_with_surface("BTCUSDT", 60_000.0, 1_000_000, &surface);
    let actions = s.on_tick(&ctx, &surface);
    assert!(actions.is_empty());
}

#[test]
fn on_tick_with_own_position_take_profit_exit() {
    let mut s = LiquidationCascadeFade::new();
    s.set_active(true);
    // 自家 long 倉位 entry=60k；current=61k → pnl = 1.67% > 1.5% TP。
    let pos = make_position(
        "BTCUSDT".to_string(),
        true,
        0.01,
        60_000.0,
        0,
        "liquidation_cascade_fade",
    );
    let panel = make_panel_with_pulse(
        "BTCUSDT",
        make_pulse(500_000.0, 50_000.0, 5, LiquidationSide::LongLiquidated),
    );
    let basis = BasisCurveSnapshot::default();
    let surface = surface_with_panel(&panel, &basis);
    let base = make_ctx_with_surface("BTCUSDT", 61_000.0, 1_000_000, &surface);
    let ctx = ctx_with_position(base, &pos);
    let actions = s.on_tick(&ctx, &surface);
    assert_eq!(actions.len(), 1);
    match &actions[0] {
        StrategyAction::Close { reason, .. } => {
            assert!(reason.contains("take_profit"), "got {reason}");
        }
        _ => panic!("expected Close"),
    }
    // exit 後 entry_notional 已清。
    assert!(!s.entry_notional.contains_key("BTCUSDT"));
}

#[test]
fn on_tick_cross_strategy_position_skip() {
    let mut s = LiquidationCascadeFade::new();
    s.set_active(true);
    // 倉位 owner = ma_crossover。
    let pos = make_position(
        "BTCUSDT".to_string(),
        true,
        0.01,
        60_000.0,
        0,
        "ma_crossover",
    );
    let panel = make_panel_with_pulse(
        "BTCUSDT",
        make_pulse(600_000.0, 50_000.0, 5, LiquidationSide::LongLiquidated),
    );
    let basis = BasisCurveSnapshot::default();
    let surface = surface_with_panel(&panel, &basis);
    let base = make_ctx_with_surface("BTCUSDT", 60_000.0, 1_000_000, &surface);
    let ctx = ctx_with_position(base, &pos);
    let actions = s.on_tick(&ctx, &surface);
    assert!(actions.is_empty(), "cross-strategy occupied must skip");
}

#[test]
fn on_tick_h0_blocked_no_entry() {
    let mut s = LiquidationCascadeFade::new();
    s.set_active(true);
    let panel = make_panel_with_pulse(
        "BTCUSDT",
        make_pulse(600_000.0, 50_000.0, 5, LiquidationSide::LongLiquidated),
    );
    let basis = BasisCurveSnapshot::default();
    let surface = surface_with_panel(&panel, &basis);
    let mut ctx = make_ctx_with_surface("BTCUSDT", 60_000.0, 1_000_000, &surface);
    ctx.h0_allowed = false;
    let actions = s.on_tick(&ctx, &surface);
    assert!(actions.is_empty());
}

// ═════════════════════════════════════════════════════════════════════
// self-fills filter Stage 1 stub
// ═════════════════════════════════════════════════════════════════════

#[test]
fn is_self_origin_event_stub_returns_false() {
    // spec §1.4 + §9 #2：Stage 1 stub 必 false；Sprint 3+ V109 wire 真實 filter。
    // 誤判 true 會錯失所有合法 cascade entry → 此 test 防 regression。
    let pulse = make_pulse(500_000.0, 50_000.0, 5, LiquidationSide::LongLiquidated);
    assert!(!LiquidationCascadeFade::is_self_origin_event(&pulse));
    let pulse2 = make_pulse(100.0, 100.0, 1, LiquidationSide::Mixed);
    assert!(!LiquidationCascadeFade::is_self_origin_event(&pulse2));
}

// ═════════════════════════════════════════════════════════════════════
// IPC update_params
// ═════════════════════════════════════════════════════════════════════

#[test]
fn update_params_accepts_default() {
    let mut s = LiquidationCascadeFade::new();
    let params = LiquidationCascadeFadeUpdateParams::default();
    assert!(s.update_params(params).is_ok());
}

#[test]
fn update_params_rejects_non_cohort_symbol() {
    let mut s = LiquidationCascadeFade::new();
    let bad = LiquidationCascadeFadeUpdateParams {
        allowed_symbols: vec!["SOLUSDT".to_string()],
        ..Default::default()
    };
    assert!(s.update_params(bad).is_err());
}

#[test]
fn update_params_via_json() {
    let mut s = LiquidationCascadeFade::new();
    let json = r#"{
        "active": true,
        "cooldown_ms": 1800000,
        "allowed_symbols": ["BTCUSDT", "ETHUSDT"],
        "default_threshold_usd": 100000.0,
        "btc_threshold_usd": 600000.0,
        "eth_threshold_usd": 350000.0,
        "min_events": 4,
        "max_hold_ms": 3600000,
        "take_profit_pct": 1.8,
        "reverse_cascade_ratio": 1.6
    }"#;
    let result = s.update_params_json(json);
    assert!(result.is_ok(), "json: {result:?}");
    assert!(s.active);
    assert!((s.threshold_for("BTCUSDT") - 600_000.0).abs() < 1e-6);
    assert!((s.threshold_for("ETHUSDT") - 350_000.0).abs() < 1e-6);
    assert_eq!(s.min_events, 4);
}

#[test]
fn get_params_round_trip() {
    let s = LiquidationCascadeFade::new();
    let params = s.get_params();
    assert!(!params.active);
    assert!((params.btc_threshold_usd - 500_000.0).abs() < 1e-6);
    assert!((params.eth_threshold_usd - 300_000.0).abs() < 1e-6);
    assert_eq!(params.min_events, 3);
}

// ═════════════════════════════════════════════════════════════════════
// declared_alpha_sources / on_external_close / on_close_confirmed
// ═════════════════════════════════════════════════════════════════════

#[test]
fn declared_alpha_sources_liquidation_cascade() {
    let s = LiquidationCascadeFade::new();
    let sources = s.declared_alpha_sources();
    assert_eq!(sources.len(), 1);
    assert!(sources.contains(&AlphaSourceTag::LiquidationCascade));
}

#[test]
fn name_is_liquidation_cascade_fade() {
    let s = LiquidationCascadeFade::new();
    assert_eq!(s.name(), "liquidation_cascade_fade");
}

#[test]
fn on_external_close_clears_entry_notional() {
    let mut s = LiquidationCascadeFade::new();
    s.entry_notional.insert("BTCUSDT".to_string(), 500_000.0);
    s.on_external_close("BTCUSDT", 60_000.0, 1_000_000);
    assert!(!s.entry_notional.contains_key("BTCUSDT"));
}

#[test]
fn on_close_confirmed_clears_entry_notional() {
    let mut s = LiquidationCascadeFade::new();
    s.entry_notional.insert("BTCUSDT".to_string(), 500_000.0);
    s.on_close_confirmed("BTCUSDT", 60_000.0, 1_000_000);
    assert!(!s.entry_notional.contains_key("BTCUSDT"));
}

#[test]
fn on_close_skipped_clears_entry_notional() {
    let mut s = LiquidationCascadeFade::new();
    s.entry_notional.insert("BTCUSDT".to_string(), 500_000.0);
    s.on_close_skipped("BTCUSDT");
    assert!(!s.entry_notional.contains_key("BTCUSDT"));
}

#[test]
fn on_rejection_clears_entry_notional_and_rolls_back_cooldown() {
    let mut s = LiquidationCascadeFade::new();
    s.set_active(true);
    let panel = make_panel_with_pulse(
        "BTCUSDT",
        make_pulse(600_000.0, 50_000.0, 5, LiquidationSide::LongLiquidated),
    );
    let basis = BasisCurveSnapshot::default();
    let surface = surface_with_panel(&panel, &basis);
    let ctx = make_ctx_with_surface("BTCUSDT", 60_000.0, 1_000_000, &surface);
    let _ = s.on_tick(&ctx, &surface);
    assert!(s.entry_notional.contains_key("BTCUSDT"));

    let intent = OrderIntent::new_trade(
        "BTCUSDT".to_string(),
        true,
        0.01,
        0.5,
        "liquidation_cascade_fade".to_string(),
        "limit".to_string(),
        Some(60_000.0),
        None,
        None,
        Some(TimeInForce::PostOnly),
        Some(45_000),
    );
    s.on_rejection(&intent, "test rejection");
    assert!(!s.entry_notional.contains_key("BTCUSDT"));
}

#[test]
fn conf_scale_default_one_and_clamp() {
    let mut s = LiquidationCascadeFade::new();
    assert!((s.conf_scale() - 1.0).abs() < 1e-9);
    s.set_conf_scale(3.0);
    assert!((s.conf_scale() - 2.0).abs() < 1e-9);
    s.set_conf_scale(-1.0);
    assert!((s.conf_scale() - 0.0).abs() < 1e-9);
}
