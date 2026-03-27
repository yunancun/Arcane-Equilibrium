"""
Kline Manager — OHLCV Candle Aggregation from Tick Data / K线管理器 — 从 Tick 数据聚合 OHLCV 蜡烛图

MODULE_NOTE (中文):
  本模块将实时 tick 数据（PriceEvent）聚合为标准 OHLCV K线。
  这是技术指标引擎的基础——所有指标（MA/RSI/MACD/BB/ATR）都需要 K线数据作为输入。

  核心设计：
  1. KlineBar — 单根 K线数据结构（open/high/low/close/volume + 时间戳）
  2. KlineBuffer — 环形缓冲区，固定容量，自动淘汰最旧的 K线
  3. KlineAggregator — 从 tick 聚合 K线，支持多时间框架（1m/5m/15m/1h/4h/1d）
  4. KlineManager — 顶层管理器，管理多个交易对 × 多个时间框架的 K线
  5. 支持注册回调：每根 K线闭合时通知下游（技术指标引擎）

  数据流：
    BybitPublicWsListener.PriceEvent
      → KlineManager.on_price_event()
        → KlineAggregator.on_tick() (每个时间框架各一个)
          → 累积 tick 直到当前周期结束
          → K线闭合 → 写入 KlineBuffer → 触发回调

  时间对齐规则：
  - 1m K线：对齐到整分钟（例如 10:05:00 ~ 10:05:59）
  - 5m K线：对齐到 5 分钟边界（例如 10:05:00 ~ 10:09:59）
  - 以此类推，所有时间框架都对齐到自然边界
  - 首根 K线可能不完整（从当前 tick 到下一个边界），这是正常的

MODULE_NOTE (English):
  This module aggregates real-time tick data (PriceEvent) into standard OHLCV klines.
  This is the foundation of the technical indicator engine — all indicators (MA/RSI/MACD/BB/ATR)
  require kline data as input.

  Core design:
  1. KlineBar — single kline data structure (open/high/low/close/volume + timestamps)
  2. KlineBuffer — circular buffer with fixed capacity, auto-evicts oldest klines
  3. KlineAggregator — aggregates ticks into klines, supports multiple timeframes
  4. KlineManager — top-level manager for multiple symbols × multiple timeframes
  5. Supports callback registration: notifies downstream (indicator engine) on kline close

  Data flow:
    BybitPublicWsListener.PriceEvent
      → KlineManager.on_price_event()
        → KlineAggregator.on_tick() (one per timeframe)
          → Accumulate ticks until current period ends
          → Kline closes → write to KlineBuffer → trigger callbacks

  Time alignment rules:
  - 1m klines: aligned to whole minutes (e.g., 10:05:00 ~ 10:05:59)
  - 5m klines: aligned to 5-minute boundaries (e.g., 10:05:00 ~ 10:09:59)
  - All timeframes are aligned to their natural boundaries
  - First kline may be incomplete (from current tick to next boundary), this is normal

Safety invariant / 安全不变量:
  - 纯数据处理，不涉及任何交易操作 / Pure data processing, no trading operations
  - 线程安全：所有公开方法可从任意线程调用 / Thread-safe: all public methods callable from any thread
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Callable

logger = logging.getLogger(__name__)


# =============================================================================
# Constants / 常量
# =============================================================================

# Supported timeframes and their durations in seconds
# 支持的时间框架及其对应的秒数
TIMEFRAME_DURATIONS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}

# Default timeframes to aggregate (balance between coverage and memory)
# 默认聚合的时间框架（在覆盖面和内存之间取平衡）
DEFAULT_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h"]

# Default buffer capacity per timeframe (how many klines to keep in memory)
# 每个时间框架的默认缓冲区容量（内存中保留多少根 K线）
# 500 × 1m = ~8.3 hours, 500 × 1h = ~20 days — 足够指标计算
DEFAULT_BUFFER_CAPACITY = 500

# Minimum number of ticks required to consider a kline valid
# 最少需要多少个 tick 才认为 K线有效（防止只有 1 个 tick 的退化 K线）
MIN_TICKS_FOR_VALID_KLINE = 1


# =============================================================================
# KlineBar — Single Kline Data / 单根 K线数据
# =============================================================================

class KlineBar:
    """
    A single OHLCV kline / candle bar.
    单根 OHLCV K线 / 蜡烛图柱。

    Fields:
      open_time_ms  — kline period start timestamp in ms / K线周期开始时间戳（毫秒）
      close_time_ms — kline period end timestamp in ms / K线周期结束时间戳（毫秒）
      open          — first trade price in this period / 本周期第一笔成交价
      high          — highest price in this period / 本周期最高价
      low           — lowest price in this period / 本周期最低价
      close         — last trade price in this period / 本周期最后一笔成交价
      volume        — cumulative volume in this period / 本周期累计成交量
      turnover      — cumulative turnover (value) in this period / 本周期累计成交额
      tick_count    — number of ticks aggregated into this kline / 汇入本 K线的 tick 数量
      is_closed     — whether this kline period has ended / 本 K线周期是否已结束
    """
    __slots__ = (
        "open_time_ms", "close_time_ms",
        "open", "high", "low", "close",
        "volume", "turnover", "tick_count", "is_closed",
    )

    def __init__(
        self,
        open_time_ms: int,
        close_time_ms: int,
        open_price: float,
        high: float | None = None,
        low: float | None = None,
        close: float | None = None,
        volume: float = 0.0,
        turnover: float = 0.0,
        tick_count: int = 1,
        is_closed: bool = False,
    ) -> None:
        self.open_time_ms = open_time_ms
        self.close_time_ms = close_time_ms
        self.open = open_price
        self.high = high if high is not None else open_price
        self.low = low if low is not None else open_price
        self.close = close if close is not None else open_price
        self.volume = volume
        self.turnover = turnover
        self.tick_count = tick_count
        self.is_closed = is_closed

    def update(self, price: float, volume: float = 0.0, turnover: float = 0.0) -> None:
        """
        Update this kline with a new tick / 用新 tick 更新本 K线

        Args:
          price    — latest trade price / 最新成交价
          volume   — trade volume to add / 追加成交量
          turnover — trade turnover to add / 追加成交额
        """
        if price > self.high:
            self.high = price
        if price < self.low:
            self.low = price
        self.close = price
        self.volume += volume
        self.turnover += turnover
        self.tick_count += 1

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for API responses / 序列化为字典（用于 API 返回）"""
        return {
            "open_time_ms": self.open_time_ms,
            "close_time_ms": self.close_time_ms,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "turnover": self.turnover,
            "tick_count": self.tick_count,
            "is_closed": self.is_closed,
        }

    def __repr__(self) -> str:
        return (
            f"KlineBar(O={self.open:.2f} H={self.high:.2f} "
            f"L={self.low:.2f} C={self.close:.2f} V={self.volume:.4f} "
            f"ticks={self.tick_count} closed={self.is_closed})"
        )


# =============================================================================
# KlineBuffer — Circular Buffer for Klines / K线环形缓冲区
# =============================================================================

class KlineBuffer:
    """
    Fixed-capacity circular buffer holding closed klines for one symbol + one timeframe.
    固定容量的环形缓冲区，保存一个交易对 + 一个时间框架的已闭合 K线。

    When full, oldest klines are automatically evicted.
    满时自动淘汰最旧的 K线。

    Usage:
      buf = KlineBuffer(capacity=500)
      buf.append(kline)           # Add a closed kline / 添加一根已闭合 K线
      buf.latest(20)              # Get latest 20 klines / 获取最近 20 根 K线
      closes = buf.close_array()  # Get all close prices as list / 获取所有收盘价列表
    """

    def __init__(self, capacity: int = DEFAULT_BUFFER_CAPACITY) -> None:
        self._capacity = capacity
        # deque with maxlen automatically evicts oldest when full
        # deque 设置 maxlen 后满时自动淘汰最旧元素
        self._bars: deque[KlineBar] = deque(maxlen=capacity)

    @property
    def capacity(self) -> int:
        """Maximum number of klines this buffer can hold / 缓冲区最大容量"""
        return self._capacity

    def __len__(self) -> int:
        """Number of klines currently in the buffer / 当前缓冲区内 K线数量"""
        return len(self._bars)

    def append(self, bar: KlineBar) -> None:
        """
        Append a closed kline to the buffer / 将一根已闭合 K线追加到缓冲区

        Args:
          bar — the kline to append (should be closed / 应该是已闭合的 K线)
        """
        self._bars.append(bar)

    def latest(self, n: int = 1) -> list[KlineBar]:
        """
        Get the latest N klines (newest last) / 获取最近 N 根 K线（最新的在最后）

        Args:
          n — how many klines to return / 返回多少根 K线

        Returns:
          List of KlineBar, ordered oldest-to-newest / K线列表，从旧到新排列
        """
        if n <= 0:
            return []
        if n >= len(self._bars):
            return list(self._bars)
        # deque slicing: take from the right end
        # deque 切片：从右端取
        start = len(self._bars) - n
        return [self._bars[i] for i in range(start, len(self._bars))]

    def close_array(self, n: int | None = None) -> list[float]:
        """
        Get close prices as a flat list (newest last) / 获取收盘价列表（最新的在最后）

        Args:
          n — how many to return (None = all) / 返回多少个（None = 全部）
        """
        bars = self.latest(n) if n else list(self._bars)
        return [b.close for b in bars]

    def high_array(self, n: int | None = None) -> list[float]:
        """Get high prices as a flat list / 获取最高价列表"""
        bars = self.latest(n) if n else list(self._bars)
        return [b.high for b in bars]

    def low_array(self, n: int | None = None) -> list[float]:
        """Get low prices as a flat list / 获取最低价列表"""
        bars = self.latest(n) if n else list(self._bars)
        return [b.low for b in bars]

    def open_array(self, n: int | None = None) -> list[float]:
        """Get open prices as a flat list / 获取开盘价列表"""
        bars = self.latest(n) if n else list(self._bars)
        return [b.open for b in bars]

    def volume_array(self, n: int | None = None) -> list[float]:
        """Get volume values as a flat list / 获取成交量列表"""
        bars = self.latest(n) if n else list(self._bars)
        return [b.volume for b in bars]

    def ohlcv_arrays(self, n: int | None = None) -> dict[str, list[float]]:
        """
        Get all OHLCV arrays at once (efficient single iteration) /
        一次性获取所有 OHLCV 数组（高效单次遍历）

        Returns:
          {"open": [...], "high": [...], "low": [...], "close": [...], "volume": [...]}
        """
        bars = self.latest(n) if n else list(self._bars)
        opens, highs, lows, closes, volumes = [], [], [], [], []
        for b in bars:
            opens.append(b.open)
            highs.append(b.high)
            lows.append(b.low)
            closes.append(b.close)
            volumes.append(b.volume)
        return {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }

    def clear(self) -> None:
        """Clear all klines from buffer / 清空缓冲区"""
        self._bars.clear()

    def to_list(self) -> list[dict[str, Any]]:
        """Serialize all klines to list of dicts / 序列化为字典列表"""
        return [b.to_dict() for b in self._bars]


# =============================================================================
# KlineAggregator — Tick-to-Kline Aggregation for One Timeframe
# K线聚合器 — 单时间框架的 Tick 到 K线聚合
# =============================================================================

class KlineAggregator:
    """
    Aggregates ticks into klines for a single timeframe (e.g., "5m").
    将 tick 数据聚合为单个时间框架（如 "5m"）的 K线。

    Time alignment:
      Klines are aligned to natural boundaries. For "5m", kline periods are:
        00:00-04:59, 05:00-09:59, 10:00-14:59, ...
      The first kline may start mid-period (incomplete), this is normal.
      K线对齐到自然边界。对于 "5m"，周期为：00-04, 05-09, 10-14, ...
      第一根 K线可能从周期中间开始（不完整），这是正常的。

    Usage:
      agg = KlineAggregator("5m", buffer=KlineBuffer(500), on_kline_close=my_callback)
      agg.on_tick(price=45000.0, volume=0.1, ts_ms=1711454321000)
    """

    def __init__(
        self,
        timeframe: str,
        buffer: KlineBuffer,
        on_kline_close: Callable[[str, KlineBar], None] | None = None,
    ) -> None:
        """
        Args:
          timeframe      — e.g., "1m", "5m", "15m", "1h", "4h", "1d"
          buffer         — KlineBuffer to store completed klines / 存放完成 K线的缓冲区
          on_kline_close — callback(timeframe, kline) when a kline closes / K线闭合时的回调
        """
        if timeframe not in TIMEFRAME_DURATIONS:
            raise ValueError(
                f"Unsupported timeframe '{timeframe}'. "
                f"Supported: {list(TIMEFRAME_DURATIONS.keys())} / "
                f"不支持的时间框架 '{timeframe}'，支持的有：{list(TIMEFRAME_DURATIONS.keys())}"
            )
        self._timeframe = timeframe
        self._duration_sec = TIMEFRAME_DURATIONS[timeframe]
        self._duration_ms = self._duration_sec * 1000
        self._buffer = buffer
        self._on_kline_close = on_kline_close

        # Current building kline (None until first tick) / 当前正在构建的 K线（首个 tick 前为 None）
        self._current_bar: KlineBar | None = None

    @property
    def timeframe(self) -> str:
        return self._timeframe

    @property
    def buffer(self) -> KlineBuffer:
        return self._buffer

    @property
    def current_bar(self) -> KlineBar | None:
        """The kline currently being built (not yet closed) / 当前正在构建的 K线（尚未闭合）"""
        return self._current_bar

    def _align_to_period_start(self, ts_ms: int) -> int:
        """
        Align a timestamp to the start of its kline period / 将时间戳对齐到其 K线周期的起始点

        Example for 5m timeframe:
          ts_ms = 10:07:23.456 → returns 10:05:00.000
          即 5 分钟框架下，10:07:23 对齐到 10:05:00

        Args:
          ts_ms — timestamp in milliseconds / 毫秒时间戳

        Returns:
          Period start timestamp in ms / 周期起始毫秒时间戳
        """
        period_start = (ts_ms // self._duration_ms) * self._duration_ms
        return period_start

    def on_tick(
        self,
        price: float,
        ts_ms: int,
        volume: float = 0.0,
        turnover: float = 0.0,
    ) -> KlineBar | None:
        """
        Process a single tick / 处理单个 tick

        If this tick belongs to the current kline period → update the current bar.
        If this tick starts a new period → close the current bar, start a new one.
        如果 tick 属于当前 K线周期 → 更新当前柱。
        如果 tick 开始了新周期 → 闭合当前柱，开始新柱。

        Args:
          price    — trade price / 成交价
          ts_ms    — timestamp in ms / 毫秒时间戳
          volume   — trade volume (optional) / 成交量（可选）
          turnover — trade turnover (optional) / 成交额（可选）

        Returns:
          The just-closed KlineBar if a kline was closed, else None
          如果有 K线被闭合则返回该 K线，否则返回 None
        """
        period_start = self._align_to_period_start(ts_ms)
        period_end = period_start + self._duration_ms

        closed_bar: KlineBar | None = None

        if self._current_bar is None:
            # First tick ever — start a new kline / 首个 tick — 创建新 K线
            self._current_bar = KlineBar(
                open_time_ms=period_start,
                close_time_ms=period_end,
                open_price=price,
                volume=volume,
                turnover=turnover,
            )
        elif ts_ms >= self._current_bar.close_time_ms:
            # Tick belongs to a new period → close the current kline
            # Tick 属于新周期 → 闭合当前 K线
            self._current_bar.is_closed = True
            closed_bar = self._current_bar
            self._buffer.append(closed_bar)

            # Notify downstream / 通知下游
            if self._on_kline_close is not None:
                try:
                    self._on_kline_close(self._timeframe, closed_bar)
                except Exception:
                    logger.exception(
                        "Kline close callback error / K线闭合回调异常, "
                        "timeframe=%s", self._timeframe,
                    )

            # Start new kline for the current period
            # 为当前周期创建新 K线
            self._current_bar = KlineBar(
                open_time_ms=period_start,
                close_time_ms=period_end,
                open_price=price,
                volume=volume,
                turnover=turnover,
            )
        else:
            # Same period → update current kline / 同一周期 → 更新当前 K线
            self._current_bar.update(price, volume, turnover)

        return closed_bar


# =============================================================================
# KlineManager — Multi-Symbol × Multi-Timeframe Manager
# K线管理器 — 多交易对 × 多时间框架管理
# =============================================================================

# Callback type: (symbol, timeframe, closed_kline_bar)
# 回调类型：(交易对, 时间框架, 已闭合的K线)
KlineCloseCallback = Callable[[str, str, KlineBar], None]


class KlineManager:
    """
    Top-level kline manager: manages multiple symbols × multiple timeframes.
    顶层 K线管理器：管理多个交易对 × 多个时间框架。

    This is the primary integration point with the rest of Phase 2:
    - Receives PriceEvent from BybitPublicWsListener (via MarketDataDispatcher or directly)
    - Aggregates into klines for each registered symbol × timeframe
    - Notifies downstream consumers (indicator engine, signal generator) on kline close
    本模块是与 Phase 2 其余部分的主要集成点：
    - 从 BybitPublicWsListener 接收 PriceEvent（通过 MarketDataDispatcher 或直接）
    - 为每个注册的交易对 × 时间框架聚合 K线
    - K线闭合时通知下游消费者（指标引擎、信号生成器）

    Thread-safe: all public methods are protected by a lock.
    线程安全：所有公开方法均受锁保护。

    Usage:
      manager = KlineManager(symbols=["BTCUSDT", "ETHUSDT"], timeframes=["1m", "5m", "1h"])
      manager.register_on_kline_close(my_indicator_engine.on_kline)
      # Feed from WebSocket:
      manager.on_price_event(price_event)
    """

    def __init__(
        self,
        symbols: list[str] | None = None,
        timeframes: list[str] | None = None,
        buffer_capacity: int = DEFAULT_BUFFER_CAPACITY,
    ) -> None:
        """
        Args:
          symbols          — trading pairs to manage / 管理的交易对列表
          timeframes       — timeframes to aggregate / 聚合的时间框架列表
          buffer_capacity  — max klines per buffer / 每个缓冲区最大 K线数
        """
        self._symbols = list(symbols or [])
        self._timeframes = list(timeframes or DEFAULT_TIMEFRAMES)
        self._buffer_capacity = buffer_capacity
        self._lock = threading.Lock()

        # Nested structure: symbol → timeframe → KlineAggregator
        # 嵌套结构：交易对 → 时间框架 → K线聚合器
        self._aggregators: dict[str, dict[str, KlineAggregator]] = {}

        # Callbacks to invoke on kline close: (symbol, timeframe, kline_bar)
        # K线闭合时调用的回调列表：(交易对, 时间框架, K线柱)
        self._on_close_callbacks: list[KlineCloseCallback] = []

        # Statistics / 统计
        self._stats = {
            "total_ticks_processed": 0,
            "total_klines_closed": 0,
            "ticks_by_symbol": {},
            "klines_by_symbol_tf": {},
        }

        # Initialize aggregators for all symbol × timeframe combinations
        # 为所有 交易对 × 时间框架 组合初始化聚合器
        for symbol in self._symbols:
            self._ensure_aggregators_for_symbol(symbol)

    def _ensure_aggregators_for_symbol(self, symbol: str) -> None:
        """
        Create aggregators for a symbol if not already present / 若尚无则为交易对创建聚合器

        Called internally (must hold self._lock or be in __init__).
        内部调用（调用时须持有 self._lock 或在 __init__ 中）。

        Note: Aggregators are created WITHOUT on_kline_close callback to avoid deadlock.
        注意：聚合器创建时不设置 on_kline_close 回调，以避免死锁。
        Instead, on_tick() return value is used to detect closed klines,
        and callbacks are fired AFTER the lock is released.
        改为通过 on_tick() 返回值检测闭合 K线，在锁释放后触发回调。
        """
        if symbol in self._aggregators:
            return
        self._aggregators[symbol] = {}
        for tf in self._timeframes:
            buf = KlineBuffer(self._buffer_capacity)
            # No callback here — closed bars are collected and dispatched outside lock
            # 此处不设回调 — 闭合的 K线在锁外统一分发
            agg = KlineAggregator(timeframe=tf, buffer=buf, on_kline_close=None)
            self._aggregators[symbol][tf] = agg
        self._stats["ticks_by_symbol"].setdefault(symbol, 0)
        logger.debug(
            "Initialized kline aggregators for %s, timeframes=%s / "
            "为 %s 初始化了 K线聚合器，时间框架=%s",
            symbol, self._timeframes, symbol, self._timeframes,
        )

    def _on_kline_closed(self, symbol: str, timeframe: str, bar: KlineBar) -> None:
        """
        Internal handler when any aggregator closes a kline / 任何聚合器闭合 K线时的内部处理

        Updates stats and invokes registered callbacks.
        更新统计信息并调用注册的回调。
        """
        # Update stats / 更新统计
        key = f"{symbol}:{timeframe}"
        self._stats["total_klines_closed"] += 1
        self._stats["klines_by_symbol_tf"][key] = (
            self._stats["klines_by_symbol_tf"].get(key, 0) + 1
        )

        logger.debug(
            "Kline closed / K线闭合: %s %s %s",
            symbol, timeframe, bar,
        )

        # Invoke all registered callbacks / 调用所有注册的回调
        for cb in self._on_close_callbacks:
            try:
                cb(symbol, timeframe, bar)
            except Exception:
                logger.exception(
                    "Kline close callback error / K线闭合回调异常, "
                    "symbol=%s, timeframe=%s", symbol, timeframe,
                )

    # ── Public Interface / 公开接口 ──

    def register_on_kline_close(self, callback: KlineCloseCallback) -> None:
        """
        Register a callback for kline close events / 注册 K线闭合事件的回调

        Callback signature: callback(symbol: str, timeframe: str, bar: KlineBar)
        回调签名：callback(交易对, 时间框架, K线柱)
        """
        with self._lock:
            self._on_close_callbacks.append(callback)

    def on_price_event(self, event: Any) -> None:
        """
        Feed a PriceEvent into the kline manager / 将 PriceEvent 输入 K线管理器

        Accepts either a PriceEvent object (with .symbol, .last_price, .ts_ms, .volume_24h)
        or a dict with the same keys. Designed to be plugged into MarketDataDispatcher or
        BybitPublicWsListener directly.
        接受 PriceEvent 对象（含 .symbol, .last_price, .ts_ms, .volume_24h）
        或具有相同键的字典。设计为可直接插入 MarketDataDispatcher 或 BybitPublicWsListener。

        Args:
          event — PriceEvent or dict with symbol/last_price/ts_ms fields
        """
        # Extract fields (support both PriceEvent objects and dicts)
        # 提取字段（同时支持 PriceEvent 对象和字典）
        if isinstance(event, dict):
            symbol = event.get("symbol", "")
            price = float(event.get("last_price", 0.0))
            ts_ms = int(event.get("ts_ms", 0) or time.time() * 1000)
            volume = float(event.get("volume_24h", 0.0) or 0.0)
            turnover = float(event.get("turnover_24h", 0.0) or 0.0)
        else:
            symbol = getattr(event, "symbol", "")
            price = float(getattr(event, "last_price", 0.0))
            ts_ms = int(getattr(event, "ts_ms", 0) or time.time() * 1000)
            volume = float(getattr(event, "volume_24h", 0.0) or 0.0)
            turnover = float(getattr(event, "turnover_24h", 0.0) or 0.0)

        if not symbol or price <= 0:
            return

        self._feed_tick(symbol, price, ts_ms, volume, turnover)

    def on_tick(
        self,
        symbol: str,
        price: float,
        ts_ms: int | None = None,
        volume: float = 0.0,
        turnover: float = 0.0,
    ) -> None:
        """
        Simplified tick input (alternative to on_price_event) /
        简化的 tick 输入（on_price_event 的替代接口）

        Args:
          symbol   — trading pair / 交易对
          price    — trade price / 成交价
          ts_ms    — timestamp in ms (None=now) / 毫秒时间戳（None=当前时间）
          volume   — trade volume / 成交量
          turnover — trade turnover / 成交额
        """
        if ts_ms is None:
            ts_ms = int(time.time() * 1000)

        self._feed_tick(symbol, price, ts_ms, volume, turnover)

    def _feed_tick(
        self,
        symbol: str,
        price: float,
        ts_ms: int,
        volume: float = 0.0,
        turnover: float = 0.0,
    ) -> None:
        """
        Internal: feed a tick, collect closed bars inside lock, fire callbacks outside lock.
        内部方法：在锁内输入 tick 并收集闭合 K线，在锁外触发回调（避免死锁）。
        """
        # Phase 1: inside lock — aggregate ticks, collect closed bars
        # 阶段 1：锁内 — 聚合 tick，收集闭合的 K线
        closed_bars: list[tuple[str, str, KlineBar]] = []  # (symbol, timeframe, bar)

        with self._lock:
            self._ensure_aggregators_for_symbol(symbol)
            for tf, agg in self._aggregators[symbol].items():
                closed = agg.on_tick(price=price, ts_ms=ts_ms, volume=volume, turnover=turnover)
                if closed is not None:
                    closed_bars.append((symbol, tf, closed))
            self._stats["total_ticks_processed"] += 1
            self._stats["ticks_by_symbol"][symbol] = (
                self._stats["ticks_by_symbol"].get(symbol, 0) + 1
            )

        # Phase 2: outside lock — fire callbacks (safe for callbacks to call get_ohlcv etc.)
        # 阶段 2：锁外 — 触发回调（回调可安全调用 get_ohlcv 等方法）
        for sym, tf, bar in closed_bars:
            self._on_kline_closed(sym, tf, bar)

    def add_symbol(self, symbol: str) -> None:
        """Add a symbol to track / 添加一个追踪的交易对"""
        with self._lock:
            if symbol not in self._symbols:
                self._symbols.append(symbol)
            self._ensure_aggregators_for_symbol(symbol)

    def remove_symbol(self, symbol: str) -> None:
        """Remove a symbol from tracking / 移除一个追踪的交易对"""
        with self._lock:
            if symbol in self._symbols:
                self._symbols.remove(symbol)
            self._aggregators.pop(symbol, None)

    def get_buffer(self, symbol: str, timeframe: str) -> KlineBuffer | None:
        """
        Get the kline buffer for a specific symbol + timeframe /
        获取指定交易对 + 时间框架的 K线缓冲区

        Returns None if symbol or timeframe is not tracked.
        如果交易对或时间框架未被追踪则返回 None。
        """
        with self._lock:
            aggs = self._aggregators.get(symbol, {})
            agg = aggs.get(timeframe)
            return agg.buffer if agg else None

    def get_current_bar(self, symbol: str, timeframe: str) -> KlineBar | None:
        """
        Get the currently building (not yet closed) kline /
        获取当前正在构建的（尚未闭合的）K线

        Useful for displaying real-time "live" kline in GUI.
        适合在 GUI 中显示实时"活"K线。
        """
        with self._lock:
            aggs = self._aggregators.get(symbol, {})
            agg = aggs.get(timeframe)
            return agg.current_bar if agg else None

    def get_latest_klines(
        self, symbol: str, timeframe: str, n: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Get latest N closed klines as dicts (for API) /
        获取最近 N 根已闭合 K线的字典形式（用于 API）

        Args:
          symbol    — trading pair / 交易对
          timeframe — e.g., "5m" / 时间框架
          n         — how many klines / 返回多少根

        Returns:
          List of kline dicts, oldest first / K线字典列表，最旧的在前
        """
        buf = self.get_buffer(symbol, timeframe)
        if buf is None:
            return []
        return [bar.to_dict() for bar in buf.latest(n)]

    def get_ohlcv(
        self, symbol: str, timeframe: str, n: int | None = None,
    ) -> dict[str, list[float]]:
        """
        Get OHLCV arrays for indicator calculation /
        获取用于指标计算的 OHLCV 数组

        Returns:
          {"open": [...], "high": [...], "low": [...], "close": [...], "volume": [...]}
          Empty dict if buffer not found.
        """
        buf = self.get_buffer(symbol, timeframe)
        if buf is None or len(buf) == 0:
            return {"open": [], "high": [], "low": [], "close": [], "volume": []}
        return buf.ohlcv_arrays(n)

    def get_stats(self) -> dict[str, Any]:
        """Get aggregation statistics / 获取聚合统计信息"""
        with self._lock:
            stats = dict(self._stats)
            stats["symbols_tracked"] = list(self._symbols)
            stats["timeframes"] = list(self._timeframes)
            stats["buffers"] = {}
            for sym, aggs in self._aggregators.items():
                for tf, agg in aggs.items():
                    stats["buffers"][f"{sym}:{tf}"] = {
                        "closed_klines": len(agg.buffer),
                        "capacity": agg.buffer.capacity,
                        "has_current_bar": agg.current_bar is not None,
                    }
            return stats

    def get_status(self) -> dict[str, Any]:
        """Get comprehensive status for API / 获取 API 用的综合状态"""
        return {
            "component": "kline_manager",
            "symbols": list(self._symbols),
            "timeframes": list(self._timeframes),
            "stats": self.get_stats(),
            "is_simulated": True,
            "data_category": "paper_simulated",
        }

    def clear_all(self) -> None:
        """Clear all buffers and reset state / 清空所有缓冲区并重置状态"""
        with self._lock:
            for aggs in self._aggregators.values():
                for agg in aggs.values():
                    agg.buffer.clear()
            self._stats = {
                "total_ticks_processed": 0,
                "total_klines_closed": 0,
                "ticks_by_symbol": {},
                "klines_by_symbol_tf": {},
            }
