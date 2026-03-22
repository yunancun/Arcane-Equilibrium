#!/usr/bin/env python3
from __future__ import annotations

import json
import time

from bybit_h1_report_utils import THOUGHT_GATE_DIR, read_json, save_latest_and_dated

ACC = THOUGHT_GATE_DIR / "bybit_thought_gate_acceptance_suite_latest.json"


def main() -> None:
    now_ms = int(time.time() * 1000)
    acc = read_json(ACC, {})
    overall_ok = bool(acc.get("overall_ok"))

    report = {
        "summary_type": "bybit_thought_gate_regression_summary",
        "summary_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "H1-I",
        "summary_ok": overall_ok,
        "summary_state": "h1_thought_gate_closed_ready_for_h2" if overall_ok else "h1_thought_gate_not_closed",
        "g_stage_closed_required": True,
        "h2_should_follow_now": overall_ok,
        "h3_should_follow_after_h2": overall_ok,
        "recommended_next_build_order": [
            "H2. query_budget",
            "H3. model_router v2",
            "I1. decision lease schema",
        ],
        "operator_message": (
            "H1 summary complete. Thought-gate can now be considered chapter-closed, and the formal mainline should continue to H2 then H3."
            if overall_ok
            else "H1 summary indicates chapter is not yet closed."
        ),
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))
    save_latest_and_dated("bybit_thought_gate_regression_summary", report)


if __name__ == "__main__":
    main()
