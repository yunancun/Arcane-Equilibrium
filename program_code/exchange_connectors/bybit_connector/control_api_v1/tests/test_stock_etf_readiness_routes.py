"""Stock/ETF readiness route tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from stock_etf_route_fixtures import (
    _make_client_with_ipc,
    _valid_api_allowlist,
    client_fail_closed,
)

def _valid_readonly_probe_request() -> dict[str, Any]:
    return {
        "contract_id": "stock_etf_ibkr_readonly_probe_request_v1",
        "source_version": 1,
        "request_artifact_present": False,
        "request_validated": False,
        "accepted_for_contact": False,
        "status": "blocked_no_request_artifact",
        "blockers": ["phase2_gate_not_accepted", "probe_request_artifact_missing"],
        "ibkr_contact_performed": False,
        "connector_runtime_started": False,
        "secret_content_serialized": False,
        "order_routed": False,
        "paper_order_submitted": False,
        "db_apply_performed": False,
        "evidence_clock_started": False,
        "bybit_path_reused": False,
        "live_or_tiny_live_authorized": False,
    }


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
    assert data["readonly_probe_request"]["contract_id"] == (
        "stock_etf_ibkr_readonly_probe_request_v1"
    )
    assert data["readonly_probe_request"]["status"] == "blocked_no_request_artifact"
    assert data["readonly_probe_request"]["accepted_for_contact"] is False
    assert data["readonly_probe_request"]["ibkr_contact_performed"] is False
    assert data["connector_skeleton"]["surface_id"] == (
        "ibkr_stock_etf_readonly_connector_skeleton_v1"
    )
    assert data["connector_skeleton"]["accepted"] is False
    assert data["connector_skeleton"]["network_contact_performed"] is False
    assert data["connector_skeleton"]["secret_content_loaded"] is False
    assert data["connector_skeleton"]["order_write_method_present"] is False
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
                "readonly_probe_request": _valid_readonly_probe_request(),
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
            "connector_skeleton": {
                "surface_id": "ibkr_stock_etf_readonly_connector_skeleton_v1",
                "accepted": False,
                "status": "blocked_source_only",
                "blockers": ["phase2_gate_not_accepted"],
                "network_contact_performed": False,
                "secret_content_loaded": False,
                "paper_channel_exposed": False,
                "live_channel_exposed": False,
                "order_write_method_present": False,
                "bybit_path_reused": False,
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
    assert data["readonly_probe_request"]["contract_id"] == (
        "stock_etf_ibkr_readonly_probe_request_v1"
    )
    assert data["readonly_probe_request"]["source_version"] == 1
    assert data["readonly_probe_request"]["status"] == "blocked_no_request_artifact"
    assert data["readonly_probe_request"]["request_artifact_present"] is False
    assert data["readonly_probe_request"]["request_validated"] is False
    assert data["readonly_probe_request"]["accepted_for_contact"] is False
    assert data["connector_skeleton"]["status"] == "blocked_source_only"
    assert data["connector_skeleton"]["accepted"] is False
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
                "readonly_probe_request": {
                    **_valid_readonly_probe_request(),
                    "contract_id": "wrong",
                    "source_version": 2,
                    "request_artifact_present": True,
                    "request_validated": True,
                    "accepted_for_contact": True,
                    "status": "ready",
                    "ibkr_contact_performed": True,
                    "connector_runtime_started": True,
                    "secret_content_serialized": True,
                    "order_routed": True,
                    "paper_order_submitted": True,
                    "db_apply_performed": True,
                    "evidence_clock_started": True,
                    "bybit_path_reused": True,
                    "live_or_tiny_live_authorized": True,
                },
                "immutable_pass_artifact_present": True,
                "first_ibkr_contact_allowed": True,
                "connector_enabled": True,
            },
            "connector_skeleton": {
                "surface_id": "ibkr_stock_etf_readonly_connector_skeleton_v1",
                "accepted": True,
                "status": "ready",
                "blockers": [],
                "network_contact_performed": True,
                "secret_content_loaded": True,
                "paper_channel_exposed": True,
                "live_channel_exposed": True,
                "order_write_method_present": True,
                "bybit_path_reused": True,
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
        "readonly_probe_request_contract_id_mismatch",
        "readonly_probe_request_source_version_mismatch",
        "readonly_probe_request_status_not_blocked",
        "readonly_probe_request_request_artifact_present",
        "readonly_probe_request_request_validated",
        "readonly_probe_request_accepted_for_contact",
        "readonly_probe_request_ibkr_contact_performed",
        "readonly_probe_request_connector_runtime_started",
        "readonly_probe_request_secret_content_serialized",
        "readonly_probe_request_order_routed",
        "readonly_probe_request_paper_order_submitted",
        "readonly_probe_request_db_apply_performed",
        "readonly_probe_request_evidence_clock_started",
        "readonly_probe_request_bybit_path_reused",
        "readonly_probe_request_live_or_tiny_live_authorized",
        "connector_skeleton_accepted",
        "connector_skeleton_status_not_blocked",
        "connector_skeleton_network_contact_performed",
        "connector_skeleton_secret_content_loaded",
        "connector_skeleton_paper_channel_exposed",
        "connector_skeleton_live_channel_exposed",
        "connector_skeleton_order_write_method_present",
        "connector_skeleton_bybit_path_reused",
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
