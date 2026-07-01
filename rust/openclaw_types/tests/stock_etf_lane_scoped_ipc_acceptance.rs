//! ADR-0048 Stock/ETF lane-scoped IPC acceptance tests.
//!
//! These tests validate the source-only Rust IPC contract matrix. They do not
//! start IPC, contact IBKR, inspect secrets, create connectors, submit paper
//! orders, or mutate existing Bybit behavior.

use std::path::PathBuf;

use openclaw_types::{
    AssetLane, AuthorityScope, Broker, BrokerOperation, StockEtfDenialReason,
    StockEtfLaneScopedIpcBlocker, StockEtfLaneScopedIpcCommandV1, StockEtfLaneScopedIpcContractV1,
    StockEtfLaneScopedIpcMethod, IBKR_API_SESSION_TOPOLOGY_CONTRACT_ID,
    IBKR_AUDIT_EVENT_POLICY_CONTRACT_ID, IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
    IBKR_RATE_LIMIT_POLICY_CONTRACT_ID, IBKR_REDACTION_POLICY_CONTRACT_ID,
    IBKR_SECRET_SLOT_CONTRACT_ID, IBKR_SESSION_ATTESTATION_CONTRACT_ID,
    NON_BYBIT_API_ALLOWLIST_CONTRACT_ID, STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID,
    STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID, STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID,
    STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID, STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID,
    STOCK_ETF_RISK_POLICY_CONTRACT_ID, STOCK_ETF_SCOPED_AUTHORIZATION_CONTRACT_ID,
    STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID,
};

#[test]
fn default_lane_scoped_ipc_contract_blocks_all_authority() {
    let verdict = StockEtfLaneScopedIpcContractV1::default().validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict.blockers,
        StockEtfLaneScopedIpcBlocker::ContractIdMismatch
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfLaneScopedIpcBlocker::SourceVersionMismatch
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfLaneScopedIpcBlocker::WrongAssetLane
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfLaneScopedIpcBlocker::WrongBroker
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfLaneScopedIpcBlocker::RustAuthorityOwnerMissing
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfLaneScopedIpcBlocker::CommandMissing
    ));
}

#[test]
fn accepted_fixture_pins_stock_etf_method_matrix_without_runtime_authority() {
    let contract = StockEtfLaneScopedIpcContractV1::accepted_fixture();
    let verdict = contract.validate();

    assert!(
        verdict.accepted,
        "unexpected blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(contract.contract_id, STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID);
    assert_eq!(contract.source_version, 1);
    assert_eq!(contract.asset_lane, AssetLane::StockEtfCash);
    assert_eq!(contract.broker, Broker::Ibkr);
    assert!(contract.rust_authority_owner);
    assert!(contract.python_forward_only);
    assert!(contract.python_direct_broker_write_denied);
    assert!(contract.bybit_ipc_reuse_denied);
    assert!(contract.existing_bybit_paper_path_denied);
    assert!(contract.live_environment_denied);
    assert!(contract.bybit_live_execution_unchanged);
    assert!(!contract.ibkr_contact_performed);
    assert!(!contract.connector_runtime_started);
    assert!(!contract.secret_content_serialized);
    assert_eq!(contract.commands.len(), 20);

    let phase0_status = contract
        .commands
        .iter()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::GetPhase0Status)
        .expect("phase0-status method exists");
    assert_eq!(phase0_status.operation, BrokerOperation::HealthRead);
    assert_eq!(phase0_status.authority_scope, AuthorityScope::DisplayOnly);
    assert!(!phase0_status.effect_capable);
    assert!(!phase0_status.rust_owned);

    let submit = contract
        .commands
        .iter()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::SubmitPaperOrder)
        .expect("submit method exists");
    assert_eq!(submit.operation, BrokerOperation::PaperOrderSubmit);
    assert_eq!(submit.authority_scope, AuthorityScope::PaperRehearsal);
    assert!(submit.effect_capable);
    assert!(submit.rust_owned);
    assert!(submit
        .required_gates
        .contains(&STOCK_ETF_SCOPED_AUTHORIZATION_CONTRACT_ID.to_string()));
    assert!(submit
        .required_gates
        .contains(&STOCK_ETF_RISK_POLICY_CONTRACT_ID.to_string()));
    assert!(submit
        .required_gates
        .contains(&STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID.to_string()));
    assert!(submit
        .required_request_fields
        .contains(&"decision_lease_id".to_string()));
    assert_fields(
        submit,
        &[
            "account_fingerprint_hash",
            "instrument_identity_hash",
            "symbol",
            "instrument_kind",
            "side",
            "order_type",
            "quantity",
            "limit_price_policy",
            "time_in_force",
            "order_local_id",
            "idempotency_key",
        ],
    );

    let preview = contract
        .commands
        .iter()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::PreviewPaperOrder)
        .expect("preview method exists");
    assert!(preview
        .required_gates
        .contains(&STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID.to_string()));
    assert!(preview
        .required_gates
        .contains(&STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID.to_string()));
    assert!(preview
        .required_gates
        .contains(&STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID.to_string()));
    assert!(!preview.effect_capable);
    assert_eq!(preview.authority_scope, AuthorityScope::ReadOnly);
    assert_fields(
        preview,
        &[
            "account_fingerprint_hash",
            "instrument_identity_hash",
            "symbol",
            "instrument_kind",
            "side",
            "order_type",
            "quantity",
            "limit_price_policy",
            "time_in_force",
        ],
    );

    let paper_status = contract
        .commands
        .iter()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::GetPaperStatus)
        .expect("paper-status method exists");
    assert_eq!(paper_status.operation, BrokerOperation::HealthRead);
    assert_eq!(paper_status.authority_scope, AuthorityScope::DisplayOnly);
    assert!(!paper_status.effect_capable);
    assert!(!paper_status.rust_owned);

    let account_status = contract
        .commands
        .iter()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::GetAccountStatus)
        .expect("account-status method exists");
    assert_eq!(account_status.operation, BrokerOperation::HealthRead);
    assert_eq!(account_status.authority_scope, AuthorityScope::DisplayOnly);
    assert!(!account_status.effect_capable);
    assert!(!account_status.rust_owned);

    let data_foundation_status = contract
        .commands
        .iter()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::GetDataFoundationStatus)
        .expect("data-foundation-status method exists");
    assert_eq!(
        data_foundation_status.operation,
        BrokerOperation::HealthRead
    );
    assert_eq!(
        data_foundation_status.authority_scope,
        AuthorityScope::DisplayOnly
    );
    assert!(!data_foundation_status.effect_capable);
    assert!(!data_foundation_status.rust_owned);

    let policy_status = contract
        .commands
        .iter()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::GetPolicyStatus)
        .expect("policy-status method exists");
    assert_eq!(policy_status.operation, BrokerOperation::HealthRead);
    assert_eq!(policy_status.authority_scope, AuthorityScope::DisplayOnly);
    assert!(!policy_status.effect_capable);
    assert!(!policy_status.rust_owned);

    let authorization_status = contract
        .commands
        .iter()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::GetAuthorizationStatus)
        .expect("authorization-status method exists");
    assert_eq!(authorization_status.operation, BrokerOperation::HealthRead);
    assert_eq!(
        authorization_status.authority_scope,
        AuthorityScope::DisplayOnly
    );
    assert!(!authorization_status.effect_capable);
    assert!(!authorization_status.rust_owned);

    let reconciliation_status = contract
        .commands
        .iter()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::GetReconciliationStatus)
        .expect("reconciliation-status method exists");
    assert_eq!(reconciliation_status.operation, BrokerOperation::HealthRead);
    assert_eq!(
        reconciliation_status.authority_scope,
        AuthorityScope::DisplayOnly
    );
    assert!(!reconciliation_status.effect_capable);
    assert!(!reconciliation_status.rust_owned);

    let scorecard_status = contract
        .commands
        .iter()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::GetScorecardStatus)
        .expect("scorecard-status method exists");
    assert_eq!(scorecard_status.operation, BrokerOperation::HealthRead);
    assert_eq!(
        scorecard_status.authority_scope,
        AuthorityScope::DisplayOnly
    );
    assert!(!scorecard_status.effect_capable);
    assert!(!scorecard_status.rust_owned);

    let launch_status = contract
        .commands
        .iter()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::GetLaunchStatus)
        .expect("launch-status method exists");
    assert_eq!(launch_status.operation, BrokerOperation::HealthRead);
    assert_eq!(launch_status.authority_scope, AuthorityScope::DisplayOnly);
    assert!(!launch_status.effect_capable);
    assert!(!launch_status.rust_owned);

    let release_packet_status = contract
        .commands
        .iter()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::GetReleasePacketStatus)
        .expect("release-packet-status method exists");
    assert_eq!(release_packet_status.operation, BrokerOperation::HealthRead);
    assert_eq!(
        release_packet_status.authority_scope,
        AuthorityScope::DisplayOnly
    );
    assert!(!release_packet_status.effect_capable);
    assert!(!release_packet_status.rust_owned);

    let disable_cleanup_status = contract
        .commands
        .iter()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::GetDisableCleanupStatus)
        .expect("disable-cleanup-status method exists");
    assert_eq!(
        disable_cleanup_status.operation,
        BrokerOperation::HealthRead
    );
    assert_eq!(
        disable_cleanup_status.authority_scope,
        AuthorityScope::DisplayOnly
    );
    assert!(!disable_cleanup_status.effect_capable);
    assert!(!disable_cleanup_status.rust_owned);

    let shadow = contract
        .commands
        .iter()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::EvaluateShadowSignal)
        .expect("shadow method exists");
    assert!(shadow
        .required_gates
        .contains(&STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID.to_string()));
    assert!(shadow
        .required_gates
        .contains(&STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID.to_string()));
    assert!(shadow
        .required_gates
        .contains(&STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID.to_string()));
    assert!(shadow
        .required_gates
        .contains(&STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID.to_string()));

    let readonly_probe = contract
        .commands
        .iter()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::PreviewReadonlyProbe)
        .expect("readonly-probe preview method exists");
    assert_eq!(readonly_probe.operation, BrokerOperation::HealthRead);
    assert_eq!(readonly_probe.authority_scope, AuthorityScope::ReadOnly);
    assert!(!readonly_probe.effect_capable);
    assert!(readonly_probe.rust_owned);
    for gate in [
        IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
        NON_BYBIT_API_ALLOWLIST_CONTRACT_ID,
        IBKR_SECRET_SLOT_CONTRACT_ID,
        IBKR_API_SESSION_TOPOLOGY_CONTRACT_ID,
        IBKR_SESSION_ATTESTATION_CONTRACT_ID,
        IBKR_REDACTION_POLICY_CONTRACT_ID,
        IBKR_RATE_LIMIT_POLICY_CONTRACT_ID,
        IBKR_AUDIT_EVENT_POLICY_CONTRACT_ID,
    ] {
        assert!(
            readonly_probe.required_gates.contains(&gate.to_string()),
            "readonly probe method missing gate {gate}"
        );
    }
    assert_fields(
        readonly_probe,
        &[
            "probe_kind",
            "api_action",
            "request_id",
            "probe_id",
            "phase2_gate_artifact_hash",
            "api_allowlist_hash",
            "secret_slot_contract_hash",
            "api_session_topology_hash",
            "session_attestation_hash",
            "redaction_policy_hash",
            "rate_limit_policy_hash",
            "audit_event_policy_hash",
            "source_artifact_hash",
            "raw_artifact_hash",
            "redacted_summary_hash",
        ],
    );
}

#[test]
fn lane_scoped_ipc_rejects_each_top_level_authority_gap_independently() {
    assert_single_blocker(
        StockEtfLaneScopedIpcContractV1 {
            contract_id: String::new(),
            ..StockEtfLaneScopedIpcContractV1::accepted_fixture()
        },
        StockEtfLaneScopedIpcBlocker::ContractIdMismatch,
    );
    assert_single_blocker(
        StockEtfLaneScopedIpcContractV1 {
            source_version: 2,
            ..StockEtfLaneScopedIpcContractV1::accepted_fixture()
        },
        StockEtfLaneScopedIpcBlocker::SourceVersionMismatch,
    );
    assert_single_blocker(
        StockEtfLaneScopedIpcContractV1 {
            asset_lane: AssetLane::CryptoPerp,
            ..StockEtfLaneScopedIpcContractV1::accepted_fixture()
        },
        StockEtfLaneScopedIpcBlocker::WrongAssetLane,
    );
    assert_single_blocker(
        StockEtfLaneScopedIpcContractV1 {
            broker: Broker::Bybit,
            ..StockEtfLaneScopedIpcContractV1::accepted_fixture()
        },
        StockEtfLaneScopedIpcBlocker::WrongBroker,
    );
    assert_single_blocker(
        StockEtfLaneScopedIpcContractV1 {
            rust_authority_owner: false,
            ..StockEtfLaneScopedIpcContractV1::accepted_fixture()
        },
        StockEtfLaneScopedIpcBlocker::RustAuthorityOwnerMissing,
    );
    assert_single_blocker(
        StockEtfLaneScopedIpcContractV1 {
            python_forward_only: false,
            ..StockEtfLaneScopedIpcContractV1::accepted_fixture()
        },
        StockEtfLaneScopedIpcBlocker::PythonForwardOnlyMissing,
    );
    assert_single_blocker(
        StockEtfLaneScopedIpcContractV1 {
            python_direct_broker_write_denied: false,
            ..StockEtfLaneScopedIpcContractV1::accepted_fixture()
        },
        StockEtfLaneScopedIpcBlocker::PythonDirectBrokerWriteNotDenied,
    );
    assert_single_blocker(
        StockEtfLaneScopedIpcContractV1 {
            bybit_ipc_reuse_denied: false,
            ..StockEtfLaneScopedIpcContractV1::accepted_fixture()
        },
        StockEtfLaneScopedIpcBlocker::BybitIpcReuseNotDenied,
    );
    assert_single_blocker(
        StockEtfLaneScopedIpcContractV1 {
            existing_bybit_paper_path_denied: false,
            ..StockEtfLaneScopedIpcContractV1::accepted_fixture()
        },
        StockEtfLaneScopedIpcBlocker::ExistingBybitPaperPathNotDenied,
    );
    assert_single_blocker(
        StockEtfLaneScopedIpcContractV1 {
            live_environment_denied: false,
            ..StockEtfLaneScopedIpcContractV1::accepted_fixture()
        },
        StockEtfLaneScopedIpcBlocker::LiveEnvironmentNotDenied,
    );
    assert_single_blocker(
        StockEtfLaneScopedIpcContractV1 {
            bybit_live_execution_unchanged: false,
            ..StockEtfLaneScopedIpcContractV1::accepted_fixture()
        },
        StockEtfLaneScopedIpcBlocker::BybitLiveExecutionNotProtected,
    );
    assert_single_blocker(
        StockEtfLaneScopedIpcContractV1 {
            ibkr_contact_performed: true,
            ..StockEtfLaneScopedIpcContractV1::accepted_fixture()
        },
        StockEtfLaneScopedIpcBlocker::IbkrContactPerformed,
    );
    assert_single_blocker(
        StockEtfLaneScopedIpcContractV1 {
            connector_runtime_started: true,
            ..StockEtfLaneScopedIpcContractV1::accepted_fixture()
        },
        StockEtfLaneScopedIpcBlocker::ConnectorRuntimeStarted,
    );
    assert_single_blocker(
        StockEtfLaneScopedIpcContractV1 {
            secret_content_serialized: true,
            ..StockEtfLaneScopedIpcContractV1::accepted_fixture()
        },
        StockEtfLaneScopedIpcBlocker::SecretContentSerialized,
    );
}

#[test]
fn lane_scoped_ipc_rejects_each_command_coverage_gap_independently() {
    let mut missing = StockEtfLaneScopedIpcContractV1::accepted_fixture();
    missing
        .commands
        .retain(|command| command.method != StockEtfLaneScopedIpcMethod::ImportPaperFills);
    assert_single_blocker(missing, StockEtfLaneScopedIpcBlocker::CommandMissing);

    let mut duplicated = StockEtfLaneScopedIpcContractV1::accepted_fixture();
    duplicated
        .commands
        .push(command(&duplicated, StockEtfLaneScopedIpcMethod::GetLaneStatus).clone());
    assert_single_blocker(duplicated, StockEtfLaneScopedIpcBlocker::CommandDuplicated);

    let mut denied_extra = StockEtfLaneScopedIpcContractV1::accepted_fixture();
    denied_extra
        .commands
        .push(StockEtfLaneScopedIpcCommandV1::fixture_for_method(
            StockEtfLaneScopedIpcMethod::BybitSubmitPaperOrderDenied,
        ));
    assert_single_blocker(
        denied_extra,
        StockEtfLaneScopedIpcBlocker::CommandMethodDenied,
    );
}

#[test]
fn lane_scoped_ipc_rejects_each_command_shape_gap_independently() {
    assert_single_command_blocker(
        |submit| submit.operation = BrokerOperation::LiveOrderSubmit,
        StockEtfLaneScopedIpcBlocker::CommandOperationMismatch,
    );
    assert_single_command_blocker(
        |submit| submit.authority_scope = AuthorityScope::ReadOnly,
        StockEtfLaneScopedIpcBlocker::CommandAuthorityScopeMismatch,
    );
    assert_single_command_blocker(
        |submit| submit.effect_capable = false,
        StockEtfLaneScopedIpcBlocker::CommandEffectCapabilityMismatch,
    );
    assert_single_command_blocker(
        |submit| submit.rust_owned = false,
        StockEtfLaneScopedIpcBlocker::CommandRustOwnershipMismatch,
    );
    assert_single_command_blocker(
        |submit| {
            submit
                .required_gates
                .retain(|gate| gate != STOCK_ETF_SCOPED_AUTHORIZATION_CONTRACT_ID)
        },
        StockEtfLaneScopedIpcBlocker::CommandRequiredGateMissing,
    );
    assert_single_command_blocker(
        |submit| {
            submit
                .required_request_fields
                .retain(|field| field != "decision_lease_id")
        },
        StockEtfLaneScopedIpcBlocker::CommandRequestFieldMissing,
    );
    assert_single_command_blocker(
        |submit| {
            submit
                .typed_denial_reasons
                .retain(|reason| *reason != StockEtfDenialReason::DecisionLeaseInvalid)
        },
        StockEtfLaneScopedIpcBlocker::CommandDenialReasonMissing,
    );
}

#[test]
fn paper_order_request_shapes_are_method_specific_and_not_cross_wireable() {
    let contract = StockEtfLaneScopedIpcContractV1::accepted_fixture();
    let submit = command(&contract, StockEtfLaneScopedIpcMethod::SubmitPaperOrder);
    let cancel = command(&contract, StockEtfLaneScopedIpcMethod::CancelPaperOrder);
    let replace = command(&contract, StockEtfLaneScopedIpcMethod::ReplacePaperOrder);

    assert_ne!(
        submit.required_request_fields,
        cancel.required_request_fields
    );
    assert_ne!(
        submit.required_request_fields,
        replace.required_request_fields
    );
    assert_ne!(
        cancel.required_request_fields,
        replace.required_request_fields
    );

    assert_fields(
        cancel,
        &[
            "account_fingerprint_hash",
            "order_local_id",
            "broker_order_id",
            "cancel_reason",
            "idempotency_key",
            "lifecycle_contract_hash",
            "broker_capability_registry_hash",
            "audit_event_id",
        ],
    );
    assert_lacks_fields(
        cancel,
        &[
            "symbol",
            "instrument_kind",
            "side",
            "order_type",
            "quantity",
            "limit_price_policy",
            "time_in_force",
        ],
    );

    assert_fields(
        replace,
        &[
            "account_fingerprint_hash",
            "order_local_id",
            "broker_order_id",
            "instrument_identity_hash",
            "symbol",
            "side",
            "replacement_idempotency_key",
            "replacement_quantity",
            "replacement_limit_price_policy",
            "replacement_time_in_force",
            "replace_reason",
            "lifecycle_contract_hash",
            "broker_capability_registry_hash",
            "audit_event_id",
        ],
    );
    assert_lacks_fields(
        replace,
        &[
            "order_type",
            "quantity",
            "limit_price_policy",
            "time_in_force",
        ],
    );

    let mut cancel_cross_wired_as_submit = StockEtfLaneScopedIpcContractV1::accepted_fixture();
    let submit_fields = command(
        &cancel_cross_wired_as_submit,
        StockEtfLaneScopedIpcMethod::SubmitPaperOrder,
    )
    .required_request_fields
    .clone();
    command_mut(
        &mut cancel_cross_wired_as_submit,
        StockEtfLaneScopedIpcMethod::CancelPaperOrder,
    )
    .required_request_fields = submit_fields;
    assert!(has(
        &cancel_cross_wired_as_submit.validate().blockers,
        StockEtfLaneScopedIpcBlocker::CommandRequestFieldMissing
    ));

    let mut replace_cross_wired_as_cancel = StockEtfLaneScopedIpcContractV1::accepted_fixture();
    let cancel_fields = command(
        &replace_cross_wired_as_cancel,
        StockEtfLaneScopedIpcMethod::CancelPaperOrder,
    )
    .required_request_fields
    .clone();
    command_mut(
        &mut replace_cross_wired_as_cancel,
        StockEtfLaneScopedIpcMethod::ReplacePaperOrder,
    )
    .required_request_fields = cancel_fields;
    assert!(has(
        &replace_cross_wired_as_cancel.validate().blockers,
        StockEtfLaneScopedIpcBlocker::CommandRequestFieldMissing
    ));

    let mut submit_cross_wired_as_cancel = StockEtfLaneScopedIpcContractV1::accepted_fixture();
    let cancel_fields = command(
        &submit_cross_wired_as_cancel,
        StockEtfLaneScopedIpcMethod::CancelPaperOrder,
    )
    .required_request_fields
    .clone();
    command_mut(
        &mut submit_cross_wired_as_cancel,
        StockEtfLaneScopedIpcMethod::SubmitPaperOrder,
    )
    .required_request_fields = cancel_fields;
    assert!(has(
        &submit_cross_wired_as_cancel.validate().blockers,
        StockEtfLaneScopedIpcBlocker::CommandRequestFieldMissing
    ));
}

#[test]
fn lane_scoped_ipc_requires_exact_contract_id_and_source_version() {
    let contract = StockEtfLaneScopedIpcContractV1 {
        contract_id: "lane_scoped_ipc_v1_fixture".to_string(),
        source_version: 2,
        ..StockEtfLaneScopedIpcContractV1::accepted_fixture()
    };
    let blockers = contract.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::ContractIdMismatch
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::SourceVersionMismatch
    ));
}

#[test]
fn lane_scoped_ipc_rejects_top_level_boundary_regressions() {
    let contract = StockEtfLaneScopedIpcContractV1 {
        contract_id: "wrong".to_string(),
        asset_lane: AssetLane::CryptoPerp,
        broker: Broker::Bybit,
        rust_authority_owner: false,
        python_forward_only: false,
        python_direct_broker_write_denied: false,
        bybit_ipc_reuse_denied: false,
        existing_bybit_paper_path_denied: false,
        live_environment_denied: false,
        bybit_live_execution_unchanged: false,
        ibkr_contact_performed: true,
        connector_runtime_started: true,
        secret_content_serialized: true,
        ..StockEtfLaneScopedIpcContractV1::accepted_fixture()
    };
    let blockers = contract.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::ContractIdMismatch
    ));
    assert!(has(&blockers, StockEtfLaneScopedIpcBlocker::WrongAssetLane));
    assert!(has(&blockers, StockEtfLaneScopedIpcBlocker::WrongBroker));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::PythonDirectBrokerWriteNotDenied
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::BybitIpcReuseNotDenied
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::ExistingBybitPaperPathNotDenied
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::LiveEnvironmentNotDenied
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::IbkrContactPerformed
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::ConnectorRuntimeStarted
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::SecretContentSerialized
    ));
}

#[test]
fn lane_scoped_ipc_requires_exact_command_coverage_once() {
    let mut contract = StockEtfLaneScopedIpcContractV1::accepted_fixture();
    let duplicate = contract.commands[0].clone();
    contract
        .commands
        .retain(|command| command.method != StockEtfLaneScopedIpcMethod::ImportPaperFills);
    contract.commands.push(duplicate);

    let blockers = contract.validate().blockers;

    assert!(has(&blockers, StockEtfLaneScopedIpcBlocker::CommandMissing));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::CommandDuplicated
    ));
}

#[test]
fn paper_effect_methods_require_gates_fields_denials_and_rust_ownership() {
    let mut contract = StockEtfLaneScopedIpcContractV1::accepted_fixture();
    let submit = contract
        .commands
        .iter_mut()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::SubmitPaperOrder)
        .expect("submit method");
    submit.operation = BrokerOperation::LiveOrderSubmit;
    submit.authority_scope = AuthorityScope::ReadOnly;
    submit.effect_capable = false;
    submit.rust_owned = false;
    submit.required_gates.clear();
    submit.required_request_fields.clear();
    submit
        .typed_denial_reasons
        .retain(|reason| *reason != StockEtfDenialReason::DecisionLeaseInvalid);

    let blockers = contract.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::CommandOperationMismatch
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::CommandAuthorityScopeMismatch
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::CommandEffectCapabilityMismatch
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::CommandRustOwnershipMismatch
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::CommandRequiredGateMissing
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::CommandRequestFieldMissing
    ));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::CommandDenialReasonMissing
    ));
}

#[test]
fn denied_or_unknown_ipc_methods_cannot_clear_contract() {
    let mut contract = StockEtfLaneScopedIpcContractV1::accepted_fixture();
    let submit = contract
        .commands
        .iter_mut()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::SubmitPaperOrder)
        .expect("submit method");
    submit.method = StockEtfLaneScopedIpcMethod::BybitSubmitPaperOrderDenied;

    let blockers = contract.validate().blockers;

    assert!(has(&blockers, StockEtfLaneScopedIpcBlocker::CommandMissing));
    assert!(has(
        &blockers,
        StockEtfLaneScopedIpcBlocker::CommandMethodDenied
    ));
}

#[test]
fn blocked_template_is_parseable_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/stock_etf_lane_scoped_ipc.template.toml"),
    )
    .expect("read lane-scoped IPC template");
    let parsed: StockEtfLaneScopedIpcContractV1 =
        toml::from_str(&raw).expect("lane-scoped IPC template parses");

    assert_eq!(parsed.contract_id, "");
    assert_eq!(parsed.source_version, 0);
    assert_eq!(parsed.asset_lane, AssetLane::CryptoPerp);
    assert_eq!(parsed.broker, Broker::Bybit);
    assert!(!parsed.validate().accepted);
    assert!(!parsed.rust_authority_owner);
    assert!(!parsed.bybit_ipc_reuse_denied);
    assert!(!parsed.ibkr_contact_performed);
    assert!(!parsed.secret_content_serialized);

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}

fn has(blockers: &[StockEtfLaneScopedIpcBlocker], blocker: StockEtfLaneScopedIpcBlocker) -> bool {
    blockers.contains(&blocker)
}

fn command(
    contract: &StockEtfLaneScopedIpcContractV1,
    method: StockEtfLaneScopedIpcMethod,
) -> &StockEtfLaneScopedIpcCommandV1 {
    contract
        .commands
        .iter()
        .find(|command| command.method == method)
        .expect("stock/ETF IPC method exists")
}

fn command_mut(
    contract: &mut StockEtfLaneScopedIpcContractV1,
    method: StockEtfLaneScopedIpcMethod,
) -> &mut StockEtfLaneScopedIpcCommandV1 {
    contract
        .commands
        .iter_mut()
        .find(|command| command.method == method)
        .expect("stock/ETF IPC method exists")
}

fn assert_fields(command: &StockEtfLaneScopedIpcCommandV1, fields: &[&str]) {
    for field in fields {
        assert!(
            command.required_request_fields.contains(&field.to_string()),
            "{:?} missing required request field {field}",
            command.method
        );
    }
}

fn assert_lacks_fields(command: &StockEtfLaneScopedIpcCommandV1, fields: &[&str]) {
    for field in fields {
        assert!(
            !command.required_request_fields.contains(&field.to_string()),
            "{:?} unexpectedly requires request field {field}",
            command.method
        );
    }
}

fn assert_single_blocker(
    candidate: StockEtfLaneScopedIpcContractV1,
    expected: StockEtfLaneScopedIpcBlocker,
) {
    let verdict = candidate.validate();

    assert!(!verdict.accepted);
    assert_eq!(verdict.blockers, vec![expected]);
}

fn assert_single_command_blocker(
    mutate: impl FnOnce(&mut StockEtfLaneScopedIpcCommandV1),
    expected: StockEtfLaneScopedIpcBlocker,
) {
    let mut contract = StockEtfLaneScopedIpcContractV1::accepted_fixture();
    mutate(command_mut(
        &mut contract,
        StockEtfLaneScopedIpcMethod::SubmitPaperOrder,
    ));
    assert_single_blocker(contract, expected);
}
