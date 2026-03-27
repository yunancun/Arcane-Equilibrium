"""
Stop Manager — Strategy-Level Stop-Loss and Position Sizing
止损管理器 — 策略级止损与动态仓位管理

MODULE_NOTE (中文):
  本模块提供策略级别的止损管理和动态仓位计算。

  止损类型：
  1. 硬止损 (Hard Stop) — 绝对价格防线，价到即触发，不可商量
  2. 追踪止损 (Trailing Stop) — 跟踪最高/最低价，锁定利润
  3. 时间止损 (Time Stop) — 持仓超时自动平仓，避免 AI 注意力税累积

  动态仓位：
  - 基于 ATR 的仓位计算：qty = risk_budget / (ATR * multiplier * price)
  - 确保每笔交易风险固定为账户的 X%

  止损隐身：
  - 永远不在交易所放 stop order
  - 本地 tick() 检查触发，市价平仓

MODULE_NOTE (English):
  Provides strategy-level stop-loss management and dynamic position sizing.

  Stop types:
  1. Hard Stop — absolute price line, triggers immediately, non-negotiable
  2. Trailing Stop — tracks best price, locks in profit
  3. Time Stop — auto-close after holding too long, prevents AI attention tax accumulation

  Dynamic sizing:
  - ATR-based: qty = risk_budget / (ATR * multiplier * price)
  - Ensures fixed risk per trade as percentage of account

  Stop stealth:
  - Never place stop orders on exchange
  - Local tick() check triggers market close

Safety invariant:
  - 只产生 OrderIntent / Only generates OrderIntents
  - 止损不可被策略绕过 / Stops cannot be bypassed by strategies
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class StopConfig:
    """Stop-loss configuration for a position / 持仓止损配置"""
    hard_stop_pct: float = 5.0          # Hard stop loss % from entry / 硬止损百分比
    trailing_stop_pct: float | None = None  # Trailing stop % from best / 追踪止损百分比
    time_stop_hours: float | None = None    # Max holding time in hours / 最大持仓时间（小时）

    def validate(self) -> None:
        if self.hard_stop_pct <= 0:
            raise ValueError(f"hard_stop_pct must be > 0, got {self.hard_stop_pct}")
        if self.trailing_stop_pct is not None and self.trailing_stop_pct <= 0:
            raise ValueError(f"trailing_stop_pct must be > 0, got {self.trailing_stop_pct}")
        if self.time_stop_hours is not None and self.time_stop_hours <= 0:
            raise ValueError(f"time_stop_hours must be > 0, got {self.time_stop_hours}")


@dataclass
class TrackedPosition:
    """A position being tracked for stop-loss / 被追踪止损的持仓"""
    symbol: str
    side: str                    # "long" or "short"
    entry_price: float
    qty: float
    strategy_name: str
    entry_ts_ms: int
    stop_config: StopConfig
    best_price: float = 0.0     # Best favorable price since entry / 入场以来最优价格

    def __post_init__(self):
        if self.best_price == 0.0:
            self.best_price = self.entry_price


class StopManager:
    """
    Manages stop-losses for all active positions across all strategies.
    管理所有策略所有活跃持仓的止损。

    Called on every price tick to check if any stops should trigger.
    每次价格 tick 时被调用，检查是否有止损应触发。
    """

    def __init__(self, default_config: StopConfig | None = None) -> None:
        self._default_config = default_config or StopConfig()
        self._default_config.validate()
        self._positions: dict[str, TrackedPosition] = {}  # key: "{strategy}:{symbol}"
        self._lock = threading.Lock()
        self._stats = {
            "hard_stops_triggered": 0,
            "trailing_stops_triggered": 0,
            "time_stops_triggered": 0,
            "positions_tracked": 0,
        }

    def track_position(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        qty: float,
        strategy_name: str,
        stop_config: StopConfig | None = None,
    ) -> None:
        """Register a position for stop-loss tracking / 注册持仓进行止损追踪"""
        config = stop_config or StopConfig(
            hard_stop_pct=self._default_config.hard_stop_pct,
            trailing_stop_pct=self._default_config.trailing_stop_pct,
            time_stop_hours=self._default_config.time_stop_hours,
        )
        config.validate()

        key = f"{strategy_name}:{symbol}"
        pos = TrackedPosition(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            qty=qty,
            strategy_name=strategy_name,
            entry_ts_ms=int(time.time() * 1000),
            stop_config=config,
        )

        with self._lock:
            self._positions[key] = pos
            self._stats["positions_tracked"] = len(self._positions)

        logger.info(
            "Tracking position: %s %s %s @ %.2f qty=%.6f hard=%.1f%% / "
            "追踪持仓: %s %s @ %.2f",
            strategy_name, side, symbol, entry_price, qty,
            config.hard_stop_pct, symbol, side, entry_price,
        )

    def untrack_position(self, symbol: str, strategy_name: str) -> None:
        """Remove a position from stop tracking / 移除持仓的止损追踪"""
        key = f"{strategy_name}:{symbol}"
        with self._lock:
            self._positions.pop(key, None)
            self._stats["positions_tracked"] = len(self._positions)

    def check_stops(self, market_prices: dict[str, float]) -> list[dict[str, Any]]:
        """
        Check all tracked positions against current prices.
        检查所有追踪持仓是否触发止损。

        Returns list of stop triggers, each containing:
          {"symbol", "side", "strategy_name", "qty", "stop_type", "reason", "entry_price", "current_price"}
        """
        triggered: list[dict[str, Any]] = []
        now_ms = int(time.time() * 1000)

        with self._lock:
            positions = list(self._positions.values())

        for pos in positions:
            price = market_prices.get(pos.symbol)
            if price is None or price <= 0:
                continue

            # Update best price
            if pos.side == "long":
                if price > pos.best_price:
                    pos.best_price = price
            else:  # short
                if pos.best_price == pos.entry_price or price < pos.best_price:
                    pos.best_price = price

            stop_type = None
            reason = ""

            # 1. Hard stop check
            if pos.side == "long":
                stop_price = pos.entry_price * (1 - pos.stop_config.hard_stop_pct / 100)
                if price <= stop_price:
                    stop_type = "hard_stop"
                    pnl_pct = (price - pos.entry_price) / pos.entry_price * 100
                    reason = f"Hard stop: price {price:.2f} <= {stop_price:.2f} ({pnl_pct:.1f}%)"
            else:
                stop_price = pos.entry_price * (1 + pos.stop_config.hard_stop_pct / 100)
                if price >= stop_price:
                    stop_type = "hard_stop"
                    pnl_pct = (pos.entry_price - price) / pos.entry_price * 100
                    reason = f"Hard stop: price {price:.2f} >= {stop_price:.2f} ({pnl_pct:.1f}%)"

            # 2. Trailing stop check (only if profitable)
            if stop_type is None and pos.stop_config.trailing_stop_pct is not None:
                trail_pct = pos.stop_config.trailing_stop_pct / 100
                if pos.side == "long":
                    trail_price = pos.best_price * (1 - trail_pct)
                    if price <= trail_price and pos.best_price > pos.entry_price:
                        stop_type = "trailing_stop"
                        locked_pct = (trail_price - pos.entry_price) / pos.entry_price * 100
                        reason = f"Trailing stop: price {price:.2f} <= trail {trail_price:.2f} (best={pos.best_price:.2f}, locked={locked_pct:.1f}%)"
                else:
                    trail_price = pos.best_price * (1 + trail_pct)
                    if price >= trail_price and pos.best_price < pos.entry_price:
                        stop_type = "trailing_stop"
                        locked_pct = (pos.entry_price - trail_price) / pos.entry_price * 100
                        reason = f"Trailing stop: price {price:.2f} >= trail {trail_price:.2f} (best={pos.best_price:.2f}, locked={locked_pct:.1f}%)"

            # 3. Time stop check
            if stop_type is None and pos.stop_config.time_stop_hours is not None:
                max_hold_ms = int(pos.stop_config.time_stop_hours * 3600 * 1000)
                held_ms = now_ms - pos.entry_ts_ms
                if held_ms >= max_hold_ms:
                    stop_type = "time_stop"
                    held_hours = held_ms / 3600_000
                    reason = f"Time stop: held {held_hours:.1f}h >= max {pos.stop_config.time_stop_hours}h"

            if stop_type:
                triggered.append({
                    "symbol": pos.symbol,
                    "side": "Sell" if pos.side == "long" else "Buy",  # Close direction
                    "strategy_name": pos.strategy_name,
                    "qty": pos.qty,
                    "stop_type": stop_type,
                    "reason": reason,
                    "entry_price": pos.entry_price,
                    "current_price": price,
                })

                with self._lock:
                    self._stats[f"{stop_type}s_triggered"] += 1
                    key = f"{pos.strategy_name}:{pos.symbol}"
                    self._positions.pop(key, None)
                    self._stats["positions_tracked"] = len(self._positions)

                logger.warning("STOP TRIGGERED: %s / 止损触发: %s", reason, reason)

        return triggered

    def get_status(self) -> dict[str, Any]:
        """Get stop manager status / 获取止损管理器状态"""
        with self._lock:
            positions = {k: {
                "symbol": p.symbol, "side": p.side,
                "entry_price": p.entry_price, "best_price": p.best_price,
                "strategy": p.strategy_name, "qty": p.qty,
                "hard_stop_pct": p.stop_config.hard_stop_pct,
                "trailing_stop_pct": p.stop_config.trailing_stop_pct,
                "time_stop_hours": p.stop_config.time_stop_hours,
            } for k, p in self._positions.items()}
            return {
                "component": "stop_manager",
                "tracked_positions": positions,
                "stats": dict(self._stats),
                "default_config": {
                    "hard_stop_pct": self._default_config.hard_stop_pct,
                    "trailing_stop_pct": self._default_config.trailing_stop_pct,
                    "time_stop_hours": self._default_config.time_stop_hours,
                },
            }


def compute_atr_position_size(
    account_balance: float,
    risk_per_trade_pct: float,
    atr: float,
    atr_multiplier: float = 2.0,
    price: float = 1.0,
    min_qty: float = 0.001,
    max_qty: float = 1.0,
) -> float:
    """
    Compute position size based on ATR (Average True Range).
    基于 ATR 计算仓位大小。

    Formula: qty = (account_balance * risk_pct) / (ATR * multiplier * price)
    公式：qty = (账户余额 × 风险比例) / (ATR × 倍数 × 价格)

    This ensures each trade risks approximately risk_per_trade_pct of the account,
    with the stop distance determined by ATR.
    确保每笔交易约风险账户的 risk_per_trade_pct，止损距离由 ATR 决定。

    Args:
      account_balance    — account equity in USDT / 账户权益
      risk_per_trade_pct — risk per trade as % of account (e.g., 1.0 = 1%) / 每笔风险百分比
      atr                — current ATR value / 当前 ATR 值
      atr_multiplier     — stop distance = ATR * multiplier (default 2.0) / 止损距离倍数
      price              — current asset price / 当前价格
      min_qty            — minimum order quantity / 最小下单数量
      max_qty            — maximum order quantity / 最大下单数量

    Returns:
      Position size in asset units, clamped to [min_qty, max_qty]
    """
    if atr <= 0 or price <= 0 or account_balance <= 0 or risk_per_trade_pct <= 0:
        return min_qty

    risk_amount = account_balance * (risk_per_trade_pct / 100.0)
    stop_distance = atr * atr_multiplier

    # qty * stop_distance = risk_amount → qty = risk_amount / stop_distance
    # But we need qty in asset units, and stop_distance is in price units
    qty = risk_amount / (stop_distance * price / price)  # simplified: risk_amount / stop_distance
    # Actually: risk = qty * stop_distance_in_usdt = qty * stop_distance
    # So qty = risk_amount / stop_distance
    qty = risk_amount / stop_distance

    # Clamp to bounds
    qty = max(min_qty, min(max_qty, qty))

    return round(qty, 6)
