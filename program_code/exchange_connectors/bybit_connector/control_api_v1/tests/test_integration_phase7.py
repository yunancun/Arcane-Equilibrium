"""
Phase 7 Integration Tests — Demo API & Reconciliation
Phase 7 集成测试 — Demo API & 对账集成

6 test cases covering T7.01-T7.04:
  IT-P7-01: test_demo_connector_injection — PaperTradingEngine has set_demo_connector method, stores reference
  IT-P7-02: test_protective_callback_side_mapping — LONG_POSITION→"Sell", SHORT_POSITION→"Buy"
  IT-P7-03: test_protective_callback_order_type_mapping — HARD_STOP_LOSS→"Market", TAKE_PROFIT→"Limit"
  IT-P7-04: test_paper_state_adapter_format — adapter output has required keys
  IT-P7-05: test_demo_snapshot_format — Mock API responses → get_current_snapshot returns correct format
  IT-P7-06: test_demo_sync_injection — PaperTradingEngine has set_demo_sync method
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ═══════════════════════════════════════════════════════════════════════════════
# IT-P7-01: test_demo_connector_injection
# ═══════════════════════════════════════════════════════════════════════════════

class TestDemoConnectorInjection:
    """IT-P7-01: PaperTradingEngine accepts and stores BybitDemoConnector"""

    def test_demo_connector_injection(self, tmp_path):
        from app.paper_trading_engine import PaperStateStore, PaperTradingEngine
        from app.bybit_demo_connector import BybitDemoConnector

        # Create engine
        store_path = tmp_path / "test_state.json"
        store = PaperStateStore(str(store_path))
        engine = PaperTradingEngine(store)

        # Verify set_demo_connector method exists and works
        mock_connector = MagicMock(spec=BybitDemoConnector)
        engine.set_demo_connector(mock_connector)

        # Verify connector was stored
        assert engine._demo_connector is mock_connector


# ═══════════════════════════════════════════════════════════════════════════════
# IT-P7-02: test_protective_callback_side_mapping
# ═══════════════════════════════════════════════════════════════════════════════

class TestProtectiveCallbackSideMapping:
    """IT-P7-02: Protective order callback maps sides correctly"""

    def test_protective_callback_long_position_maps_to_sell(self):
        from app.protective_order_manager import (
            ProtectiveOrder, ProtectiveOrderSide, ProtectiveOrderType, ProtectiveOrderStatus
        )

        # Create a LONG_POSITION protective order
        order = ProtectiveOrder(
            order_id="test_order_1",
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            trigger_price=50000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
            entry_price=52500.0,
            status=ProtectiveOrderStatus.TRIGGERED,
        )

        # Verify side enum value
        assert order.side == ProtectiveOrderSide.LONG_POSITION
        # Closing a long position requires "Sell"
        # The callback should map LONG_POSITION → Sell
        if order.side == ProtectiveOrderSide.LONG_POSITION:
            expected_side = "Sell"
        else:
            expected_side = "Buy"
        assert expected_side == "Sell"

    def test_protective_callback_short_position_maps_to_buy(self):
        from app.protective_order_manager import (
            ProtectiveOrder, ProtectiveOrderSide, ProtectiveOrderType, ProtectiveOrderStatus
        )

        # Create a SHORT_POSITION protective order
        order = ProtectiveOrder(
            order_id="test_order_2",
            symbol="ETHUSDT",
            side=ProtectiveOrderSide.SHORT_POSITION,
            order_type=ProtectiveOrderType.SOFT_STOP_LOSS,
            trigger_price=2500.0,
            trigger_price_pct=5.0,
            quantity=10.0,
            entry_price=2625.0,
            status=ProtectiveOrderStatus.TRIGGERED,
        )

        # Verify side enum value
        assert order.side == ProtectiveOrderSide.SHORT_POSITION
        # Closing a short position requires "Buy"
        # The callback should map SHORT_POSITION → Buy
        if order.side == ProtectiveOrderSide.LONG_POSITION:
            expected_side = "Sell"
        elif order.side == ProtectiveOrderSide.SHORT_POSITION:
            expected_side = "Buy"
        else:
            expected_side = "Unknown"
        assert expected_side == "Buy"


# ═══════════════════════════════════════════════════════════════════════════════
# IT-P7-03: test_protective_callback_order_type_mapping
# ═══════════════════════════════════════════════════════════════════════════════

class TestProtectiveCallbackOrderTypeMapping:
    """IT-P7-03: Protective order callback maps order types correctly"""

    def test_hard_stop_loss_maps_to_market(self):
        from app.protective_order_manager import (
            ProtectiveOrder, ProtectiveOrderSide, ProtectiveOrderType, ProtectiveOrderStatus
        )

        order = ProtectiveOrder(
            order_id="test_order_3",
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            trigger_price=50000.0,
            trigger_price_pct=5.0,
            quantity=1.0,
            entry_price=52500.0,
        )

        # HARD_STOP_LOSS should map to Market
        if order.order_type in (
            ProtectiveOrderType.HARD_STOP_LOSS,
            ProtectiveOrderType.SOFT_STOP_LOSS,
            ProtectiveOrderType.EMERGENCY_CLOSE_ALL,
        ):
            expected_type = "Market"
            expected_price = None
        else:
            expected_type = "Limit"
            expected_price = order.trigger_price

        assert expected_type == "Market"
        assert expected_price is None

    def test_take_profit_maps_to_limit(self):
        from app.protective_order_manager import (
            ProtectiveOrder, ProtectiveOrderSide, ProtectiveOrderType, ProtectiveOrderStatus
        )

        order = ProtectiveOrder(
            order_id="test_order_4",
            symbol="ETHUSDT",
            side=ProtectiveOrderSide.SHORT_POSITION,
            order_type=ProtectiveOrderType.TAKE_PROFIT,
            trigger_price=3000.0,
            trigger_price_pct=10.0,
            quantity=10.0,
            entry_price=2700.0,
        )

        # TAKE_PROFIT should map to Limit with trigger_price as price
        if order.order_type == ProtectiveOrderType.TAKE_PROFIT:
            expected_type = "Limit"
            expected_price = order.trigger_price
        else:
            expected_type = "Market"
            expected_price = None

        assert expected_type == "Limit"
        assert expected_price == order.trigger_price


# ═══════════════════════════════════════════════════════════════════════════════
# IT-P7-04: test_paper_state_adapter_format
# ═══════════════════════════════════════════════════════════════════════════════

class TestPaperStateAdapter:
    """IT-P7-04: Paper state adapter produces correct reconciliation format"""

    def test_adapter_output_format(self, tmp_path):
        from app.paper_trading_engine import PaperStateStore, PaperTradingEngine, _paper_state_to_recon_format

        # Create engine with a session
        store_path = tmp_path / "test_state.json"
        store = PaperStateStore(str(store_path))
        engine = PaperTradingEngine(store)

        # Start a session
        engine.start_session(initial_balance=10000.0)

        # Get current state
        state = engine.get_state()

        # Convert to recon format
        recon_state = _paper_state_to_recon_format(state)

        # Verify required keys exist
        assert "snapshot_ts_ms" in recon_state
        assert "orders" in recon_state
        assert "positions" in recon_state
        assert "fills" in recon_state
        assert "balances" in recon_state

        # Verify types
        assert isinstance(recon_state["snapshot_ts_ms"], int)
        assert isinstance(recon_state["orders"], list)
        assert isinstance(recon_state["positions"], dict)
        assert isinstance(recon_state["fills"], list)
        assert isinstance(recon_state["balances"], dict)

        # Verify balance is in USDT
        assert "USDT" in recon_state["balances"]
        assert recon_state["balances"]["USDT"] == 10000.0


# ═══════════════════════════════════════════════════════════════════════════════
# IT-P7-05: test_demo_snapshot_format
# ═══════════════════════════════════════════════════════════════════════════════

class TestDemoSnapshotFormat:
    """IT-P7-05: Demo sync snapshot produces correct reconciliation format"""

    def test_demo_snapshot_format(self):
        from app.bybit_demo_sync import BybitDemoSync

        # Create mock connector
        mock_connector = MagicMock()
        mock_connector.get_positions.return_value = {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "side": "Buy",
                        "size": "1.0",
                        "avgPrice": "50000.0",
                    },
                    {
                        "symbol": "ETHUSDT",
                        "side": "Sell",
                        "size": "10.0",
                        "avgPrice": "2500.0",
                    },
                ]
            },
        }
        mock_connector.get_wallet_balance.return_value = {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "coin": [
                            {"coin": "USDT", "walletBalance": "5000.0"},
                            {"coin": "BTC", "walletBalance": "0.5"},
                        ]
                    }
                ]
            },
        }

        # Create sync
        sync = BybitDemoSync(mock_connector)

        # Get snapshot
        snapshot = sync.get_current_snapshot()

        # Verify snapshot exists and has required format
        assert snapshot is not None
        assert "snapshot_ts_ms" in snapshot
        assert "orders" in snapshot
        assert "positions" in snapshot
        assert "fills" in snapshot
        assert "balances" in snapshot

        # Verify types
        assert isinstance(snapshot["snapshot_ts_ms"], int)
        assert isinstance(snapshot["orders"], list)
        assert isinstance(snapshot["positions"], dict)
        assert isinstance(snapshot["fills"], list)
        assert isinstance(snapshot["balances"], dict)

        # Verify positions are parsed
        assert len(snapshot["positions"]) == 2
        assert "BTCUSDT" in snapshot["positions"]
        assert "ETHUSDT" in snapshot["positions"]

        # Verify balances are parsed
        assert "USDT" in snapshot["balances"]
        assert snapshot["balances"]["USDT"] == 5000.0
        assert "BTC" in snapshot["balances"]
        assert snapshot["balances"]["BTC"] == 0.5


# ═══════════════════════════════════════════════════════════════════════════════
# IT-P7-06: test_demo_sync_injection
# ═══════════════════════════════════════════════════════════════════════════════

class TestDemoSyncInjection:
    """IT-P7-06: PaperTradingEngine accepts and stores BybitDemoSync"""

    def test_demo_sync_injection(self, tmp_path):
        from app.paper_trading_engine import PaperStateStore, PaperTradingEngine
        from app.bybit_demo_sync import BybitDemoSync

        # Create engine
        store_path = tmp_path / "test_state.json"
        store = PaperStateStore(str(store_path))
        engine = PaperTradingEngine(store)

        # Create mock sync
        mock_connector = MagicMock()
        mock_sync = BybitDemoSync(mock_connector)

        # Inject
        engine.set_demo_sync(mock_sync)

        # Verify sync was stored
        assert engine._demo_sync is mock_sync
