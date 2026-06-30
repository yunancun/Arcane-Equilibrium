"""Launch-status normalizers for the Stock/ETF display-only surface."""

from __future__ import annotations

from typing import Any

from .stock_etf_status_common import (
    _DENIED_OPERATIONS,
    _DISABLE_CLEANUP_RUNBOOK_ID,
    _RELEASE_PACKET_CONTRACT_ID,
    _SAFETY_FALSE_FIELDS,
    _TINY_LIVE_ADR_ELIGIBILITY_CONTRACT_ID,
    _api_allowlist_contract_violations,
    _as_bool,
    _as_dict,
    _as_int,
    _as_list,
    _as_str,
    _normalize_api_allowlist,
    _phase2_fail_closed,
)


def _release_packet_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_contract_id": _RELEASE_PACKET_CONTRACT_ID,
        "packet_id": "",
        "source_version": 0,
        "accepted": False,
        "blockers": [reason],
        "paper_shadow_window_complete": False,
        "engineering_shakedown_complete": False,
        "role_report_count": 0,
        "manifest_hash_count": 0,
        "gui_screenshot_hash_count": 0,
        "dq_manifest_hash_count": 0,
        "scorecard_regeneration_hash_count": 0,
        "pg_migrations_declared": False,
        "pg_dry_run_log_hash_present": False,
        "pg_double_apply_log_hash_present": False,
        "redaction_fixture_hash_present": False,
        "evidence_archive_pointer_present": False,
        "evidence_archive_hash_present": False,
        "secret_content_serialized": False,
        "ibkr_live_or_tiny_live_authorized": False,
        "sealed": False,
    }


def _runbook_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_runbook_id": _DISABLE_CLEANUP_RUNBOOK_ID,
        "runbook_id": "",
        "source_version": 0,
        "accepted": False,
        "blockers": [reason],
        "bybit_live_execution_unchanged": False,
        "env_flag_count": 0,
        "proof_count": 0,
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


def _tiny_live_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_contract_id": _TINY_LIVE_ADR_ELIGIBILITY_CONTRACT_ID,
        "contract_id": "",
        "source_version": 0,
        "accepted": False,
        "blockers": [reason],
        "decision": "not_eligible",
        "paper_shadow_window_complete": False,
        "benchmark_relative_after_cost_lcb_bps": 0,
        "independent_observation_count": 0,
        "min_independent_observation_count": 0,
        "conservative_cost_stress_lcb_bps": 0,
        "paper_shadow_divergence_bps": 0,
        "max_paper_shadow_divergence_bps": 0,
        "concentration_label_passed": False,
        "regime_label_passed": False,
        "freshness_label_passed": False,
        "qc_review_passed": False,
        "mit_review_passed": False,
        "secret_content_serialized": False,
        "sealed": False,
    }


def _normalize_release_packet(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _release_packet_fail_closed(reason or "missing_release_packet")
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "expected_contract_id": _as_str(
            source.get("expected_contract_id"), _RELEASE_PACKET_CONTRACT_ID
        ),
        "packet_id": _as_str(source.get("packet_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "accepted": _as_bool(source.get("accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "paper_shadow_window_complete": _as_bool(
            source.get("paper_shadow_window_complete")
        ),
        "engineering_shakedown_complete": _as_bool(
            source.get("engineering_shakedown_complete")
        ),
        "role_report_count": _as_int(source.get("role_report_count")),
        "manifest_hash_count": _as_int(source.get("manifest_hash_count")),
        "gui_screenshot_hash_count": _as_int(source.get("gui_screenshot_hash_count")),
        "dq_manifest_hash_count": _as_int(source.get("dq_manifest_hash_count")),
        "scorecard_regeneration_hash_count": _as_int(
            source.get("scorecard_regeneration_hash_count")
        ),
        "pg_migrations_declared": _as_bool(source.get("pg_migrations_declared")),
        "pg_dry_run_log_hash_present": _as_bool(
            source.get("pg_dry_run_log_hash_present")
        ),
        "pg_double_apply_log_hash_present": _as_bool(
            source.get("pg_double_apply_log_hash_present")
        ),
        "redaction_fixture_hash_present": _as_bool(
            source.get("redaction_fixture_hash_present")
        ),
        "evidence_archive_pointer_present": _as_bool(
            source.get("evidence_archive_pointer_present")
        ),
        "evidence_archive_hash_present": _as_bool(
            source.get("evidence_archive_hash_present")
        ),
        "secret_content_serialized": _as_bool(source.get("secret_content_serialized")),
        "ibkr_live_or_tiny_live_authorized": _as_bool(
            source.get("ibkr_live_or_tiny_live_authorized")
        ),
        "sealed": _as_bool(source.get("sealed")),
    }


def _normalize_disable_cleanup_runbook(
    value: Any, reason: str | None
) -> dict[str, Any]:
    fallback = _runbook_fail_closed(reason or "missing_disable_cleanup_runbook")
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
        "bybit_live_execution_unchanged": _as_bool(
            source.get("bybit_live_execution_unchanged")
        ),
        "env_flag_count": _as_int(source.get("env_flag_count")),
        "proof_count": _as_int(source.get("proof_count")),
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


def _normalize_tiny_live_adr_eligibility(
    value: Any, reason: str | None
) -> dict[str, Any]:
    fallback = _tiny_live_fail_closed(reason or "missing_tiny_live_adr_eligibility")
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "expected_contract_id": _as_str(
            source.get("expected_contract_id"),
            _TINY_LIVE_ADR_ELIGIBILITY_CONTRACT_ID,
        ),
        "contract_id": _as_str(source.get("contract_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "accepted": _as_bool(source.get("accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "decision": _as_str(source.get("decision"), "not_eligible"),
        "paper_shadow_window_complete": _as_bool(
            source.get("paper_shadow_window_complete")
        ),
        "benchmark_relative_after_cost_lcb_bps": _as_int(
            source.get("benchmark_relative_after_cost_lcb_bps")
        ),
        "independent_observation_count": _as_int(
            source.get("independent_observation_count")
        ),
        "min_independent_observation_count": _as_int(
            source.get("min_independent_observation_count")
        ),
        "conservative_cost_stress_lcb_bps": _as_int(
            source.get("conservative_cost_stress_lcb_bps")
        ),
        "paper_shadow_divergence_bps": _as_int(
            source.get("paper_shadow_divergence_bps")
        ),
        "max_paper_shadow_divergence_bps": _as_int(
            source.get("max_paper_shadow_divergence_bps")
        ),
        "concentration_label_passed": _as_bool(
            source.get("concentration_label_passed")
        ),
        "regime_label_passed": _as_bool(source.get("regime_label_passed")),
        "freshness_label_passed": _as_bool(source.get("freshness_label_passed")),
        "qc_review_passed": _as_bool(source.get("qc_review_passed")),
        "mit_review_passed": _as_bool(source.get("mit_review_passed")),
        "secret_content_serialized": _as_bool(source.get("secret_content_serialized")),
        "sealed": _as_bool(source.get("sealed")),
    }


def _launch_status_contract_violations(
    source: dict[str, Any],
    phase2: dict[str, Any],
    release_packet: dict[str, Any],
    runbook: dict[str, Any],
    tiny_live: dict[str, Any],
    reason: str | None,
) -> list[str]:
    violations = [
        field for field in _SAFETY_FALSE_FIELDS if _as_bool(source.get(field))
    ]
    for key in (
        "phase3_started",
        "phase5_started",
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
    if _as_str(release_packet.get("expected_contract_id"), "") != _RELEASE_PACKET_CONTRACT_ID:
        violations.append("release_expected_contract_id_mismatch")
    if _as_str(runbook.get("expected_runbook_id"), "") != _DISABLE_CLEANUP_RUNBOOK_ID:
        violations.append("runbook_expected_id_mismatch")
    if (
        _as_str(tiny_live.get("expected_contract_id"), "")
        != _TINY_LIVE_ADR_ELIGIBILITY_CONTRACT_ID
    ):
        violations.append("tiny_live_expected_contract_id_mismatch")
    if _as_bool(release_packet.get("accepted")):
        violations.append("release_packet_accepted_before_launch_audit")
    if _as_bool(runbook.get("accepted")):
        violations.append("disable_cleanup_runbook_accepted_before_launch_audit")
    if _as_bool(tiny_live.get("accepted")):
        violations.append("tiny_live_eligibility_accepted_before_launch_audit")
    for prefix, payload, boolean_keys in (
        (
            "release",
            release_packet,
            (
                "paper_shadow_window_complete",
                "engineering_shakedown_complete",
                "pg_migrations_declared",
                "pg_dry_run_log_hash_present",
                "pg_double_apply_log_hash_present",
                "redaction_fixture_hash_present",
                "evidence_archive_pointer_present",
                "evidence_archive_hash_present",
                "secret_content_serialized",
                "ibkr_live_or_tiny_live_authorized",
                "sealed",
            ),
        ),
        (
            "runbook",
            runbook,
            (
                "bybit_live_execution_unchanged",
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
            ),
        ),
        (
            "tiny_live",
            tiny_live,
            (
                "paper_shadow_window_complete",
                "concentration_label_passed",
                "regime_label_passed",
                "freshness_label_passed",
                "qc_review_passed",
                "mit_review_passed",
                "secret_content_serialized",
                "sealed",
            ),
        ),
    ):
        for key in boolean_keys:
            if _as_bool(payload.get(key)):
                violations.append(f"{prefix}_{key}")
    for prefix, payload, count_keys in (
        (
            "release",
            release_packet,
            (
                "role_report_count",
                "manifest_hash_count",
                "gui_screenshot_hash_count",
                "dq_manifest_hash_count",
                "scorecard_regeneration_hash_count",
            ),
        ),
        ("runbook", runbook, ("env_flag_count", "proof_count")),
        (
            "tiny_live",
            tiny_live,
            (
                "benchmark_relative_after_cost_lcb_bps",
                "independent_observation_count",
                "min_independent_observation_count",
                "conservative_cost_stress_lcb_bps",
                "paper_shadow_divergence_bps",
                "max_paper_shadow_divergence_bps",
            ),
        ),
    ):
        for key in count_keys:
            if _as_int(payload.get(key)) != 0:
                violations.append(f"{prefix}_{key}_present")
    if _as_str(tiny_live.get("decision"), "not_eligible") != "not_eligible":
        violations.append("tiny_live_decision_not_blocked")
    api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
    violations.extend(_api_allowlist_contract_violations(api_allowlist))
    return violations


def _normalize_launch_status(raw: Any, reason: str | None) -> dict[str, Any]:
    source = _as_dict(raw)
    phase2 = _as_dict(source.get("phase2")) or _phase2_fail_closed()
    external_surface_gate = _as_dict(phase2.get("external_surface_gate"))
    api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
    release_packet = _normalize_release_packet(source.get("release_packet"), reason)
    runbook = _normalize_disable_cleanup_runbook(
        source.get("disable_cleanup_runbook"), reason
    )
    tiny_live = _normalize_tiny_live_adr_eligibility(
        source.get("tiny_live_adr_eligibility"), reason
    )

    contract_violations = _launch_status_contract_violations(
        source,
        phase2,
        release_packet,
        runbook,
        tiny_live,
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

    return {
        "api_version": "v1",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "environment": "paper_shadow",
        "gui_authority": "display_only",
        "launch_status_state": status_state,
        "phase": _as_str(source.get("phase"), "phase5_launch_status_source_fixture"),
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
        "release_packet": release_packet,
        "disable_cleanup_runbook": runbook,
        "tiny_live_adr_eligibility": tiny_live,
        "phase3_started": False,
        "phase5_started": False,
        "ibkr_live_enabled": False,
        "stock_live_disabled": True,
        "paper_order_entry_visible": False,
        "allowed_gui_actions": ["refresh_launch_status"],
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
