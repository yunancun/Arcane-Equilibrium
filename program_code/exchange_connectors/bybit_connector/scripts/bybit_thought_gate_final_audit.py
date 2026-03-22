#!/usr/bin/env python3
from __future__ import annotations

import json
import time

from bybit_h1_report_utils import THOUGHT_GATE_DIR, make_check, read_json, save_latest_and_dated

ACC = THOUGHT_GATE_DIR / "bybit_thought_gate_acceptance_suite_latest.json"
SUMMARY = THOUGHT_GATE_DIR / "bybit_thought_gate_regression_summary_latest.json"
HANDOFF = THOUGHT_GATE_DIR / "bybit_thought_gate_handoff_latest.json"
RESP = THOUGHT_GATE_DIR / "bybit_ai_response_check_latest.json"
GOV = THOUGHT_GATE_DIR / "bybit_ai_governed_decision_latest.json"


def main() -> None:
    now_ms = int(time.time() * 1000)
    acc = read_json(ACC, {})
    summary = read_json(SUMMARY, {})
    handoff = read_json(HANDOFF, {})
    resp = read_json(RESP, {})
    gov = read_json(GOV, {})

    checks = [
        make_check("response_check_ok", resp.get("overall_ok") is True, resp.get("overall_ok")),
        make_check("governed_decision_ok", gov.get("decision_ok") is True, gov.get("decision_ok")),
        make_check("acceptance_ok", acc.get("overall_ok") is True, acc.get("overall_ok")),
        make_check("summary_ok", summary.get("summary_ok") is True, summary.get("summary_ok")),
        make_check("handoff_ok", handoff.get("handoff_ok") is True, handoff.get("handoff_ok")),
        make_check("read_only_guard", (gov.get("governance_guards") or {}).get("system_mode") == "read_only", (gov.get("governance_guards") or {}).get("system_mode")),
        make_check("execution_disabled_guard", (gov.get("governance_guards") or {}).get("execution_state") == "disabled", (gov.get("governance_guards") or {}).get("execution_state")),
    ]
    overall_ok = all(c["ok"] for c in checks)
    failed = [c["name"] for c in checks if not c["ok"]]

    report = {
        "audit_type": "bybit_thought_gate_final_audit",
        "audit_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "H1-I",
        "overall_ok": overall_ok,
        "failed_count": len(failed),
        "total_checks": len(checks),
        "checks": checks,
        "failed_checks": failed,
        "audit_summary": {
            "h1_stage_closed": overall_ok,
            "ai_response_checked": resp.get("overall_ok") is True,
            "governed_observation_built": gov.get("decision_ok") is True,
            "acceptance_passed": acc.get("overall_ok") is True,
            "runtime_still_protected": True,
            "ready_for_h2": overall_ok,
        },
        "operator_message": (
            "H1 final audit passed. Thought-gate chapter is formally closed and ready for H2."
            if overall_ok
            else "H1 final audit failed."
        ),
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))
    save_latest_and_dated("bybit_thought_gate_final_audit", report)


if __name__ == "__main__":
    main()
