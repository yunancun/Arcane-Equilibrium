"""AEG-S3 OI delta candidate evidence 純函數核心。"""

from __future__ import annotations

import datetime as dt
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Optional

from . import EVIDENCE_SCHEMA_VERSION, RUNNER_VERSION, SAMPLE_UNIT, STRATEGY_FAMILY, SUMMARY_SCHEMA_VERSION


def _float_or_none(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _int_or_none(value: Any) -> Optional[int]:
    f = _float_or_none(value)
    return int(f) if f is not None else None


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


def _date_or_none(value: Any) -> Optional[dt.date]:
    if value is None:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _mean(values: Iterable[float]) -> Optional[float]:
    clean = [v for v in values if math.isfinite(v)]
    return statistics.mean(clean) if clean else None


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
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


def load_regime_by_date(path: Optional[Path]) -> dict[str, str]:
    if path is None:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("regime_by_date"), dict):
        src = payload["regime_by_date"]
    elif isinstance(payload, dict):
        src = payload
    elif isinstance(payload, list):
        src = {
            str(row.get("date") or row.get("sample_date")): row.get("regime")
            for row in payload
            if isinstance(row, dict)
        }
    else:
        return {}
    return {
        str(k)[:10]: str(v).strip()
        for k, v in src.items()
        if str(k).strip() and v is not None and str(v).strip()
    }


def _price(row: dict[str, Any]) -> Optional[float]:
    return _float_or_none(row.get("price") or row.get("close") or row.get("mark_price") or row.get("entry_price"))


def _open_interest(row: dict[str, Any]) -> Optional[float]:
    return _float_or_none(row.get("open_interest") if "open_interest" in row else row.get("oi"))


def _row_ts(row: dict[str, Any]) -> Optional[dt.datetime]:
    return _parse_ts(
        row.get("ts_utc")
        or row.get("ts")
        or row.get("timestamp")
        or row.get("sample_ts_utc")
        or row.get("ts_ms")
    )


def _normalize_raw_rows(payload: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    for idx, row in enumerate(payload):
        symbol = str(row.get("symbol") or "").strip()
        ts = _row_ts(row)
        if not symbol:
            rejects.append({"row_index": idx, "reason": "missing_symbol"})
            continue
        if ts is None:
            rejects.append({"row_index": idx, "symbol": symbol, "reason": "missing_ts"})
            continue
        rows.append({
            "row_index": idx,
            "symbol": symbol,
            "ts": ts,
            "ts_utc": ts.isoformat(),
            "date": ts.date().isoformat(),
            "open_interest": _open_interest(row),
            "price": _price(row),
            "oi_delta_pct": _float_or_none(row.get("oi_delta_pct") or row.get("open_interest_delta_pct")),
            "forward_return_bps": _float_or_none(row.get("forward_return_bps") or row.get("fwd_return_bps")),
            "regime": str(row.get("regime") or "").strip() or None,
            "source_run_id": row.get("run_id"),
        })
    return rows, rejects


def _rows_by_symbol(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        out[row["symbol"]].append(row)
    for symbol in out:
        out[symbol].sort(key=lambda r: r["ts"])
    return out


def _row_at_or_before(rows: list[dict[str, Any]], target: dt.datetime, max_lag: dt.timedelta) -> Optional[dict[str, Any]]:
    best: Optional[dict[str, Any]] = None
    for row in rows:
        if row["ts"] <= target:
            best = row
            continue
        break
    if best is None or target - best["ts"] > max_lag:
        return None
    return best


def _row_at_or_after(rows: list[dict[str, Any]], target: dt.datetime, max_lag: dt.timedelta) -> Optional[dict[str, Any]]:
    for row in rows:
        if row["ts"] >= target:
            if row["ts"] - target <= max_lag:
                return row
            return None
    return None


def _enriched_rows(
    raw_rows: list[dict[str, Any]],
    *,
    lookback_hours: float,
    horizon_hours: float,
    max_timestamp_lag_minutes: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_symbol = _rows_by_symbol(raw_rows)
    lookback = dt.timedelta(hours=lookback_hours)
    horizon = dt.timedelta(hours=horizon_hours)
    max_lag = dt.timedelta(minutes=max_timestamp_lag_minutes)
    enriched: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []

    for row in raw_rows:
        symbol_rows = by_symbol[row["symbol"]]
        oi_delta = row.get("oi_delta_pct")
        if oi_delta is None:
            current_oi = row.get("open_interest")
            prev = _row_at_or_before(symbol_rows, row["ts"] - lookback, max_lag)
            prev_oi = prev.get("open_interest") if prev is not None else None
            if current_oi is None or prev_oi is None or prev_oi <= 0:
                rejects.append({"row_index": row["row_index"], "symbol": row["symbol"], "reason": "missing_oi_delta_or_prior_oi"})
                continue
            oi_delta = (current_oi - prev_oi) / prev_oi

        forward_bps = row.get("forward_return_bps")
        exit_price = None
        if forward_bps is None:
            entry = row.get("price")
            future = _row_at_or_after(symbol_rows, row["ts"] + horizon, max_lag)
            exit_price = future.get("price") if future is not None else None
            if entry is None or exit_price is None or entry <= 0:
                rejects.append({"row_index": row["row_index"], "symbol": row["symbol"], "reason": "missing_forward_return_or_future_price"})
                continue
            forward_bps = (exit_price - entry) / entry * 10_000.0

        if not math.isfinite(oi_delta) or not math.isfinite(forward_bps):
            rejects.append({"row_index": row["row_index"], "symbol": row["symbol"], "reason": "non_finite_signal_or_return"})
            continue

        enriched.append({
            **row,
            "oi_delta_pct": oi_delta,
            "forward_return_bps": forward_bps,
            "exit_price": exit_price,
        })
    return enriched, rejects


def _regime_for_window(
    ts: dt.datetime,
    rows: list[dict[str, Any]],
    *,
    regime_by_date: dict[str, str],
    default_regime: Optional[str],
) -> Optional[str]:
    date_key = ts.date().isoformat()
    if date_key in regime_by_date:
        return regime_by_date[date_key]
    if default_regime:
        return default_regime
    row_regimes = {str(row.get("regime") or "").strip() for row in rows if str(row.get("regime") or "").strip()}
    return next(iter(row_regimes)) if len(row_regimes) == 1 else None


def _daily_returns(samples: list[dict[str, Any]]) -> dict[str, Any]:
    by_date: dict[str, float] = defaultdict(float)
    regime_by_date: dict[str, set[str]] = defaultdict(set)
    for row in samples:
        d = str(row["sample_ts_utc"])[:10]
        by_date[d] += float(row["net_bps"]) / 10_000.0
        regime_by_date[d].add(str(row["regime"]))
    return {
        "unit": "fraction",
        "policy": "sum_explicit_oi_delta_window_net_bps_by_sample_date",
        "regime_by_date": {
            d: next(iter(regimes))
            for d, regimes in sorted(regime_by_date.items())
            if len(regimes) == 1
        },
        "values": dict(sorted(by_date.items())),
    }


def _sample_from_window(
    *,
    ts: dt.datetime,
    rows: list[dict[str, Any]],
    tail_frac: float,
    min_symbols: int,
    cost_bps: float,
    side_mode: str,
    regime: str,
    oos_start_date: Optional[dt.date],
) -> tuple[Optional[dict[str, Any]], str]:
    valid = sorted(rows, key=lambda r: r["oi_delta_pct"])
    n = len(valid)
    if n < min_symbols:
        return None, "insufficient_symbols"
    tail_count = int(math.floor(n * tail_frac))
    tail_count = max(1, min(tail_count, n // 2))
    if tail_count <= 0 or tail_count * 2 > n:
        return None, "empty_or_overlapping_tails"

    bottom = valid[:tail_count]
    top = valid[-tail_count:]
    top_mean = _mean(row["forward_return_bps"] for row in top)
    bottom_mean = _mean(row["forward_return_bps"] for row in bottom)
    if top_mean is None or bottom_mean is None:
        return None, "missing_tail_forward_returns"
    if side_mode == "long_high_short_low":
        gross_bps = top_mean - bottom_mean
    elif side_mode == "short_high_long_low":
        gross_bps = bottom_mean - top_mean
    else:
        return None, f"unsupported_side_mode:{side_mode}"
    net_bps = gross_bps - cost_bps
    sample_day = ts.date()
    return {
        "sample_id": f"oi_delta:{ts.isoformat()}",
        "sample_ts_utc": ts.isoformat(),
        "regime": regime,
        "independence_bucket": f"{ts.isoformat()}:oi_delta_rebalance",
        "gross_bps": round(gross_bps, 8),
        "cost_bps": round(cost_bps, 8),
        "net_bps": round(net_bps, 8),
        "is_oos": (sample_day >= oos_start_date) if oos_start_date is not None else None,
        "n_symbols": n,
        "tail_count": tail_count,
        "top_mean_forward_bps": round(top_mean, 8),
        "bottom_mean_forward_bps": round(bottom_mean, 8),
        "top_symbols": [row["symbol"] for row in top],
        "bottom_symbols": [row["symbol"] for row in bottom],
    }, ""


def _window_samples(
    enriched: list[dict[str, Any]],
    *,
    tail_frac: float,
    min_symbols: int,
    min_spacing_hours: float,
    cost_bps: float,
    side_mode: str,
    regime_by_date: dict[str, str],
    default_regime: Optional[str],
    oos_start_date: Optional[dt.date],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_ts: dict[dt.datetime, list[dict[str, Any]]] = defaultdict(list)
    for row in enriched:
        by_ts[row["ts"]].append(row)

    samples: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    last_accepted: Optional[dt.datetime] = None
    min_spacing = dt.timedelta(hours=min_spacing_hours)

    for ts in sorted(by_ts):
        rows = by_ts[ts]
        if last_accepted is not None and ts - last_accepted < min_spacing:
            rejects.append({"sample_ts_utc": ts.isoformat(), "reason": "overlap_spacing"})
            continue
        regime = _regime_for_window(ts, rows, regime_by_date=regime_by_date, default_regime=default_regime)
        if not regime:
            rejects.append({"sample_ts_utc": ts.isoformat(), "reason": "missing_regime"})
            continue
        sample, reason = _sample_from_window(
            ts=ts,
            rows=rows,
            tail_frac=tail_frac,
            min_symbols=min_symbols,
            cost_bps=cost_bps,
            side_mode=side_mode,
            regime=regime,
            oos_start_date=oos_start_date,
        )
        if sample is None:
            rejects.append({"sample_ts_utc": ts.isoformat(), "reason": reason})
            continue
        samples.append(sample)
        last_accepted = ts
    return samples, rejects


def build_oi_delta_evidence(
    payload: list[dict[str, Any]],
    *,
    source_path: str,
    run_id: str,
    lookback_hours: float,
    horizon_hours: float,
    cost_bps: float,
    k_trials: int,
    candidate_id: str = "oi_delta",
    tail_frac: float = 0.2,
    min_symbols: int = 10,
    min_spacing_hours: Optional[float] = None,
    max_timestamp_lag_minutes: float = 90.0,
    side_mode: str = "long_high_short_low",
    regime_by_date: Optional[dict[str, str]] = None,
    default_regime: Optional[str] = None,
    oos_start_date: Optional[str] = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if lookback_hours <= 0:
        raise ValueError("lookback_hours_must_be_positive")
    if horizon_hours <= 0:
        raise ValueError("horizon_hours_must_be_positive")
    if cost_bps < 0:
        raise ValueError("cost_bps_must_be_non_negative")
    if k_trials <= 1:
        raise ValueError("k_trials_must_be_gt_1")
    if not (0.0 < tail_frac <= 0.5):
        raise ValueError("tail_frac_must_be_in_(0,0.5]")
    if min_symbols < 2:
        raise ValueError("min_symbols_must_be_at_least_2")
    if max_timestamp_lag_minutes < 0:
        raise ValueError("max_timestamp_lag_minutes_must_be_non_negative")

    raw_rows, raw_rejects = _normalize_raw_rows(payload)
    enriched, enrichment_rejects = _enriched_rows(
        raw_rows,
        lookback_hours=lookback_hours,
        horizon_hours=horizon_hours,
        max_timestamp_lag_minutes=max_timestamp_lag_minutes,
    )
    spacing = horizon_hours if min_spacing_hours is None else min_spacing_hours
    samples, window_rejects = _window_samples(
        enriched,
        tail_frac=tail_frac,
        min_symbols=min_symbols,
        min_spacing_hours=spacing,
        cost_bps=cost_bps,
        side_mode=side_mode,
        regime_by_date=regime_by_date or {},
        default_regime=default_regime,
        oos_start_date=_date_or_none(oos_start_date),
    )

    daily_returns = _daily_returns(samples) if samples else None
    parameter_cell_id = (
        f"lb{lookback_hours:g}h_h{horizon_hours:g}h_tail{tail_frac:g}_"
        f"cost{cost_bps:g}_{side_mode}"
    )
    evidence: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "run_id": run_id,
        "candidate_id": candidate_id,
        "strategy_family": STRATEGY_FAMILY,
        "parameter_cell_id": parameter_cell_id,
        "selected_variant": side_mode,
        "sample_unit": SAMPLE_UNIT,
        "k_trials": k_trials,
        "annualization_factor": 365,
        "samples": samples,
        "source": {
            "source_type": "offline_panel_jsonl",
            "source_path": source_path,
            "lookback_hours": lookback_hours,
            "horizon_hours": horizon_hours,
            "tail_frac": tail_frac,
            "min_symbols": min_symbols,
            "min_spacing_hours": spacing,
            "max_timestamp_lag_minutes": max_timestamp_lag_minutes,
            "round_trip_cost_bps": cost_bps,
            "side_mode": side_mode,
        },
        "policy": "explicit_oi_delta_rebalance_windows_only_no_db_or_scalar_synthesis",
    }
    if daily_returns is not None:
        evidence["daily_returns"] = daily_returns

    all_rejects = raw_rejects + enrichment_rejects + window_rejects
    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "run_id": run_id,
        "candidate_id": candidate_id,
        "strategy_family": STRATEGY_FAMILY,
        "parameter_cell_id": parameter_cell_id,
        "source_type": "offline_panel_jsonl",
        "source_path": source_path,
        "lookback_hours": lookback_hours,
        "horizon_hours": horizon_hours,
        "tail_frac": tail_frac,
        "min_symbols": min_symbols,
        "min_spacing_hours": spacing,
        "round_trip_cost_bps": cost_bps,
        "k_trials": k_trials,
        "side_mode": side_mode,
        "raw_row_count": len(payload),
        "enriched_row_count": len(enriched),
        "sample_count": len(samples),
        "rejected_row_count": len(raw_rejects) + len(enrichment_rejects),
        "rejected_window_count": len(window_rejects),
        "rejected_sample_count": len(all_rejects),
        "reject_reasons": dict(sorted(Counter(row["reason"] for row in all_rejects).items())),
        "row_reject_reasons": dict(sorted(Counter(row["reason"] for row in raw_rejects + enrichment_rejects).items())),
        "window_reject_reasons": dict(sorted(Counter(row["reason"] for row in window_rejects).items())),
        "accepted_regime_counts": dict(sorted(Counter(row["regime"] for row in samples).items())),
        "accepted_gross_bps_mean": round(statistics.mean([row["gross_bps"] for row in samples]), 8) if samples else None,
        "accepted_net_bps_mean": round(statistics.mean([row["net_bps"] for row in samples]), 8) if samples else None,
        "daily_return_count": len((daily_returns or {}).get("values", {})),
        "pbo_status": "not_produced_missing_candidate_grid",
        "notes": [
            "gross_bps is explicit cross-sectional top-minus-bottom forward return by default",
            "round_trip_cost_bps is subtracted from every accepted rebalance window",
            "daily_returns are aggregated from explicit accepted samples only",
            "pbo is intentionally absent until explicit candidate-grid evidence exists",
        ],
        "rejected_samples": all_rejects,
    }
    return evidence, summary
