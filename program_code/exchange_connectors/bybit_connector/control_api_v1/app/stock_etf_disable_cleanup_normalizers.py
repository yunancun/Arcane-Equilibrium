"""Disable-cleanup status normalizers for the Stock/ETF display-only surface."""

from __future__ import annotations

from typing import Any

from .stock_etf_status_common import (
    _DENIED_OPERATIONS,
    _DISABLE_CLEANUP_RUNBOOK_ID,
    _SAFETY_FALSE_FIELDS,
    _api_allowlist_contract_violations,
    _as_bool,
    _as_dict,
    _as_int,
    _as_list,
    _as_str,
    _normalize_api_allowlist,
    _phase2_fail_closed,
)

_EXPECTED_ENV_FLAG_COUNT = 4
_EXPECTED_PROOF_COUNT = 7


def _disable_cleanup_runbook_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_runbook_id": _DISABLE_CLEANUP_RUNBOOK_ID,
        "runbook_id": "",
        "source_version": 0,
        "accepted": False,
        "blockers": [reason],
        "source_artifact_hash_present": False,
        "bybit_live_execution_unchanged": False,
        "env_flag_count": 0,
        "proof_count": 0,
        "env_flags": [],
        "proofs": [],
        "ibkr_contact_performed": False,
        "connector_runtime_started": False,
        "paper_order_routed": False,
        "secret_slot_created": False,
        "secret_content_serialized": False,
        "destructive_db_cleanup_requested": False,
        "db_delete_or_truncate_allowed": False,
        "paper_shadow_launch_authorized": False,
        "tiny_live_authorized": False,
        "live_authorized": False,
    }


def _normalize_env_flag(value: Any) -> dict[str, Any]:
    source = _as_dict(value)
    return {
        "name": _as_str(source.get("name"), ""),
        "expected_value": _as_str(source.get("expected_value"), ""),
        "observed_value": _as_str(source.get("observed_value"), ""),
        "evidence_hash_present": _as_bool(source.get("evidence_hash_present")),
    }


def _normalize_proof(value: Any) -> dict[str, Any]:
    source = _as_dict(value)
    return {
        "kind": _as_str(source.get("kind"), ""),
        "verified": _as_bool(source.get("verified")),
        "evidence_hash_present": _as_bool(source.get("evidence_hash_present")),
        "grants_runtime_authority": _as_bool(source.get("grants_runtime_authority")),
        "destructive_cleanup_claimed": _as_bool(
            source.get("destructive_cleanup_claimed")
        ),
    }


def _normalize_disable_cleanup_runbook(
    value: Any, reason: str | None
) -> dict[str, Any]:
    fallback = _disable_cleanup_runbook_fail_closed(
        reason or "missing_disable_cleanup_runbook"
    )
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "expected_runbook_id": _as_str(
            source.get("expected_runbook_id"), _DISABLE_CLEANUP_RUNBOOK_ID
        ),
        "runbook_id": _as_str(source.get("runbook_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "accepted": _as_bool(source.get("accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "source_artifact_hash_present": _as_bool(
            source.get("source_artifact_hash_present")
        ),
        "bybit_live_execution_unchanged": _as_bool(
            source.get("bybit_live_execution_unchanged")
        ),
        "env_flag_count": _as_int(source.get("env_flag_count")),
        "proof_count": _as_int(source.get("proof_count")),
        "env_flags": [
            _normalize_env_flag(item) for item in _as_list(source.get("env_flags"))
        ],
        "proofs": [_normalize_proof(item) for item in _as_list(source.get("proofs"))],
        "ibkr_contact_performed": _as_bool(source.get("ibkr_contact_performed")),
        "connector_runtime_started": _as_bool(
            source.get("connector_runtime_started")
        ),
        "paper_order_routed": _as_bool(source.get("paper_order_routed")),
        "secret_slot_created": _as_bool(source.get("secret_slot_created")),
        "secret_content_serialized": _as_bool(source.get("secret_content_serialized")),
        "destructive_db_cleanup_requested": _as_bool(
            source.get("destructive_db_cleanup_requested")
        ),
        "db_delete_or_truncate_allowed": _as_bool(
            source.get("db_delete_or_truncate_allowed")
        ),
        "paper_shadow_launch_authorized": _as_bool(
            source.get("paper_shadow_launch_authorized")
        ),
        "tiny_live_authorized": _as_bool(source.get("tiny_live_authorized")),
        "live_authorized": _as_bool(source.get("live_authorized")),
    }


def _disable_cleanup_contract_violations(
    source: dict[str, Any],
    phase2: dict[str, Any],
    runbook: dict[str, Any],
    reason: str | None,
) -> list[str]:
    violations = [
        field for field in _SAFETY_FALSE_FIELDS if _as_bool(source.get(field))
    ]
    for key in (
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
    ):
        if _as_bool(source.get(key)):
            violations.append(key)
    if reason is not None:
        return violations

    if _as_str(source.get("asset_lane"), "stock_etf_cash") != "stock_etf_cash":
        violations.append("asset_lane_mismatch")
    if _as_str(source.get("broker"), "ibkr") != "ibkr":
        violations.append("broker_mismatch")
    if _as_str(source.get("environment"), "paper_shadow") != "paper_shadow":
        violations.append("environment_mismatch")
    if _as_str(runbook.get("expected_runbook_id"), "") != _DISABLE_CLEANUP_RUNBOOK_ID:
        violations.append("runbook_expected_id_mismatch")
    if not _as_bool(runbook.get("accepted")):
        violations.append("runbook_not_accepted")
    if not _as_bool(runbook.get("source_artifact_hash_present")):
        violations.append("runbook_source_artifact_hash_missing")
    if not _as_bool(runbook.get("bybit_live_execution_unchanged")):
        violations.append("runbook_bybit_live_not_protected")
    if _as_int(runbook.get("env_flag_count")) != _EXPECTED_ENV_FLAG_COUNT:
        violations.append("runbook_env_flag_count_mismatch")
    if _as_int(runbook.get("proof_count")) != _EXPECTED_PROOF_COUNT:
        violations.append("runbook_proof_count_mismatch")
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
        if _as_bool(runbook.get(key)):
            violations.append(f"runbook_{key}")
    for flag in _as_list(runbook.get("env_flags")):
        normalized = _normalize_env_flag(flag)
        name = normalized["name"] or "unknown"
        if normalized["expected_value"] != normalized["observed_value"]:
            violations.append(f"env_flag_{name}_observed_mismatch")
        if not _as_bool(normalized.get("evidence_hash_present")):
            violations.append(f"env_flag_{name}_evidence_hash_missing")
    for proof in _as_list(runbook.get("proofs")):
        normalized = _normalize_proof(proof)
        kind = normalized["kind"] or "unknown"
        if not _as_bool(normalized.get("verified")):
            violations.append(f"proof_{kind}_not_verified")
        if not _as_bool(normalized.get("evidence_hash_present")):
            violations.append(f"proof_{kind}_evidence_hash_missing")
        if _as_bool(normalized.get("grants_runtime_authority")):
            violations.append(f"proof_{kind}_grants_runtime_authority")
        if _as_bool(normalized.get("destructive_cleanup_claimed")):
            violations.append(f"proof_{kind}_destructive_cleanup_claimed")

    api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
    violations.extend(_api_allowlist_contract_violations(api_allowlist))
    return violations


def _normalize_disable_cleanup_status(raw: Any, reason: str | None) -> dict[str, Any]:
    source = _as_dict(raw)
    phase2 = _as_dict(source.get("phase2")) or _phase2_fail_closed()
    external_surface_gate = _as_dict(phase2.get("external_surface_gate"))
    api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
    runbook = _normalize_disable_cleanup_runbook(source.get("runbook"), reason)
    contract_violations = _disable_cleanup_contract_violations(
        source,
        phase2,
        runbook,
        reason,
    )
    blockers = [
        str(item) for item in _as_list(external_surface_gate.get("blockers"))
    ]
    if reason is not None and reason not in blockers:
        blockers.append(reason)

    status_state = "source_ready_runtime_blocked"
    if contract_violations:
        status_state = "contract_violation_blocked"
    elif reason is not None:
        status_state = "degraded"
    elif not runbook["accepted"]:
        status_state = "blocked"

    return {
        "api_version": "v1",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "environment": "paper_shadow",
        "gui_authority": "display_only",
        "disable_cleanup_status_state": status_state,
        "phase": _as_str(
            source.get("phase"), "phase5_disable_cleanup_status_source_fixture"
        ),
        "phase2": phase2,
        "api_allowlist": api_allowlist,
        "phase2_gate_status": _as_str(external_surface_gate.get("status"), "BLOCKED"),
        "phase2_gate_blockers": blockers,
        "first_ibkr_contact_allowed": _as_bool(
            phase2.get("first_ibkr_contact_allowed")
        ),
        "immutable_pass_artifact_present": _as_bool(
            phase2.get("immutable_pass_artifact_present")
        ),
        "connector_enabled": _as_bool(phase2.get("connector_enabled")),
        "runbook": runbook,
        "phase3_started": False,
        "phase5_started": False,
        "collector_stop_requested": False,
        "gui_disable_requested": False,
        "evidence_archive_requested": False,
        "db_cleanup_requested": False,
        "ibkr_live_enabled": False,
        "stock_live_disabled": True,
        "paper_order_entry_visible": False,
        "allowed_gui_actions": ["refresh_disable_cleanup_status"],
        "denied_operations": list(_DENIED_OPERATIONS),
        "paper_shadow_launch_authorized": False,
        "tiny_live_or_live_authorized": False,
        "connector_runtime_started": False,
        "scorecard_writer_started": False,
        "db_apply_performed": False,
        "evidence_clock_started": False,
        "ibkr_call_performed": False,
        "secret_slot_touched": False,
        "order_routed": False,
        "bybit_ipc_reused": False,
        "contract_violations": contract_violations,
        "degraded": reason is not None or bool(contract_violations),
        "reason": reason,
    }
