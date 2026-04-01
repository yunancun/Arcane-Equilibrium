"""
GuardianAgent Unit Tests — 5 checks, MODIFIED logic, Qwen classification, fail-closed
========================================================================================
20 tests covering:
- Each of 5 checks (direction conflict, leverage, correlation, Sharpe, drawdown)
- APPROVED / REJECTED / MODIFIED verdicts
- Qwen event classification (mock)
- fail-closed behavior
- SM-04 risk upgrade trigger
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
    RiskVerdictResult,
    TradeIntent,
)
from app.guardian_agent import GuardianAgent, GuardianConfig


class TestGuardianLifecycle(unittest.TestCase):
    """Test GuardianAgent creation and lifecycle."""

    def test_creation(self):
        agent = GuardianAgent()
        self.assertEqual(agent.state, AgentState.INITIALIZING)
        stats = agent.get_stats()
        self.assertEqual(stats["role"], "guardian")

    def test_start_stop(self):
        agent = GuardianAgent()
        agent.start()
        self.assertEqual(agent.state, AgentState.RUNNING)
        agent.stop()
        self.assertEqual(agent.state, AgentState.STOPPED)


class TestGuardianReview(unittest.TestCase):
    """Test the 5 checks and verdict logic."""

    def _make_intent(self, symbol="BTCUSDT", direction="long", size=0.01, leverage=1.0, strategy="test", confidence=0.7):
        return TradeIntent(
            symbol=symbol,
            strategy=strategy,
            direction=direction,
            size=size,
            params={"leverage": leverage},
            confidence=confidence,
        )

    def test_all_checks_pass_approved(self):
        """Intent passing all 5 checks gets APPROVED."""
        agent = GuardianAgent(config=GuardianConfig())
        agent.start()
        intent = self._make_intent()
        verdict = agent.review_intent(intent)
        self.assertEqual(verdict.result, RiskVerdictResult.APPROVED)
        self.assertEqual(verdict.reason, "All 5 checks passed")

    def test_direction_conflict_rejected(self):
        """Opposite-direction position on same symbol → REJECTED."""
        agent = GuardianAgent(config=GuardianConfig())
        agent.start()
        agent.update_active_positions({
            "test:BTCUSDT": {"symbol": "BTCUSDT", "side": "Sell"},
        })
        intent = self._make_intent(direction="long")
        verdict = agent.review_intent(intent)
        self.assertEqual(verdict.result, RiskVerdictResult.REJECTED)
        self.assertIn("Direction conflict", verdict.reason)

    def test_too_many_same_direction(self):
        """Exceeding max same-direction positions → REJECTED."""
        config = GuardianConfig(max_same_direction_positions=2)
        agent = GuardianAgent(config=config)
        agent.start()
        agent.update_active_positions({
            "s1:ETHUSDT": {"symbol": "ETHUSDT", "side": "Buy"},
            "s2:SOLUSDT": {"symbol": "SOLUSDT", "side": "Buy"},
        })
        intent = self._make_intent(direction="long", symbol="XRPUSDT")
        verdict = agent.review_intent(intent)
        self.assertEqual(verdict.result, RiskVerdictResult.REJECTED)
        self.assertIn("Too many", verdict.reason)

    def test_leverage_excessive_rejected(self):
        """Leverage far exceeding cap → REJECTED."""
        config = GuardianConfig(max_leverage=5.0)
        agent = GuardianAgent(config=config)
        agent.start()
        intent = self._make_intent(leverage=15.0)
        verdict = agent.review_intent(intent)
        self.assertEqual(verdict.result, RiskVerdictResult.REJECTED)
        self.assertIn("Leverage", verdict.reason)

    def test_leverage_moderate_modified(self):
        """Leverage slightly over cap → MODIFIED (capped + size reduced)."""
        config = GuardianConfig(max_leverage=5.0)
        agent = GuardianAgent(config=config)
        agent.start()
        intent = self._make_intent(leverage=7.0, size=0.1)
        verdict = agent.review_intent(intent)
        self.assertEqual(verdict.result, RiskVerdictResult.MODIFIED)
        self.assertIn("leverage", verdict.modified_params)
        self.assertIn("size", verdict.modified_params)
        self.assertEqual(verdict.modified_params["leverage"], config.modification_leverage_cap)
        self.assertAlmostEqual(verdict.modified_params["size"], 0.1 * config.modification_size_factor)

    def test_correlation_conflict_rejected(self):
        """BTC+ETH same direction → correlation conflict REJECTED."""
        config = GuardianConfig(max_correlation=0.8)
        agent = GuardianAgent(config=config)
        agent.start()
        agent.update_active_positions({
            "s1:BTCUSDT": {"symbol": "BTCUSDT", "side": "Buy"},
        })
        intent = self._make_intent(symbol="ETHUSDT", direction="long")
        verdict = agent.review_intent(intent)
        self.assertEqual(verdict.result, RiskVerdictResult.REJECTED)
        self.assertIn("Correlation", verdict.reason)

    def test_correlation_ok_opposite_direction(self):
        """BTC long + ETH short → no correlation conflict (different directions)."""
        config = GuardianConfig(max_correlation=0.8)
        agent = GuardianAgent(config=config)
        agent.start()
        agent.update_active_positions({
            "s1:BTCUSDT": {"symbol": "BTCUSDT", "side": "Sell"},
        })
        intent = self._make_intent(symbol="ETHUSDT", direction="long")
        verdict = agent.review_intent(intent)
        self.assertEqual(verdict.result, RiskVerdictResult.APPROVED)

    def test_sharpe_below_threshold_rejected(self):
        """Strategy with poor Sharpe → REJECTED."""
        config = GuardianConfig(min_sharpe_ratio=0.5)
        agent = GuardianAgent(config=config)
        agent.start()
        agent.update_strategy_metrics({"test": {"sharpe_ratio": 0.1}})
        intent = self._make_intent()
        verdict = agent.review_intent(intent)
        self.assertEqual(verdict.result, RiskVerdictResult.REJECTED)
        self.assertIn("Sharpe", verdict.reason)

    def test_sharpe_no_data_passes(self):
        """No Sharpe data for strategy → check passes (no rejection)."""
        config = GuardianConfig(min_sharpe_ratio=0.5)
        agent = GuardianAgent(config=config)
        agent.start()
        intent = self._make_intent(strategy="new_strategy")
        verdict = agent.review_intent(intent)
        self.assertEqual(verdict.result, RiskVerdictResult.APPROVED)

    def test_drawdown_exceeded_rejected(self):
        """Portfolio drawdown > limit → REJECTED."""
        config = GuardianConfig(max_drawdown_pct=10.0)
        mock_rm = MagicMock()
        mock_rm.get_portfolio_summary.return_value = {"current_drawdown_pct": -12.0}

        agent = GuardianAgent(config=config, risk_manager=mock_rm)
        agent.start()
        intent = self._make_intent()
        verdict = agent.review_intent(intent)
        self.assertEqual(verdict.result, RiskVerdictResult.REJECTED)
        self.assertIn("drawdown", verdict.reason.lower())

    def test_drawdown_within_limit_passes(self):
        """Portfolio drawdown within limit → passes."""
        config = GuardianConfig(max_drawdown_pct=15.0)
        mock_rm = MagicMock()
        mock_rm.get_portfolio_summary.return_value = {"current_drawdown_pct": -5.0}

        agent = GuardianAgent(config=config, risk_manager=mock_rm)
        agent.start()
        intent = self._make_intent()
        verdict = agent.review_intent(intent)
        self.assertEqual(verdict.result, RiskVerdictResult.APPROVED)


class TestGuardianFailClosed(unittest.TestCase):
    """Test fail-closed behavior."""

    def test_review_exception_returns_rejected(self):
        """Any exception during review → fail-closed REJECTED."""
        agent = GuardianAgent()
        agent.start()

        # Corrupt the config to force error
        agent._active_positions = None  # Will cause iteration error

        intent = TradeIntent(symbol="BTCUSDT", direction="long", size=0.01)
        verdict = agent.review_intent(intent)
        self.assertEqual(verdict.result, RiskVerdictResult.REJECTED)
        self.assertIn("fail-closed", verdict.reason)

    def test_stats_track_errors(self):
        """Errors are tracked in stats."""
        agent = GuardianAgent()
        agent.start()
        agent._active_positions = None  # force error

        intent = TradeIntent(symbol="BTCUSDT", direction="long", size=0.01)
        agent.review_intent(intent)
        stats = agent.get_stats()
        self.assertGreater(stats["errors"], 0)


class TestGuardianEventAlert(unittest.TestCase):
    """Test event alert handling."""

    def test_event_alert_increments_stats(self):
        """EventAlert processing increments events_assessed."""
        agent = GuardianAgent()
        agent.start()
        msg = AgentMessage(
            sender=AgentRole.SCOUT,
            receiver=AgentRole.GUARDIAN,
            message_type=MessageType.EVENT_ALERT,
            payload={"event_type": "fomc", "severity": "high", "affected_symbols": ["BTCUSDT"]},
        )
        agent.on_message(msg)
        self.assertEqual(agent.get_stats()["events_assessed"], 1)

    def test_event_alert_with_ai_classification(self):
        """EventAlert uses Qwen classify() when available."""
        mock_ollama = MagicMock()
        mock_ollama.is_available.return_value = True
        mock_ollama.classify.return_value = MagicMock(success=True, text="high")

        agent = GuardianAgent(ollama_client=mock_ollama)
        agent.start()
        msg = AgentMessage(
            sender=AgentRole.SCOUT,
            receiver=AgentRole.GUARDIAN,
            message_type=MessageType.EVENT_ALERT,
            payload={"event_type": "cpi", "severity": "medium", "affected_symbols": ["BTCUSDT"]},
        )
        agent.on_message(msg)
        mock_ollama.classify.assert_called_once()

    def test_high_event_triggers_sm04(self):
        """High-risk event triggers SM-04 risk upgrade via GovernanceHub."""
        mock_gov = MagicMock()
        mock_gov.trigger_risk_upgrade = MagicMock()

        mock_ollama = MagicMock()
        mock_ollama.is_available.return_value = True
        mock_ollama.classify.return_value = MagicMock(success=True, text="critical")

        agent = GuardianAgent(ollama_client=mock_ollama, governance_hub=mock_gov)
        agent.start()
        msg = AgentMessage(
            sender=AgentRole.SCOUT,
            receiver=AgentRole.GUARDIAN,
            message_type=MessageType.EVENT_ALERT,
            payload={"event_type": "flash_crash", "severity": "critical", "affected_symbols": ["BTCUSDT"]},
        )
        agent.on_message(msg)
        mock_gov.trigger_risk_upgrade.assert_called_once()

    def test_directive_updates_risk_params(self):
        """Conductor directive can update risk parameters."""
        agent = GuardianAgent(config=GuardianConfig(max_leverage=5.0))
        agent.start()
        msg = AgentMessage(
            sender=AgentRole.CONDUCTOR,
            receiver=AgentRole.GUARDIAN,
            message_type=MessageType.SYSTEM_DIRECTIVE,
            payload={"directive_type": "update_risk_params", "params": {"max_leverage": 3.0}},
        )
        agent.on_message(msg)
        self.assertEqual(agent.config.max_leverage, 3.0)


class TestGuardianVerdictLog(unittest.TestCase):
    """Test verdict log and bus feedback."""

    def test_verdict_sent_to_bus(self):
        """Verdict is sent back to Strategist via MessageBus."""
        bus = MessageBus()
        received = []
        bus.subscribe(AgentRole.STRATEGIST, lambda m: received.append(m))

        agent = GuardianAgent(message_bus=bus)
        agent.start()
        intent = TradeIntent(symbol="BTCUSDT", direction="long", size=0.01)
        agent.review_intent(intent)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].message_type, MessageType.RISK_VERDICT)

    def test_recent_verdicts(self):
        """Recent verdicts are queryable."""
        agent = GuardianAgent()
        agent.start()
        for i in range(5):
            intent = TradeIntent(symbol="BTCUSDT", direction="long", size=0.01)
            agent.review_intent(intent)
        verdicts = agent.get_recent_verdicts(limit=3)
        self.assertEqual(len(verdicts), 3)


class TestGuardianApprovedIntentEmission(unittest.TestCase):
    """APR01-P1-5: Test that Guardian emits APPROVED_INTENT to Executor via MessageBus.
    APR01-P1-5：测试 Guardian 通过 MessageBus 向 Executor 发送 APPROVED_INTENT。
    """

    def _make_trade_intent_message(self, symbol="BTCUSDT", direction="long", size=0.01, leverage=1.0):
        """Helper: create a TRADE_INTENT AgentMessage as Strategist would send."""
        return AgentMessage(
            sender=AgentRole.STRATEGIST,
            receiver=AgentRole.GUARDIAN,
            message_type=MessageType.TRADE_INTENT,
            payload={
                "intent_id": "test_intent_001",
                "symbol": symbol,
                "strategy": "test_strategy",
                "direction": direction,
                "size": size,
                "params": {"leverage": leverage},
                "confidence": 0.7,
                "thesis": "test thesis",
                "invalidation_condition": "",
                "metadata": {"source": "unit_test"},
            },
        )

    def test_approved_intent_emitted_on_approval(self):
        """When Guardian approves, APPROVED_INTENT is sent to Executor via bus.
        当 Guardian 批准时，APPROVED_INTENT 通过 bus 发送给 Executor。
        """
        bus = MessageBus()
        executor_received = []
        bus.subscribe(AgentRole.EXECUTOR, lambda m: executor_received.append(m))

        agent = GuardianAgent(message_bus=bus, config=GuardianConfig())
        agent.start()

        msg = self._make_trade_intent_message()
        agent.on_message(msg)

        # Executor should receive exactly 1 APPROVED_INTENT
        approved = [m for m in executor_received if m.message_type == MessageType.APPROVED_INTENT]
        self.assertEqual(len(approved), 1, "Executor should receive 1 APPROVED_INTENT")
        self.assertEqual(approved[0].payload["symbol"], "BTCUSDT")
        self.assertEqual(approved[0].payload["direction"], "long")
        self.assertEqual(approved[0].payload["intent_id"], "test_intent_001")

    def test_approved_intent_not_emitted_on_rejection(self):
        """When Guardian rejects, NO APPROVED_INTENT is sent.
        当 Guardian 拒绝时，不发送 APPROVED_INTENT。
        """
        bus = MessageBus()
        executor_received = []
        bus.subscribe(AgentRole.EXECUTOR, lambda m: executor_received.append(m))

        # Force rejection: excessive leverage
        config = GuardianConfig(max_leverage=5.0)
        agent = GuardianAgent(message_bus=bus, config=config)
        agent.start()

        msg = self._make_trade_intent_message(leverage=15.0)
        agent.on_message(msg)

        approved = [m for m in executor_received if m.message_type == MessageType.APPROVED_INTENT]
        self.assertEqual(len(approved), 0, "Executor should NOT receive APPROVED_INTENT on rejection")

    def test_modified_intent_emitted_with_adjustments(self):
        """When Guardian modifies, APPROVED_INTENT is sent with adjusted params.
        当 Guardian 修改时，APPROVED_INTENT 带修改后参数发送。
        """
        bus = MessageBus()
        executor_received = []
        bus.subscribe(AgentRole.EXECUTOR, lambda m: executor_received.append(m))

        # Trigger modification: leverage slightly over cap
        config = GuardianConfig(max_leverage=5.0, modification_size_factor=0.5)
        agent = GuardianAgent(message_bus=bus, config=config)
        agent.start()

        msg = self._make_trade_intent_message(leverage=7.0, size=0.1)
        agent.on_message(msg)

        approved = [m for m in executor_received if m.message_type == MessageType.APPROVED_INTENT]
        self.assertEqual(len(approved), 1, "Executor should receive 1 APPROVED_INTENT for MODIFIED")
        payload = approved[0].payload
        # Size should be reduced by modification_size_factor
        self.assertAlmostEqual(payload["size"], 0.1 * 0.5)
        # guardian_modified flag should be set
        self.assertTrue(payload.get("metadata", {}).get("guardian_modified"))

    def test_approved_intent_sender_is_strategist(self):
        """APPROVED_INTENT sender must be STRATEGIST to match VALID_ROUTES.
        APPROVED_INTENT 发送者必须是 STRATEGIST 以匹配路由表。
        """
        bus = MessageBus()
        executor_received = []
        bus.subscribe(AgentRole.EXECUTOR, lambda m: executor_received.append(m))

        agent = GuardianAgent(message_bus=bus, config=GuardianConfig())
        agent.start()

        msg = self._make_trade_intent_message()
        agent.on_message(msg)

        approved = [m for m in executor_received if m.message_type == MessageType.APPROVED_INTENT]
        self.assertEqual(len(approved), 1)
        self.assertEqual(approved[0].sender, AgentRole.STRATEGIST)

    def test_bus_send_failure_is_fail_open(self):
        """If bus.send raises, _handle_trade_intent still completes (fail-open).
        如果 bus.send 抛出异常，_handle_trade_intent 仍然完成（失败开放）。
        """
        bus = MessageBus()
        original_send = bus.send

        call_count = {"n": 0}

        def failing_send(msg):
            call_count["n"] += 1
            # Let the RISK_VERDICT through (first call), fail on APPROVED_INTENT (second call)
            if msg.message_type == MessageType.APPROVED_INTENT:
                raise RuntimeError("Simulated bus failure")
            return original_send(msg)

        bus.send = failing_send

        agent = GuardianAgent(message_bus=bus, config=GuardianConfig())
        agent.start()

        msg = self._make_trade_intent_message()
        # Should not raise — fail-open
        agent.on_message(msg)
        # Verify review_intent still completed (stats updated)
        stats = agent.get_stats()
        self.assertEqual(stats["verdicts_approved"], 1)

    def test_no_bus_no_emission(self):
        """If no MessageBus, no APPROVED_INTENT is emitted (no crash).
        如果没有 MessageBus，不发送 APPROVED_INTENT（也不会崩溃）。
        """
        agent = GuardianAgent(message_bus=None, config=GuardianConfig())
        agent.start()

        msg = self._make_trade_intent_message()
        # Should not raise
        agent.on_message(msg)
        stats = agent.get_stats()
        self.assertEqual(stats["verdicts_approved"], 1)

    def test_risk_verdict_still_sent_to_strategist(self):
        """RISK_VERDICT is still sent to Strategist (existing behavior unchanged).
        RISK_VERDICT 仍然发送给 Strategist（现有行为不变）。
        """
        bus = MessageBus()
        strategist_received = []
        executor_received = []
        bus.subscribe(AgentRole.STRATEGIST, lambda m: strategist_received.append(m))
        bus.subscribe(AgentRole.EXECUTOR, lambda m: executor_received.append(m))

        agent = GuardianAgent(message_bus=bus, config=GuardianConfig())
        agent.start()

        msg = self._make_trade_intent_message()
        agent.on_message(msg)

        # Strategist gets RISK_VERDICT
        verdicts = [m for m in strategist_received if m.message_type == MessageType.RISK_VERDICT]
        self.assertEqual(len(verdicts), 1, "Strategist should still receive RISK_VERDICT")

        # Executor gets APPROVED_INTENT
        approved = [m for m in executor_received if m.message_type == MessageType.APPROVED_INTENT]
        self.assertEqual(len(approved), 1, "Executor should receive APPROVED_INTENT")


if __name__ == "__main__":
    unittest.main()
