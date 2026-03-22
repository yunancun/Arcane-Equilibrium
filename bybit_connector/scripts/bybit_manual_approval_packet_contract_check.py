#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
from pathlib import Path
from typing import Any, Dict, List

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")
REPORT_PATH = BASE / "bybit_manual_approval_packet_latest.json"
LATEST_PATH = BASE / "bybit_manual_approval_packet_contract_latest.json"


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
    report_exists = REPORT_PATH.exists()
    obj = read_json(REPORT_PATH) if report_exists else {}

    runtime = obj.get("packet_runtime_view") or {}

    checks: List[Dict[str, Any]] = [
        check("report_exists", report_exists, str(REPORT_PATH)),
        check("packet_type_expected", obj.get("packet_type") == "bybit_manual_approval_packet", obj.get("packet_type")),
        check("packet_version_v1", obj.get("packet_version") == "v1", obj.get("packet_version")),
        check("stage_i8", obj.get("stage") == "I8", obj.get("stage")),
        check("packet_ok_bool", isinstance(obj.get("packet_ok"), bool), obj.get("packet_ok")),
        check("source_refs_dict", isinstance(obj.get("source_refs"), dict), type(obj.get("source_refs")).__name__),
        check("source_integrity_dict", isinstance(obj.get("source_integrity"), dict), type(obj.get("source_integrity")).__name__),
        check("request_summary_dict", isinstance(obj.get("request_summary"), dict), type(obj.get("request_summary")).__name__),
        check("packet_runtime_view_dict", isinstance(runtime, dict), type(runtime).__name__),
        check("manual_review_packet_dict", isinstance(obj.get("manual_review_packet"), dict), type(obj.get("manual_review_packet")).__name__),
        check("blocking_reasons_list", isinstance(obj.get("blocking_reasons"), list), type(obj.get("blocking_reasons")).__name__),
        check("warning_flags_list", isinstance(obj.get("warning_flags"), list), type(obj.get("warning_flags")).__name__),
        check(
            "packet_state_allowed",
            obj.get("packet_state") in {"manual_approval_packet_shadow_ready_soft_warn", "manual_approval_packet_blocked"},
            obj.get("packet_state"),
        ),
        check("allow_progress_bool", isinstance(obj.get("allow_progress_to_i9_operator_ack"), bool), obj.get("allow_progress_to_i9_operator_ack")),
        check("packet_for_review_only_true", runtime.get("packet_for_review_only") is True, runtime.get("packet_for_review_only")),
        check("approval_submit_live_false", runtime.get("approval_submit_live") is False, runtime.get("approval_submit_live")),
    ]

    failed_checks = [c["name"] for c in checks if not c["ok"]]
    overall_ok = len(failed_checks) == 0

    out = {
        "report_type": "bybit_manual_approval_packet_contract_check",
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
