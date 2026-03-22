#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MODULE_NOTE / 模块说明:
- role / 角色:
  H1-E provider-native AI request envelope builder.
  H1-E 原生 provider 请求封装构建器。

- purpose / 目的:
  Build a normalized AI request envelope from:
  1) H1-D prompt prep output
  2) H1-R active route binding
  3) provider-native env policy

  基于以下输入生成统一的 AI 请求封装:
  1) H1-D prompt prep 输出
  2) H1-R 当前激活路由绑定
  3) provider-native 环境策略

- design / 设计原则:
  1) NO legacy H1E/H1F compatibility variables.
     不再依赖旧 H1E/H1F 兼容变量。
  2) Route binding is the single source of truth for active provider/model.
     当前激活 provider/model 以 route binding 为唯一真源。
  3) Output schema is provider-neutral but provider-native ready.
     输出结构本身对 provider 中立，但已可直接供原生 provider 调用层使用。
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List


RUNTIME_BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

THOUGHT_GATE_INPUT_PATH = RUNTIME_BASE / "bybit_thought_gate_input_latest.json"
THOUGHT_GATE_POLICY_PATH = RUNTIME_BASE / "bybit_thought_gate_policy_latest.json"
AI_PROMPT_PREP_PATH = RUNTIME_BASE / "bybit_ai_prompt_prep_latest.json"
AI_ROUTE_SELECTOR_PATH = RUNTIME_BASE / "bybit_ai_route_selector_latest.json"

OUTPUT_LATEST_PATH = RUNTIME_BASE / "bybit_ai_request_envelope_latest.json"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if raw == "":
        return default
    try:
        return int(raw)
    except Exception:
        return default


def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if raw == "":
        return default
    try:
        return float(raw)
    except Exception:
        return default


def build_idempotency_key(
    provider_target: str,
    model_name: str,
    selected_ai_tier: str,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """
    Deterministic idempotency key / 确定性幂等键
    """
    seed = "||".join(
        [
            provider_target,
            model_name,
            selected_ai_tier,
            system_prompt,
            user_prompt,
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
    return f"bybit-h1e-{digest}"


def dedup_list(items: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        if not item:
            continue
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def main() -> None:
    now_ms = int(time.time() * 1000)

    thought_gate_input = read_json(THOUGHT_GATE_INPUT_PATH)
    thought_gate_policy = read_json(THOUGHT_GATE_POLICY_PATH)
    ai_prompt_prep = read_json(AI_PROMPT_PREP_PATH)
    ai_route_selector = read_json(AI_ROUTE_SELECTOR_PATH)

    prep_summary = ai_prompt_prep.get("readiness_summary", {}) or {}
    prompt_budget = ai_prompt_prep.get("prompt_budget", {}) or {}
    prompt_payload = ai_prompt_prep.get("prompt_payload", {}) or {}

    route_decision = ai_route_selector.get("route_decision", {}) or {}

    selected_ai_tier = env_str(
        "BYBIT_AI_ACTIVE_SELECTED_AI_TIER",
        route_decision.get("selected_ai_tier", "skip"),
    )
    route_plan = env_str(
        "BYBIT_AI_ACTIVE_ROUTE_PLAN",
        route_decision.get("route_plan", "route_skip"),
    )
    route_reason = env_str(
        "BYBIT_AI_ACTIVE_ROUTE_REASON",
        route_decision.get("route_reason", "missing_route_reason"),
    )
    route_group = env_str(
        "BYBIT_AI_ACTIVE_ROUTE_GROUP",
        route_decision.get("env_binding_group", "ROUTE_SKIP"),
    )

    provider_target = env_str("BYBIT_AI_ACTIVE_PROVIDER_TARGET", "")
    model_name = env_str("BYBIT_AI_ACTIVE_MODEL", "")
    max_output_tokens = env_int("BYBIT_AI_ACTIVE_MAX_OUTPUT_TOKENS", 220)

    should_call_ai = bool(prep_summary.get("should_call_ai", False))
    require_json_response = bool(prompt_budget.get("require_json_response", True))
    response_deadline_ms_hint = int(prompt_budget.get("response_deadline_ms_hint", 1500))

    system_prompt = str(prompt_payload.get("system_prompt", ""))
    user_prompt = str(prompt_payload.get("user_prompt", ""))
    response_contract = prompt_payload.get("response_contract", {}) or {}

    blocking_reasons: List[str] = []
    warning_flags: List[str] = dedup_list(
        list(ai_prompt_prep.get("warning_flags", []) or [])
        + list(ai_route_selector.get("warning_flags", []) or [])
    )

    if not bool(prep_summary.get("allow_progress_to_h1d_prompt", False)):
        blocking_reasons.append("prompt_prep_not_ready")

    if not should_call_ai:
        blocking_reasons.append("should_call_ai_false")

    if provider_target not in {"anthropic_native", "openai_native"}:
        blocking_reasons.append("provider_target_missing_or_invalid")

    if not model_name:
        blocking_reasons.append("active_model_missing")

    if max_output_tokens <= 0:
        blocking_reasons.append("max_output_tokens_invalid")

    provider_runtime: Dict[str, Any] = {
        "provider_target": provider_target,
        "max_retries": env_int("BYBIT_AI_MAX_RETRIES", 0),
        "temperature": env_float("BYBIT_AI_TEMPERATURE", 0.1),
        "source_map": {},
    }

    if provider_target == "openai_native":
        provider_runtime.update(
            {
                "connect_timeout_sec": env_float("BYBIT_OPENAI_CONNECT_TIMEOUT_SEC", 1.0),
                "read_timeout_sec": env_float("BYBIT_OPENAI_READ_TIMEOUT_SEC", 5.0),
                "sdk_mode": "openai_sdk_responses_api",
                "source_map": {
                    "connect_timeout_sec": "env:BYBIT_OPENAI_CONNECT_TIMEOUT_SEC",
                    "read_timeout_sec": "env:BYBIT_OPENAI_READ_TIMEOUT_SEC",
                    "max_retries": "env:BYBIT_AI_MAX_RETRIES",
                    "temperature": "env:BYBIT_AI_TEMPERATURE",
                },
            }
        )
    elif provider_target == "anthropic_native":
        provider_runtime.update(
            {
                "connect_timeout_sec": env_float("BYBIT_ANTHROPIC_CONNECT_TIMEOUT_SEC", 1.0),
                "read_timeout_sec": env_float("BYBIT_ANTHROPIC_READ_TIMEOUT_SEC", 5.0),
                "sdk_mode": "anthropic_sdk_messages_api",
                "source_map": {
                    "connect_timeout_sec": "env:BYBIT_ANTHROPIC_CONNECT_TIMEOUT_SEC",
                    "read_timeout_sec": "env:BYBIT_ANTHROPIC_READ_TIMEOUT_SEC",
                    "max_retries": "env:BYBIT_AI_MAX_RETRIES",
                    "temperature": "env:BYBIT_AI_TEMPERATURE",
                },
            }
        )

    idempotency_key = build_idempotency_key(
        provider_target=provider_target,
        model_name=model_name,
        selected_ai_tier=selected_ai_tier,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )

    if blocking_reasons:
        request_state = "blocked_provider_native_request"
        allow_progress_to_h1f_invocation = False
        recommended_action = "resolve_request_blockers"
    else:
        request_state = "ready_provider_native_ai_request"
        allow_progress_to_h1f_invocation = True
        recommended_action = "may_progress_to_h1f_provider_native_invocation"

    payload: Dict[str, Any] = {
        "request_type": "bybit_ai_request_envelope",
        "request_version": "v2",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "H1-E",
        "report_ok": True,
        "source_refs": {
            "thought_gate_input_path": str(THOUGHT_GATE_INPUT_PATH),
            "thought_gate_policy_path": str(THOUGHT_GATE_POLICY_PATH),
            "ai_prompt_prep_path": str(AI_PROMPT_PREP_PATH),
            "ai_route_selector_path": str(AI_ROUTE_SELECTOR_PATH),
        },
        "source_integrity": {
            "thought_gate_input_present": THOUGHT_GATE_INPUT_PATH.exists(),
            "thought_gate_policy_present": THOUGHT_GATE_POLICY_PATH.exists(),
            "ai_prompt_prep_present": AI_PROMPT_PREP_PATH.exists(),
            "ai_route_selector_present": AI_ROUTE_SELECTOR_PATH.exists(),
            "source_errors": [],
        },
        "request_summary": {
            "prep_state": ai_prompt_prep.get("prep_state", "unknown"),
            "selected_ai_tier": selected_ai_tier,
            "should_call_ai": should_call_ai,
            "route_plan": route_plan,
            "route_reason": route_reason,
            "provider_target": provider_target,
            "model_name": model_name,
        },
        "provider_runtime": provider_runtime,
        "budget_context": {
            "ai_daily_budget_usd": (
                (thought_gate_input.get("policy_inputs", {}) or {}).get("ai_daily_budget_usd")
            ),
            "ai_per_call_budget_usd": (
                (thought_gate_input.get("policy_inputs", {}) or {}).get("ai_per_call_budget_usd")
            ),
            "max_output_tokens": max_output_tokens,
            "response_deadline_ms_hint": response_deadline_ms_hint,
        },
        "request_payload": {
            "provider_target": provider_target,
            "model_name": model_name,
            "selected_ai_tier": selected_ai_tier,
            "route_group": route_group,
            "route_plan": route_plan,
            "idempotency_key": idempotency_key,
            "max_output_tokens": max_output_tokens,
            "temperature": provider_runtime.get("temperature"),
            "require_json_response": require_json_response,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "response_contract": response_contract,
        },
        "warning_flags": warning_flags,
        "blocking_reasons": blocking_reasons,
        "request_state": request_state,
        "allow_progress_to_h1f_invocation": allow_progress_to_h1f_invocation,
        "recommended_action": recommended_action,
        "operator_message": (
            "H1-E provider-native request envelope built. "
            "This object binds active route -> provider target -> model -> provider runtime policy, "
            "without using legacy H1E/H1F compatibility variables."
        ),
    }

    write_json(OUTPUT_LATEST_PATH, payload)

    dated_path = OUTPUT_LATEST_PATH.with_name(
        f"bybit_ai_request_envelope_{now_ms}.json"
    )
    write_json(dated_path, payload)

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUTPUT_LATEST_PATH}")
    print(f"saved_dated={dated_path}")


if __name__ == "__main__":
    main()
