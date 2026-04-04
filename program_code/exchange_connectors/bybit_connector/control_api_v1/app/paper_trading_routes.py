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
from .paper_trading_engine import (
    DEFAULT_INITIAL_BALANCE_USDT,
    PaperStateStore,
    PaperTradingEngine,
)
from .market_data_dispatcher import MarketDataDispatcher
from .shadow_decision_builder import (
    ShadowDecisionConsumer,
    ShadowDecisionFileFeeder,
    build_shadow_decision,
)
from .paper_trading_metrics import compute_full_metrics

# ═══════════════════════════════════════════════════════════════════════════════
# Singletons — re-exported from paper_trading_wiring.py (TD-03 split)
# 單例 — 從 paper_trading_wiring.py 重新導出（TD-03 拆分）
# ═══════════════════════════════════════════════════════════════════════════════
from .paper_trading_wiring import *  # noqa: F401,F403
from .paper_trading_wiring import (  # noqa: F811 — explicit re-exports for type checkers
    PAPER_STORE,
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
    DISPATCHER,
    SHADOW_CONSUMER,
)

# Mutable globals — must be defined in THIS module (not in wiring) because
# route handlers use `global DISPATCHER` to rebind them at runtime.
# 可變全局變量 — 必須在本模組定義（而非 wiring），因為路由處理器使用 global 重綁定。
DISPATCHER: MarketDataDispatcher | None = None
SHADOW_CONSUMER: ShadowDecisionConsumer | None = None

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

@paper_router.post("/session/start")
def post_session_start(
    req: SessionStartRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Start a new paper trading session / 开始新的纸上交易 session

    When no explicit initial_balance is provided (i.e. the default is used),
    attempts to read the Bybit Demo account USDT balance first.
    若未指定初始餘額（使用預設值），先嘗試讀取 Bybit Demo 帳戶 USDT 餘額。
    """
    try:
        balance = req.initial_balance

        # If the caller did not override the default, try fetching Bybit Demo balance.
        # 若呼叫方未覆蓋預設值，嘗試從 Bybit Demo 帳戶獲取真實餘額。
        if balance == DEFAULT_INITIAL_BALANCE_USDT and DEMO_CONNECTOR is not None and DEMO_CONNECTOR.is_enabled:
            try:
                wallet_result = DEMO_CONNECTOR.get_wallet_balance()
                if wallet_result.get("retCode") == 0:
                    coins = wallet_result.get("result", {}).get("list", [{}])[0].get("coin", [])
                    for c in coins:
                        if c.get("coin") == "USDT":
                            demo_bal = float(c.get("walletBalance", 0))
                            if demo_bal > 0:
                                balance = demo_bal
                                logger.info(
                                    "Using Bybit Demo USDT balance as initial: %.2f / "
                                    "使用 Bybit Demo USDT 餘額作為初始資金: %.2f",
                                    demo_bal, demo_bal,
                                )
                            break
            except Exception as demo_err:
                logger.warning(
                    "Failed to fetch Bybit Demo balance, using default %.2f: %s / "
                    "獲取 Demo 餘額失敗，使用預設值: %s",
                    DEFAULT_INITIAL_BALANCE_USDT, demo_err, demo_err,
                )

        state = ENGINE.start_session(initial_balance=balance)

        # Auto-grant paper authorization on session start (zero real risk).
        # 会话启动时自动授予纸盘授权（无真实资金风险）。
        # This unblocks is_authorized() so orders can flow through the governance gate.
        # 这将解除 is_authorized() 的阻塞，让订单能通过治理门检。
        try:
            if GOV_HUB is not None:
                granted = GOV_HUB.grant_paper_authorization()
                if granted:
                    logger.info("Paper trading authorization auto-granted on session start")
                else:
                    logger.warning(
                        "grant_paper_authorization() returned False on session start "
                        "— governance gate will remain closed / 纸盘授权返回 False — 治理门检仍关闭"
                    )
        except Exception as _auth_err:
            # Non-fatal: session itself is started; warn and continue.
            # 非致命错误：会话本身已启动；记录警告并继续。
            logger.warning("Failed to auto-grant paper authorization: %s", _auth_err)

        return _paper_response({"session": state["session"], "message": "Paper trading session started"})
    except ValueError as e:
        # 不暴露內部異常細節到 HTTP 響應 / Do not leak internal exception details to HTTP response
        logger.warning("Session start conflict: %s", e)
        raise HTTPException(status_code=409, detail="Session state conflict")


@paper_router.post("/session/reauth")
def post_session_reauth(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Re-grant paper trading authorization without resetting the session.
    重新授予纸盘交易授权，无需重置当前 session。

    Use case: server was restarted with an existing active session; the authorization
    was not re-granted on startup (because grant_paper_authorization() is normally
    called on session start, not on state-file load).
    使用场景：服务器重启后加载了已有 active session；由于 grant_paper_authorization()
    只在 session start 时调用，重启后授权丢失。此端点补授权，不影响现有 session 状态。

    Returns: {granted: bool, is_authorized: bool, auth_state: str}
    """
    try:
        if GOV_HUB is None:
            raise HTTPException(status_code=503, detail="Governance hub not available")

        already_authorized = GOV_HUB.is_authorized()
        if already_authorized:
            return _paper_response({
                "granted": False,
                "is_authorized": True,
                "message": "Authorization already active — no-op / 授权已有效，跳过",
            })

        granted = GOV_HUB.grant_paper_authorization()
        is_authorized_after = GOV_HUB.is_authorized()
        logger.info(
            "Paper session reauth: granted=%s, is_authorized_after=%s / "
            "纸盘 session 补授权：granted=%s，授权后状态=%s",
            granted, is_authorized_after, granted, is_authorized_after,
        )
        return _paper_response({
            "granted": granted,
            "is_authorized": is_authorized_after,
            "message": "Paper authorization re-granted / 纸盘授权已补授" if granted
                       else "grant_paper_authorization() returned False / 补授权返回 False",
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in session reauth: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@paper_router.post("/session/pause")
def post_session_pause(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Pause the current session / 暂停当前 session"""
    try:
        state = ENGINE.pause_session()
        return _paper_response({"session": state["session"]})
    except ValueError as e:
        # 不暴露內部異常細節到 HTTP 響應 / Do not leak internal exception details to HTTP response
        logger.warning("Session pause conflict: %s", e)
        raise HTTPException(status_code=409, detail="Session state conflict")


@paper_router.post("/session/resume")
def post_session_resume(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Resume a paused session / 恢复已暂停的 session"""
    try:
        state = ENGINE.resume_session()
        return _paper_response({"session": state["session"]})
    except ValueError as e:
        # 不暴露內部異常細節到 HTTP 響應 / Do not leak internal exception details to HTTP response
        logger.warning("Session resume conflict: %s", e)
        raise HTTPException(status_code=409, detail="Session state conflict")


@paper_router.post("/session/stop")
def post_session_stop(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Stop the session and finalize PnL / 停止 session 并结算 PnL

    Before stopping, closes all open positions at market price and cancels
    all pending orders. This ensures no phantom positions remain.
    停止前先以市價平掉所有持倉並取消所有掛單，避免幽靈倉殘留。
    """
    try:
        # ── Phase 1: Close all open positions at market price ──
        # 第一階段：以市價平掉所有持倉
        positions = ENGINE.get_positions()
        if positions:
            # Fetch latest prices: Rust engine → Dispatcher → fallback empty
            # 獲取最新價格：Rust 引擎 → 行情分發器 → 降級為空
            live_prices: dict[str, float] = {}
            try:
                live_prices = get_rust_reader().get_latest_prices() or {}
            except Exception:
                pass
            if not live_prices and DISPATCHER and DISPATCHER.is_running():
                live_prices = DISPATCHER.get_status().get("latest_prices", {})

            closed_count = 0
            for symbol, pos in positions.items():
                pos_side = pos.get("side", "Buy")
                close_side = "Sell" if pos_side == "Buy" else "Buy"
                qty = pos.get("qty", 0)
                if qty <= 0:
                    continue
                try:
                    ENGINE.submit_order(
                        symbol=symbol,
                        side=close_side,
                        order_type="market",
                        qty=qty,
                        market_prices=live_prices,
                        reduce_only=True,
                    )
                    closed_count += 1
                except Exception as close_err:
                    logger.warning(
                        "Session stop — failed to close position %s: %s (non-fatal) / "
                        "停止引擎平倉失敗（非致命）",
                        symbol, close_err,
                    )
            if closed_count > 0:
                logger.info(
                    "Session stop — closed %d/%d positions at market / "
                    "停止引擎 — 已市價平掉 %d/%d 個持倉",
                    closed_count, len(positions), closed_count, len(positions),
                )

        # ── Phase 2: Cancel all pending orders ──
        # 第二階段：取消所有掛單
        try:
            working_orders = ENGINE.get_orders(state_filter="working")
            canceled_count = 0
            for order in working_orders:
                oid = order.get("order_id", "")
                if oid:
                    ENGINE.cancel_order(oid)
                    canceled_count += 1
            if canceled_count > 0:
                logger.info(
                    "Session stop — canceled %d pending orders / "
                    "停止引擎 — 已取消 %d 個掛單",
                    canceled_count, canceled_count,
                )
        except Exception as cancel_err:
            logger.warning(
                "Session stop — cancel orders error: %s (non-fatal) / "
                "停止引擎取消掛單失敗（非致命）",
                cancel_err,
            )

        # ── Phase 3: Stop session (also handles Demo close + reconciliation) ──
        # 第三階段：停止 session（同時處理 Demo 平倉 + 對賬）
        state = ENGINE.stop_session()
        return _paper_response({
            "session": state["session"],
            "pnl": state["pnl"],
            "message": "Paper trading session stopped and PnL finalized",
        })
    except ValueError as e:
        # 不暴露內部異常細節到 HTTP 響應 / Do not leak internal exception details to HTTP response
        logger.warning("Session stop conflict: %s", e)
        raise HTTPException(status_code=409, detail="Session state conflict")


@paper_router.get("/session/status")
def get_session_status(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get current session status / 获取 session 状态"""
    # R06-B: try Rust engine snapshot first, fall back to Python ENGINE
    # 優先讀取 Rust 引擎快照，降級到 Python ENGINE
    rust = get_rust_reader()
    rust_state = rust.get_paper_state() if rust.is_available() else None
    if rust_state is not None:
        # 將 Rust 扁平快照包裝為 GUI 預期的嵌套結構
        # Wrap flat Rust snapshot into nested structure expected by GUI
        positions = rust_state.get("positions", [])
        total_unrealized = sum(p.get("unrealized_pnl", 0) for p in positions)
        balance = rust_state.get("balance", 0)
        peak = rust_state.get("peak_balance", 0)
        realized = rust_state.get("total_realized_pnl", 0)
        fees = rust_state.get("total_fees", 0)
        return _paper_response({
            "source": "rust_engine",
            "session": {
                "session_state": "active",
                "session_id": "rust_engine",
                "initial_paper_balance_usdt": peak,  # 用峰值近似初始餘額 / Use peak as proxy for initial
                "current_paper_balance_usdt": balance,
                "peak_balance_usdt": peak,
                "session_halted": False,
                "session_halt_reason": None,
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
        })
    return _paper_response(ENGINE.get_session_status())


# ═══════════════════════════════════════════════════════════════════════════════
# Order Routes / 订单路由
# ═══════════════════════════════════════════════════════════════════════════════

@paper_router.post("/order/submit")
def post_order_submit(
    req: OrderSubmitRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Submit a paper order / 提交纸上订单"""
    try:
        # Use live market prices: Rust engine → Dispatcher → order price (R06-B)
        # 優先使用實時價格：Rust 引擎 → 行情分發器 → 訂單價格
        live_prices = get_rust_reader().get_latest_prices()
        if not live_prices and DISPATCHER and DISPATCHER.is_running():
            live_prices = DISPATCHER.get_status().get("latest_prices", {})
        if not live_prices:
            live_prices = {req.symbol: req.price} if req.price else None

        result = ENGINE.submit_order(
            symbol=req.symbol,
            side=req.side,
            order_type=req.order_type,
            qty=req.qty,
            price=req.price,
            leverage=req.leverage,
            market_prices=live_prices,
        )
        if result["rejected_reason"]:
            return _paper_response(
                result,
                action_result="blocked",
                reason_codes=[result["rejected_reason"]],
            )
        return _paper_response(result)
    except ValueError as e:
        # 不暴露內部異常細節到 HTTP 響應 / Do not leak internal exception details to HTTP response
        logger.warning("Order submission validation error: %s", e)
        raise HTTPException(status_code=400, detail="Invalid order parameters")


@paper_router.post("/order/cancel")
def post_order_cancel(
    req: OrderCancelRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Cancel a working paper order / 取消纸上订单"""
    result = ENGINE.cancel_order(req.order_id)
    if not result["success"]:
        raise HTTPException(status_code=409, detail=result["reason"])
    return _paper_response({"order_id": req.order_id, "canceled": True})


@paper_router.get("/orders")
def get_orders(
    state_filter: str | None = None,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """List paper orders / 获取纸上订单列表"""
    orders = ENGINE.get_orders(state_filter=state_filter)
    return _paper_response({"orders": orders, "count": len(orders)})


# ═══════════════════════════════════════════════════════════════════════════════
# Position / Fill / PnL Routes / 持仓 / 成交 / PnL 路由
# ═══════════════════════════════════════════════════════════════════════════════

@paper_router.get("/positions")
def get_positions(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get current paper positions / 获取纸上持仓"""
    # R06-B: try Rust engine snapshot first / 優先讀取 Rust 引擎快照
    rust = get_rust_reader()
    rust_state = rust.get_paper_state() if rust.is_available() else None
    if rust_state is not None:
        # 轉換 Rust 持倉欄位為 GUI 預期格式（is_long→side, entry_price→avg_entry_price）
        # Transform Rust position fields to GUI-expected format
        raw_positions = rust_state.get("positions", [])
        transformed = []
        for p in raw_positions:
            transformed.append({
                **p,
                "side": "Buy" if p.get("is_long", True) else "Sell",
                "avg_entry_price": p.get("entry_price", p.get("avg_entry_price", 0)),
            })
        return _paper_response({"positions": transformed, "count": len(transformed), "source": "rust_engine"})
    positions = ENGINE.get_positions()
    return _paper_response({"positions": positions, "count": len(positions)})


@paper_router.get("/fills")
def get_fills(
    limit: int = 50,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get fill history / 获取成交历史"""
    # IPC-03: Rust-first for recent fills / 優先讀 Rust 最近成交記錄
    reader = get_rust_reader()
    if reader.is_available():
        rust_fills = reader.get_recent_fills()
        if rust_fills:
            capped = rust_fills[:min(limit, 200)]
            return _paper_response({"fills": capped, "count": len(capped), "source": "rust_engine"})
    # Fallback to Python PaperTradingEngine / 降級到 Python 紙盤引擎
    fills = ENGINE.get_fills(limit=min(limit, 200))
    return _paper_response({"fills": fills, "count": len(fills)})


@paper_router.get("/pnl")
def get_pnl(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get paper PnL summary / 获取纸上 PnL 汇总"""
    # R06-B: try Rust engine snapshot first / 優先讀取 Rust 引擎快照
    rust = get_rust_reader()
    rust_state = rust.get_paper_state() if rust.is_available() else None
    if rust_state is not None:
        # 將 Rust PnL 包裝為 GUI 預期的嵌套結構（與 /session/status 的 pnl 子對象一致）
        # Wrap Rust PnL into nested structure matching GUI expectations
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
    return _paper_response(ENGINE.get_pnl())


@paper_router.get("/audit-trail")
def get_audit_trail(
    limit: int = 100,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get audit trail / 获取审计记录"""
    trail = ENGINE.get_audit_trail(limit=min(limit, 500))
    return _paper_response({"audit_trail": trail, "count": len(trail)})


# ═══════════════════════════════════════════════════════════════════════════════
# Tick Route / 成交模拟 Tick 路由
# ═══════════════════════════════════════════════════════════════════════════════

@paper_router.post("/tick")
def post_tick(
    req: TickRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Manually trigger a fill simulation tick / 手动触发成交模拟 tick

    Provide current market prices to check if any limit orders should fill.
    """
    result = ENGINE.tick(market_prices=req.market_prices)
    return _paper_response(result)


# ═══════════════════════════════════════════════════════════════════════════════
# Export Route / 导出路由
# ═══════════════════════════════════════════════════════════════════════════════

@paper_router.get("/export")
def get_export(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Export complete session data for analysis / 导出完整 session 数据"""
    return _paper_response(ENGINE.export_session())


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
    """
    Start real-time market data feed (Bybit public WebSocket).
    启动实时行情数据流（Bybit 公共 WebSocket）。

    Connects to wss://stream.bybit.com/v5/public/linear and subscribes to ticker data.
    The attention filter automatically triggers paper engine ticks based on trading context.
    """
    global DISPATCHER
    if DISPATCHER and DISPATCHER.is_running():
        return _paper_response(
            {"message": "Market feed already running / 行情流已在运行", "status": DISPATCHER.get_status()},
            action_result="no_change",
        )

    DISPATCHER = MarketDataDispatcher(
        engine=ENGINE,
        symbols=req.symbols,
    )
    DISPATCHER.start()

    # RC-10: Python tick processing disabled — Rust engine handles all tick processing.
    # PIPELINE_BRIDGE is NOT registered as tick consumer and NOT activated.
    # RC-10：Python tick 處理已禁用 — Rust 引擎處理所有 tick。
    # PIPELINE_BRIDGE 不再註冊為 tick 消費者，也不啟動。
    logger.info("Market feed started, Python tick processing DISABLED (RC-10) / "
                "行情流已启动，Python tick 处理已禁用（RC-10）")

    return _paper_response({
        "message": "Market feed started / 行情流已启动",
        "symbols": req.symbols,
        "status": DISPATCHER.get_status(),
    })


@paper_router.post("/market-feed/stop")
def post_market_feed_stop(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Stop the real-time market data feed / 停止实时行情数据流"""
    global DISPATCHER
    if not DISPATCHER or not DISPATCHER.is_running():
        return _paper_response(
            {"message": "Market feed not running / 行情流未运行"},
            action_result="no_change",
        )

    # Deactivate pipeline bridge / 停用管线桥接器
    try:
        from .phase2_strategy_routes import PIPELINE_BRIDGE
        if PIPELINE_BRIDGE is not None:
            PIPELINE_BRIDGE.deactivate()
    except ImportError:
        pass

    DISPATCHER.stop()
    return _paper_response({"message": "Market feed stopped / 行情流已停止"})


@paper_router.get("/market-feed/status")
def get_market_feed_status(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get market data feed status / 获取行情数据流状态"""
    if not DISPATCHER:
        return _paper_response({
            "running": False,
            "attention_level": "dormant",
            "message": "Market feed not initialized / 行情流未初始化",
        })
    return _paper_response(DISPATCHER.get_status())


@paper_router.post("/market-feed/add-symbol")
def post_market_feed_add_symbol(
    req: MarketFeedSymbolRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Dynamically add a symbol to the market feed / 动态添加交易对到行情流"""
    if not DISPATCHER or not DISPATCHER.is_running():
        raise HTTPException(status_code=409, detail="Market feed not running / 行情流未运行")

    DISPATCHER.add_symbol(req.symbol)
    return _paper_response({
        "message": f"Symbol {req.symbol} added / 已添加交易对 {req.symbol}",
        "symbol": req.symbol,
    })


@paper_router.post("/market-feed/remove-symbol")
def post_market_feed_remove_symbol(
    req: MarketFeedSymbolRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Dynamically remove a symbol from the market feed / 动态移除交易对"""
    if not DISPATCHER or not DISPATCHER.is_running():
        raise HTTPException(status_code=409, detail="Market feed not running / 行情流未运行")

    DISPATCHER.remove_symbol(req.symbol)
    return _paper_response({
        "message": f"Symbol {req.symbol} removed / 已移除交易对 {req.symbol}",
        "symbol": req.symbol,
    })


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
    """
    Manually feed a shadow decision tick.
    手动触发一次影子决策馈送（用于测试或手动模式）。

    Builds a shadow decision from current verdict/observation files and consumes it.
    """
    global SHADOW_CONSUMER
    if SHADOW_CONSUMER is None:
        SHADOW_CONSUMER = ShadowDecisionConsumer(ENGINE)

    # Build a minimal decision (no H-chain files — manual mode)
    decision = build_shadow_decision(symbol=req.symbol, market_prices=req.market_prices)
    result = SHADOW_CONSUMER.consume(decision, req.market_prices)
    return _paper_response(result)


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
    """Get shadow decisions stored in paper state / 获取存储在纸上状态中的影子决策"""
    state = ENGINE.get_state()
    decisions = state.get("shadow_decisions", [])[-min(limit, 200):]
    return _paper_response({"shadow_decisions": decisions, "count": len(decisions)})


# ═══════════════════════════════════════════════════════════════════════════════
# Metrics Route / 性能指标路由
# ═══════════════════════════════════════════════════════════════════════════════

@paper_router.get("/metrics")
def get_metrics(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get comprehensive performance metrics for the paper trading session.
    获取纸上交易 session 的综合性能指标。

    Includes: win rate, drawdown, holding period, Sharpe ratio, shadow decision stats.
    """
    state = ENGINE.get_state()
    metrics = compute_full_metrics(state)
    return _paper_response(metrics)


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
