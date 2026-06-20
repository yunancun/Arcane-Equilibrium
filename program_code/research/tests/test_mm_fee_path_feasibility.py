from program_code.research.microstructure.fee_path import (
    build_maker_fee_path_feasibility_scorecard,
)


def _fee_scorecard(break_even: float = 1.028) -> dict:
    return {
        "status": "LOWER_FEE_SAMPLE_GATED_POSITIVE",
        "best_sample_gated_break_even_cell": {
            "source": "conditional_feature_scorecard",
            "name": "quoted_half_spread_bps_p75_and_side_book_imb_p75",
            "condition": "quoted_half_spread_bps p75 AND side_book_imb p75",
            "n_fill_only": 116,
            "edge_before_fees_bps": 2.057,
            "break_even_maker_fee_bps_per_side": break_even,
        },
    }


def test_fee_path_finds_first_standard_vip_tier_that_clears_break_even():
    scorecard = build_maker_fee_path_feasibility_scorecard(
        _fee_scorecard(),
        {
            "fills": 1529,
            "notional_usd": 840_299.41,
            "maker_fills": 830,
            "maker_notional_usd": 477_049.36,
            "by_engine_mode": {"demo": {"notional_usd": 817_578.33}},
        },
    )

    assert scorecard["status"] == "STANDARD_VIP_TIER_CAN_CLEAR_BUT_SCALE_OR_CAPITAL_GATED"
    assert scorecard["break_even_maker_fee_bps_per_side"] == 1.028
    assert scorecard["fee_reduction_needed_bps_per_side"] == 0.972
    first = scorecard["first_standard_vip_tier_clearing_break_even"]
    assert first["tier"] == "VIP5"
    assert first["maker_fee_bps_per_side"] == 1.0
    assert first["volume_30d"]["threshold_usd"] == 250_000_000.0
    assert first["volume_30d"]["multiplier_needed"] == 297.513
    assert first["asset_balance"]["threshold_usd"] == 2_000_000.0


def test_fee_path_reports_current_fee_clear_when_break_even_above_current_fee():
    scorecard = build_maker_fee_path_feasibility_scorecard(
        _fee_scorecard(break_even=2.2),
        {"notional_usd": 1000.0, "maker_notional_usd": 500.0},
    )

    assert scorecard["status"] == "CURRENT_ACCOUNT_FEE_CLEARS_BREAK_EVEN"
    assert scorecard["first_standard_vip_tier_clearing_break_even"]["tier"] == "VIP1"
    assert scorecard["fee_reduction_needed_bps_per_side"] == 0.0


def test_fee_path_preserves_no_break_even_cell_status():
    scorecard = build_maker_fee_path_feasibility_scorecard(
        {"status": "NO_FEE_SCENARIO_POSITIVE_CELL"},
        {"notional_usd": 0.0},
    )

    assert scorecard["status"] == "NO_SAMPLE_GATED_BREAK_EVEN_CELL"
    assert scorecard["first_standard_vip_tier_clearing_break_even"] is None
    assert scorecard["break_even_maker_fee_bps_per_side"] is None
