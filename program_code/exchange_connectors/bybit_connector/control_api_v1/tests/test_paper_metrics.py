"""
Tests for Paper Trading Performance Metrics / 纸上交易性能指标测试

覆盖范围 / Coverage:
  - Trade metrics (win rate, avg win/loss, etc.)
  - Drawdown metrics (max drawdown, peak/trough)
  - Holding period metrics
  - Sharpe ratio computation
  - Shadow decision metrics
  - Full metrics report
  - Edge cases (empty data, zero values)
"""

import math
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.paper_trading_metrics import (
    compute_balance_series,
    compute_drawdown_metrics,
    compute_full_metrics,
    compute_holding_period_metrics,
    compute_shadow_decision_metrics,
    compute_sharpe_ratio,
    compute_trade_metrics,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Test Data Helpers / 测试数据
# ═══════════════════════════════════════════════════════════════════════════════

def _make_fill(*, side="Buy", qty=0.01, price=50000.0, fee=0.275, ts_ms=None, order_id="ord1"):
    return {
        "fill_id": f"fill_{id(side)}",
        "order_id": order_id,
        "symbol": "BTCUSDT",
        "side": side,
        "qty": qty,
        "price": price,
        "fee": fee,
        "notional": qty * price,
        "ts_ms": ts_ms or int(time.time() * 1000),
        "is_simulated": True,
    }


def _make_order(*, state="paper_order_filled", side="Buy", fills=None, created_ts_ms=None, updated_ts_ms=None):
    now = int(time.time() * 1000)
    return {
        "order_id": f"ord_{id(state)}",
        "symbol": "BTCUSDT",
        "side": side,
        "order_type": "market",
        "qty": 0.01,
        "state": state,
        "fills": fills or [],
        "created_ts_ms": created_ts_ms or now - 5000,
        "updated_ts_ms": updated_ts_ms or now,
    }


def _make_shadow_decision(*, action_taken="order_submitted", confidence=0.8, edge_bps=15.0, market_regime="trending_up"):
    return {
        "decision_id": f"sdec_{id(action_taken)}",
        "action_taken": action_taken,
        "confidence": confidence,
        "edge_bps": edge_bps,
        "market_regime": market_regime,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Trade Metrics / 测试：交易指标
# ═══════════════════════════════════════════════════════════════════════════════

class TestTradeMetrics:
    def test_empty_fills(self):
        result = compute_trade_metrics([], [])
        assert result["total_fills"] == 0
        assert result["win_rate"] == 0.0

    def test_single_buy_fill(self):
        fills = [_make_fill(side="Buy", qty=0.01, price=50000, fee=0.275)]
        result = compute_trade_metrics(fills, [])
        assert result["total_fills"] == 1
        assert result["total_fees_paid"] == 0.275
        assert result["avg_fill_price_buy"] == 50000.0

    def test_buy_and_sell_fills(self):
        fills = [
            _make_fill(side="Buy", qty=0.01, price=50000, fee=0.275, order_id="o1"),
            _make_fill(side="Sell", qty=0.01, price=51000, fee=0.2805, order_id="o2"),
        ]
        result = compute_trade_metrics(fills, [])
        assert result["total_fills"] == 2
        assert result["avg_fill_price_buy"] == 50000.0
        assert result["avg_fill_price_sell"] == 51000.0

    def test_with_filled_orders(self):
        fill = _make_fill(side="Buy", qty=0.01, price=50000, fee=0.275)
        order = _make_order(state="paper_order_filled", fills=[fill])
        result = compute_trade_metrics([fill], [order])
        assert result["total_filled_orders"] == 1

    def test_working_orders_ignored(self):
        fill = _make_fill()
        order = _make_order(state="paper_order_working", fills=[fill])
        result = compute_trade_metrics([fill], [order])
        assert result["total_filled_orders"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Balance Series / 测试：余额序列
# ═══════════════════════════════════════════════════════════════════════════════

class TestBalanceSeries:
    def test_empty_fills(self):
        series = compute_balance_series([], 10000.0)
        assert len(series) == 1
        assert series[0]["balance"] == 10000.0

    def test_fees_deducted(self):
        fills = [
            _make_fill(fee=5.0),
            _make_fill(fee=3.0),
        ]
        series = compute_balance_series(fills, 10000.0)
        assert len(series) == 3
        assert series[1]["balance"] == 9995.0
        assert series[2]["balance"] == 9992.0


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Drawdown Metrics / 测试：回撤指标
# ═══════════════════════════════════════════════════════════════════════════════

class TestDrawdownMetrics:
    def test_no_fills(self):
        result = compute_drawdown_metrics([], 10000.0, {})
        assert result["max_drawdown_pct"] == 0.0
        assert result["peak_balance"] == 10000.0

    def test_fees_cause_drawdown(self):
        fills = [_make_fill(fee=100.0), _make_fill(fee=50.0)]
        result = compute_drawdown_metrics(fills, 10000.0, {"realized_pnl": 0.0, "total_fees_paid": 150.0})
        assert result["max_drawdown_abs"] > 0
        assert result["max_drawdown_pct"] > 0

    def test_peak_tracking(self):
        fills = [
            _make_fill(fee=0.0),   # no change
            _make_fill(fee=500.0),  # drop
        ]
        result = compute_drawdown_metrics(fills, 10000.0, {"realized_pnl": 0.0, "total_fees_paid": 500.0})
        assert result["peak_balance"] == 10000.0
        assert result["max_drawdown_abs"] == 500.0


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Holding Period / 测试：持仓时长
# ═══════════════════════════════════════════════════════════════════════════════

class TestHoldingPeriod:
    def test_no_orders(self):
        result = compute_holding_period_metrics([])
        assert result["total_orders_measured"] == 0

    def test_filled_orders(self):
        now = int(time.time() * 1000)
        orders = [
            _make_order(state="paper_order_filled", created_ts_ms=now - 10000, updated_ts_ms=now),
            _make_order(state="paper_order_filled", created_ts_ms=now - 20000, updated_ts_ms=now),
        ]
        result = compute_holding_period_metrics(orders)
        assert result["total_orders_measured"] == 2
        assert result["avg_holding_period_sec"] == 15.0
        assert result["min_holding_period_sec"] == 10.0
        assert result["max_holding_period_sec"] == 20.0

    def test_non_filled_orders_excluded(self):
        orders = [_make_order(state="paper_order_canceled")]
        result = compute_holding_period_metrics(orders)
        assert result["total_orders_measured"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Sharpe Ratio / 测试：Sharpe 比率
# ═══════════════════════════════════════════════════════════════════════════════

class TestSharpeRatio:
    def test_insufficient_data(self):
        result = compute_sharpe_ratio([], 10000.0)
        assert result["sharpe_ratio"] == 0.0
        assert result["note"] == "insufficient_data"

    def test_single_fill(self):
        result = compute_sharpe_ratio([_make_fill()], 10000.0)
        assert result["note"] == "insufficient_data"

    def test_multiple_fills(self):
        fills = [_make_fill(fee=1.0) for _ in range(10)]
        result = compute_sharpe_ratio(fills, 10000.0)
        assert "sharpe_ratio" in result
        assert result["return_count"] == 10

    def test_zero_volatility(self):
        fills = [_make_fill(fee=0.0), _make_fill(fee=0.0), _make_fill(fee=0.0)]
        result = compute_sharpe_ratio(fills, 10000.0)
        assert result["note"] == "zero_volatility"


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Shadow Decision Metrics / 测试：影子决策指标
# ═══════════════════════════════════════════════════════════════════════════════

class TestShadowDecisionMetrics:
    def test_empty(self):
        result = compute_shadow_decision_metrics([])
        assert result["total_shadow_decisions"] == 0

    def test_mixed_decisions(self):
        decisions = [
            _make_shadow_decision(action_taken="order_submitted", confidence=0.8, edge_bps=15.0),
            _make_shadow_decision(action_taken="order_submitted", confidence=0.7, edge_bps=10.0),
            _make_shadow_decision(action_taken="hold", confidence=0.3, edge_bps=2.0),
        ]
        result = compute_shadow_decision_metrics(decisions)
        assert result["total_shadow_decisions"] == 3
        assert result["decisions_that_traded"] == 2
        assert result["decisions_held"] == 1
        assert result["trade_rate"] == round(2 / 3, 4)
        assert result["avg_confidence_traded"] == 0.75

    def test_regime_distribution(self):
        decisions = [
            _make_shadow_decision(market_regime="trending_up"),
            _make_shadow_decision(market_regime="trending_up"),
            _make_shadow_decision(market_regime="ranging"),
        ]
        result = compute_shadow_decision_metrics(decisions)
        assert result["regime_distribution"]["trending_up"] == 2
        assert result["regime_distribution"]["ranging"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Full Metrics Report / 测试：完整指标报告
# ═══════════════════════════════════════════════════════════════════════════════

class TestFullMetrics:
    def test_empty_state(self):
        state = {
            "fills": [],
            "orders": [],
            "session": {"initial_paper_balance_usdt": 10000.0},
            "pnl": {},
            "shadow_decisions": [],
        }
        result = compute_full_metrics(state)
        assert result["is_simulated"] is True
        assert result["data_category"] == "paper_simulated"
        assert "trade_metrics" in result
        assert "drawdown_metrics" in result
        assert "holding_period_metrics" in result
        assert "sharpe_ratio" in result
        assert "shadow_decision_metrics" in result
        assert "pnl_summary" in result

    def test_with_data(self):
        now = int(time.time() * 1000)
        fills = [_make_fill(fee=0.275)]
        orders = [_make_order(state="paper_order_filled", fills=fills, created_ts_ms=now - 5000)]
        state = {
            "fills": fills,
            "orders": orders,
            "session": {
                "initial_paper_balance_usdt": 10000.0,
                "started_ts_ms": now - 60000,
            },
            "pnl": {
                "realized_pnl": 5.0,
                "unrealized_pnl": 2.0,
                "total_fees_paid": 0.275,
                "total_ai_cost": 0.01,
                "net_paper_pnl": 6.715,
            },
            "shadow_decisions": [
                _make_shadow_decision(action_taken="order_submitted"),
            ],
        }
        result = compute_full_metrics(state)
        assert result["trade_metrics"]["total_fills"] == 1
        assert result["pnl_summary"]["net_paper_pnl"] == 6.715
        assert result["shadow_decision_metrics"]["total_shadow_decisions"] == 1
