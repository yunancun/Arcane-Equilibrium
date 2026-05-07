"""Read-only recorder coverage estimates for REF-21 replay preflight.

The helpers in this module only inspect local market recorder tables. They do
not fetch Bybit public data, do not spawn replay, and do not touch strategy,
risk, demo, or live settings.
"""

from __future__ import annotations

import math
import os
from typing import Any, Callable


STATEMENT_TIMEOUT_MS = 3_000
S2_PLUS_BBO_COVERAGE_RATIO = 0.50
S1_BBO_COVERAGE_RATIO = 0.80
S1_ORDERBOOK_COVERAGE_RATIO = 0.80
S1_LIMITED_SAMPLE_COUNT = 30
S1_CALIBRATED_SAMPLE_COUNT = 200
DEFAULT_RECORDER_RETENTION_DAYS = 45
MIN_RECORDER_RETENTION_DAYS = 14

TIMEFRAME_INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


def estimate_replay_window_coverage_sync(
    *,
    get_pg_conn_fn: Callable[[], Any],
    symbols: list[str],
    start_ms: int,
    end_ms: int,
    timeframe: str,
) -> dict[str, Any]:
    clean_symbols = _clean_symbols(symbols)
    interval_ms = TIMEFRAME_INTERVAL_MS.get(timeframe, 60_000)
    bars_per_symbol = max(0, math.ceil((end_ms - start_ms) / interval_ms))
    expected_slots = bars_per_symbol * len(clean_symbols)
    retention_policy = _recorder_retention_policy(start_ms=start_ms, end_ms=end_ms)
    base = {
        "status": "empty" if not clean_symbols else "ok",
        "source": "local_market_recorder",
        "symbols": clean_symbols,
        "symbol_count": len(clean_symbols),
        "timeframe": timeframe,
        "window": {"start_ms": start_ms, "end_ms": end_ms},
        "expected_bars_per_symbol": bars_per_symbol,
        "expected_event_slots": expected_slots,
        "tables": {},
        "bbo": _coverage_block(0, expected_slots, "market.market_tickers"),
        "funding_rate": _coverage_block(0, expected_slots, "market.market_tickers"),
        "open_interest": _coverage_block(0, expected_slots, "market.market_tickers"),
        "index_price": _coverage_block(0, expected_slots, "market.market_tickers"),
        "orderbook_depth": _coverage_block(0, expected_slots, "market.ob_snapshots"),
        "instrument_specs": _coverage_block(0, len(clean_symbols), "market.symbol_universe_snapshots"),
        "retention_policy": retention_policy,
        "reason": None,
    }
    if not clean_symbols:
        return {**base, "reason": "empty_symbols"}

    try:
        conn_ctx = get_pg_conn_fn()
        if conn_ctx is None:
            return _unavailable(base, "pg_unavailable")
        with conn_ctx as conn:
            if conn is None:
                return _unavailable(base, "pg_unavailable")
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout = %s;", (STATEMENT_TIMEOUT_MS,))
                tables = _table_presence(cur)
                base["tables"] = tables
                ticker = _ticker_coverage(
                    cur=cur,
                    table_exists=bool(tables["market.market_tickers"]["exists"]),
                    symbols=clean_symbols,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    interval_ms=interval_ms,
                    expected_slots=expected_slots,
                )
                orderbook = _orderbook_coverage(
                    cur=cur,
                    table_exists=bool(tables["market.ob_snapshots"]["exists"]),
                    symbols=clean_symbols,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    interval_ms=interval_ms,
                    expected_slots=expected_slots,
                )
                specs = _instrument_spec_coverage(
                    cur=cur,
                    table_exists=bool(
                        tables["market.symbol_universe_snapshots"]["exists"]
                    ),
                    symbols=clean_symbols,
                    end_ms=end_ms,
                )
                base.update(ticker)
                base["orderbook_depth"] = orderbook
                base["instrument_specs"] = specs
    except Exception as exc:  # noqa: BLE001
        return _unavailable(base, type(exc).__name__, message=str(exc))

    return base


def build_replay_coverage_verdict(
    *,
    recorder_coverage: dict[str, Any],
    execution_calibration: dict[str, Any],
) -> dict[str, Any]:
    bbo_ratio = _ratio(recorder_coverage.get("bbo"))
    orderbook_ratio = _ratio(recorder_coverage.get("orderbook_depth"))
    tick_ratio = _ratio(recorder_coverage.get("instrument_specs"))
    maker_samples = int(execution_calibration.get("maker_order_sample_count") or 0)
    slippage_samples = int(execution_calibration.get("slippage_sample_count") or 0)
    min_samples = min(maker_samples, slippage_samples)
    retention_policy = recorder_coverage.get("retention_policy")
    if not isinstance(retention_policy, dict):
        retention_policy = {}
    reason_codes: list[str] = []
    if bbo_ratio < S2_PLUS_BBO_COVERAGE_RATIO:
        reason_codes.append("bbo_coverage_below_s2_plus")
    if bbo_ratio < S1_BBO_COVERAGE_RATIO:
        reason_codes.append("bbo_coverage_below_s1")
    if orderbook_ratio < S1_ORDERBOOK_COVERAGE_RATIO:
        reason_codes.append("orderbook_coverage_below_s1")
    if tick_ratio < 1.0:
        reason_codes.append("tick_size_coverage_incomplete")
    if min_samples < S1_LIMITED_SAMPLE_COUNT:
        reason_codes.append("execution_samples_below_s1_limited")
    elif min_samples < S1_CALIBRATED_SAMPLE_COUNT:
        reason_codes.append("execution_samples_below_s1_calibrated")
    if retention_policy.get("status") not in (None, "ok"):
        reason_codes.append(str(retention_policy.get("reason") or "recorder_retention_policy_warning"))

    if (
        bbo_ratio >= S1_BBO_COVERAGE_RATIO
        and orderbook_ratio >= S1_ORDERBOOK_COVERAGE_RATIO
        and min_samples >= S1_CALIBRATED_SAMPLE_COUNT
    ):
        tier = "S1_CALIBRATED_READY"
        verdict = "calibrated_advisory_ready"
    elif bbo_ratio >= S1_BBO_COVERAGE_RATIO and min_samples >= S1_LIMITED_SAMPLE_COUNT:
        tier = "S1_LIMITED_READY"
        verdict = "limited_advisory_ready"
    elif bbo_ratio >= S2_PLUS_BBO_COVERAGE_RATIO:
        tier = "S2_PLUS_LOCAL_BBO"
        verdict = "development_sandbox_with_local_bbo"
    else:
        tier = "S2_PUBLIC_KLINE_ONLY"
        verdict = "development_sandbox_only"

    return {
        "tier": tier,
        "verdict": verdict,
        "reason_codes": reason_codes,
        "thresholds": {
            "s2_plus_bbo_coverage_ratio": S2_PLUS_BBO_COVERAGE_RATIO,
            "s1_bbo_coverage_ratio": S1_BBO_COVERAGE_RATIO,
            "s1_orderbook_coverage_ratio": S1_ORDERBOOK_COVERAGE_RATIO,
            "s1_limited_sample_count": S1_LIMITED_SAMPLE_COUNT,
            "s1_calibrated_sample_count": S1_CALIBRATED_SAMPLE_COUNT,
            "min_recorder_retention_days": MIN_RECORDER_RETENTION_DAYS,
        },
        "inputs": {
            "bbo_coverage_ratio": bbo_ratio,
            "orderbook_depth_coverage_ratio": orderbook_ratio,
            "tick_size_coverage_ratio": tick_ratio,
            "maker_order_sample_count": maker_samples,
            "slippage_sample_count": slippage_samples,
            "retention_policy": retention_policy,
        },
    }


def _clean_symbols(symbols: list[str]) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for item in symbols:
        symbol = str(item).strip().upper()
        if symbol and symbol not in seen:
            cleaned.append(symbol)
            seen.add(symbol)
    return cleaned


def _coverage_block(covered: int, expected: int, source: str) -> dict[str, Any]:
    ratio = min(1.0, covered / expected) if expected > 0 else 0.0
    return {
        "status": "ok" if covered else "empty",
        "source": source,
        "covered_event_slots": covered,
        "expected_event_slots": expected,
        "coverage_ratio": ratio,
    }


def _configured_recorder_retention_days() -> int:
    raw = os.environ.get(
        "OPENCLAW_REF21_RECORDER_RETENTION_DAYS",
        str(DEFAULT_RECORDER_RETENTION_DAYS),
    )
    try:
        parsed = int(raw)
    except ValueError:
        parsed = DEFAULT_RECORDER_RETENTION_DAYS
    return max(MIN_RECORDER_RETENTION_DAYS, parsed)


def _recorder_retention_policy(*, start_ms: int, end_ms: int) -> dict[str, Any]:
    retention_days = _configured_recorder_retention_days()
    window_days = max(0.0, (end_ms - start_ms) / 86_400_000.0)
    status = "ok" if window_days <= retention_days else "warning"
    reason = None if status == "ok" else "window_exceeds_configured_recorder_retention"
    return {
        "status": status,
        "reason": reason,
        "configured_retention_days": retention_days,
        "minimum_retention_days": MIN_RECORDER_RETENTION_DAYS,
        "requested_window_days": window_days,
        "maturity_rule": (
            "S1 claims require locally recorded BBO/orderbook rows for the "
            "requested window; windows older than retention remain S2/S2+."
        ),
    }


def _ratio(block: Any) -> float:
    if not isinstance(block, dict):
        return 0.0
    value = block.get("coverage_ratio")
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) else 0.0


def _unavailable(base: dict[str, Any], reason: str, *, message: str | None = None) -> dict[str, Any]:
    payload = dict(base)
    payload.update({"status": "unavailable", "reason": reason})
    if message:
        payload["message"] = message
    return payload


def _table_presence(cur: Any) -> dict[str, dict[str, Any]]:
    tables = [
        "market.market_tickers",
        "market.ob_snapshots",
        "market.symbol_universe_snapshots",
    ]
    cur.execute("SELECT to_regclass(%s), to_regclass(%s), to_regclass(%s);", tuple(tables))
    row = cur.fetchone() or (None, None, None)
    result: dict[str, dict[str, Any]] = {}
    for name, exists in zip(tables, row):
        result[name] = {"exists": bool(exists), "latest_ts": None, "row_count": 0}
    for name in tables:
        if not result[name]["exists"]:
            continue
        cur.execute(f"SELECT COUNT(*)::bigint, MIN(ts), MAX(ts) FROM {name};")
        count, oldest_ts, latest_ts = cur.fetchone() or (0, None, None)
        result[name]["row_count"] = int(count or 0)
        result[name]["oldest_ts"] = (
            oldest_ts.isoformat() if hasattr(oldest_ts, "isoformat") else oldest_ts
        )
        result[name]["latest_ts"] = (
            latest_ts.isoformat() if hasattr(latest_ts, "isoformat") else latest_ts
        )
    return result


def _ticker_coverage(
    *,
    cur: Any,
    table_exists: bool,
    symbols: list[str],
    start_ms: int,
    end_ms: int,
    interval_ms: int,
    expected_slots: int,
) -> dict[str, Any]:
    if not table_exists:
        return {
            "bbo": _coverage_block(0, expected_slots, "market.market_tickers"),
            "funding_rate": _coverage_block(0, expected_slots, "market.market_tickers"),
            "open_interest": _coverage_block(0, expected_slots, "market.market_tickers"),
            "index_price": _coverage_block(0, expected_slots, "market.market_tickers"),
        }
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'market'
          AND table_name = 'market_tickers';
        """
    )
    columns = {str(row[0]) for row in cur.fetchall()}
    funding_expr = "funding_rate" if "funding_rate" in columns else "NULL::real"
    cur.execute(
        f"""
        WITH rows AS (
            SELECT
                symbol,
                floor(
                    ((extract(epoch from ts) * 1000)::numeric - %s) / %s
                )::bigint AS bucket_idx,
                best_bid,
                best_ask,
                index_price,
                open_interest,
                {funding_expr} AS funding_rate
            FROM market.market_tickers
            WHERE symbol = ANY(%s)
              AND ts >= to_timestamp(%s / 1000.0)
              AND ts <= to_timestamp(%s / 1000.0)
        )
        SELECT
            COUNT(DISTINCT (symbol, bucket_idx)) FILTER (
                WHERE best_bid IS NOT NULL
                  AND best_ask IS NOT NULL
                  AND best_bid > 0
                  AND best_ask > 0
                  AND best_bid <= best_ask
            ) AS bbo_slots,
            COUNT(DISTINCT (symbol, bucket_idx)) FILTER (
                WHERE funding_rate IS NOT NULL
            ) AS funding_slots,
            COUNT(DISTINCT (symbol, bucket_idx)) FILTER (
                WHERE open_interest IS NOT NULL
            ) AS oi_slots,
            COUNT(DISTINCT (symbol, bucket_idx)) FILTER (
                WHERE index_price IS NOT NULL
            ) AS index_slots
        FROM rows
        WHERE bucket_idx >= 0;
        """,
        (start_ms, interval_ms, symbols, start_ms, end_ms),
    )
    row = cur.fetchone() or (0, 0, 0, 0)
    return {
        "bbo": _coverage_block(int(row[0] or 0), expected_slots, "market.market_tickers"),
        "funding_rate": _coverage_block(
            int(row[1] or 0),
            expected_slots,
            "market.market_tickers",
        ),
        "open_interest": _coverage_block(
            int(row[2] or 0),
            expected_slots,
            "market.market_tickers",
        ),
        "index_price": _coverage_block(
            int(row[3] or 0),
            expected_slots,
            "market.market_tickers",
        ),
    }


def _orderbook_coverage(
    *,
    cur: Any,
    table_exists: bool,
    symbols: list[str],
    start_ms: int,
    end_ms: int,
    interval_ms: int,
    expected_slots: int,
) -> dict[str, Any]:
    if not table_exists:
        return _coverage_block(0, expected_slots, "market.ob_snapshots")
    cur.execute(
        """
        WITH rows AS (
            SELECT
                symbol,
                floor(
                    ((extract(epoch from ts) * 1000)::numeric - %s) / %s
                )::bigint AS bucket_idx,
                bid_depth_5,
                ask_depth_5
            FROM market.ob_snapshots
            WHERE symbol = ANY(%s)
              AND ts >= to_timestamp(%s / 1000.0)
              AND ts <= to_timestamp(%s / 1000.0)
        )
        SELECT COUNT(DISTINCT (symbol, bucket_idx)) FILTER (
            WHERE bid_depth_5 IS NOT NULL
              AND ask_depth_5 IS NOT NULL
              AND bid_depth_5 > 0
              AND ask_depth_5 > 0
        )
        FROM rows
        WHERE bucket_idx >= 0;
        """,
        (start_ms, interval_ms, symbols, start_ms, end_ms),
    )
    row = cur.fetchone() or (0,)
    return _coverage_block(int(row[0] or 0), expected_slots, "market.ob_snapshots")


def _instrument_spec_coverage(
    *,
    cur: Any,
    table_exists: bool,
    symbols: list[str],
    end_ms: int,
) -> dict[str, Any]:
    if not table_exists:
        return _coverage_block(0, len(symbols), "market.symbol_universe_snapshots")
    cur.execute(
        """
        WITH latest AS (
            SELECT DISTINCT ON (symbol)
                symbol,
                tick_size
            FROM market.symbol_universe_snapshots
            WHERE symbol = ANY(%s)
              AND exchange = 'bybit'
              AND ts <= to_timestamp(%s / 1000.0)
            ORDER BY symbol, ts DESC
        )
        SELECT COUNT(*) FILTER (
            WHERE tick_size IS NOT NULL AND tick_size > 0
        )
        FROM latest;
        """,
        (symbols, end_ms),
    )
    row = cur.fetchone() or (0,)
    return _coverage_block(
        int(row[0] or 0),
        len(symbols),
        "market.symbol_universe_snapshots",
    )
