"""Stock/ETF release-packet-status route tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from stock_etf_route_fixtures import (
    _make_client_with_ipc,
    _valid_release_packet_status,
    client_fail_closed,
)


def test_stock_etf_release_packet_status_returns_200_when_ipc_down(
    client_fail_closed: TestClient,
) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf/release-packet-status")
    assert resp.status_code == 200
    assert "no-store" in resp.headers["cache-control"]
    assert "private" in resp.headers["cache-control"]
    assert resp.headers["pragma"] == "no-cache"
    assert resp.headers["expires"] == "0"
    assert resp.headers["vary"] == "Authorization"
    body = resp.json()
    data = body["data"]
    assert body["ok"] is True
    assert body["data_category"] == "stock_etf_release_packet_status"
    assert data["degraded"] is True
    assert data["reason"] == "ipc_unavailable"
    assert data["release_packet_status_state"] == "degraded"
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
    assert data["release_packet"]["accepted"] is False


def test_stock_etf_release_packet_status_uses_only_readonly_fixture_method() -> None:
    async def _fake_call(
        method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        assert method == "stock_etf.get_release_packet_status"
        assert params == {}
        return _valid_release_packet_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/release-packet-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    release = data["release_packet"]
    kill = release["kill_disable_cleanup_proof"]
    assert data["degraded"] is False
    assert data["release_packet_status_state"] == "source_ready_runtime_blocked"
    assert data["phase"] == "phase5_release_packet_status_source_fixture"
    assert data["phase3_started"] is False
    assert data["phase5_started"] is False
    assert release["expected_contract_id"] == "stock_etf_release_packet_v1"
    assert release["packet_id"] == "stock_etf_release_packet_v1"
    assert release["source_version"] == 1
    assert release["accepted"] is True
    assert release["source_commit_present"] is True
    assert release["reviewer_role_count"] == 8
    assert set(release["reviewer_roles"]) == {
        "PM",
        "Operator",
        "E2",
        "E3",
        "E4",
        "QA",
        "QC",
        "MIT",
    }
    assert release["role_report_count"] == 2
    assert release["e2_log_hash_present"] is True
    assert release["e3_redaction_log_hash_present"] is True
    assert release["e4_log_hash_present"] is True
    assert release["qa_log_hash_present"] is True
    assert release["manifest_hash_count"] == 2
    assert len(release["manifest_hashes"]) == 2
    assert release["pg_migrations_declared"] is False
    assert release["redaction_fixture_hash_present"] is True
    assert release["gui_screenshot_hash_count"] == 1
    assert release["dq_manifest_hash_count"] == 1
    assert release["scorecard_regeneration_hash_count"] == 1
    assert release["evidence_archive_pointer_present"] is True
    assert release["evidence_archive_hash_present"] is True
    assert release["paper_shadow_window_complete"] is True
    assert release["engineering_shakedown_complete"] is True
    assert release["secret_content_serialized"] is False
    assert release["ibkr_live_or_tiny_live_authorized"] is False
    assert release["sealed"] is True
    assert kill["stock_etf_lane_enabled_false"] is True
    assert kill["ibkr_readonly_enabled_false"] is True
    assert kill["ibkr_paper_enabled_false"] is True
    assert kill["stock_etf_shadow_only_true"] is True
    assert kill["collector_stopped"] is True
    assert kill["gui_stock_views_disabled_or_hidden"] is True
    assert kill["live_secret_absence_proven"] is True
    assert kill["evidence_archive_forward_only"] is True
    assert kill["destructive_db_cleanup_requested"] is False
    assert kill["proof_hash_present"] is True
    assert data["allowed_gui_actions"] == ["refresh_release_packet_status"]
    assert data["api_allowlist"]["contract_id"] == "non_bybit_api_allowlist_v1"
    assert data["paper_shadow_launch_authorized"] is False
    assert data["tiny_live_or_live_authorized"] is False
    assert data["connector_runtime_started"] is False
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    assert data["evidence_clock_started"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_release_packet_status_does_not_trust_client_state() -> None:
    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(return_value=_valid_release_packet_status())
    client = _make_client_with_ipc(fake_ipc)
    try:
        resp = client.get(
            "/api/v1/stock-etf/release-packet-status",
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


def test_stock_etf_release_packet_status_blocks_contract_violation() -> None:
    payload = _valid_release_packet_status()
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
    release["accepted"] = False
    release["source_commit_present"] = False
    release["reviewer_role_count"] = 1
    release["reviewer_roles"] = ["PM"]
    release["role_report_count"] = 0
    release["manifest_hash_count"] = 0
    release["gui_screenshot_hash_count"] = 0
    release["dq_manifest_hash_count"] = 0
    release["scorecard_regeneration_hash_count"] = 0
    release["e2_log_hash_present"] = False
    release["e3_redaction_log_hash_present"] = False
    release["e4_log_hash_present"] = False
    release["qa_log_hash_present"] = False
    release["manifest_hashes"][0]["hash_present"] = False
    release["pg_migrations_declared"] = True
    release["pg_migration_manifest_hash_present"] = False
    release["pg_dry_run_log_hash_present"] = False
    release["pg_double_apply_log_hash_present"] = False
    release["redaction_fixture_hash_present"] = False
    release["evidence_archive_pointer_present"] = False
    release["evidence_archive_hash_present"] = False
    release["paper_shadow_window_complete"] = False
    release["engineering_shakedown_complete"] = False
    release["secret_content_serialized"] = True
    release["ibkr_live_or_tiny_live_authorized"] = True
    release["sealed"] = False
    kill = release["kill_disable_cleanup_proof"]
    for key in (
        "stock_etf_lane_enabled_false",
        "ibkr_readonly_enabled_false",
        "ibkr_paper_enabled_false",
        "stock_etf_shadow_only_true",
        "collector_stopped",
        "gui_stock_views_disabled_or_hidden",
        "live_secret_absence_proven",
        "evidence_archive_forward_only",
        "proof_hash_present",
    ):
        kill[key] = False
    kill["destructive_db_cleanup_requested"] = True

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(return_value=payload)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/release-packet-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["release_packet_status_state"] == "contract_violation_blocked"
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
        "release_packet_not_accepted",
        "source_commit_missing",
        "reviewer_role_count_below_minimum",
        "reviewer_role_Operator_missing",
        "role_report_count_missing",
        "manifest_hash_count_missing",
        "gui_screenshot_hash_count_missing",
        "release_e2_log_hash_present_missing",
        "manifest_release_manifest_hash_missing",
        "pg_dry_run_log_hash_present_missing",
        "release_secret_content_serialized",
        "release_ibkr_live_or_tiny_live_authorized",
        "kill_stock_etf_lane_enabled_false_missing",
        "kill_live_secret_absence_proven_missing",
        "kill_destructive_db_cleanup_requested",
    }.issubset(set(data["contract_violations"]))
    assert data["paper_shadow_launch_authorized"] is False
    assert data["tiny_live_or_live_authorized"] is False
    assert data["connector_runtime_started"] is False
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    assert data["evidence_clock_started"] is False
    fake_ipc.call.assert_awaited_once()
