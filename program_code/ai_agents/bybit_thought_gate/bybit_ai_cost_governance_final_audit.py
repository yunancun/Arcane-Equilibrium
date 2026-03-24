#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from pathlib import Path

from bybit_path_policy import get_thought_gate_runtime_dir

from bybit_h_stage_common import mkcheck, read_json_if_exists, unique_list, write_report

BASE = get_thought_gate_runtime_dir()

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
    h5_cost_log = h5_log.get("cost_log") or {}

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
        "no_call_path_accepted": (
            h4_summary.get("no_call_path_accepted") is True
            or h5_cost_log.get("no_call_path_accepted") is True
        ),
    }

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
        "final_state": audit_state,
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
