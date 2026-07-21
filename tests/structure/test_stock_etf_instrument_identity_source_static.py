from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INSTRUMENT_IDENTITY = ROOT / "rust/openclaw_types/src/stock_etf_instrument_identity.rs"
from tests.structure.file_line_policy import MAX_FILE_LINES as MAX_LINES

REQUIRED_TYPE_TOKENS = {
    'STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID: &str = "instrument_identity_contract_v1"',
    "pub struct StockEtfInstrumentIdentityV1",
    "impl Default for StockEtfInstrumentIdentityV1",
    "impl StockEtfInstrumentIdentityV1",
    "pub fn accepted_fixture() -> Self",
    "pub fn validate(&self) -> StockEtfInstrumentIdentityVerdict<StockEtfInstrumentIdentityBlocker>",
    "pub enum StockEtfListingVenue",
    "pub enum StockEtfCurrency",
    "pub enum StockEtfTradabilityStatus",
    "pub enum StockEtfPriipsKidStatus",
    "pub struct StockEtfInstrumentIdentityVerdict",
    "pub enum StockEtfInstrumentIdentityBlocker",
    "fn validate_cash_venue_pair(",
    "fn valid_symbol(symbol: &str) -> bool",
    "is_sha256_hex",
}
REQUIRED_FIELDS = {
    "contract_id",
    "source_version",
    "asset_lane",
    "broker",
    "instrument_kind",
    "symbol",
    "listing_venue",
    "primary_exchange",
    "currency",
    "tradability_status",
    "priips_kid_status",
    "fractional_policy_recorded",
    "point_in_time_asof_ms",
    "market_calendar_id",
    "market_calendar_hash",
    "broker_contract_details_hash",
    "instrument_identity_hash",
    "corporate_action_adjustment_version_hash",
    "source_artifact_hash",
    "bybit_live_execution_unchanged",
    "ibkr_live_denied",
    "margin_short_denied",
    "options_cfd_denied",
    "ibkr_contact_performed",
    "secret_content_serialized",
}
REQUIRED_ENUM_VALUES = {
    "InstrumentKind::Stock",
    "InstrumentKind::Etf",
    "InstrumentKind::Cash",
    "InstrumentKind::CryptoPerp",
    "    Xnys,",
    "StockEtfListingVenue::Xnas",
    "    Arcx,",
    "    Bats,",
    "    Xase,",
    "StockEtfListingVenue::CashLedger",
    "StockEtfListingVenue::UnknownDenied",
    "StockEtfCurrency::Usd",
    "StockEtfCurrency::UnknownDenied",
    "StockEtfTradabilityStatus::Tradable",
    "    Blocked,",
    "    Halted,",
    "StockEtfTradabilityStatus::UnknownDenied",
    "StockEtfPriipsKidStatus::NotRequired",
    "    Present,",
    "StockEtfPriipsKidStatus::MissingBlocked",
    "StockEtfPriipsKidStatus::UnknownDenied",
}
REQUIRED_BLOCKERS = {
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "WrongAssetLane",
    "WrongBroker",
    "InstrumentKindDenied",
    "SymbolInvalid",
    "ListingVenueDenied",
    "PrimaryExchangeDenied",
    "CashInstrumentVenueMismatch",
    "NonCashInstrumentVenueMismatch",
    "CurrencyDenied",
    "TradabilityNotTradable",
    "PriipsKidBlocked",
    "FractionalPolicyMissing",
    "PointInTimeAsofMissing",
    "MarketCalendarIdMissing",
    "MarketCalendarHashInvalid",
    "BrokerContractDetailsHashInvalid",
    "InstrumentIdentityHashInvalid",
    "CorporateActionAdjustmentHashInvalid",
    "SourceArtifactHashInvalid",
    "BybitLiveExecutionNotProtected",
    "IbkrLiveNotDenied",
    "MarginShortNotDenied",
    "OptionsCfdNotDenied",
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
    return INSTRUMENT_IDENTITY.read_text(encoding="utf-8")


def test_stock_etf_instrument_identity_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_instrument_identity_source_keeps_contract_surface() -> None:
    source = _source()

    for token in REQUIRED_TYPE_TOKENS | REQUIRED_FIELDS | REQUIRED_ENUM_VALUES:
        assert token in source
    for blocker in REQUIRED_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source

    assert "accepted: blockers.is_empty()" in source


def test_stock_etf_instrument_identity_source_keeps_fail_closed_default() -> None:
    source = _source()

    assert "contract_id: String::new()" in source
    assert "source_version: 0" in source
    assert "asset_lane: AssetLane::CryptoPerp" in source
    assert "broker: Broker::Bybit" in source
    assert "instrument_kind: InstrumentKind::CryptoPerp" in source
    assert "symbol: String::new()" in source
    assert "listing_venue: StockEtfListingVenue::UnknownDenied" in source
    assert "primary_exchange: StockEtfListingVenue::UnknownDenied" in source
    assert "currency: StockEtfCurrency::UnknownDenied" in source
    assert "tradability_status: StockEtfTradabilityStatus::UnknownDenied" in source
    assert "priips_kid_status: StockEtfPriipsKidStatus::UnknownDenied" in source
    assert "fractional_policy_recorded: false" in source
    assert "point_in_time_asof_ms: 0" in source
    assert "bybit_live_execution_unchanged: false" in source
    assert "ibkr_live_denied: false" in source
    assert "margin_short_denied: false" in source
    assert "options_cfd_denied: false" in source
    assert "ibkr_contact_performed: false" in source
    assert "secret_content_serialized: false" in source


def test_stock_etf_instrument_identity_source_keeps_accepted_fixture_boundary() -> None:
    source = _source()

    assert "contract_id: STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID.to_string()" in source
    assert "source_version: 1" in source
    assert "asset_lane: AssetLane::StockEtfCash" in source
    assert "broker: Broker::Ibkr" in source
    assert "instrument_kind: InstrumentKind::Stock" in source
    assert 'symbol: "AMD".to_string()' in source
    assert "listing_venue: StockEtfListingVenue::Xnas" in source
    assert "primary_exchange: StockEtfListingVenue::Xnas" in source
    assert "currency: StockEtfCurrency::Usd" in source
    assert "tradability_status: StockEtfTradabilityStatus::Tradable" in source
    assert "priips_kid_status: StockEtfPriipsKidStatus::NotRequired" in source
    assert "fractional_policy_recorded: true" in source
    assert "point_in_time_asof_ms: 1_772_236_800_000" in source
    assert 'market_calendar_id: "XNAS-2026-03-01-regular".to_string()' in source
    assert "market_calendar_hash: hash('1')" in source
    assert "broker_contract_details_hash: hash('2')" in source
    assert "instrument_identity_hash: hash('3')" in source
    assert "corporate_action_adjustment_version_hash: hash('4')" in source
    assert "source_artifact_hash: hash('5')" in source
    assert "bybit_live_execution_unchanged: true" in source
    assert "ibkr_live_denied: true" in source
    assert "margin_short_denied: true" in source
    assert "options_cfd_denied: true" in source
    assert "ibkr_contact_performed: false" in source
    assert "secret_content_serialized: false" in source


def test_stock_etf_instrument_identity_fixture_excludes_live_margin_and_secret_crosswire() -> None:
    source = _source()
    fixture = source.split("impl StockEtfInstrumentIdentityV1", 1)[1].split(
        "pub fn validate(&self)",
        1,
    )[0]
    default_impl = source.split("impl Default for StockEtfInstrumentIdentityV1", 1)[1].split(
        "impl StockEtfInstrumentIdentityV1",
        1,
    )[0]

    for forbidden in (
        "asset_lane: AssetLane::CryptoPerp",
        "broker: Broker::Bybit",
        "instrument_kind: InstrumentKind::CryptoPerp",
        "symbol: String::new()",
        "listing_venue: StockEtfListingVenue::UnknownDenied",
        "primary_exchange: StockEtfListingVenue::UnknownDenied",
        "currency: StockEtfCurrency::UnknownDenied",
        "tradability_status: StockEtfTradabilityStatus::UnknownDenied",
        "priips_kid_status: StockEtfPriipsKidStatus::UnknownDenied",
        "fractional_policy_recorded: false",
        "point_in_time_asof_ms: 0",
        "market_calendar_id: String::new()",
        "bybit_live_execution_unchanged: false",
        "ibkr_live_denied: false",
        "margin_short_denied: false",
        "options_cfd_denied: false",
        "ibkr_contact_performed: true",
        "secret_content_serialized: true",
    ):
        assert forbidden not in fixture

    for fail_closed in (
        "asset_lane: AssetLane::CryptoPerp",
        "broker: Broker::Bybit",
        "instrument_kind: InstrumentKind::CryptoPerp",
        "symbol: String::new()",
        "listing_venue: StockEtfListingVenue::UnknownDenied",
        "primary_exchange: StockEtfListingVenue::UnknownDenied",
        "currency: StockEtfCurrency::UnknownDenied",
        "tradability_status: StockEtfTradabilityStatus::UnknownDenied",
        "priips_kid_status: StockEtfPriipsKidStatus::UnknownDenied",
        "fractional_policy_recorded: false",
        "point_in_time_asof_ms: 0",
        "market_calendar_id: String::new()",
        "bybit_live_execution_unchanged: false",
        "ibkr_live_denied: false",
        "margin_short_denied: false",
        "options_cfd_denied: false",
        "ibkr_contact_performed: false",
        "secret_content_serialized: false",
    ):
        assert fail_closed in default_impl


def test_stock_etf_instrument_identity_source_keeps_validation_matrix() -> None:
    source = _source()

    assert "self.contract_id != STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID" in source
    assert "self.source_version != 1" in source
    assert "self.asset_lane != AssetLane::StockEtfCash" in source
    assert "self.broker != Broker::Ibkr" in source
    assert "InstrumentKind::Stock | InstrumentKind::Etf | InstrumentKind::Cash" in source
    assert "!valid_symbol(&self.symbol)" in source
    assert "self.listing_venue == StockEtfListingVenue::UnknownDenied" in source
    assert "self.primary_exchange == StockEtfListingVenue::UnknownDenied" in source
    assert "validate_cash_venue_pair(" in source
    assert "self.currency != StockEtfCurrency::Usd" in source
    assert "self.tradability_status != StockEtfTradabilityStatus::Tradable" in source
    assert "StockEtfPriipsKidStatus::MissingBlocked | StockEtfPriipsKidStatus::UnknownDenied" in source
    assert "!self.fractional_policy_recorded" in source
    assert "self.point_in_time_asof_ms == 0" in source
    assert "self.market_calendar_id.trim().is_empty()" in source
    assert "!is_sha256_hex(&self.market_calendar_hash)" in source
    assert "!is_sha256_hex(&self.broker_contract_details_hash)" in source
    assert "!is_sha256_hex(&self.instrument_identity_hash)" in source
    assert "!is_sha256_hex(&self.corporate_action_adjustment_version_hash)" in source
    assert "!is_sha256_hex(&self.source_artifact_hash)" in source
    assert "!self.bybit_live_execution_unchanged" in source
    assert "!self.ibkr_live_denied" in source
    assert "!self.margin_short_denied" in source
    assert "!self.options_cfd_denied" in source
    assert "self.ibkr_contact_performed" in source
    assert "self.secret_content_serialized" in source


def test_stock_etf_instrument_identity_source_keeps_blocker_emit_order() -> None:
    source = _source()
    validate_body = source.split("pub fn validate(&self)", 1)[1].split(
        "StockEtfInstrumentIdentityVerdict::new",
        1,
    )[0]
    cash_rules = source.split("fn validate_cash_venue_pair(", 1)[1].split(
        "fn valid_symbol(",
        1,
    )[0]

    _assert_order(
        validate_body,
        (
            "blockers.push(Blocker::ContractIdMismatch);",
            "blockers.push(Blocker::SourceVersionMismatch);",
            "blockers.push(Blocker::WrongAssetLane);",
            "blockers.push(Blocker::WrongBroker);",
            "blockers.push(Blocker::InstrumentKindDenied);",
            "blockers.push(Blocker::SymbolInvalid);",
            "blockers.push(Blocker::ListingVenueDenied);",
            "blockers.push(Blocker::PrimaryExchangeDenied);",
            "validate_cash_venue_pair(",
            "blockers.push(Blocker::CurrencyDenied);",
            "blockers.push(Blocker::TradabilityNotTradable);",
            "blockers.push(Blocker::PriipsKidBlocked);",
            "blockers.push(Blocker::FractionalPolicyMissing);",
            "blockers.push(Blocker::PointInTimeAsofMissing);",
            "blockers.push(Blocker::MarketCalendarIdMissing);",
            "blockers.push(Blocker::MarketCalendarHashInvalid);",
            "blockers.push(Blocker::BrokerContractDetailsHashInvalid);",
            "blockers.push(Blocker::InstrumentIdentityHashInvalid);",
            "blockers.push(Blocker::CorporateActionAdjustmentHashInvalid);",
            "blockers.push(Blocker::SourceArtifactHashInvalid);",
            "blockers.push(Blocker::BybitLiveExecutionNotProtected);",
            "blockers.push(Blocker::IbkrLiveNotDenied);",
            "blockers.push(Blocker::MarginShortNotDenied);",
            "blockers.push(Blocker::OptionsCfdNotDenied);",
            "blockers.push(Blocker::IbkrContactPerformed);",
            "blockers.push(Blocker::SecretContentSerialized);",
        ),
    )
    _assert_order(
        cash_rules,
        (
            "blockers.push(Blocker::CashInstrumentVenueMismatch);",
            "blockers.push(Blocker::NonCashInstrumentVenueMismatch);",
        ),
    )


def test_stock_etf_instrument_identity_source_keeps_cash_and_symbol_rules() -> None:
    source = _source()

    assert "if instrument_kind == InstrumentKind::Cash" in source
    assert "listing_venue != StockEtfListingVenue::CashLedger" in source
    assert "primary_exchange != StockEtfListingVenue::CashLedger" in source
    assert "listing_venue == StockEtfListingVenue::CashLedger" in source
    assert "primary_exchange == StockEtfListingVenue::CashLedger" in source
    assert "trimmed == symbol" in source
    assert "trimmed.len() <= 24" in source
    assert "ch.is_ascii_uppercase() || ch.is_ascii_digit() || matches!(ch, '.' | '-')" in source


def test_stock_etf_instrument_identity_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{INSTRUMENT_IDENTITY}: contains forbidden token {token!r}")

    assert violations == []


def _assert_order(source: str, tokens: tuple[str, ...]) -> None:
    cursor = -1
    for token in tokens:
        index = source.find(token, cursor + 1)
        assert index > cursor, token
        cursor = index
