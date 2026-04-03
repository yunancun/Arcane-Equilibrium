"""
MA Crossover Strategy V2 / 均线交叉策略 V2

MODULE_NOTE (中文):
  经典的趋势跟踪策略：当快速均线上穿慢速均线时做多，下穿时做空。
  结合 regime 过滤、ADX 趋势强度确认和多时间框架方向一致性过滤假信号。

  适用场景：趋势明显的市场
  不适用：震荡/横盘市场（会频繁假突破）

  入场条件：
  1. MA/KAMA 交叉信号（快线穿越慢线）
  2. Regime 过滤（排除 ranging）
  3. ADX > 20 趋势强度确认
  4. 多时间框架方向一致性确认

  出场条件：
  1. 反向交叉信号
  2. 硬止损（由风控框架管理）

  V2 升级（Phase 2-1）：
  1. KAMA 替代 EMA — 自适应平滑，趋势市跟随、震荡市平滑
  2. ADX > 20 过滤 — 只在有趋势时交易
  3. 多时间框架确认 — 要求更高 TF 同向

MODULE_NOTE (English):
  Trend-following strategy V2: go long when fast MA crosses above slow MA,
  go short when it crosses below. Filters false signals with regime detection,
  ADX trend strength confirmation, and multi-timeframe directional alignment.

  Suitable: trending markets
  Not suitable: ranging/sideways markets (frequent false breakouts)

  V2 upgrades (Phase 2-1):
  1. KAMA replaces EMA — adaptive smoothing, follows trends, flattens in chop
  2. ADX > 20 filter — only trade when a trend exists
  3. Multi-timeframe confirmation — require higher TF directional agreement

Safety invariant / 安全不变量:
  - 只产生 OrderIntent / Only generates OrderIntents
"""

from __future__ import annotations

import logging
import time
from typing import Any

from .base import OrderIntent, StrategyBase, STRATEGY_ACTIVE

logger = logging.getLogger(__name__)


class MACrossoverStrategy(StrategyBase):
    """
    Moving Average Crossover trend-following strategy V2.
    均线交叉趋势跟踪策略 V2。

    V2 adds KAMA signal support, ADX trend strength filtering, and
    multi-timeframe directional confirmation on top of V1 regime filtering.
    V2 在 V1 regime 过滤基础上新增 KAMA 信号支持、ADX 趋势强度过滤、
    多时间框架方向确认。

    Parameters:
      symbol            — trading pair / 交易对
      qty_per_trade     — position size per trade / 每次交易仓位
      min_confidence    — minimum signal confidence / 最小信号置信度
      cooldown_ms       — cooldown between trades in ms / 交易冷却期（毫秒）
      adx_threshold     — ADX minimum for trend confirmation / ADX 趋势确认最低值
      use_kama          — accept KAMA crossover signals / 接受 KAMA 交叉信号
      multi_tf_confirm  — require higher-TF directional agreement / 要求更高 TF 同向
    """

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        qty_per_trade: float = 0.001,
        min_confidence: float = 0.3,
        cooldown_ms: int = 300_000,
        # V2 parameters / V2 参数
        adx_threshold: float = 20.0,      # ADX minimum for trend confirmation / ADX 趋势确认最低值
        use_kama: bool = True,             # Use KAMA signals instead of EMA / 使用 KAMA 信号替代 EMA
        multi_tf_confirm: bool = True,     # Require multi-timeframe confirmation / 需要多时间框架确认
    ) -> None:
        super().__init__()
        if qty_per_trade <= 0:
            raise ValueError(f"qty_per_trade must be > 0, got {qty_per_trade} / 每笔数量必须大于 0")
        self._symbol = symbol
        self._qty = qty_per_trade
        self._min_confidence = min_confidence
        # V2 config / V2 配置
        self._adx_threshold: float = adx_threshold
        self._use_kama: bool = use_kama
        self._multi_tf_confirm: bool = multi_tf_confirm
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
            "均线交叉趋势跟踪策略 V2 / MA Crossover V2 trend-following strategy. "
            "KAMA + ADX>{} 确认 + 多时间框架".format(self._adx_threshold)
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

        # V2: Accept both EMA and KAMA crossover signals
        # V2：同时接受 EMA 和 KAMA 交叉信号
        if "MA_Cross" not in source and "KAMA_Cross" not in source:
            return

        with self._intent_lock:  # Protect _current_position read+write+emit atomically / 原子保护仓位状态
            # Multi-TF regime filter: skip trend-following in ranging markets
            # 多时间框架 regime 过滤：震荡市场中跳过趋势跟踪
            # "unknown" passes through — cold-start symbols still need to trade for learning.
            # "squeeze" passes through — low volatility but crossover signals still valid.
            # "trending" and "volatile" pass through (favorable for trend-following).
            # Only "ranging" is filtered (MA crossover whipsaws badly in ranging markets).
            # 注意："unknown" 和 "squeeze" 允许通过 — 冷启动品种和窄幅盘整仍可交易以积累学习数据。
            # 仅 "ranging" 被过滤（MA 交叉在震荡市场中频繁假突破）。
            signal_regime = getattr(signal, "metadata", {}).get("_regime", "unknown")
            if signal_regime == "ranging":
                return

            # V2 Step 2: ADX trend strength filter — only trade when ADX > threshold
            # ADX 趋势强度过滤 — 只在 ADX > 阈值时交易
            # ADX data comes from IndicatorEngine via signal metadata
            # ADX 数据来自 IndicatorEngine 通过信号元数据
            _metadata = getattr(signal, "metadata", {}) or {}
            signal_adx = _metadata.get("adx")
            if self._adx_threshold > 0 and signal_adx is not None:
                if signal_adx < self._adx_threshold:
                    return  # No trend / 无趋势

            # V2 Step 3: Multi-timeframe confirmation
            # 多时间框架确认 — 要求更高时间框架同向
            # Higher TF regime comes from signal metadata (set by SignalEngine)
            # 更高 TF regime 来自信号元数据（由 SignalEngine 设置）
            if self._multi_tf_confirm:
                htf_direction = _metadata.get("htf_direction")
                if htf_direction is not None and htf_direction != direction:
                    return  # Higher timeframe disagrees / 更高时间框架方向不一致

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

    def on_intent_rejected(self, intent: OrderIntent) -> None:
        """
        Roll back optimistic _current_position when intent is rejected by pipeline gates.
        当 intent 被管线门控拒绝时，回滚乐观的 _current_position 状态。

        Without this, a rejected "Open short" leaves _current_position="short" but Paper Engine
        has no position — subsequent "Close short" accidentally opens a long position.
        若不回滚，被拒的「开空」会留下 _current_position="short"，但 Paper Engine 无仓位，
        后续「平空」信号会意外开多。（2026-04-01 PIPPINUSDT 复现案例）
        """
        if getattr(intent, "symbol", None) != self._symbol:
            return
        with self._intent_lock:
            self._current_position = None
            logger.info(
                "MA_Crossover %s: position reset to None after intent rejected / "
                "intent 被拒后仓位回滚为 None",
                self._symbol,
            )

    def on_fill(self, fill: dict, is_open: bool) -> None:
        """
        Sync internal position state from confirmed fill.
        从已确认的成交同步内部仓位状态，防止意图态与实际仓位漂移。
        """
        if fill.get("symbol") != self._symbol:
            return
        with self._intent_lock:
            if is_open:
                self._current_position = "long" if fill.get("side") == "Buy" else "short"
            else:
                self._current_position = None

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
            # V2 parameters / V2 参数
            "adx_threshold": self._adx_threshold,
            "use_kama": self._use_kama,
            "multi_tf_confirm": self._multi_tf_confirm,
        }
