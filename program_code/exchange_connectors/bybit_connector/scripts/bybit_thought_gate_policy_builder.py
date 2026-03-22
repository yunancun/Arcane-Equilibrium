#!/usr/bin/env python3
"""
MODULE_NOTE / 模块说明:
- role / 角色:
  H1 thought gate policy builder / H1 思考门策略构建器。

- purpose / 目的:
  Consume the H1-A normalized thought-gate input and convert it into a
  conservative, auditable AI-call policy envelope.
  消费 H1-A 标准化输入对象，并将其转换为一个保守、可审计的 AI 调用策略包络。

- upstream / 上游输入:
  1) runtime/bybit/thought_gate/bybit_thought_gate_input_latest.json

- output / 输出:
  runtime/bybit/thought_gate/bybit_thought_gate_policy_latest.json

- notes / 备注:
  1) This module does NOT decide whether AI must be called right now.
     本模块不决定“当前这次是否必须调用 AI”。
  2) This module defines the maximum allowed AI participation tier.
     本模块只定义“当前最多允许什么级别的 AI 参与”。
  3) Later H1-C will decide whether to actually call AI for this cycle.
     后续 H1-C 才会决定“这一轮是否真的调用 AI”。
"""

from __future__ import annotations
from bybit_mainline_cleanup_helpers import prune_freshness_warning_flags

import json
import os
import time
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Path constants / 路径常量
# ---------------------------------------------------------------------------

THOUGHT_GATE_DIR = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate"
)
INPUT_PATH = THOUGHT_GATE_DIR / "bybit_thought_gate_input_latest.json"
LATEST_OUTPUT_PATH = THOUGHT_GATE_DIR / "bybit_thought_gate_policy_latest.json"


# ---------------------------------------------------------------------------
# Env knobs / 环境变量参数
# These are policy thresholds, not direct execution switches.
# 这些是策略阈值，不是直接执行开关。
# ---------------------------------------------------------------------------

LIGHT_MAX_EXPECTED_ROUNDTRIP_MS_ENV = "BYBIT_THOUGHT_GATE_LIGHT_MAX_EXPECTED_ROUNDTRIP_MS"
STANDARD_MAX_EXPECTED_ROUNDTRIP_MS_ENV = "BYBIT_THOUGHT_GATE_STANDARD_MAX_EXPECTED_ROUNDTRIP_MS"

LIGHT_MAX_PER_CALL_BUDGET_USD_ENV = "BYBIT_THOUGHT_GATE_LIGHT_MAX_PER_CALL_BUDGET_USD"
STANDARD_MAX_PER_CALL_BUDGET_USD_ENV = "BYBIT_THOUGHT_GATE_STANDARD_MAX_PER_CALL_BUDGET_USD"

RUNTIME_SOFT_MAX_AGE_MS_ENV = "BYBIT_THOUGHT_GATE_RUNTIME_SOFT_MAX_AGE_MS"

DEFAULT_LIGHT_MAX_EXPECTED_ROUNDTRIP_MS = 1500
DEFAULT_STANDARD_MAX_EXPECTED_ROUNDTRIP_MS = 2500

DEFAULT_LIGHT_MAX_PER_CALL_BUDGET_USD = 0.02
DEFAULT_STANDARD_MAX_PER_CALL_BUDGET_USD = 0.05

DEFAULT_RUNTIME_SOFT_MAX_AGE_MS = 900000  # 15 minutes / 15 分钟


AI_TIER_ORDER = {
    "none": 0,
    "light": 1,
    "standard": 2,
}


# ---------------------------------------------------------------------------
# Helpers / 辅助函数
# ---------------------------------------------------------------------------

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


def parse_int_env(name: str, default: int) -> int:
    """
    Parse integer env var with fallback.
    解析整数环境变量，失败时回退默认值。
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        return default


def parse_float_env(name: str, default: float) -> float:
    """
    Parse float env var with fallback.
    解析浮点环境变量，失败时回退默认值。
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(str(raw).strip())
    except ValueError:
        return default


def save_report(report: dict[str, Any]) -> tuple[Path, Path]:
    """
    Save latest and dated policy reports.
    保存 latest 与按时间戳归档的 policy report。
    """
    THOUGHT_GATE_DIR.mkdir(parents=True, exist_ok=True)
    latest_path = LATEST_OUTPUT_PATH
    dated_path = THOUGHT_GATE_DIR / f"bybit_thought_gate_policy_{report['ts_ms']}.json"
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    latest_path.write_text(serialized, encoding="utf-8")
    dated_path.write_text(serialized, encoding="utf-8")
    return latest_path, dated_path


def tighter_tier(left: str, right: str) -> str:
    """
    Return the more conservative tier.
    返回两个 tier 中更保守的那一个。

    Tier strictness:
    none < light < standard
    等级严格度:
    none < light < standard
    """
    if AI_TIER_ORDER[left] <= AI_TIER_ORDER[right]:
        return left
    return right


# ---------------------------------------------------------------------------
# Main policy builder / 主策略构建逻辑
# ---------------------------------------------------------------------------

def build_report() -> dict[str, Any]:
    """
    Build one H1-B thought-gate policy report.
    构建一份 H1-B thought-gate 策略报告。
    """
    ts_ms = int(time.time() * 1000)

    payload, present, error = load_json(INPUT_PATH)
    source_errors = [item for item in [error] if item]

    # -----------------------------------------------------------------------
    # Policy thresholds / 策略阈值
    # -----------------------------------------------------------------------
    light_max_expected_roundtrip_ms = parse_int_env(
        LIGHT_MAX_EXPECTED_ROUNDTRIP_MS_ENV,
        DEFAULT_LIGHT_MAX_EXPECTED_ROUNDTRIP_MS,
    )
    standard_max_expected_roundtrip_ms = parse_int_env(
        STANDARD_MAX_EXPECTED_ROUNDTRIP_MS_ENV,
        DEFAULT_STANDARD_MAX_EXPECTED_ROUNDTRIP_MS,
    )
    light_max_per_call_budget_usd = parse_float_env(
        LIGHT_MAX_PER_CALL_BUDGET_USD_ENV,
        DEFAULT_LIGHT_MAX_PER_CALL_BUDGET_USD,
    )
    standard_max_per_call_budget_usd = parse_float_env(
        STANDARD_MAX_PER_CALL_BUDGET_USD_ENV,
        DEFAULT_STANDARD_MAX_PER_CALL_BUDGET_USD,
    )
    runtime_soft_max_age_ms = parse_int_env(
        RUNTIME_SOFT_MAX_AGE_MS_ENV,
        DEFAULT_RUNTIME_SOFT_MAX_AGE_MS,
    )

    # -----------------------------------------------------------------------
    # Safe defaults / 安全默认值
    # If the input is missing, stay fail-closed.
    # 如果输入缺失，则保持 fail-closed。
    # -----------------------------------------------------------------------
    input_state = payload.get("input_state", "unknown") if present else "missing"
    allow_progress_to_h1b_policy = bool(payload.get("allow_progress_to_h1b_policy")) if present else False

    h0_readiness = payload.get("h0_readiness", {}) if present else {}
    runtime_context = payload.get("runtime_context", {}) if present else {}
    market_context = payload.get("market_context", {}) if present else {}
    policy_inputs = payload.get("policy_inputs", {}) if present else {}
    freshness = payload.get("freshness", {}) if present else {}
    operator_flags_from_input = payload.get("operator_flags", []) if present else []

    h0_final_overall_ok = bool(h0_readiness.get("h0_final_overall_ok"))
    h0_chain_ok = bool(h0_readiness.get("h0_chain_ok"))
    progression_ready = bool(h0_readiness.get("progression_ready"))
    allow_progress_to_h1 = bool(h0_readiness.get("allow_progress_to_h1"))

    system_mode = runtime_context.get("system_mode", "unknown")
    execution_state = runtime_context.get("execution_state", "unknown")
    overall_runtime_state = runtime_context.get("overall_runtime_state", "unknown")

    ai_max_expected_roundtrip_ms = policy_inputs.get("ai_max_expected_roundtrip_ms")
    ai_per_call_budget_usd = policy_inputs.get("ai_per_call_budget_usd")

    runtime_state_age_ms = freshness.get("runtime_state_age_ms")

    warning_flags: list[str] = []
    blocking_reasons: list[str] = []

    # -----------------------------------------------------------------------
    # Step 1: hard gates / 第一步：硬阻断门
    # These conditions mean policy generation must end in "none".
    # 这些条件意味着策略层必须直接收敛为 "none"。
    # -----------------------------------------------------------------------
    if not present:
        blocking_reasons.append("thought_gate_input_missing")
    if input_state != "ready_for_thought_gate_policy_evaluation":
        blocking_reasons.append("input_state_not_ready")
    if not allow_progress_to_h1b_policy:
        blocking_reasons.append("h1a_policy_gate_not_open")
    if not h0_final_overall_ok or not h0_chain_ok or not progression_ready or not allow_progress_to_h1:
        blocking_reasons.append("h0_not_ready")
    if system_mode != "read_only":
        blocking_reasons.append("runtime_not_read_only")
    if execution_state != "disabled":
        blocking_reasons.append("execution_not_disabled")

    # -----------------------------------------------------------------------
    # Step 2: derive budget/latency tier cap
    # 第二步：根据预算/延迟上限，推导允许的最大 AI 档位
    # -----------------------------------------------------------------------
    budget_latency_cap = "none"

    try:
        ai_ms = int(ai_max_expected_roundtrip_ms)
        ai_budget = float(ai_per_call_budget_usd)
        if ai_ms <= light_max_expected_roundtrip_ms and ai_budget <= light_max_per_call_budget_usd:
            budget_latency_cap = "light"
        elif ai_ms <= standard_max_expected_roundtrip_ms and ai_budget <= standard_max_per_call_budget_usd:
            budget_latency_cap = "standard"
        else:
            blocking_reasons.append("budget_latency_cap_unacceptable")
    except (TypeError, ValueError):
        blocking_reasons.append("budget_latency_inputs_invalid")

    # -----------------------------------------------------------------------
    # Step 3: soft warnings / 第三步：软警告
    # Warnings do not necessarily block, but can downgrade standard -> light.
    # 软警告不一定阻断，但可以把 standard 降级为 light。
    # -----------------------------------------------------------------------
    if isinstance(runtime_state_age_ms, int) and runtime_state_age_ms > runtime_soft_max_age_ms:
        warning_flags.append("runtime_state_reference_old")
    warning_flags = prune_freshness_warning_flags(locals(), warning_flags)

    if "recent_trade_last_price_missing" in operator_flags_from_input:
        warning_flags.append("recent_trade_last_price_missing")
    if "recent_trade_last_ts_missing" in operator_flags_from_input:
        warning_flags.append("recent_trade_last_ts_missing")

    spread_bps = market_context.get("spread_bps")
    volatility_bps = market_context.get("volatility_bps")
    slippage_buy_bps = market_context.get("slippage_buy_bps_for_test_notional")
    slippage_sell_bps = market_context.get("slippage_sell_bps_for_test_notional")

    soft_max_spread_bps = policy_inputs.get("soft_max_spread_bps")
    soft_max_volatility_bps = policy_inputs.get("soft_max_volatility_bps")
    soft_max_slippage_bps = policy_inputs.get("soft_max_slippage_bps")

    try:
        if spread_bps is not None and soft_max_spread_bps is not None:
            if float(spread_bps) > float(soft_max_spread_bps):
                warning_flags.append("spread_above_soft_cap")
    except (TypeError, ValueError):
        warning_flags.append("spread_comparison_error")

    try:
        if volatility_bps is not None and soft_max_volatility_bps is not None:
            if float(volatility_bps) > float(soft_max_volatility_bps):
                warning_flags.append("volatility_above_soft_cap")
    except (TypeError, ValueError):
        warning_flags.append("volatility_comparison_error")

    try:
        if slippage_buy_bps is not None and soft_max_slippage_bps is not None:
            if float(slippage_buy_bps) > float(soft_max_slippage_bps):
                warning_flags.append("buy_slippage_above_soft_cap")
    except (TypeError, ValueError):
        warning_flags.append("buy_slippage_comparison_error")

    try:
        if slippage_sell_bps is not None and soft_max_slippage_bps is not None:
            if float(slippage_sell_bps) > float(soft_max_slippage_bps):
                warning_flags.append("sell_slippage_above_soft_cap")
    except (TypeError, ValueError):
        warning_flags.append("sell_slippage_comparison_error")

    # -----------------------------------------------------------------------
    # Step 4: data-quality tier cap / 第四步：数据质量 tier 上限
    # A small data-quality defect should usually downgrade to light, not always
    # fully block the system.
    # 轻微数据质量缺陷通常先降级到 light，而不是直接全阻断。
    # -----------------------------------------------------------------------
    data_quality_cap = "standard"
    if warning_flags:
        data_quality_cap = "light"

    # -----------------------------------------------------------------------
    # Step 5: final policy state / 第五步：最终策略状态
    # -----------------------------------------------------------------------
    if blocking_reasons:
        max_ai_call_tier = "none"
        policy_state = "policy_blocked"
        allow_progress_to_h1c_decision = False
        recommended_action = "repair_blockers_before_h1c"
    else:
        max_ai_call_tier = tighter_tier(budget_latency_cap, data_quality_cap)
        if max_ai_call_tier == "standard":
            policy_state = "policy_ready_standard_allowed"
            allow_progress_to_h1c_decision = True
            recommended_action = "may_progress_to_h1c_decision"
        elif max_ai_call_tier == "light":
            policy_state = "policy_ready_light_only"
            allow_progress_to_h1c_decision = True
            recommended_action = "may_progress_to_h1c_with_light_ai_only"
        else:
            policy_state = "policy_blocked"
            allow_progress_to_h1c_decision = False
            recommended_action = "repair_budget_latency_constraints"

    return {
        "policy_type": "bybit_thought_gate_policy",
        "policy_version": "v1",
        "ts_ms": ts_ms,
        "exchange": "bybit",
        "stage": "H1-B",
        "report_ok": True,
        "source_refs": {
            "thought_gate_input_path": str(INPUT_PATH),
        },
        "source_integrity": {
            "thought_gate_input_present": present,
            "source_errors": source_errors,
        },
        "input_summary": {
            "input_state": input_state,
            "allow_progress_to_h1b_policy": allow_progress_to_h1b_policy,
            "overall_runtime_state": overall_runtime_state,
            "system_mode": system_mode,
            "execution_state": execution_state,
        },
        "policy_thresholds": {
            "light_max_expected_roundtrip_ms": light_max_expected_roundtrip_ms,
            "standard_max_expected_roundtrip_ms": standard_max_expected_roundtrip_ms,
            "light_max_per_call_budget_usd": light_max_per_call_budget_usd,
            "standard_max_per_call_budget_usd": standard_max_per_call_budget_usd,
            "runtime_soft_max_age_ms": runtime_soft_max_age_ms,
            "source_map": {
                "light_max_expected_roundtrip_ms": f"env:{LIGHT_MAX_EXPECTED_ROUNDTRIP_MS_ENV}",
                "standard_max_expected_roundtrip_ms": f"env:{STANDARD_MAX_EXPECTED_ROUNDTRIP_MS_ENV}",
                "light_max_per_call_budget_usd": f"env:{LIGHT_MAX_PER_CALL_BUDGET_USD_ENV}",
                "standard_max_per_call_budget_usd": f"env:{STANDARD_MAX_PER_CALL_BUDGET_USD_ENV}",
                "runtime_soft_max_age_ms": f"env:{RUNTIME_SOFT_MAX_AGE_MS_ENV}",
            },
        },
        "tier_caps": {
            "budget_latency_cap": budget_latency_cap,
            "data_quality_cap": data_quality_cap,
            "final_max_ai_call_tier": max_ai_call_tier,
        },
        "warning_flags": warning_flags,
        "blocking_reasons": blocking_reasons,
        "policy_state": policy_state,
        "allow_progress_to_h1c_decision": allow_progress_to_h1c_decision,
        "recommended_action": recommended_action,
        "operator_message": (
            "H1-B thought gate policy built. This object defines the maximum "
            "allowed AI participation tier under current latency, budget, "
            "runtime, and data-quality constraints."
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
