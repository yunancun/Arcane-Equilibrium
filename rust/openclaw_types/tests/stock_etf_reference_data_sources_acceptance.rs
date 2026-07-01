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
    assert_eq!(
        verdict.blockers,
        vec![
            StockEtfReferenceDataSourcesBlocker::ContractIdMismatch,
            StockEtfReferenceDataSourcesBlocker::SourceVersionMismatch,
            StockEtfReferenceDataSourcesBlocker::WrongAssetLane,
            StockEtfReferenceDataSourcesBlocker::WrongBroker,
            StockEtfReferenceDataSourcesBlocker::EnvironmentDenied,
            StockEtfReferenceDataSourcesBlocker::EvidenceClockFreezeMissing,
            StockEtfReferenceDataSourcesBlocker::CorporateActionSourceMissing,
            StockEtfReferenceDataSourcesBlocker::CorporateActionAsOfMissing,
            StockEtfReferenceDataSourcesBlocker::CorporateActionRawHashInvalid,
            StockEtfReferenceDataSourcesBlocker::CorporateActionAdjustmentHashInvalid,
            StockEtfReferenceDataSourcesBlocker::CorporateActionPolicyHashInvalid,
            StockEtfReferenceDataSourcesBlocker::DividendTreatmentHashInvalid,
            StockEtfReferenceDataSourcesBlocker::FxRateSourceMissing,
            StockEtfReferenceDataSourcesBlocker::FxRateAsOfMissing,
            StockEtfReferenceDataSourcesBlocker::CurrencyDenied,
            StockEtfReferenceDataSourcesBlocker::FxRateSnapshotHashInvalid,
            StockEtfReferenceDataSourcesBlocker::FxDragModelHashInvalid,
            StockEtfReferenceDataSourcesBlocker::FeeScheduleSourceMissing,
            StockEtfReferenceDataSourcesBlocker::FeeScheduleAsOfMissing,
            StockEtfReferenceDataSourcesBlocker::CommissionScheduleHashInvalid,
            StockEtfReferenceDataSourcesBlocker::ExchangeRegulatoryFeeHashInvalid,
            StockEtfReferenceDataSourcesBlocker::TaxFttPlaceholderHashInvalid,
            StockEtfReferenceDataSourcesBlocker::WithholdingTaxTreatmentHashInvalid,
            StockEtfReferenceDataSourcesBlocker::SourceArtifactHashInvalid,
            StockEtfReferenceDataSourcesBlocker::BybitLiveExecutionNotProtected,
            StockEtfReferenceDataSourcesBlocker::LiveOrTinyLiveAuthorized,
        ]
    );
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

    assert_eq!(
        blockers,
        vec![
            StockEtfReferenceDataSourcesBlocker::ContractIdMismatch,
            StockEtfReferenceDataSourcesBlocker::SourceVersionMismatch,
        ]
    );
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

    assert_eq!(
        blockers,
        vec![
            StockEtfReferenceDataSourcesBlocker::CorporateActionSourceMissing,
            StockEtfReferenceDataSourcesBlocker::CorporateActionAsOfMissing,
            StockEtfReferenceDataSourcesBlocker::CorporateActionRawHashInvalid,
            StockEtfReferenceDataSourcesBlocker::CorporateActionAdjustmentHashInvalid,
            StockEtfReferenceDataSourcesBlocker::CorporateActionPolicyHashInvalid,
            StockEtfReferenceDataSourcesBlocker::DividendTreatmentHashInvalid,
            StockEtfReferenceDataSourcesBlocker::FxRateSourceMissing,
            StockEtfReferenceDataSourcesBlocker::FxRateAsOfMissing,
            StockEtfReferenceDataSourcesBlocker::FxRateSnapshotHashInvalid,
            StockEtfReferenceDataSourcesBlocker::FxDragModelHashInvalid,
            StockEtfReferenceDataSourcesBlocker::FeeScheduleSourceMissing,
            StockEtfReferenceDataSourcesBlocker::FeeScheduleAsOfMissing,
            StockEtfReferenceDataSourcesBlocker::CommissionScheduleHashInvalid,
            StockEtfReferenceDataSourcesBlocker::ExchangeRegulatoryFeeHashInvalid,
            StockEtfReferenceDataSourcesBlocker::TaxFttPlaceholderHashInvalid,
            StockEtfReferenceDataSourcesBlocker::WithholdingTaxTreatmentHashInvalid,
        ]
    );
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

    assert_eq!(
        blockers,
        vec![
            StockEtfReferenceDataSourcesBlocker::EnvironmentDenied,
            StockEtfReferenceDataSourcesBlocker::EvidenceClockFreezeMissing,
            StockEtfReferenceDataSourcesBlocker::CurrencyDenied,
            StockEtfReferenceDataSourcesBlocker::BybitLiveExecutionNotProtected,
            StockEtfReferenceDataSourcesBlocker::IbkrContactPerformed,
            StockEtfReferenceDataSourcesBlocker::ConnectorRuntimeStarted,
            StockEtfReferenceDataSourcesBlocker::SecretContentSerialized,
            StockEtfReferenceDataSourcesBlocker::LiveOrTinyLiveAuthorized,
        ]
    );
}

#[test]
fn reference_sources_reject_runtime_freeze_and_authority_cross_wire_independently() {
    let mut environment = StockEtfReferenceDataSourcesV1::accepted_fixture();
    environment.environment = BrokerEnvironment::LiveReservedDenied;
    assert_single_blocker(
        environment,
        StockEtfReferenceDataSourcesBlocker::EnvironmentDenied,
    );

    let mut freeze = StockEtfReferenceDataSourcesV1::accepted_fixture();
    freeze.frozen_for_evidence_clock = false;
    assert_single_blocker(
        freeze,
        StockEtfReferenceDataSourcesBlocker::EvidenceClockFreezeMissing,
    );

    let mut currency = StockEtfReferenceDataSourcesV1::accepted_fixture();
    currency.base_currency = StockEtfCurrency::UnknownDenied;
    assert_single_blocker(
        currency,
        StockEtfReferenceDataSourcesBlocker::CurrencyDenied,
    );

    let mut bybit = StockEtfReferenceDataSourcesV1::accepted_fixture();
    bybit.bybit_live_execution_unchanged = false;
    assert_single_blocker(
        bybit,
        StockEtfReferenceDataSourcesBlocker::BybitLiveExecutionNotProtected,
    );

    let mut ibkr_contact = StockEtfReferenceDataSourcesV1::accepted_fixture();
    ibkr_contact.ibkr_contact_performed = true;
    assert_single_blocker(
        ibkr_contact,
        StockEtfReferenceDataSourcesBlocker::IbkrContactPerformed,
    );

    let mut connector = StockEtfReferenceDataSourcesV1::accepted_fixture();
    connector.connector_runtime_started = true;
    assert_single_blocker(
        connector,
        StockEtfReferenceDataSourcesBlocker::ConnectorRuntimeStarted,
    );

    let mut secret = StockEtfReferenceDataSourcesV1::accepted_fixture();
    secret.secret_content_serialized = true;
    assert_single_blocker(
        secret,
        StockEtfReferenceDataSourcesBlocker::SecretContentSerialized,
    );

    let mut live_authority = StockEtfReferenceDataSourcesV1::accepted_fixture();
    live_authority.live_or_tiny_live_authorized = true;
    assert_single_blocker(
        live_authority,
        StockEtfReferenceDataSourcesBlocker::LiveOrTinyLiveAuthorized,
    );
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

fn assert_single_blocker(
    sources: StockEtfReferenceDataSourcesV1,
    blocker: StockEtfReferenceDataSourcesBlocker,
) {
    let verdict = sources.validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![blocker],
        "expected only {blocker:?}; blockers: {:?}",
        verdict.blockers
    );
}
