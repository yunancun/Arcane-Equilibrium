#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time

from bybit_h_stage_common import RUNTIME_BASE, mkcheck, read_json_if_exists, write_report

REPORT_PATH = RUNTIME_BASE / "bybit_model_router_runtime_latest.json"
PREFIX = "bybit_model_router_runtime_contract"


def main() -> None:
    now_ms = int(time.time() * 1000)
    obj = read_json_if_exists(REPORT_PATH)
    runtime_summary = obj.get("runtime_summary") or {}

    checks = [
        mkcheck("report_exists", REPORT_PATH.exists(), str(REPORT_PATH)),
        mkcheck("runtime_type_expected", obj.get("runtime_type") == "bybit_model_router_runtime", obj.get("runtime_type")),
        mkcheck("runtime_version_v1", obj.get("runtime_version") == "v1", obj.get("runtime_version")),
        mkcheck("stage_h3c", obj.get("stage") == "H3-C", obj.get("stage")),
        mkcheck("runtime_ok_bool", isinstance(obj.get("runtime_ok"), bool), obj.get("runtime_ok")),
        mkcheck("runtime_summary_dict", isinstance(runtime_summary, dict), type(runtime_summary).__name__),
        mkcheck("runtime_state_known", obj.get("runtime_state") in {
            "model_router_runtime_ready",
            "model_router_runtime_ready_soft_warn",
            "model_router_runtime_blocked",
        }, obj.get("runtime_state")),
        mkcheck("allow_progress_bool", isinstance(obj.get("allow_progress_to_h3d_final_audit"), bool), obj.get("allow_progress_to_h3d_final_audit")),
    ]

    overall_ok = all(c["ok"] for c in checks)
    failed_checks = [c["name"] for c in checks if not c["ok"]]

    report = {
        "report_type": "bybit_model_router_runtime_contract_check",
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
