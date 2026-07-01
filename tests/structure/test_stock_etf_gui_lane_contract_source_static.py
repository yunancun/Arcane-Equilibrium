from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GUI_LANE = ROOT / "rust/openclaw_types/src/stock_etf_gui_lane_contract.rs"
MAX_LINES = 800

REQUIRED_TYPE_TOKENS = {
    "STOCK_ETF_GUI_LANE_CONTRACT_ID",
    '"gui_lane_contract_v1"',
    "pub struct StockEtfGuiLaneContractV1",
    "pub fn accepted_fixture() -> Self",
    "pub fn validate(&self) -> StockEtfGuiLaneVerdict<StockEtfGuiLaneBlocker>",
    "fn has_required_denial(denials: &[String], expected: &str) -> bool",
    "pub struct StockEtfGuiLaneVerdict",
    "pub enum StockEtfGuiLaneBlocker",
}
REQUIRED_ENDPOINT_CONSTANTS = {
    "STOCK_ETF_GUI_READINESS_ENDPOINT",
    "STOCK_ETF_GUI_LANE_STATUS_ENDPOINT",
    "STOCK_ETF_GUI_PHASE0_STATUS_ENDPOINT",
    "STOCK_ETF_GUI_DATA_FOUNDATION_STATUS_ENDPOINT",
    "STOCK_ETF_GUI_POLICY_STATUS_ENDPOINT",
    "STOCK_ETF_GUI_AUTHORIZATION_STATUS_ENDPOINT",
    "STOCK_ETF_GUI_ACCOUNT_STATUS_ENDPOINT",
    "STOCK_ETF_GUI_EVIDENCE_STATUS_ENDPOINT",
    "STOCK_ETF_GUI_UNIVERSE_STATUS_ENDPOINT",
    "STOCK_ETF_GUI_SHADOW_STATUS_ENDPOINT",
    "STOCK_ETF_GUI_PAPER_STATUS_ENDPOINT",
    "STOCK_ETF_GUI_RECONCILIATION_STATUS_ENDPOINT",
    "STOCK_ETF_GUI_SCORECARD_STATUS_ENDPOINT",
    "STOCK_ETF_GUI_LAUNCH_STATUS_ENDPOINT",
    "STOCK_ETF_GUI_RELEASE_PACKET_STATUS_ENDPOINT",
    "STOCK_ETF_GUI_DISABLE_CLEANUP_STATUS_ENDPOINT",
}
REQUIRED_ENDPOINT_PATHS = {
    "/api/v1/stock-etf/readiness",
    "/api/v1/stock-etf/lane-status",
    "/api/v1/stock-etf/phase0-status",
    "/api/v1/stock-etf/data-foundation-status",
    "/api/v1/stock-etf/policy-status",
    "/api/v1/stock-etf/authorization-status",
    "/api/v1/stock-etf/account-status",
    "/api/v1/stock-etf/evidence-status",
    "/api/v1/stock-etf/universe-status",
    "/api/v1/stock-etf/shadow-status",
    "/api/v1/stock-etf/paper-status",
    "/api/v1/stock-etf/reconciliation-status",
    "/api/v1/stock-etf/scorecard-status",
    "/api/v1/stock-etf/launch-status",
    "/api/v1/stock-etf/release-packet-status",
    "/api/v1/stock-etf/disable-cleanup-status",
}
REQUIRED_AUTHORITY_FIELDS = {
    "display_only",
    "client_lane_state_untrusted",
    "local_storage_authority_denied",
    "query_param_authority_denied",
    "hidden_field_authority_denied",
    "no_login_success_selector",
    "no_post_routes",
    "no_order_widgets",
    "no_secret_widgets",
    "no_ibkr_contact_on_render",
    "paper_order_entry_hidden",
    "stock_live_disabled_display",
    "cfd_surface_hidden_or_fail_closed",
    "route_cache_partition_required",
    "auth_partition_required",
    "stale_cache_cross_lane_denied",
    "crypto_tabs_regression_passed",
    "decision_lease_risk_regression_passed",
    "denied_effect_operations",
    "ibkr_contact_performed",
    "secret_content_serialized",
}
REQUIRED_DENIALS = {
    "ibkr_live_order_submit",
    "ibkr_tiny_live",
    "ibkr_secret_slot_creation",
    "ibkr_api_contact_before_phase2_gate",
}
REQUIRED_BLOCKERS = {
    "ContractIdMissing",
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "DefaultLaneNotCryptoPerp",
    "StockEtfTabMissing",
    "ReadinessEndpointMismatch",
    "ReadinessEndpointNotGetOnly",
    "LaneStatusEndpointMismatch",
    "LaneStatusEndpointNotGetOnly",
    "Phase0StatusEndpointMismatch",
    "Phase0StatusEndpointNotGetOnly",
    "DataFoundationStatusEndpointMismatch",
    "DataFoundationStatusEndpointNotGetOnly",
    "PolicyStatusEndpointMismatch",
    "PolicyStatusEndpointNotGetOnly",
    "AuthorizationStatusEndpointMismatch",
    "AuthorizationStatusEndpointNotGetOnly",
    "AccountStatusEndpointMismatch",
    "AccountStatusEndpointNotGetOnly",
    "EvidenceStatusEndpointMismatch",
    "EvidenceStatusEndpointNotGetOnly",
    "UniverseStatusEndpointMismatch",
    "UniverseStatusEndpointNotGetOnly",
    "ShadowStatusEndpointMismatch",
    "ShadowStatusEndpointNotGetOnly",
    "PaperStatusEndpointMismatch",
    "PaperStatusEndpointNotGetOnly",
    "ReconciliationStatusEndpointMismatch",
    "ReconciliationStatusEndpointNotGetOnly",
    "ScorecardStatusEndpointMismatch",
    "ScorecardStatusEndpointNotGetOnly",
    "LaunchStatusEndpointMismatch",
    "LaunchStatusEndpointNotGetOnly",
    "ReleasePacketStatusEndpointMismatch",
    "ReleasePacketStatusEndpointNotGetOnly",
    "DisableCleanupStatusEndpointMismatch",
    "DisableCleanupStatusEndpointNotGetOnly",
    "DisplayOnlyMissing",
    "ClientLaneStateTrusted",
    "LocalStorageAuthorityNotDenied",
    "QueryParamAuthorityNotDenied",
    "HiddenFieldAuthorityNotDenied",
    "LoginSuccessSelectorPresent",
    "PostRoutePresent",
    "OrderWidgetPresent",
    "SecretWidgetPresent",
    "IbkrContactOnRenderAllowed",
    "PaperOrderEntryVisible",
    "StockLiveDisabledDisplayMissing",
    "CfdSurfaceNotHiddenOrFailClosed",
    "RouteCachePartitionMissing",
    "AuthPartitionMissing",
    "StaleCacheCrossLaneNotDenied",
    "CryptoTabsRegressionMissing",
    "DecisionLeaseRiskRegressionMissing",
    "StaticSourceHashInvalid",
    "RouteTestHashInvalid",
    "CryptoRegressionHashInvalid",
    "LiveOrderDenialMissing",
    "SecretSlotDenialMissing",
    "PreGateContactDenialMissing",
    "IbkrContactPerformed",
    "SecretContentSerialized",
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
    return GUI_LANE.read_text(encoding="utf-8")


def _validate_block(source: str) -> str:
    return source.split(
        "pub fn validate(&self) -> StockEtfGuiLaneVerdict<StockEtfGuiLaneBlocker>",
        1,
    )[1].split("StockEtfGuiLaneVerdict::new(blockers)", 1)[0]


def test_stock_etf_gui_lane_contract_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_gui_lane_contract_source_keeps_contract_surface() -> None:
    source = _source()

    for token in (
        REQUIRED_TYPE_TOKENS
        | REQUIRED_ENDPOINT_CONSTANTS
        | REQUIRED_ENDPOINT_PATHS
        | REQUIRED_AUTHORITY_FIELDS
        | REQUIRED_DENIALS
    ):
        assert token in source
    for blocker in REQUIRED_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source

    assert "accepted: blockers.is_empty()" in source


def test_stock_etf_gui_lane_contract_source_keeps_fail_closed_default() -> None:
    source = _source()

    assert "contract_id: String::new()" in source
    assert "source_version: 0" in source
    assert "default_asset_lane: AssetLane::CryptoPerp" in source
    assert "stock_etf_tab_registered: false" in source
    assert "readiness_endpoint: String::new()" in source
    assert "readiness_endpoint_get_only: false" in source
    assert "display_only: false" in source
    assert "client_lane_state_untrusted: false" in source
    assert "local_storage_authority_denied: false" in source
    assert "query_param_authority_denied: false" in source
    assert "hidden_field_authority_denied: false" in source
    assert "no_post_routes: false" in source
    assert "no_order_widgets: false" in source
    assert "no_secret_widgets: false" in source
    assert "no_ibkr_contact_on_render: false" in source
    assert "denied_effect_operations: Vec::new()" in source
    assert "ibkr_contact_performed: false" in source
    assert "secret_content_serialized: false" in source


def test_stock_etf_gui_lane_contract_source_keeps_accepted_fixture_display_only_boundary() -> None:
    source = _source()
    compact = "".join(source.split())

    assert "contract_id: STOCK_ETF_GUI_LANE_CONTRACT_ID.to_string()" in source
    assert "source_version: 1" in source
    assert "default_asset_lane: AssetLane::CryptoPerp" in source
    assert "stock_etf_tab_registered: true" in source
    for endpoint in REQUIRED_ENDPOINT_CONSTANTS:
        if endpoint == "STOCK_ETF_GUI_LANE_CONTRACT_ID":
            continue
        if endpoint.startswith("STOCK_ETF_GUI_"):
            assert f"{endpoint}.to_string()" in compact
    assert "readiness_endpoint_get_only: true" in source
    assert "lane_status_endpoint_get_only: true" in source
    assert "phase0_status_endpoint_get_only: true" in source
    assert "data_foundation_status_endpoint_get_only: true" in source
    assert "policy_status_endpoint_get_only: true" in source
    assert "authorization_status_endpoint_get_only: true" in source
    assert "account_status_endpoint_get_only: true" in source
    assert "evidence_status_endpoint_get_only: true" in source
    assert "universe_status_endpoint_get_only: true" in source
    assert "shadow_status_endpoint_get_only: true" in source
    assert "paper_status_endpoint_get_only: true" in source
    assert "reconciliation_status_endpoint_get_only: true" in source
    assert "scorecard_status_endpoint_get_only: true" in source
    assert "launch_status_endpoint_get_only: true" in source
    assert "release_packet_status_endpoint_get_only: true" in source
    assert "disable_cleanup_status_endpoint_get_only: true" in source
    assert "display_only: true" in source
    assert "client_lane_state_untrusted: true" in source
    assert "local_storage_authority_denied: true" in source
    assert "query_param_authority_denied: true" in source
    assert "hidden_field_authority_denied: true" in source
    assert "no_login_success_selector: true" in source
    assert "no_post_routes: true" in source
    assert "no_order_widgets: true" in source
    assert "no_secret_widgets: true" in source
    assert "no_ibkr_contact_on_render: true" in source
    assert "paper_order_entry_hidden: true" in source
    assert "stock_live_disabled_display: true" in source
    assert "cfd_surface_hidden_or_fail_closed: true" in source
    assert "route_cache_partition_required: true" in source
    assert "auth_partition_required: true" in source
    assert "stale_cache_cross_lane_denied: true" in source
    assert "crypto_tabs_regression_passed: true" in source
    assert "decision_lease_risk_regression_passed: true" in source
    assert "ibkr_contact_performed: false" in source
    assert "secret_content_serialized: false" in source


def test_stock_etf_gui_lane_contract_source_keeps_validation_matrix() -> None:
    source = _source()

    assert "self.contract_id.trim().is_empty()" in source
    assert "self.contract_id != STOCK_ETF_GUI_LANE_CONTRACT_ID" in source
    assert "self.source_version != 1" in source
    assert "self.default_asset_lane != AssetLane::CryptoPerp" in source
    assert "!self.stock_etf_tab_registered" in source
    for endpoint in (
        "readiness",
        "lane_status",
        "phase0_status",
        "data_foundation_status",
        "policy_status",
        "authorization_status",
        "account_status",
        "evidence_status",
        "universe_status",
        "shadow_status",
        "paper_status",
        "reconciliation_status",
        "scorecard_status",
        "launch_status",
        "release_packet_status",
        "disable_cleanup_status",
    ):
        assert f"self.{endpoint}_endpoint !=" in source
        assert f"!self.{endpoint}_endpoint_get_only" in source
    assert "!self.display_only" in source
    assert "!self.client_lane_state_untrusted" in source
    assert "!self.local_storage_authority_denied" in source
    assert "!self.query_param_authority_denied" in source
    assert "!self.hidden_field_authority_denied" in source
    assert "!self.no_login_success_selector" in source
    assert "!self.no_post_routes" in source
    assert "!self.no_order_widgets" in source
    assert "!self.no_secret_widgets" in source
    assert "!self.no_ibkr_contact_on_render" in source
    assert "!self.paper_order_entry_hidden" in source
    assert "!self.stock_live_disabled_display" in source
    assert "!self.cfd_surface_hidden_or_fail_closed" in source
    assert "!self.route_cache_partition_required" in source
    assert "!self.auth_partition_required" in source
    assert "!self.stale_cache_cross_lane_denied" in source
    assert "!self.crypto_tabs_regression_passed" in source
    assert "!self.decision_lease_risk_regression_passed" in source
    assert "!is_sha256_hex(&self.static_source_hash)" in source
    assert "!is_sha256_hex(&self.route_test_hash)" in source
    assert "!is_sha256_hex(&self.crypto_regression_hash)" in source
    assert 'has_required_denial(&self.denied_effect_operations, "ibkr_live_order_submit")' in source
    assert 'has_required_denial(&self.denied_effect_operations, "ibkr_secret_slot_creation")' in source
    assert 'has_required_denial(\n            &self.denied_effect_operations,\n            "ibkr_api_contact_before_phase2_gate",' in source
    assert "self.ibkr_contact_performed" in source
    assert "self.secret_content_serialized" in source


def test_stock_etf_gui_lane_contract_source_keeps_exact_blocker_order() -> None:
    validate = _validate_block(_source())
    ordered_blockers = (
        "ContractIdMissing",
        "ContractIdMismatch",
        "SourceVersionMismatch",
        "DefaultLaneNotCryptoPerp",
        "StockEtfTabMissing",
        "ReadinessEndpointMismatch",
        "ReadinessEndpointNotGetOnly",
        "LaneStatusEndpointMismatch",
        "LaneStatusEndpointNotGetOnly",
        "Phase0StatusEndpointMismatch",
        "Phase0StatusEndpointNotGetOnly",
        "DataFoundationStatusEndpointMismatch",
        "DataFoundationStatusEndpointNotGetOnly",
        "PolicyStatusEndpointMismatch",
        "PolicyStatusEndpointNotGetOnly",
        "AuthorizationStatusEndpointMismatch",
        "AuthorizationStatusEndpointNotGetOnly",
        "AccountStatusEndpointMismatch",
        "AccountStatusEndpointNotGetOnly",
        "EvidenceStatusEndpointMismatch",
        "EvidenceStatusEndpointNotGetOnly",
        "UniverseStatusEndpointMismatch",
        "UniverseStatusEndpointNotGetOnly",
        "ShadowStatusEndpointMismatch",
        "ShadowStatusEndpointNotGetOnly",
        "PaperStatusEndpointMismatch",
        "PaperStatusEndpointNotGetOnly",
        "ReconciliationStatusEndpointMismatch",
        "ReconciliationStatusEndpointNotGetOnly",
        "ScorecardStatusEndpointMismatch",
        "ScorecardStatusEndpointNotGetOnly",
        "LaunchStatusEndpointMismatch",
        "LaunchStatusEndpointNotGetOnly",
        "ReleasePacketStatusEndpointMismatch",
        "ReleasePacketStatusEndpointNotGetOnly",
        "DisableCleanupStatusEndpointMismatch",
        "DisableCleanupStatusEndpointNotGetOnly",
        "DisplayOnlyMissing",
        "ClientLaneStateTrusted",
        "LocalStorageAuthorityNotDenied",
        "QueryParamAuthorityNotDenied",
        "HiddenFieldAuthorityNotDenied",
        "LoginSuccessSelectorPresent",
        "PostRoutePresent",
        "OrderWidgetPresent",
        "SecretWidgetPresent",
        "IbkrContactOnRenderAllowed",
        "PaperOrderEntryVisible",
        "StockLiveDisabledDisplayMissing",
        "CfdSurfaceNotHiddenOrFailClosed",
        "RouteCachePartitionMissing",
        "AuthPartitionMissing",
        "StaleCacheCrossLaneNotDenied",
        "CryptoTabsRegressionMissing",
        "DecisionLeaseRiskRegressionMissing",
        "StaticSourceHashInvalid",
        "RouteTestHashInvalid",
        "CryptoRegressionHashInvalid",
        "LiveOrderDenialMissing",
        "SecretSlotDenialMissing",
        "PreGateContactDenialMissing",
        "IbkrContactPerformed",
        "SecretContentSerialized",
    )

    positions = [validate.index(f"Blocker::{blocker}") for blocker in ordered_blockers]
    assert positions == sorted(positions)


def test_stock_etf_gui_lane_contract_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{GUI_LANE}: contains forbidden token {token!r}")

    assert violations == []
