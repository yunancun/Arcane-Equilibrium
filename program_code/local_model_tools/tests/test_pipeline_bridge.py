"""
Tests for PipelineBridge
管线桥接器测试
"""

import sys
import os
import time

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
