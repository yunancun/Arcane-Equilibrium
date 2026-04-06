//! Event consumer types — shared data types for the event consumer module.
//! 事件消費者類型 — 事件消費者模組的共享資料類型。

use crate::bybit_private_ws::{ExecutionUpdate, OrderUpdate};
use crate::bybit_rest_client::BybitRestClient;
use crate::config::ConfigManager;
use crate::instrument_info::InstrumentInfoCache;
use crate::tick_pipeline::PaperSessionCommand;
use openclaw_types::PriceEvent;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;

/// Symbols tracked by the engine / 引擎追蹤的交易對
pub const SYMBOLS: &[&str] = &["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"];

/// Status report interval (seconds) / 狀態報告間隔（秒）
pub const STATUS_INTERVAL_SECS: u64 = 30;

/// EXT-1: Exchange event forwarded from ExecutionListener to event consumer.
/// EXT-1：從執行監聯器轉發到事件消費者的交易所事件。
#[derive(Debug)]
pub enum ExchangeEvent {
    /// A fill/execution confirmed by the exchange / 交易所確認的成交
    Fill(ExecutionUpdate),
    /// An order status update from the exchange / 交易所的訂單狀態更新
    OrderUpdate(OrderUpdate),
    /// DCP triggered — exchange auto-cancelled orders / DCP 觸發 — 交易所自動取消訂單
    DcpTriggered,
    /// Private WS disconnected / 私有 WS 斷連
    Disconnected,
}

/// EXT-1: Pending order tracked in exchange mode, waiting for exchange confirmation.
/// EXT-1：交易所模式中追蹤的待處理訂單，等待交易所確認。
#[derive(Debug, Clone)]
pub struct PendingOrder {
    /// Client-assigned order link ID / 客戶端分配的訂單連結 ID
    pub order_link_id: String,
    /// Trading symbol / 交易對
    pub symbol: String,
    /// Long direction / 多方向
    pub is_long: bool,
    /// Requested quantity / 請求數量
    pub qty: f64,
    /// Strategy name / 策略名稱
    pub strategy: String,
    /// Timestamp when sent / 發送時間戳
    pub sent_ts_ms: u64,
    /// Cumulative filled quantity / 累計成交數量
    pub cum_filled_qty: f64,
    /// Whether this is a close order / 是否為平倉訂單
    pub is_close: bool,
}

/// Dependencies bundle for the event consumer (W1 fix: avoids 9+ parameter function).
/// 事件消費者依賴集合（W1 修復：避免 9+ 參數的函數）。
pub struct EventConsumerDeps {
    pub event_rx: mpsc::Receiver<PriceEvent>,
    pub config: Arc<ConfigManager>,
    pub cancel: CancellationToken,
    pub initial_balance: f64,
    pub taker_fee_rate: Option<f64>,
    pub instruments: Option<Arc<InstrumentInfoCache>>,
    pub bootstrap_client: Option<Arc<BybitRestClient>>,
    pub shared_client: Option<Arc<BybitRestClient>>,
    pub bybit_balance: Option<Arc<std::sync::RwLock<Option<f64>>>>,
    pub api_pnl: Option<Arc<std::sync::RwLock<HashMap<String, f64>>>>,
    /// Paper session command receiver — IPC sends Pause/Resume/CloseAll/Reset.
    /// 紙盤 session 命令接收端 — IPC 發送 Pause/Resume/CloseAll/Reset。
    pub paper_cmd_rx: Option<mpsc::UnboundedReceiver<PaperSessionCommand>>,
    /// Phase 1: Channel to dispatch market data to async PG writer.
    /// Phase 1：市場數據派發通道。
    pub market_data_tx: Option<tokio::sync::mpsc::Sender<crate::database::MarketDataMsg>>,
    /// Phase 1: Channel to dispatch feature snapshots to async PG writer.
    /// Phase 1：特徵快照派發通道。
    pub feature_tx: Option<tokio::sync::mpsc::Sender<crate::feature_collector::FeatureSnapshot>>,
    /// Phase 1 (F-5): Shared last_tick_ms for quality monitor staleness detection.
    /// Phase 1（F-5）：共享 last_tick_ms 用於質量監控器過期檢測。
    pub last_tick_ms: Option<Arc<std::sync::atomic::AtomicU64>>,
    /// Phase 2a: Channel for trading lifecycle events (signals/intents/fills).
    /// Phase 2a：交易生命週期事件通道。
    pub trading_tx: Option<tokio::sync::mpsc::Sender<crate::database::TradingMsg>>,
    /// Phase 2a: Channel for decision context snapshots.
    /// Phase 2a：決策上下文快照通道。
    pub context_tx: Option<tokio::sync::mpsc::Sender<crate::database::DecisionContextMsg>>,
    /// EXT-1: Channel to receive exchange events (fills/order updates) from ExecutionListener.
    /// EXT-1：從執行監聽器接收交易所事件（成交/訂單更新）的通道。
    pub exchange_event_rx: Option<mpsc::UnboundedReceiver<ExchangeEvent>>,
}
