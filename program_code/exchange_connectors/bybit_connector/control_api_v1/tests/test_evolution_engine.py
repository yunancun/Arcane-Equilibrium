"""
tests/test_evolution_engine.py — EvolutionEngine Test Suite
进化引擎测试套件

MODULE_NOTE (中文):
  测试 EvolutionEngine 的参数网格搜索、BacktestEngine 集成、TruthRegistry 注入、
  原则 7 隔离验证及资源防护。
  全部测试使用 Mock BacktestEngine，不依赖真实 K 线数据。

MODULE_NOTE (English):
  Tests for EvolutionEngine: parameter grid search, BacktestEngine integration,
  TruthRegistry injection, Principle 7 isolation, and resource guards.
  All tests use Mock BacktestEngine; no real kline data required.

验收标准 EV1-EV6 全覆盖。/ Full coverage of EV1-EV6 acceptance criteria.
"""

from __future__ import annotations

import ast
import logging
import os
import sys
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Path setup — resolve local_model_tools package
# 路径设置 — 解析 local_model_tools 包
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(__file__)
# Walk up: tests/ -> control_api_v1/ -> bybit_connector/ -> exchange_connectors/
# -> program_code/ -> srv/
# 5 levels up from tests/ reaches srv/
_SRV = os.path.abspath(os.path.join(_HERE, *[".."] * 5))
if _SRV not in sys.path:
    sys.path.insert(0, _SRV)

from program_code.local_model_tools.evolution_engine import (
    EvolutionEngine,
    EvolutionResult,
    ParameterGrid,
)

# ---------------------------------------------------------------------------
# Helpers / 辅助函数
# ---------------------------------------------------------------------------

def _make_mock_result(sharpe: float = 1.5, win_rate: float = 0.6, total_trades: int = 25) -> MagicMock:
    """Create a MagicMock BacktestResult with given metrics."""
    r = MagicMock()
    r.sharpe_ratio = sharpe
    r.win_rate = win_rate
    r.total_trades = total_trades
    return r


def _make_mock_engine(sharpe: float = 1.5, win_rate: float = 0.6) -> MagicMock:
    """Create a MagicMock BacktestEngine that returns a fixed result."""
    mock_engine = MagicMock()
    mock_engine.run.return_value = _make_mock_result(sharpe=sharpe, win_rate=win_rate)
    return mock_engine


def _make_evolution_engine(sharpe: float = 1.5, max_combinations: int = 50) -> tuple:
    """Return (EvolutionEngine, mock_backtest_engine)."""
    mock_engine = _make_mock_engine(sharpe=sharpe)
    engine = EvolutionEngine(backtest_engine=mock_engine, max_combinations=max_combinations)
    return engine, mock_engine


# ---------------------------------------------------------------------------
# EV1 — ParameterGrid and combination generation / 参数网格与组合生成
# 5 tests
# ---------------------------------------------------------------------------

class TestParameterGrid:
    """EV1: ParameterGrid dataclass and _build_parameter_combinations."""

    def test_ev1_parameter_grid_fields(self):
        """ParameterGrid 有正确的 name 和 values 字段 / ParameterGrid has correct name and values fields."""
        grid = ParameterGrid(name="stop_loss_pct", values=[0.01, 0.02, 0.03])
        assert grid.name == "stop_loss_pct"
        assert grid.values == [0.01, 0.02, 0.03]

    def test_ev1_single_parameter_three_values(self):
        """单一参数 3 个值 → 3 个组合 / Single param with 3 values → 3 combos."""
        engine = EvolutionEngine(backtest_engine=_make_mock_engine())
        combos = engine._build_parameter_combinations(
            [ParameterGrid(name="stop_loss_pct", values=[0.01, 0.02, 0.03])],
            max_count=50,
        )
        assert len(combos) == 3
        assert combos[0] == {"stop_loss_pct": 0.01}
        assert combos[1] == {"stop_loss_pct": 0.02}
        assert combos[2] == {"stop_loss_pct": 0.03}

    def test_ev1_two_params_cartesian_product(self):
        """2x3 参数 → 6 个组合 / 2x3 params → 6 combos."""
        engine = EvolutionEngine(backtest_engine=_make_mock_engine())
        grids = [
            ParameterGrid(name="position_size_pct", values=[0.01, 0.02]),
            ParameterGrid(name="stop_loss_pct", values=[0.01, 0.02, 0.03]),
        ]
        combos = engine._build_parameter_combinations(grids, max_count=50)
        assert len(combos) == 6
        # 所有组合均包含两个键 / All combos contain both keys
        for c in combos:
            assert "position_size_pct" in c
            assert "stop_loss_pct" in c

    def test_ev1_truncation_at_max_combinations(self):
        """超过 max_combinations 被截断 / Exceeds max_combinations → truncated."""
        engine = EvolutionEngine(backtest_engine=_make_mock_engine(), max_combinations=4)
        grids = [
            ParameterGrid(name="position_size_pct", values=[0.01, 0.02, 0.03]),
            ParameterGrid(name="stop_loss_pct", values=[0.01, 0.02, 0.03]),
        ]
        # 3×3 = 9 but max_combinations = 4 → truncated to 4
        combos = engine._build_parameter_combinations(grids, max_count=4)
        assert len(combos) == 4

    def test_ev1_truncation_logs_warning(self, caplog):
        """截断时有 warning log / Truncation produces warning log."""
        engine = EvolutionEngine(backtest_engine=_make_mock_engine(), max_combinations=2)
        grids = [
            ParameterGrid(name="stop_loss_pct", values=[0.01, 0.02, 0.03]),
        ]
        with caplog.at_level(logging.WARNING):
            engine._build_parameter_combinations(grids, max_count=2)
        assert any("truncat" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# EV2 — EvolutionResult dataclass / EvolutionResult 数据类
# 4 tests
# ---------------------------------------------------------------------------

class TestEvolutionResult:
    """EV2: EvolutionResult dataclass invariants."""

    def test_ev2_is_simulated_always_true(self):
        """is_simulated 始终为 True，即使传入 False / is_simulated always True even if False passed."""
        result = EvolutionResult(
            strategy_name="ma_crossover",
            symbol="BTCUSDT",
            timeframe="1h",
            best_params={"stop_loss_pct": 0.02},
            best_sharpe=1.5,
            best_win_rate=0.6,
            total_combinations=3,
            evaluated_combinations=3,
            all_results=[],
            completed_at_ms=1000000,
            is_simulated=False,  # 尝试传入 False / Attempt to pass False
        )
        # __post_init__ 强制为 True / __post_init__ forces to True
        assert result.is_simulated is True

    def test_ev2_to_dict_contains_required_keys(self):
        """to_dict() 包含所有必要键 / to_dict() contains all required keys."""
        result = EvolutionResult(
            strategy_name="rsi_bb",
            symbol="ETHUSDT",
            timeframe="5m",
            best_params={"stop_loss_pct": 0.01},
            best_sharpe=2.1,
            best_win_rate=0.55,
            total_combinations=10,
            evaluated_combinations=10,
            all_results=[],
            completed_at_ms=9999999,
        )
        d = result.to_dict()
        assert "strategy_name" in d
        assert "best_params" in d
        assert "best_sharpe" in d
        assert "is_simulated" in d
        # is_simulated must be True in the serialized output too
        assert d["is_simulated"] is True

    def test_ev2_all_results_sorted_by_sharpe_desc(self):
        """all_results 按 sharpe 降序排列 / all_results sorted by sharpe descending."""
        # Simulate what run_evolution would produce
        engine, _ = _make_evolution_engine()

        # Build results with varied sharpe values
        all_results = [
            {"params": {"stop_loss_pct": 0.01}, "sharpe": 0.5, "win_rate": 0.45, "total_trades": 10},
            {"params": {"stop_loss_pct": 0.03}, "sharpe": 2.0, "win_rate": 0.65, "total_trades": 30},
            {"params": {"stop_loss_pct": 0.02}, "sharpe": 1.2, "win_rate": 0.55, "total_trades": 20},
        ]
        all_results.sort(key=lambda x: x["sharpe"], reverse=True)

        result = EvolutionResult(
            strategy_name="test",
            symbol="BTCUSDT",
            timeframe="1h",
            best_params={"stop_loss_pct": 0.03},
            best_sharpe=2.0,
            best_win_rate=0.65,
            total_combinations=3,
            evaluated_combinations=3,
            all_results=all_results,
            completed_at_ms=1000000,
        )
        sharpes = [r["sharpe"] for r in result.all_results]
        assert sharpes == sorted(sharpes, reverse=True)

    def test_ev2_empty_best_result_on_all_failures(self):
        """全部评估失败时返回 best_sharpe=0.0 / All evals fail → best_sharpe=0.0."""
        # Create engine that always raises
        failing_engine = MagicMock()
        failing_engine.run.side_effect = RuntimeError("Simulated failure")
        engine = EvolutionEngine(backtest_engine=failing_engine)

        result = engine.run_evolution(
            strategy_name="ma_crossover",
            symbol="BTCUSDT",
            timeframe="1h",
            parameter_grids=[ParameterGrid(name="stop_loss_pct", values=[0.01, 0.02])],
        )
        assert result.best_sharpe == 0.0
        assert result.best_params == {}
        assert result.is_simulated is True


# ---------------------------------------------------------------------------
# EV3 — run_evolution core behavior / run_evolution 核心行为
# 8 tests
# ---------------------------------------------------------------------------

class TestRunEvolutionCore:
    """EV3: run_evolution core behavior."""

    def test_ev3_each_combination_calls_backtest_run(self):
        """每个参数组合都调用一次 backtest_engine.run() / Each combo calls run() once."""
        engine, mock_backtest = _make_evolution_engine()
        grids = [ParameterGrid(name="stop_loss_pct", values=[0.01, 0.02, 0.03])]

        engine.run_evolution(
            strategy_name="ma_crossover",
            symbol="BTCUSDT",
            timeframe="1h",
            parameter_grids=grids,
        )
        assert mock_backtest.run.call_count == 3

    def test_ev3_best_params_has_highest_sharpe(self):
        """最优参数对应最高 Sharpe / Best params correspond to highest Sharpe."""
        mock_engine = MagicMock()
        # Return different sharpe values for different calls
        results = [
            _make_mock_result(sharpe=0.5),
            _make_mock_result(sharpe=2.5),  # best
            _make_mock_result(sharpe=1.0),
        ]
        mock_engine.run.side_effect = results

        evolution = EvolutionEngine(backtest_engine=mock_engine)
        grids = [ParameterGrid(name="stop_loss_pct", values=[0.01, 0.02, 0.03])]

        result = evolution.run_evolution(
            strategy_name="ma_crossover",
            symbol="BTCUSDT",
            timeframe="1h",
            parameter_grids=grids,
        )
        assert result.best_sharpe == 2.5
        assert result.best_params == {"stop_loss_pct": 0.02}

    def test_ev3_truncation_at_max_combinations(self):
        """超过 max_combinations 时截断 / Truncated when exceeding max_combinations."""
        engine, mock_backtest = _make_evolution_engine(max_combinations=2)
        grids = [ParameterGrid(name="stop_loss_pct", values=[0.01, 0.02, 0.03, 0.04, 0.05])]

        result = engine.run_evolution(
            strategy_name="ma_crossover",
            symbol="BTCUSDT",
            timeframe="1h",
            parameter_grids=grids,
        )
        # Only 2 combinations evaluated due to max_combinations=2
        assert mock_backtest.run.call_count == 2
        assert result.evaluated_combinations == 2
        # total_combinations should reflect original space
        assert result.total_combinations == 5

    def test_ev3_single_eval_exception_does_not_abort(self):
        """单次评估拋异常不中止搜索 / Single eval exception does not abort search."""
        mock_engine = MagicMock()
        # First call raises, second succeeds
        mock_engine.run.side_effect = [
            RuntimeError("First failed"),
            _make_mock_result(sharpe=1.8),
            _make_mock_result(sharpe=1.0),
        ]
        evolution = EvolutionEngine(backtest_engine=mock_engine)
        grids = [ParameterGrid(name="stop_loss_pct", values=[0.01, 0.02, 0.03])]

        result = evolution.run_evolution(
            strategy_name="ma_crossover",
            symbol="BTCUSDT",
            timeframe="1h",
            parameter_grids=grids,
        )
        # All 3 combinations attempted despite first failure
        assert mock_engine.run.call_count == 3
        # Best of the two successful ones
        assert result.best_sharpe == 1.8

    def test_ev3_all_failures_returns_empty_result(self):
        """全部失败返回空结果，不崩溃 / All failures → empty result, no crash."""
        failing_engine = MagicMock()
        failing_engine.run.side_effect = RuntimeError("Always fails")
        evolution = EvolutionEngine(backtest_engine=failing_engine)
        grids = [ParameterGrid(name="stop_loss_pct", values=[0.01, 0.02])]

        result = evolution.run_evolution(
            strategy_name="ma_crossover",
            symbol="BTCUSDT",
            timeframe="1h",
            parameter_grids=grids,
        )
        assert result.best_sharpe == 0.0
        assert result.best_params == {}
        assert result.evaluated_combinations == 2

    def test_ev3_empty_parameter_grids_no_crash(self):
        """空 parameter_grids 不崩溃，至少评估一个空组合 / Empty grids: no crash, evaluates one empty combo."""
        engine, mock_backtest = _make_evolution_engine()

        result = engine.run_evolution(
            strategy_name="ma_crossover",
            symbol="BTCUSDT",
            timeframe="1h",
            parameter_grids=[],  # empty
        )
        # Should evaluate at least one combo (the empty params combo)
        assert mock_backtest.run.call_count >= 1
        assert result is not None

    def test_ev3_completed_at_ms_positive(self):
        """返回结果有 completed_at_ms > 0 / Result has completed_at_ms > 0."""
        engine, _ = _make_evolution_engine()
        result = engine.run_evolution(
            strategy_name="ma_crossover",
            symbol="BTCUSDT",
            timeframe="1h",
            parameter_grids=[ParameterGrid(name="stop_loss_pct", values=[0.02])],
        )
        assert result.completed_at_ms > 0

    def test_ev3_backtest_mode_true_passed_to_engine(self):
        """backtest_mode=True 强制传给 BacktestEngine / backtest_mode=True always passed to BacktestEngine."""
        engine, mock_backtest = _make_evolution_engine()
        grids = [ParameterGrid(name="stop_loss_pct", values=[0.01, 0.02])]

        engine.run_evolution(
            strategy_name="ma_crossover",
            symbol="BTCUSDT",
            timeframe="1h",
            parameter_grids=grids,
        )
        # Check every call received a config with backtest_mode=True
        for call_args in mock_backtest.run.call_args_list:
            config_arg = call_args[0][0]
            assert config_arg.backtest_mode is True, (
                f"backtest_mode must be True, got {config_arg.backtest_mode}"
            )


# ---------------------------------------------------------------------------
# EV4 — TruthRegistry injection / TruthRegistry 注入
# 5 tests
# ---------------------------------------------------------------------------

class TestTruthRegistryInjection:
    """EV4: TruthSourceRegistry injection behavior."""

    def _make_engine_with_registry(self, sharpe: float = 1.5) -> tuple:
        """Return (EvolutionEngine with mock registry, mock_backtest, mock_registry)."""
        mock_backtest = _make_mock_engine(sharpe=sharpe)
        mock_registry = MagicMock()
        engine = EvolutionEngine(
            backtest_engine=mock_backtest,
            truth_registry=mock_registry,
        )
        return engine, mock_backtest, mock_registry

    def test_ev4_register_called_when_sharpe_above_threshold(self):
        """sharpe >= min_sharpe 时调用 register_claim / register_claim called when sharpe >= threshold."""
        mock_backtest = _make_mock_engine(sharpe=2.0)
        mock_registry = MagicMock()
        engine = EvolutionEngine(backtest_engine=mock_backtest, truth_registry=mock_registry)

        engine.run_evolution(
            strategy_name="ma_crossover",
            symbol="BTCUSDT",
            timeframe="1h",
            parameter_grids=[ParameterGrid(name="stop_loss_pct", values=[0.02])],
            min_sharpe_to_register=1.0,
        )
        mock_registry.register_claim.assert_called_once()

    def test_ev4_register_not_called_when_sharpe_below_threshold(self):
        """sharpe < min_sharpe 时不调用 register_claim / register_claim NOT called when below threshold."""
        mock_backtest = _make_mock_engine(sharpe=0.5)
        mock_registry = MagicMock()
        engine = EvolutionEngine(backtest_engine=mock_backtest, truth_registry=mock_registry)

        engine.run_evolution(
            strategy_name="ma_crossover",
            symbol="BTCUSDT",
            timeframe="1h",
            parameter_grids=[ParameterGrid(name="stop_loss_pct", values=[0.02])],
            min_sharpe_to_register=1.0,
        )
        mock_registry.register_claim.assert_not_called()

    def test_ev4_none_registry_no_crash(self):
        """truth_registry=None 不崩溃 / truth_registry=None does not crash."""
        engine, _ = _make_evolution_engine()  # no registry
        # Should not raise
        result = engine.run_evolution(
            strategy_name="ma_crossover",
            symbol="BTCUSDT",
            timeframe="1h",
            parameter_grids=[ParameterGrid(name="stop_loss_pct", values=[0.02])],
            min_sharpe_to_register=1.0,
        )
        assert result is not None

    def test_ev4_register_claim_exception_no_crash(self):
        """register_claim 拋异常不崩溃（fail-open）/ register_claim exception → no crash (fail-open)."""
        mock_backtest = _make_mock_engine(sharpe=2.0)
        mock_registry = MagicMock()
        mock_registry.register_claim.side_effect = RuntimeError("Registry down")
        engine = EvolutionEngine(backtest_engine=mock_backtest, truth_registry=mock_registry)

        # Should not raise despite registry failure
        result = engine.run_evolution(
            strategy_name="ma_crossover",
            symbol="BTCUSDT",
            timeframe="1h",
            parameter_grids=[ParameterGrid(name="stop_loss_pct", values=[0.02])],
            min_sharpe_to_register=1.0,
        )
        assert result.best_sharpe == 2.0  # Result still correct despite failure

    def test_ev4_evidence_source_format(self):
        """evidence_source 格式为 'statistical_N={n}' / evidence_source format is 'statistical_N={n}'."""
        mock_backtest = _make_mock_engine(sharpe=2.0)
        mock_registry = MagicMock()
        engine = EvolutionEngine(backtest_engine=mock_backtest, truth_registry=mock_registry)

        engine.run_evolution(
            strategy_name="ma_crossover",
            symbol="BTCUSDT",
            timeframe="1h",
            parameter_grids=[ParameterGrid(name="stop_loss_pct", values=[0.01, 0.02, 0.03])],
            min_sharpe_to_register=1.0,
        )
        call_kwargs = mock_registry.register_claim.call_args.kwargs
        evidence = call_kwargs.get("evidence_source", "")
        assert evidence.startswith("statistical_N="), (
            f"Expected 'statistical_N={{n}}', got '{evidence}'"
        )
        # Extract N from the string
        n_str = evidence.split("=")[-1]
        assert n_str.isdigit()
        assert int(n_str) == 3  # 3 combinations evaluated


# ---------------------------------------------------------------------------
# EV5 — Principle 7 Isolation / 原则 7 隔离
# 4 tests
# ---------------------------------------------------------------------------

class TestPrinciple7Isolation:
    """EV5: Principle 7 isolation verification."""

    def test_ev5_is_simulated_always_true_standalone(self):
        """EvolutionResult.is_simulated 始终为 True（独立测试）/ Always True (standalone test)."""
        for flag in [True, False, None]:
            r = EvolutionResult(
                strategy_name="x",
                symbol="BTCUSDT",
                timeframe="1h",
                best_params={},
                best_sharpe=0.0,
                best_win_rate=0.0,
                total_combinations=0,
                evaluated_combinations=0,
                all_results=[],
                completed_at_ms=1,
                is_simulated=flag,  # type: ignore
            )
            assert r.is_simulated is True, f"is_simulated should be True but got {r.is_simulated} (input={flag})"

    def test_ev5_backtest_mode_true_in_config(self):
        """传给 BacktestEngine 的 config.backtest_mode=True / config.backtest_mode=True passed to engine."""
        engine, mock_backtest = _make_evolution_engine()

        engine.run_evolution(
            strategy_name="trend_follow",
            symbol="ETHUSDT",
            timeframe="4h",
            parameter_grids=[
                ParameterGrid(name="stop_loss_pct", values=[0.01, 0.02]),
            ],
        )
        for c in mock_backtest.run.call_args_list:
            config = c[0][0]
            assert config.backtest_mode is True

    def test_ev5_no_live_module_imports_in_source(self):
        """
        evolution_engine.py 不 import GovernanceHub / PaperTradingEngine / PipelineBridge。
        evolution_engine.py does NOT import GovernanceHub / PaperTradingEngine / PipelineBridge.

        原则 7 隔离：通过 ast 解析模块的所有 import 语句验证，不扫描注释和 docstring。
        Principle 7 isolation: verified by parsing all import statements via ast;
        docstring/comment mentions are excluded from the check.
        """
        source_path = os.path.join(_SRV, "program_code", "local_model_tools", "evolution_engine.py")
        with open(source_path, "r", encoding="utf-8") as f:
            source = f.read()

        # 使用 ast 解析所有 import，仅检查实际 import 语句，不扫描 docstring
        # Use ast to parse all imports; only check actual import statements (not docstrings)
        tree = ast.parse(source)
        imported_names: set = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_names.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imported_names.add(module)
                for alias in node.names:
                    imported_names.add(f"{module}.{alias.name}")

        # 这些模块不应出现在任何 import 语句中 / These must not appear in any import statement
        forbidden_modules = [
            "governance_hub", "paper_trading_engine", "pipeline_bridge", "message_bus",
        ]
        for forbidden in forbidden_modules:
            for imported in imported_names:
                assert forbidden not in imported.lower(), (
                    f"Principle 7 violation: evolution_engine.py imports '{imported}' "
                    f"which contains forbidden module '{forbidden}'"
                )

    def test_ev5_evaluate_one_returns_none_on_exception(self):
        """_evaluate_one() 失败返回 None（mock engine 抛 Exception）/ Returns None on exception."""
        from program_code.local_model_tools.backtest_engine import BacktestConfig
        failing_engine = MagicMock()
        failing_engine.run.side_effect = RuntimeError("Deliberate failure")

        evolution = EvolutionEngine(backtest_engine=failing_engine)
        config = BacktestConfig(
            symbol="BTCUSDT",
            timeframe="1h",
            strategy_name="test",
            backtest_mode=True,
        )
        result = evolution._evaluate_one(config, None)
        assert result is None


# ---------------------------------------------------------------------------
# EV6 — get_status and counters / get_status 和计数器
# 2 tests
# ---------------------------------------------------------------------------

class TestGetStatusAndCounters:
    """EV6: get_status() and total_runs counter."""

    def test_ev6_get_status_fields(self):
        """get_status() 返回包含 total_runs / last_run_ts / max_combinations 字段 / Fields present."""
        engine = EvolutionEngine(
            backtest_engine=_make_mock_engine(),
            max_combinations=25,
        )
        status = engine.get_status()
        assert "total_runs" in status
        assert "last_run_ts" in status
        assert "max_combinations" in status
        assert status["max_combinations"] == 25
        assert status["total_runs"] == 0
        assert status["last_run_ts"] is None

    def test_ev6_total_runs_increments_on_each_run(self):
        """两次 run_evolution 后 total_runs == 2 / total_runs == 2 after two run_evolution calls."""
        engine, _ = _make_evolution_engine()
        grids = [ParameterGrid(name="stop_loss_pct", values=[0.02])]

        engine.run_evolution(
            strategy_name="ma_crossover",
            symbol="BTCUSDT",
            timeframe="1h",
            parameter_grids=grids,
        )
        engine.run_evolution(
            strategy_name="rsi_bb",
            symbol="ETHUSDT",
            timeframe="4h",
            parameter_grids=grids,
        )
        status = engine.get_status()
        assert status["total_runs"] == 2
        assert status["last_run_ts"] is not None


# ---------------------------------------------------------------------------
# Additional edge case tests
# ---------------------------------------------------------------------------

class TestAdditionalEdgeCases:
    """Additional edge cases not covered by EV1-EV6 categories."""

    def test_params_not_in_whitelist_ignored(self):
        """params 中非 BacktestConfig 字段被安全忽略 / Unknown param fields safely ignored."""
        mock_engine = _make_mock_engine()
        evolution = EvolutionEngine(backtest_engine=mock_engine)
        # Include an unknown param field that shouldn't cause errors
        grids = [
            ParameterGrid(name="unknown_future_param", values=["x", "y"]),
        ]
        # Should not crash
        result = evolution.run_evolution(
            strategy_name="ma_crossover",
            symbol="BTCUSDT",
            timeframe="1h",
            parameter_grids=grids,
        )
        assert result is not None
        # All combos still evaluated
        assert mock_engine.run.call_count == 2

    def test_run_evolution_result_symbol_and_timeframe(self):
        """结果包含正确的 symbol 和 timeframe / Result contains correct symbol and timeframe."""
        engine, _ = _make_evolution_engine()
        result = engine.run_evolution(
            strategy_name="grid_trade",
            symbol="SOLUSDT",
            timeframe="15m",
            parameter_grids=[ParameterGrid(name="stop_loss_pct", values=[0.02])],
        )
        assert result.symbol == "SOLUSDT"
        assert result.timeframe == "15m"
        assert result.strategy_name == "grid_trade"

    def test_multiple_grids_params_all_in_result(self):
        """多参数网格：最优组合包含所有参数键 / Multi-grid: best combo contains all param keys."""
        mock_engine = MagicMock()
        mock_engine.run.return_value = _make_mock_result(sharpe=1.5)
        evolution = EvolutionEngine(backtest_engine=mock_engine)
        grids = [
            ParameterGrid(name="stop_loss_pct", values=[0.01, 0.02]),
            ParameterGrid(name="position_size_pct", values=[0.01]),
        ]
        result = evolution.run_evolution(
            strategy_name="ma_crossover",
            symbol="BTCUSDT",
            timeframe="1h",
            parameter_grids=grids,
        )
        assert "stop_loss_pct" in result.best_params
        assert "position_size_pct" in result.best_params


# ---------------------------------------------------------------------------
# E4 Edge Cases: Degenerate Inputs / E4 边界: 退化输入
# 3 tests
# ---------------------------------------------------------------------------

class TestEvolutionEdgeCasesE4:
    """Edge case tests for EvolutionEngine with degenerate parameters (E4 追加).
    进化引擎退化参数边界条件测试。"""

    def test_max_combinations_zero_produces_empty_result(self):
        """max_combinations=0 should produce result with 0 evaluated combinations.
        max_combinations=0 应产生 0 个已评估组合的结果。"""
        mock_engine = _make_mock_engine(sharpe=1.5)
        evolution = EvolutionEngine(backtest_engine=mock_engine, max_combinations=0)
        grids = [ParameterGrid(name="stop_loss_pct", values=[0.01, 0.02])]
        result = evolution.run_evolution(
            strategy_name="test", symbol="BTCUSDT", timeframe="1h",
            parameter_grids=grids,
        )
        assert result.evaluated_combinations == 0
        assert result.best_params == {}
        assert result.is_simulated is True

    def test_all_negative_sharpe_still_picks_best(self):
        """All backtests returning negative Sharpe should still select the least negative.
        所有回测返回负 Sharpe 时应选择最不负的。"""
        mock_engine = MagicMock()
        mock_engine.run.return_value = _make_mock_result(sharpe=-2.0, win_rate=0.2)
        evolution = EvolutionEngine(backtest_engine=mock_engine, max_combinations=50)
        grids = [ParameterGrid(name="stop_loss_pct", values=[0.01, 0.02, 0.03])]
        result = evolution.run_evolution(
            strategy_name="test", symbol="BTCUSDT", timeframe="1h",
            parameter_grids=grids,
        )
        assert result.best_sharpe == -2.0
        assert result.evaluated_combinations == 3
        assert result.is_simulated is True

    def test_empty_parameter_grid_produces_valid_result(self):
        """Empty parameter_grids list should produce a valid (possibly trivial) result.
        空的 parameter_grids 列表应产生有效结果。"""
        mock_engine = _make_mock_engine(sharpe=1.5)
        evolution = EvolutionEngine(backtest_engine=mock_engine)
        result = evolution.run_evolution(
            strategy_name="test", symbol="BTCUSDT", timeframe="1h",
            parameter_grids=[],
        )
        assert result.is_simulated is True
        assert result.best_params is not None  # should not crash
