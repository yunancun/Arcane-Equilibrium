from __future__ import annotations

import datetime as dt
from pathlib import Path

from cost_gate_learning_lane.false_negative_candidate_friction_scorecard import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
    INPUT_NOT_READY_STATUS,
    READY_STATUS,
    SCHEMA_VERSION,
    build_false_negative_candidate_friction_scorecard,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 24, 7, 15, tzinfo=dt.timezone.utc)
SIDE_CELL = "grid_trading|AVAXUSDT|Sell"


def _candidate_packet(**overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_false_negative_candidate_packet_v1",
        "generated_at_utc": "2026-06-24T07:00:00+00:00",
        "status": "COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW",
        "ranked_false_negative_candidates": [
            {
                "side_cell_key": SIDE_CELL,
                "false_negative_rank": 1,
                "strategy_names": ["grid_trading"],
                "symbols": ["AVAXUSDT"],
                "sides": ["Sell"],
                "dominant_horizon_minutes": 60,
                "horizon_minutes": [60],
                "status": "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE",
                "outcome_count": 48,
                "avg_net_bps": 73.5511,
                "net_cost_cushion_bps": 73.5511,
                "net_positive_pct": 100.0,
                "wrongful_block_score": 147.1021,
                "global_cost_gate_lowering_recommended": False,
                "probe_authority_granted": False,
                "order_authority_granted": False,
                "promotion_evidence": False,
            },
            {
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "false_negative_rank": 2,
                "strategy_names": ["ma_crossover"],
                "symbols": ["ETHUSDT"],
                "sides": ["Sell"],
                "dominant_horizon_minutes": 60,
                "horizon_minutes": [60],
                "status": "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE",
                "outcome_count": 4774,
                "avg_net_bps": 37.7464,
                "net_cost_cushion_bps": 37.7464,
                "net_positive_pct": 100.0,
                "wrongful_block_score": 75.4927,
                "global_cost_gate_lowering_recommended": False,
                "probe_authority_granted": False,
                "order_authority_granted": False,
                "promotion_evidence": False,
            },
        ],
        "answers": {
            "global_cost_gate_lowering_recommended": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
    }
    payload.update(overrides)
    return payload


def _touchability(**overrides) -> dict:
    payload = {
        "schema_version": "bounded_demo_probe_touchability_preflight_v1",
        "generated_at_utc": "2026-06-24T07:01:00+00:00",
        "status": "TOUCHABILITY_REPAIR_REQUIRED_BEFORE_BOUNDED_DEMO_PROBE",
        "candidate": {
            "side_cell_key": SIDE_CELL,
            "strategy_name": "grid_trading",
            "symbol": "AVAXUSDT",
            "side": "Sell",
            "outcome_horizon_minutes": 60,
        },
        "answers": {
            "candidate_matched_fill_flow_present": False,
            "touchability_repair_required": True,
            "global_cost_gate_lowering_recommended": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "order_touchability": {
            "candidate_reviewed_orders": 0,
            "candidate_fill_rows": 0,
            "non_candidate_fill_rows": 4,
            "bbo_touched_without_fill": True,
        },
    }
    payload.update(overrides)
    return payload


def _placement(**overrides) -> dict:
    payload = {
        "schema_version": "bounded_demo_probe_placement_repair_plan_v1",
        "generated_at_utc": "2026-06-24T07:02:00+00:00",
        "status": "PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW",
        "candidate": {
            "side_cell_key": SIDE_CELL,
            "strategy_name": "grid_trading",
            "symbol": "AVAXUSDT",
            "side": "Sell",
            "outcome_horizon_minutes": 60,
        },
        "placement_repair_plan": {
            "active": False,
            "requires_separate_operator_authorization": True,
            "order_mode": "post_only_near_touch_or_skip",
            "candidate": {
                "side_cell_key": SIDE_CELL,
                "strategy_name": "grid_trading",
                "symbol": "AVAXUSDT",
                "side": "Sell",
                "outcome_horizon_minutes": 60,
            },
            "authority_boundary": {
                "global_cost_gate_lowering_recommended": False,
                "probe_authority_granted": False,
                "order_authority_granted": False,
                "promotion_evidence": False,
            },
        },
        "answers": {
            "global_cost_gate_lowering_recommended": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
    }
    payload.update(overrides)
    return payload


def _authorization(**overrides) -> dict:
    payload = {
        "schema_version": "bounded_demo_probe_operator_authorization_packet_v1",
        "generated_at_utc": "2026-06-24T07:03:00+00:00",
        "status": "TYPED_CONFIRM_REQUIRED",
        "decision": "authorize",
        "candidate": {
            "side_cell_key": SIDE_CELL,
            "strategy_name": "grid_trading",
            "symbol": "AVAXUSDT",
            "side": "Sell",
            "outcome_horizon_minutes": 60,
        },
        "answers": {
            "operator_authorization_object_emitted": False,
            "bounded_demo_probe_authorized": False,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted_in_authorization_object": False,
            "order_authority_granted_in_authorization_object": False,
            "promotion_evidence": False,
        },
    }
    payload.update(overrides)
    return payload


def test_scorecard_ranks_candidates_and_preserves_no_authority() -> None:
    packet = build_false_negative_candidate_friction_scorecard(
        false_negative_candidate_packet=_candidate_packet(),
        touchability_preflight=_touchability(),
        placement_repair_plan=_placement(),
        operator_authorization=_authorization(),
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["ranked_candidates"][0]["side_cell_key"] == SIDE_CELL
    assert packet["ranked_candidates"][0]["friction"]["authorization_status"] == (
        "TYPED_CONFIRM_REQUIRED"
    )
    assert packet["ranked_candidates"][0]["next_action"] == (
        "exact_bounded_demo_typed_confirm_required_or_select_next_candidate"
    )
    assert packet["answers"]["operator_authorization_object_emitted"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["promotion_evidence"] is False
    assert "False-Negative Candidate Friction Scorecard" in markdown


def test_mismatched_touchability_is_unmeasured_not_low_friction() -> None:
    eth_candidate = {
        "side_cell_key": "ma_crossover|ETHUSDT|Sell",
        "strategy_name": "ma_crossover",
        "symbol": "ETHUSDT",
        "side": "Sell",
        "outcome_horizon_minutes": 60,
    }
    touchability = _touchability(
        candidate={
            **eth_candidate,
        }
    )
    packet = build_false_negative_candidate_friction_scorecard(
        false_negative_candidate_packet=_candidate_packet(),
        touchability_preflight=touchability,
        placement_repair_plan=_placement(
            candidate={**eth_candidate},
            placement_repair_plan={
                "active": False,
                "requires_separate_operator_authorization": True,
                "order_mode": "post_only_near_touch_or_skip",
                "candidate": {**eth_candidate},
                "authority_boundary": {
                    "global_cost_gate_lowering_recommended": False,
                    "probe_authority_granted": False,
                    "order_authority_granted": False,
                    "promotion_evidence": False,
                },
            },
        ),
        operator_authorization=_authorization(candidate={**eth_candidate}),
        now_utc=NOW,
    )

    assert packet["status"] == READY_STATUS
    avax = next(row for row in packet["ranked_candidates"] if row["side_cell_key"] == SIDE_CELL)
    assert avax["friction"]["touchability_evidence_scope"] == "UNMEASURED_CANDIDATE"
    assert avax["friction"]["touchability_penalty"] == 25.0


def test_authority_bearing_input_fails_closed() -> None:
    auth = _authorization()
    auth["answers"]["operator_authorization_object_emitted"] = True
    packet = build_false_negative_candidate_friction_scorecard(
        false_negative_candidate_packet=_candidate_packet(),
        touchability_preflight=_touchability(),
        placement_repair_plan=_placement(),
        operator_authorization=auth,
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["ranked_candidates"] == []
    assert packet["answers"]["scorecard_ready"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_bybit_mutation_signal_fails_closed() -> None:
    auth = _authorization()
    auth["answers"]["bybit_call_performed"] = True
    packet = build_false_negative_candidate_friction_scorecard(
        false_negative_candidate_packet=_candidate_packet(),
        touchability_preflight=_touchability(),
        placement_repair_plan=_placement(),
        operator_authorization=auth,
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["ranked_candidates"] == []
    assert packet["answers"]["scorecard_ready"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_missing_friction_artifact_fails_closed() -> None:
    packet = build_false_negative_candidate_friction_scorecard(
        false_negative_candidate_packet=_candidate_packet(),
        touchability_preflight=_touchability(),
        placement_repair_plan=_placement(),
        operator_authorization=None,
        now_utc=NOW,
    )

    assert packet["status"] == INPUT_NOT_READY_STATUS
    assert packet["reason"] == "friction_artifacts_missing_stale_unknown_age_or_schema_mismatch"
    assert packet["ranked_candidates"] == []
    assert packet["answers"]["probe_authority_granted"] is False


def test_schema_mismatch_fails_closed() -> None:
    touchability = _touchability(schema_version="wrong_schema")
    packet = build_false_negative_candidate_friction_scorecard(
        false_negative_candidate_packet=_candidate_packet(),
        touchability_preflight=touchability,
        placement_repair_plan=_placement(),
        operator_authorization=_authorization(),
        now_utc=NOW,
    )

    assert packet["status"] == INPUT_NOT_READY_STATUS
    assert packet["reason"] == "friction_artifacts_missing_stale_unknown_age_or_schema_mismatch"
    assert packet["ranked_candidates"] == []


def test_friction_candidate_identity_mismatch_fails_closed() -> None:
    eth_candidate = {
        "side_cell_key": "ma_crossover|ETHUSDT|Sell",
        "strategy_name": "ma_crossover",
        "symbol": "ETHUSDT",
        "side": "Sell",
        "outcome_horizon_minutes": 60,
    }
    packet = build_false_negative_candidate_friction_scorecard(
        false_negative_candidate_packet=_candidate_packet(),
        touchability_preflight=_touchability(candidate={**eth_candidate}),
        placement_repair_plan=_placement(),
        operator_authorization=_authorization(),
        now_utc=NOW,
    )

    assert packet["status"] == INPUT_NOT_READY_STATUS
    assert packet["reason"] == "friction_artifact_candidate_identity_mismatch_or_not_in_packet"
    assert packet["ranked_candidates"] == []


def test_nested_placement_candidate_mismatch_fails_closed() -> None:
    eth_candidate = {
        "side_cell_key": "ma_crossover|ETHUSDT|Sell",
        "strategy_name": "ma_crossover",
        "symbol": "ETHUSDT",
        "side": "Sell",
        "outcome_horizon_minutes": 60,
    }
    placement = _placement()
    placement["placement_repair_plan"]["candidate"] = {**eth_candidate}

    packet = build_false_negative_candidate_friction_scorecard(
        false_negative_candidate_packet=_candidate_packet(),
        touchability_preflight=_touchability(),
        placement_repair_plan=placement,
        operator_authorization=_authorization(),
        now_utc=NOW,
    )

    assert packet["status"] == INPUT_NOT_READY_STATUS
    assert packet["reason"] == "friction_artifact_candidate_identity_mismatch_or_not_in_packet"
    assert packet["ranked_candidates"] == []


def test_static_no_network_db_or_order_imports() -> None:
    source = Path(
        "helper_scripts/research/cost_gate_learning_lane/"
        "false_negative_candidate_friction_scorecard.py"
    ).read_text(encoding="utf-8")

    forbidden = [
        "psycopg",
        "requests",
        "urllib",
        "ccxt",
        "pybit",
        "subprocess",
        "create_order",
        "cancel_order",
        "place_order",
    ]
    for needle in forbidden:
        assert needle not in source
