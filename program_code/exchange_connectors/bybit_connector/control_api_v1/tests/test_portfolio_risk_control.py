"""
Tests for Portfolio Correlation Risk Control — EX-01 §6 / GAP-H4
组合相关性风控测试

Covers:
  - Price return tracker
  - Pearson correlation calculation
  - Correlation gate (0.7 threshold)
  - Sector concentration limits
  - Reserve buffer enforcement
  - Portfolio metrics computation
  - Correlation matrix
  - Integration checks (check_new_entry)
  - Thread safety
  - Edge cases
"""

import sys
import math
import threading
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.portfolio_risk_control import (
    PortfolioRiskConfig,
    PortfolioRiskControl,
    PriceReturnTracker,
    pearson_correlation,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def config():
    return PortfolioRiskConfig(
        correlation_threshold=0.7,
        correlation_lookback=20,
        min_data_points=5,
        max_sector_exposure_pct=40.0,
        min_reserve_buffer_pct=30.0,
    )

@pytest.fixture
def prc(config):
    return PortfolioRiskControl(config)


def _feed_correlated_prices(prc, sym_a, sym_b, n=10, correlation="high"):
    """Feed prices that produce high or low correlation / 喂入高/低相关价格"""
    base_a = 50000.0
    base_b = 3000.0
    for i in range(n):
        move = (i % 3 - 1) * 100  # -100, 0, +100 pattern
        prc.record_price(sym_a, base_a + move * (i + 1))
        if correlation == "high":
            prc.record_price(sym_b, base_b + move * (i + 1) * 0.06)  # Same direction
        else:
            prc.record_price(sym_b, base_b - move * (i + 1) * 0.06)  # Opposite direction


def _make_positions(**kwargs):
    """Create positions dict / 创建持仓字典"""
    positions = {}
    for sym, (side, size, price) in kwargs.items():
        positions[sym] = {"side": side, "size": size, "avg_entry_price": price}
    return positions


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Pearson Correlation / 相关系数测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestPearsonCorrelation:
    def test_perfect_positive(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [2.0, 4.0, 6.0, 8.0, 10.0]
        assert abs(pearson_correlation(x, y) - 1.0) < 0.001

    def test_perfect_negative(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [10.0, 8.0, 6.0, 4.0, 2.0]
        assert abs(pearson_correlation(x, y) - (-1.0)) < 0.001

    def test_zero_correlation(self):
        x = [1.0, 0.0, -1.0, 0.0]
        y = [0.0, 1.0, 0.0, -1.0]
        assert abs(pearson_correlation(x, y)) < 0.01

    def test_insufficient_data(self):
        assert pearson_correlation([1.0], [2.0]) == 0.0

    def test_zero_variance(self):
        x = [5.0, 5.0, 5.0, 5.0]
        y = [1.0, 2.0, 3.0, 4.0]
        assert pearson_correlation(x, y) == 0.0

    def test_different_lengths(self):
        """Should use minimum length / 应使用最小长度"""
        x = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        y = [2.0, 4.0, 6.0]
        c = pearson_correlation(x, y)
        assert abs(c - 1.0) < 0.001  # Last 3 of x are perfectly correlated with y


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Price Return Tracker / 价格回报追踪器测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestPriceReturnTracker:
    def test_record_and_get_returns(self):
        tracker = PriceReturnTracker(lookback=10)
        tracker.record_price("BTCUSDT", 100.0)
        tracker.record_price("BTCUSDT", 110.0)
        tracker.record_price("BTCUSDT", 121.0)

        returns = tracker.get_returns("BTCUSDT")
        assert len(returns) == 2
        assert abs(returns[0] - 0.1) < 0.001  # 10% return
        assert abs(returns[1] - 0.1) < 0.001  # 10% return

    def test_has_sufficient_data(self):
        tracker = PriceReturnTracker()
        tracker.record_price("BTCUSDT", 100.0)
        tracker.record_price("BTCUSDT", 110.0)
        assert not tracker.has_sufficient_data("BTCUSDT", 5)

        for i in range(5):
            tracker.record_price("BTCUSDT", 100 + i * 10)
        assert tracker.has_sufficient_data("BTCUSDT", 5)

    def test_unknown_symbol(self):
        tracker = PriceReturnTracker()
        assert tracker.get_returns("UNKNOWN") == []
        assert not tracker.has_sufficient_data("UNKNOWN", 1)

    def test_tracked_symbols(self):
        tracker = PriceReturnTracker()
        tracker.record_price("BTCUSDT", 100)
        tracker.record_price("ETHUSDT", 50)
        syms = tracker.get_tracked_symbols()
        assert "BTCUSDT" in syms
        assert "ETHUSDT" in syms


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Correlation Gate / 相关性门控测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestCorrelationGate:
    def test_high_correlation_blocks_entry(self, prc):
        """High correlation (>0.7) should block same-direction entry / 高相关应阻止同方向开仓"""
        _feed_correlated_prices(prc, "BTCUSDT", "ETHUSDT", n=10, correlation="high")
        positions = _make_positions(BTCUSDT=("Buy", 0.1, 50000))  # 5k notional, small

        allowed, reason = prc.check_new_entry(
            symbol="ETHUSDT", side="Buy", notional=3000,
            positions=positions, balance=500000,  # Large balance to avoid sector/reserve blocks
        )
        assert not allowed
        assert "correlation" in reason

    def test_low_correlation_allows_entry(self, prc):
        """Low correlation should allow entry / 低相关应允许开仓"""
        _feed_correlated_prices(prc, "BTCUSDT", "ETHUSDT", n=10, correlation="low")
        positions = _make_positions(BTCUSDT=("Buy", 0.1, 50000))

        allowed, reason = prc.check_new_entry(
            symbol="ETHUSDT", side="Buy", notional=3000,
            positions=positions, balance=500000,
        )
        assert allowed

    def test_opposite_direction_not_blocked(self, prc):
        """High correlation but opposite side should be allowed / 高相关反方向应允许"""
        _feed_correlated_prices(prc, "BTCUSDT", "ETHUSDT", n=10, correlation="high")
        positions = _make_positions(BTCUSDT=("Buy", 0.1, 50000))

        allowed, reason = prc.check_new_entry(
            symbol="ETHUSDT", side="Sell", notional=3000,
            positions=positions, balance=500000,
        )
        assert allowed

    def test_insufficient_data_allows_entry(self, prc):
        """Not enough price data should not block / 数据不足不应阻止"""
        prc.record_price("BTCUSDT", 50000)
        prc.record_price("ETHUSDT", 3000)
        positions = _make_positions(BTCUSDT=("Buy", 0.1, 50000))

        allowed, _ = prc.check_new_entry(
            symbol="ETHUSDT", side="Buy", notional=3000,
            positions=positions, balance=500000,
        )
        assert allowed

    def test_same_symbol_not_checked(self, prc):
        """Adding to existing position should not check correlation with itself"""
        _feed_correlated_prices(prc, "BTCUSDT", "ETHUSDT", n=10, correlation="high")
        positions = _make_positions(BTCUSDT=("Buy", 0.1, 50000))

        allowed, _ = prc.check_new_entry(
            symbol="BTCUSDT", side="Buy", notional=5000,
            positions=positions, balance=500000,
        )
        assert allowed  # Adding to existing, no correlation check with self


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Sector Concentration / 行业集中度测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestSectorConcentration:
    def test_sector_limit_exceeded(self, prc):
        """Exceeding sector limit should block / 超过行业限制应阻止"""
        positions = _make_positions(
            BTCUSDT=("Buy", 1.0, 50000),  # L1: 50000 notional
        )
        # Balance=100000, L1 already at 50%, adding ETHUSDT (L1) would exceed 40% if total > 40k
        allowed, reason = prc.check_new_entry(
            symbol="ETHUSDT", side="Buy", notional=5000,
            positions=positions, balance=100000,
        )
        assert not allowed
        assert "sector_L1" in reason

    def test_sector_within_limit(self, prc):
        """Within sector limit should allow / 行业限制内应允许"""
        positions = _make_positions(
            BTCUSDT=("Buy", 0.1, 50000),  # L1: 5000 notional
        )
        allowed, _ = prc.check_new_entry(
            symbol="ETHUSDT", side="Buy", notional=3000,
            positions=positions, balance=100000,
        )
        assert allowed

    def test_different_sector_allowed(self, prc):
        """Different sector should be independent / 不同行业应独立"""
        positions = _make_positions(
            BTCUSDT=("Buy", 0.5, 50000),  # L1: 25000
        )
        allowed, _ = prc.check_new_entry(
            symbol="AAVEUSDT", side="Buy", notional=5000,  # DeFi sector
            positions=positions, balance=100000,
        )
        assert allowed

    def test_unknown_sector_passes(self, prc):
        """Unknown sector should pass / 未知行业应通过"""
        positions = _make_positions(BTCUSDT=("Buy", 1.0, 50000))
        allowed, _ = prc.check_new_entry(
            symbol="XYZUSDT", side="Buy", notional=5000,
            positions=positions, balance=100000,
        )
        # Unknown sector, so sector check passes (may fail on other checks)
        # This specifically tests sector check only
        assert allowed or "sector" not in _  # sector check doesn't block unknown sectors


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Reserve Buffer / 储备缓冲测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestReserveBuffer:
    def test_reserve_buffer_violated(self, prc):
        """Exceeding max allocation should block / 超过最大分配应阻止"""
        positions = _make_positions(
            BTCUSDT=("Buy", 1.0, 50000),  # 50k notional
            ETHUSDT=("Buy", 5.0, 3000),   # 15k notional = 65k total
        )
        # balance=100k, 65k used = 65%, reserve=35%. Adding 10k → 75% → reserve=25% < 30%
        allowed, reason = prc.check_new_entry(
            symbol="SOLUSDT", side="Buy", notional=10000,
            positions=positions, balance=100000,
        )
        assert not allowed
        assert "reserve_buffer" in reason

    def test_reserve_buffer_ok(self, prc):
        """Within reserve buffer should allow / 储备缓冲内应允许"""
        positions = _make_positions(
            BTCUSDT=("Buy", 0.5, 50000),  # 25k notional
        )
        # 25k + 5k = 30k / 100k = 30% used, 70% reserve > 30% min
        allowed, _ = prc.check_new_entry(
            symbol="ETHUSDT", side="Buy", notional=5000,
            positions=positions, balance=100000,
        )
        assert allowed

    def test_zero_balance(self, prc):
        """Zero balance should block / 零余额应阻止"""
        allowed, reason = prc.check_new_entry(
            symbol="BTCUSDT", side="Buy", notional=1000,
            positions={}, balance=0,
        )
        assert not allowed


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Correlation Matrix / 相关矩阵测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestCorrelationMatrix:
    def test_matrix_diagonal_is_one(self, prc):
        for i in range(10):
            prc.record_price("BTCUSDT", 50000 + i * 100)
            prc.record_price("ETHUSDT", 3000 + i * 5)

        matrix = prc.compute_correlation_matrix(["BTCUSDT", "ETHUSDT"])
        assert matrix["BTCUSDT"]["BTCUSDT"] == 1.0
        assert matrix["ETHUSDT"]["ETHUSDT"] == 1.0

    def test_matrix_symmetry(self, prc):
        for i in range(10):
            prc.record_price("BTCUSDT", 50000 + i * 100)
            prc.record_price("ETHUSDT", 3000 + i * 5)

        matrix = prc.compute_correlation_matrix(["BTCUSDT", "ETHUSDT"])
        assert abs(matrix["BTCUSDT"]["ETHUSDT"] - matrix["ETHUSDT"]["BTCUSDT"]) < 0.001

    def test_empty_matrix(self, prc):
        matrix = prc.compute_correlation_matrix([])
        assert matrix == {}


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Portfolio Metrics / 组合度量测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestPortfolioMetrics:
    def test_basic_metrics(self, prc):
        positions = _make_positions(
            BTCUSDT=("Buy", 1.0, 50000),
            ETHUSDT=("Buy", 5.0, 3000),
        )
        metrics = prc.get_portfolio_metrics(positions, balance=100000)
        assert metrics["total_exposure"] == 65000
        assert metrics["total_exposure_pct"] == 65.0
        assert metrics["reserve_buffer_pct"] == 35.0
        assert metrics["position_count"] == 2

    def test_sector_exposure_breakdown(self, prc):
        positions = _make_positions(
            BTCUSDT=("Buy", 1.0, 50000),  # L1
            AAVEUSDT=("Buy", 10.0, 100),  # DeFi
        )
        metrics = prc.get_portfolio_metrics(positions, balance=100000)
        assert "L1" in metrics["sector_exposures_pct"]
        assert "DeFi" in metrics["sector_exposures_pct"]

    def test_metrics_with_prices(self, prc):
        positions = _make_positions(BTCUSDT=("Buy", 1.0, 50000))
        market_prices = {"BTCUSDT": 55000}  # Price went up
        metrics = prc.get_portfolio_metrics(positions, balance=100000, market_prices=market_prices)
        assert metrics["total_exposure"] == 55000  # Uses market price

    def test_empty_portfolio_metrics(self, prc):
        metrics = prc.get_portfolio_metrics({}, balance=100000)
        assert metrics["total_exposure"] == 0
        assert metrics["position_count"] == 0
        assert metrics["reserve_buffer_pct"] == 100.0


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Audit Callback / 审计回调测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditCallback:
    def test_audit_on_block(self):
        audits = []
        config = PortfolioRiskConfig(min_reserve_buffer_pct=30.0)
        prc = PortfolioRiskControl(config, audit_callback=lambda r: audits.append(r))

        positions = _make_positions(BTCUSDT=("Buy", 1.5, 50000))  # 75k / 100k = 75%
        prc.check_new_entry("ETHUSDT", "Buy", 5000, positions, balance=100000)
        assert len(audits) == 1
        assert "reserve_buffer" in audits[0]["event_type"]


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Status / 状态测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestStatus:
    def test_status_after_checks(self, prc):
        prc.check_new_entry("BTCUSDT", "Buy", 1000, {}, balance=100000)
        status = prc.get_status()
        assert status["checks_performed"] == 1
        assert "correlation_threshold" in status["config"]

    def test_block_rate(self, prc):
        # Block one (reserve buffer)
        positions = _make_positions(BTCUSDT=("Buy", 1.5, 50000))
        prc.check_new_entry("ETHUSDT", "Buy", 5000, positions, balance=100000)
        # Allow one
        prc.check_new_entry("ETHUSDT", "Buy", 1000, {}, balance=100000)

        status = prc.get_status()
        assert status["checks_performed"] == 2
        assert status["entries_blocked"] == 1
        assert status["block_rate_pct"] == 50.0


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Thread Safety / 线程安全测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestThreadSafety:
    def test_concurrent_checks(self, prc):
        errors = []

        def worker():
            try:
                for _ in range(10):
                    prc.record_price("BTCUSDT", 50000)
                    prc.check_new_entry("BTCUSDT", "Buy", 1000, {}, balance=100000)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Edge Cases / 边界情况测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_no_positions_allows_entry(self, prc):
        allowed, _ = prc.check_new_entry("BTCUSDT", "Buy", 1000, {}, balance=100000)
        assert allowed

    def test_zero_size_position_ignored(self, prc):
        """Zero-size positions should be ignored in correlation check"""
        _feed_correlated_prices(prc, "BTCUSDT", "ETHUSDT", n=10, correlation="high")
        positions = {"BTCUSDT": {"side": "Buy", "size": 0, "avg_entry_price": 50000}}

        allowed, _ = prc.check_new_entry("ETHUSDT", "Buy", 3000, positions, balance=100000)
        assert allowed

    def test_market_prices_override(self, prc):
        positions = _make_positions(BTCUSDT=("Buy", 1.0, 50000))
        market_prices = {"BTCUSDT": 60000}

        metrics = prc.get_portfolio_metrics(positions, balance=100000, market_prices=market_prices)
        assert metrics["total_exposure"] == 60000
