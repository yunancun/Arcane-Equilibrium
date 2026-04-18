"""
Tests for LIVE-GATE-FALLBACK-1 in live_session_routes.

Covers the REST-only reduce_only close path that activates when the Live IPC
command channel is unavailable (Rust rejected Live pipeline spawn because
authorization.json was missing / invalid under LIVE-GATE-BINDING-1).

測試 LIVE-GATE-FALLBACK-1：Live IPC 命令通道不可用時的 REST-only 平倉降級路徑。
觸發條件：LIVE-GATE-BINDING-1 因 authorization.json 缺失/無效而拒絕啟動
Live pipeline，導致 Rust 未註冊 channels.live。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app import live_session_routes as lsr


# ── Helpers ─────────────────────────────────────────────────────────────────

_CHANNEL_ERR = (
    "503: IPC command 'close_position' failed: Engine RPC error [-32603]: "
    "paper command channel not configured / 引擎 RPC 錯誤 [-32603]: "
    "paper command channel not configured"
)


def _make_fake_rc(positions=None, place_order_result=None, round_qty_result=None):
    """Build a mock BybitClient exposing the methods the fallback path calls."""
    rc = MagicMock()
    rc.get_positions = MagicMock(return_value=positions or [])
    rc.place_order = MagicMock(
        return_value=place_order_result or {"order_id": "mock-1", "order_link_id": "mlid-1"}
    )
    rc.round_qty = MagicMock(
        side_effect=(lambda sym, q: round_qty_result if round_qty_result is not None else q)
    )
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
# REST reduce_only helper
# ═══════════════════════════════════════════════════════════════════════════════


def test_rest_close_long_uses_sell_side_reduce_only():
    rc = _make_fake_rc()
    out = lsr._rest_close_position_reduce_only(rc, "BTCUSDT", 0.05, is_long=True)
    rc.place_order.assert_called_once()
    kwargs = rc.place_order.call_args.kwargs
    assert kwargs["symbol"] == "BTCUSDT"
    assert kwargs["side"] == "Sell"
    assert kwargs["order_type"] == "Market"
    assert kwargs["reduce_only"] is True
    assert kwargs["category"] == "linear"
    assert out["rest_closed"] is True
    assert out["order_id"] == "mock-1"


def test_rest_close_short_uses_buy_side_reduce_only():
    rc = _make_fake_rc()
    lsr._rest_close_position_reduce_only(rc, "ETHUSDT", 0.2, is_long=False)
    assert rc.place_order.call_args.kwargs["side"] == "Buy"
    assert rc.place_order.call_args.kwargs["reduce_only"] is True


def test_rest_close_aligns_qty_via_round_qty():
    rc = _make_fake_rc(round_qty_result=0.048)
    out = lsr._rest_close_position_reduce_only(rc, "BTCUSDT", 0.0501, is_long=True)
    rc.round_qty.assert_called_once_with("BTCUSDT", 0.0501)
    assert out["qty"] == 0.048
    assert rc.place_order.call_args.kwargs["qty"] == 0.048


def test_rest_close_survives_round_qty_failure():
    """round_qty failure must NOT block a close — fall back to raw qty."""
    rc = MagicMock()
    rc.round_qty = MagicMock(side_effect=RuntimeError("instrument cache cold"))
    rc.place_order = MagicMock(return_value={"order_id": "x"})
    out = lsr._rest_close_position_reduce_only(rc, "BTCUSDT", 0.05, is_long=True)
    assert out["qty"] == 0.05  # raw qty preserved
    assert rc.place_order.called


# ═══════════════════════════════════════════════════════════════════════════════
# _sweep_live_orphan_positions — IPC → REST fallback paths
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_orphan_sweep_fallback_on_channel_unavailable(monkeypatch):
    """
    Every IPC call fails with channel-not-configured → every position closes
    via REST instead → swept count matches, errors list stays empty, response
    is marked rest_fallback=True.
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

    assert errors == []  # channel-not-configured is NOT recorded as an error when fallback succeeds
    assert result["swept"] == 2
    assert result["found"] == 2
    assert result["rest_fallback"] is True
    assert result["swept_via_ipc"] == 0
    assert result["swept_via_rest"] == 2
    assert rc.place_order.call_count == 2
    # Verify side mapping per position
    sides = [call.kwargs["side"] for call in rc.place_order.call_args_list]
    assert sides == ["Sell", "Buy"]  # ADA long → Sell, ETH short → Buy


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
async def test_orphan_sweep_records_rest_failure(monkeypatch):
    """
    IPC fails with channel-not-configured AND REST also fails → record error,
    do NOT increment swept_via_rest.
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
    assert "orphan_SOLUSDT_rest" in errors[0]
    assert "network timeout" in errors[0]
    assert result["swept"] == 0
    assert result.get("rest_fallback") is not True


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
async def test_orphan_sweep_mixed_ipc_and_rest(monkeypatch):
    """
    First position closes via IPC, second hits channel-not-configured (e.g.
    channel was torn down mid-sweep) → one IPC, one REST, both successful.
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

    assert errors == []
    assert result["swept"] == 2
    assert result["rest_fallback"] is True
    assert result["swept_via_ipc"] == 1
    assert result["swept_via_rest"] == 1
    assert rc.place_order.call_count == 1  # only ETH went REST
