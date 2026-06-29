//! Stock/ETF Phase 3 data provenance, DQ, and evidence-clock contracts.
//!
//! These types validate source evidence shape only. They do not ingest market
//! data, start the evidence clock, contact IBKR, or write scorecard rows.

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_artifact::is_sha256_hex;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfAdjustmentMarker {
    Adjusted,
    Unadjusted,
    Unknown,
}

impl Default for StockEtfAdjustmentMarker {
    fn default() -> Self {
        Self::Unknown
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockMarketDataProvenanceV1 {
    pub source_vendor_or_broker: String,
    pub entitlement_tier: String,
    pub raw_payload_hash: String,
    pub received_at_ms: u64,
    pub exchange_time_ms: u64,
    pub adjustment_marker: StockEtfAdjustmentMarker,
    pub corporate_action_adjustment_version_hash: String,
    pub symbol: String,
    pub instrument_identity_hash: String,
    pub calendar_session_id: String,
}

impl Default for StockMarketDataProvenanceV1 {
    fn default() -> Self {
        Self {
            source_vendor_or_broker: String::new(),
            entitlement_tier: String::new(),
            raw_payload_hash: String::new(),
            received_at_ms: 0,
            exchange_time_ms: 0,
            adjustment_marker: StockEtfAdjustmentMarker::Unknown,
            corporate_action_adjustment_version_hash: String::new(),
            symbol: String::new(),
            instrument_identity_hash: String::new(),
            calendar_session_id: String::new(),
        }
    }
}

impl StockMarketDataProvenanceV1 {
    pub fn source_fixture() -> Self {
        Self {
            source_vendor_or_broker: "ibkr_paper_market_data".to_string(),
            entitlement_tier: "paper_delayed_or_snapshot_fixture".to_string(),
            raw_payload_hash: "a".repeat(64),
            received_at_ms: 1_772_233_000_000,
            exchange_time_ms: 1_772_232_999_000,
            adjustment_marker: StockEtfAdjustmentMarker::Adjusted,
            corporate_action_adjustment_version_hash: "b".repeat(64),
            symbol: "SPY".to_string(),
            instrument_identity_hash: "c".repeat(64),
            calendar_session_id: "XNYS-2026-03-01-regular".to_string(),
        }
    }

    pub fn validate(&self) -> StockEtfPhase3Verdict<StockEtfPhase3Blocker> {
        use StockEtfPhase3Blocker as Blocker;

        let mut blockers = Vec::new();
        if self.source_vendor_or_broker.trim().is_empty() {
            blockers.push(Blocker::SourceMissing);
        }
        if self.entitlement_tier.trim().is_empty() {
            blockers.push(Blocker::EntitlementTierMissing);
        }
        if !is_sha256_hex(&self.raw_payload_hash) {
            blockers.push(Blocker::RawPayloadHashInvalid);
        }
        if self.received_at_ms == 0 || self.exchange_time_ms == 0 {
            blockers.push(Blocker::MarketDataTimestampMissing);
        }
        if self.adjustment_marker == StockEtfAdjustmentMarker::Unknown {
            blockers.push(Blocker::AdjustmentMarkerUnknown);
        }
        if !is_sha256_hex(&self.corporate_action_adjustment_version_hash) {
            blockers.push(Blocker::CorporateActionVersionHashInvalid);
        }
        if self.symbol.trim().is_empty() {
            blockers.push(Blocker::SymbolMissing);
        }
        if !is_sha256_hex(&self.instrument_identity_hash) {
            blockers.push(Blocker::InstrumentIdentityHashInvalid);
        }
        if self.calendar_session_id.trim().is_empty() {
            blockers.push(Blocker::CalendarSessionMissing);
        }

        StockEtfPhase3Verdict::new(blockers)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfFrozenEvidenceInputsV1 {
    pub universe_hash: String,
    pub benchmark_hash: String,
    pub cost_model_hash: String,
    pub strategy_hypothesis_hash: String,
    pub corporate_action_fx_fee_asof_ms: u64,
    pub paper_shadow_divergence_threshold_hash: String,
    pub gui_evidence_view_available: bool,
    pub daily_scorecard_regeneration_passed: bool,
}

impl Default for StockEtfFrozenEvidenceInputsV1 {
    fn default() -> Self {
        Self {
            universe_hash: String::new(),
            benchmark_hash: String::new(),
            cost_model_hash: String::new(),
            strategy_hypothesis_hash: String::new(),
            corporate_action_fx_fee_asof_ms: 0,
            paper_shadow_divergence_threshold_hash: String::new(),
            gui_evidence_view_available: false,
            daily_scorecard_regeneration_passed: false,
        }
    }
}

impl StockEtfFrozenEvidenceInputsV1 {
    pub fn source_fixture() -> Self {
        Self {
            universe_hash: "d".repeat(64),
            benchmark_hash: "e".repeat(64),
            cost_model_hash: "f".repeat(64),
            strategy_hypothesis_hash: "1".repeat(64),
            corporate_action_fx_fee_asof_ms: 1_772_233_000_000,
            paper_shadow_divergence_threshold_hash: "2".repeat(64),
            gui_evidence_view_available: true,
            daily_scorecard_regeneration_passed: true,
        }
    }

    pub fn validate(&self) -> StockEtfPhase3Verdict<StockEtfPhase3Blocker> {
        use StockEtfPhase3Blocker as Blocker;

        let mut blockers = Vec::new();
        if !is_sha256_hex(&self.universe_hash) {
            blockers.push(Blocker::UniverseHashInvalid);
        }
        if !is_sha256_hex(&self.benchmark_hash) {
            blockers.push(Blocker::BenchmarkHashInvalid);
        }
        if !is_sha256_hex(&self.cost_model_hash) {
            blockers.push(Blocker::CostModelHashInvalid);
        }
        if !is_sha256_hex(&self.strategy_hypothesis_hash) {
            blockers.push(Blocker::StrategyHypothesisHashInvalid);
        }
        if self.corporate_action_fx_fee_asof_ms == 0 {
            blockers.push(Blocker::CorporateActionFxFeeAsOfMissing);
        }
        if !is_sha256_hex(&self.paper_shadow_divergence_threshold_hash) {
            blockers.push(Blocker::DivergenceThresholdHashInvalid);
        }
        if !self.gui_evidence_view_available {
            blockers.push(Blocker::GuiEvidenceViewMissing);
        }
        if !self.daily_scorecard_regeneration_passed {
            blockers.push(Blocker::ScorecardRegenerationMissing);
        }

        StockEtfPhase3Verdict::new(blockers)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfDailyDqManifestV1 {
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
    pub status: StockEtfEvidenceClockStatus,
    pub ibkr_readonly_paper_connector_green_5d: bool,
    pub shadow_collector_green_5d: bool,
    pub frozen_inputs: StockEtfFrozenEvidenceInputsV1,
    pub dq_manifest: StockEtfDailyDqManifestV1,
}

impl Default for StockEtfEvidenceClockDayV1 {
    fn default() -> Self {
        Self {
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
    SourceMissing,
    EntitlementTierMissing,
    RawPayloadHashInvalid,
    MarketDataTimestampMissing,
    AdjustmentMarkerUnknown,
    CorporateActionVersionHashInvalid,
    SymbolMissing,
    InstrumentIdentityHashInvalid,
    CalendarSessionMissing,
    UniverseHashInvalid,
    BenchmarkHashInvalid,
    CostModelHashInvalid,
    StrategyHypothesisHashInvalid,
    CorporateActionFxFeeAsOfMissing,
    DivergenceThresholdHashInvalid,
    GuiEvidenceViewMissing,
    ScorecardRegenerationMissing,
    TradingDayMissing,
    CoverageBpsInvalid,
    QuarantineManifestHashInvalid,
    AtomicFactInputHashInvalid,
    IbkrConnectorNotGreenFiveDays,
    ShadowCollectorNotGreenFiveDays,
    FrozenInputsRejected,
    DqManifestShapeRejected,
    PassDayQualityRejected,
    QuarantinedDayWithoutDqFailure,
    WindowCompleteNotSourceAuthorized,
}
