"""
Stock/ETF IBKR readiness route and GUI contract tests.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import stock_etf_routes as route_module  # noqa: E402
from app.main_legacy import AuthenticatedActor, current_actor  # noqa: E402
from app.stock_etf_routes import stock_etf_router  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parents[1] / "app" / "static"


def _viewer_actor() -> AuthenticatedActor:
    return AuthenticatedActor(
        actor_id="test-viewer",
        actor_type="human",
        roles={"viewer"},
        scopes={"private_readonly"},
    )


@pytest.fixture
def client_fail_closed() -> TestClient:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    app.dependency_overrides[current_actor] = _viewer_actor
    with patch.object(route_module, "_get_ipc", AsyncMock(return_value=None)):
        yield TestClient(app)


def _make_client_with_ipc(fake_ipc: Any) -> TestClient:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    app.dependency_overrides[current_actor] = _viewer_actor
    patcher = patch.object(route_module, "_get_ipc", AsyncMock(return_value=fake_ipc))
    patcher.start()
    client = TestClient(app)
    client._stock_etf_patcher = patcher  # type: ignore[attr-defined]
    return client


def test_stock_etf_readiness_returns_200_when_ipc_down(client_fail_closed: TestClient) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf/readiness")
    assert resp.status_code == 200
    body = resp.json()
    data = body["data"]
    assert body["ok"] is True
    assert body["data_category"] == "stock_etf_readiness"
    assert data["degraded"] is True
    assert data["reason"] == "ipc_unavailable"
    assert data["readiness_state"] == "degraded"
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["default_asset_lane"] == "crypto_perp"
    assert data["gui_authority"] == "display_only"
    assert data["stock_live_disabled"] is True
    assert data["first_ibkr_contact_allowed"] is False
    assert data["immutable_pass_artifact_present"] is False
    assert data["connector_enabled"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False


def test_stock_etf_readiness_uses_only_readonly_fixture_method() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_readiness"
        assert params == {}
        return {
            "phase": "phase2_precontact_source_fixture",
            "readiness": {
                "asset_lane": "stock_etf_cash",
                "broker": "ibkr",
                "default_asset_lane": "crypto_perp",
                "readonly_ready": True,
                "paper_ready": False,
                "shadow_only": True,
                "live_denied": True,
                "denial_reasons": ["shadow_only"],
            },
            "phase2": {
                "external_surface_gate": {
                    "status": "BLOCKED",
                    "ibkr_contact_allowed": False,
                    "blockers": ["status_not_pass"],
                    "ibkr_call_performed": False,
                },
                "policy_prerequisites": {
                    "bundle_accepted": True,
                    "blockers": [],
                    "flags": {"python_no_write_guard_present": True},
                },
                "immutable_pass_artifact_present": False,
                "first_ibkr_contact_allowed": False,
                "connector_enabled": False,
                "secret_slot_touched": False,
                "order_routed": False,
            },
            "ibkr_live_enabled": False,
            "ibkr_call_performed": False,
            "secret_slot_touched": False,
            "order_routed": False,
            "bybit_ipc_reused": False,
        }

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/readiness").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["degraded"] is False
    assert data["readiness_state"] == "phase2_blocked"
    assert data["source_readiness"]["readonly_ready"] is True
    assert data["source_readiness"]["paper_ready"] is False
    assert data["source_readiness"]["live_denied"] is True
    assert data["phase2_gate_status"] == "BLOCKED"
    assert data["phase2_gate_blockers"] == ["status_not_pass"]
    assert "ibkr_live_order_submit" in data["denied_operations"]
    assert "ibkr_secret_slot_creation" in data["denied_operations"]
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_readiness_blocks_contract_violation() -> None:
    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(
        return_value={
            "readiness": {
                "asset_lane": "stock_etf_cash",
                "broker": "ibkr",
                "default_asset_lane": "stock_etf_cash",
                "readonly_ready": True,
                "paper_ready": True,
                "shadow_only": False,
                "live_denied": True,
                "denial_reasons": [],
            },
            "phase2": {
                "external_surface_gate": {"status": "PASS", "ibkr_contact_allowed": True, "blockers": []},
                "immutable_pass_artifact_present": True,
                "first_ibkr_contact_allowed": True,
                "connector_enabled": True,
            },
            "ibkr_call_performed": True,
            "secret_slot_touched": True,
            "order_routed": True,
            "bybit_ipc_reused": True,
        }
    )
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/readiness").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["readiness_state"] == "contract_violation_blocked"
    assert data["degraded"] is True
    assert set(data["contract_violations"]) == {
        "ibkr_call_performed",
        "secret_slot_touched",
        "order_routed",
        "bybit_ipc_reused",
    }
    assert data["ibkr_live_enabled"] is False
    assert data["stock_live_disabled"] is True
    assert data["paper_order_entry_visible"] is False


def test_stock_etf_readiness_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf/readiness")

    assert resp.status_code == 401


def test_stock_etf_redirect_to_static_tab(client_fail_closed: TestClient) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "/static/tab-stock-etf.html" in resp.headers.get("location", "")


def test_stock_etf_console_tab_registered() -> None:
    console = (STATIC_DIR / "console.html").read_text(encoding="utf-8")
    assert "id: 'stock-etf'" in console
    assert "tab-stock-etf.html" in console
    assert "lane crypto_perp" in console
    assert "login_success" not in console


def test_stock_etf_router_registered_in_main_app() -> None:
    main_source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(
        encoding="utf-8"
    )
    assert "from .stock_etf_routes import stock_etf_router" in main_source
    assert "app.include_router(stock_etf_router)" in main_source


def test_stock_etf_static_tab_is_readonly_display_only() -> None:
    source = (STATIC_DIR / "tab-stock-etf.html").read_text(encoding="utf-8")
    assert "/api/v1/stock-etf/readiness" in source
    assert "ocPost(" not in source
    assert "method: 'POST'" not in source
    assert "method: \"POST\"" not in source
    assert "stock_etf.submit_paper_order" not in source
    assert "stock_etf.cancel_paper_order" not in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source
