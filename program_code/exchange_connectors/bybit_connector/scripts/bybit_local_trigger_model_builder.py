#!/usr/bin/env python3
"""
MODULE_NOTE / 模块说明:
- role / 角色:
  H2 local trigger model builder / H2 本地触发模型构建器。

- purpose / 目的:
  Consume H1-A thought-gate input and H1-B policy output, then build one
  deterministic, auditable local trigger model result describing whether the
  current cycle is interesting enough to justify AI escalation.
  消费 H1-A thought-gate 输入与 H1-B policy 输出，构建一个确定性、可审计的
  本地触发模型结果，用来判断当前这一轮是否足够“值得”升级到 AI 分析层。

- upstream / 上游输入:
  1) runtime/bybit/thought_gate/bybit_thought_gate_input_latest.json
  2) runtime/bybit/thought_gate/bybit_thought_gate_policy_latest.json

- output / 输出:
  runtime/bybit/trigger_model/bybit_local_trigger_model_latest.json

- notes / 备注:
  1) This module does NOT authorize trading.
     本模块不会授权交易。
  2) This module does NOT call AI.
     本模块不会调用 AI。
  3) This module only answers:
     "Is this cycle locally interesting enough to spend AI latency and budget?"
     本模块只回答一个问题：
     “这一轮是否在本地上看起来足够值得消耗 AI 的延迟与预算？”
  4) v1 is intentionally conservative and deterministic.
     v1 版本故意保持保守且确定性。
"""

from __future__ import annotations
from bybit_mainline_cleanup_helpers import normalize_recent_trade_fields, prune_freshness_warning_flags

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
TRIGGER_DIR = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/trigger_model"
)

INPUT_PATH = THOUGHT_GATE_DIR / "bybit_thought_gate_input_latest.json"
POLICY_PATH = THOUGHT_GATE_DIR / "bybit_thought_gate_policy_latest.json"
LATEST_OUTPUT_PATH = TRIGGER_DIR / "bybit_local_trigger_model_latest.json"


# ---------------------------------------------------------------------------
# Env knobs / 环境变量参数
# These parameters define when a market condition is good enough to be worth
# escalating to AI review.
# 这些参数定义：什么样的市场状态“值得”升级到 AI 审查。
# ---------------------------------------------------------------------------

MIN_VOLATILITY_BPS_ENV = "BYBIT_H2_MIN_VOLATILITY_BPS"
MAX_VOLATILITY_BPS_ENV = "BYBIT_H2_MAX_VOLATILITY_BPS"
MAX_SPREAD_BPS_ENV = "BYBIT_H2_MAX_SPREAD_BPS"
MAX_SLIPPAGE_BPS_ENV = "BYBIT_H2_MAX_SLIPPAGE_BPS"
MIN_RECENT_TRADE_COUNT_ENV = "BYBIT_H2_MIN_RECENT_TRADE_COUNT"
TRIGGER_SCORE_THRESHOLD_ENV = "BYBIT_H2_TRIGGER_SCORE_THRESHOLD"
MIN_MARKET_QUALITY_SCORE_ENV = "BYBIT_H2_MIN_MARKET_QUALITY_SCORE"

DEFAULT_MIN_VOLATILITY_BPS = 5.0
DEFAULT_MAX_VOLATILITY_BPS = 40.0
DEFAULT_MAX_SPREAD_BPS = 1.0
DEFAULT_MAX_SLIPPAGE_BPS = 2.0
DEFAULT_MIN_RECENT_TRADE_COUNT = 20
DEFAULT_TRIGGER_SCORE_THRESHOLD = 70
DEFAULT_MIN_MARKET_QUALITY_SCORE = 70

ALLOWED_POLICY_READY_STATES = {
    "policy_ready_light_only",
    "policy_ready_standard_allowed",
}

ALLOWED_AI_TIERS = {
    "none",
    "light",
    "standard",
}

ALLOWED_TRIGGER_STATES = {
    "blocked_not_policy_ready",
    "not_triggered_insufficient_market_quality",
    "not_triggered_low_regime_interest",
    "triggered_light_ai_review",
    "triggered_standard_ai_review",
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


def safe_float(value: Any) -> float | None:
    """
    Safely convert to float.
    安全转换为浮点数。
    """
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def save_report(report: dict[str, Any]) -> tuple[Path, Path]:
    """
    Save latest and dated trigger reports.
    保存 latest 与按时间戳归档的 trigger report。
    """
    TRIGGER_DIR.mkdir(parents=True, exist_ok=True)
    latest_path = LATEST_OUTPUT_PATH
    dated_path = TRIGGER_DIR / f"bybit_local_trigger_model_{report['ts_ms']}.json"
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    latest_path.write_text(serialized, encoding="utf-8")
    dated_path.write_text(serialized, encoding="utf-8")
    return latest_path, dated_path


# ---------------------------------------------------------------------------
# Main builder / 主构建逻辑
# ---------------------------------------------------------------------------

def build_report() -> dict[str, Any]:
    """
    Build one deterministic H2 local trigger model report.
    构建一份确定性的 H2 本地触发模型报告。
    """
    ts_ms = int(time.time() * 1000)

    input_payload, input_present, input_error = load_json(INPUT_PATH)
    policy_payload, policy_present, policy_error = load_json(POLICY_PATH)

    source_errors = [
        item
        for item in [input_error, policy_error]
        if item
    ]

    # -----------------------------------------------------------------------
    # Threshold configuration / 阈值配置
    # -----------------------------------------------------------------------
    min_volatility_bps = parse_float_env(
        MIN_VOLATILITY_BPS_ENV,
        DEFAULT_MIN_VOLATILITY_BPS,
    )
    max_volatility_bps = parse_float_env(
        MAX_VOLATILITY_BPS_ENV,
        DEFAULT_MAX_VOLATILITY_BPS,
    )
    max_spread_bps = parse_float_env(
        MAX_SPREAD_BPS_ENV,
        DEFAULT_MAX_SPREAD_BPS,
    )
    max_slippage_bps = parse_float_env(
        MAX_SLIPPAGE_BPS_ENV,
        DEFAULT_MAX_SLIPPAGE_BPS,
    )
    min_recent_trade_count = parse_int_env(
        MIN_RECENT_TRADE_COUNT_ENV,
        DEFAULT_MIN_RECENT_TRADE_COUNT,
    )
    trigger_score_threshold = parse_int_env(
        TRIGGER_SCORE_THRESHOLD_ENV,
        DEFAULT_TRIGGER_SCORE_THRESHOLD,
    )
    min_market_quality_score = parse_int_env(
        MIN_MARKET_QUALITY_SCORE_ENV,
        DEFAULT_MIN_MARKET_QUALITY_SCORE,
    )

    # -----------------------------------------------------------------------
    # Input extraction / 输入抽取
    # -----------------------------------------------------------------------
    input_state = input_payload.get("input_state", "unknown") if input_present else "missing"
    policy_state = policy_payload.get("policy_state", "unknown") if policy_present else "missing"

    allow_progress_to_h1b_policy = bool(
        input_payload.get("allow_progress_to_h1b_policy")
    ) if input_present else False
    allow_progress_to_h1c_decision = bool(
        policy_payload.get("allow_progress_to_h1c_decision")
    ) if policy_present else False

    tier_caps = policy_payload.get("tier_caps", {}) if policy_present else {}
    policy_max_ai_call_tier = tier_caps.get("final_max_ai_call_tier", "none")
    if policy_max_ai_call_tier not in ALLOWED_AI_TIERS:
        policy_max_ai_call_tier = "none"

    market_context = input_payload.get("market_context", {}) if input_present else {}
    operator_flags_from_input = input_payload.get("operator_flags", []) if input_present else []
    warning_flags_from_policy = policy_payload.get("warning_flags", []) if policy_present else []
    blocking_reasons_from_policy = policy_payload.get("blocking_reasons", []) if policy_present else []

    spread_bps = safe_float(market_context.get("spread_bps"))
    volatility_bps = safe_float(market_context.get("volatility_bps"))
    slippage_buy_bps = safe_float(market_context.get("slippage_buy_bps_for_test_notional"))
    slippage_sell_bps = safe_float(market_context.get("slippage_sell_bps_for_test_notional"))
    recent_trade_count = market_context.get("recent_trade_count")
    volatility_band = market_context.get("volatility_band")
    last_trade_price = market_context.get("last_trade_price")
    last_trade_ts_ms = market_context.get("last_trade_ts_ms")

    coverage = market_context.get("coverage", {})
    best_bid_ask_present = bool(coverage.get("best_bid_ask_present"))
    orderbook_depth_present = bool(coverage.get("orderbook_depth_present"))
    recent_trade_tape_present = bool(coverage.get("recent_trade_tape_present"))
    volatility_band_present = bool(coverage.get("volatility_band_present"))
    slippage_proxy_present = bool(coverage.get("slippage_proxy_present"))

    # -----------------------------------------------------------------------
    # Hard blockers / 硬阻断条件
    # -----------------------------------------------------------------------
    blocking_reasons: list[str] = []
    warning_flags: list[str] = []

    if not input_present:
        blocking_reasons.append("thought_gate_input_missing")
    if not policy_present:
        blocking_reasons.append("thought_gate_policy_missing")
    if input_state != "ready_for_thought_gate_policy_evaluation":
        blocking_reasons.append("input_state_not_ready")
    if policy_state not in ALLOWED_POLICY_READY_STATES:
        blocking_reasons.append("policy_state_not_ready")
    if not allow_progress_to_h1b_policy:
        blocking_reasons.append("input_policy_gate_not_open")
    if not allow_progress_to_h1c_decision:
        blocking_reasons.append("policy_h1c_gate_not_open")
    if policy_max_ai_call_tier == "none":
        blocking_reasons.append("policy_ai_tier_none")

    for item in blocking_reasons_from_policy:
        if item not in blocking_reasons:
            blocking_reasons.append(f"policy_upstream:{item}")

    # -----------------------------------------------------------------------
    # Feature completeness / 特征完整性
    # -----------------------------------------------------------------------
    coverage_complete = all(
        [
            best_bid_ask_present,
            orderbook_depth_present,
            recent_trade_tape_present,
            volatility_band_present,
            slippage_proxy_present,
        ]
    )

    try:
        recent_trade_count_int = int(recent_trade_count)
    except (TypeError, ValueError):
        recent_trade_count_int = 0

    recent_trade_count_sufficient = recent_trade_count_int >= min_recent_trade_count

    last_trade_fields_present = (
        last_trade_price is not None and last_trade_ts_ms is not None
    )

    if not last_trade_fields_present:
        warning_flags.append("last_trade_fields_missing")

    for item in operator_flags_from_input:
        if item not in warning_flags:
            warning_flags.append(item)
    for item in warning_flags_from_policy:
        if item not in warning_flags:
            warning_flags.append(item)

    # -----------------------------------------------------------------------
    # Score 1: market quality / 分数一：市场质量分
    # This measures whether the market data is clean and tradable enough.
    # 这个分数衡量市场数据是否足够干净、足够可交易。
    # -----------------------------------------------------------------------
    market_quality_score = 0

    if coverage_complete:
        market_quality_score += 30
    else:
        warning_flags.append("coverage_incomplete")

    if spread_bps is not None and spread_bps <= max_spread_bps:
        market_quality_score += 20
    else:
        warning_flags.append("spread_above_trigger_cap_or_missing")

    max_slippage_observed = None
    if slippage_buy_bps is not None or slippage_sell_bps is not None:
        candidates = [x for x in [slippage_buy_bps, slippage_sell_bps] if x is not None]
        if candidates:
            max_slippage_observed = max(candidates)

    if max_slippage_observed is not None and max_slippage_observed <= max_slippage_bps:
        market_quality_score += 20
    else:
        warning_flags.append("slippage_above_trigger_cap_or_missing")

    if recent_trade_count_sufficient:
        market_quality_score += 15
    else:
        warning_flags.append("recent_trade_count_below_trigger_minimum")

    # Freshness/data pipeline warnings should reduce enthusiasm, but not always hard-block.
    # 新鲜度/数据链路警告应降低积极性，但不总是硬阻断。

    stale_like_flags = {
        "runtime_state_reference_old",
        "public_microstructure_stale",
        "h0_final_audit_stale",
    }
    if any(flag in stale_like_flags for flag in warning_flags):
        warning_flags.append("freshness_soft_warning_present")
    else:
        market_quality_score += 15

    # -----------------------------------------------------------------------
    # Score 2: regime interest / 分数二：行情兴趣分
    # This measures whether the current regime is interesting enough to spend
    # AI latency and money on.
    # 这个分数衡量当前行情状态是否“值得”花 AI 的时间与预算。
    # -----------------------------------------------------------------------
    regime_interest_score = 0

    if volatility_bps is not None and min_volatility_bps <= volatility_bps <= max_volatility_bps:
        regime_interest_score += 35
    else:
        warning_flags.append("volatility_outside_trigger_band_or_missing")

    if volatility_band in {"moderate", "high"}:
        regime_interest_score += 20
    else:
        warning_flags.append("volatility_band_not_preferred")

    if spread_bps is not None and spread_bps <= max_spread_bps:
        regime_interest_score += 15

    if max_slippage_observed is not None and max_slippage_observed <= max_slippage_bps:
        regime_interest_score += 15

    if recent_trade_count_sufficient:
        regime_interest_score += 15

    # -----------------------------------------------------------------------
    # Final trigger score / 最终触发分
    # We take the minimum of the two scores to remain conservative.
    # 为保持保守，我们取两个分数中的较小值。
    # -----------------------------------------------------------------------
    total_trigger_score = min(market_quality_score, regime_interest_score)

    # -----------------------------------------------------------------------
    # Final state / 最终状态
    # -----------------------------------------------------------------------
    if blocking_reasons:
        trigger_state = "blocked_not_policy_ready"
        should_trigger_ai_review = False
        suggested_ai_tier = "none"
        recommended_action = "repair_h1_or_policy_blockers"
    elif market_quality_score < min_market_quality_score:
        trigger_state = "not_triggered_insufficient_market_quality"
        should_trigger_ai_review = False
        suggested_ai_tier = "none"
        recommended_action = "improve_market_quality_before_ai_review"
    elif total_trigger_score < trigger_score_threshold:
        trigger_state = "not_triggered_low_regime_interest"
        should_trigger_ai_review = False
        suggested_ai_tier = "none"
        recommended_action = "wait_for_more_interesting_local_regime"
    else:
        should_trigger_ai_review = True
        suggested_ai_tier = policy_max_ai_call_tier
        if policy_max_ai_call_tier == "standard":
            trigger_state = "triggered_standard_ai_review"
        else:
            trigger_state = "triggered_light_ai_review"
        recommended_action = "may_return_to_h1c_with_real_trigger_model"

    if trigger_state not in ALLOWED_TRIGGER_STATES:
        trigger_state = "blocked_not_policy_ready"
        should_trigger_ai_review = False
        suggested_ai_tier = "none"
        if "invalid_trigger_state_generated" not in blocking_reasons:
            blocking_reasons.append("invalid_trigger_state_generated")
        recommended_action = "repair_h2_trigger_builder_logic"

    warning_flags = prune_freshness_warning_flags(locals(), warning_flags)

    return {
        "trigger_type": "bybit_local_trigger_model",
        "trigger_version": "v1",
        "ts_ms": ts_ms,
        "exchange": "bybit",
        "stage": "H2-A",
        "report_ok": True,
        "source_refs": {
            "thought_gate_input_path": str(INPUT_PATH),
            "thought_gate_policy_path": str(POLICY_PATH),
        },
        "source_integrity": {
            "thought_gate_input_present": input_present,
            "thought_gate_policy_present": policy_present,
            "source_errors": source_errors,
        },
        "input_summary": {
            "input_state": input_state,
            "policy_state": policy_state,
            "policy_max_ai_call_tier": policy_max_ai_call_tier,
        },
        "trigger_thresholds": {
            "min_volatility_bps": min_volatility_bps,
            "max_volatility_bps": max_volatility_bps,
            "max_spread_bps": max_spread_bps,
            "max_slippage_bps": max_slippage_bps,
            "min_recent_trade_count": min_recent_trade_count,
            "trigger_score_threshold": trigger_score_threshold,
            "min_market_quality_score": min_market_quality_score,
            "source_map": {
                "min_volatility_bps": f"env:{MIN_VOLATILITY_BPS_ENV}",
                "max_volatility_bps": f"env:{MAX_VOLATILITY_BPS_ENV}",
                "max_spread_bps": f"env:{MAX_SPREAD_BPS_ENV}",
                "max_slippage_bps": f"env:{MAX_SLIPPAGE_BPS_ENV}",
                "min_recent_trade_count": f"env:{MIN_RECENT_TRADE_COUNT_ENV}",
                "trigger_score_threshold": f"env:{TRIGGER_SCORE_THRESHOLD_ENV}",
                "min_market_quality_score": f"env:{MIN_MARKET_QUALITY_SCORE_ENV}",
            },
        },
        "feature_snapshot": {
            "spread_bps": spread_bps,
            "volatility_bps": volatility_bps,
            "volatility_band": volatility_band,
            "slippage_buy_bps_for_test_notional": slippage_buy_bps,
            "slippage_sell_bps_for_test_notional": slippage_sell_bps,
            "max_slippage_observed_bps": max_slippage_observed,
            "recent_trade_count": recent_trade_count_int,
            "coverage_complete": coverage_complete,
            "recent_trade_count_sufficient": recent_trade_count_sufficient,
            "last_trade_fields_present": last_trade_fields_present,
        },
        "scores": {
            "market_quality_score": market_quality_score,
            "regime_interest_score": regime_interest_score,
            "total_trigger_score": total_trigger_score,
        },
        

        "warning_flags": warning_flags,
        "blocking_reasons": blocking_reasons,
        "trigger_state": trigger_state,
        "should_trigger_ai_review": should_trigger_ai_review,
        "suggested_ai_tier": suggested_ai_tier,
        "recommended_action": recommended_action,
        "operator_message": (
            "H2-A local trigger model built. This object decides whether the "
            "current cycle is locally interesting enough to justify spending "
            "AI latency and budget, but it still does not authorize trading."
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
