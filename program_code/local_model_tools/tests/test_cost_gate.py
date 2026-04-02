"""
Tests for cost_gate.py — Cost-Aware Entry Gate
成本感知入場門檻測試

Covers:
  - compute_round_trip_cost_pct basic calculation
  - should_reject_for_cost: high ATR → pass, low ATR → reject
  - Fail-open on None ATR
  - Daily safety valve
  - Boundary: ATR exactly at threshold
  - Different win_rate impact
  - Different volume tiers (slippage lookup)
  - _lookup_slippage edge cases
"""

from __future__ import annotations

import pytest

from local_model_tools.cost_gate import (
    BYBIT_TAKER_FEE_RATE,
    DEFAULT_SLIPPAGE_RATE,
    SLIPPAGE_TIERS,
    _lookup_slippage,
    compute_round_trip_cost_pct,
    should_reject_for_cost,
)


# ─── _lookup_slippage tests ───


class TestLookupSlippage:
    """Test slippage tier lookup. / 測試滑點分級查找。"""

    def test_high_volume_btc(self):
        """BTC-level volume (>$1B) → lowest slippage (1 bps)."""
        assert _lookup_slippage(2_000_000_000) == 0.0001

    def test_mid_volume(self):
        """>$100M volume → 2 bps."""
        assert _lookup_slippage(500_000_000) == 0.0002

    def test_low_volume(self):
        """>$10M volume → 5 bps."""
        assert _lookup_slippage(50_000_000) == 0.0005

    def test_very_low_volume(self):
        """>$1M volume → 15 bps."""
        assert _lookup_slippage(5_000_000) == 0.0015

    def test_illiquid(self):
        """<$1M volume → 30 bps."""
        assert _lookup_slippage(100_000) == 0.0030

    def test_zero_volume(self):
        """Zero volume → default slippage. / 零成交量 → 默認滑點。"""
        assert _lookup_slippage(0.0) == DEFAULT_SLIPPAGE_RATE

    def test_negative_volume(self):
        """Negative volume → default slippage (defensive). / 負成交量 → 默認滑點（防禦性）。"""
        assert _lookup_slippage(-100.0) == DEFAULT_SLIPPAGE_RATE


# ─── compute_round_trip_cost_pct tests ───


class TestComputeRoundTripCostPct:
    """Test round-trip cost computation. / 測試來回成本計算。"""

    def test_default_slippage(self):
        """
        Default volume=0 → DEFAULT_SLIPPAGE_RATE.
        Cost = (0.00055 + 0.0005) * 2 * 100 = 0.21%.
        """
        cost = compute_round_trip_cost_pct("TESTUSDT")
        # taker 0.055% + slippage 0.05% = 0.105% per leg, × 2 = 0.21%
        expected = (BYBIT_TAKER_FEE_RATE + DEFAULT_SLIPPAGE_RATE) * 2 * 100.0
        assert abs(cost - expected) < 1e-10

    def test_high_volume_lower_cost(self):
        """
        High volume ($2B) → 1 bps slippage → lower cost.
        Cost = (0.00055 + 0.0001) * 2 * 100 = 0.13%.
        """
        cost = compute_round_trip_cost_pct("BTCUSDT", volume_24h=2_000_000_000)
        expected = (0.00055 + 0.0001) * 2 * 100.0
        assert abs(cost - expected) < 1e-10

    def test_illiquid_higher_cost(self):
        """
        Illiquid ($100K) → 30 bps slippage → higher cost.
        Cost = (0.00055 + 0.003) * 2 * 100 = 0.71%.
        """
        cost = compute_round_trip_cost_pct("SHITCOINUSDT", volume_24h=100_000)
        expected = (0.00055 + 0.003) * 2 * 100.0
        assert abs(cost - expected) < 1e-10


# ─── should_reject_for_cost tests ───


class TestShouldRejectForCost:
    """Test the main decision function. / 測試主決策函數。"""

    def test_high_atr_passes(self):
        """
        High ATR (3.0%) >> cost threshold → should pass.
        高 ATR（3.0%）遠超成本閾值 → 應通過。
        """
        reject, reason = should_reject_for_cost(
            "BTCUSDT", atr_pct=3.0, win_rate=0.5, daily_trade_count=5,
        )
        assert reject is False
        assert reason == ""

    def test_low_atr_rejected(self):
        """
        Very low ATR (0.01%) < cost threshold → should reject.
        極低 ATR（0.01%）低於成本閾值 → 應拒絕。
        """
        reject, reason = should_reject_for_cost(
            "LOWVOLCOIN", atr_pct=0.01, win_rate=0.5, daily_trade_count=5,
        )
        assert reject is True
        assert "insufficient_volatility" in reason

    def test_atr_none_fail_open(self):
        """
        ATR=None (no data) → fail-open, should pass.
        ATR=None（無數據）→ fail-open，應通過。
        """
        reject, reason = should_reject_for_cost("NEWCOIN", atr_pct=None)
        assert reject is False
        assert reason == "atr_unavailable_pass_through"

    def test_daily_safety_valve_zero_trades(self):
        """
        First trade of the day with marginal ATR → safety valve allows it.
        當天第一筆交易且 ATR 邊際 → 安全閥放行。
        The ATR must be > c_round * 0.5 for the valve to trigger.
        """
        # Default cost ≈ 0.21%, half = 0.105%. ATR=0.15% > 0.105% → safety valve
        reject, reason = should_reject_for_cost(
            "MARGINAL", atr_pct=0.15, win_rate=0.5, daily_trade_count=0,
        )
        assert reject is False
        assert reason == "daily_safety_valve"

    def test_daily_safety_valve_not_triggered_with_trades(self):
        """
        Same marginal ATR but daily_trade_count > 0 → no safety valve.
        相同邊際 ATR 但已有成交 → 安全閥不觸發。
        """
        # ATR=0.15% but already traded today; min_move ≈ 0.21/0.5*1.3 = 0.546%
        # 0.15 < 0.546 → rejected
        reject, reason = should_reject_for_cost(
            "MARGINAL", atr_pct=0.15, win_rate=0.5, daily_trade_count=1,
        )
        assert reject is True
        assert "insufficient_volatility" in reason

    def test_safety_valve_very_low_atr_still_rejected(self):
        """
        Even with 0 trades, if ATR is truly tiny (< c_round * 0.5) → still rejected.
        即使零成交，若 ATR 極低（< 來回成本一半）→ 仍拒絕。
        """
        # Default cost ≈ 0.21%, half = 0.105%. ATR=0.05% < 0.105% → no safety valve
        reject, reason = should_reject_for_cost(
            "DEADCOIN", atr_pct=0.05, win_rate=0.5, daily_trade_count=0,
        )
        assert reject is True
        assert "insufficient_volatility" in reason

    def test_boundary_atr_equals_min_move(self):
        """
        ATR exactly at threshold → should pass (not strictly less than).
        ATR 剛好在閾值上 → 應通過（不是嚴格小於）。
        """
        # Compute exact min_move: cost=0.21%, wr=0.5 → 0.21/0.5*1.3 = 0.546%
        c_round = (BYBIT_TAKER_FEE_RATE + DEFAULT_SLIPPAGE_RATE) * 2 * 100.0
        min_move = c_round / 0.5 * 1.3
        reject, reason = should_reject_for_cost(
            "BOUNDARY", atr_pct=min_move, win_rate=0.5, daily_trade_count=5,
        )
        assert reject is False
        assert reason == ""

    def test_boundary_atr_just_below_min_move(self):
        """
        ATR just below threshold → should reject.
        ATR 略低於閾值 → 應拒絕。
        """
        c_round = (BYBIT_TAKER_FEE_RATE + DEFAULT_SLIPPAGE_RATE) * 2 * 100.0
        min_move = c_round / 0.5 * 1.3
        reject, reason = should_reject_for_cost(
            "BOUNDARY", atr_pct=min_move - 0.0001, win_rate=0.5, daily_trade_count=5,
        )
        assert reject is True

    def test_high_win_rate_lowers_threshold(self):
        """
        Higher win rate → lower min_move → easier to pass.
        更高勝率 → 更低閾值 → 更容易通過。
        """
        c_round = (BYBIT_TAKER_FEE_RATE + DEFAULT_SLIPPAGE_RATE) * 2 * 100.0
        # wr=0.8 → min_move = 0.21/0.8*1.3 = 0.34125
        # wr=0.3 → min_move = 0.21/0.3*1.3 = 0.91
        reject_low_wr, _ = should_reject_for_cost(
            "TEST", atr_pct=0.5, win_rate=0.3, daily_trade_count=5,
        )
        reject_high_wr, _ = should_reject_for_cost(
            "TEST", atr_pct=0.5, win_rate=0.8, daily_trade_count=5,
        )
        # 0.5% < 0.91% (rejected at low wr) but 0.5% > 0.34% (passed at high wr)
        assert reject_low_wr is True
        assert reject_high_wr is False

    def test_win_rate_clamped_at_030(self):
        """
        Win rate below 0.3 is clamped to 0.3 (prevents unreasonably high threshold).
        勝率低於 0.3 被限制為 0.3（防止不合理的高閾值）。
        """
        reject1, reason1 = should_reject_for_cost(
            "TEST", atr_pct=1.0, win_rate=0.1, daily_trade_count=5,
        )
        reject2, reason2 = should_reject_for_cost(
            "TEST", atr_pct=1.0, win_rate=0.3, daily_trade_count=5,
        )
        # Both should produce the same result since 0.1 is clamped to 0.3
        assert reject1 == reject2

    def test_illiquid_symbol_higher_cost(self):
        """
        Illiquid symbol (30 bps slippage) has higher cost threshold.
        低流動性幣種（30 bps 滑點）有更高的成本閾值。
        """
        # Illiquid: cost = (0.055+0.3)*2 = 0.71%, min_move = 0.71/0.5*1.3 = 1.846%
        reject, reason = should_reject_for_cost(
            "ILLIQUID", atr_pct=1.0, win_rate=0.5, daily_trade_count=5,
            volume_24h=100_000,
        )
        assert reject is True  # 1.0 < 1.846

        # Same ATR but liquid: cost = 0.13%, min_move = 0.13/0.5*1.3 = 0.338%
        reject2, reason2 = should_reject_for_cost(
            "LIQUID", atr_pct=1.0, win_rate=0.5, daily_trade_count=5,
            volume_24h=2_000_000_000,
        )
        assert reject2 is False  # 1.0 > 0.338

    def test_reason_string_contains_values(self):
        """
        Rejection reason contains ATR, min_move, cost, and win_rate for debugging.
        拒絕原因包含 ATR、最低波動、成本和勝率，便於調試。
        """
        reject, reason = should_reject_for_cost(
            "DEBUG", atr_pct=0.05, win_rate=0.5, daily_trade_count=5,
        )
        assert reject is True
        assert "atr=" in reason
        assert "min=" in reason
        assert "cost=" in reason
        assert "wr=" in reason
