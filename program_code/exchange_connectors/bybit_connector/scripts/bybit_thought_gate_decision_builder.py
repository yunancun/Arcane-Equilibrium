#!/usr/bin/env python3
"""
MODULE_NOTE / 模块说明:
- role / 角色:
  H1 thought gate decision builder / H1 思考门决策构建器。

- purpose / 目的:
  Consume H1-A normalized input, H1-B policy envelope, and H2 local trigger
  model result, then decide whether this cycle should progress toward real AI
  prompt preparation.
  消费 H1-A 标准化输入、H1-B policy 包络、以及 H2 本地触发模型结果，
  并判断这一轮是否应当进入真实的 AI prompt 准备路径。

- upstream / 上游输入:
  1) runtime/bybit/thought_gate/bybit_thought_gate_input_latest.json
  2) runtime/bybit/thought_gate/bybit_thought_gate_policy_latest.json
  3) runtime/bybit/trigger_model/bybit_local_trigger_model_latest.json

- output / 输出:
  runtime/bybit/thought_gate/bybit_thought_gate_decision_latest.json

- notes / 备注:
  1) This module still does NOT call AI.
     本模块依旧不会真正调用 AI。
  2) This module is the bridge from "policy allows AI" to
     "this cycle actually deserves AI prompt preparation".
     本模块是从“policy 允许 AI”过渡到“这一轮真的值得准备 AI prompt”的桥梁。
  3) v2 now consumes the real H2 local trigger model instead of a fake env
     placeholder.
     v2 现在读取真实的 H2 本地触发模型，而不是依赖假的 env 占位。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Path constants / 路径常量
# ---------------------------------------------------------------------------

THOUGHT_GATE_DIR = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate"
)
TRIGGER_DIR = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/trigger_model"
)

INPUT_PATH = THOUGHT_GATE_DIR / "bybit_thought_gate_input_latest.json"
POLICY_PATH = THOUGHT_GATE_DIR / "bybit_thought_gate_policy_latest.json"
TRIGGER_MODEL_PATH = TRIGGER_DIR / "bybit_local_trigger_model_latest.json"
LATEST_OUTPUT_PATH = THOUGHT_GATE_DIR / "bybit_thought_gate_decision_latest.json"

ALLOWED_AI_TIERS = {
    "none",
    "light",
    "standard",
}

ALLOWED_DECISION_STATES = {
    "decision_blocked",
    "decision_skip_no_local_trigger_model",
    "decision_skip_trigger_model_not_fired",
    "decision_ready_light_ai_call",
    "decision_ready_standard_ai_call",
}


def load_json(path: Path) -> tuple[dict[str, Any], bool, str | None]:
    """
    Load JSON file from disk.
    从磁盘加载 JSON 文件。
    """
    if not path.exists():
        return {}, False, f"missing_file:{path}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), True, None
    except Exception as exc:  # pragma: no cover
        return {}, False, f"json_load_error:{path}:{exc}"


def save_report(report: dict[str, Any]) -> tuple[Path, Path]:
    """
    Save latest and dated decision reports.
    保存 latest 与按时间戳归档的 decision report。
    """
    THOUGHT_GATE_DIR.mkdir(parents=True, exist_ok=True)
    latest_path = LATEST_OUTPUT_PATH
    dated_path = THOUGHT_GATE_DIR / f"bybit_thought_gate_decision_{report['ts_ms']}.json"
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    latest_path.write_text(serialized, encoding="utf-8")
    dated_path.write_text(serialized, encoding="utf-8")
    return latest_path, dated_path


def tighter_tier(left: str, right: str) -> str:
    """
    Return the more conservative tier.
    返回两个 tier 中更保守的那个。
    """
    order = {"none": 0, "light": 1, "standard": 2}
    if order.get(left, 0) <= order.get(right, 0):
        return left
    return right


def build_report() -> dict[str, Any]:
    """
    Build one H1-C thought-gate decision report.
    构建一份 H1-C thought-gate 决策报告。
    """
    ts_ms = int(time.time() * 1000)

    input_payload, input_present, input_error = load_json(INPUT_PATH)
    policy_payload, policy_present, policy_error = load_json(POLICY_PATH)
    trigger_payload, trigger_present, trigger_error = load_json(TRIGGER_MODEL_PATH)

    source_errors = [
        item
        for item in [input_error, policy_error, trigger_error]
        if item
    ]

    input_state = input_payload.get("input_state", "unknown") if input_present else "missing"
    allow_progress_to_h1b_policy = bool(
        input_payload.get("allow_progress_to_h1b_policy")
    ) if input_present else False

    policy_state = policy_payload.get("policy_state", "unknown") if policy_present else "missing"
    allow_progress_to_h1c_decision = bool(
        policy_payload.get("allow_progress_to_h1c_decision")
    ) if policy_present else False

    tier_caps = policy_payload.get("tier_caps", {}) if policy_present else {}
    policy_max_ai_call_tier = tier_caps.get("final_max_ai_call_tier", "none")
    if policy_max_ai_call_tier not in ALLOWED_AI_TIERS:
        policy_max_ai_call_tier = "none"

    trigger_state = trigger_payload.get("trigger_state", "unknown") if trigger_present else "missing"
    should_trigger_ai_review = bool(
        trigger_payload.get("should_trigger_ai_review")
    ) if trigger_present else False
    suggested_ai_tier = trigger_payload.get("suggested_ai_tier", "none") if trigger_present else "none"
    if suggested_ai_tier not in ALLOWED_AI_TIERS:
        suggested_ai_tier = "none"

    runtime_context = input_payload.get("runtime_context", {}) if input_present else {}
    overall_runtime_state = runtime_context.get("overall_runtime_state", "unknown")
    system_mode = runtime_context.get("system_mode", "unknown")
    execution_state = runtime_context.get("execution_state", "unknown")

    local_gate_context = input_payload.get("local_gate_context", {}) if input_present else {}
    market_friction_allow = bool(local_gate_context.get("market_friction_allow"))
    risk_envelope_allow = bool(local_gate_context.get("risk_envelope_allow"))
    allow_progress_to_thought_gate = bool(local_gate_context.get("allow_progress_to_thought_gate"))

    warning_flags = []
    blocking_reasons = []

    if not input_present:
        blocking_reasons.append("thought_gate_input_missing")
    if not policy_present:
        blocking_reasons.append("thought_gate_policy_missing")
    if input_state != "ready_for_thought_gate_policy_evaluation":
        blocking_reasons.append("input_state_not_ready")
    if not allow_progress_to_h1b_policy:
        blocking_reasons.append("input_gate_not_ready")
    if policy_state not in {"policy_ready_light_only", "policy_ready_standard_allowed"}:
        blocking_reasons.append("policy_state_not_ready")
    if not allow_progress_to_h1c_decision:
        blocking_reasons.append("policy_does_not_allow_h1c")
    if policy_max_ai_call_tier == "none":
        blocking_reasons.append("policy_ai_tier_none")
    if system_mode != "read_only":
        blocking_reasons.append("runtime_not_read_only")
    if execution_state != "disabled":
        blocking_reasons.append("execution_not_disabled")
    if not market_friction_allow:
        blocking_reasons.append("market_friction_not_allowed")
    if not risk_envelope_allow:
        blocking_reasons.append("risk_envelope_not_allowed")
    if not allow_progress_to_thought_gate:
        blocking_reasons.append("local_trade_eligibility_not_open")

    if not trigger_present:
        decision_state = "decision_skip_no_local_trigger_model"
        selected_ai_tier = "none"
        final_should_call_ai = False
        allow_progress_to_h1d_prompt = False
        recommended_action = "build_h2_local_trigger_model_before_real_ai_calls"
    elif blocking_reasons:
        decision_state = "decision_blocked"
        selected_ai_tier = "none"
        final_should_call_ai = False
        allow_progress_to_h1d_prompt = False
        recommended_action = "repair_h1_or_runtime_blockers"
    elif not should_trigger_ai_review:
        decision_state = "decision_skip_trigger_model_not_fired"
        selected_ai_tier = "none"
        final_should_call_ai = False
        allow_progress_to_h1d_prompt = False
        recommended_action = "wait_for_h2_trigger_model_to_fire"
    else:
        selected_ai_tier = tighter_tier(policy_max_ai_call_tier, suggested_ai_tier)
        final_should_call_ai = selected_ai_tier in {"light", "standard"}
        allow_progress_to_h1d_prompt = final_should_call_ai

        if selected_ai_tier == "standard":
            decision_state = "decision_ready_standard_ai_call"
            recommended_action = "may_progress_to_h1d_standard_prompt_prep"
        elif selected_ai_tier == "light":
            decision_state = "decision_ready_light_ai_call"
            recommended_action = "may_progress_to_h1d_light_prompt_prep"
        else:
            decision_state = "decision_skip_trigger_model_not_fired"
            final_should_call_ai = False
            allow_progress_to_h1d_prompt = False
            recommended_action = "inspect_trigger_and_policy_tier_resolution"

    if decision_state not in ALLOWED_DECISION_STATES:
        decision_state = "decision_blocked"
        selected_ai_tier = "none"
        final_should_call_ai = False
        allow_progress_to_h1d_prompt = False
        if "invalid_decision_state_generated" not in blocking_reasons:
            blocking_reasons.append("invalid_decision_state_generated")
        recommended_action = "repair_decision_builder_logic"

    trigger_warning_flags = trigger_payload.get("warning_flags", []) if trigger_present else []
    policy_warning_flags = policy_payload.get("warning_flags", []) if policy_present else []
    for item in trigger_warning_flags + policy_warning_flags:
        if item not in warning_flags:
            warning_flags.append(item)

    return {
        "decision_type": "bybit_thought_gate_decision",
        "decision_version": "v2",
        "ts_ms": ts_ms,
        "exchange": "bybit",
        "stage": "H1-C",
        "report_ok": True,
        "source_refs": {
            "thought_gate_input_path": str(INPUT_PATH),
            "thought_gate_policy_path": str(POLICY_PATH),
            "local_trigger_model_path": str(TRIGGER_MODEL_PATH),
        },
        "source_integrity": {
            "thought_gate_input_present": input_present,
            "thought_gate_policy_present": policy_present,
            "local_trigger_model_present": trigger_present,
            "source_errors": source_errors,
        },
        "input_summary": {
            "input_state": input_state,
            "policy_state": policy_state,
            "trigger_state": trigger_state,
            "overall_runtime_state": overall_runtime_state,
            "system_mode": system_mode,
            "execution_state": execution_state,
        },
        "trigger_model_summary": {
            "should_trigger_ai_review": should_trigger_ai_review,
            "suggested_ai_tier": suggested_ai_tier,
            "policy_max_ai_call_tier": policy_max_ai_call_tier,
        },
        "decision_result": {
            "selected_ai_tier": selected_ai_tier,
            "should_call_ai": final_should_call_ai,
            "allow_progress_to_h1d_prompt": allow_progress_to_h1d_prompt,
        },
        "warning_flags": warning_flags,
        "blocking_reasons": blocking_reasons,
        "decision_state": decision_state,
        "recommended_action": recommended_action,
        "operator_message": (
            "H1-C thought gate decision built. This object decides whether the "
            "current cycle should actually escalate toward AI prompt preparation, "
            "based on H1 policy plus the real H2 local trigger model."
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
