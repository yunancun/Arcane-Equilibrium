//! ADR-0048 Stock/ETF reference-data source acceptance tests.
//!
//! These tests validate source-only corporate-action, FX, fee, and tax/FTT
//! source-as-of records. They do not contact IBKR, inspect secrets, create
//! connectors, ingest data, write scorecards, apply migrations, or mutate Bybit.

use std::path::PathBuf;

use openclaw_types::{
    AssetLane, Broker, BrokerEnvironment, StockEtfCurrency, StockEtfReferenceDataSourcesBlocker,
    StockEtfReferenceDataSourcesV1, STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID,
};

#[test]
fn default_reference_data_sources_block_phase3_usage() {
    let verdict = StockEtfReferenceDataSourcesV1::default().validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict.blockers,
        StockEtfReferenceDataSourcesBlocker::ContractIdMismatch
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfReferenceDataSourcesBlocker::SourceVersionMismatch
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfReferenceDataSourcesBlocker::WrongAssetLane
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfReferenceDataSourcesBlocker::WrongBroker
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfReferenceDataSourcesBlocker::EnvironmentDenied
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfReferenceDataSourcesBlocker::EvidenceClockFreezeMissing
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfReferenceDataSourcesBlocker::CorporateActionSourceMissing
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfReferenceDataSourcesBlocker::FxRateSourceMissing
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfReferenceDataSourcesBlocker::FeeScheduleSourceMissing
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfReferenceDataSourcesBlocker::LiveOrTinyLiveAuthorized
    ));
}

#[test]
fn accepted_fixture_pins_reference_sources_without_runtime_authority() {
    let sources = StockEtfReferenceDataSourcesV1::accepted_fixture();
    let verdict = sources.validate();

    assert!(
        verdict.accepted,
        "unexpected blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(
        sources.contract_id,
        STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID
    );
    assert_eq!(sources.source_version, 1);
    assert_eq!(sources.asset_lane, AssetLane::StockEtfCash);
    assert_eq!(sources.broker, Broker::Ibkr);
    assert_eq!(sources.environment, BrokerEnvironment::Paper);
    assert!(sources.frozen_for_evidence_clock);
    assert_eq!(sources.base_currency, StockEtfCurrency::Usd);
    assert_eq!(sources.quote_currency, StockEtfCurrency::Usd);
    assert!(sources.bybit_live_execution_unchanged);
    assert!(!sources.ibkr_contact_performed);
    assert!(!sources.connector_runtime_started);
    assert!(!sources.secret_content_serialized);
    assert!(!sources.live_or_tiny_live_authorized);
}

#[test]
fn reference_sources_require_exact_contract_id_and_source_version() {
    let mut sources = StockEtfReferenceDataSourcesV1::accepted_fixture();
    sources.contract_id = "stock_etf_reference_data_sources_v1_fixture".to_string();
    sources.source_version = 2;

    let blockers = sources.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfReferenceDataSourcesBlocker::ContractIdMismatch
    ));
    assert!(has(
        &blockers,
        StockEtfReferenceDataSourcesBlocker::SourceVersionMismatch
    ));
}

#[test]
fn corporate_action_fx_and_fee_sources_require_asof_and_hashes() {
    let mut sources = StockEtfReferenceDataSourcesV1::accepted_fixture();
    sources.corporate_action_source_name.clear();
    sources.corporate_action_asof_ms = 0;
    sources.corporate_action_raw_hash = "not-a-hash".to_string();
    sources.corporate_action_adjustment_version_hash.clear();
    sources.corporate_action_policy_hash.clear();
    sources.dividend_treatment_hash.clear();
    sources.fx_rate_source_name.clear();
    sources.fx_rate_asof_ms = 0;
    sources.fx_rate_snapshot_hash.clear();
    sources.fx_drag_model_hash.clear();
    sources.fee_schedule_source_name.clear();
    sources.fee_schedule_asof_ms = 0;
    sources.commission_schedule_hash.clear();
    sources.exchange_regulatory_fee_hash.clear();
    sources.tax_ftt_placeholder_hash.clear();
    sources.withholding_tax_treatment_hash.clear();

    let blockers = sources.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfReferenceDataSourcesBlocker::CorporateActionSourceMissing
    ));
    assert!(has(
        &blockers,
        StockEtfReferenceDataSourcesBlocker::CorporateActionAsOfMissing
    ));
    assert!(has(
        &blockers,
        StockEtfReferenceDataSourcesBlocker::CorporateActionRawHashInvalid
    ));
    assert!(has(
        &blockers,
        StockEtfReferenceDataSourcesBlocker::CorporateActionAdjustmentHashInvalid
    ));
    assert!(has(
        &blockers,
        StockEtfReferenceDataSourcesBlocker::DividendTreatmentHashInvalid
    ));
    assert!(has(
        &blockers,
        StockEtfReferenceDataSourcesBlocker::FxRateSourceMissing
    ));
    assert!(has(
        &blockers,
        StockEtfReferenceDataSourcesBlocker::FxRateAsOfMissing
    ));
    assert!(has(
        &blockers,
        StockEtfReferenceDataSourcesBlocker::FxRateSnapshotHashInvalid
    ));
    assert!(has(
        &blockers,
        StockEtfReferenceDataSourcesBlocker::FeeScheduleSourceMissing
    ));
    assert!(has(
        &blockers,
        StockEtfReferenceDataSourcesBlocker::CommissionScheduleHashInvalid
    ));
    assert!(has(
        &blockers,
        StockEtfReferenceDataSourcesBlocker::TaxFttPlaceholderHashInvalid
    ));
}

#[test]
fn reference_sources_reject_boundary_regressions() {
    let mut sources = StockEtfReferenceDataSourcesV1::accepted_fixture();
    sources.environment = BrokerEnvironment::LiveReservedDenied;
    sources.frozen_for_evidence_clock = false;
    sources.base_currency = StockEtfCurrency::UnknownDenied;
    sources.bybit_live_execution_unchanged = false;
    sources.ibkr_contact_performed = true;
    sources.connector_runtime_started = true;
    sources.secret_content_serialized = true;
    sources.live_or_tiny_live_authorized = true;

    let blockers = sources.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfReferenceDataSourcesBlocker::EnvironmentDenied
    ));
    assert!(has(
        &blockers,
        StockEtfReferenceDataSourcesBlocker::EvidenceClockFreezeMissing
    ));
    assert!(has(
        &blockers,
        StockEtfReferenceDataSourcesBlocker::CurrencyDenied
    ));
    assert!(has(
        &blockers,
        StockEtfReferenceDataSourcesBlocker::BybitLiveExecutionNotProtected
    ));
    assert!(has(
        &blockers,
        StockEtfReferenceDataSourcesBlocker::IbkrContactPerformed
    ));
    assert!(has(
        &blockers,
        StockEtfReferenceDataSourcesBlocker::ConnectorRuntimeStarted
    ));
    assert!(has(
        &blockers,
        StockEtfReferenceDataSourcesBlocker::SecretContentSerialized
    ));
    assert!(has(
        &blockers,
        StockEtfReferenceDataSourcesBlocker::LiveOrTinyLiveAuthorized
    ));
}

#[test]
fn blocked_template_is_parseable_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/stock_etf_reference_data_sources.template.toml"),
    )
    .expect("read reference-data source template");
    let parsed: StockEtfReferenceDataSourcesV1 =
        toml::from_str(&raw).expect("reference-data source template parses");

    assert_eq!(parsed.contract_id, "");
    assert_eq!(parsed.source_version, 0);
    assert_eq!(parsed.asset_lane, AssetLane::CryptoPerp);
    assert_eq!(parsed.broker, Broker::Bybit);
    assert!(!parsed.validate().accepted);
    assert!(!parsed.bybit_live_execution_unchanged);
    assert!(!parsed.ibkr_contact_performed);
    assert!(!parsed.secret_content_serialized);
    assert!(parsed.live_or_tiny_live_authorized);

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}

fn has(
    blockers: &[StockEtfReferenceDataSourcesBlocker],
    blocker: StockEtfReferenceDataSourcesBlocker,
) -> bool {
    blockers.contains(&blocker)
}
