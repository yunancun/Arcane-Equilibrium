#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
from pathlib import Path
from typing import Any, Dict, List

RUNTIME_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")
REPORT_PATH = RUNTIME_DIR / "bybit_query_budget_runtime_latest.json"
LATEST_PATH = RUNTIME_DIR / "bybit_query_budget_runtime_contract_latest.json"


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
    add("runtime_type_expected", report.get("runtime_type") == "bybit_query_budget_runtime", report.get("runtime_type"))
    add("runtime_version_v1", report.get("runtime_version") == "v1", report.get("runtime_version"))
    add("stage_h2c", report.get("stage") == "H2-C", report.get("stage"))
    add("runtime_ok_bool", isinstance(report.get("runtime_ok"), bool), report.get("runtime_ok"))
    add("source_refs_dict", isinstance(report.get("source_refs"), dict), type(report.get("source_refs")).__name__)
    add("source_integrity_dict", isinstance(report.get("source_integrity"), dict), type(report.get("source_integrity")).__name__)
    add("request_summary_dict", isinstance(report.get("request_summary"), dict), type(report.get("request_summary")).__name__)
    add("budget_policy_dict", isinstance(report.get("budget_policy"), dict), type(report.get("budget_policy")).__name__)
    add("observed_last_call_dict", isinstance(report.get("observed_last_call"), dict), type(report.get("observed_last_call")).__name__)
    add("runtime_assessment_dict", isinstance(report.get("runtime_assessment"), dict), type(report.get("runtime_assessment")).__name__)
    add("runtime_checks_list", isinstance(report.get("runtime_checks"), list), type(report.get("runtime_checks")).__name__)
    add("warning_flags_list", isinstance(report.get("warning_flags"), list), type(report.get("warning_flags")).__name__)
    add("blocking_reasons_list", isinstance(report.get("blocking_reasons"), list), type(report.get("blocking_reasons")).__name__)
    add(
        "runtime_state_known",
        report.get("runtime_state") in {
            "query_budget_runtime_ready",
            "query_budget_runtime_ready_soft_warn",
            "query_budget_runtime_blocked",
        },
        report.get("runtime_state"),
    )
    add(
        "allow_progress_bool",
        isinstance(report.get("allow_progress_to_h2d_final_audit"), bool),
        report.get("allow_progress_to_h2d_final_audit"),
    )

    failed_checks = [x["name"] for x in checks if not x["ok"]]

    contract_report = {
        "report_type": "bybit_query_budget_runtime_contract_check",
        "report_version": "v1",
        "ts_ms": now_ms,
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "checks": checks,
        "failed_checks": failed_checks,
    }

    dated_path = RUNTIME_DIR / f"bybit_query_budget_runtime_contract_{now_ms}.json"
    write_json(LATEST_PATH, contract_report)
    write_json(dated_path, contract_report)

    print(json.dumps(contract_report, ensure_ascii=False, indent=2))
    print(f"saved_latest={LATEST_PATH}")
    print(f"saved_dated={dated_path}")


if __name__ == "__main__":
    main()
