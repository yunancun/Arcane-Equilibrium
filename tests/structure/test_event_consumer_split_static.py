from pathlib import Path

from tests.structure.file_line_policy import MAX_FILE_LINES


ROOT = Path(__file__).resolve().parents[2]
EVENT_CONSUMER = ROOT / "rust/openclaw_engine/src/event_consumer"


def _loc(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_event_consumer_hot_files_stay_split_under_limit() -> None:
    governed = {
        "dispatch.rs",
        "dispatch_retcode.rs",
        "dispatch_retcode_tests.rs",
        "dispatch_tests.rs",
        "loop_exchange.rs",
        "loop_handlers.rs",
        "loop_pending_registration.rs",
        "loop_pipeline_command.rs",
        "loop_tick.rs",
    }
    modules = {name: _loc(EVENT_CONSUMER / name) for name in governed}
    for name in sorted(modules):
        assert modules[name] <= MAX_FILE_LINES, (
            f"{name} = {modules[name]} LOC > {MAX_FILE_LINES}"
        )


def test_event_consumer_split_keeps_compatibility_exports() -> None:
    mod_text = (EVENT_CONSUMER / "mod.rs").read_text(encoding="utf-8")
    dispatch_text = (EVENT_CONSUMER / "dispatch.rs").read_text(encoding="utf-8")
    loop_text = (EVENT_CONSUMER / "loop_handlers.rs").read_text(encoding="utf-8")
    exchange_text = (EVENT_CONSUMER / "loop_exchange.rs").read_text(encoding="utf-8")
    retcode_text = (EVENT_CONSUMER / "dispatch_retcode.rs").read_text(encoding="utf-8")
    pending_reg_text = (EVENT_CONSUMER / "loop_pending_registration.rs").read_text(encoding="utf-8")
    pipeline_cmd_text = (EVENT_CONSUMER / "loop_pipeline_command.rs").read_text(encoding="utf-8")
    tick_text = (EVENT_CONSUMER / "loop_tick.rs").read_text(encoding="utf-8")

    assert "mod loop_exchange;" in mod_text
    assert '#[path = "dispatch_tests.rs"]' in dispatch_text
    assert "pub(super) use super::loop_exchange::handle_exchange_event;" in loop_text
    assert "pub(super) async fn handle_exchange_event(" in exchange_text

    # mod 佈線
    assert "mod dispatch_retcode;" in mod_text
    assert "mod loop_pending_registration;" in mod_text
    assert "mod loop_pipeline_command;" in mod_text
    assert "mod loop_tick;" in mod_text

    # dispatch façade：re-export + 測試 mount 雙軌
    assert "pub(super) use super::dispatch_retcode::" in dispatch_text
    assert '#[path = "dispatch_retcode_tests.rs"]' in retcode_text

    # loop_handlers façade：三 arm re-export + 新檔實體
    assert "pub(super) use super::loop_pending_registration::handle_pending_registration;" in loop_text
    assert "pub(super) use super::loop_pipeline_command::handle_pipeline_command;" in loop_text
    assert "pub(super) use super::loop_tick::handle_tick_event;" in loop_text
    assert "pub(super) fn handle_pending_registration(" in pending_reg_text
    assert "pub(super) async fn handle_pipeline_command(" in pipeline_cmd_text
    assert "pub(super) fn handle_tick_event(" in tick_text
