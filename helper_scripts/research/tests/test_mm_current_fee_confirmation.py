"""Focused tests for MM current-fee confirmation packets."""

from __future__ import annotations

import datetime as dt

from alpha_discovery_throughput.mm_current_fee_confirmation import (
    build_mm_current_fee_confirmation_packet,
    render_markdown,
)


def _fillsim_report() -> dict:
    return {
        "maker_fee_sensitivity_scorecard": {
            "current_maker_fee_bps_per_side": 2.0,
            "current_fee_round_trip_bps": 4.0,
            "scenarios": [{
                "maker_fee_bps_per_side": 2.0,
                "positive_sample_gate_cells": [{
                    "source": "edge_scorecard",
                    "scope": "per_symbol_primary_queue",
                    "symbol": "SOXLUSDT",
                    "queue_position": "back",
                    "policy": "informed_skip",
                    "track": "fill_only",
                    "n_fill_only": 43,
                    "edge_before_fees_bps": 4.715,
                    "break_even_maker_fee_bps_per_side": 2.357,
                    "net_bps_at_fee": 0.715,
                }],
            }],
        },
    }


def test_current_fee_confirmation_requires_repeat_window_for_single_window_cell():
    packet = build_mm_current_fee_confirmation_packet(
        fillsim=_fillsim_report(),
        fillsim_history={
            "status": "HISTORY_SINGLE_WINDOW_CURRENT_FEE_POSITIVE_NEEDS_CONFIRMATION",
            "reason": "current_fee_positive_not_repeated_enough",
            "valid_windows": 11,
            "distinct_window_dates": ["2026-06-20", "2026-06-21", "2026-06-23"],
            "current_fee_sample_gated_positive_windows": 1,
            "walk_forward_holdout_confirmed_windows": 0,
            "repeated_positive_keys": [],
        },
        now_utc=dt.datetime(2026, 6, 23, 18, tzinfo=dt.timezone.utc),
    )

    assert packet["schema_version"] == "mm_current_fee_confirmation_packet_v1"
    assert packet["status"] == "MM_CURRENT_FEE_CONFIRMATION_REQUIRES_REPEAT_WINDOW"
    assert packet["summary"]["candidate_key"] == (
        "edge_scorecard|per_symbol_primary_queue|SOXLUSDT|back|informed_skip|fill_only"
    )
    assert packet["summary"]["candidate_net_bps"] == 0.715
    assert packet["summary"]["history_valid_windows"] == 11
    assert packet["summary"]["history_current_fee_sample_gated_positive_windows"] == 1
    assert packet["summary"]["candidate_repeated_windows"] == 0
    assert packet["summary"]["repeat_window_confirmed"] is False
    assert packet["answers"]["global_cost_gate_lowering_recommended"] is False
    assert packet["answers"]["order_authority_granted"] is False

    markdown = render_markdown(packet)
    assert "MM Current-Fee Confirmation Packet" in markdown
    assert "SOXLUSDT" in markdown


def test_current_fee_confirmation_requires_oos_after_repeated_key():
    key = "edge_scorecard|per_symbol_primary_queue|SOXLUSDT|back|informed_skip|fill_only"
    packet = build_mm_current_fee_confirmation_packet(
        fillsim=_fillsim_report(),
        fillsim_history={
            "status": "HISTORY_CURRENT_FEE_REPEAT_IN_WINDOW_NEEDS_OOS",
            "reason": "current_fee_positive_repeats_but_not_walk_forward_confirmed",
            "valid_windows": 8,
            "current_fee_sample_gated_positive_windows": 2,
            "walk_forward_holdout_confirmed_windows": 0,
            "repeated_positive_keys": [{
                "key": key,
                "windows": 2,
                "window_sources": ["a.json", "b.json"],
                "best_cell": {
                    "source": "edge_scorecard",
                    "scope": "per_symbol_primary_queue",
                    "symbol": "SOXLUSDT",
                    "queue_position": "back",
                    "policy": "informed_skip",
                    "track": "fill_only",
                    "n_fill_only": 51,
                    "edge_before_fees_bps": 4.9,
                    "net_bps": 0.9,
                },
            }],
        },
        now_utc=dt.datetime(2026, 6, 23, 18, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "MM_CURRENT_FEE_CONFIRMATION_REQUIRES_OOS"
    assert packet["summary"]["candidate_repeated_windows"] == 2
    assert packet["summary"]["repeat_window_confirmed"] is True
    assert packet["summary"]["oos_walk_forward_confirmed"] is False
    assert packet["summary"]["maker_execution_realism_status"] == (
        "NOT_REACHED_OOS_REQUIRED"
    )


def test_current_fee_confirmation_requires_maker_realism_after_oos():
    key = "edge_scorecard|per_symbol_primary_queue|SOXLUSDT|back|informed_skip|fill_only"
    packet = build_mm_current_fee_confirmation_packet(
        fillsim=_fillsim_report(),
        fillsim_history={
            "status": "HISTORY_REPEAT_HOLDOUT_OR_CURRENT_FEE_POSITIVE",
            "reason": "repeated_sample_gated_positive_with_holdout_signal",
            "valid_windows": 8,
            "current_fee_sample_gated_positive_windows": 3,
            "walk_forward_holdout_confirmed_windows": 1,
            "repeated_positive_keys": [{
                "key": key,
                "windows": 3,
                "best_cell": {
                    "source": "edge_scorecard",
                    "scope": "per_symbol_primary_queue",
                    "symbol": "SOXLUSDT",
                    "queue_position": "back",
                    "policy": "informed_skip",
                    "track": "fill_only",
                    "n_fill_only": 61,
                    "edge_before_fees_bps": 5.1,
                    "net_bps": 1.1,
                },
            }],
        },
        now_utc=dt.datetime(2026, 6, 23, 18, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == (
        "MM_CURRENT_FEE_CONFIRMATION_REQUIRES_MAKER_EXECUTION_REALISM"
    )
    assert packet["summary"]["repeat_window_confirmed"] is True
    assert packet["summary"]["oos_walk_forward_confirmed"] is True
    assert packet["summary"]["maker_execution_realism_status"] == (
        "MISSING_MAKER_EXECUTION_REALISM_REVIEW"
    )
    assert packet["answers"]["promotion_evidence"] is False
