"""
Moving Averages — SMA & EMA / 移动平均线 — 简单移动平均 & 指数移动平均

MODULE_NOTE (中文):
  移动平均线是最基础的技术指标，用于平滑价格数据、识别趋势方向。
  - SMA (Simple Moving Average): 简单算术平均，所有数据点等权重
  - EMA (Exponential Moving Average): 指数加权平均，近期数据权重更高

  在本系统中的用途：
  1. 趋势判断 — 价格在 MA 上方 = 多头，下方 = 空头
  2. 交叉信号 — 快线穿越慢线 = 买入/卖出信号（MA Crossover 策略的核心）
  3. 支撑阻力 — MA 本身可作为动态支撑/阻力位
  4. 作为其他指标的组成部分 — MACD 基于 EMA，Bollinger Bands 基于 SMA

  计算公式：
    SMA(n) = sum(close[-n:]) / n
    EMA(n) = close * k + EMA_prev * (1-k), where k = 2/(n+1)

MODULE_NOTE (English):
  Moving averages are the most fundamental technical indicator, used to smooth
  price data and identify trend direction.
  - SMA (Simple Moving Average): arithmetic mean, all data points equally weighted
  - EMA (Exponential Moving Average): exponentially weighted, recent data has higher weight

  Uses in this system:
  1. Trend identification — price above MA = bullish, below = bearish
  2. Crossover signals — fast MA crosses slow MA = buy/sell signal (core of MA Crossover strategy)
  3. Support/resistance — MA acts as dynamic support/resistance levels
  4. Building block for other indicators — MACD uses EMA, Bollinger Bands use SMA

  Formulas:
    SMA(n) = sum(close[-n:]) / n
    EMA(n) = close * k + EMA_prev * (1-k), where k = 2/(n+1)

Safety invariant / 安全不变量:
  - 纯数学计算 / Pure math computation
"""

from __future__ import annotations

import math
from typing import Any

from .base import IndicatorBase


# =============================================================================
# Helper functions / 辅助函数
# (Exposed for reuse by other indicators like MACD and Bollinger Bands)
# (暴露给其他指标复用，如 MACD 和 Bollinger Bands)
# =============================================================================

def compute_sma(values: list[float], period: int) -> float | None:
    """
    Compute Simple Moving Average of the latest `period` values.
    计算最近 `period` 个值的简单移动平均。

    Args:
      values — price list (newest last) / 价格列表（最新的在最后）
      period — window size / 窗口大小

    Returns:
      SMA value, or None if insufficient data / SMA 值，数据不足返回 None
    """
    if len(values) < period or period <= 0:
        return None
    window = values[-period:]
    # 1-5 [V3-QC-2]: Use math.fsum() for numerically stable summation.
    # 使用 math.fsum() 保證數值穩定的求和。
    return math.fsum(window) / period


def compute_sma_series(values: list[float], period: int) -> list[float]:
    """
    Compute SMA series for the entire input (returns list same length as input).
    计算整个输入序列的 SMA 序列（返回与输入同长度的列表）。

    The first (period-1) values will be NaN (insufficient data).
    前 (period-1) 个值为 NaN（数据不足）。

    Args:
      values — price list / 价格列表
      period — window size / 窗口大小

    Returns:
      SMA series / SMA 序列
    """
    if period <= 0 or len(values) < period:
        return []
    result = [float('nan')] * (period - 1)
    # Initial SMA: average of first `period` values / 初始 SMA：前 period 个值的平均
    # 1-5 [V3-QC-2]: math.fsum for numerically stable summation.
    window_sum = math.fsum(values[:period])
    result.append(window_sum / period)
    # Sliding window / 滑动窗口
    for i in range(period, len(values)):
        window_sum += values[i] - values[i - period]
        result.append(window_sum / period)
    return result


def compute_ema(values: list[float], period: int) -> float | None:
    """
    Compute Exponential Moving Average of the entire series, return the latest value.
    计算整个序列的指数移动平均，返回最新值。

    Uses SMA of first `period` values as the seed, then applies EMA formula.
    用前 period 个值的 SMA 作为种子，然后应用 EMA 公式。

    Args:
      values — price list (newest last) / 价格列表（最新的在最后）
      period — EMA period / EMA 周期

    Returns:
      Latest EMA value, or None if insufficient data / 最新 EMA 值，数据不足返回 None
    """
    if len(values) < period or period <= 0:
        return None
    series = compute_ema_series(values, period)
    return series[-1] if series else None


def compute_ema_series(values: list[float], period: int) -> list[float]:
    """
    Compute full EMA series for the entire input.
    计算整个输入序列的完整 EMA 序列。

    Seed: SMA of first `period` values.
    种子：前 period 个值的 SMA。
    The first (period-1) values will be NaN (insufficient data).
    前 (period-1) 个值为 NaN（数据不足）。

    Args:
      values — price list / 价格列表
      period — EMA period / EMA 周期

    Returns:
      EMA series / EMA 序列
    """
    if period <= 0 or len(values) < period:
        return []

    k = 2.0 / (period + 1)  # EMA multiplier / EMA 乘数
    result = [float('nan')] * (period - 1)

    # Seed with SMA / 用 SMA 作为种子
    seed = sum(values[:period]) / period
    result.append(seed)

    # Apply EMA recursion / 应用 EMA 递推
    ema = seed
    for i in range(period, len(values)):
        ema = values[i] * k + ema * (1 - k)
        result.append(ema)

    return result


# =============================================================================
# SMA Indicator Class / SMA 指标类
# =============================================================================

class SMA(IndicatorBase):
    """
    Simple Moving Average indicator.
    简单移动平均指标。

    Returns the SMA of the latest `period` close prices.
    返回最近 `period` 个收盘价的 SMA。

    Usage:
      sma = SMA(period=20)
      result = sma.compute(close=[...])  # → {"sma": 45123.5}
    """

    def __init__(self, period: int = 20) -> None:
        """
        Args:
          period — SMA window size (default 20) / SMA 窗口大小（默认 20）
        """
        self._period = period
        if period <= 0:
            raise ValueError(f"period must be > 0, got {period} / 周期必须大于 0")

    @property
    def name(self) -> str:
        return f"SMA({self._period})"

    @property
    def min_periods(self) -> int:
        return self._period

    @property
    def period(self) -> int:
        return self._period

    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        """
        Compute SMA from close prices.
        从收盘价计算 SMA。

        Args:
          close — list of close prices (newest last) / 收盘价列表

        Returns:
          {"sma": float} or None if insufficient data
        """
        close = kwargs.get("close", [])
        val = compute_sma(close, self._period)
        if val is None:
            return None
        return {"sma": val}


# =============================================================================
# EMA Indicator Class / EMA 指标类
# =============================================================================

class EMA(IndicatorBase):
    """
    Exponential Moving Average indicator.
    指数移动平均指标。

    Usage:
      ema = EMA(period=12)
      result = ema.compute(close=[...])  # → {"ema": 45150.2}
    """

    def __init__(self, period: int = 12) -> None:
        """
        Args:
          period — EMA period (default 12) / EMA 周期（默认 12）
        """
        self._period = period
        if period <= 0:
            raise ValueError(f"period must be > 0, got {period} / 周期必须大于 0")

    @property
    def name(self) -> str:
        return f"EMA({self._period})"

    @property
    def min_periods(self) -> int:
        return self._period

    @property
    def period(self) -> int:
        return self._period

    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        """
        Compute EMA from close prices.
        从收盘价计算 EMA。

        Args:
          close — list of close prices (newest last) / 收盘价列表

        Returns:
          {"ema": float} or None if insufficient data
        """
        close = kwargs.get("close", [])
        val = compute_ema(close, self._period)
        if val is None:
            return None
        return {"ema": val}
