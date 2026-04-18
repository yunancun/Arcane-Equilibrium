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
    _PRICE_JUMP_LN_LIMIT,
    _WINSORIZE_BPS,
    _is_price_jump_pair,
    _pair_round_trips,
    _reset_price_jump_counter,
    _reset_winsorize_counter,
    get_price_jump_skip_count,
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
    """Run pairing with a fresh clamp counter + price-jump counter."""
    _reset_winsorize_counter()
    _reset_price_jump_counter()
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
    """realized_pnl inflated to +10M USD on 1M notional → +100_000 bps raw.
    Exit price kept inside the P1-16 price-jump band (ratio 1.4, |ln|=0.336 < 0.5)
    so the gate does not short-circuit Winsorize — this test specifically
    exercises the Winsorize ceiling, not the price-jump guard.
    刻意把 exit 保持在 P1-16 跳價閘門內，讓 Winsorize 頂格仍能觸發驗證。"""
    fills = [
        _mk_fill(symbol="ETHUSDT", strategy="momentum", side="buy",
                 qty=100, price=10000, fee=0.0, offset_sec=0),
        _mk_fill(symbol="ETHUSDT", strategy="strategy_close:target", side="sell",
                 qty=100, price=14000, fee=0.0, realized_pnl=10_000_000, offset_sec=60),
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
    """realized_pnl = -500_000 USD on 1_000_000 notional = exactly -5000 bps.
    Exit price kept inside the P1-16 price-jump band (ratio 0.85, |ln|=0.163 < 0.5).
    Exit 保持在跳價閘門內，驗證 Winsorize 邊界嚴格 < 比較不誤傷。"""
    fills = [
        _mk_fill(symbol="SOLUSDT", strategy="grid_trading", side="buy",
                 qty=100, price=10000, fee=0.0, offset_sec=0),
        _mk_fill(symbol="SOLUSDT", strategy="strategy_close:stop", side="sell",
                 qty=100, price=8500, fee=0.0, realized_pnl=-500_000, offset_sec=60),
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


# ===========================================================================
# P1-16 defensive gate tests / P1-16 防禦閘門測試
# ===========================================================================

def test_price_jump_constant_is_half():
    """|ln(exit/entry)| threshold is 0.5 (covers ~65% round-trip move)."""
    assert _PRICE_JUMP_LN_LIMIT == 0.5


def test_price_jump_helper_flags_extreme_ratio():
    """_is_price_jump_pair flags ratios where |ln(exit/entry)| > 0.5."""
    # Inside band: ratio 1.5 → ln ≈ 0.405 < 0.5.
    assert _is_price_jump_pair(100.0, 150.0) is False
    # Outside band: ratio 2.0 → ln ≈ 0.693 > 0.5.
    assert _is_price_jump_pair(100.0, 200.0) is True
    # Inverted: ratio 0.5 → ln ≈ -0.693 → abs > 0.5.
    assert _is_price_jump_pair(100.0, 50.0) is True
    # Invalid inputs never flag (non-positive / non-finite).
    import math
    assert _is_price_jump_pair(0.0, 100.0) is False
    assert _is_price_jump_pair(100.0, 0.0) is False
    assert _is_price_jump_pair(float("nan"), 100.0) is False
    assert _is_price_jump_pair(100.0, math.inf) is False


def test_price_jump_skips_p116_style_cross_symbol_pair():
    """Reproduce the P1-16 halt_session corruption: ETHUSDT $2357.94 stamped
    onto a DOT-scale entry at $7.80 → exit/entry ≈ 302 → |ln|≈5.71 → SKIPPED.
    Neither gross nor net bps should appear in the output. The pair is consumed
    from the FIFO queue so downstream state stays consistent; the record is
    just suppressed. 複現 P1-16 ETH 價蓋 DOT fill 的情境，驗證 skip 邏輯。"""
    fills = [
        _mk_fill(symbol="DOTUSDT", strategy="grid_trading", side="buy",
                 qty=1.0, price=7.80, fee=0.0, offset_sec=0),
        _mk_fill(symbol="DOTUSDT", strategy="risk_close:halt_session", side="sell",
                 qty=1.0, price=2357.94, fee=0.0, realized_pnl=-235.66, offset_sec=60),
    ]
    records = _pair(fills)
    assert records == []  # whole round-trip suppressed
    assert get_price_jump_skip_count() == 1
    # Winsorize did NOT fire — skip runs first.
    assert get_winsorize_clamp_count() == 0


def test_price_jump_allows_legitimate_large_move():
    """A 60% round-trip (ratio 1.6, ln ≈ 0.470 < 0.5) is inside the band and
    must pass through to Winsorize. 合法 60% 往返仍進 Winsorize，不被誤殺。"""
    # realized_pnl = +600 on 100 qty at entry 10 → notional=1000, bps = +6000
    # → Winsorize to +5000.
    fills = [
        _mk_fill(symbol="AVAXUSDT", strategy="momentum", side="buy",
                 qty=100, price=10.0, fee=0.0, offset_sec=0),
        _mk_fill(symbol="AVAXUSDT", strategy="strategy_close:target", side="sell",
                 qty=100, price=16.0, fee=0.0, realized_pnl=600.0, offset_sec=60),
    ]
    records = _pair(fills)
    assert len(records) == 1
    assert records[0].gross_pnl_bps == pytest.approx(+_WINSORIZE_BPS, abs=1e-6)
    assert get_price_jump_skip_count() == 0
    # Both gross and net exceeded the cap → 2 clamps.
    assert get_winsorize_clamp_count() == 2


def test_denominator_protection_uses_full_entry_notional_on_partial_match():
    """When an exit fills only a fraction of the entry (partial match), the
    bps denominator must floor at the FULL entry notional, not the tiny
    matched-qty notional. Without this floor, a large apportioned realized_pnl
    against a micro-denominator produces absurd bps (the $0.13 vs $235 loss
    → -17M bps seen in the P1-16 incident). 部分配對時分母必須托底至整筆
    entry notional，否則微分母會把分攤 PnL 放大成荒謬 bps。"""
    # Entry: qty=100 @ price=10 → full notional = 1000.
    # Exit: qty=10 (10% of entry) @ price=10 → matched_qty=10, match_notional=100.
    # Apportion: realized_pnl=-50 at full exit qty=10, so apportion = -50 × (10/10) = -50.
    # Pre-fix (match-notional denom): -50 / 100 × 10_000 = -5000 bps.
    # Post-fix (full-entry denom):    -50 / 1000 × 10_000 = -500 bps.
    # 修復後分母從 100 抬到 1000，bps 從 -5000 縮回 -500。
    fills = [
        _mk_fill(symbol="BNBUSDT", strategy="grid_trading", side="buy",
                 qty=100, price=10.0, fee=0.0, offset_sec=0),
        _mk_fill(symbol="BNBUSDT", strategy="strategy_close:partial", side="sell",
                 qty=10, price=10.0, fee=0.0, realized_pnl=-50.0, offset_sec=60),
    ]
    records = _pair(fills)
    assert len(records) == 1
    rec = records[0]
    # -50 USD apportioned / 1000 USD full entry notional × 10_000 = -500 bps.
    # -50 / 1000 × 10_000 = -500 bps（分母托底至整筆 entry，不是 match 部分）。
    assert rec.gross_pnl_bps == pytest.approx(-500.0, abs=1e-6)
    assert rec.net_pnl_bps == pytest.approx(-500.0, abs=1e-6)
    # notional_usd still records the per-match notional for transparency.
    # notional_usd 仍記錄本次配對的名義金額，透明可查。
    assert rec.notional_usd == pytest.approx(100.0, abs=1e-6)
    assert get_price_jump_skip_count() == 0
    assert get_winsorize_clamp_count() == 0
