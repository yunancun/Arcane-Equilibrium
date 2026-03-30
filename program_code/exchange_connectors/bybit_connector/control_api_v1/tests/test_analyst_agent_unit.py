"""
AnalystAgent Unit Tests — Metrics calculation, L2 trigger, PatternInsight, edge cases
=======================================================================================
15 tests covering:
- L1: Trade analysis, rolling win rate, strategy ranking, regime metrics
- L2: Trigger condition, PatternInsight structure, AI and statistical fallback
- Edge cases: empty data, single trade, duplicate strategies
"""

import time
import unittest
from unittest.mock import MagicMock

import sys
import os

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app.multi_agent_framework import (
    AgentMessage,
    AgentRole,
    AgentState,
    MessageBus,
    MessageType,
)
from app.analyst_agent import (
    AnalystAgent,
    AnalystConfig,
    PatternInsight,
    TradeRecord,
)


class TestAnalystLifecycle(unittest.TestCase):

    def test_creation(self):
        agent = AnalystAgent()
        self.assertEqual(agent.state, AgentState.INITIALIZING)

    def test_start_stop(self):
        agent = AnalystAgent()
        agent.start()
        self.assertEqual(agent.state, AgentState.RUNNING)
        agent.stop()
        self.assertEqual(agent.state, AgentState.STOPPED)


class TestAnalystL1(unittest.TestCase):
    """Test L1 statistical analysis."""

    def _make_record(self, strategy="strat_a", pnl=0.01, regime="trending", symbol="BTCUSDT"):
        return TradeRecord(
            trade_id=f"t_{time.time_ns()}",
            symbol=symbol,
            strategy=strategy,
            direction="long",
            entry_price=60000.0,
            exit_price=60000.0 + (pnl * 60000.0),
            pnl=pnl,
            hold_ms=3600000,
            regime=regime,
            timestamp_ms=int(time.time() * 1000),
        )

    def test_single_trade_analysis(self):
        """Single trade updates metrics correctly."""
        agent = AnalystAgent()
        agent.start()
        record = self._make_record(pnl=0.05)
        metrics = agent.analyze_trade(record)
        self.assertEqual(metrics["total_trades"], 1)
        self.assertEqual(metrics["win_rate"], 1.0)

    def test_win_rate_calculation(self):
        """Win rate computed correctly over multiple trades."""
        agent = AnalystAgent()
        agent.start()
        # 3 wins, 2 losses
        for pnl in [0.05, 0.03, -0.02, 0.01, -0.04]:
            agent.analyze_trade(self._make_record(pnl=pnl))
        metrics = agent.compute_strategy_metrics("strat_a")
        self.assertEqual(metrics["total_trades"], 5)
        self.assertAlmostEqual(metrics["win_rate"], 0.6, places=2)

    def test_multiple_strategies_tracked(self):
        """Different strategies tracked independently."""
        agent = AnalystAgent()
        agent.start()
        agent.analyze_trade(self._make_record(strategy="alpha", pnl=0.05))
        agent.analyze_trade(self._make_record(strategy="beta", pnl=-0.02))

        alpha = agent.compute_strategy_metrics("alpha")
        beta = agent.compute_strategy_metrics("beta")
        self.assertEqual(alpha["win_rate"], 1.0)
        self.assertEqual(beta["win_rate"], 0.0)

    def test_strategy_rankings(self):
        """Rankings sorted by Sharpe ratio."""
        config = AnalystConfig(min_trades_for_ranking=2)
        agent = AnalystAgent(config=config)
        agent.start()
        # Strategy A: all wins
        for _ in range(3):
            agent.analyze_trade(self._make_record(strategy="winner", pnl=0.05))
        # Strategy B: all losses
        for _ in range(3):
            agent.analyze_trade(self._make_record(strategy="loser", pnl=-0.03))

        rankings = agent.get_strategy_rankings()
        self.assertGreater(len(rankings), 0)
        # Winner should rank higher
        if len(rankings) >= 2:
            self.assertGreaterEqual(rankings[0]["sharpe_ratio"], rankings[1]["sharpe_ratio"])

    def test_regime_metrics(self):
        """Per-regime metrics computed correctly."""
        agent = AnalystAgent()
        agent.start()
        agent.analyze_trade(self._make_record(regime="trending", pnl=0.05))
        agent.analyze_trade(self._make_record(regime="ranging", pnl=-0.02))
        agent.analyze_trade(self._make_record(regime="trending", pnl=0.03))

        regime = agent.get_regime_metrics()
        self.assertIn("trending", regime)
        self.assertIn("ranging", regime)
        self.assertEqual(regime["trending"]["trades"], 2)
        self.assertEqual(regime["ranging"]["trades"], 1)

    def test_sharpe_ratio_calculation(self):
        """Sharpe ratio (mean/std) is computed."""
        agent = AnalystAgent()
        agent.start()
        for pnl in [0.05, 0.03, 0.07, 0.04, 0.06]:
            agent.analyze_trade(self._make_record(pnl=pnl))
        metrics = agent.compute_strategy_metrics("strat_a")
        self.assertGreater(metrics["sharpe_ratio"], 0.0)

    def test_empty_strategy_metrics(self):
        """Non-existent strategy returns zero metrics."""
        agent = AnalystAgent()
        agent.start()
        metrics = agent.compute_strategy_metrics("nonexistent")
        self.assertEqual(metrics["total_trades"], 0)
        self.assertEqual(metrics["win_rate"], 0.0)
        self.assertEqual(metrics["sharpe_ratio"], 0.0)

    def test_learning_tier_gate_updated(self):
        """LearningTierGate.update_metrics called after trade analysis."""
        mock_ltg = MagicMock()
        mock_ltg.update_metrics = MagicMock()
        agent = AnalystAgent(learning_tier_gate=mock_ltg)
        agent.start()
        agent.analyze_trade(self._make_record(pnl=0.05))
        mock_ltg.update_metrics.assert_called_once()


class TestAnalystL2(unittest.TestCase):
    """Test L2 pattern discovery."""

    def _fill_records(self, agent, count=200, pnl_positive_rate=0.6):
        """Helper to fill agent with N trade records."""
        import random
        for i in range(count):
            pnl = 0.05 if random.random() < pnl_positive_rate else -0.03
            strategy = random.choice(["alpha", "beta", "gamma"])
            regime = random.choice(["trending", "ranging", "volatile"])
            record = TradeRecord(
                trade_id=f"t_{i}",
                symbol="BTCUSDT",
                strategy=strategy,
                direction="long",
                entry_price=60000.0,
                exit_price=60000.0 + pnl * 60000.0,
                pnl=pnl,
                hold_ms=3600000,
                regime=regime,
                timestamp_ms=int(time.time() * 1000),
            )
            agent._records.append(record)
            ss = agent._strategy_stats[strategy]
            ss["trades"] += 1
            ss["total_pnl"] += pnl
            ss["pnl_list"].append(pnl)
            if pnl > 0:
                ss["wins"] += 1
            else:
                ss["losses"] += 1
            rs = agent._regime_stats[regime]
            rs["trades"] += 1
            rs["total_pnl"] += pnl
            if pnl > 0:
                rs["wins"] += 1
            else:
                rs["losses"] += 1

    def test_l2_not_triggered_below_threshold(self):
        """L2 analysis not triggered with insufficient observations."""
        config = AnalystConfig(l2_min_observations=200)
        agent = AnalystAgent(config=config)
        agent.start()
        result = agent._run_l2_analysis()
        self.assertIsNone(result)

    def test_l2_statistical_fallback(self):
        """L2 uses statistical analysis when Ollama unavailable."""
        config = AnalystConfig(l2_min_observations=50, min_trades_for_ranking=5)
        agent = AnalystAgent(config=config)
        agent.start()
        self._fill_records(agent, count=60)
        insight = agent._run_l2_analysis()
        self.assertIsNotNone(insight)
        self.assertEqual(insight.source, "statistical")
        self.assertGreater(insight.observations_count, 0)

    def test_l2_ai_analysis(self):
        """L2 uses Qwen AI when available."""
        mock_ollama = MagicMock()
        mock_ollama.is_available.return_value = True
        mock_ollama.generate.return_value = MagicMock(
            success=True,
            text='{"winning_patterns": ["alpha in trending"], "losing_patterns": ["gamma in ranging"], "regime_strategy_matrix": {"trending": {"alpha": 0.7}}}',
        )

        config = AnalystConfig(l2_min_observations=50)
        agent = AnalystAgent(config=config, ollama_client=mock_ollama)
        agent.start()
        self._fill_records(agent, count=60)
        insight = agent._run_l2_analysis()
        self.assertIsNotNone(insight)
        self.assertEqual(insight.source, "ai")
        self.assertGreater(len(insight.winning_patterns), 0)

    def test_pattern_insight_structure(self):
        """PatternInsight has required fields."""
        insight = PatternInsight(
            observations_count=200,
            winning_patterns=["trend following in trending"],
            losing_patterns=["mean reversion in trending"],
            regime_strategy_matrix={"trending": {"alpha": 0.7}},
            source="statistical",
        )
        d = insight.to_dict()
        self.assertIn("winning_patterns", d)
        self.assertIn("losing_patterns", d)
        self.assertIn("regime_strategy_matrix", d)
        self.assertIn("insight_id", d)

    def test_pattern_insight_sent_to_bus(self):
        """PatternInsight sent to Strategist via MessageBus."""
        bus = MessageBus()
        received = []
        bus.subscribe(AgentRole.STRATEGIST, lambda m: received.append(m))

        config = AnalystConfig(l2_min_observations=50, min_trades_for_ranking=5)
        agent = AnalystAgent(config=config, message_bus=bus)
        agent.start()
        self._fill_records(agent, count=60)
        agent._run_l2_analysis()
        self.assertGreater(len(received), 0)
        self.assertEqual(received[0].message_type, MessageType.PATTERN_INSIGHT)

    def test_latest_insight_queryable(self):
        """Latest insight is accessible via get_latest_insight."""
        config = AnalystConfig(l2_min_observations=50, min_trades_for_ranking=5)
        agent = AnalystAgent(config=config)
        agent.start()
        self._fill_records(agent, count=60)
        agent._run_l2_analysis()
        insight = agent.get_latest_insight()
        self.assertIsNotNone(insight)


class TestAnalystMessageHandling(unittest.TestCase):
    """Test message handling."""

    def test_round_trip_message_handled(self):
        """ROUND_TRIP_COMPLETE message triggers analysis."""
        agent = AnalystAgent()
        agent.start()
        msg = AgentMessage(
            sender=AgentRole.EXECUTOR,
            receiver=AgentRole.ANALYST,
            message_type=MessageType.ROUND_TRIP_COMPLETE,
            payload={
                "trade_id": "t1",
                "symbol": "BTCUSDT",
                "strategy": "test",
                "direction": "long",
                "entry_price": 60000.0,
                "exit_price": 60500.0,
                "pnl": 0.05,
                "hold_ms": 3600000,
                "regime": "trending",
            },
        )
        agent.on_message(msg)
        self.assertEqual(agent.get_stats()["trades_analyzed"], 1)


if __name__ == "__main__":
    unittest.main()
