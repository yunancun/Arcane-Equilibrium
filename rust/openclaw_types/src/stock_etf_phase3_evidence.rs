//! Stock/ETF Phase 3 data provenance, DQ, and evidence-clock contracts.
//!
//! These types validate source evidence shape only. They do not ingest market
//! data, start the evidence clock, contact IBKR, or write scorecard rows.

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_artifact::is_sha256_hex;
use crate::stock_etf_lane::{AssetLane, Broker, BrokerEnvironment};
use crate::stock_etf_pit_universe::STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID;
use crate::stock_etf_reference_data_sources::STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID;
use crate::stock_etf_scorecard_inputs::STOCK_ETF_STORAGE_CAPACITY_CONTRACT_ID;

pub const STOCK_ETF_COLLECTOR_RUN_CONTRACT_ID: &str = "stock_etf_collector_run_v1";
pub const STOCK_ETF_DQ_MANIFEST_CONTRACT_ID: &str = "stock_etf_dq_manifest_v1";
pub const STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID: &str = "stock_etf_evidence_clock_v1";
pub const STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID: &str = "stock_market_data_provenance_v1";
pub const STOCK_ETF_COLLECTOR_MIN_GREEN_TRADING_DAYS: u16 = 5;

mod market_data;

pub use market_data::{
    StockEtfAdjustmentMarker, StockEtfFrozenEvidenceInputsV1, StockMarketDataProvenanceV1,
};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfCollectorRunV1 {
    pub contract_id: String,
    pub source_version: u32,
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub environment: BrokerEnvironment,
    pub collector_run_id: String,
    pub trading_day: String,
    pub pit_universe_contract_id: String,
    pub pit_universe_contract_hash: String,
    pub market_data_provenance_contract_id: String,
    pub market_data_provenance_contract_hash: String,
    pub reference_data_sources_contract_id: String,
    pub reference_data_sources_contract_hash: String,
    pub storage_capacity_contract_id: String,
    pub storage_capacity_contract_hash: String,
    pub expected_trading_sessions: u16,
    pub completed_trading_sessions: u16,
    pub gap_report_hash: String,
    pub dq_manifest_hash: String,
    pub replay_manifest_hash: String,
    pub source_artifact_hash: String,
    pub bybit_live_execution_unchanged: bool,
    pub ibkr_contact_performed: bool,
    pub connector_runtime_started: bool,
    pub market_data_ingestion_started: bool,
    pub evidence_writer_started: bool,
    pub scorecard_writer_started: bool,
    pub db_apply_performed: bool,
    pub secret_content_serialized: bool,
    pub live_or_tiny_live_authorized: bool,
}

impl Default for StockEtfCollectorRunV1 {
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            environment: BrokerEnvironment::LiveReservedDenied,
            collector_run_id: String::new(),
            trading_day: String::new(),
            pit_universe_contract_id: String::new(),
            pit_universe_contract_hash: String::new(),
            market_data_provenance_contract_id: String::new(),
            market_data_provenance_contract_hash: String::new(),
            reference_data_sources_contract_id: String::new(),
            reference_data_sources_contract_hash: String::new(),
            storage_capacity_contract_id: String::new(),
            storage_capacity_contract_hash: String::new(),
            expected_trading_sessions: 0,
            completed_trading_sessions: 0,
            gap_report_hash: String::new(),
            dq_manifest_hash: String::new(),
            replay_manifest_hash: String::new(),
            source_artifact_hash: String::new(),
            bybit_live_execution_unchanged: false,
            ibkr_contact_performed: false,
            connector_runtime_started: false,
            market_data_ingestion_started: false,
            evidence_writer_started: false,
            scorecard_writer_started: false,
            db_apply_performed: false,
            secret_content_serialized: false,
            live_or_tiny_live_authorized: false,
        }
    }
}

impl StockEtfCollectorRunV1 {
    pub fn source_fixture() -> Self {
        Self {
            contract_id: STOCK_ETF_COLLECTOR_RUN_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            environment: BrokerEnvironment::Paper,
            collector_run_id: "stock-etf-collector-run-2026-03-01-001".to_string(),
            trading_day: "2026-03-01".to_string(),
            pit_universe_contract_id: STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID.to_string(),
            pit_universe_contract_hash: "8".repeat(64),
            market_data_provenance_contract_id: STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID
                .to_string(),
            market_data_provenance_contract_hash: "9".repeat(64),
            reference_data_sources_contract_id: STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID
                .to_string(),
            reference_data_sources_contract_hash: "a".repeat(64),
            storage_capacity_contract_id: STOCK_ETF_STORAGE_CAPACITY_CONTRACT_ID.to_string(),
            storage_capacity_contract_hash: "b".repeat(64),
            expected_trading_sessions: STOCK_ETF_COLLECTOR_MIN_GREEN_TRADING_DAYS,
            completed_trading_sessions: STOCK_ETF_COLLECTOR_MIN_GREEN_TRADING_DAYS,
            gap_report_hash: "c".repeat(64),
            dq_manifest_hash: "d".repeat(64),
            replay_manifest_hash: "e".repeat(64),
            source_artifact_hash: "f".repeat(64),
            bybit_live_execution_unchanged: true,
            ibkr_contact_performed: false,
            connector_runtime_started: false,
            market_data_ingestion_started: false,
            evidence_writer_started: false,
            scorecard_writer_started: false,
            db_apply_performed: false,
            secret_content_serialized: false,
            live_or_tiny_live_authorized: false,
        }
    }

    pub fn validate(&self) -> StockEtfPhase3Verdict<StockEtfPhase3Blocker> {
        use StockEtfPhase3Blocker as Blocker;

        let mut blockers = Vec::new();
        if self.contract_id != STOCK_ETF_COLLECTOR_RUN_CONTRACT_ID {
            blockers.push(Blocker::CollectorRunContractIdMismatch);
        }
        if self.source_version != 1 {
            blockers.push(Blocker::CollectorRunVersionMismatch);
        }
        if self.asset_lane != AssetLane::StockEtfCash {
            blockers.push(Blocker::CollectorRunWrongAssetLane);
        }
        if self.broker != Broker::Ibkr {
            blockers.push(Blocker::CollectorRunWrongBroker);
        }
        if !matches!(
            self.environment,
            BrokerEnvironment::ReadOnly | BrokerEnvironment::Paper | BrokerEnvironment::Shadow
        ) {
            blockers.push(Blocker::CollectorRunEnvironmentDenied);
        }
        if self.collector_run_id.trim().is_empty() {
            blockers.push(Blocker::CollectorRunIdMissing);
        }
        if self.trading_day.trim().is_empty() {
            blockers.push(Blocker::CollectorTradingDayMissing);
        }
        if self.pit_universe_contract_id != STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID {
            blockers.push(Blocker::CollectorPitUniverseContractMismatch);
        }
        if !is_sha256_hex(&self.pit_universe_contract_hash) {
            blockers.push(Blocker::CollectorPitUniverseHashInvalid);
        }
        if self.market_data_provenance_contract_id != STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID {
            blockers.push(Blocker::CollectorMarketDataProvenanceContractMismatch);
        }
        if !is_sha256_hex(&self.market_data_provenance_contract_hash) {
            blockers.push(Blocker::CollectorMarketDataProvenanceHashInvalid);
        }
        if self.reference_data_sources_contract_id != STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID {
            blockers.push(Blocker::CollectorReferenceDataSourcesContractMismatch);
        }
        if !is_sha256_hex(&self.reference_data_sources_contract_hash) {
            blockers.push(Blocker::CollectorReferenceDataSourcesHashInvalid);
        }
        if self.storage_capacity_contract_id != STOCK_ETF_STORAGE_CAPACITY_CONTRACT_ID {
            blockers.push(Blocker::CollectorStorageCapacityContractMismatch);
        }
        if !is_sha256_hex(&self.storage_capacity_contract_hash) {
            blockers.push(Blocker::CollectorStorageCapacityHashInvalid);
        }
        if self.expected_trading_sessions < STOCK_ETF_COLLECTOR_MIN_GREEN_TRADING_DAYS {
            blockers.push(Blocker::CollectorExpectedSessionsTooSmall);
        }
        if self.completed_trading_sessions < self.expected_trading_sessions {
            blockers.push(Blocker::CollectorCompletedSessionsMissing);
        }
        if !is_sha256_hex(&self.gap_report_hash) {
            blockers.push(Blocker::CollectorGapReportHashInvalid);
        }
        if !is_sha256_hex(&self.dq_manifest_hash) {
            blockers.push(Blocker::CollectorDqManifestHashInvalid);
        }
        if !is_sha256_hex(&self.replay_manifest_hash) {
            blockers.push(Blocker::CollectorReplayManifestHashInvalid);
        }
        if !is_sha256_hex(&self.source_artifact_hash) {
            blockers.push(Blocker::CollectorSourceArtifactHashInvalid);
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
        if self.market_data_ingestion_started {
            blockers.push(Blocker::CollectorMarketDataIngestionStarted);
        }
        if self.evidence_writer_started {
            blockers.push(Blocker::CollectorEvidenceWriterStarted);
        }
        if self.scorecard_writer_started {
            blockers.push(Blocker::ScorecardWriterStarted);
        }
        if self.db_apply_performed {
            blockers.push(Blocker::DbApplyPerformed);
        }
        if self.secret_content_serialized {
            blockers.push(Blocker::SecretContentSerialized);
        }
        if self.live_or_tiny_live_authorized {
            blockers.push(Blocker::LiveOrTinyLiveAuthorized);
        }

        StockEtfPhase3Verdict::new(blockers)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfDailyDqManifestV1 {
    pub contract_id: String,
    pub source_version: u32,
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub environment: BrokerEnvironment,
    pub collector_run_id: String,
    pub market_data_provenance_contract_id: String,
    pub market_data_provenance_contract_hash: String,
    pub source_artifact_hash: String,
    pub bybit_live_execution_unchanged: bool,
    pub ibkr_contact_performed: bool,
    pub connector_runtime_started: bool,
    pub market_data_ingestion_started: bool,
    pub dq_writer_started: bool,
    pub evidence_clock_started: bool,
    pub scorecard_writer_started: bool,
    pub db_apply_performed: bool,
    pub secret_content_serialized: bool,
    pub live_or_tiny_live_authorized: bool,
    pub trading_day: String,
    pub calendar_aware_coverage_bps: u16,
    pub symbol_completeness_bps: u16,
    pub latency_dq_passed: bool,
    pub quarantine_manifest_hash: String,
    pub market_data_provenance_accepted: bool,
    pub scorecard_regeneration_passed: bool,
    pub atomic_fact_input_hash: String,
}

impl Default for StockEtfDailyDqManifestV1 {
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            environment: BrokerEnvironment::LiveReservedDenied,
            collector_run_id: String::new(),
            market_data_provenance_contract_id: String::new(),
            market_data_provenance_contract_hash: String::new(),
            source_artifact_hash: String::new(),
            bybit_live_execution_unchanged: false,
            ibkr_contact_performed: false,
            connector_runtime_started: false,
            market_data_ingestion_started: false,
            dq_writer_started: false,
            evidence_clock_started: false,
            scorecard_writer_started: false,
            db_apply_performed: false,
            secret_content_serialized: false,
            live_or_tiny_live_authorized: false,
            trading_day: String::new(),
            calendar_aware_coverage_bps: 0,
            symbol_completeness_bps: 0,
            latency_dq_passed: false,
            quarantine_manifest_hash: String::new(),
            market_data_provenance_accepted: false,
            scorecard_regeneration_passed: false,
            atomic_fact_input_hash: String::new(),
        }
    }
}

impl StockEtfDailyDqManifestV1 {
    pub fn pass_fixture() -> Self {
        Self {
            contract_id: STOCK_ETF_DQ_MANIFEST_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            environment: BrokerEnvironment::Paper,
            collector_run_id: "stock-etf-collector-run-2026-03-01".to_string(),
            market_data_provenance_contract_id: STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID
                .to_string(),
            market_data_provenance_contract_hash: "6".repeat(64),
            source_artifact_hash: "8".repeat(64),
            bybit_live_execution_unchanged: true,
            ibkr_contact_performed: false,
            connector_runtime_started: false,
            market_data_ingestion_started: false,
            dq_writer_started: false,
            evidence_clock_started: false,
            scorecard_writer_started: false,
            db_apply_performed: false,
            secret_content_serialized: false,
            live_or_tiny_live_authorized: false,
            trading_day: "2026-03-01".to_string(),
            calendar_aware_coverage_bps: 10_000,
            symbol_completeness_bps: 10_000,
            latency_dq_passed: true,
            quarantine_manifest_hash: "3".repeat(64),
            market_data_provenance_accepted: true,
            scorecard_regeneration_passed: true,
            atomic_fact_input_hash: "4".repeat(64),
        }
    }

    pub fn validates_shape(&self) -> StockEtfPhase3Verdict<StockEtfPhase3Blocker> {
        use StockEtfPhase3Blocker as Blocker;

        let mut blockers = Vec::new();
        if self.contract_id != STOCK_ETF_DQ_MANIFEST_CONTRACT_ID {
            blockers.push(Blocker::DqManifestContractIdMismatch);
        }
        if self.source_version != 1 {
            blockers.push(Blocker::DqManifestVersionMismatch);
        }
        if self.asset_lane != AssetLane::StockEtfCash {
            blockers.push(Blocker::DqManifestWrongAssetLane);
        }
        if self.broker != Broker::Ibkr {
            blockers.push(Blocker::DqManifestWrongBroker);
        }
        if !matches!(
            self.environment,
            BrokerEnvironment::ReadOnly | BrokerEnvironment::Paper | BrokerEnvironment::Shadow
        ) {
            blockers.push(Blocker::DqManifestEnvironmentDenied);
        }
        if self.collector_run_id.trim().is_empty() {
            blockers.push(Blocker::DqManifestCollectorRunIdMissing);
        }
        if self.market_data_provenance_contract_id != STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID {
            blockers.push(Blocker::DqManifestMarketDataProvenanceContractMismatch);
        }
        if !is_sha256_hex(&self.market_data_provenance_contract_hash) {
            blockers.push(Blocker::DqManifestMarketDataProvenanceHashInvalid);
        }
        if !is_sha256_hex(&self.source_artifact_hash) {
            blockers.push(Blocker::DqManifestSourceArtifactHashInvalid);
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
        if self.market_data_ingestion_started {
            blockers.push(Blocker::DqManifestMarketDataIngestionStarted);
        }
        if self.dq_writer_started {
            blockers.push(Blocker::DqManifestWriterStarted);
        }
        if self.evidence_clock_started {
            blockers.push(Blocker::DqManifestEvidenceClockStarted);
        }
        if self.scorecard_writer_started {
            blockers.push(Blocker::ScorecardWriterStarted);
        }
        if self.db_apply_performed {
            blockers.push(Blocker::DbApplyPerformed);
        }
        if self.secret_content_serialized {
            blockers.push(Blocker::SecretContentSerialized);
        }
        if self.live_or_tiny_live_authorized {
            blockers.push(Blocker::LiveOrTinyLiveAuthorized);
        }
        if self.trading_day.trim().is_empty() {
            blockers.push(Blocker::TradingDayMissing);
        }
        if self.calendar_aware_coverage_bps > 10_000 || self.symbol_completeness_bps > 10_000 {
            blockers.push(Blocker::CoverageBpsInvalid);
        }
        if !is_sha256_hex(&self.quarantine_manifest_hash) {
            blockers.push(Blocker::QuarantineManifestHashInvalid);
        }
        if !is_sha256_hex(&self.atomic_fact_input_hash) {
            blockers.push(Blocker::AtomicFactInputHashInvalid);
        }

        StockEtfPhase3Verdict::new(blockers)
    }

    pub fn passes_day_quality(&self) -> bool {
        self.validates_shape().accepted
            && self.calendar_aware_coverage_bps == 10_000
            && self.symbol_completeness_bps == 10_000
            && self.latency_dq_passed
            && self.market_data_provenance_accepted
            && self.scorecard_regeneration_passed
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum StockEtfEvidenceClockStatus {
    NotStarted,
    PassDay,
    QuarantinedDay,
    Blocked,
    WindowComplete,
}

impl Default for StockEtfEvidenceClockStatus {
    fn default() -> Self {
        Self::NotStarted
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfEvidenceClockDayV1 {
    pub contract_id: String,
    pub source_version: u32,
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub environment: BrokerEnvironment,
    pub collector_run_contract_id: String,
    pub collector_run_contract_hash: String,
    pub dq_manifest_contract_id: String,
    pub dq_manifest_contract_hash: String,
    pub source_artifact_hash: String,
    pub market_data_provenance_contract_hash: String,
    pub scorecard_input_bundle_hash: String,
    pub bybit_live_execution_unchanged: bool,
    pub checker_contacted_ibkr: bool,
    pub checker_started_connector_runtime: bool,
    pub checker_started_evidence_clock: bool,
    pub checker_wrote_scorecard: bool,
    pub checker_applied_db: bool,
    pub secret_content_serialized: bool,
    pub live_or_tiny_live_authorized: bool,
    pub status: StockEtfEvidenceClockStatus,
    pub ibkr_readonly_paper_connector_green_5d: bool,
    pub shadow_collector_green_5d: bool,
    pub frozen_inputs: StockEtfFrozenEvidenceInputsV1,
    pub dq_manifest: StockEtfDailyDqManifestV1,
}

impl Default for StockEtfEvidenceClockDayV1 {
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            environment: BrokerEnvironment::LiveReservedDenied,
            collector_run_contract_id: String::new(),
            collector_run_contract_hash: String::new(),
            dq_manifest_contract_id: String::new(),
            dq_manifest_contract_hash: String::new(),
            source_artifact_hash: String::new(),
            market_data_provenance_contract_hash: String::new(),
            scorecard_input_bundle_hash: String::new(),
            bybit_live_execution_unchanged: false,
            checker_contacted_ibkr: false,
            checker_started_connector_runtime: false,
            checker_started_evidence_clock: false,
            checker_wrote_scorecard: false,
            checker_applied_db: false,
            secret_content_serialized: false,
            live_or_tiny_live_authorized: false,
            status: StockEtfEvidenceClockStatus::NotStarted,
            ibkr_readonly_paper_connector_green_5d: false,
            shadow_collector_green_5d: false,
            frozen_inputs: StockEtfFrozenEvidenceInputsV1::default(),
            dq_manifest: StockEtfDailyDqManifestV1::default(),
        }
    }
}

impl StockEtfEvidenceClockDayV1 {
    pub fn pass_day_fixture() -> Self {
        Self {
            contract_id: STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            environment: BrokerEnvironment::Paper,
            collector_run_contract_id: STOCK_ETF_COLLECTOR_RUN_CONTRACT_ID.to_string(),
            collector_run_contract_hash: "9".repeat(64),
            dq_manifest_contract_id: STOCK_ETF_DQ_MANIFEST_CONTRACT_ID.to_string(),
            dq_manifest_contract_hash: "4".repeat(64),
            source_artifact_hash: "5".repeat(64),
            market_data_provenance_contract_hash: "6".repeat(64),
            scorecard_input_bundle_hash: "7".repeat(64),
            bybit_live_execution_unchanged: true,
            checker_contacted_ibkr: false,
            checker_started_connector_runtime: false,
            checker_started_evidence_clock: false,
            checker_wrote_scorecard: false,
            checker_applied_db: false,
            secret_content_serialized: false,
            live_or_tiny_live_authorized: false,
            status: StockEtfEvidenceClockStatus::PassDay,
            ibkr_readonly_paper_connector_green_5d: true,
            shadow_collector_green_5d: true,
            frozen_inputs: StockEtfFrozenEvidenceInputsV1::source_fixture(),
            dq_manifest: StockEtfDailyDqManifestV1::pass_fixture(),
        }
    }

    pub fn validate(&self) -> StockEtfPhase3Verdict<StockEtfPhase3Blocker> {
        use StockEtfEvidenceClockStatus as Status;
        use StockEtfPhase3Blocker as Blocker;

        let mut blockers = Vec::new();
        if self.contract_id != STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID {
            blockers.push(Blocker::EvidenceClockContractIdMismatch);
        }
        if self.source_version != 1 {
            blockers.push(Blocker::EvidenceClockVersionMismatch);
        }
        if self.asset_lane != AssetLane::StockEtfCash {
            blockers.push(Blocker::EvidenceClockWrongAssetLane);
        }
        if self.broker != Broker::Ibkr {
            blockers.push(Blocker::EvidenceClockWrongBroker);
        }
        if !matches!(
            self.environment,
            BrokerEnvironment::ReadOnly | BrokerEnvironment::Paper | BrokerEnvironment::Shadow
        ) {
            blockers.push(Blocker::EvidenceClockEnvironmentDenied);
        }
        if self.collector_run_contract_id != STOCK_ETF_COLLECTOR_RUN_CONTRACT_ID {
            blockers.push(Blocker::EvidenceClockCollectorRunContractMismatch);
        }
        if !is_sha256_hex(&self.collector_run_contract_hash) {
            blockers.push(Blocker::EvidenceClockCollectorRunHashInvalid);
        }
        if self.dq_manifest_contract_id != STOCK_ETF_DQ_MANIFEST_CONTRACT_ID {
            blockers.push(Blocker::EvidenceClockDqManifestContractMismatch);
        }
        if !is_sha256_hex(&self.dq_manifest_contract_hash) {
            blockers.push(Blocker::EvidenceClockDqManifestHashInvalid);
        }
        if !is_sha256_hex(&self.source_artifact_hash) {
            blockers.push(Blocker::EvidenceClockSourceArtifactHashInvalid);
        }
        if !is_sha256_hex(&self.market_data_provenance_contract_hash) {
            blockers.push(Blocker::EvidenceClockMarketDataProvenanceHashInvalid);
        }
        if !is_sha256_hex(&self.scorecard_input_bundle_hash) {
            blockers.push(Blocker::EvidenceClockScorecardInputHashInvalid);
        }
        if !self.bybit_live_execution_unchanged {
            blockers.push(Blocker::BybitLiveExecutionNotProtected);
        }
        if self.checker_contacted_ibkr {
            blockers.push(Blocker::IbkrContactPerformed);
        }
        if self.checker_started_connector_runtime {
            blockers.push(Blocker::ConnectorRuntimeStarted);
        }
        if self.checker_started_evidence_clock {
            blockers.push(Blocker::EvidenceClockRuntimeStarted);
        }
        if self.checker_wrote_scorecard {
            blockers.push(Blocker::ScorecardWriterStarted);
        }
        if self.checker_applied_db {
            blockers.push(Blocker::DbApplyPerformed);
        }
        if self.secret_content_serialized {
            blockers.push(Blocker::SecretContentSerialized);
        }
        if self.live_or_tiny_live_authorized {
            blockers.push(Blocker::LiveOrTinyLiveAuthorized);
        }
        if !self.ibkr_readonly_paper_connector_green_5d {
            blockers.push(Blocker::IbkrConnectorNotGreenFiveDays);
        }
        if !self.shadow_collector_green_5d {
            blockers.push(Blocker::ShadowCollectorNotGreenFiveDays);
        }
        if !self.frozen_inputs.validate().accepted {
            blockers.push(Blocker::FrozenInputsRejected);
        }
        if !self.dq_manifest.validates_shape().accepted {
            blockers.push(Blocker::DqManifestShapeRejected);
        }

        match self.status {
            Status::PassDay => {
                if !self.dq_manifest.passes_day_quality() {
                    blockers.push(Blocker::PassDayQualityRejected);
                }
            }
            Status::QuarantinedDay => {
                if self.dq_manifest.passes_day_quality() {
                    blockers.push(Blocker::QuarantinedDayWithoutDqFailure);
                }
            }
            Status::WindowComplete => blockers.push(Blocker::WindowCompleteNotSourceAuthorized),
            Status::NotStarted | Status::Blocked => {}
        }

        StockEtfPhase3Verdict::new(blockers)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfPhase3Verdict<B> {
    pub accepted: bool,
    pub blockers: Vec<B>,
}

impl<B> StockEtfPhase3Verdict<B> {
    fn new(blockers: Vec<B>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfPhase3Blocker {
    CollectorRunContractIdMismatch,
    CollectorRunVersionMismatch,
    CollectorRunWrongAssetLane,
    CollectorRunWrongBroker,
    CollectorRunEnvironmentDenied,
    CollectorRunIdMissing,
    CollectorTradingDayMissing,
    CollectorPitUniverseContractMismatch,
    CollectorPitUniverseHashInvalid,
    CollectorMarketDataProvenanceContractMismatch,
    CollectorMarketDataProvenanceHashInvalid,
    CollectorReferenceDataSourcesContractMismatch,
    CollectorReferenceDataSourcesHashInvalid,
    CollectorStorageCapacityContractMismatch,
    CollectorStorageCapacityHashInvalid,
    CollectorExpectedSessionsTooSmall,
    CollectorCompletedSessionsMissing,
    CollectorGapReportHashInvalid,
    CollectorDqManifestHashInvalid,
    CollectorReplayManifestHashInvalid,
    CollectorSourceArtifactHashInvalid,
    CollectorMarketDataIngestionStarted,
    CollectorEvidenceWriterStarted,
    MarketDataProvenanceContractIdMismatch,
    MarketDataProvenanceVersionMismatch,
    MarketDataProvenanceWrongAssetLane,
    MarketDataProvenanceWrongBroker,
    MarketDataProvenanceEnvironmentDenied,
    SourceMissing,
    EntitlementTierMissing,
    RawPayloadHashInvalid,
    MarketDataTimestampMissing,
    AdjustmentMarkerUnknown,
    CorporateActionVersionHashInvalid,
    SymbolMissing,
    InstrumentIdentityHashInvalid,
    CalendarSessionMissing,
    SourceArtifactHashInvalid,
    BybitLiveExecutionNotProtected,
    IbkrContactPerformed,
    ConnectorRuntimeStarted,
    SecretContentSerialized,
    LiveOrTinyLiveAuthorized,
    UniverseHashInvalid,
    BenchmarkHashInvalid,
    CostModelHashInvalid,
    StrategyHypothesisHashInvalid,
    ReferenceDataSourcesHashInvalid,
    CorporateActionFxFeeAsOfMissing,
    DivergenceThresholdHashInvalid,
    GuiEvidenceViewMissing,
    ScorecardRegenerationMissing,
    DqManifestContractIdMismatch,
    DqManifestVersionMismatch,
    DqManifestWrongAssetLane,
    DqManifestWrongBroker,
    DqManifestEnvironmentDenied,
    DqManifestCollectorRunIdMissing,
    DqManifestMarketDataProvenanceContractMismatch,
    DqManifestMarketDataProvenanceHashInvalid,
    DqManifestSourceArtifactHashInvalid,
    DqManifestMarketDataIngestionStarted,
    DqManifestWriterStarted,
    DqManifestEvidenceClockStarted,
    TradingDayMissing,
    CoverageBpsInvalid,
    QuarantineManifestHashInvalid,
    AtomicFactInputHashInvalid,
    IbkrConnectorNotGreenFiveDays,
    ShadowCollectorNotGreenFiveDays,
    EvidenceClockContractIdMismatch,
    EvidenceClockVersionMismatch,
    EvidenceClockWrongAssetLane,
    EvidenceClockWrongBroker,
    EvidenceClockEnvironmentDenied,
    EvidenceClockCollectorRunContractMismatch,
    EvidenceClockCollectorRunHashInvalid,
    EvidenceClockDqManifestContractMismatch,
    EvidenceClockDqManifestHashInvalid,
    EvidenceClockSourceArtifactHashInvalid,
    EvidenceClockMarketDataProvenanceHashInvalid,
    EvidenceClockScorecardInputHashInvalid,
    EvidenceClockRuntimeStarted,
    ScorecardWriterStarted,
    DbApplyPerformed,
    FrozenInputsRejected,
    DqManifestShapeRejected,
    PassDayQualityRejected,
    QuarantinedDayWithoutDqFailure,
    WindowCompleteNotSourceAuthorized,
}
