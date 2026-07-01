from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCORECARD_DERIVATION = ROOT / "rust/openclaw_types/src/stock_etf_scorecard_derivation.rs"
MAX_LINES = 800

REQUIRED_TYPE_TOKENS = {
    "STOCK_ETF_SCORECARD_DERIVATION_CONTRACT_ID",
    '"stock_etf_scorecard_derivation_v1"',
    "pub struct StockEtfScorecardDerivationV1",
    "impl Default for StockEtfScorecardDerivationV1",
    "impl StockEtfScorecardDerivationV1",
    "pub fn accepted_fixture() -> Self",
    "pub fn validate(&self) -> StockEtfScorecardDerivationVerdict",
    "pub struct StockEtfScorecardDerivationVerdict",
    "impl StockEtfScorecardDerivationVerdict",
    "pub enum StockEtfScorecardDerivationBlocker",
    "fn validate_ids(",
    "fn validate_hashes(",
    "fn validate_authority(",
}
REQUIRED_FIELDS = {
    "contract_id",
    "source_version",
    "asset_lane",
    "broker",
    "environment",
    "derivation_run_id",
    "strategy_id",
    "universe_version",
    "benchmark_version",
    "as_of_date",
    "scorecard_input_bundle_hash",
    "evidence_clock_manifest_hash",
    "dq_manifest_hash",
    "paper_shadow_reconciliation_hash",
    "formula_appendix_hash",
    "statistical_preregistration_hash",
    "scorecard_manifest_hash",
    "scorecard_verdict_hash",
    "source_commit_hash",
    "derivation_code_hash",
    "output_artifact_hash",
    "qc_review_hash",
    "mit_review_hash",
    "qa_review_hash",
    "derived_from_atomic_facts_only",
    "idempotent_replay_proven",
    "paper_and_shadow_fills_separate",
    "bybit_live_execution_unchanged",
    "ibkr_contact_performed",
    "connector_runtime_started",
    "broker_fill_import_performed",
    "shadow_fill_generated",
    "reconciliation_writer_started",
    "scorecard_writer_started",
    "db_apply_performed",
    "evidence_clock_started",
    "secret_content_serialized",
    "live_or_tiny_live_authorized",
    "sealed",
}
REQUIRED_BLOCKERS = {
    "ContractIdMissing",
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "WrongAssetLane",
    "WrongBroker",
    "EnvironmentDenied",
    "DerivationRunIdMissing",
    "StrategyIdMissing",
    "UniverseVersionMissing",
    "BenchmarkVersionMissing",
    "AsOfDateMissing",
    "ScorecardInputBundleHashInvalid",
    "EvidenceClockManifestHashInvalid",
    "DqManifestHashInvalid",
    "PaperShadowReconciliationHashInvalid",
    "FormulaAppendixHashInvalid",
    "StatisticalPreregistrationHashInvalid",
    "ScorecardManifestHashInvalid",
    "ScorecardVerdictHashInvalid",
    "SourceCommitHashInvalid",
    "DerivationCodeHashInvalid",
    "OutputArtifactHashInvalid",
    "QcReviewHashInvalid",
    "MitReviewHashInvalid",
    "QaReviewHashInvalid",
    "NotDerivedFromAtomicFactsOnly",
    "IdempotentReplayNotProven",
    "PaperShadowFillSeparationMissing",
    "BybitLiveExecutionNotProtected",
    "IbkrContactPerformed",
    "ConnectorRuntimeStarted",
    "BrokerFillImportPerformed",
    "ShadowFillGenerated",
    "ReconciliationWriterStarted",
    "ScorecardWriterStarted",
    "DbApplyPerformed",
    "EvidenceClockStarted",
    "SecretContentSerialized",
    "LiveOrTinyLiveAuthorized",
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
    return SCORECARD_DERIVATION.read_text(encoding="utf-8")


def test_stock_etf_scorecard_derivation_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_scorecard_derivation_source_keeps_contract_surface() -> None:
    source = _source()

    for token in REQUIRED_TYPE_TOKENS:
        assert token in source
    for field in REQUIRED_FIELDS:
        assert field in source
    for blocker in REQUIRED_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source

    assert "contract_id: String::new()" in source
    assert "source_version: 0" in source
    assert "asset_lane: AssetLane::CryptoPerp" in source
    assert "broker: Broker::Bybit" in source
    assert "environment: BrokerEnvironment::LiveReservedDenied" in source
    assert "derived_from_atomic_facts_only: false" in source
    assert "idempotent_replay_proven: false" in source
    assert "paper_and_shadow_fills_separate: false" in source
    assert "bybit_live_execution_unchanged: false" in source
    assert "sealed: false" in source
    assert "accepted: blockers.is_empty()" in source


def test_stock_etf_scorecard_derivation_source_keeps_accepted_sealed_shape() -> None:
    source = _source()

    assert "contract_id: STOCK_ETF_SCORECARD_DERIVATION_CONTRACT_ID.to_string()" in source
    assert "source_version: 1" in source
    assert "asset_lane: AssetLane::StockEtfCash" in source
    assert "broker: Broker::Ibkr" in source
    assert "environment: BrokerEnvironment::Paper" in source
    assert "derived_from_atomic_facts_only: true" in source
    assert "idempotent_replay_proven: true" in source
    assert "paper_and_shadow_fills_separate: true" in source
    assert "bybit_live_execution_unchanged: true" in source
    assert "ibkr_contact_performed: false" in source
    assert "connector_runtime_started: false" in source
    assert "broker_fill_import_performed: false" in source
    assert "shadow_fill_generated: false" in source
    assert "reconciliation_writer_started: false" in source
    assert "scorecard_writer_started: false" in source
    assert "db_apply_performed: false" in source
    assert "evidence_clock_started: false" in source
    assert "secret_content_serialized: false" in source
    assert "live_or_tiny_live_authorized: false" in source
    assert "sealed: true" in source


def test_stock_etf_scorecard_derivation_fixture_excludes_writer_live_and_authority_crosswire() -> None:
    source = _source()
    accepted_fixture = source.split("pub fn accepted_fixture() -> Self", 1)[1].split(
        "pub fn validate(&self)",
        1,
    )[0]
    default_impl = source.split("impl Default for StockEtfScorecardDerivationV1", 1)[1].split(
        "impl StockEtfScorecardDerivationV1",
        1,
    )[0]

    for forbidden in (
        "ibkr_contact_performed: true",
        "connector_runtime_started: true",
        "broker_fill_import_performed: true",
        "shadow_fill_generated: true",
        "reconciliation_writer_started: true",
        "scorecard_writer_started: true",
        "db_apply_performed: true",
        "evidence_clock_started: true",
        "secret_content_serialized: true",
        "live_or_tiny_live_authorized: true",
    ):
        assert forbidden not in accepted_fixture

    for fail_closed in (
        "derived_from_atomic_facts_only: false",
        "idempotent_replay_proven: false",
        "paper_and_shadow_fills_separate: false",
        "bybit_live_execution_unchanged: false",
        "sealed: false",
    ):
        assert fail_closed in default_impl


def test_stock_etf_scorecard_derivation_source_keeps_id_and_hash_validation() -> None:
    source = _source()

    assert "self.contract_id.trim().is_empty()" in source
    assert "self.contract_id != STOCK_ETF_SCORECARD_DERIVATION_CONTRACT_ID" in source
    assert "self.source_version != 1" in source
    assert "self.asset_lane != AssetLane::StockEtfCash" in source
    assert "self.broker != Broker::Ibkr" in source
    assert "self.environment != BrokerEnvironment::Paper" in source
    assert "candidate.derivation_run_id.trim().is_empty()" in source
    assert "candidate.strategy_id.trim().is_empty()" in source
    assert "candidate.universe_version.trim().is_empty()" in source
    assert "candidate.benchmark_version.trim().is_empty()" in source
    assert "candidate.as_of_date.trim().is_empty()" in source
    assert "!is_sha256_hex(&candidate.scorecard_input_bundle_hash)" in source
    assert "!is_sha256_hex(&candidate.evidence_clock_manifest_hash)" in source
    assert "!is_sha256_hex(&candidate.dq_manifest_hash)" in source
    assert "!is_sha256_hex(&candidate.paper_shadow_reconciliation_hash)" in source
    assert "!is_sha256_hex(&candidate.formula_appendix_hash)" in source
    assert "!is_sha256_hex(&candidate.statistical_preregistration_hash)" in source
    assert "!is_sha256_hex(&candidate.scorecard_manifest_hash)" in source
    assert "!is_sha256_hex(&candidate.scorecard_verdict_hash)" in source
    assert "!is_sha256_hex(&candidate.source_commit_hash)" in source
    assert "!is_sha256_hex(&candidate.derivation_code_hash)" in source
    assert "!is_sha256_hex(&candidate.output_artifact_hash)" in source
    assert "!is_sha256_hex(&candidate.qc_review_hash)" in source
    assert "!is_sha256_hex(&candidate.mit_review_hash)" in source
    assert "!is_sha256_hex(&candidate.qa_review_hash)" in source


def test_stock_etf_scorecard_derivation_source_keeps_authority_and_writer_gates() -> None:
    source = _source()

    assert "if !candidate.derived_from_atomic_facts_only" in source
    assert "if !candidate.idempotent_replay_proven" in source
    assert "if !candidate.paper_and_shadow_fills_separate" in source
    assert "if !candidate.bybit_live_execution_unchanged" in source
    assert "if candidate.ibkr_contact_performed" in source
    assert "if candidate.connector_runtime_started" in source
    assert "if candidate.broker_fill_import_performed" in source
    assert "if candidate.shadow_fill_generated" in source
    assert "if candidate.reconciliation_writer_started" in source
    assert "if candidate.scorecard_writer_started" in source
    assert "if candidate.db_apply_performed" in source
    assert "if candidate.evidence_clock_started" in source
    assert "if candidate.secret_content_serialized" in source
    assert "if candidate.live_or_tiny_live_authorized" in source
    assert "if !candidate.sealed" in source


def test_stock_etf_scorecard_derivation_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{SCORECARD_DERIVATION}: contains forbidden token {token!r}")

    assert violations == []
