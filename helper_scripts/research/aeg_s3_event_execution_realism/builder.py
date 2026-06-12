"""Aggregate empirical execution observations for AEG-S3 event candidates."""

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
    from . import RUNNER_VERSION
except ImportError:  # pragma: no cover
    _research = Path(__file__).resolve().parents[1]
    if str(_research) not in sys.path:
        sys.path.insert(0, str(_research))
    from aeg_s3_event_execution_realism import RUNNER_VERSION  # type: ignore

try:
    from aeg_s3_event_breadth.builder import (
        EventSample,
        UnsupportedCandidateEvidence,
        normalize_event_samples,
    )
except ImportError:  # pragma: no cover
    _research = Path(__file__).resolve().parents[1]
    if str(_research) not in sys.path:
        sys.path.insert(0, str(_research))
    from aeg_s3_event_breadth.builder import (  # type: ignore
        EventSample,
        UnsupportedCandidateEvidence,
        normalize_event_samples,
    )


@dataclass(frozen=True)
class ExecutionObservation:
    raw_index: int
    sample_id: Optional[str]
    symbol: Optional[str]
    sample_ts: Optional[dt.datetime]
    candidate_id: Optional[str]
    parameter_cell_id: Optional[str]
    evidence_source_tier: Optional[str]
    order_style: Optional[str]
    maker_fee_bps: Optional[float]
    taker_fee_bps: Optional[float]
    slippage_bps: Optional[float]
    maker_fill: Optional[bool]
    adverse_selection_bps: Optional[float]
    latency_ms: Optional[float]
    participation_rate: Optional[float]
    capacity_notional_usdt: Optional[float]
    order_available: Optional[bool]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            s = line.strip()
            if not s:
                continue
            obj = json.loads(s)
            if not isinstance(obj, dict):
                raise ValueError(f"invalid_jsonl_row:{line_no}")
            rows.append(obj)
    return rows


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return None


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
    if s in {"true", "1", "yes", "y", "pass", "passed", "available", "filled"}:
        return True
    if s in {"false", "0", "no", "n", "fail", "failed", "unavailable", "rejected"}:
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
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _percentile(values: list[float], q: float) -> Optional[float]:
    clean = sorted(v for v in values if math.isfinite(v))
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    pos = (len(clean) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return clean[int(pos)]
    weight = pos - lo
    return clean[lo] * (1.0 - weight) + clean[hi] * weight


def _mean_or_none(values: list[Optional[float]]) -> Optional[float]:
    clean = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    return statistics.mean(clean) if clean else None


def _normalize_style(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip().lower()
    if s in {"maker", "postonly", "post_only"}:
        return "maker"
    if s in {"taker", "market"}:
        return "taker"
    if s == "mixed":
        return "mixed"
    return s or None


def normalize_observation(raw: dict[str, Any], idx: int) -> ExecutionObservation:
    notional = _float_or_none(_first_present(raw, "notional_usdt", "order_notional_usdt"))
    market_notional = _float_or_none(_first_present(raw, "market_notional_usdt", "bucket_notional_usdt"))
    participation = _float_or_none(_first_present(raw, "participation_rate", "participation"))
    if participation is None and notional is not None and market_notional and market_notional > 0:
        participation = notional / market_notional
    return ExecutionObservation(
        raw_index=idx,
        sample_id=(
            str(_first_present(raw, "sample_id", "event_sample_id", "source_sample_id")).strip()
            if _first_present(raw, "sample_id", "event_sample_id", "source_sample_id") is not None
            else None
        ),
        symbol=(
            str(_first_present(raw, "symbol", "source_symbol", "event_symbol")).strip()
            if _first_present(raw, "symbol", "source_symbol", "event_symbol") is not None
            else None
        ),
        sample_ts=_parse_ts(_first_present(raw, "sample_ts_utc", "event_ts_utc", "signal_ts_utc")),
        candidate_id=(
            str(raw.get("candidate_id")).strip() if raw.get("candidate_id") is not None else None
        ),
        parameter_cell_id=(
            str(raw.get("parameter_cell_id")).strip()
            if raw.get("parameter_cell_id") is not None
            else None
        ),
        evidence_source_tier=(
            str(_first_present(raw, "evidence_source_tier", "source_tier")).strip().lower()
            if _first_present(raw, "evidence_source_tier", "source_tier") is not None
            else None
        ),
        order_style=_normalize_style(
            _first_present(raw, "order_style", "execution_order_style", "liquidity")
        ),
        maker_fee_bps=_float_or_none(_first_present(raw, "maker_fee_bps", "maker_fee_rate_bps")),
        taker_fee_bps=_float_or_none(_first_present(raw, "taker_fee_bps", "taker_fee_rate_bps")),
        slippage_bps=_float_or_none(_first_present(raw, "slippage_bps", "slippage_cost_bps")),
        maker_fill=_bool_or_none(_first_present(raw, "maker_fill", "is_maker_fill", "post_only_filled")),
        adverse_selection_bps=_float_or_none(
            _first_present(raw, "adverse_selection_bps", "adverse_selection_cost_bps")
        ),
        latency_ms=_float_or_none(_first_present(raw, "latency_ms", "submit_to_ack_ms", "round_trip_ms")),
        participation_rate=participation,
        capacity_notional_usdt=_float_or_none(
            _first_present(raw, "capacity_notional_usdt", "capacity_notional_usd")
        ),
        order_available=_bool_or_none(
            _first_present(raw, "order_available", "order_availability_status", "order_availability")
        ),
    )


def _event_indexes(samples: list[EventSample]) -> tuple[set[str], set[tuple[str, str]]]:
    sample_ids = {row.sample_id for row in samples}
    symbol_ts = {(row.symbol, row.sample_ts.isoformat()) for row in samples}
    return sample_ids, symbol_ts


def _matches_event(obs: ExecutionObservation, samples: list[EventSample]) -> bool:
    sample_ids, symbol_ts = _event_indexes(samples)
    if obs.sample_id and obs.sample_id in sample_ids:
        return True
    if obs.symbol and obs.sample_ts and (obs.symbol, obs.sample_ts.isoformat()) in symbol_ts:
        return True
    return False


def _resolve_source_tier(observations: list[ExecutionObservation], override: Optional[str]) -> str:
    if override:
        return override.strip().lower()
    tiers = {row.evidence_source_tier for row in observations if row.evidence_source_tier}
    return next(iter(tiers)) if len(tiers) == 1 else "missing"


def _resolve_order_style(observations: list[ExecutionObservation], override: Optional[str]) -> str:
    if override:
        return _normalize_style(override) or "missing"
    styles = {row.order_style for row in observations if row.order_style}
    if len(styles) == 1:
        return next(iter(styles)) or "missing"
    if styles and styles.issubset({"maker", "taker", "mixed"}):
        return "mixed"
    return "missing"


def _availability_status(observations: list[ExecutionObservation], override: Optional[str]) -> str:
    if override:
        parsed = _bool_or_none(override)
        if parsed is True:
            return "PASS"
        if parsed is False:
            return "FAIL"
    values = [row.order_available for row in observations if row.order_available is not None]
    if not values:
        return "MISSING"
    return "PASS" if all(values) else "FAIL"


def build_execution_input(
    *,
    candidate_evidence: dict[str, Any],
    observation_rows: list[dict[str, Any]],
    evidence_source_tier: Optional[str] = None,
    order_style: Optional[str] = None,
    capacity_notional_usdt: Optional[float] = None,
    order_availability_status: Optional[str] = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build raw `aeg_execution_realism` input from matched event observations."""
    valid_samples, rejected_samples = normalize_event_samples(candidate_evidence)
    candidate_id = str(candidate_evidence.get("candidate_id") or "").strip()
    parameter_cell_id = str(candidate_evidence.get("parameter_cell_id") or "").strip()

    observations = [
        normalize_observation(row, idx)
        for idx, row in enumerate(observation_rows)
        if isinstance(row, dict)
    ]
    matched: list[ExecutionObservation] = []
    reject_reasons: Counter[str] = Counter()
    for obs in observations:
        if obs.candidate_id and obs.candidate_id != candidate_id:
            reject_reasons["candidate_id_mismatch"] += 1
            continue
        if obs.parameter_cell_id and parameter_cell_id and obs.parameter_cell_id != parameter_cell_id:
            reject_reasons["parameter_cell_id_mismatch"] += 1
            continue
        if not _matches_event(obs, valid_samples):
            reject_reasons["unmatched_candidate_event_sample"] += 1
            continue
        matched.append(obs)

    maker_attempts = [
        row for row in matched
        if (row.order_style or _normalize_style(order_style)) in {"maker", "mixed"}
    ]
    maker_fill_values = [row.maker_fill for row in maker_attempts if row.maker_fill is not None]
    maker_fill_rate = (
        sum(1 for value in maker_fill_values if value) / len(maker_fill_values)
        if maker_fill_values
        else None
    )
    slippage_p95 = _percentile([abs(row.slippage_bps) for row in matched if row.slippage_bps is not None], 0.95)
    adverse_p95 = _percentile([
        max(row.adverse_selection_bps, 0.0)
        for row in matched
        if row.adverse_selection_bps is not None
    ], 0.95)
    latency_p95 = _percentile([row.latency_ms for row in matched if row.latency_ms is not None], 0.95)
    participation_p95 = _percentile([
        row.participation_rate for row in matched if row.participation_rate is not None
    ], 0.95)
    capacity = (
        capacity_notional_usdt
        if capacity_notional_usdt is not None
        else _mean_or_none([row.capacity_notional_usdt for row in matched])
    )

    notes = {
        "adapter_runner_version": RUNNER_VERSION,
        "policy": "matched_single_symbol_event_execution_observations_only",
        "candidate_sample_count": len(valid_samples),
        "candidate_rejected_sample_count": len(rejected_samples),
        "observation_row_count": len(observations),
        "matched_observation_count": len(matched),
        "rejected_observation_reasons": dict(sorted(reject_reasons.items())),
        "maker_attempt_count": len(maker_attempts),
        "maker_fill_observation_count": len(maker_fill_values),
    }
    payload = {
        "candidate_id": candidate_id,
        "strategy_family": candidate_evidence.get("strategy_family"),
        "parameter_cell_id": parameter_cell_id or None,
        "evidence_source_tier": _resolve_source_tier(matched, evidence_source_tier),
        "order_style": _resolve_order_style(matched, order_style),
        "maker_fee_bps": _mean_or_none([row.maker_fee_bps for row in matched]),
        "taker_fee_bps": _mean_or_none([row.taker_fee_bps for row in matched]),
        "slippage_bps_p95": slippage_p95,
        "maker_fill_rate": maker_fill_rate,
        "adverse_selection_bps_p95": adverse_p95,
        "latency_ms_p95": latency_p95,
        "participation_rate_p95": participation_p95,
        "sample_count": len(matched),
        "capacity_notional_usdt": capacity,
        "order_availability_status": _availability_status(matched, order_availability_status),
        "notes": notes,
    }
    summary = {
        "schema_version": "aeg.s3_event_execution_realism_summary.v0.1",
        "runner_version": RUNNER_VERSION,
        "candidate_id": candidate_id,
        "strategy_family": candidate_evidence.get("strategy_family"),
        "parameter_cell_id": parameter_cell_id or None,
        "candidate_sample_count": len(valid_samples),
        "observation_row_count": len(observations),
        "matched_observation_count": len(matched),
        "rejected_observation_reasons": dict(sorted(reject_reasons.items())),
        "raw_execution_input": payload,
    }
    return payload, summary


__all__ = [
    "ExecutionObservation",
    "UnsupportedCandidateEvidence",
    "build_execution_input",
    "load_json",
    "load_jsonl",
    "normalize_observation",
]
