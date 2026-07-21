from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TINY_LIVE_ELIGIBILITY = ROOT / "rust/openclaw_types/src/stock_etf_tiny_live_eligibility.rs"
from tests.structure.file_line_policy import MAX_FILE_LINES as MAX_LINES

REQUIRED_TYPE_TOKENS = {
    "STOCK_ETF_TINY_LIVE_ADR_PATH",
    "STOCK_ETF_TINY_LIVE_AMD_PATH",
    "STOCK_ETF_TINY_LIVE_SPEC_PATH",
    "STOCK_ETF_TINY_LIVE_ADR_ELIGIBILITY_CONTRACT_ID",
    '"tiny_live_adr_eligibility_v1"',
    "pub enum TinyLiveAdrEligibilityDecision",
    "pub struct TinyLiveAdrEligibilityV1",
    "impl Default for TinyLiveAdrEligibilityV1",
    "impl TinyLiveAdrEligibilityV1",
    "pub fn adr_discussion_fixture() -> Self",
    "pub fn validate(&self) -> TinyLiveAdrEligibilityVerdict<TinyLiveAdrEligibilityBlocker>",
    "pub struct TinyLiveAdrEligibilityVerdict",
    "pub enum TinyLiveAdrEligibilityBlocker",
}
REQUIRED_DECISIONS = {
    "NotEligible",
    "AdrDiscussionOnly",
    "TinyLiveAuthorized",
    "LiveAuthorized",
}
REQUIRED_BLOCKERS = {
    "ContractIdMissing",
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "AdrPathMismatch",
    "AmdPathMismatch",
    "SpecPathMismatch",
    "Phase5ReleasePacketHashInvalid",
    "ScorecardDerivationHashInvalid",
    "ScorecardVerdictHashInvalid",
    "ScorecardManifestHashInvalid",
    "PaperShadowReconciliationHashInvalid",
    "DqManifestHashInvalid",
    "StatisticalPreregistrationHashInvalid",
    "QcReviewHashInvalid",
    "MitReviewHashInvalid",
    "QaReviewHashInvalid",
    "PaperShadowWindowIncomplete",
    "BenchmarkAfterCostLcbNotPositive",
    "MinIndependentObservationMissing",
    "IndependentObservationThresholdNotMet",
    "CostStressLcbNotPositive",
    "DivergenceThresholdMissing",
    "PaperShadowDivergenceExceeded",
    "ConcentrationLabelRejected",
    "RegimeLabelRejected",
    "FreshnessLabelRejected",
    "QcReviewMissing",
    "MitReviewMissing",
    "QaReviewMissing",
    "DecisionNotAdrDiscussionOnly",
    "TinyLiveAuthorizationRequested",
    "LiveAuthorizationRequested",
    "SecretContentSerialized",
    "NotSealed",
}
FORBIDDEN_RUNTIME_TOKENS = (
    "std::env",
    "env::var",
    "var_os",
    "vars_os",
    "std::fs",
    "std::path::Path",
    "File::open",
    "OpenOptions",
    "read_to_string",
    "read_to_end",
    "include_str!",
    "include_bytes!",
    "std::net",
    "TcpStream",
    "UdpSocket",
    "tokio::net",
    "reqwest",
    "hyper::",
    "ureq",
    "ib_insync",
    "ibapi",
    "IBApi",
    "std::time",
    "SystemTime",
    "Instant",
    "chrono",
    "Utc::now",
    "Local::now",
    "std::thread",
    "thread::spawn",
    "tokio::spawn",
    "tokio::task",
    "tokio::time",
    "sleep(",
    "std::process",
    "process::Command",
    "Command::new",
    ".spawn(",
    "BybitRestClient",
    "BybitPrivateWs",
    "bybit_rest_client::",
    "bybit_private_ws::",
    "order_manager::",
    "OrderManager",
    "CreateOrderRequest",
    "OrderResponse",
    ".place_order(",
    ".cancel_order(",
    ".replace_order(",
    ".modify_order(",
    ".create_order(",
)
FORBIDDEN_SECRET_MATERIAL_TOKENS = (
    "api_key",
    "api_secret",
    "password",
    "token =",
    "OPENCLAW_",
    "SecretString",
    "SecretVec",
    "keyring",
)


def _source() -> str:
    return TINY_LIVE_ELIGIBILITY.read_text(encoding="utf-8")


def _block_between(source: str, start_token: str, end_tokens: tuple[str, ...]) -> str:
    start = source.index(start_token)
    end = len(source)
    for token in end_tokens:
        candidate = source.find(token, start + len(start_token))
        if candidate != -1:
            end = min(end, candidate)
    return source[start:end]


def _impl_block(source: str, type_name: str) -> str:
    return _block_between(
        source,
        f"impl {type_name} {{",
        ("\nimpl ", "\n#[derive", "\nfn "),
    )


def _default_block(source: str, type_name: str) -> str:
    return _block_between(
        source,
        f"impl Default for {type_name} {{",
        ("\nimpl ", "\n#[derive", "\nfn "),
    )


def _adr_discussion_fixture_block(source: str) -> str:
    impl = _impl_block(source, "TinyLiveAdrEligibilityV1")
    return _block_between(
        impl,
        "pub fn adr_discussion_fixture() -> Self",
        ("\n    pub fn validate(&self)",),
    )


def test_stock_etf_tiny_live_eligibility_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_tiny_live_eligibility_source_keeps_contract_surface() -> None:
    source = _source()

    for token in REQUIRED_TYPE_TOKENS:
        assert token in source
    for decision in REQUIRED_DECISIONS:
        assert decision in source
    for blocker in REQUIRED_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source

    assert "decision: TinyLiveAdrEligibilityDecision::NotEligible" in source
    assert "paper_shadow_window_complete: false" in source
    assert "benchmark_relative_after_cost_lcb_bps: 0" in source
    assert "independent_observation_count: 0" in source
    assert "min_independent_observation_count: 0" in source
    assert "conservative_cost_stress_lcb_bps: 0" in source
    assert "max_paper_shadow_divergence_bps: 0" in source
    assert "secret_content_serialized: false" in source
    assert "sealed: false" in source
    assert "accepted: blockers.is_empty()" in source


def test_stock_etf_tiny_live_eligibility_source_keeps_adr_discussion_only_fixture() -> None:
    source = _source()
    fixture = _adr_discussion_fixture_block(source)

    assert "contract_id: STOCK_ETF_TINY_LIVE_ADR_ELIGIBILITY_CONTRACT_ID.to_string()" in fixture
    assert "source_version: 1" in fixture
    assert "paper_shadow_window_complete: true" in fixture
    assert "benchmark_relative_after_cost_lcb_bps: 11" in fixture
    assert "independent_observation_count: 80" in fixture
    assert "min_independent_observation_count: 60" in fixture
    assert "conservative_cost_stress_lcb_bps: 4" in fixture
    assert "paper_shadow_divergence_bps: 45" in fixture
    assert "max_paper_shadow_divergence_bps: 100" in fixture
    assert "concentration_label_passed: true" in fixture
    assert "regime_label_passed: true" in fixture
    assert "freshness_label_passed: true" in fixture
    assert "qc_review_passed: true" in fixture
    assert "mit_review_passed: true" in fixture
    assert "qa_review_passed: true" in fixture
    assert "decision: TinyLiveAdrEligibilityDecision::AdrDiscussionOnly" in fixture
    assert "secret_content_serialized: false" in fixture
    assert "sealed: true" in fixture
    assert "..Self::default()" in fixture


def test_stock_etf_tiny_live_eligibility_fixture_excludes_live_authority_and_secret_crosswire() -> None:
    source = _source()
    fixture = _adr_discussion_fixture_block(source)
    default_impl = _default_block(source, "TinyLiveAdrEligibilityV1")

    for forbidden in (
        "source_version: 0",
        "phase5_release_packet_hash: String::new()",
        "scorecard_derivation_hash: String::new()",
        "scorecard_verdict_hash: String::new()",
        "scorecard_manifest_hash: String::new()",
        "paper_shadow_reconciliation_hash: String::new()",
        "dq_manifest_hash: String::new()",
        "statistical_preregistration_hash: String::new()",
        "qc_review_hash: String::new()",
        "mit_review_hash: String::new()",
        "qa_review_hash: String::new()",
        "paper_shadow_window_complete: false",
        "benchmark_relative_after_cost_lcb_bps: 0",
        "independent_observation_count: 0",
        "min_independent_observation_count: 0",
        "conservative_cost_stress_lcb_bps: 0",
        "max_paper_shadow_divergence_bps: 0",
        "concentration_label_passed: false",
        "regime_label_passed: false",
        "freshness_label_passed: false",
        "qc_review_passed: false",
        "mit_review_passed: false",
        "qa_review_passed: false",
        "decision: TinyLiveAdrEligibilityDecision::NotEligible",
        "decision: TinyLiveAdrEligibilityDecision::TinyLiveAuthorized",
        "decision: TinyLiveAdrEligibilityDecision::LiveAuthorized",
        "secret_content_serialized: true",
        "sealed: false",
    ):
        assert forbidden not in fixture

    for fail_closed in (
        "contract_id: String::new()",
        "source_version: 0",
        "phase5_release_packet_hash: String::new()",
        "scorecard_derivation_hash: String::new()",
        "scorecard_verdict_hash: String::new()",
        "scorecard_manifest_hash: String::new()",
        "paper_shadow_reconciliation_hash: String::new()",
        "dq_manifest_hash: String::new()",
        "statistical_preregistration_hash: String::new()",
        "qc_review_hash: String::new()",
        "mit_review_hash: String::new()",
        "qa_review_hash: String::new()",
        "decision: TinyLiveAdrEligibilityDecision::NotEligible",
        "paper_shadow_window_complete: false",
        "benchmark_relative_after_cost_lcb_bps: 0",
        "independent_observation_count: 0",
        "min_independent_observation_count: 0",
        "conservative_cost_stress_lcb_bps: 0",
        "max_paper_shadow_divergence_bps: 0",
        "concentration_label_passed: false",
        "regime_label_passed: false",
        "freshness_label_passed: false",
        "qc_review_passed: false",
        "mit_review_passed: false",
        "qa_review_passed: false",
        "secret_content_serialized: false",
        "sealed: false",
    ):
        assert fail_closed in default_impl


def test_stock_etf_tiny_live_eligibility_source_keeps_hash_stat_review_gates() -> None:
    source = _source()

    assert "self.contract_id.trim().is_empty()" in source
    assert "self.contract_id != STOCK_ETF_TINY_LIVE_ADR_ELIGIBILITY_CONTRACT_ID" in source
    assert "self.adr_path != STOCK_ETF_TINY_LIVE_ADR_PATH" in source
    assert "self.amd_path != STOCK_ETF_TINY_LIVE_AMD_PATH" in source
    assert "self.spec_path != STOCK_ETF_TINY_LIVE_SPEC_PATH" in source
    assert "!is_sha256_hex(&self.phase5_release_packet_hash)" in source
    assert "!is_sha256_hex(&self.scorecard_derivation_hash)" in source
    assert "!is_sha256_hex(&self.scorecard_verdict_hash)" in source
    assert "!is_sha256_hex(&self.scorecard_manifest_hash)" in source
    assert "!is_sha256_hex(&self.paper_shadow_reconciliation_hash)" in source
    assert "!is_sha256_hex(&self.dq_manifest_hash)" in source
    assert "!is_sha256_hex(&self.statistical_preregistration_hash)" in source
    assert "!is_sha256_hex(&self.qc_review_hash)" in source
    assert "!is_sha256_hex(&self.mit_review_hash)" in source
    assert "!is_sha256_hex(&self.qa_review_hash)" in source
    assert "if !self.paper_shadow_window_complete" in source
    assert "self.benchmark_relative_after_cost_lcb_bps <= 0" in source
    assert "self.min_independent_observation_count == 0" in source
    assert "self.independent_observation_count < self.min_independent_observation_count" in source
    assert "self.conservative_cost_stress_lcb_bps <= 0" in source
    assert "self.max_paper_shadow_divergence_bps == 0" in source
    assert "self.paper_shadow_divergence_bps > self.max_paper_shadow_divergence_bps" in source
    assert "if !self.concentration_label_passed" in source
    assert "if !self.regime_label_passed" in source
    assert "if !self.freshness_label_passed" in source
    assert "if !self.qc_review_passed" in source
    assert "if !self.mit_review_passed" in source
    assert "if !self.qa_review_passed" in source


def test_stock_etf_tiny_live_eligibility_source_keeps_no_authorization_decision_matrix() -> None:
    source = _source()

    assert "Decision::AdrDiscussionOnly => {}" in source
    assert "Decision::TinyLiveAuthorized => blockers.push(Blocker::TinyLiveAuthorizationRequested)" in source
    assert "Decision::LiveAuthorized => blockers.push(Blocker::LiveAuthorizationRequested)" in source
    assert "Decision::NotEligible => blockers.push(Blocker::DecisionNotAdrDiscussionOnly)" in source
    assert "if self.secret_content_serialized" in source
    assert "if !self.sealed" in source


def test_stock_etf_tiny_live_eligibility_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{TINY_LIVE_ELIGIBILITY}: contains forbidden token {token!r}")

    assert violations == []
