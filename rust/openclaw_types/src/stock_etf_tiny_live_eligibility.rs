//! Tiny-live ADR eligibility contract for ADR-0048.
//!
//! This source-only contract separates a future ADR discussion gate from any
//! execution authority. Passing it never authorizes IBKR tiny-live/live, starts a
//! connector, reads secrets, or lowers any Bybit gate.

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_artifact::is_sha256_hex;
use crate::stock_etf_release_packet::{
    STOCK_ETF_RELEASE_ADR_PATH, STOCK_ETF_RELEASE_AMD_PATH, STOCK_ETF_RELEASE_SPEC_PATH,
};

pub const STOCK_ETF_TINY_LIVE_ADR_PATH: &str = STOCK_ETF_RELEASE_ADR_PATH;
pub const STOCK_ETF_TINY_LIVE_AMD_PATH: &str = STOCK_ETF_RELEASE_AMD_PATH;
pub const STOCK_ETF_TINY_LIVE_SPEC_PATH: &str = STOCK_ETF_RELEASE_SPEC_PATH;
pub const STOCK_ETF_TINY_LIVE_ADR_ELIGIBILITY_CONTRACT_ID: &str = "tiny_live_adr_eligibility_v1";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TinyLiveAdrEligibilityDecision {
    NotEligible,
    AdrDiscussionOnly,
    TinyLiveAuthorized,
    LiveAuthorized,
}

impl Default for TinyLiveAdrEligibilityDecision {
    fn default() -> Self {
        Self::NotEligible
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TinyLiveAdrEligibilityV1 {
    pub contract_id: String,
    pub source_version: u32,
    pub adr_path: String,
    pub amd_path: String,
    pub spec_path: String,
    pub phase5_release_packet_hash: String,
    pub scorecard_derivation_hash: String,
    pub scorecard_verdict_hash: String,
    pub scorecard_manifest_hash: String,
    pub paper_shadow_reconciliation_hash: String,
    pub dq_manifest_hash: String,
    pub statistical_preregistration_hash: String,
    pub qc_review_hash: String,
    pub mit_review_hash: String,
    pub qa_review_hash: String,
    pub paper_shadow_window_complete: bool,
    pub benchmark_relative_after_cost_lcb_bps: i32,
    pub independent_observation_count: u32,
    pub min_independent_observation_count: u32,
    pub conservative_cost_stress_lcb_bps: i32,
    pub paper_shadow_divergence_bps: u32,
    pub max_paper_shadow_divergence_bps: u32,
    pub concentration_label_passed: bool,
    pub regime_label_passed: bool,
    pub freshness_label_passed: bool,
    pub qc_review_passed: bool,
    pub mit_review_passed: bool,
    pub qa_review_passed: bool,
    pub decision: TinyLiveAdrEligibilityDecision,
    pub secret_content_serialized: bool,
    pub sealed: bool,
}

impl Default for TinyLiveAdrEligibilityV1 {
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            adr_path: STOCK_ETF_TINY_LIVE_ADR_PATH.to_string(),
            amd_path: STOCK_ETF_TINY_LIVE_AMD_PATH.to_string(),
            spec_path: STOCK_ETF_TINY_LIVE_SPEC_PATH.to_string(),
            phase5_release_packet_hash: String::new(),
            scorecard_derivation_hash: String::new(),
            scorecard_verdict_hash: String::new(),
            scorecard_manifest_hash: String::new(),
            paper_shadow_reconciliation_hash: String::new(),
            dq_manifest_hash: String::new(),
            statistical_preregistration_hash: String::new(),
            qc_review_hash: String::new(),
            mit_review_hash: String::new(),
            qa_review_hash: String::new(),
            paper_shadow_window_complete: false,
            benchmark_relative_after_cost_lcb_bps: 0,
            independent_observation_count: 0,
            min_independent_observation_count: 0,
            conservative_cost_stress_lcb_bps: 0,
            paper_shadow_divergence_bps: 0,
            max_paper_shadow_divergence_bps: 0,
            concentration_label_passed: false,
            regime_label_passed: false,
            freshness_label_passed: false,
            qc_review_passed: false,
            mit_review_passed: false,
            qa_review_passed: false,
            decision: TinyLiveAdrEligibilityDecision::NotEligible,
            secret_content_serialized: false,
            sealed: false,
        }
    }
}

impl TinyLiveAdrEligibilityV1 {
    pub fn adr_discussion_fixture() -> Self {
        Self {
            contract_id: STOCK_ETF_TINY_LIVE_ADR_ELIGIBILITY_CONTRACT_ID.to_string(),
            source_version: 1,
            phase5_release_packet_hash: "1".repeat(64),
            scorecard_derivation_hash: "2".repeat(64),
            scorecard_verdict_hash: "3".repeat(64),
            scorecard_manifest_hash: "4".repeat(64),
            paper_shadow_reconciliation_hash: "5".repeat(64),
            dq_manifest_hash: "6".repeat(64),
            statistical_preregistration_hash: "7".repeat(64),
            qc_review_hash: "8".repeat(64),
            mit_review_hash: "9".repeat(64),
            qa_review_hash: "a".repeat(64),
            paper_shadow_window_complete: true,
            benchmark_relative_after_cost_lcb_bps: 11,
            independent_observation_count: 80,
            min_independent_observation_count: 60,
            conservative_cost_stress_lcb_bps: 4,
            paper_shadow_divergence_bps: 45,
            max_paper_shadow_divergence_bps: 100,
            concentration_label_passed: true,
            regime_label_passed: true,
            freshness_label_passed: true,
            qc_review_passed: true,
            mit_review_passed: true,
            qa_review_passed: true,
            decision: TinyLiveAdrEligibilityDecision::AdrDiscussionOnly,
            secret_content_serialized: false,
            sealed: true,
            ..Self::default()
        }
    }

    pub fn validate(&self) -> TinyLiveAdrEligibilityVerdict<TinyLiveAdrEligibilityBlocker> {
        use TinyLiveAdrEligibilityBlocker as Blocker;
        use TinyLiveAdrEligibilityDecision as Decision;

        let mut blockers = Vec::new();
        if self.contract_id.trim().is_empty() {
            blockers.push(Blocker::ContractIdMissing);
        } else if self.contract_id != STOCK_ETF_TINY_LIVE_ADR_ELIGIBILITY_CONTRACT_ID {
            blockers.push(Blocker::ContractIdMismatch);
        }
        if self.source_version != 1 {
            blockers.push(Blocker::SourceVersionMismatch);
        }
        if self.adr_path != STOCK_ETF_TINY_LIVE_ADR_PATH {
            blockers.push(Blocker::AdrPathMismatch);
        }
        if self.amd_path != STOCK_ETF_TINY_LIVE_AMD_PATH {
            blockers.push(Blocker::AmdPathMismatch);
        }
        if self.spec_path != STOCK_ETF_TINY_LIVE_SPEC_PATH {
            blockers.push(Blocker::SpecPathMismatch);
        }
        if !is_sha256_hex(&self.phase5_release_packet_hash) {
            blockers.push(Blocker::Phase5ReleasePacketHashInvalid);
        }
        if !is_sha256_hex(&self.scorecard_derivation_hash) {
            blockers.push(Blocker::ScorecardDerivationHashInvalid);
        }
        if !is_sha256_hex(&self.scorecard_verdict_hash) {
            blockers.push(Blocker::ScorecardVerdictHashInvalid);
        }
        if !is_sha256_hex(&self.scorecard_manifest_hash) {
            blockers.push(Blocker::ScorecardManifestHashInvalid);
        }
        if !is_sha256_hex(&self.paper_shadow_reconciliation_hash) {
            blockers.push(Blocker::PaperShadowReconciliationHashInvalid);
        }
        if !is_sha256_hex(&self.dq_manifest_hash) {
            blockers.push(Blocker::DqManifestHashInvalid);
        }
        if !is_sha256_hex(&self.statistical_preregistration_hash) {
            blockers.push(Blocker::StatisticalPreregistrationHashInvalid);
        }
        if !is_sha256_hex(&self.qc_review_hash) {
            blockers.push(Blocker::QcReviewHashInvalid);
        }
        if !is_sha256_hex(&self.mit_review_hash) {
            blockers.push(Blocker::MitReviewHashInvalid);
        }
        if !is_sha256_hex(&self.qa_review_hash) {
            blockers.push(Blocker::QaReviewHashInvalid);
        }
        if !self.paper_shadow_window_complete {
            blockers.push(Blocker::PaperShadowWindowIncomplete);
        }
        if self.benchmark_relative_after_cost_lcb_bps <= 0 {
            blockers.push(Blocker::BenchmarkAfterCostLcbNotPositive);
        }
        if self.min_independent_observation_count == 0 {
            blockers.push(Blocker::MinIndependentObservationMissing);
        }
        if self.independent_observation_count < self.min_independent_observation_count {
            blockers.push(Blocker::IndependentObservationThresholdNotMet);
        }
        if self.conservative_cost_stress_lcb_bps <= 0 {
            blockers.push(Blocker::CostStressLcbNotPositive);
        }
        if self.max_paper_shadow_divergence_bps == 0 {
            blockers.push(Blocker::DivergenceThresholdMissing);
        }
        if self.max_paper_shadow_divergence_bps > 0
            && self.paper_shadow_divergence_bps > self.max_paper_shadow_divergence_bps
        {
            blockers.push(Blocker::PaperShadowDivergenceExceeded);
        }
        if !self.concentration_label_passed {
            blockers.push(Blocker::ConcentrationLabelRejected);
        }
        if !self.regime_label_passed {
            blockers.push(Blocker::RegimeLabelRejected);
        }
        if !self.freshness_label_passed {
            blockers.push(Blocker::FreshnessLabelRejected);
        }
        if !self.qc_review_passed {
            blockers.push(Blocker::QcReviewMissing);
        }
        if !self.mit_review_passed {
            blockers.push(Blocker::MitReviewMissing);
        }
        if !self.qa_review_passed {
            blockers.push(Blocker::QaReviewMissing);
        }
        match self.decision {
            Decision::AdrDiscussionOnly => {}
            Decision::TinyLiveAuthorized => blockers.push(Blocker::TinyLiveAuthorizationRequested),
            Decision::LiveAuthorized => blockers.push(Blocker::LiveAuthorizationRequested),
            Decision::NotEligible => blockers.push(Blocker::DecisionNotAdrDiscussionOnly),
        }
        if self.secret_content_serialized {
            blockers.push(Blocker::SecretContentSerialized);
        }
        if !self.sealed {
            blockers.push(Blocker::NotSealed);
        }

        TinyLiveAdrEligibilityVerdict::new(blockers)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TinyLiveAdrEligibilityVerdict<B> {
    pub accepted: bool,
    pub blockers: Vec<B>,
}

impl<B> TinyLiveAdrEligibilityVerdict<B> {
    fn new(blockers: Vec<B>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TinyLiveAdrEligibilityBlocker {
    ContractIdMissing,
    ContractIdMismatch,
    SourceVersionMismatch,
    AdrPathMismatch,
    AmdPathMismatch,
    SpecPathMismatch,
    Phase5ReleasePacketHashInvalid,
    ScorecardDerivationHashInvalid,
    ScorecardVerdictHashInvalid,
    ScorecardManifestHashInvalid,
    PaperShadowReconciliationHashInvalid,
    DqManifestHashInvalid,
    StatisticalPreregistrationHashInvalid,
    QcReviewHashInvalid,
    MitReviewHashInvalid,
    QaReviewHashInvalid,
    PaperShadowWindowIncomplete,
    BenchmarkAfterCostLcbNotPositive,
    MinIndependentObservationMissing,
    IndependentObservationThresholdNotMet,
    CostStressLcbNotPositive,
    DivergenceThresholdMissing,
    PaperShadowDivergenceExceeded,
    ConcentrationLabelRejected,
    RegimeLabelRejected,
    FreshnessLabelRejected,
    QcReviewMissing,
    MitReviewMissing,
    QaReviewMissing,
    DecisionNotAdrDiscussionOnly,
    TinyLiveAuthorizationRequested,
    LiveAuthorizationRequested,
    SecretContentSerialized,
    NotSealed,
}
