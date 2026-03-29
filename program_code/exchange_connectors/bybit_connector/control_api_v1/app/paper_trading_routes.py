from __future__ import annotations

"""
OpenClaw Paper Trading API Routes / 纸上交易 API 路由
OpenClaw 模拟交易系统的所有 REST API 端点

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
# Paper State Store Initialization / 纸上状态存储初始化
# ═══════════════════════════════════════════════════════════════════════════════

_paper_state_path = os.getenv(
    "OPENCLAW_PAPER_STATE_FILE",
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "runtime", "paper_trading_state.json")
    ),
)
PAPER_STORE = PaperStateStore(_paper_state_path)

# Risk manager (3-tier priority: P0 category > P1 global > P2 agent)
# 风控管理器（三层优先级：P0 品类专属 > P1 全局 > P2 Agent 自适应）
from .risk_manager import RiskManager  # noqa: E402
RISK_MANAGER = RiskManager()
ENGINE = PaperTradingEngine(PAPER_STORE, risk_manager=RISK_MANAGER)

# Governance Hub (SM-01 + SM-04 + SM-02 + EX-04 integration)
# 治理集線器（授權 + 風控 + 租約 + 對賬 集成）
from .governance_hub import GovernanceHub  # noqa: E402
import os as _gov_os
_gov_audit_dir = _gov_os.getenv(
    "OPENCLAW_GOVERNANCE_AUDIT_DIR",
    _gov_os.path.abspath(_gov_os.path.join(_gov_os.path.dirname(__file__), "..", "runtime", "governance_audit"))
)
GOV_HUB = GovernanceHub(audit_dir=_gov_audit_dir)
ENGINE.set_governance_hub(GOV_HUB)
RISK_MANAGER.set_governance_hub(GOV_HUB)

# Export GOV_HUB as _GOVERNANCE_HUB for governance_routes.py to import
# This creates a singleton reference for the governance API routes
# 将 GOV_HUB 导出为 _GOVERNANCE_HUB，供 governance_routes.py 导入
import sys as _sys_ref
_current_module = _sys_ref.modules[__name__]
_current_module._GOVERNANCE_HUB = GOV_HUB

# Market data dispatcher (lazy-initialized on first start)
# 行情分发器（首次启动时延迟初始化）
DISPATCHER: MarketDataDispatcher | None = None

# Shadow decision consumer (lazy-initialized with engine)
# 影子决策消费器（与引擎延迟初始化）
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
    symbol: str = Field(max_length=30)
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
    """Start a new paper trading session / 开始新的纸上交易 session"""
    try:
        state = ENGINE.start_session(initial_balance=req.initial_balance)
        return _paper_response({"session": state["session"], "message": "Paper trading session started"})
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@paper_router.post("/session/pause")
def post_session_pause(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Pause the current session / 暂停当前 session"""
    try:
        state = ENGINE.pause_session()
        return _paper_response({"session": state["session"]})
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@paper_router.post("/session/resume")
def post_session_resume(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Resume a paused session / 恢复已暂停的 session"""
    try:
        state = ENGINE.resume_session()
        return _paper_response({"session": state["session"]})
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@paper_router.post("/session/stop")
def post_session_stop(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Stop the session and finalize PnL / 停止 session 并结算 PnL"""
    try:
        state = ENGINE.stop_session()
        return _paper_response({
            "session": state["session"],
            "pnl": state["pnl"],
            "message": "Paper trading session stopped and PnL finalized",
        })
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@paper_router.get("/session/status")
def get_session_status(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get current session status / 获取 session 状态"""
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
        # Use live market prices from dispatcher if available, fall back to order price
        # 优先使用来自行情分发器的实时价格，否则回退到订单价格
        live_prices = None
        if DISPATCHER and DISPATCHER.is_running():
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
        raise HTTPException(status_code=400, detail=str(e))


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
    positions = ENGINE.get_positions()
    return _paper_response({"positions": positions, "count": len(positions)})


@paper_router.get("/fills")
def get_fills(
    limit: int = 50,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get fill history / 获取成交历史"""
    fills = ENGINE.get_fills(limit=min(limit, 200))
    return _paper_response({"fills": fills, "count": len(fills)})


@paper_router.get("/pnl")
def get_pnl(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get paper PnL summary / 获取纸上 PnL 汇总"""
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
    symbol: str = Field(max_length=30)


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

    # Register pipeline bridge as tick consumer / 注册管线桥接器为 tick 消费者
    try:
        from .phase2_strategy_routes import PIPELINE_BRIDGE
        if PIPELINE_BRIDGE is not None:
            DISPATCHER.register_tick_consumer(PIPELINE_BRIDGE)
            PIPELINE_BRIDGE.activate()
            logger.info("Pipeline bridge registered and activated / 管线桥接器已注册并激活")
    except ImportError:
        logger.warning("Pipeline bridge not available / 管线桥接器不可用")

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
    symbol: str = Field(default="BTCUSDT", max_length=30)


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
