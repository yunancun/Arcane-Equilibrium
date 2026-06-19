"""FlashDip counterfactual ladder packet builder."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from . import COUNTERFACTUAL_EVIDENCE_TIER, COUNTERFACTUAL_PROMOTION_BLOCKER
from .packet import build_candidate_packet


def _float(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _sample_date(row: dict[str, Any]) -> str:
    return _text(row.get("sample_date") or row.get("date"))[:10]


def build_flash_dip_ladder_packets(
    *,
    rows: list[dict[str, Any]],
    k_pcts: list[float],
    cost_bps: float,
    annualization_factor: float = 365.0,
    k_trials: int | None = None,
    candidate_id_prefix: str = "flash_dip_counterfactual",
    strategy_family: str = "flash_dip_buy",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Daily rows -> per-K counterfactual candidate packets。

    rows 需要包含 symbol/date/regime/prior_close/forward_low/exit_close。
    未觸發的 near-miss 只進 summary，不作收益樣本。
    """
    packets: list[dict[str, Any]] = []
    summary = {
        "evidence_tier": COUNTERFACTUAL_EVIDENCE_TIER,
        "promotion_blocker": COUNTERFACTUAL_PROMOTION_BLOCKER,
        "k_count": len(k_pcts),
        "rows_seen": len(rows),
        "filled_by_k": {},
        "near_miss_by_k": {},
    }
    for k_pct in k_pcts:
        samples: list[dict[str, Any]] = []
        near_misses = 0
        daily_net: dict[str, float] = defaultdict(float)
        regime_by_date: dict[str, str] = {}
        parameter_cell_id = f"k_{k_pct:g}pct"
        for idx, row in enumerate(rows):
            symbol = _text(row.get("symbol"))
            day = _sample_date(row)
            regime = _text(row.get("regime"))
            prior_close = _float(row.get("prior_close") or row.get("close"))
            forward_low = _float(row.get("forward_low") or row.get("low_after_entry") or row.get("low"))
            exit_close = _float(row.get("exit_close") or row.get("hold_close") or row.get("close_after_hold"))
            if not symbol or not day or prior_close is None or forward_low is None or exit_close is None:
                continue
            entry_px = prior_close * (1.0 - k_pct / 100.0)
            if forward_low > entry_px:
                near_misses += 1
                continue
            gross_bps = (exit_close / entry_px - 1.0) * 1e4
            net_bps = gross_bps - cost_bps
            sample = {
                "sample_id": f"{symbol}:{day}:k{k_pct:g}:{idx}",
                "sample_ts_utc": f"{day}T00:00:00Z",
                "sample_date": day,
                "symbol": symbol,
                "regime": regime,
                "independence_bucket": f"{symbol}:{day}:k{k_pct:g}",
                "gross_bps": gross_bps,
                "cost_bps": cost_bps,
                "net_bps": net_bps,
                "is_oos": row.get("is_oos"),
                "parameter_cell_id": parameter_cell_id,
                "evidence_tier": COUNTERFACTUAL_EVIDENCE_TIER,
                "promotion_blocker": COUNTERFACTUAL_PROMOTION_BLOCKER,
            }
            samples.append(sample)
            daily_net[day] += net_bps
            if regime:
                regime_by_date.setdefault(day, regime)
        summary["filled_by_k"][parameter_cell_id] = len(samples)
        summary["near_miss_by_k"][parameter_cell_id] = near_misses
        daily_returns = {
            "unit": "bps",
            "regime_by_date": regime_by_date,
            "values": [
                {"date": day, "return": value, "regime": regime_by_date.get(day)}
                for day, value in sorted(daily_net.items())
            ],
        }
        packets.append(build_candidate_packet(
            candidate_id=f"{candidate_id_prefix}_{parameter_cell_id}",
            strategy_family=strategy_family,
            parameter_cell_id=parameter_cell_id,
            selected_variant=parameter_cell_id,
            sample_unit="flash_dip_counterfactual_ladder",
            samples=samples,
            annualization_factor=annualization_factor,
            k_trials=k_trials if k_trials is not None else len(k_pcts),
            daily_returns=daily_returns,
            pbo_candidates=None,
            signal_spec=None,
            evidence_tier=COUNTERFACTUAL_EVIDENCE_TIER,
            promotion_blocker=COUNTERFACTUAL_PROMOTION_BLOCKER,
        ))
    return packets, summary


__all__ = ["build_flash_dip_ladder_packets"]
