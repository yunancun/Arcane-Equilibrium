from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane.false_negative_bounded_probe_preflight import (
    FALSE_NEGATIVE_BOUNDED_PROBE_PREFLIGHT_SCHEMA_VERSION,
    build_false_negative_bounded_demo_probe_preflight,
    render_markdown,
)
from cost_gate_learning_lane.false_negative_operator_review import (
    APPROVED_FOR_PREFLIGHT_STATUS,
)


NOW = dt.datetime(2026, 6, 24, 5, 30, tzinfo=dt.timezone.utc)
SIDE_CELL = "grid_trading|AVAXUSDT|Sell"


def _proposal(**overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_autonomous_parameter_proposal_v1",
        "generated_at_utc": "2026-06-24T05:10:00+00:00",
        "status": "REVIEWABLE_PARAMETER_PROPOSAL_READY",
        "selected_side_cell_key": SIDE_CELL,
        "candidate": {
            "side_cell_key": SIDE_CELL,
            "candidate_class": "false_negative_after_cost",
            "strategy_names": ["grid_trading"],
            "symbols": ["AVAXUSDT"],
            "sides": ["Sell"],
            "dominant_horizon_minutes": 60,
        },
        "proposal": {
            "proposal_id": "cost_gate_parameter_proposal:fixture",
            "proposal_status": "INACTIVE_REVIEW_PACKET_ONLY",
            "proposal_kind": "cost_gate_false_negative_bounded_demo_probe_candidate",
            "side_cell_key": SIDE_CELL,
            "strategy_names": ["grid_trading"],
            "symbols": ["AVAXUSDT"],
            "sides": ["Sell"],
            "dominant_horizon_minutes": 60,
            "profit_thesis": {
                "avg_gross_bps": 77.5511,
                "avg_net_bps": 73.5511,
                "avg_cost_bps": 4.0,
                "net_positive_pct": 100.0,
                "net_cost_cushion_bps": 73.5511,
                "wrongful_block_score": 147.1021,
                "outcome_count": 48,
            },
        },
        "answers": {
            "reviewable_parameter_proposal_emitted": True,
            "bounded_demo_probe_authorized": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
    }
    payload.update(overrides)
    return payload


def _review(**overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_false_negative_operator_review_v1",
        "generated_at_utc": "2026-06-24T05:11:00+00:00",
        "status": "PENDING_COST_GATE_FALSE_NEGATIVE_OPERATOR_REVIEW",
        "decision": "defer",
        "selected_side_cell_key": SIDE_CELL,
        "selected_false_negative_rank": 1,
        "operator_review_approved_for_preflight": False,
        "typed_confirm_expected": (
            "approve_cost_gate_false_negative_preflight:"
            "grid_trading|AVAXUSDT|Sell:1"
        ),
        "candidate": {
            "side_cell_key": SIDE_CELL,
            "false_negative_rank": 1,
            "strategy_names": ["grid_trading"],
            "symbols": ["AVAXUSDT"],
            "sides": ["Sell"],
            "dominant_horizon_minutes": 60,
            "horizon_minutes": [60],
        },
        "answers": {
            "operator_review_approved_for_preflight": False,
            "bounded_demo_probe_preflight_approved": False,
            "review_grants_runtime_authority": False,
            "bounded_demo_probe_authorized": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
    }
    payload.update(overrides)
    return payload


def test_pending_review_emits_no_authority_preflight_design_only() -> None:
    packet = build_false_negative_bounded_demo_probe_preflight(
        autonomous_parameter_proposal=_proposal(),
        false_negative_operator_review=_review(),
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["schema_version"] == FALSE_NEGATIVE_BOUNDED_PROBE_PREFLIGHT_SCHEMA_VERSION
    assert packet["status"] == "OPERATOR_REVIEW_REQUIRED"
    assert packet["side_cell_key"] == SIDE_CELL
    assert packet["bounded_demo_probe_design"]["status"] == (
        "OPERATOR_REVIEW_READY_FOR_BOUNDED_DEMO_PROBE_DESIGN"
    )
    assert packet["answers"]["bounded_demo_probe_design_ready_for_operator_review"] is True
    assert packet["answers"]["ready_for_operator_bounded_demo_probe_authorization"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert "False-Negative Bounded Demo Probe Preflight" in markdown


def test_approved_review_reaches_authorization_review_without_order_authority() -> None:
    review = _review(
        status=APPROVED_FOR_PREFLIGHT_STATUS,
        decision="approve-preflight",
        operator_review_approved_for_preflight=True,
        answers={
            "operator_review_approved_for_preflight": True,
            "bounded_demo_probe_preflight_approved": True,
            "review_grants_runtime_authority": False,
            "bounded_demo_probe_authorized": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
    )
    packet = build_false_negative_bounded_demo_probe_preflight(
        autonomous_parameter_proposal=_proposal(),
        false_negative_operator_review=review,
        now_utc=NOW,
    )

    assert packet["status"] == "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION"
    assert packet["bounded_demo_probe_design"]["status"] == (
        "READY_FOR_SEPARATE_OPERATOR_AUTHORIZATION"
    )
    assert packet["answers"]["ready_for_operator_bounded_demo_probe_authorization"] is True
    assert packet["answers"]["bounded_demo_probe_authorized"] is False
    assert packet["answers"]["order_submission_performed"] is False


def test_preserved_approval_review_reaches_preflight_without_runtime_authority() -> None:
    review = _review(
        status=APPROVED_FOR_PREFLIGHT_STATUS,
        decision="approve-preflight",
        operator_review_approved_for_preflight=True,
        defer_refresh_preserved_existing_approval=True,
        defer_refresh_decision="defer",
        answers={
            "operator_review_approved_for_preflight": True,
            "bounded_demo_probe_preflight_approved": True,
            "review_grants_runtime_authority": False,
            "bounded_demo_probe_authorized": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
    )
    packet = build_false_negative_bounded_demo_probe_preflight(
        autonomous_parameter_proposal=_proposal(),
        false_negative_operator_review=review,
        now_utc=NOW,
    )

    assert packet["status"] == "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION"
    assert packet["answers"]["ready_for_operator_bounded_demo_probe_authorization"] is True
    assert packet["answers"]["bounded_demo_probe_authorized"] is False
    assert packet["answers"]["global_cost_gate_lowering_recommended"] is False
    assert packet["answers"]["main_cost_gate_adjustment"] == "NONE"
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["promotion_evidence"] is False


def test_candidate_alignment_mismatch_blocks_preflight() -> None:
    review = _review(
        selected_side_cell_key="grid_trading|ATOMUSDT|Sell",
        candidate={
            "side_cell_key": "grid_trading|ATOMUSDT|Sell",
            "false_negative_rank": 1,
            "strategy_names": ["grid_trading"],
            "symbols": ["ATOMUSDT"],
            "sides": ["Sell"],
            "dominant_horizon_minutes": 60,
            "horizon_minutes": [60],
        },
    )
    packet = build_false_negative_bounded_demo_probe_preflight(
        autonomous_parameter_proposal=_proposal(),
        false_negative_operator_review=review,
        now_utc=NOW,
    )

    assert packet["status"] == "CANDIDATE_ALIGNMENT_MISMATCH"
    assert "candidate_alignment" in packet["blocking_gates"]
    assert packet["answers"]["probe_authority_granted"] is False


def test_authority_bearing_input_fails_closed() -> None:
    proposal = _proposal()
    proposal["answers"]["order_authority_granted"] = "true"
    packet = build_false_negative_bounded_demo_probe_preflight(
        autonomous_parameter_proposal=proposal,
        false_negative_operator_review=_review(),
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["answers"]["order_authority_granted"] is False
