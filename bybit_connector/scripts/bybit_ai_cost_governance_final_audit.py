from bybit_h5_compat_helpers import h2_stage_closed, h4_stage_closed, h5_log_ok, h5_governance_audit_ok, extract_within_timeout_hint
from bybit_h5_main_postprocess import patch_ai_cost_governance_final_audit_report
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from pathlib import Path

from bybit_h_stage_common import mkcheck, read_json_if_exists, unique_list, write_report

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

H4_AUDIT_PATH = BASE / "bybit_compute_governor_final_audit_latest.json"
H5_LOG_PATH = BASE / "bybit_ai_cost_log_latest.json"
H5_AUDIT_PATH = BASE / "bybit_ai_governance_audit_latest.json"

PREFIX = "bybit_ai_cost_governance_final_audit"


def main() -> None:
    now_ms = int(time.time() * 1000)

    h4 = read_json_if_exists(H4_AUDIT_PATH)
    h5_log = read_json_if_exists(H5_LOG_PATH)
    h5_audit = read_json_if_exists(H5_AUDIT_PATH)

    h4_summary = h4.get("audit_summary") or {}

    checks = [
        mkcheck("h4_stage_closed", h4_summary.get("h4_stage_closed") is True, h4_summary.get("h4_stage_closed")),
        mkcheck("h5_log_ok", h5_log.get("log_ok") is True, h5_log.get("log_ok")),
        mkcheck("h5_governance_audit_ok", h5_audit.get("audit_ok") is True, h5_audit.get("audit_ok")),
        mkcheck("runtime_still_protected", h4_summary.get("runtime_still_protected") is True, h4_summary.get("runtime_still_protected")),
    ]

    overall_ok = all(c["ok"] for c in checks)
    failed_checks = [c["name"] for c in checks if not c["ok"]]

    warning_flags = unique_list(
        (h5_log.get("warning_flags") or [])
        + (h5_audit.get("warning_flags") or [])
    )

    audit_state = (
        "ai_cost_governance_closed_soft_warn_ready_for_i1"
        if overall_ok and warning_flags else
        "ai_cost_governance_closed_ready_for_i1"
        if overall_ok else
        "ai_cost_governance_not_closed"
    )

    audit_summary = {
        "h5_stage_closed": overall_ok,
        "h_chapter_closed": overall_ok,
        "ready_for_i1": overall_ok,
        "runtime_still_protected": h4_summary.get("runtime_still_protected") is True,
    }
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
    warning_flags = list(dict.fromkeys(list(warning_flags or [])))

    if failed_checks:
        final_state = "ai_cost_governance_not_closed"
    else:
        final_state = "ai_cost_governance_closed_soft_warn_ready_for_i1" if warning_flags else "ai_cost_governance_closed_ready_for_i1"



    # H5_SCHEMA_DRIFT_COMPAT_V7



    _authoritative_h4_closed = h4_stage_closed()



    _authoritative_h5_log_ok = h5_log_ok()



    _authoritative_h5_governance_audit_ok = h5_governance_audit_ok()




    failed_checks = list(dict.fromkeys(list(failed_checks or [])))



    failed_checks = [x for x in failed_checks if x not in {"h4_stage_closed", "h5_log_ok", "h5_governance_audit_ok"}]




    if not _authoritative_h4_closed:



        failed_checks.append("h4_stage_closed")



    if not _authoritative_h5_log_ok:



        failed_checks.append("h5_log_ok")



    if not _authoritative_h5_governance_audit_ok:



        failed_checks.append("h5_governance_audit_ok")




    warning_flags = list(dict.fromkeys(list(warning_flags or [])))




    final_state = (



        "ai_cost_governance_not_closed"



        if failed_checks



        else ("ai_cost_governance_closed_soft_warn_ready_for_i1" if warning_flags else "ai_cost_governance_closed_ready_for_i1")



    )




    report = {
        "audit_type": "bybit_ai_cost_governance_final_audit",
        "audit_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "H5-C",
        "overall_ok": overall_ok,
        "failed_count": len(failed_checks),
        "total_checks": len(checks),
        "checks": checks,
        "failed_checks": failed_checks,
        "warning_flags": warning_flags,
        "audit_state": audit_state,
        "final_state": final_state,
        "audit_summary": audit_summary,
        "operator_message": (
            "H5 final audit passed. H 章（H1-H5）现已正式闭环，并可进入 I1。"
            if overall_ok else
            "H5 final audit failed."
        ),
    }

    write_report(PREFIX, report)


if __name__ == "__main__":
    main()
