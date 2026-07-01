from __future__ import annotations

"""Shared fail-closed constants and helpers for Stock/ETF status surfaces."""

from typing import Any

_API_ALLOWLIST_CONTRACT_ID = "non_bybit_api_allowlist_v1"
_API_ALLOWLIST_SOURCE_VERSION = 1
_API_ALLOWLIST_READ_ACTION_COUNT = 10
_API_ALLOWLIST_PAPER_WRITE_ACTION_COUNT = 3
_API_ALLOWLIST_DENIED_ACTION_COUNT = 10
_MARKET_DATA_PROVENANCE_CONTRACT_ID = "stock_market_data_provenance_v1"
_COLLECTOR_RUN_CONTRACT_ID = "stock_etf_collector_run_v1"
_DQ_MANIFEST_CONTRACT_ID = "stock_etf_dq_manifest_v1"
_EVIDENCE_CLOCK_CONTRACT_ID = "stock_etf_evidence_clock_v1"
_PIT_UNIVERSE_CONTRACT_ID = "stock_etf_pit_universe_contract_v1"
_SHADOW_FILL_MODEL_CONTRACT_ID = "stock_shadow_fill_model_v1"
_PAPER_SHADOW_RECONCILIATION_CONTRACT_ID = (
    "stock_etf_paper_shadow_reconciliation_v1"
)
_STRATEGY_HYPOTHESIS_CONTRACT_ID = "stock_etf_strategy_hypothesis_contract_v1"
_PAPER_LIFECYCLE_CONTRACT_ID = "ibkr_paper_order_lifecycle_v1"
_BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID = "broker_lifecycle_event_log_v1"
_PAPER_ORDER_REQUEST_CONTRACT_ID = "stock_etf_paper_order_request_v1"
_ACCOUNT_CASH_LEDGER_CONTRACT_ID = "broker_account_portfolio_cash_ledger_v1"
_SESSION_ATTESTATION_CONTRACT_ID = "ibkr_session_attestation_v1"
_PAPER_ATTESTATION_CONTRACT_ID = "ibkr_paper_attestation_v1"
_SCORECARD_DERIVATION_CONTRACT_ID = "stock_etf_scorecard_derivation_v1"
_SCORECARD_VERDICT_CONTRACT_ID = "stock_etf_scorecard_verdict_v1"
_RELEASE_PACKET_CONTRACT_ID = "stock_etf_release_packet_v1"
_DISABLE_CLEANUP_RUNBOOK_ID = "stock_etf_kill_switch_and_disable_cleanup_runbook_v1"
_TINY_LIVE_ADR_ELIGIBILITY_CONTRACT_ID = "tiny_live_adr_eligibility_v1"
_DENIED_OPERATIONS: tuple[str, ...] = (
    "ibkr_live_order_submit",
    "ibkr_tiny_live",
    "ibkr_margin_or_short",
    "ibkr_options_or_cfd",
    "ibkr_transfer_or_account_write",
    "ibkr_secret_slot_creation",
    "ibkr_api_contact_before_phase2_gate",
)
_NO_STORE_HEADERS: dict[str, str] = {
    "Cache-Control": "no-cache, no-store, private, max-age=0, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
    "Vary": "Authorization",
}
_SAFETY_FALSE_FIELDS: tuple[str, ...] = (
    "ibkr_live_enabled",
    "ibkr_call_performed",
    "secret_slot_touched",
    "order_routed",
    "bybit_ipc_reused",
)


def _phase2_fail_closed() -> dict[str, Any]:
    return {
        "external_surface_gate": {
            "status": "BLOCKED",
            "ibkr_contact_allowed": False,
            "blockers": ["ipc_unavailable"],
            "ibkr_call_performed": False,
        },
        "api_allowlist": {
            "contract_id": "",
            "source_version": 0,
            "accepted": False,
            "blockers": ["ipc_unavailable"],
            "read_action_count": 0,
            "paper_write_action_count": 0,
            "denied_action_count": 0,
            "ibkr_contact_performed": False,
            "secret_content_serialized": False,
            "bybit_live_execution_protected": False,
        },
        "policy_prerequisites": {
            "bundle_accepted": False,
            "blockers": ["ipc_unavailable"],
            "flags": {},
        },
        "immutable_pass_artifact_present": False,
        "first_ibkr_contact_allowed": False,
        "connector_enabled": False,
        "secret_slot_touched": False,
        "order_routed": False,
    }


def _readiness_fail_closed() -> dict[str, Any]:
    return {
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "default_asset_lane": "crypto_perp",
        "readonly_ready": False,
        "paper_ready": False,
        "shadow_only": True,
        "live_denied": True,
        "denial_reasons": ["ipc_unavailable"],
    }


def _market_data_provenance_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_contract_id": _MARKET_DATA_PROVENANCE_CONTRACT_ID,
        "contract_id": "",
        "source_version": 0,
        "accepted": False,
        "blockers": [reason],
        "ibkr_contact_performed": False,
        "connector_runtime_started": False,
        "secret_content_serialized": False,
        "live_or_tiny_live_authorized": False,
    }


def _evidence_clock_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_contract_id": _EVIDENCE_CLOCK_CONTRACT_ID,
        "contract_id": "",
        "source_version": 0,
        "status": "NOT_STARTED",
        "accepted": False,
        "blockers": [reason],
        "collector_run_contract_id": "",
        "collector_run_contract_hash_present": False,
        "dq_manifest_contract_id": "",
        "dq_manifest_contract_hash_present": False,
        "source_artifact_hash_present": False,
        "market_data_provenance_contract_hash_present": False,
        "scorecard_input_bundle_hash_present": False,
        "checker_contacted_ibkr": False,
        "checker_started_connector_runtime": False,
        "checker_started_evidence_clock": False,
        "checker_wrote_scorecard": False,
        "checker_applied_db": False,
        "secret_content_serialized": False,
        "live_or_tiny_live_authorized": False,
        "ibkr_readonly_paper_connector_green_5d": False,
        "shadow_collector_green_5d": False,
    }


def _collector_run_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_contract_id": _COLLECTOR_RUN_CONTRACT_ID,
        "contract_id": "",
        "source_version": 0,
        "accepted": False,
        "blockers": [reason],
        "collector_run_id": "",
        "trading_day": "",
        "expected_trading_sessions": 0,
        "completed_trading_sessions": 0,
        "pit_universe_contract_hash_present": False,
        "market_data_provenance_contract_hash_present": False,
        "reference_data_sources_contract_hash_present": False,
        "storage_capacity_contract_hash_present": False,
        "gap_report_hash_present": False,
        "dq_manifest_hash_present": False,
        "replay_manifest_hash_present": False,
        "source_artifact_hash_present": False,
        "bybit_live_execution_unchanged": False,
        "ibkr_contact_performed": False,
        "connector_runtime_started": False,
        "market_data_ingestion_started": False,
        "evidence_writer_started": False,
        "scorecard_writer_started": False,
        "db_apply_performed": False,
        "secret_content_serialized": False,
        "live_or_tiny_live_authorized": False,
    }


def _frozen_inputs_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "accepted": False,
        "blockers": [reason],
        "universe_hash_present": False,
        "benchmark_hash_present": False,
        "cost_model_hash_present": False,
        "strategy_hypothesis_hash_present": False,
        "reference_data_sources_contract_hash_present": False,
        "paper_shadow_divergence_threshold_hash_present": False,
        "gui_evidence_view_available": False,
        "daily_scorecard_regeneration_passed": False,
    }


def _dq_manifest_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_contract_id": _DQ_MANIFEST_CONTRACT_ID,
        "contract_id": "",
        "source_version": 0,
        "shape_accepted": False,
        "shape_blockers": [reason],
        "passes_day_quality": False,
        "collector_run_id": "",
        "trading_day": "",
        "market_data_provenance_contract_hash_present": False,
        "source_artifact_hash_present": False,
        "bybit_live_execution_unchanged": False,
        "ibkr_contact_performed": False,
        "connector_runtime_started": False,
        "market_data_ingestion_started": False,
        "dq_writer_started": False,
        "evidence_clock_started": False,
        "scorecard_writer_started": False,
        "db_apply_performed": False,
        "secret_content_serialized": False,
        "live_or_tiny_live_authorized": False,
        "calendar_aware_coverage_bps": 0,
        "symbol_completeness_bps": 0,
        "latency_dq_passed": False,
        "market_data_provenance_accepted": False,
        "scorecard_regeneration_passed": False,
    }


def _scorecard_fail_closed() -> dict[str, Any]:
    return {
        "writer_started": False,
        "db_apply_performed": False,
        "daily_scorecard_regeneration_passed": False,
    }


def _universe_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_contract_id": _PIT_UNIVERSE_CONTRACT_ID,
        "contract_id": "",
        "source_version": 0,
        "accepted": False,
        "blockers": [reason],
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
    }


def _shadow_fill_model_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_contract_id": _SHADOW_FILL_MODEL_CONTRACT_ID,
        "contract_id": "",
        "source_version": 0,
        "accepted": False,
        "blockers": [reason],
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
    }


def _strategy_hypothesis_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_contract_id": _STRATEGY_HYPOTHESIS_CONTRACT_ID,
        "contract_id": "",
        "source_version": 0,
        "accepted": False,
        "blockers": [reason],
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
    }


def _paper_lifecycle_event_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_lifecycle_contract_id": _PAPER_LIFECYCLE_CONTRACT_ID,
        "lifecycle_contract_id": "",
        "expected_event_log_contract_id": _BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID,
        "event_log_contract_id": "",
        "expected_request_contract_id": _PAPER_ORDER_REQUEST_CONTRACT_ID,
        "request_contract_id": "",
        "source_version": 0,
        "accepted": False,
        "blockers": [reason],
        "operation": "paper_order_submit",
        "previous_state": "local_intent_created",
        "next_state": "local_intent_created",
        "allowed": False,
        "denial_reason": "",
        "event_id_present": False,
        "event_sequence": 0,
        "event_sequence_present": False,
        "genesis_event": False,
        "event_time_ms": 0,
        "previous_event_hash_present": False,
        "event_hash_present": False,
        "request_envelope_hash_present": False,
        "stale_state_policy": "",
        "stale_state_policy_present": False,
        "state_machine_contract_fields_present": True,
        "order_local_id_present": False,
        "idempotency_key_present": False,
        "broker_order_id_present": False,
        "execution_id_present": False,
        "commission_report_id_present": False,
        "reconciliation_run_id_present": False,
        "raw_artifact_hash_present": False,
        "redacted_summary_hash_present": False,
    }


def _paper_reconstructability_fail_closed() -> dict[str, Any]:
    return {
        "append_only_event_ready": False,
        "event_hash_chain_ready": False,
        "request_envelope_linked": False,
        "stale_state_policy_present": False,
        "broker_order_id_present": False,
        "execution_id_present": False,
        "commission_report_id_present": False,
        "raw_artifact_hash_present": False,
        "redacted_summary_hash_present": False,
        "restart_recovery_required": False,
        "manual_review_required": False,
    }


def _account_snapshot_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_contract_id": _ACCOUNT_CASH_LEDGER_CONTRACT_ID,
        "contract_id": "",
        "source_version": 0,
        "accepted": False,
        "blockers": [reason],
        "account_fingerprint_hash_present": False,
        "account_snapshot_hash_present": False,
        "portfolio_positions_hash_present": False,
        "currency": "",
        "cash_balance_minor_units": 0,
        "buying_power_minor_units": 0,
        "as_of_ms": 0,
        "source_report_hash_present": False,
    }


def _session_attestation_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_contract_id": _SESSION_ATTESTATION_CONTRACT_ID,
        "contract_id": "",
        "source_version": 0,
        "status": "BLOCKED",
        "accepted": False,
        "blockers": [reason],
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
    }


def _paper_attestation_policy_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_contract_id": _PAPER_ATTESTATION_CONTRACT_ID,
        "contract_id": "",
        "source_version": 0,
        "accepted": False,
        "blockers": [reason],
        "external_surface_gate_required": False,
        "session_attestation_required": False,
        "rust_lane_scoped_ipc_required": False,
        "decision_lease_required": False,
        "guardian_required": False,
        "paper_environment_only": False,
        "live_account_fingerprint_denied": False,
        "margin_short_options_cfd_denied": False,
    }


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str(value: Any, default: str) -> str:
    return value if isinstance(value, str) and value else default


def _as_bool(value: Any) -> bool:
    return value is True


def _as_int(value: Any) -> int:
    return value if type(value) is int else 0


def _normalize_api_allowlist(value: Any) -> dict[str, Any]:
    source = _as_dict(value)
    return {
        "contract_id": _as_str(source.get("contract_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "accepted": _as_bool(source.get("accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "read_action_count": _as_int(source.get("read_action_count")),
        "paper_write_action_count": _as_int(source.get("paper_write_action_count")),
        "denied_action_count": _as_int(source.get("denied_action_count")),
        "ibkr_contact_performed": _as_bool(source.get("ibkr_contact_performed")),
        "secret_content_serialized": _as_bool(source.get("secret_content_serialized")),
        "bybit_live_execution_protected": _as_bool(
            source.get("bybit_live_execution_protected")
        ),
    }


def _api_allowlist_contract_violations(api_allowlist: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    if not _as_bool(api_allowlist.get("accepted")):
        violations.append("api_allowlist_not_accepted")
    if _as_str(api_allowlist.get("contract_id"), "") != _API_ALLOWLIST_CONTRACT_ID:
        violations.append("api_allowlist_contract_id_mismatch")
    if _as_int(api_allowlist.get("source_version")) != _API_ALLOWLIST_SOURCE_VERSION:
        violations.append("api_allowlist_source_version_mismatch")
    if _as_int(api_allowlist.get("read_action_count")) != _API_ALLOWLIST_READ_ACTION_COUNT:
        violations.append("api_allowlist_read_action_count_mismatch")
    if (
        _as_int(api_allowlist.get("paper_write_action_count"))
        != _API_ALLOWLIST_PAPER_WRITE_ACTION_COUNT
    ):
        violations.append("api_allowlist_paper_write_action_count_mismatch")
    if _as_int(api_allowlist.get("denied_action_count")) != _API_ALLOWLIST_DENIED_ACTION_COUNT:
        violations.append("api_allowlist_denied_action_count_mismatch")
    if _as_bool(api_allowlist.get("ibkr_contact_performed")):
        violations.append("api_allowlist_ibkr_contact_performed")
    if _as_bool(api_allowlist.get("secret_content_serialized")):
        violations.append("api_allowlist_secret_content_serialized")
    if not _as_bool(api_allowlist.get("bybit_live_execution_protected")):
        violations.append("api_allowlist_bybit_live_not_protected")
    return violations
