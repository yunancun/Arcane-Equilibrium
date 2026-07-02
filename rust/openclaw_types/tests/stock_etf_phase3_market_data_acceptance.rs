//! ADR-0048 Stock/ETF Phase 3 market-data evidence contract acceptance tests.
//!
//! These tests validate source evidence checkers only. They do not ingest
//! market data, start an evidence clock, contact IBKR, or write scorecards.

use std::path::PathBuf;

use openclaw_types::{
    AssetLane, Broker, BrokerEnvironment, StockEtfFrozenEvidenceInputsV1, StockEtfPhase3Blocker,
    StockMarketDataProvenanceV1, STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID,
};

#[test]
fn default_market_data_provenance_blocks_scorecard_readiness() {
    let verdict = StockMarketDataProvenanceV1::default().validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![
            StockEtfPhase3Blocker::MarketDataProvenanceContractIdMismatch,
            StockEtfPhase3Blocker::MarketDataProvenanceVersionMismatch,
            StockEtfPhase3Blocker::MarketDataProvenanceWrongAssetLane,
            StockEtfPhase3Blocker::MarketDataProvenanceWrongBroker,
            StockEtfPhase3Blocker::MarketDataProvenanceEnvironmentDenied,
            StockEtfPhase3Blocker::SourceMissing,
            StockEtfPhase3Blocker::EntitlementTierMissing,
            StockEtfPhase3Blocker::RawPayloadHashInvalid,
            StockEtfPhase3Blocker::MarketDataTimestampMissing,
            StockEtfPhase3Blocker::AdjustmentMarkerUnknown,
            StockEtfPhase3Blocker::CorporateActionVersionHashInvalid,
            StockEtfPhase3Blocker::SymbolMissing,
            StockEtfPhase3Blocker::InstrumentIdentityHashInvalid,
            StockEtfPhase3Blocker::CalendarSessionMissing,
            StockEtfPhase3Blocker::SourceArtifactHashInvalid,
            StockEtfPhase3Blocker::BybitLiveExecutionNotProtected,
        ]
    );
}

#[test]
fn source_market_data_provenance_has_required_hashes_and_calendar_session() {
    let provenance = StockMarketDataProvenanceV1::source_fixture();
    let verdict = provenance.validate();

    assert!(verdict.accepted);
    assert!(verdict.blockers.is_empty());
    assert_eq!(
        provenance.contract_id,
        STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID
    );
    assert_eq!(provenance.source_version, 1);
}

#[test]
fn market_data_provenance_requires_exact_contract_id_and_source_version() {
    use StockEtfPhase3Blocker as Blocker;

    let mut provenance = StockMarketDataProvenanceV1::source_fixture();
    provenance.contract_id = "stock_market_data_provenance_v1_fixture".to_string();
    provenance.source_version = 2;

    let blockers = provenance.validate().blockers;

    assert_eq!(
        blockers,
        vec![
            Blocker::MarketDataProvenanceContractIdMismatch,
            Blocker::MarketDataProvenanceVersionMismatch,
        ]
    );
}

#[test]
fn market_data_provenance_rejects_boundary_regressions() {
    use StockEtfPhase3Blocker as Blocker;

    let mut provenance = StockMarketDataProvenanceV1::source_fixture();
    provenance.asset_lane = AssetLane::CryptoPerp;
    provenance.broker = Broker::Bybit;
    provenance.environment = BrokerEnvironment::LiveReservedDenied;
    provenance.source_artifact_hash.clear();
    provenance.bybit_live_execution_unchanged = false;
    provenance.ibkr_contact_performed = true;
    provenance.connector_runtime_started = true;
    provenance.secret_content_serialized = true;
    provenance.live_or_tiny_live_authorized = true;

    let blockers = provenance.validate().blockers;

    assert_eq!(
        blockers,
        vec![
            Blocker::MarketDataProvenanceWrongAssetLane,
            Blocker::MarketDataProvenanceWrongBroker,
            Blocker::MarketDataProvenanceEnvironmentDenied,
            Blocker::SourceArtifactHashInvalid,
            Blocker::BybitLiveExecutionNotProtected,
            Blocker::IbkrContactPerformed,
            Blocker::ConnectorRuntimeStarted,
            Blocker::SecretContentSerialized,
            Blocker::LiveOrTinyLiveAuthorized,
        ]
    );
}

#[test]
fn market_data_provenance_rejects_runtime_secret_and_authority_cross_wire_independently() {
    let mut live_environment = StockMarketDataProvenanceV1::source_fixture();
    live_environment.environment = BrokerEnvironment::LiveReservedDenied;
    assert_single_market_data_blocker(
        live_environment,
        StockEtfPhase3Blocker::MarketDataProvenanceEnvironmentDenied,
    );

    let mut bybit = StockMarketDataProvenanceV1::source_fixture();
    bybit.bybit_live_execution_unchanged = false;
    assert_single_market_data_blocker(bybit, StockEtfPhase3Blocker::BybitLiveExecutionNotProtected);

    let mut ibkr_contact = StockMarketDataProvenanceV1::source_fixture();
    ibkr_contact.ibkr_contact_performed = true;
    assert_single_market_data_blocker(ibkr_contact, StockEtfPhase3Blocker::IbkrContactPerformed);

    let mut connector = StockMarketDataProvenanceV1::source_fixture();
    connector.connector_runtime_started = true;
    assert_single_market_data_blocker(connector, StockEtfPhase3Blocker::ConnectorRuntimeStarted);

    let mut secret = StockMarketDataProvenanceV1::source_fixture();
    secret.secret_content_serialized = true;
    assert_single_market_data_blocker(secret, StockEtfPhase3Blocker::SecretContentSerialized);

    let mut live_authority = StockMarketDataProvenanceV1::source_fixture();
    live_authority.live_or_tiny_live_authorized = true;
    assert_single_market_data_blocker(
        live_authority,
        StockEtfPhase3Blocker::LiveOrTinyLiveAuthorized,
    );
}

#[test]
fn market_data_provenance_template_is_blocked_parseable_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/stock_market_data_provenance.template.toml"),
    )
    .expect("read market data provenance template");
    let parsed: StockMarketDataProvenanceV1 =
        toml::from_str(&raw).expect("market data provenance template parses");

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

#[test]
fn frozen_inputs_require_reference_data_sources_contract_hash() {
    let accepted = StockEtfFrozenEvidenceInputsV1::source_fixture();
    assert!(accepted.validate().accepted);

    let mut missing = accepted;
    missing.reference_data_sources_contract_hash.clear();
    let verdict = missing.validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![StockEtfPhase3Blocker::ReferenceDataSourcesHashInvalid]
    );
}

#[test]
fn frozen_inputs_reject_source_readiness_cross_wire_independently() {
    let mut universe = StockEtfFrozenEvidenceInputsV1::source_fixture();
    universe.universe_hash.clear();
    assert_single_frozen_input_blocker(universe, StockEtfPhase3Blocker::UniverseHashInvalid);

    let mut benchmark = StockEtfFrozenEvidenceInputsV1::source_fixture();
    benchmark.benchmark_hash.clear();
    assert_single_frozen_input_blocker(benchmark, StockEtfPhase3Blocker::BenchmarkHashInvalid);

    let mut cost_model = StockEtfFrozenEvidenceInputsV1::source_fixture();
    cost_model.cost_model_hash.clear();
    assert_single_frozen_input_blocker(cost_model, StockEtfPhase3Blocker::CostModelHashInvalid);

    let mut strategy = StockEtfFrozenEvidenceInputsV1::source_fixture();
    strategy.strategy_hypothesis_hash.clear();
    assert_single_frozen_input_blocker(
        strategy,
        StockEtfPhase3Blocker::StrategyHypothesisHashInvalid,
    );

    let mut reference = StockEtfFrozenEvidenceInputsV1::source_fixture();
    reference.reference_data_sources_contract_hash.clear();
    assert_single_frozen_input_blocker(
        reference,
        StockEtfPhase3Blocker::ReferenceDataSourcesHashInvalid,
    );

    let mut asof = StockEtfFrozenEvidenceInputsV1::source_fixture();
    asof.corporate_action_fx_fee_asof_ms = 0;
    assert_single_frozen_input_blocker(
        asof,
        StockEtfPhase3Blocker::CorporateActionFxFeeAsOfMissing,
    );

    let mut divergence = StockEtfFrozenEvidenceInputsV1::source_fixture();
    divergence.paper_shadow_divergence_threshold_hash.clear();
    assert_single_frozen_input_blocker(
        divergence,
        StockEtfPhase3Blocker::DivergenceThresholdHashInvalid,
    );

    let mut gui = StockEtfFrozenEvidenceInputsV1::source_fixture();
    gui.gui_evidence_view_available = false;
    assert_single_frozen_input_blocker(gui, StockEtfPhase3Blocker::GuiEvidenceViewMissing);

    let mut scorecard = StockEtfFrozenEvidenceInputsV1::source_fixture();
    scorecard.daily_scorecard_regeneration_passed = false;
    assert_single_frozen_input_blocker(
        scorecard,
        StockEtfPhase3Blocker::ScorecardRegenerationMissing,
    );
}

fn assert_single_market_data_blocker(
    provenance: StockMarketDataProvenanceV1,
    blocker: StockEtfPhase3Blocker,
) {
    let verdict = provenance.validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![blocker],
        "expected only {blocker:?}; blockers: {:?}",
        verdict.blockers
    );
}

fn assert_single_frozen_input_blocker(
    frozen_inputs: StockEtfFrozenEvidenceInputsV1,
    blocker: StockEtfPhase3Blocker,
) {
    let verdict = frozen_inputs.validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![blocker],
        "expected only {blocker:?}; blockers: {:?}",
        verdict.blockers
    );
}
