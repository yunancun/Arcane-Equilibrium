#!/usr/bin/env python3
"""Build an operator-facing profit-learning decision packet.

This module stitches together existing read-only artifacts:

* demo data-flow monitor output
* cost-gate reject counterfactual scorecard
* bounded demo-learning lane plan
* learning-lane activation preflight / stack health
* blocked-signal outcome review

It does not query PG, call Bybit, place orders, lower the main Cost Gate, or
grant probe authority. Missing inputs fail closed into explicit next actions.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any


PROFIT_LEARNING_DECISION_PACKET_SCHEMA_VERSION = (
    "cost_gate_profit_learning_decision_packet_v1"
)
DEFAULT_MAX_ARTIFACT_AGE_HOURS = 24
BOUNDARY = (
    "artifact-only decision packet; no PG query/write, Bybit call, order, "
    "config, risk, auth, runtime mutation, main Cost Gate lowering, or probe authority"
)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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


def _generated_at(payload: dict[str, Any]) -> Any:
    return (
        payload.get("generated_at_utc")
        or payload.get("generated")
        or payload.get("ts_utc")
    )


def _artifact_summary(
    *,
    name: str,
    path: Path | None,
    payload: dict[str, Any] | None,
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    present = isinstance(payload, dict) and bool(payload)
    generated_at = _generated_at(payload or {}) if present else None
    age = _age_seconds(generated_at, now_utc=now_utc) if generated_at else None
    if not present:
        status = "MISSING"
    elif age is None:
        status = "PRESENT_UNKNOWN_AGE"
    elif age > max_age_seconds:
        status = "STALE"
    else:
        status = "FRESH"
    return {
        "name": name,
        "path": str(path) if path else None,
        "status": status,
        "present": present,
        "generated_at_utc": generated_at,
        "age_seconds": age,
        "max_age_seconds": max_age_seconds,
        "schema_version": (payload or {}).get("schema_version") if present else None,
    }


def _data_flow_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    return _dict((payload or {}).get("summary"))


def _counterfactual_scorecard(payload: dict[str, Any] | None) -> dict[str, Any]:
    return _dict((payload or {}).get("learning_lane_scorecard"))


def _profit_ranking(counterfactual: dict[str, Any] | None) -> dict[str, Any]:
    return _dict(_counterfactual_scorecard(counterfactual).get("profit_opportunity_ranking"))


def _horizon_stability(counterfactual: dict[str, Any] | None) -> dict[str, Any]:
    return _dict(_counterfactual_scorecard(counterfactual).get("horizon_stability_scorecard"))


def _top_side_cells(counterfactual: dict[str, Any] | None, limit: int = 5) -> list[dict[str, Any]]:
    ranking = _profit_ranking(counterfactual)
    stability = _horizon_stability(counterfactual)
    horizon_by_key = {
        str(row.get("side_cell_key")): row
        for row in _list(stability.get("top_side_cells"))
        if isinstance(row, dict) and row.get("side_cell_key")
    }
    rows: list[dict[str, Any]] = []
    for row in _list(ranking.get("top_side_cells")):
        if not isinstance(row, dict):
            continue
        enriched = dict(row)
        horizon = horizon_by_key.get(str(row.get("side_cell_key") or ""))
        if horizon:
            enriched["horizon_status"] = horizon.get("status")
            enriched["candidate_horizons_minutes"] = horizon.get("candidate_horizons")
            enriched["block_confirmed_horizons_minutes"] = (
                horizon.get("block_confirmed_horizons")
            )
            enriched["best_horizon_minutes"] = horizon.get("best_horizon_minutes")
            enriched["best_horizon_avg_net_bps"] = horizon.get("best_avg_net_bps")
            enriched["best_horizon_net_positive_pct"] = horizon.get(
                "best_net_positive_pct"
            )
        rows.append(enriched)
    return rows[:limit]


def _plan_ready(plan: dict[str, Any] | None) -> bool:
    if not isinstance(plan, dict) or not plan:
        return False
    return (
        plan.get("schema_version") == "cost_gate_demo_learning_lane_plan_v1"
        and plan.get("status") == "READY_FOR_DEMO_LEARNING_PROBE"
        and plan.get("gate_status") == "OPERATOR_REVIEW"
        and _int(plan.get("selected_probe_candidate_count")) > 0
        and plan.get("order_authority", "NOT_GRANTED") == "NOT_GRANTED"
        and plan.get("main_cost_gate_adjustment", "NONE") == "NONE"
    )


def _activation_status(
    activation_preflight: dict[str, Any] | None,
    stack_health: dict[str, Any] | None,
) -> str | None:
    if isinstance(activation_preflight, dict) and activation_preflight:
        return str(activation_preflight.get("status") or "")
    if isinstance(stack_health, dict) and stack_health:
        return str(stack_health.get("status") or "")
    return None


def _activation_next_actions(
    activation_preflight: dict[str, Any] | None,
    stack_health: dict[str, Any] | None,
) -> list[str]:
    for payload in (activation_preflight, stack_health):
        if isinstance(payload, dict):
            actions = payload.get("next_actions")
            if isinstance(actions, list) and actions:
                return [str(item) for item in actions]
            action = payload.get("next_action")
            if action:
                return [str(action)]
    return []


def _blocked_review_status(blocked_review: dict[str, Any] | None) -> str | None:
    if not isinstance(blocked_review, dict) or not blocked_review:
        return None
    return str(blocked_review.get("status") or "")


def _blocked_review_candidates(blocked_review: dict[str, Any] | None) -> int:
    if not isinstance(blocked_review, dict) or not blocked_review:
        return 0
    return _int(
        blocked_review.get("review_candidate_count")
        or blocked_review.get("candidate_count")
        or blocked_review.get("demo_probe_authority_review_candidate_count")
    )


def _sealed_learning_review_ready(evidence: dict[str, Any] | None) -> bool:
    payload = _dict(evidence)
    answers = _dict(payload.get("answers"))
    return (
        payload.get("schema_version") == "sealed_horizon_learning_evidence_v1"
        and payload.get("status") == "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT"
        and answers.get("candidate_clears_operator_review_gate") is True
        and answers.get("order_authority_granted") is not True
        and answers.get("probe_authority_granted") is not True
        and answers.get("global_cost_gate_lowering_recommended") is not True
    )


def _sealed_learning_summary(evidence: dict[str, Any] | None) -> dict[str, Any]:
    payload = _dict(evidence)
    if not payload:
        return {
            "status": None,
            "side_cell_key": None,
            "outcome_horizon_minutes": None,
            "blocked_signal_outcome_count": 0,
            "avg_net_bps": None,
            "net_positive_pct": None,
            "review_ready": False,
        }
    outcomes = _dict(payload.get("outcomes"))
    review = _dict(payload.get("review"))
    return {
        "status": payload.get("status"),
        "side_cell_key": payload.get("side_cell_key")
        or review.get("top_side_cell_key"),
        "source_kind": payload.get("source_kind"),
        "outcome_horizon_minutes": payload.get("outcome_horizon_minutes"),
        "blocked_signal_outcome_count": outcomes.get(
            "blocked_signal_outcome_count"
        )
        or review.get("blocked_signal_outcome_count")
        or 0,
        "avg_gross_bps": outcomes.get("avg_gross_bps"),
        "avg_net_bps": outcomes.get("avg_net_bps")
        or review.get("avg_blocked_signal_outcome_net_bps"),
        "net_positive_pct": outcomes.get("net_positive_pct")
        or review.get("blocked_signal_net_positive_pct"),
        "review_candidate_side_cell_count": review.get(
            "review_candidate_side_cell_count"
        ),
        "top_side_cell_status": review.get("top_side_cell_status"),
        "review_ready": _sealed_learning_review_ready(payload),
    }


def _counterfactual_has_learning_candidates(counterfactual: dict[str, Any] | None) -> bool:
    scorecard = _counterfactual_scorecard(counterfactual)
    ranking = _profit_ranking(counterfactual)
    stability = _horizon_stability(counterfactual)
    return (
        scorecard.get("status") == "LEARNING_LANE_PROBE_CANDIDATES_PRESENT"
        or ranking.get("status") == "PROFIT_LEARNING_CANDIDATES_PRESENT"
        or str(stability.get("status") or "").endswith(
            "PROFIT_LEARNING_CANDIDATES_PRESENT"
        )
        or _int(ranking.get("candidate_count")) > 0
    )


def _counterfactual_block_confirmed(counterfactual: dict[str, Any] | None) -> bool:
    scorecard = _counterfactual_scorecard(counterfactual)
    action_counts = _dict(scorecard.get("action_counts"))
    stability = _horizon_stability(counterfactual)
    return (
        _int(action_counts.get("BLOCK_CONFIRMED")) > 0
        or stability.get("status") == "MULTI_HORIZON_BLOCK_CONFIRMED"
    )


def _data_flow_observations(data_flow: dict[str, Any] | None) -> dict[str, Any]:
    summary = _data_flow_summary(data_flow)
    answers = _dict(summary.get("answers"))
    key_counts = _dict(summary.get("key_counts"))
    return {
        "status": summary.get("status"),
        "short_window_empty": answers.get("short_window_empty") is True,
        "broad_window_has_any_data": answers.get("broad_window_has_any_data") is True,
        "broad_window_has_candidate_or_reject_data": (
            answers.get("broad_window_has_candidate_or_reject_data") is True
        ),
        "cost_gate_rejects_recorded": answers.get("cost_gate_rejects_recorded") is True,
        "orders_present": answers.get("orders_present") is True,
        "fills_present": answers.get("fills_present") is True,
        "broad_cost_gate_rejects": _int(key_counts.get("broad_cost_gate_rejects")),
        "broad_orders": _int(key_counts.get("broad_orders")),
        "broad_fills": _int(key_counts.get("broad_fills")),
    }


def _decision(
    *,
    data_flow: dict[str, Any] | None,
    counterfactual: dict[str, Any] | None,
    plan: dict[str, Any] | None,
    activation_preflight: dict[str, Any] | None,
    blocked_review: dict[str, Any] | None,
    sealed_horizon_learning_evidence: dict[str, Any] | None,
    stack_health: dict[str, Any] | None,
    artifact_summaries: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    flow = _data_flow_observations(data_flow)
    data_flow_status = str(flow.get("status") or "")
    counterfresh = artifact_summaries["counterfactual"]["status"] == "FRESH"
    activation_status = _activation_status(activation_preflight, stack_health)
    review_status = _blocked_review_status(blocked_review)
    sealed_summary = _sealed_learning_summary(sealed_horizon_learning_evidence)
    sealed_review_ready = (
        artifact_summaries["sealed_horizon_learning_evidence"]["status"] == "FRESH"
        and sealed_summary["review_ready"] is True
    )

    if artifact_summaries["data_flow"]["present"] is not True:
        return {
            "status": "DATA_FLOW_MONITOR_REQUIRED",
            "reason": "demo_data_flow_monitor_artifact_missing",
            "next_actions": ["run_demo_data_flow_monitor_for_1h_4h_24h"],
        }

    if data_flow_status == "NO_DEMO_DATA_ANY_WINDOW":
        return {
            "status": "RESTORE_DEMO_DATA_FLOW",
            "reason": "no_demo_signal_candidate_risk_order_or_fill_data_in_broad_window",
            "next_actions": ["restore_demo_signal_pipeline_before_cost_gate_learning_review"],
        }

    if (
        flow["cost_gate_rejects_recorded"] is not True
        and flow["broad_window_has_candidate_or_reject_data"] is not True
    ):
        return {
            "status": "WAIT_FOR_REJECT_OR_CANDIDATE_DATA",
            "reason": "demo_flow_has_no_cost_gate_or_candidate_rows_to_score",
            "next_actions": ["keep_data_flow_monitor_running_until_candidate_or_reject_rows_exist"],
        }

    if artifact_summaries["counterfactual"]["present"] is not True:
        return {
            "status": "RUN_REJECT_COUNTERFACTUAL",
            "reason": "cost_gate_rejects_are_recorded_but_counterfactual_scorecard_missing",
            "next_actions": ["run_cost_gate_reject_counterfactual_multi_horizon_scorecard"],
        }

    if not counterfresh:
        return {
            "status": "REFRESH_REJECT_COUNTERFACTUAL",
            "reason": "cost_gate_counterfactual_scorecard_missing_timestamp_or_stale",
            "next_actions": ["refresh_cost_gate_reject_counterfactual_before_policy_review"],
        }

    if _counterfactual_has_learning_candidates(counterfactual):
        if not _plan_ready(plan):
            return {
                "status": "BUILD_OR_REFRESH_BOUNDED_LEARNING_PLAN",
                "reason": "counterfactual_candidates_present_but_ready_plan_missing",
                "next_actions": ["build_cost_gate_demo_learning_lane_plan_from_scorecard"],
            }
        if sealed_review_ready:
            return {
                "status": "OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE",
                "reason": (
                    "sealed_horizon_learning_evidence_clears_review_thresholds;"
                    "production_learning_lane_activation_still_requires_operator_control"
                ),
                "next_actions": [
                    "operator_review_sealed_horizon_learning_evidence_before_bounded_demo_probe",
                    "activate_or_repair_cost_gate_learning_lane_stack_before_runtime_probe",
                ],
            }
        if activation_status is None:
            return {
                "status": "RUN_LEARNING_LANE_ACTIVATION_PREFLIGHT",
                "reason": "ready_plan_present_but_activation_or_stack_health_missing",
                "next_actions": ["run_cost_gate_learning_lane_activation_preflight"],
            }
        if activation_status in {
            "SOURCE_NOT_READY",
            "NOT_INSTALLED",
            "INSTALLED_NOT_FIRING",
            "FIRING_NO_RECENT_STATUS",
            "PLAN_NOT_READY",
            "NOT_ACCUMULATING",
            "LOOP_RUNNING_NO_LEDGER_ROWS",
            "ADMISSION_ROWS_NEED_REFRESH_LOOP",
            "ADMISSION_ONLY_NEEDS_OUTCOME_REFRESH",
            "LEARNING_LOOP_STALE",
            "LEARNING_LOOP_ERROR",
        }:
            return {
                "status": "ACTIVATE_OR_REPAIR_LEARNING_STACK",
                "reason": f"learning_stack_not_accumulating: {activation_status}",
                "next_actions": (
                    _activation_next_actions(activation_preflight, stack_health)
                    or ["repair_or_activate_cost_gate_learning_lane_stack"]
                ),
            }
        if review_status is None:
            return {
                "status": "WAIT_FOR_BLOCKED_OUTCOME_REVIEW",
                "reason": "learning_lane_ready_or_active_but_blocked_outcome_review_missing",
                "next_actions": ["run_or_wait_for_blocked_signal_outcome_review"],
            }
        if (
            review_status == "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT"
            or _blocked_review_candidates(blocked_review) > 0
        ):
            return {
                "status": "OPERATOR_REVIEW_DEMO_PROBE_CANDIDATES",
                "reason": "blocked_signal_outcomes_clear_review_thresholds",
                "next_actions": ["operator_review_blocked_outcome_scorecard_before_probe_authority"],
            }
        return {
            "status": "CONTINUE_BLOCKED_OUTCOME_COLLECTION",
            "reason": "no_blocked_outcome_review_candidate_yet",
            "next_actions": ["continue_recording_and_refreshing_blocked_signal_outcomes"],
        }

    if _counterfactual_block_confirmed(counterfactual):
        return {
            "status": "KEEP_COST_GATE_AND_CONTINUE_COLLECTION",
            "reason": "counterfactual_rows_confirm_some_blocks_after_friction",
            "next_actions": ["keep_main_cost_gate_and_continue_counterfactual_collection"],
        }

    return {
        "status": "NO_READY_PROFIT_LEARNING_CANDIDATE",
        "reason": "counterfactual_scorecard_has_no_ready_learning_candidates",
        "next_actions": ["continue_collecting_cost_gate_reject_counterfactuals"],
    }


def build_profit_learning_decision_packet(
    *,
    data_flow: dict[str, Any] | None = None,
    counterfactual: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
    activation_preflight: dict[str, Any] | None = None,
    blocked_review: dict[str, Any] | None = None,
    sealed_horizon_learning_evidence: dict[str, Any] | None = None,
    stack_health: dict[str, Any] | None = None,
    paths: dict[str, Path | None] | None = None,
    now_utc: dt.datetime | None = None,
    max_artifact_age_hours: int = DEFAULT_MAX_ARTIFACT_AGE_HOURS,
) -> dict[str, Any]:
    """Build a fail-closed next-step packet from existing artifacts."""
    if max_artifact_age_hours < 1 or max_artifact_age_hours > 24 * 14:
        raise ValueError("max_artifact_age_hours must be in [1, 336]")
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    max_age_seconds = max_artifact_age_hours * 3600
    paths = paths or {}
    artifacts = {
        "data_flow": _artifact_summary(
            name="data_flow",
            path=paths.get("data_flow"),
            payload=data_flow,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
        "counterfactual": _artifact_summary(
            name="counterfactual",
            path=paths.get("counterfactual"),
            payload=counterfactual,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
        "plan": _artifact_summary(
            name="plan",
            path=paths.get("plan"),
            payload=plan,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
        "activation_preflight": _artifact_summary(
            name="activation_preflight",
            path=paths.get("activation_preflight"),
            payload=activation_preflight,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
        "blocked_review": _artifact_summary(
            name="blocked_review",
            path=paths.get("blocked_review"),
            payload=blocked_review,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
        "sealed_horizon_learning_evidence": _artifact_summary(
            name="sealed_horizon_learning_evidence",
            path=paths.get("sealed_horizon_learning_evidence"),
            payload=sealed_horizon_learning_evidence,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
        "stack_health": _artifact_summary(
            name="stack_health",
            path=paths.get("stack_health"),
            payload=stack_health,
            now_utc=now,
            max_age_seconds=max_age_seconds,
        ),
    }
    decision = _decision(
        data_flow=data_flow,
        counterfactual=counterfactual,
        plan=plan,
        activation_preflight=activation_preflight,
        blocked_review=blocked_review,
        sealed_horizon_learning_evidence=sealed_horizon_learning_evidence,
        stack_health=stack_health,
        artifact_summaries=artifacts,
    )
    flow = _data_flow_observations(data_flow)
    ranking = _profit_ranking(counterfactual)
    stability = _horizon_stability(counterfactual)
    review_status = _blocked_review_status(blocked_review)
    sealed_summary = _sealed_learning_summary(sealed_horizon_learning_evidence)

    return {
        "schema_version": PROFIT_LEARNING_DECISION_PACKET_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": decision["status"],
        "reason": decision["reason"],
        "next_actions": decision["next_actions"],
        "answers": {
            "demo_data_flow_seen": artifacts["data_flow"]["present"],
            "cost_gate_rejects_recorded": flow["cost_gate_rejects_recorded"],
            "silent_drop_risk": (
                artifacts["data_flow"]["present"] is not True
                or (
                    flow["cost_gate_rejects_recorded"] is not True
                    and flow["broad_window_has_candidate_or_reject_data"] is not True
                )
            ),
            "counterfactual_scorecard_available": artifacts["counterfactual"]["present"],
            "counterfactual_learning_candidates_present": (
                _counterfactual_has_learning_candidates(counterfactual)
            ),
            "bounded_plan_ready": _plan_ready(plan),
            "activation_or_stack_health_available": (
                artifacts["activation_preflight"]["present"]
                or artifacts["stack_health"]["present"]
            ),
            "blocked_outcome_review_available": artifacts["blocked_review"]["present"],
            "blocked_outcome_review_candidates_present": (
                review_status == "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT"
                or _blocked_review_candidates(blocked_review) > 0
            ),
            "sealed_horizon_learning_evidence_available": artifacts[
                "sealed_horizon_learning_evidence"
            ]["present"],
            "sealed_horizon_learning_evidence_candidates_present": sealed_summary[
                "review_ready"
            ],
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "data_flow": flow,
        "counterfactual": {
            "scorecard_status": _counterfactual_scorecard(counterfactual).get("status"),
            "profit_opportunity_ranking_status": ranking.get("status"),
            "horizon_stability_status": stability.get("status"),
            "candidate_count": _int(ranking.get("candidate_count")),
            "top_side_cells": _top_side_cells(counterfactual),
        },
        "plan": {
            "status": (plan or {}).get("status") if isinstance(plan, dict) else None,
            "gate_status": (plan or {}).get("gate_status") if isinstance(plan, dict) else None,
            "selected_probe_candidate_count": (
                (plan or {}).get("selected_probe_candidate_count")
                if isinstance(plan, dict)
                else None
            ),
            "ready": _plan_ready(plan),
        },
        "activation": {
            "status": _activation_status(activation_preflight, stack_health),
            "next_actions": _activation_next_actions(activation_preflight, stack_health),
        },
        "blocked_review": {
            "status": review_status,
            "candidate_count": _blocked_review_candidates(blocked_review),
        },
        "sealed_horizon_learning_evidence": sealed_summary,
        "artifacts": artifacts,
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# Cost Gate Profit Learning Decision Packet",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: {packet.get('reason')}",
        "- Boundary: artifact-only; no Cost Gate lowering, order authority, PG write, or runtime mutation.",
        "",
        "## Next Actions",
        "",
    ]
    for action in packet.get("next_actions") or []:
        lines.append(f"- `{action}`")
    answers = packet.get("answers") or {}
    lines.extend(
        [
            "",
            "## Answers",
            "",
            "| answer | value |",
            "|---|---|",
        ]
    )
    for key in [
        "demo_data_flow_seen",
        "cost_gate_rejects_recorded",
        "silent_drop_risk",
        "counterfactual_scorecard_available",
        "counterfactual_learning_candidates_present",
        "bounded_plan_ready",
        "activation_or_stack_health_available",
        "blocked_outcome_review_available",
        "blocked_outcome_review_candidates_present",
        "sealed_horizon_learning_evidence_available",
        "sealed_horizon_learning_evidence_candidates_present",
        "global_cost_gate_lowering_recommended",
        "order_authority_granted",
    ]:
        lines.append(f"| {key} | `{answers.get(key)}` |")

    sealed = packet.get("sealed_horizon_learning_evidence") or {}
    if sealed.get("review_ready"):
        lines.extend(
            [
                "",
                "## Sealed Horizon Learning Evidence",
                "",
                "| side_cell | horizon_min | outcomes | avg_net_bps | net_positive_pct |",
                "|---|---:|---:|---:|---:|",
                "| "
                f"{sealed.get('side_cell_key')} | "
                f"{sealed.get('outcome_horizon_minutes')} | "
                f"{sealed.get('blocked_signal_outcome_count')} | "
                f"{sealed.get('avg_net_bps')} | "
                f"{sealed.get('net_positive_pct')} |",
            ]
        )

    top = ((packet.get("counterfactual") or {}).get("top_side_cells") or [])[:5]
    if top:
        lines.extend(
            [
                "",
                "## Top Counterfactual Side Cells",
                "",
                "| side_cell | action | score | sample_n | rows | avg_net_bps | net_positive_pct |",
                "|---|---|---:|---:|---:|---:|---:|",
            ]
        )
        for row in top:
            sample_n = (
                row.get("sample_count_for_gate")
                or row.get("distinct_ts")
                or row.get("n")
            )
            lines.append(
                "| "
                f"{row.get('side_cell_key')} | {row.get('learning_lane_action')} | "
                f"{row.get('priority_score')} | {sample_n} | {row.get('n')} | "
                f"{row.get('avg_net_bps')} | {row.get('net_positive_pct')} |"
            )
    return "\n".join(lines) + "\n"


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-flow-json", type=Path)
    parser.add_argument("--counterfactual-json", type=Path)
    parser.add_argument("--plan-json", type=Path)
    parser.add_argument("--activation-preflight-json", type=Path)
    parser.add_argument("--blocked-outcome-review-json", type=Path)
    parser.add_argument("--sealed-horizon-learning-evidence-json", type=Path)
    parser.add_argument("--stack-health-json", type=Path)
    parser.add_argument("--max-artifact-age-hours", type=int, default=24)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    payloads = {
        "data_flow": _read_json(args.data_flow_json),
        "counterfactual": _read_json(args.counterfactual_json),
        "plan": _read_json(args.plan_json),
        "activation_preflight": _read_json(args.activation_preflight_json),
        "blocked_review": _read_json(args.blocked_outcome_review_json),
        "sealed_horizon_learning_evidence": _read_json(
            args.sealed_horizon_learning_evidence_json
        ),
        "stack_health": _read_json(args.stack_health_json),
    }
    paths = {
        "data_flow": args.data_flow_json,
        "counterfactual": args.counterfactual_json,
        "plan": args.plan_json,
        "activation_preflight": args.activation_preflight_json,
        "blocked_review": args.blocked_outcome_review_json,
        "sealed_horizon_learning_evidence": args.sealed_horizon_learning_evidence_json,
        "stack_health": args.stack_health_json,
    }
    packet = build_profit_learning_decision_packet(
        **payloads,
        paths=paths,
        max_artifact_age_hours=args.max_artifact_age_hours,
    )
    markdown = render_markdown(packet)
    if args.output:
        _write_text(args.output, markdown)
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True, default=str))
    elif not args.output:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
