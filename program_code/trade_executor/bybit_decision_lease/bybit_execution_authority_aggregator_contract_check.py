#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
from pathlib import Path
import os
from typing import Any, Dict, List
from bybit_decision_lease_common import read_json_required as read_json, save_report

BASE = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")
REPORT_PATH = BASE / "bybit_execution_authority_aggregator_latest.json"
LATEST_PATH = BASE / "bybit_execution_authority_aggregator_contract_latest.json"


def check(name: str, ok: bool, detail: Any) -> Dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def main() -> None:
    now_ms = int(time.time() * 1000)
    report_exists = REPORT_PATH.exists()
    obj = read_json(REPORT_PATH) if report_exists else {}

    checks: List[Dict[str, Any]] = [
        check("report_exists", report_exists, str(REPORT_PATH)),
        check("aggregator_type_expected", obj.get("aggregator_type") == "bybit_execution_authority_aggregator", obj.get("aggregator_type")),
        check("aggregator_version_v1", obj.get("aggregator_version") == "v1", obj.get("aggregator_version")),
        check("stage_i7", obj.get("stage") == "I7", obj.get("stage")),
        check("aggregator_ok_bool", isinstance(obj.get("aggregator_ok"), bool), obj.get("aggregator_ok")),
        check("source_refs_dict", isinstance(obj.get("source_refs"), dict), type(obj.get("source_refs")).__name__),
        check("source_integrity_dict", isinstance(obj.get("source_integrity"), dict), type(obj.get("source_integrity")).__name__),
        check("request_summary_dict", isinstance(obj.get("request_summary"), dict), type(obj.get("request_summary")).__name__),
        check("authority_model_dict", isinstance(obj.get("authority_model"), dict), type(obj.get("authority_model")).__name__),
        check("governance_guards_dict", isinstance(obj.get("governance_guards"), dict), type(obj.get("governance_guards")).__name__),
        check("aggregated_authority_view_dict", isinstance(obj.get("aggregated_authority_view"), dict), type(obj.get("aggregated_authority_view")).__name__),
        check("blocking_reasons_list", isinstance(obj.get("blocking_reasons"), list), type(obj.get("blocking_reasons")).__name__),
        check("warning_flags_list", isinstance(obj.get("warning_flags"), list), type(obj.get("warning_flags")).__name__),
        check(
            "aggregator_state_allowed",
            obj.get("aggregator_state") in {
                "execution_authority_aggregated_shadow_ready_soft_warn",
                "execution_authority_aggregation_blocked",
            },
            obj.get("aggregator_state"),
        ),
        check(
            "allow_progress_bool",
            isinstance(obj.get("allow_progress_to_i8_manual_approval_packet"), bool),
            obj.get("allow_progress_to_i8_manual_approval_packet"),
        ),
        check(
            "shadow_authority_only_true",
            (obj.get("authority_model") or {}).get("shadow_authority_only") is True,
            (obj.get("authority_model") or {}).get("shadow_authority_only"),
        ),
        check(
            "authority_grant_live_false",
            (obj.get("authority_model") or {}).get("authority_grant_live") is False,
            (obj.get("authority_model") or {}).get("authority_grant_live"),
        ),
    ]

    failed_checks = [c["name"] for c in checks if not c["ok"]]
    overall_ok = len(failed_checks) == 0

    out = {
        "report_type": "bybit_execution_authority_aggregator_contract_check",
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
