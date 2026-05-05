"""REF-20 Sprint B1 R0-T0 — GET /api/v1/replay/status endpoint logic extraction.
REF-20 Sprint B1 R0-T0 — GET /api/v1/replay/status endpoint 邏輯抽出。

MODULE_NOTE (EN):
    Sprint B1 R0-T0 (2026-05-05) extraction. Owns the
    ``GET /api/v1/replay/status`` business logic so the thin handler in
    ``app/replay_routes.py`` keeps under the CLAUDE.md §九 1500 LOC hard
    cap. PA design report `2026-05-05--ref20_sprint_b_task_dag.md` §11.3
    requires R0-T0 LOC release before R4 + R5 IMPL can land.

    What this module does:
      - ``query_active_run_via_pg(*, actor_id, async_safe_pg_select_fn)
        -> Tuple[Optional[dict], Optional[str]]`` coroutine that tries
        the PG path:
          1. SELECTs V045 ``replay.run_state`` for ``actor_id`` with
             ``status IN ('starting','running')``, ordered DESC by
             ``started_at`` (latest if multiple — in practice cap=1).
          2. Returns ``(snapshot_dict, None)`` on found,
             ``(None, None)`` on PG OK + 0 row (caller renders
             ``is_idle=True``), ``(None, err)`` on PG err (caller falls
             back to in-memory dict).

    The in-memory fallback path stays in ``replay_routes.py`` because it
    touches module-level state (``_ACTIVE_RUNS`` + ``_ACTIVE_RUNS_LOCK``)
    that is the legitimate source of truth for that fallback layer.

    What this module does NOT do (out of scope):
      - In-memory fallback (caller-owned via ``_ACTIVE_RUNS`` dict).
      - Auth scope check (caller's ``Depends(current_actor)`` is enough;
        read-only own-status query, no write scope required).
      - Envelope wrap (caller picks ``replay_response_envelope`` shape
        based on PG-success vs in-memory-fallback branch).

MODULE_NOTE (中):
    Sprint B1 R0-T0（2026-05-05）抽出。擁有 ``GET /api/v1/replay/status``
    業務邏輯，使 ``app/replay_routes.py`` 薄 handler 守住 CLAUDE.md
    §九 1500 LOC 硬上限。PA design report ``2026-05-05--ref20_sprint_b
    _task_dag.md`` §11.3 要求 R0-T0 LOC 釋放後 R4+R5 IMPL 才可進。

    本 module 做的事：
      - ``query_active_run_via_pg(...)`` coroutine 試 PG 路徑，回傳
        ``(snapshot_dict, None)`` / ``(None, None)`` / ``(None, err)``。

    in-memory fallback 路徑留在 ``replay_routes.py``，因其觸碰 module-
    level 狀態（``_ACTIVE_RUNS`` + ``_ACTIVE_RUNS_LOCK``），那是該
    fallback 層的合法 SoT。

    本 module 不做（範圍外）：
      - In-memory fallback（caller 透過 ``_ACTIVE_RUNS`` dict 持）。
      - Auth scope 檢查（caller 的 ``Depends(current_actor)`` 足夠；
        own-status 只讀查詢，不需 write scope）。
      - Envelope wrap（caller 依 PG-success vs in-memory-fallback 分支
        選 ``replay_response_envelope`` shape）。

SPEC: docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md §6.R3
PA Plan: docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-05--ref20_sprint_b_task_dag.md §11.3
V045 schema: sql/migrations/V045__replay_run_state.sql
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── SQL constant / SQL 常量 ─────────────────────────────────────────

# V045 ``replay.run_state`` SELECT for the per-actor active-run probe.
# 8 columns: run_id, manifest_id, status, subprocess_pid, started_at_ms,
# output_path, runtime_environment, idempotency_key. ``LIMIT 1`` matches
# V3 §5 per-actor active cap = 1; ``ORDER BY started_at DESC`` is
# defense-in-depth in case multi-row drift ever occurs.
# V045 ``replay.run_state`` SELECT，per-actor active-run probe。
# 8 欄：run_id, manifest_id, status, subprocess_pid, started_at_ms,
# output_path, runtime_environment, idempotency_key。``LIMIT 1`` 對齊
# V3 §5 per-actor active cap = 1；``ORDER BY started_at DESC`` 為
# multi-row 漂移時的縱深防禦。
_ACTIVE_RUN_SQL = """
SELECT run_id::text, manifest_id::text, status,
       subprocess_pid,
       EXTRACT(EPOCH FROM started_at)*1000 AS started_at_ms,
       output_path, runtime_environment,
       idempotency_key
  FROM replay.run_state
 WHERE actor_id = %s
   AND status IN ('starting','running')
 ORDER BY started_at DESC
 LIMIT 1;
"""


# ─── Public coroutine: query_active_run_via_pg ────────────────────────


async def query_active_run_via_pg(
    *,
    actor_id: str,
    async_safe_pg_select_fn: Callable[
        [str, tuple], Awaitable[Tuple[list, Optional[str]]]
    ],
) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
    """Query V045 for the actor's active run (R0-T0 thin extract).
    查詢 V045 取得 actor 的 active run（R0-T0 thin extract）。

    The thin route handler in ``app/replay_routes.py`` calls this then:
      - On ``(snapshot, None)``: caller wraps in envelope with
        ``wiring_status='pg_path_active'`` + ``is_idle=False``.
      - On ``(None, None)``: caller wraps with ``is_idle=True`` and
        ``active_run=None`` (PG OK + 0 active run is canonical).
      - On ``(None, err)``: caller falls back to in-memory ``_ACTIVE_RUNS``
        dict and wraps with ``degraded=True`` + ``reason=err``.

    Args:
        actor_id: caller's ``str(actor.actor_id)``.
        async_safe_pg_select_fn: ``app.replay_routes._async_safe_pg_select``
            (returns ``(rows, err)`` tuple, statement-timeout guarded).

    Returns / 回傳:
        ``(snapshot_dict, None)`` on found;
        ``(None, None)`` on PG OK + 0 row;
        ``(None, err)`` on PG err (caller falls back).

    snapshot_dict keys / snapshot_dict 鍵:
        run_id / experiment_id (None — V045 stores manifest_id; caller
        joins V049 if needed) / manifest_id / status / subprocess_pid /
        started_at_ms / output_path / runtime_environment /
        idempotency_key / actor_id.
    """
    rows, err = await async_safe_pg_select_fn(_ACTIVE_RUN_SQL, (actor_id,))

    if err is not None:
        # PG outage / V045 absent → caller falls back to in-memory dict.
        # PG outage / V045 缺 → caller fallback in-memory dict。
        return None, err

    if not rows:
        # PG OK + 0 active run → canonical idle (no fallback needed).
        # PG OK + 0 active run → canonical idle（無需 fallback）。
        return None, None

    row = rows[0]
    snapshot = {
        "run_id": row[0],
        # V045 stores manifest_id only; experiment_id is upstream V049
        # column. Same projection as pre-extract behaviour.
        # V045 只存 manifest_id；experiment_id 屬上游 V049 欄。與抽出前
        # projection 一致。
        "experiment_id": None,
        "manifest_id": row[1],
        "status": row[2],
        "subprocess_pid": row[3],
        "started_at_ms": int(row[4]) if row[4] is not None else None,
        "output_path": row[5],
        "runtime_environment": row[6],
        "idempotency_key": row[7],
        "actor_id": actor_id,
    }
    return snapshot, None


__all__ = [
    "query_active_run_via_pg",
]
