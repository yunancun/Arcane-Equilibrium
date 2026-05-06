//! Rust market scanner — dynamic symbol selection for the trading universe.
//! Rust 市場掃描器 — 交易品類的動態交易對選擇。
//!
//! MODULE_NOTE (EN): Replaces the disconnected Python market_scanner.py.
//!   Runs as a background tokio task inside the engine, polling Bybit's
//!   /v5/market/tickers every 30 minutes and updating the active symbol set.
//!   BTC and ETH are always pinned; remaining slots are filled by fitness score.
//! MODULE_NOTE (中): 替換已斷開連接的 Python market_scanner.py。
//!   在引擎內部作為後台 tokio 任務運行，每 30 分鐘輪詢 Bybit 的
//!   /v5/market/tickers 並更新活躍交易對集合。
//!   BTC 和 ETH 始終固定；其餘槽位由適配評分填充。

pub mod config;
pub mod market_judgment;
pub mod opportunity;
pub mod registry;
pub mod runner;
pub mod scorer;
pub mod sectors;
pub mod strategy_policy;
pub mod types;

pub use config::ScannerConfig;
pub use strategy_policy::ScannerStrategyPolicyStores;
pub use types::{ChurnState, ScanResult, ScoredSymbol, StrategyCategory};
