"""Demo 快照快讀 payload 組裝 — 純由 Rust paper_state 快照產生 GUI 形狀。

MODULE_NOTE
模塊用途：從 strategy_ai_routes 抽出的 Demo「fast」讀路徑 payload builders。
    這些函數只讀 Rust 引擎快照（paper_state / engine_snapshot），絕不碰
    PG 或 Bybit REST，供 GUI 低延遲面板（balance / positions / orders / fills /
    pnl-series / metrics）使用。route handler 在 fast=True 分支直接委派至此。
主要函數：
    _demo_snapshot_pair — 取 demo 引擎快照 + paper_state（不可用回空 dict）
    _paper_state_balance_payload / _paper_state_positions_for_gui — 餘額/持倉 GUI 形狀
    _demo_snapshot_fills_payload / _demo_snapshot_orders_payload — 成交/掛單快讀
    _demo_snapshot_pnl_series_payload / _demo_snapshot_metrics_payload — PnL 序列/績效快讀
    _normalize_order / _normalize_execution — Rust snake_case → Bybit camelCase 映射
    _num / _time_ms — 數值/時間戳 best-effort 解析
依賴：app.paper_trading_routes.get_rust_reader（懶加載）、
    app.trading_true_metrics.build_performance_metrics（懶加載）、time。
硬邊界：
    - 絕不觸發 PG / Bybit REST（fast 路徑契約）；快照不可用時 fail-soft 回空形狀。
    - 懶加載 get_rust_reader 在 module-level，測試 monkeypatch paper_trading_routes
      仍可生效（不破壞既有 fast-snapshot 測試語意）。
"""
from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


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
