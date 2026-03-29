from __future__ import annotations

"""
Market Data Dispatcher + Attention Filter / 行情分发器 + 注意力过滤器
事件驱动的智能行情处理：根据交易上下文自适应调节关注度

MODULE_NOTE (中文):
  本模块是 OpenClaw Agent 的"感知注意力系统"，连接 Public WebSocket 和 Paper Trading Engine。

  核心理念：**像交易员一样思考，而不是像机器一样轮询**。
  - 有挂单靠近当前价时 → 高度关注（每次价格更新都检查）
  - 持仓但无挂单时 → 中等关注（定期更新未实现盈亏）
  - 无挂单无持仓时 → 低关注（仅记录价格快照，不频繁触发引擎）
  - 价格剧烈波动时 → 自动提升关注度（即使没有挂单也要关注风险）

  设计原则：
  1. 事件驱动 — 不用定时器，WebSocket 推送驱动一切
  2. 自适应节流 — 不是固定间隔，而是根据上下文动态调整
  3. 最小计算 — 注意力低时几乎零开销，注意力高时精确触发
  4. Agent 主动性 — 有意义的价格变化才值得反应

MODULE_NOTE (English):
  This module is the "perceptual attention system" of the OpenClaw Agent,
  connecting the Public WebSocket to the Paper Trading Engine.

  Core idea: **Think like a trader, not poll like a machine**.
  - Limit orders near current price → high attention (check on every price update)
  - Holding positions but no pending orders → medium attention (periodic unrealized PnL update)
  - No orders, no positions → low attention (only log price snapshots, minimal engine triggers)
  - Sudden price spike → auto-escalate attention (watch risk even without orders)

  Design principles:
  1. Event-driven — no timers, everything driven by WebSocket pushes
  2. Adaptive throttling — not fixed intervals, dynamically adjusted by context
  3. Minimal computation — near-zero overhead when attention is low, precise triggers when high
  4. Agent proactivity — only meaningful price changes deserve a reaction

安全不变量 / Safety invariant:
  - 仅读取行情 + 触发纸上交易模拟，绝不接触真实交易 API
  - Only reads market data + triggers paper trading simulation, never touches real trading APIs
"""

import logging
import math
import threading
import time
from typing import Any

from .bybit_public_ws_listener import BybitPublicWsListener, PriceCallback, PriceEvent
from .paper_trading_engine import (
    ACTIVE_STATES,
    ORDER_TYPE_LIMIT,
    PaperTradingEngine,
    SESSION_ACTIVE,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Attention Levels / 注意力等级
# ═══════════════════════════════════════════════════════════════════════════════

ATTENTION_DORMANT = "dormant"       # No session active / 无活跃 session
ATTENTION_LOW = "low"               # Session active, no orders or positions / 有 session，无订单持仓
ATTENTION_MEDIUM = "medium"         # Has positions, no pending orders / 有持仓，无挂单
ATTENTION_HIGH = "high"             # Has limit orders near price / 有限价单靠近当前价
ATTENTION_CRITICAL = "critical"     # Volatile market or orders about to fill / 剧烈波动或即将成交

# Throttle intervals per attention level (minimum seconds between engine ticks)
# 各注意力等级的节流间隔（引擎 tick 最小间隔秒数）
THROTTLE_INTERVALS = {
    ATTENTION_DORMANT: 60.0,    # Once per minute / 每分钟一次
    ATTENTION_LOW: 10.0,        # Every 10s / 每 10 秒
    ATTENTION_MEDIUM: 3.0,      # Every 3s / 每 3 秒
    ATTENTION_HIGH: 0.5,        # Every 500ms / 每 500 毫秒
    ATTENTION_CRITICAL: 0.0,    # Every update / 每次更新
}

# Price proximity threshold for high attention (% from limit price)
# 限价单距离当前价多近时进入高关注（百分比）
PROXIMITY_THRESHOLD_PCT = 0.5   # 0.5% — within this range → high attention

# Volatility spike threshold (% change from recent baseline to trigger critical attention)
# 波动率飙升阈值（相对近期基线的百分比变化，触发 critical 注意力）
VOLATILITY_SPIKE_PCT = 1.0      # 1% sudden move → critical


# ═══════════════════════════════════════════════════════════════════════════════
# Market Data Dispatcher / 行情数据分发器
# ═══════════════════════════════════════════════════════════════════════════════

class MarketDataDispatcher:
    """
    Event-driven market data processor with adaptive attention.
    事件驱动的行情处理器，具有自适应注意力机制。

    Connects BybitPublicWsListener → PaperTradingEngine via intelligent filtering.
    通过智能过滤连接 BybitPublicWsListener → PaperTradingEngine。
    """

    def __init__(
        self,
        engine: PaperTradingEngine,
        symbols: list[str] | None = None,
        ws_url: str | None = None,
    ) -> None:
        self._engine = engine
        self._symbols = symbols or ["BTCUSDT", "ETHUSDT"]

        # WebSocket listener / WebSocket 监听器
        ws_kwargs: dict[str, Any] = {
            "symbols": self._symbols,
            "on_price": self._on_price_event,
        }
        if ws_url:
            ws_kwargs["ws_url"] = ws_url
        self._listener = BybitPublicWsListener(**ws_kwargs)

        # Attention state / 注意力状态
        self._attention_level = ATTENTION_DORMANT
        self._lock = threading.Lock()

        # Throttle tracking / 节流追踪
        self._last_tick_time: dict[str, float] = {}  # symbol → last tick timestamp
        self._last_tick_all: float = 0.0              # last global tick timestamp

        # Price history for volatility detection / 价格历史（用于波动率检测）
        # Stores recent prices as (timestamp, price) tuples
        self._price_history: dict[str, list[tuple[float, float]]] = {}
        self._history_window_sec = 60.0  # 60-second sliding window / 60 秒滑动窗口

        # Statistics / 统计
        self._stats = {
            "total_events_received": 0,
            "ticks_triggered": 0,
            "ticks_throttled": 0,
            "attention_changes": 0,
            "volatility_spikes": 0,
            "last_attention_level": ATTENTION_DORMANT,
            "started_ts_ms": None,
        }

        # External tick consumers (e.g., PipelineBridge) / 外部 tick 消费者（如管线桥接器）
        self._tick_consumers: list[Any] = []

    # ── Public Interface / 公开接口 ──

    def start(self) -> None:
        """Start the market data feed / 启动行情数据流"""
        self._stats["started_ts_ms"] = int(time.time() * 1000)
        self._listener.start()
        logger.info(
            "Market data dispatcher started / 行情分发器已启动, symbols=%s",
            self._symbols,
        )

    def stop(self) -> None:
        """Stop the market data feed / 停止行情数据流"""
        self._listener.stop()
        logger.info("Market data dispatcher stopped / 行情分发器已停止")

    def is_running(self) -> bool:
        return self._listener.is_running()

    def get_status(self) -> dict[str, Any]:
        """Get comprehensive status / 获取综合状态"""
        with self._lock:
            attention = self._attention_level
            stats = dict(self._stats)
        return {
            "dispatcher_running": self.is_running(),
            "attention_level": attention,
            "throttle_interval_sec": THROTTLE_INTERVALS.get(attention, 10.0),
            "ws_listener": self._listener.get_status(),
            "latest_prices": self._listener.get_all_latest_prices(),
            "stats": stats,
            "is_simulated": True,
            "data_category": "paper_simulated",
        }

    def add_symbol(self, symbol: str) -> None:
        """Add a symbol to the feed / 添加交易对到行情流"""
        if symbol not in self._symbols:
            self._symbols.append(symbol)
        self._listener.add_symbol(symbol)

    def remove_symbol(self, symbol: str) -> None:
        """Remove a symbol from the feed / 从行情流移除交易对"""
        if symbol in self._symbols:
            self._symbols.remove(symbol)
        self._listener.remove_symbol(symbol)

    def register_tick_consumer(self, consumer: Any) -> None:
        """
        Register an external tick consumer that will receive price events.
        注册外部 tick 消费者，将收到价格事件。

        Consumer must have an `on_tick(event)` method.
        消费者必须有 `on_tick(event)` 方法。
        """
        self._tick_consumers.append(consumer)
        logger.info("Registered tick consumer: %s / 注册 tick 消费者", type(consumer).__name__)

    # ── Core: Price Event Handler / 核心：价格事件处理 ──

    def _on_price_event(self, event: PriceEvent) -> None:
        """
        Central event handler — called by WebSocket listener on every ticker update.
        中枢事件处理器 — 每次 ticker 更新时由 WebSocket 监听器调用。

        Flow / 流程:
        1. Update price history for volatility tracking / 更新价格历史
        2. Assess attention level based on current context / 评估当前注意力等级
        3. Check throttle — skip if too soon for current attention level / 检查节流
        4. If not throttled → trigger paper engine tick / 未被节流 → 触发引擎 tick
        """
        self._stats["total_events_received"] += 1

        # 1. Update price history / 更新价格历史
        self._update_price_history(event.symbol, event.last_price)

        # 2. Assess attention level / 评估注意力等级
        new_attention = self._assess_attention(event)

        with self._lock:
            if new_attention != self._attention_level:
                old = self._attention_level
                self._attention_level = new_attention
                self._stats["attention_changes"] += 1
                self._stats["last_attention_level"] = new_attention
                logger.info(
                    "Attention: %s → %s (symbol=%s, price=%.2f) / 注意力变化",
                    old, new_attention, event.symbol, event.last_price,
                )
            current_attention = self._attention_level

        # 3. Check throttle / 检查节流
        now = time.monotonic()
        min_interval = THROTTLE_INTERVALS.get(current_attention, 10.0)
        time_since_last = now - self._last_tick_all

        if time_since_last < min_interval:
            self._stats["ticks_throttled"] += 1
            return

        # 4. Trigger paper engine tick / 触发引擎 tick
        self._trigger_tick(event)

    def _trigger_tick(self, trigger_event: PriceEvent) -> None:
        """
        Trigger a paper engine tick with all latest prices.
        用所有最新价格触发纸上交易引擎 tick。
        """
        now = time.monotonic()

        # Collect all latest prices / 收集所有最新价格
        market_prices = self._listener.get_all_latest_prices()

        # Ensure the triggering event's price is included (freshest)
        # 确保触发事件的价格被包含（最新的）
        market_prices[trigger_event.symbol] = trigger_event.last_price

        if not market_prices:
            return

        try:
            result = self._engine.tick(market_prices)
            self._last_tick_all = now
            self._last_tick_time[trigger_event.symbol] = now
            self._stats["ticks_triggered"] += 1

            if result.get("orders_filled", 0) > 0:
                logger.info(
                    "Tick filled %d orders / Tick 成交 %d 笔订单 (trigger=%s@%.2f)",
                    result["orders_filled"],
                    result["orders_filled"],
                    trigger_event.symbol,
                    trigger_event.last_price,
                )

            # Fan-out to registered tick consumers / 分发到注册的 tick 消费者
            for consumer in self._tick_consumers:
                try:
                    consumer.on_tick(trigger_event)
                except Exception:
                    logger.exception("Tick consumer error / tick 消费者异常: %s", type(consumer).__name__)

            # Notify consumers of tick fills for E1/G1 hooks
            # (covers positions closed via risk_auto_close, time stop, soft stop — paths
            #  that bypass the submit_order() route and would otherwise miss observations)
            # 通知消费者 tick 成交，覆盖 E1/G1 路径（risk_auto_close/时间止损/软止损）
            if result.get("orders_filled", 0) > 0:
                for consumer in self._tick_consumers:
                    if hasattr(consumer, "on_tick_result"):
                        try:
                            consumer.on_tick_result(result)
                        except Exception:
                            logger.exception(
                                "Tick consumer on_tick_result error: %s", type(consumer).__name__
                            )
        except Exception as e:
            logger.error("Engine tick failed: %s", e)

    # ── Attention Assessment / 注意力评估 ──

    def _assess_attention(self, event: PriceEvent) -> str:
        """
        Determine the appropriate attention level based on current trading context.
        根据当前交易上下文确定适当的注意力等级。

        Decision hierarchy / 决策层级:
        1. No active session → dormant
        2. Volatility spike detected → critical
        3. Limit orders within proximity → high or critical
        4. Has positions but no pending orders → medium
        5. Active session but nothing happening → low
        """
        # Read paper trading state / 读取纸上交易状态
        try:
            state = self._engine.get_state()
        except Exception:
            return ATTENTION_DORMANT

        session_state = state.get("session", {}).get("session_state", "inactive")
        if session_state != SESSION_ACTIVE:
            return ATTENTION_DORMANT

        # Check for volatility spike / 检查波动率飙升
        if self._detect_volatility_spike(event.symbol, event.last_price):
            self._stats["volatility_spikes"] += 1
            return ATTENTION_CRITICAL

        # Check limit orders proximity / 检查限价单距离
        orders = state.get("orders", [])
        active_limits = [
            o for o in orders
            if o.get("state") in ACTIVE_STATES
            and o.get("order_type") == ORDER_TYPE_LIMIT
            and o.get("symbol") == event.symbol
        ]

        if active_limits:
            closest_pct = self._closest_order_distance_pct(active_limits, event.last_price)
            if closest_pct <= PROXIMITY_THRESHOLD_PCT * 0.3:
                # Very close: within 0.15% → critical (about to fill)
                # 非常接近：0.15% 以内 → critical（即将成交）
                return ATTENTION_CRITICAL
            elif closest_pct <= PROXIMITY_THRESHOLD_PCT:
                # Close: within 0.5% → high
                return ATTENTION_HIGH

        # Check for any active orders (not just limits for this symbol)
        # 检查所有活跃订单（不仅是当前交易对的限价单）
        any_active_orders = any(o.get("state") in ACTIVE_STATES for o in orders)
        if any_active_orders:
            return ATTENTION_HIGH

        # Check positions / 检查持仓
        positions = state.get("positions", {})
        if positions:
            return ATTENTION_MEDIUM

        return ATTENTION_LOW

    def _closest_order_distance_pct(
        self,
        orders: list[dict],
        current_price: float,
    ) -> float:
        """
        Find the closest limit order's distance from current price (in %).
        找到最近限价单与当前价的距离（百分比）。
        """
        if not orders or current_price <= 0:
            return float("inf")

        min_dist = float("inf")
        for order in orders:
            order_price = order.get("price")
            if order_price and order_price > 0:
                dist_pct = abs(current_price - order_price) / current_price * 100
                if dist_pct < min_dist:
                    min_dist = dist_pct
        return min_dist

    # ── Volatility Detection / 波动率检测 ──

    def _update_price_history(self, symbol: str, price: float) -> None:
        """Update the sliding window price history / 更新滑动窗口价格历史"""
        now = time.monotonic()
        if symbol not in self._price_history:
            self._price_history[symbol] = []

        history = self._price_history[symbol]
        history.append((now, price))

        # Trim old entries outside the window / 裁剪窗口外的旧数据
        cutoff = now - self._history_window_sec
        while history and history[0][0] < cutoff:
            history.pop(0)

    def _detect_volatility_spike(self, symbol: str, current_price: float) -> bool:
        """
        Detect if current price represents a volatility spike.
        检测当前价格是否代表波动率飙升。

        Compares current price to the average of recent prices in the sliding window.
        将当前价格与滑动窗口内近期价格的均值比较。
        """
        history = self._price_history.get(symbol, [])
        if len(history) < 5:
            return False

        # Use prices from 5-60 seconds ago as baseline (skip the most recent few)
        # 使用 5-60 秒前的价格作为基线（跳过最近几个）
        now = time.monotonic()
        baseline_prices = [
            p for t, p in history
            if (now - t) > 2.0  # at least 2 seconds old
        ]

        if len(baseline_prices) < 3:
            return False

        avg_baseline = sum(baseline_prices) / len(baseline_prices)
        if avg_baseline <= 0:
            return False

        change_pct = abs(current_price - avg_baseline) / avg_baseline * 100
        return change_pct >= VOLATILITY_SPIKE_PCT
