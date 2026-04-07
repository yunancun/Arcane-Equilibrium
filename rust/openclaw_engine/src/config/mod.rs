//! Engine runtime configuration + ARCH-RC1 unified Config system.
//! 引擎運行時配置 + ARCH-RC1 統一 Config 系統。
//!
//! MODULE_NOTE (EN): Module root containing both the legacy `RuntimeConfig`
//!   (engine bootstrap params loaded from engine.toml — ws_url, db, ipc_socket,
//!   trading_mode, etc.) AND the new ARCH-RC1 unified Config types added in 1B:
//!   `RiskConfig` (1 source of truth for ALL risk decisions),
//!   `LearningConfig` (ML/RL/Agent behaviour switches),
//!   `BudgetConfig` (AI cost limits + attention tax). The new Configs are
//!   wrapped by the generic `ConfigStore<T>` (lock-free reads via ArcSwap, all-or-nothing
//!   patches via mutex). RuntimeConfig still owns the engine bootstrap fields;
//!   risk/leverage/drawdown duplication will be removed in Session 1C when call
//!   sites migrate to the new Configs.
//! MODULE_NOTE (中): 模組根，包含既有 `RuntimeConfig`（從 engine.toml 載入的
//!   引擎啟動參數 —— ws_url、db、ipc_socket、trading_mode 等）以及 1B 新增的
//!   ARCH-RC1 統一 Config 型別：`RiskConfig`（所有風控決策的單一真相來源）、
//!   `LearningConfig`（ML/RL/Agent 行為開關）、`BudgetConfig`（AI 成本上限 +
//!   注意力稅）。新 Config 透過泛型 `ConfigStore<T>` 包裹（ArcSwap 無鎖讀、
//!   mutex 序列化的 all-or-nothing patch）。RuntimeConfig 仍持有引擎啟動欄位；
//!   風控/槓桿/回撤的重複欄位將在 Session 1C 由 call site 遷移後移除。

pub mod budget_config;
pub mod io;
pub mod learning_config;
pub mod risk_config;
pub mod store;

pub use budget_config::BudgetConfig;
pub use io::{load_toml_or_default, save_toml};
pub use learning_config::LearningConfig;
pub use risk_config::RiskConfig;
pub use store::{ConfigStore, PatchOutcome, PatchSource};

use arc_swap::ArcSwap;
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use thiserror::Error;
use tracing::{info, warn};

// ---------------------------------------------------------------------------
// TradingMode — EXT-1 Exchange-as-Truth / 交易所即真相模式
// ---------------------------------------------------------------------------

/// Trading execution mode (cold param — requires restart).
/// 交易執行模式（冷參數 — 需重啟）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum TradingMode {
    /// Local paper simulation (default) / 本地紙盤模擬（預設）
    #[default]
    PaperOnly,
    /// Exchange-as-Truth: orders placed on exchange, fills confirmed via WS
    /// 交易所即真相：訂單送交交易所，成交經 WS 確認
    Exchange,
}

impl std::fmt::Display for TradingMode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            TradingMode::PaperOnly => write!(f, "paper_only"),
            TradingMode::Exchange => write!(f, "exchange"),
        }
    }
}

fn default_trading_mode() -> TradingMode {
    TradingMode::PaperOnly
}

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

/// Engine bootstrap configuration (renamed from `RuntimeConfig` in 1C-1 Batch 5).
/// 引擎啟動配置（1C-1 Batch 5 從 `RuntimeConfig` 改名）。
///
/// Holds ONLY connection / bootstrap / integration parameters from engine.toml.
/// All risk, leverage, drawdown, sizing, and ML parameters are owned by the
/// ARCH-RC1 unified Configs (`RiskConfig`, `LearningConfig`, `BudgetConfig`).
///
/// 只持有連線/啟動/整合參數。所有風控、槓桿、回撤、sizing、ML 參數由
/// ARCH-RC1 統一 Config (`RiskConfig` / `LearningConfig` / `BudgetConfig`) 擁有。
///
/// Cold params (require restart): ws_url, reconnect_delay_ms,
/// heartbeat_interval_ms, ipc_socket_path, state_push_interval_ms, trading_mode.
/// 冷參數（需重啟）：ws_url / reconnect / heartbeat / ipc_socket / state_push / trading_mode。
#[derive(Debug, Clone, Deserialize)]
pub struct EngineBootstrap {
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

    // -- EXT-1: Trading mode (cold param) / 交易模式（冷參數） --
    /// Trading execution mode: paper_only (local sim) or exchange (exchange-as-truth).
    /// 交易執行模式：paper_only（本地模擬）或 exchange（交易所即真相）。
    #[serde(default = "default_trading_mode")]
    pub trading_mode: TradingMode,

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
    std::env::var("OPENCLAW_IPC_SOCKET").unwrap_or_else(|_| "/tmp/openclaw/engine.sock".into())
}
fn default_state_push_interval_ms() -> u64 {
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

impl Default for EngineBootstrap {
    fn default() -> Self {
        Self {
            ws_url: default_ws_url(),
            reconnect_delay_ms: default_reconnect_delay_ms(),
            heartbeat_interval_ms: default_heartbeat_interval_ms(),
            ipc_socket_path: default_ipc_socket_path(),
            state_push_interval_ms: default_state_push_interval_ms(),
            dcp_enabled: default_true(),
            dcp_time_window: default_dcp_time_window(),
            auto_add_margin: default_true(),
            balance_mode: default_balance_mode(),
            server_side_stops: default_true(),
            enable_extended_ws: default_true(),
            shadow_orders: true,
            kline_bootstrap: default_true(),
            trading_mode: TradingMode::PaperOnly,
            database: crate::database::DatabaseConfig::default(),
        }
    }
}

impl EngineBootstrap {
    /// Validate bootstrap values (risk-related validation lives in RiskConfig).
    /// 驗證啟動參數（風控相關驗證已遷移到 RiskConfig）。
    pub fn validate(&self) -> Result<(), ConfigError> {
        if self.reconnect_delay_ms == 0 {
            return Err(ConfigError::Validation(
                "reconnect_delay_ms must be > 0".into(),
            ));
        }
        if self.heartbeat_interval_ms == 0 {
            return Err(ConfigError::Validation(
                "heartbeat_interval_ms must be > 0".into(),
            ));
        }
        if self.ipc_socket_path.is_empty() {
            return Err(ConfigError::Validation(
                "ipc_socket_path must not be empty".into(),
            ));
        }
        Ok(())
    }
}

/// Backwards-compat alias during the 1C-1 → 1C-2 transition so that external
/// callers importing `config::RuntimeConfig` keep compiling. Remove in 1C-2
/// once all imports are updated.
/// 1C-1 → 1C-2 過渡期的向後相容別名；1C-2 所有 import 更新後移除。
#[deprecated(note = "Renamed to EngineBootstrap in ARCH-RC1 1C-1 Batch 5; update imports.")]
pub type RuntimeConfig = EngineBootstrap;

// ---------------------------------------------------------------------------
// ConfigManager — ArcSwap-based hot reload / 基於 ArcSwap 的熱加載管理器
// ---------------------------------------------------------------------------

/// Atomic config manager using ArcSwap for zero-lock reads.
/// 使用 ArcSwap 的原子配置管理器，實現零鎖讀取。
pub struct ConfigManager {
    inner: ArcSwap<EngineBootstrap>,
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
    pub fn get(&self) -> Arc<EngineBootstrap> {
        self.inner.load_full()
    }

    /// Hot-reload config from file. Only hot params take effect.
    /// 從文件熱加載配置。只有熱參數生效。
    pub fn reload(&self) -> Result<(), ConfigError> {
        let mut new_config = load_from_file(&self.file_path)?;
        new_config.validate()?;

        let old = self.inner.load_full();

        // Warn if cold params changed (they won't take effect) / 冷參數變更警告
        if old.ws_url != new_config.ws_url {
            warn!(
                "ws_url changed but is cold — requires restart / ws_url 已變更但為冷參數，需重啟"
            );
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
        // SEC-1: Preserve cold params from running config (prevent accidental hot-switch)
        // SEC-1：保留運行中配置的冷參數（防止意外熱切換）
        if old.trading_mode != new_config.trading_mode {
            warn!(
                old = %old.trading_mode, new = %new_config.trading_mode,
                "trading_mode changed but is cold — preserving old value, requires restart"
            );
            new_config.trading_mode = old.trading_mode;
        }
        if old.ws_url != new_config.ws_url {
            new_config.ws_url = old.ws_url.clone();
        }
        if old.reconnect_delay_ms != new_config.reconnect_delay_ms {
            new_config.reconnect_delay_ms = old.reconnect_delay_ms;
        }
        if old.heartbeat_interval_ms != new_config.heartbeat_interval_ms {
            new_config.heartbeat_interval_ms = old.heartbeat_interval_ms;
        }
        if old.ipc_socket_path != new_config.ipc_socket_path {
            new_config.ipc_socket_path = old.ipc_socket_path.clone();
        }
        if old.state_push_interval_ms != new_config.state_push_interval_ms {
            new_config.state_push_interval_ms = old.state_push_interval_ms;
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
fn load_from_file(path: &Path) -> Result<EngineBootstrap, ConfigError> {
    if !path.exists() {
        info!(
            path = %path.display(),
            "config file not found, using defaults / 配置文件未找到，使用預設值"
        );
        return Ok(EngineBootstrap::default());
    }
    let content = std::fs::read_to_string(path).map_err(|e| ConfigError::ReadFile {
        path: path.display().to_string(),
        source: e,
    })?;
    let config: EngineBootstrap = toml::from_str(&content)?;
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
    fn test_default_bootstrap_valid() {
        let cfg = EngineBootstrap::default();
        assert!(cfg.validate().is_ok());
        assert_eq!(cfg.ws_url, "wss://stream.bybit.com/v5/public/linear");
        assert_eq!(cfg.trading_mode, TradingMode::PaperOnly);
    }

    #[test]
    fn test_invalid_reconnect_delay_zero() {
        let mut cfg = EngineBootstrap::default();
        cfg.reconnect_delay_ms = 0;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn test_invalid_ipc_socket_empty() {
        let mut cfg = EngineBootstrap::default();
        cfg.ipc_socket_path = String::new();
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
"#;
        let cfg: EngineBootstrap = toml::from_str(toml_str).unwrap();
        assert_eq!(cfg.ws_url, "wss://example.com/ws");
        assert_eq!(cfg.reconnect_delay_ms, 5000);
        assert_eq!(cfg.heartbeat_interval_ms, 15000);
        assert!(cfg.validate().is_ok());
    }

    #[test]
    fn test_toml_parse_partial_uses_defaults() {
        let toml_str = r#"
heartbeat_interval_ms = 30000
"#;
        let cfg: EngineBootstrap = toml::from_str(toml_str).unwrap();
        assert_eq!(cfg.heartbeat_interval_ms, 30000);
        assert_eq!(cfg.ws_url, "wss://stream.bybit.com/v5/public/linear");
        assert!(cfg.validate().is_ok());
    }

    #[test]
    fn test_config_manager_load_missing_file() {
        // Should fall back to defaults / 應回退到預設值
        let mgr = ConfigManager::load(Some("/tmp/nonexistent_openclaw_test.toml")).unwrap();
        let cfg = mgr.get();
        assert_eq!(cfg.ws_url, "wss://stream.bybit.com/v5/public/linear");
    }

    #[test]
    fn test_config_manager_load_and_reload() {
        let dir = std::env::temp_dir().join("openclaw_config_test");
        let _ = std::fs::create_dir_all(&dir);
        let path = dir.join("engine_test.toml");

        // Write initial config / 寫入初始配置
        {
            let mut f = std::fs::File::create(&path).unwrap();
            writeln!(f, "heartbeat_interval_ms = 10000").unwrap();
        }

        let mgr = ConfigManager::load(Some(path.to_str().unwrap())).unwrap();
        assert_eq!(mgr.get().heartbeat_interval_ms, 10000);

        // Update config file / 更新配置文件
        {
            let mut f = std::fs::File::create(&path).unwrap();
            writeln!(f, "heartbeat_interval_ms = 25000").unwrap();
        }

        mgr.reload().unwrap();
        // heartbeat_interval_ms is cold → preserved from original load
        assert_eq!(mgr.get().heartbeat_interval_ms, 10000);

        // Cleanup / 清理
        let _ = std::fs::remove_file(&path);
        let _ = std::fs::remove_dir(&dir);
    }
}
