"""
1-10: Shadow Decision Tracker — Four-Stage Exit Condition Data / 影子決策追蹤
=============================================================================

MODULE_NOTE (中文):
  ShadowDecisionTracker 記錄策略在四個放權階段下的假設退出結果（報告 §2）：
  - Stage 1 (Paper only)：純本地止損
  - Stage 2 (Supervised)：本地止損 + AI 建議 + 人工確認
  - Stage 3 (Constrained)：AI 自主 + 風控硬限
  - Stage 4 (Autonomous)：AI 完全自主（P0/P1 內）

  目的：在 Paper Trading 階段收集數據，比較四階段下的假設表現，
  為未來放權決策提供量化依據（Phase 3 四階段放權框架的數據基礎）。

MODULE_NOTE (English):
  ShadowDecisionTracker records hypothetical exit outcomes under four authority stages:
  - Stage 1 (Paper only): local stop-loss only
  - Stage 2 (Supervised): local SL + AI suggestion + human confirmation
  - Stage 3 (Constrained): AI autonomous + hard risk limits
  - Stage 4 (Autonomous): AI fully autonomous (within P0/P1)

  Purpose: collect data during Paper Trading to compare hypothetical performance
  across four stages, providing quantitative basis for future authority delegation
  (Phase 3 four-stage delegation framework).
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_MAX_RECORDS = 500


@dataclass
class ShadowExitRecord:
    """
    A single shadow exit evaluation record.
    單條影子退出評估記錄。
    """
    symbol: str = ""
    strategy_name: str = ""
    entry_price: float = 0.0
    current_price: float = 0.0
    pnl_pct: float = 0.0
    ts_ms: int = 0
    # What each stage would do / 每個階段會做什麼
    stage1_action: str = "hold"  # "exit_sl" | "exit_tp" | "hold"
    stage2_action: str = "hold"  # "exit_ai_suggest" | "hold"
    stage3_action: str = "hold"  # "exit_ai_auto" | "hold"
    stage4_action: str = "hold"  # "exit_full_auto" | "hold"
    # Hypothetical PnL if exited at this point / 若此刻退出的假設 PnL
    stage1_pnl: float = 0.0
    stage2_pnl: float = 0.0
    stage3_pnl: float = 0.0
    stage4_pnl: float = 0.0


class ShadowDecisionTracker:
    """
    Track hypothetical exit decisions under four authority stages.
    追蹤四個放權階段下的假設退出決策。

    Thread-safe: per-symbol state isolation.
    """

    def __init__(
        self,
        *,
        health_monitor: Any = None,
        opportunity_tracker: Any = None,
    ) -> None:
        self._health_monitor = health_monitor
        self._opportunity_tracker = opportunity_tracker
        self._records: deque[ShadowExitRecord] = deque(maxlen=_MAX_RECORDS)
        self._stage_pnl_sums: dict[str, float] = {
            "stage1": 0.0, "stage2": 0.0, "stage3": 0.0, "stage4": 0.0,
        }
        self._stage_exit_counts: dict[str, int] = {
            "stage1": 0, "stage2": 0, "stage3": 0, "stage4": 0,
        }
        self._eval_count = 0

    def evaluate_exit(
        self,
        symbol: str,
        strategy_name: str,
        entry_price: float,
        current_price: float,
        *,
        sl_pct: float = 5.0,
        tp_pct: float = 10.0,
        ai_suggests_exit: bool = False,
        health_degraded: bool = False,
        regret_direction: str = "balanced",
    ) -> ShadowExitRecord:
        """
        Evaluate what each stage would decide for the current position.
        評估每個階段對當前持倉的決策。

        Args:
            symbol, strategy_name, entry_price, current_price: Position data.
            sl_pct: Stop-loss percentage.
            tp_pct: Take-profit percentage.
            ai_suggests_exit: Whether AI model recommends exit.
            health_degraded: Whether StrategyHealthMonitor flags degradation.
            regret_direction: From OpportunityTracker ("overtrading"/"undertrading"/"balanced").

        Returns:
            ShadowExitRecord with each stage's hypothetical action.
        """
        if entry_price <= 0:
            return ShadowExitRecord()

        pnl_pct = (current_price - entry_price) / entry_price * 100
        self._eval_count += 1

        record = ShadowExitRecord(
            symbol=symbol,
            strategy_name=strategy_name,
            entry_price=entry_price,
            current_price=current_price,
            pnl_pct=pnl_pct,
            ts_ms=int(time.time() * 1000),
        )

        # Stage 1: Pure local SL/TP only / 純本地止損止盈
        if pnl_pct <= -sl_pct:
            record.stage1_action = "exit_sl"
            record.stage1_pnl = -sl_pct
        elif pnl_pct >= tp_pct:
            record.stage1_action = "exit_tp"
            record.stage1_pnl = tp_pct
        else:
            record.stage1_pnl = pnl_pct

        # Stage 2: SL/TP + AI advisory + human gate / SL/TP + AI 建議 + 人工確認
        record.stage2_action = record.stage1_action  # inherits SL/TP
        record.stage2_pnl = record.stage1_pnl
        if record.stage2_action == "hold" and ai_suggests_exit and pnl_pct > 0:
            record.stage2_action = "exit_ai_suggest"
            record.stage2_pnl = pnl_pct

        # Stage 3: AI auto + hard limits / AI 自主 + 硬限
        record.stage3_action = record.stage1_action
        record.stage3_pnl = record.stage1_pnl
        if record.stage3_action == "hold":
            if health_degraded:
                record.stage3_action = "exit_ai_auto"
                record.stage3_pnl = pnl_pct
            elif ai_suggests_exit:
                record.stage3_action = "exit_ai_auto"
                record.stage3_pnl = pnl_pct

        # Stage 4: Full autonomy (exits also on regret signals) / 完全自主
        record.stage4_action = record.stage3_action
        record.stage4_pnl = record.stage3_pnl
        if record.stage4_action == "hold" and regret_direction == "overtrading" and pnl_pct > 1.0:
            record.stage4_action = "exit_full_auto"
            record.stage4_pnl = pnl_pct

        # Track cumulative stats / 追蹤累積統計
        for stage in ["stage1", "stage2", "stage3", "stage4"]:
            action = getattr(record, f"{stage}_action")
            if action != "hold":
                self._stage_exit_counts[stage] += 1
                self._stage_pnl_sums[stage] += getattr(record, f"{stage}_pnl")

        self._records.append(record)
        return record

    def get_comparison(self) -> dict[str, Any]:
        """
        Get comparative summary across all four stages.
        獲取四個階段的比較摘要。
        """
        return {
            "total_evaluations": self._eval_count,
            "stages": {
                stage: {
                    "exits": self._stage_exit_counts[stage],
                    "cumulative_pnl_pct": round(self._stage_pnl_sums[stage], 4),
                    "avg_exit_pnl": round(
                        self._stage_pnl_sums[stage] / self._stage_exit_counts[stage], 4
                    ) if self._stage_exit_counts[stage] > 0 else 0.0,
                }
                for stage in ["stage1", "stage2", "stage3", "stage4"]
            },
            "records_buffered": len(self._records),
        }
