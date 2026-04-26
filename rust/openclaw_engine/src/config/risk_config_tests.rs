//! Tests for RiskConfig — extracted from risk_config.rs (FIX-08 file size).
//! RiskConfig 測試 — 從 risk_config.rs 提取（FIX-08 文件大小）。

use super::*;

#[test]
fn test_default_validates() {
    let cfg = RiskConfig::default();
    assert!(cfg.validate().is_ok(), "{:?}", cfg.validate());
}

#[test]
fn test_default_limits_match_python_legacy() {
    // Sanity-check that default values still match Python operator_risk_config.json
    // intent (so legacy migration round-trips).
    // 健全性檢查：預設值仍與 Python operator_risk_config.json 對齊。
    let l = GlobalLimits::default();
    assert_eq!(l.stop_loss_max_pct, 5.0);
    assert_eq!(l.take_profit_max_pct, 20.0);
    assert_eq!(l.position_size_max_pct, 20.0);
    assert_eq!(l.leverage_max, 20.0);
    assert_eq!(l.session_drawdown_max_pct, 15.0);
    assert_eq!(l.daily_loss_max_pct, 5.0);
    assert_eq!(l.holding_hours_max, 72.0);
}

#[test]
fn test_invalid_stop_loss_rejected() {
    let mut cfg = RiskConfig::default();
    cfg.limits.stop_loss_max_pct = 150.0;
    assert!(cfg.validate().is_err());
}

#[test]
fn test_invalid_leverage_rejected() {
    let mut cfg = RiskConfig::default();
    cfg.limits.leverage_max = 0.5;
    assert!(cfg.validate().is_err());
}

#[test]
fn test_zero_open_positions_rejected() {
    let mut cfg = RiskConfig::default();
    cfg.limits.open_positions_max = 0;
    assert!(cfg.validate().is_err());
}

#[test]
fn test_invalid_margin_mode_rejected() {
    let mut cfg = RiskConfig::default();
    cfg.limits.margin_mode = "iceberg".into();
    assert!(cfg.validate().is_err());
}

#[test]
fn test_partial_tp_exceeds_max_rejected() {
    let mut cfg = RiskConfig::default();
    cfg.agent.partial_tp_enabled = true;
    cfg.agent.partial_tp_levels = vec![(2.0, 0.3), (50.0, 0.4)]; // 50 > max 20
    assert!(cfg.validate().is_err());
}

#[test]
fn test_partial_tp_under_max_accepted() {
    let mut cfg = RiskConfig::default();
    cfg.agent.partial_tp_enabled = true;
    cfg.agent.partial_tp_levels = vec![(2.0, 0.3), (5.0, 0.4), (10.0, 0.3)];
    assert!(cfg.validate().is_ok());
}

#[test]
fn test_partial_tp_invalid_fraction_rejected() {
    let mut cfg = RiskConfig::default();
    cfg.agent.partial_tp_enabled = true;
    cfg.agent.partial_tp_levels = vec![(2.0, 1.5)];
    assert!(cfg.validate().is_err());
}

#[test]
fn test_partial_tp_disabled_skips_validation() {
    let mut cfg = RiskConfig::default();
    cfg.agent.partial_tp_enabled = false;
    cfg.agent.partial_tp_levels = vec![(999.0, 999.0)]; // garbage but disabled
    assert!(cfg.validate().is_ok());
}

#[test]
fn test_min_order_notional_exceeds_max_rejected() {
    let mut cfg = RiskConfig::default();
    cfg.limits.min_order_notional_usdt = 500.0;
    cfg.limits.max_order_notional_usdt = 100.0;
    assert!(cfg.validate().is_err());
}

#[test]
fn test_size_multiplier_out_of_range_rejected() {
    let mut cfg = RiskConfig::default();
    cfg.agent.size_multiplier = 1.5;
    assert!(cfg.validate().is_err());
}

#[test]
fn test_cascade_drawdown_non_increasing_rejected() {
    let mut cfg = RiskConfig::default();
    cfg.cascade.drawdown_reduced_pct = 3.0; // < cautious 5.0
    assert!(cfg.validate().is_err());
}

#[test]
fn test_cascade_consec_loss_non_increasing_rejected() {
    let mut cfg = RiskConfig::default();
    cfg.cascade.consec_loss_reduced = 2; // < cautious 3
    assert!(cfg.validate().is_err());
}

#[test]
fn test_regime_default_lookups() {
    let r = RegimeMultipliers::default();
    assert_eq!(r.get("trending").stop, 1.0);
    assert_eq!(r.get("trending").tp, 1.5);
    assert_eq!(r.get("volatile").stop, 1.5);
    assert_eq!(r.get("squeeze").stop, 0.6);
    assert_eq!(r.get("nonexistent").stop, 1.0); // fall back to unknown
}

#[test]
fn test_regime_negative_multiplier_rejected() {
    let mut cfg = RiskConfig::default();
    cfg.regime.trending.stop = -1.0;
    assert!(cfg.validate().is_err());
}

#[test]
fn test_dynamic_stop_base_exceeds_cap_rejected() {
    let mut cfg = RiskConfig::default();
    cfg.dynamic_stop.base_ratio = 0.9;
    cfg.dynamic_stop.cap_ratio = 0.5;
    assert!(cfg.validate().is_err());
}

#[test]
fn test_market_gate_invalid_imbalance_rejected() {
    let mut cfg = RiskConfig::default();
    cfg.market_gate.max_ob_imbalance = 1.5;
    assert!(cfg.validate().is_err());
}

#[test]
fn test_anti_cluster_offset_too_large_rejected() {
    let mut cfg = RiskConfig::default();
    cfg.anti_cluster.offset_fraction = 0.6;
    assert!(cfg.validate().is_err());
}

#[test]
fn test_anti_cluster_max_same_direction_default() {
    let cfg = RiskConfig::default();
    assert_eq!(cfg.anti_cluster.max_same_direction, 3);
}

#[test]
fn test_anti_cluster_max_same_direction_zero_rejected() {
    let mut cfg = RiskConfig::default();
    cfg.anti_cluster.max_same_direction = 0;
    assert!(cfg.validate().is_err());
}

#[test]
fn test_anti_cluster_max_same_direction_over_limit_rejected() {
    let mut cfg = RiskConfig::default();
    cfg.anti_cluster.max_same_direction = 101;
    assert!(cfg.validate().is_err());
}

#[test]
fn test_correlation_invalid_r_rejected() {
    let mut cfg = RiskConfig::default();
    cfg.correlation.max_pairwise_r = 1.5;
    assert!(cfg.validate().is_err());
}

#[test]
fn test_strategy_override_default_enabled() {
    let so = StrategyOverride::default();
    assert!(so.enabled);
}

#[test]
fn test_per_strategy_pause_via_override() {
    let mut cfg = RiskConfig::default();
    cfg.per_strategy.insert(
        "ma_crossover".into(),
        StrategyOverride {
            enabled: false,
            ..Default::default()
        },
    );
    assert!(cfg.validate().is_ok());
    assert!(!cfg.per_strategy["ma_crossover"].enabled);
}

#[test]
fn test_toml_round_trip_default() {
    let cfg = RiskConfig::default();
    let toml_str = toml::to_string(&cfg).unwrap();
    let de: RiskConfig = toml::from_str(&toml_str).unwrap();
    assert!(de.validate().is_ok());
    assert_eq!(de.limits.stop_loss_max_pct, 5.0);
}

#[test]
fn test_json_round_trip_with_overrides() {
    let mut cfg = RiskConfig::default();
    cfg.limits.stop_loss_max_pct = 3.5;
    cfg.agent.size_multiplier = 0.5;
    cfg.regime.trending.tp = 2.0;
    let json = serde_json::to_string(&cfg).unwrap();
    let de: RiskConfig = serde_json::from_str(&json).unwrap();
    assert_eq!(de.limits.stop_loss_max_pct, 3.5);
    assert_eq!(de.agent.size_multiplier, 0.5);
    assert_eq!(de.regime.trending.tp, 2.0);
    assert!(de.validate().is_ok());
}

#[test]
fn test_partial_toml_uses_defaults() {
    let toml_str = r#"
[limits]
stop_loss_max_pct = 3.0

[agent]
size_multiplier = 0.7
"#;
    let cfg: RiskConfig = toml::from_str(toml_str).unwrap();
    assert_eq!(cfg.limits.stop_loss_max_pct, 3.0);
    assert_eq!(cfg.agent.size_multiplier, 0.7);
    // Defaults preserved / 預設值保留
    assert_eq!(cfg.limits.take_profit_max_pct, 20.0);
    assert_eq!(cfg.regime.trending.tp, 1.5);
    assert!(cfg.validate().is_ok());
}

// ---------------------------------------------------------------------------
// EdgePredictor (EDGE-P3-1) — spec §7.3 defaults + invariants
// ---------------------------------------------------------------------------

#[test]
fn test_edge_predictor_default_is_off_shadow_on() {
    let cfg = EdgePredictor::default();
    // Stage 0: predictor totally off, shadow-true is irrelevant until use flips.
    // Stage 0：完全關閉，shadow_mode=true 在 use=false 時無意義。
    assert!(!cfg.use_edge_predictor);
    assert!(cfg.shadow_mode);
    assert_eq!(cfg.quantile_safety_k, 0.5);
    assert!(cfg.require_q10_positive_for_adds);
    assert_eq!(cfg.fallback_on_error, EdgePredictorFallback::Shrinkage);
    assert_eq!(cfg.exploration_rate, 0.05);
    assert_eq!(cfg.retrain_cadence_seconds, 604_800);
    assert_eq!(cfg.model_max_age_seconds, 1_209_600);
}

#[test]
fn test_edge_predictor_default_validates() {
    assert!(EdgePredictor::default().validate().is_ok());
}

#[test]
fn test_edge_predictor_quantile_k_bounds() {
    let mut cfg = EdgePredictor::default();
    cfg.quantile_safety_k = -0.01;
    assert!(cfg.validate().is_err());
    cfg.quantile_safety_k = 1.01;
    assert!(cfg.validate().is_err());
    cfg.quantile_safety_k = 0.0;
    assert!(cfg.validate().is_ok());
    cfg.quantile_safety_k = 1.0;
    assert!(cfg.validate().is_ok());
}

#[test]
fn test_edge_predictor_exploration_rate_bounds() {
    let mut cfg = EdgePredictor::default();
    cfg.exploration_rate = -0.01;
    assert!(cfg.validate().is_err());
    cfg.exploration_rate = 0.21;
    assert!(cfg.validate().is_err());
    cfg.exploration_rate = 0.0;
    assert!(cfg.validate().is_ok());
    cfg.exploration_rate = 0.2;
    assert!(cfg.validate().is_ok());
}

#[test]
fn test_edge_predictor_zero_durations_rejected() {
    let mut cfg = EdgePredictor::default();
    cfg.retrain_cadence_seconds = 0;
    assert!(cfg.validate().is_err());
    cfg.retrain_cadence_seconds = 1;
    cfg.model_max_age_seconds = 0;
    assert!(cfg.validate().is_err());
}

#[test]
fn test_edge_predictor_toml_partial_defaults() {
    // Operator only sets what they care about; other fields hold defaults.
    // 操作員只改關心的欄位，其餘保持默認。
    let toml_str = r#"
[edge_predictor]
use_edge_predictor = true
shadow_mode = false
"#;
    let cfg: RiskConfig = toml::from_str(toml_str).unwrap();
    assert!(cfg.edge_predictor.use_edge_predictor);
    assert!(!cfg.edge_predictor.shadow_mode);
    assert_eq!(cfg.edge_predictor.quantile_safety_k, 0.5);
    assert_eq!(cfg.edge_predictor.exploration_rate, 0.05);
    assert_eq!(cfg.edge_predictor.model_max_age_seconds, 1_209_600);
    assert!(cfg.validate().is_ok());
}

#[test]
fn test_edge_predictor_toml_fallback_snake_case() {
    let toml_str = r#"
[edge_predictor]
fallback_on_error = "fail_closed"
"#;
    let cfg: RiskConfig = toml::from_str(toml_str).unwrap();
    assert_eq!(
        cfg.edge_predictor.fallback_on_error,
        EdgePredictorFallback::FailClosed
    );
}

#[test]
fn test_edge_predictor_empty_section_all_defaults() {
    // Missing section entirely → #[serde(default)] on RiskConfig field.
    let toml_str = r#"[limits]
stop_loss_max_pct = 3.0
"#;
    let cfg: RiskConfig = toml::from_str(toml_str).unwrap();
    assert!(!cfg.edge_predictor.use_edge_predictor);
    assert!(cfg.edge_predictor.shadow_mode);
    assert!(cfg.validate().is_ok());
}

#[test]
fn test_edge_predictor_roundtrip_preserves_values() {
    let original = EdgePredictor {
        use_edge_predictor: true,
        shadow_mode: false,
        quantile_safety_k: 0.75,
        require_q10_positive_for_adds: false,
        fallback_on_error: EdgePredictorFallback::FailClosed,
        exploration_rate: 0.1,
        retrain_cadence_seconds: 86_400,
        model_max_age_seconds: 604_800,
    };
    let s = toml::to_string(&original).unwrap();
    let restored: EdgePredictor = toml::from_str(&s).unwrap();
    assert_eq!(restored.use_edge_predictor, original.use_edge_predictor);
    assert_eq!(restored.shadow_mode, original.shadow_mode);
    assert_eq!(restored.quantile_safety_k, original.quantile_safety_k);
    assert_eq!(
        restored.require_q10_positive_for_adds,
        original.require_q10_positive_for_adds
    );
    assert_eq!(restored.fallback_on_error, original.fallback_on_error);
    assert_eq!(restored.exploration_rate, original.exploration_rate);
    assert_eq!(
        restored.retrain_cadence_seconds,
        original.retrain_cadence_seconds
    );
    assert_eq!(
        restored.model_max_age_seconds,
        original.model_max_age_seconds
    );
}

// ---------------------------------------------------------------------------
// MICRO-PROFIT-FIX-1 (2026-04-17): ft_min_notional_ratio_of_entry
// ---------------------------------------------------------------------------

#[test]
fn test_ft_min_notional_ratio_default_0_25() {
    // Default must be 0.25 ("halve twice then stop") per worklog §3.1.
    // Default 必須為 0.25（halve 兩次後停手）。
    let l = GlobalLimits::default();
    assert!((l.ft_min_notional_ratio_of_entry - 0.25).abs() < f64::EPSILON);
}

#[test]
fn test_ft_min_notional_ratio_out_of_range_rejected() {
    // Range is [0, 1]; negatives and > 1 must be rejected.
    // 範圍 [0, 1]；負值與 > 1 必須被拒絕。
    let mut cfg = RiskConfig::default();
    cfg.limits.ft_min_notional_ratio_of_entry = -0.01;
    assert!(cfg.validate().is_err());
    cfg.limits.ft_min_notional_ratio_of_entry = 1.01;
    assert!(cfg.validate().is_err());
}

#[test]
fn test_ft_min_notional_ratio_boundaries_accepted() {
    // 0.0 (disables filter) and 1.0 (most restrictive) are both inclusive-valid.
    // 0.0（關閉過濾）與 1.0（最嚴）皆在合法範圍內。
    let mut cfg = RiskConfig::default();
    cfg.limits.ft_min_notional_ratio_of_entry = 0.0;
    assert!(cfg.validate().is_ok());
    cfg.limits.ft_min_notional_ratio_of_entry = 1.0;
    assert!(cfg.validate().is_ok());
}

#[test]
fn test_ft_min_notional_ratio_serialization_roundtrip() {
    let mut cfg = RiskConfig::default();
    cfg.limits.ft_min_notional_ratio_of_entry = 0.4;
    let json = serde_json::to_string(&cfg).unwrap();
    let de: RiskConfig = serde_json::from_str(&json).unwrap();
    assert!((de.limits.ft_min_notional_ratio_of_entry - 0.4).abs() < f64::EPSILON);
    let toml_str = toml::to_string(&cfg).unwrap();
    let de2: RiskConfig = toml::from_str(&toml_str).unwrap();
    assert!((de2.limits.ft_min_notional_ratio_of_entry - 0.4).abs() < f64::EPSILON);
}

// ---------------------------------------------------------------------------
// EXIT-FEATURES-WRITER-BUG-1-FIX (2026-04-26): ft_dust_qty_floor_usd schema +
// validate + serde tests. Pin default 1 USD, [0, 100_000] range, NaN reject,
// and TOML roundtrip so future schema drift fails loudly. MIT audit
// `2026-04-26--exit_features_writer_bug_audit.md` §4 RCA-A new knob.
// ---------------------------------------------------------------------------

#[test]
fn test_ft_dust_qty_floor_default_1_usd() {
    // Default 1 USD — large enough to swallow sub-cent dust residues yet small
    // enough to never block a real position halving. Pinned by both
    // GlobalLimits::default() and full RiskConfig::default() round-trip.
    // 預設 1 USD — 足夠捕捉 sub-cent dust 卻不擋真實倉位半倉。
    let l = GlobalLimits::default();
    assert!((l.ft_dust_qty_floor_usd - 1.0).abs() < f64::EPSILON);
    let cfg = RiskConfig::default();
    assert!((cfg.limits.ft_dust_qty_floor_usd - 1.0).abs() < f64::EPSILON);
    assert!(cfg.validate().is_ok(), "default dust floor must validate");
}

#[test]
fn test_ft_dust_qty_floor_out_of_range_rejected() {
    // Range is [0, 100_000]. Negatives + above-cap + NaN must all reject.
    // 範圍 [0, 100000]；負值 / 超上限 / NaN 一律拒絕。
    let mut cfg = RiskConfig::default();
    cfg.limits.ft_dust_qty_floor_usd = -0.01;
    assert!(
        cfg.validate().is_err(),
        "negative dust floor must reject"
    );
    cfg.limits.ft_dust_qty_floor_usd = 100_000.01;
    assert!(
        cfg.validate().is_err(),
        "above-cap dust floor must reject (operator typo guard)"
    );
    cfg.limits.ft_dust_qty_floor_usd = f64::NAN;
    assert!(
        cfg.validate().is_err(),
        "NaN dust floor must reject (silent disable)"
    );
    cfg.limits.ft_dust_qty_floor_usd = f64::INFINITY;
    assert!(
        cfg.validate().is_err(),
        "infinity dust floor must reject (operator typo guard)"
    );
}

#[test]
fn test_ft_dust_qty_floor_boundaries_accepted() {
    // 0.0 (filter disabled) and 100_000 (maximum sane ceiling) inclusive-valid.
    // 0.0（關閉）與 100000（合理上限）皆合法。
    let mut cfg = RiskConfig::default();
    cfg.limits.ft_dust_qty_floor_usd = 0.0;
    assert!(
        cfg.validate().is_ok(),
        "0.0 dust floor must validate (filter disabled)"
    );
    cfg.limits.ft_dust_qty_floor_usd = 100_000.0;
    assert!(
        cfg.validate().is_ok(),
        "100000 dust floor must validate (upper boundary)"
    );
}

#[test]
fn test_ft_dust_qty_floor_serialization_roundtrip() {
    // TOML + JSON roundtrip — operator-edit TOML must persist faithfully and
    // patch_risk_config IPC (JSON) must preserve the field bit-exactly.
    // TOML + JSON 雙向往返 — operator 編輯與 IPC patch 都必須位元保真。
    let mut cfg = RiskConfig::default();
    cfg.limits.ft_dust_qty_floor_usd = 5.5;
    let json = serde_json::to_string(&cfg).unwrap();
    let de: RiskConfig = serde_json::from_str(&json).unwrap();
    assert!((de.limits.ft_dust_qty_floor_usd - 5.5).abs() < f64::EPSILON);
    let toml_str = toml::to_string(&cfg).unwrap();
    let de2: RiskConfig = toml::from_str(&toml_str).unwrap();
    assert!((de2.limits.ft_dust_qty_floor_usd - 5.5).abs() < f64::EPSILON);
}

#[test]
fn test_ft_dust_qty_floor_legacy_toml_default_applied() {
    // A legacy TOML missing `ft_dust_qty_floor_usd` (e.g. operator's existing
    // `risk_config_*.toml` written before this commit) must deserialize with
    // the field defaulted to 1.0 — operators on live config should NOT need to
    // edit TOML manually for the fix to take effect.
    // 舊版 TOML（本 commit 前的 `risk_config_*.toml`）缺欄位時必須 default 為
    // 1.0，operator 不需手動編輯就能享受 fix。
    let toml_str = r#"
[meta]
version = 1

[limits]
stop_loss_max_pct = 5.0
ft_min_notional_ratio_of_entry = 0.25
"#;
    let cfg: RiskConfig = toml::from_str(toml_str).unwrap();
    assert!(
        (cfg.limits.ft_dust_qty_floor_usd - 1.0).abs() < f64::EPSILON,
        "legacy TOML must inherit default 1.0 USD dust floor"
    );
    assert!(cfg.validate().is_ok());
}

// ----- G7-01 (2026-04-24): Kelly tier boundary TOML configurability -----

#[test]
fn test_g7_01_kelly_tier_default_50_200() {
    // Default RiskConfig must have Kelly thresholds = 50 / 200 (mirrors
    // ml::kelly_sizer::KellyConfig defaults; preserves pre-G7-01 behavior).
    // 預設 RiskConfig 的 Kelly 門檻必須為 50/200，保留 G7-01 前行為。
    let cfg = RiskConfig::default();
    assert_eq!(cfg.kelly.young_threshold, 50);
    assert_eq!(cfg.kelly.mature_threshold, 200);
    assert!(cfg.validate().is_ok(), "default Kelly config must validate");
}

#[test]
fn test_g7_01_kelly_tier_validate_rejects_inverted_and_zero() {
    // young >= mature must be rejected; either-zero must be rejected.
    // young >= mature 必須拒絕；任一為 0 必須拒絕。
    let mut cfg = RiskConfig::default();

    cfg.kelly.young_threshold = 200;
    cfg.kelly.mature_threshold = 50;
    assert!(cfg.validate().is_err(), "young > mature must reject");

    cfg.kelly.young_threshold = 100;
    cfg.kelly.mature_threshold = 100;
    assert!(cfg.validate().is_err(), "young == mature must reject");

    cfg.kelly.young_threshold = 0;
    cfg.kelly.mature_threshold = 200;
    assert!(cfg.validate().is_err(), "young == 0 must reject");

    cfg.kelly.young_threshold = 50;
    cfg.kelly.mature_threshold = 0;
    assert!(cfg.validate().is_err(), "mature == 0 must reject");
}

#[test]
fn test_g7_01_kelly_tier_toml_roundtrip() {
    // Custom thresholds must survive TOML round-trip cleanly.
    // 自訂門檻必須無損穿越 TOML round-trip。
    let mut cfg = RiskConfig::default();
    cfg.kelly.young_threshold = 30;
    cfg.kelly.mature_threshold = 150;
    let toml_str = toml::to_string(&cfg).unwrap();
    let de: RiskConfig = toml::from_str(&toml_str).unwrap();
    assert_eq!(de.kelly.young_threshold, 30);
    assert_eq!(de.kelly.mature_threshold, 150);
    assert!(de.validate().is_ok());
}

#[test]
fn test_g7_01_kelly_tier_partial_toml_falls_back_to_defaults() {
    // [kelly] section absent in TOML → defaults 50/200 apply via #[serde(default)].
    // TOML 缺 [kelly] 區段時，#[serde(default)] 應補回 50/200。
    let toml_str = r#"
        [meta]
        version = 1
        saved_ts_ms = 0
    "#;
    let cfg: RiskConfig = toml::from_str(toml_str).unwrap();
    assert_eq!(cfg.kelly.young_threshold, 50);
    assert_eq!(cfg.kelly.mature_threshold, 200);
    assert!(cfg.validate().is_ok());
}

// ----- G3-02 Phase A (2026-04-25): ExecutorConfig schema + validation -----

#[test]
fn test_g3_02_executor_default_shadow_true_5pct() {
    // Phase A default preserves Python ExecutorAgent's pre-G3-02 forced-shadow
    // behavior. shadow_mode=true, max_position_pct=5%, no per-symbol overrides.
    // Phase A 預設保留 Python ExecutorAgent 強制 shadow 行為。
    let cfg = RiskConfig::default();
    assert!(cfg.executor.shadow_mode, "shadow_mode must default true");
    assert!((cfg.executor.max_position_pct - 0.05).abs() < 1e-12);
    assert!(cfg.executor.per_symbol_position_cap.is_empty());
    assert!(cfg.validate().is_ok());
}

#[test]
fn test_g3_02_executor_validate_rejects_out_of_range_max_position_pct() {
    // max_position_pct must be in [0.0, 1.0]; -0.1 / 1.1 must reject.
    // max_position_pct 必須在 [0.0, 1.0]；越界必拒。
    let mut cfg = RiskConfig::default();
    cfg.executor.max_position_pct = -0.1;
    assert!(cfg.validate().is_err(), "negative max_position_pct must reject");
    cfg.executor.max_position_pct = 1.1;
    assert!(cfg.validate().is_err(), "max_position_pct > 1.0 must reject");
    cfg.executor.max_position_pct = 0.0;
    assert!(cfg.validate().is_ok(), "0.0 (no-op) must accept");
    cfg.executor.max_position_pct = 1.0;
    assert!(cfg.validate().is_ok(), "1.0 (full margin) must accept");
}

#[test]
fn test_g3_02_executor_validate_rejects_bad_per_symbol_overrides() {
    // per_symbol fraction out-of-range or empty key must reject.
    // per_symbol fraction 越界或空 key 必拒。
    let mut cfg = RiskConfig::default();
    cfg.executor
        .per_symbol_position_cap
        .insert("BTCUSDT".into(), 1.5);
    assert!(
        cfg.validate().is_err(),
        "per_symbol fraction > 1.0 must reject"
    );

    cfg.executor.per_symbol_position_cap.clear();
    cfg.executor
        .per_symbol_position_cap
        .insert("ETHUSDT".into(), -0.05);
    assert!(
        cfg.validate().is_err(),
        "per_symbol fraction < 0.0 must reject"
    );

    cfg.executor.per_symbol_position_cap.clear();
    cfg.executor
        .per_symbol_position_cap
        .insert("".into(), 0.10);
    assert!(
        cfg.validate().is_err(),
        "empty symbol key must reject"
    );
}

#[test]
fn test_g3_02_executor_toml_roundtrip() {
    // Custom executor knobs must survive TOML round-trip.
    // 自訂 executor knob 必須無損穿越 TOML round-trip。
    let mut cfg = RiskConfig::default();
    cfg.executor.shadow_mode = false;
    cfg.executor.max_position_pct = 0.10;
    cfg.executor
        .per_symbol_position_cap
        .insert("BTCUSDT".into(), 0.15);
    cfg.executor
        .per_symbol_position_cap
        .insert("ETHUSDT".into(), 0.08);
    let toml_str = toml::to_string(&cfg).unwrap();
    let de: RiskConfig = toml::from_str(&toml_str).unwrap();
    assert!(!de.executor.shadow_mode);
    assert!((de.executor.max_position_pct - 0.10).abs() < 1e-12);
    assert_eq!(de.executor.per_symbol_position_cap.len(), 2);
    assert!(
        (de.executor.per_symbol_position_cap.get("BTCUSDT").copied().unwrap() - 0.15).abs()
            < 1e-12
    );
    assert!(de.validate().is_ok());
}

#[test]
fn test_g3_02_executor_partial_toml_falls_back_to_defaults() {
    // [executor] section absent → #[serde(default)] returns Phase A defaults.
    // TOML 缺 [executor] 區段時，#[serde(default)] 補回 Phase A 預設。
    let toml_str = r#"
        [meta]
        version = 1
        saved_ts_ms = 0
    "#;
    let cfg: RiskConfig = toml::from_str(toml_str).unwrap();
    assert!(cfg.executor.shadow_mode, "default shadow_mode must be true");
    assert!((cfg.executor.max_position_pct - 0.05).abs() < 1e-12);
    assert!(cfg.executor.per_symbol_position_cap.is_empty());
    assert!(cfg.validate().is_ok());
}

// ----- G7-02 (2026-04-24): EwmaVolConfig per-timeframe lambda configurability -----

#[test]
fn test_g7_02_ewma_vol_default_preserves_pre_g7_02_value() {
    // Default EwmaVolConfig must expose default_lambda = 0.97 (mirrors the
    // pre-G7-02 hardcoded constant in `IndicatorEngine::compute_all`) and an
    // empty per-tf overrides map; lambda_for_timeframe must fall back to
    // default_lambda for any timeframe.
    // 預設 EwmaVolConfig 的 default_lambda 必須為 0.97 保留 G7-02 前行為，
    // overrides 表為空時 lambda_for_timeframe 必回傳 default_lambda。
    let cfg = RiskConfig::default();
    assert!(
        (cfg.ewma_vol.default_lambda - 0.97).abs() < 1e-12,
        "default_lambda must be 0.97 (pre-G7-02 RiskMetrics value)"
    );
    assert!(
        cfg.ewma_vol.lambdas.is_empty(),
        "default lambdas map must be empty"
    );
    // Bit-identical to compute_all_with_lambda call from Core.
    assert!(
        (cfg.ewma_vol.lambda_for_timeframe("1m")
            - openclaw_core::indicators::DEFAULT_EWMA_VOL_LAMBDA)
            .abs()
            < 1e-12,
        "lambda_for_timeframe('1m') must equal core DEFAULT_EWMA_VOL_LAMBDA"
    );
    assert!(cfg.validate().is_ok(), "default ewma_vol must validate");
}

#[test]
fn test_g7_02_ewma_vol_validate_rejects_out_of_range() {
    // EWMA recursion needs 0 < lambda < 1 — both endpoints + negative + >=1
    // must be rejected. validate() should fail-fast at config-load time
    // instead of letting `ewma_vol()` return None silently every tick.
    // 0 < lambda < 1 開區間外的所有值（負/0/1/>1）都必須拒絕。
    let mut cfg = RiskConfig::default();
    cfg.ewma_vol.default_lambda = -0.1;
    assert!(cfg.validate().is_err(), "negative default_lambda must reject");
    cfg.ewma_vol.default_lambda = 0.0;
    assert!(cfg.validate().is_err(), "default_lambda == 0 must reject");
    cfg.ewma_vol.default_lambda = 1.0;
    assert!(cfg.validate().is_err(), "default_lambda == 1.0 must reject");
    cfg.ewma_vol.default_lambda = 1.5;
    assert!(cfg.validate().is_err(), "default_lambda > 1.0 must reject");
    cfg.ewma_vol.default_lambda = 0.94;
    assert!(cfg.validate().is_ok(), "0.94 (in-range) must accept");

    // Per-tf override out-of-range must reject as well.
    // Per-tf 覆寫越界亦必拒。
    cfg.ewma_vol.default_lambda = 0.97;
    cfg.ewma_vol.lambdas.insert("1m".into(), 1.5);
    assert!(cfg.validate().is_err(), "per-tf lambda > 1.0 must reject");
    cfg.ewma_vol.lambdas.clear();
    cfg.ewma_vol.lambdas.insert("5m".into(), 0.0);
    assert!(cfg.validate().is_err(), "per-tf lambda == 0 must reject");
    cfg.ewma_vol.lambdas.clear();
    cfg.ewma_vol.lambdas.insert("".into(), 0.95);
    assert!(cfg.validate().is_err(), "empty timeframe key must reject");
}

#[test]
fn test_g7_02_ewma_vol_toml_roundtrip() {
    // Custom default + per-tf overrides must survive TOML round-trip cleanly.
    // 自訂 default + per-tf 覆寫必須無損穿越 TOML round-trip。
    let mut cfg = RiskConfig::default();
    cfg.ewma_vol.default_lambda = 0.95;
    cfg.ewma_vol.lambdas.insert("1m".into(), 0.94);
    cfg.ewma_vol.lambdas.insert("5m".into(), 0.95);
    cfg.ewma_vol.lambdas.insert("1h".into(), 0.97);
    cfg.ewma_vol.lambdas.insert("4h".into(), 0.99);

    let toml_str = toml::to_string(&cfg).unwrap();
    let de: RiskConfig = toml::from_str(&toml_str).unwrap();

    assert!((de.ewma_vol.default_lambda - 0.95).abs() < 1e-12);
    assert_eq!(de.ewma_vol.lambdas.len(), 4);
    assert!((de.ewma_vol.lambda_for_timeframe("1m") - 0.94).abs() < 1e-12);
    assert!((de.ewma_vol.lambda_for_timeframe("5m") - 0.95).abs() < 1e-12);
    assert!((de.ewma_vol.lambda_for_timeframe("1h") - 0.97).abs() < 1e-12);
    assert!((de.ewma_vol.lambda_for_timeframe("4h") - 0.99).abs() < 1e-12);
    // Unconfigured timeframe must fall back to default_lambda.
    // 未設定 timeframe 必回退至 default_lambda。
    assert!((de.ewma_vol.lambda_for_timeframe("15m") - 0.95).abs() < 1e-12);
    assert!(de.validate().is_ok());
}

#[test]
fn test_g7_02_ewma_vol_partial_toml_falls_back_to_defaults() {
    // [ewma_vol] section absent → #[serde(default)] returns 0.97 + empty map,
    // preserving the pre-G7-02 runtime behavior bit-for-bit.
    // TOML 缺 [ewma_vol] 區段時，#[serde(default)] 補回 0.97 + 空表保留 G7-02 前行為。
    let toml_str = r#"
        [meta]
        version = 1
        saved_ts_ms = 0
    "#;
    let cfg: RiskConfig = toml::from_str(toml_str).unwrap();
    assert!((cfg.ewma_vol.default_lambda - 0.97).abs() < 1e-12);
    assert!(cfg.ewma_vol.lambdas.is_empty());
    assert!((cfg.ewma_vol.lambda_for_timeframe("anything") - 0.97).abs() < 1e-12);
    assert!(cfg.validate().is_ok());
}

#[test]
fn test_g7_02_ewma_vol_lambda_for_timeframe_lookup() {
    // Per-timeframe lookup must return the override when present and
    // default_lambda otherwise; ensures the helper used by the tick path is
    // semantically correct before relying on it for hot-path indicator calc.
    // lambda_for_timeframe 必須在有 override 時回傳 override，否則回 default_lambda；
    // 確保 tick 熱路徑指標計算所依賴的 helper 語義正確。
    let mut cfg = EwmaVolConfig::default();
    cfg.default_lambda = 0.97;
    cfg.lambdas.insert("1m".into(), 0.94);
    cfg.lambdas.insert("4h".into(), 0.99);

    assert!((cfg.lambda_for_timeframe("1m") - 0.94).abs() < 1e-12);
    assert!((cfg.lambda_for_timeframe("4h") - 0.99).abs() < 1e-12);
    // Missing 5m / 1h → default_lambda (0.97)
    assert!((cfg.lambda_for_timeframe("5m") - 0.97).abs() < 1e-12);
    assert!((cfg.lambda_for_timeframe("1h") - 0.97).abs() < 1e-12);
    // Unknown / empty key → default_lambda (must not panic).
    assert!((cfg.lambda_for_timeframe("random") - 0.97).abs() < 1e-12);
    assert!((cfg.lambda_for_timeframe("") - 0.97).abs() < 1e-12);
}

// ----- G7-04 (2026-04-24): CusumConfig strategy edge-decay monitor schema -----

#[test]
fn test_g7_04_cusum_default_disabled_with_canonical_constants() {
    // Phase A safe default: enabled=false (dormant) so no behavioural change
    // until Phase B+ runtime wiring lands. Numeric defaults match canonical
    // quant-control-chart literature: slack_k=0.5σ deadband, threshold_h=4σ
    // alarm boundary, min_observations=30 warm-up, target_return_bps=0
    // (breakeven net of fees).
    // Phase A 預設靜默 enabled=false；數值預設對齊標準 CUSUM 文獻
    // (slack_k=0.5σ, threshold_h=4σ, min_obs=30, target_return_bps=0)。
    let cfg = RiskConfig::default();
    assert!(!cfg.cusum.enabled, "Phase A default must be enabled=false");
    assert!(
        (cfg.cusum.slack_k - 0.5).abs() < 1e-12,
        "default slack_k must be 0.5σ"
    );
    assert!(
        (cfg.cusum.threshold_h - 4.0).abs() < 1e-12,
        "default threshold_h must be 4.0σ"
    );
    assert_eq!(
        cfg.cusum.min_observations, 30,
        "default min_observations must be 30"
    );
    assert!(
        (cfg.cusum.target_return_bps - 0.0).abs() < 1e-12,
        "default target_return_bps must be 0.0 (breakeven net of fees)"
    );
    assert!(cfg.validate().is_ok(), "default cusum must validate");
}

#[test]
fn test_g7_04_cusum_validate_rejects_nonpositive_slack_k() {
    // slack_k <= 0 collapses the deadband to zero, which makes any non-zero
    // drift instantly accumulate — degenerate; validate() must reject.
    // slack_k <= 0 死區為零退化為任意偏移即累積；validate() 必須拒絕。
    let mut cfg = RiskConfig::default();
    cfg.cusum.slack_k = 0.0;
    assert!(cfg.validate().is_err(), "slack_k == 0 must reject");
    cfg.cusum.slack_k = -0.1;
    assert!(cfg.validate().is_err(), "negative slack_k must reject");
    cfg.cusum.slack_k = 0.5;
    assert!(cfg.validate().is_ok(), "0.5 (default) must accept");
}

#[test]
fn test_g7_04_cusum_validate_rejects_slack_k_ge_threshold_h() {
    // slack_k >= threshold_h makes the σ-scaled threshold sit inside the
    // deadband — no alarm is reachable. validate() must reject this
    // configuration so the bug is caught at config-load time, not when an
    // operator wonders why no alarm ever fires after Phase B+ wiring.
    // slack_k >= threshold_h 警報閾值落入死區內無法觸發，必須在 config-load 時拒絕。
    let mut cfg = RiskConfig::default();
    cfg.cusum.slack_k = 4.0;
    cfg.cusum.threshold_h = 4.0;
    assert!(
        cfg.validate().is_err(),
        "slack_k == threshold_h must reject (no alarm room)"
    );
    cfg.cusum.slack_k = 5.0;
    cfg.cusum.threshold_h = 4.0;
    assert!(
        cfg.validate().is_err(),
        "slack_k > threshold_h must reject"
    );
    cfg.cusum.slack_k = 0.5;
    cfg.cusum.threshold_h = 4.0;
    assert!(cfg.validate().is_ok(), "slack_k < threshold_h must accept");
}

#[test]
fn test_g7_04_cusum_validate_rejects_threshold_h_out_of_range() {
    // threshold_h must be > 0 (alarm boundary at zero collapses to the
    // deadband) and <= 100 (sanity ceiling — beyond ~10σ the chart is
    // effectively unreachable). Both endpoints + negative + >100 reject.
    // threshold_h 必為 (0, 100]；超界（含 ≤0、>100）皆必拒絕。
    let mut cfg = RiskConfig::default();
    cfg.cusum.threshold_h = 0.0;
    assert!(cfg.validate().is_err(), "threshold_h == 0 must reject");
    cfg.cusum.threshold_h = -1.0;
    assert!(cfg.validate().is_err(), "negative threshold_h must reject");
    cfg.cusum.threshold_h = 101.0;
    assert!(
        cfg.validate().is_err(),
        "threshold_h > 100 must reject (sanity ceiling)"
    );
    cfg.cusum.threshold_h = 100.0;
    assert!(
        cfg.validate().is_ok(),
        "threshold_h == 100 (boundary) must accept"
    );
    cfg.cusum.threshold_h = 4.0;
    assert!(cfg.validate().is_ok(), "default 4.0 must accept");
}

#[test]
fn test_g7_04_cusum_validate_rejects_min_observations_below_5() {
    // min_observations < 5 makes the σ estimate degenerate (sub-handful of
    // samples) — validate() must reject so the chart only evaluates after
    // a meaningful warm-up.
    // min_observations < 5 樣本不足 σ 估計失效；validate() 必須拒絕。
    let mut cfg = RiskConfig::default();
    cfg.cusum.min_observations = 0;
    assert!(cfg.validate().is_err(), "min_observations == 0 must reject");
    cfg.cusum.min_observations = 4;
    assert!(cfg.validate().is_err(), "min_observations == 4 must reject");
    cfg.cusum.min_observations = 5;
    assert!(
        cfg.validate().is_ok(),
        "min_observations == 5 (boundary) must accept"
    );
    cfg.cusum.min_observations = 30;
    assert!(cfg.validate().is_ok(), "default 30 must accept");
}

#[test]
fn test_g7_04_cusum_toml_roundtrip_preserves_custom_values() {
    // Custom CUSUM values must survive TOML round-trip unchanged so operator
    // edits in [cusum] sections of risk_config_{demo,live,paper}.toml flow
    // back through the Rust ConfigStore correctly.
    // 自訂 cusum 值經 TOML round-trip 必須無損保留。
    let mut cfg = RiskConfig::default();
    cfg.cusum.enabled = true;
    cfg.cusum.slack_k = 0.75;
    cfg.cusum.threshold_h = 5.0;
    cfg.cusum.min_observations = 60;
    cfg.cusum.target_return_bps = -10.0;

    let toml_str = toml::to_string(&cfg).unwrap();
    let de: RiskConfig = toml::from_str(&toml_str).unwrap();

    assert!(de.cusum.enabled);
    assert!((de.cusum.slack_k - 0.75).abs() < 1e-12);
    assert!((de.cusum.threshold_h - 5.0).abs() < 1e-12);
    assert_eq!(de.cusum.min_observations, 60);
    assert!((de.cusum.target_return_bps - (-10.0)).abs() < 1e-12);
    assert!(de.validate().is_ok());
}

#[test]
fn test_g7_04_cusum_partial_toml_falls_back_to_defaults() {
    // [cusum] section absent → #[serde(default)] returns the canonical
    // dormant defaults (enabled=false / 0.5 / 4.0 / 30 / 0.0), preserving
    // the pre-G7-04 runtime behavior bit-for-bit.
    // TOML 缺 [cusum] 區段時，#[serde(default)] 補回靜默預設保留 G7-04 前行為。
    let toml_str = r#"
        [meta]
        version = 1
        saved_ts_ms = 0
    "#;
    let cfg: RiskConfig = toml::from_str(toml_str).unwrap();
    assert!(!cfg.cusum.enabled, "absent section must default to disabled");
    assert!((cfg.cusum.slack_k - 0.5).abs() < 1e-12);
    assert!((cfg.cusum.threshold_h - 4.0).abs() < 1e-12);
    assert_eq!(cfg.cusum.min_observations, 30);
    assert!((cfg.cusum.target_return_bps - 0.0).abs() < 1e-12);
    assert!(cfg.validate().is_ok());
}

// ----- STRATEGIST-TUNE-TARGET-CONFIG-1 (2026-04-25): StrategistConfig schema -----
// Lifts the previously hardcoded `MAX_PARAM_DELTA_PCT = 0.30` constant from
// `strategist_scheduler/mod.rs` into `RiskConfig.strategist.max_param_delta_pct`
// so the StrategistScheduler param tuner clamp becomes IPC-hot-reloadable.
// Default 0.30 preserves the pre-extraction behaviour bit-for-bit.

#[test]
fn test_strategist_config_defaults() {
    // Default `max_param_delta_pct = 0.30` must match the pre-extraction
    // hardcoded constant exactly (otherwise this landing silently changes the
    // clamp). Default RiskConfig must also pass validate().
    // 預設 max_param_delta_pct=0.30 必須與原硬編碼完全一致；validate() 必須通過。
    let cfg = StrategistConfig::default();
    assert!(
        (cfg.max_param_delta_pct - 0.30).abs() < 1e-12,
        "default max_param_delta_pct must be 0.30 (was hardcoded MAX_PARAM_DELTA_PCT)"
    );
    assert!(cfg.validate().is_ok(), "default StrategistConfig must validate");

    let rc = RiskConfig::default();
    assert!(
        (rc.strategist.max_param_delta_pct - 0.30).abs() < 1e-12,
        "RiskConfig::default().strategist.max_param_delta_pct must be 0.30"
    );
    assert!(rc.validate().is_ok(), "default RiskConfig must validate");
}

#[test]
fn test_strategist_config_validate_ok() {
    // Mid-interval values cover the design envelope: tight 0.05 (operator
    // wants very small per-cycle moves) through default 0.30 to relaxed 0.99
    // (just below the 1.0 ceiling). All three must validate.
    // 驗證 0.30 / 0.05 / 0.99 — 設計信封內的緊/中/鬆三個代表值，皆需通過。
    for v in [0.30_f64, 0.05_f64, 0.99_f64] {
        let cfg = StrategistConfig {
            max_param_delta_pct: v,
        };
        assert!(
            cfg.validate().is_ok(),
            "max_param_delta_pct={} must validate",
            v
        );
    }
}

#[test]
fn test_strategist_config_validate_rejects_zero_or_negative() {
    // ≤ 0 collapses the clamp to instantly-reject every recommendation
    // (delta_pct > 0 always) — degenerate. validate() must reject so a
    // misconfigured TOML can't reach the hot path.
    // ≤ 0 死區零退化為任意 delta 即拒絕；validate() 必須拒絕。
    for bad in [0.0_f64, -0.1_f64, -1.0_f64] {
        let cfg = StrategistConfig {
            max_param_delta_pct: bad,
        };
        assert!(
            cfg.validate().is_err(),
            "max_param_delta_pct={} must reject (≤ 0 collapses gate)",
            bad
        );
    }
}

#[test]
fn test_strategist_config_validate_rejects_ge_one() {
    // ≥ 1.0 means "≥100% delta accepted" which is wholesale parameter
    // replacement — defeats the purpose of a sanity gate. validate() must
    // reject the boundary and beyond.
    // ≥ 1.0 等於完全替換無意義；validate() 必須拒絕邊界 + 超界值。
    for bad in [1.0_f64, 1.5_f64, 2.0_f64, 100.0_f64] {
        let cfg = StrategistConfig {
            max_param_delta_pct: bad,
        };
        assert!(
            cfg.validate().is_err(),
            "max_param_delta_pct={} must reject (≥1.0 = wholesale replace)",
            bad
        );
    }
}

#[test]
fn test_strategist_config_validate_rejects_nan_inf() {
    // NaN comparisons are always false in Rust, so a NaN clamp would silently
    // pass through every recommendation regardless of delta. ±∞ is similarly
    // pathological. Fail fast at config-load time to surface the bug.
    // NaN 比較恆為 false 會讓 clamp 失效；±∞ 同樣病態，必須在 config-load 時拒絕。
    for bad in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
        let cfg = StrategistConfig {
            max_param_delta_pct: bad,
        };
        assert!(
            cfg.validate().is_err(),
            "max_param_delta_pct={:?} must reject (non-finite collapses gate)",
            bad
        );
    }
}

#[test]
fn test_strategist_config_toml_roundtrip() {
    // Operator-edited [strategist] section in risk_config_{demo,live,paper}.toml
    // must survive Rust ConfigStore reload bit-for-bit, otherwise an IPC
    // hot-reload would silently revert to defaults.
    // 自訂 [strategist] 經 TOML round-trip 必須無損保留。
    let toml_str = r#"
        [meta]
        version = 1
        saved_ts_ms = 0

        [strategist]
        max_param_delta_pct = 0.30
    "#;
    let cfg: RiskConfig = toml::from_str(toml_str).unwrap();
    assert!(
        (cfg.strategist.max_param_delta_pct - 0.30).abs() < 1e-12,
        "TOML [strategist] section must parse max_param_delta_pct=0.30"
    );
    assert!(cfg.validate().is_ok());

    // Round-trip via to_string + from_str preserves the value across the
    // serde boundary (catches any Serialize/Deserialize asymmetry).
    // Round-trip 也驗證 Serialize/Deserialize 對稱。
    let mut custom = RiskConfig::default();
    custom.strategist.max_param_delta_pct = 0.45;
    let s = toml::to_string(&custom).unwrap();
    let de: RiskConfig = toml::from_str(&s).unwrap();
    assert!((de.strategist.max_param_delta_pct - 0.45).abs() < 1e-12);
    assert!(de.validate().is_ok());
}

#[test]
fn test_strategist_config_partial_fallback() {
    // TOML missing [strategist] section entirely → #[serde(default)] returns
    // the canonical default (0.30), preserving the pre-extraction runtime
    // bit-for-bit. This is the path every existing live risk_config_*.toml
    // takes the first time the engine boots after this change lands.
    // TOML 缺 [strategist] 區段 → #[serde(default)] 補預設 0.30，保留現行為。
    // 此路徑為現存 risk_config_*.toml 在升級首啟時走的路徑。
    let toml_str = r#"
        [meta]
        version = 1
        saved_ts_ms = 0
    "#;
    let cfg: RiskConfig = toml::from_str(toml_str).unwrap();
    assert!(
        (cfg.strategist.max_param_delta_pct - 0.30).abs() < 1e-12,
        "absent [strategist] section must default to 0.30"
    );
    assert!(cfg.validate().is_ok());

    // Empty `[strategist]` section (operator left it blank intentionally) ->
    // same default fallback applies (#[serde(default = "...")]) on the field.
    // 空白 [strategist] 區段同樣回 0.30。
    let toml_empty = r#"
        [meta]
        version = 1
        saved_ts_ms = 0

        [strategist]
    "#;
    let cfg2: RiskConfig = toml::from_str(toml_empty).unwrap();
    assert!(
        (cfg2.strategist.max_param_delta_pct - 0.30).abs() < 1e-12,
        "empty [strategist] section must default to 0.30"
    );
    assert!(cfg2.validate().is_ok());
}

// G2-03 (2026-04-26) per-strategy override tests live in a dedicated sibling
// to keep this file under §九 1200-line cap.
// G2-03 每策略覆蓋測試在獨立 sibling，守 §九 1200 行上限。
#[path = "risk_config_per_strategy_tests.rs"]
mod g2_03_per_strategy_tests;
