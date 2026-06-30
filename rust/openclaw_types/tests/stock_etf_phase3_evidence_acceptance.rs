//! ADR-0048 Stock/ETF Phase 3 evidence contract acceptance tests.
//!
//! These tests validate source evidence checkers only. They do not ingest
//! market data, start an evidence clock, contact IBKR, or write scorecards.

use std::path::PathBuf;

use openclaw_types::{
    StockEtfDailyDqManifestV1, StockEtfEvidenceClockDayV1, StockEtfEvidenceClockStatus,
    StockEtfFrozenEvidenceInputsV1, StockEtfPhase3Blocker, StockMarketDataProvenanceV1,
};

#[test]
fn default_market_data_provenance_blocks_scorecard_readiness() {
    let verdict = StockMarketDataProvenanceV1::default().validate();

    assert!(!verdict.accepted);
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
    let verdict = StockMarketDataProvenanceV1::source_fixture().validate();

    assert!(verdict.accepted);
    assert!(verdict.blockers.is_empty());
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
        parsed["evidence_clock_day"]["status"].as_str(),
        Some("NOT_STARTED")
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
