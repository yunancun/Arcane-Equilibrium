#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from pathlib import Path

from bybit_h1_report_utils import THOUGHT_GATE_DIR, make_check, read_json, save_latest_and_dated

REPORT_PATH = THOUGHT_GATE_DIR / "bybit_ai_response_check_latest.json"


def main() -> None:
    now_ms = int(time.time() * 1000)
    obj = read_json(REPORT_PATH, {})
    checks = [
        make_check("report_exists", bool(obj), str(REPORT_PATH)),
        make_check("report_type_expected", obj.get("report_type") == "bybit_ai_response_check", obj.get("report_type")),
        make_check("report_version_v1", obj.get("report_version") == "v1", obj.get("report_version")),
        make_check("stage_h1g", obj.get("stage") == "H1-G", obj.get("stage")),
        make_check("overall_ok_bool", isinstance(obj.get("overall_ok"), bool), obj.get("overall_ok")),
        make_check("checks_list", isinstance(obj.get("checks"), list), type(obj.get("checks")).__name__),
        make_check("failed_checks_list", isinstance(obj.get("failed_checks"), list), type(obj.get("failed_checks")).__name__),
        make_check("response_state_known", obj.get("response_state") in {"response_json_contract_satisfied", "response_invalid_or_incomplete"}, obj.get("response_state")),
        make_check("allow_progress_bool", isinstance(obj.get("allow_progress_to_h1h_governed_decision"), bool), obj.get("allow_progress_to_h1h_governed_decision")),
    ]
    overall_ok = all(c["ok"] for c in checks)
    failed = [c["name"] for c in checks if not c["ok"]]

    report = {
        "report_type": "bybit_ai_response_check_contract_check",
        "report_version": "v1",
        "ts_ms": now_ms,
        "overall_ok": overall_ok,
        "failed_count": len(failed),
        "checks": checks,
        "failed_checks": failed,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    save_latest_and_dated("bybit_ai_response_check_contract", report)


if __name__ == "__main__":
    main()
