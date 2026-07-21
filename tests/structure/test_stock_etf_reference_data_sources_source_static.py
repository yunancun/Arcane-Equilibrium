from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REFERENCE_SOURCES = ROOT / "rust/openclaw_types/src/stock_etf_reference_data_sources.rs"
from tests.structure.file_line_policy import MAX_FILE_LINES as MAX_LINES

REQUIRED_TYPE_TOKENS = {
    "STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID",
    '"stock_etf_reference_data_sources_v1"',
    "pub struct StockEtfReferenceDataSourcesV1",
    "impl Default for StockEtfReferenceDataSourcesV1",
    "impl StockEtfReferenceDataSourcesV1",
    "pub fn accepted_fixture() -> Self",
    "pub fn validate(",
    "fn validate_corporate_action_sources(",
    "fn validate_fx_sources(",
    "fn validate_fee_tax_sources(",
    "pub struct StockEtfReferenceDataSourcesVerdict",
    "pub enum StockEtfReferenceDataSourcesBlocker",
    "is_sha256_hex",
}
REQUIRED_FIELDS = {
    "contract_id",
    "source_version",
    "asset_lane",
    "broker",
    "environment",
    "frozen_for_evidence_clock",
    "corporate_action_source_name",
    "corporate_action_asof_ms",
    "corporate_action_raw_hash",
    "corporate_action_adjustment_version_hash",
    "corporate_action_policy_hash",
    "dividend_treatment_hash",
    "fx_rate_source_name",
    "fx_rate_asof_ms",
    "base_currency",
    "quote_currency",
    "fx_rate_snapshot_hash",
    "fx_drag_model_hash",
    "fee_schedule_source_name",
    "fee_schedule_asof_ms",
    "commission_schedule_hash",
    "exchange_regulatory_fee_hash",
    "tax_ftt_placeholder_hash",
    "withholding_tax_treatment_hash",
    "source_artifact_hash",
    "bybit_live_execution_unchanged",
    "ibkr_contact_performed",
    "connector_runtime_started",
    "secret_content_serialized",
    "live_or_tiny_live_authorized",
}
REQUIRED_BLOCKERS = {
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "WrongAssetLane",
    "WrongBroker",
    "EnvironmentDenied",
    "EvidenceClockFreezeMissing",
    "CorporateActionSourceMissing",
    "CorporateActionAsOfMissing",
    "CorporateActionRawHashInvalid",
    "CorporateActionAdjustmentHashInvalid",
    "CorporateActionPolicyHashInvalid",
    "DividendTreatmentHashInvalid",
    "FxRateSourceMissing",
    "FxRateAsOfMissing",
    "CurrencyDenied",
    "FxRateSnapshotHashInvalid",
    "FxDragModelHashInvalid",
    "FeeScheduleSourceMissing",
    "FeeScheduleAsOfMissing",
    "CommissionScheduleHashInvalid",
    "ExchangeRegulatoryFeeHashInvalid",
    "TaxFttPlaceholderHashInvalid",
    "WithholdingTaxTreatmentHashInvalid",
    "SourceArtifactHashInvalid",
    "BybitLiveExecutionNotProtected",
    "IbkrContactPerformed",
    "ConnectorRuntimeStarted",
    "SecretContentSerialized",
    "LiveOrTinyLiveAuthorized",
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
    return REFERENCE_SOURCES.read_text(encoding="utf-8")


def test_stock_etf_reference_data_sources_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_reference_data_sources_source_keeps_contract_surface() -> None:
    source = _source()

    for token in REQUIRED_TYPE_TOKENS | REQUIRED_FIELDS:
        assert token in source
    for blocker in REQUIRED_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source

    assert "accepted: blockers.is_empty()" in source


def test_stock_etf_reference_data_sources_source_keeps_fail_closed_default() -> None:
    source = _source()

    assert "contract_id: String::new()" in source
    assert "source_version: 0" in source
    assert "asset_lane: AssetLane::CryptoPerp" in source
    assert "broker: Broker::Bybit" in source
    assert "environment: BrokerEnvironment::LiveReservedDenied" in source
    assert "frozen_for_evidence_clock: false" in source
    assert "corporate_action_source_name: String::new()" in source
    assert "corporate_action_asof_ms: 0" in source
    assert "fx_rate_source_name: String::new()" in source
    assert "fx_rate_asof_ms: 0" in source
    assert "base_currency: StockEtfCurrency::UnknownDenied" in source
    assert "quote_currency: StockEtfCurrency::UnknownDenied" in source
    assert "fee_schedule_source_name: String::new()" in source
    assert "fee_schedule_asof_ms: 0" in source
    assert "bybit_live_execution_unchanged: false" in source
    assert "ibkr_contact_performed: false" in source
    assert "connector_runtime_started: false" in source
    assert "secret_content_serialized: false" in source
    assert "live_or_tiny_live_authorized: true" in source


def test_stock_etf_reference_data_sources_source_keeps_accepted_fixture_boundary() -> None:
    source = _source()

    assert "contract_id: STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID.to_string()" in source
    assert "source_version: 1" in source
    assert "asset_lane: AssetLane::StockEtfCash" in source
    assert "broker: Broker::Ibkr" in source
    assert "environment: BrokerEnvironment::Paper" in source
    assert "frozen_for_evidence_clock: true" in source
    assert (
        'corporate_action_source_name: "ibkr_contract_details_and_reference_feed".to_string()'
        in source
    )
    assert "corporate_action_asof_ms: 1_772_236_800_000" in source
    assert "corporate_action_raw_hash: hash('1')" in source
    assert "corporate_action_adjustment_version_hash: hash('2')" in source
    assert "corporate_action_policy_hash: hash('3')" in source
    assert "dividend_treatment_hash: hash('4')" in source
    assert 'fx_rate_source_name: "ibkr_paper_cash_ledger_usd_reference".to_string()' in source
    assert "fx_rate_asof_ms: 1_772_236_800_000" in source
    assert "base_currency: StockEtfCurrency::Usd" in source
    assert "quote_currency: StockEtfCurrency::Usd" in source
    assert "fx_rate_snapshot_hash: hash('5')" in source
    assert "fx_drag_model_hash: hash('6')" in source
    assert 'fee_schedule_source_name: "ibkr_paper_us_stock_etf_fee_schedule".to_string()' in source
    assert "fee_schedule_asof_ms: 1_772_236_800_000" in source
    assert "commission_schedule_hash: hash('7')" in source
    assert "exchange_regulatory_fee_hash: hash('8')" in source
    assert "tax_ftt_placeholder_hash: hash('9')" in source
    assert "withholding_tax_treatment_hash: hash('a')" in source
    assert "source_artifact_hash: hash('b')" in source
    assert "bybit_live_execution_unchanged: true" in source
    assert "ibkr_contact_performed: false" in source
    assert "connector_runtime_started: false" in source
    assert "secret_content_serialized: false" in source
    assert "live_or_tiny_live_authorized: false" in source


def test_stock_etf_reference_data_sources_fixture_excludes_runtime_and_authority_crosswire() -> None:
    source = _source()
    fixture = source.split("impl StockEtfReferenceDataSourcesV1", 1)[1].split(
        "pub fn validate(",
        1,
    )[0]
    default_impl = source.split("impl Default for StockEtfReferenceDataSourcesV1", 1)[1].split(
        "impl StockEtfReferenceDataSourcesV1",
        1,
    )[0]

    for forbidden in (
        "environment: BrokerEnvironment::LiveReservedDenied",
        "frozen_for_evidence_clock: false",
        "corporate_action_source_name: String::new()",
        "corporate_action_asof_ms: 0",
        "fx_rate_source_name: String::new()",
        "fx_rate_asof_ms: 0",
        "base_currency: StockEtfCurrency::UnknownDenied",
        "quote_currency: StockEtfCurrency::UnknownDenied",
        "fee_schedule_source_name: String::new()",
        "fee_schedule_asof_ms: 0",
        "bybit_live_execution_unchanged: false",
        "ibkr_contact_performed: true",
        "connector_runtime_started: true",
        "secret_content_serialized: true",
        "live_or_tiny_live_authorized: true",
    ):
        assert forbidden not in fixture

    for fail_closed in (
        "environment: BrokerEnvironment::LiveReservedDenied",
        "frozen_for_evidence_clock: false",
        "corporate_action_source_name: String::new()",
        "corporate_action_asof_ms: 0",
        "fx_rate_source_name: String::new()",
        "fx_rate_asof_ms: 0",
        "base_currency: StockEtfCurrency::UnknownDenied",
        "quote_currency: StockEtfCurrency::UnknownDenied",
        "fee_schedule_source_name: String::new()",
        "fee_schedule_asof_ms: 0",
        "bybit_live_execution_unchanged: false",
        "ibkr_contact_performed: false",
        "connector_runtime_started: false",
        "secret_content_serialized: false",
        "live_or_tiny_live_authorized: true",
    ):
        assert fail_closed in default_impl


def test_stock_etf_reference_data_sources_source_keeps_validation_matrix() -> None:
    source = _source()

    assert "self.contract_id != STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID" in source
    assert "self.source_version != 1" in source
    assert "self.asset_lane != AssetLane::StockEtfCash" in source
    assert "self.broker != Broker::Ibkr" in source
    assert (
        "BrokerEnvironment::ReadOnly | BrokerEnvironment::Paper | BrokerEnvironment::Shadow"
        in source
    )
    assert "!self.frozen_for_evidence_clock" in source
    assert "validate_corporate_action_sources(self, &mut blockers)" in source
    assert "validate_fx_sources(self, &mut blockers)" in source
    assert "validate_fee_tax_sources(self, &mut blockers)" in source
    assert "!is_sha256_hex(&self.source_artifact_hash)" in source
    assert "!self.bybit_live_execution_unchanged" in source
    assert "self.ibkr_contact_performed" in source
    assert "self.connector_runtime_started" in source
    assert "self.secret_content_serialized" in source
    assert "self.live_or_tiny_live_authorized" in source


def test_stock_etf_reference_data_sources_source_keeps_blocker_emit_order() -> None:
    source = _source()
    validate_body = source.split("pub fn validate(", 1)[1].split(
        "StockEtfReferenceDataSourcesVerdict::new",
        1,
    )[0]
    corporate_body = source.split("fn validate_corporate_action_sources(", 1)[1].split(
        "fn validate_fx_sources(",
        1,
    )[0]
    fx_body = source.split("fn validate_fx_sources(", 1)[1].split(
        "fn validate_fee_tax_sources(",
        1,
    )[0]
    fee_body = source.split("fn validate_fee_tax_sources(", 1)[1].split(
        "fn hash(",
        1,
    )[0]

    _assert_order(
        validate_body,
        (
            "blockers.push(Blocker::ContractIdMismatch);",
            "blockers.push(Blocker::SourceVersionMismatch);",
            "blockers.push(Blocker::WrongAssetLane);",
            "blockers.push(Blocker::WrongBroker);",
            "blockers.push(Blocker::EnvironmentDenied);",
            "blockers.push(Blocker::EvidenceClockFreezeMissing);",
            "validate_corporate_action_sources(self, &mut blockers)",
            "validate_fx_sources(self, &mut blockers)",
            "validate_fee_tax_sources(self, &mut blockers)",
            "blockers.push(Blocker::SourceArtifactHashInvalid);",
            "blockers.push(Blocker::BybitLiveExecutionNotProtected);",
            "blockers.push(Blocker::IbkrContactPerformed);",
            "blockers.push(Blocker::ConnectorRuntimeStarted);",
            "blockers.push(Blocker::SecretContentSerialized);",
            "blockers.push(Blocker::LiveOrTinyLiveAuthorized);",
        ),
    )
    _assert_order(
        corporate_body,
        (
            "blockers.push(Blocker::CorporateActionSourceMissing);",
            "blockers.push(Blocker::CorporateActionAsOfMissing);",
            "blockers.push(Blocker::CorporateActionRawHashInvalid);",
            "blockers.push(Blocker::CorporateActionAdjustmentHashInvalid);",
            "blockers.push(Blocker::CorporateActionPolicyHashInvalid);",
            "blockers.push(Blocker::DividendTreatmentHashInvalid);",
        ),
    )
    _assert_order(
        fx_body,
        (
            "blockers.push(Blocker::FxRateSourceMissing);",
            "blockers.push(Blocker::FxRateAsOfMissing);",
            "blockers.push(Blocker::CurrencyDenied);",
            "blockers.push(Blocker::FxRateSnapshotHashInvalid);",
            "blockers.push(Blocker::FxDragModelHashInvalid);",
        ),
    )
    _assert_order(
        fee_body,
        (
            "blockers.push(Blocker::FeeScheduleSourceMissing);",
            "blockers.push(Blocker::FeeScheduleAsOfMissing);",
            "blockers.push(Blocker::CommissionScheduleHashInvalid);",
            "blockers.push(Blocker::ExchangeRegulatoryFeeHashInvalid);",
            "blockers.push(Blocker::TaxFttPlaceholderHashInvalid);",
            "blockers.push(Blocker::WithholdingTaxTreatmentHashInvalid);",
        ),
    )


def test_stock_etf_reference_data_sources_source_keeps_source_family_checks() -> None:
    source = _source()

    assert "sources.corporate_action_source_name.trim().is_empty()" in source
    assert "sources.corporate_action_asof_ms == 0" in source
    assert "!is_sha256_hex(&sources.corporate_action_raw_hash)" in source
    assert "!is_sha256_hex(&sources.corporate_action_adjustment_version_hash)" in source
    assert "!is_sha256_hex(&sources.corporate_action_policy_hash)" in source
    assert "!is_sha256_hex(&sources.dividend_treatment_hash)" in source
    assert "sources.fx_rate_source_name.trim().is_empty()" in source
    assert "sources.fx_rate_asof_ms == 0" in source
    assert "sources.base_currency != StockEtfCurrency::Usd" in source
    assert "sources.quote_currency != StockEtfCurrency::Usd" in source
    assert "!is_sha256_hex(&sources.fx_rate_snapshot_hash)" in source
    assert "!is_sha256_hex(&sources.fx_drag_model_hash)" in source
    assert "sources.fee_schedule_source_name.trim().is_empty()" in source
    assert "sources.fee_schedule_asof_ms == 0" in source
    assert "!is_sha256_hex(&sources.commission_schedule_hash)" in source
    assert "!is_sha256_hex(&sources.exchange_regulatory_fee_hash)" in source
    assert "!is_sha256_hex(&sources.tax_ftt_placeholder_hash)" in source
    assert "!is_sha256_hex(&sources.withholding_tax_treatment_hash)" in source


def test_stock_etf_reference_data_sources_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{REFERENCE_SOURCES}: contains forbidden token {token!r}")

    assert violations == []


def _assert_order(source: str, tokens: tuple[str, ...]) -> None:
    cursor = -1
    for token in tokens:
        index = source.find(token, cursor + 1)
        assert index > cursor, token
        cursor = index
