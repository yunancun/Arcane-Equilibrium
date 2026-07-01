from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
NON_BYBIT_ALLOWLIST = ROOT / "rust/openclaw_types/src/ibkr_non_bybit_api_allowlist.rs"
MAX_LINES = 800

REQUIRED_TYPE_TOKENS = {
    'NON_BYBIT_API_ALLOWLIST_CONTRACT_ID: &str = "non_bybit_api_allowlist_v1"',
    "pub enum NonBybitApiAction",
    "pub enum NonBybitApiDenialReason",
    "pub struct NonBybitApiAllowlistDecision",
    "impl NonBybitApiAllowlistDecision",
    "pub struct NonBybitApiAllowlistV1",
    "impl Default for NonBybitApiAllowlistV1",
    "impl NonBybitApiAllowlistV1",
    "pub fn accepted_fixture() -> Self",
    "pub fn validate(&self) -> NonBybitApiAllowlistVerdict",
    "pub struct NonBybitApiAllowlistVerdict",
    "pub enum NonBybitApiAllowlistBlocker",
    "pub const fn classify_non_bybit_api_action(",
    "pub const fn required_non_bybit_api_actions()",
    "fn validate_allowlist_actions(",
    "fn count_action(",
}
REQUIRED_FIELDS = {
    "contract_id",
    "source_version",
    "api_baseline",
    "read_actions",
    "paper_write_actions",
    "denied_actions",
    "client_portal_web_api_denied",
    "live_order_denied",
    "account_transfer_denied",
    "margin_short_options_cfd_denied",
    "market_data_entitlement_purchase_denied",
    "account_management_write_denied",
    "ibkr_contact_performed",
    "secret_content_serialized",
    "bybit_live_execution_protected",
}
READ_ACTIONS = {
    "ServerTimeRead",
    "ConnectionHealthRead",
    "AccountSummarySnapshotRead",
    "PortfolioPositionsSnapshotRead",
    "ContractDetailsRead",
    "MarketDataSnapshotRead",
    "MarketDataSubscriptionRead",
    "HistoricalBarsRead",
    "OpenPaperOrdersRead",
    "PaperExecutionsCommissionsRead",
}
PAPER_WRITE_ACTIONS = {
    "PaperOrderSubmit",
    "PaperOrderCancel",
    "PaperOrderReplace",
}
DENIED_ACTIONS = {
    "LiveOrderSubmit",
    "LiveAccountQuery",
    "AccountTransfer",
    "MarginEnablement",
    "ShortBorrow",
    "OptionsTrading",
    "CfdTrading",
    "MarketDataEntitlementPurchase",
    "AccountManagementWrite",
    "ClientPortalWebApiUse",
}
DENIAL_REASONS = {
    "LiveOrderDenied",
    "LiveAccountFingerprintDenied",
    "AccountTransferDenied",
    "MarginDenied",
    "ShortDenied",
    "OptionsDenied",
    "CfdDenied",
    "MarketDataEntitlementPurchaseDenied",
    "AccountManagementWriteDenied",
    "ClientPortalWebApiDenied",
}
REQUIRED_BLOCKERS = {
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "ApiBaselineMismatch",
    "ActionMissing",
    "ActionDuplicated",
    "ActionInWrongBucket",
    "ClientPortalWebApiNotDenied",
    "LiveOrderNotDenied",
    "AccountTransferNotDenied",
    "MarginShortOptionsCfdNotDenied",
    "MarketDataEntitlementPurchaseNotDenied",
    "AccountManagementWriteNotDenied",
    "IbkrContactPerformed",
    "SecretContentSerialized",
    "BybitLiveExecutionNotProtected",
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
    return NON_BYBIT_ALLOWLIST.read_text(encoding="utf-8")


def _function_block(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def test_ibkr_non_bybit_api_allowlist_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_ibkr_non_bybit_api_allowlist_source_keeps_contract_matrix() -> None:
    source = _source()

    for token in REQUIRED_TYPE_TOKENS:
        assert token in source
    for field in REQUIRED_FIELDS:
        assert field in source
    for action in READ_ACTIONS | PAPER_WRITE_ACTIONS | DENIED_ACTIONS:
        assert f"NonBybitApiAction::{action}" in source or action in source
    for denial in DENIAL_REASONS:
        assert f"Deny::{denial}" in source or denial in source
    for blocker in REQUIRED_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source

    assert "api_baseline: IbkrApiBaseline::IbGatewayTwsApi" in source
    assert "read_actions: Vec::new()" in source
    assert "paper_write_actions: Vec::new()" in source
    assert "denied_actions: Vec::new()" in source
    assert "ibkr_contact_performed: false" in source
    assert "secret_content_serialized: false" in source
    assert "bybit_live_execution_protected: false" in source
    assert "bybit_live_execution_protected: true" in source
    assert "accepted: blockers.is_empty()" in source


def test_ibkr_non_bybit_api_allowlist_source_keeps_action_bucket_semantics() -> None:
    source = _source()

    assert "allowed_after_external_gate: true" in source
    assert "requires_external_surface_gate: true" in source
    assert "requires_session_attestation" in source
    assert "requires_paper_order_gates: false" in source
    assert "requires_paper_order_gates: true" in source
    assert "denied: true" in source
    assert "denial_reason: Some(denial_reason)" in source
    assert "NonBybitApiAllowlistDecision::allowed_read(action, false)" in source
    assert "NonBybitApiAllowlistDecision::allowed_read(action, true)" in source
    assert "NonBybitApiAllowlistDecision::paper_write(action)" in source
    assert "NonBybitApiAllowlistDecision::denied(action, Deny::LiveOrderDenied)" in source
    assert (
        "NonBybitApiAllowlistDecision::denied(action, Deny::LiveAccountFingerprintDenied)"
        in source
    )
    assert (
        "NonBybitApiAllowlistDecision::denied(action, Deny::ClientPortalWebApiDenied)"
        in source
    )
    assert "Action::PaperOrderSubmit | Action::PaperOrderCancel | Action::PaperOrderReplace" in source
    assert "Action::LiveOrderSubmit" in source
    assert "Action::LiveAccountQuery" in source
    assert "Action::ClientPortalWebApiUse" in source


def test_ibkr_non_bybit_api_allowlist_fixture_excludes_runtime_secret_and_authority_crosswire() -> None:
    source = _source()
    fixture = source.split("impl NonBybitApiAllowlistV1", 1)[1].split(
        "pub fn validate(&self)",
        1,
    )[0]
    default_impl = source.split("impl Default for NonBybitApiAllowlistV1", 1)[1].split(
        "impl NonBybitApiAllowlistV1",
        1,
    )[0]

    for forbidden in (
        "read_actions: Vec::new()",
        "paper_write_actions: Vec::new()",
        "denied_actions: Vec::new()",
        "client_portal_web_api_denied: false",
        "live_order_denied: false",
        "account_transfer_denied: false",
        "margin_short_options_cfd_denied: false",
        "market_data_entitlement_purchase_denied: false",
        "account_management_write_denied: false",
        "ibkr_contact_performed: true",
        "secret_content_serialized: true",
        "bybit_live_execution_protected: false",
    ):
        assert forbidden not in fixture

    for fail_closed in (
        "read_actions: Vec::new()",
        "paper_write_actions: Vec::new()",
        "denied_actions: Vec::new()",
        "client_portal_web_api_denied: false",
        "live_order_denied: false",
        "account_transfer_denied: false",
        "margin_short_options_cfd_denied: false",
        "market_data_entitlement_purchase_denied: false",
        "account_management_write_denied: false",
        "ibkr_contact_performed: false",
        "secret_content_serialized: false",
        "bybit_live_execution_protected: false",
    ):
        assert fail_closed in default_impl


def test_ibkr_non_bybit_api_allowlist_source_keeps_drift_detection() -> None:
    source = _source()

    assert "validate_allowlist_actions(self, &mut blockers)" in source
    assert "for action in required_non_bybit_api_actions()" in source
    assert "let read_count = count_action(&allowlist.read_actions, *action)" in source
    assert "let paper_count = count_action(&allowlist.paper_write_actions, *action)" in source
    assert "let denied_count = count_action(&allowlist.denied_actions, *action)" in source
    assert "let total_count = read_count + paper_count + denied_count" in source
    assert "if total_count == 0" in source
    assert "if total_count > 1" in source
    assert "let decision = classify_non_bybit_api_action(*action)" in source
    assert "if decision.denied" in source
    assert "denied_count == 1 && read_count == 0 && paper_count == 0" in source
    assert "decision.requires_paper_order_gates" in source
    assert "paper_count == 1 && read_count == 0 && denied_count == 0" in source
    assert "read_count == 1 && paper_count == 0 && denied_count == 0" in source
    assert "if total_count > 0 && !in_correct_bucket" in source
    assert "if self.ibkr_contact_performed" in source
    assert "if self.secret_content_serialized" in source
    assert "if !self.bybit_live_execution_protected" in source


def test_ibkr_non_bybit_api_allowlist_source_keeps_exact_blocker_order() -> None:
    source = _source()
    validate = _function_block(
        source,
        "pub fn validate(&self) -> NonBybitApiAllowlistVerdict",
        "NonBybitApiAllowlistVerdict {",
    )
    actions = _function_block(source, "fn validate_allowlist_actions(", "fn count_action(")

    for block, ordered_blockers in (
        (
            validate,
            (
                "ContractIdMismatch",
                "SourceVersionMismatch",
                "ApiBaselineMismatch",
                "ClientPortalWebApiNotDenied",
                "LiveOrderNotDenied",
                "AccountTransferNotDenied",
                "MarginShortOptionsCfdNotDenied",
                "MarketDataEntitlementPurchaseNotDenied",
                "AccountManagementWriteNotDenied",
                "IbkrContactPerformed",
                "SecretContentSerialized",
                "BybitLiveExecutionNotProtected",
            ),
        ),
        (
            actions,
            (
                "ActionMissing",
                "ActionDuplicated",
                "ActionInWrongBucket",
            ),
        ),
    ):
        positions = [block.index(f"Blocker::{blocker}") for blocker in ordered_blockers]
        assert positions == sorted(positions)

    assert validate.index("validate_allowlist_actions(self, &mut blockers)") < validate.index(
        "Blocker::ClientPortalWebApiNotDenied"
    )


def test_ibkr_non_bybit_api_allowlist_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{NON_BYBIT_ALLOWLIST}: contains forbidden token {token!r}")

    assert violations == []
