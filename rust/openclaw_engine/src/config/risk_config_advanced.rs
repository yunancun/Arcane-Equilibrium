//! Advanced risk-config sub-structs (extracted from risk_config.rs).
//! 進階風控子配置（從 risk_config.rs 抽出）。
//!
//! MODULE_NOTE (EN): Extracted from `config/risk_config.rs` as Wave 1 G1-03
//!   Rust refactor wave. Groups sub-config structs that are logically "advanced"
//!   knobs — EdgePredictor / DynamicStop / MarketGate / AntiCluster / Correlation
//!   / RuntimeKnobs / Experimental — distinct from the top-level P0/P1 ceilings
//!   (GlobalLimits) and strategy overrides which stay in `risk_config.rs`.
//!   Loaded via `#[path = "risk_config_advanced.rs"] mod advanced;` in
//!   `risk_config.rs`; `pub use advanced::*` keeps the public API stable
//!   (`crate::config::risk_config::EdgePredictor`, etc.).
//! MODULE_NOTE (中): 從 `config/risk_config.rs` 抽出（Wave 1 G1-03 Rust refactor）。
//!   聚合「進階」子配置 struct（EdgePredictor / DynamicStop / MarketGate /
//!   AntiCluster / Correlation / RuntimeKnobs / Experimental），區別於頂層
//!   P0/P1 硬上限（GlobalLimits）與策略覆蓋（留在 risk_config.rs）。
//!   `risk_config.rs` 以 `#[path]` 加 `pub use advanced::*` 重新導出以保持
//!   公共 API 不變。

use super::default_true;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// ---------------------------------------------------------------------------
// EdgePredictor (EDGE-P3-1) — per-strategy quantile LGBM gate config.
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EdgePredictorFallback {
    Shrinkage,
    FailClosed,
}

impl Default for EdgePredictorFallback {
    fn default() -> Self {
        Self::Shrinkage
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EdgePredictor {
    #[serde(default = "default_edge_predictor_use")]
    pub use_edge_predictor: bool,
    #[serde(default = "default_edge_predictor_shadow")]
    pub shadow_mode: bool,
    #[serde(default = "default_edge_predictor_quantile_k")]
    pub quantile_safety_k: f64,
    #[serde(default = "default_edge_predictor_require_q10_pos_adds")]
    pub require_q10_positive_for_adds: bool,
    #[serde(default)]
    pub fallback_on_error: EdgePredictorFallback,
    #[serde(default = "default_edge_predictor_exploration_rate")]
    pub exploration_rate: f64,
    #[serde(default = "default_edge_predictor_retrain_cadence")]
    pub retrain_cadence_seconds: u64,
    #[serde(default = "default_edge_predictor_model_max_age")]
    pub model_max_age_seconds: u64,
}

fn default_edge_predictor_use() -> bool {
    false
}
fn default_edge_predictor_shadow() -> bool {
    true
}
fn default_edge_predictor_quantile_k() -> f64 {
    0.5
}
fn default_edge_predictor_require_q10_pos_adds() -> bool {
    true
}
fn default_edge_predictor_exploration_rate() -> f64 {
    0.05
}
fn default_edge_predictor_retrain_cadence() -> u64 {
    604_800 // 1 week
}
fn default_edge_predictor_model_max_age() -> u64 {
    1_209_600 // 2 weeks
}

impl Default for EdgePredictor {
    fn default() -> Self {
        Self {
            use_edge_predictor: default_edge_predictor_use(),
            shadow_mode: default_edge_predictor_shadow(),
            quantile_safety_k: default_edge_predictor_quantile_k(),
            require_q10_positive_for_adds: default_edge_predictor_require_q10_pos_adds(),
            fallback_on_error: EdgePredictorFallback::default(),
            exploration_rate: default_edge_predictor_exploration_rate(),
            retrain_cadence_seconds: default_edge_predictor_retrain_cadence(),
            model_max_age_seconds: default_edge_predictor_model_max_age(),
        }
    }
}

impl EdgePredictor {
    pub(super) fn validate(&self) -> Result<(), String> {
        if !(0.0..=1.0).contains(&self.quantile_safety_k) {
            return Err("risk.edge_predictor.quantile_safety_k must be in [0, 1]".into());
        }
        if !(0.0..=0.2).contains(&self.exploration_rate) {
            return Err("risk.edge_predictor.exploration_rate must be in [0, 0.2]".into());
        }
        if self.retrain_cadence_seconds == 0 {
            return Err("risk.edge_predictor.retrain_cadence_seconds must be > 0".into());
        }
        if self.model_max_age_seconds == 0 {
            return Err("risk.edge_predictor.model_max_age_seconds must be > 0".into());
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// DynamicStop
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DynamicStop {
    #[serde(default = "default_base_ratio")]
    pub base_ratio: f64,
    #[serde(default = "default_cap_ratio")]
    pub cap_ratio: f64,
    #[serde(default = "default_trailing_min_rr")]
    pub trailing_min_rr: f64,
    #[serde(default = "default_atr_stop_mult")]
    pub atr_stop_mult: f64,
    #[serde(default = "default_atr_tp_mult")]
    pub atr_tp_mult: f64,
}

fn default_base_ratio() -> f64 {
    0.6
}
fn default_cap_ratio() -> f64 {
    0.8
}
fn default_trailing_min_rr() -> f64 {
    0.5
}
fn default_atr_stop_mult() -> f64 {
    2.0
}
fn default_atr_tp_mult() -> f64 {
    3.0
}

impl Default for DynamicStop {
    fn default() -> Self {
        Self {
            base_ratio: default_base_ratio(),
            cap_ratio: default_cap_ratio(),
            trailing_min_rr: default_trailing_min_rr(),
            atr_stop_mult: default_atr_stop_mult(),
            atr_tp_mult: default_atr_tp_mult(),
        }
    }
}

impl DynamicStop {
    pub(super) fn validate(&self) -> Result<(), String> {
        if self.base_ratio <= 0.0 || self.cap_ratio <= 0.0 {
            return Err("risk.dynamic_stop ratios must be > 0".into());
        }
        if self.base_ratio > self.cap_ratio {
            return Err("risk.dynamic_stop.base_ratio must be <= cap_ratio".into());
        }
        if self.atr_stop_mult <= 0.0 || self.atr_tp_mult <= 0.0 {
            return Err("risk.dynamic_stop.atr_*_mult must be > 0".into());
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// MarketGate (microstructure, merged from former MarketConfig)
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketGate {
    #[serde(default = "default_min_ob_depth_usdt")]
    pub min_ob_depth_usdt: f64,
    #[serde(default = "default_max_ob_imbalance")]
    pub max_ob_imbalance: f64,
    #[serde(default = "default_min_volume_24h_usdt")]
    pub min_volume_24h_usdt: f64,
    #[serde(default = "default_max_taker_fee_bps")]
    pub max_taker_fee_bps: f64,
    #[serde(default = "default_spread_max_bps")]
    pub spread_max_bps: f64,
    #[serde(default = "default_slippage_max_bps")]
    pub slippage_max_bps: f64,
    #[serde(default = "default_funding_rate_max_abs")]
    pub funding_rate_max_abs: f64,
    #[serde(default = "default_liquidation_buffer_pct")]
    pub liquidation_buffer_pct: f64,
    #[serde(default = "default_max_orders_per_minute")]
    pub max_orders_per_minute: u32,
}

fn default_min_ob_depth_usdt() -> f64 {
    50_000.0
}
fn default_max_ob_imbalance() -> f64 {
    0.7
}
fn default_min_volume_24h_usdt() -> f64 {
    1_000_000.0
}
fn default_max_taker_fee_bps() -> f64 {
    8.0
}
fn default_spread_max_bps() -> f64 {
    20.0
}
fn default_slippage_max_bps() -> f64 {
    15.0
}
fn default_funding_rate_max_abs() -> f64 {
    0.03
}
fn default_liquidation_buffer_pct() -> f64 {
    20.0
}
fn default_max_orders_per_minute() -> u32 {
    60
}

impl Default for MarketGate {
    fn default() -> Self {
        Self {
            min_ob_depth_usdt: default_min_ob_depth_usdt(),
            max_ob_imbalance: default_max_ob_imbalance(),
            min_volume_24h_usdt: default_min_volume_24h_usdt(),
            max_taker_fee_bps: default_max_taker_fee_bps(),
            spread_max_bps: default_spread_max_bps(),
            slippage_max_bps: default_slippage_max_bps(),
            funding_rate_max_abs: default_funding_rate_max_abs(),
            liquidation_buffer_pct: default_liquidation_buffer_pct(),
            max_orders_per_minute: default_max_orders_per_minute(),
        }
    }
}

impl MarketGate {
    pub(super) fn validate(&self) -> Result<(), String> {
        if self.min_ob_depth_usdt < 0.0 || self.min_volume_24h_usdt < 0.0 {
            return Err("risk.market_gate min_* values must be >= 0".into());
        }
        if !(0.0..=1.0).contains(&self.max_ob_imbalance) {
            return Err("risk.market_gate.max_ob_imbalance must be in [0, 1]".into());
        }
        if self.spread_max_bps < 0.0 || self.slippage_max_bps < 0.0 {
            return Err("risk.market_gate spread/slippage bps must be >= 0".into());
        }
        if self.funding_rate_max_abs < 0.0 {
            return Err("risk.market_gate.funding_rate_max_abs must be >= 0".into());
        }
        if self.liquidation_buffer_pct < 0.0 {
            return Err("risk.market_gate.liquidation_buffer_pct must be >= 0".into());
        }
        if self.max_orders_per_minute == 0 {
            return Err("risk.market_gate.max_orders_per_minute must be >= 1".into());
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// AntiCluster
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AntiCluster {
    #[serde(default = "default_offset_fraction")]
    pub offset_fraction: f64,
    #[serde(default = "default_max_same_direction")]
    pub max_same_direction: u32,
}

fn default_offset_fraction() -> f64 {
    0.15
}

fn default_max_same_direction() -> u32 {
    3
}

impl Default for AntiCluster {
    fn default() -> Self {
        Self {
            offset_fraction: default_offset_fraction(),
            max_same_direction: default_max_same_direction(),
        }
    }
}

impl AntiCluster {
    pub(super) fn validate(&self) -> Result<(), String> {
        if !(0.0..=0.5).contains(&self.offset_fraction) {
            return Err("risk.anti_cluster.offset_fraction must be in [0, 0.5]".into());
        }
        if !(1..=100).contains(&self.max_same_direction) {
            return Err("risk.anti_cluster.max_same_direction must be in [1, 100]".into());
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Correlation
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Correlation {
    #[serde(default = "default_max_pairwise_r")]
    pub max_pairwise_r: f64,
    #[serde(default = "default_correlation_window_minutes")]
    pub window_minutes: u32,
}

fn default_max_pairwise_r() -> f64 {
    0.7
}
fn default_correlation_window_minutes() -> u32 {
    60
}

impl Default for Correlation {
    fn default() -> Self {
        Self {
            max_pairwise_r: default_max_pairwise_r(),
            window_minutes: default_correlation_window_minutes(),
        }
    }
}

impl Correlation {
    pub(super) fn validate(&self) -> Result<(), String> {
        if !(0.0..=1.0).contains(&self.max_pairwise_r) {
            return Err("risk.correlation.max_pairwise_r must be in [0, 1]".into());
        }
        if self.window_minutes == 0 {
            return Err("risk.correlation.window_minutes must be >= 1".into());
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// RuntimeKnobs
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeKnobs {
    #[serde(default = "default_boot_cooldown_ms")]
    pub boot_cooldown_ms: u64,
    #[serde(default = "default_signals_heartbeat_ms")]
    pub signals_heartbeat_ms: u64,
    #[serde(default = "default_true")]
    pub h0_shadow_mode: bool,
}

fn default_boot_cooldown_ms() -> u64 {
    60_000
}
fn default_signals_heartbeat_ms() -> u64 {
    60_000
}

impl Default for RuntimeKnobs {
    fn default() -> Self {
        Self {
            boot_cooldown_ms: default_boot_cooldown_ms(),
            signals_heartbeat_ms: default_signals_heartbeat_ms(),
            h0_shadow_mode: default_true(),
        }
    }
}

impl RuntimeKnobs {
    pub(super) fn validate(&self) -> Result<(), String> {
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
