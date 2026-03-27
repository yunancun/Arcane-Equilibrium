"""
MACD — Moving Average Convergence Divergence / 移动平均收敛发散指标

MODULE_NOTE (中文):
  MACD 是经典的趋势跟踪 + 动量指标，由三部分组成：
  1. MACD 线 = EMA(fast) - EMA(slow)，反映短期与长期趋势的差异
  2. Signal 线 = EMA(MACD 线, signal_period)，MACD 的平滑版本
  3. Histogram = MACD 线 - Signal 线，直观显示动量变化

  默认参数（经典设置）：fast=12, slow=26, signal=9
  这些参数由 Gerald Appel 在 1979 年提出，至今仍是最广泛使用的默认值。

  在本系统中的用途：
  1. 趋势方向 — MACD > 0 趋势向上，MACD < 0 趋势向下
  2. 交叉信号 — MACD 穿越 Signal 线 = 买入/卖出信号
  3. 零轴交叉 — MACD 穿越零轴 = 趋势反转
  4. 柱状图动量 — Histogram 由大变小 = 动量减弱
  5. 背离 — 价格新高/新低但 MACD 没有跟随 = 潜在反转

MODULE_NOTE (English):
  MACD is a classic trend-following + momentum indicator with three components:
  1. MACD line = EMA(fast) - EMA(slow), reflects difference between short/long-term trends
  2. Signal line = EMA(MACD line, signal_period), smoothed version of MACD
  3. Histogram = MACD line - Signal line, visually shows momentum changes

  Default parameters (classic): fast=12, slow=26, signal=9
  Proposed by Gerald Appel in 1979, still the most widely used defaults.

  Uses in this system:
  1. Trend direction — MACD > 0 = uptrend, MACD < 0 = downtrend
  2. Crossover signals — MACD crosses Signal = buy/sell signal
  3. Zero-line cross — MACD crosses zero = trend reversal
  4. Histogram momentum — histogram shrinking = momentum weakening
  5. Divergence — price makes new high/low but MACD doesn't = potential reversal

Safety invariant / 安全不变量:
  - 纯数学计算 / Pure math computation
"""

from __future__ import annotations

from typing import Any

from .base import IndicatorBase
from .moving_averages import compute_ema_series


def compute_macd(
    close: list[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> dict[str, float] | None:
    """
    Compute MACD, Signal, and Histogram.
    计算 MACD、Signal 和 Histogram。

    Args:
      close         — close prices (newest last) / 收盘价列表
      fast_period   — fast EMA period (default 12) / 快速 EMA 周期
      slow_period   — slow EMA period (default 26) / 慢速 EMA 周期
      signal_period — signal line EMA period (default 9) / 信号线 EMA 周期

    Returns:
      {"macd": float, "signal": float, "histogram": float} or None
    """
    min_needed = slow_period + signal_period
    if len(close) < min_needed or fast_period <= 0 or slow_period <= 0 or signal_period <= 0:
        return None

    # Step 1: Compute fast and slow EMA series / 计算快慢 EMA 序列
    fast_ema = compute_ema_series(close, fast_period)
    slow_ema = compute_ema_series(close, slow_period)

    if not fast_ema or not slow_ema:
        return None

    # Step 2: MACD line = fast EMA - slow EMA / MACD 线 = 快速 EMA - 慢速 EMA
    # Only valid where both EMAs have values (from slow_period-1 onwards)
    # 只有两个 EMA 都有值的位置才有效（从 slow_period-1 开始）
    macd_line = []
    for i in range(len(close)):
        if i < slow_period - 1:
            macd_line.append(0.0)
        else:
            macd_line.append(fast_ema[i] - slow_ema[i])

    # Step 3: Signal line = EMA of MACD line / Signal 线 = MACD 线的 EMA
    # Use only the valid portion of MACD line (from slow_period-1 onwards)
    # 仅使用 MACD 线的有效部分
    valid_macd = macd_line[slow_period - 1:]
    if len(valid_macd) < signal_period:
        return None

    signal_series = compute_ema_series(valid_macd, signal_period)
    if not signal_series:
        return None

    # Latest values / 最新值
    macd_val = macd_line[-1]
    signal_val = signal_series[-1]
    histogram_val = macd_val - signal_val

    return {
        "macd": macd_val,
        "signal": signal_val,
        "histogram": histogram_val,
    }


class MACD(IndicatorBase):
    """
    MACD (Moving Average Convergence Divergence) indicator.
    MACD（移动平均收敛发散）指标。

    Usage:
      macd = MACD(fast=12, slow=26, signal=9)
      result = macd.compute(close=[...])
      # → {"macd": 150.5, "signal": 120.3, "histogram": 30.2}
    """

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ) -> None:
        """
        Args:
          fast_period   — fast EMA period (default 12) / 快速 EMA 周期
          slow_period   — slow EMA period (default 26) / 慢速 EMA 周期
          signal_period — signal EMA period (default 9) / 信号线 EMA 周期
        """
        self._fast = fast_period
        self._slow = slow_period
        self._signal = signal_period

    @property
    def name(self) -> str:
        return f"MACD({self._fast},{self._slow},{self._signal})"

    @property
    def min_periods(self) -> int:
        # Need slow_period for EMA + signal_period for signal line EMA
        # 需要 slow_period 来计算 EMA + signal_period 来计算信号线 EMA
        return self._slow + self._signal

    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        """
        Compute MACD from close prices.
        从收盘价计算 MACD。

        Args:
          close — list of close prices (newest last) / 收盘价列表

        Returns:
          {"macd": float, "signal": float, "histogram": float} or None
        """
        close = kwargs.get("close", [])
        return compute_macd(close, self._fast, self._slow, self._signal)
