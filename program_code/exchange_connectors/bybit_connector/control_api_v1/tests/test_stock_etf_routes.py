"""
Stock/ETF IBKR readiness route and GUI contract tests.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import stock_etf_routes as route_module  # noqa: E402
from app.main_legacy import AuthenticatedActor, current_actor  # noqa: E402
from app.stock_etf_routes import stock_etf_router  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parents[1] / "app" / "static"


def _viewer_actor() -> AuthenticatedActor:
    return AuthenticatedActor(
        actor_id="test-viewer",
        actor_type="human",
        roles={"viewer"},
        scopes={"private_readonly"},
    )


@pytest.fixture
def client_fail_closed() -> TestClient:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    app.dependency_overrides[current_actor] = _viewer_actor
    with patch.object(route_module, "_get_ipc", AsyncMock(return_value=None)):
        yield TestClient(app)


def _make_client_with_ipc(fake_ipc: Any) -> TestClient:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    app.dependency_overrides[current_actor] = _viewer_actor
    patcher = patch.object(route_module, "_get_ipc", AsyncMock(return_value=fake_ipc))
    patcher.start()
    client = TestClient(app)
    client._stock_etf_patcher = patcher  # type: ignore[attr-defined]
    return client


def _valid_api_allowlist() -> dict[str, Any]:
    return {
        "contract_id": "non_bybit_api_allowlist_v1",
        "source_version": 1,
        "accepted": True,
        "blockers": [],
        "read_action_count": 10,
        "paper_write_action_count": 3,
        "denied_action_count": 10,
        "ibkr_contact_performed": False,
        "secret_content_serialized": False,
        "bybit_live_execution_protected": True,
    }


def _valid_lane_status() -> dict[str, Any]:
    return {
        "phase": "phase2_precontact_source_fixture",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "default_asset_lane": "crypto_perp",
        "flags": {
            "stock_etf_lane_enabled": True,
            "ibkr_readonly_enabled": True,
            "ibkr_paper_enabled": False,
            "asset_lane_default": "crypto_perp",
            "stock_etf_shadow_only": True,
        },
        "phase2": {
            "external_surface_gate": {
                "status": "BLOCKED",
                "ibkr_contact_allowed": False,
                "blockers": ["status_not_pass"],
                "ibkr_call_performed": False,
            },
            "api_allowlist": _valid_api_allowlist(),
            "immutable_pass_artifact_present": False,
            "first_ibkr_contact_allowed": False,
            "connector_enabled": False,
        },
        "ibkr_live_enabled": False,
        "ibkr_call_performed": False,
        "secret_slot_touched": False,
        "order_routed": False,
        "bybit_ipc_reused": False,
    }


def _valid_evidence_status() -> dict[str, Any]:
    return {
        "phase": "phase3_evidence_status_source_fixture",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "environment": "paper",
        "evidence_status_state": "blocked",
        "phase3_started": False,
        "market_data_provenance": {
            "expected_contract_id": "stock_market_data_provenance_v1",
            "contract_id": "",
            "source_version": 0,
            "accepted": False,
            "blockers": ["market_data_provenance_contract_id_mismatch"],
            "ibkr_contact_performed": False,
            "connector_runtime_started": False,
            "secret_content_serialized": False,
            "live_or_tiny_live_authorized": False,
        },
        "evidence_clock": {
            "expected_contract_id": "stock_etf_evidence_clock_v1",
            "contract_id": "",
            "source_version": 0,
            "status": "NOT_STARTED",
            "accepted": False,
            "blockers": ["evidence_clock_contract_id_mismatch"],
            "checker_contacted_ibkr": False,
            "checker_started_connector_runtime": False,
            "checker_started_evidence_clock": False,
            "checker_wrote_scorecard": False,
            "checker_applied_db": False,
            "secret_content_serialized": False,
            "live_or_tiny_live_authorized": False,
            "ibkr_readonly_paper_connector_green_5d": False,
            "shadow_collector_green_5d": False,
        },
        "frozen_inputs": {
            "accepted": False,
            "blockers": ["frozen_inputs_contract_id_mismatch"],
            "universe_hash_present": False,
            "benchmark_hash_present": False,
            "cost_model_hash_present": False,
            "strategy_hypothesis_hash_present": False,
            "reference_data_sources_contract_hash_present": False,
            "paper_shadow_divergence_threshold_hash_present": False,
            "gui_evidence_view_available": False,
            "daily_scorecard_regeneration_passed": False,
        },
        "dq_manifest": {
            "shape_accepted": False,
            "shape_blockers": ["trading_day_missing"],
            "passes_day_quality": False,
            "trading_day": "",
            "calendar_aware_coverage_bps": 0,
            "symbol_completeness_bps": 0,
            "latency_dq_passed": False,
            "market_data_provenance_accepted": False,
            "scorecard_regeneration_passed": False,
        },
        "scorecard": {
            "writer_started": False,
            "db_apply_performed": False,
            "daily_scorecard_regeneration_passed": False,
        },
        "phase2": {
            "external_surface_gate": {
                "status": "BLOCKED",
                "ibkr_contact_allowed": False,
                "blockers": ["status_not_pass"],
                "ibkr_call_performed": False,
            },
            "api_allowlist": _valid_api_allowlist(),
            "immutable_pass_artifact_present": False,
            "first_ibkr_contact_allowed": False,
            "connector_enabled": False,
            "secret_slot_touched": False,
            "order_routed": False,
        },
        "ibkr_live_enabled": False,
        "ibkr_call_performed": False,
        "secret_slot_touched": False,
        "order_routed": False,
        "bybit_ipc_reused": False,
    }


def _valid_universe_status() -> dict[str, Any]:
    return {
        "phase": "phase3_universe_status_source_fixture",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "environment": "paper",
        "universe_status_state": "blocked",
        "phase3_started": False,
        "universe": {
            "expected_contract_id": "stock_etf_pit_universe_contract_v1",
            "contract_id": "",
            "source_version": 0,
            "accepted": False,
            "blockers": ["contract_id_mismatch", "source_version_mismatch"],
            "universe_id": "",
            "universe_version": "",
            "universe_hash_present": False,
            "point_in_time_asof_ms": 0,
            "effective_from_ms": 0,
            "effective_to_ms": 0,
            "constituent_count": 0,
            "max_constituents": 0,
            "sample_constituents": [],
            "frozen_for_evidence_clock": False,
            "survivorship_bias_controls_present": False,
            "bybit_live_execution_unchanged": True,
            "ibkr_live_denied": True,
            "ibkr_contact_performed": False,
            "secret_content_serialized": False,
        },
        "phase2": {
            "external_surface_gate": {
                "status": "BLOCKED",
                "ibkr_contact_allowed": False,
                "blockers": ["status_not_pass"],
                "ibkr_call_performed": False,
            },
            "api_allowlist": _valid_api_allowlist(),
            "immutable_pass_artifact_present": False,
            "first_ibkr_contact_allowed": False,
            "connector_enabled": False,
            "secret_slot_touched": False,
            "order_routed": False,
        },
        "collector_started": False,
        "market_data_ingestion_started": False,
        "db_apply_performed": False,
        "ibkr_live_enabled": False,
        "ibkr_call_performed": False,
        "secret_slot_touched": False,
        "order_routed": False,
        "bybit_ipc_reused": False,
    }


def _valid_shadow_status() -> dict[str, Any]:
    return {
        "phase": "phase3_shadow_status_source_fixture",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "environment": "shadow",
        "shadow_status_state": "blocked",
        "phase3_started": False,
        "shadow_fill_model": {
            "expected_contract_id": "stock_shadow_fill_model_v1",
            "contract_id": "",
            "source_version": 0,
            "accepted": False,
            "blockers": ["contract_id_mismatch", "source_version_mismatch"],
            "signal_id": "",
            "side": "unknown",
            "intended_notional_minor_units": 0,
            "market_session_id": "",
            "quote_or_bar_source_hash_present": False,
            "conservative_fill_price_micros": 0,
            "spread_bps": 0,
            "slippage_bps": 0,
            "cost_bps": 0,
            "rejection_reason": "",
            "synthetic_shadow": False,
            "broker_paper_fill_linked": False,
            "live_fill_linked": False,
        },
        "strategy_hypothesis": {
            "expected_contract_id": "stock_etf_strategy_hypothesis_contract_v1",
            "contract_id": "",
            "source_version": 0,
            "accepted": False,
            "blockers": ["contract_id_mismatch", "source_version_mismatch"],
            "hypothesis_id": "",
            "hypothesis_version": "",
            "strategy_family": "unknown_denied",
            "primary_timeframe": "unknown_denied",
            "instrument_scope": "unknown_denied",
            "paper_shadow_only": True,
            "profitability_claimed": False,
            "live_or_tiny_live_authority_claimed": False,
            "bybit_live_execution_unchanged": True,
            "ibkr_live_denied": True,
            "ibkr_contact_performed": False,
            "secret_content_serialized": False,
        },
        "phase2": {
            "external_surface_gate": {
                "status": "BLOCKED",
                "ibkr_contact_allowed": False,
                "blockers": ["status_not_pass"],
                "ibkr_call_performed": False,
            },
            "api_allowlist": _valid_api_allowlist(),
            "immutable_pass_artifact_present": False,
            "first_ibkr_contact_allowed": False,
            "connector_enabled": False,
            "secret_slot_touched": False,
            "order_routed": False,
        },
        "shadow_collector_started": False,
        "shadow_signal_emitted": False,
        "shadow_fill_generated": False,
        "scorecard_writer_started": False,
        "db_apply_performed": False,
        "ibkr_live_enabled": False,
        "ibkr_call_performed": False,
        "secret_slot_touched": False,
        "order_routed": False,
        "bybit_ipc_reused": False,
    }


def _valid_paper_status() -> dict[str, Any]:
    return {
        "phase": "phase2_paper_status_source_fixture",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "environment": "paper",
        "paper_status_state": "blocked",
        "phase2_started": False,
        "paper_lifecycle_started": False,
        "paper_order_submitted": False,
        "paper_fill_imported": False,
        "paper_reconciliation_started": False,
        "paper_account_snapshot_present": False,
        "broker_paper_attestation_present": False,
        "lifecycle_event": {
            "expected_lifecycle_contract_id": "ibkr_paper_order_lifecycle_v1",
            "lifecycle_contract_id": "",
            "expected_event_log_contract_id": "broker_lifecycle_event_log_v1",
            "event_log_contract_id": "",
            "source_version": 0,
            "accepted": False,
            "blockers": [
                "lifecycle_contract_id_mismatch",
                "event_log_contract_id_mismatch",
                "source_version_mismatch",
            ],
            "operation": "paper_order_submit",
            "previous_state": "local_intent_created",
            "next_state": "local_intent_created",
            "allowed": False,
            "denial_reason": "",
            "event_id_present": False,
            "event_time_ms": 0,
            "order_local_id_present": False,
            "idempotency_key_present": False,
            "broker_order_id_present": False,
            "execution_id_present": False,
            "commission_report_id_present": False,
            "reconciliation_run_id_present": False,
            "raw_artifact_hash_present": False,
            "redacted_summary_hash_present": False,
        },
        "reconstructability": {
            "append_only_event_ready": False,
            "broker_order_id_present": False,
            "execution_id_present": False,
            "commission_report_id_present": False,
            "raw_artifact_hash_present": False,
            "redacted_summary_hash_present": False,
            "restart_recovery_required": False,
            "manual_review_required": False,
        },
        "phase2": {
            "external_surface_gate": {
                "status": "BLOCKED",
                "ibkr_contact_allowed": False,
                "blockers": ["status_not_pass"],
                "ibkr_call_performed": False,
            },
            "api_allowlist": _valid_api_allowlist(),
            "immutable_pass_artifact_present": False,
            "first_ibkr_contact_allowed": False,
            "connector_enabled": False,
            "secret_slot_touched": False,
            "order_routed": False,
        },
        "ibkr_live_enabled": False,
        "ibkr_call_performed": False,
        "secret_slot_touched": False,
        "order_routed": False,
        "bybit_ipc_reused": False,
        "db_apply_performed": False,
    }


def test_stock_etf_lane_status_returns_200_when_ipc_down(client_fail_closed: TestClient) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf/lane-status")
    assert resp.status_code == 200
    assert "no-store" in resp.headers["cache-control"]
    assert "private" in resp.headers["cache-control"]
    assert resp.headers["vary"] == "Authorization"
    body = resp.json()
    data = body["data"]
    assert body["ok"] is True
    assert body["data_category"] == "stock_etf_lane_status"
    assert data["degraded"] is True
    assert data["reason"] == "ipc_unavailable"
    assert data["lane_status_state"] == "degraded"
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["default_asset_lane"] == "crypto_perp"
    assert data["gui_authority"] == "display_only"
    assert data["flags"]["stock_etf_lane_enabled"] is False
    assert data["flags"]["ibkr_readonly_enabled"] is False
    assert data["flags"]["ibkr_paper_enabled"] is False
    assert data["flags"]["stock_etf_shadow_only"] is True
    assert data["first_ibkr_contact_allowed"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False


def test_stock_etf_lane_status_uses_only_readonly_fixture_method() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_lane_status"
        assert params == {}
        return _valid_lane_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/lane-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["degraded"] is False
    assert data["lane_status_state"] == "phase2_blocked"
    assert data["flags"]["stock_etf_lane_enabled"] is True
    assert data["flags"]["ibkr_readonly_enabled"] is True
    assert data["flags"]["ibkr_paper_enabled"] is False
    assert data["flags"]["stock_etf_shadow_only"] is True
    assert data["api_allowlist"]["contract_id"] == "non_bybit_api_allowlist_v1"
    assert data["allowed_gui_actions"] == ["refresh_lane_status", "refresh_readiness"]
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_lane_status_does_not_trust_client_lane_state() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_lane_status"
        assert params == {}
        return _valid_lane_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        resp = client.get(
            "/api/v1/stock-etf/lane-status",
            params={
                "default_asset_lane": "stock_etf_cash",
                "ibkr_paper_enabled": "true",
                "first_ibkr_contact_allowed": "true",
            },
            headers={"X-Asset-Lane": "stock_etf_cash", "X-Ibkr-Paper-Ready": "true"},
        )
        data = resp.json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert "no-store" in resp.headers["cache-control"]
    assert data["default_asset_lane"] == "crypto_perp"
    assert data["flags"]["asset_lane_default"] == "crypto_perp"
    assert data["flags"]["ibkr_paper_enabled"] is False
    assert data["first_ibkr_contact_allowed"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_lane_status_blocks_contract_violation() -> None:
    payload = _valid_lane_status()
    payload["asset_lane"] = "crypto_perp"
    payload["broker"] = "bybit"
    payload["ibkr_call_performed"] = True
    payload["secret_slot_touched"] = True
    payload["order_routed"] = True
    payload["bybit_ipc_reused"] = True
    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(return_value=payload)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/lane-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["lane_status_state"] == "contract_violation_blocked"
    assert data["degraded"] is True
    assert set(data["contract_violations"]) == {
        "ibkr_call_performed",
        "secret_slot_touched",
        "order_routed",
        "bybit_ipc_reused",
        "asset_lane_mismatch",
        "broker_mismatch",
    }
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["paper_order_entry_visible"] is False


def test_stock_etf_readiness_returns_200_when_ipc_down(client_fail_closed: TestClient) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf/readiness")
    assert resp.status_code == 200
    assert "no-store" in resp.headers["cache-control"]
    assert "private" in resp.headers["cache-control"]
    assert resp.headers["pragma"] == "no-cache"
    assert resp.headers["expires"] == "0"
    assert resp.headers["vary"] == "Authorization"
    body = resp.json()
    data = body["data"]
    assert body["ok"] is True
    assert body["data_category"] == "stock_etf_readiness"
    assert data["degraded"] is True
    assert data["reason"] == "ipc_unavailable"
    assert data["readiness_state"] == "degraded"
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["default_asset_lane"] == "crypto_perp"
    assert data["gui_authority"] == "display_only"
    assert data["stock_live_disabled"] is True
    assert data["first_ibkr_contact_allowed"] is False
    assert data["immutable_pass_artifact_present"] is False
    assert data["connector_enabled"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False


def test_stock_etf_readiness_uses_only_readonly_fixture_method() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_readiness"
        assert params == {}
        return {
            "phase": "phase2_precontact_source_fixture",
            "readiness": {
                "asset_lane": "stock_etf_cash",
                "broker": "ibkr",
                "default_asset_lane": "crypto_perp",
                "readonly_ready": True,
                "paper_ready": False,
                "shadow_only": True,
                "live_denied": True,
                "denial_reasons": ["shadow_only"],
            },
            "phase2": {
                "external_surface_gate": {
                    "status": "BLOCKED",
                    "ibkr_contact_allowed": False,
                    "blockers": ["status_not_pass"],
                    "ibkr_call_performed": False,
                },
                "api_allowlist": _valid_api_allowlist(),
                "policy_prerequisites": {
                    "bundle_accepted": True,
                    "blockers": [],
                    "flags": {"python_no_write_guard_present": True},
                },
                "immutable_pass_artifact_present": False,
                "first_ibkr_contact_allowed": False,
                "connector_enabled": False,
                "secret_slot_touched": False,
                "order_routed": False,
            },
            "ibkr_live_enabled": False,
            "ibkr_call_performed": False,
            "secret_slot_touched": False,
            "order_routed": False,
            "bybit_ipc_reused": False,
        }

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/readiness").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["degraded"] is False
    assert data["readiness_state"] == "phase2_blocked"
    assert data["source_readiness"]["readonly_ready"] is True
    assert data["source_readiness"]["paper_ready"] is False
    assert data["source_readiness"]["live_denied"] is True
    assert data["phase2_gate_status"] == "BLOCKED"
    assert data["phase2_gate_blockers"] == ["status_not_pass"]
    assert data["api_allowlist"]["contract_id"] == "non_bybit_api_allowlist_v1"
    assert data["api_allowlist"]["source_version"] == 1
    assert data["api_allowlist"]["accepted"] is True
    assert data["api_allowlist"]["read_action_count"] == 10
    assert data["api_allowlist"]["paper_write_action_count"] == 3
    assert data["api_allowlist"]["denied_action_count"] == 10
    assert "ibkr_live_order_submit" in data["denied_operations"]
    assert "ibkr_secret_slot_creation" in data["denied_operations"]
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_readiness_does_not_trust_client_lane_state() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_readiness"
        assert params == {}
        return {
            "readiness": {
                "asset_lane": "stock_etf_cash",
                "broker": "ibkr",
                "default_asset_lane": "crypto_perp",
                "readonly_ready": True,
                "paper_ready": False,
                "shadow_only": True,
                "live_denied": True,
                "denial_reasons": ["shadow_only"],
            },
            "phase2": {
                "external_surface_gate": {
                    "status": "BLOCKED",
                    "ibkr_contact_allowed": False,
                    "blockers": ["status_not_pass"],
                    "ibkr_call_performed": False,
                },
                "api_allowlist": _valid_api_allowlist(),
                "immutable_pass_artifact_present": False,
                "first_ibkr_contact_allowed": False,
                "connector_enabled": False,
            },
            "ibkr_live_enabled": False,
            "ibkr_call_performed": False,
            "secret_slot_touched": False,
            "order_routed": False,
            "bybit_ipc_reused": False,
        }

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        resp = client.get(
            "/api/v1/stock-etf/readiness",
            params={
                "default_asset_lane": "stock_etf_cash",
                "paper_ready": "true",
                "first_ibkr_contact_allowed": "true",
            },
            headers={"X-Asset-Lane": "stock_etf_cash", "X-Ibkr-Paper-Ready": "true"},
        )
        data = resp.json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert "no-store" in resp.headers["cache-control"]
    assert data["default_asset_lane"] == "crypto_perp"
    assert data["source_readiness"]["paper_ready"] is False
    assert data["first_ibkr_contact_allowed"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_readiness_blocks_contract_violation() -> None:
    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(
        return_value={
            "readiness": {
                "asset_lane": "stock_etf_cash",
                "broker": "ibkr",
                "default_asset_lane": "stock_etf_cash",
                "readonly_ready": True,
                "paper_ready": True,
                "shadow_only": False,
                "live_denied": True,
                "denial_reasons": [],
            },
            "phase2": {
                "external_surface_gate": {
                    "status": "PASS",
                    "ibkr_contact_allowed": True,
                    "blockers": [],
                },
                "api_allowlist": _valid_api_allowlist(),
                "immutable_pass_artifact_present": True,
                "first_ibkr_contact_allowed": True,
                "connector_enabled": True,
            },
            "ibkr_call_performed": True,
            "secret_slot_touched": True,
            "order_routed": True,
            "bybit_ipc_reused": True,
        }
    )
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/readiness").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["readiness_state"] == "contract_violation_blocked"
    assert data["degraded"] is True
    assert set(data["contract_violations"]) == {
        "ibkr_call_performed",
        "secret_slot_touched",
        "order_routed",
        "bybit_ipc_reused",
    }
    assert data["ibkr_live_enabled"] is False
    assert data["stock_live_disabled"] is True
    assert data["paper_order_entry_visible"] is False


def test_stock_etf_readiness_blocks_missing_api_allowlist_contract() -> None:
    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(
        return_value={
            "readiness": {
                "asset_lane": "stock_etf_cash",
                "broker": "ibkr",
                "default_asset_lane": "crypto_perp",
                "readonly_ready": True,
                "paper_ready": False,
                "shadow_only": True,
                "live_denied": True,
                "denial_reasons": [],
            },
            "phase2": {
                "external_surface_gate": {
                    "status": "BLOCKED",
                    "ibkr_contact_allowed": False,
                    "blockers": ["status_not_pass"],
                    "ibkr_call_performed": False,
                },
                "immutable_pass_artifact_present": False,
                "first_ibkr_contact_allowed": False,
                "connector_enabled": False,
            },
            "ibkr_live_enabled": False,
            "ibkr_call_performed": False,
            "secret_slot_touched": False,
            "order_routed": False,
            "bybit_ipc_reused": False,
        }
    )
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/readiness").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["readiness_state"] == "contract_violation_blocked"
    assert data["degraded"] is True
    assert data["api_allowlist"]["accepted"] is False
    assert "api_allowlist_not_accepted" in data["contract_violations"]
    assert "api_allowlist_contract_id_mismatch" in data["contract_violations"]
    assert "api_allowlist_source_version_mismatch" in data["contract_violations"]


def test_stock_etf_readiness_rejects_boolean_api_allowlist_version() -> None:
    api_allowlist = _valid_api_allowlist()
    api_allowlist["source_version"] = True
    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(
        return_value={
            "readiness": {
                "asset_lane": "stock_etf_cash",
                "broker": "ibkr",
                "default_asset_lane": "crypto_perp",
                "readonly_ready": True,
                "paper_ready": False,
                "shadow_only": True,
                "live_denied": True,
                "denial_reasons": [],
            },
            "phase2": {
                "external_surface_gate": {
                    "status": "BLOCKED",
                    "ibkr_contact_allowed": False,
                    "blockers": ["status_not_pass"],
                    "ibkr_call_performed": False,
                },
                "api_allowlist": api_allowlist,
                "immutable_pass_artifact_present": False,
                "first_ibkr_contact_allowed": False,
                "connector_enabled": False,
            },
            "ibkr_live_enabled": False,
            "ibkr_call_performed": False,
            "secret_slot_touched": False,
            "order_routed": False,
            "bybit_ipc_reused": False,
        }
    )
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/readiness").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["readiness_state"] == "contract_violation_blocked"
    assert data["api_allowlist"]["source_version"] == 0
    assert "api_allowlist_source_version_mismatch" in data["contract_violations"]


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
    assert data["evidence_clock"]["status"] == "NOT_STARTED"
    assert data["evidence_clock"]["blockers"] == ["ipc_unavailable"]
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
    assert data["evidence_clock"]["expected_contract_id"] == (
        "stock_etf_evidence_clock_v1"
    )
    assert data["evidence_clock"]["status"] == "NOT_STARTED"
    assert data["frozen_inputs"]["gui_evidence_view_available"] is False
    assert data["dq_manifest"]["passes_day_quality"] is False
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
    payload["evidence_clock"]["checker_contacted_ibkr"] = True
    payload["evidence_clock"]["checker_started_connector_runtime"] = True
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
    assert {
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
    }.issubset(set(data["contract_violations"]))
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


def test_stock_etf_universe_status_returns_200_when_ipc_down(
    client_fail_closed: TestClient,
) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf/universe-status")
    assert resp.status_code == 200
    assert "no-store" in resp.headers["cache-control"]
    assert "private" in resp.headers["cache-control"]
    assert resp.headers["pragma"] == "no-cache"
    assert resp.headers["expires"] == "0"
    assert resp.headers["vary"] == "Authorization"
    body = resp.json()
    data = body["data"]
    assert body["ok"] is True
    assert body["data_category"] == "stock_etf_universe_status"
    assert data["degraded"] is True
    assert data["reason"] == "ipc_unavailable"
    assert data["universe_status_state"] == "degraded"
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
    assert data["collector_started"] is False
    assert data["market_data_ingestion_started"] is False
    assert data["db_apply_performed"] is False
    assert data["universe"]["blockers"] == ["ipc_unavailable"]
    assert data["universe"]["bybit_live_execution_unchanged"] is True
    assert data["universe"]["ibkr_live_denied"] is True


def test_stock_etf_universe_status_uses_only_readonly_fixture_method() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_universe_status"
        assert params == {}
        return _valid_universe_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/universe-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["degraded"] is False
    assert data["universe_status_state"] == "blocked"
    assert data["phase"] == "phase3_universe_status_source_fixture"
    assert data["phase3_started"] is False
    assert data["universe"]["expected_contract_id"] == (
        "stock_etf_pit_universe_contract_v1"
    )
    assert data["universe"]["accepted"] is False
    assert data["universe"]["universe_hash_present"] is False
    assert data["universe"]["constituent_count"] == 0
    assert data["universe"]["sample_constituents"] == []
    assert data["allowed_gui_actions"] == ["refresh_universe_status"]
    assert data["api_allowlist"]["contract_id"] == "non_bybit_api_allowlist_v1"
    assert data["collector_started"] is False
    assert data["market_data_ingestion_started"] is False
    assert data["db_apply_performed"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_universe_status_does_not_trust_client_state() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_universe_status"
        assert params == {}
        return _valid_universe_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        resp = client.get(
            "/api/v1/stock-etf/universe-status",
            params={
                "phase3_started": "true",
                "collector_started": "true",
                "first_ibkr_contact_allowed": "true",
            },
            headers={
                "X-Ibkr-Phase3-Started": "true",
                "X-Collector-Started": "true",
            },
        )
        data = resp.json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert "no-store" in resp.headers["cache-control"]
    assert data["phase3_started"] is False
    assert data["first_ibkr_contact_allowed"] is False
    assert data["collector_started"] is False
    assert data["market_data_ingestion_started"] is False
    assert data["db_apply_performed"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_universe_status_blocks_contract_violation() -> None:
    payload = _valid_universe_status()
    payload["phase3_started"] = True
    payload["asset_lane"] = "crypto_perp"
    payload["broker"] = "bybit"
    payload["environment"] = "live"
    payload["collector_started"] = True
    payload["market_data_ingestion_started"] = True
    payload["db_apply_performed"] = True
    payload["ibkr_call_performed"] = True
    payload["secret_slot_touched"] = True
    payload["order_routed"] = True
    payload["bybit_ipc_reused"] = True
    payload["universe"]["expected_contract_id"] = "wrong"
    payload["universe"]["ibkr_contact_performed"] = True
    payload["universe"]["secret_content_serialized"] = True
    payload["universe"]["bybit_live_execution_unchanged"] = False
    payload["universe"]["ibkr_live_denied"] = False
    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(return_value=payload)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/universe-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["universe_status_state"] == "contract_violation_blocked"
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
        "collector_started",
        "market_data_ingestion_started",
        "db_apply_performed",
        "universe_expected_contract_id_mismatch",
        "universe_ibkr_contact_performed",
        "universe_secret_content_serialized",
        "universe_bybit_live_not_protected",
        "universe_ibkr_live_not_denied",
    }.issubset(set(data["contract_violations"]))
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["environment"] == "paper"
    assert data["phase3_started"] is False
    assert data["collector_started"] is False
    assert data["market_data_ingestion_started"] is False
    assert data["db_apply_performed"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False


def test_stock_etf_universe_status_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf/universe-status")

    assert resp.status_code == 401


def test_stock_etf_shadow_status_returns_200_when_ipc_down(
    client_fail_closed: TestClient,
) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf/shadow-status")
    assert resp.status_code == 200
    assert "no-store" in resp.headers["cache-control"]
    assert "private" in resp.headers["cache-control"]
    assert resp.headers["pragma"] == "no-cache"
    assert resp.headers["expires"] == "0"
    assert resp.headers["vary"] == "Authorization"
    body = resp.json()
    data = body["data"]
    assert body["ok"] is True
    assert body["data_category"] == "stock_etf_shadow_status"
    assert data["degraded"] is True
    assert data["reason"] == "ipc_unavailable"
    assert data["shadow_status_state"] == "degraded"
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["environment"] == "shadow"
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
    assert data["shadow_collector_started"] is False
    assert data["shadow_signal_emitted"] is False
    assert data["shadow_fill_generated"] is False
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    assert data["shadow_fill_model"]["blockers"] == ["ipc_unavailable"]
    assert data["shadow_fill_model"]["broker_paper_fill_linked"] is False
    assert data["shadow_fill_model"]["live_fill_linked"] is False
    assert data["strategy_hypothesis"]["paper_shadow_only"] is True
    assert data["strategy_hypothesis"]["profitability_claimed"] is False
    assert data["strategy_hypothesis"]["live_or_tiny_live_authority_claimed"] is False


def test_stock_etf_shadow_status_uses_only_readonly_fixture_method() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_shadow_status"
        assert params == {}
        return _valid_shadow_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/shadow-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["degraded"] is False
    assert data["shadow_status_state"] == "blocked"
    assert data["phase"] == "phase3_shadow_status_source_fixture"
    assert data["phase3_started"] is False
    assert data["shadow_fill_model"]["expected_contract_id"] == (
        "stock_shadow_fill_model_v1"
    )
    assert data["shadow_fill_model"]["accepted"] is False
    assert data["shadow_fill_model"]["synthetic_shadow"] is False
    assert data["shadow_fill_model"]["broker_paper_fill_linked"] is False
    assert data["shadow_fill_model"]["live_fill_linked"] is False
    assert data["strategy_hypothesis"]["expected_contract_id"] == (
        "stock_etf_strategy_hypothesis_contract_v1"
    )
    assert data["strategy_hypothesis"]["accepted"] is False
    assert data["strategy_hypothesis"]["paper_shadow_only"] is True
    assert data["allowed_gui_actions"] == ["refresh_shadow_status"]
    assert data["api_allowlist"]["contract_id"] == "non_bybit_api_allowlist_v1"
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_shadow_status_does_not_trust_client_state() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_shadow_status"
        assert params == {}
        return _valid_shadow_status()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        resp = client.get(
            "/api/v1/stock-etf/shadow-status",
            params={
                "phase3_started": "true",
                "shadow_fill_generated": "true",
                "first_ibkr_contact_allowed": "true",
            },
            headers={
                "X-Ibkr-Phase3-Started": "true",
                "X-Shadow-Fill-Generated": "true",
            },
        )
        data = resp.json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert "no-store" in resp.headers["cache-control"]
    assert data["phase3_started"] is False
    assert data["first_ibkr_contact_allowed"] is False
    assert data["shadow_collector_started"] is False
    assert data["shadow_signal_emitted"] is False
    assert data["shadow_fill_generated"] is False
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_shadow_status_blocks_contract_violation() -> None:
    payload = _valid_shadow_status()
    payload["phase3_started"] = True
    payload["asset_lane"] = "crypto_perp"
    payload["broker"] = "bybit"
    payload["environment"] = "paper"
    payload["shadow_collector_started"] = True
    payload["shadow_signal_emitted"] = True
    payload["shadow_fill_generated"] = True
    payload["scorecard_writer_started"] = True
    payload["db_apply_performed"] = True
    payload["ibkr_call_performed"] = True
    payload["secret_slot_touched"] = True
    payload["order_routed"] = True
    payload["bybit_ipc_reused"] = True
    payload["shadow_fill_model"]["expected_contract_id"] = "wrong"
    payload["shadow_fill_model"]["broker_paper_fill_linked"] = True
    payload["shadow_fill_model"]["live_fill_linked"] = True
    payload["strategy_hypothesis"]["expected_contract_id"] = "wrong"
    payload["strategy_hypothesis"]["paper_shadow_only"] = False
    payload["strategy_hypothesis"]["profitability_claimed"] = True
    payload["strategy_hypothesis"]["live_or_tiny_live_authority_claimed"] = True
    payload["strategy_hypothesis"]["bybit_live_execution_unchanged"] = False
    payload["strategy_hypothesis"]["ibkr_live_denied"] = False
    payload["strategy_hypothesis"]["ibkr_contact_performed"] = True
    payload["strategy_hypothesis"]["secret_content_serialized"] = True
    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(return_value=payload)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/shadow-status").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["shadow_status_state"] == "contract_violation_blocked"
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
        "shadow_collector_started",
        "shadow_signal_emitted",
        "shadow_fill_generated",
        "scorecard_writer_started",
        "db_apply_performed",
        "shadow_fill_expected_contract_id_mismatch",
        "shadow_fill_linked_to_broker_paper_fill",
        "shadow_fill_linked_to_live_fill",
        "strategy_expected_contract_id_mismatch",
        "strategy_not_paper_shadow_only",
        "strategy_profitability_claimed",
        "strategy_live_or_tiny_live_authority_claimed",
        "strategy_bybit_live_not_protected",
        "strategy_ibkr_live_not_denied",
        "strategy_ibkr_contact_performed",
        "strategy_secret_content_serialized",
    }.issubset(set(data["contract_violations"]))
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["environment"] == "shadow"
    assert data["phase3_started"] is False
    assert data["shadow_collector_started"] is False
    assert data["shadow_signal_emitted"] is False
    assert data["shadow_fill_generated"] is False
    assert data["scorecard_writer_started"] is False
    assert data["db_apply_performed"] is False
    assert data["paper_order_entry_visible"] is False
    assert data["ibkr_live_enabled"] is False
    assert data["ibkr_call_performed"] is False
    assert data["secret_slot_touched"] is False
    assert data["order_routed"] is False
    assert data["bybit_ipc_reused"] is False


def test_stock_etf_shadow_status_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf/shadow-status")

    assert resp.status_code == 401


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


def test_stock_etf_evidence_status_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf/evidence-status")

    assert resp.status_code == 401


def test_stock_etf_readiness_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf/readiness")

    assert resp.status_code == 401


def test_stock_etf_lane_status_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf/lane-status")

    assert resp.status_code == 401


def test_stock_etf_redirect_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf", follow_redirects=False)

    assert resp.status_code == 401


def test_stock_etf_openapi_exposes_stock_etf_get_only(client_fail_closed: TestClient) -> None:
    schema = client_fail_closed.get("/openapi.json").json()
    stock_paths = {
        path: set(methods)
        for path, methods in schema["paths"].items()
        if path.startswith("/api/v1/stock-etf")
    }

    assert stock_paths == {
        "/api/v1/stock-etf/evidence-status": {"get"},
        "/api/v1/stock-etf/lane-status": {"get"},
        "/api/v1/stock-etf/paper-status": {"get"},
        "/api/v1/stock-etf/readiness": {"get"},
        "/api/v1/stock-etf/shadow-status": {"get"},
        "/api/v1/stock-etf/universe-status": {"get"},
    }


def test_stock_etf_runtime_rejects_write_methods(client_fail_closed: TestClient) -> None:
    for path in (
        "/api/v1/stock-etf",
        "/api/v1/stock-etf/evidence-status",
        "/api/v1/stock-etf/lane-status",
        "/api/v1/stock-etf/paper-status",
        "/api/v1/stock-etf/readiness",
        "/api/v1/stock-etf/shadow-status",
        "/api/v1/stock-etf/universe-status",
    ):
        for method in ("post", "put", "patch", "delete"):
            resp = getattr(client_fail_closed, method)(path)
            assert resp.status_code == 405, f"{method.upper()} {path} returned {resp.status_code}"


def test_stock_etf_redirect_to_static_tab(client_fail_closed: TestClient) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "/static/tab-stock-etf.html" in resp.headers.get("location", "")
    assert "no-store" in resp.headers["cache-control"]
    assert resp.headers["vary"] == "Authorization"


def test_stock_etf_console_tab_registered() -> None:
    console = (STATIC_DIR / "console.html").read_text(encoding="utf-8")
    assert "id: 'stock-etf'" in console
    assert "tab-stock-etf.html" in console
    assert "lane crypto_perp" in console
    assert "login_success" not in console


def test_stock_etf_router_registered_in_main_app() -> None:
    main_source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(
        encoding="utf-8"
    )
    assert "from .stock_etf_routes import stock_etf_router" in main_source
    assert "app.include_router(stock_etf_router)" in main_source


def test_stock_etf_static_tab_is_readonly_display_only() -> None:
    source = (STATIC_DIR / "tab-stock-etf.html").read_text(encoding="utf-8")
    assert "/api/v1/stock-etf/evidence-status" in source
    assert "/api/v1/stock-etf/lane-status" in source
    assert "/api/v1/stock-etf/paper-status" in source
    assert "/api/v1/stock-etf/readiness" in source
    assert "/api/v1/stock-etf/shadow-status" in source
    assert "/api/v1/stock-etf/universe-status" in source
    assert "se-evidence-status" in source
    assert "se-evidence-body" in source
    assert "se-shadow-status" in source
    assert "se-shadow-body" in source
    assert "se-paper-status" in source
    assert "se-paper-body" in source
    assert "se-universe-status" in source
    assert "se-universe-body" in source
    assert "api_allowlist" in source
    assert "se-api-allowlist-status" in source
    assert "se-api-allowlist-body" in source
    assert "ocPost(" not in source
    assert "method: 'POST'" not in source
    assert "method: \"POST\"" not in source
    assert "stock_etf.submit_paper_order" not in source
    assert "stock_etf.cancel_paper_order" not in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source
