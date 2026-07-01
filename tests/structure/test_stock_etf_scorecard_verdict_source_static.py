from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCORECARD_VERDICT = ROOT / "rust/openclaw_types/src/stock_etf_scorecard_verdict.rs"
MAX_LINES = 800

REQUIRED_TYPE_TOKENS = {
    "STOCK_ETF_SCORECARD_VERDICT_CONTRACT_ID",
    '"stock_etf_scorecard_verdict_v1"',
    "pub enum StockEtfScorecardVerdictLabel",
    "pub struct StockEtfScorecardVerdictV1",
    "impl Default for StockEtfScorecardVerdictV1",
    "impl StockEtfScorecardVerdictV1",
    "pub fn profitability_feasible_fixture() -> Self",
    "pub fn validate(&self) -> StockEtfScorecardVerdict<StockEtfScorecardVerdictBlocker>",
    "pub struct StockEtfScorecardVerdict",
    "pub enum StockEtfScorecardVerdictBlocker",
    "fn validate_contract_identity(",
    "fn validate_hashes(",
    "fn validate_threshold_shapes(",
    "fn validate_window_thresholds(",
    "fn validate_paper_shadow_divergence(",
    "fn validate_positive_profitability(",
    "fn validate_probability_thresholds(",
    "fn validate_quality_labels(",
    "fn validate_reviews_and_authority(",
}
REQUIRED_LABELS = {
    "EngineeringReady",
    "ResearchPromising",
    "ProfitabilityFeasible",
    "InsufficientEvidence",
    "ExecutionModelInvalid",
    "Kill",
}
REQUIRED_BLOCKERS = {
    "ContractIdMissing",
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "WrongAssetLane",
    "WrongBroker",
    "EnvironmentDenied",
    "ScorecardInputBundleHashInvalid",
    "EvidenceClockManifestHashInvalid",
    "DqManifestHashInvalid",
    "FormulaAppendixHashInvalid",
    "StatisticalPreregistrationHashInvalid",
    "BenchmarkVersionHashInvalid",
    "CostModelVersionHashInvalid",
    "StrategyHypothesisHashInvalid",
    "ReferenceDataSourcesHashInvalid",
    "PaperShadowReconciliationHashInvalid",
    "ScorecardManifestHashInvalid",
    "VerdictRationaleHashInvalid",
    "WindowThresholdMissing",
    "WindowThresholdNotMet",
    "MinIndependentObservationMissing",
    "IndependentObservationThresholdNotMet",
    "DivergenceThresholdMissing",
    "PaperShadowDivergenceExceeded",
    "ProbabilityMetricOutOfRange",
    "PsrThresholdMissing",
    "DsrThresholdMissing",
    "PsrThresholdNotMet",
    "DsrThresholdNotMet",
    "BenchmarkAfterCostLcbNotPositive",
    "CostStressLcbNotPositive",
    "ConcentrationLabelRejected",
    "RegimeLabelRejected",
    "BreadthLabelRejected",
    "FreshnessLabelRejected",
    "SurvivorshipLabelRejected",
    "ExecutionRealismLabelRejected",
    "QcReviewHashInvalid",
    "MitReviewHashInvalid",
    "QaReviewHashInvalid",
    "QcReviewMissing",
    "MitReviewMissing",
    "QaReviewMissing",
    "ScorecardNotDerivedOnly",
    "PaperShadowFillSeparationMissing",
    "LiveFillClaimed",
    "BybitLiveExecutionNotProtected",
    "IbkrContactPerformed",
    "ConnectorRuntimeStarted",
    "BrokerFillImportPerformed",
    "ScorecardWriterStarted",
    "DbApplyPerformed",
    "EvidenceClockStarted",
    "SecretContentSerialized",
    "LiveOrTinyLiveAuthorized",
    "NotSealed",
    "ExecutionInvalidVerdictWithoutExecutionFailure",
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
    return SCORECARD_VERDICT.read_text(encoding="utf-8")


def test_stock_etf_scorecard_verdict_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_scorecard_verdict_source_keeps_contract_surface() -> None:
    source = _source()

    for token in REQUIRED_TYPE_TOKENS:
        assert token in source
    for label in REQUIRED_LABELS:
        assert label in source
    for blocker in REQUIRED_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source

    assert "contract_id: String::new()" in source
    assert "source_version: 0" in source
    assert "asset_lane: AssetLane::CryptoPerp" in source
    assert "broker: Broker::Bybit" in source
    assert "environment: BrokerEnvironment::LiveReservedDenied" in source
    assert "verdict_label: StockEtfScorecardVerdictLabel::InsufficientEvidence" in source
    assert "scorecard_is_derived_only: false" in source
    assert "paper_and_shadow_fills_separate: false" in source
    assert "bybit_live_execution_unchanged: false" in source
    assert "sealed: false" in source
    assert "accepted: blockers.is_empty()" in source


def test_stock_etf_scorecard_verdict_source_keeps_profitability_feasible_fixture() -> None:
    source = _source()

    assert "contract_id: STOCK_ETF_SCORECARD_VERDICT_CONTRACT_ID.to_string()" in source
    assert "asset_lane: AssetLane::StockEtfCash" in source
    assert "broker: Broker::Ibkr" in source
    assert "environment: BrokerEnvironment::Paper" in source
    assert "paper_shadow_window_trading_days: 42" in source
    assert "min_window_trading_days: 30" in source
    assert "independent_observation_count: 85" in source
    assert "min_independent_observation_count: 60" in source
    assert "net_pnl_minor_units: 119_000" in source
    assert "benchmark_excess_lcb_bps: 12" in source
    assert "conservative_cost_stress_lcb_bps: 5" in source
    assert "paper_shadow_divergence_bps: 35" in source
    assert "max_paper_shadow_divergence_bps: 100" in source
    assert "psr_bps: 9_700" in source
    assert "min_psr_bps: 9_500" in source
    assert "dsr_bps: 9_250" in source
    assert "min_dsr_bps: 9_000" in source
    assert "verdict_label: StockEtfScorecardVerdictLabel::ProfitabilityFeasible" in source
    assert "scorecard_is_derived_only: true" in source
    assert "paper_and_shadow_fills_separate: true" in source
    assert "live_fill_claimed: false" in source
    assert "bybit_live_execution_unchanged: true" in source
    assert "live_or_tiny_live_authorized: false" in source
    assert "sealed: true" in source


def test_stock_etf_scorecard_verdict_source_keeps_validation_dispatch() -> None:
    source = _source()

    assert "validate_contract_identity(self, &mut blockers)" in source
    assert "validate_hashes(self, &mut blockers)" in source
    assert "validate_threshold_shapes(self, &mut blockers)" in source
    assert "validate_reviews_and_authority(self, &mut blockers)" in source
    assert "Label::ProfitabilityFeasible" in source
    assert "validate_positive_profitability(self, &mut blockers)" in source
    assert "Label::ResearchPromising" in source
    assert "Label::EngineeringReady" in source
    assert "Label::ExecutionModelInvalid" in source
    assert "ExecutionInvalidVerdictWithoutExecutionFailure" in source
    assert "Label::InsufficientEvidence | Label::Kill => {}" in source


def test_stock_etf_scorecard_verdict_source_keeps_hash_threshold_quality_gates() -> None:
    source = _source()

    assert "candidate.contract_id.trim().is_empty()" in source
    assert "candidate.contract_id != STOCK_ETF_SCORECARD_VERDICT_CONTRACT_ID" in source
    assert "candidate.environment" in source and "BrokerEnvironment::ReadOnly | BrokerEnvironment::Paper" in source
    assert "!is_sha256_hex(&candidate.scorecard_input_bundle_hash)" in source
    assert "!is_sha256_hex(&candidate.formula_appendix_hash)" in source
    assert "!is_sha256_hex(&candidate.statistical_preregistration_hash)" in source
    assert "!is_sha256_hex(&candidate.paper_shadow_reconciliation_hash)" in source
    assert "candidate.min_window_trading_days == 0" in source
    assert "candidate.min_independent_observation_count == 0" in source
    assert "candidate.max_paper_shadow_divergence_bps == 0" in source
    assert "candidate.psr_bps > 10_000 || candidate.dsr_bps > 10_000" in source
    assert "candidate.min_psr_bps == 0 || candidate.min_psr_bps > 10_000" in source
    assert "candidate.min_dsr_bps == 0 || candidate.min_dsr_bps > 10_000" in source
    assert "candidate.paper_shadow_window_trading_days < candidate.min_window_trading_days" in source
    assert "candidate.independent_observation_count < candidate.min_independent_observation_count" in source
    assert "candidate.paper_shadow_divergence_bps > candidate.max_paper_shadow_divergence_bps" in source
    assert "candidate.benchmark_excess_lcb_bps <= 0" in source
    assert "candidate.conservative_cost_stress_lcb_bps <= 0" in source
    assert "candidate.psr_bps < candidate.min_psr_bps" in source
    assert "candidate.dsr_bps < candidate.min_dsr_bps" in source
    assert "!candidate.concentration_label_passed" in source
    assert "!candidate.regime_label_passed" in source
    assert "!candidate.breadth_label_passed" in source
    assert "!candidate.freshness_label_passed" in source
    assert "!candidate.survivorship_label_passed" in source
    assert "!candidate.execution_realism_label_passed" in source


def test_stock_etf_scorecard_verdict_source_keeps_reviews_and_authority_gates() -> None:
    source = _source()

    assert "!is_sha256_hex(&candidate.qc_review_hash)" in source
    assert "!is_sha256_hex(&candidate.mit_review_hash)" in source
    assert "!is_sha256_hex(&candidate.qa_review_hash)" in source
    assert "!candidate.qc_review_passed" in source
    assert "!candidate.mit_review_passed" in source
    assert "!candidate.qa_review_passed" in source
    assert "!candidate.scorecard_is_derived_only" in source
    assert "!candidate.paper_and_shadow_fills_separate" in source
    assert "candidate.live_fill_claimed" in source
    assert "!candidate.bybit_live_execution_unchanged" in source
    assert "candidate.ibkr_contact_performed" in source
    assert "candidate.connector_runtime_started" in source
    assert "candidate.broker_fill_import_performed" in source
    assert "candidate.scorecard_writer_started" in source
    assert "candidate.db_apply_performed" in source
    assert "candidate.evidence_clock_started" in source
    assert "candidate.secret_content_serialized" in source
    assert "candidate.live_or_tiny_live_authorized" in source
    assert "!candidate.sealed" in source


def test_stock_etf_scorecard_verdict_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{SCORECARD_VERDICT}: contains forbidden token {token!r}")

    assert violations == []
