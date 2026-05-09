//! REF-20 Wave 4 R20-P2b-T1 — replay execution orchestrator.
//! REF-20 Wave 4 R20-P2b-T1 — replay 執行總指揮。
//!
//! MODULE_NOTE (EN):
//!   This module wires the in-memory replay logic that runs AFTER the three
//!   Wave 3 fail-closed guards (`profile.fail_closed_assert_isolated`,
//!   `forbidden_guard::enforce_at_startup`, `mac_policy_guard::enforce`) have
//!   passed. It owns the `IsolatedPipeline` which:
//!     1. Holds the manifest fingerprint + verified manifest bytes.
//!     2. Walks `MarketEvent` fixtures supplied by `fixture_loader::load_fixtures`.
//!     3. Tracks a single in-memory `paper_balance` + `paper_position` map
//!        WITHOUT touching the live `crate::paper_state::PaperState` module
//!        (which is forbidden by V3 §6.2 #5 — DB writer channel + global
//!        mutate side).
//!     4. Calls `forbidden_guard::enforce_at_runtime(action_label)` BEFORE
//!        each simulated step so a Wave 4 wrapper can hard-abort on an
//!        injected trip-flag (V3 §12 #10 acceptance).
//!     5. Produces a typed `ReplayResult` carrying status + simulated fills
//!        + a coarse PnL summary + diagnostic counters.
//!
//!   What we do NOT touch (V3 §6.1 + PA boundary §5):
//!     - `crate::intent_processor` — owns Guardian / CostGate / Kelly / OMS;
//!       importing it would force `paper_state`, `canary_writer`,
//!       `database::*`, `bybit_rest_client` into the build graph (the
//!       symbol audit (S10) would catch this immediately).
//!     - `crate::tick_pipeline` — same reason.
//!     - `crate::ipc_server` / `crate::bybit_*` / `crate::governance_hub` —
//!       no integration whatsoever.
//!
//!   Why the isolated implementation does not "share" the live IntentProcessor
//!   despite V3 §6.1 saying replay "may share internal strategy / risk /
//!   TickPipeline / IntentProcessor modules":
//!     - V3 §6.1 grants permission, but §6.2 forbids the lower-level surfaces
//!       those modules transitively pull in. Today's IntentProcessor depends
//!       on `paper_state` (mutable global), `canary_writer` (DB writer),
//!       `database::DecisionFeatureMsg` (DB writer channel). All three are
//!       on the §6.2 forbidden list.
//!     - Per Wave 1 boundary report §5, importing IntentProcessor under
//!       `replay_isolated` feature would cause the symbol audit
//!       (R20-P2b-S10) to fail-loud on `canary_writer::write` and
//!       `bybit_*` symbols.
//!     - Wave 4 task spec carries an ambiguity flag for this exact reason
//!       ("如 既有 module 在 Live profile 已混入 lease/ipc/dispatch wiring,
//!       T1 sub-agent 不擅修, 留 ambiguity for PM"). T1 takes the minimal
//!       stub path so the binary is functional without breaking §6.2.
//!
//!   Future-Wave room:
//!     - Wave 4 R20-P2b-T2 will land the comparison route (baseline vs
//!       candidate) and may extract `IntentProcessor` strategy/cost-gate
//!       sub-modules into a `replay_compatible` feature gate, but that
//!       refactor is out of T1 scope.
//!     - Wave 5 P3a will extend `ReplayResult.pnl_summary` with calibration
//!       fields (DSR / PBO / quantile CIs).
//!
//! MODULE_NOTE (中):
//!   本模組接線 Wave 3 三層 fail-closed guard
//!   （`profile.fail_closed_assert_isolated`、
//!   `forbidden_guard::enforce_at_startup`、`mac_policy_guard::enforce`）
//!   通過後的 in-memory replay 邏輯。它擁有 `IsolatedPipeline`：
//!     1. 持有 manifest fingerprint + verified manifest bytes。
//!     2. 走訪 `fixture_loader::load_fixtures` 提供的 `MarketEvent` fixture。
//!     3. 維護單一 in-memory `paper_balance` + `paper_position` map，
//!        **不**接觸 live 的 `crate::paper_state::PaperState`（被 V3 §6.2 #5
//!        禁 — DB writer channel + 全域 mutate 側）。
//!     4. 在每個模擬步驟之前呼叫
//!        `forbidden_guard::enforce_at_runtime(action_label)`，使 Wave 4
//!        wrapper 在注入 trip-flag 時可硬性 abort（V3 §12 #10 acceptance）。
//!     5. 產出 typed `ReplayResult` 攜帶 status + 模擬 fills + 粗略 PnL
//!        summary + 診斷計數。
//!
//!   不碰之處（V3 §6.1 + PA boundary §5）：
//!     - `crate::intent_processor` — 擁有 Guardian / CostGate / Kelly / OMS；
//!       import 它會強迫 `paper_state`、`canary_writer`、`database::*`、
//!       `bybit_rest_client` 進入 build graph（symbol audit (S10) 會立即抓到）。
//!     - `crate::tick_pipeline` — 同上理由。
//!     - `crate::ipc_server` / `crate::bybit_*` / `crate::governance_hub` —
//!       完全 0 整合。
//!
//!   為何儘管 V3 §6.1 言明 replay「可共用內部 strategy / risk / TickPipeline /
//!   IntentProcessor module」我們仍不共用 live IntentProcessor：
//!     - V3 §6.1 給予許可，但 §6.2 禁 module 遞傳引入的低層 surface。今日
//!       IntentProcessor 依 `paper_state`（可變全域）、`canary_writer`（DB
//!       writer）、`database::DecisionFeatureMsg`（DB writer channel）。三者
//!       皆於 §6.2 forbidden list。
//!     - 依 Wave 1 boundary report §5，`replay_isolated` feature 下 import
//!       IntentProcessor 會使 symbol audit（R20-P2b-S10）在 `canary_writer::write`
//!       與 `bybit_*` symbol 上 fail-loud。
//!     - Wave 4 task spec 為此留 ambiguity flag（「如 既有 module 在 Live profile
//!       已混入 lease/ipc/dispatch wiring，T1 sub-agent 不擅修，留 ambiguity
//!       for PM」）。T1 採 minimal stub 路徑，使 binary 可運作而不破 §6.2。
//!
//!   未來 Wave 餘地：
//!     - Wave 4 R20-P2b-T2 落 comparison route（baseline vs candidate），
//!       可能將 `IntentProcessor` 策略 / cost-gate 子模組抽成 `replay_compatible`
//!       feature gate；但該重構非 T1 範圍。
//!     - Wave 5 P3a 延伸 `ReplayResult.pnl_summary` 含 calibration 欄位
//!       （DSR / PBO / 分位 CI）。
//!
//! SPEC: REF-20 V3 §6.1 + §6.2 + §6.4 + §12 #8/#10/#11 + workplan §4 Wave 4 R20-P2b-T1.

use serde::Serialize;
use std::collections::HashMap;

use crate::replay::context_builder::{ReplayContextBuilder, ReplayTickInputs};
use crate::replay::fixture_loader::MarketEvent;
use crate::replay::forbidden_guard::{self, ForbiddenPathError};
use crate::replay::profile::ReplayProfile;
use crate::replay::risk_adapter::{ReplayPaperSnapshot, ReplayRiskAdapter};
use crate::replay::scanner_timeline::ReplayScannerTimeline;
use crate::replay::strategy_adapter::{DecisionTraceEntry, ReplayStrategyAdapter};
use crate::strategies::StrategyAction;

// ─────────────────────────────────────────────────────────────────────────
// Public types / 公開型別
// ─────────────────────────────────────────────────────────────────────────

/// Status label written to `ReplayResult.status`.
///
/// 寫入 `ReplayResult.status` 的狀態 label。
///
/// Semantics (EN):
///   - `Completed`: walk-through finished without forbidden trip; PnL summary
///     is canonical. `replay_runner` exits 0.
///   - `AbortedForbidden(_)`: an `enforce_at_runtime` call returned `Err`.
///     The aborted action label is preserved so the report writer can
///     surface it in `replay_report.json::diagnostics::abort_reason`. Binary
///     still exits non-zero (caller `.expect()`'s the runtime guard).
///   - `AbortedFixtureExhausted`: the fixture vector was empty AT the start
///     of execution. Reserved variant — `fixture_loader::load_fixtures`
///     already errors out on empty fixtures (`FixtureEmpty`), so this is
///     defense-in-depth only.
///
/// 語意（中）：
///   - `Completed`：走訪完成且無 forbidden trip；PnL summary 為標準值。
///     `replay_runner` 以 0 結束。
///   - `AbortedForbidden(_)`：某個 `enforce_at_runtime` 呼叫回 `Err`。
///     被 abort 的 action label 被保留，使 report writer 可在
///     `replay_report.json::diagnostics::abort_reason` 揭露。Binary 仍以非 0
///     結束（caller `.expect()` runtime guard）。
///   - `AbortedFixtureExhausted`：fixture vector 在執行開始時即為空。保留
///     variant — `fixture_loader::load_fixtures` 已對空 fixture 報錯
///     （`FixtureEmpty`），故此屬縱深防禦。
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum ReplayStatus {
    Completed,
    AbortedForbidden { action: String },
    AbortedFixtureExhausted,
}

impl ReplayStatus {
    /// Short kv-safe label for `replay_report.json::status`.
    /// `replay_report.json::status` 用的短 kv-safe label。
    pub fn label(&self) -> &'static str {
        match self {
            Self::Completed => "completed",
            Self::AbortedForbidden { .. } => "aborted_forbidden",
            Self::AbortedFixtureExhausted => "aborted_fixture_exhausted",
        }
    }
}

/// Single simulated fill emitted by the in-memory pipeline.
/// in-memory pipeline 發出的單一模擬 fill。
///
/// Sprint A/B fields: `ts_ms` / `symbol` / `side` (long|short string) / `qty` /
/// `price` (event close pre-R6-T2; slippage-adjusted post-R6-T2) /
/// `evidence_source_tier` (fixture tier 'calibrated_replay'|'synthetic_replay').
///
/// Sprint C R6-T1+T2 fields:
///   - `fee` = qty × price × fee_rate. 0 on ghost rows (qty=0 reject) and on
///     the synthetic-walker fallback (`'synthetic_replay'` tier — fee/slippage
///     not credible without intent context).
///   - `fee_rate` (decimal) — PostOnly→maker / else taker. Source:
///     `account_manager` if seeded, else `DEFAULT_*_FEE_RATE` constants.
///   - `slippage_bps` — signed bps on reference price. PostOnly→0; else
///     turnover-tier via `SlippageConfig::lookup_rate`. Buy→+bps / Sell→-bps.
///   - `liquidity_role` — V050 CHECK enum ∈ {'maker','taker','unknown'}.
///     PostOnly→'maker' / explicit non-PostOnly TIF or `Close`→'taker' /
///     synthetic walker (no intent)→'unknown'.
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct SimulatedFill {
    pub ts_ms: i64,
    pub symbol: String,
    pub side: String,
    pub qty: f64,
    /// Requested quantity before replay execution realism clamps.
    /// replay 執行真實度 clamp 前的原始請求數量。
    pub requested_qty: f64,
    /// Filled / requested ratio. 1.0 = full fill; 0.0 = miss/reject.
    /// 成交 / 請求比例。1.0 = 全成；0.0 = 未成/拒絕。
    pub fill_ratio: f64,
    /// Fill status: filled / partial / rejected / maker_miss / synthetic.
    /// 成交狀態：filled / partial / rejected / maker_miss / synthetic。
    pub fill_status: String,
    pub price: f64,
    pub evidence_source_tier: String,
    /// Sprint C R6-T1 — per-fill fee in quote-asset units (qty × price × fee_rate).
    /// Sprint C R6-T1 — 每筆 fill 的手續費（quote 資產單位 = qty × price × fee_rate）。
    pub fee: f64,
    /// Sprint C R6-T1 — per-fill fee rate (decimal; maker if PostOnly, else taker).
    /// Sprint C R6-T1 — 每筆 fill 的費率（小數；PostOnly→maker，否則 taker）。
    pub fee_rate: f64,
    /// Sprint C R6-T2 — signed slippage bps (positive=buy, negative=sell, 0=PostOnly).
    /// Sprint C R6-T2 — 有號滑點 bps（買=正、賣=負、PostOnly=0）。
    pub slippage_bps: f64,
    /// Sprint C R6-T1 — liquidity role ∈ {'maker', 'taker', 'unknown'} (V050 CHECK).
    /// Sprint C R6-T1 — 流動性角色 ∈ {'maker', 'taker', 'unknown'}（V050 CHECK）。
    pub liquidity_role: String,
    /// REF-21 S1 calibration: partial-fill model status for this fill.
    /// REF-21 S1 校準：本 fill 的 partial-fill 模型狀態。
    pub partial_fill_model_status: String,
    /// REF-21 S1 calibration: usable depth quantity at the replay timestamp.
    /// REF-21 S1 校準：replay 時刻可用的深度數量。
    pub depth_available_qty: Option<f64>,
    /// REF-21 S1 calibration: modeled execution latency in milliseconds.
    /// REF-21 S1 校準：建模執行延遲（毫秒）。
    pub latency_ms: Option<u64>,
    /// REF-21 S1 calibration: ts_ms + latency_ms when latency exists.
    /// REF-21 S1 校準：存在 latency 時為 ts_ms + latency_ms。
    pub effective_ts_ms: Option<i64>,
}

/// Coarse PnL summary written to `replay_report.json::pnl_summary`.
///
/// 寫入 `replay_report.json::pnl_summary` 的粗略 PnL 摘要。
///
/// Wave 4 T1 scope: only the inputs that are computable without calibration.
/// Wave 5 P3a will extend with `realized_edge_bps_after_cost_p10/50/90`
/// + bootstrap CI fields.
///
/// Wave 4 T1 範圍：僅算 calibration 前可得的輸入。Wave 5 P3a 將延伸
/// `realized_edge_bps_after_cost_p10/50/90` + bootstrap CI 欄位。
#[derive(Debug, Clone, Serialize)]
pub struct PnlSummary {
    pub events_processed: usize,
    pub fills_emitted: usize,
    pub starting_balance: f64,
    pub ending_balance: f64,
    pub net_pnl: f64,
}

/// Diagnostic counters written to `replay_report.json::diagnostics`.
///
/// 寫入 `replay_report.json::diagnostics` 的診斷計數。
#[derive(Debug, Clone, Serialize)]
pub struct ReplayDiagnostics {
    pub guard_enforce_runtime_calls: u64,
    pub last_action_label: String,
    pub abort_reason: Option<String>,
    pub scanner_timeline_enabled: bool,
    pub scanner_timeline_cycles: usize,
    pub scanner_timeline_skipped_events: u64,
}

/// Full replay execution result.
///
/// 完整 replay 執行結果。
///
/// Field semantics (EN):
///   - `manifest_id`: from manifest body (echoed for trace correlation).
///   - `status`: see `ReplayStatus` above.
///   - `execution_confidence`: V3 §12 #11 invariant; ALWAYS `"none"` for
///     the Isolated profile (S2/S3 smoke replay is non-actionable).
///   - `fills`: ordered vector of simulated fills.
///   - `pnl_summary`: coarse balance arithmetic.
///   - `diagnostics`: counters + last action label + optional abort reason.
///   - `decision_traces`: Sprint B2 R5-T3 NEW — populated only when an
///     `ReplayStrategyAdapter` was wired in (R5-T4 CLI path); empty `Vec`
///     in the synthetic-walker path that proof_1/4/5 e2e currently exercise.
///     Carries the strategy-side `DecisionTraceEntry` (one entry per tick
///     that emitted ≥1 action) for plan §6.R5 acceptance A4 parameter-delta
///     proof.
///
/// 欄位語意（中）：
///   - `manifest_id`: 來自 manifest body（回聲供 trace 關聯）。
///   - `status`：見上方 `ReplayStatus`。
///   - `execution_confidence`：V3 §12 #11 不變量；Isolated profile 永遠
///     為 `"none"`（S2/S3 smoke replay non-actionable）。
///   - `fills`：模擬 fill 的有序 vector。
///   - `pnl_summary`：粗略餘額算術。
///   - `diagnostics`：計數 + 最後 action label + 可選 abort 原因。
///   - `decision_traces`: Sprint B2 R5-T3 新增 — 僅在接入
///     `ReplayStrategyAdapter`（R5-T4 CLI 路徑）時填值；synthetic-walker
///     路徑（proof_1/4/5 e2e 走的路徑）為空 `Vec`。攜帶策略端
///     `DecisionTraceEntry`（每個發出 ≥1 action 的 tick 一筆），供 plan
///     §6.R5 acceptance A4 parameter-delta proof 使用。
#[derive(Debug, Clone, Serialize)]
pub struct ReplayResult {
    pub manifest_id: String,
    pub status: ReplayStatus,
    pub execution_confidence: String,
    pub fills: Vec<SimulatedFill>,
    pub pnl_summary: PnlSummary,
    pub diagnostics: ReplayDiagnostics,
    /// Sprint B2 R5-T3: per-tick decision trace (empty in synthetic-walker path).
    /// Sprint B2 R5-T3：逐 tick 決策追蹤（synthetic-walker 路徑下為空）。
    #[serde(default)]
    pub decision_traces: Vec<DecisionTraceEntry>,
}

/// Runner-level error type.
///
/// Runner 層的錯誤型別。
///
/// Note (EN): unlike `FixtureError`, this enum is the orchestrator-level
/// failure surface (e.g. invariant violation about Profile, or guard runtime
/// trip during pipeline execution). Build-time / load-time failures stay in
/// their respective sibling crate modules so attribution stays sharp.
///
/// 註（中）：與 `FixtureError` 不同，本 enum 是 orchestrator 層的失敗 surface
/// （例如 Profile 不變量違反，或 pipeline 執行期間 guard runtime trip）。
/// build-time / load-time 失敗仍歸屬各 sibling crate module，使歸因清晰。
#[derive(Debug)]
pub enum ReplayError {
    /// `IsolatedPipeline::new` was called with non-Isolated profile (Wave 3
    /// `fail_closed_assert_isolated` should have caught this upstream; this
    /// is defense-in-depth on the orchestrator side).
    /// `IsolatedPipeline::new` 用 non-Isolated profile 呼叫（Wave 3
    /// `fail_closed_assert_isolated` 在上游應已捕獲；此為 orchestrator 側
    /// 的縱深防禦）。
    NonIsolatedProfile { found: ReplayProfile },
    /// Sprint B2 R5-T3 fail-loud snapshot construction (E2 §7 #2 + F-3
    /// LOW finding fix): the runner refuses to wire a strategy/risk adapter
    /// pipeline if the initial paper snapshot carries a NaN/Inf balance or
    /// an empty `latest_price` map (router.rs/paper_state would silently
    /// bypass Gate 1.6 + Gate 2.6 in those edge cases).
    ///
    /// Sprint B2 R5-T3 fail-loud snapshot 構造（E2 §7 #2 + F-3 LOW finding
    /// fix）：runner 拒絕在初始 paper snapshot 含 NaN/Inf balance 或
    /// `latest_price` 空 map 的情況下接 strategy/risk adapter pipeline
    /// （router.rs/paper_state 在此 edge case 會 silent bypass Gate 1.6 + Gate
    /// 2.6）。
    InvalidSnapshot { reason: String },
}

impl std::fmt::Display for ReplayError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::NonIsolatedProfile { found } => write!(
                f,
                "ReplayError::NonIsolatedProfile{{found={:?}}} — orchestrator \
                 refuses non-Isolated profile (V3 §6.1)",
                found
            ),
            Self::InvalidSnapshot { reason } => write!(
                f,
                "ReplayError::InvalidSnapshot{{reason={reason}}} — orchestrator \
                 refuses to attach adapter pipeline on a NaN/empty snapshot \
                 (Sprint B2 R5-T3 F-3 fix)"
            ),
        }
    }
}

impl std::error::Error for ReplayError {}

// ─────────────────────────────────────────────────────────────────────────
// IsolatedPipeline — single replay execution / 單一 replay 執行
// ─────────────────────────────────────────────────────────────────────────

/// Default starting balance for the in-memory paper account when manifest
/// does not override.
///
/// manifest 未覆寫時 in-memory paper 帳戶的預設起始餘額。
///
/// Justification (EN): the binary is non-actionable
/// (`execution_confidence='none'`); the absolute value carries no business
/// meaning, only relative deltas matter. We pick 10_000 USDT to match the
/// existing demo paper bootstrap (see `paper_state.rs` for context — but we
/// do NOT import that module).
///
/// 理由（中）：binary 為 non-actionable（`execution_confidence='none'`）；
/// 絕對值無業務意義，僅相對差值重要。挑 10_000 USDT 以對齊既有 demo paper
/// bootstrap（context 見 `paper_state.rs` — 但我們**不** import 該模組）。
pub const DEFAULT_STARTING_BALANCE: f64 = 10_000.0;

/// In-memory replay execution unit. Owns a deterministic pipeline state and
/// produces a `ReplayResult`.
///
/// in-memory replay 執行單位。擁有確定性的 pipeline state 並產出 `ReplayResult`。
///
/// Lifecycle (synthetic-walker path — proof_1/4/5 e2e):
///   1. `build_isolated_pipeline(profile, manifest_id, tier, fixtures)` —
///      validates profile + initialises balance + position map. NO adapters.
///   2. `execute()` — fallback synthetic walker preserved for backward compat:
///      first sighting of each symbol emits 1 `SimulatedFill`, subsequent
///      events apply mark-to-market arithmetic on the per-symbol entry price.
///   3. `into_result()` — finalises the `ReplayResult` (consumes self).
///
/// Lifecycle (Sprint B2 R5-T3 adapter path — R5-T4 CLI wires this):
///   1. `build_isolated_pipeline(...)` (same as above) — produces baseline.
///   2. `with_adapter_pipeline(strategy_adapter, risk_adapter, snapshot)` —
///      attaches the wrapped strategy + risk adapter + initial paper
///      snapshot. Snapshot is fail-loud validated (NaN/Inf balance and
///      empty `latest_price` rejected — F-3 LOW finding fix).
///   3. `execute()` — when adapters are wired, runs the real strategy + risk
///      pipeline: build `TickContext` per event → `strategy.on_tick(ctx)` →
///      per `StrategyAction`, evaluate via `risk_adapter.evaluate(...)` →
///      record `Accepted` as `SimulatedFill` (qty>0) or `Rejected` as
///      ghost row (qty=0, per PA §6.1) → mutate snapshot via
///      `apply_fill_open` / `apply_fill_close`.
///   4. `into_result()` — finalises with `decision_traces` populated.
///
/// 生命週期（synthetic-walker 路徑 — proof_1/4/5 e2e）：
///   1. `build_isolated_pipeline(profile, manifest_id, tier, fixtures)` —
///      驗 profile + 初始化 balance + position map。**不**接 adapter。
///   2. `execute()` — 保留向後兼容的 fallback synthetic walker：每個 symbol
///      首見發 1 `SimulatedFill`，後續以 entry price 做 mark-to-market 算術。
///   3. `into_result()` — finalise `ReplayResult`（消費 self）。
///
/// 生命週期（Sprint B2 R5-T3 adapter 路徑 — R5-T4 CLI 接此）：
///   1. `build_isolated_pipeline(...)`（同上）— 產出 baseline。
///   2. `with_adapter_pipeline(strategy_adapter, risk_adapter, snapshot)` —
///      接入 wrapped strategy + risk adapter + 初始 paper snapshot。
///      Snapshot 經 fail-loud 驗證（拒絕 NaN/Inf balance 與空 `latest_price`
///      — F-3 LOW finding fix）。
///   3. `execute()` — adapter 接入時跑真實 strategy + risk pipeline：每 event
///      建 `TickContext` → `strategy.on_tick(ctx)` → 每 `StrategyAction` 經
///      `risk_adapter.evaluate(...)` → `Accepted` 記為 `SimulatedFill`
///      (qty>0)，`Rejected` 記為 ghost row（qty=0，per PA §6.1）→ 透過
///      `apply_fill_open` / `apply_fill_close` mutate snapshot。
///   4. `into_result()` — finalise 時填入 `decision_traces`。
pub struct IsolatedPipeline {
    profile: ReplayProfile,
    manifest_id: String,
    fixtures: Vec<MarketEvent>,
    fixture_tier_label: String,
    pub(super) starting_balance: f64,
    pub(super) balance: f64,
    /// Map of symbol -> last simulated entry price (used to compute
    /// final-mark PnL). One position per symbol; T1 does not net out.
    /// **Synthetic-walker path only** — adapter path tracks positions inside
    /// `paper_snapshot`.
    /// symbol -> 最近模擬入場價（用於算 final-mark PnL）。每 symbol 一倉；
    /// T1 不 netting。**僅 synthetic-walker 路徑使用** — adapter 路徑透過
    /// `paper_snapshot` 追蹤倉位。
    positions: HashMap<String, f64>,
    /// Accumulated fills (deterministic order; see `execute`).
    /// 累積 fill（確定性順序；見 `execute`）。
    pub(super) fills: Vec<SimulatedFill>,
    /// Counter for `enforce_at_runtime` calls — surfaces in
    /// `ReplayDiagnostics.guard_enforce_runtime_calls`.
    /// `enforce_at_runtime` 呼叫計數 — 顯示於
    /// `ReplayDiagnostics.guard_enforce_runtime_calls`。
    guard_calls: u64,
    /// Last action label passed to `enforce_at_runtime`. Surfaces in
    /// `ReplayDiagnostics.last_action_label`.
    /// 最近一次傳給 `enforce_at_runtime` 的 action label。顯示於
    /// `ReplayDiagnostics.last_action_label`。
    pub(super) last_action: String,
    /// Final status — set by `execute` then consumed by `into_result`.
    /// 最終狀態 — 由 `execute` 設定並由 `into_result` 消費。
    status: ReplayStatus,
    /// Sprint B2 R5-T3: optional wrapped `Strategy` impl. `None` =
    /// synthetic-walker fallback (proof_1/4/5 e2e). `Some(_)` is owned `mut`
    /// per E2 §7 #1 (Strategy::on_tick takes `&mut self`); not `Arc<Mutex<>>`.
    /// Sprint B2 R5-T3：選用包裝的 `Strategy` 實作。`None` = synthetic-walker
    /// fallback（proof_1/4/5 e2e）。`Some(_)` 為 owned `mut`（per E2 §7 #1，
    /// Strategy::on_tick 取 `&mut self`），**非** `Arc<Mutex<>>`。
    strategy_adapter: Option<ReplayStrategyAdapter>,
    /// Sprint B2 R5-T3: optional 6-Gate risk adapter; `evaluate` is pure
    /// (`&self`/`&snapshot`) so a single adapter can sit alongside a
    /// mutable `paper_snapshot`. `None` ⇔ `strategy_adapter == None`
    /// (paired-or-neither invariant enforced by `with_adapter_pipeline`).
    /// Sprint B2 R5-T3：選用 6-Gate 風控 adapter；`evaluate` 為純函式
    /// （`&self`/`&snapshot`），故單一 adapter 可與可變 `paper_snapshot`
    /// 並列。`None` ⇔ `strategy_adapter == None`（成對或皆無，由
    /// `with_adapter_pipeline` 強制）。
    pub(super) risk_adapter: Option<ReplayRiskAdapter>,
    /// Sprint B2 R5-T3: paper snapshot mutated by `apply_fill_open` /
    /// `apply_fill_close`. `None` in synthetic-walker path.
    /// Sprint B2 R5-T3：由 `apply_fill_open` / `apply_fill_close` mutate 的
    /// paper snapshot。synthetic-walker 路徑下為 `None`。
    pub(super) paper_snapshot: Option<ReplayPaperSnapshot>,
    /// Sprint C R6-T1: optional `AccountManager` for per-symbol maker/taker.
    /// `None` ⇒ `DEFAULT_*_FEE_RATE` (live cold-boot path).
    /// Sprint C R6-T1：可選 `AccountManager` 提供 per-symbol maker/taker；
    /// `None` ⇒ `DEFAULT_*_FEE_RATE`（live 冷啟動路徑）。
    pub(super) account_manager: Option<std::sync::Arc<crate::account_manager::AccountManager>>,
    /// Sprint C R6-T2: slippage tier snapshot (default = pre-G7-07 SLIPPAGE_TIERS).
    /// Sprint C R6-T2：滑點分級表（預設 = pre-G7-07 SLIPPAGE_TIERS）。
    pub(super) slippage_config: crate::config::SlippageConfig,
    /// Sprint C R6-T2: 24h USD turnover for tier lookup; `None` → 5 bps default.
    /// Sprint C R6-T2：tier 查找用 24h USD 成交量；`None` → 5 bps 預設。
    pub(super) volume_24h: Option<f64>,
    /// REF-21 calibration: replay-only conservative cap for PostOnly maker
    /// execution probability. `None` preserves legacy "fills if risk accepts"
    /// semantics; `Some(p)` deterministically converts a fraction of maker
    /// attempts into qty=0 maker-miss ghost rows.
    pub(super) maker_fill_probability_cap: Option<f64>,
    pub(super) maker_attempt_counter: u64,
    /// REF-21 S1 calibration: replay-only modeled latency attached to emitted
    /// fill evidence. This does not import live order state; it is parsed from
    /// the signed manifest execution_calibration block.
    pub(super) execution_latency_ms: Option<u64>,
    /// REF-21: optional replay-safe scanner timeline. When present, adapter
    /// path only feeds a strategy tick for symbols active at the historical
    /// scanner cycle, while still feeding ticks for already-open positions so
    /// exits remain observable.
    pub(super) scanner_timeline: Option<ReplayScannerTimeline>,
    pub(super) scanner_timeline_skipped_events: u64,
}

/// Public constructor for `IsolatedPipeline` that funnels callers through the
/// orchestrator-level invariant: only `ReplayProfile::Isolated` is acceptable.
/// This is the single seam the binary entry uses — `replay_runner::main`
/// passes the profile that was already vetted by S7 / S8 / S9 guards.
///
/// `IsolatedPipeline` 的公開構造，把 caller 引導通過 orchestrator 層不變量：
/// 僅 `ReplayProfile::Isolated` 可受。此為 binary entry 唯一接縫 —
/// `replay_runner::main` 傳入已被 S7/S8/S9 guard 通過的 profile。
pub fn build_isolated_pipeline(
    profile: ReplayProfile,
    manifest_id: String,
    fixture_tier_label: &str,
    fixtures: Vec<MarketEvent>,
) -> Result<IsolatedPipeline, ReplayError> {
    if !matches!(profile, ReplayProfile::Isolated) {
        return Err(ReplayError::NonIsolatedProfile { found: profile });
    }
    Ok(IsolatedPipeline {
        profile,
        manifest_id,
        fixtures,
        fixture_tier_label: tier_label_to_evidence_source(fixture_tier_label),
        starting_balance: DEFAULT_STARTING_BALANCE,
        balance: DEFAULT_STARTING_BALANCE,
        positions: HashMap::new(),
        fills: Vec::new(),
        guard_calls: 0,
        last_action: "init".to_string(),
        status: ReplayStatus::Completed, // overwritten on abort
        // Sprint B2 R5-T3: adapter path opt-in via `with_adapter_pipeline`.
        // Sprint B2 R5-T3：adapter 路徑經 `with_adapter_pipeline` opt-in。
        strategy_adapter: None,
        risk_adapter: None,
        paper_snapshot: None,
        // Sprint C R6-T1+T2: fee/slippage context opt-in via
        // `with_replay_fee_context`. Defaults preserve walker 'unknown'/0
        // path (proof_1/4/5 byte-equal).
        // Sprint C R6-T1+T2：fee/slippage context 經 `with_replay_fee_context`
        // opt-in；預設保留 walker 'unknown'/0 路徑（proof_1/4/5 byte-equal）。
        account_manager: None,
        slippage_config: crate::config::SlippageConfig::default(),
        volume_24h: None,
        maker_fill_probability_cap: None,
        maker_attempt_counter: 0,
        execution_latency_ms: None,
        scanner_timeline: None,
        scanner_timeline_skipped_events: 0,
    })
}

/// Map fixture tier label ("S2" / "S3") to V3 §4.1 `evidence_source_tier`
/// enum literal. S2 -> calibrated_replay (operator-curated public data),
/// S3 -> synthetic_replay. Unknown tiers fall back to "synthetic_replay"
/// because the safer-claim choice is the lower-confidence label.
///
/// 將 fixture tier label（"S2" / "S3"）映射到 V3 §4.1 `evidence_source_tier`
/// enum 字面量。S2 -> calibrated_replay（operator 策展公開資料），
/// S3 -> synthetic_replay。未知 tier fallback 至 "synthetic_replay"，因較
/// 安全的主張是較低 confidence label。
fn tier_label_to_evidence_source(tier_label: &str) -> String {
    match tier_label {
        "S2" => "calibrated_replay".to_string(),
        "S3" => "synthetic_replay".to_string(),
        _ => "synthetic_replay".to_string(),
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Sprint C R6 W2 R0-T0 — fee/slippage helpers + apply_fill methods extracted.
// Sprint C R6 W2 R0-T0 — 費率/滑點輔助 + apply_fill 方法已抽出。
// ─────────────────────────────────────────────────────────────────────────
// Carved into `crate::replay::apply_fill` in R6 W2, then the module-internal
// tests moved to sibling `runner_tests.rs` in W-AUDIT-5 F-12 so this file stays
// under the §九 2000 LOC cap.
// Helpers (`replay_fee_rate_for_tif`, `replay_slippage_bps_for_tif`,
// `apply_slippage_to_price`, `DEFAULT_*_FEE_RATE`) and the 4 inherent
// methods (`process_open_intent`, `process_close_intent`, `apply_fill_open`,
// `apply_fill_close`) live in `apply_fill.rs`. Same-crate `impl` block
// preserves field visibility; same-crate `pub(crate)` visibility lets the
// `tests` submodule below import them via `super::*` byte-equal.
//
// R6 W2 先抽至 `crate::replay::apply_fill`，W-AUDIT-5 F-12 再把模組內
// test 移到 sibling `runner_tests.rs`，使本檔維持在 §九 2000 LOC cap 內。
// 輔助與 4 個 inherent method 住 `apply_fill.rs`；同 crate `impl` block
// 保留欄位可見度，同 crate `pub(crate)` 可見度讓 child test module 透過
// `super::*` 位元級不變地引用。

impl IsolatedPipeline {
    /// Read-only profile getter (used by tests + future T2 wiring).
    /// 唯讀 profile getter（供 test 與未來 T2 接線使用）。
    pub fn profile(&self) -> ReplayProfile {
        self.profile
    }

    /// Read-only manifest_id getter.
    /// 唯讀 manifest_id getter。
    pub fn manifest_id(&self) -> &str {
        &self.manifest_id
    }

    /// Set the replay balance anchor before execution. The CLI wires this from
    /// ``manifest.starting_balance`` so both synthetic smoke fixtures and the
    /// real adapter path report PnL against the manifest-selected account size.
    pub fn with_starting_balance(mut self, starting_balance: f64) -> Result<Self, ReplayError> {
        if !starting_balance.is_finite() || starting_balance <= 0.0 {
            return Err(ReplayError::InvalidSnapshot {
                reason: format!(
                    "starting_balance must be finite and > 0, got {}",
                    starting_balance
                ),
            });
        }
        self.starting_balance = starting_balance;
        self.balance = starting_balance;
        Ok(self)
    }

    /// Sprint B2 R5-T3 — wire in a strategy adapter + risk adapter + initial
    /// paper snapshot. After this call `execute()` runs the real strategy
    /// pipeline (Strategy::on_tick → Risk evaluate → apply_fill) instead of
    /// the synthetic walker fallback.
    ///
    /// Sprint B2 R5-T3 — 接入 strategy adapter + risk adapter + 初始 paper
    /// snapshot。呼叫後 `execute()` 跑真實策略管線（Strategy::on_tick →
    /// Risk evaluate → apply_fill）取代 synthetic walker fallback。
    ///
    /// Fail-loud snapshot validation (E2 §7 #2 + F-3 LOW finding fix):
    ///   - `balance.is_nan() || balance.is_infinite()` → `InvalidSnapshot`.
    ///   - `latest_price.is_none()` AND `positions.is_empty()` → `InvalidSnapshot`
    ///     (caller MUST seed at least one of: a starting price hint or an
    ///     existing inventory; otherwise Gate 2.6 P1 cap silent-bypasses).
    ///
    /// Fail-loud snapshot 驗證（E2 §7 #2 + F-3 LOW finding fix）：
    ///   - `balance.is_nan() || balance.is_infinite()` → `InvalidSnapshot`。
    ///   - `latest_price.is_none()` 且 `positions.is_empty()` →
    ///     `InvalidSnapshot`（caller 必傳起始價提示或既有倉位之一；否則
    ///     Gate 2.6 P1 cap 會 silent-bypass）。
    ///
    /// SAFETY / 不變量：strategy_adapter 與 risk_adapter 必同 wave/profile
    /// 構造（皆 `ReplayProfile::Isolated`）；此 setter 不重驗 profile
    /// (兩 adapter 各自於 `new()` 時已驗，此處不重複攻擊面)。
    /// SAFETY: strategy_adapter and risk_adapter MUST come from the same
    /// wave/profile (both built with `ReplayProfile::Isolated`). Setter does
    /// not re-validate profile (each adapter's `new()` already did, repeating
    /// here only widens attack surface).
    pub fn with_adapter_pipeline(
        mut self,
        strategy_adapter: ReplayStrategyAdapter,
        risk_adapter: ReplayRiskAdapter,
        snapshot: ReplayPaperSnapshot,
    ) -> Result<Self, ReplayError> {
        // F-3 fix: NaN/Inf balance fails loud (router.rs/paper_state would
        // silently let Gate 1.6 pass since `NaN <= 0.0` is false).
        // F-3 fix：NaN/Inf balance fail loud（router.rs/paper_state 會 silent
        // 放過 Gate 1.6，因 `NaN <= 0.0` 為 false）。
        if !snapshot.balance.is_finite() {
            return Err(ReplayError::InvalidSnapshot {
                reason: format!(
                    "balance must be finite f64, got {} (NaN/Inf rejected)",
                    snapshot.balance
                ),
            });
        }
        // F-3 fix part 2: empty `latest_price` + no inventory → Gate 2.6
        // (P1 cap = balance * p1_risk_pct / price) silent-bypasses by falling
        // back to `kelly_qty`. Caller MUST seed one anchor.
        // F-3 fix part 2：空 `latest_price` + 無庫存 → Gate 2.6（P1 cap =
        // balance * p1_risk_pct / price）會 silent-bypass（fallback 至
        // `kelly_qty`）。Caller 必種一個錨。
        if snapshot.latest_price.is_none() && snapshot.positions.is_empty() {
            return Err(ReplayError::InvalidSnapshot {
                reason: "latest_price is None and positions is empty — caller \
                         must seed at least one (otherwise Gate 2.6 P1 cap \
                         silent-bypasses)"
                    .to_string(),
            });
        }
        // Mirror snapshot.balance into pipeline.balance so `into_result`
        // pnl_summary uses the adapter-path arithmetic. Pre-existing
        // synthetic-walker `balance` retains the same starting value
        // (DEFAULT_STARTING_BALANCE) when no snapshot is supplied.
        // 把 snapshot.balance 鏡射至 pipeline.balance，使 `into_result`
        // pnl_summary 採 adapter-path 算術。未提供 snapshot 時 synthetic-walker
        // 的 `balance` 維持原值（DEFAULT_STARTING_BALANCE）。
        self.starting_balance = snapshot.balance;
        self.balance = snapshot.balance;
        self.strategy_adapter = Some(strategy_adapter);
        self.risk_adapter = Some(risk_adapter);
        self.paper_snapshot = Some(snapshot);
        Ok(self)
    }

    /// Sprint C R6-T1+T2 — wire optional fee/slippage context. All three
    /// params opt-in:
    ///   - `account_manager`: per-symbol maker/taker; else `DEFAULT_*_FEE_RATE`.
    ///   - `slippage_config`: `None` keeps `SlippageConfig::default()` (= pre-G7-07
    ///     SLIPPAGE_TIERS) seeded by `build_isolated_pipeline`.
    ///   - `volume_24h`: 24h USD turnover for tier lookup (`None` → 0.0 → 5 bps).
    ///
    /// Sprint C R6-T1+T2 — 接入可選 fee/slippage context。三個參數皆 opt-in：
    /// `account_manager` 否則退 `DEFAULT_*_FEE_RATE` / `slippage_config` `None`
    /// 沿用 `SlippageConfig::default()` / `volume_24h` `None` → 5 bps fallback。
    ///
    /// SAFETY / 不變量：本 builder 不打 endpoint；`account_manager` 必為 caller
    /// 預先 `seed_default_fee_rates` 過的 instance（dispatch §1）。
    /// SAFETY: builder does NOT call any endpoint; `account_manager` MUST be
    /// caller-pre-seeded via `seed_default_fee_rates` (dispatch §1).
    pub fn with_replay_fee_context(
        mut self,
        account_manager: Option<std::sync::Arc<crate::account_manager::AccountManager>>,
        slippage_config: Option<crate::config::SlippageConfig>,
        volume_24h: Option<f64>,
    ) -> Self {
        self.account_manager = account_manager;
        if let Some(cfg) = slippage_config {
            self.slippage_config = cfg;
        }
        self.volume_24h = volume_24h;
        self
    }

    /// REF-21 calibration — attach replay-only execution calibration knobs.
    /// The dedicated subprocess receives this only through the signed
    /// manifest; it never reads or mutates live execution state.
    pub fn with_execution_calibration(
        mut self,
        maker_fill_probability_cap: Option<f64>,
        execution_latency_ms: Option<u64>,
    ) -> Self {
        self.maker_fill_probability_cap = maker_fill_probability_cap
            .filter(|value| value.is_finite())
            .map(|value| value.clamp(0.0, 1.0));
        self.execution_latency_ms = execution_latency_ms.filter(|value| *value <= 60_000);
        self
    }

    pub(super) fn should_accept_maker_execution(&mut self, symbol: &str, ts_ms: i64) -> bool {
        let Some(cap) = self.maker_fill_probability_cap else {
            return true;
        };
        if cap >= 1.0 {
            self.maker_attempt_counter = self.maker_attempt_counter.saturating_add(1);
            return true;
        }
        if cap <= 0.0 {
            self.maker_attempt_counter = self.maker_attempt_counter.saturating_add(1);
            return false;
        }
        self.maker_attempt_counter = self.maker_attempt_counter.saturating_add(1);
        let bucket = deterministic_maker_bucket(
            &self.manifest_id,
            symbol,
            ts_ms,
            self.maker_attempt_counter,
        );
        bucket < (cap * 10_000.0).round() as u64
    }

    fn set_replay_event_turnover_24h(&mut self, turnover_24h: Option<f64>) {
        self.volume_24h = turnover_24h.filter(|v| v.is_finite() && *v > 0.0);
    }

    /// REF-21 full-chain replay: attach a precomputed, replay-safe scanner
    /// timeline. The timeline is built inside the dedicated replay subprocess
    /// from fixture data only; it does not share live scanner state.
    pub fn with_scanner_timeline(mut self, timeline: ReplayScannerTimeline) -> Self {
        self.scanner_timeline = Some(timeline);
        self
    }

    /// Drive the in-memory pipeline.
    ///
    /// 驅動 in-memory pipeline。
    ///
    /// Per V3 §12 #10 acceptance, before each simulated step we call
    /// `forbidden_guard::enforce_at_runtime(action)` so a Wave 4 wrapper
    /// can hard-abort by injecting `OPENCLAW_REPLAY_FORBIDDEN_TRIPPED=...`
    /// or the magic-file marker. On abort we record the failed action +
    /// preserve all fills emitted up to that point (auditability over
    /// completeness).
    ///
    /// 依 V3 §12 #10 acceptance，每個模擬步驟前我們呼叫
    /// `forbidden_guard::enforce_at_runtime(action)`，使 Wave 4 wrapper
    /// 可透過注入 `OPENCLAW_REPLAY_FORBIDDEN_TRIPPED=...` 或 magic-file
    /// marker 硬性 abort。abort 時記錄失敗的 action + 保留至該點為止發出
    /// 的所有 fill（可審計 > 完整）。
    ///
    /// Sprint B2 R5-T3 dispatch logic:
    ///   * `strategy_adapter.is_some()` → real strategy + 6-Gate risk
    ///     pipeline (proof_R5T3 acceptance path; R5-T4 CLI wires this).
    ///   * `strategy_adapter.is_none()` → synthetic walker fallback
    ///     (proof_1/4/5 e2e legacy path; CRITICAL backward compat — must
    ///     stay byte-equal to the pre-R5-T3 implementation).
    ///
    /// Sprint B2 R5-T3 分流邏輯：
    ///   * `strategy_adapter.is_some()` → 真實 strategy + 6-Gate 風控管線
    ///     （proof_R5T3 acceptance 路徑；R5-T4 CLI 接此）。
    ///   * `strategy_adapter.is_none()` → synthetic walker fallback
    ///     （proof_1/4/5 e2e legacy 路徑；**關鍵向後兼容** — 必與
    ///     R5-T3 前的實作 byte-equal）。
    pub fn execute(&mut self) -> Result<(), ForbiddenPathError> {
        // Empty fixture defense (fixture_loader.rs::load_fixtures already
        // errored on empty; this is purely defensive). The
        // `AbortedFixtureExhausted` variant exists for telemetry parity.
        // 空 fixture 防禦（fixture_loader.rs::load_fixtures 對空已報錯；此純
        // 縱深）。`AbortedFixtureExhausted` variant 為 telemetry 對稱保留。
        if self.fixtures.is_empty() {
            self.status = ReplayStatus::AbortedFixtureExhausted;
            return Ok(());
        }

        // Sprint B2 R5-T3: dispatch to adapter path or synthetic walker.
        // Sprint B2 R5-T3：分流至 adapter 路徑或 synthetic walker。
        if self.strategy_adapter.is_some() {
            self.execute_adapter_pipeline()
        } else {
            self.execute_synthetic_walker()
        }
    }

    /// Sprint B2 R5-T3 — synthetic walker (legacy, proof_1/4/5 e2e).
    /// Each new symbol → 1 entry fill; subsequent events apply
    /// mark-to-market via `balance` arithmetic. NO strategy logic, NO
    /// 6-Gate risk evaluation.
    ///
    /// Sprint B2 R5-T3 — synthetic walker（legacy，proof_1/4/5 e2e）。
    /// 每新 symbol → 1 入場 fill；後續 event 用 `balance` 算術做
    /// mark-to-market。**無**策略邏輯、**無** 6-Gate 風控評估。
    ///
    /// SAFETY / 不變量：本函式邏輯與 R5-T3 前 `execute()` byte-equal；
    /// 改動會破 proof_1（fills.len()==1）+ proof_5（baseline ≡ candidate）
    /// + proof_4（forbidden trip 仍生效）。
    /// SAFETY: this function MUST remain byte-equal to the pre-R5-T3
    /// `execute()` body; mutation breaks proof_1 (fills.len()==1) +
    /// proof_5 (baseline ≡ candidate) + proof_4 (forbidden trip persists).
    fn execute_synthetic_walker(&mut self) -> Result<(), ForbiddenPathError> {
        // Snapshot fixtures into a local so we can iterate while keeping
        // `&mut self` for guard counters + emit_fill.
        // 把 fixture 快照到 local，使得在保留 `&mut self`（用於 guard counter +
        // emit_fill）的同時可走訪。
        let fixtures = std::mem::take(&mut self.fixtures);

        for event in fixtures.iter() {
            // Pre-step runtime guard. V3 §12 #10:「forbidden path aborts run,
            // NOT log-only」.
            // 步驟前 runtime guard。V3 §12 #10：「forbidden 路徑 abort run，
            // 非 log-only」。
            let action = format!("on_event:{}@{}", event.symbol, event.ts_ms);
            self.last_action = action.clone();
            self.guard_calls += 1;
            forbidden_guard::enforce_at_runtime(&action).map_err(|err| {
                self.status = ReplayStatus::AbortedForbidden {
                    action: action.clone(),
                };
                err
            })?;

            // Minimal IMPL — emit one simulated entry fill on FIRST sighting
            // of each symbol; subsequent events update the position's
            // mark-to-market via `balance` arithmetic. The walker
            // deliberately does NOT model: order book, latency, partial
            // fills. fee/slippage are emitted as 0 / 'unknown' on this path
            // (Sprint C R6-T1+T2; see SimulatedFill push site below) since
            // the walker has no `OrderIntent` context (no TIF binding).
            // Minimal IMPL — 每個 symbol 首見時發出一筆模擬入場 fill；後續
            // event 透過 `balance` 算術更新倉位 mark-to-market。Walker 刻意
            // 不模擬：order book、延遲、部分成交。fee/slippage 在此路徑發 0 /
            // 'unknown'（Sprint C R6-T1+T2；見下方 SimulatedFill push site），
            // 因 walker 無 `OrderIntent` context（無 TIF 綁定）。
            if !self.positions.contains_key(&event.symbol) {
                let entry_price = event.close;
                // Deterministic synthetic qty: 1.0 lot per new symbol. Real
                // sizing belongs to a `replay_compatible` strategy refactor
                // out of T1 scope.
                // 確定性合成數量：每新 symbol 1.0 lot。真實 sizing 屬
                // `replay_compatible` 策略重構，非 T1 範圍。
                let qty = 1.0_f64;
                self.positions.insert(event.symbol.clone(), entry_price);
                // Sprint C R6-T1+T2: synthetic-walker → 'unknown' role + 0 fee/slippage
                // (no intent context; proof_1/4/5 e2e byte-equal since slippage=0).
                // Sprint C R6-T1+T2：synthetic-walker → 'unknown' role + 0 fee/slippage
                // （無 intent context；proof_1/4/5 e2e 因 slippage=0 byte-equal）。
                self.fills.push(SimulatedFill {
                    ts_ms: event.ts_ms,
                    symbol: event.symbol.clone(),
                    side: "long".to_string(),
                    qty,
                    price: entry_price,
                    evidence_source_tier: self.fixture_tier_label.clone(),
                    fee: 0.0,
                    fee_rate: 0.0,
                    slippage_bps: 0.0,
                    liquidity_role: "unknown".to_string(),
                    requested_qty: qty,
                    fill_ratio: 1.0,
                    fill_status: "synthetic".to_string(),
                    partial_fill_model_status: "synthetic_walker_unavailable".to_string(),
                    depth_available_qty: None,
                    latency_ms: None,
                    effective_ts_ms: Some(event.ts_ms),
                });
            } else {
                // Mark-to-market: update balance with delta vs last seen entry.
                // mark-to-market：以 vs 最近 entry 的差額更新 balance。
                if let Some(entry_price) = self.positions.get_mut(&event.symbol) {
                    let delta = event.close - *entry_price;
                    self.balance += delta; // qty=1.0 lot per T1
                    *entry_price = event.close;
                }
            }
        }

        // Restore fixtures (so post-execute readers can still inspect).
        // 還原 fixture（使 post-execute reader 仍可檢視）。
        self.fixtures = fixtures;
        self.status = ReplayStatus::Completed;
        Ok(())
    }

    fn should_skip_for_scanner_timeline(&self, event: &MarketEvent) -> bool {
        let Some(timeline) = self.scanner_timeline.as_ref() else {
            return false;
        };
        if timeline.is_active_at(&event.symbol, event.ts_ms) {
            return false;
        }
        self.paper_snapshot
            .as_ref()
            .and_then(|snapshot| snapshot.get_position(&event.symbol))
            .is_none()
    }

    /// Sprint B2 R5-T3 — real adapter pipeline (Strategy::on_tick + 6-Gate
    /// Risk evaluate + apply_fill snapshot mutation).
    ///
    /// Sprint B2 R5-T3 — 真實 adapter 管線（Strategy::on_tick + 6-Gate
    /// 風控評估 + apply_fill snapshot mutation）。
    ///
    /// Forbidden import audit (V3 §6.2 — MUST stay green):
    ///   - 0 use of `crate::paper_state` (uses local `ReplayPaperSnapshot`).
    ///   - 0 use of `crate::canary_writer` / `crate::database`.
    ///   - 0 use of `crate::ipc_server` / `crate::governance_hub`.
    ///   - 0 use of `crate::live_authorization` / `crate::decision_lease`.
    ///   - 0 use of `crate::bybit_*` / `crate::intent_processor::router`.
    ///   - Allowed: `crate::strategies::StrategyAction`,
    ///     `crate::intent_processor::OrderIntent` (pure structural type),
    ///     adapter modules (replay-pure).
    ///
    /// 禁忌匯入稽核（V3 §6.2，**必**保綠）：見 EN 列表；adapter 內部使用
    /// `openclaw_core::guardian` + `crate::risk_checks` + `crate::ml::kelly_sizer`
    /// 為 R5-T2 既綠路徑。
    fn execute_adapter_pipeline(&mut self) -> Result<(), ForbiddenPathError> {
        let fixtures = std::mem::take(&mut self.fixtures);
        let mut context_builder = ReplayContextBuilder::new();
        for event in fixtures.iter() {
            // Pre-step runtime guard. V3 §12 #10 + Proof 4 acceptance.
            // 步驟前 runtime guard。V3 §12 #10 + Proof 4 acceptance。
            let action = format!("on_tick:{}@{}", event.symbol, event.ts_ms);
            self.last_action = action.clone();
            self.guard_calls += 1;
            forbidden_guard::enforce_at_runtime(&action).map_err(|err| {
                self.status = ReplayStatus::AbortedForbidden {
                    action: action.clone(),
                };
                err
            })?;

            let tick_inputs = context_builder.update(event);

            // Update snapshot's last-seen price for this symbol so Gate 2.6
            // P1 cap (balance * p1_risk_pct / price) has a real anchor.
            // REF-21 derives indicators/signals inside the isolated subprocess
            // from fixture OHLCV, or consumes fixture-provided snapshots when
            // present. ATR therefore reaches risk evaluation on warm bars
            // without importing live IndicatorEngine / SignalEngine singletons.
            //
            // SAFETY / 不變量：本 block 至 self.paper_snapshot.is_some() —
            // execute_adapter_pipeline 由 execute() 守衛保證 strategy_adapter
            // 與 paper_snapshot pair 同存（with_adapter_pipeline 唯一入口）。
            // SAFETY: paper_snapshot must be Some at this point — entry guard
            // execute() ensures strategy_adapter / paper_snapshot pair is set
            // (with_adapter_pipeline is the sole construction path).
            if let Some(snap) = self.paper_snapshot.as_mut() {
                snap.latest_price = Some(event.close);
            }
            let atr: f64 = tick_inputs
                .indicators
                .as_ref()
                .and_then(|snapshot| snapshot.get_conservative_atr())
                .map(|atr| atr.atr)
                .filter(|value| value.is_finite() && *value > 0.0)
                .unwrap_or(0.0);
            self.set_replay_event_turnover_24h(tick_inputs.turnover_24h);
            let tier_label = self.fixture_tier_label.clone();

            if self.should_skip_for_scanner_timeline(event) {
                self.scanner_timeline_skipped_events += 1;
                continue;
            }

            let ctx = build_tick_context(event, &tick_inputs);

            // Strategy emits actions (mut borrow on adapter).
            // 策略發出 action（adapter 取 mut borrow）。
            let actions = if let Some(strategy) = self.strategy_adapter.as_mut() {
                strategy.on_tick(&ctx)
            } else {
                Vec::new() // unreachable — execute() guard already filtered.
            };

            // Process each action: Open via risk gate, Close lightweight.
            // 處理每個 action：Open 走風控、Close 輕量。
            for act in actions {
                match act {
                    StrategyAction::Open(intent) => {
                        self.process_open_intent(
                            &intent,
                            event.ts_ms,
                            event.close,
                            event.best_bid,
                            event.best_ask,
                            event.bid_size,
                            event.ask_size,
                            event.bid_depth_5,
                            event.ask_depth_5,
                            atr,
                            &tier_label,
                        );
                    }
                    StrategyAction::Close { symbol, .. } => {
                        self.process_close_intent(
                            &symbol,
                            event.ts_ms,
                            event.close,
                            event.best_bid,
                            event.best_ask,
                            event.bid_size,
                            event.ask_size,
                            event.bid_depth_5,
                            event.ask_depth_5,
                            &tier_label,
                        );
                    }
                }
            }
        }

        self.fixtures = fixtures;
        self.status = ReplayStatus::Completed;
        Ok(())
    }

    // R0-T0 (Sprint C R6 W2): process_open_intent / process_close_intent /
    // apply_fill_open / apply_fill_close moved to crate::replay::apply_fill
    // (same-crate impl block; method calls below resolve identically via
    // self.method_name). 0 logic change — see apply_fill.rs MODULE_NOTE
    // for boundary rationale and forbidden-surface audit.
    //
    // R0-T0（Sprint C R6 W2）：上述 4 個 method 抽到 crate::replay::apply_fill
    // （同 crate impl block；下方 self.method_name 呼叫於同型別不變）。0 邏輯
    // 改動 — 邊界理由與禁忌表面稽核見 apply_fill.rs MODULE_NOTE。

    /// Finalise into a `ReplayResult` (consumes self).
    ///
    /// 最終化為 `ReplayResult`（消費 self）。
    ///
    pub fn into_result(self) -> ReplayResult {
        let starting_balance = self.starting_balance;
        let net_pnl = self.balance - starting_balance;
        let abort_reason = match &self.status {
            ReplayStatus::AbortedForbidden { action } => Some(format!(
                "forbidden_guard::enforce_at_runtime tripped on action={}",
                action
            )),
            ReplayStatus::AbortedFixtureExhausted => {
                Some("fixture_loader returned empty event vector".to_string())
            }
            ReplayStatus::Completed => None,
        };

        // R5-T3: drain decision_traces from strategy_adapter (consumes adapter).
        // R5-T3：從 strategy_adapter 抽出 decision_traces（消費 adapter）。
        let decision_traces = match self.strategy_adapter {
            Some(s) => s.into_trace(),
            None => Vec::new(),
        };

        ReplayResult {
            manifest_id: self.manifest_id,
            execution_confidence: "none".to_string(),
            pnl_summary: PnlSummary {
                events_processed: self.fixtures.len(),
                fills_emitted: self.fills.len(),
                starting_balance,
                ending_balance: self.balance,
                net_pnl,
            },
            diagnostics: ReplayDiagnostics {
                guard_enforce_runtime_calls: self.guard_calls,
                last_action_label: self.last_action,
                abort_reason,
                scanner_timeline_enabled: self.scanner_timeline.is_some(),
                scanner_timeline_cycles: self
                    .scanner_timeline
                    .as_ref()
                    .map(ReplayScannerTimeline::len)
                    .unwrap_or(0),
                scanner_timeline_skipped_events: self.scanner_timeline_skipped_events,
            },
            fills: self.fills,
            status: self.status,
            decision_traces,
        }
    }
}

/// Build a replay TickContext from fixture event + replay-safe derived inputs.
///
/// SAFETY: this helper borrows owned inputs from the current replay loop only;
/// it imports no production singleton, DB writer, exchange, IPC, or live-auth
/// surface.
fn build_tick_context<'a>(
    event: &'a MarketEvent,
    inputs: &'a ReplayTickInputs,
) -> crate::tick_pipeline::TickContext<'a> {
    // W-AUDIT-8a Phase A：replay 用 EMPTY_ALPHA_SURFACE 對齊 byte-identical baseline。
    crate::tick_pipeline::TickContext {
        symbol: &event.symbol,
        price: event.close,
        timestamp_ms: event.ts_ms.max(0) as u64,
        indicators: inputs.indicators.as_ref(),
        indicators_5m: None,
        signals: &inputs.signals,
        h0_allowed: inputs.h0_allowed,
        funding_rate: inputs.funding_rate,
        index_price: inputs.index_price,
        open_interest: inputs.open_interest,
        best_bid: event.best_bid,
        best_ask: event.best_ask,
        tick_size: inputs.tick_size,
        alpha_surface_ref: &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    }
}

fn deterministic_maker_bucket(manifest_id: &str, symbol: &str, ts_ms: i64, attempt: u64) -> u64 {
    let mut hash = 0xcbf2_9ce4_8422_2325_u64;
    for byte in manifest_id
        .as_bytes()
        .iter()
        .chain(symbol.as_bytes().iter())
        .chain(ts_ms.to_le_bytes().iter())
        .chain(attempt.to_le_bytes().iter())
    {
        hash ^= *byte as u64;
        hash = hash.wrapping_mul(0x0000_0100_0000_01b3);
    }
    hash % 10_000
}

// ─────────────────────────────────────────────────────────────────────────
// Module-internal unit tests / 模組內部 unit test
// ─────────────────────────────────────────────────────────────────────────
#[cfg(test)]
#[path = "runner_tests.rs"]
mod runner_tests;
