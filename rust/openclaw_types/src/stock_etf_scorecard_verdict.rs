//! Stock/ETF scorecard verdict contract for ADR-0048.
//!
//! This source-only validator pins the statistical verdict shape that sits
//! between scorecard inputs and any future tiny-live ADR discussion. It does not
//! contact IBKR, start connectors, write scorecards, apply migrations, read
//! secrets, authorize tiny-live/live, or lower any Bybit gate.

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_artifact::is_sha256_hex;
use crate::stock_etf_lane::{AssetLane, Broker, BrokerEnvironment};

pub const STOCK_ETF_SCORECARD_VERDICT_CONTRACT_ID: &str = "stock_etf_scorecard_verdict_v1";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfScorecardVerdictLabel {
    EngineeringReady,
    ResearchPromising,
    ProfitabilityFeasible,
    InsufficientEvidence,
    ExecutionModelInvalid,
    Kill,
}

impl Default for StockEtfScorecardVerdictLabel {
    fn default() -> Self {
        Self::InsufficientEvidence
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfScorecardVerdictV1 {
    pub contract_id: String,
    pub source_version: u32,
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub environment: BrokerEnvironment,
    pub scorecard_input_bundle_hash: String,
    pub evidence_clock_manifest_hash: String,
    pub dq_manifest_hash: String,
    pub formula_appendix_hash: String,
    pub statistical_preregistration_hash: String,
    pub benchmark_version_hash: String,
    pub cost_model_version_hash: String,
    pub strategy_hypothesis_hash: String,
    pub reference_data_sources_hash: String,
    pub paper_shadow_reconciliation_hash: String,
    pub scorecard_manifest_hash: String,
    pub verdict_rationale_hash: String,
    pub paper_shadow_window_trading_days: u32,
    pub min_window_trading_days: u32,
    pub independent_observation_count: u32,
    pub min_independent_observation_count: u32,
    pub gross_pnl_minor_units: i64,
    pub commission_minor_units: u64,
    pub spread_slippage_minor_units: u64,
    pub fx_drag_minor_units: u64,
    pub tax_drag_minor_units: u64,
    pub net_pnl_minor_units: i64,
    pub benchmark_excess_lcb_bps: i32,
    pub conservative_cost_stress_lcb_bps: i32,
    pub paper_shadow_divergence_bps: u32,
    pub max_paper_shadow_divergence_bps: u32,
    pub information_ratio_bps: i32,
    pub tracking_error_bps: u32,
    pub cost_edge_ratio_bps: i32,
    pub psr_bps: u16,
    pub min_psr_bps: u16,
    pub dsr_bps: u16,
    pub min_dsr_bps: u16,
    pub concentration_label_passed: bool,
    pub regime_label_passed: bool,
    pub breadth_label_passed: bool,
    pub freshness_label_passed: bool,
    pub survivorship_label_passed: bool,
    pub execution_realism_label_passed: bool,
    pub qc_review_hash: String,
    pub mit_review_hash: String,
    pub qa_review_hash: String,
    pub qc_review_passed: bool,
    pub mit_review_passed: bool,
    pub qa_review_passed: bool,
    pub verdict_label: StockEtfScorecardVerdictLabel,
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
    pub sealed: bool,
}

impl Default for StockEtfScorecardVerdictV1 {
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            environment: BrokerEnvironment::LiveReservedDenied,
            scorecard_input_bundle_hash: String::new(),
            evidence_clock_manifest_hash: String::new(),
            dq_manifest_hash: String::new(),
            formula_appendix_hash: String::new(),
            statistical_preregistration_hash: String::new(),
            benchmark_version_hash: String::new(),
            cost_model_version_hash: String::new(),
            strategy_hypothesis_hash: String::new(),
            reference_data_sources_hash: String::new(),
            paper_shadow_reconciliation_hash: String::new(),
            scorecard_manifest_hash: String::new(),
            verdict_rationale_hash: String::new(),
            paper_shadow_window_trading_days: 0,
            min_window_trading_days: 0,
            independent_observation_count: 0,
            min_independent_observation_count: 0,
            gross_pnl_minor_units: 0,
            commission_minor_units: 0,
            spread_slippage_minor_units: 0,
            fx_drag_minor_units: 0,
            tax_drag_minor_units: 0,
            net_pnl_minor_units: 0,
            benchmark_excess_lcb_bps: 0,
            conservative_cost_stress_lcb_bps: 0,
            paper_shadow_divergence_bps: 0,
            max_paper_shadow_divergence_bps: 0,
            information_ratio_bps: 0,
            tracking_error_bps: 0,
            cost_edge_ratio_bps: 0,
            psr_bps: 0,
            min_psr_bps: 0,
            dsr_bps: 0,
            min_dsr_bps: 0,
            concentration_label_passed: false,
            regime_label_passed: false,
            breadth_label_passed: false,
            freshness_label_passed: false,
            survivorship_label_passed: false,
            execution_realism_label_passed: false,
            qc_review_hash: String::new(),
            mit_review_hash: String::new(),
            qa_review_hash: String::new(),
            qc_review_passed: false,
            mit_review_passed: false,
            qa_review_passed: false,
            verdict_label: StockEtfScorecardVerdictLabel::InsufficientEvidence,
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
            sealed: false,
        }
    }
}

impl StockEtfScorecardVerdictV1 {
    pub fn profitability_feasible_fixture() -> Self {
        Self {
            contract_id: STOCK_ETF_SCORECARD_VERDICT_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            environment: BrokerEnvironment::Paper,
            scorecard_input_bundle_hash: "1".repeat(64),
            evidence_clock_manifest_hash: "2".repeat(64),
            dq_manifest_hash: "3".repeat(64),
            formula_appendix_hash: "4".repeat(64),
            statistical_preregistration_hash: "5".repeat(64),
            benchmark_version_hash: "6".repeat(64),
            cost_model_version_hash: "7".repeat(64),
            strategy_hypothesis_hash: "8".repeat(64),
            reference_data_sources_hash: "9".repeat(64),
            paper_shadow_reconciliation_hash: "a".repeat(64),
            scorecard_manifest_hash: "b".repeat(64),
            verdict_rationale_hash: "c".repeat(64),
            paper_shadow_window_trading_days: 42,
            min_window_trading_days: 30,
            independent_observation_count: 85,
            min_independent_observation_count: 60,
            gross_pnl_minor_units: 145_000,
            commission_minor_units: 5_000,
            spread_slippage_minor_units: 18_000,
            fx_drag_minor_units: 2_000,
            tax_drag_minor_units: 1_000,
            net_pnl_minor_units: 119_000,
            benchmark_excess_lcb_bps: 12,
            conservative_cost_stress_lcb_bps: 5,
            paper_shadow_divergence_bps: 35,
            max_paper_shadow_divergence_bps: 100,
            information_ratio_bps: 120,
            tracking_error_bps: 240,
            cost_edge_ratio_bps: 350,
            psr_bps: 9_700,
            min_psr_bps: 9_500,
            dsr_bps: 9_250,
            min_dsr_bps: 9_000,
            concentration_label_passed: true,
            regime_label_passed: true,
            breadth_label_passed: true,
            freshness_label_passed: true,
            survivorship_label_passed: true,
            execution_realism_label_passed: true,
            qc_review_hash: "d".repeat(64),
            mit_review_hash: "e".repeat(64),
            qa_review_hash: "f".repeat(64),
            qc_review_passed: true,
            mit_review_passed: true,
            qa_review_passed: true,
            verdict_label: StockEtfScorecardVerdictLabel::ProfitabilityFeasible,
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
            sealed: true,
        }
    }

    pub fn validate(&self) -> StockEtfScorecardVerdict<StockEtfScorecardVerdictBlocker> {
        use StockEtfScorecardVerdictBlocker as Blocker;
        use StockEtfScorecardVerdictLabel as Label;

        let mut blockers = Vec::new();
        validate_contract_identity(self, &mut blockers);
        validate_hashes(self, &mut blockers);
        validate_threshold_shapes(self, &mut blockers);
        validate_reviews_and_authority(self, &mut blockers);

        match self.verdict_label {
            Label::ProfitabilityFeasible => {
                validate_window_thresholds(self, &mut blockers);
                validate_paper_shadow_divergence(self, &mut blockers);
                validate_positive_profitability(self, &mut blockers);
                validate_probability_thresholds(self, &mut blockers);
                validate_quality_labels(self, &mut blockers);
            }
            Label::ResearchPromising => {
                validate_window_thresholds(self, &mut blockers);
                validate_paper_shadow_divergence(self, &mut blockers);
                validate_probability_thresholds(self, &mut blockers);
                validate_quality_labels(self, &mut blockers);
            }
            Label::EngineeringReady => {
                validate_window_thresholds(self, &mut blockers);
                validate_paper_shadow_divergence(self, &mut blockers);
                validate_quality_labels(self, &mut blockers);
            }
            Label::ExecutionModelInvalid => {
                if self.execution_realism_label_passed
                    && self.max_paper_shadow_divergence_bps > 0
                    && self.paper_shadow_divergence_bps <= self.max_paper_shadow_divergence_bps
                {
                    blockers.push(Blocker::ExecutionInvalidVerdictWithoutExecutionFailure);
                }
            }
            Label::InsufficientEvidence | Label::Kill => {}
        }

        StockEtfScorecardVerdict::new(blockers)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfScorecardVerdict<B> {
    pub accepted: bool,
    pub blockers: Vec<B>,
}

impl<B> StockEtfScorecardVerdict<B> {
    fn new(blockers: Vec<B>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfScorecardVerdictBlocker {
    ContractIdMissing,
    ContractIdMismatch,
    SourceVersionMismatch,
    WrongAssetLane,
    WrongBroker,
    EnvironmentDenied,
    ScorecardInputBundleHashInvalid,
    EvidenceClockManifestHashInvalid,
    DqManifestHashInvalid,
    FormulaAppendixHashInvalid,
    StatisticalPreregistrationHashInvalid,
    BenchmarkVersionHashInvalid,
    CostModelVersionHashInvalid,
    StrategyHypothesisHashInvalid,
    ReferenceDataSourcesHashInvalid,
    PaperShadowReconciliationHashInvalid,
    ScorecardManifestHashInvalid,
    VerdictRationaleHashInvalid,
    WindowThresholdMissing,
    WindowThresholdNotMet,
    MinIndependentObservationMissing,
    IndependentObservationThresholdNotMet,
    DivergenceThresholdMissing,
    PaperShadowDivergenceExceeded,
    ProbabilityMetricOutOfRange,
    PsrThresholdMissing,
    DsrThresholdMissing,
    PsrThresholdNotMet,
    DsrThresholdNotMet,
    BenchmarkAfterCostLcbNotPositive,
    CostStressLcbNotPositive,
    ConcentrationLabelRejected,
    RegimeLabelRejected,
    BreadthLabelRejected,
    FreshnessLabelRejected,
    SurvivorshipLabelRejected,
    ExecutionRealismLabelRejected,
    QcReviewHashInvalid,
    MitReviewHashInvalid,
    QaReviewHashInvalid,
    QcReviewMissing,
    MitReviewMissing,
    QaReviewMissing,
    ScorecardNotDerivedOnly,
    PaperShadowFillSeparationMissing,
    LiveFillClaimed,
    BybitLiveExecutionNotProtected,
    IbkrContactPerformed,
    ConnectorRuntimeStarted,
    BrokerFillImportPerformed,
    ScorecardWriterStarted,
    DbApplyPerformed,
    EvidenceClockStarted,
    SecretContentSerialized,
    LiveOrTinyLiveAuthorized,
    NotSealed,
    ExecutionInvalidVerdictWithoutExecutionFailure,
}

fn validate_contract_identity(
    candidate: &StockEtfScorecardVerdictV1,
    blockers: &mut Vec<StockEtfScorecardVerdictBlocker>,
) {
    use StockEtfScorecardVerdictBlocker as Blocker;

    if candidate.contract_id.trim().is_empty() {
        blockers.push(Blocker::ContractIdMissing);
    } else if candidate.contract_id != STOCK_ETF_SCORECARD_VERDICT_CONTRACT_ID {
        blockers.push(Blocker::ContractIdMismatch);
    }
    if candidate.source_version != 1 {
        blockers.push(Blocker::SourceVersionMismatch);
    }
    if candidate.asset_lane != AssetLane::StockEtfCash {
        blockers.push(Blocker::WrongAssetLane);
    }
    if candidate.broker != Broker::Ibkr {
        blockers.push(Blocker::WrongBroker);
    }
    if !matches!(
        candidate.environment,
        BrokerEnvironment::ReadOnly | BrokerEnvironment::Paper
    ) {
        blockers.push(Blocker::EnvironmentDenied);
    }
}

fn validate_hashes(
    candidate: &StockEtfScorecardVerdictV1,
    blockers: &mut Vec<StockEtfScorecardVerdictBlocker>,
) {
    use StockEtfScorecardVerdictBlocker as Blocker;

    if !is_sha256_hex(&candidate.scorecard_input_bundle_hash) {
        blockers.push(Blocker::ScorecardInputBundleHashInvalid);
    }
    if !is_sha256_hex(&candidate.evidence_clock_manifest_hash) {
        blockers.push(Blocker::EvidenceClockManifestHashInvalid);
    }
    if !is_sha256_hex(&candidate.dq_manifest_hash) {
        blockers.push(Blocker::DqManifestHashInvalid);
    }
    if !is_sha256_hex(&candidate.formula_appendix_hash) {
        blockers.push(Blocker::FormulaAppendixHashInvalid);
    }
    if !is_sha256_hex(&candidate.statistical_preregistration_hash) {
        blockers.push(Blocker::StatisticalPreregistrationHashInvalid);
    }
    if !is_sha256_hex(&candidate.benchmark_version_hash) {
        blockers.push(Blocker::BenchmarkVersionHashInvalid);
    }
    if !is_sha256_hex(&candidate.cost_model_version_hash) {
        blockers.push(Blocker::CostModelVersionHashInvalid);
    }
    if !is_sha256_hex(&candidate.strategy_hypothesis_hash) {
        blockers.push(Blocker::StrategyHypothesisHashInvalid);
    }
    if !is_sha256_hex(&candidate.reference_data_sources_hash) {
        blockers.push(Blocker::ReferenceDataSourcesHashInvalid);
    }
    if !is_sha256_hex(&candidate.paper_shadow_reconciliation_hash) {
        blockers.push(Blocker::PaperShadowReconciliationHashInvalid);
    }
    if !is_sha256_hex(&candidate.scorecard_manifest_hash) {
        blockers.push(Blocker::ScorecardManifestHashInvalid);
    }
    if !is_sha256_hex(&candidate.verdict_rationale_hash) {
        blockers.push(Blocker::VerdictRationaleHashInvalid);
    }
}

fn validate_threshold_shapes(
    candidate: &StockEtfScorecardVerdictV1,
    blockers: &mut Vec<StockEtfScorecardVerdictBlocker>,
) {
    use StockEtfScorecardVerdictBlocker as Blocker;

    if candidate.min_window_trading_days == 0 {
        blockers.push(Blocker::WindowThresholdMissing);
    }
    if candidate.min_independent_observation_count == 0 {
        blockers.push(Blocker::MinIndependentObservationMissing);
    }
    if candidate.max_paper_shadow_divergence_bps == 0 {
        blockers.push(Blocker::DivergenceThresholdMissing);
    }
    if candidate.psr_bps > 10_000 || candidate.dsr_bps > 10_000 {
        blockers.push(Blocker::ProbabilityMetricOutOfRange);
    }
    if candidate.min_psr_bps == 0 || candidate.min_psr_bps > 10_000 {
        blockers.push(Blocker::PsrThresholdMissing);
    }
    if candidate.min_dsr_bps == 0 || candidate.min_dsr_bps > 10_000 {
        blockers.push(Blocker::DsrThresholdMissing);
    }
}

fn validate_window_thresholds(
    candidate: &StockEtfScorecardVerdictV1,
    blockers: &mut Vec<StockEtfScorecardVerdictBlocker>,
) {
    use StockEtfScorecardVerdictBlocker as Blocker;

    if candidate.min_window_trading_days > 0
        && candidate.paper_shadow_window_trading_days < candidate.min_window_trading_days
    {
        blockers.push(Blocker::WindowThresholdNotMet);
    }
    if candidate.min_independent_observation_count > 0
        && candidate.independent_observation_count < candidate.min_independent_observation_count
    {
        blockers.push(Blocker::IndependentObservationThresholdNotMet);
    }
}

fn validate_paper_shadow_divergence(
    candidate: &StockEtfScorecardVerdictV1,
    blockers: &mut Vec<StockEtfScorecardVerdictBlocker>,
) {
    use StockEtfScorecardVerdictBlocker as Blocker;

    if candidate.max_paper_shadow_divergence_bps > 0
        && candidate.paper_shadow_divergence_bps > candidate.max_paper_shadow_divergence_bps
    {
        blockers.push(Blocker::PaperShadowDivergenceExceeded);
    }
}

fn validate_positive_profitability(
    candidate: &StockEtfScorecardVerdictV1,
    blockers: &mut Vec<StockEtfScorecardVerdictBlocker>,
) {
    use StockEtfScorecardVerdictBlocker as Blocker;

    if candidate.benchmark_excess_lcb_bps <= 0 {
        blockers.push(Blocker::BenchmarkAfterCostLcbNotPositive);
    }
    if candidate.conservative_cost_stress_lcb_bps <= 0 {
        blockers.push(Blocker::CostStressLcbNotPositive);
    }
}

fn validate_probability_thresholds(
    candidate: &StockEtfScorecardVerdictV1,
    blockers: &mut Vec<StockEtfScorecardVerdictBlocker>,
) {
    use StockEtfScorecardVerdictBlocker as Blocker;

    if candidate.min_psr_bps > 0 && candidate.psr_bps < candidate.min_psr_bps {
        blockers.push(Blocker::PsrThresholdNotMet);
    }
    if candidate.min_dsr_bps > 0 && candidate.dsr_bps < candidate.min_dsr_bps {
        blockers.push(Blocker::DsrThresholdNotMet);
    }
}

fn validate_quality_labels(
    candidate: &StockEtfScorecardVerdictV1,
    blockers: &mut Vec<StockEtfScorecardVerdictBlocker>,
) {
    use StockEtfScorecardVerdictBlocker as Blocker;

    if !candidate.concentration_label_passed {
        blockers.push(Blocker::ConcentrationLabelRejected);
    }
    if !candidate.regime_label_passed {
        blockers.push(Blocker::RegimeLabelRejected);
    }
    if !candidate.breadth_label_passed {
        blockers.push(Blocker::BreadthLabelRejected);
    }
    if !candidate.freshness_label_passed {
        blockers.push(Blocker::FreshnessLabelRejected);
    }
    if !candidate.survivorship_label_passed {
        blockers.push(Blocker::SurvivorshipLabelRejected);
    }
    if !candidate.execution_realism_label_passed {
        blockers.push(Blocker::ExecutionRealismLabelRejected);
    }
}

fn validate_reviews_and_authority(
    candidate: &StockEtfScorecardVerdictV1,
    blockers: &mut Vec<StockEtfScorecardVerdictBlocker>,
) {
    use StockEtfScorecardVerdictBlocker as Blocker;

    if !is_sha256_hex(&candidate.qc_review_hash) {
        blockers.push(Blocker::QcReviewHashInvalid);
    }
    if !is_sha256_hex(&candidate.mit_review_hash) {
        blockers.push(Blocker::MitReviewHashInvalid);
    }
    if !is_sha256_hex(&candidate.qa_review_hash) {
        blockers.push(Blocker::QaReviewHashInvalid);
    }
    if !candidate.qc_review_passed {
        blockers.push(Blocker::QcReviewMissing);
    }
    if !candidate.mit_review_passed {
        blockers.push(Blocker::MitReviewMissing);
    }
    if !candidate.qa_review_passed {
        blockers.push(Blocker::QaReviewMissing);
    }
    if !candidate.scorecard_is_derived_only {
        blockers.push(Blocker::ScorecardNotDerivedOnly);
    }
    if !candidate.paper_and_shadow_fills_separate {
        blockers.push(Blocker::PaperShadowFillSeparationMissing);
    }
    if candidate.live_fill_claimed {
        blockers.push(Blocker::LiveFillClaimed);
    }
    if !candidate.bybit_live_execution_unchanged {
        blockers.push(Blocker::BybitLiveExecutionNotProtected);
    }
    if candidate.ibkr_contact_performed {
        blockers.push(Blocker::IbkrContactPerformed);
    }
    if candidate.connector_runtime_started {
        blockers.push(Blocker::ConnectorRuntimeStarted);
    }
    if candidate.broker_fill_import_performed {
        blockers.push(Blocker::BrokerFillImportPerformed);
    }
    if candidate.scorecard_writer_started {
        blockers.push(Blocker::ScorecardWriterStarted);
    }
    if candidate.db_apply_performed {
        blockers.push(Blocker::DbApplyPerformed);
    }
    if candidate.evidence_clock_started {
        blockers.push(Blocker::EvidenceClockStarted);
    }
    if candidate.secret_content_serialized {
        blockers.push(Blocker::SecretContentSerialized);
    }
    if candidate.live_or_tiny_live_authorized {
        blockers.push(Blocker::LiveOrTinyLiveAuthorized);
    }
    if !candidate.sealed {
        blockers.push(Blocker::NotSealed);
    }
}
