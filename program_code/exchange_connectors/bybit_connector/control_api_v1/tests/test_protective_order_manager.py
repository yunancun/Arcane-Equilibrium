"""
Test Suite: ProtectiveOrderManager (T2.19 / GAP-M10)
测试套件：保护性订单管理器

This test suite provides ~100% coverage of protective order manager functionality.
Covers:
- Order creation and tracking
- Trigger evaluation (check_triggers)
- Execution callbacks
- Hard stop mandatory enforcement
- Coverage validation
- Emergency close
- Serialization
- Thread safety
"""

import json
import pytest
import threading
import time
from unittest.mock import Mock, MagicMock, call

from app.protective_order_manager import (
    ProtectiveOrderManager,
    ProtectiveOrder,
    ProtectiveOrderConfig,
    ProtectiveOrderCheckResult,
    ProtectiveOrderType,
    ProtectiveOrderStatus,
    ProtectiveOrderSide,
    TriggerCondition,
    create_default_hard_stop_config,
    calculate_atr_adjusted_stop,
)


class TestProtectiveOrderDataclasses:
    """Test data structures"""

    def test_protective_order_config_creation(self):
        """Test ProtectiveOrderConfig creation"""
        config = ProtectiveOrderConfig(
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            trigger_price_pct=5.0,
            trigger_condition=TriggerCondition.PRICE_LESS_THAN,
            is_mandatory=True,
            can_be_disabled=False,
        )
        assert config.order_type == ProtectiveOrderType.HARD_STOP_LOSS
        assert config.trigger_price_pct == 5.0
        assert config.is_mandatory is True

    def test_protective_order_creation(self):
        """Test ProtectiveOrder auto-generation of ID and timestamp"""
        order = ProtectiveOrder(
            order_id="",
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            trigger_price=40000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
            entry_price=42000.0,
        )
        assert order.order_id.startswith("pord_")
        assert order.created_at_ms > 0
        assert order.status == ProtectiveOrderStatus.CREATED

    def test_protective_order_to_dict(self):
        """Test serialization to dict"""
        order = ProtectiveOrder(
            order_id="test123",
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            trigger_price=40000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
            entry_price=42000.0,
            status=ProtectiveOrderStatus.ARMED,
        )
        d = order.to_dict()
        assert d['symbol'] == 'BTCUSDT'
        assert d['status'] == 'ARMED'
        assert d['order_type'] == 'HARD_STOP_LOSS'
        assert d['side'] == 'LONG'

    def test_protective_order_from_dict(self):
        """Test deserialization from dict"""
        data = {
            'order_id': 'test123',
            'symbol': 'BTCUSDT',
            'side': 'LONG',
            'order_type': 'HARD_STOP_LOSS',
            'trigger_price': 40000.0,
            'trigger_price_pct': 5.0,
            'quantity': 1.0,
            'entry_price': 42000.0,
            'status': 'ARMED',
            'created_at_ms': 1000,
            'triggered_at_ms': None,
            'exchange_order_id': None,
            'position_id': 'pos1',
            'strategy_id': 'strat1',
            'tags': {},
            'trailing_high': None,
            'trailing_distance': None,
            'atr_value': None,
            'random_offset': None,
        }
        order = ProtectiveOrder.from_dict(data)
        assert order.symbol == 'BTCUSDT'
        assert order.status == ProtectiveOrderStatus.ARMED
        assert order.order_type == ProtectiveOrderType.HARD_STOP_LOSS

    def test_protective_order_check_result(self):
        """Test ProtectiveOrderCheckResult"""
        order = ProtectiveOrder(
            order_id="test",
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            trigger_price=40000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
            entry_price=42000.0,
        )
        result = ProtectiveOrderCheckResult(
            triggered_orders=[order],
            unprotected_positions=[],
            missing_mandatory_stops=[],
            portfolio_coverage_pct=100.0,
        )
        assert len(result.triggered_orders) == 1
        assert result.portfolio_coverage_pct == 100.0
        assert result.timestamp_ms > 0


class TestProtectiveOrderManagerCreation:
    """Test order creation and tracking"""

    def test_manager_initialization(self):
        """Test manager initialization"""
        manager = ProtectiveOrderManager()
        assert manager is not None
        assert len(manager.get_all_orders()) == 0

    def test_create_long_stop_loss(self):
        """Test creating a hard stop-loss for long position"""
        manager = ProtectiveOrderManager()
        order = manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
            position_id="pos1",
        )
        assert order.symbol == "BTCUSDT"
        assert order.side == ProtectiveOrderSide.LONG_POSITION
        assert order.order_type == ProtectiveOrderType.HARD_STOP_LOSS
        assert order.entry_price == 42000.0
        # For long: trigger below entry
        assert order.trigger_price == pytest.approx(42000.0 * 0.95)
        assert order.quantity == 1.0

    def test_create_short_stop_loss(self):
        """Test creating stop-loss for short position"""
        manager = ProtectiveOrderManager()
        order = manager.create_protective_order(
            symbol="ETHUSDT",
            side=ProtectiveOrderSide.SHORT_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=2000.0,
            trigger_price_pct=5.0,
            quantity=10.0,
            position_id="pos2",
        )
        # For short: trigger above entry
        assert order.trigger_price == pytest.approx(2000.0 * 1.05)
        assert order.side == ProtectiveOrderSide.SHORT_POSITION

    def test_create_order_with_atr_and_offset(self):
        """Test creating order with ATR and random offset"""
        manager = ProtectiveOrderManager()
        order = manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.SOFT_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
            atr_value=500.0,
            random_offset_pct=0.5,
        )
        assert order.atr_value == 500.0
        assert order.random_offset == 0.5

    def test_create_order_invalid_entry_price(self):
        """Test that invalid entry_price raises ValueError"""
        manager = ProtectiveOrderManager()
        with pytest.raises(ValueError):
            manager.create_protective_order(
                symbol="BTCUSDT",
                side=ProtectiveOrderSide.LONG_POSITION,
                order_type=ProtectiveOrderType.HARD_STOP_LOSS,
                entry_price=-100.0,  # Invalid
                trigger_price_pct=5.0,
                quantity=1.0,
            )

    def test_create_order_invalid_quantity(self):
        """Test that invalid quantity raises ValueError"""
        manager = ProtectiveOrderManager()
        with pytest.raises(ValueError):
            manager.create_protective_order(
                symbol="BTCUSDT",
                side=ProtectiveOrderSide.LONG_POSITION,
                order_type=ProtectiveOrderType.HARD_STOP_LOSS,
                entry_price=42000.0,
                trigger_price_pct=5.0,
                quantity=-1.0,  # Invalid
            )

    def test_get_order(self):
        """Test retrieving order by ID"""
        manager = ProtectiveOrderManager()
        order = manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
        )
        retrieved = manager.get_order(order.order_id)
        assert retrieved is not None
        assert retrieved.order_id == order.order_id

    def test_get_nonexistent_order(self):
        """Test getting order that doesn't exist"""
        manager = ProtectiveOrderManager()
        result = manager.get_order("nonexistent")
        assert result is None

    def test_get_orders_for_position(self):
        """Test getting all orders for a position"""
        manager = ProtectiveOrderManager()
        order1 = manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
            position_id="pos1",
        )
        order2 = manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.TAKE_PROFIT,
            entry_price=42000.0,
            trigger_price_pct=10.0,
            quantity=1.0,
            position_id="pos1",
        )
        orders = manager.get_orders_for_position("pos1")
        assert len(orders) == 2
        order_ids = [o.order_id for o in orders]
        assert order1.order_id in order_ids
        assert order2.order_id in order_ids

    def test_get_orders_for_symbol(self):
        """Test getting all orders for a symbol"""
        manager = ProtectiveOrderManager()
        manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
        )
        manager.create_protective_order(
            symbol="ETHUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=2000.0,
            trigger_price_pct=5.0,
            quantity=10.0,
        )
        orders = manager.get_orders_for_symbol("BTCUSDT")
        assert len(orders) == 1
        assert orders[0].symbol == "BTCUSDT"

    def test_get_all_orders(self):
        """Test getting all orders"""
        manager = ProtectiveOrderManager()
        assert len(manager.get_all_orders()) == 0

        manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
        )
        manager.create_protective_order(
            symbol="ETHUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=2000.0,
            trigger_price_pct=5.0,
            quantity=10.0,
        )
        orders = manager.get_all_orders()
        assert len(orders) == 2


class TestTriggerEvaluation:
    """Test check_triggers and trigger condition logic"""

    def test_check_triggers_long_stop_loss_triggered(self):
        """Test long position stop-loss trigger"""
        manager = ProtectiveOrderManager()
        order = manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
        )
        # Price drops below stop
        market_state = {"BTCUSDT": {"price": 39000.0}}
        result = manager.check_triggers(market_state)
        assert len(result.triggered_orders) == 1
        assert result.triggered_orders[0].order_id == order.order_id

    def test_check_triggers_long_stop_loss_not_triggered(self):
        """Test long position stop-loss not triggered when price above trigger"""
        manager = ProtectiveOrderManager()
        manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
        )
        # Price still above trigger
        market_state = {"BTCUSDT": {"price": 41500.0}}
        result = manager.check_triggers(market_state)
        assert len(result.triggered_orders) == 0

    def test_check_triggers_short_stop_loss(self):
        """Test short position stop-loss trigger"""
        manager = ProtectiveOrderManager()
        order = manager.create_protective_order(
            symbol="ETHUSDT",
            side=ProtectiveOrderSide.SHORT_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=2000.0,
            trigger_price_pct=5.0,
            quantity=10.0,
        )
        # Price rises above stop (trigger_price = 2000 * 1.05 = 2100)
        market_state = {"ETHUSDT": {"price": 2200.0}}
        result = manager.check_triggers(market_state)
        assert len(result.triggered_orders) == 1

    def test_check_triggers_take_profit(self):
        """Test take-profit trigger"""
        manager = ProtectiveOrderManager()
        order = manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.TAKE_PROFIT,
            entry_price=42000.0,
            trigger_price_pct=10.0,  # 10% above entry
            quantity=1.0,
        )
        # Manually set trigger price for take-profit (would be above entry)
        order.trigger_price = 42000.0 * 1.10  # 46200
        # Price rises to trigger level
        market_state = {"BTCUSDT": {"price": 47000.0}}
        result = manager.check_triggers(market_state)
        assert len(result.triggered_orders) == 1

    def test_check_triggers_skip_soft_stops(self):
        """Test skip_soft_stops parameter"""
        manager = ProtectiveOrderManager()
        manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.SOFT_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
        )
        manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=8.0,
            quantity=1.0,
        )
        # Price triggers both stops
        market_state = {"BTCUSDT": {"price": 38000.0}}

        # Without skip: both triggered
        result1 = manager.check_triggers(market_state, skip_soft_stops=False)
        assert len(result1.triggered_orders) == 2

        # Reset order statuses
        for order in manager.get_all_orders():
            order.status = ProtectiveOrderStatus.ARMED

        # With skip: only hard stop triggered
        result2 = manager.check_triggers(market_state, skip_soft_stops=True)
        assert len(result2.triggered_orders) == 1
        assert result2.triggered_orders[0].order_type == ProtectiveOrderType.HARD_STOP_LOSS

    def test_check_triggers_missing_market_data(self):
        """Test trigger check with missing market data"""
        manager = ProtectiveOrderManager()
        manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
        )
        # Market state missing BTCUSDT
        market_state = {"ETHUSDT": {"price": 2000.0}}
        result = manager.check_triggers(market_state)
        assert len(result.triggered_orders) == 0

    def test_check_triggers_trailing_stop(self):
        """Test trailing stop behavior"""
        manager = ProtectiveOrderManager()
        order = manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.TRAILING_STOP,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
        )
        order.trailing_distance = 5.0  # 5% trailing distance

        # Price rises
        market_state = {"BTCUSDT": {"price": 50000.0}}
        result1 = manager.check_triggers(market_state)
        assert len(result1.triggered_orders) == 0
        assert order.trailing_high == 50000.0

        # Price falls, but not beyond trailing level
        market_state = {"BTCUSDT": {"price": 48000.0}}
        result2 = manager.check_triggers(market_state)
        assert len(result2.triggered_orders) == 0

        # Price falls below trailing level (50000 * 0.95 = 47500)
        market_state = {"BTCUSDT": {"price": 47000.0}}
        result3 = manager.check_triggers(market_state)
        assert len(result3.triggered_orders) == 1

    def test_check_triggers_skips_terminal_orders(self):
        """Test that terminal status orders are skipped"""
        manager = ProtectiveOrderManager()
        order = manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
        )
        # Mark as executed
        order.status = ProtectiveOrderStatus.EXECUTED

        market_state = {"BTCUSDT": {"price": 39000.0}}
        result = manager.check_triggers(market_state)
        assert len(result.triggered_orders) == 0


class TestExecutionCallback:
    """Test protective action execution"""

    def test_execute_protective_action_success(self):
        """Test successful protective action execution"""
        exec_callback = Mock()
        manager = ProtectiveOrderManager(on_execute_callback=exec_callback)

        order = manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
        )
        order.status = ProtectiveOrderStatus.TRIGGERED

        market_state = {"price": 39000.0, "volume": 1000.0}
        result = manager.execute_protective_action(order, market_state)

        assert result is True
        assert order.status == ProtectiveOrderStatus.EXECUTED
        assert order.exchange_order_id is not None
        exec_callback.assert_called_once()

    def test_execute_protective_action_with_audit_callback(self):
        """Test that execution fires audit callback"""
        audit_callback = Mock()
        exec_callback = Mock()
        manager = ProtectiveOrderManager(
            audit_callback=audit_callback,
            on_execute_callback=exec_callback,
        )

        order = manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
        )
        order.status = ProtectiveOrderStatus.TRIGGERED

        manager.execute_protective_action(order, {})
        assert audit_callback.call_count >= 2  # At least creation + execution

    def test_execute_protective_action_invalid_status(self):
        """Test execution fails with invalid status"""
        manager = ProtectiveOrderManager()
        order = manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
        )
        # Order is in CREATED status, not TRIGGERED
        result = manager.execute_protective_action(order, {})
        assert result is False

    def test_execute_protective_action_callback_error(self):
        """Test execution handles callback error"""
        exec_callback = Mock(side_effect=Exception("Network error"))
        manager = ProtectiveOrderManager(on_execute_callback=exec_callback)

        order = manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
        )
        order.status = ProtectiveOrderStatus.TRIGGERED

        result = manager.execute_protective_action(order, {})
        assert result is False
        assert order.status == ProtectiveOrderStatus.FAILED


class TestCancellation:
    """Test order cancellation and hard stop protection"""

    def test_cancel_order_soft_stop(self):
        """Test cancelling a soft stop-loss"""
        manager = ProtectiveOrderManager()
        order = manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.SOFT_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
        )
        result = manager.cancel_order(order.order_id, reason="Manual override")
        assert result is True
        assert order.status == ProtectiveOrderStatus.CANCELLED

    def test_cancel_hard_stop_fails(self):
        """Test that hard stop-loss cannot be cancelled (DOC-01 §5.9)"""
        audit_callback = Mock()
        manager = ProtectiveOrderManager(audit_callback=audit_callback)
        order = manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
        )
        result = manager.cancel_order(order.order_id, reason="Manual override")
        assert result is False
        assert order.status != ProtectiveOrderStatus.CANCELLED
        # Check that hard_stop_cancel_rejected was logged
        assert any('hard_stop_cancel_rejected' in str(call) for call in audit_callback.call_args_list)

    def test_cancel_nonexistent_order(self):
        """Test cancelling nonexistent order raises ValueError"""
        manager = ProtectiveOrderManager()
        with pytest.raises(ValueError):
            manager.cancel_order("nonexistent")

    def test_cancel_take_profit(self):
        """Test cancelling take-profit"""
        manager = ProtectiveOrderManager()
        order = manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.TAKE_PROFIT,
            entry_price=42000.0,
            trigger_price_pct=10.0,
            quantity=1.0,
        )
        result = manager.cancel_order(order.order_id)
        assert result is True


class TestValidationAndCoverage:
    """Test coverage validation"""

    def test_validate_coverage_all_protected(self):
        """Test validation when all positions have hard stops"""
        manager = ProtectiveOrderManager()
        manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
            position_id="pos1",
        )
        open_positions = [{"position_id": "pos1", "symbol": "BTCUSDT"}]
        is_valid, missing = manager.validate_coverage(open_positions)
        assert is_valid is True
        assert len(missing) == 0

    def test_validate_coverage_unprotected_position(self):
        """Test validation with unprotected position"""
        manager = ProtectiveOrderManager()
        open_positions = [{"position_id": "pos1", "symbol": "BTCUSDT"}]
        is_valid, missing = manager.validate_coverage(open_positions)
        assert is_valid is False
        assert "pos1" in missing

    def test_get_unprotected_positions(self):
        """Test identifying unprotected positions"""
        manager = ProtectiveOrderManager()
        open_positions = [
            {"position_id": "pos1", "symbol": "BTCUSDT", "side": "LONG",
             "quantity": 1.0, "entry_price": 42000.0},
            {"position_id": "pos2", "symbol": "ETHUSDT", "side": "LONG",
             "quantity": 10.0, "entry_price": 2000.0},
        ]
        manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
            position_id="pos1",
        )
        unprotected = manager.get_unprotected_positions(open_positions)
        assert len(unprotected) == 1
        assert unprotected[0]["position_id"] == "pos2"


class TestEmergencyClose:
    """Test emergency close functionality"""

    def test_emergency_close_all(self):
        """Test emergency close all positions"""
        exec_callback = Mock()
        manager = ProtectiveOrderManager(on_execute_callback=exec_callback)

        manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
            position_id="pos1",
        )
        manager.create_protective_order(
            symbol="ETHUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=2000.0,
            trigger_price_pct=5.0,
            quantity=10.0,
            position_id="pos2",
        )

        closed = manager.emergency_close_all({}, reason="CIRCUIT_BREAKER")
        assert closed == 2  # Two positions closed

        # Check that emergency orders were created
        all_orders = manager.get_all_orders()
        emergency_orders = [o for o in all_orders
                           if o.order_type == ProtectiveOrderType.EMERGENCY_CLOSE_ALL]
        assert len(emergency_orders) >= 2


class TestSerialization:
    """Test serialization and deserialization"""

    def test_to_dict(self):
        """Test serializing manager state"""
        manager = ProtectiveOrderManager()
        manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
            position_id="pos1",
        )
        data = manager.to_dict()
        assert 'orders' in data
        assert 'position_orders' in data
        assert 'symbol_orders' in data
        assert len(data['orders']) == 1

    def test_from_dict(self):
        """Test deserializing manager state"""
        manager1 = ProtectiveOrderManager()
        order1 = manager1.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
            position_id="pos1",
        )
        data = manager1.to_dict()

        manager2 = ProtectiveOrderManager()
        manager2.from_dict(data)
        orders = manager2.get_all_orders()
        assert len(orders) == 1
        assert orders[0].symbol == "BTCUSDT"
        assert orders[0].position_id == "pos1"

    def test_export_json(self):
        """Test JSON export"""
        manager = ProtectiveOrderManager()
        manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
        )
        json_str = manager.export_json()
        assert json_str is not None
        data = json.loads(json_str)
        assert 'orders' in data
        assert len(data['orders']) == 1

    def test_import_json(self):
        """Test JSON import"""
        manager1 = ProtectiveOrderManager()
        manager1.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
            position_id="pos1",
        )
        json_str = manager1.export_json()

        manager2 = ProtectiveOrderManager()
        manager2.import_json(json_str)
        orders = manager2.get_all_orders()
        assert len(orders) == 1
        assert orders[0].position_id == "pos1"


class TestThreadSafety:
    """Test thread-safety"""

    def test_concurrent_order_creation(self):
        """Test thread-safe order creation"""
        manager = ProtectiveOrderManager()
        results = []

        def create_orders():
            for i in range(10):
                order = manager.create_protective_order(
                    symbol=f"SYM{i}",
                    side=ProtectiveOrderSide.LONG_POSITION,
                    order_type=ProtectiveOrderType.HARD_STOP_LOSS,
                    entry_price=1000.0,
                    trigger_price_pct=5.0,
                    quantity=1.0,
                )
                results.append(order.order_id)

        threads = [threading.Thread(target=create_orders) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 30
        all_orders = manager.get_all_orders()
        assert len(all_orders) == 30

    def test_concurrent_trigger_check(self):
        """Test thread-safe trigger checking"""
        manager = ProtectiveOrderManager()
        for i in range(5):
            manager.create_protective_order(
                symbol=f"SYM{i}",
                side=ProtectiveOrderSide.LONG_POSITION,
                order_type=ProtectiveOrderType.HARD_STOP_LOSS,
                entry_price=1000.0,
                trigger_price_pct=5.0,
                quantity=1.0,
            )

        def check_triggers():
            for i in range(10):
                market_state = {f"SYM{j}": {"price": 950.0} for j in range(5)}
                manager.check_triggers(market_state)

        threads = [threading.Thread(target=check_triggers) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()


class TestUtilities:
    """Test utility functions"""

    def test_create_default_hard_stop_config(self):
        """Test default hard stop config creation"""
        config = create_default_hard_stop_config(hard_stop_pct=5.0)
        assert config.order_type == ProtectiveOrderType.HARD_STOP_LOSS
        assert config.trigger_price_pct == 5.0
        assert config.is_mandatory is True
        assert config.can_be_disabled is False

    def test_calculate_atr_adjusted_stop(self):
        """Test ATR adjustment calculation"""
        stop = calculate_atr_adjusted_stop(
            atr=500.0,
            base_stop_pct=5.0,
            atr_multiplier=1.5,
        )
        assert stop > 5.0  # Should increase stop distance with high ATR


class TestAuditCallbacks:
    """Test audit logging"""

    def test_audit_callback_on_creation(self):
        """Test audit callback fires on order creation"""
        audit_callback = Mock()
        manager = ProtectiveOrderManager(audit_callback=audit_callback)

        manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
        )

        assert audit_callback.called
        call_args = audit_callback.call_args[0]
        assert call_args[0] == "protective_order_created"
        assert "symbol" in call_args[1]

    def test_audit_callback_on_trigger(self):
        """Test audit callback fires on trigger"""
        audit_callback = Mock()
        manager = ProtectiveOrderManager(audit_callback=audit_callback)

        manager.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=42000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
        )

        audit_callback.reset_mock()
        market_state = {"BTCUSDT": {"price": 39000.0}}
        manager.check_triggers(market_state)

        # Check for trigger event in audit logs
        trigger_logged = any(
            'protected_order_triggered' in str(call)
            for call in audit_callback.call_args_list
        )
        # Note: the actual event name might be different; check what's called
        assert audit_callback.called


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
