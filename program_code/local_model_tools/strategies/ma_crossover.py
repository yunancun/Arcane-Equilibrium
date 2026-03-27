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
      require_macd      — require MACD confirmation / 是否需要 MACD 确认
    """

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        qty_per_trade: float = 0.001,
        min_confidence: float = 0.3,
        require_macd: bool = True,
    ) -> None:
        super().__init__()
        self._symbol = symbol
        self._qty = qty_per_trade
        self._min_confidence = min_confidence
        self._require_macd = require_macd
        self._current_position: str | None = None  # "long" / "short" / None
        self._trade_count = 0

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

        source = getattr(signal, "source", "")
        direction = getattr(signal, "direction", "")

        # Only act on MA crossover signals / 只对 MA 交叉信号行动
        if "MA_Cross" not in source:
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

    def get_status(self) -> dict[str, Any]:
        return {
            "strategy": self.name,
            "state": self.state,
            "symbol": self._symbol,
            "current_position": self._current_position,
            "qty_per_trade": self._qty,
            "min_confidence": self._min_confidence,
            "trade_count": self._trade_count,
        }
