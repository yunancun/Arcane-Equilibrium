#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
from pathlib import Path
import os
from typing import Any, Dict, List
from bybit_decision_lease_common import read_json_required as read_json, save_report

BASE = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")
PACKET_PATH = BASE / "bybit_manual_approval_packet_latest.json"
LATEST_PATH = BASE / "bybit_manual_approval_packet_final_audit_latest.json"


def check(name: str, ok: bool, detail: Any) -> Dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def main() -> None:
    now_ms = int(time.time() * 1000)
    obj = read_json(PACKET_PATH)

    packet_ok = bool(obj.get("packet_ok"))
    packet_state = obj.get("packet_state")
    runtime = obj.get("packet_runtime_view") or {}

    checks: List[Dict[str, Any]] = [
        check("packet_ok", packet_ok, packet_ok),
        check("packet_state_green", packet_state == "manual_approval_packet_shadow_ready_soft_warn", packet_state),
        check("packet_for_review_only_true", runtime.get("packet_for_review_only") is True, runtime.get("packet_for_review_only")),
        check("approval_submit_live_false", runtime.get("approval_submit_live") is False, runtime.get("approval_submit_live")),
        check("execution_authority_not_granted", runtime.get("execution_authority") == "not_granted", runtime.get("execution_authority")),
        check("operator_review_required_true", runtime.get("operator_review_required") is True, runtime.get("operator_review_required")),
        check("live_execution_allowed_false", runtime.get("live_execution_allowed") is False, runtime.get("live_execution_allowed")),
    ]

    failed_checks = [c["name"] for c in checks if not c["ok"]]
    overall_ok = len(failed_checks) == 0

    out = {
        "audit_type": "bybit_manual_approval_packet_final_audit",
        "audit_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "I8",
        "overall_ok": overall_ok,
        "failed_count": len(failed_checks),
        "total_checks": len(checks),
        "checks": checks,
        "failed_checks": failed_checks,
        "audit_summary": {
            "i8_stage_closed": overall_ok,
            "ready_for_i9": overall_ok,
            "runtime_still_protected": (
                runtime.get("approval_submit_live") is False
                and runtime.get("live_execution_allowed") is False
                and runtime.get("execution_authority") == "not_granted"
            ),
            "packet_for_review_only": runtime.get("packet_for_review_only") is True,
        },
        "warning_flags": obj.get("warning_flags") or [],
        "audit_state": (
            "manual_approval_packet_closed_soft_warn_ready_for_i9"
            if overall_ok else
            "manual_approval_packet_audit_failed"
        ),
        "operator_message": (
            "I8 final audit passed. Manual approval packet is closed in review-only mode and ready for I9."
            if overall_ok else
            "I8 final audit failed."
        ),
    }

    print(json.dumps(out, ensure_ascii=False, indent=2))
    save_report(out, LATEST_PATH)


if __name__ == "__main__":
    main()
