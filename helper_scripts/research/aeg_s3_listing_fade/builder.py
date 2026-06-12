"""AEG-S3 listing fade candidate evidence 純函數核心。"""

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


def _date_from_ms(value: Any) -> Optional[str]:
    ms = _int_or_none(value)
    if ms is None:
        return None
    return dt.datetime.fromtimestamp(ms / 1000.0, tz=dt.timezone.utc).date().isoformat()


def _iso_from_ms(value: Any) -> Optional[str]:
    ms = _int_or_none(value)
    if ms is None:
        return None
    return dt.datetime.fromtimestamp(ms / 1000.0, tz=dt.timezone.utc).isoformat()


def _date_or_none(value: Any) -> Optional[dt.date]:
    if value is None:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
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


def load_gate_b_run(run_dir: Path) -> dict[str, list[dict[str, Any]]]:
    run_dir = Path(run_dir)
    return {
        "capture_lag": load_jsonl(run_dir / "capture_lag.jsonl") if (run_dir / "capture_lag.jsonl").exists() else [],
        "markout": load_jsonl(run_dir / "markout.jsonl") if (run_dir / "markout.jsonl").exists() else [],
    }


def load_capture_events_jsonl(path: Path) -> dict[str, list[dict[str, Any]]]:
    rows = load_jsonl(path)
    return {
        "capture_lag": [row for row in rows if row.get("event_kind") == "capture_lag" or row.get("kind") == "capture_lag"],
        "public_trade": [row for row in rows if row.get("event_kind") == "public_trade" or row.get("kind") == "public_trade"],
    }


def _capture_by_symbol(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}

    def _capture_ts(row: dict[str, Any]) -> float:
        event_ts = _int_or_none(row.get("first_trade_event_ts_ms") or row.get("event_ts_exchange_ms"))
        return float(event_ts) if event_ts is not None else math.inf

    for row in rows:
        symbol = str(row.get("symbol") or "").strip()
        if not symbol:
            continue
        current = out.get(symbol)
        if current is None or _capture_ts(row) < _capture_ts(current):
            out[symbol] = row
    return out


def _capture_ok(row: Optional[dict[str, Any]], *, allow_slow_capture: bool) -> tuple[bool, str]:
    if row is None:
        return False, "missing_capture_lag"
    verdict = str(row.get("verdict") or row.get("capture_verdict") or "").strip()
    if verdict == "PASS_CAPTURE":
        return True, ""
    if allow_slow_capture and verdict == "SLOW_CAPTURE":
        return True, ""
    if not verdict:
        return False, "missing_capture_verdict"
    return False, f"capture_verdict_not_allowed:{verdict}"


def _samples_from_gate_b_payload(
    payload: dict[str, list[dict[str, Any]]],
    *,
    horizon_s: int,
    cost_bps: float,
    regime_by_date: dict[str, str],
    default_regime: Optional[str],
    oos_start_date: Optional[dt.date],
    allow_slow_capture: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    captures = _capture_by_symbol(payload.get("capture_lag", []))
    fills = [
        row for row in payload.get("markout", [])
        if row.get("kind") == "markout_fill" and _int_or_none(row.get("horizon_s")) == horizon_s
    ]
    fills_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in fills:
        symbol = str(row.get("symbol") or "").strip()
        if symbol:
            fills_by_symbol[symbol].append(row)

    samples: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    symbols = sorted(set(captures) | set(fills_by_symbol))
    for symbol in symbols:
        ok, reason = _capture_ok(captures.get(symbol), allow_slow_capture=allow_slow_capture)
        if not ok:
            rejects.append({"symbol": symbol, "reason": reason})
            continue
        rows = sorted(fills_by_symbol.get(symbol, []), key=lambda r: _int_or_none(r.get("trigger_event_ts_ms")) or 0)
        if not rows:
            rejects.append({"symbol": symbol, "reason": "missing_horizon_fill"})
            continue
        # One listing event should have one first-trade trigger. If duplicates exist, use earliest
        # and keep the duplicate visible through summary counts.
        row = rows[0]
        sample, reason = _sample_from_markout_fill(
            row,
            cost_bps=cost_bps,
            regime_by_date=regime_by_date,
            default_regime=default_regime,
            oos_start_date=oos_start_date,
        )
        if sample is None:
            rejects.append({"symbol": symbol, "reason": reason})
            continue
        samples.append(sample)
    return samples, rejects


def _samples_from_capture_events_payload(
    payload: dict[str, list[dict[str, Any]]],
    *,
    horizon_s: int,
    cost_bps: float,
    regime_by_date: dict[str, str],
    default_regime: Optional[str],
    oos_start_date: Optional[dt.date],
    allow_slow_capture: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    captures = _capture_by_symbol(payload.get("capture_lag", []))
    trades_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in payload.get("public_trade", []):
        symbol = str(row.get("symbol") or "").strip()
        if symbol:
            trades_by_symbol[symbol].append(row)

    samples: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    for symbol in sorted(set(captures) | set(trades_by_symbol)):
        ok, reason = _capture_ok(captures.get(symbol), allow_slow_capture=allow_slow_capture)
        if not ok:
            rejects.append({"symbol": symbol, "reason": reason})
            continue
        trades = sorted(trades_by_symbol.get(symbol, []), key=lambda r: _int_or_none(r.get("event_ts_exchange_ms")) or 0)
        if not trades:
            rejects.append({"symbol": symbol, "reason": "missing_public_trades"})
            continue
        first = trades[0]
        trigger_ts = _int_or_none(first.get("event_ts_exchange_ms"))
        entry = _float_or_none(first.get("price"))
        if trigger_ts is None or entry is None or entry <= 0:
            rejects.append({"symbol": symbol, "reason": "invalid_first_trade"})
            continue
        target_ts = trigger_ts + horizon_s * 1000
        exit_trade = next((row for row in trades if (_int_or_none(row.get("event_ts_exchange_ms")) or -1) >= target_ts), None)
        if exit_trade is None:
            rejects.append({"symbol": symbol, "reason": "missing_horizon_trade"})
            continue
        exit_price = _float_or_none(exit_trade.get("price"))
        if exit_price is None:
            rejects.append({"symbol": symbol, "reason": "invalid_horizon_trade"})
            continue
        markout_bps = (exit_price - entry) / entry * 10_000.0
        fill = {
            "symbol": symbol,
            "trigger_event_ts_ms": trigger_ts,
            "filled_event_ts_ms": _int_or_none(exit_trade.get("event_ts_exchange_ms")),
            "mid_at_trigger": entry,
            "mid_at_horizon": exit_price,
            "markout_bps": markout_bps,
        }
        sample, reason = _sample_from_markout_fill(
            fill,
            cost_bps=cost_bps,
            regime_by_date=regime_by_date,
            default_regime=default_regime,
            oos_start_date=oos_start_date,
        )
        if sample is None:
            rejects.append({"symbol": symbol, "reason": reason})
            continue
        samples.append(sample)
    return samples, rejects


def _sample_from_markout_fill(
    row: dict[str, Any],
    *,
    cost_bps: float,
    regime_by_date: dict[str, str],
    default_regime: Optional[str],
    oos_start_date: Optional[dt.date],
) -> tuple[Optional[dict[str, Any]], str]:
    symbol = str(row.get("symbol") or "").strip()
    trigger_ts = _int_or_none(row.get("trigger_event_ts_ms"))
    sample_date = _date_from_ms(trigger_ts)
    sample_ts = _iso_from_ms(trigger_ts)
    markout = _float_or_none(row.get("markout_bps"))
    entry = _float_or_none(row.get("mid_at_trigger"))
    exit_price = _float_or_none(row.get("mid_at_horizon"))
    if not symbol:
        return None, "missing_symbol"
    if sample_date is None or sample_ts is None:
        return None, "missing_trigger_ts"
    if markout is None:
        if entry is None or exit_price is None or entry <= 0:
            return None, "missing_markout_bps"
        markout = (exit_price - entry) / entry * 10_000.0
    regime = regime_by_date.get(sample_date) or default_regime
    if not regime:
        return None, "missing_regime"
    gross_bps = -markout
    net_bps = gross_bps - cost_bps
    sample_day = _date_or_none(sample_date)
    return {
        "sample_id": f"{symbol}:{trigger_ts}",
        "sample_ts_utc": sample_ts,
        "regime": regime,
        "independence_bucket": f"{sample_date}:{symbol}",
        "gross_bps": round(gross_bps, 8),
        "cost_bps": round(cost_bps, 8),
        "net_bps": round(net_bps, 8),
        "is_oos": (sample_day >= oos_start_date) if sample_day is not None and oos_start_date is not None else None,
        "source_symbol": symbol,
        "entry_price": entry,
        "exit_price": exit_price,
    }, ""


def _daily_returns(samples: list[dict[str, Any]]) -> dict[str, Any]:
    by_date: dict[str, float] = defaultdict(float)
    regime_by_date: dict[str, set[str]] = defaultdict(set)
    for row in samples:
        d = str(row["sample_ts_utc"])[:10]
        by_date[d] += float(row["net_bps"]) / 10_000.0
        regime_by_date[d].add(str(row["regime"]))
    return {
        "unit": "fraction",
        "policy": "sum_explicit_listing_event_net_bps_by_sample_date",
        "regime_by_date": {
            d: next(iter(regimes))
            for d, regimes in sorted(regime_by_date.items())
            if len(regimes) == 1
        },
        "values": dict(sorted(by_date.items())),
    }


def _parameter_cell_id(*, horizon_s: int, cost_bps: float) -> str:
    return f"h{horizon_s}s_cost{cost_bps:g}"


def default_pbo_grid(*, cost_bps: float) -> list[dict[str, Any]]:
    """Small listing-fade parameter family used only when explicitly requested."""
    costs = []
    for value in (cost_bps, cost_bps + 1.0, cost_bps + 3.0, max(0.0, cost_bps - 1.0)):
        if value not in costs:
            costs.append(value)
    cells: list[dict[str, Any]] = []
    for horizon_s in (30, 60, 300):
        for cell_cost_bps in costs:
            cells.append({
                "horizon_s": horizon_s,
                "cost_bps": cell_cost_bps,
            })
    return cells


def _cell_int(cell: dict[str, Any], key: str) -> int:
    value = cell.get(key)
    if value is None:
        raise ValueError(f"pbo_grid_missing_{key}")
    return int(value)


def _cell_float(cell: dict[str, Any], key: str) -> float:
    value = cell.get(key)
    if value is None:
        raise ValueError(f"pbo_grid_missing_{key}")
    return float(value)


def _samples_for_parameters(
    payload: dict[str, list[dict[str, Any]]],
    *,
    source_type: str,
    horizon_s: int,
    cost_bps: float,
    regime_by_date: dict[str, str],
    default_regime: Optional[str],
    oos_start_date: Optional[dt.date],
    allow_slow_capture: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if horizon_s <= 0:
        raise ValueError("horizon_s_must_be_positive")
    if cost_bps < 0:
        raise ValueError("cost_bps_must_be_non_negative")
    if source_type == "gate_b_run":
        return _samples_from_gate_b_payload(
            payload,
            horizon_s=horizon_s,
            cost_bps=cost_bps,
            regime_by_date=regime_by_date,
            default_regime=default_regime,
            oos_start_date=oos_start_date,
            allow_slow_capture=allow_slow_capture,
        )
    if source_type == "capture_events_jsonl":
        return _samples_from_capture_events_payload(
            payload,
            horizon_s=horizon_s,
            cost_bps=cost_bps,
            regime_by_date=regime_by_date,
            default_regime=default_regime,
            oos_start_date=oos_start_date,
            allow_slow_capture=allow_slow_capture,
        )
    raise ValueError(f"unsupported_source_type:{source_type}")


def _pbo_grid_candidates(
    payload: dict[str, list[dict[str, Any]]],
    *,
    source_type: str,
    pbo_grid: list[dict[str, Any]],
    regime_by_date: dict[str, str],
    default_regime: Optional[str],
    oos_start_date: Optional[dt.date],
    allow_slow_capture: bool,
) -> tuple[dict[str, dict[str, float]], list[dict[str, Any]]]:
    candidates: dict[str, dict[str, float]] = {}
    grid_summary: list[dict[str, Any]] = []
    for idx, cell in enumerate(pbo_grid):
        horizon_s = _cell_int(cell, "horizon_s")
        cost_bps = _cell_float(cell, "cost_bps")
        samples, rejects = _samples_for_parameters(
            payload,
            source_type=source_type,
            horizon_s=horizon_s,
            cost_bps=cost_bps,
            regime_by_date=regime_by_date,
            default_regime=default_regime,
            oos_start_date=oos_start_date,
            allow_slow_capture=allow_slow_capture,
        )
        daily_returns = _daily_returns(samples) if samples else None
        parameter_cell_id = str(cell.get("parameter_cell_id") or _parameter_cell_id(
            horizon_s=horizon_s,
            cost_bps=cost_bps,
        ))
        if parameter_cell_id in candidates:
            parameter_cell_id = f"{parameter_cell_id}_idx{idx}"
        daily_values = (daily_returns or {}).get("values", {})
        if daily_values:
            candidates[parameter_cell_id] = {
                str(day): float(value)
                for day, value in daily_values.items()
                if _float_or_none(value) is not None
            }
        grid_summary.append({
            "parameter_cell_id": parameter_cell_id,
            "horizon_s": horizon_s,
            "round_trip_cost_bps": cost_bps,
            "sample_count": len(samples),
            "rejected_sample_count": len(rejects),
            "reject_reasons": dict(sorted(Counter(row["reason"] for row in rejects).items())),
            "daily_return_count": len(daily_values),
            "included_in_pbo": bool(daily_values),
        })
    return candidates, grid_summary


def build_listing_fade_evidence(
    payload: dict[str, list[dict[str, Any]]],
    *,
    source_type: str,
    source_path: str,
    run_id: str,
    horizon_s: int,
    cost_bps: float,
    k_trials: int,
    candidate_id: str = "listing_fade",
    regime_by_date: Optional[dict[str, str]] = None,
    default_regime: Optional[str] = None,
    oos_start_date: Optional[str] = None,
    allow_slow_capture: bool = False,
    pbo_grid: Optional[list[dict[str, Any]]] = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if horizon_s <= 0:
        raise ValueError("horizon_s_must_be_positive")
    if cost_bps < 0:
        raise ValueError("cost_bps_must_be_non_negative")
    if k_trials <= 1:
        raise ValueError("k_trials_must_be_gt_1")
    regimes = regime_by_date or {}
    oos_start = _date_or_none(oos_start_date)
    samples, rejects = _samples_for_parameters(
        payload,
        source_type=source_type,
        horizon_s=horizon_s,
        cost_bps=cost_bps,
        regime_by_date=regimes,
        default_regime=default_regime,
        oos_start_date=oos_start,
        allow_slow_capture=allow_slow_capture,
    )

    daily_returns = _daily_returns(samples) if samples else None
    parameter_cell_id = _parameter_cell_id(horizon_s=horizon_s, cost_bps=cost_bps)
    pbo_candidates: dict[str, dict[str, float]] = {}
    pbo_grid_summary: list[dict[str, Any]] = []
    if pbo_grid:
        pbo_candidates, pbo_grid_summary = _pbo_grid_candidates(
            payload,
            source_type=source_type,
            pbo_grid=pbo_grid,
            regime_by_date=regimes,
            default_regime=default_regime,
            oos_start_date=oos_start,
            allow_slow_capture=allow_slow_capture,
        )
    evidence: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "run_id": run_id,
        "candidate_id": candidate_id,
        "strategy_family": STRATEGY_FAMILY,
        "parameter_cell_id": parameter_cell_id,
        "selected_variant": f"short_first_trade_exit_{horizon_s}s",
        "sample_unit": SAMPLE_UNIT,
        "k_trials": k_trials,
        "annualization_factor": 365,
        "samples": samples,
        "source": {
            "source_type": source_type,
            "source_path": source_path,
            "horizon_s": horizon_s,
            "round_trip_cost_bps": cost_bps,
            "allow_slow_capture": allow_slow_capture,
        },
        "policy": "explicit_listing_event_windows_only_no_connection_only_samples",
    }
    if daily_returns is not None:
        evidence["daily_returns"] = daily_returns
    if pbo_candidates:
        evidence["pbo_seed"] = 20260611
        evidence["pbo_candidates"] = pbo_candidates
        evidence["pbo_candidate_grid"] = pbo_grid_summary
    included_pbo_count = len(pbo_candidates)
    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "run_id": run_id,
        "candidate_id": candidate_id,
        "strategy_family": STRATEGY_FAMILY,
        "parameter_cell_id": parameter_cell_id,
        "source_type": source_type,
        "source_path": source_path,
        "horizon_s": horizon_s,
        "round_trip_cost_bps": cost_bps,
        "k_trials": k_trials,
        "sample_count": len(samples),
        "rejected_sample_count": len(rejects),
        "reject_reasons": dict(sorted(Counter(row["reason"] for row in rejects).items())),
        "accepted_regime_counts": dict(sorted(Counter(row["regime"] for row in samples).items())),
        "accepted_net_bps_mean": round(statistics.mean([row["net_bps"] for row in samples]), 8) if samples else None,
        "daily_return_count": len((daily_returns or {}).get("values", {})),
        "pbo_grid_cell_count": len(pbo_grid_summary),
        "pbo_grid_included_candidate_count": included_pbo_count,
        "pbo_grid_daily_return_counts": {
            row["parameter_cell_id"]: row["daily_return_count"]
            for row in pbo_grid_summary
        },
        "pbo_status": (
            "produced_candidate_grid"
            if included_pbo_count >= 10
            else ("insufficient_candidate_grid" if pbo_grid else "not_produced_missing_candidate_grid")
        ),
        "notes": [
            "short fade gross_bps is negative markout_bps",
            "daily_returns are aggregated from explicit accepted samples only",
            "pbo_candidates are emitted only when an explicit candidate-grid request is provided",
        ],
        "rejected_samples": rejects,
    }
    if pbo_grid_summary:
        summary["pbo_candidate_grid"] = pbo_grid_summary
    return evidence, summary
