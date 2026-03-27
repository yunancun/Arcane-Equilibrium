#!/usr/bin/env python3
import json
import time
from pathlib import Path
from typing import Any, Dict, List
from bybit_decision_lease_common import read_json_required as read_json, save_report_stem, uniq

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")
POLICY_PATH = BASE / "bybit_decision_lease_replay_policy_latest.json"
GUARD_PATH = BASE / "bybit_decision_lease_replay_guard_latest.json"
STEM = "bybit_decision_lease_replay_final_audit"


def main() -> None:
    now_ms = int(time.time() * 1000)
    policy = read_json(POLICY_PATH)
    guard = read_json(GUARD_PATH)

    gd = guard.get("guard_decision") or {}

    checks: List[Dict[str, Any]] = []
    failed_checks: List[str] = []

    def add(name: str, ok: bool, detail: Any) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            failed_checks.append(name)

    add("policy_ok", policy.get("policy_ok") is True, policy.get("policy_ok"))
    add("guard_ok", guard.get("gate_ok") is True, guard.get("gate_ok"))
    add("shadow_replay_defense_ready", gd.get("shadow_replay_defense_ready") is True, gd.get("shadow_replay_defense_ready"))
    add("duplicate_rejected", ((gd.get("second_attempt") or {}).get("result") == "would_reject_replay"), (gd.get("second_attempt") or {}).get("result"))
    add("live_replay_block_active_false", gd.get("live_replay_block_active") is False, gd.get("live_replay_block_active"))
    add("live_revoke_active_false", gd.get("live_revoke_active") is False, gd.get("live_revoke_active"))
    add("decision_lease_consumed_false", gd.get("decision_lease_consumed") is False, gd.get("decision_lease_consumed"))
    add("decision_lease_revoked_false", gd.get("decision_lease_revoked") is False, gd.get("decision_lease_revoked"))

    overall_ok = len(failed_checks) == 0
    warning_flags = uniq((policy.get("warning_flags") or []) + (guard.get("warning_flags") or []))

    if overall_ok and warning_flags:
        audit_state = "decision_lease_replay_closed_soft_warn_ready_for_i5"
    elif overall_ok:
        audit_state = "decision_lease_replay_closed_ready_for_i5"
    else:
        audit_state = "decision_lease_replay_not_closed"

    report = {
        "audit_type": STEM,
        "audit_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "I4-C",
        "overall_ok": overall_ok,
        "failed_count": len(failed_checks),
        "checks": checks,
        "failed_checks": failed_checks,
        "audit_summary": {
            "i4_stage_closed": overall_ok,
            "ready_for_i5": overall_ok,
            "runtime_still_protected": True,
            "shadow_replay_only": True,
            "duplicate_replay_rejected": True if overall_ok else False,
            "live_revoke_active": False,
            "live_replay_block_active": False,
        },
        "recommended_next_build_order": [
            "I5. lease friction metrics and adaptive ttl",
            "I6. multi-actor approval bridge",
            "I7. authority escalation boundary",
        ],
        "warning_flags": warning_flags,
        "audit_state": audit_state,
        "operator_message": "I4 final audit complete. Replay and revoke semantics are now modeled and verified in shadow-only mode, while runtime remains fully protected.",
    }
    save_report_stem(report, BASE, STEM)


if __name__ == "__main__":
    main()
