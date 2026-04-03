"""
1-6: CognitiveModulator — L0 Decision Threshold Modulation / L0 決策門檻調製
==============================================================================

MODULE_NOTE (中文):
  CognitiveModulator 根據歷史績效、遺憾數據、蒙特卡洛建議動態調整策略決策參數：
  - confidence_floor：信號信心下限（越高 = 越保守）
  - qty_ceiling：倉位大小上限倍率（1.0 = 滿倉，0.3 = 最小倉）
  - stoploss_multiplier：止損距離倍率
  - scan_interval_s：掃描間隔（秒）

  所有輸出使用 EMA(α=0.3) 平滑以防止振盪。
  [Q1] max 單因子（不求和），[Q6] EMA 平滑，[R1-5] 連虧時忽略負向壓力。

MODULE_NOTE (English):
  CognitiveModulator dynamically adjusts Strategist decision parameters based on
  historical performance, regret data, and Monte Carlo suggestions:
  - confidence_floor: signal confidence minimum (higher = more conservative)
  - qty_ceiling: position size ceiling multiplier (1.0 = full, 0.3 = minimum)
  - stoploss_multiplier: stop-loss distance multiplier
  - scan_interval_s: scan interval (seconds)

  All outputs EMA-smoothed (α=0.3) to prevent oscillation.
  [Q1] max single-factor (not sum), [Q6] EMA smoothing, [R1-5] ignore downward on streak.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Base parameters / 基礎參數
_BASE_CONFIDENCE_FLOOR = 0.60
_BASE_QTY_CEILING = 1.0
_BASE_STOPLOSS_MULT = 1.0
_BASE_SCAN_INTERVAL = 1800  # 30 minutes

# Clamp ranges / 限幅範圍
_MIN_CONF_FLOOR, _MAX_CONF_FLOOR = 0.45, 0.85
_MIN_QTY_CEIL, _MAX_QTY_CEIL = 0.3, 1.0
_MIN_SL_MULT, _MAX_SL_MULT = 0.8, 2.0
_MIN_SCAN, _MAX_SCAN = 300, 3600

# EMA smoothing / EMA 平滑
_EMA_ALPHA = 0.3


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


class CognitiveModulator:
    """
    L0 deterministic decision threshold modulator (~120 lines).
    L0 確定性決策門檻調製器。

    Thread-safe: no shared mutable state beyond internal parameters.
    """

    def __init__(self) -> None:
        self._confidence_floor = _BASE_CONFIDENCE_FLOOR
        self._qty_ceiling = _BASE_QTY_CEILING
        self._stoploss_mult = _BASE_STOPLOSS_MULT
        self._scan_interval = float(_BASE_SCAN_INTERVAL)
        self._update_count = 0

    def update(
        self,
        *,
        consecutive_losses: int = 0,
        weekly_net_pnl: float = 0.0,
        regret_data: dict[str, Any] | None = None,
        dream_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Update all modulated parameters based on current state.
        根據當前狀態更新所有調製參數。

        Args:
            consecutive_losses: Current consecutive loss streak.
            weekly_net_pnl: Net PnL this week (after all costs).
            regret_data: From OpportunityTracker.get_regret_summary(). May be empty dict.
            dream_data: From DreamEngine.get_insights(). May be empty dict.

        Returns:
            Dict with all current parameter values.
        """
        rd = regret_data or {}
        dd = dream_data or {}
        self._update_count += 1

        # ── Confidence floor / 信心下限 ──
        target_conf = self._compute_confidence_floor(consecutive_losses, weekly_net_pnl, rd)
        self._confidence_floor = _EMA_ALPHA * target_conf + (1 - _EMA_ALPHA) * self._confidence_floor

        # ── Qty ceiling / 倉位上限 ──
        target_qty = self._compute_qty_ceiling(consecutive_losses, weekly_net_pnl)
        self._qty_ceiling = _EMA_ALPHA * target_qty + (1 - _EMA_ALPHA) * self._qty_ceiling

        # ── Stoploss multiplier / 止損倍率 ──
        target_sl = self._compute_stoploss_mult(dd)
        self._stoploss_mult = _EMA_ALPHA * target_sl + (1 - _EMA_ALPHA) * self._stoploss_mult

        # ── Scan interval / 掃描間隔 ──
        target_scan = self._compute_scan_interval(weekly_net_pnl, rd)
        self._scan_interval = _EMA_ALPHA * target_scan + (1 - _EMA_ALPHA) * self._scan_interval

        return self.get_all_params()

    def _compute_confidence_floor(
        self, consec_losses: int, weekly_pnl: float, rd: dict,
    ) -> float:
        """[Q1] max single-factor, [R1-5] ignore neg on loss streak."""
        pos: list[float] = []
        neg: list[float] = []

        direction = rd.get("net_regret_direction", "balanced")
        if direction == "overtrading":
            pos.append(0.05)
        elif direction == "undertrading":
            neg.append(-0.03)

        if consec_losses >= 3:
            pos.append(0.02 * min(consec_losses - 2, 5))

        if weekly_pnl < 0:
            pos.append(0.02)

        pos_net = max(pos) if pos else 0.0
        # [R1-5]: ignore downward pressure during loss streak / 連虧時忽略向下壓力
        neg_net = 0.0 if consec_losses >= 3 else (min(neg) if neg else 0.0)

        return _clamp(_BASE_CONFIDENCE_FLOOR + pos_net + neg_net, _MIN_CONF_FLOOR, _MAX_CONF_FLOOR)

    def _compute_qty_ceiling(self, consec_losses: int, weekly_pnl: float) -> float:
        """[Q1] Single worst-case factor."""
        adj: list[float] = []
        if consec_losses >= 3:
            adj.append(-0.05 * min(consec_losses - 2, 5))
        if weekly_pnl < 0:
            adj.append(-0.1)
        net = min(adj) if adj else 0.0
        return _clamp(_BASE_QTY_CEILING + net, _MIN_QTY_CEIL, _MAX_QTY_CEIL)

    def _compute_stoploss_mult(self, dd: dict) -> float:
        """Dream-based stoploss adjustment."""
        g = dd.get("global", dd.get("_meta", {}))
        dream_sl = g.get("stoploss_multiplier")
        dream_conf = g.get("confidence", 0.0)
        if dream_sl is not None and dream_conf > 0.6:
            blend = (1.0 - dream_conf * 0.3) * _BASE_STOPLOSS_MULT + dream_conf * 0.3 * dream_sl
            return _clamp(blend, _MIN_SL_MULT, _MAX_SL_MULT)
        return _BASE_STOPLOSS_MULT

    def _compute_scan_interval(self, weekly_pnl: float, rd: dict) -> float:
        """[R1-1] Speed-up + slow-down."""
        interval = float(_BASE_SCAN_INTERVAL)
        direction = rd.get("net_regret_direction", "balanced")

        if weekly_pnl < 0:
            interval = min(interval, _BASE_SCAN_INTERVAL * 0.5)
        if direction == "undertrading":
            interval = min(interval, _BASE_SCAN_INTERVAL * 0.7)
        # [R1-1] Overtrading slow-down / 過度交易減速
        if direction == "overtrading":
            interval = max(interval, _BASE_SCAN_INTERVAL * 1.5)

        return _clamp(interval, _MIN_SCAN, _MAX_SCAN)

    # ── Public getters / 公開存取器 ──

    def get_confidence_floor(self) -> float:
        return round(self._confidence_floor, 4)

    def get_qty_ceiling(self) -> float:
        return round(self._qty_ceiling, 4)

    def get_stoploss_multiplier(self) -> float:
        return round(self._stoploss_mult, 4)

    def get_scan_interval_seconds(self) -> int:
        return int(self._scan_interval)

    def get_all_params(self) -> dict[str, Any]:
        return {
            "confidence_floor": self.get_confidence_floor(),
            "qty_ceiling": self.get_qty_ceiling(),
            "stoploss_multiplier": self.get_stoploss_multiplier(),
            "scan_interval_s": self.get_scan_interval_seconds(),
            "update_count": self._update_count,
        }
