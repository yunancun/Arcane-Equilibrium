from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane.bounded_probe_result_review import (
    BOUNDED_PROBE_RESULT_REVIEW_SCHEMA_VERSION,
    build_bounded_demo_probe_result_review,
    render_markdown,
)
from cost_gate_learning_lane.contract import (
    ADMIT_DECISION,
    BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE,
    PROBE_ADMISSION_DECISION_RECORD_TYPE,
    PROBE_OUTCOME_RECORD_TYPE,
)


NOW = dt.datetime(2026, 6, 22, 13, 0, tzinfo=dt.timezone.utc)
SIDE_CELL = "ma_crossover|BTCUSDT|Sell"


def _preflight(**answer_overrides) -> dict:
    answers = {
        "sealed_horizon_evidence_ready": True,
        "decision_packet_aligned": True,
        "operator_review_recorded": False,
        "production_learning_lane_accumulating": True,
        "ready_for_operator_bounded_demo_probe_authorization": False,
        "bounded_demo_probe_design_ready_for_operator_review": True,
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "promotion_evidence": False,
    }
    answers.update(answer_overrides)
    return {
        "schema_version": "sealed_horizon_bounded_demo_probe_preflight_v1",
        "generated_at_utc": "2026-06-22T12:55:00+00:00",
        "status": "OPERATOR_REVIEW_REQUIRED",
        "side_cell_key": SIDE_CELL,
        "outcome_horizon_minutes": 240,
        "answers": answers,
        "bounded_demo_probe_design": {
            "schema_version": "bounded_demo_probe_design_v1",
            "status": "OPERATOR_REVIEW_READY_FOR_BOUNDED_DEMO_PROBE_DESIGN",
            "candidate": {
                "side_cell_key": SIDE_CELL,
                "strategy_name": "ma_crossover",
                "symbol": "BTCUSDT",
                "side": "Sell",
                "outcome_horizon_minutes": 240,
                "source_kind": "horizon_specific_sealed_replay",
            },
            "suggested_initial_probe_limits": {
                "active": False,
                "requires_separate_operator_authorization": True,
                "max_probe_intents_before_review": 3,
                "max_filled_probe_outcomes_before_review": 3,
                "max_total_filled_probe_outcomes_before_second_review": 10,
                "max_demo_notional_usdt_per_order": 10,
                "max_total_demo_notional_usdt_before_review": 30,
            },
            "success_criteria": {
                "min_filled_probe_outcomes_for_first_review": 3,
                "min_filled_probe_outcomes_for_learning_review": 10,
                "min_realized_avg_net_bps": 0.0,
                "min_realized_net_positive_pct": 60.0,
                "promotion_evidence": False,
            },
            "authority_boundary": {
                "global_cost_gate_lowering_recommended": False,
                "main_cost_gate_adjustment": "NONE",
                "probe_authority_granted": False,
                "order_authority_granted": False,
                "promotion_evidence": False,
            },
        },
    }


def _preflight_with_design_status(status: str) -> dict:
    payload = _preflight()
    payload["bounded_demo_probe_design"]["status"] = status
    return payload


def _admission(i: int) -> dict:
    return {
        "record_type": PROBE_ADMISSION_DECISION_RECORD_TYPE,
        "attempt_id": f"attempt-{i}",
        "side_cell_key": SIDE_CELL,
        "decision": ADMIT_DECISION,
    }


def _outcome(i: int, net_bps: float, gross_bps: float | None = None) -> dict:
    return {
        "record_type": PROBE_OUTCOME_RECORD_TYPE,
        "generated_at_utc": f"2026-06-22T12:{i:02d}:00+00:00",
        "attempt_id": f"attempt-{i}",
        "side_cell_key": SIDE_CELL,
        "realized_net_bps": net_bps,
        "gross_bps": gross_bps if gross_bps is not None else net_bps + 4.0,
    }


def _control(i: int, net_bps: float, horizon_minutes: int = 240) -> dict:
    return {
        "record_type": BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE,
        "generated_at_utc": f"2026-06-22T11:{i:02d}:00+00:00",
        "attempt_id": f"control-{i}",
        "side_cell_key": SIDE_CELL,
        "horizon_minutes": horizon_minutes,
        "realized_net_bps": net_bps,
        "gross_bps": net_bps + 4.0,
    }


def _ledger(nets: list[float]) -> list[dict]:
    rows = []
    for idx, net in enumerate(nets, start=1):
        rows.append(_admission(idx))
        rows.append(_outcome(idx, net))
    return rows


def test_no_probe_outcomes_waits_without_granting_authority() -> None:
    packet = build_bounded_demo_probe_result_review(
        preflight=_preflight(),
        ledger_rows=[],
        now_utc=NOW,
    )

    assert packet["schema_version"] == BOUNDED_PROBE_RESULT_REVIEW_SCHEMA_VERSION
    assert packet["status"] == "NO_PROBE_OUTCOMES_RECORDED"
    assert packet["answers"]["operator_review_required"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["promotion_evidence"] is False
    assert packet["evidence_quality"]["status"] == "NO_PROBE_OUTCOMES_RECORDED"


def test_partial_probe_sample_can_continue_under_existing_review_boundary() -> None:
    packet = build_bounded_demo_probe_result_review(
        preflight=_preflight(),
        ledger_rows=_ledger([2.0, -1.0]),
        now_utc=NOW,
    )

    assert packet["status"] == "COLLECT_MORE_PROBE_OUTCOMES_BEFORE_FIRST_REVIEW"
    assert packet["probe_result_summary"]["completed_probe_outcome_count"] == 2
    assert packet["answers"]["continue_probe_without_operator_review_allowed"] is True
    assert packet["answers"]["operator_review_required"] is False
    assert packet["evidence_quality"]["status"] == "PROBE_SAMPLE_BELOW_FIRST_REVIEW_FLOOR"


def test_first_review_pass_without_control_is_marked_as_anecdote_risk() -> None:
    packet = build_bounded_demo_probe_result_review(
        preflight=_preflight(),
        ledger_rows=_ledger([2.0, 4.0, 1.0]),
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["status"] == "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED"
    assert packet["probe_result_summary"]["avg_realized_net_bps"] == 2.3333
    assert packet["probe_result_summary"]["net_positive_pct"] == 100.0
    assert packet["answers"]["operator_review_required"] is True
    assert packet["answers"]["continue_probe_without_operator_review_allowed"] is False
    assert packet["answers"]["anecdote_risk"] is True
    assert packet["evidence_quality"]["status"] == "CONTROL_COMPARISON_MISSING"
    assert packet["evidence_quality"]["matched_control_outcome_count"] == 0
    assert packet["next_actions"][0] == (
        "record_matched_blocked_signal_outcomes_for_same_side_cell_and_horizon"
    )
    assert "Operator review required" in markdown


def test_first_review_pass_with_matched_control_records_relative_edge() -> None:
    packet = build_bounded_demo_probe_result_review(
        preflight=_preflight(),
        ledger_rows=[
            *_ledger([2.0, 4.0, 1.0]),
            _control(1, 1.0),
            _control(2, -1.0),
            _control(3, 0.0),
        ],
        now_utc=NOW,
    )

    assert packet["status"] == "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED"
    assert packet["answers"]["matched_control_comparison_present"] is True
    assert packet["answers"]["anecdote_risk"] is False
    assert packet["evidence_quality"]["status"] == (
        "FIRST_REVIEW_WITH_MATCHED_CONTROL_COMPARISON"
    )
    assert packet["evidence_quality"]["matched_control_outcome_count"] == 3
    assert packet["evidence_quality"]["matched_control_avg_net_bps"] == 0.0
    assert packet["evidence_quality"]["probe_minus_control_avg_net_bps"] == 2.3333
    assert packet["evidence_quality"]["probe_outperforms_matched_control"] is True


def test_first_review_pass_under_captures_matched_control_execution_gap() -> None:
    packet = build_bounded_demo_probe_result_review(
        preflight=_preflight(),
        ledger_rows=[
            *_ledger([1.0, 2.0, 3.0]),
            _control(1, 3.0),
            _control(2, 3.0),
            _control(3, 3.0),
        ],
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["status"] == "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED"
    assert packet["answers"]["matched_control_comparison_present"] is True
    assert packet["answers"]["anecdote_risk"] is False
    assert packet["answers"]["execution_realism_gap"] is True
    assert packet["evidence_quality"]["status"] == (
        "PROBE_UNDERPERFORMS_MATCHED_CONTROL_EXECUTION_GAP"
    )
    assert packet["evidence_quality"]["matched_control_outcome_count"] == 3
    assert packet["evidence_quality"]["matched_control_avg_net_bps"] == 3.0
    assert packet["evidence_quality"]["probe_minus_control_avg_net_bps"] == -1.0
    assert packet["evidence_quality"]["probe_edge_capture_ratio"] == 0.6667
    assert packet["evidence_quality"]["probe_execution_gap_bps"] == 1.0
    assert packet["evidence_quality"]["probe_outperforms_matched_control"] is False
    assert packet["evidence_quality"]["execution_realism_gap"] is True
    assert packet["next_actions"][0] == (
        "investigate_probe_execution_realism_slippage_and_timing_before_cost_gate_review"
    )
    assert "Probe execution gap bps" in markdown


def test_failed_first_review_stops_probe() -> None:
    packet = build_bounded_demo_probe_result_review(
        preflight=_preflight(),
        ledger_rows=_ledger([3.0, -2.0, -1.0]),
        now_utc=NOW,
    )

    assert packet["status"] == "STOP_BOUNDED_DEMO_PROBE_REALIZED_EDGE_FAILED"
    assert packet["answers"]["stop_probe_recommended"] is True
    assert packet["answers"]["operator_review_required"] is True
    assert packet["evidence_quality"]["status"] == "REALIZED_EDGE_FAILED"
    assert "stop_probe_and_keep_cost_gate_blocked_for_this_side_cell" in packet[
        "next_actions"
    ]


def test_learning_review_candidate_still_does_not_promote_or_grant_authority() -> None:
    packet = build_bounded_demo_probe_result_review(
        preflight=_preflight(),
        ledger_rows=_ledger([1.0, 2.0, 3.0, 2.5, 1.5, 1.0, 2.2, 3.1, 2.4, 1.8]),
        now_utc=NOW,
    )

    assert packet["status"] == "LEARNING_REVIEW_CANDIDATE_OPERATOR_REVIEW_REQUIRED"
    assert packet["answers"]["learning_review_candidate"] is True
    assert packet["answers"]["operator_review_required"] is True
    assert packet["answers"]["promotion_evidence"] is False
    assert packet["answers"]["main_cost_gate_adjustment"] == "NONE"
    assert packet["evidence_quality"]["status"] == "CONTROL_COMPARISON_MISSING"


def test_authority_violation_fails_closed() -> None:
    packet = build_bounded_demo_probe_result_review(
        preflight=_preflight(probe_authority_granted=True),
        ledger_rows=_ledger([2.0, 2.0, 2.0]),
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["answers"]["authority_boundary_preserved"] is False
    assert packet["answers"]["stop_probe_recommended"] is True


def test_not_ready_design_cannot_be_used_as_result_review() -> None:
    packet = build_bounded_demo_probe_result_review(
        preflight=_preflight_with_design_status("NOT_READY_FOR_OPERATOR_PROBE_REVIEW"),
        ledger_rows=_ledger([2.0, 2.0, 2.0]),
        now_utc=NOW,
    )

    assert packet["status"] == "PREFLIGHT_DESIGN_NOT_USABLE"
    assert packet["reason"] == "bounded_probe_design_not_ready_for_result_review"
    assert packet["answers"]["operator_review_required"] is True
    assert packet["answers"]["continue_probe_without_operator_review_allowed"] is False
