"""
Tests for Bybit Public WS Listener + Market Data Dispatcher + Attention Filter
测试：Bybit 公共 WS 监听器 + 行情分发器 + 注意力过滤器

覆盖范围 / Coverage:
  - PriceEvent construction and serialization / 价格事件构造与序列化
  - BybitPublicWsListener message parsing / 公共 WS 消息解析
  - Attention level assessment (dormant/low/medium/high/critical) / 注意力等级评估
  - Throttle behavior per attention level / 各注意力等级的节流行为
  - Volatility spike detection / 波动率飙升检测
  - Order proximity calculation / 订单距离计算
  - Market feed API routes / 行情流 API 路由
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.bybit_public_ws_listener import (
    BybitPublicWsListener,
    PriceEvent,
    _safe_float,
)
from app.market_data_dispatcher import (
    ATTENTION_CRITICAL,
    ATTENTION_DORMANT,
    ATTENTION_HIGH,
    ATTENTION_LOW,
    ATTENTION_MEDIUM,
    PROXIMITY_THRESHOLD_PCT,
    THROTTLE_INTERVALS,
    MarketDataDispatcher,
)
from app.paper_trading_engine import (
    PaperStateStore,
    PaperTradingEngine,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures / 测试夹具
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def tmp_state_path():
    """Create a temp file path for paper state / 创建临时状态文件路径"""
    fd, path = tempfile.mkstemp(suffix=".json", prefix="test_paper_state_")
    os.close(fd)
    os.unlink(path)  # Let PaperStateStore create it
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def engine(tmp_state_path):
    """Create a paper trading engine for testing / 创建测试用纸上交易引擎"""
    store = PaperStateStore(tmp_state_path)
    return PaperTradingEngine(store)


@pytest.fixture
def active_engine(engine):
    """Engine with an active session / 已启动 session 的引擎"""
    engine.start_session(initial_balance=10000.0)
    return engine


# ═══════════════════════════════════════════════════════════════════════════════
# Test: PriceEvent / 测试：价格事件
# ═══════════════════════════════════════════════════════════════════════════════

class TestPriceEvent:
    def test_create_basic(self):
        """PriceEvent can be created with basic fields / 基本字段创建"""
        evt = PriceEvent(symbol="BTCUSDT", last_price=87000.0)
        assert evt.symbol == "BTCUSDT"
        assert evt.last_price == 87000.0
        assert evt.mark_price is None
        assert evt.best_bid is None

    def test_create_full(self):
        """PriceEvent with all fields / 全部字段创建"""
        evt = PriceEvent(
            symbol="ETHUSDT",
            last_price=3200.50,
            mark_price=3200.40,
            index_price=3200.45,
            best_bid=3200.30,
            best_ask=3200.70,
            volume_24h=150000.0,
            turnover_24h=480000000.0,
            price_change_pct_24h=0.025,
            high_24h=3300.0,
            low_24h=3100.0,
            ts_ms=1711500000000,
            receive_ts_ms=1711500000050,
        )
        d = evt.to_dict()
        assert d["symbol"] == "ETHUSDT"
        assert d["last_price"] == 3200.50
        assert d["mark_price"] == 3200.40
        assert d["best_bid"] == 3200.30
        assert d["volume_24h"] == 150000.0

    def test_to_dict_complete(self):
        """to_dict includes all fields / 序列化包含所有字段"""
        evt = PriceEvent(symbol="BTCUSDT", last_price=87000.0, ts_ms=123)
        d = evt.to_dict()
        assert "symbol" in d
        assert "last_price" in d
        assert "mark_price" in d
        assert "ts_ms" in d
        assert d["ts_ms"] == 123


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Safe Float / 测试：安全浮点转换
# ═══════════════════════════════════════════════════════════════════════════════

class TestSafeFloat:
    def test_valid_string(self):
        assert _safe_float("87654.30") == 87654.30

    def test_valid_int(self):
        assert _safe_float(100) == 100.0

    def test_none(self):
        assert _safe_float(None) is None

    def test_invalid_string(self):
        assert _safe_float("not_a_number") is None

    def test_zero(self):
        assert _safe_float("0") is None  # Zero returns None (invalid price)

    def test_negative(self):
        assert _safe_float("-1.5") is None


# ═══════════════════════════════════════════════════════════════════════════════
# Test: WS Listener Message Parsing / 测试：WS 消息解析
# ═══════════════════════════════════════════════════════════════════════════════

class TestWsListenerMessageParsing:
    def test_parse_ticker_snapshot(self):
        """Parse a Bybit ticker snapshot message / 解析 Bybit ticker 快照消息"""
        received_events: list[PriceEvent] = []

        listener = BybitPublicWsListener(
            symbols=["BTCUSDT"],
            on_price=lambda evt: received_events.append(evt),
        )

        msg = json.dumps({
            "topic": "tickers.BTCUSDT",
            "type": "snapshot",
            "ts": 1711500000000,
            "data": {
                "symbol": "BTCUSDT",
                "lastPrice": "87654.30",
                "markPrice": "87650.12",
                "indexPrice": "87652.00",
                "bid1Price": "87654.00",
                "ask1Price": "87654.50",
                "volume24h": "12345.678",
                "turnover24h": "1082345678.90",
                "price24hPcnt": "0.0123",
                "highPrice24h": "88000.00",
                "lowPrice24h": "86000.00",
            }
        })

        listener._handle_message(msg)

        assert len(received_events) == 1
        evt = received_events[0]
        assert evt.symbol == "BTCUSDT"
        assert evt.last_price == 87654.30
        assert evt.mark_price == 87650.12
        assert evt.best_bid == 87654.00
        assert evt.best_ask == 87654.50
        assert evt.volume_24h == 12345.678

    def test_parse_ticker_delta(self):
        """Parse a delta update (partial fields) / 解析增量更新"""
        received: list[PriceEvent] = []
        listener = BybitPublicWsListener(
            symbols=["ETHUSDT"],
            on_price=lambda evt: received.append(evt),
        )

        msg = json.dumps({
            "topic": "tickers.ETHUSDT",
            "type": "delta",
            "ts": 1711500000100,
            "data": {
                "symbol": "ETHUSDT",
                "lastPrice": "3200.50",
            }
        })

        listener._handle_message(msg)
        assert len(received) == 1
        assert received[0].last_price == 3200.50
        assert received[0].mark_price is None  # Not in delta

    def test_ignore_non_ticker_message(self):
        """Non-ticker messages are ignored / 非 ticker 消息被忽略"""
        received: list[PriceEvent] = []
        listener = BybitPublicWsListener(
            symbols=["BTCUSDT"],
            on_price=lambda evt: received.append(evt),
        )

        # Subscribe confirmation
        listener._handle_message(json.dumps({"op": "subscribe", "success": True}))
        # Pong
        listener._handle_message(json.dumps({"op": "pong"}))

        assert len(received) == 0

    def test_ignore_invalid_price(self):
        """Messages with invalid price are skipped / 无效价格消息被跳过"""
        received: list[PriceEvent] = []
        listener = BybitPublicWsListener(
            symbols=["BTCUSDT"],
            on_price=lambda evt: received.append(evt),
        )

        listener._handle_message(json.dumps({
            "topic": "tickers.BTCUSDT",
            "data": {"symbol": "BTCUSDT", "lastPrice": "0"},
        }))
        listener._handle_message(json.dumps({
            "topic": "tickers.BTCUSDT",
            "data": {"symbol": "BTCUSDT", "lastPrice": "invalid"},
        }))

        assert len(received) == 0

    def test_latest_price_cache(self):
        """Listener caches latest price per symbol / 监听器缓存每个交易对的最新价格"""
        listener = BybitPublicWsListener(symbols=["BTCUSDT", "ETHUSDT"])

        listener._handle_message(json.dumps({
            "topic": "tickers.BTCUSDT",
            "data": {"symbol": "BTCUSDT", "lastPrice": "87000.00"},
        }))
        listener._handle_message(json.dumps({
            "topic": "tickers.ETHUSDT",
            "data": {"symbol": "ETHUSDT", "lastPrice": "3200.00"},
        }))

        prices = listener.get_all_latest_prices()
        assert prices["BTCUSDT"] == 87000.00
        assert prices["ETHUSDT"] == 3200.00

        btc_evt = listener.get_latest_price("BTCUSDT")
        assert btc_evt is not None
        assert btc_evt.last_price == 87000.00

    def test_status_tracking(self):
        """Status tracks message counts / 状态追踪消息计数"""
        listener = BybitPublicWsListener(symbols=["BTCUSDT"])

        listener._handle_message(json.dumps({
            "topic": "tickers.BTCUSDT",
            "data": {"symbol": "BTCUSDT", "lastPrice": "87000.00"},
        }))
        listener._handle_message(json.dumps({
            "topic": "tickers.BTCUSDT",
            "data": {"symbol": "BTCUSDT", "lastPrice": "87001.00"},
        }))

        status = listener.get_status()
        assert status["message_count"] == 2
        assert status["ticker_update_count"] == 2
        assert status["last_ticker_ts_ms"] is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Attention Level Assessment / 测试：注意力等级评估
# ═══════════════════════════════════════════════════════════════════════════════

class TestAttentionLevel:
    def test_dormant_when_no_session(self, engine):
        """No active session → dormant / 无活跃 session → dormant"""
        dispatcher = MarketDataDispatcher(engine=engine, symbols=["BTCUSDT"])
        event = PriceEvent(symbol="BTCUSDT", last_price=87000.0)
        level = dispatcher._assess_attention(event)
        assert level == ATTENTION_DORMANT

    def test_low_when_session_no_orders(self, active_engine):
        """Active session, no orders → low / 活跃 session，无订单 → low"""
        dispatcher = MarketDataDispatcher(engine=active_engine, symbols=["BTCUSDT"])
        event = PriceEvent(symbol="BTCUSDT", last_price=87000.0)
        level = dispatcher._assess_attention(event)
        assert level == ATTENTION_LOW

    def test_medium_when_has_position(self, active_engine):
        """Has position but no pending orders → medium / 有持仓无挂单 → medium"""
        # Create a filled market order to establish a position
        active_engine.submit_order(
            symbol="BTCUSDT", side="Buy", order_type="market",
            qty=0.01, market_prices={"BTCUSDT": 87000.0},
        )

        dispatcher = MarketDataDispatcher(engine=active_engine, symbols=["BTCUSDT"])
        event = PriceEvent(symbol="BTCUSDT", last_price=87100.0)
        level = dispatcher._assess_attention(event)
        assert level == ATTENTION_MEDIUM

    def test_high_when_has_limit_order(self, active_engine):
        """Has limit order (any distance) → at least high / 有限价单 → 至少 high"""
        active_engine.submit_order(
            symbol="BTCUSDT", side="Buy", order_type="limit",
            qty=0.01, price=85000.0,  # Far from current
        )

        dispatcher = MarketDataDispatcher(engine=active_engine, symbols=["BTCUSDT"])
        event = PriceEvent(symbol="BTCUSDT", last_price=87000.0)
        level = dispatcher._assess_attention(event)
        assert level == ATTENTION_HIGH

    def test_critical_when_order_very_close(self, active_engine):
        """Limit order within 0.15% of current price → critical / 限价单在 0.15% 以内 → critical"""
        # Place a buy limit at 86950 — within 0.057% of 87000
        active_engine.submit_order(
            symbol="BTCUSDT", side="Buy", order_type="limit",
            qty=0.01, price=86950.0,
        )

        dispatcher = MarketDataDispatcher(engine=active_engine, symbols=["BTCUSDT"])
        event = PriceEvent(symbol="BTCUSDT", last_price=87000.0)
        level = dispatcher._assess_attention(event)
        assert level == ATTENTION_CRITICAL


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Volatility Detection / 测试：波动率检测
# ═══════════════════════════════════════════════════════════════════════════════

class TestVolatilityDetection:
    def test_no_spike_with_few_samples(self, active_engine):
        """Not enough data → no spike detected / 数据不足 → 未检测到飙升"""
        dispatcher = MarketDataDispatcher(engine=active_engine, symbols=["BTCUSDT"])
        assert dispatcher._detect_volatility_spike("BTCUSDT", 87000.0) is False

    def test_no_spike_with_stable_prices(self, active_engine):
        """Stable prices → no spike / 价格稳定 → 无飙升"""
        dispatcher = MarketDataDispatcher(engine=active_engine, symbols=["BTCUSDT"])

        # Simulate stable price history
        base_time = time.monotonic() - 30  # 30 seconds ago
        dispatcher._price_history["BTCUSDT"] = [
            (base_time + i, 87000.0 + i * 0.1)  # Tiny changes
            for i in range(20)
        ]

        assert dispatcher._detect_volatility_spike("BTCUSDT", 87005.0) is False

    def test_spike_detected_on_large_move(self, active_engine):
        """Large price move triggers spike detection / 大幅价格变动触发飙升检测"""
        dispatcher = MarketDataDispatcher(engine=active_engine, symbols=["BTCUSDT"])

        # Simulate price history at 87000
        base_time = time.monotonic() - 30
        dispatcher._price_history["BTCUSDT"] = [
            (base_time + i, 87000.0)
            for i in range(20)
        ]

        # Sudden jump to 88000 (1.15% move) → should trigger spike
        assert dispatcher._detect_volatility_spike("BTCUSDT", 88000.0) is True


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Order Proximity / 测试：订单距离
# ═══════════════════════════════════════════════════════════════════════════════

class TestOrderProximity:
    def test_closest_distance(self):
        """Calculate closest order distance correctly / 正确计算最近订单距离"""
        dispatcher = MarketDataDispatcher.__new__(MarketDataDispatcher)

        orders = [
            {"price": 86000.0},  # ~1.15% away from 87000
            {"price": 86800.0},  # ~0.23% away from 87000
            {"price": 85000.0},  # ~2.30% away
        ]

        dist = dispatcher._closest_order_distance_pct(orders, 87000.0)
        assert dist == pytest.approx(0.2299, abs=0.01)  # 86800 is closest

    def test_empty_orders(self):
        """No orders → infinite distance / 无订单 → 无穷距离"""
        dispatcher = MarketDataDispatcher.__new__(MarketDataDispatcher)
        dist = dispatcher._closest_order_distance_pct([], 87000.0)
        assert dist == float("inf")


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Throttle Behavior / 测试：节流行为
# ═══════════════════════════════════════════════════════════════════════════════

class TestThrottleBehavior:
    def test_throttle_intervals_defined(self):
        """All attention levels have throttle intervals / 所有注意力等级都有节流间隔"""
        assert ATTENTION_DORMANT in THROTTLE_INTERVALS
        assert ATTENTION_LOW in THROTTLE_INTERVALS
        assert ATTENTION_MEDIUM in THROTTLE_INTERVALS
        assert ATTENTION_HIGH in THROTTLE_INTERVALS
        assert ATTENTION_CRITICAL in THROTTLE_INTERVALS

    def test_throttle_order(self):
        """Higher attention → shorter throttle interval / 更高注意力 → 更短节流间隔"""
        assert THROTTLE_INTERVALS[ATTENTION_DORMANT] > THROTTLE_INTERVALS[ATTENTION_LOW]
        assert THROTTLE_INTERVALS[ATTENTION_LOW] > THROTTLE_INTERVALS[ATTENTION_MEDIUM]
        assert THROTTLE_INTERVALS[ATTENTION_MEDIUM] > THROTTLE_INTERVALS[ATTENTION_HIGH]
        assert THROTTLE_INTERVALS[ATTENTION_HIGH] > THROTTLE_INTERVALS[ATTENTION_CRITICAL]

    def test_critical_is_zero(self):
        """Critical attention has zero throttle / Critical 注意力零节流"""
        assert THROTTLE_INTERVALS[ATTENTION_CRITICAL] == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Dispatcher Integration / 测试：分发器集成
# ═══════════════════════════════════════════════════════════════════════════════

class TestDispatcherIntegration:
    def test_tick_triggered_on_price_event(self, active_engine):
        """Price event triggers engine tick / 价格事件触发引擎 tick"""
        dispatcher = MarketDataDispatcher(engine=active_engine, symbols=["BTCUSDT"])

        # Submit a limit order near price
        active_engine.submit_order(
            symbol="BTCUSDT", side="Buy", order_type="limit",
            qty=0.01, price=87000.0,
        )

        # Simulate price event at limit price
        event = PriceEvent(symbol="BTCUSDT", last_price=87000.0)
        dispatcher._on_price_event(event)

        assert dispatcher._stats["ticks_triggered"] >= 1

    def test_limit_order_filled_via_dispatch(self, active_engine):
        """Limit order filled when price reaches limit via dispatcher / 分发器触发限价单成交"""
        dispatcher = MarketDataDispatcher(engine=active_engine, symbols=["BTCUSDT"])

        # Submit buy limit at 86500
        result = active_engine.submit_order(
            symbol="BTCUSDT", side="Buy", order_type="limit",
            qty=0.01, price=86500.0,
        )
        order_id = result["order"]["order_id"]

        # Price drops well below limit (deep cross >0.5%) → guarantees full fill
        # 价格深穿限价（>0.5%）→ 保证全部成交
        deep_cross_price = 86500.0 * 0.994  # ~86000, >0.5% below limit
        event = PriceEvent(symbol="BTCUSDT", last_price=deep_cross_price)
        dispatcher._on_price_event(event)

        # Verify filled (deep cross ensures 100% fill)
        orders = active_engine.get_orders()
        filled = [o for o in orders if o["order_id"] == order_id]
        assert len(filled) == 1
        assert filled[0]["state"] == "paper_order_filled"

    def test_status_report(self, engine):
        """Dispatcher status includes all key fields / 状态报告包含所有关键字段"""
        dispatcher = MarketDataDispatcher(engine=engine, symbols=["BTCUSDT"])
        status = dispatcher.get_status()

        assert "dispatcher_running" in status
        assert "attention_level" in status
        assert "throttle_interval_sec" in status
        assert "ws_listener" in status
        assert "latest_prices" in status
        assert "stats" in status
        assert status["is_simulated"] is True

    def test_not_running_initially(self, engine):
        """Dispatcher not running before start() / 启动前分发器未运行"""
        dispatcher = MarketDataDispatcher(engine=engine, symbols=["BTCUSDT"])
        assert dispatcher.is_running() is False


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Market Feed API Routes / 测试：行情流 API 路由
# ═══════════════════════════════════════════════════════════════════════════════

class TestMarketFeedAPIRoutes:
    """Test the market feed control routes via FastAPI TestClient."""

    @pytest.fixture
    def api_client(self):
        """Build test client with isolated state / 构建隔离状态的测试客户端"""
        import app.paper_trading_routes as routes

        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.unlink(path)

        original_store = routes.PAPER_STORE
        original_engine = routes.ENGINE
        original_dispatcher = routes.DISPATCHER

        try:
            routes.PAPER_STORE = PaperStateStore(path)
            routes.ENGINE = PaperTradingEngine(routes.PAPER_STORE)
            routes.DISPATCHER = None

            from fastapi.testclient import TestClient
            # Import from app.main which registers paper_router
            from app.main import app
            client = TestClient(app)

            # Set auth token
            token = os.getenv("OPENCLAW_API_TOKEN", "")
            if not token:
                from app.main_legacy import settings
                token = settings.api_token

            yield client, token
        finally:
            routes.PAPER_STORE = original_store
            routes.ENGINE = original_engine
            routes.DISPATCHER = original_dispatcher
            if os.path.exists(path):
                os.unlink(path)

    def test_market_feed_status_not_initialized(self, api_client):
        """Status returns not-initialized when dispatcher is None / 未初始化时状态返回未初始化"""
        client, token = api_client
        resp = client.get(
            "/api/v1/paper/market-feed/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["running"] is False

    def test_market_feed_stop_when_not_running(self, api_client):
        """Stop returns no_change when not running / 未运行时停止返回 no_change"""
        client, token = api_client
        resp = client.post(
            "/api/v1/paper/market-feed/stop",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["action_result"] == "no_change"

    def test_add_symbol_when_not_running(self, api_client):
        """Add symbol fails when feed not running / 行情流未运行时添加交易对失败"""
        client, token = api_client
        resp = client.post(
            "/api/v1/paper/market-feed/add-symbol",
            headers={"Authorization": f"Bearer {token}"},
            json={"symbol": "SOLUSDT"},
        )
        assert resp.status_code == 409
