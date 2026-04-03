#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
from pathlib import Path
import os
from typing import Any, Dict, List
from bybit_decision_lease_common import read_json_required as read_json, save_report

BASE = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")
BRIDGE_PATH = BASE / "bybit_decision_lease_approval_bridge_latest.json"
LATEST_PATH = BASE / "bybit_decision_lease_approval_bridge_final_audit_latest.json"


def check(name: str, ok: bool, detail: Any) -> Dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def main() -> None:
    now_ms = int(time.time() * 1000)
    obj = read_json(BRIDGE_PATH)

    bridge_ok = bool(obj.get("bridge_ok"))
    bridge_state = obj.get("bridge_state")
    approval_bridge_view = obj.get("approval_bridge_view") or {}
    governance_guards = obj.get("governance_guards") or {}

    shadow_bridge_only = approval_bridge_view.get("shadow_bridge_only")
    live_approval_grant_active = approval_bridge_view.get("live_approval_grant_active")
    execution_authority = governance_guards.get("execution_authority")
    system_mode = governance_guards.get("system_mode")
    execution_state = governance_guards.get("execution_state")

    checks: List[Dict[str, Any]] = [
        check("bridge_ok", bridge_ok, bridge_ok),
        check(
            "bridge_state_green",
            bridge_state == "decision_lease_approval_bridge_shadow_ready_soft_warn",
            bridge_state,
        ),
        check(
            "shadow_bridge_only_true",
            shadow_bridge_only is True,
            shadow_bridge_only,
        ),
        check(
            "live_approval_grant_active_false",
            live_approval_grant_active is False,
            live_approval_grant_active,
        ),
        check(
            "execution_authority_not_granted",
            execution_authority == "not_granted",
            execution_authority,
        ),
        check("system_mode_read_only", system_mode == "read_only", system_mode),
        check("execution_state_disabled", execution_state == "disabled", execution_state),
    ]

    failed_checks = [c["name"] for c in checks if not c["ok"]]
    overall_ok = len(failed_checks) == 0

    warning_flags = obj.get("warning_flags") or []

    out = {
        "audit_type": "bybit_decision_lease_approval_bridge_final_audit",
        "audit_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "I6",
        "overall_ok": overall_ok,
        "failed_count": len(failed_checks),
        "total_checks": len(checks),
        "checks": checks,
        "failed_checks": failed_checks,
        "audit_summary": {
            "i6_stage_closed": overall_ok,
            "ready_for_i7": overall_ok,
            "runtime_still_protected": (system_mode == "read_only" and execution_state == "disabled"),
            "shadow_bridge_only": shadow_bridge_only is True,
            "live_approval_grant_active": live_approval_grant_active is True,
        },
        "warning_flags": warning_flags,
        "audit_state": (
            "decision_lease_approval_bridge_closed_soft_warn_ready_for_i7"
            if overall_ok else
            "decision_lease_approval_bridge_audit_failed"
        ),
        "operator_message": (
            "I6 final audit passed. Approval bridge is closed in shadow-only mode and ready for I7."
            if overall_ok else
            "I6 final audit failed."
        ),
    }

    print(json.dumps(out, ensure_ascii=False, indent=2))
    save_report(out, LATEST_PATH)


if __name__ == "__main__":
    main()
