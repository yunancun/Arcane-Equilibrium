from __future__ import annotations

"""
Paper Trading Risk Control Routes / 纸上交易风控路由
8 条路由：全局配置 / 品类配置 / Agent 调参 / 状态查询 / 冷却重置 / 熔断解除

MODULE_NOTE (中文):
  本模块提供风控管理的 REST API 接口。
  支持三层优先级风控的查看和配置。

MODULE_NOTE (English):
  REST API routes for the risk control layer.
  Supports viewing and configuring the 3-tier priority risk framework.
"""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from . import main_legacy as base

# ═══════════════════════════════════════════════════════════════════════════════
# Router / 路由器
# ═══════════════════════════════════════════════════════════════════════════════

risk_router = APIRouter(
    prefix="/api/v1/paper/risk",
    tags=["Paper Risk Control / 纸上风险控制"],
)


def _get_risk_manager():
    """Lazy import to avoid circular dependency."""
    from .paper_trading_routes import RISK_MANAGER
    return RISK_MANAGER


def _get_engine():
    """Lazy import."""
    from .paper_trading_routes import ENGINE
    return ENGINE


def _risk_response(data: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "data": data,
        "is_simulated": True,
        "data_category": "paper_risk_control",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Request Models / 请求模型
# ═══════════════════════════════════════════════════════════════════════════════

class GlobalConfigUpdate(BaseModel):
    max_stop_loss_pct: float | None = Field(default=None, gt=0, le=100)
    max_take_profit_pct: float | None = Field(default=None, gt=0, le=100)
    max_single_position_pct: float | None = Field(default=None, gt=0, le=100)
    max_total_exposure_pct: float | None = Field(default=None, gt=0, le=100)
    max_correlated_exposure_pct: float | None = Field(default=None, gt=0, le=100)
    max_leverage: float | None = Field(default=None, gt=0, le=200)
    max_session_drawdown_pct: float | None = Field(default=None, gt=0, le=100)
    max_daily_loss_pct: float | None = Field(default=None, gt=0, le=100)
    consecutive_loss_cooldown_count: int | None = Field(default=None, gt=0, le=100)
    consecutive_loss_cooldown_minutes: float | None = Field(default=None, gt=0, le=1440)
    max_holding_hours: float | None = Field(default=None, gt=0, le=8760)
    max_cost_edge_ratio: float | None = Field(default=None, gt=0, le=10)
    allowed_categories: list[str] | None = None
    preferred_margin_mode: str | None = None
    preferred_position_mode: str | None = None


class CategoryConfigUpdate(BaseModel):
    enabled: bool | None = None
    max_leverage: float | None = Field(default=None, gt=0, le=200)
    max_single_position_pct: float | None = Field(default=None, gt=0, le=100)
    max_total_exposure_pct: float | None = Field(default=None, gt=0, le=100)
    max_stop_loss_pct: float | None = Field(default=None, gt=0, le=100)
    max_holding_hours: float | None = Field(default=None, gt=0, le=8760)
    allowed_symbols: list[str] | None = None
    spot_allow_margin: bool | None = None
    perp_max_funding_rate_abs: float | None = Field(default=None, gt=0)
    option_max_premium_pct: float | None = Field(default=None, gt=0, le=100)
    option_max_delta_exposure: float | None = Field(default=None, gt=0)
    option_allowed_strategies: list[str] | None = None


class AgentAdjustRequest(BaseModel):
    effective_stop_loss_pct: float | None = Field(default=None, gt=0)
    effective_take_profit_pct: float | None = Field(default=None, gt=0)
    trailing_stop_enabled: bool | None = None
    trailing_stop_activation_pct: float | None = Field(default=None, gt=0)
    trailing_stop_distance_pct: float | None = Field(default=None, gt=0)
    position_size_multiplier: float | None = Field(default=None, ge=0.1, le=1.0)
    category_preference_weights: dict[str, float] | None = None
    prefer_limit_over_market: bool | None = None
    use_reduce_only_for_close: bool | None = None
    use_post_only_for_limit: bool | None = None


# ═══════════════════════════════════════════════════════════════════════════════
# Routes / 路由
# ═══════════════════════════════════════════════════════════════════════════════

@risk_router.get("/config")
def get_risk_config(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get full risk config (all 3 tiers) / 获取完整风控配置（三层）"""
    rm = _get_risk_manager()
    return _risk_response(rm.get_full_config())


@risk_router.post("/config/global")
def update_global_config(
    body: GlobalConfigUpdate,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Update P1 global risk config / 更新 P1 全局风控配置"""
    rm = _get_risk_manager()
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return _risk_response({"message": "no_updates", "config": rm.config.to_dict()})
    rm.update_global_config(updates)
    return _risk_response({"message": "updated", "config": rm.config.to_dict()})


@risk_router.get("/config/category/{category}")
def get_category_config(
    category: str,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get P0 category risk config / 获取 P0 品类风控配置"""
    rm = _get_risk_manager()
    cfg = rm.get_category_config(category)
    if cfg is None:
        return _risk_response({"category": category, "config": None, "message": "using_global_defaults"})
    return _risk_response({"category": category, "config": cfg.to_dict()})


@risk_router.post("/config/category/{category}")
def update_category_config(
    category: str,
    body: CategoryConfigUpdate,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Update P0 category risk config / 更新 P0 品类风控配置"""
    rm = _get_risk_manager()
    updates = body.model_dump(exclude_none=True)
    if not updates:
        cfg = rm.get_category_config(category)
        return _risk_response({"message": "no_updates", "config": cfg.to_dict() if cfg else None})
    cfg = rm.update_category_config(category, updates)
    return _risk_response({"message": "updated", "category": category, "config": cfg.to_dict()})


@risk_router.get("/status")
def get_risk_status(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get current risk status / 获取当前风控状态"""
    rm = _get_risk_manager()
    engine = _get_engine()
    status = rm.get_status()

    # Add session drawdown info
    try:
        state = engine.get_state()
        sess = state.get("session", {})
        peak = sess.get("peak_balance_usdt", sess.get("initial_paper_balance_usdt", 0))
        current = sess.get("current_paper_balance_usdt", 0)
        drawdown_pct = ((peak - current) / peak * 100) if peak > 0 else 0.0
        status["session_halted"] = sess.get("session_halted", False)
        status["session_halt_reason"] = sess.get("session_halt_reason")
        status["drawdown_pct"] = round(drawdown_pct, 2)
        status["peak_balance_usdt"] = peak
        status["current_balance_usdt"] = current
    except Exception:
        pass

    return _risk_response(status)


@risk_router.get("/ai-context")
def get_ai_risk_context(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get risk context for AI decision-making / 获取 AI 决策用风控上下文
    L2 AI engine should consult this before making trade recommendations.
    """
    rm = _get_risk_manager()
    engine = _get_engine()
    try:
        state = engine.get_state()
        ctx = rm.get_risk_context_for_ai(state)
    except Exception:
        ctx = {"risk_pressure": 0.0, "suggestion": "normal", "error": "state_read_failed"}
    return _risk_response(ctx)


@risk_router.post("/agent-adjust")
def agent_adjust(
    body: AgentAdjustRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Agent adjusts P2 params within caps / Agent 在上限内调整 P2 参数"""
    rm = _get_risk_manager()
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return _risk_response({"message": "no_updates", "agent_params": rm.agent_params.to_dict()})
    params = rm.agent_adjust(updates)
    return _risk_response({"message": "adjusted", "agent_params": params.to_dict()})


@risk_router.post("/reset-cooldown")
def reset_cooldown(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Manually reset consecutive loss cooldown / 手动重置连续亏损冷却"""
    rm = _get_risk_manager()
    rm.reset_cooldown()
    return _risk_response({"message": "cooldown_reset", "status": rm.get_status()})


@risk_router.post("/unhalt-session")
def unhalt_session(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Manually unhalt session after drawdown circuit breaker / 手动解除 session 熔断"""
    engine = _get_engine()

    def mutator(state):
        state["session"]["session_halted"] = False
        state["session"]["session_halt_reason"] = None
        return state

    engine.store.mutate(mutator)
    return _risk_response({"message": "session_unhalted"})
