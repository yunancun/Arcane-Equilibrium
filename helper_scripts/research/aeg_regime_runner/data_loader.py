"""AEG regime runner read-only data loader.

MODULE_NOTE:
  模塊用途：從 ``market.klines`` 讀 daily close panel。此層只 SELECT，強制
    ``set_session(readonly=True)``，不寫 V127 表；寫庫在 ``db_writer.py`` 且需 CLI
    顯式 ``--write-db``。
"""

from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

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


def load_daily_closes(
    symbols: Sequence[str],
    *,
    window_start: dt.datetime,
    window_end: dt.datetime,
    closed_bar_cutoff: dt.datetime,
    lookback_days: int = 430,
    dsn: Optional[str] = None,
) -> dict[str, list[tuple[dt.datetime, float]]]:
    """讀 daily close panel，回 ``{symbol: [(signal_ts, close), ...]}``。

    ``signal_ts`` 優先採 daily kline ``close_ts_ms``；缺失時退到 ``ts + 1 day``。
    ``history_start`` 顯式用 lookback_days，避免 runner 在沒有足夠 prior context 時
    偷用 window 內未來分布補樣本。
    """
    if not symbols:
        return {}
    history_start = _utc(window_start) - dt.timedelta(days=int(lookback_days))
    conn = _connect(dsn, "aeg_regime_runner_read")
    try:
        out = {s: [] for s in symbols}
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT symbol,
                       COALESCE(to_timestamp(close_ts_ms / 1000.0), ts + INTERVAL '1 day') AS signal_ts,
                       close
                  FROM market.klines
                 WHERE timeframe = '1d'
                   AND symbol = ANY(%s)
                   AND ts >= %s
                   AND ts <= %s
                   AND COALESCE(to_timestamp(close_ts_ms / 1000.0), ts + INTERVAL '1 day') <= %s
                 ORDER BY symbol, signal_ts
                """,
                (
                    list(symbols),
                    history_start,
                    _utc(window_end),
                    _utc(closed_bar_cutoff),
                ),
            )
            for symbol, signal_ts, close in cur.fetchall():
                out.setdefault(symbol, []).append((_utc(signal_ts), float(close)))
        return out
    finally:
        conn.close()


def parse_symbols(value: str) -> list[str]:
    """CLI ``--symbols`` 解析；去重但保留排序。"""
    seen = set()
    out = []
    for part in value.split(","):
        sym = part.strip().upper()
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out
