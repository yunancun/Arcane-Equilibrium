#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Dict, List

from bybit_h1_report_utils import (
    THOUGHT_GATE_DIR,
    make_check,
    preview_text,
    read_json,
    save_latest_and_dated,
    try_parse_json_object,
)

INV_PATH = THOUGHT_GATE_DIR / "bybit_ai_invocation_attempt_latest.json"

REQUIRED_FIELDS = [
    "analysis_mode",
    "market_regime",
    "action_bias",
    "confidence_0_to_1",
    "edge_assessment_bps",
    "key_reasons",
    "risk_notes",
    "why_not_trade",
]


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def main() -> None:
    now_ms = int(time.time() * 1000)
    inv = read_json(INV_PATH, {})
    response_extract = inv.get("response_extract") or {}
    request_summary = inv.get("request_summary") or {}
    transport_summary = inv.get("transport_summary") or {}
    attempt_result = inv.get("attempt_result") or {}

    parsed_json = response_extract.get("parsed_json_object")
    if not isinstance(parsed_json, dict):
        parsed_json = try_parse_json_object(response_extract.get("ai_response_text"))

    response_contract = response_extract.get("response_contract") or {}
    constraints = response_contract.get("constraints") or {}

    max_key_reasons = int(constraints.get("max_key_reasons", 5))
    max_risk_notes = int(constraints.get("max_risk_notes", 5))
    max_why_not_trade = int(constraints.get("max_why_not_trade", 5))
    allowed_bias = constraints.get("action_bias_allowed") or ["long_bias", "short_bias", "flat_bias"]

    should_call_ai = request_summary.get("should_call_ai") is True
    route_plan = request_summary.get("route_plan")
    selected_ai_tier = request_summary.get("selected_ai_tier")
    provider_target = transport_summary.get("provider_target")
    invocation_state = inv.get("invocation_state")

    invocation_attempted = attempt_result.get("invocation_attempted") is True
    provider_response_present = attempt_result.get("provider_response_present") is True
    parsed_json_present = isinstance(parsed_json, dict)

    checks: List[Dict[str, Any]] = []
    hard_errors: List[str] = []
    semantic_flags: List[str] = []
    terminal_mode: str | None = None

    checks.append(make_check("invocation_exists", bool(inv), str(INV_PATH)))
    checks.append(make_check("invocation_version_v2", inv.get("invocation_version") == "v2", inv.get("invocation_version")))

    if should_call_ai:
        terminal_mode = "provider_json_ready"
        semantic_flags.append("ai_call_expected_path")
        checks.append(
            make_check(
                "provider_target_known",
                provider_target in {"openai_native", "anthropic_native"},
                provider_target,
            )
        )
        checks.append(make_check("invocation_attempted_true", invocation_attempted, invocation_attempted))
        checks.append(make_check("provider_response_present_true", provider_response_present, provider_response_present))
        checks.append(make_check("parsed_json_dict", parsed_json_present, type(parsed_json).__name__ if parsed_json is not None else None))

        if not invocation_attempted:
            hard_errors.append("ai_call_required_but_invocation_not_attempted")
        if invocation_attempted and not provider_response_present:
            hard_errors.append("ai_call_attempted_but_provider_response_missing")
        if provider_response_present and not parsed_json_present:
            hard_errors.append("provider_response_present_but_json_not_ready")

        if isinstance(parsed_json, dict):
            for f in REQUIRED_FIELDS:
                checks.append(make_check(f"field_present_{f}", f in parsed_json, parsed_json.get(f)))

            checks.append(make_check("analysis_mode_observation_only", parsed_json.get("analysis_mode") == "observation_only", parsed_json.get("analysis_mode")))
            checks.append(make_check("action_bias_allowed", parsed_json.get("action_bias") in allowed_bias, parsed_json.get("action_bias")))
            checks.append(make_check("confidence_numeric", _is_number(parsed_json.get("confidence_0_to_1")), parsed_json.get("confidence_0_to_1")))
            checks.append(make_check("edge_assessment_numeric", _is_number(parsed_json.get("edge_assessment_bps")), parsed_json.get("edge_assessment_bps")))
            checks.append(make_check("key_reasons_list", isinstance(parsed_json.get("key_reasons"), list), type(parsed_json.get("key_reasons")).__name__))
            checks.append(make_check("risk_notes_list", isinstance(parsed_json.get("risk_notes"), list), type(parsed_json.get("risk_notes")).__name__))
            checks.append(make_check("why_not_trade_list", isinstance(parsed_json.get("why_not_trade"), list), type(parsed_json.get("why_not_trade")).__name__))

            if isinstance(parsed_json.get("key_reasons"), list):
                checks.append(make_check("key_reasons_len_ok", len(parsed_json["key_reasons"]) <= max_key_reasons, len(parsed_json["key_reasons"])))
            if isinstance(parsed_json.get("risk_notes"), list):
                checks.append(make_check("risk_notes_len_ok", len(parsed_json["risk_notes"]) <= max_risk_notes, len(parsed_json["risk_notes"])))
            if isinstance(parsed_json.get("why_not_trade"), list):
                checks.append(make_check("why_not_trade_len_ok", len(parsed_json["why_not_trade"]) <= max_why_not_trade, len(parsed_json["why_not_trade"])))
    else:
        terminal_mode = "legal_no_ai_call"
        semantic_flags.append("legal_no_ai_call_path")
        checks.append(make_check("should_call_ai_false", True, should_call_ai))
        checks.append(make_check("invocation_not_attempted", not invocation_attempted, invocation_attempted))
        checks.append(make_check("provider_response_absent", not provider_response_present, provider_response_present))
        checks.append(make_check("parsed_json_absent", not parsed_json_present, parsed_json_present))

        if invocation_attempted:
            hard_errors.append("unexpected_invocation_when_no_ai_call_expected")
        if provider_response_present:
            hard_errors.append("unexpected_provider_response_when_no_ai_call_expected")
        if parsed_json_present:
            hard_errors.append("unexpected_parsed_json_when_no_ai_call_expected")

    overall_ok = all(c["ok"] for c in checks) and not hard_errors
    failed_checks = [c["name"] for c in checks if not c["ok"]]
    failed_count = len(failed_checks) + len(hard_errors)

    if terminal_mode == "legal_no_ai_call":
        response_state = "legal_no_ai_call_terminal" if overall_ok else "illegal_no_ai_call_state"
    else:
        response_state = "response_json_contract_satisfied" if overall_ok else "response_invalid_or_incomplete"

    report = {
        "report_type": "bybit_ai_response_check",
        "report_version": "v2",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "H1-G",
        "overall_ok": overall_ok,
        "failed_count": failed_count,
        "terminal_mode": terminal_mode,
        "route_plan": route_plan,
        "selected_ai_tier": selected_ai_tier,
        "should_call_ai": should_call_ai,
        "invocation_attempted": invocation_attempted,
        "provider_response_present": provider_response_present,
        "parsed_json_present": parsed_json_present,
        "source_refs": {
            "ai_invocation_attempt_path": str(INV_PATH),
        },
        "request_summary": {
            "selected_ai_tier": selected_ai_tier,
            "provider_target": request_summary.get("provider_target"),
            "model_name": request_summary.get("model_name"),
            "route_plan": route_plan,
            "should_call_ai": should_call_ai,
            "invocation_state": invocation_state,
        },
        "response_summary": {
            "response_text_present": attempt_result.get("response_text_present"),
            "parsed_json_present": parsed_json_present,
            "raw_response_preview": preview_text(response_extract.get("ai_response_text")),
        },
        "parsed_json_object": parsed_json,
        "response_contract": response_contract,
        "checks": checks,
        "failed_checks": failed_checks,
        "hard_errors": hard_errors,
        "semantic_flags": semantic_flags,
        "response_state": response_state,
        "allow_progress_to_h1h_governed_decision": overall_ok,
        "recommended_action": (
            "may_progress_to_h1h_governed_decision"
            if overall_ok
            else "inspect_ai_response_failure"
        ),
        "operator_message": (
            "H1-G accepted legal no-call terminal path. No provider-native response was required for this cycle."
            if overall_ok and terminal_mode == "legal_no_ai_call"
            else (
                "H1-G AI response check complete. Parsed JSON was validated against the contract and constrained into observation-only semantics."
                if overall_ok
                else "H1-G AI response check failed. Inspect failed_checks and hard_errors before progressing."
            )
        ),
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))
    save_latest_and_dated("bybit_ai_response_check", report)


if __name__ == "__main__":
    main()
