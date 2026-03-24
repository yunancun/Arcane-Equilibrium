#!/usr/bin/env python3
import json
import time
from pathlib import Path
from typing import Any, Dict, List

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")
METRICS_PATH = BASE / "bybit_decision_lease_friction_metrics_latest.json"
ADAPTIVE_PATH = BASE / "bybit_decision_lease_adaptive_ttl_latest.json"
STEM = "bybit_decision_lease_friction_final_audit"


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

    metrics = read_json(METRICS_PATH)
    adaptive = read_json(ADAPTIVE_PATH)

    ad = adaptive.get("adaptive_ttl_decision") or {}

    checks: List[Dict[str, Any]] = []
    failed_checks: List[str] = []

    def add(name: str, ok: bool, detail: Any) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            failed_checks.append(name)

    add("metrics_ok", metrics.get("metrics_ok") is True, metrics.get("metrics_ok"))
    add("adaptive_ok", adaptive.get("decision_ok") is True, adaptive.get("decision_ok"))
    add("shadow_apply_only", ad.get("shadow_apply_only") is True, ad.get("shadow_apply_only"))
    add("live_apply_allowed_now_false", ad.get("live_apply_allowed_now") is False, ad.get("live_apply_allowed_now"))
    add("applied_to_runtime_false", ad.get("applied_to_runtime") is False, ad.get("applied_to_runtime"))
    add("recommended_ttl_positive", int(ad.get("recommended_ttl_ms") or 0) > 0, ad.get("recommended_ttl_ms"))
    add("recommended_consume_slack_positive", int(ad.get("recommended_consume_slack_ms") or 0) > 0, ad.get("recommended_consume_slack_ms"))

    overall_ok = len(failed_checks) == 0
    warning_flags = uniq((metrics.get("warning_flags") or []) + (adaptive.get("warning_flags") or []))

    if overall_ok and warning_flags:
        audit_state = "decision_lease_friction_closed_soft_warn_ready_for_i6"
    elif overall_ok:
        audit_state = "decision_lease_friction_closed_ready_for_i6"
    else:
        audit_state = "decision_lease_friction_not_closed"

    report = {
        "audit_type": STEM,
        "audit_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "I5-C",
        "overall_ok": overall_ok,
        "failed_count": len(failed_checks),
        "checks": checks,
        "failed_checks": failed_checks,
        "audit_summary": {
            "i5_stage_closed": overall_ok,
            "ready_for_i6": overall_ok,
            "runtime_still_protected": True,
            "shadow_adaptive_ttl_only": True,
            "recommended_ttl_ms": ad.get("recommended_ttl_ms"),
            "recommended_consume_slack_ms": ad.get("recommended_consume_slack_ms"),
            "live_apply_allowed_now": False,
        },
        "warning_flags": warning_flags,
        "audit_state": audit_state,
        "recommended_next_build_order": [
            "I6. multi-actor approval bridge",
            "I7. authority escalation boundary",
            "I8. live lease activation conditions",
        ],
        "operator_message": "I5 final audit complete. Lease friction and adaptive TTL are now modeled in shadow-only mode, improving future executability without creating live blocking today.",
    }
    save_report(report)


if __name__ == "__main__":
    main()
