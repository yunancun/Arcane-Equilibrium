#!/usr/bin/env python3
"""Build a low-friction MM motif amplification packet.

This module turns repeated near-miss motif history into a concrete search plan:
which motif to keep investigating, whether distinct-date history is still
missing, which train/holdout leg is the bottleneck, and how much gross-edge
uplift is needed to clear the current maker round trip.

It is artifact-only: no PG query/write, Bybit call, order placement, config /
risk / auth / runtime mutation, Cost Gate lowering, probe authority, or
promotion authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "mm_motif_amplification_packet_v1"
BOUNDARY = (
    "artifact-only MM motif amplification packet; no PG query/write, Bybit "
    "call, order, config, risk, auth, runtime mutation, Cost Gate lowering, "
    "probe authority, or promotion authority"
)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _round(value: Any, ndigits: int = 4) -> float | None:
    out = _float(value)
    return round(out, ndigits) if out is not None else None


def _current_fee_round_trip_bps(
    cell: dict[str, Any],
    explicit: float | None,
) -> float | None:
    if explicit is not None:
        return explicit
    holdout_gross = _float(cell.get("holdout_edge_before_fees_bps"))
    holdout_gap = _float(cell.get("gap_to_current_fee_round_trip_bps"))
    if holdout_gross is not None and holdout_gap is not None:
        return holdout_gross + holdout_gap
    for gross_key, net_key in (
        ("train_edge_before_fees_bps", "train_net_bps"),
        ("holdout_edge_before_fees_bps", "holdout_net_bps"),
    ):
        gross = _float(cell.get(gross_key))
        net = _float(cell.get(net_key))
        if gross is not None and net is not None:
            return gross - net
    return None


def _bottleneck_leg(train: float | None, holdout: float | None) -> str | None:
    if train is None and holdout is None:
        return None
    if train is None:
        return "train_missing"
    if holdout is None:
        return "holdout_missing"
    return "train" if train <= holdout else "holdout"


def _frontier_experiment_focus(bottleneck: str | None) -> str:
    if bottleneck == "train":
        return "lift_train_gross_edge_without_destroying_holdout_sample_gate"
    if bottleneck == "holdout":
        return "lift_holdout_gross_edge_without_overfitting_train_filters"
    if bottleneck in {"train_missing", "holdout_missing"}:
        return "restore_missing_train_holdout_leg_before_edge_claim"
    return "rank_same_motif_variants_by_min_train_holdout_gross"


def _motif_axes(motif_key: str) -> list[str]:
    parts = [part for part in motif_key.split("|") if part]
    return parts[1:] if parts[:1] == ["low_friction_motif"] else parts


def _candidate_record(
    row: dict[str, Any],
    *,
    current_fee_round_trip_bps: float | None,
    min_distinct_dates: int,
) -> dict[str, Any] | None:
    cell = _dict(row.get("best_cell"))
    motif_key = _str(row.get("motif_key") or cell.get("motif_key"))
    if not motif_key:
        return None

    train_gross = _float(cell.get("train_edge_before_fees_bps"))
    holdout_gross = _float(cell.get("holdout_edge_before_fees_bps"))
    gross_values = [value for value in (train_gross, holdout_gross) if value is not None]
    best_cell_min_train_holdout_gross = min(gross_values) if gross_values else None
    fee = _current_fee_round_trip_bps(cell, current_fee_round_trip_bps)
    dates = [str(item) for item in _list(row.get("distinct_window_dates")) if item]
    dates_remaining = max(0, min_distinct_dates - len(set(dates)))

    bottleneck = _bottleneck_leg(train_gross, holdout_gross)
    frontier = [
        item for item in _list(row.get("candidate_frontier"))
        if isinstance(item, dict)
    ][:10]
    frontier_summary = _dict(row.get("frontier_summary"))
    frontier_count = int(
        frontier_summary.get("candidate_count") or len(frontier) or 0
    )
    frontier_best_min_gross = _float(
        frontier_summary.get("best_min_train_holdout_gross_bps")
    )
    min_train_holdout_gross = best_cell_min_train_holdout_gross
    if frontier_best_min_gross is not None and (
        min_train_holdout_gross is None
        or frontier_best_min_gross > min_train_holdout_gross
    ):
        min_train_holdout_gross = frontier_best_min_gross
    min_gross_gap = (
        max(0.0, fee - min_train_holdout_gross)
        if fee is not None and min_train_holdout_gross is not None
        else None
    )
    required_uplift_multiple = (
        fee / min_train_holdout_gross
        if fee is not None
        and min_train_holdout_gross is not None
        and min_train_holdout_gross > 0.0
        else None
    )
    frontier_gap = (
        max(0.0, fee - frontier_best_min_gross)
        if fee is not None and frontier_best_min_gross is not None
        else None
    )
    if dates_remaining > 0:
        status = "MOTIF_REPEATS_DISTINCT_DATES_INSUFFICIENT"
        next_gate = "collect_repeated_motif_distinct_window_history"
        next_action = "accumulate_distinct_window_history_for_repeated_low_friction_motif"
    elif min_gross_gap is not None and min_gross_gap > 0.0:
        status = "MOTIF_REPEATS_EDGE_UPLIFT_REQUIRED"
        next_gate = "train_holdout_min_gross_edge_clears_current_fee"
        next_action = "search_same_motif_variants_for_train_holdout_edge_uplift"
    else:
        status = "MOTIF_REPEATS_READY_FOR_WALK_FORWARD_REVIEW"
        next_gate = "walk_forward_and_execution_realism_review"
        next_action = "run_walk_forward_and_execution_realism_review_for_repeated_motif"
    frontier_search_plan = {
        "status": (
            "MOTIF_FRONTIER_PRESENT"
            if frontier_count > 0 else "MOTIF_FRONTIER_NOT_EMITTED_BY_HISTORY"
        ),
        "frontier_candidate_count": frontier_count,
        "frontier_best_min_gross_key": frontier_summary.get("best_min_gross_key"),
        "frontier_best_min_train_holdout_gross_bps": _round(frontier_best_min_gross),
        "frontier_gap_to_current_fee_bps": _round(frontier_gap),
        "frontier_best_train_key": frontier_summary.get("best_train_key"),
        "frontier_best_train_gross_bps": _round(
            frontier_summary.get("best_train_gross_bps")
        ),
        "frontier_best_holdout_key": frontier_summary.get("best_holdout_key"),
        "frontier_best_holdout_gross_bps": _round(
            frontier_summary.get("best_holdout_gross_bps")
        ),
        "experiment_focus": _frontier_experiment_focus(bottleneck),
    }
    return {
        "motif_key": motif_key,
        "motif_axes": _motif_axes(motif_key),
        "status": status,
        "candidate_keys": row.get("candidate_keys") or [],
        "candidate_frontier": frontier,
        "frontier_summary": frontier_summary,
        "frontier_search_plan": frontier_search_plan,
        "windows": row.get("windows"),
        "distinct_window_dates": dates,
        "min_distinct_dates": min_distinct_dates,
        "distinct_dates_remaining": dates_remaining,
        "best_condition": cell.get("condition") or cell.get("name"),
        "best_candidate_shape": cell.get("candidate_shape"),
        "threshold_source": cell.get("threshold_source"),
        "train_gross_edge_bps": _round(train_gross),
        "holdout_gross_edge_bps": _round(holdout_gross),
        "best_cell_min_train_holdout_gross_bps": _round(
            best_cell_min_train_holdout_gross
        ),
        "min_train_holdout_gross_bps": _round(min_train_holdout_gross),
        "current_fee_round_trip_bps": _round(fee),
        "min_gross_gap_to_current_fee_bps": _round(min_gross_gap),
        "required_uplift_multiple": (
            _round(required_uplift_multiple)
            if required_uplift_multiple is not None and required_uplift_multiple > 1.0
            else None
        ),
        "bottleneck_leg": bottleneck,
        "search_constraint": (
            "preserve_repeated_motif_axes_and_require_train_holdout_sample_gated_"
            "min_gross_ge_current_fee_round_trip"
        ),
        "suggested_search_focus": (
            f"amplify_{bottleneck or 'unknown'}_leg_within_repeated_low_friction_motif"
        ),
        "required_next_gate": next_gate,
        "next_action": next_action,
        "order_authority": "NOT_GRANTED",
        "main_cost_gate_adjustment": "NONE",
        "promotion_evidence": False,
    }


def build_mm_motif_amplification_packet(
    *,
    fillsim_history: dict[str, Any] | None,
    current_fee_round_trip_bps: float | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    history = _dict(fillsim_history)
    stability = _dict(history.get("low_friction_near_miss_motif_stability"))
    min_distinct_dates = int(stability.get("min_distinct_dates") or 3)
    raw_rows = _list(stability.get("top_repeated_near_miss_motifs"))
    if not raw_rows and isinstance(stability.get("best_repeated_near_miss_motif"), dict):
        raw_rows = [stability["best_repeated_near_miss_motif"]]

    candidates = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            continue
        record = _candidate_record(
            raw,
            current_fee_round_trip_bps=current_fee_round_trip_bps,
            min_distinct_dates=min_distinct_dates,
        )
        if record is not None:
            candidates.append(record)
    candidates.sort(key=lambda row: (
        row.get("distinct_dates_remaining") or 0,
        row.get("min_gross_gap_to_current_fee_bps")
        if row.get("min_gross_gap_to_current_fee_bps") is not None
        else 9999.0,
        -(row.get("windows") or 0),
    ))
    for index, row in enumerate(candidates, start=1):
        row["rank"] = index

    if not candidates:
        status = "NO_REPEATED_LOW_FRICTION_MOTIF_FOR_AMPLIFICATION"
        next_action = "continue_collecting_low_friction_near_miss_history"
    elif any((row.get("distinct_dates_remaining") or 0) > 0 for row in candidates):
        status = "MM_MOTIF_AMPLIFICATION_REQUIRES_DISTINCT_DATE_HISTORY"
        next_action = "accumulate_distinct_window_history_for_repeated_low_friction_motif"
    elif any((row.get("min_gross_gap_to_current_fee_bps") or 0.0) > 0.0 for row in candidates):
        status = "MM_MOTIF_AMPLIFICATION_EDGE_UPLIFT_REQUIRED"
        next_action = "search_same_motif_variants_for_train_holdout_edge_uplift"
    else:
        status = "MM_MOTIF_AMPLIFICATION_READY_FOR_WALK_FORWARD_REVIEW"
        next_action = "run_walk_forward_and_execution_realism_review_for_repeated_motif"

    top = candidates[0] if candidates else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": "low_friction_near_miss_motifs_ranked_for_edge_amplification",
        "next_action": next_action,
        "source": {
            "history_status": history.get("status"),
            "history_valid_windows": history.get("valid_windows"),
            "history_distinct_window_dates": history.get("distinct_window_dates"),
            "near_miss_motif_stability_status": stability.get("status"),
            "near_miss_motif_stability_reason": stability.get("reason"),
        },
        "summary": {
            "candidate_count": len(candidates),
            "top_motif_key": top.get("motif_key"),
            "top_status": top.get("status"),
            "top_bottleneck_leg": top.get("bottleneck_leg"),
            "top_min_train_holdout_gross_bps": top.get("min_train_holdout_gross_bps"),
            "top_min_gross_gap_to_current_fee_bps": (
                top.get("min_gross_gap_to_current_fee_bps")
            ),
            "top_required_uplift_multiple": top.get("required_uplift_multiple"),
            "top_distinct_dates_remaining": top.get("distinct_dates_remaining"),
            "top_frontier_candidate_count": (
                _dict(top.get("frontier_search_plan")).get("frontier_candidate_count")
            ),
            "top_frontier_best_min_gross_key": (
                _dict(top.get("frontier_search_plan")).get("frontier_best_min_gross_key")
            ),
            "top_frontier_best_min_train_holdout_gross_bps": (
                _dict(top.get("frontier_search_plan")).get(
                    "frontier_best_min_train_holdout_gross_bps"
                )
            ),
            "top_frontier_gap_to_current_fee_bps": (
                _dict(top.get("frontier_search_plan")).get(
                    "frontier_gap_to_current_fee_bps"
                )
            ),
            "top_frontier_experiment_focus": (
                _dict(top.get("frontier_search_plan")).get("experiment_focus")
            ),
        },
        "top_candidate": top or None,
        "candidates": candidates,
        "answers": {
            "motif_amplification_candidate_present": bool(candidates),
            "motif_current_fee_proven": bool(
                candidates
                and (top.get("min_gross_gap_to_current_fee_bps") in {0, 0.0})
                and (top.get("distinct_dates_remaining") in {0, None})
            ),
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "order_authority_granted": False,
            "probe_authority_granted": False,
            "promotion_evidence": False,
        },
        "global_boundaries": {
            "order_authority": "NOT_GRANTED",
            "probe_authority": "NOT_GRANTED",
            "main_cost_gate_adjustment": "NONE",
            "runtime_mutation": "NONE",
            "promotion_evidence": False,
            "boundary": BOUNDARY,
        },
    }


def render_markdown(packet: dict[str, Any]) -> str:
    def cell(value: Any) -> str:
        return str(value).replace("|", "\\|")

    lines = [
        "# MM Motif Amplification Packet",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Next action: `{packet.get('next_action')}`",
        "- Boundary: artifact-only; no order authority, no probe authority, no Cost Gate lowering.",
        "",
        "## Summary",
        "",
        "| field | value |",
        "|---|---|",
    ]
    for key, value in _dict(packet.get("summary")).items():
        lines.append(f"| {key} | `{value}` |")

    lines.extend([
        "",
        "## Candidates",
        "",
        "| rank | motif | status | bottleneck | min_gross_bps | gap_bps | uplift_multiple | dates_remaining | next gate |",
        "|---:|---|---|---|---:|---:|---:|---:|---|",
    ])
    for row in _list(packet.get("candidates")):
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            f"{row.get('rank')} | {cell(row.get('motif_key'))} | {cell(row.get('status'))} | "
            f"{cell(row.get('bottleneck_leg'))} | {row.get('min_train_holdout_gross_bps')} | "
            f"{row.get('min_gross_gap_to_current_fee_bps')} | {row.get('required_uplift_multiple')} | "
            f"{row.get('distinct_dates_remaining')} | {cell(row.get('required_next_gate'))} |"
        )
    return "\n".join(lines) + "\n"


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fillsim-history-json", type=Path, required=True)
    parser.add_argument("--current-fee-round-trip-bps", type=float)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_mm_motif_amplification_packet(
        fillsim_history=_read_json(args.fillsim_history_json),
        current_fee_round_trip_bps=args.current_fee_round_trip_bps,
    )
    if args.output:
        _write_text(args.output, render_markdown(packet))
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True, default=str))
    if not (args.output or args.json_output or args.print_json):
        print(render_markdown(packet), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
