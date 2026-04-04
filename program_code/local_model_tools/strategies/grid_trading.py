"""
Grid Trading Strategy V2 / 网格交易策略 V2

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

  V2 升级（OU 动态间距 + 成本修正）：
  - 使用 Ornstein-Uhlenbeck 模型估算价格均值回归速度和波动率
  - 动态计算最优网格间距：σ/√θ（OU 理论最优间距）
  - 成本地板：网格间距必须超过 2× 单程手续费（否则赔钱）
  - 默认启用 OU 动态间距（ou_dynamic 默认 True）

  运行方式：
  1. 初始化时在每个网格价位放置限价单
  2. 价格上穿网格线 → 在该价位卖出 → 在下一格放买单
  3. 价格下穿网格线 → 在该价位买入 → 在上一格放卖单
  4. 反复循环，价格波动 = 利润
  5. (V2) 定期调用 update_grid_spacing() → OU 模型自动调整间距

  Agent 为什么喜欢网格：
  - AI 注意力成本极低（设置后基本不需要调整）
  - cost_edge_ratio 通常很好（高频小利润 vs 低 AI 成本）
  - 非标仓位大小（每格独立）→ 天然对抗止损猎杀
  - (V2) OU 动态间距让网格自适应市场状态

MODULE_NOTE (English):
  Grid trading is a classic range-trading strategy: evenly distribute buy
  and sell orders across a price range ("grid"). Each time price crosses
  a grid line, execute a trade, profiting from buy-low-sell-high spreads.

  Key characteristics:
  - No direction prediction needed — profits from oscillation within range
  - Highly automated — once set up, runs automatically, low AI attention cost
  - Ideal for ranging markets — longer sideways = more profit
  - Risk: sustained trend causes growing drawdown (needs stop-loss protection)

  V2 upgrade (OU dynamic spacing + cost correction):
  - Ornstein-Uhlenbeck model estimates mean reversion speed and volatility
  - Optimal grid step: σ/√θ (OU theoretical optimum)
  - Fee floor: grid step must exceed 2× one-way fee (otherwise unprofitable)
  - OU dynamic spacing enabled by default (ou_dynamic defaults to True)

Safety invariant / 安全不变量:
  - 只产生 OrderIntent / Only generates OrderIntents
  - V1: 网格参数一旦设定不可自动突破上下边界 / Grid bounds are fixed once set
  - V2: OU 动态更新时网格范围会重建，但间距有成本地板保护
  - V2: OU dynamic update rebuilds grid range, but step has fee floor protection
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

from .base import OrderIntent, StrategyBase, STRATEGY_ACTIVE


class GridTradingStrategy(StrategyBase):
    """
    Grid Trading strategy V2 / 网格交易策略 V2

    Parameters:
      symbol         — trading pair / 交易对
      upper_price    — grid upper bound / 网格上边界
      lower_price    — grid lower bound / 网格下边界
      grid_count     — number of grid lines / 网格线数量
      qty_per_grid   — order quantity per grid level / 每格下单数量
      geometric      — use geometric spacing / 使用几何间距
      ou_dynamic     — (V2) enable OU dynamic spacing / 启用 OU 动态间距
      ou_mean_period — (V2) OU mean estimation lookback / OU 均值估计回看期
      fee_pct        — (V2) one-way taker fee percentage / 单向 taker 费率百分比
    """

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        upper_price: float = 50000.0,
        lower_price: float = 40000.0,
        grid_count: int = 10,
        qty_per_grid: float = 0.001,
        geometric: bool = False,
        # V2 parameters / V2 参数
        ou_dynamic: bool = True,          # Enable OU dynamic spacing / 启用 OU 动态间距（V2 默认开启）
        ou_mean_period: int = 100,        # OU mean estimation lookback / OU 均值估计回看期
        fee_pct: float = 0.055,           # One-way taker fee percentage / 单向 taker 费率
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

        # V2 parameters / V2 参数
        self._ou_dynamic = ou_dynamic
        self._ou_mean_period = ou_mean_period
        self._fee_pct = fee_pct

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

        # Cooldown: prevent rapid-fire duplicate intents when price oscillates around a grid line.
        # 冷却：防止价格在网格线附近震荡时产生大量重复 intent。
        self._last_emit_ts_ms: int = 0
        self._emit_cooldown_ms: int = 60_000  # 60 seconds between grid emissions / 网格发射间隔 60 秒

        # V2: OU tick counter + price history for periodic spacing update
        # V2: OU tick 计数器 + 价格历史，用于定期更新间距
        self._ou_tick_count: int = 0
        self._ou_price_history: list[float] = []
        self._ou_update_interval: int = 50  # Update OU spacing every N ticks / 每 N 个 tick 更新 OU 间距

    @property
    def name(self) -> str:
        return "Grid_Trading"

    @property
    def description(self) -> str:
        ou_tag = " [V2 OU dynamic]" if self._ou_dynamic else ""
        return (
            f"网格交易策略 / Grid Trading strategy{ou_tag}. "
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

    # ------------------------------------------------------------------
    # V2: OU dynamic spacing / V2: OU 动态间距
    # ------------------------------------------------------------------

    def _compute_ou_grid_step(self, prices: list[float]) -> float | None:
        """
        Compute OU-adjusted grid step: σ/√θ + 2×fee_pct as lower bound.
        计算 OU 调整的网格间距：σ/√θ + 2×fee_pct 为下限。

        OU model: dX = θ(μ - X)dt + σdW
        - θ (mean reversion speed): estimated from lag-1 autocorrelation
          θ（均值回归速度）：通过滞后-1 自相关估算
        - σ (volatility): standard deviation of price changes
          σ（波动率）：价格变动的标准差
        - μ (mean): rolling mean of prices
          μ（均值）：价格的滚动平均

        Grid step = max(σ/√θ, current_step) with fee floor = 2×fee_pct×μ
        网格间距 = max(σ/√θ, 当前间距)，费用地板 = 2×fee_pct×μ

        Args:
            prices: Recent price series (at least ou_mean_period elements)
                    最近的价格序列（至少 ou_mean_period 个元素）

        Returns:
            Suggested grid step, or None if insufficient data
            建议的网格间距，数据不足时返回 None
        """
        if len(prices) < max(20, self._ou_mean_period):
            return None

        # Estimate OU parameters from recent prices
        # 从最近价格估算 OU 参数
        recent = prices[-self._ou_mean_period:]
        mu = sum(recent) / len(recent)

        # θ from lag-1 autocorrelation via simple OLS: ΔX = a + b·X → θ ≈ -b
        # 通过简单 OLS 从滞后-1 自相关估算 θ：ΔX = a + b·X → θ ≈ -b
        changes = [recent[i] - recent[i - 1] for i in range(1, len(recent))]
        levels = recent[:-1]

        if not changes or not levels:
            return None

        n = len(changes)
        sum_x = sum(levels)
        sum_y = sum(changes)
        sum_xy = sum(x * y for x, y in zip(levels, changes))
        sum_xx = sum(x * x for x in levels)

        denom = n * sum_xx - sum_x * sum_x
        if abs(denom) < 1e-12:
            return None

        b = (n * sum_xy - sum_x * sum_y) / denom
        theta = max(0.001, -b)  # Mean reversion speed (must be positive) / 均值回归速度（必须为正）

        # σ from residuals / 从残差估算 σ
        sigma = (sum(c * c for c in changes) / n) ** 0.5

        # OU grid step = σ / √θ / OU 网格间距 = σ / √θ
        ou_step = sigma / math.sqrt(theta)

        # Fee floor: grid step must exceed 2× round-trip fee to be profitable
        # 费用地板：网格间距必须超过 2× 往返手续费才能盈利
        fee_floor = 2 * self._fee_pct / 100.0 * mu

        return max(ou_step, fee_floor)

    def update_grid_spacing(self, prices: list[float]) -> bool:
        """
        V2: Dynamically update grid spacing using OU model.
        V2：使用 OU 模型动态更新网格间距。

        Call this periodically (e.g. every hour) with recent prices.
        定期调用（如每小时），传入最近价格序列。

        Returns True if grid was updated / 网格已更新返回 True
        """
        if not self._ou_dynamic:
            return False

        new_step = self._compute_ou_grid_step(prices)
        if new_step is None:
            return False

        # Only update if change is significant (>10% difference)
        # 仅在变化显著时更新（>10% 差异）
        if self._grid_step > 0 and abs(new_step - self._grid_step) / self._grid_step < 0.10:
            return False

        # Rebuild grid levels with new step / 用新间距重建网格
        mid_price = prices[-1]
        half_range = new_step * self._grid_count / 2
        self._lower = mid_price - half_range
        self._upper = mid_price + half_range
        self._grid_step = new_step
        self._grid_levels = [self._lower + i * new_step for i in range(self._grid_count + 1)]

        # Reset grid index for new grid / 为新网格重置网格索引
        self._last_grid_index = self._price_to_grid_index(prices[-1])

        logger.info(
            "Grid V2: OU updated spacing to %.4f (range %.2f-%.2f) / "
            "OU 更新网格间距为 %.4f（范围 %.2f-%.2f）",
            new_step, self._lower, self._upper, new_step, self._lower, self._upper,
        )
        return True

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

        # V2: Collect price history and periodically update OU spacing
        # V2: 收集价格历史，定期更新 OU 间距
        if self._ou_dynamic:
            self._ou_price_history.append(price)
            # Cap history at 2× lookback to avoid unbounded growth
            # 限制历史长度为 2× 回看期，避免无限增长
            max_hist = self._ou_mean_period * 2
            if len(self._ou_price_history) > max_hist:
                self._ou_price_history = self._ou_price_history[-self._ou_mean_period:]
            self._ou_tick_count += 1
            if self._ou_tick_count % self._ou_update_interval == 0:
                self.update_grid_spacing(self._ou_price_history)

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

            # Cooldown: skip if emitted too recently (prevents duplicate intents on oscillation)
            # 冷却：最近已发出过 intent 则跳过（防止震荡时重复发射）
            if ts_ms - self._last_emit_ts_ms < self._emit_cooldown_ms:
                # Still update grid index to avoid stale state — but don't emit
                # 仍更新网格索引以避免状态过期 — 但不发射 intent
                self._last_grid_index = current_index
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
                self._last_emit_ts_ms = ts_ms

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
                self._last_emit_ts_ms = ts_ms

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
            # V2 fields / V2 字段
            "ou_dynamic": self._ou_dynamic,
            "ou_mean_period": self._ou_mean_period,
            "fee_pct": self._fee_pct,
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
        # V2 fields / V2 字段
        self._ou_dynamic = saved.get("ou_dynamic", self._ou_dynamic)
        self._ou_mean_period = saved.get("ou_mean_period", self._ou_mean_period)
        self._fee_pct = saved.get("fee_pct", self._fee_pct)

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
            # V2 fields / V2 字段
            "ou_dynamic": self._ou_dynamic,
            "ou_mean_period": self._ou_mean_period,
            "fee_pct": self._fee_pct,
        }
