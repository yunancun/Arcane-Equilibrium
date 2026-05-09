//! BB Breakout core unit tests — entry/exit, params, E5-P2-4 hot-reload, PostOnly.
//! BB 突破核心單元測試 — 入場/出場、參數、E5-P2-4 熱重載、PostOnly。
//!
//! MODULE_NOTE (EN): Split from monolithic `mod tests` to keep each file ≤ 800
//!   soft warn. OI confluence + rejection rollback tests live in
//!   `tests_oi.rs`. Helpers (`ctx`, `ctx_ext`) here are local to this module.
//! MODULE_NOTE (中): 從單檔 `mod tests` 拆出以維持每檔 ≤ 800 soft warn；OI 合流
//!   與拒絕回滾測試在 `tests_oi.rs`。本檔 `ctx`/`ctx_ext` 助手僅供本模組使用。

use super::super::{Strategy, StrategyAction, StrategyParams};
use super::params::BbBreakoutParams;
use super::BbBreakout;
use crate::order_manager::TimeInForce;
use crate::tick_pipeline::TickContext;
use openclaw_core::indicators::{AtrResult, BollingerResult, HurstResult, IndicatorSnapshot};

// P-08: Test helpers use Box::leak for owned indicator data (fine for tests).
pub(super) fn ctx(bw: f64, pct_b: f64, vol: f64, ts: u64) -> TickContext<'static> {
    ctx_ext(bw, pct_b, vol, ts, 50000.0, None, None)
}

/// Extended context builder with price, ATR, and Hurst overrides.
/// 擴展上下文建構器，支持自訂價格、ATR、Hurst。
pub(super) fn ctx_ext(
    bw: f64,
    pct_b: f64,
    vol: f64,
    ts: u64,
    price: f64,
    atr: Option<AtrResult>,
    hurst: Option<HurstResult>,
) -> TickContext<'static> {
    let ind = Box::leak(Box::new(IndicatorSnapshot {
        bollinger: Some(BollingerResult {
            upper: 51000.0,
            middle: 50000.0,
            lower: 49000.0,
            bandwidth: bw,
            percent_b: pct_b,
        }),
        volume_ratio: Some(vol),
        atr_14: atr,
        hurst,
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
        best_bid: None,
        best_ask: None,
        tick_size: None,
    }
}

#[test]
fn test_squeeze_then_breakout() {
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    s.on_tick(&ctx(0.01, 0.5, 1.0, 0));
    let i = s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000));
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Open(intent) => assert!(intent.is_long),
        other => panic!("expected Open, got {:?}", other),
    }
}

#[test]
fn test_no_breakout_without_squeeze() {
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    assert!(s.on_tick(&ctx(0.05, 1.1, 2.0, 0)).is_empty());
}

#[test]
fn test_entry_price_recorded() {
    // After entry, entry_price should be set / 入場後 entry_price 應被設置
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
    s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000)); // breakout long
    assert_eq!(s.entry_price_of("BTC"), Some(50000.0));
    assert!(s.trailing_stop_of("BTC").is_none()); // no ATR data, no trailing stop yet
}

#[test]
fn test_atr_trailing_stop_long_exit() {
    // Long position: price drops below trailing stop -> exit
    // 做多倉位：價格跌破追蹤止損 -> 出場
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    let atr = || {
        Some(AtrResult {
            atr: 500.0,
            atr_percent: 0.01,
        })
    };

    // Enter long
    s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
    s.on_tick(&ctx_ext(0.05, 1.1, 2.0, 700_000, 50000.0, atr(), None)); // breakout
    assert_eq!(s.position_of("BTC"), Some(true));
    // trailing_stop = 50000 - 500*2 = 49000
    assert_eq!(s.trailing_stop_of("BTC"), Some(49000.0));

    // Price rises -> trailing stop ratchets up, no exit
    // 價格上漲 -> 追蹤止損上移，不出場
    let i = s.on_tick(&ctx_ext(0.05, 1.2, 2.0, 1_400_000, 52000.0, atr(), None));
    assert!(i.is_empty()); // still in trend
    assert_eq!(s.trailing_stop_of("BTC"), Some(51000.0)); // 52000 - 1000

    // Price drops to trailing stop -> exit
    // 價格跌至追蹤止損 -> 出場
    let i = s.on_tick(&ctx_ext(0.05, 0.9, 2.0, 2_100_000, 51000.0, atr(), None));
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Close {
            reason, confidence, ..
        } => {
            assert_eq!(reason, "trailing_stop");
            assert!((*confidence - 0.7).abs() < 1e-9);
        }
        other => panic!("expected Close, got {:?}", other),
    }
    assert!(s.position_of("BTC").is_none());
    assert!(s.entry_price_of("BTC").is_none());
    assert!(s.trailing_stop_of("BTC").is_none());
}

#[test]
fn test_atr_trailing_stop_short_exit() {
    // Short position: price rises above trailing stop -> exit
    // 做空倉位：價格漲破追蹤止損 -> 出場
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    let atr = || {
        Some(AtrResult {
            atr: 500.0,
            atr_percent: 0.01,
        })
    };

    // Enter short
    s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
    s.on_tick(&ctx_ext(0.05, -0.1, 2.0, 700_000, 50000.0, atr(), None)); // breakout short
    assert_eq!(s.position_of("BTC"), Some(false));
    // trailing_stop = 50000 + 500*2 = 51000
    assert_eq!(s.trailing_stop_of("BTC"), Some(51000.0));

    // Price drops -> trailing stop ratchets down
    let i = s.on_tick(&ctx_ext(0.05, -0.2, 2.0, 1_400_000, 48000.0, atr(), None));
    assert!(i.is_empty());
    assert_eq!(s.trailing_stop_of("BTC"), Some(49000.0)); // 48000 + 1000

    // Price rises to trailing stop -> exit
    let i = s.on_tick(&ctx_ext(0.05, 0.1, 2.0, 2_100_000, 49000.0, atr(), None));
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Close { reason, .. } => assert_eq!(reason, "trailing_stop"),
        other => panic!("expected Close, got {:?}", other),
    }
}

#[test]
fn test_regime_exit() {
    // Exit when regime changes to mean_reverting / 當 regime 變為均值回歸時出場
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    let trending = || {
        Some(HurstResult {
            hurst: 0.7,
            regime: "trending".into(),
        })
    };
    let ranging = || {
        Some(HurstResult {
            hurst: 0.4,
            regime: "mean_reverting".into(),
        })
    };

    // Enter long (with trending regime boost)
    s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
    let i = s.on_tick(&ctx_ext(0.05, 1.1, 2.0, 700_000, 50000.0, None, trending()));
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Open(intent) => {
            assert!((intent.confidence - 0.8).abs() < 1e-9); // 0.7 + 0.1 hurst boost
        }
        other => panic!("expected Open, got {:?}", other),
    }
    assert_eq!(s.position_of("BTC"), Some(true));

    // Regime shifts to mean_reverting -> exit
    let i = s.on_tick(&ctx_ext(
        0.05,
        1.1,
        2.0,
        1_400_000,
        51000.0,
        None,
        ranging(),
    ));
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Close {
            reason, confidence, ..
        } => {
            assert_eq!(reason, "regime_shift");
            assert!((*confidence - 0.6).abs() < 1e-9);
        }
        other => panic!("expected Close, got {:?}", other),
    }
    assert!(s.position_of("BTC").is_none());
}

#[test]
fn test_configurable_volume_threshold() {
    // RC-03: Custom volume threshold — higher threshold blocks low-volume breakouts
    // RC-03：自訂成交量閾值 — 較高閾值阻擋低量突破
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    s.volume_threshold = 3.0; // require 3x volume instead of default 1.5x
    s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
                                        // vol=2.0 passes default (1.5) but fails custom (3.0)
                                        // vol=2.0 通過默認閾值(1.5)但不通過自訂閾值(3.0)
    let i = s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000));
    assert!(i.is_empty(), "volume 2.0 should not pass threshold 3.0");

    // vol=3.5 passes custom threshold / vol=3.5 通過自訂閾值
    let i = s.on_tick(&ctx(0.05, 1.1, 3.5, 700_000));
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Open(intent) => assert!(intent.is_long),
        other => panic!("expected Open, got {:?}", other),
    }
}

#[test]
fn test_configurable_squeeze_expansion_bw() {
    // RC-03: Custom squeeze/expansion bandwidth thresholds
    // RC-03：自訂壓縮/擴張帶寬閾值
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    s.squeeze_bw = 0.03; // wider squeeze detection / 更寬的壓縮偵測
    s.expansion_bw = 0.06; // require stronger expansion / 要求更強擴張

    // bw=0.025 triggers squeeze with custom threshold (< 0.03)
    s.on_tick(&ctx(0.025, 0.5, 1.0, 0));
    assert!(s.has_squeeze("BTC"));

    // bw=0.05 is expansion for default (> 0.04) but NOT for custom (< 0.06)
    let i = s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000));
    assert!(i.is_empty(), "bw 0.05 should not pass expansion_bw 0.06");

    // bw=0.07 passes custom expansion threshold / 通過自訂擴張閾值
    let i = s.on_tick(&ctx(0.07, 1.1, 2.0, 700_000));
    assert_eq!(i.len(), 1);
}

#[test]
fn test_bb_brk_param_ranges() {
    assert!(!BbBreakoutParams::param_ranges().is_empty());
}
#[test]
fn test_bb_brk_validate() {
    assert!(BbBreakoutParams::default().validate().is_ok());
    assert!(BbBreakoutParams {
        squeeze_bw: 0.05,
        expansion_bw: 0.04,
        ..Default::default()
    }
    .validate()
    .is_err());
}
#[test]
fn test_bb_brk_update() {
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    assert!(s
        .update_params(BbBreakoutParams {
            trailing_stop_atr_mult: 3.0,
            ..Default::default()
        })
        .is_ok());
    assert!((s.get_params().trailing_stop_atr_mult - 3.0).abs() < 0.01);
}

#[test]
fn test_pctb_revert_exit() {
    // Failed breakout: %B returns to mid-band [0.2, 0.8] → exit with pctb_revert
    // 突破失敗：%B 回到中間帶 [0.2, 0.8] → 以 pctb_revert 出場
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
                              // Enter long (no ATR, no Hurst — only pctb/bw exits active)
    s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
    s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000)); // breakout long
    assert_eq!(s.position_of("BTC"), Some(true));

    // %B reverts to 0.5 (mid-band) → should trigger pctb_revert exit
    let i = s.on_tick(&ctx(0.05, 0.5, 2.0, 1_400_000));
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Close {
            reason, confidence, ..
        } => {
            assert_eq!(reason, "pctb_revert");
            // 0.55 * conf_scale(1.0) = 0.55
            assert!((*confidence - 0.55).abs() < 1e-9);
        }
        other => panic!("expected Close(pctb_revert), got {:?}", other),
    }
    assert!(s.position_of("BTC").is_none());
}

#[test]
fn test_bw_squeeze_exit() {
    // Volatility collapse: bandwidth drops below squeeze_bw while %B still extreme → bw_squeeze
    // 波動塌陷：帶寬低於壓縮閾值且 %B 仍在極端 → bw_squeeze
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
                              // Enter long
    s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
    s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000)); // breakout long
    assert_eq!(s.position_of("BTC"), Some(true));

    // %B still extreme (1.1, outside [0.2,0.8]) but bandwidth collapsed below squeeze_bw (0.02)
    // → pctb_revert doesn't trigger, but bw_squeeze does
    let i = s.on_tick(&ctx(0.015, 1.1, 2.0, 1_400_000));
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Close {
            reason, confidence, ..
        } => {
            assert_eq!(reason, "bw_squeeze");
            // 0.45 * conf_scale(1.0) = 0.45
            assert!((*confidence - 0.45).abs() < 1e-9);
        }
        other => panic!("expected Close(bw_squeeze), got {:?}", other),
    }
    assert!(s.position_of("BTC").is_none());
}

// ── G-SR-1 S3+S4: param_ranges + validation tests ──

#[test]
fn test_bbb_param_ranges_count() {
    let ranges = BbBreakoutParams::param_ranges();
    // 5 original + 11 confluence (includes confluence_as_gate) + 4 EDGE-P2-2 OI
    // (enable_oi_signal + oi_buffer_window_ms + oi_confluence_bonus + oi_min_delta_pct)
    // + 1 P1-11 (donchian_score_bonus; donchian_mode is enum, not in numeric ranges) = 21
    // EDGE-P2-2 FUP：oi_min_delta_pct 是 noise floor，需作為 agent-tunable ParamRange 暴露。
    // P1-11 (2)：donchian_score_bonus 為 numeric ParamRange；donchian_mode 為 enum 不入此表。
    assert_eq!(
        ranges.len(),
        21,
        "expected 21 param ranges, got {}",
        ranges.len()
    );
}

#[test]
fn test_bbb_param_ranges_has_confluence_as_gate() {
    let ranges = BbBreakoutParams::param_ranges();
    let names: Vec<&str> = ranges.iter().map(|r| r.name.as_str()).collect();
    assert!(
        names.contains(&"confluence_as_gate"),
        "BBB must expose confluence_as_gate"
    );
}

#[test]
fn test_bbb_param_ranges_confluence_names() {
    let ranges = BbBreakoutParams::param_ranges();
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
        "confluence_as_gate",
        "min_persistence_ms",
        "min_notional_usd",
    ] {
        assert!(names.contains(expected), "missing param range: {expected}");
    }
}

#[test]
fn test_bbb_validate_default_ok() {
    assert!(BbBreakoutParams::default().validate().is_ok());
}

#[test]
fn test_bbb_validate_bad_weight_sum() {
    let mut p = BbBreakoutParams::default();
    p.weight_adx = 0.0; // sum = 0+20+12+8 = 40 ≠ 65
    assert!(p.validate().is_err());
}

#[test]
fn test_bbb_validate_bad_threshold_order() {
    let mut p = BbBreakoutParams::default();
    p.confluence_threshold_no_trade = 60.0; // > light (45)
    assert!(p.validate().is_err());
}

// ── E5-P2-4: bit-exact defaults for newly config-driven magic numbers ──
// ── E5-P2-4：新增 config 欄位的預設值需與原 hard-coded 一致（bit-exact） ──

#[test]
fn test_e5_p2_4_bbb_params_defaults_match_prior_hardcoded() {
    // Defaults must equal the literals previously embedded in the strategy body
    // so downstream numerical outputs are byte-identical when TOML omits them.
    // 默認值需等於原先硬編碼的字面量，以保證 TOML 未覆寫時輸出位元相等。
    let p = BbBreakoutParams::default();
    assert!(
        (p.hurst_regime_boost - 0.1).abs() < f64::EPSILON,
        "hurst_regime_boost default must be 0.1 (bit-exact)"
    );
    assert!(
        (p.exit_bonus_trailing_stop - 0.2).abs() < f64::EPSILON,
        "exit_bonus_trailing_stop default must be 0.2 (bit-exact)"
    );
    assert!(
        (p.exit_bonus_regime_shift - 0.1).abs() < f64::EPSILON,
        "exit_bonus_regime_shift default must be 0.1 (bit-exact)"
    );
    assert!(
        (p.exit_bonus_pctb_revert - 0.05).abs() < f64::EPSILON,
        "exit_bonus_pctb_revert default must be 0.05 (bit-exact)"
    );
    assert!(
        (p.exit_penalty_bw_squeeze - 0.05).abs() < f64::EPSILON,
        "exit_penalty_bw_squeeze default must be 0.05 (bit-exact)"
    );
}

#[test]
fn test_e5_p2_4_runtime_new_matches_params_default() {
    // BbBreakout::new() must seed the runtime fields with the same literals
    // as BbBreakoutParams::default() — enforces a single source of truth.
    // BbBreakout::new() 初始化值需與 BbBreakoutParams::default() 同源（單一事實來源）。
    let mut s = BbBreakout::new();
    let d = BbBreakoutParams::default();
    assert_eq!(s.cooldown_ms, d.cooldown_ms);
    assert_eq!(s.cooldown.duration_ms(), d.cooldown_ms);
    s.cooldown.record_signal("BTCUSDT", 1_000);
    assert!(!s
        .cooldown
        .is_cooled_down("BTCUSDT", 1_000 + d.cooldown_ms - 1));
    assert!(s.cooldown.is_cooled_down("BTCUSDT", 1_000 + d.cooldown_ms));
    assert!((s.hurst_regime_boost - d.hurst_regime_boost).abs() < f64::EPSILON);
    assert!((s.exit_bonus_trailing_stop - d.exit_bonus_trailing_stop).abs() < f64::EPSILON);
    assert!((s.exit_bonus_regime_shift - d.exit_bonus_regime_shift).abs() < f64::EPSILON);
    assert!((s.exit_bonus_pctb_revert - d.exit_bonus_pctb_revert).abs() < f64::EPSILON);
    assert!((s.exit_penalty_bw_squeeze - d.exit_penalty_bw_squeeze).abs() < f64::EPSILON);
}

#[test]
fn test_e5_p2_4_update_params_hot_reloads_offsets() {
    // update_params must propagate new field values to the live runtime
    // (hot-reload contract — ConfigStore / ArcSwap compatibility).
    // update_params 需將新欄位熱重載到運行時（與 ConfigStore/ArcSwap 契約一致）。
    let mut s = BbBreakout::new();
    let mut p = BbBreakoutParams::default();
    p.hurst_regime_boost = 0.17;
    p.exit_bonus_trailing_stop = 0.25;
    p.exit_bonus_regime_shift = 0.12;
    p.exit_bonus_pctb_revert = 0.07;
    p.exit_penalty_bw_squeeze = 0.08;
    s.update_params(p.clone()).expect("valid params");
    assert!((s.hurst_regime_boost - 0.17).abs() < f64::EPSILON);
    assert!((s.exit_bonus_trailing_stop - 0.25).abs() < f64::EPSILON);
    assert!((s.exit_bonus_regime_shift - 0.12).abs() < f64::EPSILON);
    assert!((s.exit_bonus_pctb_revert - 0.07).abs() < f64::EPSILON);
    assert!((s.exit_penalty_bw_squeeze - 0.08).abs() < f64::EPSILON);
    // Round-trip get_params must expose the freshly hot-reloaded values.
    // get_params 需回吐熱重載後的新值。
    let back = s.get_params();
    assert!((back.hurst_regime_boost - 0.17).abs() < f64::EPSILON);
    assert!((back.exit_bonus_trailing_stop - 0.25).abs() < f64::EPSILON);
}

/// EDGE-P2-2 FUP: update_params must hot-reload the 3 OI fields
/// (`enable_oi_signal` / `oi_buffer_window_ms` / `oi_confluence_bonus`) and
/// get_params must echo the mutated values — mirrors the
/// `test_e5_p2_4_update_params_hot_reloads_offsets` contract.
/// EDGE-P2-2 FUP：update_params 需熱重載 OI 三欄位；get_params 回吐新值。
#[test]
fn test_oi_params_update_hot_reloads() {
    let mut s = BbBreakout::new();
    // Baseline defaults — document the pre-EDGE-P2-2 bit-identical floor.
    // 預設值—記錄 pre-EDGE-P2-2 bit-identical 基線。
    assert!(
        !s.enable_oi_signal,
        "default enable_oi_signal must be false"
    );
    assert_eq!(
        s.oi_buffer_window_ms, 60_000,
        "default oi_buffer_window_ms must be 60_000"
    );
    assert!(
        (s.oi_confluence_bonus - 0.10).abs() < f64::EPSILON,
        "default oi_confluence_bonus must be 0.10"
    );

    let mut p = BbBreakoutParams::default();
    p.enable_oi_signal = true;
    p.oi_buffer_window_ms = 30_000;
    p.oi_confluence_bonus = 0.25;
    s.update_params(p.clone()).expect("valid OI params");

    // Runtime fields reflect the hot-reloaded values.
    // 運行時欄位反映熱重載後的值。
    assert!(s.enable_oi_signal, "flag must hot-reload to true");
    assert_eq!(s.oi_buffer_window_ms, 30_000, "window ms must hot-reload");
    assert!((s.oi_confluence_bonus - 0.25).abs() < f64::EPSILON);

    // get_params round-trip echoes the mutated values.
    // get_params 回吐後須等同變更值。
    let back = s.get_params();
    assert!(back.enable_oi_signal);
    assert_eq!(back.oi_buffer_window_ms, 30_000);
    assert!((back.oi_confluence_bonus - 0.25).abs() < f64::EPSILON);
}

/// EDGE-P2-2 FUP: JSON round-trip — serialize → mutate → update_params_json
/// must apply the 3 OI fields to the live runtime (ConfigStore Agent path).
/// EDGE-P2-2 FUP：JSON 往返 — 序列化→修改→update_params_json 熱重載 OI 三欄位。
#[test]
fn test_oi_params_json_round_trip() {
    let mut s = BbBreakout::new();
    // Serialize defaults.
    let json_v0 = s.get_params_json();
    assert!(
        !json_v0.is_empty(),
        "get_params_json must emit non-empty string"
    );

    // Deserialize, mutate OI fields, re-serialize.
    let mut p: BbBreakoutParams =
        serde_json::from_str(&json_v0).expect("default params must deserialize");
    p.enable_oi_signal = true;
    p.oi_buffer_window_ms = 15_000;
    p.oi_confluence_bonus = 0.33;
    let json_v1 = serde_json::to_string(&p).expect("params must serialize");

    // Apply via the Strategy-trait JSON path.
    s.update_params_json(&json_v1)
        .expect("valid JSON params must hot-reload");

    // Runtime reflects the mutated JSON values.
    assert!(s.enable_oi_signal);
    assert_eq!(s.oi_buffer_window_ms, 15_000);
    assert!((s.oi_confluence_bonus - 0.33).abs() < f64::EPSILON);

    // And round-trip back through get_params_json.
    let json_v2 = s.get_params_json();
    let back: BbBreakoutParams =
        serde_json::from_str(&json_v2).expect("round-trip JSON must deserialize");
    assert!(back.enable_oi_signal);
    assert_eq!(back.oi_buffer_window_ms, 15_000);
    assert!((back.oi_confluence_bonus - 0.33).abs() < f64::EPSILON);
}

// ── EDGE-P2-3 Phase 2+: PostOnly maker entry tests ──
// ── EDGE-P2-3 Phase 2+：PostOnly maker 入場測試 ──

/// When `use_maker_entry=false` (default), the entry intent keeps the legacy
/// Market shape: order_type="market", limit_price=None, TIF=None, maker_timeout_ms=None.
/// Byte-identical to pre-Phase-2+ behaviour.
/// 當 use_maker_entry=false（默認）時，入場意圖維持原本 Market 形態；與 Phase 2+ 之前 byte-identical。
#[test]
fn test_bb_breakout_market_entry_when_maker_disabled() {
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0; // disable persistence gate for unit test
    assert!(!s.use_maker_entry, "use_maker_entry must default to false");
    // Squeeze then expansion long breakout (mirrors test_squeeze_then_breakout).
    // 先壓縮再擴張多頭突破（與 test_squeeze_then_breakout 同模式）。
    s.on_tick(&ctx(0.01, 0.5, 1.0, 0));
    let i = s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000));
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Open(intent) => {
            assert_eq!(intent.order_type, "market");
            assert!(intent.limit_price.is_none());
            assert!(intent.time_in_force.is_none());
            assert!(intent.maker_timeout_ms.is_none());
        }
        other => panic!("expected Open, got {:?}", other),
    }
}

/// Long breakout with maker enabled emits BBO-derived PostOnly Limit.
/// 多頭突破且 maker 啟用 → 發 BBO-derived PostOnly Limit。
#[test]
fn test_bb_breakout_buy_postonly_below_last_price() {
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0;
    s.use_maker_entry = true;
    s.maker_price_offset_bps = 2.0; // 2 bps for bit-exact math check
    s.maker_limit_timeout_ms = 45_000;
    // Long setup: pctb=1.1 > 1.0 -> is_long
    // 多頭設置：pctb=1.1 > 1.0 → is_long
    s.on_tick(&ctx_with_bbo_g709c(
        0.01, 0.5, 1.0, 0, 50_000.0, 49_999.5, 50_000.5, 0.1,
    ));
    let i = s.on_tick(&ctx_with_bbo_g709c(
        0.05, 1.1, 2.0, 700_000, 50_000.0, 49_999.5, 50_000.5, 0.1,
    ));
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Open(intent) => {
            assert!(intent.is_long);
            assert_eq!(intent.order_type, "limit");
            assert_eq!(intent.time_in_force, Some(TimeInForce::PostOnly));
            assert_eq!(intent.maker_timeout_ms, Some(45_000));
            let lp = intent.limit_price.expect("limit_price set");
            let expected = 49_999.4;
            assert!(
                (lp - expected).abs() < 1e-9,
                "buy PostOnly must use best_bid-buffer: got {lp}, expected {expected}"
            );
            assert!(lp < 50000.0, "buy limit must rest below last_price");
        }
        other => panic!("expected Open, got {:?}", other),
    }
}

/// Short breakout with maker enabled emits BBO-derived PostOnly Limit.
/// 空頭突破且 maker 啟用 → 發 BBO-derived PostOnly Limit。
#[test]
fn test_bb_breakout_sell_postonly_above_last_price() {
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0;
    s.use_maker_entry = true;
    s.maker_price_offset_bps = 2.0; // 2 bps
    s.maker_limit_timeout_ms = 45_000;
    // Short setup: pctb=-0.1 < 0.0 -> is_short
    // 空頭設置：pctb=-0.1 < 0.0 → is_short
    s.on_tick(&ctx_with_bbo_g709c(
        0.01, 0.5, 1.0, 0, 50_000.0, 49_999.5, 50_000.5, 0.1,
    ));
    let i = s.on_tick(&ctx_with_bbo_g709c(
        0.05, -0.1, 2.0, 700_000, 50_000.0, 49_999.5, 50_000.5, 0.1,
    ));
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Open(intent) => {
            assert!(!intent.is_long);
            assert_eq!(intent.order_type, "limit");
            assert_eq!(intent.time_in_force, Some(TimeInForce::PostOnly));
            assert_eq!(intent.maker_timeout_ms, Some(45_000));
            let lp = intent.limit_price.expect("limit_price set");
            let expected = 50_000.6;
            assert!(
                (lp - expected).abs() < 1e-9,
                "sell PostOnly must use best_ask+buffer: got {lp}, expected {expected}"
            );
            assert!(lp > 50000.0, "sell limit must rest above last_price");
        }
        other => panic!("expected Open, got {:?}", other),
    }
}

/// update_params round-trips maker fields for Agent IPC hot-reload, and the
/// maker_limit_timeout_ms clamp invariant [15_000, 300_000] is enforced at
/// assignment. Tests both extremes (1_000 → 15_000, 500_000 → 300_000).
/// update_params 回吐 maker 欄位供 Agent IPC 熱重載；maker_limit_timeout_ms 寫入時
/// clamp 至 [15_000, 300_000]；驗證兩端（1_000→15_000、500_000→300_000）。
#[test]
fn test_bb_breakout_update_params_roundtrips_maker_fields() {
    let mut s = BbBreakout::new();
    let mut p = s.get_params();
    assert!(!p.use_maker_entry, "default must be false");
    // In-band round-trip: flag + offset + in-range timeout.
    // 在有效區間內的往返：旗標 + offset + timeout。
    p.use_maker_entry = true;
    p.maker_price_offset_bps = 3.0;
    p.maker_limit_timeout_ms = 60_000;
    s.update_params(p.clone()).expect("valid params");
    let back = s.get_params();
    assert!(back.use_maker_entry);
    assert!((back.maker_price_offset_bps - 3.0).abs() < 1e-9);
    assert_eq!(back.maker_limit_timeout_ms, 60_000);
    // Runtime fields reflect the update.
    // 運行時欄位亦已更新。
    assert!(s.use_maker_entry);
    assert!((s.maker_price_offset_bps - 3.0).abs() < 1e-9);
    assert_eq!(s.maker_limit_timeout_ms, 60_000);

    // Upper-bound clamp: 500_000 → 300_000.
    // 上限 clamp：500_000 → 300_000。
    let mut p_hi = s.get_params();
    p_hi.maker_limit_timeout_ms = 500_000;
    s.update_params(p_hi).expect("valid params");
    assert_eq!(s.get_params().maker_limit_timeout_ms, 300_000);

    // Lower-bound clamp: 1_000 → 15_000.
    // 下限 clamp：1_000 → 15_000。
    let mut p_lo = s.get_params();
    p_lo.maker_limit_timeout_ms = 1_000;
    s.update_params(p_lo).expect("valid params");
    assert_eq!(s.get_params().maker_limit_timeout_ms, 15_000);
}

// ─────────────────────────────────────────────────────────────────────────
// G7-09c Phase 1: BBO-aware PostOnly maker price tests for bb_breakout.
// G7-09c Phase 1：bb_breakout BBO-aware PostOnly 限價測試。
// ─────────────────────────────────────────────────────────────────────────

/// Helper: ctx_ext clone with BBO + tick_size populated.
/// 輔助：在 ctx_ext 基礎上補齊 BBO + tick_size。
fn ctx_with_bbo_g709c(
    bw: f64,
    pct_b: f64,
    vol: f64,
    ts: u64,
    last: f64,
    bid: f64,
    ask: f64,
    tick: f64,
) -> TickContext<'static> {
    let ind = Box::leak(Box::new(IndicatorSnapshot {
        bollinger: Some(BollingerResult {
            upper: 51000.0,
            middle: 50000.0,
            lower: 49000.0,
            bandwidth: bw,
            percent_b: pct_b,
        }),
        volume_ratio: Some(vol),
        atr_14: None,
        hurst: None,
        ..Default::default()
    }));
    TickContext {
        symbol: "BTC",
        price: last,
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

/// G7-09c: bb_breakout buy (squeeze→expansion long) uses best_bid - buffer×tick.
/// G7-09c：bb_breakout 買單（壓縮→擴張多頭）使用 best_bid - buffer×tick。
#[test]
fn test_g7_09c_bb_breakout_buy_uses_best_bid_passive() {
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0;
    s.use_maker_entry = true;
    s.maker_price_buffer_ticks = 1;
    s.maker_price_offset_bps = 1.0;
    // Squeeze first.
    // 先壓縮。
    s.on_tick(&ctx_with_bbo_g709c(
        0.01, 0.5, 1.0, 0, 50_000.0, 49_999.5, 50_000.5, 0.1,
    ));
    // Expansion + high vol + percent_b > 1 → long breakout.
    // 擴張 + 高量 + percent_b > 1 → 多頭突破。
    let i = s.on_tick(&ctx_with_bbo_g709c(
        0.05, 1.1, 2.0, 700_000, 50_000.0, 49_999.5, 50_000.5, 0.1,
    ));
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Open(intent) => {
            assert!(intent.is_long);
            assert_eq!(intent.order_type, "limit");
            assert_eq!(intent.time_in_force, Some(TimeInForce::PostOnly));
            let lp = intent.limit_price.expect("limit_price set");
            // Expected: 49_999.5 - 0.1 = 49_999.4.
            assert!(
                (lp - 49_999.4).abs() < 1e-6,
                "G7-09c BUY limit got {lp}, expected 49_999.4"
            );
        }
        other => panic!("expected Open, got {other:?}"),
    }
}

/// G7-09c: bb_breakout sell (squeeze→expansion short) uses best_ask + buffer×tick.
/// G7-09c：bb_breakout 賣單（壓縮→擴張空頭）使用 best_ask + buffer×tick。
#[test]
fn test_g7_09c_bb_breakout_sell_uses_best_ask_passive() {
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0;
    s.use_maker_entry = true;
    s.maker_price_buffer_ticks = 1;
    s.maker_price_offset_bps = 1.0;
    s.on_tick(&ctx_with_bbo_g709c(
        0.01, 0.5, 1.0, 0, 50_000.0, 49_999.5, 50_000.5, 0.1,
    ));
    // Expansion + high vol + percent_b < 0 → short breakout.
    // 擴張 + 高量 + percent_b < 0 → 空頭突破。
    let i = s.on_tick(&ctx_with_bbo_g709c(
        0.05, -0.1, 2.0, 700_000, 50_000.0, 49_999.5, 50_000.5, 0.1,
    ));
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Open(intent) => {
            assert!(!intent.is_long);
            assert_eq!(intent.order_type, "limit");
            let lp = intent.limit_price.expect("limit_price set");
            // Expected: 50_000.5 + 0.1 = 50_000.6.
            assert!(
                (lp - 50_000.6).abs() < 1e-6,
                "G7-09c SELL limit got {lp}, expected 50_000.6"
            );
        }
        other => panic!("expected Open, got {other:?}"),
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// G7-03 Phase B regression — typed `RegimeLabel` migration
// G7-03 Phase B 回歸 — 切換為 typed RegimeLabel
// ═══════════════════════════════════════════════════════════════════════════
//
// Purpose: prove that swapping the legacy `h.regime == "trending"` /
// `"mean_reverting" || "random_walk"` string compares for typed
// `RegimeLabel::from_legacy_str(&h.regime) == RegimeLabel::*` is a
// behaviour-preserving rewrite. Same input → same decision (entry boost or
// regime_shift exit) at every site touched by the migration.
//
// 目的：證明把 legacy 字串比較換成 typed enum 是行為保留改寫。

#[test]
fn test_phase_b_persistent_label_triggers_hurst_boost() {
    // Same scenario as `test_regime_exit` entry path: trending Hurst →
    // confidence base (0.7) + hurst_regime_boost (0.1) = 0.8.
    // 與 test_regime_exit 入場路徑同情境：trending → 0.7 + 0.1 = 0.8。
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0;
    let trending = || {
        Some(HurstResult {
            hurst: 0.7,
            regime: "trending".into(), // == RegimeLabel::Persistent.as_legacy_str()
        })
    };
    s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
    let i = s.on_tick(&ctx_ext(0.05, 1.1, 2.0, 700_000, 50000.0, None, trending()));
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Open(intent) => {
            assert!(
                (intent.confidence - 0.8).abs() < 1e-9,
                "Persistent regime must add hurst_regime_boost (0.1) to base 0.7 → 0.8, got {}",
                intent.confidence
            );
        }
        other => panic!("expected Open, got {:?}", other),
    }
}

#[test]
fn test_phase_b_random_label_does_not_trigger_hurst_boost() {
    // Unknown / Random regime must NOT trigger the boost. With the typed
    // match, `from_legacy_str("random_walk") == Random ≠ Persistent`, so
    // the `_ => 0.0` branch fires (legacy string compare also fails).
    // Random regime 不應觸發加成；typed match 與 legacy 字串比對皆走 _ 分支。
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0;
    let random = || {
        Some(HurstResult {
            hurst: 0.5,
            regime: "random_walk".into(), // RegimeLabel::Random
        })
    };
    s.on_tick(&ctx(0.01, 0.5, 1.0, 0));
    let i = s.on_tick(&ctx_ext(0.05, 1.1, 2.0, 700_000, 50000.0, None, random()));
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Open(intent) => {
            assert!(
                (intent.confidence - 0.7).abs() < 1e-9,
                "Random regime must NOT add hurst_regime_boost; expect base 0.7, got {}",
                intent.confidence
            );
        }
        other => panic!("expected Open, got {:?}", other),
    }
}

#[test]
fn test_phase_b_anti_persistent_triggers_regime_shift_exit() {
    // Anti-persistent regime after trending entry → regime_shift exit.
    // Reproduces the migration target: `RegimeLabel::AntiPersistent || Random`.
    // AntiPersistent 出場觸發 regime_shift；對應 migration target。
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0;
    let trending = || {
        Some(HurstResult {
            hurst: 0.7,
            regime: "trending".into(),
        })
    };
    let anti = || {
        Some(HurstResult {
            hurst: 0.4,
            regime: "mean_reverting".into(),
        })
    };
    s.on_tick(&ctx(0.01, 0.5, 1.0, 0));
    s.on_tick(&ctx_ext(0.05, 1.1, 2.0, 700_000, 50000.0, None, trending()));
    let i = s.on_tick(&ctx_ext(0.05, 1.1, 2.0, 1_400_000, 51000.0, None, anti()));
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Close { reason, .. } => {
            assert_eq!(
                reason, "regime_shift",
                "AntiPersistent must trigger regime_shift exit"
            );
        }
        other => panic!("expected Close, got {:?}", other),
    }
}

#[test]
fn test_phase_b_random_walk_triggers_regime_shift_exit() {
    // After trending entry, regime drifting to Random (not AntiPersistent)
    // must still trigger regime_shift exit — `Random || AntiPersistent`.
    // 從 Persistent 漂回 Random 也必須觸發 regime_shift 出場。
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0;
    let trending = || {
        Some(HurstResult {
            hurst: 0.7,
            regime: "trending".into(),
        })
    };
    let random = || {
        Some(HurstResult {
            hurst: 0.55,
            regime: "random_walk".into(),
        })
    };
    s.on_tick(&ctx(0.01, 0.5, 1.0, 0));
    s.on_tick(&ctx_ext(0.05, 1.1, 2.0, 700_000, 50000.0, None, trending()));
    let i = s.on_tick(&ctx_ext(0.05, 1.1, 2.0, 1_400_000, 51000.0, None, random()));
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Close { reason, .. } => {
            assert_eq!(
                reason, "regime_shift",
                "Random regime must trigger regime_shift exit (drop from Persistent)"
            );
        }
        other => panic!("expected Close, got {:?}", other),
    }
}

#[test]
fn test_phase_b_unknown_regime_string_treated_as_random() {
    // Defensive: an unrecognised regime string (e.g. data corruption upstream)
    // must map to `RegimeLabel::Random` via `from_legacy_str`. This proves the
    // typed migration preserves the legacy fail-safe (legacy code's _ branch).
    // 防禦性：未知 regime 字串映射為 Random，保留 legacy fail-safe 語意。
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0;
    let trending = || {
        Some(HurstResult {
            hurst: 0.7,
            regime: "trending".into(),
        })
    };
    let bogus = || {
        Some(HurstResult {
            hurst: 0.5,
            regime: "totally_invalid_label".into(),
        })
    };
    s.on_tick(&ctx(0.01, 0.5, 1.0, 0));
    s.on_tick(&ctx_ext(0.05, 1.1, 2.0, 700_000, 50000.0, None, trending()));
    // Unknown → Random → triggers regime_shift exit (Random branch matches).
    // 未知 → Random → 觸發 regime_shift（Random 分支命中）。
    let i = s.on_tick(&ctx_ext(0.05, 1.1, 2.0, 1_400_000, 51000.0, None, bogus()));
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Close { reason, .. } => {
            assert_eq!(
                reason, "regime_shift",
                "Unknown regime string must map to Random and trigger exit"
            );
        }
        other => panic!("expected Close, got {:?}", other),
    }
}
