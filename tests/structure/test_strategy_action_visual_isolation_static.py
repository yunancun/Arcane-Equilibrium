from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC = REPO_ROOT / "program_code/exchange_connectors/bybit_connector/control_api_v1/app/static"


def _source(rel_path: str) -> str:
    return (STATIC / rel_path).read_text(encoding="utf-8")


def test_common_css_defines_action_risk_zones() -> None:
    source = _source("common.js")

    for marker in (
        ".oc-btn-warning",
        ".oc-btn-critical",
        ".oc-btn-destructive",
        ".oc-action-row",
        ".oc-action-cluster-pause",
        ".oc-action-cluster-stop",
        ".oc-action-cluster-destructive",
        ".oc-toolbar-danger-action",
        ".oc-row-close-action",
    ):
        assert marker in source

    assert '"paper-stop-all"' in source
    assert "typeof actionName === 'object'" in source
    assert "confirmBtn.className = 'oc-btn ' + (meta.confirmClass || 'oc-btn-danger');" in source


def test_strategy_stop_pause_delete_are_visually_separated() -> None:
    source = _source("tab-strategy.html")

    assert "oc-action-row-strategy" in source
    assert 'data-danger-zone="strategy-pause"' in source
    assert 'data-danger-zone="strategy-stop"' in source
    assert 'data-danger-zone="strategy-delete"' in source
    assert "oc-btn-warning oc-action-pause" in source
    assert "oc-btn-danger oc-btn-critical oc-action-stop" in source
    assert "oc-btn-destructive oc-action-delete" in source
    assert 'openConfirmModal("delete-strategy")' in source
    assert "confirm(" not in source


def test_paper_stop_and_close_actions_use_zones_and_custom_confirm() -> None:
    source = _source("tab-paper.html")

    assert 'id="paper-session-controls"' in source
    assert 'data-danger-zone="paper-session-pause"' in source
    assert 'data-danger-zone="paper-session-stop"' in source
    assert 'data-danger-zone="paper-dual-stop"' in source
    assert 'id="btn-pause"' in source and "oc-btn-warning" in source
    assert 'id="btn-stop"' in source and "oc-btn-critical" in source
    assert 'id="btn-stop-all"' in source and "oc-btn-destructive" in source
    assert 'openConfirmModal("paper-stop-all")' in source
    assert "oc-toolbar-danger-action" in source
    assert "oc-row-close-action" in source
    assert "confirm(" not in source


def test_live_stop_emergency_and_close_actions_are_visually_separated() -> None:
    source = _source("tab-live.html")

    assert ".live-shutdown-zone" in source
    assert 'data-danger-zone="live-shutdown"' in source
    assert "live-stop-action" in source
    assert "live-emergency-action" in source
    assert "live-close-all-action" in source
    assert "oc-toolbar-danger-action live-close-all-action" in source
    assert "oc-row-close-action" in source
    assert "openConfirmModal({" in source
    assert "confirmClass: 'oc-btn-destructive oc-btn-critical'" in source
    assert "confirmClass: 'oc-btn-danger oc-btn-critical'" in source
    assert "confirm(" not in source
