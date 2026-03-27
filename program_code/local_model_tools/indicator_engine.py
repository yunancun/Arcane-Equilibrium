"""
Indicator Engine — Unified Technical Indicator Computation Hub
指标引擎 — 统一技术指标计算中枢

MODULE_NOTE (中文):
  本模块是 Phase 2 技术指标系统的核心枢纽，连接 K线管理器和信号生成器。
  职责：
  1. 管理多个交易对 × 多个时间框架的指标实例
  2. 在 K线闭合时自动重新计算相关指标
  3. 缓存最新指标值，供信号生成器和 API 查询
  4. 提供统一的 get_indicators() 接口

  数据流：
    KlineManager (K线闭合回调)
      → IndicatorEngine.on_kline_close(symbol, timeframe, bar)
        → 获取该 symbol+timeframe 的 OHLCV 数据
        → 逐个计算注册的指标
        → 缓存结果到 _indicator_cache
        → 触发下游回调（信号生成器）

  设计原则：
  1. 懒计算 — 只在 K线闭合时计算，不轮询
  2. 统一缓存 — 所有指标结果集中管理，避免重复计算
  3. 可扩展 — 通过 register_indicator() 动态添加新指标
  4. 零 AI 成本 — 全部本地计算

MODULE_NOTE (English):
  This module is the central hub of the Phase 2 technical indicator system,
  connecting the Kline Manager to the Signal Generator.
  Responsibilities:
  1. Manage indicator instances across multiple symbols × timeframes
  2. Auto-recompute relevant indicators when a kline closes
  3. Cache latest indicator values for signal generator and API queries
  4. Provide unified get_indicators() interface

  Data flow:
    KlineManager (kline close callback)
      → IndicatorEngine.on_kline_close(symbol, timeframe, bar)
        → Get OHLCV data for that symbol+timeframe
        → Compute each registered indicator
        → Cache results in _indicator_cache
        → Trigger downstream callbacks (signal generator)

  Design principles:
  1. Lazy computation — only compute on kline close, no polling
  2. Unified cache — all indicator results centrally managed, avoid redundant computation
  3. Extensible — dynamically add new indicators via register_indicator()
  4. Zero AI cost — all local computation

Safety invariant / 安全不变量:
  - 纯数据处理，不涉及交易操作 / Pure data processing, no trading operations
  - 线程安全 / Thread-safe
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from .indicators.atr import ATR
from .indicators.bollinger_bands import BollingerBands
from .indicators.macd import MACD
from .indicators.moving_averages import EMA, SMA
from .indicators.rsi import RSI
from .indicators.stochastic import Stochastic
from .indicators.base import IndicatorBase
from .kline_manager import KlineBar, KlineManager

logger = logging.getLogger(__name__)


# =============================================================================
# Default Indicator Set / 默认指标集
# =============================================================================

def create_default_indicators() -> list[IndicatorBase]:
    """
    Create the default set of indicators used by the system.
    创建系统默认使用的指标集。

    These cover the four main analysis dimensions:
    覆盖四个主要分析维度：
    - Trend (趋势): SMA, EMA, MACD
    - Momentum (动量): RSI, Stochastic
    - Volatility (波动率): Bollinger Bands, ATR
    - Support/Resistance (支撑/阻力): Bollinger Bands

    Returns:
      List of indicator instances / 指标实例列表
    """
    return [
        # Trend indicators / 趋势指标
        SMA(period=20),     # SMA(20) — 20 周期简单移动平均
        SMA(period=50),     # SMA(50) — 50 周期简单移动平均
        EMA(period=12),     # EMA(12) — 12 周期指数移动平均（MACD fast）
        EMA(period=26),     # EMA(26) — 26 周期指数移动平均（MACD slow）
        MACD(),             # MACD(12,26,9) — 经典 MACD

        # Momentum indicators / 动量指标
        RSI(period=14),     # RSI(14) — 14 周期相对强弱指数
        Stochastic(),       # Stochastic(14,3) — 随机振荡指标

        # Volatility indicators / 波动率指标
        BollingerBands(),   # BB(20,2) — 布林带
        ATR(period=14),     # ATR(14) — 14 周期平均真实波幅
    ]


# =============================================================================
# Indicator Update Callback Type / 指标更新回调类型
# =============================================================================

# callback(symbol, timeframe, indicator_results)
# 回调(交易对, 时间框架, 指标计算结果)
IndicatorUpdateCallback = Callable[[str, str, dict[str, Any]], None]


# =============================================================================
# IndicatorEngine / 指标引擎
# =============================================================================

class IndicatorEngine:
    """
    Unified indicator computation engine.
    统一指标计算引擎。

    Automatically computes all registered indicators when klines close,
    caches results, and notifies downstream consumers.
    K线闭合时自动计算所有注册指标，缓存结果，通知下游消费者。

    Usage:
      engine = IndicatorEngine(kline_manager=km)
      engine.register_on_update(signal_generator.on_indicators_update)
      # Now every kline close will trigger indicator computation + callback
      # 每次 K线闭合都会触发指标计算 + 回调

      # Or query manually:
      result = engine.get_indicators("BTCUSDT", "5m")
      # → {"SMA(20)": {"sma": 45000}, "RSI(14)": {"rsi": 65.3}, ...}
    """

    def __init__(
        self,
        kline_manager: KlineManager,
        indicators: list[IndicatorBase] | None = None,
    ) -> None:
        """
        Args:
          kline_manager — the KlineManager instance to pull OHLCV data from /
                          用于获取 OHLCV 数据的 KlineManager 实例
          indicators    — list of indicator instances (None = use defaults) /
                          指标实例列表（None = 使用默认集）
        """
        self._kline_manager = kline_manager
        self._indicators = list(indicators or create_default_indicators())
        self._lock = threading.Lock()

        # Cache: (symbol, timeframe) → {indicator_name: result_dict}
        # 缓存：(交易对, 时间框架) → {指标名称: 结果字典}
        self._cache: dict[tuple[str, str], dict[str, Any]] = {}

        # Timestamp of last update per (symbol, timeframe)
        # 每个 (交易对, 时间框架) 的最后更新时间戳
        self._last_update: dict[tuple[str, str], float] = {}

        # Downstream callbacks / 下游回调
        self._on_update_callbacks: list[IndicatorUpdateCallback] = []

        # Statistics / 统计
        self._stats = {
            "total_computations": 0,
            "computation_errors": 0,
            "cache_hits": 0,
        }

        # Register with kline manager / 注册到 K线管理器
        self._kline_manager.register_on_kline_close(self._on_kline_close)
        logger.info(
            "IndicatorEngine initialized with %d indicators: %s / "
            "指标引擎初始化完成，%d 个指标：%s",
            len(self._indicators),
            [i.name for i in self._indicators],
            len(self._indicators),
            [i.name for i in self._indicators],
        )

    # ── Registration / 注册 ──

    def register_indicator(self, indicator: IndicatorBase) -> None:
        """
        Register a new indicator for computation / 注册新指标
        """
        with self._lock:
            self._indicators.append(indicator)
        logger.info("Registered indicator / 注册指标: %s", indicator.name)

    def register_on_update(self, callback: IndicatorUpdateCallback) -> None:
        """
        Register a callback for indicator update events / 注册指标更新回调

        Called after all indicators are computed for a (symbol, timeframe).
        在某个 (交易对, 时间框架) 的所有指标计算完成后调用。
        Signature: callback(symbol, timeframe, all_indicator_results)
        """
        with self._lock:
            self._on_update_callbacks.append(callback)

    # ── Core: Kline Close Handler / 核心：K线闭合处理 ──

    def _on_kline_close(self, symbol: str, timeframe: str, bar: KlineBar) -> None:
        """
        Called by KlineManager when a kline closes.
        K线闭合时由 KlineManager 调用。

        Fetches OHLCV data from the kline buffer, computes all indicators,
        caches the results, and notifies downstream.
        从 K线缓冲区获取 OHLCV 数据，计算所有指标，缓存结果，通知下游。
        """
        # Get OHLCV arrays from kline manager / 从 K线管理器获取 OHLCV 数组
        ohlcv = self._kline_manager.get_ohlcv(symbol, timeframe)
        if not ohlcv or not ohlcv.get("close"):
            return

        # Compute all indicators / 计算所有指标
        results = self._compute_all(ohlcv)

        with self._lock:
            key = (symbol, timeframe)
            self._cache[key] = results
            self._last_update[key] = time.time()

        # Notify downstream callbacks / 通知下游回调
        for cb in self._on_update_callbacks:
            try:
                cb(symbol, timeframe, results)
            except Exception:
                logger.exception(
                    "Indicator update callback error / 指标更新回调异常, "
                    "symbol=%s, timeframe=%s", symbol, timeframe,
                )

    def _compute_all(self, ohlcv: dict[str, list[float]]) -> dict[str, Any]:
        """
        Compute all registered indicators from OHLCV data.
        从 OHLCV 数据计算所有注册的指标。

        Args:
          ohlcv — {"open": [...], "high": [...], "low": [...], "close": [...], "volume": [...]}

        Returns:
          {indicator_name: result_dict_or_None} for each indicator
        """
        results: dict[str, Any] = {}

        with self._lock:
            indicators = list(self._indicators)

        for indicator in indicators:
            try:
                result = indicator.compute(
                    open=ohlcv.get("open", []),
                    high=ohlcv.get("high", []),
                    low=ohlcv.get("low", []),
                    close=ohlcv.get("close", []),
                    volume=ohlcv.get("volume", []),
                )
                results[indicator.name] = result
                self._stats["total_computations"] += 1
            except Exception:
                logger.exception(
                    "Indicator computation error / 指标计算异常: %s",
                    indicator.name,
                )
                results[indicator.name] = None
                self._stats["computation_errors"] += 1

        return results

    # ── Public Query Interface / 公开查询接口 ──

    def get_indicators(
        self, symbol: str, timeframe: str,
    ) -> dict[str, Any]:
        """
        Get latest cached indicator values for a symbol + timeframe.
        获取指定交易对 + 时间框架的最新缓存指标值。

        Args:
          symbol    — trading pair (e.g., "BTCUSDT") / 交易对
          timeframe — e.g., "5m", "1h" / 时间框架

        Returns:
          {indicator_name: result_dict_or_None} or empty dict if no data
          {指标名称: 结果字典或None}，无数据时返回空字典
        """
        with self._lock:
            key = (symbol, timeframe)
            self._stats["cache_hits"] += 1
            return dict(self._cache.get(key, {}))

    def get_indicator(
        self, symbol: str, timeframe: str, indicator_name: str,
    ) -> dict[str, Any] | None:
        """
        Get a specific indicator's latest value / 获取特定指标的最新值

        Args:
          symbol         — trading pair / 交易对
          timeframe      — timeframe / 时间框架
          indicator_name — e.g., "RSI(14)" / 指标名称

        Returns:
          Indicator result dict or None / 指标结果字典或 None
        """
        with self._lock:
            key = (symbol, timeframe)
            cached = self._cache.get(key, {})
            return cached.get(indicator_name)

    def compute_now(self, symbol: str, timeframe: str) -> dict[str, Any]:
        """
        Force immediate computation (don't wait for kline close).
        强制立即计算（不等待 K线闭合）。

        Useful for initial state or debugging.
        适合初始状态或调试。
        """
        ohlcv = self._kline_manager.get_ohlcv(symbol, timeframe)
        if not ohlcv or not ohlcv.get("close"):
            return {}
        results = self._compute_all(ohlcv)
        with self._lock:
            key = (symbol, timeframe)
            self._cache[key] = results
            self._last_update[key] = time.time()
        return results

    def get_all_cached(self) -> dict[str, dict[str, Any]]:
        """
        Get all cached indicator values across all symbols and timeframes.
        获取所有交易对和时间框架的缓存指标值。

        Returns:
          {"BTCUSDT:5m": {indicators...}, "ETHUSDT:1h": {indicators...}, ...}
        """
        with self._lock:
            return {
                f"{sym}:{tf}": dict(vals)
                for (sym, tf), vals in self._cache.items()
            }

    def get_status(self) -> dict[str, Any]:
        """Get engine status for API / 获取引擎状态"""
        with self._lock:
            return {
                "component": "indicator_engine",
                "indicators_registered": [i.name for i in self._indicators],
                "indicator_count": len(self._indicators),
                "cached_pairs": [
                    f"{sym}:{tf}" for sym, tf in self._cache.keys()
                ],
                "stats": dict(self._stats),
                "last_updates": {
                    f"{sym}:{tf}": ts
                    for (sym, tf), ts in self._last_update.items()
                },
            }

    def clear_cache(self) -> None:
        """Clear all cached indicator values / 清除所有缓存的指标值"""
        with self._lock:
            self._cache.clear()
            self._last_update.clear()
