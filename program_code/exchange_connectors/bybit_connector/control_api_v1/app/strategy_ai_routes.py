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
import base64
import json
import logging
import os
import re
import time
from threading import RLock
from typing import Any

from fastapi import Depends, HTTPException, Query

from . import main_legacy as base
from .strategy_wiring import (
    phase2_router,
    ORCHESTRATOR,
    TELEGRAM,
    _envelope,
)

logger = logging.getLogger(__name__)
_CLOSED_PNL_CACHE = None
_OPENCLAW_LINK_RE = re.compile(r"^oc_(?:close_[a-z0-9_]+_)?(?:risk_)?(?P<engine>dm|ld)(?:_|$)", re.I)
_CLOSED_PNL_DAY_MS = 24 * 60 * 60 * 1000
_CLOSED_PNL_MAX_WINDOW_MS = 7 * 24 * 60 * 60 * 1000
_CLOSED_PNL_ALL_HISTORY_DAYS = 730
_CLOSED_PNL_MAX_WINDOWS_PER_PRELOAD = 8
_CLOSED_PNL_CURSOR_VERSION = 1
_CLOSED_PNL_FAILURE_WINDOW_SEC = 60.0
_CLOSED_PNL_DEGRADED_SEC = 5 * 60
_CLOSED_PNL_BYBIT_FAILURES: list[float] = []
_CLOSED_PNL_FAILURE_LOCK = RLock()
_GUI_READ_STATEMENT_TIMEOUT_MS = int(os.getenv("OPENCLAW_GUI_READ_STATEMENT_TIMEOUT_MS", "1500"))


def _closed_pnl_cache():
    """Lazy singleton for Demo closed-PnL REST reads."""
    global _CLOSED_PNL_CACHE
    if _CLOSED_PNL_CACHE is None:
        from .bybit_pnl_cache import ClosedPnlCache  # noqa: PLC0415
        _CLOSED_PNL_CACHE = ClosedPnlCache(ttl_sec=8.0)
    return _CLOSED_PNL_CACHE


def _clear_closed_pnl_bybit_failures() -> None:
    with _CLOSED_PNL_FAILURE_LOCK:
        _CLOSED_PNL_BYBIT_FAILURES.clear()


def _record_closed_pnl_bybit_failure() -> dict[str, Any]:
    now = time.monotonic()
    cutoff = now - _CLOSED_PNL_FAILURE_WINDOW_SEC
    with _CLOSED_PNL_FAILURE_LOCK:
        _CLOSED_PNL_BYBIT_FAILURES[:] = [
            ts for ts in _CLOSED_PNL_BYBIT_FAILURES if ts >= cutoff
        ]
        _CLOSED_PNL_BYBIT_FAILURES.append(now)
        count = len(_CLOSED_PNL_BYBIT_FAILURES)
    degraded_until_ms = (
        int((time.time() + _CLOSED_PNL_DEGRADED_SEC) * 1000)
        if count >= 3
        else None
    )
    return {
        "bybit_failure_count_60s": count,
        "degraded_until_ms": degraded_until_ms,
    }


def _closed_pnl_encode_cursor(payload: dict[str, Any]) -> str:
    data = dict(payload)
    data["v"] = _CLOSED_PNL_CURSOR_VERSION
    raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _closed_pnl_decode_cursor(cursor: str | None) -> dict[str, Any]:
    if not cursor:
        return {}
    try:
        padded = cursor + ("=" * (-len(cursor) % 4))
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid closed-pnl cursor") from exc
    if not isinstance(data, dict) or data.get("v") != _CLOSED_PNL_CURSOR_VERSION:
        raise HTTPException(status_code=400, detail="invalid closed-pnl cursor")
    return data


def _closed_pnl_optional_ms(value: Any) -> int | None:
    if not isinstance(value, (int, float, str)):
        return None
    try:
        return int(value)
    except Exception:
        return None


def _closed_pnl_history_bounds(
    *,
    start_time: Any,
    end_time: Any,
    lookback_days: int,
) -> tuple[int, int]:
    now_ms = int(time.time() * 1000)
    end_ms = _closed_pnl_optional_ms(end_time)
    if end_ms is None:
        end_ms = (now_ms // 5000) * 5000
    start_ms = _closed_pnl_optional_ms(start_time)
    if start_ms is None:
        try:
            requested_days = int(lookback_days)
        except Exception:
            requested_days = _CLOSED_PNL_ALL_HISTORY_DAYS
        safe_days = min(max(requested_days, 1), _CLOSED_PNL_ALL_HISTORY_DAYS)
        start_ms = end_ms - safe_days * _CLOSED_PNL_DAY_MS
    if end_ms < start_ms:
        raise HTTPException(status_code=400, detail="end_time must be >= start_time")
    return start_ms, end_ms


def _closed_pnl_initial_bybit_state(
    *,
    start_ms: int,
    end_ms: int,
    symbol: str | None,
) -> dict[str, Any]:
    window_start_ms = max(start_ms, end_ms - _CLOSED_PNL_MAX_WINDOW_MS)
    return {
        "source": "bybit",
        "start_ms": start_ms,
        "end_ms": end_ms,
        "window_start_ms": window_start_ms,
        "window_end_ms": end_ms,
        "cursor": None,
        "symbol": symbol,
    }


def _closed_pnl_previous_window_state(state: dict[str, Any]) -> dict[str, Any] | None:
    start_ms = int(state.get("start_ms") or 0)
    window_start_ms = int(state.get("window_start_ms") or 0)
    prev_end_ms = window_start_ms - 1
    if prev_end_ms < start_ms:
        return None
    return {
        "source": "bybit",
        "start_ms": start_ms,
        "end_ms": int(state.get("end_ms") or prev_end_ms),
        "window_start_ms": max(start_ms, prev_end_ms - _CLOSED_PNL_MAX_WINDOW_MS),
        "window_end_ms": prev_end_ms,
        "cursor": None,
        "symbol": state.get("symbol"),
    }


def _closed_pnl_bybit_state_with_cursor(
    *,
    cursor: str | None,
    start_ms: int,
    end_ms: int,
    symbol: str | None,
) -> dict[str, Any]:
    decoded = _closed_pnl_decode_cursor(cursor)
    if decoded.get("source") != "bybit":
        return _closed_pnl_initial_bybit_state(start_ms=start_ms, end_ms=end_ms, symbol=symbol)
    return {
        "source": "bybit",
        "start_ms": int(decoded.get("start_ms") or start_ms),
        "end_ms": int(decoded.get("end_ms") or end_ms),
        "window_start_ms": int(decoded.get("window_start_ms") or start_ms),
        "window_end_ms": int(decoded.get("window_end_ms") or end_ms),
        "cursor": decoded.get("cursor") or None,
        "symbol": decoded.get("symbol") or symbol,
    }


def _fetch_closed_pnl_bybit_history_page(
    rc: Any,
    *,
    limit: int,
    cursor: str | None,
    symbol: str | None,
    start_ms: int,
    end_ms: int,
) -> tuple[list[dict[str, Any]], str | None]:
    rows: list[dict[str, Any]] = []
    state = _closed_pnl_bybit_state_with_cursor(
        cursor=cursor,
        start_ms=start_ms,
        end_ms=end_ms,
        symbol=symbol,
    )
    next_state: dict[str, Any] | None = None
    seen_cursors: set[str] = {str(state["cursor"])} if state.get("cursor") else set()
    calls = 0
    while state and len(rows) < limit and calls < _CLOSED_PNL_MAX_WINDOWS_PER_PRELOAD:
        calls += 1
        page_limit = min(100, max(1, limit - len(rows)))
        bybit_cursor = state.get("cursor") or None
        result = rc.get_closed_pnl(
            "linear",
            symbol=symbol,
            start_time=int(state["window_start_ms"]),
            end_time=int(state["window_end_ms"]),
            limit=page_limit,
            cursor=bybit_cursor,
        )
        items = result.get("list") if isinstance(result, dict) else result
        if isinstance(items, list):
            rows.extend([dict(row) for row in items if isinstance(row, dict)])
        next_bybit_cursor = (
            result.get("nextPageCursor")
            if isinstance(result, dict)
            else None
        )
        if next_bybit_cursor:
            if next_bybit_cursor in seen_cursors:
                logger.warning("Bybit closed-pnl returned repeated cursor; stopping pagination")
                next_state = None
                break
            seen_cursors.add(str(next_bybit_cursor))
            next_state = {**state, "cursor": str(next_bybit_cursor)}
            if len(rows) >= limit:
                break
            state = next_state
            continue
        previous = _closed_pnl_previous_window_state(state)
        if len(rows) >= limit:
            next_state = previous
            break
        state = previous
        next_state = state
    if len(rows) < limit and state is not None and calls >= _CLOSED_PNL_MAX_WINDOWS_PER_PRELOAD:
        next_state = state
    next_cursor = _closed_pnl_encode_cursor(next_state) if next_state else None
    return rows[:limit], next_cursor


def _closed_pnl_pg_cursor(
    *,
    offset: int,
    symbol: str | None,
    start_ms: int,
    end_ms: int,
    engine_modes: tuple[str, ...],
) -> str:
    return _closed_pnl_encode_cursor({
        "source": "pg",
        "offset": offset,
        "symbol": symbol,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "engine_modes": list(engine_modes),
    })


def _require_demo_session_write(actor: base.AuthenticatedActor) -> None:
    """Shared Batch B gate for demo-session state mutations.
    Batch B 共用 demo session 寫入閘門：必須是 Operator 且具 paper:trade scope。
    """
    base.require_scope_and_operator(actor, "paper:trade")

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


def _paper_state_balance_payload(
    state: dict[str, Any],
    *,
    source: str = "rust_engine",
    pipeline_status: str = "connected",
) -> dict[str, Any]:
    """Build a GUI-compatible balance payload from Rust paper_state only."""
    positions = state.get("positions") or []
    unrealized = 0.0
    if isinstance(positions, list):
        for p in positions:
            if not isinstance(p, dict):
                continue
            try:
                unrealized += float(p.get("unrealized_pnl") or 0.0)
            except Exception:
                continue
    balance = state.get("bybit_sync_balance")
    if balance is None:
        balance = state.get("balance")
    try:
        equity = float(balance or 0.0)
    except Exception:
        equity = 0.0
    return {
        "source": source,
        "read_model": "rust_snapshot_fast",
        "pipeline_status": pipeline_status,
        "totalEquity": equity,
        "total_equity": equity,
        "equity": equity,
        "balance": equity,
        "totalAvailableBalance": equity,
        "total_available_balance": equity,
        "availableBalance": equity,
        "available_balance": equity,
        "totalWalletBalance": equity,
        "total_wallet_balance": equity,
        "walletBalance": equity,
        "wallet_balance": equity,
        "totalPerpUPL": unrealized,
        "total_unrealized_pnl": unrealized,
        "unrealized_pnl": unrealized,
        "engine_initial_balance": state.get("initial_balance"),
        "engine_peak_balance": state.get("peak_balance"),
        "engine_current_balance": state.get("balance"),
        "engine_realized_pnl": state.get("total_realized_pnl"),
        "engine_total_fees": state.get("total_fees"),
    }


def _paper_state_positions_for_gui(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize Rust paper_state positions into the Bybit-like shape used by the GUI."""
    out: list[dict[str, Any]] = []
    raw_positions = state.get("positions") or []
    if not isinstance(raw_positions, list):
        return out
    for p in raw_positions:
        if not isinstance(p, dict):
            continue
        sym = str(p.get("symbol") or "")
        qty = p.get("qty") or p.get("size") or 0
        entry = p.get("entry_price") or p.get("avgPrice") or p.get("avg_price") or 0
        mark = p.get("mark_price") or p.get("best_price") or entry
        side = p.get("side")
        if not side:
            side = "Buy" if bool(p.get("is_long")) else "Sell"
        cat = p.get("category") or ("inverse" if sym.endswith("USD") and not sym.endswith("USDT") else "linear")
        out.append({
            **p,
            "symbol": sym,
            "category": cat,
            "side": side,
            "size": qty,
            "qty": qty,
            "avgPrice": entry,
            "avg_price": entry,
            "entry_price": entry,
            "markPrice": mark,
            "mark_price": mark,
            "unrealisedPnl": p.get("unrealized_pnl", p.get("unrealisedPnl", 0)),
            "unrealized_pnl": p.get("unrealized_pnl", p.get("unrealisedPnl", 0)),
            "leverage": p.get("leverage") or "1",
            "owner_strategy": p.get("owner_strategy") or "",
        })
    return out


def _demo_snapshot_pair() -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the fresh Demo engine snapshot + paper_state, or empty dicts."""
    try:
        from .paper_trading_routes import get_rust_reader  # noqa: PLC0415
        reader = get_rust_reader()
        if not reader.is_engine_available("demo"):
            return {}, {}
        snap = (
            reader.get_engine_snapshot("demo")
            if hasattr(reader, "get_engine_snapshot")
            else reader.get_snapshot(engine="demo")
            if hasattr(reader, "get_snapshot")
            else {}
        ) or {}
        state = reader.get_paper_state(engine="demo") or {}
        return snap, state
    except Exception:
        logger.debug("Demo snapshot fast read unavailable", exc_info=True)
        return {}, {}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if out == out else default


def _time_ms(row: dict[str, Any]) -> int:
    for key in ("timestamp_ms", "ts_ms", "exec_time", "execTime", "filled_at", "timestamp"):
        value = row.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def _demo_snapshot_fills_payload(
    *,
    limit: int,
    offset: int,
    side: str | None = None,
) -> dict[str, Any]:
    """Fast GUI fills from the Rust snapshot only; never hits PG or Bybit REST."""
    snap, state = _demo_snapshot_pair()
    raw = snap.get("recent_fills") or state.get("fills") or []
    if not isinstance(raw, list):
        raw = []
    safe_side = side if side in {"Buy", "Sell"} else None
    fills: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        is_long = row.get("is_long")
        if not row.get("side") and isinstance(is_long, bool):
            row["side"] = "Buy" if is_long else "Sell"
        ts_ms = _time_ms(row)
        row["exec_time"] = str(ts_ms)
        row["execTime"] = str(ts_ms)
        row["qty"] = _num(row.get("qty") or row.get("execQty"))
        row["price"] = _num(row.get("price") or row.get("execPrice"))
        row["fee"] = _num(row.get("fee") or row.get("execFee"))
        row["execQty"] = row["qty"]
        row["execPrice"] = row["price"]
        row["execFee"] = row["fee"]
        row["realized_pnl"] = _num(row.get("realized_pnl") or row.get("closedPnl"))
        row["closedPnl"] = row["realized_pnl"]
        row["strategy"] = row.get("strategy") or row.get("strategy_name") or ""
        sym = str(row.get("symbol") or "")
        row["category"] = row.get("category") or (
            "inverse" if sym.endswith("USD") and not sym.endswith("USDT") else "linear"
        )
        if safe_side and row.get("side") != safe_side:
            continue
        fills.append(_normalize_execution(row))
    fills.sort(key=_time_ms, reverse=True)
    page = fills[offset:offset + limit]
    return {
        "source": "rust_snapshot_fast",
        "list": page,
        "count": len(page),
        "limit": limit,
        "offset": offset,
        "has_more": len(fills) > offset + limit,
        "next_offset": offset + len(page) if len(fills) > offset + limit else None,
    }


def _demo_snapshot_orders_payload() -> dict[str, Any]:
    """Fast GUI orders from snapshot fields when present; otherwise fail-soft empty."""
    snap, state = _demo_snapshot_pair()
    raw = (
        snap.get("active_orders")
        or snap.get("open_orders")
        or state.get("active_orders")
        or state.get("orders")
        or []
    )
    if not isinstance(raw, list):
        raw = []
    orders = [_normalize_order(o) for o in raw if isinstance(o, dict)]
    conditional_count = sum(
        1 for o in orders
        if (o.get("orderStatus") or "").lower() == "untriggered"
    )
    regular_count = len(orders) - conditional_count
    return {
        "source": "rust_snapshot_fast",
        "retCode": 0,
        "result": {"list": orders},
        "regular_count": regular_count,
        "conditional_count": conditional_count,
        "degraded_reason": None if orders else "snapshot_has_no_open_orders",
    }


def _demo_snapshot_pnl_series_payload(
    *,
    range_key: str,
    bucket_sec: int | None,
) -> dict[str, Any]:
    """Build a small PnL series from snapshot recent_fills without DB access."""
    range_map = {
        "1h": 60 * 60,
        "6h": 6 * 60 * 60,
        "24h": 24 * 60 * 60,
        "7d": 7 * 24 * 60 * 60,
        "30d": 30 * 24 * 60 * 60,
    }
    default_buckets = {
        "1h": 60,
        "6h": 5 * 60,
        "24h": 15 * 60,
        "7d": 60 * 60,
        "30d": 4 * 60 * 60,
    }
    key = str(range_key or "24h").strip().lower()
    if key not in range_map:
        key = "24h"
    range_sec = range_map[key]
    bucket = int(bucket_sec or default_buckets[key])
    bucket = max(60, min(bucket, 24 * 60 * 60))
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - range_sec * 1000
    fills = _demo_snapshot_fills_payload(limit=200, offset=0).get("list", [])
    buckets: dict[int, dict[str, float | int]] = {}
    for row in fills:
        if not isinstance(row, dict):
            continue
        ts_ms = _time_ms(row)
        if ts_ms < start_ms or ts_ms > now_ms:
            continue
        epoch = int((ts_ms // 1000) // bucket) * bucket
        slot = buckets.setdefault(epoch, {"fills": 0, "gross_pnl": 0.0, "fees": 0.0})
        slot["fills"] = int(slot["fills"]) + 1
        slot["gross_pnl"] = float(slot["gross_pnl"]) + _num(row.get("realized_pnl") or row.get("closedPnl"))
        slot["fees"] = float(slot["fees"]) + _num(row.get("fee") or row.get("execFee"))
    cumulative = 0.0
    points: list[dict[str, Any]] = []
    for epoch in sorted(buckets):
        slot = buckets[epoch]
        gross = float(slot["gross_pnl"])
        fees = float(slot["fees"])
        net = gross - fees
        cumulative += net
        points.append({
            "ts_ms": epoch * 1000,
            "fills": int(slot["fills"]),
            "gross_pnl": round(gross, 6),
            "fees": round(fees, 6),
            "funding_pnl": 0.0,
            "net_pnl": round(net, 6),
            "cumulative_net_pnl": round(cumulative, 6),
        })
    return {
        "available": True,
        "source": "rust_snapshot_fast",
        "range": key,
        "range_sec": range_sec,
        "bucket_sec": bucket,
        "engine_modes": ["demo"],
        "from_ts_ms": start_ms,
        "to_ts_ms": now_ms,
        "window_net_pnl": round(sum(p["net_pnl"] for p in points), 6),
        "window_gross_pnl": round(sum(p["gross_pnl"] for p in points), 6),
        "window_fees": round(sum(p["fees"] for p in points), 6),
        "window_funding_pnl": 0.0,
        "fills": sum(int(p["fills"]) for p in points),
        "points": points,
    }


def _demo_snapshot_metrics_payload() -> dict[str, Any]:
    """Fast Demo metrics from Rust snapshot only; no PG, no Bybit REST."""
    _, state = _demo_snapshot_pair()
    if not state:
        return {
            "source": "rust_snapshot_fast",
            "available": False,
            "reason": "demo_snapshot_unavailable",
            "performance_metrics": [],
        }
    positions = state.get("positions") if isinstance(state.get("positions"), list) else []
    unrealized = sum(_num(p.get("unrealized_pnl")) for p in positions if isinstance(p, dict))
    gross = _num(state.get("total_realized_pnl"))
    fees = _num(state.get("total_fees"))
    funding = _num(state.get("total_funding_pnl"))
    net = gross - fees + funding
    trade_count = int(_num(state.get("trade_count")))
    db_like = {
        "available": True,
        "source": "rust_snapshot_fast",
        "window_days": 7,
        "engine_modes": ["demo"],
        "edge_engine_modes": ["demo"],
        "account_metrics": {
            "total_fills": trade_count,
            "gross_pnl": round(gross, 6),
            "total_fees": round(fees, 6),
            "funding_pnl": round(funding, 6),
            "net_pnl": round(net, 6),
        },
        "account_metrics_today": {
            "total_fills": trade_count,
            "gross_pnl": round(gross, 6),
            "total_fees": round(fees, 6),
            "funding_pnl": round(funding, 6),
            "net_pnl": round(net, 6),
        },
        "account_metrics_24h": {
            "total_fills": trade_count,
            "gross_pnl": round(gross, 6),
            "total_fees": round(fees, 6),
            "funding_pnl": round(funding, 6),
            "net_pnl": round(net, 6),
        },
        "trade_metrics": {
            "metric_source": "rust_snapshot_fast",
            "metric_unit": "usdt",
            "total_round_trips": trade_count,
            "win_rate": 0.0,
            "win_loss_ratio": 0.0,
            "largest_win": 0.0,
            "largest_loss": 0.0,
            "avg_loss": 0.0,
        },
        "edge_metrics": {
            "metric_source": "rust_snapshot_fast",
            "metric_unit": "bps",
            "total_round_trips": 0,
        },
        "risk_metrics": {
            "metric_source": "rust_snapshot_fast",
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "avg_holding_period_sec": 0.0,
        },
    }
    from .trading_true_metrics import build_performance_metrics  # noqa: PLC0415
    return {
        "source": "rust_snapshot_fast",
        "unrealized_pnl": round(unrealized, 6),
        "db_true_metrics": db_like,
        "performance_metrics": build_performance_metrics(db_like),
    }


@phase2_router.get("/demo/balance")
async def get_demo_balance(
    fast: bool = Query(False),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
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

    if fast is True:
        try:
            demo_state = reader.get_paper_state(engine="demo") or {}
            if demo_state:
                return _envelope(_paper_state_balance_payload(demo_state))
        except Exception:
            logger.debug("Demo fast balance snapshot unavailable", exc_info=True)

    rc = _get_rust_client()
    if rc is None:
        return _envelope({"enabled": False, "source": "rust_engine"})
    try:
        wallet = rc.refresh_balance()
    except Exception as exc:
        # WP-05 Real Fix
        logger.exception("Bybit balance fetch failed")
        from .error_sanitize import sanitize_exc_for_detail  # noqa: PLC0415
        raise HTTPException(
            status_code=502,
            detail=sanitize_exc_for_detail(exc, "bybit_api_failure"),
        )

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
        spec = None
    min_notional = _safe_float(spec.get("min_notional")) if spec else None
    if min_notional is not None:
        return min_notional
    # The lightweight FastAPI singleton often has an empty instrument cache.
    # For REST-only dust positions not present in paper_state, do a one-symbol
    # public lookup so the GUI can still label below-minNotional residues.
    try:
        fetch = getattr(rc, "_get", None)
        if not callable(fetch):
            return None
        payload = fetch(
            "/v5/market/instruments-info",
            {"category": "linear", "symbol": symbol},
        )
        result = payload.get("result") if isinstance(payload, dict) else None
        items = result.get("list") if isinstance(result, dict) else None
        item = items[0] if isinstance(items, list) and items else None
        lot = item.get("lotSizeFilter") if isinstance(item, dict) else None
        if isinstance(lot, dict):
            return _safe_float(lot.get("minNotionalValue"))
    except Exception:
        return None
    return None


def _position_est_notional(p: dict[str, Any]) -> float | None:
    """Best-effort qty × reference price for Bybit REST position rows."""
    qty = _safe_float(p.get("size")) or _safe_float(p.get("qty"))
    ref_price = (
        _safe_float(p.get("markPrice"))
        or _safe_float(p.get("avgPrice"))
        or _safe_float(p.get("entry_price"))
    )
    if qty is not None and ref_price is not None and qty > 0.0 and ref_price > 0.0:
        return qty * ref_price
    return None


def _attach_owner_strategy(positions: list, engine: str) -> list:
    """Enrich each Bybit position dict with `owner_strategy` from engine paper_state.
    For synthetic owners (bybit_sync / orphan_adopted / orphan_frozen) additionally
    attach `frozen_reason` + `min_notional` + `est_notional` so the GUI can explain
    WHY a position is held without an active strategy tag.
    No-op when position is not a dict. Symbols not found in the map are left
    for the GUI's fills-derived fallback, except below-minNotional residues,
    which are labelled as orphan_frozen directly. Real strategy names skip the
    dust enrichment path to keep the common payload lean.

    用引擎 paper_state 的 owner_strategy 豐富每筆 Bybit 倉位 dict。
    對合成 owner (bybit_sync / orphan_adopted / orphan_frozen) 額外附加
    `frozen_reason` + `min_notional` + `est_notional`，供 GUI 解釋該倉位為何
    持有卻無活躍策略標籤。非 dict 時跳過；映射未命中時保留前端 fills fallback，
    但低於 minNotional 的殘倉直接標為 orphan_frozen。真實策略名略過 dust
    enrichment 路徑以保持常態 payload lean。
    """
    if not isinstance(positions, list) or not positions:
        return positions
    owner_map = _engine_owner_strategy_map(engine)
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
            # GUI-DUST-ATTRIBUTION-FUP: some exchange-side residues are
            # intentionally removed from paper_state by EVICT-ON-DUST because
            # they are too small to close. They still appear in Bybit REST, so
            # label them directly from minNotional instead of showing "--".
            try:
                est_notional = _position_est_notional(p)
                if est_notional is None or not sym:
                    continue
                if sym not in min_notional_cache:
                    min_notional_cache[sym] = _fetch_min_notional(sym)
                min_notional = min_notional_cache.get(sym)
                if min_notional is not None and est_notional < min_notional:
                    p["owner_strategy"] = "orphan_frozen"
                    p["frozen_reason"] = "dust_below_min_notional"
                    p["min_notional"] = min_notional
                    p["est_notional"] = est_notional
            except Exception:
                logger.exception("unmapped dust enrichment failed for symbol=%s", sym)
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
            est_notional = _position_est_notional(p)

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
async def get_demo_positions(
    fast: bool = Query(False),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get Bybit Demo open positions via httpx BybitClient / 通過 httpx BybitClient 獲取 Demo 持倉"""
    if fast is True:
        try:
            from .paper_trading_routes import get_rust_reader  # noqa: PLC0415
            reader = get_rust_reader()
            if reader.is_engine_available("demo"):
                state = reader.get_paper_state(engine="demo") or {}
                positions = _paper_state_positions_for_gui(state)
                return _envelope({
                    "source": "rust_snapshot_fast",
                    "list": positions,
                    "count": len(positions),
                })
        except Exception:
            logger.debug("Demo fast positions snapshot unavailable", exc_info=True)

    rc = _get_rust_client()
    if rc is None:
        return _envelope({"enabled": False, "source": "rust_engine"})
    try:
        positions = rc.get_positions("linear")
        positions = _attach_owner_strategy(positions, engine="demo")
        return _envelope({"source": "rust_engine", "list": positions, "count": len(positions)})
    except Exception as exc:
        # WP-05 Real Fix
        logger.exception("Bybit positions fetch failed")
        from .error_sanitize import sanitize_exc_for_detail  # noqa: PLC0415
        raise HTTPException(
            status_code=502,
            detail=sanitize_exc_for_detail(exc, "bybit_api_failure"),
        )


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
async def get_demo_orders(
    fast: bool = Query(False),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get Bybit Demo open orders via httpx BybitClient.
    通過 httpx BybitClient 獲取 Demo 活躍訂單。
    """
    if fast is True:
        return _envelope(_demo_snapshot_orders_payload())

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
        # WP-05 Real Fix
        logger.exception("Bybit orders fetch failed")
        from .error_sanitize import sanitize_exc_for_detail  # noqa: PLC0415
        raise HTTPException(
            status_code=502,
            detail=sanitize_exc_for_detail(exc, "bybit_api_failure"),
        )


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


def _strategy_from_order_link_id(
    order_link_id: Any,
    *,
    symbol: str,
) -> tuple[str, str]:
    """Infer strategy_name/source from Bybit orderLinkId when PG join misses."""
    link = str(order_link_id or "").strip()
    match = _OPENCLAW_LINK_RE.match(link)
    if not link or not match:
        return "external_manual", "bybit_unknown"
    engine = "live_demo" if match.group("engine").lower() == "ld" else "demo"
    owner = _engine_owner_strategy_map(engine).get(symbol)
    if owner:
        return owner, "pg_link_id"
    return "unknown_pending", "pg_missing_unknown_external"


def _fetch_strategy_by_order_id(
    order_ids: list[str],
    *,
    engine_modes: tuple[str, ...] = ("demo", "live_demo"),
) -> dict[str, dict[str, Any]]:
    """Read-only PG join: Bybit orderId/link id → latest local fill attribution."""
    ids = sorted({oid for oid in order_ids if oid})
    if not ids:
        return {}
    safe_modes = tuple(engine_modes or ("demo", "live_demo"))
    mode_placeholders = ", ".join(["%s"] * len(safe_modes))
    try:
        from . import db_pool  # noqa: PLC0415
        conn = db_pool.get_conn()
    except Exception:
        return {}
    if conn is None:
        return {}
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT ON (order_id) order_id, strategy_name, realized_pnl "
            "FROM trading.fills "
            f"WHERE order_id = ANY(%s) AND engine_mode IN ({mode_placeholders}) "
            "ORDER BY order_id, ts DESC",
            (ids, *safe_modes),
        )
        rows = cur.fetchall()
        return {
            str(order_id): {
                "strategy_name": str(strategy_name) if strategy_name else "",
                "realized_pnl": _safe_float(realized_pnl),
            }
            for order_id, strategy_name, realized_pnl in rows
            if order_id
        }
    except Exception as exc:
        logger.warning("closed-pnl PG strategy join failed: %s", exc)
        return {}
    finally:
        try:
            db_pool.put_conn(conn)
        except Exception:
            pass


def _closed_pnl_float(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value is None:
        return None
    return _safe_float(value)


def _closed_pnl_snake_row(row: dict[str, Any]) -> dict[str, Any]:
    """Expose stable snake_case aliases while preserving raw Bybit camelCase."""
    closed_pnl = _closed_pnl_float(row, "closedPnl")
    open_fee = _closed_pnl_float(row, "openFee")
    close_fee = _closed_pnl_float(row, "closeFee")
    fill_count = row.get("fillCount")
    try:
        fill_count_int = int(fill_count) if fill_count is not None and fill_count != "" else 0
    except Exception:
        fill_count_int = 0
    out = dict(row)
    out.update({
        "symbol": row.get("symbol") or "",
        "side": row.get("side") or "",
        "qty": _closed_pnl_float(row, "qty") or 0.0,
        "avg_entry_price": _closed_pnl_float(row, "avgEntryPrice"),
        "avg_exit_price": _closed_pnl_float(row, "avgExitPrice"),
        "closed_pnl": closed_pnl if closed_pnl is not None else 0.0,
        "bybit_closed_pnl": closed_pnl if closed_pnl is not None else 0.0,
        "open_fee": open_fee,
        "close_fee": close_fee,
        "closed_size": _closed_pnl_float(row, "closedSize"),
        "fill_count": fill_count_int,
        "updated_time_ms": int(_closed_pnl_float(row, "updatedTime") or 0),
        "created_time_ms": int(_closed_pnl_float(row, "createdTime") or 0),
        "order_id": row.get("orderId") or "",
        "order_link_id": row.get("orderLinkId") or "",
        "leverage": row.get("leverage") or "",
        "exec_type": row.get("execType") or "",
    })
    return out


def _attach_closed_pnl_strategy(
    rows: list[dict[str, Any]],
    *,
    engine_modes: tuple[str, ...] = ("demo", "live_demo"),
) -> list[dict[str, Any]]:
    """Attach strategy_name, source, PG PnL and drift fields."""
    lookup_ids: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in ("orderId", "orderLinkId"):
            value = str(row.get(key) or "").strip()
            if value:
                lookup_ids.append(value)
    strategy_by_order_id = _fetch_strategy_by_order_id(lookup_ids, engine_modes=engine_modes)
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        order_id = str(row.get("orderId") or "").strip()
        order_link_id = str(row.get("orderLinkId") or "").strip()
        enriched = _closed_pnl_snake_row(row)
        pg_match = strategy_by_order_id.get(order_id) or strategy_by_order_id.get(order_link_id)
        pg_pnl = pg_match.get("realized_pnl") if pg_match else None
        if pg_match and pg_match.get("strategy_name"):
            enriched["strategy_name"] = pg_match["strategy_name"]
            enriched["strategy_source"] = "pg_fill"
        else:
            strategy_name, strategy_source = _strategy_from_order_link_id(
                row.get("orderLinkId"),
                symbol=str(enriched.get("symbol") or ""),
            )
            enriched["strategy_name"] = strategy_name
            enriched["strategy_source"] = strategy_source
        bybit_pnl = _safe_float(enriched.get("closed_pnl"))
        enriched["pg_engine_pnl"] = pg_pnl
        if pg_pnl is not None and bybit_pnl is not None:
            diff = abs(float(pg_pnl) - float(bybit_pnl))
            enriched["pnl_source_drift_usd"] = diff
            enriched["pnl_source_drift_pct"] = (
                diff / abs(float(bybit_pnl)) if abs(float(bybit_pnl)) > 0 else None
            )
        else:
            enriched["pnl_source_drift_usd"] = None
            enriched["pnl_source_drift_pct"] = None
        out.append(enriched)
    return out


def _fetch_pg_closed_pnl_fallback(
    *,
    limit: int,
    offset: int,
    symbol: str | None,
    start_ms: int,
    end_ms: int,
    engine_modes: tuple[str, ...] = ("demo", "live_demo"),
) -> dict[str, Any]:
    """Read-only fallback from trading.fills when Bybit REST is unavailable."""
    safe_modes = tuple(engine_modes or ("demo", "live_demo"))
    mode_placeholders = ", ".join(["%s"] * len(safe_modes))
    try:
        from . import db_pool  # noqa: PLC0415
        conn = db_pool.get_conn()
    except Exception as exc:
        raise RuntimeError("pg_unavailable") from exc
    if conn is None:
        raise RuntimeError("pg_unavailable")
    try:
        where = (
            f"engine_mode IN ({mode_placeholders}) "
            "AND ts >= to_timestamp(%s / 1000.0) "
            "AND ts <= to_timestamp(%s / 1000.0) "
            "AND COALESCE(realized_pnl, 0) <> 0"
        )
        params: list[Any] = [*safe_modes, start_ms, end_ms]
        if symbol:
            where += " AND symbol = %s"
            params.append(symbol)
        params.extend([limit + 1, offset])
        cur = conn.cursor()
        cur.execute(
            "SELECT ts, order_id, symbol, side, qty, price, fee, realized_pnl, strategy_name "
            f"FROM trading.fills WHERE {where} ORDER BY ts DESC LIMIT %s OFFSET %s",
            tuple(params),
        )
        rows = cur.fetchall()
    finally:
        try:
            db_pool.put_conn(conn)
        except Exception:
            pass

    has_more = len(rows) > limit
    out: list[dict[str, Any]] = []
    for ts, order_id, sym, side, qty, price, fee, rpnl, strategy in rows[:limit]:
        ts_ms = int(ts.timestamp() * 1000) if ts is not None else 0
        strategy_name = strategy or "unknown_external"
        row = {
            "symbol": sym or "",
            "side": side or "",
            "qty": str(qty if qty is not None else 0),
            "avgEntryPrice": str(price if price is not None else 0),
            "avgExitPrice": str(price if price is not None else 0),
            "closedPnl": str(rpnl if rpnl is not None else 0),
            "openFee": "",
            "closeFee": str(fee if fee is not None else 0),
            "closedSize": str(qty if qty is not None else 0),
            "fillCount": "1",
            "updatedTime": str(ts_ms),
            "orderId": order_id or "",
            "orderLinkId": "",
            "leverage": "",
            "execType": "pg_fallback",
            "strategy_name": strategy_name,
            "strategy_source": "pg_fill" if strategy else "pg_missing_unknown_external",
            "pg_engine_pnl": float(rpnl) if rpnl is not None else 0.0,
        }
        normalized = _closed_pnl_snake_row(row)
        normalized["strategy_name"] = row["strategy_name"]
        normalized["strategy_source"] = row["strategy_source"]
        normalized["pg_engine_pnl"] = row["pg_engine_pnl"]
        normalized["pnl_source_drift_usd"] = 0.0
        normalized["pnl_source_drift_pct"] = 0.0
        out.append(normalized)
    return {
        "list": out,
        "count": len(out),
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
        "next_offset": offset + len(out) if has_more else None,
        "next_cursor": _closed_pnl_pg_cursor(
            offset=offset + len(out),
            symbol=symbol,
            start_ms=start_ms,
            end_ms=end_ms,
            engine_modes=safe_modes,
        ) if has_more else None,
        "source": "pg_fallback",
        "source_ts": int(time.time() * 1000),
        "cache_age": 0.0,
        "cache_age_seconds": 0.0,
        "degraded_reason": (
            "bybit_closed_pnl_unavailable; pg_fallback_estimated_from_trading_fills; "
            "avgEntryPrice/avgExitPrice/closedSize/fillCount are approximate"
        ),
    }


async def _closed_pnl_history_cursor_payload(
    *,
    rc: Any,
    limit: int,
    cursor: str | None,
    symbol: str | None,
    start_time: Any,
    end_time: Any,
    lookback_days: int,
    engine_modes: tuple[str, ...],
    client_unavailable_reason: str,
) -> dict[str, Any]:
    """Cursor-mode all-history read model for GUI preloading."""
    safe_modes = tuple(engine_modes or ("demo", "live_demo"))
    cursor_state = _closed_pnl_decode_cursor(cursor)
    start_ms, end_ms = _closed_pnl_history_bounds(
        start_time=start_time,
        end_time=end_time,
        lookback_days=lookback_days,
    )
    sym = symbol
    if cursor_state:
        start_ms = int(cursor_state.get("start_ms") or start_ms)
        end_ms = int(cursor_state.get("end_ms") or end_ms)
        sym = cursor_state.get("symbol") or sym
    if cursor_state.get("source") == "pg":
        pg_modes = tuple(cursor_state.get("engine_modes") or safe_modes)
        offset = int(cursor_state.get("offset") or 0)
        payload = await asyncio.to_thread(
            _fetch_pg_closed_pnl_fallback,
            limit=limit,
            offset=offset,
            symbol=sym,
            start_ms=start_ms,
            end_ms=end_ms,
            engine_modes=pg_modes,
        )
        payload.update({
            "all_history": True,
            "range_start_ms": start_ms,
            "range_end_ms": end_ms,
            "page_size": 50,
            "preload_limit": limit,
        })
        return payload

    if rc is None:
        try:
            payload = await asyncio.to_thread(
                _fetch_pg_closed_pnl_fallback,
                limit=limit,
                offset=0,
                symbol=sym,
                start_ms=start_ms,
                end_ms=end_ms,
                engine_modes=safe_modes,
            )
            pg_reason = payload.get("degraded_reason") or "pg_fallback"
            pg_reason = pg_reason.removeprefix("bybit_closed_pnl_unavailable; ")
            payload["degraded_reason"] = f"{client_unavailable_reason}; {pg_reason}"
            payload["bybit_failure_count_60s"] = 0
            payload["degraded_until_ms"] = None
            payload.update({
                "all_history": True,
                "range_start_ms": start_ms,
                "range_end_ms": end_ms,
                "page_size": 50,
                "preload_limit": limit,
            })
            return payload
        except Exception:
            return {
                "enabled": False,
                "source": "pg_fallback",
                "source_ts": int(time.time() * 1000),
                "cache_age": None,
                "cache_age_seconds": None,
                "list": [],
                "count": 0,
                "limit": limit,
                "offset": 0,
                "has_more": False,
                "next_offset": None,
                "next_cursor": None,
                "degraded_reason": f"{client_unavailable_reason}_and_pg_fallback_failed",
                "all_history": True,
                "range_start_ms": start_ms,
                "range_end_ms": end_ms,
                "page_size": 50,
                "preload_limit": limit,
            }

    try:
        rows, next_cursor = await asyncio.to_thread(
            _fetch_closed_pnl_bybit_history_page,
            rc,
            limit=limit,
            cursor=cursor,
            symbol=sym,
            start_ms=start_ms,
            end_ms=end_ms,
        )
        _clear_closed_pnl_bybit_failures()
        enriched = await asyncio.to_thread(
            _attach_closed_pnl_strategy,
            rows,
            engine_modes=safe_modes,
        )
        return {
            "list": enriched,
            "count": len(enriched),
            "limit": limit,
            "offset": 0,
            "has_more": bool(next_cursor),
            "next_offset": None,
            "next_cursor": next_cursor,
            "source": "bybit_api",
            "source_ts": int(time.time() * 1000),
            "cache_age": 0.0,
            "cache_age_seconds": 0.0,
            "degraded_reason": None,
            "all_history": True,
            "range_start_ms": start_ms,
            "range_end_ms": end_ms,
            "page_size": 50,
            "preload_limit": limit,
        }
    except Exception as exc:
        failure_state = _record_closed_pnl_bybit_failure()
        degraded_suffix = (
            "; bybit_unavailable_5min_contact_operator"
            if failure_state["degraded_until_ms"] is not None
            else ""
        )
        try:
            payload = await asyncio.to_thread(
                _fetch_pg_closed_pnl_fallback,
                limit=limit,
                offset=0,
                symbol=sym,
                start_ms=start_ms,
                end_ms=end_ms,
                engine_modes=safe_modes,
            )
            payload["degraded_reason"] = (
                f"{payload.get('degraded_reason') or 'bybit_closed_pnl_unavailable'}"
                f"; bybit_failure_count_60s={failure_state['bybit_failure_count_60s']}"
                f"{degraded_suffix}"
            )
            payload.update(failure_state)
            payload.update({
                "all_history": True,
                "range_start_ms": start_ms,
                "range_end_ms": end_ms,
                "page_size": 50,
                "preload_limit": limit,
            })
            return payload
        except Exception as pg_exc:
            logger.exception("Bybit closed-pnl cursor mode and PG fallback both failed")
            from .error_sanitize import sanitize_exc_for_detail  # noqa: PLC0415
            raise HTTPException(
                status_code=502,
                detail=sanitize_exc_for_detail(pg_exc, "closed_pnl_unavailable"),
            ) from pg_exc


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
    from .paper_trading_routes import _ipc_command
    _require_demo_session_write(actor)
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
        # WP-05 Real Fix
        logger.exception("IPC close_position failed for %s", sym)
        from .error_sanitize import sanitize_exc_for_detail  # noqa: PLC0415
        raise HTTPException(
            status_code=502,
            detail=sanitize_exc_for_detail(exc, "ipc_error"),
        )

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
    from .paper_trading_routes import _ipc_command
    _require_demo_session_write(actor)
    errors: list[str] = []
    try:
        result = await _ipc_command("close_all_positions", {"engine": "demo"})
    except Exception as exc:
        # P2-WP05-FUP-1：client-facing error 用 stable reason_code，
        # 例外明細只進 log。
        logger.error("IPC close_all_positions failed: %s", exc)
        errors.append(f"ipc_close_all: {exc}")
        result = {"error": "ipc_close_all_failed"}
    # Orphan sweep: close exchange positions not tracked in paper_state.
    # IPC close_all only iterates paper_state — orphan positions (e.g. opened
    # externally or after paper_state reset) are silently skipped.
    # 孤兒清掃：IPC close_all 只遍歷 paper_state，交易所有但 paper_state
    # 沒有的倉位會被跳過。此處補掃確保全部平掉。
    orphan_result = await _sweep_demo_orphan_positions(errors)
    partial_failure = bool(errors) or bool(orphan_result.get("skipped")) or bool(result.get("error"))
    closed_all = not partial_failure
    logger.warning(
        "close-all-positions (manual) — closed_all=%s errors=%s actor=%s",
        closed_all,
        errors or None,
        getattr(actor, "actor_id", "?"),
    )
    return _envelope({
        "message": (
            "Close-all partially failed — session continues / 全平部分失敗，session 繼續運行"
            if partial_failure else
            "All positions closed — session continues / 已平掉所有倉位，session 繼續運行"
        ),
        "source": "rust_engine",
        "status": "partial_failure" if partial_failure else "closed",
        "closed_all": closed_all,
        "partial_failure": partial_failure,
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
        # P2-WP05-FUP-1：client 返 stable reason_code，例外只進 log。
        logger.warning("Orphan sweep: get_positions failed: %s", exc)
        errors.append(f"orphan_sweep_query: {exc}")
        return {"skipped": True, "reason": "orphan_sweep_query_failed"}

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
            errors.append(f"orphan_{sym}: {exc}")

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
        # P2-WP05-FUP-1：client 看 stable code，例外明細只進 log。
        logger.warning("%s order sweep: cancel-all failed: %s", env_label, exc)
        errors.append(f"order_sweep_{env_label}: {exc}")
        return {
            "skipped": True,
            "reason": "order_sweep_cancel_all_failed",
            "found": len(pre_orders),
        }
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
    _require_demo_session_write(actor)
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
    _require_demo_session_write(actor)
    _ipc_command = _ipc_command_sync_import()
    try:
        result = await _ipc_command("pause_paper", {"engine": "demo"})
    except Exception as exc:
        # WP-05 Real Fix
        logger.exception("IPC pause (demo) failed")
        from .error_sanitize import sanitize_exc_for_detail  # noqa: PLC0415
        raise HTTPException(
            status_code=502,
            detail=sanitize_exc_for_detail(exc, "ipc_error"),
        )
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
    _require_demo_session_write(actor)
    global _DEMO_USER_STOPPED
    _DEMO_USER_STOPPED = False
    _ipc_command = _ipc_command_sync_import()
    try:
        result = await _ipc_command("resume_paper", {"engine": "demo"})
    except Exception as exc:
        # WP-05 Real Fix
        logger.exception("IPC resume (demo) failed")
        from .error_sanitize import sanitize_exc_for_detail  # noqa: PLC0415
        raise HTTPException(
            status_code=502,
            detail=sanitize_exc_for_detail(exc, "ipc_error"),
        )
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
    _require_demo_session_write(actor)
    global _DEMO_USER_STOPPED
    _DEMO_USER_STOPPED = True
    errors: list[str] = []
    from .paper_trading_routes import get_rust_reader  # noqa: PLC0415
    _ipc_command = _ipc_command_sync_import()
    rust_online = get_rust_reader().is_available()
    close_result: dict = {}
    pause_result: dict = {}
    cancel_orders_result: dict = {}
    orphan_result: dict = {}
    verify_result: dict = {}
    if rust_online:
        # Phase 0 — Pause demo dispatch FIRST so no new orders are placed
        # during cancel + close. Demo session stop is allowed to pause the
        # pipeline (unlike Live which keeps the pipeline up).
        # 先暫停策略派發，避免 cancel/close 流程中再產生新單。
        try:
            pause_result = await _ipc_command("pause_paper", {"engine": "demo"})
        except Exception as e:
            errors.append(f"demo_pause: {e}")
            logger.error("IPC pause_paper (demo) failed: %s", e)
        # Phase 1 — Cancel all pending orders (limits / TP / SL / conditional)
        # via REST settleCoin scope BEFORE close_all to avoid TP/SL triggering
        # during the close-position window.
        # 第一步：先全帳戶取消掛單，避免平倉途中 TP/SL 條件單觸發。
        cancel_orders_result = await _sweep_demo_orphan_orders(errors)
        # Phase 2 — Close tracked positions via IPC (Rust paper_state iter).
        # 第二步：通過 IPC 平倉 paper_state 追蹤的持倉。
        try:
            close_result = await _ipc_command("close_all_positions", {"engine": "demo"})
        except Exception as e:
            errors.append(f"demo_close: {e}")
            logger.error("IPC close_all_positions (demo) failed: %s", e)
        # Phase 3 — Orphan position sweep: positions that exist on Bybit but
        # not in paper_state (e.g. opened externally) are caught here.
        # 第三步：孤兒倉位清掃，平掉交易所有但 paper_state 沒有的倉位。
        orphan_result = await _sweep_demo_orphan_positions(errors)
        # Phase 4 — Verify Bybit account fully clean (positions=0 AND orders=0).
        # Polls until clean or timeout (~30s default). Residual = explicit error
        # so GUI/operator sees what survived rather than silent partial-stop.
        # 第四步：輪詢確認 Bybit 帳戶完全乾淨。30s 內未清乾淨 → 顯式回報殘留。
        verify_result = await _verify_account_clean(_get_rust_client(), env_label="demo")
        if not verify_result.get("clean"):
            errors.append(
                f"demo_verify_residual: positions={verify_result.get('residual_positions')} "
                f"orders={verify_result.get('residual_orders')}"
            )
    else:
        errors.append("engine_offline")
        close_result = pause_result = orphan_result = {"skipped": True, "reason": "engine_offline"}
        cancel_orders_result = {"skipped": True, "reason": "engine_offline"}
        verify_result = {"skipped": True, "reason": "engine_offline"}
    partial_failure = bool(errors) or not verify_result.get("clean", False)
    closed_all = not partial_failure
    return _envelope({
        "message": (
            "Demo engine stopped with partial close failure / Demo 引擎已停止，但平倉存在部分失敗"
            if partial_failure else
            "Demo engine stopped — orders cancelled + positions closed / Demo 引擎已停止，掛單已取消、倉位已平"
        ),
        "source": "rust_engine",
        "status": "partial_failure" if partial_failure else "closed",
        "closed_all": closed_all,
        "partial_failure": partial_failure,
        "cancel_orders": cancel_orders_result,
        "demo_close": close_result,
        "orphan_sweep": orphan_result,
        "demo_pause": pause_result,
        "verify": verify_result,
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
async def get_demo_fills(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    side: str | None = Query(None),
    fast: bool = Query(False),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get Demo fill history. DB primary (has realized_pnl) / Bybit API fallback.
    獲取 Demo 成交歷史。DB 為主（帶 realized_pnl）/ Bybit API 備援。"""
    if fast is True:
        return _envelope(_demo_snapshot_fills_payload(limit=limit, offset=offset, side=side))

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
            cur.execute("SET LOCAL statement_timeout = %s", (_GUI_READ_STATEMENT_TIMEOUT_MS,))
            safe_side = side if side in {"Buy", "Sell"} else None
            where = "engine_mode IN (%s, %s)"
            params: list[Any] = ["demo", "live_demo"]
            if safe_side:
                where += " AND side = %s"
                params.append(safe_side)
            params.extend([limit + 1, offset])
            cur.execute(
                "SELECT ts, symbol, side, qty, price, fee, realized_pnl, strategy_name "
                f"FROM trading.fills WHERE {where} ORDER BY ts DESC LIMIT %s OFFSET %s",
                tuple(params),
            )
            rows = cur.fetchall()
            has_more = len(rows) > limit
            rows = rows[:limit]
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
            return _envelope({
                "list": fills,
                "count": len(fills),
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
                "next_offset": offset + len(fills) if has_more else None,
                "source": "pg_trading_fills",
            })
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
        safe_side = side if side in {"Buy", "Sell"} else None
        fetch_limit = min(max(limit + offset + 1, limit), 100)
        raw = [_normalize_execution(f) for f in rc.get_executions("linear", limit=fetch_limit)]
        if safe_side:
            raw = [f for f in raw if f.get("side") == safe_side]
        fills = raw[offset:offset + limit]
        return _envelope({
            "source": "rust_engine",
            "list": fills,
            "count": len(fills),
            "limit": limit,
            "offset": offset,
            "has_more": len(raw) > offset + limit,
            "next_offset": offset + len(fills) if len(raw) > offset + limit else None,
        })
    except Exception as exc:
        # WP-05 Real Fix
        logger.exception("Bybit fills fetch failed")
        from .error_sanitize import sanitize_exc_for_detail  # noqa: PLC0415
        raise HTTPException(
            status_code=502,
            detail=sanitize_exc_for_detail(exc, "bybit_api_failure"),
        )


@phase2_router.get("/demo/closed-pnl")
async def get_demo_closed_pnl(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    cursor: str | None = Query(None),
    start_time: int | None = Query(None),
    end_time: int | None = Query(None),
    symbol: str | None = Query(None),
    force_refresh: bool = Query(False),
    cursor_mode: bool = Query(False),
    lookback_days: int = Query(_CLOSED_PNL_ALL_HISTORY_DAYS, ge=1, le=_CLOSED_PNL_ALL_HISTORY_DAYS),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Bybit-first Demo closed PnL read model with PG fallback."""
    sym = symbol.upper().strip() if symbol else None
    cursor_token = cursor if isinstance(cursor, str) and cursor else None
    cursor_mode_enabled = cursor_mode is True or str(cursor_mode).lower() == "true"
    if cursor_mode_enabled or cursor_token:
        payload = await _closed_pnl_history_cursor_payload(
            rc=_get_rust_client(),
            limit=limit,
            cursor=cursor_token,
            symbol=sym,
            start_time=start_time,
            end_time=end_time,
            lookback_days=lookback_days,
            engine_modes=("demo", "live_demo"),
            client_unavailable_reason="bybit_client_unavailable",
        )
        return _envelope(payload)

    if not isinstance(start_time, (int, float, str)):
        start_time = None
    if not isinstance(end_time, (int, float, str)):
        end_time = None
    now_ms = int(time.time() * 1000)
    end_ms = int(end_time) if end_time is not None else (now_ms // 5000) * 5000
    start_ms = int(start_time) if start_time is not None else end_ms - 24 * 60 * 60 * 1000
    if end_ms < start_ms:
        raise HTTPException(status_code=400, detail="end_time must be >= start_time")
    if end_ms - start_ms > _CLOSED_PNL_MAX_WINDOW_MS:
        raise HTTPException(
            status_code=400,
            detail="Bybit closed-pnl query window must be <= 7 days",
        )
    rows_needed = offset + limit + 1
    cache_key = ("demo_closed_pnl", "linear", sym or "", start_ms, end_ms, rows_needed)
    rc = _get_rust_client()
    if rc is None:
        try:
            payload = await asyncio.to_thread(
                _fetch_pg_closed_pnl_fallback,
                limit=limit,
                offset=offset,
                symbol=sym,
                start_ms=start_ms,
                end_ms=end_ms,
            )
            pg_reason = payload.get("degraded_reason") or "pg_fallback"
            pg_reason = pg_reason.removeprefix("bybit_closed_pnl_unavailable; ")
            payload["degraded_reason"] = (
                f"bybit_client_unavailable; "
                f"{pg_reason}"
            )
            payload["bybit_failure_count_60s"] = 0
            payload["degraded_until_ms"] = None
            return _envelope(payload)
        except Exception:
            return _envelope({
                "enabled": False,
                "source": "pg_fallback",
                "source_ts": int(time.time() * 1000),
                "cache_age": None,
                "cache_age_seconds": None,
                "list": [],
                "count": 0,
                "limit": limit,
                "offset": offset,
                "has_more": False,
                "next_offset": None,
                "degraded_reason": "bybit_client_unavailable_and_pg_fallback_failed",
            })

    def _fetch_bybit_rows() -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        while len(rows) < rows_needed:
            page_limit = min(100, max(1, rows_needed - len(rows)))
            result = rc.get_closed_pnl(
                "linear",
                symbol=sym,
                start_time=start_ms,
                end_time=end_ms,
                limit=page_limit,
                cursor=cursor,
            )
            items = result.get("list") if isinstance(result, dict) else result
            if not isinstance(items, list):
                break
            rows.extend([dict(row) for row in items if isinstance(row, dict)])
            cursor = (
                result.get("nextPageCursor")
                if isinstance(result, dict)
                else None
            )
            if len(rows) >= rows_needed or not cursor:
                break
            if cursor in seen_cursors:
                logger.warning("Bybit closed-pnl returned repeated cursor; stopping pagination")
                break
            seen_cursors.add(cursor)
        return rows

    try:
        cached = await asyncio.to_thread(
            _closed_pnl_cache().get_or_fetch,
            cache_key,
            _fetch_bybit_rows,
            force_refresh=force_refresh,
        )
        if not cached.hit:
            _clear_closed_pnl_bybit_failures()
        enriched = await asyncio.to_thread(_attach_closed_pnl_strategy, cached.value)
        page = enriched[offset:offset + limit]
        has_more = len(enriched) > offset + limit
        return _envelope({
            "list": page,
            "count": len(page),
            "limit": limit,
            "offset": offset,
            "has_more": has_more,
            "next_offset": offset + len(page) if has_more else None,
            "source": "bybit_cached" if cached.hit else "bybit_api",
            "source_ts": cached.source_ts,
            "cache_age": cached.cache_age,
            "cache_age_seconds": cached.cache_age,
            "degraded_reason": None,
        })
    except Exception as exc:
        failure_state = _record_closed_pnl_bybit_failure()
        degraded_suffix = (
            "; bybit_unavailable_5min_contact_operator"
            if failure_state["degraded_until_ms"] is not None
            else ""
        )
        stale = _closed_pnl_cache().get_any(cache_key)
        if stale is not None:
            enriched = await asyncio.to_thread(_attach_closed_pnl_strategy, stale.value)
            page = enriched[offset:offset + limit]
            has_more = len(enriched) > offset + limit
            return _envelope({
                "list": page,
                "count": len(page),
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
                "next_offset": offset + len(page) if has_more else None,
                "source": "bybit_cached",
                "source_ts": stale.source_ts,
                "cache_age": stale.cache_age,
                "cache_age_seconds": stale.cache_age,
                "degraded_reason": (
                    f"bybit_fetch_failed_using_stale_cache: {type(exc).__name__}"
                    f"; bybit_failure_count_60s={failure_state['bybit_failure_count_60s']}"
                    f"{degraded_suffix}"
                ),
                **failure_state,
            })
        try:
            payload = await asyncio.to_thread(
                _fetch_pg_closed_pnl_fallback,
                limit=limit,
                offset=offset,
                symbol=sym,
                start_ms=start_ms,
                end_ms=end_ms,
            )
            payload["degraded_reason"] = (
                f"{payload.get('degraded_reason') or 'bybit_closed_pnl_unavailable'}"
                f"; bybit_failure_count_60s={failure_state['bybit_failure_count_60s']}"
                f"{degraded_suffix}"
            )
            payload.update(failure_state)
            return _envelope(payload)
        except Exception as pg_exc:
            logger.exception("Bybit closed-pnl and PG fallback both failed")
            from .error_sanitize import sanitize_exc_for_detail  # noqa: PLC0415
            raise HTTPException(
                status_code=502,
                detail=sanitize_exc_for_detail(pg_exc, "closed_pnl_unavailable"),
            )


@phase2_router.get("/demo/pnl-series")
async def get_demo_pnl_series(
    range_key: str = Query("24h", alias="range"),
    bucket_sec: int | None = Query(None, ge=60, le=86400),
    fast: bool = Query(False),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get Demo bucketed PnL series for GUI chart/table. / 獲取 Demo 分桶 PnL 序列。"""
    if fast is True:
        return _envelope(_demo_snapshot_pnl_series_payload(range_key=range_key, bucket_sec=bucket_sec))

    from .pnl_series import fetch_pnl_series  # noqa: PLC0415

    return _envelope(fetch_pnl_series(["demo"], range_key=range_key, bucket_sec=bucket_sec))


@phase2_router.get("/demo/metrics")
async def get_demo_metrics(
    fast: bool = Query(False),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get DB-truth Demo performance metrics. / 獲取 DB 真實 Demo 績效指標。"""
    if fast is True:
        return _envelope(_demo_snapshot_metrics_payload())

    from .trading_true_metrics import build_performance_metrics, fetch_db_true_metrics  # noqa: PLC0415

    full: dict[str, Any] = {}
    try:
        from .paper_trading_metrics import compute_full_metrics  # noqa: PLC0415
        from .paper_trading_routes import get_rust_reader  # noqa: PLC0415

        reader = get_rust_reader()
        if reader.is_engine_available("demo"):
            rust_state = reader.get_paper_state(engine="demo") or {}
            if rust_state:
                snap = (
                    reader.get_engine_snapshot("demo")
                    if hasattr(reader, "get_engine_snapshot")
                    else {}
                ) or {}
                fills = rust_state.get("fills") or snap.get("recent_fills") or []
                if fills:
                    full = compute_full_metrics({**rust_state, "fills": fills}, engine_mode="demo")
                else:
                    full = _demo_snapshot_metrics_payload()
    except Exception:
        logger.debug("Demo rust metrics fallback unavailable", exc_info=True)

    db_metrics = fetch_db_true_metrics(["demo"], edge_engine_modes=["demo"], window_days=7)
    total_ai_cost = _fetch_total_ai_cost_30d_safe()
    if total_ai_cost is not None:
        full["total_ai_cost"] = round(total_ai_cost, 6)
    full.update({
        "source": full.get("source", "db_true_metrics"),
        "db_true_metrics": db_metrics,
        "performance_metrics": build_performance_metrics(
            db_metrics,
            fallback_metrics=full,
            total_ai_cost=total_ai_cost,
        ),
    })
    return _envelope(full)


def _fetch_total_ai_cost_30d_safe() -> float | None:
    """Fetch AI cost for metrics without failing the Demo route.

    讀取 AI 成本供績效指標使用；失敗時不影響 Demo route。
    """
    try:
        from .paper_trading_ai_cost_routes import fetch_total_ai_cost_30d

        return fetch_total_ai_cost_30d()
    except Exception:
        logger.debug("AI cost lookup failed for demo metrics", exc_info=True)
        return None
