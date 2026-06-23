"""Focused tests for MM motif amplification packets."""

from __future__ import annotations

import datetime as dt

from alpha_discovery_throughput.mm_motif_amplification import (
    build_mm_motif_amplification_packet,
    render_markdown,
)


def test_mm_motif_amplification_ranks_repeated_near_miss_motif():
    packet = build_mm_motif_amplification_packet(
        fillsim_history={
            "status": "HISTORY_LOWER_FEE_ONLY",
            "valid_windows": 10,
            "distinct_window_dates": ["2026-06-20", "2026-06-23"],
            "low_friction_near_miss_motif_stability": {
                "status": "LOW_FRICTION_NEAR_MISS_MOTIF_REPEATS_BUT_DATE_INSUFFICIENT",
                "reason": "repeated_motif_but_distinct_dates_below_min",
                "min_distinct_dates": 3,
                "top_repeated_near_miss_motifs": [{
                    "motif_key": "low_friction_motif|spread_combo|recent_trade_imbalance",
                    "windows": 2,
                    "distinct_window_dates": ["2026-06-20"],
                    "candidate_keys": ["candidate-a"],
                    "best_cell": {
                        "condition": (
                            "quoted_half_spread_bps train_p90 AND "
                            "side_recent_trade_imbalance_30s train_p90"
                        ),
                        "train_edge_before_fees_bps": 1.032,
                        "holdout_edge_before_fees_bps": 2.81,
                        "holdout_net_bps": -1.19,
                        "gap_to_current_fee_round_trip_bps": 1.19,
                        "threshold_source": "train_only",
                    },
                }],
            },
        },
        now_utc=dt.datetime(2026, 6, 23, 17, tzinfo=dt.timezone.utc),
    )

    assert packet["schema_version"] == "mm_motif_amplification_packet_v1"
    assert packet["status"] == "MM_MOTIF_AMPLIFICATION_REQUIRES_DISTINCT_DATE_HISTORY"
    assert packet["answers"]["global_cost_gate_lowering_recommended"] is False
    assert packet["answers"]["order_authority_granted"] is False
    top = packet["top_candidate"]
    assert top["motif_key"] == "low_friction_motif|spread_combo|recent_trade_imbalance"
    assert top["status"] == "MOTIF_REPEATS_DISTINCT_DATES_INSUFFICIENT"
    assert top["bottleneck_leg"] == "train"
    assert top["min_train_holdout_gross_bps"] == 1.032
    assert top["current_fee_round_trip_bps"] == 4.0
    assert top["min_gross_gap_to_current_fee_bps"] == 2.968
    assert top["required_uplift_multiple"] == 3.876
    assert top["distinct_dates_remaining"] == 2
    assert top["search_constraint"] == (
        "preserve_repeated_motif_axes_and_require_train_holdout_sample_gated_"
        "min_gross_ge_current_fee_round_trip"
    )

    markdown = render_markdown(packet)
    assert "MM Motif Amplification Packet" in markdown
    assert "low_friction_motif" in markdown


def test_mm_motif_amplification_handles_missing_repeated_motifs():
    packet = build_mm_motif_amplification_packet(
        fillsim_history={"status": "HISTORY_INSUFFICIENT_WINDOWS"},
        now_utc=dt.datetime(2026, 6, 23, 17, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "NO_REPEATED_LOW_FRICTION_MOTIF_FOR_AMPLIFICATION"
    assert packet["summary"]["candidate_count"] == 0
    assert packet["answers"]["motif_amplification_candidate_present"] is False
