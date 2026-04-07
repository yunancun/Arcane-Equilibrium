//! BudgetConfig — AI cost limits, attention tax, model pricing (ARCH-RC1).
//! BudgetConfig — AI 成本上限、注意力稅、模型定價。
//!
//! MODULE_NOTE (EN): One of the three hot-reload Configs in ARCH-RC1. Owns ALL
//!   AI-cost-related settings: per-scope USD caps, exhaustion cooldown, model
//!   pricing table, and the attention tax sub-system (burn rates + grade
//!   thresholds + cost-edge gate). The attention tax `enabled` flag lives here
//!   too — RiskConfig has zero attention-tax fields. Tick path reads this via
//!   `Arc<ArcSwap<BudgetConfig>>` for lock-free snapshots.
//! MODULE_NOTE (中): ARCH-RC1 三個熱重載 Config 之一，持有所有 AI 成本相關設定：
//!   按 scope 美元上限、耗盡冷卻、模型定價表、注意力稅子系統（burn rate + grade
//!   閾值 + cost-edge gate）。注意力稅的 `enabled` 開關也在這裡 —— RiskConfig
//!   完全不持有任何 attention_tax 欄位。Tick 路徑透過 `Arc<ArcSwap<BudgetConfig>>`
//!   無鎖讀取快照。

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// ---------------------------------------------------------------------------
// Top-level / 頂層
// ---------------------------------------------------------------------------

/// Schema version + persistence metadata.
/// Schema 版本與持久化中繼資料。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Meta {
    #[serde(default = "default_meta_version")]
    pub version: u32,
    #[serde(default)]
    pub saved_ts_ms: u64,
}

fn default_meta_version() -> u32 {
    1
}

impl Default for Meta {
    fn default() -> Self {
        Self {
            version: default_meta_version(),
            saved_ts_ms: 0,
        }
    }
}

/// Complete budget configuration (ARCH-RC1).
/// 完整預算配置。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct BudgetConfig {
    #[serde(default)]
    pub meta: Meta,
    #[serde(default)]
    pub caps: BudgetCaps,
    #[serde(default)]
    pub model_costs: ModelCosts,
    #[serde(default)]
    pub attention_tax: AttentionTax,
    #[serde(default)]
    pub experimental: Experimental,
}

impl BudgetConfig {
    /// Validate cross-field invariants.
    /// 驗證跨欄位不變量。
    pub fn validate(&self) -> Result<(), String> {
        self.caps.validate()?;
        self.attention_tax.validate()?;
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// BudgetCaps / 預算上限
// ---------------------------------------------------------------------------

/// Per-scope USD spending caps + cooldown + alerting.
/// 按 scope 美元支出上限 + 冷卻 + 預警。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BudgetCaps {
    /// Total daily AI spend ceiling (USD). 0 = uncapped (not recommended).
    /// 每日 AI 支出總上限（美元）。0 = 不限（不建議）。
    #[serde(default = "default_daily_usd_max")]
    pub daily_usd_max: f64,

    /// Total monthly AI spend ceiling (USD). 0 = uncapped.
    /// 每月 AI 支出總上限（美元）。0 = 不限。
    #[serde(default = "default_monthly_usd_max")]
    pub monthly_usd_max: f64,

    /// Per-scope daily caps (e.g. teacher / linucb_explain / news / scorer → USD).
    /// 按 scope 每日上限。
    #[serde(default)]
    pub per_scope_caps: HashMap<String, f64>,

    /// Cooldown after a scope hits its cap (minutes).
    /// scope 觸頂後的冷卻時長（分鐘）。
    #[serde(default = "default_exhaustion_cooldown_minutes")]
    pub exhaustion_cooldown_minutes: u32,

    /// Alert threshold as fraction of daily_usd_max (e.g. 0.8 = warn at 80%).
    /// 預警閾值（每日上限的比例，0.8 = 80% 時預警）。
    #[serde(default = "default_alert_threshold_pct")]
    pub alert_threshold_pct: f64,
}

fn default_daily_usd_max() -> f64 {
    100.0
}
fn default_monthly_usd_max() -> f64 {
    150.0
}
fn default_exhaustion_cooldown_minutes() -> u32 {
    60
}
fn default_alert_threshold_pct() -> f64 {
    0.8
}

impl Default for BudgetCaps {
    fn default() -> Self {
        Self {
            daily_usd_max: default_daily_usd_max(),
            monthly_usd_max: default_monthly_usd_max(),
            per_scope_caps: HashMap::new(),
            exhaustion_cooldown_minutes: default_exhaustion_cooldown_minutes(),
            alert_threshold_pct: default_alert_threshold_pct(),
        }
    }
}

impl BudgetCaps {
    fn validate(&self) -> Result<(), String> {
        if self.daily_usd_max < 0.0 {
            return Err("budget.caps.daily_usd_max must be >= 0".into());
        }
        if self.monthly_usd_max < 0.0 {
            return Err("budget.caps.monthly_usd_max must be >= 0".into());
        }
        if self.daily_usd_max > 0.0
            && self.monthly_usd_max > 0.0
            && self.daily_usd_max > self.monthly_usd_max
        {
            return Err(
                "budget.caps.daily_usd_max must not exceed monthly_usd_max".into(),
            );
        }
        if !(0.0..=1.0).contains(&self.alert_threshold_pct) {
            return Err("budget.caps.alert_threshold_pct must be in [0, 1]".into());
        }
        for (scope, cap) in &self.per_scope_caps {
            if *cap < 0.0 {
                return Err(format!(
                    "budget.caps.per_scope_caps[{}] must be >= 0",
                    scope
                ));
            }
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// ModelCosts / 模型定價
// ---------------------------------------------------------------------------

/// Per-model input/output token pricing (USD per 1k tokens).
/// 各模型輸入/輸出 token 定價（美元/千 token）。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ModelCosts {
    #[serde(default)]
    pub models: HashMap<String, ModelPricing>,
}

/// Single model pricing entry.
/// 單一模型定價。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelPricing {
    pub input_per_1k_usd: f64,
    pub output_per_1k_usd: f64,
}

// ---------------------------------------------------------------------------
// AttentionTax / 注意力稅（含 enabled）
// ---------------------------------------------------------------------------

/// AI attention tax: hourly burn rates → cost-edge ratio → grade → close decision.
/// AI 注意力稅：時薪燒錢率 → cost-edge 比率 → 等級 → 平倉決策。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AttentionTax {
    /// Master switch. Disabling skips the close-on-cost-edge gate entirely.
    /// 總開關。關閉時完全跳過 cost-edge 平倉檢查。
    #[serde(default = "default_true")]
    pub enabled: bool,

    /// Hourly USD burn when no positions and no orders.
    /// 無持倉且無掛單時的時薪美元燒錢率。
    #[serde(default = "default_burn_rate_dormant")]
    pub burn_rate_dormant: f64,

    /// Hourly USD burn when only background scanning active.
    /// 僅後台掃描活躍時的時薪燒錢率。
    #[serde(default = "default_burn_rate_low")]
    pub burn_rate_low: f64,

    /// Hourly USD burn with positions open but no active orders.
    /// 有持倉但無活躍掛單時的時薪燒錢率。
    #[serde(default = "default_burn_rate_medium")]
    pub burn_rate_medium: f64,

    /// Hourly USD burn with active orders or high-frequency decisions.
    /// 有活躍掛單或高頻決策時的時薪燒錢率。
    #[serde(default = "default_burn_rate_high")]
    pub burn_rate_high: f64,

    /// Cost-edge ratio threshold for grade A (≤ 0.2 = best).
    /// A 級閾值（≤ 0.2 為最佳）。
    #[serde(default = "default_grade_a_threshold")]
    pub grade_a_threshold: f64,
    #[serde(default = "default_grade_b_threshold")]
    pub grade_b_threshold: f64,
    #[serde(default = "default_grade_c_threshold")]
    pub grade_c_threshold: f64,
    #[serde(default = "default_grade_d_threshold")]
    pub grade_d_threshold: f64,

    /// Above this cost-edge ratio, the gate triggers a close suggestion.
    /// 超過此 cost-edge 比率，gate 觸發平倉建議。
    #[serde(default = "default_cost_edge_max_ratio")]
    pub cost_edge_max_ratio: f64,
}

fn default_true() -> bool {
    true
}
fn default_burn_rate_dormant() -> f64 {
    0.000
}
fn default_burn_rate_low() -> f64 {
    0.003
}
fn default_burn_rate_medium() -> f64 {
    0.010
}
fn default_burn_rate_high() -> f64 {
    0.050
}
fn default_grade_a_threshold() -> f64 {
    0.2
}
fn default_grade_b_threshold() -> f64 {
    0.4
}
fn default_grade_c_threshold() -> f64 {
    0.6
}
fn default_grade_d_threshold() -> f64 {
    0.8
}
fn default_cost_edge_max_ratio() -> f64 {
    0.8
}

impl Default for AttentionTax {
    fn default() -> Self {
        Self {
            enabled: default_true(),
            burn_rate_dormant: default_burn_rate_dormant(),
            burn_rate_low: default_burn_rate_low(),
            burn_rate_medium: default_burn_rate_medium(),
            burn_rate_high: default_burn_rate_high(),
            grade_a_threshold: default_grade_a_threshold(),
            grade_b_threshold: default_grade_b_threshold(),
            grade_c_threshold: default_grade_c_threshold(),
            grade_d_threshold: default_grade_d_threshold(),
            cost_edge_max_ratio: default_cost_edge_max_ratio(),
        }
    }
}

impl AttentionTax {
    fn validate(&self) -> Result<(), String> {
        let rates = [
            ("dormant", self.burn_rate_dormant),
            ("low", self.burn_rate_low),
            ("medium", self.burn_rate_medium),
            ("high", self.burn_rate_high),
        ];
        for (name, rate) in rates {
            if rate < 0.0 {
                return Err(format!(
                    "budget.attention_tax.burn_rate_{} must be >= 0",
                    name
                ));
            }
        }
        // Burn rates should be monotonically non-decreasing across activity levels.
        // 燒錢率應隨活躍度單調非遞減。
        if !(self.burn_rate_dormant <= self.burn_rate_low
            && self.burn_rate_low <= self.burn_rate_medium
            && self.burn_rate_medium <= self.burn_rate_high)
        {
            return Err(
                "budget.attention_tax burn rates must be non-decreasing (dormant ≤ low ≤ medium ≤ high)".into()
            );
        }
        // Grade thresholds must be strictly increasing in (0, 1).
        // 等級閾值必須在 (0, 1) 區間內嚴格遞增。
        let grades = [
            self.grade_a_threshold,
            self.grade_b_threshold,
            self.grade_c_threshold,
            self.grade_d_threshold,
        ];
        for g in grades {
            if !(0.0..=1.0).contains(&g) {
                return Err("budget.attention_tax.grade_*_threshold must be in [0, 1]".into());
            }
        }
        if !(grades[0] < grades[1] && grades[1] < grades[2] && grades[2] < grades[3]) {
            return Err(
                "budget.attention_tax grade thresholds must be strictly increasing (A < B < C < D)".into()
            );
        }
        if !(0.0..=1.0).contains(&self.cost_edge_max_ratio) {
            return Err("budget.attention_tax.cost_edge_max_ratio must be in [0, 1]".into());
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Experimental namespace / 試驗性命名空間
// ---------------------------------------------------------------------------

/// Reserved for experimental fields. Promoted to a permanent sub-struct once stable.
/// 預留給試驗性欄位。穩定後晉升為正式 sub-struct。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Experimental {
    #[serde(default)]
    pub flags: HashMap<String, serde_json::Value>,
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_validates() {
        let cfg = BudgetConfig::default();
        assert!(cfg.validate().is_ok());
    }

    #[test]
    fn test_default_burn_rates_monotonic() {
        let at = AttentionTax::default();
        assert!(at.burn_rate_dormant <= at.burn_rate_low);
        assert!(at.burn_rate_low <= at.burn_rate_medium);
        assert!(at.burn_rate_medium <= at.burn_rate_high);
    }

    #[test]
    fn test_invalid_negative_daily_cap() {
        let mut cfg = BudgetConfig::default();
        cfg.caps.daily_usd_max = -1.0;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_daily_exceeds_monthly_rejected() {
        let mut cfg = BudgetConfig::default();
        cfg.caps.daily_usd_max = 200.0;
        cfg.caps.monthly_usd_max = 150.0;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_alert_threshold_out_of_range_rejected() {
        let mut cfg = BudgetConfig::default();
        cfg.caps.alert_threshold_pct = 1.5;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_burn_rates_non_monotonic_rejected() {
        let mut cfg = BudgetConfig::default();
        cfg.attention_tax.burn_rate_low = 0.999;
        cfg.attention_tax.burn_rate_medium = 0.001;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_grade_thresholds_non_increasing_rejected() {
        let mut cfg = BudgetConfig::default();
        cfg.attention_tax.grade_b_threshold = 0.1;
        cfg.attention_tax.grade_a_threshold = 0.5;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_cost_edge_max_ratio_out_of_range_rejected() {
        let mut cfg = BudgetConfig::default();
        cfg.attention_tax.cost_edge_max_ratio = 1.5;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_attention_tax_can_be_disabled() {
        let mut cfg = BudgetConfig::default();
        cfg.attention_tax.enabled = false;
        assert!(cfg.validate().is_ok());
        assert!(!cfg.attention_tax.enabled);
    }

    #[test]
    fn test_per_scope_caps_negative_rejected() {
        let mut cfg = BudgetConfig::default();
        cfg.caps.per_scope_caps.insert("teacher".into(), -5.0);
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_toml_round_trip_default() {
        let cfg = BudgetConfig::default();
        let toml_str = toml::to_string(&cfg).unwrap();
        let de: BudgetConfig = toml::from_str(&toml_str).unwrap();
        assert!(de.validate().is_ok());
        assert_eq!(de.attention_tax.cost_edge_max_ratio, 0.8);
    }

    #[test]
    fn test_json_round_trip_with_overrides() {
        let mut cfg = BudgetConfig::default();
        cfg.caps.daily_usd_max = 50.0;
        cfg.caps
            .per_scope_caps
            .insert("teacher".into(), 30.0);
        cfg.attention_tax.cost_edge_max_ratio = 0.7;
        let json = serde_json::to_string(&cfg).unwrap();
        let de: BudgetConfig = serde_json::from_str(&json).unwrap();
        assert_eq!(de.caps.daily_usd_max, 50.0);
        assert_eq!(de.caps.per_scope_caps.get("teacher"), Some(&30.0));
        assert!((de.attention_tax.cost_edge_max_ratio - 0.7).abs() < f64::EPSILON);
    }

    #[test]
    fn test_partial_toml_uses_defaults() {
        let toml_str = r#"
[caps]
daily_usd_max = 50.0
"#;
        let cfg: BudgetConfig = toml::from_str(toml_str).unwrap();
        assert_eq!(cfg.caps.daily_usd_max, 50.0);
        // attention_tax defaults preserved / attention_tax 預設值保留
        assert!(cfg.attention_tax.enabled);
        assert_eq!(cfg.attention_tax.cost_edge_max_ratio, 0.8);
        assert!(cfg.validate().is_ok());
    }
}
