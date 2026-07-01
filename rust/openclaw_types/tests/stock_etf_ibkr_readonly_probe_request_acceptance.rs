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
fn readonly_probe_request_rejects_probe_action_operation_cross_wire() {
    let market_with_account_action = StockEtfIbkrReadonlyProbeRequestV1 {
        probe_kind: StockEtfIbkrReadonlyProbeKind::MarketDataSnapshot,
        api_action: NonBybitApiAction::AccountSummarySnapshotRead,
        operation: BrokerOperation::MarketDataRead,
        ..StockEtfIbkrReadonlyProbeRequestV1::accepted_fixture()
    };
    let verdict = market_with_account_action.validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::ProbeActionMismatch
    ));
    assert!(!has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::OperationMismatch
    ));
    assert!(!has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::ApiActionNotReadAllowed
    ));

    let market_with_account_operation = StockEtfIbkrReadonlyProbeRequestV1 {
        probe_kind: StockEtfIbkrReadonlyProbeKind::MarketDataSnapshot,
        api_action: NonBybitApiAction::MarketDataSnapshotRead,
        operation: BrokerOperation::AccountSnapshotRead,
        ..StockEtfIbkrReadonlyProbeRequestV1::accepted_fixture()
    };
    let verdict = market_with_account_operation.validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::OperationMismatch
    ));
    assert!(!has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::ProbeActionMismatch
    ));
    assert!(!has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::ApiActionNotReadAllowed
    ));

    let paper_write_action = StockEtfIbkrReadonlyProbeRequestV1 {
        probe_kind: StockEtfIbkrReadonlyProbeKind::MarketDataSnapshot,
        api_action: NonBybitApiAction::PaperOrderSubmit,
        operation: BrokerOperation::MarketDataRead,
        ..StockEtfIbkrReadonlyProbeRequestV1::accepted_fixture()
    };
    let verdict = paper_write_action.validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::ProbeActionMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::ApiActionNotReadAllowed
    ));
    assert!(!has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::OperationMismatch
    ));
    assert!(!has(
        &verdict,
        StockEtfIbkrReadonlyProbeBlocker::PaperOrderSubmitted
    ));
}

#[test]
fn readonly_probe_request_rejects_each_authority_gap_independently() {
    use StockEtfIbkrReadonlyProbeBlocker as Blocker;

    let cases: [(fn(&mut StockEtfIbkrReadonlyProbeRequestV1), Blocker); 9] = [
        (
            |request| {
                request.contract_id = "stock_etf_ibkr_readonly_probe_request_v1_fixture".to_string()
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
            |request| request.environment = BrokerEnvironment::Paper,
            Blocker::EnvironmentNotReadonly,
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
        let mut request = StockEtfIbkrReadonlyProbeRequestV1::accepted_fixture();
        mutate(&mut request);
        assert_single_blocker(request, blocker);
    }
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
fn readonly_probe_request_rejects_each_lineage_gap_independently() {
    use StockEtfIbkrReadonlyProbeBlocker as Blocker;

    let cases: [(fn(&mut StockEtfIbkrReadonlyProbeRequestV1), Blocker); 22] = [
        (
            |request| request.request_id.clear(),
            Blocker::RequestIdMissing,
        ),
        (|request| request.probe_id.clear(), Blocker::ProbeIdMissing),
        (
            |request| request.external_surface_gate_contract_id = "wrong".to_string(),
            Blocker::ExternalSurfaceGateContractIdMismatch,
        ),
        (
            |request| request.phase2_gate_artifact_hash.clear(),
            Blocker::Phase2GateArtifactHashInvalid,
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
            |request| request.secret_slot_contract_id = "wrong".to_string(),
            Blocker::SecretSlotContractIdMismatch,
        ),
        (
            |request| request.secret_slot_contract_hash.clear(),
            Blocker::SecretSlotContractHashInvalid,
        ),
        (
            |request| request.api_session_topology_contract_id = "wrong".to_string(),
            Blocker::ApiSessionTopologyContractIdMismatch,
        ),
        (
            |request| request.api_session_topology_hash.clear(),
            Blocker::ApiSessionTopologyHashInvalid,
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
            |request| request.redaction_policy_contract_id = "wrong".to_string(),
            Blocker::RedactionPolicyContractIdMismatch,
        ),
        (
            |request| request.redaction_policy_hash.clear(),
            Blocker::RedactionPolicyHashInvalid,
        ),
        (
            |request| request.rate_limit_policy_contract_id = "wrong".to_string(),
            Blocker::RateLimitPolicyContractIdMismatch,
        ),
        (
            |request| request.rate_limit_policy_hash.clear(),
            Blocker::RateLimitPolicyHashInvalid,
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
            |request| request.source_artifact_hash.clear(),
            Blocker::SourceArtifactHashInvalid,
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
            |request| {
                request.api_action = NonBybitApiAction::PaperOrderSubmit;
            },
            Blocker::ProbeActionMismatch,
        ),
    ];

    for (mutate, blocker) in cases {
        let mut request = StockEtfIbkrReadonlyProbeRequestV1::accepted_fixture();
        mutate(&mut request);
        if blocker == Blocker::ProbeActionMismatch {
            let verdict = request.validate();
            assert!(has(&verdict, Blocker::ProbeActionMismatch));
            assert!(has(&verdict, Blocker::ApiActionNotReadAllowed));
            assert_eq!(
                verdict.blockers.len(),
                2,
                "expected only probe/action blockers, got {:?}",
                verdict.blockers
            );
        } else {
            assert_single_blocker(request, blocker);
        }
    }
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
fn readonly_probe_request_rejects_each_boundary_flag_independently() {
    use StockEtfIbkrReadonlyProbeBlocker as Blocker;

    let cases: [(fn(&mut StockEtfIbkrReadonlyProbeRequestV1), Blocker); 14] = [
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
        (|request| request.order_routed = true, Blocker::OrderRouted),
        (
            |request| request.paper_order_submitted = true,
            Blocker::PaperOrderSubmitted,
        ),
        (
            |request| request.db_apply_performed = true,
            Blocker::DbApplyPerformed,
        ),
        (
            |request| request.evidence_clock_started = true,
            Blocker::EvidenceClockStarted,
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
        let mut request = StockEtfIbkrReadonlyProbeRequestV1::accepted_fixture();
        mutate(&mut request);
        assert_single_blocker(request, blocker);
    }
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

fn assert_single_blocker(
    request: StockEtfIbkrReadonlyProbeRequestV1,
    blocker: StockEtfIbkrReadonlyProbeBlocker,
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
