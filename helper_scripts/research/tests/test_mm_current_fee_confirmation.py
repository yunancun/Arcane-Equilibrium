"""Focused tests for MM current-fee confirmation packets."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

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


def _candidate_key() -> str:
    return "edge_scorecard|per_symbol_primary_queue|SOXLUSDT|back|informed_skip|fill_only"


def _history_window(
    *,
    source_path: str,
    window_date: str | None,
    key: str | None = None,
    symbol: str = "SOXLUSDT",
) -> dict:
    return {
        "source_path": source_path,
        "generated_at": f"{window_date or '2026-06-23'}T06:00:00+00:00",
        "window_date": window_date,
        "valid": True,
        "current_fee_sample_gated_positive_cells": [{
            "source": "edge_scorecard",
            "key": key or _candidate_key(),
            "scope": "per_symbol_primary_queue",
            "symbol": symbol,
            "queue_position": "back",
            "policy": "informed_skip",
            "track": "fill_only",
            "n_fill_only": 43,
            "edge_before_fees_bps": 4.715,
            "net_bps": 0.715,
        }],
    }


def test_current_fee_confirmation_requires_repeat_window_for_single_window_cell():
    packet = build_mm_current_fee_confirmation_packet(
        fillsim=_fillsim_report(),
        fillsim_history={
            "status": "HISTORY_SINGLE_WINDOW_CURRENT_FEE_POSITIVE_NEEDS_CONFIRMATION",
            "reason": "current_fee_positive_not_repeated_enough",
            "thresholds": {"min_repeat_positive_windows": 2},
            "valid_windows": 11,
            "distinct_window_dates": ["2026-06-20", "2026-06-21", "2026-06-23"],
            "current_fee_sample_gated_positive_windows": 1,
            "walk_forward_holdout_confirmed_windows": 0,
            "repeated_positive_keys": [],
            "window_summaries": [
                _history_window(source_path="a.json", window_date="2026-06-23")
            ],
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
    assert packet["summary"]["candidate_observed_independent_windows"] == 1
    assert packet["summary"]["repeat_window_design_status"] == (
        "REPEAT_WINDOW_SAFE_TEST_READY"
    )
    assert packet["summary"]["same_candidate_independent_windows_remaining"] == 1
    assert packet["repeat_window_design"]["max_safe_next_action"] == (
        "accumulate_or_replay_independent_windows_for_same_current_fee_mm_cell"
    )
    assert packet["summary"]["repeat_window_confirmed"] is False
    assert packet["answers"]["global_cost_gate_lowering_recommended"] is False
    assert packet["answers"]["order_authority_granted"] is False

    markdown = render_markdown(packet)
    assert "MM Current-Fee Confirmation Packet" in markdown
    assert "SOXLUSDT" in markdown


def test_current_fee_confirmation_normalizes_recorder_edge_scorecard_key():
    packet = build_mm_current_fee_confirmation_packet(
        fillsim=_fillsim_report(),
        gross_edge_cost_decomposition={
            "current_fee_round_trip_bps": 4.0,
            "current_fee_positive_sample_gated_cell_count": 1,
            "best_sample_gated_current_fee_cell": {
                "source": "edge_scorecard",
                "symbol": "SOXLUSDT",
                "queue_position": "back",
                "policy": "informed_skip",
                "track": "fill_only",
                "n_fill_only": 43,
                "edge_before_fees_bps": 4.715,
                "net_bps": 0.715,
                "break_even_maker_fee_bps_per_side": 2.3575,
            },
        },
        fillsim_history={
            "status": "HISTORY_SINGLE_WINDOW_CURRENT_FEE_POSITIVE_NEEDS_CONFIRMATION",
            "thresholds": {"min_repeat_positive_windows": 2},
            "current_fee_sample_gated_positive_windows": 1,
            "repeated_positive_keys": [],
            "window_summaries": [
                _history_window(source_path="a.json", window_date="2026-06-23")
            ],
        },
        now_utc=dt.datetime(2026, 6, 23, 18, tzinfo=dt.timezone.utc),
    )

    assert packet["summary"]["candidate_key"] == (
        "edge_scorecard|per_symbol_primary_queue|SOXLUSDT|back|informed_skip|fill_only"
    )
    assert packet["summary"]["candidate_break_even_maker_fee_bps_per_side"] == 2.3575


def test_current_fee_confirmation_requires_oos_after_repeated_key():
    key = _candidate_key()
    packet = build_mm_current_fee_confirmation_packet(
        fillsim=_fillsim_report(),
        fillsim_history={
            "status": "HISTORY_CURRENT_FEE_REPEAT_IN_WINDOW_NEEDS_OOS",
            "reason": "current_fee_positive_repeats_but_not_walk_forward_confirmed",
            "thresholds": {"min_repeat_positive_windows": 2},
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
            "window_summaries": [
                _history_window(source_path="a.json", window_date="2026-06-22"),
                _history_window(source_path="b.json", window_date="2026-06-23"),
            ],
        },
        now_utc=dt.datetime(2026, 6, 23, 18, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "MM_CURRENT_FEE_CONFIRMATION_REQUIRES_OOS"
    assert packet["summary"]["candidate_repeated_windows"] == 2
    assert packet["summary"]["candidate_observed_independent_windows"] == 2
    assert packet["summary"]["repeat_window_design_status"] == (
        "REPEAT_WINDOW_CONFIRMED_ADVANCE_TO_NEXT_GATE"
    )
    assert packet["summary"]["repeat_window_confirmed"] is True
    assert packet["summary"]["oos_walk_forward_confirmed"] is False
    assert packet["summary"]["maker_execution_realism_status"] == (
        "NOT_REACHED_OOS_REQUIRED"
    )


def test_current_fee_confirmation_requires_maker_realism_after_oos():
    key = _candidate_key()
    packet = build_mm_current_fee_confirmation_packet(
        fillsim=_fillsim_report(),
        fillsim_history={
            "status": "HISTORY_REPEAT_HOLDOUT_OR_CURRENT_FEE_POSITIVE",
            "reason": "repeated_sample_gated_positive_with_holdout_signal",
            "thresholds": {"min_repeat_positive_windows": 2},
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
            "window_summaries": [
                _history_window(source_path="a.json", window_date="2026-06-21"),
                _history_window(source_path="b.json", window_date="2026-06-22"),
                _history_window(source_path="c.json", window_date="2026-06-23"),
            ],
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


def test_current_fee_confirmation_requires_exact_key_for_repeat_window():
    packet = build_mm_current_fee_confirmation_packet(
        fillsim=_fillsim_report(),
        fillsim_history={
            "status": "HISTORY_SINGLE_WINDOW_CURRENT_FEE_POSITIVE_NEEDS_CONFIRMATION",
            "thresholds": {"min_repeat_positive_windows": 2},
            "current_fee_sample_gated_positive_windows": 2,
            "repeated_positive_keys": [],
            "window_summaries": [
                _history_window(
                    source_path="a.json",
                    window_date="2026-06-22",
                    key="edge_scorecard|per_symbol_primary_queue|SOXLUSDT|front|informed_skip|fill_only",
                ),
                _history_window(source_path="b.json", window_date="2026-06-23"),
            ],
        },
        now_utc=dt.datetime(2026, 6, 23, 18, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "MM_CURRENT_FEE_CONFIRMATION_REQUIRES_REPEAT_WINDOW"
    assert packet["summary"]["candidate_observed_independent_windows"] == 1
    assert packet["summary"]["same_candidate_independent_windows_remaining"] == 1


def test_current_fee_confirmation_dedupes_source_and_date_for_repeat_window():
    key = _candidate_key()
    packet = build_mm_current_fee_confirmation_packet(
        fillsim=_fillsim_report(),
        fillsim_history={
            "status": "HISTORY_CURRENT_FEE_REPEAT_IN_WINDOW_NEEDS_OOS",
            "thresholds": {"min_repeat_positive_windows": 2},
            "current_fee_sample_gated_positive_windows": 3,
            "repeated_positive_keys": [{"key": key, "windows": 2}],
            "window_summaries": [
                _history_window(source_path="a.json", window_date="2026-06-23"),
                _history_window(source_path="a.json", window_date="2026-06-23"),
                _history_window(source_path="b.json", window_date="2026-06-23"),
                _history_window(source_path="c.json", window_date=None),
            ],
        },
        now_utc=dt.datetime(2026, 6, 23, 18, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "MM_CURRENT_FEE_CONFIRMATION_HISTORY_REBUILD_REQUIRED"
    assert packet["summary"]["candidate_observed_windows"] == 3
    assert packet["summary"]["candidate_observed_independent_windows"] == 1
    assert packet["summary"]["repeat_window_consistency_status"] == (
        "reported_repeats_disagree_with_window_summaries"
    )


def test_current_fee_confirmation_rejects_malformed_exact_key_window_cells():
    key = _candidate_key()
    packet = build_mm_current_fee_confirmation_packet(
        fillsim=_fillsim_report(),
        fillsim_history={
            "status": "HISTORY_CURRENT_FEE_REPEAT_IN_WINDOW_NEEDS_OOS",
            "thresholds": {"min_repeat_positive_windows": 2},
            "current_fee_sample_gated_positive_windows": 2,
            "repeated_positive_keys": [{"key": key, "windows": 2}],
            "window_summaries": [
                {
                    "source_path": "a.json",
                    "window_date": "2026-06-22",
                    "valid": True,
                    "current_fee_sample_gated_positive_cells": [{"key": key}],
                },
                {
                    "source_path": "b.json",
                    "window_date": "2026-06-23",
                    "valid": True,
                    "current_fee_sample_gated_positive_cells": [{
                        "key": key,
                        "net_bps": 0.715,
                    }],
                },
            ],
        },
        now_utc=dt.datetime(2026, 6, 23, 18, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "MM_CURRENT_FEE_CONFIRMATION_HISTORY_REBUILD_REQUIRED"
    assert packet["reason"] == "fill_sim_history_window_summaries_malformed_for_candidate"
    assert packet["summary"]["candidate_observed_independent_windows"] == 0
    assert packet["summary"]["candidate_malformed_window_cell_count"] == 2
    assert packet["summary"]["repeat_window_design_status"] == (
        "HISTORY_WINDOW_SUMMARIES_MALFORMED"
    )
    assert packet["summary"]["repeat_window_confirmed"] is False


def test_current_fee_confirmation_malformed_cell_forces_repeat_proof_false():
    key = _candidate_key()
    packet = build_mm_current_fee_confirmation_packet(
        fillsim=_fillsim_report(),
        fillsim_history={
            "status": "HISTORY_CURRENT_FEE_REPEAT_IN_WINDOW_NEEDS_OOS",
            "thresholds": {"min_repeat_positive_windows": 2},
            "current_fee_sample_gated_positive_windows": 3,
            "repeated_positive_keys": [{"key": key, "windows": 2}],
            "window_summaries": [
                _history_window(source_path="a.json", window_date="2026-06-21"),
                _history_window(source_path="b.json", window_date="2026-06-22"),
                {
                    "source_path": "c.json",
                    "window_date": "2026-06-23",
                    "valid": True,
                    "current_fee_sample_gated_positive_cells": [{
                        "source": "edge_scorecard",
                        "scope": "per_symbol_primary_queue",
                        "symbol": "SOXLUSDT",
                        "queue_position": "back",
                        "policy": "informed_skip",
                        "track": "fill_only",
                        "key": key,
                    }],
                },
            ],
        },
        now_utc=dt.datetime(2026, 6, 23, 18, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "MM_CURRENT_FEE_CONFIRMATION_HISTORY_REBUILD_REQUIRED"
    assert packet["summary"]["candidate_observed_independent_windows"] == 2
    assert packet["summary"]["candidate_malformed_window_cell_count"] == 1
    assert packet["summary"]["repeat_window_confirmed"] is False
    assert packet["answers"]["repeat_window_confirmed"] is False


def test_current_fee_confirmation_fails_closed_on_authority_signal():
    packet = build_mm_current_fee_confirmation_packet(
        fillsim=_fillsim_report(),
        fillsim_history={
            "status": "HISTORY_SINGLE_WINDOW_CURRENT_FEE_POSITIVE_NEEDS_CONFIRMATION",
            "thresholds": {"min_repeat_positive_windows": 2},
            "current_fee_sample_gated_positive_windows": 1,
            "promotion_evidence": True,
            "window_summaries": [
                _history_window(source_path="a.json", window_date="2026-06-23")
            ],
        },
        now_utc=dt.datetime(2026, 6, 23, 18, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert "promotion_evidence" in packet["reason"]
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["promotion_evidence"] is False


def test_current_fee_confirmation_fails_closed_on_authority_signal_without_candidate():
    packet = build_mm_current_fee_confirmation_packet(
        fillsim={},
        fillsim_history={"order_authority_granted": True},
        now_utc=dt.datetime(2026, 6, 23, 18, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert "order_authority_granted" in packet["reason"]
    assert packet["answers"]["current_fee_positive_candidate_present"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_current_fee_confirmation_fails_closed_on_non_none_authority_signal():
    packet = build_mm_current_fee_confirmation_packet(
        fillsim={},
        fillsim_history={
            "main_cost_gate_adjustment": "LOWER_CURRENT_FEE_MM_GATE",
            "runtime_mutation": "SERVICE_RESTARTED",
        },
        now_utc=dt.datetime(2026, 6, 23, 18, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert "main_cost_gate_adjustment" in packet["reason"]
    assert packet["answers"]["current_fee_positive_candidate_present"] is False
    assert packet["answers"]["main_cost_gate_adjustment"] == "NONE"
    assert packet["global_boundaries"]["runtime_mutation"] == "NONE"


def test_current_fee_confirmation_fails_closed_without_window_summaries():
    packet = build_mm_current_fee_confirmation_packet(
        fillsim=_fillsim_report(),
        fillsim_history={
            "status": "HISTORY_SINGLE_WINDOW_CURRENT_FEE_POSITIVE_NEEDS_CONFIRMATION",
            "thresholds": {"min_repeat_positive_windows": 2},
            "current_fee_sample_gated_positive_windows": 1,
            "repeated_positive_keys": [],
        },
        now_utc=dt.datetime(2026, 6, 23, 18, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == (
        "MM_CURRENT_FEE_CONFIRMATION_HISTORY_WINDOW_SUMMARIES_REQUIRED"
    )
    assert packet["summary"]["repeat_window_design_status"] == (
        "HISTORY_WINDOW_SUMMARIES_REQUIRED"
    )
    assert packet["summary"]["repeat_window_confirmed"] is False
    assert packet["repeat_window_design"]["max_safe_next_action"] == (
        "rebuild_fill_sim_history_scorecard_with_window_summaries"
    )
    assert packet["answers"]["promotion_evidence"] is False


def test_current_fee_confirmation_source_stays_artifact_only():
    source = Path(
        "helper_scripts/research/alpha_discovery_throughput/"
        "mm_current_fee_confirmation.py"
    ).read_text(encoding="utf-8")

    forbidden_tokens = [
        "psycopg",
        "requests.",
        "urllib.",
        "ccxt",
        "pybit",
        "place_order",
        "cancel_order",
        "create_order",
        "submit_order",
        "modify_order",
    ]
    assert not [token for token in forbidden_tokens if token in source]
