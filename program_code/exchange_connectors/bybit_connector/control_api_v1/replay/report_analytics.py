"""Replay report analytics overlays for REF-21 C3.

The analytics are derived only from the immutable replay report payload. They
are advisory diagnostics, not promotion, handoff, or live mutation signals.
"""

from __future__ import annotations

import math
from statistics import median
from typing import Any


def build_replay_result_analytics(payload: dict[str, Any]) -> dict[str, Any]:
    return _build_replay_result_analytics(payload, include_baseline=True)


def compare_replay_analytics(
    *,
    baseline: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
) -> dict[str, Any]:
    baseline_metrics = _normalise_analytics_input(baseline)
    candidate_metrics = _normalise_analytics_input(candidate)
    if not baseline_metrics or not candidate_metrics:
        return {
            "schema_version": 1,
            "status": "insufficient_data",
            "verdict": "comparison_unavailable",
            "reason_codes": ["baseline_or_candidate_missing"],
        }

    baseline_net = _finite_float(baseline_metrics.get("net_bps_after_fee"))
    candidate_net = _finite_float(candidate_metrics.get("net_bps_after_fee"))
    if baseline_net is None or candidate_net is None:
        return {
            "schema_version": 1,
            "status": "insufficient_data",
            "verdict": "comparison_unavailable",
            "baseline_net_bps_after_fee": baseline_net,
            "candidate_net_bps_after_fee": candidate_net,
            "reason_codes": ["net_bps_missing"],
        }

    baseline_dd = _finite_float(baseline_metrics.get("max_drawdown_bps"))
    candidate_dd = _finite_float(candidate_metrics.get("max_drawdown_bps"))
    delta_net = candidate_net - baseline_net
    delta_drawdown = (
        candidate_dd - baseline_dd
        if candidate_dd is not None and baseline_dd is not None
        else None
    )
    delta_reject = (
        (_finite_float(candidate_metrics.get("reject_or_miss_rate")) or 0.0)
        - (_finite_float(baseline_metrics.get("reject_or_miss_rate")) or 0.0)
    )
    verdict = "candidate_flat"
    if delta_net >= 5.0 and (delta_drawdown is None or delta_drawdown <= 25.0):
        verdict = "candidate_better"
    elif delta_net <= -5.0 or (delta_drawdown is not None and delta_drawdown > 50.0):
        verdict = "candidate_worse"
    return {
        "schema_version": 1,
        "status": "computed",
        "verdict": verdict,
        "baseline_net_bps_after_fee": baseline_net,
        "candidate_net_bps_after_fee": candidate_net,
        "delta_net_bps_after_fee": delta_net,
        "baseline_max_drawdown_bps": baseline_dd,
        "candidate_max_drawdown_bps": candidate_dd,
        "delta_max_drawdown_bps": delta_drawdown,
        "delta_fill_count": (
            int(candidate_metrics.get("fill_count") or 0)
            - int(baseline_metrics.get("fill_count") or 0)
        ),
        "delta_reject_or_miss_rate": delta_reject,
        "reason_codes": ["baseline_candidate_comparison"],
    }


def _build_replay_result_analytics(
    payload: dict[str, Any],
    *,
    include_baseline: bool,
) -> dict[str, Any]:
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
    curve = _build_balance_curve(
        fills=fills,
        starting_balance=starting_balance,
        reported_net_pnl=net_pnl,
    )
    bands = _stationary_block_bootstrap_bands(
        curve.get("balance_delta_bps_series")
        if isinstance(curve.get("balance_delta_bps_series"), list)
        else []
    )
    analytics = {
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
        "max_drawdown_bps": curve.get("max_drawdown_bps"),
        "drawdown_status": curve.get("status"),
        "balance_curve": curve.get("points"),
        "balance_curve_point_count": len(curve.get("points") or []),
        "balance_curve_reconciliation_delta": curve.get("reconciliation_delta"),
        "run_band_status": bands.get("status"),
        "run_bands_bps": bands.get("run_bands_bps"),
        "baseline_comparison_status": "not_configured",
        "reason_codes": _reason_codes(
            fill_count=len(positive_fills),
            net_bps=net_bps,
            diagnostics=diagnostics,
        ),
    }
    if include_baseline:
        baseline_payload = _extract_baseline_payload(payload, result)
        if baseline_payload is not None:
            comparison = compare_replay_analytics(
                baseline=baseline_payload,
                candidate=analytics,
            )
            analytics["baseline_comparison_status"] = comparison.get("status")
            analytics["baseline_comparison"] = comparison
            if comparison.get("status") == "computed":
                analytics["baseline_delta_net_bps_after_fee"] = comparison.get(
                    "delta_net_bps_after_fee"
                )
    return analytics


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


def _normalise_analytics_input(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    if "net_bps_after_fee" in value or "max_drawdown_bps" in value:
        return value
    return _build_replay_result_analytics(value, include_baseline=False)


def _extract_baseline_payload(
    payload: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any] | None:
    for key in (
        "baseline_payload",
        "baseline_report_payload",
        "baseline_replay_result",
        "baseline_result",
    ):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    for key in ("baseline_payload", "baseline_report_payload", "baseline_result"):
        value = result.get(key)
        if isinstance(value, dict):
            return value
    return None


def _build_balance_curve(
    *,
    fills: list[Any],
    starting_balance: float | None,
    reported_net_pnl: float | None,
) -> dict[str, Any]:
    if starting_balance is None or starting_balance <= 0.0:
        return {
            "status": "unavailable_without_starting_balance",
            "points": [],
            "max_drawdown_bps": None,
            "balance_delta_bps_series": [],
            "reconciliation_delta": None,
        }
    sortable: list[tuple[int, int, dict[str, Any]]] = []
    for idx, fill in enumerate(fills):
        if not isinstance(fill, dict):
            continue
        qty = _finite_float(fill.get("qty")) or 0.0
        if qty <= 0.0:
            continue
        ts = _finite_float(fill.get("effective_ts_ms"))
        if ts is None:
            ts = _finite_float(fill.get("ts_ms"))
        sortable.append((int(ts or 0), idx, fill))
    if not sortable:
        return {
            "status": "unavailable_without_positive_fills",
            "points": [{"ts_ms": None, "balance": starting_balance, "delta": 0.0}],
            "max_drawdown_bps": 0.0,
            "balance_delta_bps_series": [],
            "reconciliation_delta": (
                reported_net_pnl if reported_net_pnl is not None else None
            ),
        }

    sortable.sort(key=lambda item: (item[0], item[1]))
    balance = starting_balance
    peak = starting_balance
    max_dd_bps = 0.0
    positions: dict[str, dict[str, float]] = {}
    points = [{"ts_ms": sortable[0][0], "balance": balance, "delta": 0.0}]
    delta_bps_series: list[float] = []
    for ts_ms, _idx, fill in sortable:
        delta = _realized_balance_delta(fill, positions)
        balance += delta
        peak = max(peak, balance)
        if peak > 0.0:
            max_dd_bps = max(max_dd_bps, ((peak - balance) / peak) * 10_000.0)
        delta_bps = (delta / starting_balance) * 10_000.0
        delta_bps_series.append(delta_bps)
        points.append({
            "ts_ms": ts_ms,
            "balance": balance,
            "delta": delta,
        })
    expected_end = (
        starting_balance + reported_net_pnl
        if reported_net_pnl is not None
        else None
    )
    reconciliation_delta = (
        expected_end - balance
        if expected_end is not None
        else None
    )
    return {
        "status": "computed_from_fill_sequence",
        "points": points,
        "max_drawdown_bps": max_dd_bps,
        "balance_delta_bps_series": delta_bps_series,
        "reconciliation_delta": reconciliation_delta,
    }


def _realized_balance_delta(
    fill: dict[str, Any],
    positions: dict[str, dict[str, float]],
) -> float:
    symbol = str(fill.get("symbol") or "").upper()
    if not symbol:
        return 0.0
    qty = _finite_float(fill.get("qty")) or 0.0
    price = _finite_float(fill.get("price")) or 0.0
    fee = _finite_float(fill.get("fee")) or 0.0
    if qty <= 0.0 or price <= 0.0:
        return -fee
    side = str(fill.get("side") or "").lower()
    signed_qty = qty if side == "long" else -qty
    pos = positions.get(symbol, {"qty": 0.0, "avg_price": 0.0})
    pos_qty = pos["qty"]
    avg = pos["avg_price"]
    delta = -fee
    if pos_qty == 0.0 or (pos_qty > 0.0) == (signed_qty > 0.0):
        new_abs = abs(pos_qty) + abs(signed_qty)
        if new_abs > 0.0:
            pos["avg_price"] = (
                (avg * abs(pos_qty)) + (price * abs(signed_qty))
            ) / new_abs
        pos["qty"] = pos_qty + signed_qty
        positions[symbol] = pos
        return delta

    close_qty = min(abs(pos_qty), abs(signed_qty))
    if pos_qty > 0.0:
        delta += (price - avg) * close_qty
    else:
        delta += (avg - price) * close_qty
    remaining_pos = pos_qty + signed_qty
    if abs(remaining_pos) < 1e-12:
        positions.pop(symbol, None)
    elif (remaining_pos > 0.0) == (pos_qty > 0.0):
        pos["qty"] = remaining_pos
        positions[symbol] = pos
    else:
        positions[symbol] = {"qty": remaining_pos, "avg_price": price}
    return delta


def _stationary_block_bootstrap_bands(series: list[Any]) -> dict[str, Any]:
    values = [_finite_float(value) for value in series]
    values = [value for value in values if value is not None]
    n = len(values)
    if n < 2:
        return {
            "status": "insufficient_samples_for_block_bootstrap",
            "run_bands_bps": None,
        }
    block_size = max(1, min(24, int(round(math.sqrt(n)))))
    iterations = 1_000
    state = 0xC0FFEE1234
    totals: list[float] = []

    def rnd() -> float:
        nonlocal state
        state = (
            (state * 6364136223846793005 + 1442695040888963407)
            & ((1 << 64) - 1)
        )
        return state / float(1 << 64)

    reset_p = 1.0 / float(block_size)
    for _ in range(iterations):
        idx = int(rnd() * n) % n
        total = 0.0
        for _step in range(n):
            total += values[idx]
            if rnd() < reset_p:
                idx = int(rnd() * n) % n
            else:
                idx = (idx + 1) % n
        totals.append(total)
    totals.sort()
    return {
        "status": "stationary_block_bootstrap",
        "run_bands_bps": {
            "q10": _quantile_sorted(totals, 0.10),
            "q50": _quantile_sorted(totals, 0.50),
            "q90": _quantile_sorted(totals, 0.90),
            "n_iter": iterations,
            "block_size": block_size,
            "sample_count": n,
            "method": "stationary_block_bootstrap",
        },
    }


def _quantile_sorted(values: list[float], q: float) -> float | None:
    if not values:
        return None
    idx = min(len(values) - 1, max(0, int(round((len(values) - 1) * q))))
    return values[idx]


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
    "compare_replay_analytics",
    "overlay_artifact_payload_analytics",
]
