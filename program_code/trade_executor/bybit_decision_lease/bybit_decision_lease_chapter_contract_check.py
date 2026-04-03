#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
from pathlib import Path
import os
from typing import Any, Dict, List
from bybit_decision_lease_common import read_json_required as read_json, save_report

BASE = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")
REPORT_PATH = BASE / "bybit_decision_lease_chapter_final_audit_latest.json"
LATEST_PATH = BASE / "bybit_decision_lease_chapter_contract_latest.json"


def check(name: str, ok: bool, detail: Any) -> Dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def main() -> None:
    now_ms = int(time.time() * 1000)
    report_exists = REPORT_PATH.exists()
    obj = read_json(REPORT_PATH) if report_exists else {}

    checks: List[Dict[str, Any]] = [
        check("report_exists", report_exists, str(REPORT_PATH)),
        check("audit_type_expected", obj.get("audit_type") == "bybit_decision_lease_chapter_final_audit", obj.get("audit_type")),
        check("audit_version_v1", obj.get("audit_version") == "v1", obj.get("audit_version")),
        check("stage_i10", obj.get("stage") == "I10", obj.get("stage")),
        check("overall_ok_bool", isinstance(obj.get("overall_ok"), bool), obj.get("overall_ok")),
        check("checks_list", isinstance(obj.get("checks"), list), type(obj.get("checks")).__name__),
        check("failed_checks_list", isinstance(obj.get("failed_checks"), list), type(obj.get("failed_checks")).__name__),
        check("audit_summary_dict", isinstance(obj.get("audit_summary"), dict), type(obj.get("audit_summary")).__name__),
    ]

    failed_checks = [c["name"] for c in checks if not c["ok"]]
    overall_ok = len(failed_checks) == 0

    report = {
        "report_type": "bybit_decision_lease_chapter_contract_check",
        "report_version": "v1",
        "ts_ms": now_ms,
        "overall_ok": overall_ok,
        "failed_count": len(failed_checks),
        "checks": checks,
        "failed_checks": failed_checks,
    }

    save_report(report, LATEST_PATH, print_json=True)


if __name__ == "__main__":
    main()
