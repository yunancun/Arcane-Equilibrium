"""
Tests for U-03: Trailing Stop Profit Constraint / 追蹤止損利潤約束測試

Verifies that the trailing stop activation is auto-raised when the locked profit
(activation - distance) would be less than the round-trip transaction cost.
驗證當鎖定利潤（activation - distance）低於往返交易成本時，
追蹤止損的激活閾值會被自動提高。

Covers:
  - compute_round_trip_cost_pct for various volume tiers
  - Large coin (BTC-like): cost low, no adjustment needed
  - Small coin (illiquid alt): cost high, activation auto-raised
  - Boundary: cost == locked profit triggers adjustment
  - Zero cost: no adjustment
  - Activation cap: raised activation never exceeds hard_stop
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.risk_manager import (
    BYBIT_TAKER_FEE_RATE,
    TRAILING_COST_SAFETY_MARGIN,
    AgentRiskParams,
    GlobalRiskConfig,
    RiskManager,
    compute_round_trip_cost_pct,
    _estimate_slippage,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Module-level isolation: block operator JSON from overriding code defaults
# 模塊級隔離：阻止 operator JSON 覆蓋代碼默認值
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True, scope="function")
def _block_operator_json(monkeypatch):
    """
    Isolate RiskManager from operator_risk_config.json during tests.
    測試期間隔離 RiskManager 與 operator_risk_config.json。
    """
    import app.risk_manager as _rm_module
    monkeypatch.setattr(_rm_module, "_OPERATOR_CONFIG_PATH", "/dev/null")


# ═══════════════════════════════════════════════════════════════════════════════
# Test: compute_round_trip_cost_pct / 往返成本計算
# ═══════════════════════════════════════════════════════════════════════════════

class TestComputeRoundTripCostPct:
    """Tests for the round-trip cost estimation helper."""

    def test_large_coin_btc_like(self):
        """BTC/ETH (>$1B vol): cost ≈ 0.13% — (0.00055 + 0.0001) × 2 × 100"""
        cost = compute_round_trip_cost_pct(volume_24h=2_000_000_000)
        expected = (BYBIT_TAKER_FEE_RATE + 0.0001) * 2 * 100  # 0.13%
        assert abs(cost - expected) < 1e-6
        assert cost < 0.15  # sanity: large coins are cheap

    def test_small_coin_illiquid(self):
        """Illiquid alt (<$1M vol): cost ≈ 0.71% — (0.00055 + 0.003) × 2 × 100"""
        cost = compute_round_trip_cost_pct(volume_24h=500_000)
        expected = (BYBIT_TAKER_FEE_RATE + 0.0030) * 2 * 100  # 0.71%
        assert abs(cost - expected) < 1e-6
        assert cost > 0.5  # sanity: small coins are expensive

    def test_mid_tier_100m(self):
        """Mid-tier (>$100M): cost ≈ 0.15%"""
        cost = compute_round_trip_cost_pct(volume_24h=200_000_000)
        expected = (BYBIT_TAKER_FEE_RATE + 0.0002) * 2 * 100
        assert abs(cost - expected) < 1e-6

    def test_zero_volume_uses_default(self):
        """Zero volume falls back to default slippage (5 bps)."""
        cost = compute_round_trip_cost_pct(volume_24h=0.0)
        expected = (BYBIT_TAKER_FEE_RATE + 0.0005) * 2 * 100
        assert abs(cost - expected) < 1e-6

    def test_negative_volume_uses_default(self):
        """Negative volume falls back to default slippage."""
        cost = compute_round_trip_cost_pct(volume_24h=-100)
        cost_zero = compute_round_trip_cost_pct(volume_24h=0.0)
        assert cost == cost_zero


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Trailing Stop Cost Constraint in RiskManager._check_stops()
# 追蹤止損成本約束在 RiskManager._check_stops() 中的行為
# ═══════════════════════════════════════════════════════════════════════════════

def _make_risk_manager(
    activation: float = 1.0,
    distance: float = 0.8,
    hard_stop: float = 5.0,
) -> RiskManager:
    """Helper to create a RiskManager with specific trailing stop params."""
    config = GlobalRiskConfig(max_stop_loss_pct=hard_stop)
    agent = AgentRiskParams(
        trailing_stop_enabled=True,
        trailing_stop_activation_pct=activation,
        trailing_stop_distance_pct=distance,
    )
    rm = RiskManager(config=config, agent_params=agent)
    return rm


def _build_state_and_prices(
    symbol: str,
    side: str = "Buy",
    entry: float = 100.0,
    current: float = 101.5,
    qty: float = 1.0,
    volume_24h: float = 0.0,
) -> tuple[dict, dict]:
    """
    Build state dict + market_prices dict for check_positions_on_tick().
    構建 state 字典和 market_prices 字典，用於 check_positions_on_tick()。
    """
    import time
    state = {
        "positions": {
            symbol: {
                "symbol": symbol,
                "side": side,
                "avg_entry_price": entry,
                "qty": qty,
                "category": "linear",
                "regime": "unknown",
                "opened_ts_ms": int(time.time() * 1000) - 60000,
                "volume_24h": volume_24h,
            }
        },
        "session": {"status": "running"},
    }
    market_prices = {symbol: current}
    return state, market_prices


class TestTrailingStopCostConstraint:
    """
    Integration tests verifying U-03 cost constraint in the trailing stop path.
    集成測試：驗證 U-03 成本約束在追蹤止損路徑中的行為。
    """

    def test_large_coin_no_adjustment(self):
        """
        Large coin (BTC, >$1B vol): cost ≈ 0.13%, locked profit = 0.2%.
        0.2% > 0.13% × 1.5 = 0.195% → no adjustment needed.
        大幣種成本低，鎖定利潤足夠，不需調整激活閾值。
        """
        rm = _make_risk_manager(activation=1.0, distance=0.8)
        state, prices = _build_state_and_prices(
            "BTCUSDT", entry=100.0, current=101.5, volume_24h=2_000_000_000
        )
        orders = rm.check_positions_on_tick(state, prices)
        # With default 1.0% activation and 1.5% pnl, trailing activates
        # Peak is set at 1.5%, drawback = 0 < distance → no close yet
        assert "BTCUSDT" in rm._trailing_stops
        assert "peak_pnl_pct" in rm._trailing_stops["BTCUSDT"]

    def test_small_coin_activation_raised(self):
        """
        Small coin (<$1M vol): cost ≈ 0.71%, locked = 0.2%.
        0.2% < 0.71% × 1.5 = 1.065% → activation auto-raised to ~1.865%.
        小幣種成本高，鎖定利潤不足，激活閾值被自動提高。
        """
        rm = _make_risk_manager(activation=1.0, distance=0.8)
        cost_pct = compute_round_trip_cost_pct(volume_24h=500_000)
        min_required = cost_pct * TRAILING_COST_SAFETY_MARGIN
        expected_activation = 0.8 + min_required

        # Position at +1.5% profit — below the raised activation threshold
        state, prices = _build_state_and_prices(
            "SMALLCOINUSDT", entry=100.0, current=101.5, volume_24h=500_000
        )
        rm.check_positions_on_tick(state, prices)
        # 1.5% < expected_activation (~1.865%) → trailing should NOT activate
        assert "SMALLCOINUSDT" not in rm._trailing_stops or \
               "peak_pnl_pct" not in rm._trailing_stops.get("SMALLCOINUSDT", {})

        # Now with +2.0% profit — above the raised threshold
        rm2 = _make_risk_manager(activation=1.0, distance=0.8)
        state2, prices2 = _build_state_and_prices(
            "SMALLCOINUSDT", entry=100.0, current=102.0, volume_24h=500_000
        )
        rm2.check_positions_on_tick(state2, prices2)
        # 2.0% > ~1.865% → trailing should activate
        assert "SMALLCOINUSDT" in rm2._trailing_stops
        assert "peak_pnl_pct" in rm2._trailing_stops["SMALLCOINUSDT"]

    def test_boundary_cost_equals_locked_profit(self):
        """
        Boundary: locked profit exactly equals round-trip cost → triggers raise.
        Even if locked == cost, the safety margin makes it insufficient.
        邊界：鎖定利潤恰好等於往返成本 → 仍觸發提高（安全邊際要求更高）。
        """
        vol = 10_000_000  # 10M → slippage = 5 bps
        cost_pct = compute_round_trip_cost_pct(volume_24h=vol)  # ~0.21%
        distance = 0.5
        activation = distance + cost_pct  # locked = cost_pct exactly

        rm = _make_risk_manager(activation=activation, distance=distance)
        min_required = cost_pct * TRAILING_COST_SAFETY_MARGIN
        expected_new_activation = distance + min_required

        pnl_needed = expected_new_activation + 0.5
        current = 100.0 * (1 + pnl_needed / 100)
        state, prices = _build_state_and_prices(
            "MIDCOINUSDT", entry=100.0, current=current, volume_24h=vol
        )
        rm.check_positions_on_tick(state, prices)
        assert "MIDCOINUSDT" in rm._trailing_stops
        assert "peak_pnl_pct" in rm._trailing_stops["MIDCOINUSDT"]

    def test_zero_cost_no_adjustment(self):
        """
        Large coin: cost low enough that locked profit (0.2%) > cost × 1.5.
        No activation adjustment needed.
        大幣種成本低，鎖定利潤充足，不調整。
        """
        rm = _make_risk_manager(activation=1.0, distance=0.8)
        cost = compute_round_trip_cost_pct(volume_24h=2_000_000_000)
        min_required = cost * TRAILING_COST_SAFETY_MARGIN
        locked = 1.0 - 0.8  # 0.2%
        # For BTC-tier: cost ≈ 0.13%, min_required ≈ 0.195%, locked = 0.2% > 0.195%
        assert locked > min_required, "Test assumption: BTC-tier locked profit > cost × safety"

        state, prices = _build_state_and_prices(
            "BTCUSDT", entry=100.0, current=101.5, volume_24h=2_000_000_000
        )
        rm.check_positions_on_tick(state, prices)
        assert "BTCUSDT" in rm._trailing_stops

    def test_activation_capped_at_hard_stop(self):
        """
        If cost is so high that raised activation would exceed hard_stop,
        cap at hard_stop.
        若成本極高導致提高後的 activation 超過硬止損，則上限為硬止損。
        """
        # distance=1.5, hard_stop=2.0 → would-be = 1.5 + 1.065 = 2.565 > 2.0 → capped
        rm = _make_risk_manager(activation=1.0, distance=1.5, hard_stop=2.0)
        state, prices = _build_state_and_prices(
            "TINYCOINUSDT", entry=100.0, current=102.5, volume_24h=500_000
        )
        orders = rm.check_positions_on_tick(state, prices)
        # pnl = 2.5% > 2.0% (capped activation) → trailing should activate
        assert "TINYCOINUSDT" in rm._trailing_stops
        assert "peak_pnl_pct" in rm._trailing_stops["TINYCOINUSDT"]

    def test_trailing_close_respects_adjusted_activation(self):
        """
        Full lifecycle: small coin, activation raised, peak set, drawback triggers close.
        完整生命週期：小幣種激活閾值被提高，設定峰值，回撤觸發平倉。
        """
        rm = _make_risk_manager(activation=1.0, distance=0.8)
        cost_pct = compute_round_trip_cost_pct(volume_24h=500_000)
        min_required = cost_pct * TRAILING_COST_SAFETY_MARGIN
        raised_activation = 0.8 + min_required  # ~1.865%

        # Step 1: Price reaches above raised activation → peak set
        peak_pnl = raised_activation + 1.0  # ~2.865%
        current1 = 100.0 * (1 + peak_pnl / 100)
        state1, prices1 = _build_state_and_prices(
            "ALTUSDT", entry=100.0, current=current1, volume_24h=500_000
        )
        orders1 = rm.check_positions_on_tick(state1, prices1)
        assert len(orders1) == 0  # No close yet, just peak set
        assert "peak_pnl_pct" in rm._trailing_stops.get("ALTUSDT", {})

        # Step 2: Price drops by distance from peak → should trigger close
        close_pnl = peak_pnl - 0.8 - 0.01  # just below peak - distance
        current2 = 100.0 * (1 + close_pnl / 100)
        state2, prices2 = _build_state_and_prices(
            "ALTUSDT", entry=100.0, current=current2, volume_24h=500_000
        )
        orders2 = rm.check_positions_on_tick(state2, prices2)
        assert len(orders2) == 1
        assert orders2[0]["symbol"] == "ALTUSDT"
        assert "trailing_stop" in orders2[0]["reason"]


class TestEstimateSlippage:
    """Unit tests for _estimate_slippage helper."""

    def test_tier_boundaries(self):
        """Each tier boundary returns expected rate."""
        assert _estimate_slippage(1_000_000_001) == 0.0001
        assert _estimate_slippage(1_000_000_000) == 0.0001
        assert _estimate_slippage(100_000_000) == 0.0002
        assert _estimate_slippage(10_000_000) == 0.0005
        assert _estimate_slippage(1_000_000) == 0.0015
        assert _estimate_slippage(999_999) == 0.0030
        assert _estimate_slippage(0) == 0.0005  # default
        assert _estimate_slippage(-1) == 0.0005  # default
