//! Event consumer types — shared data types for the event consumer module.
//! 事件消費者類型 — 事件消費者模組的共享資料類型。
//!
//! MODULE_NOTE (EN): Defines EventConsumerDeps bundle, ExchangeEvent enum,
//!   PendingOrder tracking struct, and module constants (SYMBOLS, STATUS_INTERVAL_SECS).
//! MODULE_NOTE (中): 定義 EventConsumerDeps 依賴集合、ExchangeEvent 枚舉、
//!   PendingOrder 追蹤結構體、及模組常量（SYMBOLS、STATUS_INTERVAL_SECS）。

use crate::bybit_private_ws::{ExecutionUpdate, OrderUpdate};
use crate::bybit_rest_client::BybitRestClient;
use crate::config::ConfigManager;
use crate::instrument_info::InstrumentInfoCache;
use crate::tick_pipeline::{PipelineCommand, PipelineKind};
use openclaw_types::PriceEvent;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;

// 3E D20: Fan-out sends Arc-wrapped events to avoid cloning HashMap metadata.
// 3E D20：扇出發送 Arc 包裝事件，避免深拷貝 HashMap metadata。

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
    /// 3E-2a: Pipeline identity — determines governance profile, DB prefix, exchange binding.
    /// 管線身份 — 決定治理檔案、DB 前綴、交易所綁定。
    pub pipeline_kind: PipelineKind,
    pub event_rx: mpsc::Receiver<Arc<PriceEvent>>,
    pub config: Arc<ConfigManager>,
    pub cancel: CancellationToken,
    pub initial_balance: f64,
    /// When trading_mode=Live, paper mode should mirror the Demo account balance
    /// (wBu0 slot), not the Live/GBR balance. If Some, paper mode is pre-initialized
    /// with this value at startup. None = use initial_balance (normal case).
    /// Live 模式下 paper 模式應映射 Demo 帳號（wBu0 槽），而非 Live/GBR 餘額。
    /// 若 Some，啟動時以此值預初始化 paper 模式。None = 使用 initial_balance（一般情況）。
    pub paper_initial_balance: Option<f64>,
    pub taker_fee_rate: Option<f64>,
    /// Live AccountManager for per-symbol fee lookups (Bybit `/v5/account/fee-rate`).
    /// 用於 per-symbol 動態費率查詢的 AccountManager。
    pub account_manager: Option<Arc<crate::account_manager::AccountManager>>,
    pub instruments: Option<Arc<InstrumentInfoCache>>,
    pub bootstrap_client: Option<Arc<BybitRestClient>>,
    pub shared_client: Option<Arc<BybitRestClient>>,
    pub bybit_balance: Option<Arc<std::sync::RwLock<Option<f64>>>>,
    pub api_pnl: Option<Arc<std::sync::RwLock<HashMap<String, f64>>>>,
    /// Paper session command receiver — IPC sends Pause/Resume/CloseAll/Reset.
    /// 紙盤 session 命令接收端 — IPC 發送 Pause/Resume/CloseAll/Reset。
    pub pipeline_cmd_rx: Option<mpsc::UnboundedReceiver<PipelineCommand>>,
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
    /// Phase 4 W-3: Optional LinUCB runtime for read-only arm selection at the
    /// DecisionContextMsg producer site.
    /// Phase 4 W-3：可選的 LinUCB 運行時，用於 DecisionContextMsg producer
    /// 站點唯讀 arm 選擇。
    pub linucb_runtime: Option<Arc<crate::linucb::LinUcbRuntime>>,
    /// Phase 4 W-4: Optional shared news context snapshot read by the
    /// DecisionContextMsg producer site (news_severity + hours_since_last_major_news).
    /// Phase 4 W-4：可選的共享新聞 context 快照，由 DecisionContextMsg producer
    /// 站點讀取（news_severity + hours_since_last_major_news）。
    pub news_snapshot: Option<Arc<crate::news::NewsContextSnapshot>>,
    /// ARCH-RC1 1C-2-B: live RiskConfig store handle (hot-reloadable).
    /// When Some, TickPipeline syncs intent_processor.risk_config on each tick
    /// if the store version bumps (IPC patch applied).
    /// ARCH-RC1 1C-2-B：live RiskConfig store 控制代碼（可熱重載）。
    pub risk_store:
        Option<Arc<crate::config::ConfigStore<crate::config::RiskConfig>>>,
    /// ARCH-RC1 1C-2-B: live BudgetConfig store handle — hot-path reads
    /// attention_tax.cost_edge_max_ratio per tick for the cost-edge check.
    /// ARCH-RC1 1C-2-B：live BudgetConfig store 控制代碼。
    pub budget_store:
        Option<Arc<crate::config::ConfigStore<crate::config::BudgetConfig>>>,
    /// Scanner D1: Active symbol registry — read-only ref so event consumer can
    /// call pipeline.add_symbol/remove_symbol when scanner updates the universe.
    /// 掃描器 D1：活躍交易對注冊表 — 唯讀引用，供 event consumer 在掃描器更新
    /// 品類時調用 pipeline.add_symbol/remove_symbol。
    pub symbol_registry: Option<Arc<crate::scanner::registry::SymbolRegistry>>,
    /// Scanner D1: ScannerConfig store for reading scheduling params at startup.
    /// 掃描器 D1：ScannerConfig store，供啟動時讀取調度參數。
    pub scanner_store:
        Option<Arc<crate::config::ConfigStore<crate::scanner::ScannerConfig>>>,
    /// ARCH-RC1 1C-4 B1: V014 audit pool — used at startup to restore the
    /// governor de-escalation cooldown timestamp (24h window) so a restart
    /// during an active cooldown does not silently reset the guard.
    /// Fail-soft: when None or query fails, cooldown starts fresh and a
    /// warning is logged. Other multi-layer guards (reason_code whitelist,
    /// step rule, 5-min hold, CB/MR lockout) remain in force.
    /// ARCH-RC1 1C-4 B1：V014 審計 pool — 啟動時用來還原 governor 降級
    /// 24h 冷卻時間戳，避免重啟期間冷卻被靜默重置。fail-soft：None 或
    /// 查詢失敗時冷卻從零開始並記 warn，其他多層守衛繼續生效。
    pub audit_pool: Option<sqlx::PgPool>,
    /// Phase 6: Shared atomic for reconciler to read current risk level.
    /// Event consumer writes governor level here after every command handler call.
    /// Phase 6：共享原子量供對帳器讀取當前風控級別。
    pub shared_risk_level: Option<Arc<std::sync::atomic::AtomicU8>>,
    /// 3E-5: Whether this is the primary pipeline (writes compat pipeline_snapshot.json).
    /// 3E-5：是否為主管線（寫入兼容的 pipeline_snapshot.json）。
    pub is_primary: bool,
}
