#!/usr/bin/env python3
from __future__ import annotations

import json
import time

from bybit_h1_report_utils import THOUGHT_GATE_DIR, read_json, save_latest_and_dated

SUMMARY = THOUGHT_GATE_DIR / "bybit_thought_gate_regression_summary_latest.json"


def main() -> None:
    now_ms = int(time.time() * 1000)
    s = read_json(SUMMARY, {})
    summary_ok = bool(s.get("summary_ok"))

    report = {
        "handoff_type": "bybit_thought_gate_handoff",
        "handoff_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "H1-I",
        "handoff_ok": summary_ok,
        "handoff_state": "h1_closed_ready_for_h2" if summary_ok else "h1_not_ready_for_handoff",
        "hard_safety_boundaries": {
            "system_mode": "read_only",
            "execution_state": "disabled",
            "execution_authority": "not_granted",
            "decision_lease_emitted": False,
        },
        "recommended_next_build_order": s.get("recommended_next_build_order") or [],
        "operator_guidance": [
            "Do not treat H1 output as execution permission.",
            "Proceed to H2 query_budget before expanding model routing complexity.",
            "Keep provider-native output under contract and audit checks.",
        ],
        "operator_message": (
            "H1 handoff complete. Chapter is closed as a governed AI observation path and ready to hand off to H2."
            if summary_ok
            else "H1 handoff blocked because summary is not yet green."
        ),
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))
    save_latest_and_dated("bybit_thought_gate_handoff", report)


if __name__ == "__main__":
    main()
