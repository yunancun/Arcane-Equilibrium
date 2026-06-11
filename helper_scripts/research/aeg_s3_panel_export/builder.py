"""AEG-S3 offline panel export pure builder."""

from __future__ import annotations

import datetime as dt
import json
import math
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Optional

from . import RUNNER_VERSION, SUMMARY_SCHEMA_VERSION


def _float_or_none(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _parse_ts(value: Any) -> Optional[dt.datetime]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(float(value) / 1000.0, tz=dt.timezone.utc)
    s = str(value).strip()
    if not s:
        return None
    if s.isdigit():
        return dt.datetime.fromtimestamp(int(s) / 1000.0, tz=dt.timezone.utc)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _date_key(value: Any) -> Optional[str]:
    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return value.isoformat()
    ts = _parse_ts(value)
    if ts is not None:
        return ts.date().isoformat()
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s[:10]).isoformat()
    except ValueError:
        return None


def _symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _price_value(row: dict[str, Any]) -> Optional[float]:
    for key in ("price", "close", "mark_price"):
        if key in row:
            out = _float_or_none(row.get(key))
            if out is not None:
                return out
    return None


def _price_ts(row: dict[str, Any]) -> Optional[dt.datetime]:
    return _parse_ts(row.get("ts_utc") or row.get("signal_ts") or row.get("ts") or row.get("close_ts"))


def _regime_lookup(
    regime_by_symbol_date: dict[tuple[str, str], str],
    regime_by_date: dict[str, str],
    *,
    symbol: str,
    date: str,
) -> Optional[str]:
    regime = regime_by_symbol_date.get((symbol, date)) or regime_by_date.get(date)
    return str(regime).strip() if regime is not None and str(regime).strip() else None


def normalize_price_rows(rows: Iterable[dict[str, Any]]) -> tuple[dict[tuple[str, str], dict[str, Any]], list[dict[str, Any]]]:
    """Normalize price rows to one latest row per `(symbol, date)`."""
    prices: dict[tuple[str, str], dict[str, Any]] = {}
    rejects: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        symbol = _symbol(row.get("symbol"))
        ts = _price_ts(row)
        price = _price_value(row)
        date = _date_key(row.get("date") or ts)
        if not symbol:
            rejects.append({"row_index": idx, "reason": "missing_symbol", "source": "price"})
            continue
        if ts is None or date is None:
            rejects.append({"row_index": idx, "symbol": symbol, "reason": "missing_ts", "source": "price"})
            continue
        if price is None or price <= 0:
            rejects.append({"row_index": idx, "symbol": symbol, "reason": "missing_price", "source": "price"})
            continue
        key = (symbol, date)
        current = prices.get(key)
        candidate = {
            "symbol": symbol,
            "date": date,
            "ts": ts,
            "ts_utc": ts.isoformat(),
            "price": price,
        }
        if current is None or ts >= current["ts"]:
            prices[key] = candidate
    return prices, rejects


def normalize_regime_rows(rows: Iterable[dict[str, Any]]) -> tuple[dict[tuple[str, str], str], dict[str, str], list[dict[str, Any]]]:
    by_symbol_date: dict[tuple[str, str], str] = {}
    by_date_votes: dict[str, list[str]] = {}
    rejects: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        symbol = _symbol(row.get("symbol") or row.get("market_symbol"))
        date = _date_key(row.get("date") or row.get("sample_date") or row.get("signal_ts") or row.get("ts_utc"))
        regime = str(row.get("regime") or row.get("main_regime") or row.get("market_anchor_regime") or "").strip()
        if not symbol:
            rejects.append({"row_index": idx, "reason": "missing_symbol", "source": "regime"})
            continue
        if date is None:
            rejects.append({"row_index": idx, "symbol": symbol, "reason": "missing_date", "source": "regime"})
            continue
        if not regime or regime == "insufficient_context":
            rejects.append({"row_index": idx, "symbol": symbol, "date": date, "reason": "missing_regime", "source": "regime"})
            continue
        by_symbol_date[(symbol, date)] = regime
        by_date_votes.setdefault(date, []).append(regime)
    by_date = {
        date: Counter(values).most_common(1)[0][0]
        for date, values in by_date_votes.items()
        if values
    }
    return by_symbol_date, by_date, rejects


def build_daily_oi_delta_panel(
    *,
    price_rows: Iterable[dict[str, Any]],
    oi_rows: Iterable[dict[str, Any]],
    regime_rows: Iterable[dict[str, Any]],
    run_id: str,
    category: str = "linear",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build daily OI/price/regime JSONL rows for `aeg_s3_oi_delta`.

    OI history may be intraday. This exporter intentionally emits one row per
    symbol/date: the latest OI observation on that date plus the daily price.
    """
    prices, price_rejects = normalize_price_rows(price_rows)
    regime_by_symbol_date, regime_by_date, regime_rejects = normalize_regime_rows(regime_rows)
    latest_oi: dict[tuple[str, str], dict[str, Any]] = {}
    oi_rejects: list[dict[str, Any]] = []
    for idx, row in enumerate(oi_rows):
        symbol = _symbol(row.get("symbol"))
        ts = _parse_ts(row.get("ts_utc") or row.get("ts"))
        date = _date_key(row.get("date") or ts)
        value = _float_or_none(row.get("open_interest") if "open_interest" in row else row.get("oi"))
        row_category = str(row.get("category") or category).strip()
        if row_category != category:
            continue
        if not symbol:
            oi_rejects.append({"row_index": idx, "reason": "missing_symbol", "source": "oi"})
            continue
        if ts is None or date is None:
            oi_rejects.append({"row_index": idx, "symbol": symbol, "reason": "missing_ts", "source": "oi"})
            continue
        if value is None or value < 0:
            oi_rejects.append({"row_index": idx, "symbol": symbol, "date": date, "reason": "missing_open_interest", "source": "oi"})
            continue
        key = (symbol, date)
        candidate = {
            "symbol": symbol,
            "date": date,
            "oi_ts_utc": ts.isoformat(),
            "open_interest": value,
            "interval_time": row.get("interval_time"),
        }
        current = latest_oi.get(key)
        if current is None or ts.isoformat() >= current["oi_ts_utc"]:
            latest_oi[key] = candidate

    out: list[dict[str, Any]] = []
    row_rejects: list[dict[str, Any]] = []
    for key in sorted(latest_oi):
        symbol, date = key
        price = prices.get(key)
        if price is None:
            row_rejects.append({"symbol": symbol, "date": date, "reason": "missing_price", "source": "oi_panel"})
            continue
        # OI delta is cross-sectional by timestamp; every symbol in the same
        # rebalance window must carry one market-level regime.
        regime = regime_by_date.get(date)
        if regime is None:
            row_rejects.append({"symbol": symbol, "date": date, "reason": "missing_regime", "source": "oi_panel"})
            continue
        oi = latest_oi[key]
        out.append({
            "symbol": symbol,
            "ts_utc": price["ts_utc"],
            "date": date,
            "open_interest": oi["open_interest"],
            "price": price["price"],
            "regime": regime,
            "run_id": run_id,
            "category": category,
            "oi_ts_utc": oi["oi_ts_utc"],
            "price_ts_utc": price["ts_utc"],
            "interval_time": oi.get("interval_time"),
        })

    rejects = price_rejects + regime_rejects + oi_rejects + row_rejects
    return out, _summary(
        panel_name="oi_delta_panel_jsonl",
        run_id=run_id,
        rows=out,
        rejects=rejects,
        source_counts={
            "price_rows": len(list(price_rows)) if isinstance(price_rows, list) else None,
            "oi_rows": len(list(oi_rows)) if isinstance(oi_rows, list) else None,
            "regime_rows": len(list(regime_rows)) if isinstance(regime_rows, list) else None,
        },
    )


def build_funding_revive_panel(
    *,
    price_rows: Iterable[dict[str, Any]],
    funding_rows: Iterable[dict[str, Any]],
    regime_rows: Iterable[dict[str, Any]],
    run_id: str,
    category: str = "linear",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build funding/price/regime JSONL rows for `aeg_s3_funding_revive`."""
    prices, price_rejects = normalize_price_rows(price_rows)
    regime_by_symbol_date, regime_by_date, regime_rejects = normalize_regime_rows(regime_rows)
    out: list[dict[str, Any]] = []
    funding_rejects: list[dict[str, Any]] = []
    for idx, row in enumerate(funding_rows):
        symbol = _symbol(row.get("symbol"))
        ts = _parse_ts(row.get("funding_ts") or row.get("ts_utc") or row.get("ts"))
        date = _date_key(row.get("date") or ts)
        rate = _float_or_none(row.get("funding_rate"))
        if rate is None and "funding_bps" in row:
            bps = _float_or_none(row.get("funding_bps"))
            rate = bps / 10_000.0 if bps is not None else None
        row_category = str(row.get("category") or category).strip()
        if row_category != category:
            continue
        if not symbol:
            funding_rejects.append({"row_index": idx, "reason": "missing_symbol", "source": "funding"})
            continue
        if ts is None or date is None:
            funding_rejects.append({"row_index": idx, "symbol": symbol, "reason": "missing_ts", "source": "funding"})
            continue
        if rate is None:
            funding_rejects.append({"row_index": idx, "symbol": symbol, "date": date, "reason": "missing_funding_rate", "source": "funding"})
            continue
        price = prices.get((symbol, date))
        if price is None:
            funding_rejects.append({"row_index": idx, "symbol": symbol, "date": date, "reason": "missing_price", "source": "funding_panel"})
            continue
        regime = _regime_lookup(regime_by_symbol_date, regime_by_date, symbol=symbol, date=date)
        if regime is None:
            funding_rejects.append({"row_index": idx, "symbol": symbol, "date": date, "reason": "missing_regime", "source": "funding_panel"})
            continue
        out.append({
            "symbol": symbol,
            "ts_utc": ts.isoformat(),
            "date": date,
            "funding_rate": rate,
            "funding_bps": rate * 10_000.0,
            "price": price["price"],
            "regime": regime,
            "run_id": run_id,
            "category": category,
            "price_ts_utc": price["ts_utc"],
            "funding_interval_minutes": row.get("funding_interval_minutes"),
        })

    out.sort(key=lambda r: (r["ts_utc"], r["symbol"]))
    rejects = price_rejects + regime_rejects + funding_rejects
    return out, _summary(
        panel_name="funding_revive_panel_jsonl",
        run_id=run_id,
        rows=out,
        rejects=rejects,
        source_counts={
            "price_rows": len(list(price_rows)) if isinstance(price_rows, list) else None,
            "funding_rows": len(list(funding_rows)) if isinstance(funding_rows, list) else None,
            "regime_rows": len(list(regime_rows)) if isinstance(regime_rows, list) else None,
        },
    )


def _summary(
    *,
    panel_name: str,
    run_id: str,
    rows: list[dict[str, Any]],
    rejects: list[dict[str, Any]],
    source_counts: dict[str, Optional[int]],
) -> dict[str, Any]:
    dates = sorted({row["date"] for row in rows})
    symbols = sorted({row["symbol"] for row in rows})
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "panel_name": panel_name,
        "run_id": run_id,
        "row_count": len(rows),
        "symbol_count": len(symbols),
        "date_span": [dates[0], dates[-1]] if dates else [None, None],
        "symbols": symbols,
        "source_counts": source_counts,
        "rejected_row_count": len(rejects),
        "reject_reasons": dict(sorted(Counter(row["reason"] for row in rejects).items())),
        "price_policy": "daily_close_price_joined_by_symbol_date",
        "regime_policy": "symbol_date_regime_preferred_then_date_majority",
        "notes": [
            "exporter produces offline JSONL only",
            "OI panel is daily-resampled latest OI per symbol/date",
            "funding panel keeps every explicit funding settlement row",
        ],
        "rejected_rows": rejects,
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) for row in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )
    return path


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return path


def combined_summary(*summaries: dict[str, Any], run_id: str) -> dict[str, Any]:
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "run_id": run_id,
        "panel_count": len(summaries),
        "panels": list(summaries),
        "total_rows": sum(int(s.get("row_count") or 0) for s in summaries),
        "total_rejected_rows": sum(int(s.get("rejected_row_count") or 0) for s in summaries),
    }
