from __future__ import annotations

"""Read-only PnL time series for Demo / Live GUI charts.

GUI 的 PnL 曲線不應再依賴最近 50 筆成交列表；快速成交時列表分頁會覆蓋圖形。
本模組直接從 DB 聚合 realized_pnl - fee + funding，提供可調時間範圍的只讀序列。
"""

import logging
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from . import db_pool

logger = logging.getLogger(__name__)

PNL_SERIES_RANGES: dict[str, int] = {
    "1h": 60 * 60,
    "6h": 6 * 60 * 60,
    "24h": 24 * 60 * 60,
    "7d": 7 * 24 * 60 * 60,
    "30d": 30 * 24 * 60 * 60,
}

_DEFAULT_BUCKETS: dict[str, int] = {
    "1h": 60,
    "6h": 5 * 60,
    "24h": 15 * 60,
    "7d": 60 * 60,
    "30d": 4 * 60 * 60,
}

_MAX_POINTS = 520


def fetch_pnl_series(
    engine_modes: Sequence[str],
    *,
    range_key: str = "24h",
    bucket_sec: int | None = None,
) -> dict[str, Any]:
    """Fetch bucketed net PnL series for the requested engine modes.

    讀取指定 engine modes 的分桶淨 PnL 序列。
    """
    modes = _clean_modes(engine_modes)
    key, range_sec = _normalize_range(range_key)
    bucket = _normalize_bucket(key, range_sec, bucket_sec)
    if not modes:
        return _empty_series(key, range_sec, bucket, "no_engine_modes")

    conn = None
    try:
        conn = db_pool.get_conn()
        if conn is None:
            return _empty_series(key, range_sec, bucket, "pg_unavailable")
        with conn.cursor() as cur:
            fill_buckets = _fetch_fill_buckets(cur, modes, range_sec, bucket)
            funding_buckets = _fetch_funding_buckets(cur, modes, range_sec, bucket)
        return _build_series(modes, key, range_sec, bucket, fill_buckets, funding_buckets)
    except Exception as exc:  # noqa: BLE001 - GUI metrics must fail soft
        logger.warning("PnL series query failed for %s: %s", modes, exc)
        return _empty_series(key, range_sec, bucket, f"{type(exc).__name__}: {exc}")
    finally:
        if conn is not None:
            db_pool.put_conn(conn)


def _clean_modes(modes: Sequence[str]) -> list[str]:
    out: list[str] = []
    for mode in modes:
        m = str(mode or "").strip()
        if m and m not in out:
            out.append(m)
    return out


def _normalize_range(range_key: str) -> tuple[str, int]:
    key = str(range_key or "24h").strip().lower()
    if key not in PNL_SERIES_RANGES:
        key = "24h"
    return key, PNL_SERIES_RANGES[key]


def _normalize_bucket(key: str, range_sec: int, bucket_sec: int | None) -> int:
    if bucket_sec is None:
        bucket = _DEFAULT_BUCKETS.get(key, 15 * 60)
    else:
        try:
            bucket = int(bucket_sec)
        except (TypeError, ValueError):
            bucket = _DEFAULT_BUCKETS.get(key, 15 * 60)
    bucket = max(60, min(bucket, 24 * 60 * 60))
    while range_sec / bucket > _MAX_POINTS:
        bucket *= 2
    return bucket


def _empty_series(key: str, range_sec: int, bucket_sec: int, reason: str) -> dict[str, Any]:
    now_ms = int(time.time() * 1000)
    return {
        "available": False,
        "source": "pg_trading_fills",
        "reason": reason,
        "range": key,
        "range_sec": range_sec,
        "bucket_sec": bucket_sec,
        "engine_modes": [],
        "from_ts_ms": now_ms - range_sec * 1000,
        "to_ts_ms": now_ms,
        "window_net_pnl": 0.0,
        "window_gross_pnl": 0.0,
        "window_fees": 0.0,
        "window_funding_pnl": 0.0,
        "fills": 0,
        "points": [],
    }


def _placeholders(n: int) -> str:
    return ", ".join(["%s"] * n)


def _fetch_fill_buckets(
    cur: Any,
    modes: list[str],
    range_sec: int,
    bucket_sec: int,
) -> dict[int, dict[str, float | int]]:
    mode_sql = _placeholders(len(modes))
    cur.execute(
        f"""
        SELECT
          to_timestamp(
            floor(extract(epoch from ts) / (%s)::double precision)
            * (%s)::double precision
          ) AS bucket_ts,
          COUNT(*)::int AS fills,
          COALESCE(SUM(realized_pnl), 0)::float8 AS gross_pnl,
          COALESCE(SUM(fee), 0)::float8 AS fees
        FROM trading.fills
        WHERE engine_mode IN ({mode_sql})
          AND ts >= now() - ((%s)::int * interval '1 second')
        GROUP BY bucket_ts
        ORDER BY bucket_ts ASC
        """,
        tuple([bucket_sec, bucket_sec, *modes, range_sec]),
    )
    out: dict[int, dict[str, float | int]] = {}
    for bucket_ts, fills, gross_pnl, fees in cur.fetchall() or []:
        epoch = _bucket_epoch(bucket_ts, bucket_sec)
        out[epoch] = {
            "fills": int(fills or 0),
            "gross_pnl": _as_float(gross_pnl),
            "fees": _as_float(fees),
        }
    return out


def _fetch_funding_buckets(
    cur: Any,
    modes: list[str],
    range_sec: int,
    bucket_sec: int,
) -> dict[int, float]:
    try:
        cur.execute("SELECT to_regclass('trading.funding_settlements') IS NOT NULL")
        exists = cur.fetchone()
        if not exists or not exists[0]:
            return {}
        mode_sql = _placeholders(len(modes))
        cur.execute(
            f"""
            SELECT
              to_timestamp(
                floor(extract(epoch from ts) / (%s)::double precision)
                * (%s)::double precision
              ) AS bucket_ts,
              COALESCE(SUM(amount), 0)::float8 AS funding_pnl
            FROM trading.funding_settlements
            WHERE engine_mode IN ({mode_sql})
              AND ts >= now() - ((%s)::int * interval '1 second')
            GROUP BY bucket_ts
            ORDER BY bucket_ts ASC
            """,
            tuple([bucket_sec, bucket_sec, *modes, range_sec]),
        )
        out: dict[int, float] = {}
        for bucket_ts, amount in cur.fetchall() or []:
            out[_bucket_epoch(bucket_ts, bucket_sec)] = _as_float(amount)
        return out
    except Exception:
        return {}


def _bucket_epoch(value: Any, bucket_sec: int) -> int:
    if isinstance(value, datetime):
        return int(value.timestamp() // bucket_sec) * bucket_sec
    try:
        ts = float(value)
    except (TypeError, ValueError):
        ts = time.time()
    return int(ts // bucket_sec) * bucket_sec


def _build_series(
    modes: list[str],
    key: str,
    range_sec: int,
    bucket_sec: int,
    fill_buckets: dict[int, dict[str, float | int]],
    funding_buckets: dict[int, float],
) -> dict[str, Any]:
    now_epoch = int(time.time())
    start_epoch = int((now_epoch - range_sec) // bucket_sec) * bucket_sec
    end_epoch = int(now_epoch // bucket_sec) * bucket_sec

    cumulative = 0.0
    window_net = 0.0
    window_gross = 0.0
    window_fees = 0.0
    window_funding = 0.0
    total_fills = 0
    points: list[dict[str, Any]] = []
    for epoch in range(start_epoch, end_epoch + bucket_sec, bucket_sec):
        fill = fill_buckets.get(epoch) or {}
        fills = int(fill.get("fills") or 0)
        gross = _as_float(fill.get("gross_pnl"))
        fees = _as_float(fill.get("fees"))
        funding = _as_float(funding_buckets.get(epoch))
        net = gross - fees + funding
        cumulative += net
        window_net += net
        window_gross += gross
        window_fees += fees
        window_funding += funding
        total_fills += fills
        points.append({
            "ts_ms": epoch * 1000,
            "bucket_start": datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat(),
            "fills": fills,
            "gross_pnl": round(gross, 6),
            "fees": round(fees, 6),
            "funding_pnl": round(funding, 6),
            "net_pnl": round(net, 6),
            "cumulative_net_pnl": round(cumulative, 6),
        })

    return {
        "available": True,
        "source": "pg_trading_fills",
        "range": key,
        "range_sec": range_sec,
        "bucket_sec": bucket_sec,
        "engine_modes": modes,
        "from_ts_ms": start_epoch * 1000,
        "to_ts_ms": end_epoch * 1000,
        "window_net_pnl": round(window_net, 6),
        "window_gross_pnl": round(window_gross, 6),
        "window_fees": round(window_fees, 6),
        "window_funding_pnl": round(window_funding, 6),
        "fills": total_fills,
        "points": points,
    }


def _as_float(value: Any) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return 0.0
    return out if out == out and out not in (float("inf"), float("-inf")) else 0.0
