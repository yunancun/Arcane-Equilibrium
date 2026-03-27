#!/usr/bin/env python3
import json
import time
from pathlib import Path
from typing import Any, Dict, List
from bybit_decision_lease_common import read_json_required as read_json, save_report_stem

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")
TARGET = BASE / "bybit_decision_lease_replay_final_audit_latest.json"
STEM = "bybit_decision_lease_replay_contract"


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
    add("audit_type_expected", obj.get("audit_type") == "bybit_decision_lease_replay_final_audit", obj.get("audit_type"))
    add("audit_version_v1", obj.get("audit_version") == "v1", obj.get("audit_version"))
    add("stage_i4c", obj.get("stage") == "I4-C", obj.get("stage"))
    add("overall_ok_bool", isinstance(obj.get("overall_ok"), bool), obj.get("overall_ok"))
    add("checks_list", isinstance(obj.get("checks"), list), type(obj.get("checks")).__name__ if obj.get("checks") is not None else None)
    add("failed_checks_list", isinstance(obj.get("failed_checks"), list), type(obj.get("failed_checks")).__name__ if obj.get("failed_checks") is not None else None)
    add("audit_summary_dict", isinstance(obj.get("audit_summary"), dict), type(obj.get("audit_summary")).__name__ if obj.get("audit_summary") is not None else None)

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
