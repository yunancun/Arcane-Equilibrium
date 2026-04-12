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
