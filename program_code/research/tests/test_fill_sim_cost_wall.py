from __future__ import annotations

import pandas as pd
import pytest

from program_code.research.microstructure.fill_sim import _net_block


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
