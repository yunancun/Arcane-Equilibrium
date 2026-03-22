#!/usr/bin/env python3
from __future__ import annotations

import json
import time

from bybit_h1_report_utils import THOUGHT_GATE_DIR, make_check, read_json, save_latest_and_dated

RESP_CHECK = THOUGHT_GATE_DIR / "bybit_ai_response_check_latest.json"
GOV_DECISION = THOUGHT_GATE_DIR / "bybit_ai_governed_decision_latest.json"
INV = THOUGHT_GATE_DIR / "bybit_ai_invocation_attempt_latest.json"


def main() -> None:
    now_ms = int(time.time() * 1000)
    r = read_json(RESP_CHECK, {})
    g = read_json(GOV_DECISION, {})
    i = read_json(INV, {})

    parsed = (r.get("parsed_json_object") or {})
    guards = (g.get("governance_guards") or {})

    checks = [
        make_check("response_check_overall_ok", r.get("overall_ok") is True, r.get("overall_ok")),
        make_check("governed_decision_ok", g.get("decision_ok") is True, g.get("decision_ok")),
        make_check("invocation_state_json_ready", i.get("invocation_state") == "invocation_success_json_ready", i.get("invocation_state")),
        make_check("analysis_mode_observation_only", parsed.get("analysis_mode") == "observation_only", parsed.get("analysis_mode")),
        make_check("action_bias_present", parsed.get("action_bias") in {"long_bias", "short_bias", "flat_bias"}, parsed.get("action_bias")),
        make_check("execution_authority_not_granted", guards.get("execution_authority") == "not_granted", guards.get("execution_authority")),
        make_check("live_execution_allowed_false", guards.get("live_execution_allowed") is False, guards.get("live_execution_allowed")),
        make_check("decision_lease_emitted_false", guards.get("decision_lease_emitted") is False, guards.get("decision_lease_emitted")),
    ]
    overall_ok = all(c["ok"] for c in checks)
    failed = [c["name"] for c in checks if not c["ok"]]

    report = {
        "suite_type": "bybit_thought_gate_acceptance_suite",
        "suite_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "H1-I",
        "overall_ok": overall_ok,
        "failed_count": len(failed),
        "checks": checks,
        "failed_checks": failed,
        "suite_state": "thought_gate_acceptance_passed" if overall_ok else "thought_gate_acceptance_failed",
        "recommended_action": "may_progress_to_h1i_summary" if overall_ok else "inspect_h1_acceptance_failures",
        "operator_message": (
            "H1-I acceptance suite passed. Thought-gate chain is closed as a governed read-only AI observation path."
            if overall_ok
            else "H1-I acceptance suite failed. Inspect failed_checks before chapter closure."
        ),
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))
    save_latest_and_dated("bybit_thought_gate_acceptance_suite", report)


if __name__ == "__main__":
    main()
