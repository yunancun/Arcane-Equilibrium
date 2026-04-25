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
use openclaw_core::indicators::{AdxResult, HurstResult, IndicatorSnapshot, KamaResult};

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

/// Helper: build a TickContext with sma_50 for higher-TF testing.
/// 輔助函數：用 sma_50 構建 TickContext 以測試較高時間框架。
fn ctx_with_sma50(
    sma_20: f64,
    kama: f64,
    adx: f64,
    ts: u64,
    sma_50: f64,
) -> TickContext<'static> {
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

// ═══════════════════════════════════════════════════════════════════════
// Existing tests (must still pass) / 原有測試（必須繼續通過）
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_no_signal_low_adx() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    assert!(s.on_tick(&ctx_with(100.0, 101.0, 15.0, 0)).is_empty());
}

#[test]
fn test_long_entry() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    let i = s.on_tick(&ctx_with(100.0, 101.0, 25.0, 0));
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Open(intent) => assert!(intent.is_long),
        other => panic!("expected StrategyAction::Open, got {:?}", other),
    }
}

#[test]
fn test_exit_on_reverse() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    s.on_tick(&ctx_with(100.0, 101.0, 25.0, 0));
    let i = s.on_tick(&ctx_with(101.0, 100.0, 25.0, 500_000));
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
    let intents = s.on_tick(&ctx);
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
    let intents = s.on_tick(&ctx);
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
    let entry = s.on_tick(&ctx_entry);
    assert_eq!(entry.len(), 1, "Should enter long");

    // Step 2: Regime flips to mean_reverting, but crossover reverses → exit must work.
    // 步驟 2：狀態轉為均值回歸，但交叉反轉 → 出場必須有效。
    let ctx_exit = ctx_with_hurst(101.0, 100.0, 25.0, 500_000, "mean_reverting", 0.35);
    let exit = s.on_tick(&ctx_exit);
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
    let intents = s.on_tick(&ctx);
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
    let intents = s.on_tick(&ctx);
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
    let intents = s.on_tick(&ctx);
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
    let intents = s.on_tick(&ctx);
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
    let intents = s.on_tick(&ctx);
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
    let intents = s.on_tick(&ctx);
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
    let entry = s.on_tick(&ctx_entry);
    assert_eq!(entry.len(), 1);

    // Now flip higher TF to bearish and reverse crossover → exit must still work.
    // 現在將較高 TF 翻轉為看跌並反轉交叉 → 出場仍必須有效。
    s.higher_tf_sma.insert("BTC".into(), 110.0);
    s.higher_tf_trend.insert("BTC".into(), false);
    let ctx_exit = ctx_with_sma50(101.0, 100.0, 25.0, 500_000, 100.0);
    let exit = s.on_tick(&ctx_exit);
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
        signals: &[],
        h0_allowed: true,
        funding_rate: None,
        index_price: None,
        open_interest: None,
        best_bid: None,
        best_ask: None,
        tick_size: None,
    };
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    s.set_conf_scale(0.5);
    let intent = s.make_intent(&ctx, true, 0.8);
    assert!((intent.confidence - 0.4).abs() < 1e-10);

    s.set_conf_scale(2.0);
    let intent = s.make_intent(&ctx, true, 0.9);
    assert!((intent.confidence - 1.0).abs() < 1e-10); // clamped
}

// ── G-SR-1 S3+S4: param_ranges + validation tests ──

#[test]
fn test_ma_param_ranges_count() {
    let ranges = MaCrossoverParams::param_ranges();
    // 5 original + 10 confluence + 1 A2 (max_cooldown_boost) = 16
    assert_eq!(
        ranges.len(),
        16,
        "expected 16 param ranges, got {}",
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
    let intents = s.on_tick(&ctx);
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
    let intents = s.on_tick(&ctx);
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
    let intents = s.on_tick(&ctx);
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
    let intents = s.on_tick(&ctx);
    assert!(
        intents.is_empty(),
        "Unknown regime string must map to non-Persistent and block entry"
    );
}
