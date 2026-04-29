from __future__ import annotations

"""
Phase 3 Batch 3C — Evolution Auto-Scheduler
策略進化自動排程器

MODULE_NOTE (中文):
  Phase 3 Batch 3C 後台排程器：週期性策略進化 + 假設過期清理
  - EvolutionScheduler: 每週日 UTC 00:30 自動執行策略參數優化（原則 7 隔離）
  - 每小時自動清理過期假設（ExperimentLedger.expire_stale_hypotheses()）
  - 所有任務 fail-open：任何失敗不阻斷主交易路徑

  原則對應：
  - 原則 7 隔離：EvolutionEngine 永遠以 backtest_mode=True 運行，不修改 live 配置
  - 原則 12 持續進化：週期性學習管線全自動化
  - 原則 14 零外部成本可運行：使用 daemon 線程，不依賴外部排程服務

MODULE_NOTE (English):
  Phase 3 Batch 3C background scheduler: periodic strategy evolution + hypothesis expiry.
  - EvolutionScheduler: auto-runs strategy optimization every Sunday 00:30 UTC (Principle 7 isolated)
  - Hourly auto-expiry of stale hypotheses (ExperimentLedger.expire_stale_hypotheses())
  - All tasks fail-open: any failure must not interrupt main trading pipeline

  Principle alignment:
  - Principle 7: EvolutionEngine always runs with backtest_mode=True, no live config modification
  - Principle 12: Periodic learning pipeline fully automated
  - Principle 14: Uses daemon threads; no external scheduling service dependency
"""

import datetime
import fcntl
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── sys.path 注入（複用 backtest_routes.py 的 5 級目錄上溯模式）──────────────
# sys.path injection — 5-level traversal to reach program_code/ root.
# Matches backtest_routes.py to ensure consistent import paths across app modules.
# 與 backtest_routes.py 保持一致，確保 import 路徑穩定。
_app_dir = os.path.dirname(os.path.abspath(__file__))           # app/
_control_api_dir = os.path.dirname(_app_dir)                     # control_api_v1/
_bybit_connector_dir = os.path.dirname(_control_api_dir)         # bybit_connector/
_exchange_connectors_dir = os.path.dirname(_bybit_connector_dir) # exchange_connectors/
_program_code_dir = os.path.dirname(_exchange_connectors_dir)    # program_code/
if _program_code_dir not in sys.path:
    sys.path.insert(0, _program_code_dir)

logger = logging.getLogger(__name__)


class EvolutionScheduler:
    """
    後台排程器，管理兩個週期性任務：
    1. 週進化（每週日 00:30 UTC）— 使用 EvolutionEngine 進行策略網格搜索
    2. 小時清理（每小時）— 清理 ExperimentLedger 中的過期假設

    Background scheduler managing two periodic tasks:
    1. Weekly evolution (Sunday 00:30 UTC) — EvolutionEngine grid search
    2. Hourly cleanup (every hour) — expire stale hypotheses in ExperimentLedger

    原則 7 隔離：EvolutionEngine 永遠以 backtest_mode=True 運行，不修改 live 配置。
    Principle 7: EvolutionEngine always runs with backtest_mode=True, never modifies live config.
    """

    # 預設策略清單（若外部未注入，使用此列表）
    # Default strategy list (used if not externally injected)
    DEFAULT_STRATEGIES = ["ma_crossover", "grid", "bb_reversion", "bb_breakout", "funding_arb"]

    # 預設 symbol（最常見交易對）/ Default symbol (most common pair)
    DEFAULT_SYMBOL = "BTCUSDT"
    DEFAULT_TIMEFRAME = "1h"

    def __init__(
        self,
        evolution_engine=None,          # EvolutionEngine instance or None (lazy import)
        experiment_ledger=None,          # ExperimentLedger instance or None (lazy import)
        truth_registry=None,             # TruthSourceRegistry instance or None
        evolution_interval_s: float = 7 * 24 * 3600,  # weekly = 604800s
        expiry_interval_s: float = 3600.0,              # hourly
    ) -> None:
        """
        初始化排程器，注入依賴或延遲到首次使用時懶加載。
        Initialise scheduler; inject dependencies or lazy-load on first use.

        Args:
            evolution_engine    — EvolutionEngine 實例，None 時懶加載 / instance or None (lazy)
            experiment_ledger   — ExperimentLedger 實例，None 時懶加載 / instance or None (lazy)
            truth_registry      — TruthSourceRegistry 實例，可為 None / may be None
            evolution_interval_s — 進化週期秒數（預設 7 天）/ evolution cycle seconds (default 7d)
            expiry_interval_s    — 清理週期秒數（預設 1 小時）/ expiry cycle seconds (default 1h)
        """
        # 注入的依賴（或 None，懶加載在首次使用時）
        # Injected deps (or None; lazy-loaded on first use)
        self._engine = evolution_engine
        self._ledger = experiment_ledger
        self._truth_registry = truth_registry

        # 週期設定 / Interval configuration
        self._evolution_interval_s = evolution_interval_s
        self._expiry_interval_s = expiry_interval_s

        # 啟動狀態保護鎖（確保冪等 start()）
        # Lock protecting started flag (ensures idempotent start())
        self._lock = threading.Lock()
        self._started: bool = False

        # 統計計數器（線程安全，由 _lock 保護）
        # Stat counters (thread-safe, protected by _lock)
        self._evolution_runs: int = 0
        self._evolution_failures: int = 0
        self._expiry_runs: int = 0
        self._last_evolution_ts: Optional[float] = None
        self._last_expiry_ts: Optional[float] = None

    # ── Startup / 啟動 ─────────────────────────────────────────────────────

    def start(self) -> None:
        """
        啟動兩個後台守護線程（冪等，多次調用安全）。
        Start two background daemon threads (idempotent, safe to call multiple times).

        若已啟動則靜默返回，不重複啟動線程。
        If already started, returns silently — no duplicate threads are created.
        """
        with self._lock:
            if self._started:
                # 冪等：已啟動則跳過 / Idempotent: skip if already running
                return
            self._started = True

        # 週進化線程 / Weekly evolution thread
        evo_thread = threading.Thread(
            target=self._evolution_loop,
            daemon=True,
            name="evolution-scheduler",
        )
        evo_thread.start()

        # 小時清理線程 / Hourly expiry thread
        expiry_thread = threading.Thread(
            target=self._expiry_loop,
            daemon=True,
            name="expiry-scheduler",
        )
        expiry_thread.start()

        logger.info(
            "EvolutionScheduler started: weekly evolution + hourly expiry "
            "/ 排程器已啟動：週進化 + 小時清理"
        )

    # ── Evolution loop / 週進化循環 ────────────────────────────────────────

    def _evolution_loop(self) -> None:
        """
        週進化守護循環。計算距離下個週日 00:30 UTC 的等待時間，睡眠後執行。
        Weekly evolution daemon loop. Computes sleep until next Sunday 00:30 UTC, then runs.

        使用 1 秒可中斷睡眠（daemon 線程，程序退出時自動終止）。
        Uses 1s interruptible sleep (daemon thread, auto-terminates on program exit).
        """
        while True:
            sleep_s = self._seconds_until_next_sunday_0030_utc()
            logger.info(
                "EvolutionScheduler: next evolution in %.0fs (%.1fh) "
                "/ 下次進化將在 %.0f 秒後（%.1f 小時）",
                sleep_s, sleep_s / 3600, sleep_s, sleep_s / 3600,
            )
            self._interruptible_sleep(sleep_s)
            self._run_evolution_cycle()

    def _seconds_until_next_sunday_0030_utc(self) -> float:
        """
        計算距下個週日 UTC 00:30 的秒數（最短 60s，防止緊密循環）。
        Compute seconds until next Sunday UTC 00:30 (min 60s to prevent tight loop).

        weekday() 返回值：Mon=0 ... Sun=6
        weekday() values: Mon=0 ... Sun=6
        """
        now = datetime.datetime.utcnow()
        # 距週日的天數 / Days until Sunday
        days_until_sunday = (6 - now.weekday()) % 7
        # 若今天是週日且 00:30 已過，則等下週 / If today is Sunday but past 00:30, wait 7 days
        if days_until_sunday == 0 and (now.hour, now.minute) >= (0, 30):
            days_until_sunday = 7
        target = now.replace(hour=0, minute=30, second=0, microsecond=0) + datetime.timedelta(
            days=days_until_sunday
        )
        delta = (target - now).total_seconds()
        # 最短 60s 防止緊密循環 / min 60s to prevent tight loop
        return max(60.0, delta)

    def _run_evolution_cycle(self) -> None:
        """
        執行一次策略進化週期，對所有預設策略運行網格搜索。
        Run one strategy evolution cycle, grid-searching all default strategies.

        fail-open：任何單一策略失敗不影響其他策略繼續運行。
        fail-open: single strategy failure does not affect remaining strategies.

        原則 7：所有評估在 BacktestEngine 沙箱中，不修改 live 配置。
        Principle 7: all evaluations in BacktestEngine sandbox, no live config modification.
        """
        logger.info(
            "EvolutionScheduler: starting weekly evolution cycle / 週進化週期開始"
        )
        engine = self._get_engine()
        if engine is None:
            logger.warning(
                "EvolutionScheduler: EvolutionEngine not available (fail-open) "
                "/ EvolutionEngine 不可用，跳過本次進化"
            )
            return

        for strategy in self.DEFAULT_STRATEGIES:
            try:
                grids = self._default_grids_for_strategy(strategy)
                result = engine.run_evolution(
                    strategy_name=strategy,
                    symbol=self.DEFAULT_SYMBOL,
                    timeframe=self.DEFAULT_TIMEFRAME,
                    parameter_grids=grids,
                    min_sharpe_to_register=1.0,
                )
                logger.info(
                    "EvolutionScheduler: strategy=%s best_sharpe=%.2f evaluated=%d "
                    "/ 進化完成 strategy=%s best_sharpe=%.2f evaluated=%d",
                    strategy, result.best_sharpe, result.evaluated_combinations,
                    strategy, result.best_sharpe, result.evaluated_combinations,
                )
            except Exception as e:
                # fail-open：跳過此策略，繼續下一個 / fail-open: skip this strategy, continue
                logger.warning(
                    "EvolutionScheduler: strategy=%s failed (fail-open): %s "
                    "/ 策略 %s 進化失敗（跳過）：%s",
                    strategy, e, strategy, e,
                )
                with self._lock:
                    self._evolution_failures += 1

        with self._lock:
            self._evolution_runs += 1
            self._last_evolution_ts = time.time()

        logger.info(
            "EvolutionScheduler: evolution cycle complete / 週進化週期完成"
        )

    def _default_grids_for_strategy(self, strategy: str) -> List[Any]:
        """
        為指定策略返回預設參數搜索網格（每策略最多 2-3 個參數，組合數 ≤ 50）。
        Return default parameter search grids for the given strategy (max 2-3 params, combos <= 50).

        設計原則 5：保持組合數合理，防止資源耗盡。
        Principle 5: Keep combination count reasonable to prevent resource exhaustion.
        """
        # 懶加載 ParameterGrid（避免頂層循環導入）
        # Lazy import ParameterGrid to avoid top-level circular import
        from local_model_tools.evolution_engine import ParameterGrid  # noqa: PLC0415

        _grids: Dict[str, List[ParameterGrid]] = {
            "ma_crossover": [
                ParameterGrid(name="stop_loss_pct", values=[0.02, 0.03, 0.05]),
                ParameterGrid(name="take_profit_pct", values=[0.04, 0.06, 0.09]),
            ],
            "grid": [
                ParameterGrid(name="grid_spacing_pct", values=[0.005, 0.01, 0.02]),
                ParameterGrid(name="stop_loss_pct", values=[0.05, 0.08]),
            ],
            "bb_reversion": [
                ParameterGrid(name="stop_loss_pct", values=[0.02, 0.03, 0.04]),
                ParameterGrid(name="take_profit_pct", values=[0.03, 0.05, 0.07]),
            ],
            "bb_breakout": [
                ParameterGrid(name="stop_loss_pct", values=[0.02, 0.03, 0.05]),
                ParameterGrid(name="take_profit_pct", values=[0.04, 0.06, 0.09]),
            ],
            "funding_arb": [
                ParameterGrid(name="stop_loss_pct", values=[0.01, 0.02, 0.03]),
                ParameterGrid(name="take_profit_pct", values=[0.005, 0.01, 0.02]),
            ],
        }
        # 未知策略返回通用網格（單參數，確保 <= 50 組合）
        # Unknown strategies get a generic single-param grid (ensures <= 50 combos)
        return _grids.get(
            strategy,
            [ParameterGrid(name="stop_loss_pct", values=[0.02, 0.03, 0.05])],
        )

    # ── Expiry loop / 小時清理循環 ─────────────────────────────────────────

    def _expiry_loop(self) -> None:
        """
        小時清理守護循環，每小時調用 expire_stale_hypotheses()。
        Hourly cleanup daemon loop, calls expire_stale_hypotheses() every hour.

        使用 1 秒可中斷睡眠（daemon 線程，程序退出時自動終止）。
        Uses 1s interruptible sleep (daemon thread, auto-terminates on program exit).
        """
        while True:
            self._interruptible_sleep(self._expiry_interval_s)
            self._run_expiry_cycle()

    def _run_expiry_cycle(self) -> None:
        """
        執行一次過期假設清理（fail-open）。
        Run one stale hypothesis expiry cycle (fail-open).

        若 ledger 不可用，靜默返回；若 expire 失敗，記錄 warning 並繼續。
        If ledger unavailable, return silently; if expire fails, log warning and continue.
        """
        try:
            ledger = self._get_ledger()
            if ledger is None:
                # 無 ledger 可用，靜默跳過 / No ledger available, skip silently
                return
            expired = ledger.expire_stale_hypotheses()
            if expired > 0:
                logger.info(
                    "EvolutionScheduler: expired %d stale hypotheses / 清理 %d 個過期假設",
                    expired, expired,
                )
        except Exception as e:
            # fail-open：清理失敗不阻斷主流程 / fail-open: expiry failure does not block main flow
            logger.warning(
                "EvolutionScheduler: expiry failed (fail-open): %s / 過期清理失敗（跳過）：%s",
                e, e,
            )

        with self._lock:
            self._expiry_runs += 1
            self._last_expiry_ts = time.time()

    # ── Lazy dependency resolution / 懶加載依賴 ──────────────────────────

    def _get_engine(self):
        """
        懶加載 EvolutionEngine 實例（避免循環依賴，fail-open）。
        Lazy-load EvolutionEngine instance (avoid circular imports, fail-open).

        若注入了外部實例則直接使用；否則從 local_model_tools 動態導入。
        Use injected instance if provided; otherwise dynamically import from local_model_tools.
        """
        if self._engine is not None:
            return self._engine
        try:
            from local_model_tools.evolution_engine import EvolutionEngine  # noqa: PLC0415
            self._engine = EvolutionEngine(truth_registry=self._truth_registry)
            return self._engine
        except Exception as e:
            # fail-open：無法加載引擎不阻斷程序 / fail-open: engine load failure is non-fatal
            logger.warning(
                "EvolutionScheduler: failed to load EvolutionEngine (fail-open): %s "
                "/ 無法加載 EvolutionEngine（跳過）：%s",
                e, e,
            )
            return None

    def _get_ledger(self):
        """
        懶加載 ExperimentLedger 單例（避免循環依賴）。
        Lazy-load ExperimentLedger singleton (avoid circular imports).

        首先嘗試使用注入的實例，否則通過 experiment_routes 的工廠函數獲取全局單例。
        Use injected instance first; otherwise obtain global singleton via experiment_routes factory.
        """
        if self._ledger is not None:
            return self._ledger
        try:
            from .experiment_routes import get_experiment_ledger  # noqa: PLC0415
            return get_experiment_ledger()
        except Exception as e:
            # fail-open：無法加載 ledger 不阻斷程序 / fail-open: ledger load failure is non-fatal
            logger.warning(
                "EvolutionScheduler: failed to load ExperimentLedger (fail-open): %s "
                "/ 無法加載 ExperimentLedger（跳過）：%s",
                e, e,
            )
            return None

    # ── Utilities / 工具方法 ───────────────────────────────────────────────

    def _interruptible_sleep(self, seconds: float) -> None:
        """
        以 1 秒為單位分段睡眠，允許 daemon 線程在程序退出時優雅終止。
        Sleep in 1s chunks, allowing daemon thread to terminate cleanly on program exit.

        這比單次 time.sleep(seconds) 更友好，避免長時間阻塞 GIL。
        Preferred over single time.sleep(seconds) — avoids prolonged GIL hold.
        """
        remaining = seconds
        while remaining > 0:
            time.sleep(min(1.0, remaining))
            remaining -= 1.0

    # ── Status / 狀態查詢 ─────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """
        返回排程器當前狀態字典，供監控端點使用。
        Return current scheduler status dict for monitoring endpoints.

        所有字段含義雙語標注。
        All fields annotated bilingually.
        """
        with self._lock:
            return {
                # 排程器是否已啟動 / Whether scheduler has been started
                "started": self._started,
                # 默認策略清單 / Default strategy list
                "default_strategies": self.DEFAULT_STRATEGIES,
                # 默認交易對 / Default trading pair
                "default_symbol": self.DEFAULT_SYMBOL,
                # 默認時間框架 / Default timeframe
                "default_timeframe": self.DEFAULT_TIMEFRAME,
                # 週進化週期秒數 / Weekly evolution interval in seconds
                "evolution_interval_s": self._evolution_interval_s,
                # 小時清理週期秒數 / Hourly expiry interval in seconds
                "expiry_interval_s": self._expiry_interval_s,
                # 完成的週進化次數 / Completed evolution cycles
                "evolution_runs": self._evolution_runs,
                # 週進化失敗的策略次數 / Failed strategy evaluations in evolution
                "evolution_failures": self._evolution_failures,
                # 完成的清理次數 / Completed expiry cycles
                "expiry_runs": self._expiry_runs,
                # 最近一次週進化完成時間（Unix 秒，None 表示尚未運行）
                # Last evolution completion time (Unix seconds, None = not yet run)
                "last_evolution_ts": self._last_evolution_ts,
                # 最近一次清理完成時間（Unix 秒，None 表示尚未運行）
                # Last expiry completion time (Unix seconds, None = not yet run)
                "last_expiry_ts": self._last_expiry_ts,
            }


# =============================================================================
# Module-level singleton / 模塊級單例
# =============================================================================

_scheduler: Optional[EvolutionScheduler] = None
_scheduler_lock = threading.Lock()
_LEADER_LOCK_FD: Optional[int] = None
_LEADER_LOCK_PATH: Optional[str] = None


def _leader_lock_path() -> Path:
    """Leader lock path under OPENCLAW_DATA_DIR. / leader 鎖檔路徑。"""
    data_dir = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")
    return Path(data_dir) / "evolution_scheduler.leader.lock"


def _acquire_leader_lock() -> bool:
    """
    Single-host leader election for multi-worker uvicorn startup.
    多 worker 啟動時的單機 leader 選舉。
    """
    global _LEADER_LOCK_FD, _LEADER_LOCK_PATH
    if _LEADER_LOCK_FD is not None:
        return True
    if os.environ.get("OPENCLAW_EVOLUTION_SCHEDULER_LEADER") == "0":
        logger.info(
            "EvolutionScheduler[pid=%d]: forced non-leader by env / "
            "由環境變數強制為非 leader",
            os.getpid(),
        )
        return False

    lock_path = _leader_lock_path()
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning(
            "EvolutionScheduler[pid=%d]: cannot create lock parent %s (%s), non-leader",
            os.getpid(),
            lock_path,
            exc,
        )
        return False

    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    except OSError as exc:
        logger.warning(
            "EvolutionScheduler[pid=%d]: cannot open lock %s (%s), non-leader",
            os.getpid(),
            lock_path,
            exc,
        )
        return False

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError):
        os.close(fd)
        logger.info(
            "EvolutionScheduler[pid=%d]: non-leader (lock held at %s)",
            os.getpid(),
            lock_path,
        )
        return False

    try:
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode("utf-8"))
    except OSError:
        pass
    _LEADER_LOCK_FD = fd
    _LEADER_LOCK_PATH = str(lock_path)
    logger.info(
        "EvolutionScheduler[pid=%d]: elected leader (lock=%s)",
        os.getpid(),
        lock_path,
    )
    return True


def start_scheduler(
    evolution_engine=None,
    experiment_ledger=None,
    truth_registry=None,
) -> Optional[EvolutionScheduler]:
    """
    啟動全局排程器單例（冪等，多次調用安全）。
    Start global scheduler singleton (idempotent, safe to call multiple times).

    從 main.py _startup_integrity_check() 調用，傳入可選的依賴注入對象。
    Called from main.py _startup_integrity_check() with optional injected deps.

    Args:
        evolution_engine  — EvolutionEngine 實例（None 時懶加載）/ instance or None (lazy)
        experiment_ledger — ExperimentLedger 實例（None 時懶加載）/ instance or None (lazy)
        truth_registry    — TruthSourceRegistry 實例（可為 None）/ may be None

    Returns:
        EvolutionScheduler singleton (started)
    """
    global _scheduler
    # 快速路徑：已初始化則直接啟動（start() 本身冪等）
    # Fast path: already initialized → just call start() (start() is idempotent)
    if _scheduler is None:
        with _scheduler_lock:
            if _scheduler is None:
                if not _acquire_leader_lock():
                    return None
                _scheduler = EvolutionScheduler(
                    evolution_engine=evolution_engine,
                    experiment_ledger=experiment_ledger,
                    truth_registry=truth_registry,
                )
    _scheduler.start()
    return _scheduler


def get_scheduler() -> Optional[EvolutionScheduler]:
    """
    返回當前全局排程器單例（若尚未啟動則為 None）。
    Return the current global scheduler singleton (None if not yet started).
    """
    return _scheduler


def _reset_for_tests() -> None:
    """Test helper: reset singleton and release leader lock. / 測試重置。"""
    global _scheduler, _LEADER_LOCK_FD, _LEADER_LOCK_PATH
    _scheduler = None
    if _LEADER_LOCK_FD is not None:
        try:
            fcntl.flock(_LEADER_LOCK_FD, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(_LEADER_LOCK_FD)
        except OSError:
            pass
        _LEADER_LOCK_FD = None
    _LEADER_LOCK_PATH = None
