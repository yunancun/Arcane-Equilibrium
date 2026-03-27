"""
RSI — Relative Strength Index / 相对强弱指数

MODULE_NOTE (中文):
  RSI 是最常用的动量振荡指标，衡量价格变动的速度和幅度。
  取值范围 0-100：
  - RSI > 70: 超买区域（可能回落）
  - RSI < 30: 超卖区域（可能反弹）
  - RSI ≈ 50: 中性

  在本系统中的用途：
  1. 超买超卖信号 — RSI 极端值作为反转信号
  2. 背离检测 — 价格新高但 RSI 没新高 = 看跌背离
  3. 趋势确认 — 在均值回归策略（Bollinger）中确认回归时机
  4. 过滤器 — 在 MA 交叉策略中过滤假信号

  Wilder's RSI 计算方法（平滑版，非简单版）：
  1. 计算每日价格变动：change = close[i] - close[i-1]
  2. 分离涨跌：gain = max(change, 0), loss = max(-change, 0)
  3. 第一个平均值用 SMA：avg_gain = mean(gains[:period]), avg_loss = mean(losses[:period])
  4. 后续用 Wilder 平滑：avg_gain = (prev_avg_gain * (period-1) + gain) / period
  5. RS = avg_gain / avg_loss
  6. RSI = 100 - 100/(1+RS)

MODULE_NOTE (English):
  RSI is the most commonly used momentum oscillator, measuring the speed and magnitude
  of price movements. Range 0-100:
  - RSI > 70: overbought (may pull back)
  - RSI < 30: oversold (may bounce)
  - RSI ≈ 50: neutral

  Uses in this system:
  1. Overbought/oversold signals — extreme RSI values as reversal signals
  2. Divergence detection — price makes new high but RSI doesn't = bearish divergence
  3. Trend confirmation — confirms mean-reversion timing in Bollinger strategy
  4. Filter — filters false signals in MA crossover strategy

  Wilder's RSI calculation (smoothed version, not simple):
  1. Daily price changes: change = close[i] - close[i-1]
  2. Separate gains/losses: gain = max(change, 0), loss = max(-change, 0)
  3. First average uses SMA: avg_gain = mean(gains[:period]), avg_loss = mean(losses[:period])
  4. Subsequent uses Wilder smoothing: avg_gain = (prev_avg_gain * (period-1) + gain) / period
  5. RS = avg_gain / avg_loss
  6. RSI = 100 - 100/(1+RS)

Safety invariant / 安全不变量:
  - 纯数学计算 / Pure math computation
"""

from __future__ import annotations

from typing import Any

from .base import IndicatorBase


def compute_rsi(close: list[float], period: int = 14) -> float | None:
    """
    Compute RSI using Wilder's smoothing method.
    使用 Wilder 平滑法计算 RSI。

    Args:
      close  — list of close prices (newest last), needs at least period+1 values
               收盘价列表（最新在最后），至少需要 period+1 个值
      period — RSI period (default 14, Wilder's standard) / RSI 周期（默认 14）

    Returns:
      RSI value (0-100), or None if insufficient data / RSI 值 (0-100)，数据不足返回 None
    """
    if len(close) < period + 1 or period <= 0:
        return None

    # Step 1: Calculate price changes / 计算价格变动
    changes = [close[i] - close[i - 1] for i in range(1, len(close))]

    # Step 2: Separate gains and losses / 分离涨跌
    gains = [max(c, 0.0) for c in changes]
    losses = [max(-c, 0.0) for c in changes]

    # Step 3: Initial average using SMA / 用 SMA 计算初始平均值
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    # Step 4: Wilder smoothing for remaining values / 对后续值用 Wilder 平滑
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    # Step 5 & 6: RS → RSI
    if avg_loss == 0:
        if avg_gain == 0:
            # No movement → RSI = 50 (neutral) / 无波动 → RSI = 50（中性）
            return 50.0
        # All gains, no losses → RSI = 100 / 全涨无跌 → RSI = 100
        return 100.0
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def compute_rsi_series(close: list[float], period: int = 14) -> list[float]:
    """
    Compute RSI series for the entire input.
    计算整个输入序列的 RSI 序列。

    Returns list same length as input. First `period` values are NaN (insufficient data).
    返回与输入同长度的列表。前 `period` 个值为 NaN（数据不足）。

    Args:
      close  — close prices / 收盘价
      period — RSI period / RSI 周期

    Returns:
      RSI series / RSI 序列
    """
    if len(close) < period + 1 or period <= 0:
        return []

    changes = [close[i] - close[i - 1] for i in range(1, len(close))]
    gains = [max(c, 0.0) for c in changes]
    losses = [max(-c, 0.0) for c in changes]

    result = [float('nan')] * period  # First `period` values are insufficient / 前 period 个值不足

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_loss == 0:
        result.append(50.0 if avg_gain == 0 else 100.0)
    else:
        rs = avg_gain / avg_loss
        result.append(100.0 - (100.0 / (1.0 + rs)))

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            result.append(50.0 if avg_gain == 0 else 100.0)
        else:
            rs = avg_gain / avg_loss
            result.append(100.0 - (100.0 / (1.0 + rs)))

    return result


class RSI(IndicatorBase):
    """
    Relative Strength Index indicator.
    相对强弱指数指标。

    Usage:
      rsi = RSI(period=14)
      result = rsi.compute(close=[...])  # → {"rsi": 65.3}
    """

    def __init__(self, period: int = 14) -> None:
        """
        Args:
          period — RSI period (default 14, Wilder's standard) / RSI 周期（默认 14）
        """
        if period <= 0:
            raise ValueError(f"period must be > 0, got {period} / 周期必须大于 0")
        self._period = period

    @property
    def name(self) -> str:
        return f"RSI({self._period})"

    @property
    def min_periods(self) -> int:
        # RSI needs period+1 values: period changes require period+1 prices
        # RSI 需要 period+1 个值：period 个变动需要 period+1 个价格
        return self._period + 1

    @property
    def period(self) -> int:
        return self._period

    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        """
        Compute RSI from close prices.
        从收盘价计算 RSI。

        Args:
          close — list of close prices (newest last) / 收盘价列表

        Returns:
          {"rsi": float} or None if insufficient data
        """
        close = kwargs.get("close", [])
        val = compute_rsi(close, self._period)
        if val is None:
            return None
        return {"rsi": val}
