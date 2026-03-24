#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
from pathlib import Path

from bybit_path_policy import get_thought_gate_runtime_dir
from typing import Any, Dict, List

RUNTIME_DIR = get_thought_gate_runtime_dir()
REPORT_PATH = RUNTIME_DIR / "bybit_query_budget_policy_latest.json"
LATEST_PATH = RUNTIME_DIR / "bybit_query_budget_policy_contract_latest.json"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    now_ms = int(time.time() * 1000)

    checks: List[Dict[str, Any]] = []

    report = read_json(REPORT_PATH) if REPORT_PATH.exists() else {}

    def add(name: str, ok: bool, detail: Any) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    add("report_exists", REPORT_PATH.exists(), str(REPORT_PATH))
    add("report_type_expected", report.get("report_type") == "bybit_query_budget_policy", report.get("report_type"))
    add("report_version_v1", report.get("report_version") == "v1", report.get("report_version"))
    add("stage_h2a", report.get("stage") == "H2-A", report.get("stage"))
    add("report_ok_bool", isinstance(report.get("report_ok"), bool), report.get("report_ok"))
    add("source_refs_dict", isinstance(report.get("source_refs"), dict), type(report.get("source_refs")).__name__)
    add("source_integrity_dict", isinstance(report.get("source_integrity"), dict), type(report.get("source_integrity")).__name__)
    add("request_summary_dict", isinstance(report.get("request_summary"), dict), type(report.get("request_summary")).__name__)
    add("policy_snapshot_dict", isinstance(report.get("policy_snapshot"), dict), type(report.get("policy_snapshot")).__name__)
    add("observed_last_call_dict", isinstance(report.get("observed_last_call"), dict), type(report.get("observed_last_call")).__name__)
    add("budget_assessment_dict", isinstance(report.get("budget_assessment"), dict), type(report.get("budget_assessment")).__name__)
    add("warning_flags_list", isinstance(report.get("warning_flags"), list), type(report.get("warning_flags")).__name__)
    add("blocking_reasons_list", isinstance(report.get("blocking_reasons"), list), type(report.get("blocking_reasons")).__name__)
    add(
        "policy_state_known",
        report.get("policy_state") in {"query_budget_policy_snapshotted", "query_budget_policy_blocked"},
        report.get("policy_state"),
    )
    add(
        "allow_progress_bool",
        isinstance(report.get("allow_progress_to_h2b_budget_gate"), bool),
        report.get("allow_progress_to_h2b_budget_gate"),
    )

    failed_checks = [x["name"] for x in checks if not x["ok"]]

    contract_report = {
        "report_type": "bybit_query_budget_policy_contract_check",
        "report_version": "v1",
        "ts_ms": now_ms,
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "checks": checks,
        "failed_checks": failed_checks,
    }

    dated_path = RUNTIME_DIR / f"bybit_query_budget_policy_contract_{now_ms}.json"
    write_json(LATEST_PATH, contract_report)
    write_json(dated_path, contract_report)

    print(json.dumps(contract_report, ensure_ascii=False, indent=2))
    print(f"saved_latest={LATEST_PATH}")
    print(f"saved_dated={dated_path}")


if __name__ == "__main__":
    main()
