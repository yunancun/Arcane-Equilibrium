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

// ---------------------------------------------------------------------------
// SlippageConfig (G7-07) — cost-gate slippage tiers + win-rate weighting knobs.
// 成本門滑點分級表 + 勝率加權可調 knob。
// ---------------------------------------------------------------------------

/// G7-07 (2026-04-24): Cost-gate slippage assumptions consolidated into a single
/// hot-reloadable struct. Defaults preserve the pre-G7-07 hardcoded values
/// (`SLIPPAGE_TIERS`, `DEFAULT_SLIPPAGE_RATE`, `win_rate.clamp(0.3, 1.0)`,
/// `× 1.3` safety margin) so engine behaviour is bit-identical when this section
/// is absent from `risk_config*.toml`.
///
/// G7-07：成本門滑點假設整合進可熱重載 struct；預設保持 G7-07 前的硬編碼數值
/// （`SLIPPAGE_TIERS` / `DEFAULT_SLIPPAGE_RATE` / 勝率 floor 0.3 / safety
/// multiplier 1.3），TOML 缺此 section 時引擎行為 bit-identical。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SlippageConfig {
    /// Default slippage rate (decimal, NOT bps — `0.0005` = 5 bps) used when
    /// `volume_24h <= 0.0` or no tier matches. Validated 0 ≤ rate ≤ 0.01
    /// (1.0 % cap to catch unit confusion).
    /// 默認滑點率（小數而非 bps，`0.0005` = 5 bps）；當 24h 成交量無法判斷
    /// 或無 tier 命中時回退。Validate 限制 [0, 0.01]（1% 上限防單位混淆）。
    #[serde(default = "default_slippage_default_rate")]
    pub default_rate: f64,
    /// Volume-tier table sorted by descending `min_turnover_usd`. Lookup picks
    /// the first row whose `min_turnover_usd <= volume_24h`. Defaults mirror
    /// the pre-G7-07 SLIPPAGE_TIERS exactly. Empty list ⇒ always fall back
    /// to `default_rate`.
    /// 成交量分級表（依 `min_turnover_usd` 降序）。Lookup 選首個
    /// `min_turnover_usd <= volume_24h` 的列；空列表 ⇒ 永用 `default_rate`。
    /// 預設與 G7-07 前 SLIPPAGE_TIERS 完全一致。
    #[serde(default = "default_slippage_tiers")]
    pub tiers: Vec<SlippageTier>,
    /// Lower clamp on `win_rate` when computing the cost-gate threshold.
    /// `threshold_bps = fee_bps / max(floor, win_rate) × safety_multiplier`.
    /// Pre-G7-07 hardcoded `0.3`. Validated 0 < floor < 1.
    /// 成本門 threshold 計算時對 `win_rate` 的下限 clamp。
    /// `threshold_bps = fee_bps / max(floor, win_rate) × safety_multiplier`。
    /// G7-07 前硬編 0.3。Validate 限制 (0, 1)。
    #[serde(default = "default_cost_gate_win_rate_floor")]
    pub cost_gate_win_rate_floor: f64,
    /// Safety multiplier applied to the win-rate-weighted threshold above.
    /// Pre-G7-07 hardcoded `1.3` (= 30 % buffer). Validated 1 ≤ x ≤ 5.
    /// 勝率加權 threshold 的 safety multiplier；G7-07 前硬編 1.3（30% buffer）。
    /// Validate 限制 [1, 5]。
    #[serde(default = "default_cost_gate_safety_multiplier")]
    pub cost_gate_safety_multiplier: f64,
}

/// One row of the slippage volume-tier table.
/// 滑點成交量分級表單一條目。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SlippageTier {
    /// Lower-bound 24h USD turnover for this tier (inclusive).
    /// 本級 24h USD 成交量下限（含）。
    pub min_turnover_usd: f64,
    /// Slippage rate (decimal) applied when `volume_24h >= min_turnover_usd`.
    /// 命中本級時套用的滑點率（小數）。
    pub rate: f64,
}

fn default_slippage_default_rate() -> f64 {
    0.0005 // 5 bps — fallback when volume unavailable
}

fn default_slippage_tiers() -> Vec<SlippageTier> {
    // Mirrors pre-G7-07 SLIPPAGE_TIERS in `intent_processor::mod`.
    // 對齊 G7-07 前 intent_processor::mod 的 SLIPPAGE_TIERS。
    vec![
        SlippageTier {
            min_turnover_usd: 1_000_000_000.0,
            rate: 0.0001, // >$1B: 1 bps (BTC/ETH)
        },
        SlippageTier {
            min_turnover_usd: 100_000_000.0,
            rate: 0.0002, // >$100M: 2 bps
        },
        SlippageTier {
            min_turnover_usd: 10_000_000.0,
            rate: 0.0005, // >$10M: 5 bps
        },
        SlippageTier {
            min_turnover_usd: 1_000_000.0,
            rate: 0.0015, // >$1M: 15 bps
        },
        SlippageTier {
            min_turnover_usd: 0.0,
            rate: 0.0030, // <$1M: 30 bps (illiquid alts)
        },
    ]
}

fn default_cost_gate_win_rate_floor() -> f64 {
    0.3
}

fn default_cost_gate_safety_multiplier() -> f64 {
    1.3
}

impl Default for SlippageConfig {
    fn default() -> Self {
        Self {
            default_rate: default_slippage_default_rate(),
            tiers: default_slippage_tiers(),
            cost_gate_win_rate_floor: default_cost_gate_win_rate_floor(),
            cost_gate_safety_multiplier: default_cost_gate_safety_multiplier(),
        }
    }
}

impl SlippageConfig {
    /// Validate cross-field invariants and ranges.
    /// 驗證跨欄位不變量與範圍。
    pub(super) fn validate(&self) -> Result<(), String> {
        if !(0.0..=0.01).contains(&self.default_rate) {
            return Err(
                "risk.slippage.default_rate must be in [0, 0.01] (decimal, 1 % cap)".into(),
            );
        }
        if !(0.0..1.0).contains(&self.cost_gate_win_rate_floor) {
            return Err(
                "risk.slippage.cost_gate_win_rate_floor must be in [0, 1) (exclusive upper)".into(),
            );
        }
        if !(1.0..=5.0).contains(&self.cost_gate_safety_multiplier) {
            return Err("risk.slippage.cost_gate_safety_multiplier must be in [1, 5]".into());
        }
        // Tiers: validate each row, plus descending min_turnover_usd ordering.
        let mut prev_floor: Option<f64> = None;
        for (i, tier) in self.tiers.iter().enumerate() {
            if tier.min_turnover_usd < 0.0 {
                return Err(format!(
                    "risk.slippage.tiers[{}].min_turnover_usd must be >= 0",
                    i
                ));
            }
            if !(0.0..=0.01).contains(&tier.rate) {
                return Err(format!(
                    "risk.slippage.tiers[{}].rate must be in [0, 0.01] (decimal, 1 % cap)",
                    i
                ));
            }
            if let Some(prev) = prev_floor {
                if tier.min_turnover_usd >= prev {
                    return Err(format!(
                        "risk.slippage.tiers must be sorted by descending min_turnover_usd \
                         (row {} = {} not strictly less than previous {})",
                        i, tier.min_turnover_usd, prev
                    ));
                }
            }
            prev_floor = Some(tier.min_turnover_usd);
        }
        Ok(())
    }

    /// Look up the slippage rate for a given 24h USD turnover. Picks the first
    /// tier whose `min_turnover_usd <= volume_24h`; falls back to `default_rate`
    /// when `volume_24h <= 0` or no tier matches.
    /// 給定 24h USD 成交量取滑點率。選首個 `min_turnover_usd <= volume_24h`
    /// 的 tier；`volume_24h <= 0` 或無命中 → fallback `default_rate`。
    pub fn lookup_rate(&self, volume_24h: f64) -> f64 {
        if volume_24h <= 0.0 {
            return self.default_rate;
        }
        for tier in &self.tiers {
            if volume_24h >= tier.min_turnover_usd {
                return tier.rate;
            }
        }
        self.default_rate
    }
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    // ── G7-07 SlippageConfig tests ──

    #[test]
    fn slippage_config_default_validates() {
        // Pre-G7-07 hardcoded values must be valid under the new validator.
        // G7-07 前硬編值在新 validator 下必須通過。
        assert!(SlippageConfig::default().validate().is_ok());
    }

    #[test]
    fn slippage_config_default_lookup_matches_pre_g7_07_tiers() {
        // Default lookup MUST be bit-identical to pre-G7-07 SLIPPAGE_TIERS.
        // 默認 lookup 必須與 G7-07 前 SLIPPAGE_TIERS bit-identical。
        let cfg = SlippageConfig::default();
        assert_eq!(cfg.lookup_rate(2_000_000_000.0), 0.0001); // >$1B
        assert_eq!(cfg.lookup_rate(500_000_000.0), 0.0002); // >$100M
        assert_eq!(cfg.lookup_rate(50_000_000.0), 0.0005); // >$10M
        assert_eq!(cfg.lookup_rate(5_000_000.0), 0.0015); // >$1M
        assert_eq!(cfg.lookup_rate(100_000.0), 0.0030); // <$1M
        // Volume <= 0 falls back to default_rate (5 bps).
        assert_eq!(cfg.lookup_rate(0.0), 0.0005);
        assert_eq!(cfg.lookup_rate(-1.0), 0.0005);
    }

    #[test]
    fn slippage_config_rejects_default_rate_above_cap() {
        // 1.5 % rate is well above sanity cap → reject.
        // 1.5 % 遠超合理上限 → 拒絕。
        let mut cfg = SlippageConfig::default();
        cfg.default_rate = 0.015;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn slippage_config_rejects_win_rate_floor_at_one() {
        // floor must be strictly less than 1.0 (else gate tightens to 0 bps).
        // floor 必須 < 1.0（否則 gate 收緊到 0 bps）。
        let mut cfg = SlippageConfig::default();
        cfg.cost_gate_win_rate_floor = 1.0;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn slippage_config_rejects_safety_multiplier_below_one() {
        // multiplier < 1 would loosen the gate below break-even — disallow.
        // multiplier < 1 會把 gate 放鬆到負 EV，禁止。
        let mut cfg = SlippageConfig::default();
        cfg.cost_gate_safety_multiplier = 0.9;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn slippage_config_rejects_unsorted_tiers() {
        // Tier table must be descending by min_turnover_usd; ascending = reject.
        // tier 表必須以 min_turnover_usd 降序；升序 → 拒絕。
        let cfg = SlippageConfig {
            tiers: vec![
                SlippageTier {
                    min_turnover_usd: 1_000_000.0,
                    rate: 0.0015,
                },
                SlippageTier {
                    min_turnover_usd: 10_000_000.0,
                    rate: 0.0005,
                },
            ],
            ..SlippageConfig::default()
        };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn slippage_config_custom_tiers_lookup() {
        // Operator can shrink the table to a single tier; lookup remains sane.
        // operator 可把 table 縮成單 tier，lookup 仍合理。
        let cfg = SlippageConfig {
            default_rate: 0.001,
            tiers: vec![SlippageTier {
                min_turnover_usd: 500_000.0,
                rate: 0.0008,
            }],
            cost_gate_win_rate_floor: 0.4,
            cost_gate_safety_multiplier: 1.5,
        };
        assert!(cfg.validate().is_ok());
        assert_eq!(cfg.lookup_rate(1_000_000.0), 0.0008); // hits the only tier
        assert_eq!(cfg.lookup_rate(100_000.0), 0.001); // below tier → default
        assert_eq!(cfg.lookup_rate(0.0), 0.001);
    }

    #[test]
    fn slippage_config_empty_tiers_uses_default_rate() {
        // Empty tier list ⇒ every positive volume returns default_rate.
        // 空 tier 列表 ⇒ 任何正成交量都回 default_rate。
        let cfg = SlippageConfig {
            tiers: vec![],
            ..SlippageConfig::default()
        };
        assert!(cfg.validate().is_ok());
        assert_eq!(cfg.lookup_rate(1_000_000_000.0), cfg.default_rate);
        assert_eq!(cfg.lookup_rate(1.0), cfg.default_rate);
    }

    #[test]
    fn slippage_config_toml_roundtrip_matches_pre_g7_07() {
        // Mirrors the TOML stanza added to risk_config*.toml; ensures wire format
        // is stable and deser yields identical lookup results to default.
        // 鏡像 risk_config*.toml 中新增的 stanza；驗證序列化格式穩定且 deser
        // lookup 結果與 default bit-identical。
        let toml_str = r#"
default_rate = 0.0005
cost_gate_win_rate_floor = 0.3
cost_gate_safety_multiplier = 1.3

[[tiers]]
min_turnover_usd = 1_000_000_000.0
rate = 0.0001

[[tiers]]
min_turnover_usd = 100_000_000.0
rate = 0.0002

[[tiers]]
min_turnover_usd = 10_000_000.0
rate = 0.0005

[[tiers]]
min_turnover_usd = 1_000_000.0
rate = 0.0015

[[tiers]]
min_turnover_usd = 0.0
rate = 0.003
"#;
        let cfg: SlippageConfig = toml::from_str(toml_str).expect("parse");
        assert!(cfg.validate().is_ok());
        // Same lookup results as Default.
        let dflt = SlippageConfig::default();
        for vol in [
            -1.0,
            0.0,
            500.0,
            500_000.0,
            5_000_000.0,
            50_000_000.0,
            500_000_000.0,
            2_000_000_000.0,
        ] {
            assert!(
                (cfg.lookup_rate(vol) - dflt.lookup_rate(vol)).abs() < f64::EPSILON,
                "vol={} mismatch: cfg={} dflt={}",
                vol,
                cfg.lookup_rate(vol),
                dflt.lookup_rate(vol)
            );
        }
    }
}
