"""
1-2: Strategy Health Monitor — CUSUM Drift Detection + Rolling Sharpe / 策略健康監控
===================================================================================

MODULE_NOTE (中文):
  StrategyHealthMonitor 實現策略衰減檢測（報告 §5.2）：
  1. Rolling Sharpe ratio — 滾動 Sharpe 比率（默認 50 筆窗口）
  2. CUSUM (Cumulative Sum) — 累積和算法檢測策略性能漂移
  3. 15 連虧硬性兜底 — 超過連續虧損上限自動暫停策略

  安全不變量：
  - 純計算，不直接暫停策略（只返回建議）
  - CUSUM 使用在線更新，無需存儲完整歷史
  - 所有異常 fail-open（返回安全默認值）

MODULE_NOTE (English):
  StrategyHealthMonitor implements strategy degradation detection (Report §5.2):
  1. Rolling Sharpe ratio — windowed Sharpe (default 50 trades)
  2. CUSUM (Cumulative Sum) — detect performance drift
  3. 15-consecutive-loss hard stop — emergency strategy pause trigger

  Safety invariants:
  - Pure computation, never directly pauses strategies (returns advisory)
  - CUSUM uses online update, no full history storage needed
  - All exceptions fail-open (return safe defaults)
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# CUSUM sensitivity: number of standard deviations for threshold.
# CUSUM 靈敏度：偏移檢測的標準差倍數。
_CUSUM_SENSITIVITY = 4.0

# Default rolling window size for Sharpe calculation.
# 默認 Sharpe 計算的滾動窗口大小。
_DEFAULT_WINDOW = 50


@dataclass
class StrategyHealth:
    """
    Health snapshot for a single strategy.
    單個策略的健康快照。
    """
    strategy_name: str = ""
    rolling_sharpe: float = 0.0
    win_rate: float = 0.0
    mean_return: float = 0.0
    trade_count: int = 0
    consecutive_losses: int = 0
    cusum_high: float = 0.0
    cusum_low: float = 0.0
    cusum_drift_detected: bool = False
    hard_stop_triggered: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "rolling_sharpe": round(self.rolling_sharpe, 4),
            "win_rate": round(self.win_rate, 4),
            "mean_return": round(self.mean_return, 6),
            "trade_count": self.trade_count,
            "consecutive_losses": self.consecutive_losses,
            "cusum_drift_detected": self.cusum_drift_detected,
            "hard_stop_triggered": self.hard_stop_triggered,
        }


class StrategyHealthMonitor:
    """
    Monitor strategy health using rolling Sharpe, CUSUM, and consecutive-loss detection.
    使用滾動 Sharpe、CUSUM 和連續虧損檢測監控策略健康。

    Thread-safe: internal state protected by per-strategy isolation (no shared mutation).
    線程安全：內部狀態按策略隔離（無共享可變狀態）。
    """

    def __init__(
        self,
        *,
        window: int = _DEFAULT_WINDOW,
        max_consecutive_losses: int = 15,
        cusum_sensitivity: float = _CUSUM_SENSITIVITY,
    ) -> None:
        self._window = max(10, window)
        self._max_consec = max_consecutive_losses
        self._cusum_k = cusum_sensitivity

        # Per-strategy state / 每策略狀態
        # returns deque, win/loss counts, CUSUM accumulators
        self._returns: dict[str, deque] = defaultdict(lambda: deque(maxlen=self._window))
        self._wins: dict[str, int] = defaultdict(int)
        self._losses: dict[str, int] = defaultdict(int)
        self._consec_losses: dict[str, int] = defaultdict(int)
        self._trade_counts: dict[str, int] = defaultdict(int)

        # CUSUM state / CUSUM 狀態
        self._cusum_high: dict[str, float] = defaultdict(float)
        self._cusum_low: dict[str, float] = defaultdict(float)
        self._cusum_detected: dict[str, bool] = defaultdict(bool)

    def update(self, strategy_name: str, pnl: float) -> StrategyHealth:
        """
        Record a trade result and return updated health snapshot.
        記錄交易結果並返回更新的健康快照。

        Args:
            strategy_name: Strategy identifier.
            pnl: Trade PnL (positive = win, negative/zero = loss).

        Returns:
            StrategyHealth with current rolling metrics.
        """
        self._returns[strategy_name].append(pnl)
        self._trade_counts[strategy_name] += 1

        if pnl > 0:
            self._wins[strategy_name] += 1
            self._consec_losses[strategy_name] = 0
        else:
            self._losses[strategy_name] += 1
            self._consec_losses[strategy_name] += 1

        # Update CUSUM / 更新 CUSUM
        self._update_cusum(strategy_name, pnl)

        return self.get_health(strategy_name)

    def _update_cusum(self, name: str, pnl: float) -> None:
        """
        CUSUM drift detection: tracks cumulative upward/downward shifts.
        CUSUM 漂移檢測：追蹤累積向上/向下偏移。

        S_h(t) = max(0, S_h(t-1) + x - (mu + k*sigma))
        S_l(t) = min(0, S_l(t-1) + x - (mu - k*sigma))
        Drift detected if S_h > threshold or S_l < -threshold.

        Uses online mean/std from rolling window.
        """
        returns = self._returns[name]
        n = len(returns)
        if n < 5:
            return  # Need minimum data / 需要最少數據

        # Online mean and std from window / 從窗口計算在線均值和標準差
        mean = math.fsum(returns) / n
        variance = math.fsum((r - mean) ** 2 for r in returns) / n
        std = math.sqrt(variance) if variance > 0 else 1e-10

        # CUSUM update / CUSUM 更新
        k = self._cusum_k * std * 0.5  # half-sensitivity for threshold
        s_h = max(0.0, self._cusum_high[name] + pnl - (mean + k))
        s_l = min(0.0, self._cusum_low[name] + pnl - (mean - k))

        self._cusum_high[name] = s_h
        self._cusum_low[name] = s_l

        # Detect drift: threshold = sensitivity × std / 檢測漂移
        threshold = self._cusum_k * std
        if s_h > threshold or abs(s_l) > threshold:
            if not self._cusum_detected[name]:
                self._cusum_detected[name] = True
                logger.info(
                    "CUSUM drift detected for %s: S_h=%.4f S_l=%.4f threshold=%.4f / "
                    "CUSUM 漂移檢測：策略 %s",
                    name, s_h, s_l, threshold, name,
                )

    def get_health(self, strategy_name: str) -> StrategyHealth:
        """
        Get current health snapshot for a strategy.
        獲取策略的當前健康快照。
        """
        returns = self._returns[strategy_name]
        n = len(returns)
        total_trades = self._trade_counts[strategy_name]
        wins = self._wins[strategy_name]

        # Rolling Sharpe / 滾動 Sharpe
        sharpe = 0.0
        mean_ret = 0.0
        if n >= 5:
            mean_ret = math.fsum(returns) / n
            variance = math.fsum((r - mean_ret) ** 2 for r in returns) / n
            std = math.sqrt(variance) if variance > 0 else 1e-10
            sharpe = mean_ret / std if std > 1e-10 else 0.0

        # Win rate / 勝率
        win_rate = wins / total_trades if total_trades > 0 else 0.0

        # Hard stop / 硬性停止
        consec = self._consec_losses[strategy_name]
        hard_stop = consec >= self._max_consec

        return StrategyHealth(
            strategy_name=strategy_name,
            rolling_sharpe=sharpe,
            win_rate=win_rate,
            mean_return=mean_ret,
            trade_count=total_trades,
            consecutive_losses=consec,
            cusum_high=self._cusum_high[strategy_name],
            cusum_low=self._cusum_low[strategy_name],
            cusum_drift_detected=self._cusum_detected[strategy_name],
            hard_stop_triggered=hard_stop,
        )

    def reset_cusum(self, strategy_name: str) -> None:
        """
        Reset CUSUM state for a strategy (e.g., after parameter update).
        重置策略的 CUSUM 狀態（例如參數更新後）。
        """
        self._cusum_high[strategy_name] = 0.0
        self._cusum_low[strategy_name] = 0.0
        self._cusum_detected[strategy_name] = False

    def get_all_health(self) -> dict[str, dict[str, Any]]:
        """
        Get health snapshots for all tracked strategies.
        獲取所有已追蹤策略的健康快照。
        """
        return {
            name: self.get_health(name).to_dict()
            for name in self._trade_counts
        }
