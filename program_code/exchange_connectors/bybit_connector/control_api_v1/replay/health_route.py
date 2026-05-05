"""REF-20 Sprint B1 R0-T0 — GET /api/v1/replay/health endpoint logic extraction.
REF-20 Sprint B1 R0-T0 — GET /api/v1/replay/health endpoint 邏輯抽出。

MODULE_NOTE (EN):
    Sprint B1 R0-T0 (2026-05-05) extraction. Owns the
    ``GET /api/v1/replay/health`` business logic so the thin handler in
    ``app/replay_routes.py`` keeps under the CLAUDE.md §九 1500 LOC hard
    cap. PA design report `2026-05-05--ref20_sprint_b_task_dag.md` §11.3
    requires R0-T0 LOC release before R4 (UI enable) + R5 (real
    decision/risk replay path) IMPL can land.

    Why this module exists (PA push back):
      ``replay_routes.py`` reached EXACT 1500 LOC after Sprint A R3 round 6
      hotfix wiring. R4/R5 IMPL adds ~800 LOC. Without R0-T0 thin-handler
      extraction, Sprint B violates §九 1500 LOC hard cap.

    What this module does:
      - ``aggregate_replay_health(*, async_safe_pg_select_fn,
        compute_replay_health_state_fn, replay_response_envelope_fn)
        -> dict`` coroutine that:
          1. SELECTs V045/V049 schema presence via two EXISTS sub-queries
             (single SQL round-trip, fail-closed on PG outage).
          2. Calls ``route_helpers.compute_replay_health_state`` with the
             PG row + err to derive ``wiring_status`` + sub-keys.
          3. Wraps in ``replay_response_envelope`` with ``degraded=True``
             when ``wiring_status != "ready"`` so monitoring can fail
             fast without parsing the inner dict.

    What this module does NOT do (out of scope):
      - PG xact lifecycle (caller-owned via ``async_safe_pg_select_fn``).
      - Auth scope check (caller's ``Depends(current_actor)`` is enough;
        no write scope required for read-only probe).
      - Binary release profile env probing (covered inside
        ``compute_replay_health_state``).

MODULE_NOTE (中):
    Sprint B1 R0-T0（2026-05-05）抽出。擁有
    ``GET /api/v1/replay/health`` 業務邏輯，使 ``app/replay_routes.py``
    薄 handler 守住 CLAUDE.md §九 1500 LOC 硬上限。PA design report
    ``2026-05-05--ref20_sprint_b_task_dag.md`` §11.3 要求 R0-T0 LOC
    釋放後 R4（UI enable）+ R5（real decision/risk replay path）IMPL
    才可進。

    本 module 為何存在（PA push back）：
      ``replay_routes.py`` 在 Sprint A R3 round 6 hotfix wiring 後達 EXACT
      1500 LOC。R4/R5 IMPL 加 ~800 LOC。若不做 R0-T0 thin-handler 抽出，
      Sprint B 將違反 §九 1500 LOC 硬上限。

    本 module 做的事：
      - ``aggregate_replay_health(...)`` coroutine 實作 3 步驟。

    本 module 不做（範圍外）：
      - PG xact 生命周期（caller 透過 ``async_safe_pg_select_fn`` 持）。
      - Auth scope 檢查（caller 的 ``Depends(current_actor)`` 足夠；
        read-only probe 不需 write scope）。
      - Binary release profile env probing（由
        ``compute_replay_health_state`` 內部覆蓋）。

SPEC: docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md §6.R1 acceptance
PA Plan: docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-05--ref20_sprint_b_task_dag.md §11.3
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── SQL constants / SQL 常量 ─────────────────────────────────────────

# Single round-trip SQL: probes both V045 ``replay.run_state`` + V049
# ``replay.experiments`` schema presence. Returns one row of two booleans
# so ``compute_replay_health_state`` can derive the aggregate status.
# 單次 round-trip SQL：同時探 V045 ``replay.run_state`` 與 V049
# ``replay.experiments`` schema 存在性。返回一列兩布林值供
# ``compute_replay_health_state`` 推斷聚合狀態。
_SCHEMA_PRESENCE_SQL = """
SELECT
    EXISTS(
        SELECT 1 FROM information_schema.tables
         WHERE table_schema='replay'
           AND table_name='run_state' LIMIT 1),
    EXISTS(
        SELECT 1 FROM information_schema.tables
         WHERE table_schema='replay'
           AND table_name='experiments' LIMIT 1);
"""


# ─── Public coroutine: aggregate_replay_health ────────────────────────


async def aggregate_replay_health(
    *,
    async_safe_pg_select_fn: Callable[
        [str, tuple], Awaitable[Tuple[list, Optional[str]]]
    ],
    compute_replay_health_state_fn: Callable[..., dict[str, Any]],
    replay_response_envelope_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Run the full GET /health aggregation flow (R0-T0 thin extract).
    執行完整 GET /health 聚合流程（R0-T0 thin extract）。

    Caller is the thin route handler in ``app/replay_routes.py`` which
    only does the auth ``Depends`` + this call + return the envelope.

    Args:
        async_safe_pg_select_fn: ``app.replay_routes._async_safe_pg_select``
            (returns ``(rows, err)`` tuple, statement-timeout guarded).
        compute_replay_health_state_fn: ``replay.route_helpers
            .compute_replay_health_state`` (returns dict with
            ``wiring_status`` + sub-keys).
        replay_response_envelope_fn: ``replay.route_helpers
            .replay_response_envelope`` (wraps in ``data`` envelope with
            optional ``degraded`` + ``reason``).

    Returns / 回傳:
        dict — fully-formed envelope ready for FastAPI to serialise.
        Caller does NOT raise HTTPException for any path here (degraded
        is reported in-band via ``degraded=True`` to keep ``/health`` a
        200 endpoint that can be probed by monitoring even on PG outage).
    """
    # Step 1: probe V045/V049 schema presence in a single PG round-trip.
    # 步驟 1：單次 PG round-trip 探 V045/V049 schema 存在。
    rows, err = await async_safe_pg_select_fn(_SCHEMA_PRESENCE_SQL, ())

    # Step 2: aggregate via compute_replay_health_state (binary resolve +
    # OPENCLAW_DATA_DIR writability + V045/V049 + release profile env).
    # 步驟 2：由 compute_replay_health_state 聚合（binary resolve +
    # OPENCLAW_DATA_DIR 可寫 + V045/V049 + release profile env）。
    health = compute_replay_health_state_fn(rows=rows or [], pg_err=err)

    # Step 3: degraded=True iff wiring_status != "ready"; surface inner
    # status as ``reason`` for monitoring fail-fast (no need to parse
    # inner dict).
    # 步驟 3：wiring_status != "ready" 時 degraded=True；以 ``reason``
    # 揭內部狀態使監控 fail-fast（不必解內部 dict）。
    degraded = health["wiring_status"] != "ready"
    return replay_response_envelope_fn(
        data=health,
        degraded=degraded,
        reason=None if not degraded else f"wiring_status:{health['wiring_status']}",
    )


__all__ = [
    "aggregate_replay_health",
]
