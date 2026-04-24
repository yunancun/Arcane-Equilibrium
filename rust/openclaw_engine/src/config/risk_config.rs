//! RiskConfig — Authoritative risk control configuration (ARCH-RC1).
//! RiskConfig — 風控權威配置。
//!
//! MODULE_NOTE (EN): One of the three hot-reload Configs in ARCH-RC1, and the
//!   single source of truth for ALL risk decisions: P0 category overrides,
//!   P1 operator hard ceilings, P2 agent self-tunable params, 6-level RiskGovernor
//!   cascade thresholds, regime multipliers, cost gate, dynamic stop, market
//!   gate (microstructure), anti-cluster, correlation, and runtime knobs.
//!   `partial_tp_*` lives in agent (P2) here, NOT in LearningConfig — coupled
//!   to take_profit_max_pct so they share the same Config validate path.
//!   Tick path reads via `Arc<ArcSwap<RiskConfig>>` for ~5ns lock-free snapshot.
//! MODULE_NOTE (中): ARCH-RC1 三個熱重載 Config 之一，所有風控決策的單一真相來源：
//!   P0 品類覆蓋、P1 操作員硬上限、P2 Agent 自我調整、6 級 RiskGovernor cascade
//!   閾值、regime 乘數、cost gate、動態 stop、market gate（微結構）、anti-cluster、
//!   correlation、runtime knobs。`partial_tp_*` 在這裡的 agent (P2)，不在
//!   LearningConfig —— 與 take_profit_max_pct 耦合所以同 Config validate。
//!   Tick 路徑透過 `Arc<ArcSwap<RiskConfig>>` 無鎖快照（~5ns）。

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use crate::exit_features::ExitConfig;

// G1-03 Wave 1 Rust refactor (2026-04-24): advanced sub-configs extracted to
// risk_config_advanced.rs sibling to bring this file under §九 1200-line limit.
// G1-03 Wave 1 Rust refactor（2026-04-24）：進階子配置抽至 sibling。
#[path = "risk_config_advanced.rs"]
mod advanced;
pub use advanced::{
    AntiCluster, Correlation, DynamicStop, EdgePredictor, EdgePredictorFallback, Experimental,
    MarketGate, RuntimeKnobs,
};

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

/// Complete risk configuration (ARCH-RC1).
/// 完整風控配置。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct RiskConfig {
    #[serde(default)]
    pub meta: Meta,
    #[serde(default)]
    pub limits: GlobalLimits,
    #[serde(default)]
    pub overrides: CategoryOverrides,
    #[serde(default)]
    pub per_strategy: HashMap<String, StrategyOverride>,
    #[serde(default)]
    pub agent: AgentParams,
    #[serde(default)]
    pub cascade: CascadeThresholds,
    #[serde(default)]
    pub regime: RegimeMultipliers,
    #[serde(default)]
    pub cost_gate: CostGate,
    #[serde(default)]
    pub edge_predictor: EdgePredictor,
    #[serde(default)]
    pub dynamic_stop: DynamicStop,
    #[serde(default)]
    pub market_gate: MarketGate,
    #[serde(default)]
    pub anti_cluster: AntiCluster,
    #[serde(default)]
    pub correlation: Correlation,
    #[serde(default)]
    pub runtime: RuntimeKnobs,
    /// DUAL-TRACK-EXIT-1 Track P: Physical-layer exit config (non-linear
    /// giveback v2). Drives Priority 6 `physical_micro_profit_lock_v2` in
    /// `risk_checks::check_position_on_tick`. Hot-reloaded via
    /// `Arc<ArcSwap<RiskConfig>>`.
    ///
    /// TRACK-P-V2-SWAP-1 (2026-04-22): replaced linear `PhysLockConfig` with
    /// `ExitConfig` defined in `exit_features::v2`. See that module for the
    /// non-linear giveback threshold (`base - slope × peak_atr_norm`, bounded
    /// below by `floor`) which replaces the former single fixed threshold.
    ///
    /// DUAL-TRACK-EXIT-1 Track P：物理層退出參數（v2 非線性 giveback）。
    /// 驅動 `risk_checks::check_position_on_tick` 的 Priority 6
    /// `physical_micro_profit_lock_v2`，透過 `Arc<ArcSwap<RiskConfig>>` 熱重載。
    /// TRACK-P-V2-SWAP-1（2026-04-22）：線性 `PhysLockConfig` 換為
    /// `exit_features::v2::ExitConfig`，threshold 由固定值改非線性。
    #[serde(default, alias = "phys_lock")]
    pub exit: ExitConfig,
    #[serde(default)]
    pub experimental: Experimental,
    /// DYNAMIC-RISK-1: Sharpe-aware dynamic `per_trade_risk_pct` sizer.
    /// Hot-reloadable; disabled by default. See `dynamic_risk_sizer.rs`.
    /// DYNAMIC-RISK-1：Sharpe 動態 `per_trade_risk_pct` 調整器，可熱重載，預設停用。
    #[serde(default)]
    pub dynamic_sizing: crate::dynamic_risk_sizer::DynamicRiskSizerConfig,
}

impl RiskConfig {
    /// Validate cross-field invariants. Cross-Config dependencies are checked
    /// elsewhere (DirectiveApplier etc.).
    /// 驗證跨欄位不變量。跨 Config 依賴在別處檢查（DirectiveApplier 等）。
    pub fn validate(&self) -> Result<(), String> {
        self.limits.validate()?;
        self.agent.validate()?;
        self.cascade.validate()?;
        self.regime.validate()?;
        self.cost_gate.validate()?;
        self.edge_predictor.validate()?;
        self.dynamic_stop.validate()?;
        self.market_gate.validate()?;
        self.anti_cluster.validate()?;
        self.correlation.validate()?;
        self.runtime.validate()?;
        self.exit.validate().map_err(|e| format!("risk.exit: {}", e))?;
        self.dynamic_sizing.validate()?;

        // Cross-sub-struct invariant: partial_tp levels must not exceed take_profit_max_pct.
        // 跨 sub-struct 不變量：partial_tp 各層不得超過 take_profit_max_pct。
        if self.agent.partial_tp_enabled {
            for (i, (pct, frac)) in self.agent.partial_tp_levels.iter().enumerate() {
                if *pct > self.limits.take_profit_max_pct {
                    return Err(format!(
                        "risk.agent.partial_tp_levels[{}] pct {} exceeds risk.limits.take_profit_max_pct {}",
                        i, pct, self.limits.take_profit_max_pct
                    ));
                }
                if !(0.0..=1.0).contains(frac) {
                    return Err(format!(
                        "risk.agent.partial_tp_levels[{}] fraction {} must be in [0, 1]",
                        i, frac
                    ));
                }
            }
        }

        // Cross-sub-struct: min_order_notional must allow at least one position.
        // 跨 sub-struct：min_order_notional 必須允許至少一個倉位存在。
        if self.limits.min_order_notional_usdt > self.limits.max_order_notional_usdt
            && self.limits.max_order_notional_usdt > 0.0
        {
            return Err(
                "risk.limits.min_order_notional_usdt must not exceed max_order_notional_usdt"
                    .into(),
            );
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// GlobalLimits (P1) / 全局上限
// ---------------------------------------------------------------------------

/// Operator-set hard ceilings (P1). All percentages are in absolute points (5.0 = 5%).
/// 操作員設定的硬上限（P1）。所有百分比為絕對值（5.0 = 5%）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GlobalLimits {
    #[serde(default = "default_stop_loss_max_pct")]
    pub stop_loss_max_pct: f64,
    #[serde(default = "default_take_profit_max_pct")]
    pub take_profit_max_pct: f64,
    /// Whether take-profit is forced at limits.take_profit_max_pct (vs trailing only).
    /// 是否在 take_profit_max_pct 處強制止盈（vs 僅追蹤）。
    #[serde(default)]
    pub take_profit_enforced: bool,
    #[serde(default = "default_position_size_max_pct")]
    pub position_size_max_pct: f64,
    #[serde(default = "default_total_exposure_max_pct")]
    pub total_exposure_max_pct: f64,
    #[serde(default = "default_correlated_exposure_max_pct")]
    pub correlated_exposure_max_pct: f64,
    #[serde(default = "default_leverage_max")]
    pub leverage_max: f64,
    #[serde(default = "default_session_drawdown_max_pct")]
    pub session_drawdown_max_pct: f64,
    #[serde(default = "default_daily_loss_max_pct")]
    pub daily_loss_max_pct: f64,
    #[serde(default = "default_consec_loss_cooldown_count")]
    pub consec_loss_cooldown_count: u32,
    #[serde(default = "default_consec_loss_cooldown_min")]
    pub consec_loss_cooldown_min: u32,
    #[serde(default = "default_holding_hours_max")]
    pub holding_hours_max: f64,
    #[serde(default = "default_open_positions_max")]
    pub open_positions_max: u32,
    /// Smallest notional a single order may have (USDT). 0 = no floor.
    /// 單筆訂單最小名目（USDT）。0 = 無下限。
    #[serde(default)]
    pub min_order_notional_usdt: f64,
    /// Largest notional a single order may have (USDT). 0 = no ceiling.
    /// 單筆訂單最大名目（USDT）。0 = 無上限。
    #[serde(default)]
    pub max_order_notional_usdt: f64,
    /// Account balance below which all new entries are blocked.
    /// 賬戶餘額低於此值時阻擋所有新進場。
    #[serde(default)]
    pub min_balance_usdt: f64,
    /// BLOCKER-3 D15: Global notional cap across all exchange pipelines (USDT).
    /// 0 = no cap (default). Paper is excluded — only Demo+Live real exposure counts.
    /// BLOCKER-3 D15：跨交易所管線全局名目上限（USDT）。0 = 無上限。Paper 排除。
    #[serde(default)]
    pub global_notional_cap_usdt: f64,
    #[serde(default = "default_allowed_categories")]
    pub allowed_categories: Vec<String>,
    #[serde(default = "default_margin_mode")]
    pub margin_mode: String,
    #[serde(default = "default_position_mode")]
    pub position_mode: String,
    /// ARCH-RC1 1C-4 E-Merge-4: Guardian "Modified" verdict knobs.
    /// When a trade intent's leverage exceeds `leverage_max` but is < 2x over,
    /// Guardian rewrites the order with `qty *= modification_size_factor` and
    /// `leverage = modification_leverage_cap`. Previously these lived only in
    /// GuardianConfig (operator-invisible); they are now first-class RiskConfig
    /// fields so the operator GUI can tune them via patch_risk_config.
    /// ARCH-RC1 1C-4 E-Merge-4：Guardian「Modified」裁決參數。
    /// 槓桿超出 leverage_max 但 < 2x 時，Guardian 將 qty *= modification_size_factor
    /// 並把 leverage 改寫為 modification_leverage_cap。原先只存在 GuardianConfig 內
    /// 對 operator 不可見，現在升級為 RiskConfig 一級欄位，可經 patch_risk_config 調整。
    #[serde(default = "default_guardian_modification_size_factor")]
    pub guardian_modification_size_factor: f64,
    #[serde(default = "default_guardian_modification_leverage_cap")]
    pub guardian_modification_leverage_cap: f64,
    /// Per-trade risk cap as a fraction of equity (0.02 = 2%). Used by
    /// IntentProcessor Gate 2.6 to size positions: max_qty = balance × pct / price.
    /// Hot-reloaded via patch_risk_config; previously hard-coded as DEFAULT_P1_RISK_PCT.
    /// 單筆風險上限（佔餘額比例，0.02 = 2%）。IntentProcessor Gate 2.6 用此計算
    /// 上限：max_qty = balance × pct / price。經 patch_risk_config 熱重載；先前寫死。
    #[serde(default = "default_per_trade_risk_pct")]
    pub per_trade_risk_pct: f64,

    /// MICRO-PROFIT-FIX-1 (2026-04-17): fast_track ReduceToHalf skips positions
    /// whose current notional has fallen below this fraction of the entry
    /// notional (current_qty × latest_price < ratio × entry_notional). Default
    /// 0.25 = "halve twice then stop" — prevents the dust-grinding loop where
    /// the same position is halved 4–6 times down to ~$1 remaining. Range
    /// [0.0, 1.0]; 0.0 disables the filter (pre-fix behaviour).
    /// MICRO-PROFIT-FIX-1：fast_track ReduceToHalf 跳過名目已降至此比例以下的倉位。
    /// Default 0.25 = 「halve 兩次後停手」，避免同一倉位被反復 halve 到 dust 化。
    /// 0.0 = 關閉過濾（還原修前行為）。
    #[serde(default = "default_ft_min_notional_ratio_of_entry")]
    pub ft_min_notional_ratio_of_entry: f64,
}

fn default_stop_loss_max_pct() -> f64 {
    5.0
}
fn default_take_profit_max_pct() -> f64 {
    20.0
}
fn default_position_size_max_pct() -> f64 {
    20.0
}
fn default_total_exposure_max_pct() -> f64 {
    100.0
}
fn default_correlated_exposure_max_pct() -> f64 {
    60.0
}
fn default_leverage_max() -> f64 {
    20.0
}
fn default_session_drawdown_max_pct() -> f64 {
    15.0
}
fn default_daily_loss_max_pct() -> f64 {
    5.0
}
fn default_consec_loss_cooldown_count() -> u32 {
    3
}
fn default_consec_loss_cooldown_min() -> u32 {
    30
}
fn default_holding_hours_max() -> f64 {
    72.0
}
fn default_open_positions_max() -> u32 {
    25
}
fn default_allowed_categories() -> Vec<String> {
    vec!["spot".into(), "linear".into(), "inverse".into()]
}
fn default_margin_mode() -> String {
    "isolated".into()
}
fn default_position_mode() -> String {
    "one_way".into()
}
fn default_guardian_modification_size_factor() -> f64 {
    0.5
}
fn default_guardian_modification_leverage_cap() -> f64 {
    2.0
}
fn default_per_trade_risk_pct() -> f64 {
    0.02
}
fn default_ft_min_notional_ratio_of_entry() -> f64 {
    // MICRO-PROFIT-FIX-1: 0.25 maps to "two halvings then stop" — a 4th halve
    // would take the position to 12.5% and be blocked. Lower values allow more
    // halvings; 0.0 disables the filter. See worklog 2026-04-17 §3.1.
    // MICRO-PROFIT-FIX-1：0.25 = 「halve 兩次後停手」（再 halve 會降到 12.5% 被擋）。
    0.25
}

impl Default for GlobalLimits {
    fn default() -> Self {
        Self {
            stop_loss_max_pct: default_stop_loss_max_pct(),
            take_profit_max_pct: default_take_profit_max_pct(),
            take_profit_enforced: false,
            position_size_max_pct: default_position_size_max_pct(),
            total_exposure_max_pct: default_total_exposure_max_pct(),
            correlated_exposure_max_pct: default_correlated_exposure_max_pct(),
            leverage_max: default_leverage_max(),
            session_drawdown_max_pct: default_session_drawdown_max_pct(),
            daily_loss_max_pct: default_daily_loss_max_pct(),
            consec_loss_cooldown_count: default_consec_loss_cooldown_count(),
            consec_loss_cooldown_min: default_consec_loss_cooldown_min(),
            holding_hours_max: default_holding_hours_max(),
            open_positions_max: default_open_positions_max(),
            min_order_notional_usdt: 0.0,
            max_order_notional_usdt: 0.0,
            min_balance_usdt: 0.0,
            global_notional_cap_usdt: 0.0,
            allowed_categories: default_allowed_categories(),
            margin_mode: default_margin_mode(),
            position_mode: default_position_mode(),
            guardian_modification_size_factor: default_guardian_modification_size_factor(),
            guardian_modification_leverage_cap: default_guardian_modification_leverage_cap(),
            per_trade_risk_pct: default_per_trade_risk_pct(),
            ft_min_notional_ratio_of_entry: default_ft_min_notional_ratio_of_entry(),
        }
    }
}

impl GlobalLimits {
    fn validate(&self) -> Result<(), String> {
        if self.stop_loss_max_pct <= 0.0 || self.stop_loss_max_pct > 100.0 {
            return Err("risk.limits.stop_loss_max_pct must be in (0, 100]".into());
        }
        if self.take_profit_max_pct <= 0.0 {
            return Err("risk.limits.take_profit_max_pct must be > 0".into());
        }
        if self.position_size_max_pct <= 0.0 || self.position_size_max_pct > 100.0 {
            return Err("risk.limits.position_size_max_pct must be in (0, 100]".into());
        }
        if self.total_exposure_max_pct <= 0.0 {
            return Err("risk.limits.total_exposure_max_pct must be > 0".into());
        }
        if self.leverage_max < 1.0 {
            return Err("risk.limits.leverage_max must be >= 1".into());
        }
        if self.open_positions_max == 0 {
            return Err("risk.limits.open_positions_max must be >= 1".into());
        }
        if self.holding_hours_max <= 0.0 {
            return Err("risk.limits.holding_hours_max must be > 0".into());
        }
        if self.min_order_notional_usdt < 0.0 || self.max_order_notional_usdt < 0.0 {
            return Err("risk.limits.*_order_notional_usdt must be >= 0".into());
        }
        if self.allowed_categories.is_empty() {
            return Err("risk.limits.allowed_categories must not be empty".into());
        }
        match self.margin_mode.as_str() {
            "isolated" | "cross" => {}
            other => return Err(format!("risk.limits.margin_mode invalid: '{}'", other)),
        }
        match self.position_mode.as_str() {
            "one_way" | "hedge" => {}
            other => return Err(format!("risk.limits.position_mode invalid: '{}'", other)),
        }
        // E-Merge-4 Guardian modification knobs / E-Merge-4 Guardian 修正參數
        if !(0.0..=1.0).contains(&self.guardian_modification_size_factor) {
            return Err("risk.limits.guardian_modification_size_factor must be in [0, 1]".into());
        }
        if self.guardian_modification_leverage_cap < 1.0 {
            return Err("risk.limits.guardian_modification_leverage_cap must be >= 1".into());
        }
        if !(0.0001..=0.20).contains(&self.per_trade_risk_pct) {
            return Err(
                "risk.limits.per_trade_risk_pct must be in [0.0001, 0.20] (0.01–20%)".into(),
            );
        }
        // MICRO-PROFIT-FIX-1: ft_min_notional_ratio_of_entry ∈ [0, 1]; 0 disables the filter.
        // MICRO-PROFIT-FIX-1：ft_min_notional_ratio_of_entry ∈ [0, 1]，0 = 關閉。
        if !(0.0..=1.0).contains(&self.ft_min_notional_ratio_of_entry) {
            return Err("risk.limits.ft_min_notional_ratio_of_entry must be in [0, 1]".into());
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// CategoryOverrides (P0)
// ---------------------------------------------------------------------------

/// Per-category P0 overrides (spot / linear / inverse / option).
/// 按品類的 P0 覆蓋。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct CategoryOverrides {
    #[serde(default)]
    pub spot: Option<CategoryOverride>,
    #[serde(default)]
    pub linear: Option<CategoryOverride>,
    #[serde(default)]
    pub inverse: Option<CategoryOverride>,
    #[serde(default)]
    pub option: Option<CategoryOverride>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct CategoryOverride {
    #[serde(default)]
    pub enabled: Option<bool>,
    #[serde(default)]
    pub leverage_max: Option<f64>,
    #[serde(default)]
    pub position_size_max_pct: Option<f64>,
    #[serde(default)]
    pub total_exposure_max_pct: Option<f64>,
    #[serde(default)]
    pub stop_loss_max_pct: Option<f64>,
    #[serde(default)]
    pub holding_hours_max: Option<f64>,
    #[serde(default)]
    pub allowed_symbols: Option<Vec<String>>,
    #[serde(default)]
    pub spot_margin_allowed: Option<bool>,
}

// ---------------------------------------------------------------------------
// StrategyOverride (per-strategy)
// ---------------------------------------------------------------------------

/// Per-strategy risk override. Indexed by strategy name in `RiskConfig.per_strategy`.
/// 按策略名稱索引的策略級風控覆蓋。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StrategyOverride {
    /// One-click pause/resume.
    /// 一鍵暫停/恢復。
    #[serde(default = "default_true")]
    pub enabled: bool,
    #[serde(default)]
    pub position_size_max_pct: Option<f64>,
    #[serde(default)]
    pub max_concurrent_positions: Option<u32>,
    #[serde(default)]
    pub consec_loss_cooldown_count: Option<u32>,
    #[serde(default)]
    pub allowed_symbols: Option<Vec<String>>,
    #[serde(default)]
    pub blocked_symbols: Option<Vec<String>>,
}

impl Default for StrategyOverride {
    fn default() -> Self {
        Self {
            enabled: true,
            position_size_max_pct: None,
            max_concurrent_positions: None,
            consec_loss_cooldown_count: None,
            allowed_symbols: None,
            blocked_symbols: None,
        }
    }
}

pub(super) fn default_true() -> bool {
    true
}

// ---------------------------------------------------------------------------
// AgentParams (P2)
// ---------------------------------------------------------------------------

/// Agent self-tunable risk-side parameters (P2).
/// Agent 自我調整的風控側參數（P2）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentParams {
    /// Effective stop-loss %. None = dynamic ATR.
    /// 有效止損百分比。None = 動態 ATR。
    #[serde(default)]
    pub stop_loss_pct: Option<f64>,
    /// Effective take-profit %. None = dynamic ATR.
    /// 有效止盈百分比。None = 動態 ATR。
    #[serde(default)]
    pub take_profit_pct: Option<f64>,
    #[serde(default = "default_true")]
    pub trailing_enabled: bool,
    #[serde(default = "default_trailing_activation_pct")]
    pub trailing_activation_pct: f64,
    #[serde(default = "default_trailing_distance_pct")]
    pub trailing_distance_pct: f64,
    /// Position size scaling (0.1 - 1.0).
    /// 倉位規模縮放（0.1 - 1.0）。
    #[serde(default = "default_size_multiplier")]
    pub size_multiplier: f64,
    /// Per-category preference weights (sum should be > 0).
    /// 按品類偏好權重（總和應 > 0）。
    #[serde(default)]
    pub category_weights: HashMap<String, f64>,
    /// Order placement preferences.
    /// 訂單放置偏好。
    #[serde(default = "default_true")]
    pub prefer_limit: bool,
    #[serde(default = "default_true")]
    pub reduce_only_close: bool,
    #[serde(default)]
    pub post_only_limit: bool,
    /// Partial take-profit toggle. Coupled to limits.take_profit_max_pct.
    /// 分批止盈開關。與 limits.take_profit_max_pct 耦合。
    #[serde(default)]
    pub partial_tp_enabled: bool,
    /// Partial TP levels: list of (pct_profit, fraction_to_close).
    /// 分批止盈各層：(百分比利潤, 平倉比例) 列表。
    #[serde(default)]
    pub partial_tp_levels: Vec<(f64, f64)>,
}

fn default_trailing_activation_pct() -> f64 {
    1.0
}
fn default_trailing_distance_pct() -> f64 {
    0.8
}
fn default_size_multiplier() -> f64 {
    1.0
}

impl Default for AgentParams {
    fn default() -> Self {
        Self {
            stop_loss_pct: None,
            take_profit_pct: None,
            trailing_enabled: default_true(),
            trailing_activation_pct: default_trailing_activation_pct(),
            trailing_distance_pct: default_trailing_distance_pct(),
            size_multiplier: default_size_multiplier(),
            category_weights: HashMap::new(),
            prefer_limit: default_true(),
            reduce_only_close: default_true(),
            post_only_limit: false,
            partial_tp_enabled: false,
            partial_tp_levels: Vec::new(),
        }
    }
}

impl AgentParams {
    fn validate(&self) -> Result<(), String> {
        if !(0.1..=1.0).contains(&self.size_multiplier) {
            return Err("risk.agent.size_multiplier must be in [0.1, 1.0]".into());
        }
        if self.trailing_activation_pct <= 0.0 {
            return Err("risk.agent.trailing_activation_pct must be > 0".into());
        }
        if self.trailing_distance_pct <= 0.0 {
            return Err("risk.agent.trailing_distance_pct must be > 0".into());
        }
        if let Some(sl) = self.stop_loss_pct {
            if sl <= 0.0 {
                return Err("risk.agent.stop_loss_pct must be > 0 when set".into());
            }
        }
        if let Some(tp) = self.take_profit_pct {
            if tp <= 0.0 {
                return Err("risk.agent.take_profit_pct must be > 0 when set".into());
            }
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// CascadeThresholds — RiskGovernor 6-level
// ---------------------------------------------------------------------------

/// Six-level RiskGovernor cascade thresholds (Normal / Cautious / Reduced / Defensive / CircuitBreaker / ManualReview).
/// 六級 RiskGovernor cascade 閾值。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CascadeThresholds {
    #[serde(default = "default_drawdown_cautious_pct")]
    pub drawdown_cautious_pct: f64,
    #[serde(default = "default_drawdown_reduced_pct")]
    pub drawdown_reduced_pct: f64,
    #[serde(default = "default_drawdown_defensive_pct")]
    pub drawdown_defensive_pct: f64,
    #[serde(default = "default_drawdown_circuit_pct")]
    pub drawdown_circuit_pct: f64,
    #[serde(default = "default_daily_loss_cautious_pct")]
    pub daily_loss_cautious_pct: f64,
    #[serde(default = "default_daily_loss_reduced_pct")]
    pub daily_loss_reduced_pct: f64,
    #[serde(default = "default_daily_loss_circuit_pct")]
    pub daily_loss_circuit_pct: f64,
    #[serde(default = "default_consec_loss_cautious")]
    pub consec_loss_cautious: u32,
    #[serde(default = "default_consec_loss_reduced")]
    pub consec_loss_reduced: u32,
    #[serde(default = "default_consec_loss_circuit")]
    pub consec_loss_circuit: u32,
    #[serde(default = "default_pressure_cautious")]
    pub pressure_cautious: f64,
    #[serde(default = "default_pressure_reduced")]
    pub pressure_reduced: f64,
    #[serde(default = "default_pressure_defensive")]
    pub pressure_defensive: f64,
    #[serde(default = "default_pressure_circuit")]
    pub pressure_circuit: f64,
    #[serde(default = "default_min_hold_ms")]
    pub min_hold_ms: u64,
}

fn default_drawdown_cautious_pct() -> f64 {
    5.0
}
fn default_drawdown_reduced_pct() -> f64 {
    8.0
}
fn default_drawdown_defensive_pct() -> f64 {
    12.0
}
fn default_drawdown_circuit_pct() -> f64 {
    15.0
}
fn default_daily_loss_cautious_pct() -> f64 {
    2.0
}
fn default_daily_loss_reduced_pct() -> f64 {
    3.5
}
fn default_daily_loss_circuit_pct() -> f64 {
    5.0
}
fn default_consec_loss_cautious() -> u32 {
    3
}
fn default_consec_loss_reduced() -> u32 {
    5
}
fn default_consec_loss_circuit() -> u32 {
    10
}
fn default_pressure_cautious() -> f64 {
    0.3
}
fn default_pressure_reduced() -> f64 {
    0.5
}
fn default_pressure_defensive() -> f64 {
    0.7
}
fn default_pressure_circuit() -> f64 {
    0.9
}
fn default_min_hold_ms() -> u64 {
    300_000
}

impl Default for CascadeThresholds {
    fn default() -> Self {
        Self {
            drawdown_cautious_pct: default_drawdown_cautious_pct(),
            drawdown_reduced_pct: default_drawdown_reduced_pct(),
            drawdown_defensive_pct: default_drawdown_defensive_pct(),
            drawdown_circuit_pct: default_drawdown_circuit_pct(),
            daily_loss_cautious_pct: default_daily_loss_cautious_pct(),
            daily_loss_reduced_pct: default_daily_loss_reduced_pct(),
            daily_loss_circuit_pct: default_daily_loss_circuit_pct(),
            consec_loss_cautious: default_consec_loss_cautious(),
            consec_loss_reduced: default_consec_loss_reduced(),
            consec_loss_circuit: default_consec_loss_circuit(),
            pressure_cautious: default_pressure_cautious(),
            pressure_reduced: default_pressure_reduced(),
            pressure_defensive: default_pressure_defensive(),
            pressure_circuit: default_pressure_circuit(),
            min_hold_ms: default_min_hold_ms(),
        }
    }
}

impl CascadeThresholds {
    fn validate(&self) -> Result<(), String> {
        // Drawdown tiers strictly increasing / Drawdown 階層嚴格遞增
        if !(self.drawdown_cautious_pct < self.drawdown_reduced_pct
            && self.drawdown_reduced_pct < self.drawdown_defensive_pct
            && self.drawdown_defensive_pct < self.drawdown_circuit_pct)
        {
            return Err(
                "risk.cascade drawdown tiers must be strictly increasing (cautious < reduced < defensive < circuit)".into()
            );
        }
        if !(self.daily_loss_cautious_pct < self.daily_loss_reduced_pct
            && self.daily_loss_reduced_pct < self.daily_loss_circuit_pct)
        {
            return Err(
                "risk.cascade daily_loss tiers must be strictly increasing (cautious < reduced < circuit)".into()
            );
        }
        if !(self.consec_loss_cautious < self.consec_loss_reduced
            && self.consec_loss_reduced < self.consec_loss_circuit)
        {
            return Err(
                "risk.cascade consec_loss tiers must be strictly increasing (cautious < reduced < circuit)".into()
            );
        }
        if !(self.pressure_cautious < self.pressure_reduced
            && self.pressure_reduced < self.pressure_defensive
            && self.pressure_defensive < self.pressure_circuit)
        {
            return Err("risk.cascade pressure tiers must be strictly increasing".into());
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// RegimeMultipliers
// ---------------------------------------------------------------------------

/// Regime-conditional multipliers applied to stop / tp / time limits.
/// 按 regime 套用到 stop / tp / time 上的乘數。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegimeMultipliers {
    #[serde(default = "default_trending")]
    pub trending: RegimeBundle,
    #[serde(default = "default_volatile")]
    pub volatile: RegimeBundle,
    #[serde(default = "default_ranging")]
    pub ranging: RegimeBundle,
    #[serde(default = "default_squeeze")]
    pub squeeze: RegimeBundle,
    #[serde(default = "default_unknown")]
    pub unknown: RegimeBundle,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct RegimeBundle {
    pub stop: f64,
    pub tp: f64,
    pub time: f64,
}

fn default_trending() -> RegimeBundle {
    RegimeBundle {
        stop: 1.0,
        tp: 1.5,
        time: 1.5,
    }
}
fn default_volatile() -> RegimeBundle {
    RegimeBundle {
        stop: 1.5,
        tp: 0.8,
        time: 0.8,
    }
}
fn default_ranging() -> RegimeBundle {
    RegimeBundle {
        stop: 0.7,
        tp: 0.7,
        time: 0.8,
    }
}
fn default_squeeze() -> RegimeBundle {
    RegimeBundle {
        stop: 0.6,
        tp: 0.5,
        time: 1.0,
    }
}
fn default_unknown() -> RegimeBundle {
    RegimeBundle {
        stop: 1.0,
        tp: 1.0,
        time: 1.0,
    }
}

impl Default for RegimeMultipliers {
    fn default() -> Self {
        Self {
            trending: default_trending(),
            volatile: default_volatile(),
            ranging: default_ranging(),
            squeeze: default_squeeze(),
            unknown: default_unknown(),
        }
    }
}

impl RegimeMultipliers {
    /// Look up bundle by regime name. Unknown names fall back to `unknown`.
    /// 按 regime 名稱查找 bundle。未知名稱回退到 `unknown`。
    pub fn get(&self, regime: &str) -> RegimeBundle {
        match regime {
            "trending" => self.trending,
            "volatile" => self.volatile,
            "ranging" => self.ranging,
            "squeeze" => self.squeeze,
            _ => self.unknown,
        }
    }

    fn validate(&self) -> Result<(), String> {
        for (name, b) in [
            ("trending", &self.trending),
            ("volatile", &self.volatile),
            ("ranging", &self.ranging),
            ("squeeze", &self.squeeze),
            ("unknown", &self.unknown),
        ] {
            if b.stop <= 0.0 || b.tp <= 0.0 || b.time <= 0.0 {
                return Err(format!("risk.regime.{} multipliers must all be > 0", name));
            }
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// CostGate
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CostGate {
    #[serde(default = "default_min_confidence")]
    pub min_confidence: f64,
    #[serde(default = "default_k_base")]
    pub k_base: f64,
    #[serde(default = "default_k_medium")]
    pub k_medium: f64,
    #[serde(default = "default_k_small")]
    pub k_small: f64,
    #[serde(default = "default_adx_trending")]
    pub adx_trending: f64,
}

fn default_min_confidence() -> f64 {
    0.15
}
fn default_k_base() -> f64 {
    1.5
}
fn default_k_medium() -> f64 {
    2.0
}
fn default_k_small() -> f64 {
    3.0
}
fn default_adx_trending() -> f64 {
    25.0
}

impl Default for CostGate {
    fn default() -> Self {
        Self {
            min_confidence: default_min_confidence(),
            k_base: default_k_base(),
            k_medium: default_k_medium(),
            k_small: default_k_small(),
            adx_trending: default_adx_trending(),
        }
    }
}

impl CostGate {
    fn validate(&self) -> Result<(), String> {
        if !(0.0..=1.0).contains(&self.min_confidence) {
            return Err("risk.cost_gate.min_confidence must be in [0, 1]".into());
        }
        if self.k_base <= 0.0 || self.k_medium <= 0.0 || self.k_small <= 0.0 {
            return Err("risk.cost_gate k coefficients must all be > 0".into());
        }
        Ok(())
    }
}


// ---------------------------------------------------------------------------
// Tests — extracted to risk_config_tests.rs (FIX-08 file size)
// 測試 — 提取至 risk_config_tests.rs（FIX-08 文件大小）
// ---------------------------------------------------------------------------

#[cfg(test)]
#[path = "risk_config_tests.rs"]
mod tests;
