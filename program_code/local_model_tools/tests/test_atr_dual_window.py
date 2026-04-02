"""
Tests for U-09: ATR Fast/Slow Dual Window
U-09 测试：ATR 快/慢双窗口

MODULE_NOTE (中文):
  验证 IndicatorEngine 的 ATR 双窗口功能（ATR_5 快窗口 + ATR_14 慢窗口）。
  核心行为：get_conservative_atr() 返回 max(ATR_fast, ATR_slow)。
  在 regime 快速切换时，快窗口（5 期）应比慢窗口（14 期）反应更快。

MODULE_NOTE (English):
  Tests for the IndicatorEngine ATR dual-window feature (ATR_5 fast + ATR_14 slow).
  Core behavior: get_conservative_atr() returns max(ATR_fast, ATR_slow).
  During rapid regime switches, fast window (5-period) should react faster than slow (14-period).

Test coverage:
  1. ATR_5 and ATR_14 compute correctly from separate indicator instances
  2. max(ATR_5, ATR_14) = conservative value (larger of the two)
  3. Insufficient data (<5 bars): ATR_5 = None, fallback to ATR_14
  4. Insufficient data (<14 bars): both None
  5. Regime rapid switch: ATR_5 > ATR_14 (fast window reacts faster)
  6. Default indicators include both ATR(5) and ATR(14)
  7. Backward compatibility: existing ATR(14) consumers unaffected
  8. get_conservative_atr returns correct structure
"""

import pytest

from local_model_tools.indicators.atr import ATR, compute_atr
from local_model_tools.indicator_engine import (
    IndicatorEngine,
    create_default_indicators,
    ATR_FAST_PERIOD,
    ATR_SLOW_PERIOD,
)
from local_model_tools.kline_manager import KlineManager


# =============================================================================
# Test Data / 测试数据
# =============================================================================

def _make_stable_ohlcv(n: int, base: float = 100.0, volatility: float = 1.0):
    """
    Generate stable OHLCV data with controlled volatility.
    生成具有可控波动率的稳定 OHLCV 数据。
    """
    import math
    high, low, close, open_, volume = [], [], [], [], []
    for i in range(n):
        c = base + math.sin(i * 0.5) * volatility
        h = c + volatility * 0.5
        l = c - volatility * 0.5
        o = c - volatility * 0.1
        open_.append(o)
        high.append(h)
        low.append(l)
        close.append(c)
        volume.append(1000.0)
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume}


def _make_regime_switch_ohlcv(
    n_calm: int = 20, n_volatile: int = 10, base: float = 100.0,
):
    """
    Generate OHLCV with a calm period followed by a volatile period.
    生成先平静后剧烈波动的 OHLCV 数据，模拟 regime 快速切换。
    """
    import math
    high, low, close, open_, volume = [], [], [], [], []

    # Calm period: low volatility / 平静期：低波动
    for i in range(n_calm):
        c = base + math.sin(i * 0.3) * 0.5
        h = c + 0.3
        l = c - 0.3
        o = c - 0.1
        open_.append(o)
        high.append(h)
        low.append(l)
        close.append(c)
        volume.append(1000.0)

    # Volatile period: high volatility (5x) / 剧烈期：高波动（5 倍）
    for i in range(n_volatile):
        c = base + math.sin(i * 0.8) * 5.0
        h = c + 3.0
        l = c - 3.0
        o = c - 1.0
        open_.append(o)
        high.append(h)
        low.append(l)
        close.append(c)
        volume.append(5000.0)

    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume}


# =============================================================================
# Test: Default indicators include both ATR windows / 默认指标包含两个 ATR 窗口
# =============================================================================

class TestDefaultIndicators:
    """Verify create_default_indicators() includes ATR(5) and ATR(14)."""

    def test_default_includes_atr_fast_and_slow(self):
        """Default indicator set must include ATR(5) and ATR(14)."""
        indicators = create_default_indicators()
        names = [ind.name for ind in indicators]
        assert f"ATR({ATR_FAST_PERIOD})" in names, f"ATR({ATR_FAST_PERIOD}) missing from defaults"
        assert f"ATR({ATR_SLOW_PERIOD})" in names, f"ATR({ATR_SLOW_PERIOD}) missing from defaults"

    def test_atr_fast_period_constant(self):
        """ATR_FAST_PERIOD should be 5."""
        assert ATR_FAST_PERIOD == 5

    def test_atr_slow_period_constant(self):
        """ATR_SLOW_PERIOD should be 14."""
        assert ATR_SLOW_PERIOD == 14


# =============================================================================
# Test: ATR(5) and ATR(14) compute correctly / ATR(5) 和 ATR(14) 分别计算正确
# =============================================================================

class TestATRDualCompute:
    """Verify both ATR windows produce correct, independent results."""

    def test_atr5_and_atr14_both_compute(self):
        """Both ATR(5) and ATR(14) should compute from sufficient data (30 bars)."""
        ohlcv = _make_stable_ohlcv(30, base=100.0, volatility=2.0)
        atr5 = ATR(period=5)
        atr14 = ATR(period=14)
        r5 = atr5.compute(
            open=ohlcv["open"], high=ohlcv["high"],
            low=ohlcv["low"], close=ohlcv["close"], volume=ohlcv["volume"],
        )
        r14 = atr14.compute(
            open=ohlcv["open"], high=ohlcv["high"],
            low=ohlcv["low"], close=ohlcv["close"], volume=ohlcv["volume"],
        )
        assert r5 is not None, "ATR(5) should compute with 30 bars"
        assert r14 is not None, "ATR(14) should compute with 30 bars"
        assert r5["atr"] > 0
        assert r14["atr"] > 0
        assert r5["atr_percent"] > 0
        assert r14["atr_percent"] > 0

    def test_atr5_none_with_insufficient_data(self):
        """ATR(5) should return None with fewer than 5 bars."""
        ohlcv = _make_stable_ohlcv(4)
        atr5 = ATR(period=5)
        result = atr5.compute(
            open=ohlcv["open"], high=ohlcv["high"],
            low=ohlcv["low"], close=ohlcv["close"], volume=ohlcv["volume"],
        )
        assert result is None, "ATR(5) must be None with only 4 bars"

    def test_atr14_none_with_insufficient_data(self):
        """ATR(14) should return None with fewer than 14 bars."""
        ohlcv = _make_stable_ohlcv(13)
        atr14 = ATR(period=14)
        result = atr14.compute(
            open=ohlcv["open"], high=ohlcv["high"],
            low=ohlcv["low"], close=ohlcv["close"], volume=ohlcv["volume"],
        )
        assert result is None, "ATR(14) must be None with only 13 bars"

    def test_atr5_available_but_atr14_not(self):
        """
        With exactly 10 bars: ATR(5) should compute, ATR(14) should be None.
        数据恰好 10 根时：ATR(5) 可计算，ATR(14) 返回 None（数据不足）。
        """
        ohlcv = _make_stable_ohlcv(10, volatility=1.5)
        atr5 = ATR(period=5)
        atr14 = ATR(period=14)
        r5 = atr5.compute(
            open=ohlcv["open"], high=ohlcv["high"],
            low=ohlcv["low"], close=ohlcv["close"], volume=ohlcv["volume"],
        )
        r14 = atr14.compute(
            open=ohlcv["open"], high=ohlcv["high"],
            low=ohlcv["low"], close=ohlcv["close"], volume=ohlcv["volume"],
        )
        assert r5 is not None, "ATR(5) should compute with 10 bars"
        assert r14 is None, "ATR(14) should be None with only 10 bars"


# =============================================================================
# Test: get_conservative_atr / 保守 ATR 查询
# =============================================================================

class TestGetConservativeATR:
    """Verify get_conservative_atr() returns max(fast, slow) correctly."""

    def _make_engine_with_cache(self, fast_val, slow_val, fast_pct=None, slow_pct=None):
        """Helper: create engine and inject cache directly for unit testing."""
        km = KlineManager()
        engine = IndicatorEngine(kline_manager=km)
        # Inject cache directly / 直接注入缓存
        cache_entry = {}
        if fast_val is not None:
            cache_entry[f"ATR({ATR_FAST_PERIOD})"] = {
                "atr": fast_val,
                "atr_percent": fast_pct if fast_pct is not None else fast_val,
            }
        if slow_val is not None:
            cache_entry[f"ATR({ATR_SLOW_PERIOD})"] = {
                "atr": slow_val,
                "atr_percent": slow_pct if slow_pct is not None else slow_val,
            }
        engine._cache[("BTCUSDT", "1h")] = cache_entry
        return engine

    def test_conservative_is_max_when_both_available(self):
        """atr_conservative = max(fast, slow) when both are available."""
        engine = self._make_engine_with_cache(fast_val=500.0, slow_val=350.0)
        result = engine.get_conservative_atr("BTCUSDT", "1h")
        assert result["atr_conservative"] == 500.0
        assert result["atr_fast"] == 500.0
        assert result["atr_slow"] == 350.0

    def test_conservative_picks_slow_when_larger(self):
        """atr_conservative = slow when slow > fast."""
        engine = self._make_engine_with_cache(fast_val=200.0, slow_val=400.0)
        result = engine.get_conservative_atr("BTCUSDT", "1h")
        assert result["atr_conservative"] == 400.0

    def test_fallback_to_slow_when_fast_none(self):
        """
        When fast is None (data < 5 bars), conservative falls back to slow.
        快窗口为 None 时（数据不足 5 根），保守值回退到慢窗口。
        """
        engine = self._make_engine_with_cache(fast_val=None, slow_val=350.0)
        result = engine.get_conservative_atr("BTCUSDT", "1h")
        assert result["atr_fast"] is None
        assert result["atr_slow"] == 350.0
        assert result["atr_conservative"] == 350.0

    def test_fallback_to_fast_when_slow_none(self):
        """
        When slow is None (data < 14 bars), conservative falls back to fast.
        慢窗口为 None 时（数据不足 14 根），保守值回退到快窗口。
        """
        engine = self._make_engine_with_cache(fast_val=250.0, slow_val=None)
        result = engine.get_conservative_atr("BTCUSDT", "1h")
        assert result["atr_fast"] == 250.0
        assert result["atr_slow"] is None
        assert result["atr_conservative"] == 250.0

    def test_both_none_when_no_data(self):
        """
        When both windows lack data, all values are None.
        两个窗口都没数据时，所有值为 None。
        """
        km = KlineManager()
        engine = IndicatorEngine(kline_manager=km)
        result = engine.get_conservative_atr("NONEXISTENT", "1h")
        assert result["atr_fast"] is None
        assert result["atr_slow"] is None
        assert result["atr_conservative"] is None
        assert result["atr_conservative_pct"] is None

    def test_conservative_pct_is_max(self):
        """atr_conservative_pct = max(fast_pct, slow_pct)."""
        engine = self._make_engine_with_cache(
            fast_val=500.0, slow_val=350.0,
            fast_pct=1.2, slow_pct=0.8,
        )
        result = engine.get_conservative_atr("BTCUSDT", "1h")
        assert result["atr_conservative_pct"] == 1.2

    def test_return_dict_has_all_keys(self):
        """Return dict must contain all 6 expected keys."""
        km = KlineManager()
        engine = IndicatorEngine(kline_manager=km)
        result = engine.get_conservative_atr("ANY", "5m")
        expected_keys = {
            "atr_fast", "atr_slow", "atr_conservative",
            "atr_fast_pct", "atr_slow_pct", "atr_conservative_pct",
        }
        assert set(result.keys()) == expected_keys


# =============================================================================
# Test: Regime switch — fast window reacts faster / 快窗口在 regime 切换时反应更快
# =============================================================================

class TestRegimeSwitchReactivity:
    """
    Verify that ATR(5) reacts faster than ATR(14) during regime switches.
    验证 regime 快速切换时 ATR(5) 比 ATR(14) 反应更快。
    """

    def test_fast_window_larger_after_volatility_spike(self):
        """
        After a sudden volatility increase, ATR(5) should be larger than ATR(14)
        because the fast window adapts to the new regime more quickly.
        波动率突然增大后，ATR(5) 应大于 ATR(14)，因为快窗口更快适应新 regime。
        """
        ohlcv = _make_regime_switch_ohlcv(n_calm=20, n_volatile=10, base=100.0)

        atr5 = compute_atr(
            ohlcv["high"], ohlcv["low"], ohlcv["close"], period=5,
        )
        atr14 = compute_atr(
            ohlcv["high"], ohlcv["low"], ohlcv["close"], period=14,
        )

        assert atr5 is not None, "ATR(5) should compute with 30 bars"
        assert atr14 is not None, "ATR(14) should compute with 30 bars"
        # After calm→volatile transition, ATR(5) should be higher
        # 从平静到剧烈波动后，ATR(5) 应该更高
        assert atr5 > atr14, (
            f"After regime switch to high volatility, ATR(5)={atr5:.4f} "
            f"should exceed ATR(14)={atr14:.4f} / "
            f"regime 切换到高波动后，ATR(5) 应大于 ATR(14)"
        )

    def test_conservative_equals_fast_after_spike(self):
        """
        After volatility spike, conservative = fast (since fast > slow).
        波动率突增后，保守值 = 快窗口值（因为快 > 慢）。
        """
        ohlcv = _make_regime_switch_ohlcv(n_calm=20, n_volatile=10, base=100.0)

        atr5 = compute_atr(ohlcv["high"], ohlcv["low"], ohlcv["close"], period=5)
        atr14 = compute_atr(ohlcv["high"], ohlcv["low"], ohlcv["close"], period=14)

        conservative = max(atr5, atr14) if atr5 and atr14 else None
        assert conservative == atr5, "Conservative should equal fast window after spike"


# =============================================================================
# Test: Backward compatibility / 向后兼容
# =============================================================================

class TestBackwardCompatibility:
    """Existing ATR(14) consumers should not break."""

    def test_atr14_still_in_cache_by_name(self):
        """ATR(14) is still accessible by its standard name in the cache."""
        km = KlineManager()
        engine = IndicatorEngine(kline_manager=km)
        # Manually inject some data
        engine._cache[("ETHUSDT", "5m")] = {
            f"ATR({ATR_SLOW_PERIOD})": {"atr": 30.0, "atr_percent": 1.5},
        }
        result = engine.get_indicator("ETHUSDT", "5m", f"ATR({ATR_SLOW_PERIOD})")
        assert result is not None
        assert result["atr"] == 30.0

    def test_get_indicators_returns_both_atr_entries(self):
        """get_indicators() returns both ATR(5) and ATR(14) entries."""
        km = KlineManager()
        engine = IndicatorEngine(kline_manager=km)
        engine._cache[("BTCUSDT", "1h")] = {
            f"ATR({ATR_FAST_PERIOD})": {"atr": 500.0, "atr_percent": 1.0},
            f"ATR({ATR_SLOW_PERIOD})": {"atr": 350.0, "atr_percent": 0.7},
        }
        all_indics = engine.get_indicators("BTCUSDT", "1h")
        assert f"ATR({ATR_FAST_PERIOD})" in all_indics
        assert f"ATR({ATR_SLOW_PERIOD})" in all_indics
