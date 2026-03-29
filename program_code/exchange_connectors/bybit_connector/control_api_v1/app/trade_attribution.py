from __future__ import annotations

"""
Trade Attribution Engine / 交易归因引擎
根原则 §5.8：每笔交易必须可解释、可追踪
根原则 §5.12：系统必须能自动归因交易结果（alpha / timing / sizing / execution / cost 错误分类）

MODULE_NOTE (中文):
  本模块负责将已完成的交易分解为多个归因因子，区分"判断"（skill）和"偶然"（luck）：
  - ALPHA: 方向正确性，反映是否选对了交易方向
  - TIMING: 入场/出场时机，反映时序判断的质量
  - SIZING: 仓位大小选择，反映头寸规模与波动率的匹配度
  - EXECUTION: 成交质量，反映滑点与期望的差异
  - COST: 费用效率，反映手续费优化（maker vs taker）
  - LUCK: 剩余的不可解释分量

  核心能力：
  - attribute_trade()：分解单笔已完成交易
  - aggregate_attribution()：跨多笔交易的策略级视图
  - get_strategy_skill_ratio()：长期追踪 skill vs luck 的比例

  线程安全，支持序列化。

MODULE_NOTE (English):
  Trade Attribution Engine that decomposes completed trades into attribution factors
  that distinguish skill (judgment) from luck (random/unexplained):
  - ALPHA: directional correctness (was the direction right?)
  - TIMING: entry/exit timing quality (did timing improve PnL vs random?)
  - SIZING: position sizing appropriateness (size vs volatility match)
  - EXECUTION: fill quality (slippage vs expected)
  - COST: fee optimization (maker vs taker usage)
  - LUCK: residual unexplained component

  Core capabilities:
  - attribute_trade(): decompose a completed trade
  - aggregate_attribution(): strategy-level view across multiple trades
  - get_strategy_skill_ratio(): track skill vs luck over time

  Thread-safe, serializable.
"""

import dataclasses
import datetime
import json
import logging
import threading
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, List, Dict, Any
from decimal import Decimal

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Enums & Constants / 枚举与常数
# ═══════════════════════════════════════════════════════════════════════════════

class AttributionCategory(str, Enum):
    """Attribution factor categories / 归因因子类别"""
    ALPHA = "alpha"           # Directional correctness / 方向正确性
    TIMING = "timing"         # Entry/exit timing quality / 入场/出场时机
    SIZING = "sizing"         # Position sizing vs volatility / 仓位与波动率匹配
    EXECUTION = "execution"   # Fill quality and slippage / 成交质量与滑点
    COST = "cost"             # Fee optimization / 费用效率
    LUCK = "luck"             # Residual unexplained / 剩余不可解释分量


class SkillLevel(str, Enum):
    """Skill classification based on skill_pct / 基于 skill_pct 的技能分类"""
    HIGH_SKILL = "high_skill"           # skill_pct > 0.70
    MODERATE_SKILL = "moderate_skill"   # 0.40 <= skill_pct <= 0.70
    LOW_SKILL = "low_skill"             # skill_pct < 0.40


# ═══════════════════════════════════════════════════════════════════════════════
# Data Classes / 数据类
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class AttributionScore:
    """
    Single attribution factor score / 单个归因因子分数

    Attributes:
      category: AttributionCategory (ALPHA, TIMING, SIZING, EXECUTION, COST, LUCK)
      score: float, -1.0 to 1.0 (negative = detracted from PnL, positive = contributed)
      contribution_pct: float, 0.0 to 1.0 (what % of gross PnL came from this factor?)
      explanation: str (human-readable explanation of this factor's impact)
    """
    category: AttributionCategory
    score: float  # -1.0 to 1.0
    contribution_pct: float  # 0.0 to 1.0
    explanation: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict"""
        return {
            "category": self.category.value,
            "score": round(self.score, 4),
            "contribution_pct": round(self.contribution_pct, 4),
            "explanation": self.explanation,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> AttributionScore:
        """Deserialize from dict"""
        return AttributionScore(
            category=AttributionCategory(d["category"]),
            score=float(d["score"]),
            contribution_pct=float(d["contribution_pct"]),
            explanation=str(d["explanation"]),
        )


@dataclass
class TradeAttributionResult:
    """
    Attribution decomposition for a single completed trade / 单笔交易的归因分解

    Attributes:
      trade_id: str (unique trade identifier)
      symbol: str (e.g., "BTCUSDT")
      strategy: str (strategy name that executed this trade)
      pnl_gross: float (gross PnL before fees)
      pnl_net: float (net PnL after all costs)
      attribution_scores: List[AttributionScore] (6 factors: ALPHA, TIMING, SIZING, EXECUTION, COST, LUCK)
      skill_pct: float (0.0-1.0, aggregate skill contribution)
      luck_pct: float (0.0-1.0, aggregate luck contribution)
      total_cost: float (total cost: fees + slippage + AI cost)
      timestamp: datetime (when trade was completed)
    """
    trade_id: str
    symbol: str
    strategy: str
    pnl_gross: float
    pnl_net: float
    attribution_scores: List[AttributionScore]
    skill_pct: float  # 0.0 to 1.0
    luck_pct: float  # 0.0 to 1.0
    total_cost: float
    timestamp: datetime.datetime

    def __post_init__(self):
        """Validate invariants"""
        if not isinstance(self.timestamp, datetime.datetime):
            raise ValueError("timestamp must be datetime.datetime")

        # skill_pct + luck_pct should sum to ~1.0 (allow small floating point error)
        if abs((self.skill_pct + self.luck_pct) - 1.0) > 0.01:
            logger.warning(
                f"skill_pct ({self.skill_pct}) + luck_pct ({self.luck_pct}) "
                f"does not sum to 1.0 for trade {self.trade_id}"
            )

        # Verify attribution_scores contain all categories
        categories = {score.category for score in self.attribution_scores}
        expected_categories = set(AttributionCategory)
        if categories != expected_categories:
            raise ValueError(
                f"Attribution scores must contain all categories. "
                f"Missing: {expected_categories - categories}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict"""
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "strategy": self.strategy,
            "pnl_gross": round(self.pnl_gross, 8),
            "pnl_net": round(self.pnl_net, 8),
            "attribution_scores": [s.to_dict() for s in self.attribution_scores],
            "skill_pct": round(self.skill_pct, 4),
            "luck_pct": round(self.luck_pct, 4),
            "total_cost": round(self.total_cost, 8),
            "timestamp": self.timestamp.isoformat(),
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> TradeAttributionResult:
        """Deserialize from dict"""
        return TradeAttributionResult(
            trade_id=str(d["trade_id"]),
            symbol=str(d["symbol"]),
            strategy=str(d["strategy"]),
            pnl_gross=float(d["pnl_gross"]),
            pnl_net=float(d["pnl_net"]),
            attribution_scores=[
                AttributionScore.from_dict(s) for s in d["attribution_scores"]
            ],
            skill_pct=float(d["skill_pct"]),
            luck_pct=float(d["luck_pct"]),
            total_cost=float(d["total_cost"]),
            timestamp=datetime.datetime.fromisoformat(d["timestamp"]),
        )


@dataclass
class StrategyAttributionSummary:
    """
    Aggregated attribution metrics for a strategy across multiple trades / 策略级汇总

    Attributes:
      strategy: str (strategy name)
      period_start: datetime (start of aggregation period)
      period_end: datetime (end of aggregation period)
      trade_count: int (number of trades)
      total_pnl_gross: float
      total_pnl_net: float
      win_rate: float (0.0-1.0, fraction of trades with positive pnl_net)
      avg_skill_pct: float (average skill contribution across trades)
      avg_luck_pct: float (average luck contribution across trades)
      skill_consistency: float (std dev of skill_pct across trades, lower = more consistent)
      total_cost: float (sum of all trade costs)
      attribution_by_category: Dict[str, float] (average contribution % by category)
    """
    strategy: str
    period_start: datetime.datetime
    period_end: datetime.datetime
    trade_count: int
    total_pnl_gross: float
    total_pnl_net: float
    win_rate: float
    avg_skill_pct: float
    avg_luck_pct: float
    skill_consistency: float
    total_cost: float
    attribution_by_category: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict"""
        return {
            "strategy": self.strategy,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "trade_count": self.trade_count,
            "total_pnl_gross": round(self.total_pnl_gross, 8),
            "total_pnl_net": round(self.total_pnl_net, 8),
            "win_rate": round(self.win_rate, 4),
            "avg_skill_pct": round(self.avg_skill_pct, 4),
            "avg_luck_pct": round(self.avg_luck_pct, 4),
            "skill_consistency": round(self.skill_consistency, 4),
            "total_cost": round(self.total_cost, 8),
            "attribution_by_category": {
                k: round(v, 4) for k, v in self.attribution_by_category.items()
            },
        }


@dataclass
class StrategySkillRatio:
    """
    Long-term skill vs luck tracking for a strategy / 策略的长期 skill vs luck 追踪

    Attributes:
      strategy: str
      skill_level: SkillLevel (HIGH/MODERATE/LOW based on skill_pct)
      skill_pct: float (0.0-1.0, aggregate across all trades)
      luck_pct: float (0.0-1.0)
      total_trades: int
      trades_positive_skill: int (trades where skill_pct > 0.50)
      trades_negative_skill: int (trades where skill_pct < 0.40)
      confidence: float (0.0-1.0, based on sample size)
      last_updated: datetime
    """
    strategy: str
    skill_level: SkillLevel
    skill_pct: float
    luck_pct: float
    total_trades: int
    trades_positive_skill: int
    trades_negative_skill: int
    confidence: float
    last_updated: datetime.datetime

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict"""
        return {
            "strategy": self.strategy,
            "skill_level": self.skill_level.value,
            "skill_pct": round(self.skill_pct, 4),
            "luck_pct": round(self.luck_pct, 4),
            "total_trades": self.total_trades,
            "trades_positive_skill": self.trades_positive_skill,
            "trades_negative_skill": self.trades_negative_skill,
            "confidence": round(self.confidence, 4),
            "last_updated": self.last_updated.isoformat(),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Trade Attribution Engine / 交易归因引擎
# ═══════════════════════════════════════════════════════════════════════════════

class TradeAttributionEngine:
    """
    Decomposes completed trades into attribution factors.
    Thread-safe, supports serialization.
    """

    def __init__(self):
        """Initialize the attribution engine"""
        self._lock = threading.RLock()
        self._attribution_cache: Dict[str, TradeAttributionResult] = {}
        self._strategy_summaries: Dict[str, StrategyAttributionSummary] = {}
        self._strategy_skill_ratios: Dict[str, StrategySkillRatio] = {}

    # ─────────────────────────────────────────────────────────────────────────
    # Core Attribution Methods
    # ─────────────────────────────────────────────────────────────────────────

    def attribute_trade(
        self,
        trade_id: str,
        symbol: str,
        strategy: str,
        entry_price: float,
        exit_price: float,
        quantity: float,
        entry_timestamp: datetime.datetime,
        exit_timestamp: datetime.datetime,
        market_prices_at_entry: Dict[str, float],
        market_prices_at_exit: Dict[str, float],
        fees_paid: float = 0.0,
        slippage: float = 0.0,
        ai_cost: float = 0.0,
        expected_timing_pnl: Optional[float] = None,
        expected_sizing_volatility: Optional[float] = None,
        expected_execution_slippage: Optional[float] = None,
    ) -> TradeAttributionResult:
        """
        Decompose a completed trade into attribution factors.

        Args:
          trade_id: Unique trade identifier
          symbol: Trading symbol (e.g., "BTCUSDT")
          strategy: Strategy name
          entry_price: Entry price (average if multi-fill)
          exit_price: Exit price (average if multi-fill)
          quantity: Position size in base asset
          entry_timestamp: When entry completed
          exit_timestamp: When exit completed
          market_prices_at_entry: Dict of prices at entry (for regime/alternatives)
          market_prices_at_exit: Dict of prices at exit (for regime/alternatives)
          fees_paid: Total fees paid (in quote currency)
          slippage: Slippage from expected execution (in quote currency)
          ai_cost: AI decision cost (in quote currency or equivalent)
          expected_timing_pnl: Counterfactual PnL if entry/exit timing was median
          expected_sizing_volatility: Expected volatility at entry (for sizing evaluation)
          expected_execution_slippage: Expected slippage vs actual

        Returns:
          TradeAttributionResult with 6 attribution factors
        """
        with self._lock:
            # Calculate gross and net PnL
            gross_pnl = self._calculate_gross_pnl(entry_price, exit_price, quantity)
            total_cost = fees_paid + slippage + ai_cost
            net_pnl = gross_pnl - total_cost

            # Calculate individual attribution factors
            alpha_score = self._calculate_alpha_score(
                entry_price, exit_price, gross_pnl
            )
            timing_score = self._calculate_timing_score(
                entry_timestamp, exit_timestamp, gross_pnl, expected_timing_pnl
            )
            sizing_score = self._calculate_sizing_score(
                quantity, expected_sizing_volatility, gross_pnl
            )
            execution_score = self._calculate_execution_score(
                slippage, expected_execution_slippage, gross_pnl
            )
            cost_score = self._calculate_cost_score(
                fees_paid, total_cost, gross_pnl
            )

            # Calculate luck as residual
            luck_score = self._calculate_luck_score(
                gross_pnl,
                alpha_score,
                timing_score,
                sizing_score,
                execution_score,
                cost_score,
            )

            # Aggregate skill contributions
            skill_pct, luck_pct = self._aggregate_skill_luck(
                alpha_score,
                timing_score,
                sizing_score,
                execution_score,
                cost_score,
                luck_score,
            )

            # Normalize contribution percentages to sum to 1.0
            all_contributions = [
                alpha_score.contribution_pct,
                timing_score.contribution_pct,
                sizing_score.contribution_pct,
                execution_score.contribution_pct,
                cost_score.contribution_pct,
                luck_score.contribution_pct,
            ]
            total_contrib = sum(all_contributions)
            if total_contrib > 0.01:
                norm_factor = 1.0 / total_contrib
            else:
                norm_factor = 1.0 / 6  # Equal distribution if no contributions

            # Create attribution scores list with normalized contributions
            attribution_scores = [
                AttributionScore(
                    category=AttributionCategory.ALPHA,
                    score=alpha_score.score,
                    contribution_pct=alpha_score.contribution_pct * norm_factor,
                    explanation=alpha_score.explanation,
                ),
                AttributionScore(
                    category=AttributionCategory.TIMING,
                    score=timing_score.score,
                    contribution_pct=timing_score.contribution_pct * norm_factor,
                    explanation=timing_score.explanation,
                ),
                AttributionScore(
                    category=AttributionCategory.SIZING,
                    score=sizing_score.score,
                    contribution_pct=sizing_score.contribution_pct * norm_factor,
                    explanation=sizing_score.explanation,
                ),
                AttributionScore(
                    category=AttributionCategory.EXECUTION,
                    score=execution_score.score,
                    contribution_pct=execution_score.contribution_pct * norm_factor,
                    explanation=execution_score.explanation,
                ),
                AttributionScore(
                    category=AttributionCategory.COST,
                    score=cost_score.score,
                    contribution_pct=cost_score.contribution_pct * norm_factor,
                    explanation=cost_score.explanation,
                ),
                AttributionScore(
                    category=AttributionCategory.LUCK,
                    score=luck_score.score,
                    contribution_pct=luck_score.contribution_pct * norm_factor,
                    explanation=luck_score.explanation,
                ),
            ]

            result = TradeAttributionResult(
                trade_id=trade_id,
                symbol=symbol,
                strategy=strategy,
                pnl_gross=gross_pnl,
                pnl_net=net_pnl,
                attribution_scores=attribution_scores,
                skill_pct=skill_pct,
                luck_pct=luck_pct,
                total_cost=total_cost,
                timestamp=datetime.datetime.utcnow(),
            )

            # Cache result
            self._attribution_cache[trade_id] = result
            logger.info(
                f"Attributed trade {trade_id}: "
                f"PnL={net_pnl:.2f}, skill={skill_pct:.1%}, luck={luck_pct:.1%}"
            )

            return result

    # ─────────────────────────────────────────────────────────────────────────
    # Attribution Factor Calculations
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _calculate_gross_pnl(
        entry_price: float, exit_price: float, quantity: float
    ) -> float:
        """Calculate gross PnL without fees/slippage"""
        return (exit_price - entry_price) * quantity

    @staticmethod
    def _calculate_alpha_score(
        entry_price: float, exit_price: float, gross_pnl: float
    ) -> "AttributionComponent":
        """
        ALPHA: Was the direction correct? How much better than 50-50?
        Returns: score in [-1.0, 1.0] + contribution_pct
        """
        if gross_pnl == 0:
            # Exactly breakeven at entry price (rare)
            score = 0.0
            contribution_pct = 0.0
            explanation = "No directional P&L; entry price = exit price"
        elif gross_pnl > 0:
            # Profitable direction
            # score ranges from 0 (barely profitable) to 1.0 (strongly profitable)
            # Heuristic: use price change magnitude
            price_change_pct = abs(exit_price - entry_price) / entry_price
            # Map: 0.1% → 0.5, 1% → 0.85, 5% → 1.0
            score = min(1.0, price_change_pct / 0.05)
            contribution_pct = 1.0  # All positive PnL comes from getting direction right
            explanation = f"Correct direction: {price_change_pct:.2%} price move"
        else:
            # Loss: direction was wrong
            price_change_pct = abs(exit_price - entry_price) / entry_price
            score = -min(1.0, price_change_pct / 0.05)
            contribution_pct = 1.0  # All negative PnL from wrong direction
            explanation = f"Wrong direction: {price_change_pct:.2%} adverse move"

        return TradeAttributionEngine._AttributionComponent(
            score=score, contribution_pct=contribution_pct, explanation=explanation
        )

    @staticmethod
    def _calculate_timing_score(
        entry_ts: datetime.datetime,
        exit_ts: datetime.datetime,
        gross_pnl: float,
        expected_timing_pnl: Optional[float] = None,
    ) -> "AttributionComponent":
        """
        TIMING: Did entry/exit timing improve P&L vs random/median timing?
        Compares actual PnL to expected PnL if timing was "average" (median).
        """
        holding_minutes = (exit_ts - entry_ts).total_seconds() / 60.0

        if expected_timing_pnl is None or expected_timing_pnl == 0:
            # No counterfactual; assume timing was neutral
            score = 0.0
            contribution_pct = 0.0
            explanation = f"No timing counterfactual; held {holding_minutes:.0f}min"
        else:
            # Compare actual to expected
            timing_improvement = gross_pnl - expected_timing_pnl
            if abs(expected_timing_pnl) < 0.01:  # Avoid division by very small numbers
                score = min(1.0, max(-1.0, timing_improvement / 0.01))
            else:
                score = min(1.0, max(-1.0, timing_improvement / expected_timing_pnl))
            contribution_pct = abs(timing_improvement) / (abs(gross_pnl) + 0.001)
            explanation = (
                f"Timing: actual PnL {gross_pnl:.2f} vs expected {expected_timing_pnl:.2f}"
            )

        return TradeAttributionEngine._AttributionComponent(
            score=score, contribution_pct=contribution_pct, explanation=explanation
        )

    @staticmethod
    def _calculate_sizing_score(
        quantity: float,
        expected_volatility: Optional[float] = None,
        gross_pnl: float = 0.0,
    ) -> "AttributionComponent":
        """
        SIZING: Was position size appropriate given volatility?
        Larger sizes in lower volatility = better sizing.
        """
        if expected_volatility is None or expected_volatility < 0.0001:
            # No volatility data; assume sizing was neutral
            score = 0.0
            contribution_pct = 0.0
            explanation = "No volatility data; sizing assessment neutral"
        else:
            # Heuristic: size/volatility ratio should be in [0.5, 2.0] for good sizing
            # Outside = poor sizing
            ratio = quantity / expected_volatility if expected_volatility > 0 else 1.0

            if 0.5 <= ratio <= 2.0:
                # Good range
                score = 0.5 + (1.0 - abs(ratio - 1.0)) * 0.5  # Peak at ratio=1.0
                contribution_pct = 0.3 if gross_pnl > 0 else 0.1  # Sizing less important than direction
            else:
                # Over/undersized
                score = -min(1.0, abs(ratio - 1.0) / 2.0)
                contribution_pct = 0.2

            explanation = f"Size/vol ratio {ratio:.2f}; expected vol {expected_volatility:.4f}"

        return TradeAttributionEngine._AttributionComponent(
            score=score, contribution_pct=contribution_pct, explanation=explanation
        )

    @staticmethod
    def _calculate_execution_score(
        actual_slippage: float,
        expected_slippage: Optional[float] = None,
        gross_pnl: float = 0.0,
    ) -> "AttributionComponent":
        """
        EXECUTION: Fill quality (slippage vs expected).
        Negative slippage is good (we got better fills).
        """
        if expected_slippage is None:
            expected_slippage = 0.0

        slippage_improvement = expected_slippage - actual_slippage

        if abs(slippage_improvement) < 0.0001:
            score = 0.0
            contribution_pct = 0.0
            explanation = "Slippage as expected"
        else:
            # Better than expected slippage = positive score
            # Worse than expected = negative score
            # Heuristic: slippage impact is typically 10-30% of PnL
            if abs(gross_pnl) > 0.01:
                score = min(1.0, max(-1.0, slippage_improvement / abs(gross_pnl)))
                contribution_pct = abs(slippage_improvement) / (abs(gross_pnl) + 0.001)
            else:
                # When no expected slippage given, treat actual slippage as neutral
                if expected_slippage == 0.0:
                    score = 0.0  # Neutral, not negative
                else:
                    score = 0.5 if slippage_improvement > 0 else -0.5
                contribution_pct = 0.0

            explanation = (
                f"Slippage: actual {actual_slippage:.4f} vs expected {expected_slippage:.4f}"
            )

        return TradeAttributionEngine._AttributionComponent(
            score=score, contribution_pct=contribution_pct, explanation=explanation
        )

    @staticmethod
    def _calculate_cost_score(
        fees_paid: float, total_cost: float, gross_pnl: float = 0.0
    ) -> "AttributionComponent":
        """
        COST: Fee optimization (maker vs taker, VIP level, etc).
        Negative cost is good; high cost is bad.
        Score reflects whether costs were minimized.
        """
        if total_cost <= 0.0:
            score = 1.0
            contribution_pct = 0.0
            explanation = "Zero or negative total cost (rebates/credits)"
        else:
            # Cost is a drag; ideally we want to minimize it
            if abs(gross_pnl) > 0.01:
                cost_drag = total_cost / abs(gross_pnl)
                # Heuristic: cost < 5% of PnL = good, > 20% = bad
                if cost_drag < 0.05:
                    # Excellent: 0.8 to 1.0
                    score = 0.8 + 0.2 * (1.0 - cost_drag / 0.05)
                elif cost_drag > 0.20:
                    # Bad: negative
                    score = -0.8 - 0.2 * min(1.0, (cost_drag - 0.20) / 0.20)
                else:
                    # Medium: linear decline from 0.8 to -0.8
                    # When cost_drag = 0.05: score = 0.8
                    # When cost_drag = 0.20: score = -0.8
                    score = 0.8 - ((cost_drag - 0.05) / 0.15) * 1.6
                contribution_pct = cost_drag
            else:
                # Small gross PnL; cost matters more
                score = -1.0 if total_cost > 0.001 else 0.0
                contribution_pct = 1.0

            explanation = f"Total cost {total_cost:.4f}; fees {fees_paid:.4f}"

        return TradeAttributionEngine._AttributionComponent(
            score=score, contribution_pct=contribution_pct, explanation=explanation
        )

    @staticmethod
    def _calculate_luck_score(
        gross_pnl: float,
        alpha: "AttributionComponent",
        timing: "AttributionComponent",
        sizing: "AttributionComponent",
        execution: "AttributionComponent",
        cost: "AttributionComponent",
    ) -> "AttributionComponent":
        """
        LUCK: Residual unexplained component.
        Calculated as the component not explained by other factors.
        """
        # Sum up explained contribution percentages
        explained_contrib = (
            alpha.contribution_pct
            + timing.contribution_pct
            + sizing.contribution_pct
            + execution.contribution_pct
            + cost.contribution_pct
        )

        luck_contrib = max(0.0, 1.0 - explained_contrib)

        if luck_contrib > 0.5:
            score = 0.5 if gross_pnl > 0 else -0.5
        else:
            score = 0.0

        explanation = f"Unexplained {luck_contrib:.1%} of PnL variability"

        return TradeAttributionEngine._AttributionComponent(
            score=score, contribution_pct=luck_contrib, explanation=explanation
        )

    @staticmethod
    def _aggregate_skill_luck(
        alpha: "AttributionComponent",
        timing: "AttributionComponent",
        sizing: "AttributionComponent",
        execution: "AttributionComponent",
        cost: "AttributionComponent",
        luck: "AttributionComponent",
    ) -> tuple[float, float]:
        """
        Aggregate skill and luck percentages.
        skill_pct = sum of alpha, timing, sizing, execution, cost contributions (normalized)
        luck_pct = luck contribution
        """
        skill_contrib = (
            alpha.contribution_pct
            + timing.contribution_pct
            + sizing.contribution_pct
            + execution.contribution_pct
            + cost.contribution_pct
        )
        total_contrib = skill_contrib + luck.contribution_pct

        if total_contrib > 0.01:
            skill_pct = skill_contrib / total_contrib
            luck_pct = luck.contribution_pct / total_contrib
        else:
            # Very small PnL; default to 50-50
            skill_pct = 0.5
            luck_pct = 0.5

        return skill_pct, luck_pct

    # ─────────────────────────────────────────────────────────────────────────
    # Aggregation Methods
    # ─────────────────────────────────────────────────────────────────────────

    def aggregate_attribution(
        self,
        strategy: str,
        period_start: datetime.datetime,
        period_end: datetime.datetime,
    ) -> Optional[StrategyAttributionSummary]:
        """
        Aggregate attribution across all trades for a strategy in a time period.

        Returns:
          StrategyAttributionSummary with aggregated metrics, or None if no trades.
        """
        with self._lock:
            # Filter trades for this strategy in the time period
            trades = [
                attr
                for attr in self._attribution_cache.values()
                if attr.strategy == strategy
                and period_start <= attr.timestamp <= period_end
            ]

            if not trades:
                return None

            # Calculate aggregates
            total_pnl_gross = sum(t.pnl_gross for t in trades)
            total_pnl_net = sum(t.pnl_net for t in trades)
            win_count = sum(1 for t in trades if t.pnl_net > 0.0)
            win_rate = win_count / len(trades) if trades else 0.0

            avg_skill_pct = sum(t.skill_pct for t in trades) / len(trades)
            avg_luck_pct = sum(t.luck_pct for t in trades) / len(trades)

            # Calculate skill consistency (lower std dev = more consistent)
            if len(trades) > 1:
                mean_skill = avg_skill_pct
                variance = sum((t.skill_pct - mean_skill) ** 2 for t in trades) / len(trades)
                skill_consistency = variance ** 0.5
            else:
                skill_consistency = 0.0

            total_cost = sum(t.total_cost for t in trades)

            # Attribution by category: average contribution across all trades
            attribution_by_category: Dict[str, float] = {}
            for category in AttributionCategory:
                contributions = []
                for trade in trades:
                    score_for_cat = next(
                        (s for s in trade.attribution_scores if s.category == category),
                        None,
                    )
                    if score_for_cat:
                        contributions.append(score_for_cat.contribution_pct)

                if contributions:
                    attribution_by_category[category.value] = sum(contributions) / len(
                        contributions
                    )
                else:
                    attribution_by_category[category.value] = 0.0

            summary = StrategyAttributionSummary(
                strategy=strategy,
                period_start=period_start,
                period_end=period_end,
                trade_count=len(trades),
                total_pnl_gross=total_pnl_gross,
                total_pnl_net=total_pnl_net,
                win_rate=win_rate,
                avg_skill_pct=avg_skill_pct,
                avg_luck_pct=avg_luck_pct,
                skill_consistency=skill_consistency,
                total_cost=total_cost,
                attribution_by_category=attribution_by_category,
            )

            self._strategy_summaries[strategy] = summary
            logger.info(
                f"Aggregated {strategy}: {len(trades)} trades, "
                f"net PnL={total_pnl_net:.2f}, avg skill={avg_skill_pct:.1%}"
            )

            return summary

    def get_strategy_skill_ratio(self, strategy: str) -> Optional[StrategySkillRatio]:
        """
        Get long-term skill vs luck tracking for a strategy.

        Returns:
          StrategySkillRatio with high-level classification, or None if no trades.
        """
        with self._lock:
            trades = [
                attr
                for attr in self._attribution_cache.values()
                if attr.strategy == strategy
            ]

            if not trades:
                return None

            # Calculate aggregates
            avg_skill_pct = sum(t.skill_pct for t in trades) / len(trades)
            avg_luck_pct = sum(t.luck_pct for t in trades) / len(trades)

            # Classify skill level
            if avg_skill_pct > 0.70:
                skill_level = SkillLevel.HIGH_SKILL
            elif avg_skill_pct >= 0.40:
                skill_level = SkillLevel.MODERATE_SKILL
            else:
                skill_level = SkillLevel.LOW_SKILL

            # Count trades by skill level
            trades_positive_skill = sum(
                1 for t in trades if t.skill_pct > 0.50
            )
            trades_negative_skill = sum(
                1 for t in trades if t.skill_pct < 0.40
            )

            # Confidence based on sample size (higher = more confident)
            # Heuristic: 30+ trades = 90%, 100+ = 95%, <10 = 50%
            trade_count = len(trades)
            if trade_count >= 100:
                confidence = 0.95
            elif trade_count >= 30:
                confidence = 0.90
            elif trade_count >= 10:
                confidence = 0.70
            else:
                confidence = 0.50

            ratio = StrategySkillRatio(
                strategy=strategy,
                skill_level=skill_level,
                skill_pct=avg_skill_pct,
                luck_pct=avg_luck_pct,
                total_trades=trade_count,
                trades_positive_skill=trades_positive_skill,
                trades_negative_skill=trades_negative_skill,
                confidence=confidence,
                last_updated=datetime.datetime.utcnow(),
            )

            self._strategy_skill_ratios[strategy] = ratio
            logger.info(
                f"Strategy {strategy}: skill_level={skill_level.value}, "
                f"skill_pct={avg_skill_pct:.1%}, confidence={confidence:.0%}"
            )

            return ratio

    # ─────────────────────────────────────────────────────────────────────────
    # Utility Methods
    # ─────────────────────────────────────────────────────────────────────────

    def get_trade_attribution(self, trade_id: str) -> Optional[TradeAttributionResult]:
        """Retrieve cached attribution for a trade"""
        with self._lock:
            return self._attribution_cache.get(trade_id)

    def list_strategy_summaries(self) -> Dict[str, StrategyAttributionSummary]:
        """Get all strategy attribution summaries"""
        with self._lock:
            return dict(self._strategy_summaries)

    def list_strategy_skill_ratios(self) -> Dict[str, StrategySkillRatio]:
        """Get all strategy skill ratios"""
        with self._lock:
            return dict(self._strategy_skill_ratios)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize engine state to dict"""
        with self._lock:
            return {
                "attribution_cache": {
                    k: v.to_dict() for k, v in self._attribution_cache.items()
                },
                "strategy_summaries": {
                    k: v.to_dict() for k, v in self._strategy_summaries.items()
                },
                "strategy_skill_ratios": {
                    k: v.to_dict() for k, v in self._strategy_skill_ratios.items()
                },
            }

    def from_dict(self, data: Dict[str, Any]) -> None:
        """Deserialize engine state from dict"""
        with self._lock:
            if "attribution_cache" in data:
                self._attribution_cache = {
                    k: TradeAttributionResult.from_dict(v)
                    for k, v in data["attribution_cache"].items()
                }
            if "strategy_summaries" in data:
                # Note: StrategyAttributionSummary doesn't have from_dict yet
                # This is intentional — summaries are computed, not restored
                pass
            if "strategy_skill_ratios" in data:
                # Same for skill ratios
                pass

    # ─────────────────────────────────────────────────────────────────────────
    # Internal Helper Class
    # ─────────────────────────────────────────────────────────────────────────

    @dataclass
    class _AttributionComponent:
        """Internal helper for attribution factor calculation"""
        score: float  # -1.0 to 1.0
        contribution_pct: float  # 0.0 to 1.0
        explanation: str
