from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane.sealed_horizon_probe_preflight import (
    build_sealed_horizon_bounded_demo_probe_preflight,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 22, 12, 0, tzinfo=dt.timezone.utc)


def _sealed_evidence() -> dict:
    return {
        "schema_version": "sealed_horizon_learning_evidence_v1",
        "generated_at_utc": "2026-06-22T11:55:00+00:00",
        "status": "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT",
        "side_cell_key": "ma_crossover|BTCUSDT|Sell",
        "source_kind": "horizon_specific_sealed_replay",
        "outcome_horizon_minutes": 240,
        "outcomes": {
            "blocked_signal_outcome_count": 16515,
            "avg_gross_bps": 7.0511,
            "avg_net_bps": 3.0511,
            "net_positive_pct": 68.5619,
        },
        "review": {
            "status": "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT",
            "top_side_cell_key": "ma_crossover|BTCUSDT|Sell",
            "top_side_cell_status": "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE",
            "blocked_signal_outcome_count": 16515,
        },
        "answers": {
            "candidate_clears_operator_review_gate": True,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
    }


def _decision_packet() -> dict:
    return {
        "schema_version": "cost_gate_profit_learning_decision_packet_v1",
        "generated_at_utc": "2026-06-22T11:56:00+00:00",
        "status": "OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE",
        "reason": "sealed_horizon_learning_evidence_clears_review_thresholds",
        "answers": {
            "sealed_horizon_learning_evidence_available": True,
            "sealed_horizon_learning_evidence_candidates_present": True,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "sealed_horizon_learning_evidence": {
            "status": "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT",
            "side_cell_key": "ma_crossover|BTCUSDT|Sell",
            "outcome_horizon_minutes": 240,
            "review_ready": True,
        },
    }


def _activation(status: str = "NOT_ACCUMULATING") -> dict:
    return {
        "schema_version": "cost_gate_demo_learning_lane_activation_preflight_v1",
        "generated_at_utc": "2026-06-22T11:57:00+00:00",
        "status": status,
        "next_actions": [
            "sync_runtime_source_then_enable_learning_lane_writer_after_operator_review",
            "install_or_run_cost_gate_learning_lane_cron",
        ],
        "answers": {
            "currently_accumulating_evidence": status == "DATA_ACCUMULATING",
        },
        "ledger": {
            "admission_decision_count": 100 if status == "DATA_ACCUMULATING" else 0,
            "blocked_signal_outcome_count": 50 if status == "DATA_ACCUMULATING" else 0,
            "probe_outcome_count": 0,
        },
    }


def _operator_review(**overrides) -> dict:
    payload = {
        "schema_version": "sealed_horizon_operator_review_v1",
        "generated_at_utc": "2026-06-22T11:58:00+00:00",
        "status": "APPROVED_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT",
        "side_cell_key": "ma_crossover|BTCUSDT|Sell",
        "outcome_horizon_minutes": 240,
        "operator_review_approved": True,
        "main_cost_gate_adjustment": "NONE",
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "promotion_evidence": False,
    }
    payload.update(overrides)
    return payload


def test_preflight_blocks_on_operator_review_and_production_lane() -> None:
    packet = build_sealed_horizon_bounded_demo_probe_preflight(
        sealed_horizon_learning_evidence=_sealed_evidence(),
        decision_packet=_decision_packet(),
        activation_preflight=_activation(),
        now_utc=NOW,
    )

    assert packet["status"] == "OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE_REQUIRED"
    assert packet["answers"]["sealed_horizon_evidence_ready"] is True
    assert packet["answers"]["decision_packet_aligned"] is True
    assert packet["answers"]["operator_review_recorded"] is False
    assert packet["answers"]["production_learning_lane_accumulating"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["main_cost_gate_adjustment"] == "NONE"
    assert "operator_sealed_horizon_review_recorded" in packet["blocking_gates"]
    assert "production_learning_lane_accumulating" in packet["blocking_gates"]


def test_operator_review_without_learning_lane_still_blocks_probe() -> None:
    packet = build_sealed_horizon_bounded_demo_probe_preflight(
        sealed_horizon_learning_evidence=_sealed_evidence(),
        decision_packet=_decision_packet(),
        activation_preflight=_activation(),
        operator_review=_operator_review(),
        now_utc=NOW,
    )

    assert packet["status"] == "PRODUCTION_LEARNING_LANE_NOT_READY"
    assert packet["answers"]["operator_review_recorded"] is True
    assert packet["answers"]["production_learning_lane_accumulating"] is False
    assert packet["blocking_gates"] == ["production_learning_lane_accumulating"]


def test_all_review_gates_ready_still_does_not_grant_authority() -> None:
    packet = build_sealed_horizon_bounded_demo_probe_preflight(
        sealed_horizon_learning_evidence=_sealed_evidence(),
        decision_packet=_decision_packet(),
        activation_preflight=_activation("DATA_ACCUMULATING"),
        operator_review=_operator_review(),
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["status"] == "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION"
    assert packet["blocking_gate_count"] == 0
    assert packet["answers"]["ready_for_operator_bounded_demo_probe_authorization"] is True
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["global_cost_gate_lowering_recommended"] is False
    assert "Sealed Horizon Bounded Demo Probe Preflight" in markdown
    assert "ma_crossover|BTCUSDT|Sell" in markdown


def test_authority_granting_input_fails_closed() -> None:
    packet = build_sealed_horizon_bounded_demo_probe_preflight(
        sealed_horizon_learning_evidence=_sealed_evidence(),
        decision_packet=_decision_packet(),
        activation_preflight=_activation("DATA_ACCUMULATING"),
        operator_review=_operator_review(probe_authority_granted=True),
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["answers"]["ready_for_operator_bounded_demo_probe_authorization"] is False
    assert "authority_boundary_preserved" in packet["blocking_gates"]
