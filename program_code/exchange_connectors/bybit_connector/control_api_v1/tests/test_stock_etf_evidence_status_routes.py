"""Stock/ETF evidence-status route tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from stock_etf_route_fixtures import (
    _make_client_with_ipc,
    _valid_evidence_status,
    client_fail_closed,
)


EXPECTED_EVIDENCE_CONTRACT_VIOLATIONS = [
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
    "collector_run_ibkr_contact_performed",
    "collector_run_connector_runtime_started",
    "collector_run_market_data_ingestion_started",
    "collector_run_evidence_writer_started",
    "collector_run_scorecard_writer_started",
    "collector_run_db_apply_performed",
    "collector_run_secret_content_serialized",
    "collector_run_live_or_tiny_live_authorized",
    "dq_manifest_ibkr_contact_performed",
    "dq_manifest_connector_runtime_started",
    "dq_manifest_market_data_ingestion_started",
    "dq_manifest_writer_started",
    "dq_manifest_evidence_clock_started",
    "dq_manifest_scorecard_writer_started",
    "dq_manifest_db_apply_performed",
    "dq_manifest_secret_content_serialized",
    "dq_manifest_live_or_tiny_live_authorized",
    "evidence_clock_collector_run_contract_id_mismatch",
    "evidence_clock_dq_manifest_contract_id_mismatch",
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
]


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
    assert data["collector_run"]["expected_contract_id"] == "stock_etf_collector_run_v1"
    assert data["collector_run"]["blockers"] == ["ipc_unavailable"]
    assert data["dq_manifest"]["expected_contract_id"] == "stock_etf_dq_manifest_v1"
    assert data["dq_manifest"]["shape_blockers"] == ["ipc_unavailable"]
    assert data["dq_manifest"]["market_data_ingestion_started"] is False
    assert data["dq_manifest"]["dq_writer_started"] is False
    assert data["dq_manifest"]["evidence_clock_started"] is False
    assert data["evidence_clock"]["status"] == "NOT_STARTED"
    assert data["evidence_clock"]["blockers"] == ["ipc_unavailable"]
    assert data["evidence_clock"]["collector_run_contract_id"] == ""
    assert data["evidence_clock"]["collector_run_contract_hash_present"] is False
    assert data["evidence_clock"]["dq_manifest_contract_id"] == ""
    assert data["evidence_clock"]["dq_manifest_contract_hash_present"] is False
    assert data["evidence_clock"]["source_artifact_hash_present"] is False
    assert (
        data["evidence_clock"]["market_data_provenance_contract_hash_present"] is False
    )
    assert data["evidence_clock"]["scorecard_input_bundle_hash_present"] is False
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
    assert data["collector_run"]["expected_contract_id"] == "stock_etf_collector_run_v1"
    assert data["collector_run"]["accepted"] is False
    assert data["collector_run"]["expected_trading_sessions"] == 0
    assert data["collector_run"]["completed_trading_sessions"] == 0
    assert data["collector_run"]["market_data_ingestion_started"] is False
    assert data["collector_run"]["evidence_writer_started"] is False
    assert data["collector_run"]["scorecard_writer_started"] is False
    assert data["evidence_clock"]["expected_contract_id"] == (
        "stock_etf_evidence_clock_v1"
    )
    assert data["evidence_clock"]["status"] == "NOT_STARTED"
    assert data["evidence_clock"]["collector_run_contract_id"] == ""
    assert data["evidence_clock"]["collector_run_contract_hash_present"] is False
    assert data["evidence_clock"]["dq_manifest_contract_id"] == ""
    assert data["evidence_clock"]["dq_manifest_contract_hash_present"] is False
    assert data["evidence_clock"]["source_artifact_hash_present"] is False
    assert (
        data["evidence_clock"]["market_data_provenance_contract_hash_present"] is False
    )
    assert data["evidence_clock"]["scorecard_input_bundle_hash_present"] is False
    assert data["frozen_inputs"]["gui_evidence_view_available"] is False
    assert data["dq_manifest"]["passes_day_quality"] is False
    assert data["dq_manifest"]["expected_contract_id"] == "stock_etf_dq_manifest_v1"
    assert data["dq_manifest"]["contract_id"] == ""
    assert data["dq_manifest"]["source_version"] == 0
    assert data["dq_manifest"]["collector_run_id"] == ""
    assert (
        data["dq_manifest"]["market_data_provenance_contract_hash_present"] is False
    )
    assert data["dq_manifest"]["source_artifact_hash_present"] is False
    assert data["dq_manifest"]["bybit_live_execution_unchanged"] is False
    assert data["dq_manifest"]["ibkr_contact_performed"] is False
    assert data["dq_manifest"]["connector_runtime_started"] is False
    assert data["dq_manifest"]["market_data_ingestion_started"] is False
    assert data["dq_manifest"]["dq_writer_started"] is False
    assert data["dq_manifest"]["evidence_clock_started"] is False
    assert data["dq_manifest"]["scorecard_writer_started"] is False
    assert data["dq_manifest"]["db_apply_performed"] is False
    assert data["dq_manifest"]["secret_content_serialized"] is False
    assert data["dq_manifest"]["live_or_tiny_live_authorized"] is False
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
    payload["collector_run"]["ibkr_contact_performed"] = True
    payload["collector_run"]["connector_runtime_started"] = True
    payload["collector_run"]["market_data_ingestion_started"] = True
    payload["collector_run"]["evidence_writer_started"] = True
    payload["collector_run"]["scorecard_writer_started"] = True
    payload["collector_run"]["db_apply_performed"] = True
    payload["collector_run"]["secret_content_serialized"] = True
    payload["collector_run"]["live_or_tiny_live_authorized"] = True
    payload["dq_manifest"]["ibkr_contact_performed"] = True
    payload["dq_manifest"]["connector_runtime_started"] = True
    payload["dq_manifest"]["market_data_ingestion_started"] = True
    payload["dq_manifest"]["dq_writer_started"] = True
    payload["dq_manifest"]["evidence_clock_started"] = True
    payload["dq_manifest"]["scorecard_writer_started"] = True
    payload["dq_manifest"]["db_apply_performed"] = True
    payload["dq_manifest"]["secret_content_serialized"] = True
    payload["dq_manifest"]["live_or_tiny_live_authorized"] = True
    payload["evidence_clock"]["checker_contacted_ibkr"] = True
    payload["evidence_clock"]["checker_started_connector_runtime"] = True
    payload["evidence_clock"]["collector_run_contract_id"] = "stock_etf_collector_run_v2"
    payload["evidence_clock"]["dq_manifest_contract_id"] = "stock_etf_dq_manifest_v2"
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
    assert data["contract_violations"] == EXPECTED_EVIDENCE_CONTRACT_VIOLATIONS
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


def test_stock_etf_evidence_contract_violation_assertions_stay_exact() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    source_under_test = source.split(
        "def test_stock_etf_evidence_contract_violation_assertions_stay_exact",
        1,
    )[0]
    forbidden_patterns = [
        'set(data["contract_violations"])',
        'in data["contract_violations"]',
        'issubset(set(data["contract_violations"]))',
    ]
    for pattern in forbidden_patterns:
        assert pattern not in source_under_test
