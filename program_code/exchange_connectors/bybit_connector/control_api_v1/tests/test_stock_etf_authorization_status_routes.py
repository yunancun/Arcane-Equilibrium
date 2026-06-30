"""Stock/ETF authorization status route tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from stock_etf_route_fixtures import (
    _make_client_with_ipc,
    _valid_authorization_status,
    client_fail_closed,
    route_module,
    stock_etf_router,
)


def test_stock_etf_authorization_status_returns_200_when_ipc_down(
    client_fail_closed: TestClient,
) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf/authorization-status")
    assert resp.status_code == 200
    assert "no-store" in resp.headers["cache-control"]
    assert resp.headers["vary"] == "Authorization"
    body = resp.json()
    data = body["data"]
    assert body["ok"] is True
    assert body["data_category"] == "stock_etf_authorization_status"
    assert data["degraded"] is True
    assert data["reason"] == "ipc_unavailable"
    assert data["authorization_status_state"] == "degraded"
    assert data["gui_authority"] == "display_only"
    assert data["phase2_started"] is False
    assert data["paper_order_authority_present"] is False
    assert data["scoped_authorization_present"] is False
    assert data["decision_lease_valid"] is False
    assert data["guardian_allows"] is False
    assert data["paper_order_submitted"] is False
    assert data["connector_runtime_started"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False
    assert data["authorization_matrix"]["blockers"] == ["ipc_unavailable"]
    assert data["secret_slot_contract"]["blockers"] == ["ipc_unavailable"]
    assert data["phase2_gate_artifact"]["blockers"] == ["ipc_unavailable"]
    assert data["session_attestation"]["blockers"] == ["ipc_unavailable"]


def test_stock_etf_authorization_status_uses_only_readonly_fixture_method() -> None:
    async def _fake_call(
        method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        assert method == "stock_etf.get_authorization_status"
        assert params == {}
        return _valid_authorization_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/authorization-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    matrix = data["authorization_matrix"]
    secret = data["secret_slot_contract"]
    assert data["degraded"] is False
    assert data["authorization_status_state"] == "blocked"
    assert data["phase"] == "phase2_authorization_status_source_fixture"
    assert data["paper_order_authority_present"] is False
    assert data["scoped_authorization_present"] is False
    assert data["decision_lease_valid"] is False
    assert data["guardian_allows"] is False
    assert matrix["expected_contract_id"] == "feature_flag_secret_auth_matrix_v1"
    assert matrix["request_allowed"] is False
    assert matrix["effective_authority_scope"] == "denied"
    assert matrix["gui_lane_state_override_denied"] is True
    assert matrix["server_rust_matrix_authoritative"] is True
    assert secret["expected_contract_id"] == "ibkr_secret_slot_contract_v1"
    assert secret["accepted"] is False
    assert data["phase2_gate_artifact"]["ibkr_contact_allowed"] is False
    assert data["session_attestation"]["attestation_accepted"] is False
    assert data["authorization_envelope"]["permission_scope"] == "denied"
    assert data["allowed_gui_actions"] == ["refresh_authorization_status"]
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_authorization_status_does_not_trust_client_state() -> None:
    async def _fake_call(
        method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        assert method == "stock_etf.get_authorization_status"
        assert params == {}
        return _valid_authorization_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        resp = client.get(
            "/api/v1/stock-etf/authorization-status",
            params={
                "paper_order_authority_present": "true",
                "decision_lease_valid": "true",
                "guardian_allows": "true",
                "paper_order_submitted": "true",
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
    assert data["paper_order_authority_present"] is False
    assert data["scoped_authorization_present"] is False
    assert data["decision_lease_valid"] is False
    assert data["guardian_allows"] is False
    assert data["paper_order_submitted"] is False
    assert data["ibkr_live_enabled"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_authorization_status_blocks_contract_violation() -> None:
    payload = _valid_authorization_status()
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
    payload["paper_order_authority_present"] = True
    payload["scoped_authorization_present"] = True
    payload["decision_lease_valid"] = True
    payload["guardian_allows"] = True
    payload["ibkr_call_performed"] = True
    payload["secret_slot_touched"] = True
    payload["order_routed"] = True
    payload["bybit_ipc_reused"] = True

    matrix = payload["authorization_matrix"]
    matrix["expected_contract_id"] = "wrong"
    matrix["request_allowed"] = True
    matrix["effective_authority_scope"] = "paper_rehearsal"
    matrix["gui_lane_state_override_denied"] = False
    matrix["server_rust_matrix_authoritative"] = False

    secret = payload["secret_slot_contract"]
    secret["expected_contract_id"] = "wrong"
    secret["secret_content_serialized"] = True
    secret["account_id_serialized"] = True

    artifact = payload["phase2_gate_artifact"]
    artifact["expected_contract_id"] = "wrong"
    artifact["ibkr_contact_allowed"] = True

    session = payload["session_attestation"]
    session["expected_contract_id"] = "wrong"
    session["attestation_accepted"] = True
    session["account_fingerprint_is_live"] = True

    envelope = payload["authorization_envelope"]
    envelope["permission_scope"] = "paper_rehearsal"
    envelope["expires_at_ms"] = 1

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(return_value=payload)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/authorization-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["authorization_status_state"] == "contract_violation_blocked"
    assert data["degraded"] is True
    assert {
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
        "paper_order_authority_present",
        "scoped_authorization_present",
        "decision_lease_valid",
        "guardian_allows",
        "asset_lane_mismatch",
        "broker_mismatch",
        "environment_mismatch",
        "matrix_expected_contract_id_mismatch",
        "authorization_request_allowed",
        "authorization_scope_not_denied",
        "gui_lane_state_override_not_denied",
        "server_rust_matrix_not_authoritative",
        "secret_expected_contract_id_mismatch",
        "secret_content_serialized",
        "secret_account_id_serialized",
        "phase2_artifact_expected_contract_id_mismatch",
        "phase2_artifact_contact_allowed",
        "session_expected_contract_id_mismatch",
        "session_attestation_accepted",
        "session_live_account_fingerprint",
        "authorization_envelope_scope_not_denied",
        "authorization_envelope_expiry_claimed",
    }.issubset(set(data["contract_violations"]))
    assert data["paper_order_authority_present"] is False
    assert data["scoped_authorization_present"] is False
    assert data["decision_lease_valid"] is False
    assert data["guardian_allows"] is False
    assert data["paper_order_submitted"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False


def test_stock_etf_authorization_status_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf/authorization-status")

    assert resp.status_code == 401
