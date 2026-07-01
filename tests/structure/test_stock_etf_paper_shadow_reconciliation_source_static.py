from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PAPER_SHADOW_RECONCILIATION = (
    ROOT / "rust/openclaw_types/src/stock_etf_paper_shadow_reconciliation.rs"
)
MAX_LINES = 800

REQUIRED_TYPE_TOKENS = {
    "STOCK_ETF_PAPER_SHADOW_RECONCILIATION_CONTRACT_ID",
    '"stock_etf_paper_shadow_reconciliation_v1"',
    "STOCK_ETF_PAPER_SHADOW_RECONCILIATION_SCOPE",
    '"paper_shadow"',
    "pub struct StockEtfPaperShadowReconciliationV1",
    "impl Default for StockEtfPaperShadowReconciliationV1",
    "impl StockEtfPaperShadowReconciliationV1",
    "pub fn accepted_fixture() -> Self",
    "pub fn validate(&self) -> StockEtfPaperShadowReconciliationVerdict",
    "pub struct StockEtfPaperShadowReconciliationVerdict",
    "pub enum StockEtfPaperShadowReconciliationBlocker",
    "fn validate_required_fields(",
    "fn validate_reconciliation_evidence(",
    "fn validate_boundary_flags(",
}
REQUIRED_FIELDS = {
    "contract_id",
    "source_version",
    "asset_lane",
    "broker",
    "scope",
    "authority_scope",
    "effect_capable",
    "reconciliation_run_id",
    "paper_order_local_id",
    "broker_order_id",
    "execution_id",
    "commission_report_id",
    "shadow_signal_id",
    "lifecycle_contract_hash",
    "event_log_contract_hash",
    "paper_fill_import_request_hash",
    "shadow_signal_request_hash",
    "shadow_fill_model_hash",
    "cost_model_version_hash",
    "market_data_provenance_hash",
    "paper_shadow_divergence_threshold_hash",
    "paper_shadow_link_hash",
    "raw_artifact_hash",
    "redacted_summary_hash",
    "source_artifact_hash",
    "append_only_event_ready",
    "paper_fill_imported",
    "shadow_fill_synthetic",
    "divergence_bps",
    "divergence_threshold_bps",
    "unmatched_paper_fill_count",
    "unmatched_shadow_fill_count",
    "ibkr_contact_performed",
    "connector_runtime_started",
    "secret_content_serialized",
    "fill_import_performed",
    "shadow_fill_generated",
    "reconciliation_writer_started",
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
    "ScopeMismatch",
    "AuthorityScopeMismatch",
    "EffectCapabilityPresent",
    "ReconciliationRunIdMissing",
    "PaperOrderLocalIdMissing",
    "BrokerOrderIdMissing",
    "ExecutionIdMissing",
    "CommissionReportIdMissing",
    "ShadowSignalIdMissing",
    "LifecycleContractHashInvalid",
    "EventLogContractHashInvalid",
    "PaperFillImportRequestHashInvalid",
    "ShadowSignalRequestHashInvalid",
    "ShadowFillModelHashInvalid",
    "CostModelVersionHashInvalid",
    "MarketDataProvenanceHashInvalid",
    "PaperShadowDivergenceThresholdHashInvalid",
    "PaperShadowLinkHashInvalid",
    "RawArtifactHashInvalid",
    "RedactedSummaryHashInvalid",
    "SourceArtifactHashInvalid",
    "AppendOnlyEventNotReady",
    "PaperFillNotImported",
    "ShadowFillNotSynthetic",
    "DivergenceThresholdMissing",
    "DivergenceExceedsThreshold",
    "UnmatchedPaperFillPresent",
    "UnmatchedShadowFillPresent",
    "IbkrContactPerformed",
    "ConnectorRuntimeStarted",
    "SecretContentSerialized",
    "FillImportPerformed",
    "ShadowFillGenerated",
    "ReconciliationWriterStarted",
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
    return PAPER_SHADOW_RECONCILIATION.read_text(encoding="utf-8")


def _default_block(source: str) -> str:
    return source.split("impl Default for StockEtfPaperShadowReconciliationV1", 1)[1].split(
        "impl StockEtfPaperShadowReconciliationV1",
        1,
    )[0]


def _accepted_fixture_block(source: str) -> str:
    return source.split("impl StockEtfPaperShadowReconciliationV1", 1)[1].split(
        "pub fn validate(&self)",
        1,
    )[0]


def test_stock_etf_paper_shadow_reconciliation_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_paper_shadow_reconciliation_source_keeps_contract_surface() -> None:
    source = _source()
    default_block = _default_block(source)

    for token in REQUIRED_TYPE_TOKENS:
        assert token in source
    for field in REQUIRED_FIELDS:
        assert field in source
    for blocker in REQUIRED_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source

    assert "contract_id: String::new()" in default_block
    assert "source_version: 0" in default_block
    assert "asset_lane: AssetLane::CryptoPerp" in default_block
    assert "broker: Broker::Bybit" in default_block
    assert "authority_scope: AuthorityScope::Denied" in default_block
    assert "effect_capable: false" in default_block
    assert "append_only_event_ready: false" in default_block
    assert "paper_fill_imported: false" in default_block
    assert "shadow_fill_synthetic: false" in default_block
    assert "divergence_bps: 0" in default_block
    assert "divergence_threshold_bps: 0" in default_block
    assert "unmatched_paper_fill_count: 0" in default_block
    assert "unmatched_shadow_fill_count: 0" in default_block
    assert "accepted: blockers.is_empty()" in source


def test_stock_etf_paper_shadow_reconciliation_source_keeps_accepted_readonly_shape() -> None:
    source = _accepted_fixture_block(_source())

    assert "contract_id: STOCK_ETF_PAPER_SHADOW_RECONCILIATION_CONTRACT_ID.to_string()" in source
    assert "source_version: 1" in source
    assert "asset_lane: AssetLane::StockEtfCash" in source
    assert "broker: Broker::Ibkr" in source
    assert "scope: STOCK_ETF_PAPER_SHADOW_RECONCILIATION_SCOPE.to_string()" in source
    assert "authority_scope: AuthorityScope::ReadOnly" in source
    assert "effect_capable: false" in source
    assert "append_only_event_ready: true" in source
    assert "paper_fill_imported: true" in source
    assert "shadow_fill_synthetic: true" in source
    assert "divergence_bps: 35" in source
    assert "divergence_threshold_bps: 100" in source
    assert "unmatched_paper_fill_count: 0" in source
    assert "unmatched_shadow_fill_count: 0" in source
    assert "..Self::default()" in source


def test_stock_etf_paper_shadow_reconciliation_fixture_excludes_lineage_evidence_and_runtime_crosswire() -> None:
    source = _source()
    default_block = _default_block(source)
    fixture = _accepted_fixture_block(source)

    for required_default in (
        "asset_lane: AssetLane::CryptoPerp",
        "broker: Broker::Bybit",
        "scope: String::new()",
        "authority_scope: AuthorityScope::Denied",
        "reconciliation_run_id: String::new()",
        "paper_order_local_id: String::new()",
        "broker_order_id: String::new()",
        "execution_id: String::new()",
        "commission_report_id: String::new()",
        "shadow_signal_id: String::new()",
        "lifecycle_contract_hash: String::new()",
        "event_log_contract_hash: String::new()",
        "paper_fill_import_request_hash: String::new()",
        "shadow_signal_request_hash: String::new()",
        "shadow_fill_model_hash: String::new()",
        "cost_model_version_hash: String::new()",
        "market_data_provenance_hash: String::new()",
        "paper_shadow_divergence_threshold_hash: String::new()",
        "paper_shadow_link_hash: String::new()",
        "raw_artifact_hash: String::new()",
        "redacted_summary_hash: String::new()",
        "source_artifact_hash: String::new()",
        "append_only_event_ready: false",
        "paper_fill_imported: false",
        "shadow_fill_synthetic: false",
        "divergence_bps: 0",
        "divergence_threshold_bps: 0",
        "unmatched_paper_fill_count: 0",
        "unmatched_shadow_fill_count: 0",
        "ibkr_contact_performed: false",
        "connector_runtime_started: false",
        "secret_content_serialized: false",
        "fill_import_performed: false",
        "shadow_fill_generated: false",
        "reconciliation_writer_started: false",
        "scorecard_writer_started: false",
        "db_apply_performed: false",
        "order_routed: false",
        "bybit_path_reused: false",
        "live_or_tiny_live_authorized: false",
        "margin_short_options_cfd_requested: false",
        "python_direct_broker_write_requested: false",
    ):
        assert required_default in default_block

    for forbidden in (
        "asset_lane: AssetLane::CryptoPerp",
        "broker: Broker::Bybit",
        "scope: String::new()",
        'scope: "paper_order"',
        'scope: "shadow_signal"',
        "authority_scope: AuthorityScope::Denied",
        "authority_scope: AuthorityScope::PaperRehearsal",
        "authority_scope: AuthorityScope::ShadowOnly",
        "effect_capable: true",
        "reconciliation_run_id: String::new()",
        "paper_order_local_id: String::new()",
        "broker_order_id: String::new()",
        "execution_id: String::new()",
        "commission_report_id: String::new()",
        "shadow_signal_id: String::new()",
        "lifecycle_contract_hash: String::new()",
        "event_log_contract_hash: String::new()",
        "paper_fill_import_request_hash: String::new()",
        "shadow_signal_request_hash: String::new()",
        "shadow_fill_model_hash: String::new()",
        "cost_model_version_hash: String::new()",
        "market_data_provenance_hash: String::new()",
        "paper_shadow_divergence_threshold_hash: String::new()",
        "paper_shadow_link_hash: String::new()",
        "raw_artifact_hash: String::new()",
        "redacted_summary_hash: String::new()",
        "source_artifact_hash: String::new()",
        "append_only_event_ready: false",
        "paper_fill_imported: false",
        "shadow_fill_synthetic: false",
        "divergence_threshold_bps: 0",
        "unmatched_paper_fill_count: 1",
        "unmatched_shadow_fill_count: 1",
        "ibkr_contact_performed: true",
        "connector_runtime_started: true",
        "secret_content_serialized: true",
        "fill_import_performed: true",
        "shadow_fill_generated: true",
        "reconciliation_writer_started: true",
        "scorecard_writer_started: true",
        "db_apply_performed: true",
        "order_routed: true",
        "bybit_path_reused: true",
        "live_or_tiny_live_authorized: true",
        "margin_short_options_cfd_requested: true",
        "python_direct_broker_write_requested: true",
    ):
        assert forbidden not in fixture


def test_stock_etf_paper_shadow_reconciliation_source_excludes_write_shadow_and_effect_crosswire() -> None:
    source = _source()

    assert "AuthorityScope::PaperRehearsal" not in source
    assert "AuthorityScope::ShadowOnly" not in source
    assert "effect_capable: true" not in source
    assert 'scope: "paper_order"' not in source
    assert 'scope: "shadow_signal"' not in source


def test_stock_etf_paper_shadow_reconciliation_source_keeps_lineage_validation() -> None:
    source = _source()

    assert "self.contract_id != STOCK_ETF_PAPER_SHADOW_RECONCILIATION_CONTRACT_ID" in source
    assert "self.source_version != 1" in source
    assert "self.asset_lane != AssetLane::StockEtfCash" in source
    assert "self.broker != Broker::Ibkr" in source
    assert "self.scope != STOCK_ETF_PAPER_SHADOW_RECONCILIATION_SCOPE" in source
    assert "self.authority_scope != AuthorityScope::ReadOnly" in source
    assert "self.effect_capable" in source
    assert "reconciliation.reconciliation_run_id.trim().is_empty()" in source
    assert "reconciliation.paper_order_local_id.trim().is_empty()" in source
    assert "reconciliation.broker_order_id.trim().is_empty()" in source
    assert "reconciliation.execution_id.trim().is_empty()" in source
    assert "reconciliation.commission_report_id.trim().is_empty()" in source
    assert "reconciliation.shadow_signal_id.trim().is_empty()" in source
    assert "!is_sha256_hex(&reconciliation.lifecycle_contract_hash)" in source
    assert "!is_sha256_hex(&reconciliation.event_log_contract_hash)" in source
    assert "!is_sha256_hex(&reconciliation.paper_fill_import_request_hash)" in source
    assert "!is_sha256_hex(&reconciliation.shadow_signal_request_hash)" in source
    assert "!is_sha256_hex(&reconciliation.shadow_fill_model_hash)" in source
    assert "!is_sha256_hex(&reconciliation.cost_model_version_hash)" in source
    assert "!is_sha256_hex(&reconciliation.market_data_provenance_hash)" in source
    assert "!is_sha256_hex(&reconciliation.paper_shadow_divergence_threshold_hash)" in source
    assert "!is_sha256_hex(&reconciliation.paper_shadow_link_hash)" in source
    assert "!is_sha256_hex(&reconciliation.raw_artifact_hash)" in source
    assert "!is_sha256_hex(&reconciliation.redacted_summary_hash)" in source
    assert "!is_sha256_hex(&reconciliation.source_artifact_hash)" in source


def test_stock_etf_paper_shadow_reconciliation_source_keeps_evidence_gates() -> None:
    source = _source()

    assert "if !reconciliation.append_only_event_ready" in source
    assert "if !reconciliation.paper_fill_imported" in source
    assert "if !reconciliation.shadow_fill_synthetic" in source
    assert "if reconciliation.divergence_threshold_bps == 0" in source
    assert "reconciliation.divergence_bps > reconciliation.divergence_threshold_bps" in source
    assert "if reconciliation.unmatched_paper_fill_count > 0" in source
    assert "if reconciliation.unmatched_shadow_fill_count > 0" in source


def test_stock_etf_paper_shadow_reconciliation_source_keeps_no_side_effect_boundary_flags() -> None:
    source = _source()

    assert "if reconciliation.ibkr_contact_performed" in source
    assert "if reconciliation.connector_runtime_started" in source
    assert "if reconciliation.secret_content_serialized" in source
    assert "if reconciliation.fill_import_performed" in source
    assert "if reconciliation.shadow_fill_generated" in source
    assert "if reconciliation.reconciliation_writer_started" in source
    assert "if reconciliation.scorecard_writer_started" in source
    assert "if reconciliation.db_apply_performed" in source
    assert "if reconciliation.order_routed" in source
    assert "if reconciliation.bybit_path_reused" in source
    assert "if reconciliation.live_or_tiny_live_authorized" in source
    assert "if reconciliation.margin_short_options_cfd_requested" in source
    assert "if reconciliation.python_direct_broker_write_requested" in source


def test_stock_etf_paper_shadow_reconciliation_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{PAPER_SHADOW_RECONCILIATION}: contains forbidden token {token!r}")

    assert violations == []
