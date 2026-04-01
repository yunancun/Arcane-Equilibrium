#!/usr/bin/env python3
"""
MODULE_NOTE / 模块说明:
- role / 角色:
  H1-R AI route selector builder / H1-R AI 自动路由选择器。

- purpose / 目的:
  Consume current H1/H2 gate outputs, then deterministically choose
  route A / B / C / skip based on urgency, opportunity, uncertainty,
  budget, and current policy cap.
  消费当前 H1/H2 gate 输出，并基于紧急性、机会大小、不确定性、
  预算和当前 policy cap，确定性地选择 A / B / C / skip 路线。

- route semantics / 路线语义:
  A = light / cheap-fast lane
      A = 轻量 / 便宜快速路线
  B = standard direct decision lane
      B = 标准直接决策路线
  C = escalated stronger-decision lane
      C = 升级后的更强决策路线
  skip = do not call AI this cycle
      skip = 本轮不调用 AI

- important current limitation / 当前重要限制:
  1) Existing H1-E / H1-F pipeline currently supports light / standard
     request tiers more naturally than a brand-new premium tier.
     现有 H1-E / H1-F 管线目前更自然支持 light / standard 两档，
     还没有单独扩出一个全新 premium tier。
  2) Therefore route C currently reuses the standard request pipe, but
     expects the strongest configured model to be bound into the route-C slot.
     因此当前 C 路会复用 standard 请求通道，但要求把“最强模型”
     绑定到 route-C 对应配置槽位上。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

RUNTIME_ROOT = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit")
THOUGHT_GATE_DIR = RUNTIME_ROOT / "thought_gate"
TRIGGER_DIR = RUNTIME_ROOT / "trigger_model"

INPUT_PATH = THOUGHT_GATE_DIR / "bybit_thought_gate_input_latest.json"
POLICY_PATH = THOUGHT_GATE_DIR / "bybit_thought_gate_policy_latest.json"
TRIGGER_PATH = TRIGGER_DIR / "bybit_local_trigger_model_latest.json"
DECISION_PATH = THOUGHT_GATE_DIR / "bybit_thought_gate_decision_latest.json"

OUT_LATEST = THOUGHT_GATE_DIR / "bybit_ai_route_selector_latest.json"

ROUTE_A_MAX_COST_ENV = "BYBIT_ROUTE_A_MAX_COST_USD"
ROUTE_B_MAX_COST_ENV = "BYBIT_ROUTE_B_MAX_COST_USD"
ROUTE_C_MAX_COST_ENV = "BYBIT_ROUTE_C_MAX_COST_USD"

HIGH_URGENCY_ENV = "BYBIT_ROUTE_HIGH_URGENCY_THRESHOLD"
BIG_OPPORTUNITY_ENV = "BYBIT_ROUTE_BIG_OPPORTUNITY_THRESHOLD"
MID_OPPORTUNITY_ENV = "BYBIT_ROUTE_MID_OPPORTUNITY_THRESHOLD"
MAX_UNCERTAINTY_FOR_C_ENV = "BYBIT_ROUTE_MAX_UNCERTAINTY_FOR_C"
MIN_BUDGET_FOR_C_ENV = "BYBIT_ROUTE_MIN_BUDGET_FOR_C"
ROUTE_C_ENABLED_ENV = "BYBIT_ROUTE_C_ENABLED"


def now_ms() -> int:  # TODO: consolidate with app.utils.time_utils.now_ms
    """Return current unix time in milliseconds / 返回当前毫秒时间戳。"""
    return int(time.time() * 1000)


def load_json(path: Path) -> dict[str, Any]:
    """Load JSON file / 读取 JSON 文件。"""
    return json.loads(path.read_text(encoding="utf-8"))


def env_float(name: str, default: float) -> float:
    """Read float env safely / 安全读取浮点环境变量。"""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    """Read int env safely / 安全读取整数环境变量。"""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_bool(name: str, default: bool) -> bool:
    """Read bool-like env safely / 安全读取布尔环境变量。"""
    raw = os.getenv(name, "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def clamp_score(value: float) -> int:
    """Clamp score into 0..100 / 将分数钳制到 0..100。"""
    return max(0, min(100, int(round(value))))


def write_report(payload: dict[str, Any]) -> tuple[Path, Path]:
    """Write latest + dated JSON outputs / 写出 latest + dated 两份 JSON。"""
    OUT_LATEST.parent.mkdir(parents=True, exist_ok=True)
    ts_ms = payload["ts_ms"]
    dated = OUT_LATEST.with_name(f"bybit_ai_route_selector_{ts_ms}.json")
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    OUT_LATEST.write_text(text + "\n", encoding="utf-8")
    dated.write_text(text + "\n", encoding="utf-8")
    return OUT_LATEST, dated


def main() -> None:
    ts_ms = now_ms()

    source_errors: list[str] = []
    input_present = INPUT_PATH.exists()
    policy_present = POLICY_PATH.exists()
    trigger_present = TRIGGER_PATH.exists()
    decision_present = DECISION_PATH.exists()

    if not input_present:
        source_errors.append(f"missing:{INPUT_PATH}")
    if not policy_present:
        source_errors.append(f"missing:{POLICY_PATH}")
    if not trigger_present:
        source_errors.append(f"missing:{TRIGGER_PATH}")
    if not decision_present:
        source_errors.append(f"missing:{DECISION_PATH}")

    input_payload = load_json(INPUT_PATH) if input_present else {}
    policy_payload = load_json(POLICY_PATH) if policy_present else {}
    trigger_payload = load_json(TRIGGER_PATH) if trigger_present else {}
    decision_payload = load_json(DECISION_PATH) if decision_present else {}

    input_state = input_payload.get("input_state")
    policy_state = policy_payload.get("policy_state")
    trigger_state = trigger_payload.get("trigger_state")
    decision_state = decision_payload.get("decision_state")

    policy_max_ai_call_tier = (
        policy_payload.get("tier_caps", {}) or {}
    ).get("final_max_ai_call_tier", "none")

    selected_ai_tier_from_h1c = (
        decision_payload.get("decision_result", {}) or {}
    ).get("selected_ai_tier", "none")

    should_call_ai_from_h1c = bool(
        (decision_payload.get("decision_result", {}) or {}).get("should_call_ai", False)
    )

    # ---------------------------------------------------------------------
    # Input-derived numeric context / 从输入对象提取的数值上下文
    # ---------------------------------------------------------------------
    freshness = input_payload.get("freshness", {}) or {}
    public_age_ms = int(freshness.get("public_microstructure_age_ms") or 0)

    policy_inputs = input_payload.get("policy_inputs", {}) or {}
    max_public_data_age_ms = int(policy_inputs.get("max_public_data_age_ms") or 15000)
    ai_max_expected_roundtrip_ms = int(policy_inputs.get("ai_max_expected_roundtrip_ms") or 2500)
    ai_daily_budget_usd = float(policy_inputs.get("ai_daily_budget_usd") or 0.0)
    ai_per_call_budget_usd = float(policy_inputs.get("ai_per_call_budget_usd") or 0.0)

    trigger_scores = trigger_payload.get("scores", {}) or {}
    total_trigger_score = int(trigger_scores.get("total_trigger_score") or 0)

    warning_flags = list(
        dict.fromkeys(
            (input_payload.get("operator_flags", []) or [])
            + (policy_payload.get("warning_flags", []) or [])
            + (trigger_payload.get("warning_flags", []) or [])
            + (decision_payload.get("warning_flags", []) or [])
        )
    )

    # ---------------------------------------------------------------------
    # Route control knobs / 路由控制参数
    # ---------------------------------------------------------------------
    route_a_max_cost_usd = env_float(ROUTE_A_MAX_COST_ENV, 0.03)
    route_b_max_cost_usd = env_float(ROUTE_B_MAX_COST_ENV, 0.08)
    route_c_max_cost_usd = env_float(ROUTE_C_MAX_COST_ENV, 0.20)

    high_urgency_threshold = env_int(HIGH_URGENCY_ENV, 75)
    big_opportunity_threshold = env_int(BIG_OPPORTUNITY_ENV, 85)
    mid_opportunity_threshold = env_int(MID_OPPORTUNITY_ENV, 70)
    max_uncertainty_for_c = env_int(MAX_UNCERTAINTY_FOR_C_ENV, 35)
    min_budget_for_c = env_int(MIN_BUDGET_FOR_C_ENV, 80)
    route_c_enabled = env_bool(ROUTE_C_ENABLED_ENV, True)

    # ---------------------------------------------------------------------
    # Score calculation / 分数计算
    # ---------------------------------------------------------------------
    freshness_ratio = min(1.0, public_age_ms / max(max_public_data_age_ms, 1))

    # urgency_score:
    # Lower allowed roundtrip usually means more time-sensitive path.
    # 越低的允许往返延迟，通常意味着越偏时间敏感。
    urgency_from_deadline = (
        90 if ai_max_expected_roundtrip_ms <= 1200
        else 75 if ai_max_expected_roundtrip_ms <= 1800
        else 60 if ai_max_expected_roundtrip_ms <= 2500
        else 40
    )
    urgency_penalty = freshness_ratio * 15.0
    urgency_score = clamp_score(urgency_from_deadline - urgency_penalty)

    # opportunity_score:
    # Current best proxy is local trigger total score.
    # 当前最好的机会大小代理量，就是本地 trigger 总分。
    opportunity_score = clamp_score(total_trigger_score)

    # uncertainty_score:
    # Missing last-trade fields, stale warnings, runtime reference age etc.
    # 会提高不确定性。
    uncertainty_score = 0
    if "last_trade_fields_missing" in warning_flags:
        uncertainty_score += 20
    if "recent_trade_last_price_missing" in warning_flags:
        uncertainty_score += 15
    if "recent_trade_last_ts_missing" in warning_flags:
        uncertainty_score += 15
    if "runtime_state_reference_old" in warning_flags:
        uncertainty_score += 10
    if "freshness_soft_warning_present" in warning_flags:
        uncertainty_score += 10
    if "public_microstructure_stale" in warning_flags:
        uncertainty_score += 20
    if "h0_final_audit_stale" in warning_flags:
        uncertainty_score += 10
    uncertainty_score = clamp_score(uncertainty_score)

    # budget_score:
    # Higher score means stronger route remains affordable.
    # 分数越高，表示越有能力承担更强路线。
    if ai_per_call_budget_usd >= route_c_max_cost_usd and ai_daily_budget_usd >= 10.0:
        budget_score = 95
    elif ai_per_call_budget_usd >= route_b_max_cost_usd and ai_daily_budget_usd >= 5.0:
        budget_score = 80
    elif ai_per_call_budget_usd >= route_a_max_cost_usd and ai_daily_budget_usd >= 1.0:
        budget_score = 65
    elif ai_per_call_budget_usd > 0:
        budget_score = 40
    else:
        budget_score = 0

    # latency_score:
    # Lower tolerated latency means faster lane pressure is higher.
    # 允许的延迟越低，越偏快路压力。
    latency_score = clamp_score(
        95 if ai_max_expected_roundtrip_ms <= 1200
        else 80 if ai_max_expected_roundtrip_ms <= 1800
        else 65 if ai_max_expected_roundtrip_ms <= 2500
        else 45
    )

    # ---------------------------------------------------------------------
    # Allowability by current policy / 当前 policy 对路由的允许范围
    # ---------------------------------------------------------------------
    route_a_allowed = should_call_ai_from_h1c and policy_max_ai_call_tier in {"light", "standard"}
    route_b_allowed = should_call_ai_from_h1c and policy_max_ai_call_tier == "standard"
    route_c_allowed = route_b_allowed and route_c_enabled

    # ---------------------------------------------------------------------
    # Actual route selection / 实际路线选择
    # ---------------------------------------------------------------------
    blocking_reasons: list[str] = []
    route_notes: list[str] = []

    route_plan = "route_skip"
    selected_ai_tier = "none"
    should_call_ai = False
    lane_semantics = "skip"
    route_reason = "h1c_did_not_authorize_ai"

    if not all([input_present, policy_present, trigger_present, decision_present]):
        blocking_reasons.append("missing_upstream_source")
        route_reason = "missing_upstream_source"

    elif not should_call_ai_from_h1c:
        blocking_reasons.append("h1c_should_call_ai_false")
        route_reason = "h1c_should_call_ai_false"

    elif decision_state not in {"decision_ready_light_ai_call", "decision_ready_standard_ai_call"}:
        blocking_reasons.append("h1c_decision_not_ready")
        route_reason = "h1c_decision_not_ready"

    elif input_state != "ready_for_thought_gate_policy_evaluation":
        blocking_reasons.append("h1a_input_not_ready")
        route_reason = "h1a_input_not_ready"

    elif policy_state not in {"policy_ready_light_only", "policy_ready_standard"}:
        blocking_reasons.append("h1b_policy_not_ready")
        route_reason = "h1b_policy_not_ready"

    elif trigger_state not in {"triggered_light_ai_review", "triggered_standard_ai_review"}:
        blocking_reasons.append("h2_trigger_not_ready")
        route_reason = "h2_trigger_not_ready"

    else:
        should_call_ai = True

        # Policy only allows light -> must stay in A.
        # policy 只允许 light -> 只能走 A。
        if policy_max_ai_call_tier == "light":
            route_plan = "route_a_light"
            selected_ai_tier = "light"
            lane_semantics = "cheap_fast_pass"
            route_reason = "policy_caps_ai_at_light"

        # C route:
        # Very urgent + very worthwhile + uncertainty low + budget sufficient.
        # 很急 + 很值得 + 不确定性低 + 预算够，才升到 C。
        elif route_c_allowed and (
            urgency_score >= high_urgency_threshold
            and opportunity_score >= big_opportunity_threshold
            and uncertainty_score <= max_uncertainty_for_c
            and budget_score >= min_budget_for_c
        ):
            route_plan = "route_c_escalated_standard"
            selected_ai_tier = "standard"
            lane_semantics = "escalated_decision_review"
            route_reason = "high_urgency_high_opportunity_low_uncertainty"
            route_notes.append(
                "Current route C reuses the standard request pipe and expects the strongest configured model to be bound into the route-C standard slot."
            )

        # B route:
        # Reasonably strong opportunity or urgency, without needing hard escalation.
        # 有一定机会或时间敏感，但还不到必须硬升级的程度，就走 B。
        elif route_b_allowed and (
            opportunity_score >= mid_opportunity_threshold
            or urgency_score >= high_urgency_threshold
        ):
            route_plan = "route_b_standard"
            selected_ai_tier = "standard"
            lane_semantics = "standard_direct_decision"
            route_reason = "standard_lane_worthwhile"

        # A route:
        # Default cheaper path when AI is allowed but not worth stronger spend.
        # 当允许问 AI 但还不值得花更贵模型时，默认走 A。
        elif route_a_allowed:
            route_plan = "route_a_light"
            selected_ai_tier = "light"
            lane_semantics = "cheap_fast_pass"
            route_reason = "save_cost_under_moderate_signal"

        else:
            route_plan = "route_skip"
            selected_ai_tier = "none"
            should_call_ai = False
            lane_semantics = "skip"
            route_reason = "no_route_allowed_under_current_caps"
            blocking_reasons.append("no_route_allowed_under_current_caps")

    payload = {
        "route_type": "bybit_ai_route_selector",
        "route_version": "v1",
        "ts_ms": ts_ms,
        "exchange": "bybit",
        "stage": "H1-R",
        "report_ok": len(source_errors) == 0,
        "source_refs": {
            "thought_gate_input_path": str(INPUT_PATH),
            "thought_gate_policy_path": str(POLICY_PATH),
            "local_trigger_model_path": str(TRIGGER_PATH),
            "thought_gate_decision_path": str(DECISION_PATH),
        },
        "source_integrity": {
            "thought_gate_input_present": input_present,
            "thought_gate_policy_present": policy_present,
            "local_trigger_model_present": trigger_present,
            "thought_gate_decision_present": decision_present,
            "source_errors": source_errors,
        },
        "input_summary": {
            "input_state": input_state,
            "policy_state": policy_state,
            "trigger_state": trigger_state,
            "decision_state": decision_state,
            "policy_max_ai_call_tier": policy_max_ai_call_tier,
            "selected_ai_tier_from_h1c": selected_ai_tier_from_h1c,
            "should_call_ai_from_h1c": should_call_ai_from_h1c,
        },
        "route_controls": {
            "route_a_max_cost_usd": route_a_max_cost_usd,
            "route_b_max_cost_usd": route_b_max_cost_usd,
            "route_c_max_cost_usd": route_c_max_cost_usd,
            "high_urgency_threshold": high_urgency_threshold,
            "big_opportunity_threshold": big_opportunity_threshold,
            "mid_opportunity_threshold": mid_opportunity_threshold,
            "max_uncertainty_for_c": max_uncertainty_for_c,
            "min_budget_for_c": min_budget_for_c,
            "route_c_enabled": route_c_enabled,
            "source_map": {
                "route_a_max_cost_usd": f"env:{ROUTE_A_MAX_COST_ENV}",
                "route_b_max_cost_usd": f"env:{ROUTE_B_MAX_COST_ENV}",
                "route_c_max_cost_usd": f"env:{ROUTE_C_MAX_COST_ENV}",
                "high_urgency_threshold": f"env:{HIGH_URGENCY_ENV}",
                "big_opportunity_threshold": f"env:{BIG_OPPORTUNITY_ENV}",
                "mid_opportunity_threshold": f"env:{MID_OPPORTUNITY_ENV}",
                "max_uncertainty_for_c": f"env:{MAX_UNCERTAINTY_FOR_C_ENV}",
                "min_budget_for_c": f"env:{MIN_BUDGET_FOR_C_ENV}",
                "route_c_enabled": f"env:{ROUTE_C_ENABLED_ENV}",
            },
        },
        "route_scores": {
            "urgency_score": urgency_score,
            "opportunity_score": opportunity_score,
            "uncertainty_score": uncertainty_score,
            "budget_score": budget_score,
            "latency_score": latency_score,
            "trigger_total_score": total_trigger_score,
        },
        "route_decision": {
            "route_plan": route_plan,
            "selected_ai_tier": selected_ai_tier,
            "should_call_ai": should_call_ai,
            "lane_semantics": lane_semantics,
            "route_reason": route_reason,
            "env_binding_group": (
                "ROUTE_A" if route_plan == "route_a_light"
                else "ROUTE_B" if route_plan == "route_b_standard"
                else "ROUTE_C" if route_plan == "route_c_escalated_standard"
                else "ROUTE_SKIP"
            ),
        },
        "route_notes": route_notes,
        "warning_flags": warning_flags,
        "blocking_reasons": blocking_reasons,
        "route_state": (
            "route_ready_light"
            if route_plan == "route_a_light"
            else "route_ready_standard"
            if route_plan in {"route_b_standard", "route_c_escalated_standard"}
            else "route_blocked_or_skipped"
        ),
        "allow_progress_to_h1e_request": should_call_ai,
        "recommended_action": (
            "bind_route_a_then_continue_h1e"
            if route_plan == "route_a_light"
            else "bind_route_b_then_continue_h1e"
            if route_plan == "route_b_standard"
            else "bind_route_c_then_continue_h1e"
            if route_plan == "route_c_escalated_standard"
            else "repair_blockers_before_ai_request"
        ),
        "operator_message": (
            "H1-R AI route selector built. This object chooses route A/B/C/skip from urgency, opportunity, uncertainty, budget, and current policy caps. "
            "Current implementation maps A->light lane, B->standard lane, and C->escalated standard lane placeholder so the strongest configured model can be bound without changing the rest of the pipeline yet."
        ),
    }

    latest_path, dated_path = write_report(payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest_path}")
    print(f"saved_dated={dated_path}")


if __name__ == "__main__":
    main()
