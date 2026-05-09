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

#[path = "risk_config_slippage.rs"]
mod slippage;
pub use slippage::{SlippageConfig, SlippageTier};

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
// SlippageConfig lives in risk_config_slippage.rs and is re-exported above.
// SlippageConfig 已拆至 risk_config_slippage.rs，並於上方 re-export。
// ---------------------------------------------------------------------------

// ===========================================================================
// G3-02 / G7-02 / G7-04 Phase A schema sub-structs (relocated from
// risk_config.rs 2026-04-25 to bring main file back under §九 1200-line cap).
// Behaviour bit-identical — only the file boundary moved.
// 從 risk_config.rs 搬遷至此（2026-04-25）以滿足 §九 1200 行硬上限。
// ===========================================================================

// ---------------------------------------------------------------------------
// ExecutorConfig — ExecutorAgent shadow→live control plane (G3-02 Phase A
// + W-AUDIT-9 graduated canary upgrade per AMD-2026-05-09-03)
// ExecutorAgent shadow→live 控制平面（G3-02 Phase A + W-AUDIT-9 5-stage 升級）
// ---------------------------------------------------------------------------

/// G3-02 Phase A (2026-04-25) + W-AUDIT-9 (AMD-2026-05-09-03, 2026-05-09)：
/// ExecutorAgent canonical 控制平面 + graduated canary 5-stage 升級。
///
/// 演進歷史：
/// - G3-02 Phase A：把 Python `_shadow_mode = True` 硬編碼提升為 Rust ConfigStore
///   一級欄位（per RFC `2026-04-24--g3_01_executor_agent_ipc_rfc.md`）。
/// - AMD-2026-05-09-03：把 binary `shadow_mode: bool` 升級為 5-stage graduated
///   canary（Stage 0 / Stage 1 paper / Stage 2 demo / Stage 3 demo full /
///   Stage 4 live pending）。`shadow_mode` 保留為 backward-compat projection：
///   Stage 0 ⇄ shadow_mode=true，Stage 1+ ⇄ shadow_mode=false。
///   權威 SoT 為 `canary_stage` + `canary_cohort` + `stage_entered_at_ms` +
///   `observation_period_ms`。詳見：
///   `docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md`
///
/// 預設姿態（per AMD §2.3）：
/// - paper TOML 預設 Stage 1（cohort 待 operator 顯式選擇前不啟用）
/// - demo TOML 預設 Stage 1（W-AUDIT-9 IMPL land 後 cohort 待 operator 拍板）
/// - live TOML 預設 Stage 0（live 不適用 graduated canary，仍 binary fail-closed）
///
/// 不適用範圍（per AMD §3）：DOC-08 §12 9 條安全不變量 / SM-04 ≥ L3 / Live
/// boundary 5-gate / §二 16 原則硬不變式 — 仍強制 binary fail-closed。
///
/// Phase B/C 預定（W-AUDIT-9 T3-T7）：shadow_mode_provider stage-aware（執行
/// cohort match + observation_period 計算 + auto-promote/rollback eval）+ healthcheck
/// `[58]` + GUI surface + Decision Lease `LeaseScope::CanaryStagePromotion`。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutorConfig {
    /// Legacy backward-compat 旗標。
    /// - Stage 0 ⇄ `shadow_mode = true`（log intents，不下單）
    /// - Stage 1..=4 ⇄ `shadow_mode = false`（cohort 內真實下單，cohort 外 shadow）
    ///
    /// AMD-2026-05-09-03 §4.4：權威 SoT 改為 `canary_stage`，但保留此欄位給未升級
    /// 的下游讀路徑。`validate()` 強制 `shadow_mode == (canary_stage == 0)` 一致性
    /// — 任何不一致 = legacy config drift，fail-closed reject。
    /// 影子模式 legacy 旗標。true=log 但不下單；false=真實下單（需 live-gate 全綠）。
    /// AMD-2026-05-09-03：權威來源已改 canary_stage，此欄位保留 backward-compat。
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

    // ────────────────────────────────────────────────────────────────────
    // W-AUDIT-9 (AMD-2026-05-09-03) graduated canary 5-stage 升級
    // ────────────────────────────────────────────────────────────────────
    /// AMD-2026-05-09-03：Graduated canary 階段（0..=4）。
    /// - Stage 0：shadow only（不送 intent 到 Rust submit path），永久態
    /// - Stage 1：1 strategy × 1 symbol × paper × 7d 觀察期
    /// - Stage 2：1 strategy × 1 symbol × demo × 14d 觀察期
    /// - Stage 3：5 active strategies × demo full universe × 21d
    /// - Stage 4：LIVE_PENDING — operator 拍板 + 全 5-gate live boundary 滿足
    ///
    /// 默認 0（fail-closed shadow）。TOML 升 Stage 必同時設 `canary_cohort` +
    /// `stage_entered_at_ms` + `observation_period_ms`，否則 validate() reject。
    /// AMD-2026-05-09-03：5-stage canary 階段；Stage 0 = shadow，1..=3 cohort
    /// 觀察，4 = live pending；升 Stage 必設 cohort 等三欄位，否則 reject。
    #[serde(default = "default_executor_canary_stage")]
    pub canary_stage: CanaryStage,

    /// AMD-2026-05-09-03：Stage 1/2 cohort 範圍（1 strategy × 1 symbol × env）。
    /// Stage 3/4 cohort 為全 universe（None）。Stage 0 cohort = None（shadow only）。
    /// AMD-2026-05-09-03：cohort 範圍；Stage 1/2 必填 1×1×env，Stage 0/3/4=None。
    #[serde(default)]
    pub canary_cohort: Option<CanaryCohort>,

    /// AMD-2026-05-09-03：當前 stage 進入時間（ms epoch）。
    /// Stage 0 默認 0（永久態，無觀察期）。Stage 1+ 必為正值。
    /// healthcheck `[58]` 與此欄位一致性比對 `governance.canary_stage_log` 最新 row。
    /// AMD-2026-05-09-03：當前 stage 進入時間 ms epoch；Stage 0=0，Stage 1+ 必正。
    #[serde(default)]
    pub stage_entered_at_ms: i64,

    /// AMD-2026-05-09-03：當前 stage 觀察期長度（ms）。
    /// 預設 0（Stage 0 不觀察）。Stage 1=7d / Stage 2=14d / Stage 3=21d / Stage 4=不適用。
    /// shadow_mode_provider stage-aware（W-AUDIT-9 T3）用此計算自動升級條件 eval timing。
    /// AMD-2026-05-09-03：當前 stage 觀察期長度 ms；Stage 1=7d/2=14d/3=21d。
    #[serde(default)]
    pub observation_period_ms: u64,
}

/// AMD-2026-05-09-03 §2.2：5-stage graduated canary 階段列舉。
/// 序列化為 0..=4 整數（serde transparent style）保 TOML 簡潔 + 跨 IPC schema 不變。
/// AMD-2026-05-09-03：5-stage 階段；TOML 序列化為 0..=4 整數。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(try_from = "u8", into = "u8")]
pub enum CanaryStage {
    /// Stage 0：shadow only（fail-closed default，binary 等價）
    Stage0,
    /// Stage 1：1 strategy × 1 symbol × paper × 7d 觀察期
    Stage1,
    /// Stage 2：1 strategy × 1 symbol × demo × 14d 觀察期
    Stage2,
    /// Stage 3：5 active strategies × demo full universe × 21d 觀察期
    Stage3,
    /// Stage 4：LIVE_PENDING — operator 拍板 + 全 live boundary
    Stage4,
}

impl CanaryStage {
    /// 把 stage 投影為 legacy `shadow_mode: bool`。
    /// Stage 0 ⇄ true（shadow），Stage 1+ ⇄ false（live cohort/全 universe）。
    /// AMD-2026-05-09-03 §4.4：保留給未升級的下游讀路徑。
    /// AMD-2026-05-09-03：投影為 legacy shadow_mode bool。
    pub fn as_shadow_mode(self) -> bool {
        matches!(self, CanaryStage::Stage0)
    }

    /// 把 stage 編碼為 0..=4 整數。
    /// AMD-2026-05-09-03：stage 整數編碼。
    pub fn as_u8(self) -> u8 {
        match self {
            CanaryStage::Stage0 => 0,
            CanaryStage::Stage1 => 1,
            CanaryStage::Stage2 => 2,
            CanaryStage::Stage3 => 3,
            CanaryStage::Stage4 => 4,
        }
    }
}

impl Default for CanaryStage {
    /// 預設 Stage 0（fail-closed shadow），與 W-AUDIT-9 land 前 `shadow_mode=true` 等價。
    /// AMD-2026-05-09-03：預設 Stage 0 fail-closed。
    fn default() -> Self {
        CanaryStage::Stage0
    }
}

impl From<CanaryStage> for u8 {
    fn from(s: CanaryStage) -> u8 {
        s.as_u8()
    }
}

impl TryFrom<u8> for CanaryStage {
    type Error = String;
    fn try_from(v: u8) -> Result<Self, Self::Error> {
        match v {
            0 => Ok(CanaryStage::Stage0),
            1 => Ok(CanaryStage::Stage1),
            2 => Ok(CanaryStage::Stage2),
            3 => Ok(CanaryStage::Stage3),
            4 => Ok(CanaryStage::Stage4),
            other => Err(format!(
                "risk.executor.canary_stage invalid: {} (must be 0..=4)",
                other
            )),
        }
    }
}

/// AMD-2026-05-09-03 §2.1：cohort 範圍 — 哪 1 strategy × 1 symbol × environment
/// 在當前 stage 真實送 intent；cohort 外仍 fail-closed shadow。
/// AMD-2026-05-09-03：cohort 範圍 1 strategy × 1 symbol × env。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CanaryCohort {
    /// 策略名（必須屬於 active strategy set；funding_arb 已退役不可選）。
    /// AMD-2026-05-09-03：策略名；不可為 active set 之外。
    pub strategy: String,
    /// Symbol（必須屬於當前 active universe）。
    /// AMD-2026-05-09-03：symbol；必須屬於 active universe。
    pub symbol: String,
    /// 環境字串：'paper' | 'demo' | 'live_demo' | 'mainnet'。
    /// W-AUDIT-9 T3 stage-aware provider 用此匹配 cohort scope。
    /// AMD-2026-05-09-03：環境字串 paper/demo/live_demo/mainnet。
    pub environment: String,
}

fn default_executor_shadow_mode() -> bool {
    // Phase A safe default：保留 Python ExecutorAgent 強制 shadow 行為。
    // AMD-2026-05-09-03：與 Stage 0 default 一致（投影 true）。
    true
}

fn default_executor_max_position_pct() -> f64 {
    // 5% — 與 P0/P1 cascade 默認保守起點一致。
    0.05
}

fn default_executor_canary_stage() -> CanaryStage {
    // AMD-2026-05-09-03：預設 Stage 0（fail-closed shadow）。
    // demo/paper TOML 顯式設 Stage 1 才會啟用 cohort 觀察。
    CanaryStage::Stage0
}

impl Default for ExecutorConfig {
    fn default() -> Self {
        Self {
            shadow_mode: default_executor_shadow_mode(),
            max_position_pct: default_executor_max_position_pct(),
            per_symbol_position_cap: HashMap::new(),
            canary_stage: default_executor_canary_stage(),
            canary_cohort: None,
            stage_entered_at_ms: 0,
            observation_period_ms: 0,
        }
    }
}

impl ExecutorConfig {
    /// G3-02 Phase A + AMD-2026-05-09-03：驗證比例範圍 + canary stage 一致性。
    ///
    /// E2 重點審查（per AMD-2026-05-09-03 §7）：
    /// 1. `shadow_mode legacy false` + `canary_stage=0` = reject（雞蛋死循環復活防線）
    /// 2. `canary_stage >= 1` 必伴隨 cohort + stage_entered_at_ms 等
    /// 3. Stage 1/2 必為 1 strategy × 1 symbol cohort
    ///
    /// G3-02 + AMD-2026-05-09-03：驗證比例範圍 + 5-stage 不變量。
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

        // ────────────────────────────────────────────────────────────────
        // AMD-2026-05-09-03 §4.4：shadow_mode ⇄ canary_stage 一致性不變量
        // ────────────────────────────────────────────────────────────────
        // 任何 legacy `shadow_mode=false` 配 `canary_stage=Stage 0` 的組合 = config
        // drift（升級不完全），fail-closed reject。同樣 `shadow_mode=true` 配
        // `canary_stage>=1` 也是 drift，reject。
        // PA E2 audit point #1：break 即 W-A 復活雞蛋死循環。
        // AMD-2026-05-09-03：legacy shadow_mode 必與 canary_stage projection 對齊。
        let projected_shadow = self.canary_stage.as_shadow_mode();
        if self.shadow_mode != projected_shadow {
            return Err(format!(
                "risk.executor: shadow_mode={} inconsistent with canary_stage={} \
                 (Stage 0 ⇄ true, Stage 1+ ⇄ false). \
                 AMD-2026-05-09-03 §4.4 requires legacy shadow_mode equals \
                 canary_stage.as_shadow_mode() projection. Update either field \
                 atomically (TOML/IPC patch must set both).",
                self.shadow_mode,
                self.canary_stage.as_u8()
            ));
        }

        // AMD-2026-05-09-03 §2.2：Stage 1/2 cohort 必為 1 strategy × 1 symbol。
        // Stage 0/3/4 cohort = None（Stage 0 shadow / Stage 3/4 全 universe）。
        // AMD-2026-05-09-03：Stage 1/2 必有 1×1 cohort，其他 stage cohort=None。
        match self.canary_stage {
            CanaryStage::Stage0 => {
                if self.canary_cohort.is_some() {
                    return Err(
                        "risk.executor.canary_stage=0 (shadow) must have canary_cohort=None \
                         (Stage 0 is global shadow, not cohort-scoped)"
                            .into(),
                    );
                }
                if self.stage_entered_at_ms != 0 {
                    return Err(format!(
                        "risk.executor.canary_stage=0 must have stage_entered_at_ms=0 \
                         (got {}); Stage 0 is permanent default with no observation period.",
                        self.stage_entered_at_ms
                    ));
                }
                if self.observation_period_ms != 0 {
                    return Err(format!(
                        "risk.executor.canary_stage=0 must have observation_period_ms=0 \
                         (got {}); Stage 0 has no observation period.",
                        self.observation_period_ms
                    ));
                }
            }
            CanaryStage::Stage1 | CanaryStage::Stage2 => {
                let cohort = self.canary_cohort.as_ref().ok_or_else(|| {
                    format!(
                        "risk.executor.canary_stage={} requires canary_cohort \
                         (1 strategy × 1 symbol × environment) per AMD-2026-05-09-03 §2.2",
                        self.canary_stage.as_u8()
                    )
                })?;
                if cohort.strategy.is_empty() {
                    return Err(
                        "risk.executor.canary_cohort.strategy must be non-empty for Stage 1/2"
                            .into(),
                    );
                }
                if cohort.symbol.is_empty() {
                    return Err(
                        "risk.executor.canary_cohort.symbol must be non-empty for Stage 1/2"
                            .into(),
                    );
                }
                match cohort.environment.as_str() {
                    "paper" | "demo" | "live_demo" | "mainnet" => {}
                    other => {
                        return Err(format!(
                            "risk.executor.canary_cohort.environment invalid: '{}' \
                             (must be one of paper/demo/live_demo/mainnet)",
                            other
                        ));
                    }
                }
                // Stage 1 必為 paper；Stage 2 必為 demo（per AMD §2.2 表格）。
                // Stage 1 = paper / Stage 2 = demo per AMD §2.2 表格。
                let expected_env = match self.canary_stage {
                    CanaryStage::Stage1 => "paper",
                    CanaryStage::Stage2 => "demo",
                    _ => unreachable!(),
                };
                if cohort.environment != expected_env {
                    return Err(format!(
                        "risk.executor.canary_stage={} requires environment='{}' \
                         (got '{}') per AMD-2026-05-09-03 §2.2 stage table",
                        self.canary_stage.as_u8(),
                        expected_env,
                        cohort.environment
                    ));
                }
                if self.stage_entered_at_ms <= 0 {
                    return Err(format!(
                        "risk.executor.canary_stage={} requires stage_entered_at_ms > 0 \
                         (got {}); set on stage transition.",
                        self.canary_stage.as_u8(),
                        self.stage_entered_at_ms
                    ));
                }
                if self.observation_period_ms == 0 {
                    return Err(format!(
                        "risk.executor.canary_stage={} requires observation_period_ms > 0 \
                         (Stage 1=7d=604800000ms, Stage 2=14d=1209600000ms)",
                        self.canary_stage.as_u8()
                    ));
                }
            }
            CanaryStage::Stage3 => {
                // Stage 3 = demo full universe，cohort=None
                // Stage 3：demo 全 universe，cohort=None。
                if self.canary_cohort.is_some() {
                    return Err(
                        "risk.executor.canary_stage=3 (demo full universe) must have \
                         canary_cohort=None (cohort scope = all 5 active strategies × demo)"
                            .into(),
                    );
                }
                if self.stage_entered_at_ms <= 0 {
                    return Err(
                        "risk.executor.canary_stage=3 requires stage_entered_at_ms > 0".into(),
                    );
                }
                if self.observation_period_ms == 0 {
                    return Err(
                        "risk.executor.canary_stage=3 requires observation_period_ms > 0 \
                         (Stage 3=21d=1814400000ms)"
                            .into(),
                    );
                }
            }
            CanaryStage::Stage4 => {
                // Stage 4 = LIVE_PENDING，operator 顯式拍板，無觀察期
                // Stage 4：LIVE_PENDING，operator 拍板，無觀察期。
                if self.canary_cohort.is_some() {
                    return Err(
                        "risk.executor.canary_stage=4 (LIVE_PENDING) must have \
                         canary_cohort=None (live runs full active strategy set, \
                         per AMD-2026-05-09-03 §2.2)"
                            .into(),
                    );
                }
                if self.stage_entered_at_ms <= 0 {
                    return Err(
                        "risk.executor.canary_stage=4 requires stage_entered_at_ms > 0".into(),
                    );
                }
                // Stage 4 observation_period 不適用（operator 拍板，no auto upgrade）
                // Stage 4：observation_period 不適用 — operator 拍板模式。
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
/// `max_param_delta_pct`. The pre-config hardcoded constant originally lived in
/// `strategist_scheduler/mod.rs`, requiring a Rust rebuild to retune. This
/// struct lifts it into
/// `RiskConfig.strategist` so operators flip via `<60s` IPC hot-reload through
/// the existing `Arc<ArcSwap<RiskConfig>>` deep-merge path
/// (`patch_risk_config`), matching G7-04 / G7-02 / G3-02 Phase-A patterns.
///
/// W-AUDIT-7 F-strategist-cap sets the current default to `0.50` (±50%) so
/// source defaults, TOML examples, and the scheduler's no-store fallback stay
/// aligned.
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
/// W-AUDIT-7 source 預設 0.50（±50%），operator 可透過 IPC `patch_risk_config`
/// `<60s` 熱重載；per-param 覆蓋（v2）延後。
/// validate() 拒 ≤0.0 / ≥1.0 / NaN / Inf 以早期失敗。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StrategistConfig {
    /// Maximum allowed delta for per-cycle parameter updates, expressed as a
    /// fraction of the current value (`0.50` = ±50%).
    ///
    /// Weight-family params (`weight_adx` / `weight_regime` / `weight_volume`
    /// / `weight_momentum`) are exempt from this clamp inside
    /// `validate_recommendation` (the `weight_sum == 65 ± 0.1` invariant is
    /// the relevant constraint there), so this knob only governs non-weight
    /// scalar params (`cooldown_ms`, `adx_threshold`, etc.).
    /// 每輪參數更新允許的最大 delta（current 值的比例，0.50=±50%）；
    /// weight 系參數另循 weight_sum=65 約束，不受此限。
    #[serde(default = "default_strategist_max_param_delta_pct")]
    pub max_param_delta_pct: f64,
}

fn default_strategist_max_param_delta_pct() -> f64 {
    // W-AUDIT-7 F-strategist-cap: source default aligned with
    // risk_config_{paper,demo,live}.toml and the scheduler no-store fallback.
    // W-AUDIT-7：source 預設與三份 risk_config 及 scheduler fallback 對齊。
    0.50
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
