//! G1-06 — Drawdown auto-revoke for Live authorization.
//! G1-06 — 提款回撤自動撤銷 Live 授權。
//!
//! MODULE_NOTE (EN): Implements Root Principle #5 (生存 > 利潤) and #6
//!   (失敗默認收縮): when the Live pipeline triggers a drawdown-driven
//!   `RiskAction::HaltSession`, do not just close positions and pause —
//!   *also* delete `authorization.json` so the Live session cannot be
//!   silently un-paused without operator re-approval. The
//!   `live_auth_watcher` (5s poll) will detect the missing file within
//!   5 seconds and tear down the Live pipeline slot via the existing
//!   `live_authorization::AuthError::FileMissing` → teardown path.
//!
//!   Design choices:
//!     * **Pure decision fn separated from side-effect fn.** `should_revoke`
//!       takes scalar inputs and returns `Option<RevokeDecision>`. Wiring
//!       site (Step 6 HaltSession arm) calls the pure fn first, then
//!       `revoke_live_authorization` if decision is Some. Mirrors
//!       reconciler escalation/dispatch split (`evaluate_actions` /
//!       `dispatch_action`).
//!     * **Live-only.** Demo / Paper drawdowns still produce `HaltSession`
//!       and close all positions — they just do not touch `authorization.json`
//!       (which has no meaning for Demo / Paper). Pure fn returns `None`
//!       for non-Live kinds.
//!     * **Reuse existing drawdown computation.** `paper_state.drawdown_pct()`
//!       already computes `(peak - balance) / peak * 100` from a peak that
//!       survives crash + checkpoint restore (P1-5 A2). We do not duplicate
//!       the math here; we just consume the value Step 6 already computed
//!       and the threshold already in `RiskConfig.limits.session_drawdown_max_pct`.
//!     * **Reuse existing teardown path.** Rather than plumb a new cancel
//!       token, we delete `authorization.json` and let the existing
//!       `live_auth_watcher` poll detect it within ≤5s and tear the Live
//!       slot via `PipelineSlot::teardown()`. That path is already battle-
//!       tested and ensures Demo / Paper continue running.
//!     * **Idempotent.** If the file is already missing (operator already
//!       revoked, or this is the second consecutive HaltSession in the
//!       window), `revoke_live_authorization` returns
//!       `RevokeOutcome::AlreadyRevoked` and logs at debug level, not
//!       warn. The dispatch site treats both Removed and AlreadyRevoked
//!       as success.
//!     * **Fail-soft on I/O error.** A failed `remove_file` is logged as
//!       `warn` but does not panic and does not block the existing
//!       HaltSession close-all path. Operator alerting on the
//!       `drawdown_revoke_io_error` log line is the catch.
//!
//! MODULE_NOTE (中)：實作根原則 #5「生存 > 利潤」與 #6「失敗默認收縮」：
//!   Live 管線因 drawdown 觸發 `RiskAction::HaltSession` 時，不只關倉與暫停，
//!   還要刪除 `authorization.json`，讓 Live session 不能被無 operator 再批准
//!   就靜默 unpause。`live_auth_watcher`（5s 輪詢）會在 ≤5s 內偵測到檔案缺失
//!   並透過既有 `AuthError::FileMissing` → teardown 路徑拆除 Live 槽位。
//!
//!   設計要點：
//!     * 純決策 fn 與副作用 fn 分離（鏡像 reconciler `evaluate_actions` /
//!       `dispatch_action` 模式）。
//!     * Live-only — Demo/Paper drawdown 仍走 HaltSession 全平倉，但不動
//!       `authorization.json`（對 Demo/Paper 無意義）。
//!     * 重用既有 drawdown 計算（`paper_state.drawdown_pct()`）與既有閾值
//!       （`RiskConfig.limits.session_drawdown_max_pct`），不重新發明。
//!     * 重用既有 teardown 路徑（`live_auth_watcher` poll → `PipelineSlot::teardown()`），
//!       不另外接 cancel_token，避免 Demo/Paper 被誤殺。
//!     * 冪等 — 檔案已不在則回 `AlreadyRevoked`，視為成功。
//!     * Fail-soft — I/O 失敗只 warn，不 panic、不阻塞既有關倉路徑。

use crate::live_authorization::authorization_path;
use crate::tick_pipeline::PipelineKind;
use std::path::PathBuf;
use tracing::{debug, info, warn};

/// Marker prefix that `risk_checks::check_position_on_tick` emits in the
/// `HaltSession` reason string when the trigger is session drawdown
/// (priority 7 in the 9-check ladder). Used to distinguish drawdown-driven
/// halts from `DAILY LOSS` halts (priority 9), since the latter is a
/// daily-window failure that operator may want to clear with `Resume`
/// without forcing a full re-auth.
///
/// Operator policy (2026-04-24): drawdown halts force re-auth (#5/#6),
/// daily-loss halts do not (operator already explicitly opted into the
/// daily limit and can resume same-day after review). If this policy
/// changes, just add `DAILY_LOSS_REASON_PREFIX` and check both.
///
/// `HaltSession` reason 中 drawdown 觸發的字首，用於與 `DAILY LOSS` 區分。
/// 當前政策：drawdown 強制再授權，daily loss 不必（operator 已主動設置 daily 上限）。
pub const DRAWDOWN_REASON_PREFIX: &str = "SESSION DRAWDOWN";

/// Decision returned by [`should_revoke`]. Carries the reason string for
/// downstream audit logging.
/// `should_revoke` 回傳的決策；附帶下游審計記錄用的原因字串。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RevokeDecision {
    /// The full HaltSession reason string (e.g. `"SESSION DRAWDOWN: 12.34% >= 10.00%"`).
    /// 完整的 HaltSession 原因字串。
    pub reason: String,
}

/// Outcome of a [`revoke_live_authorization`] call.
/// `revoke_live_authorization` 的執行結果。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RevokeOutcome {
    /// `authorization.json` existed and was removed. Live pipeline will be
    /// torn down by `live_auth_watcher` within ≤5 seconds.
    /// `authorization.json` 已存在並被刪除；Live 管線將於 ≤5s 內由 watcher 拆除。
    Removed { path: PathBuf },
    /// `authorization.json` did not exist (operator already revoked, or
    /// this is a duplicate trigger in the same window). Treated as success.
    /// `authorization.json` 不存在；視為成功（已被 operator 撤銷或同窗口重複觸發）。
    AlreadyRevoked { path: PathBuf },
    /// `authorization_path()` could not resolve (no `OPENCLAW_SECRETS_DIR`
    /// and no `HOME` / `USERPROFILE`). Programming error in deployment;
    /// the close-all path still runs, but no revoke is possible.
    /// 路徑無法解析（環境變數缺失）。視為部署錯誤，仍執行關倉但無法撤銷。
    PathUnresolved,
    /// Filesystem error while removing the file. Logged as warn; does not
    /// block the close-all path.
    /// 刪檔 I/O 錯誤，warn log，不阻塞關倉。
    IoError { path: PathBuf, reason: String },
}

impl RevokeOutcome {
    /// Did the revoke achieve its intent (file is no longer present)?
    /// 撤銷是否達到預期（檔案不再存在）？
    pub fn succeeded(&self) -> bool {
        matches!(self, Self::Removed { .. } | Self::AlreadyRevoked { .. })
    }

    /// Short kv-safe label for structured log fields and audit payloads.
    /// 結構化日誌與審計用的短標籤。
    pub fn kind_str(&self) -> &'static str {
        match self {
            Self::Removed { .. } => "removed",
            Self::AlreadyRevoked { .. } => "already_revoked",
            Self::PathUnresolved => "path_unresolved",
            Self::IoError { .. } => "io_error",
        }
    }
}

/// Pure decision function — given a HaltSession reason and the pipeline
/// kind, decide whether to revoke `authorization.json`.
///
/// Returns `Some(RevokeDecision)` only when:
///   * `pipeline_kind == PipelineKind::Live`, AND
///   * `halt_reason` starts with [`DRAWDOWN_REASON_PREFIX`]
///
/// Demo / Paper kinds always return `None` — drawdown halts on those
/// engines close positions but do not affect `authorization.json` (which
/// has no meaning for them). Daily-loss-driven halts also return `None`
/// per current operator policy (see [`DRAWDOWN_REASON_PREFIX`] doc).
///
/// 純決策函數：給定 HaltSession reason 與管線類型，決定是否撤銷
/// `authorization.json`。僅 Live 管線且 reason 以 `SESSION DRAWDOWN` 開頭
/// 才回傳 `Some`。Demo/Paper 與 daily loss 一律回 `None`。
pub fn should_revoke(halt_reason: &str, pipeline_kind: PipelineKind) -> Option<RevokeDecision> {
    if pipeline_kind != PipelineKind::Live {
        return None;
    }
    if !halt_reason.starts_with(DRAWDOWN_REASON_PREFIX) {
        return None;
    }
    Some(RevokeDecision {
        reason: halt_reason.to_string(),
    })
}

/// Side-effect function — delete `authorization.json` if present.
///
/// Idempotent: returns `AlreadyRevoked` if the file is already absent.
/// Logs at info level on Removed (rare event, important audit trail),
/// debug on AlreadyRevoked (expected during repeated triggers), warn on
/// IoError (operator alerting hook).
///
/// Path resolution mirrors [`authorization_path`]: respects
/// `OPENCLAW_SECRETS_DIR`, falls back to `$HOME/BybitOpenClaw/secrets/...`.
///
/// 副作用函數：刪除 `authorization.json`。冪等，多次呼叫安全。Removed 走
/// info、AlreadyRevoked 走 debug、IoError 走 warn（operator 告警鉤點）。
/// 路徑解析與 `authorization_path` 一致。
pub fn revoke_live_authorization(decision: &RevokeDecision) -> RevokeOutcome {
    let path = match authorization_path() {
        Some(p) => p,
        None => {
            warn!(
                reason = %decision.reason,
                "drawdown_revoke: authorization_path unresolvable (env vars missing) \
                 / 提款撤銷：authorization 路徑無法解析（環境變數缺失）"
            );
            return RevokeOutcome::PathUnresolved;
        }
    };
    if !path.exists() {
        debug!(
            path = %path.display(),
            reason = %decision.reason,
            "drawdown_revoke: authorization.json already absent (idempotent no-op) \
             / 提款撤銷：authorization.json 已不存在（冪等空操作）"
        );
        return RevokeOutcome::AlreadyRevoked { path };
    }
    match std::fs::remove_file(&path) {
        Ok(()) => {
            info!(
                path = %path.display(),
                reason = %decision.reason,
                "DRAWDOWN AUTO-REVOKE: deleted Live authorization.json — \
                 live_auth_watcher will tear down Live slot within ≤5s. \
                 Operator: re-approve via POST /api/v1/live/auth/renew. \
                 / 提款自動撤銷：已刪除 Live authorization.json，watcher 將於 ≤5s 內拆除 Live 槽位。"
            );
            RevokeOutcome::Removed { path }
        }
        Err(e) => {
            // I/O failure (permission denied, disk error, etc). Do NOT panic
            // — Step 6 close-all loop still needs to run. Operator alerting
            // is via the `drawdown_revoke_io_error` log kv pair.
            //
            // I/O 失敗（權限/磁碟錯誤等）。不可 panic — Step 6 全平倉仍需執行。
            // operator 透過 `drawdown_revoke_io_error` log 告警。
            let reason = e.to_string();
            warn!(
                path = %path.display(),
                halt_reason = %decision.reason,
                io_error = %reason,
                "drawdown_revoke_io_error: failed to delete authorization.json \
                 (close-all path still runs; operator must manually revoke) \
                 / 提款撤銷 I/O 失敗（關倉仍執行；operator 須手動撤銷）"
            );
            RevokeOutcome::IoError { path, reason }
        }
    }
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex as StdMutex;

    // Tests that mutate `OPENCLAW_SECRETS_DIR` must serialize to avoid
    // colliding with each other and with `live_authorization` tests in the
    // same binary. Pattern lifted from `live_auth_watcher::tests::ENV_GUARD`.
    //
    // 改動 OPENCLAW_SECRETS_DIR 的測試串行化，避免互相污染。
    static ENV_GUARD: StdMutex<()> = StdMutex::new(());

    // ── should_revoke (pure) ───────────────────────────────────────────

    /// EN: Live + SESSION DRAWDOWN reason → revoke.
    /// 中文：Live + SESSION DRAWDOWN reason → 撤銷。
    #[test]
    fn live_drawdown_triggers_revoke() {
        let decision = should_revoke(
            "SESSION DRAWDOWN: 12.34% >= 10.00%",
            PipelineKind::Live,
        );
        assert!(decision.is_some());
        assert_eq!(
            decision.unwrap().reason,
            "SESSION DRAWDOWN: 12.34% >= 10.00%"
        );
    }

    /// EN: Demo pipeline + SESSION DRAWDOWN → no revoke (Demo has no live auth).
    /// 中文：Demo + SESSION DRAWDOWN → 不撤銷（Demo 無 live auth）。
    #[test]
    fn demo_drawdown_does_not_revoke() {
        assert!(should_revoke(
            "SESSION DRAWDOWN: 25.00% >= 25.00%",
            PipelineKind::Demo,
        )
        .is_none());
    }

    /// EN: Paper pipeline + SESSION DRAWDOWN → no revoke.
    /// 中文：Paper + SESSION DRAWDOWN → 不撤銷。
    #[test]
    fn paper_drawdown_does_not_revoke() {
        assert!(should_revoke(
            "SESSION DRAWDOWN: 50.00% >= 30.00%",
            PipelineKind::Paper,
        )
        .is_none());
    }

    /// EN: Live + DAILY LOSS reason → no revoke (different policy).
    /// 中文：Live + DAILY LOSS → 不撤銷（不同政策）。
    #[test]
    fn live_daily_loss_does_not_revoke() {
        assert!(should_revoke(
            "DAILY LOSS: 5.00% >= 5.00%",
            PipelineKind::Live,
        )
        .is_none());
    }

    /// EN: Live + non-halt-style reason → no revoke. Defensive: caller
    /// should only pass HaltSession reasons, but pure fn must be robust to
    /// stray strings (e.g. ClosePosition reasons that share prefixes).
    /// 中文：Live + 非 halt 風格 reason → 不撤銷。防禦性：純 fn 對隨機字串安全。
    #[test]
    fn unrelated_reason_does_not_revoke() {
        for reason in &[
            "HARD STOP: pnl -25.00% <= -20.00%",
            "TRAILING STOP: peak 5% - current 2% = 3%",
            "",
            "session drawdown: lowercase does not match",
            " SESSION DRAWDOWN: leading space",
        ] {
            assert!(
                should_revoke(reason, PipelineKind::Live).is_none(),
                "unexpected revoke on reason {:?}",
                reason
            );
        }
    }

    // ── revoke_live_authorization (side-effect) ────────────────────────

    /// EN: When the file exists, revoke deletes it and returns Removed.
    /// 中文：檔案存在時，刪除並回傳 Removed。
    #[test]
    fn revoke_removes_existing_file() {
        let _g = ENV_GUARD.lock().unwrap_or_else(|e| e.into_inner());
        let tmp = tempfile::tempdir().unwrap();
        let prev_secrets = std::env::var("OPENCLAW_SECRETS_DIR").ok();
        std::env::set_var("OPENCLAW_SECRETS_DIR", tmp.path());
        // Seed an authorization.json under live/.
        let live_dir = tmp.path().join("live");
        std::fs::create_dir_all(&live_dir).unwrap();
        let path = live_dir.join("authorization.json");
        std::fs::write(&path, "{\"version\":1}").unwrap();

        let decision = RevokeDecision {
            reason: "SESSION DRAWDOWN: 11% >= 10%".into(),
        };
        let out = revoke_live_authorization(&decision);

        // Restore env BEFORE asserts so a failure does not pollute later tests.
        match prev_secrets {
            Some(v) => std::env::set_var("OPENCLAW_SECRETS_DIR", v),
            None => std::env::remove_var("OPENCLAW_SECRETS_DIR"),
        }

        match out {
            RevokeOutcome::Removed { path: p } => {
                assert!(!p.exists(), "file must be gone after Removed");
                assert!(p.ends_with("live/authorization.json"));
            }
            other => panic!("expected Removed, got {:?}", other),
        }
    }

    /// EN: When the file is missing, revoke returns AlreadyRevoked (idempotent).
    /// 中文：檔案不存在時回傳 AlreadyRevoked（冪等）。
    #[test]
    fn revoke_is_idempotent_when_file_missing() {
        let _g = ENV_GUARD.lock().unwrap_or_else(|e| e.into_inner());
        let tmp = tempfile::tempdir().unwrap();
        let prev_secrets = std::env::var("OPENCLAW_SECRETS_DIR").ok();
        std::env::set_var("OPENCLAW_SECRETS_DIR", tmp.path());
        // Do NOT create the file.

        let decision = RevokeDecision {
            reason: "SESSION DRAWDOWN: 99% >= 10%".into(),
        };
        let out = revoke_live_authorization(&decision);

        match prev_secrets {
            Some(v) => std::env::set_var("OPENCLAW_SECRETS_DIR", v),
            None => std::env::remove_var("OPENCLAW_SECRETS_DIR"),
        }

        assert!(matches!(out, RevokeOutcome::AlreadyRevoked { .. }));
        assert!(out.succeeded(), "AlreadyRevoked must count as success");
    }

    /// EN: A second revoke call right after a successful one returns AlreadyRevoked.
    /// 中文：第二次呼叫回 AlreadyRevoked，確認冪等行為跨呼叫一致。
    #[test]
    fn revoke_twice_is_safe() {
        let _g = ENV_GUARD.lock().unwrap_or_else(|e| e.into_inner());
        let tmp = tempfile::tempdir().unwrap();
        let prev_secrets = std::env::var("OPENCLAW_SECRETS_DIR").ok();
        std::env::set_var("OPENCLAW_SECRETS_DIR", tmp.path());
        let live_dir = tmp.path().join("live");
        std::fs::create_dir_all(&live_dir).unwrap();
        std::fs::write(live_dir.join("authorization.json"), "{}").unwrap();

        let decision = RevokeDecision {
            reason: "SESSION DRAWDOWN".into(),
        };
        let first = revoke_live_authorization(&decision);
        let second = revoke_live_authorization(&decision);

        match prev_secrets {
            Some(v) => std::env::set_var("OPENCLAW_SECRETS_DIR", v),
            None => std::env::remove_var("OPENCLAW_SECRETS_DIR"),
        }

        assert!(matches!(first, RevokeOutcome::Removed { .. }));
        assert!(matches!(second, RevokeOutcome::AlreadyRevoked { .. }));
    }

    // ── RevokeOutcome helpers ──────────────────────────────────────────

    /// EN: succeeded() is true for Removed + AlreadyRevoked, false for failure modes.
    /// 中文：succeeded() 對 Removed + AlreadyRevoked 為 true，失敗模式為 false。
    #[test]
    fn outcome_succeeded_classification() {
        assert!(RevokeOutcome::Removed { path: PathBuf::from("/x") }.succeeded());
        assert!(RevokeOutcome::AlreadyRevoked { path: PathBuf::from("/x") }.succeeded());
        assert!(!RevokeOutcome::PathUnresolved.succeeded());
        assert!(!RevokeOutcome::IoError {
            path: PathBuf::from("/x"),
            reason: "perm".into()
        }
        .succeeded());
    }

    /// EN: kind_str labels are stable — alert rules depend on them.
    /// 中文：kind_str 標籤穩定 — 告警規則依賴。
    #[test]
    fn outcome_kind_labels_are_stable() {
        assert_eq!(
            RevokeOutcome::Removed { path: PathBuf::from("/x") }.kind_str(),
            "removed"
        );
        assert_eq!(
            RevokeOutcome::AlreadyRevoked { path: PathBuf::from("/x") }.kind_str(),
            "already_revoked"
        );
        assert_eq!(RevokeOutcome::PathUnresolved.kind_str(), "path_unresolved");
        assert_eq!(
            RevokeOutcome::IoError {
                path: PathBuf::from("/x"),
                reason: "x".into()
            }
            .kind_str(),
            "io_error"
        );
    }
}
