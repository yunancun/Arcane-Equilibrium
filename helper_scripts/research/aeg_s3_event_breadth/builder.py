"""Build true FND-2 PIT breadth results from AEG-S3 event evidence."""

from __future__ import annotations

import datetime as dt
import json
import math
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

try:
    from . import RUNNER_VERSION, SUPPORTED_CANDIDATE_SYMBOL_FIELDS
except ImportError:  # pragma: no cover - direct file execution fallback
    _research = Path(__file__).resolve().parents[1]
    if str(_research) not in sys.path:
        sys.path.insert(0, str(_research))
    from aeg_s3_event_breadth import RUNNER_VERSION, SUPPORTED_CANDIDATE_SYMBOL_FIELDS  # type: ignore

_HELPER_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_HELPER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_HELPER_SCRIPTS))

from aeg_breadth_ladder.evaluator import TierResult  # noqa: E402
from lib import stats_common  # noqa: E402


class UnsupportedCandidateEvidence(ValueError):
    """Raised when evidence cannot honestly be mapped to single-symbol breadth."""


@dataclass(frozen=True)
class EventSample:
    sample_id: str
    sample_ts: dt.datetime
    symbol: str
    gross_bps: float
    cost_bps: float
    net_bps: float
    independence_bucket: Optional[str]
    is_oos: Optional[bool]


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
            parsed_date = dt.date.fromisoformat(s)
        except ValueError:
            return None
        return dt.datetime.combine(parsed_date, dt.time.min, tzinfo=dt.timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _round_or_none(value: Optional[float], digits: int = 8) -> Optional[float]:
    if value is None or not math.isfinite(value):
        return None
    return round(float(value), digits)


def _mean(values: list[float]) -> Optional[float]:
    clean = [float(v) for v in values if math.isfinite(v)]
    return statistics.mean(clean) if clean else None


def _annualized_sharpe(values_fraction: list[float], annualization_factor: Optional[float]) -> Optional[float]:
    clean = [float(v) for v in values_fraction if math.isfinite(v)]
    if len(clean) < 2 or annualization_factor is None or annualization_factor <= 0:
        return None
    sd = statistics.stdev(clean)
    if sd <= 0:
        return None
    return statistics.mean(clean) / sd * math.sqrt(annualization_factor)


def _symbol_from_sample(sample: dict[str, Any], candidate_id: str) -> Optional[str]:
    fields = SUPPORTED_CANDIDATE_SYMBOL_FIELDS.get(candidate_id)
    if not fields:
        return None
    for field in fields:
        value = sample.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def normalize_event_samples(evidence: dict[str, Any]) -> tuple[list[EventSample], list[dict[str, Any]]]:
    """Normalize AEG-S3 evidence samples that carry one event symbol.

    Cross-sectional basket samples, such as ``oi_delta`` top/bottom rebalance
    windows, are rejected at the candidate boundary rather than split into fake
    per-symbol breadth.
    """
    candidate_id = str(evidence.get("candidate_id") or "").strip()
    if candidate_id not in SUPPORTED_CANDIDATE_SYMBOL_FIELDS:
        raise UnsupportedCandidateEvidence(
            f"unsupported_candidate_for_event_breadth:{candidate_id or 'missing'}"
        )

    samples: list[EventSample] = []
    rejects: list[dict[str, Any]] = []
    for idx, raw in enumerate(evidence.get("samples") or []):
        if not isinstance(raw, dict):
            rejects.append({"index": idx, "reason": "invalid_sample_row"})
            continue
        if ("top_symbols" in raw or "bottom_symbols" in raw) and not (
            raw.get("symbol") or raw.get("source_symbol")
        ):
            raise UnsupportedCandidateEvidence(
                "cross_sectional_basket_sample_has_no_single_event_symbol"
            )

        symbol = _symbol_from_sample(raw, candidate_id)
        sample_ts = _parse_ts(raw.get("sample_ts_utc") or raw.get("sample_date") or raw.get("date"))
        gross = _float_or_none(raw.get("gross_bps"))
        cost = _float_or_none(raw.get("cost_bps"))
        net = _float_or_none(raw.get("net_bps"))
        reasons: list[str] = []
        if symbol is None:
            reasons.append("missing_event_symbol")
        if sample_ts is None:
            reasons.append("missing_or_invalid_sample_ts")
        if gross is None:
            reasons.append("missing_or_invalid_gross_bps")
        if cost is None:
            reasons.append("missing_or_invalid_cost_bps")
        if net is None:
            reasons.append("missing_or_invalid_net_bps")
        if reasons:
            rejects.append({"index": idx, "sample_id": raw.get("sample_id"), "reasons": reasons})
            continue

        bucket = raw.get("independence_bucket")
        samples.append(EventSample(
            sample_id=str(raw.get("sample_id") or f"sample_{idx}"),
            sample_ts=sample_ts,
            symbol=symbol,
            gross_bps=float(gross),
            cost_bps=float(cost),
            net_bps=float(net),
            independence_bucket=(
                str(bucket).strip() if bucket is not None and str(bucket).strip() else None
            ),
            is_oos=_bool_or_none(raw.get("is_oos")),
        ))
    return samples, rejects


def _pbo_value(evidence: dict[str, Any]) -> Optional[float]:
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
    out = stats_common.pbo_cscv(candidates, seed=int(evidence.get("pbo_seed") or 20260611))
    return _float_or_none(out.get("value"))


def _sample_alive(sample: EventSample, alive_mask: dict[str, tuple]) -> bool:
    bounds = alive_mask.get(sample.symbol)
    if bounds is None:
        return False
    alive_from, alive_to = bounds
    if alive_from is not None and sample.sample_ts < alive_from:
        return False
    if alive_to is not None and sample.sample_ts > alive_to:
        return False
    return True


def _metric_result(
    *,
    tier: str,
    universe: tuple[str, ...],
    samples: list[EventSample],
    evidence: dict[str, Any],
    pbo: Optional[float],
    notes: dict[str, Any],
) -> TierResult:
    gross = _mean([row.gross_bps for row in samples])
    cost = _mean([row.cost_bps for row in samples])
    net = _mean([row.net_bps for row in samples])
    net_to_cost = net / cost if net is not None and cost is not None and cost > 0 else None
    returns = [row.net_bps / 10_000.0 for row in samples]
    oos_returns = [row.net_bps / 10_000.0 for row in samples if row.is_oos is True]
    annualization = _float_or_none(evidence.get("annualization_factor")) or 365.0
    buckets = [row.independence_bucket for row in samples]
    n_independent = len(set(buckets)) if buckets and all(buckets) else 0
    k_trials = _float_or_none(evidence.get("k_trials"))
    k_int = int(k_trials) if k_trials is not None else None
    sample_unit = str(evidence.get("sample_unit") or "event_window")

    return TierResult(
        tier=tier,
        breadth_symbol_count=len(universe),
        seen_delisted_count=0,
        net_bps=_round_or_none(net),
        gross_bps=_round_or_none(gross),
        cost_bps=_round_or_none(cost),
        net_to_cost_ratio=_round_or_none(net_to_cost),
        is_sharpe=_round_or_none(_annualized_sharpe(returns, annualization)),
        oos_sharpe=_round_or_none(_annualized_sharpe(oos_returns, annualization)),
        n_independent=n_independent,
        sample_unit=sample_unit,
        psr_0=_round_or_none(stats_common.psr_bailey_ldp(returns, sr_benchmark=0.0)),
        dsr_k=_round_or_none(stats_common.dsr_with_k(returns, k_int or 0)),
        pbo=_round_or_none(pbo),
        k_trials=k_int,
        pit_mask_source="fnd2_alive_from_alive_to",
        leak_free_signal=True,
        survivorship_mask_applied=(True if universe else None),
        notes=notes,
    )


class EventEvidenceEvaluator:
    """CandidateEvaluator implementation for single-symbol event evidence."""

    def __init__(self, evidence: dict[str, Any]):
        self.evidence = evidence
        self.candidate_id = str(evidence.get("candidate_id") or "").strip()
        self.samples, self.rejected_samples = normalize_event_samples(evidence)
        self.pbo = _pbo_value(evidence)
        self.reject_reasons = Counter()
        for row in self.rejected_samples:
            reasons = row.get("reasons") or [row.get("reason")]
            for reason in reasons:
                if reason:
                    self.reject_reasons[str(reason)] += 1

    def evaluate(self, *, tier: str, universe: tuple, alive_mask: dict) -> TierResult:
        members = frozenset(str(s) for s in universe)
        included: list[EventSample] = []
        counters: Counter[str] = Counter()
        for sample in self.samples:
            if sample.symbol not in members:
                counters["symbol_not_in_tier"] += 1
                continue
            if sample.symbol not in alive_mask:
                counters["missing_alive_mask"] += 1
                continue
            if not _sample_alive(sample, alive_mask):
                counters["outside_alive_window"] += 1
                continue
            included.append(sample)

        notes = {
            "runner_version": RUNNER_VERSION,
            "raw_sample_count": len(self.samples) + len(self.rejected_samples),
            "valid_sample_count": len(self.samples),
            "included_sample_count": len(included),
            "rejected_sample_count": len(self.rejected_samples),
            "rejected_sample_reasons": dict(sorted(self.reject_reasons.items())),
            "filter_counts": dict(sorted(counters.items())),
            "included_symbol_count": len({row.symbol for row in included}),
            "pbo_status": "measured" if self.pbo is not None else "missing_or_insufficient",
            "policy": "fnd2_pit_alive_mask_single_event_symbol_only",
        }
        return _metric_result(
            tier=tier,
            universe=tuple(str(s) for s in universe),
            samples=included,
            evidence=self.evidence,
            pbo=self.pbo,
            notes=notes,
        )


def evidence_window(samples: list[EventSample]) -> tuple[Optional[str], Optional[str]]:
    if not samples:
        return None, None
    return (
        min(row.sample_ts for row in samples).isoformat(),
        max(row.sample_ts for row in samples).isoformat(),
    )


__all__ = [
    "EventEvidenceEvaluator",
    "EventSample",
    "UnsupportedCandidateEvidence",
    "evidence_window",
    "load_evidence",
    "normalize_event_samples",
]
