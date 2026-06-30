"""Stock/ETF paper-status route tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from stock_etf_route_fixtures import (
    _make_client_with_ipc,
    _valid_paper_status,
    route_module,
    stock_etf_router,
    client_fail_closed,
)

def test_stock_etf_paper_status_returns_200_when_ipc_down(
    client_fail_closed: TestClient,
) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf/paper-status")
    assert resp.status_code == 200
    assert "no-store" in resp.headers["cache-control"]
    assert "private" in resp.headers["cache-control"]
    assert resp.headers["pragma"] == "no-cache"
    assert resp.headers["expires"] == "0"
    assert resp.headers["vary"] == "Authorization"
    body = resp.json()
    data = body["data"]
    assert body["ok"] is True
    assert body["data_category"] == "stock_etf_paper_status"
    assert data["degraded"] is True
    assert data["reason"] == "ipc_unavailable"
    assert data["paper_status_state"] == "degraded"
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["environment"] == "paper"
    assert data["gui_authority"] == "display_only"
    assert data["phase2_started"] is False
    assert data["first_ibkr_contact_allowed"] is False
    assert data["connector_enabled"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    assert data["paper_lifecycle_started"] is False
    assert data["paper_order_submitted"] is False
    assert data["paper_fill_imported"] is False
    assert data["paper_reconciliation_started"] is False
    assert data["paper_account_snapshot_present"] is False
    assert data["broker_paper_attestation_present"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False
    assert data["db_apply_performed"] is False
    assert data["lifecycle_event"]["blockers"] == ["ipc_unavailable"]
    assert data["reconstructability"]["append_only_event_ready"] is False


def test_stock_etf_paper_status_uses_only_readonly_fixture_method() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_paper_status"
        assert params == {}
        return _valid_paper_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/paper-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["degraded"] is False
    assert data["paper_status_state"] == "blocked"
    assert data["phase"] == "phase2_paper_status_source_fixture"
    assert data["phase2_started"] is False
    assert data["lifecycle_event"]["expected_lifecycle_contract_id"] == (
        "ibkr_paper_order_lifecycle_v1"
    )
    assert data["lifecycle_event"]["expected_event_log_contract_id"] == (
        "broker_lifecycle_event_log_v1"
    )
    assert data["lifecycle_event"]["accepted"] is False
    assert data["lifecycle_event"]["operation"] == "paper_order_submit"
    assert data["lifecycle_event"]["broker_order_id_present"] is False
    assert data["lifecycle_event"]["execution_id_present"] is False
    assert data["lifecycle_event"]["commission_report_id_present"] is False
    assert data["reconstructability"]["append_only_event_ready"] is False
    assert data["reconstructability"]["raw_artifact_hash_present"] is False
    assert data["allowed_gui_actions"] == ["refresh_paper_status"]
    assert data["api_allowlist"]["contract_id"] == "non_bybit_api_allowlist_v1"
    assert data["paper_order_submitted"] is False
    assert data["paper_fill_imported"] is False
    assert data["db_apply_performed"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_paper_status_does_not_trust_client_state() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_paper_status"
        assert params == {}
        return _valid_paper_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        resp = client.get(
            "/api/v1/stock-etf/paper-status",
            params={
                "phase2_started": "true",
                "paper_order_submitted": "true",
                "first_ibkr_contact_allowed": "true",
            },
            headers={
                "X-Ibkr-Phase2-Started": "true",
                "X-Paper-Order-Submitted": "true",
            },
        )
        data = resp.json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert "no-store" in resp.headers["cache-control"]
    assert data["phase2_started"] is False
    assert data["first_ibkr_contact_allowed"] is False
    assert data["paper_lifecycle_started"] is False
    assert data["paper_order_submitted"] is False
    assert data["paper_fill_imported"] is False
    assert data["paper_reconciliation_started"] is False
    assert data["paper_account_snapshot_present"] is False
    assert data["broker_paper_attestation_present"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_paper_status_blocks_contract_violation() -> None:
    payload = _valid_paper_status()
    payload["phase2_started"] = True
    payload["asset_lane"] = "crypto_perp"
    payload["broker"] = "bybit"
    payload["environment"] = "live"
    payload["paper_lifecycle_started"] = True
    payload["paper_order_submitted"] = True
    payload["paper_fill_imported"] = True
    payload["paper_reconciliation_started"] = True
    payload["paper_account_snapshot_present"] = True
    payload["broker_paper_attestation_present"] = True
    payload["ibkr_call_performed"] = True
    payload["secret_slot_touched"] = True
    payload["order_routed"] = True
    payload["bybit_ipc_reused"] = True
    payload["db_apply_performed"] = True
    payload["lifecycle_event"]["expected_lifecycle_contract_id"] = "wrong"
    payload["lifecycle_event"]["expected_event_log_contract_id"] = "wrong"
    payload["lifecycle_event"]["accepted"] = True
    payload["lifecycle_event"]["allowed"] = True
    payload["lifecycle_event"]["event_id_present"] = True
    payload["lifecycle_event"]["order_local_id_present"] = True
    payload["lifecycle_event"]["idempotency_key_present"] = True
    payload["lifecycle_event"]["broker_order_id_present"] = True
    payload["lifecycle_event"]["execution_id_present"] = True
    payload["lifecycle_event"]["commission_report_id_present"] = True
    payload["lifecycle_event"]["reconciliation_run_id_present"] = True
    payload["lifecycle_event"]["raw_artifact_hash_present"] = True
    payload["lifecycle_event"]["redacted_summary_hash_present"] = True
    payload["reconstructability"]["append_only_event_ready"] = True
    payload["reconstructability"]["restart_recovery_required"] = True
    payload["reconstructability"]["manual_review_required"] = True
    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(return_value=payload)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/paper-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["paper_status_state"] == "contract_violation_blocked"
    assert data["degraded"] is True
    assert {
        "ibkr_call_performed",
        "secret_slot_touched",
        "order_routed",
        "bybit_ipc_reused",
        "db_apply_performed",
        "asset_lane_mismatch",
        "broker_mismatch",
        "environment_mismatch",
        "phase2_started",
        "paper_lifecycle_started",
        "paper_order_submitted",
        "paper_fill_imported",
        "paper_reconciliation_started",
        "paper_account_snapshot_present",
        "broker_paper_attestation_present",
        "paper_lifecycle_expected_contract_id_mismatch",
        "paper_event_log_expected_contract_id_mismatch",
        "paper_lifecycle_event_accepted_before_gate",
        "paper_lifecycle_event_allowed_before_gate",
        "paper_lifecycle_broker_order_id_present",
        "paper_lifecycle_execution_id_present",
        "paper_lifecycle_commission_report_id_present",
        "paper_reconstructability_append_only_event_ready",
        "paper_reconstructability_restart_recovery_required",
        "paper_reconstructability_manual_review_required",
    }.issubset(set(data["contract_violations"]))
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["environment"] == "paper"
    assert data["phase2_started"] is False
    assert data["paper_lifecycle_started"] is False
    assert data["paper_order_submitted"] is False
    assert data["paper_fill_imported"] is False
    assert data["paper_reconciliation_started"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False
    assert data["db_apply_performed"] is False


def test_stock_etf_paper_status_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf/paper-status")

    assert resp.status_code == 401
