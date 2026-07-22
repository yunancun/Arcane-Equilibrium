from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
# 直接引用的來源檔字面 rel 路徑（同時滿足 rust-source-coverage 守衛的「測試源文字
# 含該檔 rel 路徑」判定，並讓本 source-static 治理測試自身有實質斷言價值）。
IDENTITY_ROW = ROOT / "rust/openclaw_types/src/ibkr_instrument_identity_row.rs"
MAX_LINES = 2_000

# W6-S1 行契約層:契約 id + stockType 封閉白名單 + venue 白名單（v1 保守集）。
REQUIRED_CONTRACT_TOKENS = {
    'pub const IBKR_INSTRUMENT_IDENTITY_ROW_CONTRACT_ID: &str = "ibkr_instrument_identity_row_v1";',
    "pub const IBKR_INSTRUMENT_PRIMARY_EXCHANGE_WHITELIST: [&str; 6] =",
}
REQUIRED_TYPE_TOKENS = {
    "pub enum IbkrStockTypeV1",
    "pub struct IbkrInstrumentIdentityRowV1",
    "pub fn classify_wire_stock_type(raw: &str) -> Self",
    "pub fn as_wire_stock_type(&self) -> Option<&'static str>",
    "pub fn is_whitelisted_instrument_exchange(raw: &str) -> bool",
    "pub fn is_whitelisted_primary_exchange(raw: &str) -> bool",
    "pub fn identity_hash_preimage(&self) -> String",
    "pub fn validate(&self, now_ms: u64) -> IbkrInstrumentIdentityRowVerdict",
    "impl Default for IbkrStockTypeV1",
    "impl Default for IbkrInstrumentIdentityRowV1",
}
# 行級 blocker taxonomy（封閉枚舉;含 venue/stockType/未來時間戳拒）。
REQUIRED_BLOCKER_VARIANTS = {
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "WrongAssetLane",
    "WrongBroker",
    "ConIdInvalid",
    "SymbolInvalid",
    "SecTypeUnknownDenied",
    "ExchangeVenueDenied",
    "PrimaryExchangeVenueDenied",
    "CurrencyDenied",
    "LocalSymbolMissing",
    "TradingClassMissing",
    "MarketNameMissing",
    "MinTickInvalid",
    "ValidExchangesMissing",
    "PriceMagnifierInvalid",
    "TimeZoneIdMissing",
    "TradingHoursMissing",
    "LiquidHoursMissing",
    "StockTypeUnknownDenied",
    "IdentityHashInvalid",
    "CapturedAtMissing",
    "CapturedAtInFuture",
    "SnapshotSeqMissing",
    "OrderRouted",
    "SecretContentSerialized",
}
# fail-closed 關鍵語義行（stockType 表外拒/venue 表外拒/嚴格正刻度/preimage 域前綴/
# legacy 時區禁默認 America/New_York——保真紀律以注釋 token 鎖定）。
REQUIRED_SEMANTIC_TOKENS = {
    '#[serde(rename_all = "snake_case")]',
    '"ETF" => Self::Etf,',
    '"COMMON" => Self::CommonStock,',
    "_ => Self::UnknownDenied,",
    'raw == "SMART" || is_whitelisted_primary_exchange(raw)',
    "blockers.push(B::StockTypeUnknownDenied);",
    "blockers.push(B::ExchangeVenueDenied);",
    "blockers.push(B::PrimaryExchangeVenueDenied);",
    "is_positive_decimal_string(&self.min_tick_decimal)",
    "blockers.push(B::CapturedAtInFuture);",
    "禁默認 America/New_York",
}
# source-only 契約層：不得開 socket / 讀 secret / 起 clock / 觸碰 runtime material。
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
)
FORBIDDEN_SECRET_MATERIAL_TOKENS = (
    "api_key",
    "api_secret",
    "password",
    "OPENCLAW_",
    "SecretString",
    "SecretVec",
    "keyring",
)


def _source() -> str:
    return IDENTITY_ROW.read_text(encoding="utf-8")


def test_ibkr_instrument_identity_row_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_ibkr_instrument_identity_row_keeps_contract_id_and_whitelists() -> None:
    source = _source()
    for token in REQUIRED_CONTRACT_TOKENS:
        assert token in source, f"missing contract token {token!r}"


def test_ibkr_instrument_identity_row_keeps_types_and_pure_functions() -> None:
    source = _source()
    for token in REQUIRED_TYPE_TOKENS:
        assert token in source, f"missing type token {token!r}"


def test_ibkr_instrument_identity_row_keeps_blocker_taxonomy() -> None:
    source = _source()
    for variant in REQUIRED_BLOCKER_VARIANTS:
        assert variant in source, f"missing blocker variant {variant!r}"


def test_ibkr_instrument_identity_row_keeps_fail_closed_semantics() -> None:
    source = _source()
    for token in REQUIRED_SEMANTIC_TOKENS:
        assert token in source, f"missing semantic token {token!r}"


def test_ibkr_instrument_identity_row_has_no_runtime_secret_socket_or_clock_tokens() -> None:
    source = _source()
    violations = []
    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{IDENTITY_ROW}: contains forbidden token {token!r}")
    assert violations == []
