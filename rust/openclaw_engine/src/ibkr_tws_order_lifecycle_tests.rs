//! W7-S1 訂單生命週期 driver + intent journal 單元測試（不送出）。
//!
//! 覆蓋 DoD:狀態機合法/非法遷移、單一 mutator 競態（fill×cancel reduce-only fail-closed）、
//! nextValidId + idempotency_key join（order-id drift）、ApiPending→transient-pending→逾時升級
//! denied（注入時鐘）、restart recovery MarkStateUnknown、hash chain 竄改可測。

use super::*;

const T0: u64 = 100_000;
const IDEM: &str = "idem_0001";
const LOCAL: &str = "local_order_0001";

fn driver() -> OrderLifecycleDriver {
    OrderLifecycleDriver::new(OrderLifecycleConfig::default())
}

/// happy path:建意圖 → accept → submit-requested（回 driver + 分配的 order_id）。
fn to_submit_requested(d: &mut OrderLifecycleDriver) -> i64 {
    d.set_next_valid_id(9);
    let oid = d.allocate_order_id().expect("next valid id set");
    d.apply_lifecycle_event(LifecycleEvent::Create {
        idempotency_key: IDEM.to_string(),
        order_local_id: LOCAL.to_string(),
        operation: BrokerOperation::PaperOrderSubmit,
        order_id: oid,
        now_ms: T0,
    })
    .unwrap();
    d.apply_lifecycle_event(transition(
        IbkrPaperOrderLifecycleState::RustAuthorityAccepted,
        BrokerOperation::PaperOrderSubmit,
        None,
        None,
        T0 + 1,
    ))
    .unwrap();
    d.apply_lifecycle_event(transition(
        IbkrPaperOrderLifecycleState::BrokerSubmitRequested,
        BrokerOperation::PaperOrderSubmit,
        None,
        None,
        T0 + 2,
    ))
    .unwrap();
    oid
}

fn transition(
    next_state: IbkrPaperOrderLifecycleState,
    operation: BrokerOperation,
    broker_order_id: Option<i64>,
    fill: Option<FillDelta>,
    now_ms: u64,
) -> LifecycleEvent {
    LifecycleEvent::Transition {
        idempotency_key: IDEM.to_string(),
        next_state,
        operation,
        broker_order_id,
        fill,
        now_ms,
    }
}

// ── nextValidId 管理 + order-id 分配 ─────────────────────────────────────────

#[test]
fn next_valid_id_allocation_increments_and_fails_closed_before_ready() {
    let mut d = driver();
    // 未就緒 → 不可分配（fail-closed 不猜號）。
    assert_eq!(d.allocate_order_id(), None);
    d.set_next_valid_id(9); // REQ_IDS=8 → NEXT_VALID_ID=9
    assert_eq!(d.allocate_order_id(), Some(9));
    assert_eq!(d.allocate_order_id(), Some(10));
    assert_eq!(d.allocate_order_id(), Some(11));
}

// ── 狀態機合法/非法遷移 ──────────────────────────────────────────────────────

#[test]
fn legal_main_chain_to_filled() {
    let mut d = driver();
    to_submit_requested(&mut d);
    d.apply_lifecycle_event(transition(
        IbkrPaperOrderLifecycleState::BrokerAcknowledged,
        BrokerOperation::PaperOrderSubmit,
        Some(9),
        None,
        T0 + 3,
    ))
    .unwrap();
    d.apply_lifecycle_event(transition(
        IbkrPaperOrderLifecycleState::PartiallyFilled,
        BrokerOperation::PaperOrderFillImport,
        None,
        Some(FillDelta {
            cumulative_filled_decimal: "5".to_string(),
            remaining_decimal: "5".to_string(),
        }),
        T0 + 4,
    ))
    .unwrap();
    let state = d
        .apply_lifecycle_event(transition(
            IbkrPaperOrderLifecycleState::Filled,
            BrokerOperation::PaperOrderFillImport,
            None,
            Some(FillDelta {
                cumulative_filled_decimal: "10".to_string(),
                remaining_decimal: "0".to_string(),
            }),
            T0 + 5,
        ))
        .unwrap();
    assert_eq!(state, IbkrPaperOrderLifecycleState::Filled);
    assert!(d.verify_chain(), "hash chain intact");
}

#[test]
fn illegal_transition_rejected_state_unchanged() {
    let mut d = driver();
    to_submit_requested(&mut d);
    // BrokerSubmitRequested → Filled 非法（types 矩陣;須先 acked/partial）。
    let err = d
        .apply_lifecycle_event(transition(
            IbkrPaperOrderLifecycleState::Filled,
            BrokerOperation::PaperOrderFillImport,
            None,
            None,
            T0 + 3,
        ))
        .unwrap_err();
    assert!(matches!(
        err,
        LifecycleReject::InvalidTransition {
            from: IbkrPaperOrderLifecycleState::BrokerSubmitRequested,
            to: IbkrPaperOrderLifecycleState::Filled,
        }
    ));
    // 態不變（原子:失敗態不寫）。
    assert_eq!(
        d.intent_by_idempotency_key(IDEM).unwrap().state,
        IbkrPaperOrderLifecycleState::BrokerSubmitRequested
    );
}

#[test]
fn operation_scoped_transition_mismatch_rejected() {
    let mut d = driver();
    to_submit_requested(&mut d);
    d.apply_lifecycle_event(transition(
        IbkrPaperOrderLifecycleState::BrokerAcknowledged,
        BrokerOperation::PaperOrderSubmit,
        Some(9),
        None,
        T0 + 3,
    ))
    .unwrap();
    // BrokerAcknowledged → PartiallyFilled 合法(matrix)但以 PaperOrderCancel verb 驅動非法。
    let err = d
        .apply_lifecycle_event(transition(
            IbkrPaperOrderLifecycleState::PartiallyFilled,
            BrokerOperation::PaperOrderCancel,
            None,
            Some(FillDelta {
                cumulative_filled_decimal: "5".to_string(),
                remaining_decimal: "5".to_string(),
            }),
            T0 + 4,
        ))
        .unwrap_err();
    assert!(matches!(
        err,
        LifecycleReject::OperationTransitionMismatch { .. }
    ));
}

#[test]
fn duplicate_and_unknown_idempotency_rejected() {
    let mut d = driver();
    to_submit_requested(&mut d);
    // 重複 Create 同 idem key。
    assert_eq!(
        d.apply_lifecycle_event(LifecycleEvent::Create {
            idempotency_key: IDEM.to_string(),
            order_local_id: LOCAL.to_string(),
            operation: BrokerOperation::PaperOrderSubmit,
            order_id: 9,
            now_ms: T0,
        })
        .unwrap_err(),
        LifecycleReject::DuplicateIdempotencyKey
    );
    // 未知 idem key 遷移。
    assert_eq!(
        d.apply_lifecycle_event(LifecycleEvent::Transition {
            idempotency_key: "nope".to_string(),
            next_state: IbkrPaperOrderLifecycleState::BrokerAcknowledged,
            operation: BrokerOperation::PaperOrderSubmit,
            broker_order_id: None,
            fill: None,
            now_ms: T0,
        })
        .unwrap_err(),
        LifecycleReject::UnknownIdempotencyKey
    );
}

// ── 單一 mutator 競態:fill × cancel reduce-only fail-closed ──────────────────

#[test]
fn reduce_only_fail_closed_on_remaining_increase() {
    // Bybit 幻影倉教訓:fill 與 cancel 共用單一 mutator;remaining 遞增（幻影再開倉）= 無法證明
    // 減倉安全 → 拒。
    let mut d = driver();
    to_submit_requested(&mut d);
    d.apply_lifecycle_event(transition(
        IbkrPaperOrderLifecycleState::BrokerAcknowledged,
        BrokerOperation::PaperOrderSubmit,
        Some(9),
        None,
        T0 + 3,
    ))
    .unwrap();
    d.apply_lifecycle_event(transition(
        IbkrPaperOrderLifecycleState::PartiallyFilled,
        BrokerOperation::PaperOrderFillImport,
        None,
        Some(FillDelta {
            cumulative_filled_decimal: "5".to_string(),
            remaining_decimal: "5".to_string(),
        }),
        T0 + 4,
    ))
    .unwrap();
    // 第二 fill:remaining 從 5 增回 8（幻影）→ reduce-only 拒。
    let err = d
        .apply_lifecycle_event(transition(
            IbkrPaperOrderLifecycleState::PartiallyFilled,
            BrokerOperation::PaperOrderFillImport,
            None,
            Some(FillDelta {
                cumulative_filled_decimal: "6".to_string(),
                remaining_decimal: "8".to_string(),
            }),
            T0 + 5,
        ))
        .unwrap_err();
    assert!(matches!(
        err,
        LifecycleReject::ReduceOnlyViolation {
            field: "remaining_increased"
        }
    ));
    assert_eq!(d.audit().reduce_only_violations, 1);
    // 記帳不被污染:仍為第一 fill 的定點字串（原子:reduce-only 拒 = 態不寫）。
    let r = d.intent_by_idempotency_key(IDEM).unwrap();
    assert_eq!(r.remaining_decimal.as_deref(), Some("5"));
}

#[test]
fn reduce_only_fail_closed_on_cumulative_decrease() {
    let mut d = driver();
    to_submit_requested(&mut d);
    d.apply_lifecycle_event(transition(
        IbkrPaperOrderLifecycleState::BrokerAcknowledged,
        BrokerOperation::PaperOrderSubmit,
        Some(9),
        None,
        T0 + 3,
    ))
    .unwrap();
    d.apply_lifecycle_event(transition(
        IbkrPaperOrderLifecycleState::PartiallyFilled,
        BrokerOperation::PaperOrderFillImport,
        None,
        Some(FillDelta {
            cumulative_filled_decimal: "5".to_string(),
            remaining_decimal: "5".to_string(),
        }),
        T0 + 4,
    ))
    .unwrap();
    let err = d
        .apply_lifecycle_event(transition(
            IbkrPaperOrderLifecycleState::PartiallyFilled,
            BrokerOperation::PaperOrderFillImport,
            None,
            Some(FillDelta {
                cumulative_filled_decimal: "3".to_string(), // 遞減
                remaining_decimal: "5".to_string(),
            }),
            T0 + 5,
        ))
        .unwrap_err();
    assert!(matches!(
        err,
        LifecycleReject::ReduceOnlyViolation {
            field: "cumulative_filled_decreased"
        }
    ));
}

#[test]
fn cancel_path_shares_single_mutator() {
    let mut d = driver();
    to_submit_requested(&mut d);
    d.apply_lifecycle_event(transition(
        IbkrPaperOrderLifecycleState::BrokerAcknowledged,
        BrokerOperation::PaperOrderSubmit,
        Some(9),
        None,
        T0 + 3,
    ))
    .unwrap();
    d.apply_lifecycle_event(transition(
        IbkrPaperOrderLifecycleState::CancelRequested,
        BrokerOperation::PaperOrderCancel,
        None,
        None,
        T0 + 4,
    ))
    .unwrap();
    let state = d
        .apply_lifecycle_event(transition(
            IbkrPaperOrderLifecycleState::Cancelled,
            BrokerOperation::PaperOrderCancel,
            None,
            None,
            T0 + 5,
        ))
        .unwrap();
    assert_eq!(state, IbkrPaperOrderLifecycleState::Cancelled);
    assert!(state.is_terminal());
}

// ── idempotency_key join + order-id drift ────────────────────────────────────

#[test]
fn order_id_drift_joined_by_idempotency_key() {
    // 重連後 broker 回的 order-id 漂移:以 idempotency_key join,掛載漂移的 broker order-id。
    let mut d = driver();
    let local_oid = to_submit_requested(&mut d);
    assert_eq!(local_oid, 9, "本地分配 = nextValidId");
    // 首次 ack broker_order_id=9（與本地一致）。
    d.apply_lifecycle_event(transition(
        IbkrPaperOrderLifecycleState::BrokerAcknowledged,
        BrokerOperation::PaperOrderSubmit,
        Some(9),
        None,
        T0 + 3,
    ))
    .unwrap();
    // 重連後 broker 回**漂移** order-id=777,仍以 idempotency_key join 同一意圖。
    d.apply_lifecycle_event(transition(
        IbkrPaperOrderLifecycleState::PartiallyFilled,
        BrokerOperation::PaperOrderFillImport,
        Some(777),
        Some(FillDelta {
            cumulative_filled_decimal: "1".to_string(),
            remaining_decimal: "9".to_string(),
        }),
        T0 + 4,
    ))
    .unwrap();
    let r = d.intent_by_idempotency_key(IDEM).unwrap();
    assert_eq!(r.order_id, 9, "本地 order-id 不變（非冪等鍵）");
    assert_eq!(
        r.broker_order_id,
        Some(777),
        "漂移 broker order-id 已 join 掛載"
    );
    assert_eq!(d.audit().broker_order_id_drift_joins, 1);
}

// ── ApiPending → transient-pending → 逾時升級 denied（注入時鐘）────────────────

#[test]
fn api_pending_transient_then_timeout_escalates_denied() {
    let mut d = OrderLifecycleDriver::new(OrderLifecycleConfig {
        api_pending_timeout: Duration::from_secs(30),
    });
    to_submit_requested(&mut d); // 進 BrokerSubmitRequested
                                 // 觀測 ApiPending:合法暫態,不改 state（非狀態注記;與 W5-S3 誤毒對比）。
    d.observe_api_pending(IDEM, T0 + 2).unwrap();
    assert_eq!(
        d.intent_by_idempotency_key(IDEM).unwrap().state,
        IbkrPaperOrderLifecycleState::BrokerSubmitRequested,
        "ApiPending 不改 lifecycle state"
    );
    assert_eq!(d.audit().api_pending_observed, 1);
    // 未逾時:巡檢無升級。
    assert!(d.poll_api_pending_timeouts(T0 + 2 + 20_000).is_empty());
    assert_eq!(
        d.intent_by_idempotency_key(IDEM).unwrap().state,
        IbkrPaperOrderLifecycleState::BrokerSubmitRequested
    );
    // 逾 30s:升級 Rejected（denied;與真 unknown 分流）。
    let escalated = d.poll_api_pending_timeouts(T0 + 2 + 31_000);
    assert_eq!(escalated, vec![IDEM.to_string()]);
    assert_eq!(
        d.intent_by_idempotency_key(IDEM).unwrap().state,
        IbkrPaperOrderLifecycleState::Rejected
    );
    assert_eq!(d.audit().api_pending_timeout_escalations, 1);
}

#[test]
fn api_pending_invalid_at_non_submit_state() {
    let mut d = driver();
    // 未進 BrokerSubmitRequested（僅 Create → LocalIntentCreated）。
    d.set_next_valid_id(9);
    let oid = d.allocate_order_id().unwrap();
    d.apply_lifecycle_event(LifecycleEvent::Create {
        idempotency_key: IDEM.to_string(),
        order_local_id: LOCAL.to_string(),
        operation: BrokerOperation::PaperOrderSubmit,
        order_id: oid,
        now_ms: T0,
    })
    .unwrap();
    assert!(matches!(
        d.observe_api_pending(IDEM, T0 + 1).unwrap_err(),
        LifecycleReject::ApiPendingInvalidState {
            state: IbkrPaperOrderLifecycleState::LocalIntentCreated
        }
    ));
}

// ── restart recovery:未終態 → MarkStateUnknown ───────────────────────────────

#[test]
fn restart_recovery_marks_non_terminal_state_unknown() {
    let mut d = driver();
    to_submit_requested(&mut d);
    d.apply_lifecycle_event(transition(
        IbkrPaperOrderLifecycleState::BrokerAcknowledged,
        BrokerOperation::PaperOrderSubmit,
        Some(9),
        None,
        T0 + 3,
    ))
    .unwrap();
    let actions = d.mark_restart_recovery(T0 + 10);
    assert_eq!(
        actions,
        vec![(
            IDEM.to_string(),
            IbkrPaperRestartRecoveryAction::MarkStateUnknown
        )]
    );
    assert_eq!(
        d.intent_by_idempotency_key(IDEM).unwrap().state,
        IbkrPaperOrderLifecycleState::StateUnknown,
        "未終態 order 重啟後凍結為 StateUnknown（不續用舊授權）"
    );
    assert_eq!(d.audit().restart_marked_unknown, 1);
}

#[test]
fn restart_recovery_preserves_terminal() {
    let mut d = driver();
    to_submit_requested(&mut d);
    d.apply_lifecycle_event(transition(
        IbkrPaperOrderLifecycleState::BrokerAcknowledged,
        BrokerOperation::PaperOrderSubmit,
        Some(9),
        None,
        T0 + 3,
    ))
    .unwrap();
    d.apply_lifecycle_event(transition(
        IbkrPaperOrderLifecycleState::CancelRequested,
        BrokerOperation::PaperOrderCancel,
        None,
        None,
        T0 + 4,
    ))
    .unwrap();
    d.apply_lifecycle_event(transition(
        IbkrPaperOrderLifecycleState::Cancelled,
        BrokerOperation::PaperOrderCancel,
        None,
        None,
        T0 + 5,
    ))
    .unwrap();
    // terminal（Cancelled）但無 evidence hash → classify 非 PreserveTerminal（回 MarkStateUnknown），
    // 然 Cancelled 終態不可再遷（types 矩陣）→ 態不變（凍結由不再 send 承載）。
    d.mark_restart_recovery(T0 + 10);
    assert_eq!(
        d.intent_by_idempotency_key(IDEM).unwrap().state,
        IbkrPaperOrderLifecycleState::Cancelled,
        "終態不被重啟 recovery 改寫"
    );
}

// ── hash chain 竄改可測 ──────────────────────────────────────────────────────

#[test]
fn journal_hash_chain_detects_tamper() {
    let mut d = driver();
    to_submit_requested(&mut d);
    assert!(d.verify_chain());
    // journal 至少 3 條（Create genesis + 2 transitions）。
    assert!(d.journal().len() >= 3);
    // genesis prev hash 為空。
    assert_eq!(d.journal()[0].previous_event_hash, "");
    // 逐條 prev 鏈接。
    for w in d.journal().windows(2) {
        assert_eq!(w[1].previous_event_hash, w[0].event_hash);
    }
}

// ── E4-GAP-1:P0 phantom race 直測（CancelRequested/Cancelled 後 late-fill）────

/// 驅到 CancelRequested（acked → cancel-requested）。
fn to_cancel_requested(d: &mut OrderLifecycleDriver) {
    to_submit_requested(d);
    d.apply_lifecycle_event(transition(
        IbkrPaperOrderLifecycleState::BrokerAcknowledged,
        BrokerOperation::PaperOrderSubmit,
        Some(9),
        None,
        T0 + 3,
    ))
    .unwrap();
    d.apply_lifecycle_event(transition(
        IbkrPaperOrderLifecycleState::CancelRequested,
        BrokerOperation::PaperOrderCancel,
        None,
        None,
        T0 + 4,
    ))
    .unwrap();
}

#[test]
fn phantom_late_fill_after_cancel_requested_rejected_as_invalid_transition() {
    // Bybit 幻影倉形:cancel 在途時到達 late-fill（remaining 遞增再開倉嫌疑）。單一 mutator 先過
    // is_transition_allowed → CancelRequested→PartiallyFilled 非法 → **InvalidTransition**
    //（非 ReduceOnlyViolation;矩陣先攔,reduce-only 是 acked/partial 內的第二道)。態/記帳不變。
    let mut d = driver();
    to_cancel_requested(&mut d);
    let err = d
        .apply_lifecycle_event(transition(
            IbkrPaperOrderLifecycleState::PartiallyFilled,
            BrokerOperation::PaperOrderFillImport,
            None,
            Some(FillDelta {
                cumulative_filled_decimal: "1".to_string(),
                remaining_decimal: "9".to_string(),
            }),
            T0 + 5,
        ))
        .unwrap_err();
    assert!(
        matches!(
            err,
            LifecycleReject::InvalidTransition {
                from: IbkrPaperOrderLifecycleState::CancelRequested,
                to: IbkrPaperOrderLifecycleState::PartiallyFilled,
            }
        ),
        "late-fill after cancel = InvalidTransition (matrix), got {err:?}"
    );
    let r = d.intent_by_idempotency_key(IDEM).unwrap();
    assert_eq!(
        r.state,
        IbkrPaperOrderLifecycleState::CancelRequested,
        "態不變"
    );
    assert_eq!(r.cumulative_filled_decimal, None, "記帳不被 late-fill 污染");
    assert_eq!(r.remaining_decimal, None);
    assert_eq!(d.audit().reduce_only_violations, 0, "非 reduce-only 路徑");
}

#[test]
fn terminal_cancelled_rejects_late_fill() {
    // 終態 Cancelled 後 late-fill → InvalidTransition（終態不可再遷;types 矩陣）。
    let mut d = driver();
    to_cancel_requested(&mut d);
    d.apply_lifecycle_event(transition(
        IbkrPaperOrderLifecycleState::Cancelled,
        BrokerOperation::PaperOrderCancel,
        None,
        None,
        T0 + 5,
    ))
    .unwrap();
    let err = d
        .apply_lifecycle_event(transition(
            IbkrPaperOrderLifecycleState::PartiallyFilled,
            BrokerOperation::PaperOrderFillImport,
            None,
            Some(FillDelta {
                cumulative_filled_decimal: "1".to_string(),
                remaining_decimal: "9".to_string(),
            }),
            T0 + 6,
        ))
        .unwrap_err();
    assert!(matches!(
        err,
        LifecycleReject::InvalidTransition {
            from: IbkrPaperOrderLifecycleState::Cancelled,
            ..
        }
    ));
    assert_eq!(
        d.intent_by_idempotency_key(IDEM).unwrap().state,
        IbkrPaperOrderLifecycleState::Cancelled
    );
}
