//! Scanner configuration — scheduling, universe, hard filters, anti-churn, scoring weights.
//! 掃描器配置 — 調度、品類、硬過濾器、反 churn、評分權重。
//!
//! MODULE_NOTE (EN): Follows the BudgetConfig pattern exactly:
//!   - Meta struct for versioning
//!   - All fields have #[serde(default)] for partial TOML loads
//!   - Sub-structs carry their own validate() and Default
//!   - Top-level validate() delegates to sub-struct validators
//!   - TOML path: settings/risk_control_rules/scanner_config.toml
//!     or env var OPENCLAW_SCANNER_CONFIG
//! MODULE_NOTE (中): 嚴格跟隨 BudgetConfig 模式：
//!   - Meta 結構體用於版本控制
//!   - 所有字段有 #[serde(default)] 支持部分 TOML 加載
//!   - 子結構體攜帶自己的 validate() 和 Default
//!   - 頂層 validate() 委托到子結構體校驗器
//!   - TOML 路徑：settings/risk_control_rules/scanner_config.toml
//!     或環境變量 OPENCLAW_SCANNER_CONFIG

use serde::{Deserialize, Serialize};

// ─── Meta ────────────────────────────────────────────────────────────────────

fn default_meta_version() -> u32 {
    1
}

/// Config file metadata for versioning and audit.
/// 配置文件元數據，用於版本控制和審計。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Meta {
    #[serde(default = "default_meta_version")]
    pub version: u32,
    #[serde(default)]
    pub saved_ts_ms: u64,
}

impl Default for Meta {
    fn default() -> Self {
        Self {
            version: default_meta_version(),
            saved_ts_ms: 0,
        }
    }
}

// ─── SchedulingConfig ─────────────────────────────────────────────────────────

fn default_scan_interval_secs() -> u64 {
    1800 // 30 minutes / 30 分鐘
}

fn default_warmup_delay_secs() -> u64 {
    60 // 1 minute after engine start / 引擎啟動後 1 分鐘
}

/// Controls when the scanner runs.
/// 控制掃描器的運行時機。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SchedulingConfig {
    /// Seconds between scan cycles (default 1800 = 30 min) / 掃描週期間隔秒數（默認 1800 = 30 分鐘）
    #[serde(default = "default_scan_interval_secs")]
    pub scan_interval_secs: u64,
    /// Seconds to wait after engine start before first scan (default 60) / 引擎啟動後首次掃描前等待秒數（默認 60）
    #[serde(default = "default_warmup_delay_secs")]
    pub warmup_delay_secs: u64,
}

impl Default for SchedulingConfig {
    fn default() -> Self {
        Self {
            scan_interval_secs: default_scan_interval_secs(),
            warmup_delay_secs: default_warmup_delay_secs(),
        }
    }
}

impl SchedulingConfig {
    fn validate(&self) -> Result<(), String> {
        if self.scan_interval_secs == 0 {
            return Err("scan_interval_secs must be > 0".into());
        }
        Ok(())
    }
}

// ─── UniverseConfig ───────────────────────────────────────────────────────────

fn default_max_symbols() -> usize {
    25
}

fn default_pinned_symbols() -> Vec<String> {
    vec!["BTCUSDT".to_string(), "ETHUSDT".to_string()]
}

/// Controls which symbols can be in the active universe.
/// 控制哪些交易對可以進入活躍品類。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UniverseConfig {
    /// Maximum number of simultaneously active symbols including pinned (default 25) / 最大同時活躍交易對數（含固定交易對，默認 25）
    #[serde(default = "default_max_symbols")]
    pub max_symbols: usize,
    /// Symbols always included regardless of score (BTC and ETH by default) / 不論評分始終包含的交易對（默認 BTC 和 ETH）
    #[serde(default = "default_pinned_symbols")]
    pub pinned_symbols: Vec<String>,
}

impl Default for UniverseConfig {
    fn default() -> Self {
        Self {
            max_symbols: default_max_symbols(),
            pinned_symbols: default_pinned_symbols(),
        }
    }
}

impl UniverseConfig {
    fn validate(&self) -> Result<(), String> {
        if self.max_symbols == 0 {
            return Err("max_symbols must be > 0".into());
        }
        if self.pinned_symbols.len() > self.max_symbols {
            return Err(format!(
                "pinned_symbols ({}) cannot exceed max_symbols ({})",
                self.pinned_symbols.len(),
                self.max_symbols
            ));
        }
        Ok(())
    }
}

// ─── HardFilters ──────────────────────────────────────────────────────────────

fn default_min_turnover_24h_usdt() -> f64 {
    50_000_000.0 // $50M / $50M
}

fn default_max_spread_bps() -> f64 {
    8.0 // 8 basis points / 8 基點
}

fn default_min_price_usdt() -> f64 {
    0.001
}

fn default_btc_min_move_pct() -> f64 {
    0.3 // Min BTC 24h move to use beta_proxy / beta_proxy 所需的 BTC 最小 24h 移動幅度
}

/// Hard filters — any failure disqualifies the symbol entirely.
/// 硬過濾器 — 任何一項失敗直接淘汰該交易對。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HardFilters {
    /// Minimum 24h turnover in USDT (default $50M) / 最低 24h 成交額 USDT（默認 $50M）
    #[serde(default = "default_min_turnover_24h_usdt")]
    pub min_turnover_24h_usdt: f64,
    /// Maximum bid-ask spread in basis points (default 8 bps) / 最大買賣差價（基點，默認 8 bps）
    #[serde(default = "default_max_spread_bps")]
    pub max_spread_bps: f64,
    /// Minimum price in USDT (default 0.001) / 最低價格 USDT（默認 0.001）
    #[serde(default = "default_min_price_usdt")]
    pub min_price_usdt: f64,
    /// Minimum BTC 24h move pct to enable beta_proxy correlation filter (default 0.3%) / 啟用 beta_proxy 相關性過濾所需的 BTC 最小 24h 移動幅度（默認 0.3%）
    #[serde(default = "default_btc_min_move_pct")]
    pub btc_min_move_pct: f64,
}

impl Default for HardFilters {
    fn default() -> Self {
        Self {
            min_turnover_24h_usdt: default_min_turnover_24h_usdt(),
            max_spread_bps: default_max_spread_bps(),
            min_price_usdt: default_min_price_usdt(),
            btc_min_move_pct: default_btc_min_move_pct(),
        }
    }
}

impl HardFilters {
    fn validate(&self) -> Result<(), String> {
        if self.min_turnover_24h_usdt < 0.0 {
            return Err("min_turnover_24h_usdt must be >= 0".into());
        }
        if self.max_spread_bps <= 0.0 {
            return Err("max_spread_bps must be > 0".into());
        }
        if self.min_price_usdt < 0.0 {
            return Err("min_price_usdt must be >= 0".into());
        }
        Ok(())
    }
}

// ─── AntiChurnConfig ──────────────────────────────────────────────────────────

fn default_min_hold_cycles() -> u32 {
    2
}

fn default_challenger_threshold() -> f64 {
    15.0
}

fn default_removal_cooldown_minutes() -> u64 {
    90
}

/// Controls symbol stability to prevent rapid churn.
/// 控制交易對穩定性，防止快速更換。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AntiChurnConfig {
    /// Minimum scan cycles a symbol must be active before it can be removed (default 2) / 交易對被移除前必須保持活躍的最少掃描週期數（默認 2）
    #[serde(default = "default_min_hold_cycles")]
    pub min_hold_cycles: u32,
    /// Score advantage a challenger needs over incumbent to displace it (default 15.0) / 挑戰者需要超過現任的分數優勢才能替換（默認 15.0）
    #[serde(default = "default_challenger_threshold")]
    pub challenger_threshold: f64,
    /// Minutes a removed symbol must wait before re-entry (default 90) / 移除的交易對重新加入前必須等待的分鐘數（默認 90）
    #[serde(default = "default_removal_cooldown_minutes")]
    pub removal_cooldown_minutes: u64,
}

impl Default for AntiChurnConfig {
    fn default() -> Self {
        Self {
            min_hold_cycles: default_min_hold_cycles(),
            challenger_threshold: default_challenger_threshold(),
            removal_cooldown_minutes: default_removal_cooldown_minutes(),
        }
    }
}

impl AntiChurnConfig {
    fn validate(&self) -> Result<(), String> {
        if self.challenger_threshold < 0.0 {
            return Err("challenger_threshold must be >= 0".into());
        }
        Ok(())
    }
}

// ─── CorrelationLimits ────────────────────────────────────────────────────────

fn default_max_high_beta_symbols() -> usize {
    8
}

fn default_max_per_strategy() -> usize {
    8
}

fn default_max_per_sector() -> usize {
    4
}

fn default_high_beta_threshold() -> f64 {
    0.8
}

/// Diversification caps applied after scoring.
/// 評分後施加的分散限制。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CorrelationLimits {
    /// Maximum symbols with beta_proxy > high_beta_threshold (default 8) / beta_proxy 超過閾值的最大交易對數（默認 8）
    #[serde(default = "default_max_high_beta_symbols")]
    pub max_high_beta_symbols: usize,
    /// Maximum symbols per strategy category (default 8) / 每個策略類別的最大交易對數（默認 8）
    #[serde(default = "default_max_per_strategy")]
    pub max_per_strategy: usize,
    /// Maximum symbols per market sector (default 4) / 每個市場板塊的最大交易對數（默認 4）
    #[serde(default = "default_max_per_sector")]
    pub max_per_sector: usize,
    /// BTC beta threshold to classify a symbol as "high beta" (default 0.8) / 將交易對分類為「高 beta」的 BTC beta 閾值（默認 0.8）
    #[serde(default = "default_high_beta_threshold")]
    pub high_beta_threshold: f64,
}

impl Default for CorrelationLimits {
    fn default() -> Self {
        Self {
            max_high_beta_symbols: default_max_high_beta_symbols(),
            max_per_strategy: default_max_per_strategy(),
            max_per_sector: default_max_per_sector(),
            high_beta_threshold: default_high_beta_threshold(),
        }
    }
}

impl CorrelationLimits {
    fn validate(&self) -> Result<(), String> {
        if self.max_per_sector == 0 {
            return Err("max_per_sector must be > 0".into());
        }
        Ok(())
    }
}

// ─── EdgeRoutingConfig ─────────────────────────────────────────────────────────

fn default_edge_bonus_weight() -> f64 {
    0.5
}

fn default_edge_bonus_min_bps() -> f64 {
    -30.0
}

fn default_edge_bonus_max_bps() -> f64 {
    10.0
}

fn default_unexplored_bonus() -> f64 {
    2.0
}

fn default_robust_negative_min_trades() -> u32 {
    30
}

fn default_robust_negative_bps_threshold() -> f64 {
    0.0
}

fn default_robust_negative_score_cap() -> f64 {
    35.0
}

fn default_posterior_lcb_z() -> f64 {
    0.0
}

fn default_posterior_min_std_bps() -> f64 {
    20.0
}

/// Edge-aware scanner routing knobs. These defaults preserve the previous
/// bonus formula for normal cells while preventing mature negative cells from
/// dominating the active universe purely on raw scanner fitness.
/// Edge-aware scanner 路由參數。正常 cell 保持原 bonus 公式；成熟負 edge cell
/// 不再能只靠 scanner raw fitness 擠進主交易 universe。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EdgeRoutingConfig {
    /// Multiplier from runtime edge bps to scanner score bonus.
    /// runtime edge bps 轉 scanner score bonus 的權重。
    #[serde(default = "default_edge_bonus_weight")]
    pub bonus_weight: f64,
    /// Minimum edge bonus after weighting.
    /// 加權後 edge bonus 下限。
    #[serde(default = "default_edge_bonus_min_bps")]
    pub bonus_min: f64,
    /// Maximum edge bonus after weighting.
    /// 加權後 edge bonus 上限。
    #[serde(default = "default_edge_bonus_max_bps")]
    pub bonus_max: f64,
    /// Small credit for unexplored strategy-symbol cells.
    /// 未探索 strategy-symbol cell 的小額探索加分。
    #[serde(default = "default_unexplored_bonus")]
    pub unexplored_bonus: f64,
    /// Sample count at which a negative edge cell is treated as mature.
    /// 負 edge cell 被視為成熟所需樣本數。
    #[serde(default = "default_robust_negative_min_trades")]
    pub robust_negative_min_trades: u32,
    /// Runtime bps threshold below which mature cells are robust-negative.
    /// 成熟 cell 低於此 runtime bps 即視為 robust negative。
    #[serde(default = "default_robust_negative_bps_threshold")]
    pub robust_negative_bps_threshold: f64,
    /// Score cap for mature negative cells. Set to 100 to effectively disable.
    /// 成熟負 edge cell 的 scanner score 上限；設 100 可近似關閉。
    #[serde(default = "default_robust_negative_score_cap")]
    pub robust_negative_score_cap: f64,
    /// Z-score for posterior lower confidence bound. 0 disables LCB gating.
    /// posterior 下置信界 z 值；0 表示關閉 LCB 門。
    #[serde(default = "default_posterior_lcb_z")]
    pub posterior_lcb_z: f64,
    /// Minimum std_bps used when a cell has no usable sample std.
    /// cell 無有效 std_bps 時使用的最小標準差。
    #[serde(default = "default_posterior_min_std_bps")]
    pub posterior_min_std_bps: f64,
    /// LCB threshold below which mature cells become exploration-only.
    /// mature cell 的 LCB 低於此值時只走探索路由。
    #[serde(default = "default_robust_negative_bps_threshold")]
    pub posterior_negative_lcb_threshold_bps: f64,
}

impl Default for EdgeRoutingConfig {
    fn default() -> Self {
        Self {
            bonus_weight: default_edge_bonus_weight(),
            bonus_min: default_edge_bonus_min_bps(),
            bonus_max: default_edge_bonus_max_bps(),
            unexplored_bonus: default_unexplored_bonus(),
            robust_negative_min_trades: default_robust_negative_min_trades(),
            robust_negative_bps_threshold: default_robust_negative_bps_threshold(),
            robust_negative_score_cap: default_robust_negative_score_cap(),
            posterior_lcb_z: default_posterior_lcb_z(),
            posterior_min_std_bps: default_posterior_min_std_bps(),
            posterior_negative_lcb_threshold_bps: default_robust_negative_bps_threshold(),
        }
    }
}

impl EdgeRoutingConfig {
    fn validate(&self) -> Result<(), String> {
        if !self.bonus_weight.is_finite() || self.bonus_weight < 0.0 {
            return Err("edge_routing.bonus_weight must be finite and >= 0".into());
        }
        if !self.bonus_min.is_finite()
            || !self.bonus_max.is_finite()
            || self.bonus_min > self.bonus_max
        {
            return Err("edge_routing bonus_min/bonus_max invalid".into());
        }
        if !self.unexplored_bonus.is_finite() {
            return Err("edge_routing.unexplored_bonus must be finite".into());
        }
        if !self.robust_negative_bps_threshold.is_finite() {
            return Err("edge_routing.robust_negative_bps_threshold must be finite".into());
        }
        if !self.robust_negative_score_cap.is_finite()
            || !(0.0..=100.0).contains(&self.robust_negative_score_cap)
        {
            return Err("edge_routing.robust_negative_score_cap must be in [0, 100]".into());
        }
        if !self.posterior_lcb_z.is_finite() || !(0.0..=5.0).contains(&self.posterior_lcb_z) {
            return Err("edge_routing.posterior_lcb_z must be in [0, 5]".into());
        }
        if !self.posterior_min_std_bps.is_finite()
            || !(0.0..=500.0).contains(&self.posterior_min_std_bps)
        {
            return Err("edge_routing.posterior_min_std_bps must be in [0, 500]".into());
        }
        if !self.posterior_negative_lcb_threshold_bps.is_finite() {
            return Err("edge_routing.posterior_negative_lcb_threshold_bps must be finite".into());
        }
        Ok(())
    }
}

// ─── MarketJudgmentConfig ─────────────────────────────────────────────────────

fn default_market_judgment_enabled() -> bool {
    true
}

fn default_market_gate_score_cap() -> f64 {
    25.0
}

fn default_grid_max_trend_score() -> f64 {
    0.55
}

fn default_grid_max_directional_efficiency() -> f64 {
    0.55
}

fn default_grid_max_dir_pct() -> f64 {
    3.5
}

fn default_grid_min_range_pct() -> f64 {
    3.0
}

fn default_trend_min_trend_score() -> f64 {
    0.45
}

fn default_trend_min_dir_pct() -> f64 {
    0.8
}

fn default_reversion_min_range_pct() -> f64 {
    4.0
}

fn default_reversion_max_trend_score() -> f64 {
    0.60
}

fn default_breakout_min_trend_score() -> f64 {
    0.50
}

fn default_breakout_min_dir_pct() -> f64 {
    1.8
}

fn default_funding_max_dir_pct() -> f64 {
    4.0
}

fn default_funding_max_trend_score() -> f64 {
    0.65
}

fn default_immature_negative_min_trades() -> u32 {
    15
}

fn default_immature_negative_bps_threshold() -> f64 {
    -5.0
}

fn default_immature_negative_score_cap() -> f64 {
    35.0
}

/// Strategy-specific scanner market judgement. This is deliberately separate
/// from `edge_routing`: edge tells us what has happened for a cell, while
/// market judgement decides whether the current regime is compatible with a
/// strategy before demo/live_demo opens a fresh position.
/// 策略別行情判斷。刻意與 `edge_routing` 分離：edge 回饋描述 cell 已實現表現；
/// market judgement 則判斷當下 regime 是否適合該策略新開倉。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketJudgmentConfig {
    /// Master switch. When false, scanner emits neutral market metadata.
    /// 總開關；關閉時 scanner 只輸出中性行情 metadata。
    #[serde(default = "default_market_judgment_enabled")]
    pub enabled: bool,
    /// Score cap applied to a strategy-symbol route rejected by market judgement.
    /// market judgement 拒絕的 strategy-symbol route 的分數上限。
    #[serde(default = "default_market_gate_score_cap")]
    pub gate_score_cap: f64,
    /// Grid is blocked above this trend score.
    /// trend_score 高於此值時阻擋 grid 新開倉。
    #[serde(default = "default_grid_max_trend_score")]
    pub grid_max_trend_score: f64,
    /// Grid is blocked above this directional efficiency.
    /// 方向效率高於此值時阻擋 grid 新開倉。
    #[serde(default = "default_grid_max_directional_efficiency")]
    pub grid_max_directional_efficiency: f64,
    /// Grid is blocked when net 24h move is too directional.
    /// 24h 淨方向移動過大時阻擋 grid 新開倉。
    #[serde(default = "default_grid_max_dir_pct")]
    pub grid_max_dir_pct: f64,
    /// Grid needs enough range to pay fees and spacing.
    /// grid 需要足夠區間以覆蓋費用與網格間距。
    #[serde(default = "default_grid_min_range_pct")]
    pub grid_min_range_pct: f64,
    /// MA-like trend followers need at least this trend score.
    /// MA 類趨勢策略所需最低 trend_score。
    #[serde(default = "default_trend_min_trend_score")]
    pub trend_min_trend_score: f64,
    /// MA-like trend followers need at least this 24h move.
    /// MA 類趨勢策略所需最低 24h 淨移動。
    #[serde(default = "default_trend_min_dir_pct")]
    pub trend_min_dir_pct: f64,
    /// BB reversion needs enough realized range.
    /// BB 回歸所需最低 range。
    #[serde(default = "default_reversion_min_range_pct")]
    pub reversion_min_range_pct: f64,
    /// BB reversion is blocked when trend score is too high.
    /// trend_score 過高時阻擋 BB 回歸。
    #[serde(default = "default_reversion_max_trend_score")]
    pub reversion_max_trend_score: f64,
    /// BB breakout needs a stronger directional expansion proxy.
    /// BB 突破所需最低方向擴張 proxy。
    #[serde(default = "default_breakout_min_trend_score")]
    pub breakout_min_trend_score: f64,
    /// BB breakout needs this 24h net move.
    /// BB 突破所需最低 24h 淨移動。
    #[serde(default = "default_breakout_min_dir_pct")]
    pub breakout_min_dir_pct: f64,
    /// Funding arb gets a soft caution when price trend is too directional.
    /// This lowers route score but does not hard-block demo/live_demo entries.
    /// 價格趨勢過強時對 funding arb 加軟性警示；只降低路由分數，不硬阻擋
    /// demo/live_demo 新開倉。
    #[serde(default = "default_funding_max_dir_pct")]
    pub funding_max_dir_pct: f64,
    /// Funding arb trend-score caution threshold.
    /// funding arb trend_score 軟警示門檻。
    #[serde(default = "default_funding_max_trend_score")]
    pub funding_max_trend_score: f64,
    /// Low-sample negative edge watch threshold.
    /// 低樣本負 edge 觀察降分所需最小樣本數。
    #[serde(default = "default_immature_negative_min_trades")]
    pub immature_negative_min_trades: u32,
    /// Low-sample cells below this bps are watched/capped before they mature.
    /// 低樣本 cell 低於此 bps 時先觀察降分，不等成熟門檻。
    #[serde(default = "default_immature_negative_bps_threshold")]
    pub immature_negative_bps_threshold: f64,
    /// Score cap for immature negative cells; not a hard entry gate.
    /// 低樣本負 edge cell 分數上限；不是硬入場 gate。
    #[serde(default = "default_immature_negative_score_cap")]
    pub immature_negative_score_cap: f64,
}

impl Default for MarketJudgmentConfig {
    fn default() -> Self {
        Self {
            enabled: default_market_judgment_enabled(),
            gate_score_cap: default_market_gate_score_cap(),
            grid_max_trend_score: default_grid_max_trend_score(),
            grid_max_directional_efficiency: default_grid_max_directional_efficiency(),
            grid_max_dir_pct: default_grid_max_dir_pct(),
            grid_min_range_pct: default_grid_min_range_pct(),
            trend_min_trend_score: default_trend_min_trend_score(),
            trend_min_dir_pct: default_trend_min_dir_pct(),
            reversion_min_range_pct: default_reversion_min_range_pct(),
            reversion_max_trend_score: default_reversion_max_trend_score(),
            breakout_min_trend_score: default_breakout_min_trend_score(),
            breakout_min_dir_pct: default_breakout_min_dir_pct(),
            funding_max_dir_pct: default_funding_max_dir_pct(),
            funding_max_trend_score: default_funding_max_trend_score(),
            immature_negative_min_trades: default_immature_negative_min_trades(),
            immature_negative_bps_threshold: default_immature_negative_bps_threshold(),
            immature_negative_score_cap: default_immature_negative_score_cap(),
        }
    }
}

impl MarketJudgmentConfig {
    fn validate(&self) -> Result<(), String> {
        for (name, value) in [
            ("market_judgment.gate_score_cap", self.gate_score_cap),
            (
                "market_judgment.grid_max_trend_score",
                self.grid_max_trend_score,
            ),
            (
                "market_judgment.grid_max_directional_efficiency",
                self.grid_max_directional_efficiency,
            ),
            ("market_judgment.grid_max_dir_pct", self.grid_max_dir_pct),
            (
                "market_judgment.grid_min_range_pct",
                self.grid_min_range_pct,
            ),
            (
                "market_judgment.trend_min_trend_score",
                self.trend_min_trend_score,
            ),
            ("market_judgment.trend_min_dir_pct", self.trend_min_dir_pct),
            (
                "market_judgment.reversion_min_range_pct",
                self.reversion_min_range_pct,
            ),
            (
                "market_judgment.reversion_max_trend_score",
                self.reversion_max_trend_score,
            ),
            (
                "market_judgment.breakout_min_trend_score",
                self.breakout_min_trend_score,
            ),
            (
                "market_judgment.breakout_min_dir_pct",
                self.breakout_min_dir_pct,
            ),
            (
                "market_judgment.funding_max_dir_pct",
                self.funding_max_dir_pct,
            ),
            (
                "market_judgment.funding_max_trend_score",
                self.funding_max_trend_score,
            ),
            (
                "market_judgment.immature_negative_bps_threshold",
                self.immature_negative_bps_threshold,
            ),
            (
                "market_judgment.immature_negative_score_cap",
                self.immature_negative_score_cap,
            ),
        ] {
            if !value.is_finite() {
                return Err(format!("{name} must be finite"));
            }
        }
        if !(0.0..=100.0).contains(&self.gate_score_cap) {
            return Err("market_judgment.gate_score_cap must be in [0, 100]".into());
        }
        if self.grid_max_dir_pct < 0.0
            || self.grid_min_range_pct < 0.0
            || self.trend_min_dir_pct < 0.0
            || self.reversion_min_range_pct < 0.0
            || self.breakout_min_dir_pct < 0.0
            || self.funding_max_dir_pct < 0.0
        {
            return Err("market_judgment pct thresholds must be >= 0".into());
        }
        if !(0.0..=1.0).contains(&self.grid_max_trend_score)
            || !(0.0..=1.0).contains(&self.grid_max_directional_efficiency)
            || !(0.0..=1.0).contains(&self.trend_min_trend_score)
            || !(0.0..=1.0).contains(&self.reversion_max_trend_score)
            || !(0.0..=1.0).contains(&self.breakout_min_trend_score)
            || !(0.0..=1.0).contains(&self.funding_max_trend_score)
        {
            return Err("market_judgment score thresholds must be in [0, 1]".into());
        }
        if !(0.0..=100.0).contains(&self.immature_negative_score_cap) {
            return Err("market_judgment.immature_negative_score_cap must be in [0, 100]".into());
        }
        Ok(())
    }
}

// ─── ScannerConfig ────────────────────────────────────────────────────────────

/// Top-level scanner configuration.
/// TOML path: settings/risk_control_rules/scanner_config.toml
/// Env override: OPENCLAW_SCANNER_CONFIG
/// 頂層掃描器配置。
/// TOML 路徑：settings/risk_control_rules/scanner_config.toml
/// 環境變量覆蓋：OPENCLAW_SCANNER_CONFIG
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ScannerConfig {
    #[serde(default)]
    pub meta: Meta,
    #[serde(default)]
    pub scheduling: SchedulingConfig,
    #[serde(default)]
    pub universe: UniverseConfig,
    #[serde(default)]
    pub hard_filters: HardFilters,
    #[serde(default)]
    pub anti_churn: AntiChurnConfig,
    #[serde(default)]
    pub correlation: CorrelationLimits,
    #[serde(default)]
    pub edge_routing: EdgeRoutingConfig,
    #[serde(default)]
    pub market_judgment: MarketJudgmentConfig,
}

impl ScannerConfig {
    /// Validate all sub-config invariants.
    /// 校驗所有子配置不變量。
    pub fn validate(&self) -> Result<(), String> {
        self.scheduling.validate()?;
        self.universe.validate()?;
        self.hard_filters.validate()?;
        self.anti_churn.validate()?;
        self.correlation.validate()?;
        self.edge_routing.validate()?;
        self.market_judgment.validate()?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_scanner_config_valid() {
        let cfg = ScannerConfig::default();
        assert!(cfg.validate().is_ok());
    }

    #[test]
    fn test_toml_round_trip() {
        let cfg = ScannerConfig::default();
        let toml_str = toml::to_string(&cfg).unwrap();
        let cfg2: ScannerConfig = toml::from_str(&toml_str).unwrap();
        assert!(cfg2.validate().is_ok());
        assert_eq!(
            cfg2.scheduling.scan_interval_secs,
            cfg.scheduling.scan_interval_secs
        );
        assert_eq!(cfg2.hard_filters.min_turnover_24h_usdt, 50_000_000.0);
    }

    #[test]
    fn test_invalid_max_symbols_zero() {
        let mut cfg = ScannerConfig::default();
        cfg.universe.max_symbols = 0;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_invalid_scan_interval_zero() {
        let mut cfg = ScannerConfig::default();
        cfg.scheduling.scan_interval_secs = 0;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_pinned_exceeds_max_fails() {
        let mut cfg = ScannerConfig::default();
        cfg.universe.max_symbols = 1;
        cfg.universe.pinned_symbols = vec!["BTCUSDT".to_string(), "ETHUSDT".to_string()];
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_default_pinned_contains_btc_eth() {
        let cfg = ScannerConfig::default();
        assert!(cfg.universe.pinned_symbols.contains(&"BTCUSDT".to_string()));
        assert!(cfg.universe.pinned_symbols.contains(&"ETHUSDT".to_string()));
    }

    #[test]
    fn test_partial_toml_uses_defaults() {
        let partial = "[scheduling]\nscan_interval_secs = 900\n";
        let cfg: ScannerConfig = toml::from_str(partial).unwrap();
        assert_eq!(cfg.scheduling.scan_interval_secs, 900);
        // Other fields should still use defaults
        assert_eq!(cfg.hard_filters.min_turnover_24h_usdt, 50_000_000.0);
        assert_eq!(cfg.anti_churn.min_hold_cycles, 2);
    }
}
