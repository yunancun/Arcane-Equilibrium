from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RISK_POLICY = ROOT / "rust/openclaw_types/src/stock_etf_risk_policy.rs"
from tests.structure.file_line_policy import MAX_FILE_LINES as MAX_LINES

REQUIRED_TYPE_TOKENS = {
    'STOCK_ETF_RISK_POLICY_CONTRACT_ID: &str = "stock_etf_risk_policy_v1"',
    "const MAX_OPEN_ORDERS_V1: u16 = 20",
    "const MAX_OPEN_POSITIONS_V1: u16 = 100",
    "const REQUIRED_ALLOWED_KINDS",
    "const REQUIRED_DENIED_KINDS",
    "const FORBIDDEN_ALLOWED_KINDS",
    "pub struct StockEtfRiskPolicyV1",
    "impl Default for StockEtfRiskPolicyV1",
    "impl StockEtfRiskPolicyV1",
    "pub fn accepted_fixture() -> Self",
    "pub fn from_source_config(",
    "pub fn validate(&self) -> StockEtfRiskPolicyVerdict<StockEtfRiskPolicyBlocker>",
    "pub struct StockEtfRiskPolicySourceConfigV1",
    "pub struct StockEtfRiskPolicySourceMetaV1",
    "pub struct StockEtfRiskPolicySourceLimitsV1",
    "pub struct StockEtfRiskPolicySourceUniverseV1",
    "pub struct StockEtfRiskPolicySourceCostModelV1",
    "pub struct StockEtfRiskPolicySourcePaperOrderV1",
    "fn validate_caps(",
    "fn validate_cash_only_controls(",
    "fn validate_universe_controls(",
    "fn validate_cost_model_controls(",
    "fn validate_paper_order_controls(",
    "fn positive_finite(",
    "fn contains_all_kinds(",
    "fn contains_any_kind(",
    "pub struct StockEtfRiskPolicyVerdict",
    "pub enum StockEtfRiskPolicyBlocker",
}
REQUIRED_POLICY_FIELDS = {
    "contract_id",
    "source_version",
    "config_version",
    "asset_lane",
    "broker",
    "environment",
    "enabled",
    "shadow_only",
    "max_order_notional_usd",
    "max_position_notional_usd",
    "max_daily_notional_usd",
    "max_open_orders",
    "max_open_positions",
    "allow_fractional_shares",
    "allow_margin",
    "allow_short",
    "allow_options",
    "allow_cfd",
    "allow_transfer",
    "allow_live",
    "instrument_kinds_allowed",
    "instrument_kinds_denied",
    "requires_frozen_universe_hash",
    "requires_instrument_identity_hash",
    "requires_market_session",
    "cost_model_required_before_shadow_fill",
    "cost_model_required_before_scorecard",
    "commission_schedule_required",
    "spread_estimate_required",
    "slippage_estimate_required",
    "fx_drag_required",
    "conservative_fill_penalty_required",
    "rust_authority_required",
    "session_attestation_required",
    "decision_lease_required",
    "guardian_required",
    "idempotency_key_required",
    "broker_reconciliation_required",
    "bybit_live_execution_unchanged",
    "ibkr_contact_performed",
    "connector_runtime_started",
    "secret_content_serialized",
}
REQUIRED_INSTRUMENT_KINDS = {
    "InstrumentKind::Stock",
    "InstrumentKind::Etf",
    "InstrumentKind::Cash",
    "InstrumentKind::CfdReserved",
    "InstrumentKind::CryptoPerp",
}
REQUIRED_BLOCKERS = {
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "VersionMismatch",
    "WrongAssetLane",
    "WrongBroker",
    "WrongEnvironment",
    "RuntimeEnablementClaimed",
    "ShadowOnlyPostureMissing",
    "OrderCapMissing",
    "PositionCapMissing",
    "DailyCapMissing",
    "CapOrderingInvalid",
    "OpenOrderLimitMissing",
    "OpenOrderLimitTooHigh",
    "OpenPositionLimitMissing",
    "OpenPositionLimitTooHigh",
    "MarginAllowed",
    "ShortAllowed",
    "OptionsAllowed",
    "CfdAllowed",
    "TransferAllowed",
    "LiveAllowed",
    "AllowedInstrumentMissing",
    "ForbiddenInstrumentAllowed",
    "DeniedInstrumentMissing",
    "FrozenUniverseHashNotRequired",
    "InstrumentIdentityHashNotRequired",
    "MarketSessionNotRequired",
    "CostModelBeforeShadowFillMissing",
    "CostModelBeforeScorecardMissing",
    "CommissionScheduleMissing",
    "SpreadEstimateMissing",
    "SlippageEstimateMissing",
    "FxDragMissing",
    "ConservativePenaltyMissing",
    "RustAuthorityMissing",
    "SessionAttestationMissing",
    "DecisionLeaseMissing",
    "GuardianMissing",
    "IdempotencyKeyMissing",
    "BrokerReconciliationMissing",
    "BybitLiveExecutionNotProtected",
    "IbkrContactPerformed",
    "ConnectorRuntimeStarted",
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
    return RISK_POLICY.read_text(encoding="utf-8")


def test_stock_etf_risk_policy_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_risk_policy_source_keeps_contract_and_fail_closed_defaults() -> None:
    source = _source()

    for token in REQUIRED_TYPE_TOKENS | REQUIRED_INSTRUMENT_KINDS:
        assert token in source
    for field in REQUIRED_POLICY_FIELDS:
        assert field in source
    for blocker in REQUIRED_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source

    assert "contract_id: String::new()" in source
    assert "source_version: 0" in source
    assert "config_version: 0" in source
    assert "asset_lane: AssetLane::CryptoPerp" in source
    assert "broker: Broker::Bybit" in source
    assert "environment: BrokerEnvironment::LiveReservedDenied" in source
    assert "enabled: true" in source
    assert "shadow_only: false" in source
    assert "allow_margin: true" in source
    assert "allow_short: true" in source
    assert "allow_options: true" in source
    assert "allow_cfd: true" in source
    assert "allow_transfer: true" in source
    assert "allow_live: true" in source
    assert "bybit_live_execution_unchanged: false" in source
    assert "ibkr_contact_performed: false" in source
    assert "connector_runtime_started: false" in source
    assert "secret_content_serialized: false" in source
    assert "accepted: blockers.is_empty()" in source


def test_stock_etf_risk_policy_source_keeps_dormant_cash_only_paper_shadow_posture() -> None:
    source = _source()

    assert "asset_lane: AssetLane::StockEtfCash" in source
    assert "broker: Broker::Ibkr" in source
    assert "environment: BrokerEnvironment::Paper" in source
    assert "enabled: false" in source
    assert "shadow_only: true" in source
    assert "max_order_notional_usd: 1_000.0" in source
    assert "max_position_notional_usd: 5_000.0" in source
    assert "max_daily_notional_usd: 10_000.0" in source
    assert "max_open_orders: 5" in source
    assert "max_open_positions: 10" in source
    assert "allow_fractional_shares: true" in source
    assert "allow_margin: false" in source
    assert "allow_short: false" in source
    assert "allow_options: false" in source
    assert "allow_cfd: false" in source
    assert "allow_transfer: false" in source
    assert "allow_live: false" in source
    assert "instrument_kinds_allowed: REQUIRED_ALLOWED_KINDS.to_vec()" in source
    assert "instrument_kinds_denied: REQUIRED_DENIED_KINDS.to_vec()" in source
    assert "bybit_live_execution_unchanged: true" in source
    assert "if self.enabled" in source
    assert "if !self.shadow_only" in source
    assert "BrokerEnvironment::Paper | BrokerEnvironment::Shadow" in source


def test_stock_etf_risk_policy_fixture_excludes_runtime_live_secret_and_connector_crosswire() -> None:
    source = _source()
    fixture = source.split("pub fn accepted_fixture() -> Self", 1)[1].split(
        "pub fn from_source_config(",
        1,
    )[0]
    source_config_mapper = source.split("pub fn from_source_config(", 1)[1].split(
        "pub fn validate(&self)",
        1,
    )[0]
    default_impl = source.split("impl Default for StockEtfRiskPolicyV1", 1)[1].split(
        "impl StockEtfRiskPolicyV1",
        1,
    )[0]

    for forbidden in (
        "environment: BrokerEnvironment::LiveReservedDenied",
        "enabled: true",
        "shadow_only: false",
        "allow_margin: true",
        "allow_short: true",
        "allow_options: true",
        "allow_cfd: true",
        "allow_transfer: true",
        "allow_live: true",
        "bybit_live_execution_unchanged: false",
        "ibkr_contact_performed: true",
        "connector_runtime_started: true",
        "secret_content_serialized: true",
    ):
        assert forbidden not in fixture

    for forbidden in (
        "bybit_live_execution_unchanged: false",
        "ibkr_contact_performed: true",
        "connector_runtime_started: true",
        "secret_content_serialized: true",
    ):
        assert forbidden not in source_config_mapper

    for fail_closed in (
        "environment: BrokerEnvironment::LiveReservedDenied",
        "enabled: true",
        "shadow_only: false",
        "allow_margin: true",
        "allow_short: true",
        "allow_options: true",
        "allow_cfd: true",
        "allow_transfer: true",
        "allow_live: true",
        "bybit_live_execution_unchanged: false",
        "ibkr_contact_performed: false",
        "connector_runtime_started: false",
        "secret_content_serialized: false",
    ):
        assert fail_closed in default_impl


def test_stock_etf_risk_policy_source_keeps_caps_universe_cost_and_order_gates() -> None:
    source = _source()

    assert "positive_finite(policy.max_order_notional_usd)" in source
    assert "positive_finite(policy.max_position_notional_usd)" in source
    assert "positive_finite(policy.max_daily_notional_usd)" in source
    assert "policy.max_order_notional_usd <= policy.max_position_notional_usd" in source
    assert "policy.max_position_notional_usd <= policy.max_daily_notional_usd" in source
    assert "policy.max_open_orders > MAX_OPEN_ORDERS_V1" in source
    assert "policy.max_open_positions > MAX_OPEN_POSITIONS_V1" in source
    assert "if policy.allow_margin" in source
    assert "if policy.allow_short" in source
    assert "if policy.allow_options" in source
    assert "if policy.allow_cfd" in source
    assert "if policy.allow_transfer" in source
    assert "if policy.allow_live" in source
    assert "contains_all_kinds(&policy.instrument_kinds_allowed, REQUIRED_ALLOWED_KINDS)" in source
    assert "contains_any_kind(&policy.instrument_kinds_allowed, FORBIDDEN_ALLOWED_KINDS)" in source
    assert "contains_all_kinds(&policy.instrument_kinds_denied, REQUIRED_DENIED_KINDS)" in source
    assert "if !policy.requires_frozen_universe_hash" in source
    assert "if !policy.requires_instrument_identity_hash" in source
    assert "if !policy.requires_market_session" in source
    assert "if !policy.cost_model_required_before_shadow_fill" in source
    assert "if !policy.cost_model_required_before_scorecard" in source
    assert "if !policy.commission_schedule_required" in source
    assert "if !policy.spread_estimate_required" in source
    assert "if !policy.slippage_estimate_required" in source
    assert "if !policy.fx_drag_required" in source
    assert "if !policy.conservative_fill_penalty_required" in source
    assert "if !policy.rust_authority_required" in source
    assert "if !policy.session_attestation_required" in source
    assert "if !policy.decision_lease_required" in source
    assert "if !policy.guardian_required" in source
    assert "if !policy.idempotency_key_required" in source
    assert "if !policy.broker_reconciliation_required" in source


def test_stock_etf_risk_policy_source_keeps_blocker_emit_order() -> None:
    source = _source()
    validate_body = source.split("pub fn validate(&self)", 1)[1].split(
        "StockEtfRiskPolicyVerdict::new",
        1,
    )[0]
    caps_body = source.split("fn validate_caps(", 1)[1].split(
        "fn validate_cash_only_controls(",
        1,
    )[0]
    cash_body = source.split("fn validate_cash_only_controls(", 1)[1].split(
        "fn validate_universe_controls(",
        1,
    )[0]
    universe_body = source.split("fn validate_universe_controls(", 1)[1].split(
        "fn validate_cost_model_controls(",
        1,
    )[0]
    cost_body = source.split("fn validate_cost_model_controls(", 1)[1].split(
        "fn validate_paper_order_controls(",
        1,
    )[0]
    paper_body = source.split("fn validate_paper_order_controls(", 1)[1].split(
        "fn positive_finite(",
        1,
    )[0]

    _assert_order(
        validate_body,
        (
            "blockers.push(Blocker::ContractIdMismatch);",
            "blockers.push(Blocker::SourceVersionMismatch);",
            "blockers.push(Blocker::VersionMismatch);",
            "blockers.push(Blocker::WrongAssetLane);",
            "blockers.push(Blocker::WrongBroker);",
            "blockers.push(Blocker::WrongEnvironment);",
            "blockers.push(Blocker::RuntimeEnablementClaimed);",
            "blockers.push(Blocker::ShadowOnlyPostureMissing);",
            "validate_caps(self, &mut blockers);",
            "validate_cash_only_controls(self, &mut blockers);",
            "validate_universe_controls(self, &mut blockers);",
            "validate_cost_model_controls(self, &mut blockers);",
            "validate_paper_order_controls(self, &mut blockers);",
            "blockers.push(Blocker::BybitLiveExecutionNotProtected);",
            "blockers.push(Blocker::IbkrContactPerformed);",
            "blockers.push(Blocker::ConnectorRuntimeStarted);",
            "blockers.push(Blocker::SecretContentSerialized);",
        ),
    )
    _assert_order(
        caps_body,
        (
            "blockers.push(Blocker::OrderCapMissing);",
            "blockers.push(Blocker::PositionCapMissing);",
            "blockers.push(Blocker::DailyCapMissing);",
            "blockers.push(Blocker::CapOrderingInvalid);",
            "blockers.push(Blocker::OpenOrderLimitMissing);",
            "blockers.push(Blocker::OpenOrderLimitTooHigh);",
            "blockers.push(Blocker::OpenPositionLimitMissing);",
            "blockers.push(Blocker::OpenPositionLimitTooHigh);",
        ),
    )
    _assert_order(
        cash_body,
        (
            "blockers.push(Blocker::MarginAllowed);",
            "blockers.push(Blocker::ShortAllowed);",
            "blockers.push(Blocker::OptionsAllowed);",
            "blockers.push(Blocker::CfdAllowed);",
            "blockers.push(Blocker::TransferAllowed);",
            "blockers.push(Blocker::LiveAllowed);",
        ),
    )
    _assert_order(
        universe_body,
        (
            "blockers.push(Blocker::AllowedInstrumentMissing);",
            "blockers.push(Blocker::ForbiddenInstrumentAllowed);",
            "blockers.push(Blocker::DeniedInstrumentMissing);",
            "blockers.push(Blocker::FrozenUniverseHashNotRequired);",
            "blockers.push(Blocker::InstrumentIdentityHashNotRequired);",
            "blockers.push(Blocker::MarketSessionNotRequired);",
        ),
    )
    _assert_order(
        cost_body,
        (
            "blockers.push(Blocker::CostModelBeforeShadowFillMissing);",
            "blockers.push(Blocker::CostModelBeforeScorecardMissing);",
            "blockers.push(Blocker::CommissionScheduleMissing);",
            "blockers.push(Blocker::SpreadEstimateMissing);",
            "blockers.push(Blocker::SlippageEstimateMissing);",
            "blockers.push(Blocker::FxDragMissing);",
            "blockers.push(Blocker::ConservativePenaltyMissing);",
        ),
    )
    _assert_order(
        paper_body,
        (
            "blockers.push(Blocker::RustAuthorityMissing);",
            "blockers.push(Blocker::SessionAttestationMissing);",
            "blockers.push(Blocker::DecisionLeaseMissing);",
            "blockers.push(Blocker::GuardianMissing);",
            "blockers.push(Blocker::IdempotencyKeyMissing);",
            "blockers.push(Blocker::BrokerReconciliationMissing);",
        ),
    )


def test_stock_etf_risk_policy_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    assert "if !self.bybit_live_execution_unchanged" in source
    assert "if self.ibkr_contact_performed" in source
    assert "if self.connector_runtime_started" in source
    assert "if self.secret_content_serialized" in source

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{RISK_POLICY}: contains forbidden token {token!r}")

    assert violations == []


def _assert_order(source: str, tokens: tuple[str, ...]) -> None:
    cursor = -1
    for token in tokens:
        index = source.find(token, cursor + 1)
        assert index > cursor, token
        cursor = index
