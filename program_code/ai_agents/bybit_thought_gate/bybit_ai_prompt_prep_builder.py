#!/usr/bin/env python3
"""
MODULE_NOTE / 模块说明:
- role / 角色:
  H1-D AI prompt preparation builder / H1-D AI 提示词准备构建器。

- purpose / 目的:
  Consume H1-A input, H1-B policy, H1-C decision, and H2 local trigger model,
  then build one compact, auditable AI prompt preparation object.
  消费 H1-A 输入、H1-B policy、H1-C decision、以及 H2 本地触发模型，
  构建一个紧凑、可审计的 AI prompt 准备对象。

- upstream / 上游输入:
  1) runtime/bybit/thought_gate/bybit_thought_gate_input_latest.json
  2) runtime/bybit/thought_gate/bybit_thought_gate_policy_latest.json
  3) runtime/bybit/thought_gate/bybit_thought_gate_decision_latest.json
  4) runtime/bybit/trigger_model/bybit_local_trigger_model_latest.json

- output / 输出:
  runtime/bybit/thought_gate/bybit_ai_prompt_prep_latest.json

- notes / 备注:
  1) This module does NOT call AI.
     本模块不会真正调用 AI。
  2) This module does NOT authorize trading.
     本模块不会授权交易。
  3) This module only prepares the minimum necessary prompt package so that the
     next layer can invoke AI in a bounded, low-cost, latency-aware manner.
     本模块只负责准备“最小必要”的 prompt 包，以便下一层能以受控、低成本、
     考虑延迟的方式调用 AI。
  4) v1 is intentionally compact and conservative.
     v1 故意保持紧凑且保守。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from bybit_path_policy import get_thought_gate_runtime_dir
from typing import Any


# ---------------------------------------------------------------------------
# Path constants / 路径常量
# ---------------------------------------------------------------------------

THOUGHT_GATE_DIR = Path(
    str(get_thought_gate_runtime_dir())
)
TRIGGER_DIR = Path(
    os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/trigger_model"
)

INPUT_PATH = THOUGHT_GATE_DIR / "bybit_thought_gate_input_latest.json"
POLICY_PATH = THOUGHT_GATE_DIR / "bybit_thought_gate_policy_latest.json"
DECISION_PATH = THOUGHT_GATE_DIR / "bybit_thought_gate_decision_latest.json"
TRIGGER_PATH = TRIGGER_DIR / "bybit_local_trigger_model_latest.json"

LATEST_OUTPUT_PATH = THOUGHT_GATE_DIR / "bybit_ai_prompt_prep_latest.json"


# ---------------------------------------------------------------------------
# Env knobs / 环境变量参数
# These control how big and expensive the prompt package is allowed to be.
# 这些参数控制 prompt 包允许有多大、多贵。
# ---------------------------------------------------------------------------

LIGHT_MAX_PROMPT_CHARS_ENV = "BYBIT_H1D_LIGHT_MAX_PROMPT_CHARS"
STANDARD_MAX_PROMPT_CHARS_ENV = "BYBIT_H1D_STANDARD_MAX_PROMPT_CHARS"
LIGHT_MAX_FACTS_ENV = "BYBIT_H1D_LIGHT_MAX_FACTS"
STANDARD_MAX_FACTS_ENV = "BYBIT_H1D_STANDARD_MAX_FACTS"
LIGHT_MAX_OUTPUT_TOKENS_HINT_ENV = "BYBIT_H1D_LIGHT_MAX_OUTPUT_TOKENS_HINT"
STANDARD_MAX_OUTPUT_TOKENS_HINT_ENV = "BYBIT_H1D_STANDARD_MAX_OUTPUT_TOKENS_HINT"
REQUIRE_JSON_RESPONSE_ENV = "BYBIT_H1D_REQUIRE_JSON_RESPONSE"

DEFAULT_LIGHT_MAX_PROMPT_CHARS = 4200
DEFAULT_STANDARD_MAX_PROMPT_CHARS = 9000
DEFAULT_LIGHT_MAX_FACTS = 18
DEFAULT_STANDARD_MAX_FACTS = 36
DEFAULT_LIGHT_MAX_OUTPUT_TOKENS_HINT = 220
DEFAULT_STANDARD_MAX_OUTPUT_TOKENS_HINT = 500
DEFAULT_REQUIRE_JSON_RESPONSE = True

ALLOWED_DECISION_STATES = {
    "decision_blocked",
    "decision_skip_no_local_trigger_model",
    "decision_skip_trigger_model_not_fired",
    "decision_ready_light_ai_call",
    "decision_ready_standard_ai_call",
}

ALLOWED_PREP_STATES = {
    "blocked_not_ready_for_prompt_prep",
    "ready_light_prompt_prep",
    "ready_standard_prompt_prep",
}

ALLOWED_AI_TIERS = {
    "none",
    "light",
    "standard",
}


# ---------------------------------------------------------------------------
# Helper functions / 辅助函数
# ---------------------------------------------------------------------------

def load_json(path: Path) -> tuple[dict[str, Any], bool, str | None]:
    """
    Load JSON from disk.
    从磁盘读取 JSON。
    """
    if not path.exists():
        return {}, False, f"missing_file:{path}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), True, None
    except Exception as exc:  # pragma: no cover
        return {}, False, f"json_load_error:{path}:{exc}"


def save_report(report: dict[str, Any]) -> tuple[Path, Path]:
    """
    Save latest and dated reports.
    保存 latest 与按时间戳归档的报告。
    """
    THOUGHT_GATE_DIR.mkdir(parents=True, exist_ok=True)
    latest_path = LATEST_OUTPUT_PATH
    dated_path = THOUGHT_GATE_DIR / f"bybit_ai_prompt_prep_{report['ts_ms']}.json"
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    latest_path.write_text(serialized, encoding="utf-8")
    dated_path.write_text(serialized, encoding="utf-8")
    return latest_path, dated_path


def parse_int_env(name: str, default: int) -> int:
    """
    Parse integer environment variable with fallback.
    解析整数环境变量，失败时回退默认值。
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        return default


def parse_bool_env(name: str, default: bool) -> bool:
    """
    Parse boolean environment variable with fallback.
    解析布尔环境变量，失败时回退默认值。
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def unique_preserve_order(items: list[str]) -> list[str]:
    """
    Deduplicate while preserving order.
    去重但保持原始顺序。
    """
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def clip_text(text: str, max_chars: int) -> str:
    """
    Clip text to a maximum character count.
    将文本裁剪到最大字符数以内。
    """
    if len(text) <= max_chars:
        return text
    suffix = "\n...[truncated_for_budget]"
    keep = max(0, max_chars - len(suffix))
    return text[:keep] + suffix


def build_fact_lines(
    input_payload: dict[str, Any],
    policy_payload: dict[str, Any],
    decision_payload: dict[str, Any],
    trigger_payload: dict[str, Any],
) -> list[str]:
    """
    Build a compact ordered fact list for AI context.
    构建一组紧凑且有顺序的事实列表，作为 AI 上下文输入。
    """
    market_context = input_payload.get("market_context", {})
    cost_context = input_payload.get("cost_context", {})
    runtime_context = input_payload.get("runtime_context", {})
    local_gate_context = input_payload.get("local_gate_context", {})
    policy_thresholds = policy_payload.get("policy_thresholds", {})
    trigger_scores = trigger_payload.get("scores", {})
    trigger_feature_snapshot = trigger_payload.get("feature_snapshot", {})
    decision_result = decision_payload.get("decision_result", {})

    facts = [
        f"exchange=bybit",
        f"symbol={market_context.get('symbol')}",
        f"category={market_context.get('category')}",
        f"system_mode={runtime_context.get('system_mode')}",
        f"execution_state={runtime_context.get('execution_state')}",
        f"overall_runtime_state={runtime_context.get('overall_runtime_state')}",
        f"market_friction_state={local_gate_context.get('market_friction_state')}",
        f"risk_envelope_state={local_gate_context.get('risk_envelope_state')}",
        f"trade_eligibility_state={local_gate_context.get('trade_eligibility_state')}",
        f"spread_bps={market_context.get('spread_bps')}",
        f"volatility_bps={market_context.get('volatility_bps')}",
        f"volatility_band={market_context.get('volatility_band')}",
        f"slippage_buy_bps={market_context.get('slippage_buy_bps_for_test_notional')}",
        f"slippage_sell_bps={market_context.get('slippage_sell_bps_for_test_notional')}",
        f"recent_trade_count={market_context.get('recent_trade_count')}",
        f"required_edge_bps={cost_context.get('required_edge_bps')}",
        f"total_cost_floor_bps={cost_context.get('total_cost_floor_bps')}",
        f"policy_light_max_expected_roundtrip_ms={policy_thresholds.get('light_max_expected_roundtrip_ms')}",
        f"policy_standard_max_expected_roundtrip_ms={policy_thresholds.get('standard_max_expected_roundtrip_ms')}",
        f"policy_light_max_per_call_budget_usd={policy_thresholds.get('light_max_per_call_budget_usd')}",
        f"policy_standard_max_per_call_budget_usd={policy_thresholds.get('standard_max_per_call_budget_usd')}",
        f"trigger_market_quality_score={trigger_scores.get('market_quality_score')}",
        f"trigger_regime_interest_score={trigger_scores.get('regime_interest_score')}",
        f"trigger_total_score={trigger_scores.get('total_trigger_score')}",
        f"coverage_complete={trigger_feature_snapshot.get('coverage_complete')}",
        f"recent_trade_count_sufficient={trigger_feature_snapshot.get('recent_trade_count_sufficient')}",
        f"last_trade_fields_present={trigger_feature_snapshot.get('last_trade_fields_present')}",
        f"selected_ai_tier={decision_result.get('selected_ai_tier')}",
        f"should_call_ai={decision_result.get('should_call_ai')}",
    ]
    return facts


def build_response_contract(selected_ai_tier: str) -> dict[str, Any]:
    """
    Define the desired AI response contract.
    定义期望的 AI 输出契约。
    """
    return {
        "format": "json_object",
        "required_fields": [
            "analysis_mode",
            "market_regime",
            "action_bias",
            "confidence_0_to_1",
            "edge_assessment_bps",
            "key_reasons",
            "risk_notes",
            "why_not_trade",
        ],
        "constraints": {
            "analysis_mode": "observation_only",
            "action_bias_allowed": ["long_bias", "short_bias", "flat_bias"],
            "max_key_reasons": 5,
            "max_risk_notes": 5,
            "max_why_not_trade": 5,
            "tier": selected_ai_tier,
        },
    }


def build_report() -> dict[str, Any]:
    """
    Build one H1-D prompt preparation report.
    构建一份 H1-D prompt 准备报告。
    """
    ts_ms = int(time.time() * 1000)

    input_payload, input_present, input_error = load_json(INPUT_PATH)
    policy_payload, policy_present, policy_error = load_json(POLICY_PATH)
    decision_payload, decision_present, decision_error = load_json(DECISION_PATH)
    trigger_payload, trigger_present, trigger_error = load_json(TRIGGER_PATH)

    source_errors = [
        item
        for item in [input_error, policy_error, decision_error, trigger_error]
        if item
    ]

    blocking_reasons: list[str] = []
    warning_flags: list[str] = []

    if not input_present:
        blocking_reasons.append("thought_gate_input_missing")
    if not policy_present:
        blocking_reasons.append("thought_gate_policy_missing")
    if not decision_present:
        blocking_reasons.append("thought_gate_decision_missing")
    if not trigger_present:
        blocking_reasons.append("local_trigger_model_missing")

    decision_state = decision_payload.get("decision_state", "unknown") if decision_present else "missing"
    decision_result = decision_payload.get("decision_result", {}) if decision_present else {}
    selected_ai_tier = decision_result.get("selected_ai_tier", "none")
    should_call_ai = bool(decision_result.get("should_call_ai")) if decision_present else False
    allow_progress_to_h1d_prompt = bool(
        decision_result.get("allow_progress_to_h1d_prompt")
    ) if decision_present else False

    if selected_ai_tier not in ALLOWED_AI_TIERS:
        selected_ai_tier = "none"

    if decision_state not in ALLOWED_DECISION_STATES:
        blocking_reasons.append("decision_state_invalid")
    if decision_state not in {"decision_ready_light_ai_call", "decision_ready_standard_ai_call"}:
        blocking_reasons.append("decision_not_prompt_ready")
    if not should_call_ai:
        blocking_reasons.append("decision_should_call_ai_false")
    if not allow_progress_to_h1d_prompt:
        blocking_reasons.append("decision_h1d_gate_closed")
    if selected_ai_tier == "none":
        blocking_reasons.append("selected_ai_tier_none")

    # -----------------------------------------------------------------------
    # Tier-specific prompt budget / 分层 prompt 预算
    # -----------------------------------------------------------------------
    light_max_prompt_chars = parse_int_env(
        LIGHT_MAX_PROMPT_CHARS_ENV,
        DEFAULT_LIGHT_MAX_PROMPT_CHARS,
    )
    standard_max_prompt_chars = parse_int_env(
        STANDARD_MAX_PROMPT_CHARS_ENV,
        DEFAULT_STANDARD_MAX_PROMPT_CHARS,
    )
    light_max_facts = parse_int_env(
        LIGHT_MAX_FACTS_ENV,
        DEFAULT_LIGHT_MAX_FACTS,
    )
    standard_max_facts = parse_int_env(
        STANDARD_MAX_FACTS_ENV,
        DEFAULT_STANDARD_MAX_FACTS,
    )
    light_max_output_tokens_hint = parse_int_env(
        LIGHT_MAX_OUTPUT_TOKENS_HINT_ENV,
        DEFAULT_LIGHT_MAX_OUTPUT_TOKENS_HINT,
    )
    standard_max_output_tokens_hint = parse_int_env(
        STANDARD_MAX_OUTPUT_TOKENS_HINT_ENV,
        DEFAULT_STANDARD_MAX_OUTPUT_TOKENS_HINT,
    )
    require_json_response = parse_bool_env(
        REQUIRE_JSON_RESPONSE_ENV,
        DEFAULT_REQUIRE_JSON_RESPONSE,
    )

    policy_thresholds = policy_payload.get("policy_thresholds", {}) if policy_present else {}
    light_deadline_ms = policy_thresholds.get("light_max_expected_roundtrip_ms")
    standard_deadline_ms = policy_thresholds.get("standard_max_expected_roundtrip_ms")

    if selected_ai_tier == "standard":
        max_prompt_chars = standard_max_prompt_chars
        max_fact_count = standard_max_facts
        max_output_tokens_hint = standard_max_output_tokens_hint
        response_deadline_ms_hint = standard_deadline_ms
    else:
        max_prompt_chars = light_max_prompt_chars
        max_fact_count = light_max_facts
        max_output_tokens_hint = light_max_output_tokens_hint
        response_deadline_ms_hint = light_deadline_ms

    # -----------------------------------------------------------------------
    # Facts and warnings / 事实与警告
    # -----------------------------------------------------------------------
    fact_lines = build_fact_lines(
        input_payload=input_payload,
        policy_payload=policy_payload,
        decision_payload=decision_payload,
        trigger_payload=trigger_payload,
    )[:max_fact_count]

    warning_flags.extend(input_payload.get("operator_flags", []) if input_present else [])
    warning_flags.extend(policy_payload.get("warning_flags", []) if policy_present else [])
    warning_flags.extend(decision_payload.get("warning_flags", []) if decision_present else [])
    warning_flags.extend(trigger_payload.get("warning_flags", []) if trigger_present else [])
    warning_flags = unique_preserve_order(warning_flags)

    # -----------------------------------------------------------------------
    # Prompt assembly / Prompt 组装
    # -----------------------------------------------------------------------
    system_prompt = (
        "You are a conservative trading analysis assistant operating in observation-only mode. "
        "You are NOT allowed to authorize live execution. "
        "Use only the supplied facts. "
        "Be latency-aware, cost-aware, and data-quality-aware. "
        "Return a compact JSON object only."
    )

    response_contract = build_response_contract(selected_ai_tier=selected_ai_tier)

    user_prompt_lines = [
        "Analyze the following Bybit market snapshot conservatively.",
        "Do not assume missing data.",
        "Do not recommend execution as certain.",
        "Prefer 'flat_bias' if evidence is weak or data-quality concerns are material.",
        "",
        "FACTS:",
    ]
    user_prompt_lines.extend(f"- {item}" for item in fact_lines)

    if warning_flags:
        user_prompt_lines.append("")
        user_prompt_lines.append("WARNINGS:")
        user_prompt_lines.extend(f"- {item}" for item in warning_flags[:10])

    user_prompt_lines.append("")
    user_prompt_lines.append("RESPONSE_CONTRACT:")
    user_prompt_lines.append(json.dumps(response_contract, ensure_ascii=False, separators=(",", ":")))

    user_prompt = "\n".join(user_prompt_lines)
    user_prompt = clip_text(user_prompt, max_prompt_chars)

    # -----------------------------------------------------------------------
    # Final state / 最终状态
    # -----------------------------------------------------------------------
    if blocking_reasons:
        prep_state = "blocked_not_ready_for_prompt_prep"
        allow_progress_to_h1e_request = False
        recommended_action = "repair_h1c_or_h2a_before_prompt_prep"
    elif selected_ai_tier == "standard":
        prep_state = "ready_standard_prompt_prep"
        allow_progress_to_h1e_request = True
        recommended_action = "may_progress_to_h1e_standard_ai_request"
    else:
        prep_state = "ready_light_prompt_prep"
        allow_progress_to_h1e_request = True
        recommended_action = "may_progress_to_h1e_light_ai_request"

    if prep_state not in ALLOWED_PREP_STATES:
        prep_state = "blocked_not_ready_for_prompt_prep"
        allow_progress_to_h1e_request = False
        if "invalid_prep_state_generated" not in blocking_reasons:
            blocking_reasons.append("invalid_prep_state_generated")
        recommended_action = "repair_h1d_prompt_prep_logic"

    return {
        "prep_type": "bybit_ai_prompt_prep",
        "prep_version": "v1",
        "ts_ms": ts_ms,
        "exchange": "bybit",
        "stage": "H1-D",
        "report_ok": True,
        "source_refs": {
            "thought_gate_input_path": str(INPUT_PATH),
            "thought_gate_policy_path": str(POLICY_PATH),
            "thought_gate_decision_path": str(DECISION_PATH),
            "local_trigger_model_path": str(TRIGGER_PATH),
        },
        "source_integrity": {
            "thought_gate_input_present": input_present,
            "thought_gate_policy_present": policy_present,
            "thought_gate_decision_present": decision_present,
            "local_trigger_model_present": trigger_present,
            "source_errors": source_errors,
        },
        "readiness_summary": {
            "decision_state": decision_state,
            "selected_ai_tier": selected_ai_tier,
            "should_call_ai": should_call_ai,
            "allow_progress_to_h1d_prompt": allow_progress_to_h1d_prompt,
        },
        "prompt_budget": {
            "max_prompt_chars": max_prompt_chars,
            "max_fact_count": max_fact_count,
            "max_output_tokens_hint": max_output_tokens_hint,
            "response_deadline_ms_hint": response_deadline_ms_hint,
            "require_json_response": require_json_response,
            "source_map": {
                "light_max_prompt_chars": f"env:{LIGHT_MAX_PROMPT_CHARS_ENV}",
                "standard_max_prompt_chars": f"env:{STANDARD_MAX_PROMPT_CHARS_ENV}",
                "light_max_facts": f"env:{LIGHT_MAX_FACTS_ENV}",
                "standard_max_facts": f"env:{STANDARD_MAX_FACTS_ENV}",
                "light_max_output_tokens_hint": f"env:{LIGHT_MAX_OUTPUT_TOKENS_HINT_ENV}",
                "standard_max_output_tokens_hint": f"env:{STANDARD_MAX_OUTPUT_TOKENS_HINT_ENV}",
                "require_json_response": f"env:{REQUIRE_JSON_RESPONSE_ENV}",
            },
        },
        "fact_lines": fact_lines,
        "warning_flags": warning_flags,
        "blocking_reasons": blocking_reasons,
        "prompt_payload": {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "response_contract": response_contract,
        },
        "prep_state": prep_state,
        "allow_progress_to_h1e_request": allow_progress_to_h1e_request,
        "recommended_action": recommended_action,
        "operator_message": (
            "H1-D AI prompt prep built. This object prepares a bounded, compact, "
            "latency-aware AI prompt package, but still does not itself call AI "
            "and does not authorize trading."
        ),
    }


def main() -> None:
    """
    Entry point / 程序入口。
    """
    report = build_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    latest_path, dated_path = save_report(report)
    print(f"saved_latest={latest_path}")
    print(f"saved_dated={dated_path}")


if __name__ == "__main__":
    main()
