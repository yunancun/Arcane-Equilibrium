from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / "rust/openclaw_types/src/stock_etf_paper_order_request.rs"
SPLIT_DIR = ROOT / "rust/openclaw_types/src/stock_etf_paper_order_request"
FIXTURES = SPLIT_DIR / "fixtures.rs"
VALIDATION = SPLIT_DIR / "validation.rs"
from tests.structure.file_line_policy import MAX_FILE_LINES as MAX_LINES
EXPECTED_MODULES = {"fixtures.rs", "validation.rs"}
FORBIDDEN_RUNTIME_TOKENS = (
    "std::env",
    "std::fs",
    "std::net",
    "TcpStream",
    "tokio::net",
    "reqwest",
    "hyper::",
    "ureq",
    "ib_insync",
    "ibapi",
    "IBApi",
    ".place_order(",
    ".cancel_order(",
    ".replace_order(",
    ".modify_order(",
    ".create_order(",
)


def _loc(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_stock_etf_paper_order_request_files_stay_below_governance_cap() -> None:
    parent = PARENT.read_text(encoding="utf-8")
    modules = {path.name: _loc(path) for path in SPLIT_DIR.glob("*.rs")}

    assert "mod fixtures;" in parent
    assert "mod validation;" in parent
    assert set(modules) == EXPECTED_MODULES
    assert _loc(PARENT) <= MAX_LINES
    assert all(loc <= MAX_LINES for loc in modules.values())


def test_stock_etf_paper_order_request_ownership_is_split() -> None:
    parent = PARENT.read_text(encoding="utf-8")
    fixtures = FIXTURES.read_text(encoding="utf-8")
    validation = VALIDATION.read_text(encoding="utf-8")

    for name in (
        "accepted_preview_fixture",
        "accepted_submit_fixture",
        "accepted_cancel_fixture",
        "accepted_replace_fixture",
    ):
        assert f"pub fn {name}(" in fixtures
        assert f"pub fn {name}(" not in parent

    assert "pub fn validate(&self)" in validation
    assert "pub fn validate(&self)" not in parent
    assert "fn validate_order_intent(" in validation
    assert "fn validate_order_intent(" not in parent


def test_stock_etf_paper_order_request_split_has_no_runtime_tokens() -> None:
    sources = {PARENT: PARENT.read_text(encoding="utf-8")}
    sources.update({path: path.read_text(encoding="utf-8") for path in SPLIT_DIR.glob("*.rs")})

    violations = []
    for path, source in sources.items():
        for token in FORBIDDEN_RUNTIME_TOKENS:
            if token in source:
                violations.append(f"{path}: contains forbidden runtime token {token!r}")

    assert violations == []
