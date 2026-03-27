"""
Stochastic Oscillator / 随机振荡指标

MODULE_NOTE (中文):
  随机振荡指标由 George Lane 在 1950 年代发明，衡量收盘价相对于最近 N 周期价格范围的位置。
  两条线：
  1. %K = (close - lowest_low) / (highest_high - lowest_low) × 100
  2. %D = SMA(%K, d_period)  — %K 的平滑版本

  取值范围 0-100：
  - %K > 80: 超买（价格接近近期最高点）
  - %K < 20: 超卖（价格接近近期最低点）

  在本系统中的用途：
  1. 超买超卖确认 — 与 RSI 配合使用，双重确认更可靠
  2. %K/%D 交叉 — %K 上穿 %D 且在超卖区 → 买入信号
  3. 背离检测 — 价格新低但 %K 没新低 → 看涨背离

MODULE_NOTE (English):
  Stochastic Oscillator, invented by George Lane in the 1950s, measures where the
  close price is relative to the recent N-period price range.
  Two lines:
  1. %K = (close - lowest_low) / (highest_high - lowest_low) × 100
  2. %D = SMA(%K, d_period) — smoothed version of %K

  Range 0-100:
  - %K > 80: overbought (price near recent highs)
  - %K < 20: oversold (price near recent lows)

  Uses in this system:
  1. Overbought/oversold confirmation — paired with RSI for double confirmation
  2. %K/%D crossover — %K crosses above %D in oversold zone → buy signal
  3. Divergence detection — price makes new low but %K doesn't → bullish divergence

Safety invariant / 安全不变量:
  - 纯数学计算 / Pure math computation
"""

from __future__ import annotations

from typing import Any

from .base import IndicatorBase
from .moving_averages import compute_sma


def compute_stochastic(
    high: list[float],
    low: list[float],
    close: list[float],
    k_period: int = 14,
    d_period: int = 3,
) -> dict[str, float] | None:
    """
    Compute Stochastic %K and %D.
    计算随机振荡指标 %K 和 %D。

    Args:
      high     — high prices / 最高价
      low      — low prices / 最低价
      close    — close prices / 收盘价
      k_period — %K lookback period (default 14) / %K 回看周期
      d_period — %D smoothing period (default 3) / %D 平滑周期

    Returns:
      {"k": float, "d": float} or None
    """
    n = min(len(high), len(low), len(close))
    if n < k_period + d_period - 1 or k_period <= 0 or d_period <= 0:
        return None

    # Compute %K series / 计算 %K 序列
    k_values = []
    for i in range(k_period - 1, n):
        window_high = high[i - k_period + 1: i + 1]
        window_low = low[i - k_period + 1: i + 1]
        highest = max(window_high)
        lowest = min(window_low)
        diff = highest - lowest
        if diff == 0:
            # No price range in the window → return neutral 50.0 (by design).
            # This means the asset is flat; %K at midpoint is the correct neutral value.
            # 窗口内无价格波动 → 返回中性值 50.0（设计决策：平盘时 %K 取中点是正确的中性值）
            k_values.append(50.0)
        else:
            k_val = ((close[i] - lowest) / diff) * 100.0
            k_values.append(k_val)

    if len(k_values) < d_period:
        return None

    # %D = SMA of %K / %D = %K 的 SMA
    d_val = compute_sma(k_values, d_period)
    if d_val is None:
        return None

    return {
        "k": k_values[-1],
        "d": d_val,
    }


class Stochastic(IndicatorBase):
    """
    Stochastic Oscillator indicator.
    随机振荡指标。

    Usage:
      stoch = Stochastic(k_period=14, d_period=3)
      result = stoch.compute(high=[...], low=[...], close=[...])
      # → {"k": 25.3, "d": 30.1}
    """

    def __init__(self, k_period: int = 14, d_period: int = 3) -> None:
        self._k_period = k_period
        self._d_period = d_period
        if k_period <= 0:
            raise ValueError(f"k_period must be > 0, got {k_period} / K 周期必须大于 0")
        if d_period <= 0:
            raise ValueError(f"d_period must be > 0, got {d_period} / D 周期必须大于 0")

    @property
    def name(self) -> str:
        return f"Stochastic({self._k_period},{self._d_period})"

    @property
    def min_periods(self) -> int:
        return self._k_period + self._d_period - 1

    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        """
        Compute Stochastic from high/low/close.

        Returns:
          {"k": float, "d": float} or None
        """
        high = kwargs.get("high", [])
        low = kwargs.get("low", [])
        close = kwargs.get("close", [])
        return compute_stochastic(high, low, close, self._k_period, self._d_period)
