"""FND-2 唯讀資料載入 — lifecycle 聚合 + latest 投影 + tier 排序源 + scanner overlap。

MODULE_NOTE:
  模塊用途：從 PG **唯讀** SELECT FND-2 builder 所需資料，組成 ``SymbolLifecycle``
    list 餵 ``builder.build_universe``。本層只做 SELECT + 組 dataclass，**0 業務裁決**
    （裁決全在 builder 純函數，可 synthetic 測）。
  本 runtime 實況（2026-06-03 親驗，E1 不採信文檔）：
    - ``market.symbol_universe_snapshots``：508483 row / 937 distinct symbol；
      **snapshot ts 只跨 2026-05-07→2026-06-03（27 天）** → first_seen_ts/last_seen_ts
      僅診斷，**絕不**作 lifetime 邊界（builder Step D 已硬性）。
    - ``listed_at`` 跨 2018-01-01→2026-06-02、``delisted_at`` 跨 2022-02-14→
      2026-06-03 → lifetime 唯一權威。
    - USDT LinearPerpetual cohort：852 symbol（571 alive + 281 delisted）；status 枚舉
      只有 Trading/Closed/PreLaunch（無 Delivering/Settled/Delisted raw 值，故那些
      分支 dead-but-defensive）。lifecycle 欄 100% 內部一致（4 個矛盾檢查全 0）。
    - ``market.market_tickers``（symbol/turnover_24h/ts）+ ``trading.scanner_snapshots``
      （active_symbols text[]）皆存在 → tier 排序 + scanner overlap 可用；缺表時
      to_regclass guard 退化（symbol 仍 included）。
  主要函數：``load_lifecycles`` / ``_connect``。
  硬邊界：
    - **只 SELECT，絕不寫**。``conn.set_session(readonly=True)`` fail-closed（誤寫直接
      raise）。所有 query 參數化（``= ANY(%s)`` / ``= %s`` / ``ts <= %s``）。
    - DSN 用 ``lib.pg_connect.resolve_report_dsn()``（跨平台不硬編碼 host），與兩
      sibling harness 連線紀律一致。
    - **絕不**呼叫 ``_fetch_historical_universe_snapshot_sync``；universe SQL **無**
      ``LIMIT`` / ``max_symbols`` / turnover 截斷；market_tickers liquidity 只供 tier
      排序，非 inclusion 條件、非 PIT alpha feature（FND-2 §5 / contract §5）。
  依賴：psycopg2（延遲 import）。import-time 零 DB 依賴。
"""

from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path
from typing import Optional

from .builder import SymbolLifecycle, WindowSpec

_STATEMENT_TIMEOUT_MS = 180000

# delisted-proof 的 status 值（forward-defensive：現有資料只有 Closed，但未來可能
# 出現 Delivering/Settled/Delisted）。
_DELISTED_STATUSES = ("Delivering", "Closed", "Settled", "Delisted")


def _connect(dsn: Optional[str], application_name: str):
    """連 PG（唯讀）。優先 caller dsn，否則用共享 lib.pg_connect 解析。

    為什麼強制 readonly session：FND-2 是 read-only research，``set_session(readonly
    =True)`` 是 PG session-level fail-closed——任何意外寫（INSERT/UPDATE/DDL）直接被
    PG raise，機械化擋住誤寫（mirror multiday/data_loader.py:89）。
    """
    import psycopg2  # 延遲 import（import-time 零 DB 依賴）

    if dsn is None:
        # 復用 helper_scripts/lib/pg_connect.resolve_report_dsn（跨平台、不硬編碼 host）。
        srv_root = Path(__file__).resolve().parents[3]  # .../srv
        lib_dir = srv_root / "helper_scripts"
        if str(lib_dir) not in sys.path:
            sys.path.insert(0, str(lib_dir))
        try:
            from lib.pg_connect import resolve_report_dsn  # type: ignore
            dsn = resolve_report_dsn()
        except Exception:
            dsn = os.environ.get("OPENCLAW_DATABASE_URL", "")
    conn = psycopg2.connect(dsn, application_name=application_name)
    conn.set_session(readonly=True)  # 強制唯讀 session（fail-closed 防誤寫）
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = %s", (_STATEMENT_TIMEOUT_MS,))
    return conn


def load_lifecycles(
    window: WindowSpec,
    *,
    quote_coin: str = "USDT",
    contract_type: str = "LinearPerpetual",
    dsn: Optional[str] = None,
) -> list:
    """唯讀載入 USDT-perp lifecycle + latest + tier 源 + scanner overlap。

    回 ``list[SymbolLifecycle]``（per distinct symbol 一個），餵 ``build_universe``。
    """
    conn = _connect(dsn, "fnd2_pit_universe")
    try:
        lifecycle = _load_lifecycle_agg(conn, window, quote_coin, contract_type)
        latest = _load_latest_projection(conn, window, quote_coin, contract_type)
        turnover = _load_turnover(conn, window)
        scanner = _load_scanner_active(conn, window)
    finally:
        conn.close()

    out = []
    for symbol, agg in lifecycle.items():
        lat = latest.get(symbol, {})
        out.append(
            SymbolLifecycle(
                symbol=symbol,
                listed_at=agg["listed_at"],
                delisted_at=agg["delisted_at"],
                seen_delisted=agg["seen_delisted"],
                statuses_seen=tuple(agg["statuses_seen"]),
                first_seen_ts=agg["first_seen_ts"],
                last_seen_ts=agg["last_seen_ts"],
                status_raw=lat.get("status"),
                base_coin=lat.get("base_coin"),
                quote_coin=lat.get("quote_coin"),
                contract_type=lat.get("contract_type"),
                tick_size=lat.get("tick_size"),
                qty_step=lat.get("qty_step"),
                min_notional=lat.get("min_notional"),
                is_delisted_at_asof=bool(lat.get("is_delisted_at_asof")),
                source_uri=lat.get("source_uri"),
                source_snapshot_ts=lat.get("source_snapshot_ts"),
                source_payload_hash=lat.get("source_payload_hash"),
                turnover_24h=turnover.get(symbol),
                in_scanner_window=symbol in scanner,
            )
        )
    return out


def _load_lifecycle_agg(conn, window: WindowSpec, quote_coin: str, contract_type: str) -> dict:
    """Step A：per-symbol lifecycle 聚合（ts <= asof_utc，status 不過濾——含 Closed/PreLaunch）。

    為什麼 status 不過濾：contract §2「只查 Trading 失敗」——必須看到所有 status 才能
    證 delisted（Closed）+ PreLaunch metadata。
    """
    out: dict = {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              symbol,
              min(listed_at)   FILTER (WHERE listed_at IS NOT NULL)   AS listed_at,
              max(delisted_at) FILTER (WHERE delisted_at IS NOT NULL) AS delisted_at,
              bool_or(is_delisted_at_asof OR status = ANY(%s))        AS seen_delisted,
              array_agg(DISTINCT status)                              AS statuses_seen,
              min(ts) AS first_seen_ts,
              max(ts) AS last_seen_ts
            FROM market.symbol_universe_snapshots
            WHERE exchange = %s AND category = %s
              AND quote_coin = %s AND contract_type = %s
              AND ts <= %s
            GROUP BY symbol
            """,
            (
                list(_DELISTED_STATUSES),
                window.exchange, window.category,
                quote_coin, contract_type,
                window.asof_utc,
            ),
        )
        for symbol, listed_at, delisted_at, seen_delisted, statuses, first_ts, last_ts in cur.fetchall():
            out[symbol] = {
                "listed_at": listed_at,
                "delisted_at": delisted_at,
                "seen_delisted": bool(seen_delisted),
                "statuses_seen": sorted(s for s in (statuses or []) if s is not None),
                "first_seen_ts": first_ts,
                "last_seen_ts": last_ts,
            }
    return out


def _load_latest_projection(conn, window: WindowSpec, quote_coin: str, contract_type: str) -> dict:
    """Step B：latest 投影（DISTINCT ON (symbol) ORDER BY ts DESC，ts <= asof_utc）。

    payload_hash 是 bytea → ``encode(payload_hash,'hex')`` 成 text（PA §1.1）。
    """
    out: dict = {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (symbol)
              symbol, status, base_coin, quote_coin, contract_type,
              tick_size, qty_step, min_notional, is_delisted_at_asof,
              source_uri, ts, encode(payload_hash, 'hex')
            FROM market.symbol_universe_snapshots
            WHERE exchange = %s AND category = %s
              AND quote_coin = %s AND contract_type = %s
              AND ts <= %s
            ORDER BY symbol, ts DESC
            """,
            (
                window.exchange, window.category,
                quote_coin, contract_type,
                window.asof_utc,
            ),
        )
        for (symbol, status, base_coin, quote_coin_v, contract_type_v, tick_size,
             qty_step, min_notional, is_delisted, source_uri, ts, payload_hash_hex) in cur.fetchall():
            out[symbol] = {
                "status": status,
                "base_coin": base_coin,
                "quote_coin": quote_coin_v,
                "contract_type": contract_type_v,
                "tick_size": float(tick_size) if tick_size is not None else None,
                "qty_step": float(qty_step) if qty_step is not None else None,
                "min_notional": float(min_notional) if min_notional is not None else None,
                "is_delisted_at_asof": bool(is_delisted),
                "source_uri": source_uri,
                "source_snapshot_ts": ts,
                "source_payload_hash": payload_hash_hex,
            }
    return out


def _load_turnover(conn, window: WindowSpec) -> dict:
    """Step C：latest turnover_24h（read-only，**僅排序，絕不截斷、絕不 inclusion**）。

    has-table guard via to_regclass：缺 market_tickers → 回空 dict（builder tier 退為
    rank-unknown，symbol 仍 included；liquidity 缺 ≠ 排除）。
    為什麼 universe SQL 無 LIMIT：FND-2 §5 / contract §5——turnover 不得截斷 universe。
    """
    out: dict = {}
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('market.market_tickers')")
        if cur.fetchone()[0] is None:
            return out
        cur.execute(
            """
            SELECT DISTINCT ON (symbol) symbol, turnover_24h
            FROM market.market_tickers
            WHERE ts <= %s
            ORDER BY symbol, ts DESC
            """,
            (window.asof_utc,),
        )
        for symbol, turnover in cur.fetchall():
            out[symbol] = float(turnover) if turnover is not None else None
    return out


def _load_scanner_active(conn, window: WindowSpec) -> set:
    """Step G：latest scanner snapshot 的 active_symbols（asof overlap-only，<= asof_utc）。

    contract §1「scanner overlap 不足夠單用」——只標 in_scanner_window，非 inclusion。
    has-table guard：缺 scanner_snapshots → 空 set（in_scanner_window 全 false，不 fail）。
    active_symbols 是 text[]（親驗）→ 取最新一筆 snapshot 的陣列展開成 set。
    """
    out: set = set()
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('trading.scanner_snapshots')")
        if cur.fetchone()[0] is None:
            return out
        cur.execute(
            """
            SELECT active_symbols
            FROM trading.scanner_snapshots
            WHERE ts <= %s
            ORDER BY ts DESC
            LIMIT 1
            """,
            (window.asof_utc,),
        )
        row = cur.fetchone()
        if row and row[0]:
            out = {s for s in row[0] if s}
    return out


__all__ = ["load_lifecycles"]
