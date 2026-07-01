"""Stock/ETF disable-cleanup-status route tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from stock_etf_route_fixtures import (
    _make_client_with_ipc,
    _valid_disable_cleanup_status,
    client_fail_closed,
)

EXPECTED_DISABLE_CLEANUP_CONTRACT_VIOLATIONS = [
    "ibkr_call_performed",
    "secret_slot_touched",
    "order_routed",
    "bybit_ipc_reused",
    "phase3_started",
    "phase5_started",
    "collector_stop_requested",
    "gui_disable_requested",
    "evidence_archive_requested",
    "db_cleanup_requested",
    "connector_runtime_started",
    "scorecard_writer_started",
    "db_apply_performed",
    "evidence_clock_started",
    "paper_shadow_launch_authorized",
    "tiny_live_or_live_authorized",
    "asset_lane_mismatch",
    "broker_mismatch",
    "environment_mismatch",
    "runbook_expected_id_mismatch",
    "runbook_not_accepted",
    "runbook_source_artifact_hash_missing",
    "runbook_bybit_live_not_protected",
    "runbook_env_flag_count_mismatch",
    "runbook_proof_count_mismatch",
    "runbook_ibkr_contact_performed",
    "runbook_connector_runtime_started",
    "runbook_paper_order_routed",
    "runbook_secret_slot_created",
    "runbook_secret_content_serialized",
    "runbook_destructive_db_cleanup_requested",
    "runbook_db_delete_or_truncate_allowed",
    "runbook_paper_shadow_launch_authorized",
    "runbook_tiny_live_authorized",
    "runbook_live_authorized",
    "env_flag_OPENCLAW_STOCK_ETF_LANE_ENABLED_observed_mismatch",
    "env_flag_OPENCLAW_STOCK_ETF_LANE_ENABLED_evidence_hash_missing",
    "proof_collector_stopped_not_verified",
    "proof_collector_stopped_evidence_hash_missing",
    "proof_collector_stopped_grants_runtime_authority",
    "proof_collector_stopped_destructive_cleanup_claimed",
]


def test_stock_etf_disable_cleanup_status_returns_200_when_ipc_down(
    client_fail_closed: TestClient,
) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf/disable-cleanup-status")
    assert resp.status_code == 200
    assert "no-store" in resp.headers["cache-control"]
    assert "private" in resp.headers["cache-control"]
    assert resp.headers["pragma"] == "no-cache"
    assert resp.headers["expires"] == "0"
    assert resp.headers["vary"] == "Authorization"
    body = resp.json()
    data = body["data"]
    assert body["ok"] is True
    assert body["data_category"] == "stock_etf_disable_cleanup_status"
    assert data["degraded"] is True
    assert data["reason"] == "ipc_unavailable"
    assert data["disable_cleanup_status_state"] == "degraded"
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
    assert data["collector_stop_requested"] is False
    assert data["gui_disable_requested"] is False
    assert data["evidence_archive_requested"] is False
    assert data["db_cleanup_requested"] is False
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
    assert data["runbook"]["blockers"] == ["ipc_unavailable"]
    assert data["runbook"]["accepted"] is False


def test_stock_etf_disable_cleanup_status_uses_only_readonly_fixture_method() -> None:
    async def _fake_call(
        method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        assert method == "stock_etf.get_disable_cleanup_status"
        assert params == {}
        return _valid_disable_cleanup_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/disable-cleanup-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    runbook = data["runbook"]
    assert data["degraded"] is False
    assert data["disable_cleanup_status_state"] == "source_ready_runtime_blocked"
    assert data["phase"] == "phase5_disable_cleanup_status_source_fixture"
    assert data["phase3_started"] is False
    assert data["phase5_started"] is False
    assert data["collector_stop_requested"] is False
    assert data["gui_disable_requested"] is False
    assert data["evidence_archive_requested"] is False
    assert data["db_cleanup_requested"] is False
    assert runbook["expected_runbook_id"] == (
        "stock_etf_kill_switch_and_disable_cleanup_runbook_v1"
    )
    assert runbook["runbook_id"] == (
        "stock_etf_kill_switch_and_disable_cleanup_runbook_v1"
    )
    assert runbook["accepted"] is True
    assert runbook["source_artifact_hash_present"] is True
    assert runbook["bybit_live_execution_unchanged"] is True
    assert runbook["env_flag_count"] == 4
    assert runbook["proof_count"] == 7
    assert len(runbook["env_flags"]) == 4
    assert len(runbook["proofs"]) == 7
    assert runbook["ibkr_contact_performed"] is False
    assert runbook["connector_runtime_started"] is False
    assert runbook["paper_order_routed"] is False
    assert runbook["secret_slot_created"] is False
    assert runbook["secret_content_serialized"] is False
    assert runbook["destructive_db_cleanup_requested"] is False
    assert runbook["db_delete_or_truncate_allowed"] is False
    assert runbook["paper_shadow_launch_authorized"] is False
    assert runbook["tiny_live_authorized"] is False
    assert runbook["live_authorized"] is False
    assert data["allowed_gui_actions"] == ["refresh_disable_cleanup_status"]
    assert data["api_allowlist"]["contract_id"] == "non_bybit_api_allowlist_v1"
    assert data["paper_shadow_launch_authorized"] is False
    assert data["tiny_live_or_live_authorized"] is False
    assert data["connector_runtime_started"] is False
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    assert data["evidence_clock_started"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_disable_cleanup_status_does_not_trust_client_state() -> None:
    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(return_value=_valid_disable_cleanup_status())
    client = _make_client_with_ipc(fake_ipc)
    try:
        resp = client.get(
            "/api/v1/stock-etf/disable-cleanup-status",
            params={
                "collector_stop_requested": "true",
                "paper_shadow_launch_authorized": "true",
                "tiny_live_or_live_authorized": "true",
            },
            headers={
                "X-Stock-Etf-Disable": "true",
                "X-Ibkr-Live": "true",
            },
        )
        data = resp.json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert "no-store" in resp.headers["cache-control"]
    assert data["phase3_started"] is False
    assert data["phase5_started"] is False
    assert data["collector_stop_requested"] is False
    assert data["gui_disable_requested"] is False
    assert data["evidence_archive_requested"] is False
    assert data["db_cleanup_requested"] is False
    assert data["first_ibkr_contact_allowed"] is False
    assert data["paper_shadow_launch_authorized"] is False
    assert data["tiny_live_or_live_authorized"] is False
    assert data["connector_runtime_started"] is False
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_disable_cleanup_status_blocks_contract_violation() -> None:
    payload = _valid_disable_cleanup_status()
    payload["phase3_started"] = True
    payload["phase5_started"] = True
    payload["asset_lane"] = "crypto_perp"
    payload["broker"] = "bybit"
    payload["environment"] = "paper"
    payload["collector_stop_requested"] = True
    payload["gui_disable_requested"] = True
    payload["evidence_archive_requested"] = True
    payload["db_cleanup_requested"] = True
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

    runbook = payload["runbook"]
    runbook["expected_runbook_id"] = "wrong"
    runbook["accepted"] = False
    runbook["source_artifact_hash_present"] = False
    runbook["bybit_live_execution_unchanged"] = False
    runbook["env_flag_count"] = 3
    runbook["proof_count"] = 6
    for key in (
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
    runbook["env_flags"][0]["observed_value"] = "1"
    runbook["env_flags"][0]["evidence_hash_present"] = False
    runbook["proofs"][0]["verified"] = False
    runbook["proofs"][0]["evidence_hash_present"] = False
    runbook["proofs"][0]["grants_runtime_authority"] = True
    runbook["proofs"][0]["destructive_cleanup_claimed"] = True

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(return_value=payload)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/disable-cleanup-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["disable_cleanup_status_state"] == "contract_violation_blocked"
    assert data["degraded"] is True
    assert (
        data["contract_violations"]
        == EXPECTED_DISABLE_CLEANUP_CONTRACT_VIOLATIONS
    )
    assert data["paper_shadow_launch_authorized"] is False
    assert data["tiny_live_or_live_authorized"] is False
    assert data["connector_runtime_started"] is False
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    assert data["evidence_clock_started"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_disable_cleanup_contract_violation_assertions_stay_exact() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    source_under_test = source.split(
        "def test_stock_etf_disable_cleanup_contract_violation_assertions_stay_exact",
        1,
    )[0]
    forbidden_patterns = [
        'set(data["contract_violations"])',
        'in data["contract_violations"]',
        'issubset(set(data["contract_violations"]))',
    ]

    for pattern in forbidden_patterns:
        assert pattern not in source_under_test
