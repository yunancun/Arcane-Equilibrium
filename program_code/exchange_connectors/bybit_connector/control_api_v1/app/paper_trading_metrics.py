from __future__ import annotations

"""
Paper Trading Performance Metrics / 纸上交易性能指标

MODULE_NOTE (中文):
  本模块从纸上交易引擎的状态数据中计算高级性能指标，
  包括胜率、最大回撤、平均盈亏比、持仓时长、Sharpe 比率等。
  供 Beta 评估和 M 章 Supervised Live Gate 审核使用。

  v2 修复（2026-03-27 审核）：
  - 胜率和 Sharpe 现在基于真实交易 PnL 计算（而非仅 fee）
  - 余额序列包含 realized PnL（而非仅 fee 扣减）
  - _estimate_order_pnl 使用 position closed_position_pnl 或 per-symbol 配对

MODULE_NOTE (English):
  This module computes advanced performance metrics from the paper trading engine's
  state data. v2 fixes: metrics now use real trade PnL (not just fees).
"""

import math
import time
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════════
# Core Metrics Computation / 核心指标计算
# ═══════════════════════════════════════════════════════════════════════════════

def compute_trade_metrics(
    fills: list[dict],
    orders: list[dict],
    positions: dict[str, Any] | None = None,
    pnl: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Compute trade-level metrics from fills, orders, and PnL data.
    从成交、订单和 PnL 数据计算交易层面的指标。

    Uses per-symbol round-trip PnL tracking for accurate win/loss calculation.
    使用每品种往返 PnL 追踪，准确计算胜率。
    """
    if not fills:
        return _empty_trade_metrics()

    # Reconstruct per-symbol round-trip trades from fills
    # 从成交记录重建每品种的往返交易
    symbol_tracker: dict[str, dict] = {}  # symbol → {side, entry_notional, exit_notional, qty, fees}
    round_trip_pnls: list[float] = []

    total_buy_notional = 0.0
    total_sell_notional = 0.0
    total_buy_qty = 0.0
    total_sell_qty = 0.0
    total_fees = 0.0

    for f in fills:
        side = f.get("side", "")
        qty = f.get("qty", 0.0)
        price = f.get("price", 0.0)
        notional = f.get("notional", qty * price)
        fee = f.get("fee", 0.0)
        symbol = f.get("symbol", "unknown")
        total_fees += fee

        if side == "Buy":
            total_buy_notional += notional
            total_buy_qty += qty
        elif side == "Sell":
            total_sell_notional += notional
            total_sell_qty += qty

        # Track round-trip: buy then sell (or sell then buy for shorts)
        tracker = symbol_tracker.get(symbol)
        if tracker is None:
            # New position entry
            symbol_tracker[symbol] = {
                "entry_side": side,
                "entry_notional": notional,
                "entry_qty": qty,
                "fees": fee,
            }
        elif tracker["entry_side"] != side:
            # Closing trade (opposite side) → compute round-trip PnL
            close_qty = min(qty, tracker["entry_qty"])
            if tracker["entry_side"] == "Buy":
                # Bought then sold: PnL = sell_notional - buy_notional (proportional)
                entry_price_avg = tracker["entry_notional"] / tracker["entry_qty"] if tracker["entry_qty"] > 0 else 0
                rt_pnl = (price - entry_price_avg) * close_qty - tracker["fees"] - fee
            else:
                # Sold then bought (short): PnL = entry_notional - close_notional
                entry_price_avg = tracker["entry_notional"] / tracker["entry_qty"] if tracker["entry_qty"] > 0 else 0
                rt_pnl = (entry_price_avg - price) * close_qty - tracker["fees"] - fee

            round_trip_pnls.append(rt_pnl)

            remaining = tracker["entry_qty"] - close_qty
            if remaining > 0:
                # Partially closed
                tracker["entry_qty"] = remaining
                tracker["entry_notional"] = entry_price_avg * remaining
                tracker["fees"] = 0.0  # fees already accounted
            else:
                # Fully closed (or flipped)
                excess = qty - close_qty
                if excess > 0:
                    # Flipped to opposite side
                    symbol_tracker[symbol] = {
                        "entry_side": side,
                        "entry_notional": price * excess,
                        "entry_qty": excess,
                        "fees": 0.0,
                    }
                else:
                    del symbol_tracker[symbol]
        else:
            # Same side → adding to position
            tracker["entry_notional"] += notional
            tracker["entry_qty"] += qty
            tracker["fees"] += fee

    # If no round-trips computed, fall back to PnL dict
    if not round_trip_pnls and pnl:
        realized = pnl.get("realized_pnl", 0.0)
        if realized != 0:
            round_trip_pnls.append(realized - total_fees)

    wins = [p for p in round_trip_pnls if p > 0]
    losses = [p for p in round_trip_pnls if p < 0]
    win_count = len(wins)
    loss_count = len(losses)
    total_trades = win_count + loss_count

    avg_win = sum(wins) / win_count if win_count > 0 else 0.0
    avg_loss = abs(sum(losses) / loss_count) if loss_count > 0 else 0.0
    win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else float("inf") if avg_win > 0 else 0.0

    return {
        "total_fills": len(fills),
        "total_round_trips": len(round_trip_pnls),
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": round(win_count / total_trades, 4) if total_trades > 0 else 0.0,
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
    pnl: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Build a balance time series from fills including realized PnL.
    从成交历史构建包含已实现盈亏的余额时间序列。
    """
    series = [{"ts_ms": 0, "balance": initial_balance}]
    balance = initial_balance

    # Track per-symbol entry for PnL calculation
    symbol_entries: dict[str, dict] = {}

    for f in fills:
        fee = f.get("fee", 0.0)
        side = f.get("side", "")
        qty = f.get("qty", 0.0)
        price = f.get("price", 0.0)
        symbol = f.get("symbol", "unknown")

        balance -= fee  # Always deduct fees

        entry = symbol_entries.get(symbol)
        if entry is None:
            symbol_entries[symbol] = {"side": side, "qty": qty, "avg_price": price}
        elif entry["side"] != side:
            # Closing: compute realized PnL
            close_qty = min(qty, entry["qty"])
            if entry["side"] == "Buy":
                realized = (price - entry["avg_price"]) * close_qty
            else:
                realized = (entry["avg_price"] - price) * close_qty
            balance += realized
            remaining = entry["qty"] - close_qty
            if remaining > 0:
                entry["qty"] = remaining
            else:
                excess = qty - close_qty
                if excess > 0:
                    symbol_entries[symbol] = {"side": side, "qty": excess, "avg_price": price}
                else:
                    del symbol_entries[symbol]
        else:
            # Adding to position — update avg price
            total_qty = entry["qty"] + qty
            entry["avg_price"] = (entry["avg_price"] * entry["qty"] + price * qty) / total_qty
            entry["qty"] = total_qty

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
    Compute drawdown metrics from balance history (now includes realized PnL).
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

    series = compute_balance_series(fills, initial_balance, pnl)

    peak = initial_balance
    trough = initial_balance
    max_dd_abs = 0.0
    max_dd_pct = 0.0

    for point in series[1:]:
        bal = point["balance"]
        if bal > peak:
            peak = bal
        dd = peak - bal
        if dd > max_dd_abs:
            max_dd_abs = dd
            trough = bal
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
    """Compute holding period statistics from filled orders."""
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
    pnl: dict[str, Any] | None = None,
    risk_free_rate_annual: float = 0.05,
) -> dict[str, Any]:
    """
    Compute Sharpe ratio from per-trade returns (round-trip PnL / balance).
    从每笔往返交易的收益率计算 Sharpe 比率。

    v2: Uses real trade PnL, not just fees.
    """
    if len(fills) < 2:
        return {"sharpe_ratio": 0.0, "return_count": 0, "note": "insufficient_data"}

    # Compute per-trade returns from balance series changes
    series = compute_balance_series(fills, initial_balance, pnl)
    if len(series) < 2:
        return {"sharpe_ratio": 0.0, "return_count": 0, "note": "insufficient_data"}

    returns: list[float] = []
    for i in range(1, len(series)):
        prev_bal = series[i - 1]["balance"]
        curr_bal = series[i]["balance"]
        if prev_bal > 0:
            ret = (curr_bal - prev_bal) / prev_bal
            returns.append(ret)

    if len(returns) < 2:
        return {"sharpe_ratio": 0.0, "return_count": len(returns), "note": "insufficient_returns"}

    mean_ret = sum(returns) / len(returns)
    # Sample variance (Bessel's correction: N-1)
    variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
    std_ret = math.sqrt(variance) if variance > 0 else 0.0

    if std_ret == 0:
        return {"sharpe_ratio": 0.0, "return_count": len(returns), "note": "zero_volatility"}

    # Annualize
    rf_per_period = risk_free_rate_annual / 365
    sharpe = (mean_ret - rf_per_period) / std_ret

    return {
        "sharpe_ratio": round(sharpe, 4),
        "mean_return": round(mean_ret, 8),
        "std_return": round(std_ret, 8),
        "return_count": len(returns),
        "note": "round_trip_based_v2",
    }


def compute_shadow_decision_metrics(shadow_decisions: list[dict]) -> dict[str, Any]:
    """Compute metrics for shadow decision pipeline performance."""
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
    """Compute all performance metrics from paper trading state."""
    fills = state.get("fills", [])
    orders = state.get("orders", [])
    positions = state.get("positions", {})
    session = state.get("session", {})
    pnl = state.get("pnl", {})
    shadow_decisions = state.get("shadow_decisions", [])

    initial_balance = session.get("initial_paper_balance_usdt", 10000.0)

    started = session.get("started_ts_ms") or 0
    now_ms = int(time.time() * 1000)
    stopped = session.get("stopped_ts_ms") or now_ms
    duration_sec = (stopped - started) / 1000 if started > 0 else 0.0

    return {
        "computed_ts_ms": now_ms,
        "session_duration_sec": round(duration_sec, 1),
        "trade_metrics": compute_trade_metrics(fills, orders, positions, pnl),
        "drawdown_metrics": compute_drawdown_metrics(fills, initial_balance, pnl),
        "holding_period_metrics": compute_holding_period_metrics(orders),
        "sharpe_ratio": compute_sharpe_ratio(fills, initial_balance, pnl),
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

def _empty_trade_metrics() -> dict[str, Any]:
    return {
        "total_fills": 0,
        "total_round_trips": 0,
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
