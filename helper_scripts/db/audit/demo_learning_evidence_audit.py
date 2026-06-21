#!/usr/bin/env python3
"""Composite read-only audit for demo learning evidence.

This audit answers the operator question that sits above "why did demo not
order?": is demo accumulating evidence that can improve future decisions?

It combines two existing read-only surfaces:

    demo_order_stall_audit
      PG pipeline counts, Cost Gate rejects, context payload scope

    cost_gate_learning_lane.status
      local/runtime artifact preflight for probe_ledger, outcome refresh,
      blocked-outcome review, writer config, and source readiness

No PG writes, no Bybit calls, no orders, no config/risk/auth/runtime mutation,
and no main Cost Gate lowering.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
RESEARCH_ROOT = ROOT / "helper_scripts" / "research"
for _path in (str(ROOT), str(RESEARCH_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from helper_scripts.db.audit import demo_order_stall_audit as order_stall  # noqa: E402
from helper_scripts.lib.pg_connect import connect_report_pg  # noqa: E402
from cost_gate_learning_lane.status import (  # noqa: E402
    build_cost_gate_learning_lane_activation_preflight,
)


SCHEMA_VERSION = "demo_learning_evidence_audit_v1"


@dataclass(frozen=True)
class EvidenceAuditConfig:
    engine_modes: tuple[str, ...]
    lookback_hours: int
    top_limit: int
    data_dir: Path
    repo_root: Path | None = None
    expected_head: str | None = None
    runtime_env_file: Path | None = None
    engine_pid: int | None = None
    runtime_proc_environ: Path | None = None
    auto_detect_engine_pid: bool = False
    require_writer_enabled: bool = False
    require_process_writer_enabled: bool = False


def validate_config(cfg: EvidenceAuditConfig) -> None:
    order_stall.validate_config(
        order_stall.AuditConfig(
            engine_modes=cfg.engine_modes,
            lookback_hours=cfg.lookback_hours,
            top_limit=cfg.top_limit,
        ),
    )


def _as_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _get_path(payload: dict[str, Any], *parts: str) -> Any:
    current: Any = payload
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def classify_order_flow_evidence(
    *,
    candidate_or_reject_data: bool,
    cost_gate_rejects_recorded: bool,
    orders: int,
    fills: int,
) -> dict[str, Any]:
    if fills > 0:
        status = "DEMO_FILL_EVIDENCE_PRESENT"
        reason = "recent demo fills exist and can support execution realism review"
        next_action = "review_demo_fill_outcomes_for_execution_realism"
    elif orders > 0:
        status = "DEMO_ORDER_FLOW_PRESENT_NO_FILL_EVIDENCE"
        reason = "recent demo orders exist but no fills landed in the lookback window"
        next_action = "diagnose_demo_order_to_fill_gap_before_alpha_promotion"
    elif cost_gate_rejects_recorded:
        status = "COST_GATE_REJECT_WALL_NO_ORDER_FLOW_EVIDENCE"
        reason = "fresh Cost Gate rejects exist but no demo orders or fills landed"
        next_action = (
            "activate_cost_gate_learning_lane_then_operator_review_bounded_demo_probe"
        )
    elif candidate_or_reject_data:
        status = "CANDIDATE_OR_REJECT_DATA_WITHOUT_ORDER_FLOW_EVIDENCE"
        reason = "candidate/reject data exists but no demo orders or fills landed"
        next_action = "diagnose_candidate_to_order_gate_before_claiming_execution_data"
    else:
        status = "NO_ORDER_FLOW_EVIDENCE"
        reason = "no recent demo orders or fills landed"
        next_action = "restore_candidate_or_reject_flow_before_order_evidence_review"
    return {
        "status": status,
        "reason": reason,
        "next_action": next_action,
        "answers": {
            "recent_order_flow_present": orders > 0 or fills > 0,
            "recent_fill_evidence_present": fills > 0,
            "order_flow_evidence_starved": (
                cost_gate_rejects_recorded and orders == 0 and fills == 0
            ),
            "candidate_or_reject_without_order_flow": (
                candidate_or_reject_data and orders == 0 and fills == 0
            ),
        },
    }


def _cost_gate_adjustment_preflight_gate(
    learning_preflight: dict[str, Any] | None,
) -> dict[str, Any]:
    preflight = learning_preflight or {}
    answers = (
        preflight.get("answers")
        if isinstance(preflight.get("answers"), dict)
        else {}
    )
    source = (
        preflight.get("source")
        if isinstance(preflight.get("source"), dict)
        else {}
    )
    writer_config = (
        preflight.get("writer_config")
        if isinstance(preflight.get("writer_config"), dict)
        else {}
    )
    writer_process = (
        preflight.get("writer_process")
        if isinstance(preflight.get("writer_process"), dict)
        else {}
    )
    blockers = list(preflight.get("activation_blockers") or [])
    source_ready = answers.get("runtime_source_ready_for_activation")
    if source_ready is None:
        source_ready = source.get("source_activation_ready")
    source_status = (
        source.get("source_activation_status")
        or preflight.get("status")
        or "UNKNOWN"
    )
    writer_config_required = answers.get("runtime_writer_config_required") is True
    writer_config_enabled = answers.get("runtime_writer_enabled")
    if writer_config_enabled is None:
        writer_config_enabled = writer_config.get("writer_enabled")
    writer_process_required = answers.get("runtime_writer_process_required") is True
    writer_process_enabled = answers.get("runtime_writer_process_enabled")
    if writer_process_enabled is None:
        writer_process_enabled = writer_process.get("writer_process_enabled")
    preflight_status = str(preflight.get("status") or "UNKNOWN")
    first_preflight_action = str(
        (preflight.get("next_actions") or [None])[0]
        or "rerun_cost_gate_learning_lane_activation_preflight"
    )
    hard_preflight_blocked = preflight_status in {
        "PLAN_NOT_READY",
        "LEARNING_LOOP_ERROR",
        "LEARNING_LOOP_STALE",
        "CAPTURE_ERRORS_NEED_OPERATOR_FIX",
    }
    runtime_summary = {
        "runtime_activation_blockers": blockers,
        "runtime_source_activation_ready": source_ready,
        "runtime_source_activation_status": source_status,
        "runtime_writer_config_required": writer_config_required,
        "runtime_writer_config_enabled": writer_config_enabled,
        "runtime_writer_config_status": answers.get("runtime_writer_config_status")
        or writer_config.get("writer_config_status"),
        "runtime_writer_process_required": writer_process_required,
        "runtime_writer_process_enabled": writer_process_enabled,
        "runtime_writer_process_status": answers.get("runtime_writer_process_status")
        or writer_process.get("writer_process_status"),
    }

    def _block(
        *,
        status: str,
        reason: str,
        next_action: str,
        learning_gate_adjustment: str,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "reason": reason,
            "next_action": next_action,
            "learning_gate_adjustment": learning_gate_adjustment,
            "bounded_demo_learning_lane_recommended": False,
            "runtime_preflight_blocking_cost_gate_adjustment": True,
            "runtime_activation_ready": False,
            **runtime_summary,
        }

    if source_ready is False:
        return _block(
            status="RUNTIME_SOURCE_SYNC_REQUIRED_BEFORE_COST_GATE_CHANGE",
            reason="runtime source checkout is not activation-ready",
            next_action=(
                "sync_runtime_source_to_expected_head_before_cost_gate_learning_activation"
            ),
            learning_gate_adjustment="NONE_SYNC_RUNTIME_SOURCE_FIRST",
        )
    if writer_config_required and writer_config_enabled is not True:
        return _block(
            status="RUNTIME_WRITER_ENABLEMENT_REQUIRED_BEFORE_BOUNDED_LEARNING_LANE",
            reason="runtime writer config is required but disabled or unset",
            next_action=(
                "enable_OPENCLAW_DEMO_LEARNING_LANE_WRITER_after_operator_review"
            ),
            learning_gate_adjustment="NONE_ENABLE_RUNTIME_WRITER_FIRST",
        )
    if writer_process_required and writer_process_enabled is not True:
        return _block(
            status=(
                "RUNNING_ENGINE_WRITER_ENABLEMENT_REQUIRED_BEFORE_BOUNDED_LEARNING_LANE"
            ),
            reason="running engine writer is required but not enabled",
            next_action=(
                "restart_or_reconfigure_engine_with_demo_learning_writer_after_operator_review"
            ),
            learning_gate_adjustment="NONE_ENABLE_RUNNING_ENGINE_WRITER_FIRST",
        )
    if hard_preflight_blocked:
        return _block(
            status="RUNTIME_PREFLIGHT_REQUIRED_BEFORE_BOUNDED_LEARNING_LANE",
            reason=f"cost-gate learning preflight is {preflight_status}",
            next_action=first_preflight_action,
            learning_gate_adjustment="NONE_CLEAR_RUNTIME_PREFLIGHT_FIRST",
        )
    return {
        **runtime_summary,
        "runtime_preflight_blocking_cost_gate_adjustment": False,
        "runtime_activation_ready": answers.get("activation_ready"),
    }


def classify_cost_gate_adjustment_recommendation(
    *,
    cost_gate_rejects_recorded: bool,
    order_flow_evidence: dict[str, Any],
    learning_data_flow_stale: bool,
    learning_evidence_accumulating: bool,
    blocked_outcome_review_candidate: bool,
    learning_preflight: dict[str, Any] | None = None,
) -> dict[str, Any]:
    order_flow_status = str(order_flow_evidence.get("status") or "")
    order_flow_answers = order_flow_evidence.get("answers") or {}
    runtime_gate = _cost_gate_adjustment_preflight_gate(learning_preflight)
    if runtime_gate.get("runtime_preflight_blocking_cost_gate_adjustment") is True:
        status = str(runtime_gate["status"])
        reason = str(runtime_gate["reason"])
        next_action = str(runtime_gate["next_action"])
        learning_gate_adjustment = str(runtime_gate["learning_gate_adjustment"])
        bounded_recommended = False
    elif blocked_outcome_review_candidate:
        status = "BOUNDED_DEMO_PROBE_AUTHORITY_REVIEW_READY"
        reason = "blocked-signal outcomes cleared review thresholds"
        next_action = "operator_review_blocked_outcome_scorecard_before_demo_probe_authority"
        learning_gate_adjustment = "OPERATOR_REVIEW_BOUNDED_SIDE_CELL_DEMO_PROBE"
        bounded_recommended = True
    elif learning_data_flow_stale:
        status = "RESTORE_DATA_FLOW_BEFORE_ANY_COST_GATE_CHANGE"
        reason = "candidate/reject/order-flow data is stale"
        next_action = "restore_demo_data_flow_before_cost_gate_learning_activation"
        learning_gate_adjustment = "NONE_RESTORE_DATA_FLOW_FIRST"
        bounded_recommended = False
    elif (
        cost_gate_rejects_recorded
        and order_flow_answers.get("order_flow_evidence_starved") is True
        and not learning_evidence_accumulating
    ):
        status = "BOUNDED_LEARNING_LANE_ACTIVATION_RECOMMENDED"
        reason = "fresh Cost Gate rejects exist but no demo order/fill evidence exists"
        next_action = (
            "activate_cost_gate_learning_lane_then_operator_review_bounded_demo_probe"
        )
        learning_gate_adjustment = "ENABLE_LEDGER_AND_OUTCOME_REVIEW_FIRST"
        bounded_recommended = True
    elif (
        cost_gate_rejects_recorded
        and order_flow_status == "DEMO_ORDER_FLOW_PRESENT_NO_FILL_EVIDENCE"
    ):
        status = "ORDER_TO_FILL_DIAGNOSIS_BEFORE_COST_GATE_CHANGE"
        reason = "demo orders exist but no fills landed"
        next_action = "diagnose_demo_order_to_fill_gap_before_cost_gate_changes"
        learning_gate_adjustment = "NONE_DIAGNOSE_ORDER_TO_FILL_FIRST"
        bounded_recommended = False
    elif cost_gate_rejects_recorded and learning_evidence_accumulating:
        status = "CONTINUE_BOUNDED_LEARNING_NO_COST_GATE_CHANGE"
        reason = "learning evidence is accumulating; continue outcome review"
        next_action = "continue_recording_and_refreshing_blocked_signal_outcomes"
        learning_gate_adjustment = "NONE_CONTINUE_EVIDENCE_ACCUMULATION"
        bounded_recommended = True
    else:
        status = "NO_COST_GATE_ADJUSTMENT_RECOMMENDED"
        reason = "no machine-checked evidence supports changing Cost Gate behavior"
        next_action = "continue_demo_learning_evidence_collection"
        learning_gate_adjustment = "NONE"
        bounded_recommended = False
    recommendation = {
        "status": status,
        "reason": reason,
        "next_action": next_action,
        "main_cost_gate_adjustment": "NONE",
        "global_cost_gate_lowering_recommended": False,
        "bounded_demo_learning_lane_recommended": bounded_recommended,
        "learning_gate_adjustment": learning_gate_adjustment,
        "order_authority": "NOT_GRANTED",
    }
    recommendation.update(runtime_gate)
    return recommendation


def classify_demo_learning_evidence(
    *,
    order_scorecard: dict[str, Any],
    learning_preflight: dict[str, Any],
) -> dict[str, Any]:
    """Classify whether demo is learning, not just ordering.

    This deliberately keeps main Cost Gate lowering false. The intended path is
    a bounded learning lane with ledger/outcome/review evidence.
    """
    counts = order_scorecard.get("counts") or {}
    order_cls = order_scorecard.get("classification") or {}
    order_answers = order_cls.get("answers") or {}
    order_freshness = order_cls.get("data_flow_freshness") or {}
    order_freshness_answers = order_freshness.get("answers") or {}
    risk_category = order_cls.get("dominant_risk_category") or {}
    context_scope = order_scorecard.get("context_payload_scope") or {}
    learning_answers = learning_preflight.get("answers") or {}
    ledger = learning_preflight.get("ledger") or {}

    contexts = _as_int(counts.get("decision_context_snapshots"))
    evaluations = _as_int(counts.get("candidate_evaluations"))
    risk_verdicts = _as_int(counts.get("risk_verdicts"))
    rejected_features = _as_int(counts.get("rejected_decision_features"))
    orders = _as_int(counts.get("orders"))
    fills = _as_int(counts.get("fills"))
    observation_only = order_answers.get("context_payload_observation_only") is True
    order_silent_drop = order_answers.get("silent_drop_risk") is True
    learning_data_flow_stale = (
        order_answers.get("learning_data_flow_stale") is True
        or order_freshness_answers.get("learning_data_flow_stale") is True
    )
    candidate_or_reject_data = (
        order_answers.get("candidate_or_reject_data_accumulating") is True
    )
    cost_gate_dominant = risk_category.get("category") == "cost_gate"
    cost_gate_pg_rejects_recorded = bool(
        cost_gate_dominant and (risk_verdicts > 0 or rejected_features > 0)
    )
    order_flow_evidence = classify_order_flow_evidence(
        candidate_or_reject_data=candidate_or_reject_data,
        cost_gate_rejects_recorded=cost_gate_pg_rejects_recorded,
        orders=orders,
        fills=fills,
    )
    order_flow_answers = order_flow_evidence.get("answers") or {}

    ledger_rows = _as_int(ledger.get("ledger_total_rows"))
    admission_rows = _as_int(ledger.get("admission_decision_count"))
    blocked_outcomes = _as_int(ledger.get("blocked_signal_outcome_count"))
    probe_outcomes = _as_int(ledger.get("probe_outcome_count"))
    learning_status = str(learning_preflight.get("status") or "UNKNOWN")
    review_status = str(
        ledger.get("blocked_signal_outcome_review_status")
        or _get_path(learning_preflight, "learning_loop", "learning_loop_last_review_status")
        or ""
    )
    learning_evidence_accumulating = (
        learning_answers.get("currently_accumulating_evidence") is True
        or ledger_rows > 0
    )
    blocked_outcome_review_candidate = (
        review_status == "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT"
        or learning_status == "REVIEW_CANDIDATE_OPERATOR_REVIEW"
    )
    cost_gate_recommendation = classify_cost_gate_adjustment_recommendation(
        cost_gate_rejects_recorded=cost_gate_pg_rejects_recorded,
        order_flow_evidence=order_flow_evidence,
        learning_data_flow_stale=learning_data_flow_stale,
        learning_evidence_accumulating=learning_evidence_accumulating,
        blocked_outcome_review_candidate=blocked_outcome_review_candidate,
        learning_preflight=learning_preflight,
    )

    if contexts == 0 and not candidate_or_reject_data and ledger_rows == 0:
        status = "NO_DEMO_LEARNING_EVIDENCE"
        reason = "no recent demo context/candidate/reject rows and no learning ledger rows"
        next_action = "restore_demo_signal_and_reject_data_before_learning_review"
    elif order_silent_drop:
        status = "ACTIONABLE_CONTEXT_SILENT_DROP_RISK"
        reason = "recent non-observation contexts have no candidate/risk/intent path"
        next_action = "diagnose_context_to_candidate_pipeline_before_cost_gate_changes"
    elif (
        cost_gate_recommendation.get("runtime_preflight_blocking_cost_gate_adjustment")
        is True
    ):
        status = "RUNTIME_PREFLIGHT_BLOCKS_COST_GATE_LEARNING_ADJUSTMENT"
        reason = str(cost_gate_recommendation.get("reason"))
        next_action = str(cost_gate_recommendation.get("next_action"))
    elif blocked_outcome_review_candidate:
        status = "LEARNING_REVIEW_CANDIDATES_PRESENT"
        reason = "blocked-signal outcomes clear review thresholds"
        next_action = "operator_review_blocked_outcome_scorecard_before_demo_probe_authority"
    elif blocked_outcomes > 0:
        status = "BLOCKED_OUTCOMES_ACCUMULATING"
        reason = "blocked-signal outcomes exist but have not cleared review authority"
        next_action = "continue_recording_and_refreshing_blocked_signal_outcomes"
    elif admission_rows > 0:
        status = "ADMISSION_ROWS_NEED_OUTCOME_REFRESH"
        reason = "cost-gate rejects are in the ledger but blocked outcomes are missing"
        next_action = "run_cost_gate_outcome_refresh_for_blocked_signal_outcomes"
    elif learning_data_flow_stale and not learning_evidence_accumulating:
        status = "DEMO_LEARNING_DATA_FLOW_STALE"
        reason = (
            "demo learning data rows exist in the lookback window but the latest "
            "candidate/reject/order-flow timestamp is stale"
        )
        next_action = "restore_demo_data_flow_before_cost_gate_learning_activation"
    elif cost_gate_pg_rejects_recorded and not learning_evidence_accumulating:
        status = "PG_REJECTS_RECORDED_LEARNING_LANE_NOT_ACCUMULATING"
        reason = "PG records Cost Gate rejects but runtime learning ledger is absent or empty"
        next_action = "enable_bounded_cost_gate_learning_lane_after_operator_review"
    elif observation_only and not candidate_or_reject_data:
        status = "OBSERVATION_TELEMETRY_ACTIVE_NO_ACTIONABLE_LEDGER"
        reason = "demo signal observation telemetry is active but not producing actionable reject evidence"
        next_action = "wait_for_candidate_rejects_or_verify_strategy_candidate_producer"
    elif candidate_or_reject_data:
        status = "REJECT_OR_CANDIDATE_DATA_ACCUMULATING"
        reason = "candidate/reject rows are accumulating; learning ledger state decides next step"
        next_action = str(
            learning_preflight.get("next_actions", [None])[0]
            or "run_cost_gate_learning_lane_preflight"
        )
    elif orders > 0 or fills > 0:
        status = "ORDER_FLOW_PRESENT_LEARNING_REVIEW_STILL_REQUIRED"
        reason = "orders/fills exist, but profitability learning still requires ledger/review evidence"
        next_action = "review_order_fill_outcomes_and_cost_gate_learning_lane"
    else:
        status = "PARTIAL_DEMO_LEARNING_EVIDENCE"
        reason = "some demo evidence exists but it does not yet form a closed learning loop"
        next_action = "run_demo_order_stall_and_cost_gate_learning_preflight_again"

    return {
        "status": status,
        "reason": reason,
        "next_action": next_action,
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "cost_gate_adjustment_recommendation": cost_gate_recommendation,
        "order_authority": "NOT_GRANTED",
        "answers": {
            "demo_context_data_accumulating": contexts > 0,
            "demo_observation_only_contexts_active": observation_only,
            "candidate_or_reject_data_accumulating": candidate_or_reject_data,
            "pipeline_flow_fresh": order_answers.get("pipeline_flow_fresh"),
            "pipeline_flow_stale": order_answers.get("pipeline_flow_stale"),
            "learning_data_flow_fresh": order_answers.get("learning_data_flow_fresh"),
            "learning_data_flow_stale": learning_data_flow_stale,
            "cost_gate_rejects_recorded_in_pg": cost_gate_pg_rejects_recorded,
            "recent_order_flow_present": order_flow_answers.get(
                "recent_order_flow_present"
            ),
            "recent_fill_evidence_present": order_flow_answers.get(
                "recent_fill_evidence_present"
            ),
            "order_flow_evidence_starved": order_flow_answers.get(
                "order_flow_evidence_starved"
            ),
            "candidate_or_reject_without_order_flow": order_flow_answers.get(
                "candidate_or_reject_without_order_flow"
            ),
            "learning_lane_ledger_rows_present": ledger_rows > 0,
            "learning_lane_currently_accumulating_evidence": learning_evidence_accumulating,
            "blocked_signal_outcomes_recorded": blocked_outcomes > 0,
            "probe_outcomes_recorded": probe_outcomes > 0,
            "blocked_outcome_review_candidate_present": blocked_outcome_review_candidate,
            "order_flow_silent_drop_risk": order_silent_drop,
            "learning_lane_silent_drop_risk": (
                learning_answers.get("silent_drop_risk") is True
            ),
            "historical_counterfactual_candidates_present": (
                learning_answers.get("historical_counterfactual_candidates_present")
                is True
            ),
            "historical_counterfactual_is_runtime_evidence": False,
            "bounded_demo_learning_lane_recommended": (
                cost_gate_recommendation.get("bounded_demo_learning_lane_recommended")
                is True
            ),
            "runtime_preflight_blocking_cost_gate_adjustment": (
                cost_gate_recommendation.get(
                    "runtime_preflight_blocking_cost_gate_adjustment"
                )
                is True
            ),
        },
        "key_counts": {
            "decision_context_snapshots": contexts,
            "candidate_evaluations": evaluations,
            "risk_verdicts": risk_verdicts,
            "rejected_decision_features": rejected_features,
            "orders": orders,
            "fills": fills,
            "order_flow_evidence_status": order_flow_evidence.get("status"),
            "order_flow_evidence_reason": order_flow_evidence.get("reason"),
            "order_flow_evidence_next_action": order_flow_evidence.get("next_action"),
            "cost_gate_adjustment_recommendation_status": (
                cost_gate_recommendation.get("status")
            ),
            "cost_gate_adjustment_recommendation_reason": (
                cost_gate_recommendation.get("reason")
            ),
            "cost_gate_adjustment_recommendation_next_action": (
                cost_gate_recommendation.get("next_action")
            ),
            "cost_gate_learning_gate_adjustment": (
                cost_gate_recommendation.get("learning_gate_adjustment")
            ),
            "cost_gate_adjustment_runtime_preflight_blocking": (
                cost_gate_recommendation.get(
                    "runtime_preflight_blocking_cost_gate_adjustment"
                )
            ),
            "cost_gate_adjustment_runtime_activation_ready": (
                cost_gate_recommendation.get("runtime_activation_ready")
            ),
            "cost_gate_adjustment_runtime_activation_blockers": (
                cost_gate_recommendation.get("runtime_activation_blockers")
            ),
            "cost_gate_adjustment_runtime_source_activation_ready": (
                cost_gate_recommendation.get("runtime_source_activation_ready")
            ),
            "cost_gate_adjustment_runtime_source_activation_status": (
                cost_gate_recommendation.get("runtime_source_activation_status")
            ),
            "cost_gate_adjustment_runtime_writer_config_required": (
                cost_gate_recommendation.get("runtime_writer_config_required")
            ),
            "cost_gate_adjustment_runtime_writer_config_enabled": (
                cost_gate_recommendation.get("runtime_writer_config_enabled")
            ),
            "cost_gate_adjustment_runtime_writer_config_status": (
                cost_gate_recommendation.get("runtime_writer_config_status")
            ),
            "cost_gate_adjustment_runtime_writer_process_required": (
                cost_gate_recommendation.get("runtime_writer_process_required")
            ),
            "cost_gate_adjustment_runtime_writer_process_enabled": (
                cost_gate_recommendation.get("runtime_writer_process_enabled")
            ),
            "cost_gate_adjustment_runtime_writer_process_status": (
                cost_gate_recommendation.get("runtime_writer_process_status")
            ),
            "data_flow_freshness_status": order_freshness.get("status"),
            "latest_learning_stage": order_freshness.get("latest_learning_stage"),
            "latest_learning_ts_utc": order_freshness.get("latest_learning_ts_utc"),
            "latest_learning_age_seconds": order_freshness.get(
                "latest_learning_age_seconds"
            ),
            "context_payload_rows": _as_int(context_scope.get("context_rows")),
            "signal_observation_only_contexts": _as_int(
                context_scope.get("signal_observation_only_contexts")
            ),
            "accepted_intent_bound_contexts": _as_int(
                context_scope.get("accepted_intent_bound_contexts")
            ),
            "learning_ledger_rows": ledger_rows,
            "learning_admission_rows": admission_rows,
            "blocked_signal_outcomes": blocked_outcomes,
            "probe_outcomes": probe_outcomes,
        },
    }


def build_payload(
    cfg: EvidenceAuditConfig,
    counts: dict[str, Any],
    risk_reasons: list[dict[str, Any]],
    eval_outcomes: list[dict[str, Any]],
    lineage: dict[str, Any],
    context_payload_scope: dict[str, Any],
    pre_gate_drilldown: list[dict[str, Any]],
    *,
    generated: str | None = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    validate_config(cfg)
    generated = generated or datetime.now(timezone.utc).isoformat(timespec="seconds")
    order_cfg = order_stall.AuditConfig(
        engine_modes=cfg.engine_modes,
        lookback_hours=cfg.lookback_hours,
        top_limit=cfg.top_limit,
    )
    order_scorecard = order_stall.build_scorecard(
        order_cfg,
        counts,
        risk_reasons,
        eval_outcomes,
        lineage,
        pre_gate_drilldown,
        context_payload_scope,
        now_utc=now_utc,
    )
    learning_preflight = build_cost_gate_learning_lane_activation_preflight(
        cfg.data_dir,
        repo_root=cfg.repo_root,
        expected_head=cfg.expected_head,
        runtime_env_file=cfg.runtime_env_file,
        engine_pid=cfg.engine_pid,
        runtime_proc_environ=cfg.runtime_proc_environ,
        auto_detect_engine_pid=cfg.auto_detect_engine_pid,
        require_writer_enabled=cfg.require_writer_enabled,
        require_process_writer_enabled=cfg.require_process_writer_enabled,
        now_utc=now_utc,
    )
    classification = classify_demo_learning_evidence(
        order_scorecard=order_scorecard,
        learning_preflight=learning_preflight,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated,
        "engine_modes": list(cfg.engine_modes),
        "lookback_hours": cfg.lookback_hours,
        "top_limit": cfg.top_limit,
        "classification": classification,
        "order_stall_scorecard": order_scorecard,
        "cost_gate_learning_preflight": learning_preflight,
        "boundary": (
            "read-only PG SELECT plus read-only artifact/source/process-env inspection; "
            "no PG write/schema migration, Bybit private/signed/trading call, order, "
            "auth/risk/runtime/config mutation, main Cost Gate lowering, or demo order authority"
        ),
    }


def fetch_and_build_payload(
    conn: Any,
    cfg: EvidenceAuditConfig,
    *,
    generated: str | None = None,
) -> dict[str, Any]:
    validate_config(cfg)
    order_cfg = order_stall.AuditConfig(
        engine_modes=cfg.engine_modes,
        lookback_hours=cfg.lookback_hours,
        top_limit=cfg.top_limit,
    )
    (
        counts,
        risk_reasons,
        eval_outcomes,
        lineage,
        context_payload_scope,
        pre_gate_drilldown,
    ) = order_stall.fetch_audit(conn, order_cfg)
    return build_payload(
        cfg,
        counts,
        risk_reasons,
        eval_outcomes,
        lineage,
        context_payload_scope,
        pre_gate_drilldown,
        generated=generated,
    )


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, Decimal):
        return f"{float(value):.4f}"
    return str(value)


def render_markdown(payload: dict[str, Any]) -> str:
    cls = payload["classification"]
    answers = cls["answers"]
    counts = cls["key_counts"]
    recommendation = cls.get("cost_gate_adjustment_recommendation") or {}
    order_cls = payload["order_stall_scorecard"]["classification"]
    preflight = payload["cost_gate_learning_preflight"]
    preflight_answers = preflight.get("answers") or {}
    lines = [
        "# Demo Learning Evidence Audit",
        "",
        f"- Generated: `{payload['generated_at_utc']}`",
        f"- Engine modes: `{','.join(payload['engine_modes'])}`",
        f"- Lookback: `{payload['lookback_hours']}` hours",
        "- Boundary: read-only PG SELECT plus read-only artifact/source/process-env inspection; no order/config/risk/runtime mutation.",
        "",
        "## Classification",
        "",
        f"- Status: `{cls['status']}`",
        f"- Reason: {cls['reason']}",
        f"- Next action: `{cls['next_action']}`",
        f"- Global Cost Gate lowering recommended: `{cls['global_cost_gate_lowering_recommended']}`",
        f"- Main Cost Gate adjustment: `{cls['main_cost_gate_adjustment']}`",
        f"- Cost Gate adjustment recommendation: `{recommendation.get('status')}`",
        f"- Learning Gate adjustment: `{recommendation.get('learning_gate_adjustment')}`",
        f"- Order authority: `{cls['order_authority']}`",
        "",
        "## Answers",
        "",
        "| question | answer |",
        "|---|---:|",
    ]
    for key in [
        "demo_context_data_accumulating",
        "demo_observation_only_contexts_active",
        "candidate_or_reject_data_accumulating",
        "pipeline_flow_fresh",
        "pipeline_flow_stale",
        "learning_data_flow_fresh",
        "learning_data_flow_stale",
        "cost_gate_rejects_recorded_in_pg",
        "recent_order_flow_present",
        "recent_fill_evidence_present",
        "order_flow_evidence_starved",
        "candidate_or_reject_without_order_flow",
        "learning_lane_ledger_rows_present",
        "learning_lane_currently_accumulating_evidence",
        "blocked_signal_outcomes_recorded",
        "blocked_outcome_review_candidate_present",
        "order_flow_silent_drop_risk",
        "learning_lane_silent_drop_risk",
        "bounded_demo_learning_lane_recommended",
        "runtime_preflight_blocking_cost_gate_adjustment",
    ]:
        lines.append(f"| {key} | {_fmt(answers.get(key))} |")

    lines.extend(
        [
            "",
            "## Key Counts",
            "",
            "| metric | value |",
            "|---|---:|",
        ]
    )
    for key, value in counts.items():
        lines.append(f"| {key} | {_fmt(value)} |")

    lines.extend(
        [
            "",
            "## Component Status",
            "",
            "| component | status | reason |",
            "|---|---|---|",
            f"| order_stall | `{order_cls.get('status')}` | {order_cls.get('primary_blocker_reason')} |",
            f"| cost_gate_learning_preflight | `{preflight.get('status')}` | {preflight.get('reason')} |",
            f"| source_activation | `{_get_path(preflight, 'source', 'source_activation_status')}` | ready=`{_fmt(_get_path(preflight, 'source', 'source_activation_ready'))}` |",
            f"| writer_config | `{_get_path(preflight, 'writer_config', 'writer_config_status')}` | required=`{_fmt(preflight_answers.get('runtime_writer_config_required'))}` |",
            f"| writer_process | `{_get_path(preflight, 'writer_process', 'writer_process_status')}` | required=`{_fmt(preflight_answers.get('runtime_writer_process_required'))}` |",
            f"| learning_loop | `{_get_path(preflight, 'learning_loop', 'learning_loop_status')}` | {_get_path(preflight, 'learning_loop', 'learning_loop_reason')} |",
            f"| ledger | `{_get_path(preflight, 'ledger', 'ledger_status')}` | rows=`{_fmt(_get_path(preflight, 'ledger', 'ledger_total_rows'))}` |",
        ]
    )
    blockers = preflight.get("activation_blockers") or []
    if blockers:
        lines.extend(["", "## Activation Blockers", ""])
        for blocker in blockers:
            lines.append(f"- `{blocker}`")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-mode", action="append", dest="engine_modes")
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--top-limit", type=int, default=20)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")),
    )
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--expected-head", default=os.environ.get("OPENCLAW_EXPECTED_SOURCE_HEAD"))
    parser.add_argument("--runtime-env-file", type=Path)
    parser.add_argument("--engine-pid", type=int)
    parser.add_argument("--runtime-proc-environ", type=Path)
    parser.add_argument("--auto-detect-engine-pid", action="store_true")
    parser.add_argument("--require-writer-enabled", action="store_true")
    parser.add_argument("--require-process-writer-enabled", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = EvidenceAuditConfig(
        engine_modes=tuple(args.engine_modes or ["demo", "live_demo"]),
        lookback_hours=args.lookback_hours,
        top_limit=args.top_limit,
        data_dir=args.data_dir,
        repo_root=args.repo_root,
        expected_head=args.expected_head,
        runtime_env_file=args.runtime_env_file,
        engine_pid=args.engine_pid,
        runtime_proc_environ=args.runtime_proc_environ,
        auto_detect_engine_pid=(
            args.auto_detect_engine_pid
            or (
                args.require_process_writer_enabled
                and args.engine_pid is None
                and args.runtime_proc_environ is None
            )
        ),
        require_writer_enabled=args.require_writer_enabled,
        require_process_writer_enabled=args.require_process_writer_enabled,
    )
    validate_config(cfg)
    conn = connect_report_pg(
        "demo_learning_evidence_audit",
        statement_timeout_ms_default=180_000,
    )
    try:
        conn.rollback()
        conn.set_session(readonly=True, autocommit=True)
        generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
        payload = fetch_and_build_payload(conn, cfg, generated=generated)
    finally:
        conn.close()

    report = render_markdown(payload)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
