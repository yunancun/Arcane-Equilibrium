//! ADR-0048 Stock/ETF IBKR read-only probe request contract acceptance tests.
//!
//! These tests validate a source-only pre-contact request envelope. They must
//! not contact IBKR, import an SDK, inspect secrets, create connectors, route
//! orders, write evidence, apply DB changes, or mutate Bybit behavior.

use openclaw_types::{
    AssetLane, AuthorityScope, Broker, BrokerEnvironment, BrokerOperation, NonBybitApiAction,
    StockEtfIbkrReadonlyProbeBlocker, StockEtfIbkrReadonlyProbeKind,
    StockEtfIbkrReadonlyProbeRequestV1, StockEtfIbkrReadonlyProbeVerdict,
    IBKR_API_SESSION_TOPOLOGY_CONTRACT_ID, IBKR_AUDIT_EVENT_POLICY_CONTRACT_ID,
    IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID, IBKR_RATE_LIMIT_POLICY_CONTRACT_ID,
    IBKR_REDACTION_POLICY_CONTRACT_ID, IBKR_SECRET_SLOT_CONTRACT_ID,
    IBKR_SESSION_ATTESTATION_CONTRACT_ID, NON_BYBIT_API_ALLOWLIST_CONTRACT_ID,
    STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID,
};

#[test]
fn default_readonly_probe_request_blocks_all_authority() {
    let verdict = StockEtfIbkrReadonlyProbeRequestV1::default().validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::ContractIdMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::SourceVersionMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::WrongAssetLane
    ));
    assert!(has(&verdict, StockEtfIbkrReadonlyProbeBlocker::WrongBroker));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::EnvironmentNotReadonly
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::ProbeActionMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::OperationMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::AuthorityScopeMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::ApiActionNotReadAllowed
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::RequestIdMissing
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::SessionAttestationHashInvalid
    ));
}

#[test]
fn accepted_readonly_probe_request_validates_without_side_effects() {
    let request = StockEtfIbkrReadonlyProbeRequestV1::accepted_fixture();
    let verdict = request.validate();

    assert!(
        verdict.accepted,
        "unexpected blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(
        request.contract_id,
        STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID
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
    assert!(!request.effect_capable);
    assert_eq!(
        request.external_surface_gate_contract_id,
        IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID
    );
    assert_eq!(
        request.api_allowlist_contract_id,
        NON_BYBIT_API_ALLOWLIST_CONTRACT_ID
    );
    assert_eq!(
        request.secret_slot_contract_id,
        IBKR_SECRET_SLOT_CONTRACT_ID
    );
    assert_eq!(
        request.api_session_topology_contract_id,
        IBKR_API_SESSION_TOPOLOGY_CONTRACT_ID
    );
    assert_eq!(
        request.session_attestation_contract_id,
        IBKR_SESSION_ATTESTATION_CONTRACT_ID
    );
    assert_eq!(
        request.redaction_policy_contract_id,
        IBKR_REDACTION_POLICY_CONTRACT_ID
    );
    assert_eq!(
        request.rate_limit_policy_contract_id,
        IBKR_RATE_LIMIT_POLICY_CONTRACT_ID
    );
    assert_eq!(
        request.audit_event_policy_contract_id,
        IBKR_AUDIT_EVENT_POLICY_CONTRACT_ID
    );
    assert!(!request.ibkr_contact_performed);
    assert!(!request.connector_runtime_started);
    assert!(!request.secret_content_serialized);
    assert!(!request.order_routed);
    assert!(!request.paper_order_submitted);
    assert!(!request.db_apply_performed);
    assert!(!request.evidence_clock_started);
    assert!(!request.bybit_path_reused);
}

#[test]
fn readonly_probe_requires_allowlisted_read_action_and_operation_mapping() {
    let bad = StockEtfIbkrReadonlyProbeRequestV1 {
        probe_kind: StockEtfIbkrReadonlyProbeKind::ConnectionHealth,
        api_action: NonBybitApiAction::PaperOrderSubmit,
        operation: BrokerOperation::MarketDataRead,
        authority_scope: AuthorityScope::PaperRehearsal,
        effect_capable: true,
        ..StockEtfIbkrReadonlyProbeRequestV1::accepted_fixture()
    };
    let verdict = bad.validate();

    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::ProbeActionMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::OperationMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::AuthorityScopeMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::EffectCapabilityPresent
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::ApiActionNotReadAllowed
    ));
}

#[test]
fn readonly_probe_requires_full_precontact_lineage_hashes() {
    let bad = StockEtfIbkrReadonlyProbeRequestV1 {
        request_id: String::new(),
        probe_id: String::new(),
        external_surface_gate_contract_id: "wrong".to_string(),
        phase2_gate_artifact_hash: String::new(),
        api_allowlist_contract_id: "wrong".to_string(),
        api_allowlist_hash: String::new(),
        secret_slot_contract_id: "wrong".to_string(),
        secret_slot_contract_hash: String::new(),
        api_session_topology_contract_id: "wrong".to_string(),
        api_session_topology_hash: String::new(),
        session_attestation_contract_id: "wrong".to_string(),
        session_attestation_hash: String::new(),
        redaction_policy_contract_id: "wrong".to_string(),
        redaction_policy_hash: String::new(),
        rate_limit_policy_contract_id: "wrong".to_string(),
        rate_limit_policy_hash: String::new(),
        audit_event_policy_contract_id: "wrong".to_string(),
        audit_event_policy_hash: String::new(),
        source_artifact_hash: String::new(),
        raw_artifact_hash: String::new(),
        redacted_summary_hash: String::new(),
        ..StockEtfIbkrReadonlyProbeRequestV1::accepted_fixture()
    };
    let verdict = bad.validate();

    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::RequestIdMissing
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::ProbeIdMissing
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::ExternalSurfaceGateContractIdMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::Phase2GateArtifactHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::ApiAllowlistContractIdMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::SecretSlotContractIdMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::ApiSessionTopologyContractIdMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::SessionAttestationContractIdMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::RedactionPolicyContractIdMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::RateLimitPolicyContractIdMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::AuditEventPolicyContractIdMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::SourceArtifactHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::RawArtifactHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::RedactedSummaryHashInvalid
    ));
}

#[test]
fn readonly_probe_rejects_contact_runtime_write_and_bybit_regressions() {
    let bad = StockEtfIbkrReadonlyProbeRequestV1 {
        ibkr_contact_performed: true,
        connector_runtime_started: true,
        secret_content_serialized: true,
        order_routed: true,
        paper_order_submitted: true,
        db_apply_performed: true,
        evidence_clock_started: true,
        bybit_path_reused: true,
        live_or_tiny_live_authorized: true,
        margin_short_options_cfd_requested: true,
        account_write_requested: true,
        market_data_entitlement_purchase_requested: true,
        client_portal_web_api_requested: true,
        python_direct_broker_write_requested: true,
        ..StockEtfIbkrReadonlyProbeRequestV1::accepted_fixture()
    };
    let verdict = bad.validate();

    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::IbkrContactPerformed
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::ConnectorRuntimeStarted
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::SecretContentSerialized
    ));
    assert!(has(&verdict, StockEtfIbkrReadonlyProbeBlocker::OrderRouted));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::PaperOrderSubmitted
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::DbApplyPerformed
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::EvidenceClockStarted
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::BybitPathReused
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::LiveOrTinyLiveAuthorized
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::MarginShortOptionsCfdRequested
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::AccountWriteRequested
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::MarketDataEntitlementPurchaseRequested
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::ClientPortalWebApiRequested
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::PythonDirectBrokerWriteRequested
    ));
}

#[test]
fn readonly_probe_kind_maps_to_expected_read_operations() {
    let account = StockEtfIbkrReadonlyProbeRequestV1 {
        probe_kind: StockEtfIbkrReadonlyProbeKind::AccountSummarySnapshot,
        api_action: NonBybitApiAction::AccountSummarySnapshotRead,
        operation: BrokerOperation::AccountSnapshotRead,
        ..StockEtfIbkrReadonlyProbeRequestV1::accepted_fixture()
    };
    let market = StockEtfIbkrReadonlyProbeRequestV1 {
        probe_kind: StockEtfIbkrReadonlyProbeKind::MarketDataSnapshot,
        api_action: NonBybitApiAction::MarketDataSnapshotRead,
        operation: BrokerOperation::MarketDataRead,
        ..StockEtfIbkrReadonlyProbeRequestV1::accepted_fixture()
    };
    let contract_details = StockEtfIbkrReadonlyProbeRequestV1 {
        probe_kind: StockEtfIbkrReadonlyProbeKind::ContractDetails,
        api_action: NonBybitApiAction::ContractDetailsRead,
        operation: BrokerOperation::ContractDetailsRead,
        ..StockEtfIbkrReadonlyProbeRequestV1::accepted_fixture()
    };

    assert!(account.validate().accepted);
    assert!(market.validate().accepted);
    assert!(contract_details.validate().accepted);
}

fn has(
    verdict: &StockEtfIbkrReadonlyProbeVerdict,
    blocker: StockEtfIbkrReadonlyProbeBlocker,
) -> bool {
    verdict.blockers.contains(&blocker)
}
