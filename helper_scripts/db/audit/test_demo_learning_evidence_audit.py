from __future__ import annotations

from helper_scripts.db.audit.demo_learning_evidence_audit import (
    classify_demo_learning_evidence,
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
            "answers": {
                "context_payload_observation_only": observation_only,
                "candidate_or_reject_data_accumulating": (
                    candidate_evaluations > 0
                    or risk_verdicts > 0
                    or rejected_features > 0
                ),
                "silent_drop_risk": silent_drop,
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
    assert result["answers"]["bounded_demo_learning_lane_recommended"] is True


def test_observation_only_telemetry_is_not_actionable_silent_drop() -> None:
    result = classify_demo_learning_evidence(
        order_scorecard=_order_scorecard(),
        learning_preflight=_preflight(),
    )

    assert result["status"] == "OBSERVATION_TELEMETRY_ACTIVE_NO_ACTIONABLE_LEDGER"
    assert result["answers"]["demo_context_data_accumulating"] is True
    assert result["answers"]["demo_observation_only_contexts_active"] is True
    assert result["answers"]["order_flow_silent_drop_risk"] is False


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
    assert result["answers"]["bounded_demo_learning_lane_recommended"] is False


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
