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
        """Dynamic matrix high same-direction correlation → REJECTED."""
        config = GuardianConfig(max_correlation=0.8)
        agent = GuardianAgent(config=config)
        agent.start()
        agent.update_active_positions({
            "s1:BTCUSDT": {"symbol": "BTCUSDT", "side": "Buy"},
        })
        agent.update_correlation_snapshot({
            "snapshot_id": "corr-unit-1",
            "ts_ms": int(time.time() * 1000),
            "source": "runtime_returns",
            "quality": "full",
            "pairwise_r": {"ETHUSDT": {"BTCUSDT": 0.86}},
            "sample_counts": {"ETHUSDT/BTCUSDT": 12},
        })
        intent = self._make_intent(symbol="ETHUSDT", direction="long")
        verdict = agent.review_intent(intent)
        self.assertEqual(verdict.result, RiskVerdictResult.REJECTED)
        self.assertIn("Correlation", verdict.reason)

    def test_dynamic_correlation_rejects_non_btc_eth_pair(self):
        """SOL+XRP high dynamic correlation rejects without static BTC/ETH map."""
        config = GuardianConfig(max_correlation=0.8)
        agent = GuardianAgent(config=config)
        agent.start()
        agent.update_active_positions({
            "s1:SOLUSDT": {"symbol": "SOLUSDT", "side": "Buy"},
        })
        agent.update_correlation_snapshot({
            "snapshot_id": "corr-unit-sol-xrp",
            "ts_ms": int(time.time() * 1000),
            "source": "runtime_returns",
            "quality": "full",
            "pairwise_r": {"XRPUSDT": {"SOLUSDT": 0.91}},
            "sample_counts": {"XRPUSDT/SOLUSDT": 16},
        })
        intent = self._make_intent(symbol="XRPUSDT", direction="long")
        verdict = agent.review_intent(intent)
        self.assertEqual(verdict.result, RiskVerdictResult.REJECTED)
        self.assertIn("XRPUSDT", verdict.reason)
        self.assertIn("SOLUSDT", verdict.reason)
        correlation_review = verdict.metadata["correlation_review"]
        self.assertEqual(correlation_review["selected_pair"], "XRPUSDT/SOLUSDT")
        self.assertIn("correlation_hard_limit", correlation_review["reason_codes"])

    def test_btc_eth_without_dynamic_matrix_uses_safe_fallback_not_static_reject(self):
        """BTC/ETH static pair alone cannot create hard correlation rejection."""
        config = GuardianConfig(max_correlation=0.8)
        agent = GuardianAgent(config=config)
        agent.start()
        agent.update_active_positions({
            "s1:BTCUSDT": {"symbol": "BTCUSDT", "side": "Buy"},
        })
        intent = self._make_intent(symbol="ETHUSDT", direction="long", size=0.2)
        verdict = agent.review_intent(intent)
        self.assertEqual(verdict.result, RiskVerdictResult.MODIFIED)
        self.assertIn("correlation_data_insufficient", verdict.reason)
        self.assertAlmostEqual(verdict.modified_params["size"], 0.1)
        correlation_review = verdict.metadata["correlation_review"]
        self.assertEqual(correlation_review["quality"], "insufficient")
        self.assertIn("correlation_safe_fallback_size_cap", correlation_review["reason_codes"])

    def test_soft_dynamic_correlation_modifies_size(self):
        """Soft dynamic correlation produces MODIFIED rather than hard rejection."""
        config = GuardianConfig(max_correlation=0.8, soft_correlation=0.55)
        agent = GuardianAgent(config=config)
        agent.start()
        agent.update_active_positions({
            "s1:SOLUSDT": {"symbol": "SOLUSDT", "side": "Buy"},
        })
        agent.update_correlation_snapshot({
            "snapshot_id": "corr-unit-soft",
            "ts_ms": int(time.time() * 1000),
            "source": "runtime_returns",
            "quality": "full",
            "pairwise_r": {"XRPUSDT": {"SOLUSDT": 0.62}},
            "sample_counts": {"XRPUSDT/SOLUSDT": 20},
        })
        intent = self._make_intent(symbol="XRPUSDT", direction="long", size=0.2)
        verdict = agent.review_intent(intent)
        self.assertEqual(verdict.result, RiskVerdictResult.MODIFIED)
        self.assertIn("Correlation soft limit", verdict.reason)
        self.assertEqual(verdict.modified_params["correlation_action"], "soft_limit_size_cap")
        correlation_review = verdict.metadata["correlation_review"]
        self.assertEqual(correlation_review["selected_pair"], "XRPUSDT/SOLUSDT")
        self.assertIn("correlation_soft_limit", correlation_review["reason_codes"])

    def test_missing_matrix_without_same_direction_records_insufficient_metadata(self):
        """Missing matrix without same-direction exposure remains pass but records evidence."""
        agent = GuardianAgent(config=GuardianConfig())
        agent.start()
        intent = self._make_intent(symbol="ADAUSDT", direction="long")
        verdict = agent.review_intent(intent)
        self.assertEqual(verdict.result, RiskVerdictResult.APPROVED)
        correlation_review = verdict.metadata["correlation_review"]
        self.assertEqual(correlation_review["quality"], "insufficient")
        self.assertIn("correlation_data_insufficient", correlation_review["reason_codes"])
        self.assertEqual(correlation_review["same_direction_symbols"], [])

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
        correlation_review = verdict.metadata["correlation_review"]
        self.assertEqual(correlation_review["hedge_symbols"], ["BTCUSDT"])
        self.assertIn("correlation_hedge_evidence", correlation_review["reason_codes"])

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

    def test_soft_strategy_drawdown_modifies_size_leverage_stop_cooldown(self):
        """Soft strategy drawdown emits bounded P2 modification output."""
        config = GuardianConfig()
        agent = GuardianAgent(config=config)
        agent.start()
        agent.update_strategy_risk_snapshot({
            "snapshot_id": "strategy-risk-soft-1",
            "ts_ms": int(time.time() * 1000),
            "engine_mode": "paper",
            "strategy": "test",
            "sample_count": 12,
            "current_drawdown_bps": 180.0,
            "max_drawdown_bps": 190.0,
            "consecutive_losses": 3,
            "loss_rate": 0.5,
            "quality": "full",
            "evidence_refs": ["execution_report:soft-1"],
        })
        intent = self._make_intent(size=0.4, leverage=3.0)
        intent.params["stop_loss_bps"] = 120.0

        verdict = agent.review_intent(intent)

        self.assertEqual(verdict.result, RiskVerdictResult.MODIFIED)
        self.assertIn("Strategy risk modified", verdict.reason)
        self.assertAlmostEqual(verdict.modified_params["size"], 0.2)
        self.assertEqual(verdict.modified_params["leverage"], config.modification_leverage_cap)
        self.assertEqual(verdict.modified_params["stop_loss_bps"], config.p2_stop_loss_bps_cap)
        self.assertEqual(verdict.modified_params["cooldown_ms"], config.p2_cooldown_ms)
        fields = {item["field"]: item for item in verdict.p2_modifications}
        self.assertEqual(set(fields), {"size", "leverage", "stop", "cooldown"})
        self.assertNotIn("symbol", fields["size"])
        self.assertNotIn("direction", fields["size"])
        self.assertIn(
            "strategy_soft_drawdown",
            verdict.metadata["strategy_risk_review"]["reason_codes"],
        )

    def test_hard_strategy_drawdown_rejects_and_requests_position_review_not_close(self):
        """Hard strategy risk pauses new opens and requests review, not direct close."""
        config = GuardianConfig()
        agent = GuardianAgent(config=config)
        agent.start()
        agent.update_active_positions({
            "pos1": {"symbol": "BTCUSDT", "side": "Buy", "strategy": "test", "size": 0.1},
        })
        agent.update_strategy_risk_snapshot({
            "snapshot_id": "strategy-risk-hard-1",
            "ts_ms": int(time.time() * 1000),
            "engine_mode": "paper",
            "strategy": "test",
            "sample_count": 15,
            "current_drawdown_bps": 325.0,
            "max_drawdown_bps": 330.0,
            "consecutive_losses": 5,
            "loss_rate": 0.7,
            "quality": "full",
            "evidence_refs": ["execution_report:hard-1"],
        })

        verdict = agent.review_intent(self._make_intent(symbol="BTCUSDT", direction="long"))

        self.assertEqual(verdict.result, RiskVerdictResult.REJECTED)
        self.assertIn("Strategy risk pause", verdict.reason)
        review = verdict.metadata["strategy_risk_review"]
        self.assertEqual(review["state"], "pause_new_entries")
        self.assertTrue(review["position_review_requested"])
        self.assertIn("position_review_requested", review["reason_codes"])
        self.assertNotIn("close", verdict.modified_params)
        self.assertEqual(verdict.p2_modifications, [])


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

    def test_high_event_tightens_next_matching_intent_without_ordering(self):
        """High Scout event modifies risk for matching symbols without direct order authority."""
        config = GuardianConfig()
        agent = GuardianAgent(config=config)
        agent.start()
        msg = AgentMessage(
            sender=AgentRole.SCOUT,
            receiver=AgentRole.GUARDIAN,
            message_type=MessageType.EVENT_ALERT,
            payload={"event_type": "fomc", "severity": "high", "affected_symbols": ["BTCUSDT"]},
        )
        agent.on_message(msg)

        intent = TradeIntent(
            symbol="BTCUSDT",
            strategy="test",
            direction="long",
            size=0.4,
            params={"leverage": 1.0},
            confidence=0.7,
        )
        verdict = agent.review_intent(intent)

        self.assertEqual(verdict.result, RiskVerdictResult.MODIFIED)
        self.assertIn("Event/scanner risk modified", verdict.reason)
        self.assertAlmostEqual(verdict.modified_params["size"], 0.2)
        fields = {item["field"] for item in verdict.p2_modifications}
        self.assertEqual(fields, {"size", "cooldown"})
        review = verdict.metadata["risk_evidence_review"]
        self.assertIn("event_high_risk", review["reason_codes"])
        self.assertNotIn("close", verdict.modified_params)

    def test_scanner_risk_evidence_tightens_without_symbol_direction_change(self):
        """Scanner risk evidence can tighten risk without changing trade authority."""
        agent = GuardianAgent(config=GuardianConfig())
        agent.start()
        intent = TradeIntent(
            symbol="SOLUSDT",
            strategy="grid_trading",
            direction="long",
            size=0.3,
            params={"leverage": 1.0},
            confidence=0.7,
            metadata={
                "scanner_risk_evidence": {
                    "source": "scanner_crowding",
                    "symbol": "SOLUSDT",
                    "risk_score": 0.72,
                    "reason_codes": ["scanner_crowding_high"],
                }
            },
        )

        verdict = agent.review_intent(intent)

        self.assertEqual(verdict.result, RiskVerdictResult.MODIFIED)
        self.assertEqual(verdict.modified_params["risk_evidence_action"], "event_scanner_risk_p2_modify")
        review = verdict.metadata["risk_evidence_review"]
        self.assertIn("scanner_soft_risk", review["reason_codes"])
        self.assertIn("scanner_crowding_high", review["reason_codes"])
        for modification in verdict.p2_modifications:
            self.assertNotIn("symbol", modification)
            self.assertNotIn("direction", modification)

    def test_scanner_risk_pattern_can_pause_new_open_without_direct_close(self):
        """Critical scanner risk pattern rejects new opens but does not direct close."""
        agent = GuardianAgent(config=GuardianConfig())
        agent.start()
        agent.on_message(AgentMessage(
            sender=AgentRole.ANALYST,
            receiver=AgentRole.GUARDIAN,
            message_type=MessageType.RISK_PATTERN,
            payload={
                "source": "scanner_decay",
                "risk_level": "critical",
                "symbols": ["XRPUSDT"],
                "reason_codes": ["scanner_decay_requires_review"],
            },
        ))
        verdict = agent.review_intent(TradeIntent(
            symbol="XRPUSDT",
            strategy="grid_trading",
            direction="long",
            size=0.2,
            params={"leverage": 1.0},
            confidence=0.7,
        ))

        self.assertEqual(verdict.result, RiskVerdictResult.REJECTED)
        self.assertIn("Event/scanner risk pause", verdict.reason)
        self.assertEqual(verdict.p2_modifications, [])
        self.assertNotIn("close", verdict.modified_params)
        self.assertIn(
            "scanner_hard_risk",
            verdict.metadata["risk_evidence_review"]["reason_codes"],
        )

    def test_analyst_risk_pattern_tightens_p2_without_scope_authority(self):
        """Analyst L2 risk patterns can P2-tighten without symbol/direction authority."""
        agent = GuardianAgent(config=GuardianConfig())
        agent.start()
        agent.on_message(AgentMessage(
            sender=AgentRole.ANALYST,
            receiver=AgentRole.GUARDIAN,
            message_type=MessageType.RISK_PATTERN,
            payload={
                "insight_id": "insight-l2-grid-risk-1",
                "analyst_tier": "l2",
                "insight_type": "risk_pattern",
                "insight_level": "inference",
                "symbol": "ADAUSDT",
                "strategy": "grid_trading",
                "confidence": 0.78,
                "reason_codes": ["analyst_grid_drawdown_cluster"],
                "evidence_refs": ["roundtrip-ada-grid-loss-window"],
            },
        ))

        verdict = agent.review_intent(TradeIntent(
            symbol="ADAUSDT",
            strategy="grid_trading",
            direction="long",
            size=0.4,
            params={"leverage": 1.0},
            confidence=0.7,
        ))

        self.assertEqual(verdict.result, RiskVerdictResult.MODIFIED)
        self.assertIn("Event/scanner risk modified", verdict.reason)
        self.assertAlmostEqual(verdict.modified_params["size"], 0.2)
        self.assertEqual(
            verdict.modified_params["risk_evidence_action"],
            "event_scanner_risk_p2_modify",
        )
        fields = {item["field"] for item in verdict.p2_modifications}
        self.assertEqual(fields, {"size", "cooldown"})
        for modification in verdict.p2_modifications:
            self.assertNotIn("symbol", modification)
            self.assertNotIn("direction", modification)
        review = verdict.metadata["risk_evidence_review"]
        self.assertIn("risk_pattern_soft_risk", review["reason_codes"])
        self.assertIn("analyst_grid_drawdown_cluster", review["reason_codes"])
        evidence = review["scanner_risk_evidence"][0]
        self.assertEqual(evidence["insight_id"], "insight-l2-grid-risk-1")
        self.assertEqual(evidence["analyst_tier"], "l2")
        self.assertEqual(evidence["insight_type"], "risk_pattern")
        self.assertEqual(evidence["evidence_refs"], ["roundtrip-ada-grid-loss-window"])

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


# ── G3-08 Phase 4 Sub-task 4-2: Guardian agent_state snapshot ──
# G3-08 Phase 4 Sub-task 4-2：Guardian agent 狀態 snapshot


class TestGuardianAgentStateSnapshot(unittest.TestCase):
    """G3-08 Phase 4 Sub-task 4-2: get_guardian_snapshot() schema + thread safety.

    PA RFC §2.2 — 8 fields, all int / bool→int (Rust HashMap<String, i64> parity).
    PA RFC §2.2 — 8 欄位、皆 int / bool→int（Rust HashMap<String, i64> 對齊）。
    """

    _EXPECTED_FIELDS = {
        "intents_reviewed",
        "verdicts_approved",
        "verdicts_rejected",
        "verdicts_modified",
        "events_assessed",
        "errors",
        "active_event_risks",
        "verdict_log_size",
    }

    def _make_intent(self, symbol="BTCUSDT", direction="long", size=0.01, leverage=1.0):
        return TradeIntent(
            symbol=symbol,
            strategy="test",
            direction=direction,
            size=size,
            params={"leverage": leverage},
            confidence=0.7,
        )

    def test_snapshot_zero_initial_state(self):
        """Fresh GuardianAgent → all 8 fields present, all 0."""
        agent = GuardianAgent()
        snap = agent.get_guardian_snapshot()
        self.assertEqual(set(snap.keys()), self._EXPECTED_FIELDS)
        for k, v in snap.items():
            self.assertIsInstance(v, int, f"{k} must be int")
            self.assertEqual(v, 0, f"{k} must be 0 on fresh agent")

    def test_snapshot_after_approved_review(self):
        """APPROVED review increments intents_reviewed + verdicts_approved."""
        agent = GuardianAgent(config=GuardianConfig())
        agent.start()
        verdict = agent.review_intent(self._make_intent())
        self.assertEqual(verdict.result, RiskVerdictResult.APPROVED)
        snap = agent.get_guardian_snapshot()
        self.assertEqual(snap["intents_reviewed"], 1)
        self.assertEqual(snap["verdicts_approved"], 1)
        self.assertEqual(snap["verdicts_rejected"], 0)
        self.assertEqual(snap["verdicts_modified"], 0)
        self.assertEqual(snap["events_assessed"], 0)
        self.assertEqual(snap["active_event_risks"], 0)
        # verdict_log_size grew to 1.
        self.assertEqual(snap["verdict_log_size"], 1)

    def test_snapshot_after_rejected_review(self):
        """REJECTED review increments verdicts_rejected (direction conflict)."""
        agent = GuardianAgent(config=GuardianConfig())
        agent.start()
        agent.update_active_positions({
            "test:BTCUSDT": {"symbol": "BTCUSDT", "side": "Sell"},
        })
        verdict = agent.review_intent(self._make_intent(direction="long"))
        self.assertEqual(verdict.result, RiskVerdictResult.REJECTED)
        snap = agent.get_guardian_snapshot()
        self.assertEqual(snap["intents_reviewed"], 1)
        self.assertEqual(snap["verdicts_rejected"], 1)
        self.assertEqual(snap["verdicts_approved"], 0)
        self.assertEqual(snap["verdict_log_size"], 1)

    def test_snapshot_after_modified_review(self):
        """MODIFIED review (over-leverage but not 2x cap) increments verdicts_modified."""
        agent = GuardianAgent(config=GuardianConfig(max_leverage=5.0))
        agent.start()
        # leverage 7 > 5 cap but ≤ 5*2=10 → MODIFIED, not REJECTED.
        verdict = agent.review_intent(self._make_intent(leverage=7.0))
        self.assertEqual(verdict.result, RiskVerdictResult.MODIFIED)
        snap = agent.get_guardian_snapshot()
        self.assertEqual(snap["intents_reviewed"], 1)
        self.assertEqual(snap["verdicts_modified"], 1)

    def test_snapshot_active_event_risks_gauge(self):
        """active_event_risks tracks len(self._active_event_risks) gauge."""
        agent = GuardianAgent(config=GuardianConfig())
        agent.start()
        # Inject event risks directly.
        agent._active_event_risks = [{"event_type": "x"}, {"event_type": "y"}]
        snap = agent.get_guardian_snapshot()
        self.assertEqual(snap["active_event_risks"], 2)

    def test_snapshot_all_int_phase4_invariant(self):
        """Phase 4 invariant: all values must be int (no float / str / bool)."""
        agent = GuardianAgent(config=GuardianConfig())
        agent.start()
        agent.review_intent(self._make_intent())
        snap = agent.get_guardian_snapshot()
        for k, v in snap.items():
            self.assertIsInstance(v, int, f"{k}={v!r} must be int (Phase 4 invariant)")
            # bool is a subclass of int in Python — make sure bools aren't leaking.
            self.assertNotIsInstance(v, bool, f"{k}={v!r} must NOT be bool (cast to int)")

    def test_snapshot_thread_safety_acquires_lock(self):
        """get_guardian_snapshot must acquire self._lock — assert by inspecting
        that the call returns a dict snapshot even while another thread is
        actively mutating _stats. Pragmatic smoke (not a full race assertion).
        """
        import threading
        agent = GuardianAgent(config=GuardianConfig())
        agent.start()
        stop_flag = threading.Event()

        def hammer():
            while not stop_flag.is_set():
                with agent._lock:
                    agent._stats["intents_reviewed"] = agent._stats.get(
                        "intents_reviewed", 0
                    ) + 1

        t = threading.Thread(target=hammer, daemon=True)
        t.start()
        try:
            for _ in range(50):
                snap = agent.get_guardian_snapshot()
                self.assertEqual(set(snap.keys()), self._EXPECTED_FIELDS)
                self.assertIsInstance(snap["intents_reviewed"], int)
        finally:
            stop_flag.set()
            t.join(timeout=2.0)


if __name__ == "__main__":
    unittest.main()
