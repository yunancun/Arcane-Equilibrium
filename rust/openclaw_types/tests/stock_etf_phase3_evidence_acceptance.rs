//! ADR-0048 Stock/ETF Phase 3 evidence contract acceptance tests.
//!
//! These tests validate source evidence checkers only. They do not ingest
//! market data, start an evidence clock, contact IBKR, or write scorecards.

use std::path::PathBuf;

use openclaw_types::{
    AssetLane, Broker, BrokerEnvironment, StockEtfDailyDqManifestV1, StockEtfEvidenceClockDayV1,
    StockEtfEvidenceClockStatus, StockEtfFrozenEvidenceInputsV1, StockEtfPhase3Blocker,
    StockMarketDataProvenanceV1, STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID,
    STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID,
};

#[test]
fn default_market_data_provenance_blocks_scorecard_readiness() {
    let verdict = StockMarketDataProvenanceV1::default().validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::MarketDataProvenanceContractIdMismatch));
    assert!(verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::MarketDataProvenanceVersionMismatch));
    assert!(verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::MarketDataProvenanceWrongAssetLane));
    assert!(verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::MarketDataProvenanceWrongBroker));
    assert!(verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::SourceMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::RawPayloadHashInvalid));
    assert!(verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::AdjustmentMarkerUnknown));
    assert!(verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::CalendarSessionMissing));
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
    let mut provenance = StockMarketDataProvenanceV1::source_fixture();
    provenance.contract_id = "stock_market_data_provenance_v1_fixture".to_string();
    provenance.source_version = 2;

    let blockers = provenance.validate().blockers;

    assert!(blockers.contains(&StockEtfPhase3Blocker::MarketDataProvenanceContractIdMismatch));
    assert!(blockers.contains(&StockEtfPhase3Blocker::MarketDataProvenanceVersionMismatch));
}

#[test]
fn market_data_provenance_rejects_boundary_regressions() {
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

    assert!(blockers.contains(&StockEtfPhase3Blocker::MarketDataProvenanceWrongAssetLane));
    assert!(blockers.contains(&StockEtfPhase3Blocker::MarketDataProvenanceWrongBroker));
    assert!(blockers.contains(&StockEtfPhase3Blocker::MarketDataProvenanceEnvironmentDenied));
    assert!(blockers.contains(&StockEtfPhase3Blocker::SourceArtifactHashInvalid));
    assert!(blockers.contains(&StockEtfPhase3Blocker::BybitLiveExecutionNotProtected));
    assert!(blockers.contains(&StockEtfPhase3Blocker::IbkrContactPerformed));
    assert!(blockers.contains(&StockEtfPhase3Blocker::ConnectorRuntimeStarted));
    assert!(blockers.contains(&StockEtfPhase3Blocker::SecretContentSerialized));
    assert!(blockers.contains(&StockEtfPhase3Blocker::LiveOrTinyLiveAuthorized));
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
    assert!(verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::ReferenceDataSourcesHashInvalid));
}

#[test]
fn default_evidence_clock_day_is_not_a_pass_day() {
    let verdict = StockEtfEvidenceClockDayV1::default().validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::EvidenceClockContractIdMismatch));
    assert!(verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::EvidenceClockVersionMismatch));
    assert!(verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::EvidenceClockWrongAssetLane));
    assert!(verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::EvidenceClockWrongBroker));
    assert!(verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::EvidenceClockEnvironmentDenied));
    assert!(verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::EvidenceClockSourceArtifactHashInvalid));
    assert!(verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::EvidenceClockMarketDataProvenanceHashInvalid));
    assert!(verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::EvidenceClockScorecardInputHashInvalid));
    assert!(verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::BybitLiveExecutionNotProtected));
    assert!(verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::IbkrConnectorNotGreenFiveDays));
    assert!(verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::ShadowCollectorNotGreenFiveDays));
    assert!(verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::FrozenInputsRejected));
    assert!(verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::DqManifestShapeRejected));
}

#[test]
fn pass_day_requires_green_dependencies_frozen_inputs_and_dq_quality() {
    let pass = StockEtfEvidenceClockDayV1::pass_day_fixture();
    assert!(pass.validate().accepted);
    assert_eq!(pass.contract_id, STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID);
    assert_eq!(pass.source_version, 1);
    assert_eq!(pass.asset_lane, AssetLane::StockEtfCash);
    assert_eq!(pass.broker, Broker::Ibkr);
    assert_eq!(pass.environment, BrokerEnvironment::Paper);
    assert!(pass.bybit_live_execution_unchanged);
    assert!(!pass.checker_contacted_ibkr);
    assert!(!pass.checker_started_connector_runtime);
    assert!(!pass.checker_started_evidence_clock);
    assert!(!pass.checker_wrote_scorecard);
    assert!(!pass.checker_applied_db);
    assert!(!pass.secret_content_serialized);
    assert!(!pass.live_or_tiny_live_authorized);
    assert!(pass.dq_manifest.passes_day_quality());

    let mut missing_connector = pass.clone();
    missing_connector.ibkr_readonly_paper_connector_green_5d = false;
    let verdict = missing_connector.validate();
    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::IbkrConnectorNotGreenFiveDays));

    let mut weak_dq = pass;
    weak_dq.dq_manifest.calendar_aware_coverage_bps = 9_900;
    let weak_verdict = weak_dq.validate();
    assert!(!weak_verdict.accepted);
    assert!(weak_verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::PassDayQualityRejected));
}

#[test]
fn evidence_clock_day_rejects_contract_drift_and_checker_side_effects() {
    let mut day = StockEtfEvidenceClockDayV1::pass_day_fixture();
    day.contract_id = "stock_etf_evidence_clock_v2".to_string();
    day.source_version = 2;
    day.asset_lane = AssetLane::CryptoPerp;
    day.broker = Broker::Bybit;
    day.environment = BrokerEnvironment::LiveReservedDenied;
    day.source_artifact_hash.clear();
    day.market_data_provenance_contract_hash.clear();
    day.scorecard_input_bundle_hash.clear();
    day.bybit_live_execution_unchanged = false;
    day.checker_contacted_ibkr = true;
    day.checker_started_connector_runtime = true;
    day.checker_started_evidence_clock = true;
    day.checker_wrote_scorecard = true;
    day.checker_applied_db = true;
    day.secret_content_serialized = true;
    day.live_or_tiny_live_authorized = true;

    let blockers = day.validate().blockers;

    assert!(blockers.contains(&StockEtfPhase3Blocker::EvidenceClockContractIdMismatch));
    assert!(blockers.contains(&StockEtfPhase3Blocker::EvidenceClockVersionMismatch));
    assert!(blockers.contains(&StockEtfPhase3Blocker::EvidenceClockWrongAssetLane));
    assert!(blockers.contains(&StockEtfPhase3Blocker::EvidenceClockWrongBroker));
    assert!(blockers.contains(&StockEtfPhase3Blocker::EvidenceClockEnvironmentDenied));
    assert!(blockers.contains(&StockEtfPhase3Blocker::EvidenceClockSourceArtifactHashInvalid));
    assert!(blockers.contains(&StockEtfPhase3Blocker::EvidenceClockMarketDataProvenanceHashInvalid));
    assert!(blockers.contains(&StockEtfPhase3Blocker::EvidenceClockScorecardInputHashInvalid));
    assert!(blockers.contains(&StockEtfPhase3Blocker::BybitLiveExecutionNotProtected));
    assert!(blockers.contains(&StockEtfPhase3Blocker::IbkrContactPerformed));
    assert!(blockers.contains(&StockEtfPhase3Blocker::ConnectorRuntimeStarted));
    assert!(blockers.contains(&StockEtfPhase3Blocker::EvidenceClockRuntimeStarted));
    assert!(blockers.contains(&StockEtfPhase3Blocker::ScorecardWriterStarted));
    assert!(blockers.contains(&StockEtfPhase3Blocker::DbApplyPerformed));
    assert!(blockers.contains(&StockEtfPhase3Blocker::SecretContentSerialized));
    assert!(blockers.contains(&StockEtfPhase3Blocker::LiveOrTinyLiveAuthorized));
}

#[test]
fn quarantined_day_requires_valid_manifest_shape_and_actual_dq_failure() {
    let mut quarantined = StockEtfEvidenceClockDayV1::pass_day_fixture();
    quarantined.status = StockEtfEvidenceClockStatus::QuarantinedDay;
    quarantined.dq_manifest.symbol_completeness_bps = 9_500;
    quarantined.dq_manifest.latency_dq_passed = false;

    assert!(quarantined.dq_manifest.validates_shape().accepted);
    assert!(!quarantined.dq_manifest.passes_day_quality());
    assert!(quarantined.validate().accepted);

    let mut false_quarantine = StockEtfEvidenceClockDayV1::pass_day_fixture();
    false_quarantine.status = StockEtfEvidenceClockStatus::QuarantinedDay;
    let verdict = false_quarantine.validate();
    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::QuarantinedDayWithoutDqFailure));
}

#[test]
fn window_complete_status_is_not_source_authorized_by_checker_fixture() {
    let day = StockEtfEvidenceClockDayV1 {
        status: StockEtfEvidenceClockStatus::WindowComplete,
        ..StockEtfEvidenceClockDayV1::pass_day_fixture()
    };
    let verdict = day.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfPhase3Blocker::WindowCompleteNotSourceAuthorized));
}

#[test]
fn dq_manifest_shape_is_separate_from_pass_day_quality() {
    let mut manifest = StockEtfDailyDqManifestV1::pass_fixture();
    manifest.market_data_provenance_accepted = false;

    assert!(manifest.validates_shape().accepted);
    assert!(!manifest.passes_day_quality());
}

#[test]
fn phase3_evidence_template_is_default_blocked_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/stock_etf_phase3_evidence_contracts.toml"),
    )
    .expect("read phase3 evidence template");
    let parsed: toml::Value = toml::from_str(&raw).expect("phase3 evidence template toml parses");

    assert_eq!(
        parsed["market_data_provenance"]["contract_id"].as_str(),
        Some("")
    );
    assert_eq!(
        parsed["market_data_provenance"]["source_version"].as_integer(),
        Some(0)
    );
    assert_eq!(
        parsed["market_data_provenance"]["bybit_live_execution_unchanged"].as_bool(),
        Some(false)
    );
    assert_eq!(
        parsed["market_data_provenance"]["ibkr_contact_performed"].as_bool(),
        Some(false)
    );
    assert_eq!(
        parsed["market_data_provenance"]["live_or_tiny_live_authorized"].as_bool(),
        Some(false)
    );
    assert_eq!(
        STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID,
        "stock_market_data_provenance_v1"
    );
    assert_eq!(
        parsed["evidence_clock_day"]["status"].as_str(),
        Some("NOT_STARTED")
    );
    assert_eq!(
        parsed["evidence_clock_day"]["contract_id"].as_str(),
        Some("")
    );
    assert_eq!(
        parsed["evidence_clock_day"]["source_version"].as_integer(),
        Some(0)
    );
    assert_eq!(
        parsed["evidence_clock_day"]["asset_lane"].as_str(),
        Some("crypto_perp")
    );
    assert_eq!(
        parsed["evidence_clock_day"]["broker"].as_str(),
        Some("bybit")
    );
    assert_eq!(
        parsed["evidence_clock_day"]["environment"].as_str(),
        Some("live_reserved_denied")
    );
    assert_eq!(
        parsed["evidence_clock_day"]["source_artifact_hash"].as_str(),
        Some("")
    );
    assert_eq!(
        parsed["evidence_clock_day"]["market_data_provenance_contract_hash"].as_str(),
        Some("")
    );
    assert_eq!(
        parsed["evidence_clock_day"]["scorecard_input_bundle_hash"].as_str(),
        Some("")
    );
    assert_eq!(
        parsed["evidence_clock_day"]["bybit_live_execution_unchanged"].as_bool(),
        Some(false)
    );
    assert_eq!(
        parsed["evidence_clock_day"]["checker_started_evidence_clock"].as_bool(),
        Some(false)
    );
    assert_eq!(
        parsed["evidence_clock_day"]["checker_wrote_scorecard"].as_bool(),
        Some(false)
    );
    assert_eq!(
        parsed["evidence_clock_day"]["checker_applied_db"].as_bool(),
        Some(false)
    );
    assert_eq!(
        STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID,
        "stock_etf_evidence_clock_v1"
    );
    assert_eq!(
        parsed["evidence_clock_day"]["ibkr_readonly_paper_connector_green_5d"].as_bool(),
        Some(false)
    );
    assert_eq!(
        parsed["frozen_inputs"]["gui_evidence_view_available"].as_bool(),
        Some(false)
    );
    assert_eq!(
        parsed["frozen_inputs"]["reference_data_sources_contract_hash"].as_str(),
        Some("")
    );
    assert_eq!(
        parsed["dq_manifest"]["calendar_aware_coverage_bps"].as_integer(),
        Some(0)
    );

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}
