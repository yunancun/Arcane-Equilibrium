//! ADR-0048 Stock/ETF IBKR read-only probe result import request tests.
//!
//! These tests validate source-only import-request shape. They must not contact
//! IBKR, inspect secrets, create connectors, import evidence, apply DB changes,
//! route orders, or mutate Bybit behavior.

use std::path::PathBuf;

use openclaw_types::{
    AssetLane, AuthorityScope, Broker, BrokerEnvironment, BrokerOperation, NonBybitApiAction,
    StockEtfIbkrReadonlyProbeKind, StockEtfIbkrReadonlyProbeResultImportBlocker,
    StockEtfIbkrReadonlyProbeResultImportRequestV1, StockEtfIbkrReadonlyProbeResultImportVerdict,
    BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID, BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID,
    IBKR_AUDIT_EVENT_POLICY_CONTRACT_ID, IBKR_REDACTION_POLICY_CONTRACT_ID,
    IBKR_SESSION_ATTESTATION_CONTRACT_ID, NON_BYBIT_API_ALLOWLIST_CONTRACT_ID,
    STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID,
    STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID,
    STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID, STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID,
};

#[test]
fn default_result_import_request_blocks_all_authority() {
    let verdict = StockEtfIbkrReadonlyProbeResultImportRequestV1::default().validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::ContractIdMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::SourceVersionMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::WrongAssetLane
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::WrongBroker
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::EnvironmentDenied
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::ProbeActionMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::OperationMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::ResultImportRequestIdMissing
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::HealthSnapshotHashInvalid
    ));
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

    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::ResultImportRequestIdMissing
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::RequestIdMissing
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::ProbeIdMissing
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::ReadonlyProbeRequestContractIdMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::ReadonlyProbeRequestHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::SessionAttestationContractIdMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::ApiAllowlistContractIdMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::RedactionPolicyContractIdMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::AuditEventPolicyContractIdMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::ResultPayloadHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::RawArtifactHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::RedactedSummaryHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::SourceArtifactHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::ResultAsOfAfterImportRequested
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::IdempotencyKeyMissing
    ));
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
    let blockers = bad_account.validate().blockers;
    assert!(blockers.contains(
        &StockEtfIbkrReadonlyProbeResultImportBlocker::AccountCashLedgerContractIdMismatch
    ));
    assert!(blockers
        .contains(&StockEtfIbkrReadonlyProbeResultImportBlocker::AccountCashLedgerHashInvalid));

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
fn result_import_request_rejects_boundary_and_replay_regressions() {
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

    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::DuplicateImportDetected
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::StaleResultWithoutManualReview
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::IbkrContactPerformed
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::ConnectorRuntimeStarted
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::SecretContentSerialized
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::ResultImportPerformed
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::EvidenceWriterStarted
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::ScorecardWriterStarted
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::DbApplyPerformed
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::OrderRouted
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::PaperOrderSubmitted
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::BybitPathReused
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::LiveOrTinyLiveAuthorized
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::MarginShortOptionsCfdRequested
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::AccountWriteRequested
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::MarketDataEntitlementPurchaseRequested
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::ClientPortalWebApiRequested
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeResultImportBlocker::PythonDirectBrokerWriteRequested
    ));
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

fn has(
    verdict: &StockEtfIbkrReadonlyProbeResultImportVerdict,
    blocker: StockEtfIbkrReadonlyProbeResultImportBlocker,
) -> bool {
    verdict.blockers.contains(&blocker)
}
