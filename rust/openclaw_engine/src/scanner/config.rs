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
