"""
Grid Trading Strategy / 网格交易策略

MODULE_NOTE (中文):
  网格交易是一种经典的区间交易策略：
  在价格范围内均匀分布买单和卖单（"网格"），
  价格每穿越一个网格线就执行一笔交易，低买高卖赚取利差。

  核心特点：
  - 不需要预测方向 — 只需价格在网格范围内波动就能盈利
  - 自动化程度高 — 网格设好后自动运行，AI 注意力成本低
  - 适合震荡市场 — 横盘越久赚越多
  - 风险：单边行情下持仓会持续亏损（需要止损保护）

  网格参数：
  - upper_price: 网格上边界
  - lower_price: 网格下边界
  - grid_count: 网格线数量（线越多、间距越小、交易越频繁）
  - qty_per_grid: 每个网格的下单数量

  运行方式：
  1. 初始化时在每个网格价位放置限价单
  2. 价格上穿网格线 → 在该价位卖出 → 在下一格放买单
  3. 价格下穿网格线 → 在该价位买入 → 在上一格放卖单
  4. 反复循环，价格波动 = 利润

  Agent 为什么喜欢网格：
  - AI 注意力成本极低（设置后基本不需要调整）
  - cost_edge_ratio 通常很好（高频小利润 vs 低 AI 成本）
  - 非标仓位大小（每格独立）→ 天然对抗止损猎杀

MODULE_NOTE (English):
  Grid trading is a classic range-trading strategy: evenly distribute buy
  and sell orders across a price range ("grid"). Each time price crosses
  a grid line, execute a trade, profiting from buy-low-sell-high spreads.

  Key characteristics:
  - No direction prediction needed — profits from oscillation within range
  - Highly automated — once set up, runs automatically, low AI attention cost
  - Ideal for ranging markets — longer sideways = more profit
  - Risk: sustained trend causes growing drawdown (needs stop-loss protection)

Safety invariant / 安全不变量:
  - 只产生 OrderIntent / Only generates OrderIntents
  - 网格参数一旦设定不可自动突破上下边界 / Grid bounds are fixed once set
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

from .base import OrderIntent, StrategyBase, STRATEGY_ACTIVE


class GridTradingStrategy(StrategyBase):
    """
    Grid Trading strategy / 网格交易策略

    Parameters:
      symbol         — trading pair / 交易对
      upper_price    — grid upper bound / 网格上边界
      lower_price    — grid lower bound / 网格下边界
      grid_count     — number of grid lines / 网格线数量
      qty_per_grid   — order quantity per grid level / 每格下单数量
    """

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        upper_price: float = 50000.0,
        lower_price: float = 40000.0,
        grid_count: int = 10,
        qty_per_grid: float = 0.001,
        geometric: bool = False,
    ) -> None:
        super().__init__()
        if upper_price <= lower_price:
            raise ValueError(
                f"upper_price ({upper_price}) must be > lower_price ({lower_price}) / "
                f"上边界必须大于下边界"
            )
        if grid_count < 2:
            raise ValueError(
                f"grid_count ({grid_count}) must be >= 2 / 网格数量至少为 2"
            )
        if qty_per_grid <= 0:
            raise ValueError(
                f"qty_per_grid ({qty_per_grid}) must be > 0 / 每格数量必须大于 0"
            )

        self._symbol = symbol
        self._upper = upper_price
        self._lower = lower_price
        self._grid_count = grid_count
        self._qty = qty_per_grid

        # Calculate grid levels / 计算网格价位
        if geometric:
            # Geometric spacing: constant percentage between levels
            # 几何间距：每级之间百分比恒定
            ratio = (upper_price / lower_price) ** (1.0 / grid_count)
            self._grid_levels = [lower_price * (ratio ** i) for i in range(grid_count + 1)]
            self._grid_step = 0  # Not used in geometric mode
            self._geometric = True
            self._geo_ratio = ratio
        else:
            step = (upper_price - lower_price) / grid_count
            self._grid_levels = [lower_price + i * step for i in range(grid_count + 1)]
            self._grid_step = step
            self._geometric = False
            self._geo_ratio = 1.0

        # Track which grid level the price was last in
        # 追踪价格上次在哪个网格层
        self._last_grid_index: int | None = None
        self._last_price: float | None = None

        # Statistics / 统计
        self._trade_count = 0
        self._buy_count = 0
        self._sell_count = 0
        self._net_inventory: float = 0.0  # Net inventory in asset units (positive=long, negative=short)
        self._max_inventory_qty: float = qty_per_grid * grid_count  # Max allowed inventory
        self._inventory_stop_triggered = False

    @property
    def name(self) -> str:
        return "Grid_Trading"

    @property
    def description(self) -> str:
        return (
            f"网格交易策略 / Grid Trading strategy. "
            f"范围 {self._lower}-{self._upper}, {self._grid_count} 格"
        )

    def _price_to_grid_index(self, price: float) -> int:
        """
        Map a price to its grid index (which interval it falls in).
        将价格映射到网格索引（在哪个区间内）。

        Returns:
          Grid index (0 = below lowest, grid_count = above highest)
          网格索引（0 = 低于最低, grid_count = 高于最高）
        """
        if price <= self._lower:
            return 0
        if price >= self._upper:
            return self._grid_count
        if self._geometric:
            idx = int(math.floor(math.log(price / self._lower) / math.log(self._geo_ratio)))
            return min(idx, self._grid_count)
        else:
            idx = int(math.floor((price - self._lower) / self._grid_step))
            return min(idx, self._grid_count)  # clamp to valid range / 限制在有效范围内

    def on_tick(self, symbol: str, price: float, ts_ms: int) -> None:
        """
        Check grid crossings on each price tick.
        每次价格 tick 检查网格穿越。

        When price crosses a grid line:
        - Crossing upward → sell at that level (lock in profit from lower buy)
        - Crossing downward → buy at that level (acquire cheaper position)
        价格穿越网格线时：
        - 向上穿越 → 在该价位卖出（锁定低位买入的利润）
        - 向下穿越 → 在该价位买入（获取更低价位的头寸）
        """
        if self._state != STRATEGY_ACTIVE:
            return
        if symbol != self._symbol:
            return

        with self._intent_lock:  # Protect grid state read+write+emit atomically / 原子保护网格状态
            # Price out of grid range → reset grid index to boundary to avoid phantom orders on re-entry
            # 价格超出网格范围 → 重置网格索引到边界，避免重入时产生幻影订单
            if price < self._lower or price > self._upper:
                if price < self._lower:
                    self._last_grid_index = 0
                else:
                    self._last_grid_index = self._grid_count
                self._last_price = price
                return

            current_index = self._price_to_grid_index(price)

            if self._last_grid_index is None:
                # First tick — just record position / 首个 tick — 只记录位置
                self._last_grid_index = current_index
                self._last_price = price
                return

            if current_index == self._last_grid_index:
                # Same grid level — no crossing / 同一网格层 — 无穿越
                self._last_price = price
                return

            # Inventory stop: if accumulated inventory exceeds max, stop taking new positions
            # 库存止损：累计库存超过上限时，停止新建同方向仓位
            if abs(self._net_inventory) >= self._max_inventory_qty:
                if not self._inventory_stop_triggered:
                    self._inventory_stop_triggered = True
                    logger.warning(
                        "Grid inventory limit reached: %.6f (max %.6f) / "
                        "网格库存达到上限",
                        self._net_inventory, self._max_inventory_qty,
                    )

            # Grid crossing detected / 检测到网格穿越
            if current_index > self._last_grid_index:
                # Price moved up → sell (one intent per grid crossed)
                # 价格上移 → 卖出（每穿越一格一个意图）
                if self._net_inventory <= -self._max_inventory_qty:
                    self._last_grid_index = current_index
                    self._last_price = price
                    return  # Inventory limit reached / 库存限制
                grids_crossed = current_index - self._last_grid_index
                for i in range(grids_crossed):
                    grid_level = self._grid_levels[self._last_grid_index + i + 1]
                    self._emit_intent(OrderIntent(
                        symbol=self._symbol,
                        side="Sell",
                        order_type="limit",
                        qty=self._qty,
                        price=grid_level,
                        strategy_name=self.name,
                        reason=(
                            f"Grid sell at {grid_level:.2f} (crossed up) / "
                            f"网格卖出 {grid_level:.2f}（向上穿越）"
                        ),
                        confidence=0.8,
                        metadata={"grid_level": grid_level, "direction": "up"},
                    ))
                    self._sell_count += 1
                    self._net_inventory -= self._qty
                    self._trade_count += 1

            else:
                # Price moved down → buy / 价格下移 → 买入
                if self._net_inventory >= self._max_inventory_qty:
                    self._last_grid_index = current_index
                    self._last_price = price
                    return  # Inventory limit reached / 库存限制
                grids_crossed = self._last_grid_index - current_index
                for i in range(grids_crossed):
                    grid_level = self._grid_levels[self._last_grid_index - i]
                    self._emit_intent(OrderIntent(
                        symbol=self._symbol,
                        side="Buy",
                        order_type="limit",
                        qty=self._qty,
                        price=grid_level,
                        strategy_name=self.name,
                        reason=(
                            f"Grid buy at {grid_level:.2f} (crossed down) / "
                            f"网格买入 {grid_level:.2f}（向下穿越）"
                        ),
                        confidence=0.8,
                        metadata={"grid_level": grid_level, "direction": "down"},
                    ))
                    self._buy_count += 1
                    self._net_inventory += self._qty
                    self._trade_count += 1

            self._last_grid_index = current_index
            self._last_price = price

    def check_grid_health(self) -> dict[str, Any]:
        """
        Check if grid needs recentering.
        检查网格是否需要重新居中。
        """
        if self._last_price is None:
            return {"needs_reset": False, "reason": "no_data"}

        # If price is within 10% of boundary for extended time, suggest reset
        range_size = self._upper - self._lower
        if self._last_price < self._lower + range_size * 0.1:
            return {"needs_reset": True, "reason": "price_near_lower_boundary", "last_price": self._last_price}
        if self._last_price > self._upper - range_size * 0.1:
            return {"needs_reset": True, "reason": "price_near_upper_boundary", "last_price": self._last_price}
        return {"needs_reset": False, "reason": "price_in_range"}

    def get_persistent_state(self) -> dict[str, Any]:
        base = super().get_persistent_state()
        base.update({
            "last_grid_index": self._last_grid_index,
            "last_price": self._last_price,
            "net_inventory": self._net_inventory,
            "trade_count": self._trade_count,
            "buy_count": self._buy_count,
            "sell_count": self._sell_count,
        })
        return base

    def restore_persistent_state(self, saved: dict[str, Any]) -> None:
        super().restore_persistent_state(saved)
        self._last_grid_index = saved.get("last_grid_index")
        self._last_price = saved.get("last_price")
        self._net_inventory = saved.get("net_inventory", 0.0)
        self._trade_count = saved.get("trade_count", 0)
        self._buy_count = saved.get("buy_count", 0)
        self._sell_count = saved.get("sell_count", 0)

    def get_status(self) -> dict[str, Any]:
        return {
            "strategy": self.name,
            "state": self.state,
            "symbol": self._symbol,
            "upper_price": self._upper,
            "lower_price": self._lower,
            "grid_count": self._grid_count,
            "grid_step": round(self._grid_step, 2),
            "geometric": self._geometric,
            "grid_health": self.check_grid_health(),
            "qty_per_grid": self._qty,
            "current_grid_index": self._last_grid_index,
            "last_price": self._last_price,
            "trade_count": self._trade_count,
            "buy_count": self._buy_count,
            "sell_count": self._sell_count,
            "net_inventory": self._net_inventory,
            "max_inventory_qty": self._max_inventory_qty,
            "inventory_stop_triggered": self._inventory_stop_triggered,
            "grid_levels": [round(l, 2) for l in self._grid_levels],
        }
