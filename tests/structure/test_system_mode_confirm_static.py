from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TAB_SYSTEM = (
    REPO_ROOT
    / "program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-system.html"
)


def _source() -> str:
    return TAB_SYSTEM.read_text(encoding="utf-8")


def test_live_reserved_confirmation_has_countdown_and_hold_guard() -> None:
    source = _source()

    assert "const LIVE_RESERVED_CONFIRM_DELAY_MS = 5000;" in source
    assert "const LIVE_RESERVED_HOLD_MS = 1200;" in source
    assert 'id="live-confirm-guard"' in source
    assert 'onclick="handleConfirmOkClick(event)"' in source
    assert "function startLiveReservedConfirmGuard()" in source
    assert "function beginLiveReservedConfirmHold(event)" in source
    assert "function handleConfirmOkClick(event)" in source
    assert "button.disabled = true;" in source
    assert "Math.ceil(remainingMs / 1000)" in source
    assert "setInterval(updateCountdown, 100)" in source
    assert "setTimeout(setLiveConfirmReady, LIVE_RESERVED_CONFIRM_DELAY_MS)" in source
    assert "setTimeout(() =>" in source
    assert "executeConfirmed();" in source


def test_live_reserved_guard_is_scoped_to_live_mode_only() -> None:
    source = _source()

    confirm_mode = source[source.index("function confirmMode(mode)") : source.index("async function executeModeChange")]
    assert "resetLiveReservedConfirmGuard();" in confirm_mode
    assert "if (mode === 'live_reserved') startLiveReservedConfirmGuard();" in confirm_mode

    click_handler = source[source.index("function handleConfirmOkClick(event)") : source.index("function setupLiveReservedConfirmButton")]
    assert "if (_pendingMode === 'live_reserved')" in click_handler
    assert "executeConfirmed();" in click_handler


def test_live_reserved_hold_supports_pointer_and_keyboard_cancel_paths() -> None:
    source = _source()

    setup = source[source.index("function setupLiveReservedConfirmButton()") : source.index("function closeConfirm()")]
    for event_name in ("pointerdown", "pointerup", "pointerleave", "pointercancel", "keydown", "keyup"):
        assert event_name in setup
    assert "cancelLiveReservedConfirmHold" in setup
    assert "event.key === 'Enter' || event.key === ' '" in setup
