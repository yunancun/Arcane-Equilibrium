"""
ATR — Average True Range / 平均真实波幅

MODULE_NOTE (中文):
  ATR 由 J. Welles Wilder 在 1978 年提出，衡量市场波动性。
  True Range 是三个值中的最大值：
  1. 当前最高价 - 当前最低价（日内波动）
  2. |当前最高价 - 前收盘价|（跳空高开）
  3. |当前最低价 - 前收盘价|（跳空低开）
  ATR = Wilder 平滑的 True Range 均值

  在本系统中的用途：
  1. **对抗性止损距离** — ATR × 倍数 = 止损距离（已在 risk_manager.py 中使用）
  2. 仓位大小计算 — 按 ATR 调整仓位：波动大 → 仓位小，波动小 → 仓位大
  3. 波动率过滤 — ATR 过高时可能不适合某些策略（如均值回归）
  4. 追踪止损 — Trailing Stop 距离 = ATR × 倍数
  5. 突破确认 — 价格变动 > 1.5 × ATR 可能是真突破

MODULE_NOTE (English):
  ATR was proposed by J. Welles Wilder in 1978, measuring market volatility.
  True Range is the maximum of:
  1. Current high - current low (intraday range)
  2. |Current high - previous close| (gap up)
  3. |Current low - previous close| (gap down)
  ATR = Wilder-smoothed average of True Range

  Uses in this system:
  1. **Adversarial stop distance** — ATR × multiplier = stop distance (used in risk_manager.py)
  2. Position sizing — adjust size by ATR: higher volatility → smaller position
  3. Volatility filter — ATR too high may not suit some strategies (e.g., mean reversion)
  4. Trailing stop — trailing distance = ATR × multiplier
  5. Breakout confirmation — price move > 1.5 × ATR may be a genuine breakout

Safety invariant / 安全不变量:
  - 纯数学计算 / Pure math computation
"""

from __future__ import annotations

from typing import Any

from .base import IndicatorBase


def compute_true_range(
    high: list[float],
    low: list[float],
    close: list[float],
) -> list[float]:
    """
    Compute True Range series.
    计算 True Range 序列。

    TR[0] = high[0] - low[0] (no previous close available for the first bar)
    TR[i] = max(high[i]-low[i], |high[i]-close[i-1]|, |low[i]-close[i-1]|)
    第一根 K线无前收盘价，用日内波幅代替。

    Args:
      high  — high prices / 最高价
      low   — low prices / 最低价
      close — close prices / 收盘价

    Returns:
      True Range series / True Range 序列
    """
    n = min(len(high), len(low), len(close))
    if n == 0:
        return []

    tr = [abs(high[0] - low[0])]  # First bar: intraday range (abs for safety) / 首根：日内波幅（abs 防负值）
    for i in range(1, n):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr.append(max(hl, hc, lc))
    return tr


def compute_atr(
    high: list[float],
    low: list[float],
    close: list[float],
    period: int = 14,
) -> float | None:
    """
    Compute ATR using Wilder's smoothing method.
    使用 Wilder 平滑法计算 ATR。

    Args:
      high   — high prices / 最高价
      low    — low prices / 最低价
      close  — close prices / 收盘价
      period — ATR period (default 14) / ATR 周期

    Returns:
      Latest ATR value, or None if insufficient data / 最新 ATR 值
    """
    tr = compute_true_range(high, low, close)
    if len(tr) < period or period <= 0:
        return None

    # Seed with SMA of first `period` true ranges / 用前 period 个 TR 的 SMA 作种子
    atr = sum(tr[:period]) / period

    # Wilder smoothing for remaining / 对后续值 Wilder 平滑
    for i in range(period, len(tr)):
        atr = (atr * (period - 1) + tr[i]) / period

    return atr


def compute_atr_series(
    high: list[float],
    low: list[float],
    close: list[float],
    period: int = 14,
) -> list[float]:
    """
    Compute full ATR series.
    计算完整的 ATR 序列。

    First `period-1` values are NaN (insufficient data).
    前 period-1 个值为 NaN（数据不足）。
    """
    tr = compute_true_range(high, low, close)
    if len(tr) < period or period <= 0:
        return []

    result = [float('nan')] * (period - 1)
    atr = sum(tr[:period]) / period
    result.append(atr)

    for i in range(period, len(tr)):
        atr = (atr * (period - 1) + tr[i]) / period
        result.append(atr)

    return result


def compute_atr_percent(
    high: list[float],
    low: list[float],
    close: list[float],
    period: int = 14,
) -> float | None:
    """
    Compute ATR as percentage of current price (ATR / close * 100).
    计算 ATR 占当前价格的百分比（ATR / 收盘价 × 100）。

    Useful for comparing volatility across different-priced assets.
    适合跨不同价格资产比较波动率。
    例：BTC ATR=500, price=50000 → ATR%=1.0%; ETH ATR=30, price=3000 → ATR%=1.0%

    Returns:
      ATR percentage, or None / ATR 百分比
    """
    atr_val = compute_atr(high, low, close, period)
    if atr_val is None or not close or close[-1] <= 0:
        return None
    return (atr_val / close[-1]) * 100.0


class ATR(IndicatorBase):
    """
    Average True Range indicator.
    平均真实波幅指标。

    Usage:
      atr = ATR(period=14)
      result = atr.compute(high=[...], low=[...], close=[...])
      # → {"atr": 350.5, "atr_percent": 0.78}
    """

    def __init__(self, period: int = 14) -> None:
        """
        Args:
          period — ATR period (default 14) / ATR 周期
        """
        self._period = period
        if period <= 0:
            raise ValueError(f"period must be > 0, got {period} / 周期必须大于 0")

    @property
    def name(self) -> str:
        return f"ATR({self._period})"

    @property
    def min_periods(self) -> int:
        return self._period

    @property
    def period(self) -> int:
        return self._period

    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        """
        Compute ATR from high/low/close prices.
        从最高价/最低价/收盘价计算 ATR。

        Args:
          high  — list of high prices / 最高价列表
          low   — list of low prices / 最低价列表
          close — list of close prices / 收盘价列表

        Returns:
          {"atr": float, "atr_percent": float} or None
        """
        high = kwargs.get("high", [])
        low = kwargs.get("low", [])
        close = kwargs.get("close", [])

        atr_val = compute_atr(high, low, close, self._period)
        if atr_val is None:
            return None

        # Compute ATR percent inline (avoid calling compute_atr a second time)
        # 内联计算 ATR 百分比（避免重复调用 compute_atr）
        atr_pct = (atr_val / close[-1]) * 100.0 if close and close[-1] > 0 else 0.0
        return {
            "atr": atr_val,
            "atr_percent": atr_pct,
        }
