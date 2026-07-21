from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PHASE0_MANIFEST = ROOT / "rust/openclaw_types/src/stock_etf_phase0_manifest.rs"
from tests.structure.file_line_policy import MAX_FILE_LINES as MAX_LINES

REQUIRED_TYPE_TOKENS = {
    "STOCK_ETF_PHASE0_MANIFEST_SCHEMA",
    '"stock_etf_phase0_contract_packet_manifest_v1"',
    "STOCK_ETF_PHASE0_MANIFEST_STATUS",
    '"ACCEPTED_PHASE0_CONTRACT_NO_RUNTIME_AUTHORITY"',
    "STOCK_ETF_PHASE0_MANIFEST_SCOPE",
    '"paper_shadow_only"',
    "STOCK_ETF_PHASE0_GENERATED_AT",
    '"2026-06-29"',
    "STOCK_ETF_PHASE0_ADR_PATH",
    "STOCK_ETF_PHASE0_AMD_PATH",
    "STOCK_ETF_PHASE0_PACKET_PATH",
    "const REQUIRED_CONTRACTS",
    "pub struct StockEtfPhase0ContractPacketManifestV1",
    "pub struct StockEtfPhase0AuthorityV1",
    "pub struct StockEtfPhase0ApiBaselineV1",
    "pub struct StockEtfPhase0GlobalDenialsV1",
    "pub struct StockEtfPhase0UnlockTableV1",
    "pub enum StockEtfPhase0ManifestBlocker",
    "pub fn required_phase0_contract_ids()",
    "fn validate_authority(",
    "fn validate_api_baseline(",
    "fn validate_global_denials(",
    "fn validate_contracts(",
    "fn validate_phase_unlock(",
}
REQUIRED_CONTRACT_IDS = {
    "STOCK_ETF_ASSET_LANE_TAXONOMY_CONTRACT_ID",
    "STOCK_ETF_BROKER_CAPABILITY_REGISTRY_ID",
    "IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID",
    "NON_BYBIT_API_ALLOWLIST_CONTRACT_ID",
    "STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID",
    "STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID",
    "STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID",
    "STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID",
    "STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID",
    "STOCK_ETF_RISK_POLICY_CONTRACT_ID",
    "STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID",
    "IBKR_API_SESSION_TOPOLOGY_CONTRACT_ID",
    "IBKR_SESSION_ATTESTATION_CONTRACT_ID",
    "FEATURE_FLAG_SECRET_AUTH_MATRIX_CONTRACT_ID",
    "STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID",
    "STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID",
    "STOCK_ETF_PAPER_FILL_IMPORT_REQUEST_CONTRACT_ID",
    "STOCK_ETF_SHADOW_SIGNAL_REQUEST_CONTRACT_ID",
    "IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID",
    "BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID",
    "STOCK_ETF_ASSET_LANE_EVENTS_CONTRACT_ID",
    "STOCK_ETF_DB_EVIDENCE_CONTRACT_ID",
    "STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID",
    "BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID",
    "STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID",
    "STOCK_ETF_BENCHMARK_VERSIONS_CONTRACT_ID",
    "STOCK_SHADOW_FILL_MODEL_CONTRACT_ID",
    "STOCK_ETF_PAPER_SHADOW_RECONCILIATION_CONTRACT_ID",
    "STOCK_ETF_COLLECTOR_RUN_CONTRACT_ID",
    "STOCK_ETF_DQ_MANIFEST_CONTRACT_ID",
    "STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID",
    "STOCK_ETF_GUI_LANE_CONTRACT_ID",
    "STOCK_ETF_STORAGE_CAPACITY_CONTRACT_ID",
    "STOCK_ETF_DISABLE_CLEANUP_RUNBOOK_ID",
    "STOCK_ETF_RELEASE_PACKET_CONTRACT_ID",
    "STOCK_ETF_TINY_LIVE_ADR_ELIGIBILITY_CONTRACT_ID",
}
REQUIRED_BLOCKERS = {
    "SchemaMismatch",
    "GeneratedAtMismatch",
    "StatusMismatch",
    "WrongAssetLane",
    "WrongBroker",
    "ScopeMismatch",
    "AdrPathMismatch",
    "AmdPathMismatch",
    "ContractPacketPathMismatch",
    "ApiBaselineSelectedMismatch",
    "ApiBaselineHostPolicyMismatch",
    "ApiBaselinePaperPortMismatch",
    "ApiBaselineLivePortsNotDenied",
    "ApiBaselineIbkrCallAlreadyPerformed",
    "GlobalDenialMissing",
    "ContractMissing",
    "ContractDuplicated",
    "ContractUnexpected",
    "Phase1UnlockMismatch",
    "Phase2ContactNotBlocked",
    "Phase3EvidenceClockNotBlocked",
    "Phase4GuiRuntimeNotBlocked",
    "Phase5OnlineNotBlocked",
    "TinyLiveOrLiveNotBlocked",
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
    return PHASE0_MANIFEST.read_text(encoding="utf-8")


def _function_block(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def test_stock_etf_phase0_manifest_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_phase0_manifest_source_keeps_contract_surface() -> None:
    source = _source()

    for token in REQUIRED_TYPE_TOKENS | REQUIRED_CONTRACT_IDS:
        assert token in source
    for blocker in REQUIRED_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source

    assert "asset_lane: AssetLane::CryptoPerp" in source
    assert "broker: Broker::Bybit" in source
    assert "asset_lane: AssetLane::StockEtfCash" in source
    assert "broker: Broker::Ibkr" in source
    assert "accepted: blockers.is_empty()" in source


def test_stock_etf_phase0_manifest_source_keeps_accepted_manifest_shape() -> None:
    source = _source()

    assert "schema: STOCK_ETF_PHASE0_MANIFEST_SCHEMA.to_string()" in source
    assert "generated_at: STOCK_ETF_PHASE0_GENERATED_AT.to_string()" in source
    assert "status: STOCK_ETF_PHASE0_MANIFEST_STATUS.to_string()" in source
    assert "scope: STOCK_ETF_PHASE0_MANIFEST_SCOPE.to_string()" in source
    assert "authority: StockEtfPhase0AuthorityV1::accepted_fixture()" in source
    assert "api_baseline: StockEtfPhase0ApiBaselineV1::accepted_fixture()" in source
    assert "global_denials: StockEtfPhase0GlobalDenialsV1::accepted_fixture()" in source
    assert "contracts: REQUIRED_CONTRACTS" in source
    assert "phase_unlock: StockEtfPhase0UnlockTableV1::accepted_fixture()" in source
    assert "selected: \"ib_gateway_tws_api\".to_string()" in source
    assert "host_policy: \"loopback_only\".to_string()" in source
    assert "paper_port_default_candidate: 4002" in source
    assert "live_ports_denied: true" in source
    assert "ibkr_call_performed: false" in source


def test_stock_etf_phase0_manifest_source_keeps_global_denials_and_unlocks() -> None:
    source = _source()

    for denial in (
        "ibkr_live: true",
        "tiny_live: true",
        "margin: true",
        "short: true",
        "options: true",
        "cfd: true",
        "transfer: true",
        "account_management_writes: true",
        "python_broker_write_authority: true",
        "gui_lane_authority: true",
        "automatic_promotion: true",
    ):
        assert denial in source

    assert "ALLOWED_AFTER_THIS_PACKET_WITH_E2_E4_QA" in source
    assert "BLOCKED_UNTIL_PHASE2_EXTERNAL_SURFACE_GATE_PASS" in source
    assert "BLOCKED_UNTIL_DATA_PROVENANCE_EVIDENCE_CONTRACTS_PASS" in source
    assert "BLOCKED_UNTIL_ROUTE_CACHE_AUTH_NEGATIVE_TESTS_PASS" in source
    assert "BLOCKED_UNTIL_RELEASE_PACKET_AND_SHAKEDOWN_PASS" in source
    assert "BLOCKED_REQUIRES_FUTURE_ADR" in source


def test_stock_etf_phase0_manifest_source_keeps_validation_matrix() -> None:
    source = _source()

    assert "self.schema != STOCK_ETF_PHASE0_MANIFEST_SCHEMA" in source
    assert "self.generated_at != STOCK_ETF_PHASE0_GENERATED_AT" in source
    assert "self.status != STOCK_ETF_PHASE0_MANIFEST_STATUS" in source
    assert "self.scope != STOCK_ETF_PHASE0_MANIFEST_SCOPE" in source
    assert "authority.adr != STOCK_ETF_PHASE0_ADR_PATH" in source
    assert "authority.amd != STOCK_ETF_PHASE0_AMD_PATH" in source
    assert "authority.contract_packet != STOCK_ETF_PHASE0_PACKET_PATH" in source
    assert 'baseline.selected != "ib_gateway_tws_api"' in source
    assert 'baseline.host_policy != "loopback_only"' in source
    assert "baseline.paper_port_default_candidate != 4002" in source
    assert "!baseline.live_ports_denied" in source
    assert "baseline.ibkr_call_performed" in source
    assert "if !all_denied" in source
    assert "for required in REQUIRED_CONTRACTS" in source
    assert "if count == 0" in source
    assert "if count > 1" in source
    assert "Blocker::ContractUnexpected" in source
    assert 'unlock.phase2_ibkr_external_contact != "BLOCKED_UNTIL_PHASE2_EXTERNAL_SURFACE_GATE_PASS"' in source
    assert 'unlock.tiny_live_or_live != "BLOCKED_REQUIRES_FUTURE_ADR"' in source


def test_stock_etf_phase0_manifest_source_keeps_exact_blocker_order() -> None:
    source = _source()
    manifest = _function_block(
        source,
        "pub fn validate(&self) -> StockEtfPhase0ManifestVerdict<StockEtfPhase0ManifestBlocker>",
        "StockEtfPhase0ManifestVerdict::new(blockers)",
    )
    authority = _function_block(source, "fn validate_authority(", "fn validate_api_baseline(")
    api_baseline = _function_block(
        source,
        "fn validate_api_baseline(",
        "fn validate_global_denials(",
    )
    contracts = _function_block(source, "fn validate_contracts(", "fn validate_phase_unlock(")
    phase_unlock = source.split("fn validate_phase_unlock(", 1)[1]

    for block, ordered_blockers in (
        (
            manifest,
            (
                "SchemaMismatch",
                "GeneratedAtMismatch",
                "StatusMismatch",
                "WrongAssetLane",
                "WrongBroker",
                "ScopeMismatch",
            ),
        ),
        (
            authority,
            (
                "AdrPathMismatch",
                "AmdPathMismatch",
                "ContractPacketPathMismatch",
            ),
        ),
        (
            api_baseline,
            (
                "ApiBaselineSelectedMismatch",
                "ApiBaselineHostPolicyMismatch",
                "ApiBaselinePaperPortMismatch",
                "ApiBaselineLivePortsNotDenied",
                "ApiBaselineIbkrCallAlreadyPerformed",
            ),
        ),
        (
            contracts,
            (
                "ContractMissing",
                "ContractDuplicated",
                "ContractUnexpected",
            ),
        ),
        (
            phase_unlock,
            (
                "Phase1UnlockMismatch",
                "Phase2ContactNotBlocked",
                "Phase3EvidenceClockNotBlocked",
                "Phase4GuiRuntimeNotBlocked",
                "Phase5OnlineNotBlocked",
                "TinyLiveOrLiveNotBlocked",
            ),
        ),
    ):
        positions = [block.index(f"Blocker::{blocker}") for blocker in ordered_blockers]
        assert positions == sorted(positions)

    validator_call_order = (
        "validate_authority(&self.authority, &mut blockers)",
        "validate_api_baseline(&self.api_baseline, &mut blockers)",
        "validate_global_denials(&self.global_denials, &mut blockers)",
        "validate_contracts(&self.contracts, &mut blockers)",
        "validate_phase_unlock(&self.phase_unlock, &mut blockers)",
    )
    positions = [manifest.index(call) for call in validator_call_order]
    assert positions == sorted(positions)


def test_stock_etf_phase0_manifest_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{PHASE0_MANIFEST}: contains forbidden token {token!r}")

    assert violations == []
