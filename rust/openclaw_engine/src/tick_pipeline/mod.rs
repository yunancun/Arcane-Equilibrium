//! Tick Pipeline — on_tick 4-step orchestration (R04-1).
//! Tick 管線 — on_tick 4 步編排。
//!
//! MODULE_NOTE (EN): Core tick processing loop. WS event → kline aggregate →
//!   indicator compute → signal evaluate → strategy dispatch → governance →
//!   fill/stop. Sole-owner actor pattern: no locks [V3-PA-1]. Holds all
//!   sub-systems (KlineManager, IndicatorEngine, SignalEngine, Orchestrator,
//!   IntentProcessor, PaperState, StopManager, Governance).
//! MODULE_NOTE (中): 核心 tick 處理循環。WS 事件 → K 線聚合 → 指標計算 →
//!   信號評估 → 策略分派 → 治理 → 成交/止損。獨佔所有者模式：無鎖 [V3-PA-1]。
//!   持有所有子系統（KlineManager、IndicatorEngine、SignalEngine、Orchestrator、
//!   IntentProcessor、PaperState、StopManager、Governance）。

use openclaw_core::{
    governance_core::{GovernanceCore, GovernanceProfile},
    h0_gate::H0Gate,
    indicators::{IndicatorEngine, IndicatorSnapshot},
    klines::KlineManager,
    risk::PriceHistoryTracker,
    signals::{IndicatorInput, Signal, SignalEngine},
};
use crate::risk_checks::RiskAction;
use openclaw_types::{PriceEvent, PriceEventKind};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, VecDeque};
use std::sync::Arc;
use std::time::Instant;
use tracing::{debug, info, warn};

use crate::instrument_info::InstrumentInfoCache;
use crate::intent_processor::IntentProcessor;
use crate::orchestrator::Orchestrator;
use crate::paper_state::PaperState;
use crate::strategies::StrategyAction;

/// Global system operating mode — synced from Python GUI `global_execution_mode_switch`.
/// Controls which engines are allowed to trade. Persisted in TickPipeline.system_mode.
/// 全局系統運行模式 — 從 Python GUI `global_execution_mode_switch` 同步。
/// 控制哪些引擎允許交易。持久化在 TickPipeline.system_mode 中。
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum SystemMode {
    /// Live trading reserved — all engines (paper/demo/live) allowed.
    /// 保留實盤模式 — 所有引擎（paper/demo/live）均允許。
    #[default]
    LiveReserved,
    /// Demo trading reserved — demo + paper allowed, live blocked.
    /// 保留 Demo 模式 — demo + paper 允許，live 封鎖。
    DemoReserved,
    /// Shadow only — paper simulation only; exchange (demo/live) blocked + positions closed.
    /// 影子模式 — 僅 paper 模擬；交易所（demo/live）封鎖並平倉。
    ShadowOnly,
    /// Observe only — all trading engines stopped; scanner + market data continue.
    /// 觀察模式 — 所有交易引擎停止；掃描器 + 市場數據繼續。
    ObserveOnly,
    /// Design only — same as ObserveOnly for the engine (development mode).
    /// 設計模式 — 引擎側等同 ObserveOnly（開發模式）。
    DesignOnly,
}

impl SystemMode {
    /// Parse from Python GUI string values / 從 Python GUI 字符串值解析
    pub fn from_str(s: &str) -> Result<Self, String> {
        match s {
            "live_reserved" => Ok(Self::LiveReserved),
            "demo_reserved" => Ok(Self::DemoReserved),
            "shadow_only" => Ok(Self::ShadowOnly),
            "observe_only" => Ok(Self::ObserveOnly),
            "design_only" => Ok(Self::DesignOnly),
            _ => Err(format!("unknown system_mode: {s}")),
        }
    }

    /// Serialize to string / 序列化為字符串
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::LiveReserved => "live_reserved",
            Self::DemoReserved => "demo_reserved",
            Self::ShadowOnly => "shadow_only",
            Self::ObserveOnly => "observe_only",
            Self::DesignOnly => "design_only",
        }
    }
}

impl std::fmt::Display for SystemMode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

// ---------------------------------------------------------------------------
// PipelineKind — immutable pipeline identity (3E-1)
// ---------------------------------------------------------------------------

/// Immutable pipeline identity — baked in at construction, never changes.
/// Unlike `TradingMode` (which was a mutable global), `PipelineKind` is set once
/// and determines the pipeline's DB prefix, governance profile, and exchange binding.
/// 不可變管線身份 — 構造時固定，永不更改。
/// 與可變全局 `TradingMode` 不同，`PipelineKind` 一次設定，決定 DB 前綴、治理檔案、交易所綁定。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum PipelineKind {
    #[default]
    Paper,
    Demo,
    Live,
}

impl PipelineKind {
    /// DB-canonical engine_mode string: "paper" / "demo" / "live".
    /// DB 標準 engine_mode 字串。
    pub fn db_mode(&self) -> &'static str {
        match self {
            Self::Paper => "paper",
            Self::Demo => "demo",
            Self::Live => "live",
        }
    }

    /// Whether this pipeline connects to a real exchange (Demo or Live).
    /// 此管線是否連接真實交易所（Demo 或 Live）。
    pub fn is_exchange(&self) -> bool {
        matches!(self, Self::Demo | Self::Live)
    }

    /// Derive the governance profile from pipeline identity.
    /// 從管線身份推導治理檔案。
    pub fn governance_profile(&self) -> GovernanceProfile {
        match self {
            Self::Paper => GovernanceProfile::Exploration,
            Self::Demo => GovernanceProfile::Validation,
            Self::Live => GovernanceProfile::Production,
        }
    }
}

impl std::fmt::Display for PipelineKind {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.db_mode())
    }
}

// ---------------------------------------------------------------------------
// BLOCKER-2 D6: Cross-engine event types for crash cascade notification
// 跨引擎事件類型，用於崩潰級聯通知
// ---------------------------------------------------------------------------

/// Cross-engine events broadcast from one pipeline to all others.
/// 從一個管線廣播到所有其他管線的跨引擎事件。
#[derive(Debug, Clone)]
pub enum EngineEvent {
    /// Pipeline panicked or task exited unexpectedly / 管線 panic 或任務異常退出
    Crashed(PipelineKind),
    /// Pipeline's risk governor tripped to CircuitBreaker / 管線風控觸發熔斷
    CircuitBreakerTripped(PipelineKind),
}

/// Per-pipeline health status (stored as AtomicU8 for lock-free reads).
/// 每管線健康狀態（以 AtomicU8 存儲，無鎖讀取）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum PipelineHealth {
    /// Pipeline is running normally / 管線正常運行
    Running = 0,
    /// Pipeline is paused (risk contraction) / 管線已暫停（風控收縮）
    Paused = 1,
    /// Pipeline has crashed or been shut down / 管線已崩潰或關閉
    Down = 2,
}

impl PipelineHealth {
    pub fn from_u8(v: u8) -> Self {
        match v {
            0 => Self::Running,
            1 => Self::Paused,
            _ => Self::Down,
        }
    }
}

// GovernanceProfile is re-exported from openclaw_core::governance_core (3E-1 / D3).
// GovernanceProfile 從 openclaw_core::governance_core 重導出。

// ---------------------------------------------------------------------------
// PipelineCommand — IPC → event consumer → TickPipeline
// ---------------------------------------------------------------------------

/// Pipeline command — IPC → event consumer → TickPipeline.
/// Renamed from PipelineCommand (D22): serves all 3 pipeline kinds.
/// 管線命令 — IPC → 事件消費者 → TickPipeline。
/// 從 PipelineCommand 改名（D22）：服務所有 3 種管線。
#[derive(Debug)]
pub enum PipelineCommand {
    /// Pause strategy dispatch + shadow orders. Prices/indicators/stops continue.
    /// 暫停策略分派+影子訂單。價格/指標/止損繼續。
    Pause,
    /// Resume strategy dispatch + shadow orders.
    /// 恢復策略分派+影子訂單。
    Resume,
    /// Close all open positions at current market prices.
    /// 以當前市場價格平掉所有持倉。
    CloseAll,
    /// Close a single position by symbol at current market price.
    /// Optional hints let the caller supply side/qty for orphan exchange positions
    /// not tracked in paper_state (e.g. GUI manual close of a shadow-only position).
    /// 以當前市場價格平掉指定 symbol 的持倉。
    /// hint_is_long / hint_qty：呼叫方提供的交易所側倉位方向與數量（paper_state
    /// 沒有追蹤的孤兒倉位時使用，例如 GUI 手動平掉 shadow-only 倉位）。
    CloseSymbol {
        symbol: String,
        hint_is_long: Option<bool>,
        hint_qty: Option<f64>,
    },
    /// Reset paper state — clear positions, reset balance.
    /// 重置紙盤狀態 — 清倉、重置餘額。
    Reset { new_balance: f64 },
    /// Phase 3b: Update strategy parameters via JSON (Optuna → Rust).
    /// Phase 3b：通過 JSON 更新策略參數（Optuna → Rust）。
    UpdateStrategyParams {
        strategy_name: String,
        params_json: String,
        response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    },
    /// Phase 3b: Get current strategy parameters as JSON.
    /// Phase 3b：獲取當前策略參數 JSON。
    GetStrategyParams {
        strategy_name: String,
        response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    },
    /// Phase 3b: Get parameter ranges for a strategy (Optuna search space).
    /// Phase 3b：獲取策略參數範圍（Optuna 搜索空間）。
    GetParamRanges {
        strategy_name: String,
        response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    },
    /// RRC-1-E2: Set strategy active/paused by name.
    /// RRC-1-E2：按名稱設置策略活躍/暫停。
    SetStrategyActive {
        strategy_name: String,
        active: bool,
        response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    },
    /// Update risk config at runtime (from GUI/Python/Agent → IPC → Rust).
    /// 運行時更新風控配置（從 GUI/Python/Agent → IPC → Rust）。
    UpdateRiskConfig {
        // StopConfig fields / 止損配置
        hard_stop_pct: Option<f64>,
        trailing_stop_pct: Option<Option<f64>>, // Some(None)=disable, Some(Some(x))=set
        time_stop_hours: Option<Option<f64>>,
        atr_multiplier: Option<Option<f64>>,
        take_profit_pct: Option<Option<f64>>,
        // GuardianConfig fields / 守護者配置
        max_leverage: Option<f64>,
        max_drawdown_pct: Option<f64>,
        max_same_direction_positions: Option<usize>,
        // IntentProcessor fields / 意圖處理器配置
        p1_risk_pct: Option<f64>,
        // RRC-1-A3: H0Gate shadow mode toggle / H0 門控影子模式切換
        h0_shadow_mode: Option<bool>,
        // PNL-7: agent-tunable dynamic-stop knobs
        // PNL-7：Agent 可調的動態止損參數
        dynamic_stop_base_ratio: Option<f64>,
        dynamic_stop_cap_ratio: Option<f64>,
        trailing_min_rr_ratio: Option<f64>,
        // Session 12: cost-gate + regime + boot cooldown tunables
        cost_gate_min_confidence: Option<f64>,
        cost_gate_k_base: Option<f64>,
        cost_gate_k_medium: Option<f64>,
        cost_gate_k_small: Option<f64>,
        adx_trending_threshold: Option<f64>,
        boot_cooldown_ms: Option<u64>,
        // DB-RUN-1: signals heartbeat (0 = disable throttling)
        signals_heartbeat_ms: Option<u64>,
    },
    /// ARCH-RC1 1C-3-B: Get Rust-native risk runtime status snapshot.
    /// Returns JSON: `{governor_tier, consecutive_losses_by_symbol, boot_cooldown_remaining_ms,
    /// paper_paused, session_halted}`. Shape intentionally differs from the
    /// deprecated Python `RiskManager.get_status()` — this exposes the real
    /// Rust state machine (risk_governor cascade) rather than synthesising
    /// Python's obsolete counter+cooldown fields.
    /// ARCH-RC1 1C-3-B：獲取 Rust 原生風控運行時狀態快照。
    GetRiskRuntimeStatus {
        response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    },
    /// ARCH-RC1 1C-3-B: Clear per-symbol consecutive-loss counters.
    /// Safe reset — the counters are pure statistics; no governor tier
    /// change. For governor override (de-escalation) see 1C-3-B-2.
    /// ARCH-RC1 1C-3-B：清除 per-symbol 連虧計數器（純統計重置，不影響 governor tier）。
    ClearConsecutiveLosses {
        response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    },
    /// ARCH-RC1 1C-3-B-2: Force RiskGovernor toward more restrictive tier
    /// (operator escalation). No 24h cooldown — operator can always be more
    /// careful. Hard rules:
    /// - Target must be exactly one level higher than current (no jumps)
    /// - target ∈ {Cautious, Reduced, Defensive, CircuitBreaker, ManualReview}
    /// 強制 RiskGovernor 往更嚴方向（operator 升級）。無 24h 冷卻——operator
    /// 隨時可以變保守。只能逐級且不能反向。
    ForceGovernorTighter {
        target_tier: String,
        reason: String,
        response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    },
    /// ARCH-RC1 1C-3-B-2: Force RiskGovernor toward less restrictive tier
    /// (operator de-escalation). Hard guards layered on top of the SM's
    /// built-in min_hold_time_ms + lookup_rule:
    /// - Target must be exactly one level lower (no jumps)
    /// - reason_code ∈ {"false_positive", "root_cause_fixed", "accept_risk"}
    /// - 24h IPC-layer cooldown since last successful de-escalation (in-memory)
    /// - CircuitBreaker / ManualReview cannot be unlocked here (the SM's
    ///   lookup_rule already enforces this — operator must edit TOML + restart)
    /// - Writes V014 audit row with from/to tier + reason_code + drawdown snap
    /// 強制 RiskGovernor 往更鬆方向（operator 降級）。在 SM 內建保護之上加：
    /// 逐級限制 / reason_code 白名單 / 24h IPC 冷卻 / CB/MR 不可解 / V014 audit。
    ForceGovernorLooser {
        target_tier: String,
        reason_code: String,
        notes: String,
        response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    },
    /// ARCH-RC1 1C-3-F: Submit an external paper-side order through the same
    /// IntentProcessor pipeline strategies use (Guardian / Kelly / P1 cap /
    /// risk gates / cost gate / paper fill). Used by `shadow_decision_builder`
    /// after Layer 2 retires `paper_trading_engine.py`. Returns a JSON envelope
    /// `{"order_id","fill_qty","fill_price","fee"}` on success.
    /// ARCH-RC1 1C-3-F：通過策略所走的同一條 IntentProcessor 管線提交外部紙盤訂單。
    /// shadow_decision_builder 在 paper_trading_engine.py 退場後改走此 RPC。
    SubmitOrder {
        symbol: String,
        side: String,   // "Buy" / "Sell"
        qty: f64,
        order_type: String, // "market" or "limit"
        limit_price: Option<f64>,
        confidence: f64,
        strategy: String,
        response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    },
    /// Scanner: query the set of symbols with open paper positions.
    /// Used by ScannerRunner to defer removal of symbols with active trades.
    /// 掃描器：查詢有開放紙盤持倉的交易對集合。
    /// 由 ScannerRunner 使用，以延遲移除有活躍交易的交易對。
    GetOpenPositionSymbols {
        response_tx: tokio::sync::oneshot::Sender<std::collections::HashSet<String>>,
    },
    // 3E-3: AddMode and SwitchMode REMOVED — pipelines are now spawned
    // at startup with fixed PipelineKind. Dynamic mode switching replaced
    // by per-pipeline command routing via EngineCommandChannels.
    // 3E-3：AddMode 和 SwitchMode 已移除 — 管線啟動時以固定 PipelineKind 啟動。
    /// Phase 6: Reconciler auto-escalation (tighten risk on drift detection).
    /// Bypasses operator whitelist/24h cooldown — drift response must not be blocked.
    /// Phase 6: 對帳器自動升級（漂移偵測時收緊風控）。繞過 operator 白名單/冷卻。
    ReconcilerEscalate {
        target_tier: String,
        reason: String,
        response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    },
    /// Phase 6: Reconciler auto-recovery (de-escalate after clean cycles).
    /// Only for Cautious/Reduced/Defensive. CB/MR stays operator-only.
    /// Phase 6: 對帳器自動恢復（乾淨週期後降級）。CB/MR 仍需 operator。
    ReconcilerDeEscalate {
        target_tier: String,
        reason: String,
        response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    },
    /// Sync global system mode from Python GUI → Rust engine.
    /// Blocks certain engines and auto-closes positions as required.
    /// 從 Python GUI 同步全局系統模式到 Rust 引擎。
    /// 按需封鎖特定引擎並自動平倉。
    SetSystemMode {
        mode: String,
        response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    },
}

/// Server-side stop request dispatched from tick_pipeline to Bybit API (Item 1).
/// 從 tick_pipeline 派發到 Bybit API 的伺服器端止損請求（項目 1）。
#[derive(Debug, Clone)]
pub struct StopRequest {
    pub symbol: String,
    pub stop_loss: f64,
    pub is_long: bool,
}

/// Order dispatch request from tick_pipeline to exchange API (EXT-1).
/// 從 tick_pipeline 派發到交易所 API 的訂單派發請求。
///
/// R-04: Renamed from ShadowOrderRequest — used for both shadow and primary orders.
/// R-04：從 ShadowOrderRequest 重命名 — 同時用於影子單和主訂單。
///
/// Used in both modes:
/// - `paper_only`: shadow order (fire-and-forget after local fill, is_primary=false)
/// - `exchange`: primary order (tracked, fill confirmed via WS, is_primary=true)
#[derive(Debug, Clone)]
pub struct OrderDispatchRequest {
    /// Trading symbol / 交易對
    pub symbol: String,
    /// Long direction / 多方向
    pub is_long: bool,
    /// Order quantity / 訂單數量
    pub qty: f64,
    /// Reference price / 參考價格
    pub price: f64,
    /// Strategy name / 策略名稱
    pub strategy: String,
    /// Timestamp (ms) when the intent was generated / 意圖生成時間戳（毫秒）
    pub paper_fill_ts: u64,
    /// true = closing position, use reduce_only / true = 平倉，使用 reduce_only
    pub is_close: bool,
    /// EXT-1: Client-assigned order link ID for tracking / 客戶端訂單連結 ID
    pub order_link_id: String,
    /// EXT-1: true = exchange mode primary order (track pending, await confirmation)
    /// false = paper_only mode shadow order (fire-and-forget)
    pub is_primary: bool,
    /// I-08 雙軌止損：broker-side stop loss price (None = engine rail only)
    pub stop_loss: Option<f64>,
    /// I-08 雙軌止損：broker-side take profit price
    pub take_profit: Option<f64>,
}

/// Tick context passed to strategies — borrows from on_tick scope to avoid cloning.
/// 傳遞給策略的 tick 上下文 — 從 on_tick 作用域借用以避免克隆。
/// P-08: Lifetime-parameterized to eliminate per-tick clone of indicators/signals.
#[derive(Debug, Clone)]
pub struct TickContext<'a> {
    pub symbol: &'a str,
    pub price: f64,
    pub timestamp_ms: u64,
    pub indicators: Option<&'a IndicatorSnapshot>,
    pub signals: &'a [Signal],
    pub h0_allowed: bool,
    /// EDGE-P1-2: Latest funding rate for this symbol (from Bybit tickers).
    /// EDGE-P1-2：該幣種最新資金費率（來自 Bybit tickers）。
    pub funding_rate: Option<f64>,
}

/// Tick statistics for monitoring.
/// Tick 統計。
#[derive(Debug, Default, Clone, Serialize, Deserialize)]
pub struct TickStats {
    pub total_ticks: u64,
    pub total_intents: u64,
    pub total_fills: u64,
    pub total_stops: u64,
    pub last_tick_ms: u64,
}

/// Core tick pipeline — owns all processing state.
/// 核心 tick 管線 — 擁有所有處理狀態。
///
/// Phase 3 (Signal Diamond): per-mode state lives in `mode_states` HashMap.
/// The fields below marked "primary mode alias" are migration shims that
/// point to the primary (first) active mode. Once multi-mode on_tick is
/// fully migrated, these will be removed.
/// Phase 3（Signal Diamond）：每模式狀態在 `mode_states` HashMap 中。
/// 下方標記 "primary mode alias" 的欄位是遷移墊片，指向主要活躍模式。
/// 多模式 on_tick 完整遷移後將移除。
pub struct TickPipeline {
    pub kline_manager: KlineManager,
    pub signal_engine: SignalEngine,
    pub orchestrator: Orchestrator,
    pub intent_processor: IntentProcessor,
    pub governance: GovernanceCore,
    pub paper_state: PaperState,
    pub stats: TickStats,
    latest_prices: HashMap<String, f64>,
    /// Per-symbol latest indicators for IPC / 每交易對最新指標供 IPC 使用
    latest_indicators: HashMap<String, IndicatorSnapshot>,
    /// Recent signals ring buffer (max 100) / 最近信號環形緩衝（最大 100）
    recent_signals: VecDeque<Signal>,
    /// Recent intents ring buffer (max 50) / 最近意圖環形緩衝（最大 50）
    recent_intents: VecDeque<TimestampedIntent>,
    /// Recent fills ring buffer (max 50) / 最近成交環形緩衝（最大 50）
    recent_fills: VecDeque<TimestampedFill>,
    /// Channel to dispatch server-side stop requests (Item 1: dual-track stops).
    /// 派發伺服器端止損請求的通道（項目 1：雙軌止損）。
    stop_request_tx: Option<tokio::sync::mpsc::UnboundedSender<StopRequest>>,
    /// ADL alert ring buffer (ts_ms, symbol, rank). Item 9.
    /// ADL 警報環形緩衝（時間戳, 交易對, 排名）。項目 9。
    adl_alerts: VecDeque<(u64, String, u32)>,
    /// Enable canary mode — on_tick returns per-tick CanaryRecord (R07-2).
    /// 啟用灰度模式 — on_tick 返回每 tick 的 CanaryRecord。
    pub canary_mode: bool,
    /// Instrument info cache for exchange precision rounding (R-05).
    /// 合約信息緩存，用於交易所精度取整。
    instrument_cache: Option<Arc<InstrumentInfoCache>>,
    /// Channel to dispatch shadow orders to Bybit Demo API.
    /// 派發影子訂單到 Bybit Demo API 的通道。
    order_dispatch_tx: Option<tokio::sync::mpsc::UnboundedSender<OrderDispatchRequest>>,
    /// Phase 1: Channel to dispatch market data to async PG writer.
    /// Phase 1：派發市場數據到異步 PG 寫入器的通道。
    market_data_tx: Option<tokio::sync::mpsc::Sender<crate::database::MarketDataMsg>>,
    /// Phase 1: Channel to dispatch feature snapshots to async PG writer.
    /// Phase 1：派發特徵快照到異步 PG 寫入器的通道。
    feature_tx: Option<tokio::sync::mpsc::Sender<crate::feature_collector::FeatureSnapshot>>,
    /// Phase 2a: Channel to dispatch trading lifecycle events to PG writer.
    /// Phase 2a：派發交易生命週期事件到 PG 寫入器的通道。
    trading_tx: Option<tokio::sync::mpsc::Sender<crate::database::TradingMsg>>,
    /// Phase 2a: Channel to dispatch decision context snapshots to PG writer.
    /// Phase 2a：派發決策上下文快照到 PG 寫入器的通道。
    context_tx: Option<tokio::sync::mpsc::Sender<crate::database::DecisionContextMsg>>,
    /// Phase 1: Feature version string for FeatureSnapshot.
    /// Phase 1：特徵版本字符串。
    feature_version: String,
    /// Phase 1: Counter for dropped channel sends (logged periodically).
    /// Phase 1：通道發送丟棄計數器（定期記錄）。
    market_tx_dropped: u64,
    feature_tx_dropped: u64,
    /// Paper trading paused — skip strategy dispatch + shadow orders, keep prices/indicators/stops.
    /// 紙盤交易暫停 — 跳過策略分派+影子訂單，保留價格/指標/止損。
    pub paper_paused: bool,
    /// 3E-4: Pipeline identity — immutable, set at construction (replaces TradingMode).
    /// 3E-4：管線身份 — 不可變，構造時設定（取代 TradingMode）。
    pub(crate) pipeline_kind: PipelineKind,
    /// EXT-1: Sequence counter for generating unique order_link_id.
    /// EXT-1：序列計數器，用於生成唯一 order_link_id。
    exchange_seq: u64,
    /// EXT-1: Symbols with pending close orders (prevent duplicate stop-close in exchange mode).
    /// EXT-1：有待處理平倉訂單的交易對（防止交易所模式下重複止損平倉）。
    pending_close_symbols: std::collections::HashSet<String>,
    /// RRC-1-A1: H0 Gate — pre-strategy health/risk/freshness gate (shadow mode by default).
    /// RRC-1-A1：H0 門控 — 策略前的健康/風控/新鮮度檢查（默認影子模式）。
    pub h0_gate: H0Gate,
    /// RRC-1-C1: Price history tracker for ATR computation + spike detection.
    /// RRC-1-C1：價格歷史追蹤器，用於 ATR 計算 + 尖峰偵測。
    price_tracker: PriceHistoryTracker,
    /// RRC-1-C3: Per-symbol consecutive loss counter (reset on win).
    /// RRC-1-C3：每交易對連續虧損計數器（盈利時重置）。
    pub consecutive_losses: HashMap<String, u32>,
    /// RRC-1-C4: Session halted flag — set by HaltSession, cleared by Resume/Reset.
    /// RRC-1-C4：會話暫停標誌 — 由 HaltSession 設置，由 Resume/Reset 清除。
    pub session_halted: bool,
    /// Session 11: 1-minute trade aggregator (idle writer #2 fix).
    /// Session 11：1 分鐘成交聚合器（idle writer #2 修復）。
    trade_aggregator: crate::database::aggregators::TradeAggregator,
    /// Session 11: 1-minute orderbook aggregator (idle writer #1 fix).
    /// Session 11：1 分鐘訂單簿聚合器（idle writer #1 修復）。
    ob_aggregator: crate::database::aggregators::ObAggregator,
    /// PNL-3: Boot timestamp (set on first tick) for cooldown gating.
    /// PNL-3：啟動時間戳（首個 tick 設定），用於冷卻期門控。
    boot_ts_ms: Option<u64>,
    /// PNL-3: Cooldown duration after boot during which strategy signals are suppressed.
    /// Reads from OPENCLAW_BOOT_COOLDOWN_MS env var, default 60_000ms.
    /// PNL-3：啟動冷卻期，期間策略信號被抑制（止損/指標/快照繼續）。
    boot_cooldown_ms: u64,
    /// ARCH-RC1 1C-3-B-2: timestamp of the last successful operator-driven
    /// governor de-escalation (in-memory only — resets on engine restart, which
    /// is intentional for the demo phase). Used to enforce a 24h cooldown
    /// between manual de-escalations.
    /// ARCH-RC1 1C-3-B-2：上次成功 operator 降級的時間戳（in-memory，重啟即重置）。
    /// 用於強制 24h 解鎖冷卻期，避免 operator 在虧損下反覆解鎖的賭徒循環。
    last_governor_de_escalation_ms: Option<u64>,
    /// DB-RUN-1: Last persisted signal per (symbol, strategy) — direction + ts_ms.
    /// Used to dedupe by state-change and rate-limit by heartbeat.
    /// DB-RUN-1：每 (symbol, strategy) 最近持久化的信號 — 用於狀態變更去重 + 心跳節流。
    last_persisted_signal: HashMap<(String, String), (openclaw_core::signals::SignalDirection, u64)>,
    /// DB-RUN-1: Heartbeat interval — re-emit unchanged signals at most this often.
    /// Default 60_000ms (1/min). 0 disables (legacy per-tick behavior).
    /// DB-RUN-1：心跳間隔，未變化信號最多每此間隔重發一次。0=關閉節流。
    signals_heartbeat_ms: u64,
    /// DB-RUN-1: Counter for dropped (throttled) signal writes — observability.
    /// DB-RUN-1：被節流跳過的 signal 寫入計數，供 status 報告觀察降頻效果。
    signals_throttled: u64,
    /// DB-RUN-2: Counter for dropped (throttled) decision_context writes.
    /// DB-RUN-2：被節流跳過的 decision_context 寫入計數。
    context_throttled: u64,
    /// DB-RUN-5: Black-swan detector — fed on bar close, logs severity.
    /// DB write path deferred until risk.black_swan_events schema lands.
    /// DB-RUN-5：黑天鵝檢測器，K 線收盤時餵入；DB 寫入待 schema 上線後接通。
    black_swan: crate::database::black_swan_detector::BlackSwanDetector,
    /// DB-RUN-5: Last close price per symbol for return computation.
    /// DB-RUN-5：每品種上一根 K 線收盤價（用於計算回報）。
    last_close_price: HashMap<String, f64>,
    /// W-3: LinUCB runtime for read-only arm selection on each decision tick.
    /// None = disabled (no arm selection, decision context emits NULL).
    /// W-3：LinUCB 運行時，每個決策 tick 做唯讀 arm 選擇。None = 關閉
    /// （不選 arm，decision context 寫 NULL）。
    linucb: Option<std::sync::Arc<crate::linucb::LinUcbRuntime>>,
    /// W-4 (Phase 4 wiring sweep): shared news context snapshot, read at the
    /// DecisionContextMsg producer site to populate `news_severity` +
    /// `hours_since_last_major_news`. None = no news wired.
    /// W-4 (Phase 4 wiring sweep)：共享新聞 context 快照，在 DecisionContextMsg
    /// producer 站點讀取以填 news_severity + hours_since_last_major_news。
    /// None = 未接新聞。
    news_snapshot: Option<std::sync::Arc<crate::news::NewsContextSnapshot>>,
    /// ARCH-RC1 1C-2-B: live RiskConfig store (ArcSwap snapshot read each tick).
    /// None = 1C-1 legacy mode (intent_processor owns RiskConfig::default()).
    /// ARCH-RC1 1C-2-B：live RiskConfig store（每 tick ArcSwap 快照讀）。
    /// None = 1C-1 舊模式（intent_processor 持有 RiskConfig::default()）。
    risk_store: Option<std::sync::Arc<crate::config::ConfigStore<crate::config::RiskConfig>>>,
    /// ARCH-RC1 1C-2-B: live BudgetConfig store — hot path reads
    /// `attention_tax.cost_edge_max_ratio` per tick for the cost-edge check.
    /// ARCH-RC1 1C-2-B：live BudgetConfig store — 熱路徑每 tick 讀
    /// attention_tax.cost_edge_max_ratio 用於 cost-edge 檢查。
    budget_store: Option<std::sync::Arc<crate::config::ConfigStore<crate::config::BudgetConfig>>>,
    /// ARCH-RC1 1C-2-B: last seen RiskConfig version number — used to detect
    /// store updates and sync the intent_processor snapshot only on change.
    /// ARCH-RC1 1C-2-B：上一次見到的 RiskConfig 版本號 — 用於檢測 store 更新並
    /// 僅在變化時同步 intent_processor 快照。
    risk_config_version_seen: u64,
    /// Phase 3: Per-mode trading state (Signal Diamond architecture).
    // 3E-4: mode_states and active_modes REMOVED — each pipeline is now
    // an independent TickPipeline instance with its own PipelineKind.
    // 3E-4：mode_states 和 active_modes 已移除 — 每管線是獨立 TickPipeline 實例。
    /// Global system mode — synced from Python GUI. Gates trading at tick level.
    /// 全局系統模式 — 從 Python GUI 同步。在 tick 級別封鎖交易。
    system_mode: SystemMode,
    /// EDGE-P0-1: Symbols already halved in the current Defensive+ episode.
    /// Reset when risk drops below Defensive. Prevents geometric qty decay
    /// from ReduceToHalf firing every tick.
    /// EDGE-P0-1：當前 Defensive+ 階段已半倉的交易對。
    /// 風控降至 Defensive 以下時重置。防止每 tick ReduceToHalf 造成幾何衰減。
    ft_reduced_symbols: std::collections::HashSet<String>,
    /// EDGE-P1-2: Cached latest funding rate per symbol (from Ticker events).
    /// EDGE-P1-2：每幣種最新資金費率緩存（來自 Ticker 事件）。
    funding_rates: HashMap<String, f64>,
}

impl TickPipeline {
    pub fn new(symbols: &[&str]) -> Self {
        // Read paper balance from env var or default to 10,000 USDT.
        // 從環境變量讀取紙盤餘額，預設 10,000 USDT。
        let balance = std::env::var("OPENCLAW_PAPER_BALANCE")
            .ok()
            .and_then(|s| s.parse::<f64>().ok())
            .unwrap_or(10_000.0);
        Self::with_balance(symbols, balance)
    }

    /// Create a pipeline with an explicit initial balance.
    /// 使用明確初始餘額創建管線。
    pub fn with_balance(symbols: &[&str], balance: f64) -> Self {
        Self {
            kline_manager: KlineManager::new(symbols, None, None),
            signal_engine: SignalEngine::new(),
            orchestrator: Orchestrator::new(),
            intent_processor: IntentProcessor::new(),
            governance: GovernanceCore::new(),
            paper_state: PaperState::new(balance),
            stats: TickStats::default(),
            latest_prices: HashMap::new(),
            latest_indicators: HashMap::new(),
            recent_signals: VecDeque::new(),
            recent_intents: VecDeque::new(),
            recent_fills: VecDeque::new(),
            stop_request_tx: None,
            adl_alerts: VecDeque::new(),
            canary_mode: false,
            instrument_cache: None,
            order_dispatch_tx: None,
            market_data_tx: None,
            feature_tx: None,
            trading_tx: None,
            context_tx: None,
            feature_version: "v1.0".into(),
            market_tx_dropped: 0,
            feature_tx_dropped: 0,
            paper_paused: false,
            pipeline_kind: PipelineKind::Paper,
            exchange_seq: 0,
            pending_close_symbols: std::collections::HashSet::new(),
            h0_gate: H0Gate::new(Some(openclaw_types::H0GateConfig {
                shadow_mode: true, // RRC-1-A3: observe-only until proven stable
                ..Default::default()
            })),
            price_tracker: PriceHistoryTracker::new(),
            consecutive_losses: HashMap::new(),
            session_halted: false,
            trade_aggregator: crate::database::aggregators::TradeAggregator::new(),
            ob_aggregator: crate::database::aggregators::ObAggregator::new(),
            boot_ts_ms: None,
            boot_cooldown_ms: std::env::var("OPENCLAW_BOOT_COOLDOWN_MS")
                .ok()
                .and_then(|s| s.parse::<u64>().ok())
                .unwrap_or(60_000),
            last_governor_de_escalation_ms: None,
            last_persisted_signal: HashMap::new(),
            signals_heartbeat_ms: std::env::var("OPENCLAW_SIGNALS_HEARTBEAT_MS")
                .ok()
                .and_then(|s| s.parse::<u64>().ok())
                .unwrap_or(60_000),
            signals_throttled: 0,
            context_throttled: 0,
            black_swan: crate::database::black_swan_detector::BlackSwanDetector::new(),
            last_close_price: HashMap::new(),
            linucb: None,
            news_snapshot: None,
            risk_store: None,
            budget_store: None,
            risk_config_version_seen: 0,
            // 3E-4: mode_states/active_modes removed (per-pipeline architecture)
            system_mode: SystemMode::default(),
            ft_reduced_symbols: std::collections::HashSet::new(),
            funding_rates: HashMap::new(),
        }
    }

    /// 3E-2a: Create a pipeline with explicit kind + balance.
    /// GovernanceCore is constructed with the appropriate profile (auto-grant for Paper/Demo).
    /// 3E-2a：以明確 kind + balance 創建管線。GovernanceCore 按 profile 構造（Paper/Demo 自動授權）。
    pub fn with_kind(symbols: &[&str], balance: f64, kind: PipelineKind) -> Self {
        let mut p = Self::with_balance(symbols, balance);
        // 3E-ARCH bugfix: persist the kind on the pipeline so downstream consumers
        // (event_consumer persistence kind_tag, IPC routing, status reports) see the
        // correct value. Without this all engines kept the with_balance() default
        // PipelineKind::Paper and raced on paper_state.json / pipeline_snapshot_paper.json.
        // 3E-ARCH 修復：把 kind 寫入 pipeline 字段，否則下游持久化 / IPC / 狀態報告
        // 都讀回 with_balance() 預設的 Paper，三引擎搶寫同一份 paper_state.json。
        p.pipeline_kind = kind;
        p.governance = GovernanceCore::new_with_profile(kind.governance_profile());
        p
    }

    /// Scanner C3: Add a symbol to the kline manager (idempotent).
    /// Per-symbol HashMaps (latest_prices, latest_indicators, consecutive_losses)
    /// self-populate on first tick — no explicit initialisation needed.
    /// 掃描器 C3：向 kline manager 添加交易對（冪等）。
    /// Per-symbol HashMap 在第一個 tick 時自動填充，無需明確初始化。
    pub fn add_symbol(&mut self, symbol: &str) {
        self.kline_manager.add_symbol(symbol);
    }

    /// Scanner C3: Remove a symbol from the kline manager and clear its cached state.
    /// 掃描器 C3：從 kline manager 移除交易對並清除其緩存狀態。
    pub fn remove_symbol(&mut self, symbol: &str) {
        self.kline_manager.remove_symbol(symbol);
        self.latest_prices.remove(symbol);
        self.latest_indicators.remove(symbol);
        self.consecutive_losses.remove(symbol);
        self.last_persisted_signal.retain(|(sym, _), _| sym != symbol);
        self.last_close_price.remove(symbol);
        // M-1 fix: clear pending_close lock so re-entry of same symbol doesn't
        // inherit a stale close-pending flag from the previous tenure.
        // M-1 修復：清除待處理平倉鎖，防止同名交易對重新加入時繼承過期標記。
        self.pending_close_symbols.remove(symbol);
        // M-1 fix: purge stale ADL alerts for removed symbol (ring-buffer cap=50, minor but clean).
        // M-1 修復：清除已移除交易對的過期 ADL 警報（環形緩衝上限 50，次要但乾淨）。
        self.adl_alerts.retain(|(_, sym, _)| sym != symbol);
    }

    /// PH5-WIRE-1: Inject JS shrunk edge estimates into the intent processor.
    /// PH5-WIRE-1：將 JS 收縮邊際估計注入意圖處理器。
    pub fn set_edge_estimates(&mut self, estimates: crate::edge_estimates::EdgeEstimates) {
        self.intent_processor.set_edge_estimates(estimates);
    }

    /// BLOCKER-3 D15: Wire shared cross-engine global exposure atomic.
    /// BLOCKER-3 D15：接入跨引擎全局曝險共享原子量。
    pub fn set_global_exposure(&mut self, exposure: std::sync::Arc<std::sync::atomic::AtomicU64>) {
        self.intent_processor.set_global_exposure(exposure);
    }

    /// W-3: Plug in a LinUCB runtime (read-only on the live path; metadata only).
    /// W-3：注入 LinUCB 運行時（live 路徑唯讀；僅 metadata）。
    pub fn set_linucb_runtime(
        &mut self,
        rt: std::sync::Arc<crate::linucb::LinUcbRuntime>,
    ) {
        self.linucb = Some(rt);
    }

    /// W-4: Plug in a shared NewsContextSnapshot (read-only on the live path).
    /// W-4：注入共享 NewsContextSnapshot（live 路徑唯讀）。
    pub fn set_news_snapshot(
        &mut self,
        snap: std::sync::Arc<crate::news::NewsContextSnapshot>,
    ) {
        self.news_snapshot = Some(snap);
    }

    /// ARCH-RC1 1C-2-B: Inject the live RiskConfig ConfigStore handle. After
    /// wiring, the pipeline checks the store version at the top of each tick
    /// and refreshes the intent_processor's owned snapshot if the version has
    /// bumped (IPC patch applied). Also seeds the first snapshot immediately.
    /// ARCH-RC1 1C-2-B：注入 live RiskConfig ConfigStore。接線後每 tick 檢查
    /// 版本號，若上升（IPC patch 已套用）則刷新 intent_processor 快照。
    pub fn set_risk_store(
        &mut self,
        store: std::sync::Arc<crate::config::ConfigStore<crate::config::RiskConfig>>,
    ) {
        // Immediate sync so the first tick already sees the live config.
        let snap = store.load();
        self.apply_risk_snapshot(&snap);
        self.risk_config_version_seen = store.version();
        self.risk_store = Some(store);
    }

    /// ARCH-RC1 1C-2-B (Option B) + 1C-4 E-Merge-4: Push a RiskConfig snapshot
    /// into every downstream consumer that owns a derived copy. After E-Merge-4
    /// the Guardian is a **pure derived view** of RiskConfig — no RMW, every
    /// field is sourced from RiskConfig (modification_size_factor and
    /// modification_leverage_cap were promoted to RiskConfig.limits, and the
    /// dead `max_correlation` field on GuardianConfig was deleted). This means
    /// the operator GUI's `patch_risk_config` is now the SINGLE source of
    /// truth for every Guardian knob.
    /// ARCH-RC1 1C-2-B + 1C-4 E-Merge-4：把 RiskConfig 快照推到所有持派生 copy
    /// 的下游。E-Merge-4 後 Guardian 為 RiskConfig 的純派生視圖 — 無 RMW，
    /// 每個欄位皆從 RiskConfig 取值。modification_* 欄位升級至 RiskConfig.limits，
    /// 死欄位 max_correlation 已刪除。operator GUI 的 patch_risk_config 從此
    /// 是 Guardian 任何旋鈕的唯一真相源。
    fn apply_risk_snapshot(&mut self, snap: &crate::config::RiskConfig) {
        // 1. Update intent_processor's owned RiskConfig (used for cost_gate k_*,
        //    dynamic_stop tunables, and check_order_allowed via risk_config()).
        self.intent_processor.update_risk_config(snap.clone());

        // 2. Construct a fresh GuardianConfig fully derived from RiskConfig
        //    (no RMW). Every field below has a 1:1 source in `snap`.
        //    完整重建 GuardianConfig，無 RMW，每個欄位都對應 snap 內的單一來源。
        let gc = openclaw_core::guardian::GuardianConfig {
            max_leverage: snap.limits.leverage_max,
            max_drawdown_pct: snap.limits.session_drawdown_max_pct,
            max_same_direction_positions: snap.anti_cluster.max_same_direction as usize,
            modification_size_factor: snap.limits.guardian_modification_size_factor,
            modification_leverage_cap: snap.limits.guardian_modification_leverage_cap,
        };
        self.intent_processor.update_guardian_config(gc);

        // 3. ARCH-RC1 1C-2-F E-Merge-2: hot-reload H0Gate risk-level fields
        //    from RiskConfig.limits (RMW preserves health + shadow_mode fields
        //    that don't live in RiskConfig). Previously the H0GateConfig was
        //    only seeded at tick_pipeline construction from defaults and never
        //    updated — so an operator raising open_positions_max in RiskConfig
        //    would still hit the old cap at the H0 gate.
        //    ARCH-RC1 1C-2-F E-Merge-2：H0Gate 的風控層欄位從 RiskConfig.limits
        //    熱重載（RMW 保留健康欄位與 shadow_mode）。
        let mut h0 = self.h0_gate.config().clone();
        h0.max_open_positions = snap.limits.open_positions_max;
        h0.max_total_exposure_pct = snap.limits.total_exposure_max_pct;
        h0.allowed_categories = snap.limits.allowed_categories.clone();
        self.h0_gate.update_config(h0);

        // 4. ARCH-RC1 1C-2-F E-Merge-1 (downgraded): hot-reload the legacy
        //    paper_state.stop_config so the H0-blocked / paused protective
        //    fallback stops at tick_pipeline.rs:910 + :1017 use the operator-
        //    current RiskConfig values, not stale boot defaults. The research
        //    agent confirmed those two call sites are intentional protective
        //    fallbacks (main engine evaluate_positions never runs in their
        //    early-return branches), so stop_manager is KEPT but its owned
        //    StopConfig must now track RiskConfig.
        //    Trailing / time stops stay None on paper_state because the
        //    main engine owns them; the fallback only needs hard + TP to
        //    prevent unbounded losses during gate block / pause.
        //    ARCH-RC1 1C-2-F E-Merge-1 (降級版)：熱重載 paper_state.stop_config，
        //    讓 H0 阻擋 / 暫停時的 fallback 止損使用 operator 最新的 RiskConfig
        //    值，而非啟動時的 defaults。Research agent 確認 910/1017 是故意的
        //    保護 fallback，因此 stop_manager 保留，只把它的 owned 配置拉齊。
        self.paper_state
            .set_hard_stop_pct(snap.limits.stop_loss_max_pct);
        if snap.limits.take_profit_enforced {
            self.paper_state
                .set_take_profit_pct(Some(snap.limits.take_profit_max_pct));
        } else {
            self.paper_state.set_take_profit_pct(None);
        }

        // 5. ARCH-RC1 1C-2-F E-Merge-3: hot-reload RiskGovernorSm.thresholds
        //    from RiskConfig.cascade. Previously the 6-tier cascade state
        //    machine carried its own hardcoded EscalationThresholds::default()
        //    with NO path to operator override. Field names differ slightly
        //    (circuit_breaker_pct vs circuit_pct, consecutive_loss_ vs
        //    consec_loss_, min_hold_time_ms vs min_hold_ms) but semantics are
        //    identical — map 1-to-1 and push.
        //    ARCH-RC1 1C-2-F E-Merge-3：把 RiskGovernorSm 的閾值從
        //    RiskConfig.cascade 熱重載進來；原本它只讀自己的硬編碼 default。
        let c = &snap.cascade;
        self.governance.risk.thresholds =
            openclaw_core::sm::risk_gov::EscalationThresholds {
                drawdown_cautious_pct: c.drawdown_cautious_pct,
                drawdown_reduced_pct: c.drawdown_reduced_pct,
                drawdown_defensive_pct: c.drawdown_defensive_pct,
                drawdown_circuit_breaker_pct: c.drawdown_circuit_pct,
                daily_loss_cautious_pct: c.daily_loss_cautious_pct,
                daily_loss_reduced_pct: c.daily_loss_reduced_pct,
                daily_loss_circuit_breaker_pct: c.daily_loss_circuit_pct,
                consecutive_loss_cautious: c.consec_loss_cautious,
                consecutive_loss_reduced: c.consec_loss_reduced,
                consecutive_loss_circuit_breaker: c.consec_loss_circuit,
                pressure_cautious: c.pressure_cautious,
                pressure_reduced: c.pressure_reduced,
                pressure_defensive: c.pressure_defensive,
                pressure_circuit_breaker: c.pressure_circuit,
                min_hold_time_ms: c.min_hold_ms,
            };
    }

    /// ARCH-RC1 1C-2-B: Inject the live BudgetConfig ConfigStore handle for
    /// the cost-edge hot-path read (`attention_tax.cost_edge_max_ratio`).
    /// ARCH-RC1 1C-2-B：注入 live BudgetConfig ConfigStore，供熱路徑讀
    /// attention_tax.cost_edge_max_ratio。
    pub fn set_budget_store(
        &mut self,
        store: std::sync::Arc<crate::config::ConfigStore<crate::config::BudgetConfig>>,
    ) {
        self.budget_store = Some(store);
    }

    /// ARCH-RC1 1C-2-B: Hot-reload hook called at the top of on_tick. If the
    /// risk store's version has bumped since last check, pull the latest
    /// snapshot into the intent_processor (which still owns a plain copy for
    /// its fine-grained patch_* methods). Cheap: one atomic load + equality.
    /// ARCH-RC1 1C-2-B：on_tick 頂部呼叫的熱重載檢查。store 版本號若有變化，
    /// 拉最新快照餵給 intent_processor。極低成本（一次原子 load + 相等比較）。
    #[inline]
    fn sync_risk_config_if_changed(&mut self) {
        if let Some(ref store) = self.risk_store {
            let v = store.version();
            if v != self.risk_config_version_seen {
                let snap = store.load();
                self.apply_risk_snapshot(&snap);
                self.risk_config_version_seen = v;
                tracing::info!(
                    new_version = v,
                    "ARCH-RC1 risk config hot-reloaded (pipeline + guardian)"
                );
            }
        }
    }

    /// ARCH-RC1 1C-2-B: Read the live `cost_edge_max_ratio` for the tick-level
    /// cost-edge check. Falls back to 0.8 when BudgetConfig store is not
    /// wired (1C-1 / unit-test paths).
    /// ARCH-RC1 1C-2-B：熱路徑讀取 live cost_edge_max_ratio；store 未接線時
    /// 回退 0.8（1C-1 / 單測路徑）。
    #[inline]
    fn current_cost_edge_max_ratio(&self) -> f64 {
        match self.budget_store.as_ref() {
            Some(store) => store.load().attention_tax.cost_edge_max_ratio,
            None => 0.8,
        }
    }

    /// Set dynamic fee rate from API for more accurate paper trading cost.
    /// 設定 API 動態費率，提高紙盤交易成本精確度。
    pub fn set_fee_rate(&mut self, rate: f64) {
        self.intent_processor.set_fee_rate(rate);
    }

    /// Wire AccountManager for live per-symbol fee lookups.
    /// 接入 AccountManager 用於 per-symbol 真實費率查詢。
    pub fn set_account_manager(
        &mut self,
        am: std::sync::Arc<crate::account_manager::AccountManager>,
    ) {
        self.intent_processor.set_account_manager(am);
    }
    /// PNL-FIX-1: Close a single position at its OWN symbol's latest market price.
    /// Returns (is_long, qty, close_price, pnl) on success — caller passes the
    /// returned price to emit_close_fill so the fill record matches the close.
    ///
    /// Why this exists: every multi-symbol close path used to call
    /// `paper_state.close_position(sym, event.last_price, ts)`, where
    /// `event.last_price` is the price of the SINGLE tick that fired the close.
    /// When sym ≠ event.symbol (e.g. fast_track CloseAll iterating all
    /// positions on one tick) the wrong-symbol price corrupted PnL by 1000-
    /// 10000x — see the 2026-04-12 paper anomaly: $497K fake PnL from 8 fills.
    ///
    /// Falls back to the position's entry_price (zero PnL) when no latest
    /// price is recorded for the symbol — strictly safer than borrowing the
    /// triggering tick's price.
    ///
    /// PNL-FIX-1：以「該交易對自己」的最新市場價平掉單一倉位。
    /// 返回 (is_long, qty, close_price, pnl)，呼叫端把 close_price 傳給
    /// emit_close_fill 讓 fill 記錄與真實平倉一致。
    /// 無最新價時退回到 entry_price（pnl=0），絕不借用觸發 tick 的價格。
    fn close_position_at_symbol_market(
        &mut self,
        sym: &str,
        ts_ms: u64,
    ) -> Option<(bool, f64, f64, f64)> {
        let (is_long, qty, entry_price) = self
            .paper_state
            .get_position(sym)
            .map(|p| (p.is_long, p.qty, p.entry_price))?;
        let close_price = match self.paper_state.latest_price(sym) {
            Some(p) if p.is_finite() && p > 0.0 => p,
            _ => {
                tracing::warn!(
                    symbol = %sym,
                    fallback = entry_price,
                    "PNL-FIX-1: no latest_price for symbol — falling back to entry price (zero PnL close)"
                );
                entry_price
            }
        };
        let pnl = self.paper_state.close_position(sym, close_price, ts_ms)?;
        Some((is_long, qty, close_price, pnl))
    }

    /// DB-RUN-3 / PNL-FIX-2: Emit a TradingMsg::Fill row for a close so
    /// trading.fills records the realized PnL **and** the real taker fee.
    /// Counter on stats.total_fills.
    ///
    /// EDGE-P2-1: `close_tag` is written directly as `strategy_name` in the DB.
    /// Callers MUST pass a prefixed tag to distinguish close sources:
    ///   - `"risk_close:{reason}"` — risk evaluator / fast-track / halt-session
    ///   - `"stop_trigger:{reason}"` — StopManager hard/trailing/time stop
    ///   - `"strategy_close:{reason}"` — strategy-driven exit
    /// This enables downstream analytics to separate risk-forced from
    /// strategy-driven exits (previously ALL closes were `risk_close:*`).
    ///
    /// EDGE-P2-1：`close_tag` 直接寫入 DB `strategy_name`。呼叫方必須傳入
    /// 帶前綴標籤（risk_close / stop_trigger / strategy_close）以區分平倉來源。
    ///
    /// PNL-FIX-2 (2026-04-12): the previous version wrote `fee: 0.0` —
    /// now we compute close_fee = qty × price × fee_rate, charge it via
    /// paper_state.charge_fee(), AND write it to DB so downstream cost
    /// analytics see the truth.
    fn emit_close_fill(
        &mut self,
        symbol: &str,
        is_long: bool,
        qty: f64,
        price: f64,
        ts_ms: u64,
        realized_pnl: f64,
        close_tag: &str,
    ) {
        // PNL-FIX-2: compute close fee from per-symbol taker rate, charge it
        // to paper_state, and record it in the DB row. Charge always happens
        // (even when trading_tx is unwired) so paper_state.balance / total_fees
        // stay consistent with the close action regardless of persistence.
        let fr = self.intent_processor.fee_rate(symbol);
        let close_fee = qty * price * fr;
        self.paper_state.charge_fee(close_fee);
        if let Some(ref tx) = self.trading_tx {
            // Fill side reflects the closing direction (opposite of position side).
            let close_side = if is_long { "Sell" } else { "Buy" };
            let em = self.pipeline_kind.db_mode();
            let _ = tx.try_send(crate::database::TradingMsg::Fill {
                fill_id: format!("close-{em}-{}-{}", symbol, ts_ms),
                ts_ms,
                order_id: format!("close_{em}_{}_{}", symbol, ts_ms),
                symbol: symbol.to_string(),
                side: close_side.into(),
                qty,
                price,
                fee: close_fee,
                fee_rate: fr,
                realized_pnl,
                strategy_name: close_tag.to_string(),
                context_id: on_tick_helpers::make_context_id(em, symbol, ts_ms),
                engine_mode: em.to_string(),
            });
        }
        self.stats.total_fills += 1;
    }

    /// DB-RUN-1: Decide whether to persist a freshly emitted signal.
    /// Persist if (a) direction differs from last persisted for the same
    /// (symbol, strategy) key, OR (b) heartbeat interval has elapsed.
    /// Returns true on persist (and updates the dedupe map).
    /// DB-RUN-1：判斷新生成的 signal 是否應持久化（狀態變更或心跳到期）。
    fn should_persist_signal(&mut self, sig: &openclaw_core::signals::Signal) -> bool {
        if self.signals_heartbeat_ms == 0 {
            return true;
        }
        let key = (sig.symbol.clone(), sig.source.clone());
        let now = sig.ts_ms;
        let persist = match self.last_persisted_signal.get(&key) {
            None => true,
            Some(&(prev_dir, prev_ts)) => {
                prev_dir != sig.direction
                    || now.saturating_sub(prev_ts) >= self.signals_heartbeat_ms
            }
        };
        if persist {
            self.last_persisted_signal.insert(key, (sig.direction, now));
        } else {
            self.signals_throttled += 1;
        }
        persist
    }

    /// PNL-4: Derive live regime label from indicator snapshot.
    /// Priority: Hurst regime → ADX strength fallback → "ranging" default.
    /// ADX threshold reads from RiskManagerConfig (Session 12 cleanup).
    /// PNL-4：從指標快照推導實時 regime 標籤。
    fn derive_regime(&self, snap: Option<&openclaw_core::indicators::IndicatorSnapshot>) -> String {
        if let Some(ind) = snap {
            if let Some(ref h) = ind.hurst {
                match h.regime.as_str() {
                    "trending" => return "trending".into(),
                    "mean_reverting" => return "ranging".into(),
                    _ => {}
                }
            }
            if let Some(ref a) = ind.adx {
                let threshold = self.intent_processor.risk_config().cost_gate.adx_trending;
                if a.adx >= threshold {
                    return "trending".into();
                }
            }
        }
        "ranging".into()
    }

    /// Set instrument info cache for exchange precision rounding (R-05).
    /// 設定合約信息緩存，用於交易所精度取整。
    pub fn set_instrument_cache(&mut self, cache: Arc<InstrumentInfoCache>) {
        self.instrument_cache = Some(cache);
    }

    /// Set channel for dispatching server-side stop requests (Item 1: dual-track stops).
    /// 設定伺服器端止損請求派發通道（項目 1：雙軌止損）。
    pub fn set_stop_channel(&mut self, tx: tokio::sync::mpsc::UnboundedSender<StopRequest>) {
        self.stop_request_tx = Some(tx);
    }

    /// Set channel for dispatching orders to exchange API.
    /// 設定訂單派發通道到交易所 API。
    pub fn set_shadow_channel(
        &mut self,
        tx: tokio::sync::mpsc::UnboundedSender<OrderDispatchRequest>,
    ) {
        self.order_dispatch_tx = Some(tx);
    }

    /// EXT-1: Set trading mode (paper_only or exchange).
    // 3E-4: set_trading_mode() REMOVED — pipeline identity is immutable.
    // 3E-4：set_trading_mode() 已移除 — 管線身份不可變。

    /// EXT-1: Clear pending close flag for a symbol (called when close order is rejected/cancelled).
    /// EXT-1：清除交易對的待處理平倉標記（平倉訂單被拒/取消時調用）。
    pub fn clear_pending_close(&mut self, symbol: &str) {
        self.pending_close_symbols.remove(symbol);
    }

    /// EXT-1: Clear all pending close flags (on reset or DCP).
    /// EXT-1：清除所有待處理平倉標記（重置或 DCP 時）。
    pub fn clear_all_pending_close(&mut self) {
        self.pending_close_symbols.clear();
    }

    /// Phase 1: Set channel for dispatching market data to async PG writer.
    /// Phase 1：設定市場數據派發到異步 PG 寫入器的通道。
    pub fn set_market_data_channel(
        &mut self,
        tx: tokio::sync::mpsc::Sender<crate::database::MarketDataMsg>,
    ) {
        self.market_data_tx = Some(tx);
    }

    /// Phase 1: Set channel for dispatching feature snapshots to async PG writer.
    /// Phase 1：設定特徵快照派發到異步 PG 寫入器的通道。
    pub fn set_feature_channel(
        &mut self,
        tx: tokio::sync::mpsc::Sender<crate::feature_collector::FeatureSnapshot>,
    ) {
        self.feature_tx = Some(tx);
    }

    /// Phase 2a: Set channel for dispatching trading lifecycle events to PG writer.
    /// Phase 2a：設定交易生命週期事件派發通道。
    pub fn set_trading_channel(
        &mut self,
        tx: tokio::sync::mpsc::Sender<crate::database::TradingMsg>,
    ) {
        self.trading_tx = Some(tx);
    }

    /// Phase 2a: Set channel for dispatching decision context snapshots.
    /// Phase 2a：設定決策上下文快照派發通道。
    pub fn set_context_channel(
        &mut self,
        tx: tokio::sync::mpsc::Sender<crate::database::DecisionContextMsg>,
    ) {
        self.context_tx = Some(tx);
    }

    // 3E-4: Multi-mode infrastructure REMOVED — each pipeline is independent.
    // set_trading_mode / sync_direct_to_mode_state / load_mode_state_to_direct /
    // add_mode / get_mode_state / get_mode_state_mut / active_modes /
    // set_mode_risk_store / mode_snapshot all removed.
    // 3E-4：多模式基礎設施已移除 — 每管線獨立運行。


    // 3E-4: Multi-mode infrastructure REMOVED — each pipeline is independent.
    // 3E-4：多模式基礎設施已移除 — 每管線獨立運行。
}

mod on_tick;
pub(crate) mod on_tick_helpers;
mod commands;
#[cfg(test)]
mod tests;


/// Convert IndicatorSnapshot to flat IndicatorInput for signal rules.
/// 將 IndicatorSnapshot 轉換為扁平 IndicatorInput 用於信號規則。
fn snapshot_to_input(snap: &IndicatorSnapshot) -> IndicatorInput {
    IndicatorInput {
        rsi: snap.rsi_14,
        sma: snap.sma_20,
        ema: snap.ema_12,
        macd: snap.macd.as_ref().map(|m| m.macd),
        macd_signal: snap.macd.as_ref().map(|m| m.signal),
        macd_histogram: snap.macd.as_ref().map(|m| m.histogram),
        bb_percent_b: snap.bollinger.as_ref().map(|b| b.percent_b),
        bb_bandwidth: snap.bollinger.as_ref().map(|b| b.bandwidth),
        atr_percent: snap.atr_14.as_ref().map(|a| a.atr_percent),
        stoch_k: snap.stochastic.as_ref().map(|s| s.k),
        adx: snap.adx.as_ref().map(|a| a.adx),
        volume_ratio: snap.volume_ratio,
    }
}

// Types extracted to pipeline_types.rs (RRC-1 E2 fix: 1200-line limit).
// 類型已提取到 pipeline_types.rs（RRC-1 E2 修復：1200 行限制）。
pub use crate::pipeline_types::{
    CanaryRecord, PipelineSnapshot, PipelineStatus, StrategyInfo, TimestampedFill,
    TimestampedIntent,
};

