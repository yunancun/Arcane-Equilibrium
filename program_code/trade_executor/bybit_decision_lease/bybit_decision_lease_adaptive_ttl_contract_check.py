#!/usr/bin/env python3
import json
import time
from pathlib import Path
from typing import Any, Dict, List
from bybit_decision_lease_common import read_json_required as read_json, save_report_stem

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")
TARGET = BASE / "bybit_decision_lease_adaptive_ttl_latest.json"
STEM = "bybit_decision_lease_adaptive_ttl_contract"


def main() -> None:
    now_ms = int(time.time() * 1000)
    obj = read_json(TARGET) if TARGET.exists() else {}

    checks: List[Dict[str, Any]] = []
    failed_checks: List[str] = []

    def add(name: str, ok: bool, detail: Any) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            failed_checks.append(name)

    add("report_exists", TARGET.exists(), str(TARGET))
    add("decision_type_expected", obj.get("decision_type") == "bybit_decision_lease_adaptive_ttl", obj.get("decision_type"))
    add("decision_version_v1", obj.get("decision_version") == "v1", obj.get("decision_version"))
    add("stage_i5b", obj.get("stage") == "I5-B", obj.get("stage"))
    add("decision_ok_bool", isinstance(obj.get("decision_ok"), bool), obj.get("decision_ok"))
    add("adaptive_ttl_decision_dict", isinstance(obj.get("adaptive_ttl_decision"), dict), type(obj.get("adaptive_ttl_decision")).__name__ if obj.get("adaptive_ttl_decision") is not None else None)
    add("checks_list", isinstance(obj.get("checks"), list), type(obj.get("checks")).__name__ if obj.get("checks") is not None else None)
    add("failed_checks_list", isinstance(obj.get("failed_checks"), list), type(obj.get("failed_checks")).__name__ if obj.get("failed_checks") is not None else None)
    add("decision_state_known", obj.get("decision_state") in {
        "decision_lease_adaptive_ttl_blocked",
        "decision_lease_adaptive_ttl_ready_soft_warn",
        "decision_lease_adaptive_ttl_ready",
    }, obj.get("decision_state"))
    add("allow_progress_bool", isinstance(obj.get("allow_progress_to_i5c_final_audit"), bool), obj.get("allow_progress_to_i5c_final_audit"))

    report = {
        "report_type": STEM,
        "report_version": "v1",
        "ts_ms": now_ms,
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "checks": checks,
        "failed_checks": failed_checks,
    }
    save_report_stem(report, BASE, STEM)


if __name__ == "__main__":
    main()
