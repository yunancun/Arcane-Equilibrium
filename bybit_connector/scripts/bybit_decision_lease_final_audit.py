#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from pathlib import Path

from bybit_h_stage_common import mkcheck, read_json_if_exists, unique_list, write_report

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

SCHEMA_PATH = BASE / "bybit_decision_lease_schema_latest.json"
H5_AUDIT_PATH = BASE / "bybit_ai_cost_governance_final_audit_latest.json"

PREFIX = "bybit_decision_lease_final_audit"


def main() -> None:
    now_ms = int(time.time() * 1000)

    schema = read_json_if_exists(SCHEMA_PATH)
    h5 = read_json_if_exists(H5_AUDIT_PATH)

    schema_runtime_view = schema.get("schema_runtime_view") or {}
    h5_summary = h5.get("audit_summary") or {}

    checks = [
        mkcheck("h5_stage_closed", h5_summary.get("h5_stage_closed") is True, h5_summary.get("h5_stage_closed")),
        mkcheck("ready_for_i1", h5_summary.get("ready_for_i1") is True, h5_summary.get("ready_for_i1")),
        mkcheck("schema_ok", schema.get("schema_ok") is True, schema.get("schema_ok")),
        mkcheck("schema_only_mode_true", schema_runtime_view.get("schema_only_mode") is True, schema_runtime_view.get("schema_only_mode")),
        mkcheck("lease_emit_allowed_now_false", schema_runtime_view.get("lease_emit_allowed_now") is False, schema_runtime_view.get("lease_emit_allowed_now")),
        mkcheck("execution_authority_not_granted", schema_runtime_view.get("execution_authority") == "not_granted", schema_runtime_view.get("execution_authority")),
        mkcheck("decision_lease_emitted_false", schema_runtime_view.get("decision_lease_emitted") is False, schema_runtime_view.get("decision_lease_emitted")),
    ]

    overall_ok = all(c["ok"] for c in checks)
    failed_checks = [c["name"] for c in checks if not c["ok"]]

    warning_flags = unique_list(
        (schema.get("warning_flags") or [])
    )

    audit_summary = {
        "i1_stage_closed": overall_ok,
        "ready_for_future_i_stage": overall_ok,
        "runtime_still_protected": True,
        "lease_emit_allowed_now": False,
        "decision_lease_emitted": False,
    }

    audit_state = (
        "decision_lease_schema_closed_soft_warn"
        if overall_ok and warning_flags else
        "decision_lease_schema_closed"
        if overall_ok else
        "decision_lease_schema_not_closed"
    )

    report = {
        "audit_type": "bybit_decision_lease_final_audit",
        "audit_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "I1-B",
        "overall_ok": overall_ok,
        "failed_count": len(failed_checks),
        "total_checks": len(checks),
        "checks": checks,
        "failed_checks": failed_checks,
        "warning_flags": warning_flags,
        "audit_state": audit_state,
        "audit_summary": audit_summary,
        "operator_message": (
            "I1 final audit passed. decision lease schema 已闭环，但仍严格处于 no-emit / no-authority 状态。"
            if overall_ok else
            "I1 final audit failed."
        ),
    }

    write_report(PREFIX, report)


if __name__ == "__main__":
    main()
