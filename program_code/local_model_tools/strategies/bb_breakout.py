"""
Bollinger Band Breakout Strategy V2 / 布林带突破策略 V2

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

  V2 升级（Phase 2-3）：
  1. Volume ratio > 1.5 确认 — 拒绝低量假突破
  2. Donchian(20) 确认 — 价格需同时突破 Donchian 通道
  3. ATR trailing stop — 动态追踪止损，保留趋势仓位

  出场条件：
  1. 价格回到带内（%B 回到 0.2-0.8）
  2. V2: ATR trailing stop 触发
  3. StopManager 硬止损

MODULE_NOTE (English):
  Detects Bollinger Band squeeze-to-expansion breakouts.
  Complementary to BB Reversion (reversion = ranging, breakout = trending).

  V2 upgrades (Phase 2-3):
  1. Volume ratio > 1.5 confirmation — reject low-volume false breakouts
  2. Donchian(20) confirmation — price must also breach Donchian channel
  3. ATR trailing stop — dynamic trailing stop to ride trends

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
        # V2 parameters / V2 参数
        volume_ratio_threshold: float = 1.5,  # Volume must be 1.5x average / 成交量需达平均 1.5 倍
        donchian_confirm: bool = True,        # Require Donchian channel breakout / 需要 Donchian 通道突破确认
        atr_trailing_mult: float = 2.0,       # ATR multiplier for trailing stop / ATR 追踪止损倍率
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
        # V2 state / V2 状态
        self._volume_ratio_th = volume_ratio_threshold
        self._donchian_confirm = donchian_confirm
        self._atr_trailing_mult = atr_trailing_mult
        self._entry_price: float | None = None       # Entry price for trailing stop / 入场价格
        self._trailing_stop: float | None = None     # Current trailing stop price / 当前追踪止损价

    @property
    def name(self) -> str:
        return "BB_Breakout"

    @property
    def description(self) -> str:
        return "布林带突破策略 V2 / BB Breakout V2: squeeze→expansion + volume + Donchian + ATR trailing"

    def on_signal(self, signal: Any) -> None:
        if self._state != STRATEGY_ACTIVE:
            return
        if getattr(signal, "symbol", "") != self._symbol:
            return

        # B3: Check ATR trailing stop on every signal when position is open
        # B3：有持仓时每次信号都检查 ATR 追踪止损
        if self._current_position is not None:
            metadata = getattr(signal, "metadata", {}) or {}
            # Try to get ATR and close price from signal metadata or _indicators
            # 尝试从信号 metadata 或 _indicators 获取 ATR 和收盘价
            atr_val = metadata.get("atr")
            sig_price = metadata.get("close", 0)
            if atr_val is None or sig_price == 0:
                ind_snapshot = metadata.get("_indicators", {})
                if isinstance(ind_snapshot, dict):
                    atr_data = ind_snapshot.get("ATR(14)")
                    if isinstance(atr_data, dict) and "atr" in atr_data:
                        atr_val = atr_data["atr"]
                    if sig_price == 0:
                        bb_data = ind_snapshot.get("BB(20,2.0)")
                        if isinstance(bb_data, dict) and "middle" in bb_data:
                            sig_price = bb_data["middle"]
            if atr_val is not None and sig_price > 0:
                self.check_trailing_stop(self._symbol, sig_price, atr_val)

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

        # V2: Volume ratio confirmation — reject low-volume breakouts (false breakouts)
        # 成交量比率确认 — 拒绝低量突破（假突破）
        volume_ratio = metadata.get("volume_ratio")
        if volume_ratio is not None and volume_ratio < self._volume_ratio_th:
            return  # Low volume breakout, likely false / 低量突破，可能是假的

        # V2: Donchian channel confirmation — price must also break Donchian boundary
        # Donchian 通道确认 — 价格也需突破 Donchian 边界
        current_price = metadata.get("close", 0)
        if self._donchian_confirm:
            donchian_high = metadata.get("donchian_high")
            donchian_low = metadata.get("donchian_low")
            if donchian_high is not None and donchian_low is not None and current_price > 0:
                if pct_b > 1.0 and current_price < donchian_high:
                    return  # BB breakout up but not Donchian breakout / BB 向上突破但未突破 Donchian
                if pct_b < 0.0 and current_price > donchian_low:
                    return  # BB breakout down but not Donchian breakout / BB 向下突破但未突破 Donchian

        with self._intent_lock:
            if self._current_position is not None:
                return  # Already in position

            if pct_b > 1.0:
                # Price above upper band -> bullish breakout
                # 价格突破上轨 -> 多头突破
                self._emit_intent(OrderIntent(
                    symbol=self._symbol, side="Buy", order_type="market",
                    qty=self._qty, strategy_name=self.name,
                    reason=f"BB breakout long: squeeze→expansion, %B={pct_b:.3f}, BW={bandwidth:.4f}",
                    confidence=confidence,
                ))
                self._current_position = "long"
                self._entry_price = current_price if current_price > 0 else None
                self._trailing_stop = None  # Reset trailing stop for new position / 新仓位重置追踪止损
                self._trade_count += 1
                self._last_trade_ts_ms = now_ms
                self._was_squeezed = False  # Reset squeeze state after trade

            elif pct_b < 0.0:
                # Price below lower band -> bearish breakout
                # 价格突破下轨 -> 空头突破
                self._emit_intent(OrderIntent(
                    symbol=self._symbol, side="Sell", order_type="market",
                    qty=self._qty, strategy_name=self.name,
                    reason=f"BB breakout short: squeeze→expansion, %B={pct_b:.3f}, BW={bandwidth:.4f}",
                    confidence=confidence,
                ))
                self._current_position = "short"
                self._entry_price = current_price if current_price > 0 else None
                self._trailing_stop = None  # Reset trailing stop for new position / 新仓位重置追踪止损
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
                self._entry_price = None       # V2: reset on exit / 出场时重置
                self._trailing_stop = None     # V2: reset on exit / 出场时重置

    def check_trailing_stop(self, symbol: str, price: float, atr_value: float) -> None:
        """
        V2: Check ATR-based trailing stop and exit if triggered.
        V2：检查基于 ATR 的追踪止损，触发时出场。

        Args:
            symbol: trading pair / 交易对
            price: current price / 当前价格
            atr_value: current ATR value / 当前 ATR 值
        """
        if self._state != STRATEGY_ACTIVE or symbol != self._symbol:
            return

        with self._intent_lock:
            if self._current_position is None or self._entry_price is None:
                return

            stop_distance = atr_value * self._atr_trailing_mult

            if self._current_position == "long":
                # Update trailing stop to max(current_stop, price - ATR*mult)
                # 追踪止损上移至 max(当前止损, 价格 - ATR*倍率)
                new_stop = price - stop_distance
                if self._trailing_stop is None or new_stop > self._trailing_stop:
                    self._trailing_stop = new_stop

                if price <= self._trailing_stop:
                    self._emit_intent(OrderIntent(
                        symbol=self._symbol, side="Sell", order_type="market",
                        qty=self._qty, strategy_name=self.name,
                        reason=(
                            f"V2 ATR trailing stop hit: price={price:.2f} <= stop={self._trailing_stop:.2f} "
                            f"(ATR={atr_value:.2f}×{self._atr_trailing_mult})"
                        ),
                        confidence=0.7,
                    ))
                    self._current_position = None
                    self._entry_price = None
                    self._trailing_stop = None
                    self._was_squeezed = False

            elif self._current_position == "short":
                # Update trailing stop to min(current_stop, price + ATR*mult)
                # 追踪止损下移至 min(当前止损, 价格 + ATR*倍率)
                new_stop = price + stop_distance
                if self._trailing_stop is None or new_stop < self._trailing_stop:
                    self._trailing_stop = new_stop

                if price >= self._trailing_stop:
                    self._emit_intent(OrderIntent(
                        symbol=self._symbol, side="Buy", order_type="market",
                        qty=self._qty, strategy_name=self.name,
                        reason=(
                            f"V2 ATR trailing stop hit: price={price:.2f} >= stop={self._trailing_stop:.2f} "
                            f"(ATR={atr_value:.2f}×{self._atr_trailing_mult})"
                        ),
                        confidence=0.7,
                    ))
                    self._current_position = None
                    self._entry_price = None
                    self._trailing_stop = None
                    self._was_squeezed = False

    def get_persistent_state(self) -> dict[str, Any]:
        base = super().get_persistent_state()
        base.update({
            "current_position": self._current_position,
            "was_squeezed": self._was_squeezed,
            "trade_count": self._trade_count,
            "entry_price": self._entry_price,         # V2
            "trailing_stop": self._trailing_stop,     # V2
        })
        return base

    def restore_persistent_state(self, saved: dict[str, Any]) -> None:
        super().restore_persistent_state(saved)
        self._current_position = saved.get("current_position")
        self._was_squeezed = saved.get("was_squeezed", False)
        self._trade_count = saved.get("trade_count", 0)
        self._entry_price = saved.get("entry_price")          # V2
        self._trailing_stop = saved.get("trailing_stop")      # V2

    def on_intent_rejected(self, intent: OrderIntent) -> None:
        """Roll back _current_position on rejected intent / intent 被拒后回滚仓位状态"""
        if getattr(intent, "symbol", None) != self._symbol:
            return
        with self._intent_lock:
            self._current_position = None
            self._entry_price = None       # V2: reset on rejection / 拒绝时重置
            self._trailing_stop = None     # V2: reset on rejection / 拒绝时重置

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
            "volume_ratio_threshold": self._volume_ratio_th,    # V2
            "donchian_confirm": self._donchian_confirm,          # V2
            "atr_trailing_mult": self._atr_trailing_mult,        # V2
            "entry_price": self._entry_price,                    # V2
            "trailing_stop": self._trailing_stop,                # V2
        }
