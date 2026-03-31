"""
Tests for PipelineBridge
管线桥接器测试

P1-10: 新增 3 个测试验证 Perception Plane register_data() 被正确调用。
       测试覆盖：注入路径 + on_tick 数据注册 + PerceptionPlane.get_stats() 统计递增。
"""

import sys
import os
import time
from unittest.mock import MagicMock, call

# Add paths
_tests_dir = os.path.dirname(os.path.abspath(__file__))
_local_model_tools = os.path.dirname(_tests_dir)
_program_code = os.path.dirname(_local_model_tools)
_control_api = os.path.join(_program_code, "exchange_connectors", "bybit_connector", "control_api_v1")
if _control_api not in sys.path:
    sys.path.insert(0, _control_api)
if _program_code not in sys.path:
    sys.path.insert(0, _program_code)

from app.pipeline_bridge import PipelineBridge
from app.perception_data_plane import PerceptionPlane, DataSourceType, CognitiveLevel
from local_model_tools.kline_manager import KlineManager
from local_model_tools.indicator_engine import IndicatorEngine
from local_model_tools.signal_generator import SignalEngine
from local_model_tools.strategy_orchestrator import StrategyOrchestrator


class MockPaperEngine:
    """Mock PaperTradingEngine for testing"""
    def __init__(self):
        self.submitted_orders = []
        self._state = {"positions": [], "orders": []}

    def submit_order(self, **kwargs):
        self.submitted_orders.append(kwargs)
        return {"order": {"id": len(self.submitted_orders)}, "rejected_reason": None}

    def get_state(self):
        return self._state


class TestPipelineBridge:
    def setup_method(self):
        self.km = KlineManager(symbols=["BTCUSDT"], timeframes=["1m"])
        self.ie = IndicatorEngine(kline_manager=self.km)
        self.se = SignalEngine()
        self.ie.register_on_update(self.se.on_indicators_update)
        self.orch = StrategyOrchestrator(
            kline_manager=self.km, indicator_engine=self.ie, signal_engine=self.se,
        )
        self.engine = MockPaperEngine()
        self.bridge = PipelineBridge(
            kline_manager=self.km,
            indicator_engine=self.ie,
            signal_engine=self.se,
            orchestrator=self.orch,
            paper_engine=self.engine,
        )

    def test_inactive_by_default(self):
        assert not self.bridge.is_active

    def test_activate_deactivate(self):
        self.bridge.activate()
        assert self.bridge.is_active
        self.bridge.deactivate()
        assert not self.bridge.is_active

    def test_tick_when_inactive_does_nothing(self):
        event = {"symbol": "BTCUSDT", "last_price": 60000.0, "ts_ms": int(time.time() * 1000)}
        self.bridge.on_tick(event)
        stats = self.bridge.get_stats()
        assert stats["ticks_received"] == 0

    def test_tick_when_active_feeds_kline_manager(self):
        self.bridge.activate()
        ts = int(time.time() * 1000)
        for i in range(3):
            event = {"symbol": "BTCUSDT", "last_price": 60000.0 + i * 100, "ts_ms": ts + i * 1000}
            self.bridge.on_tick(event)
        stats = self.bridge.get_stats()
        assert stats["ticks_received"] == 3
        km_stats = self.km.get_stats()
        assert km_stats["total_ticks_processed"] == 3

    def test_stats(self):
        stats = self.bridge.get_stats()
        assert stats["component"] == "pipeline_bridge"
        assert "ticks_received" in stats
        assert "intents_submitted" in stats


class TestPipelineBridgePerceptionPlane:
    """
    P1-10: Tests that register_data() is actually called when PerceptionPlane is injected.
    P1-10：验证注入感知平面后 register_data() 被正确调用。

    These tests cover the critical gap where _perception_plane was always None
    in practice due to missing injection, meaning register_data() was never invoked.
    这些测试覆盖了感知平面因注入缺失导致 register_data() 零调用的关键问题。
    """

    def setup_method(self):
        self.km = KlineManager(symbols=["BTCUSDT"], timeframes=["1m"])
        self.ie = IndicatorEngine(kline_manager=self.km)
        self.se = SignalEngine()
        self.ie.register_on_update(self.se.on_indicators_update)
        self.orch = StrategyOrchestrator(
            kline_manager=self.km, indicator_engine=self.ie, signal_engine=self.se,
        )
        self.engine = MockPaperEngine()
        self.bridge = PipelineBridge(
            kline_manager=self.km,
            indicator_engine=self.ie,
            signal_engine=self.se,
            orchestrator=self.orch,
            paper_engine=self.engine,
        )

    def test_set_perception_plane_injects_instance(self):
        """P1-10 Test 1: set_perception_plane() stores the instance so on_tick can use it.
        验证 set_perception_plane() 正确存储实例，使 on_tick 能访问感知平面。
        """
        plane = PerceptionPlane()
        # Before injection: _perception_plane is None
        assert self.bridge._perception_plane is None
        # After injection: _perception_plane is the real PerceptionPlane
        self.bridge.set_perception_plane(plane)
        assert self.bridge._perception_plane is plane

    def test_on_tick_calls_register_data_when_perception_plane_injected(self):
        """P1-10 Test 2: on_tick() calls register_data() with EXCHANGE_WS + FACT when PerceptionPlane is set.
        验证 on_tick() 注入感知平面后，使用 EXCHANGE_WS + FACT 调用 register_data()。
        """
        mock_plane = MagicMock()
        self.bridge.set_perception_plane(mock_plane)
        self.bridge.activate()

        ts = int(time.time() * 1000)
        event = {"symbol": "BTCUSDT", "last_price": 60000.0, "ts_ms": ts}
        self.bridge.on_tick(event)

        # register_data must have been called at least once
        assert mock_plane.register_data.called, (
            "register_data() was never called — Perception Plane is still dead (P1-10)"
        )
        # Verify the call used correct source_type and cognitive_level (EX-07 §1)
        kwargs = mock_plane.register_data.call_args.kwargs
        assert kwargs["source_type"] == DataSourceType.EXCHANGE_WS, (
            "Expected source_type=EXCHANGE_WS (exchange fact), got %s" % kwargs.get("source_type")
        )
        assert kwargs["cognitive_level"] == CognitiveLevel.FACT, (
            "Expected cognitive_level=FACT for WS price data (EX-07 §1), got %s" % kwargs.get("cognitive_level")
        )
        assert kwargs["symbols"] == ["BTCUSDT"], (
            "Expected symbols=['BTCUSDT'], got %s" % kwargs.get("symbols")
        )

    def test_perception_plane_stats_increment_on_tick(self):
        """P1-10 Test 3: Real PerceptionPlane.get_stats() shows objects_registered increments after on_tick.
        使用真实 PerceptionPlane 验证 get_stats() 中 objects_registered 在 on_tick 后递增。
        """
        plane = PerceptionPlane()
        self.bridge.set_perception_plane(plane)
        self.bridge.activate()

        stats_before = plane.get_stats()
        registered_before = stats_before["objects_registered"]

        ts = int(time.time() * 1000)
        for i in range(3):
            event = {"symbol": "BTCUSDT", "last_price": 60000.0 + i * 10, "ts_ms": ts + i * 1000}
            self.bridge.on_tick(event)

        stats_after = plane.get_stats()
        registered_after = stats_after["objects_registered"]

        assert registered_after > registered_before, (
            "PerceptionPlane.objects_registered did not increment after 3 ticks — "
            "register_data() is still zero-called (P1-10). "
            "Before=%d, After=%d" % (registered_before, registered_after)
        )
