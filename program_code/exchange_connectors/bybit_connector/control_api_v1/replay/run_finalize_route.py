"""REF-20 Sprint A R3-T1 — POST /run/{run_id}/finalize endpoint logic.
REF-20 Sprint A R3-T1 — POST /run/{run_id}/finalize endpoint 邏輯。

MODULE_NOTE (EN):
    Sprint A R3-T1 (2026-05-04). Owns the
    ``POST /api/v1/replay/run/{run_id}/finalize`` business logic so the
    thin handler in ``app/replay_routes.py`` keeps under the
    ``CLAUDE.md §九 1500 LOC`` hard cap.

    This route persists *post-execution evidence* into PostgreSQL after
    the Rust ``replay_runner`` subprocess has written
    ``<output_dir>/replay_report.json``. Three writes in one transaction:

      1. INSERT one row into ``replay.report_artifacts`` (V046; via
         ``canary_writer.register_artifact_in_db``).
      2. INSERT N rows into ``replay.simulated_fills`` (V050; via
         ``simulated_fills_writer.persist_replay_report``).
      3. UPDATE ``replay.run_state`` SET status='completed' +
         completed_at=NOW() + exit_code=0 (V045) for the matching row.

    Failure / partial-failure semantics:
      - Cross-actor 404: V045 ``run_state`` row with ``actor_id != caller``
        returns 404 ``replay_run_not_found`` to close the IDOR
        enumeration oracle (mirrors ``/report`` round 3 H-IDOR-ENUM fix).
        This is identical to "no row at all" from the caller's POV.
      - Status guard: ``run_state.status NOT IN ('starting', 'running')``
        → 409 ``replay_run_not_finalizable`` (already terminal, OR never
        spawned). Re-finalize is harmless at SQL level (UPDATE WHERE
        status IN (...) returns 0 rows + ON CONFLICT DO NOTHING for
        fills) but we surface 409 to the caller for clarity.
      - Subprocess still running: ``verify_replay_runner_pid(pid) == True``
        and ``status='running'`` → 409 ``replay_run_not_yet_completed``.
        Operator must wait or call ``/cancel`` first.
      - Missing report file: ``replay_report.json`` absent under
        ``output_dir`` → 410 ``replay_report_artifact_missing``.
        Subprocess died before writing or never spawned.
      - Atomic xact: report_artifacts + simulated_fills + run_state UPDATE
        all share the same cursor. Any exception → ``conn.rollback()`` →
        zero rows persisted on partial failure.

MODULE_NOTE (中):
    Sprint A R3-T1（2026-05-04）。擁有
    ``POST /api/v1/replay/run/{run_id}/finalize`` 業務邏輯，使
    ``app/replay_routes.py`` 薄 handler 守住
    ``CLAUDE.md §九 1500 LOC`` 硬上限。

    本 route 在 Rust ``replay_runner`` subprocess 寫
    ``<output_dir>/replay_report.json`` 後，將「執行後證據」持久化到
    PostgreSQL。同 transaction 三次寫：

      1. INSERT 一列至 ``replay.report_artifacts``（V046；透過
         ``canary_writer.register_artifact_in_db``）。
      2. INSERT N 列至 ``replay.simulated_fills``（V050；透過
         ``simulated_fills_writer.persist_replay_report``）。
      3. UPDATE ``replay.run_state`` SET status='completed' +
         completed_at=NOW() + exit_code=0（V045）對應 row。

    失敗 / 部分失敗語意：
      - 跨 actor 404：V045 ``run_state`` row 的 ``actor_id != caller``
        回 404 ``replay_run_not_found`` 收斂 IDOR 列舉預言機（鏡像
        ``/report`` round 3 H-IDOR-ENUM 修復）。從 caller 視角與「完全
        沒有 row」等價。
      - 狀態守門：``run_state.status NOT IN ('starting', 'running')``
        → 409 ``replay_run_not_finalizable``（已終態 OR 從未 spawn）。
        SQL 層 re-finalize 無害（UPDATE WHERE 0 row + fills ON CONFLICT
        DO NOTHING）但對 caller 揭露 409 為清晰。
      - subprocess 仍在跑：``verify_replay_runner_pid(pid) == True``
        且 ``status='running'`` → 409 ``replay_run_not_yet_completed``。
        operator 必須等或先 /cancel。
      - 缺 report 檔：``output_dir`` 下無 ``replay_report.json`` →
        410 ``replay_report_artifact_missing``。subprocess 死於寫入前
        或未 spawn。
      - 原子 xact：report_artifacts + simulated_fills + run_state UPDATE
        共用同 cursor。任何例外 → ``conn.rollback()`` → 部分失敗時 0 row
        持久化。

SPEC: docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md §6.R3
V045 schema: sql/migrations/V045__replay_run_state.sql
V046 schema: sql/migrations/V046__replay_report_artifacts.sql
V050 schema: sql/migrations/V050__replay_simulated_fills.sql
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── Constants / 常量 ────────────────────────────────────────────────

# V045 status enum we accept as "ready to finalize" (mirrors run_state_manager
# ACTIVE_STATUSES). Anything else (completed/failed/cancelled) returns 409.
# V045 status enum 接受為「可 finalize」（鏡像 run_state_manager
# ACTIVE_STATUSES）。其他（completed/failed/cancelled）回 409。
FINALIZABLE_STATUSES = frozenset({"starting", "running"})

# V045 status set after successful finalize.
# 成功 finalize 後的 V045 status。
FINALIZED_STATUS = "completed"

# V046 artifact_type used for the per-finalize replay_report.json registration.
# V046 CHECK chk_replay_report_artifacts_type allowlist
#   = {canary, diagnostic, pnl_summary, fill_log, baseline_compare}.
# We choose ``pnl_summary`` because Rust ``replay_report.json`` carries a
# top-level ``pnl_summary`` block as its dominant payload. The plan §6.R3
# pseudocode wrote ``replay_report`` but that string is NOT in V046 CHECK
# enum (would 23514 reject INSERT). E1 selects the closest in-allowlist
# value and notes the discrepancy in the sign-off report (§10).
#
# V046 artifact_type 用於 per-finalize replay_report.json 註冊。
# V046 CHECK chk_replay_report_artifacts_type 白名單
#   = {canary, diagnostic, pnl_summary, fill_log, baseline_compare}。
# 選 ``pnl_summary`` 因為 Rust ``replay_report.json`` top-level 有
# ``pnl_summary`` block 為主 payload。plan §6.R3 偽碼寫 ``replay_report``
# 但該字串不在 V046 CHECK enum（會 INSERT 23514 reject）。E1 選白名單
# 內最近義值並在 sign-off §10 標記差異。
ARTIFACT_TYPE_REPLAY_REPORT = "pnl_summary"

# Replay report file basename written by Rust report_writer.
# Rust report_writer 寫的 replay report file basename。
REPLAY_REPORT_BASENAME = "replay_report.json"

# REF-20 Sprint A R3 round 2 fix M-2: finalize statement timeout.
# Distinct from register's 2_000ms (per replay_routes._STATEMENT_TIMEOUT_MS):
# finalize does up to N×INSERT simulated_fills (worst-case ~80k rows from
# 16 MB report cap / 200 byte/fill). 2s would 503-rollback under heavy
# fixtures. 5s is the documented finalize ceiling per E1 round 1 §10 #3
# operator handoff intent.
#
# REF-20 Sprint A R3 round 2 fix M-2：finalize statement timeout 與 register
# 的 2_000ms 區隔（replay_routes._STATEMENT_TIMEOUT_MS）。finalize 最多 N×
# INSERT simulated_fills（16 MB 報告 / 200 byte/fill ≈ 80k row 上限），2s
# 在重 fixture 下會 503 rollback；5s 是 E1 round 1 §10 #3 operator handoff
# 文件意圖。
_FINALIZE_STATEMENT_TIMEOUT_MS = 5_000


# ─── Validation / 驗證 ───────────────────────────────────────────────


def validate_run_id_shape(run_id: str) -> Optional[str]:
    """Validate run_id is hex-only (no '-'), max 32 chars (uuid4().hex shape).
    驗證 run_id 為純 hex（無 '-'），最大 32 char（uuid4().hex 形狀）。

    Returns / 回傳:
        ``None`` on valid; error reason string on invalid (caller maps to
        400 ``replay_invalid_run_id``).
    """
    if not run_id:
        return "empty_run_id"
    # Allow uuid4().hex (32 hex) OR uuid4 with hyphens (36 chars). The
    # canonical form written by ``replay_routes.post_replay_run`` is hex
    # (no hyphens; ``uuid.uuid4().hex``) but accept hyphenated form for
    # operator convenience.
    # 接受 uuid4().hex（32 hex）OR uuid4 含 hyphen（36 chars）。
    # ``replay_routes.post_replay_run`` 規範形式為 hex，便利接 hyphenated。
    if len(run_id) not in (32, 36):
        return f"run_id_length_invalid:{len(run_id)}"
    for ch in run_id:
        if not (ch in "0123456789abcdefABCDEF-"):
            return f"run_id_invalid_char:{ch!r}"
    return None


# ─── Run state lookup with IDOR enum-oracle close ────────────────────


def _select_run_state_for_finalize_sync(
    cur: Any,
    *,
    run_id: str,
    expected_actor_id: str,
) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
    """SELECT V045 ``run_state`` row guarded by actor_id IDOR check.
    SELECT V045 ``run_state`` row，含 actor_id IDOR 檢查。

    Mirrors the H-IDOR-ENUM pattern from ``report_route._lookup_manifest_uuid``:
    cross-actor row collapses to ``"not_found"`` (NOT a distinct reason)
    so HTTP layer cannot distinguish from absent row.

    鏡像 ``report_route._lookup_manifest_uuid`` 的 H-IDOR-ENUM 模式：
    跨 actor row 收斂為 ``"not_found"``（非獨立 reason）使 HTTP 層
    無法區分 absent。

    Returns / 回傳:
        (row_dict, None) on found AND own row;
        (None, "not_found") on absent OR cross-actor;
        (None, "not_finalizable") on status NOT IN ('starting','running');
        (None, "still_running") on subprocess pid alive (caller must verify
                                  via verify_replay_runner_pid).

    Output row_dict keys / 輸出 row_dict 鍵:
        run_id / actor_id / manifest_id / status / subprocess_pid /
        runtime_environment / output_path
    """
    # REF-20 Sprint A R3 round 2 fix M-1: SELECT ... FOR UPDATE row-locks the
    # V045 run_state row inside the finalize xact to prevent multi-worker
    # uvicorn race that would otherwise INSERT TWO V046 report_artifacts
    # rows for a single finalize call. Worker B blocks on FOR UPDATE until
    # worker A commits/rolls back; if A commits first then B's subsequent
    # SELECT sees status='completed' → B routes to 409 not_finalizable.
    # V050 simulated_fills was already idempotent via composite UNIQUE
    # (experiment_id, idempotency_key) but V046 lacked an analogous guard,
    # so without FOR UPDATE worker B could still insert a duplicate V046
    # row pointing at the same on-disk file (cosmetic but breaks V3 §5
    # quota integrity that assumes one V046 row per finalize).
    #
    # REF-20 Sprint A R3 round 2 fix M-1：SELECT ... FOR UPDATE 在 finalize
    # xact 內 row-lock V045 run_state row，防止 multi-worker uvicorn race
    # 對單一 finalize 呼叫產生兩條 V046 report_artifacts row。worker B 在
    # FOR UPDATE 上 block 直到 worker A commit/rollback；若 A 先 commit，
    # B 後續 SELECT 看到 status='completed' → B 走 409 not_finalizable。
    # V050 simulated_fills 已透過 (experiment_id, idempotency_key) 複合
    # UNIQUE 保 idempotent，但 V046 無對應守門；少了 FOR UPDATE 時 worker B
    # 仍會 INSERT 一條指向同一 disk file 的 V046 row（cosmetic 但破 V3 §5
    # quota 完整性的「每 finalize 一條 V046 row」不變式）。
    cur.execute(
        """
        SELECT run_id::text, actor_id, manifest_id::text, status,
               subprocess_pid, runtime_environment, output_path
          FROM replay.run_state
         WHERE run_id = %s::uuid
         LIMIT 1
           FOR UPDATE;
        """,
        (run_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None, "not_found"

    # IDOR enum-oracle close: cross-actor row collapses to "not_found".
    # IDOR enum-oracle close：跨 actor row 收斂為 "not_found"。
    if row[1] != expected_actor_id:
        return None, "not_found"

    status = row[3]
    if status not in FINALIZABLE_STATUSES:
        return None, "not_finalizable"

    return {
        "run_id": row[0],
        "actor_id": row[1],
        "manifest_id": row[2],
        "status": status,
        "subprocess_pid": row[4],
        "runtime_environment": row[5],
        "output_path": row[6],
    }, None


# ─── Run state UPDATE / run_state UPDATE ─────────────────────────────


def _mark_run_finalized(cur: Any, *, run_id: str) -> bool:
    """UPDATE V045 run_state SET status='completed' + completed_at + exit_code=0.
    UPDATE V045 run_state SET status='completed' + completed_at + exit_code=0。

    Status guard prevents re-finalize: WHERE status IN ('starting','running')
    only flips active rows. Idempotent re-finalize returns False (UPDATE 0).

    狀態守門防 re-finalize：WHERE status IN ('starting','running') 只翻
    active row。idempotent re-finalize 回 False（UPDATE 0）。

    Returns / 回傳:
        True iff a row was actually updated.
    """
    cur.execute(
        """
        UPDATE replay.run_state
           SET status = %s,
               exit_code = 0,
               completed_at = NOW()
         WHERE run_id = %s::uuid
           AND status IN ('starting', 'running')
        RETURNING run_id::text;
        """,
        (FINALIZED_STATUS, run_id),
    )
    row = cur.fetchone()
    return row is not None


# ─── Public coroutine: run_finalize_in_pg_xact ───────────────────────


async def run_finalize_in_pg_xact(
    *,
    actor: Any,
    run_id: str,
    get_pg_conn_fn: Callable[..., Any],
    resolve_artifact_output_dir_fn: Callable[[str], Path],
    artifact_path_within_allowlist_fn: Callable[[Path], Tuple[bool, Optional[str]]],
    verify_replay_runner_pid_fn: Callable[[int], Tuple[bool, Optional[str]]],
    canary_writer: Any,
    simulated_fills_writer: Any,
    audit_emit_fn: Callable[..., None],
    statement_timeout_ms: int = _FINALIZE_STATEMENT_TIMEOUT_MS,
) -> Tuple[Optional[dict[str, Any]], Optional[Tuple[int, dict[str, Any]]]]:
    """Run the full finalize flow inside a single PG transaction.
    在單一 PG transaction 內跑完整 finalize 流程。

    Flow / 流程:
      1. validate_run_id_shape (caller already; defense-in-depth here too).
      2. SELECT run_state with IDOR check.
      3. If still_running: verify_replay_runner_pid; subprocess alive → 409.
      4. resolve output_dir; check replay_report.json exists.
      5. canary_writer.write_replay_artifact (filesystem; idempotent rename).
         NOTE: actually we register the EXISTING replay_report.json file
         that Rust binary already wrote, NOT re-write it. canary_writer
         API is two-step (write + register); we skip step 1 because the
         file is already present and instead use ``WriteResult`` directly
         (bypass write step via ``register_artifact_in_db`` only).
      6. simulated_fills_writer.persist_replay_report (parse + INSERT N).
      7. _mark_run_finalized (UPDATE V045 status=completed).
      8. conn.commit + emit_audit_stub.

    Args:
        actor: ``base.AuthenticatedActor``. Uses ``actor.actor_id`` for
               IDOR guard.
        run_id: V045 run uuid (hex or hyphenated; validated).
        get_pg_conn_fn: ``app.db_pool.get_pg_conn`` (context manager).
        resolve_artifact_output_dir_fn: ``route_helpers.resolve_artifact_output_dir``.
        artifact_path_within_allowlist_fn: ``route_helpers.artifact_path_within_allowlist``.
        verify_replay_runner_pid_fn: ``route_helpers.verify_replay_runner_pid``.
        canary_writer: ``replay.canary_writer`` module (uses
                       ``CanaryArtifactWriter`` + ``WriteResult``).
        simulated_fills_writer: ``replay.simulated_fills_writer`` module
                                (uses ``persist_replay_report``).
        audit_emit_fn: ``route_helpers.emit_replay_audit_stub``.
        statement_timeout_ms: per-stmt timeout (default
                              ``_FINALIZE_STATEMENT_TIMEOUT_MS = 5_000ms``;
                              finalize is slower than register because of
                              bulk INSERT N×simulated_fills). R3 round 2
                              fix M-2 introduced this constant to fix
                              timeout drift from register's 2_000ms.

    Returns / 回傳:
        (response_dict, None) on success;
        (None, (status_code, detail_dict)) on failure.
    """
    actor_id = str(actor.actor_id)

    # Step 1: validate run_id shape (defense-in-depth).
    # 步驟 1：驗 run_id 形狀（縱深防禦）。
    err = validate_run_id_shape(run_id)
    if err is not None:
        return None, (400, {
            "reason_codes": ["replay_invalid_run_id"],
            "message": err,
        })

    # Step 2: PG xact open + SELECT run_state with IDOR check.
    # 步驟 2：開 PG xact + SELECT run_state 含 IDOR 檢查。
    def _do_pg_xact() -> (
        Tuple[Optional[dict[str, Any]], Optional[Tuple[int, dict[str, Any]]]]
    ):
        with get_pg_conn_fn() as conn:
            if conn is None:
                return None, (503, {
                    "reason_codes": ["replay_pg_unavailable"],
                    "message": "PG unavailable; cannot finalize run",
                })
            try:
                cur = conn.cursor()
                cur.execute(
                    "SET LOCAL statement_timeout = %s",
                    (statement_timeout_ms,),
                )

                row, lookup_err = _select_run_state_for_finalize_sync(
                    cur, run_id=run_id, expected_actor_id=actor_id,
                )
                if lookup_err == "not_found":
                    conn.rollback()
                    return None, (404, {
                        "reason_codes": ["replay_run_not_found"],
                        "message": (
                            f"run_id {run_id!r} not found OR not owned by caller; "
                            "this response unifies both cases per IDOR enum-oracle close"
                        ),
                    })
                if lookup_err == "not_finalizable":
                    conn.rollback()
                    return None, (409, {
                        "reason_codes": ["replay_run_not_finalizable"],
                        "message": (
                            f"run {run_id} status not in ('starting','running'); "
                            "may be already finalized or never started"
                        ),
                    })
                # row is not None at this point; but assert defensively.
                assert row is not None

                # Step 3: subprocess still alive? → 409 not_yet_completed.
                # 步驟 3：subprocess 還活著？→ 409 not_yet_completed。
                pid = row.get("subprocess_pid")
                if pid:
                    is_alive, _why = verify_replay_runner_pid_fn(pid)
                    if is_alive:
                        conn.rollback()
                        return None, (409, {
                            "reason_codes": ["replay_run_not_yet_completed"],
                            "message": (
                                f"subprocess pid={pid} still running for "
                                f"run_id={run_id}; wait or POST /cancel first"
                            ),
                        })

                # Step 4: resolve output_dir + check replay_report.json.
                # 步驟 4：解析 output_dir + 檢查 replay_report.json。
                output_dir = resolve_artifact_output_dir_fn(run_id)
                report_path = output_dir / REPLAY_REPORT_BASENAME

                # Path-traversal allowlist guard (cross-platform Path.resolve
                # symlink check by upstream helper). Defense-in-depth: even
                # though resolve_artifact_output_dir is server-controlled,
                # we still check.
                # 路徑遍歷白名單守門（上游 helper Path.resolve symlink 檢）。
                # 縱深防禦：即使 resolve_artifact_output_dir 由 server 控制
                # 仍檢。
                within, traversal_err = artifact_path_within_allowlist_fn(
                    report_path
                )
                if not within:
                    conn.rollback()
                    return None, (410, {
                        "reason_codes": ["replay_report_artifact_missing"],
                        "message": (
                            f"replay_report.json path-traversal blocked: "
                            f"{traversal_err}"
                        ),
                    })

                if not report_path.is_file():
                    conn.rollback()
                    return None, (410, {
                        "reason_codes": ["replay_report_artifact_missing"],
                        "message": (
                            f"replay_report.json not found at "
                            f"{report_path!s}; subprocess may have died "
                            "before writing"
                        ),
                    })

                # Step 5: register replay_report.json in V046.
                # 步驟 5：將 replay_report.json 註冊到 V046。
                # NOTE: we do NOT re-write the file (Rust already wrote
                # it). We synthesize a WriteResult from the existing file
                # to call register_artifact_in_db without re-IO. Using
                # canary_writer.WriteResult dataclass directly.
                # 註：不重寫該檔（Rust 已寫）。從現存檔合成 WriteResult
                # 直接呼 register_artifact_in_db 而不重 IO。
                try:
                    file_size = report_path.stat().st_size
                except OSError as exc:
                    conn.rollback()
                    return None, (410, {
                        "reason_codes": ["replay_report_artifact_missing"],
                        "message": f"stat failed on {report_path!s}: {exc}",
                    })

                write_result = canary_writer.WriteResult(
                    artifact_id=uuid.uuid4().hex,
                    artifact_path=str(report_path),
                    byte_size=file_size,
                    is_mock=(row.get("runtime_environment")
                             == "mac_dev_smoke_test_only"),
                )

                writer = canary_writer.CanaryArtifactWriter(
                    runtime_environment=(row.get("runtime_environment") or "")
                )
                registered = writer.register_artifact_in_db(
                    cur, run_id, write_result,
                    artifact_type=ARTIFACT_TYPE_REPLAY_REPORT,
                )
                if not registered:
                    # V046 absent (graceful no-op per canary_writer contract).
                    # Continue — schema-absent is not fatal in Sprint A.
                    # V046 缺（canary_writer 契約 graceful no-op）。
                    # 繼續 — schema-absent 在 Sprint A 不致命。
                    logger.info(
                        "run_finalize: V046 absent; continuing without "
                        "report_artifacts row (run_id=%s)", run_id,
                    )

                # Step 6: parse + INSERT simulated_fills.
                # 步驟 6：parse + INSERT simulated_fills。
                fills_result = simulated_fills_writer.persist_replay_report(
                    cur, report_path,
                    experiment_id=row["manifest_id"],
                    run_id=run_id,
                )

                # Step 7: UPDATE run_state status → completed.
                # 步驟 7：UPDATE run_state status → completed。
                marked = _mark_run_finalized(cur, run_id=run_id)
                if not marked:
                    # Race: row flipped to terminal between SELECT and UPDATE.
                    # Conservative behavior: rollback + 409.
                    # race：SELECT 與 UPDATE 之間 row 翻為 terminal。保守
                    # 行為：rollback + 409。
                    conn.rollback()
                    return None, (409, {
                        "reason_codes": ["replay_run_finalize_race"],
                        "message": (
                            f"run {run_id} status changed during finalize; "
                            "retry harmless"
                        ),
                    })

                # Step 8: commit + emit audit stub.
                # 步驟 8：commit + 發 audit stub。
                conn.commit()

                response = {
                    "run_id": run_id,
                    "experiment_id": row["manifest_id"],
                    "status": FINALIZED_STATUS,
                    "report_artifact_id": (
                        write_result.artifact_id if registered else None
                    ),
                    "report_artifact_registered": registered,
                    "fills_inserted": fills_result.fills_inserted,
                    "fills_skipped": fills_result.fills_skipped,
                    "fills_truncated": fills_result.fills_truncated,
                    "writer_errors": fills_result.errors,
                }
                audit_emit_fn(
                    event_type="replay_run_finalized",
                    actor_id=actor_id,
                    experiment_id=row["manifest_id"],
                    manifest_hash=None,
                    decision="accepted",
                    extra_payload={
                        "run_id": run_id,
                        "report_artifact_id": response["report_artifact_id"],
                        "fills_inserted": fills_result.fills_inserted,
                        "fills_skipped": fills_result.fills_skipped,
                    },
                )
                return response, None

            except (OSError, ValueError) as exc:
                # File / parse errors map to 410 (artifact-side issue).
                # 檔 / parse 錯誤 map 到 410（artifact 端問題）。
                logger.warning(
                    "run_finalize: artifact error run_id=%s: %s",
                    run_id, exc,
                )
                try:
                    conn.rollback()
                except Exception:
                    pass
                return None, (410, {
                    "reason_codes": ["replay_report_artifact_missing"],
                    "message": (
                        f"finalize failed reading replay_report.json: "
                        f"{type(exc).__name__}: {exc}"
                    ),
                })
            except Exception as exc:  # noqa: BLE001 — fail-closed PG envelope
                logger.warning(
                    "run_finalize: PG xact exception run_id=%s: %s",
                    run_id, exc,
                )
                try:
                    conn.rollback()
                except Exception:
                    pass
                return None, (503, {
                    "reason_codes": ["replay_finalize_failed"],
                    "message": f"finalize failed: {type(exc).__name__}",
                })

    return await asyncio.to_thread(_do_pg_xact)


__all__ = [
    "ARTIFACT_TYPE_REPLAY_REPORT",
    "FINALIZABLE_STATUSES",
    "FINALIZED_STATUS",
    "REPLAY_REPORT_BASENAME",
    "_FINALIZE_STATEMENT_TIMEOUT_MS",
    "run_finalize_in_pg_xact",
    "validate_run_id_shape",
]
