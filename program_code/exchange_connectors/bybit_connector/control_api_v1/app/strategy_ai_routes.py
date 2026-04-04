"""Strategy AI & Demo Routes — Demo connector, AI consultation, Telegram (TD-02 split).
策略 AI 和 Demo 路由 — Demo 連接器、AI 諮詢、Telegram。

PYO3-BYBIT: demo/* endpoints now use Rust BybitClient (PyO3 bridge) as primary,
with Python BybitDemoConnector as fallback if Rust bridge is unavailable.
PYO3-BYBIT: demo/* 端點現在使用 Rust BybitClient（PyO3 橋接）作為主路徑，
Python BybitDemoConnector 作為 Rust 橋接不可用時的降級回退。
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, HTTPException

from . import main_legacy as base
from .strategy_wiring import (
    phase2_router,
    DEMO_CONNECTOR,
    ORCHESTRATOR,
    TELEGRAM,
    _envelope,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rust PyO3 bridge (PYO3-BYBIT) — lazy singleton
# Rust PyO3 橋接 — 懶加載單例
# ---------------------------------------------------------------------------
_RUST_BYBIT_CLIENT = None
_RUST_BRIDGE_AVAILABLE = None  # None = not checked yet / None = 尚未檢查


def _get_rust_client():
    """Get or create the Rust BybitClient singleton. Returns None if unavailable.
    獲取或創建 Rust BybitClient 單例。不可用時返回 None。"""
    global _RUST_BYBIT_CLIENT, _RUST_BRIDGE_AVAILABLE
    if _RUST_BRIDGE_AVAILABLE is False:
        return None
    if _RUST_BYBIT_CLIENT is not None:
        return _RUST_BYBIT_CLIENT
    try:
        from openclaw_core import BybitClient
        _RUST_BYBIT_CLIENT = BybitClient()
        _RUST_BRIDGE_AVAILABLE = True
        logger.info("Rust BybitClient initialized (PyO3 bridge active) / Rust BybitClient 已初始化")
        return _RUST_BYBIT_CLIENT
    except Exception as e:
        _RUST_BRIDGE_AVAILABLE = False
        logger.warning(f"Rust BybitClient unavailable, using Python fallback: {e}")
        return None


# ── Telegram Status Route / Telegram 状态路由 ──

@phase2_router.get("/telegram/status")
async def get_telegram_status(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """Get Telegram alerter status / 获取 Telegram 告警器状态"""
    if TELEGRAM is None:
        return _envelope({"enabled": False, "reason": "module not loaded"})
    return _envelope(TELEGRAM.get_stats())


# ── AI Consultation Route / AI 咨询路由 ──

@phase2_router.get("/ai/status")
async def get_ai_consultation_status(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get AI consultation availability status.
    获取 AI 咨询可用状态。
    """
    try:
        result = ORCHESTRATOR.request_ai_analysis("status_check")
        return _envelope({
            "ai_consultation_enabled": ORCHESTRATOR._ai_consultation_enabled,
            "analysis_result": result,
        })
    except Exception:
        logger.exception("AI status check error / AI 状态检查异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


# ── Bybit Demo Routes / Bybit Demo 路由 ──

@phase2_router.get("/demo/status")
async def get_demo_status(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """Get Bybit Demo connector status / 获取 Bybit Demo 连接器状态"""
    if DEMO_CONNECTOR is None:
        return _envelope({"enabled": False})
    try:
        status = DEMO_CONNECTOR.get_status()
        return _envelope(status)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")


@phase2_router.get("/demo/balance")
async def get_demo_balance(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """Get Bybit Demo account balance / 获取 Bybit Demo 账户余额"""
    # Rust-first path (PYO3-BYBIT) / Rust 優先路徑
    rc = _get_rust_client()
    if rc is not None:
        try:
            wallet = rc.refresh_balance()
            return _envelope({"source": "rust_engine", **wallet})
        except Exception as e:
            logger.warning(f"Rust balance failed, falling back to Python: {e}")
    # Python fallback / Python 降級回退
    if DEMO_CONNECTOR is None or not DEMO_CONNECTOR.is_enabled:
        return _envelope({"enabled": False})
    try:
        result = DEMO_CONNECTOR.get_wallet_balance()
        return _envelope(result)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")


@phase2_router.get("/demo/positions")
async def get_demo_positions(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """Get Bybit Demo open positions / 获取 Bybit Demo 持仓"""
    # Rust-first path (PYO3-BYBIT) / Rust 優先路徑
    rc = _get_rust_client()
    if rc is not None:
        try:
            positions = rc.get_positions("linear")
            return _envelope({"source": "rust_engine", "list": positions, "count": len(positions)})
        except Exception as e:
            logger.warning(f"Rust positions failed, falling back to Python: {e}")
    # Python fallback / Python 降級回退
    if DEMO_CONNECTOR is None or not DEMO_CONNECTOR.is_enabled:
        return _envelope({"enabled": False})
    try:
        params: dict[str, Any] = {"category": "linear", "settleCoin": "USDT"}
        result = DEMO_CONNECTOR._request("GET", "/v5/position/list", params)
        return _envelope(result)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")


@phase2_router.get("/demo/orders")
async def get_demo_orders(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """
    Get Bybit Demo open orders (regular + conditional/stop).
    获取 Bybit Demo 活跃订单（普通订单 + 条件止损单合并返回）。
    """
    # Rust-first path (PYO3-BYBIT) / Rust 優先路徑
    rc = _get_rust_client()
    if rc is not None:
        try:
            orders = rc.get_active_orders("linear")
            return _envelope({
                "source": "rust_engine",
                "retCode": 0,
                "result": {"list": orders},
                "regular_count": len(orders),
                "conditional_count": 0,
            })
        except Exception as e:
            logger.warning(f"Rust orders failed, falling back to Python: {e}")
    # Python fallback / Python 降級回退
    if DEMO_CONNECTOR is None or not DEMO_CONNECTOR.is_enabled:
        return _envelope({"enabled": False})
    try:
        regular = DEMO_CONNECTOR.get_open_orders(category="linear")
        regular_list = []
        if regular.get("retCode") == 0:
            regular_list = (regular.get("result") or {}).get("list") or []

        # 条件单（止损单）通过 orderFilter=StopOrder 单独查询
        # Conditional orders (stop-loss) are queried separately via orderFilter=StopOrder
        conditional_list = []
        try:
            cond = DEMO_CONNECTOR.get_conditional_orders(category="linear")
            if cond.get("retCode") == 0:
                conditional_list = (cond.get("result") or {}).get("list") or []
        except Exception:
            logger.warning("Failed to fetch conditional orders / 获取条件单失败")

        for o in conditional_list:
            o["_orderFilter"] = "StopOrder"
        merged = regular_list + conditional_list

        return _envelope({
            "retCode": 0,
            "result": {"list": merged},
            "regular_count": len(regular_list),
            "conditional_count": len(conditional_list),
        })
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")


@phase2_router.get("/demo/fills")
async def get_demo_fills(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """Get Bybit Demo recent executions / 获取 Bybit Demo 最近成交"""
    # Rust-first path (PYO3-BYBIT) / Rust 優先路徑
    rc = _get_rust_client()
    if rc is not None:
        try:
            fills = rc.get_executions("linear", limit=50)
            return _envelope({"source": "rust_engine", "list": fills, "count": len(fills)})
        except Exception as e:
            logger.warning(f"Rust fills failed, falling back to Python: {e}")
    # Python fallback / Python 降級回退
    if DEMO_CONNECTOR is None or not DEMO_CONNECTOR.is_enabled:
        return _envelope({"enabled": False})
    try:
        result = DEMO_CONNECTOR.get_executions(category="linear", limit=50)
        return _envelope(result)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")
