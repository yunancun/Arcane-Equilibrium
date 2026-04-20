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

use crate::risk_checks::RiskAction;
use openclaw_core::{
    governance_core::{GovernanceCore, GovernanceProfile},
    h0_gate::H0Gate,
    indicators::{IndicatorEngine, IndicatorSnapshot},
    klines::KlineManager,
    risk::PriceHistoryTracker,
    signals::{IndicatorInput, Signal, SignalEngine},
};
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
    /// Pipeline is intentionally disabled (e.g. paper off by default).
    /// 管線刻意禁用（例如 paper 預設關閉）。
    Disabled = 3,
}

impl PipelineHealth {
    pub fn from_u8(v: u8) -> Self {
        match v {
            0 => Self::Running,
            1 => Self::Paused,
            2 => Self::Down,
            3 => Self::Disabled,
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
    /// P1-5 A2: operator-driven drawdown baseline reset. Sets
    /// `peak_balance = balance` (drawdown_pct → 0) and DELETEs the persisted
    /// `trading.paper_state_checkpoint` row for this engine. Does NOT touch
    /// positions, fills, or realized_pnl — purely a risk-governor acknowledgement
    /// that the historical peak is no longer load-bearing (e.g., after an
    /// explicit manual-close flush). Python FastAPI route wraps this with
    /// `change_audit_log` write per Root Principle #8.
    /// P1-5 A2：operator 手動重置 drawdown 基準。記憶體 peak_balance=balance、
    /// 刪除 checkpoint row；不動倉位/成交/已實現。Python 路由寫 change_audit_log。
    ResetDrawdownBaseline {
        response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    },
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
        trailing_activation_pct: Option<Option<f64>>, // Some(None)=default-to-trail, Some(Some(x))=explicit
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
        side: String, // "Buy" / "Sell"
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
    /// EDGE-P3-1 Stage 0 · Swap in a new `EdgePredictor` for `strategy` on this
    /// engine's `EdgePredictorStore`. Used by Python ML-MIT pipeline to hot-
    /// reload the ONNX model without restart. `predictor` is wrapped in
    /// `BoxedEdgePredictor` so `PipelineCommand` can stay `Debug`.
    /// EDGE-P3-1 Stage 0 · 熱換指定策略的 EdgePredictor 至本引擎的
    /// `EdgePredictorStore`。ML-MIT 透過此命令無重啟重載 ONNX 模型。
    /// `predictor` 用 `BoxedEdgePredictor` 包裝以保持 `Debug`。
    SetEdgePredictorShadow {
        strategy: String,
        predictor: crate::edge_predictor::BoxedEdgePredictor,
        response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    },
    /// EDGE-P3-1 Stage 0 · Kill-switch (Step 7e hardened): clear every loaded
    /// predictor on this engine AND (when risk_store is wired) persist the
    /// `use_edge_predictor=false` flag to disk so a crash/restart does not
    /// silently re-enable. Two-phase commit: Stage 1 `write_toml_atomic_fsynced`
    /// (disk first, fail-abort before any memory change) → Stage 2
    /// `apply_patch` ArcSwap (near-infallible) → Stage 3 `clear_all` (in-memory
    /// ONNX models). Fire-and-forget `observability.engine_events` audit row
    /// (`event_type='predictor_disabled_all'`, JSONB payload carries
    /// `operator_token_hash` + `reason` + `cleared_slots`).
    ///
    /// `operator_token`: U1 authz envelope — Python proxy layer authenticates
    /// the session and passes a per-session token (UUID-v4-ish, `len >= 32`).
    /// Rust-side only length-validates today; HMAC verification is a future hook.
    /// `reason`: operator-provided free-text audit string (stored in JSONB
    /// payload, never logged raw without the token-hash alongside).
    ///
    /// EDGE-P3-1 Stage 0 · Kill-switch（Step 7e 強化）：清空 predictor 並（當
    /// risk_store 已接線時）落盤 use_edge_predictor=false 旗標，避免重啟重啟用。
    /// 兩階段提交 Stage 1 fsync TOML → Stage 2 ArcSwap → Stage 3 clear_all；
    /// audit 行 fire-and-forget 寫入 observability.engine_events。
    /// operator_token：U1 授權 envelope（Python proxy 層填入 per-session UUID，
    /// Rust 側 len>=32 檢查），reason：operator 填寫的 free-text 審計原因。
    DisableEdgePredictorAll {
        /// U1 authz envelope — `len >= 32` required (UUID-v4-ish).
        /// U1 授權 envelope — 要求 `len >= 32`（UUID-v4 樣式）。
        operator_token: String,
        /// Operator free-text audit reason (stored in engine_events payload JSONB).
        /// operator 填寫的審計原因（存入 engine_events payload JSONB）。
        reason: String,
        response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    },
    /// EDGE-P3-1 Step 7b (plumbing-only) · Reload a single strategy's predictor
    /// from an on-disk artifact path. `engine` is carried for parity with the
    /// IPC wire protocol — by the time this variant reaches a per-engine
    /// handler the routing has already used it to pick the right
    /// `pipeline_cmd_tx`, so the handler only range-checks it (paper/demo/live
    /// whitelist) as a second-line defence against misrouting.
    ///
    /// Today the loader (`edge_predictor::load_predictor_from_path`) is a stub
    /// that returns `Err("onnx_loader_not_wired: awaiting ML-MIT #26")` — so
    /// the happy path still exists in protocol shape, but no handler can swap
    /// a real predictor until #26 lands the first ONNX artifact. Capability
    /// flag `reload_edge_predictor` stays `False` in `engine_capabilities`
    /// until then.
    ///
    /// EDGE-P3-1 Step 7b（管線骨架）· 從磁碟熱重載單一策略的 predictor。
    /// `engine` 為協定對稱攜帶（IPC 路由層已據此挑選 tx，handler 僅作白名單二次
    /// 防禦）。當前 loader 為存根（返回 "onnx_loader_not_wired"），待 ML-MIT #26
    /// 首 ONNX artifact 交付後啟用實作並翻 capability flag。
    ReloadEdgePredictor {
        /// Engine whitelist: "paper" | "demo" | "live". Defence-in-depth only —
        /// primary routing is at the IPC dispatcher. Handler rejects mismatches.
        /// 引擎白名單（paper/demo/live），handler 作對稱二次防禦。
        engine: String,
        /// Strategy key the new predictor is bound to (e.g. "ma_crossover").
        /// 目標策略鍵。
        strategy: String,
        /// Filesystem path to the ONNX artifact.
        /// ONNX artifact 的磁碟路徑。
        path: std::path::PathBuf,
        response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    },
    /// EDGE-P3-1 Stage 0 · ε-greedy shadow-fill emission from the cost gate
    /// (spec §7.3 step 7). Python consumer writes to
    /// `learning.decision_shadow_fills` with `close_tag='shadow_fill:epsilon_greedy'`.
    /// Label backfill permanently excludes these rows (§5.1 WHERE clause).
    /// EDGE-P3-1 Stage 0 · 成本門 ε-greedy shadow-fill 發射。Python 消費者寫入
    /// `learning.decision_shadow_fills`，label 回填永久排除。
    EmitShadowFill {
        context_id: String,
        strategy: String,
        symbol: String,
        /// +1 long / -1 short — pulled from FeatureVectorV1 and carried as a
        /// typed field so the Step 7c writer can bind directly into the
        /// `learning.decision_shadow_fills.side` SMALLINT column without
        /// re-parsing the JSONB payload. Added in Step 7c (2026-04-15).
        /// +1 多 / -1 空，取自 FeatureVectorV1；typed 攜帶避免 writer 再解析
        /// JSONB，直接 bind SMALLINT（Step 7c 2026-04-15 加入）。
        side: i8,
        features_jsonb: String,
        prediction_q10: f32,
        prediction_q50: f32,
        prediction_q90: f32,
        cost_bps: f64,
        ts_ms: u64,
    },
    /// EDGE-P3-1 Step 7a · Passthrough IPC entry for feeding the
    /// `learning.decision_features` training store. The main internal producer
    /// is IntentProcessor (emits at every gate evaluation); this variant exists
    /// so external callers (Python tooling, backfill scripts, replay harnesses)
    /// can inject feature rows through the same Rust-direct writer without
    /// bypassing the DB writer’s dedup + fail-closed policies.
    /// Fire-and-forget — no `response_tx` (producer has no recovery path if
    /// DB is down; writer task already JSONL-fallbacks on pool failures).
    /// EDGE-P3-1 Step 7a · 訓練特徵 passthrough IPC。主要 producer 為 IntentProcessor；
    /// 此變體供外部呼叫方（Python 工具、回填腳本、回放框架）透過相同 Rust 直寫路徑注入
    /// 特徵行，不繞過 writer 去重與 fail-closed 機制。Fire-and-forget：DB 宕機時 producer
    /// 無復原路徑，writer task 已處理 JSONL 回退。
    DecisionFeatureSnapshot {
        context_id: String,
        ts_ms: u64,
        engine_mode: String,
        strategy: String,
        symbol: String,
        side: i8,
        feature_schema_version: String,
        feature_schema_hash: String,
        feature_definition_hash: String,
        features_jsonb: String,
    },
    /// ORPHAN-ADOPT-1 Phase 2A · Adopt an exchange-reported orphan position.
    /// Dispatched by position_reconciler after `handle_orphan()` returns
    /// `OrphanDecision::Adopt` (Stage B2 AdoptPositiveEdge). Injects the
    /// position into `paper_state`; `owner_strategy` defaults to
    /// `ORPHAN_ADOPTED_STRATEGY` when None, or the triggering strategy name
    /// when Some (P0-6: real strategy attribution for adopted orphans).
    /// Fire-and-forget — adoption outcome is logged; no recovery path if the
    /// command channel is closed (pipeline already tearing down).
    /// ORPHAN-ADOPT-1 Phase 2A · 接管交易所孤兒倉位。owner_strategy 為 None 時
    /// 用 "orphan_adopted"，Some 時歸屬真實策略（P0-6 改進）。Fire-and-forget。
    AdoptOrphan {
        symbol: String,
        is_long: bool,
        qty: f64,
        entry_price: f64,
        ts_ms: u64,
        /// P0-6: real strategy name for PnL attribution. None → "orphan_adopted".
        /// P0-6：真實策略名用於 PnL 歸因。None → "orphan_adopted"。
        owner_strategy: Option<String>,
    },
    /// DYNAMIC-RISK-1: Get the per-engine sizer status snapshot as JSON.
    /// Returns the `SizerStatus` struct serialized; includes current_pct,
    /// base_pct, last_sharpe, trades_in_window, last_direction.
    /// DYNAMIC-RISK-1：取得本引擎動態風險調整器狀態（JSON SizerStatus）。
    GetDynamicRiskStatus {
        response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    },
    /// DYNAMIC-RISK-1: Toggle the sizer at runtime. TOML `[dynamic_sizing]` is
    /// still authoritative at next hot-reload — this is a transient operator
    /// override useful for incident response (flip off if sizer misbehaves).
    /// DYNAMIC-RISK-1：運行時切換啟用，僅過渡用；TOML 熱重載會覆蓋。
    SetDynamicRiskEnabled {
        enabled: bool,
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

/// Order dispatch request from tick_pipeline to exchange API (EXT-1, R-04).
/// 從 tick_pipeline 到交易所的訂單派發請求。paper_only=shadow; exchange=primary。
#[derive(Debug, Clone)]
pub struct OrderDispatchRequest {
    pub symbol: String,        // Trading symbol / 交易對
    pub is_long: bool,         // Long direction / 多方向
    pub qty: f64,              // Order quantity / 訂單數量
    pub price: f64,            // Reference price / 參考價格
    pub strategy: String,      // Strategy name / 策略名稱
    pub paper_fill_ts: u64,    // Intent generation timestamp (ms) / 意圖生成時間戳
    pub is_close: bool,        // true = closing position (reduce_only) / 平倉
    pub order_link_id: String, // EXT-1: Client order link ID / 客戶端連結 ID
    /// EXT-1: true = exchange primary (track pending); false = paper shadow (fire-and-forget)
    pub is_primary: bool,
    pub stop_loss: Option<f64>,   // I-08: broker-side SL / 券商側止損
    pub take_profit: Option<f64>, // I-08: broker-side TP / 券商側止盈
    /// FILL-CONTEXT-LINKAGE-1 (2026-04-19): signal-time context_id carried
    /// end-to-end so exchange-confirmed fills write the matching
    /// `trading.fills.entry_context_id` that JOINs to
    /// `learning.decision_features.context_id`. Open orders carry the
    /// fresh entry's id; close orders carry the live position's entry id
    /// (callers that don't know the id, e.g. orphan close, pass empty).
    /// FILL-CONTEXT-LINKAGE-1 (2026-04-19)：訊號時刻的 context_id 端到端傳遞，
    /// 確保交易所確認成交寫入的 trading.fills.entry_context_id 與
    /// learning.decision_features.context_id 可 JOIN。開單攜帶新建倉 id；
    /// 平倉攜帶當前持倉 entry id；呼叫方不知時傳空字串。
    pub context_id: String,
    /// EDGE-P2-3 Phase 1a: mirrored from OrderIntent.order_type — lowercased
    /// "market" | "limit". Dispatch layer parses to OrderType enum.
    /// EDGE-P2-3 Phase 1a：鏡射 OrderIntent.order_type — 派發層解析為 enum。
    pub order_type: String,
    /// EDGE-P2-3 Phase 1a: mirrored from OrderIntent.limit_price — required
    /// when `order_type == "limit"`, ignored for market.
    /// EDGE-P2-3 Phase 1a：鏡射 OrderIntent.limit_price — limit 單必填。
    pub limit_price: Option<f64>,
    /// EDGE-P2-3 Phase 1a: mirrored from OrderIntent.time_in_force.
    pub time_in_force: Option<crate::order_manager::TimeInForce>,
    /// EDGE-P2-3 Phase 1B-3.2: mirrored from OrderIntent.maker_timeout_ms.
    /// Set only when `time_in_force == Some(PostOnly)`. Consumed by the
    /// event_consumer timeout sweep to decide when a resting maker order
    /// must be cancelled (via orderLinkId) rather than left idle.
    /// EDGE-P2-3 Phase 1B-3.2：鏡射 OrderIntent.maker_timeout_ms。僅 PostOnly
    /// 帶值。event_consumer sweep 依此判斷何時以 orderLinkId 取消掛單。
    pub maker_timeout_ms: Option<u64>,
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
    /// OC-5: Latest index price for basis calculation (from Bybit tickers).
    /// OC-5：最新指數價格，用於基差計算（來自 Bybit tickers）。
    pub index_price: Option<f64>,
    /// EDGE-P2-2: Latest open interest (contract count, from Bybit tickers).
    /// Raw value — consumer strategies buffer + compute delta on their own window.
    /// EDGE-P2-2：最新未平倉合約數（合約張數，來自 Bybit tickers）。
    /// 此處僅暴露原始值；差分窗口由各策略自行維護。
    pub open_interest: Option<f64>,
}

/// Tick statistics for monitoring / Tick 統計。
#[derive(Debug, Default, Clone, Serialize, Deserialize)]
pub struct TickStats {
    pub total_ticks: u64,
    pub total_intents: u64,
    pub total_fills: u64,
    pub total_stops: u64,
    pub last_tick_ms: u64,
}

/// Core tick pipeline — owns all processing state / 核心 tick 管線 — 擁有所有處理狀態。
/// Phase 3: per-pipeline independent instance (3E-4 removed multi-mode shims).
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
    /// Bybit endpoint this pipeline is bound to. Determines the DB engine_mode
    /// tag (via `effective_engine_mode`) so `Live + LiveDemo` rows are tagged
    /// `"live_demo"` instead of colliding with real-mainnet `"live"`.
    /// None until `set_endpoint_env()` is called (main.rs bootstrap or test).
    /// Bybit 端點綁定，決定 DB engine_mode 標籤（via `effective_engine_mode`）。
    /// None 代表尚未由 main.rs bootstrap / 測試設定。
    pub(crate) endpoint_env: Option<crate::bybit_rest_client::BybitEnvironment>,
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
    last_persisted_signal:
        HashMap<(String, String), (openclaw_core::signals::SignalDirection, u64)>,
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
    /// EDGE-P2-3 Phase 1B-5: live MakerKpiConfig store (hot-reload). `None` =
    /// unwired mode (tick-level sync is a no-op; `maker_kpi_config` stays at
    /// `MakerKpiConfig::default()`). Tick path checks `store.version()` at
    /// tick start vs `maker_kpi_version_seen`; on bump → `apply_maker_kpi_snapshot`
    /// mirrors the snapshot into the owned `maker_kpi_config` copy. Read sites
    /// (sweep call in `on_tick`, router KPI gate) use the owned copy so they
    /// stay lock-free inside the tick.
    /// EDGE-P2-3 Phase 1B-5：live MakerKpiConfig store（熱重載）。None = 未接線
    /// （tick 同步 no-op，`maker_kpi_config` 維持 `MakerKpiConfig::default()`）。
    /// tick 頂部比對 `store.version()` 與 `maker_kpi_version_seen`；升版時
    /// `apply_maker_kpi_snapshot` 把快照鏡像進 owned copy。讀取端（on_tick 的
    /// sweep 呼叫、router 的 KPI gate）一律讀 owned copy，tick 內保持無鎖。
    maker_kpi_store: Option<std::sync::Arc<crate::config::ConfigStore<crate::paper_state::MakerKpiConfig>>>,
    /// EDGE-P2-3 Phase 1B-5: owned snapshot of the live MakerKpiConfig used
    /// by the tick hot path. Initialised to `MakerKpiConfig::default()` in
    /// the constructor (bit-identical to the pre-hot-reload behaviour when
    /// no store is wired); overwritten by `apply_maker_kpi_snapshot` on every
    /// detected store version bump.
    /// EDGE-P2-3 Phase 1B-5：tick 熱路徑使用的 owned MakerKpiConfig 快照。
    /// 建構子設為 `MakerKpiConfig::default()`（未接 store 時 bit-identical
    /// 於熱重載前的行為）；store 升版時由 `apply_maker_kpi_snapshot` 覆寫。
    maker_kpi_config: crate::paper_state::MakerKpiConfig,
    /// EDGE-P2-3 Phase 1B-5: last seen MakerKpiConfig version number — mirrors
    /// the `risk_config_version_seen` pattern so the tick-level sync can skip
    /// the `ArcSwap::load()` allocation whenever no patch has landed.
    /// EDGE-P2-3 Phase 1B-5：上一次見到的 MakerKpiConfig 版本號；與
    /// `risk_config_version_seen` 同模式，未升版時 tick 同步可跳過
    /// `ArcSwap::load()` 分配。
    maker_kpi_version_seen: u64,
    /// Phase 3: Per-mode trading state (Signal Diamond architecture).
    // 3E-4: mode_states and active_modes REMOVED — each pipeline is now
    // an independent TickPipeline instance with its own PipelineKind.
    // 3E-4：mode_states 和 active_modes 已移除 — 每管線是獨立 TickPipeline 實例。
    /// Global system mode — synced from Python GUI. Gates trading at tick level.
    /// 全局系統模式 — 從 Python GUI 同步。在 tick 級別封鎖交易。
    system_mode: SystemMode,
    /// EDGE-P0-1 + P0-5 + B2: Map of symbol → (last ReduceToHalf `event.ts_ms`, effective cooldown ms).
    /// Guards against repeat half-qty emits on the same symbol within the
    /// per-event cooldown (base 60s, scaled up by trigger sigma via
    /// `sigma_scaled_reduce_cooldown_ms` — see on_tick_helpers). Also fully
    /// cleared when risk returns to Normal so a new episode can re-arm.
    /// Replaces the pre-P0-5 HashSet, which was nullified every tick in
    /// persistent Cautious under the FA-PHANTOM-2 5%+3σ path.
    /// EDGE-P0-1 + P0-5 + B2：symbol → (上次半倉時間戳, 當時有效冷卻 ms)。
    /// 冷卻按觸發 sigma 縮放，risk 回 Normal 時整表清空。
    ft_reduced_symbols: std::collections::HashMap<String, on_tick_helpers::FtReduceStamp>,
    /// EDGE-P1-2: Cached latest funding rate per symbol (from Ticker events).
    /// EDGE-P1-2：每幣種最新資金費率緩存（來自 Ticker 事件）。
    funding_rates: HashMap<String, f64>,
    /// OC-5: Cached latest index price per symbol (from Ticker events).
    /// OC-5：每幣種最新指數價格緩存（來自 Ticker 事件）。
    index_prices: HashMap<String, f64>,
    /// EDGE-P2-2: Cached latest open interest per symbol (from Ticker events).
    /// Raw value only — delta/window computation lives inside consuming strategies.
    /// EDGE-P2-2：每幣種最新 OI 緩存（來自 Ticker 事件）。僅儲原始值，
    /// 差分／滾動窗口由消費者策略自行維護，避免跨策略污染。
    open_interests: HashMap<String, f64>,
    /// EDGE-P3-1 Stage 0: Per-strategy quantile predictor store for this engine.
    /// None until the engine bootstrap registers one. When present, the
    /// intent processor's cost gate consults it before falling through to the
    /// JS shrinkage gate (wired in A4). Hot-swapped via
    /// `PipelineCommand::SetEdgePredictorShadow` / `DisableEdgePredictorAll`.
    /// EDGE-P3-1 Stage 0：本引擎的逐策略 quantile 預測器 store。引擎啟動註冊後
    /// 由 intent processor cost gate 在 JS shrinkage 之前諮詢（A4 接線）。
    /// 通過 IPC 熱換 / 清空。
    edge_predictor_store: Option<Arc<crate::edge_predictor::EdgePredictorStore>>,
    /// EDGE-P3-1 Step 7a: Cached sender for `DecisionFeatureMsg` writes, used by
    /// the `DecisionFeatureSnapshot` IPC passthrough handler. Also propagated to
    /// `IntentProcessor` at wire-up time so the internal producer uses the same
    /// writer. `None` = emission disabled (fail-soft; no training collection but
    /// trading unaffected).
    /// EDGE-P3-1 Step 7a：供 `DecisionFeatureSnapshot` IPC passthrough 使用的 sender
    /// 緩存；同時傳給 IntentProcessor 讓內部 producer 共用同一 writer。
    /// None 時發射停用（fail-soft，不影響交易）。
    decision_feature_tx: Option<tokio::sync::mpsc::Sender<crate::database::DecisionFeatureMsg>>,
    /// EDGE-P3-1 Step 7c: Cached sender for `ShadowFillMsg` writes, used by
    /// the `EmitShadowFill` IPC handler to forward ε-greedy paper exploration
    /// fills into `learning.decision_shadow_fills`. Paper-only (the predictor
    /// gate already guards `is_paper`); `None` = emission disabled (fail-soft;
    /// no Stage-4 exploration collection but trading unaffected).
    /// EDGE-P3-1 Step 7c：供 `EmitShadowFill` IPC handler 將 ε-greedy paper 探索
    /// 轉寫 `learning.decision_shadow_fills` 的 sender。僅 paper（gate 已保證）。
    /// None 時發射停用（fail-soft，不採集 Stage-4 探索但不影響交易）。
    shadow_fill_db_tx: Option<tokio::sync::mpsc::Sender<crate::database::ShadowFillMsg>>,
    /// EXIT-FEATURES-TABLE-1: Cached sender for `ExitFeatureRow` writes. The
    /// `emit_close_fill` path builds one row per position exit and try_send's
    /// here. `None` = emission disabled (fail-soft; trading unaffected, just
    /// no Track P label collection). Wired per-engine from `main.rs`.
    /// EXIT-FEATURES-TABLE-1：`ExitFeatureRow` 發送端；`emit_close_fill` 於每筆
    /// 平倉組一列並 try_send 入此通道。None = 停用（fail-soft，不影響交易）。
    /// 由 `main.rs` 逐引擎接線。
    exit_feature_tx: Option<tokio::sync::mpsc::Sender<crate::database::ExitFeatureRow>>,
    /// Scanner symbol registry — gates new opens to scanner-active symbols only.
    /// None = gate disabled (all symbols allowed, e.g. tests / standalone).
    /// 掃描器交易對注冊表 — 新開倉僅限掃描器活躍交易對。
    /// None = 門控停用（允許所有交易對，如測試/獨立運行）。
    symbol_registry: Option<Arc<crate::scanner::registry::SymbolRegistry>>,
    /// DUST-EVICTION-GAP-1 / P1-8 FUP (2026-04-17): per-symbol last `NeedsEviction`
    /// dispatch timestamp (ms since epoch). Used to rate-limit `ipc_close_symbol`
    /// retries on symbols whose retriage keeps asking for a close but the exchange
    /// has yet to settle the fill. Matches `ORPHAN_CLOSE_DEDUP_MS` cadence (2 min).
    /// DUST-EVICTION-GAP-1 / P1-8 FUP：每 symbol 最後一次重分流派 CloseSymbol 的
    /// 時間戳，用於速率限制（與 ORPHAN_CLOSE_DEDUP_MS 2 min 一致）。
    retriage_last_evict_ms: HashMap<String, u64>,
    /// DYNAMIC-RISK-1: Per-engine Sharpe-aware sizer. Adjusts
    /// `IntentProcessor::p1_risk_pct` up/down after realized PnL closes.
    /// Disabled by default; enabled via `[risk.dynamic_sizing]` TOML block.
    /// DYNAMIC-RISK-1：引擎私有的 Sharpe 調整器，平倉後上調/下調
    /// `IntentProcessor::p1_risk_pct`。預設停用，`[risk.dynamic_sizing]` 啟用。
    pub dynamic_risk_sizer: crate::dynamic_risk_sizer::DynamicRiskSizer,
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
            endpoint_env: None,
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
            maker_kpi_store: None,
            maker_kpi_config: crate::paper_state::MakerKpiConfig::default(),
            maker_kpi_version_seen: 0,
            // 3E-4: mode_states/active_modes removed (per-pipeline architecture)
            system_mode: SystemMode::default(),
            ft_reduced_symbols: std::collections::HashMap::new(),
            funding_rates: HashMap::new(),
            index_prices: HashMap::new(),
            // EDGE-P2-2: init empty OI cache; filled on first ticker with openInterest.
            // EDGE-P2-2：初始化空 OI 緩存；首次攜帶 openInterest 的 ticker 後填充。
            open_interests: HashMap::new(),
            edge_predictor_store: None,
            decision_feature_tx: None,
            shadow_fill_db_tx: None,
            exit_feature_tx: None,
            symbol_registry: None,
            retriage_last_evict_ms: HashMap::new(),
            // DYNAMIC-RISK-1: anchored on IntentProcessor's default p1_risk_pct (3%).
            // DYNAMIC-RISK-1：以 IntentProcessor 預設 p1_risk_pct (3%) 為錨。
            dynamic_risk_sizer: crate::dynamic_risk_sizer::DynamicRiskSizer::new(
                0.03,
                crate::dynamic_risk_sizer::DynamicRiskSizerConfig::default(),
            ),
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
        // EDGE-P3-1 Phase B #4 coupled fix: forward `kind` into the IntentProcessor
        // copy that the predictor gate reads via `inputs.engine_kind`. Without this,
        // `IntentProcessor::pipeline_kind` stays at its constructor default (Paper)
        // for demo/live pipelines — the ε-greedy branch at `gate.rs:213` then fires
        // on demo/live too and only gets stopped by the writer-level R5 defense +
        // DB CHECK. Forwarding here keeps the gate itself paper-only, matching
        // spec §7.3 C13.
        // EDGE-P3-1 Phase B #4 配套修復：把 `kind` 透傳給 IntentProcessor（gate 讀
        // `inputs.engine_kind`）。未透傳則 demo/live 的 IntentProcessor 仍是 Paper，
        // ε-greedy 會誤發 ShadowFill，由 R5 與 DB CHECK 兜底才擋下來；在 gate 層
        // 直接擋住與 §7.3 C13 一致。
        p.intent_processor.set_pipeline_kind(kind);
        p.governance = GovernanceCore::new_with_profile(kind.governance_profile());
        p
    }

    /// Bind this pipeline to a concrete Bybit endpoint so DB rows tag with the
    /// endpoint-aware engine_mode (see `mode_state::effective_engine_mode`).
    /// Also propagates to `IntentProcessor` so its internal DB writes (e.g.
    /// decision_feature snapshots) use the same tag.
    /// 將管線綁定到具體 Bybit 端點，DB 寫入使用 endpoint-aware engine_mode。
    /// 同時透傳至 IntentProcessor 讓其 DB 寫入（如決策特徵快照）一致。
    pub fn set_endpoint_env(&mut self, env: crate::bybit_rest_client::BybitEnvironment) {
        self.endpoint_env = Some(env);
        self.intent_processor.set_endpoint_env(env);
    }

    /// Wire the shared scanner SymbolRegistry so new opens are gated to
    /// scanner-active symbols only. Must be called after construction.
    /// 接入掃描器 SymbolRegistry，新開倉僅限掃描器活躍交易對。
    pub fn set_symbol_registry(&mut self, reg: Arc<crate::scanner::registry::SymbolRegistry>) {
        self.symbol_registry = Some(reg);
    }

    /// DB engine_mode tag for this pipeline (endpoint-aware). All DB-writing
    /// code paths inside TickPipeline should route through this, NOT through
    /// `self.pipeline_kind.db_mode()` directly — the latter loses the
    /// endpoint distinction (Live + LiveDemo would collide with real
    /// mainnet live).
    /// 本管線的 DB engine_mode 標籤（endpoint 感知）。所有 DB 寫入路徑都應走這裡。
    #[inline]
    pub fn effective_engine_mode(&self) -> &'static str {
        crate::mode_state::effective_engine_mode(self.pipeline_kind, self.endpoint_env)
    }

    /// Endpoint-aware GovernanceProfile for per-intent cost-gate selection
    /// (P0-6 方案 A). Intent-processing paths must call this instead of
    /// `self.pipeline_kind.governance_profile()` — the latter ignores the
    /// bound endpoint and forces Production cost gate for LiveDemo,
    /// producing the cold-start deadlock (P0-6 RCA 2026-04-17).
    /// 本管線的 cost-gate GovernanceProfile（endpoint 感知）。
    /// Intent 處理路徑必須走這裡，避免 LiveDemo 被強制走 Production。
    #[inline]
    pub fn effective_governance_profile(
        &self,
    ) -> openclaw_core::governance_core::GovernanceProfile {
        crate::mode_state::effective_governance_profile(self.pipeline_kind, self.endpoint_env)
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
        self.last_persisted_signal
            .retain(|(sym, _), _| sym != symbol);
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
    pub fn set_linucb_runtime(&mut self, rt: std::sync::Arc<crate::linucb::LinUcbRuntime>) {
        self.linucb = Some(rt);
    }

    /// EDGE-P3-1 Phase B #1: Inject the per-engine `EdgePredictorStore` handle.
    /// Engine bootstrap in `main.rs` creates one store per PipelineKind
    /// (paper/demo/live) and passes the Arc here. Single call wires both sides:
    /// TickPipeline (for `handle_paper_command` IPC swap/clear) + IntentProcessor
    /// (for the §7.3 gate load_for lookup). Without the propagation, the IPC
    /// side would accept `SetEdgePredictorShadow` but the gate would still see
    /// `store = None` and short-circuit to legacy shrinkage.
    /// EDGE-P3-1 Phase B #1：注入本引擎的 `EdgePredictorStore` handle。
    /// 單次調用把 Arc 同時塞給 TickPipeline（IPC 熱換用）與 IntentProcessor
    /// （§7.3 gate load_for 讀取用）— 缺一會造成 IPC 收命令但 gate 仍走 legacy。
    pub fn set_edge_predictor_store(
        &mut self,
        store: std::sync::Arc<crate::edge_predictor::EdgePredictorStore>,
    ) {
        debug_assert!(
            self.edge_predictor_store.is_none(),
            "EdgePredictorStore injected twice — bootstrap should call this exactly once per pipeline"
        );
        self.intent_processor
            .set_edge_predictor_store(store.clone());
        self.edge_predictor_store = Some(store);
    }

    /// EDGE-P3-1 A4 + B wiring: inject the PipelineCommand sender used by the
    /// IntentProcessor predictor gate to emit `EmitShadowFill` for ε-greedy
    /// paper exploration (spec §7.3). Without this bootstrap call the gate's
    /// `emit_shadow_fill` path hits the fail-soft `None` drop branch and all
    /// shadow fills are silently discarded — breaking Stage 4 paper learning.
    /// EDGE-P3-1 A4 + B 接線：注入 PipelineCommand 發送端供 IntentProcessor
    /// predictor gate 在 ε-greedy paper 探索時發出 `EmitShadowFill`（spec §7.3）。
    /// 缺此接線則 shadow fill 走 fail-soft 丟棄分支，Stage 4 paper 學習失效。
    pub fn set_shadow_fill_tx(&mut self, tx: tokio::sync::mpsc::UnboundedSender<PipelineCommand>) {
        self.intent_processor.set_shadow_fill_tx(tx);
    }

    /// EDGE-P3-1 Step 7a: Wire the decision-feature DB channel. Single call
    /// registers the tx for both the IntentProcessor (internal producer — one
    /// row per gate eval) and the `DecisionFeatureSnapshot` IPC passthrough
    /// handler. `None` leaves emission as no-op (fail-soft). Call exactly
    /// once per pipeline during bootstrap.
    /// EDGE-P3-1 Step 7a：把決策特徵 DB 通道同時接給 IntentProcessor（內部 producer）
    /// 與 `DecisionFeatureSnapshot` IPC passthrough。未接線時為 no-op（fail-soft）。
    /// 每個 pipeline 啟動時只呼叫一次。
    pub fn set_decision_feature_tx(
        &mut self,
        tx: tokio::sync::mpsc::Sender<crate::database::DecisionFeatureMsg>,
    ) {
        debug_assert!(
            self.decision_feature_tx.is_none(),
            "decision_feature_tx injected twice — bootstrap should call this exactly once per pipeline"
        );
        self.intent_processor.set_decision_feature_tx(tx.clone());
        self.decision_feature_tx = Some(tx);
    }

    /// EDGE-P3-1 Step 7a: Accessor for the `DecisionFeatureSnapshot` IPC
    /// handler. Returns `None` until `set_decision_feature_tx` has been called.
    /// EDGE-P3-1 Step 7a：IPC handler 用的 tx 取用器；未接線前返回 None。
    pub fn decision_feature_tx(
        &self,
    ) -> Option<&tokio::sync::mpsc::Sender<crate::database::DecisionFeatureMsg>> {
        self.decision_feature_tx.as_ref()
    }

    /// EDGE-P3-1 Step 7c: Wire the shadow-fill DB channel. Call exactly once
    /// per pipeline during bootstrap. `None` leaves emission as fail-soft
    /// no-op (predictor gate still runs; Stage-4 exploration rows just not
    /// persisted).
    /// EDGE-P3-1 Step 7c：接 shadow-fill DB 通道，每 pipeline 只呼叫一次。
    /// 未接線時發射為 fail-soft no-op（gate 仍運作，僅 Stage-4 列不持久化）。
    pub fn set_shadow_fill_db_tx(
        &mut self,
        tx: tokio::sync::mpsc::Sender<crate::database::ShadowFillMsg>,
    ) {
        debug_assert!(
            self.shadow_fill_db_tx.is_none(),
            "shadow_fill_db_tx injected twice — bootstrap should call this exactly once per pipeline"
        );
        self.shadow_fill_db_tx = Some(tx);
    }

    /// EDGE-P3-1 Step 7c: Accessor for the `EmitShadowFill` IPC handler.
    /// Returns `None` until `set_shadow_fill_db_tx` has been called.
    /// EDGE-P3-1 Step 7c：IPC handler 用的 tx 取用器；未接線前返回 None。
    pub fn shadow_fill_db_tx(
        &self,
    ) -> Option<&tokio::sync::mpsc::Sender<crate::database::ShadowFillMsg>> {
        self.shadow_fill_db_tx.as_ref()
    }

    /// EXIT-FEATURES-TABLE-1: Wire the exit-feature DB channel. Call exactly
    /// once per pipeline during bootstrap (main.rs passes the same writer tx
    /// to all three engines — multi-producer is safe). `None` leaves emission
    /// as fail-soft no-op (trading unaffected, just no Track P label collection).
    /// EXIT-FEATURES-TABLE-1：接 exit-feature DB 通道；每 pipeline 啟動時呼叫一次。
    /// 未接線時 emit_close_fill 走 fail-soft no-op。
    pub fn set_exit_feature_tx(
        &mut self,
        tx: tokio::sync::mpsc::Sender<crate::database::ExitFeatureRow>,
    ) {
        debug_assert!(
            self.exit_feature_tx.is_none(),
            "exit_feature_tx injected twice — bootstrap should call this exactly once per pipeline"
        );
        self.exit_feature_tx = Some(tx);
    }

    /// EXIT-FEATURES-TABLE-1: Accessor for the `emit_close_fill` producer
    /// path. Returns `None` until `set_exit_feature_tx` has been called.
    /// EXIT-FEATURES-TABLE-1：emit_close_fill 產生器的 tx 取用器；未接線前回 None。
    pub fn exit_feature_tx(
        &self,
    ) -> Option<&tokio::sync::mpsc::Sender<crate::database::ExitFeatureRow>> {
        self.exit_feature_tx.as_ref()
    }

    /// EXIT-FEATURES-TABLE-1: Read-only accessor to the pre-existing
    /// `price_tracker` used both by fast_track and the exit-feature ROC
    /// computation. Exposed so `emit_close_fill` can compute `price_roc_short`
    /// without duplicating the per-tick sample feed already wired in `on_tick`.
    /// EXIT-FEATURES-TABLE-1：價格追蹤器的唯讀取用器；emit_close_fill 用來計算
    /// price_roc_short，避免重複 per-tick 樣本饋入。
    pub fn price_tracker(&self) -> &PriceHistoryTracker {
        &self.price_tracker
    }

    /// EXIT-FEATURES-TABLE-1 (tests only): mutable handle so unit tests can
    /// seed price samples for ROC / ATR / giveback assertions without
    /// spinning a full on_tick loop. Not used in production paths.
    /// EXIT-FEATURES-TABLE-1（僅測試）：測試用可變 handle，用來預填價格樣本
    /// 做 ROC/ATR/giveback 斷言，無需走完整 on_tick。非生產路徑。
    #[cfg(test)]
    pub(crate) fn price_tracker_mut(&mut self) -> &mut PriceHistoryTracker {
        &mut self.price_tracker
    }

    /// EDGE-P3-1 Phase B #4: Reseed the IntentProcessor predictor RNG.
    /// Bootstrap should call this exactly once per pipeline with
    /// `seed_for_engine(startup_nanos, kind)` so paper/demo/live each get a
    /// distinct ε-greedy stream (spec §7.3 F9). Without this call every engine
    /// runs with the constructor default `SmallRng::seed_from_u64(0)` — all
    /// three engines produce identical exploration draws and the per-kind
    /// discriminant XOR in `seed_for_engine` is inert.
    /// EDGE-P3-1 Phase B #4：重置 IntentProcessor predictor RNG。
    /// 啟動時以 `seed_for_engine(startup_nanos, kind)` 每個 pipeline 呼叫一次；
    /// 不做則三引擎共用 seed=0，kind 互異失去意義。
    pub fn set_predictor_rng_seed(&mut self, seed: u64) {
        self.intent_processor.set_predictor_rng_seed(seed);
    }

    /// EDGE-P3-1 Stage 0: Accessor for command handlers that need to mutate
    /// the store (swap / clear). Returns `None` until `set_edge_predictor_store`
    /// is called.
    /// EDGE-P3-1 Stage 0：命令 handler 用的 store 取用器；未注入前返回 None。
    pub fn edge_predictor_store(
        &self,
    ) -> Option<&std::sync::Arc<crate::edge_predictor::EdgePredictorStore>> {
        self.edge_predictor_store.as_ref()
    }

    /// EDGE-P3-1 Step 7e: Accessor for command handlers that need to mutate
    /// the live `RiskConfig` (e.g. `DisableEdgePredictorAll` two-phase commit
    /// flips `use_edge_predictor=false` on disk + ArcSwap before clearing the
    /// in-memory predictor slots). Returns `None` when the pipeline is running
    /// without a wired store — handler falls back to memory-only clear.
    /// EDGE-P3-1 Step 7e：命令 handler 用的 RiskConfig 取用器；未接線時 handler
    /// 退回 memory-only clear。
    pub fn risk_store(
        &self,
    ) -> Option<&std::sync::Arc<crate::config::ConfigStore<crate::config::RiskConfig>>> {
        self.risk_store.as_ref()
    }

    /// W-4: Plug in a shared NewsContextSnapshot (read-only on the live path).
    /// W-4：注入共享 NewsContextSnapshot（live 路徑唯讀）。
    pub fn set_news_snapshot(&mut self, snap: std::sync::Arc<crate::news::NewsContextSnapshot>) {
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

        // DYNAMIC-RISK-1: rebuild sizer from the fresh `dynamic_sizing` block
        // and re-anchor on `per_trade_risk_pct`. Config changes are operator-
        // originated (TOML hot-reload) — current_pct resets to base so drift
        // never accumulates across operator intents.
        // DYNAMIC-RISK-1：從新 dynamic_sizing 區塊重建，並以 per_trade_risk_pct
        // 重錨；config 變動皆 operator 觸發，current 回 base 避免跨 operator 意圖累積漂移。
        self.dynamic_risk_sizer = crate::dynamic_risk_sizer::DynamicRiskSizer::new(
            snap.limits.per_trade_risk_pct,
            snap.dynamic_sizing.clone(),
        );
        // Apply the base immediately so IntentProcessor reflects TOML intent until
        // the sizer earns enough data to deviate.
        // 立即把 base 推入 IntentProcessor，讓其反映 TOML 意圖，之後調整器累積足夠資料才偏移。
        self.intent_processor
            .set_p1_risk_pct(snap.limits.per_trade_risk_pct);

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
        self.governance.risk.thresholds = openclaw_core::sm::risk_gov::EscalationThresholds {
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

    /// EDGE-P2-3 Phase 1B-5: Inject the live MakerKpiConfig ConfigStore handle.
    /// After wiring, the pipeline seeds the owned `maker_kpi_config` copy from
    /// the current snapshot and records the version so the next tick-level
    /// sync no-ops. Subsequent operator patches bump the version and the
    /// next `on_tick` picks up the new snapshot via
    /// `sync_maker_kpi_config_if_changed`.
    /// EDGE-P2-3 Phase 1B-5：注入 live MakerKpiConfig ConfigStore。接線後立即把
    /// 當前快照播入 owned `maker_kpi_config` 並記錄版本號，後續 tick 同步
    /// 在未升版時 no-op；operator patch 升版後下一個 `on_tick` 自動拾取。
    pub fn set_maker_kpi_store(
        &mut self,
        store: std::sync::Arc<crate::config::ConfigStore<crate::paper_state::MakerKpiConfig>>,
    ) {
        // Immediate sync so the first tick already sees the live config.
        // Push to the router-facing IntentProcessor snapshot too, so a
        // `set_maker_kpi_store` wired before any ticks run still leaves the
        // router's KPI gate reading the live thresholds (not the
        // constructor's `MakerKpiConfig::default()` placeholder).
        // 立即同步：首個 tick 就看到 live 快照；同步推入 IntentProcessor，
        // 避免 `set_maker_kpi_store` 於首個 tick 之前接線時，router 的
        // KPI gate 仍讀到建構子預設值。
        let snap = store.load();
        let fresh = (*snap).clone();
        self.intent_processor.update_maker_kpi_config(fresh.clone());
        self.maker_kpi_config = fresh;
        self.maker_kpi_version_seen = store.version();
        self.maker_kpi_store = Some(store);
    }

    /// EDGE-P2-3 Phase 1B-5: Hot-reload hook called at the top of on_tick.
    /// Mirrors `sync_risk_config_if_changed`: compare the store's monotonic
    /// version to `maker_kpi_version_seen`; on bump, pull the snapshot into
    /// the owned `maker_kpi_config` copy (used by the paper sweep) AND push
    /// the same snapshot into `IntentProcessor.maker_kpi_config` so the
    /// router's PostOnly KPI gate picks up the patched thresholds on the
    /// very next routed intent — without any `ArcSwap::load()` inside the
    /// tick hot path for subsequent ticks.
    /// EDGE-P2-3 Phase 1B-5：`on_tick` 頂部的熱重載檢查。與
    /// `sync_risk_config_if_changed` 同模式：比對版本，升版時把快照寫進
    /// owned `maker_kpi_config`（紙盤 sweep 使用），並推入
    /// `IntentProcessor.maker_kpi_config` 讓 router PostOnly KPI gate 下一筆
    /// 意圖即見新門檻；後續 tick 無需再觸發 `ArcSwap::load()`。
    #[inline]
    fn sync_maker_kpi_config_if_changed(&mut self) {
        if let Some(ref store) = self.maker_kpi_store {
            let v = store.version();
            if v != self.maker_kpi_version_seen {
                let snap = store.load();
                let fresh = (*snap).clone();
                self.intent_processor.update_maker_kpi_config(fresh.clone());
                self.maker_kpi_config = fresh;
                self.maker_kpi_version_seen = v;
                tracing::info!(
                    new_version = v,
                    funding_drag_threshold = self.maker_kpi_config.funding_drag_threshold,
                    min_fill_rate = self.maker_kpi_config.min_fill_rate,
                    min_avg_net_edge_bps = self.maker_kpi_config.min_avg_net_edge_bps,
                    "EDGE-P2-3 1B-5 maker KPI config hot-reloaded"
                );
            }
        }
    }

    /// ARCH-RC1 1C-2-B: Read the live `cost_edge_max_ratio` for the tick-level
    /// cost-edge check. Falls back to the production default (MICRO-PROFIT-FIX-1
    /// 0.2) when BudgetConfig store is not wired (1C-1 / unit-test paths).
    /// ARCH-RC1 1C-2-B：熱路徑讀取 live cost_edge_max_ratio；store 未接線時回退
    /// 當前 default（MICRO-PROFIT-FIX-1 後為 0.2）。
    #[inline]
    fn current_cost_edge_max_ratio(&self) -> f64 {
        match self.budget_store.as_ref() {
            Some(store) => store.load().attention_tax.cost_edge_max_ratio,
            None => 0.2,
        }
    }

    /// MICRO-PROFIT-FIX-1 (2026-04-17): Read the live `min_profit_to_close_pct`
    /// floor for the COST EDGE gate's narrow lock-in band. Falls back to the
    /// production default (0.3%) when BudgetConfig store is not wired
    /// (1C-1 / unit-test paths).
    /// MICRO-PROFIT-FIX-1：熱路徑讀取 live min_profit_to_close_pct；未接線時回退 0.3。
    #[inline]
    fn current_min_profit_to_close_pct(&self) -> f64 {
        match self.budget_store.as_ref() {
            Some(store) => store.load().attention_tax.min_profit_to_close_pct,
            None => 0.3,
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
        // DYNAMIC-RISK-1: feed realized PnL into the per-engine sizer.
        // Skip the zero-pnl fallback branch (close_price == entry_price when
        // no latest price is known) so synthetic break-even values don't
        // pollute the Sharpe window. DYNAMIC-RISK-1 BUG-10 fix.
        // DYNAMIC-RISK-1：把實現 PnL 餵入 sizer；跳過 entry-price fallback
        // 產生的假零值，避免污染 Sharpe 視窗。
        if pnl != 0.0 {
            self.dynamic_risk_sizer.record_closed_trade(pnl);
        }
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
    /// EDGE-P3-1 R2: `entry_context_id` is the context_id of the entry that opened
    /// the position being closed. Pass empty string when unknown (pre-V017 restored
    /// positions, orphan adopts, tests). Typical call sites capture it via
    /// `self.paper_state.get_entry_context_id(symbol)` **before** invoking the
    /// `close_position*` helper that removes the position, then pass it here.
    /// EDGE-P3-1 R2：entry_context_id 為開此倉 entry 的 context_id。未知時空串。
    /// 典型呼叫：先 `paper_state.get_entry_context_id(symbol)` 捕獲，再關倉，再傳入。
    fn emit_close_fill(
        &mut self,
        symbol: &str,
        is_long: bool,
        qty: f64,
        price: f64,
        ts_ms: u64,
        realized_pnl: f64,
        close_tag: &str,
        entry_context_id: &str,
        exit_snapshot: Option<&crate::paper_state::PositionExitSnapshot>,
    ) {
        // PNL-FIX-2: compute close fee from per-symbol taker rate, charge it
        // to paper_state, and record it in the DB row. Charge always happens
        // (even when trading_tx is unwired) so paper_state.balance / total_fees
        // stay consistent with the close action regardless of persistence.
        let fr = self.intent_processor.fee_rate(symbol);
        let close_fee = qty * price * fr;
        self.paper_state.charge_fee(close_fee);
        let em = self.effective_engine_mode();
        if let Some(ref tx) = self.trading_tx {
            // Fill side reflects the closing direction (opposite of position side).
            let close_side = if is_long { "Sell" } else { "Buy" };
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
                entry_context_id: entry_context_id.to_string(),
                engine_mode: em.to_string(),
            });
        }
        self.stats.total_fills += 1;
        // Mirror the close fill into the in-memory ring buffer so GUI snapshot
        // readers see it. Without this, `recent_fills` only contained open fills
        // and every risk_close / stop_trigger / strategy_close silently bypassed
        // the buffer — DB had the data but the snapshot view was blind.
        // `is_long` is the POSITION side; the closing order is the opposite.
        // 鏡像平倉 fill 到環形緩衝供 GUI 快照讀取；否則 recent_fills 只有開倉 fill，
        // 所有 risk_close / stop_trigger / strategy_close 都悄悄繞過緩衝。
        on_tick_helpers::push_capped(
            &mut self.recent_fills,
            TimestampedFill {
                timestamp_ms: ts_ms,
                symbol: symbol.to_string(),
                is_long: !is_long,
                qty,
                price,
                fee: close_fee,
                realized_pnl,
                strategy: close_tag.to_string(),
            },
            50,
        );

        self.try_emit_exit_feature_row(symbol, qty, price, ts_ms, realized_pnl,
                                       close_fee, fr, close_tag, exit_snapshot,
                                       entry_context_id);
    }

    /// EXIT-FEATURES-TABLE-1: emit one row to `learning.exit_features` per
    /// close. Requires both a captured pre-close snapshot (caller's
    /// responsibility — position is already removed by the time we run) and
    /// a wired tx. With either missing we degrade to fail-soft no-op —
    /// trading is unaffected, only Track P label collection for this close
    /// is skipped. Split out so non-`emit_close_fill` close paths
    /// (`ipc_close_symbol` paper branch, `process_external_fill`) can emit
    /// exit features without going through full Fill-persistence logic that
    /// those paths already handle themselves.
    /// EXIT-FEATURES-TABLE-1：獨立 helper，支援非 emit_close_fill 路徑
    /// （ipc_close_symbol paper 分支、process_external_fill 外部 fill 回報）
    /// 的 exit feature 發送。缺 snap 或 tx → fail-soft no-op。
    pub(crate) fn try_emit_exit_feature_row(
        &self,
        symbol: &str,
        qty: f64,
        price: f64,
        ts_ms: u64,
        realized_pnl: f64,
        close_fee: f64,
        fee_rate: f64,
        close_tag: &str,
        exit_snapshot: Option<&crate::paper_state::PositionExitSnapshot>,
        entry_context_id: &str,
    ) {
        let em = self.effective_engine_mode();
        if let (Some(snap), Some(tx)) = (exit_snapshot, self.exit_feature_tx.as_ref()) {
            let row =
                self.build_exit_feature_row(symbol, qty, price, ts_ms, realized_pnl,
                                            close_fee, fee_rate, close_tag, snap, em,
                                            entry_context_id);
            // try_send: never block the close path. Overflow → row dropped,
            // writer logs the channel pressure via its own metric.
            // try_send：永不阻塞 close 路徑；溢出 → 丟列，由 writer 自行計量。
            let _ = tx.try_send(row);
        }
    }

    /// EXIT-FEATURES-TABLE-1: assemble one `ExitFeatureRow` from the captured
    /// position snapshot + current tick context. Pure data-shaping — no IO,
    /// no mutation beyond what `emit_close_fill` already did before calling
    /// this. Split out of `emit_close_fill` so the 7-dim math has its own test
    /// surface and the signature stays readable.
    ///
    /// Derivation summary:
    ///   est_net_bps       = edge_estimates[(owner_strategy, symbol)].shrunk_bps  (None on miss)
    ///   peak_pnl_pct      = snapshot.max_favorable_pnl_pct                       (always Some; 0.0 pre-first-tick)
    ///   atr_pct           = price_tracker.compute_atr_pct(symbol)                (None until ≥ min samples)
    ///   giveback_atr_norm = (peak_pct - current_pct) / atr_pct                   (None when atr_pct None/≤0)
    ///   time_since_peak_ms= ts_ms (i64) − peak_reached_ts_ms                     (clamped ≥ 0)
    ///   price_roc_short   = price_tracker.compute_roc(symbol, 300 ms)            (None until ≥ 2 samples in window)
    ///   entry_age_secs    = (ts_ms − entry_ts_ms) / 1000                         (None if ts_ms < entry_ts_ms)
    ///
    /// realized_net_bps = (realized_pnl / entry_notional_for_portion) × 10000
    ///                  − round_trip_fee_bps (2 × fee_rate × 10000).
    /// entry_notional_for_portion uses the portion's entry notional
    /// (`qty * entry_price`) rather than the position's aggregate accumulated
    /// `entry_notional` so partial closes report bps of the portion actually
    /// exiting.
    ///
    /// EXIT-FEATURES-TABLE-1：純資料整形，無 IO、無副作用；從 emit_close_fill
    /// 拆出以便 7 維衍生獨立測試、並保持原簽名可讀。realized_net_bps 以本段
    /// 平倉部位對應的入場 notional 計算（非聚合 entry_notional），partial close
    /// 才不會誤放大。
    fn build_exit_feature_row(
        &self,
        symbol: &str,
        qty: f64,
        close_price: f64,
        ts_ms: u64,
        realized_pnl: f64,
        close_fee: f64,
        fee_rate: f64,
        close_tag: &str,
        snap: &crate::paper_state::PositionExitSnapshot,
        engine_mode: &str,
        caller_entry_context_id: &str,
    ) -> crate::database::ExitFeatureRow {
        let ts_ms_i64 = ts_ms as i64;
        // est_net_bps — shrunk JS edge for (entry strategy, symbol). Cell miss
        // keeps it None rather than folding in grand_mean_bps: the label
        // preserves "we had no cell" as a distinct signal downstream.
        let est_net_bps = self
            .intent_processor
            .edge_estimates()
            .get_cell(&snap.owner_strategy, symbol)
            .map(|c| c.shrunk_bps as f32);

        // peak_pnl_pct — already maintained tick-by-tick on PaperPosition.
        let peak_pnl_pct = Some(snap.max_favorable_pnl_pct);

        // atr_pct — reuses PriceHistoryTracker; None until ≥ min_samples.
        let atr_pct = self
            .price_tracker
            .compute_atr_pct(symbol)
            .map(|v| v as f32);

        // current_pnl_pct at exit (side-signed, in %). Used to derive the
        // normalized giveback. If entry_price was zero we'd have returned early
        // from the close path, but guard anyway so division is defensive.
        let current_pnl_pct = if snap.entry_price > 0.0 && snap.entry_price.is_finite() {
            let side = if snap.is_long { 1.0f64 } else { -1.0f64 };
            ((close_price - snap.entry_price) / snap.entry_price) * 100.0 * side
        } else {
            0.0
        };

        // giveback_atr_norm = (peak_pct − current_pct) / atr_pct. The divisor
        // is in "percent" too (atr_pct is already a percentage), so the ratio
        // is unitless. None when ATR is unavailable OR peak lies below current
        // (position exiting into a fresh high — giveback is undefined).
        let giveback_atr_norm = match atr_pct {
            Some(atr) if atr > 0.0 => {
                let peak_f64 = snap.max_favorable_pnl_pct as f64;
                let gb = peak_f64 - current_pnl_pct;
                if gb < 0.0 {
                    // Closing at/above peak — ok, but giveback is 0 not negative.
                    Some(0.0f32)
                } else {
                    Some((gb / atr as f64) as f32)
                }
            }
            _ => None,
        };

        // time_since_peak_ms: monotone ≥ 0. Legacy snapshots with
        // `peak_reached_ts_ms == 0` surface a large value until the first
        // favorable-tick refresh runs; `max(0)` prevents negative output.
        let time_since_peak_ms = if snap.peak_reached_ts_ms > 0 {
            Some((ts_ms_i64 - snap.peak_reached_ts_ms).max(0))
        } else {
            None
        };

        // 300 ms ROC — short-window momentum feature for Track P policy. None
        // until the price buffer has two samples spanning the window.
        let price_roc_short = self.price_tracker.compute_roc(symbol, 300);

        // entry_age_secs: guard against clock skew / restored snapshots whose
        // entry_ts_ms lies in the future of `ts_ms`.
        let entry_age_secs = if ts_ms >= snap.entry_ts_ms {
            Some(((ts_ms - snap.entry_ts_ms) as f32) / 1000.0)
        } else {
            None
        };

        // exit_source / exit_trigger_rule derivation. close_tag format from
        // call sites is "<prefix>:<reason>" where prefix ∈ {risk_close,
        // stop_trigger, strategy_close}. Map to canonical categories mirroring
        // the DUAL-TRACK-EXIT-1 taxonomy ("Physical" / "TimeStop" / "HardStop"
        // etc.). Unknown prefixes fall through verbatim so labels never lie.
        let (exit_source, exit_trigger_rule) = parse_exit_tag(close_tag);

        // realized_net_bps: gross bps on the portion closed, minus round-trip
        // taker fees (entry + exit at same rate). `qty * entry_price` is the
        // portion's entry notional — matches how pairer reasons and avoids
        // proration gymnastics with the aggregate `entry_notional` for partial
        // closes.
        let entry_notional_portion = qty * snap.entry_price;
        let realized_net_bps = if entry_notional_portion > 0.0
            && entry_notional_portion.is_finite()
        {
            let gross_bps = (realized_pnl / entry_notional_portion) * 10_000.0;
            // Entry fee was already charged at open; close fee was charged in
            // emit_close_fill. Both are taker-rate × notional. Express in bps
            // of the entry notional for internal consistency with the edge
            // conventions (cost_gate reasons in bps of entry notional).
            let close_fee_bps = (close_fee / entry_notional_portion) * 10_000.0;
            // Entry fee is aggregate on the position; prorate by qty share.
            let entry_fee_prorated =
                if snap.qty_at_snapshot > 0.0 && snap.qty_at_snapshot.is_finite() {
                    snap.entry_fee * (qty / snap.qty_at_snapshot)
                } else {
                    // Defensive fallback: synthesize from fee_rate.
                    entry_notional_portion * fee_rate
                };
            let entry_fee_bps = (entry_fee_prorated / entry_notional_portion) * 10_000.0;
            Some((gross_bps - close_fee_bps - entry_fee_bps) as f32)
        } else {
            None
        };

        crate::database::ExitFeatureRow {
            // Precedence: caller-supplied entry_context_id (authoritative, set
            // at intent-emit time) > snapshot-stored entry_context_id (captured
            // at position open, may be empty for restored/orphan-adopted
            // positions) > synthetic `ctx-<mode>-<sym>-<ts>` fallback (PK must
            // be non-null). The synthetic branch mirrors decision_features.
            // 優先序：caller 傳入 > 快照內 > 合成 fallback。
            context_id: if !caller_entry_context_id.is_empty() {
                caller_entry_context_id.to_string()
            } else if !snap.entry_context_id.is_empty() {
                snap.entry_context_id.clone()
            } else {
                on_tick_helpers::make_context_id(engine_mode, symbol, ts_ms)
            },
            ts_ms: ts_ms_i64,
            engine_mode: engine_mode.to_string(),
            strategy_name: snap.owner_strategy.clone(),
            symbol: symbol.to_string(),
            side: if snap.is_long { 1 } else { -1 },
            est_net_bps,
            peak_pnl_pct,
            atr_pct,
            giveback_atr_norm,
            time_since_peak_ms,
            price_roc_short,
            entry_age_secs,
            exit_source: Some(exit_source),
            exit_trigger_rule: Some(exit_trigger_rule),
            realized_net_bps,
            feature_schema_version:
                crate::database::exit_feature_schema::EXIT_FEATURE_SCHEMA_VERSION.to_string(),
            feature_schema_hash:
                crate::database::exit_feature_schema::exit_feature_schema_hash().to_string(),
        }
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

    /// DUST-EVICTION-GAP-1 / P1-8 FUP (2026-04-17): per-tick hook called from `on_tick`.
    /// Reads instrument_cache + symbol_registry snapshot for this symbol, delegates the
    /// actual decision to `paper_state.retriage_synthetic_owner`, then (for
    /// `NeedsEviction`) dispatches `ipc_close_symbol` with 2-minute dedup.
    /// DUST-EVICTION-GAP-1 / P1-8 FUP：on_tick 的 per-tick hook。讀 instrument_cache +
    /// symbol_registry 快照，委派給 paper_state，NeedsEviction 走 ipc_close_symbol 並 2min 去重。
    pub(crate) fn retriage_synthetic_owner_for_symbol(
        &mut self,
        symbol: &str,
        tick_price: f64,
        ts_ms: u64,
    ) {
        // Symbol-registry gate: treat None (registry not wired) as "universe unknown" —
        // we can't safely promote a position to a strategy that may not evaluate this
        // symbol, so in that case behave as "not in universe" (pushes into eviction path
        // only when notional is OK). Most production paths have the registry wired; tests
        // using `with_balance` and no registry naturally exercise this fallback.
        // symbol_registry 未接時視為「universe 未知」→ 不升級；僅在名義值足夠時考慮驅逐。
        let in_universe = match self.symbol_registry.as_ref() {
            Some(reg) => reg.is_active(symbol),
            None => false,
        };

        // Look up min_notional from instrument cache. None → caller treats as "no dust gate".
        // 從 instrument cache 取 min_notional。None → 無 dust 門檻。
        let min_notional = self
            .instrument_cache
            .as_ref()
            .and_then(|ic| ic.get(symbol).map(|spec| spec.min_notional))
            .filter(|v| *v > 0.0);

        // Target strategy for promotion — KNOWN_STRATEGY_NAMES[0] (same rule as startup
        // triage adoption). Keeps behaviour consistent between boot-time and tick-time.
        // 升級目標策略 — 與啟動 triage 同規則取 KNOWN_STRATEGY_NAMES[0]。
        let target_strategy = crate::position_reconciler::orphan_handler::KNOWN_STRATEGY_NAMES
            .first()
            .copied()
            .unwrap_or("");

        let outcome = self.paper_state.retriage_synthetic_owner(
            symbol,
            tick_price,
            in_universe,
            target_strategy,
            min_notional,
        );

        match outcome {
            crate::paper_state::RetriageOutcome::NoOp => {}
            crate::paper_state::RetriageOutcome::FrozenAsDust {
                est_notional,
                min_notional: minn,
                was_downgraded,
            } => {
                // Only log on first downgrade — subsequent ticks on the same frozen
                // symbol would spam otherwise.
                // 僅在首次降級時記錄，避免重複 tick 轟炸日誌。
                if was_downgraded {
                    warn!(
                        symbol,
                        est_notional,
                        min_notional = minn,
                        "DUST-EVICTION-GAP-1 retriage: position frozen as dust (notional \
                         below exchange minimum) / 重分流：持倉降級為 dust"
                    );
                }
            }
            crate::paper_state::RetriageOutcome::Promoted {
                from,
                to,
                est_notional,
            } => {
                info!(
                    symbol,
                    from = %from,
                    to = %to,
                    est_notional,
                    "DUST-EVICTION-GAP-1 retriage: synthetic owner promoted to real strategy \
                     / 重分流：synthetic 擁有者升級為實策略"
                );
                // Also clear any lingering dedup entry so a subsequent re-freeze + evict
                // flip isn't rate-limited by a stale timestamp.
                // 升級後清除 dedup 時間戳，避免後續 re-freeze+evict 被舊戳節流。
                self.retriage_last_evict_ms.remove(symbol);
            }
            crate::paper_state::RetriageOutcome::NeedsEviction {
                is_long,
                qty,
                est_notional,
            } => {
                // 2-minute dedup — matches ORPHAN_CLOSE_DEDUP_MS cadence in orphan_handler.
                // 2 分鐘去重，與 orphan_handler 的 ORPHAN_CLOSE_DEDUP_MS 一致。
                const RETRIAGE_EVICT_DEDUP_MS: u64 =
                    crate::position_reconciler::orphan_handler::ORPHAN_CLOSE_DEDUP_MS;
                let last = self
                    .retriage_last_evict_ms
                    .get(symbol)
                    .copied()
                    .unwrap_or(0);
                if ts_ms.saturating_sub(last) < RETRIAGE_EVICT_DEDUP_MS {
                    return;
                }
                warn!(
                    symbol,
                    is_long,
                    qty,
                    est_notional,
                    "DUST-EVICTION-GAP-1 retriage: synthetic-owner position not in universe, \
                     dispatching close / 重分流：synthetic 持倉不在 universe，派平倉"
                );
                self.retriage_last_evict_ms
                    .insert(symbol.to_string(), ts_ms);
                self.ipc_close_symbol(symbol, Some(is_long), Some(qty));
            }
        }
    }
}

mod commands;
mod on_tick;
pub(crate) mod on_tick_helpers;
#[cfg(test)]
mod tests;

/// EXIT-FEATURES-TABLE-1: classify a `close_tag` into
/// `(exit_source, exit_trigger_rule)` for the `ExitFeatureRow` label.
/// `close_tag` follows the `"<prefix>:<reason>"` convention used by every
/// close call site (prefix ∈ {risk_close, stop_trigger, strategy_close}).
/// Unknown prefixes fall through verbatim so the label never lies about
/// provenance. Split out of `build_exit_feature_row` so the taxonomy has its
/// own unit-test surface.
///
/// Mapping:
///   "risk_close:halt_session*"      → ("HaltSession",  reason)
///   "risk_close:fast_track*"        → ("FastTrack",    reason)
///   "risk_close:phys_lock_*"        → ("Physical",     reason)   // DUAL-TRACK T3
///   "risk_close:*"                  → ("Risk",         reason)
///   "stop_trigger:hard*"            → ("HardStop",     reason)
///   "stop_trigger:trailing*"        → ("TrailingStop", reason)
///   "stop_trigger:time*"            → ("TimeStop",     reason)
///   "stop_trigger:*"                → ("Stop",         reason)
///   "strategy_close:*"              → ("Strategy",     reason)
///   tag without ':'                 → (whole_tag,      "")
///
/// EXIT-FEATURES-TABLE-1：將 close_tag 解析為 (exit_source, exit_trigger_rule)；
/// "<prefix>:<reason>" 格式；未知前綴原樣回退，避免標籤撒謊。
/// DUAL-TRACK-EXIT-1 Track P T3：`phys_lock_*` prefix 歸類為 "Physical"。
pub(crate) fn parse_exit_tag(close_tag: &str) -> (String, String) {
    let (prefix, reason) = match close_tag.split_once(':') {
        Some((p, r)) => (p, r),
        None => return (close_tag.to_string(), String::new()),
    };

    let source = match prefix {
        "risk_close" => {
            if reason.starts_with("halt_session") {
                "HaltSession"
            } else if reason.starts_with("fast_track") {
                "FastTrack"
            } else if reason.starts_with("phys_lock_") {
                // DUAL-TRACK-EXIT-1 Track P T3: physical-layer micro-profit lock.
                // reason suffix preserved for gate-level drill-down
                // (phys_lock_gate1_low_edge / phys_lock_gate4_giveback /
                // phys_lock_gate4_stale_roc_neg).
                // DUAL-TRACK-EXIT-1 T3：phys_lock_* 歸類 Physical；reason 保留 gate 細節。
                "Physical"
            } else {
                "Risk"
            }
        }
        "stop_trigger" => {
            if reason.starts_with("hard") {
                "HardStop"
            } else if reason.starts_with("trailing") {
                "TrailingStop"
            } else if reason.starts_with("time") {
                "TimeStop"
            } else {
                "Stop"
            }
        }
        "strategy_close" => "Strategy",
        other => other,
    };

    (source.to_string(), reason.to_string())
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
