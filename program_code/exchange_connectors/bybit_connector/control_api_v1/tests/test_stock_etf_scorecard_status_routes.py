"""Stock/ETF scorecard-status route tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from stock_etf_route_fixtures import (
    _make_client_with_ipc,
    _valid_scorecard_status,
    client_fail_closed,
    route_module,
    stock_etf_router,
)


def test_stock_etf_scorecard_status_returns_200_when_ipc_down(
    client_fail_closed: TestClient,
) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf/scorecard-status")
    assert resp.status_code == 200
    assert "no-store" in resp.headers["cache-control"]
    assert "private" in resp.headers["cache-control"]
    assert resp.headers["pragma"] == "no-cache"
    assert resp.headers["expires"] == "0"
    assert resp.headers["vary"] == "Authorization"
    body = resp.json()
    data = body["data"]
    assert body["ok"] is True
    assert body["data_category"] == "stock_etf_scorecard_status"
    assert data["degraded"] is True
    assert data["reason"] == "ipc_unavailable"
    assert data["scorecard_status_state"] == "degraded"
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["environment"] == "paper_shadow"
    assert data["gui_authority"] == "display_only"
    assert data["phase3_started"] is False
    assert data["first_ibkr_contact_allowed"] is False
    assert data["connector_enabled"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    assert data["evidence_clock_started"] is False
    assert data["paper_shadow_window_complete"] is False
    assert data["live_or_tiny_live_authorized"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False
    assert data["scorecard"]["blockers"] == ["ipc_unavailable"]


def test_stock_etf_scorecard_status_uses_only_readonly_fixture_method() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_scorecard_status"
        assert params == {}
        return _valid_scorecard_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/scorecard-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["degraded"] is False
    assert data["scorecard_status_state"] == "blocked"
    assert data["phase"] == "phase3_scorecard_status_source_fixture"
    assert data["phase3_started"] is False
    assert data["scorecard"]["expected_contract_id"] == "stock_etf_scorecard_verdict_v1"
    assert data["scorecard"]["accepted"] is False
    assert data["scorecard"]["verdict_label"] == "insufficient_evidence"
    assert data["scorecard"]["scorecard_input_bundle_hash_present"] is False
    assert data["scorecard"]["formula_appendix_hash_present"] is False
    assert data["scorecard"]["statistical_preregistration_hash_present"] is False
    assert data["scorecard"]["scorecard_manifest_hash_present"] is False
    assert data["scorecard"]["paper_shadow_window_trading_days"] == 0
    assert data["scorecard"]["independent_observation_count"] == 0
    assert data["scorecard"]["benchmark_excess_lcb_bps"] == 0
    assert data["scorecard"]["psr_bps"] == 0
    assert data["scorecard"]["dsr_bps"] == 0
    assert data["scorecard"]["scorecard_is_derived_only"] is False
    assert data["scorecard"]["paper_and_shadow_fills_separate"] is False
    assert data["scorecard"]["sealed"] is False
    assert data["allowed_gui_actions"] == ["refresh_scorecard_status"]
    assert data["api_allowlist"]["contract_id"] == "non_bybit_api_allowlist_v1"
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_scorecard_status_does_not_trust_client_state() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_scorecard_status"
        assert params == {}
        return _valid_scorecard_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        resp = client.get(
            "/api/v1/stock-etf/scorecard-status",
            params={
                "phase3_started": "true",
                "scorecard_writer_started": "true",
                "live_or_tiny_live_authorized": "true",
            },
            headers={
                "X-Scorecard-Writer-Started": "true",
                "X-Ibkr-Live": "true",
            },
        )
        data = resp.json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert "no-store" in resp.headers["cache-control"]
    assert data["phase3_started"] is False
    assert data["first_ibkr_contact_allowed"] is False
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    assert data["evidence_clock_started"] is False
    assert data["paper_shadow_window_complete"] is False
    assert data["live_or_tiny_live_authorized"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_scorecard_status_blocks_contract_violation() -> None:
    payload = _valid_scorecard_status()
    payload["phase3_started"] = True
    payload["asset_lane"] = "crypto_perp"
    payload["broker"] = "bybit"
    payload["environment"] = "paper"
    payload["scorecard_writer_started"] = True
    payload["db_apply_performed"] = True
    payload["evidence_clock_started"] = True
    payload["paper_shadow_window_complete"] = True
    payload["ibkr_call_performed"] = True
    payload["secret_slot_touched"] = True
    payload["order_routed"] = True
    payload["bybit_ipc_reused"] = True
    payload["live_or_tiny_live_authorized"] = True
    scorecard = payload["scorecard"]
    scorecard["expected_contract_id"] = "wrong"
    scorecard["accepted"] = True
    for key in (
        "scorecard_input_bundle_hash_present",
        "formula_appendix_hash_present",
        "statistical_preregistration_hash_present",
        "scorecard_manifest_hash_present",
        "verdict_rationale_hash_present",
        "concentration_label_passed",
        "regime_label_passed",
        "breadth_label_passed",
        "freshness_label_passed",
        "survivorship_label_passed",
        "execution_realism_label_passed",
        "qc_review_hash_present",
        "qc_review_passed",
        "scorecard_is_derived_only",
        "paper_and_shadow_fills_separate",
        "bybit_live_execution_unchanged",
        "sealed",
    ):
        scorecard[key] = True
    scorecard["paper_shadow_window_trading_days"] = 42
    scorecard["independent_observation_count"] = 80
    scorecard["benchmark_excess_lcb_bps"] = 12
    scorecard["psr_bps"] = 9700

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(return_value=payload)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/scorecard-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["scorecard_status_state"] == "contract_violation_blocked"
    assert data["degraded"] is True
    assert {
        "ibkr_call_performed",
        "secret_slot_touched",
        "order_routed",
        "bybit_ipc_reused",
        "live_or_tiny_live_authorized",
        "asset_lane_mismatch",
        "broker_mismatch",
        "environment_mismatch",
        "phase3_started",
        "scorecard_writer_started",
        "db_apply_performed",
        "evidence_clock_started",
        "paper_shadow_window_complete",
        "scorecard_expected_contract_id_mismatch",
        "scorecard_accepted_before_writer",
        "scorecard_scorecard_input_bundle_hash_present",
        "scorecard_formula_appendix_hash_present",
        "scorecard_statistical_preregistration_hash_present",
        "scorecard_scorecard_manifest_hash_present",
        "scorecard_verdict_rationale_hash_present",
        "scorecard_concentration_label_passed",
        "scorecard_execution_realism_label_passed",
        "scorecard_qc_review_hash_present",
        "scorecard_qc_review_passed",
        "scorecard_scorecard_is_derived_only",
        "scorecard_paper_and_shadow_fills_separate",
        "scorecard_bybit_live_execution_unchanged",
        "scorecard_sealed",
        "scorecard_paper_shadow_window_trading_days_present",
        "scorecard_independent_observation_count_present",
        "scorecard_benchmark_excess_lcb_bps_present",
        "scorecard_psr_bps_present",
    }.issubset(set(data["contract_violations"]))
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["environment"] == "paper_shadow"
    assert data["phase3_started"] is False
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    assert data["evidence_clock_started"] is False
    assert data["live_or_tiny_live_authorized"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False


def test_stock_etf_scorecard_status_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf/scorecard-status")

    assert resp.status_code == 401
