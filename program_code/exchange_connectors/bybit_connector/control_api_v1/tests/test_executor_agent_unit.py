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


class TestExecutorShadowProviderContract(unittest.TestCase):

    def test_executor_agent_has_no_unconditional_lambda_true_fallback(self):
        """F-01: ExecutorAgent source must not hide provider absence behind lambda True."""
        source_path = os.path.join(_control_api_dir, "app", "executor_agent.py")
        with open(source_path, encoding="utf-8") as handle:
            source = handle.read()

        self.assertNotIn("lambda: True", source)
        self.assertIn("self._shadow_mode_provider: Optional", source)
        self.assertIn("shadow_mode_provider unavailable", source)


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
        self.assertEqual(report.metadata.get("execution_engine"), "paper")

    def test_no_engine_missing_provider_fail_closed_no_ipc_submit(self):
        """F-01: missing provider is explicit fail-closed, not an implicit callable fallback."""
        agent = ExecutorAgent()
        agent.start()
        report = agent.execute_order(
            intent_id="i3_missing_provider",
            symbol="BTCUSDT",
            side="Buy",
            qty=0.01,
            metadata={"engine": "demo"},
        )
        self.assertTrue(report.success)
        self.assertEqual(report.error, "shadow_mode")
        self.assertEqual(report.metadata.get("execution_path"), "ipc_shadow")
        self.assertEqual(report.metadata.get("execution_engine"), "demo")

    def test_no_engine_provider_failure_fail_closed_no_ipc_submit(self):
        """F-01: provider exception must fail closed before IPC submit authority."""
        def _raises(_engine):
            raise RuntimeError("provider boom")

        agent = ExecutorAgent(shadow_mode_provider=_raises)
        agent.start()
        report = agent.execute_order(
            intent_id="i3_provider_fail",
            symbol="BTCUSDT",
            side="Buy",
            qty=0.01,
            metadata={"engine": "live"},
        )
        self.assertTrue(report.success)
        self.assertEqual(report.error, "shadow_mode")
        self.assertEqual(report.metadata.get("execution_path"), "ipc_shadow")
        self.assertEqual(report.metadata.get("execution_engine"), "live")

    def test_no_engine_shadow_provider_receives_explicit_engine(self):
        """F-01: engine-aware providers are consulted with the resolved engine."""
        calls = []

        def _provider(engine):
            calls.append(engine)
            return True

        agent = ExecutorAgent(shadow_mode_provider=_provider)
        agent.start()
        report = agent.execute_order(
            intent_id="i3_engine_provider",
            symbol="BTCUSDT",
            side="Buy",
            qty=0.01,
            metadata={"engine": "demo"},
        )
        self.assertTrue(report.success)
        self.assertEqual(report.metadata.get("execution_path"), "ipc_shadow")
        self.assertEqual(calls, ["demo"])

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
        defaults to 1 (provider absent -> explicit fail-closed read).
        新建 agent -> 9 keys 全在；counter 為 0；shadow_mode 預設 1。"""
        agent = self._make_agent()
        snap = agent.get_executor_snapshot()
        self.assertEqual(set(snap.keys()), self._EXPECTED_FIELDS)
        for key in self._EXPECTED_FIELDS:
            self.assertIsInstance(snap[key], int, f"{key} must be int")
        self.assertEqual(snap["intents_received"], 0)
        self.assertEqual(snap["executions_attempted"], 0)
        self.assertEqual(snap["recent_intent_id_size"], 0)
        # Missing provider fail-closes to shadow_mode=1.
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

    def test_invalidate_hook_present_on_empty_intent_payload(self):
        agent = ExecutorAgent()
        agent.start()
        msg = AgentMessage(
            sender=AgentRole.STRATEGIST,
            receiver=AgentRole.EXECUTOR,
            message_type=MessageType.APPROVED_INTENT,
            payload={},
        )
        with patch("app.executor_agent._invalidate_h_state_async") as mock_inv:
            agent.on_message(msg)
        self.assertIn(
            "agent.executor.intent_empty",
            [c.args[0] for c in mock_inv.call_args_list if c.args],
        )

    def test_invalidate_hook_present_on_invalid_intent_payload(self):
        agent = ExecutorAgent()
        agent.start()
        msg = AgentMessage(
            sender=AgentRole.STRATEGIST,
            receiver=AgentRole.EXECUTOR,
            message_type=MessageType.APPROVED_INTENT,
            payload={"intent_id": "i-invalid", "symbol": "", "direction": "long", "size": 0},
        )
        with patch("app.executor_agent._invalidate_h_state_async") as mock_inv:
            agent.on_message(msg)
        self.assertIn(
            "agent.executor.intent_invalid",
            [c.args[0] for c in mock_inv.call_args_list if c.args],
        )

    def test_invalidate_hook_present_on_deduped_intent(self):
        agent = ExecutorAgent()
        agent.start()
        agent.execute_order = MagicMock(return_value=MagicMock(success=True))
        msg = AgentMessage(
            sender=AgentRole.STRATEGIST,
            receiver=AgentRole.EXECUTOR,
            message_type=MessageType.APPROVED_INTENT,
            payload={
                "intent_id": "i-dedup",
                "symbol": "BTCUSDT",
                "direction": "long",
                "size": 0.01,
            },
        )
        with patch("app.executor_agent._invalidate_h_state_async") as mock_inv:
            agent.on_message(msg)
            agent.on_message(msg)
        self.assertIn(
            "agent.executor.intent_deduped",
            [c.args[0] for c in mock_inv.call_args_list if c.args],
        )


# ═══════════════════════════════════════════════════════════════════════════════
# W-AUDIT-9 T3 — ExecutorAgent stage-aware shadow_mode 接線 unit tests
# AMD-2026-05-09-03 §2.1 / §2.2 + TODO v19 §5 invariant 9
# ═══════════════════════════════════════════════════════════════════════════════


class TestExecutorAgentCanaryStage(unittest.TestCase):
    """W-AUDIT-9 T3：ExecutorAgent ``canary_stage_provider`` 接線 + fail-closed。

    invariant 9（**critical**）：cache miss / IPC failure / schema fail /
    provider exception → Stage 0（**不是** Stage 1）。
    """

    def _import_canary_stage(self):
        """延遲匯入 CanaryStage 避免測試環境 import order 顧慮。"""
        from app.executor_config_cache import CanaryStage  # noqa: PLC0415
        return CanaryStage

    def test_canary_stage_provider_returns_stage_one(self):
        """provider 返 Stage 1 → _read_canary_stage 對應 + shadow_mode=False。"""
        CanaryStage = self._import_canary_stage()
        agent = ExecutorAgent(
            canary_stage_provider=lambda: CanaryStage.PAPER_SINGLE_COHORT,
        )
        self.assertEqual(agent._read_canary_stage(), CanaryStage.PAPER_SINGLE_COHORT)
        self.assertFalse(agent._read_shadow_mode())

    def test_canary_stage_provider_returns_stage_two(self):
        """Stage 2 → shadow_mode=False，stage 對齊。"""
        CanaryStage = self._import_canary_stage()
        agent = ExecutorAgent(
            canary_stage_provider=lambda: CanaryStage.DEMO_SINGLE_COHORT,
        )
        self.assertEqual(agent._read_canary_stage(), CanaryStage.DEMO_SINGLE_COHORT)
        self.assertFalse(agent._read_shadow_mode())

    def test_canary_stage_provider_returns_stage_zero_shadows_path(self):
        """Stage 0 → shadow_mode=True（legacy projection 不變）。"""
        CanaryStage = self._import_canary_stage()
        agent = ExecutorAgent(
            canary_stage_provider=lambda: CanaryStage.SHADOW,
        )
        self.assertEqual(agent._read_canary_stage(), CanaryStage.SHADOW)
        self.assertTrue(agent._read_shadow_mode())

    def test_canary_stage_provider_exception_fails_closed_stage_zero(self):
        """invariant 9：provider raise → Stage 0（**不是** Stage 1）。"""
        CanaryStage = self._import_canary_stage()

        def _boom():
            raise RuntimeError("provider explode")

        agent = ExecutorAgent(canary_stage_provider=_boom)
        self.assertEqual(agent._read_canary_stage(), CanaryStage.SHADOW)
        self.assertTrue(agent._read_shadow_mode())

    def test_canary_stage_provider_engine_aware(self):
        """provider 接受 engine arg → 透傳；不接受則退化 zero-arg。"""
        CanaryStage = self._import_canary_stage()
        calls: list = []

        def _provider(engine):
            calls.append(engine)
            return CanaryStage.DEMO_FULL_UNIVERSE

        agent = ExecutorAgent(canary_stage_provider=_provider)
        self.assertEqual(
            agent._read_canary_stage("demo"),
            CanaryStage.DEMO_FULL_UNIVERSE,
        )
        self.assertEqual(calls, ["demo"])

    def test_canary_stage_provider_zero_arg_fallback(self):
        """zero-arg provider + 傳入 engine → 退化為 zero-arg call。"""
        CanaryStage = self._import_canary_stage()

        def _zero_arg():
            return CanaryStage.PAPER_SINGLE_COHORT

        agent = ExecutorAgent(canary_stage_provider=_zero_arg)
        # 傳 engine 應觸 TypeError → fallback to zero-arg
        self.assertEqual(
            agent._read_canary_stage("demo"),
            CanaryStage.PAPER_SINGLE_COHORT,
        )

    def test_canary_stage_overrides_legacy_shadow_mode_provider(self):
        """canary_stage_provider 優先於 legacy shadow_mode_provider。"""
        CanaryStage = self._import_canary_stage()
        agent = ExecutorAgent(
            shadow_mode_provider=lambda: True,  # legacy 說 True (=shadow)
            canary_stage_provider=lambda: CanaryStage.DEMO_SINGLE_COHORT,
        )
        # canary_stage_provider 優先 → Stage 2 + shadow_mode=False
        self.assertEqual(agent._read_canary_stage(), CanaryStage.DEMO_SINGLE_COHORT)
        self.assertFalse(agent._read_shadow_mode())

    def test_legacy_shadow_mode_provider_true_projects_to_shadow(self):
        """backward-compat：只有 legacy shadow_mode_provider=True → Stage 0。"""
        CanaryStage = self._import_canary_stage()
        agent = ExecutorAgent(shadow_mode_provider=lambda: True)
        self.assertEqual(agent._read_canary_stage(), CanaryStage.SHADOW)
        self.assertTrue(agent._read_shadow_mode())

    def test_legacy_shadow_mode_provider_false_projects_to_stage_one(self):
        """backward-compat：legacy shadow_mode_provider=False → Stage 1（最低非 shadow）。"""
        CanaryStage = self._import_canary_stage()
        agent = ExecutorAgent(shadow_mode_provider=lambda: False)
        # 注意：legacy False → Stage 1（PAPER_SINGLE_COHORT）僅作 backward-compat
        # 投影；新代碼必須注入 canary_stage_provider 以區分 1/2/3/4。
        self.assertEqual(
            agent._read_canary_stage(),
            CanaryStage.PAPER_SINGLE_COHORT,
        )
        self.assertFalse(agent._read_shadow_mode())

    def test_legacy_shadow_mode_provider_exception_fails_closed_stage_zero(self):
        """invariant 9：legacy shadow_mode_provider raise → Stage 0。"""
        CanaryStage = self._import_canary_stage()

        def _boom():
            raise RuntimeError("legacy boom")

        agent = ExecutorAgent(shadow_mode_provider=_boom)
        self.assertEqual(agent._read_canary_stage(), CanaryStage.SHADOW)
        self.assertTrue(agent._read_shadow_mode())

    def test_no_provider_fails_closed_stage_zero(self):
        """雙 provider None → fail-closed Stage 0 + 維持 legacy log 字串。"""
        CanaryStage = self._import_canary_stage()
        agent = ExecutorAgent()
        self.assertEqual(agent._read_canary_stage(), CanaryStage.SHADOW)
        self.assertTrue(agent._read_shadow_mode())

    def test_canary_stage_invalid_value_fails_closed_stage_zero(self):
        """provider 回傳不可解析值 → CanaryStage.from_raw fall back Stage 0。"""
        CanaryStage = self._import_canary_stage()
        agent = ExecutorAgent(canary_stage_provider=lambda: "garbage")
        self.assertEqual(agent._read_canary_stage(), CanaryStage.SHADOW)
        self.assertTrue(agent._read_shadow_mode())

    def test_canary_stage_int_value_parsed(self):
        """provider 回傳 raw int 0..=4 → CanaryStage.from_raw 對應。"""
        CanaryStage = self._import_canary_stage()
        agent = ExecutorAgent(canary_stage_provider=lambda: 2)
        self.assertEqual(agent._read_canary_stage(), CanaryStage.DEMO_SINGLE_COHORT)
        self.assertFalse(agent._read_shadow_mode())


class TestExecutorAgentLegacyTestFixturesUnchanged(unittest.TestCase):
    """W-AUDIT-9 T3 backward-compat：既有 fixture（lambda True / False / raise）
    + ``test_no_engine_*`` 維持原行為，不引入 regression。
    """

    def test_legacy_lambda_true_still_shadow(self):
        """既有 fixture: shadow_mode_provider=lambda: True → 仍 shadow。"""
        agent = ExecutorAgent(shadow_mode_provider=lambda: True)
        self.assertTrue(agent._read_shadow_mode())

    def test_legacy_engine_aware_provider_receives_engine(self):
        """既有 fixture: shadow_mode_provider=_provider(engine) → engine 透傳。"""
        calls: list = []

        def _provider(engine):
            calls.append(engine)
            return True

        agent = ExecutorAgent(shadow_mode_provider=_provider)
        self.assertTrue(agent._read_shadow_mode("demo"))
        self.assertEqual(calls, ["demo"])

    def test_legacy_provider_raise_still_fails_closed_true(self):
        """既有 fixture: provider raise → shadow_mode=True（不變）。"""
        def _raises(_engine):
            raise RuntimeError("provider boom")

        agent = ExecutorAgent(shadow_mode_provider=_raises)
        self.assertTrue(agent._read_shadow_mode("live"))


if __name__ == "__main__":
    unittest.main()
