from __future__ import annotations

"""
Live Session Endpoints — session lifecycle + execution_authority handlers
實盤 Session 端點 — session 生命週期 + execution_authority 處理器

MODULE_NOTE (中文):
  本檔由 G5-02 從 ``live_session_routes.py`` 拆出（§九 1200 行硬上限）。
  純結構搬遷 — 0 邏輯變更。所有 handler 行為、路由路徑、Depends 守衛、
  global 狀態語義 byte-for-byte 一致。

  端點：
  - GET  /api/v1/live/session/status            — 當前狀態
  - POST /api/v1/live/session/start             — 啟動 (Operator + live_reserved gate)
  - POST /api/v1/live/session/stop              — 平倉 + 取消授權
  - POST /api/v1/live/session/pause             — 暫停下單
  - POST /api/v1/live/session/resume            — 恢復下單
  - POST /api/v1/live/execution-authority/grant — 顯式授予
  - POST /api/v1/live/execution-authority/revoke — 顯式撤銷

  關鍵設計（保留 monkey-patch 行為）：
    所有對 ``live_session_routes`` 模組屬性的引用走 ``core.<name>``，不走
    ``from .live_session_routes import <name>``。原因：tests/test_live_gate_fallback.py
    用 ``monkeypatch.setattr(lsr, "_get_rust_client_safe", ...)`` 之類重綁定
    模組屬性；如果 sibling 用 from-import 捕獲早期函數引用，monkeypatch 失效。

MODULE_NOTE (English):
  Split out of ``live_session_routes.py`` by G5-02 (§九 1200-line hard cap).
  Pure structural move — zero logic changes. Handlers, routes, Depends,
  global-state semantics are byte-for-byte identical.

  Module-attribute lookup matters: all references to ``live_session_routes``
  internals go via ``core.<name>`` so test monkeypatches still bind correctly.
"""

import asyncio
import logging
import time
from typing import Any

from fastapi import Depends, HTTPException

from . import live_session_routes as core
from . import main_legacy as base
from .ipc_state_reader import get_rust_reader
from .live_session_governance import (
    _revoke_live_governance_auth,
    _submit_live_governance_request,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Session lifecycle endpoints / Session 生命週期端點
# ═══════════════════════════════════════════════════════════════════════════════


@core.live_router.get("/session/status")
def get_live_session_status(
    actor: Any = Depends(base.current_actor),
) -> dict:
    """GET /api/v1/live/session/status — engine state + execution_authority + active_engines. / 當前 live session 狀態。"""
    rust = get_rust_reader()
    engine_available = rust.is_available()
    # 3E-5: query the live/demo engine directly via per-engine snapshot.
    # 3E-5：通過每引擎快照直接查詢 live/demo 引擎。
    engine_kind = core._get_live_engine_kind()
    rust_state = rust.get_paper_state(engine=engine_kind) if engine_available and engine_kind != "unknown" else None
    # Read full engine snapshot for top-level fields like paper_paused.
    # get_paper_state() only returns the nested paper_state sub-object (balance/positions),
    # which does NOT contain paper_paused — that lives at the snapshot root.
    # 讀完整引擎快照以取得頂層欄位（如 paper_paused）。
    # get_paper_state() 僅返回 paper_state 子對象，不含頂層的 paper_paused。
    engine_snap = rust.get_engine_snapshot(engine_kind) if engine_available and engine_kind != "unknown" else None

    execution_authority = core._get_execution_authority()

    if rust_state is None:
        session_state = "offline"
    elif core._LIVE_USER_STOPPED:
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

    return core._live_response({
        "engine_available": engine_available,
        "execution_authority": execution_authority,
        "engine_kind": engine_kind,
        "active_engines": rust.get_active_engines(),
        "system_mode": core._get_global_mode_state(),
        "session": {
            "session_state": session_state,
            "session_id": "rust_engine_live",
        },
        "rust_state": rust_state,
        "contraction": {
            "state": core._live_contraction_state,
            "warn_pct": core.CONTRACTION_WARN_PCT,
            "halt_pct": core.CONTRACTION_HALT_PCT,
            **drawdown_info,
        },
    })


@core.live_router.post("/session/start")
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
    core._require_operator(actor)

    # Gate: global_mode_state must include 'live' (i.e. live_reserved or live_enabled)
    # 門控：global_mode_state 必須含 'live'（即 live_reserved 或 live_enabled）
    global_mode = core._get_global_mode_state()
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

    engine_kind = core._get_live_engine_kind()

    # Auto-grant execution_authority on session start.
    # Double gate (Operator role + live_reserved global mode) is already verified above.
    # No separate manual grant step required — cleared on stop / process restart (fail-closed).
    # 啟動時自動授予 execution_authority。
    # 雙重門控（Operator 角色 + live_reserved global mode）已在上方驗證。
    # 無需另行手動 grant — stop 時 / 進程重啟後清零（fail-closed）。
    core._set_execution_authority("granted")  # EA-PERSIST: session start → grant + persist
    core._LIVE_USER_STOPPED = False
    core._live_contraction_state = "normal"

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
        result = await core._ipc_command("resume_paper", {"engine": "live"})
    except Exception as exc:
        logger.warning("IPC resume_paper skipped (engine may already be running): %s", exc)

    # Start drawdown contraction monitor (cancel any stale task first)
    # 啟動回撤縮倉監控（先取消舊 task）
    if core._live_monitor_task is not None and not core._live_monitor_task.done():
        core._live_monitor_task.cancel()
    core._live_monitor_task = asyncio.create_task(core._live_contraction_monitor())

    logger.warning(
        "⚠ LIVE SESSION STARTED — engine_kind=%s execution_authority=granted "
        "contraction_monitor=active warn=%.0f%% halt=%.0f%% — actor=%s",
        engine_kind, core.CONTRACTION_WARN_PCT, core.CONTRACTION_HALT_PCT,
        getattr(actor, "actor_id", "?"),
    )
    return core._live_response({
        "message": "Live session started / 實盤 session 已啟動",
        "source": "rust_engine",
        "engine_kind": engine_kind,
        "authority": "granted",
        "ipc_result": result,
        "session": {"session_state": "active", "session_id": "rust_engine_live"},
        "contraction": {
            "state": "normal",
            "warn_pct": core.CONTRACTION_WARN_PCT,
            "halt_pct": core.CONTRACTION_HALT_PCT,
        },
    })


@core.live_router.post("/session/stop")
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
    core._require_operator(actor)

    core._LIVE_USER_STOPPED = True
    # EA-PERSIST: revoke + persist on voluntary stop — will NOT auto-restore on next restart
    # EA-PERSIST：主動停止時撤銷並持久化 — 下次重啟不會自動恢復
    core._set_execution_authority(None)
    core._live_contraction_state = "normal"
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
    if core._live_monitor_task is not None and not core._live_monitor_task.done():
        core._live_monitor_task.cancel()
    core._live_monitor_task = None

    errors: list[str] = []
    rust_online = get_rust_reader().is_available()
    rest_fallback_used = False

    # Close all live positions via IPC (engine handles exchange order cancellation in live mode)
    # 通過 IPC 平倉（live 模式下引擎同時處理交易所掛單取消）
    close_result: dict = {}
    orphan_result: dict = {}
    if rust_online:
        try:
            close_result = await core._ipc_command("close_all_positions", {"engine": "live"})
        except Exception as exc:
            if core._is_live_channel_unavailable_error(exc):
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
        orphan_result = await core._sweep_live_orphan_positions(errors)
        if orphan_result.get("rest_fallback"):
            rest_fallback_used = True
    else:
        close_result = orphan_result = {"skipped": True, "reason": "engine_offline"}

    logger.warning(
        "⚠ LIVE SESSION STOPPED — positions closed — rest_fallback=%s — errors=%s — actor=%s",
        rest_fallback_used, errors or None, getattr(actor, "actor_id", "?"),
    )
    return core._live_response({
        "message": "Live session stopped — positions closed / 實盤 session 已停止 — 倉位已平",
        "source": "rust_engine_with_rest_fallback" if rest_fallback_used else "rust_engine",
        "rest_fallback": rest_fallback_used,
        "reason": "live_pipeline_not_authorized" if rest_fallback_used else None,
        "close_result": close_result,
        "orphan_sweep": orphan_result,
        "errors": errors if errors else None,
        "session": {"session_state": "stopped", "session_id": "rust_engine_live"},
    })


@core.live_router.post("/session/pause")
async def post_live_session_pause(
    actor: Any = Depends(base.current_actor),
) -> dict:
    """
    POST /api/v1/live/session/pause
    暫停 Live session — 停止策略下單，但不平倉

    Stops new order dispatch without closing existing positions.
    暫停新訂單下發，不平倉。
    """
    core._require_operator(actor)
    try:
        result = await core._ipc_command("pause_paper", {"engine": "live"})
        return core._live_response({
            "message": "Live session paused — no new orders / 實盤 session 已暫停",
            "source": "rust_engine",
            "ipc_result": result,
            "session": {"session_state": "paused", "session_id": "rust_engine_live"},
        })
    except Exception as exc:
        logger.error("IPC pause_paper failed (live pause): %s", exc)
        raise HTTPException(status_code=502, detail=f"IPC command failed: {exc}")


@core.live_router.post("/session/resume")
async def post_live_session_resume(
    actor: Any = Depends(base.current_actor),
) -> dict:
    """
    POST /api/v1/live/session/resume
    恢復 Live session — 從暫停狀態恢復策略下單

    Gate: Operator role + live_reserved global mode (same as start).
    門控：Operator 角色 + live_reserved global mode（與 start 相同）。
    """
    core._require_operator(actor)

    # Gate: global_mode_state must still be live_reserved
    # 門控：global_mode_state 仍需為 live_reserved
    global_mode = core._get_global_mode_state()
    if "live" not in global_mode:
        raise HTTPException(
            status_code=409,
            detail=f"Live session resume blocked: global_mode={global_mode!r}. "
                   "Switch Global Mode to live_reserved first.",
        )

    # Re-grant execution_authority and restart monitor on resume
    # 恢復時重新授予 execution_authority 並重啟縮倉監控
    core._set_execution_authority("granted")  # EA-PERSIST: resume → re-grant + persist
    core._LIVE_USER_STOPPED = False
    core._live_contraction_state = "normal"

    # Restart contraction monitor (cancel stale task if any)
    if core._live_monitor_task is not None and not core._live_monitor_task.done():
        core._live_monitor_task.cancel()
    core._live_monitor_task = asyncio.create_task(core._live_contraction_monitor())

    try:
        result = await core._ipc_command("resume_paper", {"engine": "live"})
        return core._live_response({
            "message": "Live session resumed / 實盤 session 已恢復",
            "source": "rust_engine",
            "ipc_result": result,
            "session": {"session_state": "active", "session_id": "rust_engine_live"},
            "contraction": {"state": "normal", "warn_pct": core.CONTRACTION_WARN_PCT, "halt_pct": core.CONTRACTION_HALT_PCT},
        })
    except Exception as exc:
        logger.error("IPC resume_paper failed (live resume): %s", exc)
        raise HTTPException(status_code=502, detail=f"IPC command failed: {exc}")


# ═══════════════════════════════════════════════════════════════════════════════
# Execution authority grant / revoke (in-memory, Operator only)
# Execution authority 授予 / 撤銷（記憶體，僅 Operator 角色）
# ═══════════════════════════════════════════════════════════════════════════════


@core.live_router.post("/execution-authority/grant")
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
    core._require_operator(actor)
    core._set_execution_authority("granted")  # EA-PERSIST: manual grant + persist
    actor_id = getattr(actor, "actor_id", "?")
    # Also create + approve live SM-1 authorization so governance center shows mode=live.
    # 同步創建並批准 live SM-1 授權，讓治理中心顯示 mode=live。
    _submit_live_governance_request(actor_id)
    logger.warning(
        "⚠ execution_authority GRANTED by actor=%s — live session now unlocked",
        actor_id,
    )
    return core._live_response({
        "execution_authority": "granted",
        "message": "execution_authority granted — live session unlocked",
        "actor": actor_id,
    })


@core.live_router.post("/execution-authority/revoke")
async def revoke_execution_authority(
    actor: Any = Depends(base.current_actor),
) -> dict:
    """
    POST /api/v1/live/execution-authority/revoke
    Operator revokes execution authority; lock screen re-appears.
    Operator 撤銷 execution_authority；鎖定頁重新顯示。
    """
    core._require_operator(actor)
    core._set_execution_authority("not_granted")  # EA-PERSIST: manual revoke + persist
    actor_id = getattr(actor, "actor_id", "?")
    # Revoke live SM-1 authorization so governance center reflects revoked state.
    # 撤銷 live SM-1 授權，讓治理中心反映已撤銷狀態。
    _revoke_live_governance_auth(reason="execution_authority_revoked", actor_id=actor_id)
    logger.info(
        "execution_authority REVOKED by actor=%s",
        actor_id,
    )
    return core._live_response({
        "execution_authority": "not_granted",
        "message": "execution_authority revoked — live session locked",
        "actor": getattr(actor, "actor_id", "?"),
    })
