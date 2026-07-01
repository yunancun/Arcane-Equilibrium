//! ADR-0048 Stock/ETF broker capability registry acceptance tests.
//!
//! These tests validate the source-only operation matrix. They do not contact
//! IBKR, inspect secrets, create connectors, route orders, or change Bybit.

use std::path::PathBuf;

use openclaw_types::{
    evaluate_broker_operation, AssetLane, AuthorityScope, Broker, BrokerCapabilityRequest,
    BrokerEnvironment, BrokerOperation, InstrumentKind, StockEtfBrokerCapabilityBlocker,
    StockEtfBrokerCapabilityEntryV1, StockEtfBrokerCapabilityRegistryV1, StockEtfDenialReason,
    StockEtfFeatureFlags, StockEtfGateInputs, BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID,
    IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID, IBKR_SESSION_ATTESTATION_CONTRACT_ID,
    STOCK_ETF_BENCHMARK_VERSIONS_CONTRACT_ID, STOCK_ETF_BROKER_CAPABILITY_REGISTRY_ID,
    STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID, STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID,
    STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID,
    STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID,
    STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID, STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID,
    STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID, STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID,
    STOCK_ETF_RISK_POLICY_CONTRACT_ID, STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID,
    STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID, STOCK_SHADOW_FILL_MODEL_CONTRACT_ID,
};

#[test]
fn default_registry_blocks_without_matrix_or_boundaries() {
    use StockEtfBrokerCapabilityBlocker as Blocker;

    let verdict = StockEtfBrokerCapabilityRegistryV1::default().validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![
            Blocker::RegistryIdMismatch,
            Blocker::SourceVersionMismatch,
            Blocker::WrongAssetLane,
            Blocker::WrongBroker,
            Blocker::BybitLiveExecutionNotProtected,
            Blocker::PythonBrokerWriteAuthorityNotDenied,
            Blocker::IbkrLiveNotDenied,
            Blocker::CfdMarginReservedNotDenied,
            Blocker::RequiredAuditFieldMissing,
            Blocker::OperationMissing,
            Blocker::OperationMissing,
            Blocker::OperationMissing,
            Blocker::OperationMissing,
            Blocker::OperationMissing,
            Blocker::OperationMissing,
            Blocker::OperationMissing,
            Blocker::OperationMissing,
            Blocker::OperationMissing,
            Blocker::OperationMissing,
            Blocker::OperationMissing,
            Blocker::OperationMissing,
            Blocker::OperationMissing,
            Blocker::OperationMissing,
            Blocker::OperationMissing,
        ]
    );
}

#[test]
fn accepted_registry_contains_full_stock_etf_ibkr_operation_matrix() {
    let registry = StockEtfBrokerCapabilityRegistryV1::accepted_fixture();
    let verdict = registry.validate();

    assert!(
        verdict.accepted,
        "unexpected blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(
        registry.registry_id,
        STOCK_ETF_BROKER_CAPABILITY_REGISTRY_ID
    );
    assert_eq!(registry.source_version, 1);
    assert_eq!(registry.asset_lane, AssetLane::StockEtfCash);
    assert_eq!(registry.broker, Broker::Ibkr);
    assert!(registry.bybit_live_execution_unchanged);
    assert!(registry.python_broker_write_authority_denied);
    assert!(registry.ibkr_live_denied);
    assert!(registry.cfd_margin_reserved_denied);
    assert!(!registry.first_ibkr_contact_performed);
    assert!(!registry.secret_content_serialized);
    assert_eq!(registry.operations.len(), 15);
    assert!(registry.operations.iter().any(|entry| entry.operation
        == BrokerOperation::PaperOrderSubmit
        && entry.authority_scope == AuthorityScope::PaperRehearsal
        && entry.rust_owned
        && entry
            .required_gates
            .contains(&STOCK_ETF_RISK_POLICY_CONTRACT_ID.to_string())));
    assert!(registry.operations.iter().any(|entry| {
        entry.operation == BrokerOperation::HealthRead
            && entry
                .required_gates
                .contains(&STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID.to_string())
            && entry
                .required_gates
                .contains(&STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID.to_string())
    }));
    assert!(registry.operations.iter().any(|entry| {
        entry.operation == BrokerOperation::AccountSnapshotRead
            && entry
                .required_gates
                .contains(&STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID.to_string())
            && entry
                .required_gates
                .contains(&STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID.to_string())
    }));
    assert!(registry.operations.iter().any(|entry| {
        entry.operation == BrokerOperation::MarketDataRead
            && entry
                .required_gates
                .contains(&STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID.to_string())
            && entry
                .required_gates
                .contains(&STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID.to_string())
            && entry
                .required_gates
                .contains(&STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID.to_string())
    }));
    assert!(registry.operations.iter().any(|entry| {
        entry.operation == BrokerOperation::ContractDetailsRead
            && entry
                .required_gates
                .contains(&STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID.to_string())
            && entry
                .required_gates
                .contains(&STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID.to_string())
            && entry
                .required_gates
                .contains(&STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID.to_string())
    }));
    assert!(registry.operations.iter().any(|entry| {
        entry.operation == BrokerOperation::ShadowSignalEmit
            && entry
                .required_gates
                .contains(&STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID.to_string())
            && entry
                .required_gates
                .contains(&STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID.to_string())
            && entry
                .required_gates
                .contains(&STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID.to_string())
    }));
    assert!(registry.operations.iter().any(|entry| {
        entry.operation == BrokerOperation::ScorecardDerive
            && entry.required_gates.contains(
                &STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID.to_string(),
            )
            && entry
                .required_gates
                .contains(&BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID.to_string())
            && entry
                .required_gates
                .contains(&STOCK_ETF_RISK_POLICY_CONTRACT_ID.to_string())
            && entry
                .required_gates
                .contains(&STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID.to_string())
            && entry
                .required_gates
                .contains(&STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID.to_string())
            && entry
                .required_gates
                .contains(&STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID.to_string())
            && entry
                .required_gates
                .contains(&STOCK_ETF_BENCHMARK_VERSIONS_CONTRACT_ID.to_string())
            && entry
                .required_gates
                .contains(&STOCK_SHADOW_FILL_MODEL_CONTRACT_ID.to_string())
            && entry
                .required_gates
                .contains(&STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID.to_string())
            && entry
                .required_gates
                .contains(&STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID.to_string())
    }));
    assert!(registry.operations.iter().any(|entry| {
        entry.operation == BrokerOperation::ShadowFillReconstruct
            && entry
                .required_gates
                .contains(&STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID.to_string())
            && entry
                .required_gates
                .contains(&STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID.to_string())
            && entry
                .required_gates
                .contains(&STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID.to_string())
    }));
    assert!(registry
        .operations
        .iter()
        .any(|entry| entry.operation == BrokerOperation::LiveOrderSubmit
            && entry.authority_scope == AuthorityScope::Denied
            && entry.typed_denial_reason == Some(StockEtfDenialReason::IbkrLiveNotAuthorized)));
}

#[test]
fn registry_rejects_each_top_level_gap_independently() {
    assert_single_blocker(
        StockEtfBrokerCapabilityRegistryV1 {
            registry_id: String::new(),
            ..StockEtfBrokerCapabilityRegistryV1::accepted_fixture()
        },
        StockEtfBrokerCapabilityBlocker::RegistryIdMismatch,
    );
    assert_single_blocker(
        StockEtfBrokerCapabilityRegistryV1 {
            source_version: 2,
            ..StockEtfBrokerCapabilityRegistryV1::accepted_fixture()
        },
        StockEtfBrokerCapabilityBlocker::SourceVersionMismatch,
    );
    assert_single_blocker(
        StockEtfBrokerCapabilityRegistryV1 {
            asset_lane: AssetLane::CryptoPerp,
            ..StockEtfBrokerCapabilityRegistryV1::accepted_fixture()
        },
        StockEtfBrokerCapabilityBlocker::WrongAssetLane,
    );
    assert_single_blocker(
        StockEtfBrokerCapabilityRegistryV1 {
            broker: Broker::Bybit,
            ..StockEtfBrokerCapabilityRegistryV1::accepted_fixture()
        },
        StockEtfBrokerCapabilityBlocker::WrongBroker,
    );
    assert_single_blocker(
        StockEtfBrokerCapabilityRegistryV1 {
            bybit_live_execution_unchanged: false,
            ..StockEtfBrokerCapabilityRegistryV1::accepted_fixture()
        },
        StockEtfBrokerCapabilityBlocker::BybitLiveExecutionNotProtected,
    );
    assert_single_blocker(
        StockEtfBrokerCapabilityRegistryV1 {
            python_broker_write_authority_denied: false,
            ..StockEtfBrokerCapabilityRegistryV1::accepted_fixture()
        },
        StockEtfBrokerCapabilityBlocker::PythonBrokerWriteAuthorityNotDenied,
    );
    assert_single_blocker(
        StockEtfBrokerCapabilityRegistryV1 {
            ibkr_live_denied: false,
            ..StockEtfBrokerCapabilityRegistryV1::accepted_fixture()
        },
        StockEtfBrokerCapabilityBlocker::IbkrLiveNotDenied,
    );
    assert_single_blocker(
        StockEtfBrokerCapabilityRegistryV1 {
            cfd_margin_reserved_denied: false,
            ..StockEtfBrokerCapabilityRegistryV1::accepted_fixture()
        },
        StockEtfBrokerCapabilityBlocker::CfdMarginReservedNotDenied,
    );
    assert_single_blocker(
        StockEtfBrokerCapabilityRegistryV1 {
            first_ibkr_contact_performed: true,
            ..StockEtfBrokerCapabilityRegistryV1::accepted_fixture()
        },
        StockEtfBrokerCapabilityBlocker::FirstIbkrContactPerformed,
    );
    assert_single_blocker(
        StockEtfBrokerCapabilityRegistryV1 {
            secret_content_serialized: true,
            ..StockEtfBrokerCapabilityRegistryV1::accepted_fixture()
        },
        StockEtfBrokerCapabilityBlocker::SecretContentSerialized,
    );
    assert_single_blocker(
        StockEtfBrokerCapabilityRegistryV1 {
            required_audit_fields: Vec::new(),
            ..StockEtfBrokerCapabilityRegistryV1::accepted_fixture()
        },
        StockEtfBrokerCapabilityBlocker::RequiredAuditFieldMissing,
    );
}

#[test]
fn registry_rejects_each_operation_coverage_gap_independently() {
    let mut missing = StockEtfBrokerCapabilityRegistryV1::accepted_fixture();
    missing
        .operations
        .retain(|entry| entry.operation != BrokerOperation::MarketDataRead);
    assert_single_blocker(missing, StockEtfBrokerCapabilityBlocker::OperationMissing);

    let mut duplicated = StockEtfBrokerCapabilityRegistryV1::accepted_fixture();
    duplicated
        .operations
        .push(operation(&duplicated, BrokerOperation::HealthRead).clone());
    assert_single_blocker(
        duplicated,
        StockEtfBrokerCapabilityBlocker::OperationDuplicated,
    );
}

#[test]
fn registry_rejects_each_operation_shape_gap_independently() {
    assert_single_operation_blocker(
        BrokerOperation::PaperOrderSubmit,
        |entry| entry.authority_scope = AuthorityScope::ReadOnly,
        StockEtfBrokerCapabilityBlocker::OperationAuthorityScopeMismatch,
    );
    assert_single_operation_blocker(
        BrokerOperation::PaperOrderSubmit,
        |entry| {
            entry
                .required_gates
                .retain(|gate| gate != STOCK_ETF_RISK_POLICY_CONTRACT_ID)
        },
        StockEtfBrokerCapabilityBlocker::OperationRequiredGateMissing,
    );
    assert_single_operation_blocker(
        BrokerOperation::PaperOrderSubmit,
        |entry| entry.typed_denial_reason = Some(StockEtfDenialReason::LaneDisabled),
        StockEtfBrokerCapabilityBlocker::OperationTypedDenialMismatch,
    );
    assert_single_operation_blocker(
        BrokerOperation::PaperOrderSubmit,
        |entry| entry.rust_owned = false,
        StockEtfBrokerCapabilityBlocker::OperationRustOwnershipMismatch,
    );
    assert_single_operation_blocker(
        BrokerOperation::PaperOrderSubmit,
        |entry| entry.audit_event_required = false,
        StockEtfBrokerCapabilityBlocker::OperationAuditEventMissing,
    );
    assert_single_operation_blocker(
        BrokerOperation::PaperOrderSubmit,
        |entry| entry.source_artifact_hash_required = false,
        StockEtfBrokerCapabilityBlocker::OperationSourceArtifactHashMissing,
    );
    assert_single_operation_blocker(
        BrokerOperation::LiveOrderSubmit,
        |entry| entry.authority_scope = AuthorityScope::PaperRehearsal,
        StockEtfBrokerCapabilityBlocker::OperationAuthorityScopeMismatch,
    );
    assert_single_operation_blocker(
        BrokerOperation::LiveOrderSubmit,
        |entry| entry.typed_denial_reason = None,
        StockEtfBrokerCapabilityBlocker::OperationTypedDenialMismatch,
    );
    assert_single_operation_blocker(
        BrokerOperation::PaperOrderFillImport,
        |entry| entry.authority_scope = AuthorityScope::PaperRehearsal,
        StockEtfBrokerCapabilityBlocker::OperationAuthorityScopeMismatch,
    );
    assert_single_operation_blocker(
        BrokerOperation::PaperOrderFillImport,
        |entry| entry.rust_owned = true,
        StockEtfBrokerCapabilityBlocker::OperationRustOwnershipMismatch,
    );
}

#[test]
fn readonly_rows_require_lane_scoped_ipc_and_probe_request_gate() {
    use StockEtfBrokerCapabilityBlocker as Blocker;

    let mut registry = StockEtfBrokerCapabilityRegistryV1::accepted_fixture();
    for operation in [
        BrokerOperation::HealthRead,
        BrokerOperation::AccountSnapshotRead,
        BrokerOperation::MarketDataRead,
        BrokerOperation::ContractDetailsRead,
    ] {
        let row = registry
            .operations
            .iter_mut()
            .find(|entry| entry.operation == operation)
            .expect("read row");
        row.required_gates.retain(|gate| {
            gate != STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID
                && gate != STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID
        });
    }

    let blockers = registry.validate().blockers;

    assert_eq!(
        blockers,
        vec![
            Blocker::OperationRequiredGateMissing,
            Blocker::OperationRequiredGateMissing,
            Blocker::OperationRequiredGateMissing,
            Blocker::OperationRequiredGateMissing,
        ]
    );
}

#[test]
fn registry_requires_exact_id_and_source_version() {
    use StockEtfBrokerCapabilityBlocker as Blocker;

    let mut registry = StockEtfBrokerCapabilityRegistryV1::accepted_fixture();
    registry.registry_id = "broker_capability_registry_v1_fixture".to_string();
    registry.source_version = 2;

    let blockers = registry.validate().blockers;

    assert_eq!(
        blockers,
        vec![Blocker::RegistryIdMismatch, Blocker::SourceVersionMismatch]
    );
}

#[test]
fn registry_requires_every_operation_once() {
    use StockEtfBrokerCapabilityBlocker as Blocker;

    let mut registry = StockEtfBrokerCapabilityRegistryV1::accepted_fixture();
    let duplicate = registry.operations[0].clone();
    registry
        .operations
        .retain(|entry| entry.operation != BrokerOperation::MarketDataRead);
    registry.operations.push(duplicate);

    let blockers = registry.validate().blockers;

    assert_eq!(
        blockers,
        vec![Blocker::OperationDuplicated, Blocker::OperationMissing]
    );
}

#[test]
fn paper_write_rows_require_rust_owned_gates_audit_and_source_hash() {
    use StockEtfBrokerCapabilityBlocker as Blocker;

    let mut registry = StockEtfBrokerCapabilityRegistryV1::accepted_fixture();
    let submit = registry
        .operations
        .iter_mut()
        .find(|entry| entry.operation == BrokerOperation::PaperOrderSubmit)
        .expect("paper submit row");
    submit.rust_owned = false;
    submit.required_gates.clear();
    submit.audit_event_required = false;
    submit.source_artifact_hash_required = false;

    let blockers = registry.validate().blockers;

    assert_eq!(
        blockers,
        vec![
            Blocker::OperationRequiredGateMissing,
            Blocker::OperationRustOwnershipMismatch,
            Blocker::OperationAuditEventMissing,
            Blocker::OperationSourceArtifactHashMissing,
        ]
    );
}

#[test]
fn paper_fill_import_row_is_readonly_and_requires_session_lifecycle_gate() {
    let registry = StockEtfBrokerCapabilityRegistryV1::accepted_fixture();
    let fill_import = registry
        .operations
        .iter()
        .find(|entry| entry.operation == BrokerOperation::PaperOrderFillImport)
        .expect("paper fill import row");

    assert_eq!(fill_import.authority_scope, AuthorityScope::ReadOnly);
    assert_eq!(fill_import.typed_denial_reason, None);
    assert!(!fill_import.rust_owned);
    assert!(fill_import.audit_event_required);
    assert!(fill_import.source_artifact_hash_required);
    assert!(fill_import
        .required_gates
        .contains(&IBKR_SESSION_ATTESTATION_CONTRACT_ID.to_string()));
    assert!(fill_import
        .required_gates
        .contains(&IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID.to_string()));

    let mut broken = registry;
    let fill_import = broken
        .operations
        .iter_mut()
        .find(|entry| entry.operation == BrokerOperation::PaperOrderFillImport)
        .expect("paper fill import row");
    fill_import.authority_scope = AuthorityScope::PaperRehearsal;
    fill_import.required_gates.retain(|gate| {
        gate != IBKR_SESSION_ATTESTATION_CONTRACT_ID
            && gate != IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID
    });
    fill_import.rust_owned = true;
    fill_import.audit_event_required = false;
    fill_import.source_artifact_hash_required = false;

    let blockers = broken.validate().blockers;

    assert_eq!(
        blockers,
        vec![
            StockEtfBrokerCapabilityBlocker::OperationAuthorityScopeMismatch,
            StockEtfBrokerCapabilityBlocker::OperationRequiredGateMissing,
            StockEtfBrokerCapabilityBlocker::OperationRustOwnershipMismatch,
            StockEtfBrokerCapabilityBlocker::OperationAuditEventMissing,
            StockEtfBrokerCapabilityBlocker::OperationSourceArtifactHashMissing,
        ]
    );
}

#[test]
fn denied_rows_require_exact_typed_denials_and_no_authority() {
    use StockEtfBrokerCapabilityBlocker as Blocker;

    let mut registry = StockEtfBrokerCapabilityRegistryV1::accepted_fixture();
    let live = registry
        .operations
        .iter_mut()
        .find(|entry| entry.operation == BrokerOperation::LiveOrderSubmit)
        .expect("live row");
    live.authority_scope = AuthorityScope::PaperRehearsal;
    live.typed_denial_reason = None;

    let transfer = registry
        .operations
        .iter_mut()
        .find(|entry| entry.operation == BrokerOperation::TransferOrAccountWrite)
        .expect("transfer row");
    transfer.typed_denial_reason = Some(StockEtfDenialReason::IbkrLiveNotAuthorized);

    let blockers = registry.validate().blockers;

    assert_eq!(
        blockers,
        vec![
            Blocker::OperationAuthorityScopeMismatch,
            Blocker::OperationTypedDenialMismatch,
            Blocker::OperationTypedDenialMismatch,
        ]
    );
}

#[test]
fn registry_boundary_flags_reject_contact_secret_and_bybit_regression() {
    use StockEtfBrokerCapabilityBlocker as Blocker;

    let mut registry = StockEtfBrokerCapabilityRegistryV1::accepted_fixture();
    registry.bybit_live_execution_unchanged = false;
    registry.python_broker_write_authority_denied = false;
    registry.ibkr_live_denied = false;
    registry.cfd_margin_reserved_denied = false;
    registry.first_ibkr_contact_performed = true;
    registry.secret_content_serialized = true;
    registry.required_audit_fields.clear();

    let blockers = registry.validate().blockers;

    assert_eq!(
        blockers,
        vec![
            Blocker::BybitLiveExecutionNotProtected,
            Blocker::PythonBrokerWriteAuthorityNotDenied,
            Blocker::IbkrLiveNotDenied,
            Blocker::CfdMarginReservedNotDenied,
            Blocker::FirstIbkrContactPerformed,
            Blocker::SecretContentSerialized,
            Blocker::RequiredAuditFieldMissing,
        ]
    );
}

#[test]
fn evaluator_and_registry_agree_on_denied_live_and_paper_gate_shape() {
    let registry = StockEtfBrokerCapabilityRegistryV1::accepted_fixture();
    assert!(registry.validate().accepted);

    let flags = StockEtfFeatureFlags {
        stock_etf_lane_enabled: true,
        ibkr_readonly_enabled: true,
        ibkr_paper_enabled: true,
        stock_etf_shadow_only: false,
        ..StockEtfFeatureFlags::default()
    };
    let gates = StockEtfGateInputs {
        external_surface_gate_passed: true,
        session_attested: true,
        scoped_authorization_present: true,
        decision_lease_valid: true,
        guardian_allows: true,
        risk_config_hash_present: true,
        instrument_identity_hash_present: true,
        idempotency_key_present: true,
        cost_model_present: true,
        universe_match: true,
        credential_available: true,
        connector_available: true,
        ..StockEtfGateInputs::default()
    };

    let paper = evaluate_broker_operation(
        BrokerCapabilityRequest::stock_etf_ibkr_paper(
            InstrumentKind::Stock,
            BrokerOperation::PaperOrderSubmit,
        ),
        &flags,
        &gates,
    );
    assert!(paper.allowed);
    assert_eq!(paper.authority_scope, AuthorityScope::PaperRehearsal);

    let live = evaluate_broker_operation(
        BrokerCapabilityRequest {
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            environment: BrokerEnvironment::Paper,
            instrument_kind: InstrumentKind::Stock,
            operation: BrokerOperation::LiveOrderSubmit,
        },
        &flags,
        &gates,
    );
    assert!(!live.allowed);
    assert_eq!(
        live.denial_reason,
        Some(StockEtfDenialReason::IbkrLiveNotAuthorized)
    );
}

#[test]
fn blocked_template_is_parseable_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/stock_etf_broker_capability_registry.template.toml"),
    )
    .expect("read broker capability registry template");
    let parsed: StockEtfBrokerCapabilityRegistryV1 =
        toml::from_str(&raw).expect("broker capability registry template parses");

    assert_eq!(parsed.registry_id, "");
    assert_eq!(parsed.source_version, 0);
    assert_eq!(parsed.asset_lane, AssetLane::CryptoPerp);
    assert_eq!(parsed.broker, Broker::Bybit);
    assert!(!parsed.bybit_live_execution_unchanged);
    assert!(!parsed.python_broker_write_authority_denied);
    assert!(!parsed.validate().accepted);

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}

fn assert_single_blocker(
    registry: StockEtfBrokerCapabilityRegistryV1,
    expected: StockEtfBrokerCapabilityBlocker,
) {
    let verdict = registry.validate();

    assert!(!verdict.accepted);
    assert_eq!(verdict.blockers, vec![expected]);
}

fn assert_single_operation_blocker(
    operation_kind: BrokerOperation,
    mutate: impl FnOnce(&mut StockEtfBrokerCapabilityEntryV1),
    expected: StockEtfBrokerCapabilityBlocker,
) {
    let mut registry = StockEtfBrokerCapabilityRegistryV1::accepted_fixture();
    mutate(operation_mut(&mut registry, operation_kind));
    assert_single_blocker(registry, expected);
}

fn operation(
    registry: &StockEtfBrokerCapabilityRegistryV1,
    operation_kind: BrokerOperation,
) -> &StockEtfBrokerCapabilityEntryV1 {
    registry
        .operations
        .iter()
        .find(|entry| entry.operation == operation_kind)
        .expect("broker capability operation exists")
}

fn operation_mut(
    registry: &mut StockEtfBrokerCapabilityRegistryV1,
    operation_kind: BrokerOperation,
) -> &mut StockEtfBrokerCapabilityEntryV1 {
    registry
        .operations
        .iter_mut()
        .find(|entry| entry.operation == operation_kind)
        .expect("broker capability operation exists")
}
