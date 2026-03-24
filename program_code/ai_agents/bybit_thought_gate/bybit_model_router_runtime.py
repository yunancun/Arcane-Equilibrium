#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from pathlib import Path

from bybit_path_policy import get_thought_gate_runtime_dir

from bybit_h_stage_common import read_json_if_exists, unique_list, write_report

BASE = get_thought_gate_runtime_dir()
DECISION_PATH = BASE / "bybit_model_router_decision_latest.json"
INV_PATH = BASE / "bybit_ai_invocation_attempt_latest.json"
RESP_CHECK_PATH = BASE / "bybit_ai_response_check_latest.json"
BUDGET_RUNTIME_PATH = BASE / "bybit_query_budget_runtime_latest.json"

PREFIX = "bybit_model_router_runtime"


def main() -> None:
    now_ms = int(time.time() * 1000)

    decision = read_json_if_exists(DECISION_PATH)
    inv = read_json_if_exists(INV_PATH)
    resp_check = read_json_if_exists(RESP_CHECK_PATH)
    budget_runtime = read_json_if_exists(BUDGET_RUNTIME_PATH)

    router_output = decision.get("router_output") or {}
    decision_request_summary = decision.get("request_summary") or {}
    inv_summary = inv.get("request_summary") or {}
    inv_attempt = inv.get("attempt_result") or {}
    inv_extract = inv.get("response_extract") or {}
    usage_summary = inv_extract.get("usage_summary") or {}
    budget_summary = budget_runtime.get("runtime_summary") or {}

    decision_ok = decision.get("decision_ok") is True
    response_check_ok = resp_check.get("overall_ok") is True

    provider_target = router_output.get("provider_target")
    model_name = router_output.get("model_name")
    inv_provider_target = inv_summary.get("provider_target")
    inv_model_name = inv_summary.get("model_name")

    provider_match = provider_target == inv_provider_target
    model_match = model_name == inv_model_name
    response_text_present = inv_attempt.get("response_text_present") is True
    parsed_json_present = inv_attempt.get("parsed_json_present") is True

    no_call_path_accepted = (
        router_output.get("no_call_path_expected") is True
        or router_output.get("route_mode") == "local_only"
        or decision_request_summary.get("should_call_ai") is False
        or resp_check.get("terminal_mode") == "legal_no_ai_call"
    )

    warning_flags = unique_list(
        (decision.get("warning_flags") or [])
        + (budget_runtime.get("warning_flags") or [])
        + (resp_check.get("failed_checks") or [])
        + (inv.get("warning_flags") or [])
    )

    blocking_reasons = []
    if not decision_ok:
        blocking_reasons.append("model_router_decision_not_ready")
    if not provider_match:
        blocking_reasons.append("provider_target_mismatch_vs_invocation")
    if not model_match:
        blocking_reasons.append("model_name_mismatch_vs_invocation")
    if not response_check_ok:
        blocking_reasons.append("ai_response_check_not_ready")
    if not no_call_path_accepted:
        if not response_text_present:
            blocking_reasons.append("response_text_missing")
        if not parsed_json_present:
            blocking_reasons.append("parsed_json_missing")

    runtime_ok = not blocking_reasons

    runtime_state = (
        "model_router_runtime_ready_soft_warn"
        if runtime_ok and warning_flags else
        "model_router_runtime_ready"
        if runtime_ok else
        "model_router_runtime_blocked"
    )

    report = {
        "runtime_type": "bybit_model_router_runtime",
        "runtime_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "H3-C",
        "runtime_ok": runtime_ok,
        "source_refs": {
            "model_router_decision_path": str(DECISION_PATH),
            "ai_invocation_attempt_path": str(INV_PATH),
            "ai_response_check_path": str(RESP_CHECK_PATH),
            "query_budget_runtime_path": str(BUDGET_RUNTIME_PATH),
        },
        "request_summary": {
            "provider_target": provider_target,
            "model_name": model_name,
            "selected_ai_tier": router_output.get("selected_ai_tier"),
            "route_mode": router_output.get("route_mode"),
            "should_call_ai": decision_request_summary.get("should_call_ai"),
        },
        "runtime_summary": {
            "provider_target_match": provider_match,
            "model_name_match": model_match,
            "response_check_ok": response_check_ok,
            "invocation_state": inv.get("invocation_state"),
            "latency_ms": inv_attempt.get("latency_ms"),
            "within_timeout_hint": budget_summary.get("within_timeout_hint"),
            "input_tokens": usage_summary.get("input_tokens"),
            "output_tokens": usage_summary.get("output_tokens"),
            "reasoning_tokens": (usage_summary.get("output_tokens_details") or {}).get("reasoning_tokens"),
            "total_tokens": usage_summary.get("total_tokens"),
            "no_call_path_accepted": no_call_path_accepted,
        },
        "route_explainability": {
            "route_reason_code": router_output.get("route_reason_code"),
            "route_reason_text": router_output.get("route_reason_text"),
            "local_owner": router_output.get("local_owner"),
            "cloud_owner": router_output.get("cloud_owner"),
            "no_call_path_expected": router_output.get("no_call_path_expected"),
        },
        "warning_flags": warning_flags,
        "blocking_reasons": blocking_reasons,
        "runtime_state": runtime_state,
        "allow_progress_to_h3d_final_audit": runtime_ok,
        "recommended_action": (
            "may_progress_to_h3d_final_audit"
            if runtime_ok else
            "inspect_model_router_runtime_blockers"
        ),
        "operator_message": (
            "H3-C model router runtime ready. 路由决策与当前 no-call / invocation 语义已对齐。"
            if runtime_ok else
            "H3-C model router runtime blocked."
        ),
    }

    write_report(PREFIX, report)


if __name__ == "__main__":
    main()
