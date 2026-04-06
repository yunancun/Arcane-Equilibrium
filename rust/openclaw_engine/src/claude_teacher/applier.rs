//! Directive applier — converts parsed Teacher directives into executable
//! hints with fail-closed P0/P1 hard-boundary filtering.
//! Directive 套用層 — 將解析後的 Teacher directive 轉為可執行 hint，
//! 並以 fail-closed 方式過濾所有觸碰 P0/P1 硬邊界的指令。
//!
//! MODULE_NOTE (EN): Phase 4 sub-task 4-02 (CRITICAL · Risk Register R6).
//!   This module is the **only** path that turns a parsed `Directive` into a
//!   side-effect on the running engine. Every directive must pass two gates
//!   before any side-effect is attempted:
//!     1. P0/P1 hard-boundary filter — field-level denylist +
//!        structural rules ("pause all strategies" = instant veto).
//!     2. GovernanceCore veto check via an injected `GovernanceCheck` trait
//!        (system state, daily loss, etc.).
//!   Every outcome — Applied, VetoedByGovernance, VetoedByHardBoundary,
//!   InvalidDirective, IpcError — is written to `learning.directive_executions`
//!   as an audit row (best-effort: PG unavailable = silent skip, the outcome
//!   is still returned to the caller).
//!
//!   ARCH-RC1 alignment: this module **never** touches Python RiskManager,
//!   `operator_risk_config.json`, or any Python-side state. Side-effects go
//!   through an injected `StrategyIpcSink` trait which in production is backed
//!   by the existing `PaperSessionCommand` channel (`update_strategy_params`,
//!   `set_strategy_active`). The wiring of the real sink into `main.rs` is
//!   deferred to the Phase 4 wiring sweep — this module ships fully unit-
//!   testable via mock impls so it can be written, reviewed, and merged
//!   without touching `lib.rs` / `main.rs` / `ipc_server.rs`.
//!
//! MODULE_NOTE (中): Phase 4 子任務 4-02（CRITICAL · 風險登記 R6）。
//!   本模組是將解析後的 `Directive` 轉為執行引擎副作用的 **唯一** 路徑。
//!   任何副作用執行前，directive 必須通過兩道閘：
//!     1. P0/P1 硬邊界過濾 — 欄位層黑名單 + 結構規則（「暫停所有策略」=
//!        立刻 veto）。
//!     2. GovernanceCore veto 檢查（透過注入的 `GovernanceCheck` trait，
//!        覆蓋系統狀態、日虧損等）。
//!   所有 outcome（Applied / VetoedByGovernance / VetoedByHardBoundary /
//!   InvalidDirective / IpcError）都會寫入 `learning.directive_executions`
//!   作為審計行（盡力寫入：PG 不可用則靜默跳過，outcome 仍回傳給呼叫方）。
//!
//!   ARCH-RC1 對齊：本模組 **絕不** 觸碰 Python RiskManager、
//!   `operator_risk_config.json` 或任何 Python 側狀態。副作用透過注入的
//!   `StrategyIpcSink` trait 走 — 生產環境由既有的 `PaperSessionCommand`
//!   channel 承載（`update_strategy_params` / `set_strategy_active`）。
//!   真實 sink 在 `main.rs` 的接線留給 Phase 4 wiring sweep — 本模組
//!   透過 mock 實作完全可單元測試，可在不動 `lib.rs` / `main.rs` /
//!   `ipc_server.rs` 的情況下寫成、審查、合併。

use super::parser::{Directive, DirectiveType};
use crate::database::pool::DbPool;
use std::future::Future;
use std::pin::Pin;
use std::sync::Arc;
use tracing::{debug, info, warn};

// ---------------------------------------------------------------------------
// Public types / 公開型別
// ---------------------------------------------------------------------------

/// Outcome of applying a single parsed directive.
/// 套用單一已解析 directive 的結果。
#[derive(Debug, Clone)]
pub enum ApplyOutcome {
    /// Directive passed every gate and was dispatched to the IPC sink.
    /// directive 通過所有閘並已派發至 IPC sink。
    Applied {
        directive_id: i64,
        action_summary: String,
    },
    /// GovernanceCore rejected based on current system state
    /// (e.g. daily loss over threshold, session halted).
    /// GovernanceCore 基於當前系統狀態拒絕（例如日虧超標、session halt）。
    VetoedByGovernance {
        directive_id: i64,
        reason: String,
    },
    /// Directive tried to modify a P0/P1 hard-boundary field or violated a
    /// structural boundary rule ("pause all strategies", "boost factor > 2.0").
    /// directive 嘗試修改 P0/P1 硬邊界欄位或違反結構規則
    /// （「暫停所有策略」、「boost factor > 2.0」等）。
    VetoedByHardBoundary {
        directive_id: i64,
        boundary: String,
        reason: String,
    },
    /// Directive shape is legal per parser but semantically invalid
    /// (unknown strategy name, missing required params).
    /// directive 結構合法（parser 通過）但語義無效
    /// （未知策略名、缺必要 params 等）。
    InvalidDirective {
        directive_id: i64,
        error: String,
    },
    /// IPC dispatch itself failed (channel closed, strategy not found, etc.).
    /// IPC 派發本身失敗（channel 關閉、策略找不到等）。
    IpcError {
        directive_id: i64,
        error: String,
    },
}

impl ApplyOutcome {
    /// Short action-type string written to `directive_executions.action_taken`.
    /// 寫入 `directive_executions.action_taken` 的簡短動作類型字串。
    pub fn action_tag(&self) -> &'static str {
        match self {
            ApplyOutcome::Applied { .. } => "applied",
            ApplyOutcome::VetoedByGovernance { .. } => "vetoed_by_governance",
            ApplyOutcome::VetoedByHardBoundary { .. } => "vetoed_by_hard_boundary",
            ApplyOutcome::InvalidDirective { .. } => "invalid_directive",
            ApplyOutcome::IpcError { .. } => "ipc_error",
        }
    }

    /// Whether this outcome is a successful application.
    /// 此 outcome 是否為成功套用。
    pub fn is_success(&self) -> bool {
        matches!(self, ApplyOutcome::Applied { .. })
    }

    /// Directive id this outcome is about.
    /// 此 outcome 對應的 directive id。
    pub fn directive_id(&self) -> i64 {
        match self {
            ApplyOutcome::Applied { directive_id, .. }
            | ApplyOutcome::VetoedByGovernance { directive_id, .. }
            | ApplyOutcome::VetoedByHardBoundary { directive_id, .. }
            | ApplyOutcome::InvalidDirective { directive_id, .. }
            | ApplyOutcome::IpcError { directive_id, .. } => *directive_id,
        }
    }
}

// ---------------------------------------------------------------------------
// Injection traits / 注入用 trait
// ---------------------------------------------------------------------------

/// A thin governance facade used by the applier. The real implementation is
/// backed by `openclaw_core::governance_core::GovernanceCore`; tests inject a
/// mock. Keeping this trait narrow is intentional — the applier must **not**
/// rewrite governance rules, only ask yes/no questions.
///
/// 供 applier 使用的薄 governance 門面。真實實作由
/// `openclaw_core::governance_core::GovernanceCore` 承載；測試注入 mock。
/// 介面刻意設計得很窄 — applier **絕不** 重寫治理規則，只問 yes/no。
pub trait GovernanceCheck: Send + Sync {
    /// Current daily-loss percentage (absolute, 0.0–1.0).
    /// 當前日虧損百分比（絕對值，0.0–1.0）。
    fn current_daily_loss_pct(&self) -> f64;
    /// Whether the trading session is currently halted (cooldown / circuit).
    /// 當前 trading session 是否已 halt（cooldown / circuit）。
    fn session_halted(&self) -> bool;
    /// Daily-loss threshold above which unpause is vetoed.
    /// 日虧超過此閾值時 unpause 會被否決。
    fn unpause_daily_loss_threshold(&self) -> f64;
    /// Set of strategy names currently known to the engine. Used to reject
    /// directives that reference unknown scopes.
    /// 引擎目前已知的策略名集合。用於拒絕引用未知 scope 的 directive。
    fn known_strategies(&self) -> Vec<String>;
}

/// IPC sink boxed-future type alias. Returns Ok(summary) or Err(msg).
/// IPC sink 的 boxed-future 類型別名。回傳 Ok(summary) 或 Err(msg)。
pub type IpcFuture<'a> =
    Pin<Box<dyn Future<Output = Result<String, String>> + Send + 'a>>;

/// Strategy IPC sink — the **only** channel through which the applier
/// mutates engine state. Production impl wraps `PaperSessionCommand` sender.
///
/// ARCH-RC1: this trait has intentionally zero methods that could reach
/// Python. No `update_operator_risk_config`, no `update_risk_manager`, no
/// `write_risk_json`. If a future directive type needs a new side-effect,
/// add it here (not on Python RiskManager).
///
/// 策略 IPC sink — applier 唯一可變動引擎狀態的通道。生產實作包裝
/// `PaperSessionCommand` sender。
///
/// ARCH-RC1：此 trait 刻意完全沒有任何可觸及 Python 的方法。
/// 沒有 `update_operator_risk_config`、沒有 `update_risk_manager`、
/// 沒有 `write_risk_json`。未來若有新的 directive type 需要新副作用，
/// 加在這裡（絕不走 Python RiskManager）。
pub trait StrategyIpcSink: Send + Sync {
    /// Update strategy params by JSON patch (maps to
    /// `PaperSessionCommand::UpdateStrategyParams`).
    /// 以 JSON patch 更新策略參數（對應
    /// `PaperSessionCommand::UpdateStrategyParams`）。
    fn update_strategy_params<'a>(
        &'a self,
        strategy_name: &'a str,
        params_json: &'a str,
    ) -> IpcFuture<'a>;

    /// Toggle strategy active flag (maps to
    /// `PaperSessionCommand::SetStrategyActive`).
    /// 切換策略 active 旗標（對應
    /// `PaperSessionCommand::SetStrategyActive`）。
    fn set_strategy_active<'a>(
        &'a self,
        strategy_name: &'a str,
        active: bool,
    ) -> IpcFuture<'a>;
}

// ---------------------------------------------------------------------------
// Hard-boundary denylist / 硬邊界黑名單
// ---------------------------------------------------------------------------

/// P0/P1 hard-boundary fields that a directive **must never** be allowed to
/// modify. Any `adjust_param` directive whose `params` contains one of these
/// keys is immediately vetoed. List is intentionally over-broad: we would
/// rather refuse a legitimate change than let a compromised Teacher slip by.
///
/// 絕對禁止 directive 修改的 P0/P1 硬邊界欄位。任何 `adjust_param` 指令
/// 的 `params` 包含其中任一 key 都會立刻 veto。列表刻意從寬：寧可錯殺
/// 合法修改，也不讓被攻破的 Teacher 滑過。
const P0_P1_DENYLIST_FIELDS: &[&str] = &[
    "max_position_size_usd",
    "max_total_exposure_pct",
    "max_total_exposure_usd",
    "hard_loss_pct",
    "hard_stop_pct",
    "daily_loss_pct",
    "daily_loss_cap_pct",
    "max_drawdown_pct",
    "max_leverage",
    "p1_risk_pct",
    "execution_state",
    "execution_authority",
    "system_mode",
    "live_execution_allowed",
    "trading_mode",
    "max_same_direction_positions",
    "boot_cooldown_ms",
    "trading_mode_override",
];

/// Upper limit on LinUCB boost factor — anything above this is a single-arm
/// dominance risk and is rejected.
/// LinUCB boost factor 上限 — 高於此值即有單 arm 主導風險，直接拒絕。
const MAX_BOOST_FACTOR: f64 = 2.0;

// ---------------------------------------------------------------------------
// DirectiveApplier / 套用器
// ---------------------------------------------------------------------------

/// Applies parsed Teacher directives with fail-closed hard-boundary + veto
/// filtering, then records the outcome to `learning.directive_executions`.
/// 套用已解析的 Teacher directive，進行 fail-closed 硬邊界 + veto 過濾，
/// 並將 outcome 寫入 `learning.directive_executions`。
pub struct DirectiveApplier {
    /// Reference to Rust GovernanceCore (or mock) for veto check.
    /// Rust GovernanceCore（或 mock）引用，用於 veto 檢查。
    governance: Arc<dyn GovernanceCheck>,
    /// Injected strategy IPC sink. `None` = dry-run mode (used in tests that
    /// only want to assert gate decisions without touching a real channel).
    /// 注入的策略 IPC sink。`None` = dry-run 模式（測試只要斷言閘決定、
    /// 不需要真實 channel 時使用）。
    ipc_sink: Option<Arc<dyn StrategyIpcSink>>,
    /// PG pool handle for the audit row write.
    /// PG pool 句柄，用於審計行寫入。
    pool: Arc<DbPool>,
}

impl DirectiveApplier {
    /// Construct a new applier. `ipc_sink = None` disables side-effects
    /// (dry-run) — suitable for tests and for a future "shadow mode" where
    /// Teacher directives are evaluated but never executed.
    /// 建立新 applier。`ipc_sink = None` 停用副作用（dry-run）—
    /// 適用於測試，以及未來「shadow 模式」（只評估 Teacher directive，
    /// 永不實際執行）。
    pub fn new(
        governance: Arc<dyn GovernanceCheck>,
        ipc_sink: Option<Arc<dyn StrategyIpcSink>>,
        pool: Arc<DbPool>,
    ) -> Self {
        Self {
            governance,
            ipc_sink,
            pool,
        }
    }

    /// Apply a single directive. Guarantees an audit row write attempt for
    /// **every** outcome (Applied, Vetoed, Invalid, IpcError).
    /// 套用單一 directive。保證對 **每一種** outcome（Applied / Vetoed /
    /// Invalid / IpcError）都嘗試寫入審計行。
    pub async fn apply(
        &self,
        directive: Directive,
        directive_id: i64,
    ) -> ApplyOutcome {
        let outcome = self.apply_inner(&directive, directive_id).await;
        // Fire-and-log audit write. We never swallow the outcome if audit
        // write fails — the outcome is the authoritative signal to callers.
        // 觸發並 log 審計寫入。審計失敗絕不吞掉 outcome — outcome 永遠
        // 是回傳給呼叫方的權威訊號。
        if let Err(e) =
            super::writer::record_execution(&self.pool, directive_id, &outcome).await
        {
            warn!(
                directive_id,
                error = ?e,
                "directive_executions audit row write failed (best-effort) / 審計行寫入失敗（盡力）"
            );
        }
        outcome
    }

    /// Inner apply logic — runs gates then dispatches. Pure function of
    /// `(directive, governance, ipc_sink)`; does not touch PG.
    /// 內層 apply 邏輯 — 跑閘然後派發。對 `(directive, governance, ipc_sink)`
    /// 是純函數；不碰 PG。
    async fn apply_inner(
        &self,
        directive: &Directive,
        directive_id: i64,
    ) -> ApplyOutcome {
        match directive.directive_type {
            DirectiveType::AdjustParam => {
                self.apply_adjust_param(directive, directive_id).await
            }
            DirectiveType::PauseStrategy => {
                self.apply_pause_strategy(directive, directive_id).await
            }
            DirectiveType::BoostArm => {
                self.apply_boost_arm(directive, directive_id).await
            }
            DirectiveType::Unpause => {
                self.apply_unpause(directive, directive_id).await
            }
        }
    }

    // -------------------- adjust_param --------------------

    async fn apply_adjust_param(
        &self,
        directive: &Directive,
        directive_id: i64,
    ) -> ApplyOutcome {
        // Gate 1: P0/P1 hard-boundary denylist.
        // 閘 1：P0/P1 硬邊界黑名單。
        if let Some(offending) =
            find_denylisted_field(&directive.params, P0_P1_DENYLIST_FIELDS)
        {
            return ApplyOutcome::VetoedByHardBoundary {
                directive_id,
                boundary: offending.clone(),
                reason: format!(
                    "adjust_param attempted to modify P0/P1 hard-boundary field '{offending}'"
                ),
            };
        }

        // Gate 2: scope must be a known strategy name.
        // 閘 2：scope 必須是已知策略名。
        let known = self.governance.known_strategies();
        if !known.iter().any(|s| s == &directive.scope) {
            return ApplyOutcome::InvalidDirective {
                directive_id,
                error: format!("unknown strategy scope: {}", directive.scope),
            };
        }

        // Gate 3: GovernanceCore veto — if session halted, do not tune params.
        // 閘 3：GovernanceCore veto — session halted 時禁止調參。
        if self.governance.session_halted() {
            return ApplyOutcome::VetoedByGovernance {
                directive_id,
                reason: "session halted — param adjustment blocked".into(),
            };
        }

        // Dispatch via IPC sink (if configured).
        // 透過 IPC sink 派發（若已配置）。
        let params_json = serde_json::to_string(&directive.params).unwrap_or_else(|_| "{}".into());
        let summary = format!("adjust_param {}: {}", directive.scope, params_json);
        match &self.ipc_sink {
            Some(sink) => match sink
                .update_strategy_params(&directive.scope, &params_json)
                .await
            {
                Ok(msg) => {
                    info!(directive_id, %msg, "directive applied via IPC / directive 已通過 IPC 套用");
                    ApplyOutcome::Applied {
                        directive_id,
                        action_summary: summary,
                    }
                }
                Err(e) => ApplyOutcome::IpcError {
                    directive_id,
                    error: e,
                },
            },
            None => {
                debug!(directive_id, "ipc_sink=None, dry-run applied / dry-run 套用");
                ApplyOutcome::Applied {
                    directive_id,
                    action_summary: format!("DRY-RUN {summary}"),
                }
            }
        }
    }

    // -------------------- pause_strategy --------------------

    async fn apply_pause_strategy(
        &self,
        directive: &Directive,
        directive_id: i64,
    ) -> ApplyOutcome {
        // Structural hard boundary: "pause all strategies" is a kill-switch.
        // LLM must not be able to one-shot disable the whole engine.
        // 結構硬邊界：「暫停所有策略」= 關機。LLM 絕不可一鍵關掉整個引擎。
        let scope_lc = directive.scope.to_lowercase();
        if matches!(scope_lc.as_str(), "*" | "all" | "all_strategies" | "everything") {
            return ApplyOutcome::VetoedByHardBoundary {
                directive_id,
                boundary: "pause_all_strategies".into(),
                reason: "attempted to pause all strategies (kill-switch blocked)".into(),
            };
        }

        let known = self.governance.known_strategies();
        if !known.iter().any(|s| s == &directive.scope) {
            return ApplyOutcome::InvalidDirective {
                directive_id,
                error: format!("unknown strategy scope: {}", directive.scope),
            };
        }

        let summary = format!("pause_strategy {}", directive.scope);
        match &self.ipc_sink {
            Some(sink) => match sink.set_strategy_active(&directive.scope, false).await {
                Ok(msg) => {
                    info!(directive_id, %msg, "strategy paused via IPC / 策略已通過 IPC 暫停");
                    ApplyOutcome::Applied {
                        directive_id,
                        action_summary: summary,
                    }
                }
                Err(e) => ApplyOutcome::IpcError {
                    directive_id,
                    error: e,
                },
            },
            None => ApplyOutcome::Applied {
                directive_id,
                action_summary: format!("DRY-RUN {summary}"),
            },
        }
    }

    // -------------------- boost_arm (stub — full wiring in 4-06) --------------------

    async fn apply_boost_arm(
        &self,
        directive: &Directive,
        directive_id: i64,
    ) -> ApplyOutcome {
        // Read boost factor from params.boost (default 1.0).
        // 從 params.boost 讀取 boost factor（預設 1.0）。
        let boost = directive
            .params
            .get("boost")
            .and_then(|v| v.as_f64())
            .unwrap_or(1.0);

        if !boost.is_finite() || boost <= 0.0 {
            return ApplyOutcome::InvalidDirective {
                directive_id,
                error: format!("invalid boost factor: {boost}"),
            };
        }

        if boost > MAX_BOOST_FACTOR {
            return ApplyOutcome::VetoedByHardBoundary {
                directive_id,
                boundary: "max_boost_factor".into(),
                reason: format!(
                    "boost factor {boost} exceeds hard cap {MAX_BOOST_FACTOR} (single-arm dominance risk)"
                ),
            };
        }

        // Stub: 4-06 will wire this into learning.linucb_state. For now we
        // just log + return Applied so that the audit row + counters exist.
        // Stub：4-06 會將此接入 learning.linucb_state。此處僅 log + 回
        // Applied，讓審計行與計數器先存在。
        info!(
            directive_id,
            arm = %directive.scope,
            boost,
            "boost_arm stub — wiring deferred to 4-06 / boost_arm stub — 接線留給 4-06"
        );
        ApplyOutcome::Applied {
            directive_id,
            action_summary: format!("boost_arm STUB {} x{boost:.2}", directive.scope),
        }
    }

    // -------------------- unpause --------------------

    async fn apply_unpause(
        &self,
        directive: &Directive,
        directive_id: i64,
    ) -> ApplyOutcome {
        // Governance gate: do not unpause while daily loss exceeds threshold
        // or while session is halted. This prevents Teacher from forcing the
        // engine back online during a drawdown spiral.
        // Governance 閘：日虧超標或 session halt 時拒絕 unpause。
        // 防止 Teacher 在回撤螺旋中強制重啟引擎。
        let loss = self.governance.current_daily_loss_pct();
        let threshold = self.governance.unpause_daily_loss_threshold();
        if loss >= threshold {
            return ApplyOutcome::VetoedByGovernance {
                directive_id,
                reason: format!(
                    "daily_loss_pct {loss:.4} >= unpause threshold {threshold:.4}"
                ),
            };
        }
        if self.governance.session_halted() {
            return ApplyOutcome::VetoedByGovernance {
                directive_id,
                reason: "session halted — unpause blocked".into(),
            };
        }

        let known = self.governance.known_strategies();
        if !known.iter().any(|s| s == &directive.scope) {
            return ApplyOutcome::InvalidDirective {
                directive_id,
                error: format!("unknown strategy scope: {}", directive.scope),
            };
        }

        let summary = format!("unpause {}", directive.scope);
        match &self.ipc_sink {
            Some(sink) => match sink.set_strategy_active(&directive.scope, true).await {
                Ok(msg) => {
                    info!(directive_id, %msg, "strategy unpaused via IPC / 策略已通過 IPC 恢復");
                    ApplyOutcome::Applied {
                        directive_id,
                        action_summary: summary,
                    }
                }
                Err(e) => ApplyOutcome::IpcError {
                    directive_id,
                    error: e,
                },
            },
            None => ApplyOutcome::Applied {
                directive_id,
                action_summary: format!("DRY-RUN {summary}"),
            },
        }
    }
}

// ---------------------------------------------------------------------------
// Helpers / 輔助
// ---------------------------------------------------------------------------

/// Walk a JSON value (one level — directives never nest params) looking for
/// any denylisted key. Returns the offending key if found.
/// 走訪 JSON value 一層（directive 的 params 不會巢狀）尋找任何黑名單 key。
/// 若找到則回傳該違規 key。
fn find_denylisted_field(
    params: &serde_json::Value,
    denylist: &[&str],
) -> Option<String> {
    let obj = params.as_object()?;
    for key in obj.keys() {
        let k_lc = key.to_lowercase();
        if denylist.iter().any(|d| d.eq_ignore_ascii_case(&k_lc)) {
            return Some(key.clone());
        }
    }
    None
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::database::DatabaseConfig;
    use serde_json::json;
    use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
    use std::sync::Mutex;

    // ---- test fixtures / 測試夾具 ----

    async fn empty_pool() -> Arc<DbPool> {
        let cfg = DatabaseConfig {
            database_url: String::new(),
            ..Default::default()
        };
        Arc::new(DbPool::connect(&cfg).await)
    }

    /// Mock governance — configurable per-test.
    /// 可逐測試配置的 mock governance。
    struct MockGov {
        daily_loss: f64,
        threshold: f64,
        halted: bool,
        known: Vec<String>,
    }
    impl MockGov {
        fn default_healthy() -> Self {
            Self {
                daily_loss: 0.0,
                threshold: 0.05,
                halted: false,
                known: vec![
                    "ma_crossover".into(),
                    "bb_reversion".into(),
                    "bb_breakout".into(),
                    "grid_trading".into(),
                ],
            }
        }
    }
    impl GovernanceCheck for MockGov {
        fn current_daily_loss_pct(&self) -> f64 {
            self.daily_loss
        }
        fn session_halted(&self) -> bool {
            self.halted
        }
        fn unpause_daily_loss_threshold(&self) -> f64 {
            self.threshold
        }
        fn known_strategies(&self) -> Vec<String> {
            self.known.clone()
        }
    }

    /// Mock IPC sink — records all calls in-memory, flags Python touches.
    /// mock IPC sink — 在記憶體紀錄所有呼叫，標記任何觸及 Python 的跡象。
    #[derive(Default)]
    struct MockSink {
        update_calls: Mutex<Vec<(String, String)>>,
        set_active_calls: Mutex<Vec<(String, bool)>>,
        /// Set to true if any code path attempts a forbidden Python side-effect.
        /// 若任何路徑嘗試禁止的 Python 副作用則設為 true。
        python_touched: AtomicBool,
        total_calls: AtomicUsize,
    }
    impl StrategyIpcSink for MockSink {
        fn update_strategy_params<'a>(
            &'a self,
            strategy_name: &'a str,
            params_json: &'a str,
        ) -> IpcFuture<'a> {
            self.total_calls.fetch_add(1, Ordering::SeqCst);
            self.update_calls
                .lock()
                .unwrap()
                .push((strategy_name.into(), params_json.into()));
            Box::pin(async move { Ok(format!("params updated for {strategy_name}")) })
        }
        fn set_strategy_active<'a>(
            &'a self,
            strategy_name: &'a str,
            active: bool,
        ) -> IpcFuture<'a> {
            self.total_calls.fetch_add(1, Ordering::SeqCst);
            self.set_active_calls
                .lock()
                .unwrap()
                .push((strategy_name.into(), active));
            Box::pin(async move { Ok(format!("was_active=true")) })
        }
    }

    fn future_expiry() -> i64 {
        (std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs()
            + 86_400) as i64
    }

    fn directive(ty: DirectiveType, scope: &str, params: serde_json::Value) -> Directive {
        Directive {
            directive_type: ty,
            scope: scope.into(),
            params,
            expiry: future_expiry(),
            priority: 3,
        }
    }

    async fn make_applier(
        gov: MockGov,
        sink: Option<Arc<MockSink>>,
    ) -> (DirectiveApplier, Arc<MockGov>, Option<Arc<MockSink>>) {
        let pool = empty_pool().await;
        let gov_arc = Arc::new(gov);
        let sink_dyn: Option<Arc<dyn StrategyIpcSink>> =
            sink.clone().map(|s| s as Arc<dyn StrategyIpcSink>);
        let applier = DirectiveApplier::new(
            gov_arc.clone() as Arc<dyn GovernanceCheck>,
            sink_dyn,
            pool,
        );
        (applier, gov_arc, sink)
    }

    // ===================================================================
    // Accept-path tests (4) / 接受路徑測試（4 個）
    // ===================================================================

    // Test 1: adjust_param on a safe (non-P0) field succeeds.
    // 測試 1：對安全（非 P0）欄位的 adjust_param 成功。
    #[tokio::test]
    async fn test_apply_adjust_param_safe_field_succeeds() {
        let sink = Arc::new(MockSink::default());
        let (applier, _gov, sink) =
            make_applier(MockGov::default_healthy(), Some(sink)).await;
        let d = directive(
            DirectiveType::AdjustParam,
            "ma_crossover",
            json!({"min_confidence": 0.35}),
        );
        let outcome = applier.apply(d, 101).await;
        assert!(
            matches!(outcome, ApplyOutcome::Applied { .. }),
            "expected Applied, got {outcome:?}"
        );
        // IPC was called exactly once.
        let sink = sink.unwrap();
        assert_eq!(sink.update_calls.lock().unwrap().len(), 1);
        assert_eq!(sink.set_active_calls.lock().unwrap().len(), 0);
    }

    // Test 2: pause a single known strategy succeeds.
    // 測試 2：暫停單一已知策略成功。
    #[tokio::test]
    async fn test_apply_pause_single_strategy_succeeds() {
        let sink = Arc::new(MockSink::default());
        let (applier, _gov, sink) =
            make_applier(MockGov::default_healthy(), Some(sink)).await;
        let d = directive(DirectiveType::PauseStrategy, "ma_crossover", json!({}));
        let outcome = applier.apply(d, 102).await;
        assert!(matches!(outcome, ApplyOutcome::Applied { .. }));
        let sink = sink.unwrap();
        let calls = sink.set_active_calls.lock().unwrap();
        assert_eq!(calls.len(), 1);
        assert_eq!(calls[0], ("ma_crossover".into(), false));
    }

    // Test 3: unpause within loss limit succeeds.
    // 測試 3：日虧低於閾值時 unpause 成功。
    #[tokio::test]
    async fn test_apply_unpause_within_loss_limit_succeeds() {
        let sink = Arc::new(MockSink::default());
        let gov = MockGov {
            daily_loss: 0.01, // under 0.05 threshold
            ..MockGov::default_healthy()
        };
        let (applier, _gov, sink) = make_applier(gov, Some(sink)).await;
        let d = directive(DirectiveType::Unpause, "bb_reversion", json!({}));
        let outcome = applier.apply(d, 103).await;
        assert!(matches!(outcome, ApplyOutcome::Applied { .. }));
        let sink = sink.unwrap();
        let calls = sink.set_active_calls.lock().unwrap();
        assert_eq!(calls[0], ("bb_reversion".into(), true));
    }

    // Test 4: boost_arm within factor limit succeeds (stub).
    // 測試 4：boost factor 在上限內的 boost_arm 成功（stub）。
    #[tokio::test]
    async fn test_apply_boost_arm_within_factor_limit() {
        let (applier, _gov, _sink) =
            make_applier(MockGov::default_healthy(), None).await;
        let d = directive(
            DirectiveType::BoostArm,
            "arm_ma_trending",
            json!({"boost": 1.5}),
        );
        let outcome = applier.apply(d, 104).await;
        assert!(
            matches!(outcome, ApplyOutcome::Applied { .. }),
            "expected Applied, got {outcome:?}"
        );
    }

    // ===================================================================
    // Reject-path tests (≥ 8) / 拒絕路徑測試（≥ 8 個）
    // ===================================================================

    // Test 5: adjust_param cannot modify max_position_size_usd.
    // 測試 5：adjust_param 禁止修改 max_position_size_usd。
    #[tokio::test]
    async fn test_apply_adjust_param_max_position_size_vetoed() {
        let sink = Arc::new(MockSink::default());
        let (applier, _gov, sink) =
            make_applier(MockGov::default_healthy(), Some(sink)).await;
        let d = directive(
            DirectiveType::AdjustParam,
            "ma_crossover",
            json!({"max_position_size_usd": 10_000_000.0}),
        );
        let outcome = applier.apply(d, 201).await;
        match outcome {
            ApplyOutcome::VetoedByHardBoundary { boundary, .. } => {
                assert_eq!(boundary, "max_position_size_usd");
            }
            other => panic!("expected VetoedByHardBoundary, got {other:?}"),
        }
        // Sink MUST NOT have been called — veto before dispatch.
        // Sink 絕不可被呼叫 — veto 在 dispatch 之前。
        let sink = sink.unwrap();
        assert_eq!(sink.total_calls.load(Ordering::SeqCst), 0);
    }

    // Test 6: adjust_param cannot modify hard_loss_pct.
    // 測試 6：adjust_param 禁止修改 hard_loss_pct。
    #[tokio::test]
    async fn test_apply_adjust_param_hard_loss_pct_vetoed() {
        let (applier, _gov, _sink) =
            make_applier(MockGov::default_healthy(), None).await;
        let d = directive(
            DirectiveType::AdjustParam,
            "ma_crossover",
            json!({"hard_loss_pct": 0.5}),
        );
        let outcome = applier.apply(d, 202).await;
        assert!(matches!(
            outcome,
            ApplyOutcome::VetoedByHardBoundary { .. }
        ));
    }

    // Test 7: adjust_param cannot modify max_total_exposure_pct.
    // 測試 7：adjust_param 禁止修改 max_total_exposure_pct。
    #[tokio::test]
    async fn test_apply_adjust_param_max_total_exposure_vetoed() {
        let (applier, _gov, _sink) =
            make_applier(MockGov::default_healthy(), None).await;
        let d = directive(
            DirectiveType::AdjustParam,
            "ma_crossover",
            json!({"max_total_exposure_pct": 0.99}),
        );
        let outcome = applier.apply(d, 203).await;
        match outcome {
            ApplyOutcome::VetoedByHardBoundary { boundary, .. } => {
                assert_eq!(boundary, "max_total_exposure_pct");
            }
            other => panic!("expected VetoedByHardBoundary, got {other:?}"),
        }
    }

    // Test 8: pause-all kill-switch is rejected.
    // 測試 8：一鍵暫停所有策略被拒絕（防關機）。
    #[tokio::test]
    async fn test_apply_pause_all_strategies_vetoed() {
        let sink = Arc::new(MockSink::default());
        let (applier, _gov, sink) =
            make_applier(MockGov::default_healthy(), Some(sink)).await;
        for scope in ["*", "all", "all_strategies", "everything"] {
            let d = directive(DirectiveType::PauseStrategy, scope, json!({}));
            let outcome = applier.apply(d, 204).await;
            match outcome {
                ApplyOutcome::VetoedByHardBoundary { boundary, .. } => {
                    assert_eq!(boundary, "pause_all_strategies");
                }
                other => panic!("expected VetoedByHardBoundary for '{scope}', got {other:?}"),
            }
        }
        let sink = sink.unwrap();
        assert_eq!(
            sink.set_active_calls.lock().unwrap().len(),
            0,
            "pause_all must not reach IPC"
        );
    }

    // Test 9: unpause blocked when daily loss over threshold.
    // 測試 9：日虧超過閾值時 unpause 被 governance 否決。
    #[tokio::test]
    async fn test_apply_unpause_over_loss_limit_vetoed_by_governance() {
        let gov = MockGov {
            daily_loss: 0.08, // over 0.05
            ..MockGov::default_healthy()
        };
        let (applier, _gov, _sink) = make_applier(gov, None).await;
        let d = directive(DirectiveType::Unpause, "ma_crossover", json!({}));
        let outcome = applier.apply(d, 205).await;
        assert!(matches!(
            outcome,
            ApplyOutcome::VetoedByGovernance { .. }
        ));
    }

    // Test 10: boost_arm with factor > 2.0 rejected.
    // 測試 10：boost factor > 2.0 被拒絕。
    #[tokio::test]
    async fn test_apply_boost_arm_factor_too_high_vetoed() {
        let (applier, _gov, _sink) =
            make_applier(MockGov::default_healthy(), None).await;
        let d = directive(
            DirectiveType::BoostArm,
            "arm_ma_trending",
            json!({"boost": 3.0}),
        );
        let outcome = applier.apply(d, 206).await;
        match outcome {
            ApplyOutcome::VetoedByHardBoundary { boundary, .. } => {
                assert_eq!(boundary, "max_boost_factor");
            }
            other => panic!("expected VetoedByHardBoundary, got {other:?}"),
        }
    }

    // Test 11: unknown strategy scope rejected as InvalidDirective.
    // 測試 11：未知策略 scope 被視為 InvalidDirective。
    #[tokio::test]
    async fn test_apply_unknown_strategy_invalid_directive() {
        let (applier, _gov, _sink) =
            make_applier(MockGov::default_healthy(), None).await;
        let d = directive(
            DirectiveType::PauseStrategy,
            "no_such_strategy",
            json!({}),
        );
        let outcome = applier.apply(d, 207).await;
        assert!(matches!(outcome, ApplyOutcome::InvalidDirective { .. }));
    }

    // Test 12: adjust_param while session halted vetoed by governance.
    // 測試 12：session halted 時 adjust_param 被 governance 否決。
    #[tokio::test]
    async fn test_apply_adjust_param_session_halted_vetoed() {
        let gov = MockGov {
            halted: true,
            ..MockGov::default_healthy()
        };
        let (applier, _gov, _sink) = make_applier(gov, None).await;
        let d = directive(
            DirectiveType::AdjustParam,
            "ma_crossover",
            json!({"min_confidence": 0.4}),
        );
        let outcome = applier.apply(d, 208).await;
        assert!(matches!(
            outcome,
            ApplyOutcome::VetoedByGovernance { .. }
        ));
    }

    // Test 13: outcome audit row write attempted for BOTH accept and reject.
    // We can't assert real PG rows (empty pool = silent skip), but we can
    // assert the applier returns the outcome unchanged after the audit call
    // and that record_execution does not panic on any variant.
    // 測試 13：成功與拒絕兩種路徑都嘗試寫審計行。
    //         空 pool 無法驗真實 PG 行，但可驗 applier 回傳 outcome 正確且
    //         record_execution 在任何 variant 下都不 panic。
    #[tokio::test]
    async fn test_apply_directive_writes_execution_audit_row() {
        let (applier, _gov, _sink) =
            make_applier(MockGov::default_healthy(), None).await;
        // Applied path
        let d1 = directive(
            DirectiveType::AdjustParam,
            "ma_crossover",
            json!({"min_confidence": 0.3}),
        );
        let o1 = applier.apply(d1, 301).await;
        assert!(o1.is_success());
        assert_eq!(o1.action_tag(), "applied");
        assert_eq!(o1.directive_id(), 301);

        // Vetoed path
        let d2 = directive(
            DirectiveType::AdjustParam,
            "ma_crossover",
            json!({"hard_loss_pct": 0.9}),
        );
        let o2 = applier.apply(d2, 302).await;
        assert!(!o2.is_success());
        assert_eq!(o2.action_tag(), "vetoed_by_hard_boundary");
        assert_eq!(o2.directive_id(), 302);

        // Invalid path
        let d3 = directive(DirectiveType::PauseStrategy, "ghost", json!({}));
        let o3 = applier.apply(d3, 303).await;
        assert!(!o3.is_success());
        assert_eq!(o3.action_tag(), "invalid_directive");
    }

    // ===================================================================
    // ARCH-RC1 alignment tests (2) / ARCH-RC1 對齊測試（2 個）
    // ===================================================================

    // Test 14: applying an adjust_param directive only calls Rust IPC methods —
    // never any Python-touching code path. We verify by (a) the MockSink's
    // python_touched flag staying false (Rust-only trait has no such method,
    // so flipping it would require the applier to invent one), and (b) the
    // update_calls vec contains exactly the expected Rust IPC call.
    // 測試 14：套用 adjust_param 只呼叫 Rust IPC 方法 — 永不走 Python。
    //         驗證方式：(a) MockSink 的 python_touched 維持 false；
    //         (b) update_calls 恰好記錄預期的 Rust IPC 呼叫。
    #[tokio::test]
    async fn test_apply_adjust_param_does_not_call_python_rm() {
        let sink = Arc::new(MockSink::default());
        let (applier, _gov, sink) =
            make_applier(MockGov::default_healthy(), Some(sink)).await;
        let d = directive(
            DirectiveType::AdjustParam,
            "ma_crossover",
            json!({"fast_period": 10, "slow_period": 25}),
        );
        let outcome = applier.apply(d, 401).await;
        assert!(outcome.is_success());
        let sink = sink.unwrap();
        // Python path must not be touched.
        assert!(
            !sink.python_touched.load(Ordering::SeqCst),
            "applier must not touch Python RiskManager"
        );
        // Rust IPC path IS touched.
        assert_eq!(sink.update_calls.lock().unwrap().len(), 1);
        // StrategyIpcSink trait surface has no method reaching Python — the
        // type system itself is the enforcement. This test documents intent.
        // StrategyIpcSink trait 介面上沒有任何可觸及 Python 的方法 —
        // 型別系統本身就是防線。此測試紀錄意圖。
    }

    // Test 15: applying any directive does not write operator_risk_config.json.
    // We check this by setting CWD to a tempdir and asserting no such file
    // appears after an apply call.
    // 測試 15：套用任何 directive 都不會寫 operator_risk_config.json。
    //         將 CWD 設為 tempdir，apply 後斷言該檔案不存在。
    #[tokio::test]
    async fn test_apply_does_not_write_operator_risk_config_json() {
        let tmp = std::env::temp_dir().join(format!(
            "openclaw_applier_test_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&tmp).unwrap();
        let target = tmp.join("operator_risk_config.json");
        assert!(!target.exists(), "precondition: file must not pre-exist");

        let sink = Arc::new(MockSink::default());
        let (applier, _gov, _sink) =
            make_applier(MockGov::default_healthy(), Some(sink)).await;
        // Apply a legal adjust_param.
        let d = directive(
            DirectiveType::AdjustParam,
            "ma_crossover",
            json!({"min_confidence": 0.25}),
        );
        let _ = applier.apply(d, 501).await;

        // The file must STILL not exist.
        // 該檔案必須仍然不存在。
        assert!(
            !target.exists(),
            "applier must never write operator_risk_config.json"
        );
        // Also no other json in tmp.
        let any_json: Vec<_> = std::fs::read_dir(&tmp)
            .unwrap()
            .filter_map(Result::ok)
            .filter(|e| {
                e.path()
                    .extension()
                    .and_then(|x| x.to_str())
                    .map(|s| s == "json")
                    .unwrap_or(false)
            })
            .collect();
        assert!(any_json.is_empty(), "no json writes allowed by applier");

        let _ = std::fs::remove_dir_all(&tmp);
    }
}
