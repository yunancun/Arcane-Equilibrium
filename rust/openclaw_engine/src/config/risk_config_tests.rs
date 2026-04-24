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
