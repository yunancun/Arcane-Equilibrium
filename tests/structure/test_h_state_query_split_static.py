from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = (
    ROOT / "program_code/exchange_connectors/bybit_connector/control_api_v1/tests"
)
SHIM = TEST_ROOT / "test_h_state_query_handler.py"
SPLIT_DIR = TEST_ROOT / "h_state_query"


def _loc(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_h_state_query_handler_is_only_a_compatibility_collector() -> None:
    text = SHIM.read_text(encoding="utf-8")

    assert _loc(SHIM) <= 80
    assert "from h_state_query.test_core import *" in text
    assert "from h_state_query.test_h_buckets import *" in text
    assert "from h_state_query.test_agent_states import *" in text


def test_h_state_query_split_modules_stay_below_hard_limit() -> None:
    modules = {
        path.name: _loc(path)
        for path in SPLIT_DIR.glob("*.py")
        if path.name != "__init__.py"
    }

    assert set(modules) == {
        "common.py",
        "test_core.py",
        "test_h_buckets.py",
        "test_agent_states.py",
    }
    assert modules["common.py"] <= 800
    assert modules["test_core.py"] <= 800
    assert modules["test_h_buckets.py"] <= 800
    assert modules["test_agent_states.py"] <= 1500
