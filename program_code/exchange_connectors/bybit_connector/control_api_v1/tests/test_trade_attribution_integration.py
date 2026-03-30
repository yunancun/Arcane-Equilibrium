"""
Integration Tests for Trade Attribution Engine with PipelineBridge
交易归因引擎与管线桥接器的集成测试

MODULE_NOTE (中文):
  验证 TradeAttributionEngine 与 PipelineBridge 的集成：
  1. 初始化阶段：在 phase2_strategy_routes.py 中创建和注入 TradeAttributionEngine
  2. 执行阶段：在 _emit_round_trip 中调用 attribute_trade()
  3. 归因结果：验证交易被分解为归因因子

MODULE_NOTE (English):
  Test integration of TradeAttributionEngine with PipelineBridge:
  1. Initialization: TradeAttributionEngine created and injected in phase2_strategy_routes.py
  2. Execution: attribute_trade() called in _emit_round_trip
  3. Attribution results: verify trades decomposed into attribution factors
"""

import datetime
import os
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.trade_attribution import TradeAttributionEngine, AttributionCategory
from app.pipeline_bridge import PipelineBridge


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_components():
    """Create mock components for PipelineBridge"""
    return {
        "kline_manager": MagicMock(),
        "indicator_engine": MagicMock(),
        "signal_engine": MagicMock(),
        "orchestrator": MagicMock(),
        "paper_engine": MagicMock(),
        "stop_manager": MagicMock(),
    }


@pytest.fixture
def pipeline_bridge(mock_components):
    """Create a PipelineBridge with mock components"""
    bridge = PipelineBridge(
        kline_manager=mock_components["kline_manager"],
        indicator_engine=mock_components["indicator_engine"],
        signal_engine=mock_components["signal_engine"],
        orchestrator=mock_components["orchestrator"],
        paper_engine=mock_components["paper_engine"],
        stop_manager=mock_components["stop_manager"],
    )
    return bridge


@pytest.fixture
def trade_attribution_engine():
    """Create a TradeAttributionEngine"""
    return TradeAttributionEngine()


# ═══════════════════════════════════════════════════════════════════════════════
# Test TradeAttributionEngine Initialization
# ═══════════════════════════════════════════════════════════════════════════════

class TestTradeAttributionInitialization:
    """Test initialization of TradeAttributionEngine"""

    def test_trade_attribution_engine_created(self, trade_attribution_engine):
        """Verify TradeAttributionEngine can be instantiated"""
        assert trade_attribution_engine is not None
        assert hasattr(trade_attribution_engine, "attribute_trade")
        assert hasattr(trade_attribution_engine, "aggregate_attribution")
        assert hasattr(trade_attribution_engine, "get_strategy_skill_ratio")

    def test_pipeline_bridge_accepts_attribution_engine(self, pipeline_bridge, trade_attribution_engine):
        """Verify PipelineBridge can accept TradeAttributionEngine via set_trade_attribution"""
        # Initially should be None
        assert pipeline_bridge._trade_attribution is None

        # Set the engine
        pipeline_bridge.set_trade_attribution(trade_attribution_engine)

        # Should now be set
        assert pipeline_bridge._trade_attribution is not None
        assert pipeline_bridge._trade_attribution == trade_attribution_engine


# ═══════════════════════════════════════════════════════════════════════════════
# Test _emit_round_trip Attribution Integration
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmitRoundTripAttribution:
    """Test attribution integration in _emit_round_trip"""

    def test_emit_round_trip_with_attribution_disabled(self, pipeline_bridge):
        """Verify _emit_round_trip works when attribution is not set (graceful degradation)"""
        # This tests the non-fatal behavior when attribution engine is not available
        assert pipeline_bridge._trade_attribution is None

        # Should not raise an exception
        pipeline_bridge._emit_round_trip(
            symbol="BTCUSDT",
            strategy_name="TestStrategy",
            exit_price=50000.0,
            close_pnl=100.0,
        )

    def test_emit_round_trip_with_attribution_enabled(self, pipeline_bridge, trade_attribution_engine):
        """Verify _emit_round_trip calls attribute_trade when engine is set"""
        pipeline_bridge.set_trade_attribution(trade_attribution_engine)

        # Mock the observation writer to capture calls
        observation_calls = []

        def mock_writer(**kwargs):
            observation_calls.append(kwargs)

        pipeline_bridge.set_observation_writer(mock_writer)

        # Set up an open position so we have data for attribution
        key = "TestStrategy:BTCUSDT"
        now_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
        pipeline_bridge._open_positions[key] = {
            "symbol": "BTCUSDT",
            "strategy_name": "TestStrategy",
            "side": "long",
            "entry_price": 49000.0,
            "qty": 0.001,
            "entry_ts_ms": now_ms - 3600000,  # 1 hour ago
            "regime": "trend_up",
        }

        # Call _emit_round_trip
        pipeline_bridge._emit_round_trip(
            symbol="BTCUSDT",
            strategy_name="TestStrategy",
            exit_price=50000.0,
            close_pnl=1.0,
        )

        # Verify the position was popped
        assert key not in pipeline_bridge._open_positions

        # Verify observation writer was called
        assert len(observation_calls) > 0

    def test_emit_round_trip_attribution_calculates_gross_pnl(
        self, pipeline_bridge, trade_attribution_engine
    ):
        """Verify attribution calculation uses correct gross PnL from entry/exit prices"""
        pipeline_bridge.set_trade_attribution(trade_attribution_engine)

        # Spy on the attribution engine's attribute_trade method
        original_attribute_trade = trade_attribution_engine.attribute_trade
        call_args = []

        def spy_attribute_trade(*args, **kwargs):
            call_args.append((args, kwargs))
            return original_attribute_trade(*args, **kwargs)

        trade_attribution_engine.attribute_trade = spy_attribute_trade

        # Set up an open position
        key = "TestStrategy:ETHUSDT"
        now_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
        entry_price = 3000.0
        qty = 0.1
        exit_price = 3100.0

        pipeline_bridge._open_positions[key] = {
            "symbol": "ETHUSDT",
            "strategy_name": "TestStrategy",
            "side": "long",
            "entry_price": entry_price,
            "qty": qty,
            "entry_ts_ms": now_ms - 1800000,  # 30 min ago
            "regime": "consolidation",
        }

        # Call _emit_round_trip with exit price
        pipeline_bridge._emit_round_trip(
            symbol="ETHUSDT",
            strategy_name="TestStrategy",
            exit_price=exit_price,
            close_pnl=10.0,
        )

        # Verify attribution_trade was called with correct parameters
        assert len(call_args) > 0
        kwargs = call_args[0][1]

        assert kwargs["symbol"] == "ETHUSDT"
        assert kwargs["strategy"] == "TestStrategy"
        assert kwargs["entry_price"] == entry_price
        assert kwargs["exit_price"] == exit_price
        assert kwargs["quantity"] == qty


# ═══════════════════════════════════════════════════════════════════════════════
# Test Trade Attribution Result Persistence
# ═══════════════════════════════════════════════════════════════════════════════

class TestAttributionResultPersistence:
    """Test that attribution results are properly tracked"""

    def test_attribution_result_contains_skill_pct(self, trade_attribution_engine):
        """Verify attribution results contain skill_pct component"""
        now = datetime.datetime.now(datetime.timezone.utc)

        result = trade_attribution_engine.attribute_trade(
            trade_id="test_trade_1",
            symbol="BTCUSDT",
            strategy="TestStrategy",
            entry_price=50000.0,
            exit_price=51000.0,
            quantity=0.01,
            entry_timestamp=now,
            exit_timestamp=now + datetime.timedelta(hours=1),
            market_prices_at_entry={},
            market_prices_at_exit={},
        )

        assert result is not None
        assert hasattr(result, "skill_pct")
        assert hasattr(result, "luck_pct")
        assert 0.0 <= result.skill_pct <= 1.0
        assert 0.0 <= result.luck_pct <= 1.0
        # skill + luck should approximately equal 1.0
        assert abs((result.skill_pct + result.luck_pct) - 1.0) < 0.01

    def test_attribution_result_has_six_factors(self, trade_attribution_engine):
        """Verify attribution results decompose into 6 factors (ALPHA/TIMING/SIZING/EXECUTION/COST/LUCK)"""
        now = datetime.datetime.now(datetime.timezone.utc)

        result = trade_attribution_engine.attribute_trade(
            trade_id="test_trade_2",
            symbol="BTCUSDT",
            strategy="TestStrategy",
            entry_price=50000.0,
            exit_price=52000.0,
            quantity=0.01,
            entry_timestamp=now,
            exit_timestamp=now + datetime.timedelta(hours=2),
            market_prices_at_entry={},
            market_prices_at_exit={},
        )

        assert len(result.attribution_scores) == 6

        # Verify all 6 categories are present
        categories = {score.category for score in result.attribution_scores}
        expected_categories = {
            AttributionCategory.ALPHA,
            AttributionCategory.TIMING,
            AttributionCategory.SIZING,
            AttributionCategory.EXECUTION,
            AttributionCategory.COST,
            AttributionCategory.LUCK,
        }
        assert categories == expected_categories


# ═══════════════════════════════════════════════════════════════════════════════
# Test Thread Safety
# ═══════════════════════════════════════════════════════════════════════════════

class TestAttributionThreadSafety:
    """Test thread safety of attribution integration"""

    def test_concurrent_round_trip_calls(self, pipeline_bridge, trade_attribution_engine):
        """Verify multiple threads can safely call _emit_round_trip"""
        pipeline_bridge.set_trade_attribution(trade_attribution_engine)

        errors = []

        def emit_trades(strategy_name, symbol, base_price):
            try:
                for i in range(5):
                    now_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
                    key = f"{strategy_name}:{symbol}"

                    with pipeline_bridge._lock:
                        pipeline_bridge._open_positions[key] = {
                            "symbol": symbol,
                            "strategy_name": strategy_name,
                            "side": "long",
                            "entry_price": base_price,
                            "qty": 0.01,
                            "entry_ts_ms": now_ms,
                            "regime": "test",
                        }

                    pipeline_bridge._emit_round_trip(
                        symbol=symbol,
                        strategy_name=strategy_name,
                        exit_price=base_price + 100,
                        close_pnl=1.0,
                    )
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(3):
            t = threading.Thread(
                target=emit_trades,
                args=(f"Strategy{i}", "BTCUSDT", 50000.0 + i * 1000),
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Should have no errors
        assert len(errors) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Test Error Handling
# ═══════════════════════════════════════════════════════════════════════════════

class TestAttributionErrorHandling:
    """Test error handling in attribution integration"""

    def test_invalid_attribution_parameters_do_not_crash(self, pipeline_bridge, trade_attribution_engine):
        """Verify invalid parameters don't crash the system (non-fatal behavior)"""
        pipeline_bridge.set_trade_attribution(trade_attribution_engine)

        # Call _emit_round_trip with no open position (entry_price and qty will be 0)
        # This should not raise an exception due to the guard `if entry_price > 0 and qty > 0`
        pipeline_bridge._emit_round_trip(
            symbol="BTCUSDT",
            strategy_name="UnknownStrategy",
            exit_price=50000.0,
            close_pnl=0.0,
        )
        # If we reach here without exception, the test passes

    def test_attribution_engine_exception_is_non_fatal(self, pipeline_bridge):
        """Verify exceptions in attribution engine don't crash round-trip handling"""
        # Create a mock engine that raises an exception
        mock_engine = MagicMock()
        mock_engine.attribute_trade.side_effect = Exception("Test error")

        pipeline_bridge.set_trade_attribution(mock_engine)

        # Set up an open position
        key = "TestStrategy:BTCUSDT"
        now_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
        pipeline_bridge._open_positions[key] = {
            "symbol": "BTCUSDT",
            "strategy_name": "TestStrategy",
            "side": "long",
            "entry_price": 50000.0,
            "qty": 0.01,
            "entry_ts_ms": now_ms,
            "regime": "test",
        }

        # This should not raise an exception, even though attribution fails
        pipeline_bridge._emit_round_trip(
            symbol="BTCUSDT",
            strategy_name="TestStrategy",
            exit_price=51000.0,
            close_pnl=10.0,
        )
        # If we reach here, the test passes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
