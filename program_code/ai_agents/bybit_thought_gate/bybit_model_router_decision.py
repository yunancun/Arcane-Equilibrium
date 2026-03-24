#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from pathlib import Path

from bybit_path_policy import get_thought_gate_runtime_dir

from bybit_h_stage_common import read_json_if_exists, unique_list, write_report

BASE = get_thought_gate_runtime_dir()
POLICY_PATH = BASE / "bybit_model_router_policy_latest.json"
REQ_PATH = BASE / "bybit_ai_request_envelope_latest.json"
INV_PATH = BASE / "bybit_ai_invocation_attempt_latest.json"
BUDGET_RUNTIME_PATH = BASE / "bybit_query_budget_runtime_latest.json"

PREFIX = "bybit_model_router_decision"


def main() -> None:
    now_ms = int(time.time() * 1000)

    policy = read_json_if_exists(POLICY_PATH)
    req = read_json_if_exists(REQ_PATH)
    inv = read_json_if_exists(INV_PATH)
    budget_runtime = read_json_if_exists(BUDGET_RUNTIME_PATH)

    request_summary = req.get("request_summary") or {}
    request_payload = req.get("request_payload") or {}
    inv_summary = inv.get("request_summary") or {}
    inv_attempt = inv.get("attempt_result") or {}
    current_task_profile = policy.get("current_task_profile") or {}
    budget_runtime_assessment = budget_runtime.get("runtime_assessment") or {}

    provider_target = request_summary.get("provider_target") or request_payload.get("provider_target")
    model_name = request_summary.get("model_name") or request_payload.get("model_name")
    selected_ai_tier = request_summary.get("selected_ai_tier") or request_payload.get("selected_ai_tier")
    route_plan = request_summary.get("route_plan") or request_payload.get("route_plan")
    should_call_ai = request_summary.get("should_call_ai")

    no_call_path_expected = (
        current_task_profile.get("no_call_path_expected") is True
        or budget_runtime_assessment.get("no_call_path_accepted") is True
        or should_call_ai is False
        or route_plan == "route_skip"
    )

    policy_ok = policy.get("policy_ok") is True
    runtime_ok = budget_runtime.get("runtime_ok") is True
    latest_parse_stable = inv_attempt.get("parsed_json_present") is True

    warning_flags = unique_list(
        (policy.get("warning_flags") or [])
        + (budget_runtime.get("warning_flags") or [])
        + (inv.get("warning_flags") or [])
    )

    blocking_reasons = []
    if not policy_ok:
        blocking_reasons.append("model_router_policy_not_ready")
    if not runtime_ok:
        blocking_reasons.append("query_budget_runtime_not_ready")
    if not provider_target:
        blocking_reasons.append("provider_target_missing")
    if not model_name:
        blocking_reasons.append("model_name_missing")

    if no_call_path_expected:
        route_reason_code = "local_skip_route_no_ai_required"
        route_reason_text = (
            "当前周期 should_call_ai=false / route_skip，因此模型路由保持本地处理，"
            "不进入云端 AI 调用。"
        )
        router_output = {
            "router_version": "v2",
            "task_class": "local_skip_no_ai",
            "route_mode": "local_only",
            "provider_target": provider_target,
            "model_name": model_name,
            "selected_ai_tier": selected_ai_tier,
            "route_reason_code": route_reason_code,
            "route_reason_text": route_reason_text,
            "why_this_route": [
                "当前周期已被上游判定为不需要 AI 调用。",
                "事实、预算、治理、contract、audit 继续由本地主链承担。",
                "local_only 路径更符合 no-call 终态。",
            ],
            "why_not_local_only": [],
            "why_not_longform_route": [
                "当前不是长文研究/复盘任务。",
                "当前不需要云端模型参与。",
            ],
            "local_owner": [
                "facts",
                "thought_gate",
                "query_budget",
                "contract_check",
                "governed_observation_normalization",
            ],
            "cloud_owner": [],
            "no_call_path_expected": True,
        }
    else:
        route_reason_code = "structured_json_budgeted_route"
        if latest_parse_stable:
            route_reason_text = (
                "当前任务属于 governed_ai_observation_json，且最近一次该 provider/model "
                "已成功给出可解析 JSON，因此继续沿用该有约束的紧凑路由。"
            )
        else:
            route_reason_text = (
                "当前任务属于 governed_ai_observation_json，预算链已准备好，"
                "因此继续走受治理的 compact JSON 路由，而不是退回长文本或无约束路径。"
            )
        router_output = {
            "router_version": "v2",
            "task_class": "governed_ai_observation_json",
            "route_mode": "cloud_compact_json",
            "provider_target": provider_target,
            "model_name": model_name,
            "selected_ai_tier": selected_ai_tier,
            "route_reason_code": route_reason_code,
            "route_reason_text": route_reason_text,
            "why_this_route": [
                "当前任务需要紧凑 JSON 观察结果，不需要长文研究输出。",
                "事实构建、gate、contract、audit 仍由本地负责，不应把本地主责外包给云模型。",
                f"当前 active route 已绑定到 {provider_target}/{model_name}。",
                "query_budget 已通过，因此本次路由在预算口径下可解释。",
            ],
            "why_not_local_only": [
                "当前仍需把压缩后的市场事实转成结构化观察 JSON。",
                "本地主链负责事实与治理，云端只负责受限观察表达，不等于执行许可。",
            ],
            "why_not_longform_route": [
                "当前不是长文研究/复盘任务。",
                "长上下文高成本路径不适合交易快照只读主链。",
            ],
            "local_owner": [
                "facts",
                "thought_gate",
                "query_budget",
                "contract_check",
                "governed_observation_normalization",
            ],
            "cloud_owner": [
                "compact_json_observation_only",
            ],
            "no_call_path_expected": False,
        }

    decision_ok = not blocking_reasons

    decision_state = (
        "model_router_v2_route_ready_soft_warn"
        if decision_ok and warning_flags else
        "model_router_v2_route_ready"
        if decision_ok else
        "model_router_v2_route_blocked"
    )

    report = {
        "decision_type": "bybit_model_router_decision",
        "decision_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "H3-B",
        "decision_ok": decision_ok,
        "source_refs": {
            "model_router_policy_path": str(POLICY_PATH),
            "ai_request_envelope_path": str(REQ_PATH),
            "ai_invocation_attempt_path": str(INV_PATH),
            "query_budget_runtime_path": str(BUDGET_RUNTIME_PATH),
        },
        "request_summary": {
            "provider_target": provider_target,
            "model_name": model_name,
            "selected_ai_tier": selected_ai_tier,
            "route_plan": route_plan,
            "should_call_ai": should_call_ai,
            "invocation_provider_target": inv_summary.get("provider_target"),
            "invocation_model_name": inv_summary.get("model_name"),
        },
        "router_output": router_output,
        "warning_flags": warning_flags,
        "blocking_reasons": blocking_reasons,
        "decision_state": decision_state,
        "allow_progress_to_h3c_router_runtime": decision_ok,
        "recommended_action": (
            "may_progress_to_h3c_router_runtime"
            if decision_ok else
            "inspect_model_router_decision_blockers"
        ),
        "operator_message": (
            "H3-B model router decision built. 当前任务、当前模型、路由原因已可解释。"
            if decision_ok else
            "H3-B model router decision blocked."
        ),
    }

    write_report(PREFIX, report)


if __name__ == "__main__":
    main()
