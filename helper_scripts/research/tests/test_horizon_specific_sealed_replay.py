from __future__ import annotations

import datetime as dt
import json

from alpha_discovery_throughput.horizon_specific_sealed_replay import (
    SCHEMA_VERSION,
    build_horizon_specific_sealed_replay_packet,
    render_markdown,
)


def _horizon_packet() -> dict:
    return {
        "schema_version": "horizon_edge_amplification_packet_v1",
        "generated_at_utc": "2026-06-22T03:25:00+00:00",
        "status": "HORIZON_RETIMING_CANDIDATES_PRESENT",
        "candidates": [
            {
                "rank": 1,
                "side_cell_key": "ma_crossover|BTCUSDT|Sell",
                "status": "RETIMING_CANDIDATE",
                "best_horizon_minutes": 240,
                "primary_horizon_minutes": 60,
                "primary_horizon_action": "BLOCK_CONFIRMED",
                "primary_horizon_net_bps": -41.8107,
                "best_net_bps": 31.8707,
                "best_net_positive_pct": 81.94,
                "best_p50_gross_bps": 51.4448,
                "edge_amplification_vs_primary_bps": 73.6814,
                "sample_count_for_gate": 13819,
                "required_next_gate": "sealed_horizon_specific_replay_before_bounded_demo_probe",
                "raw_horizon_rows": [
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
                        "p50_gross_bps": 51.4448,
                        "net_positive_pct": 81.94,
                        "sample_count_for_gate": 13819,
                    },
                ],
            },
            {
                "rank": 2,
                "side_cell_key": "ma_crossover|BTCUSDT|Buy",
                "status": "STABLE_MULTI_HORIZON_CANDIDATE",
                "best_horizon_minutes": 60,
                "sample_count_for_gate": 39637,
            },
        ],
    }


def _counterfactual() -> dict:
    return {
        "generated_at_utc": "2026-06-22T03:16:07+00:00",
        "horizon_minutes": 60,
        "friction_bps": 4.0,
        "learning_lane_scorecard": {
            "schema_version": "cost_gate_reject_counterfactual_v2",
            "thresholds": {
                "min_probe_sample": 100,
                "min_probe_avg_net_bps": 0.0,
                "min_probe_net_positive_pct": 55.0,
                "friction_bps": 4.0,
            },
            "horizon_stability_scorecard": {
                "schema_version": "cost_gate_reject_horizon_stability_v1",
                "top_side_cells": [
                    {
                        "side_cell_key": "ma_crossover|BTCUSDT|Sell",
                        "status": "MIXED_HORIZON_RESPONSE",
                        "candidate_horizons": [240],
                        "block_confirmed_horizons": [15, 60],
                        "best_horizon_minutes": 240,
                        "best_avg_net_bps": 31.8707,
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
                                "p50_gross_bps": 51.4448,
                                "net_positive_pct": 81.94,
                                "sample_count_for_gate": 13819,
                            },
                        ],
                    }
                ],
            },
        },
    }


def test_sealed_replay_passes_only_preselected_retiming_candidate() -> None:
    packet = build_horizon_specific_sealed_replay_packet(
        horizon_packet=_horizon_packet(),
        replay_counterfactual=_counterfactual(),
        now_utc=dt.datetime(2026, 6, 22, 3, 30, tzinfo=dt.timezone.utc),
    )

    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == "SEALED_HORIZON_REPLAY_READY_FOR_OPERATOR_REVIEW"
    assert packet["answers"]["sealed_replay_passed"] is True
    assert packet["answers"]["operator_review_ready"] is True
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["selection"]["selected"]["side_cell_key"] == "ma_crossover|BTCUSDT|Sell"
    assert packet["replay_evaluation"]["best_horizon"]["horizon_minutes"] == 240
    assert packet["replay_evaluation"]["primary_horizon"]["learning_lane_action"] == "BLOCK_CONFIRMED"
    assert packet["replay_evaluation"]["failed_gate_names"] == []


def test_sealed_replay_blocks_stable_candidate_rank() -> None:
    packet = build_horizon_specific_sealed_replay_packet(
        horizon_packet=_horizon_packet(),
        replay_counterfactual=_counterfactual(),
        candidate_rank=2,
        now_utc=dt.datetime(2026, 6, 22, 3, 30, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "SEALED_HORIZON_REPLAY_BLOCKED"
    assert "candidate_is_retiming" in packet["replay_evaluation"]["failed_gate_names"]
    assert packet["answers"]["probe_authority_granted"] is False


def test_sealed_replay_blocks_metric_drift() -> None:
    replay = _counterfactual()
    replay["learning_lane_scorecard"]["horizon_stability_scorecard"]["top_side_cells"][0]["horizon_rows"][2]["avg_net_bps"] = 12.0

    packet = build_horizon_specific_sealed_replay_packet(
        horizon_packet=_horizon_packet(),
        replay_counterfactual=replay,
        now_utc=dt.datetime(2026, 6, 22, 3, 30, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "SEALED_HORIZON_REPLAY_BLOCKED"
    assert "best_net_metric_drift_within_tolerance" in packet["replay_evaluation"]["failed_gate_names"]


def test_sealed_replay_cli_hashes_inputs_and_renders_markdown(tmp_path) -> None:
    horizon_path = tmp_path / "horizon.json"
    replay_path = tmp_path / "replay.json"
    horizon_path.write_text(json.dumps(_horizon_packet()), encoding="utf-8")
    replay_path.write_text(json.dumps(_counterfactual()), encoding="utf-8")

    packet = build_horizon_specific_sealed_replay_packet(
        horizon_packet=json.loads(horizon_path.read_text(encoding="utf-8")),
        replay_counterfactual=json.loads(replay_path.read_text(encoding="utf-8")),
        horizon_packet_path=horizon_path,
        replay_counterfactual_path=replay_path,
        now_utc=dt.datetime(2026, 6, 22, 3, 30, tzinfo=dt.timezone.utc),
    )
    markdown = render_markdown(packet)

    assert packet["source"]["horizon_packet"]["sha256"]
    assert packet["source"]["replay_counterfactual"]["sha256"]
    assert "Horizon Specific Sealed Replay Packet" in markdown
    assert "ma_crossover\\|BTCUSDT\\|Sell" in markdown
