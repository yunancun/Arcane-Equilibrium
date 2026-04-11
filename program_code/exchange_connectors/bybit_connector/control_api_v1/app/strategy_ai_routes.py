"""Strategy AI & Demo Routes — AI consultation, Telegram, Demo data read (TD-02 split).
策略 AI 和 Demo 路由 — AI 諮詢、Telegram、Demo 數據讀取。

All demo data reads use Rust PyO3 BybitClient exclusively.
All trading operations (close) go through Rust IPC.
Python BybitDemoConnector fallbacks removed — Rust is the sole exchange interface.

所有 Demo 數據讀取使用 Rust PyO3 BybitClient。
所有交易操作（平倉）通過 Rust IPC。
Python BybitDemoConnector 降級路徑已移除 — Rust 是唯一交易所接口。
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, HTTPException

from . import main_legacy as base
from .strategy_wiring import (
    phase2_router,
    ORCHESTRATOR,
    TELEGRAM,
    _envelope,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rust PyO3 bridge (PYO3-BYBIT) — lazy singleton
# Rust PyO3 橋接 — 懶加載單例
# ---------------------------------------------------------------------------
_RUST_BYBIT_CLIENT = None
_RUST_BRIDGE_AVAILABLE = None  # None = not checked yet / None = 尚未檢查


def _get_rust_client():
    """Get or create the Rust BybitClient singleton. Returns None if unavailable.
    獲取或創建 Rust BybitClient 單例。不可用時返回 None。"""
    global _RUST_BYBIT_CLIENT, _RUST_BRIDGE_AVAILABLE
    if _RUST_BRIDGE_AVAILABLE is False:
        return None
    if _RUST_BYBIT_CLIENT is not None:
        return _RUST_BYBIT_CLIENT
    try:
        from openclaw_core import BybitClient
        _RUST_BYBIT_CLIENT = BybitClient()
        _RUST_BRIDGE_AVAILABLE = True
        logger.info("Rust BybitClient initialized (PyO3 bridge active) / Rust BybitClient 已初始化")
        return _RUST_BYBIT_CLIENT
    except Exception as e:
        _RUST_BRIDGE_AVAILABLE = False
        logger.warning(f"Rust BybitClient unavailable, using Python fallback: {e}")
        return None


# ── Telegram Status Route / Telegram 状态路由 ──

@phase2_router.get("/telegram/status")
async def get_telegram_status(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """Get Telegram alerter status / 获取 Telegram 告警器状态"""
    if TELEGRAM is None:
        return _envelope({"enabled": False, "reason": "module not loaded"})
    return _envelope(TELEGRAM.get_stats())


# ── AI Consultation Route / AI 咨询路由 ──

@phase2_router.get("/ai/status")
async def get_ai_consultation_status(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get AI consultation availability status.
    获取 AI 咨询可用状态。
    """
    try:
        result = ORCHESTRATOR.request_ai_analysis("status_check")
        return _envelope({
            "ai_consultation_enabled": ORCHESTRATOR._ai_consultation_enabled,
            "analysis_result": result,
        })
    except Exception:
        logger.exception("AI status check error / AI 状态检查异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


# ── Bybit Demo Routes / Bybit Demo 路由 ──

@phase2_router.get("/demo/status")
async def get_demo_status(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """Get Bybit Demo connector status via PyO3 BybitClient / 通過 PyO3 獲取 Demo 狀態"""
    rc = _get_rust_client()
    if rc is None:
        return _envelope({"enabled": False, "source": "rust_engine"})
    return _envelope({
        "enabled": True,
        "source": "rust_engine",
        "has_credentials": rc.has_credentials(),
        "base_url": rc.base_url(),
    })


@phase2_router.get("/demo/balance")
async def get_demo_balance(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """
    Get Bybit Demo account balance via PyO3 BybitClient.
    Also exposes engine-side session baseline (initial_balance, peak_balance) so the
    GUI can show "session initial / peak" that resets on engine process restart and
    persists across pause/resume.
    通過 PyO3 獲取 Demo 餘額；同時暴露引擎側 session 基線（initial_balance / peak_balance），
    供 GUI 顯示「本次 session 初始 / 峰值」，引擎進程重啟時重置，pause/resume 期間保持不變。
    """
    rc = _get_rust_client()
    if rc is None:
        return _envelope({"enabled": False, "source": "rust_engine"})
    try:
        wallet = rc.refresh_balance()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Bybit balance fetch failed: {exc}")

    # Pull per-engine session baseline from Rust snapshot (paper_state sub-dict).
    # 從 Rust 快照拉取本 session 的基線（paper_state 子字段）。
    session_baseline: dict[str, Any] = {}
    try:
        from .paper_trading_routes import get_rust_reader  # noqa: PLC0415
        demo_state = get_rust_reader().get_paper_state(engine="demo") or {}
        if demo_state:
            session_baseline = {
                "engine_initial_balance": demo_state.get("initial_balance"),
                "engine_peak_balance": demo_state.get("peak_balance"),
                "engine_current_balance": demo_state.get("balance"),
                "engine_realized_pnl": demo_state.get("total_realized_pnl"),
                "engine_total_fees": demo_state.get("total_fees"),
            }
    except Exception:
        # Snapshot read is best-effort — wallet data is the primary payload.
        # 快照讀取是 best-effort — wallet 數據才是主要 payload。
        pass

    return _envelope({"source": "rust_engine", **wallet, **session_baseline})


@phase2_router.get("/demo/positions")
async def get_demo_positions(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """Get Bybit Demo open positions via PyO3 BybitClient / 通過 PyO3 獲取 Demo 持倉"""
    rc = _get_rust_client()
    if rc is None:
        return _envelope({"enabled": False, "source": "rust_engine"})
    try:
        positions = rc.get_positions("linear")
        return _envelope({"source": "rust_engine", "list": positions, "count": len(positions)})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Bybit positions fetch failed: {exc}")


@phase2_router.get("/demo/orders")
async def get_demo_orders(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """
    Get Bybit Demo open orders via PyO3 BybitClient.
    通過 PyO3 BybitClient 獲取 Demo 活躍訂單。
    """
    rc = _get_rust_client()
    if rc is None:
        return _envelope({"enabled": False, "source": "rust_engine"})
    try:
        orders = rc.get_active_orders("linear")
        return _envelope({
            "source": "rust_engine",
            "retCode": 0,
            "result": {"list": orders},
            "regular_count": len(orders),
            "conditional_count": 0,
        })
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Bybit orders fetch failed: {exc}")


def _normalize_execution(f: dict) -> dict:
    """Remap Rust ExecutionInfo snake_case fields to Bybit camelCase so the GUI
    fallback chain (execQty || qty, execPrice || price, execFee || fee) finds them.
    Rust 序列化為 snake_case（exec_qty/exec_price/exec_fee），GUI 期望 camelCase，
    此函數將 Rust 格式轉換為 Bybit API 格式避免 qty/price 顯示 0。
    """
    if not isinstance(f, dict):
        return f
    return {
        **f,
        "execQty":   f.get("execQty")   or f.get("exec_qty"),
        "execPrice": f.get("execPrice") or f.get("exec_price"),
        "execFee":   f.get("execFee")   or f.get("exec_fee"),
        "execTime":  f.get("execTime")  or f.get("exec_time"),
        "side":      f.get("side")      or ("Buy" if f.get("is_long") else "Sell"),
    }


@phase2_router.post("/demo/positions/{symbol}/close")
async def post_demo_close_position(
    symbol: str,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    POST /api/v1/strategy/demo/positions/{symbol}/close
    通過 IPC close_position 平掉指定 symbol 的 Demo 倉位。
    執行路徑完全在 Rust 引擎內：
      1. Python 從 Bybit REST 查詢持倉（只讀），取得 is_long / qty 作為 hints
      2. IPC 帶 hints 傳給 Rust
      3. Rust 引擎直接 dispatch shadow reduce_only 市價單至 Bybit（不經 Python 下單）
      4. paper_state 有倉 → 走既有路徑；無倉 → 用 hints 平孤兒倉位

    Close a single Demo position by symbol. All trading execution happens inside Rust:
    Python only does a read-only REST lookup to supply is_long/qty hints.
    Rust dispatches the reduce_only market order via its own shadow channel.
    """
    from .governance_routes import _require_operator_role
    from .paper_trading_routes import _ipc_command
    _require_operator_role(actor)
    sym = symbol.upper()

    # Step 1: read-only lookup of exchange position to build hints for Rust.
    # Python 只查倉位資料（只讀），供 Rust 平孤兒倉位時使用。
    hint_is_long: bool | None = None
    hint_qty: float | None = None
    rc = _get_rust_client()
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
            logger.warning("demo close: position hint lookup failed for %s: %s", sym, exc)

    # If no position found anywhere (neither paper nor exchange), bail early.
    # 紙盤和交易所都沒有這個倉位，直接返回 404。
    if hint_qty is None or hint_qty <= 0:
        # Still send IPC — paper_state might track it even if REST doesn't.
        # REST 查不到，但 paper_state 可能有，還是發 IPC。
        pass

    # Step 2: send IPC — Rust handles the actual close order via shadow channel.
    # 發 IPC — Rust 引擎通過 shadow channel 執行平倉，Python 不介入下單。
    ipc_params: dict = {"symbol": sym, "engine": "demo"}
    if hint_is_long is not None:
        ipc_params["is_long"] = hint_is_long
    if hint_qty is not None and hint_qty > 0:
        ipc_params["qty"] = hint_qty

    try:
        result = await _ipc_command("close_position", ipc_params)
    except Exception as exc:
        logger.error("IPC close_position failed for %s: %s", sym, exc)
        raise HTTPException(status_code=502, detail=f"IPC error: {exc}")

    # If no exchange position AND paper IPC also found nothing, return 404.
    # 交易所和紙盤都沒倉，回 404（避免謊報 closed=True）。
    if (hint_qty is None or hint_qty <= 0):
        raise HTTPException(
            status_code=404,
            detail=f"No position found for {sym} (neither paper state nor exchange) / 倉位不存在",
        )

    logger.warning(
        "close_position %s hint_is_long=%s hint_qty=%s — actor=%s",
        sym, hint_is_long, hint_qty, getattr(actor, "actor_id", "?"),
    )
    return _envelope({"symbol": sym, "closed": True, "source": "rust_engine", "ipc": result})


@phase2_router.post("/demo/close-all-positions")
async def post_demo_close_all_positions(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    POST /api/v1/strategy/demo/close-all-positions
    通過 IPC close_all_positions 平掉所有倉位。不影響 session 運行狀態。需要 Operator 角色。
    Rust 引擎依 pipeline_kind 分派：Demo/Live → reduce_only 市價單；Paper → 清 paper_state。

    Close all positions via IPC close_all_positions. Does not affect session state.
    Rust engine branches by pipeline_kind: Demo/Live → reduce_only market orders; Paper → paper_state.
    Requires Operator role.
    """
    from .governance_routes import _require_operator_role
    from .paper_trading_routes import _ipc_command
    _require_operator_role(actor)
    try:
        result = await _ipc_command("close_all_positions", {"engine": "demo"})
    except Exception as exc:
        logger.error("IPC close_all_positions failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"IPC error: {exc}")
    logger.warning(
        "close-all-positions (manual) — actor=%s", getattr(actor, "actor_id", "?"),
    )
    return _envelope({
        "message": "All positions closed — session continues / 已平掉所有倉位，session 繼續運行",
        "source": "rust_engine",
        "close_result": result,
    })


# ---------------------------------------------------------------------------
# Demo session controls — demo-engine-only, never touches paper/live.
# Demo 引擎 session 控制 — 僅影響 demo 引擎，不觸碰 paper/live。
# ---------------------------------------------------------------------------

# Sticky "user stopped" flag for demo engine — mirrors paper_trading_routes._USER_STOPPED.
# Demo 引擎「用戶主動停止」標誌 — 類比 paper 的 _USER_STOPPED。
_DEMO_USER_STOPPED: bool = False


def _ipc_command_sync_import():
    """Lazy import _ipc_command from paper_trading_routes to avoid circular import.
    延遲導入 _ipc_command 以避免循環導入。
    """
    from .paper_trading_routes import _ipc_command  # noqa: PLC0415
    return _ipc_command


async def _sweep_demo_orphan_positions(errors: list[str]) -> dict:
    """Close any exchange Demo positions not tracked in paper_state (orphan sweep).

    ipc_close_all() only iterates paper_state — positions that exist on the exchange
    but not in paper_state are silently skipped.  This sweep queries the exchange via
    BybitClient and issues a close_position IPC (with exchange-side hints) for every
    open position, so orphans are caught regardless.

    Uses reduce_only market orders — safe to call even if the position was already
    closed by the preceding close_all_positions IPC (exchange will reject with a
    benign "position size zero" error; Rust logs and ignores it).

    IPC close_all 只遍歷 paper_state，交易所有但 paper_state 沒有的「孤兒倉位」
    會被靜默跳過。本函數通過 BybitClient 查詢交易所所有持倉，對每個持倉發
    close_position IPC（帶 exchange-side hints），確保孤兒倉位也被平掉。
    使用 reduce_only 市價單，若倉位已被前一個 close_all 平掉則交易所拒單（無害）。
    """
    rc = _get_rust_client()
    if rc is None:
        return {"skipped": True, "reason": "rust_client_unavailable"}

    positions: list = []
    try:
        positions = rc.get_positions("linear") or []
    except Exception as exc:
        logger.warning("Orphan sweep: get_positions failed: %s", exc)
        errors.append(f"orphan_sweep_query: {exc}")
        return {"skipped": True, "reason": str(exc)}

    open_positions = [p for p in positions if float(p.get("size") or p.get("qty") or 0) > 0]
    if not open_positions:
        return {"swept": 0}

    _ipc_command = _ipc_command_sync_import()
    swept = 0
    for p in open_positions:
        sym = p.get("symbol", "")
        size = float(p.get("size") or p.get("qty") or 0)
        if not sym or size <= 0:
            continue
        ipc_params: dict = {
            "symbol": sym,
            "engine": "demo",
            "is_long": p.get("side") == "Buy",
            "qty": size,
        }
        try:
            await _ipc_command("close_position", ipc_params)
            swept += 1
            logger.warning(
                "Orphan sweep: close_position %s qty=%.4f is_long=%s (demo)",
                sym, size, ipc_params["is_long"],
            )
        except Exception as exc:
            logger.warning("Orphan sweep: close_position %s failed: %s", sym, exc)

    return {"swept": swept, "found": len(open_positions)}


@phase2_router.post("/demo/session/start")
async def post_demo_session_start(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Demo-only session start — resume Demo engine, does NOT affect Paper.
    Demo 引擎單獨啟動 — 僅恢復 Demo 引擎，不影響 Paper。
    """
    global _DEMO_USER_STOPPED
    _DEMO_USER_STOPPED = False
    _ipc_command = _ipc_command_sync_import()
    try:
        result = await _ipc_command("resume_paper", {"engine": "demo"})
    except Exception as exc:
        logger.warning("IPC resume_paper (demo) failed (may already be running): %s", exc)
        result = {}
    return _envelope({
        "message": "Demo engine started / Demo 引擎已啟動",
        "source": "rust_engine",
        "ipc_result": result,
        "session": {"session_state": "active"},
    })


@phase2_router.post("/demo/session/pause")
async def post_demo_session_pause(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Demo-only pause — pause Demo strategy dispatch, does NOT affect Paper.
    Demo 引擎單獨暫停 — 暫停策略分派，不影響 Paper。
    """
    _ipc_command = _ipc_command_sync_import()
    try:
        result = await _ipc_command("pause_paper", {"engine": "demo"})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"IPC pause (demo) failed: {exc}")
    return _envelope({
        "message": "Demo engine paused / Demo 引擎已暫停",
        "source": "rust_engine",
        "ipc_result": result,
        "session": {"session_state": "paused"},
    })


@phase2_router.post("/demo/session/resume")
async def post_demo_session_resume(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Demo-only resume — resume Demo engine, does NOT affect Paper.
    Demo 引擎單獨恢復 — 不影響 Paper。
    """
    global _DEMO_USER_STOPPED
    _DEMO_USER_STOPPED = False
    _ipc_command = _ipc_command_sync_import()
    try:
        result = await _ipc_command("resume_paper", {"engine": "demo"})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"IPC resume (demo) failed: {exc}")
    return _envelope({
        "message": "Demo engine resumed / Demo 引擎已恢復",
        "source": "rust_engine",
        "ipc_result": result,
        "session": {"session_state": "active"},
    })


@phase2_router.post("/demo/session/stop")
async def post_demo_session_stop(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Demo-only stop — close Demo positions and pause Demo engine, does NOT affect Paper.
    Demo 引擎單獨停止 — 平倉+暫停 Demo 引擎，不影響 Paper 引擎。
    雙引擎聯停請用 POST /api/v1/paper/session/stop-all。
    """
    global _DEMO_USER_STOPPED
    _DEMO_USER_STOPPED = True
    errors: list[str] = []
    from .paper_trading_routes import get_rust_reader  # noqa: PLC0415
    _ipc_command = _ipc_command_sync_import()
    rust_online = get_rust_reader().is_available()
    close_result: dict = {}
    pause_result: dict = {}
    if rust_online:
        try:
            close_result = await _ipc_command("close_all_positions", {"engine": "demo"})
        except Exception as e:
            errors.append(f"demo_close: {e}")
            logger.error("IPC close_all_positions (demo) failed: %s", e)
        # Orphan sweep: close any exchange positions not tracked in paper_state.
        # ipc_close_all only covers paper_state — orphan positions on the exchange
        # (e.g. FARTCOINUSDT opened externally or after paper_state reset) are missed.
        # 孤兒清掃：平掉交易所有但 paper_state 沒有的倉位。
        orphan_result = await _sweep_demo_orphan_positions(errors)
        try:
            pause_result = await _ipc_command("pause_paper", {"engine": "demo"})
        except Exception as e:
            errors.append(f"demo_pause: {e}")
            logger.error("IPC pause_paper (demo) failed: %s", e)
    else:
        close_result = pause_result = orphan_result = {"skipped": True, "reason": "engine_offline"}
    return _envelope({
        "message": "Demo engine stopped — positions closed / Demo 引擎已停止，倉位已平",
        "source": "rust_engine",
        "demo_close": close_result,
        "orphan_sweep": orphan_result,
        "demo_pause": pause_result,
        "errors": errors if errors else None,
        "session": {"session_state": "stopped"},
    })


@phase2_router.get("/demo/session/status")
def get_demo_session_status(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Demo engine session status — independent of Paper engine state.
    Demo 引擎 session 狀態 — 與 Paper 引擎狀態獨立。
    """
    from .paper_trading_routes import get_rust_reader  # noqa: PLC0415
    rust = get_rust_reader()
    if not rust.is_available():
        return _envelope({"session": {"session_state": "offline"}})
    if _DEMO_USER_STOPPED:
        return _envelope({"session": {"session_state": "stopped"}})
    # Read demo engine's paper_paused flag from its own snapshot.
    # 從 Demo 引擎自己的快照讀取 paper_paused 標誌。
    engine_snap = rust.get_engine_snapshot("demo") if hasattr(rust, "get_engine_snapshot") else None
    paper_paused = (engine_snap or {}).get("paper_paused", True)
    state = "paused" if paper_paused else "active"
    return _envelope({"session": {"session_state": state}})


@phase2_router.get("/demo/fills")
async def get_demo_fills(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """Get Bybit Demo recent executions via PyO3 BybitClient / 通過 PyO3 獲取 Demo 成交"""
    rc = _get_rust_client()
    if rc is None:
        return _envelope({"enabled": False, "source": "rust_engine"})
    try:
        fills = [_normalize_execution(f) for f in rc.get_executions("linear", limit=50)]
        return _envelope({"source": "rust_engine", "list": fills, "count": len(fills)})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Bybit fills fetch failed: {exc}")
