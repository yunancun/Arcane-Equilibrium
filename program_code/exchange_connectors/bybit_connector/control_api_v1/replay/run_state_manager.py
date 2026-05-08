"""REF-20 P2b-T2 ReplayRunStateManager — replay_runner subprocess lifecycle.
REF-20 P2b-T2 ReplayRunStateManager — replay_runner 子程序生命週期。

MODULE_NOTE (EN):
    Wave 4 R20-P2b-T2 (workplan §4) lands the Python helper that bridges
    the 8-route Paper Replay Lab API (replay_routes.py) to the
    `replay_runner` Rust binary lifecycle, persisting subprocess state
    in `replay.run_state` (V045 schema). The class wraps a psycopg2-style
    cursor (DB-API 2.0) and exposes 4 lifecycle operations:

      | Operation                              | Endpoint                              |
      |----------------------------------------|---------------------------------------|
      | start_run(actor_id, manifest_id, pid)  | POST /api/v1/replay/run               |
      | get_run_status(run_id)                 | GET /api/v1/replay/status             |
      | mark_run_complete(run_id, ...)         | (subprocess wait callback / cron)     |
      | cancel_run(run_id)                     | POST /api/v1/replay/cancel            |

    All four methods are idempotent (re-issuing same op on already-final
    row is a no-op). Schema-absent graceful: when V045 has not landed yet
    (Mac dev, fresh PG, etc.), every method returns a sentinel so callers
    can fall through without raising. This mirrors quota_enforcer.py
    schema-absent pattern (`replay.experiments` absent → graceful permit).

    `ReplayRunStateManager` does NOT:
      - spawn the subprocess (caller's responsibility — replay_routes.py
        does subprocess.Popen + hands the resulting pid here);
      - couple to GovernanceHub / Decision Lease / live hot path
        (V3 §6.2 + §12 #14 red-line);
      - read `replay.experiments` manifest_jsonb (manifest verification
        is replay/manifest_signer.py's job);
      - perform DDL or filesystem cleanup (V045 + S5 cron own those).

MODULE_NOTE (中):
    Wave 4 R20-P2b-T2（workplan §4）落地 Python helper，把 8-route Paper
    Replay Lab API（replay_routes.py）橋接到 `replay_runner` Rust binary
    生命週期，狀態存於 `replay.run_state`（V045 schema）。class 包一個
    psycopg2 風格 cursor（DB-API 2.0），暴露 4 種生命週期操作：

      | 操作                                  | 端點                                 |
      |---------------------------------------|---------------------------------------|
      | start_run(actor_id, manifest_id, pid) | POST /api/v1/replay/run              |
      | get_run_status(run_id)                | GET /api/v1/replay/status            |
      | mark_run_complete(run_id, ...)        | （子程序 wait 回調 / cron）          |
      | cancel_run(run_id)                    | POST /api/v1/replay/cancel           |

    四種方法皆冪等（重複對已 final row 做同操作為 no-op）。Schema-absent
    graceful：V045 尚未 land（Mac dev、fresh PG 等）時，每個方法回 sentinel
    讓 caller 不 raise 直接 fall through。對齊 quota_enforcer.py 的
    schema-absent 模式（`replay.experiments` 不在 → graceful permit）。

    `ReplayRunStateManager` 不做：
      - spawn 子程序（caller 責任 — replay_routes.py 自己 subprocess.Popen
        後把 pid 傳進來）；
      - 耦合 GovernanceHub / Decision Lease / live hot path（V3 §6.2 +
        §12 #14 紅線）；
      - 讀 `replay.experiments` manifest_jsonb（manifest 驗證是
        replay/manifest_signer.py 的職責）；
      - DDL 或 filesystem cleanup（V045 + S5 cron 各自負責）。

SPEC: REF-20 V3 §6.1 (Canonical Implementation Choice = `replay_runner`
      binary) + workplan §4 Wave 4 R20-P2b-T2
V3 §12 acceptance #3 route_auth (per-actor / global cap enforced via
      PG advisory lock + this manager owning the lifecycle row)
V3 §12 acceptance #14 replay_no_live_mutation (this module: 0
      trading.* write, 0 live config mutation)

Cross-language note / 跨語言註：本 module 為 Python 端 lifecycle manager；
    Rust 端的 subprocess 體（`replay_runner` binary）由 Wave 3 P2b-S7/S8/S9
    之前的 stub 加上 Wave 4 R20-P2b-T1 的 actual replay logic 組成；
    本 manager 不嵌入 binary，僅透過 PID + signal IPC（SIGTERM）對話。
"""

from __future__ import annotations

import logging
import os
import signal
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

# ─── Logging setup / 日誌設定 ────────────────────────────────────────
log = logging.getLogger("replay.run_state_manager")


# ─── Constants / 常量 ────────────────────────────────────────────────
# V045 table FQN. Hardcoded per spec (V3 §4.1 schema = `replay`).
# V045 table FQN；硬編碼依規範（V3 §4.1 schema = `replay`）。
TABLE_FQN = "replay.run_state"

# V045 status enum allowlist. Mirrors CHECK chk_replay_run_state_status.
# V045 status enum 白名單。對齊 CHECK chk_replay_run_state_status。
STATUS_STARTING = "starting"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

ALLOWED_STATUSES = frozenset({
    STATUS_STARTING,
    STATUS_RUNNING,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_CANCELLED,
})

# Active statuses (used by PG advisory-lock cap query).
# 活躍狀態（PG advisory-lock cap 查詢用）。
ACTIVE_STATUSES = frozenset({STATUS_STARTING, STATUS_RUNNING})

# V3 §4.1 runtime_environment enum. Mirrors CHECK chk_replay_run_state_runtime_env.
# V3 §4.1 runtime_environment enum。對齊 CHECK chk_replay_run_state_runtime_env。
RUNTIME_LINUX = "linux_trade_core"
RUNTIME_MAC = "mac_dev_smoke_test_only"


# ─── Result type / 結果型別 ──────────────────────────────────────────
@dataclass(frozen=True)
class RunStatus:
    """Snapshot returned by `get_run_status` / `start_run`.
    `get_run_status` / `start_run` 回的快照。

    Fields / 欄位:
      - run_id           UUID hex (V045 PRIMARY KEY).
      - actor_id         caller-provided actor identifier.
      - manifest_id      logical reference to replay.experiments.
      - status           V045 status enum value.
      - subprocess_pid   may be None during status='starting' (pre-spawn).
      - started_at_iso   ISO-8601 UTC timestamp.
      - completed_at_iso None unless status in (completed/failed/cancelled).
      - exit_code        None unless completed_at_iso is set.
      - output_path      filesystem path; None when no artifacts written yet.
      - runtime_environment V3 §4.1 enum.
      - schema_present   False when V045 absent (caller can degrade gracefully).
    """

    run_id: str
    actor_id: str
    manifest_id: str
    status: str
    subprocess_pid: Optional[int]
    started_at_iso: str
    completed_at_iso: Optional[str]
    exit_code: Optional[int]
    output_path: Optional[str]
    runtime_environment: str
    schema_present: bool


# ─── Schema presence probe (graceful fallback) ─────────────────────────
def _table_exists(cur: Any, schema: str, table: str) -> bool:
    """Return True iff `schema.table` exists in current DB.
    若 `schema.table` 在當前 DB 存在則回 True。

    Mirrors `quota_enforcer._table_exists` pattern — information_schema
    probe is read-only + portable across psycopg2 versions. Any unexpected
    exception fails closed (returns False) so the manager treats
    schema-absent identically to "table missing → graceful fallback".

    對齊 `quota_enforcer._table_exists` 模式 — information_schema probe
    唯讀且跨 psycopg2 版本可移植。任何例外 fail-closed（回 False），
    manager 把 schema-absent 等同「表缺 → graceful fallback」。
    """
    try:
        cur.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = %s LIMIT 1;",
            (schema, table),
        )
        return cur.fetchone() is not None
    except Exception as exc:  # noqa: BLE001 — fail-closed schema probe
        log.warning(
            "schema probe failed for %s.%s: %s; treating as absent",
            schema, table, exc,
        )
        return False


# ─── Manager class / 管理器主類 ──────────────────────────────────────
class ReplayRunStateManager:
    """Pure-Python run_state manager wrapping a DB-API 2.0 cursor.
    純 Python run_state manager，包一個 DB-API 2.0 cursor。

    Caller responsibility / Caller 責任:
      - Hand a live cursor (psycopg2 / mock); manager does NOT manage
        connection lifecycle.
      - Wrap calls in caller's own transaction; manager does NOT commit
        or rollback.
      - Handle `subprocess.Popen` itself; this manager only persists
        lifecycle metadata + PID + sends SIGTERM in `cancel_run`.

    Thread safety / 執行緒安全:
      Stateless beyond the cursor reference; reuse across requests is
      safe iff each request hands its own cursor (per uvicorn worker
      thread).
    """

    def __init__(self) -> None:
        # Resolve runtime_environment once at construction. Mac platform
        # forces RUNTIME_MAC; Linux defaults to RUNTIME_LINUX (overridable
        # via OPENCLAW_REPLAY_RUNTIME_ENV env var for test environments).
        # 在 ctor 解析一次 runtime_environment。Mac 平台強制 RUNTIME_MAC；
        # Linux 預設 RUNTIME_LINUX（test 環境可透過
        # OPENCLAW_REPLAY_RUNTIME_ENV env var 覆寫）。
        self._runtime_env = self._detect_runtime_environment()
        log.info(
            "ReplayRunStateManager ctor: runtime_environment=%s",
            self._runtime_env,
        )

    @staticmethod
    def _detect_runtime_environment() -> str:
        """Detect runtime environment per V3 §4.1 enum.
        依 V3 §4.1 enum 偵測 runtime environment。

        Priority / 優先級:
          1. OPENCLAW_REPLAY_RUNTIME_ENV env var (test override).
          2. sys.platform == 'darwin' → RUNTIME_MAC.
          3. else → RUNTIME_LINUX.
        """
        override = os.environ.get("OPENCLAW_REPLAY_RUNTIME_ENV", "").strip()
        if override in (RUNTIME_LINUX, RUNTIME_MAC):
            return override

        import sys
        if sys.platform == "darwin":
            return RUNTIME_MAC
        return RUNTIME_LINUX

    @property
    def runtime_environment(self) -> str:
        """Resolved runtime_environment for this manager.
        本 manager 解析得到的 runtime_environment。
        """
        return self._runtime_env

    # ─── Public API: lifecycle / 公開 API：生命週期 ─────────────────────

    def start_run(
        self,
        cur: Any,
        *,
        actor_id: str,
        manifest_id: str,
        subprocess_pid: Optional[int] = None,
        idempotency_key: Optional[str] = None,
    ) -> RunStatus:
        """Insert a new row in replay.run_state with status='starting'.
        在 replay.run_state INSERT 新列，status='starting'。

        Caller's responsibility / Caller 責任:
          - Acquire PG advisory lock (global + per-actor) BEFORE calling
            this method (replay_routes.py owns advisory_lock acquire).
          - Spawn subprocess.Popen AFTER getting back run_id; pass back
            the pid via a follow-up `update_subprocess_pid()` call (or
            include here if Popen happens before INSERT).

        Returns / 回傳:
            `RunStatus` snapshot including server-generated run_id.

        Schema absent / Schema 缺:
            V045 absent → return RunStatus with `schema_present=False`
            and an ephemeral run_id (caller can still surface the id back
            to the GUI; once V045 lands subsequent calls persist).
        """
        run_id = uuid.uuid4().hex
        if not _table_exists(cur, "replay", "run_state"):
            log.info(
                "start_run: replay.run_state absent; ephemeral run_id=%s "
                "(actor=%s, manifest=%s)",
                run_id, actor_id, manifest_id,
            )
            now_iso = datetime.now(timezone.utc).isoformat()
            return RunStatus(
                run_id=run_id,
                actor_id=actor_id,
                manifest_id=manifest_id,
                status=STATUS_STARTING,
                subprocess_pid=subprocess_pid,
                started_at_iso=now_iso,
                completed_at_iso=None,
                exit_code=None,
                output_path=None,
                runtime_environment=self._runtime_env,
                schema_present=False,
            )

        cur.execute(
            """
            INSERT INTO replay.run_state (
                run_id, actor_id, manifest_id, subprocess_pid,
                status, started_at, runtime_environment, idempotency_key
            ) VALUES (
                %s::uuid, %s, %s::uuid, %s,
                %s, NOW(), %s, %s
            )
            RETURNING run_id::text, started_at;
            """,
            (
                run_id, actor_id, manifest_id, subprocess_pid,
                STATUS_STARTING, self._runtime_env, idempotency_key,
            ),
        )
        row = cur.fetchone()
        # row[0] = run_id::text; row[1] = started_at timestamptz.
        # row[0] = run_id::text；row[1] = started_at timestamptz。
        started_at_iso = (
            row[1].isoformat() if hasattr(row[1], "isoformat")
            else str(row[1])
        )
        log.info(
            "start_run: inserted run_id=%s actor=%s manifest=%s pid=%s",
            row[0], actor_id, manifest_id, subprocess_pid,
        )
        return RunStatus(
            run_id=row[0],
            actor_id=actor_id,
            manifest_id=manifest_id,
            status=STATUS_STARTING,
            subprocess_pid=subprocess_pid,
            started_at_iso=started_at_iso,
            completed_at_iso=None,
            exit_code=None,
            output_path=None,
            runtime_environment=self._runtime_env,
            schema_present=True,
        )

    def update_subprocess_pid(
        self,
        cur: Any,
        run_id: str,
        subprocess_pid: int,
        subprocess_started_at_ms: Optional[int] = None,
    ) -> bool:
        """Update subprocess_pid + flip status starting → running.
        更新 subprocess_pid + status starting → running。

        Called by replay_routes.py after subprocess.Popen returns the pid.
        Idempotent: if the row is already running with the same pid,
        UPDATE matches 0 rows and we return False (caller can ignore).

        replay_routes.py 在 subprocess.Popen 拿到 pid 後呼叫。
        冪等：若 row 已 running + 同 pid，UPDATE 0 row 回 False（caller 忽略）。
        """
        if not _table_exists(cur, "replay", "run_state"):
            log.info(
                "update_subprocess_pid: replay.run_state absent; no-op (run_id=%s)",
                run_id,
            )
            return False

        cur.execute(
            """
            UPDATE replay.run_state
               SET subprocess_pid = %s,
                   subprocess_started_at_ms = %s,
                   status = %s
             WHERE run_id = %s::uuid
               AND status = %s
            RETURNING run_id::text;
            """,
            (
                subprocess_pid,
                subprocess_started_at_ms,
                STATUS_RUNNING,
                run_id,
                STATUS_STARTING,
            ),
        )
        row = cur.fetchone()
        if row is None:
            log.info(
                "update_subprocess_pid: no row to flip "
                "(run_id=%s; either absent or not in status=starting)",
                run_id,
            )
            return False
        log.info(
            "update_subprocess_pid: run_id=%s pid=%d status starting→running",
            run_id, subprocess_pid,
        )
        return True

    def get_run_status(
        self, cur: Any, run_id: str
    ) -> Optional[RunStatus]:
        """Query current state for one run.
        查詢單一 run 的當前狀態。

        Returns / 回傳:
            RunStatus on hit; None if run_id not found OR V045 absent.
            Caller can disambiguate via len(_table_exists) probe or by
            calling `get_active_run_for_actor()` first.
        """
        if not _table_exists(cur, "replay", "run_state"):
            return None

        cur.execute(
            """
            SELECT run_id::text, actor_id, manifest_id::text, status,
                   subprocess_pid, started_at, completed_at,
                   exit_code, output_path, runtime_environment
              FROM replay.run_state
             WHERE run_id = %s::uuid
             LIMIT 1;
            """,
            (run_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return RunStatus(
            run_id=row[0],
            actor_id=row[1],
            manifest_id=row[2],
            status=row[3],
            subprocess_pid=row[4],
            started_at_iso=(
                row[5].isoformat() if hasattr(row[5], "isoformat")
                else str(row[5])
            ),
            completed_at_iso=(
                row[6].isoformat() if row[6] and hasattr(row[6], "isoformat")
                else (str(row[6]) if row[6] else None)
            ),
            exit_code=row[7],
            output_path=row[8],
            runtime_environment=row[9],
            schema_present=True,
        )

    def get_active_run_for_actor(
        self, cur: Any, actor_id: str
    ) -> Optional[RunStatus]:
        """Find active run (status IN starting/running) for actor.
        找 actor 的活躍 run（status IN starting/running）。

        Used by GET /status route to return per-actor active snapshot.
        Schema absent → return None (caller treats as idle).

        GET /status route 用以回 actor 的活躍 run 快照。Schema 缺回 None
        （caller 視為閒置）。
        """
        if not _table_exists(cur, "replay", "run_state"):
            return None

        cur.execute(
            """
            SELECT run_id::text, actor_id, manifest_id::text, status,
                   subprocess_pid, started_at, completed_at,
                   exit_code, output_path, runtime_environment
              FROM replay.run_state
             WHERE actor_id = %s
               AND status IN (%s, %s)
             ORDER BY started_at DESC
             LIMIT 1;
            """,
            (actor_id, STATUS_STARTING, STATUS_RUNNING),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return RunStatus(
            run_id=row[0],
            actor_id=row[1],
            manifest_id=row[2],
            status=row[3],
            subprocess_pid=row[4],
            started_at_iso=(
                row[5].isoformat() if hasattr(row[5], "isoformat")
                else str(row[5])
            ),
            completed_at_iso=(
                row[6].isoformat() if row[6] and hasattr(row[6], "isoformat")
                else (str(row[6]) if row[6] else None)
            ),
            exit_code=row[7],
            output_path=row[8],
            runtime_environment=row[9],
            schema_present=True,
        )

    def mark_run_complete(
        self,
        cur: Any,
        run_id: str,
        *,
        exit_code: int,
        output_path: Optional[str] = None,
    ) -> bool:
        """Flip starting/running → (completed | failed) per exit_code.
        依 exit_code 將 starting/running → (completed | failed) 翻轉。

        Mapping / 映射:
          - exit_code == 0 → STATUS_COMPLETED.
          - exit_code != 0 → STATUS_FAILED.

        Idempotent: re-marking already-final row returns False (UPDATE 0).
        Schema absent: returns False (no-op).

        Returns / 回傳:
            True iff a row was actually flipped.
        """
        if not _table_exists(cur, "replay", "run_state"):
            log.info(
                "mark_run_complete: replay.run_state absent; no-op (run_id=%s)",
                run_id,
            )
            return False

        target_status = (
            STATUS_COMPLETED if exit_code == 0 else STATUS_FAILED
        )
        cur.execute(
            """
            UPDATE replay.run_state
               SET status = %s,
                   exit_code = %s,
                   output_path = COALESCE(%s, output_path),
                   completed_at = NOW()
             WHERE run_id = %s::uuid
               AND status IN (%s, %s)
            RETURNING run_id::text;
            """,
            (
                target_status, exit_code, output_path,
                run_id, STATUS_STARTING, STATUS_RUNNING,
            ),
        )
        row = cur.fetchone()
        if row is None:
            log.info(
                "mark_run_complete: no row to flip (run_id=%s; "
                "either absent or already final)",
                run_id,
            )
            return False
        log.info(
            "mark_run_complete: run_id=%s status→%s exit_code=%d output=%s",
            run_id, target_status, exit_code, output_path or "<unchanged>",
        )
        return True

    def cancel_run(
        self,
        cur: Any,
        run_id: str,
        *,
        cancel_reason: Optional[str] = None,
        send_signal: bool = True,
    ) -> bool:
        """Send SIGTERM to subprocess + flip starting/running → cancelled.
        對子程序送 SIGTERM + status starting/running → cancelled。

        Order of operations:
          1. SELECT subprocess_pid + status (single row probe).
          2. If status not in (starting, running) OR no row → return False.
          3. If `send_signal` and pid is set → os.kill(pid, SIGTERM).
             Failure to signal is NOT fatal (subprocess may have already
             exited; we still flip the DB row so caller's GUI updates).
          4. UPDATE status → cancelled, cancel_reason, completed_at = NOW(),
             exit_code = -1 (sentinel for "killed by SIGTERM").

        操作順序：
          1. SELECT subprocess_pid + status（單列 probe）。
          2. status 不在 (starting, running) 或 row 缺 → 回 False。
          3. `send_signal` 且 pid 存在 → os.kill(pid, SIGTERM)。signal 失敗
             不算致命（subprocess 可能已自行 exit）；仍翻 DB row 讓 GUI 更新。
          4. UPDATE status → cancelled、cancel_reason、completed_at = NOW()、
             exit_code = -1（「被 SIGTERM 殺掉」的 sentinel）。

        Returns / 回傳:
            True iff status was actually flipped to cancelled.
        """
        if not _table_exists(cur, "replay", "run_state"):
            log.info(
                "cancel_run: replay.run_state absent; no-op (run_id=%s)",
                run_id,
            )
            return False

        # 1) SELECT current pid + status.
        # 1) SELECT 當前 pid + status。
        cur.execute(
            """
            SELECT subprocess_pid, status
              FROM replay.run_state
             WHERE run_id = %s::uuid
             LIMIT 1;
            """,
            (run_id,),
        )
        row = cur.fetchone()
        if row is None:
            log.info("cancel_run: run_id=%s not found; no-op", run_id)
            return False

        current_pid: Optional[int] = row[0]
        current_status: str = row[1]
        if current_status not in ACTIVE_STATUSES:
            log.info(
                "cancel_run: run_id=%s already final (status=%s); no-op",
                run_id, current_status,
            )
            return False

        # 2) Send SIGTERM if pid known and caller requested.
        # 2) 若 pid 已知且 caller 要求送 signal，呼叫 os.kill。
        if send_signal and current_pid is not None and current_pid > 0:
            try:
                os.kill(current_pid, signal.SIGTERM)
                log.info(
                    "cancel_run: sent SIGTERM to pid=%d (run_id=%s)",
                    current_pid, run_id,
                )
            except ProcessLookupError:
                # Subprocess already exited; flip DB anyway for state coherence.
                # 子程序已退；仍翻 DB row 保狀態一致。
                log.info(
                    "cancel_run: pid=%d already exited; flipping DB only",
                    current_pid,
                )
            except PermissionError as exc:
                # Should not happen (replay_runner spawned by same user), but
                # log + still flip DB so GUI state is coherent.
                # 不該發生（replay_runner 由同 user spawn），但記錄 + 仍翻 DB
                # 保 GUI 一致。
                log.warning(
                    "cancel_run: PermissionError on os.kill(pid=%d): %s; "
                    "flipping DB only",
                    current_pid, exc,
                )
            except OSError as exc:
                # Catch-all for other os.kill failures (e.g. invalid signal
                # number on exotic platforms); fail-safe to DB flip.
                # 其他 os.kill 失敗（罕見平台 invalid signal num）；fail-safe
                # 仍翻 DB。
                log.warning(
                    "cancel_run: OSError on os.kill(pid=%d): %s; "
                    "flipping DB only",
                    current_pid, exc,
                )

        # 3) Flip DB row.
        # 3) 翻 DB row。
        cur.execute(
            """
            UPDATE replay.run_state
               SET status = %s,
                   cancel_reason = %s,
                   exit_code = -1,
                   completed_at = NOW()
             WHERE run_id = %s::uuid
               AND status IN (%s, %s)
            RETURNING run_id::text;
            """,
            (
                STATUS_CANCELLED, cancel_reason,
                run_id, STATUS_STARTING, STATUS_RUNNING,
            ),
        )
        flipped = cur.fetchone()
        if flipped is None:
            log.info(
                "cancel_run: race condition — run_id=%s flipped to final by "
                "concurrent writer between SELECT and UPDATE; no-op",
                run_id,
            )
            return False
        log.info(
            "cancel_run: run_id=%s status→cancelled reason=%s",
            run_id, cancel_reason,
        )
        return True


# ─── Module export / 模組匯出 ────────────────────────────────────────
__all__ = [
    "ACTIVE_STATUSES",
    "ALLOWED_STATUSES",
    "ReplayRunStateManager",
    "RUNTIME_LINUX",
    "RUNTIME_MAC",
    "RunStatus",
    "STATUS_CANCELLED",
    "STATUS_COMPLETED",
    "STATUS_FAILED",
    "STATUS_RUNNING",
    "STATUS_STARTING",
    "TABLE_FQN",
]
