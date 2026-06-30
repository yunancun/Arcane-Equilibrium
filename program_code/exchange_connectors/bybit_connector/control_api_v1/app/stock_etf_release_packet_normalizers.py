"""Release-packet status normalizers for the Stock/ETF display-only surface."""

from __future__ import annotations

from typing import Any

from .stock_etf_status_common import (
    _DENIED_OPERATIONS,
    _RELEASE_PACKET_CONTRACT_ID,
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

_MIN_REVIEWER_ROLE_COUNT = 8


def _release_packet_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_contract_id": _RELEASE_PACKET_CONTRACT_ID,
        "packet_id": "",
        "source_version": 0,
        "accepted": False,
        "blockers": [reason],
        "adr_path": "",
        "amd_path": "",
        "spec_path": "",
        "source_commit_present": False,
        "created_at_ms": 0,
        "reviewer_role_count": 0,
        "reviewer_roles": [],
        "role_report_count": 0,
        "e2_log_hash_present": False,
        "e3_redaction_log_hash_present": False,
        "e4_log_hash_present": False,
        "qa_log_hash_present": False,
        "manifest_hash_count": 0,
        "manifest_hashes": [],
        "pg_migrations_declared": False,
        "pg_migration_manifest_hash_present": False,
        "pg_dry_run_log_hash_present": False,
        "pg_double_apply_log_hash_present": False,
        "redaction_fixture_hash_present": False,
        "gui_screenshot_hash_count": 0,
        "dq_manifest_hash_count": 0,
        "scorecard_regeneration_hash_count": 0,
        "evidence_archive_pointer_present": False,
        "evidence_archive_hash_present": False,
        "paper_shadow_window_complete": False,
        "engineering_shakedown_complete": False,
        "secret_content_serialized": False,
        "ibkr_live_or_tiny_live_authorized": False,
        "sealed": False,
        "kill_disable_cleanup_proof": _kill_proof_fail_closed(reason),
    }


def _kill_proof_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "stock_etf_lane_enabled_false": False,
        "ibkr_readonly_enabled_false": False,
        "ibkr_paper_enabled_false": False,
        "stock_etf_shadow_only_true": False,
        "collector_stopped": False,
        "gui_stock_views_disabled_or_hidden": False,
        "live_secret_absence_proven": False,
        "evidence_archive_forward_only": False,
        "destructive_db_cleanup_requested": False,
        "proof_hash_present": False,
        "blockers": [reason],
    }


def _normalize_manifest_hash(value: Any) -> dict[str, Any]:
    source = _as_dict(value)
    return {
        "label": _as_str(source.get("label"), ""),
        "hash_present": _as_bool(source.get("hash_present")),
    }


def _normalize_kill_proof(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _kill_proof_fail_closed(reason or "missing_kill_disable_cleanup_proof")
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "stock_etf_lane_enabled_false": _as_bool(
            source.get("stock_etf_lane_enabled_false")
        ),
        "ibkr_readonly_enabled_false": _as_bool(
            source.get("ibkr_readonly_enabled_false")
        ),
        "ibkr_paper_enabled_false": _as_bool(source.get("ibkr_paper_enabled_false")),
        "stock_etf_shadow_only_true": _as_bool(
            source.get("stock_etf_shadow_only_true")
        ),
        "collector_stopped": _as_bool(source.get("collector_stopped")),
        "gui_stock_views_disabled_or_hidden": _as_bool(
            source.get("gui_stock_views_disabled_or_hidden")
        ),
        "live_secret_absence_proven": _as_bool(
            source.get("live_secret_absence_proven")
        ),
        "evidence_archive_forward_only": _as_bool(
            source.get("evidence_archive_forward_only")
        ),
        "destructive_db_cleanup_requested": _as_bool(
            source.get("destructive_db_cleanup_requested")
        ),
        "proof_hash_present": _as_bool(source.get("proof_hash_present")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
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
        "adr_path": _as_str(source.get("adr_path"), ""),
        "amd_path": _as_str(source.get("amd_path"), ""),
        "spec_path": _as_str(source.get("spec_path"), ""),
        "source_commit_present": _as_bool(source.get("source_commit_present")),
        "created_at_ms": _as_int(source.get("created_at_ms")),
        "reviewer_role_count": _as_int(source.get("reviewer_role_count")),
        "reviewer_roles": [str(item) for item in _as_list(source.get("reviewer_roles"))],
        "role_report_count": _as_int(source.get("role_report_count")),
        "e2_log_hash_present": _as_bool(source.get("e2_log_hash_present")),
        "e3_redaction_log_hash_present": _as_bool(
            source.get("e3_redaction_log_hash_present")
        ),
        "e4_log_hash_present": _as_bool(source.get("e4_log_hash_present")),
        "qa_log_hash_present": _as_bool(source.get("qa_log_hash_present")),
        "manifest_hash_count": _as_int(source.get("manifest_hash_count")),
        "manifest_hashes": [
            _normalize_manifest_hash(item)
            for item in _as_list(source.get("manifest_hashes"))
        ],
        "pg_migrations_declared": _as_bool(source.get("pg_migrations_declared")),
        "pg_migration_manifest_hash_present": _as_bool(
            source.get("pg_migration_manifest_hash_present")
        ),
        "pg_dry_run_log_hash_present": _as_bool(
            source.get("pg_dry_run_log_hash_present")
        ),
        "pg_double_apply_log_hash_present": _as_bool(
            source.get("pg_double_apply_log_hash_present")
        ),
        "redaction_fixture_hash_present": _as_bool(
            source.get("redaction_fixture_hash_present")
        ),
        "gui_screenshot_hash_count": _as_int(source.get("gui_screenshot_hash_count")),
        "dq_manifest_hash_count": _as_int(source.get("dq_manifest_hash_count")),
        "scorecard_regeneration_hash_count": _as_int(
            source.get("scorecard_regeneration_hash_count")
        ),
        "evidence_archive_pointer_present": _as_bool(
            source.get("evidence_archive_pointer_present")
        ),
        "evidence_archive_hash_present": _as_bool(
            source.get("evidence_archive_hash_present")
        ),
        "paper_shadow_window_complete": _as_bool(
            source.get("paper_shadow_window_complete")
        ),
        "engineering_shakedown_complete": _as_bool(
            source.get("engineering_shakedown_complete")
        ),
        "secret_content_serialized": _as_bool(source.get("secret_content_serialized")),
        "ibkr_live_or_tiny_live_authorized": _as_bool(
            source.get("ibkr_live_or_tiny_live_authorized")
        ),
        "sealed": _as_bool(source.get("sealed")),
        "kill_disable_cleanup_proof": _normalize_kill_proof(
            source.get("kill_disable_cleanup_proof"), reason
        ),
    }


def _release_packet_contract_violations(
    source: dict[str, Any],
    phase2: dict[str, Any],
    release_packet: dict[str, Any],
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
    if (
        _as_str(release_packet.get("expected_contract_id"), "")
        != _RELEASE_PACKET_CONTRACT_ID
    ):
        violations.append("release_expected_contract_id_mismatch")
    if not _as_bool(release_packet.get("accepted")):
        violations.append("release_packet_not_accepted")
    if not _as_bool(release_packet.get("source_commit_present")):
        violations.append("source_commit_missing")
    if _as_int(release_packet.get("reviewer_role_count")) < _MIN_REVIEWER_ROLE_COUNT:
        violations.append("reviewer_role_count_below_minimum")
    for role in ("PM", "Operator", "E2", "E3", "E4", "QA", "QC", "MIT"):
        if role not in set(release_packet.get("reviewer_roles") or []):
            violations.append(f"reviewer_role_{role}_missing")
    for key in (
        "role_report_count",
        "manifest_hash_count",
        "gui_screenshot_hash_count",
        "dq_manifest_hash_count",
        "scorecard_regeneration_hash_count",
    ):
        if _as_int(release_packet.get(key)) <= 0:
            violations.append(f"{key}_missing")
    for key in (
        "e2_log_hash_present",
        "e3_redaction_log_hash_present",
        "e4_log_hash_present",
        "qa_log_hash_present",
        "redaction_fixture_hash_present",
        "evidence_archive_pointer_present",
        "evidence_archive_hash_present",
        "paper_shadow_window_complete",
        "engineering_shakedown_complete",
        "sealed",
    ):
        if not _as_bool(release_packet.get(key)):
            violations.append(f"release_{key}_missing")
    if _as_bool(release_packet.get("secret_content_serialized")):
        violations.append("release_secret_content_serialized")
    if _as_bool(release_packet.get("ibkr_live_or_tiny_live_authorized")):
        violations.append("release_ibkr_live_or_tiny_live_authorized")
    if _as_bool(release_packet.get("pg_migrations_declared")):
        for key in (
            "pg_migration_manifest_hash_present",
            "pg_dry_run_log_hash_present",
            "pg_double_apply_log_hash_present",
        ):
            if not _as_bool(release_packet.get(key)):
                violations.append(f"{key}_missing")
    for item in _as_list(release_packet.get("manifest_hashes")):
        manifest = _normalize_manifest_hash(item)
        label = manifest["label"] or "unknown"
        if not _as_bool(manifest.get("hash_present")):
            violations.append(f"manifest_{label}_hash_missing")

    kill = _as_dict(release_packet.get("kill_disable_cleanup_proof"))
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
        if not _as_bool(kill.get(key)):
            violations.append(f"kill_{key}_missing")
    if _as_bool(kill.get("destructive_db_cleanup_requested")):
        violations.append("kill_destructive_db_cleanup_requested")

    api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
    violations.extend(_api_allowlist_contract_violations(api_allowlist))
    return violations


def _normalize_release_packet_status(raw: Any, reason: str | None) -> dict[str, Any]:
    source = _as_dict(raw)
    phase2 = _as_dict(source.get("phase2")) or _phase2_fail_closed()
    external_surface_gate = _as_dict(phase2.get("external_surface_gate"))
    api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
    release_packet = _normalize_release_packet(source.get("release_packet"), reason)
    contract_violations = _release_packet_contract_violations(
        source,
        phase2,
        release_packet,
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
    elif not release_packet["accepted"]:
        status_state = "blocked"

    return {
        "api_version": "v1",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "environment": "paper_shadow",
        "gui_authority": "display_only",
        "release_packet_status_state": status_state,
        "phase": _as_str(
            source.get("phase"), "phase5_release_packet_status_source_fixture"
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
        "release_packet": release_packet,
        "phase3_started": False,
        "phase5_started": False,
        "ibkr_live_enabled": False,
        "stock_live_disabled": True,
        "paper_order_entry_visible": False,
        "allowed_gui_actions": ["refresh_release_packet_status"],
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
