from __future__ import annotations

"""
P1-7 B — James-Stein Edge Estimator Auto-Scheduler
James-Stein 邊際估計器自動排程器（每小時）

MODULE_NOTE (EN):
  Activates the dormant james_stein_estimator pipeline (P1-7 B / LEARNING-PIPELINE-DORMANT-1).
  Spawns a daemon thread that runs the estimator every hour for engine_modes 'demo' and
  'live_demo', writing snapshots to settings/edge_estimates.json and settings/edge_estimates_live_demo.json.
  Provides a `trigger_now()` callable for IPC hot-trigger (route handler can invoke).

  IMPORTANT — file-only, NOT bound to cost_gate:
  Per CLAUDE.md §三 LEARNING-PIPELINE-DORMANT-1 + TODO §P1-14, the engine reads
  edge_estimates.json once at startup via `set_edge_estimates()` and does NOT hot-reload.
  Binding cost_gate threshold change is gated on:
    1. P1-16 halt_session price corruption fix landed (upstream)
    2. demo grand_mean > -50 bps
    3. >= 2 strategies with shrunk_bps > 0
  This scheduler intentionally only refreshes the file; engine restart picks it up.

MODULE_NOTE (中):
  啟動沉睡的 james_stein_estimator 管線（P1-7 B / LEARNING-PIPELINE-DORMANT-1）。
  daemon 線程每小時跑 demo + live_demo 估計，寫入 settings/edge_estimates*.json。
  提供 `trigger_now()` 供 IPC 手動熱觸發。

  重要 — 只寫檔，不 bind cost_gate：
  引擎啟動時 `set_edge_estimates()` 讀一次 demo edge_estimates.json，不做熱重載。
  cost_gate 門檻 bind 條件：P1-16 修復 + demo grand_mean > -50 bps + ≥2 策略 shrunk_bps>0。
  此排程器僅刷新檔案，engine 重啟才生效。
"""

import datetime
import logging
import os
import sys
import threading
import time
from typing import Optional

_app_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_app_dir)
_bybit_connector_dir = os.path.dirname(_control_api_dir)
_exchange_connectors_dir = os.path.dirname(_bybit_connector_dir)
_program_code_dir = os.path.dirname(_exchange_connectors_dir)
if _program_code_dir not in sys.path:
    sys.path.insert(0, _program_code_dir)

logger = logging.getLogger(__name__)


class EdgeEstimatorScheduler:
    """
    Hourly James-Stein refresh for demo + live_demo edge estimates.
    每小時刷新 demo + live_demo 的 James-Stein 邊際估計。

    fail-open: any single mode failure does not stop the loop or affect trading.
    fail-open: 單一 mode 失敗不停止循環，也不影響交易。
    """

    DEFAULT_MODES = ("demo", "live_demo")
    DEFAULT_DAYS = 7  # rolling window matches P1-15/17 cleanup horizon

    def __init__(
        self,
        modes: tuple[str, ...] = DEFAULT_MODES,
        interval_s: float = 3600.0,
        days_back: int = DEFAULT_DAYS,
    ) -> None:
        self._modes = modes
        self._interval_s = interval_s
        self._days_back = days_back
        self._lock = threading.Lock()
        self._started: bool = False
        # Thread-safe stats / 線程安全統計
        self._runs: int = 0
        self._failures: int = 0
        self._last_run_ts: Optional[float] = None
        self._last_results: dict[str, dict] = {}

    def start(self) -> None:
        """Idempotent start. Spawns the daemon thread on first call. / 冪等啟動。"""
        with self._lock:
            if self._started:
                return
            self._started = True
        t = threading.Thread(
            target=self._loop,
            daemon=True,
            name="edge-estimator-scheduler",
        )
        t.start()
        logger.info(
            "EdgeEstimatorScheduler started: modes=%s interval=%.0fs days=%d "
            "/ JS 估計器排程器已啟動：modes=%s interval=%.0fs days=%d",
            self._modes, self._interval_s, self._days_back,
            self._modes, self._interval_s, self._days_back,
        )

    def trigger_now(self) -> dict[str, dict]:
        """
        Synchronous on-demand re-run for IPC hot-trigger. Returns per-mode summary.
        IPC 熱觸發：同步執行一次，返回每 mode 結果摘要。
        """
        return self._run_cycle(reason="manual_trigger")

    def status(self) -> dict:
        """Return current scheduler stats (non-blocking). / 返回排程器統計。"""
        with self._lock:
            return {
                "started": self._started,
                "runs": self._runs,
                "failures": self._failures,
                "last_run_ts": self._last_run_ts,
                "last_run_iso": (
                    datetime.datetime.fromtimestamp(self._last_run_ts, tz=datetime.timezone.utc).isoformat()
                    if self._last_run_ts else None
                ),
                "modes": list(self._modes),
                "interval_s": self._interval_s,
                "days_back": self._days_back,
                "last_results": dict(self._last_results),
            }

    def _loop(self) -> None:
        # First run after a 60s warm-up so startup ordering is forgiving.
        # 首次延遲 60s 避免和啟動其它任務搶資源
        time.sleep(60.0)
        while True:
            self._run_cycle(reason="scheduled")
            time.sleep(self._interval_s)

    @staticmethod
    def _ensure_pg_env_from_database_url() -> None:
        """
        james_stein_estimator._get_db_conn() reads PG_HOST/PG_PORT/PG_DB/PG_USER/PG_PASSWORD
        env vars. The API server is launched with OPENCLAW_DATABASE_URL only (restart_all.sh
        convention). Bridge the two so the in-process scheduler inherits credentials without
        widening the launch contract.

        JS 估計器讀 PG_* 環境變量；API server 只設 OPENCLAW_DATABASE_URL。在排程器內就地
        橋接，避免擴張啟動契約。已存在的 PG_* 不覆蓋（顯式優先）。
        """
        url = os.environ.get("OPENCLAW_DATABASE_URL")
        if not url:
            return
        try:
            from urllib.parse import urlparse  # noqa: PLC0415

            parsed = urlparse(url)
        except Exception:
            return
        if parsed.scheme not in ("postgres", "postgresql"):
            return
        # Only set what is missing — explicit env var wins.
        # 只補缺失的；顯式設定優先。
        env_map = {
            "PG_HOST": parsed.hostname or "",
            "PG_PORT": str(parsed.port) if parsed.port else "",
            "PG_DB": (parsed.path or "").lstrip("/"),
            "PG_USER": parsed.username or "",
            "PG_PASSWORD": parsed.password or "",
        }
        for k, v in env_map.items():
            if v and not os.environ.get(k):
                os.environ[k] = v

    def _run_cycle(self, reason: str) -> dict[str, dict]:
        results: dict[str, dict] = {}
        for mode in self._modes:
            try:
                summary = self._run_one_mode(mode)
                results[mode] = summary
                logger.info(
                    "EdgeEstimatorScheduler[%s]: mode=%s n_cells=%d grand_mean_bps=%.2f reason=%s "
                    "/ JS 排程器[%s]：mode=%s n_cells=%d grand_mean=%.2f bps reason=%s",
                    reason, mode, summary.get("n_cells", 0), summary.get("grand_mean_bps", 0.0), reason,
                    reason, mode, summary.get("n_cells", 0), summary.get("grand_mean_bps", 0.0), reason,
                )
            except Exception as exc:
                results[mode] = {"error": str(exc)}
                with self._lock:
                    self._failures += 1
                logger.warning(
                    "EdgeEstimatorScheduler[%s]: mode=%s failed (fail-open): %s "
                    "/ JS 排程器[%s]：mode=%s 失敗（不阻斷）：%s",
                    reason, mode, exc, reason, mode, exc,
                )
        with self._lock:
            self._runs += 1
            self._last_run_ts = time.time()
            self._last_results = results
        return results

    def _run_one_mode(self, mode: str) -> dict:
        """
        Invoke james_stein_estimator.run_james_stein() in-process for a single mode.
        Returns a small summary dict (kept light to avoid bloating /status response).
        對單一 mode 內進程調用 run_james_stein()，返回小型摘要 dict。
        """
        # Lazy import to avoid pulling psycopg2 at module load if Postgres absent.
        # Top-level `ml_training` matches the existing app convention
        # (program_code is on sys.path via the 5-level traversal at module load).
        # 懶 import，避免 PG 不可達時模組載入即失敗。頂層 `ml_training` 對齊 app
        # 既有慣例（5-level traversal 已將 program_code 加入 sys.path）。
        from ml_training.james_stein_estimator import run_james_stein  # noqa: PLC0415

        self._ensure_pg_env_from_database_url()
        results = run_james_stein(
            days_back=self._days_back,
            engine_mode=mode,
            # snapshot_path=None → mode-aware default (settings/edge_estimates*.json)
        )

        # Distill: n_cells + grand_mean_bps (other fields stay in the JSON snapshot).
        # 摘要：cell 數 + grand_mean，其他細節保留在 JSON 檔
        if not results:
            return {"n_cells": 0, "grand_mean_bps": 0.0}

        # results is dict[(strategy, symbol)] → row dict
        n = len(results)
        first_row = next(iter(results.values()))
        grand_mean = float(first_row.get("grand_mean_bps", first_row.get("grand_mean", 0.0)))
        return {"n_cells": n, "grand_mean_bps": grand_mean}


_scheduler: Optional[EdgeEstimatorScheduler] = None
_scheduler_lock = threading.Lock()


def start_scheduler(
    modes: tuple[str, ...] = EdgeEstimatorScheduler.DEFAULT_MODES,
    interval_s: float = 3600.0,
    days_back: int = EdgeEstimatorScheduler.DEFAULT_DAYS,
) -> EdgeEstimatorScheduler:
    """
    Idempotent global start. Called from main.py startup hook.
    冪等全域啟動，由 main.py startup hook 呼叫。
    """
    global _scheduler
    if _scheduler is None:
        with _scheduler_lock:
            if _scheduler is None:
                _scheduler = EdgeEstimatorScheduler(
                    modes=modes,
                    interval_s=interval_s,
                    days_back=days_back,
                )
    _scheduler.start()
    return _scheduler


def get_scheduler() -> Optional[EdgeEstimatorScheduler]:
    """Return current global scheduler (None if not yet started). / 返回單例。"""
    return _scheduler
