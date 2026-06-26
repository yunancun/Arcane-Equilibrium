from __future__ import annotations

import datetime as dt
from pathlib import Path

from cost_gate_learning_lane.false_negative_evidence_floor_ranking import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
    EVIDENCE_FLOOR_CONTRACT_NOT_READY_STATUS,
    READY_STATUS,
    SCHEMA_VERSION,
    build_false_negative_evidence_floor_ranking,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 26, 7, 45, tzinfo=dt.timezone.utc)


def _scorecard(**overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_false_negative_candidate_friction_scorecard_v1",
        "generated_at_utc": "2026-06-26T07:30:55+00:00",
        "status": "FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_READY",
        "ranked_candidates": [
            {
                "side_cell_key": "grid_trading|ETHUSDT|Buy",
                "candidate": {
                    "strategy_name": "grid_trading",
                    "symbol": "ETHUSDT",
                    "side": "Buy",
                    "outcome_horizon_minutes": 60,
                },
                "friction_rank": 1,
                "outcome_count": 7,
                "net_cost_cushion_bps": 258.3905,
                "net_positive_pct": 100.0,
            },
            {
                "side_cell_key": "grid_trading|AVAXUSDT|Sell",
                "candidate": {
                    "strategy_name": "grid_trading",
                    "symbol": "AVAXUSDT",
                    "side": "Sell",
                    "outcome_horizon_minutes": 60,
                },
                "friction_rank": 2,
                "outcome_count": 48,
                "net_cost_cushion_bps": 73.5511,
                "net_positive_pct": 100.0,
            },
            {
                "side_cell_key": "grid_trading|ETCUSDT|Sell",
                "candidate": {
                    "strategy_name": "grid_trading",
                    "symbol": "ETCUSDT",
                    "side": "Sell",
                    "outcome_horizon_minutes": 60,
                },
                "friction_rank": 3,
                "outcome_count": 40,
                "net_cost_cushion_bps": 31.0992,
                "net_positive_pct": 77.5,
            },
            {
                "side_cell_key": "grid_trading|SUIUSDT|Sell",
                "candidate": {
                    "strategy_name": "grid_trading",
                    "symbol": "SUIUSDT",
                    "side": "Sell",
                    "outcome_horizon_minutes": 60,
                },
                "friction_rank": 4,
                "outcome_count": 25,
                "net_cost_cushion_bps": 17.424,
                "net_positive_pct": 88.0,
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


def _cap_screen(**overrides) -> dict:
    payload = {
        "schema_version": "bounded_probe_candidate_universe_instrument_screen_input_v1",
        "generated_at_utc": "2026-06-25T21:49:49+00:00",
        "rows": [
            {
                "side_cell_key": "grid_trading|ETHUSDT|Buy",
                "strategy_name": "grid_trading",
                "symbol": "ETHUSDT",
                "side": "Buy",
                "fits_current_cap": False,
                "cap_usdt": 10.0,
                "best_bid": 1573.17,
                "best_ask": 1573.18,
                "spread_bps": 0.0636,
                "outcome_count": 7,
                "net_cost_cushion_bps": 258.3905,
                "net_positive_pct": 100.0,
            },
            {
                "side_cell_key": "grid_trading|AVAXUSDT|Sell",
                "strategy_name": "grid_trading",
                "symbol": "AVAXUSDT",
                "side": "Sell",
                "fits_current_cap": True,
                "cap_usdt": 10.0,
                "best_bid": 6.208,
                "best_ask": 6.209,
                "spread_bps": 1.6108,
                "outcome_count": 48,
                "net_cost_cushion_bps": 73.5511,
                "net_positive_pct": 100.0,
            },
            {
                "side_cell_key": "grid_trading|ETCUSDT|Sell",
                "strategy_name": "grid_trading",
                "symbol": "ETCUSDT",
                "side": "Sell",
                "fits_current_cap": True,
                "cap_usdt": 10.0,
                "best_bid": 7.084,
                "best_ask": 0.0,
                "spread_bps": 0.0,
                "outcome_count": 40,
                "net_cost_cushion_bps": 31.0992,
                "net_positive_pct": 77.5,
            },
            {
                "side_cell_key": "grid_trading|SUIUSDT|Sell",
                "strategy_name": "grid_trading",
                "symbol": "SUIUSDT",
                "side": "Sell",
                "fits_current_cap": True,
                "cap_usdt": 10.0,
                "best_bid": 0.6791,
                "best_ask": 0.6792,
                "spread_bps": 1.4725,
                "outcome_count": 25,
                "net_cost_cushion_bps": 17.424,
                "net_positive_pct": 88.0,
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


def _proposal(**overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_autonomous_parameter_proposal_v1",
        "generated_at_utc": "2026-06-26T07:29:20+00:00",
        "status": "REVIEWABLE_PARAMETER_PROPOSAL_READY",
        "selected_side_cell_key": "grid_trading|AVAXUSDT|Sell",
        "proposal": {
            "cap_envelope_evidence_floor": {
                "schema_version": "cost_gate_cap_envelope_evidence_floor_v1",
                "required_before_cap_envelope_review": [
                    "candidate_matched_controls_present",
                    "candidate_matched_fee_slippage_and_maker_taker_labels",
                ],
            }
        },
        "answers": {
            "cap_envelope_mutation_allowed": False,
            "global_cost_gate_lowering_recommended": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
    }
    payload.update(overrides)
    return payload


def test_ranking_keeps_avax_as_review_only_leader_without_authority() -> None:
    packet = build_false_negative_evidence_floor_ranking(
        false_negative_candidate_friction_scorecard=_scorecard(),
        cap_feasible_screen=_cap_screen(),
        autonomous_parameter_proposal=_proposal(),
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["ranked_candidates"][0]["side_cell_key"] == "grid_trading|AVAXUSDT|Sell"
    assert packet["ranked_candidates"][0]["classification"] == "REVIEW_ONLY_LEADER_NOT_PROOF"
    assert packet["ranked_candidates"][0]["review_only_prefilter_pass"] is True
    assert packet["ranked_candidates"][0]["floor_satisfied"] is False
    assert packet["summary"]["floor_satisfied_count"] == 0
    assert packet["answers"]["global_cost_gate_lowering_recommended"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert "False-Negative Evidence-Floor Ranking" in markdown


def test_ranking_classifies_bbo_and_sample_failures() -> None:
    packet = build_false_negative_evidence_floor_ranking(
        false_negative_candidate_friction_scorecard=_scorecard(),
        cap_feasible_screen=_cap_screen(),
        autonomous_parameter_proposal=_proposal(),
        now_utc=NOW,
    )

    etc = next(row for row in packet["ranked_candidates"] if row["side_cell_key"].endswith("ETCUSDT|Sell"))
    sui = next(row for row in packet["ranked_candidates"] if row["side_cell_key"].endswith("SUIUSDT|Sell"))
    eth = next(row for row in packet["ranked_candidates"] if row["side_cell_key"].endswith("ETHUSDT|Buy"))
    assert etc["classification"] == "REJECT_BBO_OR_SPREAD_NOT_CLEAN"
    assert "complete_bbo" in etc["failed_checks"]
    assert sui["classification"] == "RESEARCH_CONTROL_SAMPLE_BELOW_FLOOR"
    assert "sample_count_floor" in sui["failed_checks"]
    assert eth["classification"] == "RESEARCH_ONLY_CAP_INFEASIBLE"
    assert "current_cap_feasible" in eth["failed_checks"]


def test_missing_evidence_floor_contract_fails_closed() -> None:
    proposal = _proposal(proposal={})
    packet = build_false_negative_evidence_floor_ranking(
        false_negative_candidate_friction_scorecard=_scorecard(),
        cap_feasible_screen=_cap_screen(),
        autonomous_parameter_proposal=proposal,
        now_utc=NOW,
    )

    assert packet["status"] == EVIDENCE_FLOOR_CONTRACT_NOT_READY_STATUS
    assert packet["ranked_candidates"] == []
    assert packet["answers"]["order_authority_granted"] is False


def test_authority_bearing_input_fails_closed() -> None:
    scorecard = _scorecard()
    scorecard["answers"]["order_authority_granted"] = True
    packet = build_false_negative_evidence_floor_ranking(
        false_negative_candidate_friction_scorecard=scorecard,
        cap_feasible_screen=_cap_screen(),
        autonomous_parameter_proposal=_proposal(),
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["ranked_candidates"] == []
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_static_no_network_db_or_order_imports() -> None:
    source = Path(
        "helper_scripts/research/cost_gate_learning_lane/"
        "false_negative_evidence_floor_ranking.py"
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
