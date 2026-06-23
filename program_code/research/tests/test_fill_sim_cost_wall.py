from __future__ import annotations

import pandas as pd
import pytest

from program_code.research.microstructure.fill_sim import (
    _net_block,
    add_low_friction_microstructure_features,
    fill_sim_conditional_feature_scorecard,
    fill_sim_edge_scorecard,
    fill_sim_horizon_scorecard,
    fill_sim_low_friction_signal_scorecard,
    fill_sim_maker_fee_sensitivity_scorecard,
    fill_sim_walk_forward_feature_scorecard,
)


def test_net_block_reports_break_even_cost_wall():
    sub = pd.DataFrame(
        {
            "half_spread_bps": [1.0, 3.0],
            "adverse_sel_bps@15": [0.5, 1.5],
        }
    )

    out = _net_block(sub, horizons=(15,), n_for_signif=len(sub))

    assert out["n"] == 2
    assert out["half_spread_bps"] == pytest.approx(2.0)
    assert out["adverse_sel_bps@15"] == pytest.approx(1.0)
    assert out["edge_before_fees_bps@15"] == pytest.approx(1.0)
    assert out["net_bps@15_maker_exit"] == pytest.approx(-3.0)
    assert out["net_bps@15_taker_exit"] == pytest.approx(-6.5)
    assert out["break_even_fee_round_trip_bps@15_maker_exit"] == pytest.approx(1.0)
    assert out["break_even_maker_fee_bps_per_side@15_maker_exit"] == pytest.approx(0.5)
    assert out["fee_round_trip_shortfall_bps@15_maker_exit"] == pytest.approx(3.0)
    assert out["required_half_spread_bps@15_maker_exit"] == pytest.approx(5.0)
    assert out["required_maker_rebate_bps_per_side@15_maker_exit"] == pytest.approx(0.0)


def test_net_block_reports_required_rebate_when_break_even_fee_is_negative():
    sub = pd.DataFrame(
        {
            "half_spread_bps": [0.6],
            "adverse_sel_bps@15": [1.8],
        }
    )

    out = _net_block(sub, horizons=(15,), n_for_signif=len(sub))

    assert out["edge_before_fees_bps@15"] == pytest.approx(-1.2)
    assert out["break_even_fee_round_trip_bps@15_maker_exit"] == pytest.approx(-1.2)
    assert out["break_even_maker_fee_bps_per_side@15_maker_exit"] == pytest.approx(-0.6)
    assert out["required_maker_rebate_bps_per_side@15_maker_exit"] == pytest.approx(0.6)
    assert out["fee_round_trip_shortfall_bps@15_maker_exit"] == pytest.approx(5.2)


def test_net_block_empty_block_sets_cost_wall_fields_to_none():
    sub = pd.DataFrame(columns=["half_spread_bps", "adverse_sel_bps@15"])

    out = _net_block(sub, horizons=(15,), n_for_signif=0)

    assert out["n"] == 0
    assert out["half_spread_bps"] is None
    assert out["edge_before_fees_bps@15"] is None
    assert out["break_even_fee_round_trip_bps@15_maker_exit"] is None
    assert out["break_even_maker_fee_bps_per_side@15_maker_exit"] is None
    assert out["fee_round_trip_shortfall_bps@15_maker_exit"] is None
    assert out["required_half_spread_bps@15_maker_exit"] is None
    assert out["required_maker_rebate_bps_per_side@15_maker_exit"] is None
    assert out["signif_suppressed@15"] is True


def _block(*, n: int, half_spread: float, adverse: float) -> dict:
    return _net_block(
        pd.DataFrame(
            {
                "half_spread_bps": [half_spread] * n,
                "adverse_sel_bps@15": [adverse] * n,
            }
        ),
        horizons=(15,),
        n_for_signif=n,
    )


def test_fill_sim_edge_scorecard_ranks_conditional_positive_cells():
    report = {
        "primary_queue_position": "back",
        "pooled": {
            "naive": {"fill_only": _block(n=40, half_spread=1.0, adverse=1.5)},
            "informed_skip": {"fill_only": _block(n=40, half_spread=1.2, adverse=1.4)},
        },
        "queue_dose_response": {
            "queue_positions": {
                "front": {
                    "naive": {"fill_only": _block(n=35, half_spread=5.0, adverse=0.4)},
                    "informed_skip": {"fill_only": _block(n=25, half_spread=5.2, adverse=0.3)},
                },
                "back": {
                    "naive": {"fill_only": _block(n=40, half_spread=1.0, adverse=1.5)},
                    "informed_skip": {"fill_only": _block(n=40, half_spread=1.2, adverse=1.4)},
                },
            }
        },
        "per_symbol": [
            {
                "symbol": "ABCUSDT",
                "naive": {"fill_only": _block(n=40, half_spread=4.3, adverse=0.2)},
                "informed_skip": {"fill_only": _block(n=40, half_spread=4.4, adverse=0.1)},
            },
        ],
    }

    scorecard = fill_sim_edge_scorecard(report, primary_horizon_s=15)

    assert scorecard["status"] == "CONDITIONAL_POSITIVE_FILL_ONLY_CELL"
    assert scorecard["cells_evaluated"] == 8
    assert scorecard["best_fill_only"]["queue_position"] == "front"
    assert scorecard["best_fill_only"]["policy"] == "informed_skip"
    assert scorecard["best_fill_only"]["net_bps"] == pytest.approx(0.9)
    assert scorecard["best_fill_only"]["signif_suppressed"] is True
    assert scorecard["best_back_of_queue_fill_only"]["symbol"] == "ABCUSDT"
    assert scorecard["best_back_of_queue_fill_only"]["net_bps"] == pytest.approx(0.3)
    assert scorecard["positive_fill_only_cells_with_sample_gate"][0]["queue_position"] == "front"
    assert any(
        cell["symbol"] == "ABCUSDT"
        for cell in scorecard["positive_fill_only_cells_with_sample_gate"]
    )


def test_fill_sim_edge_scorecard_surfaces_nearest_negative_cell():
    report = {
        "primary_queue_position": "back",
        "pooled": {
            "naive": {"fill_only": _block(n=40, half_spread=1.0, adverse=1.1)},
            "informed_skip": {"fill_only": _block(n=40, half_spread=1.4, adverse=1.1)},
        },
    }

    scorecard = fill_sim_edge_scorecard(report, primary_horizon_s=15)

    assert scorecard["status"] == "NO_POSITIVE_FILL_ONLY_CELL"
    assert scorecard["positive_fill_only_cells"] == []
    assert scorecard["best_fill_only"]["policy"] == "informed_skip"
    assert scorecard["best_fill_only"]["net_bps"] == pytest.approx(-3.7)
    assert scorecard["best_fill_only"]["fee_round_trip_shortfall_bps"] == pytest.approx(3.7)


def test_fill_sim_horizon_scorecard_finds_non_primary_horizon_positive():
    report = {
        "params": {"horizons_s": [5, 15, 30]},
        "primary_queue_position": "back",
        "pooled": {
            "naive": {
                "fill_only": _net_block(
                    pd.DataFrame(
                        {
                            "half_spread_bps": [6.0] * 40,
                            "adverse_sel_bps@5": [3.0] * 40,
                            "adverse_sel_bps@15": [3.0] * 40,
                            "adverse_sel_bps@30": [1.0] * 40,
                        }
                    ),
                    horizons=(5, 15, 30),
                    n_for_signif=40,
                )
            }
        },
    }

    scorecard = fill_sim_horizon_scorecard(report)

    assert scorecard["status"] == "HORIZON_SAMPLE_GATED_POSITIVE"
    assert scorecard["best_cell"]["horizon_s"] == 30
    assert scorecard["best_cell"]["net_bps"] == pytest.approx(1.0)
    assert scorecard["best_by_horizon"][0]["horizon_s"] == 5
    assert scorecard["positive_cells_with_sample_gate"][0]["horizon_s"] == 30


def test_fill_sim_horizon_scorecard_blocks_when_all_horizons_negative():
    report = {
        "params": {"horizons_s": [5, 15, 30]},
        "primary_queue_position": "back",
        "pooled": {
            "naive": {
                "fill_only": _net_block(
                    pd.DataFrame(
                        {
                            "half_spread_bps": [2.0] * 40,
                            "adverse_sel_bps@5": [1.0] * 40,
                            "adverse_sel_bps@15": [1.2] * 40,
                            "adverse_sel_bps@30": [0.8] * 40,
                        }
                    ),
                    horizons=(5, 15, 30),
                    n_for_signif=40,
                )
            }
        },
    }

    scorecard = fill_sim_horizon_scorecard(report)

    assert scorecard["status"] == "NO_HORIZON_POSITIVE_CELL"
    assert scorecard["positive_cells"] == []
    assert scorecard["best_cell"]["horizon_s"] == 30
    assert scorecard["best_cell"]["net_bps"] == pytest.approx(-2.8)


def _conditional_trials(rows: list[dict]) -> pd.DataFrame:
    out = []
    for i, row in enumerate(rows):
        out.append(
            {
                "symbol": row.get("symbol", "ABCUSDT"),
                "side": row.get("side", "bid"),
                "t_place": i,
                "outcome": row.get("outcome", "fill"),
                "quoted_half_spread_bps": row.get("quoted_half_spread_bps", 1.0),
                "q0": row.get("q0", 10.0),
                "q_eff": row.get("q_eff", row.get("q0", 10.0)),
                "side_book_imb": row.get("side_book_imb", 0.0),
                "side_signal_ofi10": row.get("side_signal_ofi10", 0.0),
                "side_signal_btc_lead": row.get("side_signal_btc_lead", 0.0),
            }
        )
    return pd.DataFrame(out)


def _conditional_adverse(trials: pd.DataFrame, rows: list[dict]) -> pd.DataFrame:
    out = []
    for i, row in enumerate(rows):
        if row.get("outcome", "fill") not in {"fill", "adverse_through"}:
            continue
        out.append(
            {
                "symbol": trials.at[i, "symbol"],
                "side": trials.at[i, "side"],
                "t_place": int(trials.at[i, "t_place"]),
                "outcome": row.get("outcome", "fill"),
                "half_spread_bps": row.get("half_spread_bps", 1.0),
                "adverse_sel_bps@15": row.get("adverse_sel_bps@15", 1.0),
            }
        )
    return pd.DataFrame(out)


def test_conditional_feature_scorecard_finds_sample_gated_positive_cell():
    rows = []
    for _ in range(35):
        rows.append(
            {
                "side": "bid",
                "quoted_half_spread_bps": 6.0,
                "q0": 2.0,
                "side_book_imb": 0.8,
                "side_signal_ofi10": 1.0,
                "half_spread_bps": 6.0,
                "adverse_sel_bps@15": 1.0,
            }
        )
    for _ in range(10):
        rows.append(
            {
                "side": "bid",
                "quoted_half_spread_bps": 1.0,
                "half_spread_bps": 1.0,
                "adverse_sel_bps@15": 1.0,
            }
        )
    for _ in range(20):
        rows.append(
            {
                "side": "ask",
                "quoted_half_spread_bps": 1.0,
                "half_spread_bps": 1.0,
                "adverse_sel_bps@15": 1.0,
            }
        )
    trials = _conditional_trials(rows)
    adverse = _conditional_adverse(trials, rows)

    scorecard = fill_sim_conditional_feature_scorecard(
        trials,
        adverse,
        horizons=(15,),
        span_hours=1.0,
        primary_horizon_s=15,
    )

    assert scorecard["status"] == "CONDITIONAL_FEATURE_POSITIVE_SAMPLE_GATED"
    assert scorecard["best_cell"]["net_bps"] == pytest.approx(1.0)
    assert scorecard["best_cell"]["n_fill_only"] >= 30
    assert any(
        cell["feature"] == "quoted_half_spread_bps"
        and cell["n_fill_only"] >= 30
        and cell["net_bps"] > 0
        for cell in scorecard["positive_cells_with_sample_gate"]
    )


def test_conditional_feature_scorecard_labels_tiny_positive_below_gate():
    rows = [
        {"side": "bid", "half_spread_bps": 6.0, "adverse_sel_bps@15": 1.0},
        {"side": "bid", "half_spread_bps": 6.0, "adverse_sel_bps@15": 1.0},
    ]
    rows.extend(
        {
            "side": "ask",
            "half_spread_bps": 1.0,
            "adverse_sel_bps@15": 1.0,
        }
        for _ in range(40)
    )
    trials = _conditional_trials(rows)
    adverse = _conditional_adverse(trials, rows)

    scorecard = fill_sim_conditional_feature_scorecard(
        trials,
        adverse,
        horizons=(15,),
        span_hours=1.0,
        primary_horizon_s=15,
    )

    assert scorecard["status"] == "CONDITIONAL_FEATURE_POSITIVE_BELOW_SAMPLE_GATE"
    assert scorecard["best_cell"]["name"] == "side=bid"
    assert scorecard["best_cell"]["n_fill_only"] == 2
    assert scorecard["positive_cells_with_sample_gate"] == []


def test_conditional_feature_scorecard_surfaces_no_positive_cells():
    rows = [
        {
            "side": "bid" if i % 2 == 0 else "ask",
            "quoted_half_spread_bps": 1.0 + (i % 3),
            "half_spread_bps": 1.0,
            "adverse_sel_bps@15": 1.2,
        }
        for i in range(50)
    ]
    trials = _conditional_trials(rows)
    adverse = _conditional_adverse(trials, rows)

    scorecard = fill_sim_conditional_feature_scorecard(
        trials,
        adverse,
        horizons=(15,),
        span_hours=1.0,
        primary_horizon_s=15,
    )

    assert scorecard["status"] == "NO_CONDITIONAL_FEATURE_POSITIVE_CELL"
    assert scorecard["positive_cells"] == []
    assert scorecard["best_cell"]["net_bps"] == pytest.approx(-4.2)


def test_walk_forward_feature_scorecard_confirms_holdout_positive_cell():
    rows = []
    for half in range(2):
        for i in range(35):
            rows.append(
                {
                    "side": "bid" if i % 2 == 0 else "ask",
                    "quoted_half_spread_bps": 6.0,
                    "half_spread_bps": 6.0,
                    "adverse_sel_bps@15": 1.0,
                }
            )
        for i in range(5):
            rows.append(
                {
                    "side": "bid" if i % 2 == 0 else "ask",
                    "quoted_half_spread_bps": 1.0,
                    "half_spread_bps": 1.0,
                    "adverse_sel_bps@15": 2.0,
                }
            )
    trials = _conditional_trials(rows)
    adverse = _conditional_adverse(trials, rows)

    scorecard = fill_sim_walk_forward_feature_scorecard(
        trials,
        adverse,
        horizons=(15,),
        span_hours=1.0,
        primary_horizon_s=15,
    )

    assert scorecard["status"] == "WALK_FORWARD_FEATURE_HOLDOUT_POSITIVE_SAMPLE_GATED"
    assert scorecard["best_holdout_confirmed_candidate"] is not None
    assert scorecard["best_holdout_confirmed_candidate"]["train"]["n_fill_only"] >= 30
    assert scorecard["best_holdout_confirmed_candidate"]["holdout"]["n_fill_only"] >= 30
    assert scorecard["best_holdout_confirmed_candidate"]["holdout"]["net_bps"] > 0
    assert scorecard["failure_summary"]["status"] == "HOLDOUT_CONFIRMED"
    assert scorecard["failure_summary"]["holdout_confirmed_count"] >= 1


def test_walk_forward_feature_scorecard_blocks_train_only_overfit():
    rows = []
    for i in range(35):
        rows.append(
            {
                "side": "bid" if i % 2 == 0 else "ask",
                "quoted_half_spread_bps": 6.0,
                "half_spread_bps": 6.0,
                "adverse_sel_bps@15": 1.0,
            }
        )
    for i in range(5):
        rows.append(
            {
                "side": "bid" if i % 2 == 0 else "ask",
                "quoted_half_spread_bps": 1.0,
                "half_spread_bps": 1.0,
                "adverse_sel_bps@15": 2.0,
            }
        )
    for i in range(35):
        rows.append(
            {
                "side": "bid" if i % 2 == 0 else "ask",
                "quoted_half_spread_bps": 6.0,
                "half_spread_bps": 1.0,
                "adverse_sel_bps@15": 2.0,
            }
        )
    for i in range(5):
        rows.append(
            {
                "side": "bid" if i % 2 == 0 else "ask",
                "quoted_half_spread_bps": 1.0,
                "half_spread_bps": 1.0,
                "adverse_sel_bps@15": 2.0,
            }
        )
    trials = _conditional_trials(rows)
    adverse = _conditional_adverse(trials, rows)

    scorecard = fill_sim_walk_forward_feature_scorecard(
        trials,
        adverse,
        horizons=(15,),
        span_hours=1.0,
        primary_horizon_s=15,
    )

    assert scorecard["status"] == "WALK_FORWARD_FEATURE_TRAIN_ONLY_POSITIVE"
    assert scorecard["train_positive_sample_gated_candidates"]
    assert scorecard["holdout_confirmed_candidates"] == []
    assert scorecard["best_train_candidate"]["train"]["net_bps"] > 0
    assert scorecard["best_train_candidate"]["holdout"]["net_bps"] < 0
    summary = scorecard["failure_summary"]
    assert summary["status"] == "TRAIN_POSITIVE_HOLDOUT_DECAY"
    assert summary["train_positive_sample_gated_count"] >= 1
    assert summary["holdout_confirmed_count"] == 0
    assert summary["best_train_candidate"]["train_net_bps"] > 0
    assert summary["best_train_candidate"]["holdout_net_bps"] < 0
    assert summary["best_train_candidate"]["train_to_holdout_net_decay_bps"] > 0


def test_walk_forward_feature_scorecard_does_not_peek_at_holdout_thresholds():
    rows = []
    for i in range(40):
        rows.append(
            {
                "side": "bid" if i % 2 == 0 else "ask",
                "quoted_half_spread_bps": 1.0,
                "half_spread_bps": 1.0,
                "adverse_sel_bps@15": 2.0,
            }
        )
    for i in range(40):
        rows.append(
            {
                "side": "bid" if i % 2 == 0 else "ask",
                "quoted_half_spread_bps": 6.0,
                "half_spread_bps": 6.0,
                "adverse_sel_bps@15": 1.0,
            }
        )
    trials = _conditional_trials(rows)
    adverse = _conditional_adverse(trials, rows)

    scorecard = fill_sim_walk_forward_feature_scorecard(
        trials,
        adverse,
        horizons=(15,),
        span_hours=1.0,
        primary_horizon_s=15,
    )

    assert scorecard["status"] == "NO_WALK_FORWARD_FEATURE_TRAIN_POSITIVE"
    assert scorecard["best_holdout_confirmed_candidate"] is None
    assert scorecard["holdout_confirmed_candidates"] == []
    assert scorecard["failure_summary"]["status"] == "NO_TRAIN_POSITIVE_CELL"


def test_low_friction_feature_enrichment_uses_strictly_prior_windows():
    t_place = pd.Timestamp("2026-01-01T00:00:20Z").value
    trials = pd.DataFrame(
        [
            {
                "symbol": "ABCUSDT",
                "side": "bid",
                "t_place": t_place,
                "q0": 12.0,
                "quoted_half_spread_bps": 2.0,
            },
            {
                "symbol": "ABCUSDT",
                "side": "ask",
                "t_place": t_place,
                "q0": 8.0,
                "quoted_half_spread_bps": 2.0,
            },
        ]
    )
    trades = pd.DataFrame(
        {
            "ts": pd.to_datetime(
                [
                    "2026-01-01T00:00:11Z",
                    "2026-01-01T00:00:15Z",
                    "2026-01-01T00:00:20Z",
                ],
                utc=True,
            ),
            "symbol": ["ABCUSDT", "ABCUSDT", "ABCUSDT"],
            "side": ["Buy", "Sell", "Buy"],
            "qty": [2.0, 1.0, 100.0],
        }
    )
    l1 = pd.DataFrame(
        {
            "ts": pd.to_datetime(
                [
                    "2026-01-01T00:00:09Z",
                    "2026-01-01T00:00:12Z",
                    "2026-01-01T00:00:18Z",
                    "2026-01-01T00:00:20Z",
                ],
                utc=True,
            ),
            "symbol": ["ABCUSDT"] * 4,
            "best_bid": [99.0, 99.5, 99.6, 100.0],
            "bid_size": [10.0, 11.0, 11.5, 50.0],
            "best_ask": [101.0, 101.0, 100.8, 101.0],
            "ask_size": [9.0, 8.5, 8.2, 60.0],
            "update_id": [1, 2, 3, 4],
        }
    )

    enriched = add_low_friction_microstructure_features(trials, trades, l1, lookbacks_s=(10,))

    assert enriched.at[0, "recent_trade_count_10s"] == pytest.approx(2.0)
    assert enriched.at[0, "recent_trade_abs_qty_10s"] == pytest.approx(3.0)
    assert enriched.at[0, "recent_trade_imbalance_10s"] == pytest.approx(1.0 / 3.0)
    assert enriched.at[0, "side_recent_trade_imbalance_10s"] == pytest.approx(1.0 / 3.0)
    assert enriched.at[1, "side_recent_trade_imbalance_10s"] == pytest.approx(-1.0 / 3.0)
    assert enriched.at[0, "recent_l1_update_count_10s"] == pytest.approx(2.0)
    assert enriched.at[0, "side_touch_size_delta_frac_10s"] == pytest.approx(0.2)
    assert enriched.at[1, "side_touch_size_delta_frac_10s"] == pytest.approx(-1.0 / 9.0)


def test_low_friction_signal_scorecard_confirms_holdout_current_fee_cell():
    rows = []
    for _half in range(2):
        for _ in range(32):
            rows.append(
                {
                    "symbol": "ABCUSDT",
                    "side": "bid",
                    "outcome": "fill",
                    "quoted_half_spread_bps": 6.0,
                    "side_recent_trade_imbalance_10s": 1.0,
                    "recent_trade_count_10s": 1.0,
                    "recent_l1_update_count_10s": 1.0,
                    "side_touch_size_delta_frac_10s": 0.2,
                    "spread_bps_delta_10s": 0.5,
                    "half_spread_bps": 6.0,
                    "adverse_sel_bps@15": 1.0,
                }
            )
        for _ in range(8):
            rows.append(
                {
                    "symbol": "ABCUSDT",
                    "side": "bid",
                    "outcome": "fill",
                    "quoted_half_spread_bps": 1.0,
                    "side_recent_trade_imbalance_10s": -1.0,
                    "recent_trade_count_10s": 5.0,
                    "recent_l1_update_count_10s": 5.0,
                    "side_touch_size_delta_frac_10s": -0.2,
                    "spread_bps_delta_10s": -0.5,
                    "half_spread_bps": 1.0,
                    "adverse_sel_bps@15": 1.0,
                }
            )
    trials = _conditional_trials(rows)
    for col in (
        "side_recent_trade_imbalance_10s",
        "recent_trade_count_10s",
        "recent_l1_update_count_10s",
        "side_touch_size_delta_frac_10s",
        "spread_bps_delta_10s",
    ):
        trials[col] = [row[col] for row in rows]
    adverse = _conditional_adverse(trials, rows)

    scorecard = fill_sim_low_friction_signal_scorecard(
        trials,
        adverse,
        horizons=(15,),
        span_hours=1.0,
        primary_horizon_s=15,
    )

    assert scorecard["status"] == "LOW_FRICTION_SIGNAL_HOLDOUT_CURRENT_FEE_SAMPLE_GATED"
    assert scorecard["best_holdout_current_fee_candidate"] is not None
    assert scorecard["best_holdout_current_fee_candidate"]["holdout"]["edge_before_fees_bps"] >= 4.0
    assert scorecard["best_holdout_current_fee_candidate"]["holdout"]["n_fill_only"] >= 30
    train_confirmed = scorecard["train_confirmed_gross_scorecard"]
    assert train_confirmed["status"] == (
        "LOW_FRICTION_TRAIN_CONFIRMED_GROSS_CLEARS_CURRENT_FEE"
    )
    assert train_confirmed["current_fee_confirmed_count"] >= 1
    assert train_confirmed["best_min_train_holdout_gross_bps"] >= 4.0
    assert scorecard["best_train_confirmed_gross_candidate"][
        "min_train_holdout_gross_bps"
    ] >= 4.0
    assert scorecard["failure_summary"]["holdout_confirmed_current_fee_count"] >= 1


def test_low_friction_signal_scorecard_ranks_train_confirmed_gross_below_fee_wall():
    rows = []
    for _half in range(2):
        for _ in range(34):
            rows.append(
                {
                    "symbol": "ABCUSDT",
                    "side": "bid",
                    "outcome": "fill",
                    "quoted_half_spread_bps": 6.0,
                    "side_recent_trade_imbalance_10s": 1.0,
                    "recent_trade_count_10s": 1.0,
                    "recent_l1_update_count_10s": 1.0,
                    "side_touch_size_delta_frac_10s": 0.2,
                    "spread_bps_delta_10s": 0.5,
                    "half_spread_bps": 2.0,
                    "adverse_sel_bps@15": 1.0,
                }
            )
        for _ in range(8):
            rows.append(
                {
                    "symbol": "ABCUSDT",
                    "side": "bid",
                    "outcome": "fill",
                    "quoted_half_spread_bps": 1.0,
                    "side_recent_trade_imbalance_10s": -1.0,
                    "recent_trade_count_10s": 5.0,
                    "recent_l1_update_count_10s": 5.0,
                    "side_touch_size_delta_frac_10s": -0.2,
                    "spread_bps_delta_10s": -0.5,
                    "half_spread_bps": 0.6,
                    "adverse_sel_bps@15": 1.0,
                }
            )
    trials = _conditional_trials(rows)
    for col in (
        "side_recent_trade_imbalance_10s",
        "recent_trade_count_10s",
        "recent_l1_update_count_10s",
        "side_touch_size_delta_frac_10s",
        "spread_bps_delta_10s",
    ):
        trials[col] = [row[col] for row in rows]
    adverse = _conditional_adverse(trials, rows)

    scorecard = fill_sim_low_friction_signal_scorecard(
        trials,
        adverse,
        horizons=(15,),
        span_hours=1.0,
        primary_horizon_s=15,
    )

    assert scorecard["status"] == "LOW_FRICTION_SIGNAL_HOLDOUT_GROSS_POSITIVE_BELOW_CURRENT_FEE"
    train_confirmed = scorecard["train_confirmed_gross_scorecard"]
    assert train_confirmed["status"] == (
        "LOW_FRICTION_TRAIN_CONFIRMED_GROSS_BELOW_CURRENT_FEE"
    )
    assert train_confirmed["train_confirmed_positive_gross_count"] >= 1
    assert train_confirmed["current_fee_confirmed_count"] == 0
    assert train_confirmed["best_min_train_holdout_gross_bps"] == pytest.approx(1.0)
    assert train_confirmed["gap_to_current_fee_round_trip_bps"] == pytest.approx(3.0)
    best = scorecard["best_train_confirmed_gross_candidate"]
    assert best["train_sample_gated_positive_gross"] is True
    assert best["holdout_sample_gated_positive_gross"] is True


def test_low_friction_interaction_finds_train_confirmed_current_fee_cell():
    rows = []
    for _half in range(2):
        for spread, count, touch, half_spread in (
            (6.0, 0.0, 1.0, 6.0),   # 只有三條件交集能過 fee
            (6.0, 0.0, -1.0, 2.0),  # spread + quiet 仍低於 fee
            (6.0, 10.0, 1.0, 2.0),  # spread + touch 仍低於 fee
            (1.0, 10.0, -1.0, 0.5),
        ):
            for _ in range(32):
                rows.append(
                    {
                        "symbol": "ABCUSDT",
                        "side": "bid",
                        "outcome": "fill",
                        "quoted_half_spread_bps": spread,
                        "side_recent_trade_imbalance_10s": touch,
                        "recent_trade_count_10s": count,
                        "recent_l1_update_count_10s": count,
                        "recent_l1_update_intensity_10s": count / 10.0,
                        "side_touch_size_delta_frac_10s": touch,
                        "spread_bps_delta_10s": touch,
                        "half_spread_bps": half_spread,
                        "adverse_sel_bps@15": 1.0,
                    }
                )
    trials = _conditional_trials(rows)
    for col in (
        "side_recent_trade_imbalance_10s",
        "recent_trade_count_10s",
        "recent_l1_update_count_10s",
        "recent_l1_update_intensity_10s",
        "side_touch_size_delta_frac_10s",
        "spread_bps_delta_10s",
    ):
        trials[col] = [row[col] for row in rows]
    adverse = _conditional_adverse(trials, rows)

    scorecard = fill_sim_low_friction_signal_scorecard(
        trials,
        adverse,
        horizons=(15,),
        span_hours=1.0,
        primary_horizon_s=15,
    )

    assert scorecard["interaction_candidates_evaluated"] > 0
    train_confirmed = scorecard["train_confirmed_gross_scorecard"]
    assert train_confirmed["status"] == (
        "LOW_FRICTION_TRAIN_CONFIRMED_GROSS_CLEARS_CURRENT_FEE"
    )
    best = scorecard["best_train_confirmed_gross_candidate"]
    assert best["feature"] == "low_friction_interaction"
    assert best["candidate_shape"] == "spread_quiet_touch_interaction_v1"
    assert best["min_train_holdout_gross_bps"] >= 4.0
    assert train_confirmed["current_fee_confirmed_count"] >= 1


def test_low_friction_interaction_uses_recent_trade_abs_qty_as_quiet_tape():
    rows = []
    for _half in range(2):
        for spread, abs_qty, touch, half_spread in (
            (6.0, 0.1, 1.0, 7.0),    # only this three-way cell clears current fee
            (6.0, 0.1, -1.0, 1.0),   # spread + quiet abs qty stays below fee
            (6.0, 10.0, 1.0, 1.0),   # spread + favorable touch stays below fee
            (1.0, 0.1, 1.0, 1.0),    # quiet abs qty + favorable touch stays below fee
        ):
            for _ in range(32):
                rows.append(
                    {
                        "symbol": "ABCUSDT",
                        "side": "bid",
                        "outcome": "fill",
                        "quoted_half_spread_bps": spread,
                        "recent_trade_abs_qty_10s": abs_qty,
                        "recent_trade_count_10s": 2.0,
                        "recent_l1_update_count_10s": 2.0,
                        "recent_l1_update_intensity_10s": 0.2,
                        "side_recent_trade_imbalance_10s": touch,
                        "side_touch_size_delta_frac_10s": touch,
                        "spread_bps_delta_10s": touch,
                        "half_spread_bps": half_spread,
                        "adverse_sel_bps@15": 1.0,
                    }
                )
    trials = _conditional_trials(rows)
    for col in (
        "recent_trade_abs_qty_10s",
        "recent_trade_count_10s",
        "recent_l1_update_count_10s",
        "recent_l1_update_intensity_10s",
        "side_recent_trade_imbalance_10s",
        "side_touch_size_delta_frac_10s",
        "spread_bps_delta_10s",
    ):
        trials[col] = [row[col] for row in rows]
    adverse = _conditional_adverse(trials, rows)

    scorecard = fill_sim_low_friction_signal_scorecard(
        trials,
        adverse,
        horizons=(15,),
        span_hours=1.0,
        primary_horizon_s=15,
    )

    train_confirmed = scorecard["train_confirmed_gross_scorecard"]
    assert train_confirmed["status"] == (
        "LOW_FRICTION_TRAIN_CONFIRMED_GROSS_CLEARS_CURRENT_FEE"
    )
    best = scorecard["best_train_confirmed_gross_candidate"]
    assert best["feature"] == "low_friction_interaction"
    assert best["candidate_shape"] == "spread_quiet_abs_qty_interaction_v1"
    assert "recent_trade_abs_qty_10s" in best["name"]
    assert best["min_train_holdout_gross_bps"] >= 4.0


def test_low_friction_interaction_uses_median_quiet_l1_to_restore_sample_gate():
    rows = []
    for _half in range(2):
        for spread, l1_count, touch, half_spread, repeats in (
            (6.0, 0.0, 1.0, 2.0, 64),    # p25/p10 quiet is sample-rich but below fee
            (6.0, 4.0, 1.0, 9.0, 64),    # p50 quiet is needed to clear fee with sample gate
            (6.0, 10.0, 1.0, 0.0, 32),   # spread + touch alone stays below fee
            (1.0, 4.0, 1.0, 1.0, 32),    # quiet + touch alone stays below fee
            (6.0, 4.0, -1.0, 0.0, 64),   # spread + p50 quiet alone stays below fee
        ):
            for _ in range(repeats):
                rows.append(
                    {
                        "symbol": "ABCUSDT",
                        "side": "bid",
                        "outcome": "fill",
                        "quoted_half_spread_bps": spread,
                        "recent_trade_abs_qty_10s": 99.0,
                        "recent_trade_count_10s": 99.0,
                        "recent_l1_update_count_10s": l1_count,
                        "recent_l1_update_intensity_10s": l1_count / 10.0,
                        "side_recent_trade_imbalance_10s": touch,
                        "side_touch_size_delta_frac_10s": touch,
                        "spread_bps_delta_10s": touch,
                        "half_spread_bps": half_spread,
                        "adverse_sel_bps@15": 1.0,
                    }
                )
    trials = _conditional_trials(rows)
    for col in (
        "recent_trade_abs_qty_10s",
        "recent_trade_count_10s",
        "recent_l1_update_count_10s",
        "recent_l1_update_intensity_10s",
        "side_recent_trade_imbalance_10s",
        "side_touch_size_delta_frac_10s",
        "spread_bps_delta_10s",
    ):
        trials[col] = [row[col] for row in rows]
    adverse = _conditional_adverse(trials, rows)

    scorecard = fill_sim_low_friction_signal_scorecard(
        trials,
        adverse,
        horizons=(15,),
        span_hours=1.0,
        primary_horizon_s=15,
    )

    train_confirmed = scorecard["train_confirmed_gross_scorecard"]
    assert train_confirmed["status"] == (
        "LOW_FRICTION_TRAIN_CONFIRMED_GROSS_CLEARS_CURRENT_FEE"
    )
    best = scorecard["best_train_confirmed_gross_candidate"]
    assert best["feature"] == "low_friction_interaction"
    assert best["candidate_shape"] == "spread_quiet_touch_interaction_v1"
    assert "recent_l1_update_count_10s_train_p50" in best["name"]
    assert best["min_train_holdout_gross_bps"] >= 4.0


def test_low_friction_interaction_uses_book_imbalance_support():
    rows = []
    for _half in range(2):
        for spread, trade_count, book_imb, half_spread in (
            (6.0, 0.0, 1.0, 8.0),    # only spread + quiet + book support clears fee
            (6.0, 10.0, 1.0, 0.0),   # spread + book support alone stays below fee
            (6.0, 0.0, -1.0, 0.0),   # spread + quiet alone stays below fee
            (1.0, 0.0, 1.0, 0.0),    # quiet + book support alone stays below fee
        ):
            for _ in range(32):
                rows.append(
                    {
                        "symbol": "ABCUSDT",
                        "side": "bid",
                        "outcome": "fill",
                        "quoted_half_spread_bps": spread,
                        "recent_trade_count_10s": trade_count,
                        "recent_l1_update_count_10s": trade_count,
                        "recent_l1_update_intensity_10s": trade_count / 10.0,
                        "side_book_imb": book_imb,
                        "side_recent_trade_imbalance_10s": -1.0,
                        "side_touch_size_delta_frac_10s": -1.0,
                        "spread_bps_delta_10s": -1.0,
                        "half_spread_bps": half_spread,
                        "adverse_sel_bps@15": 1.0,
                    }
                )
    trials = _conditional_trials(rows)
    for col in (
        "recent_trade_count_10s",
        "recent_l1_update_count_10s",
        "recent_l1_update_intensity_10s",
        "side_book_imb",
        "side_recent_trade_imbalance_10s",
        "side_touch_size_delta_frac_10s",
        "spread_bps_delta_10s",
    ):
        trials[col] = [row[col] for row in rows]
    adverse = _conditional_adverse(trials, rows)

    scorecard = fill_sim_low_friction_signal_scorecard(
        trials,
        adverse,
        horizons=(15,),
        span_hours=1.0,
        primary_horizon_s=15,
    )

    train_confirmed = scorecard["train_confirmed_gross_scorecard"]
    assert train_confirmed["status"] == (
        "LOW_FRICTION_TRAIN_CONFIRMED_GROSS_CLEARS_CURRENT_FEE"
    )
    assert scorecard["interaction_candidate_shape_counts"][
        "spread_quiet_book_imbalance_interaction_v1"
    ] > 0
    best = scorecard["best_train_confirmed_gross_candidate"]
    assert best["feature"] == "low_friction_interaction"
    assert best["candidate_shape"] == "spread_quiet_book_imbalance_interaction_v1"
    assert "side_book_imb_train_p75" in best["name"]
    assert best["min_train_holdout_gross_bps"] >= 4.0


def test_maker_fee_sensitivity_finds_lower_fee_sample_gated_path():
    report = {
        "edge_scorecard": {
            "all_fill_only_cells": [
                {
                    "scope": "per_symbol_primary_queue",
                    "symbol": "ABCUSDT",
                    "queue_position": "back",
                    "policy": "naive",
                    "track": "fill_only",
                    "n": 40,
                    "edge_before_fees_bps": 1.2,
                    "signif_suppressed": False,
                }
            ]
        },
        "conditional_feature_scorecard": {"all_cells": []},
    }

    scorecard = fill_sim_maker_fee_sensitivity_scorecard(
        report,
        primary_horizon_s=15,
        fee_scenarios_bps_per_side=(2.0, 0.5, 0.0),
    )

    assert scorecard["status"] == "LOWER_FEE_SAMPLE_GATED_POSITIVE"
    assert scorecard["best_sample_gated_break_even_cell"]["symbol"] == "ABCUSDT"
    assert scorecard["best_sample_gated_break_even_cell"][
        "break_even_maker_fee_bps_per_side"
    ] == pytest.approx(0.6)
    assert scorecard["best_sample_gated_break_even_cell"][
        "fee_reduction_to_breakeven_bps_per_side"
    ] == pytest.approx(1.4)
    assert scorecard["scenarios"][0]["positive_sample_gate_count"] == 0
    assert scorecard["scenarios"][1]["positive_sample_gate_count"] == 1
    assert scorecard["scenarios"][1]["best_cell"]["net_bps_at_fee"] == pytest.approx(0.2)


def test_maker_fee_sensitivity_includes_walk_forward_holdout_cells():
    report = {
        "edge_scorecard": {"all_fill_only_cells": []},
        "conditional_feature_scorecard": {"all_cells": []},
        "walk_forward_feature_scorecard": {
            "holdout_confirmed_candidates": [
                {
                    "holdout": {
                        "name": "quoted_half_spread_train_p75_ge",
                        "condition": "quoted_half_spread_bps >= train_p75(6)",
                        "n_fill_only": 35,
                        "edge_before_fees_bps": 2.4,
                        "signif_suppressed": False,
                    }
                }
            ]
        },
    }

    scorecard = fill_sim_maker_fee_sensitivity_scorecard(
        report,
        primary_horizon_s=15,
        fee_scenarios_bps_per_side=(2.0, 1.0),
    )

    best = scorecard["best_sample_gated_break_even_cell"]
    assert best["source"] == "walk_forward_feature_scorecard_holdout"
    assert best["break_even_maker_fee_bps_per_side"] == pytest.approx(1.2)
    assert scorecard["scenarios"][1]["positive_sample_gate_count"] == 1


def test_maker_fee_sensitivity_includes_low_friction_holdout_cells():
    report = {
        "edge_scorecard": {"all_fill_only_cells": []},
        "conditional_feature_scorecard": {"all_cells": []},
        "walk_forward_feature_scorecard": {"holdout_confirmed_candidates": []},
        "low_friction_signal_scorecard": {
            "top_holdout_gross_candidates": [
                {
                    "holdout": {
                        "name": "recent_trade_count_10s_train_p25_le",
                        "condition": "recent_trade_count_10s <= train_p25",
                        "feature": "recent_trade_count_10s",
                        "n_fill_only": 35,
                        "edge_before_fees_bps": 2.6,
                        "signif_suppressed": False,
                    }
                }
            ]
        },
    }

    scorecard = fill_sim_maker_fee_sensitivity_scorecard(
        report,
        primary_horizon_s=15,
        fee_scenarios_bps_per_side=(2.0, 1.0),
    )

    best = scorecard["best_sample_gated_break_even_cell"]
    assert best["source"] == "low_friction_signal_scorecard_holdout"
    assert best["break_even_maker_fee_bps_per_side"] == pytest.approx(1.3)
    assert scorecard["scenarios"][1]["positive_sample_gate_count"] == 1


def test_maker_fee_sensitivity_keeps_tiny_positive_below_gate():
    report = {
        "edge_scorecard": {"all_fill_only_cells": []},
        "conditional_feature_scorecard": {
            "all_cells": [
                {
                    "name": "tiny_positive",
                    "condition": "side == bid",
                    "n_fill_only": 2,
                    "edge_before_fees_bps": 2.0,
                    "signif_suppressed": True,
                }
            ]
        },
    }

    scorecard = fill_sim_maker_fee_sensitivity_scorecard(
        report,
        primary_horizon_s=15,
        fee_scenarios_bps_per_side=(2.0, 0.5, 0.0),
    )

    assert scorecard["status"] == "FEE_SCENARIO_POSITIVE_BELOW_SAMPLE_GATE"
    assert scorecard["scenarios"][2]["positive_cell_count"] == 1
    assert scorecard["scenarios"][2]["positive_sample_gate_count"] == 0


def test_maker_fee_sensitivity_surfaces_no_positive_cells():
    report = {
        "edge_scorecard": {
            "all_fill_only_cells": [
                {
                    "scope": "pooled_primary_queue",
                    "queue_position": "back",
                    "policy": "naive",
                    "track": "fill_only",
                    "n": 40,
                    "edge_before_fees_bps": -2.0,
                    "signif_suppressed": False,
                }
            ]
        },
        "conditional_feature_scorecard": {"all_cells": []},
    }

    scorecard = fill_sim_maker_fee_sensitivity_scorecard(
        report,
        primary_horizon_s=15,
        fee_scenarios_bps_per_side=(2.0, 0.0, -0.5),
    )

    assert scorecard["status"] == "NO_FEE_SCENARIO_POSITIVE_CELL"
    assert scorecard["best_sample_gated_break_even_cell"][
        "break_even_maker_fee_bps_per_side"
    ] == pytest.approx(-1.0)
    assert scorecard["scenarios"][2]["best_cell"]["net_bps_at_fee"] == pytest.approx(-1.0)
