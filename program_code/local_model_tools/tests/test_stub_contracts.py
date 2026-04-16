"""
Contract tests for DEDUP-PY-RUST stubs / DEDUP-PY-RUST stub 契約測試.

MODULE_NOTE (EN): After DEDUP-PY-RUST (2026-04-16, commit d41f72a), 21
  local_model_tools modules were reduced to thin stubs that preserve their
  public surface while delegating all computation to the Rust engine. These
  tests lock that public surface: constructor kwargs still accept, __all__
  still exports the same names, methods still return the documented empty
  shape ([], {}, None, False, zero-filled dataclass). They do NOT exercise
  any computation — Rust owns that and is tested on the Rust side.
MODULE_NOTE (中): DEDUP-PY-RUST 後，21 個 Python 模組被壓縮為 stub，
  保留介面表面、計算下沉到 Rust engine。本檔只測介面表面：建構子 kwargs
  仍能接受、__all__ 仍匯出相同名稱、方法仍回傳文件化的空形狀
  ([] / {} / None / False / 零值 dataclass)。任何計算行為皆由 Rust 單元
  測試負責。
"""

from __future__ import annotations

import pytest


# -----------------------------------------------------------------------------
# indicators/ package
# -----------------------------------------------------------------------------

def test_indicators_package_all():
    from local_model_tools import indicators as pkg

    expected = {
        "IndicatorBase", "SMA", "EMA", "RSI", "BollingerBands", "MACD", "ATR",
        "Stochastic", "KAMA", "ADX", "HurstIndicator", "EWMAVolIndicator",
        "VolumeRatio", "DonchianChannel",
    }
    assert expected.issubset(set(pkg.__all__))
    for name in expected:
        assert hasattr(pkg, name), f"indicators missing export: {name}"


@pytest.mark.parametrize(
    "module_path, cls_name, ctor_kwargs",
    [
        ("local_model_tools.indicators.moving_averages", "SMA", {"period": 20}),
        ("local_model_tools.indicators.moving_averages", "EMA", {"period": 12}),
        ("local_model_tools.indicators.rsi", "RSI", {"period": 14}),
        ("local_model_tools.indicators.bollinger_bands", "BollingerBands", {"period": 20, "std_dev_multiplier": 2.0}),
        ("local_model_tools.indicators.macd", "MACD", {"fast_period": 12, "slow_period": 26, "signal_period": 9}),
        ("local_model_tools.indicators.atr", "ATR", {"period": 14}),
        ("local_model_tools.indicators.stochastic", "Stochastic", {"k_period": 14, "d_period": 3, "slow_k_period": 3}),
        ("local_model_tools.indicators.extended", "KAMA", {"period": 10, "fast_sc": 2, "slow_sc": 30}),
        ("local_model_tools.indicators.extended", "ADX", {"period": 14}),
        ("local_model_tools.indicators.extended", "HurstIndicator", {"min_lag": 10, "max_lag": 50}),
        ("local_model_tools.indicators.extended", "EWMAVolIndicator", {"timeframe": "1h"}),
        ("local_model_tools.indicators.extended", "VolumeRatio", {"period": 20}),
        ("local_model_tools.indicators.extended", "DonchianChannel", {"period": 20}),
    ],
)
def test_indicator_class_contract(module_path, cls_name, ctor_kwargs):
    import importlib

    mod = importlib.import_module(module_path)
    cls = getattr(mod, cls_name)
    inst = cls(**ctor_kwargs)
    assert isinstance(inst.name, str) and inst.name
    assert isinstance(inst.min_periods, int) and inst.min_periods >= 1
    assert inst.compute() is None
    assert inst.compute(foo="bar", extra=123) is None


@pytest.mark.parametrize(
    "module_path, fn_name, args",
    [
        ("local_model_tools.indicators.moving_averages", "compute_sma", ([1.0, 2.0, 3.0], 2)),
        ("local_model_tools.indicators.moving_averages", "compute_ema", ([1.0, 2.0, 3.0], 2)),
        ("local_model_tools.indicators.moving_averages", "compute_sma_series", ([1.0, 2.0, 3.0], 2)),
        ("local_model_tools.indicators.moving_averages", "compute_ema_series", ([1.0, 2.0, 3.0], 2)),
        ("local_model_tools.indicators.rsi", "compute_rsi", ([1.0, 2.0], 14)),
        ("local_model_tools.indicators.rsi", "compute_rsi_series", ([1.0, 2.0], 14)),
        ("local_model_tools.indicators.macd", "compute_macd", ([1.0, 2.0],)),
        ("local_model_tools.indicators.bollinger_bands", "compute_bollinger_bands", ([1.0, 2.0],)),
        ("local_model_tools.indicators.bollinger_bands", "compute_stddev", ([1.0, 2.0], 2)),
        ("local_model_tools.indicators.atr", "compute_true_range", ([1.0], [0.5], [0.7])),
        ("local_model_tools.indicators.atr", "compute_atr", ([1.0], [0.5], [0.7])),
        ("local_model_tools.indicators.atr", "compute_atr_percent", ([1.0], [0.5], [0.7])),
        ("local_model_tools.indicators.stochastic", "compute_stochastic", ([1.0], [0.5], [0.7])),
    ],
)
def test_indicator_module_functions_return_none(module_path, fn_name, args):
    import importlib

    mod = importlib.import_module(module_path)
    fn = getattr(mod, fn_name)
    assert fn(*args) is None


# -----------------------------------------------------------------------------
# indicator_engine
# -----------------------------------------------------------------------------

def test_indicator_engine_contract():
    from local_model_tools.indicator_engine import IndicatorEngine

    eng = IndicatorEngine(kline_manager=None, indicators=[])
    assert eng.get_indicators("BTCUSDT", "1h") == {}
    assert eng.get_indicator("BTCUSDT", "1h", "RSI(14)") is None
    assert eng.compute_now("BTCUSDT", "1h") == {}
    assert eng.get_all_cached() == {}
    assert eng.get_conservative_atr("BTCUSDT") == {"atr": None, "atr_percent": None}

    status = eng.get_status()
    assert status["stub"] is True
    assert status["source"] == "rust_engine_primary"
    assert status["indicators_registered"] == 0

    # Registration surface still works (no crash, counter increments).
    called: list[str] = []
    eng.register_on_update(lambda s, tf, ind: called.append(s))
    assert eng.get_status()["indicators_registered"] == 0
    eng.clear_cache()


# -----------------------------------------------------------------------------
# signal_generator + signal_engine
# -----------------------------------------------------------------------------

def test_signal_direction_constants():
    from local_model_tools.signal_generator import (
        ALL_DIRECTIONS, DIRECTION_CLOSE_LONG, DIRECTION_CLOSE_SHORT,
        DIRECTION_LONG, DIRECTION_NEUTRAL, DIRECTION_SHORT,
        SIGNAL_HISTORY_CAPACITY,
    )

    assert DIRECTION_LONG == "long"
    assert DIRECTION_SHORT == "short"
    assert DIRECTION_CLOSE_LONG == "close_long"
    assert DIRECTION_CLOSE_SHORT == "close_short"
    assert DIRECTION_NEUTRAL == "neutral"
    assert ALL_DIRECTIONS == {
        DIRECTION_LONG, DIRECTION_SHORT, DIRECTION_CLOSE_LONG,
        DIRECTION_CLOSE_SHORT, DIRECTION_NEUTRAL,
    }
    assert SIGNAL_HISTORY_CAPACITY == 1000


def test_signal_dataclass_surface():
    from local_model_tools.signal_generator import (
        DIRECTION_LONG, DIRECTION_NEUTRAL, Signal,
    )

    sig = Signal(
        symbol="BTCUSDT",
        direction=DIRECTION_LONG,
        confidence=0.75,
        edge_bps=12.0,
        source="stub",
        timeframe="1h",
        reasoning="test",
    )
    assert sig.symbol == "BTCUSDT"
    assert sig.direction == DIRECTION_LONG
    assert sig.confidence == 0.75
    assert sig.edge_bps == 12.0
    assert sig.is_actionable is True
    assert sig.is_entry is True
    assert sig.is_exit is False
    assert isinstance(sig.ts_ms, int) and sig.ts_ms > 0
    assert sig.to_dict()["symbol"] == "BTCUSDT"

    neutral = Signal("BTCUSDT", DIRECTION_NEUTRAL, 0.0)
    assert neutral.is_actionable is False


@pytest.mark.parametrize(
    "cls_name",
    [
        "RSIOverboughtOversoldRule", "MACrossoverRule", "KAMACrossoverRule",
        "BollingerBandReversionRule", "MACDCrossoverRule", "RegimeDetectorRule",
        "RSIExitRule", "MACDExhaustionRule", "RSIDivergenceRule",
    ],
)
def test_signal_rule_evaluate_returns_none(cls_name):
    import local_model_tools.signal_generator as sg

    rule = getattr(sg, cls_name)()
    assert isinstance(rule.name, str) and rule.name
    assert rule.evaluate("BTCUSDT", "1h", {}) is None


def test_create_default_signal_rules():
    from local_model_tools.signal_generator import (
        SignalRule, create_default_signal_rules,
    )

    rules = create_default_signal_rules()
    assert isinstance(rules, list) and len(rules) >= 1
    for r in rules:
        assert isinstance(r, SignalRule)


def test_signal_engine_contract():
    from local_model_tools.signal_engine import SignalEngine

    eng = SignalEngine()
    assert eng.on_indicators_update("BTCUSDT", "1h", {}) == []
    assert eng.get_latest_signals() == []
    assert eng.get_latest_signals(symbol="BTCUSDT", n=5) == []
    assert eng.get_latest_for_symbol("BTCUSDT") == {}

    summary = eng.get_signal_summary("BTCUSDT")
    assert summary["stub"] is True
    assert summary["signals"] == []
    assert summary["symbol"] == "BTCUSDT"

    stats = eng.get_stats()
    assert stats["stub"] is True
    assert stats["source"] == "rust_engine_primary"
    assert stats["rules_registered"] == 0

    eng.register_rule(object())
    assert eng.get_stats()["rules_registered"] == 1
    eng.register_on_signal(lambda s: None)
    eng.clear_history()


def test_signal_generator_reexports_signal_engine():
    # Back-compat: legacy `from .signal_generator import SignalEngine`.
    from local_model_tools.signal_generator import SignalEngine as SG_SignalEngine
    from local_model_tools.signal_engine import SignalEngine as SE_SignalEngine

    assert SG_SignalEngine is SE_SignalEngine


# -----------------------------------------------------------------------------
# kline_manager
# -----------------------------------------------------------------------------

def test_kline_constants():
    from local_model_tools.kline_manager import (
        DEFAULT_TIMEFRAMES, TIMEFRAME_DURATIONS,
    )

    assert TIMEFRAME_DURATIONS["1h"] == 3600
    assert TIMEFRAME_DURATIONS["1d"] == 86400
    assert "1h" in DEFAULT_TIMEFRAMES


def test_kline_bar_dataclass_shape():
    from local_model_tools.kline_manager import KlineBar

    bar = KlineBar(open_time_ms=1, close_time_ms=2, open_price=100.0)
    assert bar.open == 100.0
    assert bar.high == 100.0
    assert bar.low == 100.0
    assert bar.close == 100.0
    bar.update(101.0, volume=5.0, turnover=500.0)
    assert bar.close == 101.0
    assert bar.high == 101.0
    assert bar.volume == 5.0
    d = bar.to_dict()
    assert d["open"] == 100.0 and d["close"] == 101.0


def test_kline_manager_contract():
    from local_model_tools.kline_manager import KlineManager

    km = KlineManager(symbols=["BTCUSDT"], timeframes=["1h"])
    assert km.get_tracked_symbols() == ["BTCUSDT"]
    assert km.get_timeframes() == ["1h"]
    km.add_symbol("ETHUSDT")
    assert "ETHUSDT" in km.get_tracked_symbols()
    km.remove_symbol("ETHUSDT")
    assert "ETHUSDT" not in km.get_tracked_symbols()

    assert km.get_buffer("BTCUSDT", "1h") is None
    assert km.get_current_bar("BTCUSDT", "1h") is None
    assert km.get_latest_klines("BTCUSDT", "1h") == []
    assert km.get_ohlcv("BTCUSDT", "1h") == {
        "open": [], "high": [], "low": [], "close": [], "volume": [],
    }
    assert km.bootstrap_from_rest() == {}

    stats = km.get_stats()
    assert stats["stub"] is True
    assert stats["source"] == "rust_engine_primary"
    assert km.get_status() == stats

    stale = km.get_staleness()
    assert stale["stub"] is True
    assert stale["stale_count"] == 0


# -----------------------------------------------------------------------------
# market_scanner
# -----------------------------------------------------------------------------

def test_market_scanner_contract():
    from local_model_tools.market_scanner import (
        MAX_SYMBOLS_TO_TRADE, MIN_VOLUME_24H_USDT, MarketScanner,
        SymbolOpportunity,
    )

    opp = SymbolOpportunity(symbol="BTCUSDT", score=0.9, category="trend")
    assert opp.symbol == "BTCUSDT"
    assert opp.api_category == "linear"

    scanner = MarketScanner(
        scan_interval_sec=300.0,
        min_volume=MIN_VOLUME_24H_USDT,
        max_symbols=MAX_SYMBOLS_TO_TRADE,
        categories=["linear"],
    )
    scanner.register_on_scan(lambda results: None)
    scanner.start()
    scanner.stop()
    assert scanner.scan() == []
    assert scanner.get_latest_opportunities() == []

    stats = scanner.get_stats()
    assert stats["stub"] is True
    assert stats["source"] == "rust_engine_primary"
    assert stats["max_symbols"] == MAX_SYMBOLS_TO_TRADE


# -----------------------------------------------------------------------------
# position_sizer
# -----------------------------------------------------------------------------

def test_position_sizer_contract():
    from local_model_tools.position_sizer import PositionSizer, SizingRecommendation

    sizer = PositionSizer(p1_max_pct=2.0, risk_pct_default=3.0)
    assert sizer.compute_kelly_fraction(0.6, 10.0, 5.0, trade_count=50) == 0.0
    assert sizer.compute_volatility_adjusted_qty(1000.0, 10.0, 100.0) == 0.0
    assert sizer.compute_max_allowed_qty(1000.0, 100.0) == 0.0
    assert sizer.compute_risk_parity_weights({"BTCUSDT": 0.1}) == {}

    rec = sizer.compute_recommendation(
        balance=1000.0,
        price=100.0,
        win_rate=0.55,
        avg_win=10.0,
        avg_loss=5.0,
        trade_count=20,
        atr=5.0,
    )
    assert isinstance(rec, SizingRecommendation)
    assert rec.recommended_qty == 0.0
    assert rec.sample_size == 20
    assert rec.win_rate == 0.55
    d = rec.to_dict()
    assert d["stub"] is True
    assert d["recommended_qty"] == 0.0


# -----------------------------------------------------------------------------
# strategies/base
# -----------------------------------------------------------------------------

def test_strategy_state_constants():
    from local_model_tools.strategies.base import (
        STRATEGY_ACTIVE, STRATEGY_IDLE, STRATEGY_PAUSED, STRATEGY_STOPPED,
    )

    assert STRATEGY_IDLE == "idle"
    assert STRATEGY_ACTIVE == "active"
    assert STRATEGY_PAUSED == "paused"
    assert STRATEGY_STOPPED == "stopped"


def test_order_intent_contract():
    from local_model_tools.strategies.base import OrderIntent

    intent = OrderIntent(
        symbol="BTCUSDT", side="buy", qty=0.5, price=100.0,
        strategy_name="stub_strategy", reason="test", confidence=0.8,
    )
    assert intent.symbol == "BTCUSDT"
    assert intent.side == "buy"
    assert intent.qty == 0.5
    assert intent.metadata == {}
    d = intent.to_dict()
    assert d["strategy_name"] == "stub_strategy"
    assert d["confidence"] == 0.8


def test_strategy_base_lifecycle():
    from local_model_tools.strategies.base import (
        STRATEGY_ACTIVE, STRATEGY_IDLE, STRATEGY_PAUSED, STRATEGY_STOPPED,
        OrderIntent, StrategyBase,
    )

    class _DummyStrategy(StrategyBase):
        @property
        def name(self) -> str:
            return "dummy"

        @property
        def description(self) -> str:
            return "stub-only dummy strategy"

        def get_status(self) -> dict:
            return {"name": self.name, "state": self.state}

    strat = _DummyStrategy()
    assert strat.state == STRATEGY_IDLE
    assert strat.registered_name == "dummy"
    strat.activate()
    assert strat.state == STRATEGY_ACTIVE
    strat.pause()
    assert strat.state == STRATEGY_PAUSED
    strat.stop()
    assert strat.state == STRATEGY_STOPPED

    strat.on_signal(object())
    strat.on_tick("BTCUSDT", 100.0, 1_700_000_000_000)
    strat.on_fill({"symbol": "BTCUSDT"}, is_open=True)
    assert strat.get_pending_intents() == []

    intent = OrderIntent("BTCUSDT", "buy", qty=0.1)
    strat._emit_intent(intent)
    assert strat.pending_intent_count == 1
    drained = strat.get_pending_intents()
    assert drained == [intent]
    assert strat.pending_intent_count == 0

    strat.record_trade_result("BTCUSDT", "buy", 0.1, 100.0, 110.0)
    assert strat.get_pnl_summary()["stub"] is True
    assert strat.get_persistent_state() == {}
    strat.restore_persistent_state({"anything": 1})


# -----------------------------------------------------------------------------
# backtest_types + backtest_engine
# -----------------------------------------------------------------------------

def test_backtest_constants():
    from local_model_tools.backtest_types import (
        ANNUALIZATION_FACTORS, MIN_BARS_REQUIRED, MIN_TRADES_FOR_STATS,
    )

    assert ANNUALIZATION_FACTORS["1h"] == 8760
    assert ANNUALIZATION_FACTORS["1d"] == 365
    assert MIN_BARS_REQUIRED == 30
    assert MIN_TRADES_FOR_STATS == 2


def test_backtest_config_defaults():
    from local_model_tools.backtest_types import BacktestConfig

    cfg = BacktestConfig(
        symbol="BTCUSDT", strategy_name="stub", backtest_mode=True,
    )
    assert cfg.symbol == "BTCUSDT"
    assert cfg.timeframe == "1h"
    assert cfg.initial_capital == 1000.0
    assert cfg.backtest_mode is True


def test_backtest_trade_to_dict():
    from local_model_tools.backtest_types import BacktestTrade

    t = BacktestTrade(trade_id=1, symbol="BTCUSDT", direction="long", qty=0.1)
    d = t.to_dict()
    assert d["trade_id"] == 1
    assert d["symbol"] == "BTCUSDT"
    assert d["direction"] == "long"
    assert d["net_pnl"] == 0.0


def test_backtest_result_defaults_and_to_dict():
    from local_model_tools.backtest_types import BacktestResult

    r = BacktestResult(symbol="BTCUSDT", strategy_name="stub")
    assert r.total_trades == 0
    assert r.trades == []
    assert r.equity_curve == []
    d = r.to_dict()
    assert d["symbol"] == "BTCUSDT"
    assert d["warning"]  # non-empty fallback message


def test_backtest_engine_contract():
    from local_model_tools.backtest_engine import BacktestEngine
    from local_model_tools.backtest_types import BacktestConfig, BacktestResult

    eng = BacktestEngine()
    cfg = BacktestConfig(
        symbol="BTCUSDT", strategy_name="stub", backtest_mode=True,
    )
    result = eng.run(cfg)
    assert isinstance(result, BacktestResult)
    assert result.symbol == "BTCUSDT"
    assert result.initial_capital == cfg.initial_capital
    assert result.final_capital == cfg.initial_capital
    assert result.total_trades == 0
    assert "Rust" in result.warning or "stub" in result.warning.lower()
    assert eng.get_last_result() is result

    status = eng.get_status()
    assert status["stub"] is True
    assert status["source"] == "rust_engine_primary"
    assert status["last_result_available"] is True


def test_backtest_engine_requires_backtest_mode():
    from local_model_tools.backtest_engine import BacktestEngine
    from local_model_tools.backtest_types import BacktestConfig

    eng = BacktestEngine()
    cfg = BacktestConfig(symbol="BTCUSDT", strategy_name="stub", backtest_mode=False)
    with pytest.raises(ValueError):
        eng.run(cfg)


# -----------------------------------------------------------------------------
# strategy_orchestrator
# -----------------------------------------------------------------------------

def test_strategy_orchestrator_contract():
    from local_model_tools.strategies.base import StrategyBase
    from local_model_tools.strategy_orchestrator import StrategyOrchestrator

    class _DummyStrategy(StrategyBase):
        @property
        def name(self) -> str:
            return "dummy"

        @property
        def description(self) -> str:
            return "dummy"

        def get_status(self) -> dict:
            return {"name": "dummy", "state": self.state}

    orch = StrategyOrchestrator(
        kline_manager=None,
        indicator_engine=None,
        signal_engine=None,
    )
    assert orch.list_available_strategies() == []
    assert orch.collect_pending_intents() == []
    assert orch.get_all_strategies_status() == []
    assert orch.get_intent_history() == []
    assert orch.get_indicators("BTCUSDT", "1h") == {}
    assert orch.get_current_regime() == "unknown"

    strat = _DummyStrategy()
    orch.register_strategy(strat, name="dummy")
    assert "dummy" in orch.list_available_strategies()
    assert orch.activate_strategy("dummy") is True
    assert orch.activate_strategy("missing") is False
    assert orch.pause_strategy("dummy") is True
    assert orch.stop_strategy("dummy") is True
    status = orch.get_strategy_status("dummy")
    assert status is not None
    assert status.get("name") == "dummy"
    assert orch.remove_strategy("dummy") is True

    orch_status = orch.get_status()
    assert orch_status["component"] == "strategy_orchestrator"
    assert orch_status["stub"] is True
    assert orch_status["source"] == "rust_engine_primary"
    assert "kline_manager_status" in orch_status
    assert "indicator_engine_status" in orch_status
    assert "signal_engine_status" in orch_status

    orch.compute_indicators("BTCUSDT", "1h")
    assert orch.save_all_strategy_state() == {}
    orch.restore_all_strategy_state({})
    orch.set_ai_engine(object())
    assert orch.request_ai_analysis("test") is None
    orch.dispatch_tick("BTCUSDT", 100.0, 1_700_000_000_000)


# -----------------------------------------------------------------------------
# strategy_auto_deployer
# -----------------------------------------------------------------------------

def test_strategy_auto_deployer_category_priority():
    from local_model_tools.strategy_auto_deployer import CATEGORY_PRIORITY_BONUS

    assert CATEGORY_PRIORITY_BONUS["funding_arb"] == 50
    assert CATEGORY_PRIORITY_BONUS["grid"] == 20
    assert CATEGORY_PRIORITY_BONUS["trend"] == 0


def test_strategy_auto_deployer_contract():
    from local_model_tools.strategy_auto_deployer import StrategyAutoDeployer

    deployer = StrategyAutoDeployer(
        orchestrator=None,
        kline_manager=None,
        paper_engine=None,
        max_symbols=25,
        risk_per_trade_pct=3.0,
    )
    deployer.on_scan_results([])
    assert deployer.apply_evolution_result({}) is False
    deployer.set_backtest_engine(object(), min_sharpe=1.0)
    deployer.update_risk_from_sharpe()
    assert deployer.compute_dynamic_qty("BTCUSDT", 100.0) == 0.0
    deployer.notify_fill("strat", {"symbol": "BTCUSDT"}, is_open=True)
    deployer.on_trade_result("strat", 10.0)
    deployer.remove_stale_strategies({"BTCUSDT"})
    deployer.set_pipeline_bridge(object())

    assert deployer.get_deployed() == []

    kelly = deployer.get_kelly_recommendations()
    assert kelly["stub"] is True
    assert kelly["recommendations"] == {}

    risk = deployer.get_dynamic_risk_status()
    assert risk["stub"] is True
    assert risk["risk_pct"] == 3.0
    deployer.set_dynamic_risk_enabled(True)
    assert deployer.get_dynamic_risk_status()["enabled"] is True

    stats = deployer.get_stats()
    assert stats["stub"] is True
    assert stats["source"] == "rust_engine_primary"
    assert stats["max_symbols"] == 25
    assert stats["risk_pct"] == 3.0
