#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
from pathlib import Path
from typing import Any, Dict, List
from bybit_decision_lease_common import read_json_required as read_json, save_report

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")
ACK_PATH = BASE / "bybit_operator_ack_shadow_latest.json"
LATEST_PATH = BASE / "bybit_operator_ack_shadow_final_audit_latest.json"


def check(name: str, ok: bool, detail: Any) -> Dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def main() -> None:
    now_ms = int(time.time() * 1000)
    obj = read_json(ACK_PATH)
    runtime = obj.get("ack_runtime_view") or {}

    checks: List[Dict[str, Any]] = [
        check("ack_ok", bool(obj.get("ack_ok")), obj.get("ack_ok")),
        check("ack_state_green", obj.get("ack_state") == "operator_ack_shadow_ready_soft_warn", obj.get("ack_state")),
        check("operator_ack_shadow_only_true", runtime.get("operator_ack_shadow_only") is True, runtime.get("operator_ack_shadow_only")),
        check("live_operator_ack_enabled_false", runtime.get("live_operator_ack_enabled") is False, runtime.get("live_operator_ack_enabled")),
        check("approval_submit_live_false", runtime.get("approval_submit_live") is False, runtime.get("approval_submit_live")),
        check("execution_authority_not_granted", runtime.get("execution_authority") == "not_granted", runtime.get("execution_authority")),
        check("live_execution_allowed_false", runtime.get("live_execution_allowed") is False, runtime.get("live_execution_allowed")),
    ]

    failed_checks = [c["name"] for c in checks if not c["ok"]]
    overall_ok = len(failed_checks) == 0

    out = {
        "audit_type": "bybit_operator_ack_shadow_final_audit",
        "audit_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "I9",
        "overall_ok": overall_ok,
        "failed_count": len(failed_checks),
        "total_checks": len(checks),
        "checks": checks,
        "failed_checks": failed_checks,
        "audit_summary": {
            "i9_stage_closed": overall_ok,
            "ready_for_i10": overall_ok,
            "runtime_still_protected": (
                runtime.get("live_operator_ack_enabled") is False
                and runtime.get("approval_submit_live") is False
                and runtime.get("execution_authority") == "not_granted"
                and runtime.get("live_execution_allowed") is False
            ),
            "operator_ack_shadow_only": runtime.get("operator_ack_shadow_only") is True,
        },
        "warning_flags": obj.get("warning_flags") or [],
        "audit_state": (
            "operator_ack_shadow_closed_soft_warn_ready_for_i10"
            if overall_ok else
            "operator_ack_shadow_audit_failed"
        ),
        "operator_message": (
            "I9 final audit passed. Operator acknowledgment shadow is closed and ready for I10."
            if overall_ok else
            "I9 final audit failed."
        ),
    }

    save_report(out, LATEST_PATH, print_json=True)


if __name__ == "__main__":
    main()
