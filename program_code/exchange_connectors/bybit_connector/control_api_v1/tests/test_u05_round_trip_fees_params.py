"""
U-05: Round-trip record dynamic parameter snapshot and real fees tests.
U-05：Round-trip 记录动态参数快照和真实费用测试。

MODULE_NOTE (中文):
  验证 round-trip 记录中的费用和参数快照功能：
  1. fees_paid 来自真实成交记录（非硬编码 0）
  2. param_snapshot 包含开仓时动态参数
  3. 向后兼容（旧格式记录不崩溃）
  4. AnalystAgent 正确读取新字段

MODULE_NOTE (English):
  Tests for round-trip record fees and parameter snapshot:
  1. fees_paid from real fill records (not hardcoded 0)
  2. param_snapshot contains entry-time dynamic parameters
  3. Backward compatibility (old format records don't crash)
  4. AnalystAgent correctly reads new fields
"""

import sys
import os
import time
import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

# Path setup
_tests_dir = os.path.dirname(os.path.abspath(__file__))
_app_dir = os.path.join(os.path.dirname(_tests_dir), "app")
_control_api = os.path.dirname(_tests_dir)
_program_code = os.path.dirname(os.path.dirname(os.path.dirname(_control_api)))
if _control_api not in sys.path:
    sys.path.insert(0, _control_api)
if _program_code not in sys.path:
    sys.path.insert(0, _program_code)

from app.pipeline_bridge import PipelineBridge
from app.analyst_agent import TradeRecord, AnalystAgent, AnalystConfig


# ── Helpers / 辅助工具 ──

class MockPaperEngine:
    """Mock PaperTradingEngine with configurable fill records / 可配置成交记录的模拟交易引擎"""
    def __init__(self, fills=None):
        self._state = {
            "positions": {},
            "orders": [],
            "fills": fills or [],
        }

    def get_state(self):
        return self._state

    def submit_order(self, **kwargs):
        return {"order": {"order_id": "test_order"}, "rejected_reason": None, "fills": [], "close_pnl": 0.0}


@dataclass
class MockIntent:
    """Mock trade intent / 模拟交易意图"""
    symbol: str = "BTCUSDT"
    side: str = "Buy"
    order_type: str = "market"
    qty: float = 1.0
    confidence: float = 0.72
    strategy_name: str = "ma_crossover"
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {"_regime": "trending_up"}


class MockKlineManager:
    def get_latest_indicators(self, symbol):
        return {"atr": 500.0}


class MockIndicatorEngine:
    def get_indicators(self, symbol, timeframe):
        return {"atr": 500.0}


def _make_bridge(**overrides):
    """Create a PipelineBridge with mocked dependencies / 创建带模拟依赖的 PipelineBridge"""
    km = MockKlineManager()
    ie = MockIndicatorEngine()
    se = MagicMock()
    orch = MagicMock()
    engine = overrides.pop("engine", MockPaperEngine())
    stop_mgr = overrides.pop("_stop_mgr", None)
    bridge = PipelineBridge(
        kline_manager=km,
        indicator_engine=ie,
        signal_engine=se,
        orchestrator=orch,
        paper_engine=engine,
        stop_manager=stop_mgr,
    )
    bridge._km = km
    bridge._ie = ie
    for k, v in overrides.items():
        setattr(bridge, k, v)
    return bridge


# ═══════════════════════════════════════════════════════════════════════
# Test 1: fees_paid > 0 in round-trip (non-hardcoded)
# 测试 1：round-trip 中 fees_paid > 0（非硬编码 0）
# ═══════════════════════════════════════════════════════════════════════

class TestRoundTripFees:
    """Verify real fees flow into round-trip records / 验证真实费用流入 round-trip 记录"""

    def test_entry_fee_captured_on_position_open(self):
        """Entry fee from fill record should be stored in _open_positions.
        开仓费用应从成交记录中提取并存储到 _open_positions。"""
        fills = [{"symbol": "BTCUSDT", "side": "Buy", "fee": 0.15, "price": 50000.0}]
        engine = MockPaperEngine(fills=fills)
        bridge = _make_bridge(engine=engine)

        intent = MockIntent()
        bridge._on_position_open(intent, fill_price=50000.0, actual_qty=1.0)

        key = "ma_crossover:BTCUSDT"
        pos = bridge._open_positions[key]
        assert pos["entry_fee"] == 0.15, "Entry fee should be captured from fill record"

    def test_fees_paid_includes_entry_and_close(self):
        """Round-trip fees_paid = entry_fee + close_fee (not hardcoded 0).
        Round-trip 费用 = 开仓费 + 平仓费（非硬编码 0）。"""
        fills = [{"symbol": "BTCUSDT", "side": "Buy", "fee": 0.12, "price": 50000.0}]
        engine = MockPaperEngine(fills=fills)
        bus = MagicMock()
        bridge = _make_bridge(engine=engine, _message_bus=bus)

        intent = MockIntent()
        bridge._on_position_open(intent, fill_price=50000.0, actual_qty=1.0)

        # Close position with close_fee
        bridge._emit_round_trip("BTCUSDT", "ma_crossover", 51000.0, 1000.0, close_fee=0.13)

        # Verify MessageBus payload has real fees
        assert bus.send.called
        payload = bus.send.call_args[0][0].payload
        # fees_paid = entry_fee(0.12) + close_fee(0.13) = 0.25
        assert payload["fees_paid"] == pytest.approx(0.25, abs=0.001), \
            f"fees_paid should be entry+close={0.25}, got {payload['fees_paid']}"

    def test_fees_paid_calculation_correct(self):
        """Verify fees_paid = sum(entry_fee, close_fee) precisely.
        精确验证 fees_paid = entry_fee + close_fee。"""
        fills = [{"symbol": "ETHUSDT", "side": "Buy", "fee": 0.0875, "price": 3000.0}]
        engine = MockPaperEngine(fills=fills)

        # Mock trade_attribution to capture fees_paid
        attribution_mock = MagicMock()
        attr_result = MagicMock()
        attr_result.skill_pct = 0.5
        attr_result.luck_pct = 0.5
        attr_result.attribution_scores = []
        attribution_mock.attribute_trade.return_value = attr_result

        bridge = _make_bridge(engine=engine, _trade_attribution=attribution_mock)

        intent = MockIntent(symbol="ETHUSDT")
        bridge._on_position_open(intent, fill_price=3000.0, actual_qty=1.0)

        bridge._emit_round_trip("ETHUSDT", "ma_crossover", 3100.0, 100.0, close_fee=0.093)

        # Check TradeAttribution received real fees
        call_kwargs = attribution_mock.attribute_trade.call_args[1]
        expected_fees = 0.0875 + 0.093
        assert call_kwargs["fees_paid"] == pytest.approx(expected_fees, abs=0.001), \
            f"TradeAttribution.fees_paid should be {expected_fees}, got {call_kwargs['fees_paid']}"

    def test_zero_close_fee_still_includes_entry_fee(self):
        """When close_fee is 0 (default), fees_paid should still include entry_fee.
        当 close_fee 为 0（默认值）时，fees_paid 仍应包含 entry_fee。"""
        fills = [{"symbol": "BTCUSDT", "side": "Buy", "fee": 0.20, "price": 50000.0}]
        engine = MockPaperEngine(fills=fills)
        bus = MagicMock()
        bridge = _make_bridge(engine=engine, _message_bus=bus)

        intent = MockIntent()
        bridge._on_position_open(intent, fill_price=50000.0, actual_qty=1.0)

        # Close without explicit close_fee (defaults to 0)
        bridge._emit_round_trip("BTCUSDT", "ma_crossover", 51000.0, 1000.0)

        payload = bus.send.call_args[0][0].payload
        assert payload["fees_paid"] == pytest.approx(0.20, abs=0.001), \
            "fees_paid should include entry_fee even when close_fee is 0"


# ═══════════════════════════════════════════════════════════════════════
# Test 2: param_snapshot in round-trip records
# 测试 2：round-trip 记录中的参数快照
# ═══════════════════════════════════════════════════════════════════════

class TestParamSnapshot:
    """Verify dynamic parameter snapshot is captured and propagated / 验证动态参数快照被捕获并传播"""

    def test_param_snapshot_all_fields_present(self):
        """param_snapshot should contain all required fields.
        param_snapshot 应包含所有必需字段。"""
        fills = [{"symbol": "BTCUSDT", "side": "Buy", "fee": 0.10, "price": 50000.0}]
        engine = MockPaperEngine(fills=fills)
        stop_mgr = MagicMock()
        bridge = _make_bridge(engine=engine, _stop_mgr=stop_mgr)

        intent = MockIntent(confidence=0.72)
        bridge._on_position_open(intent, fill_price=50000.0, actual_qty=1.0)

        key = "ma_crossover:BTCUSDT"
        snapshot = bridge._open_positions[key].get("param_snapshot", {})

        expected_keys = {
            "atr_pct", "stop_distance_pct", "trail_activation_pct",
            "trail_distance_pct", "c_round_pct", "regime",
            "strategy_name", "confidence",
        }
        assert expected_keys.issubset(snapshot.keys()), \
            f"Missing keys: {expected_keys - set(snapshot.keys())}"

    def test_param_snapshot_propagated_to_message_bus(self):
        """param_snapshot should appear in MessageBus round-trip payload.
        param_snapshot 应出现在 MessageBus round-trip 负载中。"""
        fills = [{"symbol": "BTCUSDT", "side": "Buy", "fee": 0.10, "price": 50000.0}]
        engine = MockPaperEngine(fills=fills)
        bus = MagicMock()
        stop_mgr = MagicMock()
        bridge = _make_bridge(engine=engine, _message_bus=bus, _stop_mgr=stop_mgr)

        intent = MockIntent(confidence=0.85)
        bridge._on_position_open(intent, fill_price=50000.0, actual_qty=1.0)

        bridge._emit_round_trip("BTCUSDT", "ma_crossover", 51000.0, 1000.0, close_fee=0.10)

        payload = bus.send.call_args[0][0].payload
        assert "param_snapshot" in payload
        ps = payload["param_snapshot"]
        assert ps["confidence"] == pytest.approx(0.85, abs=0.01)
        assert ps["regime"] == "trending_up"
        assert ps["strategy_name"] == "ma_crossover"
        assert ps["stop_distance_pct"] > 0

    def test_param_snapshot_values_reasonable(self):
        """param_snapshot values should be within reasonable ranges.
        param_snapshot 值应在合理范围内。"""
        fills = [{"symbol": "BTCUSDT", "side": "Buy", "fee": 0.10, "price": 50000.0}]
        engine = MockPaperEngine(fills=fills)
        stop_mgr = MagicMock()
        bridge = _make_bridge(engine=engine, _stop_mgr=stop_mgr)

        intent = MockIntent()
        bridge._on_position_open(intent, fill_price=50000.0, actual_qty=1.0)

        key = "ma_crossover:BTCUSDT"
        ps = bridge._open_positions[key]["param_snapshot"]
        assert 0 <= ps["atr_pct"] <= 100
        assert 2.0 <= ps["stop_distance_pct"] <= 15.0
        assert 0 <= ps["confidence"] <= 1.0
        assert ps["c_round_pct"] >= 0


# ═══════════════════════════════════════════════════════════════════════
# Test 3: Backward compatibility (missing fields)
# 测试 3：向后兼容性（缺失字段）
# ═══════════════════════════════════════════════════════════════════════

class TestBackwardCompatibility:
    """Ensure system handles old-format records without param_snapshot / 确保系统能处理无 param_snapshot 的旧格式记录"""

    def test_emit_round_trip_without_pos_info(self):
        """When _open_positions has no entry (stale close), should not crash.
        当 _open_positions 没有条目时（过期关闭），不应崩溃。"""
        bridge = _make_bridge()
        # No position open — _emit_round_trip should still work (empty param_snapshot)
        bridge._emit_round_trip("BTCUSDT", "unknown", 50000.0, -100.0)
        # No crash = pass

    def test_trade_record_default_fields(self):
        """TradeRecord with no fees or param_snapshot should use defaults.
        没有费用或参数快照的 TradeRecord 应使用默认值。"""
        record = TradeRecord(
            trade_id="test_1",
            symbol="BTCUSDT",
            strategy="ma_crossover",
            pnl=100.0,
        )
        assert record.fees_paid == 0.0
        assert record.param_snapshot == {}
        assert record.net_pnl == 100.0

    def test_trade_record_net_pnl_subtracts_fees(self):
        """net_pnl should equal pnl - fees_paid.
        net_pnl 应等于 pnl - fees_paid。"""
        record = TradeRecord(pnl=100.0, fees_paid=5.0)
        assert record.net_pnl == pytest.approx(95.0)

    def test_trade_record_to_dict_includes_new_fields(self):
        """to_dict() should include fees_paid, net_pnl, and param_snapshot.
        to_dict() 应包含 fees_paid、net_pnl 和 param_snapshot。"""
        ps = {"atr_pct": 1.5, "regime": "trending"}
        record = TradeRecord(pnl=50.0, fees_paid=2.0, param_snapshot=ps)
        d = record.to_dict()
        assert d["fees_paid"] == 2.0
        assert d["net_pnl"] == pytest.approx(48.0)
        assert d["param_snapshot"]["atr_pct"] == 1.5

    def test_old_payload_without_new_fields(self):
        """AnalystAgent should handle old payloads without fees_paid/param_snapshot.
        AnalystAgent 应能处理没有 fees_paid/param_snapshot 的旧负载。"""
        agent = AnalystAgent(config=AnalystConfig())
        agent.start()

        old_payload = {
            "trade_id": "old_trade_1",
            "symbol": "BTCUSDT",
            "strategy": "ma_crossover",
            "direction": "long",
            "entry_price": 50000.0,
            "exit_price": 51000.0,
            "pnl": 1000.0,
            "hold_ms": 3600000,
            "regime": "trending",
            "timestamp_ms": int(time.time() * 1000),
            # NOTE: no fees_paid, no param_snapshot
        }

        # Simulate message
        from app.multi_agent_framework import AgentMessage, AgentRole, MessageType
        msg = AgentMessage(
            sender=AgentRole.EXECUTOR,
            receiver=AgentRole.ANALYST,
            message_type=MessageType.ROUND_TRIP_COMPLETE,
            priority=5,
            payload=old_payload,
        )
        agent.on_message(msg)

        # Should process without error
        assert agent._stats["trades_analyzed"] == 1
        # Record should have default fees
        record = agent._records[-1]
        assert record.fees_paid == 0.0
        assert record.param_snapshot == {}


# ═══════════════════════════════════════════════════════════════════════
# Test 4: AnalystAgent reads new fields correctly
# 测试 4：AnalystAgent 正确读取新字段
# ═══════════════════════════════════════════════════════════════════════

class TestAnalystAgentNewFields:
    """Verify AnalystAgent correctly processes round-trip records with new fields.
    验证 AnalystAgent 正确处理包含新字段的 round-trip 记录。"""

    def test_analyst_receives_fees_and_snapshot(self):
        """AnalystAgent should store fees_paid and param_snapshot from payload.
        AnalystAgent 应从负载中存储 fees_paid 和 param_snapshot。"""
        agent = AnalystAgent(config=AnalystConfig())
        agent.start()

        from app.multi_agent_framework import AgentMessage, AgentRole, MessageType
        payload = {
            "trade_id": "test_with_fees",
            "symbol": "ETHUSDT",
            "strategy": "trend_follow",
            "direction": "long",
            "entry_price": 3000.0,
            "exit_price": 3100.0,
            "pnl": 100.0,
            "hold_ms": 7200000,
            "regime": "trending_up",
            "timestamp_ms": int(time.time() * 1000),
            "fees_paid": 0.25,
            "param_snapshot": {
                "atr_pct": 1.2,
                "stop_distance_pct": 3.5,
                "trail_activation_pct": 1.75,
                "trail_distance_pct": 5.0,
                "c_round_pct": 0.02,
                "regime": "trending_up",
                "strategy_name": "trend_follow",
                "confidence": 0.8,
            },
        }

        msg = AgentMessage(
            sender=AgentRole.EXECUTOR,
            receiver=AgentRole.ANALYST,
            message_type=MessageType.ROUND_TRIP_COMPLETE,
            priority=5,
            payload=payload,
        )
        agent.on_message(msg)

        record = agent._records[-1]
        assert record.fees_paid == pytest.approx(0.25)
        assert record.param_snapshot["confidence"] == 0.8
        assert record.param_snapshot["atr_pct"] == 1.2
        assert record.net_pnl == pytest.approx(99.75)

    def test_analyst_multiple_records_mixed_format(self):
        """AnalystAgent handles mix of old and new format records.
        AnalystAgent 能处理新旧格式混合的记录。"""
        agent = AnalystAgent(config=AnalystConfig())
        agent.start()

        from app.multi_agent_framework import AgentMessage, AgentRole, MessageType

        # Old format
        old_msg = AgentMessage(
            sender=AgentRole.EXECUTOR,
            receiver=AgentRole.ANALYST,
            message_type=MessageType.ROUND_TRIP_COMPLETE,
            priority=5,
            payload={"trade_id": "old", "symbol": "BTCUSDT", "strategy": "s1",
                      "pnl": 50.0, "direction": "long"},
        )
        # New format
        new_msg = AgentMessage(
            sender=AgentRole.EXECUTOR,
            receiver=AgentRole.ANALYST,
            message_type=MessageType.ROUND_TRIP_COMPLETE,
            priority=5,
            payload={"trade_id": "new", "symbol": "ETHUSDT", "strategy": "s2",
                      "pnl": 80.0, "direction": "short", "fees_paid": 1.5,
                      "param_snapshot": {"confidence": 0.9}},
        )

        agent.on_message(old_msg)
        agent.on_message(new_msg)

        assert agent._stats["trades_analyzed"] == 2
        assert agent._records[0].fees_paid == 0.0  # old format default
        assert agent._records[1].fees_paid == 1.5   # new format real fee


# ═══════════════════════════════════════════════════════════════════════
# Test 5: on_tick_result passes close_fee
# 测试 5：on_tick_result 传递平仓费用
# ═══════════════════════════════════════════════════════════════════════

class TestTickPathFees:
    """Verify tick-path closes pass close_fee to _emit_round_trip.
    验证 tick 路径关闭时将 close_fee 传递给 _emit_round_trip。"""

    def test_on_tick_result_passes_close_fee(self):
        """on_tick_result should extract fee from fill and pass to _emit_round_trip.
        on_tick_result 应从成交记录提取费用并传递给 _emit_round_trip。"""
        fills = [{"symbol": "BTCUSDT", "side": "Buy", "fee": 0.10, "price": 50000.0}]
        engine = MockPaperEngine(fills=fills)
        bus = MagicMock()
        bridge = _make_bridge(engine=engine, _message_bus=bus)

        # Open a position
        intent = MockIntent()
        bridge._on_position_open(intent, fill_price=50000.0, actual_qty=1.0)

        # Simulate tick close fill
        tick_result = {
            "fills": [{
                "symbol": "BTCUSDT",
                "side": "Sell",  # closing a long
                "price": 51000.0,
                "fee": 0.13,
            }],
        }
        bridge.on_tick_result(tick_result)

        assert bus.send.called
        payload = bus.send.call_args[0][0].payload
        # entry_fee=0.10, close_fee=0.13 → total=0.23
        assert payload["fees_paid"] == pytest.approx(0.23, abs=0.001)


# ═══════════════════════════════════════════════════════════════════════
# Test 6: _check_stops path passes close_fee
# 测试 6：_check_stops 路径传递平仓费用
# ═══════════════════════════════════════════════════════════════════════

class TestStopPathFees:
    """Verify stop-loss path extracts and passes close_fee.
    验证止损路径提取并传递平仓费用。"""

    def test_check_stops_extracts_fee_from_result(self):
        """_check_stops should extract fee from stop order fills.
        _check_stops 应从止损单成交记录提取费用。"""
        fills = [{"symbol": "BTCUSDT", "side": "Buy", "fee": 0.10, "price": 50000.0}]
        engine = MockPaperEngine(fills=fills)

        # Mock engine.submit_order to return a fill with fee
        engine.submit_order = MagicMock(return_value={
            "order": {"order_id": "stop_order"},
            "rejected_reason": None,
            "fills": [{"symbol": "BTCUSDT", "side": "Sell", "price": 47500.0, "fee": 0.095}],
            "close_pnl": -2500.0,
        })
        engine.get_state = MagicMock(return_value={
            "positions": {"BTCUSDT": {"qty": 1.0}},
            "fills": fills,  # preserve fills so _on_position_open can find entry_fee
        })

        stop_mgr = MagicMock()
        stop_mgr.check_stops.return_value = [{
            "symbol": "BTCUSDT",
            "side": "Sell",
            "qty": 1.0,
            "stop_type": "hard_stop",
            "reason": "ATR stop triggered",
            "strategy_name": "ma_crossover",
            "current_price": 47500.0,
            "entry_price": 50000.0,
        }]

        bus = MagicMock()
        bridge = _make_bridge(engine=engine, _stop_mgr=stop_mgr, _message_bus=bus)

        # Open a position first
        intent = MockIntent()
        bridge._on_position_open(intent, fill_price=50000.0, actual_qty=1.0)

        # Trigger stops
        bridge._latest_prices = {"BTCUSDT": 47500.0}
        bridge._check_stops()

        assert bus.send.called
        payload = bus.send.call_args[0][0].payload
        # entry_fee=0.10, close_fee=0.095 → total=0.195
        assert payload["fees_paid"] == pytest.approx(0.195, abs=0.001)
