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


def core_preflight():
    """Lazy import live_preflight module.

    為何 lazy + 函數包裝：與本檔既有「走 module attr 取得 sibling」的 monkeypatch
    安全模式一致；測試可 monkeypatch 本函數回傳的模組屬性（如 engine_mode_readback /
    all_five_live_gates_ok）而不需 patch import。
    """
    from . import live_preflight  # noqa: PLC0415
    return live_preflight


def _require_live_trade(actor: Any) -> None:
    """Batch B live session write gate: Operator + live trade scope."""
    base.require_scope_and_operator(actor, "live:trade")


def _require_live_authority(actor: Any) -> None:
    """Batch B execution authority gate: Operator + live authority scope."""
    base.require_scope_and_operator(actor, "live:authority")


def _live_call_params_with_token(method: str, params: dict[str, Any]) -> dict[str, Any]:
    """PHASE 0 AUTH-1：對 engine==live 的 LIVE_WRITE_METHOD（resume_paper / pause_paper）
    鑄 method-bound capability token 併入 params。

    為何在此鑄：caller（live session start/pause/resume）已先過自己的 operator/5-gate；
    此 helper 不做授權，只鑄憑證（Python authorizer → Rust enforcer）。lazy import 避免
    本檔 import-time 依賴 token 模組。secret 缺 → raise（fail-closed kill-switch，向上冒
    泡成 IPC 失敗 → 既有 502/503 fail-closed 路徑）。
    """
    from .live_patch_token import call_params_with_token  # noqa: PLC0415

    return call_params_with_token(method, params)


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

    P1-02 ordering：gate → IPC → readback → stamp。Python 控制面狀態僅 advisory，
    永不權威化 live readiness（PA ruling §0 INV-A1）。authority:"granted" /
    session_state:"active" 只能在「完整五門通過 + IPC resume 成功（不吞錯）+
    引擎回讀確認」後回傳；任一環節失敗即 fail-closed，撤銷 authority。

    Guard: Operator role + live_reserved（精確） + OPENCLAW_ALLOW_MAINNET（Mainnet）
    + secret slot + 簽名 authorization.json（require_authz=True）。
    engine_kind 僅用於日誌/上下文，引擎配置控制實際訂單路由。
    """
    _require_live_trade(actor)
    actor_id = getattr(actor, "actor_id", "live_operator")

    # Gate：完整 live 五門（含精確 live_reserved + 簽名授權），與 executor / Rust
    # spawn gate 對齊。失敗即拒絕，不 set authority。
    ok, reason_codes = core_preflight().all_five_live_gates_ok(actor, require_authz=True)
    if not ok:
        logger.warning(
            "Live session start BLOCKED: gate_failed=%s — actor=%s",
            reason_codes, actor_id,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "error": "live_gate_failed",
                "gate_failed": reason_codes,
                "authority": "denied",
                "session_state": "inactive",
                "rust_synced": False,
                "partial_failure": True,
                "message": "Live session blocked — live preflight gate failed. "
                           "Ensure Global Mode=live_reserved, secret slot configured, "
                           "and a valid signed authorization (renew if needed).",
            },
        )

    engine_kind = core._get_live_engine_kind()

    # IPC：恢復引擎管線。INV-A1 — 不可吞錯：resume 失敗則不 grant、不 active。
    # 如果管線因上次 stop 而暫停，恢復管線。
    #
    # PHASE 0 AUTH-1：resume_paper{engine:live} ∈ LIVE_WRITE_METHODS，Rust chokepoint
    # 要求 token。此 call 緊接 all_five_live_gates_ok 通過之後（上方 :168 gate），故在此
    # 鑄 method-bound token 併入 params（Python 是 authorizer、Rust 是 enforcer）。
    try:
        ipc_params = _live_call_params_with_token("resume_paper", {"engine": "live"})
        result = await core._ipc_command("resume_paper", ipc_params)
    except Exception as exc:
        logger.error("Live session start BLOCKED: IPC resume_paper failed — actor=%s err=%s", actor_id, exc)
        core._set_execution_authority(None)  # fail-closed：確保無 orphan granted
        from .error_sanitize import sanitize_exc_for_detail  # noqa: PLC0415
        raise HTTPException(
            status_code=502,
            detail={
                "error": "ipc_resume_failed",
                "authority": "denied",
                "session_state": "inactive",
                "rust_synced": False,
                "partial_failure": True,
                "ipc_error": sanitize_exc_for_detail(exc, "ipc_error"),
                "message": "Live session start failed: engine did not accept resume. "
                           "execution_authority NOT granted (fail-closed).",
            },
        )

    # Readback：確認引擎實際 posture（system_mode == live_reserved）。
    # INV-A1 — IPC 成功還不夠，必須回讀確認；stale/缺 snapshot 當失敗。
    try:
        readback = await core_preflight().engine_mode_readback()
    except Exception as exc:
        logger.error("Live session start BLOCKED: engine_mode_readback failed — actor=%s err=%s", actor_id, exc)
        core._set_execution_authority(None)
        from .error_sanitize import sanitize_exc_for_detail  # noqa: PLC0415
        raise HTTPException(
            status_code=502,
            detail={
                "error": "readback_failed",
                "authority": "denied",
                "session_state": "inactive",
                "rust_synced": False,
                "partial_failure": True,
                "ipc_error": sanitize_exc_for_detail(exc, "ipc_error"),
                "message": "Live session start failed: could not read back engine state. "
                           "execution_authority NOT granted (fail-closed).",
            },
        )
    if readback.get("system_mode") != "live_reserved":
        logger.error(
            "Live session start BLOCKED: readback system_mode=%r != live_reserved — actor=%s",
            readback.get("system_mode"), actor_id,
        )
        core._set_execution_authority(None)
        raise HTTPException(
            status_code=409,
            detail={
                "error": "readback_mode_mismatch",
                "authority": "denied",
                "session_state": "inactive",
                "rust_synced": False,
                "partial_failure": True,
                "readback": readback,
                "message": "Live session start failed: engine posture is not live_reserved. "
                           "execution_authority NOT granted (fail-closed).",
            },
        )

    # Stamp：門控 + IPC + 回讀全部通過後才授予 authority + active。
    # 啟動時授予 execution_authority；stop 時 / 進程重啟後清零（fail-closed）。
    core._set_execution_authority("granted")  # EA-PERSIST: session start → grant + persist
    core._LIVE_USER_STOPPED = False
    core._live_contraction_state = "normal"

    # Submit live governance request for operator audit trail (non-blocking)
    # 提交實盤治理申請用於操作員審計留痕（非阻塞）
    _submit_live_governance_request(actor_id)

    # Hook: earned-trust engine — record session start / 信任引擎 session 啟動鉤子
    try:
        from .earned_trust_engine import TIER_TTL_HOURS, get_trust_engine
        _te = get_trust_engine()
        _ttl = TIER_TTL_HOURS.get(_te.get_state_snapshot()["current_tier"], 24)
        _te.on_session_start(auth_expires_ts_ms=int((time.time() + _ttl * 3600) * 1000))
    except Exception as _te_exc:
        logger.debug("EarnedTrustEngine start hook (non-fatal): %s", _te_exc)

    # Start drawdown contraction monitor (cancel any stale task first)
    # 啟動回撤縮倉監控（先取消舊 task）
    if core._live_monitor_task is not None and not core._live_monitor_task.done():
        core._live_monitor_task.cancel()
    core._live_monitor_task = asyncio.create_task(core._live_contraction_monitor())

    logger.warning(
        "⚠ LIVE SESSION STARTED — engine_kind=%s execution_authority=granted "
        "rust_synced=true contraction_monitor=active warn=%.0f%% halt=%.0f%% — actor=%s",
        engine_kind, core.CONTRACTION_WARN_PCT, core.CONTRACTION_HALT_PCT,
        actor_id,
    )
    return core._live_response({
        "message": "Live session started / 實盤 session 已啟動",
        "source": "rust_engine",
        "engine_kind": engine_kind,
        "authority": "granted",
        "rust_synced": True,
        "readback": readback,
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
    _require_live_trade(actor)

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

    cancel_orders_result: dict = {}
    close_result: dict = {}
    orphan_result: dict = {}
    verify_result: dict = {}
    if rust_online:
        # Phase 1 — Cancel all pending USDT linear orders via the Rust engine
        # (IPC cancel_all_orders, engine=live, settleCoin=USDT) BEFORE close.
        # P1-03：取消掛單改走 Rust 執行權威，不再由 Python 直接打 Bybit
        # /v5/order/cancel-all（CC/operator 裁定 live 寫入必過 Rust）。同 close
        # path 的 fail-closed 處理：live IPC 通道不存在時 skip + 記 error，
        # 不降級到 REST。execution_authority 已撤銷，引擎此時不會下新單。
        try:
            cancel_orders_result = await core._ipc_command(
                "cancel_all_orders", {"engine": "live"}
            )
        except Exception as exc:
            if core._is_live_channel_unavailable_error(exc):
                logger.error(
                    "live session stop cancel BLOCKED: live IPC channel unavailable; REST fallback disabled"
                )
                cancel_orders_result = {
                    "skipped": True,
                    "reason": "live_pipeline_not_authorized",
                    "rest_fallback_disabled": True,
                }
                errors.append("live_channel_unavailable")
            else:
                errors.append(f"cancel_all_orders: {exc}")
                logger.error("IPC cancel_all_orders failed (live stop): %s", exc)
                cancel_orders_result = {"skipped": True, "reason": "cancel_all_orders_failed"}
        # Phase 2 — Close tracked positions via IPC.
        # 第二步：通過 IPC 平倉 paper_state 追蹤的持倉。
        try:
            close_result = await core._ipc_command("close_all_positions", {"engine": "live"})
        except Exception as exc:
            if core._is_live_channel_unavailable_error(exc):
                logger.error(
                    "live session stop close BLOCKED: live IPC channel unavailable; REST fallback disabled"
                )
                close_result = {
                    "skipped": True,
                    "reason": "live_pipeline_not_authorized",
                    "rest_fallback_disabled": True,
                }
                errors.append("live_channel_unavailable")
            else:
                errors.append(f"close_positions: {exc}")
                logger.error("IPC close_all_positions failed (live stop): %s", exc)
        # Phase 3 — Orphan position sweep (positions on exchange but not in paper_state).
        # 第三步：孤兒倉位清掃（交易所有但 paper_state 沒有）。
        if not close_result.get("rest_fallback_disabled"):
            orphan_result = await core._sweep_live_orphan_positions(errors)
        else:
            orphan_result = {
                "skipped": True,
                "reason": core._LIVE_REST_FALLBACK_DISABLED_DETAIL,
            }
        # Phase 4 — Verify Bybit account fully clean (positions=0 AND orders=0).
        # Polls REST until clean or timeout (~30s default). Residual = surfaced
        # in errors[] + verify field so operator sees explicit residual symbols.
        # 第四步：輪詢 REST 確認 Bybit 帳戶完全乾淨；殘留時顯式回報 symbol 清單。
        if not close_result.get("rest_fallback_disabled"):
            from .strategy_ai_routes import _verify_account_clean  # noqa: PLC0415
            verify_result = await _verify_account_clean(
                core._get_rust_client_safe(), env_label="live",
            )
            if not verify_result.get("clean"):
                errors.append(
                    f"live_verify_residual: positions={verify_result.get('residual_positions')} "
                    f"orders={verify_result.get('residual_orders')}"
                )
        else:
            verify_result = {
                "skipped": True,
                "reason": core._LIVE_REST_FALLBACK_DISABLED_DETAIL,
            }
    else:
        errors.append("engine_offline")
        cancel_orders_result = {"skipped": True, "reason": "engine_offline"}
        close_result = orphan_result = {"skipped": True, "reason": "engine_offline"}
        verify_result = {"skipped": True, "reason": "engine_offline"}

    logger.warning(
        "⚠ LIVE SESSION STOPPED — close requested — errors=%s — actor=%s",
        errors or None, getattr(actor, "actor_id", "?"),
    )
    if close_result.get("rest_fallback_disabled"):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "live_pipeline_not_authorized",
                "message": core._LIVE_REST_FALLBACK_DISABLED_DETAIL,
                "rest_fallback": False,
                "cancel_orders": cancel_orders_result,
                "close_result": close_result,
                "orphan_sweep": orphan_result,
                "verify": verify_result,
                "session_authority_revoked": True,
                "errors": errors if errors else None,
            },
        )
    partial_failure = bool(errors) or not verify_result.get("clean", False)
    closed_all = not partial_failure
    return core._live_response({
        "message": (
            "Live session stopped with partial close failure / 實盤 session 已停止，但平倉存在部分失敗"
            if partial_failure else
            "Live session stopped — orders cancelled + positions closed / 實盤 session 已停止 — 掛單已取消、倉位已平"
        ),
        "source": "rust_engine",
        "status": "partial_failure" if partial_failure else "closed",
        "closed_all": closed_all,
        "partial_failure": partial_failure,
        "rest_fallback": False,
        "reason": None,
        "cancel_orders": cancel_orders_result,
        "close_result": close_result,
        "orphan_sweep": orphan_result,
        "verify": verify_result,
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
    _require_live_trade(actor)
    try:
        # PHASE 0 AUTH-1：pause_paper{engine:live} ∈ LIVE_WRITE_METHODS。pause 是「停止
        # 新單但不平倉」控制，operator 過 _require_live_trade（live:trade scope）即可，
        # 不要求完整五門（pause 本身收縮風險，不應因 authz 過期而無法暫停）。在此 gate 後
        # 鑄 method-bound token。緊急 STOP（平倉）走 OUT-OF-SCOPE 的 close_* path，不受此約束。
        ipc_params = _live_call_params_with_token("pause_paper", {"engine": "live"})
        result = await core._ipc_command("pause_paper", ipc_params)
        return core._live_response({
            "message": "Live session paused — no new orders / 實盤 session 已暫停",
            "source": "rust_engine",
            "ipc_result": result,
            "session": {"session_state": "paused", "session_id": "rust_engine_live"},
        })
    except Exception as exc:
        # WP-05 Real Fix
        logger.exception("IPC pause_paper failed (live pause)")
        from .error_sanitize import sanitize_exc_for_detail  # noqa: PLC0415
        raise HTTPException(
            status_code=502,
            detail=sanitize_exc_for_detail(exc, "ipc_error"),
        )


@core.live_router.post("/session/resume")
async def post_live_session_resume(
    actor: Any = Depends(base.current_actor),
) -> dict:
    """
    POST /api/v1/live/session/resume
    恢復 Live session — 從暫停狀態恢復策略下單

    P1-02 ordering：gate → IPC → readback → stamp（與 start 相同）。修正點：
      - 舊版用 substring `"live" not in global_mode` → 改精確五門（含
        live_reserved 精確匹配，live_demo_observe 等含 "live" 子串者被擋）。
      - 舊版先 grant authority 再呼 IPC → 改為門控 + IPC 成功 + 回讀後才 grant；
        失敗一律 fail-closed 撤銷 authority、不回 active。
    """
    _require_live_trade(actor)
    actor_id = getattr(actor, "actor_id", "live_operator")

    # Gate：完整 live 五門（精確 live_reserved + 簽名授權）。
    ok, reason_codes = core_preflight().all_five_live_gates_ok(actor, require_authz=True)
    if not ok:
        logger.warning("Live session resume BLOCKED: gate_failed=%s — actor=%s", reason_codes, actor_id)
        raise HTTPException(
            status_code=409,
            detail={
                "error": "live_gate_failed",
                "gate_failed": reason_codes,
                "authority": "denied",
                "session_state": "inactive",
                "rust_synced": False,
                "partial_failure": True,
                "message": "Live session resume blocked — live preflight gate failed.",
            },
        )

    # IPC：恢復下單。失敗則不 grant、不 active（fail-closed）。
    #
    # PHASE 0 AUTH-1：resume_paper{engine:live} 緊接 all_five_live_gates_ok 通過之後
    # （上方 :517 gate）→ 鑄 method-bound token 併入 params。
    try:
        ipc_params = _live_call_params_with_token("resume_paper", {"engine": "live"})
        result = await core._ipc_command("resume_paper", ipc_params)
    except Exception as exc:
        logger.error("Live session resume BLOCKED: IPC resume_paper failed — actor=%s err=%s", actor_id, exc)
        core._set_execution_authority(None)
        from .error_sanitize import sanitize_exc_for_detail  # noqa: PLC0415
        raise HTTPException(
            status_code=502,
            detail={
                "error": "ipc_resume_failed",
                "authority": "denied",
                "session_state": "inactive",
                "rust_synced": False,
                "partial_failure": True,
                "ipc_error": sanitize_exc_for_detail(exc, "ipc_error"),
                "message": "Live session resume failed: engine did not accept resume (fail-closed).",
            },
        )

    # Readback：確認引擎 posture。
    try:
        readback = await core_preflight().engine_mode_readback()
    except Exception as exc:
        logger.error("Live session resume BLOCKED: engine_mode_readback failed — actor=%s err=%s", actor_id, exc)
        core._set_execution_authority(None)
        from .error_sanitize import sanitize_exc_for_detail  # noqa: PLC0415
        raise HTTPException(
            status_code=502,
            detail={
                "error": "readback_failed",
                "authority": "denied",
                "session_state": "inactive",
                "rust_synced": False,
                "partial_failure": True,
                "ipc_error": sanitize_exc_for_detail(exc, "ipc_error"),
                "message": "Live session resume failed: could not read back engine state (fail-closed).",
            },
        )
    if readback.get("system_mode") != "live_reserved":
        logger.error(
            "Live session resume BLOCKED: readback system_mode=%r != live_reserved — actor=%s",
            readback.get("system_mode"), actor_id,
        )
        core._set_execution_authority(None)
        raise HTTPException(
            status_code=409,
            detail={
                "error": "readback_mode_mismatch",
                "authority": "denied",
                "session_state": "inactive",
                "rust_synced": False,
                "partial_failure": True,
                "readback": readback,
                "message": "Live session resume failed: engine posture is not live_reserved (fail-closed).",
            },
        )

    # Stamp：全部通過後 re-grant + 重啟縮倉監控。
    core._set_execution_authority("granted")  # EA-PERSIST: resume → re-grant + persist
    core._LIVE_USER_STOPPED = False
    core._live_contraction_state = "normal"
    if core._live_monitor_task is not None and not core._live_monitor_task.done():
        core._live_monitor_task.cancel()
    core._live_monitor_task = asyncio.create_task(core._live_contraction_monitor())

    return core._live_response({
        "message": "Live session resumed / 實盤 session 已恢復",
        "source": "rust_engine",
        "authority": "granted",
        "rust_synced": True,
        "readback": readback,
        "ipc_result": result,
        "session": {"session_state": "active", "session_id": "rust_engine_live"},
        "contraction": {"state": "normal", "warn_pct": core.CONTRACTION_WARN_PCT, "halt_pct": core.CONTRACTION_HALT_PCT},
    })


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

    P1-02：手動 grant 不再無條件 stamp granted。依 PA 建議 (a)，先跑完整 live
    五門（含簽名授權）+ 引擎回讀，全部通過才授予；否則 fail-closed 拒絕，不留
    orphan granted。Python 控制面狀態僅 advisory（PA ruling §0 INV-A1）。

    Operator 顯式授予 execution_authority（記憶體中）。
    重啟後清零（fail-closed）。用於實盤前 demo 測試及未來 M 章受監督實盤門控。
    """
    _require_live_authority(actor)
    actor_id = getattr(actor, "actor_id", "?")

    # Gate：完整 live 五門（含簽名授權）。
    ok, reason_codes = core_preflight().all_five_live_gates_ok(actor, require_authz=True)
    if not ok:
        logger.warning("execution_authority grant BLOCKED: gate_failed=%s — actor=%s", reason_codes, actor_id)
        raise HTTPException(
            status_code=409,
            detail={
                "error": "live_gate_failed",
                "gate_failed": reason_codes,
                "execution_authority": "not_granted",
                "rust_synced": False,
                "partial_failure": True,
                "message": "execution_authority grant blocked — live preflight gate failed.",
            },
        )

    # Readback：確認引擎 posture（不可只憑門控就 stamp granted）。
    try:
        readback = await core_preflight().engine_mode_readback()
    except Exception as exc:
        logger.error("execution_authority grant BLOCKED: readback failed — actor=%s err=%s", actor_id, exc)
        from .error_sanitize import sanitize_exc_for_detail  # noqa: PLC0415
        raise HTTPException(
            status_code=502,
            detail={
                "error": "readback_failed",
                "execution_authority": "not_granted",
                "rust_synced": False,
                "partial_failure": True,
                "ipc_error": sanitize_exc_for_detail(exc, "ipc_error"),
                "message": "execution_authority grant failed: could not read back engine state (fail-closed).",
            },
        )
    if readback.get("system_mode") != "live_reserved":
        logger.error(
            "execution_authority grant BLOCKED: readback system_mode=%r != live_reserved — actor=%s",
            readback.get("system_mode"), actor_id,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "error": "readback_mode_mismatch",
                "execution_authority": "not_granted",
                "rust_synced": False,
                "partial_failure": True,
                "readback": readback,
                "message": "execution_authority grant failed: engine posture is not live_reserved (fail-closed).",
            },
        )

    core._set_execution_authority("granted")  # EA-PERSIST: manual grant + persist
    # Also create + approve live SM-1 authorization so governance center shows mode=live.
    # 同步創建並批准 live SM-1 授權，讓治理中心顯示 mode=live。
    _submit_live_governance_request(actor_id)
    logger.warning(
        "⚠ execution_authority GRANTED by actor=%s rust_synced=true — live session now unlocked",
        actor_id,
    )
    return core._live_response({
        "execution_authority": "granted",
        "rust_synced": True,
        "readback": readback,
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
    _require_live_authority(actor)
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
