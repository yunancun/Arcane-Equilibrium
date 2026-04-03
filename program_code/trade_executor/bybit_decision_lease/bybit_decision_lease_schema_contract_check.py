#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from pathlib import Path
import os

from bybit_h_stage_common import mkcheck, read_json_if_exists, write_report

REPORT_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate/bybit_decision_lease_schema_latest.json")
PREFIX = "bybit_decision_lease_schema_contract"


def main() -> None:
    now_ms = int(time.time() * 1000)
    obj = read_json_if_exists(REPORT_PATH)

    checks = [
        mkcheck("report_exists", REPORT_PATH.exists(), str(REPORT_PATH)),
        mkcheck("schema_type_expected", obj.get("schema_type") == "bybit_decision_lease_schema", obj.get("schema_type")),
        mkcheck("schema_version_v1", obj.get("schema_version") == "v1", obj.get("schema_version")),
        mkcheck("stage_i1a", obj.get("stage") == "I1-A", obj.get("stage")),
        mkcheck("schema_ok_bool", isinstance(obj.get("schema_ok"), bool), obj.get("schema_ok")),
        mkcheck("lease_schema_definition_dict", isinstance(obj.get("lease_schema_definition"), dict), type(obj.get("lease_schema_definition")).__name__),
        mkcheck("lease_template_dict", isinstance(obj.get("lease_template"), dict), type(obj.get("lease_template")).__name__),
        mkcheck("schema_runtime_view_dict", isinstance(obj.get("schema_runtime_view"), dict), type(obj.get("schema_runtime_view")).__name__),
        mkcheck(
            "schema_state_known",
            obj.get("schema_state") in {
                "decision_lease_schema_ready_no_emit",
                "decision_lease_schema_ready_no_emit_soft_warn",
                "decision_lease_schema_blocked",
            },
            obj.get("schema_state"),
        ),
        mkcheck(
            "allow_progress_bool",
            isinstance(obj.get("allow_progress_to_i1b_final_audit"), bool),
            obj.get("allow_progress_to_i1b_final_audit"),
        ),
    ]

    overall_ok = all(c["ok"] for c in checks)
    failed_checks = [c["name"] for c in checks if not c["ok"]]

    report = {
        "report_type": "bybit_decision_lease_schema_contract_check",
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
