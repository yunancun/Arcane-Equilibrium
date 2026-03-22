from bybit_mainline_cleanup_helpers import compute_usage_cost_usd, resolve_provider_pricing
from bybit_h5_compat_helpers import h2_stage_closed, h4_stage_closed, h5_log_ok, h5_governance_audit_ok, extract_within_timeout_hint
from bybit_h5_main_postprocess import patch_ai_cost_log_report
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
H5-A / AI cost log

中文：
- 记录当前主链最近一次 provider-native AI 调用的 token / latency / budget 视角信息
- 注意：这里不伪造“真实美元成本”，只记录“治理上限”和可验证 usage
- 若主链没有绑定官方价格表，则 actual_cost_usd 保持为空，并给 soft warning

English:
- Record token / latency / budget-facing information for the latest provider-native AI call
- Do NOT invent actual dollar cost; only log governed ceilings and verifiable usage
- If the mainline does not bind an official pricing table, keep actual_cost_usd null
  and emit a soft warning
"""

import time
from pathlib import Path

from bybit_h_stage_common import read_json_if_exists, unique_list, write_report

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

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

    ai_daily_budget_usd = budget_context.get("ai_daily_budget_usd")
    ai_per_call_budget_usd = budget_context.get("ai_per_call_budget_usd")
    max_output_tokens = budget_context.get("max_output_tokens")

    input_tokens = usage_summary.get("input_tokens")
    output_tokens = usage_summary.get("output_tokens")
    reasoning_tokens = output_tokens_details.get("reasoning_tokens")
    total_tokens = usage_summary.get("total_tokens")
    latency_ms = attempt_result.get("latency_ms")
    h2_runtime = locals().get("h2_runtime") or {}
    h2_observed_last_call = h2_runtime.get("observed_last_call") or {}
    within_timeout_hint = h2_runtime_summary.get("within_timeout_hint")
    if within_timeout_hint is None:
        within_timeout_hint = h2_observed_last_call.get("within_timeout_hint")

    pricing = resolve_provider_pricing(
        provider_target=request_summary.get("provider_target"),
        model_name=request_summary.get("model_name"),
        usage_summary=usage_summary,
    )
    pricing_table_bound = bool(pricing.get("pricing_table_bound"))
    actual_cost_usd = compute_usage_cost_usd(usage_summary, pricing) if pricing_table_bound else None
    governed_cost_ceiling_usd = ai_per_call_budget_usd

    warning_flags = unique_list(
        (h2.get("warning_flags") or [])
        + (inv.get("warning_flags") or [])
        + (["provider_pricing_table_not_bound_in_mainline"] if not pricing_table_bound else [])
    )

    blocking_reasons = []
    if h1_summary.get("runtime_still_protected") is not True:
        blocking_reasons.append("h1_runtime_not_protected")
    if h4_summary.get("h4_stage_closed") is not True:
        blocking_reasons.append("h4_not_closed")
    if attempt_result.get("invocation_attempted") is not True:
        blocking_reasons.append("invocation_not_attempted")
    if attempt_result.get("provider_response_present") is not True:
        blocking_reasons.append("provider_response_missing")
    if not isinstance(usage_summary, dict) or not usage_summary:
        blocking_reasons.append("usage_summary_missing")
    if ai_per_call_budget_usd is None:
        blocking_reasons.append("ai_per_call_budget_missing")
    if ai_daily_budget_usd is None:
        blocking_reasons.append("ai_daily_budget_missing")
    if provider_target is None:
        blocking_reasons.append("provider_target_missing")
    if model_name is None:
        blocking_reasons.append("model_name_missing")

    log_ok = not blocking_reasons

    cost_log = {
        "log_version": "v1",
        "provider_target": provider_target,
        "model_name": model_name,
        "selected_ai_tier": selected_ai_tier,
        "route_plan": route_plan,
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
            "actual_cost_available": False,
            "pricing_table_bound": pricing_table_bound,
            "pricing_source": "not_bound_in_mainline",
            "budget_mode": "governed_budget_cap_only",
            "usage_shape_within_contract": (
                isinstance(output_tokens, int)
                and isinstance(max_output_tokens, int)
                and output_tokens <= max_output_tokens
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

    # H5_SCHEMA_DRIFT_COMPAT_V7

    _authoritative_h4_closed = h4_stage_closed()

    _authoritative_within_timeout_hint = extract_within_timeout_hint()


    if _authoritative_within_timeout_hint is not None:

        within_timeout_hint = _authoritative_within_timeout_hint


    warning_flags = list(dict.fromkeys(list(warning_flags or [])))

    blocking_reasons = list(dict.fromkeys(list(blocking_reasons or [])))


    blocking_reasons = [x for x in blocking_reasons if x != "h4_not_closed"]

    if not _authoritative_h4_closed:

        blocking_reasons.append("h4_not_closed")


    if blocking_reasons:

        log_state = "ai_cost_log_blocked"

        log_ok = False

    else:

        log_state = "ai_cost_log_recorded_soft_warn" if warning_flags else "ai_cost_log_recorded"

        log_ok = True


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
            "H5-A AI cost log recorded. 已记录 usage / latency / budget ceiling，未伪造真实美元成本。"
            if log_ok else
            "H5-A AI cost log blocked."
        ),
    }

    write_report(PREFIX, report)


if __name__ == "__main__":
    main()
