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


def test_stock_etf_paper_shadow_reconciliation_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_paper_shadow_reconciliation_source_keeps_contract_surface() -> None:
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
    assert "authority_scope: AuthorityScope::Denied" in source
    assert "effect_capable: false" in source
    assert "append_only_event_ready: false" in source
    assert "paper_fill_imported: false" in source
    assert "shadow_fill_synthetic: false" in source
    assert "divergence_bps: 0" in source
    assert "divergence_threshold_bps: 0" in source
    assert "unmatched_paper_fill_count: 0" in source
    assert "unmatched_shadow_fill_count: 0" in source
    assert "accepted: blockers.is_empty()" in source


def test_stock_etf_paper_shadow_reconciliation_source_keeps_accepted_readonly_shape() -> None:
    source = _source()

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
