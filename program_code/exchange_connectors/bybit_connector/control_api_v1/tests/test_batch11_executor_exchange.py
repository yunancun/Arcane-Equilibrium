"""
Batch 11 Tests — ExecutorAgent + Exchange Conditional Orders + Dual Stop-Loss Defense
=====================================================================================
25 tests covering:
- ExecutorAgent lifecycle (start/stop/pause)
- ExecutorAgent executes APPROVED_INTENT → submit_order()
- ExecutorAgent produces EXECUTION_REPORT (slippage, fill time, actual vs expected)
- ExecutorAgent rejects invalid intents (fail-closed)
- ExecutorAgent conditional order callback fires on success
- ExecutorAgent conditional order callback failure is non-fatal
- BybitDemoConnector.place_conditional_order() constructs correct params
- BybitDemoConnector.place_conditional_order() auto-detects trigger direction
- BybitDemoConnector.place_conditional_order() rounds qty
- BybitDemoConnector.cancel_all_conditional_orders()
- BybitDemoConnector.get_conditional_orders()
- BybitDemoConnector disabled → returns error dict
- PipelineBridge._on_position_open() creates exchange conditional stop-loss
- PipelineBridge dual defense: exchange failure doesn't block local stop
- PipelineBridge dual defense: exchange connector disabled skips conditional
- ExecutorAgent stats tracking
- ExecutorAgent report storage + recent reports
- MessageBus integration: APPROVED_INTENT routed to Executor
- MessageBus integration: EXECUTION_REPORT sent to Analyst
"""

import os
import sys
import threading
import time
import unittest
from collections import defaultdict
from unittest.mock import MagicMock, patch, PropertyMock, call

# Ensure app and local_model_tools are importable
_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
_app_dir = os.path.join(_control_api_dir, "app")
# program_code dir (parent of local_model_tools)
_program_code_dir = os.path.dirname(os.path.dirname(os.path.dirname(_control_api_dir)))
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)
if _program_code_dir not in sys.path:
    sys.path.insert(0, _program_code_dir)

from app.executor_agent import ExecutorAgent, ExecutorConfig, ExecutionReport
from app.multi_agent_framework import (
    AgentMessage,
    AgentRole,
    AgentState,
    MessageBus,
    MessageType,
)
from app.bybit_demo_connector import BybitDemoConnector


# ═══════════════════════════════════════════════════════════════════════
# Helper: Fake PaperTradingEngine for testing
# ═══════════════════════════════════════════════════════════════════════

class FakePaperEngine:
    """Minimal stub that mimics PaperTradingEngine.submit_order()."""

    def __init__(self, *, reject: bool = False, fill_price: float = 67000.0):
        self._reject = reject
        self._fill_price = fill_price
        self.calls = []

    def submit_order(self, **kwargs):
        self.calls.append(kwargs)
        if self._reject:
            return {"rejected_reason": "risk_limit_exceeded", "order": {}}
        return {
            "order": {
                "orderId": "fake_123",
                "avg_fill_price": self._fill_price,
                "filled_qty": kwargs.get("qty", 0.001),
                "status": "Filled",
            },
            "rejected_reason": None,
            "fills": [{"price": self._fill_price}],
            "close_pnl": 0.0,
        }


# ═══════════════════════════════════════════════════════════════════════
# Test Group 1: ExecutorAgent Lifecycle
# ═══════════════════════════════════════════════════════════════════════

class TestExecutorAgentLifecycle(unittest.TestCase):
    """Tests 1-3: ExecutorAgent lifecycle management."""

    def test_01_initial_state_is_initializing(self):
        """ExecutorAgent starts in INITIALIZING state."""
        agent = ExecutorAgent()
        self.assertEqual(agent.state, AgentState.INITIALIZING)

    def test_02_start_sets_running(self):
        """start() transitions to RUNNING."""
        agent = ExecutorAgent()
        agent.start()
        self.assertEqual(agent.state, AgentState.RUNNING)

    def test_03_pause_and_stop(self):
        """pause()/stop() set correct states; messages ignored when not RUNNING."""
        agent = ExecutorAgent()
        agent.start()
        agent.pause()
        self.assertEqual(agent.state, AgentState.PAUSED)
        # Messages are ignored when paused
        msg = AgentMessage(
            sender=AgentRole.GUARDIAN,
            receiver=AgentRole.EXECUTOR,
            message_type=MessageType.APPROVED_INTENT,
            priority=5,
            payload={"intent_id": "test", "symbol": "BTCUSDT", "direction": "long", "size": 0.001},
        )
        agent.on_message(msg)
        stats = agent.get_stats()
        self.assertEqual(stats["intents_received"], 0)  # ignored because paused

        agent.stop()
        self.assertEqual(agent.state, AgentState.STOPPED)


# ═══════════════════════════════════════════════════════════════════════
# Test Group 2: ExecutorAgent Core Execution
# ═══════════════════════════════════════════════════════════════════════

class TestExecutorAgentExecution(unittest.TestCase):
    """Tests 4-10: ExecutorAgent order execution and quality feedback."""

    def _make_agent(self, *, engine=None, bus=None, audit=None):
        agent = ExecutorAgent(
            config=ExecutorConfig(),
            message_bus=bus,
            paper_engine=engine,
            audit_callback=audit,
        )
        agent.start()
        return agent

    def _make_approved_intent_msg(self, **overrides):
        payload = {
            "intent_id": "intent_001",
            "symbol": "BTCUSDT",
            "direction": "long",
            "size": 0.001,
            "metadata": {},
        }
        payload.update(overrides)
        return AgentMessage(
            sender=AgentRole.GUARDIAN,
            receiver=AgentRole.EXECUTOR,
            message_type=MessageType.APPROVED_INTENT,
            priority=5,
            payload=payload,
        )

    def test_04_execute_approved_intent_success(self):
        """Executor receives APPROVED_INTENT and calls submit_order()."""
        engine = FakePaperEngine(fill_price=67000.0)
        agent = self._make_agent(engine=engine)
        agent.update_market_prices({"BTCUSDT": 67000.0})

        msg = self._make_approved_intent_msg()
        agent.on_message(msg)

        self.assertEqual(len(engine.calls), 1)
        self.assertEqual(engine.calls[0]["symbol"], "BTCUSDT")
        self.assertEqual(engine.calls[0]["side"], "Buy")

    def test_05_execution_report_produced(self):
        """Executor produces EXECUTION_REPORT with slippage and fill time."""
        engine = FakePaperEngine(fill_price=67010.0)
        bus = MessageBus()
        reports_received = []
        bus.subscribe(AgentRole.ANALYST, lambda m: reports_received.append(m))

        agent = self._make_agent(engine=engine, bus=bus)
        agent.update_market_prices({"BTCUSDT": 67000.0})

        msg = self._make_approved_intent_msg()
        agent.on_message(msg)

        # Check that EXECUTION_REPORT was sent
        self.assertEqual(len(reports_received), 1)
        report_msg = reports_received[0]
        self.assertEqual(report_msg.message_type, MessageType.EXECUTION_REPORT)
        payload = report_msg.payload
        self.assertTrue(payload["success"])
        self.assertGreaterEqual(payload["fill_time_ms"], 0)  # may be 0 in fast unit tests
        # Slippage: |67010-67000|/67000 * 10000 ≈ 1.49 bps
        self.assertGreater(payload["slippage_bps"], 0)
        self.assertAlmostEqual(payload["actual_price"], 67010.0)

    def test_06_execution_report_on_rejection(self):
        """Rejected order produces a failed EXECUTION_REPORT."""
        engine = FakePaperEngine(reject=True)
        agent = self._make_agent(engine=engine)
        agent.update_market_prices({"BTCUSDT": 67000.0})

        report = agent.execute_order(
            intent_id="rej_001", symbol="BTCUSDT", side="Buy", qty=0.001,
        )
        self.assertFalse(report.success)
        self.assertIn("rejected", report.error.lower())

    def test_07_no_paper_engine_fail_closed(self):
        """Without paper engine, execution fails with clear error."""
        agent = self._make_agent(engine=None)
        report = agent.execute_order(
            intent_id="no_eng", symbol="BTCUSDT", side="Buy", qty=0.001,
        )
        self.assertFalse(report.success)
        self.assertIn("No paper engine", report.error)

    def test_08_invalid_intent_rejected(self):
        """Intent with invalid fields (empty symbol, zero size) is rejected."""
        engine = FakePaperEngine()
        agent = self._make_agent(engine=engine)

        # Empty symbol
        msg = self._make_approved_intent_msg(symbol="", size=0.001)
        agent.on_message(msg)
        self.assertEqual(len(engine.calls), 0)

        # Zero size
        msg2 = self._make_approved_intent_msg(symbol="BTCUSDT", size=0)
        agent.on_message(msg2)
        self.assertEqual(len(engine.calls), 0)

    def test_09_conditional_order_callback_fires(self):
        """On successful fill, conditional order callback is invoked."""
        engine = FakePaperEngine(fill_price=67000.0)
        agent = self._make_agent(engine=engine)
        agent.update_market_prices({"BTCUSDT": 67000.0})

        callback_calls = []
        agent.set_conditional_order_callback(
            lambda sym, side, price, qty: callback_calls.append((sym, side, price, qty))
        )

        report = agent.execute_order(
            intent_id="cb_001", symbol="BTCUSDT", side="Buy", qty=0.001,
        )
        self.assertTrue(report.success)
        self.assertEqual(len(callback_calls), 1)
        self.assertEqual(callback_calls[0][0], "BTCUSDT")

    def test_10_conditional_callback_failure_nonfatal(self):
        """Conditional order callback failure does not crash executor."""
        engine = FakePaperEngine(fill_price=67000.0)
        agent = self._make_agent(engine=engine)
        agent.update_market_prices({"BTCUSDT": 67000.0})

        def _bad_callback(*args):
            raise RuntimeError("exchange timeout")

        agent.set_conditional_order_callback(_bad_callback)

        # Should not raise
        report = agent.execute_order(
            intent_id="cb_fail", symbol="BTCUSDT", side="Buy", qty=0.001,
        )
        self.assertTrue(report.success)  # execution itself succeeded


# ═══════════════════════════════════════════════════════════════════════
# Test Group 3: ExecutorAgent Stats & Reports
# ═══════════════════════════════════════════════════════════════════════

class TestExecutorAgentStats(unittest.TestCase):
    """Tests 11-13: Stats tracking and report storage."""

    def test_11_stats_tracking(self):
        """Stats are correctly updated after executions."""
        engine = FakePaperEngine()
        agent = ExecutorAgent(paper_engine=engine)
        agent.start()
        agent.update_market_prices({"BTCUSDT": 67000.0})

        agent.execute_order(intent_id="s1", symbol="BTCUSDT", side="Buy", qty=0.001)
        agent.execute_order(intent_id="s2", symbol="BTCUSDT", side="Sell", qty=0.001)

        stats = agent.get_stats()
        self.assertEqual(stats["executions_attempted"], 2)
        self.assertEqual(stats["executions_success"], 2)
        self.assertEqual(stats["total_reports"], 2)

    def test_12_recent_reports_limited(self):
        """get_recent_reports() respects limit."""
        engine = FakePaperEngine()
        agent = ExecutorAgent(paper_engine=engine)
        agent.start()

        for i in range(5):
            agent.execute_order(intent_id=f"r{i}", symbol="BTCUSDT", side="Buy", qty=0.001)

        recent = agent.get_recent_reports(limit=3)
        self.assertEqual(len(recent), 3)

    def test_13_report_max_cap(self):
        """Reports list capped at config.max_reports."""
        engine = FakePaperEngine()
        config = ExecutorConfig(max_reports=5)
        agent = ExecutorAgent(config=config, paper_engine=engine)
        agent.start()

        for i in range(10):
            agent.execute_order(intent_id=f"cap{i}", symbol="BTCUSDT", side="Buy", qty=0.001)

        self.assertEqual(len(agent._reports), 5)


# ═══════════════════════════════════════════════════════════════════════
# Test Group 4: BybitDemoConnector Conditional Orders
# ═══════════════════════════════════════════════════════════════════════

class TestBybitDemoConditionalOrders(unittest.TestCase):
    """Tests 14-19: BybitDemoConnector.place_conditional_order()."""

    def _make_connector(self, *, enabled=True):
        """Create a connector with mocked _request."""
        conn = BybitDemoConnector.__new__(BybitDemoConnector)
        conn._api_key = "test_key" if enabled else ""
        conn._api_secret = "test_secret" if enabled else ""
        conn._enabled = enabled
        conn._lock = threading.Lock()
        conn._stats = {}
        conn._mock_request = MagicMock(return_value={"retCode": 0, "result": {"orderId": "cond_123"}})
        conn._request = conn._mock_request
        return conn

    def test_14_place_conditional_order_params(self):
        """place_conditional_order() sends correct Bybit V5 params."""
        conn = self._make_connector()
        result = conn.place_conditional_order(
            symbol="BTCUSDT", side="Sell", qty=0.001, trigger_price=63000.0,
        )
        self.assertEqual(result["retCode"], 0)

        call_args = conn._mock_request.call_args
        self.assertEqual(call_args[0][0], "POST")
        self.assertEqual(call_args[0][1], "/v5/order/create")
        params = call_args[0][2]
        self.assertEqual(params["symbol"], "BTCUSDT")
        self.assertEqual(params["side"], "Sell")
        self.assertEqual(params["triggerPrice"], "63000.0")
        self.assertEqual(params["orderFilter"], "StopOrder")
        self.assertTrue(params["reduceOnly"])

    def test_15_auto_detect_trigger_direction_sell(self):
        """Sell stop → trigger_direction=2 (falls below)."""
        conn = self._make_connector()
        conn.place_conditional_order(
            symbol="BTCUSDT", side="Sell", qty=0.001, trigger_price=63000.0,
        )
        params = conn._mock_request.call_args[0][2]
        self.assertEqual(params["triggerDirection"], 2)

    def test_16_auto_detect_trigger_direction_buy(self):
        """Buy stop → trigger_direction=1 (rises above)."""
        conn = self._make_connector()
        conn.place_conditional_order(
            symbol="BTCUSDT", side="Buy", qty=0.001, trigger_price=70000.0,
        )
        params = conn._mock_request.call_args[0][2]
        self.assertEqual(params["triggerDirection"], 1)

    def test_17_qty_rounding(self):
        """Qty is rounded to exchange step precision."""
        conn = self._make_connector()
        # Small qty → 3dp
        conn.place_conditional_order(
            symbol="BTCUSDT", side="Sell", qty=0.00156789, trigger_price=63000.0,
        )
        params = conn._mock_request.call_args[0][2]
        self.assertEqual(params["qty"], "0.002")

        # Large qty → integer
        conn.place_conditional_order(
            symbol="DOGEUSDT", side="Sell", qty=1234.567, trigger_price=0.08,
        )
        params = conn._mock_request.call_args[0][2]
        self.assertEqual(params["qty"], "1235")

    def test_18_disabled_connector_returns_error(self):
        """Disabled connector returns error dict without calling API."""
        conn = self._make_connector(enabled=False)
        result = conn.place_conditional_order(
            symbol="BTCUSDT", side="Sell", qty=0.001, trigger_price=63000.0,
        )
        self.assertEqual(result["retCode"], -1)
        conn._mock_request.assert_not_called()

    def test_19_cancel_all_conditional_orders(self):
        """cancel_all_conditional_orders() sends correct request."""
        conn = self._make_connector()
        result = conn.cancel_all_conditional_orders("BTCUSDT")
        self.assertEqual(result["retCode"], 0)
        call_args = conn._mock_request.call_args
        params = call_args[0][2]
        self.assertEqual(params["orderFilter"], "StopOrder")
        self.assertEqual(params["symbol"], "BTCUSDT")

    def test_20_get_conditional_orders(self):
        """get_conditional_orders() queries with StopOrder filter."""
        conn = self._make_connector()
        conn.get_conditional_orders(symbol="ETHUSDT")
        call_args = conn._mock_request.call_args
        params = call_args[0][2]
        self.assertEqual(params["orderFilter"], "StopOrder")
        self.assertEqual(params["symbol"], "ETHUSDT")


# ═══════════════════════════════════════════════════════════════════════
# Test Group 5: Dual Stop-Loss Defense (PipelineBridge)
# ═══════════════════════════════════════════════════════════════════════

class TestDualStopLossDefense(unittest.TestCase):
    """Tests 21-25: PipelineBridge dual defense (local + exchange)."""

    def _make_bridge_with_mocks(self, *, demo_enabled=True, demo_fail=False):
        """Create a minimal PipelineBridge with mocked dependencies."""
        from app.pipeline_bridge import PipelineBridge

        km = MagicMock()
        ie = MagicMock()
        ie.get_indicators.return_value = {"atr": 1500.0}  # ATR = $1500
        se = MagicMock()
        orch = MagicMock()
        engine = MagicMock()
        engine.store = MagicMock()
        engine.get_state.return_value = {"positions": {}}

        stop_mgr = MagicMock()
        stop_mgr.check_stops.return_value = []

        bridge = PipelineBridge(
            kline_manager=km,
            indicator_engine=ie,
            signal_engine=se,
            orchestrator=orch,
            paper_engine=engine,
            stop_manager=stop_mgr,
        )

        # Mock demo connector
        demo = MagicMock()
        demo.is_enabled = demo_enabled
        if demo_fail:
            demo.place_conditional_order.return_value = {"retCode": 10001, "retMsg": "Qty invalid"}
        else:
            demo.place_conditional_order.return_value = {"retCode": 0, "result": {"orderId": "cond_456"}}
        bridge.set_demo_connector(demo)

        return bridge, demo, stop_mgr

    def _make_intent(self, *, symbol="BTCUSDT", side="Buy", qty=0.001):
        intent = MagicMock()
        intent.symbol = symbol
        intent.side = side
        intent.qty = qty
        intent.metadata = {"_regime": "trending"}
        return intent

    def test_21_dual_defense_exchange_conditional_created(self):
        """On position open, exchange SL + TP conditional orders are created (0B-2)."""
        bridge, demo, _ = self._make_bridge_with_mocks()
        intent = self._make_intent(side="Buy", qty=0.001)

        bridge._on_position_open(intent, fill_price=67000.0)

        # 0B-2: Now creates both SL and TP orders (2 calls)
        self.assertGreaterEqual(demo.place_conditional_order.call_count, 1)
        # First call is SL — check close side for long = Sell
        sl_call = demo.place_conditional_order.call_args_list[0]
        sl_kwargs = sl_call[1] if sl_call[1] else {}
        self.assertEqual(sl_kwargs.get("side", sl_call[0][1] if len(sl_call[0]) > 1 else ""), "Sell")

    def test_22_dual_defense_trigger_price_long(self):
        """Long position: SL trigger_price < entry_price (0B-2: first call is SL)."""
        bridge, demo, _ = self._make_bridge_with_mocks()
        intent = self._make_intent(side="Buy")

        bridge._on_position_open(intent, fill_price=67000.0)

        # 0B-2: First call is SL, second call is TP. Check SL trigger.
        sl_call = demo.place_conditional_order.call_args_list[0]
        sl_kwargs = sl_call[1] if sl_call[1] else {}
        trigger = sl_kwargs.get("trigger_price", sl_call[0][2] if len(sl_call[0]) > 2 else None)
        self.assertLess(trigger, 67000.0)

    def test_23_dual_defense_trigger_price_short(self):
        """Short position: SL trigger_price > entry_price (0B-2: first call is SL)."""
        bridge, demo, _ = self._make_bridge_with_mocks()
        intent = self._make_intent(side="Sell")

        bridge._on_position_open(intent, fill_price=67000.0)

        # 0B-2: First call is SL. Check SL trigger.
        sl_call = demo.place_conditional_order.call_args_list[0]
        sl_kwargs = sl_call[1] if sl_call[1] else {}
        trigger = sl_kwargs.get("trigger_price", sl_call[0][2] if len(sl_call[0]) > 2 else None)
        self.assertGreater(trigger, 67000.0)

    def test_24_dual_defense_exchange_failure_nonfatal(self):
        """Exchange conditional order failure does NOT block local stop tracking."""
        bridge, demo, stop_mgr = self._make_bridge_with_mocks(demo_fail=True)
        intent = self._make_intent(side="Buy")

        # Should not raise
        bridge._on_position_open(intent, fill_price=67000.0)

        # Local stop still tracked
        stop_mgr.track_position.assert_called_once()
        # 0B-2: Exchange was attempted (SL + TP = 2 calls, but demo_fail so may vary)
        self.assertGreaterEqual(demo.place_conditional_order.call_count, 1)

    def test_25_dual_defense_disabled_connector_skipped(self):
        """If demo connector is disabled, exchange conditional is skipped gracefully."""
        bridge, demo, stop_mgr = self._make_bridge_with_mocks(demo_enabled=False)
        intent = self._make_intent(side="Buy")

        bridge._on_position_open(intent, fill_price=67000.0)

        # Local stop still tracked
        stop_mgr.track_position.assert_called_once()
        # Exchange NOT attempted
        demo.place_conditional_order.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════
# Test Group G-05: ExecutorAgent Decision Lease (Principle 3)
# G-05 測試組：ExecutorAgent Decision Lease（根原則 3）
# ═══════════════════════════════════════════════════════════════════════

class TestExecutorAgentDecisionLease(unittest.TestCase):
    """
    Tests 26-31: Decision Lease integration — principle 3 enforcement.
    G-05 Decision Lease 集成測試 — 根原則 3（AI 輸出 ≠ 即時命令）落實驗證。

    Three scenarios must hold:
    1. governance_hub=None → fail-open (backward compat), execution proceeds.
    2. acquire_lease() returns None → fail-closed, execution rejected.
    3. acquire_lease() returns valid lease_id → execution proceeds normally.
    三個場景必須成立：
    1. governance_hub=None → 允許通過（向後兼容），執行繼續。
    2. acquire_lease() 返回 None → 失敗默認收縮，拒絕執行。
    3. acquire_lease() 返回有效 lease_id → 執行正常進行。
    """

    def _make_hub(self, *, lease_result: object = "lease_abc123"):
        """
        Create a mock GovernanceHub with configurable acquire_lease return value.
        創建 mock GovernanceHub，可配置 acquire_lease 返回值。
        """
        hub = MagicMock()
        hub.acquire_lease.return_value = lease_result
        return hub

    def test_26_no_governance_hub_allows_execution(self):
        """governance_hub=None → fail-open, submit_order() is called normally."""
        # governance_hub=None 時允許通過，submit_order() 正常調用
        engine = FakePaperEngine(fill_price=67000.0)
        agent = ExecutorAgent(paper_engine=engine)
        agent.start()
        agent.update_market_prices({"BTCUSDT": 67000.0})

        report = agent.execute_order(
            intent_id="lease_test_no_hub",
            symbol="BTCUSDT",
            side="Buy",
            qty=0.001,
        )

        self.assertTrue(report.success)
        self.assertEqual(len(engine.calls), 1)

    def test_27_acquire_lease_returns_none_rejects_execution(self):
        """acquire_lease() returns None → fail-closed, execution is rejected."""
        # acquire_lease() 返回 None → 失敗默認收縮，拒絕執行
        engine = FakePaperEngine(fill_price=67000.0)
        hub = self._make_hub(lease_result=None)

        agent = ExecutorAgent(paper_engine=engine, governance_hub=hub)
        agent.start()
        agent.update_market_prices({"BTCUSDT": 67000.0})

        report = agent.execute_order(
            intent_id="lease_test_denied",
            symbol="BTCUSDT",
            side="Buy",
            qty=0.001,
        )

        self.assertFalse(report.success)
        self.assertEqual(report.error, "governance_lease_acquisition_failed")
        # submit_order() must NOT have been called — no execution without lease
        # 沒有 lease 就不能下單，submit_order() 不應被調用
        self.assertEqual(len(engine.calls), 0)

    def test_28_acquire_lease_success_allows_execution(self):
        """acquire_lease() returns valid lease_id → execution proceeds normally."""
        # acquire_lease() 返回有效 lease_id → 執行正常進行
        engine = FakePaperEngine(fill_price=67000.0)
        hub = self._make_hub(lease_result="lease_valid_001")

        agent = ExecutorAgent(paper_engine=engine, governance_hub=hub)
        agent.start()
        agent.update_market_prices({"BTCUSDT": 67000.0})

        report = agent.execute_order(
            intent_id="lease_test_ok",
            symbol="BTCUSDT",
            side="Buy",
            qty=0.001,
        )

        self.assertTrue(report.success)
        self.assertEqual(len(engine.calls), 1)
        # Verify acquire_lease was called with correct arguments
        # 驗證 acquire_lease 以正確參數被調用
        hub.acquire_lease.assert_called_once_with(
            intent_id="lease_test_ok",
            scope="TRADE_ENTRY",
            ttl_seconds=30.0,
        )

    def test_29_lease_rejection_stats_updated(self):
        """Stats correctly reflect lease-rejected executions."""
        # 統計正確反映被 lease 拒絕的執行
        engine = FakePaperEngine(fill_price=67000.0)
        hub = self._make_hub(lease_result=None)

        agent = ExecutorAgent(paper_engine=engine, governance_hub=hub)
        agent.start()

        agent.execute_order(intent_id="r1", symbol="BTCUSDT", side="Buy", qty=0.001)
        agent.execute_order(intent_id="r2", symbol="BTCUSDT", side="Sell", qty=0.001)

        stats = agent.get_stats()
        self.assertEqual(stats["executions_attempted"], 2)
        self.assertEqual(stats["executions_failed"], 2)
        self.assertEqual(stats["executions_success"], 0)
        self.assertEqual(stats["errors"], 2)

    def test_30_lease_rejection_produces_report(self):
        """Lease rejection produces a stored ExecutionReport with correct fields."""
        # lease 拒絕會產生一份包含正確欄位的 ExecutionReport 並存檔
        engine = FakePaperEngine(fill_price=67000.0)
        hub = self._make_hub(lease_result=None)

        agent = ExecutorAgent(paper_engine=engine, governance_hub=hub)
        agent.start()

        report = agent.execute_order(
            intent_id="rpt_test",
            symbol="ETHUSDT",
            side="Sell",
            qty=0.01,
        )

        self.assertFalse(report.success)
        self.assertEqual(report.intent_id, "rpt_test")
        self.assertEqual(report.symbol, "ETHUSDT")
        self.assertEqual(report.side, "Sell")
        self.assertEqual(report.error, "governance_lease_acquisition_failed")

        # Report should be stored in agent._reports
        # 報告應被存入 agent._reports
        recent = agent.get_recent_reports(limit=5)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["intent_id"], "rpt_test")
        self.assertFalse(recent[0]["success"])

    def test_31_governance_hub_stored_as_attribute(self):
        """ExecutorAgent stores governance_hub as _governance_hub attribute."""
        # ExecutorAgent 正確存儲 governance_hub 為 _governance_hub 屬性
        hub = self._make_hub()
        agent = ExecutorAgent(governance_hub=hub)
        self.assertIs(agent._governance_hub, hub)

        # None case
        agent_no_hub = ExecutorAgent()
        self.assertIsNone(agent_no_hub._governance_hub)


# ═══════════════════════════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
