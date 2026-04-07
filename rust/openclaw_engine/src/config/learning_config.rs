//! LearningConfig — ML/RL/Agent behavior switches and tunables (ARCH-RC1).
//! LearningConfig — ML/RL/Agent 行為開關與可調參數。
//!
//! MODULE_NOTE (EN): One of the three hot-reload Configs in ARCH-RC1. Owns ALL
//!   ML/RL pipeline switches (LinUCB, Thompson Sampling, Teacher loop, Scorer,
//!   News pipeline, Directive applier kill-switch) and the agent's behavioural
//!   preferences (entry confidence floor, Kelly fraction, breakeven trigger,
//!   regime whitelist, order-type preference, etc.). Phase 4.1's
//!   `teacher_loop_enabled` flag is collapsed into `learning.teacher_loop_enabled`
//!   here, so the IPC slot pattern can read from a single authoritative source.
//!   `partial_tp_*` belongs to RiskConfig.agent (coupled to take_profit_max_pct),
//!   NOT here.
//! MODULE_NOTE (中): ARCH-RC1 三個熱重載 Config 之一。持有所有 ML/RL 管線開關
//!   （LinUCB / Thompson / Teacher loop / Scorer / News / Directive applier kill
//!   switch）以及 Agent 的行為偏好（信心下限、Kelly 比例、保本觸發、regime 白名單、
//!   訂單類型偏好等）。Phase 4.1 的 `teacher_loop_enabled` 收編到此處，
//!   讓 IPC slot 從單一權威來源讀取。`partial_tp_*` 屬於 RiskConfig.agent
//!   （與 take_profit_max_pct 耦合），不在這裡。

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// ---------------------------------------------------------------------------
// Top-level / 頂層
// ---------------------------------------------------------------------------

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

/// Complete learning configuration (ARCH-RC1).
/// 完整學習配置。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct LearningConfig {
    #[serde(default)]
    pub meta: Meta,
    #[serde(default)]
    pub switches: MlSwitches,
    #[serde(default)]
    pub linucb: LinUcbParams,
    #[serde(default)]
    pub thompson: ThompsonParams,
    #[serde(default)]
    pub agent: AgentBehavior,
    #[serde(default)]
    pub experimental: Experimental,
}

impl LearningConfig {
    pub fn validate(&self) -> Result<(), String> {
        self.linucb.validate()?;
        self.thompson.validate()?;
        self.agent.validate()?;
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// MlSwitches / ML 開關
// ---------------------------------------------------------------------------

/// Master enable flags for all ML/RL/AI subsystems.
/// 所有 ML/RL/AI 子系統的總開關。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MlSwitches {
    /// LinUCB contextual bandit arm selection.
    /// LinUCB 上下文老虎機 arm 選擇。
    #[serde(default = "default_true")]
    pub linucb_enabled: bool,

    /// Thompson Sampling NIG posterior arm selection.
    /// Thompson Sampling NIG 後驗 arm 選擇。
    #[serde(default = "default_true")]
    pub thompson_enabled: bool,

    /// Phase 4.1 Claude API teacher consumer loop. Default OFF (operator IPC flip to enable).
    /// Phase 4.1 Claude API 教師消費迴圈。預設關閉（operator IPC 翻開才啟用）。
    #[serde(default)]
    pub teacher_loop_enabled: bool,

    /// Hard kill-switch for DirectiveApplier execution path.
    /// DirectiveApplier 執行路徑的硬性 kill-switch。
    #[serde(default = "default_true")]
    pub directive_apply_enabled: bool,

    /// LightGBM/ONNX scorer Tier-1 inference.
    /// LightGBM/ONNX scorer Tier-1 推論。
    #[serde(default = "default_true")]
    pub scorer_enabled: bool,

    /// News pipeline periodic fetch.
    /// 新聞管線週期擷取。
    #[serde(default = "default_true")]
    pub news_pipeline_enabled: bool,
}

fn default_true() -> bool {
    true
}

impl Default for MlSwitches {
    fn default() -> Self {
        Self {
            linucb_enabled: default_true(),
            thompson_enabled: default_true(),
            teacher_loop_enabled: false, // Phase 4.1 default-off contract
            directive_apply_enabled: default_true(),
            scorer_enabled: default_true(),
            news_pipeline_enabled: default_true(),
        }
    }
}

// ---------------------------------------------------------------------------
// LinUcbParams
// ---------------------------------------------------------------------------

/// LinUCB hyperparameters.
/// LinUCB 超參數。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LinUcbParams {
    /// Exploration coefficient (higher → more exploration). Typical 0.1 - 2.0.
    /// 探索係數（越高探索越多）。典型 0.1 - 2.0。
    #[serde(default = "default_exploration_weight")]
    pub exploration_weight: f64,

    /// Ridge regularisation lambda for arm covariance matrices.
    /// Arm 共變異數矩陣的脊回歸正則化參數。
    #[serde(default = "default_ridge_lambda")]
    pub ridge_lambda: f64,

    /// Arm space version label (e.g. "v1_15").
    /// Arm 空間版本標籤。
    #[serde(default = "default_arm_space_version")]
    pub arm_space_version: String,
}

fn default_exploration_weight() -> f64 {
    1.0
}
fn default_ridge_lambda() -> f64 {
    1.0
}
fn default_arm_space_version() -> String {
    "v1_15".into()
}

impl Default for LinUcbParams {
    fn default() -> Self {
        Self {
            exploration_weight: default_exploration_weight(),
            ridge_lambda: default_ridge_lambda(),
            arm_space_version: default_arm_space_version(),
        }
    }
}

impl LinUcbParams {
    fn validate(&self) -> Result<(), String> {
        if self.exploration_weight < 0.0 {
            return Err("learning.linucb.exploration_weight must be >= 0".into());
        }
        if self.ridge_lambda <= 0.0 {
            return Err("learning.linucb.ridge_lambda must be > 0".into());
        }
        if self.arm_space_version.is_empty() {
            return Err("learning.linucb.arm_space_version must not be empty".into());
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// ThompsonParams
// ---------------------------------------------------------------------------

/// Thompson Sampling NIG posterior hyperparameters.
/// Thompson Sampling NIG 後驗超參數。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ThompsonParams {
    /// Number of forced exploration trials before exploitation kicks in.
    /// 啟動探索的強制交易次數，達到後才開始 exploitation。
    #[serde(default = "default_floor_trials")]
    pub floor_trials: u32,

    /// Force-exploit threshold (fraction of trials). 0.5 = exploit half the time minimum.
    /// 強制 exploit 比率（達到後最少有此比例 exploit）。
    #[serde(default = "default_floor_pct")]
    pub floor_pct: f64,
}

fn default_floor_trials() -> u32 {
    10
}
fn default_floor_pct() -> f64 {
    0.5
}

impl Default for ThompsonParams {
    fn default() -> Self {
        Self {
            floor_trials: default_floor_trials(),
            floor_pct: default_floor_pct(),
        }
    }
}

impl ThompsonParams {
    fn validate(&self) -> Result<(), String> {
        if !(0.0..=1.0).contains(&self.floor_pct) {
            return Err("learning.thompson.floor_pct must be in [0, 1]".into());
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// AgentBehavior — Agent 行為偏好
// ---------------------------------------------------------------------------

/// Agent self-tuning behavioural preferences (NOT hard risk limits).
/// Agent 自我調整的行為偏好（不是硬風控）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentBehavior {
    /// Minimum signal confidence to open a new position.
    /// 開新倉所需的最小信號信心。
    #[serde(default = "default_entry_confidence_min")]
    pub entry_confidence_min: f64,

    /// Minimum expected edge in basis points to enter.
    /// 進場所需的最小預期 edge（基點）。
    #[serde(default = "default_min_edge_bps")]
    pub min_edge_bps: f64,

    /// Kelly fraction multiplier (0 = Kelly disabled, 1.0 = full Kelly).
    /// Kelly 比例縮放（0 = 禁用，1.0 = 全 Kelly）。
    #[serde(default = "default_kelly_fraction")]
    pub kelly_fraction: f64,

    /// Max concurrent positions per strategy. None = unlimited.
    /// 每策略並行持倉上限。None = 不限。
    #[serde(default)]
    pub max_positions_per_strategy: Option<u32>,

    /// Max concurrent positions per symbol. None = unlimited.
    /// 每幣種並行持倉上限。None = 不限。
    #[serde(default)]
    pub max_positions_per_symbol: Option<u32>,

    /// Move stop to break-even when PnL exceeds this %. None = disabled.
    /// 當 PnL 超過此百分比時將 stop 移到保本。None = 禁用。
    #[serde(default)]
    pub breakeven_trigger_pct: Option<f64>,

    /// Regime types Agent wants to trade. Empty = all regimes.
    /// Agent 想交易的 regime 類型。空 = 全部 regime。
    #[serde(default)]
    pub regime_whitelist: Vec<String>,

    /// Preferred order type: "market" | "limit" | "post_only".
    /// 偏好訂單類型。
    #[serde(default = "default_order_type_preference")]
    pub order_type_preference: String,

    /// Number of chunks to split a single entry into. 1 = no split.
    /// 分批進場的 chunk 數。1 = 不分批。
    #[serde(default = "default_entry_split_chunks")]
    pub entry_split_chunks: u32,
}

fn default_entry_confidence_min() -> f64 {
    0.55
}
fn default_min_edge_bps() -> f64 {
    5.0
}
fn default_kelly_fraction() -> f64 {
    0.25
}
fn default_order_type_preference() -> String {
    "market".into()
}
fn default_entry_split_chunks() -> u32 {
    1
}

impl Default for AgentBehavior {
    fn default() -> Self {
        Self {
            entry_confidence_min: default_entry_confidence_min(),
            min_edge_bps: default_min_edge_bps(),
            kelly_fraction: default_kelly_fraction(),
            max_positions_per_strategy: None,
            max_positions_per_symbol: None,
            breakeven_trigger_pct: None,
            regime_whitelist: Vec::new(),
            order_type_preference: default_order_type_preference(),
            entry_split_chunks: default_entry_split_chunks(),
        }
    }
}

impl AgentBehavior {
    fn validate(&self) -> Result<(), String> {
        if !(0.0..=1.0).contains(&self.entry_confidence_min) {
            return Err("learning.agent.entry_confidence_min must be in [0, 1]".into());
        }
        if self.min_edge_bps < 0.0 {
            return Err("learning.agent.min_edge_bps must be >= 0".into());
        }
        if !(0.0..=1.0).contains(&self.kelly_fraction) {
            return Err("learning.agent.kelly_fraction must be in [0, 1]".into());
        }
        if self.entry_split_chunks == 0 {
            return Err("learning.agent.entry_split_chunks must be >= 1".into());
        }
        if let Some(b) = self.breakeven_trigger_pct {
            if b <= 0.0 {
                return Err("learning.agent.breakeven_trigger_pct must be > 0 when set".into());
            }
        }
        match self.order_type_preference.as_str() {
            "market" | "limit" | "post_only" => {}
            other => {
                return Err(format!(
                    "learning.agent.order_type_preference must be one of market/limit/post_only, got '{}'",
                    other
                ))
            }
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Experimental
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Experimental {
    #[serde(default)]
    pub flags: HashMap<String, serde_json::Value>,
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_validates() {
        let cfg = LearningConfig::default();
        assert!(cfg.validate().is_ok());
    }

    #[test]
    fn test_phase_4_1_default_off_contract() {
        let cfg = LearningConfig::default();
        assert!(
            !cfg.switches.teacher_loop_enabled,
            "Phase 4.1 teacher loop must default OFF"
        );
        // Other switches default ON for normal operation
        assert!(cfg.switches.linucb_enabled);
        assert!(cfg.switches.thompson_enabled);
        assert!(cfg.switches.directive_apply_enabled);
        assert!(cfg.switches.scorer_enabled);
        assert!(cfg.switches.news_pipeline_enabled);
    }

    #[test]
    fn test_invalid_entry_confidence_rejected() {
        let mut cfg = LearningConfig::default();
        cfg.agent.entry_confidence_min = 1.5;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_invalid_kelly_fraction_rejected() {
        let mut cfg = LearningConfig::default();
        cfg.agent.kelly_fraction = 2.0;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_kelly_disabled_zero_allowed() {
        let mut cfg = LearningConfig::default();
        cfg.agent.kelly_fraction = 0.0;
        assert!(cfg.validate().is_ok());
    }

    #[test]
    fn test_zero_entry_split_rejected() {
        let mut cfg = LearningConfig::default();
        cfg.agent.entry_split_chunks = 0;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_invalid_order_type_rejected() {
        let mut cfg = LearningConfig::default();
        cfg.agent.order_type_preference = "iceberg".into();
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_breakeven_negative_rejected() {
        let mut cfg = LearningConfig::default();
        cfg.agent.breakeven_trigger_pct = Some(-1.0);
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_linucb_zero_lambda_rejected() {
        let mut cfg = LearningConfig::default();
        cfg.linucb.ridge_lambda = 0.0;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_thompson_floor_pct_out_of_range() {
        let mut cfg = LearningConfig::default();
        cfg.thompson.floor_pct = 1.5;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_toml_round_trip_default() {
        let cfg = LearningConfig::default();
        let toml_str = toml::to_string(&cfg).unwrap();
        let de: LearningConfig = toml::from_str(&toml_str).unwrap();
        assert!(de.validate().is_ok());
        assert!(!de.switches.teacher_loop_enabled);
    }

    #[test]
    fn test_json_round_trip_with_overrides() {
        let mut cfg = LearningConfig::default();
        cfg.agent.regime_whitelist = vec!["trending".into(), "volatile".into()];
        cfg.agent.max_positions_per_strategy = Some(3);
        cfg.switches.teacher_loop_enabled = true;
        let json = serde_json::to_string(&cfg).unwrap();
        let de: LearningConfig = serde_json::from_str(&json).unwrap();
        assert_eq!(de.agent.regime_whitelist.len(), 2);
        assert_eq!(de.agent.max_positions_per_strategy, Some(3));
        assert!(de.switches.teacher_loop_enabled);
    }

    #[test]
    fn test_partial_toml_uses_defaults() {
        let toml_str = r#"
[switches]
teacher_loop_enabled = true
"#;
        let cfg: LearningConfig = toml::from_str(toml_str).unwrap();
        assert!(cfg.switches.teacher_loop_enabled);
        // Other defaults preserved / 其他預設值保留
        assert!(cfg.switches.linucb_enabled);
        assert_eq!(cfg.linucb.exploration_weight, 1.0);
        assert!(cfg.validate().is_ok());
    }
}
