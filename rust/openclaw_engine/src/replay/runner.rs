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

use crate::replay::fixture_loader::MarketEvent;
use crate::replay::forbidden_guard::{self, ForbiddenPathError};
use crate::replay::profile::ReplayProfile;

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
///
/// in-memory pipeline 發出的單一模擬 fill。
///
/// Field semantics (EN):
///   - `ts_ms`: timestamp from the source event (UTC ms).
///   - `symbol`: forwarded from event.
///   - `side`: simplified side enum (long/short string).
///   - `qty`: simulated quantity (deterministic; see `IsolatedPipeline::execute`).
///   - `price`: fill price = event close (we do not model slippage in T1).
///   - `evidence_source_tier`: hardcoded to fixture's tier label
///     ("calibrated_replay" / "synthetic_replay") so downstream reports
///     can audit the simulation lineage.
///
/// 欄位語意（中）：
///   - `ts_ms`: 來源 event 的時戳（UTC ms）。
///   - `symbol`: 從 event 轉發。
///   - `side`: 簡化的方向 enum（long/short 字串）。
///   - `qty`: 模擬數量（確定性；見 `IsolatedPipeline::execute`）。
///   - `price`: fill price = event close（T1 不模擬滑點）。
///   - `evidence_source_tier`: 硬編 = fixture tier label
///     （"calibrated_replay" / "synthetic_replay"），使下游 report 可 audit
///     模擬 lineage。
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct SimulatedFill {
    pub ts_ms: i64,
    pub symbol: String,
    pub side: String,
    pub qty: f64,
    pub price: f64,
    pub evidence_source_tier: String,
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
///
/// 欄位語意（中）：
///   - `manifest_id`: 來自 manifest body（回聲供 trace 關聯）。
///   - `status`：見上方 `ReplayStatus`。
///   - `execution_confidence`：V3 §12 #11 不變量；Isolated profile 永遠
///     為 `"none"`（S2/S3 smoke replay non-actionable）。
///   - `fills`：模擬 fill 的有序 vector。
///   - `pnl_summary`：粗略餘額算術。
///   - `diagnostics`：計數 + 最後 action label + 可選 abort 原因。
#[derive(Debug, Clone, Serialize)]
pub struct ReplayResult {
    pub manifest_id: String,
    pub status: ReplayStatus,
    pub execution_confidence: String,
    pub fills: Vec<SimulatedFill>,
    pub pnl_summary: PnlSummary,
    pub diagnostics: ReplayDiagnostics,
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
/// Lifecycle:
///   1. `IsolatedPipeline::new(profile, manifest_id, fixtures)` — validates
///      profile + initialises balance + position map.
///   2. `execute()` — walks fixtures, calls `enforce_at_runtime` per step,
///      emits `SimulatedFill` for the first event of each new symbol
///      (deterministic minimal IMPL; Wave 5 will replace with real strategy
///      replay logic via the future `replay_compatible` strategy module).
///   3. `into_result()` — finalises the `ReplayResult` (consumes self).
///
/// 生命週期：
///   1. `IsolatedPipeline::new(profile, manifest_id, fixtures)` — 驗 profile +
///      初始化 balance + position map。
///   2. `execute()` — 走訪 fixture，每步呼叫 `enforce_at_runtime`，每個新 symbol
///      首事件發出 `SimulatedFill`（確定性 minimal IMPL；Wave 5 將以未來
///      `replay_compatible` 策略 module 提供的真實策略 replay 邏輯取代）。
///   3. `into_result()` — finalise `ReplayResult`（消費 self）。
#[derive(Debug)]
pub struct IsolatedPipeline {
    profile: ReplayProfile,
    manifest_id: String,
    fixtures: Vec<MarketEvent>,
    fixture_tier_label: String,
    balance: f64,
    /// Map of symbol -> last simulated entry price (used to compute
    /// final-mark PnL). One position per symbol; T1 does not net out.
    /// symbol -> 最近模擬入場價（用於算 final-mark PnL）。每 symbol 一倉；
    /// T1 不 netting。
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
            // mark-to-market via `balance` arithmetic. T1 deliberately does
            // NOT model: order book, slippage, latency, partial fills, fee
            // model — those land in Wave 5 P3a.
            // Minimal IMPL — 每個 symbol 首見時發出一筆模擬入場 fill；後續
            // event 透過 `balance` 算術更新倉位 mark-to-market。T1 刻意不模擬：
            // order book、滑點、延遲、部分成交、費率模型 — 那些於 Wave 5 P3a
            // 落地。
            if !self.positions.contains_key(&event.symbol) {
                let entry_price = event.close;
                // Deterministic synthetic qty: 1.0 lot per new symbol. Real
                // sizing belongs to a `replay_compatible` strategy refactor
                // out of T1 scope.
                // 確定性合成數量：每新 symbol 1.0 lot。真實 sizing 屬
                // `replay_compatible` 策略重構，非 T1 範圍。
                let qty = 1.0_f64;
                self.positions.insert(event.symbol.clone(), entry_price);
                self.fills.push(SimulatedFill {
                    ts_ms: event.ts_ms,
                    symbol: event.symbol.clone(),
                    side: "long".to_string(),
                    qty,
                    price: entry_price,
                    evidence_source_tier: self.fixture_tier_label.clone(),
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
        let net_pnl = self.balance - DEFAULT_STARTING_BALANCE;
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

        ReplayResult {
            manifest_id: self.manifest_id,
            execution_confidence: "none".to_string(),
            pnl_summary: PnlSummary {
                events_processed: self.fixtures.len(),
                fills_emitted: self.fills.len(),
                starting_balance: DEFAULT_STARTING_BALANCE,
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
        }
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
        let err = build_isolated_pipeline(
            ReplayProfile::Live,
            "exp_1".into(),
            "S3",
            synthetic_events(),
        )
        .unwrap_err();
        assert!(matches!(
            err,
            ReplayError::NonIsolatedProfile { found: ReplayProfile::Live }
        ));
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
}
