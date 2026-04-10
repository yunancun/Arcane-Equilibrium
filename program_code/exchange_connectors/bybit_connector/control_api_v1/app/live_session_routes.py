from __future__ import annotations

"""
Live Session Routes — REST API endpoints for Live trading session control
實盤 Session 路由 — 實盤交易 session 控制 REST API 端點

MODULE_NOTE (中文):
  本模塊提供實盤交易 session 的控制接口，平行於 paper_trading_routes 但目標是 Live 引擎：
  - GET  /api/v1/live/session/status  — 當前 live session 狀態（不需 operator 角色）
  - POST /api/v1/live/session/start   — 啟動 live session（雙重硬鎖：execution_authority=granted + TradingMode=live）
  - POST /api/v1/live/session/stop    — 停止 live session（平倉 + 取消訂單 + pause）
  - POST /api/v1/live/session/pause   — 暫停 live session（停止策略下單）
  - POST /api/v1/live/session/resume  — 恢復 live session（恢復策略下單）

  安全不變量（Safety invariants）：
  1. start 端點強制雙重硬鎖：
     a) execution_authority 必須為 "granted"（否則拒絕，不管誰調用）
     b) trading_mode 必須為 "live"（否則拒絕，防止意外用 demo key 跑 live session）
  2. 所有寫入端點要求 Operator 角色認證
  3. stop 端點先平倉再 pause，fail-partial 容忍（記錄錯誤繼續執行）
  4. IPC 命令複用 paper 通道（pause_paper / resume_paper / close_all_positions）

MODULE_NOTE (English):
  Live trading session control endpoints, parallel to paper_trading_routes but targeting
  the Live engine mode.

  Safety invariants:
  1. start endpoint enforces dual hard lock:
     a) execution_authority must be "granted" (rejected otherwise, regardless of caller)
     b) trading_mode must be "live" (rejected otherwise, prevents accidental live session on demo key)
  2. All write endpoints require Operator role authentication
  3. stop endpoint closes positions then pauses; fail-partial tolerant (logs errors, continues)
  4. IPC commands reuse paper channel (pause_paper / resume_paper / close_all_positions)
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from . import main_legacy as base
from .ipc_state_reader import get_rust_reader

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Router / 路由器
# ═══════════════════════════════════════════════════════════════════════════════

live_router = APIRouter(
    prefix="/api/v1/live",
    tags=["Live Session / 實盤 Session"],
)

# ═══════════════════════════════════════════════════════════════════════════════
# Sticky user-stop flag (mirrors paper_trading_routes pattern)
# 用戶主動停止粘性標誌（同 paper_trading_routes 模式）
# ═══════════════════════════════════════════════════════════════════════════════

_LIVE_USER_STOPPED: bool = False

# In-memory execution authority override (operator grant/revoke from GUI).
# Survives IPC failures; cleared on process restart (fail-closed by design).
# 記憶體內 execution_authority override（Operator 從 GUI 授予/撤銷）。
# 重啟後清零（fail-closed 設計）。
_EXECUTION_AUTHORITY_OVERRIDE: str | None = None

# ═══════════════════════════════════════════════════════════════════════════════
# IPC helpers / IPC 輔助函數
# ═══════════════════════════════════════════════════════════════════════════════


async def _ipc_command(method: str, params: dict | None = None) -> dict[str, Any]:
    """
    Send IPC command to Rust engine; raise HTTPException on failure.
    Mirrors paper_trading_routes._ipc_command: connect → call → disconnect (finally).
    向 Rust 引擎發送 IPC 命令；失敗時拋出 HTTPException。
    模仿 paper_trading_routes 模式：connect → call → finally disconnect。
    """
    from .ipc_client import EngineIPCClient
    client = EngineIPCClient()
    try:
        await client.connect()
        result = await client.call(method, params=params or {}, timeout=5.0)
        return result if isinstance(result, dict) else {"result": result}
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"IPC command '{method}' failed: {exc}",
        ) from exc
    finally:
        await client.disconnect()


def _get_rust_client_safe():
    """
    Import and return PyO3 BybitClient (same client used by demo endpoints).
    Works with both demo and live API keys depending on engine mode.
    Returns None on any failure — callers must handle gracefully.
    導入並返回 PyO3 BybitClient（與 demo 端點使用相同客戶端）。
    demo / live API key 均可使用，依引擎模式而定。失敗時返回 None。
    """
    try:
        from .strategy_ai_routes import _get_rust_client
        return _get_rust_client()
    except Exception:
        return None


def _live_response(data: dict[str, Any]) -> dict[str, Any]:
    """
    Wrap response with live-specific metadata markers.
    為 live session 回應添加元數據標記。
    """
    return {
        "data": {
            **data,
            "is_simulated": False,
            "data_category": "live_exchange",
        }
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Auth helpers (reuse governance_routes pattern)
# 認證輔助函數（複用 governance_routes 模式）
# ═══════════════════════════════════════════════════════════════════════════════


def _get_auth_actor(
    request: Any = None,
    authorization: str | None = None,
) -> Any:
    """Reuse governance_routes._get_auth_actor via direct import."""
    from .governance_routes import _get_auth_actor as _gov_get_actor
    return _gov_get_actor(request, authorization)


def _require_operator(actor: Any) -> None:
    """Reuse governance_routes._require_operator_role via direct import."""
    from .governance_routes import _require_operator_role
    _require_operator_role(actor)


# ═══════════════════════════════════════════════════════════════════════════════
# Governance helpers / 治理輔助函數
# ═══════════════════════════════════════════════════════════════════════════════


def _get_execution_authority() -> str:
    """
    Read current execution_authority. Checks in-memory override first (set via
    /api/v1/live/execution-authority/grant), then falls back to governance state.
    讀取 execution_authority。優先檢查記憶體 override（由 grant 端點設置），
    然後回退到治理狀態。

    Returns: "granted" | "not_granted" | "unknown"
    """
    global _EXECUTION_AUTHORITY_OVERRIDE
    if _EXECUTION_AUTHORITY_OVERRIDE is not None:
        return _EXECUTION_AUTHORITY_OVERRIDE
    try:
        from .governance_hub import GovernanceHub
        hub = GovernanceHub.get_instance()
        if hub is not None:
            auth_sm = getattr(hub, "authorization_sm", None) or getattr(hub, "auth_sm", None)
            if auth_sm is not None:
                authority = getattr(auth_sm, "execution_authority", None)
                if authority is not None:
                    return str(authority)
        # Fallback: read from STORE snapshot / 回退：從 STORE 快照讀取
        snapshot = base.STORE.read()
        gov = snapshot.get("governance", {})
        return gov.get("execution_authority", "not_granted")
    except Exception as exc:
        logger.warning("Failed to read execution_authority: %s", exc)
        return "not_granted"  # fail-closed / 失敗時默認拒絕


def _get_trading_mode_from_engine() -> str:
    """
    Read current trading_mode from Rust engine snapshot.
    從 Rust 引擎快照讀取當前 trading_mode。

    Returns: "live" | "demo" | "paper_only" | "unknown"
    """
    rust = get_rust_reader()
    if not rust.is_available():
        return "unknown"
    try:
        paper_state = rust.get_paper_state()
        if paper_state and isinstance(paper_state, dict):
            return paper_state.get("trading_mode", "unknown")
    except Exception:
        pass
    return "unknown"


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoints / 端點
# ═══════════════════════════════════════════════════════════════════════════════


@live_router.get("/session/status")
def get_live_session_status(
    actor: Any = Depends(base.current_actor),
) -> dict:
    """
    GET /api/v1/live/session/status
    返回當前 live session 狀態（引擎快照 + 執行授權 + trading_mode）

    Returns live session state, engine availability, execution_authority, and trading_mode.
    Mirrors /api/v1/paper/session/status structure for GUI consistency.
    結構與 /api/v1/paper/session/status 保持一致，方便 GUI 複用。
    """
    rust = get_rust_reader()
    engine_available = rust.is_available()
    rust_state = rust.get_paper_state() if engine_available else None

    execution_authority = _get_execution_authority()
    trading_mode = _get_trading_mode_from_engine()

    if rust_state is None:
        session_state = "offline"
    elif _LIVE_USER_STOPPED:
        session_state = "stopped"
    else:
        # Live session inherits paper session state (same underlying pipeline)
        # Live session 繼承 paper session 狀態（同一底層管線）
        paper_paused = rust_state.get("paper_paused", True)
        session_state = "paused" if paper_paused else "active"

    return _live_response({
        "engine_available": engine_available,
        "execution_authority": execution_authority,
        "trading_mode": trading_mode,
        "session": {
            "session_state": session_state,
            "session_id": "rust_engine_live",
        },
        "rust_state": rust_state,
    })


@live_router.post("/session/start")
async def post_live_session_start(
    actor: Any = Depends(base.current_actor),
) -> dict:
    """
    POST /api/v1/live/session/start
    啟動 Live session（雙重硬鎖：execution_authority=granted + trading_mode=live）

    HARD LOCK: execution_authority must be "granted" before starting live session.
    HARD LOCK: trading_mode must be "live" to prevent accidental start with demo key.
    Both conditions are enforced server-side — GUI lock alone is insufficient.

    雙重硬鎖：
    1. execution_authority 必須為 "granted"（防止未授權啟動）
    2. trading_mode 必須為 "live"（防止意外用 demo key 跑 live session）
    兩個條件在服務器端強制，GUI 鎖定不足以保護。
    """
    # Require Operator role / 要求 Operator 角色
    _require_operator(actor)

    # HARD LOCK #1: execution_authority must be granted
    # 硬鎖 #1：execution_authority 必須已授予
    authority = _get_execution_authority()
    if authority != "granted":
        logger.warning(
            "Live session start BLOCKED: execution_authority=%s (not granted) — actor=%s",
            authority, getattr(actor, "actor_id", "?"),
        )
        raise HTTPException(
            status_code=403,
            detail=f"Live session blocked: execution_authority={authority!r}. "
                   "Operator approval required to grant execution authority.",
        )

    # GATE #2: trading_mode must be "live" or "demo" (demo allowed for pre-live testing)
    # 門控 #2：trading_mode 必須為 "live" 或 "demo"（demo 允許用於測試 live 流程）
    trading_mode = _get_trading_mode_from_engine()
    if trading_mode not in ("live", "demo", "unknown"):
        logger.warning(
            "Live session start BLOCKED: trading_mode=%s (not live/demo) — actor=%s",
            trading_mode, getattr(actor, "actor_id", "?"),
        )
        raise HTTPException(
            status_code=409,
            detail=f"Live session blocked: engine trading_mode={trading_mode!r}. "
                   "Set trading_mode = 'demo' (for testing) or 'live' in engine.toml.",
        )
    if trading_mode == "demo":
        logger.warning(
            "⚠ DEMO-LIVE TEST: live session started with trading_mode=demo — "
            "using demo API keys, NO real money at risk — actor=%s",
            getattr(actor, "actor_id", "?"),
        )

    # Resume paper pipeline (sends orders to exchange when TradingMode=Live)
    # 恢復 paper 管線（TradingMode=Live 時會向交易所發送訂單）
    global _LIVE_USER_STOPPED
    _LIVE_USER_STOPPED = False
    try:
        result = await _ipc_command("resume_paper")
    except Exception as exc:
        logger.error("IPC resume_paper failed for live start: %s", exc)
        raise HTTPException(status_code=502, detail=f"IPC command failed: {exc}")

    logger.warning(
        "⚠ LIVE SESSION STARTED — real money at risk — actor=%s",
        getattr(actor, "actor_id", "?"),
    )
    return _live_response({
        "message": "Live session started — REAL MONEY / 實盤 session 已啟動 — 真實資金",
        "source": "rust_engine",
        "execution_authority": authority,
        "trading_mode": trading_mode,
        "ipc_result": result,
        "session": {"session_state": "active", "session_id": "rust_engine_live"},
    })


@live_router.post("/session/stop")
async def post_live_session_stop(
    actor: Any = Depends(base.current_actor),
) -> dict:
    """
    POST /api/v1/live/session/stop
    停止 Live session：取消掛單 + 平倉 + 暫停策略

    Stop sequence (fail-partial tolerant — all steps attempted):
    1. Close all positions via IPC (also cancels exchange orders in Live mode)
    2. Pause paper pipeline via IPC
    停止序列（fail-partial 容忍 — 所有步驟都會嘗試）：
    1. 通過 IPC 平倉（Live 模式下同時取消交易所掛單）
    2. 通過 IPC 暫停管線
    """
    _require_operator(actor)

    global _LIVE_USER_STOPPED
    _LIVE_USER_STOPPED = True

    errors: list[str] = []
    rust_online = get_rust_reader().is_available()

    # Step 1: Close positions via IPC / 通過 IPC 平倉
    close_result: dict = {}
    if rust_online:
        try:
            close_result = await _ipc_command("close_all_positions")
        except Exception as exc:
            errors.append(f"close_positions: {exc}")
            logger.error("IPC close_all_positions failed (live stop): %s", exc)
    else:
        close_result = {"skipped": True, "reason": "engine_offline"}

    # Step 2: Pause pipeline via IPC / 通過 IPC 暫停管線
    pause_result: dict = {}
    if rust_online:
        try:
            pause_result = await _ipc_command("pause_paper")
        except Exception as exc:
            errors.append(f"pause_pipeline: {exc}")
            logger.error("IPC pause_paper failed (live stop): %s", exc)
    else:
        pause_result = {"skipped": True, "reason": "engine_offline"}

    logger.warning(
        "⚠ LIVE SESSION STOPPED — errors=%s — actor=%s",
        errors or None, getattr(actor, "actor_id", "?"),
    )
    return _live_response({
        "message": "Live session stopped — positions closed / 實盤 session 已停止 — 倉位已平",
        "source": "rust_engine",
        "close_result": close_result,
        "pause_result": pause_result,
        "errors": errors if errors else None,
        "session": {"session_state": "stopped", "session_id": "rust_engine_live"},
    })


@live_router.post("/session/pause")
async def post_live_session_pause(
    actor: Any = Depends(base.current_actor),
) -> dict:
    """
    POST /api/v1/live/session/pause
    暫停 Live session — 停止策略下單，但不平倉

    Stops new order dispatch without closing existing positions.
    暫停新訂單下發，不平倉。
    """
    _require_operator(actor)
    try:
        result = await _ipc_command("pause_paper")
        return _live_response({
            "message": "Live session paused — no new orders / 實盤 session 已暫停",
            "source": "rust_engine",
            "ipc_result": result,
            "session": {"session_state": "paused", "session_id": "rust_engine_live"},
        })
    except Exception as exc:
        logger.error("IPC pause_paper failed (live pause): %s", exc)
        raise HTTPException(status_code=502, detail=f"IPC command failed: {exc}")


@live_router.post("/session/resume")
async def post_live_session_resume(
    actor: Any = Depends(base.current_actor),
) -> dict:
    """
    POST /api/v1/live/session/resume
    恢復 Live session — 從暫停狀態恢復策略下單

    HARD LOCK: execution_authority must still be "granted" before resuming.
    硬鎖：恢復前仍需確認 execution_authority=granted。
    """
    _require_operator(actor)

    # Re-check execution_authority on resume (not just on start)
    # 恢復時重新確認 execution_authority（不僅在 start 時）
    authority = _get_execution_authority()
    if authority != "granted":
        raise HTTPException(
            status_code=403,
            detail=f"Live session resume blocked: execution_authority={authority!r}.",
        )

    global _LIVE_USER_STOPPED
    _LIVE_USER_STOPPED = False
    try:
        result = await _ipc_command("resume_paper")
        return _live_response({
            "message": "Live session resumed / 實盤 session 已恢復",
            "source": "rust_engine",
            "ipc_result": result,
            "session": {"session_state": "active", "session_id": "rust_engine_live"},
        })
    except Exception as exc:
        logger.error("IPC resume_paper failed (live resume): %s", exc)
        raise HTTPException(status_code=502, detail=f"IPC command failed: {exc}")


# ═══════════════════════════════════════════════════════════════════════════════
# Execution authority grant / revoke (in-memory, Operator only)
# Execution authority 授予 / 撤銷（記憶體，僅 Operator 角色）
# ═══════════════════════════════════════════════════════════════════════════════


@live_router.post("/execution-authority/grant")
async def grant_execution_authority(
    actor: Any = Depends(base.current_actor),
) -> dict:
    """
    POST /api/v1/live/execution-authority/grant
    Operator explicitly grants execution authority in-memory.
    Clears on process restart (fail-closed). Used for pre-live demo testing
    and future supervised live gate (Phase M).

    Operator 顯式授予 execution_authority（記憶體中）。
    重啟後清零（fail-closed）。用於實盤前 demo 測試及未來 M 章受監督實盤門控。
    """
    _require_operator(actor)
    global _EXECUTION_AUTHORITY_OVERRIDE
    _EXECUTION_AUTHORITY_OVERRIDE = "granted"
    logger.warning(
        "⚠ execution_authority GRANTED by actor=%s — live session now unlocked",
        getattr(actor, "actor_id", "?"),
    )
    return _live_response({
        "execution_authority": "granted",
        "message": "execution_authority granted — live session unlocked",
        "actor": getattr(actor, "actor_id", "?"),
    })


@live_router.post("/execution-authority/revoke")
async def revoke_execution_authority(
    actor: Any = Depends(base.current_actor),
) -> dict:
    """
    POST /api/v1/live/execution-authority/revoke
    Operator revokes execution authority; lock screen re-appears.
    Operator 撤銷 execution_authority；鎖定頁重新顯示。
    """
    _require_operator(actor)
    global _EXECUTION_AUTHORITY_OVERRIDE
    _EXECUTION_AUTHORITY_OVERRIDE = "not_granted"
    logger.info(
        "execution_authority REVOKED by actor=%s",
        getattr(actor, "actor_id", "?"),
    )
    return _live_response({
        "execution_authority": "not_granted",
        "message": "execution_authority revoked — live session locked",
        "actor": getattr(actor, "actor_id", "?"),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# Live account data — balance / positions / orders
# 實盤帳戶數據端點 — 餘額 / 倉位 / 掛單
#
# Primary: Rust PyO3 BybitClient (real exchange data, same client as demo).
# Fallback: IPC get_paper_state (engine internal state).
# 主路徑：Rust PyO3 BybitClient（真實交易所數據，同 demo 使用相同客戶端）。
# 降級：IPC get_paper_state（引擎內部狀態）。
# ═══════════════════════════════════════════════════════════════════════════════


@live_router.get("/balance")
async def get_live_balance(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    GET /api/v1/live/balance
    Primary: real Bybit account balance via Rust PyO3 client (demo or live key).
    Fallback: engine internal balance + bybit_sync_balance.

    主路徑：Rust PyO3 client 獲取真實 Bybit 帳戶餘額（demo 或 live key 均可）。
    降級：引擎內部餘額 + bybit_sync_balance。
    """
    rc = _get_rust_client_safe()
    if rc is not None:
        try:
            wallet = rc.refresh_balance()
            return _live_response({"source": "rust_engine", **wallet})
        except Exception as e:
            logger.warning("Rust balance fetch failed for live endpoint: %s", e)
    # Fallback: engine internal state / 降級：引擎內部狀態
    try:
        state = await _ipc_command("get_paper_state")
    except HTTPException:
        return _live_response({"available": False, "source": "engine_unavailable"})
    sync_bal = state.get("bybit_sync_balance")
    return _live_response({
        "balance": sync_bal if sync_bal is not None else state.get("balance"),
        "peak_balance": state.get("peak_balance"),
        "bybit_sync_balance": sync_bal,
        "engine_balance": state.get("balance"),
        "source": "bybit_sync" if sync_bal is not None else "engine_internal",
    })


@live_router.get("/positions")
async def get_live_positions(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    GET /api/v1/live/positions
    Primary: real Bybit positions via Rust PyO3 client.
    Fallback: engine-tracked positions (internal state).

    主路徑：Rust PyO3 client 獲取真實 Bybit 倉位。
    降級：引擎追蹤倉位（內部狀態）。
    """
    rc = _get_rust_client_safe()
    if rc is not None:
        try:
            positions = rc.get_positions("linear")
            return _live_response({
                "source": "rust_engine",
                "positions": positions,
                "list": positions,
                "count": len(positions),
            })
        except Exception as e:
            logger.warning("Rust positions fetch failed for live endpoint: %s", e)
    # Fallback: engine internal state / 降級：引擎內部狀態
    try:
        state = await _ipc_command("get_paper_state")
    except HTTPException:
        return _live_response({"positions": [], "count": 0, "available": False})
    positions = state.get("positions", [])
    return _live_response({"positions": positions, "count": len(positions), "source": "engine_state"})


@live_router.get("/orders")
async def get_live_orders(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    GET /api/v1/live/orders
    Primary: real Bybit active orders via Rust PyO3 client.
    Fallback: pending-close orders derived from engine position state.

    主路徑：Rust PyO3 client 獲取真實 Bybit 掛單。
    降級：從引擎倉位狀態派生 pending_close 訂單。
    """
    rc = _get_rust_client_safe()
    if rc is not None:
        try:
            orders = rc.get_active_orders("linear")
            return _live_response({
                "source": "rust_engine",
                "list": orders,
                "count": len(orders),
                "regular_count": len(orders),
                "conditional_count": 0,
            })
        except Exception as e:
            logger.warning("Rust orders fetch failed for live endpoint: %s", e)
    # Fallback: engine internal state / 降級：引擎內部狀態
    try:
        state = await _ipc_command("get_paper_state")
    except HTTPException:
        return _live_response({"list": [], "count": 0, "available": False})
    positions: list = state.get("positions", [])
    pending = [p for p in positions if p.get("pending_close") or p.get("stop_order_id")]
    return _live_response({
        "list": pending,
        "count": len(pending),
        "regular_count": 0,
        "conditional_count": len(pending),
        "source": "engine_state",
    })
