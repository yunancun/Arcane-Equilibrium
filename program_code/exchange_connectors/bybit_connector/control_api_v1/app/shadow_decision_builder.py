from __future__ import annotations

"""
Shadow Decision Builder / 影子决策构建器
将 H 链 AI 治理管线的观察结论转化为纸上交易信号

MODULE_NOTE (中文):
  本模块是 H 链 AI 治理管线与 Paper Trading Engine 之间的桥梁。
  它读取 H1-H 的 AI governed observation（市场判断），结合 I 链的 shadow decision lease
  模式，生成可供 Paper Trading Engine 消费的交易信号。

  核心流程：
  1. 读取 observer verdict — 确认系统处于安全状态
  2. 读取 H1-H governed decision — 获取 AI 的市场判断（regime / bias / confidence / edge）
  3. 构建 shadow decision — 包含交易方向、置信度、预期边际
  4. 将 shadow decision 喂给 Paper Trading Engine — 如果满足阈值则自动创建纸上订单
  5. 记录决策与执行结果的关联 — 供事后归因分析

  安全保证：
  - 仅读取文件 + 提交纸上订单，绝不与 Bybit 真实 API 交互
  - 所有 shadow decision 携带 is_simulated=True 标记
  - 即使 AI 建议"立即买入"，也只在 paper engine 中执行
  - system_mode / execution_state / execution_authority 全程不变

MODULE_NOTE (English):
  This module bridges the H-chain AI governance pipeline with the Paper Trading Engine.
  It reads the H1-H AI governed observation (market judgment), combined with the I-chain
  shadow decision lease pattern, to generate trade signals consumable by the Paper Engine.

  Core flow:
  1. Read observer verdict — confirm system is in safe state
  2. Read H1-H governed decision — get AI's market judgment (regime/bias/confidence/edge)
  3. Build shadow decision — contains trade direction, confidence, expected edge
  4. Feed shadow decision to Paper Engine — auto-create paper orders if threshold met
  5. Record decision-to-execution mapping — for post-hoc attribution analysis

  Safety guarantees:
  - Only reads files + submits paper orders, never interacts with real Bybit API
  - All shadow decisions carry is_simulated=True marker
  - Even if AI recommends "buy now", it only executes in the paper engine
  - system_mode / execution_state / execution_authority unchanged throughout
"""

import hashlib
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from .paper_trading_engine import (
    ORDER_TYPE_MARKET,
    SIDE_BUY,
    SIDE_SELL,
    PaperTradingEngine,
    SESSION_ACTIVE,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Constants / 常量
# ═══════════════════════════════════════════════════════════════════════════════

# Minimum confidence to generate a paper trade signal (0-1 scale)
# 生成纸上交易信号的最低置信度
DEFAULT_CONFIDENCE_THRESHOLD = 0.5

# Minimum expected edge in basis points to justify a trade
# 交易的最低预期边际（基点）
DEFAULT_EDGE_THRESHOLD_BPS = 25.0  # Must exceed round-trip cost floor (~21 bps)

# Default position size as fraction of paper balance
# 默认仓位大小（纸上余额的百分比）
DEFAULT_POSITION_SIZE_FRACTION = 0.02  # 2%

# Action bias → order side mapping
# 动作偏向 → 订单方向映射
BIAS_TO_SIDE = {
    "buy_bias": SIDE_BUY,
    "sell_bias": SIDE_SELL,
}


# ═══════════════════════════════════════════════════════════════════════════════
# Shadow Decision Data Structure / 影子决策数据结构
# ═══════════════════════════════════════════════════════════════════════════════

def build_shadow_decision(
    *,
    verdict: dict[str, Any] | None = None,
    governed_observation: dict[str, Any] | None = None,
    market_prices: dict[str, float] | None = None,
    symbol: str = "BTCUSDT",
) -> dict[str, Any]:
    """
    Build a shadow decision from H-chain outputs.
    从 H 链输出构建影子决策。

    If no governed_observation is available (H-chain not yet connected),
    builds a minimal decision from verdict data alone.
    """
    now_ms = int(time.time() * 1000)
    decision_id = f"sdec:{uuid.uuid4().hex[:12]}"

    # Extract from governed observation if available
    # 如果有 AI governed observation，从中提取
    if governed_observation:
        market_regime = governed_observation.get("market_regime", "unknown")
        action_bias = governed_observation.get("action_bias", "flat_bias")
        confidence = governed_observation.get("confidence_0_to_1", 0.0)
        edge_bps = governed_observation.get("edge_assessment_bps", 0.0)
        key_reasons = governed_observation.get("key_reasons", [])
        risk_notes = governed_observation.get("risk_notes", [])
        why_not_trade = governed_observation.get("why_not_trade", [])
        analysis_mode = governed_observation.get("analysis_mode", "observation_only")

        # Build observation fingerprint for audit trail
        obs_str = json.dumps(governed_observation, sort_keys=True, ensure_ascii=False)
        obs_fingerprint = hashlib.sha256(obs_str.encode()).hexdigest()[:16]
    else:
        # No AI observation available — use verdict hints
        # 无 AI 观察结论 — 使用 verdict 提示
        market_regime = "unknown"
        action_bias = "flat_bias"
        confidence = 0.0
        edge_bps = 0.0
        key_reasons = []
        risk_notes = verdict.get("risk_flags", []) if verdict else []
        why_not_trade = verdict.get("reasons", []) if verdict else ["no_ai_observation"]
        analysis_mode = "observation_only"
        obs_fingerprint = "no_observation"

    # Determine trade signal / 确定交易信号
    side = BIAS_TO_SIDE.get(action_bias)
    should_trade = (
        side is not None
        and confidence >= DEFAULT_CONFIDENCE_THRESHOLD
        and edge_bps >= DEFAULT_EDGE_THRESHOLD_BPS
        and analysis_mode != "observation_only"
    )

    decision: dict[str, Any] = {
        "decision_id": decision_id,
        "decision_ts_ms": now_ms,
        "symbol": symbol,

        # AI judgment / AI 判断
        "market_regime": market_regime,
        "action_bias": action_bias,
        "confidence": confidence,
        "edge_assessment_bps": edge_bps,
        "analysis_mode": analysis_mode,

        # Trade signal / 交易信号
        "should_trade": should_trade,
        "trade_side": side if should_trade else None,
        "trade_reason": key_reasons[:3] if should_trade else why_not_trade[:3],

        # Risk / 风险
        "risk_notes": risk_notes[:5],
        "blocking_reasons": [] if should_trade else why_not_trade[:3],

        # Audit / 审计
        "observation_fingerprint": obs_fingerprint,
        "verdict_code": verdict.get("verdict_code") if verdict else None,

        # Safety markers / 安全标记
        "is_simulated": True,
        "lease_mode": "shadow_only",
        "execution_authority": "not_granted",
        "decision_lease_emitted": False,
    }

    return decision


# ═══════════════════════════════════════════════════════════════════════════════
# Shadow Decision Consumer / 影子决策消费器
# ═══════════════════════════════════════════════════════════════════════════════

class ShadowDecisionConsumer:
    """
    Consumes shadow decisions and creates paper orders when appropriate.
    消费影子决策，在满足条件时创建纸上订单。
    """

    def __init__(
        self,
        engine: PaperTradingEngine,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        edge_threshold_bps: float = DEFAULT_EDGE_THRESHOLD_BPS,
        position_size_fraction: float = DEFAULT_POSITION_SIZE_FRACTION,
    ) -> None:
        self._engine = engine
        self._confidence_threshold = confidence_threshold
        self._edge_threshold_bps = edge_threshold_bps
        self._position_size_fraction = position_size_fraction
        self._decision_history: list[dict[str, Any]] = []

    def consume(
        self,
        decision: dict[str, Any],
        market_prices: dict[str, float],
    ) -> dict[str, Any]:
        """
        Process a shadow decision — create paper order if signal is strong enough.
        处理影子决策 — 如果信号足够强则创建纸上订单。

        Returns consumption result with decision_id → order_id mapping.
        """
        result: dict[str, Any] = {
            "decision_id": decision["decision_id"],
            "consumed_ts_ms": int(time.time() * 1000),
            "action_taken": "hold",
            "order_id": None,
            "reason": "",
        }

        # Check session is active / 检查 session 活跃
        try:
            state = self._engine.get_state()
        except Exception:
            result["reason"] = "engine_read_failed"
            self._record(decision, result)
            return result

        if state.get("session", {}).get("session_state") != SESSION_ACTIVE:
            result["reason"] = "session_not_active"
            self._record(decision, result)
            return result

        # Check if decision says to trade / 检查决策是否建议交易
        if not decision.get("should_trade"):
            result["reason"] = "; ".join(decision.get("blocking_reasons", ["no_signal"]))
            self._record(decision, result)
            return result

        symbol = decision["symbol"]
        side = decision["trade_side"]
        price = market_prices.get(symbol)

        if not price or price <= 0:
            result["reason"] = f"no_market_price_for_{symbol}"
            self._record(decision, result)
            return result

        # Calculate position size / 计算仓位大小
        # Apply risk manager's position_size_multiplier if available
        # 如果有风控管理器，应用仓位大小乘数
        balance = state["session"].get("current_paper_balance_usdt", 0)
        effective_fraction = self._position_size_fraction
        risk_state = state.get("risk", {})
        agent_params = risk_state.get("agent_params", {})
        multiplier = agent_params.get("position_size_multiplier", 1.0)
        effective_fraction *= max(0.1, min(multiplier, 1.0))
        notional = balance * effective_fraction
        qty = notional / price
        if qty <= 0:
            result["reason"] = "insufficient_balance"
            self._record(decision, result)
            return result

        # Round qty to reasonable precision / 合理精度
        if price > 10000:
            qty = round(qty, 5)   # BTC-like
        elif price > 100:
            qty = round(qty, 3)   # ETH-like
        else:
            qty = round(qty, 1)

        if qty <= 0:
            result["reason"] = "qty_rounds_to_zero"
            self._record(decision, result)
            return result

        # Submit paper order / 提交纸上订单
        try:
            order_result = self._engine.submit_order(
                symbol=symbol,
                side=side,
                order_type=ORDER_TYPE_MARKET,
                qty=qty,
                market_prices=market_prices,
            )

            if order_result.get("rejected_reason"):
                result["action_taken"] = "rejected"
                result["reason"] = order_result["rejected_reason"]
            else:
                result["action_taken"] = "order_submitted"
                result["order_id"] = order_result["order"]["order_id"]
                result["reason"] = f"confidence={decision['confidence']:.2f} edge={decision['edge_assessment_bps']:.1f}bps"

                # Record shadow decision in paper state
                self._engine.store.mutate(lambda s: _append_shadow_decision(s, decision, result))

                logger.info(
                    "Shadow decision → paper order: %s %s %s qty=%.6f @ %.2f",
                    decision["decision_id"], side, symbol, qty, price,
                )

        except Exception as e:
            result["action_taken"] = "error"
            result["reason"] = str(e)
            logger.error("Shadow decision consume error: %s", e)

        self._record(decision, result)
        return result

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent shadow decision consumption history / 获取影子决策消费历史"""
        return self._decision_history[-limit:]

    def _record(self, decision: dict, result: dict) -> None:
        self._decision_history.append({
            "decision": decision,
            "result": result,
        })
        # Cap history
        if len(self._decision_history) > 200:
            self._decision_history = self._decision_history[-200:]


def _append_shadow_decision(state: dict, decision: dict, result: dict) -> dict:
    """Append shadow decision record to paper state / 将影子决策记录附加到纸上状态"""
    if "shadow_decisions" not in state:
        state["shadow_decisions"] = []
    state["shadow_decisions"].append({
        "decision_id": decision["decision_id"],
        "order_id": result.get("order_id"),
        "symbol": decision["symbol"],
        "side": decision.get("trade_side"),
        "confidence": decision["confidence"],
        "edge_bps": decision["edge_assessment_bps"],
        "market_regime": decision["market_regime"],
        "action_taken": result["action_taken"],
        "ts_ms": result["consumed_ts_ms"],
        "is_simulated": True,
    })
    # Cap at 200 entries
    if len(state["shadow_decisions"]) > 200:
        state["shadow_decisions"] = state["shadow_decisions"][-200:]
    return state


# ═══════════════════════════════════════════════════════════════════════════════
# File-Based Shadow Decision Feeder / 基于文件的影子决策馈送器
# ═══════════════════════════════════════════════════════════════════════════════

class ShadowDecisionFileFeeder:
    """
    Reads H-chain output files and feeds shadow decisions to the consumer.
    读取 H 链输出文件并将影子决策馈送给消费器。

    This is the adapter that connects the existing H-chain file-based pipeline
    with the paper trading engine's in-process consumption.
    """

    def __init__(
        self,
        consumer: ShadowDecisionConsumer,
        verdict_path: str | Path | None = None,
        governed_decision_path: str | Path | None = None,
        default_symbol: str = "BTCUSDT",
    ) -> None:
        self._consumer = consumer
        self._verdict_path = Path(verdict_path) if verdict_path else None
        self._governed_decision_path = Path(governed_decision_path) if governed_decision_path else None
        self._default_symbol = default_symbol
        self._last_processed_verdict_ts: int = 0

    def check_and_feed(self, market_prices: dict[str, float]) -> dict[str, Any] | None:
        """
        Check for new H-chain outputs and feed if available.
        检查是否有新的 H 链输出，如果有则馈送。

        Returns consumption result or None if no new data.
        """
        # Load verdict / 加载判决
        verdict = self._load_json(self._verdict_path) if self._verdict_path else None

        # Check if this is a new verdict (avoid re-processing)
        # 检查是否为新判决（避免重复处理）
        if verdict:
            verdict_ts = verdict.get("verdict_generated_ts_ms", 0)
            if verdict_ts <= self._last_processed_verdict_ts:
                return None  # Already processed / 已处理过
            self._last_processed_verdict_ts = verdict_ts

        # Load governed observation (if H-chain has run AI consultation)
        # 加载 AI 治理观察结论（如果 H 链已执行 AI 咨询）
        governed_obs = self._load_json(self._governed_decision_path) if self._governed_decision_path else None

        # Build shadow decision / 构建影子决策
        decision = build_shadow_decision(
            verdict=verdict,
            governed_observation=governed_obs,
            market_prices=market_prices,
            symbol=self._default_symbol,
        )

        # Consume / 消费
        return self._consumer.consume(decision, market_prices)

    @staticmethod
    def _load_json(path: Path | None) -> dict[str, Any] | None:
        if path is None or not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
