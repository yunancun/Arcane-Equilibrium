"""Paper/shadow reconciliation status normalizers for Stock/ETF display-only views."""

from __future__ import annotations

from typing import Any

from .stock_etf_status_common import (
    _BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID,
    _DENIED_OPERATIONS,
    _PAPER_LIFECYCLE_CONTRACT_ID,
    _PAPER_SHADOW_RECONCILIATION_CONTRACT_ID,
    _SAFETY_FALSE_FIELDS,
    _SHADOW_FILL_MODEL_CONTRACT_ID,
    _api_allowlist_contract_violations,
    _as_bool,
    _as_dict,
    _as_int,
    _as_list,
    _as_str,
    _normalize_api_allowlist,
    _phase2_fail_closed,
)


def _matching_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_lifecycle_contract_id": _PAPER_LIFECYCLE_CONTRACT_ID,
        "lifecycle_contract_id": "",
        "expected_event_log_contract_id": _BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID,
        "event_log_contract_id": "",
        "expected_shadow_contract_id": _SHADOW_FILL_MODEL_CONTRACT_ID,
        "shadow_contract_id": "",
        "expected_reconciliation_contract_id": _PAPER_SHADOW_RECONCILIATION_CONTRACT_ID,
        "reconciliation_contract_id": "",
        "reconciliation_accepted": False,
        "reconciliation_blockers": [reason],
        "lifecycle_event_accepted": False,
        "shadow_fill_model_accepted": False,
        "lifecycle_blockers": [reason],
        "shadow_blockers": [reason],
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
        "contract_reconciliation_run_id_present": False,
        "paper_shadow_link_hash_present": False,
        "paper_fill_imported": False,
        "shadow_fill_synthetic": False,
        "raw_artifact_hash_present": False,
        "redacted_summary_hash_present": False,
        "reconciliation_writer_started": False,
        "ibkr_contact_performed": False,
        "connector_runtime_started": False,
        "secret_content_serialized": False,
        "fill_import_performed": False,
        "shadow_fill_generated": False,
    }


def _normalize_matching(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _matching_fail_closed(reason or "missing_reconciliation_matching")
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "expected_lifecycle_contract_id": _as_str(
            source.get("expected_lifecycle_contract_id"),
            _PAPER_LIFECYCLE_CONTRACT_ID,
        ),
        "lifecycle_contract_id": _as_str(source.get("lifecycle_contract_id"), ""),
        "expected_event_log_contract_id": _as_str(
            source.get("expected_event_log_contract_id"),
            _BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID,
        ),
        "event_log_contract_id": _as_str(source.get("event_log_contract_id"), ""),
        "expected_shadow_contract_id": _as_str(
            source.get("expected_shadow_contract_id"),
            _SHADOW_FILL_MODEL_CONTRACT_ID,
        ),
        "shadow_contract_id": _as_str(source.get("shadow_contract_id"), ""),
        "expected_reconciliation_contract_id": _as_str(
            source.get("expected_reconciliation_contract_id"),
            _PAPER_SHADOW_RECONCILIATION_CONTRACT_ID,
        ),
        "reconciliation_contract_id": _as_str(
            source.get("reconciliation_contract_id"), ""
        ),
        "reconciliation_accepted": _as_bool(source.get("reconciliation_accepted")),
        "reconciliation_blockers": [
            str(item) for item in _as_list(source.get("reconciliation_blockers"))
        ],
        "lifecycle_event_accepted": _as_bool(source.get("lifecycle_event_accepted")),
        "shadow_fill_model_accepted": _as_bool(
            source.get("shadow_fill_model_accepted")
        ),
        "lifecycle_blockers": [
            str(item) for item in _as_list(source.get("lifecycle_blockers"))
        ],
        "shadow_blockers": [
            str(item) for item in _as_list(source.get("shadow_blockers"))
        ],
        "append_only_event_ready": _as_bool(source.get("append_only_event_ready")),
        "paper_order_id_present": _as_bool(source.get("paper_order_id_present")),
        "broker_order_id_present": _as_bool(source.get("broker_order_id_present")),
        "execution_id_present": _as_bool(source.get("execution_id_present")),
        "commission_report_id_present": _as_bool(
            source.get("commission_report_id_present")
        ),
        "shadow_signal_id_present": _as_bool(source.get("shadow_signal_id_present")),
        "shadow_fill_price_present": _as_bool(source.get("shadow_fill_price_present")),
        "paper_shadow_link_present": _as_bool(source.get("paper_shadow_link_present")),
        "divergence_bps": _as_int(source.get("divergence_bps")),
        "divergence_threshold_bps": _as_int(source.get("divergence_threshold_bps")),
        "divergence_within_threshold": _as_bool(
            source.get("divergence_within_threshold")
        ),
        "unmatched_paper_fill_count": _as_int(
            source.get("unmatched_paper_fill_count")
        ),
        "unmatched_shadow_fill_count": _as_int(
            source.get("unmatched_shadow_fill_count")
        ),
        "reconciliation_run_id_present": _as_bool(
            source.get("reconciliation_run_id_present")
        ),
        "contract_reconciliation_run_id_present": _as_bool(
            source.get("contract_reconciliation_run_id_present")
        ),
        "paper_shadow_link_hash_present": _as_bool(
            source.get("paper_shadow_link_hash_present")
        ),
        "paper_fill_imported": _as_bool(source.get("paper_fill_imported")),
        "shadow_fill_synthetic": _as_bool(source.get("shadow_fill_synthetic")),
        "raw_artifact_hash_present": _as_bool(source.get("raw_artifact_hash_present")),
        "redacted_summary_hash_present": _as_bool(
            source.get("redacted_summary_hash_present")
        ),
        "reconciliation_writer_started": _as_bool(
            source.get("reconciliation_writer_started")
        ),
        "ibkr_contact_performed": _as_bool(source.get("ibkr_contact_performed")),
        "connector_runtime_started": _as_bool(
            source.get("connector_runtime_started")
        ),
        "secret_content_serialized": _as_bool(
            source.get("secret_content_serialized")
        ),
        "fill_import_performed": _as_bool(source.get("fill_import_performed")),
        "shadow_fill_generated": _as_bool(source.get("shadow_fill_generated")),
    }


def _reconciliation_contract_violations(
    source: dict[str, Any],
    phase2: dict[str, Any],
    matching: dict[str, Any],
    reason: str | None,
) -> list[str]:
    violations = [
        field for field in _SAFETY_FALSE_FIELDS if _as_bool(source.get(field))
    ]
    if _as_str(source.get("asset_lane"), "stock_etf_cash") != "stock_etf_cash":
        violations.append("asset_lane_mismatch")
    if _as_str(source.get("broker"), "ibkr") != "ibkr":
        violations.append("broker_mismatch")
    if _as_str(source.get("environment"), "paper_shadow") != "paper_shadow":
        violations.append("environment_mismatch")
    for key in (
        "phase3_started",
        "paper_shadow_reconciliation_started",
        "paper_orders_ready",
        "paper_fills_ready",
        "shadow_fills_ready",
        "scorecard_writer_started",
        "db_apply_performed",
    ):
        if _as_bool(source.get(key)):
            violations.append(key)
    if (
        _as_str(matching.get("expected_lifecycle_contract_id"), "")
        != _PAPER_LIFECYCLE_CONTRACT_ID
    ):
        violations.append("reconciliation_lifecycle_expected_contract_id_mismatch")
    if (
        _as_str(matching.get("expected_event_log_contract_id"), "")
        != _BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID
    ):
        violations.append("reconciliation_event_log_expected_contract_id_mismatch")
    if (
        _as_str(matching.get("expected_shadow_contract_id"), "")
        != _SHADOW_FILL_MODEL_CONTRACT_ID
    ):
        violations.append("reconciliation_shadow_expected_contract_id_mismatch")
    if (
        _as_str(matching.get("expected_reconciliation_contract_id"), "")
        != _PAPER_SHADOW_RECONCILIATION_CONTRACT_ID
    ):
        violations.append("reconciliation_expected_contract_id_mismatch")
    for key in (
        "reconciliation_accepted",
        "lifecycle_event_accepted",
        "shadow_fill_model_accepted",
        "append_only_event_ready",
        "paper_order_id_present",
        "broker_order_id_present",
        "execution_id_present",
        "commission_report_id_present",
        "shadow_signal_id_present",
        "shadow_fill_price_present",
        "paper_shadow_link_present",
        "divergence_within_threshold",
        "reconciliation_run_id_present",
        "contract_reconciliation_run_id_present",
        "paper_shadow_link_hash_present",
        "paper_fill_imported",
        "shadow_fill_synthetic",
        "raw_artifact_hash_present",
        "redacted_summary_hash_present",
        "reconciliation_writer_started",
        "ibkr_contact_performed",
        "connector_runtime_started",
        "secret_content_serialized",
        "fill_import_performed",
        "shadow_fill_generated",
    ):
        if _as_bool(matching.get(key)):
            violations.append(f"reconciliation_{key}")
    if _as_int(matching.get("divergence_bps")) != 0:
        violations.append("reconciliation_divergence_bps_present")
    if _as_int(matching.get("divergence_threshold_bps")) != 0:
        violations.append("reconciliation_divergence_threshold_bps_present")
    if _as_int(matching.get("unmatched_paper_fill_count")) != 0:
        violations.append("reconciliation_unmatched_paper_fill_count_present")
    if _as_int(matching.get("unmatched_shadow_fill_count")) != 0:
        violations.append("reconciliation_unmatched_shadow_fill_count_present")
    if reason is None:
        api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
        violations.extend(_api_allowlist_contract_violations(api_allowlist))
    return violations


def _normalize_reconciliation_status(raw: Any, reason: str | None) -> dict[str, Any]:
    source = _as_dict(raw)
    phase2 = _as_dict(source.get("phase2")) or _phase2_fail_closed()
    external_surface_gate = _as_dict(phase2.get("external_surface_gate"))
    api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
    matching = _normalize_matching(source.get("matching"), reason)

    contract_violations = _reconciliation_contract_violations(
        source,
        phase2,
        matching,
        reason,
    )
    blockers = [
        str(item) for item in _as_list(external_surface_gate.get("blockers"))
    ]
    if reason is not None and reason not in blockers:
        blockers.append(reason)

    status_state = "blocked"
    if contract_violations:
        status_state = "contract_violation_blocked"
    elif reason is not None:
        status_state = "degraded"

    first_contact_allowed = _as_bool(phase2.get("first_ibkr_contact_allowed"))
    immutable_artifact = _as_bool(phase2.get("immutable_pass_artifact_present"))
    connector_enabled = _as_bool(phase2.get("connector_enabled"))

    return {
        "api_version": "v1",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "environment": "paper_shadow",
        "gui_authority": "display_only",
        "reconciliation_status_state": status_state,
        "phase": _as_str(
            source.get("phase"),
            "phase3_reconciliation_status_source_fixture",
        ),
        "phase3_started": False,
        "phase2": phase2,
        "api_allowlist": api_allowlist,
        "phase2_gate_status": _as_str(external_surface_gate.get("status"), "BLOCKED"),
        "phase2_gate_blockers": blockers,
        "first_ibkr_contact_allowed": first_contact_allowed,
        "immutable_pass_artifact_present": immutable_artifact,
        "connector_enabled": connector_enabled,
        "matching": matching,
        "ibkr_live_enabled": False,
        "stock_live_disabled": True,
        "paper_order_entry_visible": False,
        "allowed_gui_actions": ["refresh_reconciliation_status"],
        "denied_operations": list(_DENIED_OPERATIONS),
        "paper_shadow_reconciliation_started": False,
        "paper_orders_ready": False,
        "paper_fills_ready": False,
        "shadow_fills_ready": False,
        "scorecard_writer_started": False,
        "db_apply_performed": False,
        "ibkr_call_performed": False,
        "secret_slot_touched": False,
        "order_routed": False,
        "bybit_ipc_reused": False,
        "contract_violations": contract_violations,
        "degraded": reason is not None or bool(contract_violations),
        "reason": reason,
    }
