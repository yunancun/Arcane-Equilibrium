//! ADR-0048 Stock/ETF Phase 3 evidence contract acceptance tests.
//!
//! These tests validate source evidence checkers only. They do not ingest
//! market data, start an evidence clock, contact IBKR, or write scorecards.

use std::path::PathBuf;

use openclaw_types::{
    AssetLane, Broker, BrokerEnvironment, StockEtfCollectorRunV1, StockEtfEvidenceClockDayV1,
    StockEtfEvidenceClockStatus, StockEtfPhase3Blocker, STOCK_ETF_COLLECTOR_MIN_GREEN_TRADING_DAYS,
    STOCK_ETF_COLLECTOR_RUN_CONTRACT_ID, STOCK_ETF_DQ_MANIFEST_CONTRACT_ID,
    STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID, STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID,
};

#[test]
fn default_collector_run_blocks_phase3_evidence_clock() {
    let verdict = StockEtfCollectorRunV1::default().validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![
            StockEtfPhase3Blocker::CollectorRunContractIdMismatch,
            StockEtfPhase3Blocker::CollectorRunVersionMismatch,
            StockEtfPhase3Blocker::CollectorRunWrongAssetLane,
            StockEtfPhase3Blocker::CollectorRunWrongBroker,
            StockEtfPhase3Blocker::CollectorRunEnvironmentDenied,
            StockEtfPhase3Blocker::CollectorRunIdMissing,
            StockEtfPhase3Blocker::CollectorTradingDayMissing,
            StockEtfPhase3Blocker::CollectorPitUniverseContractMismatch,
            StockEtfPhase3Blocker::CollectorPitUniverseHashInvalid,
            StockEtfPhase3Blocker::CollectorMarketDataProvenanceContractMismatch,
            StockEtfPhase3Blocker::CollectorMarketDataProvenanceHashInvalid,
            StockEtfPhase3Blocker::CollectorReferenceDataSourcesContractMismatch,
            StockEtfPhase3Blocker::CollectorReferenceDataSourcesHashInvalid,
            StockEtfPhase3Blocker::CollectorStorageCapacityContractMismatch,
            StockEtfPhase3Blocker::CollectorStorageCapacityHashInvalid,
            StockEtfPhase3Blocker::CollectorExpectedSessionsTooSmall,
            StockEtfPhase3Blocker::CollectorGapReportHashInvalid,
            StockEtfPhase3Blocker::CollectorDqManifestHashInvalid,
            StockEtfPhase3Blocker::CollectorReplayManifestHashInvalid,
            StockEtfPhase3Blocker::CollectorSourceArtifactHashInvalid,
            StockEtfPhase3Blocker::BybitLiveExecutionNotProtected,
        ]
    );
}

#[test]
fn source_collector_run_requires_five_green_sessions_and_lineage_hashes() {
    use StockEtfPhase3Blocker as Blocker;

    let collector = StockEtfCollectorRunV1::source_fixture();
    let verdict = collector.validate();

    assert!(
        verdict.accepted,
        "collector blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(collector.contract_id, STOCK_ETF_COLLECTOR_RUN_CONTRACT_ID);
    assert_eq!(
        collector.expected_trading_sessions,
        STOCK_ETF_COLLECTOR_MIN_GREEN_TRADING_DAYS
    );
    assert_eq!(
        collector.completed_trading_sessions,
        STOCK_ETF_COLLECTOR_MIN_GREEN_TRADING_DAYS
    );
    assert!(!collector.ibkr_contact_performed);
    assert!(!collector.connector_runtime_started);
    assert!(!collector.market_data_ingestion_started);
    assert!(!collector.evidence_writer_started);
    assert!(!collector.scorecard_writer_started);
    assert!(!collector.db_apply_performed);

    let mut missing_lineage = collector.clone();
    missing_lineage.pit_universe_contract_hash.clear();
    missing_lineage.market_data_provenance_contract_hash.clear();
    missing_lineage.reference_data_sources_contract_hash.clear();
    missing_lineage.storage_capacity_contract_hash.clear();
    missing_lineage.gap_report_hash.clear();
    missing_lineage.dq_manifest_hash.clear();
    missing_lineage.replay_manifest_hash.clear();
    let blockers = missing_lineage.validate().blockers;

    assert_eq!(
        blockers,
        vec![
            Blocker::CollectorPitUniverseHashInvalid,
            Blocker::CollectorMarketDataProvenanceHashInvalid,
            Blocker::CollectorReferenceDataSourcesHashInvalid,
            Blocker::CollectorStorageCapacityHashInvalid,
            Blocker::CollectorGapReportHashInvalid,
            Blocker::CollectorDqManifestHashInvalid,
            Blocker::CollectorReplayManifestHashInvalid,
        ]
    );
}

#[test]
fn collector_run_rejects_side_effecting_runtime_claims() {
    use StockEtfPhase3Blocker as Blocker;

    let mut collector = StockEtfCollectorRunV1::source_fixture();
    collector.expected_trading_sessions = STOCK_ETF_COLLECTOR_MIN_GREEN_TRADING_DAYS;
    collector.completed_trading_sessions = STOCK_ETF_COLLECTOR_MIN_GREEN_TRADING_DAYS - 1;
    collector.bybit_live_execution_unchanged = false;
    collector.ibkr_contact_performed = true;
    collector.connector_runtime_started = true;
    collector.market_data_ingestion_started = true;
    collector.evidence_writer_started = true;
    collector.scorecard_writer_started = true;
    collector.db_apply_performed = true;
    collector.secret_content_serialized = true;
    collector.live_or_tiny_live_authorized = true;
    let blockers = collector.validate().blockers;

    assert_eq!(
        blockers,
        vec![
            Blocker::CollectorCompletedSessionsMissing,
            Blocker::BybitLiveExecutionNotProtected,
            Blocker::IbkrContactPerformed,
            Blocker::ConnectorRuntimeStarted,
            Blocker::CollectorMarketDataIngestionStarted,
            Blocker::CollectorEvidenceWriterStarted,
            Blocker::ScorecardWriterStarted,
            Blocker::DbApplyPerformed,
            Blocker::SecretContentSerialized,
            Blocker::LiveOrTinyLiveAuthorized,
        ]
    );
}

#[test]
fn collector_run_rejects_runtime_writer_secret_and_authority_cross_wire_independently() {
    let mut incomplete_sessions = StockEtfCollectorRunV1::source_fixture();
    incomplete_sessions.completed_trading_sessions = STOCK_ETF_COLLECTOR_MIN_GREEN_TRADING_DAYS - 1;
    assert_single_phase3_blocker(
        incomplete_sessions,
        StockEtfPhase3Blocker::CollectorCompletedSessionsMissing,
    );

    let mut bybit = StockEtfCollectorRunV1::source_fixture();
    bybit.bybit_live_execution_unchanged = false;
    assert_single_phase3_blocker(bybit, StockEtfPhase3Blocker::BybitLiveExecutionNotProtected);

    let mut ibkr_contact = StockEtfCollectorRunV1::source_fixture();
    ibkr_contact.ibkr_contact_performed = true;
    assert_single_phase3_blocker(ibkr_contact, StockEtfPhase3Blocker::IbkrContactPerformed);

    let mut connector = StockEtfCollectorRunV1::source_fixture();
    connector.connector_runtime_started = true;
    assert_single_phase3_blocker(connector, StockEtfPhase3Blocker::ConnectorRuntimeStarted);

    let mut ingestion = StockEtfCollectorRunV1::source_fixture();
    ingestion.market_data_ingestion_started = true;
    assert_single_phase3_blocker(
        ingestion,
        StockEtfPhase3Blocker::CollectorMarketDataIngestionStarted,
    );

    let mut evidence_writer = StockEtfCollectorRunV1::source_fixture();
    evidence_writer.evidence_writer_started = true;
    assert_single_phase3_blocker(
        evidence_writer,
        StockEtfPhase3Blocker::CollectorEvidenceWriterStarted,
    );

    let mut scorecard_writer = StockEtfCollectorRunV1::source_fixture();
    scorecard_writer.scorecard_writer_started = true;
    assert_single_phase3_blocker(
        scorecard_writer,
        StockEtfPhase3Blocker::ScorecardWriterStarted,
    );

    let mut db_apply = StockEtfCollectorRunV1::source_fixture();
    db_apply.db_apply_performed = true;
    assert_single_phase3_blocker(db_apply, StockEtfPhase3Blocker::DbApplyPerformed);

    let mut secret = StockEtfCollectorRunV1::source_fixture();
    secret.secret_content_serialized = true;
    assert_single_phase3_blocker(secret, StockEtfPhase3Blocker::SecretContentSerialized);

    let mut live_authority = StockEtfCollectorRunV1::source_fixture();
    live_authority.live_or_tiny_live_authorized = true;
    assert_single_phase3_blocker(
        live_authority,
        StockEtfPhase3Blocker::LiveOrTinyLiveAuthorized,
    );
}

#[test]
fn default_evidence_clock_day_is_not_a_pass_day() {
    let verdict = StockEtfEvidenceClockDayV1::default().validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![
            StockEtfPhase3Blocker::EvidenceClockContractIdMismatch,
            StockEtfPhase3Blocker::EvidenceClockVersionMismatch,
            StockEtfPhase3Blocker::EvidenceClockWrongAssetLane,
            StockEtfPhase3Blocker::EvidenceClockWrongBroker,
            StockEtfPhase3Blocker::EvidenceClockEnvironmentDenied,
            StockEtfPhase3Blocker::EvidenceClockCollectorRunContractMismatch,
            StockEtfPhase3Blocker::EvidenceClockCollectorRunHashInvalid,
            StockEtfPhase3Blocker::EvidenceClockDqManifestContractMismatch,
            StockEtfPhase3Blocker::EvidenceClockDqManifestHashInvalid,
            StockEtfPhase3Blocker::EvidenceClockSourceArtifactHashInvalid,
            StockEtfPhase3Blocker::EvidenceClockMarketDataProvenanceHashInvalid,
            StockEtfPhase3Blocker::EvidenceClockScorecardInputHashInvalid,
            StockEtfPhase3Blocker::BybitLiveExecutionNotProtected,
            StockEtfPhase3Blocker::IbkrConnectorNotGreenFiveDays,
            StockEtfPhase3Blocker::ShadowCollectorNotGreenFiveDays,
            StockEtfPhase3Blocker::FrozenInputsRejected,
            StockEtfPhase3Blocker::DqManifestShapeRejected,
        ]
    );
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
    assert_eq!(
        pass.collector_run_contract_id,
        STOCK_ETF_COLLECTOR_RUN_CONTRACT_ID
    );
    assert_eq!(
        pass.dq_manifest_contract_id,
        STOCK_ETF_DQ_MANIFEST_CONTRACT_ID
    );
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
    assert_eq!(
        verdict.blockers,
        vec![StockEtfPhase3Blocker::IbkrConnectorNotGreenFiveDays]
    );

    let mut weak_dq = pass;
    weak_dq.dq_manifest.calendar_aware_coverage_bps = 9_900;
    let weak_verdict = weak_dq.validate();
    assert!(!weak_verdict.accepted);
    assert_eq!(
        weak_verdict.blockers,
        vec![StockEtfPhase3Blocker::PassDayQualityRejected]
    );
}

#[test]
fn evidence_clock_day_rejects_contract_drift_and_checker_side_effects() {
    use StockEtfPhase3Blocker as Blocker;

    let mut day = StockEtfEvidenceClockDayV1::pass_day_fixture();
    day.contract_id = "stock_etf_evidence_clock_v2".to_string();
    day.source_version = 2;
    day.asset_lane = AssetLane::CryptoPerp;
    day.broker = Broker::Bybit;
    day.environment = BrokerEnvironment::LiveReservedDenied;
    day.collector_run_contract_id = "stock_etf_collector_run_v2".to_string();
    day.collector_run_contract_hash.clear();
    day.dq_manifest_contract_id = "stock_etf_dq_manifest_v2".to_string();
    day.dq_manifest_contract_hash.clear();
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

    assert_eq!(
        blockers,
        vec![
            Blocker::EvidenceClockContractIdMismatch,
            Blocker::EvidenceClockVersionMismatch,
            Blocker::EvidenceClockWrongAssetLane,
            Blocker::EvidenceClockWrongBroker,
            Blocker::EvidenceClockEnvironmentDenied,
            Blocker::EvidenceClockCollectorRunContractMismatch,
            Blocker::EvidenceClockCollectorRunHashInvalid,
            Blocker::EvidenceClockDqManifestContractMismatch,
            Blocker::EvidenceClockDqManifestHashInvalid,
            Blocker::EvidenceClockSourceArtifactHashInvalid,
            Blocker::EvidenceClockMarketDataProvenanceHashInvalid,
            Blocker::EvidenceClockScorecardInputHashInvalid,
            Blocker::BybitLiveExecutionNotProtected,
            Blocker::IbkrContactPerformed,
            Blocker::ConnectorRuntimeStarted,
            Blocker::EvidenceClockRuntimeStarted,
            Blocker::ScorecardWriterStarted,
            Blocker::DbApplyPerformed,
            Blocker::SecretContentSerialized,
            Blocker::LiveOrTinyLiveAuthorized,
        ]
    );
}

#[test]
fn evidence_clock_day_rejects_runtime_writer_secret_and_authority_cross_wire_independently() {
    let mut bybit = StockEtfEvidenceClockDayV1::pass_day_fixture();
    bybit.bybit_live_execution_unchanged = false;
    assert_single_evidence_clock_blocker(
        bybit,
        StockEtfPhase3Blocker::BybitLiveExecutionNotProtected,
    );

    let mut ibkr_contact = StockEtfEvidenceClockDayV1::pass_day_fixture();
    ibkr_contact.checker_contacted_ibkr = true;
    assert_single_evidence_clock_blocker(ibkr_contact, StockEtfPhase3Blocker::IbkrContactPerformed);

    let mut connector = StockEtfEvidenceClockDayV1::pass_day_fixture();
    connector.checker_started_connector_runtime = true;
    assert_single_evidence_clock_blocker(connector, StockEtfPhase3Blocker::ConnectorRuntimeStarted);

    let mut evidence_clock = StockEtfEvidenceClockDayV1::pass_day_fixture();
    evidence_clock.checker_started_evidence_clock = true;
    assert_single_evidence_clock_blocker(
        evidence_clock,
        StockEtfPhase3Blocker::EvidenceClockRuntimeStarted,
    );

    let mut scorecard_writer = StockEtfEvidenceClockDayV1::pass_day_fixture();
    scorecard_writer.checker_wrote_scorecard = true;
    assert_single_evidence_clock_blocker(
        scorecard_writer,
        StockEtfPhase3Blocker::ScorecardWriterStarted,
    );

    let mut db_apply = StockEtfEvidenceClockDayV1::pass_day_fixture();
    db_apply.checker_applied_db = true;
    assert_single_evidence_clock_blocker(db_apply, StockEtfPhase3Blocker::DbApplyPerformed);

    let mut secret = StockEtfEvidenceClockDayV1::pass_day_fixture();
    secret.secret_content_serialized = true;
    assert_single_evidence_clock_blocker(secret, StockEtfPhase3Blocker::SecretContentSerialized);

    let mut live_authority = StockEtfEvidenceClockDayV1::pass_day_fixture();
    live_authority.live_or_tiny_live_authorized = true;
    assert_single_evidence_clock_blocker(
        live_authority,
        StockEtfPhase3Blocker::LiveOrTinyLiveAuthorized,
    );

    let mut connector_green = StockEtfEvidenceClockDayV1::pass_day_fixture();
    connector_green.ibkr_readonly_paper_connector_green_5d = false;
    assert_single_evidence_clock_blocker(
        connector_green,
        StockEtfPhase3Blocker::IbkrConnectorNotGreenFiveDays,
    );

    let mut shadow_green = StockEtfEvidenceClockDayV1::pass_day_fixture();
    shadow_green.shadow_collector_green_5d = false;
    assert_single_evidence_clock_blocker(
        shadow_green,
        StockEtfPhase3Blocker::ShadowCollectorNotGreenFiveDays,
    );
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
    assert_eq!(
        verdict.blockers,
        vec![StockEtfPhase3Blocker::QuarantinedDayWithoutDqFailure]
    );
}

#[test]
fn window_complete_status_is_not_source_authorized_by_checker_fixture() {
    let day = StockEtfEvidenceClockDayV1 {
        status: StockEtfEvidenceClockStatus::WindowComplete,
        ..StockEtfEvidenceClockDayV1::pass_day_fixture()
    };
    let verdict = day.validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![StockEtfPhase3Blocker::WindowCompleteNotSourceAuthorized]
    );
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
    assert_eq!(parsed["collector_run"]["contract_id"].as_str(), Some(""));
    assert_eq!(
        parsed["collector_run"]["source_version"].as_integer(),
        Some(0)
    );
    assert_eq!(
        parsed["collector_run"]["asset_lane"].as_str(),
        Some("crypto_perp")
    );
    assert_eq!(parsed["collector_run"]["broker"].as_str(), Some("bybit"));
    assert_eq!(
        parsed["collector_run"]["environment"].as_str(),
        Some("live_reserved_denied")
    );
    assert_eq!(
        parsed["collector_run"]["expected_trading_sessions"].as_integer(),
        Some(0)
    );
    assert_eq!(
        parsed["collector_run"]["completed_trading_sessions"].as_integer(),
        Some(0)
    );
    assert_eq!(
        parsed["collector_run"]["market_data_ingestion_started"].as_bool(),
        Some(false)
    );
    assert_eq!(
        parsed["collector_run"]["evidence_writer_started"].as_bool(),
        Some(false)
    );
    assert_eq!(
        parsed["collector_run"]["scorecard_writer_started"].as_bool(),
        Some(false)
    );
    assert_eq!(
        parsed["collector_run"]["db_apply_performed"].as_bool(),
        Some(false)
    );
    assert_eq!(
        STOCK_ETF_COLLECTOR_RUN_CONTRACT_ID,
        "stock_etf_collector_run_v1"
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
        parsed["evidence_clock_day"]["collector_run_contract_id"].as_str(),
        Some("")
    );
    assert_eq!(
        parsed["evidence_clock_day"]["collector_run_contract_hash"].as_str(),
        Some("")
    );
    assert_eq!(
        parsed["evidence_clock_day"]["dq_manifest_contract_id"].as_str(),
        Some("")
    );
    assert_eq!(
        parsed["evidence_clock_day"]["dq_manifest_contract_hash"].as_str(),
        Some("")
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
    assert_eq!(parsed["dq_manifest"]["contract_id"].as_str(), Some(""));
    assert_eq!(
        parsed["dq_manifest"]["source_version"].as_integer(),
        Some(0)
    );
    assert_eq!(
        STOCK_ETF_DQ_MANIFEST_CONTRACT_ID,
        "stock_etf_dq_manifest_v1"
    );
    assert_eq!(
        parsed["dq_manifest"]["market_data_ingestion_started"].as_bool(),
        Some(false)
    );
    assert_eq!(
        parsed["dq_manifest"]["dq_writer_started"].as_bool(),
        Some(false)
    );
    assert_eq!(
        parsed["dq_manifest"]["evidence_clock_started"].as_bool(),
        Some(false)
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

fn assert_single_phase3_blocker(collector: StockEtfCollectorRunV1, blocker: StockEtfPhase3Blocker) {
    let verdict = collector.validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![blocker],
        "expected only {blocker:?}; blockers: {:?}",
        verdict.blockers
    );
}

fn assert_single_evidence_clock_blocker(
    day: StockEtfEvidenceClockDayV1,
    blocker: StockEtfPhase3Blocker,
) {
    let verdict = day.validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![blocker],
        "expected only {blocker:?}; blockers: {:?}",
        verdict.blockers
    );
}
