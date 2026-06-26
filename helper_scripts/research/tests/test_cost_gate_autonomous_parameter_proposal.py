"""Tests for no-authority Cost Gate autonomous parameter proposals."""

from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane.autonomous_parameter_proposal import (
    build_autonomous_parameter_proposal,
    render_markdown,
)


def _learning_ssot_decision() -> dict:
    return {
        "schema_version": "cost_gate_learning_ssot_decision_v1",
        "generated_at_utc": "2026-06-24T05:00:00+00:00",
        "status": "ARTIFACT_LEDGER_CURRENT_SSOT",
        "current_learning_ssot": "artifact_probe_ledger_jsonl",
        "target_learning_ssot": "pg_backed_cost_gate_learning_ledger",
        "ssot_decision": {
            "artifact_probe_ledger_is_current_ssot": True,
            "pg_backed_ledger_is_current_ssot": False,
            "pg_backed_cutover_ready": False,
        },
        "answers": {
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
    }


def _false_negative_candidate_packet() -> dict:
    return {
        "schema_version": "cost_gate_false_negative_candidate_packet_v1",
        "generated_at_utc": "2026-06-24T05:01:00+00:00",
        "status": "COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW",
        "summary": {
            "false_negative_candidate_count": 1,
            "ranked_candidate_count": 1,
            "top_false_negative_side_cell_key": "grid_trading|AVAXUSDT|Sell",
        },
        "answers": {
            "operator_review_ready": True,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "ranked_false_negative_candidates": [
            {
                "side_cell_key": "grid_trading|AVAXUSDT|Sell",
                "candidate_class": "false_negative_after_cost",
                "false_negative_rank": 1,
                "learning_diagnosis": "FALSE_NEGATIVE_CANDIDATE_AFTER_COST",
                "status": "REVIEW_CANDIDATE_OPERATOR_REVIEW",
                "reason": "blocked_side_cell_clears_after_cost_thresholds",
                "next_action": (
                    "operator_review_bounded_probe_authority_without_global_gate_lowering"
                ),
                "strategy_names": ["grid_trading"],
                "symbols": ["AVAXUSDT"],
                "sides": ["Sell"],
                "horizon_minutes": [60],
                "dominant_horizon_minutes": 60,
                "outcome_count": 24,
                "avg_gross_bps": 82.0,
                "avg_net_bps": 73.4,
                "avg_cost_bps": 8.6,
                "net_positive_pct": 91.7,
                "net_cost_cushion_bps": 73.4563,
                "wrongful_block_score": 146.9126,
                "operator_review_required": True,
                "global_cost_gate_lowering_recommended": False,
                "probe_authority_granted": False,
                "order_authority_granted": False,
                "promotion_evidence": False,
            }
        ],
    }


def test_parameter_proposal_blocks_until_profit_evidence_quality_cleared() -> None:
    packet = build_autonomous_parameter_proposal(
        learning_ssot_decision=_learning_ssot_decision(),
        false_negative_candidate_packet=_false_negative_candidate_packet(),
        now_utc=dt.datetime(2026, 6, 24, 5, 2, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "PROFIT_EVIDENCE_QUALITY_NOT_CLEARED"
    assert packet["proposal"] is None
    assert "profit_evidence_quality_cleared" in packet["blocking_gates"]
    assert packet["answers"]["reviewable_parameter_proposal_emitted"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["order_submission_performed"] is False


def test_parameter_proposal_emits_review_packet_only_after_quality_gate() -> None:
    packet = build_autonomous_parameter_proposal(
        learning_ssot_decision=_learning_ssot_decision(),
        false_negative_candidate_packet=_false_negative_candidate_packet(),
        profit_evidence_quality_status="EXPLICITLY_QUARANTINED_BY_OPERATOR",
        now_utc=dt.datetime(2026, 6, 24, 5, 2, tzinfo=dt.timezone.utc),
    )
    markdown = render_markdown(packet)
    proposal = packet["proposal"]

    assert packet["status"] == "REVIEWABLE_PARAMETER_PROPOSAL_READY"
    assert proposal["proposal_status"] == "INACTIVE_REVIEW_PACKET_ONLY"
    assert proposal["side_cell_key"] == "grid_trading|AVAXUSDT|Sell"
    assert proposal["proposed_parameter_changes"][2] == {
        "parameter": "main_cost_gate_adjustment",
        "current_value": "UNCHANGED",
        "proposed_value": "NONE",
        "mutation_allowed_by_this_packet": False,
    }
    assert proposal["proposed_parameter_changes"][3] == {
        "parameter": "bounded_demo_probe_cap_envelope",
        "current_value": "UNCHANGED",
        "proposed_value": "REQUIRES_SEPARATE_OPERATOR_QC_E3_BB_REVIEW",
        "mutation_allowed_by_this_packet": False,
    }
    assert (
        "cap_envelope_evidence_floor_satisfied_if_cap_change_is_requested"
        in proposal["required_pre_authorization_evidence"]
    )
    assert (
        proposal["cap_envelope_evidence_floor"]["schema_version"]
        == "cost_gate_cap_envelope_evidence_floor_v1"
    )
    assert "global_cost_gate_lowering" in proposal["cap_envelope_evidence_floor"][
        "forbidden_shortcuts"
    ]
    assert all(
        change["mutation_allowed_by_this_packet"] is False
        for change in proposal["proposed_parameter_changes"]
    )
    assert packet["answers"]["learning_output_converted_to_reviewable_proposal"] is True
    assert packet["answers"]["bounded_demo_probe_authorized"] is False
    assert packet["answers"]["cap_envelope_mutation_allowed"] is False
    assert packet["answers"]["active_runtime_order_authority"] is False
    assert packet["answers"]["operator_authorization_object_emitted"] is False
    assert packet["answers"]["promotion_evidence"] is False
    assert "review packet only" in markdown
    assert "Cap envelope mutation allowed: `False`" in markdown


def test_parameter_proposal_fails_closed_on_authority_bearing_input() -> None:
    candidate_packet = _false_negative_candidate_packet()
    candidate_packet["ranked_false_negative_candidates"][0]["probe_authority_granted"] = True

    packet = build_autonomous_parameter_proposal(
        learning_ssot_decision=_learning_ssot_decision(),
        false_negative_candidate_packet=candidate_packet,
        profit_evidence_quality_status="DONE",
        now_utc=dt.datetime(2026, 6, 24, 5, 2, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["proposal"] is None
    assert packet["blocking_gates"][0] == "authority_boundary_preserved"
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_parameter_proposal_fails_closed_on_truthy_authority_strings() -> None:
    candidate_packet = _false_negative_candidate_packet()
    candidate_packet["answers"]["order_authority_granted"] = "true"
    candidate_packet["ranked_false_negative_candidates"][0][
        "promotion_evidence"
    ] = 1

    packet = build_autonomous_parameter_proposal(
        learning_ssot_decision=_learning_ssot_decision(),
        false_negative_candidate_packet=candidate_packet,
        profit_evidence_quality_status="DONE",
        now_utc=dt.datetime(2026, 6, 24, 5, 2, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["proposal"] is None
    assert packet["candidate"]["promotion_evidence"] is True
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["promotion_evidence"] is False


def test_parameter_proposal_requires_artifact_current_learning_ssot() -> None:
    ssot = _learning_ssot_decision()
    ssot["current_learning_ssot"] = "NONE"
    ssot["ssot_decision"]["artifact_probe_ledger_is_current_ssot"] = False

    packet = build_autonomous_parameter_proposal(
        learning_ssot_decision=ssot,
        false_negative_candidate_packet=_false_negative_candidate_packet(),
        profit_evidence_quality_status="DONE",
        now_utc=dt.datetime(2026, 6, 24, 5, 2, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "LEARNING_SSOT_DECISION_NOT_READY"
    assert packet["proposal"] is None
    assert "learning_ssot_ready" in packet["blocking_gates"]
