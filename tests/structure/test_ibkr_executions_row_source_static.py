from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
# 直接引用的來源檔字面 rel 路徑（同時滿足 rust-source-coverage 守衛的「測試源文字
# 含該檔 rel 路徑」判定，並讓本 source-static 治理測試自身有實質斷言價值）。
EXECUTIONS_ROW = ROOT / "rust/openclaw_types/src/ibkr_executions_row.rs"
MAX_LINES = 2_000

# W5-S1 行契約層:契約 id + BOT/SLD side 白名單（IBKR 官方 Execution.side 慣例）。
REQUIRED_CONTRACT_TOKENS = {
    'pub const IBKR_EXECUTIONS_ROW_CONTRACT_ID: &str = "ibkr_executions_row_v1";',
}
REQUIRED_TYPE_TOKENS = {
    "pub enum IbkrExecutionSideV1",
    "pub struct IbkrExecutionsRowV1",
    "pub fn classify_wire_side(raw: &str) -> Self",
    "pub fn as_wire_side(&self) -> Option<&'static str>",
    "impl Default for IbkrExecutionSideV1",
    "impl Default for IbkrExecutionsRowV1",
}
# instrument identity 束（E2 F2:execDetails wire 的 Contract 物件投影,沿 positions-row
# STK-only 白名單——margin/options/cfd 型別層投影拒）。
REQUIRED_IDENTITY_TOKENS = {
    "pub con_id: i64,",
    "pub symbol: String,",
    "pub sec_type: IbkrSecTypeV1,",
    "pub currency: StockEtfCurrency,",
    "use crate::ibkr_positions_row::{is_normalized_symbol, IbkrSecTypeV1};",
}
# 行級 blocker taxonomy（含 F2 補齊的 identity 四 blocker）。
REQUIRED_BLOCKER_VARIANTS = {
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "WrongAssetLane",
    "WrongBroker",
    "AccountIdMissing",
    "ExecIdMissing",
    "ConIdInvalid",
    "SymbolInvalid",
    "SecTypeUnknownDenied",
    "CurrencyDenied",
    "ExecTimeMissing",
    "SideUnknownDenied",
    "SharesDecimalInvalid",
    "PriceDecimalInvalid",
    "ExchangeMissing",
    "OrderRouted",
    "SecretContentSerialized",
}
# fail-closed 關鍵語義行（BOT/SLD 白名單/表外拒/identity 束拒）。
REQUIRED_SEMANTIC_TOKENS = {
    '#[serde(rename_all = "snake_case")]',
    '"BOT" => Self::Bought,',
    '"SLD" => Self::Sold,',
    "_ => Self::UnknownDenied,",
    "blockers.push(B::SideUnknownDenied);",
    "blockers.push(B::SecTypeUnknownDenied);",
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
    return EXECUTIONS_ROW.read_text(encoding="utf-8")


def test_ibkr_executions_row_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_ibkr_executions_row_keeps_contract_id() -> None:
    source = _source()
    for token in REQUIRED_CONTRACT_TOKENS:
        assert token in source, f"missing contract token {token!r}"


def test_ibkr_executions_row_keeps_types_and_pure_functions() -> None:
    source = _source()
    for token in REQUIRED_TYPE_TOKENS:
        assert token in source, f"missing type token {token!r}"


def test_ibkr_executions_row_keeps_instrument_identity_bundle() -> None:
    source = _source()
    for token in REQUIRED_IDENTITY_TOKENS:
        assert token in source, f"missing identity token {token!r}"


def test_ibkr_executions_row_keeps_blocker_taxonomy() -> None:
    source = _source()
    for variant in REQUIRED_BLOCKER_VARIANTS:
        assert variant in source, f"missing blocker variant {variant!r}"


def test_ibkr_executions_row_keeps_fail_closed_semantics() -> None:
    source = _source()
    for token in REQUIRED_SEMANTIC_TOKENS:
        assert token in source, f"missing semantic token {token!r}"


def test_ibkr_executions_row_has_no_runtime_secret_socket_or_clock_tokens() -> None:
    source = _source()
    violations = []
    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{EXECUTIONS_ROW}: contains forbidden token {token!r}")
    assert violations == []
