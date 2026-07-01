"""Stock/ETF reconciliation-status route tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from stock_etf_route_fixtures import (
    _make_client_with_ipc,
    _valid_reconciliation_status,
    client_fail_closed,
    route_module,
    stock_etf_router,
)

EXPECTED_RECONCILIATION_CONTRACT_VIOLATIONS = [
    "ibkr_call_performed",
    "secret_slot_touched",
    "order_routed",
    "bybit_ipc_reused",
    "asset_lane_mismatch",
    "broker_mismatch",
    "environment_mismatch",
    "phase3_started",
    "paper_shadow_reconciliation_started",
    "paper_orders_ready",
    "paper_fills_ready",
    "shadow_fills_ready",
    "scorecard_writer_started",
    "db_apply_performed",
    "reconciliation_lifecycle_expected_contract_id_mismatch",
    "reconciliation_event_log_expected_contract_id_mismatch",
    "reconciliation_shadow_expected_contract_id_mismatch",
    "reconciliation_expected_contract_id_mismatch",
    "reconciliation_reconciliation_accepted",
    "reconciliation_lifecycle_event_accepted",
    "reconciliation_shadow_fill_model_accepted",
    "reconciliation_append_only_event_ready",
    "reconciliation_paper_order_id_present",
    "reconciliation_broker_order_id_present",
    "reconciliation_execution_id_present",
    "reconciliation_commission_report_id_present",
    "reconciliation_shadow_signal_id_present",
    "reconciliation_shadow_fill_price_present",
    "reconciliation_paper_shadow_link_present",
    "reconciliation_divergence_within_threshold",
    "reconciliation_reconciliation_run_id_present",
    "reconciliation_contract_reconciliation_run_id_present",
    "reconciliation_paper_shadow_link_hash_present",
    "reconciliation_paper_fill_imported",
    "reconciliation_shadow_fill_synthetic",
    "reconciliation_raw_artifact_hash_present",
    "reconciliation_redacted_summary_hash_present",
    "reconciliation_reconciliation_writer_started",
    "reconciliation_ibkr_contact_performed",
    "reconciliation_connector_runtime_started",
    "reconciliation_secret_content_serialized",
    "reconciliation_fill_import_performed",
    "reconciliation_shadow_fill_generated",
    "reconciliation_divergence_bps_present",
    "reconciliation_divergence_threshold_bps_present",
    "reconciliation_unmatched_paper_fill_count_present",
    "reconciliation_unmatched_shadow_fill_count_present",
]


def test_stock_etf_reconciliation_status_returns_200_when_ipc_down(
    client_fail_closed: TestClient,
) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf/reconciliation-status")
    assert resp.status_code == 200
    assert "no-store" in resp.headers["cache-control"]
    assert "private" in resp.headers["cache-control"]
    assert resp.headers["pragma"] == "no-cache"
    assert resp.headers["expires"] == "0"
    assert resp.headers["vary"] == "Authorization"
    body = resp.json()
    data = body["data"]
    assert body["ok"] is True
    assert body["data_category"] == "stock_etf_reconciliation_status"
    assert data["degraded"] is True
    assert data["reason"] == "ipc_unavailable"
    assert data["reconciliation_status_state"] == "degraded"
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["environment"] == "paper_shadow"
    assert data["gui_authority"] == "display_only"
    assert data["phase3_started"] is False
    assert data["first_ibkr_contact_allowed"] is False
    assert data["connector_enabled"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    assert data["paper_shadow_reconciliation_started"] is False
    assert data["paper_orders_ready"] is False
    assert data["paper_fills_ready"] is False
    assert data["shadow_fills_ready"] is False
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False
    assert data["matching"]["lifecycle_blockers"] == ["ipc_unavailable"]
    assert data["matching"]["shadow_blockers"] == ["ipc_unavailable"]


def test_stock_etf_reconciliation_status_uses_only_readonly_fixture_method() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_reconciliation_status"
        assert params == {}
        return _valid_reconciliation_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/reconciliation-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["degraded"] is False
    assert data["reconciliation_status_state"] == "blocked"
    assert data["phase"] == "phase3_reconciliation_status_source_fixture"
    assert data["phase3_started"] is False
    assert data["matching"]["expected_lifecycle_contract_id"] == (
        "ibkr_paper_order_lifecycle_v1"
    )
    assert data["matching"]["expected_event_log_contract_id"] == (
        "broker_lifecycle_event_log_v1"
    )
    assert data["matching"]["expected_shadow_contract_id"] == (
        "stock_shadow_fill_model_v1"
    )
    assert data["matching"]["expected_reconciliation_contract_id"] == (
        "stock_etf_paper_shadow_reconciliation_v1"
    )
    assert data["matching"]["reconciliation_accepted"] is False
    assert data["matching"]["lifecycle_event_accepted"] is False
    assert data["matching"]["shadow_fill_model_accepted"] is False
    assert data["matching"]["paper_shadow_link_present"] is False
    assert data["matching"]["paper_shadow_link_hash_present"] is False
    assert data["matching"]["paper_fill_imported"] is False
    assert data["matching"]["shadow_fill_synthetic"] is False
    assert data["matching"]["divergence_bps"] == 0
    assert data["matching"]["unmatched_paper_fill_count"] == 0
    assert data["matching"]["reconciliation_writer_started"] is False
    assert data["matching"]["ibkr_contact_performed"] is False
    assert data["matching"]["connector_runtime_started"] is False
    assert data["matching"]["secret_content_serialized"] is False
    assert data["matching"]["fill_import_performed"] is False
    assert data["matching"]["shadow_fill_generated"] is False
    assert data["allowed_gui_actions"] == ["refresh_reconciliation_status"]
    assert data["api_allowlist"]["contract_id"] == "non_bybit_api_allowlist_v1"
    assert data["paper_shadow_reconciliation_started"] is False
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_reconciliation_status_does_not_trust_client_state() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_reconciliation_status"
        assert params == {}
        return _valid_reconciliation_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        resp = client.get(
            "/api/v1/stock-etf/reconciliation-status",
            params={
                "phase3_started": "true",
                "paper_shadow_reconciliation_started": "true",
                "first_ibkr_contact_allowed": "true",
            },
            headers={
                "X-Ibkr-Phase3-Started": "true",
                "X-Reconciliation-Started": "true",
            },
        )
        data = resp.json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert "no-store" in resp.headers["cache-control"]
    assert data["phase3_started"] is False
    assert data["first_ibkr_contact_allowed"] is False
    assert data["paper_shadow_reconciliation_started"] is False
    assert data["paper_orders_ready"] is False
    assert data["paper_fills_ready"] is False
    assert data["shadow_fills_ready"] is False
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_reconciliation_status_blocks_contract_violation() -> None:
    payload = _valid_reconciliation_status()
    payload["phase3_started"] = True
    payload["asset_lane"] = "crypto_perp"
    payload["broker"] = "bybit"
    payload["environment"] = "paper"
    payload["paper_shadow_reconciliation_started"] = True
    payload["paper_orders_ready"] = True
    payload["paper_fills_ready"] = True
    payload["shadow_fills_ready"] = True
    payload["scorecard_writer_started"] = True
    payload["db_apply_performed"] = True
    payload["ibkr_call_performed"] = True
    payload["secret_slot_touched"] = True
    payload["order_routed"] = True
    payload["bybit_ipc_reused"] = True
    payload["matching"]["expected_lifecycle_contract_id"] = "wrong"
    payload["matching"]["expected_event_log_contract_id"] = "wrong"
    payload["matching"]["expected_shadow_contract_id"] = "wrong"
    payload["matching"]["expected_reconciliation_contract_id"] = "wrong"
    payload["matching"]["reconciliation_accepted"] = True
    payload["matching"]["lifecycle_event_accepted"] = True
    payload["matching"]["shadow_fill_model_accepted"] = True
    payload["matching"]["append_only_event_ready"] = True
    payload["matching"]["paper_order_id_present"] = True
    payload["matching"]["broker_order_id_present"] = True
    payload["matching"]["execution_id_present"] = True
    payload["matching"]["commission_report_id_present"] = True
    payload["matching"]["shadow_signal_id_present"] = True
    payload["matching"]["shadow_fill_price_present"] = True
    payload["matching"]["paper_shadow_link_present"] = True
    payload["matching"]["divergence_bps"] = 12
    payload["matching"]["divergence_threshold_bps"] = 10
    payload["matching"]["divergence_within_threshold"] = True
    payload["matching"]["unmatched_paper_fill_count"] = 1
    payload["matching"]["unmatched_shadow_fill_count"] = 2
    payload["matching"]["reconciliation_run_id_present"] = True
    payload["matching"]["contract_reconciliation_run_id_present"] = True
    payload["matching"]["paper_shadow_link_hash_present"] = True
    payload["matching"]["paper_fill_imported"] = True
    payload["matching"]["shadow_fill_synthetic"] = True
    payload["matching"]["raw_artifact_hash_present"] = True
    payload["matching"]["redacted_summary_hash_present"] = True
    payload["matching"]["reconciliation_writer_started"] = True
    payload["matching"]["ibkr_contact_performed"] = True
    payload["matching"]["connector_runtime_started"] = True
    payload["matching"]["secret_content_serialized"] = True
    payload["matching"]["fill_import_performed"] = True
    payload["matching"]["shadow_fill_generated"] = True
    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(return_value=payload)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/reconciliation-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["reconciliation_status_state"] == "contract_violation_blocked"
    assert data["degraded"] is True
    assert (
        data["contract_violations"]
        == EXPECTED_RECONCILIATION_CONTRACT_VIOLATIONS
    )
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["environment"] == "paper_shadow"
    assert data["phase3_started"] is False
    assert data["paper_shadow_reconciliation_started"] is False
    assert data["paper_orders_ready"] is False
    assert data["paper_fills_ready"] is False
    assert data["shadow_fills_ready"] is False
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False


def test_stock_etf_reconciliation_status_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf/reconciliation-status")

    assert resp.status_code == 401


def test_stock_etf_reconciliation_contract_violation_assertions_stay_exact() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    source_under_test = source.split(
        "def test_stock_etf_reconciliation_contract_violation_assertions_stay_exact",
        1,
    )[0]
    forbidden_patterns = [
        'set(data["contract_violations"])',
        'in data["contract_violations"]',
        'issubset(set(data["contract_violations"]))',
    ]

    for pattern in forbidden_patterns:
        assert pattern not in source_under_test
