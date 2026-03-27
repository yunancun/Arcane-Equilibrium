"""
Tests for StopManager and ATR Position Sizing
止损管理器和 ATR 仓位计算测试
"""

import time
import pytest
from local_model_tools.stop_manager import (
    StopManager, StopConfig, TrackedPosition, compute_atr_position_size,
)


class TestStopConfig:
    def test_default_config(self):
        c = StopConfig()
        assert c.hard_stop_pct == 5.0
        assert c.trailing_stop_pct is None

    def test_validate_negative_hard_stop(self):
        with pytest.raises(ValueError):
            StopConfig(hard_stop_pct=-1).validate()

    def test_validate_negative_trailing(self):
        with pytest.raises(ValueError):
            StopConfig(trailing_stop_pct=-0.5).validate()


class TestStopManager:
    def test_track_and_untrack(self):
        sm = StopManager()
        sm.track_position("BTCUSDT", "long", 60000, 0.001, "MA_Crossover")
        status = sm.get_status()
        assert len(status["tracked_positions"]) == 1
        sm.untrack_position("BTCUSDT", "MA_Crossover")
        assert len(sm.get_status()["tracked_positions"]) == 0

    def test_hard_stop_long(self):
        sm = StopManager(StopConfig(hard_stop_pct=5.0))
        sm.track_position("BTCUSDT", "long", 60000, 0.001, "test")
        # Price at 57500 = -4.2%, not triggered
        result = sm.check_stops({"BTCUSDT": 57500})
        assert len(result) == 0
        # Price at 56900 = -5.2%, triggered
        result = sm.check_stops({"BTCUSDT": 56900})
        assert len(result) == 1
        assert result[0]["stop_type"] == "hard_stop"
        assert result[0]["side"] == "Sell"  # Close long = sell

    def test_hard_stop_short(self):
        sm = StopManager(StopConfig(hard_stop_pct=5.0))
        sm.track_position("ETHUSDT", "short", 3000, 0.1, "test")
        # Price at 3100, not triggered
        result = sm.check_stops({"ETHUSDT": 3100})
        assert len(result) == 0
        # Price at 3160 = +5.3%, triggered
        result = sm.check_stops({"ETHUSDT": 3160})
        assert len(result) == 1
        assert result[0]["stop_type"] == "hard_stop"
        assert result[0]["side"] == "Buy"  # Close short = buy

    def test_trailing_stop_long(self):
        sm = StopManager(StopConfig(hard_stop_pct=10.0, trailing_stop_pct=3.0))
        sm.track_position("BTCUSDT", "long", 60000, 0.001, "test")
        # Price goes up to 65000, then drops
        sm.check_stops({"BTCUSDT": 65000})  # Update best price
        # Drop to 63200 = -2.8% from best, not triggered
        result = sm.check_stops({"BTCUSDT": 63200})
        assert len(result) == 0
        # Drop to 62900 = -3.2% from best (65000), triggered
        result = sm.check_stops({"BTCUSDT": 62900})
        assert len(result) == 1
        assert result[0]["stop_type"] == "trailing_stop"

    def test_time_stop(self):
        sm = StopManager(StopConfig(hard_stop_pct=10.0, time_stop_hours=0.001))  # ~3.6 seconds
        sm.track_position("BTCUSDT", "long", 60000, 0.001, "test")
        # Immediately check - not enough time
        result = sm.check_stops({"BTCUSDT": 60000})
        # May or may not trigger depending on timing, let's just check the mechanism works
        # For a reliable test, manipulate entry_ts_ms
        pos_key = "test:BTCUSDT"
        with sm._lock:
            if pos_key in sm._positions:
                sm._positions[pos_key].entry_ts_ms = int(time.time() * 1000) - 10_000  # 10 seconds ago
        result = sm.check_stops({"BTCUSDT": 60000})
        assert len(result) == 1
        assert result[0]["stop_type"] == "time_stop"

    def test_auto_untrack_after_trigger(self):
        sm = StopManager(StopConfig(hard_stop_pct=1.0))
        sm.track_position("BTCUSDT", "long", 60000, 0.001, "test")
        sm.check_stops({"BTCUSDT": 59000})  # Triggers
        # Position should be auto-removed
        assert len(sm.get_status()["tracked_positions"]) == 0

    def test_multiple_positions(self):
        sm = StopManager(StopConfig(hard_stop_pct=5.0))
        sm.track_position("BTCUSDT", "long", 60000, 0.001, "MA")
        sm.track_position("ETHUSDT", "short", 3000, 0.1, "BB")
        assert len(sm.get_status()["tracked_positions"]) == 2
        # Only BTC stop triggered
        result = sm.check_stops({"BTCUSDT": 56000, "ETHUSDT": 3050})
        assert len(result) == 1
        assert result[0]["symbol"] == "BTCUSDT"

    def test_no_trigger_without_price(self):
        sm = StopManager(StopConfig(hard_stop_pct=1.0))
        sm.track_position("BTCUSDT", "long", 60000, 0.001, "test")
        result = sm.check_stops({"ETHUSDT": 3000})  # No BTC price
        assert len(result) == 0


class TestATRPositionSizing:
    def test_basic_sizing(self):
        # $10,000 account, 1% risk, ATR=$500, price=$60,000
        qty = compute_atr_position_size(10000, 1.0, 500, 2.0, 60000)
        # risk = $100, stop_distance = 500*2 = $1000
        # qty = 100 / 1000 = 0.1
        assert qty == 0.1

    def test_high_volatility_reduces_size(self):
        # Same but ATR=$2000 (4x higher vol)
        qty = compute_atr_position_size(10000, 1.0, 2000, 2.0, 60000)
        # risk = $100, stop = 2000*2 = $4000, qty = 100/4000 = 0.025
        assert qty == 0.025

    def test_min_qty_floor(self):
        # Very small account
        qty = compute_atr_position_size(100, 0.5, 500, 2.0, 60000, min_qty=0.001)
        # risk = $0.50, stop = $1000, qty = 0.0005 -> clamped to min 0.001
        assert qty == 0.001

    def test_max_qty_ceiling(self):
        # Very large account
        qty = compute_atr_position_size(1_000_000, 2.0, 100, 1.0, 60000, max_qty=10.0)
        # risk = $20,000, stop = $100, qty = 200 -> clamped to max 10.0
        assert qty == 10.0

    def test_zero_atr_returns_min(self):
        qty = compute_atr_position_size(10000, 1.0, 0, 2.0, 60000)
        assert qty == 0.001  # Default min

    def test_zero_balance_returns_min(self):
        qty = compute_atr_position_size(0, 1.0, 500, 2.0, 60000)
        assert qty == 0.001
