#!/usr/bin/env python3
"""
MODULE_NOTE / 模块说明:
- role / 角色:
  H1 thought gate input builder / H1 思考门输入构建器。

- purpose / 目的:
  Aggregate H0 final handoff status, runtime health, local cost model,
  public microstructure, and operator-configured AI latency/budget knobs into
  one auditable input object for later H1 policy and decision layers.
  将 H0 最终交接状态、运行时健康状态、本地成本模型、公共微观结构、
  以及操作员配置的 AI 延迟/预算参数，统一汇总为一个可审计输入对象，
  供后续 H1 policy / decision 层消费。

- upstream / 上游输入:
  1) runtime/bybit/local_judgment/bybit_local_trade_eligibility_handoff_latest.json
  2) runtime/bybit/local_judgment/bybit_local_judgment_final_audit_latest.json
  3) runtime/bybit/bybit_runtime_state_latest.json
  4) runtime/bybit/bybit_readonly_audit_latest.json
  5) runtime/bybit/bybit_latest_consistency_latest.json
  6) decision_packets/bybit/bybit_decision_packet_latest.json
  7) runtime/bybit/local_judgment/bybit_local_cost_model_latest.json
  8) runtime/bybit/local_judgment/bybit_public_microstructure_latest.json
  9) runtime/bybit/local_judgment/bybit_local_market_friction_latest.json
  10) runtime/bybit/local_judgment/bybit_local_risk_envelope_latest.json
  11) runtime/bybit/local_judgment/bybit_local_trade_eligibility_latest.json

- output / 输出:
  runtime/bybit/thought_gate/bybit_thought_gate_input_latest.json

- notes / 备注:
  1) This module does NOT decide whether AI should be called.
     本模块不负责最终判断“是否调用 AI”。
  2) This module only prepares normalized, auditable, freshness-aware inputs.
     本模块只负责准备标准化、可审计、带新鲜度信息的输入对象。
  3) Later H1-B / H1-C will consume this object to decide:
     后续 H1-B / H1-C 将基于此对象决定：
     - whether AI is allowed / 是否允许调用 AI
     - whether AI is worthwhile / 是否值得调用 AI
     - what call intensity is allowed / 允许什么级别的 AI 调用
"""

from __future__ import annotations
from bybit_mainline_cleanup_helpers import normalize_recent_trade_fields, prune_freshness_warning_flags

import json
import os
import time
from pathlib import Path

from bybit_path_policy import get_thought_gate_runtime_dir
from typing import Any

# ---------------------------------------------------------------------------
# Path constants / 路径常量
# ---------------------------------------------------------------------------

LOCAL_JUDGMENT_DIR = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/local_judgment"
)
THOUGHT_GATE_DIR = Path(
    str(get_thought_gate_runtime_dir())
)

HANDOFF_PATH = LOCAL_JUDGMENT_DIR / "bybit_local_trade_eligibility_handoff_latest.json"
H0_FINAL_AUDIT_PATH = LOCAL_JUDGMENT_DIR / "bybit_local_judgment_final_audit_latest.json"
RUNTIME_STATE_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json"
)
READONLY_AUDIT_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_readonly_audit_latest.json"
)
LATEST_CONSISTENCY_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_latest_consistency_latest.json"
)
DECISION_PACKET_PATH = Path(
    "/home/ncyu/srv/docker_projects/trading_services/decision_packets/bybit/bybit_decision_packet_latest.json"
)
COST_MODEL_PATH = LOCAL_JUDGMENT_DIR / "bybit_local_cost_model_latest.json"
PUBLIC_MICROSTRUCTURE_PATH = LOCAL_JUDGMENT_DIR / "bybit_public_microstructure_latest.json"
MARKET_FRICTION_PATH = LOCAL_JUDGMENT_DIR / "bybit_local_market_friction_latest.json"
RISK_ENVELOPE_PATH = LOCAL_JUDGMENT_DIR / "bybit_local_risk_envelope_latest.json"
TRADE_ELIGIBILITY_PATH = LOCAL_JUDGMENT_DIR / "bybit_local_trade_eligibility_latest.json"

LATEST_OUTPUT_PATH = THOUGHT_GATE_DIR / "bybit_thought_gate_input_latest.json"

# ---------------------------------------------------------------------------
# Env knob names / 环境变量名称
# These are operator-tunable policy inputs. H1-A only records them.
# 这些是操作员可调的策略输入。H1-A 只负责记录，不负责最终裁决。
# ---------------------------------------------------------------------------

AI_MAX_EXPECTED_ROUNDTRIP_MS_ENV = "BYBIT_AI_MAX_EXPECTED_ROUNDTRIP_MS"
AI_DAILY_BUDGET_USD_ENV = "BYBIT_AI_DAILY_BUDGET_USD"
AI_PER_CALL_BUDGET_USD_ENV = "BYBIT_AI_PER_CALL_BUDGET_USD"

THOUGHT_GATE_MAX_PUBLIC_DATA_AGE_MS_ENV = "BYBIT_THOUGHT_GATE_MAX_PUBLIC_DATA_AGE_MS"
THOUGHT_GATE_MAX_H0_AUDIT_AGE_MS_ENV = "BYBIT_THOUGHT_GATE_MAX_H0_AUDIT_AGE_MS"
THOUGHT_GATE_SOFT_MAX_SPREAD_BPS_ENV = "BYBIT_THOUGHT_GATE_SOFT_MAX_SPREAD_BPS"
THOUGHT_GATE_SOFT_MAX_VOLATILITY_BPS_ENV = "BYBIT_THOUGHT_GATE_SOFT_MAX_VOLATILITY_BPS"
THOUGHT_GATE_SOFT_MAX_SLIPPAGE_BPS_ENV = "BYBIT_THOUGHT_GATE_SOFT_MAX_SLIPPAGE_BPS"

DEFAULT_AI_MAX_EXPECTED_ROUNDTRIP_MS = 2500
DEFAULT_AI_DAILY_BUDGET_USD = 5.0
DEFAULT_AI_PER_CALL_BUDGET_USD = 0.05

DEFAULT_MAX_PUBLIC_DATA_AGE_MS = 15_000
DEFAULT_MAX_H0_AUDIT_AGE_MS = 15_000
DEFAULT_SOFT_MAX_SPREAD_BPS = 3.0
DEFAULT_SOFT_MAX_VOLATILITY_BPS = 50.0
DEFAULT_SOFT_MAX_SLIPPAGE_BPS = 5.0

# ---------------------------------------------------------------------------
# Helpers / 辅助函数
# ---------------------------------------------------------------------------

def load_json(path: Path) -> tuple[dict[str, Any], bool, str | None]:
    """
    Load one JSON file from disk.
    从磁盘加载一个 JSON 文件。

    Returns / 返回:
    - payload dict / 数据字典
    - present bool / 文件是否存在且可读取
    - error string or None / 错误信息（若有）
    """
    if not path.exists():
        return {}, False, f"missing_file:{path}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), True, None
    except Exception as exc:  # pragma: no cover
        return {}, False, f"json_load_error:{path}:{exc}"

def parse_int_env(name: str, default: int) -> int:
    """
    Parse an integer environment variable with fallback.
    解析整数环境变量，失败时回退到默认值。
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
    Parse a float environment variable with fallback.
    解析浮点环境变量，失败时回退到默认值。
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(str(raw).strip())
    except ValueError:
        return default

def as_int(value: Any, default: int = 0) -> int:
    """
    Best-effort integer coercion.
    尽力把任意值转成整数。
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def compute_age_ms(now_ts_ms: int, source_ts_ms: Any) -> int | None:
    """
    Compute age in milliseconds.
    计算“当前时间 - 源时间戳”的毫秒年龄。

    Returns None when source timestamp is missing/invalid.
    若源时间戳不存在或非法，则返回 None。
    """
    try:
        value = int(source_ts_ms)
    except (TypeError, ValueError):
        return None
    return max(now_ts_ms - value, 0)

def save_report(report: dict[str, Any]) -> tuple[Path, Path]:
    """
    Write latest and dated reports.
    写出 latest 文件和按时间戳命名的归档文件。
    """
    THOUGHT_GATE_DIR.mkdir(parents=True, exist_ok=True)
    latest_path = LATEST_OUTPUT_PATH
    dated_path = THOUGHT_GATE_DIR / f"bybit_thought_gate_input_{report['ts_ms']}.json"
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    latest_path.write_text(serialized, encoding="utf-8")
    dated_path.write_text(serialized, encoding="utf-8")
    return latest_path, dated_path

# ---------------------------------------------------------------------------
# Main builder / 主构建逻辑
# ---------------------------------------------------------------------------

def build_report() -> dict[str, Any]:
    """
    Build one auditable H1-A input object.
    构建一份可审计的 H1-A 输入对象。
    """
    ts_ms = int(time.time() * 1000)

    handoff, handoff_present, handoff_error = load_json(HANDOFF_PATH)
    h0_final, h0_final_present, h0_final_error = load_json(H0_FINAL_AUDIT_PATH)
    runtime_state, runtime_present, runtime_error = load_json(RUNTIME_STATE_PATH)
    readonly_audit, readonly_present, readonly_error = load_json(READONLY_AUDIT_PATH)
    latest_consistency, consistency_present, consistency_error = load_json(LATEST_CONSISTENCY_PATH)
    decision_packet, packet_present, packet_error = load_json(DECISION_PACKET_PATH)
    cost_model, cost_model_present, cost_model_error = load_json(COST_MODEL_PATH)
    public_micro, public_micro_present, public_micro_error = load_json(PUBLIC_MICROSTRUCTURE_PATH)
    market_friction, friction_present, friction_error = load_json(MARKET_FRICTION_PATH)
    risk_envelope, risk_present, risk_error = load_json(RISK_ENVELOPE_PATH)
    trade_eligibility, eligibility_present, eligibility_error = load_json(TRADE_ELIGIBILITY_PATH)

    source_errors = [
        item
        for item in [
            handoff_error,
            h0_final_error,
            runtime_error,
            readonly_error,
            consistency_error,
            packet_error,
            cost_model_error,
            public_micro_error,
            friction_error,
            risk_error,
            eligibility_error,
        ]
        if item
    ]

    # -----------------------------------------------------------------------
    # Policy / budget / latency input knobs
    # 策略 / 预算 / 延迟输入参数
    # -----------------------------------------------------------------------
    ai_max_expected_roundtrip_ms = parse_int_env(
        AI_MAX_EXPECTED_ROUNDTRIP_MS_ENV,
        DEFAULT_AI_MAX_EXPECTED_ROUNDTRIP_MS,
    )
    ai_daily_budget_usd = parse_float_env(
        AI_DAILY_BUDGET_USD_ENV,
        DEFAULT_AI_DAILY_BUDGET_USD,
    )
    ai_per_call_budget_usd = parse_float_env(
        AI_PER_CALL_BUDGET_USD_ENV,
        DEFAULT_AI_PER_CALL_BUDGET_USD,
    )
    max_public_data_age_ms = parse_int_env(
        THOUGHT_GATE_MAX_PUBLIC_DATA_AGE_MS_ENV,
        DEFAULT_MAX_PUBLIC_DATA_AGE_MS,
    )
    max_h0_audit_age_ms = parse_int_env(
        THOUGHT_GATE_MAX_H0_AUDIT_AGE_MS_ENV,
        DEFAULT_MAX_H0_AUDIT_AGE_MS,
    )
    soft_max_spread_bps = parse_float_env(
        THOUGHT_GATE_SOFT_MAX_SPREAD_BPS_ENV,
        DEFAULT_SOFT_MAX_SPREAD_BPS,
    )
    soft_max_volatility_bps = parse_float_env(
        THOUGHT_GATE_SOFT_MAX_VOLATILITY_BPS_ENV,
        DEFAULT_SOFT_MAX_VOLATILITY_BPS,
    )
    soft_max_slippage_bps = parse_float_env(
        THOUGHT_GATE_SOFT_MAX_SLIPPAGE_BPS_ENV,
        DEFAULT_SOFT_MAX_SLIPPAGE_BPS,
    )

    # -----------------------------------------------------------------------
    # Extract runtime / H0 context
    # 提取运行时 / H0 状态上下文
    # -----------------------------------------------------------------------
    h0_final_overall_ok = bool(h0_final.get("overall_ok")) if h0_final_present else False
    h0_chain_ok = bool(h0_final.get("h0_chain_ok")) if h0_final_present else False
    progression_ready = bool(h0_final.get("progression_ready")) if h0_final_present else False
    final_h0_state = h0_final.get("final_h0_state", "unknown")
    final_h0_recommended_action = h0_final.get("recommended_action", "unknown")

    handoff_state = handoff.get("handoff_state", "unknown")
    allow_progress_to_h1 = bool(handoff.get("allow_progress_to_h1")) if handoff_present else False
    next_step_hint = handoff.get("next_step_hint", "unknown")

    overall_runtime_state = runtime_state.get("overall_runtime_state", "unknown")
    system_mode = runtime_state.get("system_mode", "unknown")
    observer_state = runtime_state.get("observer_state", "unknown")
    execution_state = runtime_state.get("execution_state", "unknown")
    ai_state = runtime_state.get("ai_state", "unknown")
    preflight_guard_allowed = runtime_state.get("preflight_guard_allowed")

    market_friction_state = market_friction.get("market_friction_state", "unknown")
    market_friction_allow = bool(market_friction.get("allow_progress_to_trade_path")) if friction_present else False

    risk_envelope_state = risk_envelope.get("risk_envelope_state", "unknown")
    risk_envelope_allow = bool(risk_envelope.get("allow_progress_to_eligibility")) if risk_present else False

    trade_eligibility_state = trade_eligibility.get("trade_eligibility_state", "unknown")
    allow_progress_to_thought_gate = bool(
        trade_eligibility.get("allow_progress_to_thought_gate")
    ) if eligibility_present else False

    # -----------------------------------------------------------------------
    # Extract cost / market context
    # 提取成本 / 市场上下文
    # -----------------------------------------------------------------------
    cost_config = cost_model.get("config", {}) if cost_model_present else {}
    cost_derived = cost_model.get("derived", {}) if cost_model_present else {}
    public_config = public_micro.get("config", {}) if public_micro_present else {}
    public_derived = public_micro.get("derived", {}) if public_micro_present else {}
    public_coverage = public_micro.get("coverage", {}) if public_micro_present else {}

    public_ts_ms = public_micro.get("ts_ms")
    h0_final_ts_ms = h0_final.get("ts_ms")
    runtime_ts_ms = runtime_state.get("ts_ms")
    decision_packet_ts_ms = decision_packet.get("ts_ms")

    public_micro_age_ms = compute_age_ms(ts_ms, public_ts_ms)
    h0_final_age_ms = compute_age_ms(ts_ms, h0_final_ts_ms)
    runtime_state_age_ms = compute_age_ms(ts_ms, runtime_ts_ms)
    decision_packet_age_ms = compute_age_ms(ts_ms, decision_packet_ts_ms)

    # -----------------------------------------------------------------------
    # Coarse operator flags
    # 粗粒度操作员提示标志
    # These are hints only, not final decisions.
    # 这些只是提示，不是最终 AI 调用裁决。
    # -----------------------------------------------------------------------
    operator_flags: list[str] = []

    if not h0_final_overall_ok or not h0_chain_ok:
        operator_flags.append("h0_final_not_ok")
    if not progression_ready or not allow_progress_to_h1:
        operator_flags.append("h0_not_ready_for_h1")

    if public_micro_age_ms is None:
        operator_flags.append("public_microstructure_ts_missing")
    elif public_micro_age_ms > max_public_data_age_ms:
        operator_flags.append("public_microstructure_stale")

    if h0_final_age_ms is None:
        operator_flags.append("h0_final_audit_ts_missing")
    elif h0_final_age_ms > max_h0_audit_age_ms:
        operator_flags.append("h0_final_audit_stale")

    spread_bps = public_derived.get("spread_bps")
    volatility_bps = public_derived.get("volatility_bps")
    slippage_buy_bps = public_derived.get("slippage_buy_bps_for_test_notional")
    slippage_sell_bps = public_derived.get("slippage_sell_bps_for_test_notional")

    try:
        if spread_bps is not None and float(spread_bps) > soft_max_spread_bps:
            operator_flags.append("spread_above_soft_cap")
    except (TypeError, ValueError):
        operator_flags.append("spread_parse_error")

    try:
        if volatility_bps is not None and float(volatility_bps) > soft_max_volatility_bps:
            operator_flags.append("volatility_above_soft_cap")
    except (TypeError, ValueError):
        operator_flags.append("volatility_parse_error")

    try:
        if slippage_buy_bps is not None and float(slippage_buy_bps) > soft_max_slippage_bps:
            operator_flags.append("buy_slippage_above_soft_cap")
    except (TypeError, ValueError):
        operator_flags.append("buy_slippage_parse_error")

    try:
        if slippage_sell_bps is not None and float(slippage_sell_bps) > soft_max_slippage_bps:
            operator_flags.append("sell_slippage_above_soft_cap")
    except (TypeError, ValueError):
        operator_flags.append("sell_slippage_parse_error")

    if not bool(public_coverage.get("best_bid_ask_present", False)):
        operator_flags.append("best_bid_ask_missing")
    if not bool(public_coverage.get("orderbook_depth_present", False)):
        operator_flags.append("orderbook_depth_missing")
    if not bool(public_coverage.get("recent_trade_tape_present", False)):
        operator_flags.append("recent_trade_tape_missing")
    _last_trade_price = public_derived.get("last_trade_price")
    _last_trade_ts_ms = public_derived.get("last_trade_ts_ms")
    if _last_trade_price is None or _last_trade_ts_ms is None:
        _rehydrated_trade = normalize_recent_trade_fields(
            locals(),
            explicit_price=_last_trade_price,
            explicit_ts_ms=_last_trade_ts_ms,
        )
        _last_trade_price = _rehydrated_trade.get("price")
        _last_trade_ts_ms = _rehydrated_trade.get("ts_ms")

    if _last_trade_price is None:
        operator_flags.append("recent_trade_last_price_missing")
    if _last_trade_ts_ms is None:
        operator_flags.append("recent_trade_last_ts_missing")

    # -----------------------------------------------------------------------
    # Coarse input state / 粗粒度输入状态
    # This is NOT the final thought-gate decision.
    # 这不是最终的 thought-gate 决策，只是 H1-A 输入状态。
    # -----------------------------------------------------------------------
    if source_errors:
        input_state = "blocked_missing_sources"
        allow_progress_to_h1b_policy = False
    elif not h0_final_overall_ok or not h0_chain_ok or not progression_ready or not allow_progress_to_h1:
        input_state = "blocked_h0_not_ready"
        allow_progress_to_h1b_policy = False
    elif public_micro_age_ms is not None and public_micro_age_ms > max_public_data_age_ms:
        input_state = "blocked_stale_public_microstructure"
        allow_progress_to_h1b_policy = False
    elif h0_final_age_ms is not None and h0_final_age_ms > max_h0_audit_age_ms:
        input_state = "blocked_stale_h0_final_audit"
        allow_progress_to_h1b_policy = False
    else:
        input_state = "ready_for_thought_gate_policy_evaluation"
        allow_progress_to_h1b_policy = True

    operator_flags = prune_freshness_warning_flags(locals(), operator_flags)

    return {
        "input_type": "bybit_thought_gate_input",
        "input_version": "v1",
        "ts_ms": ts_ms,
        "exchange": "bybit",
        "stage": "H1-A",
        "report_ok": True,
        "source_refs": {
            "handoff_path": str(HANDOFF_PATH),
            "h0_final_audit_path": str(H0_FINAL_AUDIT_PATH),
            "runtime_state_path": str(RUNTIME_STATE_PATH),
            "readonly_audit_path": str(READONLY_AUDIT_PATH),
            "latest_consistency_path": str(LATEST_CONSISTENCY_PATH),
            "decision_packet_path": str(DECISION_PACKET_PATH),
            "cost_model_path": str(COST_MODEL_PATH),
            "public_microstructure_path": str(PUBLIC_MICROSTRUCTURE_PATH),
            "market_friction_path": str(MARKET_FRICTION_PATH),
            "risk_envelope_path": str(RISK_ENVELOPE_PATH),
            "trade_eligibility_path": str(TRADE_ELIGIBILITY_PATH),
        },
        "source_integrity": {
            "handoff_present": handoff_present,
            "h0_final_present": h0_final_present,
            "runtime_present": runtime_present,
            "readonly_audit_present": readonly_present,
            "latest_consistency_present": consistency_present,
            "decision_packet_present": packet_present,
            "cost_model_present": cost_model_present,
            "public_microstructure_present": public_micro_present,
            "market_friction_present": friction_present,
            "risk_envelope_present": risk_present,
            "trade_eligibility_present": eligibility_present,
            "source_errors": source_errors,
        },
        "h0_readiness": {
            "h0_final_overall_ok": h0_final_overall_ok,
            "h0_chain_ok": h0_chain_ok,
            "progression_ready": progression_ready,
            "final_h0_state": final_h0_state,
            "final_h0_recommended_action": final_h0_recommended_action,
            "handoff_state": handoff_state,
            "allow_progress_to_h1": allow_progress_to_h1,
            "handoff_next_step_hint": next_step_hint,
        },
        "runtime_context": {
            "overall_runtime_state": overall_runtime_state,
            "system_mode": system_mode,
            "observer_state": observer_state,
            "execution_state": execution_state,
            "ai_state": ai_state,
            "preflight_guard_allowed": preflight_guard_allowed,
        },
        "local_gate_context": {
            "market_friction_state": market_friction_state,
            "market_friction_allow": market_friction_allow,
            "risk_envelope_state": risk_envelope_state,
            "risk_envelope_allow": risk_envelope_allow,
            "trade_eligibility_state": trade_eligibility_state,
            "allow_progress_to_thought_gate": allow_progress_to_thought_gate,
        },
        "market_context": {
            "symbol": public_config.get("symbol"),
            "category": public_config.get("category"),
            "spread_bps": public_derived.get("spread_bps"),
            "volatility_bps": public_derived.get("volatility_bps"),
            "volatility_band": public_derived.get("volatility_band"),
            "slippage_buy_bps_for_test_notional": public_derived.get("slippage_buy_bps_for_test_notional"),
            "slippage_sell_bps_for_test_notional": public_derived.get("slippage_sell_bps_for_test_notional"),
            "recent_trade_count": as_int(public_derived.get("recent_trade_count"), 0),
            "last_trade_price": public_derived.get("last_trade_price"),
            "last_trade_ts_ms": public_derived.get("last_trade_ts_ms"),
            "coverage": public_coverage,
        },
        "cost_context": {
            "cost_model_state": cost_model.get("cost_model_state"),
            "round_trip_cost_bps": cost_config.get("round_trip_cost_bps"),
            "slippage_buffer_bps": cost_config.get("slippage_buffer_bps"),
            "edge_multiplier": cost_config.get("edge_multiplier"),
            "total_cost_floor_bps": cost_derived.get("total_cost_floor_bps"),
            "required_edge_bps": cost_derived.get("required_edge_bps"),
        },
        "policy_inputs": {
            "ai_max_expected_roundtrip_ms": ai_max_expected_roundtrip_ms,
            "ai_daily_budget_usd": ai_daily_budget_usd,
            "ai_per_call_budget_usd": ai_per_call_budget_usd,
            "max_public_data_age_ms": max_public_data_age_ms,
            "max_h0_audit_age_ms": max_h0_audit_age_ms,
            "soft_max_spread_bps": soft_max_spread_bps,
            "soft_max_volatility_bps": soft_max_volatility_bps,
            "soft_max_slippage_bps": soft_max_slippage_bps,
            "source_map": {
                "ai_max_expected_roundtrip_ms": f"env:{AI_MAX_EXPECTED_ROUNDTRIP_MS_ENV}",
                "ai_daily_budget_usd": f"env:{AI_DAILY_BUDGET_USD_ENV}",
                "ai_per_call_budget_usd": f"env:{AI_PER_CALL_BUDGET_USD_ENV}",
                "max_public_data_age_ms": f"env:{THOUGHT_GATE_MAX_PUBLIC_DATA_AGE_MS_ENV}",
                "max_h0_audit_age_ms": f"env:{THOUGHT_GATE_MAX_H0_AUDIT_AGE_MS_ENV}",
                "soft_max_spread_bps": f"env:{THOUGHT_GATE_SOFT_MAX_SPREAD_BPS_ENV}",
                "soft_max_volatility_bps": f"env:{THOUGHT_GATE_SOFT_MAX_VOLATILITY_BPS_ENV}",
                "soft_max_slippage_bps": f"env:{THOUGHT_GATE_SOFT_MAX_SLIPPAGE_BPS_ENV}",
            },
        },
        "freshness": {
            "public_microstructure_age_ms": public_micro_age_ms,
            "h0_final_audit_age_ms": h0_final_age_ms,
            "runtime_state_age_ms": runtime_state_age_ms,
            "decision_packet_age_ms": decision_packet_age_ms,
        },
        "input_state": input_state,
        "allow_progress_to_h1b_policy": allow_progress_to_h1b_policy,

        "operator_flags": operator_flags,
        "operator_message": (
            "H1-A thought gate input built. This object prepares normalized, "
            "freshness-aware, budget-aware inputs for later H1 policy and "
            "decision layers, but does not itself authorize AI invocation."
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
