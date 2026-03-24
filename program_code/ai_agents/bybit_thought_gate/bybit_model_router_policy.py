#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from pathlib import Path

from bybit_path_policy import get_thought_gate_runtime_dir

from bybit_h_stage_common import read_json_if_exists, unique_list, write_report

BASE = get_thought_gate_runtime_dir()
REQ_PATH = BASE / "bybit_ai_request_envelope_latest.json"
BUDGET_RUNTIME_PATH = BASE / "bybit_query_budget_runtime_latest.json"

PREFIX = "bybit_model_router_policy"


def main() -> None:
    now_ms = int(time.time() * 1000)

    req = read_json_if_exists(REQ_PATH)
    budget_runtime = read_json_if_exists(BUDGET_RUNTIME_PATH)

    request_summary = req.get("request_summary") or {}
    request_payload = req.get("request_payload") or {}
    budget_context = req.get("budget_context") or {}
    budget_runtime_assessment = budget_runtime.get("runtime_assessment") or {}

    provider_target = request_summary.get("provider_target") or request_payload.get("provider_target")
    model_name = request_summary.get("model_name") or request_payload.get("model_name")
    selected_ai_tier = request_summary.get("selected_ai_tier") or request_payload.get("selected_ai_tier")
    route_plan = request_summary.get("route_plan") or request_payload.get("route_plan")
    should_call_ai = request_summary.get("should_call_ai")

    runtime_ok = budget_runtime.get("runtime_ok") is True
    no_call_path_expected = (
        should_call_ai is False
        or route_plan == "route_skip"
        or budget_runtime_assessment.get("no_call_path_accepted") is True
    )

    warning_flags = unique_list(
        (budget_runtime.get("warning_flags") or [])
        + (req.get("warning_flags") or [])
    )

    blocking_reasons = []
    if not provider_target:
        blocking_reasons.append("provider_target_missing")
    if not model_name:
        blocking_reasons.append("model_name_missing")
    if not selected_ai_tier:
        blocking_reasons.append("selected_ai_tier_missing")
    if not runtime_ok:
        blocking_reasons.append("h2_query_budget_runtime_not_ready")

    task_catalog = [
        {
            "task_class": "local_skip_no_ai",
            "preferred_route": "local_only",
            "description": "本地事实已足够，不应进入云端 AI 调用。",
        },
        {
            "task_class": "governed_ai_observation_json",
            "preferred_route": "cloud_compact_json",
            "description": "受治理的紧凑 JSON 观察输出，供只读判断链使用。",
        },
        {
            "task_class": "longform_research_review",
            "preferred_route": "cloud_long_context",
            "description": "长文本研究、审阅、复盘，不属于当前交易快照主链。",
        },
        {
            "task_class": "local_numeric_postcheck",
            "preferred_route": "local_only",
            "description": "contract / acceptance / audit / accounting 等数值与治理校验。",
        },
    ]

    if no_call_path_expected:
        current_task_profile = {
            "task_class": "local_skip_no_ai",
            "local_role": [
                "build_market_facts",
                "apply_thought_gate",
                "apply_query_budget",
                "local_route_resolution",
                "contract_check",
                "governed_observation_normalization",
            ],
            "cloud_role": [],
            "active_provider_target": provider_target,
            "active_model_name": model_name,
            "selected_ai_tier": selected_ai_tier,
            "route_plan": route_plan,
            "should_call_ai": should_call_ai,
            "no_call_path_expected": True,
            "route_mode": "local_only",
        }
    else:
        current_task_profile = {
            "task_class": "governed_ai_observation_json",
            "local_role": [
                "build_market_facts",
                "apply_thought_gate",
                "apply_query_budget",
                "enforce_json_contract",
                "governed_observation_normalization",
            ],
            "cloud_role": [
                "compact_market_observation_synthesis",
                "bounded_json_response_only",
            ],
            "active_provider_target": provider_target,
            "active_model_name": model_name,
            "selected_ai_tier": selected_ai_tier,
            "route_plan": route_plan,
            "should_call_ai": should_call_ai,
            "no_call_path_expected": False,
            "route_mode": "cloud_compact_json",
        }

    policy_ok = not blocking_reasons
    policy_state = "model_router_policy_snapshotted" if policy_ok else "model_router_policy_blocked"
    allow_progress = policy_ok

    report = {
        "policy_type": "bybit_model_router_policy",
        "policy_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "H3-A",
        "policy_ok": policy_ok,
        "source_refs": {
            "ai_request_envelope_path": str(REQ_PATH),
            "query_budget_runtime_path": str(BUDGET_RUNTIME_PATH),
        },
        "request_summary": {
            "provider_target": provider_target,
            "model_name": model_name,
            "selected_ai_tier": selected_ai_tier,
            "route_plan": route_plan,
            "should_call_ai": should_call_ai,
        },
        "budget_snapshot": {
            "ai_daily_budget_usd": budget_context.get("ai_daily_budget_usd"),
            "ai_per_call_budget_usd": budget_context.get("ai_per_call_budget_usd"),
            "max_output_tokens": budget_context.get("max_output_tokens"),
            "response_deadline_ms_hint": budget_context.get("response_deadline_ms_hint"),
            "runtime_ok": runtime_ok,
            "no_call_path_expected": no_call_path_expected,
        },
        "task_catalog": task_catalog,
        "current_task_profile": current_task_profile,
        "routing_principles": [
            "local_first_for_facts_and_gates",
            "local_skip_when_no_ai_required",
            "cloud_only_when_task_requires_bounded_model_judgment",
            "compact_json_for_governed_observation_path",
            "do_not_expand_to_longform_route_without_explicit_task_change",
        ],
        "warning_flags": warning_flags,
        "blocking_reasons": blocking_reasons,
        "policy_state": policy_state,
        "allow_progress_to_h3b_router_decision": allow_progress,
        "recommended_action": (
            "may_progress_to_h3b_router_decision"
            if allow_progress else
            "inspect_model_router_policy_blockers"
        ),
        "operator_message": (
            "H3-A model router policy snapshotted. 当前任务、当前路由边界与是否需要 AI 调用已经明确。"
            if allow_progress else
            "H3-A model router policy blocked. Resolve blockers before H3-B."
        ),
    }

    write_report(PREFIX, report)


if __name__ == "__main__":
    main()
