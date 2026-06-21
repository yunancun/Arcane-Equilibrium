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
    "cost_gate_demo_learning_lane_blocked_outcome_review_v1"
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


def _review_side_cell_rows(
    side_cell_key: str,
    rows: list[dict[str, Any]],
    *,
    cfg: BlockedOutcomeReviewConfig,
) -> dict[str, Any]:
    nets = []
    symbols = set()
    strategies = set()
    sides = set()
    latest = None
    for row in rows:
        net = _float(row.get("realized_net_bps"))
        if net is None:
            continue
        nets.append(net)
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
    avg_net = sum(nets) / outcome_count if outcome_count else None
    net_positive_pct = (positive_count / outcome_count * 100.0) if outcome_count else None
    min_net = min(nets) if nets else None
    max_net = max(nets) if nets else None

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

    return {
        "side_cell_key": side_cell_key,
        "status": status,
        "reason": reason,
        "review_candidate": review_candidate,
        "outcome_count": outcome_count,
        "positive_outcome_count": positive_count,
        "avg_net_bps": avg_net,
        "min_net_bps": min_net,
        "max_net_bps": max_net,
        "net_positive_pct": net_positive_pct,
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
            -int(row.get("outcome_count") or 0),
            -float(row.get("avg_net_bps") or -10_000.0),
            row["side_cell_key"],
        ),
    )
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
        "thresholds": {
            "min_outcomes_per_side_cell": cfg.min_outcomes_per_side_cell,
            "min_avg_net_bps": cfg.min_avg_net_bps,
            "min_net_positive_pct": cfg.min_net_positive_pct,
        },
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
