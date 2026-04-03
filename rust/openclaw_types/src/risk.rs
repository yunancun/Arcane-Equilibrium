//! Risk control configurations, H0 Gate types, Guardian config.
//! 風控配置、H0 門控類型、Guardian 配置。

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// H0 Gate deterministic checks configuration.
/// H0 確定性門控參數配置。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct H0GateConfig {
    pub max_data_age_ms: u64,
    pub max_cpu_pct: f64,
    pub min_memory_mb: i32,
    pub max_db_latency_ms: f64,
    pub max_network_loss_pct: f64,
    pub allowed_categories: Vec<String>,
    pub max_open_positions: u32,
    pub max_total_exposure_pct: f64,
    pub health_snapshot_max_age_ms: u64,
    pub shadow_mode: bool,
}

impl Default for H0GateConfig {
    fn default() -> Self {
        Self {
            max_data_age_ms: 1000,
            max_cpu_pct: 90.0,
            min_memory_mb: 1024,
            max_db_latency_ms: 100.0,
            max_network_loss_pct: 5.0,
            allowed_categories: vec!["linear".into(), "inverse".into(), "spot".into()],
            max_open_positions: 10,
            max_total_exposure_pct: 90.0,
            health_snapshot_max_age_ms: 30_000,
            shadow_mode: false,
        }
    }
}

/// System health snapshot for H0 checks.
/// H0 檢查用系統健康快照。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct H0GateHealthSnapshot {
    pub cpu_pct: f64,
    pub memory_available_mb: i32,
    pub db_latency_ms: f64,
    pub network_loss_pct: f64,
    pub snapshot_ts_ms: u64,
}

impl Default for H0GateHealthSnapshot {
    fn default() -> Self {
        Self {
            cpu_pct: 0.0,
            memory_available_mb: 9999,
            db_latency_ms: 0.0,
            network_loss_pct: 0.0,
            snapshot_ts_ms: 0,
        }
    }
}

/// Risk state snapshot for H0 position/exposure checks.
/// H0 持倉/曝險檢查用風控狀態快照。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct H0GateRiskSnapshot {
    pub open_position_count: u32,
    pub total_exposure_pct: f64,
    pub cooldown_until_ts_ms: u64,
    pub kill_switch_active: bool,
    pub snapshot_ts_ms: u64,
}

impl Default for H0GateRiskSnapshot {
    fn default() -> Self {
        Self {
            open_position_count: 0,
            total_exposure_pct: 0.0,
            cooldown_until_ts_ms: 0,
            kill_switch_active: false,
            snapshot_ts_ms: 0,
        }
    }
}

/// H0 Gate check result (<1ms SLA).
/// H0 門控檢查結果（<1ms SLA）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct H0CheckResult {
    pub allowed: bool,
    pub reason: String,
    pub check_name: String,
    pub latency_us: u32,
}

impl H0CheckResult {
    pub fn allowed() -> Self {
        Self {
            allowed: true,
            reason: String::new(),
            check_name: "all_passed".into(),
            latency_us: 0,
        }
    }

    pub fn blocked(reason: String, check_name: String) -> Self {
        Self {
            allowed: false,
            reason,
            check_name,
            latency_us: 0,
        }
    }
}

/// Guardian agent risk configuration.
/// 守衛 Agent 風控配置。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GuardianConfig {
    pub max_position_size: f64,
    pub max_daily_drawdown_pct: f64,
    pub min_confidence: f64,
    pub max_leverage: f64,
    pub allowed_timeframes: Vec<String>,
}

impl Default for GuardianConfig {
    fn default() -> Self {
        Self {
            max_position_size: 1000.0,
            max_daily_drawdown_pct: 10.0,
            min_confidence: 0.5,
            max_leverage: 5.0,
            allowed_timeframes: vec![
                "1m".into(),
                "5m".into(),
                "15m".into(),
                "1h".into(),
                "4h".into(),
            ],
        }
    }
}

/// Stop-loss configuration (V3 §3.2 shared_types — StopConfig).
/// 止損配置。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StopConfig {
    pub hard_stop_pct: f64,
    pub trailing_stop_pct: Option<f64>,
    pub time_stop_hours: Option<f64>,
    pub atr_multiplier: Option<f64>,
}

impl Default for StopConfig {
    fn default() -> Self {
        Self {
            hard_stop_pct: 5.0,
            trailing_stop_pct: None,
            time_stop_hours: None,
            atr_multiplier: None,
        }
    }
}

/// Composite risk configuration.
/// 組合風控配置。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct RiskConfig {
    #[serde(default)]
    pub h0_gate: H0GateConfig,
    #[serde(default)]
    pub guardian: GuardianConfig,
    #[serde(default)]
    pub stop: StopConfig,
    #[serde(default)]
    pub constraints: HashMap<String, serde_json::Value>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_h0_gate_config_serde() {
        let cfg = H0GateConfig::default();
        let json = serde_json::to_string(&cfg).unwrap();
        let de: H0GateConfig = serde_json::from_str(&json).unwrap();
        assert_eq!(de.max_open_positions, 10);
        assert!(!de.shadow_mode);
    }

    #[test]
    fn test_h0_check_result_constructors() {
        let ok = H0CheckResult::allowed();
        assert!(ok.allowed);

        let fail = H0CheckResult::blocked("stale data".into(), "freshness".into());
        assert!(!fail.allowed);
        assert_eq!(fail.check_name, "freshness");
    }

    #[test]
    fn test_risk_config_default_serde() {
        let cfg = RiskConfig::default();
        let json = serde_json::to_string(&cfg).unwrap();
        let de: RiskConfig = serde_json::from_str(&json).unwrap();
        assert_eq!(de.stop.hard_stop_pct, 5.0);
    }

    #[test]
    fn test_stop_config_serde() {
        let sc = StopConfig {
            hard_stop_pct: 3.0,
            trailing_stop_pct: Some(2.0),
            time_stop_hours: Some(1.0),
            atr_multiplier: Some(1.5),
        };
        let json = serde_json::to_string(&sc).unwrap();
        let de: StopConfig = serde_json::from_str(&json).unwrap();
        assert_eq!(de.trailing_stop_pct, Some(2.0));
    }
}
