#!/usr/bin/env python3
"""L1 short-exit replay for FlashDip shallow-K retune research.

This is the gate after `shallow_retune_execution_realism.py`.

The v245 execution-realism artifact found that K6/N2/C3/nf0.5% fails the
2-day exit, but intraday short exits may still carry edge. This script tests
that weaker hypothesis against recorder-v2 `market.l1_events` plus
`market.trades`:

  L1. did a deep maker buy at entry_level realistically fill;
  L2. did it fill by queue consumption or by adverse through-sweep;
  L3. does a taker sell at 15/60/240m still survive fees.

Hard boundary:
  - read-only PG through sibling `screen.py`;
  - no Bybit private/trading/auth APIs;
  - no strategy, risk, order, or runtime mutation;
  - writes only a local research artifact.

Output is counterfactual research. A green result can only feed formal
QC/MIT/AI-E review and a separate default-off implementation.
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import hashlib
import json
import math
import os
from typing import Any, Optional

import screen as base
import survival_safe as surv
import extend_history as ext
import prepilot_gates as gates
import shallow_retune_adversarial as adv

L1_REPLAY_VERSION = "tail_dislocation_meanrev.shallow_retune_l1_short_exit_replay.v0.1"

DEFAULT_K = 0.06
DEFAULT_HOLD = 2
DEFAULT_CAP: Optional[int] = 3
DEFAULT_NOTIONAL = 0.005
DEFAULT_HORIZON_MINUTES = (15, 60, 240)
DEFAULT_QUEUE_AHEAD_FRACS = (0.0, 0.5, 1.0)
DEFAULT_GATE_QUEUE_AHEAD_FRAC = 1.0
DEFAULT_GATE_HORIZON_MINUTES = 240
DEFAULT_MIN_FILLED = 30
DEFAULT_MIN_DAYS = 20
DEFAULT_MAKER_TIMEOUT_MINUTES = 24 * 60
DEFAULT_CLEAN_SINCE = "2026-06-17T14:25:00+02:00"
EPS = 1e-12


def _data_root() -> str:
    return os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")


def _parse_float_csv(raw: str) -> tuple[float, ...]:
    vals = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            vals.append(float(part))
    if not vals:
        raise ValueError(f"empty numeric CSV: {raw!r}")
    return tuple(vals)


def _parse_int_csv(raw: str) -> tuple[int, ...]:
    vals = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            vals.append(int(part))
    if not vals:
        raise ValueError(f"empty integer CSV: {raw!r}")
    return tuple(vals)


def _parse_cap(raw: str) -> Optional[int]:
    val = raw.strip().lower()
    if val in {"none", "unlimited", "inf", "all"}:
        return None
    return int(val)


def _parse_dt(raw: Optional[str]) -> Optional[dt.datetime]:
    if not raw:
        return None
    out = dt.datetime.fromisoformat(raw)
    if out.tzinfo is None:
        out = out.replace(tzinfo=dt.timezone.utc)
    return out.astimezone(dt.timezone.utc)


def _dt_to_ms(ts: dt.datetime) -> int:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    return int(ts.astimezone(dt.timezone.utc).timestamp() * 1000)


def _ms_to_dt(ms: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(int(ms) / 1000, dt.timezone.utc)


def _date_to_ms(date_iso: str) -> int:
    d = dt.date.fromisoformat(date_iso)
    return _dt_to_ms(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc))


def _add_days(date_iso: str, days: int) -> str:
    return (dt.date.fromisoformat(date_iso) + dt.timedelta(days=days)).isoformat()


def _iso_ms(ms: Optional[int]) -> Optional[str]:
    return _ms_to_dt(ms).isoformat() if ms is not None else None


def _summary(xs: list[float]) -> dict[str, Any]:
    vals = [float(x) for x in xs if x is not None and math.isfinite(float(x))]
    if not vals:
        return {"n": 0}
    vals.sort()
    def pct(q: float) -> float:
        if len(vals) == 1:
            return vals[0]
        idx = q * (len(vals) - 1)
        lo = int(math.floor(idx))
        hi = int(math.ceil(idx))
        if lo == hi:
            return vals[lo]
        frac = idx - lo
        return vals[lo] * (1 - frac) + vals[hi] * frac
    return {
        "n": len(vals),
        "mean": sum(vals) / len(vals),
        "p10": pct(0.10),
        "p50": pct(0.50),
        "p90": pct(0.90),
        "min": vals[0],
        "max": vals[-1],
        "pct_positive": sum(1 for x in vals if x > 0.0) / len(vals),
    }


def l1_date_range(conn) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("SELECT min(ts), max(ts), count(*) FROM market.l1_events")
        lo, hi, n = cur.fetchone()
    return {
        "first_l1_ts_ms": _dt_to_ms(lo) if lo else None,
        "last_l1_ts_ms": _dt_to_ms(hi) if hi else None,
        "first_l1_ts": lo.isoformat() if lo else None,
        "last_l1_ts": hi.isoformat() if hi else None,
        "n_l1_rows_total": int(n or 0),
    }


def build_daily_candidate_events(
    conn,
    *,
    k: float,
    hold: int,
    cap: Optional[int],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    merged, funding, btc_fwd, btc_regime, meta = gates.build_merged_klines(conn)
    raw = surv.build_events_stopped(
        merged,
        funding,
        btc_fwd,
        btc_regime,
        k=k,
        hold=hold,
        stop=None,
    )
    kept = surv.apply_concurrency_cap(raw, cap=cap)["kept"]
    return kept, {
        "n_raw": len(raw),
        "n_kept_after_cap": len(kept),
        "first_kept_entry_date": min((e["entry_date"] for e in kept), default=None),
        "last_kept_entry_date": max((e["entry_date"] for e in kept), default=None),
        "data_meta": meta,
    }


def filter_events_to_l1_window(
    events: list[dict[str, Any]],
    *,
    first_l1_ts_ms: Optional[int],
    last_l1_ts_ms: Optional[int],
    max_horizon_minutes: int,
) -> list[dict[str, Any]]:
    if first_l1_ts_ms is None or last_l1_ts_ms is None:
        return []
    out = []
    for event in events:
        start_ms = _date_to_ms(event["entry_date"])
        end_ms = _date_to_ms(_add_days(event["entry_date"], 1)) + max_horizon_minutes * 60 * 1000
        if end_ms < first_l1_ts_ms or start_ms > last_l1_ts_ms:
            continue
        out.append(event)
    return out


def load_l1_rows(
    conn,
    *,
    symbols: list[str],
    start_ms: int,
    end_ms: int,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    if not symbols:
        return {}, {"n_rows_raw": 0, "n_symbols": 0}
    rows_by_symbol: dict[str, list[dict[str, Any]]] = {}
    bad = 0
    crossed = 0
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ts, symbol, best_bid, bid_size, best_ask, ask_size, update_id, seq, is_snapshot "
            "FROM market.l1_events "
            "WHERE symbol = ANY(%s) AND ts >= %s AND ts < %s "
            "ORDER BY symbol ASC, ts ASC, update_id ASC",
            (symbols, _ms_to_dt(start_ms), _ms_to_dt(end_ms)),
        )
        for ts, sym, bid, bid_sz, ask, ask_sz, update_id, seq, is_snapshot in cur.fetchall():
            bid = float(bid)
            ask = float(ask)
            bid_sz = float(bid_sz)
            ask_sz = float(ask_sz)
            if not all(math.isfinite(v) and v > 0.0 for v in (bid, ask, bid_sz, ask_sz)):
                bad += 1
                continue
            if bid >= ask:
                crossed += 1
                continue
            row = {
                "ts_ms": _dt_to_ms(ts),
                "symbol": sym,
                "best_bid": bid,
                "bid_size": bid_sz,
                "best_ask": ask,
                "ask_size": ask_sz,
                "update_id": int(update_id),
                "seq": int(seq),
                "is_snapshot": bool(is_snapshot),
            }
            rows_by_symbol.setdefault(sym, []).append(row)
    all_ts = [r["ts_ms"] for rows in rows_by_symbol.values() for r in rows]
    return rows_by_symbol, {
        "n_rows_post_filter": len(all_ts),
        "n_bad_rows_dropped": bad,
        "n_crossed_rows_dropped": crossed,
        "n_symbols": len(rows_by_symbol),
        "first_loaded_ts": _iso_ms(min(all_ts)) if all_ts else None,
        "last_loaded_ts": _iso_ms(max(all_ts)) if all_ts else None,
    }


def load_trade_rows(
    conn,
    *,
    symbols: list[str],
    start_ms: int,
    end_ms: int,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    if not symbols:
        return {}, {"n_rows": 0, "n_symbols": 0}
    rows_by_symbol: dict[str, list[dict[str, Any]]] = {}
    bad = 0
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ts, symbol, side, price, qty "
            "FROM market.trades "
            "WHERE symbol = ANY(%s) AND ts >= %s AND ts < %s "
            "ORDER BY symbol ASC, ts ASC",
            (symbols, _ms_to_dt(start_ms), _ms_to_dt(end_ms)),
        )
        for ts, sym, side, price, qty in cur.fetchall():
            price = float(price)
            qty = float(qty)
            if side not in {"Buy", "Sell"} or not (math.isfinite(price) and price > 0.0 and math.isfinite(qty) and qty > 0.0):
                bad += 1
                continue
            rows_by_symbol.setdefault(sym, []).append({
                "ts_ms": _dt_to_ms(ts),
                "symbol": sym,
                "side": side,
                "price": price,
                "qty": qty,
            })
    all_ts = [r["ts_ms"] for rows in rows_by_symbol.values() for r in rows]
    return rows_by_symbol, {
        "n_rows": len(all_ts),
        "n_bad_rows_dropped": bad,
        "n_symbols": len(rows_by_symbol),
        "first_loaded_ts": _iso_ms(min(all_ts)) if all_ts else None,
        "last_loaded_ts": _iso_ms(max(all_ts)) if all_ts else None,
    }


def _asof_l1(rows: list[dict[str, Any]], ts_ms: int) -> Optional[dict[str, Any]]:
    if not rows:
        return None
    ts_arr = [r["ts_ms"] for r in rows]
    idx = bisect.bisect_right(ts_arr, ts_ms) - 1
    return rows[idx] if idx >= 0 else None


def replay_limit_buy_short_exit(
    event: dict[str, Any],
    l1_rows: list[dict[str, Any]],
    trade_rows: list[dict[str, Any]],
    *,
    queue_ahead_frac: float,
    horizon_minutes: tuple[int, ...],
    maker_timeout_minutes: int,
) -> dict[str, Any]:
    """Replay one deep passive buy and taker sell exits.

    The order is assumed to be resting from UTC day start. If the market trades
    through the level, it fills regardless of queue. If the level becomes best
    bid, queue-ahead starts as `queue_ahead_frac * bid_size`; same-side Sell
    prints at the level consume that queue.
    """
    rec: dict[str, Any] = {
        "symbol": event["symbol"],
        "entry_date": event["entry_date"],
        "entry_level": float(event["entry_level"]),
        "queue_ahead_frac": queue_ahead_frac,
        "fill_status": "NO_FILL",
        "fill_outcome": None,
        "fill_ts_ms": None,
        "fill_ts": None,
        "queue_touch_ts_ms": None,
        "queue_touch_ts": None,
        "q0_at_touch": None,
        "short_exit": {},
    }
    if not l1_rows:
        rec["fill_status"] = "NO_L1_ROWS"
        return rec

    limit = float(event["entry_level"])
    day_start = _date_to_ms(event["entry_date"])
    deadline = min(
        _date_to_ms(_add_days(event["entry_date"], 1)),
        day_start + maker_timeout_minutes * 60 * 1000,
    )
    l1 = [r for r in l1_rows if day_start <= r["ts_ms"] <= deadline]
    trades = [r for r in trade_rows if day_start <= r["ts_ms"] <= deadline]
    if not l1:
        rec["fill_status"] = "NO_L1_ROWS_IN_EVENT_WINDOW"
        return rec

    queue_active = False
    size_ahead = None
    prev_bid_size = None
    consumed_since_l1 = 0.0
    trade_i = 0
    fill_ts = None
    fill_outcome = None

    def fill(ts_ms: int, outcome: str):
        nonlocal fill_ts, fill_outcome
        fill_ts = int(ts_ms)
        fill_outcome = outcome

    for row in l1:
        ev_ts = int(row["ts_ms"])
        while trade_i < len(trades) and int(trades[trade_i]["ts_ms"]) <= ev_ts:
            tr = trades[trade_i]
            trade_i += 1
            if tr["side"] != "Sell":
                continue
            px = float(tr["price"])
            qty = float(tr["qty"])
            if px < limit * (1.0 - EPS):
                fill(tr["ts_ms"], "trade_through_fill")
                break
            if px <= limit * (1.0 + EPS) and queue_active:
                consumed_since_l1 += qty
                size_ahead = max(0.0, float(size_ahead) - qty)
                if size_ahead <= 0.0:
                    fill(tr["ts_ms"], "queue_fill")
                    break
        if fill_ts is not None:
            break

        bid = float(row["best_bid"])
        ask = float(row["best_ask"])
        bid_size = float(row["bid_size"])
        if ask <= limit * (1.0 + EPS) or bid < limit * (1.0 - EPS):
            fill(ev_ts, "book_through_fill")
            break

        at_bid = abs(bid - limit) <= max(abs(limit) * 1e-8, 1e-12)
        if at_bid:
            q_eff = queue_ahead_frac * bid_size
            if not queue_active:
                queue_active = True
                size_ahead = max(0.0, q_eff)
                rec["queue_touch_ts_ms"] = ev_ts
                rec["queue_touch_ts"] = _iso_ms(ev_ts)
                rec["q0_at_touch"] = bid_size
            else:
                size_ahead = max(float(size_ahead), q_eff)
            if prev_bid_size is not None:
                drop = prev_bid_size - bid_size
                cancel_ahead = max(0.0, drop - consumed_since_l1)
                size_ahead = max(0.0, float(size_ahead) - cancel_ahead)
            prev_bid_size = bid_size
            consumed_since_l1 = 0.0

    while fill_ts is None and trade_i < len(trades):
        tr = trades[trade_i]
        trade_i += 1
        if int(tr["ts_ms"]) > deadline:
            break
        if tr["side"] != "Sell":
            continue
        px = float(tr["price"])
        qty = float(tr["qty"])
        if px < limit * (1.0 - EPS):
            fill(tr["ts_ms"], "trade_through_fill")
            break
        if px <= limit * (1.0 + EPS) and queue_active:
            size_ahead = max(0.0, float(size_ahead) - qty)
            if size_ahead <= 0.0:
                fill(tr["ts_ms"], "queue_fill")
                break

    if fill_ts is None:
        return rec

    rec["fill_status"] = "FILLED"
    rec["fill_outcome"] = fill_outcome
    rec["fill_ts_ms"] = fill_ts
    rec["fill_ts"] = _iso_ms(fill_ts)
    for minutes in horizon_minutes:
        exit_ts = fill_ts + minutes * 60 * 1000
        exit_book = _asof_l1(l1_rows, exit_ts)
        if exit_book is None or int(exit_book["ts_ms"]) < fill_ts:
            rec["short_exit"][f"{minutes}m"] = {
                "status": "NO_EXIT_BOOK",
                "exit_ts": _iso_ms(exit_ts),
                "net_taker": None,
            }
            continue
        if int(exit_book["ts_ms"]) < exit_ts and int(exit_book["ts_ms"]) == int(l1_rows[-1]["ts_ms"]):
            rec["short_exit"][f"{minutes}m"] = {
                "status": "EXIT_HORIZON_BEYOND_L1_DATA",
                "exit_ts": _iso_ms(exit_ts),
                "exit_book_ts": _iso_ms(exit_book["ts_ms"]),
                "net_taker": None,
            }
            continue
        exit_bid = float(exit_book["best_bid"])
        markout_bps = (exit_bid / limit - 1.0) * 10000.0
        net_taker = (
            exit_bid / limit - 1.0
            - base.MAKER_FEE_BPS / 10000.0
            - base.TAKER_FEE_BPS / 10000.0
        )
        rec["short_exit"][f"{minutes}m"] = {
            "status": "OK",
            "exit_ts": _iso_ms(exit_ts),
            "exit_book_ts": _iso_ms(exit_book["ts_ms"]),
            "exit_bid": exit_bid,
            "markout_bps": markout_bps,
            "net_taker": net_taker,
        }
    return rec


def summarize_queue_horizons(
    records: list[dict[str, Any]],
    *,
    queue_ahead_frac: float,
    horizon_minutes: tuple[int, ...],
    notional_frac: float,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "queue_ahead_frac": queue_ahead_frac,
        "n_events": len(records),
        "n_filled": sum(1 for r in records if r["fill_status"] == "FILLED"),
        "n_distinct_filled_days": len({r["entry_date"] for r in records if r["fill_status"] == "FILLED"}),
        "fill_rate": (
            sum(1 for r in records if r["fill_status"] == "FILLED") / len(records)
        ) if records else None,
        "fill_outcomes": {},
        "horizons": {},
    }
    for r in records:
        if r["fill_status"] != "FILLED":
            continue
        outcome = r.get("fill_outcome") or "unknown"
        out["fill_outcomes"][outcome] = out["fill_outcomes"].get(outcome, 0) + 1
    for minutes in horizon_minutes:
        key = f"{minutes}m"
        evs = []
        nets = []
        markouts = []
        for r in records:
            h = (r.get("short_exit") or {}).get(key) or {}
            if h.get("status") != "OK" or h.get("net_taker") is None:
                continue
            evs.append({
                "symbol": r["symbol"],
                "entry_date": r["entry_date"],
                "l1_short_exit_net_taker": h["net_taker"],
            })
            nets.append(float(h["net_taker"]))
            if h.get("markout_bps") is not None:
                markouts.append(float(h["markout_bps"]))
        out["horizons"][key] = {
            "n_exit_measured": len(evs),
            "n_distinct_exit_days": len({e["entry_date"] for e in evs}),
            "mean_net_taker_per_trade": base._mean(nets) if nets else None,
            "pct_positive": (sum(1 for x in nets if x > 0.0) / len(nets)) if nets else None,
            "markout_bps": _summary(markouts),
            "fixed_notional": ext.fixed_notional_equity_curve(
                evs,
                ret_key="l1_short_exit_net_taker",
                notional_frac=notional_frac,
            ),
        }
    return out


def l1_short_exit_gate(
    queue_summaries: list[dict[str, Any]],
    *,
    gate_queue_ahead_frac: float,
    gate_horizon_minutes: int,
    min_filled: int,
    min_days: int,
) -> dict[str, Any]:
    gate = None
    horizon_key = f"{gate_horizon_minutes}m"
    for row in queue_summaries:
        if abs(float(row["queue_ahead_frac"]) - float(gate_queue_ahead_frac)) <= 1e-12:
            gate = row
            break
    reasons: list[str] = []
    if gate is None:
        reasons.append("gate_queue_missing")
        status = "L1_SHORT_EXIT_INSUFFICIENT_SAMPLE"
    else:
        h = (gate.get("horizons") or {}).get(horizon_key)
        if h is None:
            reasons.append("gate_horizon_missing")
        else:
            if int(h.get("n_exit_measured") or 0) < min_filled:
                reasons.append("gate_horizon_sample_below_min_filled")
            if int(h.get("n_distinct_exit_days") or 0) < min_days:
                reasons.append("gate_horizon_sample_below_min_days")
            fn = h.get("fixed_notional") or {}
            annret = fn.get("annualized_return")
            maxdd = fn.get("max_drawdown")
            if annret is not None and annret <= 0.0:
                reasons.append("gate_horizon_nonpositive_annret")
            if maxdd is not None and maxdd > surv.SURVIVABLE_MAXDD:
                reasons.append("gate_horizon_maxdd_not_survivable")
        if any(r in {"gate_horizon_nonpositive_annret", "gate_horizon_maxdd_not_survivable"} for r in reasons):
            status = "L1_SHORT_EXIT_BLOCKED"
        elif reasons:
            status = "L1_SHORT_EXIT_INSUFFICIENT_SAMPLE"
        else:
            status = "L1_SHORT_EXIT_CONDITIONAL_PASS"
    return {
        "status": status,
        "gate_queue_ahead_frac": gate_queue_ahead_frac,
        "gate_horizon_minutes": gate_horizon_minutes,
        "min_filled": min_filled,
        "min_days": min_days,
        "fail_reasons": reasons,
        "promotion_boundary": (
            "L1 short-exit replay is research only. This does not authorize "
            "live/demo parameter changes, order placement, restarts, or risk changes."
        ),
    }


def l1_candidate_coverage_summary(
    candidate_events: list[dict[str, Any]],
    l1_by_sym: dict[str, list[dict[str, Any]]],
    *,
    maker_timeout_minutes: int = DEFAULT_MAKER_TIMEOUT_MINUTES,
) -> dict[str, Any]:
    candidate_symbols = sorted({e["symbol"] for e in candidate_events})
    events_by_symbol: dict[str, int] = {sym: 0 for sym in candidate_symbols}
    days_by_symbol: dict[str, set[str]] = {sym: set() for sym in candidate_symbols}
    event_window_rows_by_symbol_date: dict[str, int] = {}
    missing_event_windows: list[dict[str, Any]] = []
    n_events_with_l1_in_event_window = 0
    days_with_l1_in_event_window: set[str] = set()
    days_missing_l1_in_event_window: set[str] = set()
    for event in candidate_events:
        sym = event["symbol"]
        events_by_symbol[sym] = events_by_symbol.get(sym, 0) + 1
        days_by_symbol.setdefault(sym, set()).add(event["entry_date"])
        day_start = _date_to_ms(event["entry_date"])
        deadline = min(
            _date_to_ms(_add_days(event["entry_date"], 1)),
            day_start + maker_timeout_minutes * 60 * 1000,
        )
        rows = l1_by_sym.get(sym, [])
        n_window_rows = sum(1 for row in rows if day_start <= int(row["ts_ms"]) <= deadline)
        key = f"{sym}:{event['entry_date']}"
        event_window_rows_by_symbol_date[key] = event_window_rows_by_symbol_date.get(key, 0) + n_window_rows
        if n_window_rows > 0:
            n_events_with_l1_in_event_window += 1
            days_with_l1_in_event_window.add(event["entry_date"])
        else:
            days_missing_l1_in_event_window.add(event["entry_date"])
            missing_event_windows.append({
                "symbol": sym,
                "entry_date": event["entry_date"],
                "entry_level": event.get("entry_level"),
            })
    l1_rows_by_symbol = {
        sym: len(rows)
        for sym, rows in sorted(l1_by_sym.items())
    }
    symbols_with_l1 = sorted(sym for sym in candidate_symbols if l1_rows_by_symbol.get(sym, 0) > 0)
    symbols_missing_l1 = sorted(sym for sym in candidate_symbols if l1_rows_by_symbol.get(sym, 0) <= 0)
    return {
        "n_candidate_events": len(candidate_events),
        "candidate_events_by_symbol": events_by_symbol,
        "candidate_days_by_symbol": {
            sym: len(days)
            for sym, days in sorted(days_by_symbol.items())
        },
        "event_window_maker_timeout_minutes": maker_timeout_minutes,
        "n_events_with_l1_in_event_window": n_events_with_l1_in_event_window,
        "n_events_missing_l1_in_event_window": len(candidate_events) - n_events_with_l1_in_event_window,
        "n_distinct_days_with_l1_in_event_window": len(days_with_l1_in_event_window),
        "n_distinct_days_missing_l1_in_event_window": len(days_missing_l1_in_event_window),
        "event_window_l1_rows_by_symbol_date": dict(sorted(event_window_rows_by_symbol_date.items())),
        "events_missing_l1_in_event_window_sample": missing_event_windows[:100],
        "symbols_with_l1": symbols_with_l1,
        "symbols_missing_l1": symbols_missing_l1,
        "l1_rows_by_symbol": l1_rows_by_symbol,
    }


def apply_l1_coverage_reasons(
    gate: dict[str, Any],
    coverage: dict[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []
    if int(coverage.get("n_candidate_events") or 0) > 0:
        if not coverage.get("symbols_with_l1"):
            reasons.append("no_l1_rows_for_candidate_window")
        elif coverage.get("symbols_missing_l1"):
            reasons.append("partial_l1_symbol_coverage")
        n_missing_event_windows = int(coverage.get("n_events_missing_l1_in_event_window") or 0)
        n_with_event_windows = int(coverage.get("n_events_with_l1_in_event_window") or 0)
        if n_missing_event_windows > 0 and coverage.get("symbols_with_l1"):
            if n_with_event_windows == 0:
                reasons.append("no_l1_rows_for_candidate_event_windows")
            elif "partial_l1_symbol_coverage" not in reasons:
                reasons.append("partial_l1_event_window_coverage")

    if not reasons:
        return gate

    out = dict(gate)
    merged_reasons = list(reasons)
    for reason in out.get("fail_reasons") or []:
        if reason not in merged_reasons:
            merged_reasons.append(reason)
    out["fail_reasons"] = merged_reasons
    if out.get("status") == "L1_SHORT_EXIT_CONDITIONAL_PASS":
        out["status"] = "L1_SHORT_EXIT_INSUFFICIENT_SAMPLE"
    return out


def run_l1_replay(
    conn,
    *,
    k: float = DEFAULT_K,
    hold: int = DEFAULT_HOLD,
    cap: Optional[int] = DEFAULT_CAP,
    notional_frac: float = DEFAULT_NOTIONAL,
    horizon_minutes: tuple[int, ...] = DEFAULT_HORIZON_MINUTES,
    queue_ahead_fracs: tuple[float, ...] = DEFAULT_QUEUE_AHEAD_FRACS,
    gate_queue_ahead_frac: float = DEFAULT_GATE_QUEUE_AHEAD_FRAC,
    gate_horizon_minutes: int = DEFAULT_GATE_HORIZON_MINUTES,
    min_filled: int = DEFAULT_MIN_FILLED,
    min_days: int = DEFAULT_MIN_DAYS,
    maker_timeout_minutes: int = DEFAULT_MAKER_TIMEOUT_MINUTES,
    clean_since: Optional[dt.datetime] = _parse_dt(DEFAULT_CLEAN_SINCE),
) -> dict[str, Any]:
    daily_events, daily_meta = build_daily_candidate_events(conn, k=k, hold=hold, cap=cap)
    l1_meta = l1_date_range(conn)
    max_horizon = max(horizon_minutes) if horizon_minutes else 0
    candidate_events = filter_events_to_l1_window(
        daily_events,
        first_l1_ts_ms=l1_meta.get("first_l1_ts_ms"),
        last_l1_ts_ms=l1_meta.get("last_l1_ts_ms"),
        max_horizon_minutes=max_horizon,
    )
    if candidate_events:
        start_ms = min(_date_to_ms(e["entry_date"]) for e in candidate_events)
        end_ms = max(_date_to_ms(_add_days(e["entry_date"], 1)) for e in candidate_events) + max_horizon * 60 * 1000
        if clean_since is not None:
            start_ms = max(start_ms, _dt_to_ms(clean_since))
        symbols = sorted({e["symbol"] for e in candidate_events})
    else:
        start_ms = end_ms = _dt_to_ms(dt.datetime.now(dt.timezone.utc))
        symbols = []
    l1_by_sym, loaded_l1_meta = load_l1_rows(conn, symbols=symbols, start_ms=start_ms, end_ms=end_ms)
    trades_by_sym, trades_meta = load_trade_rows(conn, symbols=symbols, start_ms=start_ms, end_ms=end_ms)
    l1_coverage = l1_candidate_coverage_summary(
        candidate_events,
        l1_by_sym,
        maker_timeout_minutes=maker_timeout_minutes,
    )

    records_by_queue: dict[float, list[dict[str, Any]]] = {float(q): [] for q in queue_ahead_fracs}
    for q in queue_ahead_fracs:
        for event in candidate_events:
            sym = event["symbol"]
            records_by_queue[float(q)].append(
                replay_limit_buy_short_exit(
                    event,
                    l1_by_sym.get(sym, []),
                    trades_by_sym.get(sym, []),
                    queue_ahead_frac=float(q),
                    horizon_minutes=horizon_minutes,
                    maker_timeout_minutes=maker_timeout_minutes,
                )
            )
    summaries = [
        summarize_queue_horizons(
            records_by_queue[float(q)],
            queue_ahead_frac=float(q),
            horizon_minutes=horizon_minutes,
            notional_frac=notional_frac,
        )
        for q in queue_ahead_fracs
    ]
    gate = l1_short_exit_gate(
        summaries,
        gate_queue_ahead_frac=gate_queue_ahead_frac,
        gate_horizon_minutes=gate_horizon_minutes,
        min_filled=min_filled,
        min_days=min_days,
    )
    gate = apply_l1_coverage_reasons(gate, l1_coverage)
    return {
        "version": L1_REPLAY_VERSION,
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "params": {
            "candidate_label": adv.candidate_label(k, hold, cap, notional_frac),
            "k": k,
            "k_pct": k * 100.0,
            "hold": hold,
            "cap": adv._cap_label(cap),
            "notional_frac": notional_frac,
            "horizon_minutes": list(horizon_minutes),
            "queue_ahead_fracs": list(queue_ahead_fracs),
            "gate_queue_ahead_frac": gate_queue_ahead_frac,
            "gate_horizon_minutes": gate_horizon_minutes,
            "min_filled": min_filled,
            "min_days": min_days,
            "maker_timeout_minutes": maker_timeout_minutes,
            "clean_since": clean_since.isoformat() if clean_since else None,
            "fee_model": {
                "maker_entry_bps": base.MAKER_FEE_BPS,
                "taker_exit_bps": base.TAKER_FEE_BPS,
            },
        },
        "daily_candidate": daily_meta,
        "l1_meta": l1_meta,
        "loaded_l1_meta": loaded_l1_meta,
        "l1_candidate_coverage": l1_coverage,
        "trades_meta": trades_meta,
        "candidate_overlap": {
            "n_events_l1_window": len(candidate_events),
            "n_distinct_days_l1_window": len({e["entry_date"] for e in candidate_events}),
            "symbols": symbols,
            "first_loaded_window_ts": _iso_ms(start_ms) if symbols else None,
            "last_loaded_window_ts": _iso_ms(end_ms) if symbols else None,
        },
        "queue_horizon_summary": summaries,
        "sample_records": {
            str(q): records_by_queue[q][:100]
            for q in sorted(records_by_queue)
        },
        "verdict": gate,
    }


def write_artifact(report: dict[str, Any], *, out_path: Optional[str]) -> str:
    if out_path is None:
        root = os.path.join(_data_root(), "research", "tail_dislocation_meanrev")
        os.makedirs(root, exist_ok=True)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = os.path.join(root, f"shallow_retune_l1_short_exit_replay_{stamp}.json")
    else:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    blob = json.dumps(report, indent=2, sort_keys=True, default=str)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(blob)
    sha = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    with open(out_path + ".sha256", "w", encoding="utf-8") as fh:
        fh.write(sha + "  " + os.path.basename(out_path) + "\n")
    return out_path


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Read-only L1 short-exit replay for FlashDip shallow retune candidates."
    )
    ap.add_argument("--out", default=None)
    ap.add_argument("--k-pct", type=float, default=DEFAULT_K * 100.0)
    ap.add_argument("--hold", type=int, default=DEFAULT_HOLD)
    ap.add_argument("--cap", default=str(DEFAULT_CAP))
    ap.add_argument("--notional-frac", type=float, default=DEFAULT_NOTIONAL)
    ap.add_argument("--horizon-minutes", default=",".join(str(x) for x in DEFAULT_HORIZON_MINUTES))
    ap.add_argument("--queue-ahead-fracs", default=",".join(str(x) for x in DEFAULT_QUEUE_AHEAD_FRACS))
    ap.add_argument("--gate-queue-ahead-frac", type=float, default=DEFAULT_GATE_QUEUE_AHEAD_FRAC)
    ap.add_argument("--gate-horizon-minutes", type=int, default=DEFAULT_GATE_HORIZON_MINUTES)
    ap.add_argument("--min-filled", type=int, default=DEFAULT_MIN_FILLED)
    ap.add_argument("--min-days", type=int, default=DEFAULT_MIN_DAYS)
    ap.add_argument("--maker-timeout-minutes", type=int, default=DEFAULT_MAKER_TIMEOUT_MINUTES)
    ap.add_argument("--clean-since", default=DEFAULT_CLEAN_SINCE)
    args = ap.parse_args(argv)

    conn = base.connect_pg()
    try:
        report = run_l1_replay(
            conn,
            k=args.k_pct / 100.0,
            hold=args.hold,
            cap=_parse_cap(args.cap),
            notional_frac=args.notional_frac,
            horizon_minutes=_parse_int_csv(args.horizon_minutes),
            queue_ahead_fracs=_parse_float_csv(args.queue_ahead_fracs),
            gate_queue_ahead_frac=args.gate_queue_ahead_frac,
            gate_horizon_minutes=args.gate_horizon_minutes,
            min_filled=args.min_filled,
            min_days=args.min_days,
            maker_timeout_minutes=args.maker_timeout_minutes,
            clean_since=_parse_dt(args.clean_since),
        )
    finally:
        conn.close()

    out = write_artifact(report, out_path=args.out)
    print(f"[{L1_REPLAY_VERSION}] artifact -> {out}")
    print(f"verdict={report['verdict']['status']} fail={report['verdict']['fail_reasons']}")
    print(
        "candidate_overlap="
        f"events={report['candidate_overlap']['n_events_l1_window']} "
        f"days={report['candidate_overlap']['n_distinct_days_l1_window']} "
        f"symbols={report['candidate_overlap']['symbols']}"
    )
    for row in report["queue_horizon_summary"]:
        h = (row.get("horizons") or {}).get(f"{args.gate_horizon_minutes}m") or {}
        fn = h.get("fixed_notional") or {}
        print(
            f"queue_frac={row['queue_ahead_frac']:g} "
            f"filled={row['n_filled']} "
            f"exit_measured={h.get('n_exit_measured')} "
            f"annret={fn.get('annualized_return')} "
            f"maxdd={fn.get('max_drawdown')}"
        )
    print("boundary=counterfactual_only_not_promotion_evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
