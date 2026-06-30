from __future__ import annotations

"""Paper-lifecycle status normalizers for the Stock/ETF display-only surface."""

from typing import Any

from .stock_etf_status_common import (
    _BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID,
    _DENIED_OPERATIONS,
    _PAPER_LIFECYCLE_CONTRACT_ID,
    _PAPER_ORDER_REQUEST_CONTRACT_ID,
    _SAFETY_FALSE_FIELDS,
    _api_allowlist_contract_violations,
    _as_bool,
    _as_dict,
    _as_int,
    _as_list,
    _as_str,
    _normalize_api_allowlist,
    _paper_lifecycle_event_fail_closed,
    _paper_reconstructability_fail_closed,
    _phase2_fail_closed,
)

_LIFECYCLE_STATE_MACHINE_KEYS: tuple[str, ...] = (
    "expected_request_contract_id",
    "request_contract_id",
    "event_sequence",
    "event_sequence_present",
    "genesis_event",
    "previous_event_hash_present",
    "event_hash_present",
    "request_envelope_hash_present",
    "stale_state_policy",
    "stale_state_policy_present",
)

def _normalize_paper_lifecycle_event(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _paper_lifecycle_event_fail_closed(reason or "missing_lifecycle_event")
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
        "expected_request_contract_id": _as_str(
            source.get("expected_request_contract_id"),
            "",
        ),
        "request_contract_id": _as_str(source.get("request_contract_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "accepted": _as_bool(source.get("accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "operation": _as_str(source.get("operation"), "paper_order_submit"),
        "previous_state": _as_str(source.get("previous_state"), "local_intent_created"),
        "next_state": _as_str(source.get("next_state"), "local_intent_created"),
        "allowed": _as_bool(source.get("allowed")),
        "denial_reason": _as_str(source.get("denial_reason"), ""),
        "event_id_present": _as_bool(source.get("event_id_present")),
        "event_sequence": _as_int(source.get("event_sequence")),
        "event_sequence_present": _as_bool(source.get("event_sequence_present")),
        "genesis_event": _as_bool(source.get("genesis_event")),
        "event_time_ms": _as_int(source.get("event_time_ms")),
        "previous_event_hash_present": _as_bool(
            source.get("previous_event_hash_present")
        ),
        "event_hash_present": _as_bool(source.get("event_hash_present")),
        "request_envelope_hash_present": _as_bool(
            source.get("request_envelope_hash_present")
        ),
        "stale_state_policy": _as_str(source.get("stale_state_policy"), ""),
        "stale_state_policy_present": _as_bool(
            source.get("stale_state_policy_present")
        ),
        "state_machine_contract_fields_present": all(
            key in source for key in _LIFECYCLE_STATE_MACHINE_KEYS
        ),
        "order_local_id_present": _as_bool(source.get("order_local_id_present")),
        "idempotency_key_present": _as_bool(source.get("idempotency_key_present")),
        "broker_order_id_present": _as_bool(source.get("broker_order_id_present")),
        "execution_id_present": _as_bool(source.get("execution_id_present")),
        "commission_report_id_present": _as_bool(
            source.get("commission_report_id_present")
        ),
        "reconciliation_run_id_present": _as_bool(
            source.get("reconciliation_run_id_present")
        ),
        "raw_artifact_hash_present": _as_bool(source.get("raw_artifact_hash_present")),
        "redacted_summary_hash_present": _as_bool(
            source.get("redacted_summary_hash_present")
        ),
    }


def _normalize_paper_reconstructability(value: Any) -> dict[str, Any]:
    source = _as_dict(value)
    if not source:
        return _paper_reconstructability_fail_closed()
    return {
        "append_only_event_ready": _as_bool(source.get("append_only_event_ready")),
        "event_hash_chain_ready": _as_bool(source.get("event_hash_chain_ready")),
        "request_envelope_linked": _as_bool(source.get("request_envelope_linked")),
        "stale_state_policy_present": _as_bool(
            source.get("stale_state_policy_present")
        ),
        "broker_order_id_present": _as_bool(source.get("broker_order_id_present")),
        "execution_id_present": _as_bool(source.get("execution_id_present")),
        "commission_report_id_present": _as_bool(
            source.get("commission_report_id_present")
        ),
        "raw_artifact_hash_present": _as_bool(source.get("raw_artifact_hash_present")),
        "redacted_summary_hash_present": _as_bool(
            source.get("redacted_summary_hash_present")
        ),
        "restart_recovery_required": _as_bool(source.get("restart_recovery_required")),
        "manual_review_required": _as_bool(source.get("manual_review_required")),
    }


def _paper_status_contract_violations(
    source: dict[str, Any],
    phase2: dict[str, Any],
    lifecycle_event: dict[str, Any],
    reconstructability: dict[str, Any],
    reason: str | None,
) -> list[str]:
    violations = [
        field for field in _SAFETY_FALSE_FIELDS if _as_bool(source.get(field))
    ]
    if _as_bool(source.get("db_apply_performed")):
        violations.append("db_apply_performed")
    if _as_str(source.get("asset_lane"), "stock_etf_cash") != "stock_etf_cash":
        violations.append("asset_lane_mismatch")
    if _as_str(source.get("broker"), "ibkr") != "ibkr":
        violations.append("broker_mismatch")
    if _as_str(source.get("environment"), "paper") != "paper":
        violations.append("environment_mismatch")
    for key in (
        "phase2_started",
        "paper_lifecycle_started",
        "paper_order_submitted",
        "paper_fill_imported",
        "paper_reconciliation_started",
        "paper_account_snapshot_present",
        "broker_paper_attestation_present",
    ):
        if _as_bool(source.get(key)):
            violations.append(key)
    if (
        _as_str(lifecycle_event.get("expected_lifecycle_contract_id"), "")
        != _PAPER_LIFECYCLE_CONTRACT_ID
    ):
        violations.append("paper_lifecycle_expected_contract_id_mismatch")
    if (
        _as_str(lifecycle_event.get("expected_event_log_contract_id"), "")
        != _BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID
    ):
        violations.append("paper_event_log_expected_contract_id_mismatch")
    if (
        _as_str(lifecycle_event.get("expected_request_contract_id"), "")
        != _PAPER_ORDER_REQUEST_CONTRACT_ID
    ):
        violations.append("paper_request_expected_contract_id_mismatch")
    if reason is None and not _as_bool(
        lifecycle_event.get("state_machine_contract_fields_present")
    ):
        violations.append("paper_lifecycle_state_machine_fields_missing")
    if _as_bool(lifecycle_event.get("accepted")):
        violations.append("paper_lifecycle_event_accepted_before_gate")
    if _as_bool(lifecycle_event.get("allowed")):
        violations.append("paper_lifecycle_event_allowed_before_gate")
    for key in (
        "event_id_present",
        "event_sequence_present",
        "genesis_event",
        "previous_event_hash_present",
        "event_hash_present",
        "request_envelope_hash_present",
        "stale_state_policy_present",
        "order_local_id_present",
        "idempotency_key_present",
        "broker_order_id_present",
        "execution_id_present",
        "commission_report_id_present",
        "reconciliation_run_id_present",
        "raw_artifact_hash_present",
        "redacted_summary_hash_present",
    ):
        if _as_bool(lifecycle_event.get(key)):
            violations.append(f"paper_lifecycle_{key}")
    if _as_str(lifecycle_event.get("request_contract_id"), ""):
        violations.append("paper_lifecycle_request_contract_id_present")
    for key in (
        "append_only_event_ready",
        "event_hash_chain_ready",
        "request_envelope_linked",
        "stale_state_policy_present",
        "broker_order_id_present",
        "execution_id_present",
        "commission_report_id_present",
        "raw_artifact_hash_present",
        "redacted_summary_hash_present",
        "restart_recovery_required",
        "manual_review_required",
    ):
        if _as_bool(reconstructability.get(key)):
            violations.append(f"paper_reconstructability_{key}")
    if reason is None:
        api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
        violations.extend(_api_allowlist_contract_violations(api_allowlist))
    return violations


def _normalize_paper_status(raw: Any, reason: str | None) -> dict[str, Any]:
    source = _as_dict(raw)
    phase2 = _as_dict(source.get("phase2")) or _phase2_fail_closed()
    external_surface_gate = _as_dict(phase2.get("external_surface_gate"))
    api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
    lifecycle_event = _normalize_paper_lifecycle_event(
        source.get("lifecycle_event"),
        reason,
    )
    reconstructability = _normalize_paper_reconstructability(
        source.get("reconstructability")
    )

    contract_violations = _paper_status_contract_violations(
        source,
        phase2,
        lifecycle_event,
        reconstructability,
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
        "environment": "paper",
        "gui_authority": "display_only",
        "paper_status_state": status_state,
        "phase": _as_str(source.get("phase"), "phase2_paper_status_source_fixture"),
        "phase2_started": False,
        "phase2": phase2,
        "api_allowlist": api_allowlist,
        "phase2_gate_status": _as_str(external_surface_gate.get("status"), "BLOCKED"),
        "phase2_gate_blockers": blockers,
        "first_ibkr_contact_allowed": first_contact_allowed,
        "immutable_pass_artifact_present": immutable_artifact,
        "connector_enabled": connector_enabled,
        "lifecycle_event": lifecycle_event,
        "reconstructability": reconstructability,
        "ibkr_live_enabled": False,
        "stock_live_disabled": True,
        "paper_order_entry_visible": False,
        "allowed_gui_actions": ["refresh_paper_status"],
        "denied_operations": list(_DENIED_OPERATIONS),
        "paper_lifecycle_started": False,
        "paper_order_submitted": False,
        "paper_fill_imported": False,
        "paper_reconciliation_started": False,
        "paper_account_snapshot_present": False,
        "broker_paper_attestation_present": False,
        "ibkr_call_performed": False,
        "secret_slot_touched": False,
        "order_routed": False,
        "bybit_ipc_reused": False,
        "db_apply_performed": False,
        "contract_violations": contract_violations,
        "degraded": reason is not None or bool(contract_violations),
        "reason": reason,
    }
