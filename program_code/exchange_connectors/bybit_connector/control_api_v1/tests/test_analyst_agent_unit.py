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


# ═══════════════════════════════════════════════════════════════════════════════
# TestAnalystSnapshot
# G3-08 Phase 4 Sub-task 4-3: Analyst agent_state snapshot accessor (5 fields)
# G3-08 Phase 4 Sub-task 4-3：Analyst agent 狀態 snapshot 存取器（5 欄位）
# ═══════════════════════════════════════════════════════════════════════════════


class TestAnalystSnapshot(unittest.TestCase):
    """G3-08 Phase 4 Sub-task 4-3: verify get_analyst_snapshot() returns
    5-field dict per PA RFC §2.3, schema-parity with Rust
    ``AgentState.stats: HashMap<String, i64>``.

    G3-08 Phase 4 Sub-task 4-3：驗證 get_analyst_snapshot() 回傳 5-field
    dict（PA RFC §2.3），schema 對齊 Rust ``AgentState.stats``。
    """

    _EXPECTED_FIELDS = {
        "trades_analyzed",
        "l1_updates",
        "l2_analyses",
        "errors",
        "experiment_ledger_connected",
    }

    def test_get_analyst_snapshot_initial_state(self):
        """Fresh agent → all 5 counters 0; schema has exactly 5 keys.
        新建 agent → 5 counters 皆 0；schema 恰 5 個 key。"""
        agent = AnalystAgent()
        snap = agent.get_analyst_snapshot()
        self.assertEqual(set(snap.keys()), self._EXPECTED_FIELDS)
        for key in self._EXPECTED_FIELDS:
            self.assertEqual(snap[key], 0, f"{key} must be 0 on fresh agent")
            # All values must be int (Rust HashMap<String, i64> parity).
            self.assertIsInstance(snap[key], int, f"{key} must be int")

    def test_get_analyst_snapshot_returns_independent_dicts(self):
        """Multiple calls return independent dict objects (no aliasing).
        多次呼叫回獨立 dict（無別名）。"""
        agent = AnalystAgent()
        a = agent.get_analyst_snapshot()
        b = agent.get_analyst_snapshot()
        self.assertIsNot(a, b)
        a["trades_analyzed"] = 999
        self.assertEqual(b["trades_analyzed"], 0)
        c = agent.get_analyst_snapshot()
        self.assertEqual(c["trades_analyzed"], 0)

    def test_get_analyst_snapshot_reflects_stats_increments(self):
        """analyze_trade() must bump trades_analyzed + l1_updates in snapshot.
        analyze_trade() 必須讓 snapshot 中 trades_analyzed + l1_updates 遞增。"""
        agent = AnalystAgent()
        agent.start()
        record = TradeRecord(
            trade_id="t-snap-1",
            symbol="BTCUSDT",
            strategy="grid_trading",
            direction="long",
            entry_price=60000.0,
            exit_price=60100.0,
            pnl=0.001,
            hold_ms=1000,
            regime="trending",
            timestamp_ms=int(time.time() * 1000),
        )
        agent.analyze_trade(record)
        snap = agent.get_analyst_snapshot()
        self.assertEqual(snap["trades_analyzed"], 1)
        self.assertEqual(snap["l1_updates"], 1)
        self.assertEqual(snap["errors"], 0)

    def test_get_analyst_snapshot_experiment_ledger_flag(self):
        """experiment_ledger_connected reflects whether set_experiment_ledger
        injected a non-None ledger; bool→int (0 or 1).
        experiment_ledger_connected 反映 set_experiment_ledger 是否注入非 None
        ledger；bool→int（0 或 1）。"""
        agent = AnalystAgent()
        # No ledger injected → 0.
        self.assertEqual(agent.get_analyst_snapshot()["experiment_ledger_connected"], 0)
        # Inject a stub ledger → 1.
        agent.set_experiment_ledger(MagicMock())
        snap = agent.get_analyst_snapshot()
        self.assertEqual(snap["experiment_ledger_connected"], 1)
        self.assertIsInstance(snap["experiment_ledger_connected"], int)
        # Reset to None → back to 0.
        agent.set_experiment_ledger(None)
        self.assertEqual(agent.get_analyst_snapshot()["experiment_ledger_connected"], 0)

    def test_get_analyst_snapshot_error_path_increments_errors(self):
        """_handle_round_trip exception path bumps errors counter; snapshot
        observable in same metric. _handle_round_trip 例外路徑遞增 errors。"""
        agent = AnalystAgent()
        agent.start()
        # Malformed payload: entry_price is non-numeric → float() raises.
        msg = AgentMessage(
            sender=AgentRole.EXECUTOR,
            receiver=AgentRole.ANALYST,
            message_type=MessageType.ROUND_TRIP_COMPLETE,
            payload={"trade_id": "bad", "entry_price": "not_a_number"},
        )
        agent.on_message(msg)
        snap = agent.get_analyst_snapshot()
        self.assertEqual(snap["errors"], 1)
        self.assertEqual(snap["trades_analyzed"], 0)


if __name__ == "__main__":
    unittest.main()
