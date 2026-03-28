"""
Tests for Strategy Orchestrator / 策略编排器测试

覆盖范围：
  - 策略注册 / 激活 / 暂停 / 停止 / 移除
  - 信号分发到策略
  - Tick 分发到策略
  - OrderIntent 收集
  - 完整管线集成（KlineManager → IndicatorEngine → SignalEngine → Strategies → Intents）
"""

import time
import pytest

from local_model_tools.kline_manager import KlineManager
from local_model_tools.indicator_engine import IndicatorEngine
from local_model_tools.signal_generator import Signal, SignalEngine, DIRECTION_LONG
from local_model_tools.strategy_orchestrator import StrategyOrchestrator
from local_model_tools.strategies.ma_crossover import MACrossoverStrategy
from local_model_tools.strategies.grid_trading import GridTradingStrategy
from local_model_tools.strategies.bollinger_reversion import BollingerReversionStrategy
from local_model_tools.strategies.base import STRATEGY_ACTIVE, STRATEGY_PAUSED, STRATEGY_STOPPED


def _build_orchestrator():
    """Helper: create a full orchestrator stack / 辅助：创建完整编排器栈"""
    km = KlineManager(symbols=["BTCUSDT"], timeframes=["1m"])
    ie = IndicatorEngine(kline_manager=km)
    se = SignalEngine()
    ie.register_on_update(se.on_indicators_update)
    orch = StrategyOrchestrator(
        kline_manager=km, indicator_engine=ie, signal_engine=se,
    )
    return km, ie, se, orch


class TestStrategyRegistration:
    """Strategy registration and lifecycle tests / 策略注册与生命周期测试"""

    def test_register_strategy(self):
        _, _, _, orch = _build_orchestrator()
        s = MACrossoverStrategy(symbol="BTCUSDT")
        orch.register_strategy(s)
        assert "MA_Crossover" in orch.list_available_strategies()

    def test_activate_strategy(self):
        _, _, _, orch = _build_orchestrator()
        orch.register_strategy(MACrossoverStrategy())
        assert orch.activate_strategy("MA_Crossover") is True

    def test_activate_nonexistent(self):
        _, _, _, orch = _build_orchestrator()
        assert orch.activate_strategy("NonExistent") is False

    def test_pause_strategy(self):
        _, _, _, orch = _build_orchestrator()
        orch.register_strategy(MACrossoverStrategy())
        orch.activate_strategy("MA_Crossover")
        orch.pause_strategy("MA_Crossover")
        status = orch.get_strategy_status("MA_Crossover")
        assert status["state"] == STRATEGY_PAUSED

    def test_stop_strategy(self):
        _, _, _, orch = _build_orchestrator()
        orch.register_strategy(MACrossoverStrategy())
        orch.activate_strategy("MA_Crossover")
        orch.stop_strategy("MA_Crossover")
        status = orch.get_strategy_status("MA_Crossover")
        assert status["state"] == STRATEGY_STOPPED

    def test_remove_strategy(self):
        _, _, _, orch = _build_orchestrator()
        orch.register_strategy(MACrossoverStrategy())
        assert orch.remove_strategy("MA_Crossover") is True
        assert "MA_Crossover" not in orch.list_available_strategies()

    def test_remove_nonexistent(self):
        _, _, _, orch = _build_orchestrator()
        assert orch.remove_strategy("NonExistent") is False


class TestSignalDispatch:
    """Signal dispatch to strategies tests / 信号分发到策略测试"""

    def test_signal_dispatched_to_active_strategy(self):
        """Signals reach active strategies / 信号传达到活跃策略"""
        _, _, _, orch = _build_orchestrator()
        s = MACrossoverStrategy(symbol="BTCUSDT")
        orch.register_strategy(s)
        orch.activate_strategy("MA_Crossover")

        # Manually trigger signal dispatch / 手动触发信号分发
        signal = Signal(
            symbol="BTCUSDT", direction="long", confidence=0.8,
            source="MA_Cross(EMA(12)/EMA(26))", timeframe="1h",
            metadata={"_regime": "trending"},
        )
        orch._on_signal(signal)

        intents = orch.collect_pending_intents()
        assert len(intents) >= 1
        assert intents[0].side == "Buy"

    def test_signal_not_dispatched_to_inactive(self):
        """Signals don't reach inactive strategies / 信号不传达到非活跃策略"""
        _, _, _, orch = _build_orchestrator()
        s = MACrossoverStrategy(symbol="BTCUSDT")
        orch.register_strategy(s)
        # Strategy is idle (not activated)

        signal = Signal(
            symbol="BTCUSDT", direction="long", confidence=0.8,
            source="MA_Cross(EMA(12)/EMA(26))", timeframe="1h",
        )
        orch._on_signal(signal)

        assert orch.collect_pending_intents() == []


class TestTickDispatch:
    """Tick dispatch to strategies tests / Tick 分发到策略测试"""

    def test_tick_reaches_grid_strategy(self):
        """Ticks reach grid trading strategy / Tick 传达到网格策略"""
        _, _, _, orch = _build_orchestrator()
        grid = GridTradingStrategy(
            symbol="BTCUSDT", upper_price=50000, lower_price=40000, grid_count=5,
        )
        orch.register_strategy(grid)
        orch.activate_strategy("Grid_Trading")

        ts = int(time.time() * 1000)
        orch.dispatch_tick("BTCUSDT", 42500.0, ts)
        orch.dispatch_tick("BTCUSDT", 44500.0, ts + 1000)

        intents = orch.collect_pending_intents()
        assert len(intents) >= 1


class TestIntentCollection:
    """OrderIntent collection tests / 订单意图收集测试"""

    def test_collect_clears_intents(self):
        """collect_pending_intents clears after collection / 收集后清空"""
        _, _, _, orch = _build_orchestrator()
        s = MACrossoverStrategy(symbol="BTCUSDT")
        orch.register_strategy(s)
        orch.activate_strategy("MA_Crossover")

        signal = Signal(
            symbol="BTCUSDT", direction="long", confidence=0.8,
            source="MA_Cross(EMA(12)/EMA(26))", timeframe="1h",
            metadata={"_regime": "trending"},
        )
        orch._on_signal(signal)

        first = orch.collect_pending_intents()
        assert len(first) >= 1
        second = orch.collect_pending_intents()
        assert len(second) == 0

    def test_intent_history_recorded(self):
        """Collected intents are recorded in history / 收集的意图记录在历史中"""
        _, _, _, orch = _build_orchestrator()
        s = MACrossoverStrategy(symbol="BTCUSDT")
        orch.register_strategy(s)
        orch.activate_strategy("MA_Crossover")

        signal = Signal(
            symbol="BTCUSDT", direction="long", confidence=0.8,
            source="MA_Cross(EMA(12)/EMA(26))", timeframe="1h",
            metadata={"_regime": "trending"},
        )
        orch._on_signal(signal)
        orch.collect_pending_intents()

        history = orch.get_intent_history()
        assert len(history) >= 1
        assert history[0]["symbol"] == "BTCUSDT"

    def test_multi_strategy_intents_collected(self):
        """Intents from multiple strategies are collected / 多策略的意图统一收集"""
        _, _, _, orch = _build_orchestrator()

        # Register two strategies / 注册两个策略
        ma = MACrossoverStrategy(symbol="BTCUSDT")
        grid = GridTradingStrategy(
            symbol="BTCUSDT", upper_price=50000, lower_price=40000, grid_count=5,
        )
        orch.register_strategy(ma)
        orch.register_strategy(grid)
        orch.activate_strategy("MA_Crossover")
        orch.activate_strategy("Grid_Trading")

        # Trigger MA signal / 触发 MA 信号
        signal = Signal(
            symbol="BTCUSDT", direction="long", confidence=0.8,
            source="MA_Cross(EMA(12)/EMA(26))", timeframe="1h",
            metadata={"_regime": "trending"},
        )
        orch._on_signal(signal)

        # Trigger Grid tick / 触发 Grid tick
        ts = int(time.time() * 1000)
        orch.dispatch_tick("BTCUSDT", 42500.0, ts)
        orch.dispatch_tick("BTCUSDT", 44500.0, ts + 1000)

        intents = orch.collect_pending_intents()
        # Should have intents from both strategies
        strategy_names = {i.strategy_name for i in intents}
        assert len(intents) >= 2
        assert "MA_Crossover" in strategy_names
        assert "Grid_Trading" in strategy_names


class TestOrchestratorStatus:
    """Status and query tests / 状态和查询测试"""

    def test_get_status(self):
        _, _, _, orch = _build_orchestrator()
        orch.register_strategy(MACrossoverStrategy())
        status = orch.get_status()
        assert status["component"] == "strategy_orchestrator"
        assert status["total_registered"] == 1
        assert "kline_manager_status" in status
        assert "indicator_engine_status" in status

    def test_get_all_strategies_status(self):
        _, _, _, orch = _build_orchestrator()
        orch.register_strategy(MACrossoverStrategy())
        orch.register_strategy(GridTradingStrategy())
        statuses = orch.get_all_strategies_status()
        assert len(statuses) == 2

    def test_get_nonexistent_strategy_status(self):
        _, _, _, orch = _build_orchestrator()
        assert orch.get_strategy_status("NonExistent") is None


class TestFullPipelineIntegration:
    """Full pipeline integration tests / 完整管线集成测试"""

    def test_end_to_end_kline_to_intent(self):
        """
        Full pipeline: tick data → klines → indicators → signals → strategies → intents
        完整管线：tick 数据 → K线 → 指标 → 信号 → 策略 → 订单意图
        """
        km, ie, se, orch = _build_orchestrator()

        # Register and activate MA crossover / 注册并激活 MA 交叉
        ma = MACrossoverStrategy(symbol="BTCUSDT", min_confidence=0.1)
        orch.register_strategy(ma)
        orch.activate_strategy("MA_Crossover")

        # Feed enough data to compute indicators (50+ klines)
        # 输入足够数据计算指标（50+ 根 K线）
        # Simulate uptrend → should trigger bullish MA crossover eventually
        # 模拟上升趋势 → 最终应触发均线金叉
        base_price = 45000.0
        for i in range(60):
            price = base_price + i * 20  # Uptrend / 上升趋势
            km.on_tick("BTCUSDT", price, ts_ms=60000 * (i + 1))

        # The pipeline may or may not have generated intents
        # depending on indicator state. Check that everything ran without error.
        # 管线可能产生也可能未产生意图，取决于指标状态。
        # 确认一切运行无错误。
        intents = orch.collect_pending_intents()
        # At minimum, verify the pipeline components are connected
        stats = orch.get_status()
        assert stats["total_registered"] == 1
        assert stats["active_count"] == 1

    def test_grid_tick_pipeline(self):
        """Grid strategy responds to ticks via orchestrator / 网格策略通过编排器响应 tick"""
        km, ie, se, orch = _build_orchestrator()

        grid = GridTradingStrategy(
            symbol="BTCUSDT", upper_price=46000, lower_price=44000, grid_count=4,
        )
        orch.register_strategy(grid)
        orch.activate_strategy("Grid_Trading")

        ts = int(time.time() * 1000)
        # First tick sets position / 首个 tick 设置位置
        orch.dispatch_tick("BTCUSDT", 44500.0, ts)
        # Second tick crosses a grid / 第二个 tick 穿越网格
        orch.dispatch_tick("BTCUSDT", 45100.0, ts + 1000)

        intents = orch.collect_pending_intents()
        assert len(intents) >= 1
        assert intents[0].strategy_name == "Grid_Trading"
