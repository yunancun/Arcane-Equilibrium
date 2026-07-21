from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
# 直接引用的來源檔字面 rel 路徑（同時滿足 rust-source-coverage 守衛的「測試源文字
# 含該檔 rel 路徑」判定，並讓本 source-static 治理測試自身有實質斷言價值）。
ACCOUNT_SUMMARY_ROW = ROOT / "rust/openclaw_types/src/ibkr_account_summary_row.rs"
from tests.structure.file_line_policy import MAX_FILE_LINES as MAX_LINES

# W5-S1 行契約層:契約 id + wire tag 白名單 const（9 tag,fail-closed）。
REQUIRED_CONTRACT_TOKENS = {
    'pub const IBKR_ACCOUNT_SUMMARY_ROW_CONTRACT_ID: &str = "ibkr_account_summary_row_v1";',
    "pub const IBKR_ACCOUNT_SUMMARY_WIRE_TAG_WHITELIST: [&str; 9] = [",
}
# 枚舉/struct/純函數面（含 W5-S1 row 家族共用 decimal helper 三件與符號紀律表）。
REQUIRED_TYPE_TOKENS = {
    "pub enum IbkrAccountSummaryTagV1",
    "pub struct IbkrAccountSummaryRowV1",
    "pub fn classify_wire_tag(raw: &str) -> Self",
    "pub fn as_wire_tag(&self) -> Option<&'static str>",
    "pub fn is_structurally_non_negative(&self) -> bool",
    "pub fn is_signed_decimal_string(raw: &str) -> bool",
    "pub fn is_nonnegative_decimal_string(raw: &str) -> bool",
    "pub fn is_positive_decimal_string(raw: &str) -> bool",
    "impl Default for IbkrAccountSummaryTagV1",
    "impl Default for IbkrAccountSummaryRowV1",
}
# tag 白名單變體（9 官方慣例 tag + fail-closed UnknownDenied）。
REQUIRED_TAG_VARIANTS = {
    "NetLiquidation",
    "TotalCashValue",
    "SettledCash",
    "BuyingPower",
    "AvailableFunds",
    "ExcessLiquidity",
    "GrossPositionValue",
    "AccruedCash",
    "EquityWithLoanValue",
    "UnknownDenied",
}
# 行級 blocker taxonomy（含 E2 F3 的 per-tag 符號紀律 blocker）。
REQUIRED_BLOCKER_VARIANTS = {
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "WrongAssetLane",
    "WrongBroker",
    "AccountIdMissing",
    "TagUnknownDenied",
    "ValueDecimalInvalid",
    "NegativeValueForNonNegativeTag",
    "CurrencyDenied",
    "CapturedAtMissing",
    "SnapshotSeqMissing",
    "OrderRouted",
    "SecretContentSerialized",
}
# fail-closed 關鍵語義行（表外 tag 拒/符號紀律/snake_case serde）。
REQUIRED_SEMANTIC_TOKENS = {
    '#[serde(rename_all = "snake_case")]',
    "_ => Self::UnknownDenied,",
    "blockers.push(B::TagUnknownDenied);",
    "blockers.push(B::NegativeValueForNonNegativeTag);",
    "blockers.push(B::SecretContentSerialized);",
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
    return ACCOUNT_SUMMARY_ROW.read_text(encoding="utf-8")


def test_ibkr_account_summary_row_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_ibkr_account_summary_row_keeps_contract_id_and_whitelist_const() -> None:
    source = _source()
    for token in REQUIRED_CONTRACT_TOKENS:
        assert token in source, f"missing contract token {token!r}"


def test_ibkr_account_summary_row_keeps_types_and_pure_functions() -> None:
    source = _source()
    for token in REQUIRED_TYPE_TOKENS:
        assert token in source, f"missing type token {token!r}"


def test_ibkr_account_summary_row_keeps_tag_whitelist_variants() -> None:
    source = _source()
    for variant in REQUIRED_TAG_VARIANTS:
        assert variant in source, f"missing tag variant {variant!r}"


def test_ibkr_account_summary_row_keeps_blocker_taxonomy() -> None:
    source = _source()
    for variant in REQUIRED_BLOCKER_VARIANTS:
        assert variant in source, f"missing blocker variant {variant!r}"


def test_ibkr_account_summary_row_keeps_fail_closed_semantics() -> None:
    source = _source()
    for token in REQUIRED_SEMANTIC_TOKENS:
        assert token in source, f"missing semantic token {token!r}"


def test_ibkr_account_summary_row_has_no_runtime_secret_socket_or_clock_tokens() -> None:
    source = _source()
    violations = []
    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{ACCOUNT_SUMMARY_ROW}: contains forbidden token {token!r}")
    assert violations == []
