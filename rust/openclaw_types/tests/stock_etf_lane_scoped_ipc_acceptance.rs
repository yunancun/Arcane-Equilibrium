//! ADR-0048 Stock/ETF lane-scoped IPC acceptance tests.
//!
//! These tests validate the source-only Rust IPC contract matrix. They do not
//! start IPC, contact IBKR, inspect secrets, create connectors, submit paper
//! orders, or mutate existing Bybit behavior.

use std::path::PathBuf;

use openclaw_types::{
    AssetLane, AuthorityScope, Broker, BrokerOperation, StockEtfDenialReason,
    StockEtfLaneScopedIpcBlocker, StockEtfLaneScopedIpcCommandV1, StockEtfLaneScopedIpcContractV1,
    StockEtfLaneScopedIpcMethod, STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID,
    STOCK_ETF_SCOPED_AUTHORIZATION_CONTRACT_ID,
};

#[test]
fn default_lane_scoped_ipc_contract_blocks_all_authority() {
    use StockEtfLaneScopedIpcBlocker as Blocker;

    let verdict = StockEtfLaneScopedIpcContractV1::default().validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![
            Blocker::ContractIdMismatch,
            Blocker::SourceVersionMismatch,
            Blocker::WrongAssetLane,
            Blocker::WrongBroker,
            Blocker::RustAuthorityOwnerMissing,
            Blocker::PythonForwardOnlyMissing,
            Blocker::PythonDirectBrokerWriteNotDenied,
            Blocker::BybitIpcReuseNotDenied,
            Blocker::ExistingBybitPaperPathNotDenied,
            Blocker::LiveEnvironmentNotDenied,
            Blocker::BybitLiveExecutionNotProtected,
            Blocker::CommandMissing,
            Blocker::CommandMissing,
            Blocker::CommandMissing,
            Blocker::CommandMissing,
            Blocker::CommandMissing,
            Blocker::CommandMissing,
            Blocker::CommandMissing,
            Blocker::CommandMissing,
            Blocker::CommandMissing,
            Blocker::CommandMissing,
            Blocker::CommandMissing,
            Blocker::CommandMissing,
            Blocker::CommandMissing,
            Blocker::CommandMissing,
            Blocker::CommandMissing,
            Blocker::CommandMissing,
            Blocker::CommandMissing,
            Blocker::CommandMissing,
            Blocker::CommandMissing,
            Blocker::CommandMissing,
            Blocker::CommandMissing,
        ]
    );
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
    assert_eq!(contract.commands.len(), 21);

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

    let preview = contract
        .commands
        .iter()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::PreviewPaperOrder)
        .expect("preview method exists");
    assert!(!preview.effect_capable);
    assert_eq!(preview.authority_scope, AuthorityScope::ReadOnly);

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

    // W4:connection-health 唯讀查詢——DisplayOnly、effect 不可、Rust 不擁 authority。
    let connection_health = contract
        .commands
        .iter()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::GetConnectionHealth)
        .expect("connection-health method exists");
    assert_eq!(connection_health.operation, BrokerOperation::HealthRead);
    assert_eq!(
        connection_health.authority_scope,
        AuthorityScope::DisplayOnly
    );
    assert!(!connection_health.effect_capable);
    assert!(!connection_health.rust_owned);

    let shadow = contract
        .commands
        .iter()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::EvaluateShadowSignal)
        .expect("shadow method exists");
    assert_eq!(shadow.operation, BrokerOperation::ShadowSignalEmit);
    assert_eq!(shadow.authority_scope, AuthorityScope::ShadowOnly);
    assert!(!shadow.effect_capable);
    assert!(!shadow.rust_owned);

    let readonly_probe = contract
        .commands
        .iter()
        .find(|command| command.method == StockEtfLaneScopedIpcMethod::PreviewReadonlyProbe)
        .expect("readonly-probe preview method exists");
    assert_eq!(readonly_probe.operation, BrokerOperation::HealthRead);
    assert_eq!(readonly_probe.authority_scope, AuthorityScope::ReadOnly);
    assert!(!readonly_probe.effect_capable);
    assert!(readonly_probe.rust_owned);
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
    assert_single_blocker(
        cancel_cross_wired_as_submit,
        StockEtfLaneScopedIpcBlocker::CommandRequestFieldMissing,
    );

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
    assert_single_blocker(
        replace_cross_wired_as_cancel,
        StockEtfLaneScopedIpcBlocker::CommandRequestFieldMissing,
    );

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
    assert_single_blocker(
        submit_cross_wired_as_cancel,
        StockEtfLaneScopedIpcBlocker::CommandRequestFieldMissing,
    );
}

#[test]
fn lane_scoped_ipc_requires_exact_contract_id_and_source_version() {
    let contract = StockEtfLaneScopedIpcContractV1 {
        contract_id: "lane_scoped_ipc_v1_fixture".to_string(),
        source_version: 2,
        ..StockEtfLaneScopedIpcContractV1::accepted_fixture()
    };
    let blockers = contract.validate().blockers;

    assert_eq!(
        blockers,
        vec![
            StockEtfLaneScopedIpcBlocker::ContractIdMismatch,
            StockEtfLaneScopedIpcBlocker::SourceVersionMismatch,
        ]
    );
}

#[test]
fn lane_scoped_ipc_rejects_top_level_boundary_regressions() {
    use StockEtfLaneScopedIpcBlocker as Blocker;

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

    assert_eq!(
        blockers,
        vec![
            Blocker::ContractIdMismatch,
            Blocker::WrongAssetLane,
            Blocker::WrongBroker,
            Blocker::RustAuthorityOwnerMissing,
            Blocker::PythonForwardOnlyMissing,
            Blocker::PythonDirectBrokerWriteNotDenied,
            Blocker::BybitIpcReuseNotDenied,
            Blocker::ExistingBybitPaperPathNotDenied,
            Blocker::LiveEnvironmentNotDenied,
            Blocker::BybitLiveExecutionNotProtected,
            Blocker::IbkrContactPerformed,
            Blocker::ConnectorRuntimeStarted,
            Blocker::SecretContentSerialized,
        ]
    );
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

    assert_eq!(
        blockers,
        vec![
            StockEtfLaneScopedIpcBlocker::CommandDuplicated,
            StockEtfLaneScopedIpcBlocker::CommandMissing,
        ]
    );
}

#[test]
fn paper_effect_methods_require_gates_fields_denials_and_rust_ownership() {
    use StockEtfLaneScopedIpcBlocker as Blocker;

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

    assert_eq!(
        blockers,
        vec![
            Blocker::CommandOperationMismatch,
            Blocker::CommandAuthorityScopeMismatch,
            Blocker::CommandEffectCapabilityMismatch,
            Blocker::CommandRustOwnershipMismatch,
            Blocker::CommandRequiredGateMissing,
            Blocker::CommandRequestFieldMissing,
            Blocker::CommandDenialReasonMissing,
        ]
    );
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

    assert_eq!(
        blockers,
        vec![
            StockEtfLaneScopedIpcBlocker::CommandMethodDenied,
            StockEtfLaneScopedIpcBlocker::CommandMissing,
        ]
    );
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
