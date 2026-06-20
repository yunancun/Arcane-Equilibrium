"""AEG-S3 candidate direct rows 純函數核心。"""

from __future__ import annotations

import datetime as dt
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

_HELPER_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_HELPER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_HELPER_SCRIPTS))

from lib import stats_common  # noqa: E402

from . import DIRECT_REPORT_SCHEMA_VERSION, RUNNER_VERSION


def load_evidence(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _float_or_none(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _bool_or_none(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    s = str(value).strip().lower()
    if s in {"true", "1", "yes", "y"}:
        return True
    if s in {"false", "0", "no", "n"}:
        return False
    return None


def _parse_ts(value: Any) -> Optional[dt.datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(s)
    except ValueError:
        try:
            d = dt.date.fromisoformat(s)
        except ValueError:
            return None
        return dt.datetime.combine(d, dt.time.min, tzinfo=dt.timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _date_key(ts: Optional[dt.datetime]) -> Optional[str]:
    if ts is None:
        return None
    return ts.date().isoformat()


def _candidate_key(evidence: dict[str, Any]) -> Optional[str]:
    raw = evidence.get("candidate_key")
    if raw is None and isinstance(evidence.get("source"), dict):
        raw = (evidence.get("source") or {}).get("candidate_key")
    text = str(raw).strip() if raw is not None else ""
    return text or None


def _annualized_sharpe(values_fraction: list[float], annualization_factor: Optional[float]) -> Optional[float]:
    clean = [v for v in values_fraction if math.isfinite(v)]
    if len(clean) < 2 or annualization_factor is None or annualization_factor <= 0:
        return None
    sd = statistics.stdev(clean)
    if sd <= 0:
        return None
    return statistics.mean(clean) / sd * math.sqrt(annualization_factor)


def _mean(values: list[float]) -> Optional[float]:
    clean = [v for v in values if math.isfinite(v)]
    return statistics.mean(clean) if clean else None


def _round_or_none(value: Optional[float], digits: int = 8) -> Optional[float]:
    if value is None or not math.isfinite(value):
        return None
    return round(value, digits)


def _normalize_sample(raw: dict[str, Any], idx: int) -> tuple[Optional[dict[str, Any]], list[str]]:
    reasons: list[str] = []
    sample_ts = _parse_ts(raw.get("sample_ts_utc") or raw.get("sample_date") or raw.get("date"))
    sample_date = _date_key(sample_ts)
    regime = str(raw.get("regime") or "").strip()
    bucket = raw.get("independence_bucket")
    gross = _float_or_none(raw.get("gross_bps"))
    cost = _float_or_none(raw.get("cost_bps"))
    net = _float_or_none(raw.get("net_bps"))
    is_oos = _bool_or_none(raw.get("is_oos"))
    sample_id = str(raw.get("sample_id") or f"sample_{idx}").strip()

    if sample_ts is None:
        reasons.append("missing_or_invalid_sample_ts")
    if not regime:
        reasons.append("missing_regime")
    if gross is None:
        reasons.append("missing_or_invalid_gross_bps")
    if cost is None:
        reasons.append("missing_or_invalid_cost_bps")
    if net is None:
        reasons.append("missing_or_invalid_net_bps")
    if reasons:
        return None, reasons
    return {
        "sample_id": sample_id,
        "sample_ts": sample_ts,
        "sample_ts_utc": sample_ts.isoformat(),
        "sample_date": sample_date,
        "regime": regime,
        "independence_bucket": str(bucket).strip() if bucket is not None and str(bucket).strip() else None,
        "gross_bps": gross,
        "cost_bps": cost,
        "net_bps": net,
        "is_oos": is_oos,
    }, []


def _sample_regime_by_date(samples: list[dict[str, Any]]) -> dict[str, Optional[str]]:
    regimes_by_date: dict[str, set[str]] = defaultdict(set)
    for row in samples:
        if row.get("sample_date") and row.get("regime"):
            regimes_by_date[row["sample_date"]].add(row["regime"])
    return {
        date: next(iter(regimes)) if len(regimes) == 1 else None
        for date, regimes in regimes_by_date.items()
    }


def _daily_return_rows(evidence: dict[str, Any], samples: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    payload = evidence.get("daily_returns")
    if not isinstance(payload, dict):
        return [], []
    unit = str(payload.get("unit") or "fraction").strip().lower()
    raw_values = payload.get("values")
    regime_by_date = payload.get("regime_by_date") or {}
    inferred = _sample_regime_by_date(samples)
    rows: list[dict[str, Any]] = []
    rejects: list[str] = []

    def _append(date_value: Any, return_value: Any, regime_value: Any = None) -> None:
        parsed = _parse_ts(date_value)
        date = _date_key(parsed)
        val = _float_or_none(return_value)
        if date is None or val is None:
            rejects.append(f"invalid_daily_return:{date_value}")
            return
        frac = val / 1e4 if unit == "bps" else val
        regime = str(regime_value or regime_by_date.get(date) or inferred.get(date) or "").strip() or None
        rows.append({"date": date, "return_fraction": frac, "regime": regime})

    if isinstance(raw_values, dict):
        for date, value in raw_values.items():
            _append(date, value)
    elif isinstance(raw_values, list):
        for item in raw_values:
            if not isinstance(item, dict):
                rejects.append("invalid_daily_return_row")
                continue
            return_value = item["return"] if "return" in item else item.get("value")
            _append(item.get("date") or item.get("sample_date"), return_value, item.get("regime"))
    return rows, rejects


def _pbo_value(evidence: dict[str, Any], *, seed: int) -> Optional[float]:
    raw = evidence.get("pbo_candidates")
    if not isinstance(raw, dict):
        return None
    candidates: dict[str, dict[str, float]] = {}
    for key, daily in raw.items():
        if not isinstance(daily, dict):
            continue
        rows: dict[str, float] = {}
        for day, value in daily.items():
            f = _float_or_none(value)
            if f is not None:
                rows[str(day)] = f
        if rows:
            candidates[str(key)] = rows
    out = stats_common.pbo_cscv(candidates, seed=seed)
    return _float_or_none(out.get("value"))


def _recent_mean(samples: list[dict[str, Any]], max_ts: dt.datetime, days: int) -> Optional[float]:
    start = max_ts - dt.timedelta(days=days)
    vals = [row["net_bps"] for row in samples if row["sample_ts"] >= start]
    return _mean(vals)


def _build_regime_row(
    *,
    regime: str,
    samples: list[dict[str, Any]],
    daily_rows: list[dict[str, Any]],
    evidence: dict[str, Any],
    max_ts: Optional[dt.datetime],
    pbo: Optional[float],
) -> dict[str, Any]:
    gross = _mean([row["gross_bps"] for row in samples])
    cost = _mean([row["cost_bps"] for row in samples])
    net = _mean([row["net_bps"] for row in samples])
    net_to_cost = net / cost if net is not None and cost is not None and cost > 0 else None
    sample_returns_fraction = [row["net_bps"] / 1e4 for row in samples]
    annualization_factor = _float_or_none(evidence.get("annualization_factor"))
    oos_returns = [row["net_bps"] / 1e4 for row in samples if row.get("is_oos") is True]
    buckets = [row.get("independence_bucket") for row in samples]
    n_independent = len(set(buckets)) if buckets and all(buckets) else None
    sample_unit = evidence.get("sample_unit") or evidence.get("sample_unit_name")
    k_trials = evidence.get("k_trials")
    k_int = int(k_trials) if _float_or_none(k_trials) is not None else None

    regime_daily = [row["return_fraction"] for row in daily_rows if row.get("regime") == regime]
    mean_daily_bps = _mean([v * 1e4 for v in regime_daily])
    recent_90 = _recent_mean(samples, max_ts, 90) if max_ts is not None else None
    recent_180 = _recent_mean(samples, max_ts, 180) if max_ts is not None else None

    return {
        "regime": regime,
        "n_days": len({row["sample_date"] for row in samples if row.get("sample_date")}),
        "gross_bps": _round_or_none(gross),
        "cost_bps": _round_or_none(cost),
        "net_bps": _round_or_none(net),
        "net_to_cost_ratio": _round_or_none(net_to_cost),
        "mean_daily_bps": _round_or_none(mean_daily_bps),
        "annualized_net_sharpe": _round_or_none(_annualized_sharpe(sample_returns_fraction, annualization_factor)),
        "oos_sharpe": _round_or_none(_annualized_sharpe(oos_returns, annualization_factor)),
        "psr_0": _round_or_none(stats_common.psr_bailey_ldp(sample_returns_fraction, sr_benchmark=0.0)),
        "dsr_k": _round_or_none(stats_common.dsr_with_k(sample_returns_fraction, k_int or 0)),
        "pbo": _round_or_none(pbo),
        "k_trials": k_int,
        "n_independent": n_independent,
        "sample_unit": str(sample_unit).strip() if sample_unit is not None and str(sample_unit).strip() else None,
        "recent_90d_net_bps": _round_or_none(recent_90),
        "recent_180d_net_bps": _round_or_none(recent_180),
    }


def build_direct_report(
    evidence: dict[str, Any],
    *,
    run_id: str,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """候選 evidence JSON -> direct report + summary + normalized rows。

    回傳 `(direct_report, summary, sample_rows, daily_rows)`。
    """
    samples: list[dict[str, Any]] = []
    rejected_samples: list[dict[str, Any]] = []
    for idx, raw in enumerate(evidence.get("samples") or []):
        if not isinstance(raw, dict):
            rejected_samples.append({"index": idx, "reasons": ["invalid_sample_row"]})
            continue
        row, reasons = _normalize_sample(raw, idx)
        if row is None:
            rejected_samples.append({"index": idx, "sample_id": raw.get("sample_id"), "reasons": reasons})
            continue
        samples.append(row)

    daily_rows, daily_rejects = _daily_return_rows(evidence, samples)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in samples:
        grouped[row["regime"]].append(row)
    max_ts = max((row["sample_ts"] for row in samples), default=None)
    pbo = _pbo_value(evidence, seed=int(evidence.get("pbo_seed") or 20260611))
    candidate_rows = [
        _build_regime_row(
            regime=regime,
            samples=grouped[regime],
            daily_rows=daily_rows,
            evidence=evidence,
            max_ts=max_ts,
            pbo=pbo,
        )
        for regime in sorted(grouped)
    ]

    report = {
        "schema_version": DIRECT_REPORT_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "run_id": run_id,
        "candidate_id": evidence.get("candidate_id"),
        "candidate_key": _candidate_key(evidence),
        "strategy_family": evidence.get("strategy_family"),
        "parameter_cell_id": evidence.get("parameter_cell_id"),
        "selected_variant": evidence.get("selected_variant") or evidence.get("variant"),
        "date_span": [
            min((row["sample_date"] for row in samples), default=None),
            max((row["sample_date"] for row in samples), default=None),
        ],
        "candidate_metric_defaults": {
            "sample_unit": evidence.get("sample_unit"),
            "k_trials": evidence.get("k_trials"),
        },
        "candidate_regime_metrics": candidate_rows,
        "daily_returns_present": bool(daily_rows),
        "policy": "explicit_sample_returns_only_no_scalar_to_series_synthesis",
    }
    summary = {
        "schema_version": "aeg.s3_candidate_rows_summary.v0.1",
        "run_id": run_id,
        "candidate_id": evidence.get("candidate_id"),
        "candidate_key": report.get("candidate_key"),
        "strategy_family": evidence.get("strategy_family"),
        "parameter_cell_id": evidence.get("parameter_cell_id"),
        "selected_variant": report["selected_variant"],
        "sample_count": len(samples),
        "rejected_sample_count": len(rejected_samples),
        "rejected_samples": rejected_samples,
        "daily_return_count": len(daily_rows),
        "daily_return_rejects": daily_rejects,
        "regime_counts": dict(sorted(Counter(row["regime"] for row in samples).items())),
        "n_regime_rows": len(candidate_rows),
        "pbo_status": "measured" if pbo is not None else "missing_or_insufficient",
        "notes": [
            "net_bps comes from explicit sample-level net_bps only",
            "mean_daily_bps is computed only from explicit daily_returns",
            "n_independent uses unique independence_bucket only when every sample has one",
        ],
        "status_counts": {"candidate_rows": len(candidate_rows)} if candidate_rows else {"no_rows": 1},
    }
    sample_rows = [
        {k: row.get(k) for k in (
            "sample_id", "sample_ts_utc", "sample_date", "regime", "independence_bucket",
            "gross_bps", "cost_bps", "net_bps", "is_oos",
        )}
        for row in samples
    ]
    return report, summary, sample_rows, daily_rows
