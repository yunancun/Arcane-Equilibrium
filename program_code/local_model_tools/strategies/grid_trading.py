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

from typing import Any

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

        self._symbol = symbol
        self._upper = upper_price
        self._lower = lower_price
        self._grid_count = grid_count
        self._qty = qty_per_grid

        # Calculate grid levels (evenly spaced from lower to upper)
        # 计算网格价位（从下边界到上边界均匀分布）
        step = (upper_price - lower_price) / grid_count
        self._grid_levels = [lower_price + i * step for i in range(grid_count + 1)]
        self._grid_step = step

        # Track which grid level the price was last in
        # 追踪价格上次在哪个网格层
        self._last_grid_index: int | None = None
        self._last_price: float | None = None

        # Statistics / 统计
        self._trade_count = 0
        self._buy_count = 0
        self._sell_count = 0

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
        # Use round() to avoid floating-point truncation errors
        # 使用 round() 避免浮点截断误差（如 0.9999→0 而非 1）
        return int(round((price - self._lower) / self._grid_step))

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

        # Price out of grid range → no action / 价格超出网格范围 → 不操作
        if price < self._lower or price > self._upper:
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

        # Grid crossing detected / 检测到网格穿越
        if current_index > self._last_grid_index:
            # Price moved up → sell (one intent per grid crossed)
            # 价格上移 → 卖出（每穿越一格一个意图）
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
                self._trade_count += 1

        else:
            # Price moved down → buy / 价格下移 → 买入
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
                self._trade_count += 1

        self._last_grid_index = current_index
        self._last_price = price

    def get_status(self) -> dict[str, Any]:
        return {
            "strategy": self.name,
            "state": self.state,
            "symbol": self._symbol,
            "upper_price": self._upper,
            "lower_price": self._lower,
            "grid_count": self._grid_count,
            "grid_step": round(self._grid_step, 2),
            "qty_per_grid": self._qty,
            "current_grid_index": self._last_grid_index,
            "last_price": self._last_price,
            "trade_count": self._trade_count,
            "buy_count": self._buy_count,
            "sell_count": self._sell_count,
            "grid_levels": [round(l, 2) for l in self._grid_levels],
        }
