"""
ExecutorAgent Unit Tests — Order wrapping, execution quality metrics, error handling
======================================================================================
12 tests covering:
- Order execution via PaperTradingEngine mock
- Execution quality (slippage, fill time)
- Error handling and fail-closed behavior
- Conditional order callback (Batch 11 stub)
- Message handling
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
from app.executor_agent import (
    ExecutionReport,
    ExecutorAgent,
    ExecutorConfig,
)


class TestExecutorLifecycle(unittest.TestCase):

    def test_creation(self):
        agent = ExecutorAgent()
        self.assertEqual(agent.state, AgentState.INITIALIZING)
        stats = agent.get_stats()
        self.assertEqual(stats["role"], "executor")

    def test_start_stop(self):
        agent = ExecutorAgent()
        agent.start()
        self.assertEqual(agent.state, AgentState.RUNNING)
        agent.stop()
        self.assertEqual(agent.state, AgentState.STOPPED)


class TestExecutorExecution(unittest.TestCase):
    """Test order execution."""

    def _make_engine(self, reject=False, fill_price=60100.0):
        """Create a mock PaperTradingEngine."""
        engine = MagicMock()
        if reject:
            engine.submit_order.return_value = {
                "order": {},
                "fills": [],
                "rejected_reason": "risk_limit_exceeded",
                "close_pnl": 0.0,
            }
        else:
            engine.submit_order.return_value = {
                "order": {
                    "avg_fill_price": fill_price,
                    "filled_qty": 0.01,
                },
                "fills": [],
                "rejected_reason": None,
                "close_pnl": 0.0,
            }
        return engine

    def test_successful_execution(self):
        """Successful order execution produces report with metrics."""
        engine = self._make_engine(fill_price=60100.0)
        agent = ExecutorAgent(paper_engine=engine)
        agent.start()
        agent.update_market_prices({"BTCUSDT": 60000.0})

        report = agent.execute_order(
            intent_id="i1",
            symbol="BTCUSDT",
            side="Buy",
            qty=0.01,
        )
        self.assertTrue(report.success)
        self.assertEqual(report.filled_qty, 0.01)
        self.assertEqual(report.actual_price, 60100.0)
        self.assertGreater(report.slippage_bps, 0)
        self.assertGreater(report.fill_time_ms, 0)

        stats = agent.get_stats()
        self.assertEqual(stats["executions_success"], 1)

    def test_rejected_order(self):
        """Rejected order produces failed report."""
        engine = self._make_engine(reject=True)
        agent = ExecutorAgent(paper_engine=engine)
        agent.start()

        report = agent.execute_order(
            intent_id="i2",
            symbol="BTCUSDT",
            side="Buy",
            qty=0.01,
        )
        self.assertFalse(report.success)
        self.assertIn("rejected", report.error)
        stats = agent.get_stats()
        self.assertEqual(stats["executions_failed"], 1)

    def test_no_engine_fails(self):
        """No paper engine → fail-closed report."""
        agent = ExecutorAgent()
        agent.start()
        report = agent.execute_order(
            intent_id="i3",
            symbol="BTCUSDT",
            side="Buy",
            qty=0.01,
        )
        self.assertFalse(report.success)
        self.assertIn("No paper engine", report.error)

    def test_engine_exception_handled(self):
        """Engine exception produces failed report, doesn't crash."""
        engine = MagicMock()
        engine.submit_order.side_effect = RuntimeError("Engine internal error")

        agent = ExecutorAgent(paper_engine=engine)
        agent.start()
        report = agent.execute_order(
            intent_id="i4",
            symbol="BTCUSDT",
            side="Buy",
            qty=0.01,
        )
        self.assertFalse(report.success)
        self.assertIn("error", report.error.lower())
        stats = agent.get_stats()
        self.assertGreater(stats["errors"], 0)

    def test_slippage_calculation(self):
        """Slippage calculated correctly in basis points."""
        engine = self._make_engine(fill_price=60060.0)  # $60 slip on $60000
        agent = ExecutorAgent(paper_engine=engine)
        agent.start()
        agent.update_market_prices({"BTCUSDT": 60000.0})

        report = agent.execute_order(
            intent_id="i5",
            symbol="BTCUSDT",
            side="Buy",
            qty=0.01,
        )
        # 60/60000 * 10000 = 10 bps
        self.assertAlmostEqual(report.slippage_bps, 10.0, places=0)

    def test_conditional_order_callback(self):
        """Conditional order callback triggered on success."""
        engine = self._make_engine(fill_price=60000.0)
        callback = MagicMock()

        agent = ExecutorAgent(paper_engine=engine)
        agent.start()
        agent.set_conditional_order_callback(callback)
        agent.update_market_prices({"BTCUSDT": 60000.0})

        agent.execute_order(
            intent_id="i6",
            symbol="BTCUSDT",
            side="Buy",
            qty=0.01,
        )
        callback.assert_called_once_with("BTCUSDT", "Buy", 60000.0, 0.01)

    def test_conditional_callback_not_on_failure(self):
        """Conditional order callback NOT triggered on failed execution."""
        engine = self._make_engine(reject=True)
        callback = MagicMock()

        agent = ExecutorAgent(paper_engine=engine)
        agent.start()
        agent.set_conditional_order_callback(callback)

        agent.execute_order(
            intent_id="i7",
            symbol="BTCUSDT",
            side="Buy",
            qty=0.01,
        )
        callback.assert_not_called()


class TestExecutorMessageHandling(unittest.TestCase):
    """Test message-based execution."""

    def test_approved_intent_handled(self):
        """APPROVED_INTENT message triggers execution."""
        engine = MagicMock()
        engine.submit_order.return_value = {
            "order": {"avg_fill_price": 60000.0, "filled_qty": 0.01},
            "fills": [],
            "rejected_reason": None,
        }

        bus = MessageBus()
        agent = ExecutorAgent(paper_engine=engine, message_bus=bus)
        agent.start()

        msg = AgentMessage(
            sender=AgentRole.STRATEGIST,
            receiver=AgentRole.EXECUTOR,
            message_type=MessageType.APPROVED_INTENT,
            payload={
                "intent_id": "i8",
                "symbol": "BTCUSDT",
                "direction": "long",
                "size": 0.01,
            },
        )
        agent.on_message(msg)
        engine.submit_order.assert_called_once()

    def test_invalid_intent_ignored(self):
        """Invalid intent (missing fields) doesn't crash."""
        engine = MagicMock()
        agent = ExecutorAgent(paper_engine=engine)
        agent.start()

        msg = AgentMessage(
            sender=AgentRole.STRATEGIST,
            receiver=AgentRole.EXECUTOR,
            message_type=MessageType.APPROVED_INTENT,
            payload={"intent_id": "i9"},  # missing symbol, direction, size
        )
        agent.on_message(msg)
        engine.submit_order.assert_not_called()

    def test_execution_report_sent_to_analyst(self):
        """Execution report sent to Analyst via bus."""
        engine = MagicMock()
        engine.submit_order.return_value = {
            "order": {"avg_fill_price": 60000.0, "filled_qty": 0.01},
            "fills": [],
            "rejected_reason": None,
        }

        bus = MessageBus()
        received = []
        bus.subscribe(AgentRole.ANALYST, lambda m: received.append(m))

        agent = ExecutorAgent(paper_engine=engine, message_bus=bus)
        agent.start()

        msg = AgentMessage(
            sender=AgentRole.STRATEGIST,
            receiver=AgentRole.EXECUTOR,
            message_type=MessageType.APPROVED_INTENT,
            payload={
                "intent_id": "i10",
                "symbol": "BTCUSDT",
                "direction": "long",
                "size": 0.01,
            },
        )
        agent.on_message(msg)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].message_type, MessageType.EXECUTION_REPORT)

    def test_recent_reports(self):
        """Recent reports are queryable."""
        engine = MagicMock()
        engine.submit_order.return_value = {
            "order": {"avg_fill_price": 60000.0, "filled_qty": 0.01},
            "fills": [],
            "rejected_reason": None,
        }
        agent = ExecutorAgent(paper_engine=engine)
        agent.start()
        for i in range(5):
            agent.execute_order(intent_id=f"i_{i}", symbol="BTCUSDT", side="Buy", qty=0.01)
        reports = agent.get_recent_reports(limit=3)
        self.assertEqual(len(reports), 3)


class TestExecutionReport(unittest.TestCase):
    """Test ExecutionReport data structure."""

    def test_report_to_dict(self):
        report = ExecutionReport(
            intent_id="test",
            symbol="BTCUSDT",
            side="Buy",
            requested_qty=0.01,
            filled_qty=0.01,
            expected_price=60000.0,
            actual_price=60010.0,
            slippage_bps=1.67,
            fill_time_ms=5.5,
            success=True,
        )
        d = report.to_dict()
        self.assertEqual(d["symbol"], "BTCUSDT")
        self.assertEqual(d["slippage_bps"], 1.67)
        self.assertTrue(d["success"])


if __name__ == "__main__":
    unittest.main()
