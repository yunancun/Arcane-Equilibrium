"""
Signal Engine — Unified Signal Evaluation and Routing.
信号引擎 — 统一信号评估与路由。

MODULE_NOTE (EN): Extracted from signal_generator.py (FIX-08 file size).
  Contains SignalEngine class and SignalCallback type alias.
  Manages multiple SignalRules, evaluates on indicator updates, records history.
MODULE_NOTE (中): 从 signal_generator.py 提取（FIX-08 文件大小）。
  包含 SignalEngine 类和 SignalCallback 类型别名。
  管理多个 SignalRule，在指标更新时评估，记录历史。
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Callable

from .signal_generator import (
    ALL_DIRECTIONS,
    DIRECTION_LONG,
    DIRECTION_NEUTRAL,
    DIRECTION_SHORT,
    SIGNAL_HISTORY_CAPACITY,
    Signal,
    SignalRule,
    create_default_signal_rules,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Signal Callback Type / 信号回调类型
# =============================================================================

# callback(signal)
SignalCallback = Callable[[Signal], None]


# =============================================================================
# SignalEngine — Unified Signal Evaluation / 统一信号评估引擎
# =============================================================================

class SignalEngine:
    """
    Manages signal rules, evaluates them on indicator updates, records history.
    管理信号规则，在指标更新时评估，记录历史。

    Integrates with IndicatorEngine: register as on_update callback.
    与 IndicatorEngine 集成：注册为 on_update 回调。

    Usage:
      se = SignalEngine()
      indicator_engine.register_on_update(se.on_indicators_update)
      se.register_on_signal(my_strategy.on_signal)
    """

    def __init__(
        self,
        rules: list[SignalRule] | None = None,
        history_capacity: int = SIGNAL_HISTORY_CAPACITY,
    ) -> None:
        self._rules = list(rules or create_default_signal_rules())
        self._lock = threading.Lock()

        # Signal history (newest last) / 信号历史（最新的在最后）
        self._history: deque[Signal] = deque(maxlen=history_capacity)

        # Latest signal per (symbol, source) / 每个 (交易对, 来源) 的最新信号
        # Bounded to prevent unbounded growth for delisted symbols / 有上限防止已下架交易对的无限增长
        self._latest: dict[tuple[str, str], Signal] = {}
        self._latest_max_size = 500

        # Downstream callbacks / 下游回调
        self._on_signal_callbacks: list[SignalCallback] = []

        # Statistics / 统计
        self._stats = {
            "total_evaluations": 0,
            "signals_generated": 0,
            "rule_errors": 0,
            "signals_by_direction": {d: 0 for d in ALL_DIRECTIONS},
            "signals_by_source": {},
        }

    # ── Registration / 注册 ──

    def register_rule(self, rule: SignalRule) -> None:
        """Register a new signal rule / 注册新信号规则"""
        with self._lock:
            self._rules.append(rule)
        logger.info("Registered signal rule / 注册信号规则: %s", rule.name)

    def register_on_signal(self, callback: SignalCallback) -> None:
        """
        Register a callback for new signals / 注册新信号回调

        Called whenever an actionable signal is generated.
        每当生成可执行信号时调用。
        """
        with self._lock:
            self._on_signal_callbacks.append(callback)

    # ── Core: Indicator Update Handler / 核心：指标更新处理 ──

    def on_indicators_update(
        self,
        symbol: str,
        timeframe: str,
        indicators: dict[str, Any],
    ) -> list[Signal]:
        """
        Evaluate all rules against updated indicators.
        使用更新的指标评估所有规则。

        This is designed to be registered as IndicatorEngine.register_on_update callback.
        设计为注册为 IndicatorEngine.register_on_update 的回调。

        Args:
          symbol     — trading pair / 交易对
          timeframe  — timeframe / 时间框架
          indicators — {indicator_name: result_dict} / 指标结果字典

        Returns:
          List of signals generated (may be empty) / 生成的信号列表（可能为空）
        """
        generated: list[Signal] = []

        with self._lock:
            rules = list(self._rules)

        for rule in rules:
            try:
                signal = rule.evaluate(symbol, timeframe, indicators)
                # Allow Regime_Detector neutral signals through for dispatch
                # 允许 Regime_Detector 的中性信号通过以便分发
                if signal is not None and (signal.is_actionable or signal.source == "Regime_Detector"):
                    generated.append(signal)
                    with self._lock:
                        self._history.append(signal)
                        self._latest[(symbol, rule.name)] = signal
                        # Evict oldest entries if _latest exceeds max size
                        # 超过上限时淘汰最旧条目
                        if len(self._latest) > self._latest_max_size:
                            oldest_key = next(iter(self._latest))
                            del self._latest[oldest_key]
                        self._stats["signals_generated"] += 1
                        self._stats["signals_by_direction"][signal.direction] = (
                            self._stats["signals_by_direction"].get(signal.direction, 0) + 1
                        )
                        self._stats["signals_by_source"][rule.name] = (
                            self._stats["signals_by_source"].get(rule.name, 0) + 1
                        )
            except Exception:
                logger.exception(
                    "Signal rule evaluation error / 信号规则评估异常: %s",
                    rule.name,
                )
                with self._lock:
                    self._stats["rule_errors"] += 1

        with self._lock:
            self._stats["total_evaluations"] += 1

        # Notify downstream (snapshot callbacks under lock) / 通知下游（在锁内快照回调列表）
        with self._lock:
            callbacks = list(self._on_signal_callbacks)
        for signal in generated:
            for cb in callbacks:
                try:
                    cb(signal)
                except Exception:
                    logger.exception("Signal callback error / 信号回调异常")

        return generated

    # ── Query Interface / 查询接口 ──

    def get_latest_signals(self, symbol: str | None = None, n: int = 20) -> list[dict[str, Any]]:
        """
        Get latest N signals (optionally filtered by symbol).
        获取最近 N 个信号（可选按交易对过滤）。
        """
        with self._lock:
            if symbol:
                filtered = [s for s in self._history if s.symbol == symbol]
            else:
                filtered = list(self._history)
            recent = filtered[-n:] if n < len(filtered) else filtered
            return [s.to_dict() for s in recent]

    def get_latest_for_symbol(self, symbol: str) -> dict[str, dict[str, Any]]:
        """
        Get the latest signal from each rule for a specific symbol.
        获取指定交易对每个规则的最新信号。

        Returns:
          {rule_name: signal_dict} / {规则名称: 信号字典}
        """
        with self._lock:
            result = {}
            for (sym, source), signal in self._latest.items():
                if sym == symbol:
                    result[source] = signal.to_dict()
            return result

    def get_signal_summary(self, symbol: str) -> dict[str, Any]:
        """
        Get a weighted consensus summary for a symbol.
        获取加权共识摘要。

        Weights signals by confidence, freshness, and regime context.
        按置信度、新鲜度和 regime 上下文加权。
        """
        now_ms = int(time.time() * 1000)
        FRESHNESS_DECAY_MS = 300_000  # 5 minutes full weight, then decay / 5 分钟内全权重

        with self._lock:
            signals = [
                s for (sym, _), s in self._latest.items()
                if sym == symbol and s.is_actionable
            ]
            # Also get regime info if available
            regime_signal = None
            for (sym, src), s in self._latest.items():
                if sym == symbol and s.source == "Regime_Detector":
                    regime_signal = s
                    break

        # Determine regime for weighting
        regime = "unknown"
        if regime_signal and regime_signal.metadata:
            regime = regime_signal.metadata.get("regime", "unknown")

        # Regime-based rule weight multipliers
        # 趋势市场：MA/MACD 权重高，RSI/BB 权重低
        # 震荡市场：RSI/BB 权重高，MA/MACD 权重低
        REGIME_WEIGHTS = {
            "trending": {"MA_Cross": 1.5, "MACD_Cross": 1.3, "RSI_OB_OS": 0.5, "BB_Reversion": 0.5},
            "ranging":  {"MA_Cross": 0.5, "MACD_Cross": 0.5, "RSI_OB_OS": 1.5, "BB_Reversion": 1.5},
            "squeeze":  {"MA_Cross": 0.3, "MACD_Cross": 0.3, "RSI_OB_OS": 0.3, "BB_Reversion": 0.3},
            "volatile": {"MA_Cross": 0.7, "MACD_Cross": 0.7, "RSI_OB_OS": 0.7, "BB_Reversion": 0.7},
        }
        regime_mults = REGIME_WEIGHTS.get(regime, {})

        long_score = 0.0
        short_score = 0.0

        for s in signals:
            # Base weight = confidence
            weight = s.confidence

            # Freshness decay: signals older than 5 min lose weight linearly
            age_ms = now_ms - s.ts_ms
            if age_ms > FRESHNESS_DECAY_MS:
                freshness = max(0.1, 1.0 - (age_ms - FRESHNESS_DECAY_MS) / FRESHNESS_DECAY_MS)
                weight *= freshness

            # Regime multiplier: match source prefix to regime weights
            for prefix, mult in regime_mults.items():
                if prefix in s.source:
                    weight *= mult
                    break

            if s.direction == DIRECTION_LONG:
                long_score += weight
            elif s.direction == DIRECTION_SHORT:
                short_score += weight

        total_score = long_score + short_score
        if total_score > 0:
            if long_score > short_score * 1.2:  # Need 20% margin for conviction
                consensus = DIRECTION_LONG
            elif short_score > long_score * 1.2:
                consensus = DIRECTION_SHORT
            else:
                consensus = DIRECTION_NEUTRAL  # Insufficient conviction / 信念不足
        else:
            consensus = DIRECTION_NEUTRAL

        return {
            "symbol": symbol,
            "long_score": round(long_score, 4),
            "short_score": round(short_score, 4),
            "long_count": sum(1 for s in signals if s.direction == DIRECTION_LONG),
            "short_count": sum(1 for s in signals if s.direction == DIRECTION_SHORT),
            "total_signals": len(signals),
            "avg_confidence": round(sum(s.confidence for s in signals) / len(signals), 4) if signals else 0.0,
            "consensus_direction": consensus,
            "regime": regime,
            "signals": [s.to_dict() for s in signals],
        }

    def get_stats(self) -> dict[str, Any]:
        """Get signal engine statistics / 获取信号引擎统计"""
        with self._lock:
            return {
                "component": "signal_engine",
                "rules_registered": [r.name for r in self._rules],
                "rule_count": len(self._rules),
                "history_size": len(self._history),
                "stats": {
                    k: (dict(v) if isinstance(v, dict) else v)
                    for k, v in self._stats.items()
                },
            }

    def clear_history(self) -> None:
        """Clear signal history / 清空信号历史"""
        with self._lock:
            self._history.clear()
            self._latest.clear()
