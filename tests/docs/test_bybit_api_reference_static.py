from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/references/2026-04-04--bybit_api_reference.md"
MARKET_CLIENT = ROOT / "rust/openclaw_engine/src/market_data_client/mod.rs"
SETTINGS_ROUTES = (
    ROOT
    / "program_code/exchange_connectors/bybit_connector/control_api_v1/app/settings_routes.py"
)
UNKNOWN_GUARD = ROOT / "rust/openclaw_engine/src/ws_unknown_handler_guard.rs"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    start_idx = text.index(start)
    end_idx = text.index(end, start_idx)
    return text[start_idx:end_idx]


def test_f27_open_interest_documents_interval_time_request_key() -> None:
    doc = _read(DOC)
    section = _section(doc, "#### get_open_interest", "#### get_funding_history")
    market_client = _read(MARKET_CLIENT)

    assert "`intervalTime`" in section
    assert "不是 `interval`" in section
    assert '("intervalTime", interval.to_string())' in market_client


def test_f27_long_short_ratio_documents_official_daily_period_drift() -> None:
    doc = _read(DOC)
    section = _section(doc, "#### get_long_short_ratio", "#### get_risk_limit")

    assert 'Rust poller 只使用 `"1h"`' in section
    assert '"1d"' in section
    assert '"4d"' in section
    assert "官方文檔互相漂移" in section
    assert "exchange smoke" in section


def test_f27_query_api_key_section_matches_python_validation_path() -> None:
    doc = _read(DOC)
    section = _section(doc, "### 1.5a User / API Key Validation", "#### set_hedging_mode")
    settings = _read(SETTINGS_ROUTES)

    assert "GET /v5/user/query-api" in section
    assert "_validate_bybit_credentials" in section
    assert "X-BAPI-SIGN-TYPE=2" in section
    assert '_VALIDATE_PATH = "/v5/user/query-api"' in settings
    assert "query-api" in settings


def test_f27_g9_02_section_matches_runtime_env_gate_and_thresholds() -> None:
    doc = _read(DOC)
    section = _section(doc, "### 2.3 G9-02 Unknown Handler Guard", "### 2.4 Shadow")
    guard = _read(UNKNOWN_GUARD)

    env_var = "OPENCLAW_WS_FORCE_RECONNECT_ON_UNKNOWN_ENABLED"
    assert env_var in section
    assert env_var in guard
    assert "OPENCLAW_WS_UNKNOWN_GUARD_ARMED" in section
    assert "runtime SSOT" in section
    assert "`unique_count >= 3`" in section
    assert "`total_count >= 5`" in section
    assert "pub const UNIQUE_THRESHOLD: usize = 3;" in guard
    assert "pub const TOTAL_THRESHOLD: usize = 5;" in guard
