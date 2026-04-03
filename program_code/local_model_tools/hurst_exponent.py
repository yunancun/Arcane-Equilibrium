"""
1-4: Hurst Exponent — R/S (Rescaled Range) Analysis / Hurst 指數 — R/S 分析
============================================================================

MODULE_NOTE (中文):
  compute_hurst_exponent 實現 R/S（重標極差）分析（報告 §5.4）：
  - 將價格序列轉為收益率序列
  - 按不同 lag 長度分段，計算每段的 R/S 統計量
  - 對 log(lag) vs log(R/S) 做線性回歸，斜率即 Hurst 指數 H
  - H > 0.60：趨勢性市場（動量策略適用）
  - H < 0.40：均值回歸（反轉策略適用）
  - 0.40 ≤ H ≤ 0.60：隨機遊走（不確定）

  安全不變量：
  - 純函數，無副作用
  - 數據不足時返回 0.5（中性隨機遊走假設）

MODULE_NOTE (English):
  compute_hurst_exponent implements R/S (Rescaled Range) analysis (Report §5.4):
  - Convert price series to return series
  - Segment by different lag lengths, compute R/S statistic per segment
  - Linear regression of log(lag) vs log(R/S), slope = Hurst exponent H
  - H > 0.60: trending market (momentum strategies appropriate)
  - H < 0.40: mean-reverting (reversion strategies appropriate)
  - 0.40 ≤ H ≤ 0.60: random walk (uncertain)

  Safety invariants:
  - Pure function, no side effects
  - Insufficient data returns 0.5 (neutral random walk assumption)
"""

from __future__ import annotations

import math
from typing import Any


def compute_hurst_exponent(
    prices: list[float],
    min_lag: int = 10,
    max_lag: int = 100,
) -> float:
    """
    Compute Hurst exponent via R/S (Rescaled Range) analysis.
    通過 R/S（重標極差）分析計算 Hurst 指數。

    Args:
        prices: Price series (at least min_lag + 1 elements).
        min_lag: Minimum segment length for R/S calculation (default 10).
        max_lag: Maximum segment length (default 100, capped to len/2).

    Returns:
        Hurst exponent H ∈ [0, 1]. 0.5 = random walk (default on insufficient data).
    """
    n = len(prices)
    if n < min_lag + 1:
        return 0.5  # Insufficient data → neutral / 數據不足 → 中性

    # Convert prices to log returns / 轉換為對數收益率
    returns = [
        math.log(prices[i] / prices[i - 1])
        for i in range(1, n)
        if prices[i] > 0 and prices[i - 1] > 0
    ]
    n_ret = len(returns)
    if n_ret < min_lag:
        return 0.5

    # Cap max_lag to half the series length / 限制 max_lag 不超過序列長度的一半
    max_lag = min(max_lag, n_ret // 2)
    if max_lag < min_lag:
        return 0.5

    # Compute R/S for each lag / 對每個 lag 計算 R/S
    log_lags: list[float] = []
    log_rs: list[float] = []

    for lag in range(min_lag, max_lag + 1):
        rs_values = _compute_rs_for_lag(returns, lag)
        if rs_values:
            avg_rs = math.fsum(rs_values) / len(rs_values)
            if avg_rs > 0:
                log_lags.append(math.log(lag))
                log_rs.append(math.log(avg_rs))

    if len(log_lags) < 3:
        return 0.5  # Not enough lag points / lag 點不足

    # Linear regression: log(R/S) = H * log(lag) + c / 線性回歸
    h = _linear_regression_slope(log_lags, log_rs)

    # Clamp to [0, 1] / 限幅到 [0, 1]
    return max(0.0, min(1.0, h))


def _compute_rs_for_lag(returns: list[float], lag: int) -> list[float]:
    """
    Compute R/S statistic for all non-overlapping segments of given lag length.
    計算給定 lag 長度的所有非重疊段的 R/S 統計量。
    """
    n = len(returns)
    rs_values: list[float] = []

    for start in range(0, n - lag + 1, lag):
        segment = returns[start: start + lag]
        if len(segment) < lag:
            break

        mean = math.fsum(segment) / lag

        # Cumulative deviations from mean / 累積偏差
        cum_devs: list[float] = []
        running = 0.0
        for r in segment:
            running += r - mean
            cum_devs.append(running)

        # Range R = max(cumdev) - min(cumdev) / 極差
        r_range = max(cum_devs) - min(cum_devs)

        # Standard deviation S / 標準差
        variance = math.fsum((r - mean) ** 2 for r in segment) / lag
        s = math.sqrt(variance) if variance > 0 else 0.0

        if s > 1e-15:
            rs_values.append(r_range / s)

    return rs_values


def _linear_regression_slope(x: list[float], y: list[float]) -> float:
    """
    Simple OLS slope: β = Σ(xi - x̄)(yi - ȳ) / Σ(xi - x̄)²
    簡單 OLS 斜率。
    """
    n = len(x)
    if n < 2:
        return 0.5

    x_mean = math.fsum(x) / n
    y_mean = math.fsum(y) / n

    num = math.fsum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
    den = math.fsum((x[i] - x_mean) ** 2 for i in range(n))

    if abs(den) < 1e-15:
        return 0.5

    return num / den


def classify_hurst(h: float) -> str:
    """
    Classify Hurst exponent into market regime.
    將 Hurst 指數分類為市場 Regime。

    Returns:
        "trending" (H > 0.60), "mean_reverting" (H < 0.40), "random_walk" (0.40-0.60)
    """
    if h > 0.60:
        return "trending"
    elif h < 0.40:
        return "mean_reverting"
    return "random_walk"
