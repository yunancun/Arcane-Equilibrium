#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
from pathlib import Path
import os
from typing import Any, Dict
from bybit_decision_lease_common import read_json_required as read_json, save_report

BASE = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")
SUMMARY_PATH = BASE / "bybit_decision_lease_chapter_summary_latest.json"
I9_ACK_PATH = BASE / "bybit_operator_ack_shadow_latest.json"
LATEST_PATH = BASE / "bybit_decision_lease_chapter_handoff_latest.json"


def main() -> None:
    now_ms = int(time.time() * 1000)

    summary = read_json(SUMMARY_PATH)
    i9 = read_json(I9_ACK_PATH)

    chapter_summary = summary.get("chapter_summary") or {}
    runtime = (i9.get("ack_runtime_view") or {})

    handoff_ok = bool(summary.get("summary_ok")) and chapter_summary.get("runtime_still_protected") is True

    if handoff_ok:
        handoff_state = "decision_lease_chapter_closed_handoff_ready"
        operator_message = (
            "I chapter handoff complete. Decision-lease control plane is closed in shadow mode and may be used as the basis for later live-gating design."
        )
    else:
        handoff_state = "decision_lease_chapter_handoff_blocked"
        operator_message = "I chapter handoff blocked."

    report = {
        "handoff_type": "bybit_decision_lease_chapter_handoff",
        "handoff_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "I10",
        "handoff_ok": handoff_ok,
        "handoff_state": handoff_state,
        "hard_safety_boundaries": {
            "execution_authority": runtime.get("execution_authority"),
            "live_execution_allowed": runtime.get("live_execution_allowed"),
            "decision_lease_emitted": runtime.get("decision_lease_emitted"),
            "live_operator_ack_enabled": runtime.get("live_operator_ack_enabled"),
            "approval_submit_live": runtime.get("approval_submit_live"),
        },
        "recommended_next_build_order": [
            "Bind provider pricing table into mainline",
            "Repair freshness / last-trade source quality",
            "Design future live pilot only behind explicit operator authority",
        ],
        "operator_guidance": [
            "Do not treat I chapter output as live execution permission.",
            "Keep operator approval shadow-only until a separate live pilot chapter is explicitly designed.",
            "Preserve explicit authority aggregation before any future lease emission path is enabled.",
        ],
        "operator_message": operator_message,
    }

    save_report(report, LATEST_PATH, print_json=True)


if __name__ == "__main__":
    main()
