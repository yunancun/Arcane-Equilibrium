from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane.sealed_horizon_operator_review import (
    APPROVED_FOR_PREFLIGHT_STATUS,
    build_sealed_horizon_operator_review,
    expected_sealed_horizon_operator_review_typed_confirm,
    render_markdown,
)
from cost_gate_learning_lane.sealed_horizon_probe_preflight import (
    build_sealed_horizon_bounded_demo_probe_preflight,
)


NOW = dt.datetime(2026, 6, 22, 12, 0, tzinfo=dt.timezone.utc)


def _sealed_evidence(**overrides) -> dict:
    payload = {
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
    payload.update(overrides)
    return payload


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
        "answers": {
            "currently_accumulating_evidence": status == "DATA_ACCUMULATING",
        },
        "ledger": {
            "admission_decision_count": 100 if status == "DATA_ACCUMULATING" else 0,
            "blocked_signal_outcome_count": 50 if status == "DATA_ACCUMULATING" else 0,
            "probe_outcome_count": 0,
        },
    }


def _preflight(
    *,
    sealed: dict | None = None,
    activation_status: str = "NOT_ACCUMULATING",
) -> dict:
    return build_sealed_horizon_bounded_demo_probe_preflight(
        sealed_horizon_learning_evidence=sealed or _sealed_evidence(),
        decision_packet=_decision_packet(),
        activation_preflight=_activation(activation_status),
        now_utc=NOW,
    )


def test_defer_review_records_no_authority_and_preflight_still_blocks() -> None:
    sealed = _sealed_evidence()
    review = build_sealed_horizon_operator_review(
        sealed_horizon_learning_evidence=sealed,
        preflight=_preflight(sealed=sealed),
        decision="defer",
        operator_id="operator-reviewer",
        now_utc=NOW,
    )

    packet = build_sealed_horizon_bounded_demo_probe_preflight(
        sealed_horizon_learning_evidence=sealed,
        decision_packet=_decision_packet(),
        activation_preflight=_activation(),
        operator_review=review,
        now_utc=NOW,
    )

    assert review["status"] == "PENDING_OPERATOR_REVIEW"
    assert review["operator_review_approved"] is False
    assert review["probe_authority_granted"] is False
    assert review["order_authority_granted"] is False
    assert packet["status"] == "OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE_REQUIRED"
    assert packet["answers"]["operator_review_recorded"] is False


def test_approved_review_closes_operator_gate_but_not_learning_lane() -> None:
    sealed = _sealed_evidence()
    preflight = _preflight(sealed=sealed)
    typed_confirm = expected_sealed_horizon_operator_review_typed_confirm(
        "ma_crossover|BTCUSDT|Sell",
        240,
    )
    review = build_sealed_horizon_operator_review(
        sealed_horizon_learning_evidence=sealed,
        preflight=preflight,
        decision="approve-preflight",
        operator_id="operator-reviewer",
        typed_confirm=typed_confirm,
        now_utc=NOW,
    )
    markdown = render_markdown(review)

    packet = build_sealed_horizon_bounded_demo_probe_preflight(
        sealed_horizon_learning_evidence=sealed,
        decision_packet=_decision_packet(),
        activation_preflight=_activation(),
        operator_review=review,
        now_utc=NOW,
    )

    assert review["status"] == APPROVED_FOR_PREFLIGHT_STATUS
    assert review["operator_review_approved"] is True
    assert review["answers"]["bounded_demo_probe_authorized"] is False
    assert review["answers"]["probe_authority_granted"] is False
    assert review["answers"]["order_authority_granted"] is False
    assert packet["status"] == "PRODUCTION_LEARNING_LANE_NOT_READY"
    assert packet["answers"]["operator_review_recorded"] is True
    assert packet["answers"]["production_learning_lane_accumulating"] is False
    assert "Sealed Horizon Operator Review" in markdown
    assert typed_confirm in markdown


def test_wrong_typed_confirm_does_not_approve_review() -> None:
    sealed = _sealed_evidence()
    review = build_sealed_horizon_operator_review(
        sealed_horizon_learning_evidence=sealed,
        preflight=_preflight(sealed=sealed),
        decision="approve-preflight",
        operator_id="operator-reviewer",
        typed_confirm="approve_sealed_horizon_preflight:wrong:240",
        now_utc=NOW,
    )

    assert review["status"] == "TYPED_CONFIRM_REQUIRED"
    assert review["operator_review_approved"] is False
    assert "typed_confirm_matches_for_approval" in review["blocking_gates"]
    assert review["answers"]["probe_authority_granted"] is False


def test_mismatched_preflight_does_not_approve_review() -> None:
    sealed = _sealed_evidence()
    mismatched_preflight = _preflight(
        sealed=_sealed_evidence(side_cell_key="ma_crossover|ETHUSDT|Sell")
    )
    typed_confirm = expected_sealed_horizon_operator_review_typed_confirm(
        "ma_crossover|BTCUSDT|Sell",
        240,
    )
    review = build_sealed_horizon_operator_review(
        sealed_horizon_learning_evidence=sealed,
        preflight=mismatched_preflight,
        decision="approve-preflight",
        operator_id="operator-reviewer",
        typed_confirm=typed_confirm,
        now_utc=NOW,
    )

    assert review["status"] == "SEALED_HORIZON_PREFLIGHT_NOT_ALIGNED"
    assert review["operator_review_approved"] is False
    assert "sealed_horizon_probe_preflight_aligned_for_approval" in review[
        "blocking_gates"
    ]


def test_authority_granting_input_fails_closed() -> None:
    sealed = _sealed_evidence()
    authority_preflight = _preflight(sealed=sealed)
    authority_preflight["answers"]["probe_authority_granted"] = True
    typed_confirm = expected_sealed_horizon_operator_review_typed_confirm(
        "ma_crossover|BTCUSDT|Sell",
        240,
    )
    review = build_sealed_horizon_operator_review(
        sealed_horizon_learning_evidence=sealed,
        preflight=authority_preflight,
        decision="approve-preflight",
        operator_id="operator-reviewer",
        typed_confirm=typed_confirm,
        now_utc=NOW,
    )

    assert review["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert review["operator_review_approved"] is False
    assert review["probe_authority_granted"] is False
    assert review["order_authority_granted"] is False
    assert "authority_boundary_preserved" in review["blocking_gates"]
