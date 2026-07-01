from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PHASE3_PARENT = ROOT / "rust/openclaw_types/src/stock_etf_phase3_evidence.rs"
PHASE3_MARKET_DATA = (
    ROOT / "rust/openclaw_types/src/stock_etf_phase3_evidence/market_data.rs"
)
MAX_PARENT_LINES = 800
MAX_MARKET_DATA_LINES = 500

PARENT_SURFACE_TOKENS = {
    'STOCK_ETF_COLLECTOR_RUN_CONTRACT_ID: &str = "stock_etf_collector_run_v1"',
    'STOCK_ETF_DQ_MANIFEST_CONTRACT_ID: &str = "stock_etf_dq_manifest_v1"',
    'STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID: &str = "stock_etf_evidence_clock_v1"',
    'STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID: &str = "stock_market_data_provenance_v1"',
    "STOCK_ETF_COLLECTOR_MIN_GREEN_TRADING_DAYS: u16 = 5",
    "mod market_data;",
    "pub use market_data::{",
    "StockEtfAdjustmentMarker",
    "StockEtfFrozenEvidenceInputsV1",
    "StockMarketDataProvenanceV1",
    "pub struct StockEtfCollectorRunV1",
    "impl Default for StockEtfCollectorRunV1",
    "pub fn source_fixture() -> Self",
    "pub fn validate(&self) -> StockEtfPhase3Verdict<StockEtfPhase3Blocker>",
    "pub struct StockEtfDailyDqManifestV1",
    "impl Default for StockEtfDailyDqManifestV1",
    "pub fn pass_fixture() -> Self",
    "pub fn validates_shape(&self) -> StockEtfPhase3Verdict<StockEtfPhase3Blocker>",
    "pub fn passes_day_quality(&self) -> bool",
    "pub enum StockEtfEvidenceClockStatus",
    "pub struct StockEtfEvidenceClockDayV1",
    "impl Default for StockEtfEvidenceClockDayV1",
    "pub fn pass_day_fixture() -> Self",
    "pub struct StockEtfPhase3Verdict",
    "pub enum StockEtfPhase3Blocker",
}
MARKET_DATA_SURFACE_TOKENS = {
    "pub enum StockEtfAdjustmentMarker",
    "pub struct StockMarketDataProvenanceV1",
    "impl Default for StockMarketDataProvenanceV1",
    "impl StockMarketDataProvenanceV1",
    "pub fn source_fixture() -> Self",
    "pub fn validate(&self) -> StockEtfPhase3Verdict<StockEtfPhase3Blocker>",
    "pub struct StockEtfFrozenEvidenceInputsV1",
    "impl Default for StockEtfFrozenEvidenceInputsV1",
    "impl StockEtfFrozenEvidenceInputsV1",
    "is_sha256_hex",
}
COLLECTOR_FIELDS = {
    "collector_run_id",
    "trading_day",
    "pit_universe_contract_id",
    "pit_universe_contract_hash",
    "market_data_provenance_contract_id",
    "market_data_provenance_contract_hash",
    "reference_data_sources_contract_id",
    "reference_data_sources_contract_hash",
    "storage_capacity_contract_id",
    "storage_capacity_contract_hash",
    "expected_trading_sessions",
    "completed_trading_sessions",
    "gap_report_hash",
    "dq_manifest_hash",
    "replay_manifest_hash",
    "source_artifact_hash",
    "market_data_ingestion_started",
    "evidence_writer_started",
    "scorecard_writer_started",
    "db_apply_performed",
}
DQ_FIELDS = {
    "collector_run_id",
    "market_data_provenance_contract_id",
    "market_data_provenance_contract_hash",
    "dq_writer_started",
    "evidence_clock_started",
    "calendar_aware_coverage_bps",
    "symbol_completeness_bps",
    "latency_dq_passed",
    "quarantine_manifest_hash",
    "market_data_provenance_accepted",
    "scorecard_regeneration_passed",
    "atomic_fact_input_hash",
}
EVIDENCE_CLOCK_FIELDS = {
    "collector_run_contract_id",
    "collector_run_contract_hash",
    "dq_manifest_contract_id",
    "dq_manifest_contract_hash",
    "market_data_provenance_contract_hash",
    "scorecard_input_bundle_hash",
    "checker_contacted_ibkr",
    "checker_started_connector_runtime",
    "checker_started_evidence_clock",
    "checker_wrote_scorecard",
    "checker_applied_db",
    "ibkr_readonly_paper_connector_green_5d",
    "shadow_collector_green_5d",
    "frozen_inputs",
    "dq_manifest",
}
MARKET_DATA_FIELDS = {
    "source_vendor_or_broker",
    "entitlement_tier",
    "raw_payload_hash",
    "received_at_ms",
    "exchange_time_ms",
    "adjustment_marker",
    "corporate_action_adjustment_version_hash",
    "symbol",
    "instrument_identity_hash",
    "calendar_session_id",
    "source_artifact_hash",
    "bybit_live_execution_unchanged",
    "ibkr_contact_performed",
    "connector_runtime_started",
    "secret_content_serialized",
    "live_or_tiny_live_authorized",
}
FROZEN_INPUT_FIELDS = {
    "universe_hash",
    "benchmark_hash",
    "cost_model_hash",
    "strategy_hypothesis_hash",
    "reference_data_sources_contract_hash",
    "corporate_action_fx_fee_asof_ms",
    "paper_shadow_divergence_threshold_hash",
    "gui_evidence_view_available",
    "daily_scorecard_regeneration_passed",
}
REQUIRED_BLOCKERS = {
    "CollectorRunContractIdMismatch",
    "CollectorRunVersionMismatch",
    "CollectorRunWrongAssetLane",
    "CollectorRunWrongBroker",
    "CollectorRunEnvironmentDenied",
    "CollectorRunIdMissing",
    "CollectorTradingDayMissing",
    "CollectorPitUniverseContractMismatch",
    "CollectorPitUniverseHashInvalid",
    "CollectorMarketDataProvenanceContractMismatch",
    "CollectorMarketDataProvenanceHashInvalid",
    "CollectorReferenceDataSourcesContractMismatch",
    "CollectorReferenceDataSourcesHashInvalid",
    "CollectorStorageCapacityContractMismatch",
    "CollectorStorageCapacityHashInvalid",
    "CollectorExpectedSessionsTooSmall",
    "CollectorCompletedSessionsMissing",
    "CollectorGapReportHashInvalid",
    "CollectorDqManifestHashInvalid",
    "CollectorReplayManifestHashInvalid",
    "CollectorSourceArtifactHashInvalid",
    "CollectorMarketDataIngestionStarted",
    "CollectorEvidenceWriterStarted",
    "MarketDataProvenanceContractIdMismatch",
    "MarketDataProvenanceVersionMismatch",
    "MarketDataProvenanceWrongAssetLane",
    "MarketDataProvenanceWrongBroker",
    "MarketDataProvenanceEnvironmentDenied",
    "SourceMissing",
    "EntitlementTierMissing",
    "RawPayloadHashInvalid",
    "MarketDataTimestampMissing",
    "AdjustmentMarkerUnknown",
    "CorporateActionVersionHashInvalid",
    "SymbolMissing",
    "InstrumentIdentityHashInvalid",
    "CalendarSessionMissing",
    "SourceArtifactHashInvalid",
    "BybitLiveExecutionNotProtected",
    "IbkrContactPerformed",
    "ConnectorRuntimeStarted",
    "SecretContentSerialized",
    "LiveOrTinyLiveAuthorized",
    "UniverseHashInvalid",
    "BenchmarkHashInvalid",
    "CostModelHashInvalid",
    "StrategyHypothesisHashInvalid",
    "ReferenceDataSourcesHashInvalid",
    "CorporateActionFxFeeAsOfMissing",
    "DivergenceThresholdHashInvalid",
    "GuiEvidenceViewMissing",
    "ScorecardRegenerationMissing",
    "DqManifestContractIdMismatch",
    "DqManifestVersionMismatch",
    "DqManifestWrongAssetLane",
    "DqManifestWrongBroker",
    "DqManifestEnvironmentDenied",
    "DqManifestCollectorRunIdMissing",
    "DqManifestMarketDataProvenanceContractMismatch",
    "DqManifestMarketDataProvenanceHashInvalid",
    "DqManifestSourceArtifactHashInvalid",
    "DqManifestMarketDataIngestionStarted",
    "DqManifestWriterStarted",
    "DqManifestEvidenceClockStarted",
    "TradingDayMissing",
    "CoverageBpsInvalid",
    "QuarantineManifestHashInvalid",
    "AtomicFactInputHashInvalid",
    "IbkrConnectorNotGreenFiveDays",
    "ShadowCollectorNotGreenFiveDays",
    "EvidenceClockContractIdMismatch",
    "EvidenceClockVersionMismatch",
    "EvidenceClockWrongAssetLane",
    "EvidenceClockWrongBroker",
    "EvidenceClockEnvironmentDenied",
    "EvidenceClockCollectorRunContractMismatch",
    "EvidenceClockCollectorRunHashInvalid",
    "EvidenceClockDqManifestContractMismatch",
    "EvidenceClockDqManifestHashInvalid",
    "EvidenceClockSourceArtifactHashInvalid",
    "EvidenceClockMarketDataProvenanceHashInvalid",
    "EvidenceClockScorecardInputHashInvalid",
    "EvidenceClockRuntimeStarted",
    "ScorecardWriterStarted",
    "DbApplyPerformed",
    "FrozenInputsRejected",
    "DqManifestShapeRejected",
    "PassDayQualityRejected",
    "QuarantinedDayWithoutDqFailure",
    "WindowCompleteNotSourceAuthorized",
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
    return PHASE3_PARENT.read_text(encoding="utf-8")


def _market_data() -> str:
    return PHASE3_MARKET_DATA.read_text(encoding="utf-8")


def _combined() -> str:
    return f"{_parent()}\n{_market_data()}"


def test_stock_etf_phase3_evidence_sources_stay_below_governance_caps() -> None:
    assert len(_parent().splitlines()) <= MAX_PARENT_LINES
    assert len(_market_data().splitlines()) <= MAX_MARKET_DATA_LINES


def test_stock_etf_phase3_evidence_parent_keeps_contract_surface() -> None:
    parent = _parent()

    for token in PARENT_SURFACE_TOKENS | COLLECTOR_FIELDS | DQ_FIELDS | EVIDENCE_CLOCK_FIELDS:
        assert token in parent
    for blocker in REQUIRED_BLOCKERS:
        assert f"Blocker::{blocker}" in parent or blocker in parent

    assert "accepted: blockers.is_empty()" in parent


def test_stock_etf_phase3_evidence_market_data_child_keeps_contract_surface() -> None:
    child = _market_data()

    for token in MARKET_DATA_SURFACE_TOKENS | MARKET_DATA_FIELDS | FROZEN_INPUT_FIELDS:
        assert token in child
    assert "StockEtfAdjustmentMarker::Unknown" in child
    assert "StockEtfAdjustmentMarker::Adjusted" in child
    assert "StockEtfPhase3Verdict::new(blockers)" in child


def test_stock_etf_phase3_collector_source_keeps_fail_closed_and_fixture_boundaries() -> None:
    parent = _parent()

    assert "contract_id: String::new()" in parent
    assert "source_version: 0" in parent
    assert "asset_lane: AssetLane::CryptoPerp" in parent
    assert "broker: Broker::Bybit" in parent
    assert "environment: BrokerEnvironment::LiveReservedDenied" in parent
    assert "market_data_ingestion_started: false" in parent
    assert "evidence_writer_started: false" in parent
    assert "scorecard_writer_started: false" in parent
    assert "db_apply_performed: false" in parent
    assert "live_or_tiny_live_authorized: false" in parent

    assert "contract_id: STOCK_ETF_COLLECTOR_RUN_CONTRACT_ID.to_string()" in parent
    assert 'collector_run_id: "stock-etf-collector-run-2026-03-01-001".to_string()' in parent
    assert 'trading_day: "2026-03-01".to_string()' in parent
    assert "pit_universe_contract_id: STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID.to_string()" in parent
    assert (
        "market_data_provenance_contract_id: STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID"
        in parent
    )
    assert (
        "reference_data_sources_contract_id: STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID"
        in parent
    )
    assert "storage_capacity_contract_id: STOCK_ETF_STORAGE_CAPACITY_CONTRACT_ID.to_string()" in parent
    assert "expected_trading_sessions: STOCK_ETF_COLLECTOR_MIN_GREEN_TRADING_DAYS" in parent
    assert "completed_trading_sessions: STOCK_ETF_COLLECTOR_MIN_GREEN_TRADING_DAYS" in parent
    assert "bybit_live_execution_unchanged: true" in parent


def test_stock_etf_phase3_collector_fixture_excludes_runtime_writer_secret_and_authority_crosswire() -> None:
    parent = _parent()
    fixture = parent.split("impl StockEtfCollectorRunV1", 1)[1].split(
        "pub fn validate(&self)",
        1,
    )[0]
    default_impl = parent.split("impl Default for StockEtfCollectorRunV1", 1)[1].split(
        "impl StockEtfCollectorRunV1",
        1,
    )[0]

    for forbidden in (
        "environment: BrokerEnvironment::LiveReservedDenied",
        "expected_trading_sessions: 0",
        "completed_trading_sessions: 0",
        "bybit_live_execution_unchanged: false",
        "ibkr_contact_performed: true",
        "connector_runtime_started: true",
        "market_data_ingestion_started: true",
        "evidence_writer_started: true",
        "scorecard_writer_started: true",
        "db_apply_performed: true",
        "secret_content_serialized: true",
        "live_or_tiny_live_authorized: true",
    ):
        assert forbidden not in fixture

    for fail_closed in (
        "environment: BrokerEnvironment::LiveReservedDenied",
        "expected_trading_sessions: 0",
        "completed_trading_sessions: 0",
        "bybit_live_execution_unchanged: false",
        "ibkr_contact_performed: false",
        "connector_runtime_started: false",
        "market_data_ingestion_started: false",
        "evidence_writer_started: false",
        "scorecard_writer_started: false",
        "db_apply_performed: false",
        "secret_content_serialized: false",
        "live_or_tiny_live_authorized: false",
    ):
        assert fail_closed in default_impl


def test_stock_etf_phase3_collector_source_keeps_validation_matrix() -> None:
    parent = _parent()

    assert "self.contract_id != STOCK_ETF_COLLECTOR_RUN_CONTRACT_ID" in parent
    assert "self.source_version != 1" in parent
    assert "self.asset_lane != AssetLane::StockEtfCash" in parent
    assert "self.broker != Broker::Ibkr" in parent
    assert "BrokerEnvironment::ReadOnly | BrokerEnvironment::Paper | BrokerEnvironment::Shadow" in parent
    assert "self.collector_run_id.trim().is_empty()" in parent
    assert "self.trading_day.trim().is_empty()" in parent
    assert "self.pit_universe_contract_id != STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID" in parent
    assert "self.market_data_provenance_contract_id != STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID" in parent
    assert "self.reference_data_sources_contract_id != STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID" in parent
    assert "self.storage_capacity_contract_id != STOCK_ETF_STORAGE_CAPACITY_CONTRACT_ID" in parent
    assert "self.expected_trading_sessions < STOCK_ETF_COLLECTOR_MIN_GREEN_TRADING_DAYS" in parent
    assert "self.completed_trading_sessions < self.expected_trading_sessions" in parent
    for hash_field in (
        "pit_universe_contract_hash",
        "market_data_provenance_contract_hash",
        "reference_data_sources_contract_hash",
        "storage_capacity_contract_hash",
        "gap_report_hash",
        "dq_manifest_hash",
        "replay_manifest_hash",
        "source_artifact_hash",
    ):
        assert f"!is_sha256_hex(&self.{hash_field})" in parent
    for flag in (
        "ibkr_contact_performed",
        "connector_runtime_started",
        "market_data_ingestion_started",
        "evidence_writer_started",
        "scorecard_writer_started",
        "db_apply_performed",
        "secret_content_serialized",
        "live_or_tiny_live_authorized",
    ):
        assert f"self.{flag}" in parent


def test_stock_etf_phase3_dq_manifest_source_keeps_shape_and_quality_split() -> None:
    parent = _parent()

    assert "contract_id: STOCK_ETF_DQ_MANIFEST_CONTRACT_ID.to_string()" in parent
    assert 'collector_run_id: "stock-etf-collector-run-2026-03-01".to_string()' in parent
    assert "calendar_aware_coverage_bps: 10_000" in parent
    assert "symbol_completeness_bps: 10_000" in parent
    assert "latency_dq_passed: true" in parent
    assert "market_data_provenance_accepted: true" in parent
    assert "scorecard_regeneration_passed: true" in parent
    assert "self.contract_id != STOCK_ETF_DQ_MANIFEST_CONTRACT_ID" in parent
    assert "self.market_data_provenance_contract_id != STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID" in parent
    assert "self.dq_writer_started" in parent
    assert "self.evidence_clock_started" in parent
    assert "self.calendar_aware_coverage_bps > 10_000 || self.symbol_completeness_bps > 10_000" in parent
    assert "self.validates_shape().accepted" in parent
    assert "self.calendar_aware_coverage_bps == 10_000" in parent
    assert "self.symbol_completeness_bps == 10_000" in parent
    assert "self.latency_dq_passed" in parent
    assert "self.market_data_provenance_accepted" in parent
    assert "self.scorecard_regeneration_passed" in parent


def test_stock_etf_phase3_dq_manifest_fixture_excludes_runtime_writer_secret_and_authority_crosswire() -> None:
    parent = _parent()
    fixture = parent.split("impl StockEtfDailyDqManifestV1", 1)[1].split(
        "pub fn validates_shape(&self)",
        1,
    )[0]
    default_impl = parent.split("impl Default for StockEtfDailyDqManifestV1", 1)[1].split(
        "impl StockEtfDailyDqManifestV1",
        1,
    )[0]

    for forbidden in (
        "environment: BrokerEnvironment::LiveReservedDenied",
        "bybit_live_execution_unchanged: false",
        "ibkr_contact_performed: true",
        "connector_runtime_started: true",
        "market_data_ingestion_started: true",
        "dq_writer_started: true",
        "evidence_clock_started: true",
        "scorecard_writer_started: true",
        "db_apply_performed: true",
        "secret_content_serialized: true",
        "live_or_tiny_live_authorized: true",
        "calendar_aware_coverage_bps: 0",
        "symbol_completeness_bps: 0",
    ):
        assert forbidden not in fixture

    for fail_closed in (
        "environment: BrokerEnvironment::LiveReservedDenied",
        "bybit_live_execution_unchanged: false",
        "ibkr_contact_performed: false",
        "connector_runtime_started: false",
        "market_data_ingestion_started: false",
        "dq_writer_started: false",
        "evidence_clock_started: false",
        "scorecard_writer_started: false",
        "db_apply_performed: false",
        "secret_content_serialized: false",
        "live_or_tiny_live_authorized: false",
        "calendar_aware_coverage_bps: 0",
        "symbol_completeness_bps: 0",
    ):
        assert fail_closed in default_impl


def test_stock_etf_phase3_evidence_clock_source_keeps_gate_and_status_rules() -> None:
    parent = _parent()

    assert "contract_id: STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID.to_string()" in parent
    assert "status: StockEtfEvidenceClockStatus::PassDay" in parent
    assert "ibkr_readonly_paper_connector_green_5d: true" in parent
    assert "shadow_collector_green_5d: true" in parent
    assert "frozen_inputs: StockEtfFrozenEvidenceInputsV1::source_fixture()" in parent
    assert "dq_manifest: StockEtfDailyDqManifestV1::pass_fixture()" in parent
    assert "self.contract_id != STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID" in parent
    assert "self.collector_run_contract_id != STOCK_ETF_COLLECTOR_RUN_CONTRACT_ID" in parent
    assert "self.dq_manifest_contract_id != STOCK_ETF_DQ_MANIFEST_CONTRACT_ID" in parent
    assert "self.checker_contacted_ibkr" in parent
    assert "self.checker_started_connector_runtime" in parent
    assert "self.checker_started_evidence_clock" in parent
    assert "self.checker_wrote_scorecard" in parent
    assert "self.checker_applied_db" in parent
    assert "!self.ibkr_readonly_paper_connector_green_5d" in parent
    assert "!self.shadow_collector_green_5d" in parent
    assert "!self.frozen_inputs.validate().accepted" in parent
    assert "!self.dq_manifest.validates_shape().accepted" in parent
    assert "Status::PassDay" in parent
    assert "Status::QuarantinedDay" in parent
    assert "Status::WindowComplete => blockers.push(Blocker::WindowCompleteNotSourceAuthorized)" in parent
    assert "Status::NotStarted | Status::Blocked => {}" in parent


def test_stock_etf_phase3_evidence_clock_fixture_excludes_runtime_writer_secret_and_authority_crosswire() -> None:
    parent = _parent()
    fixture = parent.split("impl StockEtfEvidenceClockDayV1", 1)[1].split(
        "pub fn validate(&self)",
        1,
    )[0]
    default_impl = parent.split("impl Default for StockEtfEvidenceClockDayV1", 1)[1].split(
        "impl StockEtfEvidenceClockDayV1",
        1,
    )[0]

    for forbidden in (
        "environment: BrokerEnvironment::LiveReservedDenied",
        "bybit_live_execution_unchanged: false",
        "checker_contacted_ibkr: true",
        "checker_started_connector_runtime: true",
        "checker_started_evidence_clock: true",
        "checker_wrote_scorecard: true",
        "checker_applied_db: true",
        "secret_content_serialized: true",
        "live_or_tiny_live_authorized: true",
        "ibkr_readonly_paper_connector_green_5d: false",
        "shadow_collector_green_5d: false",
        "status: StockEtfEvidenceClockStatus::WindowComplete",
    ):
        assert forbidden not in fixture

    for fail_closed in (
        "environment: BrokerEnvironment::LiveReservedDenied",
        "bybit_live_execution_unchanged: false",
        "checker_contacted_ibkr: false",
        "checker_started_connector_runtime: false",
        "checker_started_evidence_clock: false",
        "checker_wrote_scorecard: false",
        "checker_applied_db: false",
        "secret_content_serialized: false",
        "live_or_tiny_live_authorized: false",
        "ibkr_readonly_paper_connector_green_5d: false",
        "shadow_collector_green_5d: false",
        "status: StockEtfEvidenceClockStatus::NotStarted",
    ):
        assert fail_closed in default_impl


def test_stock_etf_market_data_provenance_source_keeps_boundary_and_lineage() -> None:
    child = _market_data()

    assert "contract_id: STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID.to_string()" in child
    assert "asset_lane: AssetLane::StockEtfCash" in child
    assert "broker: Broker::Ibkr" in child
    assert "environment: BrokerEnvironment::Paper" in child
    assert 'source_vendor_or_broker: "ibkr_paper_market_data".to_string()' in child
    assert 'entitlement_tier: "paper_delayed_or_snapshot_fixture".to_string()' in child
    assert "raw_payload_hash: \"a\".repeat(64)" in child
    assert "received_at_ms: 1_772_233_000_000" in child
    assert "exchange_time_ms: 1_772_232_999_000" in child
    assert "adjustment_marker: StockEtfAdjustmentMarker::Adjusted" in child
    assert "corporate_action_adjustment_version_hash: \"b\".repeat(64)" in child
    assert 'symbol: "SPY".to_string()' in child
    assert "instrument_identity_hash: \"c\".repeat(64)" in child
    assert 'calendar_session_id: "XNYS-2026-03-01-regular".to_string()' in child
    assert "self.contract_id != STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID" in child
    assert "self.source_vendor_or_broker.trim().is_empty()" in child
    assert "self.entitlement_tier.trim().is_empty()" in child
    assert "self.received_at_ms == 0 || self.exchange_time_ms == 0" in child
    assert "self.adjustment_marker == StockEtfAdjustmentMarker::Unknown" in child
    assert "self.symbol.trim().is_empty()" in child
    assert "self.calendar_session_id.trim().is_empty()" in child
    assert "self.ibkr_contact_performed" in child
    assert "self.connector_runtime_started" in child
    assert "self.secret_content_serialized" in child
    assert "self.live_or_tiny_live_authorized" in child


def test_stock_etf_market_data_provenance_fixture_excludes_runtime_secret_and_authority_crosswire() -> None:
    child = _market_data()
    fixture = child.split("impl StockMarketDataProvenanceV1", 1)[1].split(
        "pub fn validate(&self)",
        1,
    )[0]
    default_impl = child.split("impl Default for StockMarketDataProvenanceV1", 1)[1].split(
        "impl StockMarketDataProvenanceV1",
        1,
    )[0]

    for forbidden in (
        "environment: BrokerEnvironment::LiveReservedDenied",
        "bybit_live_execution_unchanged: false",
        "ibkr_contact_performed: true",
        "connector_runtime_started: true",
        "secret_content_serialized: true",
        "live_or_tiny_live_authorized: true",
        "adjustment_marker: StockEtfAdjustmentMarker::Unknown",
        "received_at_ms: 0",
        "exchange_time_ms: 0",
    ):
        assert forbidden not in fixture

    for fail_closed in (
        "environment: BrokerEnvironment::LiveReservedDenied",
        "bybit_live_execution_unchanged: false",
        "ibkr_contact_performed: false",
        "connector_runtime_started: false",
        "secret_content_serialized: false",
        "live_or_tiny_live_authorized: false",
        "adjustment_marker: StockEtfAdjustmentMarker::Unknown",
        "received_at_ms: 0",
        "exchange_time_ms: 0",
    ):
        assert fail_closed in default_impl


def test_stock_etf_frozen_inputs_source_keeps_hash_and_display_readiness_checks() -> None:
    child = _market_data()

    assert "universe_hash: \"d\".repeat(64)" in child
    assert "benchmark_hash: \"e\".repeat(64)" in child
    assert "cost_model_hash: \"f\".repeat(64)" in child
    assert "strategy_hypothesis_hash: \"1\".repeat(64)" in child
    assert "reference_data_sources_contract_hash: \"c\".repeat(64)" in child
    assert "corporate_action_fx_fee_asof_ms: 1_772_233_000_000" in child
    assert "paper_shadow_divergence_threshold_hash: \"2\".repeat(64)" in child
    assert "gui_evidence_view_available: true" in child
    assert "daily_scorecard_regeneration_passed: true" in child
    for hash_field in (
        "universe_hash",
        "benchmark_hash",
        "cost_model_hash",
        "strategy_hypothesis_hash",
        "reference_data_sources_contract_hash",
        "paper_shadow_divergence_threshold_hash",
    ):
        assert f"!is_sha256_hex(&self.{hash_field})" in child
    assert "self.corporate_action_fx_fee_asof_ms == 0" in child
    assert "!self.gui_evidence_view_available" in child
    assert "!self.daily_scorecard_regeneration_passed" in child


def test_stock_etf_frozen_inputs_fixture_excludes_missing_readiness_crosswire() -> None:
    child = _market_data()
    fixture = child.split("impl StockEtfFrozenEvidenceInputsV1", 1)[1].split(
        "pub fn validate(&self)",
        1,
    )[0]
    default_impl = child.split("impl Default for StockEtfFrozenEvidenceInputsV1", 1)[1].split(
        "impl StockEtfFrozenEvidenceInputsV1",
        1,
    )[0]

    for forbidden in (
        'universe_hash: String::new()',
        'benchmark_hash: String::new()',
        'cost_model_hash: String::new()',
        'strategy_hypothesis_hash: String::new()',
        'reference_data_sources_contract_hash: String::new()',
        "corporate_action_fx_fee_asof_ms: 0",
        'paper_shadow_divergence_threshold_hash: String::new()',
        "gui_evidence_view_available: false",
        "daily_scorecard_regeneration_passed: false",
    ):
        assert forbidden not in fixture

    for fail_closed in (
        'universe_hash: String::new()',
        'benchmark_hash: String::new()',
        'cost_model_hash: String::new()',
        'strategy_hypothesis_hash: String::new()',
        'reference_data_sources_contract_hash: String::new()',
        "corporate_action_fx_fee_asof_ms: 0",
        'paper_shadow_divergence_threshold_hash: String::new()',
        "gui_evidence_view_available: false",
        "daily_scorecard_regeneration_passed: false",
    ):
        assert fail_closed in default_impl


def test_stock_etf_phase3_sources_have_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    combined = _combined()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in combined:
            violations.append(f"phase3 evidence sources contain forbidden token {token!r}")

    assert violations == []
