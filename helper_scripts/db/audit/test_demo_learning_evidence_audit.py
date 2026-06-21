from __future__ import annotations

from helper_scripts.db.audit.demo_learning_evidence_audit import (
    classify_cost_gate_adjustment_recommendation,
    classify_demo_learning_evidence,
    classify_order_flow_evidence,
    render_markdown,
)


def _order_scorecard(
    *,
    contexts: int = 100,
    observation_only: bool = True,
    candidate_evaluations: int = 0,
    risk_verdicts: int = 0,
    rejected_features: int = 0,
    cost_gate: bool = False,
    silent_drop: bool = False,
    learning_data_flow_stale: bool = False,
) -> dict:
    return {
        "counts": {
            "decision_context_snapshots": contexts,
            "candidate_evaluations": candidate_evaluations,
            "risk_verdicts": risk_verdicts,
            "rejected_decision_features": rejected_features,
            "orders": 0,
            "fills": 0,
        },
        "context_payload_scope": {
            "context_rows": contexts,
            "signal_observation_only_contexts": contexts if observation_only else 0,
            "accepted_intent_bound_contexts": 0 if observation_only else contexts,
        },
        "classification": {
            "status": (
                "OBSERVATION_ONLY_CONTEXTS_ACTIVE"
                if observation_only
                else "SIGNAL_OBSERVATION_ONLY_PRE_GATE"
            ),
            "primary_blocker_reason": "fixture",
            "dominant_risk_category": {
                "category": "cost_gate" if cost_gate else None,
            },
            "data_flow_freshness": {
                "status": (
                    "LEARNING_DATA_FLOW_STALE"
                    if learning_data_flow_stale
                    else "LEARNING_DATA_FLOW_FRESH"
                ),
                "latest_learning_stage": "risk_verdicts",
                "latest_learning_ts_utc": "2026-06-21T20:47:59+00:00",
                "latest_learning_age_seconds": 8461 if learning_data_flow_stale else 30,
                "answers": {
                    "learning_data_flow_fresh": not learning_data_flow_stale,
                    "learning_data_flow_stale": learning_data_flow_stale,
                },
            },
            "answers": {
                "context_payload_observation_only": observation_only,
                "candidate_or_reject_data_accumulating": (
                    candidate_evaluations > 0
                    or risk_verdicts > 0
                    or rejected_features > 0
                ),
                "silent_drop_risk": silent_drop,
                "learning_data_flow_fresh": not learning_data_flow_stale,
                "learning_data_flow_stale": learning_data_flow_stale,
            },
        },
    }


def _preflight(
    *,
    status: str = "NOT_ACCUMULATING",
    ledger_rows: int = 0,
    admission_rows: int = 0,
    blocked_outcomes: int = 0,
    probe_outcomes: int = 0,
    review_status: str | None = None,
    currently_accumulating: bool = False,
) -> dict:
    return {
        "status": status,
        "reason": "fixture",
        "next_actions": ["fixture_next_action"],
        "answers": {
            "currently_accumulating_evidence": currently_accumulating,
            "silent_drop_risk": ledger_rows == 0,
            "historical_counterfactual_candidates_present": False,
        },
        "activation_blockers": [],
        "source": {"source_activation_status": "SYNCED_CLEAN", "source_activation_ready": True},
        "writer_config": {
            "writer_config_status": "ENABLED",
            "writer_config_reason": "fixture",
        },
        "writer_process": {
            "writer_process_status": "ENABLED",
            "writer_process_reason": "fixture",
        },
        "learning_loop": {
            "learning_loop_status": "RUNNING" if currently_accumulating else "NOT_SEEN",
            "learning_loop_reason": "fixture",
            "learning_loop_last_review_status": review_status,
        },
        "ledger": {
            "ledger_status": "MISSING" if ledger_rows == 0 else "ADMISSION_ROWS_PRESENT",
            "ledger_total_rows": ledger_rows,
            "admission_decision_count": admission_rows,
            "blocked_signal_outcome_count": blocked_outcomes,
            "probe_outcome_count": probe_outcomes,
            "blocked_signal_outcome_review_status": review_status,
        },
    }


def test_pg_cost_gate_rejects_without_ledger_recommend_bounded_learning_lane() -> None:
    result = classify_demo_learning_evidence(
        order_scorecard=_order_scorecard(
            candidate_evaluations=80,
            risk_verdicts=70,
            rejected_features=70,
            cost_gate=True,
        ),
        learning_preflight=_preflight(),
    )

    assert result["status"] == "PG_REJECTS_RECORDED_LEARNING_LANE_NOT_ACCUMULATING"
    assert result["next_action"] == (
        "enable_bounded_cost_gate_learning_lane_after_operator_review"
    )
    assert result["global_cost_gate_lowering_recommended"] is False
    assert result["main_cost_gate_adjustment"] == "NONE"
    assert result["order_authority"] == "NOT_GRANTED"
    assert result["answers"]["cost_gate_rejects_recorded_in_pg"] is True
    assert result["answers"]["order_flow_evidence_starved"] is True
    assert result["key_counts"]["order_flow_evidence_status"] == (
        "COST_GATE_REJECT_WALL_NO_ORDER_FLOW_EVIDENCE"
    )
    assert result["key_counts"]["cost_gate_adjustment_recommendation_status"] == (
        "BOUNDED_LEARNING_LANE_ACTIVATION_RECOMMENDED"
    )
    assert result["key_counts"]["cost_gate_learning_gate_adjustment"] == (
        "ENABLE_LEDGER_AND_OUTCOME_REVIEW_FIRST"
    )
    assert result["cost_gate_adjustment_recommendation"][
        "global_cost_gate_lowering_recommended"
    ] is False
    assert result["answers"]["bounded_demo_learning_lane_recommended"] is True


def test_cost_gate_adjustment_recommendation_never_lowers_main_gate() -> None:
    order_flow = classify_order_flow_evidence(
        candidate_or_reject_data=True,
        cost_gate_rejects_recorded=True,
        orders=0,
        fills=0,
    )
    recommendation = classify_cost_gate_adjustment_recommendation(
        cost_gate_rejects_recorded=True,
        order_flow_evidence=order_flow,
        learning_data_flow_stale=False,
        learning_evidence_accumulating=False,
        blocked_outcome_review_candidate=False,
    )

    assert recommendation["status"] == "BOUNDED_LEARNING_LANE_ACTIVATION_RECOMMENDED"
    assert recommendation["main_cost_gate_adjustment"] == "NONE"
    assert recommendation["global_cost_gate_lowering_recommended"] is False
    assert recommendation["learning_gate_adjustment"] == (
        "ENABLE_LEDGER_AND_OUTCOME_REVIEW_FIRST"
    )
    assert recommendation["order_authority"] == "NOT_GRANTED"


def test_order_flow_evidence_scorecard_distinguishes_no_fills_from_no_orders() -> None:
    no_orders = classify_order_flow_evidence(
        candidate_or_reject_data=True,
        cost_gate_rejects_recorded=True,
        orders=0,
        fills=0,
    )
    assert no_orders["status"] == "COST_GATE_REJECT_WALL_NO_ORDER_FLOW_EVIDENCE"
    assert no_orders["answers"]["order_flow_evidence_starved"] is True

    no_fills = classify_order_flow_evidence(
        candidate_or_reject_data=True,
        cost_gate_rejects_recorded=True,
        orders=3,
        fills=0,
    )
    assert no_fills["status"] == "DEMO_ORDER_FLOW_PRESENT_NO_FILL_EVIDENCE"
    assert no_fills["answers"]["recent_order_flow_present"] is True
    assert no_fills["answers"]["recent_fill_evidence_present"] is False

    fills = classify_order_flow_evidence(
        candidate_or_reject_data=True,
        cost_gate_rejects_recorded=True,
        orders=3,
        fills=1,
    )
    assert fills["status"] == "DEMO_FILL_EVIDENCE_PRESENT"
    assert fills["answers"]["recent_fill_evidence_present"] is True


def test_observation_only_telemetry_is_not_actionable_silent_drop() -> None:
    result = classify_demo_learning_evidence(
        order_scorecard=_order_scorecard(),
        learning_preflight=_preflight(),
    )

    assert result["status"] == "OBSERVATION_TELEMETRY_ACTIVE_NO_ACTIONABLE_LEDGER"
    assert result["answers"]["demo_context_data_accumulating"] is True
    assert result["answers"]["demo_observation_only_contexts_active"] is True
    assert result["answers"]["order_flow_silent_drop_risk"] is False


def test_stale_demo_learning_flow_blocks_pg_reject_learning_claim() -> None:
    result = classify_demo_learning_evidence(
        order_scorecard=_order_scorecard(
            candidate_evaluations=80,
            risk_verdicts=70,
            rejected_features=70,
            cost_gate=True,
            learning_data_flow_stale=True,
        ),
        learning_preflight=_preflight(),
    )

    assert result["status"] == "DEMO_LEARNING_DATA_FLOW_STALE"
    assert result["next_action"] == (
        "restore_demo_data_flow_before_cost_gate_learning_activation"
    )
    assert result["answers"]["cost_gate_rejects_recorded_in_pg"] is True
    assert result["answers"]["learning_data_flow_stale"] is True
    assert result["key_counts"]["data_flow_freshness_status"] == (
        "LEARNING_DATA_FLOW_STALE"
    )
    assert result["key_counts"]["latest_learning_age_seconds"] == 8461


def test_actionable_context_silent_drop_takes_priority_over_learning_lane() -> None:
    result = classify_demo_learning_evidence(
        order_scorecard=_order_scorecard(
            observation_only=False,
            silent_drop=True,
        ),
        learning_preflight=_preflight(),
    )

    assert result["status"] == "ACTIONABLE_CONTEXT_SILENT_DROP_RISK"
    assert result["next_action"] == (
        "diagnose_context_to_candidate_pipeline_before_cost_gate_changes"
    )


def test_blocked_outcome_review_candidate_routes_to_operator_review() -> None:
    result = classify_demo_learning_evidence(
        order_scorecard=_order_scorecard(
            candidate_evaluations=80,
            risk_verdicts=70,
            rejected_features=70,
            cost_gate=True,
        ),
        learning_preflight=_preflight(
            status="REVIEW_CANDIDATE_OPERATOR_REVIEW",
            ledger_rows=10,
            admission_rows=4,
            blocked_outcomes=6,
            review_status="DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT",
            currently_accumulating=True,
        ),
    )

    assert result["status"] == "LEARNING_REVIEW_CANDIDATES_PRESENT"
    assert result["next_action"] == (
        "operator_review_blocked_outcome_scorecard_before_demo_probe_authority"
    )
    assert result["answers"]["blocked_outcome_review_candidate_present"] is True
    assert result["answers"]["bounded_demo_learning_lane_recommended"] is True
    assert result["key_counts"]["cost_gate_adjustment_recommendation_status"] == (
        "BOUNDED_DEMO_PROBE_AUTHORITY_REVIEW_READY"
    )
    assert result["key_counts"]["cost_gate_learning_gate_adjustment"] == (
        "OPERATOR_REVIEW_BOUNDED_SIDE_CELL_DEMO_PROBE"
    )


def test_markdown_surfaces_composite_component_status() -> None:
    payload = {
        "generated_at_utc": "2026-06-21T00:00:00+00:00",
        "engine_modes": ["demo", "live_demo"],
        "lookback_hours": 24,
        "classification": classify_demo_learning_evidence(
            order_scorecard=_order_scorecard(
                candidate_evaluations=80,
                risk_verdicts=70,
                rejected_features=70,
                cost_gate=True,
            ),
            learning_preflight=_preflight(),
        ),
        "order_stall_scorecard": _order_scorecard(cost_gate=True),
        "cost_gate_learning_preflight": _preflight(),
    }

    markdown = render_markdown(payload)

    assert "# Demo Learning Evidence Audit" in markdown
    assert "PG_REJECTS_RECORDED_LEARNING_LANE_NOT_ACCUMULATING" in markdown
    assert "Global Cost Gate lowering recommended: `False`" in markdown
    assert "cost_gate_learning_preflight" in markdown
