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
//!
//! P0 Option A-Lite (2026-05-11)：position state SSoT 改造後，W7-2 / W7-3 /
//! W7-5 系列 sync tests 已移除（functionality 由 ctx.position_state
//! owner_strategy gate 涵蓋）；改加 cross-strategy skip acceptance tests + on_rejection
//! cooldown rollback regression。詳：PA report
//! `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p0_option_a_position_state_ssot_refactor.md`。

use super::*;
use crate::strategies::test_harness::StrategyHarness;
use crate::strategies::{Strategy, StrategyAction};
use crate::tick_pipeline::TickContext;
use openclaw_core::alpha_surface::{AlphaSurface, BtcLeadLagPanel};
use openclaw_core::indicators::{AdxResult, AtrResult, HurstResult, IndicatorSnapshot, KamaResult};

// P-08: Test helpers use Box::leak for owned indicator data (fine for tests).

/// Helper: build a TickContext with given indicator values.
/// 輔助函數：用給定指標值構建 TickContext。
fn ctx_with(sma: f64, kama: f64, adx: f64, ts: u64) -> TickContext<'static> {
    StrategyHarness::new("BTC")
        .timestamp_ms(ts)
        .indicators(IndicatorSnapshot {
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
        })
        .build()
}

fn btc_panel(symbol: &str, expected_dir: i8) -> BtcLeadLagPanel {
    BtcLeadLagPanel {
        alt_symbols: vec![symbol.to_string()],
        btc_lead_return_pct: 25.0,
        lead_window_secs: 120,
        alt_xcorr: vec![0.65],
        alt_expected_dir: vec![expected_dir],
        snapshot_ts_ms: 1_715_000_000_000,
        source_tier: "cross_asset_btc_lead_lag".to_string(),
    }
}

fn surface_with_btc(panel: &BtcLeadLagPanel) -> AlphaSurface<'_> {
    AlphaSurface {
        btc_lead_lag: Some(panel),
        ..AlphaSurface::empty()
    }
}

fn ctx_with_atr(sma: f64, kama: f64, adx: f64, ts: u64, atr: f64) -> TickContext<'static> {
    StrategyHarness::new("BTC")
        .timestamp_ms(ts)
        .indicators(IndicatorSnapshot {
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
        })
        .build()
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
    StrategyHarness::new("BTC")
        .timestamp_ms(ts)
        .indicators(IndicatorSnapshot {
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
        })
        .build()
}

/// Helper: build a TickContext with sma_50 for higher-TF testing.
/// 輔助函數：用 sma_50 構建 TickContext 以測試較高時間框架。
fn ctx_with_sma50(sma_20: f64, kama: f64, adx: f64, ts: u64, sma_50: f64) -> TickContext<'static> {
    StrategyHarness::new("BTC")
        .timestamp_ms(ts)
        .indicators(IndicatorSnapshot {
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
        })
        .build()
}

// ═══════════════════════════════════════════════════════════════════════
// Existing tests (must still pass) / 原有測試（必須繼續通過）
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_no_signal_low_adx() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    assert!(s
        .on_tick(
            &ctx_with(100.0, 101.0, 15.0, 0),
            &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE
        )
        .is_empty());
}

#[test]
fn test_long_entry() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    let i = s.on_tick(
        &ctx_with(100.0, 101.0, 25.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Open(intent) => assert!(intent.is_long),
        other => panic!("expected StrategyAction::Open, got {:?}", other),
    }
}

#[test]
fn test_btc_lead_lag_blocks_counter_direction_long_entry() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    let panel = btc_panel("BTC", -1);
    let surface = surface_with_btc(&panel);

    let actions = s.on_tick(&ctx_with(100.0, 101.0, 25.0, 0), &surface);

    assert!(
        actions.is_empty(),
        "long MA entry must be blocked when BTC lead-lag expects down"
    );
}

#[test]
fn test_btc_lead_lag_confirms_aligned_long_entry() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    let panel = btc_panel("BTC", 1);
    let surface = surface_with_btc(&panel);

    let actions = s.on_tick(&ctx_with(100.0, 101.0, 25.0, 0), &surface);

    assert_eq!(actions.len(), 1);
    match &actions[0] {
        StrategyAction::Open(intent) => assert!(intent.is_long),
        other => panic!("expected aligned long Open, got {:?}", other),
    }
}

#[test]
fn test_min_trend_snr_blocks_noisy_entry() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    s.min_trend_snr = 1.0;

    let blocked = s.on_tick(
        &ctx_with_atr(100.0, 101.0, 25.0, 0, 2.0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert!(blocked.is_empty(), "SNR 0.5 must be blocked");

    let allowed = s.on_tick(
        &ctx_with_atr(100.0, 103.0, 25.0, 1_000, 2.0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert_eq!(allowed.len(), 1, "SNR 1.5 must pass");
}

#[test]
fn test_exit_on_reverse() {
    // P0 Option A-Lite (2026-05-11)：position state SSoT 改造後，exit path 由
    // `ctx.position_state` 注入 self-owned 倉位來觸發。原 tests 透過連續 on_tick
    // 期望「strategy 自己記得有倉位」已失效；改為顯式注入 paper_state position。
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    // Step 1：entry (cold-start，ctx.position_state=None)
    s.on_tick(
        &ctx_with(100.0, 101.0, 25.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    // Step 2：reverse cross + self-owned paper_state position 注入 → exit branch
    let pp = make_paper_position("BTC", true, "ma_crossover");
    let mut ctx_exit = ctx_with(101.0, 100.0, 25.0, 500_000);
    ctx_exit.position_state = Some(&pp);
    let i = s.on_tick(
        &ctx_exit,
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
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
    // P0 Option A-Lite (2026-05-11)：exit path 由顯式 ctx.position_state 注入觸發。
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    // Step 1：trending regime 入場 LONG（cold-start，ctx.position_state=None）
    let ctx_entry = ctx_with_hurst(100.0, 101.0, 25.0, 0, "trending", 0.72);
    let entry = s.on_tick(
        &ctx_entry,
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert_eq!(entry.len(), 1, "Should enter long");

    // Step 2：regime 翻 mean_reverting + reverse cross + self-owned ma_crossover LONG 注入
    let pp = make_paper_position("BTC", true, "ma_crossover");
    let mut ctx_exit = ctx_with_hurst(101.0, 100.0, 25.0, 500_000, "mean_reverting", 0.35);
    ctx_exit.position_state = Some(&pp);
    let exit = s.on_tick(
        &ctx_exit,
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
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
    // P0 Option A-Lite (2026-05-11)：exit path 由顯式 ctx.position_state 注入觸發。
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    // Step 1：entry LONG（aligned higher TF）
    s.higher_tf_sma.insert("BTC".into(), 90.0);
    let ctx_entry = ctx_with_sma50(100.0, 101.0, 25.0, 0, 100.0);
    let entry = s.on_tick(
        &ctx_entry,
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert_eq!(entry.len(), 1);

    // Step 2：翻轉 higher TF + reverse cross + self-owned LONG 注入 → exit
    s.higher_tf_sma.insert("BTC".into(), 110.0);
    s.higher_tf_trend.insert("BTC".into(), false);
    let pp = make_paper_position("BTC", true, "ma_crossover");
    let mut ctx_exit = ctx_with_sma50(101.0, 100.0, 25.0, 500_000, 100.0);
    ctx_exit.position_state = Some(&pp);
    let exit = s.on_tick(
        &ctx_exit,
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
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
        is_pinned: true,
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
// P0 Option A-Lite (2026-05-11) — position state SSoT 改造後 acceptance tests
// ═══════════════════════════════════════════════════════════════════════════
//
// 改造背景：
// - 22:08 May 10 watchdog Auto restart 後 cross-strategy mass scalp
//   （bb_reversion 寬 exit zone + W7-2 sync self.positions = cross-strategy
//   倉位 → 走 exit 分支大量平 grid/ma 開的單）
// - PA `2026-05-11--p0_option_a_position_state_ssot_refactor.md` Option A-Lite
//   結論：ma_crossover 移除 `self.positions: PerSymbolState<bool>`，由
//   `ctx.position_state.filter(owner_strategy == self.name())` 作 SSoT
// - W7-2/W7-3/W7-5 防護碼層全移除（functionality 由 owner gate 涵蓋）
//
// 本批 tests 驗證新 contract：
// - acceptance：cross-strategy ctx.position_state → skip entry，0 actions
// - baseline regression：ctx.position_state=None → entry path 正常
// - self-owned 倉位 + reverse cross → 走 exit 分支（emit Close）
// - on_rejection cooldown rollback 仍生效（與 positions 解耦）

use crate::intent_processor::OrderIntent;
use crate::paper_state::PaperPosition;

/// Helper：構建一筆模擬 OrderIntent 給 on_rejection 用。所有欄位最小可行值。
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

/// Helper：構建一個 PaperPosition 模擬 paper_state 真實持倉。
/// `owner` 由參數決定，用以模擬 cross-strategy vs self-owned 場景。
fn make_paper_position(symbol: &str, is_long: bool, owner: &str) -> PaperPosition {
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
        owner_strategy: owner.to_string(),
        entry_notional: 1810.0 * 0.015,
        max_favorable_pnl_pct: 0.0,
        peak_reached_ts_ms: 0,
    }
}

/// Acceptance test：cross-strategy paper_state 倉位 → ma_crossover.on_tick 必 skip entry。
///
/// 對應 PA report §5.3 acceptance test 契約：
/// - paper_state 已有 grid_trading owned LONG BTCUSDT 倉位
/// - ma_crossover 同 tick signal = LONG（fast > slow）
/// - 期望：on_tick 回 0 actions（不發 entry intent，也不誤觸 exit）
/// - 對比 P0 22:08 場景：bb_reversion 寬 exit zone + cross-strategy 倉位 → mass close
///   現 owner_strategy gate 直接 skip，從根源終結 cross-strategy desync
#[test]
fn test_cross_strategy_position_skips_entry() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    let pp = make_paper_position("BTC", true, "grid_trading"); // grid 已開 LONG
    let mut ctx = ctx_with(100.0, 101.0, 25.0, 0); // ma_crossover signal = LONG (fast > slow)
    ctx.position_state = Some(&pp);

    let intents = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);

    assert!(
        intents.is_empty(),
        "cross-strategy paper_state 持倉時 ma_crossover 必 skip entry，但發了 {} intents",
        intents.len()
    );
}

/// 額外 acceptance：cross-strategy SHORT 持倉 + ma_crossover entry signal=LONG
/// → 仍 skip（與 sign 無關，純看 owner_strategy gate）。
/// 對應 INXUSDT 11:34 場景 — grid 已開 SHORT，ma_crossover 想 LONG 即跳過。
#[test]
fn test_cross_strategy_position_skips_entry_opposite_direction() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    let pp = make_paper_position("BTC", false, "grid_trading"); // grid SHORT
    let mut ctx = ctx_with(100.0, 101.0, 25.0, 0); // ma_crossover signal = LONG
    ctx.position_state = Some(&pp);

    let intents = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert!(
        intents.is_empty(),
        "cross-strategy SHORT 持倉時亦必 skip LONG entry"
    );
}

/// 額外 acceptance：bybit_sync owner 也算 cross-strategy（不對應任何策略 name）。
#[test]
fn test_bybit_sync_owner_treated_as_cross_strategy_skip() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    let pp = make_paper_position("BTC", true, "bybit_sync");
    let mut ctx = ctx_with(100.0, 101.0, 25.0, 0);
    ctx.position_state = Some(&pp);

    let intents = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert!(
        intents.is_empty(),
        "bybit_sync owner 視同 cross-strategy（owner != ma_crossover）必 skip entry"
    );
}

/// Baseline regression：ctx.position_state = None + valid signal → 1 entry intent。
/// 確認新 owner gate 不誤殺正常 entry 路徑。
#[test]
fn test_on_tick_proceeds_entry_when_paper_state_is_none() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    let mut ctx = ctx_with(100.0, 101.0, 25.0, 0); // signal = LONG
    ctx.position_state = None;

    let intents = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(
        intents.len(),
        1,
        "ctx.position_state=None 時 valid signal 必發 entry"
    );
    match &intents[0] {
        StrategyAction::Open(intent) => {
            assert!(intent.is_long, "expected LONG entry");
        }
        other => panic!("expected StrategyAction::Open, got {:?}", other),
    }
}

/// SCANNER-TRADEABLE-TIER-1：scanner 可高頻觀察 dynamic-add symbols，
/// 但 ma_crossover 只能在 pinned tradeable tier 開新倉。
#[test]
fn test_non_pinned_symbol_skips_entry() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    let mut ctx = ctx_with(100.0, 101.0, 25.0, 0); // valid LONG signal
    ctx.position_state = None;
    ctx.is_pinned = false;

    let actions = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);

    assert!(
        actions.is_empty(),
        "dynamic-add/non-pinned symbol must not produce ma_crossover entry"
    );
}

/// Self-owned ctx.position_state + reverse cross → 走 exit 分支（emit Close）。
/// 驗證 owner_strategy == "ma_crossover" filter 命中時，exit path 觸發正常。
#[test]
fn test_self_owned_position_triggers_exit_on_reverse_cross() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    // 模擬：上次 tick 已 entry LONG（paper_state 寫入 ma_crossover owned LONG）
    let pp = make_paper_position("BTC", true, "ma_crossover");
    let mut ctx_exit = ctx_with(101.0, 100.0, 25.0, 500_000); // fast < slow → reverse for LONG
    ctx_exit.position_state = Some(&pp);

    let exit_actions = s.on_tick(
        &ctx_exit,
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert_eq!(
        exit_actions.len(),
        1,
        "self-owned LONG 倉位 + reverse cross 必發 Close"
    );
    match &exit_actions[0] {
        StrategyAction::Close { reason, .. } => {
            assert_eq!(
                reason, "ma_reverse_cross",
                "exit reason 必為 ma_reverse_cross"
            );
        }
        other => panic!("expected StrategyAction::Close, got {:?}", other),
    }
}

/// SCANNER-TRADEABLE-TIER-1：pinned gate 只限制新開倉，不阻擋自家倉位出場。
#[test]
fn test_non_pinned_self_owned_position_can_exit() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    let pp = make_paper_position("BTC", true, "ma_crossover");
    let mut ctx_exit = ctx_with(101.0, 100.0, 25.0, 500_000); // reverse for LONG
    ctx_exit.position_state = Some(&pp);
    ctx_exit.is_pinned = false;

    let exit_actions = s.on_tick(
        &ctx_exit,
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );

    assert_eq!(
        exit_actions.len(),
        1,
        "non-pinned self-owned ma_crossover position must still be allowed to exit"
    );
    match &exit_actions[0] {
        StrategyAction::Close { reason, .. } => assert_eq!(reason, "ma_reverse_cross"),
        other => panic!("expected StrategyAction::Close, got {:?}", other),
    }
}

/// Self-owned ctx.position_state + aligned cross（無 reverse 信號）→ 不 emit Close。
/// 驗證 exit 條件仍要求 KAMA reverse cross，不是「self-owned 就 close」。
#[test]
fn test_self_owned_position_no_exit_when_aligned() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    let pp = make_paper_position("BTC", true, "ma_crossover"); // LONG owned
    let mut ctx = ctx_with(100.0, 101.0, 25.0, 0); // fast > slow → aligned LONG
    ctx.position_state = Some(&pp);

    let actions = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert!(
        actions.is_empty(),
        "self-owned LONG + aligned cross (no reverse) → 不可 emit Close（exit 不該 fire）"
    );
}

/// on_rejection cooldown rollback：reject 時還原 last_trade_ms 至 mutation 前。
/// pre-condition：prev_last_trade_ms == 0（哨兵：未交易過）→ rollback 後 cooldown 應 clear。
#[test]
fn test_on_rejection_cooldown_rollback_unseen_sentinel() {
    let mut s = MaCrossover::new();
    let intent = make_test_intent("SOLUSDT", true);

    // 模擬 entry path mutation：prev_last_trade_ms = 0（變更前未交易過）。
    s.prev_last_trade_ms.insert("SOLUSDT".to_string(), 0);
    s.cooldown.record_signal("SOLUSDT", 100_000);

    s.on_rejection(&intent, "cost_gate: estimated=-12.50bps");

    // Cooldown 必 clear（prev_last_trade_ms == 0 哨兵）。
    assert!(
        s.cooldown.last_ms("SOLUSDT").is_none(),
        "on_rejection 必還原 cooldown 至未交易狀態（prev_last_trade_ms=0 哨兵）"
    );
}

/// on_rejection cooldown rollback：reject 時還原非 0 last_trade_ms 至原值。
/// pre-condition：prev_last_trade_ms == 50_000（有舊紀錄）→ rollback 後 cooldown 必為 50_000。
#[test]
fn test_on_rejection_cooldown_rollback_preserves_prior_ts() {
    let mut s = MaCrossover::new();
    let intent = make_test_intent("ETHUSDT", true);

    // 模擬：prev_last_trade_ms = 50_000（變更前有交易紀錄），mutation 後寫入 100_000。
    s.prev_last_trade_ms.insert("ETHUSDT".to_string(), 50_000);
    s.cooldown.record_signal("ETHUSDT", 100_000);

    s.on_rejection(&intent, "risk_gate: portfolio_overexposure");

    // Cooldown 必回滾為 50_000。
    assert_eq!(
        s.cooldown.last_ms("ETHUSDT"),
        Some(50_000),
        "on_rejection 必還原 cooldown 至 prev_last_trade_ms 原值"
    );
}

/// on_external_close 清理 signal-time persistence trackers（mutation 不 panic）。
/// 確認改造後（positions 已不存在）persistence/exit_persistence 仍正確清理。
/// 詳 sibling tests_a1_a2_maker.rs::test_a1_external_close_clears_exit_persistence 做完整覆蓋。
#[test]
fn test_on_external_close_mutation_does_not_panic() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 180_000;
    let _ = s.persistence.check("BTC", Some(true), 0, 180_000, false);
    let _ = s
        .exit_persistence
        .check("BTC", Some(false), 100_000, 180_000, false);

    s.on_external_close("BTC");

    // clear 過後 fresh check 不 panic（mutation 完整生效）。
    let _ = s.persistence.check("BTC", Some(true), 1_000_000, 0, false);
    let _ = s
        .exit_persistence
        .check("BTC", Some(false), 1_000_000, 0, false);
}
