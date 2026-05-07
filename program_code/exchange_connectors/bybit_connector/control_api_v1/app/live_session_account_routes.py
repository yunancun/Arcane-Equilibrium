from __future__ import annotations

"""
Live Session Account Routes — balance / positions / orders / fills / close handlers
實盤 Session 帳戶路由 — 餘額 / 倉位 / 掛單 / 成交 / 平倉處理器

MODULE_NOTE (中文):
  本檔由 G5-02 從 ``live_session_routes.py`` 拆出（§九 1200 行硬上限）。
  純結構搬遷 — 0 邏輯變更。所有 handler 行為、路由路徑、Depends 守衛、
  fallback 路徑（DB → Bybit API → engine snapshot）byte-for-byte 一致。

  端點：
  - GET  /api/v1/live/balance                       — 餘額（DB → API → engine）
  - GET  /api/v1/live/positions                     — 倉位
  - GET  /api/v1/live/orders                        — 掛單
  - GET  /api/v1/live/fills                         — 成交（DB primary）
  - POST /api/v1/live/positions/{symbol}/close      — 單倉平倉（IPC + REST 降級）
  - POST /api/v1/live/close-all-positions           — 全倉平倉（IPC + REST 降級）
  - GET  /api/v1/live/metrics                       — 性能指標

  關鍵設計（保留 monkey-patch 行為）：
    所有對 ``live_session_routes`` 模組屬性（_get_rust_client_safe / _ipc_command /
    _is_live_channel_unavailable_error / _rest_close_position_reduce_only /
    _sweep_live_orphan_positions / _live_response 等）的引用走 ``core.<name>``，
    不走 ``from .live_session_routes import <name>``。原因：
    tests/test_live_gate_fallback.py 用 ``monkeypatch.setattr(lsr, ...)`` 重綁
    模組屬性；如果 sibling 用 from-import 捕獲早期函數引用，monkeypatch 失效。

MODULE_NOTE (English):
  Split out of ``live_session_routes.py`` by G5-02 (§九 1200-line hard cap).
  Pure structural move — zero logic changes. Handlers, routes, Depends,
  fallback paths (DB → Bybit API → engine snapshot) are byte-for-byte identical.

  Module-attribute lookup matters: all references to ``live_session_routes``
  internals go via ``core.<name>`` so test monkeypatches still bind correctly.
"""

import logging
from typing import Any

from fastapi import Depends, HTTPException, Query

from . import live_session_routes as core
from . import main_legacy as base
from .ipc_state_reader import get_rust_reader

logger = logging.getLogger(__name__)


def _require_live_trade(actor: Any) -> None:
    """Batch B live close gate: Operator + live trade scope."""
    base.require_scope_and_operator(actor, "live:trade")


# ═══════════════════════════════════════════════════════════════════════════════
# F5/A1 — Phantom-View Guard
# F5/A1 — 幽靈視圖守衛
# ═══════════════════════════════════════════════════════════════════════════════
def _phantom_view_guard() -> dict | None:
    """
    Refuse to expose Live account data when the Live slot is structurally
    unconfigured AND the engine is not in Live mode. Returns the response
    payload that should be returned by the caller (or None to proceed).

    Two LIVE-Tab states this protects against (per A3 audit, 2026-04-26):
      a) Live slot api_key empty → ``_get_rust_client_safe()`` falls back to the
         shared demo BybitClient (api-demo.bybit.com), which would otherwise
         render real demo wallet/positions inside the purple "REAL FUNDS" view.
      b) Live slot configured (mainnet OR live_demo) but Rust ``live`` engine
         absent → ``_get_live_engine_kind()`` reports "demo"/"paper"; the
         exchange data is technically real for that slot but it is NOT what
         the Live engine is doing. Frontend must show a non-misleading view.

    LiveDemo (slot api_key + bybit_endpoint=demo + Rust live engine running)
    is NOT a phantom view: the Live pipeline genuinely uses api-demo as the
    test bed (per CLAUDE.md memory `feedback_live_no_degradation_by_endpoint`).
    We accept that case and let the frontend label it "LiveDemo · api-demo
    endpoint" with an orange/silver theme.

    本守衛拒絕在以下情境下暴露 Live 帳戶資料：
      a) Live 槽 api_key 為空 → 客戶端回退到共享 demo client（api-demo.bybit.com），
         否則紫色「真實資金」面板會渲染出 demo 錢包/倉位。
      b) Live 槽已配置但 Rust ``live`` 引擎缺席 → engine_kind 退到 demo/paper；
         交易所資料對該槽是真實的，但**並非 Live engine 正在做的事**，前端需顯示
         不誤導視圖。

    LiveDemo（槽 api_key + endpoint=demo + Rust live 引擎運行）**不是**幽靈視圖：
    Live 管線確實在 api-demo 跑 live code path（per CLAUDE.md memory）。此情況
    放行，前端用橙/銀主題標 "LiveDemo · api-demo endpoint"。

    Returns:
      None — proceed with normal handler logic
      dict — caller should ``return`` this payload directly (HTTP 200 envelope
             carrying ``actual_*`` markers, ``error``, and empty data so the
             frontend reliably swaps to the warning view)

    Why 200 instead of HTTPException(422): the existing GUI relies on
    ``ocApi`` envelope unwrap and shows a generic toast on non-200; we want
    the page-load flow to read the payload markers and swap views, so we
    return a structured envelope with ``error`` key + ``actual_engine_kind``
    + ``actual_endpoint``. Tests assert presence of these keys on the payload.

    為何回 200 而非 422：現有 GUI 依賴 ocApi unwrap，非 200 會 toast 通用錯誤；
    我們要讓 page-load 流程讀取 payload markers 來 swap 視圖，所以回結構化 envelope
    含 ``error`` + ``actual_engine_kind`` + ``actual_endpoint``。Tests 斷言 keys 存在。
    """
    actual_engine_kind = core._get_live_engine_kind()
    actual_endpoint = core._resolve_live_endpoint_label()

    # Phantom view detected: engine not Live AND slot unconfigured
    # 幽靈視圖：引擎非 live 且槽未配置
    if actual_engine_kind != "live" and actual_endpoint == "unconfigured":
        return core._live_response({
            "available": False,
            "error": "live_slot_not_configured",
            "error_zh": "Live 槽未配置；GUI 拒絕顯示 demo data 偽裝 live",
            "error_en": "Live slot not configured; GUI refuses to render demo data as live",
            "list": [],
            "positions": [],
            "count": 0,
            "actual_engine_kind": actual_engine_kind,
            "actual_endpoint": actual_endpoint,
        })
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# F5-RETURN/Issue-1 (HIGH) — Phantom-view server-side WRITE guard
# F5-RETURN/Issue-1（HIGH）— 寫入端 server-side 幽靈視圖守衛
# ═══════════════════════════════════════════════════════════════════════════════
def _phantom_view_guard_write() -> None:
    """
    Refuse Live WRITE operations (close-position / close-all-positions) when
    the Live slot is structurally unconfigured AND the engine is not Live.

    Why a separate sibling helper instead of reusing ``_phantom_view_guard``:
      - Read endpoints return a 200 envelope with ``error`` markers because the
        existing GUI relies on ocApi unwrap and shows a generic toast on non-200
        — but it also reads the payload to swap views. Read path = soft refusal.
      - Write endpoints have a different threat model (per E2 review 2026-04-26):
        a curl POST that bypasses the client-side guard would, without this
        guard, take the IPC path → IPC fails (live pipeline absent) → fall back
        to ``_rest_close_position_reduce_only`` / ``_sweep_live_orphan_positions``
        which use the demo client and would CLOSE DEMO POSITIONS. We must hard
        refuse with HTTP 422 (semantic: "request well-formed but the live engine
        prerequisite is unmet"). 422 conveys actionable signal to curl/scripts;
        the GUI's ocApi will surface it as an error.

    LiveDemo (engine=='live' AND endpoint=='live_demo') is a legitimate Live
    operating mode (per CLAUDE.md memory ``feedback_live_no_degradation_by_endpoint``):
    the Live pipeline genuinely runs against api-demo with full Live-grade
    authorization (5-gate). It MUST be allowed through this guard. Visual
    differentiation (orange theme) happens in the frontend only.

    本守衛拒絕在 Live 槽未配置且引擎非 live 時執行 Live 寫操作（單倉平倉 /
    全平倉）。為何獨立 sibling 而非重用 ``_phantom_view_guard``：
      - 讀端點回 200 envelope 帶 ``error`` 標記，GUI 依 ocApi unwrap 然後讀
        payload 切換視圖 — 軟拒絕。
      - 寫端點不同：curl POST 繞過前端守衛後，若無此 guard，IPC 失敗 → 降級
        REST close path 使用 demo client → 誤平 demo 倉位。必須硬拒 HTTP 422
        （請求格式合法但 live 引擎前置條件未滿足），對 curl/script 提供 actionable
        signal；GUI 的 ocApi 會以 error 形式呈現。

    LiveDemo（engine=='live' 且 endpoint=='live_demo'）放行 — 該模式是合法的
    Live 運行模式，5-gate 授權按 Live 嚴格標準（per memory），視覺差異（橙色
    主題）由前端處理。

    Raises:
      HTTPException(422): live engine not configured / not running. Detail
        envelope carries ``error`` / ``actual_engine_kind`` / ``actual_endpoint``
        + bilingual ``message``. caller does not need to handle return value.

    Returns:
      None — proceed with the actual close handler.
    """
    actual_engine_kind = core._get_live_engine_kind()
    actual_endpoint = core._resolve_live_endpoint_label()

    # Block iff engine != live AND slot unconfigured (mirror read-side guard
    # exact condition, so test fixtures stay aligned and there is no asymmetry
    # that would let a Mainnet-slot configured demo engine accidentally pass).
    # 條件鏡像讀端 guard，避免不對稱讓「Mainnet 槽配置 + demo 引擎」意外通過。
    if actual_engine_kind != "live" and actual_endpoint == "unconfigured":
        raise HTTPException(
            status_code=422,
            detail={
                "error": "live_engine_not_configured",
                "actual_engine_kind": actual_engine_kind,
                "actual_endpoint": actual_endpoint,
                "message": (
                    "Live engine not running or unconfigured. Refusing write "
                    "operation to prevent accidentally closing demo positions. "
                    "/ Live 引擎未運行或未配置，拒絕寫操作，避免誤平 demo 倉位。"
                ),
            },
        )
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Live account data — balance / positions / orders
# 實盤帳戶數據端點 — 餘額 / 倉位 / 掛單
#
# Primary: httpx BybitClient (real exchange data, same client as demo).
# Fallback: IPC get_paper_state (engine internal state).
# 主路徑：httpx BybitClient（真實交易所數據，同 demo 使用相同客戶端）。
# 降級：IPC get_paper_state（引擎內部狀態）。
# ═══════════════════════════════════════════════════════════════════════════════


@core.live_router.get("/balance")
async def get_live_balance(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    GET /api/v1/live/balance
    Primary: real Bybit account balance via httpx BybitClient (demo or live key).
    Fallback: engine internal balance + bybit_sync_balance.

    主路徑：httpx BybitClient 獲取真實 Bybit 帳戶餘額（demo 或 live key 均可）。
    降級：引擎內部餘額 + bybit_sync_balance。
    """
    # F5/A1: refuse to render demo wallet under the Live "REAL FUNDS" view when
    #        the Live slot is unconfigured and engine_kind is not 'live'.
    # F5/A1：Live 槽未配置且引擎非 live 時拒絕用 demo wallet 偽裝「真實資金」視圖。
    guard = _phantom_view_guard()
    if guard is not None:
        return guard

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

    rc = core._get_rust_client_safe()
    if rc is not None:
        try:
            wallet = rc.refresh_balance()
            return core._live_response({"source": "rust_engine", **wallet, **session_baseline})
        except Exception as e:
            logger.warning("Rust balance fetch failed for live endpoint: %s", e)
    # Fallback: engine internal state / 降級：引擎內部狀態
    try:
        state = await core._ipc_command("get_paper_state", {"engine": "live"})
    except HTTPException:
        return core._live_response({"available": False, "source": "engine_unavailable"})
    sync_bal = state.get("bybit_sync_balance")
    return core._live_response({
        "balance": sync_bal if sync_bal is not None else state.get("balance"),
        "peak_balance": state.get("peak_balance"),
        "bybit_sync_balance": sync_bal,
        "engine_balance": state.get("balance"),
        "source": "bybit_sync" if sync_bal is not None else "engine_internal",
        **session_baseline,
    })


@core.live_router.get("/positions")
async def get_live_positions(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    GET /api/v1/live/positions
    Primary: real Bybit positions via httpx BybitClient.
    Fallback: engine-tracked positions (internal state).

    主路徑：httpx BybitClient 獲取真實 Bybit 倉位。
    降級：引擎追蹤倉位（內部狀態）。
    """
    # F5/A1 phantom-view guard / F5/A1 幽靈視圖守衛
    guard = _phantom_view_guard()
    if guard is not None:
        return guard

    rc = core._get_rust_client_safe()
    if rc is not None:
        try:
            positions = rc.get_positions("linear")
            from .strategy_ai_routes import _attach_owner_strategy  # noqa: PLC0415
            positions = _attach_owner_strategy(positions, engine="live")
            return core._live_response({
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
        state = await core._ipc_command("get_paper_state", {"engine": "live"})
    except HTTPException:
        return core._live_response({"positions": [], "count": 0, "available": False})
    positions = state.get("positions", [])
    return core._live_response({"positions": positions, "count": len(positions), "source": "engine_state"})


@core.live_router.get("/orders")
async def get_live_orders(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    GET /api/v1/live/orders
    Primary: real Bybit active orders via httpx BybitClient.
    Fallback: pending-close orders derived from engine position state.

    主路徑：httpx BybitClient 獲取真實 Bybit 掛單。
    降級：從引擎倉位狀態派生 pending_close 訂單。
    """
    # F5/A1 phantom-view guard / F5/A1 幽靈視圖守衛
    guard = _phantom_view_guard()
    if guard is not None:
        return guard

    rc = core._get_rust_client_safe()
    if rc is not None:
        try:
            orders = rc.get_active_orders("linear")
            return core._live_response({
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
        state = await core._ipc_command("get_paper_state", {"engine": "live"})
    except HTTPException:
        return core._live_response({"list": [], "count": 0, "available": False})
    positions: list = state.get("positions", [])
    pending = [p for p in positions if p.get("pending_close") or p.get("stop_order_id")]
    return core._live_response({
        "list": pending,
        "count": len(pending),
        "regular_count": 0,
        "conditional_count": len(pending),
        "source": "engine_state",
    })


@core.live_router.get("/fills")
async def get_live_fills(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    side: str | None = Query(None),
    actor: Any = Depends(base.current_actor),
) -> dict:
    """
    GET /api/v1/live/fills
    DB primary (realized_pnl) → Bybit API fallback → engine snapshot fallback.
    DB 為主（帶 realized_pnl）→ Bybit API 備援 → 引擎快照備援。
    """
    # F5/A1 phantom-view guard / F5/A1 幽靈視圖守衛
    guard = _phantom_view_guard()
    if guard is not None:
        return guard

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
            # W1-T3 (PA 2026-04-29 strategy_name attribution cleanup §1.2):
            # SELECT additionally returns ``exit_reason`` (V033 column, nullable).
            # Once W1-T2 normalises close path emit, ``strategy_name`` holds the
            # entry-strategy enum and ``exit_reason`` carries the dynamic trace.
            # Historical rows pre-V033 keep ``exit_reason=NULL`` and the legacy
            # ``strategy_name`` shape; GUI renders both side by side.
            # W1-T3 同步 demo bucket：fills SELECT 多回 exit_reason，UI 渲染
            # ``strategy + (exit_reason ? ' (' + exit_reason + ')' : '')``。
            safe_side = side if side in {"Buy", "Sell"} else None
            where = "engine_mode IN (%s, %s)"
            params: list[Any] = ["live", "live_demo"]
            if safe_side:
                where += " AND side = %s"
                params.append(safe_side)
            params.extend([limit + 1, offset])
            cur.execute(
                "SELECT ts, symbol, side, qty, price, fee, realized_pnl, strategy_name, exit_reason "
                f"FROM trading.fills WHERE {where} ORDER BY ts DESC LIMIT %s OFFSET %s",
                tuple(params),
            )
            rows = cur.fetchall()
            has_more = len(rows) > limit
            rows = rows[:limit]
            fills = []
            for ts, symbol, side, qty, price, fee, rpnl, strategy, exit_reason in rows:
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
                    "exit_reason": exit_reason if exit_reason else None,
                    "category": cat,
                })
            return core._live_response({
                "list": fills,
                "count": len(fills),
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
                "next_offset": offset + len(fills) if has_more else None,
                "source": "pg_trading_fills",
            })
        except Exception as e:
            logger.warning("PG live fills query failed, falling back to Bybit API: %s", e)
        finally:
            try:
                db_pool.put_conn(conn)
            except Exception:
                pass
    # Bybit API via httpx BybitClient (closedPnl from exchange).
    # Bybit API（closedPnl 來自交易所）。
    rc = core._get_rust_client_safe()
    if rc is not None:
        try:
            from .strategy_ai_routes import _normalize_execution
            safe_side = side if side in {"Buy", "Sell"} else None
            fetch_limit = min(max(limit + offset + 1, limit), 100)
            raw = [_normalize_execution(f) for f in rc.get_executions("linear", limit=fetch_limit)]
            if safe_side:
                raw = [f for f in raw if f.get("side") == safe_side]
            fills = raw[offset:offset + limit]
            return core._live_response({
                "source": "rust_engine",
                "list": fills,
                "count": len(fills),
                "limit": limit,
                "offset": offset,
                "has_more": len(raw) > offset + limit,
                "next_offset": offset + len(fills) if len(raw) > offset + limit else None,
            })
        except Exception as e:
            logger.warning("Rust fills fetch failed for live endpoint: %s", e)
    # Fallback: engine recent fills (3E-ARCH snapshot, now carries realized_pnl).
    # 降級：引擎快照 recent_fills（現帶 realized_pnl）。
    rust = get_rust_reader()
    if rust.is_engine_available("live"):
        try:
            recent = rust.get_recent_fills(mode="live") or []
            safe_side = side if side in {"Buy", "Sell"} else None
            if safe_side:
                recent = [f for f in recent if f.get("side") == safe_side]
            fills = recent[offset:offset + limit]
            return core._live_response({
                "source": "engine_state",
                "list": fills,
                "count": len(fills),
                "limit": limit,
                "offset": offset,
                "has_more": len(recent) > offset + limit,
                "next_offset": offset + len(fills) if len(recent) > offset + limit else None,
            })
        except Exception:
            pass
    return core._live_response({"list": [], "count": 0, "available": False})


@core.live_router.post("/positions/{symbol}/close")
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
    _require_live_trade(actor)
    # F5-RETURN/Issue-1 (HIGH) — server-side phantom-view WRITE guard.
    # Refuses curl-bypass attempts that would otherwise drive the IPC →
    # REST-fallback path with the demo client and close demo positions.
    # F5-RETURN/Issue-1（HIGH）— 寫入端 server-side 幽靈視圖守衛，
    # 阻擋 curl 繞過前端 → IPC 失敗 → REST 降級用 demo client 誤平 demo 倉位。
    _phantom_view_guard_write()
    sym = symbol.upper()

    # Step 1: read-only lookup of exchange position to build hints for Rust.
    # Python 只查倉位資料（只讀），供 Rust 平孤兒倉位時使用。
    hint_is_long: bool | None = None
    hint_qty: float | None = None
    rc = core._get_rust_client_safe()
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

    try:
        result = await core._ipc_command("close_position", ipc_params)
    except Exception as exc:
        if core._is_live_channel_unavailable_error(exc):
            logger.error(
                "live close BLOCKED for %s: live IPC channel unavailable; REST fallback disabled",
                sym,
            )
            raise HTTPException(
                status_code=409,
                detail=core._LIVE_REST_FALLBACK_DISABLED_DETAIL,
            ) from exc
        # E3-S2-P2-2: keep full exception in server log only — client-facing
        # `detail` must not leak `{exc}` (psycopg2 / IPC backend internals can
        # expose schema or socket paths to authenticated callers).
        # E3-S2-P2-2：完整 exception 只進 server log；client 端 detail 不可帶 {exc}
        # （psycopg2 / IPC backend 內部訊息可能漏 schema 或 socket path）。
        logger.exception("IPC close_position failed for %s", sym)
        raise HTTPException(status_code=502, detail={"reason": "ipc_error"})

    # If no exchange position AND paper IPC also found nothing, return 404.
    # 交易所和紙盤都沒倉，回 404（避免謊報 closed=True）。
    if hint_qty is None or hint_qty <= 0:
        raise HTTPException(
            status_code=404,
            detail=f"No position found for {sym} (neither paper state nor exchange) / 倉位不存在",
        )

    logger.warning(
        "⚠ close_position %s hint_is_long=%s hint_qty=%s — actor=%s",
        sym, hint_is_long, hint_qty, getattr(actor, "actor_id", "?"),
    )
    return core._live_response({
        "symbol": sym,
        "closed": True,
        "source": "rust_engine",
        "rest_fallback": False,
        "reason": None,
        "ipc": result,
    })


@core.live_router.post("/close-all-positions")
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
    _require_live_trade(actor)
    # F5-RETURN/Issue-1 (HIGH) — server-side phantom-view WRITE guard.
    # Without it, curl bypass triggers IPC fail → REST orphan-sweep on demo
    # client → mass-closes demo positions across all symbols.
    # F5-RETURN/Issue-1（HIGH）— 寫入端 server-side 守衛；
    # 缺此 guard 時 curl 繞過會觸 IPC 失敗 → REST 孤兒清掃用 demo client 全平 demo 倉位。
    _phantom_view_guard_write()
    errors: list[str] = []
    try:
        result = await core._ipc_command("close_all_positions", {"engine": "live"})
    except Exception as exc:
        if core._is_live_channel_unavailable_error(exc):
            logger.error(
                "close_all_positions BLOCKED: live IPC channel unavailable; REST fallback disabled"
            )
            raise HTTPException(
                status_code=409,
                detail=core._LIVE_REST_FALLBACK_DISABLED_DETAIL,
            ) from exc
        else:
            logger.error("IPC close_all_positions failed: %s", exc)
            errors.append(f"ipc_close_all: {exc}")
            result = {"error": str(exc)}
    # Orphan sweep: close exchange positions not tracked in paper_state.
    # IPC close_all only iterates paper_state — orphan positions are silently skipped.
    # 孤兒清掃：IPC close_all 只遍歷 paper_state，交易所孤兒倉位會被跳過，此處補掃。
    orphan_result = await core._sweep_live_orphan_positions(errors)
    partial_failure = (
        bool(errors)
        or bool(orphan_result.get("skipped"))
        or bool(orphan_result.get("rest_fallback_disabled"))
        or bool(result.get("error"))
    )
    closed_all = not partial_failure
    logger.warning(
        "⚠ close-all-positions (manual, session continues) — closed_all=%s errors=%s actor=%s",
        closed_all,
        errors or None,
        getattr(actor, "actor_id", "?"),
    )
    return core._live_response({
        "message": (
            "Close-all partially failed — session continues / 全平部分失敗，session 繼續運行"
            if partial_failure else
            "All positions closed — session continues / 已平掉所有倉位，session 繼續運行"
        ),
        "source": "rust_engine",
        "status": "partial_failure" if partial_failure else "closed",
        "closed_all": closed_all,
        "partial_failure": partial_failure,
        "rest_fallback": False,
        "reason": None,
        "close_result": result,
        "orphan_sweep": orphan_result,
        "errors": errors if errors else None,
    })


@core.live_router.get("/metrics")
def get_live_metrics(
    actor: Any = Depends(base.current_actor),
) -> dict:
    """GET /api/v1/live/metrics — performance metrics from Rust engine (fills/positions/PnL). / 性能指標。"""
    # F5/A1 phantom-view guard / F5/A1 幽靈視圖守衛
    guard = _phantom_view_guard()
    if guard is not None:
        return guard

    from .paper_trading_metrics import compute_full_metrics
    from .trading_true_metrics import build_performance_metrics, fetch_db_true_metrics

    rust = get_rust_reader()
    # 3E-5: query per-engine snapshot for live metrics.
    # 3E-5：查詢每引擎快照用於 live 指標。
    engine_kind = core._get_live_engine_kind()
    actual_endpoint = core._resolve_live_endpoint_label()
    if actual_endpoint == "live_demo":
        db_modes = ["live_demo"]
    elif actual_endpoint == "mainnet":
        db_modes = ["live"]
    elif engine_kind == "live":
        db_modes = ["live"]
    else:
        db_modes = ["live"]
    if engine_kind != "live" and actual_endpoint in ("live_demo", "mainnet"):
        db_metrics = fetch_db_true_metrics(
            db_modes,
            edge_engine_modes=db_modes,
            window_days=7,
        )
        return core._live_response({
            "available": False,
            "source": "engine_unavailable",
            "error": "live_engine_unavailable",
            "error_zh": "Live 槽已配置，但 Rust live 引擎未運行；拒絕用 demo 統計偽裝 live",
            "error_en": (
                "Live slot is configured but Rust live engine is not running; "
                "refusing to render demo metrics as live"
            ),
            "actual_engine_kind": engine_kind,
            "actual_endpoint": actual_endpoint,
            "db_true_metrics": db_metrics,
            "performance_metrics": build_performance_metrics(
                db_metrics,
                total_ai_cost=_fetch_total_ai_cost_30d_safe(),
            ),
        })
    rust_state = rust.get_paper_state(engine=engine_kind) if rust.is_available() and engine_kind != "unknown" else None
    if rust_state is None:
        db_metrics = fetch_db_true_metrics(
            db_modes,
            edge_engine_modes=db_modes,
            window_days=7,
        )
        return core._live_response({
            "available": False,
            "source": "engine_unavailable",
            "actual_engine_kind": engine_kind,
            "actual_endpoint": actual_endpoint,
            "db_true_metrics": db_metrics,
            "performance_metrics": build_performance_metrics(
                db_metrics,
                total_ai_cost=_fetch_total_ai_cost_30d_safe(),
            ),
        })
    full = compute_full_metrics(rust_state, engine_mode=engine_kind)
    # Read per-engine tick stats / 讀取每引擎 tick 統計
    engine_snap = rust.get_engine_snapshot(engine_kind) if engine_kind != "unknown" else None
    stats = (engine_snap or {}).get("stats") or {}
    full["source"] = "rust_engine"
    full["total_ticks"] = stats.get("total_ticks", 0)
    full["total_intents"] = stats.get("total_intents", 0)
    full["total_fills"] = stats.get("total_fills", 0)
    full["total_stops"] = stats.get("total_stops", 0)
    db_metrics = fetch_db_true_metrics(
        db_modes,
        edge_engine_modes=db_modes,
        window_days=7,
    )
    full["db_true_metrics"] = db_metrics
    total_ai_cost = _fetch_total_ai_cost_30d_safe()
    if total_ai_cost is not None:
        full["total_ai_cost"] = round(total_ai_cost, 6)
    full["performance_metrics"] = build_performance_metrics(
        db_metrics,
        fallback_metrics=full,
        total_ai_cost=total_ai_cost,
    )
    return core._live_response(full)


def _fetch_total_ai_cost_30d_safe() -> float | None:
    """Fetch AI cost for metrics without failing the Live route.

    讀取 AI 成本供績效指標使用；失敗時不影響 Live route。
    """
    try:
        from .paper_trading_ai_cost_routes import fetch_total_ai_cost_30d

        return fetch_total_ai_cost_30d()
    except Exception:
        logger.debug("AI cost lookup failed for live metrics", exc_info=True)
        return None
