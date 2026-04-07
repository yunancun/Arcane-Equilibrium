//! H0 Gate types shared across crates (runtime health / risk snapshots + gate result).
//! H0 門控跨 crate 共享類型（運行時健康/風控快照 + 檢查結果）。
//!
//! ARCH-RC1 1C-1 Batch 6: Dead duplicates removed —
//! `GuardianConfig` now lives exclusively in `openclaw_core::guardian`;
//! `StopConfig` in `openclaw_core::stop_manager`;
//! composite `RiskConfig` deleted (superseded by
//! `openclaw_engine::config::RiskConfig` as the single source of truth).
//! 1C-1 Batch 6：刪除死代碼重複定義 —
//! `GuardianConfig` 只存在 `openclaw_core::guardian`；
//! `StopConfig` 只存在 `openclaw_core::stop_manager`；
//! 組合 `RiskConfig` 已刪除（由 `openclaw_engine::config::RiskConfig` 作為單一真相源取代）。

use serde::{Deserialize, Serialize};

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
}
