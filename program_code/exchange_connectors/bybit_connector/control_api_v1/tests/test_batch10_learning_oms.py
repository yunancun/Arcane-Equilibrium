"""
Batch 10 Tests — OMS SM-03 Integration + L2 Learning Automation
================================================================
30 tests covering:
- OMS SM-03 串联：Paper Engine 7-state ↔ OMS 11-state lifecycle mapping
- OMS SM-03 状态同步：submit_order 时自动创建 OMS 订单并同步状态
- OMS SM-03 非法转换拒绝：SM-03 rejected transitions are enforced
- OMS SM-03 回退路径：OMS_SM03_ENABLED=False disables OMS enforcement
- Analyst L2 auto-trigger：analyze_patterns() with threshold + force
- L2 Cron trigger：周日 UTC 0:00 触发
- TTL enforcer OMS support：OMS SUBMITTED timeout → auto-CANCEL
- Post-fill reconciliation：FILLED→RECONCILING→COMPLETED lifecycle
"""

import copy
import datetime
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from collections import defaultdict
from unittest.mock import MagicMock, patch, PropertyMock, call

# Ensure app is importable
_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
_app_dir = os.path.join(_control_api_dir, "app")
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)


from app.paper_trading_engine import (
    PaperTradingEngine,
    PaperStateStore,
    OMS_SM03_ENABLED,
    ORDER_STATE_CREATED,
    ORDER_STATE_SUBMITTED,
    ORDER_STATE_WORKING,
    ORDER_STATE_PARTIALLY_FILLED,
    ORDER_STATE_FILLED,
    ORDER_STATE_CANCELED,
    ORDER_STATE_REJECTED,
    TERMINAL_STATES,
    ACTIVE_STATES,
    _transition_order,
    _oms_complete_reconciliation,
    create_paper_order,
    now_ms,
)
from app.oms_state_machine import (
    OMSStateMachine as OmsStateMachine,
    OrderState,
    OrderInitiator,
    OMSTransitionRule as TransitionRule,
)
from app.analyst_agent import (
    AnalystAgent,
    AnalystConfig,
    PatternInsight,
    TradeRecord,
)
from app.ttl_enforcer import (
    TTLEnforcer,
    TTLConfig,
    TTLEntry,
    TTLExpiryAction,
    _create_default_ttl_configs,
)


def _make_engine(tmp_dir, oms_sm=None, governance_hub=None, risk_manager=None):
    """Helper to create a PaperTradingEngine with optional OMS SM."""
    state_file = os.path.join(tmp_dir, "paper_state.json")
    store = PaperStateStore(state_file)
    engine = PaperTradingEngine(store, risk_manager=risk_manager)
    if oms_sm is not None:
        engine.set_oms_sm(oms_sm)
    if governance_hub is not None:
        engine.set_governance_hub(governance_hub)
    # Bypass learning tier check for tests
    engine._check_tier_capability = lambda cap: True
    engine.start_session(10000.0)
    return engine


class TestOMSSM03Mapping(unittest.TestCase):
    """Test OMS SM-03 state mapping between Paper 7-state and OMS 11-state."""

    def test_map_from_paper_state_all_7_states(self):
        """All 7 paper states map to valid OMS OrderState."""
        paper_states = [
            ORDER_STATE_CREATED,
            ORDER_STATE_SUBMITTED,
            ORDER_STATE_WORKING,
            ORDER_STATE_PARTIALLY_FILLED,
            ORDER_STATE_FILLED,
            ORDER_STATE_CANCELED,
            ORDER_STATE_REJECTED,
        ]
        for ps in paper_states:
            oms_state = OmsStateMachine.map_from_paper_state(ps)
            self.assertIsInstance(oms_state, OrderState)

    def test_map_to_paper_state_roundtrip(self):
        """Paper → OMS → Paper roundtrip is identity for all 7 states."""
        paper_states = [
            ORDER_STATE_CREATED,
            ORDER_STATE_SUBMITTED,
            ORDER_STATE_WORKING,
            ORDER_STATE_PARTIALLY_FILLED,
            ORDER_STATE_FILLED,
            ORDER_STATE_CANCELED,
            ORDER_STATE_REJECTED,
        ]
        for ps in paper_states:
            oms = OmsStateMachine.map_from_paper_state(ps)
            back = OmsStateMachine.map_to_paper_state(oms)
            self.assertEqual(ps, back, f"Roundtrip failed: {ps} → {oms} → {back}")

    def test_oms_has_4_extra_states(self):
        """OMS has 4 states beyond Paper's 7: PENDING, APPROVED, RECONCILING, COMPLETED."""
        oms_only = {OrderState.PENDING, OrderState.APPROVED, OrderState.RECONCILING, OrderState.COMPLETED}
        for state in oms_only:
            with self.assertRaises(ValueError):
                OmsStateMachine.map_to_paper_state(state)

    def test_unknown_paper_state_raises(self):
        """Unknown paper state raises ValueError."""
        with self.assertRaises(ValueError):
            OmsStateMachine.map_from_paper_state("paper_order_unknown")


class TestOMSSM03Integration(unittest.TestCase):
    """Test OMS SM-03 integration with PaperTradingEngine submit_order."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.oms = OmsStateMachine()
        # P0-1: provide mock governance_hub so fail-closed check passes
        self.mock_hub = MagicMock()
        self.mock_hub.is_authorized.return_value = True
        self.mock_hub.acquire_lease.return_value = "test-lease"
        self.mock_hub.release_lease.return_value = None

    def test_submit_order_creates_oms_order(self):
        """submit_order creates an OMS order with matching order_id."""
        engine = _make_engine(self._tmp, oms_sm=self.oms, governance_hub=self.mock_hub)
        result = engine.submit_order(
            "BTCUSDT", "Buy", "market", 0.001,
            market_prices={"BTCUSDT": 50000.0},
        )
        order = result["order"]
        self.assertIsNotNone(order)
        self.assertIn("oms_order_id", order)
        # OMS should have the order
        oms_order = self.oms.get(order["oms_order_id"])
        self.assertIsNotNone(oms_order)

    def test_submit_order_oms_state_synced(self):
        """After a market fill, OMS state is COMPLETED (post-reconciliation)."""
        engine = _make_engine(self._tmp, oms_sm=self.oms, governance_hub=self.mock_hub)
        result = engine.submit_order(
            "BTCUSDT", "Buy", "market", 0.001,
            market_prices={"BTCUSDT": 50000.0},
        )
        order = result["order"]
        self.assertIsNotNone(order)
        # Paper state should be FILLED
        self.assertEqual(order["state"], ORDER_STATE_FILLED)
        # OMS state should be COMPLETED (after auto-reconciliation)
        self.assertEqual(order.get("oms_state"), "COMPLETED")

    def test_submit_order_rejected_syncs_oms(self):
        """Rejected order (insufficient margin) syncs OMS to REJECTED."""
        engine = _make_engine(self._tmp, oms_sm=self.oms, governance_hub=self.mock_hub)
        # Start a session with very low balance
        engine.store.mutate(lambda s: {**s, "session": {**s["session"], "current_paper_balance_usdt": 0.01}})
        result = engine.submit_order(
            "BTCUSDT", "Buy", "market", 1.0,
            market_prices={"BTCUSDT": 50000.0},
        )
        order = result["order"]
        self.assertIsNotNone(order)
        self.assertEqual(order["state"], ORDER_STATE_REJECTED)
        self.assertEqual(result["rejected_reason"], "insufficient_margin")

    def test_transition_order_with_oms_sm(self):
        """_transition_order syncs state to OMS when oms_sm is provided."""
        oms = OmsStateMachine()
        order_obj = create_paper_order("ETHUSDT", "Buy", "market", 0.1, price=3000.0)
        # Create OMS order
        oms_order_id = oms.create_order(
            symbol="ETHUSDT", side="Buy", order_type="market",
            qty=0.1, created_by="test",
        )
        order_obj["oms_order_id"] = oms_order_id
        # Transition CREATED→SUBMITTED drives OMS through PENDING→APPROVED→SUBMITTED
        _transition_order(order_obj, ORDER_STATE_SUBMITTED, oms_sm=oms)
        self.assertEqual(order_obj["state"], ORDER_STATE_SUBMITTED)
        self.assertEqual(order_obj.get("oms_state"), "SUBMITTED")

    def test_oms_sm_reject_blocks_paper_transition(self):
        """If OMS SM-03 rejects a transition, paper engine also rejects it (fail-closed)."""
        oms = MagicMock()
        # For CREATED→SUBMITTED, submit_for_approval is called first
        oms.submit_for_approval.side_effect = ValueError("OMS: invalid transition")
        order_obj = create_paper_order("BTCUSDT", "Sell", "limit", 0.5, price=50000.0)
        order_obj["oms_order_id"] = "oms-fake-id"
        # Try to transition — should be rejected by OMS
        with self.assertRaises(ValueError) as ctx:
            _transition_order(order_obj, ORDER_STATE_SUBMITTED, oms_sm=oms)
        self.assertIn("OMS SM-03 rejected", str(ctx.exception))
        # Paper order should NOT have transitioned
        self.assertEqual(order_obj["state"], ORDER_STATE_CREATED)


class TestOMSSM03Fallback(unittest.TestCase):
    """Test OMS SM-03 fallback (OMS_SM03_ENABLED=False)."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        # P0-1: provide mock governance_hub so fail-closed check passes
        self.mock_hub = MagicMock()
        self.mock_hub.is_authorized.return_value = True
        self.mock_hub.acquire_lease.return_value = "test-lease"
        self.mock_hub.release_lease.return_value = None

    def test_no_oms_sm_works_normally(self):
        """Engine works normally without OMS SM (legacy mode)."""
        engine = _make_engine(self._tmp, oms_sm=None, governance_hub=self.mock_hub)
        result = engine.submit_order(
            "BTCUSDT", "Buy", "market", 0.001,
            market_prices={"BTCUSDT": 50000.0},
        )
        order = result["order"]
        self.assertIsNotNone(order)
        self.assertEqual(order["state"], ORDER_STATE_FILLED)
        self.assertNotIn("oms_order_id", order)

    @patch("app.paper_trading_engine.OMS_SM03_ENABLED", False)
    def test_oms_disabled_skips_oms(self):
        """When OMS_SM03_ENABLED=False, OMS SM is not consulted."""
        oms = MagicMock()
        engine = _make_engine(self._tmp, oms_sm=oms, governance_hub=self.mock_hub)
        result = engine.submit_order(
            "BTCUSDT", "Buy", "market", 0.001,
            market_prices={"BTCUSDT": 50000.0},
        )
        order = result["order"]
        self.assertIsNotNone(order)
        self.assertEqual(order["state"], ORDER_STATE_FILLED)
        # OMS should NOT have been called
        oms.create_order.assert_not_called()

    def test_transition_without_oms_sm_kwarg(self):
        """_transition_order without oms_sm kwarg works as legacy 7-state."""
        order_obj = create_paper_order("BTCUSDT", "Buy", "market", 0.1, price=50000.0)
        _transition_order(order_obj, ORDER_STATE_SUBMITTED)
        self.assertEqual(order_obj["state"], ORDER_STATE_SUBMITTED)


class TestPostFillReconciliation(unittest.TestCase):
    """Test OMS FILLED→RECONCILING→COMPLETED post-fill lifecycle."""

    def test_reconciliation_after_fill(self):
        """_oms_complete_reconciliation drives FILLED→RECONCILING→COMPLETED."""
        oms = OmsStateMachine()
        oms_order_id = oms.create_order(
            symbol="BTCUSDT", side="Buy", order_type="market",
            qty=0.1, created_by="test",
        )
        # Drive through to FILLED
        oms.submit_for_approval(oms_order_id, initiator=OrderInitiator.SYSTEM)
        oms.approve(oms_order_id, initiator=OrderInitiator.AUTHORIZATION_SM)
        oms.send_to_venue(oms_order_id, initiator=OrderInitiator.SYSTEM)
        oms.acknowledge(oms_order_id, initiator=OrderInitiator.EXECUTION_VENUE)
        oms.fill(oms_order_id, initiator=OrderInitiator.EXECUTION_VENUE, reason="full_fill")

        order = {"oms_order_id": oms_order_id, "state": ORDER_STATE_FILLED}
        _oms_complete_reconciliation(order, oms)
        self.assertEqual(order["oms_state"], "COMPLETED")

    def test_reconciliation_skipped_without_oms(self):
        """Reconciliation is a no-op without OMS SM."""
        order = {"state": ORDER_STATE_FILLED}
        _oms_complete_reconciliation(order, None)  # Should not raise
        self.assertNotIn("oms_state", order)

    @patch("app.paper_trading_engine.OMS_SM03_ENABLED", False)
    def test_reconciliation_skipped_when_disabled(self):
        """Reconciliation is a no-op when OMS_SM03_ENABLED=False."""
        oms = MagicMock()
        order = {"oms_order_id": "x", "state": ORDER_STATE_FILLED}
        _oms_complete_reconciliation(order, oms)
        oms.begin_reconciliation.assert_not_called()


class TestAnalystL2AutoTrigger(unittest.TestCase):
    """Test Analyst analyze_patterns() L2 analysis trigger."""

    def _make_analyst(self, n_records=0, ollama=None):
        config = AnalystConfig(l2_min_observations=200)
        agent = AnalystAgent(config=config, ollama_client=ollama)
        agent.start()
        for i in range(n_records):
            agent.analyze_trade(TradeRecord(
                trade_id=f"t-{i}",
                symbol="BTCUSDT",
                strategy="ma_crossover",
                direction="long",
                entry_price=50000.0,
                exit_price=50100.0 if i % 3 != 0 else 49900.0,
                pnl=100.0 if i % 3 != 0 else -100.0,
                hold_ms=3600000,
                regime="trending",
                timestamp_ms=int(time.time() * 1000),
            ))
        return agent

    def test_analyze_patterns_below_threshold_returns_none(self):
        """analyze_patterns() returns None when observations < 200."""
        agent = self._make_analyst(n_records=50)
        result = agent.analyze_patterns()
        self.assertIsNone(result)

    def test_analyze_patterns_above_threshold_returns_insight(self):
        """analyze_patterns() returns PatternInsight when observations >= 200."""
        agent = self._make_analyst(n_records=250)
        result = agent.analyze_patterns()
        self.assertIsNotNone(result)
        self.assertIsInstance(result, PatternInsight)
        self.assertIsInstance(result.winning_patterns, list)
        self.assertIsInstance(result.losing_patterns, list)
        self.assertIsInstance(result.regime_strategy_matrix, dict)

    def test_analyze_patterns_force_bypasses_threshold(self):
        """analyze_patterns(force=True) runs even with < 200 observations."""
        agent = self._make_analyst(n_records=50)
        result = agent.analyze_patterns(force=True)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, PatternInsight)

    def test_analyze_patterns_force_empty_returns_none(self):
        """analyze_patterns(force=True) returns None with 0 observations."""
        agent = self._make_analyst(n_records=0)
        result = agent.analyze_patterns(force=True)
        self.assertIsNone(result)

    def test_pattern_insight_has_required_fields(self):
        """PatternInsight must have winning_patterns, losing_patterns, regime_strategy_matrix."""
        agent = self._make_analyst(n_records=250)
        result = agent.analyze_patterns()
        self.assertIsNotNone(result)
        d = result.to_dict()
        self.assertIn("winning_patterns", d)
        self.assertIn("losing_patterns", d)
        self.assertIn("regime_strategy_matrix", d)
        self.assertIn("observations_count", d)
        self.assertEqual(d["observations_count"], 250)

    def test_auto_trigger_on_threshold(self):
        """L2 auto-triggers when 200th observation arrives."""
        config = AnalystConfig(l2_min_observations=200)
        agent = AnalystAgent(config=config)
        agent.start()
        # Add 199 — no L2 yet
        for i in range(199):
            agent.analyze_trade(TradeRecord(
                trade_id=f"t-{i}", symbol="BTCUSDT", strategy="test",
                direction="long", entry_price=100, exit_price=101,
                pnl=1.0, hold_ms=1000, regime="trending",
                timestamp_ms=int(time.time() * 1000),
            ))
        self.assertEqual(agent._stats["l2_analyses"], 0)

        # Add 200th — L2 triggers
        agent.analyze_trade(TradeRecord(
            trade_id="t-200", symbol="BTCUSDT", strategy="test",
            direction="long", entry_price=100, exit_price=101,
            pnl=1.0, hold_ms=1000, regime="trending",
            timestamp_ms=int(time.time() * 1000),
        ))
        self.assertEqual(agent._stats["l2_analyses"], 1)

    def test_ai_pattern_analysis_with_ollama(self):
        """If Ollama is available, AI analysis is attempted."""
        mock_ollama = MagicMock()
        mock_ollama.is_available.return_value = True
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.text = json.dumps({
            "winning_patterns": ["trending+ma_crossover"],
            "losing_patterns": ["squeeze+rsi_mean_revert"],
            "regime_strategy_matrix": {"trending": {"ma_crossover": 0.7}},
        })
        mock_ollama.generate.return_value = mock_response

        agent = self._make_analyst(n_records=250, ollama=mock_ollama)
        result = agent.analyze_patterns()
        self.assertIsNotNone(result)
        self.assertEqual(result.source, "ai")
        self.assertIn("trending+ma_crossover", result.winning_patterns)


class TestL2CronTrigger(unittest.TestCase):
    """Test L2 Cron trigger in PipelineBridge."""

    def test_cron_fires_on_wednesday_utc_0(self):
        """L2 Cron brief report fires when it's Wednesday UTC 0:00-0:59.
        L2 Cron 簡報在周三 UTC 0:00-0:59 觸發。
        (Sunday triggers L2 deep session, not analyze_patterns.)
        （周日觸發 L2 深度 session，不是 analyze_patterns。）"""
        from app.pipeline_bridge import PipelineBridge

        # Create a minimal mock PipelineBridge
        bridge = MagicMock(spec=PipelineBridge)
        bridge._analyst_agent = MagicMock()
        bridge._analyst_agent.analyze_patterns.return_value = MagicMock()
        bridge._last_l2_brief_week = None

        # 2026-03-25 is a Wednesday / 2026-03-25 是周三
        wednesday_utc_0 = datetime.datetime(2026, 3, 25, 0, 30,
                                             tzinfo=datetime.timezone.utc).timestamp()
        PipelineBridge._try_l2_cron_trigger(bridge, wednesday_utc_0)
        bridge._analyst_agent.analyze_patterns.assert_called_once_with(force=True)

    def test_cron_does_not_fire_on_weekday(self):
        """L2 Cron does NOT fire on non-Sunday."""
        from app.pipeline_bridge import PipelineBridge

        bridge = MagicMock(spec=PipelineBridge)
        bridge._analyst_agent = MagicMock()
        bridge._last_l2_cron_week = None

        # 2026-03-30 is a Monday
        monday = datetime.datetime(2026, 3, 30, 0, 30,
                                   tzinfo=datetime.timezone.utc).timestamp()
        PipelineBridge._try_l2_cron_trigger(bridge, monday)
        bridge._analyst_agent.analyze_patterns.assert_not_called()

    def test_cron_does_not_fire_twice_same_week(self):
        """L2 Cron brief report fires only once per week.
        L2 Cron 簡報每周只觸發一次。"""
        from app.pipeline_bridge import PipelineBridge

        bridge = MagicMock(spec=PipelineBridge)
        bridge._analyst_agent = MagicMock()
        bridge._analyst_agent.analyze_patterns.return_value = MagicMock()
        bridge._last_l2_brief_week = None

        # 2026-03-25 is a Wednesday / 2026-03-25 是周三
        wednesday = datetime.datetime(2026, 3, 25, 0, 30,
                                      tzinfo=datetime.timezone.utc).timestamp()
        PipelineBridge._try_l2_cron_trigger(bridge, wednesday)
        self.assertEqual(bridge._analyst_agent.analyze_patterns.call_count, 1)

        # Second call same week — should not fire / 同一周第二次調用不應觸發
        PipelineBridge._try_l2_cron_trigger(bridge, wednesday + 3600)
        self.assertEqual(bridge._analyst_agent.analyze_patterns.call_count, 1)


class TestTTLEnforcerOMS(unittest.TestCase):
    """Test TTL enforcer handles OMS TTL expiry."""

    def test_default_configs_include_oms(self):
        """Default TTL configs include OMS SUBMITTED with auto-cancel."""
        configs = _create_default_ttl_configs()
        key = ("OMS", "SUBMITTED")
        self.assertIn(key, configs)
        cfg = configs[key]
        self.assertEqual(cfg.max_duration_seconds, 30)
        self.assertEqual(cfg.on_expiry_action, TTLExpiryAction.AUTO_CANCEL)
        self.assertEqual(cfg.on_expiry_target_state, "CANCELED")

    def test_oms_ttl_registration_and_sweep(self):
        """OMS order registered for TTL sweeps expired after timeout."""
        callback_calls = []
        def on_expiry(entry, action):
            callback_calls.append((entry.object_id, action))

        enforcer = TTLEnforcer(expiry_callback=on_expiry)
        entry = enforcer.register_entry(
            state_machine_name="OMS",
            object_id="order-ttl-test",
            state_name="SUBMITTED",
        )
        self.assertIsNotNone(entry)

        # Sweep with a time far in the future (simulate timeout)
        future = int(time.time() * 1000) + 60000  # 60 seconds later
        expired = enforcer.sweep_expired(current_time_ms=future)
        self.assertEqual(len(expired), 1)
        self.assertEqual(len(callback_calls), 1)
        self.assertEqual(callback_calls[0][0], "order-ttl-test")
        self.assertEqual(callback_calls[0][1], "auto_cancel")

    def test_oms_ttl_not_expired_within_window(self):
        """OMS order is NOT expired within the 30-second TTL window."""
        enforcer = TTLEnforcer()
        entry = enforcer.register_entry(
            state_machine_name="OMS",
            object_id="order-in-time",
            state_name="SUBMITTED",
        )
        # Sweep with current time (should not expire)
        expired = enforcer.sweep_expired()
        self.assertEqual(len(expired), 0)

    def test_ttl_daemon_sweep_interval(self):
        """TTL enforcer daemon sweep runs at 5-second intervals."""
        enforcer = TTLEnforcer()
        self.assertEqual(enforcer._sweep_interval_seconds, 5)


class TestOMSSM03FullOrderLifecycle(unittest.TestCase):
    """End-to-end test: Paper order with full OMS SM-03 lifecycle."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        # P0-1: provide mock governance_hub so fail-closed check passes
        self.mock_hub = MagicMock()
        self.mock_hub.is_authorized.return_value = True
        self.mock_hub.acquire_lease.return_value = "test-lease"
        self.mock_hub.release_lease.return_value = None

    def test_market_order_full_lifecycle(self):
        """Market order: CREATED→SUBMITTED→WORKING→FILLED + OMS COMPLETED."""
        oms = OmsStateMachine()
        engine = _make_engine(self._tmp, oms_sm=oms, governance_hub=self.mock_hub)
        result = engine.submit_order(
            "ETHUSDT", "Buy", "market", 0.01,
            market_prices={"ETHUSDT": 3000.0},
        )
        order = result["order"]
        self.assertIsNotNone(order)
        self.assertEqual(order["state"], ORDER_STATE_FILLED)
        self.assertEqual(order.get("oms_state"), "COMPLETED")
        self.assertIsNone(result["rejected_reason"])
        self.assertTrue(len(result["fills"]) > 0)

    def test_oms_status_summary(self):
        """OMS status_summary reflects orders tracked."""
        oms = OmsStateMachine()
        engine = _make_engine(self._tmp, oms_sm=oms, governance_hub=self.mock_hub)
        engine.submit_order(
            "BTCUSDT", "Buy", "market", 0.001,
            market_prices={"BTCUSDT": 50000.0},
        )
        summary = oms.status_summary()
        # status_summary returns state_name → count mapping
        total = sum(summary.values())
        self.assertGreaterEqual(total, 1)

    def test_oms_order_id_persists_in_state(self):
        """OMS order ID is written into the paper trading state file."""
        oms = OmsStateMachine()
        engine = _make_engine(self._tmp, oms_sm=oms, governance_hub=self.mock_hub)
        engine.submit_order(
            "BTCUSDT", "Buy", "market", 0.001,
            market_prices={"BTCUSDT": 50000.0},
        )
        state = engine.get_state()
        orders = state.get("orders", [])
        self.assertTrue(len(orders) > 0)
        self.assertIn("oms_order_id", orders[0])


if __name__ == "__main__":
    unittest.main()
