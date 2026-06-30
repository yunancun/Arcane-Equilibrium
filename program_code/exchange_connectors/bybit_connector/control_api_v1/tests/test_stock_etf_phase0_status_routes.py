"""Stock/ETF Phase 0 status route tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from stock_etf_route_fixtures import (
    _make_client_with_ipc,
    _valid_phase0_status,
    client_fail_closed,
)


def test_phase0_status_ipc_down_is_degraded(
    client_fail_closed: TestClient,
) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf/phase0-status")

    assert resp.status_code == 200
    assert "no-store" in resp.headers["cache-control"]
    data = resp.json()["data"]
    assert data["phase0_status_state"] == "degraded"
    assert data["phase0_accepted"] is False
    assert data["reason"] == "ipc_unavailable"
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False


def test_phase0_status_uses_only_phase0_ipc_method_with_empty_params() -> None:
    fake_ipc = AsyncMock()
    fake_ipc.call.return_value = _valid_phase0_status()
    client = _make_client_with_ipc(fake_ipc)
    try:
        resp = client.get("/api/v1/stock-etf/phase0-status")
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert resp.status_code == 200
    fake_ipc.call.assert_awaited_once_with("stock_etf.get_phase0_status", params={})
    data = resp.json()["data"]
    assert data["phase0_status_state"] == "accepted_no_runtime_authority"
    assert data["phase0_accepted"] is True
    assert data["contract_count"] == 32
    assert "stock_etf_shadow_signal_request_v1" in data["contracts"]
    assert "stock_etf_paper_shadow_reconciliation_v1" in data["contracts"]
    assert data["manifest"]["schema"] == "stock_etf_phase0_contract_packet_manifest_v1"
    assert data["api_baseline"]["live_ports_denied"] is True
    assert data["global_denials"]["ibkr_live"] is True
    assert data["paper_shadow_launch_authorized"] is False


def test_phase0_status_does_not_trust_client_state() -> None:
    fake_ipc = AsyncMock()
    fake_ipc.call.return_value = _valid_phase0_status()
    client = _make_client_with_ipc(fake_ipc)
    try:
        resp = client.get(
            "/api/v1/stock-etf/phase0-status",
            params={
                "phase5_started": "true",
                "paper_shadow_launch_authorized": "true",
            },
            headers={"X-Phase0-Accepted": "false"},
        )
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert resp.status_code == 200
    fake_ipc.call.assert_awaited_once_with("stock_etf.get_phase0_status", params={})
    data = resp.json()["data"]
    assert data["phase0_accepted"] is True
    assert data["phase5_started"] is False
    assert data["paper_shadow_launch_authorized"] is False
    assert data["contract_violations"] == []


def test_phase0_status_blocks_runtime_or_contract_drift() -> None:
    payload = _valid_phase0_status()
    payload["phase5_started"] = True
    payload["paper_shadow_launch_authorized"] = True
    payload["manifest"]["status"] = "RUNTIME_LAUNCHED"
    payload["api_baseline"]["ibkr_call_performed"] = True
    payload["global_denials"]["ibkr_live"] = False
    fake_ipc = AsyncMock()
    fake_ipc.call.return_value = payload
    client = _make_client_with_ipc(fake_ipc)
    try:
        resp = client.get("/api/v1/stock-etf/phase0-status")
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["phase0_status_state"] == "contract_violation_blocked"
    assert data["phase0_accepted"] is False
    assert "phase5_started" in data["contract_violations"]
    assert "paper_shadow_launch_authorized" in data["contract_violations"]
    assert "phase0_status_mismatch" in data["contract_violations"]
    assert "phase0_ibkr_call_performed" in data["contract_violations"]
    assert "phase0_global_denial_missing:ibkr_live" in data["contract_violations"]
