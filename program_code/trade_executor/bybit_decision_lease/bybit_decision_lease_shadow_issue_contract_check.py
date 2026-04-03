#!/usr/bin/env python3
import json
import time
from pathlib import Path
import os
from typing import Any, Dict, List
from bybit_decision_lease_common import read_json_required as read_json, save_report_stem

BASE = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")
TARGET = BASE / "bybit_decision_lease_shadow_issue_latest.json"
STEM = "bybit_decision_lease_shadow_issue_contract"


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
    add("shadow_issue_type_expected", obj.get("shadow_issue_type") == "bybit_decision_lease_shadow_issue", obj.get("shadow_issue_type"))
    add("shadow_issue_version_v1", obj.get("shadow_issue_version") == "v1", obj.get("shadow_issue_version"))
    add("stage_i2b", obj.get("stage") == "I2-B", obj.get("stage"))
    add("shadow_issue_ok_bool", isinstance(obj.get("shadow_issue_ok"), bool), obj.get("shadow_issue_ok"))
    add("shadow_candidate_dict", isinstance(obj.get("shadow_candidate"), dict), type(obj.get("shadow_candidate")).__name__ if obj.get("shadow_candidate") is not None else None)
    add("checks_list", isinstance(obj.get("checks"), list), type(obj.get("checks")).__name__ if obj.get("checks") is not None else None)
    add("failed_checks_list", isinstance(obj.get("failed_checks"), list), type(obj.get("failed_checks")).__name__ if obj.get("failed_checks") is not None else None)
    add("shadow_issue_state_known", obj.get("shadow_issue_state") in {
        "decision_lease_shadow_candidate_blocked",
        "decision_lease_shadow_candidate_ready_soft_warn",
        "decision_lease_shadow_candidate_ready",
    }, obj.get("shadow_issue_state"))
    add("allow_progress_bool", isinstance(obj.get("allow_progress_to_i2c_shadow_audit"), bool), obj.get("allow_progress_to_i2c_shadow_audit"))

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
