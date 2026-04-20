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
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from . import main_legacy as base
from .ipc_state_reader import get_rust_reader
from .live_session_governance import (
    _freeze_live_governance_auth,
    _submit_live_governance_request,
    _revoke_live_governance_auth,
)

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


def _init_execution_authority_from_trust() -> str | None:
    """
    EA-PERSIST: On startup, restore execution_authority from persisted trust state
    if and only if:
      (a) the trust state recorded execution_authority_granted=True, AND
      (b) last_auth_expires_ts_ms is still in the future (trust has not expired).
    Fail-closed: any exception returns None (not_granted).

    EA-PERSIST：啟動時從持久化信任狀態恢復 execution_authority，當且僅當：
      (a) 信任狀態記錄了 execution_authority_granted=True，且
      (b) last_auth_expires_ts_ms 仍在未來（信任未到期）。
    失敗關閉：任何異常返回 None（not_granted）。
    """
    try:
        from .earned_trust_engine import get_trust_engine
        te = get_trust_engine()
        snap = te.get_state_snapshot()
        now_ms = int(time.time() * 1000)
        expires_ms: int = snap.get("last_auth_expires_ts_ms") or 0
        if snap.get("execution_authority_granted") and expires_ms > now_ms:
            remaining_h = (expires_ms - now_ms) / 3_600_000.0
            logger.warning(
                "EA-PERSIST: execution_authority auto-restored from persisted trust state "
                "(tier=%s, expires_in=%.1fh) — live trading authority ACTIVE / "
                "EA-PERSIST：從持久化信任狀態恢復 execution_authority（tier=%s，剩餘=%.1fh）— 實盤授權有效",
                snap.get("tier_name", "T0"), remaining_h,
                snap.get("tier_name", "T0"), remaining_h,
            )
            return "granted"
    except Exception as exc:
        logger.debug("EA-PERSIST: trust restore failed (fail-closed): %s", exc)
    return None


# In-memory execution authority override (operator grant/revoke from GUI).
# EA-PERSIST: initialized from persisted trust state on startup if trust is still valid.
# Cleared on voluntary revoke / auto-halt / session-stop (persisted → not restored next restart).
# 記憶體內 execution_authority override（Operator 從 GUI 授予/撤銷）。
# EA-PERSIST：啟動時若信任狀態仍有效則從持久化狀態恢復；主動撤銷/自動停止/session 停止時清除（持久化，下次重啟不恢復）。
_EXECUTION_AUTHORITY_OVERRIDE: str | None = _init_execution_authority_from_trust()


def _set_execution_authority(value: str | None) -> None:
    """
    EA-PERSIST: Set execution_authority in memory AND persist to trust state file.
    Use this instead of direct assignment to keep the two systems in sync.
    EA-PERSIST：同步設置記憶體 execution_authority 並持久化到信任狀態文件。
    用此函數替代直接賦值，確保兩個系統保持同步。
    """
    global _EXECUTION_AUTHORITY_OVERRIDE
    _EXECUTION_AUTHORITY_OVERRIDE = value
    try:
        from .earned_trust_engine import get_trust_engine
        te = get_trust_engine()
        if value == "granted":
            te.on_authority_granted()
        else:
            te.on_authority_revoked()
    except Exception as exc:
        logger.debug("EA-PERSIST: trust sync failed (non-fatal): %s", exc)


def _get_hub():
    """Lazy import GovernanceHub singleton. / 延遲導入 GovernanceHub 單例。"""
    try:
        from .paper_trading_routes import GOV_HUB
        return GOV_HUB
    except (ImportError, AttributeError):
        return None


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
    向 Rust 引擎發送 IPC 命令；失敗時拋出 HTTPException。

    E5-P1-5: delegates the connect→call→disconnect mechanics to shared
    ``ipc_dispatch.one_shot_ipc_call`` but keeps the legacy 503 / ``"IPC
    command '<method>' failed: <exc>"`` envelope byte-for-byte so
    ``test_live_gate_fallback`` (which asserts the exact detail string)
    remains green. We opt the helper out of HTTP-reclassification with
    ``wrap_errors_as_http=False`` and re-raise the legacy shape locally.
    E5-P1-5：連線→呼叫→斷線委派給共享 helper，但 byte-for-byte 保留舊 503/
    ``"IPC command '<method>' failed: <exc>"`` 回應格式，避免破壞
    ``test_live_gate_fallback`` 對 detail 字串的精確斷言。
    """
    from .ipc_dispatch import one_shot_ipc_call  # noqa: PLC0415

    try:
        return await one_shot_ipc_call(
            method,
            params,
            timeout=5.0,
            wrap_errors_as_http=False,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — preserve legacy envelope
        raise HTTPException(
            status_code=503,
            detail=f"IPC command '{method}' failed: {exc}",
        ) from exc


def _get_rust_client_safe():
    """
    Return a PyO3 BybitClient using the live API key slot if configured, else demo.
    Live tab 始終使用 live 槽 API key（若已配置），與引擎狀態無關。

    - live slot has api_key → use live slot (environment from bybit_endpoint)
    - otherwise → "demo" (default demo slot)

    Returns None on any failure — callers must handle gracefully.
    失敗時返回 None，調用方必須處理。
    """
    try:
        import os
        from pathlib import Path
        secrets_base = os.environ.get("OPENCLAW_SECRETS_DIR") or str(
            Path.home() / "BybitOpenClaw" / "secrets" / "secret_files" / "bybit"
        )
        live_key_file = Path(secrets_base) / "live" / "api_key"
        if live_key_file.exists() and live_key_file.read_text(encoding="utf-8").strip():
            # Live slot configured — use it with correct server
            # Live 槽已配置 — 使用正確伺服器
            ep_file = Path(secrets_base) / "live" / "bybit_endpoint"
            endpoint = ep_file.read_text(encoding="utf-8").strip() if ep_file.exists() else "mainnet"
            environment = "live_demo" if endpoint == "demo" else "mainnet"
            from .bybit_rest_client import BybitClient
            return BybitClient(environment=environment)
        # No live slot — fall back to demo
        # 無 live 槽 — 回退到 demo
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
    Read current execution_authority. Prefers the persisted trust-state
    (cross-worker consistent via MW-RELOAD-1 mtime reload), falls back to
    this worker's in-memory override, then to GovernanceHub / STORE state.

    Why the trust-state goes first:
      Uvicorn runs 4 workers. /auth/renew updates only the worker that handled
      the POST. The trust-state JSON is the single file both workers write and
      watch, so reading it first guarantees that a GUI poll landing on a
      sibling worker sees the fresh "granted" within one refresh cycle.

    讀取 execution_authority。優先使用持久化信任狀態（經 MW-RELOAD-1 mtime
    重載實現跨 worker 一致），退回到本 worker 記憶體 override，再退回 hub/STORE。
    之所以優先信任狀態：renew 只打到 4 個 worker 中的 1 個，檔案是所有 worker
    共同讀寫的單一真相來源，能保證 GUI 輪詢撞上其他 worker 時也能立即看到最新。

    Returns: "granted" | "not_granted" | "unknown"
    """
    try:
        from .earned_trust_engine import get_trust_engine
        snap = get_trust_engine().get_state_snapshot()
        persisted = snap.get("execution_authority_granted")
        if persisted is not None:
            return "granted" if persisted else "not_granted"
    except Exception as exc:
        logger.debug(
            "trust-state EA read failed, falling back to in-memory/hub: %s", exc,
        )

    global _EXECUTION_AUTHORITY_OVERRIDE
    if _EXECUTION_AUTHORITY_OVERRIDE is not None:
        return _EXECUTION_AUTHORITY_OVERRIDE
    try:
        hub = _get_hub()
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


def _get_live_engine_kind() -> str:
    """
    Determine which engine the live routes should query (3E-5).
    3E world: live routes query "live" engine; fallback to "demo", then "paper".
    確定 live 路由應查詢哪個引擎。3E：優先 live → demo → paper。

    Returns: "live" | "demo" | "paper" | "unknown"
    """
    rust = get_rust_reader()
    if rust.is_engine_available("live"):
        return "live"
    if rust.is_engine_available("demo"):
        return "demo"
    if rust.is_engine_available("paper"):
        return "paper"
    # Backward compat: check primary snapshot trading_mode
    # 向後兼容：檢查主快照的 trading_mode
    if rust.is_available():
        snap = rust.get_snapshot()
        if snap:
            tm = snap.get("trading_mode", "")
            if tm in ("live", "demo", "paper"):
                return tm
    return "unknown"


# _freeze_live_governance_auth, _submit_live_governance_request,
# _revoke_live_governance_auth extracted to live_session_governance.py (FIX-08).


# ═══════════════════════════════════════════════════════════════════════════════
# Contraction monitor / 縮倉監控
# ═══════════════════════════════════════════════════════════════════════════════


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
            # Phase 4: query live mode state for contraction monitor.
            # Phase 4：縮倉監控查詢 live 模式狀態。
            state = await _ipc_command("get_paper_state", {"engine": "live"})
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
                _set_execution_authority(None)  # EA-PERSIST: auto-halt → revoke + persist

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
                    await _ipc_command("close_all_positions", {"engine": "live"})
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


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoints / 端點
# ═══════════════════════════════════════════════════════════════════════════════


@live_router.get("/session/status")
def get_live_session_status(
    actor: Any = Depends(base.current_actor),
) -> dict:
    """GET /api/v1/live/session/status — engine state + execution_authority + active_engines. / 當前 live session 狀態。"""
    rust = get_rust_reader()
    engine_available = rust.is_available()
    # 3E-5: query the live/demo engine directly via per-engine snapshot.
    # 3E-5：通過每引擎快照直接查詢 live/demo 引擎。
    engine_kind = _get_live_engine_kind()
    rust_state = rust.get_paper_state(engine=engine_kind) if engine_available and engine_kind != "unknown" else None
    # Read full engine snapshot for top-level fields like paper_paused.
    # get_paper_state() only returns the nested paper_state sub-object (balance/positions),
    # which does NOT contain paper_paused — that lives at the snapshot root.
    # 讀完整引擎快照以取得頂層欄位（如 paper_paused）。
    # get_paper_state() 僅返回 paper_state 子對象，不含頂層的 paper_paused。
    engine_snap = rust.get_engine_snapshot(engine_kind) if engine_available and engine_kind != "unknown" else None

    execution_authority = _get_execution_authority()

    if rust_state is None:
        session_state = "offline"
    elif _LIVE_USER_STOPPED:
        session_state = "stopped"
    else:
        # paper_paused is a top-level field in the engine snapshot, not inside paper_state.
        # paper_paused 在引擎快照頂層，不在 paper_state 內。
        paper_paused = (engine_snap or {}).get("paper_paused", True)
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
        "engine_kind": engine_kind,
        "active_engines": rust.get_active_engines(),
        "system_mode": _get_global_mode_state(),
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
    engine_kind is read for logging/context only — engine config controls actual routing.

    保護：Operator 角色認證是唯一門控，不設獨立 execution_authority 二次確認。
    engine_kind 僅用於日誌/上下文，引擎配置控制實際訂單路由。
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

    engine_kind = _get_live_engine_kind()

    # Auto-grant execution_authority on session start.
    # Double gate (Operator role + live_reserved global mode) is already verified above.
    # No separate manual grant step required — cleared on stop / process restart (fail-closed).
    # 啟動時自動授予 execution_authority。
    # 雙重門控（Operator 角色 + live_reserved global mode）已在上方驗證。
    # 無需另行手動 grant — stop 時 / 進程重啟後清零（fail-closed）。
    global _LIVE_USER_STOPPED, _live_contraction_state, _live_monitor_task
    _set_execution_authority("granted")  # EA-PERSIST: session start → grant + persist
    _LIVE_USER_STOPPED = False
    _live_contraction_state = "normal"

    # Submit live governance request for operator audit trail (non-blocking)
    # 提交實盤治理申請用於操作員審計留痕（非阻塞）
    actor_id = getattr(actor, "actor_id", "live_operator")
    _submit_live_governance_request(actor_id)

    # Hook: earned-trust engine — record session start / 信任引擎 session 啟動鉤子
    try:
        from .earned_trust_engine import TIER_TTL_HOURS, get_trust_engine
        _te = get_trust_engine()
        _ttl = TIER_TTL_HOURS.get(_te.get_state_snapshot()["current_tier"], 24)
        _te.on_session_start(auth_expires_ts_ms=int((time.time() + _ttl * 3600) * 1000))
    except Exception as _te_exc:
        logger.debug("EarnedTrustEngine start hook (non-fatal): %s", _te_exc)

    # Resume engine pipeline if it was paused by a previous stop
    # 如果管線因上次 stop 而暫停，恢復管線
    result: dict = {}
    try:
        result = await _ipc_command("resume_paper", {"engine": "live"})
    except Exception as exc:
        logger.warning("IPC resume_paper skipped (engine may already be running): %s", exc)

    # Start drawdown contraction monitor (cancel any stale task first)
    # 啟動回撤縮倉監控（先取消舊 task）
    if _live_monitor_task is not None and not _live_monitor_task.done():
        _live_monitor_task.cancel()
    _live_monitor_task = asyncio.create_task(_live_contraction_monitor())

    logger.warning(
        "⚠ LIVE SESSION STARTED — engine_kind=%s execution_authority=granted "
        "contraction_monitor=active warn=%.0f%% halt=%.0f%% — actor=%s",
        engine_kind, CONTRACTION_WARN_PCT, CONTRACTION_HALT_PCT,
        getattr(actor, "actor_id", "?"),
    )
    return _live_response({
        "message": "Live session started / 實盤 session 已啟動",
        "source": "rust_engine",
        "engine_kind": engine_kind,
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

    global _LIVE_USER_STOPPED, _live_contraction_state, _live_monitor_task
    _LIVE_USER_STOPPED = True
    # EA-PERSIST: revoke + persist on voluntary stop — will NOT auto-restore on next restart
    # EA-PERSIST：主動停止時撤銷並持久化 — 下次重啟不會自動恢復
    _set_execution_authority(None)
    _live_contraction_state = "normal"
    # Revoke live SM-1 authorization so governance center reflects stopped state.
    # 撤銷 live SM-1 授權，讓治理中心反映已停止狀態。
    _revoke_live_governance_auth(
        reason="live_session_stopped",
        actor_id=getattr(actor, "actor_id", "system"),
    )

    # Hook: earned-trust engine — voluntary stop resets tier to T0 / 主動停止重置信任 tier
    try:
        from .earned_trust_engine import get_trust_engine
        get_trust_engine().on_session_stop()
    except Exception as _te_exc:
        logger.debug("EarnedTrustEngine stop hook (non-fatal): %s", _te_exc)

    # Cancel contraction monitor task if running
    # 如果縮倉監控 task 在運行，取消它
    if _live_monitor_task is not None and not _live_monitor_task.done():
        _live_monitor_task.cancel()
    _live_monitor_task = None

    errors: list[str] = []
    rust_online = get_rust_reader().is_available()
    rest_fallback_used = False

    # Close all live positions via IPC (engine handles exchange order cancellation in live mode)
    # 通過 IPC 平倉（live 模式下引擎同時處理交易所掛單取消）
    close_result: dict = {}
    orphan_result: dict = {}
    if rust_online:
        try:
            close_result = await _ipc_command("close_all_positions", {"engine": "live"})
        except Exception as exc:
            if _is_live_channel_unavailable_error(exc):
                # LIVE-GATE-FALLBACK-1：Live pipeline 未授權啟動 → channel 不存在 → REST 降級清理。
                logger.warning(
                    "LIVE-GATE-FALLBACK-1 (live stop): IPC close_all channel unavailable "
                    "— REST orphan sweep will close exchange positions / 降級至 REST 清倉"
                )
                close_result = {"skipped": True, "reason": "live_pipeline_not_authorized"}
                rest_fallback_used = True
            else:
                errors.append(f"close_positions: {exc}")
                logger.error("IPC close_all_positions failed (live stop): %s", exc)
        # Orphan sweep: close exchange positions not tracked in paper_state.
        # 孤兒清掃：平掉交易所有但 paper_state 沒有的倉位。
        orphan_result = await _sweep_live_orphan_positions(errors)
        if orphan_result.get("rest_fallback"):
            rest_fallback_used = True
    else:
        close_result = orphan_result = {"skipped": True, "reason": "engine_offline"}

    logger.warning(
        "⚠ LIVE SESSION STOPPED — positions closed — rest_fallback=%s — errors=%s — actor=%s",
        rest_fallback_used, errors or None, getattr(actor, "actor_id", "?"),
    )
    return _live_response({
        "message": "Live session stopped — positions closed / 實盤 session 已停止 — 倉位已平",
        "source": "rust_engine_with_rest_fallback" if rest_fallback_used else "rust_engine",
        "rest_fallback": rest_fallback_used,
        "reason": "live_pipeline_not_authorized" if rest_fallback_used else None,
        "close_result": close_result,
        "orphan_sweep": orphan_result,
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
        result = await _ipc_command("pause_paper", {"engine": "live"})
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
    global _LIVE_USER_STOPPED, _live_contraction_state, _live_monitor_task
    _set_execution_authority("granted")  # EA-PERSIST: resume → re-grant + persist
    _LIVE_USER_STOPPED = False
    _live_contraction_state = "normal"

    # Restart contraction monitor (cancel stale task if any)
    if _live_monitor_task is not None and not _live_monitor_task.done():
        _live_monitor_task.cancel()
    _live_monitor_task = asyncio.create_task(_live_contraction_monitor())

    try:
        result = await _ipc_command("resume_paper", {"engine": "live"})
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
    _set_execution_authority("granted")  # EA-PERSIST: manual grant + persist
    actor_id = getattr(actor, "actor_id", "?")
    # Also create + approve live SM-1 authorization so governance center shows mode=live.
    # 同步創建並批准 live SM-1 授權，讓治理中心顯示 mode=live。
    _submit_live_governance_request(actor_id)
    logger.warning(
        "⚠ execution_authority GRANTED by actor=%s — live session now unlocked",
        actor_id,
    )
    return _live_response({
        "execution_authority": "granted",
        "message": "execution_authority granted — live session unlocked",
        "actor": actor_id,
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
    _set_execution_authority("not_granted")  # EA-PERSIST: manual revoke + persist
    actor_id = getattr(actor, "actor_id", "?")
    # Revoke live SM-1 authorization so governance center reflects revoked state.
    # 撤銷 live SM-1 授權，讓治理中心反映已撤銷狀態。
    _revoke_live_governance_auth(reason="execution_authority_revoked", actor_id=actor_id)
    logger.info(
        "execution_authority REVOKED by actor=%s",
        actor_id,
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
    # Attach per-engine session baseline (initial/peak/realized/fees) from
    # Rust paper_state so the GUI can display net-of-fees PnL identity
    # (equity - initial = realized - fees + unrealized). Best-effort: snapshot
    # failure does not block wallet payload.
    # 掛載 Rust paper_state 的本 session 基線（初始/峰值/已實現/手續費），
    # 讓 GUI 以 "淨利口徑" 呈現 PnL（equity - initial = realized - fees + unrealized）。
    # best-effort：快照失敗不影響 wallet payload。
    session_baseline: dict[str, Any] = {}
    try:
        live_state = get_rust_reader().get_paper_state(engine="live") or {}
        if live_state:
            session_baseline = {
                "engine_initial_balance": live_state.get("initial_balance"),
                "engine_peak_balance": live_state.get("peak_balance"),
                "engine_current_balance": live_state.get("balance"),
                "engine_realized_pnl": live_state.get("total_realized_pnl"),
                "engine_total_fees": live_state.get("total_fees"),
            }
    except Exception:
        pass

    rc = _get_rust_client_safe()
    if rc is not None:
        try:
            wallet = rc.refresh_balance()
            return _live_response({"source": "rust_engine", **wallet, **session_baseline})
        except Exception as e:
            logger.warning("Rust balance fetch failed for live endpoint: %s", e)
    # Fallback: engine internal state / 降級：引擎內部狀態
    try:
        state = await _ipc_command("get_paper_state", {"engine": "live"})
    except HTTPException:
        return _live_response({"available": False, "source": "engine_unavailable"})
    sync_bal = state.get("bybit_sync_balance")
    return _live_response({
        "balance": sync_bal if sync_bal is not None else state.get("balance"),
        "peak_balance": state.get("peak_balance"),
        "bybit_sync_balance": sync_bal,
        "engine_balance": state.get("balance"),
        "source": "bybit_sync" if sync_bal is not None else "engine_internal",
        **session_baseline,
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
            from .strategy_ai_routes import _attach_owner_strategy  # noqa: PLC0415
            positions = _attach_owner_strategy(positions, engine="live")
            return _live_response({
                "source": "rust_engine",
                "positions": positions,
                "list": positions,
                "count": len(positions),
            })
        except Exception as e:
            logger.warning("Rust positions fetch failed for live endpoint: %s", e)
    # Fallback: engine internal state / 降級：引擎內部狀態
    # paper_state positions already carry owner_strategy natively; no enrichment needed.
    # paper_state 倉位原生帶 owner_strategy，無需額外 enrichment。
    try:
        state = await _ipc_command("get_paper_state", {"engine": "live"})
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
        state = await _ipc_command("get_paper_state", {"engine": "live"})
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
    DB primary (realized_pnl) → Bybit API fallback → engine snapshot fallback.
    DB 為主（帶 realized_pnl）→ Bybit API 備援 → 引擎快照備援。
    """
    # DB path — engine-calculated realized_pnl, same pattern as demo/paper.
    # DB 路徑 — 引擎計算的 realized_pnl，與 demo/paper 相同模式。
    try:
        from . import db_pool
        conn = db_pool.get_conn()
    except Exception:
        conn = None
    if conn is not None:
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT ts, symbol, side, qty, price, fee, realized_pnl, strategy_name "
                "FROM trading.fills WHERE engine_mode IN (%s, %s) ORDER BY ts DESC LIMIT %s",
                ("live", "live_demo", 50),
            )
            rows = cur.fetchall()
            if rows:
                fills = []
                for ts, symbol, side, qty, price, fee, rpnl, strategy in rows:
                    ts_ms = int(ts.timestamp() * 1000) if ts is not None else 0
                    sym = symbol or ""
                    cat = "inverse" if sym.endswith("USD") and not sym.endswith("USDT") else "linear"
                    fills.append({
                        "execTime": str(ts_ms),
                        "symbol": sym,
                        "side": side or "",
                        "execQty": float(qty) if qty is not None else 0.0,
                        "execPrice": float(price) if price is not None else 0.0,
                        "execFee": float(fee) if fee is not None else 0.0,
                        "closedPnl": float(rpnl) if rpnl is not None else 0.0,
                        "strategy": strategy or "",
                        "category": cat,
                    })
                return _live_response({"list": fills, "count": len(fills), "source": "pg_trading_fills"})
        except Exception as e:
            logger.warning("PG live fills query failed, falling back to Bybit API: %s", e)
        finally:
            try:
                db_pool.put_conn(conn)
            except Exception:
                pass
    # Bybit API via PyO3 (closedPnl from exchange).
    # Bybit API（closedPnl 來自交易所）。
    rc = _get_rust_client_safe()
    if rc is not None:
        try:
            from .strategy_ai_routes import _normalize_execution
            fills = [_normalize_execution(f) for f in rc.get_executions("linear", limit=50)]
            return _live_response({"source": "rust_engine", "list": fills, "count": len(fills)})
        except Exception as e:
            logger.warning("Rust fills fetch failed for live endpoint: %s", e)
    # Fallback: engine recent fills (3E-ARCH snapshot, now carries realized_pnl).
    # 降級：引擎快照 recent_fills（現帶 realized_pnl）。
    rust = get_rust_reader()
    if rust.is_engine_available("live"):
        try:
            recent = rust.get_recent_fills(mode="live")
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
    通過 IPC close_position 平掉指定 symbol 的倉位。
    執行路徑完全在 Rust 引擎內：
      1. Python 從 Bybit REST 查詢持倉（只讀），取得 is_long / qty 作為 hints
      2. IPC 帶 hints 傳給 Rust
      3. Rust 引擎直接 dispatch reduce_only 市價單至 Bybit（不經 Python 下單）
      4. paper_state 有倉 → 走既有路徑；無倉 → 用 hints 平孤兒倉位

    Close a single Live position by symbol. All trading execution happens inside Rust:
    Python only does a read-only REST lookup to supply is_long/qty hints.
    Rust dispatches the reduce_only market order directly.
    """
    _require_operator(actor)
    sym = symbol.upper()

    # Step 1: read-only lookup of exchange position to build hints for Rust.
    # Python 只查倉位資料（只讀），供 Rust 平孤兒倉位時使用。
    hint_is_long: bool | None = None
    hint_qty: float | None = None
    rc = _get_rust_client_safe()
    if rc is not None:
        try:
            positions = rc.get_positions("linear")
            for p in positions:
                if p.get("symbol") == sym:
                    size = float(p.get("size") or p.get("qty") or 0)
                    if size > 0:
                        hint_is_long = p.get("side") == "Buy"
                        hint_qty = size
                    break
        except Exception as exc:
            logger.warning("live close: position hint lookup failed for %s: %s", sym, exc)

    # Step 2: send IPC — Rust handles the actual close order.
    # 發 IPC — Rust 引擎執行平倉，Python 不介入下單。
    ipc_params: dict = {"symbol": sym, "engine": "live"}
    if hint_is_long is not None:
        ipc_params["is_long"] = hint_is_long
    if hint_qty is not None and hint_qty > 0:
        ipc_params["qty"] = hint_qty

    rest_fallback_used = False
    try:
        result = await _ipc_command("close_position", ipc_params)
    except Exception as exc:
        if _is_live_channel_unavailable_error(exc) and rc is not None \
                and hint_qty is not None and hint_qty > 0 and hint_is_long is not None:
            # LIVE-GATE-FALLBACK-1：Live pipeline 未授權 → REST reduce_only 降級。
            # 需要 hints 俱全才能降級（qty/is_long 缺一不可，避免誤下方向）。
            try:
                result = _rest_close_position_reduce_only(rc, sym, hint_qty, hint_is_long)
                rest_fallback_used = True
                logger.warning(
                    "LIVE-GATE-FALLBACK-1: close_position %s qty=%.4f is_long=%s "
                    "(REST fallback — live pipeline not authorized)",
                    sym, hint_qty, hint_is_long,
                )
            except Exception as rest_exc:
                logger.error(
                    "LIVE-GATE-FALLBACK-1 REST fallback failed for %s: %s", sym, rest_exc,
                )
                raise HTTPException(status_code=502, detail=f"REST fallback error: {rest_exc}")
        else:
            logger.error("IPC close_position failed for %s: %s", sym, exc)
            raise HTTPException(status_code=502, detail=f"IPC error: {exc}")

    # If no exchange position AND paper IPC also found nothing, return 404.
    # 交易所和紙盤都沒倉，回 404（避免謊報 closed=True）。
    if hint_qty is None or hint_qty <= 0:
        raise HTTPException(
            status_code=404,
            detail=f"No position found for {sym} (neither paper state nor exchange) / 倉位不存在",
        )

    logger.warning(
        "⚠ close_position %s hint_is_long=%s hint_qty=%s rest_fallback=%s — actor=%s",
        sym, hint_is_long, hint_qty, rest_fallback_used, getattr(actor, "actor_id", "?"),
    )
    return _live_response({
        "symbol": sym,
        "closed": True,
        "source": "rust_engine_with_rest_fallback" if rest_fallback_used else "rust_engine",
        "rest_fallback": rest_fallback_used,
        "reason": "live_pipeline_not_authorized" if rest_fallback_used else None,
        "ipc": result,
    })


# ── LIVE-GATE-FALLBACK-1 ───────────────────────────────────────────────────
# When LIVE-GATE-BINDING-1 refuses the Live pipeline (missing/invalid
# authorization.json), Rust never registers `channels.live` → every
# close_position/close_all_positions IPC returns this exact error string.
# We detect it and fall back to a REST-only reduce_only close, so operators
# can still close existing live positions when authorization is unavailable.
# Rationale: root principle #6「失敗默認收縮」— closing must stay possible.
#
# LIVE-GATE-FALLBACK-1：當 Live pipeline 因授權缺失被 LIVE-GATE-BINDING-1 拒絕
# 啟動時，Rust 不會註冊 `channels.live`，所有指向 live 的平倉 IPC 都返回此字串。
# 偵測到時降級走 REST reduce_only 市價單，不經 IPC。
# 依據：根原則 #6「失敗默認收縮」— 授權失效時仍必須能平現有倉位。
_CHANNEL_NOT_CONFIGURED_MARKER = "paper command channel not configured"


def _is_live_channel_unavailable_error(exc: BaseException) -> bool:
    """True iff IPC error indicates the Live command channel was never registered."""
    return _CHANNEL_NOT_CONFIGURED_MARKER in str(exc)


def _rest_close_position_reduce_only(
    rc: Any, symbol: str, qty: float, is_long: bool
) -> dict:
    """
    LIVE-GATE-FALLBACK-1: REST-only reduce_only close path.

    Called when the Live IPC channel is unavailable (Live pipeline refused
    to spawn).  Issues a reduce_only Market order directly via BybitClient —
    bypassing the Rust engine entirely.  Only used for closing; never opens.

    LIVE-GATE-FALLBACK-1：REST-only reduce_only 平倉路徑。
    Live IPC channel 不可用時調用（Live pipeline 拒絕啟動）。
    直接透過 BybitClient 發 reduce_only 市價單，完全繞過引擎。只用於平倉。

    Raises on Bybit REST failure; caller must catch + record.
    REST 失敗時拋異常，由 caller 捕獲並記錄。
    """
    # Bybit: long → Sell to close; short → Buy to close.
    side = "Sell" if is_long else "Buy"
    # Fresh BybitClient starts with an empty InstrumentInfoCache — round_qty
    # returns None → raw qty → Bybit rejects with retCode=10001. Warm the
    # cache once per client before the first rounding attempt.
    # 新建的 BybitClient 合約緩存是空的，round_qty 回 None → 送 raw qty →
    # Bybit 用 retCode=10001 拒單。首次取整前先把緩存熱起來。
    try:
        if hasattr(rc, "instrument_count") and rc.instrument_count() == 0:
            rc.refresh_instruments("linear")
    except Exception as ri_exc:
        logger.warning(
            "LIVE-GATE-FALLBACK-1: refresh_instruments failed for %s — "
            "proceeding with raw qty / 刷新合約規格失敗，改送 raw qty: %s",
            symbol, ri_exc,
        )
    # Align qty to instrument step size — else Bybit returns retCode=10001.
    # 對齊 instrument step size，否則 Bybit 返回 retCode=10001。
    qty_aligned = qty
    try:
        qty_aligned = float(rc.round_qty(symbol, qty))
    except Exception as rq_exc:
        logger.debug("round_qty failed for %s — using raw qty: %s", symbol, rq_exc)
    result = rc.place_order(
        symbol=symbol,
        side=side,
        order_type="Market",
        qty=qty_aligned,
        category="linear",
        reduce_only=True,
    )
    return {
        "rest_closed": True,
        "symbol": symbol,
        "side": side,
        "qty": qty_aligned,
        "order_id": result.get("order_id") if isinstance(result, dict) else None,
        "order_link_id": result.get("order_link_id") if isinstance(result, dict) else None,
    }


async def _sweep_live_orphan_positions(errors: list[str]) -> dict:
    """Close any exchange Live positions not tracked in paper_state (orphan sweep).

    Mirrors _sweep_demo_orphan_positions in strategy_ai_routes but uses the live
    API key slot.  IPC close_all only iterates paper_state — positions that exist
    on the exchange but not in paper_state are silently skipped.  This sweep
    queries the exchange and issues a close_position IPC for each open position.

    LIVE-GATE-FALLBACK-1: if the IPC error indicates the Live command channel
    was never registered (authorization gate refused pipeline spawn), fall back
    to a REST-only reduce_only Market order.  Any other IPC error is recorded
    as-is (no REST fallback — we must not mask real problems).

    IPC close_all 只遍歷 paper_state，交易所有但 paper_state 沒有的「孤兒倉位」
    會被跳過。本函數通過 Live API key 查詢交易所持倉，逐一發 close_position IPC。

    LIVE-GATE-FALLBACK-1：若 IPC 錯誤表示 Live 命令通道從未註冊（授權 gate 拒絕
    啟動管線），降級到 REST-only reduce_only 市價單。其他 IPC 錯誤原樣記錄，
    不降級（避免遮蔽真實問題）。
    """
    rc = _get_rust_client_safe()
    if rc is None:
        return {"skipped": True, "reason": "rust_client_unavailable"}

    positions: list = []
    try:
        positions = rc.get_positions("linear") or []
    except Exception as exc:
        logger.warning("Live orphan sweep: get_positions failed: %s", exc)
        errors.append(f"orphan_sweep_query: {exc}")
        return {"skipped": True, "reason": str(exc)}

    open_positions = [p for p in positions if float(p.get("size") or p.get("qty") or 0) > 0]
    if not open_positions:
        return {"swept": 0}

    swept_ipc = 0
    swept_rest = 0
    for p in open_positions:
        sym = p.get("symbol", "")
        size = float(p.get("size") or p.get("qty") or 0)
        if not sym or size <= 0:
            continue
        is_long = p.get("side") == "Buy"
        ipc_params: dict = {
            "symbol": sym,
            "engine": "live",
            "is_long": is_long,
            "qty": size,
        }
        try:
            await _ipc_command("close_position", ipc_params)
            swept_ipc += 1
            logger.warning(
                "Live orphan sweep: close_position %s qty=%.4f is_long=%s (via IPC)",
                sym, size, is_long,
            )
        except Exception as exc:
            # LIVE-GATE-FALLBACK-1：Live pipeline 未授權啟動 → channel 不存在 → 降級 REST。
            if _is_live_channel_unavailable_error(exc):
                try:
                    _rest_close_position_reduce_only(rc, sym, size, is_long)
                    swept_rest += 1
                    logger.warning(
                        "Live orphan sweep: close_position %s qty=%.4f is_long=%s "
                        "(REST fallback — live pipeline not authorized) / REST 降級平倉",
                        sym, size, is_long,
                    )
                except Exception as rest_exc:
                    logger.warning(
                        "Live orphan sweep: REST fallback %s failed: %s", sym, rest_exc,
                    )
                    errors.append(f"orphan_{sym}_rest: {rest_exc}")
            else:
                logger.warning("Live orphan sweep: close_position %s failed: %s", sym, exc)
                errors.append(f"orphan_{sym}: {exc}")

    result: dict = {"swept": swept_ipc + swept_rest, "found": len(open_positions)}
    if swept_rest > 0:
        result["rest_fallback"] = True
        result["swept_via_ipc"] = swept_ipc
        result["swept_via_rest"] = swept_rest
    return result


@live_router.post("/close-all-positions")
async def post_live_close_all_positions(
    actor: Any = Depends(base.current_actor),
) -> dict:
    """
    POST /api/v1/live/close-all-positions
    通過 IPC close_all_positions 立即平掉所有倉位（不停止 session，引擎繼續運行）。
    Rust 引擎依 pipeline_kind 分派：Demo/Live → reduce_only 市價單；Paper → 清 paper_state。
    需要 Operator 角色。

    Close all positions immediately without stopping the session via IPC close_all_positions.
    Rust engine branches by pipeline_kind: Demo/Live → reduce_only market orders; Paper → paper_state.
    Requires Operator role.
    """
    _require_operator(actor)
    errors: list[str] = []
    rest_fallback_used = False
    try:
        result = await _ipc_command("close_all_positions", {"engine": "live"})
    except Exception as exc:
        if _is_live_channel_unavailable_error(exc):
            # LIVE-GATE-FALLBACK-1：Live pipeline 未授權啟動，IPC channel 不存在。
            # paper_state live 槽也一定是空的（pipeline 沒跑），所以直接靠孤兒清掃 REST 降級平倉。
            logger.warning(
                "LIVE-GATE-FALLBACK-1: IPC close_all_positions channel unavailable "
                "(live pipeline not authorized) — falling back to REST orphan sweep / "
                "Live 命令通道不可用（管線未授權）— 降級至 REST 孤兒清掃"
            )
            result = {"skipped": True, "reason": "live_pipeline_not_authorized"}
            rest_fallback_used = True
        else:
            logger.error("IPC close_all_positions failed: %s", exc)
            errors.append(f"ipc_close_all: {exc}")
            result = {"error": str(exc)}
    # Orphan sweep: close exchange positions not tracked in paper_state.
    # IPC close_all only iterates paper_state — orphan positions are silently skipped.
    # 孤兒清掃：IPC close_all 只遍歷 paper_state，交易所孤兒倉位會被跳過，此處補掃。
    orphan_result = await _sweep_live_orphan_positions(errors)
    if orphan_result.get("rest_fallback"):
        rest_fallback_used = True
    logger.warning(
        "⚠ close-all-positions (manual, session continues, rest_fallback=%s) — actor=%s",
        rest_fallback_used, getattr(actor, "actor_id", "?"),
    )
    return _live_response({
        "message": "All positions closed — session continues / 已平掉所有倉位，session 繼續運行",
        "source": "rust_engine_with_rest_fallback" if rest_fallback_used else "rust_engine",
        "rest_fallback": rest_fallback_used,
        "reason": "live_pipeline_not_authorized" if rest_fallback_used else None,
        "close_result": result,
        "orphan_sweep": orphan_result,
        "errors": errors if errors else None,
    })


@live_router.get("/metrics")
def get_live_metrics(
    actor: Any = Depends(base.current_actor),
) -> dict:
    """GET /api/v1/live/metrics — performance metrics from Rust engine (fills/positions/PnL). / 性能指標。"""
    from .paper_trading_metrics import compute_full_metrics

    rust = get_rust_reader()
    # 3E-5: query per-engine snapshot for live metrics.
    # 3E-5：查詢每引擎快照用於 live 指標。
    engine_kind = _get_live_engine_kind()
    rust_state = rust.get_paper_state(engine=engine_kind) if rust.is_available() and engine_kind != "unknown" else None
    if rust_state is None:
        return _live_response({"available": False, "source": "engine_unavailable"})
    full = compute_full_metrics(rust_state, engine_mode=engine_kind)
    # Read per-engine tick stats / 讀取每引擎 tick 統計
    engine_snap = rust.get_engine_snapshot(engine_kind) if engine_kind != "unknown" else None
    stats = (engine_snap or {}).get("stats") or {}
    full["source"] = "rust_engine"
    full["total_ticks"] = stats.get("total_ticks", 0)
    full["total_intents"] = stats.get("total_intents", 0)
    full["total_fills"] = stats.get("total_fills", 0)
    full["total_stops"] = stats.get("total_stops", 0)
    return _live_response(full)


def _grant_execution_authority_internal() -> None:
    """Re-grant execution_authority (called by live_trust_routes after Renew). / 信任續期後重新授予 execution_authority。"""
    if _EXECUTION_AUTHORITY_OVERRIDE != "granted":
        _set_execution_authority("granted")  # EA-PERSIST: trust renewal re-grant + persist
        logger.info("execution_authority re-granted via earned-trust renewal / 信任續期重新授予")
