"""REF-20 Sprint B1 R0-T0 — POST /api/v1/replay/run endpoint logic extraction.
REF-20 Sprint B1 R0-T0 — POST /api/v1/replay/run endpoint 邏輯抽出。

MODULE_NOTE (EN):
    Sprint B1 R0-T0 (2026-05-05) extraction. Owns the
    ``POST /api/v1/replay/run`` business logic so the thin handler in
    ``app/replay_routes.py`` keeps under the CLAUDE.md §九 1500 LOC hard
    cap. PA design report `2026-05-05--ref20_sprint_b_task_dag.md` §11.3
    requires R0-T0 LOC release before R4 + R5 IMPL can land.

    Why this module exists (PA push back):
      ``replay_routes.py`` reached EXACT 1500 LOC after Sprint A R3 round 6
      hotfix wiring; ``/run`` handler is the largest single endpoint
      (~358 LOC including the inline ``_do_pg_path`` closure). Extracting
      that closure plus the error-mapping switchboard saves ~290 LOC from
      ``replay_routes.py`` while keeping byte-equal behaviour (SQL
      strings, branch order, audit payload shape, fallback semantics all
      preserved).

    What this module does:
      - ``_do_pg_path_for_run_sync(*, body, actor_id, get_pg_conn_fn,
        route_helpers, statement_timeout_ms, per_actor_cap, global_cap)
        -> Tuple[run_id, pid, err_reason, output_dir]``
        synchronous helper that wraps the entire PG advisory-lock xact
        path (locks → V045 table check → cap probe → INSERT row →
        manifest fixture write → spawn subprocess → UPDATE pid).
      - ``map_run_pg_error_to_http(pg_err) -> Optional[Tuple[int, dict]]``
        switchboard that maps PG-path error reason strings to HTTP
        ``(status_code, detail_dict)`` tuples. Mirrors the inline if/elif
        chain at ``replay_routes.py`` lines 620-698 (pre-extract).
        Returns ``None`` for non-mapped reasons (caller falls back to
        in-memory path or raises a generic 503).

    What this module does NOT do (out of scope):
      - In-memory fallback path (caller-owned via ``_ACTIVE_RUNS`` dict
        + ``_ACTIVE_RUNS_LOCK``; module-level state in ``replay_routes``).
      - Auth scope check (caller's ``_require_replay_write`` + slowapi
        rate limit run before this).
      - Audit emit (caller dispatches via ``_emit_audit_stub`` because
        success vs fallback branches differ in ``extra_payload`` shape).
      - Pydantic model definition (lives in ``replay/replay_models.py``).

MODULE_NOTE (中):
    Sprint B1 R0-T0（2026-05-05）抽出。擁有 ``POST /api/v1/replay/run``
    業務邏輯，使 ``app/replay_routes.py`` 薄 handler 守住 CLAUDE.md
    §九 1500 LOC 硬上限。PA design report ``2026-05-05--ref20_sprint_b
    _task_dag.md`` §11.3 要求 R0-T0 LOC 釋放後 R4+R5 IMPL 才可進。

    本 module 為何存在（PA push back）：
      ``replay_routes.py`` 在 Sprint A R3 round 6 hotfix wiring 後達 EXACT
      1500 LOC；``/run`` handler 是單一最大 endpoint（含 inline
      ``_do_pg_path`` closure ~358 LOC）。抽出該 closure 加 error-mapping
      switchboard 可從 ``replay_routes.py`` 釋放 ~290 LOC，同時保持
      byte-equal 行為（SQL 字串、分支順序、audit payload shape、
      fallback semantics 全保留）。

    本 module 做的事：
      - ``_do_pg_path_for_run_sync(...)`` 同步 helper 包整個 PG
        advisory-lock xact 路徑（locks → V045 table check → cap probe
        → INSERT row → manifest fixture 寫 → spawn subprocess → UPDATE pid）。
      - ``map_run_pg_error_to_http(pg_err) -> Optional[(status, detail)]``
        switchboard 把 PG-path error reason 字串映射到 HTTP tuple。
        鏡像抽出前 ``replay_routes.py`` line 620-698 inline 鏈。對未映射
        reason 回 ``None``（caller fallback in-memory 或丟通用 503）。

    本 module 不做（範圍外）：
      - In-memory fallback 路徑（caller 持 ``_ACTIVE_RUNS`` dict +
        ``_ACTIVE_RUNS_LOCK``；replay_routes 的 module-level 狀態）。
      - Auth scope 檢查（caller 的 ``_require_replay_write`` + slowapi
        rate limit 在本函式之前跑）。
      - Audit emit（caller 透過 ``_emit_audit_stub`` 派發；success vs
        fallback 分支的 ``extra_payload`` shape 不同）。
      - Pydantic model 定義（在 ``replay/replay_models.py``）。

SPEC: docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md §6.R2/R3
PA Plan: docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-05--ref20_sprint_b_task_dag.md §11.3
V045 schema: sql/migrations/V045__replay_run_state.sql
V049 schema: sql/migrations/V049__replay_experiments.sql
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── Public sync helper: _do_pg_path_for_run_sync ─────────────────────


def _do_pg_path_for_run_sync(
    *,
    body: Any,
    actor_id: str,
    get_pg_conn_fn: Callable[..., Any],
    route_helpers: Any,
    statement_timeout_ms: int,
    per_actor_cap: int,
    global_cap: int,
) -> Tuple[Optional[str], Optional[int], Optional[str], Optional[Path]]:
    """Run the PG advisory-lock xact path for /run (R0-T0 thin extract).
    跑 /run 的 PG advisory-lock xact 路徑（R0-T0 thin extract）。

    The thin route handler at ``app/replay_routes.py`` calls this via
    ``asyncio.to_thread`` then handles audit / response / in-memory
    fallback according to the returned ``err_reason``.

    Args:
        body: ``ReplayRunRequest`` Pydantic instance with attributes
              ``experiment_id`` / ``idempotency_key``.
        actor_id: ``str(actor.actor_id)``.
        get_pg_conn_fn: ``app.db_pool.get_pg_conn`` (context manager).
        route_helpers: ``replay.route_helpers`` module — must expose
              ``v045_table_present`` /
              ``try_acquire_pg_advisory_locks`` /
              ``count_active_runs_for_actor`` /
              ``count_active_runs_global`` /
              ``lookup_registered_experiment_id`` /
              ``resolve_artifact_output_dir`` /
              ``write_manifest_fixture`` /
              ``build_default_manifest_payload`` /
              ``spawn_replay_runner``.
        statement_timeout_ms: per-stmt PG timeout (mirrors
              ``replay_routes._STATEMENT_TIMEOUT_MS``).
        per_actor_cap: V3 §5 per-actor active run cap (1).
        global_cap: V3 §5 global active run cap (1).

    Returns / 回傳:
        (run_id, pid, err_reason, output_dir)

        run_id is None iff this code path did not execute the INSERT
        (PG unavailable, V045 absent, or pre-INSERT validation failed
        — caller routes to in-memory fallback or 4xx).

        pid is None iff:
          - INSERT happened but spawn failed (UPDATE status='failed' was
            persisted; caller raises 503 ``replay_runner_*``);
          - OR R9 Layer-6 sentinel pid=-1 (subprocess clean-exited within
            poll grace; caller renders ``subprocess_completed_in_poll``).

        err_reason ∈ {
          None,                          # success
          "pg_unavailable",              # caller → fallback path
          "v045_absent",                 # caller → fallback path
          "replay_per_actor_cap_exceeded",
          "replay_global_cap_exceeded",
          "replay_experiment_not_registered",
          "binary_not_found",
          "spawn_error:<...>",
          "spawn_died_early:<...>",
          "mkdir_error:<...>",
          "pg_error:<ExcType>",
          "manifest_fixture_write_failed:<ExcType>",
          "manifest_fixture_not_found",
        }

        output_dir is the resolved artifact dir (Path) iff the INSERT
        succeeded and we got far enough to call resolve; otherwise None.
    """
    # Acquire PG conn; pg_unavailable → caller fallback.
    # 取 PG conn；pg_unavailable → caller fallback。
    with get_pg_conn_fn() as conn:
        if conn is None:
            return None, None, "pg_unavailable", None
        try:
            cur = conn.cursor()
            cur.execute("SET LOCAL statement_timeout = %s", (statement_timeout_ms,))

            # Schema-absent graceful: V045 missing → caller fallback in-memory.
            # Schema-absent graceful：V045 缺則 caller fallback in-memory。
            if not route_helpers.v045_table_present(cur):
                return None, None, "v045_absent", None

            # 1) Try advisory locks within this xact.
            # 1) 在此 xact 內嘗試 advisory lock。
            lock_ok, lock_err = route_helpers.try_acquire_pg_advisory_locks(
                cur, actor_id,
            )
            if not lock_ok:
                return None, None, lock_err, None

            # 2) Belt-and-suspenders: query active runs in V045 to verify
            # cap (locks should already prevent races, but this is a
            # defense-in-depth check that's cheap given we hold the lock).
            # 2) 雙保險：在 V045 查 active run 確認 cap（lock 應已防 race，
            # 但持鎖時的 defense-in-depth 廉價檢查）。
            per_actor_count = route_helpers.count_active_runs_for_actor(
                cur, actor_id,
            )
            if per_actor_count >= per_actor_cap:
                return None, None, "replay_per_actor_cap_exceeded", None
            global_count = route_helpers.count_active_runs_global(cur)
            if global_count >= global_cap:
                return None, None, "replay_global_cap_exceeded", None

            # 3) INSERT row with status='starting'; pid filled later.
            # 3) INSERT 列 status='starting'；pid 稍後填。
            run_id_local = uuid.uuid4().hex
            # REF-20 Sprint A R2-T2: real SELECT (FOR SHARE) replaces UUID5.
            # REF-20 Sprint A R2-T2：真 SELECT（FOR SHARE）取代 UUID5。
            manifest_uuid = route_helpers.lookup_registered_experiment_id(
                cur, body.experiment_id,
            )
            if manifest_uuid is None:
                return None, None, "replay_experiment_not_registered", None

            cur.execute(
                """
                INSERT INTO replay.run_state (
                    run_id, actor_id, manifest_id, status,
                    started_at, runtime_environment, idempotency_key
                ) VALUES (
                    %s::uuid, %s, %s::uuid, 'starting',
                    NOW(),
                    COALESCE(NULLIF(%s, ''), 'linux_trade_core'),
                    %s
                );
                """,
                (
                    run_id_local, actor_id, str(manifest_uuid),
                    os.environ.get("OPENCLAW_REPLAY_RUNTIME_ENV", ""),
                    body.idempotency_key,
                ),
            )

            # 4) Resolve output_dir + write manifest fixture (real HMAC
            # sign + sibling key.hex per R6 P0-NEW-INFRA; ``run_id``
            # embedded so Rust runner self-verifies basename — Sprint 1
            # Track A PA push back #2 invariant).
            # 4) 解析 output_dir + 寫 manifest fixture（R6 起 real HMAC
            # 簽 + sibling key.hex；embed ``run_id`` 給 Rust 自驗 basename）。
            output_dir = route_helpers.resolve_artifact_output_dir(run_id_local)
            try:
                manifest_fixture_path = route_helpers.write_manifest_fixture(
                    run_id=run_id_local,
                    manifest_data=route_helpers.build_default_manifest_payload(
                        experiment_id=body.experiment_id,
                        output_dir=output_dir,
                    ),
                    output_dir=output_dir,
                )
            except (OSError, ValueError) as exc:
                cur.execute(
                    """
                    UPDATE replay.run_state
                       SET status = 'failed',
                           exit_code = -1,
                           completed_at = NOW(),
                           cancel_reason = %s
                     WHERE run_id = %s::uuid;
                    """,
                    (
                        f"manifest_fixture_write_failed:{type(exc).__name__}",
                        run_id_local,
                    ),
                )
                conn.commit()
                return (
                    run_id_local,
                    None,
                    f"manifest_fixture_write_failed:{type(exc).__name__}",
                    output_dir,
                )

            # 5) Spawn subprocess (still holding xact lock) + poll-then-INSERT.
            # spawn_replay_runner waits ``poll_grace_seconds`` (default 1.5s)
            # and polls ``proc.poll()`` to detect early death (CLI schema
            # mismatch / manifest fail-closed cause non-zero exit; previous
            # Python flow trusted Popen alone and never noticed — root
            # cause #1+#2 of REF-20 Sprint 1 Track A).
            #
            # 5) Spawn 子程序（仍持 xact lock）+ poll-then-INSERT。
            # spawn_replay_runner 等 ``poll_grace_seconds``（預設 1.5s）
            # 後 ``proc.poll()`` 偵測早死亡（CLI schema mismatch /
            # manifest fail-closed 致非 0 結束；前版 Python 只信 Popen，
            # 完全沒發現 — REF-20 Sprint 1 Track A 第一+二根因）。
            pid, spawn_err = route_helpers.spawn_replay_runner(
                run_id=run_id_local,
                manifest_id=str(manifest_uuid),
                output_dir=output_dir,
                manifest_fixture_path=manifest_fixture_path,
            )

            if pid is None:
                # Real spawn failure (binary missing / argv reject /
                # rc!=0 within poll grace etc).
                # 真 spawn 失敗（binary 缺 / argv reject / rc!=0 等）。
                cur.execute(
                    """
                    UPDATE replay.run_state
                       SET status = 'failed',
                           exit_code = -1,
                           completed_at = NOW(),
                           cancel_reason = %s
                     WHERE run_id = %s::uuid;
                    """,
                    (f"spawn_failed:{spawn_err}", run_id_local),
                )
                conn.commit()
                return run_id_local, None, spawn_err, output_dir

            # 6) UPDATE pid + status='running'. R9 Layer-6: sentinel
            # pid=-1 means subprocess clean-exit in poll grace
            # (synthetic walker <1.5s); ``replay_report.json`` already
            # on disk; subprocess_pid stays NULL (process gone) and
            # caller invokes ``/finalize`` directly.
            # 6) UPDATE pid + status='running'。R9 Layer-6：sentinel
            # pid=-1 表 subprocess 在 poll grace 內乾淨退出；report
            # 已落 disk；subprocess_pid 保 NULL，caller 直接呼 /finalize。
            if pid == -1:
                cur.execute(
                    "UPDATE replay.run_state SET status='running' "
                    "WHERE run_id=%s::uuid;",
                    (run_id_local,),
                )
                conn.commit()
                return run_id_local, None, None, output_dir
            cur.execute(
                """
                UPDATE replay.run_state
                   SET subprocess_pid = %s,
                       status = 'running'
                 WHERE run_id = %s::uuid;
                """,
                (pid, run_id_local),
            )
            conn.commit()
            return run_id_local, pid, None, output_dir
        except Exception as exc:  # noqa: BLE001 — fail-closed PG envelope
            logger.warning("replay_routes /run PG path exception: %s", exc)
            try:
                conn.rollback()
            except Exception:
                pass
            return None, None, f"pg_error:{type(exc).__name__}", None


# ─── Public mapper: map_run_pg_error_to_http ──────────────────────────


def map_run_pg_error_to_http(
    pg_err: Optional[str],
    *,
    experiment_id: str,
) -> Optional[Tuple[int, dict[str, Any]]]:
    """Map PG-path err reason to HTTP (status_code, detail_dict).
    把 PG-path err reason 映射為 HTTP (status_code, detail_dict)。

    Mirrors the inline if/elif chain that lived at ``replay_routes.py``
    lines 620-698 pre-extract. Caller raises ``HTTPException`` with the
    returned tuple, or — for ``None`` returns — falls back to the
    in-memory path (``pg_unavailable`` / ``v045_absent``).

    Branch order matches pre-extract precisely:
      1. cap-exceeded → 409
      2. experiment-not-registered → 400 (echoes ``experiment_id`` in
         ``message`` — pre-extract behaviour preserved)
      3. binary-not-found → 503
      4. spawn_* / mkdir / pg_error / manifest_fixture_write_failed → 503
         (Round 7 FINDING-2: detail message stays static, never echoes
         pg_err text, per §九 SEC-04 stderr-leak protection.)
      5. manifest_fixture_not_found → 503
      6. pg_unavailable / v045_absent / None → ``None`` returned
         (caller does in-memory fallback).

    Args:
        pg_err: reason string from ``_do_pg_path_for_run_sync``.
        experiment_id: caller's ``body.experiment_id`` echoed into the
            400 ``replay_experiment_not_registered`` message to aid
            operator diagnosis (pre-extract behaviour preserved
            byte-equal).

    分支順序精確對齊抽出前：
      1. cap 超 → 409
      2. experiment 未註冊 → 400（``message`` 內會 echo ``experiment_id``，
         與抽出前 byte-equal）
      3. binary 缺 → 503
      4. spawn_* / mkdir / pg_error / manifest_fixture_write_failed → 503
         （Round 7 FINDING-2：detail message 為靜態 operator-pointer，
         不含 pg_err text，符合 §九 SEC-04 stderr 洩漏保護。）
      5. manifest_fixture_not_found → 503
      6. pg_unavailable / v045_absent / None → 回 ``None``
         （caller 走 in-memory fallback）。
    """
    if pg_err in ("replay_global_cap_exceeded", "replay_per_actor_cap_exceeded"):
        # Cap exceeded → 409 (do NOT fallback to in-memory; PG state is canonical).
        # cap 超出 → 409（不 fallback；PG 狀態 canonical）。
        return 409, {
            "reason_codes": [pg_err],
            "message": (
                f"V3 §5 concurrency cap exceeded ({pg_err}); "
                "wait for current run to complete or cancel"
            ),
        }

    if pg_err == "replay_experiment_not_registered":
        # REF-20 Sprint A R2-T2: not in V049 → 400 (no fallback). 未註冊 → 400。
        return 400, {
            "reason_codes": ["replay_experiment_not_registered"],
            "message": (
                f"experiment_id '{experiment_id}' has no row in "
                "replay.experiments; call POST /api/v1/replay/experiments/register first."
            ),
        }

    if pg_err == "binary_not_found":
        # Binary missing → 503 (operator must deploy or set env).
        # binary 缺 → 503（operator 必部署或設 env）。
        return 503, {
            "reason_codes": ["replay_runner_binary_missing"],
            "message": (
                "replay_runner binary not found; set "
                "OPENCLAW_REPLAY_RUNNER_BIN env or build "
                "rust/openclaw_engine --features replay_isolated"
            ),
        }

    if pg_err and pg_err.startswith((
        "spawn_error:",
        "spawn_died_early:",
        "mkdir_error:",
        "pg_error:",
        "manifest_fixture_write_failed:",
    )):
        # Round 7 (2026-05-05) FINDING-2 fix: detail ``message`` is a
        # static operator-pointer (NOT ``f"... {pg_err}"``) so server-side
        # stderr excerpts do not flow back to API clients (§九 SEC-04).
        # route_helpers.py also strips stderr text from reason_code.
        # Round 7 FINDING-2：detail message 為靜態 operator-pointer，
        # 不含 ``pg_err`` text，對齊 §九 SEC-04。
        return 503, {
            "reason_codes": ["replay_runner_spawn_failed"],
            "message": (
                "replay_runner failed to spawn; check server logs "
                "(replay_runner.stderr) for diagnosis"
            ),
        }

    if pg_err == "manifest_fixture_not_found":
        # Caller-supplied manifest fixture path missing on disk before spawn.
        # This is fail-closed defense-in-depth on top of route_helpers writing
        # the fixture (race / FS-level deletion theoretical edge).
        # caller 端 manifest fixture 路徑 spawn 前不在 disk。對 route_helpers
        # 寫 fixture 路徑的 fail-closed 縱深防禦（race / FS 層刪除理論邊界）。
        return 503, {
            "reason_codes": ["replay_manifest_fixture_missing"],
            "message": (
                "manifest fixture not found at expected path; "
                "filesystem race or pre-spawn deletion suspected"
            ),
        }

    # pg_unavailable / v045_absent / None → caller falls back to in-memory.
    # pg_unavailable / v045_absent / None → caller fallback in-memory。
    return None


__all__ = [
    "_do_pg_path_for_run_sync",
    "map_run_pg_error_to_http",
]
