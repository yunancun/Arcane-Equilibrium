"""
1-5: Extended Indicators — KAMA, ADX, Hurst, EWMA Vol, Volume Ratio, Donchian
===============================================================================

MODULE_NOTE (中文):
  Phase 1 擴展指標集（報告 §6.6）：
  - KAMA (Kaufman Adaptive MA)：自適應移動平均，噪聲市場平滑/趨勢市場跟隨
  - ADX (Average Directional Index)：趨勢強度量化（>20 有趨勢，<20 無趨勢）
  - Hurst Exponent：R/S 分析判斷趨勢性/均值回歸
  - EWMA Vol：指數加權波動率估計
  - Volume Ratio：成交量相對均量比率
  - Donchian Channel：N 周期最高/最低價通道

  所有指標繼承 IndicatorBase，使用純 Python 標準庫計算。

MODULE_NOTE (English):
  Phase 1 extended indicator set (Report §6.6):
  - KAMA: Kaufman Adaptive MA — smooths noise, follows trends
  - ADX: Average Directional Index — trend strength (>20 trending, <20 ranging)
  - Hurst: R/S analysis for trend/mean-reversion classification
  - EWMA Vol: Exponentially weighted volatility estimate
  - Volume Ratio: Current volume relative to average
  - Donchian Channel: N-period high/low price channel

  All inherit IndicatorBase, use pure Python stdlib.
"""

from __future__ import annotations

import math
from typing import Any

from .base import IndicatorBase


class KAMA(IndicatorBase):
    """
    Kaufman Adaptive Moving Average / Kaufman 自適應移動平均。

    Adapts smoothing speed based on price efficiency ratio.
    根據價格效率比自適應調整平滑速度。
    """

    def __init__(self, period: int = 10, fast_sc: int = 2, slow_sc: int = 30) -> None:
        self._period = period
        self._fast_c = 2.0 / (fast_sc + 1)
        self._slow_c = 2.0 / (slow_sc + 1)

    @property
    def name(self) -> str:
        return f"KAMA({self._period})"

    @property
    def min_periods(self) -> int:
        return self._period + 1

    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        close = kwargs.get("close", [])
        if len(close) < self.min_periods:
            return None

        # Efficiency Ratio = |direction| / volatility
        direction = abs(close[-1] - close[-self._period - 1])
        volatility = math.fsum(abs(close[i] - close[i - 1]) for i in range(-self._period, 0))
        if volatility == 0:
            er = 0.0
        else:
            er = direction / volatility

        # Smoothing constant / 平滑常數
        sc = (er * (self._fast_c - self._slow_c) + self._slow_c) ** 2

        # KAMA = previous KAMA + SC × (Close - previous KAMA)
        # Initialize with SMA / 用 SMA 初始化
        kama = math.fsum(close[-self._period:]) / self._period
        for i in range(-self._period + 1, 0):
            kama = kama + sc * (close[i] - kama)
        kama = kama + sc * (close[-1] - kama)

        return {"kama": round(kama, 8), "efficiency_ratio": round(er, 4)}


class ADX(IndicatorBase):
    """
    Average Directional Index — trend strength measurement.
    平均趨向指數 — 趨勢強度度量。
    """

    def __init__(self, period: int = 14) -> None:
        self._period = period

    @property
    def name(self) -> str:
        return f"ADX({self._period})"

    @property
    def min_periods(self) -> int:
        return self._period * 2 + 1

    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        high = kwargs.get("high", [])
        low = kwargs.get("low", [])
        close = kwargs.get("close", [])
        n = min(len(high), len(low), len(close))
        if n < self.min_periods:
            return None

        # True Range, +DM, -DM / 真實波幅、正向動量、負向動量
        tr_list: list[float] = []
        pdm_list: list[float] = []
        ndm_list: list[float] = []

        for i in range(1, n):
            h = high[i]
            l = low[i]
            c_prev = close[i - 1]
            tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
            tr_list.append(tr)

            up = high[i] - high[i - 1]
            down = low[i - 1] - low[i]
            pdm_list.append(up if up > down and up > 0 else 0.0)
            ndm_list.append(down if down > up and down > 0 else 0.0)

        p = self._period
        if len(tr_list) < p * 2:
            return None

        # Wilder smoothing / Wilder 平滑
        atr = math.fsum(tr_list[:p]) / p
        pdm_s = math.fsum(pdm_list[:p]) / p
        ndm_s = math.fsum(ndm_list[:p]) / p

        for i in range(p, len(tr_list)):
            atr = (atr * (p - 1) + tr_list[i]) / p
            pdm_s = (pdm_s * (p - 1) + pdm_list[i]) / p
            ndm_s = (ndm_s * (p - 1) + ndm_list[i]) / p

        pdi = 100 * pdm_s / atr if atr > 0 else 0.0
        ndi = 100 * ndm_s / atr if atr > 0 else 0.0

        dx = 100 * abs(pdi - ndi) / (pdi + ndi) if (pdi + ndi) > 0 else 0.0

        return {
            "adx": round(dx, 2),
            "plus_di": round(pdi, 2),
            "minus_di": round(ndi, 2),
        }


class HurstIndicator(IndicatorBase):
    """
    Hurst Exponent via R/S analysis — trend/mean-reversion classifier.
    Hurst 指數（R/S 分析）— 趨勢/均值回歸分類器。
    """

    def __init__(self, min_lag: int = 10, max_lag: int = 50) -> None:
        self._min_lag = min_lag
        self._max_lag = max_lag

    @property
    def name(self) -> str:
        return "Hurst"

    @property
    def min_periods(self) -> int:
        return self._max_lag + 1

    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        close = kwargs.get("close", [])
        if len(close) < self.min_periods:
            return None

        from ..hurst_exponent import compute_hurst_exponent, classify_hurst
        h = compute_hurst_exponent(close, self._min_lag, self._max_lag)
        return {"hurst": round(h, 4), "regime": classify_hurst(h)}


class EWMAVolIndicator(IndicatorBase):
    """
    EWMA Volatility indicator — wraps EWMAVolEstimator for indicator engine.
    EWMA 波動率指標 — 包裝 EWMAVolEstimator 供指標引擎使用。
    """

    def __init__(self, timeframe: str = "1h") -> None:
        self._timeframe = timeframe

    @property
    def name(self) -> str:
        return f"EWMA_Vol({self._timeframe})"

    @property
    def min_periods(self) -> int:
        return 5

    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        close = kwargs.get("close", [])
        if len(close) < self.min_periods:
            return None

        # Compute vol from last N returns / 從最近 N 個收益率計算波動率
        from ..ewma_vol_estimator import EWMAVolEstimator
        est = EWMAVolEstimator(timeframe=self._timeframe)
        for i in range(1, len(close)):
            if close[i] > 0 and close[i - 1] > 0:
                est.update("_tmp", math.log(close[i] / close[i - 1]))

        vol = est.get_vol("_tmp")
        regime = est.get_vol_regime("_tmp")
        return {"ewma_vol": round(vol, 8), "vol_regime": regime}


class VolumeRatio(IndicatorBase):
    """
    Volume Ratio — current volume relative to N-period average.
    成交量比率 — 當前成交量與 N 周期平均的比值。
    """

    def __init__(self, period: int = 20) -> None:
        self._period = period

    @property
    def name(self) -> str:
        return f"VolumeRatio({self._period})"

    @property
    def min_periods(self) -> int:
        return self._period

    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        volume = kwargs.get("volume", [])
        if len(volume) < self.min_periods:
            return None

        avg_vol = math.fsum(volume[-self._period:]) / self._period
        if avg_vol <= 0:
            return {"volume_ratio": 0.0}

        current = volume[-1]
        ratio = current / avg_vol
        return {"volume_ratio": round(ratio, 4)}


class DonchianChannel(IndicatorBase):
    """
    Donchian Channel — N-period highest high / lowest low.
    唐奇安通道 — N 周期最高價/最低價通道。
    """

    def __init__(self, period: int = 20) -> None:
        self._period = period

    @property
    def name(self) -> str:
        return f"Donchian({self._period})"

    @property
    def min_periods(self) -> int:
        return self._period

    def compute(self, **kwargs: Any) -> dict[str, Any] | None:
        high = kwargs.get("high", [])
        low = kwargs.get("low", [])
        close = kwargs.get("close", [])
        if len(high) < self._period or len(low) < self._period:
            return None

        upper = max(high[-self._period:])
        lower = min(low[-self._period:])
        middle = (upper + lower) / 2
        width = (upper - lower) / middle if middle > 0 else 0.0

        return {
            "donchian_upper": round(upper, 8),
            "donchian_lower": round(lower, 8),
            "donchian_middle": round(middle, 8),
            "donchian_width": round(width, 6),
        }
