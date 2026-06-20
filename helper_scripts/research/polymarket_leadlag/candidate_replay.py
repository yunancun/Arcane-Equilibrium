#!/usr/bin/env python3
"""Polymarket lead-lag IC candidate -> explicit paper-PnL evidence.

This module turns an IC candidate cell into a deterministic replay rule:

  side_t = sign(IC) * sign(delta_prob_yes_t)
  gross_bps_t = side_t * forward_return_bps_t
  net_bps_t = gross_bps_t - explicit_round_trip_cost_bps

Boundary:
  - artifact/evidence only;
  - consumes already joined Polymarket/Bybit public research rows;
  - no DB, no Bybit private/signed/trading call, no strategy/risk/order mutation;
  - execution realism remains explicitly unmeasured.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import socket
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Optional

try:
    from . import (
        CANDIDATE_REPLAY_SCHEMA_VERSION,
        CANDIDATE_REPLAY_SUMMARY_SCHEMA_VERSION,
        RUNNER_VERSION,
    )
except ImportError:  # pragma: no cover
    _here = Path(__file__).resolve()
    _research = _here.parents[1]
    if str(_research) not in sys.path:
        sys.path.insert(0, str(_research))
    from polymarket_leadlag import (  # type: ignore
        CANDIDATE_REPLAY_SCHEMA_VERSION,
        CANDIDATE_REPLAY_SUMMARY_SCHEMA_VERSION,
        RUNNER_VERSION,
    )


STRATEGY_FAMILY = "polymarket_leadlag_directional_replay"
SAMPLE_UNIT = "polymarket_nonoverlap_forward_window"
DEFAULT_ROUND_TRIP_COST_BPS = 4.0
DEFAULT_COST_SENSITIVITY_BPS = (0.0, 4.0, 8.0, 12.0)
DEFAULT_TRAIN_FRACTION = 0.5
DEFAULT_THRESHOLD_QUANTILES = (0.0, 0.25, 0.5, 0.75)
PBO_SEED = 20260620


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _data_root() -> Path:
    base = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw").strip() or "/tmp/openclaw"
    return Path(base)


def _ms_to_iso(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000.0, tz=dt.timezone.utc).isoformat()


def _parse_dt(value: Any) -> Optional[dt.datetime]:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


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


def _mean(values: Iterable[float]) -> Optional[float]:
    clean = [float(v) for v in values if math.isfinite(float(v))]
    return statistics.mean(clean) if clean else None


def _round_or_none(value: Optional[float], digits: int = 8) -> Optional[float]:
    if value is None or not math.isfinite(value):
        return None
    return round(value, digits)


def _t_stat(values: Iterable[float]) -> Optional[float]:
    clean = [float(v) for v in values if math.isfinite(float(v))]
    if len(clean) < 2:
        return None
    sd = statistics.stdev(clean)
    if sd <= 0:
        return None
    return statistics.mean(clean) / (sd / math.sqrt(len(clean)))


def _horizon_ms(horizon_minutes: int) -> int:
    return int(max(1, horizon_minutes) * 60 * 1000)


def _schedule_jitter_tolerance_ms(horizon_minutes: int) -> int:
    return max(0, min(5_000, _horizon_ms(horizon_minutes) - 1))


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


def _median_positive_gap_ms(timestamps_ms: Iterable[int]) -> Optional[int]:
    ordered = sorted({int(ts) for ts in timestamps_ms})
    gaps = [b - a for a, b in zip(ordered, ordered[1:]) if b > a]
    if not gaps:
        return None
    gaps.sort()
    mid = len(gaps) // 2
    if len(gaps) % 2:
        return int(gaps[mid])
    return int((gaps[mid - 1] + gaps[mid]) / 2)


def _annualization_factor(sample_timestamps_ms: Iterable[int]) -> Optional[float]:
    gap_ms = _median_positive_gap_ms(sample_timestamps_ms)
    if gap_ms is None or gap_ms <= 0:
        return None
    year_ms = 365.25 * 24 * 60 * 60 * 1000
    return year_ms / gap_ms


def _quantile(values: list[float], q: float) -> Optional[float]:
    clean = sorted(v for v in values if math.isfinite(v))
    if not clean:
        return None
    q = min(1.0, max(0.0, float(q)))
    idx = int(math.floor(q * (len(clean) - 1)))
    return float(clean[idx])


def candidate_key(candidate: dict[str, Any]) -> Optional[str]:
    bucket = str(candidate.get("bucket") or "").strip()
    symbol = str(candidate.get("symbol") or "").strip()
    horizon = _int_or_none(candidate.get("horizon_minutes"))
    if not (bucket and symbol and horizon):
        return None
    return f"polymarket_leadlag_ic|{bucket}|{symbol}|{horizon}m"


def _candidate_id(candidate: dict[str, Any]) -> str:
    bucket = str(candidate.get("bucket") or "unknown_bucket").strip() or "unknown_bucket"
    symbol = str(candidate.get("symbol") or "unknown_symbol").strip() or "unknown_symbol"
    horizon = _int_or_none(candidate.get("horizon_minutes")) or 0
    return f"polymarket_leadlag_{bucket}_{symbol}_{horizon}m"


def _parameter_cell_id(
    candidate: dict[str, Any],
    *,
    cost_bps: float,
    threshold_quantile: float,
) -> str:
    bucket = str(candidate.get("bucket") or "unknown_bucket").strip() or "unknown_bucket"
    symbol = str(candidate.get("symbol") or "unknown_symbol").strip() or "unknown_symbol"
    horizon = _int_or_none(candidate.get("horizon_minutes")) or 0
    return (
        f"{bucket}|{symbol}|{horizon}m|rule=ic_sign_delta|"
        f"threshold_q={threshold_quantile:g}|cost_bps={cost_bps:g}"
    )


def _candidate_joined_rows(
    joined_rows: Iterable[dict[str, Any]],
    candidate: dict[str, Any],
) -> list[dict[str, Any]]:
    bucket = str(candidate.get("bucket") or "")
    symbol = str(candidate.get("symbol") or "")
    horizon = _int_or_none(candidate.get("horizon_minutes"))
    rows = []
    for row in joined_rows:
        if str(row.get("bucket") or "") != bucket:
            continue
        if str(row.get("symbol") or "") != symbol:
            continue
        if _int_or_none(row.get("horizon_minutes")) != horizon:
            continue
        if _float_or_none(row.get("mean_delta_prob_yes")) is None:
            continue
        if _float_or_none(row.get("forward_return_bps")) is None:
            continue
        if _int_or_none(row.get("snapshot_ts_ms")) is None:
            continue
        rows.append(row)
    return sorted(rows, key=lambda r: int(r["snapshot_ts_ms"]))


def _nonoverlap_rows(rows: list[dict[str, Any]], *, horizon_minutes: int) -> list[dict[str, Any]]:
    selected_ts = set(_selected_nonoverlap_timestamps(
        [int(row["snapshot_ts_ms"]) for row in rows],
        horizon_minutes,
    ))
    return [row for row in rows if int(row["snapshot_ts_ms"]) in selected_ts]


def _train_threshold(rows: list[dict[str, Any]], *, train_fraction: float, quantile: float) -> float:
    if quantile <= 0:
        return 0.0
    train_count = max(1, int(math.floor(len(rows) * min(0.95, max(0.05, train_fraction)))))
    train_abs = [
        abs(float(row["mean_delta_prob_yes"]))
        for row in rows[:train_count]
        if _float_or_none(row.get("mean_delta_prob_yes")) is not None
    ]
    return _quantile(train_abs, quantile) or 0.0


def _build_samples(
    rows: list[dict[str, Any]],
    *,
    candidate: dict[str, Any],
    cost_bps: float,
    threshold_quantile: float,
    train_fraction: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ic = _float_or_none(candidate.get("ic_pearson"))
    if ic is None or ic == 0:
        return [], {"reject_reason": "candidate_ic_missing_or_zero"}
    threshold = _train_threshold(
        rows,
        train_fraction=train_fraction,
        quantile=threshold_quantile,
    )
    ic_sign = 1.0 if ic > 0 else -1.0
    raw_samples: list[dict[str, Any]] = []
    rejects: Counter[str] = Counter()
    bucket = str(candidate.get("bucket") or "unknown")
    symbol = str(candidate.get("symbol") or "unknown")
    horizon = _int_or_none(candidate.get("horizon_minutes")) or 0
    for row in rows:
        ts_ms = int(row["snapshot_ts_ms"])
        delta = _float_or_none(row.get("mean_delta_prob_yes"))
        fwd = _float_or_none(row.get("forward_return_bps"))
        if delta is None or fwd is None:
            rejects["missing_signal_or_return"] += 1
            continue
        if abs(delta) <= threshold:
            rejects["below_threshold"] += 1
            continue
        signal_sign = 1.0 if delta > 0 else -1.0
        side = ic_sign * signal_sign
        gross = side * fwd
        net = gross - cost_bps
        ts_utc = row.get("snapshot_ts_utc") or _ms_to_iso(ts_ms)
        raw_samples.append({
            "sample_id": f"polymarket:{bucket}:{symbol}:{horizon}m:{ts_ms}",
            "sample_ts_utc": ts_utc,
            "regime": "unsegmented",
            "independence_bucket": f"{symbol}:{horizon}m:{ts_ms}",
            "gross_bps": round(gross, 8),
            "cost_bps": round(cost_bps, 8),
            "net_bps": round(net, 8),
            "side": "long" if side > 0 else "short",
            "mean_delta_prob_yes": round(delta, 12),
            "forward_return_bps": round(fwd, 8),
            "threshold_abs_delta_prob_yes": round(threshold, 12),
            "entry_price_ts_utc": row.get("entry_price_ts_utc"),
            "exit_price_ts_utc": row.get("exit_price_ts_utc"),
        })
    oos_start = int(math.floor(len(raw_samples) * min(0.95, max(0.05, train_fraction))))
    oos_start = max(1, min(oos_start, len(raw_samples))) if raw_samples else 0
    samples: list[dict[str, Any]] = []
    for idx, sample in enumerate(raw_samples):
        samples.append({**sample, "is_oos": idx >= oos_start})
    meta = {
        "threshold_abs_delta_prob_yes": threshold,
        "threshold_quantile": threshold_quantile,
        "ic_sign": "positive" if ic_sign > 0 else "negative",
        "accepted_sample_count": len(samples),
        "train_sample_count": min(oos_start, len(samples)),
        "holdout_sample_count": max(0, len(samples) - oos_start),
        "reject_reasons": dict(sorted(rejects.items())),
    }
    return samples, meta


def _daily_returns(samples: list[dict[str, Any]]) -> dict[str, Any]:
    by_date: dict[str, float] = defaultdict(float)
    regime_by_date: dict[str, set[str]] = defaultdict(set)
    for row in samples:
        parsed = _parse_dt(row.get("sample_ts_utc"))
        if parsed is None:
            continue
        day = parsed.date().isoformat()
        net = _float_or_none(row.get("net_bps"))
        if net is None:
            continue
        by_date[day] += net / 10_000.0
        regime = str(row.get("regime") or "").strip()
        if regime:
            regime_by_date[day].add(regime)
    return {
        "unit": "fraction",
        "policy": "sum_explicit_polymarket_replay_net_bps_by_sample_date",
        "regime_by_date": {
            day: next(iter(regimes))
            for day, regimes in sorted(regime_by_date.items())
            if len(regimes) == 1
        },
        "values": dict(sorted(by_date.items())),
    }


def _summarize_samples(samples: list[dict[str, Any]], *, cost_bps: float) -> dict[str, Any]:
    gross = [_float_or_none(row.get("gross_bps")) for row in samples]
    net = [_float_or_none(row.get("net_bps")) for row in samples]
    clean_gross = [float(x) for x in gross if x is not None]
    clean_net = [float(x) for x in net if x is not None]
    holdout = [row for row in samples if row.get("is_oos") is True]
    holdout_net = [
        float(x)
        for x in (_float_or_none(row.get("net_bps")) for row in holdout)
        if x is not None
    ]
    holdout_gross = [
        float(x)
        for x in (_float_or_none(row.get("gross_bps")) for row in holdout)
        if x is not None
    ]
    sample_dates = {
        parsed.date().isoformat()
        for parsed in (_parse_dt(row.get("sample_ts_utc")) for row in samples)
        if parsed is not None
    }
    gross_mean = _mean(clean_gross)
    net_mean = _mean(clean_net)
    holdout_net_mean = _mean(holdout_net)
    if not samples:
        cost_wall_status = "NO_REPLAY_SAMPLES"
    elif gross_mean is not None and gross_mean <= cost_bps:
        cost_wall_status = "GROSS_MEAN_BELOW_COST"
    elif net_mean is not None and net_mean <= 0:
        cost_wall_status = "NET_MEAN_NON_POSITIVE"
    elif holdout_net_mean is not None and holdout_net_mean <= 0:
        cost_wall_status = "HOLDOUT_NET_NON_POSITIVE"
    else:
        cost_wall_status = "PAPER_REPLAY_NET_POSITIVE_EXECUTION_UNMEASURED"
    return {
        "sample_count": len(samples),
        "n_days": len(sample_dates),
        "cost_bps": round(cost_bps, 8),
        "gross_bps_mean": _round_or_none(gross_mean),
        "net_bps_mean": _round_or_none(net_mean),
        "net_bps_t_stat_naive": _round_or_none(_t_stat(clean_net)),
        "positive_net_sample_count": sum(1 for value in clean_net if value > 0),
        "positive_net_sample_rate": (
            round(sum(1 for value in clean_net if value > 0) / len(clean_net), 8)
            if clean_net else None
        ),
        "holdout_sample_count": len(holdout),
        "holdout_gross_bps_mean": _round_or_none(_mean(holdout_gross)),
        "holdout_net_bps_mean": _round_or_none(holdout_net_mean),
        "holdout_net_bps_t_stat_naive": _round_or_none(_t_stat(holdout_net)),
        "cost_wall_status": cost_wall_status,
    }


def _pbo_candidates(
    rows: list[dict[str, Any]],
    *,
    candidate: dict[str, Any],
    train_fraction: float,
    cost_sensitivity_bps: tuple[float, ...],
    threshold_quantiles: tuple[float, ...],
) -> tuple[dict[str, dict[str, float]], list[dict[str, Any]]]:
    candidates: dict[str, dict[str, float]] = {}
    grid_summary: list[dict[str, Any]] = []
    for q in threshold_quantiles:
        for cost in cost_sensitivity_bps:
            samples, meta = _build_samples(
                rows,
                candidate=candidate,
                cost_bps=cost,
                threshold_quantile=q,
                train_fraction=train_fraction,
            )
            daily = _daily_returns(samples)
            values = daily.get("values") or {}
            parameter_cell_id = _parameter_cell_id(
                candidate,
                cost_bps=cost,
                threshold_quantile=q,
            )
            if values:
                candidates[parameter_cell_id] = {
                    str(day): float(value)
                    for day, value in values.items()
                    if _float_or_none(value) is not None
                }
            summary = _summarize_samples(samples, cost_bps=cost)
            grid_summary.append({
                "parameter_cell_id": parameter_cell_id,
                "threshold_quantile": q,
                "threshold_abs_delta_prob_yes": meta.get("threshold_abs_delta_prob_yes"),
                "round_trip_cost_bps": cost,
                "sample_count": len(samples),
                "daily_return_count": len(values),
                "net_bps_mean": summary.get("net_bps_mean"),
                "holdout_net_bps_mean": summary.get("holdout_net_bps_mean"),
                "included_in_pbo": bool(values),
            })
    return candidates, grid_summary


def build_candidate_replay(
    *,
    joined_rows: list[dict[str, Any]],
    candidate: dict[str, Any],
    ic_result_count: int,
    price_source: str,
    round_trip_cost_bps: float = DEFAULT_ROUND_TRIP_COST_BPS,
    train_fraction: float = DEFAULT_TRAIN_FRACTION,
    cost_sensitivity_bps: tuple[float, ...] = DEFAULT_COST_SENSITIVITY_BPS,
    threshold_quantiles: tuple[float, ...] = DEFAULT_THRESHOLD_QUANTILES,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build AEG candidate-evidence payload and compact replay summary."""
    horizon = _int_or_none(candidate.get("horizon_minutes")) or 0
    rows = _candidate_joined_rows(joined_rows, candidate)
    nonoverlap = _nonoverlap_rows(rows, horizon_minutes=horizon) if horizon else []
    samples, meta = _build_samples(
        nonoverlap,
        candidate=candidate,
        cost_bps=float(round_trip_cost_bps),
        threshold_quantile=0.0,
        train_fraction=train_fraction,
    )
    daily_returns = _daily_returns(samples)
    sample_ts = [
        int(row["snapshot_ts_ms"])
        for row in nonoverlap
        if any(sample["sample_id"].endswith(f":{int(row['snapshot_ts_ms'])}") for sample in samples)
    ]
    annualization = _annualization_factor(sample_ts)
    pbo, pbo_grid = _pbo_candidates(
        nonoverlap,
        candidate=candidate,
        train_fraction=train_fraction,
        cost_sensitivity_bps=cost_sensitivity_bps,
        threshold_quantiles=threshold_quantiles,
    )
    candidate_id = _candidate_id(candidate)
    parameter_cell = _parameter_cell_id(
        candidate,
        cost_bps=float(round_trip_cost_bps),
        threshold_quantile=0.0,
    )
    sensitivity = []
    for cost in cost_sensitivity_bps:
        cost_samples, _cost_meta = _build_samples(
            nonoverlap,
            candidate=candidate,
            cost_bps=float(cost),
            threshold_quantile=0.0,
            train_fraction=train_fraction,
        )
        sensitivity.append(_summarize_samples(cost_samples, cost_bps=float(cost)))
    summary = {
        "schema_version": CANDIDATE_REPLAY_SUMMARY_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "candidate_key": candidate_key(candidate),
        "candidate_id": candidate_id,
        "strategy_family": STRATEGY_FAMILY,
        "parameter_cell_id": parameter_cell,
        "selected_variant": "ic_sign_delta",
        "source_report_type": "polymarket_leadlag_ic",
        "bucket": candidate.get("bucket"),
        "symbol": candidate.get("symbol"),
        "horizon_minutes": horizon,
        "ic_pearson": candidate.get("ic_pearson"),
        "t_stat_hac": candidate.get("t_stat_hac"),
        "bh_q_value_hac_approx": candidate.get("bh_q_value_hac_approx"),
        "partial_ic_controlling_trailing_return": candidate.get(
            "partial_ic_controlling_trailing_return"
        ),
        "price_feedback_warning": candidate.get("price_feedback_warning"),
        "price_feedback_partial_collapse_warning": candidate.get(
            "price_feedback_partial_collapse_warning"
        ),
        "joined_row_count": len(rows),
        "nonoverlap_row_count": len(nonoverlap),
        "train_fraction": train_fraction,
        "execution_realism_status": "UNMEASURED",
        "execution_realism_note": "paper replay only; maker/taker fill and queue realism are not measured",
        "round_trip_cost_bps": round(float(round_trip_cost_bps), 8),
        "cost_assumption": "explicit_diagnostic_round_trip_cost_not_execution_realism",
        "sample_unit": SAMPLE_UNIT,
        "k_trials": int(ic_result_count),
        "sample_reject_reasons": meta.get("reject_reasons") or {},
        "pbo_grid_cell_count": len(pbo_grid),
        "pbo_grid_included_candidate_count": len(pbo),
        "cost_sensitivity": sensitivity,
        **_summarize_samples(samples, cost_bps=float(round_trip_cost_bps)),
        "policy": "explicit_joined_forward_returns_only_no_ic_to_pnl_substitution",
        "selection_bias_warning": (
            "IC candidate was selected before this replay; chronological holdout is diagnostic "
            "and not sealed OOS promotion evidence"
        ),
    }
    evidence: dict[str, Any] = {
        "schema_version": CANDIDATE_REPLAY_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "candidate_id": candidate_id,
        "candidate_key": candidate_key(candidate),
        "strategy_family": STRATEGY_FAMILY,
        "parameter_cell_id": parameter_cell,
        "selected_variant": "ic_sign_delta",
        "sample_unit": SAMPLE_UNIT,
        "k_trials": int(ic_result_count),
        "samples": samples,
        "daily_returns": daily_returns,
        "source": {
            "source_type": "polymarket_leadlag_joined_forward_returns",
            "candidate_key": candidate_key(candidate),
            "price_source": price_source,
            "round_trip_cost_bps": round(float(round_trip_cost_bps), 8),
            "cost_assumption": "explicit_diagnostic_round_trip_cost_not_execution_realism",
            "threshold_quantile": 0.0,
            "train_fraction": train_fraction,
            "execution_realism_status": "UNMEASURED",
        },
        "policy": "paper_replay_only_no_execution_realism_no_signal_no_order_authority",
    }
    if annualization is not None:
        evidence["annualization_factor"] = annualization
    if pbo:
        evidence["pbo_seed"] = PBO_SEED
        evidence["pbo_candidates"] = pbo
        evidence["pbo_candidate_grid"] = pbo_grid
    return evidence, summary


def build_replay_scorecard(
    *,
    joined_rows: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    ic_results: list[dict[str, Any]],
    price_source: str,
    round_trip_cost_bps: float = DEFAULT_ROUND_TRIP_COST_BPS,
    train_fraction: float = DEFAULT_TRAIN_FRACTION,
    cost_sensitivity_bps: tuple[float, ...] = DEFAULT_COST_SENSITIVITY_BPS,
) -> dict[str, Any]:
    if not candidates:
        return {
            "schema_version": CANDIDATE_REPLAY_SUMMARY_SCHEMA_VERSION,
            "runner_version": RUNNER_VERSION,
            "status": "NO_IC_CANDIDATE",
            "reason": "lead_lag_report_has_no_candidate_cells",
            "round_trip_cost_bps": round(float(round_trip_cost_bps), 8),
            "candidate_count": 0,
        }
    replays = []
    for candidate in candidates:
        evidence, summary = build_candidate_replay(
            joined_rows=joined_rows,
            candidate=candidate,
            ic_result_count=len(ic_results),
            price_source=price_source,
            round_trip_cost_bps=round_trip_cost_bps,
            train_fraction=train_fraction,
            cost_sensitivity_bps=cost_sensitivity_bps,
        )
        replays.append({"evidence": evidence, "summary": summary})
    selected = replays[0]
    selected_summary = selected["summary"]
    status = "PAPER_REPLAY_BUILT" if selected_summary.get("sample_count") else "NO_REPLAY_SAMPLES"
    return {
        "schema_version": CANDIDATE_REPLAY_SUMMARY_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "status": status,
        "reason": (
            "candidate replay evidence built from explicit joined forward returns"
            if status == "PAPER_REPLAY_BUILT"
            else "candidate cell has no replayable non-overlap samples"
        ),
        "selected_candidate_key": selected_summary.get("candidate_key"),
        "selected_candidate_id": selected_summary.get("candidate_id"),
        "selected_parameter_cell_id": selected_summary.get("parameter_cell_id"),
        "round_trip_cost_bps": round(float(round_trip_cost_bps), 8),
        "candidate_count": len(candidates),
        "selected_summary": selected_summary,
        "selected_evidence": selected["evidence"],
        "candidate_summaries": [row["summary"] for row in replays],
        "promotion_boundary": "paper_pnl_replay_not_execution_or_promotion_proof",
    }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_provenance(repo_root: Path) -> dict[str, Any]:
    def _run(args: list[str]) -> str:
        try:
            return subprocess.run(
                args,
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=10,
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


def write_replay_evidence(
    *,
    scorecard: dict[str, Any],
    out_dir: Path,
    repo_root: Optional[Path] = None,
    runtime_host: Optional[str] = None,
) -> dict[str, str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    evidence = scorecard.get("selected_evidence")
    summary = scorecard.get("selected_summary")
    if not isinstance(evidence, dict) or not isinstance(summary, dict):
        raise ValueError("scorecard_missing_selected_evidence_or_summary")
    evidence_path = out_dir / "polymarket_leadlag_candidate_evidence.json"
    summary_path = out_dir / "polymarket_leadlag_candidate_replay_summary.json"
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    prov = _git_provenance(repo_root or _repo_root())
    artifacts = [
        {
            "name": evidence_path.name,
            "path": str(evidence_path),
            "sha256": _sha256(evidence_path),
            "schema_version": evidence.get("schema_version"),
        },
        {
            "name": summary_path.name,
            "path": str(summary_path),
            "sha256": _sha256(summary_path),
            "schema_version": summary.get("schema_version"),
        },
    ]
    manifest = {
        "schema_version": "polymarket.leadlag_candidate_replay_manifest.v0.1",
        "program": "polymarket-leadlag-candidate-replay",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "runtime_host": runtime_host or socket.gethostname(),
        "runner_version": RUNNER_VERSION,
        "candidate_id": evidence.get("candidate_id"),
        "candidate_key": evidence.get("candidate_key"),
        "strategy_family": evidence.get("strategy_family"),
        "parameter_cell_id": evidence.get("parameter_cell_id"),
        "git_sha": prov["git_sha"],
        "git_dirty": prov["git_dirty"],
        "git_diff_sha256": prov["git_diff_sha256"],
        "artifacts": artifacts,
        "policy": evidence.get("policy"),
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return {
        "run_dir": str(out_dir),
        "candidate_evidence": str(evidence_path),
        "summary": str(summary_path),
        "manifest": str(manifest_path),
    }


def load_scorecard_from_report(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    scorecard = payload.get("candidate_replay_scorecard")
    if not isinstance(scorecard, dict):
        raise ValueError("leadlag_report_missing_candidate_replay_scorecard")
    return scorecard


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="polymarket_leadlag.candidate_replay",
        description="Extract Polymarket lead-lag candidate replay evidence from a lead-lag report",
    )
    p.add_argument("--leadlag-report", required=True, dest="leadlag_report")
    p.add_argument("--out-dir", default=None, dest="out_dir")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    scorecard = load_scorecard_from_report(Path(args.leadlag_report))
    out_dir = (
        Path(args.out_dir)
        if args.out_dir
        else _data_root() / "alpha_history_runs" / "polymarket_leadlag_candidate_replay"
    )
    written = write_replay_evidence(scorecard=scorecard, out_dir=out_dir)
    summary = scorecard.get("selected_summary") or {}
    print(json.dumps({
        "status": scorecard.get("status"),
        "candidate_id": summary.get("candidate_id"),
        "sample_count": summary.get("sample_count"),
        "net_bps_mean": summary.get("net_bps_mean"),
        "holdout_net_bps_mean": summary.get("holdout_net_bps_mean"),
        "cost_wall_status": summary.get("cost_wall_status"),
        "candidate_evidence": written["candidate_evidence"],
        "summary": written["summary"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
