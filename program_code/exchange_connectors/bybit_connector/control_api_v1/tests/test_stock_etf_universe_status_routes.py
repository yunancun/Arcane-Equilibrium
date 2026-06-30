"""Stock/ETF universe-status route tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from stock_etf_route_fixtures import (
    _make_client_with_ipc,
    _valid_universe_status,
    route_module,
    stock_etf_router,
    client_fail_closed,
)

def test_stock_etf_universe_status_returns_200_when_ipc_down(
    client_fail_closed: TestClient,
) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf/universe-status")
    assert resp.status_code == 200
    assert "no-store" in resp.headers["cache-control"]
    assert "private" in resp.headers["cache-control"]
    assert resp.headers["pragma"] == "no-cache"
    assert resp.headers["expires"] == "0"
    assert resp.headers["vary"] == "Authorization"
    body = resp.json()
    data = body["data"]
    assert body["ok"] is True
    assert body["data_category"] == "stock_etf_universe_status"
    assert data["degraded"] is True
    assert data["reason"] == "ipc_unavailable"
    assert data["universe_status_state"] == "degraded"
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["environment"] == "paper"
    assert data["gui_authority"] == "display_only"
    assert data["phase3_started"] is False
    assert data["first_ibkr_contact_allowed"] is False
    assert data["connector_enabled"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False
    assert data["collector_started"] is False
    assert data["market_data_ingestion_started"] is False
    assert data["db_apply_performed"] is False
    assert data["universe"]["blockers"] == ["ipc_unavailable"]
    assert data["universe"]["bybit_live_execution_unchanged"] is True
    assert data["universe"]["ibkr_live_denied"] is True


def test_stock_etf_universe_status_uses_only_readonly_fixture_method() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_universe_status"
        assert params == {}
        return _valid_universe_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/universe-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["degraded"] is False
    assert data["universe_status_state"] == "blocked"
    assert data["phase"] == "phase3_universe_status_source_fixture"
    assert data["phase3_started"] is False
    assert data["universe"]["expected_contract_id"] == (
        "stock_etf_pit_universe_contract_v1"
    )
    assert data["universe"]["accepted"] is False
    assert data["universe"]["universe_hash_present"] is False
    assert data["universe"]["constituent_count"] == 0
    assert data["universe"]["sample_constituents"] == []
    assert data["allowed_gui_actions"] == ["refresh_universe_status"]
    assert data["api_allowlist"]["contract_id"] == "non_bybit_api_allowlist_v1"
    assert data["collector_started"] is False
    assert data["market_data_ingestion_started"] is False
    assert data["db_apply_performed"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_universe_status_does_not_trust_client_state() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_universe_status"
        assert params == {}
        return _valid_universe_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        resp = client.get(
            "/api/v1/stock-etf/universe-status",
            params={
                "phase3_started": "true",
                "collector_started": "true",
                "first_ibkr_contact_allowed": "true",
            },
            headers={
                "X-Ibkr-Phase3-Started": "true",
                "X-Collector-Started": "true",
            },
        )
        data = resp.json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert "no-store" in resp.headers["cache-control"]
    assert data["phase3_started"] is False
    assert data["first_ibkr_contact_allowed"] is False
    assert data["collector_started"] is False
    assert data["market_data_ingestion_started"] is False
    assert data["db_apply_performed"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_universe_status_blocks_contract_violation() -> None:
    payload = _valid_universe_status()
    payload["phase3_started"] = True
    payload["asset_lane"] = "crypto_perp"
    payload["broker"] = "bybit"
    payload["environment"] = "live"
    payload["collector_started"] = True
    payload["market_data_ingestion_started"] = True
    payload["db_apply_performed"] = True
    payload["ibkr_call_performed"] = True
    payload["secret_slot_touched"] = True
    payload["order_routed"] = True
    payload["bybit_ipc_reused"] = True
    payload["universe"]["expected_contract_id"] = "wrong"
    payload["universe"]["ibkr_contact_performed"] = True
    payload["universe"]["secret_content_serialized"] = True
    payload["universe"]["bybit_live_execution_unchanged"] = False
    payload["universe"]["ibkr_live_denied"] = False
    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(return_value=payload)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/universe-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["universe_status_state"] == "contract_violation_blocked"
    assert data["degraded"] is True
    assert {
        "ibkr_call_performed",
        "secret_slot_touched",
        "order_routed",
        "bybit_ipc_reused",
        "asset_lane_mismatch",
        "broker_mismatch",
        "environment_mismatch",
        "phase3_started",
        "collector_started",
        "market_data_ingestion_started",
        "db_apply_performed",
        "universe_expected_contract_id_mismatch",
        "universe_ibkr_contact_performed",
        "universe_secret_content_serialized",
        "universe_bybit_live_not_protected",
        "universe_ibkr_live_not_denied",
    }.issubset(set(data["contract_violations"]))
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["environment"] == "paper"
    assert data["phase3_started"] is False
    assert data["collector_started"] is False
    assert data["market_data_ingestion_started"] is False
    assert data["db_apply_performed"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False


def test_stock_etf_universe_status_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf/universe-status")

    assert resp.status_code == 401
