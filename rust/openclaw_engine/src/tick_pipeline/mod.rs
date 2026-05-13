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
    alpha_surface::AlphaSurface,
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
use tracing::info;

use crate::instrument_info::InstrumentInfoCache;
use crate::intent_processor::IntentProcessor;
use crate::orchestrator::Orchestrator;
use crate::paper_state::{PaperPosition, PaperState};
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
        // EDGE-DIAG-1-FUP-IPC: ExitConfig hot-reload fields. Each Some(_)
        //   triggers a ConfigStore::apply_patch mutation on RiskConfig.exit,
        //   preserving validate() invariants (all-or-nothing rollback). Pre
        //   this FUP there was NO IPC path — operators had to edit TOML +
        //   restart engine (no <60s rollback for Phase 3 fallback adjustments).
        // EDGE-DIAG-1-FUP-IPC：ExitConfig 熱重載欄位。每個 Some(_) 觸發
        //   RiskConfig.exit 的 ConfigStore::apply_patch，並保留 validate()
        //   不變量（全或無 rollback）。此 FUP 前 IPC 無路徑，operator 須
        //   編輯 TOML + 重啟引擎（Phase 3 fallback 調整無法 <60s 回滾）。
        exit_missing_edge_fallback_bps: Option<f64>,
        exit_min_net_floor_bps: Option<f64>,
        exit_min_hold_secs: Option<f64>,
        exit_min_peak_atr_norm: Option<f64>,
        exit_giveback_base: Option<f64>,
        exit_giveback_slope: Option<f64>,
        exit_giveback_floor: Option<f64>,
        // EDGE-P1b-FUP-STALE-PEAK-IPC (2026-04-26): EDGE-P1b T1 calibrator
        //   computes 7 dimensions but the prior IPC schema only wired 6 ×
        //   `exit_*` percentile fields above. Dim 5 (`time_since_peak_ms`)
        //   maps to `ExitConfig.stale_peak_ms` (i64 ms) and was left as
        //   TOML-only, forcing the calibrator to fall back to TOML-edit +
        //   `reload_risk_config` for any percentile-driven bind — violating
        //   PA RFC §2.2 «IPC patch path» design intent. This field closes
        //   the asymmetry. `u64` chosen to mirror existing `*_ms`
        //   companions (`boot_cooldown_ms`, `signals_heartbeat_ms`); the
        //   consumer-side dispatch casts to `i64` (validate() rejects
        //   negative) so any reasonable ms value is round-trip safe.
        // EDGE-P1b-FUP-STALE-PEAK-IPC（2026-04-26）：EDGE-P1b T1 calibrator
        //   計算 7 維度，但先前 IPC schema 僅 wire 上方 6 個 `exit_*` 百分位
        //   欄位。維度 5（`time_since_peak_ms`）對應 `ExitConfig.stale_peak_ms`
        //   （i64 ms），原為 TOML-only，導致 calibrator 任何百分位 bind 都
        //   退回 TOML edit + `reload_risk_config` 路徑，違反 PA RFC §2.2
        //   「IPC patch path」設計意圖。本欄位封閉此不對稱。型別選 `u64`
        //   對齊既有 `*_ms` 同伴（`boot_cooldown_ms`/`signals_heartbeat_ms`）；
        //   consumer 端 dispatch cast 為 `i64`（validate() 拒負值），任何
        //   合理 ms 值皆可安全 round-trip。
        exit_stale_peak_ms: Option<u64>,
        // RC-006: optional event-consumer acknowledgement. Legacy callers can
        // pass None; IPC handlers pass Some and return only after application.
        response_tx: Option<tokio::sync::oneshot::Sender<Result<String, String>>>,
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
    /// PH5-WIRE-1 RELOAD (F6, 2026-04-26): re-load on-disk edge estimates
    /// snapshot for this pipeline's mode and inject into IntentProcessor.
    /// Fire-and-forget — no `response_tx`. Reload daemon
    /// (`spawn_edge_estimates_reloader_if_enabled`) and `reload_edge_estimates`
    /// IPC method both fan out this variant; each engine reads its own
    /// mode-specific JSON. Mode isolation structurally enforced.
    /// Fail-soft on empty / corrupt — engine retains prior snapshot.
    /// PH5-WIRE-1 RELOAD（F6，2026-04-26）：重載本管線模式對應 edge estimates
    /// 快照並注入 IntentProcessor。Fire-and-forget — 無 response_tx。
    /// Mode 隔離結構性保證；空 / 損毀走 fail-soft 保留前份。
    ReloadEdgeEstimates,
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
    /// AMD-2026-05-02-01 Track E E-3: decision lease handed off by the router
    /// success path. Dispatch emits the terminal lease outcome once the
    /// authorized action is accepted by, or rejected before reaching, the
    /// exchange. `None` means router-gate flag off; `Some("bypass")` is the
    /// non-Production no-op lease.
    /// 決策租約 id；由 router 成功路徑交給 dispatch，下游在交易所接受或派發失敗
    /// 時回寫終態。None 表示 gate flag off；"bypass" 為非 Production no-op。
    pub decision_lease_id: Option<String>,
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
    /// Dispatch-time execution reference for slippage attribution. For taker
    /// orders this should be same-side BBO; fallback sources are tagged.
    /// slippage 歸因用的送單時刻參考價；taker 優先同側 BBO。
    pub reference_price: Option<f64>,
    pub reference_ts_ms: Option<u64>,
    pub reference_source: Option<String>,
    /// W-C Caveat 2 修復（2026-05-11）：emit_entry_lineage 計算的 Spine
    /// order_plan_id，由 step_4_5_dispatch 在 lineage emit 後注入；下游
    /// dispatch.rs 構造 PendingOrder 時鏡射至 `spine_order_plan_id`，再由
    /// loop_exchange.rs fully_filled 區塊讀取以呼叫
    /// emit_fill_completion_lineage。None = 該筆未過 lineage gate 或舊路徑漏注入。
    pub spine_order_plan_id: Option<String>,
    /// W-C Caveat 2 修復（2026-05-11）：emit_entry_lineage 計算的 Spine
    /// decision_id；用途同 `spine_order_plan_id`，下游 fill_completion 必填。
    pub spine_decision_id: Option<String>,
    /// W-C Caveat 2 修復（2026-05-11）：emit_entry_lineage 對應的 Spine
    /// verdict_id；當前 fill_completion 未使用，保留以供未來 partial-fill
    /// metadata + audit cross-ref。None 為預設。
    pub spine_verdict_id: Option<String>,
    /// W-C Caveat 2 修復（2026-05-11）：emit_entry_lineage 寫入的 stub
    /// ExecutionReport id；供 fill_completion 在 quality_metrics 寫
    /// stub_report_id cross-ref。
    pub spine_stub_report_id: Option<String>,
}

/// Tick context passed to strategies — borrows from on_tick scope to avoid cloning.
/// 傳遞給策略的 tick 上下文 — 從 on_tick 作用域借用以避免克隆。
/// P-08: Lifetime-parameterized to eliminate per-tick clone of indicators/signals.
#[derive(Debug, Clone)]
pub struct TickContext<'a> {
    pub symbol: &'a str,
    pub price: f64,
    pub timestamp_ms: u64,
    /// Primary indicator snapshot, currently computed from 1m klines.
    /// 主要指標快照，目前由 1m K 線計算。
    pub indicators: Option<&'a IndicatorSnapshot>,
    /// Optional 5m indicator snapshot for strategies that explicitly opt into
    /// a 5m signal family. Absence means "not warm yet"; consumers must skip
    /// rather than fall back to 1m if their configured timeframe is 5m.
    /// 顯式切到 5m 信號族的策略可使用；缺失代表尚未 warm，不能假回退到 1m。
    pub indicators_5m: Option<&'a IndicatorSnapshot>,
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
    /// G7-09c Phase 1: Best bid from latest tick (orderbook L1, mirrored from
    /// `PriceEvent.bid_price`). `None` until WS delivers the first orderbook /
    /// trade event with non-zero bid; consumer maker-price helpers fall back
    /// to `last_price ± offset_bps` when missing.
    /// G7-09c Phase 1：最新 tick 的 best bid（鏡射自 `PriceEvent.bid_price`）。
    /// WS 首次送出非零 bid 前為 None；下游 maker-price helper 缺失時回退至
    /// `last_price ± offset_bps`。
    pub best_bid: Option<f64>,
    /// G7-09c Phase 1: Best ask from latest tick (orderbook L1, mirrored from
    /// `PriceEvent.ask_price`).
    /// G7-09c Phase 1：最新 tick 的 best ask（鏡射自 `PriceEvent.ask_price`）。
    pub best_ask: Option<f64>,
    /// G7-09c Phase 1: Symbol's tick_size from `instrument_info` cache. `None`
    /// when the cache hasn't loaded the spec yet (cold-start) — consumers fall
    /// back to bps-based offsets in that case.
    /// G7-09c Phase 1：由 `instrument_info` 快取查得的 tick_size；冷啟動 cache
    /// 未載入時為 None，consumer 走 bps 後備路徑。
    pub tick_size: Option<f64>,
    /// W-AUDIT-8a Phase A：AlphaSurface 一等公民引用 — 把非-TA alpha source 從
    /// 「策略自己 buffer」升為一等對象。Phase A：Tier 1 暴露既有 indicators，
    /// Tier 2-4 全 None / 預設值（collector 留給 Phase B/C/D）。callsite 用
    /// `&openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE` 作 fallback 引用。
    pub alpha_surface_ref: &'a AlphaSurface<'a>,
    /// Sprint N+1 W7-1：read-only handle 到 paper_state.get_position(symbol)。
    /// PA #3 P1-MA-CROSSOVER §6 Option A — 解 cross-strategy position state 盲區。
    /// `None` = symbol 當前無倉位。strategy on_tick 進 entry path 前查此 handle，
    /// 已有同 symbol 倉位 → fail-closed skip entry，避免無限 reject hot loop。
    /// 借用 scope 與 ctx 同生命週期；ctx 必每 strategy iteration 內構造，避免與
    /// 同 step 後續 `paper_state.proactive_mirror_insert` / `apply_fill` 等
    /// mutable borrow 衝突（NLL per-iteration 釋放）。
    pub position_state: Option<&'a PaperPosition>,
    /// SCANNER-PINNED-GATE-1 (2026-05-11)：當前 symbol 是否在 scanner 的 pinned tier。
    /// True = pinned 25 列表內（含 BTC/ETH 永鎖 + 23 個 scanner 可 rotate 的 slot），
    /// False = scanner 動態探索的 15 slot 之一（HYPE/WLD/ZEC 等高波動長尾）。
    /// 由 step_4_5_dispatch 從 `symbol_registry.is_pinned(symbol)` 注入；
    /// 無 registry 時預設 true（test setup 不模擬 scanner）。
    /// grid_trading entry path 用此 gate 防止在不適合的高波動 symbol 上開新倉
    /// （HYPE/WLD 等 dynamic-add 對 grid 結構性虧）；exit path 不受影響。
    /// 其他策略（ma/bb_r/bb_b/funding）可繼續在 dynamic-add 上交易。
    pub is_pinned: bool,
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
    maker_kpi_store:
        Option<std::sync::Arc<crate::config::ConfigStore<crate::paper_state::MakerKpiConfig>>>,
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
    /// W-AUDIT-4b-M1 split (V082)：candidate evaluation log channel
    /// 決策特徵 evaluation log 通道；對應每次 evaluate_predictor_gate 評估
    /// （無論 outcome 是否 emit intent），供 producer-debug / gate 行為觀測。
    /// 與 decision_feature_tx 不同：後者改為 intent-only emit（success path）。
    /// None = 停用（fail-soft，不影響交易）。逐引擎接線。
    /// Spec: docs/CCAgentWorkSpace/PA/workspace/reports/
    ///       2026-05-09--full_dispatch_engineering_plan.md §2.5 B-M1
    decision_feature_evaluation_tx:
        Option<tokio::sync::mpsc::Sender<crate::database::DecisionFeatureEvaluationMsg>>,
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
    /// INFRA-PREBUILD-1 Part A (2026-04-23): `ShadowExitMsg` sender for Combine
    /// Layer exit-time shadow observations. Phase 2+ only emits when
    /// `RiskConfig.exit.shadow_enabled=true`; otherwise dormant. `None` =
    /// emission disabled (fail-soft; trading unaffected). Wired per-engine.
    /// INFRA-PREBUILD-1 A 部：`ShadowExitMsg` 發送端；Phase 2+ 僅在
    /// `shadow_enabled=true` 時發射。None = 停用（fail-soft）。逐引擎接線。
    shadow_exit_tx: Option<tokio::sync::mpsc::Sender<crate::database::ShadowExitMsg>>,
    /// W-B: Optional Agent Decision Spine runtime shadow writer. Default None
    /// keeps typed lineage emission disabled and never affects trading authority.
    /// W-B：Agent Decision Spine runtime shadow writer，可選；None 時停用且不影響交易權限。
    agent_spine_tx: Option<tokio::sync::mpsc::Sender<crate::agent_spine::store::AgentSpineMsg>>,
    agent_spine_mode: crate::agent_spine::config::AgentSpineMode,
    /// Scanner symbol registry — always-on market context and active-universe
    /// evidence. It does not grant or remove order authority.
    /// 掃描器交易對注冊表 — 常開的市場 context 與 active-universe evidence；
    /// 不授予或移除下單權限。
    symbol_registry: Option<Arc<crate::scanner::registry::SymbolRegistry>>,
    /// Scanner authority audit label retained for compatibility. Runtime scanner
    /// would-block decisions are evidence only.
    /// scanner 權限審計標籤，僅為相容保留；runtime scanner would-block 只作 evidence。
    scanner_authority_mode: crate::scanner::types::ScannerAuthorityMode,
    /// DUST-EVICTION-GAP-1 / P1-8 FUP (2026-04-17): per-symbol last `NeedsEviction`
    /// dispatch timestamp (ms since epoch). Used to rate-limit `ipc_close_symbol`
    /// retries on symbols whose retriage keeps asking for a close but the exchange
    /// has yet to settle the fill. Matches `ORPHAN_CLOSE_DEDUP_MS` cadence (2 min).
    /// DUST-EVICTION-GAP-1 / P1-8 FUP：每 symbol 最後一次重分流派 CloseSymbol 的
    /// 時間戳，用於速率限制（與 ORPHAN_CLOSE_DEDUP_MS 2 min 一致）。
    retriage_last_evict_ms: HashMap<String, u64>,
    /// G7-03 Phase B: per-symbol HysteresisDetector cache. Lazily allocated on
    /// first regime-label call for a symbol; lives for the pipeline's lifetime.
    /// Each detector owns its own rolling history of recent Hurst observations
    /// so the `lag` parameter actually applies (Phase A's stateless adapter
    /// could not enforce hysteresis). Empty when `risk.hurst.enabled = false`
    /// (the bypass path skips the entry/insert) so dormant runtime keeps the
    /// map empty and bit-identical to Phase A. Symbols never seen on this
    /// engine never appear here.
    /// G7-03 Phase B：per-symbol `HysteresisDetector` 快取，懶分配；當
    /// `risk.hurst.enabled = false` 時 bypass 路徑不會 `entry()`，map 維持空
    /// 與 Phase A bit-identical。Phase B 啟用後每 symbol 維護自己的觀察歷史，
    /// `lag` 真正生效。
    hurst_detectors: HashMap<String, crate::regime::HysteresisDetector>,
    /// DYNAMIC-RISK-1: Per-engine Sharpe-aware sizer. Adjusts
    /// `IntentProcessor::p1_risk_pct` up/down after realized PnL closes.
    /// Disabled by default; enabled via `[risk.dynamic_sizing]` TOML block.
    /// DYNAMIC-RISK-1：引擎私有的 Sharpe 調整器，平倉後上調/下調
    /// `IntentProcessor::p1_risk_pct`。預設停用，`[risk.dynamic_sizing]` 啟用。
    pub dynamic_risk_sizer: crate::dynamic_risk_sizer::DynamicRiskSizer,
    /// W-AUDIT-8a Phase B consumer wiring: late-injected slot for
    /// FundingCurveSnapshot. step_4_5_dispatch uses try_read + clone so no
    /// lock is held across strategy dispatch.
    pub(crate) funding_curve_panel_slot: Option<crate::ipc_server::FundingCurvePanelSlot>,
    /// W-AUDIT-8a Phase B consumer wiring: late-injected slot for OIDeltaPanel.
    /// Consumers fail closed when this remains None or the snapshot is stale.
    pub(crate) oi_delta_panel_slot: Option<crate::ipc_server::OIDeltaPanelSlot>,
    /// W2 sub-task 4 (E1-δ, 2026-05-11): late-injected slot for BtcLeadLagPanel
    /// IPC handle。step_4_5_dispatch 在 paper-only fence 通過後 try_read 取
    /// `Option<BtcLeadLagPanel>` 賽進 surface.btc_lead_lag。`None` = slot 未注入
    /// （test / W2 sub-task 4 deploy 前），等同於 BtcLeadLagProducer 尚未 emit
    /// → step_4_5_dispatch 寫 surface.btc_lead_lag = None（與 paper-only fence
    /// 拒絕讀取同等語意）。Layer 2 fence 由 dispatch 端 engine_mode gate 主防線。
    /// `set_btc_lead_lag_panel_slot()` setter 由 main.rs 在 BtcLeadLagProducer
    /// spawn 同時注入既有 Arc。
    pub(crate) btc_lead_lag_panel_slot: Option<crate::ipc_server::BtcLeadLagPanelSlot>,
}

// ---------------------------------------------------------------------------
// TickPipeline impl split — TICK-PIPELINE-MOD-SPLIT-1 (2026-04-22)
//   pipeline_ctor.rs    — ctor + basic setters/getters
//   pipeline_config.rs  — config sync (risk/budget/maker_kpi/news/fee/account)
//   pipeline_helpers.rs — close + exit features + channel setters + misc
// TickPipeline impl 拆分（TICK-PIPELINE-MOD-SPLIT-1，2026-04-22）
// ---------------------------------------------------------------------------
mod pipeline_config;
mod pipeline_ctor;
mod pipeline_helpers;

mod close_sizing;
mod commands;
mod on_tick;
pub(crate) mod on_tick_helpers;
#[cfg(test)]
mod tests;

/// PA-DRY-1: check whether a strategy tag belongs to the legacy close-prefix
/// family. Zero-PnL IPC / manual close fills must still be treated as close
/// rows for DB attribution, so callers OR this with `realized_pnl != 0.0`.
/// Centralised here so any future close-prefix addition flows through a single
/// edit instead of two duplicated 4-line `starts_with` chains in `commands.rs`.
///
/// PA-DRY-1：檢查 strategy tag 是否屬於 legacy close-prefix 家族。零 PnL 的
/// IPC / manual close fill 仍須被 DB 認為是 close row（與 realized_pnl != 0.0
/// 取 OR），集中於此避免兩處 4 行 starts_with 重複漂移。
pub(crate) fn is_legacy_close_tag(strategy: &str) -> bool {
    strategy.starts_with("strategy_close:")
        || strategy.starts_with("risk_close:")
        || strategy.starts_with("stop_trigger:")
        || strategy.starts_with("ipc_close:")
}

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
