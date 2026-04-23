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


def _read_leader_pid() -> int | None:
    """
    Read the leader PID from the flock sentinel file. Non-leader workers use
    this so `/status` can report truthful "scheduler is running, just not on
    this worker" semantics instead of the pre-FA-2 lie of {"started": False}.
    讀取 flock sentinel 中的 leader PID。Non-leader worker 用此返回誠實的
    「scheduler 仍在跑，只是不在本 worker 上」語意，取代 FA-2 修復前的
    謊話 {"started": False}。
    """
    from .edge_estimator_scheduler import _leader_lock_path  # noqa: PLC0415
    try:
        lock_path = _leader_lock_path()
        if not lock_path.exists():
            return None
        content = lock_path.read_text().strip()
        return int(content) if content else None
    except (ValueError, OSError):
        return None


@router.post("/trigger")
async def trigger_now(actor: Any = Depends(_get_auth_actor)) -> dict:
    """
    Synchronously re-run the JS estimator for all configured modes.
    對所有配置的 mode 同步重跑 JS 估計器。

    Operator-only (writes settings/edge_estimates*.json files).
    僅 Operator（寫入 settings/edge_estimates*.json）。

    EDGE-SCHEDULER-LEADER-1 follow-up (FA-2): under uvicorn --workers 4 only
    the leader worker holds a scheduler instance. Non-leader workers return
    503 *with the leader PID* so the operator can understand this isn't a
    dead scheduler — it's a routing miss. Round-robin will eventually land
    on the leader.
    EDGE-SCHEDULER-LEADER-1 FUP（FA-2）：4 worker 中只 leader 持實例。
    非 leader 回 503 附帶 leader PID，讓 operator 明白是路由未中而非 scheduler 死。
    uvicorn round-robin 最終會打到 leader。
    """
    _require_operator_role(actor)
    from .edge_estimator_scheduler import get_scheduler  # noqa: PLC0415

    sched = get_scheduler()
    if sched is None:
        leader_pid = _read_leader_pid()
        if leader_pid is not None:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"This uvicorn worker is not the scheduler leader "
                    f"(leader_pid={leader_pid}). Retry; round-robin will "
                    f"eventually hit the leader worker. "
                    f"/ 本 worker 非 scheduler leader（leader_pid={leader_pid}），請重試。"
                ),
            )
        raise HTTPException(
            status_code=503,
            detail=(
                "EdgeEstimatorScheduler not started on any worker — startup "
                "hook may have failed, or all workers failed leader election. "
                "/ 所有 worker 皆未啟 scheduler — 啟動 hook 失敗或選舉全滅。"
            ),
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

    EDGE-SCHEDULER-LEADER-1 follow-up (FA-2): non-leader workers read the
    flock sentinel and report `{started: True, is_leader: False, leader_pid}`
    instead of the pre-FA-2 lie of `{started: False}` (which made monitoring
    dashboards falsely alert that the scheduler died on 3/4 workers).
    EDGE-SCHEDULER-LEADER-1 FUP（FA-2）：非 leader worker 讀 flock sentinel，
    回 {started: True, is_leader: False, leader_pid}，取代 FA-2 修復前的
    {started: False} 謊話（會讓監控 3/4 worker 誤報 scheduler 死）。
    """
    import os  # noqa: PLC0415
    from .edge_estimator_scheduler import get_scheduler  # noqa: PLC0415
    sched = get_scheduler()
    if sched is not None:
        # Leader worker: real status + pid self-identification
        # Leader worker：真實 status + pid 自我標識
        return {**sched.status(), "is_leader": True, "leader_pid": os.getpid()}
    # Non-leader worker: truthful report via sentinel
    # Non-leader worker：透過 sentinel 誠實回報
    leader_pid = _read_leader_pid()
    if leader_pid is not None:
        return {
            "started": True,
            "is_leader": False,
            "leader_pid": leader_pid,
            "this_worker_pid": os.getpid(),
        }
    # Fallback: no sentinel readable (rare — leader died + crash-exit before
    # OS released the lock, or sentinel file was manually deleted).
    # Fallback：sentinel 讀不到（罕見，leader crash 未 OS 釋放，或檔案被手刪）。
    return {
        "started": False,
        "is_leader": False,
        "leader_pid": None,
        "this_worker_pid": os.getpid(),
    }
