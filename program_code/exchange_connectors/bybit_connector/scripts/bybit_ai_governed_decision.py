#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from pathlib import Path

from bybit_h1_report_utils import THOUGHT_GATE_DIR, read_json, save_latest_and_dated

RESP_CHECK_PATH = THOUGHT_GATE_DIR / "bybit_ai_response_check_latest.json"
INV_PATH = THOUGHT_GATE_DIR / "bybit_ai_invocation_attempt_latest.json"
REQ_PATH = THOUGHT_GATE_DIR / "bybit_ai_request_envelope_latest.json"


def main() -> None:
    now_ms = int(time.time() * 1000)
    resp_check = read_json(RESP_CHECK_PATH, {})
    inv = read_json(INV_PATH, {})
    req = read_json(REQ_PATH, {})

    parsed = resp_check.get("parsed_json_object") or {}
    overall_ok = bool(resp_check.get("overall_ok"))

    if overall_ok and isinstance(parsed, dict):
        decision_state = "governed_observation_ready"
        allow_progress = True
        recommended_action = "may_progress_to_h1i_acceptance"
    else:
        decision_state = "governed_observation_blocked"
        allow_progress = False
        recommended_action = "inspect_h1g_before_h1h"

    report = {
        "decision_type": "bybit_ai_governed_decision",
        "decision_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "H1-H",
        "decision_ok": overall_ok,
        "source_refs": {
            "ai_response_check_path": str(RESP_CHECK_PATH),
            "ai_invocation_attempt_path": str(INV_PATH),
            "ai_request_envelope_path": str(REQ_PATH),
        },
        "request_summary": {
            "provider_target": (inv.get("request_summary") or {}).get("provider_target"),
            "model_name": (inv.get("request_summary") or {}).get("model_name"),
            "selected_ai_tier": (inv.get("request_summary") or {}).get("selected_ai_tier"),
            "route_plan": (inv.get("request_summary") or {}).get("route_plan"),
        },
        "governance_guards": {
            "system_mode": "read_only",
            "execution_state": "disabled",
            "execution_authority": "not_granted",
            "live_execution_allowed": False,
            "decision_lease_emitted": False,
            "operator_review_required": True,
        },
        "governed_observation": {
            "analysis_mode": parsed.get("analysis_mode"),
            "market_regime": parsed.get("market_regime"),
            "action_bias": parsed.get("action_bias"),
            "confidence_0_to_1": parsed.get("confidence_0_to_1"),
            "edge_assessment_bps": parsed.get("edge_assessment_bps"),
            "key_reasons": parsed.get("key_reasons"),
            "risk_notes": parsed.get("risk_notes"),
            "why_not_trade": parsed.get("why_not_trade"),
        },
        "decision_state": decision_state,
        "allow_progress_to_h1i_acceptance": allow_progress,
        "recommended_action": recommended_action,
        "operator_message": (
            "H1-H governed decision built. AI output has been normalized into a read-only governed observation, without granting execution authority."
            if overall_ok
            else "H1-H governed decision blocked because H1-G response validation is not yet satisfied."
        ),
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))
    save_latest_and_dated("bybit_ai_governed_decision", report)


if __name__ == "__main__":
    main()
