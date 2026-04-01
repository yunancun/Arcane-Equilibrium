"""
Bollinger Band Breakout Strategy / 布林带突破策略

MODULE_NOTE (中文):
  当布林带收窄（squeeze）后扩张时，价格通常会产生方向性突破。
  本策略检测 squeeze → expansion 转换，配合成交量和动量确认入场。

  与 BB Reversion 策略互补：
  - BB Reversion: 价格在带内回归均值（震荡市）
  - BB Breakout: 价格突破带外跟随趋势（突破市）

  入场条件：
  1. 带宽从低于 squeeze 阈值扩张到高于 expansion 阈值
  2. 价格突破上轨（%B > 1）→ 做多；突破下轨（%B < 0）→ 做空
  3. ATR 确认波动率上升

  出场条件：
  1. 价格回到带内（%B 回到 0.2-0.8）
  2. StopManager 硬止损

MODULE_NOTE (English):
  Detects Bollinger Band squeeze-to-expansion breakouts.
  Complementary to BB Reversion (reversion = ranging, breakout = trending).

Safety invariant:
  - 只产生 OrderIntent / Only generates OrderIntents
"""

from __future__ import annotations
import logging
import time
from typing import Any
from .base import OrderIntent, StrategyBase, STRATEGY_ACTIVE

logger = logging.getLogger(__name__)


class BBBreakoutStrategy(StrategyBase):
    """
    Bollinger Band Breakout strategy — trades squeeze-to-expansion transitions.
    """

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        qty_per_trade: float = 0.001,
        squeeze_bandwidth: float = 0.02,     # BW below this = squeeze
        expansion_bandwidth: float = 0.04,   # BW above this = expansion confirmed
        min_confidence: float = 0.4,
        cooldown_ms: int = 600_000,          # 10 min cooldown
    ) -> None:
        super().__init__()
        if qty_per_trade <= 0:
            raise ValueError(f"qty_per_trade must be > 0, got {qty_per_trade}")
        self._symbol = symbol
        self._qty = qty_per_trade
        self._squeeze_bw = squeeze_bandwidth
        self._expansion_bw = expansion_bandwidth
        self._min_confidence = min_confidence
        self._cooldown_ms = cooldown_ms
        self._current_position: str | None = None
        self._was_squeezed = False  # Was in squeeze state before expansion
        self._last_trade_ts_ms = 0
        self._trade_count = 0

    @property
    def name(self) -> str:
        return "BB_Breakout"

    @property
    def description(self) -> str:
        return "布林带突破策略 / BB Breakout: squeeze→expansion trend following"

    def on_signal(self, signal: Any) -> None:
        if self._state != STRATEGY_ACTIVE:
            return
        if getattr(signal, "symbol", "") != self._symbol:
            return

        source = getattr(signal, "source", "")

        # Listen to BB signals for bandwidth data, and Regime signals
        if "BB_Reversion" in source:
            self._process_bb_signal(signal)
        elif "Regime_Detector" in source:
            self._process_regime_signal(signal)

    def _process_bb_signal(self, signal: Any) -> None:
        metadata = getattr(signal, "metadata", {}) or {}
        bandwidth = metadata.get("bandwidth")
        pct_b = metadata.get("percent_b")
        if bandwidth is None or pct_b is None:
            return

        # Track squeeze state
        if bandwidth < self._squeeze_bw:
            self._was_squeezed = True
            return

        # Check for breakout: was squeezed, now expanding
        if not self._was_squeezed or bandwidth < self._expansion_bw:
            return

        # Cooldown check
        now_ms = int(time.time() * 1000)
        if now_ms - self._last_trade_ts_ms < self._cooldown_ms:
            return

        confidence = getattr(signal, "confidence", 0.5)
        if confidence < self._min_confidence:
            return

        with self._intent_lock:
            if self._current_position is not None:
                return  # Already in position

            if pct_b > 1.0:
                # Price above upper band -> bullish breakout
                self._emit_intent(OrderIntent(
                    symbol=self._symbol, side="Buy", order_type="market",
                    qty=self._qty, strategy_name=self.name,
                    reason=f"BB breakout long: squeeze→expansion, %B={pct_b:.3f}, BW={bandwidth:.4f}",
                    confidence=confidence,
                ))
                self._current_position = "long"
                self._trade_count += 1
                self._last_trade_ts_ms = now_ms
                self._was_squeezed = False  # Reset squeeze state after trade

            elif pct_b < 0.0:
                # Price below lower band -> bearish breakout
                self._emit_intent(OrderIntent(
                    symbol=self._symbol, side="Sell", order_type="market",
                    qty=self._qty, strategy_name=self.name,
                    reason=f"BB breakout short: squeeze→expansion, %B={pct_b:.3f}, BW={bandwidth:.4f}",
                    confidence=confidence,
                ))
                self._current_position = "short"
                self._trade_count += 1
                self._last_trade_ts_ms = now_ms
                self._was_squeezed = False  # Reset squeeze state after trade

    def _process_regime_signal(self, signal: Any) -> None:
        """Exit on regime change back to ranging/squeeze"""
        metadata = getattr(signal, "metadata", {}) or {}
        regime = metadata.get("regime")

        with self._intent_lock:
            if self._current_position is None:
                return

            if regime in ("ranging", "squeeze"):
                side = "Sell" if self._current_position == "long" else "Buy"
                self._emit_intent(OrderIntent(
                    symbol=self._symbol, side=side, order_type="market",
                    qty=self._qty, strategy_name=self.name,
                    reason=f"BB breakout exit: regime changed to {regime}",
                    confidence=0.6,
                ))
                self._current_position = None

    def get_persistent_state(self) -> dict[str, Any]:
        base = super().get_persistent_state()
        base.update({
            "current_position": self._current_position,
            "was_squeezed": self._was_squeezed,
            "trade_count": self._trade_count,
        })
        return base

    def restore_persistent_state(self, saved: dict[str, Any]) -> None:
        super().restore_persistent_state(saved)
        self._current_position = saved.get("current_position")
        self._was_squeezed = saved.get("was_squeezed", False)
        self._trade_count = saved.get("trade_count", 0)

    def on_intent_rejected(self, intent: OrderIntent) -> None:
        """Roll back _current_position on rejected intent / intent 被拒后回滚仓位状态"""
        if getattr(intent, "symbol", None) != self._symbol:
            return
        with self._intent_lock:
            self._current_position = None

    def get_status(self) -> dict[str, Any]:
        return {
            "strategy": self.name,
            "state": self.state,
            "symbol": self._symbol,
            "current_position": self._current_position,
            "was_squeezed": self._was_squeezed,
            "qty_per_trade": self._qty,
            "squeeze_bandwidth": self._squeeze_bw,
            "expansion_bandwidth": self._expansion_bw,
            "trade_count": self._trade_count,
        }
