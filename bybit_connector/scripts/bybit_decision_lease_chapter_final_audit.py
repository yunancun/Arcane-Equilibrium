#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
from pathlib import Path
from typing import Any, Dict, List

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")
SUMMARY_PATH = BASE / "bybit_decision_lease_chapter_summary_latest.json"
HANDOFF_PATH = BASE / "bybit_decision_lease_chapter_handoff_latest.json"
I9_ACK_PATH = BASE / "bybit_operator_ack_shadow_latest.json"
LATEST_PATH = BASE / "bybit_decision_lease_chapter_final_audit_latest.json"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_report(report: Dict[str, Any], latest_path: Path) -> None:
    ts_ms = report.get("ts_ms")
    dated_path = latest_path.with_name(latest_path.stem.replace("_latest", f"_{ts_ms}") + latest_path.suffix)
    latest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dated_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest_path}")
    print(f"saved_dated={dated_path}")


def check(name: str, ok: bool, detail: Any) -> Dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def main() -> None:
    now_ms = int(time.time() * 1000)

    summary = read_json(SUMMARY_PATH)
    handoff = read_json(HANDOFF_PATH)
    i9 = read_json(I9_ACK_PATH)

    chapter_summary = summary.get("chapter_summary") or {}
    runtime = (i9.get("ack_runtime_view") or {})

    checks: List[Dict[str, Any]] = [
        check("summary_ok", bool(summary.get("summary_ok")), summary.get("summary_ok")),
        check("handoff_ok", bool(handoff.get("handoff_ok")), handoff.get("handoff_ok")),
        check("i_chapter_closed", chapter_summary.get("i_chapter_closed") is True, chapter_summary.get("i_chapter_closed")),
        check("runtime_still_protected", chapter_summary.get("runtime_still_protected") is True, chapter_summary.get("runtime_still_protected")),
        check("execution_authority_not_granted", runtime.get("execution_authority") == "not_granted", runtime.get("execution_authority")),
        check("live_execution_allowed_false", runtime.get("live_execution_allowed") is False, runtime.get("live_execution_allowed")),
        check("decision_lease_emitted_false", runtime.get("decision_lease_emitted") is False, runtime.get("decision_lease_emitted")),
        check("live_operator_ack_enabled_false", runtime.get("live_operator_ack_enabled") is False, runtime.get("live_operator_ack_enabled")),
        check("approval_submit_live_false", runtime.get("approval_submit_live") is False, runtime.get("approval_submit_live")),
    ]

    failed_checks = [c["name"] for c in checks if not c["ok"]]
    overall_ok = len(failed_checks) == 0

    report = {
        "audit_type": "bybit_decision_lease_chapter_final_audit",
        "audit_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "I10",
        "overall_ok": overall_ok,
        "failed_count": len(failed_checks),
        "total_checks": len(checks),
        "checks": checks,
        "failed_checks": failed_checks,
        "audit_summary": {
            "i_chapter_closed": overall_ok,
            "shadow_control_plane_closed": overall_ok,
            "runtime_still_protected": (
                runtime.get("execution_authority") == "not_granted"
                and runtime.get("live_execution_allowed") is False
                and runtime.get("decision_lease_emitted") is False
                and runtime.get("live_operator_ack_enabled") is False
                and runtime.get("approval_submit_live") is False
            ),
            "ready_for_future_live_design": bool(summary.get("summary_ok")),
        },
        "warning_flags": summary.get("warning_flags") or [],
        "audit_state": (
            "decision_lease_chapter_closed_soft_warn"
            if overall_ok else
            "decision_lease_chapter_audit_failed"
        ),
        "operator_message": (
            "I10 final audit passed. I chapter is formally closed as a shadow-only decision-lease control plane."
            if overall_ok else
            "I10 final audit failed."
        ),
    }

    save_report(report, LATEST_PATH)


if __name__ == "__main__":
    main()
