"""
MODULE_NOTE (中文):
  Batch 9 Perception Plane + Analyst Agent 集成测试
  职责：
  1. 验证 PerceptionPlane 数据注册、认知等级标记、新鲜度计算
  2. 验证 Analyst Agent 接收 ROUND_TRIP_COMPLETE 消息并更新指标
  3. 验证漂移保护、数据质量评分、L1/L2 分析流程
  4. 验证 MessageBus 往返流程：Executor → Analyst
  5. 集成测试：25 个测试覆盖所有关键交互路径

MODULE_NOTE (English):
  Batch 9 Perception Plane + Analyst Agent Integration Tests
  Responsibilities:
  1. Verify PerceptionPlane data registration, cognitive level marking, freshness calculation
  2. Verify AnalystAgent receives ROUND_TRIP_COMPLETE messages and updates metrics
  3. Verify drift protection, data quality scoring, L1/L2 analysis flows
  4. Verify MessageBus round-trip: Executor → Analyst
  5. Integration tests: 25 tests covering all critical interaction paths

Governance refs: EX-07 §1-§8, EX-06 §7, DOC-04 §G
"""

import sys
import os
import time
import json
import unittest
from unittest.mock import MagicMock, patch, call

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app.perception_data_plane import (
    CognitiveLevel,
    DataSourceType,
    DataQuality,
    Freshness,
    DegradationAction,
    PerceptionPlane,
    PerceptionDataObject,
    SOURCE_COGNITIVE_DEFAULTS,
    calculate_freshness,
)
from app.analyst_agent import (
    AnalystAgent,
    AnalystConfig,
    TradeRecord,
    PatternInsight,
)
from app.multi_agent_framework import (
    MessageBus,
    AgentMessage,
    AgentRole,
    AgentState,
    MessageType,
)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST SUITE: Batch 9 Perception Plane + Analyst Agent Integration (25 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestPerceptionPlaneDataRegistration(unittest.TestCase):
    """Tests 1-5: PerceptionPlane data registration and cognitive level marking."""

    def setUp(self):
        self.perception = PerceptionPlane()

    def test_1_kline_data_marked_as_fact(self):
        """Test 1: PerceptionPlane registers kline data as FACT (DataSourceType.EXCHANGE_WS, CognitiveLevel.FACT)"""
        pdo = self.perception.register_data(
            source_type=DataSourceType.EXCHANGE_WS,
            content={"kline": [60000.0, 60100.0, 59900.0, 60050.0], "time_ms": 1234567890},
            source_detail="wss://stream.bybit.com/v5/public/linear?symbol=BTCUSDT",
            cognitive_level=CognitiveLevel.FACT,
            symbols=["BTCUSDT"],
            marked_by="system",
            marking_reason="Exchange WebSocket stream (EX-07 §1)",
        )
        self.assertIsNotNone(pdo)
        self.assertEqual(pdo.cognitive_level, CognitiveLevel.FACT)
        self.assertEqual(pdo.source_type, DataSourceType.EXCHANGE_WS)
        self.assertIn("BTCUSDT", pdo.symbols)

    def test_2_signals_marked_as_inference(self):
        """Test 2: PerceptionPlane registers signals as INFERENCE"""
        pdo = self.perception.register_data(
            source_type=DataSourceType.LOCAL_INDICATOR,
            content={"rsi": 65.5, "moving_avg": 60050.0},
            cognitive_level=CognitiveLevel.INFERENCE,
            symbols=["BTCUSDT"],
            marked_by="strategist",
            marking_reason="Computed from exchange data (EX-07 §1)",
        )
        self.assertIsNotNone(pdo)
        self.assertEqual(pdo.cognitive_level, CognitiveLevel.INFERENCE)

    def test_3_scout_intel_marked_as_inference(self):
        """Test 3: PerceptionPlane registers scout intel as INFERENCE"""
        pdo = self.perception.register_data(
            source_type=DataSourceType.SEARCH_WEB,
            content="Large liquidation event on Binance detected",
            cognitive_level=CognitiveLevel.INFERENCE,
            symbols=["BTCUSDT"],
            marked_by="scout",
            marking_reason="Search-based intel (EX-07 §1)",
        )
        self.assertIsNotNone(pdo)
        self.assertEqual(pdo.cognitive_level, CognitiveLevel.INFERENCE)

    def test_4_event_alerts_marked_as_inference(self):
        """Test 4: PerceptionPlane registers event alerts as INFERENCE"""
        pdo = self.perception.register_data(
            source_type=DataSourceType.EVENT_CALENDAR,
            content={"event": "FOMC Decision", "time": 1234567890, "symbols": ["BTCUSDT"]},
            cognitive_level=CognitiveLevel.INFERENCE,
            symbols=["BTCUSDT"],
            marked_by="scout",
            marking_reason="Calendar event (EX-07 §1)",
        )
        self.assertIsNotNone(pdo)
        self.assertEqual(pdo.cognitive_level, CognitiveLevel.INFERENCE)

    def test_5_hypothesis_level_data(self):
        """Test 5: PerceptionPlane registers hypothesis-level data as HYPOTHESIS"""
        pdo = self.perception.register_data(
            source_type=DataSourceType.LOCAL_OLLAMA,
            content="Potential trend reversal based on sentiment analysis",
            cognitive_level=CognitiveLevel.HYPOTHESIS,
            symbols=["BTCUSDT"],
            marked_by="analyst",
            marking_reason="Low-confidence pattern guess (EX-07 §1)",
        )
        self.assertIsNotNone(pdo)
        self.assertEqual(pdo.cognitive_level, CognitiveLevel.HYPOTHESIS)


class TestPerceptionPlaneDriftProtection(unittest.TestCase):
    """Tests 6: Drift protection — search data cannot be marked as FACT."""

    def setUp(self):
        self.perception = PerceptionPlane()

    def test_6_drift_protection_search_data_auto_corrected(self):
        """Test 6: Drift protection: search data cannot be marked as FACT (auto-corrected to INFERENCE)"""
        # Attempt to mark search data as FACT — should auto-correct to INFERENCE
        pdo = self.perception.register_data(
            source_type=DataSourceType.SEARCH_PERPLEXITY,
            content="Bitcoin whale purchased 1000 BTC",
            cognitive_level=CognitiveLevel.FACT,  # Deliberately wrong
            symbols=["BTCUSDT"],
            marked_by="bad_agent",
            marking_reason="Mistakenly marked as fact",
        )
        # System should auto-correct
        self.assertEqual(pdo.cognitive_level, CognitiveLevel.INFERENCE)
        # Check drift warnings
        warnings = self.perception.check_drift()
        self.assertGreater(len(warnings), 0)
        self.assertIn("inference_as_fact", warnings[0].drift_type)


class TestPerceptionPlaneDataFreshness(unittest.TestCase):
    """Test 7: Data freshness calculation."""

    def setUp(self):
        self.perception = PerceptionPlane()

    def test_7_data_freshness_calculation(self):
        """Test 7: Data freshness calculation (FRESH, STALE, EXPIRED)"""
        # Register data with current timestamp
        pdo = self.perception.register_data(
            source_type=DataSourceType.EXCHANGE_WS,
            content={"price": 60000.0},
            symbols=["BTCUSDT"],
        )
        pdo.refresh_freshness()
        self.assertEqual(pdo.freshness, Freshness.FRESH)

        # Test STALE (1 hour ago)
        pdo2 = self.perception.register_data(
            source_type=DataSourceType.EXCHANGE_WS,
            content={"price": 60000.0},
            symbols=["BTCUSDT"],
        )
        pdo2.fetched_at_ms = int(time.time() * 1000) - 3600 * 1000
        pdo2.refresh_freshness()
        self.assertEqual(pdo2.freshness, Freshness.STALE)

        # Test EXPIRED (3 hours ago)
        pdo3 = self.perception.register_data(
            source_type=DataSourceType.EXCHANGE_WS,
            content={"price": 60000.0},
            symbols=["BTCUSDT"],
        )
        pdo3.fetched_at_ms = int(time.time() * 1000) - 10800 * 1000
        pdo3.refresh_freshness()
        self.assertEqual(pdo3.freshness, Freshness.EXPIRED)


class TestPerceptionPlaneDecisionEligibility(unittest.TestCase):
    """Test 8: Decision eligibility checks."""

    def setUp(self):
        self.perception = PerceptionPlane()

    def test_8_decision_eligibility_checks(self):
        """Test 8: Decision eligibility checks (FRESH+marked vs EXPIRED vs filtering)"""
        # Test 1: FRESH + marked = eligible
        pdo = self.perception.register_data(
            source_type=DataSourceType.EXCHANGE_WS,
            content={"price": 60000.0},
            cognitive_level=CognitiveLevel.FACT,
            symbols=["BTCUSDT"],
        )
        pdo.refresh_freshness()
        eligible = pdo.is_decision_eligible()
        self.assertTrue(eligible)

        # Test 2: EXPIRED → not eligible
        pdo2 = self.perception.register_data(
            source_type=DataSourceType.EXCHANGE_WS,
            content={"price": 60000.0},
            cognitive_level=CognitiveLevel.FACT,
            symbols=["BTCUSDT"],
        )
        pdo2.fetched_at_ms = int(time.time() * 1000) - 10800 * 1000  # 3 hours ago
        pdo2.refresh_freshness()
        eligible = pdo2.is_decision_eligible()
        self.assertFalse(eligible)

        # Test 3: get_decision_eligible_data filters correctly
        pdo3 = self.perception.register_data(
            source_type=DataSourceType.EXCHANGE_WS,
            content={"price": 59000.0},
            cognitive_level=CognitiveLevel.FACT,
            symbols=["ETHUSDT"],
            metadata={"expired": True},
        )
        pdo3.fetched_at_ms = int(time.time() * 1000) - 10800 * 1000
        pdo3.refresh_freshness()

        eligible = self.perception.get_decision_eligible_data(symbols=["BTCUSDT"])
        self.assertEqual(len(eligible), 1)
        self.assertEqual(eligible[0].data_id, pdo.data_id)


class TestAnalystAgentRoundTrip(unittest.TestCase):
    """Test 9: AnalystAgent receives ROUND_TRIP_COMPLETE via MessageBus."""

    def setUp(self):
        self.bus = MessageBus()
        self.agent = AnalystAgent(message_bus=self.bus)
        self.agent.start()

    def test_9_analyst_round_trip_complete_processing(self):
        """Test 9: AnalystAgent receives ROUND_TRIP_COMPLETE via MessageBus and processes multiple messages"""
        self.bus.subscribe(AgentRole.ANALYST, self.agent.on_message)

        # Send single message
        message = AgentMessage(
            sender=AgentRole.EXECUTOR,
            receiver=AgentRole.ANALYST,
            message_type=MessageType.ROUND_TRIP_COMPLETE,
            payload={
                "trade_id": "trade_001",
                "symbol": "BTCUSDT",
                "strategy": "ma_crossover",
                "direction": "long",
                "entry_price": 60000.0,
                "exit_price": 61000.0,
                "pnl": 1000.0,
                "hold_ms": 3600000,
                "regime": "trending",
                "timestamp_ms": int(time.time() * 1000),
            },
        )
        self.bus.send(message)

        # Send 5 more messages
        for i in range(5):
            message = AgentMessage(
                sender=AgentRole.EXECUTOR,
                receiver=AgentRole.ANALYST,
                message_type=MessageType.ROUND_TRIP_COMPLETE,
                payload={
                    "trade_id": f"trade_{i:03d}",
                    "symbol": "BTCUSDT",
                    "strategy": "ma_crossover",
                    "direction": "long",
                    "entry_price": 60000.0,
                    "exit_price": 60000.0 + (1000.0 * i),
                    "pnl": 500.0 * (i % 2),
                    "hold_ms": 3600000,
                    "regime": "trending",
                    "timestamp_ms": int(time.time() * 1000),
                },
            )
            self.bus.send(message)

        stats = self.agent.get_stats()
        self.assertEqual(stats["trades_analyzed"], 6)


class TestAnalystAgentTradeAnalysis(unittest.TestCase):
    """Test 10-13: AnalystAgent.analyze_trade() updates strategy and regime stats."""

    def setUp(self):
        self.agent = AnalystAgent()
        self.agent.start()

    def _make_record(self, strategy="ma_crossover", pnl=100.0, regime="trending"):
        return TradeRecord(
            trade_id=f"trade_{int(time.time() * 1000)}",
            symbol="BTCUSDT",
            strategy=strategy,
            direction="long",
            entry_price=60000.0,
            exit_price=60000.0 + pnl,
            pnl=pnl,
            hold_ms=3600000,
            regime=regime,
            timestamp_ms=int(time.time() * 1000),
        )

    def test_10_strategy_stats_updated(self):
        """Test 10: AnalystAgent.analyze_trade() updates per-strategy stats"""
        record = self._make_record(strategy="rsi_divergence", pnl=250.0)
        self.agent.analyze_trade(record)
        metrics = self.agent.compute_strategy_metrics("rsi_divergence")
        self.assertEqual(metrics["total_trades"], 1)
        self.assertEqual(metrics["win_rate"], 1.0)
        self.assertEqual(metrics["total_pnl"], 250.0)

    def test_11_regime_stats_updated(self):
        """Test 11: AnalystAgent.analyze_trade() updates per-regime stats"""
        # Add trades in different regimes
        record1 = self._make_record(regime="trending", pnl=200.0)
        record2 = self._make_record(regime="sideways", pnl=-100.0)
        self.agent.analyze_trade(record1)
        self.agent.analyze_trade(record2)
        regime_metrics = self.agent.get_regime_metrics()
        self.assertIn("trending", regime_metrics)
        self.assertIn("sideways", regime_metrics)
        self.assertEqual(regime_metrics["trending"]["trades"], 1)
        self.assertEqual(regime_metrics["sideways"]["trades"], 1)

    def test_12_rolling_win_rate_computation(self):
        """Test 12: AnalystAgent computes rolling win rate correctly"""
        # 6 trades: 4 wins (pnl > 0), 2 losses (pnl < 0)
        for pnl in [100.0, 150.0, -50.0, 200.0, -75.0, 125.0]:
            record = self._make_record(pnl=pnl)
            self.agent.analyze_trade(record)
        metrics = self.agent.compute_strategy_metrics("ma_crossover")
        self.assertEqual(metrics["total_trades"], 6)
        self.assertAlmostEqual(metrics["win_rate"], 4.0 / 6.0, places=4)


class TestAnalystAgentSharpeRatio(unittest.TestCase):
    """Test 13: AnalystAgent computes Sharpe ratio correctly."""

    def setUp(self):
        self.agent = AnalystAgent()
        self.agent.start()

    def test_13_sharpe_ratio_calculation(self):
        """Test 13: AnalystAgent computes Sharpe ratio correctly"""
        pnl_list = [100.0, 150.0, 120.0, 180.0, 140.0]
        for i, pnl in enumerate(pnl_list):
            record = TradeRecord(
                trade_id=f"trade_sharpe_{i}",
                symbol="BTCUSDT",
                strategy="test_sharpe",
                direction="long",
                entry_price=60000.0,
                exit_price=60000.0 + pnl,
                pnl=pnl,
                hold_ms=3600000,
                regime="trending",
                timestamp_ms=int(time.time() * 1000) + i,
            )
            self.agent.analyze_trade(record)
        metrics = self.agent.compute_strategy_metrics("test_sharpe")
        # Sharpe = mean_pnl / std_pnl
        mean = sum(pnl_list) / len(pnl_list)
        variance = sum((p - mean) ** 2 for p in pnl_list) / (len(pnl_list) - 1)
        std = variance ** 0.5
        expected_sharpe = mean / std if std > 0 else 0.0
        self.assertAlmostEqual(metrics["sharpe_ratio"], expected_sharpe, places=2)


class TestAnalystAgentLearningTierGate(unittest.TestCase):
    """Test 14: AnalystAgent updates LearningTierGate metrics after trade analysis."""

    def setUp(self):
        self.mock_gate = MagicMock()
        self.agent = AnalystAgent(learning_tier_gate=self.mock_gate)
        self.agent.start()

    def test_14_learning_tier_gate_metrics_updated(self):
        """Test 14: AnalystAgent updates LearningTierGate metrics after trade analysis"""
        record = TradeRecord(
            trade_id="trade_ltg",
            symbol="BTCUSDT",
            strategy="ltg_test",
            direction="long",
            entry_price=60000.0,
            exit_price=61000.0,
            pnl=1000.0,
            hold_ms=3600000,
            regime="trending",
            timestamp_ms=int(time.time() * 1000),
        )
        self.agent.analyze_trade(record)
        # Check that LearningTierGate.update_metrics was called
        self.mock_gate.update_metrics.assert_called()
        call_args = self.mock_gate.update_metrics.call_args
        self.assertIsNotNone(call_args)
        self.assertIn("observation_count", call_args.kwargs)
        self.assertIn("win_rate", call_args.kwargs)


class TestAnalystAgentL2PatternAnalysis(unittest.TestCase):
    """Test 15: AnalystAgent L2 pattern analysis triggers after sufficient observations."""

    def setUp(self):
        self.config = AnalystConfig(l2_min_observations=10)
        self.agent = AnalystAgent(config=self.config)
        self.agent.start()

    def test_15_l2_analysis_triggered_after_observations(self):
        """Test 15: AnalystAgent L2 pattern analysis triggers after sufficient observations"""
        # Add 10 trades to trigger L2
        for i in range(10):
            record = TradeRecord(
                trade_id=f"trade_l2_{i}",
                symbol="BTCUSDT",
                strategy="l2_strategy",
                direction="long",
                entry_price=60000.0,
                exit_price=60000.0 + (100.0 * (i % 2)),
                pnl=100.0 * (i % 2),
                hold_ms=3600000,
                regime="trending",
                timestamp_ms=int(time.time() * 1000) + i * 1000,
            )
            self.agent.analyze_trade(record)
        stats = self.agent.get_stats()
        # Should have triggered L2 at least once
        self.assertGreaterEqual(stats["l2_analyses"], 1)


class TestAnalystAgentStrategyRankings(unittest.TestCase):
    """Test 16: AnalystAgent strategy rankings."""

    def setUp(self):
        self.agent = AnalystAgent()
        self.agent.start()

    def test_16_strategy_rankings_by_sharpe(self):
        """Test 16: AnalystAgent strategy rankings"""
        # Create 3 strategies with different performances
        strategies = {
            "high_performer": [100.0] * 15,  # All wins
            "medium_performer": [50.0, -50.0] * 8 + [50.0],  # ~50% win rate
            "low_performer": [-100.0] * 10 + [50.0],  # Low win rate
        }
        for strategy, pnls in strategies.items():
            for i, pnl in enumerate(pnls):
                record = TradeRecord(
                    trade_id=f"trade_{strategy}_{i}",
                    symbol="BTCUSDT",
                    strategy=strategy,
                    direction="long",
                    entry_price=60000.0,
                    exit_price=60000.0 + pnl,
                    pnl=pnl,
                    hold_ms=3600000,
                    regime="trending",
                    timestamp_ms=int(time.time() * 1000) + i * 100,
                )
                self.agent.analyze_trade(record)
        rankings = self.agent.get_strategy_rankings()
        self.assertGreater(len(rankings), 0)
        # High performer should rank higher
        if len(rankings) >= 2:
            self.assertGreaterEqual(
                rankings[0]["sharpe_ratio"], rankings[-1]["sharpe_ratio"]
            )


class TestMessageBusRoundTrip(unittest.TestCase):
    """Test 17: MessageBus round-trip: Executor → Analyst flow."""

    def setUp(self):
        self.bus = MessageBus()

    def test_17_message_bus_executor_analyst_flow(self):
        """Test 17: MessageBus round-trip: Executor → Analyst flow (routes, validation, send/retrieve)"""
        # Test 1: Valid route validation
        is_valid = self.bus.validate_route(
            AgentRole.EXECUTOR,
            AgentRole.ANALYST,
            MessageType.ROUND_TRIP_COMPLETE,
        )
        self.assertTrue(is_valid)

        # Test 2: Invalid route rejected
        is_valid = self.bus.validate_route(
            AgentRole.ANALYST,
            AgentRole.EXECUTOR,
            MessageType.ROUND_TRIP_COMPLETE,
        )
        self.assertFalse(is_valid)

        # Test 3: Send and retrieve
        message = AgentMessage(
            sender=AgentRole.EXECUTOR,
            receiver=AgentRole.ANALYST,
            message_type=MessageType.ROUND_TRIP_COMPLETE,
            payload={"trade_id": "test_001"},
        )
        sent = self.bus.send(message)
        self.assertTrue(sent)
        messages = self.bus.get_messages(receiver=AgentRole.ANALYST)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].message_id, message.message_id)


class TestDataQualityScoring(unittest.TestCase):
    """Test 18: Data quality scoring and degradation."""

    def setUp(self):
        self.perception = PerceptionPlane()

    def test_18_data_quality_and_degradation(self):
        """Test 18: Data quality overall score and degradation actions"""
        # Test 1: Data quality overall score calculation
        quality = DataQuality(
            completeness=0.9,
            consistency=0.95,
            latency_ms=100,
            source_reliability=0.98,
        )
        score = quality.overall_score
        # Should be weighted average: 0.9*0.3 + 0.95*0.3 + (1.0-min(100/5000,1))*0.2 + 0.98*0.2
        expected = 0.9 * 0.3 + 0.95 * 0.3 + 0.98 * 0.2 + (1.0 - 0.02) * 0.2
        self.assertAlmostEqual(score, expected, places=3)

        # Test 2: Degradation from WebSocket disconnect
        self.perception.register_data(
            source_type=DataSourceType.EXCHANGE_WS,
            content={"price": 60000.0},
            symbols=["BTCUSDT"],
            metadata={"data_type": "price"},
        )
        action = self.perception.assess_degradation(
            "price", ws_disconnect_seconds=360
        )
        self.assertEqual(action, DegradationAction.REDUCED)

        # Test 3: Degradation from REST failures
        action = self.perception.assess_degradation(
            "price", rest_consecutive_failures=3
        )
        self.assertEqual(action, DegradationAction.DEFENSIVE)


class TestPerceptionPlaneValidation(unittest.TestCase):
    """Test 19: PerceptionPlane validation for decision entry."""

    def setUp(self):
        self.perception = PerceptionPlane()

    def test_19_validate_for_decision_checks(self):
        """Test 19: PerceptionPlane validates data for decision chain entry"""
        # Test 1: Success with high-quality fresh data
        pdo = self.perception.register_data(
            source_type=DataSourceType.EXCHANGE_WS,
            content={"price": 60000.0},
            cognitive_level=CognitiveLevel.FACT,
            symbols=["BTCUSDT"],
            data_quality=DataQuality(
                completeness=0.9,
                consistency=0.95,
                latency_ms=50,
                source_reliability=0.98,
            ),
        )
        eligible, reason = self.perception.validate_for_decision(pdo.data_id)
        self.assertTrue(eligible)
        self.assertIn("Eligible", reason)

        # Test 2: Failure with expired data
        pdo2 = self.perception.register_data(
            source_type=DataSourceType.EXCHANGE_WS,
            content={"price": 60000.0},
            cognitive_level=CognitiveLevel.FACT,
            symbols=["BTCUSDT"],
        )
        pdo2.fetched_at_ms = int(time.time() * 1000) - 10800 * 1000
        pdo2.refresh_freshness()
        eligible, reason = self.perception.validate_for_decision(pdo2.data_id)
        self.assertFalse(eligible)
        self.assertIn("expired", reason.lower())


class TestPerceptionPlaneStats(unittest.TestCase):
    """Test 20: PerceptionPlane statistics tracking."""

    def setUp(self):
        self.perception = PerceptionPlane()

    def test_20_perception_plane_stats_tracking(self):
        """Test 20: PerceptionPlane tracks statistics correctly"""
        # Register different types
        self.perception.register_data(
            source_type=DataSourceType.EXCHANGE_WS,
            content={"price": 60000.0},
            cognitive_level=CognitiveLevel.FACT,
        )
        self.perception.register_data(
            source_type=DataSourceType.SEARCH_WEB,
            content="test",
            cognitive_level=CognitiveLevel.INFERENCE,
        )
        self.perception.register_data(
            source_type=DataSourceType.LOCAL_OLLAMA,
            content="hypothesis",
            cognitive_level=CognitiveLevel.HYPOTHESIS,
        )
        stats = self.perception.get_stats()
        self.assertEqual(stats["objects_registered"], 3)
        self.assertEqual(stats["facts"], 1)
        self.assertEqual(stats["inferences"], 1)
        self.assertEqual(stats["hypotheses"], 1)


class TestAnalystAgentAudit(unittest.TestCase):
    """Test 21: AnalystAgent audit logging."""

    def setUp(self):
        self.audit_log = []
        self.agent = AnalystAgent(
            audit_callback=lambda event, data: self.audit_log.append((event, data))
        )
        self.agent.start()

    def test_21_analyst_agent_audit_callback(self):
        """Test 21: AnalystAgent audit logging via callback"""
        record = TradeRecord(
            trade_id="audit_test",
            symbol="BTCUSDT",
            strategy="test",
            direction="long",
            entry_price=60000.0,
            exit_price=61000.0,
            pnl=1000.0,
            hold_ms=3600000,
            regime="trending",
            timestamp_ms=int(time.time() * 1000),
        )
        self.agent.analyze_trade(record)
        # Should have audit entries
        self.assertGreater(len(self.audit_log), 0)
        audit_types = [event for event, _ in self.audit_log]
        self.assertIn("analyst_trade_analyzed", audit_types)


class TestAnalystAgentPatternInsight(unittest.TestCase):
    """Test 22: AnalystAgent PatternInsight structure and creation."""

    def setUp(self):
        self.agent = AnalystAgent()
        self.agent.start()

    def test_22_pattern_insight_structure(self):
        """Test 22: PatternInsight has correct structure"""
        insight = PatternInsight(
            observations_count=100,
            winning_patterns=["ma_crossover: win_rate=0.65", "rsi_divergence: win_rate=0.60"],
            losing_patterns=["bollinger_band_squeeze: win_rate=0.30"],
            regime_strategy_matrix={
                "trending": {"ma_crossover": 0.7, "rsi_divergence": 0.65},
                "sideways": {"ma_crossover": 0.40, "rsi_divergence": 0.55},
            },
            source="statistical",
        )
        insight_dict = insight.to_dict()
        self.assertEqual(insight_dict["observations_count"], 100)
        self.assertEqual(len(insight_dict["winning_patterns"]), 2)
        self.assertEqual(len(insight_dict["losing_patterns"]), 1)
        self.assertIn("trending", insight_dict["regime_strategy_matrix"])


class TestIntegrationRoundTrip(unittest.TestCase):
    """Test 23-25: Full integration tests."""

    def setUp(self):
        self.perception = PerceptionPlane()
        self.bus = MessageBus()
        self.analyst = AnalystAgent(message_bus=self.bus)
        self.analyst.start()
        self.bus.subscribe(AgentRole.ANALYST, self.analyst.on_message)

    def test_23_end_to_end_trade_round_trip(self):
        """Test 23: End-to-end trade round-trip from message to analysis"""
        # Register price data in perception plane
        pdo = self.perception.register_data(
            source_type=DataSourceType.EXCHANGE_WS,
            content={"price": 60000.0},
            cognitive_level=CognitiveLevel.FACT,
            symbols=["BTCUSDT"],
        )
        self.assertIsNotNone(pdo)

        # Send ROUND_TRIP_COMPLETE message
        message = AgentMessage(
            sender=AgentRole.EXECUTOR,
            receiver=AgentRole.ANALYST,
            message_type=MessageType.ROUND_TRIP_COMPLETE,
            payload={
                "trade_id": "e2e_trade_001",
                "symbol": "BTCUSDT",
                "strategy": "e2e_test",
                "direction": "long",
                "entry_price": 60000.0,
                "exit_price": 61000.0,
                "pnl": 1000.0,
                "hold_ms": 3600000,
                "regime": "trending",
                "timestamp_ms": int(time.time() * 1000),
            },
        )
        sent = self.bus.send(message)
        self.assertTrue(sent)

        # Verify analyst processed it
        stats = self.analyst.get_stats()
        self.assertEqual(stats["trades_analyzed"], 1)
        self.assertEqual(stats["strategies_tracked"], 1)

    def test_24_perception_analyst_integration(self):
        """Test 24: Perception Plane and Analyst Agent integration"""
        # Register multiple perception data objects
        for i in range(3):
            self.perception.register_data(
                source_type=DataSourceType.EXCHANGE_WS,
                content={"price": 60000.0 + i * 1000},
                cognitive_level=CognitiveLevel.FACT,
                symbols=["BTCUSDT"],
            )

        # Send trades with mixed performance
        for i in range(3):
            message = AgentMessage(
                sender=AgentRole.EXECUTOR,
                receiver=AgentRole.ANALYST,
                message_type=MessageType.ROUND_TRIP_COMPLETE,
                payload={
                    "trade_id": f"perc_trade_{i:03d}",
                    "symbol": "BTCUSDT",
                    "strategy": "perception_test",
                    "direction": "long",
                    "entry_price": 60000.0,
                    "exit_price": 60000.0 + (500.0 * (i % 2 + 1)),
                    "pnl": 500.0 * (i % 2 + 1),
                    "hold_ms": 3600000,
                    "regime": "trending",
                    "timestamp_ms": int(time.time() * 1000) + i * 1000,
                },
            )
            self.bus.send(message)

        # Verify analyst stats
        analyst_stats = self.analyst.get_stats()
        self.assertEqual(analyst_stats["trades_analyzed"], 3)

        metrics = self.analyst.compute_strategy_metrics("perception_test")
        self.assertEqual(metrics["total_trades"], 3)
        self.assertGreater(metrics["total_pnl"], 0.0)

    def test_25_multi_trade_integrated_analysis(self):
        """Test 25: Multi-trade integrated analysis with comprehensive metrics"""
        # Register perception data
        for i in range(5):
            self.perception.register_data(
                source_type=DataSourceType.EXCHANGE_WS,
                content={"price": 60000.0 + i * 500},
                cognitive_level=CognitiveLevel.FACT,
                symbols=["BTCUSDT"],
            )

        # Send 5 trades with different strategies and regimes
        trade_params = [
            ("strategy_a", "trending", 250.0),
            ("strategy_a", "trending", -100.0),
            ("strategy_b", "sideways", 150.0),
            ("strategy_b", "sideways", 300.0),
            ("strategy_a", "trending", 200.0),
        ]

        for i, (strategy, regime, pnl) in enumerate(trade_params):
            message = AgentMessage(
                sender=AgentRole.EXECUTOR,
                receiver=AgentRole.ANALYST,
                message_type=MessageType.ROUND_TRIP_COMPLETE,
                payload={
                    "trade_id": f"multi_trade_{i:03d}",
                    "symbol": "BTCUSDT",
                    "strategy": strategy,
                    "direction": "long",
                    "entry_price": 60000.0,
                    "exit_price": 60000.0 + pnl,
                    "pnl": pnl,
                    "hold_ms": 3600000,
                    "regime": regime,
                    "timestamp_ms": int(time.time() * 1000) + i * 1000,
                },
            )
            self.bus.send(message)

        # Verify comprehensive stats
        analyst_stats = self.analyst.get_stats()
        self.assertEqual(analyst_stats["trades_analyzed"], 5)
        self.assertEqual(analyst_stats["total_records"], 5)
        self.assertEqual(analyst_stats["strategies_tracked"], 2)
        self.assertEqual(analyst_stats["regimes_tracked"], 2)

        # Verify strategy metrics
        strategy_a = self.analyst.compute_strategy_metrics("strategy_a")
        self.assertEqual(strategy_a["total_trades"], 3)
        self.assertGreater(strategy_a["win_rate"], 0.0)

        strategy_b = self.analyst.compute_strategy_metrics("strategy_b")
        self.assertEqual(strategy_b["total_trades"], 2)
        self.assertEqual(strategy_b["win_rate"], 1.0)

        # Verify regime metrics
        regime_metrics = self.analyst.get_regime_metrics()
        self.assertIn("trending", regime_metrics)
        self.assertIn("sideways", regime_metrics)

        # Verify perception plane stats
        perception_stats = self.perception.get_stats()
        self.assertEqual(perception_stats["total_objects"], 5)
        self.assertEqual(perception_stats["facts"], 5)


if __name__ == "__main__":
    unittest.main()
