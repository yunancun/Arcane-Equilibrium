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


# TestPipelineBridgeDemoFillPrice deleted (DEAD-PY-2 — PipelineBridge removed)
# TestProcessIntentDemoFillExtraction deleted (DEAD-PY-2 — PipelineBridge removed)


if __name__ == "__main__":
    unittest.main()


