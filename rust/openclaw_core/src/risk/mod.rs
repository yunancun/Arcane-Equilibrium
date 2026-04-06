//! RiskManager — Core hot-path risk calculations
//! RiskManager — 核心熱路徑風控計算
//!
//! MODULE_NOTE (中文):
//!   從 Python RiskManager（1633 行）移植核心風控計算邏輯。
//!   只包含在交易熱路徑上運行的計算：
//!   - 動態止損（ATR 自適應 + 反聚集偏移 + regime 乘數）
//!   - Tick 級持倉風控檢查（8 項優先級排序）
//!   - 訂單准入檢查（持倉/曝險/槓桿/日損限制）
//!   - 價格歷史追蹤器（ATR 計算 + 尖峰偵測）
//!
//!   GUI 端點、持久化、變更審計日誌保留在 Python 端。
//!
//! MODULE_NOTE (English):
//!   Port of core risk calculations from Python RiskManager (1633 lines).
//!   Only includes computations on the trading hot path:
//!   - Dynamic stop-loss (ATR-adaptive + anti-cluster offset + regime multipliers)
//!   - Tick-level position risk checks (8 items, priority-ordered)
//!   - Order admission check (position/exposure/leverage/daily-loss limits)
//!   - Price history tracker (ATR computation + spike detection)
//!
//!   GUI endpoints, persistence, and change audit log stay in Python.

mod checks;
mod config;
mod price_tracker;
mod stops;

pub use checks::{check_order_allowed, check_position_on_tick, PositionCheck, RiskAction};
pub use config::{regime_multipliers, RegimeMultipliers, RiskManagerConfig};
pub use price_tracker::{PriceHistoryTracker, SpikeInfo};
pub use stops::{anti_cluster_offset, compute_dynamic_stop_pct};
