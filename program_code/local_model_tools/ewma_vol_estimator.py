"""
1-3: EWMA Volatility Estimator — Exponentially Weighted Moving Average Vol / EWMA 波動率估計器
==============================================================================================

MODULE_NOTE (中文):
  EWMAVolEstimator 實現指數加權移動平均波動率估計（報告 §5.3）：
  - Lambda 衰減因子按時間框架自動調整（1m: 0.94, 5m: 0.96, 1h: 0.97, 4h: 0.99）
  - 在線方差更新：σ²(t) = λ·σ²(t-1) + (1-λ)·r(t)²
  - 波動率 Regime 分類：低/正常/高（基於歷史均值比率）
  - 純計算模組，無副作用，線程安全

MODULE_NOTE (English):
  EWMAVolEstimator implements exponentially weighted moving average volatility (Report §5.3):
  - Lambda decay factor auto-adjusted by timeframe (1m: 0.94, 5m: 0.96, 1h: 0.97, 4h: 0.99)
  - Online variance update: σ²(t) = λ·σ²(t-1) + (1-λ)·r(t)²
  - Vol regime classification: low/normal/high (based on ratio to historical mean)
  - Pure computation module, no side effects, thread-safe
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)

# Lambda decay factors by timeframe / 各時間框架的 Lambda 衰減因子
_LAMBDA_BY_TIMEFRAME: dict[str, float] = {
    "1m": 0.94,
    "5m": 0.96,
    "15m": 0.97,
    "30m": 0.97,
    "1h": 0.97,
    "4h": 0.99,
    "1d": 0.99,
}

# Vol regime thresholds: ratio to historical mean vol / 波動率 Regime 閾值
_REGIME_LOW_RATIO = 0.6    # < 60% of mean → low vol / 低波動
_REGIME_HIGH_RATIO = 1.5   # > 150% of mean → high vol / 高波動


class EWMAVolEstimator:
    """
    Exponentially Weighted Moving Average Volatility Estimator.
    指數加權移動平均波動率估計器。

    Thread-safe: per-symbol state isolation, no cross-symbol mutation.
    線程安全：按品種隔離狀態，無跨品種可變操作。
    """

    def __init__(self, timeframe: str = "1h") -> None:
        self._lambda = _LAMBDA_BY_TIMEFRAME.get(timeframe, 0.97)
        self._timeframe = timeframe

        # Per-symbol state / 每品種狀態
        self._variance: dict[str, float] = defaultdict(float)
        self._hist_mean_vol: dict[str, float] = defaultdict(float)
        self._update_count: dict[str, int] = defaultdict(int)
        self._initialized: dict[str, bool] = defaultdict(bool)

    def update(self, symbol: str, log_return: float) -> float:
        """
        Update EWMA variance with a new log return and return current vol estimate.
        用新的對數收益率更新 EWMA 方差並返回當前波動率估計。

        Formula: σ²(t) = λ·σ²(t-1) + (1-λ)·r(t)²
        公式：σ²(t) = λ·σ²(t-1) + (1-λ)·r(t)²

        Args:
            symbol: Trading pair (e.g., "BTCUSDT").
            log_return: Log return = ln(P_t / P_{t-1}).

        Returns:
            Current volatility estimate (σ = sqrt(variance)).
        """
        lam = self._lambda
        r_sq = log_return * log_return

        if not self._initialized[symbol]:
            # Initialize with first observation / 用第一個觀測值初始化
            self._variance[symbol] = r_sq
            self._initialized[symbol] = True
        else:
            self._variance[symbol] = lam * self._variance[symbol] + (1 - lam) * r_sq

        self._update_count[symbol] += 1

        # Update historical mean vol (EMA of vol) for regime classification
        # 更新歷史平均波動率（vol 的 EMA）用於 regime 分類
        vol = math.sqrt(max(0.0, self._variance[symbol]))
        alpha = 0.01  # Slow EMA for historical baseline / 慢速 EMA 作為歷史基準
        if self._hist_mean_vol[symbol] == 0.0:
            self._hist_mean_vol[symbol] = vol
        else:
            self._hist_mean_vol[symbol] = alpha * vol + (1 - alpha) * self._hist_mean_vol[symbol]

        return vol

    def update_from_prices(self, symbol: str, price_prev: float, price_curr: float) -> float:
        """
        Convenience: compute log return from two prices and update.
        便捷方法：從兩個價格計算對數收益率並更新。
        """
        if price_prev <= 0 or price_curr <= 0:
            return self.get_vol(symbol)
        log_ret = math.log(price_curr / price_prev)
        return self.update(symbol, log_ret)

    def get_vol(self, symbol: str) -> float:
        """
        Get current volatility estimate for a symbol.
        獲取品種的當前波動率估計。

        Returns 0.0 if no data available / 無數據時返回 0.0。
        """
        return math.sqrt(max(0.0, self._variance.get(symbol, 0.0)))

    def get_vol_regime(self, symbol: str) -> str:
        """
        Classify current volatility regime relative to historical mean.
        相對於歷史均值分類當前波動率 Regime。

        Returns:
            "low" — vol < 60% of historical mean (calm market)
            "normal" — vol between 60% and 150% of historical mean
            "high" — vol > 150% of historical mean (volatile market)
        """
        vol = self.get_vol(symbol)
        hist = self._hist_mean_vol.get(symbol, 0.0)

        if hist <= 0 or self._update_count.get(symbol, 0) < 10:
            return "normal"  # Insufficient data → default neutral / 數據不足 → 默認中性

        ratio = vol / hist
        if ratio < _REGIME_LOW_RATIO:
            return "low"
        elif ratio > _REGIME_HIGH_RATIO:
            return "high"
        return "normal"

    def get_status(self) -> dict[str, Any]:
        """
        Get status of all tracked symbols.
        獲取所有已追蹤品種的狀態。
        """
        return {
            sym: {
                "vol": round(self.get_vol(sym), 8),
                "regime": self.get_vol_regime(sym),
                "hist_mean_vol": round(self._hist_mean_vol.get(sym, 0.0), 8),
                "updates": self._update_count.get(sym, 0),
                "lambda": self._lambda,
            }
            for sym in self._initialized
            if self._initialized[sym]
        }
