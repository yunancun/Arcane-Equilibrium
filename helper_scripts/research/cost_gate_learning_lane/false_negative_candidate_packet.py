#!/usr/bin/env python3
"""Rank Cost Gate false-negative candidates from blocked-outcome review.

This artifact deepens the interface between blocked-signal outcome review and
the autonomous learning worklist. It never lowers the main Cost Gate, grants
probe/order authority, writes PG, calls Bybit, mutates runtime config, or marks
promotion evidence.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.outcome_review import (
    BLOCKED_OUTCOME_REVIEW_SCHEMA_VERSION,
)


SCHEMA_VERSION = "cost_gate_false_negative_candidate_packet_v1"
BOUNDARY = (
    "artifact-only Cost Gate false-negative candidate ranking; no PG "
    "query/write, Bybit call, order, config, risk, auth, runtime mutation, main "
    "Cost Gate lowering, probe authority, or promotion proof"
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
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _round(value: Any, ndigits: int = 4) -> float | None:
    parsed = _float(value)
    return round(parsed, ndigits) if parsed is not None else None


def _positive_gap(value: Any) -> float | None:
    parsed = _float(value)
    if parsed is None:
        return None
    return round(max(0.0, -parsed), 4)


def _candidate_class(row: dict[str, Any]) -> str:
    diagnosis = _str(row.get("learning_diagnosis"))
    if (
        row.get("false_negative_candidate") is True
        or row.get("review_candidate") is True
        or diagnosis == "FALSE_NEGATIVE_CANDIDATE_AFTER_COST"
    ):
        return "false_negative_after_cost"
    if (
        row.get("edge_amplification_required") is True
        or diagnosis
        in {
            "GROSS_EDGE_POSITIVE_COST_CUSHION_INSUFFICIENT",
            "POSITIVE_EDGE_UNSTABLE_AFTER_COST",
        }
    ):
        return "edge_amplification_required"
    if diagnosis == "SAMPLE_INSUFFICIENT":
        return "sample_accumulation_required"
    return "keep_blocked_after_cost"


def _next_action_for_candidate(candidate_class: str, row: dict[str, Any]) -> str:
    recommendation = _str(row.get("cost_gate_escape_recommendation"))
    if recommendation:
        return recommendation
    if candidate_class == "false_negative_after_cost":
        return "operator_review_bounded_probe_authority_without_global_gate_lowering"
    if candidate_class == "edge_amplification_required":
        return "amplify_edge_or_reduce_friction_for_same_side_cell"
    if candidate_class == "sample_accumulation_required":
        return "continue_recording_same_side_cell_blocked_signal_outcomes"
    return "keep_cost_gate_blocked_or_archive_until_new_evidence"


def _candidate_from_row(row: dict[str, Any]) -> dict[str, Any]:
    candidate_class = _candidate_class(row)
    avg_net = _float(row.get("avg_net_bps"))
    avg_gross = _float(row.get("avg_gross_bps"))
    net_margin = _float(row.get("net_cost_cushion_bps"))
    positive_margin = _float(row.get("net_positive_margin_pct"))
    outcome_count = _int(row.get("outcome_count"))
    gross_positive_pct = _float(row.get("gross_positive_pct"))
    edge_amplification_score = 0.0
    if candidate_class == "edge_amplification_required":
        gross = avg_gross if avg_gross is not None else 0.0
        gross_quality = (gross_positive_pct / 100.0) if gross_positive_pct is not None else 0.0
        required_net = max(0.0, -(net_margin or 0.0))
        required_stability = max(0.0, -(positive_margin or 0.0)) / 100.0
        edge_amplification_score = gross * gross_quality - required_net - required_stability
    return {
        "side_cell_key": row.get("side_cell_key"),
        "candidate_class": candidate_class,
        "learning_diagnosis": row.get("learning_diagnosis"),
        "status": row.get("status"),
        "reason": row.get("reason"),
        "next_action": _next_action_for_candidate(candidate_class, row),
        "strategy_names": row.get("strategy_names") or [],
        "symbols": row.get("symbols") or [],
        "sides": row.get("sides") or [],
        "horizon_minutes": row.get("horizon_minutes") or [],
        "horizon_counts": row.get("horizon_counts") or {},
        "dominant_horizon_minutes": row.get("dominant_horizon_minutes"),
        "outcome_count": outcome_count,
        "positive_outcome_count": _int(row.get("positive_outcome_count")),
        "gross_positive_outcome_count": _int(row.get("gross_positive_outcome_count")),
        "avg_net_bps": _round(avg_net),
        "avg_gross_bps": _round(avg_gross),
        "avg_cost_bps": _round(row.get("avg_cost_bps")),
        "min_net_bps": _round(row.get("min_net_bps")),
        "max_net_bps": _round(row.get("max_net_bps")),
        "net_positive_pct": _round(row.get("net_positive_pct")),
        "gross_positive_pct": _round(gross_positive_pct),
        "net_cost_cushion_bps": _round(net_margin),
        "net_positive_margin_pct": _round(positive_margin),
        "required_net_uplift_bps": _positive_gap(net_margin),
        "required_net_positive_pct_uplift": _positive_gap(positive_margin),
        "sample_margin_count": _int(row.get("sample_margin_count")),
        "wrongful_block_score": _round(row.get("wrongful_block_score")),
        "edge_amplification_score": round(edge_amplification_score, 4),
        "latest_generated_at_utc": row.get("latest_generated_at_utc"),
        "latest_attempt_id": row.get("latest_attempt_id"),
        "operator_review_required": candidate_class == "false_negative_after_cost",
        "engineering_actionable": candidate_class == "edge_amplification_required",
        "global_cost_gate_lowering_recommended": False,
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "promotion_evidence": False,
    }


def _false_negative_sort_key(row: dict[str, Any]) -> tuple[float, int, float, str]:
    return (
        -(_float(row.get("wrongful_block_score")) or 0.0),
        -_int(row.get("outcome_count")),
        -(_float(row.get("net_cost_cushion_bps")) or -1e9),
        _str(row.get("side_cell_key")),
    )


def _edge_amplification_sort_key(row: dict[str, Any]) -> tuple[float, float, int, str]:
    return (
        -(_float(row.get("edge_amplification_score")) or 0.0),
        _float(row.get("required_net_uplift_bps")) or 1e9,
        -_int(row.get("outcome_count")),
        _str(row.get("side_cell_key")),
    )


def _rank(rows: list[dict[str, Any]], *, rank_field: str) -> list[dict[str, Any]]:
    out = [dict(row) for row in rows]
    for index, row in enumerate(out, start=1):
        row[rank_field] = index
    return out


def build_false_negative_candidate_packet(
    blocked_outcome_review: dict[str, Any] | None,
    *,
    now_utc: dt.datetime | None = None,
    source_path: Path | None = None,
    source_error: str | None = None,
    top_limit: int = 16,
) -> dict[str, Any]:
    """Build an artifact-only Cost Gate false-negative ranking packet."""
    generated_at = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    review = _dict(blocked_outcome_review)
    side_cells = [
        _candidate_from_row(row)
        for row in _list(review.get("top_side_cells"))
        if isinstance(row, dict)
    ]
    false_negative_candidates = sorted(
        [
            row for row in side_cells
            if row["candidate_class"] == "false_negative_after_cost"
        ],
        key=_false_negative_sort_key,
    )
    edge_amplification_candidates = sorted(
        [
            row for row in side_cells
            if row["candidate_class"] == "edge_amplification_required"
        ],
        key=_edge_amplification_sort_key,
    )
    sample_accumulation_candidates = [
        row for row in side_cells
        if row["candidate_class"] == "sample_accumulation_required"
    ]
    keep_blocked_candidates = [
        row for row in side_cells
        if row["candidate_class"] == "keep_blocked_after_cost"
    ]

    false_negative_candidates = _rank(
        false_negative_candidates,
        rank_field="false_negative_rank",
    )
    edge_amplification_candidates = _rank(
        edge_amplification_candidates,
        rank_field="edge_amplification_rank",
    )
    top_false_negative = false_negative_candidates[0] if false_negative_candidates else None
    top_edge = edge_amplification_candidates[0] if edge_amplification_candidates else None

    schema_ok = review.get("schema_version") == BLOCKED_OUTCOME_REVIEW_SCHEMA_VERSION
    if source_error:
        status = "BLOCKED_OUTCOME_REVIEW_UNAVAILABLE"
        reason = source_error
        next_actions = ["refresh_blocked_outcome_review_before_candidate_ranking"]
    elif not schema_ok:
        status = "BLOCKED_OUTCOME_REVIEW_SCHEMA_MISMATCH"
        reason = "blocked_outcome_review_schema_version_not_supported"
        next_actions = ["refresh_blocked_outcome_review_with_supported_schema"]
    elif false_negative_candidates:
        status = "COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW"
        reason = "blocked_side_cells_clear_after_cost_review_thresholds"
        next_actions = [
            "operator_review_ranked_false_negative_candidates_before_bounded_demo_probe_authority",
            "preserve_global_cost_gate_no_lowering",
            "require_candidate_matched_touchability_fill_fee_slippage_lineage_before_cost_gate_change",
        ]
    elif edge_amplification_candidates:
        status = "COST_GATE_EDGE_AMPLIFICATION_REQUIRED"
        reason = "blocked_side_cells_have_positive_gross_or_unstable_after_cost_edge"
        next_actions = [
            "amplify_edge_or_reduce_friction_for_ranked_side_cells",
            "rerun_blocked_outcome_review_after_signal_or_execution_repair",
        ]
    elif sample_accumulation_candidates:
        status = "COST_GATE_SAMPLE_ACCUMULATION_REQUIRED"
        reason = "blocked_side_cells_do_not_have_enough_outcome_sample"
        next_actions = ["continue_recording_and_refreshing_blocked_signal_outcomes"]
    else:
        status = "COST_GATE_BLOCKS_CONFIRMED_FOR_REVIEWED_SIDE_CELLS"
        reason = "reviewed_blocked_side_cells_do_not_show_after_cost_edge"
        next_actions = ["keep_cost_gate_blocked_until_new_evidence"]

    ranked_review_candidates = false_negative_candidates + edge_amplification_candidates
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated_at.isoformat(),
        "status": status,
        "reason": reason,
        "next_actions": next_actions,
        "source": {
            "blocked_outcome_review_path": str(source_path) if source_path else None,
            "blocked_outcome_review_source_error": source_error,
            "blocked_outcome_review_schema_version": review.get("schema_version"),
            "blocked_outcome_review_generated_at_utc": review.get("generated_at_utc"),
            "blocked_outcome_review_status": review.get("status"),
            "blocked_outcome_review_next_trigger": review.get("next_trigger"),
            "blocked_signal_outcome_count": review.get("blocked_signal_outcome_count"),
            "review_candidate_side_cell_count": review.get(
                "review_candidate_side_cell_count"
            ),
            "edge_amplification_required_side_cell_count": review.get(
                "edge_amplification_required_side_cell_count"
            ),
        },
        "summary": {
            "ranked_candidate_count": len(ranked_review_candidates),
            "false_negative_candidate_count": len(false_negative_candidates),
            "edge_amplification_candidate_count": len(edge_amplification_candidates),
            "sample_accumulation_candidate_count": len(sample_accumulation_candidates),
            "keep_blocked_candidate_count": len(keep_blocked_candidates),
            "top_false_negative_side_cell_key": (
                top_false_negative.get("side_cell_key") if top_false_negative else None
            ),
            "top_false_negative_wrongful_block_score": (
                top_false_negative.get("wrongful_block_score")
                if top_false_negative
                else None
            ),
            "top_false_negative_net_cost_cushion_bps": (
                top_false_negative.get("net_cost_cushion_bps")
                if top_false_negative
                else None
            ),
            "top_edge_amplification_side_cell_key": (
                top_edge.get("side_cell_key") if top_edge else None
            ),
            "top_edge_amplification_required_net_uplift_bps": (
                top_edge.get("required_net_uplift_bps") if top_edge else None
            ),
        },
        "answers": {
            "false_negative_candidates_present": bool(false_negative_candidates),
            "edge_amplification_candidates_present": bool(edge_amplification_candidates),
            "operator_review_ready": bool(false_negative_candidates),
            "engineering_actionable": bool(edge_amplification_candidates),
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "ranked_false_negative_candidates": false_negative_candidates[:top_limit],
        "edge_amplification_candidates": edge_amplification_candidates[:top_limit],
        "ranked_review_candidates": ranked_review_candidates[:top_limit],
        "ranking_policy": (
            "false-negative after-cost candidates are ranked by wrongful block "
            "score, sample count, and net cushion; edge-amplification candidates "
            "are ranked separately by positive gross edge and required uplift"
        ),
        "boundary": BOUNDARY,
    }


def render_false_negative_candidate_packet_markdown(packet: dict[str, Any]) -> str:
    """Render a compact operator-facing Markdown summary."""
    summary = _dict(packet.get("summary"))
    answers = _dict(packet.get("answers"))
    lines = [
        "# Cost Gate False-Negative Candidate Packet",
        "",
        f"- status: `{packet.get('status')}`",
        f"- reason: `{packet.get('reason')}`",
        f"- false_negative_candidate_count: `{summary.get('false_negative_candidate_count')}`",
        f"- edge_amplification_candidate_count: `{summary.get('edge_amplification_candidate_count')}`",
        f"- operator_review_ready: `{answers.get('operator_review_ready')}`",
        f"- global_cost_gate_lowering_recommended: `{answers.get('global_cost_gate_lowering_recommended')}`",
        f"- probe_authority_granted: `{answers.get('probe_authority_granted')}`",
        f"- order_authority_granted: `{answers.get('order_authority_granted')}`",
        "",
        "## Top False-Negative Candidates",
        "",
        "| rank | side_cell | n | avg_net_bps | net_positive_pct | score | next_action |",
        "|---:|---|---:|---:|---:|---:|---|",
    ]
    for row in _list(packet.get("ranked_false_negative_candidates"))[:8]:
        lines.append(
            "| {rank} | `{key}` | {n} | {net} | {pct} | {score} | `{action}` |".format(
                rank=row.get("false_negative_rank"),
                key=row.get("side_cell_key"),
                n=row.get("outcome_count"),
                net=row.get("avg_net_bps"),
                pct=row.get("net_positive_pct"),
                score=row.get("wrongful_block_score"),
                action=row.get("next_action"),
            )
        )
    if not _list(packet.get("ranked_false_negative_candidates")):
        lines.append("| - | - | - | - | - | - | - |")
    lines.extend([
        "",
        "## Top Edge-Amplification Candidates",
        "",
        "| rank | side_cell | n | avg_gross_bps | avg_net_bps | required_net_uplift_bps | next_action |",
        "|---:|---|---:|---:|---:|---:|---|",
    ])
    for row in _list(packet.get("edge_amplification_candidates"))[:8]:
        lines.append(
            "| {rank} | `{key}` | {n} | {gross} | {net} | {uplift} | `{action}` |".format(
                rank=row.get("edge_amplification_rank"),
                key=row.get("side_cell_key"),
                n=row.get("outcome_count"),
                gross=row.get("avg_gross_bps"),
                net=row.get("avg_net_bps"),
                uplift=row.get("required_net_uplift_bps"),
                action=row.get("next_action"),
            )
        )
    if not _list(packet.get("edge_amplification_candidates")):
        lines.append("| - | - | - | - | - | - | - |")
    lines.extend([
        "",
        f"Boundary: {packet.get('boundary')}",
        "",
    ])
    return "\n".join(lines)


def _read_json(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return {}, "missing"
    except json.JSONDecodeError as exc:
        return {}, f"json_decode_error:{exc}"
    except OSError as exc:
        return {}, f"os_error:{exc}"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blocked-outcome-review-json", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--top-limit", type=int, default=16)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    review, err = _read_json(args.blocked_outcome_review_json)
    packet = build_false_negative_candidate_packet(
        review,
        source_path=args.blocked_outcome_review_json,
        source_error=err,
        top_limit=args.top_limit,
    )
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.output:
        _write_text(args.output, render_false_negative_candidate_packet_markdown(packet))
    if args.print_json or not args.json_output:
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

