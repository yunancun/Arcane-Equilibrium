"""Execution Realism Spine.

微結構 observation rows -> `aeg_execution_realism` gate input。
"""

from __future__ import annotations

import math
from typing import Any

from aeg_execution_realism import builder as execution_realism_builder


def _float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "filled", "pass"}


def _percentile(values: list[float], pct: float) -> float | None:
    clean = sorted(v for v in values if math.isfinite(v))
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    rank = (len(clean) - 1) * pct
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return clean[int(rank)]
    weight = rank - lo
    return clean[lo] * (1.0 - weight) + clean[hi] * weight


def build_execution_realism_input(
    *,
    observations: list[dict[str, Any]],
    candidate_id: str,
    strategy_family: str,
    parameter_cell_id: str,
    order_style: str,
    maker_fee_bps: float,
    taker_fee_bps: float,
    slippage_bps_p95: float | None = None,
    evidence_source_tier: str = "live_demo_fills",
    default_capacity_notional_usdt: float | None = None,
) -> dict[str, Any]:
    """把 observation rows 壓成既有 execution_realism gate payload。"""
    submitted = [row for row in observations if row.get("submitted", True) is not False]
    filled = [row for row in submitted if _bool(row.get("filled"))]
    adverse = [
        val for row in filled
        if (val := _float_or_none(row.get("adverse_selection_bps"))) is not None
    ]
    latencies = [
        val for row in submitted
        if (val := _float_or_none(row.get("latency_ms"))) is not None
    ]
    participation = [
        val for row in submitted
        if (val := _float_or_none(row.get("participation_rate"))) is not None
    ]
    capacities = [
        val for row in submitted
        if (val := _float_or_none(row.get("capacity_notional_usdt"))) is not None and val > 0
    ]
    slippage_values = [
        val for row in submitted
        if (val := _float_or_none(row.get("slippage_bps"))) is not None
    ]
    fill_rate = len(filled) / len(submitted) if submitted else None
    return {
        "candidate_id": candidate_id,
        "strategy_family": strategy_family,
        "parameter_cell_id": parameter_cell_id,
        "evidence_source_tier": evidence_source_tier,
        "order_style": order_style,
        "maker_fee_bps": maker_fee_bps,
        "taker_fee_bps": taker_fee_bps,
        "slippage_bps_p95": (
            slippage_bps_p95
            if slippage_bps_p95 is not None
            else _percentile(slippage_values, 0.95)
        ),
        "maker_fill_rate": fill_rate,
        "adverse_selection_bps_p95": _percentile(adverse, 0.95),
        "latency_ms_p95": _percentile(latencies, 0.95),
        "participation_rate_p95": _percentile(participation, 0.95),
        "sample_count": len(submitted),
        "capacity_notional_usdt": (
            min(capacities)
            if capacities
            else default_capacity_notional_usdt
        ),
        "order_availability_status": "PASS" if submitted else "FAIL",
        "notes": "alpha_discovery_throughput.execution_spine",
    }


def evaluate_execution_realism(**kwargs: Any) -> dict[str, Any]:
    """直接回既有 AEG execution_realism verdict。"""
    return execution_realism_builder.evaluate(build_execution_realism_input(**kwargs))


__all__ = ["build_execution_realism_input", "evaluate_execution_realism"]
