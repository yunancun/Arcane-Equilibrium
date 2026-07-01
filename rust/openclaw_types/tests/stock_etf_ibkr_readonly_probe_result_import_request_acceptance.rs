//! ADR-0048 Stock/ETF IBKR read-only probe result import request tests.
//!
//! These tests validate source-only import-request shape. They must not contact
//! IBKR, inspect secrets, create connectors, import evidence, apply DB changes,
//! route orders, or mutate Bybit behavior.

use std::path::PathBuf;

use openclaw_types::{
    AssetLane, AuthorityScope, Broker, BrokerEnvironment, BrokerOperation, NonBybitApiAction,
    StockEtfIbkrReadonlyProbeKind, StockEtfIbkrReadonlyProbeResultImportBlocker,
    StockEtfIbkrReadonlyProbeResultImportRequestV1,
    BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID, BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID,
    IBKR_AUDIT_EVENT_POLICY_CONTRACT_ID, IBKR_REDACTION_POLICY_CONTRACT_ID,
    IBKR_SESSION_ATTESTATION_CONTRACT_ID, NON_BYBIT_API_ALLOWLIST_CONTRACT_ID,
    STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID,
    STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID,
    STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID, STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID,
};

#[test]
fn default_result_import_request_blocks_all_authority() {
    use StockEtfIbkrReadonlyProbeResultImportBlocker as Blocker;

    let verdict = StockEtfIbkrReadonlyProbeResultImportRequestV1::default().validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![
            Blocker::ContractIdMismatch,
            Blocker::SourceVersionMismatch,
            Blocker::WrongAssetLane,
            Blocker::WrongBroker,
            Blocker::EnvironmentDenied,
            Blocker::ProbeActionMismatch,
            Blocker::OperationMismatch,
            Blocker::AuthorityScopeMismatch,
            Blocker::ApiActionNotReadAllowed,
            Blocker::ResultImportRequestIdMissing,
            Blocker::RequestIdMissing,
            Blocker::ProbeIdMissing,
            Blocker::ReadonlyProbeRequestContractIdMismatch,
            Blocker::ReadonlyProbeRequestHashInvalid,
            Blocker::SessionAttestationContractIdMismatch,
            Blocker::SessionAttestationHashInvalid,
            Blocker::ApiAllowlistContractIdMismatch,
            Blocker::ApiAllowlistHashInvalid,
            Blocker::RedactionPolicyContractIdMismatch,
            Blocker::RedactionPolicyHashInvalid,
            Blocker::AuditEventPolicyContractIdMismatch,
            Blocker::AuditEventPolicyHashInvalid,
            Blocker::ResultPayloadHashInvalid,
            Blocker::RawArtifactHashInvalid,
            Blocker::RedactedSummaryHashInvalid,
            Blocker::SourceArtifactHashInvalid,
            Blocker::ResultAsOfMissing,
            Blocker::ImportRequestedAtMissing,
            Blocker::IdempotencyKeyMissing,
            Blocker::HealthSnapshotHashInvalid,
        ]
    );
}

#[test]
fn accepted_result_import_request_validates_without_side_effects() {
    let request = StockEtfIbkrReadonlyProbeResultImportRequestV1::accepted_fixture();
    let verdict = request.validate();

    assert!(
        verdict.accepted,
        "unexpected blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(
        request.contract_id,
        STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID
    );
    assert_eq!(request.source_version, 1);
    assert_eq!(request.asset_lane, AssetLane::StockEtfCash);
    assert_eq!(request.broker, Broker::Ibkr);
    assert_eq!(request.environment, BrokerEnvironment::ReadOnly);
    assert_eq!(
        request.probe_kind,
        StockEtfIbkrReadonlyProbeKind::ConnectionHealth
    );
    assert_eq!(request.api_action, NonBybitApiAction::ConnectionHealthRead);
    assert_eq!(request.operation, BrokerOperation::HealthRead);
    assert_eq!(request.authority_scope, AuthorityScope::ReadOnly);
    assert_eq!(
        request.readonly_probe_request_contract_id,
        STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID
    );
    assert_eq!(
        request.session_attestation_contract_id,
        IBKR_SESSION_ATTESTATION_CONTRACT_ID
    );
    assert_eq!(
        request.api_allowlist_contract_id,
        NON_BYBIT_API_ALLOWLIST_CONTRACT_ID
    );
    assert_eq!(
        request.redaction_policy_contract_id,
        IBKR_REDACTION_POLICY_CONTRACT_ID
    );
    assert_eq!(
        request.audit_event_policy_contract_id,
        IBKR_AUDIT_EVENT_POLICY_CONTRACT_ID
    );
    assert!(!request.effect_capable);
    assert!(!request.ibkr_contact_performed);
    assert!(!request.connector_runtime_started);
    assert!(!request.secret_content_serialized);
    assert!(!request.result_import_performed);
    assert!(!request.evidence_writer_started);
    assert!(!request.scorecard_writer_started);
    assert!(!request.db_apply_performed);
    assert!(!request.order_routed);
    assert!(!request.paper_order_submitted);
    assert!(!request.bybit_path_reused);
}

#[test]
fn result_import_request_requires_common_lineage_and_artifacts() {
    use StockEtfIbkrReadonlyProbeResultImportBlocker as Blocker;

    let bad = StockEtfIbkrReadonlyProbeResultImportRequestV1 {
        result_import_request_id: String::new(),
        request_id: String::new(),
        probe_id: String::new(),
        readonly_probe_request_contract_id: "wrong".to_string(),
        readonly_probe_request_hash: "not_hash".to_string(),
        session_attestation_contract_id: "wrong".to_string(),
        session_attestation_hash: String::new(),
        api_allowlist_contract_id: "wrong".to_string(),
        api_allowlist_hash: String::new(),
        redaction_policy_contract_id: "wrong".to_string(),
        redaction_policy_hash: String::new(),
        audit_event_policy_contract_id: "wrong".to_string(),
        audit_event_policy_hash: String::new(),
        result_payload_hash: String::new(),
        raw_artifact_hash: String::new(),
        redacted_summary_hash: String::new(),
        source_artifact_hash: String::new(),
        result_as_of_ms: 2,
        import_requested_at_ms: 1,
        idempotency_key: String::new(),
        ..StockEtfIbkrReadonlyProbeResultImportRequestV1::accepted_fixture()
    };
    let verdict = bad.validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![
            Blocker::ResultImportRequestIdMissing,
            Blocker::RequestIdMissing,
            Blocker::ProbeIdMissing,
            Blocker::ReadonlyProbeRequestContractIdMismatch,
            Blocker::ReadonlyProbeRequestHashInvalid,
            Blocker::SessionAttestationContractIdMismatch,
            Blocker::SessionAttestationHashInvalid,
            Blocker::ApiAllowlistContractIdMismatch,
            Blocker::ApiAllowlistHashInvalid,
            Blocker::RedactionPolicyContractIdMismatch,
            Blocker::RedactionPolicyHashInvalid,
            Blocker::AuditEventPolicyContractIdMismatch,
            Blocker::AuditEventPolicyHashInvalid,
            Blocker::ResultPayloadHashInvalid,
            Blocker::RawArtifactHashInvalid,
            Blocker::RedactedSummaryHashInvalid,
            Blocker::SourceArtifactHashInvalid,
            Blocker::ResultAsOfAfterImportRequested,
            Blocker::IdempotencyKeyMissing,
        ]
    );
}

#[test]
fn result_import_kind_requires_matching_downstream_lineage() {
    let account = StockEtfIbkrReadonlyProbeResultImportRequestV1 {
        probe_kind: StockEtfIbkrReadonlyProbeKind::AccountSummarySnapshot,
        api_action: NonBybitApiAction::AccountSummarySnapshotRead,
        operation: BrokerOperation::AccountSnapshotRead,
        account_cash_ledger_contract_id: BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID
            .to_string(),
        account_cash_ledger_hash: "b".repeat(64),
        ..StockEtfIbkrReadonlyProbeResultImportRequestV1::accepted_fixture()
    };
    assert!(account.validate().accepted);

    let bad_account = StockEtfIbkrReadonlyProbeResultImportRequestV1 {
        account_cash_ledger_contract_id: "wrong".to_string(),
        account_cash_ledger_hash: String::new(),
        ..account
    };
    let verdict = bad_account.validate();
    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![
            StockEtfIbkrReadonlyProbeResultImportBlocker::AccountCashLedgerContractIdMismatch,
            StockEtfIbkrReadonlyProbeResultImportBlocker::AccountCashLedgerHashInvalid,
        ]
    );

    let market = StockEtfIbkrReadonlyProbeResultImportRequestV1 {
        probe_kind: StockEtfIbkrReadonlyProbeKind::MarketDataSnapshot,
        api_action: NonBybitApiAction::MarketDataSnapshotRead,
        operation: BrokerOperation::MarketDataRead,
        market_data_provenance_contract_id: STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID.to_string(),
        market_data_provenance_hash: "c".repeat(64),
        ..StockEtfIbkrReadonlyProbeResultImportRequestV1::accepted_fixture()
    };
    assert!(market.validate().accepted);

    let contract_details = StockEtfIbkrReadonlyProbeResultImportRequestV1 {
        probe_kind: StockEtfIbkrReadonlyProbeKind::ContractDetails,
        api_action: NonBybitApiAction::ContractDetailsRead,
        operation: BrokerOperation::ContractDetailsRead,
        instrument_identity_contract_id: STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID.to_string(),
        instrument_identity_hash: "d".repeat(64),
        ..StockEtfIbkrReadonlyProbeResultImportRequestV1::accepted_fixture()
    };
    assert!(contract_details.validate().accepted);

    let open_orders = StockEtfIbkrReadonlyProbeResultImportRequestV1 {
        probe_kind: StockEtfIbkrReadonlyProbeKind::OpenPaperOrders,
        api_action: NonBybitApiAction::OpenPaperOrdersRead,
        operation: BrokerOperation::AccountSnapshotRead,
        broker_lifecycle_event_log_contract_id: BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID.to_string(),
        broker_lifecycle_event_log_hash: "e".repeat(64),
        ..StockEtfIbkrReadonlyProbeResultImportRequestV1::accepted_fixture()
    };
    assert!(open_orders.validate().accepted);
}

#[test]
fn result_import_request_rejects_probe_action_operation_cross_wire() {
    use StockEtfIbkrReadonlyProbeResultImportBlocker as Blocker;

    let market_with_account_action = StockEtfIbkrReadonlyProbeResultImportRequestV1 {
        probe_kind: StockEtfIbkrReadonlyProbeKind::MarketDataSnapshot,
        api_action: NonBybitApiAction::AccountSummarySnapshotRead,
        operation: BrokerOperation::MarketDataRead,
        market_data_provenance_contract_id: STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID.to_string(),
        market_data_provenance_hash: "c".repeat(64),
        ..StockEtfIbkrReadonlyProbeResultImportRequestV1::accepted_fixture()
    };
    let verdict = market_with_account_action.validate();

    assert!(!verdict.accepted);
    assert_eq!(verdict.blockers, vec![Blocker::ProbeActionMismatch]);

    let market_with_account_operation = StockEtfIbkrReadonlyProbeResultImportRequestV1 {
        probe_kind: StockEtfIbkrReadonlyProbeKind::MarketDataSnapshot,
        api_action: NonBybitApiAction::MarketDataSnapshotRead,
        operation: BrokerOperation::AccountSnapshotRead,
        market_data_provenance_contract_id: STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID.to_string(),
        market_data_provenance_hash: "c".repeat(64),
        ..StockEtfIbkrReadonlyProbeResultImportRequestV1::accepted_fixture()
    };
    let verdict = market_with_account_operation.validate();

    assert!(!verdict.accepted);
    assert_eq!(verdict.blockers, vec![Blocker::OperationMismatch]);

    let paper_write_action = StockEtfIbkrReadonlyProbeResultImportRequestV1 {
        api_action: NonBybitApiAction::PaperOrderSubmit,
        operation: BrokerOperation::HealthRead,
        ..StockEtfIbkrReadonlyProbeResultImportRequestV1::accepted_fixture()
    };
    let verdict = paper_write_action.validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![
            Blocker::ProbeActionMismatch,
            Blocker::ApiActionNotReadAllowed,
        ]
    );
}

#[test]
fn result_import_request_rejects_each_authority_gap_independently() {
    use StockEtfIbkrReadonlyProbeResultImportBlocker as Blocker;

    let cases: [(
        fn(&mut StockEtfIbkrReadonlyProbeResultImportRequestV1),
        Blocker,
    ); 9] = [
        (
            |request| {
                request.contract_id =
                    "stock_etf_ibkr_readonly_probe_result_import_request_v1_fixture".to_string()
            },
            Blocker::ContractIdMismatch,
        ),
        (
            |request| request.source_version = 2,
            Blocker::SourceVersionMismatch,
        ),
        (
            |request| request.asset_lane = AssetLane::CryptoPerp,
            Blocker::WrongAssetLane,
        ),
        (
            |request| request.broker = Broker::Bybit,
            Blocker::WrongBroker,
        ),
        (
            |request| request.environment = BrokerEnvironment::LiveReservedDenied,
            Blocker::EnvironmentDenied,
        ),
        (
            |request| request.api_action = NonBybitApiAction::AccountSummarySnapshotRead,
            Blocker::ProbeActionMismatch,
        ),
        (
            |request| request.operation = BrokerOperation::AccountSnapshotRead,
            Blocker::OperationMismatch,
        ),
        (
            |request| request.authority_scope = AuthorityScope::PaperRehearsal,
            Blocker::AuthorityScopeMismatch,
        ),
        (
            |request| request.effect_capable = true,
            Blocker::EffectCapabilityPresent,
        ),
    ];

    for (mutate, blocker) in cases {
        let mut request = StockEtfIbkrReadonlyProbeResultImportRequestV1::accepted_fixture();
        mutate(&mut request);
        assert_single_blocker(request, blocker);
    }
}

#[test]
fn result_import_request_rejects_each_common_lineage_gap_independently() {
    use StockEtfIbkrReadonlyProbeResultImportBlocker as Blocker;

    let cases: [(
        fn(&mut StockEtfIbkrReadonlyProbeResultImportRequestV1),
        Blocker,
    ); 23] = [
        (
            |request| request.result_import_request_id.clear(),
            Blocker::ResultImportRequestIdMissing,
        ),
        (
            |request| request.request_id.clear(),
            Blocker::RequestIdMissing,
        ),
        (|request| request.probe_id.clear(), Blocker::ProbeIdMissing),
        (
            |request| request.readonly_probe_request_contract_id = "wrong".to_string(),
            Blocker::ReadonlyProbeRequestContractIdMismatch,
        ),
        (
            |request| request.readonly_probe_request_hash.clear(),
            Blocker::ReadonlyProbeRequestHashInvalid,
        ),
        (
            |request| request.session_attestation_contract_id = "wrong".to_string(),
            Blocker::SessionAttestationContractIdMismatch,
        ),
        (
            |request| request.session_attestation_hash.clear(),
            Blocker::SessionAttestationHashInvalid,
        ),
        (
            |request| request.api_allowlist_contract_id = "wrong".to_string(),
            Blocker::ApiAllowlistContractIdMismatch,
        ),
        (
            |request| request.api_allowlist_hash.clear(),
            Blocker::ApiAllowlistHashInvalid,
        ),
        (
            |request| request.redaction_policy_contract_id = "wrong".to_string(),
            Blocker::RedactionPolicyContractIdMismatch,
        ),
        (
            |request| request.redaction_policy_hash.clear(),
            Blocker::RedactionPolicyHashInvalid,
        ),
        (
            |request| request.audit_event_policy_contract_id = "wrong".to_string(),
            Blocker::AuditEventPolicyContractIdMismatch,
        ),
        (
            |request| request.audit_event_policy_hash.clear(),
            Blocker::AuditEventPolicyHashInvalid,
        ),
        (
            |request| request.health_snapshot_hash.clear(),
            Blocker::HealthSnapshotHashInvalid,
        ),
        (
            |request| request.result_payload_hash.clear(),
            Blocker::ResultPayloadHashInvalid,
        ),
        (
            |request| request.raw_artifact_hash.clear(),
            Blocker::RawArtifactHashInvalid,
        ),
        (
            |request| request.redacted_summary_hash.clear(),
            Blocker::RedactedSummaryHashInvalid,
        ),
        (
            |request| request.source_artifact_hash.clear(),
            Blocker::SourceArtifactHashInvalid,
        ),
        (
            |request| request.result_as_of_ms = 0,
            Blocker::ResultAsOfMissing,
        ),
        (
            |request| request.result_as_of_ms = request.import_requested_at_ms + 1,
            Blocker::ResultAsOfAfterImportRequested,
        ),
        (
            |request| request.idempotency_key.clear(),
            Blocker::IdempotencyKeyMissing,
        ),
        (
            |request| request.duplicate_import_detected = true,
            Blocker::DuplicateImportDetected,
        ),
        (
            |request| request.stale_result_without_manual_review = true,
            Blocker::StaleResultWithoutManualReview,
        ),
    ];

    for (mutate, blocker) in cases {
        let mut request = StockEtfIbkrReadonlyProbeResultImportRequestV1::accepted_fixture();
        mutate(&mut request);
        assert_single_blocker(request, blocker);
    }

    let mut missing_import_time =
        StockEtfIbkrReadonlyProbeResultImportRequestV1::accepted_fixture();
    missing_import_time.import_requested_at_ms = 0;
    let verdict = missing_import_time.validate();
    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![
            Blocker::ImportRequestedAtMissing,
            Blocker::ResultAsOfAfterImportRequested,
        ]
    );
}

#[test]
fn result_import_request_rejects_each_kind_lineage_gap_independently() {
    use StockEtfIbkrReadonlyProbeResultImportBlocker as Blocker;

    let mut account_contract = accepted_account_result_import();
    account_contract.account_cash_ledger_contract_id = "wrong".to_string();
    assert_single_blocker(
        account_contract,
        Blocker::AccountCashLedgerContractIdMismatch,
    );

    let mut account_hash = accepted_account_result_import();
    account_hash.account_cash_ledger_hash.clear();
    assert_single_blocker(account_hash, Blocker::AccountCashLedgerHashInvalid);

    let mut market_contract = accepted_market_result_import();
    market_contract.market_data_provenance_contract_id = "wrong".to_string();
    assert_single_blocker(
        market_contract,
        Blocker::MarketDataProvenanceContractIdMismatch,
    );

    let mut market_hash = accepted_market_result_import();
    market_hash.market_data_provenance_hash.clear();
    assert_single_blocker(market_hash, Blocker::MarketDataProvenanceHashInvalid);

    let mut instrument_contract = accepted_contract_details_result_import();
    instrument_contract.instrument_identity_contract_id = "wrong".to_string();
    assert_single_blocker(
        instrument_contract,
        Blocker::InstrumentIdentityContractIdMismatch,
    );

    let mut instrument_hash = accepted_contract_details_result_import();
    instrument_hash.instrument_identity_hash.clear();
    assert_single_blocker(instrument_hash, Blocker::InstrumentIdentityHashInvalid);

    let mut lifecycle_contract = accepted_open_orders_result_import();
    lifecycle_contract.broker_lifecycle_event_log_contract_id = "wrong".to_string();
    assert_single_blocker(
        lifecycle_contract,
        Blocker::BrokerLifecycleEventLogContractIdMismatch,
    );

    let mut lifecycle_hash = accepted_open_orders_result_import();
    lifecycle_hash.broker_lifecycle_event_log_hash.clear();
    assert_single_blocker(lifecycle_hash, Blocker::BrokerLifecycleEventLogHashInvalid);
}

#[test]
fn result_import_request_rejects_boundary_and_replay_regressions() {
    use StockEtfIbkrReadonlyProbeResultImportBlocker as Blocker;

    let bad = StockEtfIbkrReadonlyProbeResultImportRequestV1 {
        duplicate_import_detected: true,
        stale_result_without_manual_review: true,
        ibkr_contact_performed: true,
        connector_runtime_started: true,
        secret_content_serialized: true,
        result_import_performed: true,
        evidence_writer_started: true,
        scorecard_writer_started: true,
        db_apply_performed: true,
        order_routed: true,
        paper_order_submitted: true,
        bybit_path_reused: true,
        live_or_tiny_live_authorized: true,
        margin_short_options_cfd_requested: true,
        account_write_requested: true,
        market_data_entitlement_purchase_requested: true,
        client_portal_web_api_requested: true,
        python_direct_broker_write_requested: true,
        ..StockEtfIbkrReadonlyProbeResultImportRequestV1::accepted_fixture()
    };
    let verdict = bad.validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![
            Blocker::DuplicateImportDetected,
            Blocker::StaleResultWithoutManualReview,
            Blocker::IbkrContactPerformed,
            Blocker::ConnectorRuntimeStarted,
            Blocker::SecretContentSerialized,
            Blocker::ResultImportPerformed,
            Blocker::EvidenceWriterStarted,
            Blocker::ScorecardWriterStarted,
            Blocker::DbApplyPerformed,
            Blocker::OrderRouted,
            Blocker::PaperOrderSubmitted,
            Blocker::BybitPathReused,
            Blocker::LiveOrTinyLiveAuthorized,
            Blocker::MarginShortOptionsCfdRequested,
            Blocker::AccountWriteRequested,
            Blocker::MarketDataEntitlementPurchaseRequested,
            Blocker::ClientPortalWebApiRequested,
            Blocker::PythonDirectBrokerWriteRequested,
        ]
    );
}

#[test]
fn result_import_request_rejects_each_boundary_flag_independently() {
    use StockEtfIbkrReadonlyProbeResultImportBlocker as Blocker;

    let cases: [(
        fn(&mut StockEtfIbkrReadonlyProbeResultImportRequestV1),
        Blocker,
    ); 16] = [
        (
            |request| request.ibkr_contact_performed = true,
            Blocker::IbkrContactPerformed,
        ),
        (
            |request| request.connector_runtime_started = true,
            Blocker::ConnectorRuntimeStarted,
        ),
        (
            |request| request.secret_content_serialized = true,
            Blocker::SecretContentSerialized,
        ),
        (
            |request| request.result_import_performed = true,
            Blocker::ResultImportPerformed,
        ),
        (
            |request| request.evidence_writer_started = true,
            Blocker::EvidenceWriterStarted,
        ),
        (
            |request| request.scorecard_writer_started = true,
            Blocker::ScorecardWriterStarted,
        ),
        (
            |request| request.db_apply_performed = true,
            Blocker::DbApplyPerformed,
        ),
        (|request| request.order_routed = true, Blocker::OrderRouted),
        (
            |request| request.paper_order_submitted = true,
            Blocker::PaperOrderSubmitted,
        ),
        (
            |request| request.bybit_path_reused = true,
            Blocker::BybitPathReused,
        ),
        (
            |request| request.live_or_tiny_live_authorized = true,
            Blocker::LiveOrTinyLiveAuthorized,
        ),
        (
            |request| request.margin_short_options_cfd_requested = true,
            Blocker::MarginShortOptionsCfdRequested,
        ),
        (
            |request| request.account_write_requested = true,
            Blocker::AccountWriteRequested,
        ),
        (
            |request| request.market_data_entitlement_purchase_requested = true,
            Blocker::MarketDataEntitlementPurchaseRequested,
        ),
        (
            |request| request.client_portal_web_api_requested = true,
            Blocker::ClientPortalWebApiRequested,
        ),
        (
            |request| request.python_direct_broker_write_requested = true,
            Blocker::PythonDirectBrokerWriteRequested,
        ),
    ];

    for (mutate, blocker) in cases {
        let mut request = StockEtfIbkrReadonlyProbeResultImportRequestV1::accepted_fixture();
        mutate(&mut request);
        assert_single_blocker(request, blocker);
    }
}

#[test]
fn result_import_request_template_is_blocked_parseable_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw =
        std::fs::read_to_string(srv_root.join(
            "settings/broker/stock_etf_ibkr_readonly_probe_result_import_request.template.toml",
        ))
        .expect("read result import request template");
    let parsed: StockEtfIbkrReadonlyProbeResultImportRequestV1 =
        toml::from_str(&raw).expect("result import request template parses");

    assert_eq!(parsed.contract_id, "");
    assert_eq!(parsed.source_version, 0);
    assert_eq!(parsed.asset_lane, AssetLane::CryptoPerp);
    assert_eq!(parsed.broker, Broker::Bybit);
    assert_eq!(parsed.environment, BrokerEnvironment::LiveReservedDenied);
    assert!(!parsed.validate().accepted);

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}

fn accepted_account_result_import() -> StockEtfIbkrReadonlyProbeResultImportRequestV1 {
    StockEtfIbkrReadonlyProbeResultImportRequestV1 {
        probe_kind: StockEtfIbkrReadonlyProbeKind::AccountSummarySnapshot,
        api_action: NonBybitApiAction::AccountSummarySnapshotRead,
        operation: BrokerOperation::AccountSnapshotRead,
        account_cash_ledger_contract_id: BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID
            .to_string(),
        account_cash_ledger_hash: "b".repeat(64),
        ..StockEtfIbkrReadonlyProbeResultImportRequestV1::accepted_fixture()
    }
}

fn accepted_market_result_import() -> StockEtfIbkrReadonlyProbeResultImportRequestV1 {
    StockEtfIbkrReadonlyProbeResultImportRequestV1 {
        probe_kind: StockEtfIbkrReadonlyProbeKind::MarketDataSnapshot,
        api_action: NonBybitApiAction::MarketDataSnapshotRead,
        operation: BrokerOperation::MarketDataRead,
        market_data_provenance_contract_id: STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID.to_string(),
        market_data_provenance_hash: "c".repeat(64),
        ..StockEtfIbkrReadonlyProbeResultImportRequestV1::accepted_fixture()
    }
}

fn accepted_contract_details_result_import() -> StockEtfIbkrReadonlyProbeResultImportRequestV1 {
    StockEtfIbkrReadonlyProbeResultImportRequestV1 {
        probe_kind: StockEtfIbkrReadonlyProbeKind::ContractDetails,
        api_action: NonBybitApiAction::ContractDetailsRead,
        operation: BrokerOperation::ContractDetailsRead,
        instrument_identity_contract_id: STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID.to_string(),
        instrument_identity_hash: "d".repeat(64),
        ..StockEtfIbkrReadonlyProbeResultImportRequestV1::accepted_fixture()
    }
}

fn accepted_open_orders_result_import() -> StockEtfIbkrReadonlyProbeResultImportRequestV1 {
    StockEtfIbkrReadonlyProbeResultImportRequestV1 {
        probe_kind: StockEtfIbkrReadonlyProbeKind::OpenPaperOrders,
        api_action: NonBybitApiAction::OpenPaperOrdersRead,
        operation: BrokerOperation::AccountSnapshotRead,
        broker_lifecycle_event_log_contract_id: BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID.to_string(),
        broker_lifecycle_event_log_hash: "e".repeat(64),
        ..StockEtfIbkrReadonlyProbeResultImportRequestV1::accepted_fixture()
    }
}

fn assert_single_blocker(
    request: StockEtfIbkrReadonlyProbeResultImportRequestV1,
    blocker: StockEtfIbkrReadonlyProbeResultImportBlocker,
) {
    let verdict = request.validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![blocker],
        "expected only {:?}, got {:?}",
        blocker,
        verdict.blockers
    );
}
