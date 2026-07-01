"""Stock/ETF account-status route tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from stock_etf_route_fixtures import (
    _make_client_with_ipc,
    _valid_account_status,
    client_fail_closed,
    route_module,
    stock_etf_router,
)

EXPECTED_ACCOUNT_CONTRACT_VIOLATIONS = [
    "ibkr_call_performed",
    "secret_slot_touched",
    "order_routed",
    "bybit_ipc_reused",
    "db_apply_performed",
    "asset_lane_mismatch",
    "broker_mismatch",
    "environment_mismatch",
    "phase2_started",
    "readonly_account_snapshot_started",
    "paper_account_snapshot_started",
    "account_snapshot_present",
    "portfolio_positions_snapshot_present",
    "cash_ledger_present",
    "paper_account_attestation_present",
    "session_attestation_present",
    "connector_runtime_started",
    "gateway_socket_open",
    "account_snapshot_expected_contract_id_mismatch",
    "account_snapshot_accepted_before_gate",
    "account_snapshot_account_fingerprint_hash_present",
    "account_snapshot_account_snapshot_hash_present",
    "account_snapshot_portfolio_positions_hash_present",
    "account_snapshot_source_report_hash_present",
    "account_snapshot_as_of_present",
    "session_attestation_expected_contract_id_mismatch",
    "session_attestation_accepted_before_gate",
    "session_attestation_account_fingerprint_present",
    "session_attestation_account_fingerprint_is_live",
    "session_attestation_process_identity_present",
    "session_attestation_secret_slot_fingerprint_present",
    "session_attestation_secret_world_readable",
    "session_attestation_env_var_credential_fallback_used",
    "session_attestation_api_server_version_present",
    "session_attestation_entitlements_fingerprint_present",
    "session_attestation_market_data_entitlement_purchase_denied",
    "session_attestation_raw_artifact_hash_present",
    "session_attestation_data_tier_present",
    "session_attestation_gateway_started_at_present",
    "session_attestation_port_present",
    "session_attestation_attested_at_present",
    "session_attestation_expires_at_present",
    "paper_attestation_expected_contract_id_mismatch",
    "paper_attestation_policy_not_paper_only",
    "paper_attestation_live_account_not_denied",
    "paper_attestation_margin_short_options_cfd_not_denied",
]


def test_stock_etf_account_status_returns_200_when_ipc_down(
    client_fail_closed: TestClient,
) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf/account-status")
    assert resp.status_code == 200
    assert "no-store" in resp.headers["cache-control"]
    assert "private" in resp.headers["cache-control"]
    assert resp.headers["pragma"] == "no-cache"
    assert resp.headers["expires"] == "0"
    assert resp.headers["vary"] == "Authorization"
    body = resp.json()
    data = body["data"]
    assert body["ok"] is True
    assert body["data_category"] == "stock_etf_account_status"
    assert data["degraded"] is True
    assert data["reason"] == "ipc_unavailable"
    assert data["account_status_state"] == "degraded"
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["environment"] == "paper_readonly"
    assert data["gui_authority"] == "display_only"
    assert data["phase2_started"] is False
    assert data["first_ibkr_contact_allowed"] is False
    assert data["connector_enabled"] is False
    assert data["account_snapshot_present"] is False
    assert data["portfolio_positions_snapshot_present"] is False
    assert data["paper_account_attestation_present"] is False
    assert data["session_attestation_present"] is False
    assert data["connector_runtime_started"] is False
    assert data["gateway_socket_open"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False
    assert data["account_snapshot"]["blockers"] == ["ipc_unavailable"]
    assert data["session_attestation"]["blockers"] == ["ipc_unavailable"]


def test_stock_etf_account_status_uses_only_readonly_fixture_method() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_account_status"
        assert params == {}
        return _valid_account_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/account-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["degraded"] is False
    assert data["account_status_state"] == "blocked"
    assert data["phase"] == "phase2_account_status_source_fixture"
    assert data["phase2_started"] is False
    assert data["account_snapshot"]["expected_contract_id"] == (
        "broker_account_portfolio_cash_ledger_v1"
    )
    assert data["account_snapshot"]["accepted"] is False
    assert data["account_snapshot"]["account_snapshot_hash_present"] is False
    assert data["session_attestation"]["expected_contract_id"] == (
        "ibkr_session_attestation_v1"
    )
    assert data["session_attestation"]["accepted"] is False
    assert data["session_attestation"]["secret_slot_fingerprint_present"] is False
    assert data["session_attestation"]["data_tier"] == "unknown"
    assert data["session_attestation"]["entitlements_fingerprint_present"] is False
    assert data["session_attestation"]["gateway_started_at_ms"] == 0
    assert data["paper_attestation_policy"]["expected_contract_id"] == (
        "ibkr_paper_attestation_v1"
    )
    assert data["paper_attestation_policy"]["accepted"] is True
    assert data["paper_attestation_policy"]["paper_environment_only"] is True
    assert data["paper_attestation_policy"]["live_account_fingerprint_denied"] is True
    assert data["allowed_gui_actions"] == ["refresh_account_status"]
    assert data["api_allowlist"]["contract_id"] == "non_bybit_api_allowlist_v1"
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_account_status_does_not_trust_client_state() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_account_status"
        assert params == {}
        return _valid_account_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        resp = client.get(
            "/api/v1/stock-etf/account-status",
            params={
                "phase2_started": "true",
                "account_snapshot_present": "true",
                "first_ibkr_contact_allowed": "true",
            },
            headers={
                "X-Ibkr-Account-Snapshot": "true",
                "X-Ibkr-Session-Attested": "true",
            },
        )
        data = resp.json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert "no-store" in resp.headers["cache-control"]
    assert data["phase2_started"] is False
    assert data["first_ibkr_contact_allowed"] is False
    assert data["account_snapshot_present"] is False
    assert data["portfolio_positions_snapshot_present"] is False
    assert data["session_attestation_present"] is False
    assert data["connector_runtime_started"] is False
    assert data["gateway_socket_open"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_account_status_blocks_contract_violation() -> None:
    payload = _valid_account_status()
    payload["phase2_started"] = True
    payload["asset_lane"] = "crypto_perp"
    payload["broker"] = "bybit"
    payload["environment"] = "paper"
    payload["readonly_account_snapshot_started"] = True
    payload["paper_account_snapshot_started"] = True
    payload["account_snapshot_present"] = True
    payload["portfolio_positions_snapshot_present"] = True
    payload["cash_ledger_present"] = True
    payload["paper_account_attestation_present"] = True
    payload["session_attestation_present"] = True
    payload["connector_runtime_started"] = True
    payload["gateway_socket_open"] = True
    payload["ibkr_call_performed"] = True
    payload["secret_slot_touched"] = True
    payload["order_routed"] = True
    payload["bybit_ipc_reused"] = True
    payload["db_apply_performed"] = True
    payload["account_snapshot"]["expected_contract_id"] = "wrong"
    payload["account_snapshot"]["accepted"] = True
    payload["account_snapshot"]["account_fingerprint_hash_present"] = True
    payload["account_snapshot"]["account_snapshot_hash_present"] = True
    payload["account_snapshot"]["portfolio_positions_hash_present"] = True
    payload["account_snapshot"]["source_report_hash_present"] = True
    payload["account_snapshot"]["as_of_ms"] = 1
    payload["session_attestation"]["expected_contract_id"] = "wrong"
    payload["session_attestation"]["accepted"] = True
    payload["session_attestation"]["account_fingerprint_present"] = True
    payload["session_attestation"]["account_fingerprint_is_live"] = True
    payload["session_attestation"]["process_identity_present"] = True
    payload["session_attestation"]["secret_slot_fingerprint_present"] = True
    payload["session_attestation"]["secret_world_readable"] = True
    payload["session_attestation"]["env_var_credential_fallback_used"] = True
    payload["session_attestation"]["api_server_version_present"] = True
    payload["session_attestation"]["data_tier"] = "delayed"
    payload["session_attestation"]["entitlements_fingerprint_present"] = True
    payload["session_attestation"]["market_data_entitlement_purchase_denied"] = True
    payload["session_attestation"]["gateway_started_at_ms"] = 1
    payload["session_attestation"]["raw_artifact_hash_present"] = True
    payload["session_attestation"]["port"] = 4002
    payload["session_attestation"]["attested_at_ms"] = 1
    payload["session_attestation"]["expires_at_ms"] = 2
    payload["paper_attestation_policy"]["expected_contract_id"] = "wrong"
    payload["paper_attestation_policy"]["paper_environment_only"] = False
    payload["paper_attestation_policy"]["live_account_fingerprint_denied"] = False
    payload["paper_attestation_policy"]["margin_short_options_cfd_denied"] = False
    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(return_value=payload)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/account-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["account_status_state"] == "contract_violation_blocked"
    assert data["degraded"] is True
    assert data["contract_violations"] == EXPECTED_ACCOUNT_CONTRACT_VIOLATIONS
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["environment"] == "paper_readonly"
    assert data["account_snapshot_present"] is False
    assert data["session_attestation_present"] is False
    assert data["connector_runtime_started"] is False
    assert data["gateway_socket_open"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False


def test_stock_etf_account_status_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf/account-status")

    assert resp.status_code == 401


def test_stock_etf_account_contract_violation_assertions_stay_exact() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    source_under_test = source.split(
        "def test_stock_etf_account_contract_violation_assertions_stay_exact",
        1,
    )[0]
    forbidden_patterns = [
        'set(data["contract_violations"])',
        'in data["contract_violations"]',
        'issubset(set(data["contract_violations"]))',
    ]

    for pattern in forbidden_patterns:
        assert pattern not in source_under_test
