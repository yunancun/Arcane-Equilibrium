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


def _standing_demo_authorization(**overrides) -> dict:
    payload = {
        "schema_version": "standing_demo_operator_authorization_v1",
        "generated_at_utc": "2026-06-24T05:12:00+00:00",
        "status": "STANDING_DEMO_AUTHORIZATION_ACTIVE",
        "standing_authorization_id": "standing-demo-false-negative-001",
        "operator_id": "operator-test",
        "environment": "demo",
        "scope": "demo_api_only_bounded_probe",
        "demo_only": True,
        "candidate_scoping_required": True,
        "candidate": {
            "side_cell_key": SIDE_CELL,
            "strategy_name": "grid_trading",
            "symbol": "AVAXUSDT",
            "side": "Sell",
            "outcome_horizon_minutes": 60,
        },
        "max_authorized_probe_orders_per_candidate": 2,
        "expires_at_utc": "2026-06-24T12:00:00+00:00",
        "risk_cap_lineage": {
            "risk_source_of_truth": "GUI-backed Rust RiskConfig",
            "cap_source": "current_candidate_envelope.cap_resolution.resolved_cap_usdt",
            "account_equity_usdt": 9552.43426257,
            "per_trade_risk_pct_display": 10.0,
            "per_trade_risk_pct_fraction": 0.1,
            "position_size_max_pct": 25.0,
            "resolved_cap_usdt": 955.24342626,
            "rounded_notional_usdt": 954.6264,
            "single_position_budget_usdt": 2388.10856564,
            "bounded_probe_local_cap_usdt_is_authority": False,
            "local_10_usdt_cap_is_global_risk_authority": False,
        },
        "answers": {
            "demo_only": True,
            "candidate_scoping_required": True,
            "live_authority_granted": False,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
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


def test_approved_review_without_gui_risk_cap_fails_closed() -> None:
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

    assert packet["status"] == "GUI_RISK_CAP_INPUT_REQUIRED_FOR_PREFLIGHT"
    assert "gui_risk_cap_lineage_valid_for_preflight" in packet["blocking_gates"]
    assert packet["bounded_demo_probe_design"]["status"] == (
        "NOT_READY_FOR_OPERATOR_PROBE_REVIEW"
    )
    assert packet["answers"]["ready_for_operator_bounded_demo_probe_authorization"] is False
    assert packet["answers"]["bounded_demo_probe_authorized"] is False
    assert packet["answers"]["order_submission_performed"] is False


def test_standing_demo_review_reaches_ready_preflight_without_authority() -> None:
    review = _review(
        status=APPROVED_FOR_PREFLIGHT_STATUS,
        decision="approve-preflight",
        operator_id="operator-test",
        operator_review_approval_source="standing_demo_authorization",
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
            "standing_demo_authorization_consumed": True,
            "operator_review_approval_source": "standing_demo_authorization",
        },
    )
    packet = build_false_negative_bounded_demo_probe_preflight(
        autonomous_parameter_proposal=_proposal(),
        false_negative_operator_review=review,
        standing_demo_authorization=_standing_demo_authorization(),
        now_utc=NOW,
    )

    assert packet["status"] == "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION"
    assert packet["answers"]["standing_demo_authorization_required"] is True
    assert packet["answers"]["standing_demo_authorization_valid"] is True
    assert packet["answers"]["operator_review_approval_source"] == (
        "standing_demo_authorization"
    )
    limits = packet["bounded_demo_probe_design"]["suggested_initial_probe_limits"]
    assert limits["max_demo_notional_usdt_per_order"] == 955.24342626
    assert limits["max_total_demo_notional_usdt_before_review"] == 1910.48685252
    assert limits["max_probe_intents_before_review"] == 2
    assert limits["per_trade_risk_pct_fraction"] == 0.1
    assert limits["per_trade_risk_pct_display"] == 10.0
    assert limits["local_10_usdt_cap_is_global_risk_authority"] is False
    assert packet["answers"]["bounded_demo_probe_authorized"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_standing_demo_review_requires_gui_risk_cap_lineage() -> None:
    review = _review(
        status=APPROVED_FOR_PREFLIGHT_STATUS,
        decision="approve-preflight",
        operator_review_approval_source="standing_demo_authorization",
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
            "standing_demo_authorization_consumed": True,
        },
    )
    standing = _standing_demo_authorization()
    standing.pop("risk_cap_lineage")
    packet = build_false_negative_bounded_demo_probe_preflight(
        autonomous_parameter_proposal=_proposal(),
        false_negative_operator_review=review,
        standing_demo_authorization=standing,
        now_utc=NOW,
    )

    assert packet["status"] == "STANDING_DEMO_AUTHORIZATION_INVALID_FOR_PREFLIGHT"
    assert "standing_demo_authorization_valid_for_preflight" in packet["blocking_gates"]
    assert packet["standing_demo_authorization"]["risk_cap_lineage"]["valid"] is False
    assert packet["answers"]["ready_for_operator_bounded_demo_probe_authorization"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["order_submission_performed"] is False


def test_standing_demo_review_requires_same_valid_envelope_at_preflight() -> None:
    review = _review(
        status=APPROVED_FOR_PREFLIGHT_STATUS,
        decision="approve-preflight",
        operator_review_approval_source="standing_demo_authorization",
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
            "standing_demo_authorization_consumed": True,
        },
    )
    packet = build_false_negative_bounded_demo_probe_preflight(
        autonomous_parameter_proposal=_proposal(),
        false_negative_operator_review=review,
        now_utc=NOW,
    )

    assert packet["status"] == "STANDING_DEMO_AUTHORIZATION_INVALID_FOR_PREFLIGHT"
    assert "standing_demo_authorization_valid_for_preflight" in packet["blocking_gates"]
    assert packet["answers"]["standing_demo_authorization_required"] is True
    assert packet["answers"]["standing_demo_authorization_valid"] is False
    assert packet["answers"]["ready_for_operator_bounded_demo_probe_authorization"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_scope_mismatched_standing_demo_envelope_blocks_preflight() -> None:
    review = _review(
        status=APPROVED_FOR_PREFLIGHT_STATUS,
        decision="approve-preflight",
        operator_review_approval_source="standing_demo_authorization",
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
            "standing_demo_authorization_consumed": True,
        },
    )
    standing = _standing_demo_authorization(
        candidate={"side_cell_key": "grid_trading|ETHUSDT|Sell"}
    )
    packet = build_false_negative_bounded_demo_probe_preflight(
        autonomous_parameter_proposal=_proposal(),
        false_negative_operator_review=review,
        standing_demo_authorization=standing,
        now_utc=NOW,
    )

    assert packet["status"] == "STANDING_DEMO_AUTHORIZATION_INVALID_FOR_PREFLIGHT"
    assert packet["standing_demo_authorization"]["candidate_scope_matches"] is False
    assert packet["answers"]["ready_for_operator_bounded_demo_probe_authorization"] is False
    assert packet["answers"]["order_authority_granted"] is False


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

    assert packet["status"] == "GUI_RISK_CAP_INPUT_REQUIRED_FOR_PREFLIGHT"
    assert packet["answers"]["ready_for_operator_bounded_demo_probe_authorization"] is False
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
