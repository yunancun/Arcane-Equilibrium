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
    STOCK_ETF_SHADOW_SIGNAL_REQUEST_CONTRACT_ID,
};

#[test]
fn default_shadow_signal_request_blocks_all_authority() {
    use StockEtfShadowSignalRequestBlocker as Blocker;

    let verdict = StockEtfShadowSignalRequestV1::default().validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![
            Blocker::ContractIdMismatch,
            Blocker::SourceVersionMismatch,
            Blocker::WrongAssetLane,
            Blocker::WrongBroker,
            Blocker::EnvironmentNotShadow,
            Blocker::RequestMethodMismatch,
            Blocker::OperationMismatch,
            Blocker::AuthorityScopeMismatch,
            Blocker::RequestIdMissing,
            Blocker::EvaluationRunIdMissing,
            Blocker::ShadowSignalIdMissing,
            Blocker::EvidenceClockHashInvalid,
            Blocker::PitUniverseContractHashInvalid,
            Blocker::StrategyHypothesisHashInvalid,
            Blocker::InstrumentIdentityHashInvalid,
            Blocker::MarketDataProvenanceHashInvalid,
            Blocker::CostModelVersionHashInvalid,
            Blocker::AssetLaneEventsContractHashInvalid,
            Blocker::SourceArtifactHashInvalid,
        ]
    );
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
    use StockEtfShadowSignalRequestBlocker as Blocker;

    let wrong_method = StockEtfShadowSignalRequestV1 {
        request_method: StockEtfLaneScopedIpcMethod::ImportPaperFills,
        operation: BrokerOperation::ShadowSignalEmit,
        authority_scope: AuthorityScope::ShadowOnly,
        effect_capable: false,
        ..StockEtfShadowSignalRequestV1::accepted_fixture()
    };
    let verdict = wrong_method.validate();

    assert!(!verdict.accepted);
    assert_eq!(verdict.blockers, vec![Blocker::RequestMethodMismatch]);

    let wrong_operation = StockEtfShadowSignalRequestV1 {
        request_method: StockEtfLaneScopedIpcMethod::EvaluateShadowSignal,
        operation: BrokerOperation::PaperOrderSubmit,
        authority_scope: AuthorityScope::ShadowOnly,
        effect_capable: false,
        ..StockEtfShadowSignalRequestV1::accepted_fixture()
    };
    let verdict = wrong_operation.validate();

    assert!(!verdict.accepted);
    assert_eq!(verdict.blockers, vec![Blocker::OperationMismatch]);

    let paper_write_pollution = StockEtfShadowSignalRequestV1 {
        request_method: StockEtfLaneScopedIpcMethod::SubmitPaperOrder,
        operation: BrokerOperation::PaperOrderSubmit,
        authority_scope: AuthorityScope::PaperRehearsal,
        effect_capable: true,
        ..StockEtfShadowSignalRequestV1::accepted_fixture()
    };
    let verdict = paper_write_pollution.validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![
            Blocker::RequestMethodMismatch,
            Blocker::OperationMismatch,
            Blocker::AuthorityScopeMismatch,
            Blocker::EffectCapabilityPresent,
        ]
    );
}

#[test]
fn shadow_signal_request_rejects_each_authority_gap_independently() {
    use StockEtfShadowSignalRequestBlocker as Blocker;

    let cases: [(fn(&mut StockEtfShadowSignalRequestV1), Blocker); 9] = [
        (
            |request| {
                request.contract_id = "stock_etf_shadow_signal_request_v1_fixture".to_string()
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
            Blocker::EnvironmentNotShadow,
        ),
        (
            |request| request.request_method = StockEtfLaneScopedIpcMethod::ImportPaperFills,
            Blocker::RequestMethodMismatch,
        ),
        (
            |request| request.operation = BrokerOperation::PaperOrderSubmit,
            Blocker::OperationMismatch,
        ),
        (
            |request| request.authority_scope = AuthorityScope::ReadOnly,
            Blocker::AuthorityScopeMismatch,
        ),
        (
            |request| request.effect_capable = true,
            Blocker::EffectCapabilityPresent,
        ),
    ];

    for (mutate, blocker) in cases {
        let mut request = StockEtfShadowSignalRequestV1::accepted_fixture();
        mutate(&mut request);
        assert_single_blocker(request, blocker);
    }
}

#[test]
fn shadow_signal_request_requires_signal_identity_and_lineage_hashes() {
    use StockEtfShadowSignalRequestBlocker as Blocker;

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

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![
            Blocker::RequestIdMissing,
            Blocker::EvaluationRunIdMissing,
            Blocker::ShadowSignalIdMissing,
            Blocker::EvidenceClockHashInvalid,
            Blocker::PitUniverseContractHashInvalid,
            Blocker::StrategyHypothesisHashInvalid,
            Blocker::InstrumentIdentityHashInvalid,
            Blocker::MarketDataProvenanceHashInvalid,
            Blocker::CostModelVersionHashInvalid,
            Blocker::AssetLaneEventsContractHashInvalid,
            Blocker::SourceArtifactHashInvalid,
        ]
    );
}

#[test]
fn shadow_signal_request_rejects_each_lineage_gap_independently() {
    use StockEtfShadowSignalRequestBlocker as Blocker;

    let cases: [(fn(&mut StockEtfShadowSignalRequestV1), Blocker); 11] = [
        (
            |request| request.request_id.clear(),
            Blocker::RequestIdMissing,
        ),
        (
            |request| request.evaluation_run_id.clear(),
            Blocker::EvaluationRunIdMissing,
        ),
        (
            |request| request.shadow_signal_id.clear(),
            Blocker::ShadowSignalIdMissing,
        ),
        (
            |request| request.evidence_clock_hash = "not_hash".to_string(),
            Blocker::EvidenceClockHashInvalid,
        ),
        (
            |request| request.pit_universe_contract_hash.clear(),
            Blocker::PitUniverseContractHashInvalid,
        ),
        (
            |request| request.strategy_hypothesis_hash.clear(),
            Blocker::StrategyHypothesisHashInvalid,
        ),
        (
            |request| request.instrument_identity_hash.clear(),
            Blocker::InstrumentIdentityHashInvalid,
        ),
        (
            |request| request.market_data_provenance_hash.clear(),
            Blocker::MarketDataProvenanceHashInvalid,
        ),
        (
            |request| request.cost_model_version_hash.clear(),
            Blocker::CostModelVersionHashInvalid,
        ),
        (
            |request| request.asset_lane_events_contract_hash.clear(),
            Blocker::AssetLaneEventsContractHashInvalid,
        ),
        (
            |request| request.source_artifact_hash.clear(),
            Blocker::SourceArtifactHashInvalid,
        ),
    ];

    for (mutate, blocker) in cases {
        let mut request = StockEtfShadowSignalRequestV1::accepted_fixture();
        mutate(&mut request);
        assert_single_blocker(request, blocker);
    }
}

#[test]
fn shadow_signal_request_rejects_boundary_regressions() {
    use StockEtfShadowSignalRequestBlocker as Blocker;

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

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![
            Blocker::IbkrContactPerformed,
            Blocker::ConnectorRuntimeStarted,
            Blocker::SecretContentSerialized,
            Blocker::ShadowSignalEmitted,
            Blocker::ShadowFillGenerated,
            Blocker::ScorecardWriterStarted,
            Blocker::DbApplyPerformed,
            Blocker::OrderRouted,
            Blocker::BybitPathReused,
            Blocker::LiveOrTinyLiveAuthorized,
            Blocker::MarginShortOptionsCfdRequested,
            Blocker::PythonDirectBrokerWriteRequested,
        ]
    );
}

#[test]
fn shadow_signal_request_rejects_each_boundary_flag_independently() {
    use StockEtfShadowSignalRequestBlocker as Blocker;

    let cases: [(fn(&mut StockEtfShadowSignalRequestV1), Blocker); 12] = [
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
            |request| request.shadow_signal_emitted = true,
            Blocker::ShadowSignalEmitted,
        ),
        (
            |request| request.shadow_fill_generated = true,
            Blocker::ShadowFillGenerated,
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
            |request| request.python_direct_broker_write_requested = true,
            Blocker::PythonDirectBrokerWriteRequested,
        ),
    ];

    for (mutate, blocker) in cases {
        let mut request = StockEtfShadowSignalRequestV1::accepted_fixture();
        mutate(&mut request);
        assert_single_blocker(request, blocker);
    }
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

fn assert_single_blocker(
    request: StockEtfShadowSignalRequestV1,
    expected: StockEtfShadowSignalRequestBlocker,
) {
    let verdict = request.validate();

    assert!(!verdict.accepted);
    assert_eq!(verdict.blockers, vec![expected]);
}
