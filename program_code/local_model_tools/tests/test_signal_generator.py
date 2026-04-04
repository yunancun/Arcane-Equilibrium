"""
Tests for Signal Generator / 信号生成器测试

覆盖范围：
  - Signal 数据结构
  - RSIOverboughtOversoldRule
  - MACrossoverRule
  - BollingerBandReversionRule
  - MACDCrossoverRule
  - SignalEngine（评估、历史、回调、摘要）
"""

import pytest

from local_model_tools.signal_generator import (
    Signal,
    SignalRule,
    SignalEngine,
    RSIOverboughtOversoldRule,
    MACrossoverRule,
    BollingerBandReversionRule,
    MACDCrossoverRule,
    create_default_signal_rules,
    DIRECTION_LONG,
    DIRECTION_SHORT,
    DIRECTION_NEUTRAL,
    DIRECTION_CLOSE_LONG,
)


# =============================================================================
# Signal Tests / Signal 数据结构测试
# =============================================================================

class TestSignal:
    """Signal data structure tests / Signal 数据结构测试"""

    def test_create_basic(self):
        """Basic Signal creation / 基本创建"""
        s = Signal(symbol="BTCUSDT", direction="long", confidence=0.7)
        assert s.symbol == "BTCUSDT"
        assert s.direction == "long"
        assert s.confidence == 0.7
        assert s.is_actionable is True
        assert s.is_entry is True
        assert s.is_exit is False

    def test_invalid_direction_raises(self):
        """Invalid direction raises ValueError / 无效方向抛出 ValueError"""
        with pytest.raises(ValueError):
            Signal(symbol="BTCUSDT", direction="invalid", confidence=0.5)

    def test_confidence_clamped(self):
        """Confidence is clamped to [0, 1] / 置信度限制在 [0, 1]"""
        s = Signal(symbol="BTCUSDT", direction="long", confidence=1.5)
        assert s.confidence == 1.0
        s2 = Signal(symbol="BTCUSDT", direction="long", confidence=-0.5)
        assert s2.confidence == 0.0

    def test_neutral_not_actionable(self):
        """Neutral signal is not actionable / 中性信号不可执行"""
        s = Signal(symbol="BTCUSDT", direction="neutral", confidence=0.5)
        assert s.is_actionable is False

    def test_exit_signals(self):
        """Exit signals identified correctly / 出场信号正确识别"""
        s = Signal(symbol="BTCUSDT", direction="close_long", confidence=0.8)
        assert s.is_exit is True
        assert s.is_entry is False

    def test_to_dict(self):
        """Serialization includes all fields / 序列化包含所有字段"""
        s = Signal(symbol="ETHUSDT", direction="short", confidence=0.6, edge_bps=25)
        d = s.to_dict()
        assert d["symbol"] == "ETHUSDT"
        assert d["direction"] == "short"
        assert d["confidence"] == 0.6
        assert d["edge_bps"] == 25
        assert "is_actionable" in d

    def test_repr(self):
        """repr is readable / repr 可读"""
        s = Signal(symbol="BTCUSDT", direction="long", confidence=0.7, source="test")
        assert "BTCUSDT" in repr(s)
        assert "long" in repr(s)


# =============================================================================
# RSI Overbought/Oversold Rule Tests / RSI 超买超卖规则测试
# =============================================================================

class TestRSIOverboughtOversoldRule:
    """RSI overbought/oversold rule tests"""

    def test_oversold_generates_long(self):
        """RSI < 30 → long signal / RSI < 30 → 做多信号"""
        rule = RSIOverboughtOversoldRule()
        signal = rule.evaluate("BTCUSDT", "1h", {"RSI(14)": {"rsi": 20.0}})
        assert signal is not None
        assert signal.direction == DIRECTION_LONG
        assert signal.confidence > 0.3

    def test_overbought_generates_short(self):
        """RSI > 70 → short signal / RSI > 70 → 做空信号"""
        rule = RSIOverboughtOversoldRule()
        signal = rule.evaluate("BTCUSDT", "1h", {"RSI(14)": {"rsi": 85.0}})
        assert signal is not None
        assert signal.direction == DIRECTION_SHORT

    def test_neutral_no_signal(self):
        """RSI in normal range → no signal / RSI 在正常范围 → 无信号"""
        rule = RSIOverboughtOversoldRule()
        signal = rule.evaluate("BTCUSDT", "1h", {"RSI(14)": {"rsi": 55.0}})
        assert signal is None

    def test_missing_rsi_no_signal(self):
        """Missing RSI data → no signal / 缺少 RSI 数据 → 无信号"""
        rule = RSIOverboughtOversoldRule()
        assert rule.evaluate("BTCUSDT", "1h", {}) is None
        assert rule.evaluate("BTCUSDT", "1h", {"RSI(14)": None}) is None

    def test_extreme_oversold_high_confidence(self):
        """Very low RSI → higher confidence / 极低 RSI → 更高置信度"""
        rule = RSIOverboughtOversoldRule()
        s1 = rule.evaluate("BTCUSDT", "1h", {"RSI(14)": {"rsi": 25.0}})
        s2 = rule.evaluate("BTCUSDT", "1h", {"RSI(14)": {"rsi": 10.0}})
        assert s2.confidence > s1.confidence


# =============================================================================
# MA Crossover Rule Tests / MA 交叉规则测试
# =============================================================================

class TestMACrossoverRule:
    """MA crossover rule tests"""

    def test_bullish_crossover(self):
        """Fast > Slow → long / 快线 > 慢线 → 做多"""
        rule = MACrossoverRule()
        signal = rule.evaluate("BTCUSDT", "1h", {
            "EMA(12)": {"ema": 45200.0},
            "EMA(26)": {"ema": 45000.0},
        })
        assert signal is not None
        assert signal.direction == DIRECTION_LONG

    def test_bearish_crossover(self):
        """Fast < Slow → short / 快线 < 慢线 → 做空"""
        rule = MACrossoverRule()
        signal = rule.evaluate("BTCUSDT", "1h", {
            "EMA(12)": {"ema": 44800.0},
            "EMA(26)": {"ema": 45000.0},
        })
        assert signal is not None
        assert signal.direction == DIRECTION_SHORT

    def test_no_spread_no_signal(self):
        """Nearly equal MAs → no signal / MA 几乎相等 → 无信号"""
        rule = MACrossoverRule()
        signal = rule.evaluate("BTCUSDT", "1h", {
            "EMA(12)": {"ema": 45000.0},
            "EMA(26)": {"ema": 45000.0},
        })
        assert signal is None

    def test_missing_data_no_signal(self):
        """Missing MA data → no signal / 缺少 MA 数据 → 无信号"""
        rule = MACrossoverRule()
        assert rule.evaluate("BTCUSDT", "1h", {"EMA(12)": {"ema": 100}}) is None

    def test_sma_also_works(self):
        """SMA keys also work / SMA 键也有效"""
        rule = MACrossoverRule(fast_name="SMA(10)", slow_name="SMA(30)")
        signal = rule.evaluate("BTCUSDT", "1h", {
            "SMA(10)": {"sma": 46000.0},
            "SMA(30)": {"sma": 45000.0},
        })
        assert signal is not None
        assert signal.direction == DIRECTION_LONG


# =============================================================================
# Bollinger Band Reversion Rule Tests / 布林带均值回归规则测试
# =============================================================================

class TestBollingerBandReversionRule:
    """Bollinger Band mean reversion rule tests"""

    def test_below_lower_band_long(self):
        """Price below lower band with RSI oversold → long / 价格低于下轨 + RSI 超卖 → 做多"""
        rule = BollingerBandReversionRule()
        signal = rule.evaluate("BTCUSDT", "1h", {
            "BB(20,2.0)": {"percent_b": -0.1, "bandwidth": 0.03},
            "RSI(14)": {"rsi": 25.0},
        })
        assert signal is not None
        assert signal.direction == DIRECTION_LONG

    def test_above_upper_band_short(self):
        """Price above upper band with RSI overbought → short / 价格高于上轨 + RSI 超买 → 做空"""
        rule = BollingerBandReversionRule()
        signal = rule.evaluate("BTCUSDT", "1h", {
            "BB(20,2.0)": {"percent_b": 1.2, "bandwidth": 0.03},
            "RSI(14)": {"rsi": 75.0},
        })
        assert signal is not None
        assert signal.direction == DIRECTION_SHORT

    def test_rsi_disagrees_no_signal(self):
        """RSI doesn't confirm → no signal / RSI 不确认 → 无信号"""
        rule = BollingerBandReversionRule()
        # Price below lower band but RSI is normal (55) — RSI doesn't agree
        signal = rule.evaluate("BTCUSDT", "1h", {
            "BB(20,2.0)": {"percent_b": -0.1, "bandwidth": 0.03},
            "RSI(14)": {"rsi": 55.0},
        })
        assert signal is None

    def test_squeeze_no_signal(self):
        """Narrow bandwidth (squeeze) → no signal / 带宽过窄（收窄）→ 无信号"""
        rule = BollingerBandReversionRule()
        signal = rule.evaluate("BTCUSDT", "1h", {
            "BB(20,2.0)": {"percent_b": -0.5, "bandwidth": 0.005},
            "RSI(14)": {"rsi": 20.0},
        })
        assert signal is None

    def test_normal_range_no_signal(self):
        """Price within bands → no signal / 价格在带内 → 无信号"""
        rule = BollingerBandReversionRule()
        signal = rule.evaluate("BTCUSDT", "1h", {
            "BB(20,2.0)": {"percent_b": 0.5, "bandwidth": 0.03},
            "RSI(14)": {"rsi": 50.0},
        })
        assert signal is None

    def test_no_rsi_confirm_mode(self):
        """Without RSI confirmation, only BB matters / 无 RSI 确认模式只看 BB"""
        rule = BollingerBandReversionRule(rsi_confirm=False)
        signal = rule.evaluate("BTCUSDT", "1h", {
            "BB(20,2.0)": {"percent_b": -0.1, "bandwidth": 0.03},
        })
        assert signal is not None
        assert signal.direction == DIRECTION_LONG


# =============================================================================
# MACD Crossover Rule Tests / MACD 交叉规则测试
# =============================================================================

class TestMACDCrossoverRule:
    """MACD crossover rule tests"""

    def test_bullish_macd(self):
        """MACD > 0 and histogram > 0 → long / MACD > 0 且柱状图 > 0 → 做多"""
        rule = MACDCrossoverRule()
        signal = rule.evaluate("BTCUSDT", "1h", {
            "MACD(12,26,9)": {"macd": 100.0, "signal": 50.0, "histogram": 50.0},
        })
        assert signal is not None
        assert signal.direction == DIRECTION_LONG

    def test_bearish_macd(self):
        """MACD < 0 and histogram < 0 → short / MACD < 0 且柱状图 < 0 → 做空"""
        rule = MACDCrossoverRule()
        signal = rule.evaluate("BTCUSDT", "1h", {
            "MACD(12,26,9)": {"macd": -100.0, "signal": -50.0, "histogram": -50.0},
        })
        assert signal is not None
        assert signal.direction == DIRECTION_SHORT

    def test_conflicting_no_signal(self):
        """MACD and histogram disagree → no signal / MACD 和柱状图方向不一致 → 无信号"""
        rule = MACDCrossoverRule()
        signal = rule.evaluate("BTCUSDT", "1h", {
            "MACD(12,26,9)": {"macd": 100.0, "signal": 150.0, "histogram": -50.0},
        })
        assert signal is None

    def test_zero_values_no_signal(self):
        """All zeros → no signal / 全零 → 无信号"""
        rule = MACDCrossoverRule()
        signal = rule.evaluate("BTCUSDT", "1h", {
            "MACD(12,26,9)": {"macd": 0.0, "signal": 0.0, "histogram": 0.0},
        })
        assert signal is None


# =============================================================================
# SignalEngine Tests / 信号引擎测试
# =============================================================================

class TestSignalEngine:
    """SignalEngine tests / 信号引擎测试"""

    def _make_oversold_indicators(self):
        """Helper: indicators that should trigger oversold signals / 辅助：应触发超卖信号的指标"""
        return {
            "RSI(14)": {"rsi": 18.0},
            "EMA(12)": {"ema": 44800.0},
            "EMA(26)": {"ema": 45000.0},
            "BB(20,2.0)": {"percent_b": -0.2, "bandwidth": 0.03},
            "MACD(12,26,9)": {"macd": -200.0, "signal": -150.0, "histogram": -50.0},
        }

    def test_default_rules(self):
        """Default rules are populated / 默认规则已填充"""
        rules = create_default_signal_rules()
        assert len(rules) == 9  # B1: +1 for KAMACrossoverRule

    def test_evaluation_generates_signals(self):
        """Evaluation of oversold indicators generates signals / 评估超卖指标产生信号"""
        engine = SignalEngine()
        signals = engine.on_indicators_update("BTCUSDT", "1h", self._make_oversold_indicators())
        # At least RSI oversold should trigger / 至少 RSI 超卖应触发
        assert len(signals) >= 1
        directions = {s.direction for s in signals}
        assert DIRECTION_LONG in directions or DIRECTION_SHORT in directions

    def test_history_recorded(self):
        """Generated signals are recorded in history / 生成的信号记录在历史中"""
        engine = SignalEngine()
        engine.on_indicators_update("BTCUSDT", "1h", self._make_oversold_indicators())
        history = engine.get_latest_signals()
        assert len(history) > 0

    def test_callback_invoked(self):
        """Signal callbacks are invoked / 信号回调被调用"""
        engine = SignalEngine()
        received = []
        engine.register_on_signal(lambda s: received.append(s))
        engine.on_indicators_update("BTCUSDT", "1h", self._make_oversold_indicators())
        assert len(received) >= 1

    def test_filter_by_symbol(self):
        """get_latest_signals filters by symbol / 按交易对过滤"""
        engine = SignalEngine()
        engine.on_indicators_update("BTCUSDT", "1h", self._make_oversold_indicators())
        engine.on_indicators_update("ETHUSDT", "1h", {"RSI(14)": {"rsi": 50.0}})
        btc_signals = engine.get_latest_signals(symbol="BTCUSDT")
        for s in btc_signals:
            assert s["symbol"] == "BTCUSDT"

    def test_signal_summary(self):
        """get_signal_summary returns consensus / 获取信号摘要返回共识"""
        engine = SignalEngine()
        engine.on_indicators_update("BTCUSDT", "1h", self._make_oversold_indicators())
        summary = engine.get_signal_summary("BTCUSDT")
        assert summary["symbol"] == "BTCUSDT"
        assert "consensus_direction" in summary
        assert "long_count" in summary

    def test_get_latest_for_symbol(self):
        """get_latest_for_symbol returns per-rule signals / 返回每个规则的信号"""
        engine = SignalEngine()
        engine.on_indicators_update("BTCUSDT", "1h", self._make_oversold_indicators())
        latest = engine.get_latest_for_symbol("BTCUSDT")
        assert isinstance(latest, dict)

    def test_stats(self):
        """Stats are tracked / 统计被追踪"""
        engine = SignalEngine()
        engine.on_indicators_update("BTCUSDT", "1h", self._make_oversold_indicators())
        stats = engine.get_stats()
        assert stats["component"] == "signal_engine"
        assert stats["stats"]["total_evaluations"] >= 1

    def test_clear_history(self):
        """clear_history empties all data / clear_history 清空所有数据"""
        engine = SignalEngine()
        engine.on_indicators_update("BTCUSDT", "1h", self._make_oversold_indicators())
        engine.clear_history()
        assert engine.get_latest_signals() == []

    def test_register_custom_rule(self):
        """Custom rules can be registered / 可注册自定义规则"""
        engine = SignalEngine(rules=[])

        class AlwaysLong(SignalRule):
            @property
            def name(self): return "AlwaysLong"
            def evaluate(self, symbol, timeframe, indicators):
                return Signal(symbol=symbol, direction=DIRECTION_LONG, confidence=1.0, source=self.name, timeframe=timeframe)

        engine.register_rule(AlwaysLong())
        signals = engine.on_indicators_update("BTCUSDT", "1h", {})
        assert len(signals) == 1
        assert signals[0].direction == DIRECTION_LONG

    def test_no_signals_for_neutral_data(self):
        """Neutral indicator values → few or no signals / 中性指标值 → 很少或无信号"""
        engine = SignalEngine()
        neutral = {
            "RSI(14)": {"rsi": 50.0},
            "EMA(12)": {"ema": 45000.0},
            "EMA(26)": {"ema": 45000.0},
            "BB(20,2.0)": {"percent_b": 0.5, "bandwidth": 0.03},
            "MACD(12,26,9)": {"macd": 0.0, "signal": 0.0, "histogram": 0.0},
        }
        signals = engine.on_indicators_update("BTCUSDT", "1h", neutral)
        # Should have zero or very few signals / 应该没有或极少信号
        assert len(signals) <= 1
