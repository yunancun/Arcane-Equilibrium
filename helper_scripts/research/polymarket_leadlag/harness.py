#!/usr/bin/env python3
"""Polymarket probability-delta vs Bybit perp forward-return IC harness.

本檔建立 profit diagnosis 的 feedback loop：當 Polymarket hourly snapshots 足夠時，
用同一條命令測 event/regulatory prediction-market odds 是否 lead Bybit perps。

Leak-free discipline:
  - feature at t = market implied-prob delta from previous snapshot to snapshot t；
  - target = Bybit close return from first kline at/after t to first kline at/after t+h；
  - price-target 與 event/reg bucket 在研究端分桶，不在 collector 端丟 row；
  - insufficient sample fail-closed，不能升級為 alpha proof。

Hard boundary:
  - artifact/report only；
  - optional PG path is readonly session + SELECT market.klines；
  - no Bybit private/signed/trading calls, no PG writes, no strategy/risk/order/auth mutation。
"""

from __future__ import annotations

import argparse
import bisect
import datetime as dt
import hashlib
import json
import math
import os
import re
import socket
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Optional

try:
    from . import candidate_replay
    from . import (
        BUCKET_EVENT_REG,
        BUCKET_EVENT_REG_DIRECT,
        BUCKET_EVENT_REG_MACRO,
        BUCKET_OTHER,
        BUCKET_PRICE_TARGET,
        REPORT_SCHEMA_VERSION,
        RUNNER_VERSION,
        STATUS_IC_CANDIDATE_REVIEW_REQUIRED,
        STATUS_IC_READY_NO_SIGNIFICANT_EDGE,
        STATUS_INSUFFICIENT_SAMPLE,
        STATUS_NO_PRICE_DATA,
        STATUS_NO_SNAPSHOT_ROWS,
        SYMBOL_SOURCE_ASSET_DIRECT,
        SYMBOL_SOURCE_MACRO_EVENT_REG,
    )
except ImportError:  # pragma: no cover
    _here = Path(__file__).resolve()
    _research = _here.parents[1]
    if str(_research) not in sys.path:
        sys.path.insert(0, str(_research))
    from polymarket_leadlag import candidate_replay  # type: ignore
    from polymarket_leadlag import (  # type: ignore
        BUCKET_EVENT_REG,
        BUCKET_EVENT_REG_DIRECT,
        BUCKET_EVENT_REG_MACRO,
        BUCKET_OTHER,
        BUCKET_PRICE_TARGET,
        REPORT_SCHEMA_VERSION,
        RUNNER_VERSION,
        STATUS_IC_CANDIDATE_REVIEW_REQUIRED,
        STATUS_IC_READY_NO_SIGNIFICANT_EDGE,
        STATUS_INSUFFICIENT_SAMPLE,
        STATUS_NO_PRICE_DATA,
        STATUS_NO_SNAPSHOT_ROWS,
        SYMBOL_SOURCE_ASSET_DIRECT,
        SYMBOL_SOURCE_MACRO_EVENT_REG,
    )


DEFAULT_HORIZONS_MINUTES = (15, 60, 240)
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT")
DEFAULT_MACRO_PROXY_SYMBOLS = ("BTCUSDT", "ETHUSDT")
DEFAULT_QUERY_SET = "v2"
DEFAULT_MODE = "hourly-topn"
DEFAULT_MIN_POINTS = 20
DEFAULT_MAX_ALIGN_LAG_MINUTES = 10
DEFAULT_MIN_ABS_IC = 0.15
DEFAULT_MIN_ABS_T = 2.0
DEFAULT_MAX_BH_Q = 0.10
DEFAULT_MAX_HAC_LAG = 12
DEFAULT_SCHEDULE_JITTER_TOLERANCE_MS = 5_000
DEFAULT_PRICE_FEEDBACK_MIN_POINTS = 5
DEFAULT_PRICE_FEEDBACK_MIN_ABS_IC = 0.15
DEFAULT_PRICE_FEEDBACK_PARTIAL_RETAINED_RATIO = 0.5
DEFAULT_WATCHLIST_HISTORY_REPORTS = 16

_PRICE_TARGET_RE = re.compile(
    r"(\bprice\b.*\bhit\b|\bhit\b.*\$|\breach\b.*\$|above\s+\$|below\s+\$|"
    r"\ball[- ]time high\b|>\s*\$|<\s*\$|\bwill .* reach\b)",
    re.IGNORECASE,
)
_EVENT_REG_RE = re.compile(
    r"\b(etf|sec|cftc|fomc|fed|rate cut|cpi|inflation|regulation|stablecoin|"
    r"blackrock|grayscale|tether|usdt|binance|coinbase|lawsuit|reserve)\b",
    re.IGNORECASE,
)
_ASSET_PATTERNS = (
    ("BTCUSDT", re.compile(r"\b(bitcoin|btc)\b", re.IGNORECASE)),
    ("ETHUSDT", re.compile(r"\b(ethereum|ether|eth)\b", re.IGNORECASE)),
    ("SOLUSDT", re.compile(r"\b(solana|sol)\b", re.IGNORECASE)),
    ("XRPUSDT", re.compile(r"\b(xrp|ripple)\b", re.IGNORECASE)),
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _data_root() -> Path:
    base = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw").strip() or "/tmp/openclaw"
    return Path(base)


def _parse_dt(value: Any) -> Optional[dt.datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        out = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if out.tzinfo is None:
        out = out.replace(tzinfo=dt.timezone.utc)
    return out.astimezone(dt.timezone.utc)


def _dt_to_ms(value: dt.datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return int(value.astimezone(dt.timezone.utc).timestamp() * 1000)


def _ms_to_iso(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000.0, tz=dt.timezone.utc).isoformat()


def _float_or_none(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _safe_text(row: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("question", "event_title", "market_slug", "event_slug"):
        val = row.get(key)
        if val:
            parts.append(str(val))
    for query in row.get("discovery_queries") or []:
        if query:
            parts.append(str(query))
    return " ".join(parts)


def infer_symbol(row: dict[str, Any], allowed_symbols: set[str]) -> Optional[str]:
    text = _safe_text(row)
    for symbol, pattern in _ASSET_PATTERNS:
        if symbol in allowed_symbols and pattern.search(text):
            return symbol
    return None


def infer_symbol_mappings(row: dict[str, Any], allowed_symbols: set[str]) -> list[tuple[str, str]]:
    direct_symbol = infer_symbol(row, allowed_symbols)
    if direct_symbol is not None:
        return [(direct_symbol, SYMBOL_SOURCE_ASSET_DIRECT)]
    if classify_bucket(row) != BUCKET_EVENT_REG:
        return []
    return [
        (symbol, SYMBOL_SOURCE_MACRO_EVENT_REG)
        for symbol in DEFAULT_MACRO_PROXY_SYMBOLS
        if symbol in allowed_symbols
    ]


def classify_bucket(row: dict[str, Any]) -> str:
    text = _safe_text(row)
    if _PRICE_TARGET_RE.search(text):
        return BUCKET_PRICE_TARGET
    if _EVENT_REG_RE.search(text):
        return BUCKET_EVENT_REG
    return BUCKET_OTHER


def yes_probability(row: dict[str, Any]) -> Optional[float]:
    prices = row.get("outcome_prices")
    outcomes = row.get("outcomes")
    if not isinstance(prices, list) or not prices:
        return None
    idx = 0
    if isinstance(outcomes, list):
        lowered = [str(x).strip().lower() for x in outcomes]
        if "yes" in lowered:
            idx = lowered.index("yes")
    if idx >= len(prices):
        return None
    prob = _float_or_none(prices[idx])
    if prob is None or prob < 0.0 or prob > 1.0:
        return None
    return prob


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"json_not_object:{path}")
    return payload


def _report_sort_ts(payload: dict[str, Any], path: Path) -> tuple[float, str]:
    parsed = _parse_dt(payload.get("created_at_utc"))
    if parsed is not None:
        return parsed.timestamp(), path.name
    try:
        return path.stat().st_mtime, path.name
    except OSError:
        return 0.0, path.name


def load_recent_report_history(
    report_dir: Path,
    *,
    limit: int = DEFAULT_WATCHLIST_HISTORY_REPORTS,
) -> list[dict[str, Any]]:
    """Load recent dated Polymarket lead-lag reports for diagnostic reducers."""
    report_dir = Path(report_dir)
    if not report_dir.exists():
        return []
    reports: list[tuple[float, str, dict[str, Any]]] = []
    for path in report_dir.glob("polymarket_leadlag_*.json"):
        if path.name == "polymarket_leadlag_latest.json":
            continue
        try:
            payload = _read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        ts_key = _report_sort_ts(payload, path)
        reports.append((ts_key[0], ts_key[1], {**payload, "_history_path": str(path)}))
    reports.sort(key=lambda item: (item[0], item[1]))
    if limit <= 0:
        return [payload for _ts, _name, payload in reports]
    return [payload for _ts, _name, payload in reports[-limit:]]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid_jsonl:{path}:{line_no}:{exc}") from exc
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def load_snapshot_rows(
    root: Path,
    *,
    query_set_version: str,
    mode: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    root = Path(root)
    rows: list[dict[str, Any]] = []
    run_dirs = 0
    skipped: Counter[str] = Counter()
    if not root.exists():
        return [], {"root": str(root), "run_dirs": 0, "skipped": {"root_missing": 1}}
    for run_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        manifest_path = run_dir / "manifest.json"
        snapshots_path = run_dir / "snapshots.jsonl"
        if not manifest_path.exists() or not snapshots_path.exists():
            skipped["missing_manifest_or_snapshots"] += 1
            continue
        try:
            manifest = _read_json(manifest_path)
        except (OSError, ValueError, json.JSONDecodeError):
            skipped["bad_manifest"] += 1
            continue
        if manifest.get("lane") != "snapshot" or not manifest.get("point_in_time", False):
            skipped["not_snapshot_lane"] += 1
            continue
        if str(manifest.get("mode") or "") != mode:
            skipped["mode_mismatch"] += 1
            continue
        if str(manifest.get("query_set_version") or "") != query_set_version:
            skipped["query_set_mismatch"] += 1
            continue
        try:
            run_rows = _read_jsonl(snapshots_path)
        except (OSError, ValueError):
            skipped["bad_snapshots"] += 1
            continue
        run_dirs += 1
        for row in run_rows:
            row["_run_id"] = manifest.get("run_id") or run_dir.name
            row["_run_dir"] = str(run_dir)
            rows.append(row)
    return rows, {"root": str(root), "run_dirs": run_dirs, "skipped": dict(skipped)}


def build_market_deltas(
    rows: Iterable[dict[str, Any]],
    *,
    allowed_symbols: set[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_market_symbol: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    market_ids_with_rows: set[str] = set()
    skipped: Counter[str] = Counter()
    symbol_source_counts: Counter[str] = Counter()
    unmapped_bucket_counts: Counter[str] = Counter()
    unmapped_query_counts: Counter[str] = Counter()
    unmapped_examples: list[dict[str, Any]] = []
    for row in rows:
        market_id = str(row.get("market_id") or "").strip()
        ts = _parse_dt(row.get("snapshot_ts_utc"))
        prob = yes_probability(row)
        if not market_id:
            skipped["missing_market_id"] += 1
            continue
        if ts is None:
            skipped["bad_snapshot_ts"] += 1
            continue
        if prob is None:
            skipped["bad_probability"] += 1
            continue
        bucket = classify_bucket(row)
        symbol_mappings = infer_symbol_mappings(row, allowed_symbols)
        if not symbol_mappings:
            skipped["unmapped_symbol"] += 1
            unmapped_bucket_counts[bucket] += 1
            for query in row.get("discovery_queries") or ["<no_query>"]:
                unmapped_query_counts[str(query)] += 1
            if len(unmapped_examples) < 8:
                unmapped_examples.append({
                    "bucket": bucket,
                    "question": row.get("question"),
                    "event_title": row.get("event_title"),
                    "market_slug": row.get("market_slug"),
                    "event_slug": row.get("event_slug"),
                    "discovery_queries": list(row.get("discovery_queries") or []),
                })
            continue
        for symbol, symbol_source in symbol_mappings:
            enriched = {
                "market_id": market_id,
                "snapshot_ts_ms": _dt_to_ms(ts),
                "snapshot_ts_utc": ts.isoformat(),
                "prob_yes": prob,
                "symbol": symbol,
                "symbol_source": symbol_source,
                "bucket": bucket,
                "question": row.get("question"),
                "event_title": row.get("event_title"),
                "discovery_queries": list(row.get("discovery_queries") or []),
            }
            symbol_source_counts[symbol_source] += 1
            market_ids_with_rows.add(market_id)
            by_market_symbol[(market_id, symbol)].append(enriched)

    deltas: list[dict[str, Any]] = []
    for (_market_id, _symbol), market_rows in by_market_symbol.items():
        market_rows.sort(key=lambda r: r["snapshot_ts_ms"])
        prev: Optional[dict[str, Any]] = None
        for row in market_rows:
            if prev is not None and row["snapshot_ts_ms"] > prev["snapshot_ts_ms"]:
                deltas.append({
                    **row,
                    "prev_snapshot_ts_utc": prev["snapshot_ts_utc"],
                    "prev_prob_yes": prev["prob_yes"],
                    "delta_prob_yes": row["prob_yes"] - prev["prob_yes"],
                })
            prev = row
    return deltas, {
        "markets_with_rows": len(market_ids_with_rows),
        "market_symbol_series_with_rows": len(by_market_symbol),
        "delta_rows": len(deltas),
        "symbol_source_counts": dict(symbol_source_counts),
        "unmapped_symbol_diagnostics": {
            "bucket_counts": dict(unmapped_bucket_counts),
            "top_queries": dict(unmapped_query_counts.most_common(12)),
            "examples": unmapped_examples,
        },
        "skipped": dict(skipped),
    }


def _event_reg_source_split_bucket(symbol_source: str) -> Optional[str]:
    if symbol_source == SYMBOL_SOURCE_ASSET_DIRECT:
        return BUCKET_EVENT_REG_DIRECT
    if symbol_source == SYMBOL_SOURCE_MACRO_EVENT_REG:
        return BUCKET_EVENT_REG_MACRO
    return None


def aggregate_features(
    deltas: Iterable[dict[str, Any]],
    *,
    include_source_splits: bool = False,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, str, str, str, str], list[dict[str, Any]]] = defaultdict(
        list
    )
    for row in deltas:
        ts_ms = int(row["snapshot_ts_ms"])
        bucket = str(row["bucket"])
        symbol = str(row["symbol"])
        symbol_source = str(row.get("symbol_source") or "unknown")
        grouped[(ts_ms, bucket, symbol, "aggregate", "aggregate")].append(row)
        if include_source_splits and bucket == BUCKET_EVENT_REG:
            split_bucket = _event_reg_source_split_bucket(symbol_source)
            if split_bucket:
                grouped[(ts_ms, split_bucket, symbol, "source_split", symbol_source)].append(
                    row
                )
    out: list[dict[str, Any]] = []
    for (ts_ms, bucket, symbol, bucket_view, source_key), rows in sorted(grouped.items()):
        vals = [float(r["delta_prob_yes"]) for r in rows]
        source_breakdown = Counter(str(r.get("symbol_source") or "unknown") for r in rows)
        base_buckets = sorted({str(r.get("bucket") or "") for r in rows if r.get("bucket")})
        aggregate_source = (
            next(iter(source_breakdown))
            if bucket_view == "aggregate" and len(source_breakdown) == 1
            else source_key
        )
        out.append({
            "snapshot_ts_ms": ts_ms,
            "snapshot_ts_utc": _ms_to_iso(ts_ms),
            "bucket": bucket,
            "base_bucket": base_buckets[0] if len(base_buckets) == 1 else "mixed",
            "bucket_view": bucket_view,
            "symbol": symbol,
            "symbol_source": aggregate_source,
            "symbol_source_breakdown": dict(source_breakdown),
            "n_markets": len(rows),
            "mean_delta_prob_yes": sum(vals) / len(vals),
            "mean_abs_delta_prob_yes": sum(abs(v) for v in vals) / len(vals),
            "market_ids": sorted({str(r["market_id"]) for r in rows}),
        })
    return out


def load_price_points_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = _read_jsonl(Path(path))
    out: list[dict[str, Any]] = []
    for row in rows:
        symbol = str(row.get("symbol") or "").strip()
        ts_ms = row.get("open_ts_ms")
        if ts_ms is None:
            parsed = _parse_dt(row.get("ts_utc") or row.get("ts"))
            ts_ms = _dt_to_ms(parsed) if parsed is not None else None
        price = _float_or_none(row.get("price") if "price" in row else row.get("close"))
        if not symbol or ts_ms is None or price is None or price <= 0.0:
            continue
        out.append({"symbol": symbol, "ts_ms": int(ts_ms), "price": price})
    return sorted(out, key=lambda r: (r["symbol"], r["ts_ms"]))


def connect_pg(dsn: Optional[str] = None):
    import psycopg2  # type: ignore

    conn = psycopg2.connect(dsn or os.environ.get("OPENCLAW_DATABASE_URL", "") or "")
    conn.set_session(readonly=True)
    return conn


def load_price_points_pg(
    *,
    symbols: list[str],
    start_ms: int,
    end_ms: int,
    timeframe: str = "1m",
    dsn: Optional[str] = None,
) -> list[dict[str, Any]]:
    conn = connect_pg(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT symbol, open_ts_ms, close "
                "FROM market.klines "
                "WHERE timeframe=%s AND symbol = ANY(%s) AND open_ts_ms >= %s AND open_ts_ms <= %s "
                "ORDER BY symbol ASC, open_ts_ms ASC",
                (timeframe, symbols, int(start_ms), int(end_ms)),
            )
            return [
                {"symbol": sym, "ts_ms": int(ts_ms), "price": float(close)}
                for sym, ts_ms, close in cur.fetchall()
                if close is not None and float(close) > 0.0
            ]
    finally:
        conn.close()


def index_prices(price_rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, list[Any]]]:
    by_symbol: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for row in price_rows:
        symbol = str(row.get("symbol") or "").strip()
        ts_ms = row.get("ts_ms")
        price = _float_or_none(row.get("price"))
        if not symbol or ts_ms is None or price is None or price <= 0.0:
            continue
        by_symbol[symbol].append((int(ts_ms), price))
    out: dict[str, dict[str, list[Any]]] = {}
    for symbol, rows in by_symbol.items():
        dedup: dict[int, float] = {}
        for ts_ms, price in rows:
            dedup[ts_ms] = price
        ordered = sorted(dedup.items())
        out[symbol] = {
            "times": [x[0] for x in ordered],
            "prices": [x[1] for x in ordered],
        }
    return out


def _price_at_or_after(
    indexed: dict[str, dict[str, list[Any]]],
    symbol: str,
    target_ms: int,
    *,
    max_lag_ms: int,
) -> Optional[tuple[int, float]]:
    series = indexed.get(symbol)
    if not series:
        return None
    times: list[int] = series["times"]
    idx = bisect.bisect_left(times, target_ms)
    if idx >= len(times):
        return None
    ts_ms = times[idx]
    if ts_ms - target_ms > max_lag_ms:
        return None
    return ts_ms, float(series["prices"][idx])


def _price_at_or_before(
    indexed: dict[str, dict[str, list[Any]]],
    symbol: str,
    target_ms: int,
    *,
    max_lag_ms: int,
) -> Optional[tuple[int, float]]:
    series = indexed.get(symbol)
    if not series:
        return None
    times: list[int] = series["times"]
    idx = bisect.bisect_right(times, target_ms) - 1
    if idx < 0:
        return None
    ts_ms = times[idx]
    if target_ms - ts_ms > max_lag_ms:
        return None
    return ts_ms, float(series["prices"][idx])


def join_forward_returns(
    features: Iterable[dict[str, Any]],
    price_rows: Iterable[dict[str, Any]],
    *,
    horizons_minutes: tuple[int, ...],
    max_align_lag_minutes: int,
) -> list[dict[str, Any]]:
    indexed = index_prices(price_rows)
    max_lag_ms = int(max_align_lag_minutes * 60 * 1000)
    joined: list[dict[str, Any]] = []
    for feature in features:
        ts_ms = int(feature["snapshot_ts_ms"])
        symbol = str(feature["symbol"])
        p0 = _price_at_or_after(indexed, symbol, ts_ms, max_lag_ms=max_lag_ms)
        if p0 is None:
            continue
        p0_ts, p0_px = p0
        for horizon in horizons_minutes:
            p1 = _price_at_or_after(
                indexed, symbol, ts_ms + horizon * 60 * 1000, max_lag_ms=max_lag_ms,
            )
            if p1 is None:
                continue
            p1_ts, p1_px = p1
            out = {
                **feature,
                "horizon_minutes": horizon,
                "entry_price_ts_utc": _ms_to_iso(p0_ts),
                "exit_price_ts_utc": _ms_to_iso(p1_ts),
                "entry_price": p0_px,
                "exit_price": p1_px,
                "forward_return_bps": (p1_px - p0_px) / p0_px * 10_000.0,
            }
            trailing_start = _price_at_or_before(
                indexed,
                symbol,
                ts_ms - horizon * 60 * 1000,
                max_lag_ms=max_lag_ms,
            )
            trailing_end = _price_at_or_before(
                indexed,
                symbol,
                ts_ms,
                max_lag_ms=max_lag_ms,
            )
            if trailing_start is not None and trailing_end is not None:
                trailing_start_ts, trailing_start_px = trailing_start
                trailing_end_ts, trailing_end_px = trailing_end
                out.update({
                    "trailing_entry_price_ts_utc": _ms_to_iso(trailing_start_ts),
                    "trailing_exit_price_ts_utc": _ms_to_iso(trailing_end_ts),
                    "trailing_entry_price": trailing_start_px,
                    "trailing_exit_price": trailing_end_px,
                    "trailing_return_bps": (
                        (trailing_end_px - trailing_start_px) / trailing_start_px * 10_000.0
                    ),
                })
            joined.append(out)
    return joined


def diagnose_label_readiness(
    features: Iterable[dict[str, Any]],
    price_rows: Iterable[dict[str, Any]],
    *,
    horizons_minutes: tuple[int, ...],
    max_align_lag_minutes: int,
) -> dict[str, Any]:
    indexed = index_prices(price_rows)
    max_lag_ms = int(max_align_lag_minutes * 60 * 1000)
    latest_price_ts_by_symbol = {
        symbol: max(series["times"])
        for symbol, series in indexed.items()
        if series.get("times")
    }
    status_counts: Counter[str] = Counter()
    by_horizon: dict[int, Counter[str]] = {int(h): Counter() for h in horizons_minutes}
    by_symbol: dict[str, Counter[str]] = defaultdict(Counter)
    by_bucket_horizon: dict[str, Counter[str]] = defaultdict(Counter)
    unmatured_exit_targets: list[int] = []
    feature_ts_values: list[int] = []

    for feature in features:
        ts_ms = int(feature["snapshot_ts_ms"])
        feature_ts_values.append(ts_ms)
        symbol = str(feature["symbol"])
        bucket = str(feature["bucket"])
        latest_price_ts = latest_price_ts_by_symbol.get(symbol)
        p0 = _price_at_or_after(indexed, symbol, ts_ms, max_lag_ms=max_lag_ms)
        for horizon in horizons_minutes:
            horizon = int(horizon)
            target_ms = ts_ms + horizon * 60 * 1000
            if latest_price_ts is None:
                status = "missing_symbol_price"
            elif latest_price_ts < ts_ms:
                status = "entry_target_after_latest_price"
            elif p0 is None:
                status = "missing_entry_price_or_align_gap"
            elif latest_price_ts < target_ms:
                status = "exit_target_after_latest_price"
                unmatured_exit_targets.append(target_ms)
            elif _price_at_or_after(indexed, symbol, target_ms, max_lag_ms=max_lag_ms) is None:
                status = "missing_exit_price_or_align_gap"
            else:
                status = "joinable"

            status_counts[status] += 1
            by_horizon[horizon][status] += 1
            by_symbol[symbol][status] += 1
            by_bucket_horizon[f"{bucket}|{horizon}"][status] += 1

    return {
        "feature_horizon_pairs": sum(status_counts.values()),
        "joinable_pairs": status_counts.get("joinable", 0),
        "status_counts": dict(status_counts),
        "by_horizon": {str(h): dict(counter) for h, counter in sorted(by_horizon.items())},
        "by_symbol": {symbol: dict(counter) for symbol, counter in sorted(by_symbol.items())},
        "by_bucket_horizon": {
            key: dict(counter) for key, counter in sorted(by_bucket_horizon.items())
        },
        "latest_price_ts_utc_by_symbol": {
            symbol: _ms_to_iso(ts_ms) for symbol, ts_ms in sorted(latest_price_ts_by_symbol.items())
        },
        "latest_feature_ts_utc": _ms_to_iso(max(feature_ts_values)) if feature_ts_values else None,
        "oldest_unmatured_exit_target_utc": (
            _ms_to_iso(min(unmatured_exit_targets)) if unmatured_exit_targets else None
        ),
        "newest_unmatured_exit_target_utc": (
            _ms_to_iso(max(unmatured_exit_targets)) if unmatured_exit_targets else None
        ),
    }


def _mean(xs: list[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def _pearson(xs: list[float], ys: list[float]) -> Optional[float]:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0.0 or vy <= 0.0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(vx * vy)


def _t_stat_from_r(r: Optional[float], n: int) -> Optional[float]:
    if r is None or n < 3 or abs(r) >= 1.0:
        return None
    denom = max(1e-12, 1.0 - r * r)
    return r * math.sqrt((n - 2) / denom)


def _linear_residuals(ys: list[float], zs: list[float]) -> Optional[list[float]]:
    if len(ys) != len(zs) or len(ys) < 3:
        return None
    mz = sum(zs) / len(zs)
    my = sum(ys) / len(ys)
    var_z = sum((z - mz) ** 2 for z in zs)
    if var_z <= 0.0:
        return None
    beta = sum((z - mz) * (y - my) for y, z in zip(ys, zs)) / var_z
    alpha = my - beta * mz
    residuals = [y - (alpha + beta * z) for y, z in zip(ys, zs)]
    if sum((r - sum(residuals) / len(residuals)) ** 2 for r in residuals) <= 0.0:
        return None
    return residuals


def _horizon_ms(horizon_minutes: int) -> int:
    return int(max(1, horizon_minutes) * 60 * 1000)


def _schedule_jitter_tolerance_ms(horizon_minutes: int) -> int:
    horizon_ms = _horizon_ms(horizon_minutes)
    return max(0, min(DEFAULT_SCHEDULE_JITTER_TOLERANCE_MS, horizon_ms - 1))


def _count_nonoverlap_timestamps(timestamps_ms: Iterable[int], horizon_minutes: int) -> int:
    return len(_selected_nonoverlap_timestamps(timestamps_ms, horizon_minutes))


def _selected_nonoverlap_timestamps(timestamps_ms: Iterable[int], horizon_minutes: int) -> list[int]:
    ordered = sorted({int(ts) for ts in timestamps_ms})
    if not ordered:
        return []
    min_gap_ms = _horizon_ms(horizon_minutes) - _schedule_jitter_tolerance_ms(horizon_minutes)
    selected: list[int] = []
    last: Optional[int] = None
    for ts_ms in ordered:
        if last is None or ts_ms - last >= min_gap_ms:
            selected.append(ts_ms)
            last = ts_ms
    return selected


def _normal_two_sided_p_from_t(t_stat: Optional[float]) -> Optional[float]:
    if t_stat is None or not math.isfinite(t_stat):
        return None
    return math.erfc(abs(float(t_stat)) / math.sqrt(2.0))


def _median_positive_gap_ms(timestamps_ms: Iterable[int]) -> Optional[int]:
    ordered = sorted({int(ts) for ts in timestamps_ms})
    gaps = [
        b - a
        for a, b in zip(ordered, ordered[1:])
        if b > a
    ]
    if not gaps:
        return None
    gaps.sort()
    mid = len(gaps) // 2
    if len(gaps) % 2:
        return int(gaps[mid])
    return int((gaps[mid - 1] + gaps[mid]) / 2)


def _hac_lag_for_horizon(timestamps_ms: Iterable[int], horizon_minutes: int) -> int:
    gap_ms = _median_positive_gap_ms(timestamps_ms)
    if gap_ms is None or gap_ms <= 0:
        return 0
    effective_horizon_ms = _horizon_ms(horizon_minutes) - _schedule_jitter_tolerance_ms(horizon_minutes)
    return max(0, min(DEFAULT_MAX_HAC_LAG, int(math.ceil(effective_horizon_ms / gap_ms)) - 1))


def _newey_west_slope_t_stat(
    xs: list[float],
    ys: list[float],
    *,
    lag: int,
) -> Optional[float]:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    centered_x = [x - mx for x in xs]
    sxx = sum(x * x for x in centered_x)
    if sxx <= 0.0:
        return None
    slope = sum(x * (y - my) for x, y in zip(centered_x, ys)) / sxx
    intercept = my - slope * mx
    score = [
        x * (y - intercept - slope * raw_x)
        for raw_x, x, y in zip(xs, centered_x, ys)
    ]
    max_lag = max(0, min(int(lag), len(score) - 2))
    long_run_var = sum(u * u for u in score)
    for lval in range(1, max_lag + 1):
        weight = 1.0 - (lval / (max_lag + 1.0))
        gamma = sum(score[idx] * score[idx - lval] for idx in range(lval, len(score)))
        long_run_var += 2.0 * weight * gamma
    if long_run_var <= 0.0:
        return None
    se = math.sqrt(long_run_var / (sxx * sxx))
    if se <= 0.0:
        return None
    return slope / se


def _bh_q_values(p_values: list[Optional[float]]) -> list[Optional[float]]:
    indexed = [
        (idx, float(p))
        for idx, p in enumerate(p_values)
        if p is not None and math.isfinite(float(p)) and 0.0 <= float(p) <= 1.0
    ]
    m = len(indexed)
    out: list[Optional[float]] = [None for _ in p_values]
    if m == 0:
        return out
    prev = 1.0
    for rank_from_end, (idx, p) in enumerate(
        sorted(indexed, key=lambda x: x[1], reverse=True),
        start=1,
    ):
        rank = m - rank_from_end + 1
        q = min(prev, p * m / rank)
        prev = q
        out[idx] = min(1.0, max(0.0, q))
    return out


def annotate_multiple_testing(ic_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    naive_p_values = [_normal_two_sided_p_from_t(row.get("t_stat")) for row in ic_results]
    hac_p_values = [_normal_two_sided_p_from_t(row.get("t_stat_hac")) for row in ic_results]
    naive_q_values = _bh_q_values(naive_p_values)
    hac_q_values = _bh_q_values(hac_p_values)
    out: list[dict[str, Any]] = []
    for row, naive_p, hac_p, naive_q, hac_q in zip(
        ic_results,
        naive_p_values,
        hac_p_values,
        naive_q_values,
        hac_q_values,
    ):
        out.append({
            **row,
            "p_value_naive_approx_normal": naive_p,
            "bh_q_value_naive_approx": naive_q,
            "p_value_hac_approx_normal": hac_p,
            "bh_q_value_hac_approx": hac_q,
            "p_value_approx_normal": hac_p,
            "bh_q_value_approx": hac_q,
            "multiple_testing_method": (
                "benjamini_hochberg_over_report_cells_hac_normal_approx"
            ),
        })
    return out


def compute_ic(joined: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in joined:
        key = (str(row["bucket"]), str(row["symbol"]), int(row["horizon_minutes"]))
        grouped[key].append(row)
    out: list[dict[str, Any]] = []
    for (bucket, symbol, horizon), rows in sorted(grouped.items()):
        rows = sorted(rows, key=lambda r: int(r["snapshot_ts_ms"]))
        xs = [float(r["mean_delta_prob_yes"]) for r in rows]
        ys = [float(r["forward_return_bps"]) for r in rows]
        forward_ic = _pearson(xs, ys)
        control_rows = [
            row for row in rows
            if row.get("trailing_return_bps") is not None
        ]
        control_xs = [float(row["mean_delta_prob_yes"]) for row in control_rows]
        control_forward_ys = [float(row["forward_return_bps"]) for row in control_rows]
        control_ys = [float(row["trailing_return_bps"]) for row in control_rows]
        past_ic = _pearson(control_xs, control_ys)
        trailing_forward_return_ic = _pearson(control_ys, control_forward_ys)
        forward_residuals = _linear_residuals(control_forward_ys, control_ys)
        partial_ic = (
            _pearson(control_xs, forward_residuals)
            if forward_residuals is not None
            else None
        )
        lead_lag_abs_ic_margin = (
            abs(float(forward_ic)) - abs(float(past_ic))
            if forward_ic is not None and past_ic is not None
            else None
        )
        partial_ic_abs_margin_vs_raw = (
            abs(float(partial_ic)) - abs(float(forward_ic))
            if forward_ic is not None and partial_ic is not None
            else None
        )
        partial_retained_ratio = (
            abs(float(partial_ic)) / abs(float(forward_ic))
            if forward_ic is not None
            and partial_ic is not None
            and abs(float(forward_ic)) > 1e-12
            else None
        )
        price_feedback_warning = (
            past_ic is not None
            and forward_ic is not None
            and len(control_rows) >= DEFAULT_PRICE_FEEDBACK_MIN_POINTS
            and abs(float(past_ic)) >= DEFAULT_PRICE_FEEDBACK_MIN_ABS_IC
            and abs(float(past_ic)) >= abs(float(forward_ic))
        )
        price_feedback_partial_collapse_warning = (
            forward_ic is not None
            and len(control_rows) >= DEFAULT_PRICE_FEEDBACK_MIN_POINTS
            and abs(float(forward_ic)) >= DEFAULT_PRICE_FEEDBACK_MIN_ABS_IC
            and (
                partial_ic is None
                or abs(float(partial_ic)) < DEFAULT_PRICE_FEEDBACK_MIN_ABS_IC
                or abs(float(partial_ic)) < (
                    abs(float(forward_ic)) * DEFAULT_PRICE_FEEDBACK_PARTIAL_RETAINED_RATIO
                )
            )
        )
        timestamps = [int(r["snapshot_ts_ms"]) for r in rows]
        selected_nonoverlap = _selected_nonoverlap_timestamps(timestamps, horizon)
        n_distinct = len(set(timestamps))
        n_nonoverlap = len(selected_nonoverlap)
        hac_lag = _hac_lag_for_horizon(timestamps, horizon)
        jitter_tolerance_ms = _schedule_jitter_tolerance_ms(horizon)
        effective_nonoverlap_gap_ms = _horizon_ms(horizon) - jitter_tolerance_ms
        median_sample_spacing_ms = _median_positive_gap_ms(timestamps)
        out.append({
            "bucket": bucket,
            "symbol": symbol,
            "horizon_minutes": horizon,
            "n_points": len(rows),
            "n_distinct_timestamps": n_distinct,
            "n_nonoverlap_timestamps": n_nonoverlap,
            "overlap_adjusted_sample_floor": min(len(rows), n_nonoverlap),
            "overlap_warning": n_nonoverlap < n_distinct,
            "overlap_jitter_tolerance_ms": jitter_tolerance_ms,
            "effective_nonoverlap_gap_ms": effective_nonoverlap_gap_ms,
            "median_sample_spacing_ms": median_sample_spacing_ms,
            "ic_pearson": forward_ic,
            "t_stat": _t_stat_from_r(forward_ic, len(rows)),
            "t_stat_hac": _newey_west_slope_t_stat(xs, ys, lag=hac_lag),
            "hac_lag": hac_lag,
            "hac_method": "newey_west_slope_t_stat_bartlett",
            "past_return_control_n_points": len(control_rows),
            "past_return_ic_pearson": past_ic,
            "past_return_t_stat": _t_stat_from_r(past_ic, len(control_rows)),
            "trailing_forward_return_ic_pearson": trailing_forward_return_ic,
            "partial_ic_controlling_trailing_return": partial_ic,
            "partial_ic_t_stat": _t_stat_from_r(partial_ic, len(control_rows)),
            "partial_ic_abs_margin_vs_raw": partial_ic_abs_margin_vs_raw,
            "partial_ic_retained_abs_ratio": partial_retained_ratio,
            "lead_lag_abs_ic_margin": lead_lag_abs_ic_margin,
            "price_feedback_warning": price_feedback_warning,
            "price_feedback_warning_basis": (
                "abs_past_return_ic_ge_abs_forward_ic"
                if price_feedback_warning
                else None
            ),
            "price_feedback_partial_collapse_warning": (
                price_feedback_partial_collapse_warning
            ),
            "price_feedback_partial_collapse_basis": (
                "partial_ic_collapses_after_trailing_return_control"
                if price_feedback_partial_collapse_warning
                else None
            ),
            "mean_delta_prob_yes": _mean(xs),
            "mean_forward_return_bps": _mean(ys),
            "mean_trailing_return_bps": _mean(control_ys),
            "first_snapshot_ts_utc": _ms_to_iso(min(timestamps)),
            "last_snapshot_ts_utc": _ms_to_iso(max(timestamps)),
            "first_nonoverlap_snapshot_ts_utc": (
                _ms_to_iso(selected_nonoverlap[0]) if selected_nonoverlap else None
            ),
            "last_nonoverlap_snapshot_ts_utc": (
                _ms_to_iso(selected_nonoverlap[-1]) if selected_nonoverlap else None
            ),
        })
    return annotate_multiple_testing(out)


def _price_feedback_summary(
    ic_results: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> dict[str, Any]:
    rows_with_control = [
        row for row in ic_results
        if int(row.get("past_return_control_n_points") or 0) > 0
    ]
    warning_rows = [row for row in rows_with_control if row.get("price_feedback_warning")]
    partial_control_rows = [
        row for row in rows_with_control
        if row.get("partial_ic_controlling_trailing_return") is not None
    ]
    partial_collapse_rows = [
        row for row in rows_with_control
        if row.get("price_feedback_partial_collapse_warning")
    ]
    past_ic_values = [
        abs(float(row["past_return_ic_pearson"]))
        for row in rows_with_control
        if row.get("past_return_ic_pearson") is not None
    ]
    partial_ic_values = [
        abs(float(row["partial_ic_controlling_trailing_return"]))
        for row in partial_control_rows
    ]

    warning_cells = []
    for row in sorted(
        warning_rows,
        key=lambda item: abs(float(item.get("past_return_ic_pearson") or 0.0)),
        reverse=True,
    )[:limit]:
        warning_cells.append({
            "bucket": row.get("bucket"),
            "symbol": row.get("symbol"),
            "horizon_minutes": row.get("horizon_minutes"),
            "n_points": row.get("n_points"),
            "past_return_control_n_points": row.get("past_return_control_n_points"),
            "ic_pearson": row.get("ic_pearson"),
            "past_return_ic_pearson": row.get("past_return_ic_pearson"),
            "lead_lag_abs_ic_margin": row.get("lead_lag_abs_ic_margin"),
            "warning_basis": row.get("price_feedback_warning_basis"),
        })

    collapsed_cells = []
    for row in sorted(
        partial_collapse_rows,
        key=lambda item: abs(float(item.get("ic_pearson") or 0.0)),
        reverse=True,
    )[:limit]:
        collapsed_cells.append({
            "bucket": row.get("bucket"),
            "symbol": row.get("symbol"),
            "horizon_minutes": row.get("horizon_minutes"),
            "n_points": row.get("n_points"),
            "past_return_control_n_points": row.get("past_return_control_n_points"),
            "ic_pearson": row.get("ic_pearson"),
            "past_return_ic_pearson": row.get("past_return_ic_pearson"),
            "trailing_forward_return_ic_pearson": row.get(
                "trailing_forward_return_ic_pearson"
            ),
            "partial_ic_controlling_trailing_return": row.get(
                "partial_ic_controlling_trailing_return"
            ),
            "partial_ic_abs_margin_vs_raw": row.get("partial_ic_abs_margin_vs_raw"),
            "partial_ic_retained_abs_ratio": row.get("partial_ic_retained_abs_ratio"),
            "collapse_basis": row.get("price_feedback_partial_collapse_basis"),
        })

    top_partial_ic_cells = []
    for row in sorted(
        partial_control_rows,
        key=lambda item: abs(float(item.get("partial_ic_controlling_trailing_return") or 0.0)),
        reverse=True,
    )[:limit]:
        top_partial_ic_cells.append({
            "bucket": row.get("bucket"),
            "symbol": row.get("symbol"),
            "horizon_minutes": row.get("horizon_minutes"),
            "n_points": row.get("n_points"),
            "past_return_control_n_points": row.get("past_return_control_n_points"),
            "ic_pearson": row.get("ic_pearson"),
            "partial_ic_controlling_trailing_return": row.get(
                "partial_ic_controlling_trailing_return"
            ),
            "partial_ic_t_stat": row.get("partial_ic_t_stat"),
            "partial_ic_abs_margin_vs_raw": row.get("partial_ic_abs_margin_vs_raw"),
        })

    return {
        "cells_with_control": len(rows_with_control),
        "warning_count": len(warning_rows),
        "max_abs_past_return_ic": max(past_ic_values, default=None),
        "warning_cells": warning_cells,
        "control_definition": "corr(feature_delta_at_t, price_return_t_minus_h_to_t)",
        "partial_control_definition": (
            "corr(feature_delta_at_t, residual(forward_return_t_to_t_plus_h "
            "~ price_return_t_minus_h_to_t))"
        ),
        "partial_control_cells": len(partial_control_rows),
        "partial_ic_available_count": len(partial_control_rows),
        "max_abs_partial_ic_controlling_trailing_return": max(
            partial_ic_values,
            default=None,
        ),
        "raw_to_partial_collapse_count": len(partial_collapse_rows),
        "collapsed_cells": collapsed_cells,
        "top_partial_ic_cells": top_partial_ic_cells,
        "warning_threshold": {
            "min_points": DEFAULT_PRICE_FEEDBACK_MIN_POINTS,
            "min_abs_past_return_ic": DEFAULT_PRICE_FEEDBACK_MIN_ABS_IC,
            "partial_retained_ratio": DEFAULT_PRICE_FEEDBACK_PARTIAL_RETAINED_RATIO,
            "basis": "abs_past_return_ic_ge_abs_forward_ic",
        },
    }


def _sample_gate_eta(row: dict[str, Any], *, min_points: int) -> dict[str, Any] | None:
    sample_floor = int(row.get("overlap_adjusted_sample_floor") or 0)
    if sample_floor <= 0 or sample_floor >= min_points:
        return None
    horizon_minutes = int(row.get("horizon_minutes") or 0)
    if horizon_minutes <= 0:
        return None
    last_ts = _parse_dt(row.get("last_nonoverlap_snapshot_ts_utc") or row.get("last_snapshot_ts_utc"))
    if last_ts is None:
        return None
    effective_gap_ms = int(
        row.get("effective_nonoverlap_gap_ms")
        or (_horizon_ms(horizon_minutes) - _schedule_jitter_tolerance_ms(horizon_minutes))
    )
    forecast_gap_ms = max(
        _horizon_ms(horizon_minutes),
        int(row.get("median_sample_spacing_ms") or 0),
        effective_gap_ms,
    )
    if forecast_gap_ms <= 0:
        return None
    samples_remaining = max(0, min_points - sample_floor)
    feature_ts_ms = _dt_to_ms(last_ts) + samples_remaining * forecast_gap_ms
    label_ready_ms = feature_ts_ms + _horizon_ms(horizon_minutes)
    return {
        "expected_gate_feature_ts_utc": _ms_to_iso(feature_ts_ms),
        "expected_gate_label_ready_utc": _ms_to_iso(label_ready_ms),
        "eta_basis": "overlap_adjusted_floor_forecast_gap_plus_forward_horizon",
        "effective_nonoverlap_gap_minutes": effective_gap_ms / 60_000.0,
        "forecast_sample_gap_minutes": forecast_gap_ms / 60_000.0,
    }


def _sample_gate_clock(
    ic_results: list[dict[str, Any]],
    *,
    min_points: int,
    limit: int = 5,
) -> dict[str, Any]:
    max_floor = max(
        (int(row.get("overlap_adjusted_sample_floor") or 0) for row in ic_results),
        default=0,
    )
    cells: list[dict[str, Any]] = []
    for row in ic_results:
        sample_floor = int(row.get("overlap_adjusted_sample_floor") or 0)
        if sample_floor <= 0 or sample_floor >= min_points:
            continue
        eta = _sample_gate_eta(row, min_points=min_points)
        if not eta:
            continue
        cells.append({
            "bucket": row.get("bucket"),
            "symbol": row.get("symbol"),
            "horizon_minutes": row.get("horizon_minutes"),
            "overlap_adjusted_sample_floor": sample_floor,
            "sample_gap_to_min_points": max(0, min_points - sample_floor),
            "last_nonoverlap_snapshot_ts_utc": row.get("last_nonoverlap_snapshot_ts_utc"),
            **eta,
        })

    cells.sort(key=lambda r: (
        str(r.get("expected_gate_label_ready_utc") or ""),
        int(r.get("sample_gap_to_min_points") or 0),
    ))

    if max_floor >= min_points:
        status = "ENOUGH_SAMPLE"
    elif not ic_results:
        status = "NO_IC_ROWS"
    elif cells:
        status = "WAITING_FOR_SAMPLE"
    else:
        status = "ETA_UNAVAILABLE"

    fastest = cells[0] if cells else None
    return {
        "status": status,
        "min_points": min_points,
        "max_overlap_adjusted_sample_floor": max_floor,
        "min_samples_remaining_to_gate": max(0, min_points - max_floor),
        "fastest_gate_feature_ts_utc": (
            fastest.get("expected_gate_feature_ts_utc") if fastest else None
        ),
        "fastest_gate_ready_utc": (
            fastest.get("expected_gate_label_ready_utc") if fastest else None
        ),
        "eta_basis": (
            fastest.get("eta_basis") if fastest else "overlap_adjusted_nonoverlap_floor"
        ),
        "cells": cells[:limit],
    }


def _partition_ic_candidates(
    ic_results: list[dict[str, Any]],
    *,
    min_points: int,
    min_abs_ic: float,
    min_abs_t: float,
    max_bh_q: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    eligible = [
        r for r in ic_results
        if r["n_points"] >= min_points
        and r.get("overlap_adjusted_sample_floor", 0) >= min_points
        and r["ic_pearson"] is not None
    ]
    preliminary_raw = [
        r for r in eligible
        if r.get("t_stat") is not None
        and abs(float(r["ic_pearson"])) >= min_abs_ic
        and abs(float(r["t_stat"])) >= min_abs_t
    ]
    preliminary_hac = [
        r for r in eligible
        if r.get("t_stat_hac") is not None
        and abs(float(r["ic_pearson"])) >= min_abs_ic
        and abs(float(r["t_stat_hac"])) >= min_abs_t
    ]
    candidates = [
        r for r in preliminary_hac
        if r.get("bh_q_value_hac_approx") is not None
        and float(r["bh_q_value_hac_approx"]) <= max_bh_q
    ]
    return eligible, preliminary_raw, preliminary_hac, candidates


def _pre_gate_hac_watchlist(
    ic_results: list[dict[str, Any]],
    *,
    min_points: int,
    min_abs_ic: float,
    min_abs_t: float,
    max_bh_q: float,
    limit: int = 5,
) -> list[dict[str, Any]]:
    rows = []
    for row in ic_results:
        sample_floor = int(row.get("overlap_adjusted_sample_floor") or 0)
        if sample_floor >= min_points or sample_floor <= 0:
            continue
        if row.get("ic_pearson") is None or row.get("t_stat_hac") is None:
            continue
        if row.get("bh_q_value_hac_approx") is None:
            continue
        if abs(float(row["ic_pearson"])) < min_abs_ic:
            continue
        if abs(float(row["t_stat_hac"])) < min_abs_t:
            continue
        if float(row["bh_q_value_hac_approx"]) > max_bh_q:
            continue
        rows.append({
            "bucket": row.get("bucket"),
            "symbol": row.get("symbol"),
            "horizon_minutes": row.get("horizon_minutes"),
            "n_points": row.get("n_points"),
            "overlap_adjusted_sample_floor": sample_floor,
            "sample_gap_to_min_points": max(0, min_points - sample_floor),
            "ic_pearson": row.get("ic_pearson"),
            "t_stat_hac": row.get("t_stat_hac"),
            "bh_q_value_hac_approx": row.get("bh_q_value_hac_approx"),
            "past_return_control_n_points": row.get("past_return_control_n_points"),
            "past_return_ic_pearson": row.get("past_return_ic_pearson"),
            "partial_ic_controlling_trailing_return": row.get(
                "partial_ic_controlling_trailing_return"
            ),
            "partial_ic_retained_abs_ratio": row.get("partial_ic_retained_abs_ratio"),
            "price_feedback_warning": row.get("price_feedback_warning"),
            "price_feedback_partial_collapse_warning": row.get(
                "price_feedback_partial_collapse_warning"
            ),
            "first_snapshot_ts_utc": row.get("first_snapshot_ts_utc"),
            "last_snapshot_ts_utc": row.get("last_snapshot_ts_utc"),
            "last_nonoverlap_snapshot_ts_utc": row.get("last_nonoverlap_snapshot_ts_utc"),
            "gate_blocker": "sample_floor_below_min_points",
            **(_sample_gate_eta(row, min_points=min_points) or {}),
        })
    return sorted(
        rows,
        key=lambda r: (
            abs(float(r.get("t_stat_hac") or 0.0)),
            int(r.get("overlap_adjusted_sample_floor") or 0),
        ),
        reverse=True,
    )[:limit]


def _watchlist_cell_key(row: dict[str, Any]) -> str:
    return "|".join([
        str(row.get("bucket") or "unknown"),
        str(row.get("symbol") or "unknown"),
        str(int(row.get("horizon_minutes") or 0)),
    ])


def _watchlist_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = report.get("pre_gate_hac_watchlist")
    return rows if isinstance(rows, list) else []


def build_pre_gate_watchlist_persistence_scorecard(
    *,
    current_watchlist: list[dict[str, Any]],
    history_reports: list[dict[str, Any]] | None = None,
    current_created_at_utc: str | None = None,
    min_points: int | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Diagnose whether pre-gate HAC cells persist across report refreshes."""
    history_reports = list(history_reports or [])
    min_current_floor_for_status = (
        max(3, int(math.ceil(float(min_points) * 0.25)))
        if min_points is not None and int(min_points) > 0
        else 3
    )
    report_snapshots: list[dict[str, Any]] = []
    for report in history_reports:
        rows = [
            row for row in _watchlist_rows(report)
            if isinstance(row, dict)
        ]
        if not rows:
            continue
        report_snapshots.append({
            "created_at_utc": report.get("created_at_utc"),
            "path": report.get("_history_path"),
            "rows": rows,
        })
    report_snapshots.append({
        "created_at_utc": current_created_at_utc,
        "path": None,
        "rows": [row for row in current_watchlist if isinstance(row, dict)],
    })

    current_by_key = {
        _watchlist_cell_key(row): row
        for row in current_watchlist
        if isinstance(row, dict)
    }
    cell_history: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for idx, snapshot in enumerate(report_snapshots):
        seen_in_report: set[str] = set()
        for row in snapshot["rows"]:
            key = _watchlist_cell_key(row)
            if key in seen_in_report:
                continue
            seen_in_report.add(key)
            cell_history[key].append({
                "report_index": idx,
                "created_at_utc": snapshot.get("created_at_utc"),
                "path": snapshot.get("path"),
                "row": row,
            })

    latest_index = len(report_snapshots) - 1
    cells: list[dict[str, Any]] = []
    for key, current in current_by_key.items():
        observations = cell_history.get(key, [])
        indexes = {int(obs["report_index"]) for obs in observations}
        consecutive = 0
        idx = latest_index
        while idx in indexes:
            consecutive += 1
            idx -= 1
        presence_count = len(observations)
        first_seen = observations[0] if observations else None
        latest_seen = observations[-1] if observations else None
        cells.append({
            "cell_key": key,
            "bucket": current.get("bucket"),
            "symbol": current.get("symbol"),
            "horizon_minutes": current.get("horizon_minutes"),
            "presence_count": presence_count,
            "current_consecutive_reports": consecutive,
            "first_seen_created_at_utc": first_seen.get("created_at_utc") if first_seen else None,
            "latest_seen_created_at_utc": latest_seen.get("created_at_utc") if latest_seen else None,
            "first_seen_sample_floor": (
                (first_seen.get("row") or {}).get("overlap_adjusted_sample_floor")
                if first_seen else None
            ),
            "current_sample_floor": current.get("overlap_adjusted_sample_floor"),
            "floor_qualified_for_status": int(
                current.get("overlap_adjusted_sample_floor") or 0
            ) >= min_current_floor_for_status,
            "sample_gap_to_min_points": current.get("sample_gap_to_min_points"),
            "ic_pearson": current.get("ic_pearson"),
            "t_stat_hac": current.get("t_stat_hac"),
            "bh_q_value_hac_approx": current.get("bh_q_value_hac_approx"),
            "partial_ic_controlling_trailing_return": current.get(
                "partial_ic_controlling_trailing_return"
            ),
            "partial_ic_retained_abs_ratio": current.get("partial_ic_retained_abs_ratio"),
            "price_feedback_warning": current.get("price_feedback_warning"),
            "price_feedback_partial_collapse_warning": current.get(
                "price_feedback_partial_collapse_warning"
            ),
            "expected_gate_label_ready_utc": current.get("expected_gate_label_ready_utc"),
            "gate_blocker": current.get("gate_blocker"),
        })

    cells.sort(key=lambda row: (
        int(row.get("current_consecutive_reports") or 0),
        int(row.get("presence_count") or 0),
        abs(float(row.get("t_stat_hac") or 0.0)),
        int(row.get("current_sample_floor") or 0),
    ), reverse=True)
    persistent_count = sum(1 for row in cells if int(row.get("current_consecutive_reports") or 0) >= 3)
    recurring_count = sum(1 for row in cells if int(row.get("presence_count") or 0) >= 2)
    floor_qualified_persistent_count = sum(
        1 for row in cells
        if int(row.get("current_consecutive_reports") or 0) >= 3
        and row.get("floor_qualified_for_status") is True
    )
    floor_qualified_recurring_count = sum(
        1 for row in cells
        if int(row.get("presence_count") or 0) >= 2
        and row.get("floor_qualified_for_status") is True
    )
    feedback_risk_count = sum(
        1 for row in cells
        if row.get("price_feedback_warning") or row.get("price_feedback_partial_collapse_warning")
    )

    if not current_watchlist:
        status = "NO_PRE_GATE_WATCHLIST"
    elif floor_qualified_persistent_count > 0:
        status = "PERSISTENT_PRE_GATE_WATCHLIST"
    elif floor_qualified_recurring_count > 0:
        status = "RECURRING_PRE_GATE_WATCHLIST"
    elif recurring_count > 0:
        status = "LOW_SAMPLE_RECURRING_PRE_GATE_WATCHLIST"
    else:
        status = "SINGLE_REPORT_PRE_GATE_WATCHLIST"

    return {
        "schema_version": "polymarket_pre_gate_watchlist_persistence_v1",
        "status": status,
        "min_current_sample_floor_for_status": min_current_floor_for_status,
        "history_report_count": len(history_reports),
        "reports_with_watchlist_count": max(0, len(report_snapshots) - 1),
        "current_watchlist_count": len(current_watchlist),
        "current_cell_count": len(cells),
        "recurring_cell_count": recurring_count,
        "persistent_cell_count": persistent_count,
        "floor_qualified_recurring_cell_count": floor_qualified_recurring_count,
        "floor_qualified_persistent_cell_count": floor_qualified_persistent_count,
        "feedback_risk_cell_count": feedback_risk_count,
        "persistence_rule": "current_consecutive_reports_ge_3",
        "top_cells": cells[:limit],
    }


def build_report(
    *,
    snapshot_rows: list[dict[str, Any]],
    snapshot_meta: dict[str, Any],
    price_rows: list[dict[str, Any]],
    query_set_version: str,
    mode: str,
    symbols: tuple[str, ...],
    horizons_minutes: tuple[int, ...],
    min_points: int,
    max_align_lag_minutes: int,
    min_abs_ic: float,
    min_abs_t: float,
    max_bh_q: float,
    price_source: str,
    history_reports: list[dict[str, Any]] | None = None,
    candidate_replay_round_trip_cost_bps: float = candidate_replay.DEFAULT_ROUND_TRIP_COST_BPS,
) -> dict[str, Any]:
    created_at_utc = dt.datetime.now(dt.timezone.utc).isoformat()
    allowed_symbols = set(symbols)
    deltas, delta_meta = build_market_deltas(snapshot_rows, allowed_symbols=allowed_symbols)
    features = aggregate_features(deltas, include_source_splits=True)
    joined = join_forward_returns(
        features, price_rows,
        horizons_minutes=horizons_minutes,
        max_align_lag_minutes=max_align_lag_minutes,
    )
    label_readiness = diagnose_label_readiness(
        features, price_rows,
        horizons_minutes=horizons_minutes,
        max_align_lag_minutes=max_align_lag_minutes,
    )
    ic_results = compute_ic(joined)
    price_feedback_summary = _price_feedback_summary(ic_results)
    bucket_counts = Counter(row["bucket"] for row in deltas)
    feature_bucket_counts = Counter(row["bucket"] for row in features)
    feature_bucket_view_counts = Counter(
        str(row.get("bucket_view") or "unknown") for row in features
    )
    feature_source_counts = Counter(
        str(row.get("symbol_source") or "unknown") for row in features
    )
    joined_counts = Counter(
        f"{row['bucket']}|{row['symbol']}|{row['horizon_minutes']}" for row in joined
    )
    eligible, preliminary_raw, preliminary_hac, candidates = _partition_ic_candidates(
        ic_results,
        min_points=min_points,
        min_abs_ic=min_abs_ic,
        min_abs_t=min_abs_t,
        max_bh_q=max_bh_q,
    )
    pre_gate_hac_watchlist = _pre_gate_hac_watchlist(
        ic_results,
        min_points=min_points,
        min_abs_ic=min_abs_ic,
        min_abs_t=min_abs_t,
        max_bh_q=max_bh_q,
    )
    pre_gate_persistence = build_pre_gate_watchlist_persistence_scorecard(
        current_watchlist=pre_gate_hac_watchlist,
        history_reports=history_reports,
        current_created_at_utc=created_at_utc,
        min_points=min_points,
    )
    sample_gate_clock = _sample_gate_clock(ic_results, min_points=min_points)
    candidate_replay_scorecard = candidate_replay.build_replay_scorecard(
        joined_rows=joined,
        candidates=candidates,
        ic_results=ic_results,
        price_source=price_source,
        round_trip_cost_bps=candidate_replay_round_trip_cost_bps,
    )

    if not snapshot_rows:
        status = STATUS_NO_SNAPSHOT_ROWS
        reason = "no Polymarket snapshot rows matched query_set/mode"
    elif not price_rows:
        status = STATUS_NO_PRICE_DATA
        reason = "no price rows available for forward returns"
    elif not eligible:
        status = STATUS_INSUFFICIENT_SAMPLE
        best_n = max((int(r.get("overlap_adjusted_sample_floor", 0)) for r in ic_results), default=0)
        reason = f"max overlap-adjusted IC points {best_n} below min_points {min_points}"
    elif candidates:
        status = STATUS_IC_CANDIDATE_REVIEW_REQUIRED
        reason = "one or more bucket/symbol/horizon IC cells pass HAC and BH-q thresholds"
    else:
        status = STATUS_IC_READY_NO_SIGNIFICANT_EDGE
        reason = "enough sample for at least one cell, but no HAC-controlled IC threshold pass"

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "created_at_utc": created_at_utc,
        "program": "polymarket-leadlag-ic",
        "query_set_version": query_set_version,
        "mode": mode,
        "symbols": list(symbols),
        "horizons_minutes": list(horizons_minutes),
        "price_source": price_source,
        "verdict": {
            "status": status,
            "reason": reason,
            "min_points": min_points,
            "min_abs_ic": min_abs_ic,
            "min_abs_t": min_abs_t,
            "max_bh_q": max_bh_q,
            "candidate_count": len(candidates),
            "preliminary_raw_candidate_count": len(preliminary_raw),
            "preliminary_hac_candidate_count": len(preliminary_hac),
            "pre_gate_hac_watchlist_count": len(pre_gate_hac_watchlist),
            "pre_gate_watchlist_persistence_status": pre_gate_persistence["status"],
            "pre_gate_watchlist_recurring_cell_count": (
                pre_gate_persistence["recurring_cell_count"]
            ),
            "pre_gate_watchlist_persistent_cell_count": (
                pre_gate_persistence["persistent_cell_count"]
            ),
            "pre_gate_watchlist_floor_qualified_recurring_cell_count": (
                pre_gate_persistence["floor_qualified_recurring_cell_count"]
            ),
            "pre_gate_watchlist_floor_qualified_persistent_cell_count": (
                pre_gate_persistence["floor_qualified_persistent_cell_count"]
            ),
            "price_feedback_warning_count": price_feedback_summary["warning_count"],
            "price_feedback_partial_collapse_count": (
                price_feedback_summary["raw_to_partial_collapse_count"]
            ),
            "significance_t_stat": "t_stat_hac",
            "promotion_boundary": "research_context_only_not_signal_or_promotion_proof",
        },
        "counts": {
            "snapshot_rows": len(snapshot_rows),
            "snapshot_distinct_timestamps": len({
                r.get("snapshot_ts_utc") for r in snapshot_rows if r.get("snapshot_ts_utc")
            }),
            "snapshot_meta": snapshot_meta,
            "delta_rows": len(deltas),
            "feature_points": len(features),
            "joined_rows": len(joined),
            "price_rows": len(price_rows),
            "bucket_delta_counts": dict(bucket_counts),
            "feature_bucket_counts": dict(feature_bucket_counts),
            "feature_bucket_view_counts": dict(feature_bucket_view_counts),
            "feature_source_counts": dict(feature_source_counts),
            "joined_counts": dict(joined_counts),
            "label_readiness": label_readiness,
            "delta_meta": delta_meta,
            "max_ic_points": max((int(r["n_points"]) for r in ic_results), default=0),
            "max_overlap_adjusted_ic_points": max(
                (int(r.get("overlap_adjusted_sample_floor", 0)) for r in ic_results),
                default=0,
            ),
            "min_samples_remaining_to_gate": max(
                0,
                min_points - max(
                    (int(r.get("overlap_adjusted_sample_floor", 0)) for r in ic_results),
                    default=0,
                ),
            ),
            "sample_gate_clock": sample_gate_clock,
            "price_feedback_summary": price_feedback_summary,
            "pre_gate_watchlist_persistence_scorecard": pre_gate_persistence,
            "max_abs_t_stat_hac": max(
                (
                    abs(float(r["t_stat_hac"]))
                    for r in ic_results
                    if r.get("t_stat_hac") is not None
                ),
                default=None,
            ),
        },
        "ic_results": ic_results,
        "candidates": candidates,
        "pre_gate_hac_watchlist": pre_gate_hac_watchlist,
        "candidate_replay_scorecard": candidate_replay_scorecard,
        "sample_joined_rows": joined[:50],
        "method_notes": [
            "feature = probability delta from previous Polymarket snapshot to current snapshot",
            "target = Bybit close return after snapshot time; first kline at/after timestamps only",
            "price_target/event_reg bucket split is research-side and does not filter collector artifacts",
            "event_reg aggregate cells are preserved while event_reg_direct/event_reg_macro "
            "source-split cells are tested separately",
            "insufficient sample fails closed and is not alpha evidence",
            "overlap sample floor allows a small schedule-jitter tolerance before declaring windows overlapping",
            "sample gate clock estimates when the overlap-adjusted floor should reach min_points if cadence holds",
            "pre-gate HAC watchlist is diagnostic only and never promotion or probe authority",
            "pre-gate watchlist persistence is diagnostic only and never promotion or probe authority",
            "past-return price feedback control is diagnostic only and never promotion authority",
            "partial IC controlling for trailing returns is diagnostic only and never promotion authority",
            "candidate gate requires overlap-adjusted sample floor and BH q-value control",
            "candidate significance uses Newey-West/HAC slope t-stat; naive t-stat is diagnostic only",
            "candidate replay is paper PnL evidence only and never execution realism or promotion authority",
        ],
    }


def _git_provenance(repo_root: Path) -> dict[str, Any]:
    def _run(args: list[str]) -> str:
        try:
            return subprocess.run(
                args, cwd=str(repo_root), capture_output=True, text=True, timeout=10,
            ).stdout.strip()
        except Exception:
            return ""

    sha = _run(["git", "rev-parse", "HEAD"]) or "unknown"
    status = _run(["git", "status", "--porcelain"])
    diff = _run(["git", "diff", "HEAD"])
    return {
        "git_sha": sha,
        "git_dirty": bool(status),
        "git_diff_sha256": hashlib.sha256(diff.encode("utf-8")).hexdigest() if diff else None,
    }


def write_report(report: dict[str, Any], out_path: Path, *, repo_root: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **report,
        "runtime_host": socket.gethostname(),
        "git": _git_provenance(repo_root),
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return out_path


def _parse_csv_ints(raw: str) -> tuple[int, ...]:
    vals = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    if not vals:
        raise argparse.ArgumentTypeError("expected comma-separated integer list")
    return vals


def _parse_csv_symbols(raw: str) -> tuple[str, ...]:
    vals = tuple(part.strip().upper() for part in raw.split(",") if part.strip())
    if not vals:
        raise argparse.ArgumentTypeError("expected comma-separated symbols")
    return vals


def default_out_path() -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return _data_root() / "research" / "polymarket_leadlag" / f"polymarket_leadlag_{stamp}.json"


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="polymarket_leadlag.harness",
        description="Polymarket v2 probability delta vs Bybit forward-return IC report",
    )
    p.add_argument("--polymarket-root", default=None, dest="polymarket_root",
                   help="Polymarket run root (default ${OPENCLAW_DATA_DIR}/polymarket_axis_runs)")
    p.add_argument("--query-set", default=DEFAULT_QUERY_SET, choices=["v1", "v2"], dest="query_set")
    p.add_argument("--mode", default=DEFAULT_MODE, dest="mode")
    p.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS), type=_parse_csv_symbols)
    p.add_argument("--horizons-minutes", default=",".join(map(str, DEFAULT_HORIZONS_MINUTES)),
                   type=_parse_csv_ints, dest="horizons_minutes")
    p.add_argument("--min-points", default=DEFAULT_MIN_POINTS, type=int, dest="min_points")
    p.add_argument("--max-align-lag-minutes", default=DEFAULT_MAX_ALIGN_LAG_MINUTES,
                   type=int, dest="max_align_lag_minutes")
    p.add_argument("--min-abs-ic", default=DEFAULT_MIN_ABS_IC, type=float, dest="min_abs_ic")
    p.add_argument("--min-abs-t", default=DEFAULT_MIN_ABS_T, type=float, dest="min_abs_t")
    p.add_argument("--max-bh-q", default=DEFAULT_MAX_BH_Q, type=float, dest="max_bh_q",
                   help="Benjamini-Hochberg q-value ceiling for candidate review")
    p.add_argument("--candidate-replay-round-trip-cost-bps",
                   default=candidate_replay.DEFAULT_ROUND_TRIP_COST_BPS,
                   type=float,
                   dest="candidate_replay_round_trip_cost_bps",
                   help="Explicit diagnostic round-trip cost for paper candidate replay")
    p.add_argument("--price-jsonl", default=None, dest="price_jsonl",
                   help="Optional fixture price JSONL. If absent, read market.klines from PG readonly.")
    p.add_argument("--dsn", default=None, dest="dsn", help="Optional PG DSN override")
    p.add_argument("--price-timeframe", default="1m", dest="price_timeframe")
    p.add_argument("--out", default=None, dest="out")
    p.add_argument("--write-latest", action="store_true", dest="write_latest")
    return p


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.polymarket_root) if args.polymarket_root else _data_root() / "polymarket_axis_runs"
    out_path = Path(args.out) if args.out else default_out_path()
    history_reports = load_recent_report_history(out_path.parent)
    snapshot_rows, snapshot_meta = load_snapshot_rows(
        root, query_set_version=args.query_set, mode=args.mode,
    )
    horizons = tuple(int(x) for x in args.horizons_minutes)
    symbols = tuple(str(x) for x in args.symbols)

    price_source = "fixture"
    if args.price_jsonl:
        price_rows = load_price_points_jsonl(Path(args.price_jsonl))
    else:
        price_source = f"pg:market.klines:{args.price_timeframe}"
        parsed_ts = [
            _parse_dt(row.get("snapshot_ts_utc"))
            for row in snapshot_rows
            if row.get("snapshot_ts_utc")
        ]
        ts_vals = [_dt_to_ms(x) for x in parsed_ts if x is not None]
        if ts_vals:
            pad_ms = (max(horizons) + args.max_align_lag_minutes + 5) * 60 * 1000
            price_rows = load_price_points_pg(
                symbols=list(symbols),
                start_ms=min(ts_vals) - pad_ms,
                end_ms=max(ts_vals) + pad_ms,
                timeframe=args.price_timeframe,
                dsn=args.dsn,
            )
        else:
            price_rows = []

    report = build_report(
        snapshot_rows=snapshot_rows,
        snapshot_meta=snapshot_meta,
        price_rows=price_rows,
        query_set_version=args.query_set,
        mode=args.mode,
        symbols=symbols,
        horizons_minutes=horizons,
        min_points=args.min_points,
        max_align_lag_minutes=args.max_align_lag_minutes,
        min_abs_ic=args.min_abs_ic,
        min_abs_t=args.min_abs_t,
        max_bh_q=args.max_bh_q,
        price_source=price_source,
        history_reports=history_reports,
        candidate_replay_round_trip_cost_bps=args.candidate_replay_round_trip_cost_bps,
    )
    write_report(report, out_path, repo_root=_repo_root())
    if args.write_latest:
        latest = out_path.parent / "polymarket_leadlag_latest.json"
        latest.write_text(out_path.read_text(encoding="utf-8"), encoding="utf-8")
    return {"report": report, "out_path": str(out_path)}


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    result = run(args)
    report = result["report"]
    print(json.dumps({
        "out_path": result["out_path"],
        "status": report["verdict"]["status"],
        "reason": report["verdict"]["reason"],
        "snapshot_rows": report["counts"]["snapshot_rows"],
        "delta_rows": report["counts"]["delta_rows"],
        "joined_rows": report["counts"]["joined_rows"],
        "candidate_count": report["verdict"]["candidate_count"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
