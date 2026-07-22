"""
MODULE_NOTE
模塊用途：
  L2 P4 online-FDR 的 debit↔demo binding + wealth 唯讀 route（PA P4 設計 §7）。
  獨立新檔，讓 ``layer2_routes.py`` 與本檔各自保留聚焦職責及現行 2000 行
  review/split 門檻內的空間。route 薄：parse → call
  （l2_alpha_wealth_store）→ format；業務邏輯在 store / reconciler 層。

主要端點：
  - POST /api/v1/paper/layer2/fdr/bind-demo：operator 把一筆 pending debit 綁到
    demo 部署 cell（reconciler 據此起算 forward-OOS 與 round-trips）。WRITE =
    operator-scope（reuse require_scope_and_operator "ai_budget:write"，auth 第一行）。
  - GET  /api/v1/paper/layer2/fdr/wealth：唯讀 wealth 餘額 + debit_state 投影
    （authenticated read，與 /orchestrator/status 同級，不加 operator scope）。

依賴：main_legacy（auth）、l2_alpha_wealth_store（同步 psycopg2 → asyncio.to_thread）。

硬邊界：
  - 0 交易面：無 order / lease / promote_tier / live-config 寫點（grep target）。
  - binding 是 append-only operator_adjustment 事件；不 UPDATE 既有帳本 row。
  - store 不可達 → 503（fail-closed，不偽裝成功）；debit 不存在 → 404。
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from . import l2_alpha_wealth_store as _store
from . import main_legacy as base

logger = logging.getLogger("l2_fdr_routes")

fdr_router = APIRouter(
    prefix="/api/v1/paper/layer2/fdr",
    tags=["Layer2 FDR"],
)


def _fdr_response(
    data: Any,
    action_result: str = "success",
    reason_codes: list[str] | None = None,
) -> dict[str, Any]:
    """envelope 與 layer2_routes._layer2_response 同形（前端零新解析面）。"""
    return {
        "api_version": "v1",
        "action_result": action_result,
        "reason_codes": reason_codes or [],
        "data_category": "paper_simulated",
        "is_simulated": True,
        "module": "layer2_online_fdr",
        "data": data,
    }


class FdrBindDemoRequest(BaseModel):
    """POST /fdr/bind-demo 請求（PA §7：debit↔demo 部署 binding）。"""

    debit_id: str = Field(min_length=1, max_length=64)
    demo_strategy: str = Field(min_length=1, max_length=64)
    demo_symbol: str = Field(min_length=1, max_length=30)
    # ISO-8601；起算 forward-OOS 日曆天數的錨點（reconciler 嚴格按此 + cell 查 fills）。
    demo_deployed_at: str = Field(min_length=1, max_length=64)


def _parse_deployed_at(raw: str) -> dt.datetime:
    """ISO-8601 → aware UTC datetime；無法解析 / naive 無時區 → 422（不猜時區）。

    為什麼拒 naive：demo_deployed_at 是 ≥21d forward-OOS 的起算錨點，時區歧義會
    平移結算邊界；binding 是 operator 動作，要求顯式 UTC 並不苛刻。
    """
    try:
        parsed = dt.datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"reason_codes": ["demo_deployed_at_unparseable"]},
        ) from exc
    if parsed.tzinfo is None:
        raise HTTPException(
            status_code=422,
            detail={"reason_codes": ["demo_deployed_at_naive_timezone"]},
        )
    return parsed.astimezone(dt.timezone.utc)


@fdr_router.post("/bind-demo")
async def bind_demo(
    req: FdrBindDemoRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """operator 綁定一筆 debit 到 demo 部署 cell（append operator_adjustment 事件）。

    WRITE = operator-scope：binding 決定該債能否被 reconciler 結算（refund 觸發面），
    任何已認證 viewer 不得寫——auth 必須是 handler 第一行（E3-E1 既有結論）。
    """
    base.require_scope_and_operator(actor, "ai_budget:write")
    deployed_at = _parse_deployed_at(req.demo_deployed_at)
    # store 是同步 psycopg2 → to_thread（control API event loop 不可被 DB I/O 阻塞）。
    res = await asyncio.to_thread(
        _store.record_demo_binding,
        debit_id=req.debit_id,
        demo_strategy=req.demo_strategy,
        demo_symbol=req.demo_symbol,
        demo_deployed_at=deployed_at,
        actor_id=str(getattr(actor, "actor_id", "operator")),
    )
    if not res.get("ok"):
        err = str(res.get("error", "store_unavailable"))
        if err == "debit_not_found":
            raise HTTPException(
                status_code=404,
                detail={"reason_codes": ["debit_not_found"], "debit_id": req.debit_id},
            )
        # db_unavailable / store_unavailable → 503（fail-closed，不偽裝成功）。
        raise HTTPException(
            status_code=503,
            detail={"reason_codes": ["alpha_wealth_store_unavailable"]},
        )
    return _fdr_response(res)


@fdr_router.get("/wealth")
async def get_wealth(
    family_id: str | None = Query(default=None, max_length=128),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """唯讀 wealth 餘額 + debit_state 投影（per-family SUM + view rows）。"""
    try:
        summary = await asyncio.to_thread(
            _store.load_wealth_summary, family_id
        )
    except _store.AlphaWealthStoreError:
        raise HTTPException(
            status_code=503,
            detail={"reason_codes": ["alpha_wealth_store_unavailable"]},
        ) from None
    return _fdr_response(summary)


__all__ = ["fdr_router", "FdrBindDemoRequest"]
