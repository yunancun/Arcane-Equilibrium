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
    /// Minimum `n_trades` required for `cost_gate_moderate` (demo path) to BLOCK
    /// on a negative shrunk_bps. Below this threshold the JS estimate is treated
    /// as noise-dominated and the gate switches to exploration mode (allow + log)
    /// so demo can keep accumulating data toward statistically robust estimates.
    /// Live path (`cost_gate_live`) is unaffected — it remains strict per
    /// CLAUDE.md §四 (operator policy: demo loose, live strict).
    /// Default 30 (≈ CLT threshold). Validated 1 ≤ x ≤ 1000.
    /// 拒絕負 shrunk_bps 前要求的最小 n_trades（demo cost_gate_moderate 路徑）。
    /// 低於此值則 JS 估計被視為噪音主導，gate 切換到探索模式（放行+log），
    /// 讓 demo 累積資料以達到統計穩健估計。Live 路徑不受影響，仍保持嚴格
    /// （CLAUDE.md §四 operator 政策：demo 放寬 / live 收緊）。
    /// 預設 30（≈ CLT 門檻）。Validate 限制 [1, 1000]。
    #[serde(default = "default_cost_gate_min_n_trades_for_block")]
    pub cost_gate_min_n_trades_for_block: u64,
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

fn default_cost_gate_min_n_trades_for_block() -> u64 {
    30
}

impl Default for SlippageConfig {
    fn default() -> Self {
        Self {
            default_rate: default_slippage_default_rate(),
            tiers: default_slippage_tiers(),
            cost_gate_win_rate_floor: default_cost_gate_win_rate_floor(),
            cost_gate_safety_multiplier: default_cost_gate_safety_multiplier(),
            cost_gate_min_n_trades_for_block: default_cost_gate_min_n_trades_for_block(),
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
        if !(1..=1000).contains(&self.cost_gate_min_n_trades_for_block) {
            return Err(
                "risk.slippage.cost_gate_min_n_trades_for_block must be in [1, 1000]".into(),
            );
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
    fn slippage_config_default_min_n_trades_is_30() {
        // EDGE-DIAG-2 (2026-04-28): pin the documented default so future drift
        // is caught — operator policy refers to "n>=30" CLT threshold.
        // EDGE-DIAG-2：釘住預設 30，避免未來漂移；operator 政策參考 n>=30 CLT。
        assert_eq!(
            SlippageConfig::default().cost_gate_min_n_trades_for_block,
            30
        );
    }

    #[test]
    fn slippage_config_rejects_min_n_trades_zero() {
        // EDGE-DIAG-2: 0 would mean "block every estimate immediately" which
        // negates the purpose of n-trades stratification. Reject.
        // EDGE-DIAG-2：0 等於「立即阻擋所有估計」，違反分層用意，拒絕。
        let mut cfg = SlippageConfig::default();
        cfg.cost_gate_min_n_trades_for_block = 0;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn slippage_config_rejects_min_n_trades_too_high() {
        // EDGE-DIAG-2: > 1000 would mean "essentially never block" — likely a
        // typo or unit confusion (e.g., trader meant "1000 fills" but config
        // accepts u64). Cap at 1000 to surface the mistake.
        // EDGE-DIAG-2：>1000 等於「實際上永不阻擋」，疑似 typo；硬上限 1000。
        let mut cfg = SlippageConfig::default();
        cfg.cost_gate_min_n_trades_for_block = 5000;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn slippage_config_accepts_min_n_trades_boundary_values() {
        // Boundary check: 1 (minimum) and 1000 (maximum) must both validate.
        // 邊界：最小 1、最大 1000 皆須通過 validate。
        let mut cfg = SlippageConfig::default();
        cfg.cost_gate_min_n_trades_for_block = 1;
        assert!(cfg.validate().is_ok());
        cfg.cost_gate_min_n_trades_for_block = 1000;
        assert!(cfg.validate().is_ok());
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
            cost_gate_min_n_trades_for_block: 30,
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

// ===========================================================================
// G3-02 / G7-02 / G7-04 Phase A schema sub-structs (relocated from
// risk_config.rs 2026-04-25 to bring main file back under §九 1200-line cap).
// Behaviour bit-identical — only the file boundary moved.
// 從 risk_config.rs 搬遷至此（2026-04-25）以滿足 §九 1200 行硬上限。
// ===========================================================================

// ---------------------------------------------------------------------------
// ExecutorConfig — ExecutorAgent shadow→live control plane (G3-02 Phase A)
// ExecutorAgent shadow→live 控制平面（G3-02 Phase A）
// ---------------------------------------------------------------------------

/// G3-02 Phase A (2026-04-25): canonical ExecutorAgent control plane.
///
/// Replaces the hardcoded `_shadow_mode = True` class attribute on Python
/// `app/executor_agent.py:482` per RFC at
/// `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--g3_01_executor_agent_ipc_rfc.md`.
/// The Python attribute violated DOC-01 principle #3 (AI output ≠ immediate
/// command) because flipping required a code edit + rebuild instead of the
/// `<60s` IPC hot-reload turnaround used for the rest of the trading config.
///
/// Phase A scope: schema + TOML section + validation. Defaults preserve the
/// pre-G3-02 Python ExecutorAgent behavior (shadow_mode = true), so this
/// struct is dormant — no runtime change until Phase B wires Python's read
/// path through a cache layer and Phase C connects an operator IPC flip
/// behind the existing live-gate auth chain.
///
/// G3-02 Phase A：ExecutorAgent 控制平面落地。原 Python 硬編碼旗標違反
/// 原則 #3，現提升為 Rust ConfigStore 一級欄位。Phase A 僅落 schema +
/// TOML + validation；預設 shadow_mode=true 保留現行為，Phase B/C 後續完成。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutorConfig {
    /// Shadow mode flag.
    /// - `true`: log intents, do NOT submit orders to Bybit.
    /// - `false`: submit orders (requires full live-gate chain green).
    ///
    /// Default `true` preserves current Python ExecutorAgent behavior, so
    /// Phase A landing has zero runtime impact. Phase B reads via cache;
    /// Phase C unlocks operator IPC flip behind auth.
    /// 影子模式旗標。true=log 但不下單；false=真實下單（需 live-gate 全綠）。
    #[serde(default = "default_executor_shadow_mode")]
    pub shadow_mode: bool,
    /// Maximum position size as fraction of available margin (0.0 – 1.0).
    /// Per-symbol overrides via `per_symbol_position_cap` take precedence.
    /// Default `0.05` (5%) — conservative starting point matching the
    /// existing P0/P1 cascade defaults.
    /// 最大倉位佔保證金比例（0.0–1.0）；per-symbol 覆蓋優先。預設 5%。
    #[serde(default = "default_executor_max_position_pct")]
    pub max_position_pct: f64,
    /// Per-symbol max position fraction overrides. Symbol → fraction (0.0–1.0).
    /// Empty default = use `max_position_pct` for all symbols.
    /// 逐 symbol 最大倉位比例覆蓋；空表 = 全 symbol 用 max_position_pct。
    #[serde(default)]
    pub per_symbol_position_cap: HashMap<String, f64>,
}

fn default_executor_shadow_mode() -> bool {
    // Phase A safe default: preserve pre-G3-02 Python ExecutorAgent behavior
    // (forced shadow). Phase C operator IPC flip lifts this once verified.
    // Phase A 安全默認：保留 Python ExecutorAgent 強制 shadow 行為。
    true
}

fn default_executor_max_position_pct() -> f64 {
    // 5% — matches the conservative starting point in P0/P1 cascade defaults.
    // 5% — 與 P0/P1 cascade 默認保守起點一致。
    0.05
}

impl Default for ExecutorConfig {
    fn default() -> Self {
        Self {
            shadow_mode: default_executor_shadow_mode(),
            max_position_pct: default_executor_max_position_pct(),
            per_symbol_position_cap: HashMap::new(),
        }
    }
}

impl ExecutorConfig {
    /// G3-02 Phase A: validate fraction bounds.
    /// G3-02 Phase A：驗證比例範圍。
    pub fn validate(&self) -> Result<(), String> {
        if !(0.0..=1.0).contains(&self.max_position_pct) {
            return Err(format!(
                "risk.executor.max_position_pct ({}) must be in [0.0, 1.0]",
                self.max_position_pct
            ));
        }
        for (symbol, frac) in &self.per_symbol_position_cap {
            if !(0.0..=1.0).contains(frac) {
                return Err(format!(
                    "risk.executor.per_symbol_position_cap[{}] ({}) must be in [0.0, 1.0]",
                    symbol, frac
                ));
            }
            if symbol.is_empty() {
                return Err("risk.executor.per_symbol_position_cap key must be non-empty".into());
            }
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// EwmaVolConfig — Per-timeframe EWMA Vol lambda decay constants (G7-02)
// 逐 timeframe EWMA Vol lambda 衰減常數 (G7-02)
// ---------------------------------------------------------------------------

/// G7-02 (2026-04-24): Operator-tunable EWMA Vol lambda overrides per
/// timeframe. The pre-G7-02 hardcoded `0.97` was applied uniformly to every
/// timeframe; operators now configure timeframe-specific decay so a 1m series
/// can decay faster (e.g. 0.94) than a 4h series (e.g. 0.97 / 0.99).
///
/// `default_lambda` is the fallback when the requested timeframe has no
/// per-timeframe override, so existing call sites stay bit-identical when the
/// `lambdas` map is empty (the pre-G7-02 behavior).
///
/// `validate()` rejects any lambda outside the open interval `(0.0, 1.0)` —
/// the same range `openclaw_core::indicators::ewma_vol` enforces internally,
/// so an out-of-range value would silently make `EwmaVolResult` `None` for
/// every tick. We fail fast at config-load time instead.
///
/// G7-02：逐 timeframe EWMA Vol lambda 覆寫。`default_lambda` 為缺失 fallback，
/// `validate()` 強制 lambda 落於 `(0.0, 1.0)` 開區間。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EwmaVolConfig {
    /// Fallback lambda when the requested timeframe has no per-tf override.
    /// Default `0.97` mirrors the pre-G7-02 hardcoded value.
    /// 缺失 timeframe 覆寫時的 fallback；預設 0.97 保留 G7-02 前行為。
    #[serde(default = "default_ewma_vol_lambda")]
    pub default_lambda: f64,
    /// Per-timeframe lambda overrides keyed by timeframe string ("1m", "5m",
    /// "1h", "4h", ...). Empty by default → all timeframes use
    /// `default_lambda`. Operators add entries to tune specific timeframes.
    /// 逐 timeframe lambda 覆寫；預設空表 → 全部走 `default_lambda`。
    #[serde(default)]
    pub lambdas: HashMap<String, f64>,
}

fn default_ewma_vol_lambda() -> f64 {
    // 0.97 — RiskMetrics convention for sub-daily series, matches the
    // pre-G7-02 hardcoded constant in `indicators::IndicatorEngine::compute_all`.
    // 0.97 — RiskMetrics 慣例（次日級數列），與 G7-02 前的硬編碼常量對齊。
    openclaw_core::indicators::DEFAULT_EWMA_VOL_LAMBDA
}

impl Default for EwmaVolConfig {
    fn default() -> Self {
        Self {
            default_lambda: default_ewma_vol_lambda(),
            lambdas: HashMap::new(),
        }
    }
}

impl EwmaVolConfig {
    /// G7-02: Validate that `default_lambda` and every per-tf override sit
    /// in the open interval `(0.0, 1.0)` — the EWMA recursion needs
    /// `0 < lambda < 1` (lambda=0 collapses to last-tick variance, lambda=1
    /// freezes the first-tick variance forever).
    /// G7-02：驗證 `default_lambda` 與 per-tf 覆寫皆落於 (0.0, 1.0) 開區間。
    pub fn validate(&self) -> Result<(), String> {
        if !(0.0 < self.default_lambda && self.default_lambda < 1.0) {
            return Err(format!(
                "risk.ewma_vol.default_lambda ({}) must be in open interval (0.0, 1.0)",
                self.default_lambda
            ));
        }
        for (tf, lambda) in &self.lambdas {
            if tf.is_empty() {
                return Err("risk.ewma_vol.lambdas timeframe key must be non-empty".into());
            }
            if !(0.0 < *lambda && *lambda < 1.0) {
                return Err(format!(
                    "risk.ewma_vol.lambdas[{}] ({}) must be in open interval (0.0, 1.0)",
                    tf, lambda
                ));
            }
        }
        Ok(())
    }

    /// G7-02: Look up the configured lambda for a timeframe, falling back to
    /// `default_lambda` when no per-tf override exists. Hot-path safe (single
    /// HashMap lookup on the live snapshot).
    /// G7-02：依 timeframe 查 lambda；缺失時退回 `default_lambda`。
    pub fn lambda_for_timeframe(&self, tf: &str) -> f64 {
        self.lambdas.get(tf).copied().unwrap_or(self.default_lambda)
    }
}

// ---------------------------------------------------------------------------
// CusumConfig — Strategy edge-decay CUSUM monitor schema (G7-04 Phase A)
// 策略衰減 CUSUM 監控 schema（G7-04 Phase A）
// ---------------------------------------------------------------------------

/// G7-04 (2026-04-24): One-sided downward CUSUM (Cumulative Sum) control chart
/// parameters for monitoring per-strategy edge decay.
///
/// CUSUM is a sequential change-point detector: it accumulates deviations from
/// a target reference level and alarms when the cumulative sum exceeds a
/// σ-scaled threshold. For trading-edge decay we want only the LOWER side
/// (alarm when realized PnL drifts BELOW target, never above), so this struct
/// encodes a one-sided downward CUSUM:
///
/// ```text
///   S_t = max(0, S_{t-1} - (x_t - target_return_bps) - slack_k * σ)
///   alarm when S_t > threshold_h * σ
/// ```
///
/// where `σ` is an estimate of the per-trade PnL standard deviation (drawn
/// from EWMA-vol or a similar hot-path source by the future runtime wiring).
///
/// Phase A scope: schema + TOML section + validation only. Defaults
/// `enabled = false` keep this struct dormant — no `dynamic_risk_sizer` /
/// strategy-disable hook fires while operators evaluate the schema. Wiring
/// hookup is deferred to a future G7-04 follow-up (or to whichever G3-X
/// task consumes the alarm signal first).
///
/// Defaults follow the standard quant-control-chart literature:
/// - `slack_k = 0.5`: small drifts under 0.5σ are absorbed by the deadband.
/// - `threshold_h = 4.0`: classic Page H-decision boundary (4–5σ band).
/// - `min_observations = 30`: warm-up before evaluating; rejects spurious
///   alarms on the first few trades.
/// - `target_return_bps = 0.0`: breakeven net of fees (operators tune to
///   per-strategy expected gross edge minus realized cost).
///
/// `validate()` enforces:
/// - `slack_k > 0` (zero deadband collapses to instant alarm on any drift)
/// - `slack_k < threshold_h` (otherwise σ-scaled threshold sits inside the
///   deadband and an alarm is unreachable)
/// - `threshold_h > 0` and `<= 100` (sanity ceiling — beyond ~10σ the chart
///   is effectively never going to alarm; 100 is a generous upper bound)
/// - `min_observations >= 5` (any smaller warm-up makes the σ estimate
///   degenerate)
///
/// G7-04：單側下行 CUSUM 控制圖參數，用於監控策略 edge 衰減。
/// Phase A 僅落 schema + TOML + validate，預設 enabled=false 保留現行為，
/// runtime wiring 留給後續 follow-up。validate() 強制 slack_k < threshold_h。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CusumConfig {
    /// Master enable flag. `false` (default, Phase A) keeps the monitor
    /// dormant — no PnL accumulation, no alarms, no `dynamic_risk_sizer`
    /// hook. Operators flip to `true` only after Phase B+ wires the
    /// runtime consumer.
    /// 主開關。Phase A 預設 false 完全靜默；Phase B+ runtime 接線後 operator 翻 true。
    #[serde(default = "default_cusum_enabled")]
    pub enabled: bool,
    /// Deadband in σ units (typical 0.5σ). Drifts smaller than `slack_k * σ`
    /// from `target_return_bps` do not accumulate, preventing false alarms
    /// on routine sub-σ noise.
    /// 死區（σ 倍數，典型 0.5σ）；小於 `slack_k * σ` 的偏移不累積避免雜訊誤警。
    #[serde(default = "default_cusum_slack_k")]
    pub slack_k: f64,
    /// Alarm threshold in σ units (typical 4-5σ). When the running CUSUM
    /// exceeds `threshold_h * σ`, the monitor flags an edge-decay alarm.
    /// 警報閾值（σ 倍數，典型 4-5σ）；累積值超過後觸發 edge-decay 警報。
    #[serde(default = "default_cusum_threshold_h")]
    pub threshold_h: f64,
    /// Minimum PnL observations required before evaluating the chart.
    /// Prevents spurious alarms on the first handful of trades when the σ
    /// estimate is still degenerate. Default 30 mirrors common quant-control
    /// guidance for daily-trade granularity.
    /// 評估前所需的最小 PnL 樣本數；預設 30 對齊日級交易控制圖經驗值。
    #[serde(default = "default_cusum_min_observations")]
    pub min_observations: u32,
    /// Reference return level (basis points). `x_t - target_return_bps` is the
    /// per-trade deviation accumulated by the chart. Default `0.0` = breakeven
    /// net of fees; operators may bump to per-strategy expected gross edge
    /// minus realized cost when wired in Phase B+.
    /// 參考收益水平（bps）；累積偏差 = `x_t - target_return_bps`。預設 0.0 = 扣費打平。
    #[serde(default = "default_cusum_target_return_bps")]
    pub target_return_bps: f64,
}

fn default_cusum_enabled() -> bool {
    // Phase A safe default: dormant. Flipping to `true` requires Phase B+
    // runtime wiring (consumer + alarm sink) — schema-only landing has
    // nothing to act on.
    // Phase A 安全預設：靜默；翻 true 需 Phase B+ runtime wiring 完成。
    false
}

fn default_cusum_slack_k() -> f64 {
    // 0.5σ — standard one-sided CUSUM deadband (Montgomery, Statistical
    // Quality Control). Catches sustained drifts > 0.5σ while ignoring
    // sub-σ noise.
    // 0.5σ — 標準單側 CUSUM 死區（Montgomery 統計品質管制慣例）。
    0.5
}

fn default_cusum_threshold_h() -> f64 {
    // 4.0σ — Page's H-decision boundary midpoint (4-5σ is the classic
    // alarm band; 4.0 trades a slightly tighter fence for fewer false
    // negatives at the cost of more false positives, which we offset
    // with the `min_observations = 30` warm-up).
    // 4.0σ — Page H-decision 經典中位（4-5σ 警報帶；min_observations=30 平衡假警報）。
    4.0
}

fn default_cusum_min_observations() -> u32 {
    // 30 — daily-trade granularity warm-up (≈ 1 trading month of samples)
    // before the σ estimate stabilises and the chart becomes evaluable.
    // 30 — 日級交易約 1 個月樣本，σ 估計穩定後才評估警報。
    30
}

fn default_cusum_target_return_bps() -> f64 {
    // 0.0 — breakeven net of fees. Operators tune this per-strategy in the
    // future runtime wiring follow-up to encode the strategy's expected
    // gross-minus-cost reference level.
    // 0.0 — 扣費打平；後續 wiring 跟進時 operator 按策略 gross-cost 調整。
    0.0
}

impl Default for CusumConfig {
    fn default() -> Self {
        Self {
            enabled: default_cusum_enabled(),
            slack_k: default_cusum_slack_k(),
            threshold_h: default_cusum_threshold_h(),
            min_observations: default_cusum_min_observations(),
            target_return_bps: default_cusum_target_return_bps(),
        }
    }
}

impl CusumConfig {
    /// G7-04: Validate that `0 < slack_k < threshold_h`, `threshold_h <= 100`,
    /// and `min_observations >= 5`. Fails fast at config-load time so an
    /// unreachable-alarm or degenerate-σ misconfiguration cannot leak into
    /// the (future) hot path.
    /// G7-04：驗證 0 < slack_k < threshold_h、threshold_h ≤ 100、min_observations ≥ 5。
    pub fn validate(&self) -> Result<(), String> {
        if !(self.slack_k > 0.0) {
            return Err(format!(
                "risk.cusum.slack_k ({}) must be > 0 (zero deadband collapses to instant alarm)",
                self.slack_k
            ));
        }
        if !(self.threshold_h > 0.0) {
            return Err(format!(
                "risk.cusum.threshold_h ({}) must be > 0",
                self.threshold_h
            ));
        }
        if self.threshold_h > 100.0 {
            return Err(format!(
                "risk.cusum.threshold_h ({}) must be <= 100 (sanity ceiling; beyond ~10σ the chart never alarms)",
                self.threshold_h
            ));
        }
        if !(self.slack_k < self.threshold_h) {
            return Err(format!(
                "risk.cusum.slack_k ({}) must be < threshold_h ({}) — otherwise σ-scaled threshold sits inside the deadband and no alarm is reachable",
                self.slack_k, self.threshold_h
            ));
        }
        if self.min_observations < 5 {
            return Err(format!(
                "risk.cusum.min_observations ({}) must be >= 5 (smaller warm-up makes σ estimate degenerate)",
                self.min_observations
            ));
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// GridOuConfig — Grid OU residual-based sigma estimator schema (G7-06 Phase A)
// Grid OU 殘差 σ 估計器 schema（G7-06 Phase A）
// ---------------------------------------------------------------------------

/// G7-06 (2026-04-24): Schema for the residual-based σ estimator used by Grid
/// Trading's OU optimal-spacing math. `compute_ou_step`'s current path uses raw
/// `σ = sqrt(Σ Δx²/n)` which conflates drift with innovation; the residual
/// estimator returns `σ̂ = sqrt(Σ ε²/(n-1))` after subtracting `θ̂(μ̂ − x_{t-1})`.
/// Phase A: schema + TOML + validate only; default `use_residual_sigma = false`
/// keeps runtime bit-identical. Phase B wires `grid_helpers::compute_ou_step`.
/// `validate()` enforces `residual_window_size ∈ [20, 5_000]` and
/// `fallback_sigma ∈ [0.0, 1.0]`.
///
/// G7-06：Grid OU 殘差 σ 估計器 schema；Phase A 預設 false 保留現行為。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GridOuConfig {
    /// Master enable flag. Phase A default `false` keeps `compute_ou_step` on
    /// the raw-Δx σ path. Operators flip after Phase B wires the call site.
    /// 主開關；Phase A=false 靜默，Phase B 接 wire 後翻 true。
    #[serde(default = "default_grid_ou_use_residual_sigma")]
    pub use_residual_sigma: bool,
    /// Rolling window length for the residual σ estimator. Default `200`
    /// matches typical Grid `ou_lookback`.
    /// 殘差 σ 滾動窗口長度，預設 200 對齊 Grid ou_lookback。
    #[serde(default = "default_grid_ou_residual_window_size")]
    pub residual_window_size: u32,
    /// Fallback σ (fraction of price) when the estimator degenerates. Default
    /// `0.001` (10 bps) is a conservative crypto-1m placeholder.
    /// 退化時的 fallback σ（價格百分比），預設 0.001（10 bps）。
    #[serde(default = "default_grid_ou_fallback_sigma")]
    pub fallback_sigma: f64,
}

fn default_grid_ou_use_residual_sigma() -> bool {
    false
}
fn default_grid_ou_residual_window_size() -> u32 {
    200
}
fn default_grid_ou_fallback_sigma() -> f64 {
    0.001
}

impl Default for GridOuConfig {
    fn default() -> Self {
        Self {
            use_residual_sigma: default_grid_ou_use_residual_sigma(),
            residual_window_size: default_grid_ou_residual_window_size(),
            fallback_sigma: default_grid_ou_fallback_sigma(),
        }
    }
}

impl GridOuConfig {
    /// G7-06: validate `residual_window_size ∈ [20, 5_000]` and
    /// `fallback_sigma ∈ [0.0, 1.0]`.
    /// G7-06：驗證 residual_window_size ∈ [20, 5_000]、fallback_sigma ∈ [0, 1]。
    pub fn validate(&self) -> Result<(), String> {
        if self.residual_window_size < 20 {
            return Err(format!(
                "risk.grid_ou.residual_window_size ({}) must be >= 20",
                self.residual_window_size
            ));
        }
        if self.residual_window_size > 5_000 {
            return Err(format!(
                "risk.grid_ou.residual_window_size ({}) must be <= 5_000",
                self.residual_window_size
            ));
        }
        if !(self.fallback_sigma >= 0.0) {
            return Err(format!(
                "risk.grid_ou.fallback_sigma ({}) must be >= 0.0",
                self.fallback_sigma
            ));
        }
        if self.fallback_sigma > 1.0 {
            return Err(format!(
                "risk.grid_ou.fallback_sigma ({}) must be <= 1.0",
                self.fallback_sigma
            ));
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// StrategistConfig — Strategist param-tuner delta clamp (STRATEGIST-TUNE-TARGET-CONFIG-1)
// 策略師調參 delta 上限（STRATEGIST-TUNE-TARGET-CONFIG-1）
// ---------------------------------------------------------------------------

/// STRATEGIST-TUNE-TARGET-CONFIG-1 (2026-04-25): Operator-tunable max delta clamp
/// for the Rust StrategistScheduler param tuner.
///
/// `validate_recommendation` (in `strategist_scheduler::mod`) rejects any
/// per-cycle parameter change whose `|new − cur| / |cur|` exceeds
/// `max_param_delta_pct`. The pre-config hardcoded constant lived in
/// `strategist_scheduler/mod.rs` as `MAX_PARAM_DELTA_PCT: f64 = 0.30`,
/// requiring a Rust rebuild to retune. This struct lifts it into
/// `RiskConfig.strategist` so operators flip via `<60s` IPC hot-reload through
/// the existing `Arc<ArcSwap<RiskConfig>>` deep-merge path
/// (`patch_risk_config`), matching G7-04 / G7-02 / G3-02 Phase-A patterns.
///
/// The default `0.30` (±30%) preserves the pre-extraction runtime exactly, so
/// this landing has zero behavioural change until operators tune the TOML or
/// patch IPC.
///
/// `validate()` rejects:
/// - `≤ 0.0` (no headroom for tuning at all — clamp instantly rejects)
/// - `≥ 1.0` (`100%` delta is wholesale replacement of the param, defeating
///   the purpose of a sanity gate)
/// - NaN / +∞ / −∞ (silent NaN comparisons would always reject — fail fast)
///
/// Per-param overrides (e.g. allow `weight_*` to flex 0.50 while
/// `cooldown_ms` stays at 0.30) are deferred to a v2 follow-up to keep this
/// landing scope-tight.
///
/// STRATEGIST-TUNE-TARGET-CONFIG-1：策略師調參 delta 硬上限可配置化。
/// 預設 0.30（±30%）保留現行為，operator 可透過 IPC `patch_risk_config`
/// `<60s` 熱重載；per-param 覆蓋（v2）本次延後不做。
/// validate() 拒 ≤0.0 / ≥1.0 / NaN / Inf 以早期失敗。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StrategistConfig {
    /// Maximum allowed delta for per-cycle parameter updates, expressed as a
    /// fraction of the current value (`0.30` = ±30%).
    ///
    /// Weight-family params (`weight_adx` / `weight_regime` / `weight_volume`
    /// / `weight_momentum`) are exempt from this clamp inside
    /// `validate_recommendation` (the `weight_sum == 65 ± 0.1` invariant is
    /// the relevant constraint there), so this knob only governs non-weight
    /// scalar params (`cooldown_ms`, `adx_threshold`, etc.).
    /// 每輪參數更新允許的最大 delta（current 值的比例，0.30=±30%）；
    /// weight 系參數另循 weight_sum=65 約束，不受此限。
    #[serde(default = "default_strategist_max_param_delta_pct")]
    pub max_param_delta_pct: f64,
}

fn default_strategist_max_param_delta_pct() -> f64 {
    // 0.30 — preserves the pre-config hardcoded `MAX_PARAM_DELTA_PCT` in
    // `strategist_scheduler/mod.rs:48` bit-for-bit, so the schema landing
    // ships with zero runtime delta.
    // 0.30 — 與 strategist_scheduler/mod.rs:48 原硬編碼值對齊，schema
    // 落地零行為差。
    0.30
}

impl Default for StrategistConfig {
    fn default() -> Self {
        Self {
            max_param_delta_pct: default_strategist_max_param_delta_pct(),
        }
    }
}

impl StrategistConfig {
    /// STRATEGIST-TUNE-TARGET-CONFIG-1: Validate `max_param_delta_pct ∈ (0.0, 1.0)`
    /// and finite. Fails fast at config-load time so a degenerate clamp can
    /// never reach the hot path.
    /// STRATEGIST-TUNE-TARGET-CONFIG-1：驗證 max_param_delta_pct ∈ (0.0, 1.0) 且有限。
    pub fn validate(&self) -> Result<(), String> {
        let v = self.max_param_delta_pct;
        if !v.is_finite() {
            return Err(format!(
                "risk.strategist.max_param_delta_pct ({}) must be finite (no NaN/Inf)",
                v
            ));
        }
        if !(v > 0.0) {
            return Err(format!(
                "risk.strategist.max_param_delta_pct ({}) must be > 0.0 \
                 (zero or negative clamp rejects every recommendation)",
                v
            ));
        }
        if !(v < 1.0) {
            return Err(format!(
                "risk.strategist.max_param_delta_pct ({}) must be < 1.0 \
                 (>= 100% is wholesale replacement; defeats the sanity gate)",
                v
            ));
        }
        Ok(())
    }
}
