from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
# 直接引用的來源檔字面 rel 路徑（同時滿足 rust-source-coverage 守衛的「測試源文字
# 含該檔 rel 路徑」判定，並讓本 source-static 治理測試自身有實質斷言價值）。
COMMISSIONS_ROW = ROOT / "rust/openclaw_types/src/ibkr_commissions_row.rs"
MAX_LINES = 800

# W5-S1 行契約層:契約 id + exec_id 關聯鍵 + realizedPnL 缺席語義（Option,禁默認 0）。
REQUIRED_CONTRACT_TOKENS = {
    'pub const IBKR_COMMISSIONS_ROW_CONTRACT_ID: &str = "ibkr_commissions_row_v1";',
}
REQUIRED_TYPE_TOKENS = {
    "pub struct IbkrCommissionsRowV1",
    "impl Default for IbkrCommissionsRowV1",
    "pub exec_id: String,",
    "pub commission_decimal: String,",
    "pub realized_pnl_decimal: Option<String>,",
}
# 行級 blocker taxonomy。
REQUIRED_BLOCKER_VARIANTS = {
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "WrongAssetLane",
    "WrongBroker",
    "ExecIdMissing",
    "CommissionDecimalInvalid",
    "CurrencyDenied",
    "RealizedPnlDecimalInvalid",
    "OrderRouted",
    "SecretContentSerialized",
}
# fail-closed 關鍵語義行（缺席=None 誠實承載;Some 必為合法簽名定點,Some("") 拒;
# Default 的 realized_pnl_decimal: None 即「禁默認 0 假值」的機器可驗形態）。
REQUIRED_SEMANTIC_TOKENS = {
    '#[serde(rename_all = "snake_case")]',
    "realized_pnl_decimal: None,",
    "if let Some(raw) = &self.realized_pnl_decimal {",
    "blockers.push(B::RealizedPnlDecimalInvalid);",
    "blockers.push(B::ExecIdMissing);",
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
    return COMMISSIONS_ROW.read_text(encoding="utf-8")


def test_ibkr_commissions_row_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_ibkr_commissions_row_keeps_contract_id() -> None:
    source = _source()
    for token in REQUIRED_CONTRACT_TOKENS:
        assert token in source, f"missing contract token {token!r}"


def test_ibkr_commissions_row_keeps_types_and_join_key_fields() -> None:
    source = _source()
    for token in REQUIRED_TYPE_TOKENS:
        assert token in source, f"missing type token {token!r}"


def test_ibkr_commissions_row_keeps_blocker_taxonomy() -> None:
    source = _source()
    for variant in REQUIRED_BLOCKER_VARIANTS:
        assert variant in source, f"missing blocker variant {variant!r}"


def test_ibkr_commissions_row_keeps_absent_pnl_fail_closed_semantics() -> None:
    source = _source()
    for token in REQUIRED_SEMANTIC_TOKENS:
        assert token in source, f"missing semantic token {token!r}"


def test_ibkr_commissions_row_has_no_runtime_secret_socket_or_clock_tokens() -> None:
    source = _source()
    violations = []
    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{COMMISSIONS_ROW}: contains forbidden token {token!r}")
    assert violations == []
