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
H4_POLICY_PATH = BASE / "bybit_compute_governor_policy_latest.json"
H4_GATE_PATH = BASE / "bybit_compute_governor_gate_latest.json"
H4_RUNTIME_PATH = BASE / "bybit_compute_governor_runtime_latest.json"

PREFIX = "bybit_compute_governor_final_audit"


def main() -> None:
    now_ms = int(time.time() * 1000)

    h1 = read_json_if_exists(H1_AUDIT_PATH)
    h2 = read_json_if_exists(H2_AUDIT_PATH)
    h3 = read_json_if_exists(H3_AUDIT_PATH)
    h4_policy = read_json_if_exists(H4_POLICY_PATH)
    h4_gate = read_json_if_exists(H4_GATE_PATH)
    h4_runtime = read_json_if_exists(H4_RUNTIME_PATH)

    h1_summary = h1.get("audit_summary") or {}
    h2_summary = h2.get("audit_summary") or {}
    h3_summary = h3.get("audit_summary") or {}
    h4_runtime_summary = h4_runtime.get("runtime_summary") or {}

    checks = [
        mkcheck("h1_still_closed", h1_summary.get("h1_stage_closed") is True, h1_summary.get("h1_stage_closed")),
        mkcheck("h2_still_closed", h2_summary.get("h2_stage_closed") is True, h2_summary.get("h2_stage_closed")),
        mkcheck("h3_still_closed", h3_summary.get("h3_stage_closed") is True, h3_summary.get("h3_stage_closed")),
        mkcheck("h4_policy_ok", h4_policy.get("policy_ok") is True, h4_policy.get("policy_ok")),
        mkcheck("h4_gate_ok", h4_gate.get("gate_ok") is True, h4_gate.get("gate_ok")),
        mkcheck("h4_runtime_ok", h4_runtime.get("runtime_ok") is True, h4_runtime.get("runtime_ok")),
        mkcheck("runtime_still_protected", h1_summary.get("runtime_still_protected") is True, h1_summary.get("runtime_still_protected")),
    ]

    overall_ok = all(c["ok"] for c in checks)
    failed_checks = [c["name"] for c in checks if not c["ok"]]

    warning_flags = unique_list(
        (h4_policy.get("warning_flags") or [])
        + (h4_gate.get("warning_flags") or [])
        + (h4_runtime.get("warning_flags") or [])
    )

    audit_state = (
        "compute_governor_closed_soft_warn_ready_for_h5"
        if overall_ok and warning_flags else
        "compute_governor_closed_ready_for_h5"
        if overall_ok else
        "compute_governor_not_closed"
    )

    audit_summary = {
        "h4_stage_closed": overall_ok,
        "ready_for_h5": overall_ok,
        "runtime_still_protected": h1_summary.get("runtime_still_protected") is True,
        "no_call_path_accepted": h4_runtime_summary.get("no_call_path_accepted") is True,
    }

    report = {
        "audit_type": "bybit_compute_governor_final_audit",
        "audit_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "H4-D",
        "overall_ok": overall_ok,
        "failed_count": len(failed_checks),
        "total_checks": len(checks),
        "checks": checks,
        "failed_checks": failed_checks,
        "warning_flags": warning_flags,
        "audit_state": audit_state,
        "audit_summary": audit_summary,
        "operator_message": (
            "H4 final audit passed. compute governor / anti-abuse 已正式收口并可进入 H5。"
            if overall_ok else
            "H4 final audit failed."
        ),
    }

    write_report(PREFIX, report)


if __name__ == "__main__":
    main()
