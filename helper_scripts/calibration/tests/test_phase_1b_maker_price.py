"""
測試 phase_1b_maker_price module — Rust port to Python 1:1 對應 maker_price.rs:159-226 + 252-352。

為什麼這些 test：直接對應 Rust source `mod tests`（行 377-662）的 test
case；任何浮點 mismatch 即 port 失敗。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase_1b_maker_price import (  # noqa: E402
    CLOSE_MAKER_SPREAD_GUARD_BPS_DEFAULT,
    FEE_SAVING_CAP_BPS,
    CloseMakerPricePolicy,
    MakerPriceInputs,
    compute_adverse_selection_proxy_bps,
    compute_close_limit_price,
    compute_fee_saving_bps,
    compute_post_only_price,
)


def _inputs_with_bbo(last, bid, ask, tick):
    return MakerPriceInputs(last_price=last, best_bid=bid, best_ask=ask, tick_size=tick)


def _inputs_no_bbo(last, tick):
    return MakerPriceInputs(last_price=last, best_bid=None, best_ask=None, tick_size=tick)


# ---- 對應 Rust maker_price.rs buy_uses_best_bid_minus_buffer_ticks ----
def test_buy_uses_best_bid_minus_buffer_ticks():
    inputs = _inputs_with_bbo(30_000.0, 29_999.0, 30_001.0, 0.1)
    price = compute_post_only_price(
        is_long=True, inputs=inputs, fallback_offset_bps=1.0, buffer_ticks=1,
    )
    assert price is not None
    assert abs(price - 29_998.9) < 1e-9


# ---- sell_uses_best_ask_plus_buffer_ticks ----
def test_sell_uses_best_ask_plus_buffer_ticks():
    inputs = _inputs_with_bbo(30_000.0, 29_999.0, 30_001.0, 0.1)
    price = compute_post_only_price(
        is_long=False, inputs=inputs, fallback_offset_bps=1.0, buffer_ticks=1,
    )
    assert price is not None
    assert abs(price - 30_001.1) < 1e-9


# ---- buffer_zero_sits_on_inside_quote ----
def test_buffer_zero_sits_on_inside_quote():
    inputs = _inputs_with_bbo(30_000.0, 29_999.0, 30_001.0, 0.1)
    buy = compute_post_only_price(True, inputs, 1.0, 0)
    sell = compute_post_only_price(False, inputs, 1.0, 0)
    assert buy is not None and abs(buy - 29_999.0) < 1e-9
    assert sell is not None and abs(sell - 30_001.0) < 1e-9


# ---- skip_when_no_bbo ----
def test_skip_when_no_bbo():
    inputs = _inputs_no_bbo(30_000.0, 0.1)
    assert compute_post_only_price(True, inputs, 1.0, 1) is None
    assert compute_post_only_price(False, inputs, 1.0, 1) is None


# ---- skip_when_only_tick_size_missing ----
def test_skip_when_only_tick_size_missing():
    inputs = MakerPriceInputs(
        last_price=30_000.0,
        best_bid=29_999.0,
        best_ask=30_001.0,
        tick_size=None,
    )
    assert compute_post_only_price(True, inputs, 1.0, 1) is None


# ---- buy_uses_single_sided_bid ----
def test_buy_uses_single_sided_bid():
    inputs = MakerPriceInputs(
        last_price=30_000.0,
        best_bid=29_999.0,
        best_ask=None,
        tick_size=0.1,
    )
    price = compute_post_only_price(True, inputs, 1.0, 1)
    assert price is not None and abs(price - 29_998.9) < 1e-9


# ---- buy_uses_single_sided_ask_minus_at_least_one_tick (buffer_ticks=0) ----
def test_buy_uses_single_sided_ask_minus_at_least_one_tick():
    inputs = MakerPriceInputs(
        last_price=30_000.0,
        best_bid=None,
        best_ask=30_001.0,
        tick_size=0.1,
    )
    price = compute_post_only_price(True, inputs, 1.0, 0)
    # buffer_ticks=0 → cross_buffer=tick=0.1 → 30001.0 - 0.1 = 30000.9
    assert price is not None and abs(price - 30_000.9) < 1e-9


# ---- skip_when_crossed_book ----
def test_skip_when_crossed_book():
    inputs = _inputs_with_bbo(30_000.0, 30_002.0, 30_001.0, 0.1)
    assert compute_post_only_price(True, inputs, 1.0, 1) is None


# ---- skip_when_buffer_pushes_price_negative ----
def test_skip_when_buffer_pushes_price_negative():
    inputs = _inputs_with_bbo(0.5, 0.5, 0.6, 1.0)
    assert compute_post_only_price(True, inputs, 1.0, 10) is None


# ---- close_limit_price_inverts_direction_and_uses_timeout_policy ----
def test_close_limit_price_long_close_sells_passively():
    inputs = _inputs_with_bbo(30_000.0, 29_999.0, 30_001.0, 0.1)
    policy = CloseMakerPricePolicy(buffer_ticks=1, offset_bps=0.5, timeout_ms=30_000)
    long_close_sell = compute_close_limit_price(
        position_is_long=True, inputs=inputs, policy=policy,
    )
    # long close → sell → ask + buffer = 30001.0 + (1 buffer + tick widen if half_spread > 1)
    # half_spread = 1.0, tick=0.1 → required_ticks = ceil(1.0/0.1)=10 → buffer 升到 10
    # → 30001.0 + 10*0.1 = 30002.0
    assert long_close_sell is not None and abs(long_close_sell - 30_002.0) < 1e-9


def test_close_limit_price_short_close_buys_passively():
    inputs = _inputs_with_bbo(30_000.0, 29_999.0, 30_001.0, 0.1)
    policy = CloseMakerPricePolicy(buffer_ticks=1, offset_bps=0.5, timeout_ms=30_000)
    short_close_buy = compute_close_limit_price(
        position_is_long=False, inputs=inputs, policy=policy,
    )
    # short close → buy → bid - buffer (widened) = 29999.0 - 10*0.1 = 29998.0
    assert short_close_buy is not None and abs(short_close_buy - 29_998.0) < 1e-9


# ---- close_limit_price_spread_guard_strict_skips ----
def test_close_limit_price_spread_guard_strict_skips():
    # bid=99, ask=100, mid=99.5, spread = 1/99.5 * 10000 ≈ 100.5 bps > 50 guard
    inputs = _inputs_with_bbo(100.0, 99.0, 100.0, 0.1)
    policy = CloseMakerPricePolicy(buffer_ticks=1, offset_bps=0.5, timeout_ms=30_000)
    price = compute_close_limit_price(
        position_is_long=True, inputs=inputs, policy=policy,
        spread_guard_bps=CLOSE_MAKER_SPREAD_GUARD_BPS_DEFAULT,
    )
    assert price is None


def test_close_limit_price_spread_guard_dynamic_override():
    """Block 4 D-axis sweep: spread_guard_bps 可 override default 50."""
    # bid=29999, ask=30001 → spread_bps = 2/30000 * 10000 ≈ 0.67 bps
    inputs = _inputs_with_bbo(30_000.0, 29_999.0, 30_001.0, 0.1)
    policy = CloseMakerPricePolicy(buffer_ticks=1, offset_bps=0.5, timeout_ms=30_000)
    # spread_guard=25 should still permit since 0.67 < 25
    price = compute_close_limit_price(
        position_is_long=True, inputs=inputs, policy=policy,
        spread_guard_bps=25.0,
    )
    assert price is not None


def test_close_limit_price_spread_guard_25_blocks_wide_spread():
    # bid=99.9, ask=100.1 → spread = 0.2/100 * 10000 = 20 bps
    # spread_guard=25 → pass; spread_guard=10 → block
    inputs = _inputs_with_bbo(100.0, 99.9, 100.1, 0.1)
    policy = CloseMakerPricePolicy(buffer_ticks=1, offset_bps=0.5, timeout_ms=30_000)
    assert compute_close_limit_price(
        position_is_long=True, inputs=inputs, policy=policy,
        spread_guard_bps=25.0,
    ) is not None
    assert compute_close_limit_price(
        position_is_long=True, inputs=inputs, policy=policy,
        spread_guard_bps=10.0,
    ) is None


# ---- fee_saving_bps ----
def test_fee_saving_no_slippage_caps_at_3_5_bps():
    # sell at exact actual_taker_px → no slippage cost → 3.5 bps saving
    saving = compute_fee_saving_bps(
        simulated_fill_px=100.0,
        actual_taker_px=100.0,
        position_is_long=True,
    )
    assert abs(saving - FEE_SAVING_CAP_BPS) < 1e-9


def test_fee_saving_with_slippage_reduces():
    # close long (sell) simulated at 99.5, actual taker 100.0 → slippage = +50 bps
    # → fee_saving = 3.5 - 50 = -46.5 bps
    saving = compute_fee_saving_bps(
        simulated_fill_px=99.5,
        actual_taker_px=100.0,
        position_is_long=True,
    )
    assert saving < 0
    assert abs(saving - (3.5 - 50.0)) < 1e-9


def test_fee_saving_buy_close_with_negative_slippage_caps_at_3_5():
    # close short (buy) simulated at 99.5, actual taker 100.0
    # buy: lower fill is better; slippage_raw = (99.5 - 100) / 100 * 10000 = -50
    # max(0, -50) = 0 → no cost → cap at 3.5
    saving = compute_fee_saving_bps(
        simulated_fill_px=99.5,
        actual_taker_px=100.0,
        position_is_long=False,
    )
    assert abs(saving - FEE_SAVING_CAP_BPS) < 1e-9


# ---- adverse_selection_proxy ----
def test_adverse_proxy_sell_close_market_up_is_positive():
    """sell close fill at 100, mid 60s later = 101 → adverse = +100 bps."""
    proxy = compute_adverse_selection_proxy_bps(
        mid_at_fill_plus_60s=101.0,
        simulated_fill_px=100.0,
        position_is_long=True,
    )
    assert proxy is not None and abs(proxy - 100.0) < 1e-9


def test_adverse_proxy_buy_close_market_down_is_positive():
    """buy close fill at 100, mid 60s later = 99 → adverse = +100 bps (對齊 spec semantic)."""
    proxy = compute_adverse_selection_proxy_bps(
        mid_at_fill_plus_60s=99.0,
        simulated_fill_px=100.0,
        position_is_long=False,
    )
    assert proxy is not None and abs(proxy - 100.0) < 1e-9


def test_adverse_proxy_none_when_no_mid():
    proxy = compute_adverse_selection_proxy_bps(
        mid_at_fill_plus_60s=None,
        simulated_fill_px=100.0,
        position_is_long=True,
    )
    assert proxy is None
