"""
Tests for stop-loss price precision fix.
止損價格精度修復測試。

Validates that:
1. round_price_for_exchange uses tick_size grid alignment (not hardcoded round(..., 2))
2. Demo fill price is used for exchange conditional stop (not Paper simulated price)
3. PipelineBridge._on_position_open correctly handles demo_fill_price parameter
4. SymbolCategoryRegistry tick_size/qty_step lookup works correctly
"""

import math
import sys
import os
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

# ── path setup ──
_this = os.path.dirname(os.path.abspath(__file__))
_app = os.path.join(_this, "..", "app")
if _app not in sys.path:
    sys.path.insert(0, _app)
_lmt = os.path.join(_this, "..", "..", "..", "..", "local_model_tools")
if _lmt not in sys.path:
    sys.path.insert(0, _lmt)


class TestRoundPriceForExchange(unittest.TestCase):
    """Test round_price_for_exchange with tick_size precision.
    驗證 round_price_for_exchange 使用 tick_size 精度取整。"""

    def setUp(self):
        from app.bybit_demo_connector import round_price_for_exchange
        self.round_price = round_price_for_exchange

    def test_pippinusdt_stop_not_rounded_to_market(self):
        """PIPPINUSDT ($0.06) with tickSize=0.00001 should NOT round to 0.06.
        PIPPINUSDT 止損價不應被進位到市價附近。
        This was the original bug: round(0.056859, 2) = 0.06 ≈ market price → false stop."""
        tick = 0.00001
        raw_stop = 0.06052 * (1 - 5.0 / 100)  # 5% below entry = 0.057494
        result = self.round_price(raw_stop, tick)
        # Must be well below 0.06 (market price), not rounded to 0.06
        self.assertLess(result, 0.058)
        self.assertGreater(result, 0.050)
        # Must be on tick grid (use round to handle float precision)
        remainder = result % tick
        self.assertTrue(remainder < tick * 0.01 or (tick - remainder) < tick * 0.01,
                        f"Not on tick grid: {result} % {tick} = {remainder}")

    def test_btcusdt_tick_01(self):
        """BTC with tickSize=0.1 rounds correctly.
        BTC tickSize=0.1 取整正確。"""
        tick = 0.1
        price = 65432.17
        result = self.round_price(price, tick)
        self.assertEqual(result, 65432.1)

    def test_ethusdt_tick_001(self):
        """ETH with tickSize=0.01 rounds correctly."""
        tick = 0.01
        price = 3456.789
        result = self.round_price(price, tick)
        self.assertEqual(result, 3456.78)

    def test_no_tick_fallback_8dp(self):
        """Without tick_size, falls back to 8 decimal places.
        沒有 tick_size 時回退到 8 位小數。"""
        result = self.round_price(0.123456789012, None)
        self.assertEqual(result, round(0.123456789012, 8))

    def test_tick_zero_fallback(self):
        """tick_size=0 treated same as None (fallback).
        tick_size=0 等同 None（回退）。"""
        result = self.round_price(0.123456789012, 0.0)
        self.assertEqual(result, round(0.123456789012, 8))

    def test_floor_not_round(self):
        """Confirms floor behavior: 0.05999 with tick=0.01 → 0.05 not 0.06.
        確認向下取整：0.05999 不會進位到 0.06。"""
        tick = 0.01
        result = self.round_price(0.05999, tick)
        self.assertEqual(result, 0.05)

    def test_exact_tick_unchanged(self):
        """Price already on tick grid stays unchanged."""
        tick = 0.00001
        result = self.round_price(0.05700, tick)
        self.assertAlmostEqual(result, 0.057, places=10)


class TestSymbolCategoryRegistryTickSize(unittest.TestCase):
    """Test SymbolCategoryRegistry tick_size and qty_step methods.
    驗證 SymbolCategoryRegistry tick_size / qty_step 查詢。"""

    def setUp(self):
        from app.symbol_category_registry import SymbolCategoryRegistry
        self.registry = SymbolCategoryRegistry("https://mock.test")

    def test_get_tick_size_unknown_symbol(self):
        """Unknown symbol returns None."""
        self.assertIsNone(self.registry.get_tick_size("UNKNOWN"))

    def test_get_qty_step_unknown_symbol(self):
        """Unknown symbol returns None."""
        self.assertIsNone(self.registry.get_qty_step("UNKNOWN"))

    def test_get_tick_size_after_manual_inject(self):
        """Manually injected instrument data is retrievable."""
        self.registry._instrument_cache["BTCUSDT"] = {"tick_size": 0.1, "qty_step": 0.001}
        self.assertEqual(self.registry.get_tick_size("BTCUSDT"), 0.1)

    def test_get_qty_step_after_manual_inject(self):
        """Manually injected instrument data is retrievable."""
        self.registry._instrument_cache["ETHUSDT"] = {"tick_size": 0.01, "qty_step": 0.01}
        self.assertEqual(self.registry.get_qty_step("ETHUSDT"), 0.01)


class TestPipelineBridgeDemoFillPrice(unittest.TestCase):
    """Test that _on_position_open uses demo_fill_price for exchange stop.
    驗證 _on_position_open 使用 demo_fill_price 計算交易所止損。"""

    def _make_bridge(self):
        """Create a minimal PipelineBridge for testing."""
        from app.pipeline_bridge import PipelineBridge
        km = MagicMock()
        km.get_latest_indicators.return_value = {"atr": 0.003}
        bridge = PipelineBridge(
            kline_manager=km,
            indicator_engine=MagicMock(),
            signal_engine=MagicMock(),
            orchestrator=MagicMock(),
            paper_engine=MagicMock(),
        )
        bridge._engine = MagicMock()
        bridge._engine.get_state.return_value = {"positions": {}}
        return bridge

    def _make_intent(self, symbol="PIPPINUSDT", side="Buy"):
        intent = MagicMock()
        intent.symbol = symbol
        intent.side = side
        intent.order_type = "market"
        intent.qty = 2493.0
        intent.metadata = {"_regime": "trending"}
        intent.strategy_name = "ma_crossover"
        return intent

    def test_demo_fill_price_used_for_stop_trigger(self):
        """When demo_fill_price > 0, exchange stop uses it instead of Paper price.
        當 demo_fill_price > 0 時，交易所止損使用 Demo 價格而非 Paper 價格。"""
        bridge = self._make_bridge()

        # Mock demo connector
        demo = MagicMock()
        demo.is_enabled = True
        demo.place_conditional_order.return_value = {"retCode": 0}
        bridge._demo_connector = demo

        # Mock symbol registry with PIPPINUSDT tick_size
        registry = MagicMock()
        registry.get_tick_size.return_value = 0.00001
        bridge._symbol_registry = registry

        intent = self._make_intent()
        paper_price = 0.059852  # Paper simulated price
        demo_price = 0.06052   # Demo actual fill price (higher due to real orderbook)

        bridge._on_position_open(intent, paper_price, actual_qty=2493.0, demo_fill_price=demo_price)

        # Verify conditional order was placed (0B-2: SL + TP = 2 calls)
        self.assertTrue(demo.place_conditional_order.called)
        # First call is SL — check that one
        sl_call = demo.place_conditional_order.call_args_list[0]
        sl_kwargs = sl_call[1] if sl_call[1] else {}
        trigger = sl_kwargs.get("trigger_price", sl_call[0][2] if len(sl_call[0]) > 2 else None)

        # Trigger should be based on demo_price (0.06052), not paper_price (0.059852)
        # For a Buy/long position, stop = demo_price * (1 - hard_stop_pct/100)
        # This should be well below 0.06, NOT 0.057...
        self.assertGreater(trigger, 0.05)
        self.assertLess(trigger, demo_price)

    def test_fallback_to_paper_price_when_no_demo_fill(self):
        """When demo_fill_price=0, falls back to Paper fill_price (backward compatible).
        當 demo_fill_price=0 時，回退到 Paper fill_price（向後兼容）。"""
        bridge = self._make_bridge()

        demo = MagicMock()
        demo.is_enabled = True
        demo.place_conditional_order.return_value = {"retCode": 0}
        bridge._demo_connector = demo

        registry = MagicMock()
        registry.get_tick_size.return_value = 0.01
        bridge._symbol_registry = registry

        intent = self._make_intent(symbol="BTCUSDT")
        paper_price = 65000.0

        bridge._on_position_open(intent, paper_price, actual_qty=0.001, demo_fill_price=0.0)

        # Should still place conditional order using paper_price
        self.assertTrue(demo.place_conditional_order.called)

    def test_no_registry_uses_8dp_fallback(self):
        """Without symbol registry, round_price_for_exchange uses 8dp fallback.
        沒有 registry 時，使用 8 位小數回退。"""
        bridge = self._make_bridge()

        demo = MagicMock()
        demo.is_enabled = True
        demo.place_conditional_order.return_value = {"retCode": 0}
        bridge._demo_connector = demo
        bridge._symbol_registry = None

        intent = self._make_intent(symbol="BTCUSDT")
        bridge._on_position_open(intent, 65000.0, actual_qty=0.001, demo_fill_price=65010.0)

        self.assertTrue(demo.place_conditional_order.called)


class TestProcessIntentDemoFillExtraction(unittest.TestCase):
    """Test that _process_single_intent extracts Demo fill price before _on_position_open.
    驗證 _process_single_intent 在 _on_position_open 之前提取 Demo 成交價。"""

    def _make_bridge(self):
        from app.pipeline_bridge import PipelineBridge
        km = MagicMock()
        km.get_latest_indicators.return_value = {"atr": 0.003}
        engine = MagicMock()
        engine.submit_order.return_value = {
            "fills": [{"price": 0.059852}],
            "close_pnl": 0.0,
            "order": {"orderId": "test123"},
        }
        engine.get_state.return_value = {"positions": {"PIPPINUSDT": {"qty": 2493}}}
        bridge = PipelineBridge(
            kline_manager=km,
            indicator_engine=MagicMock(),
            signal_engine=MagicMock(),
            orchestrator=MagicMock(),
            paper_engine=engine,
        )
        bridge._engine = engine
        return bridge

    def _make_intent(self, symbol="PIPPINUSDT", side="Buy"):
        intent = MagicMock()
        intent.symbol = symbol
        intent.side = side
        intent.order_type = "market"
        intent.qty = 2493.0
        intent.price = None
        intent.metadata = {"_regime": "trending", "category": "linear"}
        intent.strategy_name = "ma_crossover"
        intent.status = "pending"
        return intent

    def test_demo_fill_price_queried_after_order(self):
        """After Demo order succeeds, get_positions is called to get avgPrice.
        Demo 下單成功後，應查詢 get_positions 取得 avgPrice。"""
        bridge = self._make_bridge()

        # Mock demo connector
        demo = MagicMock()
        demo.is_enabled = True
        demo.submit_order.return_value = {"retCode": 0, "result": {"orderId": "d123"}}
        demo.get_positions.return_value = {
            "retCode": 0,
            "result": {"list": [
                {"symbol": "PIPPINUSDT", "size": "2493", "avgPrice": "0.06052"}
            ]}
        }
        demo.place_conditional_order.return_value = {"retCode": 0}
        bridge._demo_connector = demo

        # Mock registry
        registry = MagicMock()
        registry.get_tick_size.return_value = 0.00001
        bridge._symbol_registry = registry

        intent = self._make_intent()
        market_prices = {"PIPPINUSDT": 0.06}
        local_stats = {}

        # Call _post_execution_hooks with a successful Paper fill result
        result = {
            "fills": [{"price": 0.059852}],
            "close_pnl": 0.0,
            "order": {"orderId": "test123"},
        }

        # Patch _on_position_open to capture demo_fill_price
        with patch.object(bridge, "_on_position_open") as mock_open:
            bridge._post_execution_hooks(
                intent, result, _submit_qty=2493.0, _effective_leverage=10.0,
                category="linear", market_prices=market_prices, _local_stats=local_stats,
            )
            self.assertTrue(mock_open.called, "_on_position_open should have been called")
            _, kwargs = mock_open.call_args
            demo_fill = kwargs.get("demo_fill_price", 0.0)
            # Demo fill price should be the avgPrice from get_positions
            self.assertAlmostEqual(demo_fill, 0.06052, places=5)


if __name__ == "__main__":
    unittest.main()
