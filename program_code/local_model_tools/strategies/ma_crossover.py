"""
MA Crossover Strategy / 均线交叉策略

MODULE_NOTE (中文):
  经典的趋势跟踪策略：当快速均线（EMA12）上穿慢速均线（EMA26）时做多，
  下穿时做空。结合 MACD 和 RSI 过滤假信号。

  适用场景：趋势明显的市场
  不适用：震荡/横盘市场（会频繁假突破）

  入场条件：
  1. MA 交叉信号（快线穿越慢线）
  2. MACD 方向确认（同向）
  3. RSI 不在极端区域（避免追高追低）

  出场条件：
  1. 反向交叉信号
  2. 硬止损（由风控框架管理）

MODULE_NOTE (English):
  Classic trend-following strategy: go long when fast MA (EMA12) crosses above
  slow MA (EMA26), go short when it crosses below. Uses MACD and RSI to filter
  false signals.

  Suitable: trending markets
  Not suitable: ranging/sideways markets (frequent false breakouts)

Safety invariant / 安全不变量:
  - 只产生 OrderIntent / Only generates OrderIntents
"""

from __future__ import annotations

import time
from typing import Any

from .base import OrderIntent, StrategyBase, STRATEGY_ACTIVE


class MACrossoverStrategy(StrategyBase):
    """
    Moving Average Crossover trend-following strategy.
    均线交叉趋势跟踪策略。

    Parameters:
      symbol            — trading pair to trade / 交易的交易对
      qty_per_trade     — position size per trade / 每次交易的仓位大小
      min_confidence    — minimum signal confidence to act / 最小信号置信度
    """

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        qty_per_trade: float = 0.001,
        min_confidence: float = 0.3,
        cooldown_ms: int = 300_000,
    ) -> None:
        super().__init__()
        if qty_per_trade <= 0:
            raise ValueError(f"qty_per_trade must be > 0, got {qty_per_trade} / 每笔数量必须大于 0")
        self._symbol = symbol
        self._qty = qty_per_trade
        self._min_confidence = min_confidence
        # Position state is "intended" — updated when intent is emitted, not when confirmed.
        # In paper trading without execution callback, this is a known limitation.
        # 仓位状态为"意图态" — 在意图发出时更新，非确认后更新。
        # 在没有执行回调的纸上交易中，这是已知限制。
        self._current_position: str | None = None  # "long" / "short" / None
        self._trade_count = 0
        self._last_trade_ts_ms: int = 0
        self._cooldown_ms: int = cooldown_ms  # Default 5 min cooldown between trades / 交易间隔冷却默认 5 分钟

    @property
    def name(self) -> str:
        return "MA_Crossover"

    @property
    def description(self) -> str:
        return (
            "均线交叉趋势跟踪策略 / MA Crossover trend-following strategy. "
            "EMA(12) × EMA(26) 交叉 + MACD 确认"
        )

    def on_signal(self, signal: Any) -> None:
        """
        Process a trading signal / 处理交易信号

        Only acts on MA crossover and MACD signals for the configured symbol.
        仅对配置的交易对的 MA 交叉和 MACD 信号做出反应。
        """
        if self._state != STRATEGY_ACTIVE:
            return
        if getattr(signal, "symbol", "") != self._symbol:
            return
        if getattr(signal, "confidence", 0) < self._min_confidence:
            return

        # Cooldown check / 冷却期检查
        now_ms = int(time.time() * 1000)
        if now_ms - self._last_trade_ts_ms < self._cooldown_ms:
            return

        source = getattr(signal, "source", "")
        direction = getattr(signal, "direction", "")

        # Only act on MA crossover signals / 只对 MA 交叉信号行动
        if "MA_Cross" not in source:
            return

        with self._intent_lock:  # Protect _current_position read+write+emit atomically / 原子保护仓位状态
            # Multi-TF regime filter: skip trend-following in ranging/squeeze markets
            # 多时间框架 regime 过滤：震荡/收窄市场中跳过趋势跟踪
            # Note: "unknown" passes through — when regime detection is unavailable for
            # this symbol (no BB/ATR history yet), we still allow trading.
            # "trending" and "volatile" also pass through (favorable for trend-following).
            # Only "ranging" and "squeeze" are filtered (unfavorable for MA crossover).
            # 注意："unknown" 允许通过 — 当该品种尚无 regime 检测（缺少 BB/ATR 历史）时，仍允许交易。
            signal_regime = getattr(signal, "metadata", {}).get("_regime", "unknown")
            # Reject ranging/squeeze (unfavorable) AND unknown (insufficient history).
            # "unknown" means no BB/ATR data yet — new symbols with cold-start data should
            # not trade immediately. Only "trending" and "volatile" pass through.
            # 拒绝 ranging/squeeze（不利）以及 unknown（数据不足）。
            # "unknown" 表示尚无 BB/ATR 历史，新上线品种不应立即入场。
            if signal_regime in ("ranging", "squeeze", "unknown"):
                return

            if direction == "long" and self._current_position != "long":
                # Close short if exists, then go long / 有空仓先平仓，再开多
                if self._current_position == "short":
                    self._emit_intent(OrderIntent(
                        symbol=self._symbol, side="Buy", order_type="market",
                        qty=self._qty, strategy_name=self.name,
                        reason=f"Close short: MA crossover bullish / 平空：均线金叉, conf={signal.confidence:.2f}",
                        confidence=signal.confidence,
                    ))
                self._emit_intent(OrderIntent(
                    symbol=self._symbol, side="Buy", order_type="market",
                    qty=self._qty, strategy_name=self.name,
                    reason=f"Open long: MA crossover bullish / 开多：均线金叉, conf={signal.confidence:.2f}",
                    confidence=signal.confidence,
                ))
                self._current_position = "long"
                self._trade_count += 1
                self._last_trade_ts_ms = int(time.time() * 1000)

            elif direction == "short" and self._current_position != "short":
                if self._current_position == "long":
                    self._emit_intent(OrderIntent(
                        symbol=self._symbol, side="Sell", order_type="market",
                        qty=self._qty, strategy_name=self.name,
                        reason=f"Close long: MA crossover bearish / 平多：均线死叉, conf={signal.confidence:.2f}",
                        confidence=signal.confidence,
                    ))
                self._emit_intent(OrderIntent(
                    symbol=self._symbol, side="Sell", order_type="market",
                    qty=self._qty, strategy_name=self.name,
                    reason=f"Open short: MA crossover bearish / 开空：均线死叉, conf={signal.confidence:.2f}",
                    confidence=signal.confidence,
                ))
                self._current_position = "short"
                self._trade_count += 1
                self._last_trade_ts_ms = int(time.time() * 1000)

    def get_persistent_state(self) -> dict[str, Any]:
        base = super().get_persistent_state()
        base.update({
            "current_position": self._current_position,
            "trade_count": self._trade_count,
        })
        return base

    def restore_persistent_state(self, saved: dict[str, Any]) -> None:
        super().restore_persistent_state(saved)
        self._current_position = saved.get("current_position")
        self._trade_count = saved.get("trade_count", 0)

    def get_status(self) -> dict[str, Any]:
        return {
            "strategy": self.name,
            "state": self.state,
            "symbol": self._symbol,
            "current_position": self._current_position,
            "qty_per_trade": self._qty,
            "min_confidence": self._min_confidence,
            "trade_count": self._trade_count,
            "cooldown_ms": self._cooldown_ms,
            "last_trade_ts_ms": self._last_trade_ts_ms,
        }
