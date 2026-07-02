//! ADR-0048 Stock/ETF Phase 3 DQ manifest contract acceptance tests.
//!
//! These tests validate source evidence checkers only. They do not ingest
//! market data, start an evidence clock, contact IBKR, or write scorecards.

use openclaw_types::{
    AssetLane, Broker, BrokerEnvironment, StockEtfDailyDqManifestV1, StockEtfPhase3Blocker,
    STOCK_ETF_DQ_MANIFEST_CONTRACT_ID, STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID,
};

#[test]
fn dq_manifest_shape_is_separate_from_pass_day_quality() {
    let mut manifest = StockEtfDailyDqManifestV1::pass_fixture();
    manifest.market_data_provenance_accepted = false;

    assert!(manifest.validates_shape().accepted);
    assert!(!manifest.passes_day_quality());
}

#[test]
fn default_dq_manifest_blocks_named_contract_and_lineage() {
    let verdict = StockEtfDailyDqManifestV1::default().validates_shape();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![
            StockEtfPhase3Blocker::DqManifestContractIdMismatch,
            StockEtfPhase3Blocker::DqManifestVersionMismatch,
            StockEtfPhase3Blocker::DqManifestWrongAssetLane,
            StockEtfPhase3Blocker::DqManifestWrongBroker,
            StockEtfPhase3Blocker::DqManifestEnvironmentDenied,
            StockEtfPhase3Blocker::DqManifestCollectorRunIdMissing,
            StockEtfPhase3Blocker::DqManifestMarketDataProvenanceContractMismatch,
            StockEtfPhase3Blocker::DqManifestMarketDataProvenanceHashInvalid,
            StockEtfPhase3Blocker::DqManifestSourceArtifactHashInvalid,
            StockEtfPhase3Blocker::BybitLiveExecutionNotProtected,
            StockEtfPhase3Blocker::TradingDayMissing,
            StockEtfPhase3Blocker::QuarantineManifestHashInvalid,
            StockEtfPhase3Blocker::AtomicFactInputHashInvalid,
        ]
    );
}

#[test]
fn source_dq_manifest_has_named_contract_lineage_and_no_side_effects() {
    let manifest = StockEtfDailyDqManifestV1::pass_fixture();
    let verdict = manifest.validates_shape();

    assert!(verdict.accepted);
    assert!(verdict.blockers.is_empty());
    assert_eq!(manifest.contract_id, STOCK_ETF_DQ_MANIFEST_CONTRACT_ID);
    assert_eq!(manifest.source_version, 1);
    assert_eq!(manifest.asset_lane, AssetLane::StockEtfCash);
    assert_eq!(manifest.broker, Broker::Ibkr);
    assert_eq!(manifest.environment, BrokerEnvironment::Paper);
    assert_eq!(
        manifest.market_data_provenance_contract_id,
        STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID
    );
    assert!(manifest.bybit_live_execution_unchanged);
    assert!(!manifest.ibkr_contact_performed);
    assert!(!manifest.connector_runtime_started);
    assert!(!manifest.market_data_ingestion_started);
    assert!(!manifest.dq_writer_started);
    assert!(!manifest.evidence_clock_started);
    assert!(!manifest.scorecard_writer_started);
    assert!(!manifest.db_apply_performed);
    assert!(!manifest.secret_content_serialized);
    assert!(!manifest.live_or_tiny_live_authorized);
}

#[test]
fn dq_manifest_rejects_runtime_side_effect_claims() {
    use StockEtfPhase3Blocker as Blocker;

    let mut manifest = StockEtfDailyDqManifestV1::pass_fixture();
    manifest.bybit_live_execution_unchanged = false;
    manifest.ibkr_contact_performed = true;
    manifest.connector_runtime_started = true;
    manifest.market_data_ingestion_started = true;
    manifest.dq_writer_started = true;
    manifest.evidence_clock_started = true;
    manifest.scorecard_writer_started = true;
    manifest.db_apply_performed = true;
    manifest.secret_content_serialized = true;
    manifest.live_or_tiny_live_authorized = true;

    let blockers = manifest.validates_shape().blockers;

    assert_eq!(
        blockers,
        vec![
            Blocker::BybitLiveExecutionNotProtected,
            Blocker::IbkrContactPerformed,
            Blocker::ConnectorRuntimeStarted,
            Blocker::DqManifestMarketDataIngestionStarted,
            Blocker::DqManifestWriterStarted,
            Blocker::DqManifestEvidenceClockStarted,
            Blocker::ScorecardWriterStarted,
            Blocker::DbApplyPerformed,
            Blocker::SecretContentSerialized,
            Blocker::LiveOrTinyLiveAuthorized,
        ]
    );
}

#[test]
fn dq_manifest_rejects_runtime_writer_secret_and_authority_cross_wire_independently() {
    let mut bybit = StockEtfDailyDqManifestV1::pass_fixture();
    bybit.bybit_live_execution_unchanged = false;
    assert_single_dq_blocker(bybit, StockEtfPhase3Blocker::BybitLiveExecutionNotProtected);

    let mut ibkr_contact = StockEtfDailyDqManifestV1::pass_fixture();
    ibkr_contact.ibkr_contact_performed = true;
    assert_single_dq_blocker(ibkr_contact, StockEtfPhase3Blocker::IbkrContactPerformed);

    let mut connector = StockEtfDailyDqManifestV1::pass_fixture();
    connector.connector_runtime_started = true;
    assert_single_dq_blocker(connector, StockEtfPhase3Blocker::ConnectorRuntimeStarted);

    let mut ingestion = StockEtfDailyDqManifestV1::pass_fixture();
    ingestion.market_data_ingestion_started = true;
    assert_single_dq_blocker(
        ingestion,
        StockEtfPhase3Blocker::DqManifestMarketDataIngestionStarted,
    );

    let mut dq_writer = StockEtfDailyDqManifestV1::pass_fixture();
    dq_writer.dq_writer_started = true;
    assert_single_dq_blocker(dq_writer, StockEtfPhase3Blocker::DqManifestWriterStarted);

    let mut evidence_clock = StockEtfDailyDqManifestV1::pass_fixture();
    evidence_clock.evidence_clock_started = true;
    assert_single_dq_blocker(
        evidence_clock,
        StockEtfPhase3Blocker::DqManifestEvidenceClockStarted,
    );

    let mut scorecard_writer = StockEtfDailyDqManifestV1::pass_fixture();
    scorecard_writer.scorecard_writer_started = true;
    assert_single_dq_blocker(
        scorecard_writer,
        StockEtfPhase3Blocker::ScorecardWriterStarted,
    );

    let mut db_apply = StockEtfDailyDqManifestV1::pass_fixture();
    db_apply.db_apply_performed = true;
    assert_single_dq_blocker(db_apply, StockEtfPhase3Blocker::DbApplyPerformed);

    let mut secret = StockEtfDailyDqManifestV1::pass_fixture();
    secret.secret_content_serialized = true;
    assert_single_dq_blocker(secret, StockEtfPhase3Blocker::SecretContentSerialized);

    let mut live_authority = StockEtfDailyDqManifestV1::pass_fixture();
    live_authority.live_or_tiny_live_authorized = true;
    assert_single_dq_blocker(
        live_authority,
        StockEtfPhase3Blocker::LiveOrTinyLiveAuthorized,
    );
}

fn assert_single_dq_blocker(manifest: StockEtfDailyDqManifestV1, blocker: StockEtfPhase3Blocker) {
    let verdict = manifest.validates_shape();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![blocker],
        "expected only {blocker:?}; blockers: {:?}",
        verdict.blockers
    );
}
