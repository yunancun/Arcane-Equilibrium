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

use crate::intent_processor::OrderIntent;
use crate::replay::fixture_loader::MarketEvent;
use crate::replay::forbidden_guard::{self, ForbiddenPathError};
use crate::replay::profile::ReplayProfile;
use crate::replay::risk_adapter::{
    ReplayPaperSnapshot, ReplayPosition, ReplayRiskAdapter, RiskDecision,
};
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
    balance: f64,
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
    fills: Vec<SimulatedFill>,
    /// Counter for `enforce_at_runtime` calls — surfaces in
    /// `ReplayDiagnostics.guard_enforce_runtime_calls`.
    /// `enforce_at_runtime` 呼叫計數 — 顯示於
    /// `ReplayDiagnostics.guard_enforce_runtime_calls`。
    guard_calls: u64,
    /// Last action label passed to `enforce_at_runtime`. Surfaces in
    /// `ReplayDiagnostics.last_action_label`.
    /// 最近一次傳給 `enforce_at_runtime` 的 action label。顯示於
    /// `ReplayDiagnostics.last_action_label`。
    last_action: String,
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
    risk_adapter: Option<ReplayRiskAdapter>,
    /// Sprint B2 R5-T3: paper snapshot mutated by `apply_fill_open` /
    /// `apply_fill_close`. `None` in synthetic-walker path.
    /// Sprint B2 R5-T3：由 `apply_fill_open` / `apply_fill_close` mutate 的
    /// paper snapshot。synthetic-walker 路徑下為 `None`。
    paper_snapshot: Option<ReplayPaperSnapshot>,
    /// Sprint C R6-T1: optional `AccountManager` for per-symbol maker/taker.
    /// `None` ⇒ `DEFAULT_*_FEE_RATE` (live cold-boot path).
    /// Sprint C R6-T1：可選 `AccountManager` 提供 per-symbol maker/taker；
    /// `None` ⇒ `DEFAULT_*_FEE_RATE`（live 冷啟動路徑）。
    account_manager: Option<std::sync::Arc<crate::account_manager::AccountManager>>,
    /// Sprint C R6-T2: slippage tier snapshot (default = pre-G7-07 SLIPPAGE_TIERS).
    /// Sprint C R6-T2：滑點分級表（預設 = pre-G7-07 SLIPPAGE_TIERS）。
    slippage_config: crate::config::SlippageConfig,
    /// Sprint C R6-T2: 24h USD turnover for tier lookup; `None` → 5 bps default.
    /// Sprint C R6-T2：tier 查找用 24h USD 成交量；`None` → 5 bps 預設。
    volume_24h: Option<f64>,
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
// Sprint C R6-T1 fee + R6-T2 slippage helpers / R6-T1 費率 + R6-T2 滑點輔助
// ─────────────────────────────────────────────────────────────────────────
// Mirror the live `IntentProcessor::fee_rate_for_tif` +
// `slippage_rate_for_tif` byte-equal contract into the replay path so
// `simulated_fills.{fee, fee_rate, slippage_bps, liquidity_role}` reflect
// the live maker/taker + turnover-tier model. Replay is non-actionable —
// these helpers MUST NOT mutate live state and MUST NOT call Bybit
// endpoints (no `refresh_fee_rates`).
//
// 把 live `IntentProcessor::fee_rate_for_tif` + `slippage_rate_for_tif`
// 的 byte-equal 契約鏡射至 replay 端，讓
// `simulated_fills.{fee, fee_rate, slippage_bps, liquidity_role}` 反映 live
// 同一套 maker/taker + turnover-tier 模型。Replay 非 actionable — 本輔助
// **不**動 live state、**不**打 Bybit endpoint（無 `refresh_fee_rates`）。

/// Sprint C R6 default fee rates / 預設費率（鏡射 live `account_manager`
/// `DEFAULT_TAKER_FEE = 0.00055` / `DEFAULT_MAKER_FEE = 0.0002`）。
/// Kept local so the binary does not touch private `crate::account_manager`
/// state when the seed path is not wired in.
pub(crate) const DEFAULT_TAKER_FEE_RATE: f64 = 0.00055;
pub(crate) const DEFAULT_MAKER_FEE_RATE: f64 = 0.0002;

/// Sprint C R6-T1 — pick (fee_rate, liquidity_role) by TimeInForce.
/// Mirrors `IntentProcessor::fee_rate_for_tif` (intent_processor/mod.rs:1200).
/// PostOnly TIF → maker / Any other TIF (incl. None) → taker.
/// Resolution: `account_manager.maker_fee/taker_fee` if Some; else
/// `DEFAULT_MAKER_FEE_RATE` / `DEFAULT_TAKER_FEE_RATE`.
///
/// Sprint C R6-T1 — 依 TimeInForce 選 (fee_rate, liquidity_role)。
/// 鏡射 `IntentProcessor::fee_rate_for_tif`。PostOnly→maker / 其他（含 None）
/// →taker。優先序：有 Some 時用 `account_manager.maker_fee/taker_fee`；否則
/// 退回 `DEFAULT_*_FEE_RATE`。
///
/// SAFETY / 不變量：本 helper 不打任何 endpoint；replay 端 AccountManager
/// 由 caller `seed_default_fee_rates` 注入（dispatch §1）。
/// SAFETY: helper does NOT call any endpoint; replay-side AccountManager is
/// caller-pre-seeded via `seed_default_fee_rates` (dispatch §1).
fn replay_fee_rate_for_tif(
    account_manager: Option<&std::sync::Arc<crate::account_manager::AccountManager>>,
    symbol: &str,
    tif: Option<crate::order_manager::TimeInForce>,
) -> (f64, &'static str) {
    if matches!(tif, Some(crate::order_manager::TimeInForce::PostOnly)) {
        let rate = account_manager.map(|am| am.maker_fee(symbol)).unwrap_or(DEFAULT_MAKER_FEE_RATE);
        (rate, "maker")
    } else {
        let rate = account_manager.map(|am| am.taker_fee(symbol)).unwrap_or(DEFAULT_TAKER_FEE_RATE);
        (rate, "taker")
    }
}

/// Sprint C R6-T2 — compute signed slippage bps for an intent.
/// Mirrors `IntentProcessor::slippage_rate_for_tif` (intent_processor/mod.rs:1179).
/// PostOnly TIF → 0.0 (rests on book) / Otherwise turnover-tier lookup via
/// `SlippageConfig::lookup_rate`. Sign per dispatch §2: buy → +bps, sell → -bps.
/// `volume_24h <= 0.0` graceful → `default_rate=0.0005` = 5 bps fallback.
///
/// Sprint C R6-T2 — 計算 intent 的有號滑點 bps。鏡射
/// `IntentProcessor::slippage_rate_for_tif`。PostOnly→0；其他經
/// `SlippageConfig::lookup_rate`。符號（dispatch §2）：買 +、賣 -。
/// `volume_24h <= 0.0` graceful → 5 bps default fallback。
fn replay_slippage_bps_for_tif(
    slippage_config: &crate::config::SlippageConfig,
    tif: Option<crate::order_manager::TimeInForce>,
    volume_24h: f64,
    is_long: bool,
) -> f64 {
    if matches!(tif, Some(crate::order_manager::TimeInForce::PostOnly)) {
        return 0.0;
    }
    let bps = slippage_config.lookup_rate(volume_24h) * 10_000.0;
    if is_long { bps } else { -bps }
}

/// Sprint C R6-T2 — apply signed slippage_bps to a reference price.
/// fill_price = reference_price × (1 + slippage_bps / 10_000.0).
/// `slippage_bps == 0` (PostOnly) → fill_price == reference_price.
/// Sprint C R6-T2 — 套用有號 slippage_bps 至參考價。
/// `slippage_bps == 0`（PostOnly）→ fill_price == reference_price。
fn apply_slippage_to_price(reference_price: f64, slippage_bps: f64) -> f64 {
    reference_price * (1.0 + slippage_bps / 10_000.0)
}

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

            // Update snapshot's last-seen price for this symbol so Gate 2.6
            // P1 cap (balance * p1_risk_pct / price) has a real anchor.
            // ATR is derived later — fixture builder pre-computes
            // `IndicatorSnapshot.atr_14` (PA design §13 line 691); R5-T3
            // assumes `event.indicators` is None until R5-T4 fixture loader
            // upgrade lands, falling back to atr=0.0 (Kelly skips
            // volatility scaling — matches `risk_adapter::evaluate` line 321).
            //
            // 更新 snapshot 該 symbol 的 latest_price，使 Gate 2.6 P1 cap
            // （balance * p1_risk_pct / price）有真錨。ATR 後算 — fixture
            // builder 預先算 `IndicatorSnapshot.atr_14`（PA design §13
            // line 691）；R5-T3 在 R5-T4 fixture loader 升級前假設
            // `event.indicators` 為 None，fallback 至 atr=0.0（Kelly 跳過
            // 波動率縮放 — 對齊 `risk_adapter::evaluate` line 321）。
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
            let atr: f64 = 0.0; // R5-T4 fixture-loader upgrade will populate.
            let tier_label = self.fixture_tier_label.clone();

            // Build TickContext (R5-T3 minimal fields; R5-T4 CLI will populate
            // indicators, signals, h0_allowed from fixture metadata).
            // 構造 TickContext（R5-T3 最小欄位；R5-T4 CLI 將以 fixture metadata
            // 填 indicators / signals / h0_allowed）。
            let ctx = build_tick_context(event);

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
                        self.process_open_intent(&intent, event.ts_ms, event.close, atr, &tier_label);
                    }
                    StrategyAction::Close { symbol, .. } => {
                        self.process_close_intent(&symbol, event.ts_ms, event.close, &tier_label);
                    }
                }
            }
        }

        self.fixtures = fixtures;
        self.status = ReplayStatus::Completed;
        Ok(())
    }

    /// Sprint B2 R5-T3 — process a strategy `Open` intent through the
    /// 6-Gate risk adapter; emit either a real fill (qty>0) on Accepted or
    /// a ghost row (qty=0, per PA §6.1) on Rejected.
    ///
    /// Sprint B2 R5-T3 — 將策略 `Open` intent 經 6-Gate 風控 adapter 處理；
    /// Accepted 發真 fill（qty>0），Rejected 發 ghost row（qty=0，per PA §6.1）。
    fn process_open_intent(
        &mut self,
        intent: &OrderIntent,
        ts_ms: i64,
        close_price: f64,
        atr: f64,
        tier_label: &str,
    ) {
        let snapshot = match self.paper_snapshot.as_ref() {
            Some(s) => s,
            None => return, // unreachable — guarded by execute()
        };
        let risk = match self.risk_adapter.as_ref() {
            Some(r) => r,
            None => return, // unreachable — paired with strategy_adapter
        };
        let decision = risk.evaluate(intent, snapshot, atr);
        // Sprint C R6-T1+T2: derive (fee_rate, liquidity_role, slippage_bps)
        // from intent.time_in_force. Used for both Accepted (qty>0) and
        // Rejected (qty=0 ghost) paths so ghost row carries counterfactual
        // fee classification (transparency for downstream attribution).
        // Sprint C R6-T1+T2：從 intent.time_in_force 派生 (fee_rate,
        // liquidity_role, slippage_bps)。Accepted (qty>0) 與 Rejected (qty=0
        // ghost) 兩路徑共用，使 ghost row 帶 counterfactual 費率分類。
        let (fee_rate, liquidity_role) = replay_fee_rate_for_tif(
            self.account_manager.as_ref(),
            &intent.symbol,
            intent.time_in_force,
        );
        let volume_24h = self.volume_24h.unwrap_or(0.0);
        let slippage_bps = replay_slippage_bps_for_tif(
            &self.slippage_config,
            intent.time_in_force,
            volume_24h,
            intent.is_long,
        );
        match decision {
            RiskDecision::Accepted { final_qty, .. } => {
                // Reference price: limit if present (PostOnly), else event close.
                // PostOnly slippage_bps=0 → fill_price == limit_price byte-equal
                // to Sprint A/B baseline.
                // 參考價：有 limit_price 取之（PostOnly），否則 event close。
                // PostOnly slippage_bps=0 → fill_price == limit_price byte-equal。
                let reference_price = intent.limit_price.unwrap_or(close_price);
                let fill_price = apply_slippage_to_price(reference_price, slippage_bps);
                let fee = final_qty * fill_price * fee_rate;
                self.fills.push(SimulatedFill {
                    ts_ms,
                    symbol: intent.symbol.clone(),
                    side: if intent.is_long { "long" } else { "short" }.to_string(),
                    qty: final_qty,
                    price: fill_price,
                    evidence_source_tier: tier_label.to_string(),
                    fee,
                    fee_rate,
                    slippage_bps,
                    liquidity_role: liquidity_role.to_string(),
                });
                self.apply_fill_open(&intent.symbol, intent.is_long, final_qty, fill_price);
                self.last_action = format!("open:{}", intent.symbol);
            }
            RiskDecision::Rejected { gate, reason } => {
                // Ghost fill row (qty=0) preserves the rejected decision for
                // evidence trail (PA §6.1). qty=0 ⇒ fee=0, but fee_rate /
                // liquidity_role / slippage_bps reflect counterfactual cost.
                // Ghost fill row (qty=0) 保留被拒決策（PA §6.1）。qty=0 ⇒ fee=0；
                // fee_rate / liquidity_role / slippage_bps 反映 counterfactual。
                let _ = reason; // recorded via last_action below.
                let reference_price = intent.limit_price.unwrap_or(close_price);
                self.fills.push(SimulatedFill {
                    ts_ms,
                    symbol: intent.symbol.clone(),
                    side: if intent.is_long { "long" } else { "short" }.to_string(),
                    qty: 0.0,
                    price: reference_price,
                    evidence_source_tier: tier_label.to_string(),
                    fee: 0.0,
                    fee_rate,
                    slippage_bps,
                    liquidity_role: liquidity_role.to_string(),
                });
                self.last_action = format!("reject:{}:{}", intent.symbol, gate);
            }
        }
    }

    /// Sprint B2 R5-T3 — process a strategy `Close` intent: look up the
    /// existing position in `paper_snapshot`, realise PnL, mutate balance.
    /// No-op when symbol has no open position (matches live router behaviour).
    ///
    /// Sprint B2 R5-T3 — 處理策略 `Close` intent：查 `paper_snapshot` 既有
    /// 倉位、realise PnL、mutate balance。symbol 無倉時 no-op（對齊 live
    /// router 行為）。
    fn process_close_intent(
        &mut self,
        symbol: &str,
        ts_ms: i64,
        close_price: f64,
        tier_label: &str,
    ) {
        let snapshot = match self.paper_snapshot.as_ref() {
            Some(s) => s,
            None => return,
        };
        let pos = match snapshot.get_position(symbol) {
            Some(p) => p.clone(),
            None => {
                self.last_action = format!("close_skip:{}", symbol);
                return;
            }
        };
        // Sprint C R6-T1+T2: Close has no OrderIntent/TIF — treat as taker
        // (live engine routes Close as market; strategies/mod.rs:51 "Close
        // bypasses governance gates"). Closing leg sign opposite open:
        // long pos→sell→-bps / short pos→buy→+bps.
        // Sprint C R6-T1+T2：Close 無 OrderIntent/TIF — 視為 taker
        // （live 預設 Close 走市價）。平倉方向與開倉相反：多倉→賣→-bps /
        // 空倉→買→+bps。
        let close_is_long = !pos.is_long;
        let (fee_rate, liquidity_role) = replay_fee_rate_for_tif(
            self.account_manager.as_ref(),
            symbol,
            None, // close has no TIF → taker path
        );
        let volume_24h = self.volume_24h.unwrap_or(0.0);
        let slippage_bps = replay_slippage_bps_for_tif(
            &self.slippage_config,
            None,
            volume_24h,
            close_is_long,
        );
        let fill_price = apply_slippage_to_price(close_price, slippage_bps);
        let fee = pos.qty * fill_price * fee_rate;
        // Record close-side fill (qty>0 with side opposite to position).
        // 記 close-side fill（qty>0，side 與倉位反向）。
        self.fills.push(SimulatedFill {
            ts_ms,
            symbol: symbol.to_string(),
            side: if pos.is_long { "short" } else { "long" }.to_string(),
            qty: pos.qty,
            price: fill_price,
            evidence_source_tier: tier_label.to_string(),
            fee,
            fee_rate,
            slippage_bps,
            liquidity_role: liquidity_role.to_string(),
        });
        self.apply_fill_close(symbol, fill_price);
        self.last_action = format!("close:{}", symbol);
    }

    /// Sprint B2 R5-T3 — open-side snapshot mutation. Inserts/extends a
    /// position; deducts no fee from `snap.balance`. Sprint C R6-T1: fee is
    /// captured at the `SimulatedFill` row level (see `process_open_intent` /
    /// `process_close_intent`) — folding fee into `snap.balance` mid-flight
    /// would double-count once `into_result` reads it for
    /// `pnl_summary.ending_balance`. Sprint D R8 may extend `pnl_summary` to
    /// fold fee into PnL — but that is a `pnl_summary` schema decision.
    ///
    /// Sprint B2 R5-T3 — open-side snapshot mutation。Sprint C R6-T1：fee 在
    /// `SimulatedFill` row 層捕獲，**不**扣 `snap.balance`（避免 `into_result`
    /// 讀 `snap.balance` 餵 `pnl_summary.ending_balance` 時 double-count）。
    fn apply_fill_open(&mut self, symbol: &str, is_long: bool, qty: f64, fill_price: f64) {
        let snap = match self.paper_snapshot.as_mut() {
            Some(s) => s,
            None => return,
        };
        if let Some(idx) = snap.positions.iter().position(|p| p.symbol == symbol) {
            // Same-symbol existing position → extend qty + recompute weighted
            // entry price (rare path — Gate 1.5 should already reject same-
            // direction adds; reducing path nets the qty).
            // 同 symbol 既有倉 → 擴 qty + 重算加權入場價（罕見路徑 — Gate
            // 1.5 應已拒同向加倉；減倉路徑 net qty）。
            let pos = &mut snap.positions[idx];
            if pos.is_long == is_long {
                let new_qty = pos.qty + qty;
                if new_qty > 0.0 {
                    pos.entry_price = (pos.entry_price * pos.qty + fill_price * qty) / new_qty;
                    pos.qty = new_qty;
                }
            } else {
                // Reducing path: net qty.
                // 減倉路徑：net qty。
                if qty >= pos.qty {
                    let realised_per_unit = if pos.is_long {
                        fill_price - pos.entry_price
                    } else {
                        pos.entry_price - fill_price
                    };
                    snap.balance += realised_per_unit * pos.qty;
                    snap.positions.remove(idx);
                } else {
                    let realised_per_unit = if pos.is_long {
                        fill_price - pos.entry_price
                    } else {
                        pos.entry_price - fill_price
                    };
                    snap.balance += realised_per_unit * qty;
                    let after = &mut snap.positions[idx];
                    after.qty -= qty;
                }
            }
        } else {
            // Fresh open.
            // 全新開倉。
            snap.positions.push(ReplayPosition {
                symbol: symbol.to_string(),
                is_long,
                qty,
                entry_price: fill_price,
            });
        }
        self.balance = snap.balance;
    }

    /// Sprint B2 R5-T3 — close-side snapshot mutation. Realises PnL =
    /// (fill_price - entry_price) * qty (long; sign-flipped for short),
    /// removes position, updates balance. Mirrors `paper_state::realize_close`.
    /// Sprint C R6-T1: fee captured at `SimulatedFill` row level (see
    /// `process_close_intent`), NOT subtracted from `snap.balance` here
    /// (same rationale as `apply_fill_open` — avoid `pnl_summary` double-count).
    ///
    /// Sprint B2 R5-T3 — close-side snapshot mutation；對齊
    /// `paper_state::realize_close`。Sprint C R6-T1：fee 在
    /// `SimulatedFill` row 層捕獲，**不**扣 `snap.balance`（同
    /// `apply_fill_open` 邏輯，避免 `pnl_summary` double-count）。
    fn apply_fill_close(&mut self, symbol: &str, fill_price: f64) {
        let snap = match self.paper_snapshot.as_mut() {
            Some(s) => s,
            None => return,
        };
        if let Some(idx) = snap.positions.iter().position(|p| p.symbol == symbol) {
            let pos = snap.positions.remove(idx);
            // PnL = (fill - entry) * qty for long; (entry - fill) * qty for short.
            // Sprint C R6-T1: fee is captured at row level in
            // `process_close_intent`, NOT applied to snap.balance here.
            // PnL = (fill - entry) * qty 多倉；(entry - fill) * qty 空倉。
            // Sprint C R6-T1：fee 在 `process_close_intent` row 層捕獲，
            // **不**於此扣 snap.balance。
            let realised_per_unit = if pos.is_long {
                fill_price - pos.entry_price
            } else {
                pos.entry_price - fill_price
            };
            snap.balance += realised_per_unit * pos.qty;
        }
        self.balance = snap.balance;
    }

    /// Finalise into a `ReplayResult` (consumes self).
    ///
    /// 最終化為 `ReplayResult`（消費 self）。
    ///
    /// `execution_confidence` is hardcoded to `"none"` per V3 §12 #11
    /// invariant for the Isolated profile.
    ///
    /// `execution_confidence` 為 V3 §12 #11 不變量於 Isolated profile 下硬編
    /// `"none"`。
    pub fn into_result(self) -> ReplayResult {
        let starting_balance = if self.paper_snapshot.is_some() {
            // Adapter path uses snapshot balance as anchor; if reached
            // `into_result`, snapshot.balance has been mirrored into
            // self.balance during `with_adapter_pipeline`.
            // adapter 路徑用 snapshot balance 為錨；走到 `into_result` 時
            // snapshot.balance 已於 `with_adapter_pipeline` 鏡射至
            // self.balance；但 starting_balance 應對齊原始注入值，故另存。
            // R5-T4 CLI 後續可擴 ReplayResult 暴露原始 starting_balance；
            // R5-T3 暫沿用 DEFAULT_STARTING_BALANCE 為對外契約穩定點。
            DEFAULT_STARTING_BALANCE
        } else {
            DEFAULT_STARTING_BALANCE
        };
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
            },
            fills: self.fills,
            status: self.status,
            decision_traces,
        }
    }
}

/// Sprint B2 R5-T3 — build a minimal `TickContext` for adapter-path
/// `Strategy::on_tick`. R5-T3 leaves indicators/signals empty; R5-T4
/// CLI + fixture-builder will populate them per PA design §13 line 691.
///
/// Sprint B2 R5-T3 — 為 adapter 路徑 `Strategy::on_tick` 建最小
/// `TickContext`。R5-T3 留 indicators/signals 為空；R5-T4 CLI + fixture-builder
/// 會依 PA design §13 line 691 填入。
///
/// SAFETY / 不變量：本 helper 不導入任何 V3 §6.2 forbidden surface；
/// `signals` 用 `&[]` 空切片（'static），`indicators` 用 None。
/// SAFETY: helper does not import any V3 §6.2 forbidden surface; `signals`
/// uses `&[]` empty slice ('static), `indicators` uses None.
fn build_tick_context<'a>(event: &'a MarketEvent) -> crate::tick_pipeline::TickContext<'a> {
    crate::tick_pipeline::TickContext {
        symbol: &event.symbol,
        price: event.close,
        timestamp_ms: event.ts_ms.max(0) as u64,
        indicators: None,
        signals: &[],
        h0_allowed: true,
        funding_rate: None,
        index_price: None,
        open_interest: None,
        best_bid: None,
        best_ask: None,
        tick_size: None,
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Module-internal unit tests / 模組內部 unit test
// ─────────────────────────────────────────────────────────────────────────
#[cfg(test)]
mod tests {
    use super::*;

    fn synthetic_events() -> Vec<MarketEvent> {
        vec![
            MarketEvent {
                ts_ms: 1,
                symbol: "BTCUSDT".into(),
                open: 100.0,
                high: 101.0,
                low: 99.0,
                close: 100.0,
                volume: 1.0,
            },
            MarketEvent {
                ts_ms: 2,
                symbol: "BTCUSDT".into(),
                open: 100.0,
                high: 105.0,
                low: 100.0,
                close: 105.0,
                volume: 1.0,
            },
            MarketEvent {
                ts_ms: 3,
                symbol: "ETHUSDT".into(),
                open: 50.0,
                high: 51.0,
                low: 49.0,
                close: 50.5,
                volume: 5.0,
            },
        ]
    }

    #[test]
    fn build_rejects_non_isolated() {
        // Sprint B2 R5-T3: `unwrap_err()` would require IsolatedPipeline:Debug;
        // since it now holds Option<Box<dyn Strategy>> via ReplayStrategyAdapter
        // (Box<dyn Strategy> is not Debug), use explicit match like the sibling
        // adapter modules.
        // Sprint B2 R5-T3：`unwrap_err()` 需 IsolatedPipeline:Debug；因經
        // ReplayStrategyAdapter 持 Option<Box<dyn Strategy>>（不可 Debug），
        // 改用顯式 match 與 sibling adapter module 對齊。
        match build_isolated_pipeline(
            ReplayProfile::Live,
            "exp_1".into(),
            "S3",
            synthetic_events(),
        ) {
            Err(ReplayError::NonIsolatedProfile { found }) => {
                assert_eq!(found, ReplayProfile::Live);
            }
            Ok(_) => panic!("expected NonIsolatedProfile rejection"),
            Err(other) => panic!("expected NonIsolatedProfile, got {:?}", other),
        }
    }

    #[test]
    fn execute_completed_walks_fixtures() {
        let mut p = build_isolated_pipeline(
            ReplayProfile::Isolated,
            "exp_2".into(),
            "S3",
            synthetic_events(),
        )
        .unwrap();
        p.execute().unwrap();
        let r = p.into_result();
        assert_eq!(r.status, ReplayStatus::Completed);
        // 2 distinct symbols => 2 entry fills emitted.
        assert_eq!(r.fills.len(), 2);
        // BTCUSDT entry at 100 then mark to 105 → +5 USDT delta on balance.
        assert!((r.pnl_summary.net_pnl - 5.0).abs() < 1e-9);
        assert_eq!(r.execution_confidence, "none");
        assert_eq!(r.pnl_summary.fills_emitted, 2);
        assert!(r.diagnostics.guard_enforce_runtime_calls >= 3);
        assert_eq!(r.diagnostics.abort_reason, None);
    }

    #[test]
    fn evidence_source_tier_maps_correctly() {
        let mut p = build_isolated_pipeline(
            ReplayProfile::Isolated,
            "exp_3".into(),
            "S2",
            synthetic_events(),
        )
        .unwrap();
        p.execute().unwrap();
        let r = p.into_result();
        for f in &r.fills {
            assert_eq!(f.evidence_source_tier, "calibrated_replay");
        }

        let mut p3 = build_isolated_pipeline(
            ReplayProfile::Isolated,
            "exp_4".into(),
            "S3",
            synthetic_events(),
        )
        .unwrap();
        p3.execute().unwrap();
        let r3 = p3.into_result();
        for f in &r3.fills {
            assert_eq!(f.evidence_source_tier, "synthetic_replay");
        }
    }

    #[test]
    fn status_label_matches_variant() {
        assert_eq!(ReplayStatus::Completed.label(), "completed");
        assert_eq!(
            ReplayStatus::AbortedForbidden {
                action: "x".into()
            }
            .label(),
            "aborted_forbidden"
        );
        assert_eq!(
            ReplayStatus::AbortedFixtureExhausted.label(),
            "aborted_fixture_exhausted"
        );
    }

    // ─── Sprint B2 R5-T3 inline tests ───
    // ─── Sprint B2 R5-T3 inline 測試 ───
    //
    // These cover the new adapter wire-up + fail-loud snapshot construction.
    // Acceptance-level coverage (cross-language parameter delta, full
    // baseline-vs-candidate replay) lives in `tests/replay/test_replay_*_smoke.rs`
    // (R5-T7).
    //
    // 涵蓋新 adapter 接線 + fail-loud snapshot 構造。Acceptance 層覆蓋
    // （跨語言 parameter delta、完整 baseline-vs-candidate replay）在
    // R5-T7 `tests/replay/test_replay_*_smoke.rs`。

    use crate::intent_processor::OrderIntent;
    use crate::ml::kelly_sizer::KellyConfig;
    use crate::strategies::{Strategy, StrategyAction};
    use openclaw_core::guardian::GuardianConfig;

    /// Stub strategy that emits one Open per call until `stop_after` ticks.
    /// Stub 策略：每 tick 發一個 Open 直到 `stop_after`。
    struct OneShotStub {
        emitted: usize,
        stop_after: usize,
    }

    impl Strategy for OneShotStub {
        fn name(&self) -> &str {
            "r5t3_stub"
        }
        fn is_active(&self) -> bool {
            true
        }
        fn set_active(&mut self, _: bool) {}
        fn on_tick(&mut self, ctx: &crate::tick_pipeline::TickContext<'_>) -> Vec<StrategyAction> {
            if self.emitted >= self.stop_after {
                return Vec::new();
            }
            self.emitted += 1;
            vec![StrategyAction::Open(OrderIntent {
                symbol: ctx.symbol.to_string(),
                is_long: true,
                qty: 0.01,
                confidence: 0.5,
                strategy: "r5t3_stub".to_string(),
                order_type: "market".to_string(),
                limit_price: None,
                confluence_score: None,
                persistence_elapsed_ms: None,
                time_in_force: None,
                maker_timeout_ms: None,
            })]
        }
    }

    fn make_snapshot_seed(
        balance: f64,
        latest_price: Option<f64>,
        positions: Vec<crate::replay::risk_adapter::ReplayPosition>,
    ) -> crate::replay::risk_adapter::ReplayPaperSnapshot {
        crate::replay::risk_adapter::ReplayPaperSnapshot {
            balance,
            drawdown_pct: 0.0,
            positions,
            latest_price,
            exposure_pct: 0.0,
            correlated_exposure_pct: 0.0,
            leverage: 0.0,
            daily_loss_pct: 0.0,
            trade_stats: None,
        }
    }

    fn make_adapters(
        kelly: Option<KellyConfig>,
    ) -> (
        crate::replay::strategy_adapter::ReplayStrategyAdapter,
        crate::replay::risk_adapter::ReplayRiskAdapter,
    ) {
        let strat = Box::new(OneShotStub {
            emitted: 0,
            stop_after: 1,
        });
        let strategy_adapter = crate::replay::strategy_adapter::ReplayStrategyAdapter::new(
            strat,
            ReplayProfile::Isolated,
        )
        .expect("Isolated accepts");
        let risk_adapter = crate::replay::risk_adapter::ReplayRiskAdapter::new(
            ReplayProfile::Isolated,
            GuardianConfig::default(),
            crate::config::RiskConfig::default(),
            0.02,
            kelly,
        )
        .expect("risk adapter Isolated accepts");
        (strategy_adapter, risk_adapter)
    }

    #[test]
    fn adapter_pipeline_rejects_nan_balance_snapshot() {
        // F-3 LOW finding fix: NaN balance must fail loud at attach time.
        // F-3 LOW finding fix：NaN balance 必須在 attach 時 fail loud。
        let pipeline = build_isolated_pipeline(
            ReplayProfile::Isolated,
            "exp_r5t3_nan".into(),
            "S3",
            synthetic_events(),
        )
        .expect("baseline build OK");
        let (strategy_adapter, risk_adapter) = make_adapters(None);
        let snapshot = make_snapshot_seed(f64::NAN, Some(100.0), Vec::new());
        match pipeline.with_adapter_pipeline(strategy_adapter, risk_adapter, snapshot) {
            Err(ReplayError::InvalidSnapshot { reason }) => {
                assert!(
                    reason.contains("NaN") || reason.contains("Inf") || reason.contains("finite"),
                    "reason should mention finite/NaN, got: {}",
                    reason
                );
            }
            Ok(_) => panic!("expected InvalidSnapshot rejection on NaN balance"),
            Err(other) => panic!("expected InvalidSnapshot, got {:?}", other),
        }
    }

    #[test]
    fn adapter_pipeline_rejects_empty_anchor_snapshot() {
        // F-3 LOW finding fix part 2: empty latest_price + empty positions
        // would silent-bypass Gate 2.6 P1 cap; must fail loud at attach.
        // F-3 LOW finding fix part 2：空 latest_price + 空 positions 會
        // silent-bypass Gate 2.6 P1 cap；必須在 attach 時 fail loud。
        let pipeline = build_isolated_pipeline(
            ReplayProfile::Isolated,
            "exp_r5t3_empty".into(),
            "S3",
            synthetic_events(),
        )
        .expect("baseline build OK");
        let (strategy_adapter, risk_adapter) = make_adapters(None);
        let snapshot = make_snapshot_seed(10_000.0, None, Vec::new());
        match pipeline.with_adapter_pipeline(strategy_adapter, risk_adapter, snapshot) {
            Err(ReplayError::InvalidSnapshot { reason }) => {
                assert!(
                    reason.contains("latest_price") && reason.contains("empty"),
                    "reason should mention latest_price + empty, got: {}",
                    reason
                );
            }
            Ok(_) => panic!("expected InvalidSnapshot rejection on empty anchor"),
            Err(other) => panic!("expected InvalidSnapshot, got {:?}", other),
        }
    }

    #[test]
    fn adapter_pipeline_walks_strategy_then_risk_emits_real_fill() {
        // R5-T3 acceptance: with strategy + risk adapter wired, execute
        // produces a real fill via Strategy::on_tick → 6-Gate risk evaluate
        // → apply_fill_open. decision_traces captures the strategy's Open.
        // R5-T3 acceptance：接 strategy + risk adapter 後，execute 經
        // Strategy::on_tick → 6-Gate 風控 evaluate → apply_fill_open 產真 fill。
        // decision_traces 捕獲策略的 Open。
        let pipeline = build_isolated_pipeline(
            ReplayProfile::Isolated,
            "exp_r5t3_happy".into(),
            "S3",
            synthetic_events(),
        )
        .expect("baseline build OK");
        let (strategy_adapter, risk_adapter) = make_adapters(None);
        let snapshot = make_snapshot_seed(10_000.0, Some(100.0), Vec::new());
        let mut wired = pipeline
            .with_adapter_pipeline(strategy_adapter, risk_adapter, snapshot)
            .expect("snapshot validation passes");
        wired.execute().expect("execute completes");
        let result = wired.into_result();
        assert_eq!(result.status, ReplayStatus::Completed);
        assert_eq!(result.execution_confidence, "none");
        // OneShotStub emits 1 Open on first tick (BTCUSDT@1) — risk gates
        // accept (qty=0.01 < P1 cap 2.0 at price=100 balance=10_000) → 1 fill.
        // OneShotStub 第一 tick 發 1 Open（BTCUSDT@1）— 風控通過
        // （qty=0.01 < P1 cap 2.0，price=100 balance=10000）→ 1 fill。
        assert_eq!(result.fills.len(), 1, "expected 1 accepted fill");
        let f0 = &result.fills[0];
        assert_eq!(f0.symbol, "BTCUSDT");
        assert_eq!(f0.side, "long");
        assert!((f0.qty - 0.01).abs() < 1e-9);
        // Decision trace populated (strategy emitted 1 Open).
        // 決策追蹤填入（策略發 1 Open）。
        assert_eq!(result.decision_traces.len(), 1);
        assert_eq!(result.decision_traces[0].symbol, "BTCUSDT");
        assert_eq!(result.decision_traces[0].strategy_name, "r5t3_stub");
    }

    #[test]
    fn adapter_pipeline_records_ghost_fill_on_risk_reject() {
        // R5-T3 acceptance + PA §6.1: rejected intent records qty=0 ghost fill.
        // Construct snapshot with existing same-direction position to trigger
        // Gate 1.5 (DuplicatePosition reject). Use only 1 event to keep the
        // last_action_label deterministic at the rejection action.
        // R5-T3 acceptance + PA §6.1：被拒 intent 記 qty=0 ghost fill。
        // 構造同向倉以觸 Gate 1.5（DuplicatePosition）。僅用 1 event 使
        // last_action_label 確定停在 reject。
        let single_event = vec![MarketEvent {
            ts_ms: 1,
            symbol: "BTCUSDT".into(),
            open: 100.0,
            high: 101.0,
            low: 99.0,
            close: 100.0,
            volume: 1.0,
        }];
        let pipeline = build_isolated_pipeline(
            ReplayProfile::Isolated,
            "exp_r5t3_ghost".into(),
            "S3",
            single_event,
        )
        .expect("baseline build OK");
        let (strategy_adapter, risk_adapter) = make_adapters(None);
        let snapshot = make_snapshot_seed(
            10_000.0,
            Some(100.0),
            vec![crate::replay::risk_adapter::ReplayPosition {
                symbol: "BTCUSDT".into(),
                is_long: true, // same direction as stub
                qty: 0.5,
                entry_price: 100.0,
            }],
        );
        let mut wired = pipeline
            .with_adapter_pipeline(strategy_adapter, risk_adapter, snapshot)
            .expect("snapshot validation passes");
        wired.execute().expect("execute completes");
        let result = wired.into_result();
        // Ghost row recorded with qty=0.
        // Ghost row 紀錄 qty=0。
        let ghost = result
            .fills
            .iter()
            .find(|f| f.qty == 0.0 && f.symbol == "BTCUSDT")
            .expect("expected ghost fill on Gate 1.5 reject");
        assert_eq!(ghost.side, "long");
        assert!(
            result.diagnostics.last_action_label.contains("reject:BTCUSDT:1.5_dup"),
            "last_action should record 1.5_dup gate, got: {}",
            result.diagnostics.last_action_label
        );
    }

    // ─── Sprint C R6-T1 + R6-T2 unit tests / R6-T1 + R6-T2 單元測試 ───
    // Dispatch §5 6 cases + 3 cross-checks (PostOnly path / synthetic walker
    // backward compat / ghost row counterfactual). Helpers tested directly;
    // SimulatedFill end-to-end via TifStub.
    // Dispatch §5 6 case + 3 交叉驗證（PostOnly path / synthetic walker
    // 向後兼容 / ghost row counterfactual）。Helper 直測；end-to-end 用 TifStub。

    use crate::order_manager::TimeInForce;

    /// Stub strategy emitting one Open with caller-controlled TimeInForce.
    /// Stub 策略：發一筆 caller 指定 TimeInForce 的 Open。
    struct TifStub {
        emitted: bool,
        tif: Option<TimeInForce>,
        is_long: bool,
        limit_price: Option<f64>,
    }

    impl Strategy for TifStub {
        fn name(&self) -> &str {
            "r6t1t2_stub"
        }
        fn is_active(&self) -> bool {
            true
        }
        fn set_active(&mut self, _: bool) {}
        fn on_tick(&mut self, ctx: &crate::tick_pipeline::TickContext<'_>) -> Vec<StrategyAction> {
            if self.emitted {
                return Vec::new();
            }
            self.emitted = true;
            vec![StrategyAction::Open(OrderIntent {
                symbol: ctx.symbol.to_string(),
                is_long: self.is_long,
                qty: 0.01,
                confidence: 0.5,
                strategy: "r6t1t2_stub".to_string(),
                order_type: if self.limit_price.is_some() {
                    "limit".to_string()
                } else {
                    "market".to_string()
                },
                limit_price: self.limit_price,
                confluence_score: None,
                persistence_elapsed_ms: None,
                time_in_force: self.tif,
                maker_timeout_ms: None,
            })]
        }
    }

    fn make_tif_adapters(
        tif: Option<TimeInForce>,
        is_long: bool,
        limit_price: Option<f64>,
    ) -> (
        crate::replay::strategy_adapter::ReplayStrategyAdapter,
        crate::replay::risk_adapter::ReplayRiskAdapter,
    ) {
        let strat = Box::new(TifStub { emitted: false, tif, is_long, limit_price });
        let strategy_adapter =
            crate::replay::strategy_adapter::ReplayStrategyAdapter::new(strat, ReplayProfile::Isolated)
                .expect("Isolated accepts");
        let risk_adapter = crate::replay::risk_adapter::ReplayRiskAdapter::new(
            ReplayProfile::Isolated,
            GuardianConfig::default(),
            crate::config::RiskConfig::default(),
            0.02,
            None,
        )
        .expect("risk adapter Isolated accepts");
        (strategy_adapter, risk_adapter)
    }

    /// Sprint C R6-T1+T2 — minimal 1-event fixture builder.
    /// Sprint C R6-T1+T2 — 最小 1-event fixture 構造器。
    fn r6_single_event() -> Vec<MarketEvent> {
        vec![MarketEvent {
            ts_ms: 1,
            symbol: "BTCUSDT".into(),
            open: 100.0,
            high: 101.0,
            low: 99.0,
            close: 100.0,
            volume: 1.0,
        }]
    }

    // ─── Helper unit tests / 輔助函式單元測試 ───

    #[test]
    fn test_apply_fill_postonly_uses_maker_fee() {
        // R6-T1: PostOnly TIF + no AM seeded → DEFAULT_MAKER_FEE_RATE + 'maker'.
        // R6-T1：PostOnly TIF + 無 AM → DEFAULT_MAKER_FEE_RATE + 'maker'。
        let (rate, role) = replay_fee_rate_for_tif(None, "BTCUSDT", Some(TimeInForce::PostOnly));
        assert!((rate - DEFAULT_MAKER_FEE_RATE).abs() < 1e-12, "maker rate, got {}", rate);
        assert_eq!(role, "maker", "PostOnly → 'maker' role");
    }

    #[test]
    fn test_apply_fill_non_postonly_uses_taker_fee() {
        // R6-T1: non-PostOnly TIF (None / GTC / IOC / FOK) → taker + 'taker'.
        // R6-T1：非 PostOnly（None / GTC / IOC / FOK）→ taker + 'taker'。
        for (tif, label) in [
            (None, "None"),
            (Some(TimeInForce::GTC), "GTC"),
            (Some(TimeInForce::IOC), "IOC"),
            (Some(TimeInForce::FOK), "FOK"),
        ] {
            let (rate, role) = replay_fee_rate_for_tif(None, "BTCUSDT", tif);
            assert!((rate - DEFAULT_TAKER_FEE_RATE).abs() < 1e-12, "{} taker, got {}", label, rate);
            assert_eq!(role, "taker", "{} → 'taker'", label);
        }
    }

    #[test]
    fn test_apply_fill_long_slippage_increases_fill_price() {
        // R6-T2: buy (is_long=true) at $1B tier → +1.0 bps signed →
        // 100.0 × (1 + 1/10000) = 100.01.
        // R6-T2：買 + $1B tier → +1.0 bps → 100.0 × (1 + 1/10000) = 100.01。
        let cfg = crate::config::SlippageConfig::default();
        let bps = replay_slippage_bps_for_tif(&cfg, None, 2_000_000_000.0, true);
        assert!(bps > 0.0, "buy → positive bps, got {}", bps);
        let fill = apply_slippage_to_price(100.0, bps);
        assert!(fill > 100.0, "buy → fill > ref, got {}", fill);
        assert!((bps - 1.0).abs() < 1e-9, "$1B tier 1.0 bps, got {}", bps);
        assert!((fill - 100.01).abs() < 1e-9, "fill=100.01, got {}", fill);
    }

    #[test]
    fn test_apply_fill_short_slippage_decreases_fill_price() {
        // R6-T2: sell at $1B tier → -1.0 bps → fill = 100 × (1 - 1/10000) = 99.99.
        // R6-T2：賣 + $1B tier → -1.0 bps → fill = 99.99。
        let cfg = crate::config::SlippageConfig::default();
        let bps = replay_slippage_bps_for_tif(&cfg, None, 2_000_000_000.0, false);
        assert!(bps < 0.0, "sell → negative bps, got {}", bps);
        let fill = apply_slippage_to_price(100.0, bps);
        assert!(fill < 100.0, "sell → fill < ref, got {}", fill);
        assert!((bps + 1.0).abs() < 1e-9, "$1B tier -1.0 bps, got {}", bps);
        assert!((fill - 99.99).abs() < 1e-9, "fill=99.99, got {}", fill);
    }

    #[test]
    fn test_apply_fill_zero_volume_24h_graceful_fallback() {
        // R6-T2: volume_24h <= 0.0 → 5 bps fallback (signed by direction).
        // PostOnly always 0. No NaN.
        // R6-T2：volume_24h <= 0.0 → 5 bps fallback（帶符號）。PostOnly 必 0。
        let cfg = crate::config::SlippageConfig::default();
        let bps_buy = replay_slippage_bps_for_tif(&cfg, None, 0.0, true);
        let bps_sell = replay_slippage_bps_for_tif(&cfg, None, 0.0, false);
        assert!(bps_buy.is_finite(), "buy bps must be finite, got {}", bps_buy);
        assert!(bps_sell.is_finite(), "sell bps must be finite, got {}", bps_sell);
        assert!((bps_buy - 5.0).abs() < 1e-9, "buy fallback +5.0 bps, got {}", bps_buy);
        assert!((bps_sell + 5.0).abs() < 1e-9, "sell fallback -5.0 bps, got {}", bps_sell);
        // Negative volume_24h same fallback (live `lookup_rate` <= 0 → default).
        // 負 volume_24h 同 fallback。
        let bps_neg = replay_slippage_bps_for_tif(&cfg, None, -1.0, true);
        assert!((bps_neg - 5.0).abs() < 1e-9, "negative vol → +5.0 bps, got {}", bps_neg);
        // PostOnly always 0 regardless of volume_24h. / PostOnly 必 0。
        let bps_po = replay_slippage_bps_for_tif(&cfg, Some(TimeInForce::PostOnly), 0.0, true);
        assert_eq!(bps_po, 0.0, "PostOnly slippage_bps must be 0");
    }

    #[test]
    fn test_apply_fill_simulated_fill_fee_field_populated() {
        // R6-T1 end-to-end via adapter path: SimulatedFill row carries fee > 0
        // (finite), fee_rate=DEFAULT_TAKER_FEE_RATE, liquidity_role='taker',
        // slippage_bps non-zero (no AM seeded; default 5 bps fallback).
        // R6-T1 端到端（adapter path）：SimulatedFill row fee > 0、
        // fee_rate=DEFAULT_TAKER_FEE_RATE、liquidity_role='taker'、
        // slippage_bps 非 0（無 AM seed；預設 5 bps fallback）。
        let pipeline = build_isolated_pipeline(
            ReplayProfile::Isolated,
            "exp_r6t1t2_taker".into(),
            "S3",
            r6_single_event(),
        )
        .expect("baseline build OK")
        .with_replay_fee_context(None, None, None);
        let (strategy_adapter, risk_adapter) = make_tif_adapters(None, true, None);
        let snapshot = make_snapshot_seed(10_000.0, Some(100.0), Vec::new());
        let mut wired = pipeline
            .with_adapter_pipeline(strategy_adapter, risk_adapter, snapshot)
            .expect("snapshot validation passes");
        wired.execute().expect("execute completes");
        let result = wired.into_result();
        assert_eq!(result.fills.len(), 1, "expected 1 accepted fill");
        let f0 = &result.fills[0];
        // R6-T1 assertions: fee + fee_rate + liquidity_role populated.
        // R6-T1 斷言：fee + fee_rate + liquidity_role 已填值。
        assert!(f0.fee.is_finite() && f0.fee > 0.0, "fee finite > 0, got {}", f0.fee);
        assert!((f0.fee_rate - DEFAULT_TAKER_FEE_RATE).abs() < 1e-12, "taker rate, got {}", f0.fee_rate);
        assert_eq!(f0.liquidity_role, "taker", "non-PostOnly → taker role");
        // R6-T2 assertions: market + None volume → +5 bps; price=100.05.
        // R6-T2 斷言：market + None volume → +5 bps；price=100.05。
        assert!((f0.slippage_bps - 5.0).abs() < 1e-9, "+5.0 bps, got {}", f0.slippage_bps);
        assert!((f0.price - 100.05).abs() < 1e-9, "price=100.05, got {}", f0.price);
        // Fee = 0.01 × 100.05 × 0.00055 = 0.000550275.
        let expected_fee = 0.01 * 100.05 * DEFAULT_TAKER_FEE_RATE;
        assert!((f0.fee - expected_fee).abs() < 1e-12, "fee={}, got {}", expected_fee, f0.fee);
    }

    #[test]
    fn test_apply_fill_postonly_path_emits_maker_zero_slippage() {
        // R6-T1+T2 cross-check: PostOnly → maker / 0 slippage / price == limit_price.
        // R6-T1+T2 交叉驗證：PostOnly → maker / 0 slippage / price == limit_price。
        let pipeline = build_isolated_pipeline(
            ReplayProfile::Isolated,
            "exp_r6t1t2_maker".into(),
            "S3",
            r6_single_event(),
        )
        .expect("baseline build OK")
        .with_replay_fee_context(None, None, None);
        // PostOnly + limit_price=99.5 (must be on book, below current 100).
        // PostOnly + limit_price=99.5（必掛單，低於現價 100）。
        let (strategy_adapter, risk_adapter) =
            make_tif_adapters(Some(TimeInForce::PostOnly), true, Some(99.5));
        let snapshot = make_snapshot_seed(10_000.0, Some(100.0), Vec::new());
        let mut wired = pipeline
            .with_adapter_pipeline(strategy_adapter, risk_adapter, snapshot)
            .expect("snapshot validation passes");
        wired.execute().expect("execute completes");
        let result = wired.into_result();
        assert_eq!(result.fills.len(), 1, "expected 1 accepted fill");
        let f0 = &result.fills[0];
        assert!((f0.fee_rate - DEFAULT_MAKER_FEE_RATE).abs() < 1e-12, "maker, got {}", f0.fee_rate);
        assert_eq!(f0.liquidity_role, "maker", "PostOnly → maker role");
        assert_eq!(f0.slippage_bps, 0.0, "PostOnly slippage_bps must be 0");
        assert!((f0.price - 99.5).abs() < 1e-9, "price=99.5, got {}", f0.price);
        // Fee = 0.01 × 99.5 × 0.0002 = 0.000199.
        let expected_fee = 0.01 * 99.5 * DEFAULT_MAKER_FEE_RATE;
        assert!((f0.fee - expected_fee).abs() < 1e-12, "fee={}, got {}", expected_fee, f0.fee);
    }

    #[test]
    fn test_apply_fill_synthetic_walker_emits_unknown_role_zero_fee() {
        // R6-T1+T2 backward compat: synthetic-walker → 0 fee / 'unknown' role
        // (proof_1/4/5 e2e byte-equal on `price` since slippage_bps=0).
        // R6-T1+T2 向後兼容：synthetic-walker → 0 fee / 'unknown' role
        // （proof_1/4/5 e2e 因 slippage_bps=0 在 `price` byte-equal）。
        let mut p = build_isolated_pipeline(
            ReplayProfile::Isolated,
            "exp_r6t1t2_synthetic".into(),
            "S3",
            synthetic_events(),
        )
        .unwrap();
        p.execute().unwrap();
        let r = p.into_result();
        assert_eq!(r.fills.len(), 2, "synthetic walker emits 1 fill per new symbol");
        for f in &r.fills {
            assert_eq!(f.fee, 0.0, "synthetic walker fee must be 0");
            assert_eq!(f.fee_rate, 0.0, "synthetic walker fee_rate must be 0");
            assert_eq!(f.slippage_bps, 0.0, "synthetic walker slippage_bps must be 0");
            assert_eq!(
                f.liquidity_role, "unknown",
                "synthetic walker liquidity_role must be 'unknown'"
            );
        }
    }

    #[test]
    fn test_apply_fill_ghost_row_records_zero_fee_with_intent_metadata() {
        // R6-T1 ghost-row contract: rejected intent → qty=0 → fee=0; but
        // fee_rate / slippage_bps / liquidity_role still reflect intent's
        // TIF + direction (counterfactual transparency).
        // R6-T1 ghost row 契約：被拒 intent → qty=0 → fee=0；fee_rate /
        // slippage_bps / liquidity_role 仍反映 TIF + 方向（counterfactual）。
        let pipeline = build_isolated_pipeline(
            ReplayProfile::Isolated,
            "exp_r6t1t2_ghost".into(),
            "S3",
            r6_single_event(),
        )
        .expect("baseline build OK")
        .with_replay_fee_context(None, None, None);
        let (strategy_adapter, risk_adapter) = make_tif_adapters(None, true, None);
        // Same-direction position triggers Gate 1.5 reject. / 同向倉觸 Gate 1.5。
        let snapshot = make_snapshot_seed(
            10_000.0,
            Some(100.0),
            vec![crate::replay::risk_adapter::ReplayPosition {
                symbol: "BTCUSDT".into(),
                is_long: true,
                qty: 0.5,
                entry_price: 100.0,
            }],
        );
        let mut wired = pipeline
            .with_adapter_pipeline(strategy_adapter, risk_adapter, snapshot)
            .expect("snapshot validation passes");
        wired.execute().expect("execute completes");
        let result = wired.into_result();
        let ghost = result
            .fills
            .iter()
            .find(|f| f.qty == 0.0 && f.symbol == "BTCUSDT")
            .expect("expected ghost fill on Gate 1.5 reject");
        assert_eq!(ghost.fee, 0.0, "ghost fee must be 0 (qty=0)");
        // fee_rate / liquidity_role / slippage_bps reflect counterfactual.
        // fee_rate / liquidity_role / slippage_bps 反映 counterfactual。
        assert!((ghost.fee_rate - DEFAULT_TAKER_FEE_RATE).abs() < 1e-12, "taker, got {}", ghost.fee_rate);
        assert_eq!(ghost.liquidity_role, "taker", "None TIF → taker");
        assert!((ghost.slippage_bps - 5.0).abs() < 1e-9, "+5.0 bps, got {}", ghost.slippage_bps);
    }
}
