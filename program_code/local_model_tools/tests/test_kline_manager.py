"""
Tests for Kline Manager / K线管理器测试

覆盖范围：
  - KlineBar 创建与更新
  - KlineBuffer 环形缓冲区
  - KlineAggregator 时间对齐与 K线聚合
  - KlineManager 多交易对 × 多时间框架管理
  - 回调机制
  - 边界情况（空数据、首根 K线、跨周期跳跃）
"""

import time
import pytest

from local_model_tools.kline_manager import (
    KlineBar, KlineBuffer, KlineAggregator, KlineManager,
    TIMEFRAME_DURATIONS, DEFAULT_BUFFER_CAPACITY,
)


# =============================================================================
# KlineBar Tests / K线柱测试
# =============================================================================

class TestKlineBar:
    """KlineBar data structure tests / K线柱数据结构测试"""

    def test_create_basic(self):
        """Basic creation sets OHLC to open_price / 基本创建将 OHLC 设为 open_price"""
        bar = KlineBar(open_time_ms=1000, close_time_ms=61000, open_price=100.0)
        assert bar.open == 100.0
        assert bar.high == 100.0
        assert bar.low == 100.0
        assert bar.close == 100.0
        assert bar.volume == 0.0
        assert bar.tick_count == 1
        assert bar.is_closed is False

    def test_update_higher_price(self):
        """Update with higher price updates high and close / 更高价更新 high 和 close"""
        bar = KlineBar(open_time_ms=0, close_time_ms=60000, open_price=100.0)
        bar.update(110.0, volume=0.5)
        assert bar.high == 110.0
        assert bar.low == 100.0
        assert bar.close == 110.0
        assert bar.tick_count == 2
        assert bar.volume == 0.5

    def test_update_lower_price(self):
        """Update with lower price updates low and close / 更低价更新 low 和 close"""
        bar = KlineBar(open_time_ms=0, close_time_ms=60000, open_price=100.0)
        bar.update(90.0)
        assert bar.high == 100.0
        assert bar.low == 90.0
        assert bar.close == 90.0

    def test_multiple_updates(self):
        """Multiple updates track OHLC correctly / 多次更新正确追踪 OHLC"""
        bar = KlineBar(open_time_ms=0, close_time_ms=60000, open_price=100.0)
        bar.update(105.0, volume=1.0)
        bar.update(95.0, volume=0.5)
        bar.update(102.0, volume=0.3)
        assert bar.open == 100.0
        assert bar.high == 105.0
        assert bar.low == 95.0
        assert bar.close == 102.0
        assert bar.tick_count == 4
        assert abs(bar.volume - 1.8) < 1e-10

    def test_to_dict(self):
        """Serialization includes all fields / 序列化包含所有字段"""
        bar = KlineBar(open_time_ms=1000, close_time_ms=61000, open_price=50.0)
        d = bar.to_dict()
        assert d["open_time_ms"] == 1000
        assert d["close_time_ms"] == 61000
        assert d["open"] == 50.0
        assert "is_closed" in d

    def test_repr(self):
        """repr is readable / repr 可读"""
        bar = KlineBar(open_time_ms=0, close_time_ms=60000, open_price=100.0)
        r = repr(bar)
        assert "KlineBar" in r
        assert "100.00" in r


# =============================================================================
# KlineBuffer Tests / K线缓冲区测试
# =============================================================================

class TestKlineBuffer:
    """KlineBuffer circular buffer tests / K线缓冲区测试"""

    def test_empty_buffer(self):
        """New buffer is empty / 新缓冲区为空"""
        buf = KlineBuffer(capacity=10)
        assert len(buf) == 0
        assert buf.latest(5) == []
        assert buf.close_array() == []

    def test_append_and_retrieve(self):
        """Append and retrieve klines / 追加和获取 K线"""
        buf = KlineBuffer(capacity=10)
        bar1 = KlineBar(0, 60000, 100.0)
        bar2 = KlineBar(60000, 120000, 110.0)
        buf.append(bar1)
        buf.append(bar2)
        assert len(buf) == 2
        latest = buf.latest(2)
        assert latest[0].open == 100.0
        assert latest[1].open == 110.0

    def test_capacity_eviction(self):
        """Buffer evicts oldest when full / 缓冲区满时淘汰最旧的"""
        buf = KlineBuffer(capacity=3)
        for i in range(5):
            buf.append(KlineBar(i * 60000, (i + 1) * 60000, float(i)))
        assert len(buf) == 3
        # Should have bars 2, 3, 4 / 应该有 bar 2, 3, 4
        closes = buf.close_array()
        assert closes == [2.0, 3.0, 4.0]

    def test_latest_n(self):
        """latest(n) returns correct subset / latest(n) 返回正确的子集"""
        buf = KlineBuffer(capacity=100)
        for i in range(10):
            buf.append(KlineBar(i * 60000, (i + 1) * 60000, float(i * 10)))
        latest_3 = buf.latest(3)
        assert len(latest_3) == 3
        assert latest_3[0].open == 70.0
        assert latest_3[2].open == 90.0

    def test_latest_more_than_available(self):
        """latest(n) with n > len returns all / latest(n) n 大于实际数量时返回全部"""
        buf = KlineBuffer(capacity=100)
        buf.append(KlineBar(0, 60000, 100.0))
        assert len(buf.latest(99)) == 1

    def test_ohlcv_arrays(self):
        """ohlcv_arrays returns all arrays / ohlcv_arrays 返回所有数组"""
        buf = KlineBuffer(capacity=10)
        bar = KlineBar(0, 60000, 100.0, high=110.0, low=90.0, close=105.0, volume=1.5)
        buf.append(bar)
        arrays = buf.ohlcv_arrays()
        assert arrays["open"] == [100.0]
        assert arrays["high"] == [110.0]
        assert arrays["low"] == [90.0]
        assert arrays["close"] == [105.0]
        assert arrays["volume"] == [1.5]

    def test_clear(self):
        """clear empties the buffer / clear 清空缓冲区"""
        buf = KlineBuffer(capacity=10)
        buf.append(KlineBar(0, 60000, 100.0))
        buf.clear()
        assert len(buf) == 0


# =============================================================================
# KlineAggregator Tests / K线聚合器测试
# =============================================================================

class TestKlineAggregator:
    """KlineAggregator tick-to-kline aggregation tests / K线聚合器测试"""

    def test_invalid_timeframe_raises(self):
        """Invalid timeframe raises ValueError / 无效时间框架抛出 ValueError"""
        with pytest.raises(ValueError):
            KlineAggregator("2m", KlineBuffer())

    def test_first_tick_creates_bar(self):
        """First tick creates a current bar / 首个 tick 创建当前 K线"""
        buf = KlineBuffer()
        agg = KlineAggregator("1m", buf)
        ts = 60000  # aligned to 1m boundary / 对齐到 1 分钟边界
        result = agg.on_tick(100.0, ts)
        assert result is None  # No kline closed yet / 还没有闭合 K线
        assert agg.current_bar is not None
        assert agg.current_bar.open == 100.0

    def test_same_period_updates(self):
        """Ticks within same period update current bar / 同周期 tick 更新当前 K线"""
        buf = KlineBuffer()
        agg = KlineAggregator("1m", buf)
        base_ts = 60000  # 00:01:00
        agg.on_tick(100.0, base_ts)
        agg.on_tick(105.0, base_ts + 10000)  # 00:01:10
        agg.on_tick(95.0, base_ts + 30000)   # 00:01:30
        assert agg.current_bar.high == 105.0
        assert agg.current_bar.low == 95.0
        assert agg.current_bar.tick_count == 3

    def test_new_period_closes_bar(self):
        """Tick in new period closes previous bar / 新周期的 tick 闭合上一个 K线"""
        buf = KlineBuffer()
        closed_bars = []
        agg = KlineAggregator("1m", buf, on_kline_close=lambda tf, bar: closed_bars.append(bar))
        # First period: 00:01:00 ~ 00:01:59 / 第一个周期
        agg.on_tick(100.0, 60000)
        agg.on_tick(110.0, 90000)
        # Second period: 00:02:00 / 第二个周期
        result = agg.on_tick(105.0, 120000)
        assert result is not None
        assert result.is_closed is True
        assert result.open == 100.0
        assert result.high == 110.0
        assert result.close == 110.0
        assert len(buf) == 1
        assert len(closed_bars) == 1

    def test_5m_alignment(self):
        """5m timeframe aligns to 5-minute boundaries / 5 分钟框架对齐到 5 分钟边界"""
        buf = KlineBuffer()
        agg = KlineAggregator("5m", buf)
        # ts at 10:07:23 → aligned to 10:05:00 / 10:07:23 对齐到 10:05:00
        ts = 10 * 3600000 + 7 * 60000 + 23000
        agg.on_tick(100.0, ts)
        bar = agg.current_bar
        expected_start = 10 * 3600000 + 5 * 60000  # 10:05:00
        assert bar.open_time_ms == expected_start
        expected_end = expected_start + 5 * 60000
        assert bar.close_time_ms == expected_end

    def test_period_gap_skips_correctly(self):
        """Gap between periods (e.g., missing data) handles correctly / 周期间的间隔正确处理"""
        buf = KlineBuffer()
        agg = KlineAggregator("1m", buf)
        agg.on_tick(100.0, 60000)   # Period 1
        agg.on_tick(200.0, 300000)  # Period 5 (skip 2,3,4) — closes period 1
        assert len(buf) == 1
        assert buf.latest(1)[0].open == 100.0
        assert agg.current_bar.open == 200.0

    def test_volume_accumulation(self):
        """Volume accumulates within a kline / K线内成交量累加"""
        buf = KlineBuffer()
        agg = KlineAggregator("1m", buf)
        agg.on_tick(100.0, 60000, volume=1.0)
        agg.on_tick(101.0, 70000, volume=2.0)
        agg.on_tick(102.0, 80000, volume=3.0)
        assert abs(agg.current_bar.volume - 6.0) < 1e-10


# =============================================================================
# KlineManager Tests / K线管理器测试
# =============================================================================

class TestKlineManager:
    """KlineManager multi-symbol/timeframe tests / K线管理器多交易对/时间框架测试"""

    def test_basic_creation(self):
        """Manager creates aggregators for specified symbols and timeframes / 管理器为指定交易对和时间框架创建聚合器"""
        mgr = KlineManager(symbols=["BTCUSDT"], timeframes=["1m", "5m"])
        status = mgr.get_status()
        assert "BTCUSDT" in status["symbols"]
        assert "1m" in status["timeframes"]
        assert "5m" in status["timeframes"]

    def test_on_tick(self):
        """on_tick feeds data to all timeframe aggregators / on_tick 将数据输入所有时间框架聚合器"""
        mgr = KlineManager(symbols=["BTCUSDT"], timeframes=["1m", "5m"])
        mgr.on_tick("BTCUSDT", 100.0, ts_ms=60000)
        stats = mgr.get_stats()
        assert stats["total_ticks_processed"] == 1
        assert stats["ticks_by_symbol"]["BTCUSDT"] == 1

    def test_on_price_event_dict(self):
        """on_price_event accepts dict input / on_price_event 接受字典输入"""
        mgr = KlineManager(symbols=["BTCUSDT"], timeframes=["1m"])
        event = {"symbol": "BTCUSDT", "last_price": 45000.0, "ts_ms": 60000}
        mgr.on_price_event(event)
        stats = mgr.get_stats()
        assert stats["total_ticks_processed"] == 1

    def test_on_price_event_object(self):
        """on_price_event accepts object with attributes / on_price_event 接受带属性的对象"""
        class FakeEvent:
            symbol = "ETHUSDT"
            last_price = 3000.0
            ts_ms = 60000
            volume_24h = 100.0
            turnover_24h = 300000.0
        mgr = KlineManager(symbols=["ETHUSDT"], timeframes=["1m"])
        mgr.on_price_event(FakeEvent())
        assert mgr.get_stats()["total_ticks_processed"] == 1

    def test_auto_register_symbol(self):
        """Unknown symbol is auto-registered / 未知交易对自动注册"""
        mgr = KlineManager(symbols=[], timeframes=["1m"])
        mgr.on_tick("SOLUSDT", 25.0, ts_ms=60000)
        assert "SOLUSDT" in mgr.get_stats()["ticks_by_symbol"]

    def test_kline_close_callback(self):
        """Kline close callback is invoked / K线闭合回调被调用"""
        mgr = KlineManager(symbols=["BTCUSDT"], timeframes=["1m"])
        closed_events = []
        mgr.register_on_kline_close(
            lambda sym, tf, bar: closed_events.append((sym, tf, bar))
        )
        # Feed ticks spanning 2 periods / 跨越 2 个周期的 tick
        mgr.on_tick("BTCUSDT", 100.0, ts_ms=60000)
        mgr.on_tick("BTCUSDT", 105.0, ts_ms=90000)
        mgr.on_tick("BTCUSDT", 110.0, ts_ms=120000)  # Closes first period
        assert len(closed_events) == 1
        sym, tf, bar = closed_events[0]
        assert sym == "BTCUSDT"
        assert tf == "1m"
        assert bar.open == 100.0
        assert bar.high == 105.0

    def test_get_buffer(self):
        """get_buffer returns correct buffer / get_buffer 返回正确的缓冲区"""
        mgr = KlineManager(symbols=["BTCUSDT"], timeframes=["1m"])
        buf = mgr.get_buffer("BTCUSDT", "1m")
        assert buf is not None
        assert len(buf) == 0

    def test_get_buffer_unknown(self):
        """get_buffer returns None for unknown symbol / 未知交易对返回 None"""
        mgr = KlineManager(symbols=["BTCUSDT"], timeframes=["1m"])
        assert mgr.get_buffer("UNKNOWN", "1m") is None

    def test_get_latest_klines(self):
        """get_latest_klines returns serialized klines / get_latest_klines 返回序列化的 K线"""
        mgr = KlineManager(symbols=["BTCUSDT"], timeframes=["1m"])
        # Create 3 klines / 创建 3 根 K线
        for i in range(4):
            mgr.on_tick("BTCUSDT", 100.0 + i, ts_ms=60000 * (i + 1))
        klines = mgr.get_latest_klines("BTCUSDT", "1m", n=10)
        assert len(klines) == 3  # 4 ticks = 3 closed klines + 1 building

    def test_get_ohlcv(self):
        """get_ohlcv returns OHLCV arrays / get_ohlcv 返回 OHLCV 数组"""
        mgr = KlineManager(symbols=["BTCUSDT"], timeframes=["1m"])
        for i in range(3):
            mgr.on_tick("BTCUSDT", 100.0 + i * 10, ts_ms=60000 * (i + 1))
        ohlcv = mgr.get_ohlcv("BTCUSDT", "1m")
        # Should have 2 closed klines / 应有 2 根闭合 K线
        assert len(ohlcv["close"]) == 2
        assert ohlcv["close"][0] == 100.0
        assert ohlcv["close"][1] == 110.0

    def test_remove_symbol(self):
        """remove_symbol stops tracking / remove_symbol 停止追踪"""
        mgr = KlineManager(symbols=["BTCUSDT", "ETHUSDT"], timeframes=["1m"])
        mgr.remove_symbol("ETHUSDT")
        assert mgr.get_buffer("ETHUSDT", "1m") is None

    def test_add_symbol(self):
        """add_symbol starts tracking new symbol / add_symbol 开始追踪新交易对"""
        mgr = KlineManager(symbols=[], timeframes=["1m"])
        mgr.add_symbol("DOTUSDT")
        assert mgr.get_buffer("DOTUSDT", "1m") is not None

    def test_clear_all(self):
        """clear_all resets all state / clear_all 重置所有状态"""
        mgr = KlineManager(symbols=["BTCUSDT"], timeframes=["1m"])
        mgr.on_tick("BTCUSDT", 100.0, ts_ms=60000)
        mgr.clear_all()
        assert mgr.get_stats()["total_ticks_processed"] == 0

    def test_multi_symbol_multi_timeframe(self):
        """Multiple symbols × multiple timeframes work independently / 多交易对 × 多时间框架独立运作"""
        mgr = KlineManager(
            symbols=["BTCUSDT", "ETHUSDT"],
            timeframes=["1m", "5m"],
        )
        # Feed BTCUSDT ticks / 输入 BTCUSDT tick
        for i in range(6):
            mgr.on_tick("BTCUSDT", 45000.0 + i * 100, ts_ms=60000 * (i + 1))
        # Feed ETHUSDT ticks / 输入 ETHUSDT tick
        for i in range(6):
            mgr.on_tick("ETHUSDT", 3000.0 + i * 10, ts_ms=60000 * (i + 1))

        # BTCUSDT 1m should have 5 closed klines / BTCUSDT 1m 应有 5 根闭合
        btc_1m = mgr.get_ohlcv("BTCUSDT", "1m")
        assert len(btc_1m["close"]) == 5

        # ETHUSDT 1m should also have 5 / ETHUSDT 1m 也应有 5
        eth_1m = mgr.get_ohlcv("ETHUSDT", "1m")
        assert len(eth_1m["close"]) == 5

        # 5m should have 1 closed kline (6 minutes spans 2 periods: 0-4, 5-9)
        # 5m 应有 1 根闭合 K线（6 分钟跨越 2 个周期：0-4, 5-9）
        btc_5m = mgr.get_ohlcv("BTCUSDT", "5m")
        assert len(btc_5m["close"]) == 1

    def test_invalid_price_ignored(self):
        """Price <= 0 or empty symbol is ignored / 价格 <= 0 或空交易对被忽略"""
        mgr = KlineManager(symbols=["BTCUSDT"], timeframes=["1m"])
        mgr.on_price_event({"symbol": "", "last_price": 100.0, "ts_ms": 60000})
        mgr.on_price_event({"symbol": "BTCUSDT", "last_price": 0, "ts_ms": 60000})
        mgr.on_price_event({"symbol": "BTCUSDT", "last_price": -1, "ts_ms": 60000})
        assert mgr.get_stats()["total_ticks_processed"] == 0

    def test_get_current_bar(self):
        """get_current_bar returns the building bar / get_current_bar 返回正在构建的 K线"""
        mgr = KlineManager(symbols=["BTCUSDT"], timeframes=["1m"])
        mgr.on_tick("BTCUSDT", 100.0, ts_ms=60000)
        bar = mgr.get_current_bar("BTCUSDT", "1m")
        assert bar is not None
        assert bar.open == 100.0
        assert bar.is_closed is False
