from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SHADOW_SIGNAL_REQUEST = ROOT / "rust/openclaw_types/src/stock_etf_shadow_signal_request.rs"
MAX_LINES = 800

REQUIRED_TYPE_TOKENS = {
    "STOCK_ETF_SHADOW_SIGNAL_REQUEST_CONTRACT_ID",
    '"stock_etf_shadow_signal_request_v1"',
    "pub struct StockEtfShadowSignalRequestV1",
    "impl Default for StockEtfShadowSignalRequestV1",
    "impl StockEtfShadowSignalRequestV1",
    "pub fn accepted_fixture() -> Self",
    "pub fn validate(&self) -> StockEtfShadowSignalRequestVerdict",
    "pub struct StockEtfShadowSignalRequestVerdict",
    "pub enum StockEtfShadowSignalRequestBlocker",
    "fn validate_required_fields(",
    "fn validate_boundary_flags(",
}
REQUIRED_FIELDS = {
    "contract_id",
    "source_version",
    "asset_lane",
    "broker",
    "environment",
    "request_method",
    "operation",
    "authority_scope",
    "effect_capable",
    "request_id",
    "evaluation_run_id",
    "shadow_signal_id",
    "evidence_clock_hash",
    "pit_universe_contract_hash",
    "strategy_hypothesis_hash",
    "instrument_identity_hash",
    "market_data_provenance_hash",
    "cost_model_version_hash",
    "asset_lane_events_contract_hash",
    "source_artifact_hash",
    "ibkr_contact_performed",
    "connector_runtime_started",
    "secret_content_serialized",
    "shadow_signal_emitted",
    "shadow_fill_generated",
    "scorecard_writer_started",
    "db_apply_performed",
    "order_routed",
    "bybit_path_reused",
    "live_or_tiny_live_authorized",
    "margin_short_options_cfd_requested",
    "python_direct_broker_write_requested",
}
REQUIRED_BLOCKERS = {
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "WrongAssetLane",
    "WrongBroker",
    "EnvironmentNotShadow",
    "RequestMethodMismatch",
    "OperationMismatch",
    "AuthorityScopeMismatch",
    "EffectCapabilityPresent",
    "RequestIdMissing",
    "EvaluationRunIdMissing",
    "ShadowSignalIdMissing",
    "EvidenceClockHashInvalid",
    "PitUniverseContractHashInvalid",
    "StrategyHypothesisHashInvalid",
    "InstrumentIdentityHashInvalid",
    "MarketDataProvenanceHashInvalid",
    "CostModelVersionHashInvalid",
    "AssetLaneEventsContractHashInvalid",
    "SourceArtifactHashInvalid",
    "IbkrContactPerformed",
    "ConnectorRuntimeStarted",
    "SecretContentSerialized",
    "ShadowSignalEmitted",
    "ShadowFillGenerated",
    "ScorecardWriterStarted",
    "DbApplyPerformed",
    "OrderRouted",
    "BybitPathReused",
    "LiveOrTinyLiveAuthorized",
    "MarginShortOptionsCfdRequested",
    "PythonDirectBrokerWriteRequested",
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
    return SHADOW_SIGNAL_REQUEST.read_text(encoding="utf-8")


def test_stock_etf_shadow_signal_request_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_shadow_signal_request_source_keeps_contract_surface() -> None:
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
    assert "request_method: StockEtfLaneScopedIpcMethod::UnknownDenied" in source
    assert "operation: BrokerOperation::TransferOrAccountWrite" in source
    assert "authority_scope: AuthorityScope::Denied" in source
    assert "effect_capable: false" in source
    assert "accepted: blockers.is_empty()" in source


def test_stock_etf_shadow_signal_request_source_keeps_shadow_only_shape() -> None:
    source = _source()

    assert "contract_id: STOCK_ETF_SHADOW_SIGNAL_REQUEST_CONTRACT_ID.to_string()" in source
    assert "source_version: 1" in source
    assert "asset_lane: AssetLane::StockEtfCash" in source
    assert "broker: Broker::Ibkr" in source
    assert "environment: BrokerEnvironment::Shadow" in source
    assert "request_method: StockEtfLaneScopedIpcMethod::EvaluateShadowSignal" in source
    assert "operation: BrokerOperation::ShadowSignalEmit" in source
    assert "authority_scope: AuthorityScope::ShadowOnly" in source
    assert "effect_capable: false" in source
    assert "..Self::default()" in source


def test_stock_etf_shadow_signal_request_source_keeps_lineage_validation() -> None:
    source = _source()

    assert "self.contract_id != STOCK_ETF_SHADOW_SIGNAL_REQUEST_CONTRACT_ID" in source
    assert "self.source_version != 1" in source
    assert "self.asset_lane != AssetLane::StockEtfCash" in source
    assert "self.broker != Broker::Ibkr" in source
    assert "self.environment != BrokerEnvironment::Shadow" in source
    assert "self.request_method != StockEtfLaneScopedIpcMethod::EvaluateShadowSignal" in source
    assert "self.operation != BrokerOperation::ShadowSignalEmit" in source
    assert "self.authority_scope != AuthorityScope::ShadowOnly" in source
    assert "self.effect_capable" in source
    assert "request.request_id.trim().is_empty()" in source
    assert "request.evaluation_run_id.trim().is_empty()" in source
    assert "request.shadow_signal_id.trim().is_empty()" in source
    assert "!is_sha256_hex(&request.evidence_clock_hash)" in source
    assert "!is_sha256_hex(&request.pit_universe_contract_hash)" in source
    assert "!is_sha256_hex(&request.strategy_hypothesis_hash)" in source
    assert "!is_sha256_hex(&request.instrument_identity_hash)" in source
    assert "!is_sha256_hex(&request.market_data_provenance_hash)" in source
    assert "!is_sha256_hex(&request.cost_model_version_hash)" in source
    assert "!is_sha256_hex(&request.asset_lane_events_contract_hash)" in source
    assert "!is_sha256_hex(&request.source_artifact_hash)" in source


def test_stock_etf_shadow_signal_request_source_keeps_no_side_effect_boundary_flags() -> None:
    source = _source()

    assert "if request.ibkr_contact_performed" in source
    assert "if request.connector_runtime_started" in source
    assert "if request.secret_content_serialized" in source
    assert "if request.shadow_signal_emitted" in source
    assert "if request.shadow_fill_generated" in source
    assert "if request.scorecard_writer_started" in source
    assert "if request.db_apply_performed" in source
    assert "if request.order_routed" in source
    assert "if request.bybit_path_reused" in source
    assert "if request.live_or_tiny_live_authorized" in source
    assert "if request.margin_short_options_cfd_requested" in source
    assert "if request.python_direct_broker_write_requested" in source


def test_stock_etf_shadow_signal_request_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{SHADOW_SIGNAL_REQUEST}: contains forbidden token {token!r}")

    assert violations == []
