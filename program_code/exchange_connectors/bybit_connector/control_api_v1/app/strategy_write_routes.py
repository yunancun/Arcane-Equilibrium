"""Strategy Write Routes — POST/state-changing route handlers (TD-02 split)."""
from __future__ import annotations

import logging
import os
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


def _strategy_toggle_live_enabled() -> bool:
    """POLICY-2 旗標讀取：OPENCLAW_STRATEGY_TOGGLE_LIVE_MODE 是否啟用 live 策略啟停。

    為何 default-OFF（fail-closed）：activate/pause/stop 原本是 Demo-only 策略開發
    控制（_sync_strategy_active 寫死 engine="demo"）。在旗標 OFF 下，engine="live"
    必須 fail-loud（409 live_strategy_toggle_disabled）而非靜默降級成 demo——靜默
    降級會讓 operator 以為改了 live 實則改了 demo，違反「失敗收縮 + 可審計」。只接受
    字面 "1"（鏡像既有 OPENCLAW_EDGE_RELOAD / OPENCLAW_ALLOW_MAINNET env-gate 慣例）。
    """
    return (os.environ.get("OPENCLAW_STRATEGY_TOGGLE_LIVE_MODE") or "").strip() == "1"


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
        # PHASE 0 AUTH-1：顯式傳 engine="demo" 而非缺省 engine。
        # 為何 demo：activate/pause/stop 路由僅 operator + strategy:write scope（非完整
        # live 五門），是策略開發/學習控制；缺 engine 時 Rust 走 primary()=live（live-running
        # 引擎），會被 live-write token chokepoint 擋。strategy 是 Demo-only 促升 lane
        # （CLAUDE §四），且此 sync 為 fire-and-forget（Python ORCHESTRATOR 為 fallback），
        # 故顯式鎖 demo pipeline、不在此非-5-gate 路徑鑄 live token（不弱化授權）。真正的
        # live 策略參數促升走 strategist_promote_routes（full 5-gate + token）。
        resp = await client.call(
            "set_strategy_active",
            params={"strategy_name": name, "active": active, "engine": "demo"},
        )
        if isinstance(resp, dict) and not resp.get("ok"):
            logger.warning("set_strategy_active IPC non-ok response: %s", resp)
    except Exception as e:
        logger.warning("set_strategy_active IPC error for %r active=%s: %s", name, active, e)


async def _sync_strategy_active_live(actor: base.AuthenticatedActor, name: str, active: bool) -> Any:
    """POLICY-2：把策略啟停同步到 **live** Rust pipeline（純 Rust IPC，不碰 Python 狀態）。

    為何鏡像 toggle_dynamic_risk(:72-142) 而非 _sync_strategy_active：改 live 策略啟停的
    後果等同改真實資金行為，故此路徑須先補完整 5-gate（all_five_live_gates_ok，
    require_authz=True）——strategy:write scope 單獨不足以授權 live（與 toggle_dynamic_risk
    同級）。通過後鑄 method-bound token，set_strategy_active ∈ Phase-0 LIVE_WRITE_METHODS，
    Rust dispatch chokepoint 會自驗 token（POLICY-2 不改 Rust）。

    硬邊界（fail-loud，非 fire-and-forget）：與 demo helper 不同，live 失敗必須上拋——
    5-gate 失敗 → 409 live_gate_failed；IPC 失敗由 caller 包成 500。live 路徑**不**呼
    ORCHESTRATOR.activate/pause/stop（那是 Python demo orchestrator 狀態），保持 live 啟停
    為純 Rust 權威，不污染 demo 狀態機。
    """
    from . import live_preflight  # noqa: PLC0415

    ok, reason_codes = live_preflight.all_five_live_gates_ok(actor, require_authz=True)
    if not ok:
        logger.warning(
            "Live set_strategy_active BLOCKED: gate_failed=%s actor=%s strategy=%r active=%s",
            reason_codes, getattr(actor, "actor_id", "unknown"), name, active,
        )
        raise HTTPException(
            status_code=409,
            detail={"error": "live_gate_failed", "gate_failed": reason_codes,
                    "message": "Live strategy toggle blocked — live preflight gate failed."},
        )
    from .live_patch_token import call_params_with_token  # noqa: PLC0415
    ipc_params: dict[str, Any] = {"strategy_name": name, "active": active, "engine": "live"}
    ipc_params = call_params_with_token("set_strategy_active", ipc_params)
    client = await _get_strategy_ipc()
    resp = await client.call("set_strategy_active", params=ipc_params)
    if isinstance(resp, dict) and not resp.get("ok"):
        logger.warning("live set_strategy_active IPC non-ok response: %s", resp)
    return resp


async def _resolve_toggle_engine(request: Request | None) -> str:
    """POLICY-2：從 activate/pause/stop 的 optional body 解析 engine（default "demo"）。

    回傳值僅可能是 "demo" 或 "live"（已通過旗標 / 合法性檢查）：
      - 無 request / 無 body / engine 缺省 / engine="demo" → "demo"（既有行為，bit-identical）。
      - engine="live" + 旗標 OFF → 409 live_strategy_toggle_disabled（fail-loud，
        **絕不**靜默降級成 demo）。
      - engine="live" + 旗標 ON → "live"（caller 走 5-gate live 路徑）。
      - 其他 engine 值（如 paper）→ 400（activate/pause/stop 僅 demo|live 語意；
        paper 啟停不屬此面）。

    為何只認 demo/live：原 demo helper 寫死 engine="demo"，POLICY-2 只新增 live 分支；
    paper pipeline 啟停不經此控制面（避免擴大 scope）。為何 request 可為 None：FastAPI
    HTTP routing 仍會注入真實 Request（型別注入，default 值不影響）；None 僅出現在
    直呼 handler 的單元測試路徑（無 body）→ 視為 demo，保 bit-identical。
    """
    if request is None:
        return "demo"
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    engine = str(body.get("engine", "demo")).strip().lower()
    if engine in ("", "demo"):
        return "demo"
    if engine == "live":
        if not _strategy_toggle_live_enabled():
            raise HTTPException(
                status_code=409,
                detail={"error": "live_strategy_toggle_disabled",
                        "message": "Live strategy toggle is disabled "
                                   "(OPENCLAW_STRATEGY_TOGGLE_LIVE_MODE off). "
                                   "Refusing to silently demote to demo."},
            )
        return "live"
    raise HTTPException(status_code=400, detail="engine must be demo|live")


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
    # PHASE 0 AUTH-1：engine=="live" 時 set_dynamic_risk_enabled ∈ LIVE_WRITE_METHODS
    # → Rust chokepoint 要求 token。此路由原本僅 strategy:write scope（非完整五門），故
    # 對 live 必須先補完整 5-gate（all_five_live_gates_ok，與 live RiskConfig 寫入同級
    # 後果——改 live 風險旋鈕等同改真實資金行為），通過後鑄 method-bound token。demo/paper
    # 維持既有零-token 行為（Demo 放寬 / Live 收緊政策）。**不可在缺 5-gate 下鑄 token**。
    ipc_params: dict[str, Any] = {"enabled": enabled, "engine": engine}
    if engine == "live":
        from . import live_preflight  # noqa: PLC0415
        ok, reason_codes = live_preflight.all_five_live_gates_ok(actor, require_authz=True)
        if not ok:
            logger.warning(
                "Live set_dynamic_risk_enabled BLOCKED: gate_failed=%s actor=%s",
                reason_codes, getattr(actor, "actor_id", "unknown"),
            )
            raise HTTPException(
                status_code=409,
                detail={"error": "live_gate_failed", "gate_failed": reason_codes,
                        "message": "Live dynamic-risk toggle blocked — live preflight gate failed."},
            )
        from .live_patch_token import call_params_with_token  # noqa: PLC0415
        ipc_params = call_params_with_token("set_dynamic_risk_enabled", ipc_params)
    try:
        client = await _get_strategy_ipc()
        resp = await client.call(
            "set_dynamic_risk_enabled",
            params=ipc_params,
        )
        # 為什麼檢 resp.get("ok")：舊碼 IPC 未拋例外即宣告 enabled；但 Rust 可能回
        # {"ok": false, ...}（如引擎拒絕、engine 未就緒）。不檢會 fake-success。
        # ok=false 時把 applied 標為 false 讓前端可分辨「已送達但未生效」，與既有
        # set_strategy_active 非-ok 記 log 的 pattern 一致。
        applied = not (isinstance(resp, dict) and resp.get("ok") is False)
        if not applied:
            logger.warning(
                "set_dynamic_risk_enabled IPC non-ok response engine=%s enabled=%s resp=%s",
                engine, enabled, resp,
            )
        # Best-effort stub mirror so `get_dynamic_risk_status` cached reads stay consistent.
        # 兼容用：同步更新 Python stub 的旗標，讓 stub fallback 路徑也看到最新狀態。
        # 僅在真生效時鏡像，避免 stub 與 Rust 權威狀態漂移。
        if applied and AUTO_DEPLOYER is not None:
            try:
                AUTO_DEPLOYER.set_dynamic_risk_enabled(enabled)
            except Exception:
                pass
        return _envelope({
            "enabled": enabled,
            "engine": engine,
            "applied": applied,
            "ipc_response": resp,
            "message": (
                f"Dynamic risk {'enabled' if enabled else 'disabled'} on {engine}"
                if applied else
                f"Dynamic risk toggle on {engine} not applied — engine rejected"
            ),
        })
    except HTTPException:
        raise
    except Exception as e:
        # WP-05 Real Fix
        logger.exception(
            "toggle_dynamic_risk IPC error engine=%s enabled=%s", engine, enabled,
        )
        from .error_sanitize import sanitize_exc_for_detail  # noqa: PLC0415
        raise HTTPException(
            status_code=500,
            detail=sanitize_exc_for_detail(e, "ipc_error"),
        )


# TODO(R-IPC): Migrate to Rust command channel when available / 待 Rust 命令通道可用後遷移
@phase2_router.post("/{name}/activate")
async def activate_strategy(
    name: str,
    request: Request = None,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Activate a registered strategy.
    激活已注册的策略。
    POLICY-2：optional body {"engine": "demo"|"live"}（default demo）。engine="live" 須旗標
    OPENCLAW_STRATEGY_TOGGLE_LIVE_MODE=1 + 完整 5-gate（純 Rust IPC，不碰 ORCHESTRATOR）。
    """
    _require_strategy_write(actor)
    if _validate_strategy_name(name) is None:
        raise HTTPException(status_code=400, detail="Invalid strategy name / 无效策略名称")
    engine = await _resolve_toggle_engine(request)
    try:
        if engine == "live":
            # live 啟停 = 純 Rust 權威，不觸 Python demo orchestrator 狀態。
            resp = await _sync_strategy_active_live(actor, name, active=True)
            return _envelope({
                "strategy": name,
                "action": "activated",
                "new_state": "active",
                "engine": "live",
                "ipc_response": resp,
            })
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
    request: Request = None,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Pause a running strategy.
    暂停运行中的策略。
    POLICY-2：optional body {"engine": "demo"|"live"}（default demo）。engine="live" 須旗標
    OPENCLAW_STRATEGY_TOGGLE_LIVE_MODE=1 + 完整 5-gate（純 Rust IPC，不碰 ORCHESTRATOR）。
    """
    _require_strategy_write(actor)
    if _validate_strategy_name(name) is None:
        raise HTTPException(status_code=400, detail="Invalid strategy name / 无效策略名称")
    engine = await _resolve_toggle_engine(request)
    try:
        if engine == "live":
            resp = await _sync_strategy_active_live(actor, name, active=False)
            return _envelope({
                "strategy": name,
                "action": "paused",
                "new_state": "paused",
                "engine": "live",
                "ipc_response": resp,
            })
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
    request: Request = None,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Stop a strategy.
    停止策略。
    POLICY-2：optional body {"engine": "demo"|"live"}（default demo）。engine="live" 須旗標
    OPENCLAW_STRATEGY_TOGGLE_LIVE_MODE=1 + 完整 5-gate（純 Rust IPC，不碰 ORCHESTRATOR）。
    """
    _require_strategy_write(actor)
    if _validate_strategy_name(name) is None:
        raise HTTPException(status_code=400, detail="Invalid strategy name / 无效策略名称")
    engine = await _resolve_toggle_engine(request)
    try:
        if engine == "live":
            resp = await _sync_strategy_active_live(actor, name, active=False)
            return _envelope({
                "strategy": name,
                "action": "stopped",
                "new_state": "stopped",
                "engine": "live",
                "ipc_response": resp,
            })
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
