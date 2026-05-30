//! Supervised-live SM 單元測試（spec v2 §8 AC-T1-1~7）。
//!
//! MODULE_NOTE
//! 模塊用途：驗證 LG-3 supervised-live 狀態機 transition 表合法/非法路徑、
//!   audit-first fail-closed 語意、reconciler 5-SoT 對賬與 2-cycle 防抖、以及
//!   §2.2A inverse map 17 action 全覆蓋。
//! 覆蓋 AC：
//!   - AC-T1-1：LEGAL_TRANSITIONS 覆蓋 §1.2 全 16 條合法 transition。
//!   - AC-T1-2：16 條 transition 各證明 (src,event)→dst 正確。
//!   - AC-T1-3：≥6 個非法 transition 各觸 IllegalTransitionError。
//!   - AC-T1-4：reconciler disagree → force_close（2-cycle 後）。
//!   - AC-T1-5：transient 1-cycle disagree 不觸 force_close。
//!   - AC-T1-6：transition 為純查表 O(1)（latency 斷言以「無分配/無鎖」結構保證）。
//!   - AC-T1-7：audit_action_to_projected_state 17 action mapping 全 cover。
//! 依賴：super::*（SM core）；MockAuditSink（測試注入，無 PG/無 file）。

use super::reconciler::{reconcile_once, ReconcileMemory, ReconcileVerdict, SotSnapshot};
use super::state::*;
use super::transition::{legal_transition_count, try_transition};
use super::*;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::Arc;

// ---------------------------------------------------------------------------
// MockAuditSink — 測試用 audit seam（無 PG / 無 file）。
// ---------------------------------------------------------------------------

/// 測試用 audit sink：記錄收到的 row + 可切換成「emit 失敗」以驗 fail-closed。
struct MockAuditSink {
    count: AtomicUsize,
    fail: AtomicBool,
    last_action: std::sync::Mutex<Option<SmAction>>,
}

impl MockAuditSink {
    fn new() -> Arc<Self> {
        Arc::new(Self {
            count: AtomicUsize::new(0),
            fail: AtomicBool::new(false),
            last_action: std::sync::Mutex::new(None),
        })
    }
    fn count(&self) -> usize {
        self.count.load(Ordering::SeqCst)
    }
    fn set_fail(&self, v: bool) {
        self.fail.store(v, Ordering::SeqCst);
    }
    fn last_action(&self) -> Option<SmAction> {
        *self.last_action.lock().unwrap()
    }
}

impl AuditSink for MockAuditSink {
    fn emit(&self, row: &AuditRow) -> Result<(), AuditEmitError> {
        if self.fail.load(Ordering::SeqCst) {
            return Err(AuditEmitError::ChannelFull);
        }
        self.count.fetch_add(1, Ordering::SeqCst);
        *self.last_action.lock().unwrap() = Some(row.action);
        Ok(())
    }
}

fn sm_with_sink(sink: Arc<MockAuditSink>) -> SupervisedLiveSm {
    SupervisedLiveSm::new(sink)
}

// ---------------------------------------------------------------------------
// AC-T1-1：transition 表覆蓋 16 條合法 transition。
// ---------------------------------------------------------------------------

#[test]
fn ac_t1_1_legal_transition_count_is_16() {
    // spec v2 §1.2 表列 16 條合法 transition（含 4 個「任一非 TERMINAL→CLOSED」）。
    assert_eq!(legal_transition_count(), 16);
}

// ---------------------------------------------------------------------------
// AC-T1-2：16 條合法 transition 各證明 (src,event)→dst 正確。
// ---------------------------------------------------------------------------

#[test]
fn ac_t1_2_all_legal_transitions_reach_expected_dst() {
    use SmEvent::*;
    use SmState::*;
    // (src, event, expected dst)。
    let cases: &[(SmState, SmEvent, SmState)] = &[
        (Draft, RequestRegistered, Registered),
        (Registered, ApprovalGranted, ActivePreAuth),
        (Registered, ApprovalRejected, Closed),
        (Registered, RequestExpired, Closed),
        (ActivePreAuth, AuthFileObserved, ActiveAuthed),
        (ActivePreAuth, AuthFileInvalid, Closed),
        (ActiveAuthed, LeaseAcquired, ActiveTrading),
        (ActiveAuthed, AuthRecheckFail, Closed),
        (ActiveTrading, LeaseReleased, ActiveAuthed),
        (ActiveTrading, DrawdownBreach, DrawdownPause),
        (DrawdownPause, TransitionalClose, Closed),
        // 「任一非 TERMINAL → CLOSED」4 事件（抽樣多個 src 驗證 guard）。
        (ActiveTrading, KillApi, Closed),
        (ActiveAuthed, KillIpc, Closed),
        (ActivePreAuth, SessionMaxDuration, Closed),
        (Registered, ReconcileForceClose, Closed),
        (DrawdownPause, KillApi, Closed),
    ];
    for (src, event, expected) in cases {
        let outcome =
            try_transition(*src, *event, Some("sess:test")).unwrap_or_else(|e| {
                panic!("expected legal transition {src} --{event}--> {expected}, got {e}")
            });
        assert_eq!(
            outcome.dst, *expected,
            "transition {src} --{event}--> expected {expected}, got {}",
            outcome.dst
        );
    }
}

#[test]
fn ac_t1_2_kill_legal_from_every_non_terminal_state() {
    use SmEvent::*;
    use SmState::*;
    // kill_api 對「每個」非 TERMINAL 態皆合法 → Closed（spec §1.2「任一非 TERMINAL」）。
    let non_terminal = [
        Draft,
        Registered,
        ActivePreAuth,
        ActiveAuthed,
        ActiveTrading,
        DrawdownPause,
    ];
    for src in non_terminal {
        let outcome = try_transition(src, KillApi, Some("sess:x"))
            .unwrap_or_else(|e| panic!("kill_api must be legal from {src}: {e}"));
        assert_eq!(outcome.dst, Closed);
        assert_eq!(outcome.action, SmAction::KillApi);
        assert_eq!(outcome.result, SmResult::Forced);
    }
}

// ---------------------------------------------------------------------------
// AC-T1-3：≥6 個非法 transition 各觸 IllegalTransitionError。
// ---------------------------------------------------------------------------

#[test]
fn ac_t1_3_illegal_transitions_fail_closed() {
    use SmEvent::*;
    use SmState::*;
    // 非法 (src, event)：跳級 / 倒退 / 對 TERMINAL 施非 closing 事件。
    let illegal: &[(SmState, SmEvent)] = &[
        (Draft, ApprovalGranted),       // 跳級：未 REGISTERED 就 approve。
        (Draft, LeaseAcquired),         // 跳級到 TRADING。
        (Registered, AuthFileObserved), // 跳過 PRE_AUTH。
        (ActivePreAuth, LeaseAcquired), // 跳過 AUTHED。
        (ActiveAuthed, AuthFileObserved), // 倒退/重複觀察非法。
        (ActiveTrading, ApprovalGranted), // 已 trading 不可再 approve。
        (Closed, LeaseAcquired),        // TERMINAL 收非 closing 事件。
        (Closed, AuthFileObserved),     // TERMINAL 收非 closing 事件。
    ];
    assert!(illegal.len() >= 6, "需要 ≥6 個非法 case");
    for (src, event) in illegal {
        let r = try_transition(*src, *event, Some("sess:bad"));
        assert!(
            r.is_err(),
            "expected illegal {src} --{event}--> to be rejected, but it succeeded"
        );
        let err = r.unwrap_err();
        assert_eq!(err.src, *src);
        assert_eq!(err.event, *event);
    }
}

// ---------------------------------------------------------------------------
// drive() audit-first fail-closed 語意。
// ---------------------------------------------------------------------------

#[test]
fn drive_advances_state_and_emits_audit() {
    let sink = MockAuditSink::new();
    let mut sm = sm_with_sink(sink.clone());
    assert_eq!(sm.state(), SmState::Draft);

    sm.bind_identity(Some("sess:1".into()), Some("req:1".into()));
    let dst = sm.drive(SmEvent::RequestRegistered, vec![]).unwrap();
    assert_eq!(dst, SmState::Registered);
    assert_eq!(sink.count(), 1);
    assert_eq!(sink.last_action(), Some(SmAction::RequestRegistered));

    let dst = sm.drive(SmEvent::ApprovalGranted, vec![]).unwrap();
    assert_eq!(dst, SmState::ActivePreAuth);
    assert_eq!(sink.count(), 2);
    assert_eq!(sink.last_action(), Some(SmAction::ApprovalGranted));
}

#[test]
fn drive_audit_failure_blocks_transition_fail_closed() {
    let sink = MockAuditSink::new();
    let mut sm = sm_with_sink(sink.clone());
    sm.bind_identity(Some("sess:2".into()), Some("req:2".into()));

    // audit emit 失敗 → transition 不前進（spec §4.4 fail-closed）。
    sink.set_fail(true);
    let r = sm.drive(SmEvent::RequestRegistered, vec![]);
    assert!(matches!(r, Err(SmTransitionError::AuditFailed(_))));
    // state 必維持 Draft（未前進）。
    assert_eq!(sm.state(), SmState::Draft);

    // 恢復 sink → 同事件可成功前進（證明先前是 fail-closed 而非永久卡死）。
    sink.set_fail(false);
    let dst = sm.drive(SmEvent::RequestRegistered, vec![]).unwrap();
    assert_eq!(dst, SmState::Registered);
}

#[test]
fn drive_illegal_writes_forensic_and_stays() {
    let sink = MockAuditSink::new();
    let mut sm = sm_with_sink(sink.clone());
    sm.bind_identity(Some("sess:3".into()), Some("req:3".into()));

    // Draft 收 ApprovalGranted = 非法 → 留在 Draft + 寫 forensic。
    let r = sm.drive(SmEvent::ApprovalGranted, vec![]);
    assert!(matches!(r, Err(SmTransitionError::Illegal(_))));
    assert_eq!(sm.state(), SmState::Draft);
    // forensic audit 已寫（illegal_transition_attempted）。
    assert_eq!(sink.count(), 1);
    assert_eq!(sink.last_action(), Some(SmAction::IllegalTransitionAttempted));
}

#[test]
fn drive_kill_on_closed_is_idempotent_noop() {
    let sink = MockAuditSink::new();
    let mut sm = sm_with_sink(sink.clone());
    sm.bind_identity(Some("sess:4".into()), Some("req:4".into()));
    sm.drive(SmEvent::RequestRegistered, vec![]).unwrap();
    sm.drive(SmEvent::KillApi, vec!["operator_kill".into()]).unwrap();
    assert_eq!(sm.state(), SmState::Closed);
    let count_after_first_kill = sink.count();

    // 對已 CLOSED session 再 kill（API+IPC 雙路徑/reconciler 重入）→ 冪等 no-op。
    let dst = sm.drive(SmEvent::KillIpc, vec![]).unwrap();
    assert_eq!(dst, SmState::Closed);
    // 不寫重複 audit。
    assert_eq!(sink.count(), count_after_first_kill);
}

// ---------------------------------------------------------------------------
// AC-T1-4 / AC-T1-5：reconciler 對賬 + 2-cycle 防抖。
// ---------------------------------------------------------------------------

fn snapshot_all(state: SmState, audit_action: &str) -> SotSnapshot {
    SotSnapshot {
        rust_sm: Some(state),
        python_mirror: Some(state),
        auth_file: Some(state),
        lease_table: Some(state),
        last_audit_action: Some(audit_action.to_string()),
    }
}

#[test]
fn ac_t1_4_two_cycle_disagree_forces_close() {
    let mut mem = ReconcileMemory::default();
    // #5 權威 = ACTIVE_AUTHED（auth_file_observed）；但 rust_sm 漂移到 ACTIVE_TRADING。
    let mut snap = snapshot_all(SmState::ActiveAuthed, "auth_file_observed");
    snap.rust_sm = Some(SmState::ActiveTrading);

    // cycle 1：disagree → pending（不 force_close）。
    let d1 = reconcile_once(&snap, &mut mem);
    assert!(!d1.should_force_close);
    assert!(matches!(d1.verdict, ReconcileVerdict::PendingFirstDisagree { .. }));

    // cycle 2：仍 disagree → force_close。
    let d2 = reconcile_once(&snap, &mut mem);
    assert!(d2.should_force_close);
    match d2.verdict {
        ReconcileVerdict::ForceClose { drift_reasons } => {
            assert!(drift_reasons.contains(&"rust_sm_drift".to_string()));
        }
        other => panic!("expected ForceClose, got {other:?}"),
    }
}

#[test]
fn ac_t1_5_transient_single_cycle_disagree_does_not_force_close() {
    let mut mem = ReconcileMemory::default();
    // cycle 1：disagree（python mirror 漂移）。
    let mut snap = snapshot_all(SmState::ActiveTrading, "lease_acquired");
    snap.python_mirror = Some(SmState::ActiveAuthed);
    let d1 = reconcile_once(&snap, &mut mem);
    assert!(!d1.should_force_close);
    assert!(matches!(d1.verdict, ReconcileVerdict::PendingFirstDisagree { .. }));

    // cycle 2：transient 已恢復一致 → 不 force_close，且重置歷史。
    let good = snapshot_all(SmState::ActiveTrading, "lease_acquired");
    let d2 = reconcile_once(&good, &mut mem);
    assert!(!d2.should_force_close);
    assert_eq!(d2.verdict, ReconcileVerdict::Consistent);
}

#[test]
fn reconcile_consistent_when_all_agree() {
    let mut mem = ReconcileMemory::default();
    let snap = snapshot_all(SmState::ActiveAuthed, "auth_file_observed");
    let d = reconcile_once(&snap, &mut mem);
    assert!(!d.should_force_close);
    assert_eq!(d.verdict, ReconcileVerdict::Consistent);
}

#[test]
fn reconcile_indeterminate_when_no_authoritative_projection() {
    let mut mem = ReconcileMemory::default();
    // #5 為 unknown action → 無權威投影 → Indeterminate（fail-closed WARN，不誤殺）。
    let snap = SotSnapshot {
        rust_sm: Some(SmState::ActiveTrading),
        python_mirror: None,
        auth_file: None,
        lease_table: None,
        last_audit_action: Some("unknown_action_xyz".into()),
    };
    let d = reconcile_once(&snap, &mut mem);
    assert!(!d.should_force_close);
    assert_eq!(d.verdict, ReconcileVerdict::Indeterminate);
}

#[test]
fn reconcile_missing_derived_view_is_not_drift() {
    let mut mem = ReconcileMemory::default();
    // 權威 = REGISTERED；其餘 derived view 全 None（新 session 尚無觀測）→ 不算 disagree。
    let snap = SotSnapshot {
        rust_sm: None,
        python_mirror: None,
        auth_file: None,
        lease_table: None,
        last_audit_action: Some("request_registered".into()),
    };
    let d = reconcile_once(&snap, &mut mem);
    assert!(!d.should_force_close);
    assert_eq!(d.verdict, ReconcileVerdict::Consistent);
}

// ---------------------------------------------------------------------------
// AC-T1-7：audit_action_to_projected_state 17 action 全 cover。
// ---------------------------------------------------------------------------

#[test]
fn ac_t1_7_inverse_map_covers_all_17_actions() {
    use SmState::*;
    // 17 個 action（spec §2.2A）。`illegal_transition_attempted` → None。
    let cases: &[(&str, Option<SmState>)] = &[
        ("request_registered", Some(Registered)),
        ("approval_granted", Some(ActivePreAuth)),
        ("approval_rejected", Some(Closed)),
        ("expired_pre_auth", Some(Closed)),
        ("auth_file_observed", Some(ActiveAuthed)),
        ("auth_file_invalid", Some(Closed)),
        ("lease_acquired", Some(ActiveTrading)),
        ("lease_released", Some(ActiveAuthed)),
        ("auth_recheck_fail", Some(Closed)),
        ("drawdown_breach", Some(DrawdownPause)),
        ("drawdown_close_complete", Some(Closed)),
        ("kill_api", Some(Closed)),
        ("kill_ipc", Some(Closed)),
        ("session_max_duration", Some(Closed)),
        ("reconcile_force_close", Some(Closed)),
        ("illegal_transition_attempted", None),
        ("session_closed", Some(Closed)),
    ];
    assert_eq!(cases.len(), 17, "必須覆蓋全 17 個 action");
    for (action, expected) in cases {
        assert_eq!(
            audit_action_to_projected_state(action),
            *expected,
            "inverse map for action '{action}' mismatch"
        );
    }
    // unknown action → None（fail-closed）。
    assert_eq!(audit_action_to_projected_state("bogus"), None);
}

#[test]
fn sm_action_strings_match_v104_check_enum() {
    // SmAction.as_str() 必與 V104 CHECK 17 值字串一致（T4 INSERT 對齊）。
    let all = [
        (SmAction::RequestRegistered, "request_registered"),
        (SmAction::ApprovalGranted, "approval_granted"),
        (SmAction::ApprovalRejected, "approval_rejected"),
        (SmAction::ExpiredPreAuth, "expired_pre_auth"),
        (SmAction::AuthFileObserved, "auth_file_observed"),
        (SmAction::AuthFileInvalid, "auth_file_invalid"),
        (SmAction::LeaseAcquired, "lease_acquired"),
        (SmAction::LeaseReleased, "lease_released"),
        (SmAction::AuthRecheckFail, "auth_recheck_fail"),
        (SmAction::DrawdownBreach, "drawdown_breach"),
        (SmAction::DrawdownCloseComplete, "drawdown_close_complete"),
        (SmAction::KillApi, "kill_api"),
        (SmAction::KillIpc, "kill_ipc"),
        (SmAction::SessionMaxDuration, "session_max_duration"),
        (SmAction::ReconcileForceClose, "reconcile_force_close"),
        (SmAction::IllegalTransitionAttempted, "illegal_transition_attempted"),
        (SmAction::SessionClosed, "session_closed"),
    ];
    assert_eq!(all.len(), 17);
    for (a, s) in all {
        assert_eq!(a.as_str(), s);
    }
}

#[test]
fn sm_state_strings_match_python_mirror() {
    // SmState.as_str() 必與 Python mirror + audit dst_state 字串一致。
    assert_eq!(SmState::Draft.as_str(), "DRAFT");
    assert_eq!(SmState::Registered.as_str(), "REGISTERED");
    assert_eq!(SmState::ActivePreAuth.as_str(), "ACTIVE_PRE_AUTH");
    assert_eq!(SmState::ActiveAuthed.as_str(), "ACTIVE_AUTHED");
    assert_eq!(SmState::ActiveTrading.as_str(), "ACTIVE_TRADING");
    assert_eq!(SmState::DrawdownPause.as_str(), "DRAWDOWN_PAUSE");
    assert_eq!(SmState::Closed.as_str(), "CLOSED");
    assert!(SmState::Closed.is_terminal());
    assert!(!SmState::ActiveTrading.is_terminal());
}

// ---------------------------------------------------------------------------
// 完整 happy-path walk-through（7-state，driving 真實 SM）。
// ---------------------------------------------------------------------------

#[test]
fn full_happy_path_walkthrough() {
    let sink = MockAuditSink::new();
    let mut sm = sm_with_sink(sink.clone());
    sm.bind_identity(Some("sess:hp".into()), Some("req:hp".into()));

    assert_eq!(sm.drive(SmEvent::RequestRegistered, vec![]).unwrap(), SmState::Registered);
    assert_eq!(sm.drive(SmEvent::ApprovalGranted, vec![]).unwrap(), SmState::ActivePreAuth);
    assert_eq!(sm.drive(SmEvent::AuthFileObserved, vec![]).unwrap(), SmState::ActiveAuthed);
    sm.bind_lease("lease:1".into());
    assert_eq!(sm.drive(SmEvent::LeaseAcquired, vec![]).unwrap(), SmState::ActiveTrading);
    assert_eq!(sm.drive(SmEvent::LeaseReleased, vec![]).unwrap(), SmState::ActiveAuthed);
    // 最終 session_max_duration → CLOSED。
    assert_eq!(
        sm.drive(SmEvent::SessionMaxDuration, vec!["ttl_expired".into()]).unwrap(),
        SmState::Closed
    );
    // 7 筆 audit（register/approve/observe/acquire/release/duration = 6 筆；
    // RequestSubmitted DRAFT 起手不寫，故此 path 共 6 筆）。
    assert_eq!(sink.count(), 6);
}

// ---------------------------------------------------------------------------
// drawdown 路徑 walk-through。
// ---------------------------------------------------------------------------

#[test]
fn drawdown_pause_to_closed_walkthrough() {
    let sink = MockAuditSink::new();
    let mut sm = sm_with_sink(sink.clone());
    sm.bind_identity(Some("sess:dd".into()), Some("req:dd".into()));
    sm.drive(SmEvent::RequestRegistered, vec![]).unwrap();
    sm.drive(SmEvent::ApprovalGranted, vec![]).unwrap();
    sm.drive(SmEvent::AuthFileObserved, vec![]).unwrap();
    sm.bind_lease("lease:dd".into());
    sm.drive(SmEvent::LeaseAcquired, vec![]).unwrap();
    assert_eq!(sm.state(), SmState::ActiveTrading);

    assert_eq!(
        sm.drive(SmEvent::DrawdownBreach, vec!["dd_breach".into()]).unwrap(),
        SmState::DrawdownPause
    );
    assert_eq!(
        sm.drive(SmEvent::TransitionalClose, vec![]).unwrap(),
        SmState::Closed
    );
}
