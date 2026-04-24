//! BB Breakout — P1-11 (2) DonchianMode + (3) BbBreakoutProfile regression tests.
//! BB 突破 — P1-11 (2) Donchian 模式 + (3) A/B profile 回歸測試。
//!
//! MODULE_NOTE (EN): Covers the P1-11 softening + variant-preset surface:
//!   - (2) `DonchianMode::{Hard, Score, Off}` semantics + hot-reload + score
//!     delta application + "missing donchian indicator" fallback.
//!   - (3) `BbBreakoutProfile::{Conservative, Balanced, Aggressive}` preset
//!     values + `for_profile(Balanced) == default()` invariant + validate pass.
//!   Split from `tests.rs` (696 LOC, near 800 soft warn) and `tests_oi.rs`
//!   (OI scope) to keep each sibling ≤ soft warn and topically coherent.
//! MODULE_NOTE (中): 涵蓋 P1-11 軟化 + variant 預設面：
//!   - (2) `DonchianMode::{Hard, Score, Off}` 語義 + 熱重載 + score delta 套用
//!     + donchian 指標缺值 fallback。
//!   - (3) `BbBreakoutProfile::{Conservative, Balanced, Aggressive}` 預設值 +
//!     `for_profile(Balanced) == default()` 不變量 + validate pass。
//!   從 `tests.rs`（696 LOC 近 800 soft warn）與 `tests_oi.rs`（OI scope）拆出，
//!   維持每 sibling ≤ soft warn 且主題一致。

use super::super::{Strategy, StrategyAction, StrategyParams};
use super::params::{BbBreakoutParams, BbBreakoutProfile, DonchianMode};
use super::BbBreakout;
use crate::tick_pipeline::TickContext;
use openclaw_core::indicators::{
    AdxResult, BollingerResult, DonchianResult, IndicatorSnapshot as IS,
};

/// Shared ctx builder for P1-11 tests: configurable price + Donchian bounds.
/// Price/upper/lower let each test drive breach / miss paths explicitly.
/// P1-11 測試共用 ctx 建構器：可調 price + Donchian 上下界以覆蓋突破/未突破路徑。
fn ctx_p1_11(
    bw: f64,
    pct_b: f64,
    vol: f64,
    ts: u64,
    price: f64,
    donchian_upper: f64,
    donchian_lower: f64,
) -> TickContext<'static> {
    let ind = Box::leak(Box::new(IS {
        bollinger: Some(BollingerResult {
            upper: 51000.0,
            middle: 50000.0,
            lower: 49000.0,
            bandwidth: bw,
            percent_b: pct_b,
        }),
        volume_ratio: Some(vol),
        adx: Some(AdxResult {
            adx: 30.0,
            plus_di: 25.0,
            minus_di: 15.0,
        }),
        rsi_14: Some(55.0),
        donchian: Some(DonchianResult {
            upper: donchian_upper,
            lower: donchian_lower,
            middle: (donchian_upper + donchian_lower) / 2.0,
            width: donchian_upper - donchian_lower,
        }),
        ..Default::default()
    }));
    TickContext {
        symbol: "BTC",
        price,
        timestamp_ms: ts,
        indicators: Some(ind),
        signals: &[],
        h0_allowed: true,
        funding_rate: None,
        index_price: None,
        open_interest: None,
    }
}

/// Squeeze-then-breakout common setup. Runs one tick at ts=0 with bandwidth
/// below squeeze_bw to register squeeze, then returns — caller follows up with
/// the expansion tick they want to exercise.
/// 壓縮後突破通用準備：先跑一個 tick 於 ts=0 以登記 squeeze，再由 caller 執行擴張 tick。
fn prime_squeeze(strat: &mut BbBreakout) {
    // Bandwidth 0.01 << default squeeze_bw=0.03; %B 0.5 neutral (no entry);
    // volume 1.0 < threshold 1.2 (safety — won't fire even if %B drifts).
    // bandwidth 0.01 遠低於 squeeze_bw=0.03；%B=0.5 中性不入場；vol=1.0 < 1.2。
    let _ = strat.on_tick(&ctx_p1_11(0.01, 0.5, 1.0, 0, 50_000.0, 50_500.0, 49_500.0));
}

// ═════════════════════════════════════════════════════════════════════════════
// (2) DonchianMode tests
// ═════════════════════════════════════════════════════════════════════════════

#[test]
fn test_donchian_mode_default_is_hard() {
    let p = BbBreakoutParams::default();
    assert_eq!(p.donchian_mode, DonchianMode::Hard);
    // Bit-identical baseline invariant: default must preserve pre-P1-11 behavior.
    // 基線 bit-identical 不變量：Default 必須保留 pre-P1-11 行為。
}

#[test]
fn test_donchian_mode_hard_rejects_long_below_upper() {
    let mut s = BbBreakout::new();
    assert_eq!(s.donchian_mode, DonchianMode::Hard); // baseline
    s.min_persistence_ms = 0; // disable persistence for unit tests
    prime_squeeze(&mut s);
    // Expansion tick: bandwidth 0.05 > expansion_bw 0.04, vol 1.5 > 1.2,
    // %B 1.1 → is_long. Price 50_400 < donchian_upper 50_500 → Hard rejects.
    // 擴張：bw=0.05 > 0.04、vol=1.5 > 1.2、%B=1.1 → is_long；price<upper 硬拒。
    let out = s.on_tick(&ctx_p1_11(0.05, 1.1, 1.5, 100_000, 50_400.0, 50_500.0, 49_500.0));
    assert!(out.is_empty(), "Hard mode must hard-reject when price < donchian.upper");
}

#[test]
fn test_donchian_mode_score_allows_entry_on_miss() {
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    // Flip to Score mode via update_params (exercises hot-reload path too).
    // 經 update_params 切 Score 模式，同時覆蓋熱重載路徑。
    let mut p = s.get_params();
    p.donchian_mode = DonchianMode::Score;
    // Make confluence non-gate so score delta only affects qty_pct, not gate.
    // confluence 不做門控，score delta 只動 qty_pct 不擋入場。
    p.confluence_as_gate = false;
    // Also disable persistence in the params struct so hot-reload doesn't
    // restore the default 60_000 ms min_persistence. Without this the test
    // asserts soft-gate emission but is silently blocked upstream.
    // update_params 也會覆寫 min_persistence_ms，需在 params 端一併關閉。
    p.min_persistence_ms = 0;
    s.update_params(p).expect("valid Score params");
    prime_squeeze(&mut s);
    // Same "miss" scenario as Hard test: price 50_400 < upper 50_500.
    // Expect Score mode to proceed to OrderIntent emission (not empty).
    // 同 Hard 測試的「未突破」情境：Score 應發 intent，不硬拒。
    let out = s.on_tick(&ctx_p1_11(0.05, 1.1, 1.5, 100_000, 50_400.0, 50_500.0, 49_500.0));
    let emitted = out.iter().any(|a| matches!(a, StrategyAction::Open(_)));
    assert!(emitted, "Score mode must soft-gate Donchian miss (expected intent emission)");
}

#[test]
fn test_donchian_mode_score_allows_entry_on_breach() {
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0;
    let mut p = s.get_params();
    p.donchian_mode = DonchianMode::Score;
    p.confluence_as_gate = false;
    p.min_persistence_ms = 0;
    s.update_params(p).expect("valid Score params");
    prime_squeeze(&mut s);
    // Breach scenario: price 50_600 > upper 50_500. Score mode applies +bonus
    // (doesn't affect emission gate under confluence_as_gate=false); entry fires.
    // 突破情境：price>upper，Score 加 +bonus（非門控），入場觸發。
    let out = s.on_tick(&ctx_p1_11(0.05, 1.1, 1.5, 100_000, 50_600.0, 50_500.0, 49_500.0));
    let emitted = out.iter().any(|a| matches!(a, StrategyAction::Open(_)));
    assert!(emitted, "Score mode must emit on Donchian breach");
}

#[test]
fn test_donchian_mode_off_skips_check_entirely() {
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0;
    let mut p = s.get_params();
    p.donchian_mode = DonchianMode::Off;
    p.confluence_as_gate = false;
    p.min_persistence_ms = 0;
    s.update_params(p).expect("valid Off params");
    prime_squeeze(&mut s);
    // Off mode: even price 50_400 (would Hard-reject) should pass through.
    // Off 模式：即使 price=50_400（Hard 會拒）也應放行。
    let out = s.on_tick(&ctx_p1_11(0.05, 1.1, 1.5, 100_000, 50_400.0, 50_500.0, 49_500.0));
    let emitted = out.iter().any(|a| matches!(a, StrategyAction::Open(_)));
    assert!(emitted, "Off mode must skip Donchian check and emit");
}

#[test]
fn test_donchian_score_bonus_hot_reload_roundtrip() {
    let mut s = BbBreakout::new();
    assert!((s.donchian_score_bonus - 0.15).abs() < 1e-9); // default
    let mut p = s.get_params();
    p.donchian_score_bonus = 0.30;
    p.donchian_mode = DonchianMode::Score;
    s.update_params(p).expect("valid params");
    let echoed = s.get_params();
    assert!((echoed.donchian_score_bonus - 0.30).abs() < 1e-9);
    assert_eq!(echoed.donchian_mode, DonchianMode::Score);
}

#[test]
fn test_donchian_score_bonus_validate_bounds() {
    let mut p = BbBreakoutParams::default();
    p.donchian_score_bonus = 0.6; // > 0.5 cap
    assert!(p.validate().is_err());
    let mut p2 = BbBreakoutParams::default();
    p2.donchian_score_bonus = -0.01; // < 0.0
    assert!(p2.validate().is_err());
    let mut p3 = BbBreakoutParams::default();
    p3.donchian_score_bonus = f64::NAN;
    assert!(p3.validate().is_err());
    let mut p4 = BbBreakoutParams::default();
    p4.donchian_score_bonus = 0.5; // boundary OK
    assert!(p4.validate().is_ok());
}

// ═════════════════════════════════════════════════════════════════════════════
// (3) BbBreakoutProfile tests
// ═════════════════════════════════════════════════════════════════════════════

#[test]
fn test_profile_balanced_equals_default() {
    // Critical invariant: Balanced preset must be bit-identical to Default,
    // so existing production behaviour is preserved when profile wiring lands.
    // 關鍵不變量：Balanced 必須與 Default bit-identical，落地時保留生產行為。
    let bal = BbBreakoutParams::for_profile(BbBreakoutProfile::Balanced);
    let def = BbBreakoutParams::default();
    assert!((bal.squeeze_bw - def.squeeze_bw).abs() < 1e-9);
    assert!((bal.expansion_bw - def.expansion_bw).abs() < 1e-9);
    assert!((bal.volume_threshold - def.volume_threshold).abs() < 1e-9);
    assert_eq!(bal.min_persistence_ms, def.min_persistence_ms);
    assert_eq!(bal.donchian_mode, def.donchian_mode);
    assert!((bal.donchian_score_bonus - def.donchian_score_bonus).abs() < 1e-9);
}

#[test]
fn test_profile_conservative_is_tighter() {
    let cons = BbBreakoutParams::for_profile(BbBreakoutProfile::Conservative);
    let bal = BbBreakoutParams::for_profile(BbBreakoutProfile::Balanced);
    // Conservative must be stricter across all 4 gate dimensions.
    // Conservative 四個門控維度都必須更嚴。
    assert!(cons.squeeze_bw < bal.squeeze_bw, "tighter squeeze");
    assert!(cons.expansion_bw > bal.expansion_bw, "wider expansion gap");
    assert!(cons.volume_threshold > bal.volume_threshold, "higher volume bar");
    assert!(cons.min_persistence_ms > bal.min_persistence_ms, "longer persistence");
    assert!(cons.validate().is_ok());
}

#[test]
fn test_profile_aggressive_is_looser() {
    let agg = BbBreakoutParams::for_profile(BbBreakoutProfile::Aggressive);
    let bal = BbBreakoutParams::for_profile(BbBreakoutProfile::Balanced);
    // Aggressive must be looser across all 4 gate dimensions.
    // Aggressive 四個門控維度都必須更鬆。
    assert!(agg.squeeze_bw > bal.squeeze_bw, "looser squeeze");
    assert!(agg.expansion_bw <= bal.expansion_bw, "narrower/equal expansion gap");
    assert!(agg.volume_threshold < bal.volume_threshold, "lower volume bar");
    assert!(agg.min_persistence_ms < bal.min_persistence_ms, "shorter persistence");
    // Critical: must still pass validate (squeeze_bw < expansion_bw + vol >= 1.0).
    // 關鍵：仍須通過 validate（squeeze_bw < expansion_bw 且 vol >= 1.0）。
    assert!(agg.validate().is_ok(), "Aggressive params must still validate");
}

#[test]
fn test_profile_all_variants_validate_ok() {
    for profile in [
        BbBreakoutProfile::Conservative,
        BbBreakoutProfile::Balanced,
        BbBreakoutProfile::Aggressive,
    ] {
        let p = BbBreakoutParams::for_profile(profile);
        assert!(
            p.validate().is_ok(),
            "profile {:?} must pass validate (squeeze<expansion invariant + vol>=1.0)",
            profile
        );
    }
}

#[test]
fn test_profile_round_trip_via_update_params() {
    // Operator workflow: pick Aggressive preset, feed through hot-reload,
    // verify the strategy picks up the new thresholds.
    // Operator 流程：選 Aggressive 預設 → 熱重載 → 驗策略接收新閾值。
    let mut s = BbBreakout::new();
    let agg = BbBreakoutParams::for_profile(BbBreakoutProfile::Aggressive);
    s.update_params(agg.clone()).expect("aggressive profile applies");
    let echoed = s.get_params();
    assert!((echoed.squeeze_bw - agg.squeeze_bw).abs() < 1e-9);
    assert!((echoed.expansion_bw - agg.expansion_bw).abs() < 1e-9);
    assert!((echoed.volume_threshold - agg.volume_threshold).abs() < 1e-9);
    assert_eq!(echoed.min_persistence_ms, agg.min_persistence_ms);
}

// ═════════════════════════════════════════════════════════════════════════════
// Serde / enum surface
// ═════════════════════════════════════════════════════════════════════════════

#[test]
fn test_donchian_mode_serde_snake_case() {
    // TOML / JSON consumers must be able to spell the enum variants in
    // snake_case (per `#[serde(rename_all = "snake_case")]`).
    // TOML / JSON 端必須能以 snake_case 寫 enum 變體。
    let json_hard = serde_json::to_string(&DonchianMode::Hard).unwrap();
    assert_eq!(json_hard, "\"hard\"");
    let json_score = serde_json::to_string(&DonchianMode::Score).unwrap();
    assert_eq!(json_score, "\"score\"");
    let json_off = serde_json::to_string(&DonchianMode::Off).unwrap();
    assert_eq!(json_off, "\"off\"");
    // Round-trip.
    let back: DonchianMode = serde_json::from_str("\"score\"").unwrap();
    assert_eq!(back, DonchianMode::Score);
}

#[test]
fn test_profile_serde_snake_case() {
    let json_cons = serde_json::to_string(&BbBreakoutProfile::Conservative).unwrap();
    assert_eq!(json_cons, "\"conservative\"");
    let json_agg = serde_json::to_string(&BbBreakoutProfile::Aggressive).unwrap();
    assert_eq!(json_agg, "\"aggressive\"");
    let back: BbBreakoutProfile = serde_json::from_str("\"balanced\"").unwrap();
    assert_eq!(back, BbBreakoutProfile::Balanced);
}

// ═════════════════════════════════════════════════════════════════════════════
// FIX-26-DEADLOCK-1 (2026-04-24): expiry-based auto-clear of squeeze_detected_ms.
// See mod.rs comment above the clear block for full RCA.
// ═════════════════════════════════════════════════════════════════════════════

#[test]
fn test_fix26_deadlock_expiry_clears_stale_squeeze() {
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0;
    // Default squeeze_bw=0.03, expansion_bw=0.04, squeeze_expiry_ms=2_700_000.
    // Bar 1 at ts=0: bw=0.01 < 0.03 → register squeeze.
    // 默認 squeeze_bw=0.03；bw=0.01 觸發 squeeze 記錄。
    let _ = s.on_tick(&ctx_p1_11(0.01, 0.5, 1.0, 0, 50_000.0, 50_500.0, 49_500.0));
    assert!(
        s.has_squeeze("BTC"),
        "after first squeeze bar, squeeze_detected_ms must be set"
    );
    // Fast-forward past expiry with bw=0.035 (between squeeze_bw 0.03 and
    // expansion_bw 0.04): above squeeze threshold so NO new recording; below
    // expansion so no entry. Before the fix: squeeze_detected_ms stuck at 0
    // forever. After the fix: auto-cleared on this post-expiry tick.
    // 超過 expiry + bw=0.035（squeeze 0.03 與 expansion 0.04 之間）：無新記錄亦無入場；
    // 修前永遠卡 0，修後本 tick 即清。
    let _ = s.on_tick(&ctx_p1_11(0.035, 0.5, 1.0, 2_800_000, 50_000.0, 50_500.0, 49_500.0));
    assert!(
        !s.has_squeeze("BTC"),
        "post-expiry tick must auto-clear stale squeeze_detected_ms (FIX-26-DEADLOCK-1)"
    );
}

#[test]
fn test_fix26_deadlock_active_squeeze_preserved() {
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0;
    // Register squeeze at ts=0, then tick at ts=1_000_000 (< 2_700_000 expiry).
    // Inside the expiry window, the record must NOT be cleared — that's the
    // original FIX-26 "record first detection, don't reset" invariant.
    // 未過期窗口內，squeeze_detected_ms 必須保留（原 FIX-26 不變量）。
    let _ = s.on_tick(&ctx_p1_11(0.01, 0.5, 1.0, 0, 50_000.0, 50_500.0, 49_500.0));
    assert!(s.has_squeeze("BTC"));
    let _ = s.on_tick(&ctx_p1_11(0.02, 0.5, 1.0, 1_000_000, 50_000.0, 50_500.0, 49_500.0));
    assert!(
        s.has_squeeze("BTC"),
        "within-expiry tick must not clear (FIX-26 first-detection invariant preserved)"
    );
}

#[test]
fn test_fix26_deadlock_re_registration_after_clear() {
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0;
    // Register at ts=0, post-expiry non-squeeze tick at ts=2_800_000 clears,
    // then a fresh squeeze at ts=3_000_000 must re-register. Pre-fix: blocked
    // by is_none()=false forever.
    // bw=0.035 on clear tick (above squeeze 0.03); bw=0.01 on re-register.
    // 首登 ts=0；ts=2_800_000 bw=0.035 過期+非 squeeze tick 清除；ts=3_000_000 bw=0.01
    // 新 squeeze 必須能重登記（修前被永久鎖住）。
    let _ = s.on_tick(&ctx_p1_11(0.01, 0.5, 1.0, 0, 50_000.0, 50_500.0, 49_500.0));
    let _ = s.on_tick(&ctx_p1_11(0.035, 0.5, 1.0, 2_800_000, 50_000.0, 50_500.0, 49_500.0));
    assert!(!s.has_squeeze("BTC"), "cleared after expiry");
    let _ = s.on_tick(&ctx_p1_11(0.01, 0.5, 1.0, 3_000_000, 50_000.0, 50_500.0, 49_500.0));
    assert!(
        s.has_squeeze("BTC"),
        "fresh squeeze at ts=3M must re-register after the stale record was cleared"
    );
}
