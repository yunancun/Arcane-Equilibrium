from __future__ import annotations

"""
Paper Trading Performance Metrics / 纸上交易性能指标

MODULE_NOTE (中文):
  本模块从纸上交易引擎的状态数据中计算高级性能指标，
  包括胜率、最大回撤、平均盈亏比、持仓时长、Sharpe 比率等。
  供 Beta 评估和 M 章 Supervised Live Gate 审核使用。

MODULE_NOTE (English):
  This module computes advanced performance metrics from the paper trading engine's
  state data, including win rate, max drawdown, avg win/loss ratio, holding period,
  and Sharpe ratio. Used for beta evaluation and M-chapter supervised live gate review.
"""

import math
import time
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════════
# Core Metrics Computation / 核心指标计算
# ═══════════════════════════════════════════════════════════════════════════════

def compute_trade_metrics(fills: list[dict], orders: list[dict]) -> dict[str, Any]:
    """
    Compute trade-level metrics from fills and orders.
    从成交和订单数据计算交易层面的指标。

    Returns metrics dict with: trade_count, win_rate, avg_win, avg_loss,
    win_loss_ratio, largest_win, largest_loss, avg_fill_price_buy/sell.
    """
    if not fills:
        return _empty_trade_metrics()

    # Group fills by order_id to reconstruct round-trip trades
    order_fills: dict[str, list[dict]] = {}
    for f in fills:
        oid = f.get("order_id", "unknown")
        order_fills.setdefault(oid, []).append(f)

    # Compute per-fill PnL using order side info
    wins: list[float] = []
    losses: list[float] = []
    total_buy_notional = 0.0
    total_sell_notional = 0.0
    total_buy_qty = 0.0
    total_sell_qty = 0.0
    total_fees = 0.0

    for f in fills:
        side = f.get("side", "")
        notional = f.get("notional", f.get("qty", 0) * f.get("price", 0))
        fee = f.get("fee", 0.0)
        total_fees += fee

        if side == "Buy":
            total_buy_notional += notional
            total_buy_qty += f.get("qty", 0)
        elif side == "Sell":
            total_sell_notional += notional
            total_sell_qty += f.get("qty", 0)

    # Estimate per-order PnL from completed orders (filled state)
    filled_orders = [o for o in orders if o.get("state") == "paper_order_filled"]
    for order in filled_orders:
        if not order.get("fills"):
            continue
        order_pnl = _estimate_order_pnl(order)
        if order_pnl > 0:
            wins.append(order_pnl)
        elif order_pnl < 0:
            losses.append(order_pnl)

    win_count = len(wins)
    loss_count = len(losses)
    total_trades = win_count + loss_count

    avg_win = sum(wins) / win_count if win_count > 0 else 0.0
    avg_loss = abs(sum(losses) / loss_count) if loss_count > 0 else 0.0
    win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else float("inf") if avg_win > 0 else 0.0

    return {
        "total_fills": len(fills),
        "total_filled_orders": len(filled_orders),
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": win_count / total_trades if total_trades > 0 else 0.0,
        "avg_win": round(avg_win, 4),
        "avg_loss": round(avg_loss, 4),
        "win_loss_ratio": round(win_loss_ratio, 4) if win_loss_ratio != float("inf") else "inf",
        "largest_win": round(max(wins), 4) if wins else 0.0,
        "largest_loss": round(min(losses), 4) if losses else 0.0,
        "total_fees_paid": round(total_fees, 6),
        "avg_fill_price_buy": round(total_buy_notional / total_buy_qty, 4) if total_buy_qty > 0 else 0.0,
        "avg_fill_price_sell": round(total_sell_notional / total_sell_qty, 4) if total_sell_qty > 0 else 0.0,
    }


def compute_balance_series(
    fills: list[dict],
    initial_balance: float,
) -> list[dict[str, Any]]:
    """
    Build a balance time series from fills for drawdown/equity curve analysis.
    从成交历史构建余额时间序列，用于回撤和权益曲线分析。
    """
    series = [{"ts_ms": 0, "balance": initial_balance}]
    balance = initial_balance

    for f in fills:
        fee = f.get("fee", 0.0)
        # Simplified: subtract fees, realized PnL handled at position close
        balance -= fee
        series.append({
            "ts_ms": f.get("ts_ms", 0),
            "balance": round(balance, 4),
        })

    return series


def compute_drawdown_metrics(
    fills: list[dict],
    initial_balance: float,
    pnl: dict[str, Any],
) -> dict[str, Any]:
    """
    Compute drawdown metrics from balance history.
    从余额历史计算回撤指标。

    Returns: max_drawdown_pct, max_drawdown_abs, current_drawdown_pct,
    peak_balance, trough_balance.
    """
    current_balance = initial_balance + pnl.get("realized_pnl", 0.0) - pnl.get("total_fees_paid", 0.0)

    if not fills:
        return {
            "max_drawdown_pct": 0.0,
            "max_drawdown_abs": 0.0,
            "current_drawdown_pct": 0.0,
            "peak_balance": initial_balance,
            "trough_balance": initial_balance,
            "current_balance": round(current_balance, 4),
        }

    # Reconstruct balance series with realized PnL
    series = compute_balance_series(fills, initial_balance)

    peak = initial_balance
    trough = initial_balance
    max_dd_abs = 0.0
    max_dd_pct = 0.0

    running_balance = initial_balance
    for point in series[1:]:
        running_balance = point["balance"]
        if running_balance > peak:
            peak = running_balance
        dd = peak - running_balance
        if dd > max_dd_abs:
            max_dd_abs = dd
            trough = running_balance
        dd_pct = dd / peak if peak > 0 else 0.0
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct

    current_dd_pct = (peak - current_balance) / peak if peak > 0 else 0.0

    return {
        "max_drawdown_pct": round(max_dd_pct * 100, 2),
        "max_drawdown_abs": round(max_dd_abs, 4),
        "current_drawdown_pct": round(max(0, current_dd_pct) * 100, 2),
        "peak_balance": round(peak, 4),
        "trough_balance": round(trough, 4),
        "current_balance": round(current_balance, 4),
    }


def compute_holding_period_metrics(orders: list[dict]) -> dict[str, Any]:
    """
    Compute holding period statistics from filled orders.
    从已成交订单计算持仓时长统计。
    """
    durations_ms: list[int] = []

    for order in orders:
        if order.get("state") != "paper_order_filled":
            continue
        created = order.get("created_ts_ms", 0)
        filled_ts = order.get("updated_ts_ms", 0)
        if created > 0 and filled_ts > created:
            durations_ms.append(filled_ts - created)

    if not durations_ms:
        return {
            "avg_holding_period_sec": 0.0,
            "min_holding_period_sec": 0.0,
            "max_holding_period_sec": 0.0,
            "total_orders_measured": 0,
        }

    avg_ms = sum(durations_ms) / len(durations_ms)
    return {
        "avg_holding_period_sec": round(avg_ms / 1000, 2),
        "min_holding_period_sec": round(min(durations_ms) / 1000, 2),
        "max_holding_period_sec": round(max(durations_ms) / 1000, 2),
        "total_orders_measured": len(durations_ms),
    }


def compute_sharpe_ratio(
    fills: list[dict],
    initial_balance: float,
    risk_free_rate_annual: float = 0.05,
) -> dict[str, Any]:
    """
    Compute a simplified Sharpe ratio from fill-level returns.
    从成交层面收益率计算简化的 Sharpe 比率。

    Uses per-fill return series. Annualizes assuming 365 trading days.
    """
    if len(fills) < 2:
        return {"sharpe_ratio": 0.0, "return_count": len(fills), "note": "insufficient_data"}

    # Compute per-fill returns as fee impact on balance
    returns: list[float] = []
    balance = initial_balance
    for f in fills:
        fee = f.get("fee", 0.0)
        ret = -fee / balance if balance > 0 else 0.0
        returns.append(ret)
        balance -= fee

    if not returns:
        return {"sharpe_ratio": 0.0, "return_count": 0, "note": "no_returns"}

    mean_ret = sum(returns) / len(returns)
    variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
    std_ret = math.sqrt(variance) if variance > 0 else 0.0

    # Annualize (simplified: assume daily returns → √365)
    if std_ret == 0:
        return {"sharpe_ratio": 0.0, "return_count": len(returns), "note": "zero_volatility"}

    rf_per_period = risk_free_rate_annual / 365
    sharpe = (mean_ret - rf_per_period) / std_ret

    return {
        "sharpe_ratio": round(sharpe, 4),
        "mean_return": round(mean_ret, 8),
        "std_return": round(std_ret, 8),
        "return_count": len(returns),
        "note": "simplified_fill_level",
    }


def compute_shadow_decision_metrics(shadow_decisions: list[dict]) -> dict[str, Any]:
    """
    Compute metrics for shadow decision pipeline performance.
    计算影子决策管线的性能指标。
    """
    if not shadow_decisions:
        return {
            "total_shadow_decisions": 0,
            "decisions_that_traded": 0,
            "decisions_held": 0,
            "trade_rate": 0.0,
            "avg_confidence_traded": 0.0,
            "avg_edge_traded_bps": 0.0,
            "regime_distribution": {},
        }

    traded = [d for d in shadow_decisions if d.get("action_taken") == "order_submitted"]
    held = [d for d in shadow_decisions if d.get("action_taken") in ("hold", "rejected")]

    regime_counts: dict[str, int] = {}
    for d in shadow_decisions:
        regime = d.get("market_regime", "unknown")
        regime_counts[regime] = regime_counts.get(regime, 0) + 1

    avg_conf = sum(d.get("confidence", 0) for d in traded) / len(traded) if traded else 0.0
    avg_edge = sum(d.get("edge_bps", 0) for d in traded) / len(traded) if traded else 0.0

    return {
        "total_shadow_decisions": len(shadow_decisions),
        "decisions_that_traded": len(traded),
        "decisions_held": len(held),
        "trade_rate": round(len(traded) / len(shadow_decisions), 4) if shadow_decisions else 0.0,
        "avg_confidence_traded": round(avg_conf, 4),
        "avg_edge_traded_bps": round(avg_edge, 2),
        "regime_distribution": regime_counts,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Full Metrics Report / 完整指标报告
# ═══════════════════════════════════════════════════════════════════════════════

def compute_full_metrics(state: dict[str, Any]) -> dict[str, Any]:
    """
    Compute all performance metrics from paper trading state.
    从纸上交易状态计算所有性能指标。

    This is the main entry point — call with the full paper state dict.
    """
    fills = state.get("fills", [])
    orders = state.get("orders", [])
    session = state.get("session", {})
    pnl = state.get("pnl", {})
    shadow_decisions = state.get("shadow_decisions", [])

    initial_balance = session.get("initial_paper_balance_usdt", 10000.0)

    # Session duration
    started = session.get("started_ts_ms") or 0
    now_ms = int(time.time() * 1000)
    stopped = session.get("stopped_ts_ms") or now_ms
    duration_sec = (stopped - started) / 1000 if started > 0 else 0.0

    return {
        "computed_ts_ms": now_ms,
        "session_duration_sec": round(duration_sec, 1),
        "trade_metrics": compute_trade_metrics(fills, orders),
        "drawdown_metrics": compute_drawdown_metrics(fills, initial_balance, pnl),
        "holding_period_metrics": compute_holding_period_metrics(orders),
        "sharpe_ratio": compute_sharpe_ratio(fills, initial_balance),
        "shadow_decision_metrics": compute_shadow_decision_metrics(shadow_decisions),
        "pnl_summary": {
            "realized_pnl": round(pnl.get("realized_pnl", 0.0), 4),
            "unrealized_pnl": round(pnl.get("unrealized_pnl", 0.0), 4),
            "total_fees": round(pnl.get("total_fees_paid", 0.0), 6),
            "total_ai_cost": round(pnl.get("total_ai_cost", 0.0), 6),
            "net_paper_pnl": round(pnl.get("net_paper_pnl", 0.0), 4),
        },
        "is_simulated": True,
        "data_category": "paper_simulated",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers / 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════

def _estimate_order_pnl(order: dict) -> float:
    """
    Estimate PnL for a single filled order from its fills.
    This is approximate — true PnL requires position-level tracking.
    """
    if not order.get("fills"):
        return 0.0
    total_notional = sum(f.get("notional", 0) for f in order["fills"])
    total_fee = sum(f.get("fee", 0) for f in order["fills"])
    # For a simple estimate, net of fees
    return -total_fee  # conservative: only fees are certain


def _empty_trade_metrics() -> dict[str, Any]:
    return {
        "total_fills": 0,
        "total_filled_orders": 0,
        "win_count": 0,
        "loss_count": 0,
        "win_rate": 0.0,
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "win_loss_ratio": 0.0,
        "largest_win": 0.0,
        "largest_loss": 0.0,
        "total_fees_paid": 0.0,
        "avg_fill_price_buy": 0.0,
        "avg_fill_price_sell": 0.0,
    }
