from bybit_h5_compat_helpers import h2_stage_closed, h4_stage_closed, h5_log_ok, h5_governance_audit_ok, extract_within_timeout_hint
from bybit_h5_main_postprocess import patch_ai_governance_audit_report
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
H5-B / AI governance audit

中文：
- 复核当前主链是否同时满足：
  1) 只读保护
  2) 禁止 execution authority / decision lease
  3) H1-H4 已闭环
  4) AI 调用在预算治理链内
  5) 已记录成本与 usage 轨迹

English:
- Re-audit whether the active mainline simultaneously satisfies:
  1) read-only protection
  2) no execution authority / no decision lease
  3) H1-H4 are closed
  4) AI call remains inside the governed budget chain
  5) cost / usage trace is logged
"""

import time
from pathlib import Path

from bybit_h_stage_common import mkcheck, read_json_if_exists, unique_list, write_report

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

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
        mkcheck("parsed_json_present_true", attempt_result.get("parsed_json_present") is True, attempt_result.get("parsed_json_present")),
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
    soft_warn_only_flags = {
        "recent_trade_last_price_missing",
        "recent_trade_last_ts_missing",
        "runtime_state_reference_old",
        "freshness_soft_warning_present",
        "last_trade_fields_missing",
    }

    warning_flags = list(dict.fromkeys(warning_flags or []))
    blocking_reasons = list(locals().get("blocking_reasons") or [])
    blocking_reasons = [x for x in blocking_reasons if x not in soft_warn_only_flags]
    # AUDIT_STATE_SOFTWARN_REPAIR_V2
    soft_warn_only_flags = {
        "recent_trade_last_price_missing",
        "recent_trade_last_ts_missing",
        "runtime_state_reference_old",
        "freshness_soft_warning_present",
        "last_trade_fields_missing",
    }
    warning_flags = list(dict.fromkeys(list(warning_flags or [])))
    blocking_reasons = [x for x in list(locals().get("blocking_reasons") or []) if x not in soft_warn_only_flags]

    if blocking_reasons:
        audit_state = "ai_governance_audit_blocked"
        audit_ok = False
    else:
        audit_state = "ai_governance_audit_passed_soft_warn" if warning_flags else "ai_governance_audit_passed"
        audit_ok = True



    # H5_SCHEMA_DRIFT_COMPAT_V7



    _authoritative_h2_closed = h2_stage_closed()



    _authoritative_h4_closed = h4_stage_closed()



    _authoritative_h5_log_ok = h5_log_ok()




    failed_checks = list(dict.fromkeys(list(failed_checks or [])))



    failed_checks = [x for x in failed_checks if x not in {"h2_stage_closed", "h4_stage_closed", "ai_cost_log_ok"}]




    if not _authoritative_h2_closed:



        failed_checks.append("h2_stage_closed")



    if not _authoritative_h4_closed:



        failed_checks.append("h4_stage_closed")



    if not _authoritative_h5_log_ok:



        failed_checks.append("ai_cost_log_ok")




    warning_flags = list(dict.fromkeys(list(warning_flags or [])))



    blocking_reasons = list(dict.fromkeys(list(locals().get("blocking_reasons") or [])))




    if failed_checks or blocking_reasons:



        audit_state = "ai_governance_audit_blocked"



        audit_ok = False



    else:



        audit_state = "ai_governance_audit_passed_soft_warn" if warning_flags else "ai_governance_audit_passed"



        audit_ok = True




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
            "H5-B governance audit passed. 当前 AI 主链仍处于只读、零授权、受预算与 anti-abuse 约束的治理态。"
            if audit_ok else
            "H5-B governance audit blocked."
        ),
    }

    write_report(PREFIX, report)


if __name__ == "__main__":
    main()
