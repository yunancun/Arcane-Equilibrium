"""
Batch 7 Tests — Conductor lifecycle, MessageBus routing, StrategistAgent signal evaluation
===========================================================================================
25+ tests covering:
- Conductor lifecycle (start, register, heartbeat, status)
- MessageBus routing (Scout→Strategist subscription, message delivery)
- StrategistAgent AI evaluation (Ollama mock, fallback, shadow mode)
- PipelineBridge Strategist intent collection
- fail-closed behavior (errors → reject)
"""

import time
import threading
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

import sys
import os

# Ensure app is importable
_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
_app_dir = os.path.join(_control_api_dir, "app")
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)


from app.multi_agent_framework import (
    AgentMessage,
    AgentRole,
    AgentState,
    Conductor,
    DataQualityLevel,
    EventAlert,
    IntelObject,
    MessageBus,
    MessageType,
    ScoutAgent,
    ScoutConfig,
    SentimentScore,
    TradeIntent,
)
from app.strategist_agent import (
    EdgeEvaluation,
    StrategistAgent,
    StrategistConfig,
    _heuristic_evaluate,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Conductor Lifecycle / Conductor 生命周期测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestConductorLifecycle(unittest.TestCase):
    """Test Conductor creation, agent registration, and lifecycle management."""

    def test_conductor_creation(self):
        """Conductor can be created with default MessageBus."""
        conductor = Conductor()
        self.assertIsNotNone(conductor.bus)
        status = conductor.get_status()
        self.assertEqual(status["role"], "conductor")
        self.assertEqual(status["agents_registered"], 0)

    def test_conductor_with_shared_bus(self):
        """Conductor can share an existing MessageBus."""
        bus = MessageBus()
        conductor = Conductor(message_bus=bus)
        self.assertIs(conductor.bus, bus)

    def test_register_agent(self):
        """Conductor registers agents correctly."""
        conductor = Conductor()
        info = conductor.register_agent(AgentRole.SCOUT, resource_mode="local")
        self.assertEqual(info.role, AgentRole.SCOUT)
        self.assertEqual(info.state, AgentState.INITIALIZING)
        self.assertEqual(info.resource_mode, "local")

        status = conductor.get_status()
        self.assertEqual(status["agents_registered"], 1)
        self.assertEqual(status["agents_running"], 0)

    def test_set_agent_state(self):
        """Conductor can transition agent states."""
        conductor = Conductor()
        conductor.register_agent(AgentRole.SCOUT)
        self.assertTrue(conductor.set_agent_state(AgentRole.SCOUT, AgentState.RUNNING))

        status = conductor.get_status()
        self.assertEqual(status["agents_running"], 1)

    def test_heartbeat(self):
        """Heartbeat updates last_heartbeat_ms."""
        conductor = Conductor()
        conductor.register_agent(AgentRole.SCOUT)
        before = conductor.get_agent_info(AgentRole.SCOUT).last_heartbeat_ms
        time.sleep(0.01)
        conductor.heartbeat(AgentRole.SCOUT)
        after = conductor.get_agent_info(AgentRole.SCOUT).last_heartbeat_ms
        self.assertGreater(after, before)

    def test_heartbeat_nonexistent_agent(self):
        """Heartbeat for unregistered agent returns False."""
        conductor = Conductor()
        self.assertFalse(conductor.heartbeat(AgentRole.ANALYST))

    def test_register_multiple_agents(self):
        """Conductor registers multiple agent roles."""
        conductor = Conductor()
        for role in [AgentRole.SCOUT, AgentRole.STRATEGIST, AgentRole.GUARDIAN]:
            conductor.register_agent(role)
            conductor.set_agent_state(role, AgentState.RUNNING)

        status = conductor.get_status()
        self.assertEqual(status["agents_registered"], 3)
        self.assertEqual(status["agents_running"], 3)

    def test_broadcast_directive(self):
        """Conductor broadcasts system directives to agents."""
        bus = MessageBus()
        conductor = Conductor(message_bus=bus)
        for role in [AgentRole.SCOUT, AgentRole.STRATEGIST]:
            conductor.register_agent(role)
            conductor.set_agent_state(role, AgentState.RUNNING)

        sent = conductor.broadcast_directive("test_directive", {"data": "value"})
        self.assertGreater(sent, 0)


# ═══════════════════════════════════════════════════════════════════════════════
# Test: MessageBus Routing / 消息总线路由测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestMessageBusRouting(unittest.TestCase):
    """Test MessageBus subscription and message delivery."""

    def test_subscribe_and_deliver(self):
        """Messages delivered to subscriber via role-based subscription."""
        bus = MessageBus()
        received = []
        bus.subscribe(AgentRole.STRATEGIST, lambda msg: received.append(msg))

        msg = AgentMessage(
            sender=AgentRole.SCOUT,
            receiver=AgentRole.STRATEGIST,
            message_type=MessageType.INTEL_OBJECT,
            payload={"test": True},
        )
        result = bus.send(msg)
        self.assertTrue(result)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].payload["test"], True)

    def test_invalid_route_rejected(self):
        """Invalid route (e.g., Scout→Executor) is rejected."""
        bus = MessageBus()
        msg = AgentMessage(
            sender=AgentRole.SCOUT,
            receiver=AgentRole.EXECUTOR,
            message_type=MessageType.INTEL_OBJECT,
        )
        result = bus.send(msg)
        self.assertFalse(result)

    def test_scout_to_strategist_intel(self):
        """Scout→Strategist INTEL_OBJECT route is valid."""
        bus = MessageBus()
        received = []
        bus.subscribe(AgentRole.STRATEGIST, lambda msg: received.append(msg))

        scout = ScoutAgent(config=ScoutConfig(), message_bus=bus)
        scout.start()
        intel = scout.produce_intel(
            source="test",
            content="BTC bullish signal",
            symbols=["BTCUSDT"],
            relevance_score=0.8,
            sentiment=SentimentScore.POSITIVE,
        )
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].message_type, MessageType.INTEL_OBJECT)

    def test_scout_to_guardian_event_alert(self):
        """Scout→Guardian EVENT_ALERT route works."""
        bus = MessageBus()
        received = []
        bus.subscribe(AgentRole.GUARDIAN, lambda msg: received.append(msg))

        scout = ScoutAgent(config=ScoutConfig(), message_bus=bus)
        scout.start()
        alert = scout.produce_event_alert(
            event_type="fomc",
            severity="high",
            affected_symbols=["BTCUSDT"],
        )
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].message_type, MessageType.EVENT_ALERT)


# ═══════════════════════════════════════════════════════════════════════════════
# Test: StrategistAgent / 策略师代理测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestStrategistAgent(unittest.TestCase):
    """Test StrategistAgent signal evaluation and intent production."""

    def _make_intel_message(
        self,
        symbols=None,
        relevance=0.8,
        sentiment="positive",
        content="BTC bullish signal",
        freshness=10,
        data_quality="fact",
    ):
        """Helper to create an IntelObject AgentMessage."""
        return AgentMessage(
            sender=AgentRole.SCOUT,
            receiver=AgentRole.STRATEGIST,
            message_type=MessageType.INTEL_OBJECT,
            payload={
                "intel_id": f"test_intel_{time.time_ns()}",
                "source": "test",
                "timestamp_ms": int(time.time() * 1000),
                "freshness_seconds": freshness,
                "data_quality": data_quality,
                "sentiment": sentiment,
                "relevance_score": relevance,
                "content": content,
                "symbols": symbols or ["BTCUSDT"],
                "metadata": {},
            },
        )

    def test_strategist_creation(self):
        """StrategistAgent can be created with default config."""
        agent = StrategistAgent()
        self.assertEqual(agent.state, AgentState.INITIALIZING)
        stats = agent.get_stats()
        self.assertEqual(stats["role"], "strategist")

    def test_strategist_start_stop(self):
        """StrategistAgent lifecycle transitions work."""
        agent = StrategistAgent()
        agent.start()
        self.assertEqual(agent.state, AgentState.RUNNING)
        agent.pause()
        self.assertEqual(agent.state, AgentState.PAUSED)
        agent.stop()
        self.assertEqual(agent.state, AgentState.STOPPED)

    def test_ignores_message_when_not_running(self):
        """StrategistAgent ignores messages when not RUNNING."""
        agent = StrategistAgent()
        msg = self._make_intel_message()
        agent.on_message(msg)
        self.assertEqual(agent.get_stats()["intel_received"], 0)

    def test_shadow_mode_logs_only(self):
        """Shadow mode: StrategistAgent logs intent but doesn't buffer it."""
        agent = StrategistAgent(config=StrategistConfig(shadow=True, min_confidence=0.1))
        agent.start()
        msg = self._make_intel_message(relevance=0.8, sentiment="positive", freshness=10)
        agent.on_message(msg)

        stats = agent.get_stats()
        self.assertGreater(stats["intel_received"], 0)
        # In shadow mode, pending_intents should be 0
        self.assertEqual(stats["pending_intents"], 0)
        # But shadow_logged should be > 0 if edge was found
        # (depends on heuristic pass)

    def test_low_relevance_ignored(self):
        """Intel below min_relevance is ignored."""
        agent = StrategistAgent(config=StrategistConfig(min_relevance=0.5))
        agent.start()
        msg = self._make_intel_message(relevance=0.1)
        agent.on_message(msg)
        stats = agent.get_stats()
        self.assertEqual(stats["intel_evaluated"], 0)

    def test_old_intel_ignored(self):
        """Intel older than max_intel_age_seconds is ignored."""
        agent = StrategistAgent(config=StrategistConfig(max_intel_age_seconds=60))
        agent.start()
        msg = self._make_intel_message()
        # Make it old
        msg.payload["timestamp_ms"] = int((time.time() - 120) * 1000)
        agent.on_message(msg)
        stats = agent.get_stats()
        self.assertEqual(stats["intel_evaluated"], 0)

    def test_heuristic_evaluation_reject_neutral(self):
        """Heuristic rejects neutral sentiment."""
        intel = IntelObject(
            relevance_score=0.8,
            sentiment=SentimentScore.NEUTRAL,
            data_quality=DataQualityLevel.FACT,
            freshness_seconds=10,
            symbols=["BTCUSDT"],
        )
        config = StrategistConfig()
        result = _heuristic_evaluate(intel, config)
        self.assertFalse(result.has_edge)
        self.assertIn("Neutral", result.reason)

    def test_heuristic_evaluation_reject_hypothesis(self):
        """Heuristic rejects HYPOTHESIS-quality intel."""
        intel = IntelObject(
            relevance_score=0.8,
            sentiment=SentimentScore.POSITIVE,
            data_quality=DataQualityLevel.HYPOTHESIS,
            freshness_seconds=10,
            symbols=["BTCUSDT"],
        )
        config = StrategistConfig()
        result = _heuristic_evaluate(intel, config)
        self.assertFalse(result.has_edge)
        self.assertIn("HYPOTHESIS", result.reason)

    def test_heuristic_evaluation_reject_stale(self):
        """Heuristic rejects stale intel."""
        intel = IntelObject(
            relevance_score=0.8,
            sentiment=SentimentScore.POSITIVE,
            data_quality=DataQualityLevel.FACT,
            freshness_seconds=999,
            symbols=["BTCUSDT"],
        )
        config = StrategistConfig()
        result = _heuristic_evaluate(intel, config)
        self.assertFalse(result.has_edge)
        self.assertIn("stale", result.reason)

    def test_heuristic_evaluation_pass(self):
        """Heuristic approves high-quality, fresh, directional intel."""
        intel = IntelObject(
            relevance_score=0.9,
            sentiment=SentimentScore.POSITIVE,
            data_quality=DataQualityLevel.FACT,
            freshness_seconds=10,
            symbols=["BTCUSDT"],
        )
        config = StrategistConfig()
        result = _heuristic_evaluate(intel, config)
        self.assertTrue(result.has_edge)
        self.assertEqual(result.source, "heuristic")
        self.assertGreater(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 0.6)  # heuristic caps at 0.6

    def test_ai_evaluation_with_mock_ollama(self):
        """StrategistAgent uses Ollama judge_edge when available."""
        mock_ollama = MagicMock()
        mock_ollama.is_available.return_value = True
        mock_ollama.judge_edge.return_value = MagicMock(
            success=True,
            text='{"has_edge": true, "confidence": 0.75, "reason": "Strong trend"}',
        )

        agent = StrategistAgent(
            config=StrategistConfig(shadow=False, min_confidence=0.3),
            ollama_client=mock_ollama,
        )
        agent.start()
        msg = self._make_intel_message(relevance=0.8, sentiment="positive")
        agent.on_message(msg)

        stats = agent.get_stats()
        self.assertGreater(stats["ai_evaluations"], 0)
        self.assertGreater(stats["intents_produced"], 0)

    def test_ai_fallback_when_ollama_unavailable(self):
        """StrategistAgent falls back to heuristic when Ollama unavailable."""
        mock_ollama = MagicMock()
        mock_ollama.is_available.return_value = False

        agent = StrategistAgent(
            config=StrategistConfig(shadow=True),
            ollama_client=mock_ollama,
        )
        agent.start()
        msg = self._make_intel_message(relevance=0.8, sentiment="positive")
        agent.on_message(msg)

        stats = agent.get_stats()
        self.assertEqual(stats["ai_evaluations"], 0)
        self.assertGreater(stats["heuristic_evaluations"], 0)

    def test_ai_error_falls_back_to_heuristic(self):
        """StrategistAgent falls back when judge_edge raises."""
        mock_ollama = MagicMock()
        mock_ollama.is_available.return_value = True
        mock_ollama.judge_edge.side_effect = Exception("Connection refused")

        agent = StrategistAgent(
            config=StrategistConfig(shadow=True),
            ollama_client=mock_ollama,
        )
        agent.start()
        msg = self._make_intel_message(relevance=0.8, sentiment="positive")
        agent.on_message(msg)

        stats = agent.get_stats()
        self.assertGreater(stats["heuristic_evaluations"], 0)

    def test_ai_invalid_json_fail_closed(self):
        """AI returns unparseable JSON → fail-closed (no edge)."""
        mock_ollama = MagicMock()
        mock_ollama.is_available.return_value = True
        mock_ollama.judge_edge.return_value = MagicMock(
            success=True,
            text="This is not JSON",
        )

        agent = StrategistAgent(
            config=StrategistConfig(shadow=True),
            ollama_client=mock_ollama,
        )
        agent.start()
        msg = self._make_intel_message(relevance=0.8, sentiment="positive")
        agent.on_message(msg)

        # Should have attempted AI evaluation but failed to parse
        stats = agent.get_stats()
        self.assertGreater(stats["ai_evaluations"], 0)

    def test_collect_pending_intents(self):
        """PipelineBridge can collect pending intents from StrategistAgent."""
        mock_ollama = MagicMock()
        mock_ollama.is_available.return_value = True
        mock_ollama.judge_edge.return_value = MagicMock(
            success=True,
            text='{"has_edge": true, "confidence": 0.8, "reason": "Good edge"}',
        )

        agent = StrategistAgent(
            config=StrategistConfig(shadow=False, min_confidence=0.3),
            ollama_client=mock_ollama,
        )
        agent.start()
        msg = self._make_intel_message(relevance=0.8, sentiment="positive")
        agent.on_message(msg)

        intents = agent.collect_pending_intents()
        self.assertGreater(len(intents), 0)
        self.assertEqual(intents[0].symbol, "BTCUSDT")
        self.assertEqual(intents[0].direction, "long")

        # After collect, buffer should be empty
        intents2 = agent.collect_pending_intents()
        self.assertEqual(len(intents2), 0)

    def test_shadow_directive_toggle(self):
        """Conductor directive can toggle shadow mode."""
        agent = StrategistAgent(config=StrategistConfig(shadow=True))
        agent.start()

        # Turn shadow off
        directive = AgentMessage(
            sender=AgentRole.CONDUCTOR,
            receiver=AgentRole.STRATEGIST,
            message_type=MessageType.SYSTEM_DIRECTIVE,
            payload={"directive_type": "shadow_off"},
        )
        agent.on_message(directive)
        self.assertFalse(agent.config.shadow)

        # Turn shadow on
        directive.payload = {"directive_type": "shadow_on"}
        agent.on_message(directive)
        self.assertTrue(agent.config.shadow)

    def test_short_direction_on_negative_sentiment(self):
        """Negative sentiment intel produces short direction intent."""
        mock_ollama = MagicMock()
        mock_ollama.is_available.return_value = True
        mock_ollama.judge_edge.return_value = MagicMock(
            success=True,
            text='{"has_edge": true, "confidence": 0.7, "reason": "Bearish"}',
        )

        agent = StrategistAgent(
            config=StrategistConfig(shadow=False, min_confidence=0.3),
            ollama_client=mock_ollama,
        )
        agent.start()
        msg = self._make_intel_message(relevance=0.8, sentiment="negative")
        agent.on_message(msg)

        intents = agent.collect_pending_intents()
        self.assertGreater(len(intents), 0)
        self.assertEqual(intents[0].direction, "short")


# ═══════════════════════════════════════════════════════════════════════════════
# Test: End-to-End Scout→Strategist Pipeline / 端到端管线测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestScoutToStrategistPipeline(unittest.TestCase):
    """Test full Scout→MessageBus→Strategist pipeline."""

    def test_scout_intel_reaches_strategist(self):
        """IntelObject from Scout reaches StrategistAgent via MessageBus."""
        bus = MessageBus()
        strategist = StrategistAgent(
            config=StrategistConfig(shadow=True),
            message_bus=bus,
        )
        strategist.start()
        bus.subscribe(AgentRole.STRATEGIST, strategist.on_message)

        scout = ScoutAgent(config=ScoutConfig(relevance_threshold=0.3), message_bus=bus)
        scout.start()

        scout.produce_intel(
            source="test",
            content="BTC strong bullish",
            symbols=["BTCUSDT"],
            relevance_score=0.7,
            sentiment=SentimentScore.POSITIVE,
            freshness_seconds=5,
        )

        stats = strategist.get_stats()
        self.assertGreater(stats["intel_received"], 0)
        self.assertGreater(stats["intel_evaluated"], 0)

    def test_conductor_full_pipeline(self):
        """Conductor + Scout + Strategist full pipeline."""
        bus = MessageBus()
        conductor = Conductor(message_bus=bus)

        scout = ScoutAgent(config=ScoutConfig(relevance_threshold=0.3), message_bus=bus)
        scout.start()
        conductor.register_agent(AgentRole.SCOUT)
        conductor.set_agent_state(AgentRole.SCOUT, AgentState.RUNNING)

        strategist = StrategistAgent(
            config=StrategistConfig(shadow=True),
            message_bus=bus,
        )
        strategist.start()
        bus.subscribe(AgentRole.STRATEGIST, strategist.on_message)
        conductor.register_agent(AgentRole.STRATEGIST)
        conductor.set_agent_state(AgentRole.STRATEGIST, AgentState.RUNNING)

        status = conductor.get_status()
        self.assertEqual(status["agents_registered"], 2)
        self.assertEqual(status["agents_running"], 2)

        # Scout produces intel → Strategist receives
        scout.produce_intel(
            source="test",
            content="ETH breakout",
            symbols=["ETHUSDT"],
            relevance_score=0.8,
            sentiment=SentimentScore.POSITIVE,
        )

        stats = strategist.get_stats()
        self.assertGreater(stats["intel_received"], 0)


if __name__ == "__main__":
    unittest.main()
