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

    def _run_backfill(self, mode: str) -> dict:
        """Run edge_label_backfill for `mode` before JS estimation so labels
        land in `learning.decision_features.label_net_edge_bps` this cycle.
        fail-open: error is caught by caller; JS still runs.
        在 JS 估計前先跑 label backfill，讓本輪取得最新 labels；失敗時交由呼叫者處理（fail-open）。"""
        from ml_training.edge_label_backfill import backfill_labels  # noqa: PLC0415
        r = backfill_labels(engine_mode=mode, batch_limit=5000, dry_run=False)
        return {
            "filled": r.filled_count,
            "excluded": r.excluded_count,
            "grid_merged": r.grid_merged_count,
            "split_blend": r.split_blend_count,
        }

    def _run_cycle(self, reason: str) -> dict[str, dict]:
        results: dict[str, dict] = {}
        for mode in self._modes:
            # Per-mode wall-clock for duration_ms / 每個 mode 各自計時
            t_start = time.time()
            backfill_error: Optional[BaseException] = None
            js_error: Optional[BaseException] = None
            try:
                # Backfill first — populate labels so JS sees this cycle's fills.
                # 先回填 labels 再跑 JS；失敗不阻斷 JS（backfill 是 JS 的 best-effort 前置）。
                try:
                    backfill_summary = self._run_backfill(mode)
                    logger.info(
                        "EdgeEstimatorScheduler[%s]: mode=%s backfill filled=%d grid=%d "
                        "/ JS 排程器[%s]：mode=%s 回填 filled=%d grid=%d",
                        reason, mode, backfill_summary.get("filled", 0),
                        backfill_summary.get("grid_merged", 0),
                        reason, mode, backfill_summary.get("filled", 0),
                        backfill_summary.get("grid_merged", 0),
                    )
                except Exception as bexc:
                    backfill_error = bexc
                    backfill_summary = {"error": str(bexc)}
                    logger.warning(
                        "EdgeEstimatorScheduler[%s]: mode=%s backfill failed (fail-open, JS still runs): %s "
                        "/ JS 排程器[%s]：mode=%s 回填失敗（fail-open，JS 仍執行）：%s",
                        reason, mode, bexc, reason, mode, bexc,
                    )

                summary = self._run_one_mode(mode)
                summary["backfill"] = backfill_summary
                results[mode] = summary
                logger.info(
                    "EdgeEstimatorScheduler[%s]: mode=%s n_cells=%d grand_mean_bps=%.2f reason=%s "
                    "/ JS 排程器[%s]：mode=%s n_cells=%d grand_mean=%.2f bps reason=%s",
                    reason, mode, summary.get("n_cells", 0), summary.get("grand_mean_bps", 0.0), reason,
                    reason, mode, summary.get("n_cells", 0), summary.get("grand_mean_bps", 0.0), reason,
                )
            except Exception as exc:
                js_error = exc
                results[mode] = {"error": str(exc)}
                with self._lock:
                    self._failures += 1
                logger.warning(
                    "EdgeEstimatorScheduler[%s]: mode=%s failed (fail-open): %s "
                    "/ JS 排程器[%s]：mode=%s 失敗（不阻斷）：%s",
                    reason, mode, exc, reason, mode, exc,
                )
            finally:
                # SCHEDULER-FAILURE-OBSERVABILITY-1: persist one row per mode
                # to observability.engine_events so operators can SQL-query
                # scheduler heartbeat + failures without greping stdout.
                # SCHEDULER-FAILURE-OBSERVABILITY-1：每個 mode 寫一行到
                # observability.engine_events，operator 可 SQL 查排程心跳與失敗，
                # 不必翻 stdout log。
                duration_ms = int((time.time() - t_start) * 1000)
                self._record_cycle_event(
                    reason=reason,
                    mode=mode,
                    duration_ms=duration_ms,
                    backfill_error=backfill_error,
                    js_error=js_error,
                    results_for_mode=results.get(mode),
                )
        with self._lock:
            self._runs += 1
            self._last_run_ts = time.time()
            self._last_results = results
        return results

    def _record_cycle_event(
        self,
        *,
        reason: str,
        mode: str,
        duration_ms: int,
        backfill_error: Optional[BaseException],
        js_error: Optional[BaseException],
        results_for_mode: Optional[dict],
    ) -> None:
        """
        Fail-soft INSERT into observability.engine_events for scheduler
        heartbeat + failure observability (SCHEDULER-FAILURE-OBSERVABILITY-1).

        Status semantics / status 語意：
          'ok'   — JS estimation succeeded (backfill may or may not have failed;
                   backfill failure is non-fatal and still yields ok status
                   but is recorded in payload.backfill_error_class).
          'fail' — JS estimation raised; cycle produced no estimates this mode.

        Fail-soft: any exception in this writer (connection loss, schema drift,
        serialisation error) is swallowed and logged at warning — never re-raised,
        never blocks the scheduler cycle.

        Fail-soft INSERT 寫入 observability.engine_events，為排程器心跳 +
        失敗觀察性（SCHEDULER-FAILURE-OBSERVABILITY-1）。

        status 語意：
          'ok'   — JS 估計成功（backfill 可失可成，backfill 失敗不致命、
                   仍算整輪 ok，但 payload.backfill_error_class 會記錄）
          'fail' — JS 估計拋出；此 mode 本輪無估計。

        Fail-soft：此 writer 任何異常（連線中斷/schema drift/序列化錯誤）
        一律吞下並 warning log，永不 re-raise、永不阻塞 scheduler 主循環。
        """
        status = "fail" if js_error is not None else "ok"
        error_class: Optional[str] = type(js_error).__name__ if js_error else None
        error_msg: Optional[str] = str(js_error) if js_error else None

        # Build payload JSON — structured enough for SQL projection but
        # capped to what operator needs for triage.
        # payload JSON 保持結構化、可 SQL 投影，同時只收 operator triage 必需資訊。
        payload = {
            "scheduler_name": "edge_estimator",
            "cycle_phase": "full_cycle",  # backfill + JS estimate, per _run_cycle contract
            "reason": reason,
            "mode": mode,
            "engine_mode": mode,  # alias for operator SQL ergonomics / 便於 operator SQL
            "status": status,
            "duration_ms": duration_ms,
            "error_class": error_class,
            "error_msg": error_msg,
            "backfill_error_class": (
                type(backfill_error).__name__ if backfill_error else None
            ),
            "n_cells": (
                int(results_for_mode.get("n_cells", 0))
                if isinstance(results_for_mode, dict) else None
            ),
            "grand_mean_bps": (
                float(results_for_mode.get("grand_mean_bps", 0.0))
                if isinstance(results_for_mode, dict) else None
            ),
        }

        # Lazy imports so a PG-less environment never breaks module load.
        # 懶 import；PG 不可達環境下不影響模組載入。
        try:
            import json  # noqa: PLC0415
            from .db_pool import get_pg_conn  # noqa: PLC0415
        except Exception as imp_exc:
            logger.warning(
                "EdgeEstimatorScheduler: observability writer import failed "
                "(fail-soft, event dropped): %s "
                "/ 觀察性寫入器 import 失敗（fail-soft，事件丟棄）：%s",
                imp_exc, imp_exc,
            )
            return

        ts_ms = int(time.time() * 1000)
        event_type = "scheduler_ok" if status == "ok" else "scheduler_fail"

        try:
            with get_pg_conn() as conn:
                if conn is None:
                    # Pool unavailable — degrade silently + one warning.
                    # Pool 不可達 — 靜默降級，一次 warning。
                    logger.warning(
                        "EdgeEstimatorScheduler: DB pool unavailable, "
                        "scheduler event not persisted (mode=%s status=%s) "
                        "/ DB pool 不可達，排程事件未持久化 (mode=%s status=%s)",
                        mode, status, mode, status,
                    )
                    return
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO observability.engine_events
                            (ts_ms, event_type, source, config_name, payload)
                        VALUES (%s, %s, %s, %s, %s::jsonb)
                        """,
                        (
                            ts_ms,
                            event_type,
                            "edge_estimator_scheduler",
                            None,  # config_name unused for scheduler events
                            json.dumps(payload),
                        ),
                    )
                conn.commit()
        except Exception as insert_exc:
            # Fail-soft — scheduler main loop must not see this.
            # Fail-soft — 不讓 scheduler 主循環看到這個錯。
            logger.warning(
                "EdgeEstimatorScheduler: observability INSERT failed "
                "(fail-soft, cycle not affected): %s "
                "/ 觀察性 INSERT 失敗（fail-soft，不影響 cycle）：%s",
                insert_exc, insert_exc,
            )

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
