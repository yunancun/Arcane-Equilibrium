"""
Tests for evolution_auto_scheduler.py — Phase 3 Batch 3C-2 + 3C-3
週進化排程器 + 小時清理排程器測試

Coverage targets / 覆蓋目標：
  - Scheduler startup idempotency / 啟動冪等性
  - Daemon thread configuration / 守護線程配置
  - Singleton behaviour / 單例行為
  - Evolution cycle (all strategies called, fail-open on partial failure, all-fail safe)
  - Default parameter grids (non-empty for all DEFAULT_STRATEGIES)
  - Principle 7: engine always called with keyword args that include symbol/timeframe
  - Expiry cycle (ledger.expire_stale_hypotheses called, None-safe, fail-open)
  - Scheduling math (seconds_until positive, >= 60s)
  - Status dict shape
"""
from __future__ import annotations

import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers / 幫助函數
# ---------------------------------------------------------------------------

def _make_scheduler(**kwargs):
    """
    Build a fresh EvolutionScheduler with all deps mocked out.
    創建帶 mock 依賴的新 EvolutionScheduler 實例。
    """
    # Import inside function to avoid module-level import ordering issues
    from program_code.exchange_connectors.bybit_connector.control_api_v1.app.evolution_auto_scheduler import (
        EvolutionScheduler,
    )
    return EvolutionScheduler(**kwargs)


def _make_mock_engine(raises_for: set | None = None):
    """
    Build a MagicMock EvolutionEngine.
    構建 MagicMock EvolutionEngine。

    Args:
        raises_for — set of strategy names that should raise / 應拋出異常的策略集合
    """
    engine = MagicMock()

    def _run_evolution(*, strategy_name, symbol, timeframe, parameter_grids, **kwargs):
        if raises_for and strategy_name in raises_for:
            raise RuntimeError(f"simulated failure for {strategy_name}")
        result = MagicMock()
        result.best_sharpe = 1.2
        result.evaluated_combinations = 6
        return result

    engine.run_evolution = MagicMock(side_effect=_run_evolution)
    return engine


def _make_mock_ledger(expired_count: int = 3, raises: bool = False):
    """
    Build a MagicMock ExperimentLedger.
    構建 MagicMock ExperimentLedger。
    """
    ledger = MagicMock()
    if raises:
        ledger.expire_stale_hypotheses = MagicMock(
            side_effect=RuntimeError("simulated ledger failure")
        )
    else:
        ledger.expire_stale_hypotheses = MagicMock(return_value=expired_count)
    return ledger


# ---------------------------------------------------------------------------
# Imports once after helper definitions
# ---------------------------------------------------------------------------

from program_code.exchange_connectors.bybit_connector.control_api_v1.app.evolution_auto_scheduler import (  # noqa: E402
    EvolutionScheduler,
    get_scheduler,
    start_scheduler,
)


# ---------------------------------------------------------------------------
# 1. Scheduler startup tests / 排程器啟動測試
# ---------------------------------------------------------------------------

class TestSchedulerStartup:

    def test_start_is_idempotent(self):
        """
        多次調用 start() 不應創建重複線程。
        Calling start() multiple times must not create duplicate threads.
        """
        engine = _make_mock_engine()
        ledger = _make_mock_ledger()
        sched = _make_scheduler(evolution_engine=engine, experiment_ledger=ledger)

        # Record thread count before / 記錄啟動前線程數
        before = threading.active_count()
        sched.start()
        after_first = threading.active_count()

        # Second start() must not add more threads / 第二次 start() 不應增加線程數
        sched.start()
        after_second = threading.active_count()

        assert after_first == after_second, (
            "Duplicate threads created on second start() call"
        )
        assert after_first > before, "start() did not create any threads"

    def test_daemon_threads_are_daemon(self):
        """
        兩個後台線程必須是 daemon=True（不阻塞進程退出）。
        Both background threads must have daemon=True (do not block process exit).
        """
        engine = _make_mock_engine()
        ledger = _make_mock_ledger()
        sched = _make_scheduler(evolution_engine=engine, experiment_ledger=ledger)

        # Patch Thread to capture created threads / 補丁 Thread 以捕獲創建的線程
        created_threads: list[threading.Thread] = []
        original_thread = threading.Thread

        def _capture_thread(*args, **kwargs):
            t = original_thread(*args, **kwargs)
            created_threads.append(t)
            return t

        with patch("threading.Thread", side_effect=_capture_thread):
            sched2 = _make_scheduler(evolution_engine=engine, experiment_ledger=ledger)
            sched2.start()

        assert len(created_threads) == 2, f"Expected 2 threads, got {len(created_threads)}"
        for t in created_threads:
            assert t.daemon is True, f"Thread {t.name} is not a daemon thread"

    def test_start_scheduler_singleton(self):
        """
        start_scheduler() 多次調用應返回同一個實例。
        Repeated calls to start_scheduler() must return the same instance.
        """
        # Reset module-level singleton between tests
        import program_code.exchange_connectors.bybit_connector.control_api_v1.app.evolution_auto_scheduler as mod
        original = mod._scheduler
        mod._scheduler = None  # Reset singleton

        try:
            engine = _make_mock_engine()
            ledger = _make_mock_ledger()
            s1 = start_scheduler(evolution_engine=engine, experiment_ledger=ledger)
            s2 = start_scheduler(evolution_engine=engine, experiment_ledger=ledger)
            assert s1 is s2, "start_scheduler() returned different instances"
        finally:
            mod._scheduler = original  # Restore


# ---------------------------------------------------------------------------
# 2. Evolution cycle tests / 進化週期測試
# ---------------------------------------------------------------------------

class TestEvolutionCycle:

    def test_run_evolution_cycle_calls_engine(self):
        """
        _run_evolution_cycle() 應對 DEFAULT_STRATEGIES 中每個策略調用 engine.run_evolution()。
        _run_evolution_cycle() must call engine.run_evolution() for each strategy in DEFAULT_STRATEGIES.
        """
        engine = _make_mock_engine()
        sched = _make_scheduler(evolution_engine=engine, experiment_ledger=_make_mock_ledger())
        sched._run_evolution_cycle()

        called_strategies = {
            call.kwargs["strategy_name"]
            for call in engine.run_evolution.call_args_list
        }
        assert called_strategies == set(EvolutionScheduler.DEFAULT_STRATEGIES), (
            f"Not all strategies called. Missing: "
            f"{set(EvolutionScheduler.DEFAULT_STRATEGIES) - called_strategies}"
        )

    def test_run_evolution_cycle_fail_open_partial(self):
        """
        某一策略拋出異常時，其他策略仍應繼續運行（fail-open）。
        If one strategy raises, others must still execute (fail-open).
        """
        # Only "grid" raises; others succeed
        engine = _make_mock_engine(raises_for={"grid"})
        sched = _make_scheduler(evolution_engine=engine, experiment_ledger=_make_mock_ledger())
        sched._run_evolution_cycle()  # Must not raise

        called_strategies = {
            call.kwargs["strategy_name"]
            for call in engine.run_evolution.call_args_list
        }
        remaining = set(EvolutionScheduler.DEFAULT_STRATEGIES) - {"grid"}
        for s in remaining:
            assert s in called_strategies, f"Strategy {s!r} was not called after partial failure"

    def test_run_evolution_cycle_all_fail(self):
        """
        所有策略均拋出異常時，不應有異常傳播（全 fail-open）。
        All strategies failing must not propagate any exception (full fail-open).
        """
        engine = _make_mock_engine(raises_for=set(EvolutionScheduler.DEFAULT_STRATEGIES))
        sched = _make_scheduler(evolution_engine=engine, experiment_ledger=_make_mock_ledger())
        # Must not raise
        sched._run_evolution_cycle()

    def test_default_grids_not_empty(self):
        """
        _default_grids_for_strategy() 對所有 DEFAULT_STRATEGIES 應返回非空列表。
        _default_grids_for_strategy() must return non-empty list for all DEFAULT_STRATEGIES.
        """
        # Use a fresh scheduler; engine may be None since we only call _default_grids_for_strategy
        sched = _make_scheduler()
        for strategy in EvolutionScheduler.DEFAULT_STRATEGIES:
            grids = sched._default_grids_for_strategy(strategy)
            assert grids, f"Empty grid returned for strategy {strategy!r}"
            assert len(grids) > 0

    def test_backtest_mode_keyword_args_present(self):
        """
        進化引擎調用時必須攜帶 symbol 和 timeframe 關鍵字參數（原則 7 沙箱隔離）。
        Engine calls must include symbol and timeframe keyword args (Principle 7 sandbox).
        """
        engine = _make_mock_engine()
        sched = _make_scheduler(
            evolution_engine=engine,
            experiment_ledger=_make_mock_ledger(),
        )
        sched._run_evolution_cycle()

        for call in engine.run_evolution.call_args_list:
            assert "symbol" in call.kwargs, "symbol kwarg missing in run_evolution() call"
            assert "timeframe" in call.kwargs, "timeframe kwarg missing in run_evolution() call"
            # Validate values are the defaults / 驗證使用預設值
            assert call.kwargs["symbol"] == EvolutionScheduler.DEFAULT_SYMBOL
            assert call.kwargs["timeframe"] == EvolutionScheduler.DEFAULT_TIMEFRAME

    def test_evolution_cycle_increments_run_counter(self):
        """
        成功完成週期後 _evolution_runs 計數器應遞增。
        After a successful cycle, _evolution_runs counter must increment.
        """
        engine = _make_mock_engine()
        sched = _make_scheduler(evolution_engine=engine, experiment_ledger=_make_mock_ledger())
        assert sched._evolution_runs == 0
        sched._run_evolution_cycle()
        assert sched._evolution_runs == 1

    def test_evolution_cycle_engine_none_no_crash(self):
        """
        EvolutionEngine 不可用時週期應靜默跳過（fail-open）。
        When EvolutionEngine is unavailable, cycle must skip silently (fail-open).
        """
        sched = _make_scheduler()
        # Force _engine to None and patch _get_engine to return None
        sched._engine = None

        with patch.object(sched, "_get_engine", return_value=None):
            sched._run_evolution_cycle()  # Must not raise


# ---------------------------------------------------------------------------
# 3. Expiry cycle tests / 清理週期測試
# ---------------------------------------------------------------------------

class TestExpiryCycle:

    def test_run_expiry_cycle_calls_expire(self):
        """
        _run_expiry_cycle() 應調用 ledger.expire_stale_hypotheses()。
        _run_expiry_cycle() must call ledger.expire_stale_hypotheses().
        """
        ledger = _make_mock_ledger(expired_count=5)
        sched = _make_scheduler(
            evolution_engine=_make_mock_engine(),
            experiment_ledger=ledger,
        )
        sched._run_expiry_cycle()
        ledger.expire_stale_hypotheses.assert_called_once()

    def test_run_expiry_cycle_ledger_none(self):
        """
        ledger 為 None 時清理週期應靜默返回（不崩潰）。
        When ledger is None, expiry cycle must return silently (no crash).
        """
        sched = _make_scheduler()
        sched._ledger = None
        with patch.object(sched, "_get_ledger", return_value=None):
            sched._run_expiry_cycle()  # Must not raise

    def test_run_expiry_cycle_fail_open(self):
        """
        ledger.expire_stale_hypotheses() 拋出異常時，不應傳播異常（fail-open）。
        Exception from expire_stale_hypotheses() must not propagate (fail-open).
        """
        ledger = _make_mock_ledger(raises=True)
        sched = _make_scheduler(
            evolution_engine=_make_mock_engine(),
            experiment_ledger=ledger,
        )
        sched._run_expiry_cycle()  # Must not raise

    def test_run_expiry_cycle_increments_run_counter(self):
        """
        成功清理後 _expiry_runs 計數器應遞增。
        After successful expiry, _expiry_runs counter must increment.
        """
        ledger = _make_mock_ledger(expired_count=2)
        sched = _make_scheduler(
            evolution_engine=_make_mock_engine(),
            experiment_ledger=ledger,
        )
        assert sched._expiry_runs == 0
        sched._run_expiry_cycle()
        assert sched._expiry_runs == 1


# ---------------------------------------------------------------------------
# 4. Scheduling logic tests / 排程計算測試
# ---------------------------------------------------------------------------

class TestSchedulingLogic:

    def test_seconds_until_next_sunday_positive(self):
        """
        _seconds_until_next_sunday_0030_utc() 應始終返回正數。
        _seconds_until_next_sunday_0030_utc() must always return a positive value.
        """
        sched = _make_scheduler()
        result = sched._seconds_until_next_sunday_0030_utc()
        assert result > 0, f"Expected positive seconds, got {result}"

    def test_seconds_until_next_sunday_min_60s(self):
        """
        _seconds_until_next_sunday_0030_utc() 應始終返回 >= 60.0。
        _seconds_until_next_sunday_0030_utc() must always return >= 60.0.
        """
        sched = _make_scheduler()
        result = sched._seconds_until_next_sunday_0030_utc()
        assert result >= 60.0, f"Expected >= 60s, got {result}"

    def test_seconds_until_next_sunday_max_one_week(self):
        """
        _seconds_until_next_sunday_0030_utc() 應始終返回 <= 7 天的秒數。
        Must always return <= 7 days in seconds.
        """
        sched = _make_scheduler()
        result = sched._seconds_until_next_sunday_0030_utc()
        one_week_s = 7 * 24 * 3600
        assert result <= one_week_s + 1, f"Expected <= 1 week, got {result}"

    def test_get_status_returns_dict(self):
        """
        get_status() 應返回包含必要鍵的字典。
        get_status() must return a dict with expected keys.
        """
        engine = _make_mock_engine()
        ledger = _make_mock_ledger()
        sched = _make_scheduler(evolution_engine=engine, experiment_ledger=ledger)

        status = sched.get_status()

        assert isinstance(status, dict), "get_status() must return a dict"

        expected_keys = {
            "started",
            "default_strategies",
            "default_symbol",
            "default_timeframe",
            "evolution_interval_s",
            "expiry_interval_s",
            "evolution_runs",
            "evolution_failures",
            "expiry_runs",
            "last_evolution_ts",
            "last_expiry_ts",
        }
        missing = expected_keys - status.keys()
        assert not missing, f"get_status() missing keys: {missing}"

    def test_get_status_started_false_before_start(self):
        """
        調用 start() 前 status['started'] 應為 False。
        status['started'] must be False before start() is called.
        """
        sched = _make_scheduler()
        assert sched.get_status()["started"] is False

    def test_get_status_started_true_after_start(self):
        """
        調用 start() 後 status['started'] 應為 True。
        status['started'] must be True after start() is called.
        """
        engine = _make_mock_engine()
        ledger = _make_mock_ledger()
        sched = _make_scheduler(evolution_engine=engine, experiment_ledger=ledger)
        sched.start()
        assert sched.get_status()["started"] is True

    def test_interruptible_sleep_completes(self):
        """
        _interruptible_sleep() 應在近似正確時間後完成（允許小誤差）。
        _interruptible_sleep() must complete after approximately the given duration.
        """
        sched = _make_scheduler()
        duration = 0.05  # 50ms for fast test / 50ms 快速測試
        t0 = time.time()
        sched._interruptible_sleep(duration)
        elapsed = time.time() - t0
        assert elapsed >= duration * 0.8, f"Sleep ended too early: elapsed={elapsed:.3f}s"
