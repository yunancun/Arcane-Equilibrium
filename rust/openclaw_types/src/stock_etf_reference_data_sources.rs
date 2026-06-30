//! Stock/ETF reference-data source contract for ADR-0048.
//!
//! This source-only validator pins corporate-action, FX, fee, and tax/FTT
//! source-as-of records before Phase 3 evidence-clock or scorecard workflows
//! can consume their hashes. It does not contact IBKR, inspect secrets, create
//! connectors, ingest data, write scorecards, apply migrations, or change Bybit
//! live execution behavior.

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_artifact::is_sha256_hex;
use crate::stock_etf_instrument_identity::StockEtfCurrency;
use crate::stock_etf_lane::{AssetLane, Broker, BrokerEnvironment};

pub const STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID: &str =
    "stock_etf_reference_data_sources_v1";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfReferenceDataSourcesV1 {
    pub contract_id: String,
    pub source_version: u16,
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub environment: BrokerEnvironment,
    pub frozen_for_evidence_clock: bool,
    pub corporate_action_source_name: String,
    pub corporate_action_asof_ms: u64,
    pub corporate_action_raw_hash: String,
    pub corporate_action_adjustment_version_hash: String,
    pub corporate_action_policy_hash: String,
    pub dividend_treatment_hash: String,
    pub fx_rate_source_name: String,
    pub fx_rate_asof_ms: u64,
    pub base_currency: StockEtfCurrency,
    pub quote_currency: StockEtfCurrency,
    pub fx_rate_snapshot_hash: String,
    pub fx_drag_model_hash: String,
    pub fee_schedule_source_name: String,
    pub fee_schedule_asof_ms: u64,
    pub commission_schedule_hash: String,
    pub exchange_regulatory_fee_hash: String,
    pub tax_ftt_placeholder_hash: String,
    pub withholding_tax_treatment_hash: String,
    pub source_artifact_hash: String,
    pub bybit_live_execution_unchanged: bool,
    pub ibkr_contact_performed: bool,
    pub connector_runtime_started: bool,
    pub secret_content_serialized: bool,
    pub live_or_tiny_live_authorized: bool,
}

impl Default for StockEtfReferenceDataSourcesV1 {
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            environment: BrokerEnvironment::LiveReservedDenied,
            frozen_for_evidence_clock: false,
            corporate_action_source_name: String::new(),
            corporate_action_asof_ms: 0,
            corporate_action_raw_hash: String::new(),
            corporate_action_adjustment_version_hash: String::new(),
            corporate_action_policy_hash: String::new(),
            dividend_treatment_hash: String::new(),
            fx_rate_source_name: String::new(),
            fx_rate_asof_ms: 0,
            base_currency: StockEtfCurrency::UnknownDenied,
            quote_currency: StockEtfCurrency::UnknownDenied,
            fx_rate_snapshot_hash: String::new(),
            fx_drag_model_hash: String::new(),
            fee_schedule_source_name: String::new(),
            fee_schedule_asof_ms: 0,
            commission_schedule_hash: String::new(),
            exchange_regulatory_fee_hash: String::new(),
            tax_ftt_placeholder_hash: String::new(),
            withholding_tax_treatment_hash: String::new(),
            source_artifact_hash: String::new(),
            bybit_live_execution_unchanged: false,
            ibkr_contact_performed: false,
            connector_runtime_started: false,
            secret_content_serialized: false,
            live_or_tiny_live_authorized: true,
        }
    }
}

impl StockEtfReferenceDataSourcesV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            contract_id: STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            environment: BrokerEnvironment::Paper,
            frozen_for_evidence_clock: true,
            corporate_action_source_name: "ibkr_contract_details_and_reference_feed".to_string(),
            corporate_action_asof_ms: 1_772_236_800_000,
            corporate_action_raw_hash: hash('1'),
            corporate_action_adjustment_version_hash: hash('2'),
            corporate_action_policy_hash: hash('3'),
            dividend_treatment_hash: hash('4'),
            fx_rate_source_name: "ibkr_paper_cash_ledger_usd_reference".to_string(),
            fx_rate_asof_ms: 1_772_236_800_000,
            base_currency: StockEtfCurrency::Usd,
            quote_currency: StockEtfCurrency::Usd,
            fx_rate_snapshot_hash: hash('5'),
            fx_drag_model_hash: hash('6'),
            fee_schedule_source_name: "ibkr_paper_us_stock_etf_fee_schedule".to_string(),
            fee_schedule_asof_ms: 1_772_236_800_000,
            commission_schedule_hash: hash('7'),
            exchange_regulatory_fee_hash: hash('8'),
            tax_ftt_placeholder_hash: hash('9'),
            withholding_tax_treatment_hash: hash('a'),
            source_artifact_hash: hash('b'),
            bybit_live_execution_unchanged: true,
            ibkr_contact_performed: false,
            connector_runtime_started: false,
            secret_content_serialized: false,
            live_or_tiny_live_authorized: false,
        }
    }

    pub fn validate(
        &self,
    ) -> StockEtfReferenceDataSourcesVerdict<StockEtfReferenceDataSourcesBlocker> {
        use StockEtfReferenceDataSourcesBlocker as Blocker;
        let mut blockers = Vec::new();

        if self.contract_id != STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID {
            blockers.push(Blocker::ContractIdMismatch);
        }
        if self.source_version != 1 {
            blockers.push(Blocker::SourceVersionMismatch);
        }
        if self.asset_lane != AssetLane::StockEtfCash {
            blockers.push(Blocker::WrongAssetLane);
        }
        if self.broker != Broker::Ibkr {
            blockers.push(Blocker::WrongBroker);
        }
        if !matches!(
            self.environment,
            BrokerEnvironment::ReadOnly | BrokerEnvironment::Paper | BrokerEnvironment::Shadow
        ) {
            blockers.push(Blocker::EnvironmentDenied);
        }
        if !self.frozen_for_evidence_clock {
            blockers.push(Blocker::EvidenceClockFreezeMissing);
        }

        validate_corporate_action_sources(self, &mut blockers);
        validate_fx_sources(self, &mut blockers);
        validate_fee_tax_sources(self, &mut blockers);

        if !is_sha256_hex(&self.source_artifact_hash) {
            blockers.push(Blocker::SourceArtifactHashInvalid);
        }
        if !self.bybit_live_execution_unchanged {
            blockers.push(Blocker::BybitLiveExecutionNotProtected);
        }
        if self.ibkr_contact_performed {
            blockers.push(Blocker::IbkrContactPerformed);
        }
        if self.connector_runtime_started {
            blockers.push(Blocker::ConnectorRuntimeStarted);
        }
        if self.secret_content_serialized {
            blockers.push(Blocker::SecretContentSerialized);
        }
        if self.live_or_tiny_live_authorized {
            blockers.push(Blocker::LiveOrTinyLiveAuthorized);
        }

        StockEtfReferenceDataSourcesVerdict::new(blockers)
    }
}

fn validate_corporate_action_sources(
    sources: &StockEtfReferenceDataSourcesV1,
    blockers: &mut Vec<StockEtfReferenceDataSourcesBlocker>,
) {
    use StockEtfReferenceDataSourcesBlocker as Blocker;

    if sources.corporate_action_source_name.trim().is_empty() {
        blockers.push(Blocker::CorporateActionSourceMissing);
    }
    if sources.corporate_action_asof_ms == 0 {
        blockers.push(Blocker::CorporateActionAsOfMissing);
    }
    if !is_sha256_hex(&sources.corporate_action_raw_hash) {
        blockers.push(Blocker::CorporateActionRawHashInvalid);
    }
    if !is_sha256_hex(&sources.corporate_action_adjustment_version_hash) {
        blockers.push(Blocker::CorporateActionAdjustmentHashInvalid);
    }
    if !is_sha256_hex(&sources.corporate_action_policy_hash) {
        blockers.push(Blocker::CorporateActionPolicyHashInvalid);
    }
    if !is_sha256_hex(&sources.dividend_treatment_hash) {
        blockers.push(Blocker::DividendTreatmentHashInvalid);
    }
}

fn validate_fx_sources(
    sources: &StockEtfReferenceDataSourcesV1,
    blockers: &mut Vec<StockEtfReferenceDataSourcesBlocker>,
) {
    use StockEtfReferenceDataSourcesBlocker as Blocker;

    if sources.fx_rate_source_name.trim().is_empty() {
        blockers.push(Blocker::FxRateSourceMissing);
    }
    if sources.fx_rate_asof_ms == 0 {
        blockers.push(Blocker::FxRateAsOfMissing);
    }
    if sources.base_currency != StockEtfCurrency::Usd
        || sources.quote_currency != StockEtfCurrency::Usd
    {
        blockers.push(Blocker::CurrencyDenied);
    }
    if !is_sha256_hex(&sources.fx_rate_snapshot_hash) {
        blockers.push(Blocker::FxRateSnapshotHashInvalid);
    }
    if !is_sha256_hex(&sources.fx_drag_model_hash) {
        blockers.push(Blocker::FxDragModelHashInvalid);
    }
}

fn validate_fee_tax_sources(
    sources: &StockEtfReferenceDataSourcesV1,
    blockers: &mut Vec<StockEtfReferenceDataSourcesBlocker>,
) {
    use StockEtfReferenceDataSourcesBlocker as Blocker;

    if sources.fee_schedule_source_name.trim().is_empty() {
        blockers.push(Blocker::FeeScheduleSourceMissing);
    }
    if sources.fee_schedule_asof_ms == 0 {
        blockers.push(Blocker::FeeScheduleAsOfMissing);
    }
    if !is_sha256_hex(&sources.commission_schedule_hash) {
        blockers.push(Blocker::CommissionScheduleHashInvalid);
    }
    if !is_sha256_hex(&sources.exchange_regulatory_fee_hash) {
        blockers.push(Blocker::ExchangeRegulatoryFeeHashInvalid);
    }
    if !is_sha256_hex(&sources.tax_ftt_placeholder_hash) {
        blockers.push(Blocker::TaxFttPlaceholderHashInvalid);
    }
    if !is_sha256_hex(&sources.withholding_tax_treatment_hash) {
        blockers.push(Blocker::WithholdingTaxTreatmentHashInvalid);
    }
}

fn hash(c: char) -> String {
    c.to_string().repeat(64)
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfReferenceDataSourcesVerdict<B> {
    pub accepted: bool,
    pub blockers: Vec<B>,
}

impl<B> StockEtfReferenceDataSourcesVerdict<B> {
    fn new(blockers: Vec<B>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfReferenceDataSourcesBlocker {
    ContractIdMismatch,
    SourceVersionMismatch,
    WrongAssetLane,
    WrongBroker,
    EnvironmentDenied,
    EvidenceClockFreezeMissing,
    CorporateActionSourceMissing,
    CorporateActionAsOfMissing,
    CorporateActionRawHashInvalid,
    CorporateActionAdjustmentHashInvalid,
    CorporateActionPolicyHashInvalid,
    DividendTreatmentHashInvalid,
    FxRateSourceMissing,
    FxRateAsOfMissing,
    CurrencyDenied,
    FxRateSnapshotHashInvalid,
    FxDragModelHashInvalid,
    FeeScheduleSourceMissing,
    FeeScheduleAsOfMissing,
    CommissionScheduleHashInvalid,
    ExchangeRegulatoryFeeHashInvalid,
    TaxFttPlaceholderHashInvalid,
    WithholdingTaxTreatmentHashInvalid,
    SourceArtifactHashInvalid,
    BybitLiveExecutionNotProtected,
    IbkrContactPerformed,
    ConnectorRuntimeStarted,
    SecretContentSerialized,
    LiveOrTinyLiveAuthorized,
}
