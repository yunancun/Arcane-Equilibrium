#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
from pathlib import Path

from bybit_path_policy import get_thought_gate_runtime_dir
from typing import Any, Dict, List

RUNTIME_DIR = get_thought_gate_runtime_dir()
REPORT_PATH = RUNTIME_DIR / "bybit_query_budget_final_audit_latest.json"
LATEST_PATH = RUNTIME_DIR / "bybit_query_budget_final_audit_contract_latest.json"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    now_ms = int(time.time() * 1000)
    report = read_json(REPORT_PATH) if REPORT_PATH.exists() else {}
    checks: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: Any) -> None:
        checks.append({
            "name": name,
            "ok": bool(ok),
            "detail": detail,
        })

    add("report_exists", REPORT_PATH.exists(), str(REPORT_PATH))
    add("audit_type_expected", report.get("audit_type") == "bybit_query_budget_final_audit", report.get("audit_type"))
    add("audit_version_v1", report.get("audit_version") == "v1", report.get("audit_version"))
    add("stage_h2d", report.get("stage") == "H2-D", report.get("stage"))
    add("overall_ok_bool", isinstance(report.get("overall_ok"), bool), report.get("overall_ok"))
    add("checks_list", isinstance(report.get("checks"), list), type(report.get("checks")).__name__)
    add("failed_checks_list", isinstance(report.get("failed_checks"), list), type(report.get("failed_checks")).__name__)
    add("audit_summary_dict", isinstance(report.get("audit_summary"), dict), type(report.get("audit_summary")).__name__)
    add(
        "audit_state_known",
        report.get("audit_state") in {
            "query_budget_closed_ready_for_h3",
            "query_budget_closed_soft_warn_ready_for_h3",
            "query_budget_not_closed",
        },
        report.get("audit_state"),
    )

    failed_checks = [x["name"] for x in checks if not x["ok"]]

    contract_report = {
        "report_type": "bybit_query_budget_final_audit_contract_check",
        "report_version": "v1",
        "ts_ms": now_ms,
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "checks": checks,
        "failed_checks": failed_checks,
    }

    dated_path = RUNTIME_DIR / f"bybit_query_budget_final_audit_contract_{now_ms}.json"
    write_json(LATEST_PATH, contract_report)
    write_json(dated_path, contract_report)

    print(json.dumps(contract_report, ensure_ascii=False, indent=2))
    print(f"saved_latest={LATEST_PATH}")
    print(f"saved_dated={dated_path}")


if __name__ == "__main__":
    main()
