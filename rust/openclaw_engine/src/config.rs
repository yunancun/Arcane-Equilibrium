//! Engine runtime configuration with ArcSwap hot-reload (R01-4).
//! 引擎運行時配置，使用 ArcSwap 實現熱加載。
//!
//! MODULE_NOTE (EN): Reads engine.toml, provides atomic zero-lock config reads (~5ns).
//!   Cold params require restart; hot params reload via SIGHUP.
//! MODULE_NOTE (中): 讀取 engine.toml，提供原子無鎖配置讀取（~5ns）。
//!   冷參數需重啟；熱參數通過 SIGHUP 重載。

use arc_swap::ArcSwap;
use serde::Deserialize;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use thiserror::Error;
use tracing::{info, warn};

// ---------------------------------------------------------------------------
// Error types / 錯誤類型
// ---------------------------------------------------------------------------

/// Configuration errors.
/// 配置錯誤。
#[derive(Debug, Error)]
pub enum ConfigError {
    /// Failed to read config file / 讀取配置文件失敗
    #[error("failed to read config file '{path}': {source}")]
    ReadFile {
        path: String,
        source: std::io::Error,
    },

    /// Failed to parse TOML / 解析 TOML 失敗
    #[error("failed to parse TOML: {0}")]
    ParseToml(#[from] toml::de::Error),

    /// Validation error / 驗證錯誤
    #[error("config validation failed: {0}")]
    Validation(String),
}

// ---------------------------------------------------------------------------
// Config struct / 配置結構
// ---------------------------------------------------------------------------

/// Complete engine runtime configuration.
/// 完整引擎運行時配置。
///
/// Cold params (require restart): ws_url, reconnect_delay_ms, heartbeat_interval_ms,
///   ipc_socket_path, state_push_interval_ms.
/// Hot params (SIGHUP reload): risk limits, attention intervals, cognitive params.
///
/// 冷參數（需重啟）：ws_url, reconnect_delay_ms, heartbeat_interval_ms,
///   ipc_socket_path, state_push_interval_ms。
/// 熱參數（SIGHUP 重載）：風控限制、注意力間隔、認知參數。
#[derive(Debug, Clone, Deserialize)]
pub struct RuntimeConfig {
    // -- Cold params / 冷參數 --
    /// Bybit WebSocket URL / Bybit WebSocket 地址
    #[serde(default = "default_ws_url")]
    pub ws_url: String,

    /// Reconnect base delay (ms) / 重連基礎延遲（毫秒）
    #[serde(default = "default_reconnect_delay_ms")]
    pub reconnect_delay_ms: u64,

    /// Heartbeat/ping interval (ms) / 心跳間隔（毫秒）
    #[serde(default = "default_heartbeat_interval_ms")]
    pub heartbeat_interval_ms: u64,

    /// Unix domain socket path for IPC / IPC Unix 域套接字路徑
    #[serde(default = "default_ipc_socket_path")]
    pub ipc_socket_path: String,

    /// State push interval to Python side (ms) / 狀態推送間隔（毫秒）
    #[serde(default = "default_state_push_interval_ms")]
    pub state_push_interval_ms: u64,

    // -- Hot params — risk / 熱參數 — 風控 --
    /// Max stop-loss percentage per position / 每倉位最大止損百分比
    #[serde(default = "default_max_stop_loss_pct")]
    pub max_stop_loss_pct: f64,

    /// Max take-profit percentage per position / 每倉位最大止盈百分比
    #[serde(default = "default_max_take_profit_pct")]
    pub max_take_profit_pct: f64,

    /// Max number of open positions / 最大持倉數
    #[serde(default = "default_max_open_positions")]
    pub max_open_positions: u32,

    /// Max total portfolio exposure (%) / 最大總組合曝險百分比
    #[serde(default = "default_max_total_exposure_pct")]
    pub max_total_exposure_pct: f64,

    // -- Hot params — attention intervals (ms) / 熱參數 — 注意力間隔 --
    /// Dormant attention interval (ms) / 休眠注意力間隔
    #[serde(default = "default_attention_dormant_ms")]
    pub attention_dormant_ms: u64,

    /// Low attention interval (ms) / 低注意力間隔
    #[serde(default = "default_attention_low_ms")]
    pub attention_low_ms: u64,

    /// Medium attention interval (ms) / 中等注意力間隔
    #[serde(default = "default_attention_medium_ms")]
    pub attention_medium_ms: u64,

    /// High attention interval (ms) / 高注意力間隔
    #[serde(default = "default_attention_high_ms")]
    pub attention_high_ms: u64,

    /// Critical attention interval (ms) / 關鍵注意力間隔
    #[serde(default = "default_attention_critical_ms")]
    pub attention_critical_ms: u64,

    // -- Hot params — Bybit API integration / 熱參數 — Bybit API 整合 --
    /// Enable DCP (Disconnected Cancel Protection) at startup / 啟動時啟用斷連取消保護
    #[serde(default = "default_true")]
    pub dcp_enabled: bool,

    /// DCP time window in seconds / DCP 時間窗口（秒）
    #[serde(default = "default_dcp_time_window")]
    pub dcp_time_window: u32,

    /// Enable auto-add-margin for existing positions at startup / 啟動時為現有倉位啟用自動追加保證金
    #[serde(default = "default_true")]
    pub auto_add_margin: bool,

    /// Balance mode: "custom" (user-set) or "bybit_sync" (read from Bybit Demo)
    /// 餘額模式："custom"（自設金額）或 "bybit_sync"（讀取 Bybit Demo）
    #[serde(default = "default_balance_mode")]
    pub balance_mode: String,

    /// Enable server-side TP/SL via set_trading_stop / 啟用伺服器端止盈止損
    #[serde(default = "default_true")]
    pub server_side_stops: bool,

    /// Enable extended WS subscriptions (adl-notice, price-limit) / 啟用擴展 WS 訂閱
    #[serde(default = "default_true")]
    pub enable_extended_ws: bool,

    /// Enable shadow orders: mirror paper fills to Demo API for comparison (default: on).
    /// 啟用影子訂單：將紙盤成交映射到 Demo API 進行比較（預設：開啟）。
    #[serde(default = "default_true")]
    pub shadow_orders: bool,

    /// Enable kline bootstrap at startup (fetch 200 historical 1m bars per symbol via REST).
    /// 啟動時啟用 K 線引導（通過 REST 為每個幣種獲取 200 根 1 分鐘歷史 K 線）。
    #[serde(default = "default_true")]
    pub kline_bootstrap: bool,

    // -- Phase 1: Database configuration / 資料庫配置 --
    /// Database configuration section (Phase 1).
    /// 資料庫配置段。
    #[serde(default)]
    pub database: crate::database::DatabaseConfig,

    // -- Phase 2b: ML configuration / ML 配置 --
    /// ML inference + Kelly sizing configuration (Phase 2b).
    /// ML 推理 + Kelly 倉位管理配置。
    #[serde(default)]
    pub ml: MlConfig,
}

/// ML inference + Kelly sizing configuration.
/// ML 推理 + Kelly 倉位管理配置。
#[derive(Debug, Clone, serde::Deserialize)]
pub struct MlConfig {
    /// Path to ONNX model file (empty = no model) / ONNX 模型路徑（空 = 無模型）
    #[serde(default)]
    pub onnx_model_path: String,
    /// Enable scorer (master switch) / 啟用評分器
    #[serde(default = "default_true")]
    pub scorer_enabled: bool,
    /// Enable Kelly sizing / 啟用 Kelly 倉位管理
    #[serde(default = "default_true")]
    pub kelly_enabled: bool,
    /// Max Kelly fraction (never full Kelly) / 最大 Kelly 分數
    #[serde(default = "default_kelly_max")]
    pub kelly_max_fraction: f64,
    /// Min trades before Kelly activates / Kelly 啟動最少交易數
    #[serde(default = "default_kelly_min_trades")]
    pub kelly_min_trades: u32,
    /// Fallback risk pct when Kelly inactive / Kelly 未啟動時的回退風險百分比
    #[serde(default = "default_kelly_risk")]
    pub kelly_risk_pct: f64,
}

fn default_kelly_max() -> f64 { 0.25 }
fn default_kelly_min_trades() -> u32 { 50 }
fn default_kelly_risk() -> f64 { 0.03 }

impl Default for MlConfig {
    fn default() -> Self {
        Self {
            onnx_model_path: String::new(),
            scorer_enabled: true,
            kelly_enabled: true,
            kelly_max_fraction: default_kelly_max(),
            kelly_min_trades: default_kelly_min_trades(),
            kelly_risk_pct: default_kelly_risk(),
        }
    }
}

// ---------------------------------------------------------------------------
// Defaults / 預設值
// ---------------------------------------------------------------------------

fn default_ws_url() -> String {
    "wss://stream.bybit.com/v5/public/linear".into()
}
fn default_reconnect_delay_ms() -> u64 {
    3000
}
fn default_heartbeat_interval_ms() -> u64 {
    20000
}
fn default_ipc_socket_path() -> String {
    // Cross-platform: use env or fallback / 跨平台：優先環境變量
    std::env::var("OPENCLAW_IPC_SOCKET")
        .unwrap_or_else(|_| "/tmp/openclaw/engine.sock".into())
}
fn default_state_push_interval_ms() -> u64 {
    1000
}
fn default_max_stop_loss_pct() -> f64 {
    5.0
}
fn default_max_take_profit_pct() -> f64 {
    8.0
}
fn default_max_open_positions() -> u32 {
    25
}
fn default_max_total_exposure_pct() -> f64 {
    100.0
}
fn default_attention_dormant_ms() -> u64 {
    60_000
}
fn default_attention_low_ms() -> u64 {
    30_000
}
fn default_attention_medium_ms() -> u64 {
    10_000
}
fn default_attention_high_ms() -> u64 {
    5000
}
fn default_attention_critical_ms() -> u64 {
    1000
}
fn default_true() -> bool {
    true
}
fn default_dcp_time_window() -> u32 {
    10
}
fn default_balance_mode() -> String {
    "custom".into()
}

impl Default for RuntimeConfig {
    fn default() -> Self {
        Self {
            ws_url: default_ws_url(),
            reconnect_delay_ms: default_reconnect_delay_ms(),
            heartbeat_interval_ms: default_heartbeat_interval_ms(),
            ipc_socket_path: default_ipc_socket_path(),
            state_push_interval_ms: default_state_push_interval_ms(),
            max_stop_loss_pct: default_max_stop_loss_pct(),
            max_take_profit_pct: default_max_take_profit_pct(),
            max_open_positions: default_max_open_positions(),
            max_total_exposure_pct: default_max_total_exposure_pct(),
            attention_dormant_ms: default_attention_dormant_ms(),
            attention_low_ms: default_attention_low_ms(),
            attention_medium_ms: default_attention_medium_ms(),
            attention_high_ms: default_attention_high_ms(),
            attention_critical_ms: default_attention_critical_ms(),
            dcp_enabled: default_true(),
            dcp_time_window: default_dcp_time_window(),
            auto_add_margin: default_true(),
            balance_mode: default_balance_mode(),
            server_side_stops: default_true(),
            enable_extended_ws: default_true(),
            shadow_orders: true,
            kline_bootstrap: default_true(),
            database: crate::database::DatabaseConfig::default(),
            ml: MlConfig::default(),
        }
    }
}

impl RuntimeConfig {
    /// Validate configuration values.
    /// 驗證配置值。
    pub fn validate(&self) -> Result<(), ConfigError> {
        if self.max_open_positions == 0 {
            return Err(ConfigError::Validation(
                "max_open_positions must be > 0".into(),
            ));
        }
        if self.max_stop_loss_pct <= 0.0 || self.max_stop_loss_pct > 100.0 {
            return Err(ConfigError::Validation(
                "max_stop_loss_pct must be in (0, 100]".into(),
            ));
        }
        if self.max_take_profit_pct <= 0.0 {
            return Err(ConfigError::Validation(
                "max_take_profit_pct must be > 0".into(),
            ));
        }
        if self.max_total_exposure_pct <= 0.0 {
            return Err(ConfigError::Validation(
                "max_total_exposure_pct must be > 0".into(),
            ));
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// ConfigManager — ArcSwap-based hot reload / 基於 ArcSwap 的熱加載管理器
// ---------------------------------------------------------------------------

/// Atomic config manager using ArcSwap for zero-lock reads.
/// 使用 ArcSwap 的原子配置管理器，實現零鎖讀取。
pub struct ConfigManager {
    inner: ArcSwap<RuntimeConfig>,
    file_path: PathBuf,
}

impl ConfigManager {
    /// Load config from file. Falls back to defaults if file is missing.
    /// 從文件加載配置。文件缺失時使用預設值。
    pub fn load(path: Option<&str>) -> Result<Self, ConfigError> {
        let file_path = resolve_config_path(path);
        let config = load_from_file(&file_path)?;
        config.validate()?;
        info!(path = %file_path.display(), "config loaded / 配置已加載");
        Ok(Self {
            inner: ArcSwap::from_pointee(config),
            file_path,
        })
    }

    /// Get current config snapshot (zero-lock, ~5ns).
    /// 獲取當前配置快照（零鎖，~5ns）。
    pub fn get(&self) -> Arc<RuntimeConfig> {
        self.inner.load_full()
    }

    /// Hot-reload config from file. Only hot params take effect.
    /// 從文件熱加載配置。只有熱參數生效。
    pub fn reload(&self) -> Result<(), ConfigError> {
        let new_config = load_from_file(&self.file_path)?;
        new_config.validate()?;

        let old = self.inner.load_full();

        // Warn if cold params changed (they won't take effect) / 冷參數變更警告
        if old.ws_url != new_config.ws_url {
            warn!("ws_url changed but is cold — requires restart / ws_url 已變更但為冷參數，需重啟");
        }
        if old.reconnect_delay_ms != new_config.reconnect_delay_ms {
            warn!("reconnect_delay_ms changed but is cold — requires restart");
        }
        if old.heartbeat_interval_ms != new_config.heartbeat_interval_ms {
            warn!("heartbeat_interval_ms changed but is cold — requires restart");
        }
        if old.ipc_socket_path != new_config.ipc_socket_path {
            warn!("ipc_socket_path changed but is cold — requires restart");
        }
        if old.state_push_interval_ms != new_config.state_push_interval_ms {
            warn!("state_push_interval_ms changed but is cold — requires restart");
        }

        self.inner.store(Arc::new(new_config));
        info!(path = %self.file_path.display(), "config reloaded (hot params) / 配置已重載（熱參數）");
        Ok(())
    }

    /// Get the config file path.
    /// 獲取配置文件路徑。
    pub fn file_path(&self) -> &Path {
        &self.file_path
    }
}

// ---------------------------------------------------------------------------
// Helpers / 輔助函數
// ---------------------------------------------------------------------------

/// Resolve config file path from env or argument.
/// 從環境變量或參數解析配置文件路徑。
fn resolve_config_path(explicit: Option<&str>) -> PathBuf {
    if let Some(p) = explicit {
        return PathBuf::from(p);
    }
    if let Ok(p) = std::env::var("OPENCLAW_ENGINE_CONFIG") {
        return PathBuf::from(p);
    }
    PathBuf::from("./engine.toml")
}

/// Load and parse TOML from file. Returns default config if file doesn't exist.
/// 從文件加載並解析 TOML。文件不存在時返回預設配置。
fn load_from_file(path: &Path) -> Result<RuntimeConfig, ConfigError> {
    if !path.exists() {
        info!(
            path = %path.display(),
            "config file not found, using defaults / 配置文件未找到，使用預設值"
        );
        return Ok(RuntimeConfig::default());
    }
    let content = std::fs::read_to_string(path).map_err(|e| ConfigError::ReadFile {
        path: path.display().to_string(),
        source: e,
    })?;
    let config: RuntimeConfig = toml::from_str(&content)?;
    Ok(config)
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    #[test]
    fn test_default_config_valid() {
        let cfg = RuntimeConfig::default();
        assert!(cfg.validate().is_ok());
        assert_eq!(cfg.max_open_positions, 25);
        assert_eq!(cfg.ws_url, "wss://stream.bybit.com/v5/public/linear");
    }

    #[test]
    fn test_invalid_positions_zero() {
        let mut cfg = RuntimeConfig::default();
        cfg.max_open_positions = 0;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_invalid_stop_loss_negative() {
        let mut cfg = RuntimeConfig::default();
        cfg.max_stop_loss_pct = -1.0;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_invalid_stop_loss_over_100() {
        let mut cfg = RuntimeConfig::default();
        cfg.max_stop_loss_pct = 101.0;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_toml_parse_full() {
        let toml_str = r#"
ws_url = "wss://example.com/ws"
reconnect_delay_ms = 5000
heartbeat_interval_ms = 15000
ipc_socket_path = "/tmp/test.sock"
state_push_interval_ms = 2000
max_stop_loss_pct = 3.0
max_take_profit_pct = 10.0
max_open_positions = 15
max_total_exposure_pct = 80.0
attention_dormant_ms = 120000
attention_low_ms = 60000
attention_medium_ms = 20000
attention_high_ms = 3000
attention_critical_ms = 500
"#;
        let cfg: RuntimeConfig = toml::from_str(toml_str).unwrap();
        assert_eq!(cfg.ws_url, "wss://example.com/ws");
        assert_eq!(cfg.reconnect_delay_ms, 5000);
        assert_eq!(cfg.max_open_positions, 15);
        assert_eq!(cfg.attention_critical_ms, 500);
        assert!(cfg.validate().is_ok());
    }

    #[test]
    fn test_toml_parse_partial_uses_defaults() {
        let toml_str = r#"
max_open_positions = 10
"#;
        let cfg: RuntimeConfig = toml::from_str(toml_str).unwrap();
        assert_eq!(cfg.max_open_positions, 10);
        assert_eq!(cfg.ws_url, "wss://stream.bybit.com/v5/public/linear");
        assert_eq!(cfg.heartbeat_interval_ms, 20000);
        assert!(cfg.validate().is_ok());
    }

    #[test]
    fn test_config_manager_load_missing_file() {
        // Should fall back to defaults / 應回退到預設值
        let mgr = ConfigManager::load(Some("/tmp/nonexistent_openclaw_test.toml")).unwrap();
        let cfg = mgr.get();
        assert_eq!(cfg.max_open_positions, 25);
    }

    #[test]
    fn test_config_manager_load_and_reload() {
        let dir = std::env::temp_dir().join("openclaw_config_test");
        let _ = std::fs::create_dir_all(&dir);
        let path = dir.join("engine_test.toml");

        // Write initial config / 寫入初始配置
        {
            let mut f = std::fs::File::create(&path).unwrap();
            writeln!(f, "max_open_positions = 10").unwrap();
            writeln!(f, "max_stop_loss_pct = 3.0").unwrap();
        }

        let mgr = ConfigManager::load(Some(path.to_str().unwrap())).unwrap();
        assert_eq!(mgr.get().max_open_positions, 10);

        // Update config file / 更新配置文件
        {
            let mut f = std::fs::File::create(&path).unwrap();
            writeln!(f, "max_open_positions = 20").unwrap();
            writeln!(f, "max_stop_loss_pct = 4.0").unwrap();
        }

        mgr.reload().unwrap();
        assert_eq!(mgr.get().max_open_positions, 20);
        assert!((mgr.get().max_stop_loss_pct - 4.0).abs() < f64::EPSILON);

        // Cleanup / 清理
        let _ = std::fs::remove_file(&path);
        let _ = std::fs::remove_dir(&dir);
    }
}
