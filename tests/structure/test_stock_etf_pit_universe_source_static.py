from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PIT_UNIVERSE = ROOT / "rust/openclaw_types/src/stock_etf_pit_universe.rs"
MAX_LINES = 2_000

REQUIRED_TYPE_TOKENS = {
    'STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID: &str = "stock_etf_pit_universe_contract_v1"',
    "pub struct StockEtfPitUniverseV1",
    "impl Default for StockEtfPitUniverseV1",
    "impl StockEtfPitUniverseV1",
    "pub fn accepted_fixture() -> Self",
    "pub fn validate(&self) -> StockEtfPitUniverseVerdict<StockEtfPitUniverseBlocker>",
    "pub struct StockEtfPitUniverseConstituentV1",
    "impl StockEtfPitUniverseConstituentV1",
    "pub fn fixture(symbol: &str) -> Self",
    "pub struct StockEtfPitUniverseVerdict",
    "pub enum StockEtfPitUniverseBlocker",
    "fn validate_constituent(",
    "fn validate_required_hashes(",
    "fn valid_identifier(value: &str) -> bool",
    "fn valid_symbol(symbol: &str) -> bool",
    "is_sha256_hex",
}
REQUIRED_UNIVERSE_FIELDS = {
    "contract_id",
    "source_version",
    "asset_lane",
    "broker",
    "universe_id",
    "universe_version",
    "universe_hash",
    "point_in_time_asof_ms",
    "effective_from_ms",
    "effective_to_ms",
    "constituent_count",
    "max_constituents",
    "constituents",
    "inclusion_rule_hash",
    "exclusion_rule_hash",
    "liquidity_screen_hash",
    "tradability_screen_hash",
    "priips_screen_hash",
    "delisted_or_inactive_policy_hash",
    "corporate_action_adjustment_version_hash",
    "market_calendar_hash",
    "source_artifact_hash",
    "frozen_for_evidence_clock",
    "survivorship_bias_controls_present",
    "bybit_live_execution_unchanged",
    "ibkr_live_denied",
    "ibkr_contact_performed",
    "secret_content_serialized",
}
REQUIRED_CONSTITUENT_FIELDS = {
    "symbol",
    "instrument_kind",
    "instrument_identity_hash",
    "listing_venue",
    "primary_exchange",
    "currency",
    "tradability_status",
    "priips_kid_status",
    "included",
    "exclusion_reason",
}
REQUIRED_BLOCKERS = {
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "WrongAssetLane",
    "WrongBroker",
    "UniverseIdInvalid",
    "UniverseVersionInvalid",
    "UniverseHashInvalid",
    "PointInTimeAsofMissing",
    "EffectiveFromMissing",
    "EffectiveWindowInvalid",
    "ConstituentCountMissing",
    "ConstituentCountMismatch",
    "MaxConstituentsInvalid",
    "UniverseTooBroadForV1",
    "ConstituentSymbolInvalid",
    "ConstituentKindDenied",
    "ConstituentIdentityHashInvalid",
    "ConstituentVenueDenied",
    "ConstituentCashVenueDenied",
    "ConstituentCurrencyDenied",
    "ConstituentNotTradable",
    "ConstituentPriipsBlocked",
    "ConstituentNotIncluded",
    "IncludedConstituentHasExclusionReason",
    "InclusionRuleHashInvalid",
    "ExclusionRuleHashInvalid",
    "LiquidityScreenHashInvalid",
    "TradabilityScreenHashInvalid",
    "PriipsScreenHashInvalid",
    "DelistedInactivePolicyHashInvalid",
    "CorporateActionVersionHashInvalid",
    "MarketCalendarHashInvalid",
    "SourceArtifactHashInvalid",
    "UniverseNotFrozenForEvidenceClock",
    "SurvivorshipControlsMissing",
    "BybitLiveExecutionNotProtected",
    "IbkrLiveNotDenied",
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
    return PIT_UNIVERSE.read_text(encoding="utf-8")


def test_stock_etf_pit_universe_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_pit_universe_source_keeps_contract_surface() -> None:
    source = _source()

    for token in REQUIRED_TYPE_TOKENS | REQUIRED_UNIVERSE_FIELDS | REQUIRED_CONSTITUENT_FIELDS:
        assert token in source
    for blocker in REQUIRED_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source

    assert "accepted: blockers.is_empty()" in source


def test_stock_etf_pit_universe_source_keeps_fail_closed_default() -> None:
    source = _source()

    assert "contract_id: String::new()" in source
    assert "source_version: 0" in source
    assert "asset_lane: AssetLane::CryptoPerp" in source
    assert "broker: Broker::Bybit" in source
    assert "universe_id: String::new()" in source
    assert "universe_version: String::new()" in source
    assert "universe_hash: String::new()" in source
    assert "point_in_time_asof_ms: 0" in source
    assert "effective_from_ms: 0" in source
    assert "effective_to_ms: 0" in source
    assert "constituent_count: 0" in source
    assert "max_constituents: 0" in source
    assert "constituents: Vec::new()" in source
    assert "frozen_for_evidence_clock: false" in source
    assert "survivorship_bias_controls_present: false" in source
    assert "bybit_live_execution_unchanged: false" in source
    assert "ibkr_live_denied: false" in source
    assert "ibkr_contact_performed: false" in source
    assert "secret_content_serialized: false" in source


def test_stock_etf_pit_universe_source_keeps_accepted_fixture_boundary() -> None:
    source = _source()

    assert "contract_id: STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID.to_string()" in source
    assert "source_version: 1" in source
    assert "asset_lane: AssetLane::StockEtfCash" in source
    assert "broker: Broker::Ibkr" in source
    assert 'universe_id: "US_LARGE_100_V1".to_string()' in source
    assert 'universe_version: "US_LARGE_100_V1_20260301".to_string()' in source
    assert "universe_hash: hash('1')" in source
    assert "point_in_time_asof_ms: 1_772_236_800_000" in source
    assert "effective_from_ms: 1_772_236_800_000" in source
    assert "effective_to_ms: 1_774_828_800_000" in source
    assert "constituent_count: 3" in source
    assert "max_constituents: 100" in source
    assert 'StockEtfPitUniverseConstituentV1::fixture("AMD")' in source
    assert 'StockEtfPitUniverseConstituentV1::fixture("MSFT")' in source
    assert 'StockEtfPitUniverseConstituentV1::fixture("SPY")' in source
    assert "inclusion_rule_hash: hash('2')" in source
    assert "exclusion_rule_hash: hash('3')" in source
    assert "liquidity_screen_hash: hash('4')" in source
    assert "tradability_screen_hash: hash('5')" in source
    assert "priips_screen_hash: hash('6')" in source
    assert "delisted_or_inactive_policy_hash: hash('7')" in source
    assert "corporate_action_adjustment_version_hash: hash('8')" in source
    assert "market_calendar_hash: hash('9')" in source
    assert "source_artifact_hash: hash('a')" in source
    assert "frozen_for_evidence_clock: true" in source
    assert "survivorship_bias_controls_present: true" in source
    assert "bybit_live_execution_unchanged: true" in source
    assert "ibkr_live_denied: true" in source
    assert "ibkr_contact_performed: false" in source
    assert "secret_content_serialized: false" in source


def test_stock_etf_pit_universe_fixture_excludes_source_freeze_and_authority_crosswire() -> None:
    source = _source()
    fixture = source.split("impl StockEtfPitUniverseV1", 1)[1].split(
        "pub fn validate(&self)",
        1,
    )[0]
    default_impl = source.split("impl Default for StockEtfPitUniverseV1", 1)[1].split(
        "impl StockEtfPitUniverseV1",
        1,
    )[0]

    for forbidden in (
        "asset_lane: AssetLane::CryptoPerp",
        "broker: Broker::Bybit",
        "universe_id: String::new()",
        "universe_version: String::new()",
        "universe_hash: String::new()",
        "point_in_time_asof_ms: 0",
        "effective_from_ms: 0",
        "constituent_count: 0",
        "max_constituents: 0",
        "constituents: Vec::new()",
        "frozen_for_evidence_clock: false",
        "survivorship_bias_controls_present: false",
        "bybit_live_execution_unchanged: false",
        "ibkr_live_denied: false",
        "ibkr_contact_performed: true",
        "secret_content_serialized: true",
    ):
        assert forbidden not in fixture

    for fail_closed in (
        "asset_lane: AssetLane::CryptoPerp",
        "broker: Broker::Bybit",
        "universe_id: String::new()",
        "universe_version: String::new()",
        "universe_hash: String::new()",
        "point_in_time_asof_ms: 0",
        "effective_from_ms: 0",
        "constituent_count: 0",
        "max_constituents: 0",
        "constituents: Vec::new()",
        "frozen_for_evidence_clock: false",
        "survivorship_bias_controls_present: false",
        "bybit_live_execution_unchanged: false",
        "ibkr_live_denied: false",
        "ibkr_contact_performed: false",
        "secret_content_serialized: false",
    ):
        assert fail_closed in default_impl


def test_stock_etf_pit_universe_source_keeps_universe_validation_matrix() -> None:
    source = _source()

    assert "self.contract_id != STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID" in source
    assert "self.source_version != 1" in source
    assert "self.asset_lane != AssetLane::StockEtfCash" in source
    assert "self.broker != Broker::Ibkr" in source
    assert "!valid_identifier(&self.universe_id)" in source
    assert "!valid_identifier(&self.universe_version)" in source
    assert "!is_sha256_hex(&self.universe_hash)" in source
    assert "self.point_in_time_asof_ms == 0" in source
    assert "self.effective_from_ms == 0" in source
    assert "self.effective_to_ms != 0 && self.effective_to_ms <= self.effective_from_ms" in source
    assert "self.constituent_count == 0 || self.constituents.is_empty()" in source
    assert "self.constituent_count as usize != self.constituents.len()" in source
    assert "self.max_constituents == 0 || self.constituent_count > self.max_constituents" in source
    assert "self.max_constituents > 500" in source
    assert "validate_constituent(constituent, &mut blockers)" in source
    assert "validate_required_hashes(self, &mut blockers)" in source
    assert "!self.frozen_for_evidence_clock" in source
    assert "!self.survivorship_bias_controls_present" in source
    assert "!self.bybit_live_execution_unchanged" in source
    assert "!self.ibkr_live_denied" in source
    assert "self.ibkr_contact_performed" in source
    assert "self.secret_content_serialized" in source


def test_stock_etf_pit_universe_source_keeps_blocker_emit_order() -> None:
    source = _source()
    validate_body = source.split("pub fn validate(&self)", 1)[1].split(
        "StockEtfPitUniverseVerdict::new",
        1,
    )[0]
    constituent_body = source.split("fn validate_constituent(", 1)[1].split(
        "fn validate_required_hashes(",
        1,
    )[0]
    hash_body = source.split("fn validate_required_hashes(", 1)[1].split(
        "fn valid_identifier(",
        1,
    )[0]

    _assert_order(
        validate_body,
        (
            "blockers.push(Blocker::ContractIdMismatch);",
            "blockers.push(Blocker::SourceVersionMismatch);",
            "blockers.push(Blocker::WrongAssetLane);",
            "blockers.push(Blocker::WrongBroker);",
            "blockers.push(Blocker::UniverseIdInvalid);",
            "blockers.push(Blocker::UniverseVersionInvalid);",
            "blockers.push(Blocker::UniverseHashInvalid);",
            "blockers.push(Blocker::PointInTimeAsofMissing);",
            "blockers.push(Blocker::EffectiveFromMissing);",
            "blockers.push(Blocker::EffectiveWindowInvalid);",
            "blockers.push(Blocker::ConstituentCountMissing);",
            "blockers.push(Blocker::ConstituentCountMismatch);",
            "blockers.push(Blocker::MaxConstituentsInvalid);",
            "blockers.push(Blocker::UniverseTooBroadForV1);",
            "validate_constituent(constituent, &mut blockers)",
            "validate_required_hashes(self, &mut blockers)",
            "blockers.push(Blocker::UniverseNotFrozenForEvidenceClock);",
            "blockers.push(Blocker::SurvivorshipControlsMissing);",
            "blockers.push(Blocker::BybitLiveExecutionNotProtected);",
            "blockers.push(Blocker::IbkrLiveNotDenied);",
            "blockers.push(Blocker::IbkrContactPerformed);",
            "blockers.push(Blocker::SecretContentSerialized);",
        ),
    )
    _assert_order(
        constituent_body,
        (
            "blockers.push(Blocker::ConstituentSymbolInvalid);",
            "blockers.push(Blocker::ConstituentKindDenied);",
            "blockers.push(Blocker::ConstituentIdentityHashInvalid);",
            "blockers.push(Blocker::ConstituentVenueDenied);",
            "blockers.push(Blocker::ConstituentCashVenueDenied);",
            "blockers.push(Blocker::ConstituentCurrencyDenied);",
            "blockers.push(Blocker::ConstituentNotTradable);",
            "blockers.push(Blocker::ConstituentPriipsBlocked);",
            "blockers.push(Blocker::ConstituentNotIncluded);",
            "blockers.push(Blocker::IncludedConstituentHasExclusionReason);",
        ),
    )
    _assert_order(
        hash_body,
        (
            "blockers.push(Blocker::InclusionRuleHashInvalid);",
            "blockers.push(Blocker::ExclusionRuleHashInvalid);",
            "blockers.push(Blocker::LiquidityScreenHashInvalid);",
            "blockers.push(Blocker::TradabilityScreenHashInvalid);",
            "blockers.push(Blocker::PriipsScreenHashInvalid);",
            "blockers.push(Blocker::DelistedInactivePolicyHashInvalid);",
            "blockers.push(Blocker::CorporateActionVersionHashInvalid);",
            "blockers.push(Blocker::MarketCalendarHashInvalid);",
            "blockers.push(Blocker::SourceArtifactHashInvalid);",
        ),
    )


def test_stock_etf_pit_universe_source_keeps_constituent_and_hash_checks() -> None:
    source = _source()

    assert "!valid_symbol(&constituent.symbol)" in source
    assert "InstrumentKind::Stock | InstrumentKind::Etf" in source
    assert "!is_sha256_hex(&constituent.instrument_identity_hash)" in source
    assert "constituent.listing_venue == StockEtfListingVenue::UnknownDenied" in source
    assert "constituent.primary_exchange == StockEtfListingVenue::UnknownDenied" in source
    assert "constituent.listing_venue == StockEtfListingVenue::CashLedger" in source
    assert "constituent.primary_exchange == StockEtfListingVenue::CashLedger" in source
    assert "constituent.currency != StockEtfCurrency::Usd" in source
    assert "constituent.tradability_status != StockEtfTradabilityStatus::Tradable" in source
    assert "StockEtfPriipsKidStatus::MissingBlocked | StockEtfPriipsKidStatus::UnknownDenied" in source
    assert "!constituent.included" in source
    assert "constituent.included && !constituent.exclusion_reason.trim().is_empty()" in source
    for hash_field in (
        "inclusion_rule_hash",
        "exclusion_rule_hash",
        "liquidity_screen_hash",
        "tradability_screen_hash",
        "priips_screen_hash",
        "delisted_or_inactive_policy_hash",
        "corporate_action_adjustment_version_hash",
        "market_calendar_hash",
        "source_artifact_hash",
    ):
        assert f"!is_sha256_hex(&universe.{hash_field})" in source


def test_stock_etf_pit_universe_source_keeps_identifier_and_symbol_rules() -> None:
    source = _source()

    assert "trimmed == value" in source
    assert "trimmed.len() <= 64" in source
    assert "matches!(ch, '_' | '-')" in source
    assert "trimmed == symbol" in source
    assert "trimmed.len() <= 24" in source
    assert "matches!(ch, '.' | '-')" in source


def test_stock_etf_pit_universe_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{PIT_UNIVERSE}: contains forbidden token {token!r}")

    assert violations == []


def _assert_order(source: str, tokens: tuple[str, ...]) -> None:
    cursor = -1
    for token in tokens:
        index = source.find(token, cursor + 1)
        assert index > cursor, token
        cursor = index
