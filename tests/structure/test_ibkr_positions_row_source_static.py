from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
# 直接引用的來源檔字面 rel 路徑（同時滿足 rust-source-coverage 守衛的「測試源文字
# 含該檔 rel 路徑」判定，並讓本 source-static 治理測試自身有實質斷言價值）。
POSITIONS_ROW = ROOT / "rust/openclaw_types/src/ibkr_positions_row.rs"
from tests.structure.file_line_policy import MAX_FILE_LINES as MAX_LINES

# W5-S1 行契約層:契約 id + STK-only secType 白名單（IBKR 慣例 ETF 亦為 wire STK）。
REQUIRED_CONTRACT_TOKENS = {
    'pub const IBKR_POSITIONS_ROW_CONTRACT_ID: &str = "ibkr_positions_row_v1";',
}
REQUIRED_TYPE_TOKENS = {
    "pub enum IbkrSecTypeV1",
    "pub struct IbkrPositionsRowV1",
    "pub fn classify_wire_sec_type(raw: &str) -> Self",
    "pub fn as_wire_sec_type(&self) -> Option<&'static str>",
    "pub fn is_normalized_symbol(symbol: &str) -> bool",
    "impl Default for IbkrSecTypeV1",
    "impl Default for IbkrPositionsRowV1",
}
# 行級 blocker taxonomy（含 short 永久 denied 的型別層投影）。
REQUIRED_BLOCKER_VARIANTS = {
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "WrongAssetLane",
    "WrongBroker",
    "AccountIdMissing",
    "ConIdInvalid",
    "SymbolInvalid",
    "SecTypeUnknownDenied",
    "CurrencyDenied",
    "ExchangeMissing",
    "ShortPositionDenied",
    "PositionDecimalInvalid",
    "AvgCostDecimalInvalid",
    "OrderRouted",
    "SecretContentSerialized",
}
# fail-closed 關鍵語義行（STK 單值白名單/表外拒/負倉拒）。
REQUIRED_SEMANTIC_TOKENS = {
    '#[serde(rename_all = "snake_case")]',
    '"STK" => Self::Stk,',
    "_ => Self::UnknownDenied,",
    "blockers.push(B::SecTypeUnknownDenied);",
    "blockers.push(B::ShortPositionDenied);",
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
    return POSITIONS_ROW.read_text(encoding="utf-8")


def test_ibkr_positions_row_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_ibkr_positions_row_keeps_contract_id() -> None:
    source = _source()
    for token in REQUIRED_CONTRACT_TOKENS:
        assert token in source, f"missing contract token {token!r}"


def test_ibkr_positions_row_keeps_types_and_pure_functions() -> None:
    source = _source()
    for token in REQUIRED_TYPE_TOKENS:
        assert token in source, f"missing type token {token!r}"


def test_ibkr_positions_row_keeps_blocker_taxonomy() -> None:
    source = _source()
    for variant in REQUIRED_BLOCKER_VARIANTS:
        assert variant in source, f"missing blocker variant {variant!r}"


def test_ibkr_positions_row_keeps_fail_closed_semantics() -> None:
    source = _source()
    for token in REQUIRED_SEMANTIC_TOKENS:
        assert token in source, f"missing semantic token {token!r}"


def test_ibkr_positions_row_has_no_runtime_secret_socket_or_clock_tokens() -> None:
    source = _source()
    violations = []
    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{POSITIONS_ROW}: contains forbidden token {token!r}")
    assert violations == []
