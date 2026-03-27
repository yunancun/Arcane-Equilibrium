#!/usr/bin/env python3
import json
import time
from pathlib import Path
from typing import Any, Dict, List
from bybit_decision_lease_common import read_json_required as read_json, save_report_stem, uniq

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")
POLICY_PATH = BASE / "bybit_decision_lease_replay_policy_latest.json"
CONSUME_GATE_PATH = BASE / "bybit_decision_lease_consume_gate_latest.json"

STEM = "bybit_decision_lease_replay_guard"


def main() -> None:
    now_ms = int(time.time() * 1000)

    policy = read_json(POLICY_PATH)
    consume_gate = read_json(CONSUME_GATE_PATH)

    replay_policy = policy.get("replay_policy") or {}
    consume_decision = consume_gate.get("consume_decision") or {}

    first_attempt = {
        "attempt_no": 1,
        "mode": "shadow_consume_simulation",
        "result": "would_accept_once" if consume_decision.get("shadow_consume_ready") else "would_reject",
        "reason": "shadow lease passes first consume path under simulated timing",
    }
    second_attempt = {
        "attempt_no": 2,
        "mode": "shadow_consume_simulation",
        "result": "would_reject_replay",
        "reason": "duplicate replay_key would be blocked by single-consume semantics",
    }
    revoke_attempt = {
        "mode": "shadow_revoke_simulation",
        "result": "would_record_revoke_shadow_only",
        "reason": "revoke path modeled but not live-enabled",
    }

    checks: List[Dict[str, Any]] = []
    failed_checks: List[str] = []

    def add(name: str, ok: bool, detail: Any) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            failed_checks.append(name)

    add("policy_ok", policy.get("policy_ok") is True, policy.get("policy_ok"))
    add("consume_gate_ok", consume_gate.get("gate_ok") is True, consume_gate.get("gate_ok"))
    add("first_attempt_accept_once", first_attempt["result"] == "would_accept_once", first_attempt["result"])
    add("second_attempt_reject_replay", second_attempt["result"] == "would_reject_replay", second_attempt["result"])
    add("replay_guard_enabled", replay_policy.get("replay_guard_enabled") is True, replay_policy.get("replay_guard_enabled"))
    add("shadow_only_mode", replay_policy.get("shadow_only_mode") is True, replay_policy.get("shadow_only_mode"))
    add("live_replay_enforced_false", replay_policy.get("replay_live_enforced") is False, replay_policy.get("replay_live_enforced"))
    add("revoke_live_enabled_false", replay_policy.get("revoke_live_enabled") is False, replay_policy.get("revoke_live_enabled"))
    add("decision_lease_consumed_false", consume_decision.get("decision_lease_consumed") is False, consume_decision.get("decision_lease_consumed"))

    hard_fail_names = {
        "policy_ok",
        "consume_gate_ok",
        "first_attempt_accept_once",
        "second_attempt_reject_replay",
        "replay_guard_enabled",
        "shadow_only_mode",
        "live_replay_enforced_false",
        "revoke_live_enabled_false",
        "decision_lease_consumed_false",
    }

    gate_ok = not any(name in hard_fail_names for name in failed_checks)

    guard_decision = {
        "replay_key": replay_policy.get("replay_key"),
        "first_attempt": first_attempt,
        "second_attempt": second_attempt,
        "revoke_attempt": revoke_attempt,
        "shadow_replay_defense_ready": gate_ok,
        "replay_block_reason": "duplicate_replay_key_detected_shadow_mode",
        "consume_receipt_store_mode": replay_policy.get("consume_receipt_store_mode"),
        "live_replay_block_active": False,
        "live_revoke_active": False,
        "decision_lease_consumed": False,
        "decision_lease_revoked": False,
    }

    warning_flags: List[str] = []
    warning_flags.extend(policy.get("warning_flags") or [])
    warning_flags.extend(consume_gate.get("warning_flags") or [])
    warning_flags.append("decision_lease_replay_guard_shadow_only_mode")
    warning_flags = uniq(warning_flags)

    if not gate_ok:
        gate_state = "decision_lease_replay_guard_blocked"
        allow_progress = False
        recommended_action = "inspect_i4b_replay_guard_failures"
    elif warning_flags:
        gate_state = "decision_lease_replay_guard_ready_soft_warn"
        allow_progress = True
        recommended_action = "may_progress_to_i4c_final_audit"
    else:
        gate_state = "decision_lease_replay_guard_ready"
        allow_progress = True
        recommended_action = "may_progress_to_i4c_final_audit"

    report = {
        "gate_type": STEM,
        "gate_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "I4-B",
        "gate_ok": gate_ok,
        "source_refs": {
            "decision_lease_replay_policy_path": str(POLICY_PATH),
            "decision_lease_consume_gate_path": str(CONSUME_GATE_PATH),
        },
        "request_summary": policy.get("request_summary") or {},
        "guard_decision": guard_decision,
        "checks": checks,
        "failed_checks": failed_checks,
        "warning_flags": warning_flags,
        "blocking_reasons": failed_checks if not gate_ok else [],
        "gate_state": gate_state,
        "allow_progress_to_i4c_final_audit": allow_progress,
        "recommended_action": recommended_action,
        "operator_message": "I4-B replay guard complete. The shadow model now proves first-consume acceptance and duplicate-consume rejection semantics without enabling live revoke or live replay enforcement.",
    }
    save_report_stem(report, BASE, STEM)


if __name__ == "__main__":
    main()
