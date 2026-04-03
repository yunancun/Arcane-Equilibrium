//! Engine configuration with cold/warm parameter marking [V3-PA-5].
//! 引擎配置，含冷/熱參數標記。

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Cold/warm parameter classification [V3-PA-5].
/// 冷/熱參數分類。
///
/// Cold: set at startup, requires restart to change.
/// Warm: can be adjusted at runtime via SIGHUP or API.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum ParamTemperature {
    /// Rarely changes, set at startup.
    Cold,
    /// Can be adjusted at runtime.
    Warm,
}

impl std::fmt::Display for ParamTemperature {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Cold => write!(f, "cold"),
            Self::Warm => write!(f, "warm"),
        }
    }
}

/// Complete engine configuration.
/// 完整引擎配置。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EngineConfig {
    /// Strategy scan interval (seconds) — WARM.
    #[serde(default = "default_scan_interval")]
    pub strategy_scan_interval_s: u32,

    /// H0 Gate max data age (ms) — COLD.
    #[serde(default = "default_max_data_age")]
    pub h0_max_data_age_ms: u64,

    /// Max concurrent positions — WARM.
    #[serde(default = "default_max_positions")]
    pub max_open_positions: u32,

    /// Risk monitoring enabled — COLD.
    #[serde(default = "default_true")]
    pub risk_monitoring_enabled: bool,

    /// Governance mode string — COLD.
    #[serde(default = "default_governance_mode")]
    pub governance_mode: String,

    /// Allowed asset categories — COLD.
    #[serde(default = "default_categories")]
    pub allowed_categories: Vec<String>,

    /// Parameter temperature classification.
    #[serde(default = "default_param_temps")]
    pub parameter_temps: HashMap<String, ParamTemperature>,
}

impl Default for EngineConfig {
    fn default() -> Self {
        Self {
            strategy_scan_interval_s: default_scan_interval(),
            h0_max_data_age_ms: default_max_data_age(),
            max_open_positions: default_max_positions(),
            risk_monitoring_enabled: true,
            governance_mode: default_governance_mode(),
            allowed_categories: default_categories(),
            parameter_temps: default_param_temps(),
        }
    }
}

impl EngineConfig {
    /// Validate configuration consistency.
    /// 驗證配置一致性。
    pub fn validate(&self) -> Result<(), String> {
        if self.max_open_positions == 0 {
            return Err("max_open_positions must be > 0".into());
        }
        if self.allowed_categories.is_empty() {
            return Err("allowed_categories cannot be empty".into());
        }
        Ok(())
    }

    /// Check if a named parameter is cold (requires restart).
    /// 檢查參數是否為冷參數（需重啟）。
    pub fn is_cold_param(&self, name: &str) -> bool {
        matches!(self.parameter_temps.get(name), Some(ParamTemperature::Cold))
    }

    /// Get all warm parameters (safe to hot-reload).
    /// 獲取所有熱參數（可安全熱加載）。
    pub fn warm_params(&self) -> Vec<&str> {
        self.parameter_temps
            .iter()
            .filter(|(_, t)| **t == ParamTemperature::Warm)
            .map(|(k, _)| k.as_str())
            .collect()
    }
}

fn default_scan_interval() -> u32 {
    1800
}
fn default_max_data_age() -> u64 {
    1000
}
fn default_max_positions() -> u32 {
    10
}
fn default_true() -> bool {
    true
}
fn default_governance_mode() -> String {
    "NORMAL".into()
}
fn default_categories() -> Vec<String> {
    vec!["linear".into(), "inverse".into(), "spot".into()]
}
fn default_param_temps() -> HashMap<String, ParamTemperature> {
    let mut m = HashMap::new();
    m.insert("h0_max_data_age_ms".into(), ParamTemperature::Cold);
    m.insert("allowed_categories".into(), ParamTemperature::Cold);
    m.insert("governance_mode".into(), ParamTemperature::Cold);
    m.insert("risk_monitoring_enabled".into(), ParamTemperature::Cold);
    m.insert("strategy_scan_interval_s".into(), ParamTemperature::Warm);
    m.insert("max_open_positions".into(), ParamTemperature::Warm);
    m
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_engine_config_default_valid() {
        let cfg = EngineConfig::default();
        assert!(cfg.validate().is_ok());
    }

    #[test]
    fn test_engine_config_invalid_positions() {
        let mut cfg = EngineConfig::default();
        cfg.max_open_positions = 0;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_cold_warm_classification() {
        let cfg = EngineConfig::default();
        assert!(cfg.is_cold_param("h0_max_data_age_ms"));
        assert!(!cfg.is_cold_param("strategy_scan_interval_s"));
        assert!(!cfg.is_cold_param("nonexistent_param"));
    }

    #[test]
    fn test_warm_params_list() {
        let cfg = EngineConfig::default();
        let warm = cfg.warm_params();
        assert!(warm.contains(&"strategy_scan_interval_s"));
        assert!(warm.contains(&"max_open_positions"));
        assert!(!warm.contains(&"h0_max_data_age_ms"));
    }

    #[test]
    fn test_engine_config_serde_roundtrip() {
        let cfg = EngineConfig::default();
        let json = serde_json::to_string_pretty(&cfg).unwrap();
        let de: EngineConfig = serde_json::from_str(&json).unwrap();
        assert_eq!(de.max_open_positions, cfg.max_open_positions);
        assert_eq!(de.governance_mode, "NORMAL");
    }

    #[test]
    fn test_engine_config_from_partial_json() {
        // Ensure defaults fill in missing fields.
        let json = r#"{"max_open_positions": 25}"#;
        let cfg: EngineConfig = serde_json::from_str(json).unwrap();
        assert_eq!(cfg.max_open_positions, 25);
        assert_eq!(cfg.strategy_scan_interval_s, 1800);
        assert!(cfg.validate().is_ok());
    }
}
