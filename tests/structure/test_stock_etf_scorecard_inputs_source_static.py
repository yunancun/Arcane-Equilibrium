from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCORECARD_INPUTS = ROOT / "rust/openclaw_types/src/stock_etf_scorecard_inputs.rs"
SCORECARD_COMPONENTS = (
    ROOT / "rust/openclaw_types/src/stock_etf_scorecard_inputs/components.rs"
)
SCORECARD_BUNDLE = ROOT / "rust/openclaw_types/src/stock_etf_scorecard_inputs/bundle.rs"
MAX_LINES = 800

REQUIRED_CONTRACT_TOKENS = {
    "BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID",
    '"broker_account_portfolio_cash_ledger_v1"',
    "STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID",
    '"cost_model_version_v1"',
    "STOCK_ETF_BENCHMARK_VERSIONS_CONTRACT_ID",
    '"benchmark_versions_v1"',
    "STOCK_SHADOW_FILL_MODEL_CONTRACT_ID",
    '"stock_shadow_fill_model_v1"',
    "STOCK_ETF_STORAGE_CAPACITY_CONTRACT_ID",
    '"stock_etf_storage_capacity_v1"',
    "STOCK_ETF_STORAGE_MAX_UNIVERSE_SIZE: u32 = 1_000",
    "STOCK_ETF_STORAGE_MAX_ROWS_PER_DAY_ESTIMATE: u64 = 5_000_000",
    "STOCK_ETF_STORAGE_MIN_RAW_PAYLOAD_HASH_RETENTION_DAYS: u32 = 365",
    "STOCK_ETF_STORAGE_MAX_COMPRESSED_RETENTION_DAYS: u32 = 3_650",
    "STOCK_ETF_STORAGE_MAX_INDEX_BUDGET_MB: u32 = 8_192",
    "STOCK_ETF_STORAGE_MAX_QUERY_SLO_MS: u32 = 5_000",
    'STOCK_ETF_STORAGE_ARCHIVE_PATH_PREFIX: &str = "evidence/stock_etf_cash/"',
}
REQUIRED_COMPONENT_TYPES = {
    "pub enum StockEtfOrderSide",
    "pub struct BrokerAccountPortfolioCashLedgerV1",
    "impl BrokerAccountPortfolioCashLedgerV1",
    "pub struct StockEtfCostModelVersionV1",
    "impl StockEtfCostModelVersionV1",
    "pub struct StockEtfBenchmarkVersionV1",
    "impl StockEtfBenchmarkVersionV1",
    "pub struct StockShadowFillModelV1",
    "impl StockShadowFillModelV1",
    "pub struct StockEtfStorageCapacityV1",
    "impl StockEtfStorageCapacityV1",
    "fn is_safe_stock_etf_archive_path(path: &str) -> bool",
}
REQUIRED_BUNDLE_TOKENS = {
    "pub struct StockEtfScorecardInputBundleV1",
    "impl Default for StockEtfScorecardInputBundleV1",
    "impl StockEtfScorecardInputBundleV1",
    "pub fn accepted_fixture() -> Self",
    "pub fn validate(&self) -> StockEtfScorecardInputVerdict<StockEtfScorecardInputBlocker>",
    "STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID",
}
REQUIRED_BLOCKERS = {
    "CashLedgerRejected",
    "CostModelRejected",
    "BenchmarkRejected",
    "ShadowFillModelRejected",
    "StorageCapacityRejected",
    "ReadonlyProbeResultImportRequestContractIdMismatch",
    "ReadonlyProbeResultImportRequestHashInvalid",
    "MarketDataProvenanceContractHashInvalid",
    "ReferenceDataSourcesContractHashInvalid",
    "RiskPolicyContractHashInvalid",
    "AtomicFactInputHashInvalid",
    "SourceCommitMissing",
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


def _parent() -> str:
    return SCORECARD_INPUTS.read_text(encoding="utf-8")


def _components() -> str:
    return SCORECARD_COMPONENTS.read_text(encoding="utf-8")


def _bundle() -> str:
    return SCORECARD_BUNDLE.read_text(encoding="utf-8")


def test_stock_etf_scorecard_inputs_sources_stay_below_governance_cap() -> None:
    assert len(_parent().splitlines()) <= MAX_LINES
    assert len(_components().splitlines()) <= MAX_LINES
    assert len(_bundle().splitlines()) <= MAX_LINES


def test_stock_etf_scorecard_inputs_parent_keeps_contracts_and_blockers() -> None:
    source = _parent()

    for token in REQUIRED_CONTRACT_TOKENS:
        assert token in source
    for blocker in REQUIRED_BLOCKERS:
        assert blocker in source

    assert "mod bundle;" in source
    assert "mod components;" in source
    assert "pub use bundle::StockEtfScorecardInputBundleV1;" in source
    assert "pub use components::" in source
    assert "accepted: blockers.is_empty()" in source


def test_stock_etf_scorecard_inputs_components_keep_atomic_fact_validators() -> None:
    source = _components()

    for token in REQUIRED_COMPONENT_TYPES:
        assert token in source

    assert "asset_lane: AssetLane::CryptoPerp" in source
    assert "broker: Broker::Bybit" in source
    assert "environment: BrokerEnvironment::LiveReservedDenied" in source
    assert "asset_lane: AssetLane::StockEtfCash" in source
    assert "broker: Broker::Ibkr" in source
    assert "environment: BrokerEnvironment::Paper" in source
    assert "BrokerEnvironment::ReadOnly | BrokerEnvironment::Paper" in source
    assert "!is_sha256_hex(&self.account_fingerprint_hash)" in source
    assert "!is_sha256_hex(&self.account_snapshot_hash)" in source
    assert "!is_sha256_hex(&self.portfolio_positions_hash)" in source
    assert "self.currency.trim().is_empty()" in source
    assert "self.as_of_ms == 0" in source
    assert "!is_sha256_hex(&self.source_report_hash)" in source
    assert "self.conservative_fill_penalty_bps == 0" in source
    assert "self.benchmark_id.trim().is_empty()" in source


def test_stock_etf_scorecard_inputs_components_keep_shadow_fill_and_capacity_gates() -> None:
    source = _components()

    assert "side: StockEtfOrderSide::Unknown" in source
    assert "side: StockEtfOrderSide::Buy" in source
    assert "self.side == StockEtfOrderSide::Unknown" in source
    assert "self.intended_notional_minor_units == 0" in source
    assert "self.market_session_id.trim().is_empty()" in source
    assert "!is_sha256_hex(&self.quote_or_bar_source_hash)" in source
    assert "self.rejection_reason.trim().is_empty() && self.conservative_fill_price_micros == 0" in source
    assert "!self.synthetic_shadow" in source
    assert "self.broker_paper_fill_linked" in source
    assert "self.live_fill_linked" in source
    assert "self.universe_size > STOCK_ETF_STORAGE_MAX_UNIVERSE_SIZE" in source
    assert "self.rows_per_day_estimate > STOCK_ETF_STORAGE_MAX_ROWS_PER_DAY_ESTIMATE" in source
    assert "STOCK_ETF_STORAGE_MIN_RAW_PAYLOAD_HASH_RETENTION_DAYS" in source
    assert "self.compressed_retention_days < self.raw_payload_hash_retention_days" in source
    assert "self.compressed_retention_days > STOCK_ETF_STORAGE_MAX_COMPRESSED_RETENTION_DAYS" in source
    assert "self.index_budget_mb > STOCK_ETF_STORAGE_MAX_INDEX_BUDGET_MB" in source
    assert "self.query_slo_ms > STOCK_ETF_STORAGE_MAX_QUERY_SLO_MS" in source
    assert "!is_safe_stock_etf_archive_path(&self.archive_path)" in source
    assert "!is_sha256_hex(&self.capacity_plan_hash)" in source
    assert "!self.capacity_breach_blocks_evidence_clock" in source
    assert "trimmed.starts_with(STOCK_ETF_STORAGE_ARCHIVE_PATH_PREFIX)" in source
    assert "!trimmed.starts_with('/')" in source
    assert '!trimmed.contains("..")' in source
    assert '!trimmed.contains("//")' in source


def test_stock_etf_scorecard_inputs_bundle_keeps_derived_only_boundary() -> None:
    source = _bundle()

    for token in REQUIRED_BUNDLE_TOKENS:
        assert token in source

    assert "cash_ledger: BrokerAccountPortfolioCashLedgerV1::accepted_fixture()" in source
    assert "cost_model: StockEtfCostModelVersionV1::accepted_fixture()" in source
    assert "benchmark: StockEtfBenchmarkVersionV1::accepted_fixture()" in source
    assert "shadow_fill_model: StockShadowFillModelV1::accepted_fill_fixture()" in source
    assert "storage_capacity: StockEtfStorageCapacityV1::accepted_fixture()" in source
    assert "readonly_probe_result_import_request_contract_id:" in source
    assert "STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID.to_string()" in source
    assert "scorecard_is_derived_only: true" in source
    assert "paper_and_shadow_fills_separate: true" in source
    assert "live_fill_claimed: false" in source
    assert "bybit_live_execution_unchanged: true" in source
    assert "ibkr_contact_performed: false" in source
    assert "connector_runtime_started: false" in source
    assert "broker_fill_import_performed: false" in source
    assert "scorecard_writer_started: false" in source
    assert "db_apply_performed: false" in source
    assert "evidence_clock_started: false" in source
    assert "secret_content_serialized: false" in source
    assert "live_or_tiny_live_authorized: false" in source


def test_stock_etf_scorecard_inputs_bundle_keeps_cross_contract_and_side_effect_gates() -> None:
    source = _bundle()

    assert "!self.cash_ledger.validate().accepted" in source
    assert "!self.cost_model.validate().accepted" in source
    assert "!self.benchmark.validate().accepted" in source
    assert "!self.shadow_fill_model.validate().accepted" in source
    assert "!self.storage_capacity.validate().accepted" in source
    assert "self.readonly_probe_result_import_request_contract_id" in source
    assert "!= STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID" in source
    assert "!is_sha256_hex(&self.readonly_probe_result_import_request_hash)" in source
    assert "!is_sha256_hex(&self.market_data_provenance_contract_hash)" in source
    assert "!is_sha256_hex(&self.reference_data_sources_contract_hash)" in source
    assert "!is_sha256_hex(&self.risk_policy_contract_hash)" in source
    assert "!is_sha256_hex(&self.atomic_fact_input_hash)" in source
    assert "self.source_commit.trim().is_empty()" in source
    assert "!self.scorecard_is_derived_only" in source
    assert "!self.paper_and_shadow_fills_separate" in source
    assert "self.live_fill_claimed" in source
    assert "!self.bybit_live_execution_unchanged" in source
    assert "self.ibkr_contact_performed" in source
    assert "self.connector_runtime_started" in source
    assert "self.broker_fill_import_performed" in source
    assert "self.scorecard_writer_started" in source
    assert "self.db_apply_performed" in source
    assert "self.evidence_clock_started" in source
    assert "self.secret_content_serialized" in source
    assert "self.live_or_tiny_live_authorized" in source


def test_stock_etf_scorecard_inputs_sources_have_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    violations = []

    for path, source in (
        (SCORECARD_INPUTS, _parent()),
        (SCORECARD_COMPONENTS, _components()),
        (SCORECARD_BUNDLE, _bundle()),
    ):
        for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
            if token in source:
                violations.append(f"{path}: contains forbidden token {token!r}")

    assert violations == []
