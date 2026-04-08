"""Strategy Write Routes — POST/state-changing route handlers (TD-02 split)."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import Body, Depends, HTTPException, Request

from . import main_legacy as base
from .ipc_client import EngineIPCClient
from .strategy_wiring import (
    phase2_router,
    ORCHESTRATOR,
    KLINE_MANAGER,
    AUTO_DEPLOYER,
    _validate_strategy_name,
    _envelope,
)

logger = logging.getLogger(__name__)

# Module-level IPC client for strategy active/inactive sync to Rust.
# 模組級 IPC client，用於同步策略啟停狀態到 Rust 引擎。
_STRATEGY_IPC: EngineIPCClient | None = None


async def _get_strategy_ipc() -> EngineIPCClient:
    """Lazy-init IPC client for strategy activation sync.
    / 懶初始化用於策略啟停同步的 IPC client。
    """
    global _STRATEGY_IPC
    if _STRATEGY_IPC is None:
        _STRATEGY_IPC = EngineIPCClient()
        try:
            await _STRATEGY_IPC.connect()
        except Exception as e:
            logger.warning("strategy IPC connect failed: %s", e)
    return _STRATEGY_IPC


async def _sync_strategy_active(name: str, active: bool) -> None:
    """Fire-and-forget sync of strategy enable/disable to Rust engine via IPC.
    Failure is logged as warning — Python ORCHESTRATOR remains the fallback.
    / 透過 IPC 把策略啟停狀態同步到 Rust 引擎。失敗只記錄警告，Python 仍為備援。
    """
    try:
        client = await _get_strategy_ipc()
        resp = await client.call(
            "set_strategy_active",
            params={"strategy_name": name, "active": active},
        )
        if isinstance(resp, dict) and not resp.get("ok"):
            logger.warning("set_strategy_active IPC non-ok response: %s", resp)
    except Exception as e:
        logger.warning("set_strategy_active IPC error for %r active=%s: %s", name, active, e)


@phase2_router.post("/dynamic-risk/toggle")
async def toggle_dynamic_risk(request: Request, actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """
    Set dynamic risk adjustment on/off. Body: {"enabled": true/false}
    设置动态风控调整开关。
    """
    if AUTO_DEPLOYER is None:
        raise HTTPException(status_code=404, detail="Auto deployer not available")
    try:
        body = await request.json()
        enabled = bool(body.get("enabled", False))
        AUTO_DEPLOYER.set_dynamic_risk_enabled(enabled)
        return _envelope({"enabled": enabled, "message": "Dynamic risk " + ("enabled" if enabled else "disabled")})
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")


# TODO(R-IPC): Migrate to Rust command channel when available / 待 Rust 命令通道可用後遷移
@phase2_router.post("/{name}/activate")
async def activate_strategy(
    name: str,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Activate a registered strategy.
    激活已注册的策略。
    """
    if _validate_strategy_name(name) is None:
        raise HTTPException(status_code=400, detail="Invalid strategy name / 无效策略名称")
    try:
        success = ORCHESTRATOR.activate_strategy(name)
        if not success:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found / 策略 '{name}' 未找到")
        await _sync_strategy_active(name, active=True)
        return _envelope({
            "strategy": name,
            "action": "activated",
            "new_state": "active",
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error in activate_strategy / activate_strategy 异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


# TODO(R-IPC): Migrate to Rust command channel when available / 待 Rust 命令通道可用後遷移
@phase2_router.post("/{name}/pause")
async def pause_strategy(
    name: str,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Pause a running strategy.
    暂停运行中的策略。
    """
    if _validate_strategy_name(name) is None:
        raise HTTPException(status_code=400, detail="Invalid strategy name / 无效策略名称")
    try:
        success = ORCHESTRATOR.pause_strategy(name)
        if not success:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found / 策略 '{name}' 未找到")
        await _sync_strategy_active(name, active=False)
        return _envelope({
            "strategy": name,
            "action": "paused",
            "new_state": "paused",
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error in pause_strategy / pause_strategy 异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


# TODO(R-IPC): Migrate to Rust command channel when available / 待 Rust 命令通道可用後遷移
@phase2_router.post("/{name}/stop")
async def stop_strategy(
    name: str,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Stop a strategy.
    停止策略。
    """
    if _validate_strategy_name(name) is None:
        raise HTTPException(status_code=400, detail="Invalid strategy name / 无效策略名称")
    try:
        success = ORCHESTRATOR.stop_strategy(name)
        if not success:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found / 策略 '{name}' 未找到")
        await _sync_strategy_active(name, active=False)
        return _envelope({
            "strategy": name,
            "action": "stopped",
            "new_state": "stopped",
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error in stop_strategy / stop_strategy 异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


# ── Strategy Create & Delete Routes / 策略创建与删除路由 ──

# TODO(R-IPC): Migrate to Rust command channel when available / 待 Rust 命令通道可用後遷移
@phase2_router.post("/create")
async def create_strategy(
    request: dict[str, Any] = Body(...),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Create and register a new strategy instance.
    创建并注册新策略实例。AI Agent 或用户均可调用。

    Body JSON:
      strategy_type: str — one of: ma_crossover, bb_reversion, funding_arb, grid, bb_breakout
      symbol: str — trading pair (e.g. BTCUSDT)
      qty_per_trade: float — quantity per trade (optional, default 0.001)
      params: dict — additional strategy-specific params (optional)
    """
    from program_code.local_model_tools.strategies.ma_crossover import MACrossoverStrategy
    from program_code.local_model_tools.strategies.bollinger_reversion import BollingerReversionStrategy
    from program_code.local_model_tools.strategies.funding_rate_arb import FundingRateArbStrategy
    from program_code.local_model_tools.strategies.grid_trading import GridTradingStrategy
    from program_code.local_model_tools.strategies.bb_breakout import BBBreakoutStrategy

    stype = request.get("strategy_type", "").lower()
    symbol = request.get("symbol", "").upper()
    qty = request.get("qty_per_trade", 0.001)
    params = request.get("params", {})

    if not stype or not symbol:
        raise HTTPException(status_code=400, detail="strategy_type and symbol required / 需要 strategy_type 和 symbol")

    strategy = None
    try:
        if stype in ("ma_crossover", "trend"):
            strategy = MACrossoverStrategy(symbol=symbol, qty_per_trade=qty)
        elif stype in ("bb_reversion", "reversion"):
            strategy = BollingerReversionStrategy(symbol=symbol, qty_per_trade=qty)
        elif stype in ("funding_arb", "funding_rate_arb"):
            strategy = FundingRateArbStrategy(symbol=symbol, qty_per_trade=qty)
        elif stype in ("grid", "grid_trading"):
            upper = params.get("upper_price", 0)
            lower = params.get("lower_price", 0)
            grid_count = params.get("grid_count", 20)
            if not upper or not lower:
                raise HTTPException(status_code=400, detail="Grid strategy requires upper_price and lower_price in params / 网格策略需要 upper_price 和 lower_price")
            strategy = GridTradingStrategy(symbol=symbol, upper_price=upper, lower_price=lower,
                                          grid_count=grid_count, qty_per_grid=qty)
        elif stype in ("bb_breakout", "breakout"):
            strategy = BBBreakoutStrategy(symbol=symbol, qty_per_trade=qty)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown strategy_type: {stype} / 未知策略类型: {stype}")

        unique_name = f"{strategy.name}_{symbol}"
        ORCHESTRATOR.register_strategy(strategy, name=unique_name)

        # Add symbol to kline manager if new
        if KLINE_MANAGER and symbol not in KLINE_MANAGER.get_tracked_symbols():
            KLINE_MANAGER.add_symbol(symbol)

        return _envelope({
            "strategy": unique_name,
            "action": "created",
            "state": "idle",
            "symbol": symbol,
            "strategy_type": stype,
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error creating strategy / 创建策略异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


# TODO(R-IPC): Migrate to Rust command channel when available / 待 Rust 命令通道可用後遷移
@phase2_router.delete("/{name}")
async def delete_strategy(
    name: str,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Delete (remove) a strategy completely. Cannot be reactivated.
    完全删除策略（不可恢复）。与 stop 不同，delete 从注册表中移除。
    """
    if _validate_strategy_name(name) is None:
        raise HTTPException(status_code=400, detail="Invalid strategy name / 无效策略名称")
    try:
        success = ORCHESTRATOR.remove_strategy(name)
        if not success:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found / 策略 '{name}' 未找到")
        return _envelope({
            "strategy": name,
            "action": "deleted",
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error deleting strategy / 删除策略异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")
