//! Event consumer types — shared data types for the event consumer module.
//! 事件消費者類型 — 事件消費者模組的共享資料類型。
//!
//! MODULE_NOTE (EN): Defines EventConsumerDeps bundle, ExchangeEvent enum,
//!   PendingOrder tracking struct, and module constants (SYMBOLS, STATUS_INTERVAL_SECS).
//! MODULE_NOTE (中): 定義 EventConsumerDeps 依賴集合、ExchangeEvent 枚舉、
//!   PendingOrder 追蹤結構體、及模組常量（SYMBOLS、STATUS_INTERVAL_SECS）。

use crate::bybit_private_ws::{ExecutionUpdate, OrderUpdate, PositionUpdate};
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
    /// B-1 Phase 2: Runtime position delta from the exchange — paper_state should
    /// upsert/remove the entry to stay in sync with what Bybit thinks we hold.
    /// B-1 Phase 2：交易所推送的運行時持倉變更，paper_state 應 upsert/移除以保持同步。
    PositionUpdate(PositionUpdate),
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
    // BLOCKER-6 / D12: parking_lot::RwLock is non-poisoning so a panic in
    // one pipeline's WS callback cannot cascade-poison other pipelines'
    // readers (cross-engine isolation).
    // BLOCKER-6 / D12：parking_lot::RwLock 不會中毒，單一管線 WS 回調 panic
    // 不會把其他管線的讀取者一併 poison（跨引擎隔離）。
    pub bybit_balance: Option<Arc<parking_lot::RwLock<Option<f64>>>>,
    pub api_pnl: Option<Arc<parking_lot::RwLock<HashMap<String, f64>>>>,
    /// Paper session command receiver — IPC sends Pause/Resume/CloseAll/Reset.
    /// 紙盤 session 命令接收端 — IPC 發送 Pause/Resume/CloseAll/Reset。
    pub pipeline_cmd_rx: Option<mpsc::UnboundedReceiver<PipelineCommand>>,
    /// EDGE-P3-1 A4: Pipeline command sender cloned for IntentProcessor's
    /// `EmitShadowFill` dispatch (spec §7.3 ε-greedy paper exploration). Passing
    /// this Some() closes the fail-soft drop branch; None keeps shadow fills
    /// silently discarded. Paper is the only engine that needs this wired, but
    /// Demo/Live can pass their own sender too — the ε-greedy branch is
    /// `pipeline_kind != Paper` short-circuited inside IntentProcessor.
    /// EDGE-P3-1 A4：給 IntentProcessor 用來發送 `EmitShadowFill` 的 PipelineCommand
    /// 發送端（spec §7.3 ε-greedy paper 探索）；Some 時關閉 fail-soft 丟棄分支，
    /// None 時 shadow fill 仍被靜默丟棄。僅 Paper 真正使用，但 Demo/Live 傳入
    /// 無副作用（ε-greedy 分支在 IntentProcessor 內以 pipeline_kind 短路）。
    pub pipeline_cmd_tx: Option<mpsc::UnboundedSender<PipelineCommand>>,
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
    /// B-1 Phase 2: Existing exchange positions captured by build_exchange_pipeline,
    /// used to seed paper_state before the first market tick. Empty Vec on cold
    /// accounts, REST failure, or paper-only pipelines.
    /// B-1 Phase 2：build_exchange_pipeline 抓取的既存持倉，用於在首個市場 tick
    /// 前 seed paper_state。冷帳戶、REST 失敗或純 paper 管線時為空 Vec。
    pub seed_positions: Vec<(String, bool, f64, f64, u64)>,
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
    /// MAJOR-2: Startup barrier — pipeline sends () after initialization completes,
    /// letting the fan-out task know it's safe to start delivering ticks.
    /// MAJOR-2：啟動屏障 — 管線初始化完成後發送 ()，通知扇出任務可以開始分發 tick。
    pub ready_tx: Option<tokio::sync::oneshot::Sender<()>>,
    /// BLOCKER-3 D15: Shared cross-engine global exposure (USDT × 100 as AtomicU64).
    /// Only exchange pipelines (Demo/Live) should write; Paper is excluded.
    /// BLOCKER-3 D15：跨引擎全局曝險原子量（USDT × 100），僅交易所管線更新。
    pub global_exposure_usdt: Option<Arc<std::sync::atomic::AtomicU64>>,
    /// BLOCKER-2 D6: Cross-engine event sender — broadcast crash/CB events to peers.
    /// BLOCKER-2 D6：跨引擎事件發送端 — 向對等管線廣播崩潰/熔斷事件。
    pub cross_engine_tx: Option<tokio::sync::broadcast::Sender<crate::tick_pipeline::EngineEvent>>,
    /// BLOCKER-2 D6: Cross-engine event receiver — react to peer crash/CB events.
    /// BLOCKER-2 D6：跨引擎事件接收端 — 對對等管線崩潰/熔斷事件作出反應。
    pub cross_engine_rx: Option<tokio::sync::broadcast::Receiver<crate::tick_pipeline::EngineEvent>>,
    /// BLOCKER-2 D6: Per-pipeline health atomic (written by this pipeline, read by others).
    /// BLOCKER-2 D6：管線健康原子量（本管線寫入，其他管線讀取）。
    pub pipeline_health: Option<Arc<std::sync::atomic::AtomicU8>>,
    /// ENGINE-HEAL-FIX-PHASE1 R1: Canary writer handle — non-blocking try_send keeps
    /// the JSONL dump off the event loop hot path. `disabled()` clone when the feature
    /// is off, in which case `is_enabled()` is false and producers skip record build.
    /// ENGINE-HEAL-FIX-PHASE1 R1：灰度寫入器控制代碼 — 非阻塞 try_send 將 JSONL
    /// 寫盤移出事件循環熱路徑。功能關閉時為 `disabled()` clone，producer 跳過記錄構建。
    pub canary_handle: crate::canary_writer::CanaryWriterHandle,
    /// EDGE-P3-1 Phase B #1: Per-engine EdgePredictorStore handle. `None` keeps the
    /// §7.3 gate `store = None` short-circuit path (→ legacy shrinkage), matching the
    /// pre-wiring behaviour. Bootstrap in `main.rs` passes `Some(pep.<kind>.clone())`
    /// so IPC `SetEdgePredictorShadow` hot-swaps and the gate `load_for()` see the
    /// same Arc. Required for any EdgePredictor activation; `use_edge_predictor=false`
    /// still gates actual consultation.
    /// EDGE-P3-1 Phase B #1：逐引擎 EdgePredictorStore handle。None 時 §7.3 gate
    /// 短路至 legacy shrinkage，符合接線前行為；bootstrap 傳
    /// `Some(pep.<kind>.clone())`，IPC 熱換與 gate load_for 共享同一 Arc。
    pub edge_predictor_store: Option<Arc<crate::edge_predictor::EdgePredictorStore>>,
    /// ORPHAN-ADOPT-1 FUP: per-engine `(symbol → is_long)` mirror of PaperState
    /// positions. Constructed in `main.rs` before the reconciler spawn so the
    /// reconciler's `OrphanHandlerConfig` and this pipeline's `PaperState`
    /// share the same handle. `run_event_consumer` calls
    /// `pipeline.paper_state.set_positions_mirror(mirror)` after TickPipeline
    /// construction; subsequent position mutations keep it in sync and the
    /// reconciler suppresses its own fresh-fill Orphan verdicts by reading it.
    /// `None` disables the suppression (reconciler falls back to Phase 1
    /// close semantics — matches pre-fix behavior).
    /// ORPHAN-ADOPT-1 FUP：每引擎 PaperState `(symbol → is_long)` 鏡像。
    /// main.rs 在 reconciler spawn 前建立，與對帳器的 OrphanHandlerConfig
    /// 共享同一 handle。run_event_consumer 構造 TickPipeline 後呼叫
    /// `paper_state.set_positions_mirror(mirror)`，對帳器讀鏡像抑制
    /// 「自家剛開倉」的假 Orphan。None 時停用抑制（回退 Phase 1 行為）。
    pub positions_mirror:
        Option<Arc<parking_lot::RwLock<HashMap<String, bool>>>>,
}
