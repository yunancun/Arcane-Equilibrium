#!/usr/bin/env python3
import json
import time
from pathlib import Path
from typing import Any, Dict, List

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")
PREFLIGHT_PATH = BASE / "bybit_decision_lease_preflight_latest.json"
SHADOW_PATH = BASE / "bybit_decision_lease_shadow_issue_latest.json"
STEM = "bybit_decision_lease_shadow_audit"


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
    preflight = read_json(PREFLIGHT_PATH)
    shadow = read_json(SHADOW_PATH)

    candidate = shadow.get("shadow_candidate") or {}

    checks: List[Dict[str, Any]] = []
    failed_checks: List[str] = []

    def add(name: str, ok: bool, detail: Any) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            failed_checks.append(name)

    add("preflight_ok", preflight.get("preflight_ok") is True, preflight.get("preflight_ok"))
    add("shadow_issue_ok", shadow.get("shadow_issue_ok") is True, shadow.get("shadow_issue_ok"))
    add("shadow_mode_only", candidate.get("lease_mode") == "shadow_only", candidate.get("lease_mode"))
    add("lease_emit_allowed_now_false", candidate.get("lease_emit_allowed_now") is False, candidate.get("lease_emit_allowed_now"))
    add("decision_lease_emitted_false", candidate.get("decision_lease_emitted") is False, candidate.get("decision_lease_emitted"))
    add("execution_authority_not_granted", candidate.get("execution_authority_current") == "not_granted", candidate.get("execution_authority_current"))
    add("shadow_candidate_ready_true", candidate.get("shadow_candidate_ready") is True, candidate.get("shadow_candidate_ready"))
    add("expires_after_issue", (candidate.get("expires_ts_ms") or 0) > (candidate.get("issue_ts_ms") or 0), {
        "issue_ts_ms": candidate.get("issue_ts_ms"),
        "expires_ts_ms": candidate.get("expires_ts_ms"),
    })

    overall_ok = len(failed_checks) == 0
    warning_flags = uniq((preflight.get("warning_flags") or []) + (shadow.get("warning_flags") or []))

    if overall_ok and warning_flags:
        audit_state = "decision_lease_shadow_closed_soft_warn_ready_for_i3"
    elif overall_ok:
        audit_state = "decision_lease_shadow_closed_ready_for_i3"
    else:
        audit_state = "decision_lease_shadow_not_closed"

    report = {
        "audit_type": STEM,
        "audit_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "I2-C",
        "overall_ok": overall_ok,
        "failed_count": len(failed_checks),
        "checks": checks,
        "failed_checks": failed_checks,
        "audit_summary": {
            "i2_stage_closed": overall_ok,
            "ready_for_i3": overall_ok,
            "runtime_still_protected": True,
            "shadow_candidate_only": True,
            "lease_emit_allowed_now": False,
            "decision_lease_emitted": False,
        },
        "recommended_next_build_order": [
            "I3. decision lease consume gate",
            "I4. revoke and replay defense",
            "I5. lease friction metrics and adaptive ttl",
        ],
        "warning_flags": warning_flags,
        "audit_state": audit_state,
        "operator_message": "I2-C decision lease shadow audit complete. Lease logic remains shadow-only and the runtime remains fully protected.",
    }
    save_report(report)


if __name__ == "__main__":
    main()
