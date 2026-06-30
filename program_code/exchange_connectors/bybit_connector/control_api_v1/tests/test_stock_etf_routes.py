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


def _valid_api_allowlist() -> dict[str, Any]:
    return {
        "contract_id": "non_bybit_api_allowlist_v1",
        "source_version": 1,
        "accepted": True,
        "blockers": [],
        "read_action_count": 10,
        "paper_write_action_count": 3,
        "denied_action_count": 10,
        "ibkr_contact_performed": False,
        "secret_content_serialized": False,
        "bybit_live_execution_protected": True,
    }


def _valid_lane_status() -> dict[str, Any]:
    return {
        "phase": "phase2_precontact_source_fixture",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "default_asset_lane": "crypto_perp",
        "flags": {
            "stock_etf_lane_enabled": True,
            "ibkr_readonly_enabled": True,
            "ibkr_paper_enabled": False,
            "asset_lane_default": "crypto_perp",
            "stock_etf_shadow_only": True,
        },
        "phase2": {
            "external_surface_gate": {
                "status": "BLOCKED",
                "ibkr_contact_allowed": False,
                "blockers": ["status_not_pass"],
                "ibkr_call_performed": False,
            },
            "api_allowlist": _valid_api_allowlist(),
            "immutable_pass_artifact_present": False,
            "first_ibkr_contact_allowed": False,
            "connector_enabled": False,
        },
        "ibkr_live_enabled": False,
        "ibkr_call_performed": False,
        "secret_slot_touched": False,
        "order_routed": False,
        "bybit_ipc_reused": False,
    }


def _valid_evidence_status() -> dict[str, Any]:
    return {
        "phase": "phase3_evidence_status_source_fixture",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "environment": "paper",
        "evidence_status_state": "blocked",
        "phase3_started": False,
        "market_data_provenance": {
            "expected_contract_id": "stock_market_data_provenance_v1",
            "contract_id": "",
            "source_version": 0,
            "accepted": False,
            "blockers": ["market_data_provenance_contract_id_mismatch"],
            "ibkr_contact_performed": False,
            "connector_runtime_started": False,
            "secret_content_serialized": False,
            "live_or_tiny_live_authorized": False,
        },
        "evidence_clock": {
            "expected_contract_id": "stock_etf_evidence_clock_v1",
            "contract_id": "",
            "source_version": 0,
            "status": "NOT_STARTED",
            "accepted": False,
            "blockers": ["evidence_clock_contract_id_mismatch"],
            "checker_contacted_ibkr": False,
            "checker_started_connector_runtime": False,
            "checker_started_evidence_clock": False,
            "checker_wrote_scorecard": False,
            "checker_applied_db": False,
            "secret_content_serialized": False,
            "live_or_tiny_live_authorized": False,
            "ibkr_readonly_paper_connector_green_5d": False,
            "shadow_collector_green_5d": False,
        },
        "frozen_inputs": {
            "accepted": False,
            "blockers": ["frozen_inputs_contract_id_mismatch"],
            "universe_hash_present": False,
            "benchmark_hash_present": False,
            "cost_model_hash_present": False,
            "strategy_hypothesis_hash_present": False,
            "reference_data_sources_contract_hash_present": False,
            "paper_shadow_divergence_threshold_hash_present": False,
            "gui_evidence_view_available": False,
            "daily_scorecard_regeneration_passed": False,
        },
        "dq_manifest": {
            "shape_accepted": False,
            "shape_blockers": ["trading_day_missing"],
            "passes_day_quality": False,
            "trading_day": "",
            "calendar_aware_coverage_bps": 0,
            "symbol_completeness_bps": 0,
            "latency_dq_passed": False,
            "market_data_provenance_accepted": False,
            "scorecard_regeneration_passed": False,
        },
        "scorecard": {
            "writer_started": False,
            "db_apply_performed": False,
            "daily_scorecard_regeneration_passed": False,
        },
        "phase2": {
            "external_surface_gate": {
                "status": "BLOCKED",
                "ibkr_contact_allowed": False,
                "blockers": ["status_not_pass"],
                "ibkr_call_performed": False,
            },
            "api_allowlist": _valid_api_allowlist(),
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


def test_stock_etf_readiness_returns_200_when_ipc_down(client_fail_closed: TestClient) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf/readiness")
    assert resp.status_code == 200
    assert "no-store" in resp.headers["cache-control"]
    assert "private" in resp.headers["cache-control"]
    assert resp.headers["pragma"] == "no-cache"
    assert resp.headers["expires"] == "0"
    assert resp.headers["vary"] == "Authorization"
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
                "api_allowlist": _valid_api_allowlist(),
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
    assert data["api_allowlist"]["contract_id"] == "non_bybit_api_allowlist_v1"
    assert data["api_allowlist"]["source_version"] == 1
    assert data["api_allowlist"]["accepted"] is True
    assert data["api_allowlist"]["read_action_count"] == 10
    assert data["api_allowlist"]["paper_write_action_count"] == 3
    assert data["api_allowlist"]["denied_action_count"] == 10
    assert "ibkr_live_order_submit" in data["denied_operations"]
    assert "ibkr_secret_slot_creation" in data["denied_operations"]
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_readiness_does_not_trust_client_lane_state() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_readiness"
        assert params == {}
        return {
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
                "api_allowlist": _valid_api_allowlist(),
                "immutable_pass_artifact_present": False,
                "first_ibkr_contact_allowed": False,
                "connector_enabled": False,
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
        resp = client.get(
            "/api/v1/stock-etf/readiness",
            params={
                "default_asset_lane": "stock_etf_cash",
                "paper_ready": "true",
                "first_ibkr_contact_allowed": "true",
            },
            headers={"X-Asset-Lane": "stock_etf_cash", "X-Ibkr-Paper-Ready": "true"},
        )
        data = resp.json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert "no-store" in resp.headers["cache-control"]
    assert data["default_asset_lane"] == "crypto_perp"
    assert data["source_readiness"]["paper_ready"] is False
    assert data["first_ibkr_contact_allowed"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
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
                "external_surface_gate": {
                    "status": "PASS",
                    "ibkr_contact_allowed": True,
                    "blockers": [],
                },
                "api_allowlist": _valid_api_allowlist(),
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


def test_stock_etf_readiness_blocks_missing_api_allowlist_contract() -> None:
    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(
        return_value={
            "readiness": {
                "asset_lane": "stock_etf_cash",
                "broker": "ibkr",
                "default_asset_lane": "crypto_perp",
                "readonly_ready": True,
                "paper_ready": False,
                "shadow_only": True,
                "live_denied": True,
                "denial_reasons": [],
            },
            "phase2": {
                "external_surface_gate": {
                    "status": "BLOCKED",
                    "ibkr_contact_allowed": False,
                    "blockers": ["status_not_pass"],
                    "ibkr_call_performed": False,
                },
                "immutable_pass_artifact_present": False,
                "first_ibkr_contact_allowed": False,
                "connector_enabled": False,
            },
            "ibkr_live_enabled": False,
            "ibkr_call_performed": False,
            "secret_slot_touched": False,
            "order_routed": False,
            "bybit_ipc_reused": False,
        }
    )
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/readiness").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["readiness_state"] == "contract_violation_blocked"
    assert data["degraded"] is True
    assert data["api_allowlist"]["accepted"] is False
    assert "api_allowlist_not_accepted" in data["contract_violations"]
    assert "api_allowlist_contract_id_mismatch" in data["contract_violations"]
    assert "api_allowlist_source_version_mismatch" in data["contract_violations"]


def test_stock_etf_readiness_rejects_boolean_api_allowlist_version() -> None:
    api_allowlist = _valid_api_allowlist()
    api_allowlist["source_version"] = True
    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(
        return_value={
            "readiness": {
                "asset_lane": "stock_etf_cash",
                "broker": "ibkr",
                "default_asset_lane": "crypto_perp",
                "readonly_ready": True,
                "paper_ready": False,
                "shadow_only": True,
                "live_denied": True,
                "denial_reasons": [],
            },
            "phase2": {
                "external_surface_gate": {
                    "status": "BLOCKED",
                    "ibkr_contact_allowed": False,
                    "blockers": ["status_not_pass"],
                    "ibkr_call_performed": False,
                },
                "api_allowlist": api_allowlist,
                "immutable_pass_artifact_present": False,
                "first_ibkr_contact_allowed": False,
                "connector_enabled": False,
            },
            "ibkr_live_enabled": False,
            "ibkr_call_performed": False,
            "secret_slot_touched": False,
            "order_routed": False,
            "bybit_ipc_reused": False,
        }
    )
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/readiness").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["readiness_state"] == "contract_violation_blocked"
    assert data["api_allowlist"]["source_version"] == 0
    assert "api_allowlist_source_version_mismatch" in data["contract_violations"]


def test_stock_etf_evidence_status_returns_200_when_ipc_down(
    client_fail_closed: TestClient,
) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf/evidence-status")
    assert resp.status_code == 200
    assert "no-store" in resp.headers["cache-control"]
    assert "private" in resp.headers["cache-control"]
    assert resp.headers["pragma"] == "no-cache"
    assert resp.headers["expires"] == "0"
    assert resp.headers["vary"] == "Authorization"
    body = resp.json()
    data = body["data"]
    assert body["ok"] is True
    assert body["data_category"] == "stock_etf_evidence_status"
    assert data["degraded"] is True
    assert data["reason"] == "ipc_unavailable"
    assert data["evidence_status_state"] == "degraded"
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
    assert data["evidence_clock_started"] is False
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    assert data["market_data_provenance"]["blockers"] == ["ipc_unavailable"]
    assert data["evidence_clock"]["status"] == "NOT_STARTED"
    assert data["evidence_clock"]["blockers"] == ["ipc_unavailable"]
    assert data["scorecard"]["writer_started"] is False
    assert data["scorecard"]["db_apply_performed"] is False


def test_stock_etf_evidence_status_uses_only_readonly_fixture_method() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_evidence_status"
        assert params == {}
        return _valid_evidence_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/evidence-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["degraded"] is False
    assert data["evidence_status_state"] == "blocked"
    assert data["phase"] == "phase3_evidence_status_source_fixture"
    assert data["phase3_started"] is False
    assert data["market_data_provenance"]["expected_contract_id"] == (
        "stock_market_data_provenance_v1"
    )
    assert data["market_data_provenance"]["accepted"] is False
    assert data["evidence_clock"]["expected_contract_id"] == (
        "stock_etf_evidence_clock_v1"
    )
    assert data["evidence_clock"]["status"] == "NOT_STARTED"
    assert data["frozen_inputs"]["gui_evidence_view_available"] is False
    assert data["dq_manifest"]["passes_day_quality"] is False
    assert data["scorecard"]["writer_started"] is False
    assert data["scorecard"]["db_apply_performed"] is False
    assert data["allowed_gui_actions"] == ["refresh_evidence_status"]
    assert data["api_allowlist"]["contract_id"] == "non_bybit_api_allowlist_v1"
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_evidence_status_does_not_trust_client_state() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_evidence_status"
        assert params == {}
        return _valid_evidence_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        resp = client.get(
            "/api/v1/stock-etf/evidence-status",
            params={
                "phase3_started": "true",
                "checker_wrote_scorecard": "true",
                "first_ibkr_contact_allowed": "true",
            },
            headers={
                "X-Ibkr-Phase3-Started": "true",
                "X-Scorecard-Writer-Started": "true",
            },
        )
        data = resp.json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert "no-store" in resp.headers["cache-control"]
    assert data["phase3_started"] is False
    assert data["first_ibkr_contact_allowed"] is False
    assert data["evidence_clock_started"] is False
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_evidence_status_blocks_contract_violation() -> None:
    payload = _valid_evidence_status()
    payload["phase3_started"] = True
    payload["asset_lane"] = "crypto_perp"
    payload["broker"] = "bybit"
    payload["environment"] = "live"
    payload["ibkr_call_performed"] = True
    payload["secret_slot_touched"] = True
    payload["order_routed"] = True
    payload["bybit_ipc_reused"] = True
    payload["market_data_provenance"]["ibkr_contact_performed"] = True
    payload["market_data_provenance"]["connector_runtime_started"] = True
    payload["market_data_provenance"]["secret_content_serialized"] = True
    payload["market_data_provenance"]["live_or_tiny_live_authorized"] = True
    payload["evidence_clock"]["checker_contacted_ibkr"] = True
    payload["evidence_clock"]["checker_started_connector_runtime"] = True
    payload["evidence_clock"]["checker_started_evidence_clock"] = True
    payload["evidence_clock"]["checker_wrote_scorecard"] = True
    payload["evidence_clock"]["checker_applied_db"] = True
    payload["evidence_clock"]["secret_content_serialized"] = True
    payload["evidence_clock"]["live_or_tiny_live_authorized"] = True
    payload["frozen_inputs"]["daily_scorecard_regeneration_passed"] = True
    payload["scorecard"]["writer_started"] = True
    payload["scorecard"]["db_apply_performed"] = True
    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(return_value=payload)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/evidence-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["evidence_status_state"] == "contract_violation_blocked"
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
        "market_data_ibkr_contact_performed",
        "market_data_connector_runtime_started",
        "market_data_secret_content_serialized",
        "market_data_live_or_tiny_live_authorized",
        "evidence_clock_contacted_ibkr",
        "evidence_clock_started_connector_runtime",
        "evidence_clock_started",
        "evidence_clock_wrote_scorecard",
        "evidence_clock_applied_db",
        "evidence_clock_secret_content_serialized",
        "evidence_clock_live_or_tiny_live_authorized",
        "frozen_inputs_daily_scorecard_regenerated",
        "scorecard_writer_started",
        "scorecard_db_apply_performed",
    }.issubset(set(data["contract_violations"]))
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["environment"] == "paper"
    assert data["phase3_started"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False
    assert data["evidence_clock_started"] is False
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False


def test_stock_etf_evidence_status_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf/evidence-status")

    assert resp.status_code == 401


def test_stock_etf_readiness_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf/readiness")

    assert resp.status_code == 401


def test_stock_etf_lane_status_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf/lane-status")

    assert resp.status_code == 401


def test_stock_etf_redirect_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf", follow_redirects=False)

    assert resp.status_code == 401


def test_stock_etf_openapi_exposes_stock_etf_get_only(client_fail_closed: TestClient) -> None:
    schema = client_fail_closed.get("/openapi.json").json()
    stock_paths = {
        path: set(methods)
        for path, methods in schema["paths"].items()
        if path.startswith("/api/v1/stock-etf")
    }

    assert stock_paths == {
        "/api/v1/stock-etf/evidence-status": {"get"},
        "/api/v1/stock-etf/lane-status": {"get"},
        "/api/v1/stock-etf/readiness": {"get"},
    }


def test_stock_etf_runtime_rejects_write_methods(client_fail_closed: TestClient) -> None:
    for path in (
        "/api/v1/stock-etf",
        "/api/v1/stock-etf/evidence-status",
        "/api/v1/stock-etf/lane-status",
        "/api/v1/stock-etf/readiness",
    ):
        for method in ("post", "put", "patch", "delete"):
            resp = getattr(client_fail_closed, method)(path)
            assert resp.status_code == 405, f"{method.upper()} {path} returned {resp.status_code}"


def test_stock_etf_redirect_to_static_tab(client_fail_closed: TestClient) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "/static/tab-stock-etf.html" in resp.headers.get("location", "")
    assert "no-store" in resp.headers["cache-control"]
    assert resp.headers["vary"] == "Authorization"


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
    assert "/api/v1/stock-etf/evidence-status" in source
    assert "/api/v1/stock-etf/lane-status" in source
    assert "/api/v1/stock-etf/readiness" in source
    assert "se-evidence-status" in source
    assert "se-evidence-body" in source
    assert "api_allowlist" in source
    assert "se-api-allowlist-status" in source
    assert "se-api-allowlist-body" in source
    assert "ocPost(" not in source
    assert "method: 'POST'" not in source
    assert "method: \"POST\"" not in source
    assert "stock_etf.submit_paper_order" not in source
    assert "stock_etf.cancel_paper_order" not in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source
