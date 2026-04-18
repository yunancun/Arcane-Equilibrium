"""Tests for realized_edge_stats Winsorization (P1-17, 2026-04-18 Edge Crisis RCA).
realized_edge_stats Winsorization 測試（P1-17，2026-04-18 Edge 危機 RCA）。

Winsorization clamps each RoundTripRecord's gross_pnl_bps and net_pnl_bps to
±_WINSORIZE_BPS to prevent outlier round-trips (e.g. halt_session mis-paired
stops) from poisoning James-Stein grand_mean via toxic shrinkage.
Winsorization 限幅每個 RoundTripRecord 的 gross_pnl_bps 和 net_pnl_bps 到
±_WINSORIZE_BPS 以防止離群往返（例如 halt_session 誤配對的止損）透過毒性
收縮污染 James-Stein grand_mean。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from program_code.ml_training import realized_edge_stats
from program_code.ml_training.realized_edge_stats import (
    _WINSORIZE_BPS,
    _pair_round_trips,
    _reset_winsorize_counter,
    get_winsorize_clamp_count,
)


# ---------------------------------------------------------------------------
# Fill fixtures / Fill 測試資料
# ---------------------------------------------------------------------------

_BASE_TS = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)


def _mk_fill(
    *,
    symbol: str,
    strategy: str,
    side: str,
    qty: float,
    price: float,
    fee: float = 0.0,
    realized_pnl: float = 0.0,
    offset_sec: int = 0,
) -> dict:
    """Build a minimal fill dict matching _FILLS_QUERY column names."""
    return {
        "ts": _BASE_TS + timedelta(seconds=offset_sec),
        "symbol": symbol,
        "strategy_name": strategy,
        "side": side,
        "qty": qty,
        "price": price,
        "fee": fee,
        "realized_pnl": realized_pnl,
        "is_paper": False,
        "engine_mode": "demo",
    }


def _pair(fills: list[dict]):
    """Run pairing with a fresh clamp counter."""
    _reset_winsorize_counter()
    return _pair_round_trips(fills)


# ---------------------------------------------------------------------------
# Sanity: constant matches expectations / 常量檢查
# ---------------------------------------------------------------------------

def test_winsorize_constant_is_5000_bps():
    """Per-trade PnL clamp is 5000 bps (±50%), covering 2× demo stop_loss_max_pct."""
    assert _WINSORIZE_BPS == 5000.0


# ---------------------------------------------------------------------------
# Case 1: normal round-trip passes through unchanged
# ---------------------------------------------------------------------------

def test_normal_roundtrip_passes_through_unchanged():
    """Entry 100 @ 10000, exit 100 @ 9500 → gross_pnl = -50000 USD on 1M notional → -500 bps.
    Should NOT be clamped."""
    # Gross PnL = -500 USD on entry notional = 1_000_000 * -0.0005 = -500 bps.
    # Use qty=100, price=10000 → entry notional 1_000_000.
    # Exit realized_pnl = -50_000 USD (= -500 bps of 1_000_000 notional).
    fills = [
        _mk_fill(symbol="BTCUSDT", strategy="grid_trading", side="buy",
                 qty=100, price=10000, fee=0.0, offset_sec=0),
        _mk_fill(symbol="BTCUSDT", strategy="strategy_close:normal", side="sell",
                 qty=100, price=9500, fee=0.0, realized_pnl=-50_000, offset_sec=60),
    ]
    records = _pair(fills)
    assert len(records) == 1
    rec = records[0]
    assert rec.gross_pnl_bps == pytest.approx(-500.0, abs=1e-6)
    assert rec.net_pnl_bps == pytest.approx(-500.0, abs=1e-6)
    assert get_winsorize_clamp_count() == 0


# ---------------------------------------------------------------------------
# Case 2: extreme negative clamps to -_WINSORIZE_BPS
# ---------------------------------------------------------------------------

def test_extreme_negative_roundtrip_clamps_to_floor():
    """realized_pnl = -500_000 USD on 1M notional → -5000 bps raw... push well beyond."""
    # Gross PnL = -2_000_000 USD on 1_000_000 notional = -20_000 bps raw.
    # Must clamp to -5000 bps.
    fills = [
        _mk_fill(symbol="DOTUSDT", strategy="grid_trading", side="buy",
                 qty=100, price=10000, fee=0.0, offset_sec=0),
        _mk_fill(symbol="DOTUSDT", strategy="strategy_close:stop", side="sell",
                 qty=100, price=8000, fee=50.0, realized_pnl=-2_000_000, offset_sec=60),
    ]
    records = _pair(fills)
    assert len(records) == 1
    rec = records[0]
    assert rec.gross_pnl_bps == pytest.approx(-_WINSORIZE_BPS, abs=1e-6)
    # Net after tiny fees: raw would be even more negative, also clamped to -5000.
    assert rec.net_pnl_bps == pytest.approx(-_WINSORIZE_BPS, abs=1e-6)
    # Both gross and net fired → 2 clamps.
    assert get_winsorize_clamp_count() == 2


# ---------------------------------------------------------------------------
# Case 3: extreme positive clamps to +_WINSORIZE_BPS
# ---------------------------------------------------------------------------

def test_extreme_positive_roundtrip_clamps_to_ceiling():
    """realized_pnl = +10_000_000 USD on 1M notional → +100_000 bps raw."""
    fills = [
        _mk_fill(symbol="ETHUSDT", strategy="momentum", side="buy",
                 qty=100, price=10000, fee=0.0, offset_sec=0),
        _mk_fill(symbol="ETHUSDT", strategy="strategy_close:target", side="sell",
                 qty=100, price=110000, fee=0.0, realized_pnl=10_000_000, offset_sec=60),
    ]
    records = _pair(fills)
    assert len(records) == 1
    rec = records[0]
    assert rec.gross_pnl_bps == pytest.approx(+_WINSORIZE_BPS, abs=1e-6)
    assert rec.net_pnl_bps == pytest.approx(+_WINSORIZE_BPS, abs=1e-6)
    assert get_winsorize_clamp_count() == 2


# ---------------------------------------------------------------------------
# Case 4: boundary values pass through unchanged
# ---------------------------------------------------------------------------

def test_boundary_exactly_negative_limit_passes_through():
    """realized_pnl = -500_000 USD on 1_000_000 notional = exactly -5000 bps."""
    fills = [
        _mk_fill(symbol="SOLUSDT", strategy="grid_trading", side="buy",
                 qty=100, price=10000, fee=0.0, offset_sec=0),
        _mk_fill(symbol="SOLUSDT", strategy="strategy_close:stop", side="sell",
                 qty=100, price=5000, fee=0.0, realized_pnl=-500_000, offset_sec=60),
    ]
    records = _pair(fills)
    assert len(records) == 1
    rec = records[0]
    assert rec.gross_pnl_bps == pytest.approx(-_WINSORIZE_BPS, abs=1e-6)
    assert rec.net_pnl_bps == pytest.approx(-_WINSORIZE_BPS, abs=1e-6)
    # Strictly less-than / greater-than check → boundary does NOT clamp.
    assert get_winsorize_clamp_count() == 0


def test_boundary_exactly_positive_limit_passes_through():
    """realized_pnl = +500_000 USD on 1_000_000 notional = exactly +5000 bps."""
    fills = [
        _mk_fill(symbol="ADAUSDT", strategy="momentum", side="buy",
                 qty=100, price=10000, fee=0.0, offset_sec=0),
        _mk_fill(symbol="ADAUSDT", strategy="strategy_close:target", side="sell",
                 qty=100, price=15000, fee=0.0, realized_pnl=500_000, offset_sec=60),
    ]
    records = _pair(fills)
    assert len(records) == 1
    rec = records[0]
    assert rec.gross_pnl_bps == pytest.approx(+_WINSORIZE_BPS, abs=1e-6)
    assert rec.net_pnl_bps == pytest.approx(+_WINSORIZE_BPS, abs=1e-6)
    assert get_winsorize_clamp_count() == 0


# ---------------------------------------------------------------------------
# Case 5: zero passes through
# ---------------------------------------------------------------------------

def test_zero_pnl_passes_through():
    """realized_pnl = 0 (flat round-trip, zero fees) → 0 bps in/out, no clamp."""
    fills = [
        _mk_fill(symbol="XRPUSDT", strategy="grid_trading", side="buy",
                 qty=100, price=10000, fee=0.0, offset_sec=0),
        _mk_fill(symbol="XRPUSDT", strategy="strategy_close:normal", side="sell",
                 qty=100, price=10000, fee=0.0, realized_pnl=0.0, offset_sec=60),
    ]
    records = _pair(fills)
    assert len(records) == 1
    rec = records[0]
    assert rec.gross_pnl_bps == pytest.approx(0.0, abs=1e-6)
    assert rec.net_pnl_bps == pytest.approx(0.0, abs=1e-6)
    assert get_winsorize_clamp_count() == 0


# ---------------------------------------------------------------------------
# Case 6: extreme net but normal gross — verify independent clamping
# ---------------------------------------------------------------------------

def test_gross_inside_band_but_net_outside_clamps_only_net():
    """Construct a case where gross passes through but net alone is clipped.

    This is pathological (fees > 5000 bps of notional), but confirms per-field
    independent winsorize decisions. In practice fees are tiny; the test just
    asserts the counter reflects only-net firing.
    """
    # Gross PnL = -300_000 USD on 1_000_000 notional = -3000 bps (inside ±5000).
    # Fees apportion to ~3000 bps → net = -6000 bps → clamp to -5000.
    # entry_fee=150_000, exit_fee=150_000, entry_notional=1_000_000 → fees = 3000 bps.
    fills = [
        _mk_fill(symbol="AVAXUSDT", strategy="grid_trading", side="buy",
                 qty=100, price=10000, fee=150_000, offset_sec=0),
        _mk_fill(symbol="AVAXUSDT", strategy="strategy_close:stop", side="sell",
                 qty=100, price=7000, fee=150_000, realized_pnl=-300_000, offset_sec=60),
    ]
    records = _pair(fills)
    assert len(records) == 1
    rec = records[0]
    assert rec.gross_pnl_bps == pytest.approx(-3000.0, abs=1e-6)
    # Net raw = (-300_000 - 150_000 - 150_000) / 1_000_000 * 10_000 = -6000 bps → clamped to -5000.
    assert rec.net_pnl_bps == pytest.approx(-_WINSORIZE_BPS, abs=1e-6)
    # Only net fired → 1 clamp.
    assert get_winsorize_clamp_count() == 1
