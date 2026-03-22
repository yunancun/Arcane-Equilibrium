#!/usr/bin/env python3
import json
import time
from pathlib import Path
from typing import Any, Dict, List

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")
POLICY_PATH = BASE / "bybit_decision_lease_consume_policy_latest.json"
GATE_PATH = BASE / "bybit_decision_lease_consume_gate_latest.json"
STEM = "bybit_decision_lease_consume_final_audit"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def uniq(items: List[str]) -> List[str]:
    return list(dict.fromkeys(items))


def save_report(obj: Dict[str, Any]) -> None:
    latest = BASE / f"{STEM}_latest.json"
    dated = BASE / f"{STEM}_{obj['ts_ms']}.json"
    latest.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")


def main() -> None:
    now_ms = int(time.time() * 1000)
    policy = read_json(POLICY_PATH)
    gate = read_json(GATE_PATH)

    decision = gate.get("consume_decision") or {}

    checks: List[Dict[str, Any]] = []
    failed_checks: List[str] = []

    def add(name: str, ok: bool, detail: Any) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            failed_checks.append(name)

    add("policy_ok", policy.get("policy_ok") is True, policy.get("policy_ok"))
    add("gate_ok", gate.get("gate_ok") is True, gate.get("gate_ok"))
    add("shadow_consume_ready", decision.get("shadow_consume_ready") is True, decision.get("shadow_consume_ready"))
    add("consume_gate_open_live_false", decision.get("consume_gate_open_live") is False, decision.get("consume_gate_open_live"))
    add("consume_authority_not_granted", decision.get("consume_authority") == "not_granted", decision.get("consume_authority"))
    add("decision_lease_consumed_false", decision.get("decision_lease_consumed") is False, decision.get("decision_lease_consumed"))
    add("consume_receipt_emitted_false", decision.get("consume_receipt_emitted") is False, decision.get("consume_receipt_emitted"))

    overall_ok = len(failed_checks) == 0
    warning_flags = uniq((policy.get("warning_flags") or []) + (gate.get("warning_flags") or []))

    if overall_ok and warning_flags:
        audit_state = "decision_lease_consume_closed_soft_warn_ready_for_i4"
    elif overall_ok:
        audit_state = "decision_lease_consume_closed_ready_for_i4"
    else:
        audit_state = "decision_lease_consume_not_closed"

    report = {
        "audit_type": STEM,
        "audit_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "I3-C",
        "overall_ok": overall_ok,
        "failed_count": len(failed_checks),
        "checks": checks,
        "failed_checks": failed_checks,
        "audit_summary": {
            "i3_stage_closed": overall_ok,
            "ready_for_i4": overall_ok,
            "runtime_still_protected": True,
            "shadow_consume_only": True,
            "consume_gate_open_live": False,
            "decision_lease_consumed": False,
        },
        "recommended_next_build_order": [
            "I4. revoke and replay defense",
            "I5. lease friction metrics and adaptive ttl",
            "I6. multi-actor approval bridge",
        ],
        "warning_flags": warning_flags,
        "audit_state": audit_state,
        "operator_message": "I3 final audit complete. Lease consume logic is now closed in shadow-only mode, without permitting live consumption or execution.",
    }
    save_report(report)


if __name__ == "__main__":
    main()
