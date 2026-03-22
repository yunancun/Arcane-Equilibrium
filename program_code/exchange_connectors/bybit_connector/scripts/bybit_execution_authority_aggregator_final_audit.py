#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
from pathlib import Path
from typing import Any, Dict, List

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")
AGG_PATH = BASE / "bybit_execution_authority_aggregator_latest.json"
LATEST_PATH = BASE / "bybit_execution_authority_aggregator_final_audit_latest.json"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_report(report: Dict[str, Any], latest_path: Path) -> None:
    ts_ms = report.get("ts_ms")
    dated_path = latest_path.with_name(latest_path.stem.replace("_latest", f"_{ts_ms}") + latest_path.suffix)
    latest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dated_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"saved_latest={latest_path}")
    print(f"saved_dated={dated_path}")


def check(name: str, ok: bool, detail: Any) -> Dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def main() -> None:
    now_ms = int(time.time() * 1000)
    obj = read_json(AGG_PATH)

    aggregator_ok = bool(obj.get("aggregator_ok"))
    aggregator_state = obj.get("aggregator_state")
    authority_model = obj.get("authority_model") or {}
    guards = obj.get("governance_guards") or {}

    checks: List[Dict[str, Any]] = [
        check("aggregator_ok", aggregator_ok, aggregator_ok),
        check(
            "aggregator_state_green",
            aggregator_state == "execution_authority_aggregated_shadow_ready_soft_warn",
            aggregator_state,
        ),
        check(
            "shadow_authority_only_true",
            authority_model.get("shadow_authority_only") is True,
            authority_model.get("shadow_authority_only"),
        ),
        check(
            "authority_grant_live_false",
            authority_model.get("authority_grant_live") is False,
            authority_model.get("authority_grant_live"),
        ),
        check(
            "execution_authority_not_granted",
            guards.get("execution_authority") == "not_granted",
            guards.get("execution_authority"),
        ),
        check("system_mode_read_only", guards.get("system_mode") == "read_only", guards.get("system_mode")),
        check("execution_state_disabled", guards.get("execution_state") == "disabled", guards.get("execution_state")),
    ]

    failed_checks = [c["name"] for c in checks if not c["ok"]]
    overall_ok = len(failed_checks) == 0

    out = {
        "audit_type": "bybit_execution_authority_aggregator_final_audit",
        "audit_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "I7",
        "overall_ok": overall_ok,
        "failed_count": len(failed_checks),
        "total_checks": len(checks),
        "checks": checks,
        "failed_checks": failed_checks,
        "audit_summary": {
            "i7_stage_closed": overall_ok,
            "ready_for_i8": overall_ok,
            "runtime_still_protected": (
                guards.get("system_mode") == "read_only"
                and guards.get("execution_state") == "disabled"
            ),
            "shadow_authority_only": authority_model.get("shadow_authority_only") is True,
            "authority_grant_live": authority_model.get("authority_grant_live") is True,
        },
        "warning_flags": obj.get("warning_flags") or [],
        "audit_state": (
            "execution_authority_aggregator_closed_soft_warn_ready_for_i8"
            if overall_ok else
            "execution_authority_aggregator_audit_failed"
        ),
        "operator_message": (
            "I7 final audit passed. Execution authority aggregation is closed in shadow-only mode and ready for I8."
            if overall_ok else
            "I7 final audit failed."
        ),
    }

    print(json.dumps(out, ensure_ascii=False, indent=2))
    save_report(out, LATEST_PATH)


if __name__ == "__main__":
    main()
