from __future__ import annotations

import datetime as dt

from alpha_discovery_throughput.horizon_edge_amplification import (
    SCHEMA_VERSION,
    build_horizon_edge_amplification_packet,
    render_markdown,
)


def _counterfactual() -> dict:
    return {
        "schema_version": "cost_gate_reject_counterfactual_v2",
        "generated_at_utc": "2026-06-22T03:16:07+00:00",
        "horizon_minutes": 60,
        "friction_bps": 4.0,
        "learning_lane_scorecard": {
            "status": "LEARNING_LANE_PROBE_CANDIDATES_PRESENT",
            "horizon_stability_scorecard": {
                "status": "MULTI_HORIZON_PROFIT_LEARNING_CANDIDATES_PRESENT",
                "top_side_cells": [
                    {
                        "side_cell_key": "ma_crossover|BTCUSDT|Buy",
                        "status": "CANDIDATE_MULTI_HORIZON_STABLE",
                        "candidate_horizons": [15, 60],
                        "block_confirmed_horizons": [240],
                        "observed_horizons": [15, 60, 240],
                        "best_horizon_minutes": 60,
                        "best_avg_net_bps": 11.397,
                        "best_net_positive_pct": 65.08,
                        "best_p50_gross_bps": 22.5553,
                        "best_sample_count_for_gate": 39637,
                        "reason": "side_cell_clears_learning_thresholds_on_multiple_horizons",
                        "horizon_rows": [
                            {
                                "horizon_minutes": 15,
                                "learning_lane_action": "LEARNING_PROBE_CANDIDATE",
                                "avg_net_bps": 0.9833,
                                "sample_count_for_gate": 39637,
                            },
                            {
                                "horizon_minutes": 60,
                                "learning_lane_action": "LEARNING_PROBE_CANDIDATE",
                                "avg_net_bps": 11.397,
                                "sample_count_for_gate": 39637,
                            },
                            {
                                "horizon_minutes": 240,
                                "learning_lane_action": "BLOCK_CONFIRMED",
                                "avg_net_bps": -43.1984,
                                "sample_count_for_gate": 39637,
                            },
                        ],
                    },
                    {
                        "side_cell_key": "ma_crossover|BTCUSDT|Sell",
                        "status": "MIXED_HORIZON_RESPONSE",
                        "candidate_horizons": [240],
                        "block_confirmed_horizons": [15, 60],
                        "observed_horizons": [15, 60, 240],
                        "best_horizon_minutes": 240,
                        "best_avg_net_bps": 31.8707,
                        "best_net_positive_pct": 81.94,
                        "best_p50_gross_bps": 51.4448,
                        "best_sample_count_for_gate": 13819,
                        "reason": "side_cell_candidate_on_one_horizon_but_blocked_on_another",
                        "horizon_rows": [
                            {
                                "horizon_minutes": 15,
                                "learning_lane_action": "BLOCK_CONFIRMED",
                                "avg_net_bps": -9.9222,
                                "sample_count_for_gate": 16515,
                            },
                            {
                                "horizon_minutes": 60,
                                "learning_lane_action": "BLOCK_CONFIRMED",
                                "avg_net_bps": -41.8107,
                                "sample_count_for_gate": 16515,
                            },
                            {
                                "horizon_minutes": 240,
                                "learning_lane_action": "LEARNING_PROBE_CANDIDATE",
                                "avg_net_bps": 31.8707,
                                "sample_count_for_gate": 13819,
                            },
                        ],
                    },
                    {
                        "side_cell_key": "ma_crossover|ETHUSDT|Buy",
                        "status": "BLOCK_CONFIRMED_MULTI_HORIZON",
                        "candidate_horizons": [],
                        "block_confirmed_horizons": [15, 60],
                        "observed_horizons": [15, 60],
                        "best_horizon_minutes": 15,
                        "best_avg_net_bps": -66.8474,
                        "best_sample_count_for_gate": 2583,
                    },
                    {
                        "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                        "status": "MIXED_HORIZON_RESPONSE",
                        "candidate_horizons": [60],
                        "block_confirmed_horizons": [15, 240],
                        "observed_horizons": [15, 60, 240],
                        "best_horizon_minutes": 60,
                        "best_avg_net_bps": 4.0264,
                        "best_net_positive_pct": 100.0,
                        "best_p50_gross_bps": 8.2321,
                        "best_sample_count_for_gate": 2355,
                        "reason": "primary_horizon_candidate_but_other_horizons_blocked",
                        "horizon_rows": [
                            {
                                "horizon_minutes": 15,
                                "learning_lane_action": "BLOCK_CONFIRMED",
                                "avg_net_bps": -12.0,
                                "sample_count_for_gate": 2355,
                            },
                            {
                                "horizon_minutes": 60,
                                "learning_lane_action": "LEARNING_PROBE_CANDIDATE",
                                "avg_net_bps": 4.0264,
                                "sample_count_for_gate": 2355,
                            },
                            {
                                "horizon_minutes": 240,
                                "learning_lane_action": "BLOCK_CONFIRMED",
                                "avg_net_bps": -8.0,
                                "sample_count_for_gate": 2355,
                            },
                        ],
                    },
                ],
            },
        },
    }


def test_horizon_packet_ranks_retiming_candidate_before_stable_candidate() -> None:
    packet = build_horizon_edge_amplification_packet(
        counterfactual=_counterfactual(),
        now_utc=dt.datetime(2026, 6, 22, 3, 20, tzinfo=dt.timezone.utc),
    )

    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == "HORIZON_RETIMING_CANDIDATES_PRESENT"
    assert packet["summary"]["retiming_candidate_count"] == 1
    assert packet["summary"]["horizon_guard_candidate_count"] == 1
    assert packet["answers"]["retiming_can_amplify_edge"] is True
    assert packet["answers"]["global_cost_gate_lowering_recommended"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["global_boundaries"]["probe_authority"] == "NOT_GRANTED"

    top = packet["candidates"][0]
    assert top["side_cell_key"] == "ma_crossover|BTCUSDT|Sell"
    assert top["status"] == "RETIMING_CANDIDATE"
    assert top["best_horizon_minutes"] == 240
    assert top["primary_horizon_minutes"] == 60
    assert top["primary_horizon_action"] == "BLOCK_CONFIRMED"
    assert top["best_net_bps"] == 31.8707
    assert top["edge_amplification_vs_primary_bps"] == 73.6814
    assert top["required_next_gate"] == (
        "sealed_horizon_specific_replay_before_bounded_demo_probe"
    )

    stable = packet["candidates"][1]
    assert stable["side_cell_key"] == "ma_crossover|BTCUSDT|Buy"
    assert stable["status"] == "STABLE_MULTI_HORIZON_CANDIDATE"
    assert stable["edge_amplification_vs_primary_bps"] == 0.0

    guarded = packet["candidates"][2]
    assert guarded["side_cell_key"] == "ma_crossover|ETHUSDT|Sell"
    assert guarded["status"] == "MIXED_HORIZON_GUARD_CANDIDATE"
    assert guarded["primary_horizon_action"] == "LEARNING_PROBE_CANDIDATE"
    assert guarded["required_next_gate"] == (
        "sealed_primary_horizon_replay_with_blocked_horizon_guard"
    )


def test_horizon_packet_markdown_escapes_side_cell_pipes() -> None:
    packet = build_horizon_edge_amplification_packet(
        counterfactual=_counterfactual(),
        now_utc=dt.datetime(2026, 6, 22, 3, 20, tzinfo=dt.timezone.utc),
    )

    markdown = render_markdown(packet)

    assert "Horizon Edge Amplification Packet" in markdown
    assert "ma_crossover\\|BTCUSDT\\|Sell" in markdown
    assert "sealed_horizon_specific_replay_before_bounded_demo_probe" in markdown
