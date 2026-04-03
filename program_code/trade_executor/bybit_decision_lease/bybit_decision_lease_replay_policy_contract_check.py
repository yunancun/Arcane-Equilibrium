#!/usr/bin/env python3
import json
import time
from pathlib import Path
import os
from typing import Any, Dict, List
from bybit_decision_lease_common import read_json_required as read_json, save_report_stem

BASE = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")
TARGET = BASE / "bybit_decision_lease_replay_policy_latest.json"
STEM = "bybit_decision_lease_replay_policy_contract"


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
    add("policy_type_expected", obj.get("policy_type") == "bybit_decision_lease_replay_policy", obj.get("policy_type"))
    add("policy_version_v1", obj.get("policy_version") == "v1", obj.get("policy_version"))
    add("stage_i4a", obj.get("stage") == "I4-A", obj.get("stage"))
    add("policy_ok_bool", isinstance(obj.get("policy_ok"), bool), obj.get("policy_ok"))
    add("replay_policy_dict", isinstance(obj.get("replay_policy"), dict), type(obj.get("replay_policy")).__name__ if obj.get("replay_policy") is not None else None)
    add("checks_list", isinstance(obj.get("checks"), list), type(obj.get("checks")).__name__ if obj.get("checks") is not None else None)
    add("failed_checks_list", isinstance(obj.get("failed_checks"), list), type(obj.get("failed_checks")).__name__ if obj.get("failed_checks") is not None else None)
    add("policy_state_known", obj.get("policy_state") in {
        "decision_lease_replay_policy_blocked",
        "decision_lease_replay_policy_ready_soft_warn",
        "decision_lease_replay_policy_ready",
    }, obj.get("policy_state"))
    add("allow_progress_bool", isinstance(obj.get("allow_progress_to_i4b_replay_guard"), bool), obj.get("allow_progress_to_i4b_replay_guard"))

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
