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
EXPECTED_SEALED_REPLAY_SCHEMA_VERSION = "horizon_specific_sealed_replay_packet_v1"
SEALED_REPLAY_READY_STATUS = "SEALED_HORIZON_REPLAY_READY_FOR_OPERATOR_REVIEW"
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


def _sort_float(value: Any) -> float:
    parsed = _float(value)
    return parsed if parsed is not None else float("-inf")


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


def _side_cell_parts(side_cell_key: Any) -> tuple[str | None, str | None, str | None]:
    parts = str(side_cell_key or "").split("|")
    if len(parts) != 3 or not all(parts):
        return None, None, None
    return parts[0], parts[1], parts[2]


def _effective_sample_count(row: dict[str, Any]) -> int:
    sample_count = _int(row.get("sample_count_for_gate"))
    if sample_count > 0:
        return sample_count
    distinct_ts = _int(row.get("distinct_ts"))
    return distinct_ts if distinct_ts > 0 else _int(row.get("n"))


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
            _effective_sample_count(row),
        ),
        reverse=True,
    )


def _bounded_score(value: float, scale: float, weight: float) -> float:
    if scale <= 0:
        return 0.0
    return min(max(value, 0.0) / scale, 1.0) * weight


def _profit_thresholds(scorecard: dict[str, Any]) -> dict[str, float]:
    thresholds = _dict(scorecard.get("thresholds"))
    return {
        "friction_bps": _float(thresholds.get("friction_bps")) or 4.0,
        "min_probe_avg_net_bps": _float(thresholds.get("min_probe_avg_net_bps")) or 0.0,
        "min_probe_net_positive_pct": (
            _float(thresholds.get("min_probe_net_positive_pct")) or 55.0
        ),
    }


def _profit_priority_components(
    row: dict[str, Any],
    thresholds: dict[str, float],
) -> dict[str, float]:
    n = max(_effective_sample_count(row), 0)
    avg_net = _float(row.get("avg_net_bps")) or 0.0
    p50_gross = _float(row.get("p50_gross_bps")) or 0.0
    net_positive_pct = _float(row.get("net_positive_pct")) or 0.0
    return {
        "sample_score": min(math.log10(n + 1) / 4.0, 1.0) * 25.0,
        "avg_net_score": _bounded_score(
            avg_net - thresholds["min_probe_avg_net_bps"],
            100.0,
            25.0,
        ),
        "median_margin_score": _bounded_score(
            p50_gross - thresholds["friction_bps"],
            50.0,
            25.0,
        ),
        "hit_rate_score": _bounded_score(net_positive_pct - 50.0, 50.0, 25.0),
    }


def _profit_priority_tier(action: str, score: float) -> str:
    if action == "LEARNING_PROBE_CANDIDATE":
        if score >= 70.0:
            return "HIGH_PRIORITY_BOUNDED_DEMO_LEARNING"
        if score >= 60.0:
            return "MEDIUM_PRIORITY_BOUNDED_DEMO_LEARNING"
        return "LOW_PRIORITY_BOUNDED_DEMO_LEARNING"
    if action == "BLOCK_CONFIRMED":
        return "KEEP_BLOCKED_CONFIRMED"
    if action == "DATA_COVERAGE_BLOCKER":
        return "DATA_FIX_BEFORE_PROFIT_JUDGMENT"
    if action == "INSUFFICIENT_SAMPLE":
        return "COLLECT_MORE_SAMPLE"
    if action == "TAIL_ONLY_WATCH":
        return "TAIL_ONLY_WATCH_NO_PROBE"
    return "NO_PROBE"


def _profit_next_action(action: str) -> str:
    if action == "LEARNING_PROBE_CANDIDATE":
        return "operator_review_ranked_side_cell_for_bounded_demo_learning_lane"
    if action == "BLOCK_CONFIRMED":
        return "keep_main_cost_gate_block_for_side_cell"
    if action == "DATA_COVERAGE_BLOCKER":
        return "fix_data_coverage_before_profit_judgment"
    if action == "INSUFFICIENT_SAMPLE":
        return "continue_collecting_reject_counterfactual_samples"
    if action == "TAIL_ONLY_WATCH":
        return "continue_watch_without_probe_authority"
    return "do_not_probe_side_cell"


def _derive_profit_opportunity_ranking(scorecard: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in _list(scorecard.get("rows")) if isinstance(row, dict)]
    if not rows:
        return {}
    thresholds = _profit_thresholds(scorecard)
    ranked_rows: list[dict[str, Any]] = []
    for row in rows:
        action = str(row.get("learning_lane_action") or "UNSCORABLE")
        components = _profit_priority_components(row, thresholds)
        score = round(sum(components.values()), 4)
        avg_net = _float(row.get("avg_net_bps"))
        p50_gross = _float(row.get("p50_gross_bps"))
        net_positive_pct = _float(row.get("net_positive_pct"))
        ranked_rows.append(
            {
                "side_cell_key": _side_cell_key(row),
                "strategy_name": row.get("strategy_name"),
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "reject_reason_code": row.get("reject_reason_code"),
                "learning_lane_action": action,
                "learning_lane_reason": row.get("learning_lane_reason"),
                "priority_tier": _profit_priority_tier(action, score),
                "priority_score": score,
                "priority_components": {
                    key: round(value, 4) for key, value in components.items()
                },
                "n": _int(row.get("n")),
                "sample_count_for_gate": _effective_sample_count(row),
                "distinct_ts": _int(row.get("distinct_ts")),
                "rows_per_distinct_ts": _float(row.get("rows_per_distinct_ts")),
                "timespan_minutes": _float(row.get("timespan_minutes")),
                "avg_net_bps": avg_net,
                "p50_gross_bps": p50_gross,
                "p90_gross_bps": _float(row.get("p90_gross_bps")),
                "net_positive_pct": net_positive_pct,
                "next_action": _profit_next_action(action),
                "order_authority": "NOT_GRANTED",
                "main_cost_gate_adjustment": "NONE",
                "promotion_evidence": False,
            }
        )
    action_order = {
        "LEARNING_PROBE_CANDIDATE": 0,
        "TAIL_ONLY_WATCH": 1,
        "INSUFFICIENT_SAMPLE": 2,
        "DATA_COVERAGE_BLOCKER": 3,
        "NO_PROBE": 4,
        "UNSCORABLE": 5,
        "BLOCK_CONFIRMED": 6,
    }
    ranked_rows.sort(
        key=lambda row: (
            action_order.get(str(row.get("learning_lane_action")), 9),
            -(float(row.get("priority_score") or 0.0)),
            -_sort_float(row.get("avg_net_bps")),
            -_effective_sample_count(row),
        )
    )
    candidate_count = sum(
        1 for row in ranked_rows
        if row.get("learning_lane_action") == "LEARNING_PROBE_CANDIDATE"
    )
    status = (
        "PROFIT_LEARNING_CANDIDATES_PRESENT"
        if candidate_count
        else "NO_PROFIT_LEARNING_CANDIDATE"
    )
    return {
        "schema_version": "cost_gate_profit_opportunity_ranking_v1",
        "source_kind": "derived_from_scorecard_rows",
        "status": status,
        "next_trigger": (
            "operator_review_top_ranked_side_cells_for_bounded_demo_learning_lane"
            if candidate_count
            else "keep_cost_gate_and_continue_research"
        ),
        "candidate_count": candidate_count,
        "top_side_cells": ranked_rows[:20],
    }


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
        "profit_priority_score": _float(row.get("priority_score")),
        "profit_priority_tier": row.get("priority_tier"),
        "profit_priority_components": row.get("priority_components"),
        "profit_priority_next_action": row.get("next_action"),
        "source_kind": row.get("source_kind"),
        "outcome_horizon_minutes": _int(row.get("outcome_horizon_minutes")),
        "learning_outcome_horizon_minutes": _int(
            row.get("learning_outcome_horizon_minutes")
        ),
        "primary_horizon_minutes": _int(row.get("primary_horizon_minutes")),
        "primary_horizon_action": row.get("primary_horizon_action"),
        "sealed_horizon_replay": row.get("sealed_horizon_replay"),
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
    outcome_horizon = _int(
        compact.get("outcome_horizon_minutes")
        or compact.get("learning_outcome_horizon_minutes")
    )
    compact["probe_proposal"] = {
        "mode": "demo_only_learning_probe",
        "max_probe_orders": max_probe_orders,
        "cooldown_minutes": cfg.cooldown_minutes,
        "requires_runtime_policy_adapter": True,
        "requires_probe_attempt_logging": True,
        "requires_probe_outcome_logging": True,
    }
    if outcome_horizon > 0:
        compact["probe_proposal"]["outcome_horizon_minutes"] = outcome_horizon
        compact["probe_proposal"]["learning_outcome_horizon_minutes"] = outcome_horizon
        compact["probe_proposal"]["requires_candidate_horizon_outcome_logging"] = True
    compact["guardrails"] = {
        "main_cost_gate_adjustment": "NONE",
        "may_bypass_main_live_gate": False,
        "demo_only": True,
        "paper_not_promotion_evidence": True,
        "notional_or_qty_not_granted_by_artifact": True,
    }
    return compact


def _sealed_replay_failed_gates(packet: dict[str, Any]) -> list[str]:
    replay = _dict(packet.get("replay_evaluation"))
    failed = replay.get("failed_gate_names")
    return [str(item) for item in failed] if isinstance(failed, list) else []


def _sealed_replay_source_error(packet: dict[str, Any] | None) -> str | None:
    if not packet:
        return None
    if packet.get("schema_version") != EXPECTED_SEALED_REPLAY_SCHEMA_VERSION:
        return "unexpected_horizon_sealed_replay_schema"
    if packet.get("status") != SEALED_REPLAY_READY_STATUS:
        return "horizon_sealed_replay_not_ready"
    answers = _dict(packet.get("answers"))
    boundaries = _dict(packet.get("global_boundaries"))
    if answers.get("sealed_replay_passed") is not True:
        return "horizon_sealed_replay_not_passed"
    if answers.get("global_cost_gate_lowering_recommended") is not False:
        return "horizon_sealed_replay_recommends_cost_gate_lowering"
    if answers.get("order_authority_granted") is not False:
        return "horizon_sealed_replay_grants_order_authority"
    if answers.get("probe_authority_granted") is not False:
        return "horizon_sealed_replay_grants_probe_authority"
    if boundaries.get("order_authority") != "NOT_GRANTED":
        return "horizon_sealed_replay_boundary_order_authority_not_closed"
    if boundaries.get("main_cost_gate_adjustment") != "NONE":
        return "horizon_sealed_replay_boundary_cost_gate_adjustment_not_none"
    if _sealed_replay_failed_gates(packet):
        return "horizon_sealed_replay_has_failed_gates"
    return None


def _sealed_replay_candidate_row(
    packet: dict[str, Any] | None,
    *,
    thresholds: dict[str, float],
) -> tuple[dict[str, Any] | None, str | None]:
    source_error = _sealed_replay_source_error(packet)
    if source_error or not packet:
        return None, source_error
    selection = _dict(_dict(packet.get("selection")).get("selected"))
    replay = _dict(packet.get("replay_evaluation"))
    best = _dict(replay.get("best_horizon"))
    primary = _dict(replay.get("primary_horizon"))
    side_cell_key = replay.get("side_cell_key") or selection.get("side_cell_key")
    strategy, symbol, side = _side_cell_parts(side_cell_key)
    if not strategy or not symbol or not side:
        return None, "horizon_sealed_replay_side_cell_invalid"

    sample_count = _int(best.get("sample_count_for_gate"))
    row: dict[str, Any] = {
        "side_cell_key": side_cell_key,
        "strategy_name": strategy,
        "symbol": symbol,
        "side": side,
        "reject_reason_code": "cost_gate_js_demo_negative_edge",
        "n": sample_count,
        "sample_count_for_gate": sample_count,
        "avg_net_bps": _float(best.get("avg_net_bps")),
        "p50_gross_bps": _float(best.get("p50_gross_bps")),
        "net_positive_pct": _float(best.get("net_positive_pct")),
        "learning_lane_action": "LEARNING_PROBE_CANDIDATE",
        "learning_lane_reason": (
            "sealed_horizon_replay_revalidated_retiming_candidate"
        ),
        "next_action": (
            "accumulate_blocked_signal_outcomes_at_sealed_candidate_horizon"
        ),
        "order_authority": "NOT_GRANTED",
        "main_cost_gate_adjustment": "NONE",
        "promotion_evidence": False,
        "source_kind": "horizon_specific_sealed_replay",
        "outcome_horizon_minutes": _int(best.get("horizon_minutes")),
        "learning_outcome_horizon_minutes": _int(best.get("horizon_minutes")),
        "primary_horizon_minutes": _int(primary.get("horizon_minutes")),
        "primary_horizon_action": primary.get("learning_lane_action"),
        "sealed_horizon_replay": {
            "schema_version": packet.get("schema_version"),
            "status": packet.get("status"),
            "next_action": packet.get("next_action"),
            "side_cell_key": side_cell_key,
            "best_horizon_minutes": _int(best.get("horizon_minutes")),
            "primary_horizon_minutes": _int(primary.get("horizon_minutes")),
            "primary_horizon_action": primary.get("learning_lane_action"),
            "best_avg_net_bps": _float(best.get("avg_net_bps")),
            "best_p50_gross_bps": _float(best.get("p50_gross_bps")),
            "best_net_positive_pct": _float(best.get("net_positive_pct")),
            "sample_count_for_gate": sample_count,
            "failed_gate_names": _sealed_replay_failed_gates(packet),
            "source": packet.get("source"),
        },
    }
    components = _profit_priority_components(row, thresholds)
    score = round(sum(components.values()), 4)
    row["priority_score"] = score
    row["priority_tier"] = "HIGH_PRIORITY_SEALED_HORIZON_DEMO_LEARNING"
    row["priority_components"] = {
        key: round(value, 4) for key, value in components.items()
    }
    return row, None


def _merge_sealed_replay_candidate(
    ranked: list[dict[str, Any]],
    sealed_row: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not sealed_row:
        return ranked
    sealed_key = _side_cell_key(sealed_row)
    merged: list[dict[str, Any]] = [sealed_row]
    for row in ranked:
        if _side_cell_key(row) == sealed_key:
            continue
        merged.append(row)
    return merged


def _ranking_probe_rows(
    scorecard: dict[str, Any],
    cfg: LearningLanePolicyConfig,
) -> tuple[list[dict[str, Any]], dict[str, Any], bool]:
    ranking = _dict(scorecard.get("profit_opportunity_ranking"))
    if ranking.get("schema_version") != "cost_gate_profit_opportunity_ranking_v1":
        ranking = _derive_profit_opportunity_ranking(scorecard)
    if ranking.get("schema_version") != "cost_gate_profit_opportunity_ranking_v1":
        return [], {}, False
    rows = [
        row for row in _list(ranking.get("top_side_cells"))
        if isinstance(row, dict)
        and row.get("learning_lane_action") == "LEARNING_PROBE_CANDIDATE"
        and _effective_sample_count(row) >= cfg.min_candidate_sample
        and row.get("order_authority") == "NOT_GRANTED"
        and row.get("main_cost_gate_adjustment") == "NONE"
        and row.get("promotion_evidence") is False
    ]
    return rows, ranking, True


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
    horizon_sealed_replay: dict[str, Any] | None = None,
    horizon_sealed_replay_path: Path | None = None,
    horizon_sealed_replay_error: str | None = None,
) -> dict[str, Any]:
    """Build the guarded demo-learning lane plan from a scorecard payload."""
    cfg = cfg or LearningLanePolicyConfig()
    validate_policy_config(cfg)
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    scorecard = _dict(payload.get("learning_lane_scorecard"))
    horizon_stability = _dict(scorecard.get("horizon_stability_scorecard"))
    stability_by_side_cell = {
        str(row.get("side_cell_key")): row
        for row in _list(horizon_stability.get("top_side_cells"))
        if isinstance(row, dict) and row.get("side_cell_key")
    }
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
    ranking_probe_rows, profit_ranking, has_profit_ranking = _ranking_probe_rows(scorecard, cfg)
    ranking_source = (
        str(profit_ranking.get("source_kind") or "profit_opportunity_ranking")
        if has_profit_ranking
        else "legacy_scorecard_candidates"
    )
    if has_profit_ranking:
        ranked = ranking_probe_rows
    else:
        probe_rows = [
            row for row in _list(scorecard.get("probe_candidates"))
            if isinstance(row, dict)
            and row.get("learning_lane_action") == "LEARNING_PROBE_CANDIDATE"
            and _effective_sample_count(row) >= cfg.min_candidate_sample
        ]
        if not probe_rows:
            probe_rows = [
                row for row in rows
                if isinstance(row, dict)
                and row.get("learning_lane_action") == "LEARNING_PROBE_CANDIDATE"
                and _effective_sample_count(row) >= cfg.min_candidate_sample
            ]
        ranked = _rank_candidates(probe_rows)
    thresholds = _profit_thresholds(scorecard)
    sealed_row, sealed_source_error = _sealed_replay_candidate_row(
        horizon_sealed_replay,
        thresholds=thresholds,
    )
    if horizon_sealed_replay_error:
        sealed_source_error = horizon_sealed_replay_error
        sealed_row = None
    ranked = _merge_sealed_replay_candidate(ranked, sealed_row)
    selected = ranked[: cfg.max_probe_side_cells]
    per_cell_budget = _probe_budget_for_candidates(len(selected), cfg)
    probe_candidates = []
    for row in selected:
        candidate = _candidate_to_probe(row, max_probe_orders=per_cell_budget, cfg=cfg)
        stability = stability_by_side_cell.get(str(candidate.get("side_cell_key")))
        if stability:
            candidate["horizon_stability"] = {
                "status": stability.get("status"),
                "reason": stability.get("reason"),
                "candidate_horizons": stability.get("candidate_horizons"),
                "best_horizon_minutes": stability.get("best_horizon_minutes"),
                "best_avg_net_bps": stability.get("best_avg_net_bps"),
                "best_net_positive_pct": stability.get("best_net_positive_pct"),
            }
        probe_candidates.append(candidate)
    if source_error:
        probe_candidates = []
        per_cell_budget = 0
    selected_side_cells = {
        str(row.get("side_cell_key")) for row in probe_candidates if row.get("side_cell_key")
    }
    do_not_probe = [
        _compact_row(row) for row in _rank_candidates([
            row for row in rows
            if isinstance(row, dict)
            and row.get("learning_lane_action") == "BLOCK_CONFIRMED"
            and _side_cell_key(row) not in selected_side_cells
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
            "profit_opportunity_ranking_schema_version": profit_ranking.get("schema_version"),
            "profit_opportunity_ranking_status": profit_ranking.get("status"),
            "profit_opportunity_ranking_next_trigger": profit_ranking.get("next_trigger"),
            "probe_candidate_ranking_source": ranking_source,
            "horizon_stability_schema_version": horizon_stability.get("schema_version"),
            "horizon_stability_status": horizon_stability.get("status"),
            "horizon_stability_next_trigger": horizon_stability.get("next_trigger"),
            "horizon_stability_horizons_minutes": horizon_stability.get(
                "horizons_minutes"
            ),
            "horizon_sealed_replay_path": (
                str(horizon_sealed_replay_path)
                if horizon_sealed_replay_path is not None
                else None
            ),
            "horizon_sealed_replay_schema_version": (
                horizon_sealed_replay or {}
            ).get("schema_version"),
            "horizon_sealed_replay_status": (horizon_sealed_replay or {}).get("status"),
            "horizon_sealed_replay_source_error": sealed_source_error,
            "horizon_sealed_replay_side_cell_key": (
                _dict(_dict(horizon_sealed_replay or {}).get("replay_evaluation")).get(
                    "side_cell_key"
                )
            ),
            "horizon_sealed_replay_best_horizon_minutes": _int(
                _dict(
                    _dict(_dict(horizon_sealed_replay or {}).get("replay_evaluation")).get(
                        "best_horizon"
                    )
                ).get("horizon_minutes")
            ),
            "horizon_sealed_replay_failed_gate_names": _sealed_replay_failed_gates(
                horizon_sealed_replay or {}
            ),
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
            "record_candidate_summary_and_horizon_in_learning_ledger",
            "refresh_blocked_signal_outcomes_at_candidate_horizon",
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
    horizon_sealed_replay_json: Path | None = None,
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
    horizon_sealed_replay = None
    horizon_sealed_replay_error = None
    if horizon_sealed_replay_json is not None:
        horizon_sealed_replay, horizon_sealed_replay_error = _read_json(
            horizon_sealed_replay_json
        )
    return build_plan_from_payload(
        payload,
        now_utc=now,
        cfg=cfg,
        scorecard_path=scorecard_json,
        horizon_sealed_replay=horizon_sealed_replay,
        horizon_sealed_replay_path=horizon_sealed_replay_json,
        horizon_sealed_replay_error=horizon_sealed_replay_error,
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
    parser.add_argument("--horizon-sealed-replay-json", type=Path)
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
    plan = build_plan_from_file(
        args.scorecard_json,
        cfg=cfg,
        horizon_sealed_replay_json=args.horizon_sealed_replay_json,
    )
    _atomic_write_json(args.output, plan)
    if args.print_json:
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
