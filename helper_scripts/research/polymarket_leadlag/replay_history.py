#!/usr/bin/env python3
"""Polymarket lead-lag replay history accumulator.

This module scans dated lead-lag reports, extracts embedded candidate replay
evidence, deduplicates explicit sample returns, and emits an AEG-compatible
history evidence payload.

Boundary:
  - artifact/evidence only;
  - reads local lead-lag JSON reports only;
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
        CANDIDATE_REPLAY_HISTORY_SCHEMA_VERSION,
        CANDIDATE_REPLAY_HISTORY_SUMMARY_SCHEMA_VERSION,
        RUNNER_VERSION,
    )
except ImportError:  # pragma: no cover
    _here = Path(__file__).resolve()
    _research = _here.parents[1]
    if str(_research) not in sys.path:
        sys.path.insert(0, str(_research))
    from polymarket_leadlag import (  # type: ignore
        CANDIDATE_REPLAY_HISTORY_SCHEMA_VERSION,
        CANDIDATE_REPLAY_HISTORY_SUMMARY_SCHEMA_VERSION,
        RUNNER_VERSION,
    )


DEFAULT_MIN_HISTORY_DAYS = 30
DEFAULT_MIN_HISTORY_SAMPLES = 30
DEFAULT_HISTORY_REPORT_LIMIT = 0
DEFAULT_MIN_INTERIM_EDGE_DAYS = 3
PBO_SEED = 20260620


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _data_root() -> Path:
    base = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw").strip() or "/tmp/openclaw"
    return Path(base)


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
        try:
            day = dt.date.fromisoformat(raw)
        except ValueError:
            return None
        return dt.datetime.combine(day, dt.time.min, tzinfo=dt.timezone.utc)
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


def _annualization_factor(samples: list[dict[str, Any]]) -> Optional[float]:
    timestamps = []
    for sample in samples:
        parsed = _parse_dt(sample.get("sample_ts_utc"))
        if parsed is not None:
            timestamps.append(int(parsed.timestamp() * 1000))
    gap_ms = _median_positive_gap_ms(timestamps)
    if gap_ms is None or gap_ms <= 0:
        return None
    return (365.25 * 24 * 60 * 60 * 1000) / gap_ms


def _load_json(path: Path) -> Optional[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _report_sort_key(path: Path, payload: dict[str, Any]) -> tuple[float, str]:
    parsed = _parse_dt(payload.get("created_at_utc"))
    if parsed is not None:
        return parsed.timestamp(), path.name
    try:
        return path.stat().st_mtime, path.name
    except OSError:
        return 0.0, path.name


def load_replay_reports(report_dir: Path, *, limit: int = DEFAULT_HISTORY_REPORT_LIMIT) -> list[dict[str, Any]]:
    report_dir = Path(report_dir)
    if not report_dir.exists():
        return []
    rows: list[tuple[float, str, dict[str, Any]]] = []
    for path in report_dir.glob("polymarket_leadlag_*.json"):
        if path.name == "polymarket_leadlag_latest.json":
            continue
        payload = _load_json(path)
        if payload is None:
            continue
        scorecard = payload.get("candidate_replay_scorecard")
        if not isinstance(scorecard, dict):
            continue
        ts, name = _report_sort_key(path, payload)
        rows.append((ts, name, {**payload, "_history_path": str(path)}))
    rows.sort(key=lambda item: (item[0], item[1]))
    if limit and limit > 0:
        rows = rows[-int(limit):]
    return [payload for _ts, _name, payload in rows]


def _sample_key(sample: dict[str, Any], fallback: int) -> str:
    raw = str(sample.get("sample_id") or "").strip()
    if raw:
        return raw
    return "|".join([
        str(sample.get("sample_ts_utc") or ""),
        str(sample.get("regime") or ""),
        str(sample.get("side") or ""),
        str(sample.get("forward_return_bps") or ""),
        str(fallback),
    ])


def _normalize_sample(sample: dict[str, Any]) -> Optional[dict[str, Any]]:
    sample_ts = _parse_dt(sample.get("sample_ts_utc") or sample.get("sample_date"))
    gross = _float_or_none(sample.get("gross_bps"))
    cost = _float_or_none(sample.get("cost_bps"))
    net = _float_or_none(sample.get("net_bps"))
    if sample_ts is None or gross is None or cost is None or net is None:
        return None
    out = dict(sample)
    out["sample_ts_utc"] = sample_ts.isoformat()
    out["sample_date"] = sample_ts.date().isoformat()
    out["regime"] = str(sample.get("regime") or "unsegmented").strip() or "unsegmented"
    out["gross_bps"] = round(gross, 8)
    out["cost_bps"] = round(cost, 8)
    out["net_bps"] = round(net, 8)
    if not str(out.get("sample_id") or "").strip():
        out["sample_id"] = _sample_key(out, 0)
    if not str(out.get("independence_bucket") or "").strip():
        out["independence_bucket"] = out["sample_id"]
    return out


def _daily_returns(samples: list[dict[str, Any]]) -> dict[str, Any]:
    by_date: dict[str, float] = defaultdict(float)
    regimes: dict[str, set[str]] = defaultdict(set)
    for sample in samples:
        day = str(sample.get("sample_date") or "").strip()
        net = _float_or_none(sample.get("net_bps"))
        if not day or net is None:
            continue
        by_date[day] += net / 10_000.0
        regime = str(sample.get("regime") or "").strip()
        if regime:
            regimes[day].add(regime)
    return {
        "unit": "fraction",
        "policy": "deduped_polymarket_replay_history_net_bps_by_sample_date",
        "regime_by_date": {
            day: next(iter(values))
            for day, values in sorted(regimes.items())
            if len(values) == 1
        },
        "values": dict(sorted(by_date.items())),
    }


def _merge_pbo_candidates(
    target: dict[str, dict[str, float]],
    raw: Any,
) -> int:
    if not isinstance(raw, dict):
        return 0
    merged = 0
    for cell, daily in raw.items():
        if not isinstance(daily, dict):
            continue
        cell_key = str(cell)
        cell_rows = target.setdefault(cell_key, {})
        for day, value in daily.items():
            parsed_day = _parse_dt(day)
            date_key = parsed_day.date().isoformat() if parsed_day else str(day)
            f = _float_or_none(value)
            if f is None:
                continue
            cell_rows[date_key] = float(f)
            merged += 1
    return merged


def _source_candidate_key(scorecard: dict[str, Any], evidence: dict[str, Any], summary: dict[str, Any]) -> Optional[str]:
    for obj in (evidence, summary, scorecard):
        value = obj.get("candidate_key") or obj.get("selected_candidate_key")
        text = str(value).strip() if value is not None else ""
        if text:
            return text
    source = evidence.get("source") if isinstance(evidence.get("source"), dict) else {}
    value = source.get("candidate_key") if isinstance(source, dict) else None
    text = str(value).strip() if value is not None else ""
    return text or None


def _report_replay(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    scorecard = payload.get("candidate_replay_scorecard")
    if not isinstance(scorecard, dict):
        return None
    evidence = scorecard.get("selected_evidence")
    summary = scorecard.get("selected_summary")
    if not isinstance(evidence, dict) or not isinstance(summary, dict):
        return None
    ckey = _source_candidate_key(scorecard, evidence, summary)
    if not ckey:
        return None
    return {
        "created_at_utc": payload.get("created_at_utc"),
        "path": payload.get("_history_path"),
        "scorecard": scorecard,
        "evidence": evidence,
        "summary": summary,
        "candidate_key": ckey,
    }


def _summary_status(sample_count: int, n_days: int, *, min_days: int, min_samples: int) -> tuple[str, str]:
    if sample_count <= 0:
        return "NO_REPLAY_HISTORY_SAMPLES", "candidate replay reports exist but no explicit samples were usable"
    if n_days < min_days:
        return "REPLAY_HISTORY_DAYS_INSUFFICIENT", "deduped replay history does not yet span the required number of dates"
    if sample_count < min_samples:
        return "REPLAY_HISTORY_SAMPLES_INSUFFICIENT", "deduped replay history does not yet meet the sample floor"
    return "REPLAY_HISTORY_READY_FOR_AEG_RECHECK", "deduped replay history meets sample/date floor for AEG recheck"


def _history_calendar_fields(days: list[str], *, min_days: int) -> dict[str, Any]:
    if not days:
        return {
            "history_days_remaining": int(min_days),
            "history_calendar_span_days": 0,
            "history_date_gap_count": 0,
            "earliest_history_ready_date": None,
        }
    first_day = dt.date.fromisoformat(days[0])
    last_day = dt.date.fromisoformat(days[-1])
    span = (last_day - first_day).days + 1
    ready_day = first_day + dt.timedelta(days=max(0, int(min_days) - 1))
    return {
        "history_days_remaining": max(0, int(min_days) - len(days)),
        "history_calendar_span_days": span,
        "history_date_gap_count": max(0, span - len(days)),
        "earliest_history_ready_date": ready_day.isoformat(),
    }


def _interim_edge_fields(
    *,
    status: str,
    sample_count: int,
    n_days: int,
    min_samples: int,
    net_bps_mean: Optional[float],
    holdout_net_bps_mean: Optional[float],
) -> dict[str, str]:
    if sample_count < int(min_samples):
        edge_status = "INSUFFICIENT_SAMPLES_FOR_INTERIM_EDGE"
        budget_status = "CONTINUE_HISTORY_ACCUMULATION"
        action = "continue_polymarket_replay_until_sample_floor"
    elif (
        n_days < DEFAULT_MIN_INTERIM_EDGE_DAYS
        and status != "REPLAY_HISTORY_READY_FOR_AEG_RECHECK"
    ):
        edge_status = "INSUFFICIENT_DAYS_FOR_INTERIM_EDGE"
        budget_status = "CONTINUE_HISTORY_ACCUMULATION"
        action = "continue_polymarket_replay_until_interim_edge_floor"
    elif net_bps_mean is not None and holdout_net_bps_mean is not None and (
        net_bps_mean <= 0 and holdout_net_bps_mean <= 0
    ):
        edge_status = "INTERIM_NEGATIVE_NET_AND_HOLDOUT"
        budget_status = "EARLY_ROTATE_RECOMMENDED"
        action = (
            "rotate_polymarket_leadlag_candidate_or_change_feature_family_"
            "before_spending_30d_history_budget"
        )
    elif net_bps_mean is not None and net_bps_mean <= 0:
        edge_status = "INTERIM_NEGATIVE_NET"
        budget_status = "REVIEW_BEFORE_MORE_HISTORY_BUDGET"
        action = "review_polymarket_net_edge_decay_before_more_history_budget"
    elif holdout_net_bps_mean is not None and holdout_net_bps_mean <= 0:
        edge_status = "INTERIM_HOLDOUT_NOT_POSITIVE"
        budget_status = "REVIEW_BEFORE_MORE_HISTORY_BUDGET"
        action = "review_polymarket_holdout_decay_before_more_history_budget"
    elif net_bps_mean is not None and holdout_net_bps_mean is not None and (
        net_bps_mean > 0 and holdout_net_bps_mean > 0
    ):
        edge_status = "INTERIM_POSITIVE_NET_AND_HOLDOUT"
        budget_status = (
            "READY_FOR_AEG_RECHECK"
            if status == "REPLAY_HISTORY_READY_FOR_AEG_RECHECK"
            else "CONTINUE_HISTORY_ACCUMULATION"
        )
        action = (
            "build_polymarket_execution_realism_before_promotion"
            if status == "REPLAY_HISTORY_READY_FOR_AEG_RECHECK"
            else "continue_dated_polymarket_replay_history_until_min_days"
        )
    else:
        edge_status = "INTERIM_EDGE_UNDETERMINED"
        budget_status = "CONTINUE_HISTORY_ACCUMULATION"
        action = "continue_dated_polymarket_replay_history_until_min_days"
    return {
        "interim_edge_status": edge_status,
        "history_budget_status": budget_status,
        "recommended_next_action": action,
    }


def _build_candidate_history(
    *,
    candidate_key: str,
    rows: list[dict[str, Any]],
    min_days: int,
    min_samples: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    reports = sorted(rows, key=lambda row: (str(row.get("created_at_utc") or ""), str(row.get("path") or "")))
    sample_by_key: dict[str, dict[str, Any]] = {}
    pbo_candidates: dict[str, dict[str, float]] = {}
    rejected = Counter()
    pbo_values_merged = 0

    for report in reports:
        evidence = report["evidence"]
        for idx, raw_sample in enumerate(evidence.get("samples") or []):
            if not isinstance(raw_sample, dict):
                rejected["invalid_sample_row"] += 1
                continue
            sample = _normalize_sample(raw_sample)
            if sample is None:
                rejected["missing_required_sample_field"] += 1
                continue
            key = _sample_key(sample, idx)
            sample_by_key[key] = {
                **sample,
                "sample_id": key,
                "history_source_report_created_at_utc": report.get("created_at_utc"),
            }
        pbo_values_merged += _merge_pbo_candidates(pbo_candidates, evidence.get("pbo_candidates"))

    samples = sorted(sample_by_key.values(), key=lambda row: (str(row.get("sample_ts_utc")), str(row.get("sample_id"))))
    days = sorted({str(row.get("sample_date")) for row in samples if row.get("sample_date")})
    gross = [_float_or_none(row.get("gross_bps")) for row in samples]
    net = [_float_or_none(row.get("net_bps")) for row in samples]
    cost = [_float_or_none(row.get("cost_bps")) for row in samples]
    clean_gross = [float(v) for v in gross if v is not None]
    clean_net = [float(v) for v in net if v is not None]
    clean_cost = [float(v) for v in cost if v is not None]
    holdout_net = [
        float(v)
        for v in (_float_or_none(row.get("net_bps")) for row in samples if row.get("is_oos") is True)
        if v is not None
    ]
    first = reports[0]
    last = reports[-1]
    first_summary = first["summary"]
    last_summary = last["summary"]
    annualization = _annualization_factor(samples)
    status, reason = _summary_status(
        len(samples),
        len(days),
        min_days=min_days,
        min_samples=min_samples,
    )
    pbo_day_count = len({day for daily in pbo_candidates.values() for day in daily})
    net_bps_mean = _round_or_none(_mean(clean_net))
    holdout_net_bps_mean = _round_or_none(_mean(holdout_net))
    summary = {
        "schema_version": CANDIDATE_REPLAY_HISTORY_SUMMARY_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "status": status,
        "reason": reason,
        "candidate_key": candidate_key,
        "candidate_id": last_summary.get("candidate_id") or first_summary.get("candidate_id"),
        "strategy_family": last_summary.get("strategy_family") or first_summary.get("strategy_family"),
        "parameter_cell_id": last_summary.get("parameter_cell_id") or first_summary.get("parameter_cell_id"),
        "selected_variant": last_summary.get("selected_variant") or first_summary.get("selected_variant"),
        "sample_unit": last_summary.get("sample_unit") or first["evidence"].get("sample_unit"),
        "report_count": len(reports),
        "first_report_created_at_utc": first.get("created_at_utc"),
        "last_report_created_at_utc": last.get("created_at_utc"),
        "first_sample_ts_utc": samples[0].get("sample_ts_utc") if samples else None,
        "last_sample_ts_utc": samples[-1].get("sample_ts_utc") if samples else None,
        "sample_count": len(samples),
        "n_days": len(days),
        "min_history_days": int(min_days),
        "min_history_samples": int(min_samples),
        **_history_calendar_fields(days, min_days=min_days),
        "gross_bps_mean": _round_or_none(_mean(clean_gross)),
        "cost_bps_mean": _round_or_none(_mean(clean_cost)),
        "net_bps_mean": net_bps_mean,
        "net_bps_t_stat_naive": _round_or_none(_t_stat(clean_net)),
        "positive_net_sample_count": sum(1 for value in clean_net if value > 0),
        "positive_net_sample_rate": (
            round(sum(1 for value in clean_net if value > 0) / len(clean_net), 8)
            if clean_net else None
        ),
        "holdout_sample_count": len(holdout_net),
        "holdout_net_bps_mean": holdout_net_bps_mean,
        "holdout_net_bps_t_stat_naive": _round_or_none(_t_stat(holdout_net)),
        "pbo_history_cell_count": len(pbo_candidates),
        "pbo_history_day_count": pbo_day_count,
        "pbo_values_merged": pbo_values_merged,
        **_interim_edge_fields(
            status=status,
            sample_count=len(samples),
            n_days=len(days),
            min_samples=min_samples,
            net_bps_mean=net_bps_mean,
            holdout_net_bps_mean=holdout_net_bps_mean,
        ),
        "rejected_sample_reasons": dict(sorted(rejected.items())),
        "execution_realism_status": "UNMEASURED",
        "execution_realism_note": "history accumulator only; maker/taker fill and queue realism are not measured",
        "promotion_boundary": "history_replay_not_execution_or_promotion_proof",
    }
    evidence = {
        "schema_version": CANDIDATE_REPLAY_HISTORY_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "candidate_id": summary["candidate_id"],
        "candidate_key": candidate_key,
        "strategy_family": summary["strategy_family"],
        "parameter_cell_id": summary["parameter_cell_id"],
        "selected_variant": summary["selected_variant"] or "ic_sign_delta",
        "sample_unit": summary["sample_unit"],
        "k_trials": last["evidence"].get("k_trials") or last_summary.get("k_trials"),
        "samples": samples,
        "daily_returns": _daily_returns(samples),
        "source": {
            "source_type": "polymarket_leadlag_candidate_replay_history",
            "candidate_key": candidate_key,
            "report_count": len(reports),
            "first_report_created_at_utc": first.get("created_at_utc"),
            "last_report_created_at_utc": last.get("created_at_utc"),
            "execution_realism_status": "UNMEASURED",
        },
        "policy": "deduped_history_of_explicit_replay_samples_no_execution_realism_no_signal_no_order_authority",
    }
    if annualization is not None:
        evidence["annualization_factor"] = annualization
    if pbo_candidates:
        evidence["pbo_seed"] = PBO_SEED
        evidence["pbo_candidates"] = {
            cell: dict(sorted(daily.items()))
            for cell, daily in sorted(pbo_candidates.items())
        }
    return evidence, summary


def build_history_scorecard(
    *,
    reports: list[dict[str, Any]],
    candidate_key: Optional[str] = None,
    min_days: int = DEFAULT_MIN_HISTORY_DAYS,
    min_samples: int = DEFAULT_MIN_HISTORY_SAMPLES,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    scanned = 0
    skipped = Counter()
    for payload in reports:
        scanned += 1
        replay = _report_replay(payload)
        if replay is None:
            skipped["missing_candidate_replay"] += 1
            continue
        if candidate_key and replay["candidate_key"] != candidate_key:
            skipped["candidate_key_mismatch"] += 1
            continue
        grouped[replay["candidate_key"]].append(replay)

    if not grouped:
        return {
            "schema_version": CANDIDATE_REPLAY_HISTORY_SUMMARY_SCHEMA_VERSION,
            "runner_version": RUNNER_VERSION,
            "status": "NO_REPLAY_HISTORY",
            "reason": "no dated lead-lag reports with candidate replay evidence matched the filter",
            "candidate_key": candidate_key,
            "report_count": scanned,
            "skipped_reports": dict(sorted(skipped.items())),
            "min_history_days": int(min_days),
            "min_history_samples": int(min_samples),
        }

    histories = []
    for ckey, rows in grouped.items():
        evidence, summary = _build_candidate_history(
            candidate_key=ckey,
            rows=rows,
            min_days=min_days,
            min_samples=min_samples,
        )
        histories.append({"candidate_key": ckey, "evidence": evidence, "summary": summary})
    histories.sort(
        key=lambda row: (
            int(row["summary"].get("n_days") or 0),
            int(row["summary"].get("sample_count") or 0),
            str(row["summary"].get("last_report_created_at_utc") or ""),
        ),
        reverse=True,
    )
    selected = histories[0]
    selected_summary = selected["summary"]
    return {
        "schema_version": CANDIDATE_REPLAY_HISTORY_SUMMARY_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "status": selected_summary.get("status"),
        "reason": selected_summary.get("reason"),
        "selected_candidate_key": selected["candidate_key"],
        "candidate_key": selected["candidate_key"],
        "report_count": scanned,
        "matched_report_count": sum(len(rows) for rows in grouped.values()),
        "candidate_count": len(histories),
        "skipped_reports": dict(sorted(skipped.items())),
        "min_history_days": int(min_days),
        "min_history_samples": int(min_samples),
        "selected_summary": selected_summary,
        "selected_evidence": selected["evidence"],
        "candidate_summaries": [row["summary"] for row in histories],
        "promotion_boundary": "history_replay_not_execution_or_promotion_proof",
    }


def build_history_scorecard_from_report_dir(
    report_dir: Path,
    *,
    candidate_key: Optional[str] = None,
    limit: int = DEFAULT_HISTORY_REPORT_LIMIT,
    min_days: int = DEFAULT_MIN_HISTORY_DAYS,
    min_samples: int = DEFAULT_MIN_HISTORY_SAMPLES,
) -> dict[str, Any]:
    return build_history_scorecard(
        reports=load_replay_reports(Path(report_dir), limit=limit),
        candidate_key=candidate_key,
        min_days=min_days,
        min_samples=min_samples,
    )


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


def write_history_evidence(
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
        raise ValueError("scorecard_missing_selected_history_evidence_or_summary")
    evidence_path = out_dir / "polymarket_leadlag_replay_history_evidence.json"
    summary_path = out_dir / "polymarket_leadlag_replay_history_summary.json"
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
        "schema_version": "polymarket.leadlag_candidate_replay_history_manifest.v0.1",
        "program": "polymarket-leadlag-replay-history",
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
        "history_evidence": str(evidence_path),
        "summary": str(summary_path),
        "manifest": str(manifest_path),
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="polymarket_leadlag.replay_history",
        description="Build deduped Polymarket lead-lag candidate replay history evidence",
    )
    p.add_argument("--report-dir", default=None, dest="report_dir")
    p.add_argument("--out-dir", default=None, dest="out_dir")
    p.add_argument("--candidate-key", default=None, dest="candidate_key")
    p.add_argument("--limit", default=DEFAULT_HISTORY_REPORT_LIMIT, type=int, dest="limit")
    p.add_argument("--min-days", default=DEFAULT_MIN_HISTORY_DAYS, type=int, dest="min_days")
    p.add_argument("--min-samples", default=DEFAULT_MIN_HISTORY_SAMPLES, type=int, dest="min_samples")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    report_dir = (
        Path(args.report_dir)
        if args.report_dir
        else _data_root() / "research" / "polymarket_leadlag"
    )
    scorecard = build_history_scorecard_from_report_dir(
        report_dir,
        candidate_key=args.candidate_key,
        limit=args.limit,
        min_days=args.min_days,
        min_samples=args.min_samples,
    )
    written = None
    if scorecard.get("selected_evidence"):
        out_dir = (
            Path(args.out_dir)
            if args.out_dir
            else _data_root() / "alpha_history_runs" / "polymarket_leadlag_replay_history"
        )
        written = write_history_evidence(scorecard=scorecard, out_dir=out_dir)
    summary = scorecard.get("selected_summary") if isinstance(scorecard.get("selected_summary"), dict) else {}
    print(json.dumps({
        "status": scorecard.get("status"),
        "candidate_key": scorecard.get("selected_candidate_key") or scorecard.get("candidate_key"),
        "report_count": scorecard.get("report_count"),
        "matched_report_count": scorecard.get("matched_report_count"),
        "sample_count": summary.get("sample_count"),
        "n_days": summary.get("n_days"),
        "net_bps_mean": summary.get("net_bps_mean"),
        "history_evidence": (written or {}).get("history_evidence"),
        "summary": (written or {}).get("summary"),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
