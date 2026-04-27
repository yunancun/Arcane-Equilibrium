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
from unittest.mock import MagicMock, patch

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

    def test_no_engine_ipc_shadow(self):
        """R-06-v2: No paper engine → IPC shadow bridge activates."""
        agent = ExecutorAgent()
        agent.start()
        report = agent.execute_order(
            intent_id="i3",
            symbol="BTCUSDT",
            side="Buy",
            qty=0.01,
        )
        self.assertTrue(report.success)
        self.assertEqual(report.error, "shadow_mode")
        self.assertEqual(report.metadata.get("execution_path"), "ipc_shadow")

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
        # A5 fix: error message is now generic to prevent exception string leak
        self.assertIn("failed", report.error.lower())
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


# ═══════════════════════════════════════════════════════════════════════════════
# G3-08 Phase 4 Sub-task 4-4 — Executor agent_state snapshot + invalidate hooks
# ═══════════════════════════════════════════════════════════════════════════════


class TestExecutorSnapshot(unittest.TestCase):
    """G3-08 Phase 4 Sub-task 4-4: verify get_executor_snapshot() returns
    9-field dict per PA RFC §2.4, schema-parity with Rust
    ``AgentState.stats: HashMap<String, i64>``.

    G3-08 Phase 4 Sub-task 4-4：驗證 get_executor_snapshot() 回傳 9-field
    dict（PA RFC §2.4），schema 對齊 Rust ``AgentState.stats``。
    """

    _EXPECTED_FIELDS = {
        "intents_received",
        "intents_deduped",
        "executions_attempted",
        "executions_success",
        "executions_failed",
        "total_slippage_bps",
        "errors",
        "recent_intent_id_size",
        "shadow_mode",
    }

    def _make_agent(self, shadow_provider=None) -> ExecutorAgent:
        """Minimal ExecutorAgent for snapshot tests / 給 snapshot 測試用的最小 agent."""
        return ExecutorAgent(shadow_mode_provider=shadow_provider)

    def test_get_executor_snapshot_initial_state(self):
        """Fresh agent -> all 9 keys present; counter values 0; shadow_mode
        defaults to 1 (provider absent -> fail-closed lambda returns True).
        新建 agent -> 9 keys 全在；counter 為 0；shadow_mode 預設 1。"""
        agent = self._make_agent()
        snap = agent.get_executor_snapshot()
        self.assertEqual(set(snap.keys()), self._EXPECTED_FIELDS)
        for key in self._EXPECTED_FIELDS:
            self.assertIsInstance(snap[key], int, f"{key} must be int")
        self.assertEqual(snap["intents_received"], 0)
        self.assertEqual(snap["executions_attempted"], 0)
        self.assertEqual(snap["recent_intent_id_size"], 0)
        # Default fail-closed provider returns True -> shadow_mode=1.
        self.assertEqual(snap["shadow_mode"], 1)

    def test_get_executor_snapshot_independent_dicts(self):
        """Multiple calls return independent dict objects (no aliasing).
        多次呼叫回獨立 dict（無別名）。"""
        agent = self._make_agent()
        a = agent.get_executor_snapshot()
        b = agent.get_executor_snapshot()
        self.assertIsNot(a, b)
        a["intents_received"] = 999
        self.assertEqual(b["intents_received"], 0)

    def test_get_executor_snapshot_reflects_stats(self):
        """Counters in self._stats must reflect in snapshot output.
        self._stats 中的計數器必須反映於 snapshot 輸出。"""
        agent = self._make_agent()
        with agent._lock:
            agent._stats["intents_received"] = 11
            agent._stats["intents_deduped"] = 1
            agent._stats["executions_attempted"] = 8
            agent._stats["executions_success"] = 6
            agent._stats["executions_failed"] = 2
            # total_slippage_bps stored as float -- snapshot must cast to int.
            agent._stats["total_slippage_bps"] = 47.93
            agent._stats["errors"] = 1
        snap = agent.get_executor_snapshot()
        self.assertEqual(snap["intents_received"], 11)
        self.assertEqual(snap["intents_deduped"], 1)
        self.assertEqual(snap["executions_attempted"], 8)
        self.assertEqual(snap["executions_success"], 6)
        self.assertEqual(snap["executions_failed"], 2)
        self.assertEqual(snap["errors"], 1)
        # Float->int cast (Phase 4 invariant: HashMap<String, i64>).
        self.assertEqual(snap["total_slippage_bps"], 47)
        self.assertIsInstance(snap["total_slippage_bps"], int)

    def test_get_executor_snapshot_recent_intent_id_size(self):
        """recent_intent_id_size reflects len(self._recent_intent_ids).
        recent_intent_id_size 反映 len(self._recent_intent_ids)。"""
        agent = self._make_agent()
        agent._recent_intent_ids["i_a"] = time.time()
        agent._recent_intent_ids["i_b"] = time.time()
        agent._recent_intent_ids["i_c"] = time.time()
        snap = agent.get_executor_snapshot()
        self.assertEqual(snap["recent_intent_id_size"], 3)

    def test_get_executor_snapshot_shadow_mode_true(self):
        """shadow_mode_provider returns True -> snapshot["shadow_mode"]=1.
        shadow_mode_provider 回 True -> snapshot 為 1。"""
        agent = self._make_agent(shadow_provider=lambda: True)
        snap = agent.get_executor_snapshot()
        self.assertEqual(snap["shadow_mode"], 1)
        self.assertIsInstance(snap["shadow_mode"], int)

    def test_get_executor_snapshot_shadow_mode_false(self):
        """shadow_mode_provider returns False -> snapshot["shadow_mode"]=0.
        shadow_mode_provider 回 False -> snapshot 為 0。"""
        agent = self._make_agent(shadow_provider=lambda: False)
        snap = agent.get_executor_snapshot()
        self.assertEqual(snap["shadow_mode"], 0)
        self.assertIsInstance(snap["shadow_mode"], int)

    def test_get_executor_snapshot_shadow_provider_raises_fail_closed(self):
        """shadow_mode_provider raises -> snapshot["shadow_mode"]=1
        (fail-closed per CLAUDE.md §二 原則 #6).
        provider 拋例外 -> snapshot 為 1（fail-closed，CLAUDE.md §二 原則 #6）。
        """
        def _raises():
            raise RuntimeError("provider boom")
        agent = self._make_agent(shadow_provider=_raises)
        snap = agent.get_executor_snapshot()
        self.assertEqual(snap["shadow_mode"], 1)
        self.assertIsInstance(snap["shadow_mode"], int)

    def test_invalidate_hook_present_on_success_path(self):
        """G3-08 Phase 4 Sub-task 4-4: _handle_approved_intent must invoke
        _invalidate_h_state_async("agent.executor.execution_complete") when
        execute_order returns a successful report.
        G3-08 Phase 4 Sub-task 4-4：execute_order 成功時須呼叫
        _invalidate_h_state_async("agent.executor.execution_complete")。
        """
        engine = MagicMock()
        engine.submit_order.return_value = {
            "order": {"avg_fill_price": 60000.0, "filled_qty": 0.01},
            "fills": [],
            "rejected_reason": None,
        }
        agent = ExecutorAgent(paper_engine=engine)
        agent.start()
        msg = AgentMessage(
            sender=AgentRole.STRATEGIST,
            receiver=AgentRole.EXECUTOR,
            message_type=MessageType.APPROVED_INTENT,
            payload={
                "intent_id": "i-success",
                "symbol": "BTCUSDT",
                "direction": "long",
                "size": 0.01,
            },
        )
        with patch("app.executor_agent._invalidate_h_state_async") as mock_inv:
            agent.on_message(msg)
        called_reasons = [c.args[0] for c in mock_inv.call_args_list if c.args]
        self.assertIn(
            "agent.executor.execution_complete", called_reasons,
            "Expected agent.executor.execution_complete hint after success",
        )

    def test_invalidate_hook_present_on_failure_path(self):
        """G3-08 Phase 4 Sub-task 4-4: _handle_approved_intent must invoke
        _invalidate_h_state_async("agent.executor.execution_failed") when
        execute_order returns a failed report (e.g. paper engine rejects).
        G3-08 Phase 4 Sub-task 4-4：execute_order 失敗時須呼叫
        _invalidate_h_state_async("agent.executor.execution_failed")。
        """
        engine = MagicMock()
        engine.submit_order.return_value = {
            "order": {},
            "fills": [],
            "rejected_reason": "risk_limit_exceeded",
        }
        agent = ExecutorAgent(paper_engine=engine)
        agent.start()
        msg = AgentMessage(
            sender=AgentRole.STRATEGIST,
            receiver=AgentRole.EXECUTOR,
            message_type=MessageType.APPROVED_INTENT,
            payload={
                "intent_id": "i-fail",
                "symbol": "BTCUSDT",
                "direction": "long",
                "size": 0.01,
            },
        )
        with patch("app.executor_agent._invalidate_h_state_async") as mock_inv:
            agent.on_message(msg)
        called_reasons = [c.args[0] for c in mock_inv.call_args_list if c.args]
        self.assertIn(
            "agent.executor.execution_failed", called_reasons,
            "Expected agent.executor.execution_failed hint after failure",
        )


if __name__ == "__main__":
    unittest.main()
