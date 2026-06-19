"""Alpha Candidate Packet Module.

這層把候選 producer 的 Interface 收斂為最小事件/收益 panel；Implementation
再轉成既有 `aeg_s3_candidate_rows` evidence dict。
"""

from __future__ import annotations

import datetime as dt
import math
from collections import defaultdict
from typing import Any

from aeg_s3_candidate_rows import builder as direct_rows_builder

from . import PACKET_SCHEMA_VERSION, RUNNER_VERSION
from .signal_manifest import validate_signal_manifest


def _float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_date(value: Any) -> str:
    raw = _text(value)
    if not raw:
        return ""
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(raw)
        return parsed.date().isoformat()
    except ValueError:
        try:
            return dt.date.fromisoformat(raw[:10]).isoformat()
        except ValueError:
            return ""


def normalize_sample(raw: dict[str, Any], idx: int) -> dict[str, Any]:
    """正規化單筆候選樣本；不補造缺失的 gate 欄位。"""
    date_value = raw.get("sample_ts_utc") or raw.get("sample_date") or raw.get("date")
    sample_date = _parse_date(date_value)
    sample_ts = _text(raw.get("sample_ts_utc")) or (f"{sample_date}T00:00:00Z" if sample_date else "")
    row = {
        "sample_id": _text(raw.get("sample_id")) or f"sample_{idx}",
        "sample_ts_utc": sample_ts,
        "sample_date": sample_date,
        "regime": _text(raw.get("regime")),
        "independence_bucket": _text(raw.get("independence_bucket")) or None,
        "gross_bps": _float_or_none(raw.get("gross_bps")),
        "cost_bps": _float_or_none(raw.get("cost_bps")),
        "net_bps": _float_or_none(raw.get("net_bps")),
        "is_oos": raw.get("is_oos"),
    }
    for key in ("symbol", "evidence_tier", "promotion_blocker", "parameter_cell_id"):
        if _text(raw.get(key)):
            row[key] = _text(raw.get(key))
    return row


def daily_returns_from_samples(samples: list[dict[str, Any]], *, unit: str = "bps") -> dict[str, Any]:
    """按 date 聚合 explicit sample net_bps；只用於 producer 明確要求時。"""
    by_date: dict[str, float] = defaultdict(float)
    regime_by_date: dict[str, str] = {}
    for row in samples:
        date_key = _text(row.get("sample_date")) or _parse_date(row.get("sample_ts_utc"))
        net = _float_or_none(row.get("net_bps"))
        if not date_key or net is None:
            continue
        by_date[date_key] += net if unit == "bps" else net / 1e4
        regime = _text(row.get("regime"))
        if regime:
            regime_by_date.setdefault(date_key, regime)
    return {
        "unit": unit,
        "regime_by_date": regime_by_date,
        "values": [
            {"date": day, "return": value, "regime": regime_by_date.get(day)}
            for day, value in sorted(by_date.items())
        ],
    }


def build_candidate_packet(
    *,
    candidate_id: str,
    strategy_family: str,
    parameter_cell_id: str,
    selected_variant: str,
    sample_unit: str,
    samples: list[dict[str, Any]],
    annualization_factor: float,
    k_trials: int,
    daily_returns: dict[str, Any] | None = None,
    pbo_candidates: dict[str, dict[str, float]] | None = None,
    signal_spec: dict[str, Any] | None = None,
    evidence_tier: str = "observed_research",
    promotion_blocker: str | None = None,
) -> dict[str, Any]:
    """候選 packet -> AEG direct rows evidence dict。"""
    normalized = [normalize_sample(row, idx) for idx, row in enumerate(samples)]
    spec_validation = validate_signal_manifest(signal_spec) if signal_spec is not None else {
        "ok": False,
        "verdict": "pending_schema",
        "reason": "signal_spec_missing",
        "reasons": ["signal_spec_missing"],
        "spec_hash": "",
    }
    packet: dict[str, Any] = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "candidate_id": str(candidate_id),
        "strategy_family": str(strategy_family),
        "parameter_cell_id": str(parameter_cell_id),
        "selected_variant": str(selected_variant),
        "sample_unit": str(sample_unit),
        "annualization_factor": float(annualization_factor),
        "k_trials": int(k_trials),
        "samples": normalized,
        "evidence_tier": evidence_tier,
        "signal_spec": signal_spec,
        "signal_spec_validation": spec_validation,
        "packet_status": "PASS" if normalized else "FAIL",
    }
    if daily_returns is not None:
        packet["daily_returns"] = daily_returns
    if pbo_candidates is not None:
        packet["pbo_candidates"] = pbo_candidates
    if promotion_blocker:
        packet["promotion_blocker"] = str(promotion_blocker)
        for row in packet["samples"]:
            row.setdefault("promotion_blocker", str(promotion_blocker))
    return packet


def build_direct_report_from_packet(packet: dict[str, Any], *, run_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """跨既有 AEG Seam：packet -> candidate direct report。"""
    report, summary, _sample_rows, _daily_rows = direct_rows_builder.build_direct_report(packet, run_id=run_id)
    return report, summary


__all__ = [
    "build_candidate_packet",
    "build_direct_report_from_packet",
    "daily_returns_from_samples",
    "normalize_sample",
]
