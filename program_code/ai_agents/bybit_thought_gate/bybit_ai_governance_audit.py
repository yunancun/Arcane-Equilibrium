#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from pathlib import Path

from bybit_path_policy import get_thought_gate_runtime_dir

from bybit_h_stage_common import mkcheck, read_json_if_exists, unique_list, write_report

BASE = get_thought_gate_runtime_dir()

H1_AUDIT_PATH = BASE / "bybit_thought_gate_final_audit_latest.json"
H2_AUDIT_PATH = BASE / "bybit_query_budget_final_audit_latest.json"
H3_AUDIT_PATH = BASE / "bybit_model_router_final_audit_latest.json"
H4_AUDIT_PATH = BASE / "bybit_compute_governor_final_audit_latest.json"
H5_LOG_PATH = BASE / "bybit_ai_cost_log_latest.json"
H1_GOV_PATH = BASE / "bybit_ai_governed_decision_latest.json"
INV_PATH = BASE / "bybit_ai_invocation_attempt_latest.json"

PREFIX = "bybit_ai_governance_audit"


def main() -> None:
    now_ms = int(time.time() * 1000)

    h1 = read_json_if_exists(H1_AUDIT_PATH)
    h2 = read_json_if_exists(H2_AUDIT_PATH)
    h3 = read_json_if_exists(H3_AUDIT_PATH)
    h4 = read_json_if_exists(H4_AUDIT_PATH)
    h5 = read_json_if_exists(H5_LOG_PATH)
    gov = read_json_if_exists(H1_GOV_PATH)
    inv = read_json_if_exists(INV_PATH)

    h1_summary = h1.get("audit_summary") or {}
    h2_summary = h2.get("audit_summary") or {}
    h3_summary = h3.get("audit_summary") or {}
    h4_summary = h4.get("audit_summary") or {}

    governance_guards = gov.get("governance_guards") or {}
    attempt_result = inv.get("attempt_result") or {}
    transport_summary = inv.get("transport_summary") or {}
    h5_cost_log = h5.get("cost_log") or {}

    no_call_path_accepted = (
        h4_summary.get("no_call_path_accepted") is True
        or h5_cost_log.get("no_call_path_accepted") is True
        or (h5.get("request_summary") or {}).get("should_call_ai") is False
    )

    checks = [
        mkcheck("h1_stage_closed", h1_summary.get("h1_stage_closed") is True, h1_summary.get("h1_stage_closed")),
        mkcheck("h2_stage_closed", h2_summary.get("h2_stage_closed") is True, h2_summary.get("h2_stage_closed")),
        mkcheck("h3_stage_closed", h3_summary.get("h3_stage_closed") is True, h3_summary.get("h3_stage_closed")),
        mkcheck("h4_stage_closed", h4_summary.get("h4_stage_closed") is True, h4_summary.get("h4_stage_closed")),
        mkcheck("ai_cost_log_ok", h5.get("log_ok") is True, h5.get("log_ok")),
        mkcheck("system_mode_read_only", governance_guards.get("system_mode") == "read_only", governance_guards.get("system_mode")),
        mkcheck("execution_state_disabled", governance_guards.get("execution_state") == "disabled", governance_guards.get("execution_state")),
        mkcheck("execution_authority_not_granted", governance_guards.get("execution_authority") == "not_granted", governance_guards.get("execution_authority")),
        mkcheck("live_execution_allowed_false", governance_guards.get("live_execution_allowed") is False, governance_guards.get("live_execution_allowed")),
        mkcheck("decision_lease_emitted_false", governance_guards.get("decision_lease_emitted") is False, governance_guards.get("decision_lease_emitted")),
        mkcheck("max_retries_zero", transport_summary.get("max_retries") == 0, transport_summary.get("max_retries")),
        mkcheck(
            "parsed_json_present_true_or_no_call_path",
            (attempt_result.get("parsed_json_present") is True) or no_call_path_accepted,
            {"parsed_json_present": attempt_result.get("parsed_json_present"), "no_call_path_accepted": no_call_path_accepted},
        ),
    ]

    audit_ok = all(c["ok"] for c in checks)
    failed_checks = [c["name"] for c in checks if not c["ok"]]

    warning_flags = unique_list(
        (h5.get("warning_flags") or [])
        + (inv.get("warning_flags") or [])
    )

    audit_state = (
        "ai_governance_audit_passed_soft_warn"
        if audit_ok and warning_flags else
        "ai_governance_audit_passed"
        if audit_ok else
        "ai_governance_audit_blocked"
    )

    report = {
        "audit_type": "bybit_ai_governance_audit",
        "audit_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "H5-B",
        "audit_ok": audit_ok,
        "source_refs": {
            "thought_gate_final_audit_path": str(H1_AUDIT_PATH),
            "query_budget_final_audit_path": str(H2_AUDIT_PATH),
            "model_router_final_audit_path": str(H3_AUDIT_PATH),
            "compute_governor_final_audit_path": str(H4_AUDIT_PATH),
            "ai_cost_log_path": str(H5_LOG_PATH),
            "ai_governed_decision_path": str(H1_GOV_PATH),
            "ai_invocation_attempt_path": str(INV_PATH),
        },
        "checks": checks,
        "failed_checks": failed_checks,
        "warning_flags": warning_flags,
        "audit_state": audit_state,
        "allow_progress_to_h5c_final_audit": audit_ok,
        "recommended_action": (
            "may_progress_to_h5c_final_audit"
            if audit_ok else
            "inspect_h5b_governance_audit_failures"
        ),
        "operator_message": (
            "H5-B governance audit passed. 当前主链仍满足只读保护、预算治理与 legal no-call 兼容语义。"
            if audit_ok else
            "H5-B governance audit blocked."
        ),
    }

    write_report(PREFIX, report)


if __name__ == "__main__":
    main()
