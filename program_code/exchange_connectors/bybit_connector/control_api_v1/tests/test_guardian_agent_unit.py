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


if __name__ == "__main__":
    unittest.main()
