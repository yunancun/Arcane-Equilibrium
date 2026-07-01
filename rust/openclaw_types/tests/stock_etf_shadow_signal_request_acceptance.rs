//! ADR-0048 Stock/ETF shadow signal request contract acceptance tests.
//!
//! These tests validate source-only request shape. They must not contact IBKR,
//! inspect secrets, create connectors, emit shadow signals, generate shadow
//! fills, write scorecards, apply DB changes, route orders, or mutate Bybit
//! behavior.

use std::path::PathBuf;

use openclaw_types::{
    AssetLane, AuthorityScope, Broker, BrokerEnvironment, BrokerOperation,
    StockEtfLaneScopedIpcMethod, StockEtfShadowSignalRequestBlocker, StockEtfShadowSignalRequestV1,
    StockEtfShadowSignalRequestVerdict, STOCK_ETF_SHADOW_SIGNAL_REQUEST_CONTRACT_ID,
};

#[test]
fn default_shadow_signal_request_blocks_all_authority() {
    let verdict = StockEtfShadowSignalRequestV1::default().validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::ContractIdMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::SourceVersionMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::WrongAssetLane
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::WrongBroker
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::EnvironmentNotShadow
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::RequestMethodMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::OperationMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::AuthorityScopeMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::RequestIdMissing
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::ShadowSignalIdMissing
    ));
}

#[test]
fn accepted_shadow_signal_request_validates_without_side_effects() {
    let request = StockEtfShadowSignalRequestV1::accepted_fixture();
    let verdict = request.validate();

    assert!(
        verdict.accepted,
        "unexpected blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(
        request.contract_id,
        STOCK_ETF_SHADOW_SIGNAL_REQUEST_CONTRACT_ID
    );
    assert_eq!(request.source_version, 1);
    assert_eq!(request.asset_lane, AssetLane::StockEtfCash);
    assert_eq!(request.broker, Broker::Ibkr);
    assert_eq!(request.environment, BrokerEnvironment::Shadow);
    assert_eq!(
        request.request_method,
        StockEtfLaneScopedIpcMethod::EvaluateShadowSignal
    );
    assert_eq!(request.operation, BrokerOperation::ShadowSignalEmit);
    assert_eq!(request.authority_scope, AuthorityScope::ShadowOnly);
    assert!(!request.effect_capable);
    assert!(!request.ibkr_contact_performed);
    assert!(!request.connector_runtime_started);
    assert!(!request.secret_content_serialized);
    assert!(!request.shadow_signal_emitted);
    assert!(!request.shadow_fill_generated);
    assert!(!request.scorecard_writer_started);
    assert!(!request.db_apply_performed);
    assert!(!request.order_routed);
    assert!(!request.bybit_path_reused);
}

#[test]
fn shadow_signal_request_rejects_method_operation_and_paper_write_cross_wire() {
    let wrong_method = StockEtfShadowSignalRequestV1 {
        request_method: StockEtfLaneScopedIpcMethod::ImportPaperFills,
        operation: BrokerOperation::ShadowSignalEmit,
        authority_scope: AuthorityScope::ShadowOnly,
        effect_capable: false,
        ..StockEtfShadowSignalRequestV1::accepted_fixture()
    };
    let verdict = wrong_method.validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::RequestMethodMismatch
    ));
    assert!(!has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::OperationMismatch
    ));
    assert!(!has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::AuthorityScopeMismatch
    ));
    assert!(!has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::EffectCapabilityPresent
    ));

    let wrong_operation = StockEtfShadowSignalRequestV1 {
        request_method: StockEtfLaneScopedIpcMethod::EvaluateShadowSignal,
        operation: BrokerOperation::PaperOrderSubmit,
        authority_scope: AuthorityScope::ShadowOnly,
        effect_capable: false,
        ..StockEtfShadowSignalRequestV1::accepted_fixture()
    };
    let verdict = wrong_operation.validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::OperationMismatch
    ));
    assert!(!has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::RequestMethodMismatch
    ));
    assert!(!has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::AuthorityScopeMismatch
    ));
    assert!(!has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::EffectCapabilityPresent
    ));

    let paper_write_pollution = StockEtfShadowSignalRequestV1 {
        request_method: StockEtfLaneScopedIpcMethod::SubmitPaperOrder,
        operation: BrokerOperation::PaperOrderSubmit,
        authority_scope: AuthorityScope::PaperRehearsal,
        effect_capable: true,
        ..StockEtfShadowSignalRequestV1::accepted_fixture()
    };
    let verdict = paper_write_pollution.validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::RequestMethodMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::OperationMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::AuthorityScopeMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::EffectCapabilityPresent
    ));
}

#[test]
fn shadow_signal_request_requires_signal_identity_and_lineage_hashes() {
    let bad = StockEtfShadowSignalRequestV1 {
        request_id: String::new(),
        evaluation_run_id: String::new(),
        shadow_signal_id: String::new(),
        evidence_clock_hash: "not_hash".to_string(),
        pit_universe_contract_hash: String::new(),
        strategy_hypothesis_hash: String::new(),
        instrument_identity_hash: String::new(),
        market_data_provenance_hash: String::new(),
        cost_model_version_hash: String::new(),
        asset_lane_events_contract_hash: String::new(),
        source_artifact_hash: String::new(),
        ..StockEtfShadowSignalRequestV1::accepted_fixture()
    };
    let verdict = bad.validate();

    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::RequestIdMissing
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::EvaluationRunIdMissing
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::ShadowSignalIdMissing
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::EvidenceClockHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::PitUniverseContractHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::StrategyHypothesisHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::InstrumentIdentityHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::MarketDataProvenanceHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::CostModelVersionHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::AssetLaneEventsContractHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::SourceArtifactHashInvalid
    ));
}

#[test]
fn shadow_signal_request_rejects_boundary_regressions() {
    let bad = StockEtfShadowSignalRequestV1 {
        ibkr_contact_performed: true,
        connector_runtime_started: true,
        secret_content_serialized: true,
        shadow_signal_emitted: true,
        shadow_fill_generated: true,
        scorecard_writer_started: true,
        db_apply_performed: true,
        order_routed: true,
        bybit_path_reused: true,
        live_or_tiny_live_authorized: true,
        margin_short_options_cfd_requested: true,
        python_direct_broker_write_requested: true,
        ..StockEtfShadowSignalRequestV1::accepted_fixture()
    };
    let verdict = bad.validate();

    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::IbkrContactPerformed
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::ConnectorRuntimeStarted
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::SecretContentSerialized
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::ShadowSignalEmitted
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::ShadowFillGenerated
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::ScorecardWriterStarted
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::DbApplyPerformed
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::OrderRouted
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::BybitPathReused
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::LiveOrTinyLiveAuthorized
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::MarginShortOptionsCfdRequested
    ));
    assert!(has(
        &verdict,
        StockEtfShadowSignalRequestBlocker::PythonDirectBrokerWriteRequested
    ));
}

#[test]
fn blocked_template_is_parseable_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/stock_etf_shadow_signal_request.template.toml"),
    )
    .expect("read shadow signal request template");
    let parsed: StockEtfShadowSignalRequestV1 =
        toml::from_str(&raw).expect("shadow signal request template parses");

    assert_eq!(parsed.contract_id, "");
    assert_eq!(parsed.source_version, 0);
    assert_eq!(parsed.asset_lane, AssetLane::CryptoPerp);
    assert_eq!(parsed.broker, Broker::Bybit);
    assert!(!parsed.validate().accepted);
    assert!(!parsed.ibkr_contact_performed);
    assert!(!parsed.connector_runtime_started);
    assert!(!parsed.secret_content_serialized);
    assert!(!parsed.shadow_signal_emitted);
    assert!(!parsed.shadow_fill_generated);
    assert!(!parsed.scorecard_writer_started);
    assert!(!parsed.db_apply_performed);
    assert!(!parsed.order_routed);

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}

fn has(
    verdict: &StockEtfShadowSignalRequestVerdict,
    blocker: StockEtfShadowSignalRequestBlocker,
) -> bool {
    verdict.blockers.contains(&blocker)
}
