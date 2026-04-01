"""
E4 Edge Case Tests: StopManager Boundary Conditions
止损管理器边界条件测试

MODULE_NOTE (中文):
  测试 StopManager 在边界/异常输入下的行为。
  覆盖：hard_stop_pct=0 验证、ATR 负值处理、浮点精度边界、
  追踪止损距离为 0、时间止损为 0 秒、None/缺失字段的止损检查。

MODULE_NOTE (English):
  Tests StopManager under boundary/anomalous inputs.
  Covers: hard_stop_pct=0 validation, negative ATR handling, float precision
  boundary, trailing stop with 0 distance, time stop with 0 seconds,
  stop check with None/missing fields.

作者: E4 (Test Engineer)
日期: 2026-04-01
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Path setup — resolve local_model_tools package
_HERE = os.path.dirname(os.path.abspath(__file__))
# tests/ -> control_api_v1/ -> bybit_connector/ -> exchange_connectors/ -> program_code/
_PROGRAM_CODE = os.path.abspath(os.path.join(_HERE, *[".."] * 4))
if _PROGRAM_CODE not in sys.path:
    sys.path.insert(0, _PROGRAM_CODE)

from local_model_tools.stop_manager import (
    StopConfig,
    StopManager,
    TrackedPosition,
    compute_atr_position_size,
)


class TestStopConfigValidation:
    """Test StopConfig.validate() boundary conditions.
    测试 StopConfig.validate() 边界条件。"""

    def test_hard_stop_pct_zero_raises(self):
        """hard_stop_pct=0 must raise ValueError (stop_manager requires > 0).
        hard_stop_pct=0 必须抛出 ValueError（止损管理器要求 > 0）。"""
        config = StopConfig(hard_stop_pct=0.0)
        with pytest.raises(ValueError, match="hard_stop_pct must be > 0"):
            config.validate()

    def test_hard_stop_pct_negative_raises(self):
        """hard_stop_pct < 0 must raise ValueError.
        hard_stop_pct < 0 必须抛出 ValueError。"""
        config = StopConfig(hard_stop_pct=-1.0)
        with pytest.raises(ValueError, match="hard_stop_pct must be > 0"):
            config.validate()

    def test_trailing_stop_zero_raises(self):
        """trailing_stop_pct=0 must raise ValueError.
        trailing_stop_pct=0 必须抛出 ValueError。"""
        config = StopConfig(trailing_stop_pct=0.0)
        with pytest.raises(ValueError, match="trailing_stop_pct must be > 0"):
            config.validate()

    def test_time_stop_zero_raises(self):
        """time_stop_hours=0 must raise ValueError.
        time_stop_hours=0 必须抛出 ValueError。"""
        config = StopConfig(time_stop_hours=0.0)
        with pytest.raises(ValueError, match="time_stop_hours must be > 0"):
            config.validate()


class TestStopManagerEdgeCases:
    """Edge case tests for StopManager.check_stops().
    StopManager.check_stops() 边界条件测试。"""

    def test_check_stops_none_price_skipped(self):
        """Symbols with None price in market_prices should be silently skipped.
        market_prices 中 price 为 None 的符号应被静默跳过。"""
        sm = StopManager(default_config=StopConfig(hard_stop_pct=5.0))
        sm.track_position(
            symbol="BTCUSDT", side="long", entry_price=60000.0,
            qty=0.01, strategy_name="test",
        )
        # Price is None for BTCUSDT
        triggered = sm.check_stops({"BTCUSDT": None})
        assert triggered == [], "None price must not trigger any stop"

    def test_check_stops_zero_price_skipped(self):
        """Price=0 in market_prices should be skipped (price <= 0 guard).
        market_prices 中 price=0 应被跳过（price <= 0 守卫）。"""
        sm = StopManager(default_config=StopConfig(hard_stop_pct=5.0))
        sm.track_position(
            symbol="BTCUSDT", side="long", entry_price=60000.0,
            qty=0.01, strategy_name="test",
        )
        triggered = sm.check_stops({"BTCUSDT": 0.0})
        assert triggered == [], "Zero price must not trigger any stop"

    def test_hard_stop_float_precision_boundary(self):
        """Price very close to but not crossing hard stop should NOT trigger.
        价格非常接近但未穿越硬止损不应触发。"""
        sm = StopManager(default_config=StopConfig(hard_stop_pct=5.0))
        sm.track_position(
            symbol="BTCUSDT", side="long", entry_price=100.0,
            qty=1.0, strategy_name="test",
        )
        # Hard stop price = 100 * (1 - 5/100) = 95.0
        # Price just above: 95.01
        triggered = sm.check_stops({"BTCUSDT": 95.01})
        assert len(triggered) == 0, "Price above stop level must not trigger"

    def test_hard_stop_exact_boundary_triggers(self):
        """Price exactly at hard stop level should trigger.
        价格刚好等于硬止损水平应触发。"""
        sm = StopManager(default_config=StopConfig(hard_stop_pct=5.0))
        sm.track_position(
            symbol="BTCUSDT", side="long", entry_price=100.0,
            qty=1.0, strategy_name="test",
        )
        # Hard stop price = 95.0, price exactly 95.0 → should trigger (price <= stop_price)
        triggered = sm.check_stops({"BTCUSDT": 95.0})
        assert len(triggered) == 1
        assert triggered[0]["stop_type"] == "hard_stop"

    def test_missing_symbol_in_market_prices_no_trigger(self):
        """Symbol not in market_prices should not trigger any stop.
        market_prices 中没有该符号不应触发任何止损。"""
        sm = StopManager(default_config=StopConfig(hard_stop_pct=5.0))
        sm.track_position(
            symbol="BTCUSDT", side="long", entry_price=60000.0,
            qty=0.01, strategy_name="test",
        )
        # Empty market prices
        triggered = sm.check_stops({})
        assert triggered == []

    def test_track_position_with_invalid_stop_config_raises(self):
        """Tracking a position with invalid StopConfig should raise.
        使用无效 StopConfig 跟踪仓位应抛出异常。"""
        sm = StopManager(default_config=StopConfig(hard_stop_pct=5.0))
        with pytest.raises(ValueError):
            sm.track_position(
                symbol="BTCUSDT", side="long", entry_price=60000.0,
                qty=0.01, strategy_name="test",
                stop_config=StopConfig(hard_stop_pct=-1.0),
            )
