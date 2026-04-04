"""
E4 C9 -- MarketDataDispatcher Dedicated Tests
E4 C9 -- MarketDataDispatcher 专用测试

MODULE_NOTE (中文):
  对 market_data_dispatcher.py 的专项测试，覆盖：
  1. ticker 数据分发到注册的回调
  2. 价格缓存与检索
  3. feed 状态追踪（connected/disconnected/stale）
  4. urgency 等级计算
  5. 价格尖峰（spike）检测逻辑
  6. 节流行为

MODULE_NOTE (English):
  Dedicated tests for market_data_dispatcher.py covering:
  1. Ticker data dispatch to registered callbacks
  2. Price caching and retrieval
  3. Feed status tracking (connected/disconnected/stale)
  4. Urgency level calculation
  5. Spike detection logic
  6. Throttling behavior
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ── PATH SETUP ──
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.market_data_dispatcher import (
    MarketDataDispatcher,
    ATTENTION_DORMANT,
    ATTENTION_LOW,
    ATTENTION_MEDIUM,
    ATTENTION_HIGH,
    ATTENTION_CRITICAL,
    THROTTLE_INTERVALS,
    PROXIMITY_THRESHOLD_PCT,
    VOLATILITY_SPIKE_PCT,
)
from app.paper_trading_engine import SESSION_ACTIVE, SESSION_INACTIVE


# ── Helpers ──

class _FakePriceEvent:
    """Minimal PriceEvent stand-in."""
    def __init__(self, symbol="BTCUSDT", last_price=50000.0, ts_ms=None, volume_24h=1e9):
        self.symbol = symbol
        self.last_price = last_price
        self.timestamp_ms = ts_ms or int(time.time() * 1000)
        self.volume_24h = volume_24h


class _FakeEngine:
    """Minimal PaperTradingEngine stand-in."""
    def __init__(self, session_state="active", orders=None, positions=None):
        self._session_state = session_state
        self._orders = orders or []
        self._positions = positions or {}

    def get_state(self):
        return {
            "session": {"session_state": self._session_state},
            "orders": list(self._orders),
            "positions": dict(self._positions),
        }

    def tick(self, market_prices):
        return {"orders_filled": 0}


class _FakeWSListener:
    """Minimal BybitPublicWsListener stand-in."""
    def __init__(self):
        self._running = False
        self._latest_prices: dict[str, float] = {}

    def start(self):
        self._running = True

    def stop(self):
        self._running = False

    def is_running(self):
        return self._running

    def get_status(self):
        return {"connected": self._running}

    def get_all_latest_prices(self):
        return dict(self._latest_prices)

    def add_symbol(self, symbol):
        pass

    def remove_symbol(self, symbol):
        pass


def _make_dispatcher(engine=None, ws_listener=None):
    """Build a MarketDataDispatcher with mocked internals."""
    eng = engine or _FakeEngine()

    with patch("app.market_data_dispatcher.BybitPublicWsListener") as mock_ws_cls:
        listener = ws_listener or _FakeWSListener()
        mock_ws_cls.return_value = listener

        dispatcher = MarketDataDispatcher(engine=eng, symbols=["BTCUSDT", "ETHUSDT"])
        # Replace listener with our fake
        dispatcher._listener = listener
        return dispatcher, listener


# ═════════════════════════════════════════════════════════════════════════════
# Group 1: Ticker Data Dispatch & Callbacks
# ═════════════════════════════════════════════════════════════════════════════

class TestTickerDispatchCallbacks:
    def test_register_tick_consumer(self):
        """Registered consumer's on_tick is called on price event."""
        dispatcher, listener = _make_dispatcher()
        consumer = MagicMock()
        consumer.on_tick = MagicMock()
        dispatcher.register_tick_consumer(consumer)

        assert consumer in dispatcher._tick_consumers

    def test_consumer_called_on_trigger(self):
        """RC-11: trigger_tick no longer fans out to consumers (Rust handles ticks).
        RC-11：trigger_tick 不再分發給消費者（Rust 處理 tick）。"""
        dispatcher, listener = _make_dispatcher()
        listener._latest_prices = {"BTCUSDT": 50000.0}

        consumer = MagicMock()
        consumer.on_tick = MagicMock()
        dispatcher.register_tick_consumer(consumer)

        evt = _FakePriceEvent("BTCUSDT", 50000.0)
        dispatcher._trigger_tick(evt)

        # RC-11: consumers no longer called — Rust engine owns tick processing
        # RC-11：消費者不再被調用 — Rust 引擎負責 tick 處理
        consumer.on_tick.assert_not_called()

    def test_consumer_exception_does_not_crash(self):
        """RC-11: trigger_tick is a no-op for consumers, no crash possible.
        RC-11：trigger_tick 對消費者是空操作，不可能崩潰。"""
        dispatcher, listener = _make_dispatcher()
        listener._latest_prices = {"BTCUSDT": 50000.0}

        bad_consumer = MagicMock()
        bad_consumer.on_tick = MagicMock(side_effect=RuntimeError("boom"))
        dispatcher.register_tick_consumer(bad_consumer)

        evt = _FakePriceEvent("BTCUSDT", 50000.0)
        # Should not raise (and consumer is not called)
        dispatcher._trigger_tick(evt)
        bad_consumer.on_tick.assert_not_called()

    def test_multiple_consumers(self):
        """RC-11: Multiple consumers registered but not called (Rust handles ticks).
        RC-11：多個消費者已註冊但不被調用（Rust 處理 tick）。"""
        dispatcher, listener = _make_dispatcher()
        listener._latest_prices = {"BTCUSDT": 50000.0}

        consumers = [MagicMock() for _ in range(3)]
        for c in consumers:
            c.on_tick = MagicMock()
            dispatcher.register_tick_consumer(c)

        evt = _FakePriceEvent("BTCUSDT", 50000.0)
        dispatcher._trigger_tick(evt)

        # RC-11: consumers not called — tick fan-out disabled
        for c in consumers:
            c.on_tick.assert_not_called()


# ═════════════════════════════════════════════════════════════════════════════
# Group 2: Price Caching & History
# ═════════════════════════════════════════════════════════════════════════════

class TestPriceCaching:
    def test_price_history_updated(self):
        """_update_price_history adds entries."""
        dispatcher, _ = _make_dispatcher()
        dispatcher._update_price_history("BTCUSDT", 50000.0)
        assert len(dispatcher._price_history["BTCUSDT"]) == 1

    def test_price_history_trimmed(self):
        """Entries older than window are trimmed."""
        dispatcher, _ = _make_dispatcher()
        dispatcher._history_window_sec = 0.01  # very short

        dispatcher._update_price_history("BTCUSDT", 50000.0)
        time.sleep(0.02)
        dispatcher._update_price_history("BTCUSDT", 51000.0)

        # Old entry should be trimmed
        assert len(dispatcher._price_history["BTCUSDT"]) == 1

    def test_new_symbol_creates_history(self):
        """First price for a symbol creates new history list."""
        dispatcher, _ = _make_dispatcher()
        assert "SOLUSDT" not in dispatcher._price_history
        dispatcher._update_price_history("SOLUSDT", 100.0)
        assert "SOLUSDT" in dispatcher._price_history


# ═════════════════════════════════════════════════════════════════════════════
# Group 3: Feed Status / Attention Level
# ═════════════════════════════════════════════════════════════════════════════

class TestAttentionLevels:
    def test_dormant_when_no_session(self):
        """No active session → dormant."""
        engine = _FakeEngine(session_state="inactive")
        dispatcher, _ = _make_dispatcher(engine=engine)
        evt = _FakePriceEvent("BTCUSDT", 50000.0)
        assert dispatcher._assess_attention(evt) == ATTENTION_DORMANT

    def test_low_when_session_active_no_orders(self):
        """Active session, no orders, no positions → low."""
        engine = _FakeEngine(session_state="active")
        dispatcher, _ = _make_dispatcher(engine=engine)
        evt = _FakePriceEvent("BTCUSDT", 50000.0)
        assert dispatcher._assess_attention(evt) == ATTENTION_LOW

    def test_medium_when_has_positions(self):
        """Active session + positions → medium."""
        engine = _FakeEngine(
            session_state="active",
            positions={"BTCUSDT": {"qty": 0.01}},
        )
        dispatcher, _ = _make_dispatcher(engine=engine)
        evt = _FakePriceEvent("BTCUSDT", 50000.0)
        assert dispatcher._assess_attention(evt) == ATTENTION_MEDIUM

    def test_high_when_active_orders(self):
        """Active session + any active order → high."""
        engine = _FakeEngine(
            session_state="active",
            orders=[{"state": "paper_order_working", "order_type": "market", "symbol": "BTCUSDT"}],
        )
        dispatcher, _ = _make_dispatcher(engine=engine)
        evt = _FakePriceEvent("BTCUSDT", 50000.0)
        assert dispatcher._assess_attention(evt) == ATTENTION_HIGH

    def test_critical_when_limit_very_close(self):
        """Limit order within 0.15% of current price → critical."""
        engine = _FakeEngine(
            session_state="active",
            orders=[{
                "state": "paper_order_working",
                "order_type": "limit",
                "symbol": "BTCUSDT",
                "price": 50010.0,  # very close to 50000
            }],
        )
        dispatcher, _ = _make_dispatcher(engine=engine)
        evt = _FakePriceEvent("BTCUSDT", 50000.0)
        level = dispatcher._assess_attention(evt)
        assert level in (ATTENTION_HIGH, ATTENTION_CRITICAL)

    def test_engine_exception_returns_dormant(self):
        """If engine.get_state() throws, return dormant."""
        engine = MagicMock()
        engine.get_state.side_effect = RuntimeError("engine down")
        dispatcher, _ = _make_dispatcher(engine=engine)
        evt = _FakePriceEvent("BTCUSDT", 50000.0)
        assert dispatcher._assess_attention(evt) == ATTENTION_DORMANT


# ═════════════════════════════════════════════════════════════════════════════
# Group 4: Volatility Spike Detection
# ═════════════════════════════════════════════════════════════════════════════

class TestVolatilitySpikeDetection:
    def test_no_spike_with_few_data_points(self):
        """Less than 5 data points → no spike."""
        dispatcher, _ = _make_dispatcher()
        for i in range(3):
            dispatcher._update_price_history("BTCUSDT", 50000.0)
        assert dispatcher._detect_volatility_spike("BTCUSDT", 55000.0) is False

    def test_spike_detected_on_large_move(self):
        """Large price change from baseline → spike detected."""
        dispatcher, _ = _make_dispatcher()
        now = time.monotonic()

        # Build baseline history (all at 50000, older than 2s)
        dispatcher._price_history["BTCUSDT"] = [
            (now - 10, 50000.0),
            (now - 8, 50000.0),
            (now - 6, 50000.0),
            (now - 4, 50000.0),
            (now - 3, 50000.0),
        ]

        # Current price 2% above baseline → should trigger (threshold is 1%)
        assert dispatcher._detect_volatility_spike("BTCUSDT", 51500.0) is True

    def test_no_spike_on_small_move(self):
        """Small price change within threshold → no spike."""
        dispatcher, _ = _make_dispatcher()
        now = time.monotonic()

        dispatcher._price_history["BTCUSDT"] = [
            (now - 10, 50000.0),
            (now - 8, 50000.0),
            (now - 6, 50000.0),
            (now - 4, 50000.0),
            (now - 3, 50000.0),
        ]

        # 0.1% move → should NOT trigger
        assert dispatcher._detect_volatility_spike("BTCUSDT", 50050.0) is False

    def test_no_spike_unknown_symbol(self):
        """Unknown symbol (no history) → no spike."""
        dispatcher, _ = _make_dispatcher()
        assert dispatcher._detect_volatility_spike("UNKNOWN", 100.0) is False


# ═════════════════════════════════════════════════════════════════════════════
# Group 5: Throttling Behavior
# ═════════════════════════════════════════════════════════════════════════════

class TestThrottling:
    def test_dormant_throttle_interval(self):
        assert THROTTLE_INTERVALS[ATTENTION_DORMANT] == 60.0

    def test_critical_no_throttle(self):
        assert THROTTLE_INTERVALS[ATTENTION_CRITICAL] == 0.0

    def test_events_throttled_at_low_attention(self):
        """At low attention, events within 10s window are throttled."""
        engine = _FakeEngine(session_state="active")
        dispatcher, listener = _make_dispatcher(engine=engine)
        listener._latest_prices = {"BTCUSDT": 50000.0}

        # Force attention to LOW
        dispatcher._attention_level = ATTENTION_LOW

        # First event triggers
        evt1 = _FakePriceEvent("BTCUSDT", 50000.0)
        dispatcher._last_tick_all = time.monotonic()  # just ticked
        dispatcher._on_price_event(evt1)

        # Should be throttled
        assert dispatcher._stats["ticks_throttled"] >= 1

    def test_stats_count_events(self):
        """total_events_received increments on every price event."""
        engine = _FakeEngine(session_state="active")
        dispatcher, listener = _make_dispatcher(engine=engine)
        listener._latest_prices = {"BTCUSDT": 50000.0}

        assert dispatcher._stats["total_events_received"] == 0

        evt = _FakePriceEvent("BTCUSDT", 50000.0)
        dispatcher._on_price_event(evt)

        assert dispatcher._stats["total_events_received"] == 1


# ═════════════════════════════════════════════════════════════════════════════
# Group 6: Order Distance Calculation
# ═════════════════════════════════════════════════════════════════════════════

class TestOrderDistanceCalculation:
    def test_closest_order_distance(self):
        dispatcher, _ = _make_dispatcher()
        orders = [{"price": 49500.0}, {"price": 50500.0}]
        # Current price 50000: closest is 49500 → 1.0%
        dist = dispatcher._closest_order_distance_pct(orders, 50000.0)
        assert abs(dist - 1.0) < 0.01

    def test_empty_orders_infinite(self):
        dispatcher, _ = _make_dispatcher()
        assert dispatcher._closest_order_distance_pct([], 50000.0) == float("inf")

    def test_zero_price_infinite(self):
        dispatcher, _ = _make_dispatcher()
        orders = [{"price": 100.0}]
        assert dispatcher._closest_order_distance_pct(orders, 0.0) == float("inf")

    def test_order_with_no_price_skipped(self):
        dispatcher, _ = _make_dispatcher()
        orders = [{"price": None}, {"price": 50100.0}]
        dist = dispatcher._closest_order_distance_pct(orders, 50000.0)
        assert dist < float("inf")


# ═════════════════════════════════════════════════════════════════════════════
# Group 7: get_status / symbol management
# ═════════════════════════════════════════════════════════════════════════════

class TestDispatcherStatus:
    def test_get_status_fields(self):
        dispatcher, listener = _make_dispatcher()
        status = dispatcher.get_status()
        assert "dispatcher_running" in status
        assert "attention_level" in status
        assert "stats" in status
        assert status["is_simulated"] is True

    def test_add_symbol(self):
        dispatcher, _ = _make_dispatcher()
        dispatcher.add_symbol("SOLUSDT")
        assert "SOLUSDT" in dispatcher._symbols

    def test_add_symbol_idempotent(self):
        dispatcher, _ = _make_dispatcher()
        dispatcher.add_symbol("BTCUSDT")  # already present
        assert dispatcher._symbols.count("BTCUSDT") == 1

    def test_remove_symbol(self):
        dispatcher, _ = _make_dispatcher()
        dispatcher.remove_symbol("ETHUSDT")
        assert "ETHUSDT" not in dispatcher._symbols
