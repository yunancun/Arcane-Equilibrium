from __future__ import annotations

import pandas as pd
import pytest

from program_code.research.microstructure.fill_sim import _net_block, fill_sim_edge_scorecard


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
