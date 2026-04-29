//! Regime-detection sub-configs (Hurst + hysteresis schema).
//! Regime 偵測子配置（Hurst + 滯回 schema）。
//!
//! MODULE_NOTE (EN): G7-03 Phase A schema-only landing. Houses `HurstConfig`,
//!   the operator-tunable knob block for the Hurst-based regime detector
//!   (`regime/hurst.rs`). Lives in a sibling file (per CLAUDE.md §九) to keep
//!   `risk_config_advanced.rs` under the 1200-line hard cap. Re-exported from
//!   `risk_config.rs` via `#[path = "risk_config_regime.rs"] mod regime_cfg;`
//!   so callers continue to use `crate::config::HurstConfig`.
//!   Defaults are dormant: `enabled = false` ensures `regime/hurst.rs`'s
//!   `hurst_label_for_symbol` short-circuits to `None` and the Phase A landing
//!   is bit-identical to pre-G7-03 runtime. Phase B will flip `enabled = true`
//!   per environment alongside wiring into the strategy / scanner path.
//! MODULE_NOTE (中): G7-03 Phase A schema 落地。承載 `HurstConfig`，Hurst regime
//!   偵測器的 operator 可調 knob 區塊。獨立 sibling 檔，避開 §九 1200 行硬上限。
//!   `risk_config.rs` 透過 `#[path]` 重新匯出，呼叫端 API 不變。
//!   預設 `enabled=false`，Phase A 完全 no-op；Phase B wire 後 operator 才翻 true。

use serde::{Deserialize, Serialize};

/// G7-03 (2026-04-24): Operator-tunable Hurst exponent regime detector knobs.
///
/// Drives `regime::hurst::hurst_label_for_symbol` (Phase A: dormant by default)
/// and `HysteresisDetector` (Phase B integration).
///
/// Defaults preserve the legacy `openclaw_core::indicators::volatility::hurst`
/// thresholds-shape with a slightly tighter band than the pre-G7-03
/// `DEFAULT_HURST_TRENDING_THRESHOLD = 0.60` /
/// `DEFAULT_HURST_MEAN_REVERTING_THRESHOLD = 0.40` constants — `0.55` /
/// `0.45` is the spec-mandated G7-03 hysteresis-band setpoint. The legacy
/// constants are still consumed by IndicatorEngine when this config is
/// `enabled = false`, so Phase A landing changes nothing at runtime.
///
/// Validation (`validate()` enforces all):
///   * `window_size >= 16` so R/S has at least 4 chunks at min_window=4.
///   * `1 <= hysteresis_lag <= 256` (sane operator bounds).
///   * `2 <= min_window` and `min_window * 4 <= window_size`.
///   * `0.0 < antipersistent_threshold < persistent_threshold < 1.0`.
///
/// G7-03：Hurst regime 偵測器 operator 可調 knob。Phase A 預設 enabled=false 完全 no-op。
/// Validate 強制：window>=16、lag∈[1,256]、min_window>=2 且 min_window*4<=window、
/// 0 < antipersistent < persistent < 1。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HurstConfig {
    /// Master enable flag. Phase A default `false` keeps
    /// `hurst_label_for_symbol` returning `None`, so callers see exactly the
    /// pre-G7-03 behaviour. Phase B wires call sites and operators flip to
    /// `true` per environment.
    /// 主開關；Phase A=false 完全 no-op，Phase B 接 wire 後 operator 才翻 true。
    #[serde(default = "default_hurst_enabled")]
    pub enabled: bool,

    /// Total observation window (in price samples) fed to R/S analysis. Default
    /// `128` matches a typical 1m / 5m / 1h scanner cadence (~2 hours at 1m).
    /// Validated `>= 16` so at least one valid sub-window pass exists.
    /// R/S 分析的總觀察窗口（價格點數），預設 128。validate 要求 >= 16。
    #[serde(default = "default_hurst_window_size")]
    pub window_size: usize,

    /// Smallest sub-window (lag) length passed to the R/S chunker. Default `8`.
    /// Validated `>= 2` and `min_window * 4 <= window_size`.
    /// R/S 子窗口最小長度，預設 8。validate 要求 >=2 且 min_window*4 <= window_size。
    #[serde(default = "default_hurst_min_window")]
    pub min_window: usize,

    /// Hysteresis lag — number of consecutive same-side observations required
    /// before `HysteresisDetector` flips the persisted label out of Random.
    /// Default `6` per the G7-03 spec (≈ 6 timeframe periods of agreement).
    /// 滯回 lag — 翻入 Persistent / AntiPersistent 所需連續同向觀察數；預設 6。
    #[serde(default = "default_hurst_lag")]
    pub hysteresis_lag: usize,

    /// Persistent (trending) threshold: H > threshold → trending side.
    /// Default `0.55` (spec). Must satisfy
    /// `antipersistent_threshold < persistent_threshold < 1.0`.
    /// 趨勢側閾值；預設 0.55。
    #[serde(default = "default_hurst_persistent_threshold")]
    pub persistent_threshold: f64,

    /// Anti-persistent (mean-reverting) threshold: H < threshold → MR side.
    /// Default `0.45` (spec). Must satisfy
    /// `0.0 < antipersistent_threshold < persistent_threshold`.
    /// 均值回歸側閾值；預設 0.45。
    #[serde(default = "default_hurst_antipersistent_threshold")]
    pub antipersistent_threshold: f64,
}

fn default_hurst_enabled() -> bool {
    false
}
fn default_hurst_window_size() -> usize {
    128
}
fn default_hurst_min_window() -> usize {
    8
}
fn default_hurst_lag() -> usize {
    6
}
fn default_hurst_persistent_threshold() -> f64 {
    0.55
}
fn default_hurst_antipersistent_threshold() -> f64 {
    0.45
}

impl Default for HurstConfig {
    fn default() -> Self {
        Self {
            enabled: default_hurst_enabled(),
            window_size: default_hurst_window_size(),
            min_window: default_hurst_min_window(),
            hysteresis_lag: default_hurst_lag(),
            persistent_threshold: default_hurst_persistent_threshold(),
            antipersistent_threshold: default_hurst_antipersistent_threshold(),
        }
    }
}

impl HurstConfig {
    /// Convenience accessor used by `regime::hurst::hurst_label_for_symbol` —
    /// keeps the public API ergonomic without exposing the field name choice.
    /// 提供給 `hurst_label_for_symbol` 的便利 getter，避免欄位名綁定。
    pub fn min_window(&self) -> usize {
        self.min_window
    }

    /// Validate operator-supplied bounds. Cross-field invariants:
    ///   * `window_size >= 16`
    ///   * `min_window >= 2` and `min_window * 4 <= window_size`
    ///   * `1 <= hysteresis_lag <= 256`
    ///   * `0.0 < antipersistent_threshold < persistent_threshold < 1.0`
    /// G7-03：驗證 operator 提供之上下界（語意見上方註解）。
    pub fn validate(&self) -> Result<(), String> {
        if self.window_size < 16 {
            return Err(format!(
                "risk.hurst.window_size ({}) must be >= 16",
                self.window_size
            ));
        }
        if self.min_window < 2 {
            return Err(format!(
                "risk.hurst.min_window ({}) must be >= 2",
                self.min_window
            ));
        }
        if self
            .min_window
            .checked_mul(4)
            .map(|x| x > self.window_size)
            .unwrap_or(true)
        {
            return Err(format!(
                "risk.hurst.min_window ({}) * 4 must be <= window_size ({})",
                self.min_window, self.window_size
            ));
        }
        if self.hysteresis_lag == 0 {
            return Err("risk.hurst.hysteresis_lag must be >= 1".into());
        }
        if self.hysteresis_lag > 256 {
            return Err(format!(
                "risk.hurst.hysteresis_lag ({}) must be <= 256",
                self.hysteresis_lag
            ));
        }
        if !(self.persistent_threshold.is_finite() && self.antipersistent_threshold.is_finite()) {
            return Err("risk.hurst thresholds must be finite".into());
        }
        if self.antipersistent_threshold <= 0.0 {
            return Err(format!(
                "risk.hurst.antipersistent_threshold ({}) must be > 0.0",
                self.antipersistent_threshold
            ));
        }
        if self.persistent_threshold >= 1.0 {
            return Err(format!(
                "risk.hurst.persistent_threshold ({}) must be < 1.0",
                self.persistent_threshold
            ));
        }
        if self.antipersistent_threshold >= self.persistent_threshold {
            return Err(format!(
                "risk.hurst.antipersistent_threshold ({}) must be < persistent_threshold ({})",
                self.antipersistent_threshold, self.persistent_threshold
            ));
        }
        Ok(())
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_validate() {
        let cfg = HurstConfig::default();
        assert!(!cfg.enabled, "Phase A must default disabled");
        assert_eq!(cfg.window_size, 128);
        assert_eq!(cfg.min_window, 8);
        assert_eq!(cfg.hysteresis_lag, 6);
        assert!((cfg.persistent_threshold - 0.55).abs() < 1e-12);
        assert!((cfg.antipersistent_threshold - 0.45).abs() < 1e-12);
        cfg.validate().expect("defaults must validate");
    }

    #[test]
    fn validate_rejects_window_too_small() {
        let cfg = HurstConfig {
            window_size: 8,
            ..HurstConfig::default()
        };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn validate_rejects_min_window_too_small() {
        let cfg = HurstConfig {
            min_window: 1,
            ..HurstConfig::default()
        };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn validate_rejects_min_window_too_big_for_window() {
        let cfg = HurstConfig {
            window_size: 32,
            min_window: 16, // 16 * 4 = 64 > 32
            ..HurstConfig::default()
        };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn validate_rejects_zero_lag() {
        let cfg = HurstConfig {
            hysteresis_lag: 0,
            ..HurstConfig::default()
        };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn validate_rejects_excessive_lag() {
        let cfg = HurstConfig {
            hysteresis_lag: 1000,
            ..HurstConfig::default()
        };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn validate_rejects_inverted_thresholds() {
        let cfg = HurstConfig {
            persistent_threshold: 0.40,
            antipersistent_threshold: 0.60,
            ..HurstConfig::default()
        };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn validate_rejects_thresholds_out_of_unit_interval() {
        // antipersistent_threshold <= 0
        let cfg = HurstConfig {
            antipersistent_threshold: 0.0,
            ..HurstConfig::default()
        };
        assert!(cfg.validate().is_err());

        // persistent_threshold >= 1.0
        let cfg = HurstConfig {
            persistent_threshold: 1.0,
            ..HurstConfig::default()
        };
        assert!(cfg.validate().is_err());

        // NaN thresholds
        let cfg = HurstConfig {
            persistent_threshold: f64::NAN,
            ..HurstConfig::default()
        };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn toml_round_trip_preserves_fields() {
        let toml_str = r#"
enabled = true
window_size = 256
min_window = 16
hysteresis_lag = 8
persistent_threshold = 0.60
antipersistent_threshold = 0.40
"#;
        let cfg: HurstConfig = toml::from_str(toml_str).expect("parse");
        assert!(cfg.enabled);
        assert_eq!(cfg.window_size, 256);
        assert_eq!(cfg.min_window, 16);
        assert_eq!(cfg.hysteresis_lag, 8);
        assert!((cfg.persistent_threshold - 0.60).abs() < 1e-12);
        assert!((cfg.antipersistent_threshold - 0.40).abs() < 1e-12);
        cfg.validate().expect("custom but valid");
    }

    #[test]
    fn toml_partial_uses_defaults() {
        let toml_str = r#"
enabled = true
"#;
        let cfg: HurstConfig = toml::from_str(toml_str).expect("parse");
        assert!(cfg.enabled);
        assert_eq!(cfg.window_size, 128);
        assert_eq!(cfg.min_window, 8);
        assert_eq!(cfg.hysteresis_lag, 6);
        cfg.validate().expect("partial should validate");
    }
}
