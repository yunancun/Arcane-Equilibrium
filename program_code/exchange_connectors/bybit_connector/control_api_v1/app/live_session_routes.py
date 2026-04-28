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

REFACTOR_NOTE (G5-02, 2026-04-24):
  本模組原為 1449 行單檔，超 §九 1200 硬上限。G5-02 將 14 個 endpoint handler
  拆至 2 個 sibling 純結構搬遷（0 邏輯變更）：
  - ``live_session_endpoints.py``       — 7 個 session 生命週期 + execution_authority
  - ``live_session_account_routes.py``  — 7 個 account data + close handlers
  本檔保留所有 state / globals / 共用 helpers / LIVE-BOUNDARY-FREEZE helpers /
  router instance / contraction monitor，並在底部 import sibling 觸發
  ``@live_router.<verb>`` 裝飾器把 routes 掛回同一個 router。

  外部 import path 不變：
  - ``from app.live_session_routes import live_router``        ← main.py
  - ``from app import live_session_routes as lsr``            ← test_live_gate_fallback.py
  - ``from .live_session_routes import _grant_execution_authority_internal``  ← live_trust_routes.py
  - ``from .live_session_routes import _live_contraction_state``               ← live_trust_routes.py
"""

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from . import main_legacy as base
from .ipc_state_reader import get_rust_reader
from .live_session_governance import (
    _freeze_live_governance_auth,
    _revoke_live_governance_auth,
    _submit_live_governance_request,
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


def _resolve_live_endpoint_label() -> str:
    """
    F5/A1 — Resolve which endpoint Live slot is bound to (without spawning a client).
    F5/A1 — 解析 Live 槽綁定的 endpoint 標籤（不建立客戶端）。

    Returns one of:
      - "mainnet"     : Live slot has api_key + bybit_endpoint = mainnet (default)
      - "live_demo"   : Live slot has api_key + bybit_endpoint = demo (LiveDemo)
      - "unconfigured": Live slot has no api_key (fallback to demo slot client elsewhere)

    本 helper 純讀檔判斷 Live 槽身份，不觸發 BybitClient 建構，提供給：
    1. tab-live 前端做 visual differentiation（mainnet 紫紅 / live_demo 橙 / unconfigured 灰）
    2. account routes 在「engine_kind != 'live' 且 endpoint == unconfigured」時回
       phantom-view error envelope，避免 demo data 偽裝 live。

    與 ``_get_rust_client_safe()`` 的關係：
      ``_get_rust_client_safe()`` 內部隱含這個邏輯但沒輸出標籤；本 helper 把它顯式化
      以供 ``_live_response()`` 注入 actual_endpoint 欄位。
    """
    try:
        # F5-RETURN (2026-04-26): imports moved to module top per E2 [R1-6] /
        # F5-RETURN：依 E2 [R1-6] 規則將 import 移至模組頂層
        secrets_base = os.environ.get("OPENCLAW_SECRETS_DIR") or str(
            Path.home() / "BybitOpenClaw" / "secrets" / "secret_files" / "bybit"
        )
        live_key_file = Path(secrets_base) / "live" / "api_key"
        if live_key_file.exists() and live_key_file.read_text(encoding="utf-8").strip():
            ep_file = Path(secrets_base) / "live" / "bybit_endpoint"
            endpoint = (
                ep_file.read_text(encoding="utf-8").strip() if ep_file.exists() else "mainnet"
            )
            return "live_demo" if endpoint == "demo" else "mainnet"
        return "unconfigured"
    except Exception:
        return "unconfigured"


def _get_rust_client_safe():
    """
    Return an httpx BybitClient using the live API key slot if configured, else demo.
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

    F5/A1 — Inject ``actual_engine_kind`` + ``actual_endpoint`` so the frontend
    can decide between four Live visual modes:
      1. engine_kind != 'live'        → integrity-fail view (warning swap)
      2. endpoint == 'mainnet'        → Mainnet REAL-FUNDS purple/red theme
      3. endpoint == 'live_demo'      → LiveDemo orange/silver theme
      4. endpoint == 'unconfigured'   → demo-fallback warning (silver/gray)
    Callers may override these by passing ``actual_engine_kind`` / ``actual_endpoint``
    in ``data``; absent → resolved from helpers via setdefault.

    F5/A1 — 注入 actual_engine_kind + actual_endpoint，讓前端能區分上述 4 種模式，
    避免 LiveDemo / unconfigured 被誤渲染為 Mainnet「真實資金」紫色面板。
    """
    payload: dict[str, Any] = {
        "is_simulated": False,
        "data_category": "live_exchange",
    }
    payload.update(data)
    # Only auto-resolve if caller didn't supply (cheap default; helpers are pure read)
    # 僅在 caller 未自行傳入時自動解析（helpers 純讀，成本低）
    payload.setdefault("actual_engine_kind", _get_live_engine_kind())
    payload.setdefault("actual_endpoint", _resolve_live_endpoint_label())
    return {"data": payload}


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


# ── LIVE-BOUNDARY-FREEZE-1 ──────────────────────────────────────────────────
# Direct Python REST live close fallback is disabled. When LiveAuthWatcher has
# no live command channel, the operator must restore the signed live_reserved
# control plane and close through Rust IPC. This keeps every live mutation on
# one auditable write boundary.
#
# LIVE-BOUNDARY-FREEZE-1：禁用 Python REST live 降級平倉。Live 命令通道不存在時，
# operator 必須先恢復 signed live_reserved 控制面，再經 Rust IPC 平倉。
_CHANNEL_NOT_CONFIGURED_MARKER = "paper command channel not configured"
_LIVE_REST_FALLBACK_DISABLED_DETAIL = (
    "Direct REST live close fallback is disabled. Renew signed Live authorization "
    "with Global Mode exactly live_reserved, then close through the Rust live pipeline."
)


def _is_live_channel_unavailable_error(exc: BaseException) -> bool:
    """True iff IPC error indicates the Live command channel was never registered."""
    return _CHANNEL_NOT_CONFIGURED_MARKER in str(exc)


def _rest_close_position_reduce_only(
    rc: Any, symbol: str, qty: float, is_long: bool
) -> dict:
    """
    Deprecated Batch-A boundary guard.

    This function used to place reduce-only market orders directly through
    BybitClient when the Live IPC channel was unavailable. Keeping that path
    would allow Python to mutate live exchange state outside the signed Rust
    pipeline, so the helper now fails closed for all callers.
    """
    raise HTTPException(status_code=409, detail=_LIVE_REST_FALLBACK_DISABLED_DETAIL)


async def _sweep_live_orphan_positions(errors: list[str]) -> dict:
    """Close any exchange Live positions not tracked in paper_state (orphan sweep).

    Mirrors _sweep_demo_orphan_positions in strategy_ai_routes but uses the live
    API key slot.  IPC close_all only iterates paper_state — positions that exist
    on the exchange but not in paper_state are silently skipped.  This sweep
    queries the exchange and issues a close_position IPC for each open position.

    If the IPC error indicates the Live command channel was never registered,
    record the blocked close. Do not fall back to Python REST writes.

    IPC close_all 只遍歷 paper_state，交易所有但 paper_state 沒有的「孤兒倉位」
    會被跳過。本函數通過 Live API key 查詢交易所持倉，逐一發 close_position IPC。

    Live 命令通道不存在時只記錄阻斷，不降級到 Python REST 寫入。
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
    blocked_no_channel = 0
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
            if _is_live_channel_unavailable_error(exc):
                blocked_no_channel += 1
                logger.error(
                    "Live orphan sweep BLOCKED: close_position %s qty=%.4f is_long=%s "
                    "has no live IPC channel; REST fallback disabled",
                    sym,
                    size,
                    is_long,
                )
                errors.append(f"orphan_{sym}_live_channel_unavailable")
            else:
                logger.warning("Live orphan sweep: close_position %s failed: %s", sym, exc)
                errors.append(f"orphan_{sym}: {exc}")

    result: dict = {"swept": swept_ipc, "found": len(open_positions)}
    if blocked_no_channel > 0:
        result["blocked_no_live_channel"] = blocked_no_channel
        result["rest_fallback_disabled"] = True
        result["swept_via_ipc"] = swept_ipc
    return result


def _grant_execution_authority_internal() -> None:
    """Re-grant execution_authority (called by live_trust_routes after Renew). / 信任續期後重新授予 execution_authority。"""
    if _EXECUTION_AUTHORITY_OVERRIDE != "granted":
        _set_execution_authority("granted")  # EA-PERSIST: trust renewal re-grant + persist
        logger.info("execution_authority re-granted via earned-trust renewal / 信任續期重新授予")


# ═══════════════════════════════════════════════════════════════════════════════
# Sibling endpoint registration (G5-02 split)
# Sibling 端點註冊（G5-02 拆分）
#
# Side-effect imports: each sibling module's @live_router.<verb> decorators
# fire on import, attaching their handlers to ``live_router`` defined above.
# Imports are placed at the bottom (after all helpers + state are defined)
# so siblings can ``from . import live_session_routes as core`` without a
# circular-import surprise — by the time this runs, the module body has
# fully executed and all of ``core.<name>`` is bound.
#
# 這兩個 import 有副作用：sibling 模組頂層的 @live_router.<verb> 裝飾器會
# 在 import 時掛 handler 到上方定義的 ``live_router``。位置必須在所有
# helpers/state 定義完之後，sibling 才能順利 ``from . import
# live_session_routes as core`` 不撞循環導入 — 此處執行時，module body
# 已完整執行，所有 ``core.<name>`` 已綁定。
# ═══════════════════════════════════════════════════════════════════════════════

from . import live_session_account_routes as _live_session_account_routes  # noqa: E402, F401
from . import live_session_endpoints as _live_session_endpoints  # noqa: E402, F401
