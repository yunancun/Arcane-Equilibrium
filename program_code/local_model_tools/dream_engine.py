"""
1-8: DreamEngine — Idle Monte Carlo Simulation / 閒置蒙特卡洛模擬引擎
====================================================================

MODULE_NOTE (中文):
  DreamEngine 在系統閒置時執行蒙特卡洛 what-if 模擬（認知 SPEC §4）：
  - 從最近 7 天真實 K 線中隨機抽取片段
  - 對策略參數（SL/TP/period 等）進行網格搜索
  - 每個參數值跑 ≥30 次模擬 [Q4]
  - 用 binomial test 計算信心度 [Q5]
  - 輸出 DreamInsight 供 CognitiveModulator 調整止損倍率

  暫不接入 CognitiveModulator（Phase 2 啟用）。
  Phase 1 版本使用簡化的閾值模型（不接入真實策略信號函數）。

MODULE_NOTE (English):
  DreamEngine runs Monte Carlo what-if simulations during system idle (SPEC §4):
  - Randomly sample segments from most recent 7 days of real candles
  - Grid search over strategy parameters (SL/TP/period etc.)
  - Each parameter value runs ≥30 simulations [Q4]
  - Confidence via binomial test [Q5]
  - Output DreamInsight for CognitiveModulator stoploss tuning

  Not yet integrated with CognitiveModulator (Phase 2 activation).
  Phase 1 version uses simplified threshold model (no real strategy signal functions).
"""

from __future__ import annotations

import logging
import math
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Constants / 常量
_MIN_SAMPLES_PER_PARAM = 30  # [Q4] Minimum simulations per parameter value
_PARAM_GRID_SIZE = 10        # Grid points per parameter
_MIN_IMPROVEMENT_PCT = 0.5   # Minimum improvement to report insight
_MIN_CONFIDENCE = 0.4        # Minimum confidence to report insight
_MAX_CYCLES_PER_IDLE = 10000 # Max simulations per idle period


@dataclass
class DreamInsight:
    """Result of Monte Carlo parameter optimization / 蒙特卡洛參數優化結果"""
    strategy_name: str = ""
    param_name: str = ""
    current_value: float = 0.0
    suggested_value: float = 0.0
    improvement_pct: float = 0.0
    confidence: float = 0.0
    sample_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "current": self.current_value,
            "suggested": self.suggested_value,
            "improvement_pct": round(self.improvement_pct, 4),
            "confidence": round(self.confidence, 4),
            "sample_count": self.sample_count,
        }


class DreamEngine:
    """
    Monte Carlo simulation engine for parameter optimization during idle.
    閒置期間的蒙特卡洛模擬引擎，用於參數優化。

    Thread-safe: uses threading.Lock for reentrancy guard [R1-3].
    """

    def __init__(self, seed: int | None = None) -> None:
        """
        Args:
            seed: Optional random seed for reproducible testing [R1-10].
        """
        self._rng = random.Random(seed)
        self._lock = threading.Lock()
        self._is_running = False
        self._total_cycles = 0
        self._actual_sim_count = 0
        self._last_run_ts_ms = 0
        self._insights: dict[str, dict[str, DreamInsight]] = {}

    def run_cycle(
        self,
        recent_candles: dict[str, list[dict[str, float]]],
        current_params: dict[str, dict[str, float]] | None = None,
    ) -> dict[str, Any]:
        """
        Run one batch of Monte Carlo simulations.
        執行一批蒙特卡洛模擬。

        Args:
            recent_candles: {symbol: [{open, high, low, close}, ...]}
            current_params: {strategy_name: {param_name: current_value}}

        Returns:
            Cycle stats dict.
        """
        with self._lock:
            if self._is_running:
                return {"status": "already_running", "total_simulations": self._actual_sim_count}
            self._is_running = True

        try:
            params = current_params or self._default_params()
            sim_count = 0

            for strategy_name, strategy_params in params.items():
                for param_name, current_value in strategy_params.items():
                    grid = self._build_grid(param_name, current_value)
                    results: dict[float, list[float]] = {}

                    for grid_val in grid:
                        pnls: list[float] = []
                        for _ in range(_MIN_SAMPLES_PER_PARAM):
                            pnl = self._simulate_single_run(
                                recent_candles, param_name, grid_val,
                            )
                            pnls.append(pnl)
                            sim_count += 1
                        results[grid_val] = pnls

                    self._evaluate_results(strategy_name, param_name, current_value, results)

            with self._lock:
                self._actual_sim_count += sim_count
                self._total_cycles += 1
                self._last_run_ts_ms = int(time.time() * 1000)
                self._is_running = False

            return {
                "cycles_completed": sim_count,
                "total_cycles": self._total_cycles,
                "total_simulations": self._actual_sim_count,
                "new_insights": sum(len(v) for v in self._insights.values()),
            }

        except Exception as e:
            with self._lock:
                self._is_running = False
            logger.warning("DreamEngine.run_cycle error: %s", e)
            return {"status": "error", "error": str(e)}

    def _default_params(self) -> dict[str, dict[str, float]]:
        """Default parameter set for simplified Phase 1 threshold model."""
        return {
            "default_strategy": {
                "stoploss_pct": 5.0,
                "takeprofit_pct": 10.0,
            },
        }

    def _build_grid(self, param_name: str, current: float) -> list[float]:
        """Build parameter grid centered on current value."""
        ranges = {
            "stoploss_pct": (1.0, 10.0),
            "takeprofit_pct": (3.0, 20.0),
            "confidence_threshold": (0.3, 0.9),
        }
        lo, hi = ranges.get(param_name, (current * 0.5, current * 2.0))
        if hi <= lo:
            return [current]
        step = (hi - lo) / (_PARAM_GRID_SIZE - 1)
        grid = [lo + i * step for i in range(_PARAM_GRID_SIZE)]
        if lo <= current <= hi and current not in grid:
            grid.append(current)
        return sorted(grid)

    def _simulate_single_run(
        self,
        candles_by_symbol: dict[str, list[dict[str, float]]],
        param_name: str,
        param_value: float,
    ) -> float:
        """
        Run one Monte Carlo simulation.
        執行一次蒙特卡洛模擬。

        [E6] Random direction to eliminate K-line color bias.
        """
        # Pick random symbol with data / 隨機選擇有數據的品種
        symbols = [s for s, c in candles_by_symbol.items() if len(c) >= 25]
        if not symbols:
            return 0.0
        symbol = self._rng.choice(symbols)
        data = candles_by_symbol[symbol]

        # Random segment / 隨機片段
        run_length = self._rng.randint(24, min(72, len(data) - 1))
        start = self._rng.randint(0, len(data) - run_length - 1)
        segment = data[start: start + run_length]

        entry_price = segment[0].get("close", 0.0)
        if entry_price <= 0:
            return 0.0

        # [E6] Random direction / 隨機方向
        direction = self._rng.choice(["long", "short"])

        # Determine SL/TP based on param / 根據參數確定 SL/TP
        sl_pct = param_value if param_name == "stoploss_pct" else 5.0
        tp_pct = param_value if param_name == "takeprofit_pct" else 10.0

        # Walk through bars / 遍歷 K 線
        for candle in segment[1:]:
            c_high = candle.get("high", entry_price)
            c_low = candle.get("low", entry_price)

            if direction == "long":
                pnl_high = (c_high - entry_price) / entry_price * 100
                pnl_low = (c_low - entry_price) / entry_price * 100
            else:
                pnl_high = (entry_price - c_low) / entry_price * 100
                pnl_low = (entry_price - c_high) / entry_price * 100

            if pnl_low <= -sl_pct:
                return -sl_pct
            if pnl_high >= tp_pct:
                return tp_pct

        # No trigger — use final price / 未觸發 — 使用最終價格
        final = segment[-1].get("close", entry_price)
        if direction == "long":
            return (final - entry_price) / entry_price * 100
        else:
            return (entry_price - final) / entry_price * 100

    def _evaluate_results(
        self,
        strategy_name: str,
        param_name: str,
        current_value: float,
        results: dict[float, list[float]],
    ) -> None:
        """
        [Q5] Evaluate simulation results with binomial test.
        用 binomial test 評估模擬結果。
        """
        best_value = current_value
        best_exp = 0.0

        for val, pnls in results.items():
            if len(pnls) < _MIN_SAMPLES_PER_PARAM:
                continue
            exp = sum(pnls) / len(pnls)
            if exp > best_exp:
                best_exp = exp
                best_value = val

        # Current expectation / 當前期望
        current_pnls = results.get(current_value, [])
        current_exp = sum(current_pnls) / len(current_pnls) if current_pnls else 0.0

        improvement = best_exp - current_exp
        if improvement < _MIN_IMPROVEMENT_PCT:
            return

        # [Q5] Binomial test confidence / 二項檢驗信心度
        best_pnls = results.get(best_value, [])
        confidence = self._binomial_confidence(best_pnls)

        if confidence < _MIN_CONFIDENCE:
            return

        # Store insight / 存儲洞察
        if strategy_name not in self._insights:
            self._insights[strategy_name] = {}

        self._insights[strategy_name][param_name] = DreamInsight(
            strategy_name=strategy_name,
            param_name=param_name,
            current_value=current_value,
            suggested_value=best_value,
            improvement_pct=improvement,
            confidence=confidence,
            sample_count=len(best_pnls),
        )

    @staticmethod
    def _binomial_confidence(pnls: list[float]) -> float:
        """
        [Q5] Binomial test: H0 = p(win) = 0.5 (random).
        Confidence = 1 - p_value (one-tailed).
        """
        n = len(pnls)
        if n < 5:
            return 0.0
        wins = sum(1 for p in pnls if p > 0)
        p_hat = wins / n
        if p_hat <= 0.5:
            return 0.0

        # Normal approximation to binomial / 二項式的正態近似
        z = (p_hat - 0.5) / math.sqrt(0.25 / n)
        # One-tailed p-value via complementary error function
        p_value = 0.5 * math.erfc(z / math.sqrt(2))
        return max(0.0, min(1.0, 1.0 - p_value))

    def get_insights(self) -> dict[str, Any]:
        """
        Get all current dream insights.
        獲取所有當前夢境洞察。
        """
        result: dict[str, Any] = {}
        for strategy_name, params in self._insights.items():
            result[strategy_name] = {
                pname: insight.to_dict() for pname, insight in params.items()
            }
        result["_meta"] = {
            "total_cycles": self._total_cycles,
            "total_simulations": self._actual_sim_count,
            "last_run_ts_ms": self._last_run_ts_ms,
            "is_running": self._is_running,
        }
        return result

    def get_status(self) -> dict[str, Any]:
        return {
            "is_running": self._is_running,
            "total_cycles": self._total_cycles,
            "total_simulations": self._actual_sim_count,
            "last_run_ts_ms": self._last_run_ts_ms,
            "insight_count": sum(len(v) for v in self._insights.values()),
        }
