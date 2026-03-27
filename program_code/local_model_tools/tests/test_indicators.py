"""
Tests for Technical Indicators / 技术指标测试

覆盖范围：
  - SMA / EMA (moving_averages.py)
  - RSI (rsi.py)
  - MACD (macd.py)
  - Bollinger Bands (bollinger_bands.py)
  - ATR (atr.py)
  - Stochastic (stochastic.py)
  - IndicatorEngine (indicator_engine.py)

每个指标测试：
  1. 正常输入 → 验证数值合理性
  2. 数据不足 → 返回 None
  3. 特殊边界（全涨/全跌/零波动等）
  4. 与已知参考值对比（手动计算或知名工具数值）
"""

import pytest

from local_model_tools.indicators.moving_averages import (
    SMA, EMA,
    compute_sma, compute_ema, compute_sma_series, compute_ema_series,
)
from local_model_tools.indicators.rsi import RSI, compute_rsi, compute_rsi_series
from local_model_tools.indicators.macd import MACD, compute_macd
from local_model_tools.indicators.bollinger_bands import (
    BollingerBands, compute_bollinger_bands, compute_stddev,
)
from local_model_tools.indicators.atr import (
    ATR, compute_atr, compute_true_range, compute_atr_percent,
)
from local_model_tools.indicators.stochastic import Stochastic, compute_stochastic
from local_model_tools.indicator_engine import IndicatorEngine, create_default_indicators
from local_model_tools.kline_manager import KlineManager


# =============================================================================
# Test Data / 测试数据
# =============================================================================

# Simple linear price data / 简单线性价格数据
LINEAR_PRICES = [float(i) for i in range(1, 31)]  # 1.0, 2.0, ..., 30.0

# Realistic BTC-like close prices (50 data points) / 类似 BTC 的收盘价（50 个数据点）
BTC_CLOSE = [
    45000, 45100, 44900, 45200, 45300, 44800, 44700, 45000, 45400, 45500,
    45600, 45300, 45100, 44900, 44700, 45000, 45200, 45400, 45600, 45800,
    46000, 46200, 46100, 45900, 45700, 45500, 45300, 45400, 45600, 45800,
    46000, 46200, 46400, 46600, 46500, 46300, 46100, 45900, 45700, 45800,
    46000, 46200, 46400, 46300, 46100, 45900, 45700, 45800, 46000, 46200,
]

# Realistic high/low prices corresponding to BTC_CLOSE / 对应的最高价/最低价
BTC_HIGH = [p + 200 for p in BTC_CLOSE]
BTC_LOW = [p - 200 for p in BTC_CLOSE]


# =============================================================================
# SMA Tests / SMA 测试
# =============================================================================

class TestSMA:
    """SMA indicator tests / SMA 指标测试"""

    def test_basic_computation(self):
        """SMA of 1-5 with period 5 = 3.0 / [1,2,3,4,5] 的 SMA(5) = 3.0"""
        assert compute_sma([1, 2, 3, 4, 5], 5) == 3.0

    def test_uses_latest_values(self):
        """SMA uses the latest N values / SMA 使用最近 N 个值"""
        # [1,2,3,4,5,6,7,8,9,10], SMA(3) = (8+9+10)/3 = 9.0
        assert compute_sma(list(range(1, 11)), 3) == 9.0

    def test_insufficient_data(self):
        """Returns None if not enough data / 数据不足返回 None"""
        assert compute_sma([1, 2], 5) is None

    def test_period_zero(self):
        """Period 0 returns None / 周期 0 返回 None"""
        assert compute_sma([1, 2, 3], 0) is None

    def test_sma_series_length(self):
        """SMA series has correct length / SMA 序列长度正确"""
        series = compute_sma_series(LINEAR_PRICES, 5)
        assert len(series) == len(LINEAR_PRICES)

    def test_sma_series_first_values(self):
        """First period-1 values are NaN (insufficient data) / 前 period-1 个值为 NaN（数据不足）"""
        import math
        series = compute_sma_series(LINEAR_PRICES, 5)
        for v in series[:4]:
            assert math.isnan(v), f"Expected NaN, got {v}"
        assert series[4] == 3.0  # mean(1,2,3,4,5)

    def test_sma_class(self):
        """SMA class compute method works / SMA 类的 compute 方法有效"""
        sma = SMA(period=5)
        result = sma.compute(close=[1, 2, 3, 4, 5])
        assert result is not None
        assert result["sma"] == 3.0
        assert sma.name == "SMA(5)"
        assert sma.min_periods == 5

    def test_sma_class_insufficient(self):
        """SMA class returns None for insufficient data / 数据不足返回 None"""
        sma = SMA(period=20)
        assert sma.compute(close=[1, 2, 3]) is None


# =============================================================================
# EMA Tests / EMA 测试
# =============================================================================

class TestEMA:
    """EMA indicator tests / EMA 指标测试"""

    def test_basic_computation(self):
        """EMA produces valid result / EMA 产生有效结果"""
        result = compute_ema([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 5)
        assert result is not None
        # EMA should be close to but not equal to SMA for trending data
        # 对于趋势数据，EMA 应接近但不等于 SMA
        assert 7.0 < result < 10.0

    def test_ema_weights_recent_more(self):
        """EMA weights recent data more heavily / EMA 更重视近期数据"""
        # For a strong uptrend, EMA should be >= SMA (more responsive to recent highs)
        # 对于强上升趋势，EMA 应 >= SMA（更能反映近期高点）
        # Use a longer, non-linear series to avoid floating point edge case
        # 使用更长的非线性序列以避免浮点精度边界情况
        data = [float(i ** 1.5) for i in range(1, 31)]
        sma_val = compute_sma(data, 10)
        ema_val = compute_ema(data, 10)
        assert ema_val > sma_val

    def test_insufficient_data(self):
        """Returns None for insufficient data / 数据不足返回 None"""
        assert compute_ema([1, 2], 5) is None

    def test_ema_series_length(self):
        """EMA series has correct length / EMA 序列长度正确"""
        series = compute_ema_series(LINEAR_PRICES, 5)
        assert len(series) == len(LINEAR_PRICES)

    def test_ema_class(self):
        """EMA class works / EMA 类有效"""
        ema = EMA(period=10)
        result = ema.compute(close=LINEAR_PRICES)
        assert result is not None
        assert "ema" in result
        assert ema.name == "EMA(10)"


# =============================================================================
# RSI Tests / RSI 测试
# =============================================================================

class TestRSI:
    """RSI indicator tests / RSI 指标测试"""

    def test_steady_uptrend(self):
        """Pure uptrend → RSI = 100 / 纯上涨 → RSI = 100"""
        # Every day goes up → all gains, no losses → RSI = 100
        up_data = [float(i) for i in range(20)]
        rsi = compute_rsi(up_data, 14)
        assert rsi == 100.0

    def test_steady_downtrend(self):
        """Pure downtrend → RSI = 0 / 纯下跌 → RSI = 0"""
        down_data = [float(20 - i) for i in range(20)]
        rsi = compute_rsi(down_data, 14)
        assert rsi == 0.0

    def test_range_0_to_100(self):
        """RSI is always between 0 and 100 / RSI 总在 0-100 之间"""
        rsi = compute_rsi(BTC_CLOSE, 14)
        assert rsi is not None
        assert 0.0 <= rsi <= 100.0

    def test_typical_value(self):
        """RSI for typical data is in reasonable range / 典型数据的 RSI 在合理范围"""
        rsi = compute_rsi(BTC_CLOSE, 14)
        # BTC_CLOSE has mild uptrend → RSI should be around 40-70
        assert 30.0 < rsi < 80.0

    def test_insufficient_data(self):
        """Returns None for insufficient data / 数据不足返回 None"""
        assert compute_rsi([100, 101, 102], 14) is None

    def test_minimum_data(self):
        """Works with exactly period+1 data points / 精确 period+1 个数据点可计算"""
        data = [float(i) for i in range(15)]
        assert compute_rsi(data, 14) is not None

    def test_rsi_series(self):
        """RSI series has correct length / RSI 序列长度正确"""
        series = compute_rsi_series(BTC_CLOSE, 14)
        assert len(series) == len(BTC_CLOSE)

    def test_rsi_class(self):
        """RSI class works / RSI 类有效"""
        rsi = RSI(period=14)
        result = rsi.compute(close=BTC_CLOSE)
        assert result is not None
        assert "rsi" in result
        assert 0.0 <= result["rsi"] <= 100.0
        assert rsi.name == "RSI(14)"
        assert rsi.min_periods == 15


# =============================================================================
# MACD Tests / MACD 测试
# =============================================================================

class TestMACD:
    """MACD indicator tests / MACD 指标测试"""

    def test_basic_computation(self):
        """MACD returns all three components / MACD 返回全部三个组成部分"""
        result = compute_macd(BTC_CLOSE)
        assert result is not None
        assert "macd" in result
        assert "signal" in result
        assert "histogram" in result

    def test_histogram_is_difference(self):
        """Histogram = MACD - Signal / 柱状图 = MACD - Signal"""
        result = compute_macd(BTC_CLOSE)
        assert result is not None
        assert abs(result["histogram"] - (result["macd"] - result["signal"])) < 1e-10

    def test_uptrend_positive_macd(self):
        """Strong uptrend → positive MACD / 强上升趋势 → 正 MACD"""
        strong_up = [float(i * 100) for i in range(50)]
        result = compute_macd(strong_up)
        assert result is not None
        assert result["macd"] > 0

    def test_insufficient_data(self):
        """Returns None for insufficient data / 数据不足返回 None"""
        assert compute_macd([1, 2, 3], 12, 26, 9) is None

    def test_minimum_data(self):
        """Works with exactly minimum data (slow+signal=35) / 精确最少数据量可计算"""
        data = [float(i) for i in range(35)]
        result = compute_macd(data)
        assert result is not None

    def test_macd_class(self):
        """MACD class works / MACD 类有效"""
        macd = MACD()
        result = macd.compute(close=BTC_CLOSE)
        assert result is not None
        assert macd.name == "MACD(12,26,9)"
        assert macd.min_periods == 35


# =============================================================================
# Bollinger Bands Tests / 布林带测试
# =============================================================================

class TestBollingerBands:
    """Bollinger Bands indicator tests / 布林带指标测试"""

    def test_basic_computation(self):
        """BB returns all five components / BB 返回全部五个组成部分"""
        result = compute_bollinger_bands(BTC_CLOSE)
        assert result is not None
        assert all(k in result for k in ["upper", "middle", "lower", "bandwidth", "percent_b"])

    def test_upper_above_lower(self):
        """Upper band > middle > lower band / 上轨 > 中轨 > 下轨"""
        result = compute_bollinger_bands(BTC_CLOSE)
        assert result["upper"] > result["middle"] > result["lower"]

    def test_middle_is_sma(self):
        """Middle band equals SMA / 中轨等于 SMA"""
        result = compute_bollinger_bands(BTC_CLOSE, period=20)
        expected_sma = sum(BTC_CLOSE[-20:]) / 20
        assert abs(result["middle"] - expected_sma) < 0.01

    def test_zero_volatility(self):
        """Constant price → zero bandwidth / 价格恒定 → 零带宽"""
        flat = [100.0] * 30
        result = compute_bollinger_bands(flat, period=20)
        assert result is not None
        assert result["bandwidth"] == 0.0
        assert result["upper"] == result["middle"] == result["lower"] == 100.0

    def test_percent_b_range(self):
        """percent_b for typical data is 0-1 / 典型数据的 %B 在 0-1 之间"""
        result = compute_bollinger_bands(BTC_CLOSE)
        # Usually between 0 and 1, but can exceed during breakouts
        # 通常在 0-1 之间，但突破时可能超出
        assert -0.5 < result["percent_b"] < 1.5

    def test_stddev_computation(self):
        """Standard deviation computation is correct / 标准差计算正确"""
        values = [2, 4, 4, 4, 5, 5, 7, 9]
        # Population stddev of this: sqrt(((2-5)^2 + ... + (9-5)^2) / 8) = 2.0
        stddev = compute_stddev(values, 8)
        assert abs(stddev - 2.0) < 0.01

    def test_insufficient_data(self):
        """Returns None for insufficient data / 数据不足返回 None"""
        assert compute_bollinger_bands([1, 2, 3], period=20) is None

    def test_bb_class(self):
        """BollingerBands class works / BollingerBands 类有效"""
        bb = BollingerBands(period=20, std_dev_multiplier=2.0)
        result = bb.compute(close=BTC_CLOSE)
        assert result is not None
        assert bb.name == "BB(20,2.0)"
        assert bb.min_periods == 20


# =============================================================================
# ATR Tests / ATR 测试
# =============================================================================

class TestATR:
    """ATR indicator tests / ATR 指标测试"""

    def test_true_range_basic(self):
        """True range computation / True range 计算"""
        high = [110, 115, 112]
        low = [90, 105, 98]
        close = [100, 110, 105]
        tr = compute_true_range(high, low, close)
        assert len(tr) == 3
        # First: 110-90 = 20 / 第一根：日内波幅
        assert tr[0] == 20.0
        # Second: max(115-105, |115-100|, |105-100|) = max(10, 15, 5) = 15
        assert tr[1] == 15.0

    def test_true_range_gap(self):
        """True range captures gaps / True range 捕获跳空"""
        # Gap up: close=100, next day high=130, low=120
        # TR = max(130-120, |130-100|, |120-100|) = max(10, 30, 20) = 30
        high = [110, 130]
        low = [90, 120]
        close = [100, 125]
        tr = compute_true_range(high, low, close)
        assert tr[1] == 30.0  # Gap up captured / 跳空高开被捕获

    def test_atr_basic(self):
        """ATR produces valid result / ATR 产生有效结果"""
        atr = compute_atr(BTC_HIGH, BTC_LOW, BTC_CLOSE, period=14)
        assert atr is not None
        assert atr > 0

    def test_atr_value_reasonable(self):
        """ATR value is reasonable for the price range / ATR 值对于价格范围是合理的"""
        # BTC_HIGH - BTC_LOW = 400 for each bar, so ATR should be around 400
        atr = compute_atr(BTC_HIGH, BTC_LOW, BTC_CLOSE, period=14)
        assert 300 < atr < 500

    def test_atr_percent(self):
        """ATR percent is reasonable / ATR 百分比合理"""
        atr_pct = compute_atr_percent(BTC_HIGH, BTC_LOW, BTC_CLOSE, period=14)
        assert atr_pct is not None
        # 400 / 46200 * 100 ≈ 0.87%
        assert 0.5 < atr_pct < 1.5

    def test_insufficient_data(self):
        """Returns None for insufficient data / 数据不足返回 None"""
        assert compute_atr([100], [90], [95], period=14) is None

    def test_atr_class(self):
        """ATR class works / ATR 类有效"""
        atr = ATR(period=14)
        result = atr.compute(high=BTC_HIGH, low=BTC_LOW, close=BTC_CLOSE)
        assert result is not None
        assert "atr" in result
        assert "atr_percent" in result
        assert atr.name == "ATR(14)"


# =============================================================================
# Stochastic Tests / 随机振荡指标测试
# =============================================================================

class TestStochastic:
    """Stochastic oscillator tests / 随机振荡指标测试"""

    def test_basic_computation(self):
        """Stochastic returns k and d / 随机振荡指标返回 k 和 d"""
        result = compute_stochastic(BTC_HIGH, BTC_LOW, BTC_CLOSE)
        assert result is not None
        assert "k" in result
        assert "d" in result

    def test_range_0_to_100(self):
        """Stochastic %K is between 0 and 100 / %K 在 0-100 之间"""
        result = compute_stochastic(BTC_HIGH, BTC_LOW, BTC_CLOSE)
        assert 0.0 <= result["k"] <= 100.0
        assert 0.0 <= result["d"] <= 100.0

    def test_at_highest_high(self):
        """Close at highest high → %K = 100 / 收盘价在最高高点 → %K = 100"""
        # All same price range, close = high → k should be 100
        high = [100.0] * 20
        low = [90.0] * 20
        close = [100.0] * 20
        result = compute_stochastic(high, low, close, k_period=14, d_period=3)
        assert result is not None
        assert result["k"] == 100.0

    def test_at_lowest_low(self):
        """Close at lowest low → %K = 0 / 收盘价在最低低点 → %K = 0"""
        high = [100.0] * 20
        low = [90.0] * 20
        close = [90.0] * 20
        result = compute_stochastic(high, low, close, k_period=14, d_period=3)
        assert result is not None
        assert result["k"] == 0.0

    def test_insufficient_data(self):
        """Returns None for insufficient data / 数据不足返回 None"""
        assert compute_stochastic([100], [90], [95]) is None

    def test_stochastic_class(self):
        """Stochastic class works / Stochastic 类有效"""
        stoch = Stochastic(k_period=14, d_period=3)
        result = stoch.compute(high=BTC_HIGH, low=BTC_LOW, close=BTC_CLOSE)
        assert result is not None
        assert stoch.name == "Stochastic(14,3)"
        assert stoch.min_periods == 16  # 14 + 3 - 1


# =============================================================================
# IndicatorEngine Tests / 指标引擎测试
# =============================================================================

class TestIndicatorEngine:
    """IndicatorEngine tests / 指标引擎测试"""

    def _setup_engine_with_data(self):
        """
        Helper: create a KlineManager + IndicatorEngine with sufficient data.
        辅助：创建有足够数据的 KlineManager + IndicatorEngine。
        """
        km = KlineManager(symbols=["BTCUSDT"], timeframes=["1m"])
        engine = IndicatorEngine(kline_manager=km)
        # Feed 50 klines worth of data (need 51 ticks to close 50 klines)
        # 输入 50 根 K线的数据（需要 51 个 tick 来闭合 50 根 K线）
        for i in range(51):
            km.on_tick("BTCUSDT", BTC_CLOSE[i % len(BTC_CLOSE)], ts_ms=60000 * (i + 1))
        return km, engine

    def test_default_indicators(self):
        """Default indicator set is populated / 默认指标集已填充"""
        defaults = create_default_indicators()
        names = [i.name for i in defaults]
        assert "SMA(20)" in names
        assert "RSI(14)" in names
        assert "MACD(12,26,9)" in names
        assert "BB(20,2.0)" in names
        assert "ATR(14)" in names

    def test_auto_computation_on_kline_close(self):
        """Indicators are computed when klines close / K线闭合时自动计算指标"""
        km, engine = self._setup_engine_with_data()
        indicators = engine.get_indicators("BTCUSDT", "1m")
        # Should have computed indicators / 应该已计算了指标
        assert len(indicators) > 0
        # SMA(20) should have a value (50 klines > 20 min_periods)
        assert indicators.get("SMA(20)") is not None

    def test_get_indicator_specific(self):
        """Get a specific indicator value / 获取特定指标值"""
        km, engine = self._setup_engine_with_data()
        rsi = engine.get_indicator("BTCUSDT", "1m", "RSI(14)")
        assert rsi is not None
        assert "rsi" in rsi
        assert 0 <= rsi["rsi"] <= 100

    def test_get_indicators_empty(self):
        """No data returns empty dict / 无数据返回空字典"""
        km = KlineManager(symbols=["BTCUSDT"], timeframes=["1m"])
        engine = IndicatorEngine(kline_manager=km)
        assert engine.get_indicators("BTCUSDT", "1m") == {}

    def test_callback_on_update(self):
        """Callback is invoked on indicator update / 指标更新时回调被调用"""
        km = KlineManager(symbols=["BTCUSDT"], timeframes=["1m"])
        engine = IndicatorEngine(kline_manager=km)
        updates = []
        engine.register_on_update(
            lambda sym, tf, results: updates.append((sym, tf))
        )
        # Feed enough data to trigger kline closes / 输入足够数据触发 K线闭合
        for i in range(25):
            km.on_tick("BTCUSDT", 45000.0 + i * 10, ts_ms=60000 * (i + 1))
        # Should have received callbacks / 应收到回调
        assert len(updates) > 0
        assert updates[0][0] == "BTCUSDT"

    def test_compute_now(self):
        """Force immediate computation / 强制立即计算"""
        km, engine = self._setup_engine_with_data()
        result = engine.compute_now("BTCUSDT", "1m")
        assert len(result) > 0

    def test_get_all_cached(self):
        """get_all_cached returns all data / get_all_cached 返回所有数据"""
        km, engine = self._setup_engine_with_data()
        all_cached = engine.get_all_cached()
        assert "BTCUSDT:1m" in all_cached

    def test_register_custom_indicator(self):
        """Custom indicator can be registered / 可注册自定义指标"""
        km = KlineManager(symbols=["BTCUSDT"], timeframes=["1m"])
        engine = IndicatorEngine(kline_manager=km, indicators=[SMA(10)])
        engine.register_indicator(RSI(7))
        status = engine.get_status()
        names = status["indicators_registered"]
        assert "SMA(10)" in names
        assert "RSI(7)" in names

    def test_clear_cache(self):
        """clear_cache empties all cached values / clear_cache 清空所有缓存"""
        km, engine = self._setup_engine_with_data()
        engine.clear_cache()
        assert engine.get_indicators("BTCUSDT", "1m") == {}

    def test_status(self):
        """get_status returns comprehensive info / get_status 返回全面信息"""
        km, engine = self._setup_engine_with_data()
        status = engine.get_status()
        assert status["component"] == "indicator_engine"
        assert "indicators_registered" in status
        assert "stats" in status
