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
use openclaw_types::PriceEvent;
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
/// Used in both modes:
/// - `paper_only`: shadow order (fire-and-forget after local fill, is_primary=false)
/// - `exchange`: primary order (tracked, fill confirmed via WS, is_primary=true)
#[derive(Debug, Clone)]
pub struct ShadowOrderRequest {
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

/// Tick context passed to strategies.
/// 傳遞給策略的 tick 上下文。
#[derive(Debug, Clone)]
pub struct TickContext {
    pub symbol: String,
    pub price: f64,
    pub timestamp_ms: u64,
    pub indicators: Option<IndicatorSnapshot>,
    pub signals: Vec<Signal>,
    pub h0_allowed: bool,
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
    shadow_order_tx: Option<tokio::sync::mpsc::UnboundedSender<ShadowOrderRequest>>,
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
            shadow_order_tx: None,
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
        }
    }

    /// 3E-2a: Create a pipeline with explicit kind + balance.
    /// GovernanceCore is constructed with the appropriate profile (auto-grant for Paper/Demo).
    /// 3E-2a：以明確 kind + balance 創建管線。GovernanceCore 按 profile 構造（Paper/Demo 自動授權）。
    pub fn with_kind(symbols: &[&str], balance: f64, kind: PipelineKind) -> Self {
        let mut p = Self::with_balance(symbols, balance);
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

    /// ARCH-RC1 1C-3-B: Build Rust-native risk runtime status snapshot.
    ///
    /// Intentionally exposes the real state machine rather than synthesising
    /// the deprecated Python `RiskManager.get_status()` shape. Callers (new
    /// GUI Risk tab, `RiskViewClient`) must bind to these fields directly.
    ///
    /// Fields:
    /// - `governor_tier`: current RiskGovernorSm level (Normal/Cautious/Reduced/
    ///   Defensive/CircuitBreaker/ManualReview)
    /// - `consecutive_losses_by_symbol`: per-symbol loss streak map
    /// - `boot_cooldown_remaining_ms`: remaining ms of post-boot signal
    ///   suppression window (0 if boot_ts_ms unset or window expired)
    /// - `paper_paused`: IPC pause flag
    /// - `session_halted`: news/guardian hard-halt flag
    ///
    /// ARCH-RC1 1C-3-B：組裝 Rust 原生風控運行時狀態快照（新 GUI 直接綁定這些欄位）。
    /// Test-only helper: seed `latest_indicators` so cost-gate ATR lookups
    /// in `submit_external_order` succeed without driving a full on_tick.
    /// 測試專用：種入 latest_indicators 以便 submit_external_order 走通成本門。
    #[cfg(test)]
    pub fn set_latest_indicators_for_test(&mut self, symbol: &str, snap: IndicatorSnapshot) {
        self.latest_indicators.insert(symbol.to_string(), snap);
    }

    /// ARCH-RC1 1C-3-F: External (non-strategy) paper-side order submission.
    /// Drives the same IntentProcessor pipeline strategies use, so all gates
    /// (Guardian / Kelly / P1 cap / risk gate / cost gate) apply uniformly.
    /// Returns a JSON envelope on success: `{order_id, fill_qty, fill_price, fee}`.
    /// Reject reasons (paused / halted / unknown symbol / no price / no atr /
    /// gate rejection) bubble up as Err(String).
    /// ARCH-RC1 1C-3-F：外部紙盤訂單入口（非策略），與策略走同一條 IntentProcessor 管線。
    pub fn submit_external_order(
        &mut self,
        symbol: &str,
        is_long: bool,
        qty: f64,
        order_type: &str,
        limit_price: Option<f64>,
        confidence: f64,
        strategy: &str,
    ) -> Result<String, String> {
        if self.paper_paused {
            return Err("paper_paused".into());
        }
        if self.session_halted {
            return Err("session_halted".into());
        }
        if !(qty > 0.0) {
            return Err(format!("invalid qty: {qty}"));
        }
        let price = self.paper_state.latest_price(symbol).unwrap_or(0.0);
        if !(price > 0.0) {
            return Err(format!("no latest price for {symbol}"));
        }
        // ATR drives the cost gate; absent ATR is fail-closed (matches on_tick path).
        // ATR 由 latest_indicators 取得；缺失即 fail-closed（與 on_tick 行為一致）。
        let atr_value = self
            .latest_indicators
            .get(symbol)
            .and_then(|i| i.atr_14.as_ref())
            .map(|a| a.atr)
            .unwrap_or(0.0);

        let intent = crate::intent_processor::OrderIntent {
            symbol: symbol.to_string(),
            is_long,
            qty,
            confidence,
            strategy: strategy.to_string(),
            order_type: order_type.to_string(),
            limit_price,
        };

        let result = self
            .intent_processor
            .process(&intent, &self.governance, &self.paper_state, atr_value, GovernanceProfile::Exploration);

        // Persist Guardian verdict (all verdicts including rejections) / 持久化 Guardian 裁定（含拒絕）
        if let (Some(ref tx), Some(ref vi)) = (&self.trading_tx, &result.verdict_info) {
            let now_ms_v = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_millis() as u64)
                .unwrap_or(0);
            let _ = tx.try_send(crate::database::TradingMsg::RiskVerdict {
                verdict_id: format!("vrd-{symbol}-{now_ms_v}"),
                ts_ms: now_ms_v,
                intent_id: format!("intent-{symbol}-{now_ms_v}"),
                context_id: format!("ctx-{symbol}-{now_ms_v}"),
                symbol: symbol.to_string(),
                verdict: vi.verdict.clone(),
                risk_score: vi.risk_score,
                reasons: vi.reasons.clone(),
                modified_qty: vi.modified_qty,
                engine_mode: self.pipeline_kind.db_mode().to_string(),
            });
        }

        if !result.submitted {
            return Err(result
                .rejected_reason
                .unwrap_or_else(|| "rejected_unknown".into()));
        }
        let mut fill = result.fill.ok_or_else(|| "submitted_but_no_fill".to_string())?;

        // Instrument-aware rounding (mirrors on_tick paper path).
        // 合約精度取整（與 on_tick 紙盤分支一致）。
        if let Some(ref icache) = self.instrument_cache {
            if let Some(spec) = icache.get(symbol) {
                fill.fill_qty = spec.round_qty(fill.fill_qty);
                fill.fill_price = spec.round_price(fill.fill_price);
                if fill.fill_qty <= 0.0 && spec.min_qty > 0.0 {
                    let notional = spec.min_qty * fill.fill_price;
                    if notional <= self.paper_state.balance() * 0.10 {
                        fill.fill_qty = spec.min_qty;
                    }
                }
            }
        }
        if !(fill.fill_qty > 0.0) {
            return Err("fill_qty rounded to 0".into());
        }

        let now_ms = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0);
        let realized_pnl = self.paper_state.apply_fill(
            symbol,
            is_long,
            fill.fill_qty,
            fill.fill_price,
            fill.fee,
            now_ms,
        );

        self.stats.total_intents += 1;
        self.stats.total_fills += 1;

        self.recent_intents.push_back(TimestampedIntent {
            timestamp_ms: now_ms,
            intent: intent.clone(),
            result: "submitted".into(),
        });
        if self.recent_intents.len() > 50 {
            self.recent_intents.pop_front();
        }
        self.recent_fills.push_back(TimestampedFill {
            timestamp_ms: now_ms,
            symbol: symbol.to_string(),
            is_long,
            qty: fill.fill_qty,
            price: fill.fill_price,
            fee: fill.fee,
            strategy: strategy.to_string(),
        });
        if self.recent_fills.len() > 50 {
            self.recent_fills.pop_front();
        }

        let order_id = format!("ext-{symbol}-{now_ms}");

        // Persistence parity: emit Intent + Fill to PG writer when wired.
        // 持久化對等：trading_tx 已接時，發 Intent + Fill 到 PG writer。
        if let Some(ref tx) = self.trading_tx {
            let context_id = format!("ctx-{symbol}-{now_ms}");
            let em = self.pipeline_kind.db_mode().to_string();
            let _ = tx.try_send(crate::database::TradingMsg::Intent {
                intent_id: format!("intent-{symbol}-{now_ms}"),
                ts_ms: now_ms,
                signal_id: String::new(),
                context_id: context_id.clone(),
                symbol: symbol.to_string(),
                side: if is_long { "Buy".into() } else { "Sell".into() },
                qty,
                price,
                order_type: order_type.to_string(),
                strategy_name: strategy.to_string(),
                engine_mode: em.clone(),
            });
            let _ = tx.try_send(crate::database::TradingMsg::Fill {
                fill_id: format!("fill-{symbol}-{now_ms}"),
                ts_ms: now_ms,
                order_id: order_id.clone(),
                symbol: symbol.to_string(),
                side: if is_long { "Buy".into() } else { "Sell".into() },
                qty: fill.fill_qty,
                price: fill.fill_price,
                fee: fill.fee,
                fee_rate: self.intent_processor.fee_rate(symbol),
                realized_pnl,
                strategy_name: strategy.to_string(),
                context_id,
                engine_mode: em,
            });
        }

        Ok(serde_json::json!({
            "order_id": order_id,
            "fill_qty": fill.fill_qty,
            "fill_price": fill.fill_price,
            "fee": fill.fee,
            "realized_pnl": realized_pnl,
        })
        .to_string())
    }

    pub fn risk_runtime_status_json(&self, now_ms: u64) -> serde_json::Value {
        let boot_remaining_ms = match self.boot_ts_ms {
            Some(boot_ts) => {
                let elapsed = now_ms.saturating_sub(boot_ts);
                self.boot_cooldown_ms.saturating_sub(elapsed)
            }
            None => 0,
        };
        serde_json::json!({
            "governor_tier": self.governance.risk.snapshot_level().to_string(),
            "consecutive_losses_by_symbol": self.consecutive_losses,
            "boot_cooldown_remaining_ms": boot_remaining_ms,
            "boot_cooldown_total_ms": self.boot_cooldown_ms,
            "paper_paused": self.paper_paused,
            "session_halted": self.session_halted,
        })
    }

    /// ARCH-RC1 1C-3-B-2: minimum interval (ms) between two operator-driven
    /// governor de-escalations. Default 24h. Demo phase only — for live this
    /// should be persisted to PG so a restart doesn't reset the cooldown.
    /// ARCH-RC1 1C-3-B-2：兩次 operator 降級之間的最短間隔（24h）。
    pub const GOVERNOR_DE_ESCALATION_COOLDOWN_MS: u64 = 24 * 60 * 60 * 1000;

    /// Whitelist of valid reason codes for `force_governor_tier_looser`.
    /// `force_governor_tier_looser` 的合法 reason code 白名單。
    pub const VALID_DE_ESCALATION_REASONS: &'static [&'static str] =
        &["false_positive", "root_cause_fixed", "accept_risk"];

    /// Parse a tier name (case-insensitive) into a `RiskLevel`.
    /// Accepts both display form ("CIRCUIT_BREAKER") and friendly aliases.
    /// 將 tier 名稱（大小寫不敏感）解析為 `RiskLevel`。
    pub fn parse_risk_level(s: &str) -> Result<openclaw_core::sm::risk_gov::RiskLevel, String> {
        use openclaw_core::sm::risk_gov::RiskLevel;
        match s.to_ascii_uppercase().as_str() {
            "NORMAL" => Ok(RiskLevel::Normal),
            "CAUTIOUS" => Ok(RiskLevel::Cautious),
            "REDUCED" => Ok(RiskLevel::Reduced),
            "DEFENSIVE" => Ok(RiskLevel::Defensive),
            "CIRCUIT_BREAKER" | "CIRCUITBREAKER" => Ok(RiskLevel::CircuitBreaker),
            "MANUAL_REVIEW" | "MANUALREVIEW" => Ok(RiskLevel::ManualReview),
            other => Err(format!("unknown risk tier: {other}")),
        }
    }

    /// ARCH-RC1 1C-3-B-2: in-memory cooldown getter (testable).
    /// ARCH-RC1 1C-3-B-2：in-memory 冷卻時間 getter（可測）。
    pub fn last_governor_de_escalation_ms(&self) -> Option<u64> {
        self.last_governor_de_escalation_ms
    }

    /// ARCH-RC1 1C-3-B-2: helper for tests to seed cooldown state.
    /// ARCH-RC1 1C-3-B-2：測試輔助設定冷卻時間戳。
    pub fn set_last_governor_de_escalation_ms(&mut self, ts: Option<u64>) {
        self.last_governor_de_escalation_ms = ts;
    }

    /// PNL-3 / Session 12: Update boot cooldown at runtime via IPC.
    /// Clamped to [0, 1h]. Returns the value actually applied.
    /// PNL-3：運行時更新啟動冷卻期，鉗制到 [0, 1h]。
    pub fn set_boot_cooldown_ms(&mut self, ms: u64) -> u64 {
        let v = ms.min(3_600_000);
        self.boot_cooldown_ms = v;
        v
    }

    pub fn boot_cooldown_ms(&self) -> u64 {
        self.boot_cooldown_ms
    }

    /// DB-RUN-1: Set signals heartbeat interval at runtime. 0 disables throttling.
    /// DB-RUN-1：運行時設定 signals 心跳間隔，0=關閉節流。
    pub fn set_signals_heartbeat_ms(&mut self, ms: u64) -> u64 {
        self.signals_heartbeat_ms = ms.min(3_600_000);
        self.signals_heartbeat_ms
    }

    pub fn signals_heartbeat_ms(&self) -> u64 {
        self.signals_heartbeat_ms
    }

    pub fn signals_throttled(&self) -> u64 {
        self.signals_throttled
    }

    pub fn context_throttled(&self) -> u64 {
        self.context_throttled
    }

    /// DB-RUN-3: Emit a TradingMsg::Fill row for a stop/risk-driven close so
    /// trading.fills records the realized PnL. Strategy is "risk_close" since
    /// these closes are not signal-driven. Counter on stats.total_fills.
    /// DB-RUN-3：為止損/風控平倉發送 Fill 訊息，使 trading.fills 記錄已實現損益。
    fn emit_close_fill(
        &mut self,
        symbol: &str,
        is_long: bool,
        qty: f64,
        price: f64,
        ts_ms: u64,
        realized_pnl: f64,
        reason: &str,
    ) {
        if let Some(ref tx) = self.trading_tx {
            // Fill side reflects the closing direction (opposite of position side).
            let close_side = if is_long { "Sell" } else { "Buy" };
            let fr = self.intent_processor.fee_rate(symbol);
            let _ = tx.try_send(crate::database::TradingMsg::Fill {
                fill_id: format!("close-{}-{}", symbol, ts_ms),
                ts_ms,
                order_id: format!("risk_close_{}_{}", symbol, ts_ms),
                symbol: symbol.to_string(),
                side: close_side.into(),
                qty,
                price,
                fee: 0.0, // close fees accrued by paper_state separately
                fee_rate: fr,
                realized_pnl,
                strategy_name: format!("risk_close:{reason}"),
                context_id: format!("ctx-{}-{}", symbol, ts_ms),
                engine_mode: self.pipeline_kind.db_mode().to_string(),
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
        tx: tokio::sync::mpsc::UnboundedSender<ShadowOrderRequest>,
    ) {
        self.shadow_order_tx = Some(tx);
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

    /// Process a single price event through the full pipeline.
    /// Returns a CanaryRecord when canary_mode is enabled (R07-2).
    /// 通過完整管線處理單個價格事件。
    /// 灰度模式啟用時返回 CanaryRecord。
    pub fn on_tick(&mut self, event: &PriceEvent) -> Option<CanaryRecord> {
        // Start timing the tick processing / 開始計時 tick 處理
        let tick_start = Instant::now();

        // ARCH-RC1 1C-2-B: hot-reload check — if RiskConfig store version has
        // bumped (IPC patch applied), refresh the intent_processor snapshot.
        // ARCH-RC1 1C-2-B：熱重載檢查 — RiskConfig store 版本有變即同步。
        self.sync_risk_config_if_changed();

        self.stats.total_ticks += 1;
        self.stats.last_tick_ms = event.ts_ms;
        // PNL-3: Stamp boot timestamp on first tick (used for cooldown gate below).
        // PNL-3：首個 tick 記錄啟動時間戳（用於下方冷卻期門控）。
        if self.boot_ts_ms.is_none() {
            self.boot_ts_ms = Some(event.ts_ms);
        }
        self.latest_prices
            .insert(event.symbol.clone(), event.last_price);
        self.paper_state
            .set_latest_price(&event.symbol, event.last_price);
        // RRC-1-B2: Reset daily start balance at UTC midnight for daily loss tracking.
        // RRC-1-B2：UTC 午夜重置每日起始餘額，用於日損追蹤。
        self.intent_processor
            .maybe_reset_daily_balance(self.paper_state.balance(), event.ts_ms);
        // RRC-1-C1: Feed price to tracker for ATR computation + spike detection.
        // RRC-1-C1：餵入價格到追蹤器，用於 ATR 計算 + 尖峰偵測。
        self.price_tracker
            .record(&event.symbol, event.last_price, event.ts_ms);
        // Update per-symbol turnover for dynamic slippage (from ticker events)
        // 更新每交易對成交額用於動態滑點（來自 ticker 事件）
        if event.turnover_24h > 0.0 {
            self.paper_state
                .set_latest_turnover(&event.symbol, event.turnover_24h);

            // Phase 1 (F-2 fix): Emit TickerSnapshot to market writer for ticker events.
            // Phase 1（F-2 修復）：為 ticker 事件發送 TickerSnapshot 到市場寫入器。
            if let Some(ref tx) = self.market_data_tx {
                let spread = if event.ask_price > 0.0 && event.bid_price > 0.0 {
                    (event.ask_price - event.bid_price) / event.last_price * 10_000.0
                } else {
                    0.0
                };
                let _ = tx.try_send(crate::database::MarketDataMsg::TickerSnapshot {
                    ts_ms: event.ts_ms,
                    symbol: event.symbol.clone(),
                    last_price: event.last_price,
                    mark_price: 0.0,  // not available in PriceEvent yet
                    index_price: 0.0, // not available in PriceEvent yet
                    best_bid: event.bid_price,
                    best_ask: event.ask_price,
                    bid_size: 0.0, // not available in PriceEvent yet
                    ask_size: 0.0, // not available in PriceEvent yet
                    volume_24h: event.volume_24h,
                    turnover_24h: event.turnover_24h,
                    spread_bps: spread,
                    open_interest: 0.0, // not available in PriceEvent yet
                });
            }
        }

        // Item 9 (M3 fix): ADL alert monitoring
        // 項目 9（M3 修復）：ADL 警報監控
        if event.metadata.get("type").map(|t| t.as_str()) == Some("adl_notice") {
            if let Some(rank_str) = event.metadata.get("adl_rank") {
                if let Ok(rank) = rank_str.parse::<u32>() {
                    self.adl_alerts
                        .push_back((event.ts_ms, event.symbol.clone(), rank));
                    if self.adl_alerts.len() > 50 {
                        self.adl_alerts.pop_front();
                    }
                    if rank >= 3 {
                        info!(
                            symbol = %event.symbol, rank = rank,
                            "⚠ ADL rank HIGH — consider reducing position / ADL 排名高，考慮減倉"
                        );
                    }
                }
            }
        }

        // Session 11: feed trade & orderbook events into 1-minute aggregators.
        // Flushes happen at minute boundaries → MarketDataMsg::TradeAgg1m / ObSnapshot.
        // Session 11：將 trade/orderbook 事件餵入 1 分鐘聚合器，跨分鐘時 flush。
        if let Some(event_type) = event.metadata.get("type").map(|s| s.as_str()) {
            match event_type {
                "trade" => {
                    let side = event
                        .metadata
                        .get("side")
                        .and_then(|s| crate::database::aggregators::TradeSide::parse(s));
                    let qty = event
                        .metadata
                        .get("qty")
                        .and_then(|s| s.parse::<f64>().ok())
                        .unwrap_or(0.0);
                    if let Some(side) = side {
                        if let Some(msg) = self.trade_aggregator.record(
                            &event.symbol,
                            side,
                            qty,
                            event.last_price,
                            event.ts_ms,
                        ) {
                            if let Some(ref tx) = self.market_data_tx {
                                let _ = tx.try_send(msg);
                            }
                        }
                    }
                }
                "orderbook" => {
                    let bids: Vec<(f64, f64)> = event
                        .metadata
                        .get("bids5")
                        .and_then(|s| serde_json::from_str(s).ok())
                        .unwrap_or_default();
                    let asks: Vec<(f64, f64)> = event
                        .metadata
                        .get("asks5")
                        .and_then(|s| serde_json::from_str(s).ok())
                        .unwrap_or_default();
                    if !bids.is_empty() && !asks.is_empty() {
                        if let Some(msg) = self.ob_aggregator.record(
                            &event.symbol,
                            &bids,
                            &asks,
                            event.ts_ms,
                        ) {
                            if let Some(ref tx) = self.market_data_tx {
                                let _ = tx.try_send(msg);
                            }
                        }
                    }
                }
                _ => {}
            }
        }

        // Step 0: Fast track check — emergency actions before normal processing
        let ft_action = crate::fast_track::evaluate_fast_track(
            self.governance.risk.level,
            0.0, // price_drop_pct computed externally
            0.0, // margin_utilization computed externally
        );
        if ft_action == crate::fast_track::FastTrackAction::CloseAll {
            let symbols: Vec<String> = self
                .paper_state
                .positions()
                .iter()
                .map(|p| p.symbol.clone())
                .collect();
            for sym in symbols {
                let pos_info = self
                    .paper_state
                    .get_position(&sym)
                    .map(|p| (p.is_long, p.qty));
                if let Some(pnl) = self
                    .paper_state
                    .close_position(&sym, event.last_price, event.ts_ms)
                {
                    if let Some((il, q)) = pos_info {
                        self.emit_close_fill(&sym, il, q, event.last_price, event.ts_ms, pnl, "fast_track");
                    }
                }
                self.stats.total_stops += 1;
            }
            // Measure elapsed time for fast-track exit / 計算快速通道退出的耗時
            let tick_duration_us = tick_start.elapsed().as_micros() as u64;
            return self.maybe_canary_record(event, None, vec![], vec![], tick_duration_us);
        }

        // Step 0.5: H0 Gate pre-check (shadow mode: observe only) / H0 門控前置檢查
        self.h0_gate.update_price_ts(&event.symbol, event.ts_ms);
        let h0_result = self.h0_gate.check(&event.symbol, "linear", event.ts_ms);
        let h0_allowed = h0_result.allowed;
        if !h0_result.allowed {
            // Hard block: stops only / 硬阻斷：僅處理止損
            warn!(symbol = %event.symbol, reason = %h0_result.reason,
                "H0 BLOCKED — stops only / H0 阻斷 — 僅止損");
            for (sym, trigger) in &self.paper_state.check_stops(event.last_price, event.ts_ms) {
                let pos_info = self
                    .paper_state
                    .get_position(sym)
                    .map(|p| (p.is_long, p.qty));
                if let Some(pnl) = self
                    .paper_state
                    .close_position(sym, event.last_price, event.ts_ms)
                {
                    if let Some((il, q)) = pos_info {
                        self.emit_close_fill(sym, il, q, event.last_price, event.ts_ms, pnl, &trigger.reason);
                    }
                }
                self.stats.total_stops += 1;
            }
            let dur = tick_start.elapsed().as_micros() as u64;
            return self.maybe_canary_record(event, None, vec![], vec![], dur);
        }
        if !h0_result.reason.is_empty() {
            debug!(symbol = %event.symbol, reason = %h0_result.reason,
                "H0 shadow would-block / H0 影子模式本應阻斷");
        }

        // Step 1: Kline aggregation — collect closed bars for DB write.
        // 步驟 1：K 線聚合 — 收集已關閉的 K 線用於 DB 寫入。
        let closed_bars = self.kline_manager.on_tick(
            &event.symbol,
            event.last_price,
            event.ts_ms,
            event.volume_24h,
            0.0,
        );

        // Phase 1: Emit KlineClose for each closed bar to market writer (F-2 audit fix).
        // Phase 1：為每根已關閉 K 線發送 KlineClose 到市場寫入器（F-2 審計修復）。
        if let Some(ref tx) = self.market_data_tx {
            for (timeframe, bar) in &closed_bars {
                if tx
                    .try_send(crate::database::MarketDataMsg::KlineClose {
                        symbol: event.symbol.clone(),
                        timeframe: timeframe.clone(),
                        bar: bar.clone(),
                    })
                    .is_err()
                {
                    self.market_tx_dropped += 1;
                }
            }
        }

        // DB-RUN-5: Feed black-swan detector on 1m bar close.
        // Compute log-return vs previous close, push into rolling window, run
        // 4-signal vote. Severity >= Observe → warn log. DB write deferred.
        // DB-RUN-5：1 分鐘 K 線收盤時餵入黑天鵝檢測器，4 信號投票，severity 達標時 warn。
        for (timeframe, bar) in &closed_bars {
            if timeframe != "1m" {
                continue;
            }
            let prev = self.last_close_price.insert(event.symbol.clone(), bar.close);
            let ret = match prev {
                Some(prev_close) if prev_close > 0.0 => (bar.close - prev_close) / prev_close,
                _ => 0.0,
            };
            self.black_swan.record_bar(&event.symbol, ret, bar.volume);
            let result = self.black_swan.check(&event.symbol, ret, bar.volume, event.ts_ms);
            use crate::database::black_swan_detector::BlackSwanSeverity;
            if !matches!(result.severity, BlackSwanSeverity::None) {
                warn!(
                    symbol = %event.symbol,
                    severity = ?result.severity,
                    votes = result.votes_for,
                    return_pct = format!("{:.4}%", ret * 100.0),
                    "BLACK SWAN signal / 黑天鵝信號"
                );
            }
        }

        // Step 2: Compute indicators (need enough 1m bars)
        // 步驟 2：計算指標（需要足夠的 1 分鐘 K 線）
        let indicators = self.compute_indicators(&event.symbol);

        // Store latest indicators for IPC snapshot / 存儲最新指標供 IPC 快照使用
        if let Some(ref ind) = indicators {
            self.latest_indicators
                .insert(event.symbol.clone(), ind.clone());
        }

        // Phase 1: Emit FeatureSnapshot to DB writer channel (non-blocking try_send).
        // Phase 1：發送 FeatureSnapshot 到 DB 寫入器通道（非阻塞 try_send）。
        if let (Some(ref tx), Some(ref ind)) = (&self.feature_tx, &indicators) {
            let snap = crate::feature_collector::FeatureSnapshot::new(
                event.symbol.clone(),
                event.ts_ms,
                event.last_price,
                event.volume_24h,
                ind.clone(),
                self.feature_version.clone(),
            );
            if tx.try_send(snap).is_err() {
                self.feature_tx_dropped += 1;
            }
        }

        // ── Pause gate: skip signal evaluation + strategy dispatch when paused ──
        // 暫停門控：暫停時跳過信號評估+策略分派（價格/指標/止損繼續）
        if self.paper_paused {
            // Protective stops while paused / 暫停時的保護性止損
            for (sym, trigger) in &self.paper_state.check_stops(event.last_price, event.ts_ms) {
                let pos_info = self
                    .paper_state
                    .get_position(sym)
                    .map(|p| (p.is_long, p.qty));
                debug!(symbol = %sym, reason = %trigger.reason, "stop (paused)");
                if let Some(pnl) = self
                    .paper_state
                    .close_position(sym, event.last_price, event.ts_ms)
                {
                    if let Some((il, q)) = pos_info {
                        self.emit_close_fill(sym, il, q, event.last_price, event.ts_ms, pnl, &trigger.reason);
                    }
                }
                self.stats.total_stops += 1;
                if let Some((is_long, qty)) = pos_info {
                    self.dispatch_close_order(sym, is_long, qty, event, false);
                }
            }
            let tick_duration_us = tick_start.elapsed().as_micros() as u64;
            return self.maybe_canary_record(event, indicators, vec![], vec![], tick_duration_us);
        }

        // PNL-3: Boot cooldown — suppress strategy signals for first N ms after boot.
        // Stops/indicators/feature snapshots continue to run; only intent generation is gated.
        // PNL-3：啟動冷卻期 — 啟動後 N 毫秒內抑制策略信號（止損/指標/快照繼續）。
        let in_boot_cooldown = match self.boot_ts_ms {
            Some(boot) => event.ts_ms.saturating_sub(boot) < self.boot_cooldown_ms,
            None => false,
        };

        // Step 3: Signal evaluation
        let signals = if in_boot_cooldown {
            debug!(
                symbol = %event.symbol,
                elapsed_ms = event.ts_ms.saturating_sub(self.boot_ts_ms.unwrap_or(event.ts_ms)),
                cooldown_ms = self.boot_cooldown_ms,
                "PNL-3 boot cooldown — signals suppressed / 啟動冷卻期 — 信號已抑制"
            );
            vec![]
        } else if let Some(ref ind) = indicators {
            let input = snapshot_to_input(ind);
            self.signal_engine
                .evaluate(&event.symbol, "1m", &input, event.ts_ms)
        } else {
            vec![]
        };

        // Store recent signals for IPC snapshot (ring buffer, max 100)
        // 存儲最近信號供 IPC 快照使用（環形緩衝，最大 100）
        let mut signals_persisted_this_tick = 0u32;
        for sig in &signals {
            self.recent_signals.push_back(sig.clone());
            if self.recent_signals.len() > 100 {
                self.recent_signals.pop_front();
            }

            // DB-RUN-1: Throttle signal persistence — only write on state change
            // or heartbeat interval. Reduces 352 rows/s to ~per-symbol-per-strat
            // change rate, expected 95%+ reduction.
            // DB-RUN-1：節流 signal 寫入 — 僅狀態變更或心跳到期時持久化。
            if !self.should_persist_signal(sig) {
                continue;
            }
            signals_persisted_this_tick += 1;

            // Phase 2a: Emit signal to trading_writer for PG persistence
            if let Some(ref tx) = self.trading_tx {
                let _ = tx.try_send(crate::database::TradingMsg::Signal {
                    signal_id: format!("sig-{}-{}", sig.source, sig.ts_ms),
                    ts_ms: sig.ts_ms,
                    symbol: sig.symbol.clone(),
                    strategy_name: sig.source.clone(),
                    timeframe: sig.timeframe.clone(),
                    signal_type: format!("{:?}", sig.direction),
                    strength: sig.confidence,
                    context_id: format!("ctx-{}-{}", sig.symbol, sig.ts_ms),
                });
            }
        }

        // DB-RUN-2: Decision context piggybacks on signal persistence — only emit
        // when at least one signal was actually persisted this tick. Reduces
        // 10.6M/day to ~36k/day (~99.6% drop) while preserving full fidelity at
        // every state-change / heartbeat boundary.
        // DB-RUN-2：decision_context 跟隨 signal 持久化 — 本 tick 至少 1 個 signal
        // 被寫入時才發送 context。降幅 ~99.6%，狀態變更與心跳邊界仍保留完整快照。
        if !signals.is_empty() && signals_persisted_this_tick == 0 {
            self.context_throttled += 1;
        }
        if signals_persisted_this_tick > 0 {
            if let Some(ref tx) = self.context_tx {
                // P2 refactor (2026-04-07): the LinUCB arm selection + news
                // snapshot read + DecisionContextMsg construction (~140 lines)
                // were extracted to `decision_context_producer.rs` to keep
                // tick_pipeline.rs under the §九 1200-line hard limit. The
                // logic is unchanged — see that module's MODULE_NOTE for the
                // full whitelist + fail-soft contract.
                // P2 重構（2026-04-07）：LinUCB arm 選擇 + 新聞快照讀取 +
                // DecisionContextMsg 構造（~140 行）已抽出至
                // `decision_context_producer.rs`，讓 tick_pipeline.rs 保持
                // 在 §九 1200 行硬上限以下。邏輯未變動 — 完整白名單與
                // fail-soft 合約見該模組 MODULE_NOTE。
                crate::decision_context_producer::emit_decision_context(
                    tx,
                    event,
                    &signals,
                    indicators.as_ref(),
                    self.paper_state.get_position(&event.symbol),
                    self.paper_state.balance(),
                    self.paper_state.drawdown_pct(),
                    self.linucb.as_ref(),
                    self.news_snapshot.as_ref(),
                    self.pipeline_kind.db_mode(),
                );
            }
        }

        // Step 4+5: Per-strategy dispatch + intent processing with rejection/fill callbacks (RC-04/RC-05).
        // 步驟 4+5：逐策略分派 + 意圖處理，含拒絕/成交回調。
        let ctx = TickContext {
            symbol: event.symbol.clone(),
            price: event.last_price,
            timestamp_ms: event.ts_ms,
            indicators: indicators.clone(),
            signals: signals.clone(),
            h0_allowed, // RRC-1-A1: real H0 gate result from Step 0.5
        };

        // NOTE: Current rejection rollback assumes each strategy emits at most 1 intent per tick.
        // If a strategy ever emits >1, partial rejection + partial fill could leave inconsistent state.
        // All current strategies satisfy this constraint. Revisit if multi-intent strategies are added.
        // 注意：當前拒絕回滾假設每策略每 tick 最多發出 1 個意圖。所有當前策略滿足此約束。
        // Exchange mode = any mode that routes real orders to an exchange (Demo or Live)
        // 交易所模式 = 向交易所發送真實訂單的任何模式（Demo 或 Live）
        let is_exchange_mode = self.pipeline_kind.is_exchange();

        // System mode gate — blocks trading based on GUI-set global mode.
        // ObserveOnly/DesignOnly: no trading of any kind (scanner + market data continue).
        // ShadowOnly: only paper simulation; exchange intents suppressed.
        // DemoReserved: live engine blocked (Demo + Paper allowed).
        // LiveReserved: all engines allowed (default).
        // 系統模式門控 — 根據 GUI 設置的全局模式封鎖交易。
        {
            let block = match self.system_mode {
                SystemMode::ObserveOnly | SystemMode::DesignOnly => true,
                SystemMode::ShadowOnly if is_exchange_mode => true,
                SystemMode::DemoReserved
                    if self.pipeline_kind == PipelineKind::Live =>
                {
                    true
                }
                _ => false,
            };
            if block {
                let tick_duration_us = tick_start.elapsed().as_micros() as u64;
                return self.maybe_canary_record(
                    event,
                    indicators,
                    signals,
                    vec![],
                    tick_duration_us,
                );
            }
        }

        // Extract ATR for cost gate (Gate 3) / 提取 ATR 用於成本門控
        let atr_value = indicators
            .as_ref()
            .and_then(|i| i.atr_14.as_ref())
            .map(|a| a.atr)
            .unwrap_or(0.0);

        let mut intents: Vec<crate::intent_processor::OrderIntent> = Vec::new();
        let mut pending_strategy_closes: Vec<(String, String)> = Vec::new();
        for strategy in self.orchestrator.strategies_mut() {
            if !strategy.is_active() {
                continue;
            }
            let strategy_actions = strategy.on_tick(&ctx);
            debug_assert!(
                strategy_actions.len() <= 1,
                "Strategy {} emitted {} actions in one tick — rollback assumes max 1",
                strategy.name(),
                strategy_actions.len()
            );
            for action in &strategy_actions {
                match action {
                // ═══════════════════════════════════════════════════════════════
                // StrategyAction::Open — full governance pipeline (unchanged)
                // StrategyAction::Open — 完整治理管線（不變）
                // ═══════════════════════════════════════════════════════════════
                StrategyAction::Open(intent) => {
                if is_exchange_mode {
                    // ═══ EXCHANGE MODE: gates only, send order to exchange ═══
                    // ═══ 交易所模式：僅過門禁，發送訂單到交易所 ═══
                    let gate = self.intent_processor.process_gates_only(
                        intent,
                        &self.governance,
                        &self.paper_state,
                        atr_value,
                        GovernanceProfile::Production, // TODO(3E-2b): derive from self.pipeline_kind
                    );

                    // Persist Guardian verdict (all verdicts including rejections) / 持久化 Guardian 裁定（含拒絕）
                    if let (Some(ref tx), Some(ref vi)) = (&self.trading_tx, &gate.verdict_info) {
                        let _ = tx.try_send(crate::database::TradingMsg::RiskVerdict {
                            verdict_id: format!("vrd-{}-{}", intent.symbol, event.ts_ms),
                            ts_ms: event.ts_ms,
                            intent_id: format!("intent-{}-{}", intent.symbol, event.ts_ms),
                            context_id: format!("ctx-{}-{}", intent.symbol, event.ts_ms),
                            symbol: intent.symbol.clone(),
                            verdict: vi.verdict.clone(),
                            risk_score: vi.risk_score,
                            reasons: vi.reasons.clone(),
                            modified_qty: vi.modified_qty,
                            engine_mode: self.pipeline_kind.db_mode().to_string(),
                        });
                    }

                    if gate.approved {
                        self.stats.total_intents += 1;

                        // Phase 3b fix: Emit Intent to trading_tx for PG persistence.
                        // Phase 3b 修復：發送 Intent 到 trading_tx 以持久化到 PG。
                        if let Some(ref tx) = self.trading_tx {
                            let _ = tx.try_send(crate::database::TradingMsg::Intent {
                                intent_id: format!("intent-{}-{}", intent.symbol, event.ts_ms),
                                ts_ms: event.ts_ms,
                                signal_id: String::new(),
                                context_id: format!("ctx-{}-{}", intent.symbol, event.ts_ms),
                                symbol: intent.symbol.clone(),
                                side: if intent.is_long {
                                    "Buy".into()
                                } else {
                                    "Sell".into()
                                },
                                qty: gate.approved_qty,
                                price: event.last_price,
                                order_type: intent.order_type.clone(),
                                strategy_name: intent.strategy.clone(),
                                engine_mode: self.pipeline_kind.db_mode().to_string(),
                            });
                        }

                        self.exchange_seq = self.exchange_seq.wrapping_add(1);
                        let order_link_id = format!("oc_{}_{}", event.ts_ms, self.exchange_seq);

                        // Round to exchange precision / 取整至交易所精度
                        let final_qty = if let Some(ref icache) = self.instrument_cache {
                            if let Some(spec) = icache.get(&intent.symbol) {
                                spec.round_qty(gate.approved_qty)
                            } else {
                                gate.approved_qty
                            }
                        } else {
                            gate.approved_qty
                        };

                        // P0-2 fix: Skip if qty rounded to zero / 數量取整為零則跳過
                        if final_qty <= 0.0 {
                            warn!(symbol = %intent.symbol, "exchange order skipped: qty=0 after rounding");
                            continue;
                        }

                        self.recent_intents.push_back(TimestampedIntent {
                            timestamp_ms: event.ts_ms,
                            intent: intent.clone(),
                            result: format!("pending_exchange:{}", order_link_id),
                        });
                        if self.recent_intents.len() > 50 {
                            self.recent_intents.pop_front();
                        }

                        // Dispatch to exchange / 派發到交易所
                        // I-08 雙軌止損：compute broker-side SL from stop config
                        let sl_pct = self.paper_state.stop_config_pct();
                        let broker_sl = if sl_pct > 0.0 {
                            Some(if intent.is_long {
                                event.last_price * (1.0 - sl_pct / 100.0)
                            } else {
                                event.last_price * (1.0 + sl_pct / 100.0)
                            })
                        } else {
                            None
                        };
                        if let Some(ref tx) = self.shadow_order_tx {
                            let _ = tx.send(ShadowOrderRequest {
                                symbol: intent.symbol.clone(),
                                is_long: intent.is_long,
                                qty: final_qty,
                                price: event.last_price,
                                strategy: intent.strategy.clone(),
                                paper_fill_ts: event.ts_ms,
                                is_close: false,
                                order_link_id,
                                is_primary: true,
                                stop_loss: broker_sl,
                                take_profit: None,
                            });
                        }
                    } else if let Some(ref reason) = gate.rejected_reason {
                        strategy.on_rejection(intent, reason);
                        self.recent_intents.push_back(TimestampedIntent {
                            timestamp_ms: event.ts_ms,
                            intent: intent.clone(),
                            result: format!("rejected:{}", reason),
                        });
                        if self.recent_intents.len() > 50 {
                            self.recent_intents.pop_front();
                        }
                    }
                } else {
                    // ═══ PAPER_ONLY MODE: simulate fill locally + optional shadow order ═══
                    // ═══ 紙盤模式：本地模擬成交 + 可選影子訂單 ═══
                    let result = self.intent_processor.process(
                        intent,
                        &self.governance,
                        &self.paper_state,
                        atr_value,
                        GovernanceProfile::Exploration, // TODO(3E-2b): derive from self.pipeline_kind
                    );

                    // Persist Guardian verdict (all verdicts including rejections) / 持久化 Guardian 裁定（含拒絕）
                    if let (Some(ref tx), Some(ref vi)) = (&self.trading_tx, &result.verdict_info) {
                        let _ = tx.try_send(crate::database::TradingMsg::RiskVerdict {
                            verdict_id: format!("vrd-{}-{}", intent.symbol, event.ts_ms),
                            ts_ms: event.ts_ms,
                            intent_id: format!("intent-{}-{}", intent.symbol, event.ts_ms),
                            context_id: format!("ctx-{}-{}", intent.symbol, event.ts_ms),
                            symbol: intent.symbol.clone(),
                            verdict: vi.verdict.clone(),
                            risk_score: vi.risk_score,
                            reasons: vi.reasons.clone(),
                            modified_qty: vi.modified_qty,
                            engine_mode: self.pipeline_kind.db_mode().to_string(),
                        });
                    }

                    if result.submitted {
                        self.stats.total_intents += 1;
                        self.recent_intents.push_back(TimestampedIntent {
                            timestamp_ms: event.ts_ms,
                            intent: intent.clone(),
                            result: "submitted".into(),
                        });
                        if self.recent_intents.len() > 50 {
                            self.recent_intents.pop_front();
                        }

                        // Phase 3b fix: Emit Intent to trading_tx for PG persistence.
                        // Phase 3b 修復：發送 Intent 到 trading_tx 以持久化到 PG。
                        if let Some(ref tx) = self.trading_tx {
                            let _ = tx.try_send(crate::database::TradingMsg::Intent {
                                intent_id: format!("intent-{}-{}", intent.symbol, event.ts_ms),
                                ts_ms: event.ts_ms,
                                signal_id: String::new(),
                                context_id: format!("ctx-{}-{}", intent.symbol, event.ts_ms),
                                symbol: intent.symbol.clone(),
                                side: if intent.is_long {
                                    "Buy".into()
                                } else {
                                    "Sell".into()
                                },
                                qty: intent.qty,
                                price: event.last_price,
                                order_type: intent.order_type.clone(),
                                strategy_name: intent.strategy.clone(),
                                engine_mode: self.pipeline_kind.db_mode().to_string(),
                            });
                        }

                        if let Some(mut fill) = result.fill {
                            if let Some(ref icache) = self.instrument_cache {
                                if let Some(spec) = icache.get(&intent.symbol) {
                                    fill.fill_qty = spec.round_qty(fill.fill_qty);
                                    fill.fill_price = spec.round_price(fill.fill_price);
                                    // Paper min-qty fallback: if rounding reduced to 0, use min_qty
                                    // so high-priced assets (BTC/ETH) can still accumulate fill data.
                                    // Guard: min_qty notional must not exceed 10% of balance.
                                    // Paper 最小手數後備：取整為 0 時使用 min_qty，
                                    // 讓高價資產（BTC/ETH）仍能積累成交數據。
                                    // 防護：min_qty 名義值不得超過餘額的 10%。
                                    if fill.fill_qty <= 0.0 && spec.min_qty > 0.0 {
                                        let notional = spec.min_qty * fill.fill_price;
                                        let balance = self.paper_state.balance();
                                        if notional <= balance * 0.10 {
                                            info!(symbol = %intent.symbol, min_qty = spec.min_qty,
                                                  "paper fill: qty rounded to 0, using min_qty fallback / 數量取整為 0，使用最小手數");
                                            fill.fill_qty = spec.min_qty;
                                        }
                                    }
                                }
                            }
                            // Guard: skip zero-qty fills (instrument rounding can reduce to 0)
                            // 防護：跳過零數量成交（合約精度取整可能降為 0）
                            if fill.fill_qty <= 0.0 {
                                warn!(symbol = %intent.symbol, "paper fill skipped: qty=0 after rounding");
                                continue;
                            }
                            strategy.on_fill(intent, &fill);
                            let realized_pnl = self.paper_state.apply_fill(
                                &intent.symbol,
                                intent.is_long,
                                fill.fill_qty,
                                fill.fill_price,
                                fill.fee,
                                event.ts_ms,
                            );
                            self.stats.total_fills += 1;
                            self.recent_fills.push_back(TimestampedFill {
                                timestamp_ms: event.ts_ms,
                                symbol: intent.symbol.clone(),
                                is_long: intent.is_long,
                                qty: fill.fill_qty,
                                price: fill.fill_price,
                                fee: fill.fee,
                                strategy: intent.strategy.clone(),
                            });
                            if self.recent_fills.len() > 50 {
                                self.recent_fills.pop_front();
                            }

                            if let Some(ref tx) = self.trading_tx {
                                let _ = tx.try_send(crate::database::TradingMsg::Fill {
                                    fill_id: format!("fill-{}-{}", intent.symbol, event.ts_ms),
                                    ts_ms: event.ts_ms,
                                    order_id: format!("order-{}-{}", intent.symbol, event.ts_ms),
                                    symbol: intent.symbol.clone(),
                                    side: if intent.is_long {
                                        "Buy".into()
                                    } else {
                                        "Sell".into()
                                    },
                                    qty: fill.fill_qty,
                                    price: fill.fill_price,
                                    fee: fill.fee,
                                    fee_rate: self.intent_processor.fee_rate(&intent.symbol),
                                    realized_pnl,
                                    strategy_name: intent.strategy.clone(),
                                    context_id: format!("ctx-{}-{}", intent.symbol, event.ts_ms),
                                    engine_mode: self.pipeline_kind.db_mode().to_string(),
                                });
                            }

                            if let Some(ref tx) = self.stop_request_tx {
                                if let Some(pos) = self.paper_state.get_position(&intent.symbol) {
                                    let stop_pct = self.paper_state.stop_config_pct();
                                    let sl_price = if pos.is_long {
                                        pos.entry_price * (1.0 - stop_pct / 100.0)
                                    } else {
                                        pos.entry_price * (1.0 + stop_pct / 100.0)
                                    };
                                    let _ = tx.send(StopRequest {
                                        symbol: intent.symbol.clone(),
                                        stop_loss: sl_price,
                                        is_long: pos.is_long,
                                    });
                                }
                            }

                            // Shadow order: mirror paper fill to Demo API
                            if let Some(ref tx) = self.shadow_order_tx {
                                self.exchange_seq = self.exchange_seq.wrapping_add(1);
                                let _ = tx.send(ShadowOrderRequest {
                                    symbol: intent.symbol.clone(),
                                    is_long: intent.is_long,
                                    qty: fill.fill_qty,
                                    price: fill.fill_price,
                                    strategy: intent.strategy.clone(),
                                    paper_fill_ts: event.ts_ms,
                                    is_close: false,
                                    order_link_id: format!(
                                        "sh_{}_{}",
                                        event.ts_ms, self.exchange_seq
                                    ),
                                    is_primary: false,
                                    stop_loss: None,
                                    take_profit: None,
                                });
                            }
                        }
                    } else if let Some(ref reason) = result.rejected_reason {
                        strategy.on_rejection(intent, reason);
                        self.recent_intents.push_back(TimestampedIntent {
                            timestamp_ms: event.ts_ms,
                            intent: intent.clone(),
                            result: format!("rejected:{}", reason),
                        });
                        if self.recent_intents.len() > 50 {
                            self.recent_intents.pop_front();
                        }
                    }
                }
                intents.push(intent.clone());
                } // end StrategyAction::Open

                // StrategyAction::Close — collected for deferred execution after strategy loop
                // (borrow checker: strategies_mut() borrows self, can't call self methods inline)
                // StrategyAction::Close — 收集後在策略循環結束後延遲執行
                StrategyAction::Close { symbol, confidence: _, reason } => {
                    pending_strategy_closes.push((symbol.clone(), reason.clone()));
                }
                } // end match
            }
        }

        // ═══════════════════════════════════════════════════════════════════════
        // Deferred strategy close execution — outside strategies_mut() borrow scope.
        // 延遲執行策略平倉 — 在 strategies_mut() 借用範圍之外。
        // Close reduces risk (not increases it), so Guardian/cost_gate/Kelly/P1 are skipped.
        // Retains: fee accounting, PG persistence, shadow order, Kelly stats, audit trail.
        // ═══════════════════════════════════════════════════════════════════════
        // Track confirmed/skipped closes for strategy callbacks after execution.
        // 追蹤已確認/跳過的平倉，供執行後的策略回調使用。
        let mut close_confirmed_symbols: Vec<String> = Vec::new();
        let mut close_skipped_symbols: Vec<String> = Vec::new();

        for (symbol, reason) in &pending_strategy_closes {
            // P2 fix: synthetic intent for monitoring/audit (recent_intents ring buffer).
            // P2 修復：合成 intent 供監控/審計（recent_intents 環形緩衝）。
            let close_intent = crate::intent_processor::OrderIntent {
                symbol: symbol.clone(),
                is_long: false, // direction filled in below if position found
                qty: 0.0,
                confidence: 0.0,
                strategy: format!("strategy_close:{reason}"),
                order_type: "market".into(),
                limit_price: None,
            };
            if is_exchange_mode {
                if self.pending_close_symbols.contains(symbol) {
                    warn!(symbol = %symbol, reason = %reason, "strategy close skipped: pending close exists / 策略平倉跳過：已有待處理平倉");
                    self.recent_intents.push_back(TimestampedIntent {
                        timestamp_ms: event.ts_ms,
                        intent: close_intent,
                        result: format!("close_skipped:pending_{reason}"),
                    });
                    if self.recent_intents.len() > 50 { self.recent_intents.pop_front(); }
                    close_skipped_symbols.push(symbol.clone());
                    continue;
                }
                if let Some(pos) = self.paper_state.get_position(symbol) {
                    let is_long = pos.is_long;
                    let qty = pos.qty;
                    info!(symbol = %symbol, is_long = %is_long, qty = %qty, reason = %reason,
                          "strategy close → exchange / 策略平倉 → 交易所");
                    self.dispatch_close_order(symbol, is_long, qty, event, true);
                    self.recent_intents.push_back(TimestampedIntent {
                        timestamp_ms: event.ts_ms,
                        intent: close_intent,
                        result: format!("close_dispatched:{reason}"),
                    });
                    if self.recent_intents.len() > 50 { self.recent_intents.pop_front(); }
                    close_confirmed_symbols.push(symbol.clone());
                } else {
                    warn!(symbol = %symbol, reason = %reason, "strategy close skipped: no position found / 策略平倉跳過：未找到倉位");
                    self.recent_intents.push_back(TimestampedIntent {
                        timestamp_ms: event.ts_ms,
                        intent: close_intent,
                        result: format!("close_skipped:no_position_{reason}"),
                    });
                    if self.recent_intents.len() > 50 { self.recent_intents.pop_front(); }
                    close_skipped_symbols.push(symbol.clone());
                }
            } else {
                if let Some(pos) = self.paper_state.get_position(symbol) {
                    let is_long = pos.is_long;
                    let qty = pos.qty;
                    info!(symbol = %symbol, is_long = %is_long, qty = %qty, reason = %reason,
                          "strategy close (paper) / 策略平倉（紙盤）");
                    if let Some(pnl) = self.paper_state.close_position(symbol, event.last_price, event.ts_ms) {
                        self.emit_close_fill(symbol, is_long, qty, event.last_price, event.ts_ms, pnl, reason);
                        // Update Kelly stats for future sizing / 更新 Kelly 統計供未來 sizing 使用
                        self.intent_processor.record_trade(symbol, pnl);
                        // Push to recent_fills ring buffer / 推入最近成交環形緩衝
                        let fr = self.intent_processor.fee_rate(symbol);
                        self.recent_fills.push_back(TimestampedFill {
                            timestamp_ms: event.ts_ms,
                            symbol: symbol.clone(),
                            is_long,
                            qty,
                            price: event.last_price,
                            fee: qty * event.last_price * fr,
                            strategy: format!("strategy_close:{reason}"),
                        });
                        if self.recent_fills.len() > 50 {
                            self.recent_fills.pop_front();
                        }
                        // Track consecutive losses for risk evaluator
                        // 追蹤連續虧損供風控評估器使用
                        if pnl < 0.0 {
                            *self.consecutive_losses.entry(symbol.clone()).or_insert(0) += 1;
                        } else {
                            self.consecutive_losses.remove(symbol);
                        }
                    }
                    // Shadow order: mirror close to Demo API / 影子訂單：鏡像平倉到 Demo API
                    self.dispatch_close_order(symbol, is_long, qty, event, false);
                    self.recent_intents.push_back(TimestampedIntent {
                        timestamp_ms: event.ts_ms,
                        intent: close_intent,
                        result: format!("close_filled:{reason}"),
                    });
                    if self.recent_intents.len() > 50 { self.recent_intents.pop_front(); }
                    close_confirmed_symbols.push(symbol.clone());
                } else {
                    warn!(symbol = %symbol, reason = %reason, "strategy close skipped: no position found / 策略平倉跳過：未找到倉位");
                    self.recent_intents.push_back(TimestampedIntent {
                        timestamp_ms: event.ts_ms,
                        intent: close_intent,
                        result: format!("close_skipped:no_position_{reason}"),
                    });
                    if self.recent_intents.len() > 50 { self.recent_intents.pop_front(); }
                    close_skipped_symbols.push(symbol.clone());
                }
            }
        }

        // Notify strategies of close outcomes (P1 fix: prevents grid inventory drift on skipped close).
        // 通知策略平倉結果（P1 修復：防止 grid 庫存在跳過平倉時漂移）。
        for strategy in self.orchestrator.strategies_mut() {
            for sym in &close_confirmed_symbols {
                strategy.on_close_confirmed(sym);
            }
            for sym in &close_skipped_symbols {
                strategy.on_close_skipped(sym);
            }
        }

        // Step 6: Position risk checks — 9-check (RRC-1-C2, replaces basic check_stops).
        // 步驟 6：持倉風控 9 項檢查（RRC-1-C2，替代基本止損）。
        //
        // P2 refactor (2026-04-07): per-position math (pnl_pct / peak_pnl_pct /
        // holding_hours / cost_ratio + check_position_on_tick) extracted to
        // `position_risk_evaluator::evaluate_positions`. Decision-vs-mechanism
        // split: that module computes WHAT to do (pure), the dispatch loop
        // below executes the side-effects (close / halt / cooldown). Behavior
        // preserved because the original code already snapshotted positions
        // into a Vec before dispatching, so reading-then-acting in two phases
        // is identical to the inline form.
        // P2 重構（2026-04-07）：逐倉計算抽出至 position_risk_evaluator；
        // 派發迴圈仍負責所有副作用，行為與原始碼一致。
        self.paper_state.update_best_prices();
        let session_drawdown = self.paper_state.drawdown_pct();
        let daily_loss = self
            .intent_processor
            .daily_loss_pct_pub(self.paper_state.balance());
        let risk_config = self.intent_processor.risk_config().clone();
        let position_rows: Vec<crate::position_risk_evaluator::PositionRow> = self
            .paper_state
            .positions()
            .iter()
            .map(|p| {
                let current_price = self
                    .latest_prices
                    .get(&p.symbol)
                    .copied()
                    .unwrap_or(p.entry_price);
                crate::position_risk_evaluator::PositionRow {
                    symbol: p.symbol.clone(),
                    is_long: p.is_long,
                    qty: p.qty,
                    entry_price: p.entry_price,
                    entry_ts_ms: p.entry_ts_ms,
                    peak_price: p.best_price,
                    current_price,
                    atr_pct: self.price_tracker.compute_atr_pct(&p.symbol),
                    fee_rate: self.intent_processor.fee_rate(&p.symbol),
                    regime: self.derive_regime(self.latest_indicators.get(&p.symbol)),
                    consecutive_losses: self
                        .consecutive_losses
                        .get(&p.symbol)
                        .copied()
                        .unwrap_or(0),
                }
            })
            .collect();
        // ARCH-RC1 1C-2-B: live read from BudgetConfig store (falls back to
        // 0.8 in tests where store is not wired).
        // ARCH-RC1 1C-2-B：從 BudgetConfig store 即時讀取；未接線時回退 0.8。
        let cost_edge_max_ratio = self.current_cost_edge_max_ratio();
        let decisions = crate::position_risk_evaluator::evaluate_positions(
            &position_rows,
            daily_loss,
            session_drawdown,
            event.ts_ms,
            cost_edge_max_ratio,
            &risk_config,
        );

        let mut risk_closed_symbols: Vec<String> = Vec::new();
        for decision in &decisions {
            let symbol = &decision.symbol;
            let is_long = &decision.is_long;
            let qty = &decision.qty;
            let pnl_pct = &decision.pnl_pct;
            let _entry_ts_ms = &decision.entry_ts_ms;
            match decision.action.clone() {
                RiskAction::Hold => {} // no action / 無動作
                RiskAction::ClosePosition(reason) => {
                    risk_closed_symbols.push(symbol.clone());
                    if is_exchange_mode {
                        if self.pending_close_symbols.contains(symbol) {
                            continue;
                        }
                        warn!(symbol = %symbol, reason = %reason, "risk close → exchange / 風控平倉 → 交易所");
                        self.dispatch_close_order(symbol, *is_long, *qty, event, true);
                    } else {
                        warn!(symbol = %symbol, reason = %reason, "risk close (paper) / 風控平倉（紙盤）");
                        if *pnl_pct < 0.0 {
                            *self.consecutive_losses.entry(symbol.clone()).or_insert(0) += 1;
                        } else {
                            self.consecutive_losses.remove(symbol);
                        }
                        if let Some(pnl) = self
                            .paper_state
                            .close_position(symbol, event.last_price, event.ts_ms)
                        {
                            self.emit_close_fill(symbol, *is_long, *qty, event.last_price, event.ts_ms, pnl, &reason);
                            // P1-2 fix: update Kelly stats for risk-close (pre-existing omission).
                            // P1-2 修復：風控平倉也更新 Kelly 統計（既有遺漏）。
                            self.intent_processor.record_trade(symbol, pnl);
                        }
                        self.stats.total_stops += 1;
                        self.dispatch_close_order(symbol, *is_long, *qty, event, false);
                    }
                }
                RiskAction::HaltSession(reason) => {
                    // RRC-1-C4: Circuit breaker — halt + close all / 熔斷 — 暫停+全部平倉
                    warn!(reason = %reason, "SESSION HALTED / 會話暫停");
                    self.session_halted = true;
                    self.paper_paused = true;
                    let all_pos: Vec<(String, bool, f64)> = self
                        .paper_state
                        .positions()
                        .iter()
                        .map(|p| (p.symbol.clone(), p.is_long, p.qty))
                        .collect();
                    for (sym, _, _) in &all_pos {
                        risk_closed_symbols.push(sym.clone());
                    }
                    for (sym, il, q) in &all_pos {
                        // Q1 fix: skip already-dispatched closes / 跳過已派發的平倉
                        if is_exchange_mode && self.pending_close_symbols.contains(sym) {
                            continue;
                        }
                        let px = self
                            .latest_prices
                            .get(sym)
                            .copied()
                            .unwrap_or(event.last_price);
                        if let Some(pnl) =
                            self.paper_state.close_position(sym, px, event.ts_ms)
                        {
                            self.emit_close_fill(sym, *il, *q, px, event.ts_ms, pnl, "halt_session");
                        }
                        self.stats.total_stops += 1;
                        self.dispatch_close_order(sym, *il, *q, event, is_exchange_mode);
                    }
                    break;
                }
                RiskAction::SetCooldown(ms) => {
                    // RRC-1-C4: Set cooldown on H0Gate to suppress new orders.
                    // RRC-1-C4：在 H0 門控設置冷卻期，抑制新訂單。
                    let until_ms = event.ts_ms + ms;
                    info!(cooldown_ms = ms, symbol = %symbol,
                        "cooldown set by risk check / 風控設置冷卻期");
                    self.h0_gate
                        .update_risk(openclaw_types::H0GateRiskSnapshot {
                            open_position_count: self.paper_state.positions().len() as u32,
                            total_exposure_pct: 0.0, // recalculated next status interval
                            cooldown_until_ts_ms: until_ms,
                            kill_switch_active: false,
                            snapshot_ts_ms: event.ts_ms,
                        });
                }
            }
        }

        // Notify strategies of externally-closed positions (risk-stop/halt)
        // so they can reset internal state (e.g., grid net_inventory, position flag).
        // 通知策略外部平倉的倉位（風控止損/熔斷），讓策略重設內部狀態。
        if !risk_closed_symbols.is_empty() {
            for strategy in self.orchestrator.strategies_mut() {
                for sym in &risk_closed_symbols {
                    strategy.on_external_close(sym);
                }
            }
        }

        if self.stats.total_ticks % 1000 == 0 {
            info!(
                ticks = self.stats.total_ticks,
                fills = self.stats.total_fills,
                "tick stats"
            );

            // GAP-7 / idle-writer-fix #4: emit PositionSnapshot for every open
            // paper position every 1000 ticks so trading.position_snapshots
            // stays populated for ML training.
            // GAP-7：每 1000 ticks 發射持倉快照以填充 position_snapshots 表。
            if let Some(ref tx) = self.trading_tx {
                for pos in self.paper_state.positions() {
                    let mark_price = *self
                        .latest_prices
                        .get(&pos.symbol)
                        .unwrap_or(&pos.entry_price);
                    let unrealized_pnl = if pos.is_long {
                        (mark_price - pos.entry_price) * pos.qty
                    } else {
                        (pos.entry_price - mark_price) * pos.qty
                    };
                    let msg = crate::database::TradingMsg::PositionSnapshot {
                        ts_ms: event.ts_ms,
                        symbol: pos.symbol.clone(),
                        side: if pos.is_long {
                            "long".to_string()
                        } else {
                            "short".to_string()
                        },
                        qty: pos.qty,
                        entry_price: pos.entry_price,
                        mark_price,
                        unrealized_pnl,
                        engine_mode: self.pipeline_kind.db_mode().to_string(),
                    };
                    let _ = tx.try_send(msg);
                }
            }
        }

        // Measure elapsed time for the full tick / 計算完整 tick 處理耗時
        let tick_duration_us = tick_start.elapsed().as_micros() as u64;
        self.maybe_canary_record(event, indicators, signals, intents, tick_duration_us)
    }

    /// EXT-1: Apply a confirmed fill from the exchange to paper_state.
    /// Called by event_consumer when exchange confirms a fill for a pending order.
    /// EXT-1：將交易所確認的成交應用到 paper_state。
    pub fn apply_confirmed_fill(
        &mut self,
        symbol: &str,
        is_long: bool,
        qty: f64,
        fill_price: f64,
        fee: f64,
        ts_ms: u64,
        strategy: &str,
        order_link_id: &str,
    ) {
        let realized_pnl = self
            .paper_state
            .apply_fill(symbol, is_long, qty, fill_price, fee, ts_ms);
        self.stats.total_fills += 1;
        // Update Kelly stats on exchange fill (previously missing — QC P2-2 fix).
        // Non-zero realized_pnl indicates a position close (open fills return 0.0).
        // 交易所成交時更新 Kelly 統計（先前遺漏 — QC P2-2 修復）。
        // 非零 realized_pnl 表示平倉成交（開倉成交返回 0.0）。
        if realized_pnl.abs() > f64::EPSILON {
            self.intent_processor.record_trade(symbol, realized_pnl);
        }
        // Clear pending_close flag if this was a close fill / 如果是平倉成交，清除待處理平倉標記
        self.pending_close_symbols.remove(symbol);

        self.recent_fills.push_back(TimestampedFill {
            timestamp_ms: ts_ms,
            symbol: symbol.to_string(),
            is_long,
            qty,
            price: fill_price,
            fee,
            strategy: strategy.to_string(),
        });
        if self.recent_fills.len() > 50 {
            self.recent_fills.pop_front();
        }

        if let Some(ref tx) = self.trading_tx {
            let fr = self.intent_processor.fee_rate(symbol);
            let _ = tx.try_send(crate::database::TradingMsg::Fill {
                fill_id: format!("fill-{}-{}", symbol, ts_ms),
                ts_ms,
                order_id: order_link_id.to_string(),
                symbol: symbol.to_string(),
                side: if is_long { "Buy".into() } else { "Sell".into() },
                qty,
                price: fill_price,
                fee,
                fee_rate: fr,
                realized_pnl,
                strategy_name: strategy.to_string(),
                context_id: format!("ctx-{}-{}", symbol, ts_ms),
                engine_mode: self.pipeline_kind.db_mode().to_string(),
            });
        }

        info!(
            symbol = %symbol, qty = %qty, price = %fill_price,
            order_link_id = %order_link_id,
            "confirmed fill applied / 已應用交易所確認成交"
        );
    }

    /// RRC-1-C2: Dispatch a close order via shadow/exchange channel.
    /// RRC-1-C2：通過影子/交易所通道派發平倉訂單。
    fn dispatch_close_order(
        &mut self,
        symbol: &str,
        is_long: bool,
        qty: f64,
        event: &PriceEvent,
        is_primary: bool,
    ) {
        if let Some(ref tx) = self.shadow_order_tx {
            self.exchange_seq = self.exchange_seq.wrapping_add(1);
            let prefix = if is_primary { "oc_risk" } else { "sh_risk" };
            let _ = tx.send(ShadowOrderRequest {
                symbol: symbol.to_string(),
                is_long: !is_long,
                qty,
                price: event.last_price,
                strategy: "risk_check".into(),
                paper_fill_ts: event.ts_ms,
                is_close: true,
                order_link_id: format!("{}_{}_{}", prefix, event.ts_ms, self.exchange_seq),
                is_primary,
                stop_loss: None,
                take_profit: None,
            });
            if is_primary {
                self.pending_close_symbols.insert(symbol.to_string());
            }
        }
    }

    /// IPC-triggered close-all: exchange mode (Demo/Live) dispatches reduce_only market orders
    /// via the shadow channel; paper mode clears paper_state directly.
    /// Returns the number of positions acted on.
    ///
    /// IPC 觸發全部平倉：交易所模式（Demo/Live）通過 shadow 通道發 reduce_only 市價單；
    /// 紙盤模式直接清除 paper_state。返回操作的倉位數量。
    pub(crate) fn ipc_close_all(&mut self) -> usize {
        let ts_ms = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis() as u64;
        let is_exchange = self.pipeline_kind.is_exchange();
        if is_exchange {
            // Collect position snapshot first to avoid borrow conflict on self.
            // 先快照倉位，避免 borrow 衝突。
            let positions: Vec<(String, bool, f64, f64)> = self
                .paper_state
                .positions()
                .into_iter()
                .filter(|p| p.qty > 0.0)
                .map(|p| {
                    let price = self
                        .paper_state
                        .latest_price(&p.symbol)
                        .unwrap_or(p.entry_price);
                    (p.symbol.clone(), p.is_long, p.qty, price)
                })
                .collect();
            let count = positions.len();
            for (symbol, is_long, qty, price) in positions {
                if let Some(ref tx) = self.shadow_order_tx {
                    self.exchange_seq = self.exchange_seq.wrapping_add(1);
                    let order_link_id =
                        format!("oc_ipc_close_{}_{}", ts_ms, self.exchange_seq);
                    let _ = tx.send(ShadowOrderRequest {
                        symbol: symbol.clone(),
                        is_long: !is_long, // opposite side to close / 相反方向平倉
                        qty,
                        price,
                        strategy: "ipc_close_all".into(),
                        paper_fill_ts: ts_ms,
                        is_close: true,
                        order_link_id,
                        is_primary: true, // exchange mode: primary order / 交易所模式主訂單
                        stop_loss: None,
                        take_profit: None,
                    });
                    self.pending_close_symbols.insert(symbol);
                }
            }
            count
        } else {
            // Paper mode: clear paper_state directly (no exchange orders).
            // 紙盤模式：直接清除 paper_state（無交易所訂單）。
            self.paper_state.close_all_positions()
        }
    }

    /// IPC-triggered close-symbol: exchange mode dispatches a single reduce_only market order;
    /// paper mode calls close_position_at_market directly.
    /// Returns true if a position was found and acted on.
    ///
    /// IPC 觸發單倉平倉：交易所模式發單一 reduce_only 市價單；
    /// 紙盤模式直接調用 close_position_at_market。找到倉位則返回 true。
    /// IPC-triggered single-symbol close.
    /// hint_is_long / hint_qty: caller-supplied exchange position info for orphan positions
    /// (positions that exist on the exchange but are not tracked in paper_state).
    /// When paper_state has no position but valid hints are provided, a shadow reduce_only
    /// market order is dispatched directly — Rust handles the Bybit API call.
    ///
    /// IPC 觸發單倉平倉。
    /// hint_is_long / hint_qty：呼叫方提供的交易所側倉位資訊（孤兒倉位用）。
    /// paper_state 無倉但有有效 hints 時，直接發 shadow reduce_only 市價單，
    /// 由 Rust 引擎完成 Bybit API 調用，Python 層不介入交易執行。
    pub(crate) fn ipc_close_symbol(
        &mut self,
        symbol: &str,
        hint_is_long: Option<bool>,
        hint_qty: Option<f64>,
    ) -> bool {
        let ts_ms = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis() as u64;
        // Use exchange path when:
        //   (a) pipeline_kind is Demo or Live, OR
        //   (b) system_mode is DemoReserved AND shadow channel is active
        //       (paper_only + demo_reserved is the current shadow-dispatch setup).
        // 交易所路徑條件：
        //   (a) pipeline_kind 為 Demo 或 Live，或
        //   (b) system_mode 為 DemoReserved 且 shadow channel 可用。
        let is_exchange = self.pipeline_kind.is_exchange()
            || (self.shadow_order_tx.is_some()
                && matches!(self.system_mode, SystemMode::DemoReserved));
        if is_exchange {
            // Read position data before mutating self.exchange_seq.
            // 先讀倉位數據，再修改 self.exchange_seq。
            let pos_info = self.paper_state.get_position(symbol).and_then(|p| {
                if p.qty > 0.0 {
                    let price = self
                        .paper_state
                        .latest_price(symbol)
                        .unwrap_or(p.entry_price);
                    Some((p.is_long, p.qty, price))
                } else {
                    None
                }
            });
            // Fallback: use caller hints for orphan exchange positions not in paper_state.
            // paper_state 無倉時，使用呼叫方提供的 hints 平掉交易所側的孤兒倉位。
            let (is_long, qty, price) = match pos_info {
                Some(v) => v,
                None => match (hint_is_long, hint_qty) {
                    (Some(il), Some(q)) if q > 0.0 => {
                        let price = self.paper_state.latest_price(symbol).unwrap_or(0.0);
                        info!(
                            symbol,
                            is_long = il,
                            qty = q,
                            "ipc_close_symbol: orphan hint close — no paper pos, using caller hint / 孤兒倉位 hint 平倉"
                        );
                        (il, q, price)
                    }
                    _ => return false,
                },
            };
            if let Some(ref tx) = self.shadow_order_tx {
                self.exchange_seq = self.exchange_seq.wrapping_add(1);
                let order_link_id = format!("oc_ipc_close_{}_{}", ts_ms, self.exchange_seq);
                let _ = tx.send(ShadowOrderRequest {
                    symbol: symbol.to_string(),
                    is_long: !is_long, // opposite side to close / 相反方向平倉
                    qty,
                    price,
                    strategy: "ipc_close_symbol".into(),
                    paper_fill_ts: ts_ms,
                    is_close: true,
                    order_link_id,
                    is_primary: true,
                    stop_loss: None,
                    take_profit: None,
                });
                self.pending_close_symbols.insert(symbol.to_string());
                true
            } else {
                false
            }
        } else {
            // Paper mode: immediate close via paper_state.
            // 紙盤模式：通過 paper_state 立即平倉。
            self.paper_state.close_position_at_market(symbol).is_some()
        }
    }

    /// Build a canary record if canary_mode is enabled (R07-2).
    /// 灰度模式啟用時構建灰度記錄。
    fn maybe_canary_record(
        &self,
        event: &PriceEvent,
        indicators: Option<IndicatorSnapshot>,
        signals: Vec<Signal>,
        intents: Vec<crate::intent_processor::OrderIntent>,
        tick_duration_us: u64,
    ) -> Option<CanaryRecord> {
        if !self.canary_mode {
            return None;
        }
        Some(CanaryRecord {
            schema_version: "1.0.0".into(),
            source: "rust_engine".into(),
            tick_number: self.stats.total_ticks,
            timestamp_ms: event.ts_ms,
            symbol: event.symbol.clone(),
            price: event.last_price,
            indicators,
            signals,
            order_intents: intents,
            paper_state: self.paper_state.export_state(),
            stats: self.stats.clone(),
            tick_duration_us,
        })
    }

    fn compute_indicators(&self, symbol: &str) -> Option<IndicatorSnapshot> {
        let ohlcv = self.kline_manager.get_ohlcv(symbol, "1m", Some(100))?;
        if ohlcv.close.len() < 30 {
            return None;
        }
        Some(IndicatorEngine::compute_all(
            &ohlcv.high,
            &ohlcv.low,
            &ohlcv.close,
            &ohlcv.volume,
        ))
    }

    pub fn grant_paper_auth(&mut self) -> Result<(), String> {
        self.governance
            .grant_paper_authorization(None)
            .map(|_| ())
            .map_err(|e| e.to_string())
    }

    pub fn status(&self) -> PipelineStatus {
        PipelineStatus {
            stats: self.stats.clone(),
            governance: self.governance.status(),
            positions: self.paper_state.position_count(),
            balance: self.paper_state.balance(),
            symbols_tracked: self.latest_prices.len(),
        }
    }

    /// Create full IPC snapshot / 創建完整 IPC 快照（R06-A）
    pub fn snapshot(&self) -> PipelineSnapshot {
        let strategies: Vec<StrategyInfo> = self.orchestrator.strategy_infos();
        let mut klines: HashMap<String, Vec<openclaw_core::klines::KlineBar>> = HashMap::new();
        for sym in self.kline_manager.symbols() {
            if let Some(buf) = self.kline_manager.get_buffer(sym, "1m") {
                let bars = buf.latest_cloned(100);
                if !bars.is_empty() {
                    klines.insert(sym.clone(), bars);
                }
            }
        }

        PipelineSnapshot {
            schema_version: "2.0.0".into(),
            written_at_ms: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_millis() as u64)
                .unwrap_or(0),
            paper_state: self.paper_state.export_state(),
            latest_prices: self.latest_prices.clone(),
            stats: self.stats.clone(),
            source: "rust_engine".into(),
            paper_paused: self.paper_paused,
            pipeline_kind: self.pipeline_kind,
            system_mode: self.system_mode.to_string(),
            indicators: self.latest_indicators.clone(),
            signals: self.recent_signals.iter().cloned().collect(),
            strategies,
            recent_intents: self.recent_intents.iter().cloned().collect(),
            recent_fills: self.recent_fills.iter().cloned().collect(),
            klines,
            h0_gate_stats: Some(self.h0_gate.get_stats().clone()),
            stop_config: Some(self.paper_state.stop_config().clone()),
            guardian_config: Some(self.intent_processor.guardian_config().clone()),
            risk_manager_config: Some(self.intent_processor.risk_config().clone()),
            consecutive_losses: self.consecutive_losses.clone(),
            session_halted: self.session_halted,
            daily_loss_pct: self
                .intent_processor
                .daily_loss_pct_pub(self.paper_state.balance()),
            session_drawdown_pct: self.paper_state.drawdown_pct(),
            mode_snapshots: {
                // 3E-4: Each pipeline emits its own snapshot. Multi-mode iteration removed.
                // 3E-4：每管線發出自己的快照。多模式迭代已移除。
                let mut ms = HashMap::new();
                ms.insert(
                    self.pipeline_kind.db_mode().to_string(),
                    crate::mode_state::ModeStateSnapshot {
                        paper_state: self.paper_state.export_state(),
                        recent_intents: self.recent_intents.iter().cloned().collect(),
                        recent_fills: self.recent_fills.iter().cloned().collect(),
                        consecutive_losses: self.consecutive_losses.clone(),
                        session_halted: self.session_halted,
                        paper_paused: self.paper_paused,
                    },
                );
                ms
            },
        }
    }

    /// Set global system mode, syncing from Python GUI.
    /// Automatically closes exchange positions when entering ShadowOnly/ObserveOnly/DesignOnly.
    /// Pauses paper simulation when entering ObserveOnly/DesignOnly.
    /// 設置全局系統模式，從 Python GUI 同步。
    /// 進入 ShadowOnly/ObserveOnly/DesignOnly 時自動平倉交易所持倉。
    /// 進入 ObserveOnly/DesignOnly 時暫停 paper 模擬。
    pub fn set_system_mode(&mut self, mode: &str) -> Result<String, String> {
        let new_mode = SystemMode::from_str(mode)?;
        let old_mode = self.system_mode;
        let is_exchange_mode = self.pipeline_kind.is_exchange();
        let was_exchange_allowed = !matches!(
            old_mode,
            SystemMode::ShadowOnly | SystemMode::ObserveOnly | SystemMode::DesignOnly
        );
        let exchange_now_blocked = matches!(
            new_mode,
            SystemMode::ShadowOnly | SystemMode::ObserveOnly | SystemMode::DesignOnly
        );
        // Auto-close exchange positions when transitioning into a blocking mode
        // 過渡到封鎖模式時自動平倉交易所持倉
        if is_exchange_mode && was_exchange_allowed && exchange_now_blocked {
            let count = self.ipc_close_all();
            info!(
                old = %old_mode, new = %new_mode, closed = count,
                "system_mode gate: auto-closing exchange positions / 系統模式門控：自動平倉交易所持倉"
            );
        }
        // Pause/resume paper simulation based on new mode
        // 根據新模式暫停/恢復 paper 模擬
        match new_mode {
            SystemMode::ObserveOnly | SystemMode::DesignOnly => {
                self.paper_paused = true;
            }
            SystemMode::ShadowOnly => {
                self.paper_paused = false;
            }
            _ => {}
        }
        self.system_mode = new_mode;
        info!(old = %old_mode, new = %new_mode, "system_mode updated / 系統模式已更新");
        Ok(format!(
            "{{\"old\":\"{old_mode}\",\"new\":\"{new_mode}\"}}"
        ))
    }

    /// Read-only access to latest prices map (R06-A).
    /// 最新價格映射的唯讀訪問。
    pub fn latest_prices(&self) -> &HashMap<String, f64> {
        &self.latest_prices
    }

    /// Feed a single replay tick through the full pipeline (R07-replay).
    /// Delegates to on_tick() with canary_mode forced on to guarantee a
    /// CanaryRecord is returned for every tick.
    /// 將單個回放 tick 送入完整管線（R07-replay）。
    /// 強制啟用 canary_mode 以確保每個 tick 都返回 CanaryRecord。
    pub fn feed_replay_tick(&mut self, event: &PriceEvent) -> Option<CanaryRecord> {
        // Ensure canary_mode is on so on_tick() produces a record.
        // 確保 canary_mode 開啟，使 on_tick() 產生記錄。
        let was_canary = self.canary_mode;
        self.canary_mode = true;
        let record = self.on_tick(event);
        self.canary_mode = was_canary;
        record
    }
}

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

#[cfg(test)]
mod tests {
    use super::*;

    fn make_event(symbol: &str, price: f64, ts: u64) -> PriceEvent {
        PriceEvent::new(symbol.to_string(), price, ts)
    }

    // ── 3E-1: PipelineKind + GovernanceProfile tests ──

    #[test]
    fn test_pipeline_kind_db_mode() {
        assert_eq!(PipelineKind::Paper.db_mode(), "paper");
        assert_eq!(PipelineKind::Demo.db_mode(), "demo");
        assert_eq!(PipelineKind::Live.db_mode(), "live");
    }

    #[test]
    fn test_pipeline_kind_is_exchange() {
        assert!(!PipelineKind::Paper.is_exchange());
        assert!(PipelineKind::Demo.is_exchange());
        assert!(PipelineKind::Live.is_exchange());
    }

    #[test]
    fn test_pipeline_kind_governance_profile() {
        assert_eq!(PipelineKind::Paper.governance_profile(), GovernanceProfile::Exploration);
        assert_eq!(PipelineKind::Demo.governance_profile(), GovernanceProfile::Validation);
        assert_eq!(PipelineKind::Live.governance_profile(), GovernanceProfile::Production);
    }

    #[test]
    fn test_governance_profile_authorization_requirements() {
        assert!(!GovernanceProfile::Exploration.requires_authorization());
        assert!(!GovernanceProfile::Validation.requires_authorization());
        assert!(GovernanceProfile::Production.requires_authorization());
    }

    #[test]
    fn test_governance_profile_lease_requirements() {
        assert!(!GovernanceProfile::Exploration.requires_lease());
        assert!(!GovernanceProfile::Validation.requires_lease());
        assert!(GovernanceProfile::Production.requires_lease());
    }

    #[test]
    fn test_pipeline_kind_serde_roundtrip() {
        for kind in [PipelineKind::Paper, PipelineKind::Demo, PipelineKind::Live] {
            let json = serde_json::to_string(&kind).expect("serialize");
            let back: PipelineKind = serde_json::from_str(&json).expect("deserialize");
            assert_eq!(kind, back);
        }
    }

    #[test]
    fn test_pipeline_kind_display() {
        assert_eq!(format!("{}", PipelineKind::Paper), "paper");
        assert_eq!(format!("{}", PipelineKind::Demo), "demo");
        assert_eq!(format!("{}", PipelineKind::Live), "live");
    }

    /// 3E D10/D20: Verify Arc<PriceEvent> fan-out delivers to multiple receivers.
    /// 3E D10/D20：驗證 Arc<PriceEvent> 扇出可向多個接收端投遞。
    #[tokio::test]
    async fn test_fanout_arc_price_event() {
        use std::sync::Arc;
        use tokio::sync::mpsc;
        let (tx1, mut rx1) = mpsc::channel::<Arc<openclaw_types::PriceEvent>>(16);
        let (tx2, mut rx2) = mpsc::channel::<Arc<openclaw_types::PriceEvent>>(16);
        let event = openclaw_types::PriceEvent::new("BTCUSDT".into(), 50000.0, 1000);
        let arc_event = Arc::new(event);
        tx1.try_send(Arc::clone(&arc_event)).unwrap();
        tx2.try_send(arc_event).unwrap();
        let e1 = rx1.recv().await.unwrap();
        let e2 = rx2.recv().await.unwrap();
        assert_eq!(e1.symbol, "BTCUSDT");
        assert_eq!(e2.symbol, "BTCUSDT");
        assert_eq!(e1.last_price, e2.last_price);
    }

    /// 3E D10: Verify try_send returns Err when channel is full (lag detection).
    /// 3E D10：驗證通道滿時 try_send 返回 Err（延遲檢測）。
    #[tokio::test]
    async fn test_fanout_lag_detection() {
        use std::sync::Arc;
        use tokio::sync::mpsc;
        // Buffer size 1 — second send should fail
        let (tx, _rx) = mpsc::channel::<Arc<openclaw_types::PriceEvent>>(1);
        let e1 = Arc::new(openclaw_types::PriceEvent::new("A".into(), 1.0, 1));
        let e2 = Arc::new(openclaw_types::PriceEvent::new("B".into(), 2.0, 2));
        assert!(tx.try_send(e1).is_ok());
        assert!(tx.try_send(e2).is_err()); // channel full → lag detected
    }

    #[test]
    fn test_pipeline_creation() {
        let pipeline = TickPipeline::new(&["BTCUSDT"]);
        assert_eq!(pipeline.stats.total_ticks, 0);
    }

    #[test]
    fn test_pipeline_on_tick() {
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.on_tick(&make_event("BTCUSDT", 50000.0, 1000));
        assert_eq!(pipeline.stats.total_ticks, 1);
    }

    #[test]
    fn test_pipeline_multiple_ticks() {
        let mut pipeline = TickPipeline::new(&["BTCUSDT", "ETHUSDT"]);
        for i in 0..50 {
            pipeline.on_tick(&make_event("BTCUSDT", 50000.0 + i as f64, i * 60_000));
        }
        assert_eq!(pipeline.stats.total_ticks, 50);
    }

    #[test]
    fn test_position_snapshot_emitted_every_1000_ticks() {
        // GAP-7 regression: PositionSnapshot must be emitted every 1000 ticks
        // for every open paper position when trading_tx is wired.
        // GAP-7 回歸：掛接 trading_tx 時每 1000 ticks 為每個持倉發射快照。
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::TradingMsg>(8192);
        pipeline.set_trading_channel(tx);
        // Open a paper long position directly.
        // 直接建立紙盤多單持倉。
        pipeline
            .paper_state
            .apply_fill("BTCUSDT", true, 0.1, 50_000.0, 0.0, 0);
        // Pump exactly 1000 ticks. total_ticks becomes 1000 -> snapshot.
        // 打 1000 tick，total_ticks 達到 1000 觸發快照。
        for i in 0..1000 {
            pipeline.on_tick(&make_event("BTCUSDT", 50_000.0, (i + 1) * 60_000));
        }
        // Drain channel; expect at least one PositionSnapshot for BTCUSDT.
        // 抽取通道；至少應有一條 BTCUSDT 的 PositionSnapshot。
        let mut found = false;
        while let Ok(msg) = rx.try_recv() {
            if let crate::database::TradingMsg::PositionSnapshot {
                symbol,
                side,
                qty,
                mark_price,
                unrealized_pnl,
                ..
            } = msg
            {
                if symbol == "BTCUSDT" {
                    assert_eq!(side, "long");
                    assert!((qty - 0.1).abs() < 1e-9);
                    assert!((mark_price - 50_000.0).abs() < 1e-9);
                    assert!(unrealized_pnl.abs() < 1e-6);
                    found = true;
                    break;
                }
            }
        }
        assert!(
            found,
            "expected a PositionSnapshot for BTCUSDT; positions={}",
            pipeline.paper_state.position_count()
        );
    }

    #[test]
    fn test_position_snapshot_noop_without_channel() {
        // Without trading_tx wired, snapshot loop must be a no-op and never panic.
        // 未掛接 trading_tx 時快照循環必須無動作且不 panic。
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline
            .paper_state
            .apply_fill("BTCUSDT", false, 0.2, 50_000.0, 0.0, 0);
        for i in 0..1000 {
            pipeline.on_tick(&make_event("BTCUSDT", 49_000.0, (i + 1) * 60_000));
        }
        assert_eq!(pipeline.stats.total_ticks, 1000);
    }

    #[test]
    fn test_pipeline_with_auth() {
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.grant_paper_auth().unwrap();
        assert!(pipeline.governance.is_authorized());
    }

    #[test]
    fn test_canary_mode_off_returns_none() {
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        assert!(!pipeline.canary_mode);
        let record = pipeline.on_tick(&make_event("BTCUSDT", 50000.0, 1000));
        assert!(record.is_none());
    }

    #[test]
    fn test_canary_mode_on_returns_record() {
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.canary_mode = true;
        let record = pipeline.on_tick(&make_event("BTCUSDT", 50000.0, 1000));
        assert!(record.is_some());
        let r = record.unwrap();
        assert_eq!(r.schema_version, "1.0.0");
        assert_eq!(r.source, "rust_engine");
        assert_eq!(r.tick_number, 1);
        assert_eq!(r.symbol, "BTCUSDT");
        assert_eq!(r.price, 50000.0);
        assert_eq!(r.timestamp_ms, 1000);
    }

    #[test]
    fn test_canary_record_serializable() {
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.canary_mode = true;
        let record = pipeline
            .on_tick(&make_event("BTCUSDT", 50000.0, 1000))
            .unwrap();
        let json = serde_json::to_string(&record).unwrap();
        assert!(json.contains("\"schema_version\":\"1.0.0\""));
        assert!(json.contains("\"source\":\"rust_engine\""));
        // Deserialize back / 反序列化
        let r2: CanaryRecord = serde_json::from_str(&json).unwrap();
        assert_eq!(r2.tick_number, record.tick_number);
    }

    #[test]
    fn test_snapshot_to_input() {
        let snap = IndicatorSnapshot {
            sma_20: Some(50000.0),
            sma_50: None,
            ema_12: Some(50100.0),
            ema_26: None,
            rsi_14: Some(55.0),
            macd: None,
            bollinger: None,
            atr_14: None,
            atr_5: None,
            stochastic: None,
            kama: None,
            adx: None,
            hurst: None,
            ewma_vol: None,
            volume_ratio: Some(1.2),
            donchian: None,
        };
        let input = snapshot_to_input(&snap);
        assert_eq!(input.sma, Some(50000.0));
        assert_eq!(input.rsi, Some(55.0));
        assert_eq!(input.volume_ratio, Some(1.2));
    }

    // ─── I-08 Dual-Rail Stop tests (Principle #9) ───
    // 雙軌止損測試：驗證 broker-side SL 只在 primary exchange mode 開倉時啟用

    #[test]
    fn test_dual_rail_shadow_order_has_sl_fields() {
        // Struct must expose stop_loss / take_profit for broker rail wiring
        let req = ShadowOrderRequest {
            symbol: "BTCUSDT".into(),
            is_long: true,
            qty: 0.01,
            price: 50000.0,
            strategy: "test".into(),
            paper_fill_ts: 0,
            is_close: false,
            order_link_id: "oc_test".into(),
            is_primary: true,
            stop_loss: Some(49000.0),
            take_profit: Some(52000.0),
        };
        assert_eq!(req.stop_loss, Some(49000.0));
        assert_eq!(req.take_profit, Some(52000.0));
    }

    #[test]
    fn test_dual_rail_broker_sl_long_below_entry() {
        // Long SL must sit below entry price
        let entry: f64 = 50000.0;
        let sl_pct: f64 = 2.0;
        let sl = entry * (1.0 - sl_pct / 100.0);
        assert!(sl < entry);
        assert!((sl - 49000.0f64).abs() < 0.01);
    }

    #[test]
    fn test_dual_rail_broker_sl_short_above_entry() {
        // Short SL must sit above entry price
        let entry: f64 = 50000.0;
        let sl_pct: f64 = 2.0;
        let sl = entry * (1.0 + sl_pct / 100.0);
        assert!(sl > entry);
        assert!((sl - 51000.0f64).abs() < 0.01);
    }

    #[test]
    fn test_dual_rail_close_orders_no_broker_sl() {
        // Close orders never attach broker SL (Bybit auto-cancels on reduce-only fill)
        let req = ShadowOrderRequest {
            symbol: "BTCUSDT".into(),
            is_long: false,
            qty: 0.01,
            price: 50000.0,
            strategy: "risk_check".into(),
            paper_fill_ts: 0,
            is_close: true,
            order_link_id: "oc_risk".into(),
            is_primary: true,
            stop_loss: None,
            take_profit: None,
        };
        assert!(req.stop_loss.is_none());
        assert!(req.is_close);
    }

    #[test]
    fn test_dual_rail_paper_shadow_skips_broker_sl() {
        // Paper/shadow orders keep broker SL None (engine rail handles stops locally)
        let req = ShadowOrderRequest {
            symbol: "ETHUSDT".into(),
            is_long: true,
            qty: 0.1,
            price: 3000.0,
            strategy: "ma".into(),
            paper_fill_ts: 0,
            is_close: false,
            order_link_id: "sh_test".into(),
            is_primary: false,
            stop_loss: None,
            take_profit: None,
        };
        assert!(!req.is_primary);
        assert!(req.stop_loss.is_none());
    }

    fn make_signal(symbol: &str, dir: openclaw_core::signals::SignalDirection, ts_ms: u64) -> openclaw_core::signals::Signal {
        openclaw_core::signals::Signal {
            symbol: symbol.into(),
            direction: dir,
            confidence: 0.5,
            edge_bps: 10.0,
            source: "ma_crossover".into(),
            timeframe: "1m".into(),
            reasoning: "test".into(),
            ts_ms,
        }
    }

    #[test]
    fn test_dbrun1_first_signal_persisted() {
        use openclaw_core::signals::SignalDirection;
        let mut p = TickPipeline::new(&["BTCUSDT"]);
        assert!(p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Long, 1_000)));
        assert_eq!(p.signals_throttled(), 0);
    }

    #[test]
    fn test_dbrun1_unchanged_signal_throttled_within_heartbeat() {
        use openclaw_core::signals::SignalDirection;
        let mut p = TickPipeline::new(&["BTCUSDT"]);
        p.set_signals_heartbeat_ms(60_000);
        assert!(p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Long, 1_000)));
        // Same direction, +30s → throttled
        assert!(!p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Long, 31_000)));
        assert_eq!(p.signals_throttled(), 1);
    }

    #[test]
    fn test_dbrun1_direction_change_breaks_throttle() {
        use openclaw_core::signals::SignalDirection;
        let mut p = TickPipeline::new(&["BTCUSDT"]);
        p.set_signals_heartbeat_ms(60_000);
        assert!(p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Long, 1_000)));
        // Direction flips → persist immediately even within heartbeat
        assert!(p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Short, 5_000)));
        assert_eq!(p.signals_throttled(), 0);
    }

    #[test]
    fn test_dbrun1_heartbeat_elapsed_persists() {
        use openclaw_core::signals::SignalDirection;
        let mut p = TickPipeline::new(&["BTCUSDT"]);
        p.set_signals_heartbeat_ms(60_000);
        assert!(p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Long, 1_000)));
        // Same direction, 60s later → heartbeat fires
        assert!(p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Long, 61_000)));
        assert_eq!(p.signals_throttled(), 0);
    }

    #[test]
    fn test_dbrun1_disable_throttle() {
        use openclaw_core::signals::SignalDirection;
        let mut p = TickPipeline::new(&["BTCUSDT"]);
        p.set_signals_heartbeat_ms(0);
        // Every call persists, no dedupe state consulted
        for ts in [1, 2, 3, 4, 5] {
            assert!(p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Long, ts)));
        }
        assert_eq!(p.signals_throttled(), 0);
    }

    #[test]
    fn test_dbrun3_close_position_returns_pnl() {
        let mut p = TickPipeline::new(&["BTCUSDT"]);
        // Open long at 50k, close at 51k → +0.1 * 1000 = +$100 realized
        p.paper_state.apply_fill("BTCUSDT", true, 0.1, 50_000.0, 0.0, 0);
        let pnl = p.paper_state.close_position("BTCUSDT", 51_000.0, 1_000);
        assert_eq!(pnl, Some(100.0));
        // Subsequent close on same symbol → None
        let none = p.paper_state.close_position("BTCUSDT", 52_000.0, 2_000);
        assert!(none.is_none());
    }

    #[test]
    fn test_dbrun3_emit_close_fill_increments_stats() {
        let mut p = TickPipeline::new(&["BTCUSDT"]);
        let before = p.stats.total_fills;
        p.emit_close_fill("BTCUSDT", true, 0.1, 51_000.0, 1_000, 100.0, "test");
        assert_eq!(p.stats.total_fills, before + 1);
    }

    #[test]
    fn test_dbrun2_context_counter_starts_zero() {
        let p = TickPipeline::new(&["BTCUSDT"]);
        assert_eq!(p.context_throttled(), 0);
        assert_eq!(p.signals_throttled(), 0);
    }

    #[test]
    fn test_dbrun1_per_symbol_strategy_isolation() {
        use openclaw_core::signals::SignalDirection;
        let mut p = TickPipeline::new(&["BTCUSDT", "ETHUSDT"]);
        p.set_signals_heartbeat_ms(60_000);
        assert!(p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Long, 1_000)));
        // Different symbol, same strategy → independent key, persists
        assert!(p.should_persist_signal(&make_signal("ETHUSDT", SignalDirection::Long, 1_000)));
        assert_eq!(p.signals_throttled(), 0);
    }

    #[test]
    fn test_pnl3_boot_cooldown_stamps_first_tick() {
        // PNL-3: First tick stamps boot_ts_ms; subsequent ticks reuse it.
        // PNL-3：首個 tick 記錄 boot_ts_ms；後續 tick 沿用。
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        assert!(pipeline.boot_ts_ms.is_none());
        pipeline.on_tick(&make_event("BTCUSDT", 50_000.0, 1_000_000));
        assert_eq!(pipeline.boot_ts_ms, Some(1_000_000));
        pipeline.on_tick(&make_event("BTCUSDT", 50_001.0, 1_010_000));
        assert_eq!(pipeline.boot_ts_ms, Some(1_000_000));
    }

    #[test]
    fn test_pnl4_derive_regime_hurst_priority() {
        use openclaw_core::indicators::{HurstResult, IndicatorSnapshot};
        let pipeline = TickPipeline::new(&["BTCUSDT"]);
        let mut ind = IndicatorSnapshot::default();
        ind.hurst = Some(HurstResult { hurst: 0.7, regime: "trending".into() });
        assert_eq!(pipeline.derive_regime(Some(&ind)), "trending");
        ind.hurst = Some(HurstResult { hurst: 0.3, regime: "mean_reverting".into() });
        assert_eq!(pipeline.derive_regime(Some(&ind)), "ranging");
    }

    #[test]
    fn test_pnl4_derive_regime_adx_fallback() {
        use openclaw_core::indicators::{AdxResult, HurstResult, IndicatorSnapshot};
        let pipeline = TickPipeline::new(&["BTCUSDT"]);
        let mut ind = IndicatorSnapshot::default();
        ind.hurst = Some(HurstResult { hurst: 0.5, regime: "random_walk".into() });
        ind.adx = Some(AdxResult { adx: 30.0, plus_di: 25.0, minus_di: 10.0 });
        assert_eq!(pipeline.derive_regime(Some(&ind)), "trending");
        ind.adx = Some(AdxResult { adx: 15.0, plus_di: 10.0, minus_di: 12.0 });
        assert_eq!(pipeline.derive_regime(Some(&ind)), "ranging");
    }

    #[test]
    fn test_pnl4_derive_regime_none_default() {
        let pipeline = TickPipeline::new(&["BTCUSDT"]);
        assert_eq!(pipeline.derive_regime(None), "ranging");
    }

    #[test]
    fn test_rc1_risk_runtime_status_no_boot_ts() {
        // 1C-3-B: before first tick, boot_ts_ms is None → remaining = 0
        // 1C-3-B：第一個 tick 之前 boot_ts_ms 為 None → 剩餘 0
        let pipeline = TickPipeline::new(&["BTCUSDT"]);
        let snap = pipeline.risk_runtime_status_json(1_000_000);
        assert_eq!(snap["boot_cooldown_remaining_ms"], 0);
        assert_eq!(snap["paper_paused"], false);
        assert_eq!(snap["session_halted"], false);
        assert!(snap["governor_tier"].is_string());
        assert!(snap["consecutive_losses_by_symbol"].is_object());
    }

    #[test]
    fn test_rc1_risk_runtime_status_boot_cooldown_math() {
        // 1C-3-B: boot at t=1000, cooldown=60s, now=t=11000 → remaining 50s
        // 1C-3-B：boot 時間 1000、冷卻 60s、現在 11000 → 剩 50s
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.boot_ts_ms = Some(1_000);
        pipeline.boot_cooldown_ms = 60_000;
        let snap = pipeline.risk_runtime_status_json(11_000);
        assert_eq!(snap["boot_cooldown_remaining_ms"], 50_000);
        assert_eq!(snap["boot_cooldown_total_ms"], 60_000);
        // Past expiry → saturating to 0
        // 過期 → 飽和到 0
        let snap2 = pipeline.risk_runtime_status_json(999_999_999);
        assert_eq!(snap2["boot_cooldown_remaining_ms"], 0);
    }

    #[test]
    fn test_rc1b2_parse_risk_level_aliases() {
        use openclaw_core::sm::risk_gov::RiskLevel;
        assert_eq!(TickPipeline::parse_risk_level("normal").unwrap(), RiskLevel::Normal);
        assert_eq!(TickPipeline::parse_risk_level("CAUTIOUS").unwrap(), RiskLevel::Cautious);
        assert_eq!(TickPipeline::parse_risk_level("circuit_breaker").unwrap(), RiskLevel::CircuitBreaker);
        assert_eq!(TickPipeline::parse_risk_level("CircuitBreaker").unwrap(), RiskLevel::CircuitBreaker);
        assert_eq!(TickPipeline::parse_risk_level("manual_review").unwrap(), RiskLevel::ManualReview);
        assert!(TickPipeline::parse_risk_level("foo").is_err());
    }

    #[test]
    fn test_rc1b2_governor_cooldown_const_24h() {
        // 1C-3-B-2: 24h = 86_400_000 ms
        // 1C-3-B-2：24h = 86_400_000 ms
        assert_eq!(TickPipeline::GOVERNOR_DE_ESCALATION_COOLDOWN_MS, 86_400_000);
    }

    #[test]
    fn test_rc1b2_de_escalation_reason_whitelist() {
        let valid = TickPipeline::VALID_DE_ESCALATION_REASONS;
        assert!(valid.contains(&"false_positive"));
        assert!(valid.contains(&"root_cause_fixed"));
        assert!(valid.contains(&"accept_risk"));
        assert!(!valid.contains(&"because_i_said_so"));
        assert_eq!(valid.len(), 3);
    }

    #[test]
    fn test_rc1b2_cooldown_state_setter_and_getter() {
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        assert_eq!(pipeline.last_governor_de_escalation_ms(), None);
        pipeline.set_last_governor_de_escalation_ms(Some(12345));
        assert_eq!(pipeline.last_governor_de_escalation_ms(), Some(12345));
        pipeline.set_last_governor_de_escalation_ms(None);
        assert_eq!(pipeline.last_governor_de_escalation_ms(), None);
    }

    #[test]
    fn test_rc1b2_sm_escalate_then_de_escalate_round_trip() {
        // End-to-end through pipeline.governance.risk: simulate operator
        // first making things tighter then relaxing them. Bypass min_hold_time
        // to keep the test fast.
        // 模擬 operator 先收緊再放鬆。繞過 min_hold_time 加速測試。
        use openclaw_core::sm::risk_gov::{RiskEvent, RiskLevel};
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.governance.risk.thresholds.min_hold_time_ms = 0;
        // Tighter: Normal → Cautious
        pipeline
            .governance
            .risk
            .escalate_to(RiskLevel::Cautious, "operator_ipc: testing", RiskEvent::OperatorEscalation)
            .unwrap();
        assert_eq!(pipeline.governance.risk.snapshot_level(), RiskLevel::Cautious);
        // Looser: Cautious → Normal
        pipeline
            .governance
            .risk
            .de_escalate_to(RiskLevel::Normal, "operator_ipc", "operator_ipc:false_positive")
            .unwrap();
        assert_eq!(pipeline.governance.risk.snapshot_level(), RiskLevel::Normal);
    }

    #[test]
    fn test_rc1_risk_runtime_status_consecutive_losses_map() {
        // 1C-3-B: per-symbol map round-trips into JSON object
        // 1C-3-B：per-symbol map 序列化為 JSON object
        let mut pipeline = TickPipeline::new(&["BTCUSDT", "ETHUSDT"]);
        pipeline.consecutive_losses.insert("BTCUSDT".into(), 3);
        pipeline.consecutive_losses.insert("ETHUSDT".into(), 1);
        let snap = pipeline.risk_runtime_status_json(0);
        assert_eq!(snap["consecutive_losses_by_symbol"]["BTCUSDT"], 3);
        assert_eq!(snap["consecutive_losses_by_symbol"]["ETHUSDT"], 1);
    }

    #[test]
    fn test_pnl3_boot_cooldown_default_60s() {
        // PNL-3: default cooldown is 60_000ms when env var not set.
        // PNL-3：未設環境變量時冷卻期默認 60_000ms。
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        // Force-set boot_ts_ms then check elapsed math via direct field.
        pipeline.boot_ts_ms = Some(0);
        assert_eq!(pipeline.boot_cooldown_ms, 60_000);
        // Tick at t=30s → still in cooldown
        let in_cd_30s: bool = (30_000u64).saturating_sub(0) < pipeline.boot_cooldown_ms;
        assert!(in_cd_30s);
        // Tick at t=61s → out of cooldown
        let in_cd_61s: bool = (61_000u64).saturating_sub(0) < pipeline.boot_cooldown_ms;
        assert!(!in_cd_61s);
    }

    // ─── ARCH-RC1 1C-4 hot-reload e2e ───────────────────────────────────
    // 驗證 IPC patch_risk_config 後的下一個 tick：5 個下游消費者全部
    // 同步看到新值（intent_processor / guardian / paper_state / h0_gate /
    // governance.risk.thresholds）。這份硬證據是 1C-4 wrap 的關鍵。
    // E2E proof: after a ConfigStore.replace() that simulates an IPC
    // patch_risk_config, driving a single on_tick must propagate the new
    // RiskConfig snapshot into ALL 5 owned-copy consumers via
    // sync_risk_config_if_changed → apply_risk_snapshot.
    #[test]
    fn test_arch_rc1_hot_reload_e2e_propagates_to_all_5_consumers() {
        use crate::config::{ConfigStore, PatchSource, RiskConfig};
        use std::sync::Arc;

        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);

        // Build a baseline RiskConfig (defaults) and wire it as the live store.
        // 建立預設 RiskConfig 並以 live store 接線。
        let initial = RiskConfig::default();
        let store = Arc::new(ConfigStore::new(initial.clone()));
        pipeline.set_risk_store(Arc::clone(&store));

        // Sanity: initial seed must already be visible across all 5 consumers.
        // 初始 seed 應已同步至 5 個下游。
        assert_eq!(
            pipeline.intent_processor.risk_config().limits.leverage_max,
            initial.limits.leverage_max
        );
        assert_eq!(
            pipeline.intent_processor.guardian_config().max_leverage,
            initial.limits.leverage_max
        );
        assert_eq!(
            pipeline.h0_gate.config().max_open_positions,
            initial.limits.open_positions_max
        );
        assert_eq!(
            pipeline.paper_state.stop_config().hard_stop_pct,
            initial.limits.stop_loss_max_pct
        );
        assert_eq!(
            pipeline.governance.risk.thresholds.drawdown_cautious_pct,
            initial.cascade.drawdown_cautious_pct
        );
        let v0 = store.version();

        // Build a mutated config that differs in fields touched by all 5
        // downstream paths inside apply_risk_snapshot, then atomically
        // replace() — this is exactly what handle_patch_config does after
        // a successful patch_risk_config IPC call.
        // 修改一份新 config（覆蓋 5 條下游路徑各自讀的欄位），用 replace()
        // 原子寫入 — 這正是 IPC patch_risk_config 成功後的行為。
        let mut next = initial.clone();
        next.limits.leverage_max = initial.limits.leverage_max + 1.0;
        next.limits.open_positions_max = initial.limits.open_positions_max + 1;
        next.limits.stop_loss_max_pct = initial.limits.stop_loss_max_pct + 0.5;
        next.anti_cluster.max_same_direction =
            initial.anti_cluster.max_same_direction + 1;
        next.cascade.drawdown_cautious_pct =
            initial.cascade.drawdown_cautious_pct + 0.001;
        // Validate the mutated config to make sure we don't accidentally
        // craft an invalid one (defaults + tiny bumps should always pass).
        next.validate().expect("mutated test config must be valid");

        store
            .replace(next.clone(), PatchSource::Operator)
            .expect("replace must succeed");
        assert_eq!(store.version(), v0 + 1);

        // Drive a single tick — sync_risk_config_if_changed runs at the top
        // of on_tick and must apply_risk_snapshot to all 5 consumers.
        // 打一個 tick — sync_risk_config_if_changed 會在 on_tick 頂部執行
        // 並把新快照推到 5 個下游。
        pipeline.on_tick(&make_event("BTCUSDT", 50_000.0, 1_000));

        // 1) intent_processor's owned RiskConfig (Gate 0 / cost-edge / dynamic_stop)
        assert_eq!(
            pipeline.intent_processor.risk_config().limits.leverage_max,
            next.limits.leverage_max,
            "consumer #1: intent_processor.risk_config NOT hot-reloaded"
        );
        // 2) Guardian (P0 trade intent veto path)
        let g = pipeline.intent_processor.guardian_config();
        assert_eq!(
            g.max_leverage, next.limits.leverage_max,
            "consumer #2: guardian.max_leverage NOT hot-reloaded"
        );
        assert_eq!(
            g.max_same_direction_positions,
            next.anti_cluster.max_same_direction as usize,
            "consumer #2: guardian.max_same_direction_positions NOT hot-reloaded"
        );
        // 3) H0Gate (risk-level fields RMW)
        assert_eq!(
            pipeline.h0_gate.config().max_open_positions,
            next.limits.open_positions_max,
            "consumer #3: h0_gate.max_open_positions NOT hot-reloaded"
        );
        // 4) paper_state.stop_config (H0-blocked / paused fallback stops)
        assert!(
            (pipeline.paper_state.stop_config().hard_stop_pct
                - next.limits.stop_loss_max_pct)
                .abs()
                < 1e-9,
            "consumer #4: paper_state.stop_config.hard_stop_pct NOT hot-reloaded"
        );
        // 5) GovernanceCore.risk.thresholds (6-tier cascade SM)
        assert!(
            (pipeline.governance.risk.thresholds.drawdown_cautious_pct
                - next.cascade.drawdown_cautious_pct)
                .abs()
                < 1e-9,
            "consumer #5: governance.risk.thresholds NOT hot-reloaded"
        );

        // The pipeline must remember the new version so the NEXT tick is a
        // no-op (cheap atomic load + equality, no re-apply).
        // 紀錄版本號避免下個 tick 重複套用。
        assert_eq!(pipeline.risk_config_version_seen, store.version());
    }

    #[test]
    fn test_strategy_close_action_closes_position() {
        // Integration test: open a paper position, then simulate the strategy Close
        // deferred execution path, verify position is closed and fills/stats updated.
        // 集成測試：建立紙盤倉位，模擬策略 Close 延遲執行路徑，驗證倉位已平且成交/統計已更新。
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.grant_paper_auth().unwrap();

        // Open a long position directly via paper_state
        pipeline
            .paper_state
            .apply_fill("BTCUSDT", true, 0.1, 50_000.0, 5.5, 1000);
        assert_eq!(pipeline.paper_state.position_count(), 1);
        let balance_before = pipeline.paper_state.balance();

        // Simulate the deferred close: close_position + record_trade + recent_fills
        // (This is exactly what the deferred close loop does for paper mode.)
        let close_price = 51_000.0;
        let close_ts = 2000_u64;
        let pos = pipeline.paper_state.get_position("BTCUSDT").unwrap();
        let is_long = pos.is_long;
        let qty = pos.qty;
        assert!(is_long);
        assert!((qty - 0.1).abs() < 1e-9);

        let pnl = pipeline
            .paper_state
            .close_position("BTCUSDT", close_price, close_ts);
        assert!(pnl.is_some(), "close_position should return pnl");
        let pnl = pnl.unwrap();
        assert!(pnl > 0.0, "long closed at higher price should be profitable");

        // Kelly stats update
        pipeline.intent_processor.record_trade("BTCUSDT", pnl);

        // Position should be gone
        assert_eq!(pipeline.paper_state.position_count(), 0);
        assert!(pipeline.paper_state.get_position("BTCUSDT").is_none());

        // Balance should have increased (profit minus fees)
        assert!(pipeline.paper_state.balance() > balance_before);
    }

    #[test]
    fn test_strategy_close_no_position_is_noop() {
        // Close when no position exists must be a safe no-op.
        // 無倉位時 Close 必須安全無動作。
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let result = pipeline
            .paper_state
            .close_position("BTCUSDT", 50_000.0, 1000);
        assert!(result.is_none(), "close_position on empty should return None");
        assert_eq!(pipeline.paper_state.position_count(), 0);
    }

    // ═══════════════════════════════════════════════════════════════
    // Phase 3: set_trading_mode state swap tests / 模式切換狀態交換測試
    // ═══════════════════════════════════════════════════════════════

    // 3E-4: set_trading_mode / add_mode / mode_snapshot tests REMOVED.
    // Pipeline identity is now immutable (PipelineKind set at construction).
    // Mode state swap tests replaced by per-pipeline independence tests (3E e2e).
    // 3E-4：模式切換/添加/快照測試已移除。管線身份不可變。

    #[test]
    fn test_snapshot_contains_pipeline_kind_mode_snapshot() {
        let pipeline = TickPipeline::with_balance(&["BTCUSDT"], 8_000.0);
        let snap = pipeline.snapshot();
        // mode_snapshots should contain exactly the pipeline's own kind.
        // mode_snapshots 應包含管線自身 kind。
        assert!(snap.mode_snapshots.contains_key("paper"));
        assert_eq!(snap.mode_snapshots.len(), 1);
        assert_eq!(snap.mode_snapshots["paper"].paper_state.balance, 8_000.0);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // BLOCKER-10 / D6: EngineEvent + PipelineHealth tests
    // D6 跨引擎事件與管線健康狀態測試
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn test_d6_engine_event_crashed_clone() {
        // EngineEvent::Crashed must be Clone + Debug (required for broadcast).
        // Crashed 必須支持 Clone + Debug（broadcast 需要）。
        let evt = EngineEvent::Crashed(PipelineKind::Paper);
        let cloned = evt.clone();
        let dbg = format!("{:?}", cloned);
        assert!(dbg.contains("Crashed"));
        assert!(dbg.contains("Paper"));
    }

    #[test]
    fn test_d6_engine_event_cb_tripped_clone() {
        // EngineEvent::CircuitBreakerTripped must be Clone + Debug.
        // CircuitBreakerTripped 必須支持 Clone + Debug。
        let evt = EngineEvent::CircuitBreakerTripped(PipelineKind::Live);
        let cloned = evt.clone();
        let dbg = format!("{:?}", cloned);
        assert!(dbg.contains("CircuitBreakerTripped"));
        assert!(dbg.contains("Live"));
    }

    #[test]
    fn test_d6_pipeline_health_from_u8_roundtrip() {
        // PipelineHealth from_u8 covers all repr values + unknown default.
        // from_u8 覆蓋所有 repr 值 + 未知值默認 Down。
        assert_eq!(PipelineHealth::from_u8(0), PipelineHealth::Running);
        assert_eq!(PipelineHealth::from_u8(1), PipelineHealth::Paused);
        assert_eq!(PipelineHealth::from_u8(2), PipelineHealth::Down);
        assert_eq!(PipelineHealth::from_u8(255), PipelineHealth::Down); // unknown → Down
    }

    #[test]
    fn test_d6_pipeline_health_repr_values() {
        // Repr values must be stable (stored in AtomicU8 by other code).
        // repr 值必須穩定（其他代碼以 AtomicU8 存儲）。
        assert_eq!(PipelineHealth::Running as u8, 0);
        assert_eq!(PipelineHealth::Paused as u8, 1);
        assert_eq!(PipelineHealth::Down as u8, 2);
    }

    #[tokio::test]
    async fn test_d6_broadcast_delivers_to_multiple_receivers() {
        // broadcast::channel delivers same event to 2 receivers.
        // broadcast 通道將同一事件送達 2 個接收端。
        let (tx, mut rx1) = tokio::sync::broadcast::channel::<EngineEvent>(4);
        let mut rx2 = tx.subscribe();
        tx.send(EngineEvent::Crashed(PipelineKind::Demo)).unwrap();
        let e1 = rx1.recv().await.unwrap();
        let e2 = rx2.recv().await.unwrap();
        assert!(matches!(e1, EngineEvent::Crashed(PipelineKind::Demo)));
        assert!(matches!(e2, EngineEvent::Crashed(PipelineKind::Demo)));
    }

    #[tokio::test]
    async fn test_d6_broadcast_cb_event_delivery() {
        // CircuitBreakerTripped event delivered via broadcast.
        // 熔斷事件通過 broadcast 送達。
        let (tx, mut rx) = tokio::sync::broadcast::channel::<EngineEvent>(4);
        tx.send(EngineEvent::CircuitBreakerTripped(PipelineKind::Live)).unwrap();
        let evt = rx.recv().await.unwrap();
        assert!(matches!(evt, EngineEvent::CircuitBreakerTripped(PipelineKind::Live)));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // BLOCKER-10 / MAJOR-7 (D23): Snapshot versioning tests
    // 快照版本控制測試
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn test_d23_snapshot_schema_version_is_2_0_0() {
        // New snapshot must have schema_version "2.0.0".
        // 新快照的 schema_version 必須是 "2.0.0"。
        let pipeline = TickPipeline::with_balance(&["BTCUSDT"], 1_000.0);
        let snap = pipeline.snapshot();
        assert_eq!(snap.schema_version, "2.0.0");
    }

    #[test]
    fn test_d23_snapshot_written_at_ms_nonzero() {
        // written_at_ms must be set to a recent wall-clock timestamp.
        // written_at_ms 必須設為近期的 wall-clock 時間戳。
        let pipeline = TickPipeline::with_balance(&["BTCUSDT"], 1_000.0);
        let snap = pipeline.snapshot();
        assert!(snap.written_at_ms > 0, "written_at_ms should be nonzero");
        // Sanity: should be after 2026-01-01 (~1767225600000 ms)
        assert!(snap.written_at_ms > 1_700_000_000_000, "written_at_ms too old: {}", snap.written_at_ms);
    }

    #[test]
    fn test_d23_snapshot_deserialization_without_schema_version() {
        // Old snapshot JSON without schema_version should default to "2.0.0".
        // 舊快照 JSON 無 schema_version 時應默認為 "2.0.0"。
        let pipeline = TickPipeline::with_balance(&["BTCUSDT"], 1_000.0);
        let snap = pipeline.snapshot();
        let mut json: serde_json::Value = serde_json::to_value(&snap).unwrap();
        // Remove schema_version + written_at_ms to simulate old format
        json.as_object_mut().unwrap().remove("schema_version");
        json.as_object_mut().unwrap().remove("written_at_ms");
        let raw = serde_json::to_string(&json).unwrap();
        let restored: crate::pipeline_types::PipelineSnapshot = serde_json::from_str(&raw).unwrap();
        assert_eq!(restored.schema_version, "2.0.0"); // serde default
        assert_eq!(restored.written_at_ms, 0); // serde default
    }

    // ═══════════════════════════════════════════════════════════════════════
    // BLOCKER-10 / MAJOR-2 (D2): Startup barrier tests
    // 啟動屏障測試
    // ═══════════════════════════════════════════════════════════════════════

    #[tokio::test]
    async fn test_d2_startup_barrier_oneshot_fires() {
        // oneshot channel used for startup barrier works as expected.
        // 啟動屏障的 oneshot 通道正常運作。
        let (tx, rx) = tokio::sync::oneshot::channel::<()>();
        tx.send(()).unwrap();
        let result = tokio::time::timeout(
            std::time::Duration::from_millis(100),
            rx,
        ).await;
        assert!(result.is_ok(), "oneshot must resolve");
        assert!(result.unwrap().is_ok(), "oneshot must deliver ()");
    }

    #[tokio::test]
    async fn test_d2_startup_barrier_timeout_on_no_send() {
        // If pipeline never sends ready, fan-out timeout should fire.
        // 若管線永不發送 ready，扇出超時應觸發。
        let (_tx, rx) = tokio::sync::oneshot::channel::<()>();
        let result = tokio::time::timeout(
            std::time::Duration::from_millis(50),
            rx,
        ).await;
        assert!(result.is_err(), "should timeout when no ready signal sent");
    }
}
