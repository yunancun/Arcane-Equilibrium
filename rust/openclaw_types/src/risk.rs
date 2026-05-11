//! H0 Gate + LG-2 共享風控/pricing 跨 crate 類型。
//!
//! ARCH-RC1 1C-1 Batch 6：刪除死代碼重複定義 —
//! `GuardianConfig` 只存在 `openclaw_core::guardian`；
//! `StopConfig` 只存在 `openclaw_core::stop_manager`；
//! 組合 `RiskConfig` 已刪除（由 `openclaw_engine::config::RiskConfig` 作為單一真相源取代）。
//!
//! LG-2 T4 (2026-05-11)：新增 `PricingConfig`，承載 24h pricing freshness gate
//! 配置。Per PA tech plan `2026-05-11--lg_2_3_4_design_plan.md` §2.2 第 5 點，
//! 提升為跨 crate shared type 以便 healthcheck `[45]` / startup assertion /
//! IPC 三方對齊閾值。實際 `RiskConfig::pricing` 欄位在 `openclaw_engine::config`
//! 為 `Option<PricingConfig>`（舊 TOML 無 `[pricing]` 時 fallback hardcoded
//! RFC §Refresh Cadence 數值）。

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

// ---------------------------------------------------------------------------
// LG-2 T4 (2026-05-11)：PricingConfig — 24h pricing freshness gate 配置。
//
// Per PA tech plan `2026-05-11--lg_2_3_4_design_plan.md` §2.2 第 5 點 +
// §2.4 表 T4：將 LG-3 RFC `2026-05-01--lg3_provider_pricing_binding_rfc.md`
// 的 freshness 閾值從散落硬編碼（healthcheck `[45]` 的 86400s + RFC 文檔的
// 60min warn）統一為 RiskConfig 一級欄位，經 ArcSwap 熱重載。
//
// 為何放 openclaw_types（而非 openclaw_engine::config）：
// - LG-2 後續 T1 contract test / T2 startup assertion / T3 FeeSource cross
//   check 將跨 crate 共用此型別；healthcheck `[45]`（Python）也走同字串集合
//   `cold_default_acceptable_modes`，shared type 較易維持單一真相源。
// - 與既有 `H0GateConfig` 同檔同層共享 — 兩者都是「跨 crate 風控 schema」
//   性質一致。
// ---------------------------------------------------------------------------

/// LG-2 T4：24h pricing freshness gate 配置。
///
/// 三欄位語意：
/// - `max_age_warn_minutes`：trading.fills 最近 fee_rate 行對應 ts 距今超過
///   此分鐘 → healthcheck `[45]` 標 WARN。
/// - `max_age_fail_minutes`：超過此分鐘 → healthcheck `[45]` 標 FAIL（24h
///   default 對齊 LG-3 RFC §2.3）。
/// - `cold_default_acceptable_modes`：當 source 推斷為 `seed_default` /
///   `cold_default` 時，僅這些 engine_mode 可接受（live 永不可接受 → FAIL）。
///   字串值與 `trading.fills.engine_mode` + healthcheck `MONITORED_ENGINE_MODES`
///   完全一致（"paper" / "demo" / "live_demo" / "live"）。
///
/// 預設值對齊 LG-3 RFC §Refresh Cadence：
/// - 60 分鐘 WARN（hourly refresh task 失敗一次即可觀測）
/// - 1440 分鐘 (24h) FAIL（mainnet hard-block 觸發點）
/// - paper/demo/live_demo 可接受 seed_default（live 不可）
///
/// 各環境 TOML 可獨立 override 此欄位（per memory
/// `feedback_env_config_independence`）。
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
pub struct PricingConfig {
    /// 超過此分鐘 → healthcheck `[45]` WARN（default 60）。
    #[serde(default = "default_pricing_warn_minutes")]
    pub max_age_warn_minutes: u64,
    /// 超過此分鐘 → healthcheck `[45]` FAIL（default 1440 = 24h）。
    #[serde(default = "default_pricing_fail_minutes")]
    pub max_age_fail_minutes: u64,
    /// 接受 seed_default / cold_default 的 engine_mode 白名單。
    /// 字串需與 `trading.fills.engine_mode` 完全一致。
    #[serde(default = "default_pricing_cold_modes")]
    pub cold_default_acceptable_modes: Vec<String>,
}

fn default_pricing_warn_minutes() -> u64 {
    60
}

fn default_pricing_fail_minutes() -> u64 {
    1440
}

fn default_pricing_cold_modes() -> Vec<String> {
    vec!["paper".into(), "demo".into(), "live_demo".into()]
}

impl Default for PricingConfig {
    fn default() -> Self {
        Self {
            max_age_warn_minutes: default_pricing_warn_minutes(),
            max_age_fail_minutes: default_pricing_fail_minutes(),
            cold_default_acceptable_modes: default_pricing_cold_modes(),
        }
    }
}

impl PricingConfig {
    /// 不變量驗證：warn < fail；fail > 0；白名單非空且不含 "live"。
    ///
    /// fail > warn 不變量阻擋「freshness 警告高於致命」誤配置；
    /// 不含 "live" 阻擋 LG-3 RFC §2.3 強約束「mainnet 必須拒絕 seed_default」
    /// 在 TOML 層被誤鬆綁。
    pub fn validate(&self) -> Result<(), String> {
        if self.max_age_fail_minutes == 0 {
            return Err("risk.pricing.max_age_fail_minutes must be > 0".into());
        }
        if self.max_age_warn_minutes >= self.max_age_fail_minutes {
            return Err(format!(
                "risk.pricing.max_age_warn_minutes ({}) must be < max_age_fail_minutes ({})",
                self.max_age_warn_minutes, self.max_age_fail_minutes
            ));
        }
        if self.cold_default_acceptable_modes.is_empty() {
            return Err(
                "risk.pricing.cold_default_acceptable_modes must not be empty".into(),
            );
        }
        // LG-3 RFC §2.3 fail-closed：live 不可進入白名單，否則 mainnet 退化。
        if self
            .cold_default_acceptable_modes
            .iter()
            .any(|m| m == "live")
        {
            return Err(
                "risk.pricing.cold_default_acceptable_modes must NOT contain 'live' \
                 (LG-3 RFC §2.3 mainnet fail-closed invariant)"
                    .into(),
            );
        }
        Ok(())
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

    // ---------------------------------------------------------------------
    // LG-2 T4 — PricingConfig 單元測試
    // ---------------------------------------------------------------------

    #[test]
    fn test_pricing_config_default_matches_rfc() {
        // Default 對齊 LG-3 RFC §Refresh Cadence：60min warn / 24h fail
        // / paper+demo+live_demo 可接受 seed_default。
        let cfg = PricingConfig::default();
        assert_eq!(cfg.max_age_warn_minutes, 60);
        assert_eq!(cfg.max_age_fail_minutes, 1440);
        assert_eq!(
            cfg.cold_default_acceptable_modes,
            vec!["paper".to_string(), "demo".to_string(), "live_demo".to_string()],
        );
        assert!(cfg.validate().is_ok());
    }

    #[test]
    fn test_pricing_config_validate_zero_fail_rejected() {
        let cfg = PricingConfig {
            max_age_warn_minutes: 0,
            max_age_fail_minutes: 0,
            cold_default_acceptable_modes: vec!["demo".into()],
        };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_pricing_config_validate_warn_ge_fail_rejected() {
        // warn 不可 ≥ fail；warn=fail 應被拒（warn 應嚴格小於 fail）。
        let cfg = PricingConfig {
            max_age_warn_minutes: 1440,
            max_age_fail_minutes: 1440,
            cold_default_acceptable_modes: vec!["demo".into()],
        };
        let err = cfg.validate().unwrap_err();
        assert!(err.contains("must be <"), "err={err}");
    }

    #[test]
    fn test_pricing_config_validate_empty_modes_rejected() {
        let cfg = PricingConfig {
            max_age_warn_minutes: 60,
            max_age_fail_minutes: 1440,
            cold_default_acceptable_modes: Vec::new(),
        };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_pricing_config_validate_live_in_whitelist_rejected() {
        // LG-3 RFC §2.3 不變量：cold default 白名單不可含 "live"。
        let cfg = PricingConfig {
            max_age_warn_minutes: 60,
            max_age_fail_minutes: 1440,
            cold_default_acceptable_modes: vec!["demo".into(), "live".into()],
        };
        let err = cfg.validate().unwrap_err();
        assert!(err.contains("'live'"), "err={err}");
    }

    #[test]
    fn test_pricing_config_toml_round_trip() {
        // 全欄位 TOML 解析 → 再序列化 → 再解析應 round-trip 一致。
        let toml_str = r#"
max_age_warn_minutes = 30
max_age_fail_minutes = 720
cold_default_acceptable_modes = ["paper", "demo"]
"#;
        let cfg: PricingConfig = toml::from_str(toml_str).expect("parse pricing toml");
        assert_eq!(cfg.max_age_warn_minutes, 30);
        assert_eq!(cfg.max_age_fail_minutes, 720);
        assert_eq!(cfg.cold_default_acceptable_modes, vec!["paper", "demo"]);
        assert!(cfg.validate().is_ok());

        let serialized = toml::to_string(&cfg).expect("serialize");
        let re: PricingConfig = toml::from_str(&serialized).expect("reparse");
        assert_eq!(re, cfg);
    }

    #[test]
    fn test_pricing_config_partial_toml_uses_defaults() {
        // 部分欄位缺失應走 serde default — 向後相容舊 TOML 場景。
        let toml_str = r#"
max_age_warn_minutes = 15
"#;
        let cfg: PricingConfig = toml::from_str(toml_str).expect("parse partial");
        assert_eq!(cfg.max_age_warn_minutes, 15);
        assert_eq!(cfg.max_age_fail_minutes, 1440); // default
        assert_eq!(
            cfg.cold_default_acceptable_modes,
            vec!["paper".to_string(), "demo".to_string(), "live_demo".to_string()],
        );
        assert!(cfg.validate().is_ok());
    }

    #[test]
    fn test_pricing_config_json_round_trip() {
        // JSON 路徑用於 IPC `patch_risk_config` 熱重載。
        let cfg = PricingConfig {
            max_age_warn_minutes: 45,
            max_age_fail_minutes: 720,
            cold_default_acceptable_modes: vec!["demo".into(), "live_demo".into()],
        };
        let json = serde_json::to_string(&cfg).unwrap();
        let de: PricingConfig = serde_json::from_str(&json).unwrap();
        assert_eq!(de, cfg);
        assert!(de.validate().is_ok());
    }
}
