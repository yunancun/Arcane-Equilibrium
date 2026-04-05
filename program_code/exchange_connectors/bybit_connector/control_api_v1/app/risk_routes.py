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

import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from . import main_legacy as base
from .ipc_state_reader import get_rust_reader

logger = logging.getLogger(__name__)

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
    tp_enabled: bool | None = None
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
    # ── Phase 3b+ additions: IPC-forwarded to Rust engine ──
    # 以下參數直接推送到 Rust 引擎 IPC
    p1_risk_pct: float | None = Field(default=None, gt=0, le=20,
        description="P1 per-trade risk cap as % of balance (e.g. 3 = 3%). / P1 單筆風險上限占餘額百分比")
    trailing_stop_pct: float | None = Field(default=None, ge=0, le=50,
        description="Trailing stop distance %. 0 or null = disabled. / 跟蹤止損百分比，0 或 null 禁用")
    atr_multiplier: float | None = Field(default=None, ge=0, le=10,
        description="ATR dynamic stop multiplier. 0 or null = disabled. / ATR 動態止損乘數，0 或 null 禁用")
    max_same_direction_positions: int | None = Field(default=None, gt=0, le=25,
        description="Guardian: max concurrent same-direction positions. / Guardian 同方向最大持倉數")
    h0_shadow_mode: bool | None = Field(default=None,
        description="H0 Gate shadow mode: true=observe only, false=active blocking. / H0 門控影子模式")


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
    # None = dynamic ATR-based mode; float = fixed override (gt=0 only when float)
    # None = 動態 ATR 模式；浮點數 = 固定覆蓋值
    effective_stop_loss_pct: float | None = None
    effective_take_profit_pct: float | None = None
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
    """Get full risk config (all 3 tiers) / 获取完整风控配置（三层）
    RRC-1-D4: Includes Rust engine's active risk configs as ground truth.
    RRC-1-D4：包含 Rust 引擎的活躍風控配置作為真相源。
    """
    rm = _get_risk_manager()
    config = rm.get_full_config()
    # RRC-1-D4: Append Rust engine's active configs / 附加 Rust 引擎活躍配置
    reader = get_rust_reader()
    snap = reader.get_snapshot() if reader.is_available() else None
    if snap is not None:
        config["rust_active"] = {
            "stop_config": snap.get("stop_config"),
            "guardian_config": snap.get("guardian_config"),
            "risk_manager_config": snap.get("risk_manager_config"),
            "source": "rust_engine",
        }
    return _risk_response(config)


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

    # Push ALL risk changes to Rust engine via IPC / 通過 IPC 推送所有風控變更到 Rust 引擎
    # Mapping: GUI field → IPC param
    # Note: p1_risk_pct is % in GUI/API, fraction in Rust IPC
    ipc_kwargs: dict = {}
    if "max_stop_loss_pct" in updates:
        ipc_kwargs["hard_stop_pct"] = updates["max_stop_loss_pct"]
    if "max_take_profit_pct" in updates:
        ipc_kwargs["take_profit_pct"] = updates["max_take_profit_pct"]
    if "max_leverage" in updates:
        ipc_kwargs["max_leverage"] = updates["max_leverage"]
    if "max_session_drawdown_pct" in updates:
        ipc_kwargs["max_drawdown_pct"] = updates["max_session_drawdown_pct"]
    if "max_holding_hours" in updates:
        ipc_kwargs["time_stop_hours"] = updates["max_holding_hours"]
    # Phase 3b+ additions — direct IPC params
    if "p1_risk_pct" in updates:
        ipc_kwargs["p1_risk_pct"] = updates["p1_risk_pct"] / 100.0  # GUI sends %, Rust expects fraction
    if "trailing_stop_pct" in updates:
        val = updates["trailing_stop_pct"]
        ipc_kwargs["trailing_stop_pct"] = val if val and val > 0 else None  # 0/null → disable
    if "atr_multiplier" in updates:
        val = updates["atr_multiplier"]
        ipc_kwargs["atr_multiplier"] = val if val and val > 0 else None  # 0/null → disable
    if "max_same_direction_positions" in updates:
        ipc_kwargs["max_same_direction_positions"] = updates["max_same_direction_positions"]
    if "h0_shadow_mode" in updates:
        ipc_kwargs["h0_shadow_mode"] = updates["h0_shadow_mode"]
    if ipc_kwargs:
        import asyncio
        from app.ipc_client import EngineIPCClient
        async def _push_risk():
            client = EngineIPCClient()
            try:
                await client.connect()
                await client.update_risk_config(**ipc_kwargs)
                await client.disconnect()
            except Exception:
                pass  # best-effort — Rust may not be running
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(_push_risk())
            else:
                loop.run_until_complete(_push_risk())
        except Exception:
            pass

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
    """Get current risk status / 获取当前风控状态
    RRC-1-D2: Rust snapshot is the single source of truth for runtime risk state.
    RRC-1-D2：Rust 快照為運行時風控狀態的單一真相源。
    """
    rm = _get_risk_manager()
    status = rm.get_status()

    # RRC-1-D2: Rust snapshot = primary source for runtime risk state
    # RRC-1-D2：Rust 快照 = 運行時風控狀態的主要來源
    reader = get_rust_reader()
    snap = reader.get_snapshot() if reader.is_available() else None
    if snap is not None:
        ps = snap.get("paper_state", {})
        peak = ps.get("peak_balance", 0)
        current = ps.get("balance", 0)
        status["drawdown_pct"] = round(snap.get("session_drawdown_pct", 0.0), 2)
        status["daily_loss_pct"] = round(snap.get("daily_loss_pct", 0.0), 2)
        status["peak_balance_usdt"] = peak
        status["current_balance_usdt"] = current
        status["session_halted"] = snap.get("session_halted", False)
        status["consecutive_losses"] = snap.get("consecutive_losses", {})
        status["h0_gate_stats"] = snap.get("h0_gate_stats")
        status["source"] = "rust_engine"
    else:
        logger.debug("Rust engine unavailable, no runtime risk data / Rust 引擎不可用")

    return _risk_response(status)


@risk_router.get("/ai-context")
def get_ai_risk_context(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get risk context for AI decision-making / 获取 AI 决策用风控上下文
    RRC-1-D2: Uses Rust snapshot for runtime state (ENGINE=None safe).
    """
    rm = _get_risk_manager()
    # RRC-1-D2: Build context from Rust snapshot (ENGINE=None safe).
    # RRC-1-D2：從 Rust 快照構建上下文（ENGINE=None 安全）。
    reader = get_rust_reader()
    snap = reader.get_snapshot() if reader.is_available() else None
    if snap is not None:
        dd = snap.get("session_drawdown_pct", 0.0)
        dl = snap.get("daily_loss_pct", 0.0)
        halted = snap.get("session_halted", False)
        pressure = min(1.0, max(dd, dl) / 10.0)  # 0-1 scale, 10%=max
        suggestion = "halt" if halted else ("reduce" if pressure > 0.5 else "normal")
        ctx = {
            "risk_pressure": round(pressure, 3),
            "suggestion": suggestion,
            "session_drawdown_pct": round(dd, 2),
            "daily_loss_pct": round(dl, 2),
            "session_halted": halted,
            "consecutive_losses": snap.get("consecutive_losses", {}),
            "source": "rust_engine",
        }
    else:
        ctx = {"risk_pressure": 0.0, "suggestion": "normal", "error": "rust_engine_unavailable"}
    return _risk_response(ctx)


@risk_router.post("/agent-adjust")
def agent_adjust(
    body: AgentAdjustRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Agent adjusts P2 params within caps / Agent 在上限内调整 P2 参数"""
    rm = _get_risk_manager()
    # Only include explicitly-set fields (model_fields_set tracks what the caller sent).
    # This allows sending null for SL/TP to enter dynamic mode.
    # 只包含顯式傳入的字段（model_fields_set 追蹤調用者發送了什麼）。
    # 這允許發送 null 讓 SL/TP 進入動態模式。
    updates = {k: v for k, v in body.model_dump().items() if k in body.model_fields_set}
    if not updates:
        return _risk_response({"message": "no_updates", "agent_params": rm.agent_params.to_dict()})
    params = rm.agent_adjust(updates)

    # Push agent risk adjustments to Rust engine via IPC
    # 通過 IPC 推送 Agent 風控調整到 Rust 引擎
    ipc_kwargs: dict = {}
    if "effective_stop_loss_pct" in updates and updates["effective_stop_loss_pct"] is not None:
        ipc_kwargs["hard_stop_pct"] = updates["effective_stop_loss_pct"]
    if "effective_take_profit_pct" in updates:
        ipc_kwargs["take_profit_pct"] = updates.get("effective_take_profit_pct")  # None = disable
    if "trailing_stop_distance_pct" in updates:
        ipc_kwargs["trailing_stop_pct"] = updates.get("trailing_stop_distance_pct")
    if ipc_kwargs:
        import asyncio
        from app.ipc_client import EngineIPCClient
        async def _push_agent_risk():
            client = EngineIPCClient()
            try:
                await client.connect()
                await client.update_risk_config(**ipc_kwargs)
                await client.disconnect()
            except Exception:
                pass
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(_push_agent_risk())
            else:
                loop.run_until_complete(_push_agent_risk())
        except Exception:
            pass

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
    # RC-10: Python ENGINE disabled — use PAPER_STORE directly
    # RC-10：Python ENGINE 已禁用 — 直接使用 PAPER_STORE
    from .paper_trading_routes import PAPER_STORE

    def mutator(state):
        state["session"]["session_halted"] = False
        state["session"]["session_halt_reason"] = None
        return state

    PAPER_STORE.mutate(mutator)

    # RRC-1-E4: Send Resume to Rust engine (clears session_halted + paper_paused).
    # RRC-1-E4：發送 Resume 到 Rust 引擎（清除 session_halted + paper_paused）。
    try:
        from .ipc_client import get_engine_ipc_client
        import asyncio
        client = get_engine_ipc_client()
        if client is not None:
            asyncio.get_event_loop().run_until_complete(client.resume_paper())
            logger.info("unhalt: IPC resume sent to Rust / 已發送 IPC resume 到 Rust")
    except Exception as e:
        logger.warning("unhalt: IPC resume failed (non-fatal): %s", e)

    return _risk_response({"message": "session_unhalted"})
