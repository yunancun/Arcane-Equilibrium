from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
# 直接引用的來源檔字面 rel 路徑（同時滿足 rust-source-coverage 守衛的「測試源文字
# 含該檔 rel 路徑」判定，並讓本 source-static 治理測試自身有實質斷言價值）。
TWS_SESSION_STATE = ROOT / "rust/openclaw_types/src/ibkr_tws_session_state.rs"
MAX_LINES = 2_000

# IB 官方現勘 error code 常數 + 客戶端 server-version pin + 連線 info 地板
# （W3-S1 契約層；出典綁 IB message_codes.html 現勘 2026-07-15）。
REQUIRED_CONSTANT_TOKENS = {
    "pub const IB_ERR_MAX_MESSAGE_RATE: i64 = 100;",
    "pub const IB_ERR_DUPLICATE_CLIENT_ID: i64 = 326;",
    "pub const IB_ERR_MARKET_DATA_NOT_SUBSCRIBED: i64 = 354;",
    "pub const IB_ERR_COULD_NOT_CONNECT_TWS: i64 = 502;",
    "pub const IB_ERR_TWS_OUT_OF_DATE: i64 = 503;",
    "pub const IB_ERR_NOT_CONNECTED: i64 = 504;",
    "pub const IB_ERR_SOCKET_PORT_RESET: i64 = 1300;",
    "pub const IB_INFO_CODE_FLOOR: i64 = 2100;",
    "pub const PINNED_MIN_SERVER_VERSION: i32 = 100;",
}
# 六態 FSM / 分類族 / typed 事件枚舉與純函數 token（W3-S1 骨架）。
REQUIRED_TYPE_TOKENS = {
    "pub enum IbkrTwsErrorClassV1",
    "pub enum IbkrTwsSessionStateV1",
    "pub enum IbkrTwsSessionEventV1",
    "pub fn classify(code: i64) -> Self",
    "pub fn conservative(code: i64) -> Self",
    'impl Default for IbkrTwsErrorClassV1',
    'impl Default for IbkrTwsSessionStateV1',
}
REQUIRED_ERROR_CLASS_VARIANTS = {
    "Transient",
    "SessionFatal",
    "Entitlement",
    "Pacing",
    "OrderReject",
    "Info",
    "Unknown",
}
REQUIRED_SESSION_STATE_VARIANTS = {
    "Disconnected",
    "Connecting",
    "Handshaking",
    "Ready",
    "Degraded",
    "Backoff",
}
REQUIRED_SESSION_EVENT_VARIANTS = {
    "ConnectPermitGranted",
    "EnvelopeRequired",
    "DuplicateClientIdRejected",
    "SessionExpiredWeeklyReauth",
    "ReconnectBudgetExhausted",
    "PacingBudgetExceeded",
    "ScheduledRestartDisconnect",
    "ServerVersionTooOld",
    "NonPaperSessionDetected",
    "IllegalTransition",
    "Halted",
}
# 表驅動分類 + 保守 fail-closed 裁決的關鍵語義行（現勘表外 code<2100→SessionFatal、
# ≥2100→Info，classify 原始回 Unknown，conservative 絕不回 Unknown）。
REQUIRED_SEMANTIC_TOKENS = {
    '#[serde(rename_all = "snake_case")]',
    "_ => Self::Unknown,",
    "Self::Unknown if code < IB_INFO_CODE_FLOOR => Self::SessionFatal,",
    "Self::Unknown => Self::Info,",
    "IB_ERR_MAX_MESSAGE_RATE => Self::Pacing,",
    "IB_ERR_MARKET_DATA_NOT_SUBSCRIBED => Self::Entitlement,",
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
    return TWS_SESSION_STATE.read_text(encoding="utf-8")


def test_ibkr_tws_session_state_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_ibkr_tws_session_state_keeps_surveyed_constants_and_pins() -> None:
    source = _source()
    for token in REQUIRED_CONSTANT_TOKENS:
        assert token in source, f"missing constant token {token!r}"


def test_ibkr_tws_session_state_keeps_error_class_and_fsm_types() -> None:
    source = _source()
    for token in REQUIRED_TYPE_TOKENS:
        assert token in source, f"missing type token {token!r}"


def test_ibkr_tws_session_state_keeps_error_class_variants() -> None:
    source = _source()
    for variant in REQUIRED_ERROR_CLASS_VARIANTS:
        assert variant in source, f"missing error-class variant {variant!r}"


def test_ibkr_tws_session_state_keeps_fsm_state_and_event_variants() -> None:
    source = _source()
    for variant in REQUIRED_SESSION_STATE_VARIANTS | REQUIRED_SESSION_EVENT_VARIANTS:
        assert variant in source, f"missing state/event variant {variant!r}"


def test_ibkr_tws_session_state_keeps_table_driven_and_fail_closed_semantics() -> None:
    source = _source()
    for token in REQUIRED_SEMANTIC_TOKENS:
        assert token in source, f"missing semantic token {token!r}"


def test_ibkr_tws_session_state_has_no_runtime_secret_socket_or_clock_tokens() -> None:
    source = _source()
    violations = []
    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{TWS_SESSION_STATE}: contains forbidden token {token!r}")
    assert violations == []
