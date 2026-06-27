from __future__ import annotations

import datetime as dt
from pathlib import Path

from cost_gate_learning_lane.false_negative_evidence_floor_gap_closure import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
    INPUT_NOT_READY_STATUS,
    READY_STATUS,
    SCHEMA_VERSION,
    build_false_negative_evidence_floor_gap_closure_design,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 26, 8, 0, tzinfo=dt.timezone.utc)


def _ranking(**overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_false_negative_evidence_floor_ranking_v1",
        "generated_at_utc": "2026-06-26T07:54:33+00:00",
        "status": "FALSE_NEGATIVE_EVIDENCE_FLOOR_RANKING_READY_NO_AUTHORITY",
        "summary": {
            "floor_satisfied_count": 0,
            "review_only_leader_side_cell_key": "grid_trading|AVAXUSDT|Sell",
        },
        "ranked_candidates": [
            {
                "side_cell_key": "grid_trading|AVAXUSDT|Sell",
                "classification": "REVIEW_ONLY_LEADER_NOT_PROOF",
                "candidate": {
                    "side_cell_key": "grid_trading|AVAXUSDT|Sell",
                    "strategy_name": "grid_trading",
                    "symbol": "AVAXUSDT",
                    "side": "Sell",
                    "outcome_horizon_minutes": 60,
                },
                "evidence_floor_gaps": {
                    "candidate_side_cell_matches_learning_packet": True,
                    "candidate_matched_controls_present": False,
                    "candidate_matched_fee_slippage_and_maker_taker_labels": False,
                    "fresh_bbo_and_instrument_metadata_for_tick_qty_min_notional": False,
                    "cap_staircase_with_discrete_exposure_tiers": False,
                    "portfolio_exposure_and_survival_risk_budget_math": False,
                    "empirical_execution_realism_or_explicit_research_only_status": False,
                    "proof_exclusion_scan_for_all_fill_backed_rows": False,
                    "regime_breadth_freshness_survivorship_labels": False,
                    "repeat_or_oos_path_before_any_promotion_claim": False,
                    "floor_satisfied": False,
                },
                "global_cost_gate_lowering_recommended": False,
                "main_cost_gate_adjustment": "NONE",
                "probe_authority_granted": False,
                "order_authority_granted": False,
                "promotion_evidence": False,
            }
        ],
        "answers": {
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "cap_envelope_mutation_allowed": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
    }
    payload.update(overrides)
    return payload


def test_gap_closure_design_maps_avax_gaps_without_authority() -> None:
    packet = build_false_negative_evidence_floor_gap_closure_design(
        evidence_floor_ranking=_ranking(),
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["candidate"]["side_cell_key"] == "grid_trading|AVAXUSDT|Sell"
    assert packet["summary"]["gap_count"] == 9
    assert packet["summary"]["floor_satisfied_after_this_design"] is False
    assert packet["summary"]["p0_authorization_required_before_probe"] is True
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    lanes = packet["lane_summary"]
    assert lanes["source_only_then_post_authorized_review"] == 2
    assert lanes["read_only_runtime_evidence"] == 1
    assert lanes["source_only_or_read_only_runtime_evidence"] == 1
    assert lanes["source_only_risk_design"] == 1
    assert lanes["source_only_data_design"] == 1
    assert lanes["source_only_validation_design"] == 1
    assert lanes["authorization_required_after_probe"] == 2
    cap_item = next(
        item
        for item in packet["gap_closure_items"]
        if item["gap_key"] == "cap_staircase_with_discrete_exposure_tiers"
    )
    assert "current reviewed GUI-resolved cap" in cap_item["authority_required"]
    assert "10 USDT cap" not in cap_item["authority_required"]
    assert "Evidence-Floor Gap-Closure Design" in markdown


def test_selected_side_cell_can_pick_specific_review_leader() -> None:
    ranking = _ranking()
    ranking["ranked_candidates"].insert(
        0,
        {
            "side_cell_key": "grid_trading|SUIUSDT|Sell",
            "classification": "RESEARCH_CONTROL_SAMPLE_BELOW_FLOOR",
            "candidate": {"side_cell_key": "grid_trading|SUIUSDT|Sell"},
            "evidence_floor_gaps": {},
        },
    )

    packet = build_false_negative_evidence_floor_gap_closure_design(
        evidence_floor_ranking=ranking,
        selected_side_cell_key="grid_trading|AVAXUSDT|Sell",
        now_utc=NOW,
    )

    assert packet["status"] == READY_STATUS
    assert packet["candidate"]["side_cell_key"] == "grid_trading|AVAXUSDT|Sell"


def test_authority_bearing_ranking_fails_closed() -> None:
    ranking = _ranking()
    ranking["answers"]["order_authority_granted"] = True
    packet = build_false_negative_evidence_floor_gap_closure_design(
        evidence_floor_ranking=ranking,
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["gap_closure_items"] == []
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_not_ready_ranking_fails_closed() -> None:
    packet = build_false_negative_evidence_floor_gap_closure_design(
        evidence_floor_ranking=_ranking(status="INPUT_NOT_READY"),
        now_utc=NOW,
    )

    assert packet["status"] == INPUT_NOT_READY_STATUS
    assert packet["gap_closure_items"] == []
    assert packet["answers"]["promotion_evidence"] is False


def test_static_no_network_db_or_order_imports() -> None:
    source = Path(
        "helper_scripts/research/cost_gate_learning_lane/"
        "false_negative_evidence_floor_gap_closure.py"
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
