"""Strategy AI & Demo Routes — AI consultation, Telegram, Demo data read (TD-02 split).
策略 AI 和 Demo 路由 — AI 諮詢、Telegram、Demo 數據讀取。

All demo data reads use Rust PyO3 BybitClient exclusively.
All trading operations (close) go through Rust IPC.
Python BybitDemoConnector fallbacks removed — Rust is the sole exchange interface.

所有 Demo 數據讀取使用 Rust PyO3 BybitClient。
所有交易操作（平倉）通過 Rust IPC。
Python BybitDemoConnector 降級路徑已移除 — Rust 是唯一交易所接口。
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, HTTPException

from . import main_legacy as base
from .strategy_wiring import (
    phase2_router,
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
    """Get Bybit Demo connector status via PyO3 BybitClient / 通過 PyO3 獲取 Demo 狀態"""
    rc = _get_rust_client()
    if rc is None:
        return _envelope({"enabled": False, "source": "rust_engine"})
    return _envelope({
        "enabled": True,
        "source": "rust_engine",
        "has_credentials": rc.has_credentials(),
        "base_url": rc.base_url(),
    })


@phase2_router.get("/demo/balance")
async def get_demo_balance(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """Get Bybit Demo account balance via PyO3 BybitClient / 通過 PyO3 獲取 Demo 餘額"""
    rc = _get_rust_client()
    if rc is None:
        return _envelope({"enabled": False, "source": "rust_engine"})
    try:
        wallet = rc.refresh_balance()
        return _envelope({"source": "rust_engine", **wallet})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Bybit balance fetch failed: {exc}")


@phase2_router.get("/demo/positions")
async def get_demo_positions(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """Get Bybit Demo open positions via PyO3 BybitClient / 通過 PyO3 獲取 Demo 持倉"""
    rc = _get_rust_client()
    if rc is None:
        return _envelope({"enabled": False, "source": "rust_engine"})
    try:
        positions = rc.get_positions("linear")
        return _envelope({"source": "rust_engine", "list": positions, "count": len(positions)})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Bybit positions fetch failed: {exc}")


@phase2_router.get("/demo/orders")
async def get_demo_orders(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """
    Get Bybit Demo open orders via PyO3 BybitClient.
    通過 PyO3 BybitClient 獲取 Demo 活躍訂單。
    """
    rc = _get_rust_client()
    if rc is None:
        return _envelope({"enabled": False, "source": "rust_engine"})
    try:
        orders = rc.get_active_orders("linear")
        return _envelope({
            "source": "rust_engine",
            "retCode": 0,
            "result": {"list": orders},
            "regular_count": len(orders),
            "conditional_count": 0,
        })
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Bybit orders fetch failed: {exc}")


def _normalize_execution(f: dict) -> dict:
    """Remap Rust ExecutionInfo snake_case fields to Bybit camelCase so the GUI
    fallback chain (execQty || qty, execPrice || price, execFee || fee) finds them.
    Rust 序列化為 snake_case（exec_qty/exec_price/exec_fee），GUI 期望 camelCase，
    此函數將 Rust 格式轉換為 Bybit API 格式避免 qty/price 顯示 0。
    """
    if not isinstance(f, dict):
        return f
    return {
        **f,
        "execQty":   f.get("execQty")   or f.get("exec_qty"),
        "execPrice": f.get("execPrice") or f.get("exec_price"),
        "execFee":   f.get("execFee")   or f.get("exec_fee"),
        "execTime":  f.get("execTime")  or f.get("exec_time"),
        "side":      f.get("side")      or ("Buy" if f.get("is_long") else "Sell"),
    }


@phase2_router.post("/demo/positions/{symbol}/close")
async def post_demo_close_position(
    symbol: str,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    POST /api/v1/strategy/demo/positions/{symbol}/close
    通過 IPC close_position 平掉指定 symbol 的 Demo 倉位。
    執行路徑完全在 Rust 引擎內：
      1. Python 從 Bybit REST 查詢持倉（只讀），取得 is_long / qty 作為 hints
      2. IPC 帶 hints 傳給 Rust
      3. Rust 引擎直接 dispatch shadow reduce_only 市價單至 Bybit（不經 Python 下單）
      4. paper_state 有倉 → 走既有路徑；無倉 → 用 hints 平孤兒倉位

    Close a single Demo position by symbol. All trading execution happens inside Rust:
    Python only does a read-only REST lookup to supply is_long/qty hints.
    Rust dispatches the reduce_only market order via its own shadow channel.
    """
    from .governance_routes import _require_operator_role
    from .paper_trading_routes import _ipc_command
    _require_operator_role(actor)
    sym = symbol.upper()

    # Step 1: read-only lookup of exchange position to build hints for Rust.
    # Python 只查倉位資料（只讀），供 Rust 平孤兒倉位時使用。
    hint_is_long: bool | None = None
    hint_qty: float | None = None
    rc = _get_rust_client()
    if rc is not None:
        try:
            positions = rc.get_positions("linear")
            for p in positions:
                if p.get("symbol") == sym:
                    size = float(p.get("size") or p.get("qty") or 0)
                    if size > 0:
                        hint_is_long = p.get("side") == "Buy"
                        hint_qty = size
                    break
        except Exception as exc:
            logger.warning("demo close: position hint lookup failed for %s: %s", sym, exc)

    # If no position found anywhere (neither paper nor exchange), bail early.
    # 紙盤和交易所都沒有這個倉位，直接返回 404。
    if hint_qty is None or hint_qty <= 0:
        # Still send IPC — paper_state might track it even if REST doesn't.
        # REST 查不到，但 paper_state 可能有，還是發 IPC。
        pass

    # Step 2: send IPC — Rust handles the actual close order via shadow channel.
    # 發 IPC — Rust 引擎通過 shadow channel 執行平倉，Python 不介入下單。
    ipc_params: dict = {"symbol": sym}
    if hint_is_long is not None:
        ipc_params["is_long"] = hint_is_long
    if hint_qty is not None and hint_qty > 0:
        ipc_params["qty"] = hint_qty

    try:
        result = await _ipc_command("close_position", ipc_params)
    except Exception as exc:
        logger.error("IPC close_position failed for %s: %s", sym, exc)
        raise HTTPException(status_code=502, detail=f"IPC error: {exc}")

    # If no exchange position AND paper IPC also found nothing, return 404.
    # 交易所和紙盤都沒倉，回 404（避免謊報 closed=True）。
    if (hint_qty is None or hint_qty <= 0):
        raise HTTPException(
            status_code=404,
            detail=f"No position found for {sym} (neither paper state nor exchange) / 倉位不存在",
        )

    logger.warning(
        "close_position %s hint_is_long=%s hint_qty=%s — actor=%s",
        sym, hint_is_long, hint_qty, getattr(actor, "actor_id", "?"),
    )
    return _envelope({"symbol": sym, "closed": True, "source": "rust_engine", "ipc": result})


@phase2_router.post("/demo/close-all-positions")
async def post_demo_close_all_positions(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    POST /api/v1/strategy/demo/close-all-positions
    通過 IPC close_all_positions 平掉所有倉位。不影響 session 運行狀態。需要 Operator 角色。
    Rust 引擎依 pipeline_kind 分派：Demo/Live → reduce_only 市價單；Paper → 清 paper_state。

    Close all positions via IPC close_all_positions. Does not affect session state.
    Rust engine branches by pipeline_kind: Demo/Live → reduce_only market orders; Paper → paper_state.
    Requires Operator role.
    """
    from .governance_routes import _require_operator_role
    from .paper_trading_routes import _ipc_command
    _require_operator_role(actor)
    try:
        result = await _ipc_command("close_all_positions")
    except Exception as exc:
        logger.error("IPC close_all_positions failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"IPC error: {exc}")
    logger.warning(
        "close-all-positions (manual) — actor=%s", getattr(actor, "actor_id", "?"),
    )
    return _envelope({
        "message": "All positions closed — session continues / 已平掉所有倉位，session 繼續運行",
        "source": "rust_engine",
        "close_result": result,
    })


@phase2_router.get("/demo/fills")
async def get_demo_fills(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """Get Bybit Demo recent executions via PyO3 BybitClient / 通過 PyO3 獲取 Demo 成交"""
    rc = _get_rust_client()
    if rc is None:
        return _envelope({"enabled": False, "source": "rust_engine"})
    try:
        fills = [_normalize_execution(f) for f in rc.get_executions("linear", limit=50)]
        return _envelope({"source": "rust_engine", "list": fills, "count": len(fills)})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Bybit fills fetch failed: {exc}")
