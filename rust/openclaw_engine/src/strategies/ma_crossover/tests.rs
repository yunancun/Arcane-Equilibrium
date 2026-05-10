//! MaCrossover tests — entry/exit core + RC-01/02 filters + Phase 3a params.
//! MaCrossover 測試 — 入場/出場核心 + RC-01/02 過濾器 + Phase 3a 參數。
//!
//! MODULE_NOTE (EN): Split out of `strategies/ma_crossover.rs` by E5-P2-4c
//!   (2026-04-23). Covers: baseline entry/exit flows, RC-01 Hurst regime
//!   filter, RC-02 multi-timeframe confirmation, Phase 3a `StrategyParams`
//!   round-trip + JSON, confidence clamping, and G-SR-1 confluence param
//!   range/validation sanity checks. A1 (ER-scaled exit persistence) + A2
//!   (trend-adaptive cooldown) + EDGE-P2-3 PostOnly maker entry tests live in
//!   sibling file `tests_a1_a2_maker.rs`.
//! MODULE_NOTE (中)：E5-P2-4c（2026-04-23）由 `strategies/ma_crossover.rs` 拆出。
//!   涵蓋：基本入場/出場流程、RC-01 赫斯特狀態過濾、RC-02 多時間框架確認、
//!   Phase 3a `StrategyParams` 來回 + JSON、信心 clamp，以及 G-SR-1 匯流參數
//!   範圍/驗證檢查。A1（ER 縮放出場持續）+ A2（趨勢自適應冷卻）+ EDGE-P2-3
//!   PostOnly maker 入場測試在 sibling `tests_a1_a2_maker.rs`。

use super::*;
use crate::strategies::{Strategy, StrategyAction};
use crate::tick_pipeline::TickContext;
use openclaw_core::indicators::{AdxResult, AtrResult, HurstResult, IndicatorSnapshot, KamaResult};

// P-08: Test helpers use Box::leak for owned indicator data (fine for tests).

/// Helper: build a TickContext with given indicator values.
/// 輔助函數：用給定指標值構建 TickContext。
fn ctx_with(sma: f64, kama: f64, adx: f64, ts: u64) -> TickContext<'static> {
    let ind = Box::leak(Box::new(IndicatorSnapshot {
        sma_20: Some(sma),
        kama: Some(KamaResult {
            kama,
            efficiency_ratio: 0.5,
        }),
        adx: Some(AdxResult {
            adx,
            plus_di: 25.0,
            minus_di: 15.0,
        }),
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
    }
}

fn ctx_with_atr(sma: f64, kama: f64, adx: f64, ts: u64, atr: f64) -> TickContext<'static> {
    let ind = Box::leak(Box::new(IndicatorSnapshot {
        sma_20: Some(sma),
        kama: Some(KamaResult {
            kama,
            efficiency_ratio: 0.5,
        }),
        adx: Some(AdxResult {
            adx,
            plus_di: 25.0,
            minus_di: 15.0,
        }),
        atr_14: Some(AtrResult {
            atr,
            atr_percent: atr / 50000.0 * 100.0,
        }),
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
    }
}

/// Helper: build a TickContext with Hurst regime data.
/// 輔助函數：用赫斯特狀態數據構建 TickContext。
fn ctx_with_hurst(
    sma: f64,
    kama: f64,
    adx: f64,
    ts: u64,
    regime: &str,
    hurst_val: f64,
) -> TickContext<'static> {
    let ind = Box::leak(Box::new(IndicatorSnapshot {
        sma_20: Some(sma),
        kama: Some(KamaResult {
            kama,
            efficiency_ratio: 0.5,
        }),
        adx: Some(AdxResult {
            adx,
            plus_di: 25.0,
            minus_di: 15.0,
        }),
        hurst: Some(HurstResult {
            hurst: hurst_val,
            regime: regime.to_string(),
        }),
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
    }
}

/// Helper: build a TickContext with sma_50 for higher-TF testing.
/// 輔助函數：用 sma_50 構建 TickContext 以測試較高時間框架。
fn ctx_with_sma50(sma_20: f64, kama: f64, adx: f64, ts: u64, sma_50: f64) -> TickContext<'static> {
    let ind = Box::leak(Box::new(IndicatorSnapshot {
        sma_20: Some(sma_20),
        sma_50: Some(sma_50),
        kama: Some(KamaResult {
            kama,
            efficiency_ratio: 0.5,
        }),
        adx: Some(AdxResult {
            adx,
            plus_di: 25.0,
            minus_di: 15.0,
        }),
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
    }
}

// ═══════════════════════════════════════════════════════════════════════
// Existing tests (must still pass) / 原有測試（必須繼續通過）
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_no_signal_low_adx() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    assert!(s.on_tick(&ctx_with(100.0, 101.0, 15.0, 0), &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE).is_empty());
}

#[test]
fn test_long_entry() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    let i = s.on_tick(&ctx_with(100.0, 101.0, 25.0, 0), &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Open(intent) => assert!(intent.is_long),
        other => panic!("expected StrategyAction::Open, got {:?}", other),
    }
}

#[test]
fn test_min_trend_snr_blocks_noisy_entry() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    s.min_trend_snr = 1.0;

    let blocked = s.on_tick(&ctx_with_atr(100.0, 101.0, 25.0, 0, 2.0), &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert!(blocked.is_empty(), "SNR 0.5 must be blocked");

    let allowed = s.on_tick(&ctx_with_atr(100.0, 103.0, 25.0, 1_000, 2.0), &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(allowed.len(), 1, "SNR 1.5 must pass");
}

#[test]
fn test_exit_on_reverse() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    s.on_tick(&ctx_with(100.0, 101.0, 25.0, 0), &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    let i = s.on_tick(&ctx_with(101.0, 100.0, 25.0, 500_000), &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Close { symbol, reason, .. } => {
            assert_eq!(symbol, "BTC");
            assert_eq!(reason, "ma_reverse_cross");
        }
        other => panic!("expected StrategyAction::Close, got {:?}", other),
    }
}

// ═══════════════════════════════════════════════════════════════════════
// RC-01: Hurst regime filter tests / RC-01: 赫斯特狀態過濾測試
// ═══════════════════════════════════════════════════════════════════════

/// Entry blocked when Hurst regime is "mean_reverting" (H < 0.5).
/// 赫斯特狀態為「均值回歸」時阻擋入場。
#[test]
fn test_regime_filter_blocks_mean_reverting() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
                              // fast(kama=101) > slow(sma_20=100), ADX=25 → would normally enter long.
                              // 快線 > 慢線, ADX 足夠 → 正常情況會做多入場。
    let ctx = ctx_with_hurst(100.0, 101.0, 25.0, 0, "mean_reverting", 0.35);
    let intents = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert!(
        intents.is_empty(),
        "Entry must be blocked in mean_reverting regime"
    );
}

/// Entry allowed when Hurst regime is "trending" (H > 0.5).
/// 赫斯特狀態為「趨勢」時允許入場。
#[test]
fn test_regime_filter_allows_trending() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    let ctx = ctx_with_hurst(100.0, 101.0, 25.0, 0, "trending", 0.72);
    let intents = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(intents.len(), 1, "Entry must be allowed in trending regime");
    match &intents[0] {
        StrategyAction::Open(intent) => assert!(intent.is_long),
        other => panic!("expected StrategyAction::Open, got {:?}", other),
    }
}

/// Exit still works even in mean_reverting regime (position already open).
/// 即使在均值回歸狀態下，已持有的倉位仍可出場。
#[test]
fn test_regime_filter_allows_exit() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
                              // Step 1: Enter long in trending regime.
                              // 步驟 1：在趨勢狀態下做多入場。
    let ctx_entry = ctx_with_hurst(100.0, 101.0, 25.0, 0, "trending", 0.72);
    let entry = s.on_tick(&ctx_entry, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(entry.len(), 1, "Should enter long");

    // Step 2: Regime flips to mean_reverting, but crossover reverses → exit must work.
    // 步驟 2：狀態轉為均值回歸，但交叉反轉 → 出場必須有效。
    let ctx_exit = ctx_with_hurst(101.0, 100.0, 25.0, 500_000, "mean_reverting", 0.35);
    let exit = s.on_tick(&ctx_exit, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(
        exit.len(),
        1,
        "Exit must work even in mean_reverting regime"
    );
    match &exit[0] {
        StrategyAction::Close { reason, .. } => assert_eq!(reason, "ma_reverse_cross"),
        other => panic!("expected StrategyAction::Close, got {:?}", other),
    }
}

/// Entry blocked when Hurst regime is "random_walk".
/// 赫斯特狀態為「隨機漫步」時阻擋入場。
#[test]
fn test_regime_filter_blocks_random_walk() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    let ctx = ctx_with_hurst(100.0, 101.0, 25.0, 0, "random_walk", 0.50);
    let intents = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert!(
        intents.is_empty(),
        "Entry must be blocked in random_walk regime"
    );
}

/// Regime filter can be disabled via struct field.
/// 狀態過濾可通過結構體字段禁用。
#[test]
fn test_regime_filter_disabled() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    s.regime_filter_enabled = false;
    let ctx = ctx_with_hurst(100.0, 101.0, 25.0, 0, "mean_reverting", 0.35);
    let intents = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(
        intents.len(),
        1,
        "Entry allowed when regime filter is disabled"
    );
}

// ═══════════════════════════════════════════════════════════════════════
// RC-02: Multi-TF confirmation tests / RC-02: 多時間框架確認測試
// ═══════════════════════════════════════════════════════════════════════

/// Long entry blocked when higher-TF trend is bearish.
/// 較高時間框架趨勢看跌時阻擋做多入場。
#[test]
fn test_higher_tf_blocks_misaligned() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
                              // Warm up higher_tf_sma with a high value so sma_50 < higher_tf_sma → bearish trend.
                              // 用高值暖機 higher_tf_sma，使 sma_50 < higher_tf_sma → 看跌趨勢。
    s.higher_tf_sma.insert("BTC".into(), 110.0);
    // After one tick, higher_tf_sma ≈ 0.01*100 + 0.99*110 = 109.9, sma_50=100 < 109.9 → bearish.
    // 一個 tick 後，higher_tf_sma ≈ 109.9，sma_50=100 < 109.9 → 看跌。
    let ctx = ctx_with_sma50(100.0, 101.0, 25.0, 0, 100.0);
    let intents = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    // fast(101) > slow(100) → would want to go long, but higher TF is bearish → blocked.
    // 快線 > 慢線 → 想做多，但較高 TF 看跌 → 阻擋。
    assert!(
        intents.is_empty(),
        "Long entry must be blocked when higher TF is bearish"
    );
}

/// Long entry allowed when higher-TF trend is bullish.
/// 較高時間框架趨勢看漲時允許做多入場。
#[test]
fn test_higher_tf_allows_aligned() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
                              // Warm up higher_tf_sma with a low value so sma_50 > higher_tf_sma → bullish trend.
                              // 用低值暖機 higher_tf_sma，使 sma_50 > higher_tf_sma → 看漲趨勢。
    s.higher_tf_sma.insert("BTC".into(), 90.0);
    // After one tick, higher_tf_sma ≈ 0.01*100 + 0.99*90 = 90.1, sma_50=100 > 90.1 → bullish.
    // 一個 tick 後，higher_tf_sma ≈ 90.1，sma_50=100 > 90.1 → 看漲。
    let ctx = ctx_with_sma50(100.0, 101.0, 25.0, 0, 100.0);
    let intents = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(
        intents.len(),
        1,
        "Long entry must be allowed when higher TF is bullish"
    );
    match &intents[0] {
        StrategyAction::Open(intent) => assert!(intent.is_long),
        other => panic!("expected StrategyAction::Open, got {:?}", other),
    }
}

/// Short entry blocked when higher-TF trend is bullish.
/// 較高時間框架趨勢看漲時阻擋做空入場。
#[test]
fn test_higher_tf_blocks_short_when_bullish() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    s.higher_tf_sma.insert("BTC".into(), 90.0);
    // sma_50=100 > 90.1 → bullish → short blocked.
    let ctx = ctx_with_sma50(101.0, 100.0, 25.0, 0, 100.0);
    let intents = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert!(
        intents.is_empty(),
        "Short entry must be blocked when higher TF is bullish"
    );
}

/// Entry allowed when higher_tf_trend is None (cold start).
/// higher_tf_trend 為 None 時允許入場（冷啟動）。
#[test]
fn test_higher_tf_cold_start_allows_entry() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
                              // No sma_50 in context → higher_tf_trend stays None → entry allowed.
                              // 上下文中無 sma_50 → higher_tf_trend 保持 None → 允許入場。
    let ctx = ctx_with(100.0, 101.0, 25.0, 0);
    let intents = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(
        intents.len(),
        1,
        "Entry must be allowed during cold start (no higher TF data)"
    );
}

/// Exit works regardless of higher-TF trend direction.
/// 無論較高時間框架趨勢方向如何，出場均有效。
#[test]
fn test_higher_tf_does_not_block_exit() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
                              // Enter long with aligned higher TF.
    s.higher_tf_sma.insert("BTC".into(), 90.0);
    let ctx_entry = ctx_with_sma50(100.0, 101.0, 25.0, 0, 100.0);
    let entry = s.on_tick(&ctx_entry, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(entry.len(), 1);

    // Now flip higher TF to bearish and reverse crossover → exit must still work.
    // 現在將較高 TF 翻轉為看跌並反轉交叉 → 出場仍必須有效。
    s.higher_tf_sma.insert("BTC".into(), 110.0);
    s.higher_tf_trend.insert("BTC".into(), false);
    let ctx_exit = ctx_with_sma50(101.0, 100.0, 25.0, 500_000, 100.0);
    let exit = s.on_tick(&ctx_exit, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(
        exit.len(),
        1,
        "Exit must work regardless of higher TF trend"
    );
}

// ── Phase 3a: StrategyParams tests ──

#[test]
fn test_param_ranges_non_empty() {
    let ranges = MaCrossoverParams::param_ranges();
    assert!(!ranges.is_empty());
    assert!(ranges.iter().any(|r| r.name == "adx_threshold"));
}

#[test]
fn test_validate_pass() {
    let p = MaCrossoverParams::default();
    assert!(p.validate().is_ok());
}

#[test]
fn test_validate_fail() {
    let p = MaCrossoverParams {
        cooldown_ms: 1000,
        ..Default::default()
    }; // too low
    assert!(p.validate().is_err());
}

#[test]
fn test_update_and_get_roundtrip() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    let new_params = MaCrossoverParams {
        adx_threshold: 35.0,
        ..Default::default()
    };
    assert!(s.update_params(new_params).is_ok());
    let got = s.get_params();
    assert!((got.adx_threshold - 35.0).abs() < 1e-10);
}

#[test]
fn test_json_roundtrip() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    let json = r#"{"cooldown_ms":600000,"adx_threshold":25.0,"default_qty":1000000000.0,"regime_filter_enabled":true,"higher_tf_alpha":0.005}"#;
    assert!(s.update_params_json(json).is_ok());
    let out = s.get_params_json();
    assert!(out.contains("25.0") || out.contains("25"));
}

#[test]
fn test_conf_scale_clamps_to_range() {
    // CONF-D: set_conf_scale must clamp to [0, 2].
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    s.set_conf_scale(3.0);
    assert!((s.conf_scale() - 2.0).abs() < 1e-10);
    s.set_conf_scale(-1.0);
    assert!((s.conf_scale() - 0.0).abs() < 1e-10);
    s.set_conf_scale(1.5);
    assert!((s.conf_scale() - 1.5).abs() < 1e-10);
}

#[test]
fn test_conf_scale_applied_to_emit() {
    // CONF-D: emitted confidence == raw * conf_scale, clamped to [0, 1].
    use crate::tick_pipeline::TickContext;
    let ctx = TickContext {
        symbol: "BTCUSDT",
        price: 50000.0,
        timestamp_ms: 0,
        indicators: None,
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
    };
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    s.set_conf_scale(0.5);
    let intent = s.make_intent(&ctx, true, 0.8).expect("market intent");
    assert!((intent.confidence - 0.4).abs() < 1e-10);

    s.set_conf_scale(2.0);
    let intent = s.make_intent(&ctx, true, 0.9).expect("market intent");
    assert!((intent.confidence - 1.0).abs() < 1e-10); // clamped
}

// ── G-SR-1 S3+S4: param_ranges + validation tests ──

#[test]
fn test_ma_param_ranges_count() {
    let ranges = MaCrossoverParams::param_ranges();
    // 5 original + 10 confluence + 1 A2 cooldown + 1 SNR gate = 17
    assert_eq!(
        ranges.len(),
        17,
        "expected 17 param ranges, got {}",
        ranges.len()
    );
}

#[test]
fn test_ma_param_ranges_confluence_names() {
    let ranges = MaCrossoverParams::param_ranges();
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
fn test_ma_param_ranges_agent_adjustable() {
    let ranges = MaCrossoverParams::param_ranges();
    // Weights should be agent_adjustable / 權重應可被 Agent 調整
    for name in &[
        "weight_adx",
        "weight_regime",
        "weight_volume",
        "weight_momentum",
    ] {
        let r = ranges.iter().find(|r| r.name == *name).unwrap();
        assert!(r.agent_adjustable, "{name} should be agent_adjustable");
    }
    // min_notional_usd should NOT be agent_adjustable
    let mn = ranges
        .iter()
        .find(|r| r.name == "min_notional_usd")
        .unwrap();
    assert!(
        !mn.agent_adjustable,
        "min_notional_usd should not be agent_adjustable"
    );
}

#[test]
fn test_ma_validate_default_ok() {
    assert!(MaCrossoverParams::default().validate().is_ok());
}

#[test]
fn test_ma_validate_bad_weight_sum() {
    let mut p = MaCrossoverParams::default();
    p.weight_adx = 30.0; // sum = 70 ≠ 65
    assert!(p.validate().is_err());
}

#[test]
fn test_ma_validate_bad_threshold_order() {
    let mut p = MaCrossoverParams::default();
    p.confluence_threshold_no_trade = 50.0;
    p.confluence_threshold_light = 45.0; // light < no_trade
    assert!(p.validate().is_err());
}

#[test]
fn test_ma_validate_bad_min_notional() {
    let mut p = MaCrossoverParams::default();
    p.min_notional_usd = 0.5; // < 1.0
    assert!(p.validate().is_err());
}

// ═══════════════════════════════════════════════════════════════════════════
// G7-03 Phase B regression — typed `RegimeLabel` migration
// G7-03 Phase B 回歸 — 切換為 typed RegimeLabel
// ═══════════════════════════════════════════════════════════════════════════
//
// Purpose: prove `regime_allows_entry` (helpers.rs) returns the same gate
// decision when the legacy `hr.regime == "trending"` compare is replaced by
// `from_legacy_str(&hr.regime) == RegimeLabel::Persistent`.

#[test]
fn test_phase_b_persistent_regime_allows_entry() {
    // Equivalent to `test_regime_filter_allows_trending` but framed as a
    // Phase B parity check — typed match must ACCEPT "trending" (Persistent).
    // 對齊 test_regime_filter_allows_trending；typed match 必須接受 trending。
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    let ctx = ctx_with_hurst(100.0, 101.0, 25.0, 0, "trending", 0.72);
    let intents = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(
        intents.len(),
        1,
        "Persistent regime (legacy 'trending') must allow entry"
    );
}

#[test]
fn test_phase_b_anti_persistent_regime_blocks_entry() {
    // `mean_reverting` → `from_legacy_str` → `AntiPersistent` ≠ `Persistent`,
    // so the gate must block entry. Same expectation as the legacy compare.
    // mean_reverting → AntiPersistent ≠ Persistent → 阻擋；對齊 legacy 行為。
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    let ctx = ctx_with_hurst(100.0, 101.0, 25.0, 0, "mean_reverting", 0.35);
    let intents = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert!(
        intents.is_empty(),
        "AntiPersistent regime (legacy 'mean_reverting') must block entry"
    );
}

#[test]
fn test_phase_b_random_regime_blocks_entry() {
    // Random regime → not Persistent → block. Same as
    // `test_regime_filter_blocks_random_walk` but framed as Phase B parity.
    // Random 不命中 Persistent → 阻擋；對齊 legacy。
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    let ctx = ctx_with_hurst(100.0, 101.0, 25.0, 0, "random_walk", 0.5);
    let intents = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert!(
        intents.is_empty(),
        "Random regime (legacy 'random_walk') must block entry"
    );
}

#[test]
fn test_phase_b_unknown_regime_string_blocks_entry() {
    // Defensive: unknown regime string → from_legacy_str → Random → block.
    // Pre-migration code's `hr.regime == "trending"` → false → block.
    // Same fail-safe behaviour preserved by the typed migration.
    // 未知字串 → Random → 阻擋；migration 保留 legacy fail-safe。
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    let ctx = ctx_with_hurst(100.0, 101.0, 25.0, 0, "totally_invalid_label", 0.5);
    let intents = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert!(
        intents.is_empty(),
        "Unknown regime string must map to non-Persistent and block entry"
    );
}

// ═══════════════════════════════════════════════════════════════════════════
// W7-3 Option B regression — on_rejection duplicate_position 1-tick defense
// W7-3 Option B 回歸 — on_rejection 對 duplicate_position 的 1-tick 防衛
// ═══════════════════════════════════════════════════════════════════════════
//
// 背景：PA audit `2026-05-10--p1_ma_crossover_duplicate_intent_audit.md`
// 揭露 ma_crossover 的 self.positions 不查 paper_state，當 grid_trading 在
// 同 symbol 先開倉，ma_crossover 每 tick 撞 router gate 1.5 duplicate_position
// 形成 hot loop（INXUSDT 11:34 一分鐘 2319 reject）。Option B 補丁讓
// on_rejection 識別 duplicate_position reason → 把 self.positions sync 成
// paper_state 真實方向，下個 tick 直接進 exit 分支終結 hot loop。
//
// 測試契約：
// - reason 格式由 rejection_coding.rs:147-152 定義
//   `"duplicate_position: {symbol} already {LONG|SHORT} {qty}"`
// - 4 case：already SHORT / already LONG / unknown format / non-duplicate

use crate::intent_processor::OrderIntent;

/// Helper：構建一筆模擬 OrderIntent 給 on_rejection 用。
/// W7-3 測試專用，所有欄位使用最小可行值。
fn make_test_intent(symbol: &str, is_long: bool) -> OrderIntent {
    OrderIntent {
        symbol: symbol.to_string(),
        is_long,
        qty: 1810.0,
        confidence: 0.5,
        strategy: "ma_crossover".to_string(),
        order_type: "market".to_string(),
        limit_price: None,
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
    }
}

/// W7-3 Option B：reason "duplicate_position ... already SHORT" 命中
/// → self.positions[symbol] sync 為 false（SHORT）。
/// 對應 PA audit INXUSDT 11:34 grid 已開 SHORT 1810 場景。
#[test]
fn test_on_rejection_duplicate_position_already_short_syncs_position() {
    let mut s = MaCrossover::new();
    let intent = make_test_intent("INXUSDT", true); // strategy 想開 LONG（被 reject）
    let reason = "duplicate_position: INXUSDT already SHORT 1810";

    // Pre-condition：模擬 entry path 已寫過 prev_position（None → 沒有舊倉位）
    s.prev_position
        .insert("INXUSDT".to_string(), None);

    s.on_rejection(&intent, reason);

    // 期望：self.positions[INXUSDT] = Some(false)（SHORT），不是被 RC-04 rollback 到 None。
    assert_eq!(
        s.positions.get("INXUSDT").copied(),
        Some(false),
        "duplicate_position already SHORT 必須 sync self.positions 為 false（SHORT）"
    );
}

/// W7-3 Option B：reason "duplicate_position ... already LONG" 命中
/// → self.positions[symbol] sync 為 true（LONG）。
#[test]
fn test_on_rejection_duplicate_position_already_long_syncs_position() {
    let mut s = MaCrossover::new();
    let intent = make_test_intent("BTCUSDT", false); // strategy 想開 SHORT（被 reject）
    let reason = "duplicate_position: BTCUSDT already LONG 0.5";

    s.prev_position.insert("BTCUSDT".to_string(), None);

    s.on_rejection(&intent, reason);

    assert_eq!(
        s.positions.get("BTCUSDT").copied(),
        Some(true),
        "duplicate_position already LONG 必須 sync self.positions 為 true（LONG）"
    );
}

/// W7-3 Option B：reason 含 "duplicate_position" 但無 "already LONG/SHORT" 子串
/// （字串契約 drift / future 改寫）→ fallback 走原 RC-04 rollback 路徑。
/// pre_position = Some(true)（LONG）→ rollback 後 positions 必為 LONG。
#[test]
fn test_on_rejection_unknown_duplicate_format_fallback_to_rollback() {
    let mut s = MaCrossover::new();
    let intent = make_test_intent("ETHUSDT", true);
    // 缺 "already LONG/SHORT" 子串 — 模擬 reason 字串契約破裂。
    let reason = "duplicate_position: ETHUSDT something_unparseable";

    // 模擬 entry path 寫過 prev_position = Some(true)（LONG），mutation 後 positions
    // 也是 LONG（不變）；現在 reject → fallback 走 RC-04，positions 仍應為 LONG。
    s.prev_position
        .insert("ETHUSDT".to_string(), Some(true));
    s.positions.insert("ETHUSDT".to_string(), true);

    s.on_rejection(&intent, reason);

    // Fallback rollback 把 positions 還原到 prev_position（Some(true)）。
    assert_eq!(
        s.positions.get("ETHUSDT").copied(),
        Some(true),
        "unknown duplicate_position format 必須 fallback 走 RC-04 prev_position rollback"
    );
}

/// W7-3 Option B：reason 不含 "duplicate_position"（其他類拒絕，例如 cost_gate / risk_gate）
/// → 必走原 RC-04 完整 rollback（positions + cooldown 都還原）。
/// pre-condition：prev_position = None（mutation 前未持倉）→ rollback 後 positions
/// 必須被 remove（不留下偽倉位）。
#[test]
fn test_on_rejection_non_duplicate_position_runs_full_rollback() {
    let mut s = MaCrossover::new();
    let intent = make_test_intent("SOLUSDT", true);
    let reason = "cost_gate(JS-demo): estimated=-12.50bps < 0 — blocked / 負估計阻擋";

    // 模擬 entry path mutation：prev_position = None（變更前未持倉），
    // mutation 後 positions = LONG，prev_last_trade_ms = 0（未交易過）。
    s.prev_position.insert("SOLUSDT".to_string(), None);
    s.positions.insert("SOLUSDT".to_string(), true);
    s.prev_last_trade_ms.insert("SOLUSDT".to_string(), 0);
    s.cooldown.record_signal("SOLUSDT", 100_000);

    s.on_rejection(&intent, reason);

    // Rollback：positions 必須被 remove（還原到 None）。
    assert!(
        !s.positions.contains_key("SOLUSDT"),
        "non-duplicate_position rejection 必須走 RC-04 把 positions 還原到 None"
    );
    // Cooldown 也應 clear（因 prev_last_trade_ms == 0 哨兵）。
    assert!(
        s.cooldown.last_ms("SOLUSDT").is_none(),
        "non-duplicate_position rejection 必須走 RC-04 把 cooldown 還原到未交易狀態"
    );
}

// ═══════════════════════════════════════════════════════════════════════════
// W7-2 Option A regression — cross-strategy paper_state pre-entry check
// W7-2 Option A 回歸 — entry path 起點查 ctx.position_state
// ═══════════════════════════════════════════════════════════════════════════
//
// 背景：PA #3 audit `2026-05-10--p1_ma_crossover_duplicate_intent_audit.md`
// §6 Option A 指出治本是「strategy 端 query paper_state」。Sprint N+1
// W7-1 trait skeleton (`c9fb0b8f`) 已把 `position_state: Option<&PaperPosition>`
// wire 到 TickContext，並由 step_4_5_dispatch.rs:287-289 per-strategy iteration
// 注入。本批 tests 驗證 ma_crossover.on_tick 在 entry path 起點查到
// ctx.position_state 後即 skip + sync self.positions 的契約：
//
// - test 1：position_state=Some(SHORT) + ma_crossover signal=LONG → 0 actions
// - test 2：position_state=None + valid signal → 1 entry intent（baseline regression）
// - test 3：exit path 不被新 check 影響（已持倉 → 走 Some 分支）
// - test 4：debug log 結構完整性（pure function check via internal state）
//
// W7-3 Option B 仍保留作 reason 字串契約 fallback（W7-4 §7 重點 3）。
//
// PaperPosition helper：模擬 paper_state.get_position 的回傳。

use crate::paper_state::PaperPosition;

/// W7-2 helper：構建一個 PaperPosition 模擬 paper_state 真實持倉。
/// 全欄位用最小可行值，僅 is_long 由參數決定。
fn make_paper_position(symbol: &str, is_long: bool) -> PaperPosition {
    PaperPosition {
        symbol: symbol.to_string(),
        is_long,
        qty: 1810.0,
        entry_price: 0.015,
        best_price: 0.015,
        entry_fee: 0.0,
        entry_ts_ms: 0,
        unrealized_pnl: 0.0,
        entry_context_id: String::new(),
        owner_strategy: "grid_trading".to_string(), // 模擬 grid 已開倉場景
        entry_notional: 1810.0 * 0.015,
        max_favorable_pnl_pct: 0.0,
        peak_reached_ts_ms: 0,
    }
}

/// W7-2 #1：ctx.position_state = Some(SHORT) + ma_crossover entry signal=LONG
/// → 必 0 actions（skip entry）+ self.positions 同步為 false（SHORT）。
/// 對應 INXUSDT 11:34 grid 已開 SHORT、ma_crossover 想 LONG 的真實場景。
#[test]
fn test_on_tick_skips_entry_when_paper_state_has_other_strategy_position() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    let pp = make_paper_position("BTC", false); // grid 已開 SHORT 1810
    let mut ctx = ctx_with(100.0, 101.0, 25.0, 0); // ma_crossover signal = LONG (fast > slow)
    ctx.position_state = Some(&pp);

    let intents = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);

    // 1. 必 0 intents（skip entry）。
    assert!(
        intents.is_empty(),
        "ctx.position_state present 必 skip entry，但發了 {} intents",
        intents.len()
    );
    // 2. self.positions 必同步為 paper_state.is_long（false = SHORT），下個 tick 走 exit 分支。
    assert_eq!(
        s.positions.get("BTC").copied(),
        Some(false),
        "skip 後必 sync self.positions 為 paper_state 真實方向（SHORT）"
    );
}

/// W7-2 #2：ctx.position_state = None + valid signal → 1 entry intent（baseline regression）。
/// 確認本檢查不誤殺正常 entry 路徑。
#[test]
fn test_on_tick_proceeds_entry_when_paper_state_is_none() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    let mut ctx = ctx_with(100.0, 101.0, 25.0, 0); // signal = LONG
    ctx.position_state = None; // 顯式 None；ctx_with 已 default None，這裡再強調契約。

    let intents = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);

    assert_eq!(intents.len(), 1, "ctx.position_state=None 時 valid signal 必發 entry");
    match &intents[0] {
        StrategyAction::Open(intent) => {
            assert!(intent.is_long, "expected LONG entry");
        }
        other => panic!("expected StrategyAction::Open, got {:?}", other),
    }
}

/// W7-2 #3：exit path 不被新 check 影響。
/// 已持有 LONG → reverse cross → 必走 Some(is_long) exit 分支（不過 None entry 分支即無 W7-2 check）。
/// 即使 ctx.position_state = Some(LONG)，因 self.positions 已是 LONG 直接走 Some(true) → exit。
#[test]
fn test_on_tick_exit_path_unchanged_by_w7_2_check() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    // Step 1：先入場 LONG（ctx.position_state=None，走正常 entry path）。
    let entry = s.on_tick(&ctx_with(100.0, 101.0, 25.0, 0), &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(entry.len(), 1, "Step 1 必入場 LONG");
    assert_eq!(s.positions.get("BTC").copied(), Some(true));

    // Step 2：reverse cross（fast < slow）+ ctx.position_state 即使 Some(LONG)，
    // 因 self.positions=Some(true) 直接走 Some(true) exit 分支（W7-2 check 在 None 分支內，不觸及）。
    let pp = make_paper_position("BTC", true);
    let mut ctx_exit = ctx_with(101.0, 100.0, 25.0, 500_000); // fast < slow → reverse
    ctx_exit.position_state = Some(&pp);
    let exit = s.on_tick(&ctx_exit, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);

    assert_eq!(exit.len(), 1, "exit path 必照走，不受 W7-2 check 影響");
    match &exit[0] {
        StrategyAction::Close { reason, .. } => {
            assert_eq!(reason, "ma_reverse_cross", "exit reason 必為 ma_reverse_cross");
        }
        other => panic!("expected StrategyAction::Close, got {:?}", other),
    }
}

/// W7-2 #4：debug log path + W7-2 sync 後 first tick 即 skip（hot loop 即時終結驗證）。
/// 對應 INXUSDT 11:34 場景：第一次撞到 cross-strategy desync 即立刻被 W7-2 skip + sync。
/// 不做 100-tick burst（second tick 會走 Some(is_long) exit 分支進入 KAMA reverse 邏輯，
/// 屬 exit-path 行為，與 W7-2 sync 契約無關）；改驗單 tick：（1）必 skip，（2）self.positions
/// 必同步 paper_state 方向，（3）self.positions size 為 1（O(1) HashMap insert 不累積）。
#[test]
fn test_on_tick_w7_2_logs_skip_reason_via_state_sync() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    let pp = make_paper_position("BTC", false); // grid SHORT
    let mut ctx = ctx_with(100.0, 101.0, 25.0, 0); // ma_crossover signal = LONG (fast > slow)
    ctx.position_state = Some(&pp);

    let intents = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);

    // (1) 必 0 intent — W7-2 skip path 觸發。
    assert!(
        intents.is_empty(),
        "first cross-strategy desync tick 必 W7-2 skip，但發了 {} intents",
        intents.len()
    );
    // (2) self.positions 必 sync 為 paper_state 真實方向（SHORT）— W7-2 contract。
    //     若 sync 失敗（仍 None），下個 tick 又走 entry path → hot loop 仍存在 → bug。
    assert_eq!(
        s.positions.get("BTC").copied(),
        Some(false),
        "W7-2 sync 後 self.positions 必反映 paper_state.is_long（SHORT）"
    );
    // (3) HashMap size = 1（O(1) insert，不洩漏多 entry）。
    assert_eq!(
        s.positions.len(),
        1,
        "W7-2 sync 必 O(1) insert，positions 應只有 1 entry"
    );
}

/// W7-3 Option B SLA：1000 次 on_rejection burst 不 panic / 不 hang / HashMap O(1) 更新。
/// 模擬 INXUSDT 11:34 hot loop 場景（單 symbol 一分鐘 reject 2319 次的縮量回放）。
/// 由 E4 W7-3 regression 加入，pure test scope，不修 business logic。
///
/// 驗證契約：
///  1. burst 完成不 panic（HashMap insert / contains / String 解析 robust）。
///  2. self.positions 在單 symbol 多次 sync 後保持 size=1（O(1) update 不累積）。
///  3. 終態 self.positions[symbol] 應為最後一次 reason 的 direction（這裡是 SHORT）。
///  4. wall-clock < 100ms（1000 op，mac_release 應 < 5ms；保留 100ms 防 CI 噪音）。
#[test]
fn test_on_rejection_duplicate_position_burst_no_panic_no_hang() {
    let mut s = MaCrossover::new();
    let intent = make_test_intent("INXUSDT", true);
    let reason = "duplicate_position: INXUSDT already SHORT 1810";

    let start = std::time::Instant::now();
    for _ in 0..1000 {
        s.on_rejection(&intent, reason);
    }
    let elapsed = start.elapsed();

    // 1. HashMap O(1) update：1000 次同 symbol 後仍只有 1 entry。
    assert_eq!(
        s.positions.len(),
        1,
        "1000 次同 symbol on_rejection 後 positions HashMap 應只有 1 entry (O(1) update 不累積)"
    );
    // 2. 終態正確：最後一次 sync 為 SHORT。
    assert_eq!(
        s.positions.get("INXUSDT").copied(),
        Some(false),
        "burst 結束 positions[INXUSDT] 應為 Some(false)（SHORT）"
    );
    // 3. SLA：1000 op < 100ms（防 hot loop 引入 O(n) 病灶）。
    assert!(
        elapsed.as_millis() < 100,
        "1000 次 on_rejection 應 < 100ms，實測 {} ms",
        elapsed.as_millis()
    );
}
