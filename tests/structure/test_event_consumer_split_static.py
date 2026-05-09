from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVENT_CONSUMER = ROOT / "rust/openclaw_engine/src/event_consumer"


def _loc(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_event_consumer_hot_files_stay_split_under_limit() -> None:
    modules = {
        name: _loc(EVENT_CONSUMER / name)
        for name in {
            "dispatch.rs",
            "dispatch_tests.rs",
            "loop_handlers.rs",
            "loop_exchange.rs",
        }
    }

    assert modules["dispatch.rs"] <= 800
    assert modules["dispatch_tests.rs"] <= 800
    assert modules["loop_handlers.rs"] <= 800
    assert modules["loop_exchange.rs"] <= 800


def test_event_consumer_split_keeps_compatibility_exports() -> None:
    mod_text = (EVENT_CONSUMER / "mod.rs").read_text(encoding="utf-8")
    dispatch_text = (EVENT_CONSUMER / "dispatch.rs").read_text(encoding="utf-8")
    loop_text = (EVENT_CONSUMER / "loop_handlers.rs").read_text(encoding="utf-8")
    exchange_text = (EVENT_CONSUMER / "loop_exchange.rs").read_text(encoding="utf-8")

    assert "mod loop_exchange;" in mod_text
    assert '#[path = "dispatch_tests.rs"]' in dispatch_text
    assert "pub(super) use super::loop_exchange::handle_exchange_event;" in loop_text
    assert "pub(super) async fn handle_exchange_event(" in exchange_text
