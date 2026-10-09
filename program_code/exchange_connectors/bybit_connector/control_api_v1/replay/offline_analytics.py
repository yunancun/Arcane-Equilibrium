"""R8 本機逐筆分析；只讀回放 JSON，不接資料庫或 API。"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from .report_analytics import build_replay_result_analytics

RECONCILIATION_TOLERANCE = 1e-8
DAY_MS = 86_400_000


def _number(value: Any) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("non-finite report number")
    return result


def _schedule(hours: list[int]) -> list[int]:
    if not hours or any(type(h) is not int or h < 0 or h > 23 for h in hours):
        raise ValueError("funding hours must be nonempty UTC integer hours 0..23")
    return sorted(set(hours))


def crosses_funding(start: int, end: int, hours: list[int]) -> bool:
    """區間兩端均包含；恰好在結算點入場或出場也標記。"""
    if end < start:
        raise ValueError("holding interval ends before entry")
    for hour in _schedule(hours):
        point = (start // DAY_MS) * DAY_MS + hour * 3_600_000
        if point < start:
            point += DAY_MS
        if point <= end:
            return True
    return False


def analyze_report(payload: dict[str, Any], *, replay_end_ts_ms: int | None = None,
                   funding_hours: dict[str, list[int]] | None = None) -> dict[str, Any]:
    result = payload.get("result", payload)
    schedules = funding_hours or {}
    for hours in schedules.values():
        _schedule(hours)
    default_hours = schedules.get("*", [0, 8, 16])
    indexed = list(enumerate(result["fills"]))
    def timestamp(fill: dict[str, Any]) -> int:
        value = fill.get("effective_ts_ms")
        return int(fill["ts_ms"] if value is None else value)
    indexed.sort(key=lambda item: (timestamp(item[1]), item[0]))
    end = replay_end_ts_ms
    if end is None:
        end = payload.get("stage1", {}).get("replay_end_ts_ms")
    if end is None:
        match = re.fullmatch(r"on_tick:[^@]+@(-?\d+)", result.get("diagnostics", {}).get("last_action_label", ""))
        if match:
            end = int(match[1])
    positions: dict[str, dict[str, Any]] = {}
    trades: list[dict[str, Any]] = []
    zero_reasons: Counter[str] = Counter()
    total_fee = 0.0
    total_slippage = 0.0
    for index, fill in indexed:
        qty = _number(fill["qty"])
        fee = _number(fill.get("fee", 0))
        if qty < 0 or fee < 0:
            raise ValueError("negative quantity or fee")
        if qty == 0:
            if fee != 0:
                raise ValueError("zero quantity has a nonzero fee")
            zero_reasons[fill.get("fill_status", "zero_quantity")] += 1
            continue
        price = _number(fill["price"])
        bps = _number(fill.get("slippage_bps", 0))
        if price <= 0 or 1 + bps / 10000 <= 0:
            raise ValueError("invalid execution price or slippage")
        slip = abs(price - price / (1 + bps / 10000)) * qty
        total_fee += fee
        total_slippage += slip
        symbol, side, ts = fill["symbol"], fill["side"], timestamp(fill)
        if side not in ("long", "short"):
            raise ValueError("unknown fill side")
        position = positions.get(symbol)
        if position is None or position["side"] == side:
            lot = {"entry_ts_ms": ts, "qty": qty, "entry_price": price,
                   "entry_fee": fee, "entry_slippage_cost": slip, "fill_index": index}
            if position is None:
                positions[symbol] = {"side": side, "qty": qty, "price": price, "lots": [lot]}
            else:
                position["price"] = (position["price"] * position["qty"] + price * qty) / (position["qty"] + qty)
                position["qty"] += qty
                position["lots"].append(lot)
            continue
        if qty > position["qty"] + 1e-12:
            raise ValueError("opposite fill exceeds held quantity; ambiguous legacy reversal")
        quantity = min(qty, position["qty"])
        ratio = quantity / position["qty"]
        entry_fee = sum(lot["entry_fee"] * ratio for lot in position["lots"])
        entry_slip = sum(lot["entry_slippage_cost"] * ratio for lot in position["lots"])
        intervals = [{"entry_ts_ms": lot["entry_ts_ms"], "exit_ts_ms": ts,
                      "qty": lot["qty"] * ratio,
                      "crosses_funding": crosses_funding(lot["entry_ts_ms"], ts, schedules.get(symbol, default_hours))}
                     for lot in position["lots"]]
        gross = (price - position["price"]) * quantity * (1 if position["side"] == "long" else -1)
        net = gross - entry_fee - fee
        trades.append({"symbol": symbol, "direction": position["side"],
                       "entry_ts_ms": min(lot["entry_ts_ms"] for lot in position["lots"]),
                       "exit_ts_ms": ts, "qty": quantity, "entry_price": position["price"],
                       "exit_price": price, "entry_fee": entry_fee, "exit_fee": fee,
                       "fees": entry_fee + fee, "slippage_cost": entry_slip + slip,
                       "gross_pnl": gross, "net_pnl": net,
                       "net_return_bps": net / (position["price"] * quantity) * 10000,
                       "holding_intervals": intervals, "exit_fill_index": index,
                       "crosses_funding": any(i["crosses_funding"] for i in intervals)})
        position["qty"] -= quantity
        if position["qty"] <= 1e-12:
            del positions[symbol]
        else:
            for lot in position["lots"]:
                for key in ("qty", "entry_fee", "entry_slippage_cost"):
                    lot[key] *= 1 - ratio
    if positions and end is None:
        raise ValueError("open positions require replay_end_ts_ms from last event, not last fill")
    if end is not None and end < max((timestamp(f) for _, f in indexed if f["qty"] > 0), default=end):
        raise ValueError("replay end precedes last execution")
    unmatched = []
    for symbol, position in positions.items():
        lots = [{**lot, "crosses_funding": crosses_funding(lot["entry_ts_ms"], end, schedules.get(symbol, default_hours))}
                for lot in position["lots"]]
        unmatched.append({"symbol": symbol, "direction": position["side"], "qty": position["qty"],
                          "entry_price": position["price"], "entry_ts_ms": min(l["entry_ts_ms"] for l in lots),
                          "replay_end_ts_ms": end, "entry_fee": sum(l["entry_fee"] for l in lots),
                          "entry_slippage_cost": sum(l["entry_slippage_cost"] for l in lots),
                          "lots": lots, "crosses_funding": any(l["crosses_funding"] for l in lots)})
    closed_net = sum(t["net_pnl"] for t in trades)
    unmatched_effect = -sum(p["entry_fee"] for p in unmatched)
    reported = _number(result["pnl_summary"]["net_pnl"])
    residual = reported - closed_net - unmatched_effect
    if abs(residual) > RECONCILIATION_TOLERANCE:
        raise ValueError(f"net_pnl reconciliation residual {residual} exceeds {RECONCILIATION_TOLERANCE}")
    base = build_replay_result_analytics(payload)
    closed_count = sum(t["crosses_funding"] for t in trades)
    open_count = sum(p["crosses_funding"] for p in unmatched)
    return {"schema_version": 1, "round_trips": trades, "unmatched_fills": unmatched,
            "realized_balance_analytics": base, "realized_balance_curve": base.get("balance_curve", []),
            "includes_unrealized_pnl": False, "curve_kind": "realized_balance_only",
            "equity_curve_available": False,
            "curve_warning": "不含未實現損益；只在成交時變動，回撤可能低估持倉期間回撤。",
            "costs": {"fees": total_fee, "slippage_cost": total_slippage,
                      "slippage_already_in_fill_price": True},
            "reconciliation": {"completed_round_trip_net_pnl": closed_net,
                               "unmatched_balance_effect": unmatched_effect,
                               "residual": residual, "reported_net_pnl": reported,
                               "absolute_tolerance": RECONCILIATION_TOLERANCE},
            "zero_quantity_reasons": dict(zero_reasons),
            "funding": {"hours_utc": {"*": default_hours, **schedules}, "endpoints": "inclusive",
                        "completed_crossing_count": closed_count, "open_position_crossing_count": open_count,
                        "funding_crossed": bool(closed_count or open_count),
                        "funding_settled": False}}
