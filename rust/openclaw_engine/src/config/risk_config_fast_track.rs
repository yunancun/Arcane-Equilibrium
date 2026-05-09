//! FastTrackConfig — emergency held-drop trigger thresholds.
//! FastTrackConfig — fast_track 緊急持倉跌幅觸發閾值。

use serde::{Deserialize, Serialize};

/// Operator-tunable fast-track held-drop thresholds.
///
/// Defaults preserve the prior hardcoded behavior:
/// - `extreme_drop_pct = 15.0`: CloseAll at any risk level.
/// - `moderate_drop_pct = 5.0` plus `outlier_sigma_threshold = 3.0`:
///   ReduceToHalf below Defensive, CloseAll at Defensive+.
///
/// Margin-crisis `90%` remains a physical exchange-safety constant inside
/// `fast_track.rs`, not a strategy tuning knob.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FastTrackConfig {
    #[serde(default = "default_fast_track_extreme_drop_pct")]
    pub extreme_drop_pct: f64,
    #[serde(default = "default_fast_track_moderate_drop_pct")]
    pub moderate_drop_pct: f64,
    #[serde(default = "default_fast_track_outlier_sigma_threshold")]
    pub outlier_sigma_threshold: f64,
}

fn default_fast_track_extreme_drop_pct() -> f64 {
    15.0
}

fn default_fast_track_moderate_drop_pct() -> f64 {
    5.0
}

fn default_fast_track_outlier_sigma_threshold() -> f64 {
    3.0
}

impl Default for FastTrackConfig {
    fn default() -> Self {
        Self {
            extreme_drop_pct: default_fast_track_extreme_drop_pct(),
            moderate_drop_pct: default_fast_track_moderate_drop_pct(),
            outlier_sigma_threshold: default_fast_track_outlier_sigma_threshold(),
        }
    }
}

impl FastTrackConfig {
    pub(super) fn validate(&self) -> Result<(), String> {
        validate_fast_track_pct("risk.fast_track.extreme_drop_pct", self.extreme_drop_pct)?;
        validate_fast_track_pct("risk.fast_track.moderate_drop_pct", self.moderate_drop_pct)?;
        if self.moderate_drop_pct >= self.extreme_drop_pct {
            return Err("risk.fast_track.moderate_drop_pct must be < extreme_drop_pct".into());
        }
        if !self.outlier_sigma_threshold.is_finite() || self.outlier_sigma_threshold <= 0.0 {
            return Err("risk.fast_track.outlier_sigma_threshold must be finite and > 0".into());
        }
        Ok(())
    }
}

fn validate_fast_track_pct(name: &str, value: f64) -> Result<(), String> {
    if !value.is_finite() || value <= 0.0 || value > 100.0 {
        return Err(format!("{name} must be finite and in (0, 100]"));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use crate::config::RiskConfig;

    #[test]
    fn test_w_audit_6_fast_track_defaults_preserve_legacy_thresholds() {
        let cfg = RiskConfig::default();
        assert!((cfg.fast_track.extreme_drop_pct - 15.0).abs() < f64::EPSILON);
        assert!((cfg.fast_track.moderate_drop_pct - 5.0).abs() < f64::EPSILON);
        assert!((cfg.fast_track.outlier_sigma_threshold - 3.0).abs() < f64::EPSILON);
        assert!(cfg.validate().is_ok());
    }

    #[test]
    fn test_w_audit_6_fast_track_validate_rejects_bad_thresholds() {
        let mut cfg = RiskConfig::default();

        cfg.fast_track.extreme_drop_pct = 0.0;
        assert!(cfg.validate().is_err(), "zero extreme pct must reject");

        cfg = RiskConfig::default();
        cfg.fast_track.moderate_drop_pct = f64::NAN;
        assert!(cfg.validate().is_err(), "NaN moderate pct must reject");

        cfg = RiskConfig::default();
        cfg.fast_track.moderate_drop_pct = 15.0;
        cfg.fast_track.extreme_drop_pct = 15.0;
        assert!(cfg.validate().is_err(), "moderate >= extreme must reject");

        cfg = RiskConfig::default();
        cfg.fast_track.outlier_sigma_threshold = f64::INFINITY;
        assert!(
            cfg.validate().is_err(),
            "infinite sigma threshold must reject"
        );

        cfg = RiskConfig::default();
        cfg.fast_track.outlier_sigma_threshold = 0.0;
        assert!(cfg.validate().is_err(), "zero sigma threshold must reject");
    }

    #[test]
    fn test_w_audit_6_fast_track_toml_roundtrip() {
        let mut cfg = RiskConfig::default();
        cfg.fast_track.extreme_drop_pct = 12.0;
        cfg.fast_track.moderate_drop_pct = 4.0;
        cfg.fast_track.outlier_sigma_threshold = 2.5;

        let toml_str = toml::to_string(&cfg).unwrap();
        let de: RiskConfig = toml::from_str(&toml_str).unwrap();

        assert!((de.fast_track.extreme_drop_pct - 12.0).abs() < f64::EPSILON);
        assert!((de.fast_track.moderate_drop_pct - 4.0).abs() < f64::EPSILON);
        assert!((de.fast_track.outlier_sigma_threshold - 2.5).abs() < f64::EPSILON);
        assert!(de.validate().is_ok());
    }

    #[test]
    fn test_w_audit_6_fast_track_partial_toml_falls_back_to_defaults() {
        let toml_str = r#"
            [meta]
            version = 1
            saved_ts_ms = 0
        "#;
        let cfg: RiskConfig = toml::from_str(toml_str).unwrap();
        assert!((cfg.fast_track.extreme_drop_pct - 15.0).abs() < f64::EPSILON);
        assert!((cfg.fast_track.moderate_drop_pct - 5.0).abs() < f64::EPSILON);
        assert!((cfg.fast_track.outlier_sigma_threshold - 3.0).abs() < f64::EPSILON);
        assert!(cfg.validate().is_ok());
    }
}
