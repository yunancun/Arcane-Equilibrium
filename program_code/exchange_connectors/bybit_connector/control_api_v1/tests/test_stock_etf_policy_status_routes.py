"""Stock/ETF policy/capability status route tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from stock_etf_route_fixtures import (
    _make_client_with_ipc,
    _valid_policy_status,
    client_fail_closed,
    route_module,
    stock_etf_router,
)

EXPECTED_POLICY_CONTRACT_VIOLATIONS = [
    "ibkr_call_performed",
    "secret_slot_touched",
    "order_routed",
    "bybit_ipc_reused",
    "phase2_started",
    "phase3_started",
    "risk_runtime_started",
    "paper_order_rehearsal_started",
    "paper_order_submitted",
    "connector_runtime_started",
    "db_apply_performed",
    "evidence_clock_started",
    "scorecard_writer_started",
    "asset_lane_mismatch",
    "broker_mismatch",
    "environment_mismatch",
    "risk_expected_contract_id_mismatch",
    "registry_expected_id_mismatch",
    "registry_read_rows_missing_lane_scoped_ipc",
    "registry_read_rows_missing_readonly_probe_request",
    "registry_scorecard_missing_readonly_probe_result_import_request",
    "risk_policy_runtime_enabled",
    "risk_policy_allow_margin",
    "risk_policy_allow_short",
    "risk_policy_allow_options",
    "risk_policy_allow_cfd",
    "risk_policy_allow_transfer",
    "risk_policy_allow_live",
    "risk_policy_ibkr_contact_performed",
    "risk_policy_connector_runtime_started",
    "risk_policy_secret_content_serialized",
    "risk_policy_bybit_live_not_protected",
    "risk_policy_accepted_without_source_proofs",
    "registry_first_ibkr_contact_performed",
    "registry_secret_content_serialized",
    "registry_bybit_live_not_protected",
    "registry_python_broker_write_not_denied",
    "registry_ibkr_live_not_denied",
    "registry_cfd_margin_not_denied",
    "registry_accepted_without_source_proofs",
]


def test_stock_etf_policy_status_returns_200_when_ipc_down(
    client_fail_closed: TestClient,
) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf/policy-status")
    assert resp.status_code == 200
    assert "no-store" in resp.headers["cache-control"]
    assert "private" in resp.headers["cache-control"]
    assert resp.headers["pragma"] == "no-cache"
    assert resp.headers["expires"] == "0"
    assert resp.headers["vary"] == "Authorization"
    body = resp.json()
    data = body["data"]
    assert body["ok"] is True
    assert body["data_category"] == "stock_etf_policy_status"
    assert data["degraded"] is True
    assert data["reason"] == "ipc_unavailable"
    assert data["policy_status_state"] == "degraded"
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["environment"] == "paper"
    assert data["gui_authority"] == "display_only"
    assert data["phase2_started"] is False
    assert data["phase3_started"] is False
    assert data["risk_runtime_started"] is False
    assert data["paper_order_rehearsal_started"] is False
    assert data["paper_order_submitted"] is False
    assert data["connector_runtime_started"] is False
    assert data["db_apply_performed"] is False
    assert data["evidence_clock_started"] is False
    assert data["scorecard_writer_started"] is False
    assert data["first_ibkr_contact_allowed"] is False
    assert data["connector_enabled"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False
    assert data["risk_policy"]["blockers"] == ["ipc_unavailable"]
    assert data["broker_capability_registry"]["blockers"] == ["ipc_unavailable"]


def test_stock_etf_policy_status_uses_only_readonly_fixture_method() -> None:
    async def _fake_call(
        method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        assert method == "stock_etf.get_policy_status"
        assert params == {}
        return _valid_policy_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/policy-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    risk = data["risk_policy"]
    registry = data["broker_capability_registry"]
    assert data["degraded"] is False
    assert data["policy_status_state"] == "blocked"
    assert data["phase"] == "phase2_policy_status_source_fixture"
    assert data["phase2_started"] is False
    assert data["phase3_started"] is False
    assert risk["expected_contract_id"] == "stock_etf_risk_policy_v1"
    assert risk["accepted"] is False
    assert risk["enabled"] is False
    assert risk["shadow_only"] is True
    assert risk["bybit_live_execution_unchanged"] is True
    assert registry["expected_registry_id"] == "broker_capability_registry_v1"
    assert registry["accepted"] is False
    assert registry["lane_scoped_ipc_contract_id"] == "lane_scoped_ipc_v1"
    assert (
        registry["readonly_probe_request_contract_id"]
        == "stock_etf_ibkr_readonly_probe_request_v1"
    )
    assert (
        registry["readonly_probe_result_import_request_contract_id"]
        == "stock_etf_ibkr_readonly_probe_result_import_request_v1"
    )
    assert registry["read_rows_require_lane_scoped_ipc"] is False
    assert registry["read_rows_require_readonly_probe_request"] is False
    assert registry["scorecard_requires_readonly_probe_result_import_request"] is False
    assert registry["python_broker_write_authority_denied"] is True
    assert registry["ibkr_live_denied"] is True
    assert registry["cfd_margin_reserved_denied"] is True
    assert data["allowed_gui_actions"] == ["refresh_policy_status"]
    assert data["api_allowlist"]["contract_id"] == "non_bybit_api_allowlist_v1"
    assert data["paper_order_rehearsal_started"] is False
    assert data["paper_order_submitted"] is False
    assert data["connector_runtime_started"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_policy_status_does_not_trust_client_state() -> None:
    async def _fake_call(
        method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        assert method == "stock_etf.get_policy_status"
        assert params == {}
        return _valid_policy_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        resp = client.get(
            "/api/v1/stock-etf/policy-status",
            params={
                "risk_runtime_started": "true",
                "paper_order_submitted": "true",
                "connector_runtime_started": "true",
            },
            headers={
                "X-Ibkr-Contact": "true",
                "X-Ibkr-Live": "true",
            },
        )
        data = resp.json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert "no-store" in resp.headers["cache-control"]
    assert data["phase2_started"] is False
    assert data["phase3_started"] is False
    assert data["first_ibkr_contact_allowed"] is False
    assert data["risk_runtime_started"] is False
    assert data["paper_order_rehearsal_started"] is False
    assert data["paper_order_submitted"] is False
    assert data["connector_runtime_started"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_policy_status_blocks_contract_violation() -> None:
    payload = _valid_policy_status()
    payload["asset_lane"] = "crypto_perp"
    payload["broker"] = "bybit"
    payload["environment"] = "shadow"
    payload["phase2_started"] = True
    payload["phase3_started"] = True
    payload["risk_runtime_started"] = True
    payload["paper_order_rehearsal_started"] = True
    payload["paper_order_submitted"] = True
    payload["connector_runtime_started"] = True
    payload["db_apply_performed"] = True
    payload["evidence_clock_started"] = True
    payload["scorecard_writer_started"] = True
    payload["ibkr_call_performed"] = True
    payload["secret_slot_touched"] = True
    payload["order_routed"] = True
    payload["bybit_ipc_reused"] = True

    risk = payload["risk_policy"]
    risk["expected_contract_id"] = "wrong"
    risk["accepted"] = True
    risk["enabled"] = True
    risk["allow_margin"] = True
    risk["allow_short"] = True
    risk["allow_options"] = True
    risk["allow_cfd"] = True
    risk["allow_transfer"] = True
    risk["allow_live"] = True
    risk["bybit_live_execution_unchanged"] = False
    risk["ibkr_contact_performed"] = True
    risk["connector_runtime_started"] = True
    risk["secret_content_serialized"] = True

    registry = payload["broker_capability_registry"]
    registry["expected_registry_id"] = "wrong"
    registry["accepted"] = True
    registry["bybit_live_execution_unchanged"] = False
    registry["python_broker_write_authority_denied"] = False
    registry["ibkr_live_denied"] = False
    registry["cfd_margin_reserved_denied"] = False
    registry["first_ibkr_contact_performed"] = True
    registry["secret_content_serialized"] = True

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(return_value=payload)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/policy-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["policy_status_state"] == "contract_violation_blocked"
    assert data["degraded"] is True
    assert data["contract_violations"] == EXPECTED_POLICY_CONTRACT_VIOLATIONS
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["environment"] == "paper"
    assert data["phase2_started"] is False
    assert data["phase3_started"] is False
    assert data["risk_runtime_started"] is False
    assert data["paper_order_rehearsal_started"] is False
    assert data["paper_order_submitted"] is False
    assert data["connector_runtime_started"] is False
    assert data["db_apply_performed"] is False
    assert data["evidence_clock_started"] is False
    assert data["scorecard_writer_started"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False


def test_stock_etf_policy_status_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf/policy-status")

    assert resp.status_code == 401


def test_stock_etf_policy_contract_violation_assertions_stay_exact() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    source_under_test = source.split(
        "def test_stock_etf_policy_contract_violation_assertions_stay_exact",
        1,
    )[0]
    forbidden_patterns = [
        'set(data["contract_violations"])',
        'in data["contract_violations"]',
        'issubset(set(data["contract_violations"]))',
    ]

    for pattern in forbidden_patterns:
        assert pattern not in source_under_test
