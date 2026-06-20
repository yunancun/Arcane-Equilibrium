"""MM maker-fee path feasibility reducers.

These helpers do not call Bybit and do not decide strategy promotion. They
combine observed fill-sim break-even fee evidence with local 30d fill capacity
so the operator can see whether the remaining blocker is signal quality, fee
tier, capital/scale, or an institutional rebate path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_CURRENT_MAKER_FEE_BPS_PER_SIDE = 2.0

# Bybit derivatives VIP fee ladder observed from official fee docs on
# 2026-06-20. Treat this as a monitoring default, not account authority:
# My Fee Rate / VIP Me is the source of truth for the actual account.
DEFAULT_BYBIT_DERIVATIVES_VIP_TIERS = (
    {
        "tier": "VIP0",
        "maker_fee_bps_per_side": 2.0,
        "volume_threshold_usd_30d": 0.0,
        "asset_balance_threshold_usd": 0.0,
    },
    {
        "tier": "VIP1",
        "maker_fee_bps_per_side": 1.8,
        "volume_threshold_usd_30d": 10_000_000.0,
        "asset_balance_threshold_usd": 100_000.0,
    },
    {
        "tier": "VIP2",
        "maker_fee_bps_per_side": 1.6,
        "volume_threshold_usd_30d": 25_000_000.0,
        "asset_balance_threshold_usd": 250_000.0,
    },
    {
        "tier": "VIP3",
        "maker_fee_bps_per_side": 1.4,
        "volume_threshold_usd_30d": 50_000_000.0,
        "asset_balance_threshold_usd": 500_000.0,
    },
    {
        "tier": "VIP4",
        "maker_fee_bps_per_side": 1.2,
        "volume_threshold_usd_30d": 100_000_000.0,
        "asset_balance_threshold_usd": 1_000_000.0,
    },
    {
        "tier": "VIP5",
        "maker_fee_bps_per_side": 1.0,
        "volume_threshold_usd_30d": 250_000_000.0,
        "asset_balance_threshold_usd": 2_000_000.0,
    },
    {
        "tier": "Supreme VIP",
        "maker_fee_bps_per_side": 0.0,
        "volume_threshold_usd_30d": 500_000_000.0,
        "asset_balance_threshold_usd": None,
    },
)


def _f(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def _r(value: Any, ndigits: int = 3) -> float | None:
    num = _f(value)
    if num is None:
        return None
    return round(num, ndigits)


def _capacity_notional(capacity_30d: dict[str, Any] | None) -> float:
    capacity_30d = capacity_30d or {}
    for key in ("notional_usd", "total_notional_usd", "gross_notional_usd"):
        val = _f(capacity_30d.get(key))
        if val is not None:
            return max(0.0, val)
    return 0.0


def _capacity_maker_notional(capacity_30d: dict[str, Any] | None) -> float:
    capacity_30d = capacity_30d or {}
    val = _f(capacity_30d.get("maker_notional_usd"))
    if val is None:
        return 0.0
    return max(0.0, val)


def _threshold_gap(current: float, threshold: float | None) -> dict[str, Any] | None:
    if threshold is None:
        return None
    threshold = max(0.0, float(threshold))
    if threshold <= 0:
        return {
            "threshold_usd": 0.0,
            "gap_usd": 0.0,
            "progress_pct": 100.0,
            "multiplier_needed": 1.0,
        }
    gap = max(0.0, threshold - current)
    progress_pct = min(100.0, (current / threshold) * 100.0) if threshold else 100.0
    multiplier = (threshold / current) if current > 0 else None
    return {
        "threshold_usd": _r(threshold, 2),
        "gap_usd": _r(gap, 2),
        "progress_pct": _r(progress_pct, 3),
        "multiplier_needed": _r(multiplier, 3) if multiplier is not None else None,
    }


def _extract_best_break_even_cell(scorecard: dict[str, Any] | None) -> dict[str, Any] | None:
    scorecard = scorecard or {}
    cell = scorecard.get("best_sample_gated_break_even_cell")
    if isinstance(cell, dict) and cell:
        return cell
    return None


def build_maker_fee_path_feasibility_scorecard(
    maker_fee_sensitivity_scorecard: dict[str, Any] | None,
    fee_capacity_30d: dict[str, Any] | None,
    *,
    vip_tiers=DEFAULT_BYBIT_DERIVATIVES_VIP_TIERS,
    current_maker_fee_bps_per_side: float = DEFAULT_CURRENT_MAKER_FEE_BPS_PER_SIDE,
) -> dict[str, Any]:
    """Combine fee sensitivity with local throughput capacity.

    `fee_capacity_30d` is a local execution capacity proxy only. Demo/live_demo
    rows do not prove Bybit mainnet VIP eligibility.
    """
    cell = _extract_best_break_even_cell(maker_fee_sensitivity_scorecard)
    current_notional = _capacity_notional(fee_capacity_30d)
    maker_notional = _capacity_maker_notional(fee_capacity_30d)
    out: dict[str, Any] = {
        "source": "maker_fee_sensitivity_scorecard + trading.fills 30d capacity proxy",
        "status": "NO_SAMPLE_GATED_BREAK_EVEN_CELL",
        "current_maker_fee_bps_per_side": _r(current_maker_fee_bps_per_side, 3),
        "capacity_30d": {
            "notional_usd": _r(current_notional, 2),
            "maker_notional_usd": _r(maker_notional, 2),
            "fills": (fee_capacity_30d or {}).get("fills"),
            "maker_fills": (fee_capacity_30d or {}).get("maker_fills"),
            "engine_mode_breakdown": (fee_capacity_30d or {}).get("by_engine_mode"),
            "proxy_warning": (
                "Local demo/live_demo fills are capacity proxy only; they are not "
                "Bybit mainnet VIP eligibility evidence."
            ),
        },
        "best_sample_gated_cell": cell,
        "break_even_maker_fee_bps_per_side": None,
        "fee_reduction_needed_bps_per_side": None,
        "standard_vip_tiers": [],
        "first_standard_vip_tier_clearing_break_even": None,
        "note": (
            "Research/business feasibility lens only. A positive fee tier still "
            "requires actual account eligibility, My Fee Rate verification, and "
            "cross-regime CP-3 evidence before any strategy work."
        ),
    }

    if not cell:
        return out

    break_even_fee = _f(cell.get("break_even_maker_fee_bps_per_side"))
    if break_even_fee is None:
        return out

    out["break_even_maker_fee_bps_per_side"] = _r(break_even_fee, 3)
    out["fee_reduction_needed_bps_per_side"] = _r(
        max(0.0, float(current_maker_fee_bps_per_side) - break_even_fee),
        3,
    )

    tier_rows = []
    first_clear = None
    for tier in vip_tiers:
        maker_fee = _f(tier.get("maker_fee_bps_per_side"))
        if maker_fee is None:
            continue
        clears = maker_fee <= break_even_fee
        row = {
            "tier": tier.get("tier"),
            "maker_fee_bps_per_side": _r(maker_fee, 3),
            "clears_break_even_fee": clears,
            "volume_30d": _threshold_gap(
                current_notional, tier.get("volume_threshold_usd_30d")
            ),
            "asset_balance": _threshold_gap(
                0.0, tier.get("asset_balance_threshold_usd")
            ),
        }
        tier_rows.append(row)
        if clears and first_clear is None and (tier.get("tier") or "") != "VIP0":
            first_clear = row

    out["standard_vip_tiers"] = tier_rows
    out["first_standard_vip_tier_clearing_break_even"] = first_clear

    current_clears = float(current_maker_fee_bps_per_side) <= break_even_fee
    if current_clears:
        out["status"] = "CURRENT_ACCOUNT_FEE_CLEARS_BREAK_EVEN"
    elif first_clear is not None:
        out["status"] = "STANDARD_VIP_TIER_CAN_CLEAR_BUT_SCALE_OR_CAPITAL_GATED"
    else:
        out["status"] = "NO_STANDARD_VIP_TIER_CLEARS_BREAK_EVEN"

    return out


__all__ = [
    "DEFAULT_BYBIT_DERIVATIVES_VIP_TIERS",
    "DEFAULT_CURRENT_MAKER_FEE_BPS_PER_SIDE",
    "build_maker_fee_path_feasibility_scorecard",
]
