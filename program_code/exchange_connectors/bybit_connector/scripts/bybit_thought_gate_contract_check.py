#!/usr/bin/env python3
from __future__ import annotations

import json
import time

from bybit_h1_report_utils import THOUGHT_GATE_DIR, make_check, read_json, save_latest_and_dated

AUDIT = THOUGHT_GATE_DIR / "bybit_thought_gate_final_audit_latest.json"


def main() -> None:
    now_ms = int(time.time() * 1000)
    obj = read_json(AUDIT, {})
    checks = [
        make_check("report_exists", bool(obj), str(AUDIT)),
        make_check("audit_type_expected", obj.get("audit_type") == "bybit_thought_gate_final_audit", obj.get("audit_type")),
        make_check("audit_version_v1", obj.get("audit_version") == "v1", obj.get("audit_version")),
        make_check("overall_ok_bool", isinstance(obj.get("overall_ok"), bool), obj.get("overall_ok")),
        make_check("checks_list", isinstance(obj.get("checks"), list), type(obj.get("checks")).__name__),
        make_check("failed_checks_list", isinstance(obj.get("failed_checks"), list), type(obj.get("failed_checks")).__name__),
        make_check("audit_summary_dict", isinstance(obj.get("audit_summary"), dict), type(obj.get("audit_summary")).__name__),
    ]
    overall_ok = all(c["ok"] for c in checks)
    failed = [c["name"] for c in checks if not c["ok"]]

    report = {
        "report_type": "bybit_thought_gate_contract_check",
        "report_version": "v1",
        "ts_ms": now_ms,
        "overall_ok": overall_ok,
        "failed_count": len(failed),
        "checks": checks,
        "failed_checks": failed,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    save_latest_and_dated("bybit_thought_gate_contract", report)


if __name__ == "__main__":
    main()
