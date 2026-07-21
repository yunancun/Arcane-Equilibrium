from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
# 直接引用的來源檔字面 rel 路徑（同時滿足 rust-source-coverage 守衛的「測試源文字含該檔
# rel 路徑」判定，並讓本 source-static 治理測試自身有實質斷言價值）。
CALENDAR = ROOT / "rust/openclaw_types/src/ibkr_trading_calendar.rs"
PARSER = ROOT / "rust/openclaw_engine/src/ibkr_trading_calendar.rs"
PARSER_TESTS = ROOT / "rust/openclaw_engine/src/ibkr_trading_calendar_tests.rs"
PROVENANCE = ROOT / "rust/openclaw_types/src/ibkr_market_data_provenance.rs"
from tests.structure.file_line_policy import MAX_FILE_LINES as MAX_LINES

# W6-S2 日曆結果契約層:契約 id + hours-kind/session-kind/blocker 封閉枚舉 + 純函數。
REQUIRED_CONTRACT_TOKENS = {
    'pub const IBKR_TRADING_CALENDAR_CONTRACT_ID: &str = "ibkr_trading_calendar_v1";',
    'pub const CALENDAR_TZ_UNKNOWN_DENIED_SENTINEL: &str = "UNKNOWN_DENIED";',
}
REQUIRED_TYPE_TOKENS = {
    "pub enum IbkrCalendarHoursKindV1",
    "pub enum IbkrCalendarSessionKindV1",
    "pub struct IbkrTradingCalendarSessionV1",
    "pub struct IbkrTradingCalendarV1",
    "pub fn calendar_hash_preimage(&self) -> String",
    "pub fn validate(&self) -> IbkrTradingCalendarVerdict",
    "impl Default for IbkrCalendarHoursKindV1",
    "impl Default for IbkrTradingCalendarV1",
}
# 封閉 blocker taxonomy（解析側 + 結構側共用單一枚舉）。
REQUIRED_BLOCKER_VARIANTS = {
    "ContractIdMismatch",
    "TimeZoneIdMissing",
    "TimeZoneUnknownDenied",
    "GrammarUnrecognized",
    "DateInvalid",
    "SessionOutOfOrder",
    "SessionTimeInvalid",
    "EmptyCalendar",
    "CalendarHashInvalid",
    "OrderRouted",
    "SecretContentSerialized",
}
# fail-closed 語義（sha256 shape / tz 哨兵拒 / Open 時刻關係 / 負空間束）。
REQUIRED_SEMANTIC_TOKENS = {
    '#[serde(rename_all = "snake_case")]',
    "is_sha256_hex(&self.calendar_hash)",
    "CALENDAR_TZ_UNKNOWN_DENIED_SENTINEL",
    "s.close_ms <= s.open_ms",
    "self.order_routed",
    "self.secret_content_serialized",
}
# types crate 不得引入雜湊 / tz / IO / socket 依賴（計算歸 engine 消化層）。
FORBIDDEN_TYPES_TOKENS = (
    "std::env",
    "std::fs",
    "File::open",
    "include_str!",
    "std::net",
    "TcpStream",
    "reqwest",
    "ibapi",
    # 用 import/path 形式而非裸字（模組註解會提及 `chrono-tz`,裸子串會誤判）。
    "use chrono",
    "chrono::",
    "chrono_tz::",
    "SystemTime",
    "sha2::",
    "use sha2",
    "Sha256::",
    "std::process",
    "Command::new",
)
FORBIDDEN_SECRET_MATERIAL_TOKENS = (
    "api_key",
    "api_secret",
    "password",
    "OPENCLAW_",
    "SecretString",
    "keyring",
)
# engine 解析器面：必含真 DST / hash 工作，且絕不含 socket / 下單 / IO。
REQUIRED_PARSER_TOKENS = {
    "pub fn parse_trading_calendar(",
    "pub fn compute_calendar_hash(",
    "pub fn legacy_tz_to_iana(",
    "use chrono_tz::Tz;",
    "from_local_datetime",
    "IbkrTradingCalendarV1",
}
FORBIDDEN_PARSER_TOKENS = (
    "TcpStream",
    "std::net",
    "tokio::net",
    "reqwest",
    "ibapi",
    "std::fs",
    "File::open",
    "std::env",
    "reqMktData",
    "place_order",
    "OUT_",
    "encode_frame",
)


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_calendar_source_stays_below_governance_cap() -> None:
    assert len(_text(CALENDAR).splitlines()) <= MAX_LINES
    assert len(_text(PARSER).splitlines()) <= MAX_LINES
    assert len(_text(PARSER_TESTS).splitlines()) <= MAX_LINES


def test_calendar_keeps_contract_and_types() -> None:
    source = _text(CALENDAR)
    for token in REQUIRED_CONTRACT_TOKENS | REQUIRED_TYPE_TOKENS:
        assert token in source, f"missing token {token!r}"


def test_calendar_keeps_blocker_taxonomy() -> None:
    source = _text(CALENDAR)
    for variant in REQUIRED_BLOCKER_VARIANTS:
        assert variant in source, f"missing blocker variant {variant!r}"


def test_calendar_keeps_fail_closed_semantics() -> None:
    source = _text(CALENDAR)
    for token in REQUIRED_SEMANTIC_TOKENS:
        assert token in source, f"missing semantic token {token!r}"


def test_calendar_types_crate_has_no_hash_tz_or_io_dependency() -> None:
    # 契約只驗 shape;雜湊 / tz / DST / IO 計算歸 engine 消化層——types crate 不得引入。
    source = _text(CALENDAR)
    violations = [
        f"{CALENDAR}: forbidden token {t!r}"
        for t in FORBIDDEN_TYPES_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS
        if t in source
    ]
    assert violations == []


def test_parser_does_real_dst_and_hash_work() -> None:
    source = _text(PARSER)
    for token in REQUIRED_PARSER_TOKENS:
        assert token in source, f"parser missing token {token!r}"


def test_parser_has_no_socket_order_or_io_surface() -> None:
    # 純解析:零 wire / 零下單 / 零 socket / 零 IO（消費 S1 已合併字串）。
    source = _text(PARSER)
    violations = [
        f"{PARSER}: forbidden token {t!r}" for t in FORBIDDEN_PARSER_TOKENS if t in source
    ]
    assert violations == []


def test_pairing_guard_calendar_hash_binds_provenance() -> None:
    # **配對守衛（跨檔）**：provenance 的 calendar_hash 欄與本切片的 calendar_hash 真值必須
    # 同源共存——provenance 驗 shape（is_sha256_hex），engine 解析器導出 compute_calendar_hash
    # 供 S4 mint 綁定。兩檔缺一則 calendar_hash 無真值來源 / 無溯源落點。
    prov = _text(PROVENANCE)
    parser = _text(PARSER)
    calendar = _text(CALENDAR)
    assert "pub calendar_hash: String" in prov
    assert "is_sha256_hex(&self.calendar_hash)" in prov
    assert "pub fn compute_calendar_hash(" in parser
    # S4 mint 接線註記存在（provenance 綁定的殘項可追）。
    assert "W6-S4" in parser and "provenance" in parser
    # calendar_hash preimage 為單一定義點（重放端可重建）。
    assert "pub fn calendar_hash_preimage(&self) -> String" in calendar
