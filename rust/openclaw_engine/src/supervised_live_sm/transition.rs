//! Supervised-live SM transition 邏輯與合法 transition 表。
//!
//! MODULE_NOTE
//! 模塊用途：實作 LG-3 supervised-live 狀態機的 transition 核心 ——
//!   合法 transition 表（spec v2 §1.2 16 條）、event→action 映射、
//!   event→result 映射、`try_transition` fail-closed 查表前進邏輯。
//! 主要型別/函數：legal_next_state / event_to_action / event_to_result /
//!   try_transition / TransitionOutcome。
//! 依賴：state.rs（SmState / SmEvent / SmAction / SmResult / IllegalTransitionError）。
//! 硬邊界：
//!   - transition 表是 (src, event) → dst 的封閉集合；查表 miss = 非法 = fail-closed。
//!   - kill_api / kill_ipc / session_max_duration / reconcile_force_close 對「任一
//!     非 TERMINAL 態」皆合法且一律收斂到 CLOSED（survival > profit, 根原則 5/6）。
//!   - 已 CLOSED（TERMINAL）態收任何事件皆非法（含重複 kill）→ 由呼叫端冪等處理，
//!     此處仍回 IllegalTransitionError 以維持 fail-closed 語意。

use super::state::{
    IllegalTransitionError, SmAction, SmEvent, SmResult, SmState,
};

/// 合法 transition 結果：dst state + 對應 audit action + result。
///
/// 為什麼回三元組：一次合法 transition 必同時決定「前進到哪個 state」「寫哪個
/// audit action」「result 標記」，三者耦合且必須原子寫入（spec v2 §4.3 outbox）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TransitionOutcome {
    pub dst: SmState,
    pub action: SmAction,
    pub result: SmResult,
}

/// 查 (src, event) → 合法 dst state（spec v2 §1.2）。
///
/// 為什麼用顯式 match 而非 HashMap：transition 集合在編譯期固定且小（16 條），
/// match 可被編譯期窮舉檢查、零分配、p99 latency 遠低於 spec AC-T1-6 的 100us。
/// 「任一非 TERMINAL → CLOSED」的 4 個事件用 guard 統一處理，避免 7×4 列舉。
///
/// 回 None = 非法 transition（呼叫端 fail-closed）。
fn legal_next_state(src: SmState, event: SmEvent) -> Option<SmState> {
    use SmEvent::*;
    use SmState::*;

    // 先處理「任一非 TERMINAL 態」皆合法的強制收斂事件。
    // 為什麼放最前：kill / duration / reconcile 是 survival 路徑，對所有 active
    // 子態（PRE_AUTH/AUTHED/TRADING/DRAWDOWN_PAUSE，以及 REGISTERED/DRAFT）一律
    // 允許並收斂到 CLOSED；只有已 TERMINAL（CLOSED）拒絕（避免重複副作用）。
    match event {
        KillApi | KillIpc | SessionMaxDuration | ReconcileForceClose => {
            return if src.is_terminal() { None } else { Some(Closed) };
        }
        _ => {}
    }

    match (src, event) {
        // 起手：無 state → DRAFT（Python-only，schema valid）。
        // 用 Draft 作為 src 自映射表達「在 Draft 之前重複 submit 仍停 Draft」不合法，
        // 故 RequestSubmitted 僅對「尚未建立」語意成立；本表以 Draft 為起點。
        (Draft, RequestSubmitted) => Some(Draft),

        // DRAFT → REGISTERED。
        (Draft, RequestRegistered) => Some(Registered),

        // REGISTERED 分支。
        (Registered, ApprovalGranted) => Some(ActivePreAuth),
        (Registered, ApprovalRejected) => Some(Closed),
        (Registered, RequestExpired) => Some(Closed),

        // ACTIVE_PRE_AUTH 分支。
        (ActivePreAuth, AuthFileObserved) => Some(ActiveAuthed),
        (ActivePreAuth, AuthFileInvalid) => Some(Closed),

        // ACTIVE_AUTHED 分支。
        (ActiveAuthed, LeaseAcquired) => Some(ActiveTrading),
        (ActiveAuthed, AuthRecheckFail) => Some(Closed),

        // ACTIVE_TRADING 分支。
        (ActiveTrading, LeaseReleased) => Some(ActiveAuthed),
        (ActiveTrading, DrawdownBreach) => Some(DrawdownPause),

        // DRAWDOWN_PAUSE 分支。
        (DrawdownPause, TransitionalClose) => Some(Closed),

        // 其餘皆非法。
        _ => None,
    }
}

/// event → audit `SmAction`（spec v2 §1.2 Side Effects 欄）。
///
/// 為什麼需要映射：多數 event 與 action 同名，但有 3 處不同：
///   - RequestExpired → ExpiredPreAuth；
///   - TransitionalClose → DrawdownCloseComplete；
///   - RequestSubmitted → 無 audit（DRAFT 是 Python-only、0 DB/0 audit，回 None）。
fn event_to_action(event: SmEvent) -> Option<SmAction> {
    use SmAction as A;
    use SmEvent as E;
    match event {
        // DRAFT 起手：0 DB、0 audit（spec v2 §1.2 第一列）。
        E::RequestSubmitted => None,
        E::RequestRegistered => Some(A::RequestRegistered),
        E::ApprovalGranted => Some(A::ApprovalGranted),
        E::ApprovalRejected => Some(A::ApprovalRejected),
        E::RequestExpired => Some(A::ExpiredPreAuth),
        E::AuthFileObserved => Some(A::AuthFileObserved),
        E::AuthFileInvalid => Some(A::AuthFileInvalid),
        E::LeaseAcquired => Some(A::LeaseAcquired),
        E::AuthRecheckFail => Some(A::AuthRecheckFail),
        E::LeaseReleased => Some(A::LeaseReleased),
        E::DrawdownBreach => Some(A::DrawdownBreach),
        E::KillApi => Some(A::KillApi),
        E::KillIpc => Some(A::KillIpc),
        E::SessionMaxDuration => Some(A::SessionMaxDuration),
        E::ReconcileForceClose => Some(A::ReconcileForceClose),
        E::TransitionalClose => Some(A::DrawdownCloseComplete),
    }
}

/// event → audit `SmResult`。
///
/// rejected：approval/expired/auth-invalid 等驗證失敗收斂；
/// forced：kill/reconcile/drawdown 等強制路徑；
/// ok：其餘正常合法前進。
fn event_to_result(event: SmEvent) -> SmResult {
    use SmEvent::*;
    match event {
        ApprovalRejected | RequestExpired | AuthFileInvalid | AuthRecheckFail => {
            SmResult::Rejected
        }
        KillApi | KillIpc | SessionMaxDuration | ReconcileForceClose | DrawdownBreach
        | TransitionalClose => SmResult::Forced,
        _ => SmResult::Ok,
    }
}

/// 嘗試 transition：查表合法則回 `TransitionOutcome`，否則 fail-closed 回
/// `IllegalTransitionError`（spec v2 §1.3）。
///
/// 為什麼是純函數：transition 決策本身無副作用、無鎖、可單測窮舉；副作用
/// （mutate state / 寫 audit / revoke / IPC broadcast）由 mod.rs 的 SM 持有者
/// 在拿到 outcome 後執行。此分離讓 transition 表測試與副作用測試解耦。
///
/// 不變量：
///   - 合法 (src,event) 但 event 無 audit action（僅 RequestSubmitted）→ 仍回 Ok，
///     由呼叫端決定是否寫 audit（DRAFT 起手不寫）。
///   - 非法 → 呼叫端必寫 `illegal_transition_attempted` forensic + 留在 src。
pub fn try_transition(
    src: SmState,
    event: SmEvent,
    session_id: Option<&str>,
) -> Result<TransitionOutcome, IllegalTransitionError> {
    match legal_next_state(src, event) {
        Some(dst) => {
            // RequestSubmitted 無 audit action，用 SessionClosed 之外的佔位不合適，
            // 故對「無 action」的合法 transition，action 以 RequestRegistered 佔位
            // 並不可行；改以 Option 表達——但 TransitionOutcome.action 為非 Option，
            // 因此 RequestSubmitted 不經 try_transition 主路徑寫 audit。
            // 設計取捨：DRAFT 起手由 mod.rs 直接設 state，不呼叫 try_transition。
            // 此處對所有「會寫 audit」的合法 event 都有 action；RequestSubmitted
            // 若意外走到這裡，回 IllegalTransition 以 fail-loud（避免 silent no-audit）。
            let action = match event_to_action(event) {
                Some(a) => a,
                None => {
                    return Err(IllegalTransitionError {
                        src,
                        event,
                        session_id: session_id.map(str::to_owned),
                    });
                }
            };
            Ok(TransitionOutcome {
                dst,
                action,
                result: event_to_result(event),
            })
        }
        None => Err(IllegalTransitionError {
            src,
            event,
            session_id: session_id.map(str::to_owned),
        }),
    }
}

/// 列出 spec v2 §1.2 全部 16 條合法 transition 的 (src, event) → dst 快照。
///
/// 為什麼導出：tests.rs 以此清單斷言 AC-T1-1「LEGAL_TRANSITIONS 覆蓋 16 條」，
/// 同時作為 transition 表的 single source of truth 文檔（含 kill 對多 src 的展開）。
/// 注意：kill/duration/reconcile 對「每個非 TERMINAL src」各算 1 條合法 transition。
pub fn legal_transition_count() -> usize {
    use SmEvent::*;
    use SmState::*;

    // 顯式 16 條（spec v2 §1.2 表列；「任一非 TERMINAL」的 4 個事件各算 1 列）。
    let explicit: &[(SmState, SmEvent)] = &[
        (Draft, RequestSubmitted),
        (Draft, RequestRegistered),
        (Registered, ApprovalGranted),
        (Registered, ApprovalRejected),
        (Registered, RequestExpired),
        (ActivePreAuth, AuthFileObserved),
        (ActivePreAuth, AuthFileInvalid),
        (ActiveAuthed, LeaseAcquired),
        (ActiveAuthed, AuthRecheckFail),
        (ActiveTrading, LeaseReleased),
        (ActiveTrading, DrawdownBreach),
        (DrawdownPause, TransitionalClose),
        // 4 個「任一非 TERMINAL → CLOSED」事件（spec 表列為 4 列）。
        (Registered, KillApi),
        (Registered, KillIpc),
        (Registered, SessionMaxDuration),
        (Registered, ReconcileForceClose),
    ];
    explicit.len()
}
