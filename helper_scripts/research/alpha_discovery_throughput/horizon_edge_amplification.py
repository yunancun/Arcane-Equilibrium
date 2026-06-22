#!/usr/bin/env python3
"""Build a horizon-specific edge amplification packet.

The Cost Gate counterfactual can show the same side-cell as blocked on one
holding horizon and profitable on another. This module turns that observation
into a ranked artifact for replay/probe review.

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


SCHEMA_VERSION = "horizon_edge_amplification_packet_v1"
BOUNDARY = (
    "artifact-only horizon edge amplification packet; no PG query/write, "
    "Bybit call, order, config, risk, auth, runtime mutation, Cost Gate "
    "lowering, probe authority, or promotion authority"
)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


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


def _primary_horizon_row(row: dict[str, Any], primary_horizon_minutes: int | None) -> dict[str, Any]:
    if primary_horizon_minutes is None:
        return {}
    for item in _list(row.get("horizon_rows")):
        if isinstance(item, dict) and _int(item.get("horizon_minutes")) == primary_horizon_minutes:
            return item
    return {}


def _status_class(row: dict[str, Any], primary_horizon_minutes: int | None = None) -> str:
    status = _str(row.get("status"))
    candidates = _list(row.get("candidate_horizons"))
    blocks = _list(row.get("block_confirmed_horizons"))
    primary_in_candidates = (
        primary_horizon_minutes is not None
        and primary_horizon_minutes in {_int(item) for item in candidates}
    )
    primary_in_blocks = (
        primary_horizon_minutes is not None
        and primary_horizon_minutes in {_int(item) for item in blocks}
    )
    if status == "CANDIDATE_MULTI_HORIZON_STABLE" and len(candidates) >= 2:
        return "STABLE_MULTI_HORIZON_CANDIDATE"
    if status == "MIXED_HORIZON_RESPONSE" and candidates and blocks:
        if primary_in_blocks:
            return "RETIMING_CANDIDATE"
        if primary_in_candidates:
            return "MIXED_HORIZON_GUARD_CANDIDATE"
        return "RETIMING_CANDIDATE"
    if candidates:
        return "SINGLE_HORIZON_CANDIDATE"
    return "NOT_HORIZON_EDGE_CANDIDATE"


def _candidate_priority(row: dict[str, Any]) -> tuple[int, float, int]:
    raw_status = _str(row.get("status"))
    status_rank = {
        "RETIMING_CANDIDATE": 0,
        "STABLE_MULTI_HORIZON_CANDIDATE": 1,
        "MIXED_HORIZON_GUARD_CANDIDATE": 2,
        "SINGLE_HORIZON_CANDIDATE": 3,
    }
    rank_key = raw_status if raw_status in status_rank else _status_class(row)
    edge = _float(row.get("best_avg_net_bps")) or -9999.0
    sample = _int(row.get("best_sample_count_for_gate") or row.get("best_distinct_ts"))
    return (status_rank.get(rank_key, 9), -edge, -sample)


def _candidate_record(
    row: dict[str, Any],
    *,
    primary_horizon_minutes: int | None,
    friction_bps: float,
) -> dict[str, Any] | None:
    status_class = _status_class(row, primary_horizon_minutes)
    if status_class == "NOT_HORIZON_EDGE_CANDIDATE":
        return None

    primary = _primary_horizon_row(row, primary_horizon_minutes)
    best_net = _float(row.get("best_avg_net_bps"))
    primary_net = _float(primary.get("avg_net_bps"))
    edge_amplification = (
        best_net - primary_net
        if best_net is not None and primary_net is not None
        else None
    )
    best_sample = _int(row.get("best_sample_count_for_gate") or row.get("best_distinct_ts"))
    best_horizon = _int(row.get("best_horizon_minutes"))
    candidate_horizons = [_int(item) for item in _list(row.get("candidate_horizons"))]
    blocked_horizons = [_int(item) for item in _list(row.get("block_confirmed_horizons"))]
    if status_class == "RETIMING_CANDIDATE":
        next_gate = "sealed_horizon_specific_replay_before_bounded_demo_probe"
        next_action = "build_horizon_specific_replay_for_best_horizon_then_operator_review"
    elif status_class == "MIXED_HORIZON_GUARD_CANDIDATE":
        next_gate = "sealed_primary_horizon_replay_with_blocked_horizon_guard"
        next_action = "build_primary_horizon_replay_and_guard_blocked_horizons_then_operator_review"
    else:
        next_gate = "bounded_demo_learning_probe_after_learning_stack_accumulates"
        next_action = "operator_review_stable_side_cell_after_learning_stack_accumulates"

    return {
        "side_cell_key": row.get("side_cell_key"),
        "status": status_class,
        "source_status": row.get("status"),
        "best_horizon_minutes": best_horizon,
        "candidate_horizons_minutes": candidate_horizons,
        "blocked_horizons_minutes": blocked_horizons,
        "observed_horizons_minutes": [_int(item) for item in _list(row.get("observed_horizons"))],
        "primary_horizon_minutes": primary_horizon_minutes,
        "primary_horizon_action": primary.get("learning_lane_action"),
        "primary_horizon_net_bps": _round(primary_net),
        "best_net_bps": _round(best_net),
        "best_net_positive_pct": _round(row.get("best_net_positive_pct")),
        "best_p50_gross_bps": _round(row.get("best_p50_gross_bps")),
        "cost_threshold_bps": _round(friction_bps),
        "net_cushion_bps": _round(best_net),
        "edge_amplification_vs_primary_bps": _round(edge_amplification),
        "edge_to_cost_multiple": (
            _round(best_net / friction_bps) if best_net is not None and friction_bps > 0 else None
        ),
        "sample_count_for_gate": best_sample,
        "raw_horizon_rows": row.get("horizon_rows"),
        "reason": row.get("reason"),
        "required_next_gate": next_gate,
        "next_action": next_action,
        "order_authority": "NOT_GRANTED",
        "main_cost_gate_adjustment": "NONE",
        "promotion_evidence": False,
        "authority_boundary": (
            "operator review required; candidate packet is replay/probe triage only"
        ),
    }


def _horizon_scorecard(counterfactual: dict[str, Any]) -> dict[str, Any]:
    return _dict(_dict(counterfactual.get("learning_lane_scorecard")).get("horizon_stability_scorecard"))


def build_horizon_edge_amplification_packet(
    *,
    counterfactual: dict[str, Any] | None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    payload = _dict(counterfactual)
    horizon = _horizon_scorecard(payload)
    primary_horizon = _int(payload.get("horizon_minutes")) or None
    friction_bps = _float(payload.get("friction_bps")) or 4.0

    candidates = []
    for row in _list(horizon.get("top_side_cells")):
        if not isinstance(row, dict):
            continue
        record = _candidate_record(
            row,
            primary_horizon_minutes=primary_horizon,
            friction_bps=friction_bps,
        )
        if record is not None:
            candidates.append(record)
    candidates.sort(
        key=lambda item: _candidate_priority({
            "status": item.get("status"),
            "candidate_horizons": item.get("candidate_horizons_minutes"),
            "block_confirmed_horizons": item.get("blocked_horizons_minutes"),
            "best_avg_net_bps": item.get("best_net_bps"),
            "best_sample_count_for_gate": item.get("sample_count_for_gate"),
        })
    )
    for index, item in enumerate(candidates, start=1):
        item["rank"] = index

    retiming_count = sum(1 for item in candidates if item["status"] == "RETIMING_CANDIDATE")
    stable_count = sum(1 for item in candidates if item["status"] == "STABLE_MULTI_HORIZON_CANDIDATE")
    horizon_guard_count = sum(
        1 for item in candidates if item["status"] == "MIXED_HORIZON_GUARD_CANDIDATE"
    )
    if retiming_count:
        status = "HORIZON_RETIMING_CANDIDATES_PRESENT"
        next_action = "run_sealed_replay_for_top_retiming_candidate"
    elif stable_count:
        status = "STABLE_HORIZON_CANDIDATES_PRESENT"
        next_action = "operator_review_stable_horizon_candidates_after_learning_stack_accumulates"
    else:
        status = "NO_HORIZON_EDGE_AMPLIFICATION_CANDIDATES"
        next_action = "continue_collecting_multi_horizon_cost_gate_counterfactuals"

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": "multi_horizon_counterfactual_cells_ranked_for_edge_amplification",
        "next_action": next_action,
        "source": {
            "counterfactual_generated_at_utc": payload.get("generated_at_utc"),
            "counterfactual_schema_version": payload.get("schema_version"),
            "counterfactual_scorecard_status": _dict(payload.get("learning_lane_scorecard")).get("status"),
            "horizon_scorecard_status": horizon.get("status"),
            "primary_horizon_minutes": primary_horizon,
            "friction_bps": friction_bps,
        },
        "summary": {
            "candidate_count": len(candidates),
            "retiming_candidate_count": retiming_count,
            "stable_multi_horizon_candidate_count": stable_count,
            "horizon_guard_candidate_count": horizon_guard_count,
            "top_side_cell_key": candidates[0]["side_cell_key"] if candidates else None,
            "top_best_horizon_minutes": candidates[0]["best_horizon_minutes"] if candidates else None,
            "top_best_net_bps": candidates[0]["best_net_bps"] if candidates else None,
            "top_edge_amplification_vs_primary_bps": (
                candidates[0]["edge_amplification_vs_primary_bps"] if candidates else None
            ),
        },
        "answers": {
            "horizon_specific_edge_present": bool(candidates),
            "retiming_can_amplify_edge": retiming_count > 0,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "order_authority_granted": False,
            "probe_authority_granted": False,
            "promotion_evidence": False,
        },
        "candidates": candidates,
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
        "# Horizon Edge Amplification Packet",
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
        "| rank | side_cell | status | best_horizon | best_net_bps | sample_n | amplification_vs_primary_bps | next gate |",
        "|---:|---|---|---:|---:|---:|---:|---|",
    ])
    for row in _list(packet.get("candidates")):
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            f"{row.get('rank')} | {cell(row.get('side_cell_key'))} | {cell(row.get('status'))} | "
            f"{row.get('best_horizon_minutes')} | {row.get('best_net_bps')} | "
            f"{row.get('sample_count_for_gate')} | {row.get('edge_amplification_vs_primary_bps')} | "
            f"{cell(row.get('required_next_gate'))} |"
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
    parser.add_argument("--counterfactual-json", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_horizon_edge_amplification_packet(
        counterfactual=_read_json(args.counterfactual_json),
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
