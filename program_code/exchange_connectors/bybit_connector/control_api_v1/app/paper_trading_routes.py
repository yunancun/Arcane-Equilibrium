from __future__ import annotations

"""
OpenClaw Paper Trading API Routes / 纸上交易 API 路由
OpenClaw 模拟交易系统的所有 REST API 端点

TD-03 Split: Module-level singletons and DI wiring moved to paper_trading_wiring.py.
This file now contains only the router, request models, and route handlers.
All existing imports (`from .paper_trading_routes import X`) remain valid via re-exports.

MODULE_NOTE (中文):
  本模块定义纸上交易系统的所有 API 路由，使用 FastAPI APIRouter 模式。
  所有路由复用主系统的认证机制，要求 paper:read 或 paper:trade scope。
  所有响应携带 is_simulated=True 和 data_category=paper_simulated 标记。

MODULE_NOTE (English):
  This module defines all API routes for the paper trading system using FastAPI APIRouter.
  All routes reuse the main system's auth mechanism, requiring paper:read or paper:trade scopes.
  All responses carry is_simulated=True and data_category=paper_simulated markers.
"""

import asyncio
import json
import logging
import os
from pathlib import Path
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import main_legacy as base
from .ipc_state_reader import get_rust_reader
# ARCH-RC1 1C-3-F: paper_trading_engine.py retired. DEFAULT_INITIAL_BALANCE_USDT
# inlined here (the only consumer in this module). ShadowDecisionConsumer kept
# as a type hint for the SHADOW_CONSUMER global re-exported from wiring.
# ARCH-RC1 1C-3-F：paper_trading_engine.py 退場，常量內聯。
DEFAULT_INITIAL_BALANCE_USDT = 10_000.0
from .shadow_decision_builder import ShadowDecisionConsumer
from .paper_trading_metrics import compute_full_metrics
from .trading_true_metrics import fetch_db_true_metrics

# ═══════════════════════════════════════════════════════════════════════════════
# Singletons — re-exported from paper_trading_wiring.py (TD-03 split)
# 單例 — 從 paper_trading_wiring.py 重新導出（TD-03 拆分）
# ═══════════════════════════════════════════════════════════════════════════════
from .paper_trading_wiring import *  # noqa: F401,F403
from .paper_trading_wiring import (  # noqa: F811 — explicit re-exports for type checkers
    RISK_MANAGER,
    PORTFOLIO_RISK_CONTROL,
    PERCEPTION_PLANE,
    ENGINE,
    DEMO_SYNC,
    GOV_HUB,
    AUDIT_PIPELINE,
    INCIDENT_POLICY,
    TTL_ENFORCER,
    H0_GATE,
    CHANGE_AUDIT_LOG,
    RECOVERY_GATE,
    SCANNER_RATE_LIMITER,
    TELEGRAM_ALERTER,
    LEARNING_TIER_GATE,
    SHADOW_CONSUMER,
)

SHADOW_CONSUMER: ShadowDecisionConsumer | None = None

# ─────────────────────────────────────────────────────────────────────────────
# Sticky "user-initiated stop" flag / 用戶主動「停止」粘性標誌
# Rust engine only knows pause/resume — there is no native "stopped" state.
# /session/stop closes positions then issues pause_paper, so a follow-up
# /session/status would otherwise report "paused" and the GUI badge would
# show "已暫停" instead of "已停止". This flag distinguishes a user-initiated
# Stop from a plain Pause so the status response stays honest.
# Cleared by /session/start (user explicitly restarts the engine).
# Rust 引擎只有 pause/resume，沒有原生 "stopped" 狀態。/session/stop 平倉後
# 發 pause_paper，導致之後 status 一直顯示 "paused"，GUI 看到「已暫停」而非
# 「已停止」。這個標誌區分用戶主動 Stop 與普通 Pause，讓 status 誠實反映。
# 由 /session/start 清除（用戶顯式重啟引擎）。
_USER_STOPPED: bool = False

# ═══════════════════════════════════════════════════════════════════════════════
# Router / 路由器
# ═══════════════════════════════════════════════════════════════════════════════

paper_router = APIRouter(prefix="/api/v1/paper", tags=["Paper Trading / 纸上交易"])


def _require_paper_trade(actor: base.AuthenticatedActor) -> None:
    """Shared Batch B gate for paper/demo trading mutations.
    Batch B 共用 paper/demo 交易寫入閘門：必須是 Operator 且具 paper:trade scope。
    """
    base.require_scope_and_operator(actor, "paper:trade")


def _require_paper_config(actor: base.AuthenticatedActor) -> None:
    """Shared Batch B gate for paper config writes.
    Batch B 共用 paper config 寫入閘門：必須是 Operator 且具 paper:config scope。
    """
    base.require_scope_and_operator(actor, "paper:config")


# ═══════════════════════════════════════════════════════════════════════════════
# Request / Response Models / 请求响应模型
# ═══════════════════════════════════════════════════════════════════════════════

class SessionStartRequest(BaseModel):
    initial_balance: float = Field(default=DEFAULT_INITIAL_BALANCE_USDT, gt=0, le=1_000_000)


class OrderSubmitRequest(BaseModel):
    symbol: str = Field(max_length=30, pattern=r"^[A-Z0-9]{1,30}$")
    side: str = Field(max_length=4)      # "Buy" or "Sell"
    order_type: str = Field(max_length=10)  # "market" or "limit"
    qty: float = Field(gt=0)
    price: float | None = Field(default=None, gt=0)
    leverage: float = Field(default=1.0, gt=0, le=125)


class OrderCancelRequest(BaseModel):
    order_id: str = Field(max_length=50)


class TickRequest(BaseModel):
    market_prices: dict[str, float]


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: Build paper response envelope / 构建纸上交易响应信封
# ═══════════════════════════════════════════════════════════════════════════════

def _paper_response(
    data: Any,
    action_result: str = "success",
    reason_codes: list[str] | None = None,
) -> dict[str, Any]:
    """Build a simplified response envelope for paper trading routes."""
    return {
        "api_version": "v1",
        "action_result": action_result,
        "reason_codes": reason_codes or [],
        "data_category": "paper_simulated",
        "is_simulated": True,
        "data": data,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Session Routes / Session 路由
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# Rust engine is the SOLE paper trading engine.
# Session commands are sent via IPC to the running Rust engine (command channel).
# Rust 引擎是唯一的紙上交易引擎。
# Session 命令通過 IPC 發送到運行中的 Rust 引擎（命令通道）。
# ═══════════════════════════════════════════════════════════════════════════════

_RC10_DISABLED_MSG = (
    "Python paper engine disabled — Rust engine is the sole paper trading engine. "
    "Python 紙盤引擎已禁用 — Rust 引擎是唯一的紙上交易引擎。"
)


def _get_ipc_client():
    """Get the IPC client for sending commands to Rust engine / 獲取 IPC 客戶端"""
    from .ipc_client import EngineIPCClient
    return EngineIPCClient()


async def _ipc_command(method: str, params: dict | None = None) -> dict:
    """Send a command to Rust engine via IPC and return result / 通過 IPC 向 Rust 引擎發送命令"""
    client = _get_ipc_client()
    try:
        await client.connect()
        result = await client.call(method, params=params, timeout=5.0)
        return result
    finally:
        await client.disconnect()


def _get_demo_summary() -> dict:
    """Get Demo account summary (balance + position count) via httpx BybitClient.
    通過 httpx BybitClient 獲取 Demo 帳戶摘要。
    """
    from .strategy_ai_routes import _get_rust_client
    rc = _get_rust_client()
    if rc is None:
        return {"available": False}
    try:
        wallet = rc.refresh_balance()
        positions = rc.get_positions("linear")
        open_positions = [p for p in positions if float(p.get("size") or p.get("qty") or 0) > 0]
        return {
            "available": True,
            "source": "bybit_demo_api",
            "equity": wallet.get("total_equity", 0),
            "wallet_balance": wallet.get("total_wallet_balance", 0),
            "available_balance": wallet.get("total_available_balance", 0),
            "unrealised_pnl": wallet.get("total_unrealised_pnl", 0),
            "position_count": len(open_positions),
        }
    except Exception as e:
        logger.debug("Demo summary failed: %s", e)
        return {"available": False, "error": str(e)}



@paper_router.post("/session/start")
async def post_session_start(
    req: SessionStartRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Resume paper trading on Rust engine / 在 Rust 引擎上恢復紙盤交易"""
    _require_paper_trade(actor)
    rust = get_rust_reader()
    if not rust.is_available():
        raise HTTPException(status_code=503, detail="Rust engine not available / Rust 引擎不可用")
    try:
        result = await _ipc_command("resume_paper", {"engine": "paper"})
        # Clear sticky stop flag — user explicitly restarted / 用戶顯式重啟，清除停止標誌
        global _USER_STOPPED
        _USER_STOPPED = False
        rust_state = rust.get_paper_state(engine="paper") or {}
        return _paper_response({
            "message": "Paper trading started (resumed) / 紙盤交易已啟動（恢復）",
            "source": "rust_engine",
            "ipc_result": result,
            "position_count": len(rust_state.get("positions", [])),
            "balance": rust_state.get("balance", 0),
            "session": {"session_state": "active", "session_id": "rust_engine"},
        })
    except Exception as e:
        logger.error("IPC resume_paper failed: %s", e)
        raise HTTPException(status_code=502, detail=f"IPC command failed: {e}")


@paper_router.post("/session/reauth")
async def post_session_reauth(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Re-grant paper trading authorization / 重新授予紙盤授權"""
    _require_paper_trade(actor)
    if GOV_HUB is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")
    try:
        already_authorized = GOV_HUB.is_authorized()
        if already_authorized:
            return _paper_response({
                "granted": False, "is_authorized": True,
                "message": "Authorization already active / 授權已有效",
            })
        # Read max_order_notional_usdt from Rust RiskConfig to avoid hardcoding.
        # 從 Rust RiskConfig 讀取 max_order_notional_usdt，避免硬編碼。
        max_pos_usd = 10_000.0
        try:
            rc = await _ipc_command("get_risk_config")
            val = (rc.get("config") or {}).get("limits", {}).get("max_order_notional_usdt", 0.0)
            if isinstance(val, (int, float)) and val > 0:
                max_pos_usd = float(val)
        except Exception:
            pass  # fall back to default / 回退到預設值
        granted = GOV_HUB.grant_paper_authorization(max_position_usd=max_pos_usd)
        return _paper_response({
            "granted": granted,
            "is_authorized": GOV_HUB.is_authorized(),
            "message": "Paper authorization granted / 紙盤授權已授予" if granted
                       else "grant_paper_authorization() returned False",
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in session reauth: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@paper_router.post("/session/pause")
async def post_session_pause(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Pause paper trading — stops strategy dispatch + Demo shadow orders / 暫停紙盤交易"""
    _require_paper_trade(actor)
    try:
        result = await _ipc_command("pause_paper", {"engine": "paper"})
        return _paper_response({
            "message": "Paper trading paused / 紙盤交易已暫停",
            "source": "rust_engine",
            "ipc_result": result,
            "session": {"session_state": "paused", "session_id": "rust_engine"},
        })
    except Exception as e:
        logger.error("IPC pause_paper failed: %s", e)
        raise HTTPException(status_code=502, detail=f"IPC command failed: {e}")


@paper_router.post("/session/resume")
async def post_session_resume(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Resume paper trading — restores strategy dispatch + Demo shadow orders / 恢復紙盤交易"""
    _require_paper_trade(actor)
    try:
        result = await _ipc_command("resume_paper", {"engine": "paper"})
        # Resume also clears any prior sticky stop / 恢復同樣清除停止標誌
        global _USER_STOPPED
        _USER_STOPPED = False
        return _paper_response({
            "message": "Paper trading resumed / 紙盤交易已恢復",
            "source": "rust_engine",
            "ipc_result": result,
            "session": {"session_state": "active", "session_id": "rust_engine"},
        })
    except Exception as e:
        logger.error("IPC resume_paper failed: %s", e)
        raise HTTPException(status_code=502, detail=f"IPC command failed: {e}")


async def _verify_paper_state_clean(
    engine: str,
    *,
    max_attempts: int | None = None,
    interval_sec: float | None = None,
) -> dict:
    """Poll engine snapshot until paper_state.positions is empty for `engine`.

    Paper / paper-mode demo lives entirely in Rust paper_state — there are
    no Bybit orders to cancel. After IPC close_all_positions, Rust clears
    the positions hashmap; we just confirm the snapshot reflects that.

    Paper / paper 模式下持倉只在 Rust paper_state 內，無 Bybit 掛單需取消；
    本 helper 只確認 IPC close_all_positions 後快照中持倉=0。

    Returns {clean, attempts, elapsed_sec, residual_positions?, residual_position_symbols?}.
    """
    cap = max(1, int(max_attempts if max_attempts is not None
                     else os.environ.get("OPENCLAW_STOP_VERIFY_MAX_ATTEMPTS", "30")))
    interval = max(0.1, float(interval_sec if interval_sec is not None
                              else os.environ.get("OPENCLAW_STOP_VERIFY_INTERVAL_SEC", "0.3")))
    rust = get_rust_reader()
    if not rust.is_available():
        return {"clean": False, "skipped": True, "reason": "engine_offline"}
    last_open: list[dict] = []
    started = asyncio.get_event_loop().time()
    for attempt in range(1, cap + 1):
        snap = rust.get_paper_state(engine=engine)
        positions = (snap or {}).get("positions") or []
        # Snapshot stores Vec<PositionSnapshot> with nested `position.qty`.
        # 快照 positions 是 Vec<PositionSnapshot>，qty 在巢狀的 position 子物件。
        last_open = []
        for entry in positions:
            if not isinstance(entry, dict):
                continue
            pos = entry.get("position") if isinstance(entry.get("position"), dict) else entry
            qty = float(pos.get("qty") or pos.get("size") or 0)
            if qty > 0:
                last_open.append(pos)
        if not last_open:
            elapsed = asyncio.get_event_loop().time() - started
            return {
                "clean": True,
                "attempts": attempt,
                "elapsed_sec": round(elapsed, 2),
            }
        if attempt < cap:
            await asyncio.sleep(interval)
    elapsed = asyncio.get_event_loop().time() - started
    syms = sorted({str(p.get("symbol") or "") for p in last_open if p.get("symbol")})
    logger.error(
        "Paper-mode (%s) verify NOT-CLEAN after %d attempts (%.2fs): residual=%d symbols=%s",
        engine, cap, elapsed, len(last_open), syms,
    )
    return {
        "clean": False,
        "attempts": cap,
        "elapsed_sec": round(elapsed, 2),
        "residual_positions": len(last_open),
        "residual_position_symbols": syms,
    }


@paper_router.post("/session/stop")
async def post_session_stop(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Stop Paper engine only — close paper positions, pause paper strategy dispatch.
    Does NOT affect Demo engine.  Use /session/stop-all to stop both engines.
    僅停止 Paper 引擎 — 平倉、暫停策略分派。不影響 Demo 引擎。
    雙引擎聯停請用 /session/stop-all。

    Paper engine has no Bybit orders to cancel — all state lives in
    paper_state. Verify polls the engine snapshot until positions=0.
    Paper 引擎無 Bybit 掛單需取消，狀態全在 paper_state 中；verify 輪詢快照確認持倉=0。
    """
    _require_paper_trade(actor)
    errors: list[str] = []
    global _USER_STOPPED
    _USER_STOPPED = True
    rust_online = get_rust_reader().is_available()
    close_result: dict = {}
    pause_result: dict = {}
    verify_result: dict = {}
    if rust_online:
        # Pause first to stop new strategy dispatch, then close, then verify.
        # 先暫停策略派發、再平倉、再確認。
        try:
            pause_result = await _ipc_command("pause_paper", {"engine": "paper"})
        except Exception as e:
            errors.append(f"paper_pause: {e}")
            logger.error("IPC pause_paper (paper) failed: %s", e)
        try:
            close_result = await _ipc_command("close_all_positions", {"engine": "paper"})
        except Exception as e:
            errors.append(f"paper_close: {e}")
            logger.error("IPC close_all_positions (paper) failed: %s", e)
        verify_result = await _verify_paper_state_clean("paper")
        if not verify_result.get("clean") and not verify_result.get("skipped"):
            errors.append(
                f"paper_verify_residual: positions={verify_result.get('residual_positions')}"
            )
    else:
        close_result = pause_result = {"skipped": True, "reason": "engine_offline"}
        verify_result = {"skipped": True, "reason": "engine_offline"}
        logger.info("Rust engine offline — skipping IPC (already stopped)")
    return _paper_response({
        "message": "Paper engine stopped — positions closed / Paper 引擎已停止，倉位已平",
        "source": "rust_engine",
        "paper_close": close_result,
        "paper_pause": pause_result,
        "verify": verify_result,
        "errors": errors if errors else None,
        "session": {"session_state": "stopped", "session_id": "rust_engine"},
    })


@paper_router.post("/session/stop-all")
async def post_session_stop_all(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Dual-engine stop — close ALL Paper + Demo positions, pause both strategies.
    Use this when you want to halt both engines in one action.
    雙引擎聯停 — 平掉 Paper + Demo 所有倉位、暫停兩個引擎策略分派。
    IMPORTANT: engine params are explicit — without them IPC routes to primary()
    which is live > demo > paper, causing unintended cross-engine writes.
    重要：明確傳 engine 參數 — 否則 IPC 路由到 primary() 造成跨引擎操作。
    """
    _require_paper_trade(actor)
    errors: list[str] = []
    global _USER_STOPPED
    _USER_STOPPED = True
    rust_online = get_rust_reader().is_available()
    close_result: dict = {}
    demo_close_result: dict = {}
    pause_result: dict = {}
    demo_cancel_orders: dict = {}
    paper_verify: dict = {}
    demo_verify: dict = {}
    if rust_online:
        # ── Phase 0: Pause both pipelines first to stop new dispatch.
        # 先雙引擎暫停，避免後續流程中產生新單。
        try:
            pause_result = await _ipc_command("pause_paper", {"engine": "paper"})
        except Exception as e:
            errors.append(f"paper_pause: {e}")
            logger.error("IPC pause_paper (paper) failed: %s", e)
        try:
            await _ipc_command("pause_paper", {"engine": "demo"})
        except Exception as e:
            logger.info("IPC pause_paper (demo) skipped or failed: %s", e)
        # ── Phase 1: Demo cancel-all (REST settleCoin=USDT, single call covers
        # entire account regardless of strategy symbol set). Paper has no
        # Bybit orders so this branch is demo-only.
        # 第一步：Demo 全帳戶 cancel-all（settleCoin=USDT）。Paper 無 Bybit 掛單跳過。
        try:
            from .strategy_ai_routes import _sweep_demo_orphan_orders  # noqa: PLC0415
            demo_cancel_orders = await _sweep_demo_orphan_orders(errors)
        except Exception as e:
            logger.info("Demo cancel-all skipped (non-fatal): %s", e)
            demo_cancel_orders = {"skipped": True, "reason": str(e)}
        # ── Phase 2: Close positions for both engines.
        # 第二步：雙引擎平倉。
        try:
            close_result = await _ipc_command("close_all_positions", {"engine": "paper"})
        except Exception as e:
            errors.append(f"paper_close: {e}")
            logger.error("IPC close_all_positions (paper) failed: %s", e)
        try:
            demo_close_result = await _ipc_command("close_all_positions", {"engine": "demo"})
        except Exception as e:
            logger.info("IPC close_all_positions (demo) skipped or failed: %s", e)
        # ── Phase 3: Demo orphan position sweep (positions on exchange not in paper_state).
        # 第三步：Demo 孤兒倉位清掃。
        try:
            from .strategy_ai_routes import _sweep_demo_orphan_positions  # noqa: PLC0415
            orphan_result = await _sweep_demo_orphan_positions(errors)
            demo_close_result = {**demo_close_result, "orphan_sweep": orphan_result}
        except Exception as e:
            logger.info("Orphan sweep skipped (non-fatal): %s", e)
        # ── Phase 4: Verify both engines fully clean.
        # Paper: poll paper_state snapshot until positions=0.
        # Demo: poll Bybit REST until positions=0 AND orders=0.
        # 第四步：雙引擎 verify 確認清乾淨。
        paper_verify = await _verify_paper_state_clean("paper")
        if not paper_verify.get("clean") and not paper_verify.get("skipped"):
            errors.append(
                f"paper_verify_residual: positions={paper_verify.get('residual_positions')}"
            )
        try:
            from .strategy_ai_routes import _verify_account_clean, _get_rust_client  # noqa: PLC0415
            demo_verify = await _verify_account_clean(_get_rust_client(), env_label="demo")
            if not demo_verify.get("clean") and not demo_verify.get("skipped"):
                errors.append(
                    f"demo_verify_residual: positions={demo_verify.get('residual_positions')} "
                    f"orders={demo_verify.get('residual_orders')}"
                )
        except Exception as e:
            logger.info("Demo verify skipped (non-fatal): %s", e)
            demo_verify = {"skipped": True, "reason": str(e)}
    else:
        close_result = demo_close_result = pause_result = {"skipped": True, "reason": "engine_offline"}
        demo_cancel_orders = paper_verify = demo_verify = {"skipped": True, "reason": "engine_offline"}
        logger.info("Rust engine offline — skipping IPC (already stopped)")
    return _paper_response({
        "message": "Both engines stopped — orders cancelled + positions closed / 雙引擎已停止，掛單已取消、倉位已平",
        "source": "rust_engine",
        "demo_cancel_orders": demo_cancel_orders,
        "paper_close": close_result,
        "demo_close": demo_close_result,
        "paper_pause": pause_result,
        "paper_verify": paper_verify,
        "demo_verify": demo_verify,
        "errors": errors if errors else None,
        "session": {"session_state": "stopped", "session_id": "rust_engine"},
    })


@paper_router.get("/session/status")
def get_session_status(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get current session status from Rust engine / 從 Rust 引擎獲取 session 狀態"""
    rust = get_rust_reader()
    # 3E-ARCH: explicit engine="paper" — without it the compat snapshot file is
    # whichever engine has is_primary=true (Live > Demo > Paper).
    # 3E-ARCH：必須明確指定 engine="paper"，否則 compat 檔由 is_primary 引擎寫入。
    rust_state = rust.get_paper_state(engine="paper") if rust.is_engine_available("paper") else None
    if rust_state is None:
        return _paper_response({
            "source": "rust_engine",
            "engine_available": False,
            "session": {
                "session_state": "offline",
                "session_id": "rust_engine",
                "session_halted": False,
                "session_halt_reason": "Rust engine not available / Rust 引擎不可用",
            },
            "pnl": {},
            "order_count": 0, "fill_count": 0, "position_count": 0,
        })
    # Read paper_paused from per-engine paper snapshot / 從 paper 引擎快照讀取暫停狀態
    full_snapshot = rust.get_snapshot(engine="paper") if rust.is_engine_available("paper") else None
    is_paused = full_snapshot.get("paper_paused", False) if full_snapshot else False
    # 3E-5: pipeline_kind from snapshot (serde renamed from trading_mode); default "paper"
    pipeline_kind = full_snapshot.get("trading_mode", "paper") if full_snapshot else "paper"
    # Wrap flat Rust snapshot into nested structure expected by GUI
    # 將 Rust 扁平快照包裝為 GUI 預期的嵌套結構
    positions = rust_state.get("positions", [])
    total_unrealized = sum(p.get("unrealized_pnl", 0) for p in positions)
    balance = rust_state.get("balance", 0)
    peak = rust_state.get("peak_balance", 0)
    realized = rust_state.get("total_realized_pnl", 0)
    fees = rust_state.get("total_fees", 0)
    # Attribute fees correctly: entry fees of still-open positions belong to unrealized,
    # not realized. total_fees - open_entry_fees = fees locked-in via closed trades.
    # 費用歸屬修復：仍開倉的 entry fee 屬於未實現，不應從 realized 中扣除。
    open_entry_fees = sum(p.get("entry_fee", 0.0) or 0.0 for p in positions)
    closed_fees = max(0.0, fees - open_entry_fees)
    # Translate Rust paused state: user-initiated Stop → "observing" (engine still running,
    # scanner still running, no new trades). Plain pause → "paused".
    # Rust paused 狀態翻譯：用戶主動 Stop → "observing"（引擎繼續運行、scanner 繼續、
    # 不開新倉）；普通 pause → "paused"。
    if is_paused:
        session_state = "observing" if _USER_STOPPED else "paused"
    else:
        session_state = "active"
    return _paper_response({
        "source": "rust_engine",
        # engine_available = True means Rust process is alive and writing snapshots.
        # Distinct from session_state (which tracks paper trading phase).
        # engine_available = True 表示 Rust 進程存活並持續寫快照；
        # 與 session_state（paper 交易階段）分開。
        "engine_available": True,
        "session": {
            "session_state": session_state,
            "session_id": "rust_engine",
            "initial_paper_balance_usdt": rust_state.get("initial_balance", peak),
            "current_paper_balance_usdt": balance,
            "peak_balance_usdt": peak,
            "session_halted": False,
            "session_halt_reason": None,
            "pipeline_kind": pipeline_kind,
        },
        "pnl": {
            "realized_pnl": realized,
            "unrealized_pnl": total_unrealized,
            "total_fees_paid": fees,
            "total_ai_cost": 0,
            "net_paper_pnl": realized + total_unrealized - fees,
            "net_realized_pnl": realized - closed_fees,
            "closed_position_pnl": realized,
        },
        "order_count": 0,
        "fill_count": rust_state.get("trade_count", 0),
        "position_count": len(positions),
        "state_revision": 0,
        # P3: Demo balance from Rust WS sync (no API call — avoids blocking)
        # Demo 餘額從 Rust WS 同步讀取（不打 API — 避免阻塞）
        # BALANCE-REAL-1: explicit pipeline_status so paper-tab demo card can
        # render N/A + 未連接 instead of stale 0 / hardcoded 10000.
        # BALANCE-REAL-1：顯式 pipeline_status，讓 paper 頁的 demo 子卡片
        # 在斷線時顯示 N/A + 未連接，而非殘留 0 或硬編碼 10000。
        "demo": {
            "available": rust.is_engine_available("demo"),
            "pipeline_status": "connected" if rust.is_engine_available("demo") else "disconnected",
            "pipeline_reason": (
                None if rust.is_engine_available("demo")
                else "Bybit Demo wallet REST 未連接（引擎啟動時抓取失敗）/ wallet REST disconnected"
            ),
            "source": "rust_ws_sync",
            "sync_balance": rust_state.get("bybit_sync_balance"),
        },
    })


# ═══════════════════════════════════════════════════════════════════════════════
# Order Routes / 订单路由
# ═══════════════════════════════════════════════════════════════════════════════

@paper_router.post("/order/submit")
def post_order_submit(
    req: OrderSubmitRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """DISABLED: Rust engine manages order execution / 已禁用：Rust 引擎管理訂單執行"""
    _require_paper_trade(actor)
    raise HTTPException(status_code=410, detail=_RC10_DISABLED_MSG)


@paper_router.post("/order/cancel")
def post_order_cancel(
    req: OrderCancelRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """DISABLED: Rust engine manages order lifecycle / 已禁用：Rust 引擎管理訂單生命週期"""
    _require_paper_trade(actor)
    raise HTTPException(status_code=410, detail=_RC10_DISABLED_MSG)


@paper_router.get("/orders")
def get_orders(
    state_filter: str | None = None,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get orders from Rust engine / 從 Rust 引擎獲取訂單"""
    # Rust engine manages orders internally; recent intents serve as order log
    # Rust 引擎內部管理訂單；最近意圖列表作為訂單記錄
    reader = get_rust_reader()
    if reader.is_engine_available("paper"):
        intents = reader.get_recent_intents(mode="paper") or []
        return _paper_response({"orders": intents, "count": len(intents), "source": "rust_engine"})
    return _paper_response({"orders": [], "count": 0, "source": "rust_engine"})


# ═══════════════════════════════════════════════════════════════════════════════
# Position / Fill / PnL Routes / 持仓 / 成交 / PnL 路由
# ═══════════════════════════════════════════════════════════════════════════════

@paper_router.get("/positions")
def get_positions(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get current paper positions from Rust engine / 從 Rust 引擎獲取紙上持倉"""
    rust = get_rust_reader()
    # 3E-ARCH: explicit engine="paper" required / 必須明確指定 paper 引擎
    rust_state = rust.get_paper_state(engine="paper") if rust.is_engine_available("paper") else None
    if rust_state is None:
        return _paper_response({"positions": [], "count": 0, "source": "rust_engine"})
    # Transform Rust position fields to GUI-expected format
    # 轉換 Rust 持倉欄位為 GUI 預期格式
    raw_positions = rust_state.get("positions", [])
    transformed = []
    for p in raw_positions:
        transformed.append({
            **p,
            "side": "Buy" if p.get("is_long", True) else "Sell",
            "avg_entry_price": p.get("entry_price", p.get("avg_entry_price", 0)),
        })
    return _paper_response({"positions": transformed, "count": len(transformed), "source": "rust_engine"})


@paper_router.post("/close-all-positions")
async def post_close_all_positions(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Close all paper positions without stopping the session (engine keeps running).
    平掉所有 Paper 持倉，不停止 session（引擎繼續運行）。
    """
    _require_paper_trade(actor)
    rust = get_rust_reader()
    if not rust.is_available():
        raise HTTPException(status_code=503, detail="Rust engine not available / Rust 引擎不可用")
    try:
        result = await _ipc_command("close_all_positions", {"engine": "paper"})
        return _paper_response({
            "message": "All paper positions closed — session continues / 所有 Paper 持倉已平，session 繼續",
            "source": "rust_engine",
            "close_result": result,
        })
    except Exception as e:
        logger.error("IPC close_all_positions (paper) failed: %s", e)
        raise HTTPException(status_code=502, detail=f"IPC error: {e}")


@paper_router.post("/positions/{symbol}/close")
async def post_close_position(
    symbol: str,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Close a single paper position by symbol via IPC close_position command.
    通過 IPC close_position 指令平掉指定 symbol 的紙上持倉。
    """
    _require_paper_trade(actor)
    rust = get_rust_reader()
    if not rust.is_available():
        raise HTTPException(status_code=503, detail="Rust engine not available / Rust 引擎不可用")
    try:
        result = await _ipc_command("close_position", {"symbol": symbol.upper(), "engine": "paper"})
        return _paper_response({"symbol": symbol.upper(), "closed": True, "source": "rust_engine", "ipc": result})
    except Exception as e:
        logger.error("IPC close_position failed for %s: %s", symbol, e)
        raise HTTPException(status_code=502, detail=f"IPC error: {e}")


@paper_router.get("/fills")
def get_fills(
    limit: int = 50,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get fill history for the paper engine.
    獲取 paper 引擎的成交歷史。

    Source priority: PG `trading.fills` (authoritative, carries realized_pnl) →
    Rust in-memory ring buffer fallback (50-deep, now also carries realized_pnl).
    數據源優先序：PG `trading.fills`（權威，帶 realized_pnl）→ Rust 環形緩衝備援
    （50 筆上限，現亦帶 realized_pnl）。
    """
    capped_limit = min(limit, 200)
    # Try PG first — DB row has realized_pnl per fill.
    # 優先讀 PG — DB 列帶逐筆 realized_pnl。
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
                "FROM trading.fills WHERE engine_mode = %s ORDER BY ts DESC LIMIT %s",
                ("paper", capped_limit),
            )
            rows = cur.fetchall()
            fills = []
            for ts, symbol, side, qty, price, fee, realized_pnl, strategy in rows:
                ts_ms = int(ts.timestamp() * 1000) if ts is not None else 0
                sym = symbol or ""
                # Category inference: USDT pair → linear; plain USD pair → inverse.
                # 品類推斷：USDT 對 → linear；純 USD 對 → inverse。
                category = "inverse" if sym.endswith("USD") and not sym.endswith("USDT") else "linear"
                fills.append({
                    "timestamp_ms": ts_ms,
                    "symbol": sym,
                    "side": side or "",
                    "is_long": side == "Buy",
                    "qty": float(qty) if qty is not None else 0.0,
                    "price": float(price) if price is not None else 0.0,
                    "fee": float(fee) if fee is not None else 0.0,
                    "realized_pnl": float(realized_pnl) if realized_pnl is not None else 0.0,
                    "strategy": strategy or "",
                    "category": category,
                })
            return _paper_response({"fills": fills, "count": len(fills), "source": "pg_trading_fills"})
        except Exception as e:
            logger.warning("PG fills query failed, falling back to Rust snapshot: %s", e)
        finally:
            try:
                db_pool.put_conn(conn)
            except Exception:
                pass

    # Fallback: Rust in-memory buffer (TimestampedFill now carries realized_pnl).
    # 備援：Rust 記憶體緩衝（TimestampedFill 現帶 realized_pnl）。
    reader = get_rust_reader()
    if reader.is_engine_available("paper"):
        rust_fills = reader.get_recent_fills(mode="paper") or []
        for f in rust_fills:
            if isinstance(f, dict) and "side" not in f:
                f["side"] = "Buy" if f.get("is_long") else "Sell"
        capped = rust_fills[:capped_limit]
        return _paper_response({"fills": capped, "count": len(capped), "source": "rust_engine"})
    return _paper_response({"fills": [], "count": 0, "source": "rust_engine"})


@paper_router.get("/pnl")
def get_pnl(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get paper PnL summary from Rust engine / 從 Rust 引擎獲取紙上 PnL"""
    rust = get_rust_reader()
    # 3E-ARCH: explicit engine="paper" / 必須明確指定 paper 引擎
    rust_state = rust.get_paper_state(engine="paper") if rust.is_engine_available("paper") else None
    if rust_state is None:
        return _paper_response({"source": "rust_engine", "available": False})
    positions = rust_state.get("positions", [])
    total_unrealized = sum(p.get("unrealized_pnl", 0) for p in positions)
    realized = rust_state.get("total_realized_pnl", 0)
    fees = rust_state.get("total_fees", 0)
    # See status() for rationale — attribute open-position entry fees to unrealized.
    # 見 status()：仍開倉的 entry fee 歸屬於未實現，不應扣在 realized 頭上。
    open_entry_fees = sum(p.get("entry_fee", 0.0) or 0.0 for p in positions)
    closed_fees = max(0.0, fees - open_entry_fees)
    return _paper_response({
        "source": "rust_engine",
        "realized_pnl": realized,
        "unrealized_pnl": total_unrealized,
        "total_fees_paid": fees,
        "total_ai_cost": 0,
        "net_paper_pnl": realized + total_unrealized - fees,
        "net_realized_pnl": realized - closed_fees,
        "closed_position_pnl": realized,
        "trade_count": rust_state.get("trade_count", 0),
    })


@paper_router.get("/audit-trail")
def get_audit_trail(
    limit: int = 100,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get audit trail from Rust engine / 從 Rust 引擎獲取審計記錄"""
    # Rust recent intents + fills serve as audit trail / Rust 意圖+成交作為審計記錄
    reader = get_rust_reader()
    trail: list = []
    if reader.is_engine_available("paper"):
        intents = reader.get_recent_intents(mode="paper") or []
        fills = reader.get_recent_fills(mode="paper") or []
        trail = intents + fills
    return _paper_response({"audit_trail": trail[:min(limit, 500)], "count": len(trail), "source": "rust_engine"})


# ═══════════════════════════════════════════════════════════════════════════════
# Tick Route / 成交模拟 Tick 路由
# ═══════════════════════════════════════════════════════════════════════════════

@paper_router.post("/tick")
def post_tick(
    req: TickRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """DISABLED: Rust engine processes ticks internally / 已禁用：Rust 引擎內部處理 tick"""
    _require_paper_trade(actor)
    raise HTTPException(status_code=410, detail=_RC10_DISABLED_MSG)


# ═══════════════════════════════════════════════════════════════════════════════
# Export Route / 导出路由
# ═══════════════════════════════════════════════════════════════════════════════

@paper_router.get("/export")
def get_export(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Export session data from Rust engine snapshot / 從 Rust 引擎快照導出 session 數據"""
    reader = get_rust_reader()
    # 3E-ARCH: export paper-engine snapshot specifically / 匯出 paper 引擎快照
    snapshot = reader.get_snapshot(engine="paper") if reader.is_engine_available("paper") else None
    if snapshot is None:
        return _paper_response({"available": False, "source": "rust_engine"})
    return _paper_response({"source": "rust_engine", **snapshot})


# ═══════════════════════════════════════════════════════════════════════════════
# Market Feed Routes / 实时行情流路由
# ═══════════════════════════════════════════════════════════════════════════════

class MarketFeedStartRequest(BaseModel):
    symbols: list[str] = Field(default=["BTCUSDT", "ETHUSDT"], max_length=20)


class MarketFeedSymbolRequest(BaseModel):
    symbol: str = Field(max_length=30, pattern=r"^[A-Z0-9]{1,30}$")


@paper_router.post("/market-feed/start")
def post_market_feed_start(
    req: MarketFeedStartRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """DISABLED: Rust engine has its own WebSocket feed / 已禁用：Rust 引擎有自己的 WebSocket 行情流"""
    _require_paper_trade(actor)
    # Rust engine is the sole WS connection — no Python WS needed
    # Rust 引擎是唯一的 WS 連接 — 不需要 Python WS
    return _paper_response({
        "message": "Market feed managed by Rust engine / 行情流由 Rust 引擎管理",
        "source": "rust_engine",
    }, action_result="no_change")


@paper_router.post("/market-feed/stop")
def post_market_feed_stop(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """DISABLED: Rust engine manages its own WebSocket / 已禁用：Rust 引擎管理自己的 WebSocket"""
    _require_paper_trade(actor)
    return _paper_response({
        "message": "Market feed managed by Rust engine / 行情流由 Rust 引擎管理",
        "source": "rust_engine",
    }, action_result="no_change")


@paper_router.get("/market-feed/status")
def get_market_feed_status(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get market data feed status from Rust engine / 從 Rust 引擎獲取行情數據流狀態"""
    # Python DISPATCHER removed — read from Rust engine snapshot instead.
    # 3E-ARCH: only Paper writes market_data_tx (D19) so read paper engine snapshot.
    # Python DISPATCHER 已移除 — 改從 Rust 引擎快照讀取。
    # 3E-ARCH：只有 Paper 寫 market_data_tx（D19），所以讀 paper 引擎快照。
    reader = get_rust_reader()
    snap = reader.get_snapshot(engine="paper") if reader.is_engine_available("paper") else None
    if snap is not None:
        stats = snap.get("stats", {})
        last_tick_ms = stats.get("last_tick_ms", 0)
        import time
        age_sec = (time.time() * 1000 - last_tick_ms) / 1000 if last_tick_ms > 0 else 999
        is_stale = age_sec > 30
        return _paper_response({
            "running": not is_stale,
            "source": "rust_engine",
            "total_ticks": stats.get("total_ticks", 0),
            "total_fills": stats.get("total_fills", 0),
            "last_tick_ms": last_tick_ms,
            "last_tick_age_sec": round(age_sec, 1),
            "attention_level": "high" if not is_stale else "dormant",
            "symbols": list(snap.get("latest_prices", {}).keys()),
            "message": "Rust engine WS feed active" if not is_stale else "Rust engine feed stale",
        })
    return _paper_response({
        "running": False,
        "attention_level": "dormant",
        "message": "Engine not available / 引擎不可用",
    })


@paper_router.post("/market-feed/add-symbol")
def post_market_feed_add_symbol(
    req: MarketFeedSymbolRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """DISABLED: Rust engine manages symbols at startup / 已禁用：Rust 引擎在啟動時管理 symbols"""
    _require_paper_trade(actor)
    raise HTTPException(status_code=410, detail=_RC10_DISABLED_MSG)


@paper_router.post("/market-feed/remove-symbol")
def post_market_feed_remove_symbol(
    req: MarketFeedSymbolRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """DISABLED: Rust engine manages symbols at startup / 已禁用：Rust 引擎在啟動時管理 symbols"""
    _require_paper_trade(actor)
    raise HTTPException(status_code=410, detail=_RC10_DISABLED_MSG)


# ═══════════════════════════════════════════════════════════════════════════════
# Shadow Decision Routes / 影子决策路由
# ═══════════════════════════════════════════════════════════════════════════════

class ShadowFeedRequest(BaseModel):
    market_prices: dict[str, float]
    symbol: str = Field(default="BTCUSDT", max_length=30, pattern=r"^[A-Z0-9]{1,30}$")


@paper_router.post("/shadow/feed")
def post_shadow_feed(
    req: ShadowFeedRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """DISABLED: Shadow decisions handled by Rust engine / 已禁用：影子決策由 Rust 引擎處理"""
    _require_paper_trade(actor)
    raise HTTPException(status_code=410, detail=_RC10_DISABLED_MSG)


@paper_router.get("/shadow/history")
def get_shadow_history(
    limit: int = 50,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get shadow decision consumption history / 获取影子决策消费历史"""
    if SHADOW_CONSUMER is None:
        return _paper_response({"history": [], "count": 0})
    history = SHADOW_CONSUMER.get_history(limit=min(limit, 200))
    return _paper_response({"history": history, "count": len(history)})


@paper_router.get("/shadow/decisions")
def get_shadow_decisions(
    limit: int = 50,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get shadow decisions from Rust engine / 從 Rust 引擎獲取影子決策"""
    # Shadow decisions are tracked via recent_intents in Rust snapshot
    # 影子決策通過 Rust 快照的 recent_intents 追蹤
    reader = get_rust_reader()
    if reader.is_engine_available("paper"):
        intents = reader.get_recent_intents(mode="paper") or []
        capped = intents[-min(limit, 200):]
        return _paper_response({"shadow_decisions": capped, "count": len(capped), "source": "rust_engine"})
    return _paper_response({"shadow_decisions": [], "count": 0, "source": "rust_engine"})


# ═══════════════════════════════════════════════════════════════════════════════
# Metrics Route / 性能指标路由
# ═══════════════════════════════════════════════════════════════════════════════

@paper_router.get("/metrics")
def get_metrics(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get performance metrics from Rust engine / 從 Rust 引擎獲取性能指標

    Returns full nested metrics (trade_metrics, drawdown_metrics, holding_period_metrics,
    sharpe_ratio) via compute_full_metrics, plus basic tick stats from the engine.
    返回完整嵌套指標（交易、回撤、持倉時間、夏普比率）+ 引擎 tick 統計。
    """
    rust = get_rust_reader()
    # 3E-ARCH: explicit engine="paper" / 必須明確指定 paper 引擎
    rust_state = rust.get_paper_state(engine="paper") if rust.is_engine_available("paper") else None
    if rust_state is None:
        return _paper_response({
            "available": False,
            "source": "rust_engine",
            "db_true_metrics": fetch_db_true_metrics(
                ["paper"],
                edge_engine_modes=["paper"],
                window_days=7,
            ),
        })

    # ── Build authoritative PnL from Rust snapshot ──────────────────────
    # Rust paper_state has flat keys (balance, peak_balance, total_realized_pnl,
    # total_fees, positions). Inject as nested "pnl" so compute_full_metrics
    # uses engine-authoritative values instead of reconstructing from DB fills
    # (which may span multiple engine sessions and produce wrong totals).
    # 從 Rust 快照構建權威 PnL，避免從跨 session 的 DB fills 重建導致錯誤。
    positions = rust_state.get("positions", [])
    total_unrealized = sum(p.get("unrealized_pnl", 0) for p in positions)
    rust_realized = rust_state.get("total_realized_pnl", 0.0)
    rust_fees = rust_state.get("total_fees", 0.0)
    rust_state["pnl"] = {
        "realized_pnl": rust_realized,
        "unrealized_pnl": total_unrealized,
        "total_fees_paid": rust_fees,
        "net_paper_pnl": rust_realized + total_unrealized - rust_fees,
    }

    # Full metrics via compute_full_metrics (trade_metrics, drawdown, sharpe, etc.)
    # 完整指標通過 compute_full_metrics 計算
    full = compute_full_metrics(rust_state, engine_mode="paper")

    # ── Override drawdown metrics with Rust-authoritative values ────────
    # The DB-derived balance series may span prior engine sessions and diverge
    # from the current engine state. Rust paper_state is the single source of
    # truth for current balance and peak balance.
    # DB 成交記錄可能跨越多次引擎重啟，餘額重建與當前引擎狀態不符。
    # Rust paper_state 是餘額/峰值的唯一權威來源。
    dm = full.get("drawdown_metrics", {})
    dm["current_balance"] = round(rust_state.get("balance", 0.0), 4)
    dm["peak_balance"] = round(rust_state.get("peak_balance", 0.0), 4)

    # Merge tick stats from engine / 合併引擎 tick 統計
    paper_snap = rust.get_snapshot(engine="paper") or {}
    stats = paper_snap.get("stats") or {}
    full["source"] = "rust_engine"
    full["total_ticks"] = stats.get("total_ticks", 0)
    full["total_intents"] = stats.get("total_intents", 0)
    # Ensure total_fills is available at top level for backward compatibility
    # 確保 total_fills 在頂層可用（向後兼容）
    full["total_fills"] = stats.get("total_fills", 0)
    full["total_stops"] = stats.get("total_stops", 0)
    full["db_true_metrics"] = fetch_db_true_metrics(["paper"], edge_engine_modes=["paper"], window_days=7)
    return _paper_response(full)


# ═══════════════════════════════════════════════════════════════════════════════
# AI Cost Tracking Route (via OpenClaw gateway) / AI 成本追踪路由
# ═══════════════════════════════════════════════════════════════════════════════

def _fetch_openclaw_usage_cost() -> dict[str, Any] | None:
    """
    Fetch AI usage cost from OpenClaw gateway CLI.
    从 OpenClaw 网关 CLI 获取 AI 使用成本。

    Returns parsed cost data or None if OpenClaw is not available.
    """
    try:
        result = subprocess.run(
            ["openclaw", "gateway", "usage-cost", "--json", "--days", "30"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        return None


@paper_router.get("/ai-cost")
def get_ai_cost(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get AI usage cost from OpenClaw gateway.
    从 OpenClaw 网关获取 AI 使用成本。

    Integrates OpenClaw's built-in token/cost tracking with our Net PnL system.
    """
    raw = _fetch_openclaw_usage_cost()
    if raw is None:
        return _paper_response({
            "available": False,
            "message": "OpenClaw gateway not reachable / OpenClaw 网关不可达",
            "today_cost": 0.0,
            "today_tokens": 0,
            "total_cost_30d": 0.0,
            "total_tokens_30d": 0,
            "daily": [],
        })

    # Extract today's cost
    daily = raw.get("daily", [])
    totals = raw.get("totals", {})

    today_entry = daily[-1] if daily else {}
    today_cost = today_entry.get("totalCost", 0.0)
    today_tokens = today_entry.get("totalTokens", 0)

    return _paper_response({
        "available": True,
        "source": "openclaw_gateway_usage_cost",
        "today_cost": round(today_cost, 6),
        "today_tokens": today_tokens,
        "total_cost_30d": round(totals.get("totalCost", 0.0), 6),
        "total_tokens_30d": totals.get("totalTokens", 0),
        "cost_breakdown": {
            "input_cost": round(totals.get("inputCost", 0.0), 6),
            "output_cost": round(totals.get("outputCost", 0.0), 6),
            "cache_read_cost": round(totals.get("cacheReadCost", 0.0), 6),
            "cache_write_cost": round(totals.get("cacheWriteCost", 0.0), 6),
        },
        "daily": daily[-7:],  # Last 7 days
    })


# ═══════════════════════════════════════════════════════════════════════════════
# Paper Config (3E-8) / Paper 配置
# ═══════════════════════════════════════════════════════════════════════════════

_PAPER_CONFIG_PATH = Path(
    os.environ.get("OPENCLAW_BASE_DIR", str(Path(__file__).resolve().parents[5]))
) / "settings" / "paper_config.toml"


@paper_router.get("/config")
def get_paper_config(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict:
    """
    GET /api/v1/paper/config
    Read paper engine configuration (initial_balance, etc.) (3E-8).
    讀取 paper 引擎配置。
    """
    try:
        if _PAPER_CONFIG_PATH.exists():
            import tomllib
            raw = _PAPER_CONFIG_PATH.read_text(encoding="utf-8")
            cfg = tomllib.loads(raw)
            return _paper_response({"config": cfg})
    except Exception as exc:
        logger.warning("Failed to read paper config: %s", exc)
    return _paper_response({"config": {"initial_balance_usdt": 10000.0}})


@paper_router.post("/config")
async def post_paper_config(
    request: Request,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict:
    """
    POST /api/v1/paper/config
    Update paper engine configuration (initial_balance_usdt) (3E-8).
    更新 paper 引擎配置。Takes effect on next session start.
    下次 session 啟動時生效。
    """
    _require_paper_config(actor)
    body = await request.json()
    initial_balance = body.get("initial_balance_usdt")
    if initial_balance is not None:
        try:
            initial_balance = float(initial_balance)
            if initial_balance < 100 or initial_balance > 10_000_000:
                raise HTTPException(status_code=400, detail="initial_balance_usdt must be 100~10,000,000")
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="invalid initial_balance_usdt")

    # Write TOML config / 寫入 TOML 配置
    try:
        _PAPER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Paper engine config (3E-8) / Paper 引擎配置\n"]
        if initial_balance is not None:
            lines.append(f"initial_balance_usdt = {initial_balance}\n")
        _PAPER_CONFIG_PATH.write_text("".join(lines), encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to write paper config: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to persist config")

    return _paper_response({
        "saved": True,
        "config": {"initial_balance_usdt": initial_balance or 10000.0},
    })
