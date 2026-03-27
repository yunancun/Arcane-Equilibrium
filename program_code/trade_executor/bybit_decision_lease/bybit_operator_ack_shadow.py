#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
from pathlib import Path
from typing import Any, Dict, List
from bybit_decision_lease_common import read_json, save_report, as_list, merged_unique

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

I8_PACKET_PATH = BASE / "bybit_manual_approval_packet_latest.json"
I8_AUDIT_PATH = BASE / "bybit_manual_approval_packet_final_audit_latest.json"
I7_AUTH_PATH = BASE / "bybit_execution_authority_aggregator_latest.json"

LATEST_PATH = BASE / "bybit_operator_ack_shadow_latest.json"


def main() -> None:
    now_ms = int(time.time() * 1000)

    i8_packet = read_json(I8_PACKET_PATH)
    i8_audit = read_json(I8_AUDIT_PATH)
    i7_auth = read_json(I7_AUTH_PATH)

    source_errors: List[str] = []
    if i8_packet is None:
        source_errors.append("i8_manual_approval_packet_missing_or_invalid")
    if i8_audit is None:
        source_errors.append("i8_manual_approval_packet_final_audit_missing_or_invalid")
    if i7_auth is None:
        source_errors.append("i7_execution_authority_aggregator_missing_or_invalid")

    packet_runtime = (i8_packet or {}).get("packet_runtime_view") or {}
    packet_summary = (i8_packet or {}).get("request_summary") or {}
    audit_summary = (i8_audit or {}).get("audit_summary") or {}
    authority_guards = (i7_auth or {}).get("governance_guards") or {}
    authority_view = (i7_auth or {}).get("aggregated_authority_view") or {}

    i8_stage_closed = bool(audit_summary.get("i8_stage_closed", False))
    packet_for_review_only = bool(packet_runtime.get("packet_for_review_only", False))
    approval_submit_live = bool(packet_runtime.get("approval_submit_live", False))
    operator_review_required = bool(packet_runtime.get("operator_review_required", True))
    execution_authority = packet_runtime.get("execution_authority", "unknown")
    live_execution_allowed = bool(packet_runtime.get("live_execution_allowed", False))
    decision_lease_emitted = bool(packet_runtime.get("decision_lease_emitted", False))

    operator_ack_shadow_only = True
    live_operator_ack_enabled = False
    operator_ack_record_emitted_live = False

    required_ack_fields = [
        "operator_id",
        "operator_role",
        "ack_ts_ms",
        "ack_reason",
        "review_packet_id",
        "review_conclusion",
    ]

    operator_ack_shadow = {
        "ack_mode": "shadow_review_only",
        "operator_ack_required": True,
        "operator_ack_shadow_only": operator_ack_shadow_only,
        "live_operator_ack_enabled": live_operator_ack_enabled,
        "operator_ack_record_emitted_live": operator_ack_record_emitted_live,
        "required_ack_fields": required_ack_fields,
        "current_ack_payload_bound": False,
        "review_packet_reference": {
            "packet_type": (i8_packet or {}).get("packet_type"),
            "packet_version": (i8_packet or {}).get("packet_version"),
            "packet_ts_ms": (i8_packet or {}).get("ts_ms"),
        },
        "authority_reference": {
            "execution_authority_required": authority_view.get("execution_authority_required"),
            "execution_authority": authority_view.get("execution_authority"),
            "execution_authority_granted": authority_view.get("execution_authority_granted"),
            "live_execution_allowed": authority_view.get("live_execution_allowed"),
        },
    }

    ack_ok = (
        len(source_errors) == 0
        and i8_stage_closed
        and packet_for_review_only
        and not approval_submit_live
        and operator_review_required
        and execution_authority == "not_granted"
        and not live_execution_allowed
        and not decision_lease_emitted
    )

    blocking_reasons: List[str] = list(source_errors)
    if not i8_stage_closed:
        blocking_reasons.append("i8_stage_not_closed")
    if not packet_for_review_only:
        blocking_reasons.append("packet_not_review_only")
    if approval_submit_live:
        blocking_reasons.append("approval_submit_live_unexpected")
    if execution_authority != "not_granted":
        blocking_reasons.append("execution_authority_not_safe")
    if live_execution_allowed:
        blocking_reasons.append("live_execution_allowed_unexpected")
    if decision_lease_emitted:
        blocking_reasons.append("decision_lease_emitted_unexpected")

    if ack_ok:
        ack_state = "operator_ack_shadow_ready_soft_warn"
        allow_progress_to_i10_finalization = True
        recommended_action = "may_progress_to_i10_finalization"
        operator_message = (
            "I9 operator acknowledgment shadow built. "
            "Human acknowledgment is now structured in shadow mode only, without granting live authority."
        )
    else:
        ack_state = "operator_ack_shadow_blocked"
        allow_progress_to_i10_finalization = False
        recommended_action = "inspect_i9_operator_ack_blockers"
        operator_message = "I9 operator acknowledgment shadow blocked."

    warning_flags = merged_unique(
        (i8_packet or {}).get("warning_flags"),
        (i8_audit or {}).get("warning_flags"),
        (i7_auth or {}).get("warning_flags"),
        [
            "operator_ack_shadow_only_mode",
            "live_operator_ack_not_active",
            "operator_review_pending" if operator_review_required else None,
            "execution_authority_not_granted" if execution_authority != "granted" else None,
        ],
    )

    report = {
        "ack_type": "bybit_operator_ack_shadow",
        "ack_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "I9",
        "ack_ok": ack_ok,
        "source_refs": {
            "i8_manual_approval_packet_path": str(I8_PACKET_PATH),
            "i8_manual_approval_packet_final_audit_path": str(I8_AUDIT_PATH),
            "i7_execution_authority_aggregator_path": str(I7_AUTH_PATH),
        },
        "source_integrity": {
            "i8_manual_approval_packet_present": i8_packet is not None,
            "i8_manual_approval_packet_final_audit_present": i8_audit is not None,
            "i7_execution_authority_aggregator_present": i7_auth is not None,
            "source_errors": source_errors,
        },
        "request_summary": {
            "provider_target": packet_summary.get("provider_target"),
            "model_name": packet_summary.get("model_name"),
            "selected_ai_tier": packet_summary.get("selected_ai_tier"),
            "route_plan": packet_summary.get("route_plan"),
        },
        "ack_runtime_view": {
            "operator_ack_shadow_only": operator_ack_shadow_only,
            "live_operator_ack_enabled": live_operator_ack_enabled,
            "operator_review_required": operator_review_required,
            "execution_authority": execution_authority,
            "live_execution_allowed": live_execution_allowed,
            "decision_lease_emitted": decision_lease_emitted,
            "approval_submit_live": approval_submit_live,
            "packet_for_review_only": packet_for_review_only,
        },
        "operator_ack_shadow": operator_ack_shadow,
        "blocking_reasons": blocking_reasons,
        "warning_flags": warning_flags,
        "ack_state": ack_state,
        "allow_progress_to_i10_finalization": allow_progress_to_i10_finalization,
        "recommended_action": recommended_action,
        "operator_message": operator_message,
    }

    save_report(report, LATEST_PATH, print_json=True)


if __name__ == "__main__":
    main()
