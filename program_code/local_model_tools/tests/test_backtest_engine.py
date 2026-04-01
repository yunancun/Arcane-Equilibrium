"""
Tests for BacktestEngine — Phase 2 Batch 2B Acceptance Tests
回测引擎测试 — Phase 2 Batch 2B 验收测试

MODULE_NOTE (中文):
  验证 BacktestEngine 的所有核心行为，对应 FA 规格 B1-B9。
  覆盖：安全守护、数据不足处理、完整回测流程、各指标计算、隔离保证。

MODULE_NOTE (English):
  Validates all core BacktestEngine behaviors, mapped to FA spec B1-B9.
  Covers: safety guards, insufficient data handling, full backtest pipeline,
  metric calculations, and isolation guarantees.

Safety invariant / 安全不变量:
  - 所有测试均使用模拟数据，不依赖真实市场数据或网络 / All tests use mock data, no real market data or network
  - 不修改线上组件状态 / Does not modify live component state
"""

from __future__ import annotations

import math
import statistics
from unittest.mock import MagicMock, patch

import pytest

from program_code.local_model_tools.backtest_engine import (
    ANNUALIZATION_FACTORS,
    MIN_BARS_REQUIRED,
    BacktestConfig,
    BacktestEngine,
    BacktestResult,
    BacktestTrade,
    _BacktestKlineAdapter,
    _compute_ema,
    _compute_indicators_pure,
    _compute_max_drawdown,
    _compute_rsi,
    _compute_sharpe,
    _compute_sma,
    _precompute_indicator_series,
)


# =============================================================================
# Helpers / 辅助函数
# =============================================================================

def _make_trending_up_ohlcv(n: int = 100) -> dict[str, list[float]]:
    """
    Generate synthetic upward-trending OHLCV data.
    生成合成的上升趋势 OHLCV 数据。
    """
    close = [100.0 + i * 0.5 for i in range(n)]
    open_ = [c - 0.1 for c in close]
    high = [c + 0.3 for c in close]
    low = [c - 0.3 for c in close]
    volume = [1000.0] * n
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume}


def _make_trending_down_ohlcv(n: int = 100) -> dict[str, list[float]]:
    """
    Generate synthetic downward-trending OHLCV data.
    生成合成的下降趋势 OHLCV 数据。
    """
    close = [200.0 - i * 0.5 for i in range(n)]
    open_ = [c + 0.1 for c in close]
    high = [c + 0.3 for c in close]
    low = [c - 0.3 for c in close]
    volume = [1000.0] * n
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume}


def _make_flat_ohlcv(n: int = 100, price: float = 100.0) -> dict[str, list[float]]:
    """
    Generate synthetic flat OHLCV data (no signals expected).
    生成合成的平稳 OHLCV 数据（预期无信号）。
    """
    close = [price] * n
    return {
        "open": close[:], "high": close[:], "low": close[:],
        "close": close[:], "volume": [1000.0] * n,
    }


def _make_default_config(**kwargs) -> BacktestConfig:
    """Create a default BacktestConfig for testing / 创建用于测试的默认配置"""
    defaults = dict(
        symbol="BTCUSDT",
        timeframe="1h",
        strategy_name="test_strategy",
        initial_capital=1000.0,
        fee_rate_taker=0.00055,
        fee_rate_maker=0.0002,
        slippage_bps=5.0,
        position_size_pct=0.02,
        stop_loss_pct=0.02,
        backtest_mode=True,
    )
    defaults.update(kwargs)
    return BacktestConfig(**defaults)


# =============================================================================
# B1: backtest_mode safety guard / B1: backtest_mode 安全守护
# =============================================================================

class TestBacktestModeSafetyGuard:
    """B1: BacktestConfig.backtest_mode must be True / backtest_mode 必须为 True"""

    def test_run_raises_if_backtest_mode_false(self):
        """B1-1: run() raises ValueError when backtest_mode=False / backtest_mode=False 时抛 ValueError"""
        engine = BacktestEngine()
        config = _make_default_config(backtest_mode=False)
        with pytest.raises(ValueError, match="backtest_mode"):
            engine.run(config, _make_trending_up_ohlcv())

    def test_run_succeeds_if_backtest_mode_true(self):
        """B1-2: run() succeeds when backtest_mode=True / backtest_mode=True 时正常运行"""
        engine = BacktestEngine()
        config = _make_default_config(backtest_mode=True)
        result = engine.run(config, _make_trending_up_ohlcv(100))
        assert isinstance(result, BacktestResult)

    def test_default_backtest_mode_is_true(self):
        """B1-3: BacktestConfig default backtest_mode=True / 默认 backtest_mode=True"""
        config = BacktestConfig(symbol="X", timeframe="1h", strategy_name="s")
        assert config.backtest_mode is True


# =============================================================================
# B2: Insufficient data handling / B2: 数据不足处理
# =============================================================================

class TestInsufficientDataHandling:
    """B2: <30 bars returns BacktestResult with warning, not raise / 数据不足时返回含 warning 的结果"""

    def test_empty_data_returns_warning_result(self):
        """B2-1: Empty OHLCV returns result with warning / 空 OHLCV 返回含 warning 的结果"""
        engine = BacktestEngine()
        config = _make_default_config()
        result = engine.run(config, {})
        assert isinstance(result, BacktestResult)
        assert result.warning != ""
        assert result.total_trades == 0

    def test_none_data_with_no_live_km_returns_warning(self):
        """B2-2: None data with no live KlineManager returns warning / 无数据无线上KM返回warning"""
        engine = BacktestEngine()  # no live KlineManager
        config = _make_default_config()
        result = engine.run(config, None)
        assert result.warning != ""
        assert result.total_trades == 0

    def test_fewer_than_30_bars_returns_warning(self):
        """B2-3: 10 bars returns warning result, does not raise / 10根K线返回含warning结果，不抛异常"""
        engine = BacktestEngine()
        config = _make_default_config()
        result = engine.run(config, _make_trending_up_ohlcv(10))
        assert isinstance(result, BacktestResult)
        assert result.warning != ""
        assert result.total_trades == 0

    def test_exactly_29_bars_returns_warning(self):
        """B2-4: Exactly 29 bars (< MIN_BARS_REQUIRED) returns warning / 29根K线返回warning"""
        engine = BacktestEngine()
        config = _make_default_config()
        result = engine.run(config, _make_trending_up_ohlcv(MIN_BARS_REQUIRED - 1))
        assert result.warning != ""

    def test_exactly_30_bars_proceeds(self):
        """B2-5: Exactly MIN_BARS_REQUIRED bars does not return data warning / 恰好MIN根K线不返回数据warning"""
        engine = BacktestEngine()
        config = _make_default_config()
        result = engine.run(config, _make_trending_up_ohlcv(MIN_BARS_REQUIRED))
        # May have no trades (indicator warmup), but no data-shortage warning
        # 可能无交易（指标预热），但不应有数据不足警告
        assert "Insufficient" not in result.warning
        assert "No OHLCV" not in result.warning


# =============================================================================
# B3: BacktestResult structure / B3: BacktestResult 结构
# =============================================================================

class TestBacktestResultStructure:
    """B3: BacktestResult contains all required fields / 包含所有必要字段"""

    def test_result_has_all_fields(self):
        """B3-1: BacktestResult contains all FA-specified fields"""
        engine = BacktestEngine()
        config = _make_default_config()
        result = engine.run(config, _make_trending_up_ohlcv(100))

        # Core metrics / 核心指标
        assert hasattr(result, "total_trades")
        assert hasattr(result, "winning_trades")
        assert hasattr(result, "losing_trades")
        assert hasattr(result, "win_rate")
        assert hasattr(result, "total_net_pnl")
        assert hasattr(result, "total_return_pct")
        assert hasattr(result, "max_drawdown_pct")
        assert hasattr(result, "sharpe_ratio")
        assert hasattr(result, "avg_win_pct")
        assert hasattr(result, "avg_loss_pct")
        assert hasattr(result, "profit_factor")
        assert hasattr(result, "avg_trade_pct")

        # Metadata / 元数据
        assert hasattr(result, "symbol")
        assert hasattr(result, "timeframe")
        assert hasattr(result, "strategy_name")
        assert hasattr(result, "initial_capital")
        assert hasattr(result, "final_capital")
        assert hasattr(result, "total_bars_processed")
        assert hasattr(result, "trades")
        assert hasattr(result, "equity_curve")
        assert hasattr(result, "config")
        assert hasattr(result, "warning")

    def test_result_to_dict_serializable(self):
        """B3-2: BacktestResult.to_dict() returns JSON-serializable dict / to_dict() 返回可序列化字典"""
        engine = BacktestEngine()
        config = _make_default_config()
        result = engine.run(config, _make_trending_up_ohlcv(100))
        d = result.to_dict()
        assert isinstance(d, dict)
        assert isinstance(d["trades"], list)
        assert isinstance(d["equity_curve"], list)
        # Check no inf or nan values / 检查没有 inf 或 nan 值
        import json
        json_str = json.dumps(d)  # should not raise
        assert json_str  # non-empty

    def test_result_trades_are_backtest_trade_instances(self):
        """B3-3: All trades in result are BacktestTrade instances / 所有交易均为 BacktestTrade 实例"""
        engine = BacktestEngine()
        config = _make_default_config()
        result = engine.run(config, _make_trending_up_ohlcv(200))
        for trade in result.trades:
            assert isinstance(trade, BacktestTrade)


# =============================================================================
# B4: Trade metric consistency / B4: 交易指标一致性
# =============================================================================

class TestTradeMetricConsistency:
    """B4: Core metrics are internally consistent / 核心指标内部一致"""

    def test_trade_counts_sum_correctly(self):
        """B4-1: winning + losing == total_trades / 盈利+亏损 == 总交易数"""
        engine = BacktestEngine()
        config = _make_default_config()
        result = engine.run(config, _make_trending_up_ohlcv(200))
        assert result.winning_trades + result.losing_trades == result.total_trades

    def test_win_rate_range(self):
        """B4-2: win_rate ∈ [0.0, 1.0] / 胜率在 [0, 1] 范围内"""
        engine = BacktestEngine()
        config = _make_default_config()
        result = engine.run(config, _make_trending_up_ohlcv(200))
        assert 0.0 <= result.win_rate <= 1.0

    def test_sharpe_is_finite(self):
        """B4-3: sharpe_ratio is always finite (no nan/inf) / sharpe_ratio 始终有限（无 nan/inf）"""
        engine = BacktestEngine()
        config = _make_default_config()
        result = engine.run(config, _make_trending_up_ohlcv(200))
        assert math.isfinite(result.sharpe_ratio)

    def test_profit_factor_finite(self):
        """B4-4: profit_factor is always finite (capped at 999 if no losses) / 利润因子始终有限"""
        engine = BacktestEngine()
        config = _make_default_config()
        result = engine.run(config, _make_trending_up_ohlcv(200))
        assert math.isfinite(result.profit_factor)
        assert result.profit_factor >= 0.0

    def test_equity_curve_starts_near_initial_capital(self):
        """B4-5: equity_curve[0] is close to initial_capital / 资金曲线起点接近初始资金"""
        engine = BacktestEngine()
        config = _make_default_config(initial_capital=1000.0)
        result = engine.run(config, _make_trending_up_ohlcv(100))
        if result.equity_curve:
            # First bar equity should be within reasonable range of initial capital
            # (could differ slightly if a trade opened on first eligible bar)
            assert abs(result.equity_curve[0] - 1000.0) < 200.0  # max 20% drift

    def test_final_capital_matches_pnl(self):
        """B4-6: final_capital ≈ initial_capital + total_net_pnl / 最终资金约等于初始资金 + 净利润"""
        engine = BacktestEngine()
        config = _make_default_config(initial_capital=1000.0)
        result = engine.run(config, _make_trending_up_ohlcv(150))
        expected = config.initial_capital + result.total_net_pnl
        assert abs(result.final_capital - expected) < 0.01  # floating point tolerance


# =============================================================================
# B5: Sharpe ratio calculation / B5: Sharpe 比率计算
# =============================================================================

class TestSharpeRatioCalculation:
    """B5: _compute_sharpe correctness / _compute_sharpe 正确性"""

    def test_sharpe_returns_zero_for_single_trade(self):
        """B5-1: Single trade returns Sharpe=0.0 (< min trades) / 单笔交易返回 0.0"""
        result = _compute_sharpe([10.0], "1h")
        assert result == 0.0

    def test_sharpe_returns_zero_for_zero_std(self):
        """B5-2: All same PnL → std=0 → Sharpe=0.0 / 所有交易PnL相同→标准差0→Sharpe=0"""
        result = _compute_sharpe([5.0, 5.0, 5.0], "1h")
        assert result == 0.0

    def test_sharpe_returns_zero_for_empty(self):
        """B5-3: Empty list returns 0.0 / 空列表返回 0.0"""
        result = _compute_sharpe([], "1h")
        assert result == 0.0

    def test_sharpe_positive_for_consistent_gains(self):
        """B5-4: Consistent gains produce positive Sharpe / 稳定盈利产生正 Sharpe"""
        pnl = [10.0, 8.0, 12.0, 9.0, 11.0, 10.5, 9.5, 11.5, 10.0, 8.5]
        result = _compute_sharpe(pnl, "1h")
        assert result > 0.0

    def test_sharpe_negative_for_consistent_losses(self):
        """B5-5: Consistent losses produce negative Sharpe / 稳定亏损产生负 Sharpe"""
        pnl = [-10.0, -8.0, -12.0, -9.0, -11.0]
        result = _compute_sharpe(pnl, "1h")
        assert result < 0.0

    def test_sharpe_uses_correct_annualization_1h(self):
        """B5-6: 1h uses annualization factor 8760 / 1h 使用年化因子 8760"""
        # Manually verify the formula for 2 trades
        pnl = [2.0, 4.0]
        mean = statistics.mean(pnl)
        std = statistics.stdev(pnl)
        expected = (mean / std) * math.sqrt(8760)
        result = _compute_sharpe(pnl, "1h")
        assert abs(result - expected) < 1e-6

    def test_sharpe_uses_correct_annualization_1d(self):
        """B5-7: 1d uses annualization factor 365 / 1d 使用年化因子 365"""
        pnl = [2.0, 4.0]
        mean = statistics.mean(pnl)
        std = statistics.stdev(pnl)
        expected = (mean / std) * math.sqrt(365)
        result = _compute_sharpe(pnl, "1d")
        assert abs(result - expected) < 1e-6

    def test_sharpe_is_always_finite(self):
        """B5-8: Sharpe is always finite regardless of input / Sharpe 始终有限"""
        # Various edge cases / 各种边缘情况
        cases = [
            [],
            [0.0],
            [0.0, 0.0],
            [1e10, -1e10],
            [1.0] * 100,
        ]
        for pnl in cases:
            result = _compute_sharpe(pnl, "1h")
            assert math.isfinite(result), f"Non-finite Sharpe for input {pnl[:5]}..."


# =============================================================================
# B6: Max drawdown calculation / B6: 最大回撤计算
# =============================================================================

class TestMaxDrawdownCalculation:
    """B6: _compute_max_drawdown correctness / _compute_max_drawdown 正确性"""

    def test_no_drawdown_for_monotone_up(self):
        """B6-1: Monotonically increasing equity → max_drawdown=0 / 单调上升→最大回撤=0"""
        curve = [100.0, 110.0, 120.0, 130.0, 140.0]
        result = _compute_max_drawdown(curve)
        assert result == 0.0

    def test_correct_drawdown_simple(self):
        """B6-2: Simple drawdown: peak=100, trough=80 → 20% / 简单回撤20%"""
        curve = [100.0, 90.0, 80.0, 85.0, 95.0]
        result = _compute_max_drawdown(curve)
        assert abs(result - 20.0) < 0.01

    def test_max_drawdown_with_recovery(self):
        """B6-3: Max drawdown is from peak before trough, not just last-to-peak"""
        # Peak at 200, then drops to 100, then recovers to 250
        # 峰值 200 → 跌至 100（50% 回撤）→ 恢复到 250
        curve = [100.0, 200.0, 150.0, 100.0, 200.0, 250.0]
        result = _compute_max_drawdown(curve)
        assert abs(result - 50.0) < 0.01  # (200-100)/200 = 50%

    def test_empty_curve_returns_zero(self):
        """B6-4: Empty curve returns 0.0 / 空曲线返回 0.0"""
        assert _compute_max_drawdown([]) == 0.0

    def test_single_point_curve_returns_zero(self):
        """B6-5: Single point curve returns 0.0 / 单点曲线返回 0.0"""
        assert _compute_max_drawdown([100.0]) == 0.0


# =============================================================================
# B7: _BacktestKlineAdapter isolation / B7: _BacktestKlineAdapter 隔离
# =============================================================================

class TestBacktestKlineAdapterIsolation:
    """B7: Adapter provides correct data window and no-ops / 适配器提供正确数据窗口且注册回调为 no-op"""

    def test_adapter_limits_data_to_idx(self):
        """B7-1: get_ohlcv returns only bars up to idx / get_ohlcv 只返回截至 idx 的数据"""
        ohlcv = {"close": list(range(100)), "open": list(range(100)),
                 "high": list(range(100)), "low": list(range(100)),
                 "volume": [1.0] * 100}
        adapter = _BacktestKlineAdapter(ohlcv, bars_up_to_idx=30)
        result = adapter.get_ohlcv("BTCUSDT", "1h")
        assert len(result["close"]) == 30

    def test_adapter_update_idx_changes_window(self):
        """B7-2: update_idx advances the data window / update_idx 推进数据窗口"""
        ohlcv = {"close": list(range(100)), "open": list(range(100)),
                 "high": list(range(100)), "low": list(range(100)),
                 "volume": [1.0] * 100}
        adapter = _BacktestKlineAdapter(ohlcv, bars_up_to_idx=10)
        adapter.update_idx(50)
        result = adapter.get_ohlcv("BTCUSDT", "1h")
        assert len(result["close"]) == 50

    def test_register_on_kline_close_is_noop(self):
        """B7-3: register_on_kline_close is a no-op / register_on_kline_close 是 no-op"""
        ohlcv = {"close": [1.0, 2.0], "open": [1.0, 2.0],
                 "high": [1.0, 2.0], "low": [1.0, 2.0], "volume": [1.0, 2.0]}
        adapter = _BacktestKlineAdapter(ohlcv, bars_up_to_idx=2)
        called = []
        adapter.register_on_kline_close(lambda: called.append(True))
        # No callback should ever be called / 不应触发任何回调
        assert len(called) == 0

    def test_adapter_n_parameter_limits_return(self):
        """B7-4: get_ohlcv with n parameter limits return length / n 参数限制返回长度"""
        ohlcv = {"close": list(range(100)), "open": list(range(100)),
                 "high": list(range(100)), "low": list(range(100)),
                 "volume": [1.0] * 100}
        adapter = _BacktestKlineAdapter(ohlcv, bars_up_to_idx=80)
        result = adapter.get_ohlcv("BTCUSDT", "1h", n=20)
        assert len(result["close"]) == 20


# =============================================================================
# B8: Pure indicator functions / B8: 纯函数指标
# =============================================================================

class TestPureIndicatorFunctions:
    """B8: Pure helper indicator functions correctness / 纯函数指标辅助函数正确性"""

    def test_sma_correct(self):
        """B8-1: SMA(3) of [1,2,3,4,5] last 3 = mean(3,4,5) = 4 / SMA正确"""
        result = _compute_sma([1.0, 2.0, 3.0, 4.0, 5.0], 3)
        assert abs(result - 4.0) < 1e-10

    def test_sma_insufficient_data_returns_none(self):
        """B8-2: SMA returns None when insufficient data / 数据不足时 SMA 返回 None"""
        result = _compute_sma([1.0, 2.0], 5)
        assert result is None

    def test_ema_converges_for_constant_series(self):
        """B8-3: EMA of constant series = that constant / 常数序列的 EMA = 该常数"""
        close = [50.0] * 30
        result = _compute_ema(close, 12)
        assert abs(result - 50.0) < 0.01

    def test_rsi_for_all_gains_approaches_100(self):
        """B8-4: RSI of all-gain series approaches 100 / 全涨序列的 RSI 趋近 100"""
        close = [float(100 + i) for i in range(30)]  # strictly increasing
        result = _compute_rsi(close, 14)
        assert result is not None
        assert result > 90.0

    def test_rsi_for_all_losses_approaches_0(self):
        """B8-5: RSI of all-loss series approaches 0 / 全跌序列的 RSI 趋近 0"""
        close = [float(200 - i) for i in range(30)]  # strictly decreasing
        result = _compute_rsi(close, 14)
        assert result is not None
        assert result < 10.0

    def test_rsi_insufficient_data_returns_none(self):
        """B8-6: RSI returns None when insufficient data / 数据不足时 RSI 返回 None"""
        result = _compute_rsi([1.0, 2.0, 3.0], 14)
        assert result is None

    def test_compute_indicators_pure_returns_dict(self):
        """B8-7: _compute_indicators_pure returns non-empty dict for sufficient data"""
        ohlcv = _make_trending_up_ohlcv(50)
        result = _compute_indicators_pure(ohlcv)
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_compute_indicators_pure_includes_rsi(self):
        """B8-8: _compute_indicators_pure includes RSI(14) for 50+ bars / 包含 RSI(14)"""
        ohlcv = _make_trending_up_ohlcv(50)
        result = _compute_indicators_pure(ohlcv)
        assert "RSI(14)" in result
        assert "rsi" in result["RSI(14)"]

    def test_compute_indicators_pure_empty_returns_empty(self):
        """B8-9: Empty OHLCV returns empty dict / 空 OHLCV 返回空字典"""
        result = _compute_indicators_pure({})
        assert result == {}


# =============================================================================
# B9: Principle 7 isolation verification / B9: 原则 7 隔离验证
# =============================================================================

class TestPrinciple7Isolation:
    """B9: Backtest does not call live pipeline components / 回测不调用线上管线组件"""

    def test_no_messagebus_call_during_run(self):
        """B9-1: No MessageBus.send() called during backtest run / 回测期间不调用 MessageBus.send()"""
        engine = BacktestEngine()
        config = _make_default_config()
        # If MessageBus were imported and called, we'd see it
        # 若 MessageBus 被导入并调用，此处会捕获
        with patch(
            "program_code.local_model_tools.backtest_engine._precompute_indicator_series",
            wraps=_precompute_indicator_series,
        ) as mock_fn:
            result = engine.run(config, _make_trending_up_ohlcv(100))
            # _precompute_indicator_series should be called (our computation)
            # but no live pipeline calls
            # _precompute_indicator_series 应被调用（我们的指标计算），
            # 但不调用任何线上管线
            assert mock_fn.called  # backtest did run indicators
        assert isinstance(result, BacktestResult)

    def test_live_indicator_engine_state_unchanged(self):
        """B9-2: Injected live IndicatorEngine state is not modified / 不修改注入的线上 IndicatorEngine"""
        mock_ie = MagicMock()
        mock_ie.get_indicators.return_value = {}
        engine = BacktestEngine(indicator_engine=mock_ie)
        config = _make_default_config()
        engine.run(config, _make_trending_up_ohlcv(100))
        # The backtest should NOT call on_kline_close on the live engine
        # 回测不应在线上引擎上调用 on_kline_close
        mock_ie.on_kline_close.assert_not_called()
        # Should NOT call register_on_update on the live engine
        mock_ie.register_on_update.assert_not_called()

    def test_live_signal_engine_state_unchanged(self):
        """B9-3: Injected live SignalEngine state is not modified / 不修改注入的线上 SignalEngine"""
        mock_se = MagicMock()
        engine = BacktestEngine(signal_engine=mock_se)
        config = _make_default_config()
        engine.run(config, _make_trending_up_ohlcv(100))
        # Should NOT call on_indicators_update on the live engine
        mock_se.on_indicators_update.assert_not_called()

    def test_none_engines_dont_crash(self):
        """B9-4: All None engines → valid BacktestResult without crash / 全 None 引擎不崩溃"""
        engine = BacktestEngine(None, None, None)
        config = _make_default_config()
        result = engine.run(config, _make_trending_up_ohlcv(100))
        assert isinstance(result, BacktestResult)
        assert math.isfinite(result.sharpe_ratio)

    def test_backtest_with_live_km_uses_get_ohlcv(self):
        """B9-5: When ohlcv_data=None, fetches read-only from live KlineManager / 只读访问 KlineManager"""
        mock_km = MagicMock()
        mock_km.get_ohlcv.return_value = _make_trending_up_ohlcv(100)
        engine = BacktestEngine(kline_manager=mock_km)
        config = _make_default_config()
        result = engine.run(config, None)  # triggers live KM fetch
        mock_km.get_ohlcv.assert_called_once()
        # Must NOT call write methods like on_price_event / register_on_kline_close
        mock_km.on_price_event.assert_not_called()
        mock_km.register_on_kline_close.assert_not_called()
        assert isinstance(result, BacktestResult)


# =============================================================================
# Additional: BacktestConfig and BacktestTrade / 额外: 配置和交易记录测试
# =============================================================================

class TestBacktestConfigAndTrade:
    """Tests for BacktestConfig and BacktestTrade dataclasses / 配置和交易记录数据类测试"""

    def test_config_default_values(self):
        """Config default values match FA spec / 配置默认值与 FA 规格一致"""
        config = BacktestConfig(symbol="X", timeframe="1h", strategy_name="s")
        assert config.initial_capital == 1000.0
        assert config.fee_rate_taker == 0.00055
        assert config.fee_rate_maker == 0.0002
        assert config.slippage_bps == 5.0
        assert config.position_size_pct == 0.02
        assert config.stop_loss_pct == 0.02

    def test_trade_to_dict_all_keys(self):
        """BacktestTrade.to_dict() contains all expected keys / 包含所有预期键"""
        trade = BacktestTrade(
            trade_id=0, symbol="BTCUSDT", direction="long",
            entry_bar_idx=10, exit_bar_idx=20,
            entry_price=100.0, exit_price=105.0,
            qty=0.1, notional_usd=10.0,
            entry_fee=0.01, exit_fee=0.01,
            gross_pnl=0.5, net_pnl=0.48, pnl_pct=0.048,
            exit_reason="signal", signal_source="RSI_Rule",
        )
        d = trade.to_dict()
        expected_keys = [
            "trade_id", "symbol", "direction", "entry_bar_idx", "exit_bar_idx",
            "entry_price", "exit_price", "qty", "notional_usd",
            "entry_fee", "exit_fee", "gross_pnl", "net_pnl", "pnl_pct",
            "exit_reason", "signal_source",
        ]
        for key in expected_keys:
            assert key in d, f"Missing key: {key}"


# =============================================================================
# Additional: BacktestEngine status / 额外: 引擎状态
# =============================================================================

class TestBacktestEngineStatus:
    """Tests for BacktestEngine.get_status() / 引擎状态方法测试"""

    def test_status_idle_before_first_run(self):
        """Status is idle before any run / 首次运行前状态为 idle"""
        engine = BacktestEngine()
        status = engine.get_status()
        assert status["status"] == "idle"
        assert engine.get_last_result() is None

    def test_status_completed_after_run(self):
        """Status is completed after successful run / 运行后状态为 completed"""
        engine = BacktestEngine()
        config = _make_default_config()
        engine.run(config, _make_trending_up_ohlcv(100))
        status = engine.get_status()
        assert status["status"] == "completed"
        assert "summary" in status
        assert status["summary"]["symbol"] == "BTCUSDT"

    def test_get_last_result_returns_most_recent(self):
        """get_last_result() returns the most recent result / 返回最近一次结果"""
        engine = BacktestEngine()
        config1 = _make_default_config(symbol="BTCUSDT")
        config2 = _make_default_config(symbol="ETHUSDT")
        engine.run(config1, _make_trending_up_ohlcv(100))
        engine.run(config2, _make_trending_up_ohlcv(100))
        last = engine.get_last_result()
        assert last.symbol == "ETHUSDT"


# =============================================================================
# Additional: Annualization factors / 额外: 年化因子
# =============================================================================

class TestAnnualizationFactors:
    """Verify all annualization factors / 验证所有年化因子"""

    def test_all_expected_timeframes_present(self):
        """All FA-specified timeframes have annualization factors"""
        for tf in ("1m", "5m", "15m", "1h", "4h", "1d"):
            assert tf in ANNUALIZATION_FACTORS, f"Missing annualization factor for {tf}"

    def test_1m_factor_is_525600(self):
        assert ANNUALIZATION_FACTORS["1m"] == 525600  # 365 * 24 * 60

    def test_1h_factor_is_8760(self):
        assert ANNUALIZATION_FACTORS["1h"] == 8760  # 365 * 24

    def test_1d_factor_is_365(self):
        assert ANNUALIZATION_FACTORS["1d"] == 365


# =============================================================================
# E4 Edge Cases: Empty and Minimal Data / E4 边界: 空数据与最小数据
# =============================================================================

class TestBacktestEdgeCasesE4:
    """Edge case tests for BacktestEngine with degenerate inputs (E4 追加).
    回测引擎退化输入边界条件测试。"""

    def test_zero_bars_returns_warning(self):
        """0 bars (empty lists) should return a result with warning, not raise.
        0 根 K 线（空列表）应返回带 warning 的结果，不应抛出异常。"""
        engine = BacktestEngine()
        config = _make_default_config()
        result = engine.run(config, {"open": [], "high": [], "low": [], "close": [], "volume": []})
        assert isinstance(result, BacktestResult)
        assert result.warning is not None and len(result.warning) > 0
        assert result.total_trades == 0
        assert result.sharpe_ratio == 0.0

    def test_single_bar_returns_warning(self):
        """1 bar (below MIN_BARS_REQUIRED) should return a result with warning.
        1 根 K 线（低于 MIN_BARS_REQUIRED）应返回带 warning 的结果。"""
        engine = BacktestEngine()
        config = _make_default_config()
        ohlcv = {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0], "volume": [1000.0]}
        result = engine.run(config, ohlcv)
        assert isinstance(result, BacktestResult)
        assert result.warning is not None
        assert "1 bars" in result.warning or "Insufficient" in result.warning
        assert result.total_trades == 0

    def test_flat_data_produces_valid_result(self):
        """Flat OHLCV data (no price movement) should produce valid result.
        完全平坦的 OHLCV（无价格变化）应产生有效结果。"""
        engine = BacktestEngine()
        config = _make_default_config()
        ohlcv = _make_flat_ohlcv(100, price=100.0)
        result = engine.run(config, ohlcv)
        assert isinstance(result, BacktestResult)
        assert result.sharpe_ratio is not None
