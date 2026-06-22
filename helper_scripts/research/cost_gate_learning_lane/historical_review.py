#!/usr/bin/env python3
"""Review historical cost-gate counterfactual scorecards for learning priority.

This module consumes the read-only ``cost_gate_reject_counterfactual_v2``
artifact and produces a separate historical review artifact. It is deliberately
not a probe ledger: aggregate counterfactual rows can prioritize which rejected
side-cells should be captured next, but they are not runtime execution evidence
and do not grant order authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
from typing import Any


HISTORICAL_REVIEW_SCHEMA_VERSION = (
    "cost_gate_demo_learning_lane_historical_scorecard_review_v1"
)
HISTORICAL_REVIEW_RECORD_TYPE = "historical_scorecard_review"
EXPECTED_SCORECARD_SCHEMA_VERSION = "cost_gate_reject_counterfactual_v2"
DEFAULT_MAX_SCORECARD_AGE_HOURS = 36


@dataclass(frozen=True)
class HistoricalScorecardReviewConfig:
    """Guardrails for treating aggregate counterfactuals as learning priority."""

    max_scorecard_age_hours: int = DEFAULT_MAX_SCORECARD_AGE_HOURS
    min_candidate_sample: int = 100
    max_side_cells: int = 20


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse_dt(value: Any) -> dt.datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _age_seconds(value: Any, *, now_utc: dt.datetime) -> float | None:
    parsed = _parse_dt(value)
    if parsed is None:
        return None
    age = (now_utc - parsed).total_seconds()
    return age if age >= 0.0 else None


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


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _side_cell_key(row: dict[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("strategy_name") or "unknown_strategy"),
            str(row.get("symbol") or "unknown_symbol"),
            str(row.get("side") or "unknown_side"),
        ]
    )


def _effective_sample_count(row: dict[str, Any]) -> int:
    sample_count = _int(row.get("sample_count_for_gate"))
    if sample_count > 0:
        return sample_count
    distinct_ts = _int(row.get("distinct_ts"))
    return distinct_ts if distinct_ts > 0 else _int(row.get("n"))


def validate_historical_scorecard_review_config(
    cfg: HistoricalScorecardReviewConfig,
) -> None:
    if cfg.max_scorecard_age_hours < 1 or cfg.max_scorecard_age_hours > 24 * 30:
        raise ValueError("--max-scorecard-age-hours must be in [1, 720]")
    if cfg.min_candidate_sample < 1:
        raise ValueError("--min-candidate-sample must be >= 1")
    if cfg.max_side_cells < 1 or cfg.max_side_cells > 200:
        raise ValueError("--max-side-cells must be in [1, 200]")


def _compact_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "side_cell_key": _side_cell_key(row),
        "strategy_name": row.get("strategy_name"),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "reject_reason_code": row.get("reject_reason_code"),
        "n": _int(row.get("n")),
        "sample_count_for_gate": _effective_sample_count(row),
        "distinct_ts": _int(row.get("distinct_ts")),
        "rows_per_distinct_ts": _float(row.get("rows_per_distinct_ts")),
        "timespan_minutes": _float(row.get("timespan_minutes")),
        "avg_gross_bps": _float(row.get("avg_gross_bps")),
        "p50_gross_bps": _float(row.get("p50_gross_bps")),
        "p90_gross_bps": _float(row.get("p90_gross_bps")),
        "avg_net_bps": _float(row.get("avg_net_bps")),
        "gross_positive_pct": _float(row.get("gross_positive_pct")),
        "net_positive_pct": _float(row.get("net_positive_pct")),
        "min_ts": row.get("min_ts"),
        "max_ts": row.get("max_ts"),
        "learning_lane_action": row.get("learning_lane_action"),
        "learning_lane_reason": row.get("learning_lane_reason"),
    }


def _rank_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            _float(row.get("avg_net_bps")) or float("-inf"),
            _float(row.get("net_positive_pct")) or float("-inf"),
            _effective_sample_count(row),
        ),
        reverse=True,
    )


def _source_failure_review(
    *,
    now_utc: dt.datetime,
    scorecard_path: Path | None,
    source_error: str,
) -> dict[str, Any]:
    return {
        "schema_version": HISTORICAL_REVIEW_SCHEMA_VERSION,
        "record_type": HISTORICAL_REVIEW_RECORD_TYPE,
        "generated_at_utc": now_utc.isoformat(),
        "status": "SOURCE_SCORECARD_UNAVAILABLE",
        "reason": source_error,
        "next_trigger": "refresh_cost_gate_reject_counterfactual_scorecard",
        "source": {
            "scorecard_path": str(scorecard_path) if scorecard_path else None,
            "source_error": source_error,
        },
        "historical_candidate_side_cell_count": 0,
        "historical_keep_blocked_side_cell_count": 0,
        "historical_data_coverage_task_count": 0,
        "historical_probe_candidates": [],
        "historical_keep_blocked_side_cells": [],
        "historical_data_coverage_tasks": [],
        "runtime_evidence_status": "NOT_RUNTIME_LEDGER_EVIDENCE",
        "promotion_evidence": False,
        "order_authority": "NOT_GRANTED",
        "main_cost_gate_adjustment": "NONE",
        "boundary": (
            "historical aggregate counterfactual review only; not probe ledger, "
            "not execution/fill evidence, no order authority or main Cost Gate lowering"
        ),
    }


def build_historical_scorecard_review(
    payload: dict[str, Any],
    *,
    now_utc: dt.datetime | None = None,
    cfg: HistoricalScorecardReviewConfig | None = None,
    scorecard_path: Path | None = None,
) -> dict[str, Any]:
    """Build a conservative learning-priority review from scorecard JSON."""
    cfg = cfg or HistoricalScorecardReviewConfig()
    validate_historical_scorecard_review_config(cfg)
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    scorecard = _dict(payload.get("learning_lane_scorecard"))
    scorecard_schema = str(scorecard.get("schema_version") or "")
    generated_at = payload.get("generated_at_utc")
    parsed_generated_at = _parse_dt(generated_at)
    age = _age_seconds(generated_at, now_utc=now)
    max_age_seconds = cfg.max_scorecard_age_hours * 3600

    source_error = None
    if scorecard_schema != EXPECTED_SCORECARD_SCHEMA_VERSION:
        source_error = "unexpected_scorecard_schema"
    elif parsed_generated_at is None:
        source_error = "missing_scorecard_generated_at"
    elif parsed_generated_at > now:
        source_error = "future_scorecard_generated_at"
    elif age is None:
        source_error = "missing_scorecard_generated_at"
    elif age > max_age_seconds:
        source_error = "stale_scorecard"

    rows = [row for row in _list(scorecard.get("rows")) if isinstance(row, dict)]
    probe_rows = [
        row for row in _list(scorecard.get("probe_candidates"))
        if isinstance(row, dict)
        and row.get("learning_lane_action") == "LEARNING_PROBE_CANDIDATE"
        and _effective_sample_count(row) >= cfg.min_candidate_sample
    ]
    if not probe_rows:
        probe_rows = [
            row for row in rows
            if row.get("learning_lane_action") == "LEARNING_PROBE_CANDIDATE"
            and _effective_sample_count(row) >= cfg.min_candidate_sample
        ]
    block_rows = [
        row for row in rows
        if row.get("learning_lane_action") == "BLOCK_CONFIRMED"
    ]
    data_rows = [
        row for row in rows
        if row.get("learning_lane_action") == "DATA_COVERAGE_BLOCKER"
    ]

    ranked_probe_rows = _rank_rows(probe_rows)
    ranked_block_rows = _rank_rows(block_rows)
    historical_candidates = [
        _compact_row(row) for row in ranked_probe_rows[: cfg.max_side_cells]
    ]
    keep_blocked = [
        _compact_row(row) for row in ranked_block_rows[: cfg.max_side_cells]
    ]
    data_tasks = [
        _compact_row(row) for row in data_rows[: cfg.max_side_cells]
    ]

    if source_error:
        status = "WAIT_FOR_HISTORICAL_SCORECARD_REFRESH"
        reason = source_error
        next_trigger = "refresh_cost_gate_reject_counterfactual_scorecard"
        historical_candidates = []
        keep_blocked = []
        data_tasks = []
    elif historical_candidates:
        status = "HISTORICAL_COUNTERFACTUAL_CANDIDATES_PRESENT"
        reason = "historical_rejected_side_cells_clear_counterfactual_learning_thresholds"
        next_trigger = (
            "enable_runtime_writer_to_accumulate_reject_outcomes_for_historical_candidates"
        )
    elif keep_blocked:
        status = "HISTORICAL_COUNTERFACTUAL_CONFIRMS_BLOCK"
        reason = "historical_rejected_side_cells_do_not_clear_learning_thresholds"
        next_trigger = "keep_cost_gate_blocked_and_continue_periodic_counterfactual_review"
    elif data_tasks:
        status = "HISTORICAL_COUNTERFACTUAL_DATA_COVERAGE_BLOCKED"
        reason = "historical_reject_reasons_require_data_coverage_fix"
        next_trigger = "fix_cost_gate_reject_data_coverage_before_probe_review"
    else:
        status = "NO_HISTORICAL_COUNTERFACTUAL_EDGE"
        reason = "no_learning_probe_candidate_rows_in_historical_scorecard"
        next_trigger = "continue_collecting_cost_gate_reject_counterfactuals"

    coverage = payload.get("coverage") if isinstance(payload.get("coverage"), dict) else {}
    return {
        "schema_version": HISTORICAL_REVIEW_SCHEMA_VERSION,
        "record_type": HISTORICAL_REVIEW_RECORD_TYPE,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "next_trigger": next_trigger,
        "source": {
            "scorecard_path": str(scorecard_path) if scorecard_path else None,
            "scorecard_generated_at_utc": generated_at,
            "scorecard_age_seconds": age,
            "scorecard_max_age_seconds": max_age_seconds,
            "scorecard_schema_version": scorecard_schema or None,
            "scorecard_status": scorecard.get("status"),
            "scorecard_outcome_path_status": scorecard.get("outcome_path_status"),
            "source_error": source_error,
        },
        "coverage": coverage,
        "scorecard_thresholds": scorecard.get("thresholds") or {},
        "scorecard_action_counts": scorecard.get("action_counts") or {},
        "scorecard_row_count": len(rows),
        "historical_candidate_side_cell_count": len(historical_candidates),
        "historical_keep_blocked_side_cell_count": len(keep_blocked),
        "historical_data_coverage_task_count": len(data_tasks),
        "historical_probe_candidates": historical_candidates,
        "historical_keep_blocked_side_cells": keep_blocked,
        "historical_data_coverage_tasks": data_tasks,
        "runtime_evidence_status": "NOT_RUNTIME_LEDGER_EVIDENCE",
        "runtime_evidence_required_before_probe_authority": True,
        "promotion_evidence": False,
        "order_authority": "NOT_GRANTED",
        "main_cost_gate_adjustment": "NONE",
        "boundary": (
            "historical aggregate counterfactual review only; can prioritize "
            "runtime capture, but is not probe ledger, not execution/fill "
            "evidence, no order authority, no runtime mutation, and no main "
            "Cost Gate lowering"
        ),
    }


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "missing"
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return None, f"malformed:{type(exc).__name__}"
    if not isinstance(payload, dict):
        return None, "not_object"
    return payload, None


def build_historical_scorecard_review_from_file(
    scorecard_json: Path,
    *,
    now_utc: dt.datetime | None = None,
    cfg: HistoricalScorecardReviewConfig | None = None,
) -> dict[str, Any]:
    """Read a scorecard artifact and produce a fail-soft historical review."""
    cfg = cfg or HistoricalScorecardReviewConfig()
    validate_historical_scorecard_review_config(cfg)
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    payload, err = _read_json(scorecard_json)
    if err:
        return _source_failure_review(
            now_utc=now,
            scorecard_path=scorecard_json,
            source_error=err,
        )
    assert payload is not None
    return build_historical_scorecard_review(
        payload,
        now_utc=now,
        cfg=cfg,
        scorecard_path=scorecard_json,
    )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _default_scorecard_json() -> Path:
    data_dir = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))
    return data_dir / "cost_gate_counterfactual" / "cost_gate_reject_counterfactual_latest.json"


def _default_output() -> Path:
    data_dir = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))
    return data_dir / "cost_gate_learning_lane" / "historical_scorecard_review_latest.json"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scorecard-json", type=Path, default=_default_scorecard_json())
    parser.add_argument("--output", type=Path, default=_default_output())
    parser.add_argument("--max-scorecard-age-hours", type=int, default=36)
    parser.add_argument("--min-candidate-sample", type=int, default=100)
    parser.add_argument("--max-side-cells", type=int, default=20)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    cfg = HistoricalScorecardReviewConfig(
        max_scorecard_age_hours=args.max_scorecard_age_hours,
        min_candidate_sample=args.min_candidate_sample,
        max_side_cells=args.max_side_cells,
    )
    validate_historical_scorecard_review_config(cfg)
    review = build_historical_scorecard_review_from_file(args.scorecard_json, cfg=cfg)
    _atomic_write_json(args.output, review)
    if args.print_json:
        print(json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
