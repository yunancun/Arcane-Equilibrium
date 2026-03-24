#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from pathlib import Path

from bybit_path_policy import get_thought_gate_runtime_dir

from bybit_h_stage_common import mkcheck, read_json_if_exists, write_report

REPORT_PATH = get_thought_gate_runtime_dir() / "bybit_ai_cost_log_latest.json"
PREFIX = "bybit_ai_cost_log_contract"


def main() -> None:
    now_ms = int(time.time() * 1000)
    obj = read_json_if_exists(REPORT_PATH)

    checks = [
        mkcheck("report_exists", REPORT_PATH.exists(), str(REPORT_PATH)),
        mkcheck("log_type_expected", obj.get("log_type") == "bybit_ai_cost_log", obj.get("log_type")),
        mkcheck("log_version_v1", obj.get("log_version") == "v1", obj.get("log_version")),
        mkcheck("stage_h5a", obj.get("stage") == "H5-A", obj.get("stage")),
        mkcheck("log_ok_bool", isinstance(obj.get("log_ok"), bool), obj.get("log_ok")),
        mkcheck("cost_log_dict", isinstance(obj.get("cost_log"), dict), type(obj.get("cost_log")).__name__),
        mkcheck(
            "log_state_known",
            obj.get("log_state") in {
                "ai_cost_log_recorded",
                "ai_cost_log_recorded_soft_warn",
                "ai_cost_log_blocked",
            },
            obj.get("log_state"),
        ),
        mkcheck(
            "allow_progress_bool",
            isinstance(obj.get("allow_progress_to_h5b_governance_audit"), bool),
            obj.get("allow_progress_to_h5b_governance_audit"),
        ),
    ]

    overall_ok = all(c["ok"] for c in checks)
    failed_checks = [c["name"] for c in checks if not c["ok"]]

    report = {
        "report_type": "bybit_ai_cost_log_contract_check",
        "report_version": "v1",
        "ts_ms": now_ms,
        "overall_ok": overall_ok,
        "failed_count": len(failed_checks),
        "checks": checks,
        "failed_checks": failed_checks,
    }

    write_report(PREFIX, report)


if __name__ == "__main__":
    main()
