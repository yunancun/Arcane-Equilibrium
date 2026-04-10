from __future__ import annotations

"""
OpenClaw Paper Trading API Routes / 纸上交易 API 路由
OpenClaw 模拟交易系统的所有 REST API 端点

TD-03 Split: Module-level singletons and DI wiring moved to paper_trading_wiring.py.
This file now contains only the router, request models, and route handlers.
All existing imports (`from .paper_trading_routes import X`) remain valid via re-exports.

MODULE_NOTE (中文):
  本模块定义纸上交易系统的所有 API 路由，使用 FastAPI APIRouter 模式。
  所有路由复用主系统的认证机制，要求 paper:read 或 paper:trade scope。
  所有响应携带 is_simulated=True 和 data_category=paper_simulated 标记。

MODULE_NOTE (English):
  This module defines all API routes for the paper trading system using FastAPI APIRouter.
  All routes reuse the main system's auth mechanism, requiring paper:read or paper:trade scopes.
  All responses carry is_simulated=True and data_category=paper_simulated markers.
"""

import json
import logging
import os
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import main_legacy as base
from .ipc_state_reader import get_rust_reader
# ARCH-RC1 1C-3-F: paper_trading_engine.py retired. DEFAULT_INITIAL_BALANCE_USDT
# inlined here (the only consumer in this module). ShadowDecisionConsumer kept
# as a type hint for the SHADOW_CONSUMER global re-exported from wiring.
# ARCH-RC1 1C-3-F：paper_trading_engine.py 退場，常量內聯。
DEFAULT_INITIAL_BALANCE_USDT = 10_000.0
from .shadow_decision_builder import ShadowDecisionConsumer
from .paper_trading_metrics import compute_full_metrics

# ═══════════════════════════════════════════════════════════════════════════════
# Singletons — re-exported from paper_trading_wiring.py (TD-03 split)
# 單例 — 從 paper_trading_wiring.py 重新導出（TD-03 拆分）
# ═══════════════════════════════════════════════════════════════════════════════
from .paper_trading_wiring import *  # noqa: F401,F403
from .paper_trading_wiring import (  # noqa: F811 — explicit re-exports for type checkers
    RISK_MANAGER,
    PORTFOLIO_RISK_CONTROL,
    PERCEPTION_PLANE,
    ENGINE,
    DEMO_CONNECTOR,
    DEMO_SYNC,
    PROTECTIVE_ORDER_MANAGER,
    GOV_HUB,
    AUDIT_PIPELINE,
    INCIDENT_POLICY,
    TTL_ENFORCER,
    H0_GATE,
    CHANGE_AUDIT_LOG,
    RECOVERY_GATE,
    SCANNER_RATE_LIMITER,
    TELEGRAM_ALERTER,
    LEARNING_TIER_GATE,
    SHADOW_CONSUMER,
)

SHADOW_CONSUMER: ShadowDecisionConsumer | None = None

# ─────────────────────────────────────────────────────────────────────────────
# Sticky "user-initiated stop" flag / 用戶主動「停止」粘性標誌
# Rust engine only knows pause/resume — there is no native "stopped" state.
# /session/stop closes positions then issues pause_paper, so a follow-up
# /session/status would otherwise report "paused" and the GUI badge would
# show "已暫停" instead of "已停止". This flag distinguishes a user-initiated
# Stop from a plain Pause so the status response stays honest.
# Cleared by /session/start (user explicitly restarts the engine).
# Rust 引擎只有 pause/resume，沒有原生 "stopped" 狀態。/session/stop 平倉後
# 發 pause_paper，導致之後 status 一直顯示 "paused"，GUI 看到「已暫停」而非
# 「已停止」。這個標誌區分用戶主動 Stop 與普通 Pause，讓 status 誠實反映。
# 由 /session/start 清除（用戶顯式重啟引擎）。
_USER_STOPPED: bool = False

# ═══════════════════════════════════════════════════════════════════════════════
# Router / 路由器
# ═══════════════════════════════════════════════════════════════════════════════

paper_router = APIRouter(prefix="/api/v1/paper", tags=["Paper Trading / 纸上交易"])


# ═══════════════════════════════════════════════════════════════════════════════
# Request / Response Models / 请求响应模型
# ═══════════════════════════════════════════════════════════════════════════════

class SessionStartRequest(BaseModel):
    initial_balance: float = Field(default=DEFAULT_INITIAL_BALANCE_USDT, gt=0, le=1_000_000)


class OrderSubmitRequest(BaseModel):
    symbol: str = Field(max_length=30, pattern=r"^[A-Z0-9]{1,30}$")
    side: str = Field(max_length=4)      # "Buy" or "Sell"
    order_type: str = Field(max_length=10)  # "market" or "limit"
    qty: float = Field(gt=0)
    price: float | None = Field(default=None, gt=0)
    leverage: float = Field(default=1.0, gt=0, le=125)


class OrderCancelRequest(BaseModel):
    order_id: str = Field(max_length=50)


class TickRequest(BaseModel):
    market_prices: dict[str, float]


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: Build paper response envelope / 构建纸上交易响应信封
# ═══════════════════════════════════════════════════════════════════════════════

def _paper_response(
    data: Any,
    action_result: str = "success",
    reason_codes: list[str] | None = None,
) -> dict[str, Any]:
    """Build a simplified response envelope for paper trading routes."""
    return {
        "api_version": "v1",
        "action_result": action_result,
        "reason_codes": reason_codes or [],
        "data_category": "paper_simulated",
        "is_simulated": True,
        "data": data,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Session Routes / Session 路由
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# Rust engine is the SOLE paper trading engine.
# Session commands are sent via IPC to the running Rust engine (command channel).
# Rust 引擎是唯一的紙上交易引擎。
# Session 命令通過 IPC 發送到運行中的 Rust 引擎（命令通道）。
# ═══════════════════════════════════════════════════════════════════════════════

_RC10_DISABLED_MSG = (
    "Python paper engine disabled — Rust engine is the sole paper trading engine. "
    "Python 紙盤引擎已禁用 — Rust 引擎是唯一的紙上交易引擎。"
)


def _get_ipc_client():
    """Get the IPC client for sending commands to Rust engine / 獲取 IPC 客戶端"""
    from .ipc_client import EngineIPCClient
    return EngineIPCClient()


async def _ipc_command(method: str, params: dict | None = None) -> dict:
    """Send a command to Rust engine via IPC and return result / 通過 IPC 向 Rust 引擎發送命令"""
    client = _get_ipc_client()
    try:
        await client.connect()
        result = await client.call(method, params=params, timeout=5.0)
        return result
    finally:
        await client.disconnect()


def _get_demo_summary() -> dict:
    """Get Demo account summary (balance + position count) via PyO3 BybitClient.
    通過 PyO3 BybitClient 獲取 Demo 帳戶摘要。
    """
    from .strategy_ai_routes import _get_rust_client
    rc = _get_rust_client()
    if rc is None:
        return {"available": False}
    try:
        wallet = rc.refresh_balance()
        positions = rc.get_positions("linear")
        open_positions = [p for p in positions if float(p.get("size") or p.get("qty") or 0) > 0]
        return {
            "available": True,
            "source": "bybit_demo_api",
            "equity": wallet.get("total_equity", 0),
            "wallet_balance": wallet.get("total_wallet_balance", 0),
            "available_balance": wallet.get("total_available_balance", 0),
            "unrealised_pnl": wallet.get("total_unrealised_pnl", 0),
            "position_count": len(open_positions),
        }
    except Exception as e:
        logger.debug("Demo summary failed: %s", e)
        return {"available": False, "error": str(e)}


def _close_all_demo_positions() -> dict:
    """Close all Demo API positions + cancel orders via PyO3 BybitClient.
    通過 PyO3 BybitClient 平掉所有 Demo API 倉位 + 取消掛單。

    Best-effort: failures are logged but don't block paper stop.
    盡力而為：失敗只記錄不阻塞 paper 停止。
    """
    from .strategy_ai_routes import _get_rust_client
    result = {"demo_closed": 0, "demo_canceled": False, "demo_errors": []}
    rc = _get_rust_client()
    if rc is None:
        result["demo_errors"].append("PyO3 BybitClient not available")
        return result

    # Step 1: Cancel all Demo orders / 取消所有 Demo 掛單
    try:
        for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]:
            try:
                rc.cancel_all_orders(sym, "linear")
            except Exception:
                pass  # Some symbols may have no orders
        result["demo_canceled"] = True
        logger.info("Demo orders canceled / Demo 掛單已取消")
    except Exception as e:
        result["demo_errors"].append(f"cancel_all: {e}")
        logger.warning("Demo cancel_all failed: %s", e)

    # Step 2: Close all Demo positions / 平掉所有 Demo 倉位
    try:
        positions = rc.get_positions("linear")
        for pos in positions:
            qty = float(pos.get("size") or pos.get("qty") or 0)
            if qty <= 0:
                continue
            side = pos.get("side", "Buy")
            close_side = "Sell" if side == "Buy" else "Buy"
            symbol = pos.get("symbol", "")
            try:
                rc.place_order(
                    symbol=symbol,
                    side=close_side,
                    order_type="Market",
                    qty=qty,
                    category="linear",
                    reduce_only=True,
                )
                result["demo_closed"] += 1
                logger.info("Demo position closed: %s %s %.4f / Demo 倉位已平：%s", symbol, close_side, qty, symbol)
            except Exception as e:
                result["demo_errors"].append(f"close {symbol}: {e}")
                logger.warning("Demo close %s failed: %s", symbol, e)
    except Exception as e:
        result["demo_errors"].append(f"get_positions: {e}")
        logger.warning("Demo get_positions failed: %s", e)

    return result


@paper_router.post("/session/start")
async def post_session_start(
    req: SessionStartRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Resume paper trading on Rust engine / 在 Rust 引擎上恢復紙盤交易"""
    rust = get_rust_reader()
    if not rust.is_available():
        raise HTTPException(status_code=503, detail="Rust engine not available / Rust 引擎不可用")
    try:
        result = await _ipc_command("resume_paper")
        # Clear sticky stop flag — user explicitly restarted / 用戶顯式重啟，清除停止標誌
        global _USER_STOPPED
        _USER_STOPPED = False
        rust_state = rust.get_paper_state() or {}
        return _paper_response({
            "message": "Paper trading started (resumed) / 紙盤交易已啟動（恢復）",
            "source": "rust_engine",
            "ipc_result": result,
            "position_count": len(rust_state.get("positions", [])),
            "balance": rust_state.get("balance", 0),
            "session": {"session_state": "active", "session_id": "rust_engine"},
        })
    except Exception as e:
        logger.error("IPC resume_paper failed: %s", e)
        raise HTTPException(status_code=502, detail=f"IPC command failed: {e}")


@paper_router.post("/session/reauth")
def post_session_reauth(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Re-grant paper trading authorization / 重新授予紙盤授權"""
    if GOV_HUB is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")
    try:
        already_authorized = GOV_HUB.is_authorized()
        if already_authorized:
            return _paper_response({
                "granted": False, "is_authorized": True,
                "message": "Authorization already active / 授權已有效",
            })
        granted = GOV_HUB.grant_paper_authorization()
        return _paper_response({
            "granted": granted,
            "is_authorized": GOV_HUB.is_authorized(),
            "message": "Paper authorization granted / 紙盤授權已授予" if granted
                       else "grant_paper_authorization() returned False",
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in session reauth: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@paper_router.post("/session/pause")
async def post_session_pause(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Pause paper trading — stops strategy dispatch + Demo shadow orders / 暫停紙盤交易"""
    try:
        result = await _ipc_command("pause_paper")
        return _paper_response({
            "message": "Paper trading paused / 紙盤交易已暫停",
            "source": "rust_engine",
            "ipc_result": result,
            "session": {"session_state": "paused", "session_id": "rust_engine"},
        })
    except Exception as e:
        logger.error("IPC pause_paper failed: %s", e)
        raise HTTPException(status_code=502, detail=f"IPC command failed: {e}")


@paper_router.post("/session/resume")
async def post_session_resume(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Resume paper trading — restores strategy dispatch + Demo shadow orders / 恢復紙盤交易"""
    try:
        result = await _ipc_command("resume_paper")
        # Resume also clears any prior sticky stop / 恢復同樣清除停止標誌
        global _USER_STOPPED
        _USER_STOPPED = False
        return _paper_response({
            "message": "Paper trading resumed / 紙盤交易已恢復",
            "source": "rust_engine",
            "ipc_result": result,
            "session": {"session_state": "active", "session_id": "rust_engine"},
        })
    except Exception as e:
        logger.error("IPC resume_paper failed: %s", e)
        raise HTTPException(status_code=502, detail=f"IPC command failed: {e}")


@paper_router.post("/session/stop")
async def post_session_stop(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Stop dual engines — close all Paper + Demo positions, pause strategies.
    停止雙引擎 — 平掉所有 Paper + Demo 倉位，暫停策略。
    """
    errors: list[str] = []
    # Mark user-initiated stop so /session/status reports "stopped" instead of "paused"
    # 標記為用戶主動停止，讓 status 顯示「stopped」而非「paused」
    global _USER_STOPPED
    _USER_STOPPED = True
    # Step 1: Close all Paper positions via IPC / 通過 IPC 平掉所有 Paper 倉位
    # If the engine is already offline, treat paper as already stopped (no error).
    # 引擎已離線時跳過 IPC（視同已停止，不算錯誤）。
    close_result = {}
    rust_online = get_rust_reader().is_available()
    if rust_online:
        try:
            close_result = await _ipc_command("close_all_positions")
        except Exception as e:
            errors.append(f"paper_close: {e}")
            logger.error("IPC close_all_positions failed: %s", e)
    else:
        close_result = {"skipped": True, "reason": "engine_offline"}
        logger.info("Rust engine offline — skipping IPC close_all_positions (already stopped)")

    # Step 2: Close all Demo positions + cancel orders via PyO3 / 通過 PyO3 平掉 Demo 倉位
    demo_result = _close_all_demo_positions()
    if demo_result.get("demo_errors"):
        errors.extend(demo_result["demo_errors"])

    # Step 3: Pause Paper strategies via IPC / 通過 IPC 暫停 Paper 策略
    pause_result = {}
    if rust_online:
        try:
            pause_result = await _ipc_command("pause_paper")
        except Exception as e:
            errors.append(f"paper_pause: {e}")
            logger.error("IPC pause_paper failed: %s", e)
    else:
        pause_result = {"skipped": True, "reason": "engine_offline"}

    return _paper_response({
        # Rust engine stays running in observation mode — scanner + price feed unaffected.
        # Rust 引擎繼續以觀察模式運行 — scanner + 行情流不受影響。
        "message": "Positions closed — Rust engine in observation mode / 倉位已平 — Rust 引擎進入觀察模式",
        "source": "rust_engine",
        "paper_close": close_result,
        "demo_close": demo_result,
        "paper_pause": pause_result,
        "errors": errors if errors else None,
        "session": {"session_state": "observing", "session_id": "rust_engine"},
    })


@paper_router.get("/session/status")
def get_session_status(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get current session status from Rust engine / 從 Rust 引擎獲取 session 狀態"""
    rust = get_rust_reader()
    rust_state = rust.get_paper_state() if rust.is_available() else None
    if rust_state is None:
        return _paper_response({
            "source": "rust_engine",
            "engine_available": False,
            "session": {
                "session_state": "offline",
                "session_id": "rust_engine",
                "session_halted": False,
                "session_halt_reason": "Rust engine not available / Rust 引擎不可用",
            },
            "pnl": {},
            "order_count": 0, "fill_count": 0, "position_count": 0,
        })
    # Read paper_paused from full snapshot / 從完整快照讀取暫停狀態
    full_snapshot = rust.get_snapshot() if rust.is_available() else None
    is_paused = full_snapshot.get("paper_paused", False) if full_snapshot else False
    trading_mode = full_snapshot.get("trading_mode", "paper_only") if full_snapshot else "paper_only"
    # Wrap flat Rust snapshot into nested structure expected by GUI
    # 將 Rust 扁平快照包裝為 GUI 預期的嵌套結構
    positions = rust_state.get("positions", [])
    total_unrealized = sum(p.get("unrealized_pnl", 0) for p in positions)
    balance = rust_state.get("balance", 0)
    peak = rust_state.get("peak_balance", 0)
    realized = rust_state.get("total_realized_pnl", 0)
    fees = rust_state.get("total_fees", 0)
    # Translate Rust paused state: user-initiated Stop → "observing" (engine still running,
    # scanner still running, no new trades). Plain pause → "paused".
    # Rust paused 狀態翻譯：用戶主動 Stop → "observing"（引擎繼續運行、scanner 繼續、
    # 不開新倉）；普通 pause → "paused"。
    if is_paused:
        session_state = "observing" if _USER_STOPPED else "paused"
    else:
        session_state = "active"
    return _paper_response({
        "source": "rust_engine",
        # engine_available = True means Rust process is alive and writing snapshots.
        # Distinct from session_state (which tracks paper trading phase).
        # engine_available = True 表示 Rust 進程存活並持續寫快照；
        # 與 session_state（paper 交易階段）分開。
        "engine_available": True,
        "session": {
            "session_state": session_state,
            "session_id": "rust_engine",
            "initial_paper_balance_usdt": peak,
            "current_paper_balance_usdt": balance,
            "peak_balance_usdt": peak,
            "session_halted": False,
            "session_halt_reason": None,
            "trading_mode": trading_mode,
        },
        "pnl": {
            "realized_pnl": realized,
            "unrealized_pnl": total_unrealized,
            "total_fees_paid": fees,
            "total_ai_cost": 0,
            "net_paper_pnl": realized + total_unrealized - fees,
            "net_realized_pnl": realized - fees,
            "closed_position_pnl": realized,
        },
        "order_count": 0,
        "fill_count": rust_state.get("trade_count", 0),
        "position_count": len(positions),
        "state_revision": 0,
        # P3: Demo balance from Rust WS sync (no API call — avoids blocking)
        # Demo 餘額從 Rust WS 同步讀取（不打 API — 避免阻塞）
        "demo": {
            "available": True,
            "source": "rust_ws_sync",
            "sync_balance": rust_state.get("bybit_sync_balance"),
        },
    })


# ═══════════════════════════════════════════════════════════════════════════════
# Order Routes / 订单路由
# ═══════════════════════════════════════════════════════════════════════════════

@paper_router.post("/order/submit")
def post_order_submit(
    req: OrderSubmitRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """DISABLED: Rust engine manages order execution / 已禁用：Rust 引擎管理訂單執行"""
    raise HTTPException(status_code=410, detail=_RC10_DISABLED_MSG)


@paper_router.post("/order/cancel")
def post_order_cancel(
    req: OrderCancelRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """DISABLED: Rust engine manages order lifecycle / 已禁用：Rust 引擎管理訂單生命週期"""
    raise HTTPException(status_code=410, detail=_RC10_DISABLED_MSG)


@paper_router.get("/orders")
def get_orders(
    state_filter: str | None = None,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get orders from Rust engine / 從 Rust 引擎獲取訂單"""
    # Rust engine manages orders internally; recent intents serve as order log
    # Rust 引擎內部管理訂單；最近意圖列表作為訂單記錄
    reader = get_rust_reader()
    if reader.is_available():
        intents = reader.get_recent_intents() or []
        return _paper_response({"orders": intents, "count": len(intents), "source": "rust_engine"})
    return _paper_response({"orders": [], "count": 0, "source": "rust_engine"})


# ═══════════════════════════════════════════════════════════════════════════════
# Position / Fill / PnL Routes / 持仓 / 成交 / PnL 路由
# ═══════════════════════════════════════════════════════════════════════════════

@paper_router.get("/positions")
def get_positions(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get current paper positions from Rust engine / 從 Rust 引擎獲取紙上持倉"""
    rust = get_rust_reader()
    rust_state = rust.get_paper_state() if rust.is_available() else None
    if rust_state is None:
        return _paper_response({"positions": [], "count": 0, "source": "rust_engine"})
    # Transform Rust position fields to GUI-expected format
    # 轉換 Rust 持倉欄位為 GUI 預期格式
    raw_positions = rust_state.get("positions", [])
    transformed = []
    for p in raw_positions:
        transformed.append({
            **p,
            "side": "Buy" if p.get("is_long", True) else "Sell",
            "avg_entry_price": p.get("entry_price", p.get("avg_entry_price", 0)),
        })
    return _paper_response({"positions": transformed, "count": len(transformed), "source": "rust_engine"})


@paper_router.post("/positions/{symbol}/close")
async def post_close_position(
    symbol: str,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Close a single paper position by symbol via IPC close_position command.
    通過 IPC close_position 指令平掉指定 symbol 的紙上持倉。
    """
    rust = get_rust_reader()
    if not rust.is_available():
        raise HTTPException(status_code=503, detail="Rust engine not available / Rust 引擎不可用")
    try:
        result = await _ipc_command("close_position", {"symbol": symbol.upper()})
        return _paper_response({"symbol": symbol.upper(), "closed": True, "source": "rust_engine", "ipc": result})
    except Exception as e:
        logger.error("IPC close_position failed for %s: %s", symbol, e)
        raise HTTPException(status_code=502, detail=f"IPC error: {e}")


@paper_router.get("/fills")
def get_fills(
    limit: int = 50,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get fill history from Rust engine / 從 Rust 引擎獲取成���歷史"""
    reader = get_rust_reader()
    if reader.is_available():
        rust_fills = reader.get_recent_fills() or []
        # Inject `side` field: Rust TimestampedFill has is_long bool, GUI expects side='Buy'/'Sell'
        # 注入 side 欄位：Rust 用 is_long，GUI 期望 side='Buy'/'Sell'
        for f in rust_fills:
            if isinstance(f, dict) and "side" not in f:
                f["side"] = "Buy" if f.get("is_long") else "Sell"
        capped = rust_fills[:min(limit, 200)]
        return _paper_response({"fills": capped, "count": len(capped), "source": "rust_engine"})
    return _paper_response({"fills": [], "count": 0, "source": "rust_engine"})


@paper_router.get("/pnl")
def get_pnl(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get paper PnL summary from Rust engine / 從 Rust 引擎獲取紙上 PnL"""
    rust = get_rust_reader()
    rust_state = rust.get_paper_state() if rust.is_available() else None
    if rust_state is None:
        return _paper_response({"source": "rust_engine", "available": False})
    positions = rust_state.get("positions", [])
    total_unrealized = sum(p.get("unrealized_pnl", 0) for p in positions)
    realized = rust_state.get("total_realized_pnl", 0)
    fees = rust_state.get("total_fees", 0)
    return _paper_response({
        "source": "rust_engine",
        "realized_pnl": realized,
        "unrealized_pnl": total_unrealized,
        "total_fees_paid": fees,
        "total_ai_cost": 0,
        "net_paper_pnl": realized + total_unrealized - fees,
        "net_realized_pnl": realized - fees,
        "closed_position_pnl": realized,
        "trade_count": rust_state.get("trade_count", 0),
    })


@paper_router.get("/audit-trail")
def get_audit_trail(
    limit: int = 100,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get audit trail from Rust engine / 從 Rust 引擎獲取審計記錄"""
    # Rust recent intents + fills serve as audit trail / Rust 意圖+成交作為審計記錄
    reader = get_rust_reader()
    trail: list = []
    if reader.is_available():
        intents = reader.get_recent_intents() or []
        fills = reader.get_recent_fills() or []
        trail = intents + fills
    return _paper_response({"audit_trail": trail[:min(limit, 500)], "count": len(trail), "source": "rust_engine"})


# ═══════════════════════════════════════════════════════════════════════════════
# Tick Route / 成交模拟 Tick 路由
# ═══════════════════════════════════════════════════════════════════════════════

@paper_router.post("/tick")
def post_tick(
    req: TickRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """DISABLED: Rust engine processes ticks internally / 已禁用：Rust 引擎內部處理 tick"""
    raise HTTPException(status_code=410, detail=_RC10_DISABLED_MSG)


# ═══════════════════════════════════════════════════════════════════════════════
# Export Route / 导出路由
# ═══════════════════════════════════════════════════════════════════════════════

@paper_router.get("/export")
def get_export(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Export session data from Rust engine snapshot / 從 Rust 引擎快照導出 session 數據"""
    reader = get_rust_reader()
    snapshot = reader.get_snapshot() if reader.is_available() else None
    if snapshot is None:
        return _paper_response({"available": False, "source": "rust_engine"})
    return _paper_response({"source": "rust_engine", **snapshot})


# ═══════════════════════════════════════════════════════════════════════════════
# Market Feed Routes / 实时行情流路由
# ═══════════════════════════════════════════════════════════════════════════════

class MarketFeedStartRequest(BaseModel):
    symbols: list[str] = Field(default=["BTCUSDT", "ETHUSDT"], max_length=20)


class MarketFeedSymbolRequest(BaseModel):
    symbol: str = Field(max_length=30, pattern=r"^[A-Z0-9]{1,30}$")


@paper_router.post("/market-feed/start")
def post_market_feed_start(
    req: MarketFeedStartRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """DISABLED: Rust engine has its own WebSocket feed / 已禁用：Rust 引擎有自己的 WebSocket 行情流"""
    # Rust engine is the sole WS connection — no Python WS needed
    # Rust 引擎是唯一的 WS 連接 — 不需要 Python WS
    return _paper_response({
        "message": "Market feed managed by Rust engine / 行情流由 Rust 引擎管理",
        "source": "rust_engine",
    }, action_result="no_change")


@paper_router.post("/market-feed/stop")
def post_market_feed_stop(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """DISABLED: Rust engine manages its own WebSocket / 已禁用：Rust 引擎管理自己的 WebSocket"""
    return _paper_response({
        "message": "Market feed managed by Rust engine / 行情流由 Rust 引擎管理",
        "source": "rust_engine",
    }, action_result="no_change")


@paper_router.get("/market-feed/status")
def get_market_feed_status(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get market data feed status from Rust engine / 從 Rust 引擎獲取行情數據流狀態"""
    # Python DISPATCHER removed — read from Rust engine snapshot instead.
    # Python DISPATCHER 已移除 — 改從 Rust 引擎快照讀取。
    reader = get_rust_reader()
    snap = reader.get_snapshot() if reader.is_available() else None
    if snap is not None:
        stats = snap.get("stats", {})
        last_tick_ms = stats.get("last_tick_ms", 0)
        import time
        age_sec = (time.time() * 1000 - last_tick_ms) / 1000 if last_tick_ms > 0 else 999
        is_stale = age_sec > 30
        return _paper_response({
            "running": not is_stale,
            "source": "rust_engine",
            "total_ticks": stats.get("total_ticks", 0),
            "total_fills": stats.get("total_fills", 0),
            "last_tick_ms": last_tick_ms,
            "last_tick_age_sec": round(age_sec, 1),
            "attention_level": "high" if not is_stale else "dormant",
            "symbols": list(snap.get("latest_prices", {}).keys()),
            "message": "Rust engine WS feed active" if not is_stale else "Rust engine feed stale",
        })
    return _paper_response({
        "running": False,
        "attention_level": "dormant",
        "message": "Engine not available / 引擎不可用",
    })


@paper_router.post("/market-feed/add-symbol")
def post_market_feed_add_symbol(
    req: MarketFeedSymbolRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """DISABLED: Rust engine manages symbols at startup / 已禁用：Rust 引擎在啟動時管理 symbols"""
    raise HTTPException(status_code=410, detail=_RC10_DISABLED_MSG)


@paper_router.post("/market-feed/remove-symbol")
def post_market_feed_remove_symbol(
    req: MarketFeedSymbolRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """DISABLED: Rust engine manages symbols at startup / 已禁用：Rust 引擎在啟動時管理 symbols"""
    raise HTTPException(status_code=410, detail=_RC10_DISABLED_MSG)


# ═══════════════════════════════════════════════════════════════════════════════
# Shadow Decision Routes / 影子决策路由
# ═══════════════════════════════════════════════════════════════════════════════

class ShadowFeedRequest(BaseModel):
    market_prices: dict[str, float]
    symbol: str = Field(default="BTCUSDT", max_length=30, pattern=r"^[A-Z0-9]{1,30}$")


@paper_router.post("/shadow/feed")
def post_shadow_feed(
    req: ShadowFeedRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """DISABLED: Shadow decisions handled by Rust engine / 已禁用：影子決策由 Rust 引擎處理"""
    raise HTTPException(status_code=410, detail=_RC10_DISABLED_MSG)


@paper_router.get("/shadow/history")
def get_shadow_history(
    limit: int = 50,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get shadow decision consumption history / 获取影子决策消费历史"""
    if SHADOW_CONSUMER is None:
        return _paper_response({"history": [], "count": 0})
    history = SHADOW_CONSUMER.get_history(limit=min(limit, 200))
    return _paper_response({"history": history, "count": len(history)})


@paper_router.get("/shadow/decisions")
def get_shadow_decisions(
    limit: int = 50,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get shadow decisions from Rust engine / 從 Rust 引擎獲取影子決策"""
    # Shadow decisions are tracked via recent_intents in Rust snapshot
    # 影子決策通過 Rust 快照��的 recent_intents 追蹤
    reader = get_rust_reader()
    if reader.is_available():
        intents = reader.get_recent_intents() or []
        capped = intents[-min(limit, 200):]
        return _paper_response({"shadow_decisions": capped, "count": len(capped), "source": "rust_engine"})
    return _paper_response({"shadow_decisions": [], "count": 0, "source": "rust_engine"})


# ═══════════════════════════════════════════════════════════════════════════════
# Metrics Route / 性能指标路由
# ═══════════════════════════════════════════════════════════════════════════════

@paper_router.get("/metrics")
def get_metrics(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get performance metrics from Rust engine / 從 Rust 引擎獲取性能指標

    Returns full nested metrics (trade_metrics, drawdown_metrics, holding_period_metrics,
    sharpe_ratio) via compute_full_metrics, plus basic tick stats from the engine.
    返回完整嵌套指標（交易、回撤、持倉時間、夏普比率）+ 引擎 tick 統計。
    """
    rust = get_rust_reader()
    rust_state = rust.get_paper_state() if rust.is_available() else None
    if rust_state is None:
        return _paper_response({"available": False, "source": "rust_engine"})
    # Full metrics via compute_full_metrics (trade_metrics, drawdown, sharpe, etc.)
    # 完整指標通過 compute_full_metrics 計算
    full = compute_full_metrics(rust_state)
    # Merge tick stats from engine / 合併引擎 tick 統計
    stats = rust.get_tick_stats() or {}
    full["source"] = "rust_engine"
    full["total_ticks"] = stats.get("total_ticks", 0)
    full["total_intents"] = stats.get("total_intents", 0)
    # Ensure total_fills is available at top level for backward compatibility
    # 確保 total_fills 在頂層可用（向後兼容）
    full["total_fills"] = stats.get("total_fills", 0)
    full["total_stops"] = stats.get("total_stops", 0)
    return _paper_response(full)


# ═══════════════════════════════════════════════════════════════════════════════
# AI Cost Tracking Route (via OpenClaw gateway) / AI 成本追踪路由
# ═══════════════════════════════════════════════════════════════════════════════

def _fetch_openclaw_usage_cost() -> dict[str, Any] | None:
    """
    Fetch AI usage cost from OpenClaw gateway CLI.
    从 OpenClaw 网关 CLI 获取 AI 使用成本。

    Returns parsed cost data or None if OpenClaw is not available.
    """
    try:
        result = subprocess.run(
            ["openclaw", "gateway", "usage-cost", "--json", "--days", "30"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        return None


@paper_router.get("/ai-cost")
def get_ai_cost(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get AI usage cost from OpenClaw gateway.
    从 OpenClaw 网关获取 AI 使用成本。

    Integrates OpenClaw's built-in token/cost tracking with our Net PnL system.
    """
    raw = _fetch_openclaw_usage_cost()
    if raw is None:
        return _paper_response({
            "available": False,
            "message": "OpenClaw gateway not reachable / OpenClaw 网关不可达",
            "today_cost": 0.0,
            "today_tokens": 0,
            "total_cost_30d": 0.0,
            "total_tokens_30d": 0,
            "daily": [],
        })

    # Extract today's cost
    daily = raw.get("daily", [])
    totals = raw.get("totals", {})

    today_entry = daily[-1] if daily else {}
    today_cost = today_entry.get("totalCost", 0.0)
    today_tokens = today_entry.get("totalTokens", 0)

    return _paper_response({
        "available": True,
        "source": "openclaw_gateway_usage_cost",
        "today_cost": round(today_cost, 6),
        "today_tokens": today_tokens,
        "total_cost_30d": round(totals.get("totalCost", 0.0), 6),
        "total_tokens_30d": totals.get("totalTokens", 0),
        "cost_breakdown": {
            "input_cost": round(totals.get("inputCost", 0.0), 6),
            "output_cost": round(totals.get("outputCost", 0.0), 6),
            "cache_read_cost": round(totals.get("cacheReadCost", 0.0), 6),
            "cache_write_cost": round(totals.get("cacheWriteCost", 0.0), 6),
        },
        "daily": daily[-7:],  # Last 7 days
    })
