#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from pathlib import Path

from bybit_path_policy import get_thought_gate_runtime_dir

from bybit_h_stage_common import read_json_if_exists, unique_list, write_report

BASE = get_thought_gate_runtime_dir()

H1_AUDIT_PATH = BASE / "bybit_thought_gate_final_audit_latest.json"
H2_RUNTIME_PATH = BASE / "bybit_query_budget_runtime_latest.json"
H3_AUDIT_PATH = BASE / "bybit_model_router_final_audit_latest.json"
REQ_PATH = BASE / "bybit_ai_request_envelope_latest.json"
INV_PATH = BASE / "bybit_ai_invocation_attempt_latest.json"

PREFIX = "bybit_compute_governor_policy"


def main() -> None:
    now_ms = int(time.time() * 1000)

    h1 = read_json_if_exists(H1_AUDIT_PATH)
    h2 = read_json_if_exists(H2_RUNTIME_PATH)
    h3 = read_json_if_exists(H3_AUDIT_PATH)
    req = read_json_if_exists(REQ_PATH)
    inv = read_json_if_exists(INV_PATH)

    h1_summary = h1.get("audit_summary") or {}
    h2_runtime_summary = h2.get("runtime_summary") or {}
    h2_runtime_assessment = h2.get("runtime_assessment") or {}
    h3_summary = h3.get("audit_summary") or {}

    request_summary = req.get("request_summary") or {}
    request_payload = req.get("request_payload") or {}
    budget_context = req.get("budget_context") or {}
    provider_runtime = req.get("provider_runtime") or {}

    transport_summary = inv.get("transport_summary") or {}
    attempt_result = inv.get("attempt_result") or {}
    response_extract = inv.get("response_extract") or {}
    usage_summary = response_extract.get("usage_summary") or {}
    output_tokens_details = usage_summary.get("output_tokens_details") or {}

    provider_target = request_summary.get("provider_target") or request_payload.get("provider_target")
    model_name = request_summary.get("model_name") or request_payload.get("model_name")
    selected_ai_tier = request_summary.get("selected_ai_tier") or request_payload.get("selected_ai_tier")
    route_plan = request_summary.get("route_plan") or request_payload.get("route_plan")
    should_call_ai = request_summary.get("should_call_ai")

    max_output_tokens = request_payload.get("max_output_tokens") or budget_context.get("max_output_tokens")
    max_retries = provider_runtime.get("max_retries")
    if max_retries is None:
        max_retries = transport_summary.get("max_retries")

    latency_ms = attempt_result.get("latency_ms")
    within_timeout_hint = h2_runtime_summary.get("within_timeout_hint")
    reasoning_tokens = output_tokens_details.get("reasoning_tokens")

    no_call_path_expected = (
        should_call_ai is False
        or route_plan == "route_skip"
        or h2_runtime_assessment.get("no_call_path_accepted") is True
        or h3_summary.get("no_call_path_accepted") is True
    )

    warning_flags = unique_list(
        (h2.get("warning_flags") or [])
        + (h3.get("warning_flags") or [])
        + (inv.get("warning_flags") or [])
    )

    blocking_reasons = []
    if h1_summary.get("runtime_still_protected") is not True:
        blocking_reasons.append("h1_runtime_not_protected")
    if h2.get("runtime_ok") is not True:
        blocking_reasons.append("h2_query_budget_runtime_not_ready")
    if h3_summary.get("h3_stage_closed") is not True:
        blocking_reasons.append("h3_model_router_not_closed")
    if not provider_target:
        blocking_reasons.append("provider_target_missing")
    if not model_name:
        blocking_reasons.append("model_name_missing")
    if max_output_tokens is None:
        blocking_reasons.append("max_output_tokens_missing")
    if max_retries is None:
        blocking_reasons.append("max_retries_missing")

    policy_ok = not blocking_reasons

    governor_policy = {
        "governor_version": "v1",
        "task_scope": "governed_read_only_ai_observation",
        "active_provider_target": provider_target,
        "active_model_name": model_name,
        "selected_ai_tier": selected_ai_tier,
        "route_plan": route_plan,
        "should_call_ai": should_call_ai,
        "no_call_path_expected": no_call_path_expected,
        "hard_constraints": {
            "system_must_remain_read_only": True,
            "execution_authority_must_not_be_granted": True,
            "decision_lease_must_not_be_emitted": True,
            "max_retries_must_equal_zero": True,
            "single_compact_request_path_only": True,
            "no_longform_escalation_in_mainline": True,
            "allow_legal_no_call_terminal": True,
        },
        "soft_constraints": {
            "prefer_reasoning_tokens_zero_when_supported": True,
            "prefer_low_latency": True,
            "prefer_compact_json_only": True,
        },
        "budget_constraints": {
            "max_output_tokens_cap": max_output_tokens,
            "max_retries_cap": 0,
            "ai_daily_budget_usd": budget_context.get("ai_daily_budget_usd"),
            "ai_per_call_budget_usd": budget_context.get("ai_per_call_budget_usd"),
            "response_deadline_ms_hint": budget_context.get("response_deadline_ms_hint"),
        },
        "latest_observation": {
            "latency_ms": latency_ms,
            "within_timeout_hint": within_timeout_hint,
            "reasoning_tokens": reasoning_tokens,
            "input_tokens": usage_summary.get("input_tokens"),
            "output_tokens": usage_summary.get("output_tokens"),
            "total_tokens": usage_summary.get("total_tokens"),
            "provider_response_present": attempt_result.get("provider_response_present"),
            "response_text_present": attempt_result.get("response_text_present"),
            "parsed_json_present": attempt_result.get("parsed_json_present"),
        },
        "anti_abuse_dimensions": [
            "no_retry_storm",
            "no_unbounded_output_expansion",
            "no_route_escalation_without_explicit_stage_change",
            "no_execution_permission_upgrade",
            "no_compute_burst_outside_budget_chain",
        ],
    }

    policy_state = (
        "compute_governor_policy_snapshotted_soft_warn"
        if policy_ok and warning_flags else
        "compute_governor_policy_snapshotted"
        if policy_ok else
        "compute_governor_policy_blocked"
    )

    allow_progress = policy_ok

    report = {
        "policy_type": "bybit_compute_governor_policy",
        "policy_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "H4-A",
        "policy_ok": policy_ok,
        "source_refs": {
            "thought_gate_final_audit_path": str(H1_AUDIT_PATH),
            "query_budget_runtime_path": str(H2_RUNTIME_PATH),
            "model_router_final_audit_path": str(H3_AUDIT_PATH),
            "ai_request_envelope_path": str(REQ_PATH),
            "ai_invocation_attempt_path": str(INV_PATH),
        },
        "request_summary": {
            "provider_target": provider_target,
            "model_name": model_name,
            "selected_ai_tier": selected_ai_tier,
            "route_plan": route_plan,
            "should_call_ai": should_call_ai,
        },
        "governor_policy": governor_policy,
        "warning_flags": warning_flags,
        "blocking_reasons": blocking_reasons,
        "policy_state": policy_state,
        "allow_progress_to_h4b_governor_gate": allow_progress,
        "recommended_action": (
            "may_progress_to_h4b_governor_gate"
            if allow_progress else
            "inspect_compute_governor_policy_blockers"
        ),
        "operator_message": (
            "H4-A compute governor policy snapshotted. 已明确只读保护、anti-abuse 约束与 no-call 合法终态。"
            if allow_progress else
            "H4-A compute governor policy blocked."
        ),
    }

    write_report(PREFIX, report)


if __name__ == "__main__":
    main()
