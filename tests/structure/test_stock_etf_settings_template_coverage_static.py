from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
THIS_FILE = Path(__file__).resolve()
SETTINGS_DIRS = (
    ROOT / "settings/asset_lanes",
    ROOT / "settings/broker",
    ROOT / "settings/risk_control_rules",
)
TEST_SOURCE_PATTERNS = (
    "rust/openclaw_types/tests/*.rs",
    "tests/structure/*.py",
    "program_code/exchange_connectors/bybit_connector/control_api_v1/tests/**/*.py",
)


def _stock_etf_ibkr_setting_files() -> list[Path]:
    files = []
    for directory in SETTINGS_DIRS:
        files.extend(
            path
            for path in directory.iterdir()
            if path.is_file()
            and path.suffix == ".toml"
            and (
                "ibkr" in path.name
                or "stock_etf" in path.name
                or "stock_market_data" in path.name
            )
        )
    return sorted(files)


def _test_source_text() -> str:
    chunks = []
    for pattern in TEST_SOURCE_PATTERNS:
        for path in ROOT.glob(pattern):
            if path.resolve() == THIS_FILE:
                continue
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def test_stock_etf_settings_template_coverage_scan_scope_is_exact() -> None:
    files = _stock_etf_ibkr_setting_files()
    names = {path.name for path in files}

    assert "stock_etf_cash.toml" in names
    assert "ibkr_feature_flag_secret_auth_matrix.toml" in names
    assert "stock_etf_ibkr_readonly_probe_request.template.toml" in names
    assert "stock_market_data_provenance.template.toml" in names
    assert "risk_config_stock_etf_paper.toml" in names
    assert "risk_config_demo.toml" not in names
    assert "risk_config_live.toml" not in names
    assert "risk_config_paper.toml" not in names


def test_stock_etf_settings_templates_are_directly_referenced_by_tests() -> None:
    source = _test_source_text()
    uncovered = []

    for path in _stock_etf_ibkr_setting_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel not in source and path.name not in source:
            uncovered.append(rel)

    assert uncovered == []


def test_stock_etf_settings_template_coverage_includes_non_prefixed_market_data_alias() -> None:
    names = {path.name for path in _stock_etf_ibkr_setting_files()}

    assert "stock_market_data_provenance.template.toml" in names
