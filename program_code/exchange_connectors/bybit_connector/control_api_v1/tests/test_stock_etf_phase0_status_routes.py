"""Stock/ETF Phase 0 status route tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from stock_etf_route_fixtures import (
    _make_client_with_ipc,
    _valid_phase0_status,
    client_fail_closed,
)

EXPECTED_PHASE0_CONTRACT_VIOLATIONS = [
    "phase5_started",
    "paper_shadow_launch_authorized",
    "phase0_status_mismatch",
    (
        "phase0_contract_missing:"
        "stock_etf_ibkr_readonly_probe_result_import_request_v1"
    ),
    "phase0_ibkr_call_performed",
    "phase0_global_denial_missing:ibkr_live",
]

EXPECTED_PHASE0_CONTRACTS = [
    "asset_lane_taxonomy_v1",
    "broker_capability_registry_v1",
    "phase2_ibkr_external_surface_gate_v1",
    "non_bybit_api_allowlist_v1",
    "stock_etf_ibkr_readonly_probe_request_v1",
    "stock_etf_ibkr_readonly_probe_result_import_request_v1",
    "instrument_identity_contract_v1",
    "stock_etf_pit_universe_contract_v1",
    "stock_etf_strategy_hypothesis_contract_v1",
    "stock_etf_risk_policy_v1",
    "stock_etf_reference_data_sources_v1",
    "ibkr_api_session_topology_v1",
    "ibkr_session_attestation_v1",
    "feature_flag_secret_auth_matrix_v1",
    "lane_scoped_ipc_v1",
    "stock_etf_paper_order_request_v1",
    "stock_etf_paper_fill_import_request_v1",
    "stock_etf_shadow_signal_request_v1",
    "ibkr_paper_order_lifecycle_v1",
    "broker_lifecycle_event_log_v1",
    "audit.asset_lane_events_v1",
    "stock_etf_db_evidence_ddl_v1",
    "stock_market_data_provenance_v1",
    "broker_account_portfolio_cash_ledger_v1",
    "cost_model_version_v1",
    "benchmark_versions_v1",
    "stock_shadow_fill_model_v1",
    "stock_etf_paper_shadow_reconciliation_v1",
    "stock_etf_collector_run_v1",
    "stock_etf_dq_manifest_v1",
    "stock_etf_evidence_clock_v1",
    "gui_lane_contract_v1",
    "stock_etf_storage_capacity_v1",
    "stock_etf_kill_switch_and_disable_cleanup_runbook_v1",
    "stock_etf_release_packet_v1",
    "tiny_live_adr_eligibility_v1",
]


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
    assert data["contract_count"] == len(EXPECTED_PHASE0_CONTRACTS)
    assert data["contracts"] == EXPECTED_PHASE0_CONTRACTS
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
    payload["contracts"].remove("stock_etf_ibkr_readonly_probe_result_import_request_v1")
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
    assert data["contract_violations"] == EXPECTED_PHASE0_CONTRACT_VIOLATIONS


def test_phase0_status_contract_assertions_stay_exact() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    source_under_test = source.split(
        "def test_phase0_status_contract_assertions_stay_exact", 1
    )[0]
    forbidden_patterns = [
        'set(data["contract_violations"])',
        'in data["contract_violations"]',
        'issubset(set(data["contract_violations"]))',
        'set(data["contracts"])',
        'in data["contracts"]',
        'issubset(set(data["contracts"]))',
    ]

    for pattern in forbidden_patterns:
        assert pattern not in source_under_test
