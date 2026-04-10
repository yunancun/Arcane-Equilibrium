from __future__ import annotations

"""
Live Session Routes — REST API endpoints for Live trading session control
實盤 Session 路由 — 實盤交易 session 控制 REST API 端點

MODULE_NOTE (中文):
  本模塊提供實盤交易 session 的控制接口，平行於 paper_trading_routes 但目標是 Live 引擎：
  - GET  /api/v1/live/session/status  — 當前 live session 狀態（不需 operator 角色）
  - POST /api/v1/live/session/start   — 啟動 live session（門控：Operator 角色 + live_reserved global mode）
  - POST /api/v1/live/session/stop    — 停止 live session（平倉 + 取消訂單）
  - POST /api/v1/live/session/pause   — 暫停 live session（停止策略下單）
  - POST /api/v1/live/session/resume  — 恢復 live session（恢復策略下單）

  安全不變量（Safety invariants）：
  1. 所有寫入端點要求 Operator 角色認證（唯一門控）
  2. start 端點雙重門控：Operator 角色 + live_reserved global mode
  3. start 時自動授予 execution_authority（fail-closed：重啟清零，stop 後重置）
  4. stop 端點只平倉，不 pause 引擎管線 — paper/demo 不受影響
  5. IPC 命令複用 paper 通道（resume_paper / close_all_positions）
  6. start 時向 GovernanceHub 提交 live 授權申請（非阻塞審計留痕）

MODULE_NOTE (English):
  Live trading session control endpoints, parallel to paper_trading_routes but targeting
  the Live engine mode.

  Safety invariants:
  1. All write endpoints require Operator role authentication (single gate)
  2. start has dual gate: Operator role + live_reserved global mode
  3. execution_authority auto-granted on start (fail-closed: cleared on restart, reset on stop)
  4. stop endpoint only closes positions, does NOT pause engine pipeline — paper/demo unaffected
  5. IPC commands reuse paper channel (resume_paper / close_all_positions)
  6. start submits live authorization request to GovernanceHub (non-blocking audit trail)
"""

import asyncio
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
# Live contraction monitor state / 實盤縮倉監控狀態
# ═══════════════════════════════════════════════════════════════════════════════

# Drawdown thresholds (from session-start peak equity).
# 回撤閾值（相對於 session 啟動時的峰值淨值）。
CONTRACTION_WARN_PCT:  float = 5.0   # -5%  → warning log only / 僅記警告
CONTRACTION_HALT_PCT:  float = 15.0  # -15% → auto-halt: revoke auth + close positions / 自動停止

# Current contraction state: "normal" | "warned" | "halted"
# 當前縮倉狀態
_live_contraction_state: str = "normal"

# Background monitor asyncio task (None when session is not active)
# 後台監控 asyncio task（session 非活躍時為 None）
_live_monitor_task: asyncio.Task | None = None

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


def _get_global_mode_state() -> str:
    """
    Read current global_mode_state from STORE snapshot.
    從 STORE 快照讀取當前 global_mode_state。

    Returns: "live_reserved" | "demo_reserved" | "shadow_only" | "observe_only" | "design_only" | "unknown"
    """
    try:
        snapshot = base.STORE.read()
        gr = snapshot.get("global_runtime", {})
        # Try derived path first (compiled state)
        mode = gr.get("derived", {}).get("global_mode_state", "")
        if mode:
            return mode
        # Fallback: controls switch
        controls = gr.get("controls", {})
        sw = controls.get("global_execution_mode_switch", "")
        return sw if sw else "unknown"
    except Exception as exc:
        logger.warning("Failed to read global_mode_state: %s", exc)
        return "unknown"


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


def _freeze_live_governance_auth(reason: str = "auto_halt_drawdown") -> None:
    """
    Freeze the live-scoped GovernanceHub authorization after auto-halt.
    Creates an audit record showing why the session was stopped.
    在自動停止後凍結 GovernanceHub 中 mode=live 的授權，生成審計記錄。
    """
    try:
        from .governance_hub import GovernanceHub
        hub = GovernanceHub.get_instance()
        if hub is None:
            return
        auth_sm = getattr(hub, "_authorization_sm", None)
        if auth_sm is None:
            return
        effective = auth_sm.get_effective()
        for auth in effective:
            scope = getattr(auth, "scope", {}) or {}
            if isinstance(scope, dict) and scope.get("mode") == "live":
                auth_sm.freeze(auth.authorization_id, reason)
                logger.info(
                    "GovernanceHub live authorization frozen (id=%s reason=%s) / "
                    "實盤 GovernanceHub 授權已凍結（id=%s reason=%s）",
                    auth.authorization_id, reason,
                    auth.authorization_id, reason,
                )
    except Exception as exc:
        logger.warning(
            "Failed to freeze live governance auth (non-fatal): %s / "
            "凍結實盤治理授權失敗（非致命）: %s", exc, exc,
        )


async def _live_contraction_monitor() -> None:
    """
    Background drawdown monitor — runs while live session is active.
    Polls engine state every 5 minutes; auto-halts on drawdown breach.

    Uses PaperStateSnapshot fields (peak_balance + bybit_sync_balance/balance)
    directly from the Rust engine via IPC — no separate peak tracking needed.

    Levels:
      normal  → drawdown < CONTRACTION_WARN_PCT
      warned  → CONTRACTION_WARN_PCT ≤ drawdown < CONTRACTION_HALT_PCT (log only)
      halted  → drawdown ≥ CONTRACTION_HALT_PCT → revoke auth + close positions

    後台回撤監控 — 實盤 session 活躍時持續運行，每 5 分鐘輪詢引擎狀態。
    直接使用 Rust PaperStateSnapshot（peak_balance + bybit_sync_balance/balance）。
    警告閾值：只記錄。停止閾值：撤銷授權 + 平倉。
    """
    global _live_contraction_state, _EXECUTION_AUTHORITY_OVERRIDE, _LIVE_USER_STOPPED

    POLL_INTERVAL_S = 300  # 5 minutes / 5 分鐘
    logger.info("Live contraction monitor started / 縮倉監控已啟動")

    while True:
        try:
            await asyncio.sleep(POLL_INTERVAL_S)
        except asyncio.CancelledError:
            logger.info("Live contraction monitor cancelled / 縮倉監控已取消")
            return

        # Skip check if session already stopped by user or authority revoked
        if _LIVE_USER_STOPPED or _EXECUTION_AUTHORITY_OVERRIDE != "granted":
            logger.debug("Contraction monitor: session inactive — skipping check")
            continue

        try:
            state = await _ipc_command("get_paper_state")
        except Exception as exc:
            logger.warning("Contraction monitor: IPC get_paper_state failed: %s", exc)
            continue

        try:
            # Prefer exchange-synced balance; fall back to internal engine balance
            # 優先使用交易所同步餘額，否則使用引擎內部餘額
            equity = float(
                state.get("bybit_sync_balance") or state.get("balance") or 0
            )
            peak   = float(state.get("peak_balance") or equity)

            if equity <= 0 or peak <= 0:
                logger.debug("Contraction monitor: equity/peak not available yet")
                continue

            drawdown_pct = ((peak - equity) / peak) * 100.0

            if drawdown_pct >= CONTRACTION_HALT_PCT:
                # ── AUTO-HALT ────────────────────────────────────────────────
                # Drawdown exceeded halt threshold: revoke authority + close positions
                # 回撤超過停止閾值：撤銷授權 + 平倉
                _live_contraction_state  = "halted"
                _EXECUTION_AUTHORITY_OVERRIDE = None

                logger.error(
                    "🚨 LIVE AUTO-HALT — drawdown=%.1f%% >= halt_threshold=%.1f%% "
                    "(peak=%.2f, current=%.2f) — execution_authority REVOKED, closing positions / "
                    "🚨 實盤自動停止 — 回撤=%.1f%% ≥ 閾值=%.1f%% "
                    "（峰值=%.2f，當前=%.2f）— 已撤銷 execution_authority，平倉中",
                    drawdown_pct, CONTRACTION_HALT_PCT, peak, equity,
                    drawdown_pct, CONTRACTION_HALT_PCT, peak, equity,
                )

                # Close all positions (best-effort; error logged but not re-raised)
                # 平倉（盡力而為；錯誤記錄但不重拋）
                try:
                    await _ipc_command("close_all_positions")
                    logger.info("Auto-halt: close_all_positions dispatched / 自動停止：已下發平倉命令")
                except Exception as close_exc:
                    logger.error(
                        "Auto-halt: close_all_positions failed: %s / 自動停止：平倉失敗: %s",
                        close_exc, close_exc,
                    )

                # Freeze GovernanceHub live authorization (audit trail)
                # 凍結 GovernanceHub 實盤授權（審計留痕）
                _freeze_live_governance_auth(
                    f"auto_halt_drawdown_{drawdown_pct:.1f}pct"
                )
                return  # Stop monitoring after halt / 停止後退出監控循環

            elif drawdown_pct >= CONTRACTION_WARN_PCT:
                if _live_contraction_state != "warned":
                    _live_contraction_state = "warned"
                    logger.warning(
                        "⚠ Live drawdown WARNING: %.1f%% (warn_threshold=%.1f%%) "
                        "peak=%.2f current=%.2f / "
                        "⚠ 實盤回撤警告：%.1f%%（閾值=%.1f%%）峰值=%.2f 當前=%.2f",
                        drawdown_pct, CONTRACTION_WARN_PCT, peak, equity,
                        drawdown_pct, CONTRACTION_WARN_PCT, peak, equity,
                    )
                else:
                    # Already warned — log at debug level only
                    logger.debug(
                        "Contraction monitor: drawdown=%.1f%% (warned state, threshold=%.1f%%)",
                        drawdown_pct, CONTRACTION_WARN_PCT,
                    )
            else:
                # Recovery below warn threshold
                if _live_contraction_state == "warned":
                    logger.info(
                        "Live drawdown recovered: %.1f%% < %.1f%% — state: warned → normal / "
                        "實盤回撤恢復：%.1f%% < %.1f%% — 狀態：warned → normal",
                        drawdown_pct, CONTRACTION_WARN_PCT,
                        drawdown_pct, CONTRACTION_WARN_PCT,
                    )
                _live_contraction_state = "normal"

        except Exception as exc:
            logger.warning(
                "Contraction monitor: check error (non-fatal): %s / 縮倉監控：檢查異常（非致命）: %s",
                exc, exc,
            )


def _submit_live_governance_request(actor_id: str) -> None:
    """
    Submit a live-mode authorization request to GovernanceHub (non-blocking).
    Creates a PENDING record visible in the Governance tab for operator awareness.
    Failure is logged as warning but never blocks live session start.

    向 GovernanceHub 提交實盤授權申請（非阻塞）。
    在治理頁創建 PENDING 記錄供 Operator 確認；失敗僅警告，不阻塞 session 啟動。
    """
    try:
        from .governance_hub import GovernanceHub
        hub = GovernanceHub.get_instance()
        if hub is None or not getattr(hub, "_initialized", False):
            logger.debug("GovernanceHub not ready — skipping live governance request")
            return
        auth_sm = getattr(hub, "_authorization_sm", None)
        if auth_sm is None:
            logger.debug("GovernanceHub._authorization_sm not available")
            return
        import time as _time
        live_scope = {
            "mode": "live",
            "execution": ["live_submit", "paper_submit"],
            "auto_approved": False,
        }
        expires_at_ms = int((_time.time() + 24 * 3600) * 1000)  # 24h TTL
        auth_obj = auth_sm.create_draft(
            title=f"Live Session Authorization — {actor_id}",
            scope=live_scope,
            created_by=actor_id,
            description=(
                f"Live session started by operator '{actor_id}'. "
                "Requires daily operator acknowledgement. / "
                f"實盤 session 由 Operator '{actor_id}' 啟動，需每日確認。"
            ),
            expires_at_ms=expires_at_ms,
        )
        auth_sm.submit_for_approval(auth_obj.authorization_id)
        logger.info(
            "Live governance request submitted (id=%s) — pending operator approval / "
            "實盤治理申請已提交（id=%s）— 待 Operator 批准",
            auth_obj.authorization_id, auth_obj.authorization_id,
        )
    except Exception as exc:
        logger.warning(
            "Failed to submit live governance request (non-fatal): %s / "
            "提交實盤治理申請失敗（非致命）: %s", exc, exc,
        )


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

    # Derive drawdown info from engine state for status display
    # 從引擎狀態派生回撤信息用於狀態顯示
    drawdown_info: dict = {}
    if rust_state and isinstance(rust_state, dict):
        try:
            bal   = float(rust_state.get("bybit_sync_balance") or rust_state.get("balance") or 0)
            peak  = float(rust_state.get("peak_balance") or bal)
            if peak > 0 and bal > 0:
                drawdown_info = {
                    "drawdown_pct": round(((peak - bal) / peak) * 100, 2),
                    "peak_balance": round(peak, 4),
                    "current_balance": round(bal, 4),
                }
        except Exception:
            pass

    return _live_response({
        "engine_available": engine_available,
        "execution_authority": execution_authority,
        "trading_mode": trading_mode,
        "session": {
            "session_state": session_state,
            "session_id": "rust_engine_live",
        },
        "rust_state": rust_state,
        "contraction": {
            "state": _live_contraction_state,
            "warn_pct": CONTRACTION_WARN_PCT,
            "halt_pct": CONTRACTION_HALT_PCT,
            **drawdown_info,
        },
    })


@live_router.post("/session/start")
async def post_live_session_start(
    actor: Any = Depends(base.current_actor),
) -> dict:
    """
    POST /api/v1/live/session/start
    啟動 Live session。

    Guard: Operator role auth is the single gate (no separate execution_authority check).
    trading_mode is read for logging/context only — engine config controls actual routing.

    保護：Operator 角色認證是唯一門控，不設獨立 execution_authority 二次確認。
    trading_mode 僅用於日誌/上下文，引擎配置控制實際訂單路由。
    """
    # Require Operator role — primary gate / 要求 Operator 角色 — 主門控
    _require_operator(actor)

    # Gate: global_mode_state must include 'live' (i.e. live_reserved or live_enabled)
    # 門控：global_mode_state 必須含 'live'（即 live_reserved 或 live_enabled）
    global_mode = _get_global_mode_state()
    if "live" not in global_mode:
        logger.warning(
            "Live session start BLOCKED: global_mode=%s (not live_reserved) — actor=%s",
            global_mode, getattr(actor, "actor_id", "?"),
        )
        raise HTTPException(
            status_code=409,
            detail=f"Live session blocked: global_mode={global_mode!r}. "
                   "Switch Global Mode to live_reserved in the System Overview tab first.",
        )

    trading_mode = _get_trading_mode_from_engine()

    # Auto-grant execution_authority on session start.
    # Double gate (Operator role + live_reserved global mode) is already verified above.
    # No separate manual grant step required — cleared on stop / process restart (fail-closed).
    # 啟動時自動授予 execution_authority。
    # 雙重門控（Operator 角色 + live_reserved global mode）已在上方驗證。
    # 無需另行手動 grant — stop 時 / 進程重啟後清零（fail-closed）。
    global _EXECUTION_AUTHORITY_OVERRIDE, _LIVE_USER_STOPPED, \
           _live_contraction_state, _live_monitor_task
    _EXECUTION_AUTHORITY_OVERRIDE = "granted"
    _LIVE_USER_STOPPED = False
    _live_contraction_state = "normal"

    # Submit live governance request for operator audit trail (non-blocking)
    # 提交實盤治理申請用於操作員審計留痕（非阻塞）
    _submit_live_governance_request(getattr(actor, "actor_id", "live_operator"))

    # Resume engine pipeline if it was paused by a previous stop
    # 如果管線因上次 stop 而暫停，恢復管線
    result: dict = {}
    try:
        result = await _ipc_command("resume_paper")
    except Exception as exc:
        logger.warning("IPC resume_paper skipped (engine may already be running): %s", exc)

    # Start drawdown contraction monitor (cancel any stale task first)
    # 啟動回撤縮倉監控（先取消舊 task）
    if _live_monitor_task is not None and not _live_monitor_task.done():
        _live_monitor_task.cancel()
    _live_monitor_task = asyncio.create_task(_live_contraction_monitor())

    logger.warning(
        "⚠ LIVE SESSION STARTED — trading_mode=%s execution_authority=granted "
        "contraction_monitor=active warn=%.0f%% halt=%.0f%% — actor=%s",
        trading_mode, CONTRACTION_WARN_PCT, CONTRACTION_HALT_PCT,
        getattr(actor, "actor_id", "?"),
    )
    return _live_response({
        "message": "Live session started / 實盤 session 已啟動",
        "source": "rust_engine",
        "trading_mode": trading_mode,
        "authority": "granted",
        "ipc_result": result,
        "session": {"session_state": "active", "session_id": "rust_engine_live"},
        "contraction": {
            "state": "normal",
            "warn_pct": CONTRACTION_WARN_PCT,
            "halt_pct": CONTRACTION_HALT_PCT,
        },
    })


@live_router.post("/session/stop")
async def post_live_session_stop(
    actor: Any = Depends(base.current_actor),
) -> dict:
    """
    POST /api/v1/live/session/stop
    停止 Live session：平倉 + 取消交易所掛單。

    Stop only closes live positions. Does NOT pause the engine pipeline —
    paper/demo session continues running independently after live stop.

    只平倉，不 pause 引擎管線 — paper/demo session 在 live stop 後繼續獨立運行。
    """
    _require_operator(actor)

    global _LIVE_USER_STOPPED, _EXECUTION_AUTHORITY_OVERRIDE, \
           _live_contraction_state, _live_monitor_task
    _LIVE_USER_STOPPED = True
    # Reset execution authority on stop — fail-closed until next explicit start
    # stop 後重置 execution_authority — 下次明確 start 前保持 fail-closed
    _EXECUTION_AUTHORITY_OVERRIDE = None
    _live_contraction_state = "normal"

    # Cancel contraction monitor task if running
    # 如果縮倉監控 task 在運行，取消它
    if _live_monitor_task is not None and not _live_monitor_task.done():
        _live_monitor_task.cancel()
    _live_monitor_task = None

    errors: list[str] = []
    rust_online = get_rust_reader().is_available()

    # Close all live positions via IPC (engine handles exchange order cancellation in live mode)
    # 通過 IPC 平倉（live 模式下引擎同時處理交易所掛單取消）
    close_result: dict = {}
    if rust_online:
        try:
            close_result = await _ipc_command("close_all_positions")
        except Exception as exc:
            errors.append(f"close_positions: {exc}")
            logger.error("IPC close_all_positions failed (live stop): %s", exc)
    else:
        close_result = {"skipped": True, "reason": "engine_offline"}

    logger.warning(
        "⚠ LIVE SESSION STOPPED — positions closed — errors=%s — actor=%s",
        errors or None, getattr(actor, "actor_id", "?"),
    )
    return _live_response({
        "message": "Live session stopped — positions closed / 實盤 session 已停止 — 倉位已平",
        "source": "rust_engine",
        "close_result": close_result,
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

    Gate: Operator role + live_reserved global mode (same as start).
    門控：Operator 角色 + live_reserved global mode（與 start 相同）。
    """
    _require_operator(actor)

    # Gate: global_mode_state must still be live_reserved
    # 門控：global_mode_state 仍需為 live_reserved
    global_mode = _get_global_mode_state()
    if "live" not in global_mode:
        raise HTTPException(
            status_code=409,
            detail=f"Live session resume blocked: global_mode={global_mode!r}. "
                   "Switch Global Mode to live_reserved first.",
        )

    # Re-grant execution_authority and restart monitor on resume
    # 恢復時重新授予 execution_authority 並重啟縮倉監控
    global _LIVE_USER_STOPPED, _EXECUTION_AUTHORITY_OVERRIDE, \
           _live_contraction_state, _live_monitor_task
    _EXECUTION_AUTHORITY_OVERRIDE = "granted"
    _LIVE_USER_STOPPED = False
    _live_contraction_state = "normal"

    # Restart contraction monitor (cancel stale task if any)
    if _live_monitor_task is not None and not _live_monitor_task.done():
        _live_monitor_task.cancel()
    _live_monitor_task = asyncio.create_task(_live_contraction_monitor())

    try:
        result = await _ipc_command("resume_paper")
        return _live_response({
            "message": "Live session resumed / 實盤 session 已恢復",
            "source": "rust_engine",
            "ipc_result": result,
            "session": {"session_state": "active", "session_id": "rust_engine_live"},
            "contraction": {"state": "normal", "warn_pct": CONTRACTION_WARN_PCT, "halt_pct": CONTRACTION_HALT_PCT},
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


@live_router.get("/fills")
async def get_live_fills(
    actor: Any = Depends(base.current_actor),
) -> dict:
    """
    GET /api/v1/live/fills
    Recent fills (executions) from Bybit account via PyO3 client.
    最近成交記錄，通過 PyO3 client 從 Bybit 帳戶讀取。
    """
    rc = _get_rust_client_safe()
    if rc is not None:
        try:
            fills = rc.get_executions("linear", limit=50)
            return _live_response({"source": "rust_engine", "list": fills, "count": len(fills)})
        except Exception as e:
            logger.warning("Rust fills fetch failed for live endpoint: %s", e)
    # Fallback: engine recent fills / 降級：引擎最近成交
    rust = get_rust_reader()
    if rust.is_available():
        try:
            recent = rust.get_recent_fills()
            return _live_response({"source": "engine_state", "list": recent or [], "count": len(recent or [])})
        except Exception:
            pass
    return _live_response({"list": [], "count": 0, "available": False})


@live_router.post("/positions/{symbol}/close")
async def post_live_close_position(
    symbol: str,
    actor: Any = Depends(base.current_actor),
) -> dict:
    """
    POST /api/v1/live/positions/{symbol}/close
    通過 IPC close_position 平掉指定 symbol 的實盤倉位。
    Close a single live position by symbol via IPC close_position command.
    """
    _require_operator(actor)
    rust = get_rust_reader()
    if not rust.is_available():
        raise HTTPException(status_code=503, detail="Rust engine not available")
    try:
        result = await _ipc_command("close_position", {"symbol": symbol.upper()})
    except Exception as exc:
        logger.error("IPC close_position failed for %s: %s", symbol, exc)
        raise HTTPException(status_code=502, detail=f"IPC error: {exc}")
    logger.warning(
        "⚠ LIVE close_position %s — actor=%s", symbol.upper(), getattr(actor, "actor_id", "?"),
    )
    return _live_response({"symbol": symbol.upper(), "closed": True, "source": "rust_engine", "ipc": result})


@live_router.post("/close-all-positions")
async def post_live_close_all_positions(
    actor: Any = Depends(base.current_actor),
) -> dict:
    """
    POST /api/v1/live/close-all-positions
    立即平掉所有實盤倉位（不停止 session，引擎繼續運行）。
    需要 Operator 角色 + 引擎在線。

    Close all live positions immediately without stopping the session.
    Requires Operator role and engine online. Engine pipeline continues running.
    """
    _require_operator(actor)
    rust_online = get_rust_reader().is_available()
    if not rust_online:
        raise HTTPException(status_code=503, detail="Rust engine offline — cannot close positions")
    try:
        result = await _ipc_command("close_all_positions")
    except Exception as exc:
        logger.error("IPC close_all_positions failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"close_all_positions IPC failed: {exc}")
    logger.warning(
        "⚠ LIVE close-all-positions (manual, session continues) — actor=%s",
        getattr(actor, "actor_id", "?"),
    )
    return _live_response({
        "message": "All live positions closed — session continues / 已平掉所有實盤倉位，session 繼續運行",
        "source": "rust_engine",
        "close_result": result,
    })


@live_router.get("/metrics")
def get_live_metrics(
    actor: Any = Depends(base.current_actor),
) -> dict:
    """
    GET /api/v1/live/metrics
    Performance metrics computed from engine state (fills, positions, PnL).
    Works for both demo-key-on-live and real-live modes — data comes from the
    Rust engine's internal paper_state which tracks all modes.

    性能指標：從引擎狀態（成交、持倉、PnL）計算。
    demo-key-on-live 和 real-live 模式均可用 — 數據來自 Rust 引擎內部狀態。
    """
    from .paper_trading_metrics import compute_full_metrics

    rust = get_rust_reader()
    rust_state = rust.get_paper_state() if rust.is_available() else None
    if rust_state is None:
        return _live_response({"available": False, "source": "engine_unavailable"})
    full = compute_full_metrics(rust_state)
    stats = rust.get_tick_stats() or {}
    full["source"] = "rust_engine"
    full["total_ticks"] = stats.get("total_ticks", 0)
    full["total_intents"] = stats.get("total_intents", 0)
    full["total_fills"] = stats.get("total_fills", 0)
    full["total_stops"] = stats.get("total_stops", 0)
    return _live_response(full)
