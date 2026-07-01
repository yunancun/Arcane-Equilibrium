//! ADR-0048 Stock/ETF paper fill import request contract acceptance tests.
//!
//! These tests validate source-only request shape. They must not contact IBKR,
//! inspect secrets, create connectors, import fills, apply DB changes, route
//! orders, or mutate Bybit behavior.

use std::path::PathBuf;

use openclaw_types::{
    AssetLane, AuthorityScope, Broker, BrokerEnvironment, BrokerOperation,
    IbkrPaperOrderLifecycleState, IbkrPaperStaleStatePolicy, StockEtfLaneScopedIpcMethod,
    StockEtfPaperFillImportBlocker, StockEtfPaperFillImportRequestV1,
    StockEtfPaperFillImportVerdict, BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID,
    IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID, IBKR_REDACTION_POLICY_CONTRACT_ID,
    STOCK_ETF_PAPER_FILL_IMPORT_REQUEST_CONTRACT_ID,
};

#[test]
fn default_fill_import_request_blocks_all_authority() {
    let verdict = StockEtfPaperFillImportRequestV1::default().validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::ContractIdMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::SourceVersionMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::WrongAssetLane
    ));
    assert!(has(&verdict, StockEtfPaperFillImportBlocker::WrongBroker));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::EnvironmentNotPaper
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::RequestMethodMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::OperationMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::ObservedOrderStateMissing
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::StaleStatePolicyMissing
    ));
}

#[test]
fn accepted_fill_import_request_validates_without_side_effects() {
    let request = StockEtfPaperFillImportRequestV1::accepted_fixture();
    let verdict = request.validate();

    assert!(
        verdict.accepted,
        "unexpected blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(
        request.contract_id,
        STOCK_ETF_PAPER_FILL_IMPORT_REQUEST_CONTRACT_ID
    );
    assert_eq!(request.source_version, 1);
    assert_eq!(request.asset_lane, AssetLane::StockEtfCash);
    assert_eq!(request.broker, Broker::Ibkr);
    assert_eq!(request.environment, BrokerEnvironment::Paper);
    assert_eq!(
        request.request_method,
        StockEtfLaneScopedIpcMethod::ImportPaperFills
    );
    assert_eq!(request.operation, BrokerOperation::PaperOrderFillImport);
    assert_eq!(request.authority_scope, AuthorityScope::ReadOnly);
    assert!(!request.effect_capable);
    assert_eq!(
        request.lifecycle_contract_id,
        IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID
    );
    assert_eq!(
        request.event_log_contract_id,
        BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID
    );
    assert_eq!(
        request.redaction_policy_contract_id,
        IBKR_REDACTION_POLICY_CONTRACT_ID
    );
    assert!(!request.ibkr_contact_performed);
    assert!(!request.connector_runtime_started);
    assert!(!request.secret_content_serialized);
    assert!(!request.fill_import_performed);
    assert!(!request.db_apply_performed);
    assert!(!request.order_routed);
    assert!(!request.bybit_path_reused);
}

#[test]
fn fill_import_request_rejects_method_operation_and_scope_cross_wire() {
    let wrong_method = StockEtfPaperFillImportRequestV1 {
        request_method: StockEtfLaneScopedIpcMethod::EvaluateShadowSignal,
        operation: BrokerOperation::PaperOrderFillImport,
        authority_scope: AuthorityScope::ReadOnly,
        effect_capable: false,
        ..StockEtfPaperFillImportRequestV1::accepted_fixture()
    };
    let verdict = wrong_method.validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::RequestMethodMismatch
    ));
    assert!(!has(
        &verdict,
        StockEtfPaperFillImportBlocker::OperationMismatch
    ));
    assert!(!has(
        &verdict,
        StockEtfPaperFillImportBlocker::AuthorityScopeMismatch
    ));
    assert!(!has(
        &verdict,
        StockEtfPaperFillImportBlocker::EffectCapabilityPresent
    ));

    let wrong_operation = StockEtfPaperFillImportRequestV1 {
        request_method: StockEtfLaneScopedIpcMethod::ImportPaperFills,
        operation: BrokerOperation::PaperOrderSubmit,
        authority_scope: AuthorityScope::ReadOnly,
        effect_capable: false,
        ..StockEtfPaperFillImportRequestV1::accepted_fixture()
    };
    let verdict = wrong_operation.validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::OperationMismatch
    ));
    assert!(!has(
        &verdict,
        StockEtfPaperFillImportBlocker::RequestMethodMismatch
    ));
    assert!(!has(
        &verdict,
        StockEtfPaperFillImportBlocker::AuthorityScopeMismatch
    ));
    assert!(!has(
        &verdict,
        StockEtfPaperFillImportBlocker::EffectCapabilityPresent
    ));

    let paper_write_pollution = StockEtfPaperFillImportRequestV1 {
        request_method: StockEtfLaneScopedIpcMethod::SubmitPaperOrder,
        operation: BrokerOperation::PaperOrderSubmit,
        authority_scope: AuthorityScope::PaperRehearsal,
        effect_capable: true,
        ..StockEtfPaperFillImportRequestV1::accepted_fixture()
    };
    let verdict = paper_write_pollution.validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::RequestMethodMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::OperationMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::AuthorityScopeMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::EffectCapabilityPresent
    ));

    let shadow_signal_pollution = StockEtfPaperFillImportRequestV1 {
        request_method: StockEtfLaneScopedIpcMethod::EvaluateShadowSignal,
        operation: BrokerOperation::ShadowSignalEmit,
        authority_scope: AuthorityScope::ShadowOnly,
        effect_capable: false,
        ..StockEtfPaperFillImportRequestV1::accepted_fixture()
    };
    let verdict = shadow_signal_pollution.validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::RequestMethodMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::OperationMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::AuthorityScopeMismatch
    ));
    assert!(!has(
        &verdict,
        StockEtfPaperFillImportBlocker::EffectCapabilityPresent
    ));
}

#[test]
fn fill_import_request_requires_lineage_ids_hashes_and_stale_policy() {
    let bad = StockEtfPaperFillImportRequestV1 {
        request_id: String::new(),
        session_attestation_hash: "not_hash".to_string(),
        lifecycle_contract_id: "wrong".to_string(),
        lifecycle_contract_hash: String::new(),
        event_log_contract_id: "wrong".to_string(),
        event_log_contract_hash: String::new(),
        redaction_policy_contract_id: "wrong".to_string(),
        redaction_policy_hash: String::new(),
        source_artifact_hash: String::new(),
        reconciliation_run_id: String::new(),
        broker_order_id: String::new(),
        execution_id: String::new(),
        commission_report_id: String::new(),
        import_idempotency_key: String::new(),
        observed_order_state: None,
        stale_state_policy: None,
        raw_artifact_hash: String::new(),
        redacted_summary_hash: String::new(),
        ..StockEtfPaperFillImportRequestV1::accepted_fixture()
    };
    let verdict = bad.validate();

    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::RequestIdMissing
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::SessionAttestationHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::LifecycleContractIdMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::EventLogContractIdMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::RedactionPolicyContractIdMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::ReconciliationRunIdMissing
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::BrokerOrderIdMissing
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::ExecutionIdMissing
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::CommissionReportIdMissing
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::ImportIdempotencyKeyMissing
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::ObservedOrderStateMissing
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::StaleStatePolicyMissing
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::RawArtifactHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::RedactedSummaryHashInvalid
    ));
}

#[test]
fn fill_import_request_rejects_boundary_and_replay_regressions() {
    let bad = StockEtfPaperFillImportRequestV1 {
        duplicate_import_detected: true,
        observed_order_state: Some(IbkrPaperOrderLifecycleState::StateUnknown),
        stale_state_policy: None,
        stale_unknown_state_without_policy: true,
        ibkr_contact_performed: true,
        connector_runtime_started: true,
        secret_content_serialized: true,
        fill_import_performed: true,
        db_apply_performed: true,
        order_routed: true,
        bybit_path_reused: true,
        live_or_tiny_live_authorized: true,
        margin_short_options_cfd_requested: true,
        python_direct_broker_write_requested: true,
        ..StockEtfPaperFillImportRequestV1::accepted_fixture()
    };
    let verdict = bad.validate();

    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::DuplicateImportDetected
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::StaleUnknownStateWithoutPolicy
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::IbkrContactPerformed
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::ConnectorRuntimeStarted
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::SecretContentSerialized
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::FillImportPerformed
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::DbApplyPerformed
    ));
    assert!(has(&verdict, StockEtfPaperFillImportBlocker::OrderRouted));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::BybitPathReused
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::LiveOrTinyLiveAuthorized
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::MarginShortOptionsCfdRequested
    ));
    assert!(has(
        &verdict,
        StockEtfPaperFillImportBlocker::PythonDirectBrokerWriteRequested
    ));
}

#[test]
fn state_unknown_is_allowed_only_with_explicit_stale_policy() {
    let request = StockEtfPaperFillImportRequestV1 {
        observed_order_state: Some(IbkrPaperOrderLifecycleState::StateUnknown),
        stale_state_policy: Some(IbkrPaperStaleStatePolicy::ManualReviewOnUnknown),
        ..StockEtfPaperFillImportRequestV1::accepted_fixture()
    };

    assert!(request.validate().accepted);
}

#[test]
fn blocked_template_is_parseable_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/stock_etf_paper_fill_import_request.template.toml"),
    )
    .expect("read paper fill import request template");
    let parsed: StockEtfPaperFillImportRequestV1 =
        toml::from_str(&raw).expect("paper fill import request template parses");

    assert_eq!(parsed.contract_id, "");
    assert_eq!(parsed.source_version, 0);
    assert_eq!(parsed.asset_lane, AssetLane::CryptoPerp);
    assert_eq!(parsed.broker, Broker::Bybit);
    assert!(!parsed.validate().accepted);
    assert!(!parsed.ibkr_contact_performed);
    assert!(!parsed.connector_runtime_started);
    assert!(!parsed.secret_content_serialized);
    assert!(!parsed.fill_import_performed);
    assert!(!parsed.db_apply_performed);
    assert!(!parsed.order_routed);

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}

fn has(verdict: &StockEtfPaperFillImportVerdict, blocker: StockEtfPaperFillImportBlocker) -> bool {
    verdict.blockers.contains(&blocker)
}
