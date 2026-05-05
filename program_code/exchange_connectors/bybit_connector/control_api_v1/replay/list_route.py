"""REF-20 Sprint B1 R0-T0 — GET /api/v1/replay/list endpoint logic extraction.
REF-20 Sprint B1 R0-T0 — GET /api/v1/replay/list endpoint 邏輯抽出。

MODULE_NOTE (EN):
    Sprint B1 R0-T0 (2026-05-05) extraction. Owns the
    ``GET /api/v1/replay/list`` business logic so the thin handler in
    ``app/replay_routes.py`` keeps under the CLAUDE.md §九 1500 LOC hard
    cap. PA design report `2026-05-05--ref20_sprint_b_task_dag.md` §11.3
    requires R0-T0 LOC release before R4 + R5 IMPL can land.

    What this module does:
      - ``list_replay_runs_for_actor(*, actor_id, limit, offset,
        status_filter, async_safe_pg_select_fn,
        replay_response_envelope_fn) -> dict`` coroutine that:
          1. Builds parameterised SQL with optional ``status_filter``
             (V3 §4.1 + V045 status enum constraint already validated by
             FastAPI ``Query(pattern=...)`` at the thin handler boundary).
          2. SELECTs V045 ``replay.run_state`` rows ordered by
             ``started_at DESC`` (latest first).
          3. Maps each row to a JSON-serialisable dict (ISO timestamps).
          4. Wraps in ``replay_response_envelope`` (degraded on PG err).

    What this module does NOT do (out of scope):
      - Auth scope check (caller's ``Depends(current_actor)`` is enough;
        read-only listing per actor_id, no write scope required).
      - Pagination / ``limit / offset`` validation (FastAPI ``Query`` at
        thin handler boundary).
      - ``status_filter`` regex validation (FastAPI ``Query(pattern=...)``
        at thin handler boundary).
      - V049 ``replay.experiments`` JOIN (V045-only projection — same as
        pre-extract behaviour; if R5 needs richer payload it should add
        a separate JOIN-aware function rather than mutate this one).

MODULE_NOTE (中):
    Sprint B1 R0-T0（2026-05-05）抽出。擁有 ``GET /api/v1/replay/list``
    業務邏輯，使 ``app/replay_routes.py`` 薄 handler 守住 CLAUDE.md
    §九 1500 LOC 硬上限。PA design report ``2026-05-05--ref20_sprint_b
    _task_dag.md`` §11.3 要求 R0-T0 LOC 釋放後 R4+R5 IMPL 才可進。

    本 module 做的事：
      - ``list_replay_runs_for_actor(...)`` coroutine 實作 4 步驟。

    本 module 不做（範圍外）：
      - Auth scope 檢查（caller 的 ``Depends(current_actor)`` 足夠；
        per actor_id 只讀列表，不需 write scope）。
      - Pagination / ``limit / offset`` 驗證（thin handler 邊界由
        FastAPI ``Query`` 處理）。
      - ``status_filter`` regex 驗證（thin handler 邊界由 FastAPI
        ``Query(pattern=...)`` 處理）。
      - V049 ``replay.experiments`` JOIN（V045-only projection，與抽
        出前行為一致；若 R5 需更豐 payload，應加獨立 JOIN-aware
        function，而非變更本函式）。

SPEC: docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md §6.R3
PA Plan: docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-05--ref20_sprint_b_task_dag.md §11.3
V045 schema: sql/migrations/V045__replay_run_state.sql
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── SQL templates / SQL 模板 ─────────────────────────────────────────

# V045 ``replay.run_state`` SELECT shared by both filtered + unfiltered
# branches. 7 columns: run_id, manifest_id, status, started_at,
# completed_at, exit_code, runtime_environment.
# V045 ``replay.run_state`` SELECT，filtered 與 unfiltered 兩分支共用。
# 7 欄：run_id, manifest_id, status, started_at, completed_at,
# exit_code, runtime_environment。
_LIST_SQL_WITH_STATUS = """
SELECT run_id::text, manifest_id::text, status,
       started_at, completed_at, exit_code,
       runtime_environment
  FROM replay.run_state
 WHERE actor_id = %s AND status = %s
 ORDER BY started_at DESC
 LIMIT %s OFFSET %s;
"""

_LIST_SQL_NO_STATUS = """
SELECT run_id::text, manifest_id::text, status,
       started_at, completed_at, exit_code,
       runtime_environment
  FROM replay.run_state
 WHERE actor_id = %s
 ORDER BY started_at DESC
 LIMIT %s OFFSET %s;
"""


# ─── Row-to-dict mapper / row 轉 dict ─────────────────────────────────


def _row_to_experiment_dict(row: tuple) -> dict[str, Any]:
    """Map one V045 ``run_state`` row tuple to JSON-serialisable dict.
    映射單個 V045 ``run_state`` row tuple 為 JSON 可序列化 dict。

    ISO-8601 conversion is defensive: the V045 columns are TIMESTAMPTZ
    so psycopg returns ``datetime`` objects with ``isoformat()``, but we
    ``hasattr`` check for the rare driver path that surfaces strings
    instead (e.g. mock fixtures in unit tests).
    ISO-8601 轉換為防禦：V045 欄位為 TIMESTAMPTZ，psycopg 返回有
    ``isoformat()`` 的 ``datetime``，但 ``hasattr`` 檢查覆蓋少數驅動
    路徑（例如 unit test 的 mock fixture）回傳字串。
    """
    return {
        "run_id": row[0],
        "manifest_id": row[1],
        "status": row[2],
        "started_at": (
            row[3].isoformat() if hasattr(row[3], "isoformat") else str(row[3])
        ),
        "completed_at": (
            row[4].isoformat() if row[4] and hasattr(row[4], "isoformat")
            else (str(row[4]) if row[4] else None)
        ),
        "exit_code": row[5],
        "runtime_environment": row[6],
    }


# ─── Public coroutine: list_replay_runs_for_actor ─────────────────────


async def list_replay_runs_for_actor(
    *,
    actor_id: str,
    limit: int,
    offset: int,
    status_filter: Optional[str],
    async_safe_pg_select_fn: Callable[
        [str, tuple], Awaitable[Tuple[list, Optional[str]]]
    ],
    replay_response_envelope_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Run the full GET /list flow (R0-T0 thin extract).
    執行完整 GET /list 流程（R0-T0 thin extract）。

    Caller is the thin route handler in ``app/replay_routes.py`` which
    only does the auth ``Depends`` + ``Query`` validation + this call
    + return the envelope.

    Args:
        actor_id: caller's ``str(actor.actor_id)``.
        limit: ``Query(1..100)`` already validated at thin handler.
        offset: ``Query(>=0)`` already validated at thin handler.
        status_filter: one of ``starting / running / completed / failed
            / cancelled / created`` or None. Pattern already validated
            by FastAPI ``Query(pattern=...)`` at thin handler.
        async_safe_pg_select_fn: ``app.replay_routes._async_safe_pg_select``.
        replay_response_envelope_fn: ``replay.route_helpers
            .replay_response_envelope``.

    Returns / 回傳:
        dict — fully-formed envelope. ``degraded=True`` on PG err
        (V3 §12 #22 mirror: list endpoint stays 200 + degraded so
        monitoring + GUI can fail fast without exception unwinding).
    """
    # Step 1: pick SQL template + bind parameters by status_filter presence.
    # 步驟 1：依 status_filter 是否提供選 SQL 模板並綁參。
    if status_filter:
        sql = _LIST_SQL_WITH_STATUS
        params: tuple[Any, ...] = (actor_id, status_filter, limit, offset)
    else:
        sql = _LIST_SQL_NO_STATUS
        params = (actor_id, limit, offset)

    # Step 2: SELECT V045 (statement-timeout guarded inside helper).
    # 步驟 2：SELECT V045（helper 內含 statement-timeout 守門）。
    rows, err = await async_safe_pg_select_fn(sql, params)

    # Step 3: PG err → 200 + degraded (mirrors pre-extract behaviour).
    # 步驟 3：PG err → 200 + degraded（鏡像抽出前行為）。
    if err is not None:
        return replay_response_envelope_fn(
            data={
                "actor_id": actor_id,
                "experiments": [],
                "limit": limit,
                "offset": offset,
                "status_filter": status_filter,
                "wiring_status": "degraded",
            },
            degraded=True,
            reason=err,
        )

    # Step 4: map rows to JSON-serialisable dicts and wrap envelope.
    # 步驟 4：rows 轉 JSON 可序列化 dict 並包 envelope。
    experiments = [_row_to_experiment_dict(r) for r in rows]
    return replay_response_envelope_fn({
        "actor_id": actor_id,
        "experiments": experiments,
        "limit": limit,
        "offset": offset,
        "status_filter": status_filter,
        "wiring_status": "pg_path_active",
    })


__all__ = [
    "list_replay_runs_for_actor",
]
