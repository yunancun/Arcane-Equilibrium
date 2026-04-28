"""Strategy AI & Demo Routes — AI consultation, Telegram, Demo data read (TD-02 split).
策略 AI 和 Demo 路由 — AI 諮詢、Telegram、Demo 數據讀取。

All demo data reads use httpx-based BybitClient (PYO3-ELIMINATE-1 Phase 2).
All trading operations (close) go through Rust IPC.
Python BybitDemoConnector fallbacks removed — pure-Python httpx BybitClient + Rust IPC.

所有 Demo 數據讀取使用 httpx 版 BybitClient（PYO3-ELIMINATE-1 Phase 2）。
所有交易操作（平倉）通過 Rust IPC。
Python BybitDemoConnector 降級路徑已移除 — 純 Python httpx BybitClient + Rust IPC。
"""
from __future__ import annotations

import asyncio
import logging
import os
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
# Bybit REST client (PYO3-ELIMINATE-1 Phase 2) — lazy singleton
# httpx-based Python client replacing former PyO3 bridge.
# Bybit REST 客戶端 — 已從 PyO3 橋接遷移為純 Python httpx 實作。
# ---------------------------------------------------------------------------
_BYBIT_CLIENT = None
_BYBIT_CLIENT_AVAILABLE = None  # None = not checked yet / None = 尚未檢查


def _get_rust_client():
    """Get or create the BybitClient singleton. Returns None if unavailable.
    Name `_get_rust_client` retained for call-site stability (grep-safe); the
    implementation is now pure-Python httpx (not Rust/PyO3).
    獲取或創建 BybitClient 單例。不可用時返回 None。函數名保留以降低改動面。"""
    global _BYBIT_CLIENT, _BYBIT_CLIENT_AVAILABLE
    if _BYBIT_CLIENT_AVAILABLE is False:
        return None
    if _BYBIT_CLIENT is not None:
        return _BYBIT_CLIENT
    try:
        from .bybit_rest_client import BybitClient
        _BYBIT_CLIENT = BybitClient()
        _BYBIT_CLIENT_AVAILABLE = True
        logger.info("BybitClient initialized (httpx) / BybitClient 已初始化（httpx）")
        return _BYBIT_CLIENT
    except Exception as e:
        _BYBIT_CLIENT_AVAILABLE = False
        logger.warning(f"BybitClient unavailable: {e}")
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
    """Get Bybit Demo connector status via httpx BybitClient / 通過 httpx BybitClient 獲取 Demo 狀態"""
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
    Get Bybit Demo account balance via httpx BybitClient.
    Also exposes engine-side session baseline (initial_balance, peak_balance) so the
    GUI can show "session initial / peak" that resets on engine process restart and
    persists across pause/resume.
    通過 httpx BybitClient 獲取 Demo 餘額；同時暴露引擎側 session 基線（initial_balance / peak_balance），
    供 GUI 顯示「本次 session 初始 / 峰值」，引擎進程重啟時重置，pause/resume 期間保持不變。
    """
    # BALANCE-REAL-1: Demo pipeline now refuses to start when Bybit wallet REST
    # fails at startup (no fallback 10000). Detect that case and surface an
    # explicit "disconnected" status so the GUI shows "N/A / 未連接" instead of
    # leftover stale snapshot or hardcoded defaults.
    # BALANCE-REAL-1：demo 管線啟動時 REST 失敗即拒絕啟動（不再 fallback 10000）。
    # 此處顯式偵測並返回 disconnected 狀態，GUI 應顯示「N/A / 未連接」而非
    # 殘留快照或硬編碼默認值。
    from .paper_trading_routes import get_rust_reader  # noqa: PLC0415
    reader = get_rust_reader()
    demo_pipeline_up = reader.is_engine_available("demo")
    if not demo_pipeline_up:
        return _envelope({
            "source": "rust_engine",
            "enabled": False,
            "pipeline_status": "disconnected",
            "pipeline_reason": "Bybit Demo wallet REST 未連接（引擎啟動時抓取失敗）/ "
                               "Bybit Demo wallet REST disconnected (REST fetch failed at engine startup)",
            "balance_display": "N/A",
            "balance": None,
            "engine_initial_balance": None,
            "engine_peak_balance": None,
            "engine_current_balance": None,
        })

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
        demo_state = reader.get_paper_state(engine="demo") or {}
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

    return _envelope({
        "source": "rust_engine",
        "pipeline_status": "connected",
        **wallet,
        **session_baseline,
    })


def _engine_owner_strategy_map(engine: str) -> dict[str, str]:
    """Build symbol → owner_strategy map from the engine's paper_state snapshot.
    Authoritative attribution lives in Rust paper_state.PaperPosition.owner_strategy
    (bybit_sync / orphan_adopted / orphan_frozen / DUST_FROZEN / strategy names).
    Returns {} on missing / stale snapshot — caller falls back to fills-derived map.

    從引擎 paper_state 快照建 symbol→owner_strategy 映射。權威歸屬源自 Rust
    paper_state.PaperPosition.owner_strategy（bybit_sync / orphan_adopted /
    orphan_frozen / DUST_FROZEN / 策略名）。快照缺失或過期時返回空 dict，
    呼叫端回退到 fills 反推映射。
    """
    try:
        from .paper_trading_routes import get_rust_reader  # noqa: PLC0415
        reader = get_rust_reader()
        # Gate on freshness — get_paper_state itself does not check 60s threshold,
        # so a stale snapshot could attach an obsolete owner_strategy after an
        # orphan-adopt handoff or close-and-reopen. Fall through to fills map when stale.
        # 守門新鮮度 — get_paper_state 本身不查 60s 閾值；快照過期時返回空，降級到 fills 映射。
        if not reader.is_engine_available(engine):
            return {}
        state = reader.get_paper_state(engine=engine)
    except Exception:
        return {}
    if not state:
        return {}
    positions = state.get("positions") or []
    mapping: dict[str, str] = {}
    if isinstance(positions, list):
        for p in positions:
            sym = p.get("symbol") if isinstance(p, dict) else None
            owner = p.get("owner_strategy") if isinstance(p, dict) else None
            if sym and owner:
                mapping[sym] = owner
    elif isinstance(positions, dict):
        for sym, p in positions.items():
            owner = p.get("owner_strategy") if isinstance(p, dict) else None
            if sym and owner:
                mapping[sym] = owner
    return mapping


# ---------------------------------------------------------------------------
# Synthetic owner labels — engine-assigned placeholders for untriaged / adopted /
# dust-frozen positions. Only these labels trigger dust-status enrichment below;
# real strategy names (ma_crossover / grid_trading / funding_arb / ...) stay lean.
# 合成 owner 標籤 — 引擎指派給未分流 / 已認領 / dust 凍結倉位的佔位符。
# 僅這些標籤觸發下方 dust-status 豐富化；真實策略名保持 lean payload。
# ---------------------------------------------------------------------------
_SYNTHETIC_OWNER_LABELS = frozenset({
    "bybit_sync",
    "orphan_adopted",
    "orphan_frozen",
})


def _dust_status(
    owner: str,
    est_notional: float | None,
    min_notional: float | None,
) -> str:
    """Derive `frozen_reason` string from synthetic owner + notional snapshot.

    - `orphan_frozen` + both values known + est < min → "dust_below_min_notional"
      (真正 dust 凍結：名義值低於交易所最小單，close 會被拒絕)
    - `orphan_frozen` + 任一值缺失 or est >= min → "frozen_pending"
      (凍結但原因未知/待 retriage；snapshot 仍讀為 frozen)
    - `bybit_sync` → "pending_triage"
      (啟動時交易所快照尚未分類)
    - `orphan_adopted` → "pending_edge"
      (Phase 2A 認領入 paper_state 等 edge 評估)
    - 其他（非合成 owner）→ ""（不附加）

    從合成 owner + 名義值快照推導 `frozen_reason` 字串。
    """
    if owner == "bybit_sync":
        return "pending_triage"
    if owner == "orphan_adopted":
        return "pending_edge"
    if owner == "orphan_frozen":
        # Dust 分支需要 est 和 min 都有值且 est < min；其他情況視為 pending。
        if (
            est_notional is not None
            and min_notional is not None
            and est_notional < min_notional
        ):
            return "dust_below_min_notional"
        return "frozen_pending"
    return ""


def _safe_float(value: Any) -> float | None:
    """Best-effort float conversion. Returns None on any failure.
    Bybit REST positions return stringified numbers; this normalizes them.
    Best-effort 轉 float；失敗返回 None。Bybit REST 倉位數值常為字串。
    """
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN guard / NaN 守衛
        return None
    return f


def _fetch_min_notional(symbol: str) -> float | None:
    """Lazy-fetch instrument min_notional from the httpx BybitClient.
    Returns None when client unavailable / symbol uncached / any exception.
    Callers MUST treat None as "dust gate not applicable" (same semantics as
    paper_state/owner_attribution.rs line 103).

    從 httpx BybitClient 懶查詢合約 min_notional。
    客戶端不可用 / 合約未緩存 / 任何異常 → 返回 None（與 Rust 端 "no dust gate" 語意對齊）。
    """
    rc = _get_rust_client()
    if rc is None:
        return None
    try:
        spec = rc.get_instrument(symbol)
    except Exception:
        return None
    if not isinstance(spec, dict):
        return None
    return _safe_float(spec.get("min_notional"))


def _attach_owner_strategy(positions: list, engine: str) -> list:
    """Enrich each Bybit position dict with `owner_strategy` from engine paper_state.
    For synthetic owners (bybit_sync / orphan_adopted / orphan_frozen) additionally
    attach `frozen_reason` + `min_notional` + `est_notional` so the GUI can explain
    WHY a position is held without an active strategy tag.
    No-op when position is not a dict or not found in the map (leaves as-is so the
    GUI's fills-derived fallback still runs). Real strategy names skip the dust
    enrichment path to keep the common payload lean.

    用引擎 paper_state 的 owner_strategy 豐富每筆 Bybit 倉位 dict。
    對合成 owner (bybit_sync / orphan_adopted / orphan_frozen) 額外附加
    `frozen_reason` + `min_notional` + `est_notional`，供 GUI 解釋該倉位為何
    持有卻無活躍策略標籤。非 dict 或映射未命中時跳過；真實策略名略過 dust
    enrichment 路徑以保持常態 payload lean。
    """
    if not isinstance(positions, list) or not positions:
        return positions
    owner_map = _engine_owner_strategy_map(engine)
    if not owner_map:
        return positions
    # Cache min_notional per symbol within one enrichment pass — get_instrument
    # is a cheap in-memory lookup, but avoid repeat calls when the same symbol
    # appears in multiple position rows (hedge-mode long/short).
    # 單次豐富化中按 symbol 緩存 min_notional；hedge mode 下同 symbol 可能有
    # 多筆（long/short）倉位，避免重複查詢。
    min_notional_cache: dict[str, float | None] = {}
    for p in positions:
        if not isinstance(p, dict):
            continue
        sym = p.get("symbol")
        owner = owner_map.get(sym) if sym else None
        if not owner:
            continue
        p["owner_strategy"] = owner
        # Only synthetic owners get dust-status enrichment; real strategy names stay lean.
        # 僅合成 owner 觸發 dust-status 豐富化；真實策略名保持 lean。
        if owner not in _SYNTHETIC_OWNER_LABELS:
            continue
        # Per-position try/except — enrichment must never break the endpoint.
        # 單倉位 try/except — 豐富化絕不可中斷 endpoint。
        try:
            # est_notional = qty × ref_price
            qty = _safe_float(p.get("size")) or _safe_float(p.get("qty"))
            ref_price = (
                _safe_float(p.get("markPrice"))
                or _safe_float(p.get("avgPrice"))
                or _safe_float(p.get("entry_price"))
            )
            est_notional: float | None = None
            if qty is not None and ref_price is not None and qty > 0.0 and ref_price > 0.0:
                est_notional = qty * ref_price

            if sym not in min_notional_cache:
                min_notional_cache[sym] = _fetch_min_notional(sym) if sym else None
            min_notional = min_notional_cache.get(sym)

            p["frozen_reason"] = _dust_status(owner, est_notional, min_notional)
            p["min_notional"] = min_notional
            p["est_notional"] = est_notional
        except Exception:
            # Fail-soft — leave whatever was attached so far; do not break endpoint.
            # Fail-soft — 保留已附加欄位，不中斷 endpoint。
            logger.exception(
                "owner_strategy dust enrichment failed for symbol=%s owner=%s",
                sym,
                owner,
            )
    return positions


@phase2_router.get("/demo/positions")
async def get_demo_positions(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """Get Bybit Demo open positions via httpx BybitClient / 通過 httpx BybitClient 獲取 Demo 持倉"""
    rc = _get_rust_client()
    if rc is None:
        return _envelope({"enabled": False, "source": "rust_engine"})
    try:
        positions = rc.get_positions("linear")
        positions = _attach_owner_strategy(positions, engine="demo")
        return _envelope({"source": "rust_engine", "list": positions, "count": len(positions)})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Bybit positions fetch failed: {exc}")


def _normalize_order(o: dict) -> dict:
    """Remap Rust OrderInfo snake_case → Bybit camelCase so the GUI filter
    (o.orderStatus / o.orderType / o.triggerPrice) finds them. Rust serializes
    snake_case; GUI compares against camelCase keys — without this remap every
    order gets filtered out of the "active" set.
    Rust 序列化 snake_case（order_status/order_type/trigger_price），GUI 過濾器
    用 camelCase 比對，未映射時所有訂單會被當作「非活躍」過濾掉。
    """
    if not isinstance(o, dict):
        return o
    return {
        **o,
        "orderId":       o.get("orderId")       or o.get("order_id"),
        "orderLinkId":   o.get("orderLinkId")   or o.get("order_link_id"),
        "orderStatus":   o.get("orderStatus")   or o.get("order_status"),
        "orderType":     o.get("orderType")     or o.get("order_type"),
        "triggerPrice":  o.get("triggerPrice")  or o.get("trigger_price"),
        "createdTime":   o.get("createdTime")   or o.get("created_time"),
        "updatedTime":   o.get("updatedTime")   or o.get("updated_time"),
    }


@phase2_router.get("/demo/orders")
async def get_demo_orders(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """
    Get Bybit Demo open orders via httpx BybitClient.
    通過 httpx BybitClient 獲取 Demo 活躍訂單。
    """
    rc = _get_rust_client()
    if rc is None:
        return _envelope({"enabled": False, "source": "rust_engine"})
    try:
        raw_orders = rc.get_active_orders("linear")
        orders = [_normalize_order(o) for o in raw_orders]
        conditional_count = sum(
            1 for o in orders
            if (o.get("orderStatus") or "").lower() == "untriggered"
        )
        regular_count = len(orders) - conditional_count
        return _envelope({
            "source": "rust_engine",
            "retCode": 0,
            "result": {"list": orders},
            "regular_count": regular_count,
            "conditional_count": conditional_count,
        })
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Bybit orders fetch failed: {exc}")


def _normalize_execution(f: dict) -> dict:
    """Remap Rust ExecutionInfo snake_case fields to Bybit camelCase so the GUI
    fallback chain (execQty || qty, execPrice || price, execFee || fee, closedPnl) finds them.
    Rust 序列化為 snake_case（exec_qty/exec_price/exec_fee/closed_pnl），GUI 期望 camelCase，
    此函數將 Rust 格式轉換為 Bybit API 格式避免 qty/price 顯示 0、PnL 欄顯示 —。
    """
    if not isinstance(f, dict):
        return f
    # closed_pnl is numeric (f64); use explicit None check — `or` falls through on 0.0
    # which is the common open-leg value, would lose the zero signal to the GUI.
    # closed_pnl 為 f64；0.0 是常見開倉腿值，不能用 `or` 否則開倉會落回 realized_pnl fallback。
    cp = f.get("closedPnl")
    if cp is None:
        cp = f.get("closed_pnl")
    return {
        **f,
        "execQty":   f.get("execQty")   or f.get("exec_qty"),
        "execPrice": f.get("execPrice") or f.get("exec_price"),
        "execFee":   f.get("execFee")   or f.get("exec_fee"),
        "execTime":  f.get("execTime")  or f.get("exec_time"),
        "side":      f.get("side")      or ("Buy" if f.get("is_long") else "Sell"),
        "closedPnl": cp,
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
    errors: list[str] = []
    try:
        result = await _ipc_command("close_all_positions", {"engine": "demo"})
    except Exception as exc:
        logger.error("IPC close_all_positions failed: %s", exc)
        errors.append(f"ipc_close_all: {exc}")
        result = {"error": str(exc)}
    # Orphan sweep: close exchange positions not tracked in paper_state.
    # IPC close_all only iterates paper_state — orphan positions (e.g. opened
    # externally or after paper_state reset) are silently skipped.
    # 孤兒清掃：IPC close_all 只遍歷 paper_state，交易所有但 paper_state
    # 沒有的倉位會被跳過。此處補掃確保全部平掉。
    orphan_result = await _sweep_demo_orphan_positions(errors)
    logger.warning(
        "close-all-positions (manual) — actor=%s", getattr(actor, "actor_id", "?"),
    )
    return _envelope({
        "message": "All positions closed — session continues / 已平掉所有倉位，session 繼續運行",
        "source": "rust_engine",
        "close_result": result,
        "orphan_sweep": orphan_result,
        "errors": errors if errors else None,
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


# ---------------------------------------------------------------------------
# Stop-path order cancellation + verification
# 停止路徑掛單取消 + 確認清乾淨
#
# 為什麼分兩步：先「全帳戶取消掛單」再「平倉」。否則平倉觸發前若有 reduce-only TP/SL
# 條件單同步活躍，可能造成競態（一邊平倉、另一邊條件單觸發）。先取消可消除此風險。
# Why two phases: cancel-all FIRST, then close positions. Otherwise reduce-only
# TP/SL conditional orders may race the close-position market orders.
# ---------------------------------------------------------------------------


def _sweep_orphan_orders(rc: Any, env_label: str, errors: list[str]) -> dict:
    """Cancel **all** USDT linear orders in one REST call (settleCoin scope).

    Not bounded to the strategy's active symbol set — calls Bybit's
    /v5/order/cancel-all with settleCoin=USDT so every pending limit /
    conditional / TP-SL on the account is cleared. Used by Stop pipelines
    (live + demo) to ensure no order survives stop.

    一次 REST 清掃 settleCoin=USDT 範圍內所有掛單，**不**依策略 symbol 集合迭代 —
    避免「停止後 25 個 symbol 外仍有殘留掛單」的盲區。

    Returns {cancelled, found_unknown_count, sample_symbols} or
    {skipped, reason} on failure.
    """
    if rc is None:
        return {"skipped": True, "reason": "rust_client_unavailable"}
    # Snapshot active orders pre-cancel for audit trail / 快照取消前的活躍掛單供審計
    pre_orders: list = []
    try:
        pre_orders = rc.get_active_orders("linear") or []
    except Exception as exc:
        # Query failure is non-fatal — still attempt the cancel-all call.
        # 查詢失敗不致命 — 仍嘗試 cancel-all。
        logger.warning("%s order sweep: get_active_orders failed: %s", env_label, exc)
        errors.append(f"order_sweep_query_{env_label}: {exc}")
    try:
        cancelled = rc.cancel_all_orders("linear", settle_coin="USDT")
    except Exception as exc:
        logger.warning("%s order sweep: cancel-all failed: %s", env_label, exc)
        errors.append(f"order_sweep_{env_label}: {exc}")
        return {"skipped": True, "reason": str(exc), "found": len(pre_orders)}
    cancelled_n = len(cancelled) if isinstance(cancelled, list) else 0
    found_n = len(pre_orders)
    sample_symbols = sorted({
        str(o.get("symbol") or "")
        for o in pre_orders
        if isinstance(o, dict) and o.get("symbol")
    })
    logger.warning(
        "%s order sweep: cancel-all cleared %d orders (found %d active pre-cancel; symbols=%s)",
        env_label, cancelled_n, found_n, sample_symbols[:10],
    )
    return {
        "cancelled": cancelled_n,
        "found": found_n,
        "symbols": sample_symbols,
    }


async def _sweep_demo_orphan_orders(errors: list[str]) -> dict:
    """Demo-side wrapper around _sweep_orphan_orders using demo BybitClient.
    Demo 側 wrapper，用 demo BybitClient 走全帳戶 cancel-all。
    """
    return _sweep_orphan_orders(_get_rust_client(), "demo", errors)


def _verify_clean_max_attempts() -> int:
    """Max polling attempts before declaring residual state. Default 30 (~30s).
    最大輪詢次數，預設 30 (~30s)。env OPENCLAW_STOP_VERIFY_MAX_ATTEMPTS 可覆寫。
    """
    try:
        return max(1, int(os.environ.get("OPENCLAW_STOP_VERIFY_MAX_ATTEMPTS", "30")))
    except Exception:
        return 30


def _verify_clean_interval_sec() -> float:
    """Polling interval in seconds. Default 1.0s.
    輪詢間隔，預設 1.0s。env OPENCLAW_STOP_VERIFY_INTERVAL_SEC 可覆寫。
    """
    try:
        return max(0.1, float(os.environ.get("OPENCLAW_STOP_VERIFY_INTERVAL_SEC", "1.0")))
    except Exception:
        return 1.0


async def _verify_account_clean(
    rc: Any,
    *,
    env_label: str,
    max_attempts: int | None = None,
    interval_sec: float | None = None,
) -> dict:
    """Poll Bybit until positions=0 AND open_orders=0, or max attempts.

    輪詢 Bybit REST 直到「持倉=0 且掛單=0」或達到上限。**重點：上限是時間上限**，
    不是 symbol 數上限 — 任何 symbol 的殘留都會讓本輪 verify 失敗。

    Returns:
        {"clean": True, "attempts": N, "elapsed_sec": ...}
        OR {"clean": False, "attempts": max, "residual_positions": N,
            "residual_orders": N, "residual_position_symbols": [...],
            "residual_order_symbols": [...], "elapsed_sec": ...}
    """
    if rc is None:
        return {"clean": False, "skipped": True, "reason": "rust_client_unavailable"}
    attempts_cap = max_attempts if max_attempts is not None else _verify_clean_max_attempts()
    interval = interval_sec if interval_sec is not None else _verify_clean_interval_sec()
    last_positions: list = []
    last_orders: list = []
    started = asyncio.get_event_loop().time()
    for attempt in range(1, attempts_cap + 1):
        try:
            positions = rc.get_positions("linear") or []
            orders = rc.get_active_orders("linear") or []
        except Exception as exc:
            logger.warning(
                "%s verify poll attempt %d exception: %s", env_label, attempt, exc,
            )
            await asyncio.sleep(interval)
            continue
        last_positions = [
            p for p in positions
            if isinstance(p, dict)
            and float(p.get("size") or p.get("qty") or 0) > 0
        ]
        last_orders = [o for o in orders if isinstance(o, dict)]
        if not last_positions and not last_orders:
            elapsed = asyncio.get_event_loop().time() - started
            logger.warning(
                "%s verify CLEAN at attempt %d (elapsed=%.2fs)",
                env_label, attempt, elapsed,
            )
            return {
                "clean": True,
                "attempts": attempt,
                "elapsed_sec": round(elapsed, 2),
            }
        # Wait one tick before re-querying / 下一輪前等待
        if attempt < attempts_cap:
            await asyncio.sleep(interval)
    elapsed = asyncio.get_event_loop().time() - started
    pos_syms = sorted({
        str(p.get("symbol") or "") for p in last_positions if p.get("symbol")
    })
    ord_syms = sorted({
        str(o.get("symbol") or "") for o in last_orders if o.get("symbol")
    })
    logger.error(
        "%s verify NOT-CLEAN after %d attempts (%.2fs): residual_positions=%d residual_orders=%d",
        env_label, attempts_cap, elapsed, len(last_positions), len(last_orders),
    )
    return {
        "clean": False,
        "attempts": attempts_cap,
        "elapsed_sec": round(elapsed, 2),
        "residual_positions": len(last_positions),
        "residual_orders": len(last_orders),
        "residual_position_symbols": pos_syms,
        "residual_order_symbols": ord_syms,
    }


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
    # BALANCE-REAL-1: Distinguish "Rust process up but demo pipeline refused
    # to start" (REST wallet failed) from a normal paused state. UI shows N/A.
    # BALANCE-REAL-1：區分「Rust 進程在跑但 demo 管線拒絕啟動」（REST 失敗）
    # 與普通 paused — 前者 GUI 顯示 N/A + 未連接。
    if not rust.is_engine_available("demo"):
        return _envelope({"session": {
            "session_state": "disconnected",
            "session_halt_reason": "Bybit Demo wallet REST 未連接 / wallet REST disconnected",
        }})
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
    """Get Demo fill history. DB primary (has realized_pnl) / Bybit API fallback.
    獲取 Demo 成交歷史。DB 為主（帶 realized_pnl）/ Bybit API 備援。"""
    # DB path — same pattern as paper fills; carries engine-calculated realized_pnl.
    # DB 路徑 — 與 paper fills 相同模式；帶引擎計算的 realized_pnl。
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
                ("demo", 50),
            )
            rows = cur.fetchall()
            fills = []
            for ts, symbol, side, qty, price, fee, rpnl, strategy in rows:
                ts_ms = int(ts.timestamp() * 1000) if ts is not None else 0
                sym = symbol or ""
                cat = "inverse" if sym.endswith("USD") and not sym.endswith("USDT") else "linear"
                fills.append({
                    "exec_time": str(ts_ms),
                    "symbol": sym,
                    "side": side or "",
                    "qty": float(qty) if qty is not None else 0.0,
                    "price": float(price) if price is not None else 0.0,
                    "fee": float(fee) if fee is not None else 0.0,
                    "realized_pnl": float(rpnl) if rpnl is not None else 0.0,
                    "strategy": strategy or "",
                    "category": cat,
                })
            return _envelope({"list": fills, "count": len(fills), "source": "pg_trading_fills"})
        except Exception as e:
            logger.warning("PG demo fills query failed, falling back to Bybit API: %s", e)
        finally:
            try:
                db_pool.put_conn(conn)
            except Exception:
                pass
    # Fallback: Bybit API via httpx BybitClient (closedPnl from exchange).
    # 備援：通過 httpx BybitClient 調 Bybit API（closedPnl 來自交易所）。
    rc = _get_rust_client()
    if rc is None:
        return _envelope({"enabled": False, "source": "rust_engine"})
    try:
        fills = [_normalize_execution(f) for f in rc.get_executions("linear", limit=50)]
        return _envelope({"source": "rust_engine", "list": fills, "count": len(fills)})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Bybit fills fetch failed: {exc}")
