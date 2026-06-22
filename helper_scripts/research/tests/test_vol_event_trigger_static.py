"""Static contracts for vol_event_trigger runtime artifacts."""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "order_flow_alpha" / "vol_event_trigger.py"


def _src() -> str:
    return SRC.read_text(encoding="utf-8")


def test_ruling_report_defaults_to_data_dir_not_repo_tree() -> None:
    src = _src()

    assert "OPENCLAW_VOL_EVENT_RULING_REPORT_PATH" in src
    assert (
        'return os.path.join(_data_dir(), "order_flow_alpha", '
        '"vol-event-robust-ruling.md")'
    ) in src
    assert '"docs", "CCAgentWorkSpace", "E1", "workspace", "reports",' not in src


def test_generated_ruling_markdown_has_no_known_trailing_space_literal() -> None:
    src = _src()

    assert 'fee-wall（taker 6bp / ")' not in src
    assert 'fee-wall（taker 6bp /")' in src
