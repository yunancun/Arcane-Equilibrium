#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from pathlib import Path

from bybit_path_policy import get_thought_gate_runtime_dir

from bybit_h_stage_common import read_json_if_exists, unique_list, write_report
from bybit_mainline_cleanup_helpers import compute_usage_cost_usd, resolve_provider_pricing

BASE = get_thought_gate_runtime_dir()

H1_AUDIT_PATH = BASE / "bybit_thought_gate_final_audit_latest.json"
H2_RUNTIME_PATH = BASE / "bybit_query_budget_runtime_latest.json"
H4_AUDIT_PATH = BASE / "bybit_compute_governor_final_audit_latest.json"
REQ_PATH = BASE / "bybit_ai_request_envelope_latest.json"
INV_PATH = BASE / "bybit_ai_invocation_attempt_latest.json"

PREFIX = "bybit_ai_cost_log"


def main() -> None:
    now_ms = int(time.time() * 1000)

    h1 = read_json_if_exists(H1_AUDIT_PATH)
    h2 = read_json_if_exists(H2_RUNTIME_PATH)
    h4 = read_json_if_exists(H4_AUDIT_PATH)
    req = read_json_if_exists(REQ_PATH)
    inv = read_json_if_exists(INV_PATH)

    h1_summary = h1.get("audit_summary") or {}
    h2_runtime_summary = h2.get("runtime_summary") or {}
    h2_runtime_assessment = h2.get("runtime_assessment") or {}
    h4_summary = h4.get("audit_summary") or {}

    request_summary = req.get("request_summary") or {}
    request_payload = req.get("request_payload") or {}
    budget_context = req.get("budget_context") or {}

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

    ai_daily_budget_usd = budget_context.get("ai_daily_budget_usd")
    ai_per_call_budget_usd = budget_context.get("ai_per_call_budget_usd")
    max_output_tokens = request_payload.get("max_output_tokens") or budget_context.get("max_output_tokens")

    input_tokens = usage_summary.get("input_tokens")
    output_tokens = usage_summary.get("output_tokens")
    reasoning_tokens = output_tokens_details.get("reasoning_tokens")
    total_tokens = usage_summary.get("total_tokens")
    latency_ms = attempt_result.get("latency_ms")
    within_timeout_hint = h2_runtime_summary.get("within_timeout_hint")

    no_call_path_accepted = (
        should_call_ai is False
        or route_plan == "route_skip"
        or h2_runtime_assessment.get("no_call_path_accepted") is True
        or h4_summary.get("no_call_path_accepted") is True
    )

    pricing = resolve_provider_pricing(
        provider_target=request_summary.get("provider_target"),
        model_name=request_summary.get("model_name"),
        usage_summary=usage_summary,
    )
    pricing_table_bound = bool(pricing.get("pricing_table_bound"))
    actual_cost_usd = (
        compute_usage_cost_usd(usage_summary, pricing)
        if pricing_table_bound and usage_summary
        else None
    )
    governed_cost_ceiling_usd = ai_per_call_budget_usd

    warning_flags = unique_list(
        (h2.get("warning_flags") or [])
        + (["provider_pricing_table_not_bound_in_mainline"] if not pricing_table_bound else [])
    )

    blocking_reasons = []
    if h1_summary.get("runtime_still_protected") is not True:
        blocking_reasons.append("h1_runtime_not_protected")
    if h4_summary.get("h4_stage_closed") is not True:
        blocking_reasons.append("h4_not_closed")
    if ai_per_call_budget_usd is None:
        blocking_reasons.append("ai_per_call_budget_missing")
    if ai_daily_budget_usd is None:
        blocking_reasons.append("ai_daily_budget_missing")
    if provider_target is None:
        blocking_reasons.append("provider_target_missing")
    if model_name is None:
        blocking_reasons.append("model_name_missing")

    if not no_call_path_accepted:
        if attempt_result.get("invocation_attempted") is not True:
            blocking_reasons.append("invocation_not_attempted")
        if attempt_result.get("provider_response_present") is not True:
            blocking_reasons.append("provider_response_missing")
        if not isinstance(usage_summary, dict) or not usage_summary:
            blocking_reasons.append("usage_summary_missing")

    log_ok = not blocking_reasons

    cost_log = {
        "log_version": "v1",
        "provider_target": provider_target,
        "model_name": model_name,
        "selected_ai_tier": selected_ai_tier,
        "route_plan": route_plan,
        "should_call_ai": should_call_ai,
        "no_call_path_accepted": no_call_path_accepted,
        "usage_summary": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "total_tokens": total_tokens,
        },
        "performance_summary": {
            "latency_ms": latency_ms,
            "within_timeout_hint": within_timeout_hint,
        },
        "budget_summary": {
            "ai_daily_budget_usd": ai_daily_budget_usd,
            "ai_per_call_budget_usd": ai_per_call_budget_usd,
            "governed_cost_ceiling_usd": governed_cost_ceiling_usd,
            "max_output_tokens": max_output_tokens,
            "max_retries": transport_summary.get("max_retries"),
        },
        "cost_accounting_summary": {
            "actual_cost_usd": actual_cost_usd,
            "actual_cost_available": actual_cost_usd is not None,
            "pricing_table_bound": pricing_table_bound,
            "pricing_source": "mainline_bound_table" if pricing_table_bound else "not_bound_in_mainline",
            "budget_mode": "governed_budget_cap_only" if no_call_path_accepted else "governed_budget_cap_plus_usage",
            "usage_shape_within_contract": (
                True if no_call_path_accepted else
                (
                    isinstance(output_tokens, int)
                    and isinstance(max_output_tokens, int)
                    and output_tokens <= max_output_tokens
                )
            ),
        },
    }

    log_state = (
        "ai_cost_log_recorded_soft_warn"
        if log_ok and warning_flags else
        "ai_cost_log_recorded"
        if log_ok else
        "ai_cost_log_blocked"
    )

    report = {
        "log_type": "bybit_ai_cost_log",
        "log_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "H5-A",
        "log_ok": log_ok,
        "source_refs": {
            "thought_gate_final_audit_path": str(H1_AUDIT_PATH),
            "query_budget_runtime_path": str(H2_RUNTIME_PATH),
            "compute_governor_final_audit_path": str(H4_AUDIT_PATH),
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
        "cost_log": cost_log,
        "warning_flags": warning_flags,
        "blocking_reasons": blocking_reasons,
        "log_state": log_state,
        "allow_progress_to_h5b_governance_audit": log_ok,
        "recommended_action": (
            "may_progress_to_h5b_governance_audit"
            if log_ok else
            "inspect_h5a_cost_log_blockers"
        ),
        "operator_message": (
            "H5-A AI cost log recorded. 已记录 usage / latency / budget ceiling，且接受 legal no-call 终态。"
            if log_ok else
            "H5-A AI cost log blocked."
        ),
    }

    write_report(PREFIX, report)


if __name__ == "__main__":
    main()
