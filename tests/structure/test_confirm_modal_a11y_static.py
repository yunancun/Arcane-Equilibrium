from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC = REPO_ROOT / "program_code/exchange_connectors/bybit_connector/control_api_v1/app/static"


def _source(rel_path: str) -> str:
    return (STATIC / rel_path).read_text(encoding="utf-8")


def test_common_confirm_modal_has_dialog_a11y_and_focus_trap() -> None:
    source = _source("common.js")

    assert 'role="dialog" aria-modal="true" aria-labelledby="oc-gc-title" tabindex="-1"' in source
    assert "var previousActive = document.activeElement;" in source
    assert "function focusableNodes()" in source
    assert "overlay.onkeydown = function(ev)" in source
    assert "ev.key === 'Escape'" in source
    assert "ev.key !== 'Tab'" in source
    assert "cancelBtn.focus()" in source
    assert "overlay.onkeydown = null;" in source
    assert "previousActive.focus()" in source


def test_app_confirm_modal_has_dialog_a11y_and_focus_trap() -> None:
    source = _source("app.js")

    assert 'dialog.setAttribute("role", "dialog")' in source
    assert 'dialog.setAttribute("aria-modal", "true")' in source
    assert 'dialog.setAttribute("aria-labelledby", "confirmModalTitle")' in source
    assert 'dialog.setAttribute("tabindex", "-1")' in source
    assert "const previousActive = document.activeElement;" in source
    assert "const focusableNodes = () => Array.from(" in source
    assert "modal.onkeydown = (ev) =>" in source
    assert 'ev.key === "Escape"' in source
    assert 'ev.key !== "Tab"' in source
    assert "cancel.focus()" in source
    assert "modal.onkeydown = null;" in source
    assert "previousActive.focus()" in source
