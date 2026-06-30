"""Stock/ETF lane-status route tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from stock_etf_route_fixtures import (
    _make_client_with_ipc,
    _valid_lane_status,
    client_fail_closed,
)

def test_stock_etf_lane_status_returns_200_when_ipc_down(client_fail_closed: TestClient) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf/lane-status")
    assert resp.status_code == 200
    assert "no-store" in resp.headers["cache-control"]
    assert "private" in resp.headers["cache-control"]
    assert resp.headers["vary"] == "Authorization"
    body = resp.json()
    data = body["data"]
    assert body["ok"] is True
    assert body["data_category"] == "stock_etf_lane_status"
    assert data["degraded"] is True
    assert data["reason"] == "ipc_unavailable"
    assert data["lane_status_state"] == "degraded"
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["default_asset_lane"] == "crypto_perp"
    assert data["gui_authority"] == "display_only"
    assert data["flags"]["stock_etf_lane_enabled"] is False
    assert data["flags"]["ibkr_readonly_enabled"] is False
    assert data["flags"]["ibkr_paper_enabled"] is False
    assert data["flags"]["stock_etf_shadow_only"] is True
    assert data["first_ibkr_contact_allowed"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False


def test_stock_etf_lane_status_uses_only_readonly_fixture_method() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_lane_status"
        assert params == {}
        return _valid_lane_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/lane-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["degraded"] is False
    assert data["lane_status_state"] == "phase2_blocked"
    assert data["flags"]["stock_etf_lane_enabled"] is True
    assert data["flags"]["ibkr_readonly_enabled"] is True
    assert data["flags"]["ibkr_paper_enabled"] is False
    assert data["flags"]["stock_etf_shadow_only"] is True
    assert data["api_allowlist"]["contract_id"] == "non_bybit_api_allowlist_v1"
    assert data["allowed_gui_actions"] == ["refresh_lane_status", "refresh_readiness"]
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_lane_status_does_not_trust_client_lane_state() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_lane_status"
        assert params == {}
        return _valid_lane_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        resp = client.get(
            "/api/v1/stock-etf/lane-status",
            params={
                "default_asset_lane": "stock_etf_cash",
                "ibkr_paper_enabled": "true",
                "first_ibkr_contact_allowed": "true",
            },
            headers={"X-Asset-Lane": "stock_etf_cash", "X-Ibkr-Paper-Ready": "true"},
        )
        data = resp.json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert "no-store" in resp.headers["cache-control"]
    assert data["default_asset_lane"] == "crypto_perp"
    assert data["flags"]["asset_lane_default"] == "crypto_perp"
    assert data["flags"]["ibkr_paper_enabled"] is False
    assert data["first_ibkr_contact_allowed"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_lane_status_blocks_contract_violation() -> None:
    payload = _valid_lane_status()
    payload["asset_lane"] = "crypto_perp"
    payload["broker"] = "bybit"
    payload["ibkr_call_performed"] = True
    payload["secret_slot_touched"] = True
    payload["order_routed"] = True
    payload["bybit_ipc_reused"] = True
    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(return_value=payload)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/lane-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["lane_status_state"] == "contract_violation_blocked"
    assert data["degraded"] is True
    assert set(data["contract_violations"]) == {
        "ibkr_call_performed",
        "secret_slot_touched",
        "order_routed",
        "bybit_ipc_reused",
        "asset_lane_mismatch",
        "broker_mismatch",
    }
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["paper_order_entry_visible"] is False
