"""Stock/ETF launch-status route tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from stock_etf_route_fixtures import (
    _make_client_with_ipc,
    _valid_launch_status,
    client_fail_closed,
    route_module,
    stock_etf_router,
)


def test_stock_etf_launch_status_returns_200_when_ipc_down(
    client_fail_closed: TestClient,
) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf/launch-status")
    assert resp.status_code == 200
    assert "no-store" in resp.headers["cache-control"]
    assert "private" in resp.headers["cache-control"]
    assert resp.headers["pragma"] == "no-cache"
    assert resp.headers["expires"] == "0"
    assert resp.headers["vary"] == "Authorization"
    body = resp.json()
    data = body["data"]
    assert body["ok"] is True
    assert body["data_category"] == "stock_etf_launch_status"
    assert data["degraded"] is True
    assert data["reason"] == "ipc_unavailable"
    assert data["launch_status_state"] == "degraded"
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["environment"] == "paper_shadow"
    assert data["gui_authority"] == "display_only"
    assert data["phase3_started"] is False
    assert data["phase5_started"] is False
    assert data["first_ibkr_contact_allowed"] is False
    assert data["connector_enabled"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    assert data["paper_shadow_launch_authorized"] is False
    assert data["tiny_live_or_live_authorized"] is False
    assert data["connector_runtime_started"] is False
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    assert data["evidence_clock_started"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False
    assert data["release_packet"]["blockers"] == ["ipc_unavailable"]
    assert data["disable_cleanup_runbook"]["blockers"] == ["ipc_unavailable"]
    assert data["tiny_live_adr_eligibility"]["blockers"] == ["ipc_unavailable"]


def test_stock_etf_launch_status_uses_only_readonly_fixture_method() -> None:
    async def _fake_call(
        method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        assert method == "stock_etf.get_launch_status"
        assert params == {}
        return _valid_launch_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/launch-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["degraded"] is False
    assert data["launch_status_state"] == "blocked"
    assert data["phase"] == "phase5_launch_status_source_fixture"
    assert data["phase3_started"] is False
    assert data["phase5_started"] is False
    assert data["release_packet"]["expected_contract_id"] == "stock_etf_release_packet_v1"
    assert data["release_packet"]["accepted"] is False
    assert data["release_packet"]["paper_shadow_window_complete"] is False
    assert data["release_packet"]["engineering_shakedown_complete"] is False
    assert data["release_packet"]["sealed"] is False
    assert (
        data["disable_cleanup_runbook"]["expected_runbook_id"]
        == "stock_etf_kill_switch_and_disable_cleanup_runbook_v1"
    )
    assert data["disable_cleanup_runbook"]["accepted"] is False
    assert data["disable_cleanup_runbook"]["paper_shadow_launch_authorized"] is False
    assert (
        data["tiny_live_adr_eligibility"]["expected_contract_id"]
        == "tiny_live_adr_eligibility_v1"
    )
    assert data["tiny_live_adr_eligibility"]["accepted"] is False
    assert data["tiny_live_adr_eligibility"]["decision"] == "not_eligible"
    assert (
        data["tiny_live_adr_eligibility"]["scorecard_derivation_hash_present"]
        is False
    )
    assert data["tiny_live_adr_eligibility"]["scorecard_verdict_hash_present"] is False
    assert (
        data["tiny_live_adr_eligibility"]["paper_shadow_reconciliation_hash_present"]
        is False
    )
    assert data["tiny_live_adr_eligibility"]["qa_review_hash_present"] is False
    assert data["tiny_live_adr_eligibility"]["qa_review_passed"] is False
    assert data["allowed_gui_actions"] == ["refresh_launch_status"]
    assert data["api_allowlist"]["contract_id"] == "non_bybit_api_allowlist_v1"
    assert data["paper_shadow_launch_authorized"] is False
    assert data["tiny_live_or_live_authorized"] is False
    assert data["connector_runtime_started"] is False
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    assert data["evidence_clock_started"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_launch_status_does_not_trust_client_state() -> None:
    async def _fake_call(
        method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        assert method == "stock_etf.get_launch_status"
        assert params == {}
        return _valid_launch_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        resp = client.get(
            "/api/v1/stock-etf/launch-status",
            params={
                "phase5_started": "true",
                "paper_shadow_launch_authorized": "true",
                "tiny_live_or_live_authorized": "true",
            },
            headers={
                "X-Stock-Etf-Launch": "true",
                "X-Ibkr-Live": "true",
            },
        )
        data = resp.json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert "no-store" in resp.headers["cache-control"]
    assert data["phase3_started"] is False
    assert data["phase5_started"] is False
    assert data["first_ibkr_contact_allowed"] is False
    assert data["paper_shadow_launch_authorized"] is False
    assert data["tiny_live_or_live_authorized"] is False
    assert data["connector_runtime_started"] is False
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_launch_status_blocks_contract_violation() -> None:
    payload = _valid_launch_status()
    payload["phase3_started"] = True
    payload["phase5_started"] = True
    payload["asset_lane"] = "crypto_perp"
    payload["broker"] = "bybit"
    payload["environment"] = "paper"
    payload["connector_runtime_started"] = True
    payload["scorecard_writer_started"] = True
    payload["db_apply_performed"] = True
    payload["evidence_clock_started"] = True
    payload["ibkr_call_performed"] = True
    payload["secret_slot_touched"] = True
    payload["order_routed"] = True
    payload["bybit_ipc_reused"] = True
    payload["paper_shadow_launch_authorized"] = True
    payload["tiny_live_or_live_authorized"] = True

    release = payload["release_packet"]
    release["expected_contract_id"] = "wrong"
    release["accepted"] = True
    for key in (
        "paper_shadow_window_complete",
        "engineering_shakedown_complete",
        "pg_migrations_declared",
        "pg_dry_run_log_hash_present",
        "pg_double_apply_log_hash_present",
        "redaction_fixture_hash_present",
        "evidence_archive_pointer_present",
        "evidence_archive_hash_present",
        "secret_content_serialized",
        "ibkr_live_or_tiny_live_authorized",
        "sealed",
    ):
        release[key] = True
    release["role_report_count"] = 1
    release["manifest_hash_count"] = 1
    release["gui_screenshot_hash_count"] = 1
    release["dq_manifest_hash_count"] = 1
    release["scorecard_regeneration_hash_count"] = 1

    runbook = payload["disable_cleanup_runbook"]
    runbook["expected_runbook_id"] = "wrong"
    runbook["accepted"] = True
    for key in (
        "bybit_live_execution_unchanged",
        "ibkr_contact_performed",
        "connector_runtime_started",
        "paper_order_routed",
        "secret_slot_created",
        "secret_content_serialized",
        "destructive_db_cleanup_requested",
        "db_delete_or_truncate_allowed",
        "paper_shadow_launch_authorized",
        "tiny_live_authorized",
        "live_authorized",
    ):
        runbook[key] = True
    runbook["env_flag_count"] = 1
    runbook["proof_count"] = 1

    tiny_live = payload["tiny_live_adr_eligibility"]
    tiny_live["expected_contract_id"] = "wrong"
    tiny_live["accepted"] = True
    tiny_live["decision"] = "adr_discussion_only"
    for key in (
        "scorecard_derivation_hash_present",
        "scorecard_verdict_hash_present",
        "scorecard_manifest_hash_present",
        "paper_shadow_reconciliation_hash_present",
        "dq_manifest_hash_present",
        "statistical_preregistration_hash_present",
        "qc_review_hash_present",
        "mit_review_hash_present",
        "qa_review_hash_present",
        "paper_shadow_window_complete",
        "concentration_label_passed",
        "regime_label_passed",
        "freshness_label_passed",
        "qc_review_passed",
        "mit_review_passed",
        "qa_review_passed",
        "secret_content_serialized",
        "sealed",
    ):
        tiny_live[key] = True
    tiny_live["benchmark_relative_after_cost_lcb_bps"] = 1
    tiny_live["independent_observation_count"] = 1
    tiny_live["min_independent_observation_count"] = 1
    tiny_live["conservative_cost_stress_lcb_bps"] = 1
    tiny_live["paper_shadow_divergence_bps"] = 1
    tiny_live["max_paper_shadow_divergence_bps"] = 1

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(return_value=payload)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/launch-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["launch_status_state"] == "contract_violation_blocked"
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
        "phase5_started",
        "connector_runtime_started",
        "scorecard_writer_started",
        "db_apply_performed",
        "evidence_clock_started",
        "paper_shadow_launch_authorized",
        "tiny_live_or_live_authorized",
        "release_expected_contract_id_mismatch",
        "release_packet_accepted_before_launch_audit",
        "release_paper_shadow_window_complete",
        "release_engineering_shakedown_complete",
        "release_secret_content_serialized",
        "release_ibkr_live_or_tiny_live_authorized",
        "release_sealed",
        "release_role_report_count_present",
        "runbook_expected_id_mismatch",
        "disable_cleanup_runbook_accepted_before_launch_audit",
        "runbook_bybit_live_execution_unchanged",
        "runbook_ibkr_contact_performed",
        "runbook_connector_runtime_started",
        "runbook_paper_shadow_launch_authorized",
        "runbook_env_flag_count_present",
        "tiny_live_expected_contract_id_mismatch",
        "tiny_live_eligibility_accepted_before_launch_audit",
        "tiny_live_scorecard_derivation_hash_present",
        "tiny_live_scorecard_verdict_hash_present",
        "tiny_live_paper_shadow_reconciliation_hash_present",
        "tiny_live_qa_review_hash_present",
        "tiny_live_paper_shadow_window_complete",
        "tiny_live_concentration_label_passed",
        "tiny_live_qa_review_passed",
        "tiny_live_decision_not_blocked",
        "tiny_live_independent_observation_count_present",
    }.issubset(set(data["contract_violations"]))
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["environment"] == "paper_shadow"
    assert data["phase3_started"] is False
    assert data["phase5_started"] is False
    assert data["paper_shadow_launch_authorized"] is False
    assert data["tiny_live_or_live_authorized"] is False
    assert data["connector_runtime_started"] is False
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    assert data["evidence_clock_started"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False


def test_stock_etf_launch_status_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf/launch-status")

    assert resp.status_code == 401
