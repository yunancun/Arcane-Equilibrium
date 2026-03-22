#!/usr/bin/env python3
from __future__ import annotations

import json
import time

from bybit_h1_report_utils import THOUGHT_GATE_DIR, make_check, read_json, save_latest_and_dated

REPORT_PATH = THOUGHT_GATE_DIR / "bybit_ai_governed_decision_latest.json"


def main() -> None:
    now_ms = int(time.time() * 1000)
    obj = read_json(REPORT_PATH, {})
    guards = obj.get("governance_guards") or {}

    checks = [
        make_check("report_exists", bool(obj), str(REPORT_PATH)),
        make_check("decision_type_expected", obj.get("decision_type") == "bybit_ai_governed_decision", obj.get("decision_type")),
        make_check("decision_version_v1", obj.get("decision_version") == "v1", obj.get("decision_version")),
        make_check("stage_h1h", obj.get("stage") == "H1-H", obj.get("stage")),
        make_check("decision_ok_bool", isinstance(obj.get("decision_ok"), bool), obj.get("decision_ok")),
        make_check("governance_guards_dict", isinstance(guards, dict), type(guards).__name__),
        make_check("system_mode_read_only", guards.get("system_mode") == "read_only", guards.get("system_mode")),
        make_check("execution_state_disabled", guards.get("execution_state") == "disabled", guards.get("execution_state")),
        make_check("execution_authority_not_granted", guards.get("execution_authority") == "not_granted", guards.get("execution_authority")),
        make_check("live_execution_allowed_false", guards.get("live_execution_allowed") is False, guards.get("live_execution_allowed")),
        make_check("allow_progress_bool", isinstance(obj.get("allow_progress_to_h1i_acceptance"), bool), obj.get("allow_progress_to_h1i_acceptance")),
    ]
    overall_ok = all(c["ok"] for c in checks)
    failed = [c["name"] for c in checks if not c["ok"]]

    report = {
        "report_type": "bybit_ai_governed_decision_contract_check",
        "report_version": "v1",
        "ts_ms": now_ms,
        "overall_ok": overall_ok,
        "failed_count": len(failed),
        "checks": checks,
        "failed_checks": failed,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    save_latest_and_dated("bybit_ai_governed_decision_contract", report)


if __name__ == "__main__":
    main()
