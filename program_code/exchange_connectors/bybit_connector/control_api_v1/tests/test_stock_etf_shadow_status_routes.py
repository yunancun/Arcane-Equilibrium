"""Stock/ETF shadow-status route tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from stock_etf_route_fixtures import (
    _make_client_with_ipc,
    _valid_shadow_status,
    route_module,
    stock_etf_router,
    client_fail_closed,
)

def test_stock_etf_shadow_status_returns_200_when_ipc_down(
    client_fail_closed: TestClient,
) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf/shadow-status")
    assert resp.status_code == 200
    assert "no-store" in resp.headers["cache-control"]
    assert "private" in resp.headers["cache-control"]
    assert resp.headers["pragma"] == "no-cache"
    assert resp.headers["expires"] == "0"
    assert resp.headers["vary"] == "Authorization"
    body = resp.json()
    data = body["data"]
    assert body["ok"] is True
    assert body["data_category"] == "stock_etf_shadow_status"
    assert data["degraded"] is True
    assert data["reason"] == "ipc_unavailable"
    assert data["shadow_status_state"] == "degraded"
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["environment"] == "shadow"
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
    assert data["shadow_collector_started"] is False
    assert data["shadow_signal_emitted"] is False
    assert data["shadow_fill_generated"] is False
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    assert data["shadow_fill_model"]["blockers"] == ["ipc_unavailable"]
    assert data["shadow_fill_model"]["broker_paper_fill_linked"] is False
    assert data["shadow_fill_model"]["live_fill_linked"] is False
    assert data["strategy_hypothesis"]["paper_shadow_only"] is True
    assert data["strategy_hypothesis"]["profitability_claimed"] is False
    assert data["strategy_hypothesis"]["live_or_tiny_live_authority_claimed"] is False


def test_stock_etf_shadow_status_uses_only_readonly_fixture_method() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_shadow_status"
        assert params == {}
        return _valid_shadow_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/shadow-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["degraded"] is False
    assert data["shadow_status_state"] == "blocked"
    assert data["phase"] == "phase3_shadow_status_source_fixture"
    assert data["phase3_started"] is False
    assert data["shadow_fill_model"]["expected_contract_id"] == (
        "stock_shadow_fill_model_v1"
    )
    assert data["shadow_fill_model"]["accepted"] is False
    assert data["shadow_fill_model"]["synthetic_shadow"] is False
    assert data["shadow_fill_model"]["broker_paper_fill_linked"] is False
    assert data["shadow_fill_model"]["live_fill_linked"] is False
    assert data["strategy_hypothesis"]["expected_contract_id"] == (
        "stock_etf_strategy_hypothesis_contract_v1"
    )
    assert data["strategy_hypothesis"]["accepted"] is False
    assert data["strategy_hypothesis"]["paper_shadow_only"] is True
    assert data["allowed_gui_actions"] == ["refresh_shadow_status"]
    assert data["api_allowlist"]["contract_id"] == "non_bybit_api_allowlist_v1"
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_shadow_status_does_not_trust_client_state() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_shadow_status"
        assert params == {}
        return _valid_shadow_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        resp = client.get(
            "/api/v1/stock-etf/shadow-status",
            params={
                "phase3_started": "true",
                "shadow_fill_generated": "true",
                "first_ibkr_contact_allowed": "true",
            },
            headers={
                "X-Ibkr-Phase3-Started": "true",
                "X-Shadow-Fill-Generated": "true",
            },
        )
        data = resp.json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert "no-store" in resp.headers["cache-control"]
    assert data["phase3_started"] is False
    assert data["first_ibkr_contact_allowed"] is False
    assert data["shadow_collector_started"] is False
    assert data["shadow_signal_emitted"] is False
    assert data["shadow_fill_generated"] is False
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_shadow_status_blocks_contract_violation() -> None:
    payload = _valid_shadow_status()
    payload["phase3_started"] = True
    payload["asset_lane"] = "crypto_perp"
    payload["broker"] = "bybit"
    payload["environment"] = "paper"
    payload["shadow_collector_started"] = True
    payload["shadow_signal_emitted"] = True
    payload["shadow_fill_generated"] = True
    payload["scorecard_writer_started"] = True
    payload["db_apply_performed"] = True
    payload["ibkr_call_performed"] = True
    payload["secret_slot_touched"] = True
    payload["order_routed"] = True
    payload["bybit_ipc_reused"] = True
    payload["shadow_fill_model"]["expected_contract_id"] = "wrong"
    payload["shadow_fill_model"]["broker_paper_fill_linked"] = True
    payload["shadow_fill_model"]["live_fill_linked"] = True
    payload["strategy_hypothesis"]["expected_contract_id"] = "wrong"
    payload["strategy_hypothesis"]["paper_shadow_only"] = False
    payload["strategy_hypothesis"]["profitability_claimed"] = True
    payload["strategy_hypothesis"]["live_or_tiny_live_authority_claimed"] = True
    payload["strategy_hypothesis"]["bybit_live_execution_unchanged"] = False
    payload["strategy_hypothesis"]["ibkr_live_denied"] = False
    payload["strategy_hypothesis"]["ibkr_contact_performed"] = True
    payload["strategy_hypothesis"]["secret_content_serialized"] = True
    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(return_value=payload)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/shadow-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["shadow_status_state"] == "contract_violation_blocked"
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
        "shadow_collector_started",
        "shadow_signal_emitted",
        "shadow_fill_generated",
        "scorecard_writer_started",
        "db_apply_performed",
        "shadow_fill_expected_contract_id_mismatch",
        "shadow_fill_linked_to_broker_paper_fill",
        "shadow_fill_linked_to_live_fill",
        "strategy_expected_contract_id_mismatch",
        "strategy_not_paper_shadow_only",
        "strategy_profitability_claimed",
        "strategy_live_or_tiny_live_authority_claimed",
        "strategy_bybit_live_not_protected",
        "strategy_ibkr_live_not_denied",
        "strategy_ibkr_contact_performed",
        "strategy_secret_content_serialized",
    }.issubset(set(data["contract_violations"]))
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["environment"] == "shadow"
    assert data["phase3_started"] is False
    assert data["shadow_collector_started"] is False
    assert data["shadow_signal_emitted"] is False
    assert data["shadow_fill_generated"] is False
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False


def test_stock_etf_shadow_status_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf/shadow-status")

    assert resp.status_code == 401
