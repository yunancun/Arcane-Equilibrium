#!/usr/bin/env python3
"""REF-21 local ticker/orderbook recorder for future replay fidelity.

Bybit REST ticker/orderbook endpoints are current snapshots, not historical
endpoints. This cron records those snapshots into existing `market.*` tables so
future full-chain replay windows can consume real locally recorded BBO/spread
instead of synthetic spread assumptions.
"""

from __future__ import annotations

import argparse
import fcntl
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_API_ROOT = (
    REPO_ROOT / "program_code/exchange_connectors/bybit_connector/control_api_v1"
)
if str(CONTROL_API_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_API_ROOT))

from replay.bybit_public_client import ReplayBybitPublicClient  # noqa: E402


DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT")
SYMBOL_PRIORITY = {"BTCUSDT": 0, "ETHUSDT": 1}


@contextmanager
def process_lock(name: str):
    data_dir = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))
    lock_dir = data_dir / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / name
    with lock_path.open("w", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"[skip] {name} already held")
            raise SystemExit(0)
        yield


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    db: str
    user: str
    password: str


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def read_db_config(base: Path = REPO_ROOT) -> DbConfig:
    values: dict[str, str] = {}
    candidates = [base / "settings/environment_files/basic_system_services.env"]
    secrets_root = os.environ.get("OPENCLAW_SECRETS_ROOT")
    if secrets_root:
        candidates.append(Path(secrets_root) / "environment_files/basic_system_services.env")
    candidates.append(Path.home() / "BybitOpenClaw/secrets/environment_files/basic_system_services.env")
    for env_file in candidates:
        if not env_file.exists():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return DbConfig(
        host=os.environ.get("PG_HOST") or values.get("POSTGRES_HOST") or "127.0.0.1",
        port=int(os.environ.get("PG_PORT") or values.get("POSTGRES_PORT") or "5432"),
        db=os.environ.get("PG_DB") or values.get("POSTGRES_DB") or "trading_ai",
        user=os.environ.get("PG_USER") or values.get("POSTGRES_USER") or "trading_admin",
        password=os.environ.get("PG_PASSWORD") or values.get("POSTGRES_PASSWORD") or "",
    )


def connect_db(config: DbConfig):
    import psycopg2  # type: ignore[import]

    return psycopg2.connect(
        host=config.host,
        port=config.port,
        dbname=config.db,
        user=config.user,
        password=config.password,
        connect_timeout=5,
    )


def table_exists(cur: Any, schema: str, table: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        LIMIT 1;
        """,
        (schema, table),
    )
    return cur.fetchone() is not None


def latest_v058_symbols(cur: Any, *, category: str, max_symbols: int) -> list[str]:
    if not table_exists(cur, "market", "symbol_universe_snapshots"):
        return list(DEFAULT_SYMBOLS[:max_symbols])
    cur.execute(
        """
        WITH latest AS (
            SELECT DISTINCT ON (symbol)
                symbol,
                status,
                is_delisted_at_asof,
                delisted_at,
                ts
            FROM market.symbol_universe_snapshots
            WHERE exchange = 'bybit'
              AND category = %s
            ORDER BY symbol, ts DESC
        )
        SELECT symbol
        FROM latest
        WHERE NOT (
            is_delisted_at_asof
            AND COALESCE(delisted_at, ts) < now()
        )
        ORDER BY
            CASE symbol WHEN 'BTCUSDT' THEN 0 WHEN 'ETHUSDT' THEN 1 ELSE 2 END,
            symbol ASC
        LIMIT %s;
        """,
        (category, max_symbols),
    )
    rows = [str(row[0]).upper() for row in cur.fetchall()]
    return rows or list(DEFAULT_SYMBOLS[:max_symbols])


def to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def spread_bps(bid: float | None, ask: float | None) -> float | None:
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return None
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return None
    return ((ask - bid) / mid) * 10_000.0


def ticker_rows(
    *,
    tickers: Iterable[dict[str, Any]],
    symbols: set[str],
    asof: datetime,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in tickers:
        symbol = str(item.get("symbol") or "").upper()
        if symbol not in symbols:
            continue
        bid = to_float(item.get("bid1Price"))
        ask = to_float(item.get("ask1Price"))
        rows.append({
            "ts": asof,
            "symbol": symbol,
            "last_price": to_float(item.get("lastPrice")),
            "mark_price": to_float(item.get("markPrice")),
            "index_price": to_float(item.get("indexPrice")),
            "best_bid": bid,
            "best_ask": ask,
            "bid_size": to_float(item.get("bid1Size")),
            "ask_size": to_float(item.get("ask1Size")),
            "volume_24h": to_float(item.get("volume24h")),
            "turnover_24h": to_float(item.get("turnover24h")),
            "spread_bps": spread_bps(bid, ask),
            "open_interest": to_float(item.get("openInterest")),
            "funding_rate": to_float(item.get("fundingRate")),
        })
    rows.sort(key=lambda row: (SYMBOL_PRIORITY.get(str(row["symbol"]), 2), str(row["symbol"])))
    return rows


def parse_book_side(values: Any, limit: int) -> list[tuple[float, float]]:
    parsed: list[tuple[float, float]] = []
    if not isinstance(values, list):
        return parsed
    for item in values[:limit]:
        if not isinstance(item, list) or len(item) < 2:
            continue
        price = to_float(item[0])
        size = to_float(item[1])
        if price is None or size is None or price <= 0 or size < 0:
            continue
        parsed.append((price, size))
    return parsed


def orderbook_summary_row(
    *,
    symbol: str,
    payload: dict[str, Any],
    asof: datetime,
    limit: int,
) -> dict[str, Any] | None:
    bids = parse_book_side(payload.get("b"), limit)
    asks = parse_book_side(payload.get("a"), limit)
    if not bids or not asks:
        return None
    bid_depth = sum(size for _price, size in bids)
    ask_depth = sum(size for _price, size in asks)
    total_depth = bid_depth + ask_depth
    best_bid = bids[0][0]
    best_ask = asks[0][0]
    weighted_numerator = sum(price * size for price, size in bids + asks)
    weighted_mid = (weighted_numerator / total_depth) if total_depth > 0 else None
    ts = asof
    try:
        raw_ts = int(payload.get("ts") or 0)
    except (TypeError, ValueError):
        raw_ts = 0
    if raw_ts > 0:
        ts = datetime.fromtimestamp(raw_ts / 1000, tz=timezone.utc)
    return {
        "ts": ts,
        "symbol": symbol,
        "imbalance_ratio": (bid_depth / total_depth) if total_depth > 0 else None,
        "weighted_mid": weighted_mid,
        "spread_bps": spread_bps(best_bid, best_ask),
        "bid_depth_5": bid_depth,
        "ask_depth_5": ask_depth,
        "depth_ratio": (bid_depth / ask_depth) if ask_depth > 0 else None,
    }


def insert_ticker_rows(conn: Any, rows: list[dict[str, Any]]) -> int:
    from psycopg2.extras import execute_batch  # type: ignore[import]

    if not rows:
        return 0
    with conn.cursor() as cur:
        has_funding_rate = table_exists(cur, "market", "market_tickers")
        if has_funding_rate:
            cur.execute(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'market'
                  AND table_name = 'market_tickers'
                  AND column_name = 'funding_rate'
                LIMIT 1;
                """
            )
            has_funding_rate = cur.fetchone() is not None
        funding_col = ", funding_rate" if has_funding_rate else ""
        funding_value = ", %(funding_rate)s" if has_funding_rate else ""
        sql = f"""
        INSERT INTO market.market_tickers (
            ts, symbol, last_price, mark_price, index_price, best_bid, best_ask,
            bid_size, ask_size, volume_24h, turnover_24h, spread_bps, open_interest
            {funding_col}
        ) VALUES (
            %(ts)s, %(symbol)s, %(last_price)s, %(mark_price)s, %(index_price)s,
            %(best_bid)s, %(best_ask)s, %(bid_size)s, %(ask_size)s,
            %(volume_24h)s, %(turnover_24h)s, %(spread_bps)s, %(open_interest)s
            {funding_value}
        )
        ON CONFLICT DO NOTHING;
        """
        execute_batch(cur, sql, rows, page_size=500)
    return len(rows)


def insert_orderbook_rows(conn: Any, rows: list[dict[str, Any]]) -> int:
    from psycopg2.extras import execute_batch  # type: ignore[import]

    if not rows:
        return 0
    sql = """
    INSERT INTO market.ob_snapshots (
        ts, symbol, imbalance_ratio, weighted_mid, spread_bps,
        bid_depth_5, ask_depth_5, depth_ratio
    ) VALUES (
        %(ts)s, %(symbol)s, %(imbalance_ratio)s, %(weighted_mid)s,
        %(spread_bps)s, %(bid_depth_5)s, %(ask_depth_5)s, %(depth_ratio)s
    )
    ON CONFLICT DO NOTHING;
    """
    with conn.cursor() as cur:
        execute_batch(cur, sql, rows, page_size=500)
    return len(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--category", default=os.environ.get("OPENCLAW_REF21_RECORDER_CATEGORY", "linear"))
    parser.add_argument("--symbols", default=os.environ.get("OPENCLAW_REF21_RECORDER_SYMBOLS", ""))
    parser.add_argument("--max-symbols", type=int, default=int(os.environ.get("OPENCLAW_REF21_RECORDER_MAX_SYMBOLS", "10")))
    parser.add_argument("--orderbook-limit", type=int, default=int(os.environ.get("OPENCLAW_REF21_RECORDER_ORDERBOOK_LIMIT", "5")))
    return parser.parse_args()


def main() -> int:
    with process_lock("ref21_market_microstructure_recorder.lock"):
        args = parse_args()
        category = str(args.category).strip().lower()
        max_symbols = max(1, min(int(args.max_symbols), 50))
        orderbook_limit = max(1, min(int(args.orderbook_limit), 50))
        asof = datetime.now(tz=timezone.utc)
        conn = connect_db(read_db_config())
        try:
            with conn.cursor() as cur:
                symbols = parse_csv(args.symbols)
                if not symbols:
                    symbols = latest_v058_symbols(cur, category=category, max_symbols=max_symbols)
            symbols = [symbol.upper() for symbol in symbols[:max_symbols]]
            symbol_set = set(symbols)
            client = ReplayBybitPublicClient()
            tickers = client.fetch_tickers_sync(category=category)
            ticker_payload = ticker_rows(tickers=tickers, symbols=symbol_set, asof=asof)
            ob_payload: list[dict[str, Any]] = []
            for symbol in symbols:
                book = client.fetch_orderbook_sync(
                    category=category,
                    symbol=symbol,
                    limit=orderbook_limit,
                )
                row = orderbook_summary_row(
                    symbol=symbol,
                    payload=book,
                    asof=asof,
                    limit=orderbook_limit,
                )
                if row is not None:
                    ob_payload.append(row)
                time.sleep(0.01)
            print(
                "[summary] mode={} category={} symbols={} ticker_rows={} ob_rows={}".format(
                    "DRY_RUN" if args.dry_run else "APPLY",
                    category,
                    ",".join(symbols),
                    len(ticker_payload),
                    len(ob_payload),
                )
            )
            if args.dry_run:
                return 0
            inserted_tickers = insert_ticker_rows(conn, ticker_payload)
            inserted_books = insert_orderbook_rows(conn, ob_payload)
            conn.commit()
            data_dir = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))
            data_dir.mkdir(parents=True, exist_ok=True)
            (data_dir / "ref21_microstructure_recorder_last_run").touch()
            print(f"[applied] ticker_attempted={inserted_tickers} ob_attempted={inserted_books}")
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
