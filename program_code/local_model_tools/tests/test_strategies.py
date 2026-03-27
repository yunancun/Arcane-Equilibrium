"""
Tests for Trading Strategies / 交易策略测试

覆盖范围：
  - StrategyBase + OrderIntent
  - MACrossoverStrategy
  - BollingerReversionStrategy
  - FundingRateArbStrategy
  - GridTradingStrategy
"""

import time
import pytest

from local_model_tools.strategies.base import (
    StrategyBase, OrderIntent,
    STRATEGY_IDLE, STRATEGY_ACTIVE, STRATEGY_PAUSED, STRATEGY_STOPPED,
)
from local_model_tools.strategies.ma_crossover import MACrossoverStrategy
from local_model_tools.strategies.bollinger_reversion import BollingerReversionStrategy
from local_model_tools.strategies.funding_rate_arb import FundingRateArbStrategy
from local_model_tools.strategies.grid_trading import GridTradingStrategy
from local_model_tools.signal_generator import Signal, DIRECTION_LONG, DIRECTION_SHORT


# =============================================================================
# OrderIntent Tests / OrderIntent 测试
# =============================================================================

class TestOrderIntent:
    """OrderIntent data structure tests"""

    def test_create_basic(self):
        oi = OrderIntent(symbol="BTCUSDT", side="Buy", qty=0.1)
        assert oi.symbol == "BTCUSDT"
        assert oi.side == "Buy"
        assert oi.qty == 0.1
        assert oi.order_type == "market"

    def test_to_dict(self):
        oi = OrderIntent(symbol="ETHUSDT", side="Sell", qty=1.0, price=3000.0,
                         order_type="limit", strategy_name="test")
        d = oi.to_dict()
        assert d["symbol"] == "ETHUSDT"
        assert d["price"] == 3000.0
        assert d["strategy_name"] == "test"

    def test_repr(self):
        oi = OrderIntent(symbol="BTCUSDT", side="Buy", qty=0.1)
        assert "BTCUSDT" in repr(oi)


# =============================================================================
# Strategy Lifecycle Tests / 策略生命周期测试
# =============================================================================

class TestStrategyLifecycle:
    """Strategy state machine tests"""

    def test_initial_state_idle(self):
        """New strategy starts as idle / 新策略初始状态为 idle"""
        s = MACrossoverStrategy()
        assert s.state == STRATEGY_IDLE

    def test_activate(self):
        s = MACrossoverStrategy()
        s.activate()
        assert s.state == STRATEGY_ACTIVE

    def test_pause(self):
        s = MACrossoverStrategy()
        s.activate()
        s.pause()
        assert s.state == STRATEGY_PAUSED

    def test_stop_clears_intents(self):
        s = MACrossoverStrategy()
        s.activate()
        # Generate some intent
        sig = Signal(symbol="BTCUSDT", direction="long", confidence=0.8, source="MA_Cross(EMA(12)/EMA(26))")
        s.on_signal(sig)
        s.stop()
        assert s.state == STRATEGY_STOPPED
        assert s.get_pending_intents() == []

    def test_idle_no_intents(self):
        """Idle strategy doesn't generate intents / idle 策略不产生意图"""
        s = MACrossoverStrategy()
        sig = Signal(symbol="BTCUSDT", direction="long", confidence=0.8, source="MA_Cross(EMA(12)/EMA(26))")
        s.on_signal(sig)
        assert s.get_pending_intents() == []


# =============================================================================
# MA Crossover Strategy Tests / 均线交叉策略测试
# =============================================================================

class TestMACrossoverStrategy:
    """MA Crossover strategy tests"""

    def _make_signal(self, direction: str, confidence: float = 0.8) -> Signal:
        return Signal(
            symbol="BTCUSDT", direction=direction, confidence=confidence,
            source="MA_Cross(EMA(12)/EMA(26))", timeframe="1h",
        )

    def test_long_signal_opens_long(self):
        """Bullish MA cross → open long / 金叉 → 开多"""
        s = MACrossoverStrategy(symbol="BTCUSDT")
        s.activate()
        s.on_signal(self._make_signal("long"))
        intents = s.get_pending_intents()
        assert len(intents) == 1
        assert intents[0].side == "Buy"
        assert "long" in intents[0].reason.lower() or "多" in intents[0].reason

    def test_short_signal_opens_short(self):
        """Bearish MA cross → open short / 死叉 → 开空"""
        s = MACrossoverStrategy(symbol="BTCUSDT")
        s.activate()
        s.on_signal(self._make_signal("short"))
        intents = s.get_pending_intents()
        assert len(intents) == 1
        assert intents[0].side == "Sell"

    def test_reversal_closes_and_opens(self):
        """Long → short reversal generates close + open / 多转空生成平仓+开仓"""
        s = MACrossoverStrategy(symbol="BTCUSDT")
        s.activate()
        s.on_signal(self._make_signal("long"))
        s.get_pending_intents()  # Clear
        s.on_signal(self._make_signal("short"))
        intents = s.get_pending_intents()
        assert len(intents) == 2  # Close long + open short
        assert intents[0].side == "Sell"  # Close long
        assert intents[1].side == "Sell"  # Open short

    def test_duplicate_direction_ignored(self):
        """Same direction signal doesn't double-open / 同方向信号不重复开仓"""
        s = MACrossoverStrategy(symbol="BTCUSDT")
        s.activate()
        s.on_signal(self._make_signal("long"))
        s.get_pending_intents()
        s.on_signal(self._make_signal("long"))  # Same direction
        assert s.get_pending_intents() == []

    def test_low_confidence_ignored(self):
        """Low confidence signal ignored / 低置信度信号被忽略"""
        s = MACrossoverStrategy(symbol="BTCUSDT", min_confidence=0.5)
        s.activate()
        s.on_signal(self._make_signal("long", confidence=0.2))
        assert s.get_pending_intents() == []

    def test_wrong_symbol_ignored(self):
        """Signal for different symbol ignored / 其他交易对的信号被忽略"""
        s = MACrossoverStrategy(symbol="BTCUSDT")
        s.activate()
        sig = Signal(symbol="ETHUSDT", direction="long", confidence=0.8, source="MA_Cross(EMA(12)/EMA(26))")
        s.on_signal(sig)
        assert s.get_pending_intents() == []

    def test_get_status(self):
        s = MACrossoverStrategy(symbol="BTCUSDT")
        status = s.get_status()
        assert status["strategy"] == "MA_Crossover"
        assert status["symbol"] == "BTCUSDT"


# =============================================================================
# Bollinger Reversion Strategy Tests / 布林带均值回归策略测试
# =============================================================================

class TestBollingerReversionStrategy:
    """Bollinger Reversion strategy tests"""

    def _make_bb_signal(self, direction: str, confidence: float = 0.5) -> Signal:
        return Signal(
            symbol="BTCUSDT", direction=direction, confidence=confidence,
            source="BB_Reversion(0.1/0.9)", timeframe="1h",
        )

    def test_long_entry(self):
        """BB oversold signal → open long / BB 超卖信号 → 开多"""
        s = BollingerReversionStrategy(symbol="BTCUSDT")
        s.activate()
        s.on_signal(self._make_bb_signal("long"))
        intents = s.get_pending_intents()
        assert len(intents) == 1
        assert intents[0].side == "Buy"

    def test_short_entry(self):
        """BB overbought signal → open short / BB 超买信号 → 开空"""
        s = BollingerReversionStrategy(symbol="BTCUSDT")
        s.activate()
        s.on_signal(self._make_bb_signal("short"))
        intents = s.get_pending_intents()
        assert len(intents) == 1
        assert intents[0].side == "Sell"

    def test_no_double_entry(self):
        """Already in position → no new entry / 已有持仓 → 不重新开仓"""
        s = BollingerReversionStrategy(symbol="BTCUSDT")
        s.activate()
        s.on_signal(self._make_bb_signal("long"))
        s.get_pending_intents()
        s.on_signal(self._make_bb_signal("long"))  # Already long
        assert s.get_pending_intents() == []

    def test_exit_on_mean_reversion(self):
        """check_exit closes position when %B reverts / 回归均值时平仓"""
        s = BollingerReversionStrategy(symbol="BTCUSDT")
        s.activate()
        s.on_signal(self._make_bb_signal("long"))
        s.get_pending_intents()
        # Simulate %B reverting to 0.5 (middle band)
        s.check_exit(pct_b=0.55)
        intents = s.get_pending_intents()
        assert len(intents) == 1
        assert intents[0].side == "Sell"  # Close long

    def test_no_exit_before_reversion(self):
        """No exit if %B hasn't reverted / %B 未回归则不平仓"""
        s = BollingerReversionStrategy(symbol="BTCUSDT")
        s.activate()
        s.on_signal(self._make_bb_signal("long"))
        s.get_pending_intents()
        s.check_exit(pct_b=0.15)  # Still near lower band
        assert s.get_pending_intents() == []

    def test_get_status(self):
        s = BollingerReversionStrategy()
        assert s.get_status()["strategy"] == "BB_Reversion"


# =============================================================================
# Funding Rate Arb Strategy Tests / Funding Rate 套利策略测试
# =============================================================================

class TestFundingRateArbStrategy:
    """Funding Rate Arbitrage strategy tests"""

    def _next_settle(self, hours: float = 4.0) -> int:
        """Helper: settlement time N hours from now / 辅助：从现在起 N 小时后的结算时间"""
        return int((time.time() + hours * 3600) * 1000)

    def test_high_positive_rate_shorts(self):
        """High positive funding → short / 高正费率 → 做空"""
        s = FundingRateArbStrategy(symbol="BTCUSDT", funding_threshold=0.0001, fee_bps=5)
        s.activate()
        s.evaluate_funding_opportunity(
            funding_rate=0.001,  # 10 bps — well above threshold
            next_settle_ts_ms=self._next_settle(4.0),
        )
        intents = s.get_pending_intents()
        assert len(intents) == 1
        assert intents[0].side == "Sell"

    def test_high_negative_rate_longs(self):
        """High negative funding → long / 高负费率 → 做多"""
        s = FundingRateArbStrategy(symbol="BTCUSDT", funding_threshold=0.0001, fee_bps=5)
        s.activate()
        s.evaluate_funding_opportunity(
            funding_rate=-0.001,
            next_settle_ts_ms=self._next_settle(4.0),
        )
        intents = s.get_pending_intents()
        assert len(intents) == 1
        assert intents[0].side == "Buy"

    def test_small_rate_no_action(self):
        """Small funding rate → no action / 小费率 → 不操作"""
        s = FundingRateArbStrategy(funding_threshold=0.0001)
        s.activate()
        s.evaluate_funding_opportunity(
            funding_rate=0.00005,  # 0.5 bps — below threshold
            next_settle_ts_ms=self._next_settle(4.0),
        )
        assert s.get_pending_intents() == []

    def test_too_close_to_settlement_no_action(self):
        """Too close to settlement → no action / 距结算太近 → 不操作"""
        s = FundingRateArbStrategy(min_hours_to_settle=2.0, fee_bps=5)
        s.activate()
        s.evaluate_funding_opportunity(
            funding_rate=0.001,
            next_settle_ts_ms=self._next_settle(1.0),  # Only 1 hour
        )
        assert s.get_pending_intents() == []

    def test_edge_below_fees_no_action(self):
        """Edge below fees → no action / 边际低于手续费 → 不操作"""
        s = FundingRateArbStrategy(fee_bps=20)  # High fees
        s.activate()
        s.evaluate_funding_opportunity(
            funding_rate=0.0001,  # 1 bps — below 20 bps fees
            next_settle_ts_ms=self._next_settle(4.0),
        )
        assert s.get_pending_intents() == []

    def test_rate_flip_exits(self):
        """Funding rate flip → exit position / 费率反转 → 平仓"""
        s = FundingRateArbStrategy(funding_threshold=0.0001, fee_bps=5)
        s.activate()
        # Enter short (positive rate)
        s.evaluate_funding_opportunity(0.001, self._next_settle(4.0))
        s.get_pending_intents()
        # Rate flips negative → should exit
        s.evaluate_funding_opportunity(-0.001, self._next_settle(4.0))
        intents = s.get_pending_intents()
        assert len(intents) == 1
        assert intents[0].side == "Buy"  # Close short

    def test_record_funding(self):
        """Funding payment tracking / 追踪 funding 支付"""
        s = FundingRateArbStrategy()
        s.record_funding_payment(5.0)
        s.record_funding_payment(3.0)
        assert s.get_status()["funding_collected_usdt"] == 8.0

    def test_get_status(self):
        s = FundingRateArbStrategy()
        assert s.get_status()["strategy"] == "FundingRate_Arb"


# =============================================================================
# Grid Trading Strategy Tests / 网格交易策略测试
# =============================================================================

class TestGridTradingStrategy:
    """Grid Trading strategy tests"""

    def test_invalid_bounds_raises(self):
        """Invalid price bounds raise error / 无效价格边界抛出错误"""
        with pytest.raises(ValueError):
            GridTradingStrategy(upper_price=100, lower_price=200)

    def test_invalid_grid_count_raises(self):
        """Grid count < 2 raises error / 网格数量 < 2 抛出错误"""
        with pytest.raises(ValueError):
            GridTradingStrategy(grid_count=1)

    def test_grid_levels_calculated(self):
        """Grid levels are evenly spaced / 网格价位均匀分布"""
        s = GridTradingStrategy(upper_price=50000, lower_price=40000, grid_count=5)
        assert len(s._grid_levels) == 6  # 5 intervals = 6 levels
        assert s._grid_levels[0] == 40000
        assert s._grid_levels[-1] == 50000
        assert s._grid_step == 2000

    def test_first_tick_no_action(self):
        """First tick just records position / 首个 tick 只记录位置"""
        s = GridTradingStrategy(upper_price=50000, lower_price=40000, grid_count=5)
        s.activate()
        s.on_tick("BTCUSDT", 45000.0, int(time.time() * 1000))
        assert s.get_pending_intents() == []

    def test_upward_crossing_sells(self):
        """Price crossing up → sell / 价格向上穿越 → 卖出"""
        s = GridTradingStrategy(
            symbol="BTCUSDT", upper_price=50000, lower_price=40000, grid_count=5
        )
        s.activate()
        ts = int(time.time() * 1000)
        s.on_tick("BTCUSDT", 42500.0, ts)       # Grid index 1
        s.on_tick("BTCUSDT", 44500.0, ts + 1000)  # Grid index 2 — crossed up!
        intents = s.get_pending_intents()
        assert len(intents) == 1
        assert intents[0].side == "Sell"

    def test_downward_crossing_buys(self):
        """Price crossing down → buy / 价格向下穿越 → 买入"""
        s = GridTradingStrategy(
            symbol="BTCUSDT", upper_price=50000, lower_price=40000, grid_count=5
        )
        s.activate()
        ts = int(time.time() * 1000)
        s.on_tick("BTCUSDT", 44500.0, ts)
        s.on_tick("BTCUSDT", 42500.0, ts + 1000)  # Crossed down
        intents = s.get_pending_intents()
        assert len(intents) == 1
        assert intents[0].side == "Buy"

    def test_multiple_grid_crossings(self):
        """Crossing multiple grids generates multiple intents / 穿越多格生成多个意图"""
        s = GridTradingStrategy(
            symbol="BTCUSDT", upper_price=50000, lower_price=40000, grid_count=5
        )
        s.activate()
        ts = int(time.time() * 1000)
        # Grid step = 2000. 41000 → index round(0.5)=0, 47000 → index round(3.5)=4
        # So 4 grids crossed upward / 穿越 4 格向上
        s.on_tick("BTCUSDT", 41000.0, ts)
        s.on_tick("BTCUSDT", 47000.0, ts + 1000)
        intents = s.get_pending_intents()
        assert len(intents) == 4
        for intent in intents:
            assert intent.side == "Sell"

    def test_same_grid_no_action(self):
        """Price within same grid → no action / 价格在同一格内 → 不操作"""
        s = GridTradingStrategy(
            symbol="BTCUSDT", upper_price=50000, lower_price=40000, grid_count=5
        )
        s.activate()
        ts = int(time.time() * 1000)
        s.on_tick("BTCUSDT", 43000.0, ts)
        s.on_tick("BTCUSDT", 43500.0, ts + 1000)  # Same grid
        assert s.get_pending_intents() == []

    def test_out_of_range_no_action(self):
        """Price outside grid range → no action / 价格超出网格范围 → 不操作"""
        s = GridTradingStrategy(
            symbol="BTCUSDT", upper_price=50000, lower_price=40000, grid_count=5
        )
        s.activate()
        ts = int(time.time() * 1000)
        s.on_tick("BTCUSDT", 35000.0, ts)  # Below range
        s.on_tick("BTCUSDT", 55000.0, ts + 1000)  # Above range
        assert s.get_pending_intents() == []

    def test_wrong_symbol_ignored(self):
        """Ticks for different symbol ignored / 其他交易对的 tick 被忽略"""
        s = GridTradingStrategy(symbol="BTCUSDT")
        s.activate()
        s.on_tick("ETHUSDT", 3000.0, int(time.time() * 1000))
        assert s.get_pending_intents() == []

    def test_paused_no_intents(self):
        """Paused strategy doesn't emit / 暂停状态不产生意图"""
        s = GridTradingStrategy(
            symbol="BTCUSDT", upper_price=50000, lower_price=40000, grid_count=5
        )
        s.activate()
        ts = int(time.time() * 1000)
        s.on_tick("BTCUSDT", 42000.0, ts)
        s.pause()
        s.on_tick("BTCUSDT", 48000.0, ts + 1000)
        assert s.get_pending_intents() == []

    def test_get_status(self):
        s = GridTradingStrategy(upper_price=50000, lower_price=40000, grid_count=10)
        status = s.get_status()
        assert status["strategy"] == "Grid_Trading"
        assert status["grid_count"] == 10
        assert len(status["grid_levels"]) == 11

    def test_limit_orders_have_price(self):
        """Grid orders are limit orders with price / 网格订单是带价格的限价单"""
        s = GridTradingStrategy(
            symbol="BTCUSDT", upper_price=50000, lower_price=40000, grid_count=5
        )
        s.activate()
        ts = int(time.time() * 1000)
        s.on_tick("BTCUSDT", 42500.0, ts)
        s.on_tick("BTCUSDT", 44500.0, ts + 1000)
        intents = s.get_pending_intents()
        assert intents[0].order_type == "limit"
        assert intents[0].price is not None
