from __future__ import annotations

"""
Stock/ETF IBKR readiness router.

This router is intentionally display-only. It may query the local Rust IPC
fixture for `stock_etf.get_readiness`, but it never creates secret slots,
contacts IBKR, or exposes paper/live order actions.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Response
from fastapi.responses import RedirectResponse

from . import main_legacy as base
from .ipc_client import EngineIPCClient
from .stock_etf_status_normalizers import (
    _NO_STORE_HEADERS,
    _normalize_evidence_status,
    _normalize_lane_status,
    _normalize_paper_status,
    _normalize_readiness,
    _normalize_shadow_status,
    _normalize_universe_status,
)

logger = logging.getLogger(__name__)

stock_etf_router = APIRouter(
    prefix="/api/v1/stock-etf",
    tags=["Stock ETF IBKR / 股票 ETF IBKR"],
)

_IPC_CLIENT: EngineIPCClient | None = None
_LANE_STATUS_METHOD = "stock_etf.get_lane_status"
_READINESS_METHOD = "stock_etf.get_readiness"
_EVIDENCE_STATUS_METHOD = "stock_etf.get_evidence_status"
_UNIVERSE_STATUS_METHOD = "stock_etf.get_universe_status"
_SHADOW_STATUS_METHOD = "stock_etf.get_shadow_status"
_PAPER_STATUS_METHOD = "stock_etf.get_paper_status"


def _apply_no_store_headers(response: Response) -> None:
    for key, value in _NO_STORE_HEADERS.items():
        response.headers[key] = value


async def _get_ipc() -> EngineIPCClient | None:
    global _IPC_CLIENT
    if _IPC_CLIENT is None:
        client = EngineIPCClient()
        try:
            connected = await client.connect()
        except Exception as exc:
            logger.warning("stock_etf: IPC connect failed: %s", exc)
            return None
        if not connected or not client.is_connected:
            logger.warning("stock_etf: IPC connect returned disconnected client")
            return None
        _IPC_CLIENT = client
    return _IPC_CLIENT


async def _query_stock_etf_lane_status(
    ipc: EngineIPCClient | None,
) -> tuple[dict[str, Any], str | None]:
    if ipc is None:
        return ({}, "ipc_unavailable")
    try:
        raw = await ipc.call(_LANE_STATUS_METHOD, params={})
    except Exception as exc:
        logger.warning("stock_etf: %s failed: %s", _LANE_STATUS_METHOD, exc)
        return ({}, f"ipc_error:{type(exc).__name__}")
    return (raw if isinstance(raw, dict) else {}, None)


async def _query_stock_etf_readiness(
    ipc: EngineIPCClient | None,
) -> tuple[dict[str, Any], str | None]:
    if ipc is None:
        return ({}, "ipc_unavailable")
    try:
        raw = await ipc.call(_READINESS_METHOD, params={})
    except Exception as exc:
        logger.warning("stock_etf: %s failed: %s", _READINESS_METHOD, exc)
        return ({}, f"ipc_error:{type(exc).__name__}")
    return (raw if isinstance(raw, dict) else {}, None)


async def _query_stock_etf_evidence_status(
    ipc: EngineIPCClient | None,
) -> tuple[dict[str, Any], str | None]:
    if ipc is None:
        return ({}, "ipc_unavailable")
    try:
        raw = await ipc.call(_EVIDENCE_STATUS_METHOD, params={})
    except Exception as exc:
        logger.warning("stock_etf: %s failed: %s", _EVIDENCE_STATUS_METHOD, exc)
        return ({}, f"ipc_error:{type(exc).__name__}")
    return (raw if isinstance(raw, dict) else {}, None)


async def _query_stock_etf_universe_status(
    ipc: EngineIPCClient | None,
) -> tuple[dict[str, Any], str | None]:
    if ipc is None:
        return ({}, "ipc_unavailable")
    try:
        raw = await ipc.call(_UNIVERSE_STATUS_METHOD, params={})
    except Exception as exc:
        logger.warning("stock_etf: %s failed: %s", _UNIVERSE_STATUS_METHOD, exc)
        return ({}, f"ipc_error:{type(exc).__name__}")
    return (raw if isinstance(raw, dict) else {}, None)


async def _query_stock_etf_shadow_status(
    ipc: EngineIPCClient | None,
) -> tuple[dict[str, Any], str | None]:
    if ipc is None:
        return ({}, "ipc_unavailable")
    try:
        raw = await ipc.call(_SHADOW_STATUS_METHOD, params={})
    except Exception as exc:
        logger.warning("stock_etf: %s failed: %s", _SHADOW_STATUS_METHOD, exc)
        return ({}, f"ipc_error:{type(exc).__name__}")
    return (raw if isinstance(raw, dict) else {}, None)


async def _query_stock_etf_paper_status(
    ipc: EngineIPCClient | None,
) -> tuple[dict[str, Any], str | None]:
    if ipc is None:
        return ({}, "ipc_unavailable")
    try:
        raw = await ipc.call(_PAPER_STATUS_METHOD, params={})
    except Exception as exc:
        logger.warning("stock_etf: %s failed: %s", _PAPER_STATUS_METHOD, exc)
        return ({}, f"ipc_error:{type(exc).__name__}")
    return (raw if isinstance(raw, dict) else {}, None)


@stock_etf_router.get("/lane-status")
async def get_stock_etf_lane_status(
    response: Response,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Read-only Stock/ETF lane-status surface for the GUI."""
    del actor
    _apply_no_store_headers(response)
    ipc = await _get_ipc()
    raw, reason = await _query_stock_etf_lane_status(ipc)
    return {
        "ok": True,
        "data": _normalize_lane_status(raw, reason),
        "is_simulated": False,
        "data_category": "stock_etf_lane_status",
    }


@stock_etf_router.get("/readiness")
async def get_stock_etf_readiness(
    response: Response,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Read-only Stock/ETF IBKR readiness surface for the GUI."""
    del actor
    _apply_no_store_headers(response)
    ipc = await _get_ipc()
    raw, reason = await _query_stock_etf_readiness(ipc)
    return {
        "ok": True,
        "data": _normalize_readiness(raw, reason),
        "is_simulated": False,
        "data_category": "stock_etf_readiness",
    }


@stock_etf_router.get("/evidence-status")
async def get_stock_etf_evidence_status(
    response: Response,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Read-only Stock/ETF evidence-status surface for the GUI."""
    del actor
    _apply_no_store_headers(response)
    ipc = await _get_ipc()
    raw, reason = await _query_stock_etf_evidence_status(ipc)
    return {
        "ok": True,
        "data": _normalize_evidence_status(raw, reason),
        "is_simulated": False,
        "data_category": "stock_etf_evidence_status",
    }


@stock_etf_router.get("/universe-status")
async def get_stock_etf_universe_status(
    response: Response,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Read-only Stock/ETF PIT-universe status surface for the GUI."""
    del actor
    _apply_no_store_headers(response)
    ipc = await _get_ipc()
    raw, reason = await _query_stock_etf_universe_status(ipc)
    return {
        "ok": True,
        "data": _normalize_universe_status(raw, reason),
        "is_simulated": False,
        "data_category": "stock_etf_universe_status",
    }


@stock_etf_router.get("/shadow-status")
async def get_stock_etf_shadow_status(
    response: Response,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Read-only Stock/ETF shadow-model status surface for the GUI."""
    del actor
    _apply_no_store_headers(response)
    ipc = await _get_ipc()
    raw, reason = await _query_stock_etf_shadow_status(ipc)
    return {
        "ok": True,
        "data": _normalize_shadow_status(raw, reason),
        "is_simulated": False,
        "data_category": "stock_etf_shadow_status",
    }


@stock_etf_router.get("/paper-status")
async def get_stock_etf_paper_status(
    response: Response,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Read-only Stock/ETF paper-lifecycle status surface for the GUI."""
    del actor
    _apply_no_store_headers(response)
    ipc = await _get_ipc()
    raw, reason = await _query_stock_etf_paper_status(ipc)
    return {
        "ok": True,
        "data": _normalize_paper_status(raw, reason),
        "is_simulated": False,
        "data_category": "stock_etf_paper_status",
    }


@stock_etf_router.get("", include_in_schema=False)
async def stock_etf_tab_redirect(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> RedirectResponse:
    del actor
    return RedirectResponse(url="/static/tab-stock-etf.html", headers=_NO_STORE_HEADERS)
