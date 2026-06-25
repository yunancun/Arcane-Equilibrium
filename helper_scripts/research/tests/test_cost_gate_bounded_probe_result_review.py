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
ACTIVE_HASH_MOD = 101_559_956_668_416
ACTIVE_HASH_LEN = 9


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


def _outcome(
    i: int,
    net_bps: float,
    gross_bps: float | None = None,
    **overrides,
) -> dict:
    row = {
        "record_type": PROBE_OUTCOME_RECORD_TYPE,
        "generated_at_utc": f"2026-06-22T12:{i:02d}:00+00:00",
        "attempt_id": f"attempt-{i}",
        "side_cell_key": SIDE_CELL,
        "realized_net_bps": net_bps,
        "gross_bps": gross_bps if gross_bps is not None else net_bps + 4.0,
    }
    row.update(overrides)
    return row


def _fill_backed_outcome(i: int, net_bps: float) -> dict:
    return _outcome(
        i,
        net_bps,
        strategy_name="ma_crossover",
        outcome_source="candidate_matched_demo_fill",
        order_link_id=f"oc_dm_attempt_{i}",
        order_id=f"bybit-order-{i}",
        exec_id=f"exec-{i}",
        intent_id=f"intent-{i}",
        risk_verdict="APPROVED_BY_BOUNDED_DEMO_PROBE",
        fee_bps=2.0,
        slippage_bps=0.25,
        close_state="CLOSED_AT_HORIZON",
        source_artifact_path=f"artifacts/probe/fill-{i}.json",
    )


def _to_base36(value: int) -> str:
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    if value == 0:
        return "0"
    out = ""
    while value > 0:
        value, idx = divmod(value, 36)
        out = digits[idx] + out
    return out


def _candidate_hash(side_cell_key: str, context_id: str, signal_id: str) -> str:
    hash_value = 0xCBF2_9CE4_8422_2325
    payload = (
        side_cell_key.encode()
        + bytes([0x1E])
        + context_id.encode()
        + bytes([0x1F])
        + signal_id.encode()
    )
    for byte in payload:
        hash_value ^= byte
        hash_value = (hash_value * 0x0000_0100_0000_01B3) & 0xFFFF_FFFF_FFFF_FFFF
    return _to_base36(hash_value % ACTIVE_HASH_MOD).rjust(ACTIVE_HASH_LEN, "0")


def _active_order_link_id(
    *,
    signal_ts_ms: int,
    seq: int,
    side_cell_key: str,
    context_id: str,
    signal_id: str,
) -> str:
    return (
        f"oc_dm_{signal_ts_ms}_{_to_base36(seq)}_"
        f"{_candidate_hash(side_cell_key, context_id, signal_id)}"
    )


def _active_fill_backed_outcome(i: int, net_bps: float, *, proof_key: bool) -> dict:
    signal_ts_ms = 1_700_000_000_000 + i
    context_id = f"ctx-demo-ma_crossover-BTCUSDT-170000000000{i}"
    signal_id = f"sig-demo-ma_crossover-BTCUSDT-170000000000{i}"
    order_link_id = _active_order_link_id(
        signal_ts_ms=signal_ts_ms,
        seq=i,
        side_cell_key=SIDE_CELL,
        context_id=context_id,
        signal_id=signal_id,
    )
    row = _fill_backed_outcome(i, net_bps)
    row.update(
        reference_source="bounded_probe_active_near_touch",
        order_link_id=order_link_id,
    )
    if proof_key:
        row["active_bounded_probe_proof_key"] = {
            "side_cell_key": SIDE_CELL,
            "engine_mode": "demo",
            "signal_ts_ms": signal_ts_ms,
            "context_id": context_id,
            "signal_id": signal_id,
            "order_link_id": order_link_id,
            "decision_lease_id": f"lease-demo-{i}",
            "reference_source": "bounded_probe_active_near_touch",
        }
    return row


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


def test_unattributed_positive_probe_outcomes_are_proof_excluded() -> None:
    packet = build_bounded_demo_probe_result_review(
        preflight=_preflight(),
        ledger_rows=[
            _outcome(
                1,
                12.0,
                strategy_name="unattributed:bybit_auto",
                outcome_source="demo_fill_execution",
                order_id="bybit-unmatched-1",
                exec_id="exec-unmatched-1",
            ),
            _outcome(
                2,
                11.0,
                strategy_name="unattributed:bybit_auto",
                outcome_source="demo_fill_execution",
                order_id="bybit-unmatched-2",
                exec_id="exec-unmatched-2",
            ),
            _outcome(
                3,
                10.0,
                strategy_name="unattributed:bybit_auto",
                outcome_source="demo_fill_execution",
                order_id="bybit-unmatched-3",
                exec_id="exec-unmatched-3",
            ),
        ],
        now_utc=NOW,
    )

    assert packet["status"] == "PROBE_OUTCOMES_PROOF_EXCLUDED"
    assert packet["reason"] == "completed_probe_outcomes_failed_attribution_or_lineage_proof"
    assert packet["probe_result_summary"]["raw_completed_probe_outcome_count"] == 3
    assert packet["probe_result_summary"]["completed_probe_outcome_count"] == 0
    assert packet["probe_result_summary"]["proof_excluded_probe_outcome_count"] == 3
    assert packet["proof_exclusion"]["reason_counts"]["unattributed_strategy_name"] == 3
    assert packet["answers"]["operator_review_required"] is True
    assert packet["answers"]["stop_probe_recommended"] is True
    assert packet["answers"]["promotion_evidence"] is False


def test_lineage_complete_fill_backed_probe_outcomes_remain_countable() -> None:
    packet = build_bounded_demo_probe_result_review(
        preflight=_preflight(),
        ledger_rows=[
            _fill_backed_outcome(1, 2.0),
            _fill_backed_outcome(2, 4.0),
            _fill_backed_outcome(3, 1.0),
        ],
        now_utc=NOW,
    )

    assert packet["status"] == "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED"
    assert packet["probe_result_summary"]["raw_completed_probe_outcome_count"] == 3
    assert packet["probe_result_summary"]["completed_probe_outcome_count"] == 3
    assert packet["probe_result_summary"]["proof_excluded_probe_outcome_count"] == 0
    assert packet["answers"]["proof_exclusion_present"] is False
    assert packet["answers"]["promotion_evidence"] is False


def test_active_fill_backed_probe_outcomes_require_active_proof_key() -> None:
    packet = build_bounded_demo_probe_result_review(
        preflight=_preflight(),
        ledger_rows=[
            _active_fill_backed_outcome(1, 2.0, proof_key=False),
            _active_fill_backed_outcome(2, 4.0, proof_key=False),
            _active_fill_backed_outcome(3, 1.0, proof_key=False),
        ],
        now_utc=NOW,
    )

    assert packet["status"] == "PROBE_OUTCOMES_PROOF_EXCLUDED"
    assert packet["probe_result_summary"]["raw_completed_probe_outcome_count"] == 3
    assert packet["probe_result_summary"]["completed_probe_outcome_count"] == 0
    assert packet["proof_exclusion"]["reason_counts"][
        "active_bounded_probe_proof_key_missing_or_invalid"
    ] == 3


def test_details_active_reference_source_also_requires_active_proof_key() -> None:
    masked = _active_fill_backed_outcome(1, 2.0, proof_key=False)
    masked["reference_source"] = "bounded_probe_near_touch"
    masked["details"] = {"reference_source": "bounded_probe_active_near_touch"}
    packet = build_bounded_demo_probe_result_review(
        preflight=_preflight(),
        ledger_rows=[masked],
        now_utc=NOW,
    )

    assert packet["status"] == "PROBE_OUTCOMES_PROOF_EXCLUDED"
    assert packet["proof_exclusion"]["reason_counts"][
        "active_bounded_probe_proof_key_missing_or_invalid"
    ] == 1


def test_malformed_active_proof_key_is_proof_excluded() -> None:
    rows = [_active_fill_backed_outcome(i, 2.0, proof_key=True) for i in range(1, 4)]
    for row in rows:
        row["active_bounded_probe_proof_key"]["engine_mode"] = "live"
        row["active_bounded_probe_proof_key"]["signal_ts_ms"] = 0

    packet = build_bounded_demo_probe_result_review(
        preflight=_preflight(),
        ledger_rows=rows,
        now_utc=NOW,
    )

    assert packet["status"] == "PROBE_OUTCOMES_PROOF_EXCLUDED"
    assert packet["probe_result_summary"]["completed_probe_outcome_count"] == 0
    assert packet["proof_exclusion"]["reason_counts"][
        "active_bounded_probe_proof_key_missing_or_invalid"
    ] == 3


def test_active_fill_backed_probe_outcomes_with_active_proof_key_remain_countable() -> None:
    packet = build_bounded_demo_probe_result_review(
        preflight=_preflight(),
        ledger_rows=[
            _active_fill_backed_outcome(1, 2.0, proof_key=True),
            _active_fill_backed_outcome(2, 4.0, proof_key=True),
            _active_fill_backed_outcome(3, 1.0, proof_key=True),
        ],
        now_utc=NOW,
    )

    assert packet["status"] == "FIRST_REVIEW_PASSED_OPERATOR_REVIEW_REQUIRED"
    assert packet["probe_result_summary"]["raw_completed_probe_outcome_count"] == 3
    assert packet["probe_result_summary"]["completed_probe_outcome_count"] == 3
    assert packet["probe_result_summary"]["proof_excluded_probe_outcome_count"] == 0
    assert packet["answers"]["proof_exclusion_present"] is False


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
