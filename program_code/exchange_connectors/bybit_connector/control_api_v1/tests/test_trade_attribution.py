"""
Tests for Trade Attribution Engine / 交易归因引擎测试

覆盖范围 / Coverage:
  - AttributionCategory, SkillLevel enums
  - AttributionScore dataclass (serialization)
  - TradeAttributionResult dataclass (serialization, validation)
  - StrategyAttributionSummary dataclass
  - StrategySkillRatio dataclass
  - TradeAttributionEngine:
    * attribute_trade(): single trade decomposition
    * Alpha score calculation (directional correctness)
    * Timing score calculation (entry/exit timing)
    * Sizing score calculation (position sizing vs volatility)
    * Execution score calculation (fill quality)
    * Cost score calculation (fee optimization)
    * Luck score calculation (residual)
    * Skill vs luck aggregation
    * aggregate_attribution(): strategy-level summaries
    * get_strategy_skill_ratio(): long-term tracking
    * Thread safety (concurrent operations)
    * Serialization (to_dict, from_dict)
"""

import datetime
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.trade_attribution import (
    AttributionCategory,
    SkillLevel,
    AttributionScore,
    TradeAttributionResult,
    StrategyAttributionSummary,
    StrategySkillRatio,
    TradeAttributionEngine,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def engine():
    """Create a fresh attribution engine for each test"""
    return TradeAttributionEngine()


@pytest.fixture
def now():
    """Standard timestamp for tests"""
    return datetime.datetime(2026, 3, 29, 12, 0, 0)


# ═══════════════════════════════════════════════════════════════════════════════
# Test AttributionScore / 归因分数测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestAttributionScore:
    """Tests for AttributionScore dataclass"""

    def test_attribution_score_creation(self):
        """Create AttributionScore with valid data"""
        score = AttributionScore(
            category=AttributionCategory.ALPHA,
            score=0.75,
            contribution_pct=0.5,
            explanation="Direction was correct",
        )
        assert score.category == AttributionCategory.ALPHA
        assert score.score == 0.75
        assert score.contribution_pct == 0.5
        assert score.explanation == "Direction was correct"

    def test_attribution_score_serialization(self):
        """Serialize and deserialize AttributionScore"""
        original = AttributionScore(
            category=AttributionCategory.TIMING,
            score=-0.2,
            contribution_pct=0.15,
            explanation="Timing was suboptimal",
        )
        d = original.to_dict()
        restored = AttributionScore.from_dict(d)

        assert restored.category == original.category
        assert restored.score == original.score
        assert restored.contribution_pct == original.contribution_pct
        assert restored.explanation == original.explanation

    def test_attribution_score_bounds(self):
        """Test score bounds (-1.0 to 1.0)"""
        # Negative score
        score = AttributionScore(
            category=AttributionCategory.LUCK,
            score=-1.0,
            contribution_pct=0.3,
            explanation="Bad luck",
        )
        assert score.score == -1.0

        # Positive score
        score = AttributionScore(
            category=AttributionCategory.EXECUTION,
            score=1.0,
            contribution_pct=0.2,
            explanation="Great execution",
        )
        assert score.score == 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# Test TradeAttributionResult / 交易归因结果测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestTradeAttributionResult:
    """Tests for TradeAttributionResult dataclass"""

    def test_trade_attribution_result_creation(self, now):
        """Create TradeAttributionResult with all 6 attribution scores"""
        scores = [
            AttributionScore(
                category=AttributionCategory.ALPHA,
                score=0.8,
                contribution_pct=0.4,
                explanation="Good direction",
            ),
            AttributionScore(
                category=AttributionCategory.TIMING,
                score=0.2,
                contribution_pct=0.1,
                explanation="Average timing",
            ),
            AttributionScore(
                category=AttributionCategory.SIZING,
                score=0.0,
                contribution_pct=0.0,
                explanation="Neutral sizing",
            ),
            AttributionScore(
                category=AttributionCategory.EXECUTION,
                score=0.3,
                contribution_pct=0.1,
                explanation="Good fills",
            ),
            AttributionScore(
                category=AttributionCategory.COST,
                score=-0.1,
                contribution_pct=0.1,
                explanation="Fees were high",
            ),
            AttributionScore(
                category=AttributionCategory.LUCK,
                score=0.0,
                contribution_pct=0.2,
                explanation="Unexplained component",
            ),
        ]

        result = TradeAttributionResult(
            trade_id="trade_123",
            symbol="BTCUSDT",
            strategy="MA_CROSSOVER",
            pnl_gross=100.0,
            pnl_net=85.0,
            attribution_scores=scores,
            skill_pct=0.8,
            luck_pct=0.2,
            total_cost=15.0,
            timestamp=now,
        )

        assert result.trade_id == "trade_123"
        assert result.symbol == "BTCUSDT"
        assert result.pnl_net == 85.0
        assert result.skill_pct == 0.8
        assert len(result.attribution_scores) == 6

    def test_trade_attribution_result_validation_missing_category(self, now):
        """Validation should fail if not all 6 categories present"""
        scores = [
            AttributionScore(
                category=AttributionCategory.ALPHA,
                score=0.8,
                contribution_pct=0.5,
                explanation="Test",
            ),
            # Missing TIMING, SIZING, EXECUTION, COST, LUCK
        ]

        with pytest.raises(ValueError, match="must contain all categories"):
            TradeAttributionResult(
                trade_id="trade_123",
                symbol="BTCUSDT",
                strategy="test",
                pnl_gross=100.0,
                pnl_net=85.0,
                attribution_scores=scores,
                skill_pct=0.8,
                luck_pct=0.2,
                total_cost=15.0,
                timestamp=now,
            )

    def test_trade_attribution_result_serialization(self, now):
        """Serialize and deserialize TradeAttributionResult"""
        scores = [
            AttributionScore(
                category=cat,
                score=0.5,
                contribution_pct=0.15,
                explanation=f"Score for {cat.value}",
            )
            for cat in AttributionCategory
        ]

        original = TradeAttributionResult(
            trade_id="trade_456",
            symbol="ETHUSDT",
            strategy="GRID",
            pnl_gross=50.0,
            pnl_net=40.0,
            attribution_scores=scores,
            skill_pct=0.6,
            luck_pct=0.4,
            total_cost=10.0,
            timestamp=now,
        )

        d = original.to_dict()
        restored = TradeAttributionResult.from_dict(d)

        assert restored.trade_id == original.trade_id
        assert restored.symbol == original.symbol
        assert restored.pnl_net == original.pnl_net
        assert len(restored.attribution_scores) == 6

    def test_trade_attribution_result_timestamp_validation(self):
        """Timestamp must be datetime, not string"""
        scores = [
            AttributionScore(
                category=cat,
                score=0.5,
                contribution_pct=0.15,
                explanation="test",
            )
            for cat in AttributionCategory
        ]

        with pytest.raises(ValueError, match="must be datetime"):
            TradeAttributionResult(
                trade_id="trade_123",
                symbol="BTCUSDT",
                strategy="test",
                pnl_gross=100.0,
                pnl_net=85.0,
                attribution_scores=scores,
                skill_pct=0.8,
                luck_pct=0.2,
                total_cost=15.0,
                timestamp="2026-03-29T12:00:00",  # String, not datetime
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Test TradeAttributionEngine / 交易归因引擎测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestTradeAttributionEngine:
    """Tests for the core attribution engine"""

    def test_engine_initialization(self, engine):
        """Engine should initialize with empty state"""
        assert engine is not None
        assert engine._attribution_cache == {}
        assert engine._strategy_summaries == {}
        assert engine._strategy_skill_ratios == {}

    def test_attribute_profitable_trade(self, engine, now):
        """Test attribution of a profitable trade"""
        entry_ts = now
        exit_ts = now + datetime.timedelta(hours=1)

        result = engine.attribute_trade(
            trade_id="trade_profit_1",
            symbol="BTCUSDT",
            strategy="MA_CROSSOVER",
            entry_price=40000.0,
            exit_price=41000.0,
            quantity=1.0,
            entry_timestamp=entry_ts,
            exit_timestamp=exit_ts,
            market_prices_at_entry={"BTCUSDT": 40000.0},
            market_prices_at_exit={"BTCUSDT": 41000.0},
            fees_paid=10.0,
            slippage=5.0,
            ai_cost=0.0,
            expected_timing_pnl=500.0,
            expected_sizing_volatility=0.02,
            expected_execution_slippage=10.0,
        )

        assert result.trade_id == "trade_profit_1"
        assert result.pnl_gross == 1000.0  # (41000 - 40000) * 1
        assert result.pnl_net == 985.0  # 1000 - 15 costs
        assert result.total_cost == 15.0
        # Should have high skill_pct for profitable trade
        assert result.skill_pct > 0.5
        assert result.luck_pct < 0.5

    def test_attribute_loss_trade(self, engine, now):
        """Test attribution of a losing trade"""
        entry_ts = now
        exit_ts = now + datetime.timedelta(hours=1)

        result = engine.attribute_trade(
            trade_id="trade_loss_1",
            symbol="ETHUSDT",
            strategy="GRID",
            entry_price=2000.0,
            exit_price=1900.0,
            quantity=1.0,
            entry_timestamp=entry_ts,
            exit_timestamp=exit_ts,
            market_prices_at_entry={"ETHUSDT": 2000.0},
            market_prices_at_exit={"ETHUSDT": 1900.0},
            fees_paid=5.0,
            slippage=0.0,
            ai_cost=0.0,
            expected_timing_pnl=-50.0,
            expected_sizing_volatility=0.015,
        )

        assert result.pnl_gross == -100.0
        assert result.pnl_net == -105.0
        # Alpha score should be negative for wrong direction
        alpha_score = next(
            s for s in result.attribution_scores if s.category == AttributionCategory.ALPHA
        )
        assert alpha_score.score < 0

    def test_alpha_score_calculation(self, engine):
        """Test ALPHA score: directional correctness"""
        # Test positive direction
        alpha = engine._calculate_alpha_score(
            entry_price=100.0,
            exit_price=105.0,
            gross_pnl=5.0,
        )
        assert alpha.score > 0  # Correct direction
        assert alpha.contribution_pct == 1.0  # All PnL from direction

        # Test negative direction
        alpha = engine._calculate_alpha_score(
            entry_price=100.0,
            exit_price=95.0,
            gross_pnl=-5.0,
        )
        assert alpha.score < 0  # Wrong direction
        assert alpha.contribution_pct == 1.0

        # Test zero PnL
        alpha = engine._calculate_alpha_score(
            entry_price=100.0,
            exit_price=100.0,
            gross_pnl=0.0,
        )
        assert alpha.score == 0.0

    def test_timing_score_calculation(self, engine, now):
        """Test TIMING score: entry/exit timing quality"""
        # Good timing (actual > expected)
        timing = engine._calculate_timing_score(
            entry_ts=now,
            exit_ts=now + datetime.timedelta(hours=1),
            gross_pnl=1000.0,
            expected_timing_pnl=500.0,
        )
        assert timing.score > 0  # Better than expected

        # Bad timing (actual < expected)
        timing = engine._calculate_timing_score(
            entry_ts=now,
            exit_ts=now + datetime.timedelta(hours=1),
            gross_pnl=100.0,
            expected_timing_pnl=500.0,
        )
        assert timing.score < 0  # Worse than expected

        # No counterfactual
        timing = engine._calculate_timing_score(
            entry_ts=now,
            exit_ts=now + datetime.timedelta(hours=1),
            gross_pnl=500.0,
            expected_timing_pnl=None,
        )
        assert timing.score == 0.0

    def test_sizing_score_calculation(self, engine):
        """Test SIZING score: position sizing vs volatility"""
        # Good sizing (ratio close to 1.0)
        sizing = engine._calculate_sizing_score(
            quantity=10.0,
            expected_volatility=10.0,
            gross_pnl=100.0,
        )
        assert sizing.score > 0  # Good sizing ratio

        # Oversized
        sizing = engine._calculate_sizing_score(
            quantity=50.0,
            expected_volatility=10.0,
            gross_pnl=100.0,
        )
        assert sizing.score < 0  # Bad ratio

        # No volatility data
        sizing = engine._calculate_sizing_score(
            quantity=10.0,
            expected_volatility=None,
            gross_pnl=100.0,
        )
        assert sizing.score == 0.0

    def test_execution_score_calculation(self, engine):
        """Test EXECUTION score: fill quality and slippage"""
        # Better than expected slippage
        execution = engine._calculate_execution_score(
            actual_slippage=5.0,
            expected_slippage=10.0,
            gross_pnl=100.0,
        )
        assert execution.score > 0  # Good execution

        # Worse than expected slippage
        execution = engine._calculate_execution_score(
            actual_slippage=15.0,
            expected_slippage=10.0,
            gross_pnl=100.0,
        )
        assert execution.score < 0  # Bad execution

        # No expected slippage but has actual slippage
        # This is treated as a cost since there was no expectation to beat
        execution = engine._calculate_execution_score(
            actual_slippage=5.0,
            expected_slippage=None,
            gross_pnl=100.0,
        )
        # With default expected_slippage=0.0, actual slippage will be scored as negative
        assert execution.score < 0 or execution.score == 0.0

    def test_cost_score_calculation(self, engine):
        """Test COST score: fee optimization"""
        # Low fees relative to PnL
        cost = engine._calculate_cost_score(
            fees_paid=5.0,
            total_cost=5.0,
            gross_pnl=100.0,
        )
        assert cost.score > 0.5  # Good cost management

        # High fees relative to PnL
        cost = engine._calculate_cost_score(
            fees_paid=30.0,
            total_cost=30.0,
            gross_pnl=100.0,
        )
        assert cost.score < 0  # Poor cost management

        # Zero cost
        cost = engine._calculate_cost_score(
            fees_paid=0.0,
            total_cost=0.0,
            gross_pnl=100.0,
        )
        assert cost.score == 1.0  # Perfect

    def test_luck_score_calculation(self, engine):
        """Test LUCK score: residual unexplained component"""
        alpha = engine._AttributionComponent(score=0.8, contribution_pct=0.4, explanation="")
        timing = engine._AttributionComponent(score=0.2, contribution_pct=0.3, explanation="")
        sizing = engine._AttributionComponent(score=0.0, contribution_pct=0.0, explanation="")
        execution = engine._AttributionComponent(score=0.5, contribution_pct=0.2, explanation="")
        cost = engine._AttributionComponent(score=-0.1, contribution_pct=0.0, explanation="")

        luck = engine._calculate_luck_score(100.0, alpha, timing, sizing, execution, cost)
        assert luck.contribution_pct > 0  # Unexplained remainder
        assert luck.contribution_pct <= 1.0

    def test_skill_luck_aggregation(self, engine):
        """Test aggregation of skill vs luck percentages"""
        alpha = engine._AttributionComponent(score=0.8, contribution_pct=0.4, explanation="")
        timing = engine._AttributionComponent(score=0.2, contribution_pct=0.3, explanation="")
        sizing = engine._AttributionComponent(score=0.0, contribution_pct=0.0, explanation="")
        execution = engine._AttributionComponent(score=0.5, contribution_pct=0.2, explanation="")
        cost = engine._AttributionComponent(score=-0.1, contribution_pct=0.0, explanation="")
        luck = engine._AttributionComponent(score=0.0, contribution_pct=0.1, explanation="")

        skill_pct, luck_pct = engine._aggregate_skill_luck(
            alpha, timing, sizing, execution, cost, luck
        )

        assert skill_pct + luck_pct == pytest.approx(1.0, abs=0.01)
        assert 0.0 <= skill_pct <= 1.0
        assert 0.0 <= luck_pct <= 1.0

    def test_cache_retrieved_trade(self, engine, now):
        """Attributed trade should be cached and retrievable"""
        entry_ts = now
        exit_ts = now + datetime.timedelta(minutes=30)

        # Attribute a trade
        result = engine.attribute_trade(
            trade_id="trade_cache_1",
            symbol="BTCUSDT",
            strategy="test",
            entry_price=100.0,
            exit_price=110.0,
            quantity=1.0,
            entry_timestamp=entry_ts,
            exit_timestamp=exit_ts,
            market_prices_at_entry={"BTCUSDT": 100.0},
            market_prices_at_exit={"BTCUSDT": 110.0},
        )

        # Retrieve from cache
        cached = engine.get_trade_attribution("trade_cache_1")
        assert cached is not None
        assert cached.trade_id == result.trade_id
        assert cached.pnl_gross == result.pnl_gross

        # Non-existent trade
        assert engine.get_trade_attribution("nonexistent") is None

    def test_aggregate_attribution_single_strategy(self, engine, now):
        """Aggregate attribution for a single strategy across multiple trades"""
        # Attribute 3 trades
        for i in range(3):
            engine.attribute_trade(
                trade_id=f"trade_agg_{i}",
                symbol="BTCUSDT",
                strategy="MA_CROSSOVER",
                entry_price=40000.0 + (i * 100),
                exit_price=41000.0 + (i * 100),
                quantity=1.0,
                entry_timestamp=now + datetime.timedelta(hours=i),
                exit_timestamp=now + datetime.timedelta(hours=i + 1),
                market_prices_at_entry={},
                market_prices_at_exit={},
                fees_paid=10.0,
            )

        # Aggregate
        period_start = now
        period_end = now + datetime.timedelta(days=1)
        summary = engine.aggregate_attribution(
            strategy="MA_CROSSOVER",
            period_start=period_start,
            period_end=period_end,
        )

        assert summary is not None
        assert summary.strategy == "MA_CROSSOVER"
        assert summary.trade_count == 3
        assert summary.total_pnl_gross > 0  # All 3 trades were profitable
        assert summary.win_rate == 1.0  # 3/3 positive

    def test_aggregate_attribution_no_trades(self, engine, now):
        """Aggregate should return None if no trades in period"""
        summary = engine.aggregate_attribution(
            strategy="NONEXISTENT",
            period_start=now,
            period_end=now + datetime.timedelta(days=1),
        )
        assert summary is None

    def test_get_strategy_skill_ratio(self, engine, now):
        """Get long-term skill vs luck ratio for a strategy"""
        # Attribute several trades
        for i in range(10):
            engine.attribute_trade(
                trade_id=f"trade_skill_{i}",
                symbol="BTCUSDT",
                strategy="GRID",
                entry_price=40000.0,
                exit_price=40000.0 + (i * 100),  # Varying profitability
                quantity=1.0,
                entry_timestamp=now + datetime.timedelta(hours=i),
                exit_timestamp=now + datetime.timedelta(hours=i + 1),
                market_prices_at_entry={},
                market_prices_at_exit={},
            )

        # Get skill ratio
        ratio = engine.get_strategy_skill_ratio("GRID")
        assert ratio is not None
        assert ratio.strategy == "GRID"
        assert ratio.total_trades == 10
        assert ratio.skill_pct + ratio.luck_pct == pytest.approx(1.0, abs=0.01)
        assert ratio.skill_level in [
            SkillLevel.HIGH_SKILL,
            SkillLevel.MODERATE_SKILL,
            SkillLevel.LOW_SKILL,
        ]
        # With 10 trades, confidence should be > 50%
        assert ratio.confidence > 0.5

    def test_get_strategy_skill_ratio_classifications(self, engine, now):
        """Skill level should classify correctly"""
        # Create a highly profitable strategy (high skill)
        for i in range(5):
            engine.attribute_trade(
                trade_id=f"trade_high_{i}",
                symbol="BTCUSDT",
                strategy="HIGH_SKILL",
                entry_price=100.0,
                exit_price=150.0,  # Always very profitable
                quantity=1.0,
                entry_timestamp=now + datetime.timedelta(hours=i),
                exit_timestamp=now + datetime.timedelta(hours=i + 1),
                market_prices_at_entry={},
                market_prices_at_exit={},
            )

        ratio = engine.get_strategy_skill_ratio("HIGH_SKILL")
        # High profitability should result in high skill_pct
        assert ratio.skill_pct > 0.4  # At least moderate
        assert ratio.skill_level in [
            SkillLevel.MODERATE_SKILL,
            SkillLevel.HIGH_SKILL,
        ]

    def test_serialization_to_from_dict(self, engine, now):
        """Serialize and deserialize engine state"""
        # Attribute a trade
        engine.attribute_trade(
            trade_id="trade_ser_1",
            symbol="BTCUSDT",
            strategy="test",
            entry_price=100.0,
            exit_price=110.0,
            quantity=1.0,
            entry_timestamp=now,
            exit_timestamp=now + datetime.timedelta(hours=1),
            market_prices_at_entry={},
            market_prices_at_exit={},
        )

        # Serialize
        state_dict = engine.to_dict()
        assert "attribution_cache" in state_dict
        assert "trade_ser_1" in state_dict["attribution_cache"]

        # Deserialize to new engine
        new_engine = TradeAttributionEngine()
        new_engine.from_dict(state_dict)

        # Verify restored trade
        restored = new_engine.get_trade_attribution("trade_ser_1")
        assert restored is not None
        assert restored.pnl_gross == 10.0

    def test_thread_safety(self, engine, now):
        """Engine should handle concurrent trade attribution"""
        import queue

        results_queue: queue.Queue = queue.Queue()
        errors_queue: queue.Queue = queue.Queue()

        def attribute_trades(thread_id):
            try:
                for i in range(5):
                    result = engine.attribute_trade(
                        trade_id=f"trade_thread_{thread_id}_{i}",
                        symbol="BTCUSDT",
                        strategy=f"strategy_{thread_id}",
                        entry_price=40000.0 + i * 10,
                        exit_price=41000.0 + i * 10,
                        quantity=1.0,
                        entry_timestamp=now + datetime.timedelta(seconds=i),
                        exit_timestamp=now + datetime.timedelta(seconds=i + 1),
                        market_prices_at_entry={},
                        market_prices_at_exit={},
                    )
                    results_queue.put(result)
            except Exception as e:
                errors_queue.put(e)

        # Launch threads
        threads = [
            threading.Thread(target=attribute_trades, args=(i,)) for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify no errors
        assert errors_queue.empty(), f"Errors: {list(errors_queue.queue)}"

        # Verify all trades were recorded
        assert results_queue.qsize() == 25  # 5 threads * 5 trades
        assert len(engine._attribution_cache) == 25

    def test_attribution_categories_all_present(self, engine, now):
        """Every trade attribution should have all 6 categories"""
        result = engine.attribute_trade(
            trade_id="trade_all_cat",
            symbol="BTCUSDT",
            strategy="test",
            entry_price=100.0,
            exit_price=110.0,
            quantity=1.0,
            entry_timestamp=now,
            exit_timestamp=now + datetime.timedelta(hours=1),
            market_prices_at_entry={},
            market_prices_at_exit={},
        )

        categories = {s.category for s in result.attribution_scores}
        assert len(categories) == 6
        assert categories == set(AttributionCategory)

    def test_contribution_percentages_sum_reasonable(self, engine, now):
        """Contribution percentages should sum to a reasonable total"""
        result = engine.attribute_trade(
            trade_id="trade_contrib",
            symbol="BTCUSDT",
            strategy="test",
            entry_price=100.0,
            exit_price=110.0,
            quantity=1.0,
            entry_timestamp=now,
            exit_timestamp=now + datetime.timedelta(hours=1),
            market_prices_at_entry={},
            market_prices_at_exit={},
            fees_paid=5.0,
        )

        total_contrib = sum(s.contribution_pct for s in result.attribution_scores)
        # Should sum to ~1.0 (allow small variance)
        assert total_contrib == pytest.approx(1.0, abs=0.05)

    def test_edge_case_zero_pnl(self, engine, now):
        """Handle edge case of zero PnL"""
        result = engine.attribute_trade(
            trade_id="trade_zero_pnl",
            symbol="BTCUSDT",
            strategy="test",
            entry_price=100.0,
            exit_price=100.0,  # Zero PnL
            quantity=1.0,
            entry_timestamp=now,
            exit_timestamp=now + datetime.timedelta(hours=1),
            market_prices_at_entry={},
            market_prices_at_exit={},
            fees_paid=2.0,
        )

        assert result.pnl_gross == 0.0
        assert result.pnl_net == -2.0  # Just the fees
        # Should still have valid attribution scores
        assert len(result.attribution_scores) == 6

    def test_edge_case_very_small_pnl(self, engine, now):
        """Handle edge case of very small PnL"""
        result = engine.attribute_trade(
            trade_id="trade_tiny_pnl",
            symbol="BTCUSDT",
            strategy="test",
            entry_price=100.0,
            exit_price=100.001,  # Tiny profit
            quantity=1.0,
            entry_timestamp=now,
            exit_timestamp=now + datetime.timedelta(hours=1),
            market_prices_at_entry={},
            market_prices_at_exit={},
            fees_paid=0.5,
        )

        assert 0 < result.pnl_gross < 0.01
        assert result.pnl_net < 0
        # Should still have valid scores
        assert all(s.score >= -1.0 and s.score <= 1.0 for s in result.attribution_scores)

    def test_multiple_strategies_independent(self, engine, now):
        """Multiple strategies should be tracked independently"""
        strategies = ["STRATEGY_A", "STRATEGY_B", "STRATEGY_C"]

        for strategy in strategies:
            for i in range(3):
                engine.attribute_trade(
                    trade_id=f"trade_{strategy}_{i}",
                    symbol="BTCUSDT",
                    strategy=strategy,
                    entry_price=40000.0,
                    exit_price=41000.0,
                    quantity=1.0,
                    entry_timestamp=now + datetime.timedelta(hours=i),
                    exit_timestamp=now + datetime.timedelta(hours=i + 1),
                    market_prices_at_entry={},
                    market_prices_at_exit={},
                )

        # Verify aggregation is independent per strategy
        for strategy in strategies:
            summary = engine.aggregate_attribution(
                strategy=strategy,
                period_start=now,
                period_end=now + datetime.timedelta(days=1),
            )
            assert summary is not None
            assert summary.trade_count == 3
            assert summary.strategy == strategy


# ═══════════════════════════════════════════════════════════════════════════════
# Test StrategyAttributionSummary / 策略汇总测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestStrategyAttributionSummary:
    """Tests for strategy-level summary dataclass"""

    def test_summary_creation(self, now):
        """Create StrategyAttributionSummary"""
        summary = StrategyAttributionSummary(
            strategy="TEST",
            period_start=now,
            period_end=now + datetime.timedelta(days=1),
            trade_count=10,
            total_pnl_gross=1000.0,
            total_pnl_net=950.0,
            win_rate=0.8,
            avg_skill_pct=0.75,
            avg_luck_pct=0.25,
            skill_consistency=0.05,
            total_cost=50.0,
            attribution_by_category={
                "alpha": 0.5,
                "timing": 0.2,
                "sizing": 0.1,
                "execution": 0.1,
                "cost": 0.05,
                "luck": 0.05,
            },
        )

        assert summary.trade_count == 10
        assert summary.win_rate == 0.8

    def test_summary_serialization(self, now):
        """Serialize and deserialize summary"""
        original = StrategyAttributionSummary(
            strategy="TEST",
            period_start=now,
            period_end=now + datetime.timedelta(days=1),
            trade_count=10,
            total_pnl_gross=1000.0,
            total_pnl_net=950.0,
            win_rate=0.8,
            avg_skill_pct=0.75,
            avg_luck_pct=0.25,
            skill_consistency=0.05,
            total_cost=50.0,
            attribution_by_category={
                "alpha": 0.5,
                "timing": 0.2,
                "sizing": 0.1,
                "execution": 0.1,
                "cost": 0.05,
                "luck": 0.05,
            },
        )

        d = original.to_dict()
        assert "strategy" in d
        assert "win_rate" in d


# ═══════════════════════════════════════════════════════════════════════════════
# Test StrategySkillRatio / 策略 skill 比例测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestStrategySkillRatio:
    """Tests for skill ratio dataclass"""

    def test_skill_ratio_creation(self, now):
        """Create StrategySkillRatio"""
        ratio = StrategySkillRatio(
            strategy="TEST",
            skill_level=SkillLevel.HIGH_SKILL,
            skill_pct=0.85,
            luck_pct=0.15,
            total_trades=50,
            trades_positive_skill=40,
            trades_negative_skill=5,
            confidence=0.95,
            last_updated=now,
        )

        assert ratio.skill_level == SkillLevel.HIGH_SKILL
        assert ratio.confidence == 0.95

    def test_skill_level_classifications(self, now):
        """Skill level should classify correctly"""
        # High skill
        ratio = StrategySkillRatio(
            strategy="HIGH",
            skill_level=SkillLevel.HIGH_SKILL,
            skill_pct=0.8,
            luck_pct=0.2,
            total_trades=50,
            trades_positive_skill=40,
            trades_negative_skill=2,
            confidence=0.95,
            last_updated=now,
        )
        assert ratio.skill_level == SkillLevel.HIGH_SKILL

        # Moderate skill
        ratio = StrategySkillRatio(
            strategy="MODERATE",
            skill_level=SkillLevel.MODERATE_SKILL,
            skill_pct=0.55,
            luck_pct=0.45,
            total_trades=20,
            trades_positive_skill=12,
            trades_negative_skill=5,
            confidence=0.80,
            last_updated=now,
        )
        assert ratio.skill_level == SkillLevel.MODERATE_SKILL

        # Low skill
        ratio = StrategySkillRatio(
            strategy="LOW",
            skill_level=SkillLevel.LOW_SKILL,
            skill_pct=0.30,
            luck_pct=0.70,
            total_trades=10,
            trades_positive_skill=2,
            trades_negative_skill=6,
            confidence=0.50,
            last_updated=now,
        )
        assert ratio.skill_level == SkillLevel.LOW_SKILL


# ═══════════════════════════════════════════════════════════════════════════════
# Additional Coverage Tests / 额外覆盖测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestAttributionCoverage:
    """Additional tests to improve code coverage"""

    def test_trade_attribution_result_warn_on_imbalanced_skill_luck(self, now):
        """Test warning logged for imbalanced skill/luck percentages"""
        # Create a result where skill + luck doesn't sum to ~1.0
        scores = [
            AttributionScore(
                category=cat,
                score=0.5,
                contribution_pct=0.15,
                explanation="test",
            )
            for cat in AttributionCategory
        ]

        # This should log a warning but not fail
        result = TradeAttributionResult(
            trade_id="trade_imbalanced",
            symbol="BTCUSDT",
            strategy="test",
            pnl_gross=100.0,
            pnl_net=85.0,
            attribution_scores=scores,
            skill_pct=0.9,  # High
            luck_pct=0.05,  # Too low, doesn't sum to ~1.0
            total_cost=15.0,
            timestamp=now,
        )
        assert result.skill_pct == 0.9

    def test_attribution_score_dict_rounding(self):
        """Test that to_dict rounds values properly"""
        score = AttributionScore(
            category=AttributionCategory.ALPHA,
            score=0.123456789,
            contribution_pct=0.987654321,
            explanation="Test rounding",
        )
        d = score.to_dict()
        # Values should be rounded to 4 decimal places
        assert d["score"] == 0.1235
        assert d["contribution_pct"] == 0.9877

    def test_trade_attribution_dict_rounding(self, now):
        """Test that to_dict rounds PnL values properly"""
        scores = [
            AttributionScore(
                category=cat,
                score=0.5,
                contribution_pct=0.15,
                explanation="test",
            )
            for cat in AttributionCategory
        ]

        result = TradeAttributionResult(
            trade_id="trade_round",
            symbol="BTCUSDT",
            strategy="test",
            pnl_gross=100.12345678,
            pnl_net=85.87654321,
            attribution_scores=scores,
            skill_pct=0.123456789,
            luck_pct=0.876543211,
            total_cost=14.24691357,
            timestamp=now,
        )
        d = result.to_dict()
        # PnL values rounded to 8 decimals
        assert d["pnl_gross"] == 100.12345678
        assert d["pnl_net"] == 85.87654321
        # Skill/luck to 4 decimals
        assert d["skill_pct"] == 0.1235
        assert d["luck_pct"] == 0.8765

    def test_strategy_attribution_summary_dict_rounding(self, now):
        """Test StrategyAttributionSummary to_dict rounding"""
        summary = StrategyAttributionSummary(
            strategy="TEST",
            period_start=now,
            period_end=now + datetime.timedelta(days=1),
            trade_count=10,
            total_pnl_gross=1000.123456789,
            total_pnl_net=950.987654321,
            win_rate=0.8123456789,
            avg_skill_pct=0.75123456789,
            avg_luck_pct=0.24876543211,
            skill_consistency=0.0512345678,
            total_cost=50.123456789,
            attribution_by_category={"alpha": 0.5123456789},
        )
        d = summary.to_dict()
        assert d["total_pnl_gross"] == 1000.12345679
        assert d["avg_skill_pct"] == 0.7512

    def test_strategy_skill_ratio_dict_rounding(self, now):
        """Test StrategySkillRatio to_dict rounding"""
        ratio = StrategySkillRatio(
            strategy="TEST",
            skill_level=SkillLevel.HIGH_SKILL,
            skill_pct=0.8123456789,
            luck_pct=0.1876543211,
            total_trades=50,
            trades_positive_skill=40,
            trades_negative_skill=5,
            confidence=0.9512345678,
            last_updated=now,
        )
        d = ratio.to_dict()
        assert d["skill_pct"] == 0.8123
        assert d["confidence"] == 0.9512

    def test_sizing_score_no_volatility_data(self, engine):
        """Test sizing score with zero volatility"""
        sizing = engine._calculate_sizing_score(
            quantity=10.0,
            expected_volatility=0.00001,  # Nearly zero
            gross_pnl=100.0,
        )
        # Should default to neutral when vol too small
        assert sizing.score >= -1.0 and sizing.score <= 1.0

    def test_aggregate_attribution_with_varied_pnl(self, engine, now):
        """Test aggregation with mix of profitable and losing trades"""
        # Add 5 profitable and 5 losing trades
        for i in range(5):
            engine.attribute_trade(
                trade_id=f"trade_profit_{i}",
                symbol="BTCUSDT",
                strategy="MIXED",
                entry_price=40000.0,
                exit_price=41000.0,  # +1000
                quantity=1.0,
                entry_timestamp=now + datetime.timedelta(hours=i),
                exit_timestamp=now + datetime.timedelta(hours=i + 1),
                market_prices_at_entry={},
                market_prices_at_exit={},
                fees_paid=10.0,
            )

        for i in range(5):
            engine.attribute_trade(
                trade_id=f"trade_loss_{i}",
                symbol="BTCUSDT",
                strategy="MIXED",
                entry_price=40000.0,
                exit_price=39000.0,  # -1000
                quantity=1.0,
                entry_timestamp=now + datetime.timedelta(hours=i + 10),
                exit_timestamp=now + datetime.timedelta(hours=i + 11),
                market_prices_at_entry={},
                market_prices_at_exit={},
                fees_paid=10.0,
            )

        summary = engine.aggregate_attribution(
            strategy="MIXED",
            period_start=now,
            period_end=now + datetime.timedelta(days=1),
        )

        assert summary is not None
        assert summary.trade_count == 10
        assert summary.win_rate == 0.5  # 5/10
        assert summary.total_pnl_net == -100.0  # 5000 - 5000 - 100 fees

    def test_skill_ratio_low_trade_count_confidence(self, engine, now):
        """Test confidence calibration with low trade count"""
        # Add just 2 trades
        for i in range(2):
            engine.attribute_trade(
                trade_id=f"trade_low_{i}",
                symbol="BTCUSDT",
                strategy="LOW_COUNT",
                entry_price=100.0,
                exit_price=110.0,
                quantity=1.0,
                entry_timestamp=now + datetime.timedelta(hours=i),
                exit_timestamp=now + datetime.timedelta(hours=i + 1),
                market_prices_at_entry={},
                market_prices_at_exit={},
            )

        ratio = engine.get_strategy_skill_ratio("LOW_COUNT")
        assert ratio is not None
        assert ratio.confidence == 0.50  # Low confidence with only 2 trades

    def test_skill_ratio_high_trade_count_confidence(self, engine, now):
        """Test confidence calibration with high trade count"""
        # Add 150 trades
        for i in range(150):
            engine.attribute_trade(
                trade_id=f"trade_high_{i}",
                symbol="BTCUSDT",
                strategy="HIGH_COUNT",
                entry_price=100.0,
                exit_price=110.0,
                quantity=1.0,
                entry_timestamp=now + datetime.timedelta(minutes=i),
                exit_timestamp=now + datetime.timedelta(minutes=i + 1),
                market_prices_at_entry={},
                market_prices_at_exit={},
            )

        ratio = engine.get_strategy_skill_ratio("HIGH_COUNT")
        assert ratio is not None
        assert ratio.confidence == 0.95  # High confidence with 150+ trades

    def test_serialization_deserialize_consistency(self, engine, now):
        """Test that serialize->deserialize preserves data exactly"""
        # Attribute a few trades
        for i in range(3):
            engine.attribute_trade(
                trade_id=f"trade_ser_{i}",
                symbol="ETHUSDT",
                strategy="SER_TEST",
                entry_price=2000.0 + i * 100,
                exit_price=2100.0 + i * 100,
                quantity=2.5,
                entry_timestamp=now + datetime.timedelta(hours=i),
                exit_timestamp=now + datetime.timedelta(hours=i + 1),
                market_prices_at_entry={},
                market_prices_at_exit={},
                fees_paid=5.0,
                slippage=2.0,
                ai_cost=0.5,
            )

        # Serialize and deserialize
        state1 = engine.to_dict()
        engine2 = TradeAttributionEngine()
        engine2.from_dict(state1)
        state2 = engine2.to_dict()

        # States should be identical
        assert len(state1["attribution_cache"]) == len(state2["attribution_cache"])
        for trade_id in state1["attribution_cache"]:
            assert (
                state1["attribution_cache"][trade_id]
                == state2["attribution_cache"][trade_id]
            )

    def test_list_strategy_summaries(self, engine, now):
        """Test listing all strategy summaries"""
        # Create trades for multiple strategies
        for strategy_name in ["STRAT_A", "STRAT_B", "STRAT_C"]:
            engine.attribute_trade(
                trade_id=f"trade_{strategy_name}",
                symbol="BTCUSDT",
                strategy=strategy_name,
                entry_price=100.0,
                exit_price=110.0,
                quantity=1.0,
                entry_timestamp=now,
                exit_timestamp=now + datetime.timedelta(hours=1),
                market_prices_at_entry={},
                market_prices_at_exit={},
            )
            # Create summary
            engine.aggregate_attribution(
                strategy=strategy_name,
                period_start=now,
                period_end=now + datetime.timedelta(days=1),
            )

        summaries = engine.list_strategy_summaries()
        assert len(summaries) == 3
        assert "STRAT_A" in summaries
        assert "STRAT_B" in summaries
        assert "STRAT_C" in summaries

    def test_list_strategy_skill_ratios(self, engine, now):
        """Test listing all strategy skill ratios"""
        # Create trades and compute skill ratios
        for strategy_name in ["SKILL_A", "SKILL_B"]:
            for i in range(3):
                engine.attribute_trade(
                    trade_id=f"trade_{strategy_name}_{i}",
                    symbol="BTCUSDT",
                    strategy=strategy_name,
                    entry_price=100.0,
                    exit_price=110.0 + i * 5,
                    quantity=1.0,
                    entry_timestamp=now + datetime.timedelta(hours=i),
                    exit_timestamp=now + datetime.timedelta(hours=i + 1),
                    market_prices_at_entry={},
                    market_prices_at_exit={},
                )
            # Get skill ratio
            engine.get_strategy_skill_ratio(strategy_name)

        ratios = engine.list_strategy_skill_ratios()
        assert len(ratios) == 2
        assert "SKILL_A" in ratios
        assert "SKILL_B" in ratios
