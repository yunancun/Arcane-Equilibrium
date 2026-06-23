#!/usr/bin/env python3
"""Review blocked-signal outcomes for the cost-gate demo learning lane.

This module turns accumulated ``blocked_signal_outcome`` ledger rows into a
machine-checkable review scorecard. It does not grant order authority, lower
the main Cost Gate, write PG, call Bybit, or mutate runtime config.
"""

from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sys
from typing import Any


RESEARCH_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
for _path in (str(RESEARCH_ROOT), str(ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from cost_gate_learning_lane.contract import BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE
from cost_gate_learning_lane.runtime_adapter import read_jsonl_ledger


BLOCKED_OUTCOME_REVIEW_SCHEMA_VERSION = (
    "cost_gate_demo_learning_lane_blocked_outcome_review_v2"
)
BLOCKED_OUTCOME_REVIEW_RECORD_TYPE = "blocked_signal_outcome_review"


@dataclass(frozen=True)
class BlockedOutcomeReviewConfig:
    """Fail-closed thresholds for blocked-signal review candidates."""

    min_outcomes_per_side_cell: int = 3
    min_avg_net_bps: float = 0.0
    min_net_positive_pct: float = 60.0


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _str(value: Any) -> str:
    return str(value or "").strip()


def validate_blocked_outcome_review_config(cfg: BlockedOutcomeReviewConfig) -> None:
    if cfg.min_outcomes_per_side_cell < 1 or cfg.min_outcomes_per_side_cell > 1_000:
        raise ValueError("--min-outcomes-per-side-cell must be in [1, 1000]")
    if cfg.min_avg_net_bps < -10_000.0 or cfg.min_avg_net_bps > 10_000.0:
        raise ValueError("--min-avg-net-bps must be in [-10000, 10000]")
    if cfg.min_net_positive_pct < 0.0 or cfg.min_net_positive_pct > 100.0:
        raise ValueError("--min-net-positive-pct must be in [0, 100]")


def _row_sort_ts(row: dict[str, Any]) -> str:
    return _str(row.get("generated_at_utc")) or _str(row.get("exit_ts_ms"))


def _int(value: Any, default: int = 0) -> int:
    try:
        out = int(float(value))
    except (TypeError, ValueError):
        return default
    return out


def _wrongful_block_score(
    *,
    outcome_count: int,
    avg_net_bps: float | None,
    net_positive_pct: float | None,
    cfg: BlockedOutcomeReviewConfig,
) -> float:
    """Rank review candidates without changing the conservative review gate."""
    if avg_net_bps is None or net_positive_pct is None:
        return 0.0
    avg_margin = avg_net_bps - cfg.min_avg_net_bps
    pct_margin = net_positive_pct - cfg.min_net_positive_pct
    if (
        outcome_count < cfg.min_outcomes_per_side_cell
        or avg_margin < 0.0
        or pct_margin < 0.0
    ):
        return 0.0
    sample_factor = min(2.0, outcome_count / cfg.min_outcomes_per_side_cell)
    return avg_margin * (net_positive_pct / 100.0) * sample_factor


def _diagnose_cost_gate_escape(
    *,
    outcome_count: int,
    avg_net_bps: float | None,
    avg_gross_bps: float | None,
    net_positive_pct: float | None,
    review_candidate: bool,
    cfg: BlockedOutcomeReviewConfig,
) -> dict[str, Any]:
    """Classify blocked outcomes into the next profit-learning action."""
    if outcome_count < cfg.min_outcomes_per_side_cell:
        return {
            "learning_diagnosis": "SAMPLE_INSUFFICIENT",
            "cost_gate_escape_recommendation": (
                "continue_recording_same_side_cell_blocked_signal_outcomes"
            ),
            "edge_amplification_required": False,
            "false_negative_candidate": False,
        }

    if review_candidate:
        return {
            "learning_diagnosis": "FALSE_NEGATIVE_CANDIDATE_AFTER_COST",
            "cost_gate_escape_recommendation": (
                "operator_review_bounded_probe_authority_without_global_gate_lowering"
            ),
            "edge_amplification_required": False,
            "false_negative_candidate": True,
        }

    avg_net = avg_net_bps if avg_net_bps is not None else 0.0
    avg_gross = avg_gross_bps if avg_gross_bps is not None else 0.0
    net_positive = net_positive_pct if net_positive_pct is not None else 0.0
    if avg_gross > 0.0 and avg_net < cfg.min_avg_net_bps:
        return {
            "learning_diagnosis": "GROSS_EDGE_POSITIVE_COST_CUSHION_INSUFFICIENT",
            "cost_gate_escape_recommendation": (
                "amplify_edge_or_reduce_friction_for_same_side_cell"
            ),
            "edge_amplification_required": True,
            "false_negative_candidate": False,
        }
    if avg_net >= cfg.min_avg_net_bps and net_positive < cfg.min_net_positive_pct:
        return {
            "learning_diagnosis": "POSITIVE_EDGE_UNSTABLE_AFTER_COST",
            "cost_gate_escape_recommendation": (
                "add_regime_filter_or_matched_controls_before_probe_review"
            ),
            "edge_amplification_required": True,
            "false_negative_candidate": False,
        }
    return {
        "learning_diagnosis": "BLOCK_CONFIRMED_AFTER_COST",
        "cost_gate_escape_recommendation": (
            "keep_cost_gate_blocked_or_archive_until_new_evidence"
        ),
        "edge_amplification_required": False,
        "false_negative_candidate": False,
    }


def _review_side_cell_rows(
    side_cell_key: str,
    rows: list[dict[str, Any]],
    *,
    cfg: BlockedOutcomeReviewConfig,
) -> dict[str, Any]:
    nets = []
    gross_values = []
    cost_values = []
    horizon_counts: dict[int, int] = {}
    symbols = set()
    strategies = set()
    sides = set()
    latest = None
    for row in rows:
        net = _float(row.get("realized_net_bps"))
        if net is None:
            continue
        nets.append(net)
        gross = _float(row.get("gross_bps"))
        if gross is not None:
            gross_values.append(gross)
        cost = _float(row.get("cost_bps"))
        if cost is not None:
            cost_values.append(cost)
        horizon = _int(row.get("horizon_minutes"), default=0)
        if horizon > 0:
            horizon_counts[horizon] = horizon_counts.get(horizon, 0) + 1
        symbol = _str(row.get("symbol")).upper()
        strategy = _str(row.get("strategy_name"))
        side = _str(row.get("side"))
        if symbol:
            symbols.add(symbol)
        if strategy:
            strategies.add(strategy)
        if side:
            sides.add(side)
        if latest is None or _row_sort_ts(row) >= _row_sort_ts(latest):
            latest = row

    outcome_count = len(nets)
    positive_count = sum(1 for value in nets if value > 0.0)
    gross_positive_count = sum(1 for value in gross_values if value > 0.0)
    avg_net = sum(nets) / outcome_count if outcome_count else None
    net_positive_pct = (positive_count / outcome_count * 100.0) if outcome_count else None
    min_net = min(nets) if nets else None
    max_net = max(nets) if nets else None
    avg_gross = sum(gross_values) / len(gross_values) if gross_values else None
    avg_cost = sum(cost_values) / len(cost_values) if cost_values else None
    gross_positive_pct = (
        gross_positive_count / len(gross_values) * 100.0
        if gross_values
        else None
    )
    net_cost_cushion_bps = (
        avg_net - cfg.min_avg_net_bps
        if avg_net is not None
        else None
    )
    net_positive_margin_pct = (
        net_positive_pct - cfg.min_net_positive_pct
        if net_positive_pct is not None
        else None
    )
    sample_margin_count = outcome_count - cfg.min_outcomes_per_side_cell
    wrongful_block_score = _wrongful_block_score(
        outcome_count=outcome_count,
        avg_net_bps=avg_net,
        net_positive_pct=net_positive_pct,
        cfg=cfg,
    )
    dominant_horizon = None
    if horizon_counts:
        dominant_horizon = sorted(
            horizon_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[0][0]

    if outcome_count < cfg.min_outcomes_per_side_cell:
        status = "COLLECT_MORE_BLOCKED_SIGNAL_OUTCOMES"
        reason = "side_cell_below_min_blocked_outcome_sample"
        review_candidate = False
    elif (
        avg_net is not None
        and avg_net >= cfg.min_avg_net_bps
        and net_positive_pct is not None
        and net_positive_pct >= cfg.min_net_positive_pct
    ):
        status = "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE"
        reason = "blocked_signal_markouts_clear_review_thresholds"
        review_candidate = True
    else:
        status = "KEEP_COST_GATE_BLOCKED"
        reason = "blocked_signal_markouts_do_not_clear_review_thresholds"
        review_candidate = False

    diagnosis = _diagnose_cost_gate_escape(
        outcome_count=outcome_count,
        avg_net_bps=avg_net,
        avg_gross_bps=avg_gross,
        net_positive_pct=net_positive_pct,
        review_candidate=review_candidate,
        cfg=cfg,
    )

    return {
        "side_cell_key": side_cell_key,
        "status": status,
        "reason": reason,
        **diagnosis,
        "review_candidate": review_candidate,
        "outcome_count": outcome_count,
        "positive_outcome_count": positive_count,
        "gross_positive_outcome_count": gross_positive_count,
        "avg_net_bps": avg_net,
        "avg_gross_bps": avg_gross,
        "avg_cost_bps": avg_cost,
        "min_net_bps": min_net,
        "max_net_bps": max_net,
        "net_positive_pct": net_positive_pct,
        "gross_positive_pct": gross_positive_pct,
        "net_cost_cushion_bps": net_cost_cushion_bps,
        "net_positive_margin_pct": net_positive_margin_pct,
        "sample_margin_count": sample_margin_count,
        "wrongful_block_score": wrongful_block_score,
        "horizon_minutes": sorted(horizon_counts),
        "horizon_counts": {
            str(key): horizon_counts[key]
            for key in sorted(horizon_counts)
        },
        "dominant_horizon_minutes": dominant_horizon,
        "min_outcomes_per_side_cell": cfg.min_outcomes_per_side_cell,
        "min_avg_net_bps": cfg.min_avg_net_bps,
        "min_net_positive_pct": cfg.min_net_positive_pct,
        "strategy_names": sorted(strategies),
        "symbols": sorted(symbols),
        "sides": sorted(sides),
        "latest_generated_at_utc": latest.get("generated_at_utc") if latest else None,
        "latest_attempt_id": latest.get("attempt_id") if latest else None,
        "promotion_evidence": False,
        "order_authority": "NOT_GRANTED",
        "main_cost_gate_adjustment": "NONE",
    }


def build_blocked_signal_outcome_review(
    ledger_rows: list[dict[str, Any]],
    *,
    now_utc: dt.datetime | None = None,
    cfg: BlockedOutcomeReviewConfig | None = None,
) -> dict[str, Any]:
    """Build a conservative scorecard from blocked-signal outcome rows."""
    cfg = cfg or BlockedOutcomeReviewConfig()
    validate_blocked_outcome_review_config(cfg)
    generated_at = (now_utc or _utc_now()).astimezone(dt.timezone.utc)

    grouped: dict[str, list[dict[str, Any]]] = {}
    invalid_outcome_row_count = 0
    for row in ledger_rows:
        if _str(row.get("record_type")) != BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE:
            continue
        side_cell_key = _str(row.get("side_cell_key"))
        net_bps = _float(row.get("realized_net_bps"))
        if not side_cell_key or net_bps is None:
            invalid_outcome_row_count += 1
            continue
        grouped.setdefault(side_cell_key, []).append(row)

    side_cells = [
        _review_side_cell_rows(key, rows, cfg=cfg)
        for key, rows in sorted(grouped.items())
    ]
    side_cells = sorted(
        side_cells,
        key=lambda row: (
            0 if row["review_candidate"] else 1,
            -float(row.get("wrongful_block_score") or 0.0),
            -int(row.get("outcome_count") or 0),
            -float(row.get("avg_net_bps") or -10_000.0),
            row["side_cell_key"],
        ),
    )
    candidate_rank = 0
    for rank, row in enumerate(side_cells, start=1):
        row["review_rank"] = rank
        if row["review_candidate"]:
            candidate_rank += 1
            row["bounded_demo_probe_review_rank"] = candidate_rank
        else:
            row["bounded_demo_probe_review_rank"] = None

    candidate_count = sum(1 for row in side_cells if row["review_candidate"])
    insufficient_count = sum(
        1 for row in side_cells
        if row["status"] == "COLLECT_MORE_BLOCKED_SIGNAL_OUTCOMES"
    )
    blocked_count = sum(
        1 for row in side_cells
        if row["status"] == "KEEP_COST_GATE_BLOCKED"
    )
    outcome_count = sum(int(row.get("outcome_count") or 0) for row in side_cells)
    positive_count = sum(int(row.get("positive_outcome_count") or 0) for row in side_cells)
    avg_net = (
        sum(
            float(row["avg_net_bps"]) * int(row["outcome_count"])
            for row in side_cells
            if row.get("avg_net_bps") is not None
        )
        / outcome_count
        if outcome_count
        else None
    )
    net_positive_pct = (positive_count / outcome_count * 100.0) if outcome_count else None
    top_side_cell = side_cells[0] if side_cells else None
    top_candidate = next(
        (row for row in side_cells if row["review_candidate"]),
        None,
    )
    max_wrongful_block_score = (
        max(float(row.get("wrongful_block_score") or 0.0) for row in side_cells)
        if side_cells
        else 0.0
    )
    diagnosis_counts: dict[str, int] = {}
    recommendation_counts: dict[str, int] = {}
    false_negative_candidate_count = 0
    edge_amplification_required_side_cell_count = 0
    for row in side_cells:
        diagnosis = _str(row.get("learning_diagnosis"))
        recommendation = _str(row.get("cost_gate_escape_recommendation"))
        if diagnosis:
            diagnosis_counts[diagnosis] = diagnosis_counts.get(diagnosis, 0) + 1
        if recommendation:
            recommendation_counts[recommendation] = (
                recommendation_counts.get(recommendation, 0) + 1
            )
        if row.get("false_negative_candidate") is True:
            false_negative_candidate_count += 1
        if row.get("edge_amplification_required") is True:
            edge_amplification_required_side_cell_count += 1

    if outcome_count == 0:
        status = "NO_BLOCKED_SIGNAL_OUTCOMES"
        reason = "blocked_signal_outcome_rows_missing"
        next_trigger = "run_cost_gate_outcome_refresh_for_blocked_signal_outcomes"
    elif candidate_count > 0:
        status = "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT"
        reason = "one_or_more_blocked_side_cells_clear_review_thresholds"
        next_trigger = "operator_review_blocked_outcome_scorecard_before_demo_probe_authority"
    elif insufficient_count > 0:
        status = "COLLECT_MORE_BLOCKED_SIGNAL_OUTCOMES"
        reason = "blocked_signal_outcome_sample_below_review_threshold"
        next_trigger = "continue_recording_and_refreshing_blocked_signal_outcomes"
    else:
        status = "NO_DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE"
        reason = "reviewed_blocked_side_cells_do_not_clear_thresholds"
        next_trigger = "keep_cost_gate_blocked_for_reviewed_side_cells"

    return {
        "schema_version": BLOCKED_OUTCOME_REVIEW_SCHEMA_VERSION,
        "record_type": BLOCKED_OUTCOME_REVIEW_RECORD_TYPE,
        "generated_at_utc": generated_at.isoformat(),
        "status": status,
        "reason": reason,
        "next_trigger": next_trigger,
        "side_cell_count": len(side_cells),
        "review_candidate_side_cell_count": candidate_count,
        "insufficient_sample_side_cell_count": insufficient_count,
        "keep_blocked_side_cell_count": blocked_count,
        "blocked_signal_outcome_count": outcome_count,
        "blocked_signal_positive_outcome_count": positive_count,
        "invalid_outcome_row_count": invalid_outcome_row_count,
        "avg_blocked_signal_outcome_net_bps": avg_net,
        "blocked_signal_net_positive_pct": net_positive_pct,
        "max_wrongful_block_score": max_wrongful_block_score,
        "top_side_cell_key": top_side_cell.get("side_cell_key") if top_side_cell else None,
        "top_side_cell_status": top_side_cell.get("status") if top_side_cell else None,
        "top_side_cell_learning_diagnosis": (
            top_side_cell.get("learning_diagnosis") if top_side_cell else None
        ),
        "top_side_cell_cost_gate_escape_recommendation": (
            top_side_cell.get("cost_gate_escape_recommendation")
            if top_side_cell
            else None
        ),
        "top_side_cell_wrongful_block_score": (
            top_side_cell.get("wrongful_block_score") if top_side_cell else None
        ),
        "top_side_cell_net_cost_cushion_bps": (
            top_side_cell.get("net_cost_cushion_bps") if top_side_cell else None
        ),
        "top_review_candidate_side_cell_key": (
            top_candidate.get("side_cell_key") if top_candidate else None
        ),
        "top_review_candidate_learning_diagnosis": (
            top_candidate.get("learning_diagnosis") if top_candidate else None
        ),
        "top_review_candidate_cost_gate_escape_recommendation": (
            top_candidate.get("cost_gate_escape_recommendation")
            if top_candidate
            else None
        ),
        "top_review_candidate_wrongful_block_score": (
            top_candidate.get("wrongful_block_score") if top_candidate else None
        ),
        "top_review_candidate_net_cost_cushion_bps": (
            top_candidate.get("net_cost_cushion_bps") if top_candidate else None
        ),
        "thresholds": {
            "min_outcomes_per_side_cell": cfg.min_outcomes_per_side_cell,
            "min_avg_net_bps": cfg.min_avg_net_bps,
            "min_net_positive_pct": cfg.min_net_positive_pct,
        },
        "diagnosis_counts": {
            key: diagnosis_counts[key] for key in sorted(diagnosis_counts)
        },
        "cost_gate_escape_recommendation_counts": {
            key: recommendation_counts[key]
            for key in sorted(recommendation_counts)
        },
        "false_negative_candidate_count": false_negative_candidate_count,
        "edge_amplification_required_side_cell_count": (
            edge_amplification_required_side_cell_count
        ),
        "top_side_cells": side_cells[:16],
        "promotion_evidence": False,
        "order_authority": "NOT_GRANTED",
        "main_cost_gate_adjustment": "NONE",
        "boundary": (
            "blocked outcome review artifact only; proposes operator review at "
            "most; no PG, Bybit, order, config, risk, auth, runtime mutation, "
            "or main Cost Gate lowering"
        ),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-outcomes-per-side-cell", type=int, default=3)
    parser.add_argument("--min-avg-net-bps", type=float, default=0.0)
    parser.add_argument("--min-net-positive-pct", type=float, default=60.0)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    cfg = BlockedOutcomeReviewConfig(
        min_outcomes_per_side_cell=args.min_outcomes_per_side_cell,
        min_avg_net_bps=args.min_avg_net_bps,
        min_net_positive_pct=args.min_net_positive_pct,
    )
    validate_blocked_outcome_review_config(cfg)
    scorecard = build_blocked_signal_outcome_review(
        read_jsonl_ledger(args.ledger),
        cfg=cfg,
    )
    if args.output:
        _write_json(args.output, scorecard)
    if args.print_json or not args.output:
        print(json.dumps(scorecard, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
