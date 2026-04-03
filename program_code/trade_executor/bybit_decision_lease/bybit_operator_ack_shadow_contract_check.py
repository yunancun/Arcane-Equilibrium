#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
from pathlib import Path
import os
from typing import Any, Dict, List
from bybit_decision_lease_common import read_json_required as read_json, save_report

BASE = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")
REPORT_PATH = BASE / "bybit_operator_ack_shadow_latest.json"
LATEST_PATH = BASE / "bybit_operator_ack_shadow_contract_latest.json"


def check(name: str, ok: bool, detail: Any) -> Dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def main() -> None:
    now_ms = int(time.time() * 1000)
    report_exists = REPORT_PATH.exists()
    obj = read_json(REPORT_PATH) if report_exists else {}

    runtime = obj.get("ack_runtime_view") or {}

    checks: List[Dict[str, Any]] = [
        check("report_exists", report_exists, str(REPORT_PATH)),
        check("ack_type_expected", obj.get("ack_type") == "bybit_operator_ack_shadow", obj.get("ack_type")),
        check("ack_version_v1", obj.get("ack_version") == "v1", obj.get("ack_version")),
        check("stage_i9", obj.get("stage") == "I9", obj.get("stage")),
        check("ack_ok_bool", isinstance(obj.get("ack_ok"), bool), obj.get("ack_ok")),
        check("source_refs_dict", isinstance(obj.get("source_refs"), dict), type(obj.get("source_refs")).__name__),
        check("source_integrity_dict", isinstance(obj.get("source_integrity"), dict), type(obj.get("source_integrity")).__name__),
        check("request_summary_dict", isinstance(obj.get("request_summary"), dict), type(obj.get("request_summary")).__name__),
        check("ack_runtime_view_dict", isinstance(runtime, dict), type(runtime).__name__),
        check("operator_ack_shadow_dict", isinstance(obj.get("operator_ack_shadow"), dict), type(obj.get("operator_ack_shadow")).__name__),
        check("blocking_reasons_list", isinstance(obj.get("blocking_reasons"), list), type(obj.get("blocking_reasons")).__name__),
        check("warning_flags_list", isinstance(obj.get("warning_flags"), list), type(obj.get("warning_flags")).__name__),
        check(
            "ack_state_allowed",
            obj.get("ack_state") in {"operator_ack_shadow_ready_soft_warn", "operator_ack_shadow_blocked"},
            obj.get("ack_state"),
        ),
        check("allow_progress_bool", isinstance(obj.get("allow_progress_to_i10_finalization"), bool), obj.get("allow_progress_to_i10_finalization")),
        check("operator_ack_shadow_only_true", runtime.get("operator_ack_shadow_only") is True, runtime.get("operator_ack_shadow_only")),
        check("live_operator_ack_enabled_false", runtime.get("live_operator_ack_enabled") is False, runtime.get("live_operator_ack_enabled")),
    ]

    failed_checks = [c["name"] for c in checks if not c["ok"]]
    overall_ok = len(failed_checks) == 0

    out = {
        "report_type": "bybit_operator_ack_shadow_contract_check",
        "report_version": "v1",
        "ts_ms": now_ms,
        "overall_ok": overall_ok,
        "failed_count": len(failed_checks),
        "checks": checks,
        "failed_checks": failed_checks,
    }

    save_report(out, LATEST_PATH, print_json=True)


if __name__ == "__main__":
    main()
