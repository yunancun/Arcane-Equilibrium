"""
Bollinger Band Mean Reversion Strategy / 布林带均值回归策略

MODULE_NOTE (中文):
  均值回归策略 V2：当价格触及布林带下轨（且 RSI 确认超卖）时做多，
  价格回归中轨时平仓。上轨对称处理做空。

  核心假设：价格偏离均值后倾向于回归。
  适用场景：震荡/区间市场
  不适用：强单边趋势（会持续突破布林带）

  入场条件：
  1. %B < 0.1（价格接近或低于下轨）→ 做多
  2. RSI < 40 确认超卖
  3. 带宽 > 0.01（非收窄期）

  V2 升级（Phase 2-2）：
  1. RSI < 30 确认（做多）/ RSI > 70 确认（做空）— 比 V1 更严格
  2. Regime 感知 — trending 市场不做反转交易（基于 Hurst 滞后判定）
  3. Limit order 预留 — Phase 2 预设关闭，未来可开启

  出场条件：
  1. %B 回归到 0.4-0.6（接近中轨）→ 平仓获利
  2. %B 进一步恶化（极端情况）→ 由风控止损

MODULE_NOTE (English):
  Mean reversion strategy V2: go long when price touches lower Bollinger Band
  (with RSI oversold confirmation), close when price reverts to middle band.
  Short is symmetric for upper band.

  Core assumption: prices tend to revert to the mean after deviation.
  Suitable: ranging/sideways markets
  Not suitable: strong trending markets (will keep breaking through bands)

  V2 upgrades (Phase 2-2):
  1. RSI < 30 confirmation (long) / RSI > 70 confirmation (short) — stricter than V1
  2. Regime awareness — skip mean reversion in trending markets (Hurst-based)
  3. Limit order placeholder — disabled by default, future enablement

Safety invariant / 安全不变量:
  - 只产生 OrderIntent / Only generates OrderIntents
"""

from __future__ import annotations

from typing import Any

from .base import OrderIntent, StrategyBase, STRATEGY_ACTIVE


class BollingerReversionStrategy(StrategyBase):
    """
    Bollinger Band mean reversion strategy.
    布林带均值回归策略。

    Parameters:
      symbol              — trading pair / 交易对
      qty_per_trade       — position size / 每次仓位
      entry_pct_b         — %B threshold for entry (default 0.1) / 入场 %B 阈值
      exit_pct_b          — %B threshold for exit (default 0.5) / 出场 %B 阈值
      min_confidence      — minimum signal confidence / 最小信号置信度
      rsi_threshold       — RSI must be below this for long entry (V2) / 做多入场 RSI 上限
      rsi_short_threshold — RSI must be above this for short entry (V2) / 做空入场 RSI 下限
      regime_aware        — skip entries in trending regime (V2) / 趋势市场跳过入场
      use_limit_orders    — use limit orders instead of market (V2 placeholder) / 限价单预留
    """

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        qty_per_trade: float = 0.001,
        entry_pct_b: float = 0.1,
        exit_pct_b: float = 0.5,
        min_confidence: float = 0.35,
        # V2 parameters / V2 参数
        rsi_threshold: float = 30.0,
        rsi_short_threshold: float = 70.0,
        regime_aware: bool = True,
        use_limit_orders: bool = False,
    ) -> None:
        super().__init__()
        if qty_per_trade <= 0:
            raise ValueError(f"qty_per_trade must be > 0, got {qty_per_trade} / 每笔数量必须大于 0")
        self._symbol = symbol
        self._qty = qty_per_trade
        self._entry_pct_b = entry_pct_b
        self._exit_pct_b = exit_pct_b
        self._min_confidence = min_confidence
        self._current_position: str | None = None
        self._entry_pct_b_at_open: float | None = None  # %B when we opened / 开仓时的 %B
        self._trade_count = 0
        # V2 state / V2 状态
        self._rsi_threshold = rsi_threshold
        self._rsi_short_threshold = rsi_short_threshold
        self._regime_aware = regime_aware
        self._use_limit_orders = use_limit_orders

    @property
    def name(self) -> str:
        return "BB_Reversion"

    @property
    def description(self) -> str:
        return (
            "布林带均值回归策略 V2 / Bollinger Band Mean Reversion V2. "
            "RSI<{} 确认 + Regime 感知 + %B 回归中轨".format(self._rsi_threshold)
        )

    def on_signal(self, signal: Any) -> None:
        """Process BB reversion signals / 处理布林带回归信号"""
        if self._state != STRATEGY_ACTIVE:
            return
        if getattr(signal, "symbol", "") != self._symbol:
            return
        if getattr(signal, "confidence", 0) < self._min_confidence:
            return

        with self._intent_lock:  # Protect _current_position read+write+emit atomically / 原子保护仓位状态
            # Check exit conditions on any BB signal when we have a position
            # 当有持仓时，在收到任何 BB 信号时检查出场条件
            if self._current_position is not None and "BB_Reversion" in getattr(signal, "source", ""):
                pct_b = getattr(signal, "metadata", {}).get("percent_b")
                if pct_b is not None:
                    self._check_exit_locked(pct_b)
                    if self._current_position is None:
                        return  # Exited, don't process entry / 已出场，不处理入场

            source = getattr(signal, "source", "")
            direction = getattr(signal, "direction", "")

            if "BB_Reversion" not in source:
                return

            # --- V2 filters (applied before entry) / V2 过滤（入场前应用） ---

            # V2: RSI confirmation filter — stricter than V1 implicit RSI<40
            # RSI 确认过滤 — 比 V1 隐含的 RSI<40 更严格
            signal_meta = getattr(signal, "metadata", {}) or {}
            signal_rsi = signal_meta.get("rsi")
            if signal_rsi is not None:
                if direction == "long" and signal_rsi > self._rsi_threshold:
                    return  # Not oversold enough / 未充分超卖
                if direction == "short" and signal_rsi < self._rsi_short_threshold:
                    return  # Not overbought enough / 未充分超买

            # V2: Regime awareness — skip mean reversion in trending markets
            # Regime 感知 — 趋势市场中跳过均值回归交易
            # Hurst-based regime comes via signal metadata / 基于 Hurst 的 regime 通过信号元数据传递
            if self._regime_aware:
                signal_regime = signal_meta.get("_regime", "unknown")
                hurst_regime = signal_meta.get("_hurst_regime", "uncertain")
                # In trending markets, mean reversion is dangerous
                # 趋势市场中均值回归是危险的
                if signal_regime in ("trending_up", "trending_down") or hurst_regime == "trending":
                    return

            # --- End V2 filters / V2 过滤结束 ---

            # Entry: open position based on BB signal / 入场：根据 BB 信号开仓
            if direction == "long" and self._current_position is None:
                self._emit_intent(OrderIntent(
                    symbol=self._symbol, side="Buy", order_type="market",
                    qty=self._qty, strategy_name=self.name,
                    reason=(
                        f"BB reversion long: price near lower band / "
                        f"布林带回归做多：价格接近下轨, conf={signal.confidence:.2f}"
                    ),
                    confidence=signal.confidence,
                ))
                self._current_position = "long"
                self._trade_count += 1

            elif direction == "short" and self._current_position is None:
                self._emit_intent(OrderIntent(
                    symbol=self._symbol, side="Sell", order_type="market",
                    qty=self._qty, strategy_name=self.name,
                    reason=(
                        f"BB reversion short: price near upper band / "
                        f"布林带回归做空：价格接近上轨, conf={signal.confidence:.2f}"
                    ),
                    confidence=signal.confidence,
                ))
                self._current_position = "short"
                self._trade_count += 1

    def check_exit(self, pct_b: float) -> None:
        """
        Check if position should be closed based on %B reversion to mean.
        根据 %B 回归均值检查是否应平仓。

        Called by the strategy orchestrator with current %B value.
        由策略编排器传入当前 %B 值调用。

        Args:
          pct_b — current Bollinger %B value / 当前布林带 %B 值
        """
        with self._intent_lock:  # Protect _current_position read+write atomically / 原子保护仓位状态
            self._check_exit_locked(pct_b)

    def _check_exit_locked(self, pct_b: float) -> None:
        """Internal: check exit while _intent_lock is already held / 内部：在已持有锁时检查出场"""
        if self._state != STRATEGY_ACTIVE or self._current_position is None:
            return

        # Long position: exit when %B reverts above exit threshold / 多仓：%B 回升到出场阈值上方平仓
        if self._current_position == "long" and pct_b >= self._exit_pct_b:
            self._emit_intent(OrderIntent(
                symbol=self._symbol, side="Sell", order_type="market",
                qty=self._qty, strategy_name=self.name,
                reason=(
                    f"BB reversion exit long: %%B={pct_b:.3f} reverted to mean / "
                    f"布林带回归平多：%%B={pct_b:.3f} 已回归均值"
                ),
                confidence=0.7,
            ))
            self._current_position = None

        # Short position: exit when %B reverts below exit threshold / 空仓：%B 回落到出场阈值下方平仓
        elif self._current_position == "short" and pct_b <= (1.0 - self._exit_pct_b):
            self._emit_intent(OrderIntent(
                symbol=self._symbol, side="Buy", order_type="market",
                qty=self._qty, strategy_name=self.name,
                reason=(
                    f"BB reversion exit short: %%B={pct_b:.3f} reverted to mean / "
                    f"布林带回归平空：%%B={pct_b:.3f} 已回归均值"
                ),
                confidence=0.7,
            ))
            self._current_position = None

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
            "qty_per_trade": self._qty,
            "entry_pct_b": self._entry_pct_b,
            "exit_pct_b": self._exit_pct_b,
            "trade_count": self._trade_count,
            # V2 parameters / V2 参数
            "rsi_threshold": self._rsi_threshold,
            "rsi_short_threshold": self._rsi_short_threshold,
            "regime_aware": self._regime_aware,
            "use_limit_orders": self._use_limit_orders,
        }
