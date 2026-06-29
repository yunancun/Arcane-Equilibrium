//! ADR-0048 IBKR paper lifecycle/event-log acceptance tests.
//!
//! These tests validate source lifecycle contracts only. They do not construct
//! an IBKR connector, contact IBKR, read secrets, or submit paper orders.

use std::path::PathBuf;

use openclaw_types::{
    classify_ibkr_paper_restart_recovery, BrokerEnvironment, BrokerLifecycleEventLogV1,
    BrokerOperation, IbkrPaperLifecycleEventBlocker, IbkrPaperOrderLifecycleState,
    IbkrPaperRestartRecoveryAction, IbkrPaperRestartRecoveryInputV1, StockEtfDenialReason,
};

#[test]
fn accepted_ack_lifecycle_event_is_append_only_evidence() {
    let event = BrokerLifecycleEventLogV1::accepted_ack_fixture();
    let verdict = event.validate();

    assert!(verdict.accepted);
    assert!(verdict.blockers.is_empty());
}

#[test]
fn default_lifecycle_event_is_blocked_and_incomplete() {
    let verdict = BrokerLifecycleEventLogV1::default().validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::EventIdMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::EventTimeMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::LocalOrderIdMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::InvalidStateTransition));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::RawArtifactHashInvalid));
}

#[test]
fn live_or_account_write_operation_is_not_paper_lifecycle() {
    let event = BrokerLifecycleEventLogV1 {
        environment: BrokerEnvironment::LiveReservedDenied,
        operation: BrokerOperation::LiveOrderSubmit,
        ..BrokerLifecycleEventLogV1::accepted_ack_fixture()
    };
    let verdict = event.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::LiveEnvironmentDenied));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::OperationNotPaperLifecycle));
}

#[test]
fn terminal_state_cannot_transition_back_to_active_lifecycle() {
    let event = BrokerLifecycleEventLogV1 {
        previous_state: IbkrPaperOrderLifecycleState::Filled,
        next_state: IbkrPaperOrderLifecycleState::CancelRequested,
        execution_id: "paper_exec_0001".to_string(),
        commission_report_id: "paper_commission_0001".to_string(),
        ..BrokerLifecycleEventLogV1::accepted_ack_fixture()
    };
    let verdict = event.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::InvalidStateTransition));
}

#[test]
fn unknown_state_only_recovers_to_manual_review_or_terminal_with_evidence() {
    let invalid = BrokerLifecycleEventLogV1 {
        previous_state: IbkrPaperOrderLifecycleState::StateUnknown,
        next_state: IbkrPaperOrderLifecycleState::BrokerAcknowledged,
        ..BrokerLifecycleEventLogV1::accepted_ack_fixture()
    };
    let invalid_verdict = invalid.validate();
    assert!(!invalid_verdict.accepted);
    assert!(invalid_verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::InvalidStateTransition));
    assert!(invalid_verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::StateUnknownRecoveryInvalid));

    let terminal = BrokerLifecycleEventLogV1 {
        operation: BrokerOperation::PaperOrderFillImport,
        previous_state: IbkrPaperOrderLifecycleState::StateUnknown,
        next_state: IbkrPaperOrderLifecycleState::Filled,
        execution_id: "paper_exec_0001".to_string(),
        commission_report_id: "paper_commission_0001".to_string(),
        ..BrokerLifecycleEventLogV1::accepted_ack_fixture()
    };
    assert!(terminal.validate().accepted);
}

#[test]
fn denied_lifecycle_event_requires_denial_reason() {
    let denied_without_reason = BrokerLifecycleEventLogV1 {
        previous_state: IbkrPaperOrderLifecycleState::RustAuthorityAccepted,
        next_state: IbkrPaperOrderLifecycleState::Rejected,
        allowed: false,
        denial_reason: None,
        ..BrokerLifecycleEventLogV1::accepted_ack_fixture()
    };
    let verdict = denied_without_reason.validate();
    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::DenialReasonMissingOnDeniedEvent));

    let denied_with_reason = BrokerLifecycleEventLogV1 {
        denial_reason: Some(StockEtfDenialReason::AuthorizationInvalid),
        ..denied_without_reason
    };
    assert!(denied_with_reason.validate().accepted);
}

#[test]
fn restart_recovery_classification_is_fail_closed() {
    let reconcile = IbkrPaperRestartRecoveryInputV1 {
        broker_state_known: true,
        broker_order_id: "paper_broker_order_0001".to_string(),
        idempotency_key: "idem_0001".to_string(),
        ..IbkrPaperRestartRecoveryInputV1::default()
    };
    assert_eq!(
        classify_ibkr_paper_restart_recovery(&reconcile),
        IbkrPaperRestartRecoveryAction::ReconcileByBrokerOrderIdAndIdempotencyKey
    );

    let terminal = IbkrPaperRestartRecoveryInputV1 {
        last_local_state: IbkrPaperOrderLifecycleState::Cancelled,
        terminal_evidence_hash: "c".repeat(64),
        ..IbkrPaperRestartRecoveryInputV1::default()
    };
    assert_eq!(
        classify_ibkr_paper_restart_recovery(&terminal),
        IbkrPaperRestartRecoveryAction::PreserveTerminalState
    );

    assert_eq!(
        classify_ibkr_paper_restart_recovery(&IbkrPaperRestartRecoveryInputV1::default()),
        IbkrPaperRestartRecoveryAction::MarkStateUnknown
    );
}

#[test]
fn lifecycle_template_is_default_blocked_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw =
        std::fs::read_to_string(srv_root.join("settings/broker/ibkr_paper_order_lifecycle.toml"))
            .expect("read paper lifecycle template");
    let parsed: toml::Value = toml::from_str(&raw).expect("paper lifecycle template toml parses");

    assert_eq!(parsed["event"]["allowed"].as_bool(), Some(false));
    assert_eq!(
        parsed["event"]["next_state"].as_str(),
        Some("STATE_UNKNOWN")
    );
    assert_eq!(
        parsed["restart_recovery"]["broker_state_known"].as_bool(),
        Some(false)
    );

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}
