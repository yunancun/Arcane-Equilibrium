//! Supervised-live SM 狀態與事件型別。
//!
//! MODULE_NOTE
//! 模塊用途：定義 LG-3 supervised-live 7-state 狀態機的核心型別 ——
//!   `SmState`（7 態）、`SmEvent`（驅動 transition 的事件）、
//!   `SmAction`（17 個 audit action enum）、`IllegalTransitionError`，
//!   以及 audit-action → projected-state 反向映射（reconciler 對賬用）。
//! 主要型別/函數：SmState / SmEvent / SmAction / IllegalTransitionError /
//!   audit_action_to_projected_state。
//! 依賴：serde（Python mirror 與 audit row 序列化對齊）。
//! 硬邊界：
//!   - `audit_action_to_projected_state` 必與 spec v2 §2.2A 反向映射表 1:1，
//!     且 Python mirror `supervised_live_state.py` 必同 dict（E2 等價性檢查）。
//!   - unknown audit action 回 None → reconciler 走 fail-closed（WARN，不更新 state）。
//!   - `illegal_transition_attempted` 回 None：非法嘗試只記 forensic，不改 state。

use serde::{Deserialize, Serialize};
use std::fmt;

/// Supervised-live 7-state（spec v2 §1）。
///
/// 為什麼用獨立 enum：supervised-live session 的 control-plane 狀態必須是
/// 集中、可序列化、可被 5 SoT 對賬的單一型別；Python mirror 以同名字串對齊。
/// CLOSED 為 TERMINAL，任何後續事件皆非法（除冪等的重複 close）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SmState {
    /// Python-only 草稿態；operator 準備 request payload，無 DB row。
    Draft,
    /// request 已註冊 DB；等 operator 審批；尚無任何 live 動作。
    Registered,
    /// operator 已批准 + 已寫 authorization.json；Rust LiveAuthWatcher 尚未觀察到檔。
    ActivePreAuth,
    /// Rust 已授權 + Live pipeline 已 spawn；尚未綁定任何 Decision Lease。
    ActiveAuthed,
    /// 已綁定 ≥1 lease；live 訂單可下；effective limit = min(P1, override, strategy)。
    ActiveTrading,
    /// drawdown 觸發 revoke 中的過渡態；revoke 完成後轉 CLOSED。
    DrawdownPause,
    /// TERMINAL：正常結束 / kill / drawdown halt / reconcile 強推。無後續 transition。
    Closed,
}

impl SmState {
    /// 是否為 TERMINAL 態（CLOSED）。
    ///
    /// 為什麼需要：transition 表對「任一非 TERMINAL 態」收 kill/duration/reconcile
    /// 事件，需用此判斷避免對已 CLOSED session 重複施加副作用。
    pub fn is_terminal(self) -> bool {
        matches!(self, SmState::Closed)
    }

    /// canonical 字串表示（與 Python mirror + audit dst_state 欄位對齊）。
    pub fn as_str(self) -> &'static str {
        match self {
            SmState::Draft => "DRAFT",
            SmState::Registered => "REGISTERED",
            SmState::ActivePreAuth => "ACTIVE_PRE_AUTH",
            SmState::ActiveAuthed => "ACTIVE_AUTHED",
            SmState::ActiveTrading => "ACTIVE_TRADING",
            SmState::DrawdownPause => "DRAWDOWN_PAUSE",
            SmState::Closed => "CLOSED",
        }
    }
}

impl fmt::Display for SmState {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// 驅動 supervised-live SM transition 的事件（spec v2 §1.2）。
///
/// 為什麼把事件設成 enum 而非自由字串：transition 表 key = (state, event_kind)
/// 必須是封閉集合，編譯期窮舉才能保證「§1.2 16 條合法 transition 全覆蓋」且
/// 非法組合在查表時被 fail-closed 拒絕。
///
/// 注意：事件「載荷」（如 session_id / reason_codes / decision_lease_id）不放進
/// enum 變體，而是由呼叫端透過 `SmContext` 與 `try_transition` 的參數傳入，
/// 使 transition 表 key 維持輕量 `SmEventKind`。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SmEvent {
    /// Python-only：schema valid 的 request 物件建立 → DRAFT。
    RequestSubmitted,
    /// DRAFT → REGISTERED：scope canonical + expires_at 充足。
    RequestRegistered,
    /// REGISTERED → ACTIVE_PRE_AUTH：8-gate 全過 + 寫 authorization.json。
    ApprovalGranted,
    /// REGISTERED → CLOSED：任一 gate fail。
    ApprovalRejected,
    /// REGISTERED → CLOSED：expires_at < NOW。
    RequestExpired,
    /// ACTIVE_PRE_AUTH → ACTIVE_AUTHED：LiveAuthWatcher Verified。
    AuthFileObserved,
    /// ACTIVE_PRE_AUTH → CLOSED：HMAC fail / env_allowed mismatch。
    AuthFileInvalid,
    /// ACTIVE_AUTHED → ACTIVE_TRADING：首筆 lease 綁定（W-AUDIT-9 Stage≥3）。
    LeaseAcquired,
    /// ACTIVE_AUTHED → CLOSED：5min re-verify fail。
    AuthRecheckFail,
    /// ACTIVE_TRADING → ACTIVE_AUTHED：最後一筆 lease release（仍授權）。
    LeaseReleased,
    /// ACTIVE_TRADING → DRAWDOWN_PAUSE：drawdown_revoke.should_revoke Some。
    DrawdownBreach,
    /// 任一非 TERMINAL → CLOSED：operator API kill。
    KillApi,
    /// 任一非 TERMINAL → CLOSED：IPC trigger_kill_switch。
    KillIpc,
    /// 任一非 TERMINAL → CLOSED：max_duration_minutes 倒數到期。
    SessionMaxDuration,
    /// 任一非 TERMINAL → CLOSED：reconciler 對賬發現 5 SoT disagree。
    ReconcileForceClose,
    /// DRAWDOWN_PAUSE → CLOSED：revoke 完成 + leases revoked。
    TransitionalClose,
}

impl SmEvent {
    /// 事件 canonical 字串（log / debug）。
    pub fn as_str(self) -> &'static str {
        match self {
            SmEvent::RequestSubmitted => "request_submitted",
            SmEvent::RequestRegistered => "request_registered",
            SmEvent::ApprovalGranted => "approval_granted",
            SmEvent::ApprovalRejected => "approval_rejected",
            SmEvent::RequestExpired => "request_expired",
            SmEvent::AuthFileObserved => "auth_file_observed",
            SmEvent::AuthFileInvalid => "auth_file_invalid",
            SmEvent::LeaseAcquired => "lease_acquired",
            SmEvent::AuthRecheckFail => "auth_recheck_fail",
            SmEvent::LeaseReleased => "lease_released",
            SmEvent::DrawdownBreach => "drawdown_breach",
            SmEvent::KillApi => "kill_api",
            SmEvent::KillIpc => "kill_ipc",
            SmEvent::SessionMaxDuration => "session_max_duration",
            SmEvent::ReconcileForceClose => "reconcile_force_close",
            SmEvent::TransitionalClose => "transitional_close",
        }
    }
}

impl fmt::Display for SmEvent {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// 17 個 audit `action` enum（spec v2 §4.1 chk_supervised_live_audit_action）。
///
/// 為什麼與 `SmEvent` 分離：多數 event 對應同名 action，但有差異 ——
///   - `RequestExpired` event 寫 audit action `expired_pre_auth`；
///   - `TransitionalClose` event 寫 audit action `drawdown_close_complete`；
///   - `illegal_transition_attempted` 與 `session_closed` 沒有對應 event
///     （前者由非法嘗試路徑寫，後者為 normal close 的 synonym）。
/// 此 enum 必與 V104 CHECK constraint 的 17 值字串 1:1，否則 INSERT 觸 check_violation。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SmAction {
    RequestRegistered,
    ApprovalGranted,
    ApprovalRejected,
    ExpiredPreAuth,
    AuthFileObserved,
    AuthFileInvalid,
    LeaseAcquired,
    LeaseReleased,
    AuthRecheckFail,
    DrawdownBreach,
    DrawdownCloseComplete,
    KillApi,
    KillIpc,
    SessionMaxDuration,
    ReconcileForceClose,
    IllegalTransitionAttempted,
    SessionClosed,
}

impl SmAction {
    /// audit action canonical 字串（必對齊 V104 CHECK 17 值）。
    pub fn as_str(self) -> &'static str {
        match self {
            SmAction::RequestRegistered => "request_registered",
            SmAction::ApprovalGranted => "approval_granted",
            SmAction::ApprovalRejected => "approval_rejected",
            SmAction::ExpiredPreAuth => "expired_pre_auth",
            SmAction::AuthFileObserved => "auth_file_observed",
            SmAction::AuthFileInvalid => "auth_file_invalid",
            SmAction::LeaseAcquired => "lease_acquired",
            SmAction::LeaseReleased => "lease_released",
            SmAction::AuthRecheckFail => "auth_recheck_fail",
            SmAction::DrawdownBreach => "drawdown_breach",
            SmAction::DrawdownCloseComplete => "drawdown_close_complete",
            SmAction::KillApi => "kill_api",
            SmAction::KillIpc => "kill_ipc",
            SmAction::SessionMaxDuration => "session_max_duration",
            SmAction::ReconcileForceClose => "reconcile_force_close",
            SmAction::IllegalTransitionAttempted => "illegal_transition_attempted",
            SmAction::SessionClosed => "session_closed",
        }
    }
}

impl fmt::Display for SmAction {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// transition `result` 欄位（spec v2 §4.1 chk_supervised_live_audit_result）。
///
/// ok = 正常合法 transition；rejected = approval/parse 驗證失敗；
/// forced = reconcile/kill/drawdown 等強制收斂路徑。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SmResult {
    Ok,
    Rejected,
    Forced,
}

impl SmResult {
    pub fn as_str(self) -> &'static str {
        match self {
            SmResult::Ok => "ok",
            SmResult::Rejected => "rejected",
            SmResult::Forced => "forced",
        }
    }
}

/// 非法 transition 錯誤（spec v2 §1.3）。
///
/// 為什麼 fail-closed：非法 (src, event) 組合代表上游邏輯出錯或 race；
/// 此時必須留在當前 state、寫 forensic audit、回 Err，絕不擅自前進到任何態。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct IllegalTransitionError {
    pub src: SmState,
    pub event: SmEvent,
    pub session_id: Option<String>,
}

impl fmt::Display for IllegalTransitionError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "illegal supervised-live transition: state={} event={} session={}",
            self.src,
            self.event,
            self.session_id.as_deref().unwrap_or("<none>")
        )
    }
}

impl std::error::Error for IllegalTransitionError {}

/// audit `action` 字串 → projected `SmState`（spec v2 §2.2A 反向映射表）。
///
/// 為什麼必須有明文映射：reconciler 以 audit 表（SoT #5）為真值權威，需把
/// 「最後一筆 audit action」投影成預期 state 才能與其餘 4 個 derived view 對賬。
/// Rust 與 Python mirror 兩端若對此映射解讀不一致 = split-brain，故集中於此函數。
///
/// 不變量：
///   - `illegal_transition_attempted` → None（不更新 state，僅 forensic）。
///   - unknown action → None → reconciler 視為異常走 WARN fail-closed。
pub fn audit_action_to_projected_state(action: &str) -> Option<SmState> {
    match action {
        "request_registered" => Some(SmState::Registered),
        "approval_granted" => Some(SmState::ActivePreAuth),
        "approval_rejected"
        | "expired_pre_auth"
        | "auth_file_invalid"
        | "auth_recheck_fail"
        | "drawdown_close_complete"
        | "kill_api"
        | "kill_ipc"
        | "session_max_duration"
        | "reconcile_force_close"
        | "session_closed" => Some(SmState::Closed),
        "auth_file_observed" | "lease_released" => Some(SmState::ActiveAuthed),
        "lease_acquired" => Some(SmState::ActiveTrading),
        "drawdown_breach" => Some(SmState::DrawdownPause),
        // 非法嘗試只記 forensic，不投影 state。
        "illegal_transition_attempted" => None,
        // 未知 action → fail-closed（reconciler WARN）。
        _ => None,
    }
}
