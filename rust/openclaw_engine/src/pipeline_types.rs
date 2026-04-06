//! Pipeline snapshot and status types — extracted from tick_pipeline.rs (RRC-1 E2 fix).
//! 管線快照與狀態類型 — 從 tick_pipeline.rs 提取（RRC-1 E2 修復）。
//!
//! MODULE_NOTE (EN): Data types used by IPC consumers, canary records, and status reports.
//!   Kept separate from tick_pipeline.rs to respect the 1200-line file-size limit.
//! MODULE_NOTE (中): IPC 消費者、灰度記錄和狀態報告使用的數據類型。
//!   從 tick_pipeline.rs 分離以遵守 1200 行文件大小限制。

use openclaw_core::indicators::IndicatorSnapshot;
use openclaw_core::signals::Signal;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use crate::tick_pipeline::TickStats;

/// Pipeline operational status for monitoring.
/// 管線運行狀態，供監控使用。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PipelineStatus {
    pub stats: TickStats,
    pub governance: openclaw_core::governance_core::GovernanceStatus,
    pub positions: usize,
    pub balance: f64,
    pub symbols_tracked: usize,
}

/// Per-tick canary record for Rust vs Python comparison (R07-2).
/// 每 tick 灰度記錄，用於 Rust 與 Python 比較。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CanaryRecord {
    pub schema_version: String,
    pub source: String,
    pub tick_number: u64,
    pub timestamp_ms: u64,
    pub symbol: String,
    pub price: f64,
    pub indicators: Option<IndicatorSnapshot>,
    pub signals: Vec<Signal>,
    pub order_intents: Vec<crate::intent_processor::OrderIntent>,
    pub paper_state: crate::paper_state::PaperStateSnapshot,
    pub stats: TickStats,
    /// Per-tick processing latency in microseconds (for Go/No-Go P50 < 50μs check).
    /// 每 tick 處理延遲（微秒），用於 Go/No-Go P50 < 50μs 驗證。
    pub tick_duration_us: u64,
}

/// Strategy status info for IPC snapshot.
/// 策略狀態信息供 IPC 快照使用。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StrategyInfo {
    /// Strategy name / 策略名稱
    pub name: String,
    /// Whether the strategy is currently active / 策略是否當前活躍
    pub active: bool,
}

/// A timestamped order intent for IPC ring buffer.
/// 帶時間戳的交易意圖，供 IPC 環形緩衝使用。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TimestampedIntent {
    /// Event timestamp in milliseconds / 事件時間戳（毫秒）
    pub timestamp_ms: u64,
    /// The original order intent / 原始交易意圖
    pub intent: crate::intent_processor::OrderIntent,
    /// Result: "submitted" or "rejected:<reason>" / 結果："submitted" 或 "rejected:<原因>"
    pub result: String,
}

/// A timestamped fill record for IPC ring buffer.
/// 帶時間戳的成交記錄，供 IPC 環形緩衝使用。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TimestampedFill {
    /// Event timestamp in milliseconds / 事件時間戳（毫秒）
    pub timestamp_ms: u64,
    /// Trading symbol / 交易對
    pub symbol: String,
    /// Long or short direction / 多空方向
    pub is_long: bool,
    /// Fill quantity / 成交數量
    pub qty: f64,
    /// Fill price / 成交價格
    pub price: f64,
    /// Fee charged / 手續費
    pub fee: f64,
    /// Strategy that generated this fill / 產生此成交的策略
    pub strategy: String,
}

/// Full pipeline snapshot for IPC consumers (R06-A).
/// 完整管線快照供 IPC 消費者使用。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PipelineSnapshot {
    /// Paper trading state / 紙盤交易狀態
    pub paper_state: crate::paper_state::PaperStateSnapshot,
    /// Latest per-symbol prices / 每交易對最新價格
    pub latest_prices: HashMap<String, f64>,
    /// Tick statistics / Tick 統計
    pub stats: TickStats,
    /// Data source discriminator / 數據源標識
    pub source: String,
    /// Paper trading paused flag / 紙盤交易暫停標誌
    #[serde(default)]
    pub paper_paused: bool,
    /// EXT-1: Current trading mode / 當前交易模式
    #[serde(default)]
    pub trading_mode: crate::config::TradingMode,
    /// Per-symbol latest indicator values / 每交易對最新指標值
    pub indicators: HashMap<String, IndicatorSnapshot>,
    /// Recent signals (last 100) / 最近信號（最近 100 個）
    pub signals: Vec<Signal>,
    /// Strategy status list / 策略狀態列表
    pub strategies: Vec<StrategyInfo>,
    /// Recent order intents (last 50) / 最近交易意圖（最近 50 個）
    pub recent_intents: Vec<TimestampedIntent>,
    /// Recent fills (last 50) / 最近成交記錄（最近 50 個）
    pub recent_fills: Vec<TimestampedFill>,
    /// Per-symbol latest completed klines (up to 100 bars, 1m only).
    /// 每交易對最新已完成 K 線（最多 100 根，僅 1m）。
    #[serde(default, skip_serializing_if = "HashMap::is_empty")]
    pub klines: HashMap<String, Vec<openclaw_core::klines::KlineBar>>,
    /// RRC-1: H0 Gate statistics (total checks, blocks, shadow would-block).
    /// RRC-1：H0 門控統計（總檢查次數、阻斷、影子模式本應阻斷）。
    #[serde(default)]
    pub h0_gate_stats: Option<openclaw_core::h0_gate::GateStats>,
    // ─── RRC-1-D1: Risk single source of truth / 風控單一真相源 ───
    /// Stop-loss configuration / 止損配置
    #[serde(default)]
    pub stop_config: Option<openclaw_core::stop_manager::StopConfig>,
    /// Guardian configuration / 守護者配置
    #[serde(default)]
    pub guardian_config: Option<openclaw_core::guardian::GuardianConfig>,
    /// Risk manager configuration (P1 limits + P2 agent params) / 風控管理器配置
    #[serde(default)]
    pub risk_manager_config: Option<openclaw_core::risk::RiskManagerConfig>,
    /// Per-symbol consecutive loss count / 每交易對連續虧損計數
    #[serde(default, skip_serializing_if = "HashMap::is_empty")]
    pub consecutive_losses: HashMap<String, u32>,
    /// Session halted by risk circuit breaker / 風控熔斷暫停會話
    #[serde(default)]
    pub session_halted: bool,
    /// Current daily loss percentage / 當前日損百分比
    #[serde(default)]
    pub daily_loss_pct: f64,
    /// Current session drawdown percentage / 當前會話回撤百分比
    #[serde(default)]
    pub session_drawdown_pct: f64,
}
