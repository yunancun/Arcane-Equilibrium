from __future__ import annotations

"""
P1-7 B — Routes for the James-Stein edge estimator scheduler.
James-Stein 排程器的路由（IPC 熱觸發 + 狀態）。

  POST /api/v1/edge-estimator/trigger  — Operator-only synchronous re-run
  GET  /api/v1/edge-estimator/status   — read-only stats

The scheduler itself is started in main.py during _startup_integrity_check().
排程器在 main.py 啟動時由 _startup_integrity_check() 觸發。
"""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from .governance_routes import _require_operator_role, _get_auth_actor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/edge-estimator", tags=["edge-estimator"])


@router.post("/trigger")
async def trigger_now(actor: Any = Depends(_get_auth_actor)) -> dict:
    """
    Synchronously re-run the JS estimator for all configured modes.
    對所有配置的 mode 同步重跑 JS 估計器。

    Operator-only (writes settings/edge_estimates*.json files).
    僅 Operator（寫入 settings/edge_estimates*.json）。
    """
    _require_operator_role(actor)
    from .edge_estimator_scheduler import get_scheduler  # noqa: PLC0415

    sched = get_scheduler()
    if sched is None:
        raise HTTPException(
            status_code=503,
            detail="EdgeEstimatorScheduler not started yet — startup hook may have failed.",
        )
    # JS estimator does PG queries + math; offload to thread to keep loop free.
    # JS 估計器走 PG 查詢 + 計算，丟到 thread 避免阻塞事件迴圈
    results = await asyncio.to_thread(sched.trigger_now)
    return {"results": results}


@router.get("/status")
async def status(actor: Any = Depends(_get_auth_actor)) -> dict:
    """
    Return scheduler stats (runs / failures / last-run summary).
    返回排程器統計（runs / failures / 上次執行摘要）。
    """
    from .edge_estimator_scheduler import get_scheduler  # noqa: PLC0415
    sched = get_scheduler()
    if sched is None:
        return {"started": False}
    return sched.status()
