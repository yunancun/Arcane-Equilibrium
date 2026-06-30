"""Shared fixtures and payload builders for Stock/ETF route tests."""

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


def _valid_account_status() -> dict[str, Any]:
    return {
        "phase": "phase2_account_status_source_fixture",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "environment": "paper_readonly",
        "account_status_state": "blocked",
        "phase2_started": False,
        "readonly_account_snapshot_started": False,
        "paper_account_snapshot_started": False,
        "account_snapshot_present": False,
        "portfolio_positions_snapshot_present": False,
        "cash_ledger_present": False,
        "paper_account_attestation_present": False,
        "session_attestation_present": False,
        "connector_runtime_started": False,
        "gateway_socket_open": False,
        "account_snapshot": {
            "expected_contract_id": "broker_account_portfolio_cash_ledger_v1",
            "contract_id": "",
            "source_version": 0,
            "accepted": False,
            "blockers": [
                "contract_id_mismatch",
                "source_version_mismatch",
                "wrong_asset_lane",
            ],
            "account_fingerprint_hash_present": False,
            "account_snapshot_hash_present": False,
            "portfolio_positions_hash_present": False,
            "currency": "",
            "cash_balance_minor_units": 0,
            "buying_power_minor_units": 0,
            "as_of_ms": 0,
            "source_report_hash_present": False,
        },
        "session_attestation": {
            "expected_contract_id": "ibkr_session_attestation_v1",
            "contract_id": "",
            "source_version": 0,
            "status": "BLOCKED",
            "accepted": False,
            "blockers": [
                "contract_id_mismatch",
                "source_version_mismatch",
                "status_blocked",
            ],
            "account_fingerprint_present": False,
            "account_fingerprint_is_live": False,
            "environment": "read_only",
            "host": "",
            "port": 0,
            "process_identity_present": False,
            "gateway_mode": "unknown",
            "secret_slot_fingerprint_present": False,
            "secret_slot_mode": "unknown",
            "secret_world_readable": False,
            "live_secret_absent_or_empty": False,
            "env_var_credential_fallback_used": False,
            "api_server_version_present": False,
            "attested_at_ms": 0,
            "expires_at_ms": 0,
            "raw_artifact_hash_present": False,
        },
        "paper_attestation_policy": {
            "expected_contract_id": "ibkr_paper_attestation_v1",
            "contract_id": "ibkr_paper_attestation_v1",
            "source_version": 1,
            "accepted": True,
            "blockers": [],
            "external_surface_gate_required": True,
            "session_attestation_required": True,
            "rust_lane_scoped_ipc_required": True,
            "decision_lease_required": True,
            "guardian_required": True,
            "paper_environment_only": True,
            "live_account_fingerprint_denied": True,
            "margin_short_options_cfd_denied": True,
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


def _valid_reconciliation_status() -> dict[str, Any]:
    return {
        "phase": "phase3_reconciliation_status_source_fixture",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "environment": "paper_shadow",
        "reconciliation_status_state": "blocked",
        "phase3_started": False,
        "paper_shadow_reconciliation_started": False,
        "paper_orders_ready": False,
        "paper_fills_ready": False,
        "shadow_fills_ready": False,
        "scorecard_writer_started": False,
        "db_apply_performed": False,
        "matching": {
            "expected_lifecycle_contract_id": "ibkr_paper_order_lifecycle_v1",
            "lifecycle_contract_id": "",
            "expected_event_log_contract_id": "broker_lifecycle_event_log_v1",
            "event_log_contract_id": "",
            "expected_shadow_contract_id": "stock_shadow_fill_model_v1",
            "shadow_contract_id": "",
            "lifecycle_event_accepted": False,
            "shadow_fill_model_accepted": False,
            "lifecycle_blockers": [
                "lifecycle_contract_id_mismatch",
                "event_log_contract_id_mismatch",
                "source_version_mismatch",
            ],
            "shadow_blockers": [
                "contract_id_mismatch",
                "source_version_mismatch",
                "signal_id_missing",
            ],
            "append_only_event_ready": False,
            "paper_order_id_present": False,
            "broker_order_id_present": False,
            "execution_id_present": False,
            "commission_report_id_present": False,
            "shadow_signal_id_present": False,
            "shadow_fill_price_present": False,
            "paper_shadow_link_present": False,
            "divergence_bps": 0,
            "divergence_threshold_bps": 0,
            "divergence_within_threshold": False,
            "unmatched_paper_fill_count": 0,
            "unmatched_shadow_fill_count": 0,
            "reconciliation_run_id_present": False,
            "raw_artifact_hash_present": False,
            "redacted_summary_hash_present": False,
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


def _valid_scorecard_status() -> dict[str, Any]:
    return {
        "phase": "phase3_scorecard_status_source_fixture",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "environment": "paper_shadow",
        "scorecard_status_state": "blocked",
        "phase3_started": False,
        "scorecard_writer_started": False,
        "db_apply_performed": False,
        "evidence_clock_started": False,
        "paper_shadow_window_complete": False,
        "scorecard": {
            "expected_contract_id": "stock_etf_scorecard_verdict_v1",
            "contract_id": "",
            "source_version": 0,
            "accepted": False,
            "blockers": [
                "contract_id_missing",
                "source_version_mismatch",
                "wrong_asset_lane",
            ],
            "verdict_label": "insufficient_evidence",
            "scorecard_input_bundle_hash_present": False,
            "evidence_clock_manifest_hash_present": False,
            "dq_manifest_hash_present": False,
            "formula_appendix_hash_present": False,
            "statistical_preregistration_hash_present": False,
            "benchmark_version_hash_present": False,
            "cost_model_version_hash_present": False,
            "strategy_hypothesis_hash_present": False,
            "reference_data_sources_hash_present": False,
            "scorecard_manifest_hash_present": False,
            "verdict_rationale_hash_present": False,
            "paper_shadow_window_trading_days": 0,
            "min_window_trading_days": 0,
            "independent_observation_count": 0,
            "min_independent_observation_count": 0,
            "gross_pnl_minor_units": 0,
            "net_pnl_minor_units": 0,
            "commission_minor_units": 0,
            "spread_slippage_minor_units": 0,
            "fx_drag_minor_units": 0,
            "tax_drag_minor_units": 0,
            "benchmark_excess_lcb_bps": 0,
            "conservative_cost_stress_lcb_bps": 0,
            "paper_shadow_divergence_bps": 0,
            "max_paper_shadow_divergence_bps": 0,
            "psr_bps": 0,
            "min_psr_bps": 0,
            "dsr_bps": 0,
            "min_dsr_bps": 0,
            "concentration_label_passed": False,
            "regime_label_passed": False,
            "breadth_label_passed": False,
            "freshness_label_passed": False,
            "survivorship_label_passed": False,
            "execution_realism_label_passed": False,
            "qc_review_hash_present": False,
            "mit_review_hash_present": False,
            "qa_review_hash_present": False,
            "qc_review_passed": False,
            "mit_review_passed": False,
            "qa_review_passed": False,
            "scorecard_is_derived_only": False,
            "paper_and_shadow_fills_separate": False,
            "live_fill_claimed": False,
            "bybit_live_execution_unchanged": False,
            "sealed": False,
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
        "live_or_tiny_live_authorized": False,
    }


def _make_authless_client() -> TestClient:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    return TestClient(app)
