#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
from pathlib import Path
import os
from typing import Any, Dict, List
from bybit_decision_lease_common import read_json_required as read_json, save_report

BASE = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")
REPORT_PATH = BASE / "bybit_decision_lease_approval_bridge_latest.json"
LATEST_PATH = BASE / "bybit_decision_lease_approval_bridge_contract_latest.json"


def check(name: str, ok: bool, detail: Any) -> Dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def main() -> None:
    now_ms = int(time.time() * 1000)

    report_exists = REPORT_PATH.exists()
    obj = read_json(REPORT_PATH) if report_exists else {}

    checks: List[Dict[str, Any]] = [
        check("report_exists", report_exists, str(REPORT_PATH)),
        check("bridge_type_expected", obj.get("bridge_type") == "bybit_decision_lease_approval_bridge", obj.get("bridge_type")),
        check("bridge_version_v1", obj.get("bridge_version") == "v1", obj.get("bridge_version")),
        check("stage_i6", obj.get("stage") == "I6", obj.get("stage")),
        check("bridge_ok_bool", isinstance(obj.get("bridge_ok"), bool), obj.get("bridge_ok")),
        check("source_refs_dict", isinstance(obj.get("source_refs"), dict), type(obj.get("source_refs")).__name__),
        check("source_integrity_dict", isinstance(obj.get("source_integrity"), dict), type(obj.get("source_integrity")).__name__),
        check("request_summary_dict", isinstance(obj.get("request_summary"), dict), type(obj.get("request_summary")).__name__),
        check("approval_model_dict", isinstance(obj.get("approval_model"), dict), type(obj.get("approval_model")).__name__),
        check("governance_guards_dict", isinstance(obj.get("governance_guards"), dict), type(obj.get("governance_guards")).__name__),
        check("lease_runtime_view_dict", isinstance(obj.get("lease_runtime_view"), dict), type(obj.get("lease_runtime_view")).__name__),
        check("approval_bridge_view_dict", isinstance(obj.get("approval_bridge_view"), dict), type(obj.get("approval_bridge_view")).__name__),
        check("warning_flags_list", isinstance(obj.get("warning_flags"), list), type(obj.get("warning_flags")).__name__),
        check("blocking_reasons_list", isinstance(obj.get("blocking_reasons"), list), type(obj.get("blocking_reasons")).__name__),
        check(
            "bridge_state_allowed",
            obj.get("bridge_state") in {
                "decision_lease_approval_bridge_shadow_ready_soft_warn",
                "decision_lease_approval_bridge_blocked",
            },
            obj.get("bridge_state"),
        ),
        check(
            "allow_progress_bool",
            isinstance(obj.get("allow_progress_to_i7_execution_authority_aggregator"), bool),
            obj.get("allow_progress_to_i7_execution_authority_aggregator"),
        ),
        check(
            "shadow_bridge_only_true_when_green",
            (obj.get("approval_bridge_view") or {}).get("shadow_bridge_only") is True if obj.get("bridge_ok") else True,
            (obj.get("approval_bridge_view") or {}).get("shadow_bridge_only"),
        ),
        check(
            "live_approval_grant_active_false",
            (obj.get("approval_bridge_view") or {}).get("live_approval_grant_active") is False,
            (obj.get("approval_bridge_view") or {}).get("live_approval_grant_active"),
        ),
    ]

    failed_checks = [c["name"] for c in checks if not c["ok"]]
    overall_ok = len(failed_checks) == 0

    out = {
        "report_type": "bybit_decision_lease_approval_bridge_contract_check",
        "report_version": "v1",
        "ts_ms": now_ms,
        "overall_ok": overall_ok,
        "failed_count": len(failed_checks),
        "checks": checks,
        "failed_checks": failed_checks,
    }

    print(json.dumps(out, ensure_ascii=False, indent=2))
    save_report(out, LATEST_PATH)


if __name__ == "__main__":
    main()
