//! ADR-0048 IBKR paper lifecycle/event-log acceptance tests.
//!
//! These tests validate source lifecycle contracts only. They do not construct
//! an IBKR connector, contact IBKR, read secrets, or submit paper orders.

use std::path::PathBuf;

use openclaw_types::{
    classify_ibkr_paper_restart_recovery, is_operation_transition_allowed, AssetLane, Broker,
    BrokerEnvironment, BrokerLifecycleEventLogV1, BrokerOperation, IbkrPaperLifecycleEventBlocker,
    IbkrPaperOrderLifecycleState, IbkrPaperRestartRecoveryAction, IbkrPaperRestartRecoveryInputV1,
    IbkrPaperStaleStatePolicy, StockEtfDenialReason, BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID,
    IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID, STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID,
};

#[test]
fn accepted_ack_lifecycle_event_is_append_only_evidence() {
    let event = BrokerLifecycleEventLogV1::accepted_ack_fixture();
    let verdict = event.validate();

    assert!(verdict.accepted);
    assert!(verdict.blockers.is_empty());
    assert_eq!(
        event.lifecycle_contract_id,
        IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID
    );
    assert_eq!(
        event.event_log_contract_id,
        BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID
    );
    assert_eq!(event.source_version, 1);
    assert_eq!(
        event.request_contract_id,
        STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID
    );
    assert!(!event.genesis_event);
    assert_eq!(event.event_sequence, 2);
}

#[test]
fn default_lifecycle_event_is_blocked_and_incomplete() {
    let verdict = BrokerLifecycleEventLogV1::default().validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::LifecycleContractIdMismatch));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::EventLogContractIdMismatch));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::SourceVersionMismatch));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::EventIdMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::EventSequenceMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::PreviousEventHashInvalid));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::EventTimeMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::EventHashInvalid));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::RequestContractIdMismatch));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::RequestEnvelopeHashInvalid));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::LocalOrderIdMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::InvalidStateTransition));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::StaleStatePolicyMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::RawArtifactHashInvalid));
}

#[test]
fn lifecycle_event_requires_exact_contract_ids_and_source_version() {
    let event = BrokerLifecycleEventLogV1 {
        lifecycle_contract_id: "ibkr_paper_order_lifecycle_v1_fixture".to_string(),
        event_log_contract_id: "broker_lifecycle_event_log_v1_fixture".to_string(),
        source_version: 2,
        ..BrokerLifecycleEventLogV1::accepted_ack_fixture()
    };
    let blockers = event.validate().blockers;

    assert!(blockers.contains(&IbkrPaperLifecycleEventBlocker::LifecycleContractIdMismatch));
    assert!(blockers.contains(&IbkrPaperLifecycleEventBlocker::EventLogContractIdMismatch));
    assert!(blockers.contains(&IbkrPaperLifecycleEventBlocker::SourceVersionMismatch));
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
        .contains(&IbkrPaperLifecycleEventBlocker::PaperEnvironmentRequired));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::OperationNotPaperLifecycle));
}

#[test]
fn lifecycle_event_requires_paper_environment() {
    let event = BrokerLifecycleEventLogV1 {
        environment: BrokerEnvironment::ReadOnly,
        ..BrokerLifecycleEventLogV1::accepted_ack_fixture()
    };
    let verdict = event.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&IbkrPaperLifecycleEventBlocker::PaperEnvironmentRequired));
}

#[test]
fn append_only_chain_and_request_envelope_are_required() {
    let broken_chain = BrokerLifecycleEventLogV1 {
        event_sequence: 0,
        previous_event_hash: String::new(),
        event_hash: "not-a-hash".to_string(),
        request_contract_id: "wrong_request_contract".to_string(),
        request_envelope_hash: String::new(),
        ..BrokerLifecycleEventLogV1::accepted_ack_fixture()
    };
    let blockers = broken_chain.validate().blockers;

    assert!(blockers.contains(&IbkrPaperLifecycleEventBlocker::EventSequenceMissing));
    assert!(blockers.contains(&IbkrPaperLifecycleEventBlocker::PreviousEventHashInvalid));
    assert!(blockers.contains(&IbkrPaperLifecycleEventBlocker::EventHashInvalid));
    assert!(blockers.contains(&IbkrPaperLifecycleEventBlocker::RequestContractIdMismatch));
    assert!(blockers.contains(&IbkrPaperLifecycleEventBlocker::RequestEnvelopeHashInvalid));

    let bad_genesis = BrokerLifecycleEventLogV1 {
        event_sequence: 2,
        genesis_event: true,
        previous_event_hash: "f".repeat(64),
        ..BrokerLifecycleEventLogV1::accepted_ack_fixture()
    };
    let blockers = bad_genesis.validate().blockers;
    assert!(blockers.contains(&IbkrPaperLifecycleEventBlocker::GenesisSequenceInvalid));
    assert!(blockers.contains(&IbkrPaperLifecycleEventBlocker::GenesisPreviousEventHashPresent));

    let genesis = BrokerLifecycleEventLogV1 {
        event_sequence: 1,
        genesis_event: true,
        previous_event_hash: String::new(),
        previous_state: IbkrPaperOrderLifecycleState::LocalIntentCreated,
        next_state: IbkrPaperOrderLifecycleState::RustAuthorityAccepted,
        broker_order_id: String::new(),
        ..BrokerLifecycleEventLogV1::accepted_ack_fixture()
    };
    assert!(genesis.validate().accepted);
}

#[test]
fn lifecycle_event_rejects_each_identity_and_lineage_gap_independently() {
    use IbkrPaperLifecycleEventBlocker as Blocker;

    let cases: [(fn(&mut BrokerLifecycleEventLogV1), Blocker); 15] = [
        (
            |event| {
                event.lifecycle_contract_id = "ibkr_paper_order_lifecycle_v1_fixture".to_string()
            },
            Blocker::LifecycleContractIdMismatch,
        ),
        (
            |event| {
                event.event_log_contract_id = "broker_lifecycle_event_log_v1_fixture".to_string()
            },
            Blocker::EventLogContractIdMismatch,
        ),
        (
            |event| event.source_version = 2,
            Blocker::SourceVersionMismatch,
        ),
        (|event| event.event_id.clear(), Blocker::EventIdMissing),
        (
            |event| event.event_sequence = 0,
            Blocker::EventSequenceMissing,
        ),
        (
            |event| event.previous_event_hash.clear(),
            Blocker::PreviousEventHashInvalid,
        ),
        (|event| event.event_time_ms = 0, Blocker::EventTimeMissing),
        (|event| event.event_hash.clear(), Blocker::EventHashInvalid),
        (
            |event| event.request_contract_id = "wrong".to_string(),
            Blocker::RequestContractIdMismatch,
        ),
        (
            |event| event.request_envelope_hash.clear(),
            Blocker::RequestEnvelopeHashInvalid,
        ),
        (
            |event| event.asset_lane = AssetLane::CryptoPerp,
            Blocker::WrongAssetLane,
        ),
        (|event| event.broker = Broker::Bybit, Blocker::WrongBroker),
        (
            |event| event.order_local_id.clear(),
            Blocker::LocalOrderIdMissing,
        ),
        (
            |event| event.idempotency_key.clear(),
            Blocker::IdempotencyKeyMissing,
        ),
        (
            |event| event.reconciliation_run_id.clear(),
            Blocker::ReconciliationRunIdMissing,
        ),
    ];

    for (mutate, blocker) in cases {
        let mut event = BrokerLifecycleEventLogV1::accepted_ack_fixture();
        mutate(&mut event);
        assert_single_blocker(event, blocker);
    }
}

#[test]
fn lifecycle_event_rejects_each_paper_authority_and_artifact_gap_independently() {
    use IbkrPaperLifecycleEventBlocker as Blocker;

    let cases: [(fn(&mut BrokerLifecycleEventLogV1), Blocker); 9] = [
        (
            |event| event.environment = BrokerEnvironment::ReadOnly,
            Blocker::PaperEnvironmentRequired,
        ),
        (
            |event| event.operation = BrokerOperation::PaperOrderCancel,
            Blocker::OperationTransitionMismatch,
        ),
        (
            |event| event.broker_order_id.clear(),
            Blocker::BrokerOrderIdMissing,
        ),
        (
            |event| event.denial_reason = Some(StockEtfDenialReason::AuthorizationInvalid),
            Blocker::DenialReasonPresentOnAllowedEvent,
        ),
        (
            |event| event.stale_state_policy = None,
            Blocker::StaleStatePolicyMissing,
        ),
        (
            |event| {
                event.stale_state_policy =
                    Some(IbkrPaperStaleStatePolicy::PreserveTerminalWithEvidence)
            },
            Blocker::StaleStatePolicyMismatch,
        ),
        (
            |event| event.raw_artifact_hash.clear(),
            Blocker::RawArtifactHashInvalid,
        ),
        (
            |event| event.redacted_summary_hash.clear(),
            Blocker::RedactedSummaryHashInvalid,
        ),
        (
            |event| event.operation = BrokerOperation::TransferOrAccountWrite,
            Blocker::OperationNotPaperLifecycle,
        ),
    ];

    for (mutate, blocker) in cases {
        let mut event = BrokerLifecycleEventLogV1::accepted_ack_fixture();
        mutate(&mut event);
        if blocker == Blocker::OperationNotPaperLifecycle {
            let verdict = event.validate();
            assert!(!verdict.accepted);
            assert!(verdict
                .blockers
                .contains(&Blocker::OperationNotPaperLifecycle));
            assert!(verdict
                .blockers
                .contains(&Blocker::OperationTransitionMismatch));
            assert_eq!(
                verdict.blockers.len(),
                2,
                "expected operation aggregate only, got {:?}",
                verdict.blockers
            );
        } else {
            assert_single_blocker(event, blocker);
        }
    }
}

#[test]
fn operation_must_match_lifecycle_transition_shape() {
    assert!(is_operation_transition_allowed(
        BrokerOperation::PaperOrderSubmit,
        IbkrPaperOrderLifecycleState::BrokerSubmitRequested,
        IbkrPaperOrderLifecycleState::BrokerAcknowledged,
    ));
    assert!(!is_operation_transition_allowed(
        BrokerOperation::PaperOrderSubmit,
        IbkrPaperOrderLifecycleState::BrokerAcknowledged,
        IbkrPaperOrderLifecycleState::Filled,
    ));

    let submit_used_for_fill = BrokerLifecycleEventLogV1 {
        previous_state: IbkrPaperOrderLifecycleState::BrokerAcknowledged,
        next_state: IbkrPaperOrderLifecycleState::Filled,
        operation: BrokerOperation::PaperOrderSubmit,
        execution_id: "paper_exec_0001".to_string(),
        commission_report_id: "paper_commission_0001".to_string(),
        ..BrokerLifecycleEventLogV1::accepted_ack_fixture()
    };
    let blockers = submit_used_for_fill.validate().blockers;
    assert!(blockers.contains(&IbkrPaperLifecycleEventBlocker::OperationTransitionMismatch));

    let cancel_used_for_replace = BrokerLifecycleEventLogV1 {
        previous_state: IbkrPaperOrderLifecycleState::BrokerAcknowledged,
        next_state: IbkrPaperOrderLifecycleState::ReplaceRequested,
        operation: BrokerOperation::PaperOrderCancel,
        ..BrokerLifecycleEventLogV1::accepted_ack_fixture()
    };
    let blockers = cancel_used_for_replace.validate().blockers;
    assert!(blockers.contains(&IbkrPaperLifecycleEventBlocker::OperationTransitionMismatch));
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

    let wrong_policy = BrokerLifecycleEventLogV1 {
        operation: BrokerOperation::PaperOrderFillImport,
        previous_state: IbkrPaperOrderLifecycleState::StateUnknown,
        next_state: IbkrPaperOrderLifecycleState::Filled,
        execution_id: "paper_exec_0001".to_string(),
        commission_report_id: "paper_commission_0001".to_string(),
        stale_state_policy: Some(IbkrPaperStaleStatePolicy::ManualReviewOnUnknown),
        ..BrokerLifecycleEventLogV1::accepted_ack_fixture()
    };
    let blockers = wrong_policy.validate().blockers;
    assert!(blockers.contains(&IbkrPaperLifecycleEventBlocker::StaleStatePolicyMismatch));

    let manual_review = BrokerLifecycleEventLogV1 {
        operation: BrokerOperation::PaperOrderSubmit,
        previous_state: IbkrPaperOrderLifecycleState::StateUnknown,
        next_state: IbkrPaperOrderLifecycleState::ManualReviewRequired,
        stale_state_policy: Some(IbkrPaperStaleStatePolicy::ManualReviewOnUnknown),
        ..BrokerLifecycleEventLogV1::accepted_ack_fixture()
    };
    assert!(manual_review.validate().accepted);

    let active_preserve_policy = BrokerLifecycleEventLogV1 {
        stale_state_policy: Some(IbkrPaperStaleStatePolicy::PreserveTerminalWithEvidence),
        ..BrokerLifecycleEventLogV1::accepted_ack_fixture()
    };
    let blockers = active_preserve_policy.validate().blockers;
    assert!(blockers.contains(&IbkrPaperLifecycleEventBlocker::StaleStatePolicyMismatch));
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

    let denied_but_active = BrokerLifecycleEventLogV1 {
        previous_state: IbkrPaperOrderLifecycleState::BrokerSubmitRequested,
        next_state: IbkrPaperOrderLifecycleState::BrokerAcknowledged,
        allowed: false,
        denial_reason: Some(StockEtfDenialReason::AuthorizationInvalid),
        ..BrokerLifecycleEventLogV1::accepted_ack_fixture()
    };
    let blockers = denied_but_active.validate().blockers;
    assert!(blockers.contains(&IbkrPaperLifecycleEventBlocker::DeniedEventAdvancesActiveState));
}

#[test]
fn lifecycle_event_rejects_denial_and_fill_identity_gaps_independently() {
    use IbkrPaperLifecycleEventBlocker as Blocker;

    let denied_without_reason = BrokerLifecycleEventLogV1 {
        previous_state: IbkrPaperOrderLifecycleState::RustAuthorityAccepted,
        next_state: IbkrPaperOrderLifecycleState::Rejected,
        allowed: false,
        denial_reason: None,
        broker_order_id: String::new(),
        ..BrokerLifecycleEventLogV1::accepted_ack_fixture()
    };
    assert_single_blocker(
        denied_without_reason.clone(),
        Blocker::DenialReasonMissingOnDeniedEvent,
    );

    let denied_but_active = BrokerLifecycleEventLogV1 {
        allowed: false,
        denial_reason: Some(StockEtfDenialReason::AuthorizationInvalid),
        ..BrokerLifecycleEventLogV1::accepted_ack_fixture()
    };
    assert_single_blocker(denied_but_active, Blocker::DeniedEventAdvancesActiveState);

    let mut missing_execution = accepted_fill_event();
    missing_execution.execution_id.clear();
    assert_single_blocker(missing_execution, Blocker::ExecutionIdMissing);

    let mut missing_commission = accepted_fill_event();
    missing_commission.commission_report_id.clear();
    assert_single_blocker(missing_commission, Blocker::CommissionReportIdMissing);
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

    assert_eq!(parsed["event"]["lifecycle_contract_id"].as_str(), Some(""));
    assert_eq!(parsed["event"]["event_log_contract_id"].as_str(), Some(""));
    assert_eq!(parsed["event"]["source_version"].as_integer(), Some(0));
    assert_eq!(parsed["event"]["event_sequence"].as_integer(), Some(0));
    assert_eq!(parsed["event"]["genesis_event"].as_bool(), Some(false));
    assert_eq!(parsed["event"]["previous_event_hash"].as_str(), Some(""));
    assert_eq!(parsed["event"]["event_hash"].as_str(), Some(""));
    assert_eq!(parsed["event"]["request_contract_id"].as_str(), Some(""));
    assert_eq!(parsed["event"]["request_envelope_hash"].as_str(), Some(""));
    assert_eq!(parsed["event"]["allowed"].as_bool(), Some(false));
    assert_eq!(
        parsed["event"]["next_state"].as_str(),
        Some("STATE_UNKNOWN")
    );
    assert_eq!(
        parsed["event"]["stale_state_policy"].as_str(),
        Some("manual_review_on_unknown")
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

fn accepted_fill_event() -> BrokerLifecycleEventLogV1 {
    BrokerLifecycleEventLogV1 {
        operation: BrokerOperation::PaperOrderFillImport,
        previous_state: IbkrPaperOrderLifecycleState::BrokerAcknowledged,
        next_state: IbkrPaperOrderLifecycleState::Filled,
        execution_id: "paper_exec_0001".to_string(),
        commission_report_id: "paper_commission_0001".to_string(),
        ..BrokerLifecycleEventLogV1::accepted_ack_fixture()
    }
}

fn assert_single_blocker(
    event: BrokerLifecycleEventLogV1,
    blocker: IbkrPaperLifecycleEventBlocker,
) {
    let verdict = event.validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![blocker],
        "expected only {:?}, got {:?}",
        blocker,
        verdict.blockers
    );
}
