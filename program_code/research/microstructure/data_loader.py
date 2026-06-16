"""microstructure.data_loader — read-only PG loader（$0 唯讀）。

MODULE_NOTE
模塊用途：
  載入 harness 計算所需的 market.trades / market.ob_top 切片。連線憑證走 libpq env
  （PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE）或 OPENCLAW_DATABASE_URL，
  禁硬編 trading_admin（跨平台 + 不洩 runtime cred）。

主要函數：
  - connect：psycopg2 連線（read-only session）。
  - resolve_window：把 --hours / --since / --until 解析成 (since_ts, until_ts)。
  - load_trades / load_obtop：參數化 SELECT，回 typed DataFrame（含 sgn 衍生）。

硬邊界：
  - 連線一律 set_session(readonly=True)，結構上禁任何寫入（fail-loud 若被誤用）。
  - 只 SELECT market.trades / market.ob_top；0 寫入、0 order path、0 market 表 mutate。
  - SQL 全參數化（%s / params），symbol 篩用 ANY(%s) 不用字串拼接。
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
import pandas as pd


def connect():
    """psycopg2 read-only 連線。

    憑證解析序（皆 libpq / env，禁硬編 user）：
      1. OPENCLAW_DATABASE_URL（若設）。
      2. 否則空 DSN（libpq 讀 PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE），
         與 cron wrapper export 的 PG* env + ssh trade-core 一致。
    set_session(readonly=True)：結構性禁寫，任何 INSERT/UPDATE 會被 PG 拒絕（fail-loud）。
    """
    import psycopg2

    dsn = os.environ.get("OPENCLAW_DATABASE_URL", "")
    conn = psycopg2.connect(dsn) if dsn else psycopg2.connect("")
    conn.set_session(readonly=True)
    return conn


def resolve_window(conn, hours: Optional[float], since: Optional[str], until: Optional[str]):
    """把窗參數解析成 (since_ts, until_ts)，皆 tz-aware UTC 或 None。

    優先序：
      - since/until（ISO8601 字串）若任一提供 → 用顯式邊界（另一邊 None = 開放）。
      - 否則 hours>0 → since = max(ts) - hours（相對最新資料，與 campaign-8 慣例一致）。
      - 皆無 / hours<=0 → 全量（since=until=None）。
    為什麼相對 max(ts) 而非 now()：資料可能滯後，相對最新一筆才取得到「最近 N 小時有資料的窗」。
    """
    def _parse(s: str) -> datetime:
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d

    if since is not None or until is not None:
        since_ts = _parse(since) if since else None
        until_ts = _parse(until) if until else None
        return since_ts, until_ts

    if hours and hours > 0:
        cur = conn.cursor()
        cur.execute("SELECT max(ts) FROM market.trades")
        row = cur.fetchone()
        cur.close()
        max_ts = row[0] if row else None
        if max_ts is None:
            return None, None
        if max_ts.tzinfo is None:
            max_ts = max_ts.replace(tzinfo=timezone.utc)
        return max_ts - timedelta(hours=hours), None

    return None, None


def _window_clause(since_ts, until_ts):
    """構造參數化 WHERE 子句片段 + params list。"""
    clauses, params = [], []
    if since_ts is not None:
        clauses.append("ts >= %s")
        params.append(since_ts)
    if until_ts is not None:
        clauses.append("ts < %s")
        params.append(until_ts)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def load_trades(conn, since_ts=None, until_ts=None) -> pd.DataFrame:
    """SELECT market.trades 切片 → typed DataFrame（含 native side label 的 sgn）。

    sgn = Buy:+qty / Sell:-qty（native exchange aggressor side 決定 OFI 符號）。
    """
    where, params = _window_clause(since_ts, until_ts)
    q = "SELECT ts,symbol,side,price,qty FROM market.trades" + where + " ORDER BY ts"
    df = pd.read_sql(q, conn, params=params or None)
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    for c in ["price", "qty"]:
        df[c] = df[c].astype(float)
    df["sgn"] = np.where(df["side"] == "Buy", df["qty"], -df["qty"])
    return df


def load_obtop(conn, since_ts=None, until_ts=None) -> pd.DataFrame:
    """SELECT market.ob_top 切片 → typed DataFrame（尚未 clean，呼叫端必過 clean_obtop）。"""
    where, params = _window_clause(since_ts, until_ts)
    q = ("SELECT ts,symbol,best_bid,bid_size,best_ask,ask_size FROM market.ob_top"
         + where + " ORDER BY ts")
    df = pd.read_sql(q, conn, params=params or None)
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    for c in ["best_bid", "bid_size", "best_ask", "ask_size"]:
        df[c] = df[c].astype(float)
    return df


def liquid_symbols(conn, since_ts=None, until_ts=None, min_trades: int = 500):
    """流動性入選 symbol：窗內 trade 數 >= min_trades（與 core.MIN_TRADES 對齊）。"""
    where, params = _window_clause(since_ts, until_ts)
    q = ("SELECT symbol FROM market.trades" + where
         + " GROUP BY symbol HAVING count(*) >= %s ORDER BY symbol")
    cur = conn.cursor()
    cur.execute(q, params + [min_trades])
    syms = [r[0] for r in cur.fetchall()]
    cur.close()
    return syms
