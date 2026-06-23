from __future__ import annotations

import json

from program_code.research.microstructure.fill_sim_history import (
    build_fill_sim_history_scorecard,
    load_reports,
)


def _report(
    day: str,
    *,
    current_positive: bool = False,
    holdout_positive: bool = False,
    break_even_fee: float | None = None,
    break_even_name: str = "quoted_half_spread_p75_and_side_book_imb_p75",
    break_even_symbol: str | None = None,
    break_even_policy: str | None = None,
    low_friction_near_miss_name: str | None = None,
    low_friction_holdout_edge: float = 3.2,
    low_friction_holdout_n: int = 30,
    low_friction_train_edge: float = -0.5,
    low_friction_train_n: int = 40,
    source_path: str | None = None,
) -> dict:
    edge_positive = []
    if current_positive:
        edge_positive.append(
            {
                "scope": "per_symbol_primary_queue",
                "symbol": "ABCUSDT",
                "queue_position": "back",
                "policy": "naive",
                "track": "fill_only",
                "n": 40,
                "net_bps": 0.25,
                "edge_before_fees_bps": 4.25,
                "signif_suppressed": False,
            }
        )

    holdout_rows = []
    if holdout_positive:
        holdout_rows.append(
            {
                "holdout": {
                    "name": "quoted_half_spread_train_p75_ge",
                    "condition": "quoted_half_spread_bps >= train_p75(6)",
                    "n_fill_only": 35,
                    "net_bps": 0.3,
                    "edge_before_fees_bps": 4.3,
                    "signif_suppressed": False,
                }
            }
        )

    fee_cell = None
    if break_even_fee is not None:
        fee_cell = {
            "source": "conditional_feature_scorecard",
            "name": break_even_name,
            "condition": f"{break_even_name} condition",
            "symbol": break_even_symbol,
            "policy": break_even_policy,
            "n_fill_only": 40,
            "edge_before_fees_bps": break_even_fee * 2.0,
            "break_even_maker_fee_bps_per_side": break_even_fee,
            "signif_suppressed": False,
        }

    rep = {
        "generated_at": f"{day}T06:00:00+00:00",
        "data": {
            "l1_rows_post_filter": 1000,
            "trades_rows": 2000,
            "span_minutes": 120.0,
            "n_symbols": 12,
            "l1_min_ts": f"{day}T04:00:00+00:00",
            "l1_max_ts": f"{day}T06:00:00+00:00",
            "l1_max_age_hours": 0.1,
        },
        "edge_scorecard": {
            "status": (
                "CONDITIONAL_POSITIVE_FILL_ONLY_CELL"
                if current_positive
                else "NO_POSITIVE_FILL_ONLY_CELL"
            ),
            "positive_fill_only_cells_with_sample_gate": edge_positive,
        },
        "conditional_feature_scorecard": {
            "status": "NO_CONDITIONAL_FEATURE_POSITIVE_CELL",
            "positive_cells_with_sample_gate": [],
        },
        "walk_forward_feature_scorecard": {
            "status": (
                "WALK_FORWARD_FEATURE_HOLDOUT_POSITIVE_SAMPLE_GATED"
                if holdout_positive
                else "NO_WALK_FORWARD_FEATURE_TRAIN_POSITIVE"
            ),
            "holdout_confirmed_candidates": holdout_rows,
        },
        "maker_fee_sensitivity_scorecard": {
            "status": (
                "LOWER_FEE_SAMPLE_GATED_POSITIVE"
                if break_even_fee is not None and break_even_fee < 2.0
                else "NO_FEE_SCENARIO_POSITIVE_CELL"
            ),
            "best_sample_gated_break_even_cell": fee_cell,
            "scenarios": [],
        },
        "low_friction_signal_scorecard": {
            "status": "LOW_FRICTION_SIGNAL_TRAIN_ONLY_CURRENT_FEE",
            "current_fee_round_trip_bps": 4.0,
            "failure_summary": {
                "best_sample_gated_holdout_gross_candidate": (
                    {
                        "name": low_friction_near_miss_name,
                        "condition": f"{low_friction_near_miss_name} condition",
                        "feature": "low_friction_interaction",
                        "candidate_shape": "spread_thin_queue_favorable_interaction_v1",
                        "threshold_source": "train_only",
                        "holdout_edge_before_fees_bps": low_friction_holdout_edge,
                        "holdout_n_fill_only": low_friction_holdout_n,
                        "holdout_net_bps": low_friction_holdout_edge - 4.0,
                        "train_edge_before_fees_bps": low_friction_train_edge,
                        "train_n_fill_only": low_friction_train_n,
                        "train_net_bps": low_friction_train_edge - 4.0,
                    }
                    if low_friction_near_miss_name is not None
                    else None
                ),
                "top_holdout_gross_candidates": [],
            },
        },
    }
    if source_path:
        rep["_source_path"] = source_path
    return rep


def test_history_scorecard_requires_multiple_windows_before_status_claims() -> None:
    scorecard = build_fill_sim_history_scorecard([
        _report("2026-06-20", current_positive=True, break_even_fee=2.2)
    ])

    assert scorecard["status"] == "HISTORY_INSUFFICIENT_WINDOWS"
    assert scorecard["valid_windows"] == 1
    assert scorecard["current_fee_sample_gated_positive_windows"] == 1
    assert scorecard["reason"] == "below_min_windows_or_dates"


def test_history_scorecard_marks_lower_fee_only_when_current_fee_never_clears() -> None:
    reports = [
        _report("2026-06-18", break_even_fee=1.1),
        _report("2026-06-19", break_even_fee=1.2),
        _report("2026-06-20", break_even_fee=1.0),
    ]

    scorecard = build_fill_sim_history_scorecard(reports)

    assert scorecard["status"] == "HISTORY_LOWER_FEE_ONLY"
    best = scorecard["best_sample_gated_break_even_window"]
    assert best["break_even_maker_fee_bps_per_side"] == 1.2
    assert best["cell"]["fee_reduction_to_breakeven_bps_per_side"] == 0.8
    stability = scorecard["lower_fee_break_even_stability"]
    assert stability["status"] == "LOWER_FEE_BREAK_EVEN_REPEATS_ACROSS_WINDOWS"
    assert stability["lower_fee_break_even_windows"] == 3
    assert stability["repeated_key_count"] == 1
    assert scorecard["repeated_lower_fee_break_even_keys"][0]["windows"] == 3


def test_history_scorecard_marks_rotating_lower_fee_break_even_keys() -> None:
    reports = [
        _report("2026-06-18", break_even_fee=1.1, break_even_name="cell_a"),
        _report("2026-06-19", break_even_fee=1.2, break_even_name="cell_b"),
        _report("2026-06-20", break_even_fee=1.0, break_even_name="cell_c"),
    ]

    scorecard = build_fill_sim_history_scorecard(reports)

    assert scorecard["status"] == "HISTORY_LOWER_FEE_ONLY"
    stability = scorecard["lower_fee_break_even_stability"]
    assert stability["status"] == "LOWER_FEE_BREAK_EVEN_ROTATES_OR_DATE_INSUFFICIENT"
    assert stability["reason"] == "no_repeated_lower_fee_break_even_key"
    assert stability["lower_fee_break_even_windows"] == 3
    assert stability["repeated_key_count"] == 0


def test_history_scorecard_requires_distinct_dates_for_repeated_lower_fee_key() -> None:
    reports = [
        _report("2026-06-20", break_even_fee=1.1, source_path="a.json"),
        _report("2026-06-20", break_even_fee=1.2, source_path="b.json"),
        _report("2026-06-20", break_even_fee=1.0, source_path="c.json"),
    ]

    scorecard = build_fill_sim_history_scorecard(reports)

    assert scorecard["status"] == "HISTORY_INSUFFICIENT_WINDOWS"
    stability = scorecard["lower_fee_break_even_stability"]
    assert stability["status"] == "LOWER_FEE_BREAK_EVEN_REPEATS_BUT_DATE_INSUFFICIENT"
    assert stability["reason"] == "repeated_key_but_distinct_dates_below_min"
    assert stability["repeated_key_count"] == 1


def test_history_scorecard_tracks_repeated_low_friction_near_miss() -> None:
    reports = [
        _report(
            "2026-06-18",
            low_friction_near_miss_name=(
                "quoted_half_spread_bps_train_p75_and_q_eff_train_p10_and_spread_bps_delta_10s_train_p90"
            ),
            low_friction_holdout_edge=3.2,
            low_friction_train_edge=-0.6,
        ),
        _report(
            "2026-06-19",
            low_friction_near_miss_name=(
                "quoted_half_spread_bps_train_p75_and_q_eff_train_p10_and_spread_bps_delta_10s_train_p90"
            ),
            low_friction_holdout_edge=3.4,
            low_friction_train_edge=0.2,
        ),
        _report(
            "2026-06-20",
            low_friction_near_miss_name="rotating_queue_pressure_cell",
            low_friction_holdout_edge=2.6,
            low_friction_train_edge=-1.0,
        ),
    ]

    scorecard = build_fill_sim_history_scorecard(reports)

    stability = scorecard["low_friction_near_miss_stability"]
    assert stability["status"] == "LOW_FRICTION_NEAR_MISS_REPEATS_ACROSS_WINDOWS"
    assert stability["sample_gated_near_miss_windows"] == 3
    assert stability["repeated_key_count"] == 1
    best = stability["best_repeated_near_miss_key"]
    assert best["windows"] == 2
    assert best["best_cell"]["candidate_shape"] == (
        "spread_thin_queue_favorable_interaction_v1"
    )
    assert best["best_cell"]["holdout_edge_before_fees_bps"] == 3.4
    assert best["best_cell"]["train_holdout_gross_current_fee_consistent"] is False
    assert scorecard["status"] == "HISTORY_NO_CURRENT_FEE_SAMPLE_GATED_EDGE"


def test_history_scorecard_requires_distinct_dates_for_repeated_low_friction_near_miss() -> None:
    reports = [
        _report("2026-06-20", low_friction_near_miss_name="queue_cell", source_path="a.json"),
        _report("2026-06-20", low_friction_near_miss_name="queue_cell", source_path="b.json"),
        _report("2026-06-20", low_friction_near_miss_name="queue_cell", source_path="c.json"),
    ]

    scorecard = build_fill_sim_history_scorecard(reports)

    stability = scorecard["low_friction_near_miss_stability"]
    assert stability["status"] == "LOW_FRICTION_NEAR_MISS_REPEATS_BUT_DATE_INSUFFICIENT"
    assert stability["reason"] == "repeated_key_but_distinct_dates_below_min"
    assert stability["repeated_key_count"] == 1


def test_history_scorecard_groups_low_friction_near_miss_motifs() -> None:
    reports = [
        _report(
            "2026-06-18",
            low_friction_near_miss_name=(
                "quoted_half_spread_bps_train_p75_and_q_eff_train_p10_and_spread_bps_delta_10s_train_p90"
            ),
            low_friction_holdout_edge=3.2,
            low_friction_train_edge=-0.4,
        ),
        _report(
            "2026-06-19",
            low_friction_near_miss_name=(
                "quoted_half_spread_bps_train_p75_and_q0_train_p25_and_spread_bps_delta_10s_train_p75"
            ),
            low_friction_holdout_edge=3.1,
            low_friction_train_edge=-0.8,
        ),
        _report(
            "2026-06-20",
            low_friction_near_miss_name=(
                "quoted_half_spread_bps_train_p90_and_q_eff_train_p10_and_spread_bps_delta_30s_train_p90"
            ),
            low_friction_holdout_edge=3.5,
            low_friction_train_edge=0.1,
        ),
    ]

    scorecard = build_fill_sim_history_scorecard(reports)

    assert scorecard["repeated_low_friction_near_miss_keys"] == []
    motif = scorecard["low_friction_near_miss_motif_stability"]
    assert motif["status"] == "LOW_FRICTION_NEAR_MISS_MOTIF_REPEATS_ACROSS_WINDOWS"
    assert motif["repeated_motif_count"] == 1
    best = motif["best_repeated_near_miss_motif"]
    assert best["windows"] == 3
    assert best["distinct_window_dates"] == ["2026-06-18", "2026-06-19", "2026-06-20"]
    assert best["best_cell"]["motif_key"] == (
        "low_friction_motif|spread_thin_queue_favorable|thin_queue|spread_delta"
    )
    assert best["best_cell"]["train_holdout_gross_current_fee_consistent"] is False
    assert scorecard["status"] == "HISTORY_NO_CURRENT_FEE_SAMPLE_GATED_EDGE"


def test_history_scorecard_repeated_current_fee_positive_still_requires_oos() -> None:
    reports = [
        _report("2026-06-18", current_positive=True, break_even_fee=2.2),
        _report("2026-06-19", current_positive=True, break_even_fee=2.3),
        _report("2026-06-20", current_positive=False, break_even_fee=1.4),
    ]

    scorecard = build_fill_sim_history_scorecard(reports)

    assert scorecard["status"] == "HISTORY_CURRENT_FEE_REPEAT_IN_WINDOW_NEEDS_OOS"
    assert scorecard["repeated_positive_keys"]
    assert scorecard["walk_forward_holdout_confirmed_windows"] == 0


def test_history_scorecard_tracks_holdout_confirmed_windows() -> None:
    reports = [
        _report("2026-06-18", current_positive=True, holdout_positive=True, break_even_fee=2.2),
        _report("2026-06-19", current_positive=True, holdout_positive=True, break_even_fee=2.3),
        _report("2026-06-20", current_positive=False, break_even_fee=1.4),
    ]

    scorecard = build_fill_sim_history_scorecard(reports)

    assert scorecard["status"] == "HISTORY_REPEAT_HOLDOUT_OR_CURRENT_FEE_POSITIVE"
    assert scorecard["walk_forward_holdout_confirmed_windows"] == 2
    assert scorecard["repeated_positive_keys"]


def test_load_reports_skips_invalid_json(tmp_path) -> None:
    good = tmp_path / "good.json"
    bad = tmp_path / "bad.json"
    good.write_text(json.dumps(_report("2026-06-20")), encoding="utf-8")
    bad.write_text("{not-json", encoding="utf-8")

    reports = load_reports([str(good), str(bad), str(tmp_path / "missing.json")])

    assert len(reports) == 1
    assert reports[0]["_source_path"] == str(good)
