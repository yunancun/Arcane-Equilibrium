"""AEG-S3 funding revive candidate evidence pure builder."""

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


def _round_for_output(value: float) -> float:
    return round(float(value), 12)


def _first_float(row: dict[str, Any], keys: Iterable[str]) -> Optional[float]:
    for key in keys:
        if key in row:
            val = _float_or_none(row.get(key))
            if val is not None:
                return val
    return None


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


def _row_ts(row: dict[str, Any]) -> Optional[dt.datetime]:
    return _parse_ts(
        row.get("ts_utc")
        or row.get("ts")
        or row.get("timestamp")
        or row.get("sample_ts_utc")
        or row.get("ts_ms")
    )


def _price(row: dict[str, Any]) -> Optional[float]:
    return _first_float(row, ("price", "close", "mark_price", "entry_price"))


def _funding_bps(row: dict[str, Any]) -> Optional[float]:
    explicit = _first_float(row, ("funding_bps", "funding_rate_bps"))
    if explicit is not None:
        return explicit
    rate = _first_float(row, ("funding_rate", "funding"))
    return rate * 10_000.0 if rate is not None else None


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
            "funding_bps": _funding_bps(row),
            "funding_zscore": _first_float(row, ("funding_zscore", "funding_stress_zscore", "zscore")),
            "price": _price(row),
            "forward_return_bps": _first_float(row, ("forward_return_bps", "fwd_return_bps")),
            "gross_price_bps": _first_float(row, ("gross_price_bps", "price_pnl_bps")),
            "funding_pnl_bps": _first_float(row, ("funding_pnl_bps", "carry_pnl_bps")),
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


def _compute_missing_zscores(rows: list[dict[str, Any]], *, lookback_points: int) -> list[dict[str, Any]]:
    by_symbol = _rows_by_symbol(rows)
    enriched: list[dict[str, Any]] = []
    for symbol_rows in by_symbol.values():
        prior: list[float] = []
        for row in symbol_rows:
            z = row.get("funding_zscore")
            funding = row.get("funding_bps")
            if z is None and funding is not None and len(prior) >= lookback_points:
                window = prior[-lookback_points:]
                sd = statistics.stdev(window) if len(window) >= 2 else 0.0
                if sd > 0:
                    z = (funding - statistics.mean(window)) / sd
            copy = {**row, "funding_zscore": z}
            enriched.append(copy)
            if funding is not None:
                prior.append(funding)
    enriched.sort(key=lambda r: (r["ts"], r["symbol"], r["row_index"]))
    return enriched


def _row_at_or_after(rows: list[dict[str, Any]], target: dt.datetime, max_lag: dt.timedelta) -> Optional[dict[str, Any]]:
    for row in rows:
        if row["ts"] >= target:
            if row["ts"] - target <= max_lag:
                return row
            return None
    return None


def _regime_for_event(
    row: dict[str, Any],
    *,
    regime_by_date: dict[str, str],
    default_regime: Optional[str],
) -> Optional[str]:
    date_key = row["date"]
    if date_key in regime_by_date:
        return regime_by_date[date_key]
    if row.get("regime"):
        return str(row["regime"]).strip()
    if default_regime:
        return default_regime
    return None


def _funding_pnl_between(
    rows: list[dict[str, Any]],
    *,
    start_ts: dt.datetime,
    exit_ts: dt.datetime,
    side: int,
) -> Optional[float]:
    values = [
        -side * float(row["funding_bps"])
        for row in rows
        if start_ts < row["ts"] <= exit_ts and row.get("funding_bps") is not None
    ]
    return sum(values) if values else None


def _sample_from_event(
    *,
    row: dict[str, Any],
    symbol_rows: list[dict[str, Any]],
    side: int,
    horizon: dt.timedelta,
    max_lag: dt.timedelta,
    cost_bps: float,
    regime: str,
    oos_start_date: Optional[dt.date],
) -> tuple[Optional[dict[str, Any]], str]:
    event_ts = row["ts"]
    target = event_ts + horizon
    exit_row = _row_at_or_after(symbol_rows, target, max_lag)
    exit_ts = exit_row["ts"] if exit_row is not None else target

    gross_price = row.get("gross_price_bps")
    forward_bps = row.get("forward_return_bps")
    entry_price = row.get("price")
    exit_price = exit_row.get("price") if exit_row is not None else None

    if gross_price is None:
        if forward_bps is None:
            if entry_price is None or exit_price is None or entry_price <= 0:
                return None, "missing_forward_return_or_future_price"
            forward_bps = (exit_price - entry_price) / entry_price * 10_000.0
        gross_price = side * forward_bps

    if not math.isfinite(gross_price):
        return None, "non_finite_price_return"

    funding_pnl = row.get("funding_pnl_bps")
    if funding_pnl is None:
        funding_pnl = _funding_pnl_between(symbol_rows, start_ts=event_ts, exit_ts=exit_ts, side=side)
    if funding_pnl is None:
        return None, "missing_funding_pnl_window"
    if not math.isfinite(funding_pnl):
        return None, "non_finite_funding_pnl"

    gross = gross_price + funding_pnl
    net = gross - cost_bps
    sample_day = event_ts.date()
    side_name = "long" if side > 0 else "short"
    stress_direction = "negative" if side > 0 else "positive"
    return {
        "sample_id": f"funding_revive:{row['symbol']}:{event_ts.isoformat()}:{side_name}",
        "sample_ts_utc": event_ts.isoformat(),
        "symbol": row["symbol"],
        "regime": regime,
        "independence_bucket": f"{sample_day.isoformat()}:funding_revive",
        "gross_bps": _round_for_output(gross),
        "cost_bps": _round_for_output(cost_bps),
        "net_bps": _round_for_output(net),
        "is_oos": (sample_day >= oos_start_date) if oos_start_date is not None else None,
        "side": side_name,
        "stress_direction": stress_direction,
        "gross_price_bps": _round_for_output(gross_price),
        "funding_pnl_bps": _round_for_output(funding_pnl),
        "funding_zscore": _round_for_output(row["funding_zscore"]),
        "entry_price": entry_price,
        "exit_price": exit_price,
        "exit_ts_utc": exit_ts.isoformat(),
    }, ""


def _event_samples(
    rows: list[dict[str, Any]],
    *,
    horizon_hours: float,
    stress_z: float,
    exit_z: float,
    cost_bps: float,
    min_spacing_hours: float,
    max_timestamp_lag_minutes: float,
    regime_by_date: dict[str, str],
    default_regime: Optional[str],
    oos_start_date: Optional[dt.date],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_symbol = _rows_by_symbol(rows)
    horizon = dt.timedelta(hours=horizon_hours)
    spacing = dt.timedelta(hours=min_spacing_hours)
    max_lag = dt.timedelta(minutes=max_timestamp_lag_minutes)
    samples: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []

    for symbol, symbol_rows in sorted(by_symbol.items()):
        active_direction: Optional[int] = None
        last_accepted: Optional[dt.datetime] = None
        for row in symbol_rows:
            z = row.get("funding_zscore")
            if z is None:
                continue
            if active_direction is None:
                if z <= -stress_z:
                    active_direction = -1
                elif z >= stress_z:
                    active_direction = 1
                continue

            side: Optional[int] = None
            if active_direction < 0 and z >= -exit_z:
                side = 1
            elif active_direction > 0 and z <= exit_z:
                side = -1

            if side is None:
                if z <= -stress_z:
                    active_direction = -1
                elif z >= stress_z:
                    active_direction = 1
                continue

            active_direction = None
            if last_accepted is not None and row["ts"] - last_accepted < spacing:
                rejects.append({"sample_ts_utc": row["ts_utc"], "symbol": symbol, "reason": "overlap_spacing"})
                continue

            regime = _regime_for_event(row, regime_by_date=regime_by_date, default_regime=default_regime)
            if not regime:
                rejects.append({"sample_ts_utc": row["ts_utc"], "symbol": symbol, "reason": "missing_regime"})
                continue

            sample, reason = _sample_from_event(
                row=row,
                symbol_rows=symbol_rows,
                side=side,
                horizon=horizon,
                max_lag=max_lag,
                cost_bps=cost_bps,
                regime=regime,
                oos_start_date=oos_start_date,
            )
            if sample is None:
                rejects.append({"sample_ts_utc": row["ts_utc"], "symbol": symbol, "reason": reason})
                continue
            samples.append(sample)
            last_accepted = row["ts"]

    samples.sort(key=lambda r: (r["sample_ts_utc"], r["symbol"]))
    return samples, rejects


def _daily_returns(samples: list[dict[str, Any]]) -> dict[str, Any]:
    by_date: dict[str, list[float]] = defaultdict(list)
    regime_by_date: dict[str, set[str]] = defaultdict(set)
    for row in samples:
        d = str(row["sample_ts_utc"])[:10]
        by_date[d].append(float(row["net_bps"]) / 10_000.0)
        regime_by_date[d].add(str(row["regime"]))
    return {
        "unit": "fraction",
        "policy": "mean_explicit_funding_revive_event_net_bps_by_sample_date",
        "regime_by_date": {
            d: next(iter(regimes))
            for d, regimes in sorted(regime_by_date.items())
            if len(regimes) == 1
        },
        "values": {
            d: statistics.mean(vals)
            for d, vals in sorted(by_date.items())
        },
    }


def build_funding_revive_evidence(
    payload: list[dict[str, Any]],
    *,
    source_path: str,
    run_id: str,
    lookback_points: int,
    horizon_hours: float,
    stress_z: float,
    exit_z: float,
    cost_bps: float,
    k_trials: int,
    candidate_id: str = "funding_revive",
    min_spacing_hours: Optional[float] = None,
    max_timestamp_lag_minutes: float = 90.0,
    regime_by_date: Optional[dict[str, str]] = None,
    default_regime: Optional[str] = None,
    oos_start_date: Optional[str] = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if lookback_points < 2:
        raise ValueError("lookback_points_must_be_at_least_2")
    if horizon_hours <= 0:
        raise ValueError("horizon_hours_must_be_positive")
    if stress_z <= 0:
        raise ValueError("stress_z_must_be_positive")
    if exit_z < 0 or exit_z >= stress_z:
        raise ValueError("exit_z_must_be_non_negative_and_below_stress_z")
    if cost_bps < 0:
        raise ValueError("cost_bps_must_be_non_negative")
    if k_trials <= 1:
        raise ValueError("k_trials_must_be_gt_1")
    if max_timestamp_lag_minutes < 0:
        raise ValueError("max_timestamp_lag_minutes_must_be_non_negative")

    raw_rows, raw_rejects = _normalize_raw_rows(payload)
    enriched_rows = _compute_missing_zscores(raw_rows, lookback_points=lookback_points)
    spacing = horizon_hours if min_spacing_hours is None else min_spacing_hours
    samples, event_rejects = _event_samples(
        enriched_rows,
        horizon_hours=horizon_hours,
        stress_z=stress_z,
        exit_z=exit_z,
        cost_bps=cost_bps,
        min_spacing_hours=spacing,
        max_timestamp_lag_minutes=max_timestamp_lag_minutes,
        regime_by_date=regime_by_date or {},
        default_regime=default_regime,
        oos_start_date=_date_or_none(oos_start_date),
    )

    daily_returns = _daily_returns(samples) if samples else None
    parameter_cell_id = (
        f"lb{lookback_points}_h{horizon_hours:g}h_"
        f"stress{stress_z:g}_exit{exit_z:g}_cost{cost_bps:g}"
    )
    evidence: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "run_id": run_id,
        "candidate_id": candidate_id,
        "strategy_family": STRATEGY_FAMILY,
        "parameter_cell_id": parameter_cell_id,
        "selected_variant": "stress_unwind_event_window",
        "sample_unit": SAMPLE_UNIT,
        "k_trials": k_trials,
        "annualization_factor": 365,
        "samples": samples,
        "source": {
            "source_type": "offline_funding_price_jsonl",
            "source_path": source_path,
            "lookback_points": lookback_points,
            "horizon_hours": horizon_hours,
            "stress_z": stress_z,
            "exit_z": exit_z,
            "min_spacing_hours": spacing,
            "max_timestamp_lag_minutes": max_timestamp_lag_minutes,
            "round_trip_cost_bps": cost_bps,
        },
        "policy": "explicit_funding_revive_event_windows_only_no_db_or_tilt_reopen",
    }
    if daily_returns is not None:
        evidence["daily_returns"] = daily_returns

    all_rejects = raw_rejects + event_rejects
    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "run_id": run_id,
        "candidate_id": candidate_id,
        "strategy_family": STRATEGY_FAMILY,
        "parameter_cell_id": parameter_cell_id,
        "source_type": "offline_funding_price_jsonl",
        "source_path": source_path,
        "lookback_points": lookback_points,
        "horizon_hours": horizon_hours,
        "stress_z": stress_z,
        "exit_z": exit_z,
        "min_spacing_hours": spacing,
        "round_trip_cost_bps": cost_bps,
        "k_trials": k_trials,
        "raw_row_count": len(payload),
        "normalized_row_count": len(raw_rows),
        "sample_count": len(samples),
        "rejected_row_count": len(raw_rejects),
        "rejected_event_count": len(event_rejects),
        "rejected_sample_count": len(all_rejects),
        "reject_reasons": dict(sorted(Counter(row["reason"] for row in all_rejects).items())),
        "row_reject_reasons": dict(sorted(Counter(row["reason"] for row in raw_rejects).items())),
        "event_reject_reasons": dict(sorted(Counter(row["reason"] for row in event_rejects).items())),
        "accepted_regime_counts": dict(sorted(Counter(row["regime"] for row in samples).items())),
        "accepted_gross_bps_mean": _round_for_output(statistics.mean([row["gross_bps"] for row in samples])) if samples else None,
        "accepted_gross_price_bps_mean": _round_for_output(statistics.mean([row["gross_price_bps"] for row in samples])) if samples else None,
        "accepted_funding_pnl_bps_mean": _round_for_output(statistics.mean([row["funding_pnl_bps"] for row in samples])) if samples else None,
        "accepted_net_bps_mean": _round_for_output(statistics.mean([row["net_bps"] for row in samples])) if samples else None,
        "daily_return_count": len((daily_returns or {}).get("values", {})),
        "pbo_status": "not_produced_missing_candidate_grid",
        "notes": [
            "events are single-symbol funding stress unwind windows",
            "gross_bps equals sided price return plus explicit holding-window funding pnl",
            "round_trip_cost_bps is subtracted from every accepted event window",
            "daily_returns are date-level means of accepted event returns",
            "pbo is intentionally absent until explicit candidate-grid evidence exists",
        ],
        "rejected_samples": all_rejects,
    }
    return evidence, summary
