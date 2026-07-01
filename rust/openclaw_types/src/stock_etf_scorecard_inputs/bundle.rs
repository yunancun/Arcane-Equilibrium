use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_artifact::is_sha256_hex;
use crate::stock_etf_ibkr_readonly_probe_result_import_request::STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID;

use super::{
    BrokerAccountPortfolioCashLedgerV1, StockEtfBenchmarkVersionV1, StockEtfCostModelVersionV1,
    StockEtfScorecardInputBlocker, StockEtfScorecardInputVerdict, StockEtfStorageCapacityV1,
    StockShadowFillModelV1,
};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfScorecardInputBundleV1 {
    pub cash_ledger: BrokerAccountPortfolioCashLedgerV1,
    pub cost_model: StockEtfCostModelVersionV1,
    pub benchmark: StockEtfBenchmarkVersionV1,
    pub shadow_fill_model: StockShadowFillModelV1,
    pub storage_capacity: StockEtfStorageCapacityV1,
    pub readonly_probe_result_import_request_contract_id: String,
    pub readonly_probe_result_import_request_hash: String,
    pub market_data_provenance_contract_hash: String,
    pub reference_data_sources_contract_hash: String,
    pub risk_policy_contract_hash: String,
    pub atomic_fact_input_hash: String,
    pub source_commit: String,
    pub scorecard_is_derived_only: bool,
    pub paper_and_shadow_fills_separate: bool,
    pub live_fill_claimed: bool,
    pub bybit_live_execution_unchanged: bool,
    pub ibkr_contact_performed: bool,
    pub connector_runtime_started: bool,
    pub broker_fill_import_performed: bool,
    pub scorecard_writer_started: bool,
    pub db_apply_performed: bool,
    pub evidence_clock_started: bool,
    pub secret_content_serialized: bool,
    pub live_or_tiny_live_authorized: bool,
}

impl Default for StockEtfScorecardInputBundleV1 {
    fn default() -> Self {
        Self {
            cash_ledger: BrokerAccountPortfolioCashLedgerV1::default(),
            cost_model: StockEtfCostModelVersionV1::default(),
            benchmark: StockEtfBenchmarkVersionV1::default(),
            shadow_fill_model: StockShadowFillModelV1::default(),
            storage_capacity: StockEtfStorageCapacityV1::default(),
            readonly_probe_result_import_request_contract_id: String::new(),
            readonly_probe_result_import_request_hash: String::new(),
            market_data_provenance_contract_hash: String::new(),
            reference_data_sources_contract_hash: String::new(),
            risk_policy_contract_hash: String::new(),
            atomic_fact_input_hash: String::new(),
            source_commit: String::new(),
            scorecard_is_derived_only: false,
            paper_and_shadow_fills_separate: false,
            live_fill_claimed: false,
            bybit_live_execution_unchanged: false,
            ibkr_contact_performed: false,
            connector_runtime_started: false,
            broker_fill_import_performed: false,
            scorecard_writer_started: false,
            db_apply_performed: false,
            evidence_clock_started: false,
            secret_content_serialized: false,
            live_or_tiny_live_authorized: false,
        }
    }
}

impl StockEtfScorecardInputBundleV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            cash_ledger: BrokerAccountPortfolioCashLedgerV1::accepted_fixture(),
            cost_model: StockEtfCostModelVersionV1::accepted_fixture(),
            benchmark: StockEtfBenchmarkVersionV1::accepted_fixture(),
            shadow_fill_model: StockShadowFillModelV1::accepted_fill_fixture(),
            storage_capacity: StockEtfStorageCapacityV1::accepted_fixture(),
            readonly_probe_result_import_request_contract_id:
                STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID.to_string(),
            readonly_probe_result_import_request_hash: "b".repeat(64),
            market_data_provenance_contract_hash: "8".repeat(64),
            reference_data_sources_contract_hash: "9".repeat(64),
            risk_policy_contract_hash: "a".repeat(64),
            atomic_fact_input_hash: "7".repeat(64),
            source_commit: "535019c9".to_string(),
            scorecard_is_derived_only: true,
            paper_and_shadow_fills_separate: true,
            live_fill_claimed: false,
            bybit_live_execution_unchanged: true,
            ibkr_contact_performed: false,
            connector_runtime_started: false,
            broker_fill_import_performed: false,
            scorecard_writer_started: false,
            db_apply_performed: false,
            evidence_clock_started: false,
            secret_content_serialized: false,
            live_or_tiny_live_authorized: false,
        }
    }

    pub fn validate(&self) -> StockEtfScorecardInputVerdict<StockEtfScorecardInputBlocker> {
        use StockEtfScorecardInputBlocker as Blocker;
        let mut blockers = Vec::new();
        if !self.cash_ledger.validate().accepted {
            blockers.push(Blocker::CashLedgerRejected);
        }
        if !self.cost_model.validate().accepted {
            blockers.push(Blocker::CostModelRejected);
        }
        if !self.benchmark.validate().accepted {
            blockers.push(Blocker::BenchmarkRejected);
        }
        if !self.shadow_fill_model.validate().accepted {
            blockers.push(Blocker::ShadowFillModelRejected);
        }
        if !self.storage_capacity.validate().accepted {
            blockers.push(Blocker::StorageCapacityRejected);
        }
        if self.readonly_probe_result_import_request_contract_id
            != STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID
        {
            blockers.push(Blocker::ReadonlyProbeResultImportRequestContractIdMismatch);
        }
        if !is_sha256_hex(&self.readonly_probe_result_import_request_hash) {
            blockers.push(Blocker::ReadonlyProbeResultImportRequestHashInvalid);
        }
        if !is_sha256_hex(&self.market_data_provenance_contract_hash) {
            blockers.push(Blocker::MarketDataProvenanceContractHashInvalid);
        }
        if !is_sha256_hex(&self.reference_data_sources_contract_hash) {
            blockers.push(Blocker::ReferenceDataSourcesContractHashInvalid);
        }
        if !is_sha256_hex(&self.risk_policy_contract_hash) {
            blockers.push(Blocker::RiskPolicyContractHashInvalid);
        }
        if !is_sha256_hex(&self.atomic_fact_input_hash) {
            blockers.push(Blocker::AtomicFactInputHashInvalid);
        }
        if self.source_commit.trim().is_empty() {
            blockers.push(Blocker::SourceCommitMissing);
        }
        if !self.scorecard_is_derived_only {
            blockers.push(Blocker::ScorecardNotDerivedOnly);
        }
        if !self.paper_and_shadow_fills_separate {
            blockers.push(Blocker::PaperShadowFillSeparationMissing);
        }
        if self.live_fill_claimed {
            blockers.push(Blocker::LiveFillClaimed);
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
        if self.broker_fill_import_performed {
            blockers.push(Blocker::BrokerFillImportPerformed);
        }
        if self.scorecard_writer_started {
            blockers.push(Blocker::ScorecardWriterStarted);
        }
        if self.db_apply_performed {
            blockers.push(Blocker::DbApplyPerformed);
        }
        if self.evidence_clock_started {
            blockers.push(Blocker::EvidenceClockStarted);
        }
        if self.secret_content_serialized {
            blockers.push(Blocker::SecretContentSerialized);
        }
        if self.live_or_tiny_live_authorized {
            blockers.push(Blocker::LiveOrTinyLiveAuthorized);
        }
        StockEtfScorecardInputVerdict::new(blockers)
    }
}
