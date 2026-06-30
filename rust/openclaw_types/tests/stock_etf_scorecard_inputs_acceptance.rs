//! ADR-0048 Stock/ETF scorecard input contract acceptance tests.
//!
//! These tests validate source-only input evidence shape. They do not contact
//! IBKR, import broker fills, derive scorecards, write PG, or start an evidence
//! clock.

use std::path::PathBuf;

use openclaw_types::{
    BrokerAccountPortfolioCashLedgerV1, BrokerEnvironment, StockEtfBenchmarkVersionV1,
    StockEtfCostModelVersionV1, StockEtfScorecardInputBlocker, StockEtfScorecardInputBundleV1,
    StockEtfStorageCapacityV1, StockShadowFillModelV1,
    BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID, STOCK_ETF_BENCHMARK_VERSIONS_CONTRACT_ID,
    STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID, STOCK_ETF_STORAGE_CAPACITY_CONTRACT_ID,
    STOCK_SHADOW_FILL_MODEL_CONTRACT_ID,
};

#[test]
fn default_scorecard_bundle_blocks_all_atomic_inputs() {
    let verdict = StockEtfScorecardInputBundleV1::default().validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::CashLedgerRejected));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::CostModelRejected));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::BenchmarkRejected));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::ShadowFillModelRejected));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::StorageCapacityRejected));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::MarketDataProvenanceContractHashInvalid));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::ReferenceDataSourcesContractHashInvalid));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::RiskPolicyContractHashInvalid));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::ScorecardNotDerivedOnly));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::BybitLiveExecutionNotProtected));
}

#[test]
fn accepted_fixture_keeps_scorecard_derived_and_live_separate() {
    let bundle = StockEtfScorecardInputBundleV1::accepted_fixture();
    let verdict = bundle.validate();

    assert!(verdict.accepted);
    assert!(verdict.blockers.is_empty());
    assert!(bundle.scorecard_is_derived_only);
    assert!(bundle.paper_and_shadow_fills_separate);
    assert!(!bundle.live_fill_claimed);
    assert_eq!(
        bundle.cash_ledger.contract_id,
        BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID
    );
    assert_eq!(
        bundle.cost_model.contract_id,
        STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID
    );
    assert_eq!(
        bundle.benchmark.contract_id,
        STOCK_ETF_BENCHMARK_VERSIONS_CONTRACT_ID
    );
    assert_eq!(
        bundle.shadow_fill_model.contract_id,
        STOCK_SHADOW_FILL_MODEL_CONTRACT_ID
    );
    assert_eq!(
        bundle.storage_capacity.contract_id,
        STOCK_ETF_STORAGE_CAPACITY_CONTRACT_ID
    );
    assert_eq!(bundle.cash_ledger.source_version, 1);
    assert_eq!(bundle.cost_model.source_version, 1);
    assert_eq!(bundle.benchmark.source_version, 1);
    assert_eq!(bundle.shadow_fill_model.source_version, 1);
    assert_eq!(bundle.storage_capacity.source_version, 1);
    assert_eq!(bundle.market_data_provenance_contract_hash.len(), 64);
    assert_eq!(bundle.reference_data_sources_contract_hash.len(), 64);
    assert_eq!(bundle.risk_policy_contract_hash.len(), 64);
    assert!(bundle.bybit_live_execution_unchanged);
    assert!(!bundle.ibkr_contact_performed);
    assert!(!bundle.connector_runtime_started);
    assert!(!bundle.broker_fill_import_performed);
    assert!(!bundle.scorecard_writer_started);
    assert!(!bundle.db_apply_performed);
    assert!(!bundle.evidence_clock_started);
    assert!(!bundle.secret_content_serialized);
    assert!(!bundle.live_or_tiny_live_authorized);
}

#[test]
fn scorecard_subcontracts_require_named_contract_ids_and_source_versions() {
    let mut ledger = BrokerAccountPortfolioCashLedgerV1::accepted_fixture();
    ledger.contract_id = "wrong_cash_ledger_v1".to_string();
    ledger.source_version = 2;

    let mut cost = StockEtfCostModelVersionV1::accepted_fixture();
    cost.contract_id.clear();
    cost.source_version = 0;

    let mut benchmark = StockEtfBenchmarkVersionV1::accepted_fixture();
    benchmark.contract_id = "benchmark_versions_v2".to_string();
    benchmark.source_version = 2;

    let mut shadow = StockShadowFillModelV1::accepted_fill_fixture();
    shadow.contract_id.clear();
    shadow.source_version = 3;

    let mut storage = StockEtfStorageCapacityV1::accepted_fixture();
    storage.contract_id = "stock_etf_storage_capacity_v2".to_string();
    storage.source_version = 2;

    for blockers in [
        ledger.validate().blockers,
        cost.validate().blockers,
        benchmark.validate().blockers,
        shadow.validate().blockers,
        storage.validate().blockers,
    ] {
        assert!(blockers.contains(&StockEtfScorecardInputBlocker::ContractIdMismatch));
        assert!(blockers.contains(&StockEtfScorecardInputBlocker::SourceVersionMismatch));
    }
}

#[test]
fn cash_ledger_rejects_live_environment_and_missing_hashes() {
    let mut ledger = BrokerAccountPortfolioCashLedgerV1::accepted_fixture();
    ledger.environment = BrokerEnvironment::LiveReservedDenied;
    ledger.account_snapshot_hash.clear();

    let verdict = ledger.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::CashLedgerEnvironmentDenied));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::AccountSnapshotHashInvalid));
}

#[test]
fn shadow_fill_must_be_synthetic_and_never_linked_to_broker_or_live_fill() {
    let mut shadow = StockShadowFillModelV1::accepted_fill_fixture();
    shadow.synthetic_shadow = false;
    shadow.broker_paper_fill_linked = true;
    shadow.live_fill_linked = true;

    let verdict = shadow.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::SyntheticShadowMarkerMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::ShadowFillLinkedToBrokerPaperFill));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::ShadowFillLinkedToLiveFill));
}

#[test]
fn storage_capacity_requires_forward_capacity_policy_before_evidence_clock() {
    let mut storage = StockEtfStorageCapacityV1::accepted_fixture();
    storage.capacity_breach_blocks_evidence_clock = false;
    storage.capacity_plan_hash.clear();
    storage.rows_per_day_estimate = 0;

    let verdict = storage.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::CapacityBreachPolicyMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::CapacityPlanHashInvalid));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::RowsPerDayEstimateMissing));
}

#[test]
fn scorecard_bundle_rejects_live_fill_claim_and_missing_separation() {
    let mut bundle = StockEtfScorecardInputBundleV1::accepted_fixture();
    bundle.scorecard_is_derived_only = false;
    bundle.paper_and_shadow_fills_separate = false;
    bundle.live_fill_claimed = true;

    let verdict = bundle.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::ScorecardNotDerivedOnly));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::PaperShadowFillSeparationMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::LiveFillClaimed));
}

#[test]
fn scorecard_bundle_rejects_missing_cross_contract_hashes_and_runtime_side_effects() {
    let mut bundle = StockEtfScorecardInputBundleV1::accepted_fixture();
    bundle.market_data_provenance_contract_hash.clear();
    bundle.reference_data_sources_contract_hash.clear();
    bundle.risk_policy_contract_hash.clear();
    bundle.bybit_live_execution_unchanged = false;
    bundle.ibkr_contact_performed = true;
    bundle.connector_runtime_started = true;
    bundle.broker_fill_import_performed = true;
    bundle.scorecard_writer_started = true;
    bundle.db_apply_performed = true;
    bundle.evidence_clock_started = true;
    bundle.secret_content_serialized = true;
    bundle.live_or_tiny_live_authorized = true;

    let verdict = bundle.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::MarketDataProvenanceContractHashInvalid));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::ReferenceDataSourcesContractHashInvalid));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::RiskPolicyContractHashInvalid));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::BybitLiveExecutionNotProtected));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::IbkrContactPerformed));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::ConnectorRuntimeStarted));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::BrokerFillImportPerformed));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::ScorecardWriterStarted));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::DbApplyPerformed));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::EvidenceClockStarted));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::SecretContentSerialized));
    assert!(verdict
        .blockers
        .contains(&StockEtfScorecardInputBlocker::LiveOrTinyLiveAuthorized));
}

#[test]
fn blocked_template_is_parseable_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/stock_etf_scorecard_inputs.template.toml"),
    )
    .expect("read scorecard input template");
    let parsed: StockEtfScorecardInputBundleV1 =
        toml::from_str(&raw).expect("scorecard input template parses");

    assert!(!parsed.scorecard_is_derived_only);
    assert!(!parsed.paper_and_shadow_fills_separate);
    assert!(!parsed.bybit_live_execution_unchanged);
    assert!(!parsed.ibkr_contact_performed);
    assert!(!parsed.connector_runtime_started);
    assert!(!parsed.broker_fill_import_performed);
    assert!(!parsed.scorecard_writer_started);
    assert!(!parsed.db_apply_performed);
    assert!(!parsed.evidence_clock_started);
    assert!(!parsed.secret_content_serialized);
    assert!(!parsed.live_or_tiny_live_authorized);
    assert!(parsed.market_data_provenance_contract_hash.is_empty());
    assert!(parsed.reference_data_sources_contract_hash.is_empty());
    assert!(parsed.risk_policy_contract_hash.is_empty());
    assert!(parsed.cash_ledger.contract_id.is_empty());
    assert_eq!(parsed.cash_ledger.source_version, 0);
    assert!(parsed.cost_model.contract_id.is_empty());
    assert_eq!(parsed.cost_model.source_version, 0);
    assert!(parsed.benchmark.contract_id.is_empty());
    assert_eq!(parsed.benchmark.source_version, 0);
    assert!(parsed.shadow_fill_model.contract_id.is_empty());
    assert_eq!(parsed.shadow_fill_model.source_version, 0);
    assert!(parsed.storage_capacity.contract_id.is_empty());
    assert_eq!(parsed.storage_capacity.source_version, 0);
    assert!(!parsed.validate().accepted);

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}
