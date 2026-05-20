"""
測試 phase_1b_sweep_replay module — per-cell simulation engine。

為什麼用 fixture 而非 PG：unit test 必 deterministic + 無 IO；
PG integration 留給 smoke test（手動跑）。
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase_1b_sweep_cells import CalibrationCell  # noqa: E402
from phase_1b_tick_loader import (  # noqa: E402
    FillReplaySeed,
    OrderbookDepthWindow,
    TickSample,
    TickWindow,
    DATA_SOURCE_TAG,
)
from phase_1b_queue_adjustment import (  # noqa: E402
    QueueDepthSample,
    DEFAULT_QUEUE_WEIGHT,
)
from phase_1b_sweep_replay import (  # noqa: E402
    simulate_cell,
    simulate_cell_against_fill,
)


def _make_seed(
    order_id="test_order",
    symbol="BTCUSDT",
    side="Buy",  # close BUY = close short
    exit_reason="grid_close_short",
    price=100.0,
    ts=None,
    seed_source="post_restart",
) -> FillReplaySeed:
    return FillReplaySeed(
        order_id=order_id,
        link_id=None,
        symbol=symbol,
        side=side,
        exit_reason=exit_reason,
        qty=1.0,
        price=price,
        ts=ts or datetime(2026, 5, 18, 0, 0, 0, tzinfo=timezone.utc),
        close_maker_attempt=True,
        close_maker_fallback_reason=None,
        seed_source=seed_source,
    )


def _make_cell(
    cell_id="G-AB-02-C30",
    family="grid",
    block=1,
    offset_bps=0.5,
    buffer_ticks=0,
    timeout_ms=30_000,
    spread_guard_bps=50.0,
) -> CalibrationCell:
    return CalibrationCell(
        cell_id=cell_id, family=family, block=block,
        offset_bps=offset_bps, buffer_ticks=buffer_ticks,
        timeout_ms=timeout_ms, spread_guard_bps=spread_guard_bps,
        is_baseline=False, direction_note="test",
    )


def _make_tick_window(
    fill_ts,
    symbol="BTCUSDT",
    pre_quotes=None,  # list of (offset_sec, bid, ask)
    replay_quotes=None,
    drift_quotes=None,
) -> TickWindow:
    def _samples(quote_list):
        if not quote_list:
            return tuple()
        out = []
        for offset_sec, bid, ask in quote_list:
            spread = (ask - bid) / ((ask + bid) * 0.5) * 10_000.0 if ask > bid else 999.0
            out.append(TickSample(
                ts=fill_ts + timedelta(seconds=offset_sec),
                symbol=symbol,
                best_bid=bid,
                best_ask=ask,
                spread_bps=spread,
            ))
        return tuple(out)
    return TickWindow(
        fill_order_id="test_order",
        symbol=symbol,
        fill_ts=fill_ts,
        pre_fill_samples=_samples(pre_quotes),
        replay_samples=_samples(replay_quotes),
        post_drift_samples=_samples(drift_quotes),
    )


def test_simulate_fills_when_ask_drops_to_buy_limit():
    """close short (BUY limit). buffer=0, tight book (1-tick spread) → limit at best_bid。
    為什麼 1-tick spread：避觸 Rust small-tick widening（half_spread > tick → ticks 升）；
    這 cell 期測 baseline inside book 行為。
    """
    fill_ts = datetime(2026, 5, 18, 0, 0, 0, tzinfo=timezone.utc)
    cell = _make_cell(buffer_ticks=0, timeout_ms=30_000)
    seed = _make_seed(side="Buy", exit_reason="grid_close_short", price=100.0, ts=fill_ts)
    # pre-fill BBO: bid=100.00, ask=100.01, tick=0.01 → half_spread=0.005, tick=0.01
    # → required_ticks = ceil(0.5) = 1, > buffer 0 → widen 至 1 → limit = bid - 1*tick = 99.99
    # replay: ask drops to 99.99 within 30s → fill
    window = _make_tick_window(
        fill_ts=fill_ts,
        pre_quotes=[(-1, 100.00, 100.01)],
        replay_quotes=[
            (5, 99.98, 100.00),  # ask 100.00 > limit 99.99
            (10, 99.97, 99.99),   # ask 99.99 == limit → fill
        ],
    )
    result = simulate_cell_against_fill(cell, seed, window, tick_size=0.01)
    assert result.skipped_reason is None
    assert result.simulated_fill is True
    # Rust widen logic: ceil(half_spread/tick)=1 > buffer 0 → buffer 升至 1 → limit = bid - 0.01 = 99.99
    assert abs(result.limit_price - 99.99) < 1e-9
    assert abs(result.simulated_fill_px - 99.99) < 1e-9
    # buy close: simulated 99.99 vs actual taker 100.00 → slippage_raw = (99.99-100)/100*10000 = -1 bps
    # max(0, -1) = 0 → no cost → fee_saving = 3.5
    assert abs(result.fee_saving_bps - 3.5) < 1e-9


def test_simulate_skips_when_no_pre_bbo():
    """無 pre-fill BBO → strict skip no_bbo。"""
    fill_ts = datetime(2026, 5, 18, 0, 0, 0, tzinfo=timezone.utc)
    cell = _make_cell()
    seed = _make_seed(ts=fill_ts)
    window = _make_tick_window(fill_ts=fill_ts, pre_quotes=None, replay_quotes=[(5, 99.0, 100.0)])
    result = simulate_cell_against_fill(cell, seed, window, tick_size=0.01)
    # BBO at fill 取最後 ≤ fill_ts；replay 都是 > fill_ts → 無 pre → no_bbo
    assert result.skipped_reason == "no_bbo"
    assert result.simulated_fill is False


def test_simulate_skips_when_spread_above_guard():
    """spread > guard → strict skip spread_guard。"""
    fill_ts = datetime(2026, 5, 18, 0, 0, 0, tzinfo=timezone.utc)
    cell = _make_cell(spread_guard_bps=25.0)
    seed = _make_seed(ts=fill_ts)
    # bid=100, ask=100.5 → spread = 0.5/100.25 * 10000 ≈ 49.87 bps > 25 guard
    window = _make_tick_window(
        fill_ts=fill_ts,
        pre_quotes=[(-1, 100.0, 100.5)],
        replay_quotes=[(5, 100.0, 100.5)],
    )
    result = simulate_cell_against_fill(cell, seed, window, tick_size=0.01)
    assert result.skipped_reason == "spread_guard"


def test_simulate_no_fill_when_ask_never_reaches_limit():
    """限價 99.99 but ask 維持 100.01 整 timeout → no fill。
    為什麼這 setup：1-tick spread + buffer=0 → small-tick widening 升 buffer 至 1
    → limit=99.99；replay ask 維持 100.01 不達 → no fill。
    """
    fill_ts = datetime(2026, 5, 18, 0, 0, 0, tzinfo=timezone.utc)
    cell = _make_cell(buffer_ticks=0, timeout_ms=30_000)
    seed = _make_seed(side="Buy", price=100.0, ts=fill_ts)
    window = _make_tick_window(
        fill_ts=fill_ts,
        pre_quotes=[(-1, 100.00, 100.01)],
        replay_quotes=[(5, 100.00, 100.01), (15, 100.00, 100.01), (25, 100.00, 100.01)],
    )
    result = simulate_cell_against_fill(cell, seed, window, tick_size=0.01)
    assert result.skipped_reason is None
    assert result.simulated_fill is False
    # widened: limit = bid - 0.01 = 99.99
    assert abs(result.limit_price - 99.99) < 1e-9
    assert result.fee_saving_bps is None  # no fill → no saving


def test_simulate_skips_when_family_mismatch():
    """cell.family='phys_lock_giveback' but seed.exit_reason='grid_close_short' → mismatch."""
    fill_ts = datetime(2026, 5, 18, 0, 0, 0, tzinfo=timezone.utc)
    cell = _make_cell(family="phys_lock_giveback")
    seed = _make_seed(exit_reason="grid_close_short", ts=fill_ts)
    window = _make_tick_window(fill_ts=fill_ts, pre_quotes=[(-1, 100.0, 100.1)])
    result = simulate_cell_against_fill(cell, seed, window, tick_size=0.01)
    assert result.skipped_reason == "family_exit_mismatch"


def test_simulate_handles_strategy_close_prefix():
    """'strategy_close:grid_close_short' canonical → 'grid_close_short' 應匹配 grid family。"""
    fill_ts = datetime(2026, 5, 18, 0, 0, 0, tzinfo=timezone.utc)
    cell = _make_cell(family="grid", buffer_ticks=0)
    seed = _make_seed(
        side="Buy",
        exit_reason="strategy_close:grid_close_short",
        price=100.0,
        ts=fill_ts,
    )
    # 1-tick spread → widening 升 buffer 至 1 → limit = bid - tick = 99.99
    window = _make_tick_window(
        fill_ts=fill_ts,
        pre_quotes=[(-1, 100.00, 100.01)],
        replay_quotes=[(5, 99.97, 99.99)],  # ask 99.99 reaches limit → fill
    )
    result = simulate_cell_against_fill(cell, seed, window, tick_size=0.01)
    assert result.skipped_reason is None  # 不應 mismatch
    assert result.simulated_fill is True


def test_simulate_cell_aggregates_multiple_fills():
    """simulate_cell aggregates n_attempts / n_simulated_fills correctly。
    用 1-tick spread 避觸 small-tick widening；limit = bid - tick = 99.99。
    """
    fill_ts = datetime(2026, 5, 18, 0, 0, 0, tzinfo=timezone.utc)
    cell = _make_cell(buffer_ticks=0, timeout_ms=30_000)
    seeds = [
        _make_seed(order_id="o1", side="Buy", price=100.0,
                   ts=fill_ts),
        _make_seed(order_id="o2", side="Buy", price=100.0,
                   ts=fill_ts + timedelta(minutes=1)),
    ]
    win1 = _make_tick_window(
        fill_ts=seeds[0].ts,
        pre_quotes=[(-1, 100.00, 100.01)],
        replay_quotes=[(5, 99.97, 99.99)],  # ask 99.99 reaches limit → fill
    )
    win2 = _make_tick_window(
        fill_ts=seeds[1].ts,
        pre_quotes=[(-1, 100.00, 100.01)],
        replay_quotes=[(5, 100.00, 100.02)],  # ask stays at 100.02 → no fill
    )
    outcome = simulate_cell(
        cell=cell,
        seeds=seeds,
        tick_windows={"o1": win1, "o2": win2},
        tick_size_map={"BTCUSDT": 0.01},
    )
    assert outcome.n_attempts == 2
    assert outcome.n_simulated_fills == 1
    assert outcome.maker_fill_rate == 0.5  # 1 / 2 eligible
    assert outcome.data_source == DATA_SOURCE_TAG


def test_simulate_cell_skips_missing_tick_size():
    """seed.symbol 不在 tick_size_map → skipped_reason=tick_size_missing。"""
    fill_ts = datetime(2026, 5, 18, 0, 0, 0, tzinfo=timezone.utc)
    cell = _make_cell()
    seed = _make_seed(symbol="UNKNOWNUSDT", ts=fill_ts)
    win = _make_tick_window(fill_ts=fill_ts)
    outcome = simulate_cell(
        cell=cell,
        seeds=[seed],
        tick_windows={"test_order": win},
        tick_size_map={},  # no tick_size for UNKNOWNUSDT
    )
    assert outcome.n_attempts == 1
    assert outcome.n_simulated_fills == 0
    assert outcome.n_skipped_tick_missing == 1


def _make_orderbook_window(
    fill_ts,
    symbol="BTCUSDT",
    bid_depth_5=1000.0,
    ask_depth_5=1000.0,
) -> OrderbookDepthWindow:
    """構造 1 個 1m bucket 對應 fill_ts 前 60s 的 depth sample。"""
    from datetime import timedelta as _td
    sample = QueueDepthSample(
        ts_bucket_start=fill_ts - _td(seconds=30),
        symbol=symbol,
        bid_depth_5=bid_depth_5,
        ask_depth_5=ask_depth_5,
    )
    return OrderbookDepthWindow(
        fill_order_id="test_order",
        symbol=symbol,
        fill_ts=fill_ts,
        buckets=(sample,),
    )


def test_queue_adjusted_probability_when_fill_and_depth_available():
    """BBO-cross-proxy fill=True，有 depth → queue_adjusted_fill_probability < 1。"""
    fill_ts = datetime(2026, 5, 18, 0, 0, 0, tzinfo=timezone.utc)
    cell = _make_cell(buffer_ticks=0, timeout_ms=30_000)
    seed = _make_seed(side="Buy", exit_reason="grid_close_short", price=100.0, ts=fill_ts)
    seed = FillReplaySeed(
        order_id=seed.order_id, link_id=seed.link_id, symbol=seed.symbol,
        side=seed.side, exit_reason=seed.exit_reason,
        qty=100.0,  # 對比 bid_depth_5=100 → factor=0.5
        price=seed.price, ts=seed.ts,
        close_maker_attempt=seed.close_maker_attempt,
        close_maker_fallback_reason=seed.close_maker_fallback_reason,
        seed_source=seed.seed_source,
    )
    tick_win = _make_tick_window(
        fill_ts=fill_ts,
        pre_quotes=[(-1, 100.00, 100.01)],
        replay_quotes=[(5, 99.97, 99.99)],
    )
    ob_win = _make_orderbook_window(
        fill_ts=fill_ts, bid_depth_5=100.0, ask_depth_5=100.0,
    )
    result = simulate_cell_against_fill(
        cell, seed, tick_win, tick_size=0.01,
        orderbook_window=ob_win, queue_weight=0.40,
    )
    assert result.simulated_fill is True
    # close BUY (position_is_long=False) → same-side = bid_depth_5 = 100
    # factor = 100 / (100+100) = 0.5；adj = 1 * (1 - 0.40*0.5) = 0.80
    assert result.same_side_depth_5 == 100.0
    assert result.queue_factor == 0.5
    assert abs(result.queue_adjusted_fill_probability - 0.80) < 1e-9


def test_queue_adjusted_probability_passthrough_when_no_orderbook():
    """無 orderbook_window → queue_adjusted = simulated_fill 對應 0/1（不調整）。"""
    fill_ts = datetime(2026, 5, 18, 0, 0, 0, tzinfo=timezone.utc)
    cell = _make_cell(buffer_ticks=0, timeout_ms=30_000)
    seed = _make_seed(side="Buy", price=100.0, ts=fill_ts)
    tick_win = _make_tick_window(
        fill_ts=fill_ts,
        pre_quotes=[(-1, 100.00, 100.01)],
        replay_quotes=[(5, 99.97, 99.99)],
    )
    result = simulate_cell_against_fill(
        cell, seed, tick_win, tick_size=0.01,
        orderbook_window=None,  # passthrough
    )
    assert result.simulated_fill is True
    assert result.queue_factor is None
    # passthrough → queue_adjusted == fill_p_proxy = 1.0
    assert result.queue_adjusted_fill_probability == 1.0


def test_queue_adjusted_probability_zero_when_no_fill():
    """BBO-cross-proxy fill=False → queue_adjusted = 0（即使 depth 有效）。"""
    fill_ts = datetime(2026, 5, 18, 0, 0, 0, tzinfo=timezone.utc)
    cell = _make_cell(buffer_ticks=0, timeout_ms=30_000)
    seed = _make_seed(side="Buy", price=100.0, ts=fill_ts)
    tick_win = _make_tick_window(
        fill_ts=fill_ts,
        pre_quotes=[(-1, 100.00, 100.01)],
        replay_quotes=[(5, 100.00, 100.01), (15, 100.00, 100.01)],  # no cross
    )
    ob_win = _make_orderbook_window(fill_ts=fill_ts)
    result = simulate_cell_against_fill(
        cell, seed, tick_win, tick_size=0.01, orderbook_window=ob_win,
    )
    assert result.simulated_fill is False
    # queue_factor 可能算出 ≠ None（depth 有效），但 proxy=0 → adjusted = 0
    assert result.queue_adjusted_fill_probability == 0.0


def test_simulate_cell_aggregates_queue_adjusted_rate():
    """simulate_cell aggregates queue_adjusted_fill_rate per eligible mean。"""
    fill_ts = datetime(2026, 5, 18, 0, 0, 0, tzinfo=timezone.utc)
    cell = _make_cell(buffer_ticks=0, timeout_ms=30_000)
    seeds = [
        _make_seed(order_id="o1", side="Buy", price=100.0, ts=fill_ts),
        _make_seed(order_id="o2", side="Buy", price=100.0,
                   ts=fill_ts + timedelta(minutes=1)),
    ]
    # 把 qty 改大確保 queue factor 顯著
    seeds = [
        FillReplaySeed(order_id=s.order_id, link_id=s.link_id, symbol=s.symbol,
                       side=s.side, exit_reason=s.exit_reason,
                       qty=100.0,
                       price=s.price, ts=s.ts,
                       close_maker_attempt=s.close_maker_attempt,
                       close_maker_fallback_reason=s.close_maker_fallback_reason,
                       seed_source=s.seed_source)
        for s in seeds
    ]
    win1 = _make_tick_window(
        fill_ts=seeds[0].ts,
        pre_quotes=[(-1, 100.00, 100.01)],
        replay_quotes=[(5, 99.97, 99.99)],  # fill
    )
    win2 = _make_tick_window(
        fill_ts=seeds[1].ts,
        pre_quotes=[(-1, 100.00, 100.01)],
        replay_quotes=[(5, 100.00, 100.02)],  # no fill
    )
    ob1 = _make_orderbook_window(fill_ts=seeds[0].ts,
                                  bid_depth_5=100.0, ask_depth_5=100.0)
    ob2 = _make_orderbook_window(fill_ts=seeds[1].ts,
                                  bid_depth_5=100.0, ask_depth_5=100.0)
    outcome = simulate_cell(
        cell=cell, seeds=seeds,
        tick_windows={"o1": win1, "o2": win2},
        tick_size_map={"BTCUSDT": 0.01},
        orderbook_windows={"o1": ob1, "o2": ob2},
        queue_weight=0.40,
    )
    assert outcome.n_attempts == 2
    assert outcome.n_simulated_fills == 1
    assert outcome.maker_fill_rate == 0.5
    # eligible = 2，queue_adjusted = (0.80 + 0.0) / 2 = 0.40
    assert abs(outcome.queue_adjusted_fill_rate - 0.40) < 1e-9
    assert outcome.queue_adjusted_eligible_with_depth == 2


def test_simulate_sell_close_fills_when_bid_rises_to_limit():
    """close long (SELL limit). buffer=0, 1-tick spread → small-tick widen 至 buffer=1
    → SELL limit = ask + tick = 100.02. bid rises to 100.02 → fill。
    """
    fill_ts = datetime(2026, 5, 18, 0, 0, 0, tzinfo=timezone.utc)
    cell = _make_cell(buffer_ticks=0, timeout_ms=30_000)
    seed = _make_seed(side="Sell", exit_reason="grid_close_long", price=100.0, ts=fill_ts)
    # pre BBO: bid=100.00, ask=100.01 → widening → SELL limit = ask + 1*tick = 100.02
    # replay: bid rises to 100.02 → fill
    window = _make_tick_window(
        fill_ts=fill_ts,
        pre_quotes=[(-1, 100.00, 100.01)],
        replay_quotes=[(5, 100.02, 100.03)],  # bid 100.02 ≥ limit 100.02 → fill
    )
    result = simulate_cell_against_fill(cell, seed, window, tick_size=0.01)
    assert result.skipped_reason is None
    assert result.simulated_fill is True
    assert abs(result.limit_price - 100.02) < 1e-9
