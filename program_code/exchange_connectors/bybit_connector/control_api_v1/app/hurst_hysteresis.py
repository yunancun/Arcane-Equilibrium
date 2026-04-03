"""
Hurst Hysteresis Filter — extracted from market_regime.py
Hurst 滯後過濾器 — 從 market_regime.py 提取

MODULE_NOTE (中文):
  Hurst-based regime 滯後過濾器，防止 regime 切換來回震盪（whipsaw）。
  根據改善報告附錄 B.2.1：
    - H > 0.60 連續 6 根 bar → "trending"
    - H < 0.40 連續 6 根 bar → "mean_reverting"
    - 介於兩者之間 → 緩慢衰減計數，保持當前 regime（滯後）
  支持序列化/還原（get_state / from_state）。

MODULE_NOTE (English):
  Hurst-based regime hysteresis filter to prevent whipsaw regime switching.
  Per Improvement Report Appendix B.2.1:
    - H > 0.60 for 6 consecutive bars → "trending"
    - H < 0.40 for 6 consecutive bars → "mean_reverting"
    - In between → slowly decay counts, keep current regime (hysteresis)
  Supports serialization/restoration (get_state / from_state).
"""

from __future__ import annotations

from typing import Any, Dict


class HurstHysteresis:
    """
    Hurst-based regime hysteresis filter to prevent whipsaw regime switching.
    基於 Hurst 的 regime 滯後過濾器，防止 regime 切換來回震盪。

    Regime switches require H to stay outside threshold for N consecutive periods.
    Regime 切換需要 H 連續 N 個週期停留在閾值外。

    Per Improvement Report Appendix B.2.1:
      - H > 0.60 for 6 consecutive bars → "trending"
      - H < 0.40 for 6 consecutive bars → "mean_reverting"
      - In between → slowly decay counts, keep current regime (hysteresis)
    根據改善報告附錄 B.2.1：
      - H > 0.60 連續 6 根 bar → "trending"
      - H < 0.40 連續 6 根 bar → "mean_reverting"
      - 介於兩者之間 → 緩慢衰減計數，保持當前 regime（滯後）
    """

    def __init__(
        self,
        trend_threshold: float = 0.60,
        revert_threshold: float = 0.40,
        required_consecutive: int = 6,  # 6 × 1h bar = 6 hours
    ):
        self._trend_th = trend_threshold
        self._revert_th = revert_threshold
        self._required = required_consecutive
        self._consecutive_trend = 0
        self._consecutive_revert = 0
        self._current_regime = "uncertain"  # "trending" / "mean_reverting" / "uncertain"

    def update(self, hurst: float) -> str:
        """
        Update with new Hurst value, return confirmed regime.
        用新 Hurst 值更新，返回確認的 regime。

        Args:
            hurst: Hurst exponent value (0.0 – 1.0 typical range)

        Returns:
            Current confirmed regime string: "trending" / "mean_reverting" / "uncertain"
        """
        if hurst > self._trend_th:
            self._consecutive_trend += 1
            self._consecutive_revert = 0
        elif hurst < self._revert_th:
            self._consecutive_revert += 1
            self._consecutive_trend = 0
        else:
            # In uncertain zone, slowly decay counts (don't immediately zero)
            # 在不確定區間，緩慢衰減計數（不立即歸零）
            self._consecutive_trend = max(0, self._consecutive_trend - 1)
            self._consecutive_revert = max(0, self._consecutive_revert - 1)

        if self._consecutive_trend >= self._required:
            self._current_regime = "trending"
        elif self._consecutive_revert >= self._required:
            self._current_regime = "mean_reverting"
        # If neither threshold met, keep current regime unchanged
        # 不滿足任一條件時保持當前 regime 不變

        return self._current_regime

    @property
    def current_regime(self) -> str:
        """Current confirmed regime / 當前確認的 regime"""
        return self._current_regime

    def get_state(self) -> dict:
        """
        Get full internal state for serialization / diagnostics.
        獲取完整內部狀態用於序列化/診斷。
        """
        return {
            "current_regime": self._current_regime,
            "consecutive_trend": self._consecutive_trend,
            "consecutive_revert": self._consecutive_revert,
            "trend_threshold": self._trend_th,
            "revert_threshold": self._revert_th,
            "required_consecutive": self._required,
        }

    def reset(self) -> None:
        """Reset all counters and regime to initial state / 重置所有計數器和 regime 到初始狀態"""
        self._consecutive_trend = 0
        self._consecutive_revert = 0
        self._current_regime = "uncertain"

    @classmethod
    def from_state(cls, state: Dict[str, Any]) -> "HurstHysteresis":
        """
        Restore HurstHysteresis from serialized state dict.
        從序列化的狀態字典還原 HurstHysteresis。
        """
        obj = cls(
            trend_threshold=state.get("trend_threshold", 0.60),
            revert_threshold=state.get("revert_threshold", 0.40),
            required_consecutive=state.get("required_consecutive", 6),
        )
        obj._consecutive_trend = state.get("consecutive_trend", 0)
        obj._consecutive_revert = state.get("consecutive_revert", 0)
        obj._current_regime = state.get("current_regime", "uncertain")
        return obj
