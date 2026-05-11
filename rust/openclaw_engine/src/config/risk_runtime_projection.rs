//! Runtime projection for RiskConfig.
//! RiskConfig 的 runtime-facing 投影。
//!
//! This Module keeps fallback semantics close to the authoritative config:
//! callers that need runtime knobs should consume this Interface instead of
//! manually cloning optional fields.
//! 本 Module 把 fallback 語意集中在權威 config 附近；runtime caller 不應各自
//! 手寫 optional 欄位 fallback。

use super::RiskConfig;
use openclaw_types::PricingConfig;
use serde::{Deserialize, Serialize};

/// Small read-model consumed by startup / watcher code.
/// startup / watcher 消費的小型唯讀模型。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RiskRuntimeProjection {
    /// H0 hard-block toggle as seen by runtime consumers.
    /// runtime consumer 看到的 H0 hard-block toggle。
    pub h0_shadow_mode: bool,
    /// Pricing config with legacy-TOML fallback already applied.
    /// 已套用舊 TOML fallback 的 pricing config。
    pub pricing: PricingConfig,
}

impl RiskConfig {
    /// Build the runtime projection from the authoritative config snapshot.
    /// 從權威 config snapshot 建立 runtime-facing 投影。
    pub fn runtime_projection(&self) -> RiskRuntimeProjection {
        RiskRuntimeProjection {
            h0_shadow_mode: self.runtime.h0_shadow_mode,
            pricing: self.pricing.clone().unwrap_or_default(),
        }
    }

    /// Convenience accessor for Live/Demo spawn callsites.
    /// Live/Demo spawn callsite 使用的便利 accessor。
    pub fn pricing_config(&self) -> PricingConfig {
        self.runtime_projection().pricing
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn runtime_projection_applies_pricing_default_when_absent() {
        let cfg = RiskConfig::default();
        let projection = cfg.runtime_projection();
        assert_eq!(projection.pricing, PricingConfig::default());
        assert_eq!(projection.h0_shadow_mode, cfg.runtime.h0_shadow_mode);
    }

    #[test]
    fn runtime_projection_preserves_explicit_pricing() {
        let mut cfg = RiskConfig::default();
        cfg.pricing = Some(PricingConfig {
            max_age_warn_minutes: 15,
            max_age_fail_minutes: 360,
            cold_default_acceptable_modes: vec!["demo".into(), "live_demo".into()],
        });
        let projection = cfg.runtime_projection();
        assert_eq!(projection.pricing.max_age_warn_minutes, 15);
        assert_eq!(
            projection.pricing.cold_default_acceptable_modes,
            vec!["demo".to_string(), "live_demo".to_string()]
        );
    }
}
