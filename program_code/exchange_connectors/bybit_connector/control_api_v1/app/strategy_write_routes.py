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


def _require_strategy_write(actor: base.AuthenticatedActor) -> None:
    """Shared Batch B gate for strategy state mutations.
    Batch B 共用策略狀態寫入閘門：必須是 Operator 且具 strategy:write scope。
    """
    base.require_scope_and_operator(actor, "strategy:write")


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
    Set dynamic risk adjustment on/off per engine. Body:
      {"enabled": true/false, "engine": "paper"|"demo"|"live"}
    设置动态风控调整开关（按引擎）。
    DYNAMIC-RISK-1: forwards to Rust IPC `set_dynamic_risk_enabled`; the Python
    AUTO_DEPLOYER is a stub so the authoritative toggle lives in the Rust pipeline.
    DYNAMIC-RISK-1：轉發到 Rust IPC；Python AUTO_DEPLOYER 為 stub，Rust 為權威。
    """
    _require_strategy_write(actor)
    try:
        body = await request.json()
    except Exception:
        body = {}
    enabled = bool(body.get("enabled", False))
    engine = str(body.get("engine", "demo")).lower()
    if engine not in ("paper", "demo", "live"):
        raise HTTPException(status_code=400, detail="engine must be paper|demo|live")
    try:
        client = await _get_strategy_ipc()
        resp = await client.call(
            "set_dynamic_risk_enabled",
            params={"enabled": enabled, "engine": engine},
        )
        # Best-effort stub mirror so `get_dynamic_risk_status` cached reads stay consistent.
        # 兼容用：同步更新 Python stub 的旗標，讓 stub fallback 路徑也看到最新狀態。
        if AUTO_DEPLOYER is not None:
            try:
                AUTO_DEPLOYER.set_dynamic_risk_enabled(enabled)
            except Exception:
                pass
        return _envelope({
            "enabled": enabled,
            "engine": engine,
            "ipc_response": resp,
            "message": f"Dynamic risk {'enabled' if enabled else 'disabled'} on {engine}",
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("toggle_dynamic_risk IPC error engine=%s enabled=%s: %s", engine, enabled, e)
        raise HTTPException(status_code=500, detail=f"IPC error: {e}")


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
    _require_strategy_write(actor)
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
    _require_strategy_write(actor)
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
    _require_strategy_write(actor)
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
    [DEPRECATED] Python strategy creation removed — Rust engine manages all strategies.
    [已廢棄] Python 策略創建已移除 — Rust 引擎管理所有策略。
    """
    _require_strategy_write(actor)
    raise HTTPException(
        status_code=410,
        detail="Python strategy creation removed (DEAD-PY-3). Strategies are managed by Rust engine. / Python 策略創建已移除，策略由 Rust 引擎管理。",
    )


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
    _require_strategy_write(actor)
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
