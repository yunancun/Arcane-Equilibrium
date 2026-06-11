"""AEG-S3 panel export read-only data loader."""

from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

from . import DEFAULT_ALPHA_HISTORY_RUN_ID, DEFAULT_REGIME_CLASSIFIER_VERSION

_STATEMENT_TIMEOUT_MS = 180000


def _connect(dsn: Optional[str], application_name: str):
    import psycopg2  # type: ignore

    if dsn is None:
        srv_root = Path(__file__).resolve().parents[3]
        helper_dir = srv_root / "helper_scripts"
        if str(helper_dir) not in sys.path:
            sys.path.insert(0, str(helper_dir))
        try:
            from lib.pg_connect import resolve_report_dsn  # type: ignore
            dsn = resolve_report_dsn()
        except Exception:
            dsn = os.environ.get("OPENCLAW_DATABASE_URL", "")
    conn = psycopg2.connect(dsn, application_name=application_name)
    conn.set_session(readonly=True)
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = %s", (_STATEMENT_TIMEOUT_MS,))
    return conn


def _utc(ts: dt.datetime) -> dt.datetime:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    return ts.astimezone(dt.timezone.utc)


def _window_clause(alias: str, start: Optional[dt.datetime], end: Optional[dt.datetime]) -> tuple[str, list]:
    clauses = []
    params: list = []
    if start is not None:
        clauses.append(f"{alias} >= %s")
        params.append(_utc(start))
    if end is not None:
        clauses.append(f"{alias} <= %s")
        params.append(_utc(end))
    return (" AND " + " AND ".join(clauses)) if clauses else "", params


def load_price_rows(
    conn,
    symbols: Sequence[str],
    *,
    timeframe: str = "1d",
    window_start: Optional[dt.datetime] = None,
    window_end: Optional[dt.datetime] = None,
) -> list[dict]:
    clause, params = _window_clause("ts", window_start, window_end)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT symbol,
                   COALESCE(to_timestamp(close_ts_ms / 1000.0), ts + INTERVAL '1 day') AS signal_ts,
                   ts::date AS date,
                   close
              FROM market.klines
             WHERE timeframe = %s
               AND symbol = ANY(%s)
               {clause}
             ORDER BY symbol, signal_ts
            """,
            [timeframe, list(symbols), *params],
        )
        return [
            {"symbol": sym, "ts_utc": _utc(signal_ts).isoformat(), "date": str(day), "close": float(close)}
            for sym, signal_ts, day, close in cur.fetchall()
            if close is not None
        ]


def load_oi_rows(
    conn,
    symbols: Sequence[str],
    *,
    run_id: str = DEFAULT_ALPHA_HISTORY_RUN_ID,
    category: str = "linear",
    interval_time: Optional[str] = "1h",
    window_start: Optional[dt.datetime] = None,
    window_end: Optional[dt.datetime] = None,
) -> list[dict]:
    clause, params = _window_clause("ts", window_start, window_end)
    interval_clause = "AND interval_time = %s" if interval_time else ""
    interval_params = [interval_time] if interval_time else []
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT symbol, ts, ts::date AS date, open_interest, interval_time, category
              FROM research.alpha_open_interest_history
             WHERE run_id = %s
               AND category = %s
               AND symbol = ANY(%s)
               {interval_clause}
               {clause}
             ORDER BY symbol, ts
            """,
            [run_id, category, list(symbols), *interval_params, *params],
        )
        return [
            {
                "symbol": sym,
                "ts_utc": _utc(ts).isoformat(),
                "date": str(day),
                "open_interest": float(oi),
                "interval_time": interval,
                "category": cat,
            }
            for sym, ts, day, oi, interval, cat in cur.fetchall()
            if oi is not None
        ]


def load_funding_rows(
    conn,
    symbols: Sequence[str],
    *,
    run_id: str = DEFAULT_ALPHA_HISTORY_RUN_ID,
    category: str = "linear",
    window_start: Optional[dt.datetime] = None,
    window_end: Optional[dt.datetime] = None,
) -> list[dict]:
    clause, params = _window_clause("funding_ts", window_start, window_end)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT symbol, funding_ts, funding_ts::date AS date,
                   funding_rate, funding_interval_minutes, category
              FROM research.alpha_funding_rates_history
             WHERE run_id = %s
               AND category = %s
               AND symbol = ANY(%s)
               {clause}
             ORDER BY symbol, funding_ts
            """,
            [run_id, category, list(symbols), *params],
        )
        return [
            {
                "symbol": sym,
                "funding_ts": _utc(ts).isoformat(),
                "date": str(day),
                "funding_rate": float(rate),
                "funding_interval_minutes": interval,
                "category": cat,
            }
            for sym, ts, day, rate, interval, cat in cur.fetchall()
            if rate is not None
        ]


def load_regime_rows(
    conn,
    symbols: Sequence[str],
    *,
    classifier_version: str = DEFAULT_REGIME_CLASSIFIER_VERSION,
    run_id: Optional[str] = None,
    timeframe: str = "1d",
    window_start: Optional[dt.datetime] = None,
    window_end: Optional[dt.datetime] = None,
) -> list[dict]:
    clause, params = _window_clause("signal_ts", window_start, window_end)
    run_clause = "AND run_id = %s" if run_id else ""
    run_params = [run_id] if run_id else []
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT DISTINCT ON (symbol, signal_ts::date)
                   symbol,
                   signal_ts::date AS date,
                   signal_ts,
                   main_regime,
                   market_anchor_regime,
                   run_id
              FROM research.aeg_regime_labels
             WHERE classifier_version = %s
               AND timeframe = %s
               AND symbol = ANY(%s)
               {run_clause}
               {clause}
             ORDER BY symbol, signal_ts::date, created_at DESC
            """,
            [classifier_version, timeframe, list(symbols), *run_params, *params],
        )
        rows = []
        for sym, day, signal_ts, main_regime, anchor_regime, regime_run_id in cur.fetchall():
            regime = anchor_regime if main_regime == "insufficient_context" and anchor_regime else main_regime
            rows.append({
                "symbol": sym,
                "date": str(day),
                "signal_ts": _utc(signal_ts).isoformat(),
                "regime": regime,
                "main_regime": main_regime,
                "market_anchor_regime": anchor_regime,
                "run_id": regime_run_id,
            })
        return rows


def load_export_sources(
    symbols: Sequence[str],
    *,
    dsn: Optional[str] = None,
    run_id: str = DEFAULT_ALPHA_HISTORY_RUN_ID,
    category: str = "linear",
    price_timeframe: str = "1d",
    oi_interval_time: Optional[str] = "1h",
    regime_classifier_version: str = DEFAULT_REGIME_CLASSIFIER_VERSION,
    regime_run_id: Optional[str] = None,
    regime_timeframe: str = "1d",
    window_start: Optional[dt.datetime] = None,
    window_end: Optional[dt.datetime] = None,
) -> dict[str, list[dict]]:
    conn = _connect(dsn, "aeg_s3_panel_export_read")
    try:
        return {
            "price_rows": load_price_rows(
                conn,
                symbols,
                timeframe=price_timeframe,
                window_start=window_start,
                window_end=window_end,
            ),
            "oi_rows": load_oi_rows(
                conn,
                symbols,
                run_id=run_id,
                category=category,
                interval_time=oi_interval_time,
                window_start=window_start,
                window_end=window_end,
            ),
            "funding_rows": load_funding_rows(
                conn,
                symbols,
                run_id=run_id,
                category=category,
                window_start=window_start,
                window_end=window_end,
            ),
            "regime_rows": load_regime_rows(
                conn,
                symbols,
                classifier_version=regime_classifier_version,
                run_id=regime_run_id,
                timeframe=regime_timeframe,
                window_start=window_start,
                window_end=window_end,
            ),
        }
    finally:
        conn.close()
