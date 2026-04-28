"""Tests for Batch-A live close fail-closed behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import HTTPException
import pytest

from app import live_session_routes as lsr
from app import live_session_endpoints as lse


# ── Helpers ─────────────────────────────────────────────────────────────────

_CHANNEL_ERR = (
    "503: IPC command 'close_position' failed: Engine RPC error [-32603]: "
    "paper command channel not configured / 引擎 RPC 錯誤 [-32603]: "
    "paper command channel not configured"
)


def _make_fake_rc(positions=None, place_order_result=None, round_qty_result=None,
                  instrument_count=42):
    """Build a mock BybitClient exposing the methods the fallback path calls."""
    rc = MagicMock()
    rc.get_positions = MagicMock(return_value=positions or [])
    rc.place_order = MagicMock(
        return_value=place_order_result or {"order_id": "mock-1", "order_link_id": "mlid-1"}
    )
    rc.round_qty = MagicMock(
        side_effect=(lambda sym, q: round_qty_result if round_qty_result is not None else q)
    )
    # Default: instrument cache already warm so tests that don't care about
    # refresh_instruments behaviour aren't forced to stub it.
    # 預設：合約規格緩存已熱；不關心 refresh 行為的測試不需 stub。
    rc.instrument_count = MagicMock(return_value=instrument_count)
    rc.refresh_instruments = MagicMock(return_value=instrument_count)
    return rc


# ═══════════════════════════════════════════════════════════════════════════════
# Error classifier
# ═══════════════════════════════════════════════════════════════════════════════


def test_detects_channel_unavailable_error():
    assert lsr._is_live_channel_unavailable_error(RuntimeError(_CHANNEL_ERR)) is True


def test_does_not_flag_generic_errors():
    assert lsr._is_live_channel_unavailable_error(RuntimeError("timeout")) is False
    assert lsr._is_live_channel_unavailable_error(ValueError("retCode=110017")) is False
    assert lsr._is_live_channel_unavailable_error(Exception("connection refused")) is False


# ═══════════════════════════════════════════════════════════════════════════════
# REST reduce_only helper disabled
# ═══════════════════════════════════════════════════════════════════════════════


def test_rest_close_helper_is_disabled():
    rc = _make_fake_rc()
    with pytest.raises(HTTPException) as excinfo:
        lsr._rest_close_position_reduce_only(rc, "BTCUSDT", 0.05, is_long=True)
    assert excinfo.value.status_code == 409
    rc.place_order.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# _sweep_live_orphan_positions — live IPC fail-closed paths
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_orphan_sweep_blocks_on_channel_unavailable(monkeypatch):
    """
    Every IPC call fails with channel-not-configured. Batch A must not use
    Python REST fallback; the sweep records blocked positions and calls no
    exchange write method.
    """
    rc = _make_fake_rc(
        positions=[
            {"symbol": "ADAUSDT", "size": 100.0, "side": "Buy"},
            {"symbol": "ETHUSDT", "size": 0.2, "side": "Sell"},
        ]
    )
    monkeypatch.setattr(lsr, "_get_rust_client_safe", lambda: rc)

    async def _fail_channel(method, params):
        raise RuntimeError(_CHANNEL_ERR)

    monkeypatch.setattr(lsr, "_ipc_command", _fail_channel)

    errors: list[str] = []
    result = await lsr._sweep_live_orphan_positions(errors)

    assert len(errors) == 2
    assert "orphan_ADAUSDT_live_channel_unavailable" in errors
    assert "orphan_ETHUSDT_live_channel_unavailable" in errors
    assert result["swept"] == 0
    assert result["found"] == 2
    assert result["rest_fallback_disabled"] is True
    assert result["blocked_no_live_channel"] == 2
    assert result["swept_via_ipc"] == 0
    rc.place_order.assert_not_called()


@pytest.mark.asyncio
async def test_orphan_sweep_does_not_fallback_on_generic_error(monkeypatch):
    """
    IPC fails with a non-channel error (e.g. Bybit retCode=10001) → DO NOT
    silently REST fallback; record the error so operators see the real problem.
    """
    rc = _make_fake_rc(positions=[{"symbol": "BTCUSDT", "size": 0.01, "side": "Buy"}])
    monkeypatch.setattr(lsr, "_get_rust_client_safe", lambda: rc)

    async def _fail_generic(method, params):
        raise RuntimeError("Bybit retCode=10001 qty step violation")

    monkeypatch.setattr(lsr, "_ipc_command", _fail_generic)

    errors: list[str] = []
    result = await lsr._sweep_live_orphan_positions(errors)

    assert len(errors) == 1
    assert "orphan_BTCUSDT" in errors[0]
    assert "qty step" in errors[0]
    assert result["swept"] == 0
    assert "rest_fallback" not in result
    rc.place_order.assert_not_called()  # MUST NOT REST-close on unknown IPC error


@pytest.mark.asyncio
async def test_orphan_sweep_does_not_call_rest_when_channel_unavailable(monkeypatch):
    """
    Even if a fake REST client would raise, channel-unavailable must not reach
    REST at all.
    """
    rc = _make_fake_rc(positions=[{"symbol": "SOLUSDT", "size": 5.0, "side": "Buy"}])
    rc.place_order = MagicMock(side_effect=RuntimeError("network timeout"))
    monkeypatch.setattr(lsr, "_get_rust_client_safe", lambda: rc)

    async def _fail_channel(method, params):
        raise RuntimeError(_CHANNEL_ERR)

    monkeypatch.setattr(lsr, "_ipc_command", _fail_channel)

    errors: list[str] = []
    result = await lsr._sweep_live_orphan_positions(errors)

    assert len(errors) == 1
    assert "orphan_SOLUSDT_live_channel_unavailable" in errors[0]
    assert result["swept"] == 0
    assert result["rest_fallback_disabled"] is True
    rc.place_order.assert_not_called()


@pytest.mark.asyncio
async def test_orphan_sweep_no_positions_returns_zero_swept(monkeypatch):
    rc = _make_fake_rc(positions=[])
    monkeypatch.setattr(lsr, "_get_rust_client_safe", lambda: rc)

    async def _unused(method, params):
        raise AssertionError("IPC must not be called when there are no positions")

    monkeypatch.setattr(lsr, "_ipc_command", _unused)

    errors: list[str] = []
    result = await lsr._sweep_live_orphan_positions(errors)
    assert errors == []
    assert result == {"swept": 0}


@pytest.mark.asyncio
async def test_orphan_sweep_mixed_ipc_and_blocked(monkeypatch):
    """
    First position closes via IPC, second hits channel-not-configured. The
    second is blocked; no direct REST fallback is attempted.
    """
    rc = _make_fake_rc(
        positions=[
            {"symbol": "ADAUSDT", "size": 100.0, "side": "Buy"},
            {"symbol": "ETHUSDT", "size": 0.2, "side": "Sell"},
        ]
    )
    monkeypatch.setattr(lsr, "_get_rust_client_safe", lambda: rc)

    calls = {"n": 0}

    async def _first_ok_then_channel(method, params):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"close_all_sent": True}
        raise RuntimeError(_CHANNEL_ERR)

    monkeypatch.setattr(lsr, "_ipc_command", _first_ok_then_channel)

    errors: list[str] = []
    result = await lsr._sweep_live_orphan_positions(errors)

    assert errors == ["orphan_ETHUSDT_live_channel_unavailable"]
    assert result["swept"] == 1
    assert result["rest_fallback_disabled"] is True
    assert result["blocked_no_live_channel"] == 1
    assert result["swept_via_ipc"] == 1
    rc.place_order.assert_not_called()


@pytest.mark.asyncio
async def test_session_stop_channel_unavailable_returns_409(monkeypatch):
    """
    Session stop may revoke session authority, but if live close cannot be
    dispatched it must be operator-visible 409 instead of a false "closed" 200.
    """
    monkeypatch.setattr(lsr, "_require_operator", lambda actor: None)
    monkeypatch.setattr(lsr, "_set_execution_authority", lambda authority: None)
    monkeypatch.setattr(lse, "_revoke_live_governance_auth", lambda **kwargs: None)

    class _RustReader:
        def is_available(self):
            return True

    monkeypatch.setattr(lse, "get_rust_reader", lambda: _RustReader())

    async def _fail_channel(method, params):
        assert method == "close_all_positions"
        assert params == {"engine": "live"}
        raise RuntimeError(_CHANNEL_ERR)

    async def _unused_sweep(errors):
        raise AssertionError("orphan sweep must be skipped when close_all channel is unavailable")

    monkeypatch.setattr(lsr, "_ipc_command", _fail_channel)
    monkeypatch.setattr(lsr, "_sweep_live_orphan_positions", _unused_sweep)

    with pytest.raises(HTTPException) as excinfo:
        await lse.post_live_session_stop(actor=SimpleNamespace(actor_id="op-batch-a"))

    assert excinfo.value.status_code == 409
    detail = excinfo.value.detail
    assert detail["rest_fallback"] is False
    assert detail["close_result"]["rest_fallback_disabled"] is True
    assert detail["session_authority_revoked"] is True
