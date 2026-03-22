#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from pathlib import Path

from bybit_h_stage_common import read_json_if_exists, unique_list, mkcheck, write_report

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")
POLICY_PATH = BASE / "bybit_model_router_policy_latest.json"
DECISION_PATH = BASE / "bybit_model_router_decision_latest.json"
RUNTIME_PATH = BASE / "bybit_model_router_runtime_latest.json"
THOUGHT_GATE_AUDIT_PATH = BASE / "bybit_thought_gate_final_audit_latest.json"

PREFIX = "bybit_model_router_final_audit"


def main() -> None:
    now_ms = int(time.time() * 1000)

    policy = read_json_if_exists(POLICY_PATH)
    decision = read_json_if_exists(DECISION_PATH)
    runtime = read_json_if_exists(RUNTIME_PATH)
    thought_gate_audit = read_json_if_exists(THOUGHT_GATE_AUDIT_PATH)

    tg_summary = thought_gate_audit.get("audit_summary") or {}
    runtime_still_protected = tg_summary.get("runtime_still_protected") is True

    warning_flags = unique_list(
        (policy.get("warning_flags") or [])
        + (decision.get("warning_flags") or [])
        + (runtime.get("warning_flags") or [])
    )

    checks = [
        mkcheck("thought_gate_still_closed", tg_summary.get("h1_stage_closed") is True, tg_summary.get("h1_stage_closed")),
        mkcheck("runtime_still_protected", runtime_still_protected, runtime_still_protected),
        mkcheck("policy_ok", policy.get("policy_ok") is True, policy.get("policy_ok")),
        mkcheck("decision_ok", decision.get("decision_ok") is True, decision.get("decision_ok")),
        mkcheck("runtime_ok", runtime.get("runtime_ok") is True, runtime.get("runtime_ok")),
    ]

    overall_ok = all(c["ok"] for c in checks)
    failed_checks = [c["name"] for c in checks if not c["ok"]]

    request_summary = decision.get("request_summary") or {}
    audit_summary = {
        "h3_stage_closed": overall_ok,
        "ready_for_h4": overall_ok,
        "runtime_still_protected": runtime_still_protected,
        "provider_target": request_summary.get("provider_target"),
        "model_name": request_summary.get("model_name"),
    }

    audit_state = (
        "model_router_closed_soft_warn_ready_for_h4"
        if overall_ok and warning_flags else
        "model_router_closed_ready_for_h4"
        if overall_ok else
        "model_router_not_closed"
    )

    report = {
        "audit_type": "bybit_model_router_final_audit",
        "audit_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "H3-D",
        "overall_ok": overall_ok,
        "failed_count": len(failed_checks),
        "total_checks": len(checks),
        "checks": checks,
        "failed_checks": failed_checks,
        "warning_flags": warning_flags,
        "audit_state": audit_state,
        "audit_summary": audit_summary,
        "operator_message": (
            "H3 final audit passed. model_router v2 已正式收口并可继续进入 H4。"
            if overall_ok else
            "H3 final audit failed."
        ),
    }

    write_report(PREFIX, report)


if __name__ == "__main__":
    main()
