//! ADR-0048 tiny-live ADR eligibility acceptance tests.
//!
//! These tests validate the future discussion gate only. They do not authorize
//! tiny-live/live, read secrets, contact IBKR, or start an evidence clock.

use std::path::PathBuf;

use openclaw_types::{
    TinyLiveAdrEligibilityBlocker, TinyLiveAdrEligibilityDecision, TinyLiveAdrEligibilityV1,
    STOCK_ETF_TINY_LIVE_ADR_ELIGIBILITY_CONTRACT_ID,
};

fn assert_has_blocker(
    blockers: &[TinyLiveAdrEligibilityBlocker],
    blocker: TinyLiveAdrEligibilityBlocker,
) {
    assert!(
        blockers.contains(&blocker),
        "missing blocker {blocker:?}; blockers: {blockers:?}"
    );
}

fn assert_lacks_blocker(
    blockers: &[TinyLiveAdrEligibilityBlocker],
    blocker: TinyLiveAdrEligibilityBlocker,
) {
    assert!(
        !blockers.contains(&blocker),
        "unexpected blocker {blocker:?}; blockers: {blockers:?}"
    );
}

#[test]
fn default_tiny_live_eligibility_blocks_discussion() {
    let verdict = TinyLiveAdrEligibilityV1::default().validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::ContractIdMissing));
    assert!(verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::SourceVersionMismatch));
    assert!(verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::Phase5ReleasePacketHashInvalid));
    assert!(verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::ScorecardDerivationHashInvalid));
    assert!(verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::ScorecardVerdictHashInvalid));
    assert!(verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::PaperShadowReconciliationHashInvalid));
    assert!(verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::PaperShadowWindowIncomplete));
    assert!(verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::DecisionNotAdrDiscussionOnly));
    assert!(verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::NotSealed));
}

#[test]
fn accepted_fixture_allows_only_future_adr_discussion() {
    let candidate = TinyLiveAdrEligibilityV1::adr_discussion_fixture();
    let verdict = candidate.validate();

    assert!(verdict.accepted);
    assert!(verdict.blockers.is_empty());
    assert_eq!(
        candidate.contract_id,
        STOCK_ETF_TINY_LIVE_ADR_ELIGIBILITY_CONTRACT_ID
    );
    assert_eq!(candidate.source_version, 1);
    assert_eq!(
        candidate.decision,
        TinyLiveAdrEligibilityDecision::AdrDiscussionOnly
    );
}

#[test]
fn tiny_live_eligibility_rejects_each_identity_and_path_gap_independently() {
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            contract_id: String::new(),
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::ContractIdMissing,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            contract_id: "tiny_live_adr_eligibility_v1_fixture".to_string(),
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::ContractIdMismatch,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            source_version: 2,
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::SourceVersionMismatch,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            adr_path: "docs/adr/wrong.md".to_string(),
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::AdrPathMismatch,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            amd_path: "docs/governance_dev/amendments/wrong.md".to_string(),
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::AmdPathMismatch,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            spec_path: "docs/execution_plan/specs/wrong.md".to_string(),
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::SpecPathMismatch,
    );
}

#[test]
fn tiny_live_eligibility_rejects_each_hash_lineage_gap_independently() {
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            phase5_release_packet_hash: String::new(),
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::Phase5ReleasePacketHashInvalid,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            scorecard_derivation_hash: String::new(),
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::ScorecardDerivationHashInvalid,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            scorecard_verdict_hash: String::new(),
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::ScorecardVerdictHashInvalid,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            scorecard_manifest_hash: String::new(),
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::ScorecardManifestHashInvalid,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            paper_shadow_reconciliation_hash: String::new(),
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::PaperShadowReconciliationHashInvalid,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            dq_manifest_hash: String::new(),
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::DqManifestHashInvalid,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            statistical_preregistration_hash: String::new(),
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::StatisticalPreregistrationHashInvalid,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            qc_review_hash: String::new(),
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::QcReviewHashInvalid,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            mit_review_hash: String::new(),
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::MitReviewHashInvalid,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            qa_review_hash: String::new(),
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::QaReviewHashInvalid,
    );
}

#[test]
fn tiny_live_eligibility_rejects_each_statistical_gate_gap_independently() {
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            paper_shadow_window_complete: false,
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::PaperShadowWindowIncomplete,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            benchmark_relative_after_cost_lcb_bps: 0,
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::BenchmarkAfterCostLcbNotPositive,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            min_independent_observation_count: 0,
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::MinIndependentObservationMissing,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            independent_observation_count: 59,
            min_independent_observation_count: 60,
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::IndependentObservationThresholdNotMet,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            conservative_cost_stress_lcb_bps: 0,
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::CostStressLcbNotPositive,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            max_paper_shadow_divergence_bps: 0,
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::DivergenceThresholdMissing,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            paper_shadow_divergence_bps: 101,
            max_paper_shadow_divergence_bps: 100,
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::PaperShadowDivergenceExceeded,
    );
}

#[test]
fn tiny_live_eligibility_rejects_each_label_and_review_gap_independently() {
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            concentration_label_passed: false,
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::ConcentrationLabelRejected,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            regime_label_passed: false,
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::RegimeLabelRejected,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            freshness_label_passed: false,
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::FreshnessLabelRejected,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            qc_review_passed: false,
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::QcReviewMissing,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            mit_review_passed: false,
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::MitReviewMissing,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            qa_review_passed: false,
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::QaReviewMissing,
    );
}

#[test]
fn tiny_live_eligibility_rejects_each_decision_secret_and_seal_gap_independently() {
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            decision: TinyLiveAdrEligibilityDecision::NotEligible,
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::DecisionNotAdrDiscussionOnly,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            decision: TinyLiveAdrEligibilityDecision::TinyLiveAuthorized,
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::TinyLiveAuthorizationRequested,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            decision: TinyLiveAdrEligibilityDecision::LiveAuthorized,
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::LiveAuthorizationRequested,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            secret_content_serialized: true,
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::SecretContentSerialized,
    );
    assert_single_blocker(
        TinyLiveAdrEligibilityV1 {
            sealed: false,
            ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
        },
        TinyLiveAdrEligibilityBlocker::NotSealed,
    );
}

#[test]
fn tiny_live_eligibility_requires_exact_contract_id_and_source_version() {
    let candidate = TinyLiveAdrEligibilityV1 {
        contract_id: "tiny_live_adr_eligibility_v1_fixture".to_string(),
        source_version: 2,
        ..TinyLiveAdrEligibilityV1::adr_discussion_fixture()
    };
    let verdict = candidate.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::ContractIdMismatch));
    assert!(verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::SourceVersionMismatch));
}

#[test]
fn positive_scorecard_still_requires_window_reviews_and_hashes() {
    let mut candidate = TinyLiveAdrEligibilityV1::adr_discussion_fixture();
    candidate.paper_shadow_window_complete = false;
    candidate.qc_review_passed = false;
    candidate.qa_review_passed = false;
    candidate.scorecard_derivation_hash.clear();
    candidate.scorecard_verdict_hash.clear();
    candidate.scorecard_manifest_hash.clear();
    candidate.paper_shadow_reconciliation_hash.clear();
    candidate.qa_review_hash.clear();

    let verdict = candidate.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::PaperShadowWindowIncomplete));
    assert!(verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::QcReviewMissing));
    assert!(verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::QaReviewMissing));
    assert!(verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::ScorecardDerivationHashInvalid));
    assert!(verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::ScorecardVerdictHashInvalid));
    assert!(verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::ScorecardManifestHashInvalid));
    assert!(verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::PaperShadowReconciliationHashInvalid));
    assert!(verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::QaReviewHashInvalid));
}

#[test]
fn statistics_gate_requires_positive_lcbs_independent_sample_and_divergence_pass() {
    let mut candidate = TinyLiveAdrEligibilityV1::adr_discussion_fixture();
    candidate.benchmark_relative_after_cost_lcb_bps = 0;
    candidate.conservative_cost_stress_lcb_bps = -1;
    candidate.independent_observation_count = 59;
    candidate.min_independent_observation_count = 60;
    candidate.paper_shadow_divergence_bps = 101;
    candidate.max_paper_shadow_divergence_bps = 100;

    let verdict = candidate.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::BenchmarkAfterCostLcbNotPositive));
    assert!(verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::CostStressLcbNotPositive));
    assert!(verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::IndependentObservationThresholdNotMet));
    assert!(verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::PaperShadowDivergenceExceeded));
}

#[test]
fn tiny_live_or_live_authority_is_rejected_even_with_all_evidence_present() {
    let mut tiny_live = TinyLiveAdrEligibilityV1::adr_discussion_fixture();
    tiny_live.decision = TinyLiveAdrEligibilityDecision::TinyLiveAuthorized;
    let tiny_verdict = tiny_live.validate();
    assert!(!tiny_verdict.accepted);
    assert!(tiny_verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::TinyLiveAuthorizationRequested));

    let mut live = TinyLiveAdrEligibilityV1::adr_discussion_fixture();
    live.decision = TinyLiveAdrEligibilityDecision::LiveAuthorized;
    live.secret_content_serialized = true;
    let live_verdict = live.validate();
    assert!(!live_verdict.accepted);
    assert!(live_verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::LiveAuthorizationRequested));
    assert!(live_verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::SecretContentSerialized));
}

#[test]
fn tiny_live_eligibility_rejects_decision_and_secret_cross_wire_independently() {
    let mut not_eligible = TinyLiveAdrEligibilityV1::adr_discussion_fixture();
    not_eligible.decision = TinyLiveAdrEligibilityDecision::NotEligible;
    let not_eligible_verdict = not_eligible.validate();
    assert!(!not_eligible_verdict.accepted);
    assert_has_blocker(
        &not_eligible_verdict.blockers,
        TinyLiveAdrEligibilityBlocker::DecisionNotAdrDiscussionOnly,
    );
    assert_lacks_blocker(
        &not_eligible_verdict.blockers,
        TinyLiveAdrEligibilityBlocker::TinyLiveAuthorizationRequested,
    );
    assert_lacks_blocker(
        &not_eligible_verdict.blockers,
        TinyLiveAdrEligibilityBlocker::LiveAuthorizationRequested,
    );
    assert_lacks_blocker(
        &not_eligible_verdict.blockers,
        TinyLiveAdrEligibilityBlocker::SecretContentSerialized,
    );
    assert_lacks_blocker(
        &not_eligible_verdict.blockers,
        TinyLiveAdrEligibilityBlocker::NotSealed,
    );

    let mut tiny_live = TinyLiveAdrEligibilityV1::adr_discussion_fixture();
    tiny_live.decision = TinyLiveAdrEligibilityDecision::TinyLiveAuthorized;
    let tiny_live_verdict = tiny_live.validate();
    assert!(!tiny_live_verdict.accepted);
    assert_has_blocker(
        &tiny_live_verdict.blockers,
        TinyLiveAdrEligibilityBlocker::TinyLiveAuthorizationRequested,
    );
    assert_lacks_blocker(
        &tiny_live_verdict.blockers,
        TinyLiveAdrEligibilityBlocker::DecisionNotAdrDiscussionOnly,
    );
    assert_lacks_blocker(
        &tiny_live_verdict.blockers,
        TinyLiveAdrEligibilityBlocker::LiveAuthorizationRequested,
    );
    assert_lacks_blocker(
        &tiny_live_verdict.blockers,
        TinyLiveAdrEligibilityBlocker::SecretContentSerialized,
    );
    assert_lacks_blocker(
        &tiny_live_verdict.blockers,
        TinyLiveAdrEligibilityBlocker::NotSealed,
    );

    let mut live = TinyLiveAdrEligibilityV1::adr_discussion_fixture();
    live.decision = TinyLiveAdrEligibilityDecision::LiveAuthorized;
    let live_verdict = live.validate();
    assert!(!live_verdict.accepted);
    assert_has_blocker(
        &live_verdict.blockers,
        TinyLiveAdrEligibilityBlocker::LiveAuthorizationRequested,
    );
    assert_lacks_blocker(
        &live_verdict.blockers,
        TinyLiveAdrEligibilityBlocker::DecisionNotAdrDiscussionOnly,
    );
    assert_lacks_blocker(
        &live_verdict.blockers,
        TinyLiveAdrEligibilityBlocker::TinyLiveAuthorizationRequested,
    );
    assert_lacks_blocker(
        &live_verdict.blockers,
        TinyLiveAdrEligibilityBlocker::SecretContentSerialized,
    );
    assert_lacks_blocker(
        &live_verdict.blockers,
        TinyLiveAdrEligibilityBlocker::NotSealed,
    );

    let mut secret = TinyLiveAdrEligibilityV1::adr_discussion_fixture();
    secret.secret_content_serialized = true;
    let secret_verdict = secret.validate();
    assert!(!secret_verdict.accepted);
    assert_has_blocker(
        &secret_verdict.blockers,
        TinyLiveAdrEligibilityBlocker::SecretContentSerialized,
    );
    assert_lacks_blocker(
        &secret_verdict.blockers,
        TinyLiveAdrEligibilityBlocker::DecisionNotAdrDiscussionOnly,
    );
    assert_lacks_blocker(
        &secret_verdict.blockers,
        TinyLiveAdrEligibilityBlocker::TinyLiveAuthorizationRequested,
    );
    assert_lacks_blocker(
        &secret_verdict.blockers,
        TinyLiveAdrEligibilityBlocker::LiveAuthorizationRequested,
    );
    assert_lacks_blocker(
        &secret_verdict.blockers,
        TinyLiveAdrEligibilityBlocker::NotSealed,
    );

    let mut unsealed = TinyLiveAdrEligibilityV1::adr_discussion_fixture();
    unsealed.sealed = false;
    let unsealed_verdict = unsealed.validate();
    assert!(!unsealed_verdict.accepted);
    assert_has_blocker(
        &unsealed_verdict.blockers,
        TinyLiveAdrEligibilityBlocker::NotSealed,
    );
    assert_lacks_blocker(
        &unsealed_verdict.blockers,
        TinyLiveAdrEligibilityBlocker::DecisionNotAdrDiscussionOnly,
    );
    assert_lacks_blocker(
        &unsealed_verdict.blockers,
        TinyLiveAdrEligibilityBlocker::TinyLiveAuthorizationRequested,
    );
    assert_lacks_blocker(
        &unsealed_verdict.blockers,
        TinyLiveAdrEligibilityBlocker::LiveAuthorizationRequested,
    );
    assert_lacks_blocker(
        &unsealed_verdict.blockers,
        TinyLiveAdrEligibilityBlocker::SecretContentSerialized,
    );
}

#[test]
fn blocked_template_is_parseable_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/stock_etf_tiny_live_adr_eligibility.template.toml"),
    )
    .expect("read tiny-live ADR eligibility template");
    let parsed: TinyLiveAdrEligibilityV1 =
        toml::from_str(&raw).expect("tiny-live ADR eligibility template parses");

    assert_eq!(parsed.decision, TinyLiveAdrEligibilityDecision::NotEligible);
    assert_eq!(parsed.source_version, 0);
    assert!(!parsed.paper_shadow_window_complete);
    assert!(!parsed.sealed);
    assert!(!parsed.validate().accepted);

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}

fn assert_single_blocker(
    candidate: TinyLiveAdrEligibilityV1,
    expected: TinyLiveAdrEligibilityBlocker,
) {
    let verdict = candidate.validate();

    assert!(!verdict.accepted);
    assert_eq!(verdict.blockers, vec![expected]);
}
