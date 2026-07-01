"""Stock/ETF data-foundation status route tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from stock_etf_route_fixtures import (
    _make_client_with_ipc,
    _valid_data_foundation_status,
    client_fail_closed,
    route_module,
    stock_etf_router,
)

EXPECTED_DATA_FOUNDATION_CONTRACT_VIOLATIONS = [
    "ibkr_call_performed",
    "secret_slot_touched",
    "order_routed",
    "bybit_ipc_reused",
    "phase2_started",
    "phase3_started",
    "contract_details_request_started",
    "reference_data_collection_started",
    "market_data_ingestion_started",
    "connector_runtime_started",
    "db_apply_performed",
    "evidence_clock_started",
    "scorecard_writer_started",
    "asset_lane_mismatch",
    "broker_mismatch",
    "environment_mismatch",
    "instrument_expected_contract_id_mismatch",
    "reference_expected_contract_id_mismatch",
    "instrument_ibkr_contact_performed",
    "instrument_secret_content_serialized",
    "instrument_bybit_live_not_protected",
    "instrument_ibkr_live_not_denied",
    "instrument_margin_short_not_denied",
    "instrument_options_cfd_not_denied",
    "instrument_accepted_without_source_proofs",
    "reference_ibkr_contact_performed",
    "reference_connector_runtime_started",
    "reference_secret_content_serialized",
    "reference_live_or_tiny_live_authorized",
    "reference_bybit_live_not_protected",
    "reference_accepted_without_source_proofs",
]


def test_stock_etf_data_foundation_status_returns_200_when_ipc_down(
    client_fail_closed: TestClient,
) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf/data-foundation-status")
    assert resp.status_code == 200
    assert "no-store" in resp.headers["cache-control"]
    assert "private" in resp.headers["cache-control"]
    assert resp.headers["pragma"] == "no-cache"
    assert resp.headers["expires"] == "0"
    assert resp.headers["vary"] == "Authorization"
    body = resp.json()
    data = body["data"]
    assert body["ok"] is True
    assert body["data_category"] == "stock_etf_data_foundation_status"
    assert data["degraded"] is True
    assert data["reason"] == "ipc_unavailable"
    assert data["data_foundation_status_state"] == "degraded"
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["environment"] == "paper"
    assert data["gui_authority"] == "display_only"
    assert data["phase2_started"] is False
    assert data["phase3_started"] is False
    assert data["first_ibkr_contact_allowed"] is False
    assert data["connector_enabled"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    assert data["contract_details_request_started"] is False
    assert data["reference_data_collection_started"] is False
    assert data["market_data_ingestion_started"] is False
    assert data["connector_runtime_started"] is False
    assert data["db_apply_performed"] is False
    assert data["evidence_clock_started"] is False
    assert data["scorecard_writer_started"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False
    assert data["instrument_identity"]["blockers"] == ["ipc_unavailable"]
    assert data["reference_data_sources"]["blockers"] == ["ipc_unavailable"]


def test_stock_etf_data_foundation_status_uses_only_readonly_fixture_method() -> None:
    async def _fake_call(
        method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        assert method == "stock_etf.get_data_foundation_status"
        assert params == {}
        return _valid_data_foundation_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/data-foundation-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["degraded"] is False
    assert data["data_foundation_status_state"] == "blocked"
    assert data["phase"] == "phase2_data_foundation_status_source_fixture"
    assert data["phase2_started"] is False
    assert data["phase3_started"] is False
    assert data["instrument_identity"]["expected_contract_id"] == "instrument_identity_contract_v1"
    assert data["instrument_identity"]["accepted"] is False
    assert data["instrument_identity"]["instrument_kind"] == "stock"
    assert data["instrument_identity"]["bybit_live_execution_unchanged"] is True
    assert data["instrument_identity"]["ibkr_live_denied"] is True
    assert (
        data["reference_data_sources"]["expected_contract_id"]
        == "stock_etf_reference_data_sources_v1"
    )
    assert data["reference_data_sources"]["accepted"] is False
    assert data["reference_data_sources"]["environment"] == "paper"
    assert data["reference_data_sources"]["live_or_tiny_live_authorized"] is False
    assert data["allowed_gui_actions"] == ["refresh_data_foundation_status"]
    assert data["api_allowlist"]["contract_id"] == "non_bybit_api_allowlist_v1"
    assert data["contract_details_request_started"] is False
    assert data["reference_data_collection_started"] is False
    assert data["market_data_ingestion_started"] is False
    assert data["connector_runtime_started"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_data_foundation_status_does_not_trust_client_state() -> None:
    async def _fake_call(
        method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        assert method == "stock_etf.get_data_foundation_status"
        assert params == {}
        return _valid_data_foundation_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        resp = client.get(
            "/api/v1/stock-etf/data-foundation-status",
            params={
                "phase2_started": "true",
                "phase3_started": "true",
                "contract_details_request_started": "true",
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
    assert data["contract_details_request_started"] is False
    assert data["reference_data_collection_started"] is False
    assert data["market_data_ingestion_started"] is False
    assert data["connector_runtime_started"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_data_foundation_status_blocks_contract_violation() -> None:
    payload = _valid_data_foundation_status()
    payload["asset_lane"] = "crypto_perp"
    payload["broker"] = "bybit"
    payload["environment"] = "shadow"
    payload["phase2_started"] = True
    payload["phase3_started"] = True
    payload["contract_details_request_started"] = True
    payload["reference_data_collection_started"] = True
    payload["market_data_ingestion_started"] = True
    payload["connector_runtime_started"] = True
    payload["db_apply_performed"] = True
    payload["evidence_clock_started"] = True
    payload["scorecard_writer_started"] = True
    payload["ibkr_call_performed"] = True
    payload["secret_slot_touched"] = True
    payload["order_routed"] = True
    payload["bybit_ipc_reused"] = True

    identity = payload["instrument_identity"]
    identity["expected_contract_id"] = "wrong"
    identity["accepted"] = True
    identity["bybit_live_execution_unchanged"] = False
    identity["ibkr_live_denied"] = False
    identity["margin_short_denied"] = False
    identity["options_cfd_denied"] = False
    identity["ibkr_contact_performed"] = True
    identity["secret_content_serialized"] = True

    reference = payload["reference_data_sources"]
    reference["expected_contract_id"] = "wrong"
    reference["accepted"] = True
    reference["bybit_live_execution_unchanged"] = False
    reference["ibkr_contact_performed"] = True
    reference["connector_runtime_started"] = True
    reference["secret_content_serialized"] = True
    reference["live_or_tiny_live_authorized"] = True

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(return_value=payload)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/data-foundation-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["data_foundation_status_state"] == "contract_violation_blocked"
    assert data["degraded"] is True
    assert (
        data["contract_violations"]
        == EXPECTED_DATA_FOUNDATION_CONTRACT_VIOLATIONS
    )
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["environment"] == "paper"
    assert data["phase2_started"] is False
    assert data["phase3_started"] is False
    assert data["contract_details_request_started"] is False
    assert data["reference_data_collection_started"] is False
    assert data["market_data_ingestion_started"] is False
    assert data["connector_runtime_started"] is False
    assert data["db_apply_performed"] is False
    assert data["evidence_clock_started"] is False
    assert data["scorecard_writer_started"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False


def test_stock_etf_data_foundation_status_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf/data-foundation-status")

    assert resp.status_code == 401


def test_stock_etf_data_foundation_contract_violation_assertions_stay_exact() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    source_under_test = source.split(
        "def test_stock_etf_data_foundation_contract_violation_assertions_stay_exact",
        1,
    )[0]
    forbidden_patterns = [
        'set(data["contract_violations"])',
        'in data["contract_violations"]',
        'issubset(set(data["contract_violations"]))',
    ]

    for pattern in forbidden_patterns:
        assert pattern not in source_under_test
