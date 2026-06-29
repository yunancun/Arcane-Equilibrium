//! ADR-0048 tiny-live ADR eligibility acceptance tests.
//!
//! These tests validate the future discussion gate only. They do not authorize
//! tiny-live/live, read secrets, contact IBKR, or start an evidence clock.

use std::path::PathBuf;

use openclaw_types::{
    TinyLiveAdrEligibilityBlocker, TinyLiveAdrEligibilityDecision, TinyLiveAdrEligibilityV1,
};

#[test]
fn default_tiny_live_eligibility_blocks_discussion() {
    let verdict = TinyLiveAdrEligibilityV1::default().validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::ContractIdMissing));
    assert!(verdict
        .blockers
        .contains(&TinyLiveAdrEligibilityBlocker::Phase5ReleasePacketHashInvalid));
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
        candidate.decision,
        TinyLiveAdrEligibilityDecision::AdrDiscussionOnly
    );
}

#[test]
fn positive_scorecard_still_requires_window_reviews_and_hashes() {
    let mut candidate = TinyLiveAdrEligibilityV1::adr_discussion_fixture();
    candidate.paper_shadow_window_complete = false;
    candidate.qc_review_passed = false;
    candidate.scorecard_manifest_hash.clear();

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
        .contains(&TinyLiveAdrEligibilityBlocker::ScorecardManifestHashInvalid));
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
