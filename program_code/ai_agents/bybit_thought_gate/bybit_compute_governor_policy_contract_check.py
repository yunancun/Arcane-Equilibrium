#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from bybit_h_stage_common import RUNTIME_BASE, mkcheck, read_json_if_exists, write_report

REPORT_PATH = RUNTIME_BASE / "bybit_compute_governor_policy_latest.json"
PREFIX = "bybit_compute_governor_policy_contract"


def main() -> None:
    now_ms = int(time.time() * 1000)
    obj = read_json_if_exists(REPORT_PATH)

    checks = [
        mkcheck("report_exists", REPORT_PATH.exists(), str(REPORT_PATH)),
        mkcheck("policy_type_expected", obj.get("policy_type") == "bybit_compute_governor_policy", obj.get("policy_type")),
        mkcheck("policy_version_v1", obj.get("policy_version") == "v1", obj.get("policy_version")),
        mkcheck("stage_h4a", obj.get("stage") == "H4-A", obj.get("stage")),
        mkcheck("policy_ok_bool", isinstance(obj.get("policy_ok"), bool), obj.get("policy_ok")),
        mkcheck("governor_policy_dict", isinstance(obj.get("governor_policy"), dict), type(obj.get("governor_policy")).__name__),
        mkcheck(
            "policy_state_known",
            obj.get("policy_state") in {
                "compute_governor_policy_snapshotted",
                "compute_governor_policy_snapshotted_soft_warn",
                "compute_governor_policy_blocked",
            },
            obj.get("policy_state"),
        ),
        mkcheck("allow_progress_bool", isinstance(obj.get("allow_progress_to_h4b_governor_gate"), bool), obj.get("allow_progress_to_h4b_governor_gate")),
    ]

    overall_ok = all(c["ok"] for c in checks)
    failed_checks = [c["name"] for c in checks if not c["ok"]]

    report = {
        "report_type": "bybit_compute_governor_policy_contract_check",
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
