#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from pathlib import Path

from bybit_h_stage_common import mkcheck, read_json_if_exists, write_report

REPORT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate/bybit_ai_governance_audit_latest.json")
PREFIX = "bybit_ai_governance_audit_contract"


def main() -> None:
    now_ms = int(time.time() * 1000)
    obj = read_json_if_exists(REPORT_PATH)

    checks = [
        mkcheck("report_exists", REPORT_PATH.exists(), str(REPORT_PATH)),
        mkcheck("audit_type_expected", obj.get("audit_type") == "bybit_ai_governance_audit", obj.get("audit_type")),
        mkcheck("audit_version_v1", obj.get("audit_version") == "v1", obj.get("audit_version")),
        mkcheck("stage_h5b", obj.get("stage") == "H5-B", obj.get("stage")),
        mkcheck("audit_ok_bool", isinstance(obj.get("audit_ok"), bool), obj.get("audit_ok")),
        mkcheck("checks_list", isinstance(obj.get("checks"), list), type(obj.get("checks")).__name__),
        mkcheck("failed_checks_list", isinstance(obj.get("failed_checks"), list), type(obj.get("failed_checks")).__name__),
        mkcheck(
            "audit_state_known",
            obj.get("audit_state") in {
                "ai_governance_audit_passed",
                "ai_governance_audit_passed_soft_warn",
                "ai_governance_audit_blocked",
            },
            obj.get("audit_state"),
        ),
        mkcheck(
            "allow_progress_bool",
            isinstance(obj.get("allow_progress_to_h5c_final_audit"), bool),
            obj.get("allow_progress_to_h5c_final_audit"),
        ),
    ]

    overall_ok = all(c["ok"] for c in checks)
    failed_checks = [c["name"] for c in checks if not c["ok"]]

    report = {
        "report_type": "bybit_ai_governance_audit_contract_check",
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
