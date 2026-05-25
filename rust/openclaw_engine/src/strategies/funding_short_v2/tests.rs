//! Sprint 2 Alpha Tournament Candidate #1 — funding_short_v2 unit tests。
//! 範圍：
//!   - annualized_funding / compute_basis_pct / compute_edge 純函式對齊 spec §1.3
//!   - should_enter / should_exit 5+4 條件各自獨立觸發
//!   - hard short-side enforcement (negative funding hard reject; cross-language fixture)
//!   - cohort gate (BTCUSDT / ETHUSDT 入場；SOLUSDT silent skip)
//!   - exit branch (4 條件)
//!   - cross-strategy occupied → skip entry
//!   - rejection rollback (cooldown 還原)
//!   - update_params validate floor enforce (IPC 不可降至 break-even)

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

// ═════════════════════════════════════════════════════════════════════
// Pure helpers / 純函數
// ═════════════════════════════════════════════════════════════════════

#[test]
fn annualized_funding_30pct_threshold() {
    // 8h funding = 0.000274 → annualized = 0.000274 × 1095 ≈ 0.3000
    // 對應 spec §1.1 條件 1 break-even 邊界。
    let a = FundingShortV2::annualized_funding(0.000274);
    assert!((a - 0.30003).abs() < 1e-4, "got {a}");
}

#[test]
fn annualized_funding_60pct_high() {
    // 8h funding = 0.000548 → annualized ≈ 60%（高 conviction）。
    let a = FundingShortV2::annualized_funding(0.000548);
    assert!((a - 0.6).abs() < 1e-3, "got {a}");
}

#[test]
fn annualized_funding_negative_returns_negative() {
    // 負 funding → 負 annualized；short-only should_enter 必 reject。
    let a = FundingShortV2::annualized_funding(-0.0003);
    assert!(a < 0.0);
}

#[test]
fn compute_basis_pct_normal() {
    // perp=60300, index=60000 → basis = |60300/60000 - 1| × 100 = 0.5%
    let bp = FundingShortV2::compute_basis_pct(60300.0, Some(60000.0));
    assert!((bp - 0.5).abs() < 0.01);
}

#[test]
fn compute_basis_pct_no_index_fail_closed() {
    // None → f64::MAX fail-closed signal（entry/exit gate 必跳過）。
    let bp = FundingShortV2::compute_basis_pct(60000.0, None);
    assert_eq!(bp, f64::MAX);
}

#[test]
fn compute_basis_pct_zero_index_fail_closed() {
    let bp = FundingShortV2::compute_basis_pct(60000.0, Some(0.0));
    assert_eq!(bp, f64::MAX);
}

#[test]
fn compute_edge_positive_at_high_funding() {
    let s = FundingShortV2::new();
    // funding = 0.0005 (≈ 55% annualized)；total_cost=22, expected_periods=1.5
    // amortized_cost = 22/10000/1.5 ≈ 0.001467
    // edge = 0.0005 - 0.001467 ≈ -0.000967 < 0 (因為 0.0005 < amortized_cost)
    // 提高 funding 到 0.002（~220% annualized）
    let edge = s.compute_edge(0.002);
    assert!(edge > 0.0, "expected positive edge, got {edge}");
}

#[test]
fn compute_edge_negative_below_break_even() {
    let s = FundingShortV2::new();
    // funding = 0.0001 → 11% annualized < 30% threshold；edge 必負。
    let edge = s.compute_edge(0.0001);
    assert!(edge < 0.0);
}

// ═════════════════════════════════════════════════════════════════════
// should_enter — 5 conditions + hard side enforcement
// ═════════════════════════════════════════════════════════════════════

#[test]
fn should_enter_pass_high_funding_low_basis() {
    let s = FundingShortV2::new();
    // funding = 0.002（~220% annualized > 30%）+ basis 0.2% < 0.3% gate。
    assert!(s.should_enter(0.002, 0.2));
}

#[test]
fn should_enter_reject_funding_below_threshold() {
    let s = FundingShortV2::new();
    // funding = 0.0002（~22% annualized < 30%）→ reject。
    assert!(!s.should_enter(0.0002, 0.2));
}

#[test]
fn should_enter_reject_negative_funding_hard_side_enforcement() {
    // spec §1.4 + §9 #1 對抗式 review focus：負 funding hard reject 不可轉 long。
    let s = FundingShortV2::new();
    // 即使絕對值滿足 30% (annualized -55%)，short-only hard reject。
    assert!(!s.should_enter(-0.0005, 0.2));
}

#[test]
fn should_enter_reject_basis_too_wide() {
    let s = FundingShortV2::new();
    // funding=0.002 滿足 + edge>0 + 但 basis=0.4% > entry_gate 0.5×0.6 = 0.3%
    assert!(!s.should_enter(0.002, 0.4));
}

#[test]
fn should_enter_reject_basis_at_entry_gate_boundary() {
    let s = FundingShortV2::new();
    // entry_basis_gate = 0.5 × 0.6 = 0.3；basis=0.3 邊界值 → not less-than → reject。
    assert!(!s.should_enter(0.002, 0.3));
}

// ═════════════════════════════════════════════════════════════════════
// should_exit — 4 conditions OR
// ═════════════════════════════════════════════════════════════════════

#[test]
fn should_exit_funding_collapse_below_exit_gate() {
    let s = FundingShortV2::new();
    // annualized = 0.00003 × 1095 ≈ 3.3% < funding_exit_annualized 5%
    assert!(s.should_exit(0.00003, 0.1, 1_000_000, 0));
}

#[test]
fn should_exit_funding_flip_to_negative() {
    let s = FundingShortV2::new();
    // funding 翻負 → exit。
    assert!(s.should_exit(-0.0001, 0.1, 1_000_000, 0));
}

#[test]
fn should_exit_basis_blowout() {
    let s = FundingShortV2::new();
    // funding ok (0.002 ≈ 220% annualized) + edge > 0 + basis = 0.6% > 0.5% max。
    assert!(s.should_exit(0.002, 0.6, 1_000_000, 0));
}

#[test]
fn should_exit_time_stop() {
    let s = FundingShortV2::new();
    // funding + basis 全 ok；但 hold = 25h > 24h max。
    assert!(s.should_exit(0.002, 0.2, 25 * 3_600_000, 0));
}

#[test]
fn should_exit_no_trigger_in_normal_range() {
    let s = FundingShortV2::new();
    // funding ok + basis ok + hold < max。
    assert!(!s.should_exit(0.002, 0.2, 1_000_000, 0));
}

// ═════════════════════════════════════════════════════════════════════
// on_tick — entry / exit / cross-strategy
// ═════════════════════════════════════════════════════════════════════

#[test]
fn on_tick_inactive_returns_empty() {
    let mut s = FundingShortV2::new();
    // default active=false → 必 no-op。
    let ctx = make_ctx("BTCUSDT", 60_000.0, 0, Some(0.002), Some(60_000.0));
    let actions = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert!(actions.is_empty(), "inactive strategy must not emit");
}

#[test]
fn on_tick_non_cohort_symbol_silent_skip() {
    let mut s = FundingShortV2::new();
    s.set_active(true);
    // SOLUSDT 非 cohort → silent skip。
    let ctx = make_ctx("SOLUSDT", 150.0, 0, Some(0.002), Some(150.0));
    let actions = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert!(actions.is_empty());
}

#[test]
fn on_tick_btc_high_funding_emits_short_entry() {
    let mut s = FundingShortV2::new();
    s.set_active(true);
    // BTCUSDT funding=0.002 (~220% annualized) + basis=0.05%。
    let ctx = make_ctx("BTCUSDT", 60_000.0, 1_000_000, Some(0.002), Some(60_000.0));
    let actions = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(actions.len(), 1, "expected 1 Open intent");
    match &actions[0] {
        StrategyAction::Open(intent) => {
            // hard side enforcement: is_long 必 false。
            assert!(!intent.is_long, "funding_short_v2 must always emit short");
            assert_eq!(intent.strategy, "funding_short_v2");
            assert_eq!(intent.symbol, "BTCUSDT");
            // sentinel qty 1e9 → IntentProcessor Kelly sizing。
            assert!(intent.qty >= 1.0);
        }
        StrategyAction::Close { .. } => panic!("expected Open, got Close"),
    }
}

#[test]
fn on_tick_btc_negative_funding_does_not_emit_long() {
    // spec §1.4 + §9 #1 對抗式 review focus 真實 on_tick path：
    // 即使 |funding| 達 threshold 也不可轉 long。
    let mut s = FundingShortV2::new();
    s.set_active(true);
    let ctx = make_ctx("BTCUSDT", 60_000.0, 1_000_000, Some(-0.002), Some(60_000.0));
    let actions = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert!(
        actions.is_empty(),
        "negative funding must never emit (no long entry)"
    );
}

#[test]
fn on_tick_with_own_position_exit_branch_on_funding_collapse() {
    let mut s = FundingShortV2::new();
    s.set_active(true);
    let pos = make_position(
        "BTCUSDT".to_string(),
        false, // short position
        0.01,
        60_000.0,
        0,
        "funding_short_v2",
    );
    // funding 暴跌至 ~0.4% annualized < 5% exit gate。
    let base = make_ctx("BTCUSDT", 60_000.0, 1_000_000, Some(0.000004), Some(60_000.0));
    let ctx = ctx_with_position(base, &pos);
    let actions = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(actions.len(), 1);
    match &actions[0] {
        StrategyAction::Close { reason, symbol, .. } => {
            assert_eq!(symbol, "BTCUSDT");
            assert!(reason.contains("funding_short_v2_exit"), "got {reason}");
        }
        StrategyAction::Open(_) => panic!("expected Close, got Open"),
    }
}

#[test]
fn on_tick_with_own_position_time_stop_exit() {
    let mut s = FundingShortV2::new();
    s.set_active(true);
    let pos = make_position(
        "BTCUSDT".to_string(),
        false,
        0.01,
        60_000.0,
        0, // entry at t=0
        "funding_short_v2",
    );
    // funding 仍高 + basis 仍緊；但 now = 25h > 24h max → time-stop exit。
    let now = 25 * 3_600_000;
    let base = make_ctx("BTCUSDT", 60_000.0, now, Some(0.002), Some(60_000.0));
    let ctx = ctx_with_position(base, &pos);
    let actions = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(actions.len(), 1);
    match &actions[0] {
        StrategyAction::Close { reason, .. } => {
            assert!(reason.contains("funding_short_v2_exit"));
        }
        StrategyAction::Open(_) => panic!("expected Close"),
    }
}

#[test]
fn on_tick_cross_strategy_position_skip() {
    let mut s = FundingShortV2::new();
    s.set_active(true);
    // 倉位 owner = ma_crossover (cross-strategy occupied)。
    let pos = make_position(
        "BTCUSDT".to_string(),
        true,
        0.01,
        60_000.0,
        0,
        "ma_crossover",
    );
    let base = make_ctx("BTCUSDT", 60_000.0, 1_000_000, Some(0.002), Some(60_000.0));
    let ctx = ctx_with_position(base, &pos);
    let actions = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert!(
        actions.is_empty(),
        "cross-strategy occupied must skip entry without action"
    );
}

#[test]
fn on_tick_h0_blocked_no_entry() {
    let mut s = FundingShortV2::new();
    s.set_active(true);
    let mut ctx = make_ctx("BTCUSDT", 60_000.0, 1_000_000, Some(0.002), Some(60_000.0));
    ctx.h0_allowed = false;
    let actions = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert!(actions.is_empty());
}

#[test]
fn on_tick_funding_below_threshold_no_entry() {
    let mut s = FundingShortV2::new();
    s.set_active(true);
    // funding = 0.0002 (≈22% annualized < 30%)。
    let ctx = make_ctx("BTCUSDT", 60_000.0, 1_000_000, Some(0.0002), Some(60_000.0));
    let actions = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert!(actions.is_empty());
}

// ═════════════════════════════════════════════════════════════════════
// IPC update_params 路徑（floor enforce）
// ═════════════════════════════════════════════════════════════════════

#[test]
fn update_params_rejects_funding_threshold_below_floor() {
    // spec §9 #2 對抗式 review focus：IPC 不可降至 break-even 以下。
    let mut s = FundingShortV2::new();
    let bad_params = FundingShortV2UpdateParams {
        active: true,
        funding_threshold_annualized: 0.10, // < FUNDING_THRESHOLD_FLOOR 0.20
        ..Default::default()
    };
    let result = s.update_params(bad_params);
    assert!(result.is_err());
    let err = result.unwrap_err();
    assert!(err.contains("funding_threshold_annualized"), "err: {err}");
}

#[test]
fn update_params_accepts_default_30pct() {
    let mut s = FundingShortV2::new();
    let params = FundingShortV2UpdateParams::default();
    assert!(s.update_params(params).is_ok());
    assert!(!s.active, "default active=false should not change");
}

#[test]
fn update_params_via_json() {
    let mut s = FundingShortV2::new();
    let json = r#"{
        "active": true,
        "cooldown_ms": 28800000,
        "allowed_symbols": ["BTCUSDT", "ETHUSDT"],
        "funding_threshold_annualized": 0.35,
        "funding_exit_annualized": 0.05,
        "max_basis_pct": 0.5,
        "entry_basis_ratio": 0.6,
        "max_hold_ms": 86400000,
        "total_cost_bps": 22.0,
        "expected_periods": 1.5
    }"#;
    let result = s.update_params_json(json);
    assert!(result.is_ok(), "json: {result:?}");
    assert!(s.active);
    assert!((s.funding_threshold_annualized - 0.35).abs() < 1e-9);
}

#[test]
fn get_params_round_trip() {
    let s = FundingShortV2::new();
    let params = s.get_params();
    assert!(!params.active);
    assert!((params.funding_threshold_annualized - DEFAULT_FUNDING_THRESHOLD_ANNUALIZED).abs() < 1e-9);
    assert!((params.expected_periods - DEFAULT_EXPECTED_PERIODS).abs() < 1e-9);
}

#[test]
fn get_params_json_round_trip() {
    let s = FundingShortV2::new();
    let json = s.get_params_json();
    let parsed: FundingShortV2UpdateParams = serde_json::from_str(&json).unwrap();
    assert!(!parsed.active);
}

#[test]
fn param_ranges_json_has_funding_threshold() {
    let s = FundingShortV2::new();
    let json = s.param_ranges_json();
    let parsed: Vec<ParamRange> = serde_json::from_str(&json).unwrap();
    let names: Vec<&str> = parsed.iter().map(|r| r.name.as_str()).collect();
    assert!(names.contains(&"funding_threshold_annualized"));
}

// ═════════════════════════════════════════════════════════════════════
// declared_alpha_sources / cross-strategy contract
// ═════════════════════════════════════════════════════════════════════

#[test]
fn declared_alpha_sources_funding_skew_and_basis() {
    let s = FundingShortV2::new();
    let sources = s.declared_alpha_sources();
    assert_eq!(sources.len(), 2);
    assert!(sources.contains(&AlphaSourceTag::FundingSkew));
    assert!(sources.contains(&AlphaSourceTag::Basis));
}

#[test]
fn name_is_funding_short_v2() {
    let s = FundingShortV2::new();
    assert_eq!(s.name(), "funding_short_v2");
}

#[test]
fn conf_scale_default_one_and_clamp() {
    let mut s = FundingShortV2::new();
    assert!((s.conf_scale() - 1.0).abs() < 1e-9);
    // clamp [0, 2]。
    s.set_conf_scale(3.0);
    assert!((s.conf_scale() - 2.0).abs() < 1e-9);
    s.set_conf_scale(-1.0);
    assert!((s.conf_scale() - 0.0).abs() < 1e-9);
}

// ═════════════════════════════════════════════════════════════════════
// Rejection rollback
// ═════════════════════════════════════════════════════════════════════

#[test]
fn on_rejection_rolls_back_cooldown() {
    let mut s = FundingShortV2::new();
    s.set_active(true);
    let ctx = make_ctx("BTCUSDT", 60_000.0, 1_000_000, Some(0.002), Some(60_000.0));
    let _ = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    // 入場後 cooldown 已 set；模擬 rejection → 應 clear cooldown 回到 0（無紀錄）。
    let intent = OrderIntent::new_trade(
        "BTCUSDT".to_string(),
        false,
        0.01,
        0.5,
        "funding_short_v2".to_string(),
        "limit".to_string(),
        Some(60_000.0),
        None,
        None,
        Some(TimeInForce::PostOnly),
        Some(45_000),
    );
    s.on_rejection(&intent, "test rejection");
    // rollback 後 cooldown clear 回 0 → 立即可再入場 (cooldown 不 block)。
    assert!(s.cooldown.is_cooled_down("BTCUSDT", 1_001_000));
}

// ═════════════════════════════════════════════════════════════════════
// Hard side enforcement compile-time invariant guard
// ═════════════════════════════════════════════════════════════════════

#[test]
fn is_long_const_is_false() {
    // spec §9 #1 對抗式 review focus 編譯期 + 運行期 雙保險。
    // 此 assert 在 const 變動時會 fail，配合 grep 防止 v1 dormant 路徑重啟。
    assert!(!IS_LONG, "funding_short_v2 IS_LONG must always be false");
}
