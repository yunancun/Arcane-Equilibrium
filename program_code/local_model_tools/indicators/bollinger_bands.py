"""
Bollinger Bands / 布林带

MODULE_NOTE (中文):
  布林带由 John Bollinger 在 1980 年代发明，是最经典的波动率通道指标。
  三条线组成：
  1. 中轨 (Middle Band) = SMA(close, period)
  2. 上轨 (Upper Band) = Middle + std_dev_multiplier × StdDev(close, period)
  3. 下轨 (Lower Band) = Middle - std_dev_multiplier × StdDev(close, period)

  默认参数：period=20, std_dev_multiplier=2.0
  约 95% 的价格会落在 2 倍标准差范围内（假设正态分布）。

  在本系统中的用途：
  1. **均值回归策略（核心）** — 价格触及下轨 + RSI 超卖 → 买入信号
  2. 波动率衡量 — 带宽（bandwidth）= (upper-lower)/middle，越大波动越大
  3. 布林带收窄 (Squeeze) — 带宽极小 → 可能即将出现大幅突破
  4. %B 指标 — (price-lower)/(upper-lower)，0=在下轨，1=在上轨

MODULE_NOTE (English):
  Bollinger Bands, invented by John Bollinger in the 1980s, is a classic volatility
  channel indicator. Three lines:
  1. Middle Band = SMA(close, period)
  2. Upper Band = Middle + std_dev_multiplier × StdDev(close, period)
  3. Lower Band = Middle - std_dev_multiplier × StdDev(close, period)

  Default: period=20, std_dev_multiplier=2.0
  ~95% of prices fall within 2 standard deviations (assuming normal distribution).

  Uses in this system:
  1. **Mean reversion strategy (core)** — price touches lower band + RSI oversold → buy signal
  2. Volatility measurement — bandwidth = (upper-lower)/middle, wider = more volatile
  3. Bollinger Squeeze — extremely narrow bandwidth → potential breakout imminent
  4. %B indicator — (price-lower)/(upper-lower), 0=at lower, 1=at upper

Safety invariant / 安全不变量:
  - 纯数学计算 / Pure math computation
"""

from __future__ import annotations

import math
from typing import Any

from .base import IndicatorBase
from .moving_averages import compute_sma


def compute_stddev(values: list[float], period: int) -> float | None:
    """
    Compute population standard deviation of the latest `period` values.
    计算最近 `period` 个值的总体标准差。

    Note: Uses population stddev (ddof=0), consistent with TradingView and most
    charting platforms. Some implementations use sample stddev (ddof=1).
    注意：使用总体标准差 (ddof=0)，与 TradingView 等主流平台一致。

    Args:
      values — value list / 值列表
      period — window size / 窗口大小

    Returns:
      Standard deviation, or None if insufficient data / 标准差，数据不足返回 None
    """
    if len(values) < period or period <= 0:
        return None
    window = values[-period:]
    mean = sum(window) / period
    variance = sum((x - mean) ** 2 for x in window) / period
    return math.sqrt(variance)


def compute_bollinger_bands(
    close: list[float],
    period: int = 20,
    std_dev_multiplier: float = 2.0,
) -> dict[str, float] | None:
    """
    Compute Bollinger Bands: upper, middle, lower, bandwidth, percent_b.
    计算布林带：上轨、中轨、下轨、带宽、%B。

    Args:
      close              — close prices (newest last) / 收盘价列表
      period             — SMA period (default 20) / SMA 周期
      std_dev_multiplier — standard deviation multiplier (default 2.0) / 标准差乘数

    Returns:
      {
        "upper": float,        # upper band / 上轨
        "middle": float,       # middle band (SMA) / 中轨 (SMA)
        "lower": float,        # lower band / 下轨
        "bandwidth": float,    # (upper-lower)/middle, normalized volatility / 归一化波动率
        "percent_b": float,    # (close-lower)/(upper-lower), 0=at lower, 1=at upper / 当前价格在带内的位置
      }
      or None if insufficient data
    """
    if len(close) < period:
        return None

    middle = compute_sma(close, period)
    stddev = compute_stddev(close, period)
    if middle is None or stddev is None:
        return None

    upper = middle + std_dev_multiplier * stddev
    lower = middle - std_dev_multiplier * stddev

    # Bandwidth: normalized volatility (0 means no volatility)
    # 带宽：归一化波动率（0 表示无波动）
    bandwidth = (upper - lower) / middle if middle != 0 else 0.0

    # %B: where is the current price within the band (0=lower, 1=upper)
    # %B：当前价格在带内的位置（0=下轨, 1=上轨）
    band_width_abs = upper - lower
    current_price = close[-1]
    percent_b = (current_price - lower) / band_width_abs if band_width_abs != 0 else 0.5

    return {
        "upper": upper,
        "middle": middle,
        "lower": lower,
        "bandwidth": bandwidth,
        "percent_b": percent_b,
    }


class BollingerBands(IndicatorBase):
    """
    Bollinger Bands indicator.
    布林带指标。

    Usage:
      bb = BollingerBands(period=20, std_dev_multiplier=2.0)
      result = bb.compute(close=[...])
      # → {"upper": 46000, "middle": 45000, "lower": 44000, "bandwidth": 0.044, "percent_b": 0.75}
    """

    def __init__(self, period: int = 20, std_dev_multiplier: float = 2.0) -> None:
        """
        Args:
          period             — SMA period (default 20) / SMA 周期
          std_dev_multiplier — standard deviation multiplier (default 2.0) / 标准差乘数
        """
        self._period = period
        self._std_dev_multiplier = std_dev_multiplier

    @property
    def name(self) -> str:
        return f"BB({self._period},{self._std_dev_multiplier})"

    @property
    def min_periods(self) -> int:
        return self._period

    @property
    def period(self) -> int:
        return self._period

    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        """
        Compute Bollinger Bands from close prices.
        从收盘价计算布林带。

        Args:
          close — list of close prices (newest last) / 收盘价列表

        Returns:
          {"upper", "middle", "lower", "bandwidth", "percent_b"} or None
        """
        close = kwargs.get("close", [])
        return compute_bollinger_bands(close, self._period, self._std_dev_multiplier)
