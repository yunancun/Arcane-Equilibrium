from __future__ import annotations

import datetime as dt

from alpha_discovery_throughput.profitability_path_scorecard import (
    PROFITABILITY_PATH_SCORECARD_SCHEMA_VERSION,
    build_profitability_path_scorecard,
    render_markdown,
)


def _cost_gate_counterfactual() -> dict:
    return {
        "generated_at_utc": "2026-06-22T03:00:00+00:00",
        "friction_bps": 4.0,
        "learning_lane_scorecard": {
            "status": "LEARNING_LANE_PROBE_CANDIDATES_PRESENT",
            "profit_opportunity_ranking": {
                "status": "PROFIT_LEARNING_CANDIDATES_PRESENT",
                "candidate_count": 2,
                "top_side_cells": [
                    {
                        "side_cell_key": "ma_crossover|BTCUSDT|Buy",
                        "symbol": "BTCUSDT",
                        "side": "Buy",
                        "learning_lane_action": "LEARNING_PROBE_CANDIDATE",
                        "learning_lane_reason": "avg_net_positive",
                        "priority_score": 44.6,
                        "priority_tier": "LOW_PRIORITY_BOUNDED_DEMO_LEARNING",
                        "avg_net_bps": 11.397,
                        "p50_gross_bps": 22.5553,
                        "net_positive_pct": 65.08,
                        "sample_count_for_gate": 39637,
                        "distinct_ts": 39637,
                        "n": 39637,
                        "rows_per_distinct_ts": 1.0,
                        "next_action": "operator_review_ranked_side_cell_for_bounded_demo_learning_lane",
                    }
                ],
            },
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
                    },
                ],
            },
        },
    }


def test_cost_gate_candidates_and_horizon_paths_do_not_grant_authority() -> None:
    scorecard = build_profitability_path_scorecard(
        cost_gate_counterfactual=_cost_gate_counterfactual(),
        profit_learning_packet={
            "status": "DATA_FLOW_MONITOR_REQUIRED",
            "next_actions": ["run_demo_data_flow_monitor_for_1h_4h_24h"],
            "answers": {
                "silent_drop_risk": True,
                "global_cost_gate_lowering_recommended": False,
                "order_authority_granted": False,
            },
            "activation": {"status": "NOT_ACCUMULATING"},
        },
        activation_preflight={"status": "NOT_ACCUMULATING"},
        now_utc=dt.datetime(2026, 6, 22, 3, tzinfo=dt.timezone.utc),
    )

    assert scorecard["schema_version"] == PROFITABILITY_PATH_SCORECARD_SCHEMA_VERSION
    assert scorecard["status"] == "PROFITABILITY_PATHS_PRESENT_BUT_EXECUTION_EVIDENCE_MISSING"
    assert scorecard["answers"]["cost_gate_crossing_candidates_present"] is True
    assert scorecard["answers"]["global_cost_gate_lowering_recommended"] is False
    assert scorecard["answers"]["order_authority_granted"] is False
    assert scorecard["global_boundaries"]["order_authority"] == "NOT_GRANTED"

    paths = {row["path_id"]: row for row in scorecard["top_paths"]}
    cost_path = paths["cost_gate_learning_lane:ma_crossover|BTCUSDT|Buy"]
    assert cost_path["status"] == "COST_GATE_CANDIDATE_READY_FOR_DATA_FLOW_PROOF"
    assert cost_path["required_next_gate"] == "run_demo_data_flow_monitor"
    assert cost_path["current_edge_bps"] == 11.397
    assert cost_path["sample_count"] == 39637
    assert cost_path["order_authority"] == "NOT_GRANTED"

    horizon_path = paths["horizon_edge_amplification:ma_crossover|BTCUSDT|Sell"]
    assert horizon_path["class"] == "horizon_retiming_or_side_cell_filter"
    assert horizon_path["status"] == "HORIZON_EDGE_AMPLIFICATION_CANDIDATE"
    assert horizon_path["candidate_horizons_minutes"] == [240]
    assert horizon_path["best_horizon_minutes"] == 240


def test_mm_fee_polymarket_and_gate_b_paths_are_separated() -> None:
    scorecard = build_profitability_path_scorecard(
        fillsim={
            "generated_at": "2026-06-22T03:00:00+00:00",
            "low_friction_signal_scorecard": {
                "status": "LOW_FRICTION_SIGNAL_TRAIN_ONLY_CURRENT_FEE",
                "current_fee_round_trip_bps": 4.0,
                "train_confirmed_gross_scorecard": {
                    "status": "LOW_FRICTION_TRAIN_CONFIRMED_GROSS_BELOW_CURRENT_FEE",
                    "current_fee_round_trip_bps": 4.0,
                    "best_train_confirmed_gross_candidate": {
                        "name": "quoted_half_spread_bps_train_p90",
                        "train_edge_before_fees_bps": 4.416,
                        "holdout_edge_before_fees_bps": 2.269,
                        "min_train_holdout_gross_bps": 2.269,
                        "gap_to_current_fee_round_trip_bps": 1.731,
                        "train_n_fill_only": 69,
                        "holdout_n_fill_only": 74,
                    },
                },
            },
            "maker_fee_sensitivity_scorecard": {
                "status": "LOWER_FEE_SAMPLE_GATED_POSITIVE",
                "current_fee_round_trip_bps": 4.0,
                "best_sample_gated_break_even_cell": {
                    "key": "edge_scorecard|ADAUSDT",
                    "edge_before_fees_bps": 1.632,
                    "n_fill_only": 1521,
                    "break_even_maker_fee_bps_per_side": 0.816,
                },
            },
        },
        fillsim_history={
            "status": "HISTORY_INSUFFICIENT_WINDOWS",
            "reason": "below_min_windows_or_dates",
            "valid_windows": 4,
            "distinct_window_dates": ["2026-06-20", "2026-06-21"],
            "lower_fee_break_even_stability": {
                "status": "LOWER_FEE_BREAK_EVEN_REPEATS_BUT_DATE_INSUFFICIENT",
                "reason": "repeated_key_but_distinct_dates_below_min",
                "current_maker_fee_bps_per_side": 2.0,
                "best_repeated_lower_fee_break_even_key": {
                    "key": "edge_scorecard|ADAUSDT",
                    "windows": 3,
                    "best_cell": {
                        "key": "edge_scorecard|ADAUSDT",
                        "edge_before_fees_bps": 2.048,
                        "n_fill_only": 850,
                        "break_even_maker_fee_bps_per_side": 1.024,
                        "fee_reduction_to_breakeven_bps_per_side": 0.976,
                    },
                },
            },
        },
        polymarket_leadlag={
            "schema_version": "polymarket.leadlag_report.v0.15",
            "verdict": {"status": "IC_CANDIDATE_REVIEW_REQUIRED", "candidate_count": 3},
            "candidate_replay_scorecard": {
                "status": "PAPER_REPLAY_BUILT",
                "round_trip_cost_bps": 4.0,
                "selected_candidate_key": "polymarket_leadlag_ic|event_reg|BTCUSDT|15m",
                "candidate_count": 3,
                "selected_summary": {
                    "candidate_key": "polymarket_leadlag_ic|event_reg|BTCUSDT|15m",
                    "gross_bps_mean": 1.4647,
                    "net_bps_mean": -2.5353,
                    "holdout_net_bps_mean": -1.0761,
                    "sample_count": 116,
                    "n_days": 3,
                    "horizon_minutes": 15,
                    "execution_realism_status": "UNMEASURED",
                },
            },
        },
        gate_b_watch={
            "schema_version": 1,
            "status": "WATCH_ONLY",
            "candidate_counts": {
                "total": 21,
                "watch_only": 1,
                "alertable": 0,
                "start_now": 0,
                "schedule": 0,
            },
        },
        now_utc=dt.datetime(2026, 6, 22, 3, tzinfo=dt.timezone.utc),
    )

    by_class = {row["class"]: row for row in scorecard["top_paths"]}
    assert by_class["low_friction_mm_alpha_search"]["status"] == (
        "LOW_FRICTION_MM_GROSS_EDGE_BELOW_CURRENT_FEE"
    )
    assert by_class["low_friction_mm_alpha_search"]["current_edge_bps"] == 2.269
    assert by_class["fee_or_scale"]["status"] == "FEE_OR_SCALE_PATH_NOT_SHORT_TERM_ALPHA"
    assert by_class["external_event_leadlag_alpha"]["status"] == (
        "POLYMARKET_ALPHA_GROSS_BELOW_COST_OR_EXECUTION_UNMEASURED"
    )
    assert by_class["event_driven_listing_fade"]["status"] == "EVENT_WAIT_NO_ACTIONABLE_WINDOW"
    assert scorecard["answers"]["profitability_proven"] is False
    assert scorecard["answers"]["alpha_or_edge_amplification_paths_present"] is True

    markdown = render_markdown(scorecard)
    assert "Profitability Path Scorecard" in markdown
    assert "mm_low_friction_signal_search" in markdown
