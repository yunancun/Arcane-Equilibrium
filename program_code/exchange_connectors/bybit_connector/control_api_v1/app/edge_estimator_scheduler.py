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
import fcntl
import logging
import os
import sys
import threading
import time
from pathlib import Path
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
        # SCHEDULER-SHUTDOWN-PRIMITIVE-1 (2026-04-23): event-based shutdown
        # so pytest session teardown can cleanly join the daemon thread
        # instead of leaking `while True:` daemon threads per test.
        # SCHEDULER-SHUTDOWN-PRIMITIVE-1：事件式關閉原語，pytest session
        # teardown 可乾淨 join daemon thread，不再每測洩漏 `while True:` daemon。
        self._stop_event: threading.Event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Idempotent start. Spawns the daemon thread on first call. / 冪等啟動。"""
        with self._lock:
            if self._started:
                return
            self._started = True
        # SHUTDOWN-PRIMITIVE-1: retain thread handle for `shutdown()` join.
        # SHUTDOWN-PRIMITIVE-1：保存 thread handle 供 shutdown() join。
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="edge-estimator-scheduler",
        )
        self._thread.start()
        logger.info(
            "EdgeEstimatorScheduler started: modes=%s interval=%.0fs days=%d "
            "/ JS 估計器排程器已啟動：modes=%s interval=%.0fs days=%d",
            self._modes, self._interval_s, self._days_back,
            self._modes, self._interval_s, self._days_back,
        )

    def shutdown(self, join_timeout: float = 5.0) -> bool:
        """
        Graceful shutdown. Signals the loop to stop, joins thread within timeout.
        優雅關閉：發出停止訊號並在 timeout 內 join thread。

        Returns True if thread exited cleanly (or was never running), False if
        join timed out.
        回傳 True 表 thread 乾淨退出（或從未啟動），False 表 join timeout。

        Idempotent: a second call after the thread has exited returns True
        immediately without blocking.
        冪等：thread 已退出後再次呼叫立即回 True，不阻塞。

        SCHEDULER-SHUTDOWN-PRIMITIVE-1 (2026-04-23): purpose is to let pytest
        session teardown reclaim the daemon thread; production code keeps
        running the daemon for the process lifetime (OS cleans up at exit).
        SHUTDOWN-PRIMITIVE-1：目的為讓 pytest session teardown 回收 daemon
        thread；正式環境 daemon 伴隨進程壽命，OS 在進程退出時自動清理。
        """
        self._stop_event.set()
        thread = self._thread
        if thread is None or not thread.is_alive():
            return True
        thread.join(timeout=join_timeout)
        clean = not thread.is_alive()
        if not clean:
            logger.warning(
                "EdgeEstimatorScheduler.shutdown: thread did not exit within "
                "%.1fs / 排程器 thread 未在 %.1fs 內退出",
                join_timeout, join_timeout,
            )
        return clean

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
        # SHUTDOWN-PRIMITIVE-1: replace bare `time.sleep` + `while True:` with
        # stop_event-aware waits so `shutdown()` can interrupt both the warm-up
        # and the interval sleep without leaving the thread dangling until the
        # next `time.sleep` wakes. `Event.wait(timeout)` returns True iff the
        # event was set (shutdown requested), False on timeout (keep looping).
        # SHUTDOWN-PRIMITIVE-1：以 stop_event-aware wait 取代 time.sleep + while True，
        # shutdown() 可在 warm-up 或 interval sleep 中斷，thread 不會卡到下一輪
        # time.sleep 才退出。Event.wait(timeout) 事件被 set 回 True，timeout 回 False。

        # First-run warm-up: 60s or until stop signalled.
        # 首次延遲 60s 或直到停止訊號（避免與啟動其他任務搶資源）。
        if self._stop_event.wait(timeout=60.0):
            return  # Shutdown requested during warm-up / 啟動期已被要求關閉
        while not self._stop_event.is_set():
            self._run_cycle(reason="scheduled")
            if self._stop_event.wait(timeout=self._interval_s):
                return  # Clean exit on shutdown / 被要求關閉，乾淨退出

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
        # QC-2 (2026-04-23): wrap the ENTIRE writer body in try/except so the
        # fail-soft contract in the docstring is actually enforced. Previously
        # payload build (int/float conversions on `results_for_mode`) sat
        # outside any guard — a non-numeric value would raise and escape via
        # _run_cycle's `finally` back up into the daemon thread.
        # QC-2：payload 構建包入最外層 try/except，兌現 docstring 宣告的
        # fail-soft 契約。原來 int/float 轉換在 try 外，非數字值會拋出並經
        # _run_cycle 的 finally 穿透回 daemon thread。
        try:
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
        except Exception as payload_exc:
            # Payload build raised (non-numeric value, serialisation edge, etc.).
            # Warn and return — do NOT propagate up into _run_cycle's finally.
            # payload 構建失敗（非數字值 / 序列化邊界）— warning 後 return，
            # 絕不傳播回 _run_cycle 的 finally block。
            logger.warning(
                "EdgeEstimatorScheduler: payload build failed "
                "(fail-soft, event dropped): mode=%s js_error=%r payload_exc=%s "
                "/ payload 構建失敗（fail-soft，事件丟棄）：mode=%s js_error=%r payload_exc=%s",
                mode, js_error, payload_exc, mode, js_error, payload_exc,
            )
            return

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

# EDGE-SCHEDULER-LEADER-1 (2026-04-23): process-wide flock fd, held for the
# lifetime of the leader worker. OS auto-releases on process exit (including
# SIGKILL), so a crashed leader does not prevent the next restart from
# electing a new leader.
# EDGE-SCHEDULER-LEADER-1：leader worker 進程壽命內持有的 flock fd。
# OS 在進程退出（含 SIGKILL）時自動釋放鎖，crashed leader 不阻塞下次啟動重新選舉。
_LEADER_LOCK_FD: Optional[int] = None
_LEADER_LOCK_PATH: Optional[str] = None


def _leader_lock_path() -> Path:
    """
    Resolve the leader-election sentinel path.
    計算 leader 選舉 sentinel 檔案路徑。

    Uses $OPENCLAW_DATA_DIR (cross-platform; Mac sets this in ~/.zshrc per
    CLAUDE.md §六) and falls back to /tmp/openclaw to match the Linux
    runtime default. Parent is created if missing (matches engine.sock /
    api.log convention).
    使用 $OPENCLAW_DATA_DIR 跨平台變數（Mac 需在 ~/.zshrc 設定，見 CLAUDE.md §六），
    fallback 到 /tmp/openclaw 對齊 Linux runtime 預設。Parent 不存在則建立，
    與 engine.sock / api.log 慣例一致。
    """
    data_dir = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")
    return Path(data_dir) / "edge_scheduler.leader.lock"


def _acquire_leader_lock() -> bool:
    """
    EDGE-SCHEDULER-LEADER-1: per-host leader election via fcntl.flock.

    Returns True iff THIS process is now the leader (it successfully acquired
    an exclusive non-blocking lock on the sentinel file). The fd is stashed
    in `_LEADER_LOCK_FD` module-global so the lock is held for the process
    lifetime — the OS releases it automatically at process exit.

    Under uvicorn --workers N, N worker processes call this on startup; only
    the first to reach `flock(LOCK_EX|LOCK_NB)` wins. The other N-1 workers
    receive `BlockingIOError` (EWOULDBLOCK) and return False.

    Env override / test hook:
      OPENCLAW_SCHEDULER_LEADER=0 → force non-leader (skip flock; return False).
        Useful for: single-worker dev where you want no scheduler; tests
        that need to simulate a follower; operator disabling the scheduler
        without touching code.

    Cross-platform: fcntl.flock is available on Linux and macOS (per POSIX /
    BSD). Not Windows — but per CLAUDE.md §七.★★ the project's portability
    target is Mac + Linux only.

    EDGE-SCHEDULER-LEADER-1：單機 leader 選舉（fcntl.flock）。

    回傳 True 表示本進程剛贏得選舉（成功取得 sentinel 檔的 exclusive
    non-blocking 鎖）。fd 保存於 `_LEADER_LOCK_FD` 模組全域，進程退出時
    OS 自動釋放，無需 atexit handler。

    uvicorn --workers N 下 N 個 worker 進程於啟動時呼叫此函數；最早到達
    `flock(LOCK_EX|LOCK_NB)` 的 worker 獲勝，其餘 N-1 個收到
    `BlockingIOError (EWOULDBLOCK)` 後回 False。

    env opt-out / 測試鉤子：
      OPENCLAW_SCHEDULER_LEADER=0 → 強制非 leader（跳過 flock 直接 return False）。
        適用於：單 worker 開發情境、測試模擬 follower、operator 臨時
        關閉 scheduler 不動碼。

    跨平台：fcntl.flock 支援 Linux 與 macOS（POSIX/BSD），不支援 Windows；
    本專案目標平台為 Mac + Linux（CLAUDE.md §七.★★），涵蓋完整。
    """
    global _LEADER_LOCK_FD, _LEADER_LOCK_PATH

    # Idempotent: if already leader in this process, return True immediately
    # without re-flocking (re-flock on the same fd from same process would
    # succeed but wastefully churn the inode).
    # 冪等：若本進程已是 leader，直接回 True，避免重複 flock 同一 fd。
    if _LEADER_LOCK_FD is not None:
        return True

    # Env opt-out for tests / single-worker dev / operator disable.
    # 測試、單 worker 開發、operator 手動停用通道：env=0 強制非 leader。
    if os.environ.get("OPENCLAW_SCHEDULER_LEADER") == "0":
        logger.info(
            "EdgeEstimatorScheduler[pid=%d]: OPENCLAW_SCHEDULER_LEADER=0, "
            "forced non-leader / pid=%d：環境變數強制非 leader",
            os.getpid(), os.getpid(),
        )
        return False

    lock_path = _leader_lock_path()
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as mkdir_exc:
        logger.warning(
            "EdgeEstimatorScheduler[pid=%d]: cannot mkdir parent for leader "
            "lock %s (%s) — falling back to non-leader / 無法建立 leader "
            "lock 父目錄 %s（%s），降級為非 leader",
            os.getpid(), lock_path, mkdir_exc, lock_path, mkdir_exc,
        )
        return False

    try:
        # O_CREAT: create if missing; O_RDWR so we can write PID for debug.
        # O_CREAT：檔案不存在則建立；O_RDWR 允許寫入 PID 方便 debug。
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    except OSError as open_exc:
        logger.warning(
            "EdgeEstimatorScheduler[pid=%d]: cannot open leader lock %s "
            "(%s) — non-leader / 無法開啟 leader lock %s（%s），非 leader",
            os.getpid(), lock_path, open_exc, lock_path, open_exc,
        )
        return False

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError) as lock_exc:
        # Another worker in the same uvicorn cohort already holds the lock.
        # This is the EXPECTED path for N-1 of N workers — log at info not warn.
        # 同 uvicorn 群組另一 worker 已持鎖，N-1 個 worker 走此路徑，info 級別。
        os.close(fd)
        logger.info(
            "EdgeEstimatorScheduler[pid=%d]: non-leader worker (lock held "
            "by another worker at %s; %s) / 非 leader worker（鎖由另一 "
            "worker 持有於 %s；%s）",
            os.getpid(), lock_path, lock_exc, lock_path, lock_exc,
        )
        return False

    # Write current PID into the lock file for operator debuggability
    # (`cat edge_scheduler.leader.lock` → current leader PID). Non-fatal.
    # 寫入 current PID 便於 operator debug（cat 檔案即見 leader PID）；寫失敗不致命。
    try:
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode("utf-8"))
    except OSError:
        pass

    _LEADER_LOCK_FD = fd
    _LEADER_LOCK_PATH = str(lock_path)
    logger.info(
        "EdgeEstimatorScheduler[pid=%d]: elected leader (lock=%s) / "
        "pid=%d 當選 leader（鎖=%s）",
        os.getpid(), lock_path, os.getpid(), lock_path,
    )
    return True


def start_scheduler(
    modes: tuple[str, ...] = EdgeEstimatorScheduler.DEFAULT_MODES,
    interval_s: float = 3600.0,
    days_back: int = EdgeEstimatorScheduler.DEFAULT_DAYS,
) -> Optional[EdgeEstimatorScheduler]:
    """
    Idempotent global start, gated by EDGE-SCHEDULER-LEADER-1 election.
    冪等全域啟動，受 EDGE-SCHEDULER-LEADER-1 選舉把關。

    Under uvicorn --workers N (N=4 in restart_all.sh), only the worker that
    wins `_acquire_leader_lock()` actually instantiates the scheduler and
    spawns the daemon thread. The other N-1 workers return None and their
    `get_scheduler()` returns None — route handlers surface 503 (Operator
    can retry; uvicorn's round-robin will eventually hit the leader).
    uvicorn --workers N（restart_all.sh 中 N=4）下只有贏得選舉的 worker
    實際建立 scheduler 並啟動 daemon thread；其餘 N-1 個 worker 回 None，
    其 `get_scheduler()` 也回 None，route handler 回 503（operator 重試，
    uvicorn round-robin 最終會打到 leader）。

    Rationale — this prevents 4 parallel JS estimations per hour, each
    holding a PG connection and UPDATE-ing `learning.decision_features`
    (PG MVCC tolerates the race but it's pure waste: 4x DB load, 4x
    settings/edge_estimates.json atomic-replace races, 4x observability
    rows).
    修復動機：避免 4 個 worker 每小時同時跑 JS 估計（各自佔 PG 連線 +
    UPDATE learning.decision_features），PG MVCC 可容忍但純粹浪費：4 倍 DB
    負載、4 倍 settings/edge_estimates.json atomic-replace 競爭、4 倍
    observability 行數。
    """
    global _scheduler
    if _scheduler is None:
        with _scheduler_lock:
            if _scheduler is None:
                if not _acquire_leader_lock():
                    # Non-leader — no instance, no thread, no cycles. Main.py
                    # ignores return value; routes see None and 503.
                    # 非 leader：無 instance、無 thread、無 cycle。main.py 忽略回傳值；
                    # routes 看到 None 回 503。
                    return None
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


def _reset_for_tests() -> None:
    """
    Test-only: reset module globals + release leader lock fd so tests can
    re-exercise the election path without process restart.
    測試專用：重置模組全域變數並釋放 leader lock fd，讓測試可重複跑選舉路徑而不需重啟進程。

    SCHEDULER-SHUTDOWN-PRIMITIVE-1 (2026-04-23): before clearing the singleton,
    gracefully shut down any running scheduler so its daemon thread actually
    joins instead of leaking across tests in the same pytest session.
    SHUTDOWN-PRIMITIVE-1：清單例前先優雅關閉既有 scheduler，daemon thread
    真正 join，而非跨測試累積於同一 pytest session。
    """
    global _scheduler, _LEADER_LOCK_FD, _LEADER_LOCK_PATH
    # SHUTDOWN-PRIMITIVE-1: stop-signal + 5s join before dropping reference.
    # SHUTDOWN-PRIMITIVE-1：放棄引用前 signal stop 並 join（5s 上限）。
    if _scheduler is not None:
        try:
            _scheduler.shutdown(join_timeout=5.0)
        except Exception:
            # Best-effort: teardown must never raise, otherwise fixtures that
            # chain _reset_for_tests() at yield break and wedge the suite.
            # Best-effort：teardown 絕不可 raise，否則 fixture 於 yield 後串呼
            # _reset_for_tests 會中斷整個測試。
            pass
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
