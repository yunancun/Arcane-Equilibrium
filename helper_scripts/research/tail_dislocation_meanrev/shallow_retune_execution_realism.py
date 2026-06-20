#!/usr/bin/env python3
"""Intraday execution-realism check for FlashDip shallow-K retunes.

This is the gate after `shallow_retune_adversarial.py`.

The daily research assumes a maker entry fills whenever daily low <= limit.
That can be too optimistic. This script intersects the survivor-first shallow
candidate with local 1m `market.klines` and asks:

  E1. did the intraday bar merely touch the limit, or move through it;
  E2. how much edge survives if fills require a through-buffer;
  E3. what is the post-fill short-horizon markout from the limit price.

Hard boundary:
  - read-only PG through sibling `screen.py`;
  - no Bybit private/trading/auth APIs;
  - no strategy, risk, order, or runtime mutation;
  - writes only a local research artifact.

Output remains counterfactual research. A green result can only feed formal
QC/MIT/AI-E review and a separate default-off demo implementation.
"""
from __future__ import annotations

import argparse
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

EXECUTION_REALISM_VERSION = "tail_dislocation_meanrev.shallow_retune_execution_realism.v0.2"

DEFAULT_K = 0.06
DEFAULT_HOLD = 2
DEFAULT_CAP: Optional[int] = 3
DEFAULT_NOTIONAL = 0.005
DEFAULT_TIMEFRAME = "1m"
DEFAULT_BUFFER_BPS = (0.0, 5.0, 10.0, 25.0, 50.0)
DEFAULT_MARKOUT_MINUTES = (5, 15, 30, 60, 240)
DEFAULT_GATE_BUFFER_BPS = 10.0
DEFAULT_MIN_FILLED = 30
DEFAULT_MIN_DAYS = 20


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


def _date_to_ms(date_iso: str) -> int:
    d = dt.date.fromisoformat(date_iso)
    return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000)


def _ms_to_date(open_ts_ms: int) -> str:
    return dt.datetime.fromtimestamp(int(open_ts_ms) / 1000, dt.timezone.utc).date().isoformat()


def _add_days(date_iso: str, days: int) -> str:
    return (dt.date.fromisoformat(date_iso) + dt.timedelta(days=days)).isoformat()


def _percentile(xs: list[float], q: float) -> Optional[float]:
    if not xs:
        return None
    vals = sorted(xs)
    if len(vals) == 1:
        return vals[0]
    idx = q * (len(vals) - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return vals[lo]
    frac = idx - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


def _summary(xs: list[float]) -> dict[str, Any]:
    vals = [float(x) for x in xs if x is not None and math.isfinite(float(x))]
    if not vals:
        return {"n": 0}
    return {
        "n": len(vals),
        "mean": sum(vals) / len(vals),
        "p10": _percentile(vals, 0.10),
        "p50": _percentile(vals, 0.50),
        "p90": _percentile(vals, 0.90),
        "min": min(vals),
        "max": max(vals),
        "pct_positive": sum(1 for x in vals if x > 0.0) / len(vals),
    }


def load_intraday_bars(
    conn,
    *,
    symbols: list[str],
    start_date: str,
    end_date: str,
    timeframe: str,
) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], dict[str, Any]]:
    """Load intraday klines grouped by (symbol, UTC date)."""
    if not symbols:
        return {}, {"n_rows": 0, "n_symbols": 0, "start_date": start_date, "end_date": end_date}
    start_ms = _date_to_ms(start_date)
    end_ms = _date_to_ms(_add_days(end_date, 1))
    by_day: dict[tuple[str, str], list[dict[str, Any]]] = {}
    bad = 0
    with conn.cursor() as cur:
        cur.execute(
            "SELECT symbol, open_ts_ms, open, high, low, close, volume, turnover "
            "FROM market.klines "
            "WHERE timeframe=%s AND symbol = ANY(%s) AND open_ts_ms >= %s AND open_ts_ms < %s "
            "ORDER BY symbol ASC, open_ts_ms ASC",
            (timeframe, symbols, start_ms, end_ms),
        )
        for sym, ts_ms, o, h, l, c, vol, turn in cur.fetchall():
            vals = [float(o), float(h), float(l), float(c)]
            if not all(math.isfinite(v) and v > 0.0 for v in vals):
                bad += 1
                continue
            row = {
                "symbol": sym,
                "open_ts_ms": int(ts_ms),
                "open": vals[0],
                "high": vals[1],
                "low": vals[2],
                "close": vals[3],
                "volume": float(vol) if vol is not None else None,
                "turnover": float(turn) if turn is not None else None,
            }
            by_day.setdefault((sym, _ms_to_date(int(ts_ms))), []).append(row)
    dates = sorted({d for _, d in by_day})
    return by_day, {
        "timeframe": timeframe,
        "n_rows": sum(len(v) for v in by_day.values()),
        "n_bad_rows": bad,
        "n_symbol_days": len(by_day),
        "n_symbols": len({s for s, _ in by_day}),
        "first_intraday_date": dates[0] if dates else None,
        "last_intraday_date": dates[-1] if dates else None,
        "requested_start_date": start_date,
        "requested_end_date": end_date,
    }


def intraday_fill_assessment(
    event: dict[str, Any],
    bars: list[dict[str, Any]],
    *,
    buffer_bps: float,
    markout_minutes: tuple[int, ...],
) -> Optional[dict[str, Any]]:
    """Return fill proxy and markouts for one event at one through-buffer."""
    if not bars:
        return None
    limit = float(event["entry_level"])
    threshold = limit * (1.0 - buffer_bps / 10000.0)
    first_idx = None
    for idx, bar in enumerate(bars):
        if float(bar["low"]) <= threshold:
            first_idx = idx
            break
    if first_idx is None:
        return None
    fill_bar = bars[first_idx]
    through_bps = max(0.0, (limit - float(fill_bar["low"])) / limit * 10000.0)
    fill_ts = int(fill_bar["open_ts_ms"])
    rec: dict[str, Any] = {
        "symbol": event["symbol"],
        "entry_date": event["entry_date"],
        "exit_date": event.get("exit_date"),
        "entry_level": limit,
        "execution_buffer_bps": buffer_bps,
        "first_fill_ts_ms": fill_ts,
        "first_fill_bar_low": float(fill_bar["low"]),
        "first_fill_bar_close": float(fill_bar["close"]),
        "through_bps": through_bps,
        "net_taker": event.get("net_taker"),
        "net_maker": event.get("net_maker"),
        "gross": event.get("gross"),
    }
    for minutes in markout_minutes:
        target = fill_ts + minutes * 60 * 1000
        horizon_bar = None
        for bar in bars[first_idx:]:
            if int(bar["open_ts_ms"]) <= target:
                horizon_bar = bar
            else:
                break
        if horizon_bar is None:
            rec[f"markout_bps@{minutes}m"] = None
            rec[f"short_exit_net_taker@{minutes}m"] = None
            continue
        markout_bps = (float(horizon_bar["close"]) / limit - 1.0) * 10000.0
        rec[f"markout_bps@{minutes}m"] = markout_bps
        rec[f"short_exit_net_taker@{minutes}m"] = (
            markout_bps / 10000.0
            - base.MAKER_FEE_BPS / 10000.0
            - base.TAKER_FEE_BPS / 10000.0
        )
    one_hour_end = fill_ts + 60 * 60 * 1000
    first_hour = [b for b in bars[first_idx:] if int(b["open_ts_ms"]) <= one_hour_end]
    if first_hour:
        rec["mae_60m_bps"] = (min(float(b["low"]) for b in first_hour) / limit - 1.0) * 10000.0
        rec["mfe_60m_bps"] = (max(float(b["high"]) for b in first_hour) / limit - 1.0) * 10000.0
    return rec


def _buffer_row(
    *,
    buffer_bps: float,
    daily_kept: list[dict[str, Any]],
    filled: list[dict[str, Any]],
    notional_frac: float,
    markout_minutes: tuple[int, ...],
) -> dict[str, Any]:
    fn = ext.fixed_notional_equity_curve(filled, ret_key="net_taker", notional_frac=notional_frac)
    n_days = len({r["entry_date"] for r in filled})
    row = {
        "execution_buffer_bps": buffer_bps,
        "n_daily_kept_with_intraday_day": len(daily_kept),
        "n_filled_proxy": len(filled),
        "n_distinct_filled_days": n_days,
        "fill_proxy_rate_vs_daily_kept": (len(filled) / len(daily_kept)) if daily_kept else None,
        "mean_net_taker_per_trade": base._mean([r["net_taker"] for r in filled]) if filled else None,
        "pct_positive": (sum(1 for r in filled if r.get("net_taker", 0.0) > 0.0) / len(filled)) if filled else None,
        "through_bps": _summary([r["through_bps"] for r in filled]),
        "mae_60m_bps": _summary([r["mae_60m_bps"] for r in filled if r.get("mae_60m_bps") is not None]),
        "mfe_60m_bps": _summary([r["mfe_60m_bps"] for r in filled if r.get("mfe_60m_bps") is not None]),
        "fixed_notional": fn,
    }
    row["markout_bps"] = {
        f"{m}m": _summary([r[f"markout_bps@{m}m"] for r in filled if r.get(f"markout_bps@{m}m") is not None])
        for m in markout_minutes
    }
    row["short_exit_horizons"] = {}
    for minutes in markout_minutes:
        key = f"short_exit_net_taker@{minutes}m"
        short_events = [dict(r, short_exit_net_taker=r[key]) for r in filled if r.get(key) is not None]
        row["short_exit_horizons"][f"{minutes}m"] = {
            "fee_model": {
                "maker_entry_bps": base.MAKER_FEE_BPS,
                "taker_exit_bps": base.TAKER_FEE_BPS,
            },
            "mean_net_taker_per_trade": base._mean([r["short_exit_net_taker"] for r in short_events])
            if short_events else None,
            "pct_positive": (
                sum(1 for r in short_events if r["short_exit_net_taker"] > 0.0) / len(short_events)
            ) if short_events else None,
            "fixed_notional": ext.fixed_notional_equity_curve(
                short_events,
                ret_key="short_exit_net_taker",
                notional_frac=notional_frac,
            ),
        }
    return row


def execution_realism_gate(
    buffer_rows: list[dict[str, Any]],
    *,
    gate_buffer_bps: float,
    min_filled: int,
    min_days: int,
) -> dict[str, Any]:
    """Pure reducer for the intraday execution-realism result."""
    by_buffer = {float(r["execution_buffer_bps"]): r for r in buffer_rows}
    touch = by_buffer.get(0.0)
    gate = by_buffer.get(float(gate_buffer_bps))
    reasons: list[str] = []
    if touch is None or int(touch.get("n_filled_proxy") or 0) < min_filled:
        reasons.append("touch_sample_below_min_filled")
    if touch is None or int(touch.get("n_distinct_filled_days") or 0) < min_days:
        reasons.append("touch_sample_below_min_days")
    if gate is None:
        reasons.append("gate_buffer_missing")
    else:
        if int(gate.get("n_filled_proxy") or 0) < min_filled:
            reasons.append("gate_buffer_sample_below_min_filled")
        if int(gate.get("n_distinct_filled_days") or 0) < min_days:
            reasons.append("gate_buffer_sample_below_min_days")
        fn = gate.get("fixed_notional") or {}
        annret = fn.get("annualized_return")
        maxdd = fn.get("max_drawdown")
        if annret is None or annret <= 0.0:
            reasons.append("gate_buffer_nonpositive_annret")
        if maxdd is None or maxdd > surv.SURVIVABLE_MAXDD:
            reasons.append("gate_buffer_maxdd_not_survivable")
    hard_fail = {
        "gate_buffer_nonpositive_annret",
        "gate_buffer_maxdd_not_survivable",
    }
    sample_fail = [r for r in reasons if "sample" in r or r == "gate_buffer_missing"]
    if any(r in hard_fail for r in reasons):
        status = "EXECUTION_REALISM_BLOCKED"
    elif sample_fail:
        status = "EXECUTION_REALISM_INSUFFICIENT_SAMPLE"
    else:
        status = "EXECUTION_REALISM_CONDITIONAL_PASS"
    return {
        "status": status,
        "gate_buffer_bps": gate_buffer_bps,
        "min_filled": min_filled,
        "min_days": min_days,
        "fail_reasons": reasons,
        "promotion_boundary": (
            "Execution-realism research only. This does not authorize live/demo "
            "parameter changes, order placement, restarts, or risk changes."
        ),
    }


def short_exit_opportunity_summary(
    buffer_rows: list[dict[str, Any]],
    *,
    min_filled: int,
    min_days: int,
) -> dict[str, Any]:
    """Summarize whether intraday exits show a separate research signal."""
    candidates: list[dict[str, Any]] = []
    for row in buffer_rows:
        if int(row.get("n_filled_proxy") or 0) < min_filled:
            continue
        if int(row.get("n_distinct_filled_days") or 0) < min_days:
            continue
        for horizon, stats in (row.get("short_exit_horizons") or {}).items():
            fn = stats.get("fixed_notional") or {}
            annret = fn.get("annualized_return")
            maxdd = fn.get("max_drawdown")
            if annret is None or maxdd is None:
                continue
            candidates.append({
                "execution_buffer_bps": row["execution_buffer_bps"],
                "horizon": horizon,
                "n_filled_proxy": row["n_filled_proxy"],
                "n_distinct_filled_days": row["n_distinct_filled_days"],
                "mean_net_taker_per_trade": stats.get("mean_net_taker_per_trade"),
                "pct_positive": stats.get("pct_positive"),
                "annualized_return": annret,
                "max_drawdown": maxdd,
                "survivable_maxdd": maxdd <= surv.SURVIVABLE_MAXDD,
            })
    if not candidates:
        return {
            "status": "SHORT_EXIT_NO_SAMPLE",
            "best": None,
            "n_positive_survivable": 0,
            "boundary": "Short-exit markout is research-only and cannot authorize parameter changes.",
        }
    positive_survivable = [
        c for c in candidates
        if c["annualized_return"] > 0.0 and c["survivable_maxdd"]
    ]
    best = max(candidates, key=lambda c: c["annualized_return"])
    return {
        "status": "SHORT_EXIT_RESEARCH_SIGNAL" if positive_survivable else "SHORT_EXIT_NO_SIGNAL",
        "best": best,
        "n_positive_survivable": len(positive_survivable),
        "top_positive_survivable": sorted(
            positive_survivable,
            key=lambda c: c["annualized_return"],
            reverse=True,
        )[:10],
        "boundary": "Short-exit markout is research-only and cannot authorize parameter changes.",
    }


def run_execution_realism(
    conn,
    *,
    k: float = DEFAULT_K,
    hold: int = DEFAULT_HOLD,
    cap: Optional[int] = DEFAULT_CAP,
    notional_frac: float = DEFAULT_NOTIONAL,
    timeframe: str = DEFAULT_TIMEFRAME,
    buffer_bps_grid: tuple[float, ...] = DEFAULT_BUFFER_BPS,
    markout_minutes: tuple[int, ...] = DEFAULT_MARKOUT_MINUTES,
    gate_buffer_bps: float = DEFAULT_GATE_BUFFER_BPS,
    min_filled: int = DEFAULT_MIN_FILLED,
    min_days: int = DEFAULT_MIN_DAYS,
) -> dict[str, Any]:
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
    if kept:
        start_date = min(e["entry_date"] for e in kept)
        end_date = max(e["entry_date"] for e in kept)
        symbols = sorted({e["symbol"] for e in kept})
    else:
        start_date = end_date = dt.datetime.now(dt.timezone.utc).date().isoformat()
        symbols = []
    intraday, intraday_meta = load_intraday_bars(
        conn,
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        timeframe=timeframe,
    )
    daily_with_intraday = [e for e in kept if (e["symbol"], e["entry_date"]) in intraday]
    filled_by_buffer: dict[float, list[dict[str, Any]]] = {float(b): [] for b in buffer_bps_grid}
    for e in daily_with_intraday:
        bars = intraday[(e["symbol"], e["entry_date"])]
        for buf in buffer_bps_grid:
            assessed = intraday_fill_assessment(
                e,
                bars,
                buffer_bps=float(buf),
                markout_minutes=markout_minutes,
            )
            if assessed is not None:
                filled_by_buffer[float(buf)].append(assessed)
    buffer_rows = [
        _buffer_row(
            buffer_bps=float(buf),
            daily_kept=daily_with_intraday,
            filled=filled_by_buffer[float(buf)],
            notional_frac=notional_frac,
            markout_minutes=markout_minutes,
        )
        for buf in buffer_bps_grid
    ]
    gate = execution_realism_gate(
        buffer_rows,
        gate_buffer_bps=gate_buffer_bps,
        min_filled=min_filled,
        min_days=min_days,
    )
    short_exit = short_exit_opportunity_summary(
        buffer_rows,
        min_filled=min_filled,
        min_days=min_days,
    )
    return {
        "version": EXECUTION_REALISM_VERSION,
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "params": {
            "candidate_label": adv.candidate_label(k, hold, cap, notional_frac),
            "k": k,
            "k_pct": k * 100.0,
            "hold": hold,
            "cap": adv._cap_label(cap),
            "notional_frac": notional_frac,
            "intraday_timeframe": timeframe,
            "buffer_bps_grid": list(buffer_bps_grid),
            "markout_minutes": list(markout_minutes),
            "gate_buffer_bps": gate_buffer_bps,
            "min_filled": min_filled,
            "min_days": min_days,
            "survivable_maxdd": surv.SURVIVABLE_MAXDD,
            "short_exit_fee_model": {
                "maker_entry_bps": base.MAKER_FEE_BPS,
                "taker_exit_bps": base.TAKER_FEE_BPS,
            },
        },
        "data_meta": meta,
        "intraday_meta": intraday_meta,
        "daily_candidate": {
            "n_raw": len(raw),
            "n_kept_after_cap": len(kept),
            "n_kept_with_intraday_day": len(daily_with_intraday),
            "intraday_coverage_rate_vs_kept": (len(daily_with_intraday) / len(kept)) if kept else None,
            "first_kept_entry_date": start_date,
            "last_kept_entry_date": end_date,
        },
        "buffer_sensitivity": buffer_rows,
        "short_exit_opportunity": short_exit,
        "verdict": gate,
    }


def write_artifact(report: dict[str, Any], *, out_path: Optional[str]) -> str:
    if out_path is None:
        root = os.path.join(_data_root(), "research", "tail_dislocation_meanrev")
        os.makedirs(root, exist_ok=True)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = os.path.join(root, f"shallow_retune_execution_realism_{stamp}.json")
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
        description="Read-only intraday execution-realism check for FlashDip shallow retune candidates."
    )
    ap.add_argument("--out", default=None)
    ap.add_argument("--k-pct", type=float, default=DEFAULT_K * 100.0)
    ap.add_argument("--hold", type=int, default=DEFAULT_HOLD)
    ap.add_argument("--cap", default=str(DEFAULT_CAP))
    ap.add_argument("--notional-frac", type=float, default=DEFAULT_NOTIONAL)
    ap.add_argument("--timeframe", default=DEFAULT_TIMEFRAME)
    ap.add_argument("--buffer-bps", default=",".join(str(x) for x in DEFAULT_BUFFER_BPS))
    ap.add_argument("--markout-minutes", default=",".join(str(x) for x in DEFAULT_MARKOUT_MINUTES))
    ap.add_argument("--gate-buffer-bps", type=float, default=DEFAULT_GATE_BUFFER_BPS)
    ap.add_argument("--min-filled", type=int, default=DEFAULT_MIN_FILLED)
    ap.add_argument("--min-days", type=int, default=DEFAULT_MIN_DAYS)
    args = ap.parse_args(argv)

    conn = base.connect_pg()
    try:
        report = run_execution_realism(
            conn,
            k=args.k_pct / 100.0,
            hold=args.hold,
            cap=_parse_cap(args.cap),
            notional_frac=args.notional_frac,
            timeframe=args.timeframe,
            buffer_bps_grid=_parse_float_csv(args.buffer_bps),
            markout_minutes=_parse_int_csv(args.markout_minutes),
            gate_buffer_bps=args.gate_buffer_bps,
            min_filled=args.min_filled,
            min_days=args.min_days,
        )
    finally:
        conn.close()

    out = write_artifact(report, out_path=args.out)
    print(f"[{EXECUTION_REALISM_VERSION}] artifact -> {out}")
    print(f"verdict={report['verdict']['status']} fail={report['verdict']['fail_reasons']}")
    short_exit = report.get("short_exit_opportunity") or {}
    best_short = short_exit.get("best") or {}
    if best_short:
        print(
            "short_exit_best="
            f"status={short_exit.get('status')} "
            f"buffer={best_short.get('execution_buffer_bps')}bps "
            f"horizon={best_short.get('horizon')} "
            f"annret={best_short.get('annualized_return')} "
            f"maxdd={best_short.get('max_drawdown')} "
            f"mean_net={best_short.get('mean_net_taker_per_trade')}"
        )
    for row in report["buffer_sensitivity"]:
        fn = row.get("fixed_notional") or {}
        print(
            f"buffer={row['execution_buffer_bps']:g}bps "
            f"filled={row['n_filled_proxy']} days={row['n_distinct_filled_days']} "
            f"fill_rate={row['fill_proxy_rate_vs_daily_kept']} "
            f"annret={fn.get('annualized_return')} maxdd={fn.get('max_drawdown')}"
        )
    print("boundary=counterfactual_only_not_promotion_evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
