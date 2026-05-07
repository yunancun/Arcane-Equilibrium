"""Replay report analytics overlays for REF-21 C3.

The analytics are derived only from the immutable replay report payload. They
are advisory diagnostics, not promotion, handoff, or live mutation signals.
"""

from __future__ import annotations

import math
from statistics import median
from typing import Any


def build_replay_result_analytics(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    if not isinstance(result, dict):
        return _empty_analytics("payload_missing_result")
    fills = result.get("fills")
    if not isinstance(fills, list):
        fills = []
    pnl = result.get("pnl_summary") if isinstance(result.get("pnl_summary"), dict) else {}
    diagnostics = (
        result.get("diagnostics")
        if isinstance(result.get("diagnostics"), dict)
        else {}
    )
    starting_balance = _finite_float(pnl.get("starting_balance"))
    net_pnl = _finite_float(pnl.get("net_pnl"))
    fees = [_finite_float(fill.get("fee")) or 0.0 for fill in fills if isinstance(fill, dict)]
    total_fee = sum(fees)
    positive_fills = [
        fill for fill in fills
        if isinstance(fill, dict) and (_finite_float(fill.get("qty")) or 0.0) > 0.0
    ]
    ghost_fills = [
        fill for fill in fills
        if isinstance(fill, dict) and (_finite_float(fill.get("qty")) or 0.0) <= 0.0
    ]
    maker_miss_count = sum(
        1 for fill in ghost_fills
        if str(fill.get("liquidity_role") or "").lower() == "maker"
    )
    risk_reject_count = max(0, len(ghost_fills) - maker_miss_count)
    notional_values = [
        abs((_finite_float(fill.get("qty")) or 0.0) * (_finite_float(fill.get("price")) or 0.0))
        for fill in positive_fills
    ]
    gross_notional = sum(notional_values)
    slippage_values = [
        _finite_float(fill.get("slippage_bps"))
        for fill in positive_fills
        if _finite_float(fill.get("slippage_bps")) is not None
    ]
    net_bps = (
        (net_pnl / starting_balance) * 10_000.0
        if starting_balance and net_pnl is not None
        else None
    )
    fee_bps = (
        (total_fee / gross_notional) * 10_000.0
        if gross_notional > 0.0
        else None
    )
    reject_rate = len(ghost_fills) / len(fills) if fills else 0.0
    verdict = _development_verdict(
        fill_count=len(positive_fills),
        net_bps=net_bps,
        diagnostics=diagnostics,
    )
    return {
        "schema_version": 1,
        "verdict": verdict,
        "net_bps_after_fee": net_bps,
        "net_pnl": net_pnl,
        "starting_balance": starting_balance,
        "ending_balance": _finite_float(pnl.get("ending_balance")),
        "fill_count": len(positive_fills),
        "ghost_fill_count": len(ghost_fills),
        "maker_miss_count": maker_miss_count,
        "risk_reject_count": risk_reject_count,
        "reject_or_miss_rate": reject_rate,
        "total_fee": total_fee,
        "gross_notional": gross_notional,
        "fee_bps_on_notional": fee_bps,
        "slippage_bps_q50": median(slippage_values) if slippage_values else None,
        "max_drawdown_bps": None,
        "drawdown_status": "unavailable_without_balance_curve",
        "run_band_status": "single_run_no_bootstrap",
        "baseline_comparison_status": "not_configured",
        "reason_codes": _reason_codes(
            fill_count=len(positive_fills),
            net_bps=net_bps,
            diagnostics=diagnostics,
        ),
    }


def overlay_artifact_payload_analytics(artifact: dict[str, Any]) -> None:
    payload = artifact.get("payload")
    if not isinstance(payload, dict):
        return
    analytics = build_replay_result_analytics(payload)
    payload["replay_result_analytics"] = analytics
    result = payload.get("result")
    if isinstance(result, dict):
        result["replay_result_analytics"] = analytics


def _empty_analytics(reason: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "verdict": "needs_more_data",
        "reason_codes": [reason],
        "net_bps_after_fee": None,
        "fill_count": 0,
        "ghost_fill_count": 0,
        "maker_miss_count": 0,
        "risk_reject_count": 0,
        "reject_or_miss_rate": 0.0,
        "drawdown_status": "unavailable_without_balance_curve",
        "run_band_status": "single_run_no_bootstrap",
        "baseline_comparison_status": "not_configured",
    }


def _finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _development_verdict(
    *,
    fill_count: int,
    net_bps: float | None,
    diagnostics: dict[str, Any],
) -> str:
    if diagnostics.get("abort_reason"):
        return "needs_more_data"
    if fill_count <= 0:
        return "needs_more_data"
    if net_bps is None:
        return "needs_more_data"
    return "development_sandbox_pass" if net_bps >= 0.0 else "development_sandbox_fail"


def _reason_codes(
    *,
    fill_count: int,
    net_bps: float | None,
    diagnostics: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if diagnostics.get("abort_reason"):
        reasons.append("replay_aborted")
    if fill_count <= 0:
        reasons.append("no_positive_qty_fills")
    if net_bps is None:
        reasons.append("net_bps_unavailable")
    if not reasons:
        reasons.append("single_run_in_sample_sandbox")
    return reasons


__all__ = [
    "build_replay_result_analytics",
    "overlay_artifact_payload_analytics",
]
