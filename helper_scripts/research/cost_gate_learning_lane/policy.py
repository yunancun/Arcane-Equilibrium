#!/usr/bin/env python3
"""Build a bounded demo-learning lane plan from cost-gate reject scorecards.

This module consumes the read-only
``cost_gate_reject_counterfactual_v2`` artifact and emits a policy artifact
that a future demo adapter can consume. It does not grant order authority,
lower the main cost gate, connect to PG, or call Bybit.
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

DEMO_LEARNING_LANE_SCHEMA_VERSION = "cost_gate_demo_learning_lane_plan_v1"
EXPECTED_SCORECARD_SCHEMA_VERSION = "cost_gate_reject_counterfactual_v2"
DEFAULT_MAX_SCORECARD_AGE_HOURS = 24


@dataclass(frozen=True)
class LearningLanePolicyConfig:
    """Small, deterministic guardrails for demo-only learning probes."""

    max_probe_side_cells: int = 4
    max_probe_orders_per_side_cell: int = 3
    max_total_probe_orders: int = 8
    cooldown_minutes: int = 30
    max_scorecard_age_hours: int = DEFAULT_MAX_SCORECARD_AGE_HOURS
    min_candidate_sample: int = 100


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


def validate_policy_config(cfg: LearningLanePolicyConfig) -> None:
    if cfg.max_probe_side_cells < 1 or cfg.max_probe_side_cells > 20:
        raise ValueError("--max-probe-side-cells must be in [1, 20]")
    if cfg.max_probe_orders_per_side_cell < 1 or cfg.max_probe_orders_per_side_cell > 20:
        raise ValueError("--max-probe-orders-per-side-cell must be in [1, 20]")
    if cfg.max_total_probe_orders < 1 or cfg.max_total_probe_orders > 100:
        raise ValueError("--max-total-probe-orders must be in [1, 100]")
    if cfg.cooldown_minutes < 1 or cfg.cooldown_minutes > 24 * 60:
        raise ValueError("--cooldown-minutes must be in [1, 1440]")
    if cfg.max_scorecard_age_hours < 1 or cfg.max_scorecard_age_hours > 24 * 14:
        raise ValueError("--max-scorecard-age-hours must be in [1, 336]")
    if cfg.min_candidate_sample < 1:
        raise ValueError("--min-candidate-sample must be >= 1")


def _rank_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            _float(row.get("avg_net_bps")) or float("-inf"),
            _float(row.get("net_positive_pct")) or float("-inf"),
            _int(row.get("n")),
        ),
        reverse=True,
    )


def _compact_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "side_cell_key": _side_cell_key(row),
        "strategy_name": row.get("strategy_name"),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "reject_reason_code": row.get("reject_reason_code"),
        "n": _int(row.get("n")),
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


def _probe_budget_for_candidates(
    selected_count: int,
    cfg: LearningLanePolicyConfig,
) -> int:
    if selected_count <= 0:
        return 0
    fair_share = max(1, cfg.max_total_probe_orders // selected_count)
    return min(cfg.max_probe_orders_per_side_cell, fair_share)


def _candidate_to_probe(
    row: dict[str, Any],
    *,
    max_probe_orders: int,
    cfg: LearningLanePolicyConfig,
) -> dict[str, Any]:
    compact = _compact_row(row)
    compact["probe_proposal"] = {
        "mode": "demo_only_learning_probe",
        "max_probe_orders": max_probe_orders,
        "cooldown_minutes": cfg.cooldown_minutes,
        "requires_runtime_policy_adapter": True,
        "requires_probe_attempt_logging": True,
        "requires_probe_outcome_logging": True,
    }
    compact["guardrails"] = {
        "main_cost_gate_adjustment": "NONE",
        "may_bypass_main_live_gate": False,
        "demo_only": True,
        "paper_not_promotion_evidence": True,
        "notional_or_qty_not_granted_by_artifact": True,
    }
    return compact


def _source_failure_plan(
    *,
    now_utc: dt.datetime,
    scorecard_path: Path,
    source_error: str,
) -> dict[str, Any]:
    return {
        "schema_version": DEMO_LEARNING_LANE_SCHEMA_VERSION,
        "generated_at_utc": now_utc.isoformat(),
        "status": "SOURCE_SCORECARD_UNAVAILABLE",
        "gate_status": "WAIT",
        "policy": "artifact_only_demo_learning_probe_plan_no_order_authority",
        "main_cost_gate_adjustment": "NONE",
        "learning_gate_adjustment": "NONE_WITHOUT_FRESH_SCORECARD",
        "order_authority": "NOT_GRANTED",
        "source": {
            "scorecard_path": str(scorecard_path),
            "source_error": source_error,
        },
        "probe_candidate_count": 0,
        "selected_probe_candidate_count": 0,
        "probe_candidates": [],
        "do_not_probe_side_cells": [],
        "data_coverage_tasks": [],
        "required_runtime_wiring": [],
        "stop_conditions": [],
        "boundary": "artifact-only; no DB, Bybit, order, config, risk, auth, or runtime mutation",
    }


def build_plan_from_payload(
    payload: dict[str, Any],
    *,
    now_utc: dt.datetime | None = None,
    cfg: LearningLanePolicyConfig | None = None,
    scorecard_path: Path | None = None,
) -> dict[str, Any]:
    """Build the guarded demo-learning lane plan from a scorecard payload."""
    cfg = cfg or LearningLanePolicyConfig()
    validate_policy_config(cfg)
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

    rows = _list(scorecard.get("rows"))
    probe_rows = [
        row for row in _list(scorecard.get("probe_candidates"))
        if isinstance(row, dict)
        and row.get("learning_lane_action") == "LEARNING_PROBE_CANDIDATE"
        and _int(row.get("n")) >= cfg.min_candidate_sample
    ]
    if not probe_rows:
        probe_rows = [
            row for row in rows
            if isinstance(row, dict)
            and row.get("learning_lane_action") == "LEARNING_PROBE_CANDIDATE"
            and _int(row.get("n")) >= cfg.min_candidate_sample
        ]
    ranked = _rank_candidates(probe_rows)
    selected = ranked[: cfg.max_probe_side_cells]
    per_cell_budget = _probe_budget_for_candidates(len(selected), cfg)
    probe_candidates = [
        _candidate_to_probe(row, max_probe_orders=per_cell_budget, cfg=cfg)
        for row in selected
    ]
    if source_error:
        probe_candidates = []
        per_cell_budget = 0
    do_not_probe = [
        _compact_row(row) for row in _rank_candidates([
            row for row in rows
            if isinstance(row, dict)
            and row.get("learning_lane_action") == "BLOCK_CONFIRMED"
        ])[:20]
    ]
    data_tasks = [
        _compact_row(row) for row in [
            row for row in rows
            if isinstance(row, dict)
            and row.get("learning_lane_action") == "DATA_COVERAGE_BLOCKER"
        ][:20]
    ]

    if source_error:
        status = "WAIT_FOR_SCORECARD_REFRESH"
        gate_status = "WAIT"
        learning_gate_adjustment = "NONE_WITHOUT_FRESH_SCORECARD"
    elif probe_candidates:
        status = "READY_FOR_DEMO_LEARNING_PROBE"
        gate_status = "OPERATOR_REVIEW"
        learning_gate_adjustment = "SIDE_CELL_DEMO_PROBE_ONLY_AFTER_ADAPTER_WIRING"
    elif data_tasks:
        status = "BLOCKED_BY_DATA_COVERAGE"
        gate_status = "WAIT"
        learning_gate_adjustment = "NONE_FIX_DATA_COVERAGE_FIRST"
    else:
        status = "NO_DEMO_LEARNING_PROBE_CANDIDATES"
        gate_status = "NO_CANDIDATE"
        learning_gate_adjustment = "NONE"

    return {
        "schema_version": DEMO_LEARNING_LANE_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "gate_status": gate_status,
        "policy": "artifact_only_demo_learning_probe_plan_no_order_authority",
        "main_cost_gate_adjustment": "NONE",
        "learning_gate_adjustment": learning_gate_adjustment,
        "order_authority": "NOT_GRANTED",
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
        "coverage": payload.get("coverage") if isinstance(payload.get("coverage"), dict) else {},
        "probe_budget": {
            "max_probe_side_cells": cfg.max_probe_side_cells,
            "max_probe_orders_per_side_cell": cfg.max_probe_orders_per_side_cell,
            "max_total_probe_orders": cfg.max_total_probe_orders,
            "selected_per_cell_probe_orders": per_cell_budget,
            "cooldown_minutes": cfg.cooldown_minutes,
        },
        "scorecard_action_counts": scorecard.get("action_counts") or {},
        "probe_candidate_count": len(ranked),
        "selected_probe_candidate_count": len(probe_candidates),
        "probe_candidates": probe_candidates,
        "do_not_probe_side_cells": do_not_probe,
        "data_coverage_tasks": data_tasks,
        "required_runtime_wiring": [
            "consume_plan_in_demo_learning_policy_before_any_probe",
            "persist_probe_attempts_with_source_scorecard_hash",
            "persist_probe_outcomes_and_counterfactual_labels",
            "auto_disable_side_cell_after_budget_or_stop_condition",
            "feed_realized_probe_labels_back_to_edge_estimator",
        ],
        "stop_conditions": [
            "scorecard_stale_or_missing",
            "side_cell_removed_from_LEARNING_PROBE_CANDIDATE",
            "probe_budget_exhausted",
            "realized_probe_outcomes_fail_learning_threshold",
            "session_halt_or_guardian_risk_state_not_normal",
        ],
        "boundary": "artifact-only; no DB, Bybit, order, config, risk, auth, or runtime mutation",
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


def build_plan_from_file(
    scorecard_json: Path,
    *,
    now_utc: dt.datetime | None = None,
    cfg: LearningLanePolicyConfig | None = None,
) -> dict[str, Any]:
    """Read a scorecard artifact and produce a fail-soft plan."""
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    payload, err = _read_json(scorecard_json)
    if err:
        return _source_failure_plan(
            now_utc=now,
            scorecard_path=scorecard_json,
            source_error=err,
        )
    assert payload is not None
    return build_plan_from_payload(
        payload,
        now_utc=now,
        cfg=cfg,
        scorecard_path=scorecard_json,
    )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _default_scorecard_json() -> Path:
    data_dir = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))
    return data_dir / "cost_gate_counterfactual" / "cost_gate_reject_counterfactual_latest.json"


def _default_output() -> Path:
    data_dir = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))
    return data_dir / "cost_gate_learning_lane" / "demo_learning_lane_plan_latest.json"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scorecard-json", type=Path, default=_default_scorecard_json())
    parser.add_argument("--output", type=Path, default=_default_output())
    parser.add_argument("--max-probe-side-cells", type=int, default=4)
    parser.add_argument("--max-probe-orders-per-side-cell", type=int, default=3)
    parser.add_argument("--max-total-probe-orders", type=int, default=8)
    parser.add_argument("--cooldown-minutes", type=int, default=30)
    parser.add_argument("--max-scorecard-age-hours", type=int, default=24)
    parser.add_argument("--min-candidate-sample", type=int, default=100)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    cfg = LearningLanePolicyConfig(
        max_probe_side_cells=args.max_probe_side_cells,
        max_probe_orders_per_side_cell=args.max_probe_orders_per_side_cell,
        max_total_probe_orders=args.max_total_probe_orders,
        cooldown_minutes=args.cooldown_minutes,
        max_scorecard_age_hours=args.max_scorecard_age_hours,
        min_candidate_sample=args.min_candidate_sample,
    )
    validate_policy_config(cfg)
    plan = build_plan_from_file(args.scorecard_json, cfg=cfg)
    _atomic_write_json(args.output, plan)
    if args.print_json:
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
