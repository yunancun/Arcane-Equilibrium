"""
Signal Generator — Turn Indicator Values into Trading Signals
信号生成器 — 将指标值转化为交易信号

MODULE_NOTE (中文):
  本模块是技术指标和交易策略之间的桥梁。
  指标引擎输出原始数值（RSI=65.3, MACD histogram=0.2），
  信号生成器将这些数值解读为可执行的交易信号。

  核心概念：
  1. Signal — 一个结构化的交易建议，包含：
     - symbol: 交易对
     - direction: "long" / "short" / "close_long" / "close_short" / "neutral"
     - confidence: 信号置信度 (0.0 ~ 1.0)
     - edge_bps: 预期边际收益（基点）
     - source: 信号来源（哪个指标/哪个策略）
     - reasoning: 人类可读的信号理由

  2. SignalRule — 抽象规则类，子类实现具体的信号逻辑
     - evaluate(indicators) → Signal | None

  3. SignalEngine — 管理多个 SignalRule，统一评估和历史记录

  信号并不直接下单。信号 → 策略编排器 → 风控检查 → Paper Trading Engine。
  这样保证每一层都有独立的职责和检查。

MODULE_NOTE (English):
  This module bridges technical indicators and trading strategies.
  The indicator engine outputs raw values (RSI=65.3, MACD histogram=0.2),
  the signal generator interprets these into actionable trading signals.

  Core concepts:
  1. Signal — a structured trading recommendation containing:
     - symbol: trading pair
     - direction: "long" / "short" / "close_long" / "close_short" / "neutral"
     - confidence: signal confidence (0.0 ~ 1.0)
     - edge_bps: expected edge in basis points
     - source: signal source (which indicator/strategy)
     - reasoning: human-readable rationale

  2. SignalRule — abstract rule class, subclasses implement specific signal logic
     - evaluate(indicators) → Signal | None

  3. SignalEngine — manages multiple SignalRules, unified evaluation and history

  Signals do NOT submit orders directly. Signal → Strategy Orchestrator → Risk Check
  → Paper Trading Engine. Each layer has independent responsibilities.

Safety invariant / 安全不变量:
  - 信号只是建议，不直接执行任何交易 / Signals are recommendations only, never execute trades
  - 线程安全 / Thread-safe
"""

from __future__ import annotations

import logging
import math
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from typing import Any, Callable

logger = logging.getLogger(__name__)


# =============================================================================
# Constants / 常量
# =============================================================================

# Signal directions / 信号方向
DIRECTION_LONG = "long"               # 开多 / 加多
DIRECTION_SHORT = "short"             # 开空 / 加空
DIRECTION_CLOSE_LONG = "close_long"   # 平多
DIRECTION_CLOSE_SHORT = "close_short" # 平空
DIRECTION_NEUTRAL = "neutral"         # 无操作
ALL_DIRECTIONS = {DIRECTION_LONG, DIRECTION_SHORT, DIRECTION_CLOSE_LONG, DIRECTION_CLOSE_SHORT, DIRECTION_NEUTRAL}

# Signal history capacity / 信号历史容量
SIGNAL_HISTORY_CAPACITY = 1000


# =============================================================================
# Signal — Structured Trading Signal / 结构化交易信号
# =============================================================================

class Signal:
    """
    A structured trading signal / recommendation.
    结构化的交易信号 / 建议。

    This is the output of a SignalRule evaluation. It captures what to do,
    how confident we are, and why.
    这是 SignalRule 评估的输出，捕获要做什么、多有把握、以及为什么。

    Attributes:
      symbol      — trading pair (e.g., "BTCUSDT") / 交易对
      direction   — "long" / "short" / "close_long" / "close_short" / "neutral" / 方向
      confidence  — 0.0 to 1.0, how confident this signal is / 信号置信度
      edge_bps    — expected edge in basis points (1 bps = 0.01%) / 预期边际（基点）
      source      — which rule/indicator generated this signal / 信号来源
      timeframe   — which timeframe this signal is based on / 基于的时间框架
      reasoning   — human-readable explanation / 人类可读的解释
      ts_ms       — signal generation timestamp in ms / 信号生成时间戳
      metadata    — arbitrary extra data / 额外数据
    """
    __slots__ = (
        "symbol", "direction", "confidence", "edge_bps",
        "source", "timeframe", "reasoning", "ts_ms", "metadata",
    )

    def __init__(
        self,
        symbol: str,
        direction: str,
        confidence: float,
        edge_bps: float = 0.0,
        source: str = "",
        timeframe: str = "",
        reasoning: str = "",
        ts_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if direction not in ALL_DIRECTIONS:
            raise ValueError(
                f"Invalid direction '{direction}'. Must be one of {ALL_DIRECTIONS} / "
                f"无效方向 '{direction}'，必须是 {ALL_DIRECTIONS} 之一"
            )
        self.symbol = symbol
        self.direction = direction
        self.confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1] / 限制到 [0, 1]
        if confidence < 0.0 or confidence > 1.0:
            logger.debug(
                "Signal confidence clamped: %.4f → %.4f / 信号置信度被截断",
                confidence, self.confidence,
            )
        self.edge_bps = edge_bps
        self.source = source
        self.timeframe = timeframe
        self.reasoning = reasoning
        self.ts_ms = ts_ms if ts_ms is not None else int(time.time() * 1000)
        self.metadata = metadata or {}

    @property
    def is_actionable(self) -> bool:
        """Whether this signal suggests an action (not neutral) / 是否建议行动（非中性）"""
        return self.direction != DIRECTION_NEUTRAL

    @property
    def is_entry(self) -> bool:
        """Whether this is an entry signal (long or short) / 是否为入场信号"""
        return self.direction in (DIRECTION_LONG, DIRECTION_SHORT)

    @property
    def is_exit(self) -> bool:
        """Whether this is an exit signal (close_long or close_short) / 是否为出场信号"""
        return self.direction in (DIRECTION_CLOSE_LONG, DIRECTION_CLOSE_SHORT)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for API responses / 序列化为字典"""
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "confidence": round(self.confidence, 4),
            "edge_bps": round(self.edge_bps, 2),
            "source": self.source,
            "timeframe": self.timeframe,
            "reasoning": self.reasoning,
            "ts_ms": self.ts_ms,
            "is_actionable": self.is_actionable,
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        return (
            f"Signal({self.symbol} {self.direction} "
            f"conf={self.confidence:.2f} edge={self.edge_bps:.0f}bps "
            f"src={self.source})"
        )


# =============================================================================
# SignalRule — Abstract Base for Signal Logic / 信号规则抽象基类
# =============================================================================

class SignalRule(ABC):
    """
    Abstract base class for signal generation rules.
    信号生成规则的抽象基类。

    Each rule evaluates indicator values and optionally produces a Signal.
    每个规则评估指标值，选择性地产生一个 Signal。

    Subclasses must implement:
      - name: rule name / 规则名称
      - evaluate(symbol, timeframe, indicators) → Signal | None
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable rule name / 人类可读的规则名称"""
        ...

    @abstractmethod
    def evaluate(
        self,
        symbol: str,
        timeframe: str,
        indicators: dict[str, Any],
    ) -> Signal | None:
        """
        Evaluate indicators and optionally generate a signal.
        评估指标值，选择性地生成信号。

        Args:
          symbol     — trading pair / 交易对
          timeframe  — timeframe of the indicators / 指标的时间框架
          indicators — {indicator_name: result_dict}, e.g., {"RSI(14)": {"rsi": 65.3}}

        Returns:
          Signal if conditions are met, None otherwise
          满足条件时返回 Signal，否则返回 None
        """
        ...


# =============================================================================
# Built-in Signal Rules / 内置信号规则
# =============================================================================

class RSIOverboughtOversoldRule(SignalRule):
    """
    RSI overbought/oversold reversal signal.
    RSI 超买/超卖反转信号。

    Logic:
    - RSI < oversold_threshold (default 30) → long signal (预期反弹)
    - RSI > overbought_threshold (default 70) → short signal (预期回落)

    This is a mean-reversion signal. Works best in ranging markets,
    may produce false signals in strong trends.
    这是均值回归信号。在震荡市场效果最好，强趋势中可能产生假信号。
    """

    def __init__(
        self,
        rsi_indicator_name: str = "RSI(14)",
        oversold: float = 30.0,
        overbought: float = 70.0,
    ) -> None:
        if oversold >= overbought:
            raise ValueError(f"oversold ({oversold}) must be < overbought ({overbought})")
        self._rsi_name = rsi_indicator_name
        self._oversold = oversold
        self._overbought = overbought

    @property
    def name(self) -> str:
        return f"RSI_OB_OS({self._oversold}/{self._overbought})"

    def evaluate(self, symbol: str, timeframe: str, indicators: dict[str, Any]) -> Signal | None:
        rsi_data = indicators.get(self._rsi_name)
        if not rsi_data or "rsi" not in rsi_data:
            return None

        rsi = rsi_data["rsi"]
        if not isinstance(rsi, (int, float)) or not math.isfinite(rsi):
            return None

        # Attach V2 metadata for downstream strategies / 为下游策略附加 V2 元数据
        adx_val = indicators.get("ADX(14)", {}).get("adx")
        volume_ratio_val = indicators.get("VolumeRatio(20)", {}).get("volume_ratio")

        if rsi <= self._oversold:
            # Oversold → expect bounce → long / 超卖 → 预期反弹 → 做多
            # Confidence scales with how extreme the RSI is / 置信度随 RSI 极端程度增加
            confidence = min(1.0, (self._oversold - rsi) / self._oversold + 0.3)
            meta = {"rsi": rsi}
            if adx_val is not None:
                meta["adx"] = adx_val
            if volume_ratio_val is not None:
                meta["volume_ratio"] = volume_ratio_val
            return Signal(
                symbol=symbol,
                direction=DIRECTION_LONG,
                confidence=confidence,
                edge_bps=max(10, (self._oversold - rsi) * 3),
                source=self.name,
                timeframe=timeframe,
                reasoning=f"RSI={rsi:.1f} < {self._oversold} (oversold/超卖), expect bounce/预期反弹",
                metadata=meta,
            )

        if rsi >= self._overbought:
            # Overbought → expect pullback → short / 超买 → 预期回落 → 做空
            confidence = min(1.0, (rsi - self._overbought) / (100 - self._overbought) + 0.3)
            meta = {"rsi": rsi}
            if adx_val is not None:
                meta["adx"] = adx_val
            if volume_ratio_val is not None:
                meta["volume_ratio"] = volume_ratio_val
            return Signal(
                symbol=symbol,
                direction=DIRECTION_SHORT,
                confidence=confidence,
                edge_bps=max(10, (rsi - self._overbought) * 3),
                source=self.name,
                timeframe=timeframe,
                reasoning=f"RSI={rsi:.1f} > {self._overbought} (overbought/超买), expect pullback/预期回落",
                metadata=meta,
            )

        return None


class MACrossoverRule(SignalRule):
    """
    Moving Average crossover signal.
    移动平均线交叉信号。

    Logic:
    - Fast MA > Slow MA → long (uptrend, 上升趋势)
    - Fast MA < Slow MA → short (downtrend, 下降趋势)

    Classic trend-following signal. Works best in trending markets.
    经典趋势跟踪信号。在趋势市场效果最好。

    Note: This rule generates signals based on MA spread levels (fast above/below slow),
    not on the actual crossing event. It will emit a signal on every evaluation tick
    as long as the spread exceeds the threshold.
    注意：本规则基于 MA 价差水平（快线在慢线上/下方）生成信号，
    而非真正的交叉事件。只要价差超过阈值，每次评估都会生成信号。
    """

    def __init__(
        self,
        fast_name: str = "EMA(12)",
        slow_name: str = "EMA(26)",
    ) -> None:
        self._fast_name = fast_name
        self._slow_name = slow_name

    @property
    def name(self) -> str:
        return f"MA_Cross({self._fast_name}/{self._slow_name})"

    def evaluate(self, symbol: str, timeframe: str, indicators: dict[str, Any]) -> Signal | None:
        fast_data = indicators.get(self._fast_name)
        slow_data = indicators.get(self._slow_name)
        if not fast_data or not slow_data:
            return None

        # Extract the MA value (could be "sma" or "ema" key)
        # 提取 MA 值（可能是 "sma" 或 "ema" 键）
        # Use `is not None` instead of `or` to handle 0.0 correctly / 用 is not None 正确处理 0.0
        fast_val = fast_data.get("ema")
        if fast_val is None:
            fast_val = fast_data.get("sma")
        slow_val = slow_data.get("ema")
        if slow_val is None:
            slow_val = slow_data.get("sma")
        if fast_val is None or slow_val is None:
            return None
        if not math.isfinite(fast_val) or not math.isfinite(slow_val):
            return None

        # Calculate the spread as percentage / 计算价差百分比
        if abs(slow_val) < 1e-12:
            return None
        spread_pct = (fast_val - slow_val) / slow_val * 100

        # Need a minimum spread to generate signal (avoid noise)
        # 需要最小价差才生成信号（避免噪音）
        min_spread_pct = 0.05  # 0.05% minimum spread / 最小 0.05% 价差

        # Attach V2 metadata for downstream strategies / 为下游策略附加 V2 元数据
        adx_val = indicators.get("ADX(14)", {}).get("adx")
        volume_ratio_val = indicators.get("VolumeRatio(20)", {}).get("volume_ratio")

        # A1: Donchian channel data for downstream confirmation
        # A1：Donchian 通道数据供下游确认
        donchian_data = indicators.get("Donchian(20)")
        donchian_high = donchian_data.get("upper") if isinstance(donchian_data, dict) else None
        donchian_low = donchian_data.get("lower") if isinstance(donchian_data, dict) else None

        # A2: Close price — use fast MA value as proxy (closest to current close)
        # A2：收盘价 — 用快线 MA 值作为代理（最接近当前收盘价）
        close_price = fast_val

        if spread_pct > min_spread_pct:
            # Fast above slow → bullish / 快线在慢线上方 → 看多
            confidence = min(1.0, spread_pct / 1.0 * 0.5 + 0.2)
            meta: dict[str, Any] = {"close": close_price}
            if adx_val is not None:
                meta["adx"] = adx_val
            if volume_ratio_val is not None:
                meta["volume_ratio"] = volume_ratio_val
            if donchian_high is not None:
                meta["donchian_high"] = donchian_high
            if donchian_low is not None:
                meta["donchian_low"] = donchian_low
            return Signal(
                symbol=symbol,
                direction=DIRECTION_LONG,
                confidence=confidence,
                edge_bps=max(5, spread_pct * 10),
                source=self.name,
                timeframe=timeframe,
                reasoning=(
                    f"{self._fast_name}={fast_val:.2f} > {self._slow_name}={slow_val:.2f} "
                    f"(spread={spread_pct:.3f}%, bullish/看多)"
                ),
                metadata=meta,
            )

        if spread_pct < -min_spread_pct:
            # Fast below slow → bearish / 快线在慢线下方 → 看空
            confidence = min(1.0, abs(spread_pct) / 1.0 * 0.5 + 0.2)
            meta = {"close": close_price}
            if adx_val is not None:
                meta["adx"] = adx_val
            if volume_ratio_val is not None:
                meta["volume_ratio"] = volume_ratio_val
            if donchian_high is not None:
                meta["donchian_high"] = donchian_high
            if donchian_low is not None:
                meta["donchian_low"] = donchian_low
            return Signal(
                symbol=symbol,
                direction=DIRECTION_SHORT,
                confidence=confidence,
                edge_bps=max(5, abs(spread_pct) * 10),
                source=self.name,
                timeframe=timeframe,
                reasoning=(
                    f"{self._fast_name}={fast_val:.2f} < {self._slow_name}={slow_val:.2f} "
                    f"(spread={spread_pct:.3f}%, bearish/看空)"
                ),
                metadata=meta,
            )

        return None


class KAMACrossoverRule(SignalRule):
    """
    KAMA (Kaufman Adaptive MA) crossover signal.
    KAMA 自適應移動平均交叉信號。

    B1: Fires when KAMA crosses above/below EMA — adaptive trend detection.
    B1：當 KAMA 穿越 EMA 上方/下方時觸發 — 自適應趨勢偵測。

    Logic:
    - KAMA > EMA → long (adaptive trend up / 自適應上升趨勢)
    - KAMA < EMA → short (adaptive trend down / 自適應下降趨勢)
    - Uses efficiency_ratio to boost confidence when trend is clean.
      利用效率比提升趨勢乾淨時的信心。

    Safety invariant: signals only, no execution / 僅產生信號，不執行
    """

    def __init__(
        self,
        kama_name: str = "KAMA(10)",
        ema_name: str = "EMA(12)",
    ) -> None:
        self._kama_name = kama_name
        self._ema_name = ema_name

    @property
    def name(self) -> str:
        return f"KAMA_Cross({self._kama_name}/{self._ema_name})"

    def evaluate(self, symbol: str, timeframe: str, indicators: dict[str, Any]) -> Signal | None:
        """
        Evaluate KAMA vs EMA crossover.
        評估 KAMA 對 EMA 的交叉。
        """
        kama_data = indicators.get(self._kama_name)
        ema_data = indicators.get(self._ema_name)
        if not kama_data or not ema_data:
            return None

        kama_val = kama_data.get("kama")
        ema_val = ema_data.get("ema")
        if kama_val is None or ema_val is None:
            return None
        if not math.isfinite(kama_val) or not math.isfinite(ema_val):
            return None

        # Calculate spread as percentage / 計算價差百分比
        if abs(ema_val) < 1e-12:
            return None
        spread_pct = (kama_val - ema_val) / ema_val * 100

        # Minimum spread to avoid noise / 最小價差避免噪音
        min_spread_pct = 0.03  # KAMA is smoother, lower threshold / KAMA 更平滑，用較低閾值

        # Efficiency ratio boosts confidence when trend is clean
        # 效率比在趨勢乾淨時提升信心
        er = kama_data.get("efficiency_ratio", 0.5)

        if spread_pct > min_spread_pct:
            # KAMA above EMA → adaptive bullish / KAMA 在 EMA 上方 → 自適應看多
            confidence = min(1.0, spread_pct / 0.8 * 0.4 + 0.2 + er * 0.2)
            return Signal(
                symbol=symbol,
                direction=DIRECTION_LONG,
                confidence=confidence,
                edge_bps=max(5, spread_pct * 8),
                source=self.name,
                timeframe=timeframe,
                reasoning=(
                    f"KAMA={kama_val:.2f} > EMA={ema_val:.2f} "
                    f"(spread={spread_pct:.3f}%, ER={er:.2f}, bullish/看多)"
                ),
                metadata={"kama": kama_val, "ema": ema_val, "efficiency_ratio": er, "close": kama_val},
            )

        if spread_pct < -min_spread_pct:
            # KAMA below EMA → adaptive bearish / KAMA 在 EMA 下方 → 自適應看空
            confidence = min(1.0, abs(spread_pct) / 0.8 * 0.4 + 0.2 + er * 0.2)
            return Signal(
                symbol=symbol,
                direction=DIRECTION_SHORT,
                confidence=confidence,
                edge_bps=max(5, abs(spread_pct) * 8),
                source=self.name,
                timeframe=timeframe,
                reasoning=(
                    f"KAMA={kama_val:.2f} < EMA={ema_val:.2f} "
                    f"(spread={spread_pct:.3f}%, ER={er:.2f}, bearish/看空)"
                ),
                metadata={"kama": kama_val, "ema": ema_val, "efficiency_ratio": er, "close": kama_val},
            )

        return None


class BollingerBandReversionRule(SignalRule):
    """
    Bollinger Band mean reversion signal.
    布林带均值回归信号。

    Logic:
    - Price below lower band (%B < 0) → long (expect reversion to mean / 预期回归均值)
    - Price above upper band (%B > 1) → short (expect reversion)
    - Enhanced with RSI confirmation: only trigger if RSI agrees (RSI 确认)

    This is the core signal for the Bollinger Mean Reversion strategy.
    这是 Bollinger 均值回归策略的核心信号。
    """

    def __init__(
        self,
        bb_name: str = "BB(20,2.0)",
        rsi_name: str = "RSI(14)",
        bb_lower_threshold: float = 0.1,    # %B below this → oversold / %B 低于此值 → 超卖
        bb_upper_threshold: float = 0.9,    # %B above this → overbought / %B 高于此值 → 超买
        rsi_confirm: bool = True,           # Use RSI for confirmation / 用 RSI 确认
    ) -> None:
        self._bb_name = bb_name
        self._rsi_name = rsi_name
        self._lower = bb_lower_threshold
        self._upper = bb_upper_threshold
        self._rsi_confirm = rsi_confirm

    @property
    def name(self) -> str:
        return f"BB_Reversion({self._lower}/{self._upper})"

    def evaluate(self, symbol: str, timeframe: str, indicators: dict[str, Any]) -> Signal | None:
        bb_data = indicators.get(self._bb_name)
        if not bb_data or "percent_b" not in bb_data:
            return None

        pct_b = bb_data["percent_b"]
        if not isinstance(pct_b, (int, float)) or not math.isfinite(pct_b):
            return None
        bandwidth = bb_data.get("bandwidth")
        if bandwidth is None or not math.isfinite(bandwidth):
            return None

        # Skip if bandwidth too narrow (squeeze — don't trade reversion during squeeze)
        # 跳过带宽过窄的情况（布林带收窄 — 收窄期间不做均值回归）
        if bandwidth < 0.01:
            return None

        # Check RSI confirmation / 检查 RSI 确认
        rsi_val = None
        if self._rsi_confirm:
            rsi_data = indicators.get(self._rsi_name)
            if rsi_data and "rsi" in rsi_data:
                rsi_val = rsi_data["rsi"]

        if pct_b < self._lower:
            # Below lower band → long (mean reversion) / 低于下轨 → 做多（均值回归）
            # RSI confirmation: only if RSI also suggests oversold (< 40)
            if self._rsi_confirm and rsi_val is not None and rsi_val > 40:
                return None  # RSI doesn't confirm / RSI 不确认

            confidence = min(1.0, (self._lower - pct_b) * 2 + 0.3)
            if rsi_val is not None:
                confidence = min(1.0, confidence + 0.1)  # RSI bonus / RSI 加成
            return Signal(
                symbol=symbol,
                direction=DIRECTION_LONG,
                confidence=confidence,
                edge_bps=max(15, (self._lower - pct_b) * 100),
                source=self.name,
                timeframe=timeframe,
                reasoning=(
                    f"%B={pct_b:.3f} < {self._lower} (below lower band/低于下轨), "
                    f"BW={bandwidth:.4f}"
                    + (f", RSI={rsi_val:.1f}" if rsi_val else "")
                    + " → mean reversion long/均值回归做多"
                ),
                # Attach V2 indicator data for strategies / 为策略附加 V2 指标数据
                # A1: Include Donchian high/low for BB_Breakout Donchian confirmation
                # A1：含 Donchian 高/低值，供 BB_Breakout Donchian 确认
                # A2: Include close price for downstream strategy use
                # A2：含收盘价，供下游策略使用
                metadata=self._build_bb_metadata(pct_b, bandwidth, rsi_val, indicators),
            )

        if pct_b > self._upper:
            # Above upper band → short (mean reversion) / 高于上轨 → 做空（均值回归）
            if self._rsi_confirm and rsi_val is not None and rsi_val < 60:
                return None

            confidence = min(1.0, (pct_b - self._upper) * 2 + 0.3)
            if rsi_val is not None:
                confidence = min(1.0, confidence + 0.1)
            return Signal(
                symbol=symbol,
                direction=DIRECTION_SHORT,
                confidence=confidence,
                edge_bps=max(15, (pct_b - self._upper) * 100),
                source=self.name,
                timeframe=timeframe,
                reasoning=(
                    f"%B={pct_b:.3f} > {self._upper} (above upper band/高于上轨), "
                    f"BW={bandwidth:.4f}"
                    + (f", RSI={rsi_val:.1f}" if rsi_val else "")
                    + " → mean reversion short/均值回归做空"
                ),
                # Attach V2 indicator data for strategies / 为策略附加 V2 指标数据
                metadata=self._build_bb_metadata(pct_b, bandwidth, rsi_val, indicators),
            )

        return None

    def _build_bb_metadata(
        self,
        pct_b: float,
        bandwidth: float,
        rsi_val: float | None,
        indicators: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build enriched metadata dict for BB signals.
        构建 BB 信号的丰富 metadata 字典。

        A1: Donchian high/low from Donchian(20) indicator.
        A1：从 Donchian(20) 指标获取 Donchian 高/低值。
        A2: Close price from BB middle band as proxy.
        A2：用 BB 中轨作为收盘价代理。
        """
        meta: dict[str, Any] = {"percent_b": pct_b, "bandwidth": bandwidth}
        if rsi_val is not None:
            meta["rsi"] = rsi_val

        # A1: Donchian channel data for BB_Breakout confirmation
        # A1：Donchian 通道数据供 BB_Breakout 确认
        donchian_data = indicators.get("Donchian(20)")
        if isinstance(donchian_data, dict):
            if "upper" in donchian_data:
                meta["donchian_high"] = donchian_data["upper"]
            if "lower" in donchian_data:
                meta["donchian_low"] = donchian_data["lower"]

        # A2: Close price — use BB middle band as proxy (closest available)
        # A2：收盘价 — 用 BB 中轨作为代理（最接近的可用值）
        bb_data = indicators.get(self._bb_name)
        if isinstance(bb_data, dict) and "middle" in bb_data:
            meta["close"] = bb_data["middle"]

        # Volume ratio for breakout filtering / 成交量比率供突破过滤
        vol_data = indicators.get("VolumeRatio(20)")
        if isinstance(vol_data, dict) and "volume_ratio" in vol_data:
            meta["volume_ratio"] = vol_data["volume_ratio"]

        return meta


class MACDCrossoverRule(SignalRule):
    """
    MACD histogram crossover signal.
    MACD 柱状图交叉信号。

    Logic:
    - MACD > 0 and histogram > 0 → long (uptrend with momentum / 上升趋势+动量)
    - MACD < 0 and histogram < 0 → short (downtrend with momentum / 下降趋势+动量)

    Combines trend (MACD line) with momentum (histogram).
    结合趋势（MACD 线）和动量（柱状图）。
    """

    def __init__(self, macd_name: str = "MACD(12,26,9)") -> None:
        self._macd_name = macd_name

    @property
    def name(self) -> str:
        return f"MACD_Cross({self._macd_name})"

    def evaluate(self, symbol: str, timeframe: str, indicators: dict[str, Any]) -> Signal | None:
        macd_data = indicators.get(self._macd_name)
        if not macd_data:
            return None

        macd_val = macd_data.get("macd")
        histogram = macd_data.get("histogram")
        if macd_val is None or histogram is None:
            return None
        if not math.isfinite(macd_val) or not math.isfinite(histogram):
            return None

        if macd_val == 0 and histogram == 0:
            return None

        # Attach V2 metadata for downstream strategies / 为下游策略附加 V2 元数据
        adx_val = indicators.get("ADX(14)", {}).get("adx")
        volume_ratio_val = indicators.get("VolumeRatio(20)", {}).get("volume_ratio")

        # Need both MACD and histogram to agree / 需要 MACD 和柱状图方向一致
        if macd_val > 0 and histogram > 0:
            confidence = min(1.0, abs(histogram) / (abs(macd_val) + abs(histogram) + 1e-10) * 0.5 + 0.2)
            meta: dict[str, Any] = {}
            if adx_val is not None:
                meta["adx"] = adx_val
            if volume_ratio_val is not None:
                meta["volume_ratio"] = volume_ratio_val
            return Signal(
                symbol=symbol,
                direction=DIRECTION_LONG,
                confidence=confidence,
                edge_bps=max(5, abs(histogram) * 0.1),
                source=self.name,
                timeframe=timeframe,
                reasoning=(
                    f"MACD={macd_val:.2f}>0, hist={histogram:.2f}>0 "
                    "(bullish trend+momentum / 看多趋势+动量)"
                ),
                metadata=meta,
            )

        if macd_val < 0 and histogram < 0:
            confidence = min(1.0, abs(histogram) / (abs(macd_val) + abs(histogram) + 1e-10) * 0.5 + 0.2)
            meta = {}
            if adx_val is not None:
                meta["adx"] = adx_val
            if volume_ratio_val is not None:
                meta["volume_ratio"] = volume_ratio_val
            return Signal(
                symbol=symbol,
                direction=DIRECTION_SHORT,
                confidence=confidence,
                edge_bps=max(5, abs(histogram) * 0.1),
                source=self.name,
                timeframe=timeframe,
                reasoning=(
                    f"MACD={macd_val:.2f}<0, hist={histogram:.2f}<0 "
                    "(bearish trend+momentum / 看空趋势+动量)"
                ),
                metadata=meta,
            )

        return None


class RegimeDetectorRule(SignalRule):
    """
    Market regime detection — trending vs ranging.
    市场 regime 检测 — 趋势 vs 震荡。

    Uses ATR-normalized range and BB bandwidth to classify:
    - trending: strong directional move, BB expanding
    - ranging: sideways, BB contracting or stable
    - volatile: high ATR but no direction (choppy)

    Emits a neutral signal with regime info in metadata.
    Output is used by orchestrator to weight other signals.
    输出用于编排器加权其他信号。

    Note: This rule emits "neutral" direction with regime info in metadata,
    so it does not directly trigger trades. It provides context for other rules.
    本规则发出"中性"方向 + 元数据中的 regime 信息，不直接触发交易。
    """

    def __init__(
        self,
        atr_name: str = "ATR(14)",
        bb_name: str = "BB(20,2.0)",
        ema_fast_name: str = "EMA(12)",
        ema_slow_name: str = "EMA(26)",
        trend_spread_threshold: float = 0.3,  # MA spread % to consider trending
        bb_squeeze_threshold: float = 0.02,    # BB bandwidth below this = squeeze
    ) -> None:
        self._atr_name = atr_name
        self._bb_name = bb_name
        self._ema_fast = ema_fast_name
        self._ema_slow = ema_slow_name
        self._trend_threshold = trend_spread_threshold
        self._squeeze_threshold = bb_squeeze_threshold

    @property
    def name(self) -> str:
        return "Regime_Detector"

    def evaluate(self, symbol: str, timeframe: str, indicators: dict[str, Any]) -> Signal | None:
        bb_data = indicators.get(self._bb_name)
        atr_data = indicators.get(self._atr_name)
        fast_data = indicators.get(self._ema_fast)
        slow_data = indicators.get(self._ema_slow)

        if not bb_data or not atr_data:
            return None

        bandwidth = bb_data.get("bandwidth")
        atr_pct = atr_data.get("atr_percent")
        if bandwidth is None or atr_pct is None:
            return None
        if not math.isfinite(bandwidth) or not math.isfinite(atr_pct):
            return None

        # Determine MA spread for trend direction
        ma_spread_pct = 0.0
        trend_direction = "none"
        if fast_data and slow_data:
            fast_val = fast_data.get("ema")
            slow_val = slow_data.get("ema")
            if fast_val is not None and slow_val is not None and slow_val != 0:
                if math.isfinite(fast_val) and math.isfinite(slow_val):
                    ma_spread_pct = (fast_val - slow_val) / slow_val * 100
                    if ma_spread_pct > self._trend_threshold:
                        trend_direction = "up"
                    elif ma_spread_pct < -self._trend_threshold:
                        trend_direction = "down"

        # Classify regime
        if bandwidth < self._squeeze_threshold:
            regime = "squeeze"       # BB contracting — breakout imminent
        elif abs(ma_spread_pct) > self._trend_threshold and bandwidth > 0.03:
            regime = "trending"      # Strong trend + expanding bands
        elif atr_pct > 3.0 and abs(ma_spread_pct) < self._trend_threshold:
            regime = "volatile"      # High ATR but no trend = choppy
        else:
            regime = "ranging"       # Default: sideways

        # Regime confidence
        if regime == "trending":
            confidence = min(1.0, abs(ma_spread_pct) / 1.0 * 0.3 + 0.4)
        elif regime == "squeeze":
            confidence = min(1.0, (self._squeeze_threshold - bandwidth) / self._squeeze_threshold * 0.5 + 0.3)
        elif regime == "volatile":
            confidence = min(1.0, atr_pct / 5.0 * 0.3 + 0.3)
        else:
            confidence = 0.5

        # Attach V2 metadata: ADX for trend strength / 附加 V2 元数据：ADX 趋势强度
        adx_val = indicators.get("ADX(14)", {}).get("adx")
        regime_meta: dict[str, Any] = {
            "regime": regime,
            "trend_direction": trend_direction,
            "ma_spread_pct": round(ma_spread_pct, 4),
            "bandwidth": round(bandwidth, 6),
            "atr_percent": round(atr_pct, 4),
        }
        if adx_val is not None:
            regime_meta["adx"] = adx_val

        return Signal(
            symbol=symbol,
            direction=DIRECTION_NEUTRAL,
            confidence=confidence,
            source=self.name,
            timeframe=timeframe,
            reasoning=f"Regime={regime}, MA_spread={ma_spread_pct:.2f}%, BW={bandwidth:.4f}, ATR%={atr_pct:.2f}%",
            metadata=regime_meta,
        )


class RSIExitRule(SignalRule):
    """
    RSI exit signal — close positions when RSI reverts from extreme.
    RSI 出场信号 — RSI 从极端值回归时平仓。

    Logic:
    - RSI crosses back below 70 from overbought → close_long
    - RSI crosses back above 30 from oversold → close_short
    """

    def __init__(
        self,
        rsi_name: str = "RSI(14)",
        exit_overbought: float = 65.0,   # Exit long when RSI drops below this
        exit_oversold: float = 35.0,      # Exit short when RSI rises above this
    ) -> None:
        self._rsi_name = rsi_name
        self._exit_ob = exit_overbought
        self._exit_os = exit_oversold

    @property
    def name(self) -> str:
        return "RSI_Exit"

    def evaluate(self, symbol: str, timeframe: str, indicators: dict[str, Any]) -> Signal | None:
        rsi_data = indicators.get(self._rsi_name)
        if not rsi_data or "rsi" not in rsi_data:
            return None
        rsi = rsi_data["rsi"]
        if not isinstance(rsi, (int, float)) or not math.isfinite(rsi):
            return None

        # RSI dropping from overbought → close long
        if 50 < rsi < self._exit_ob:
            return Signal(
                symbol=symbol,
                direction=DIRECTION_CLOSE_LONG,
                confidence=0.6,
                source=self.name,
                timeframe=timeframe,
                reasoning=f"RSI={rsi:.1f} dropped below {self._exit_ob} (exit overbought/退出超买)",
                # V2 metadata: attach RSI for downstream strategy use / 附加 RSI 供下游策略使用
                metadata={"rsi": rsi},
            )

        # RSI rising from oversold → close short
        if rsi > self._exit_os and rsi < 50:
            return Signal(
                symbol=symbol,
                direction=DIRECTION_CLOSE_SHORT,
                confidence=0.6,
                source=self.name,
                timeframe=timeframe,
                reasoning=f"RSI={rsi:.1f} rose above {self._exit_os} (exit oversold/退出超卖)",
                # V2 metadata: attach RSI for downstream strategy use / 附加 RSI 供下游策略使用
                metadata={"rsi": rsi},
            )

        return None


class MACDExhaustionRule(SignalRule):
    """
    MACD momentum exhaustion exit signal.
    MACD 动量衰竭出场信号。

    Logic:
    - MACD histogram shrinking toward zero from positive → momentum fading → close_long
    - MACD histogram shrinking toward zero from negative → momentum fading → close_short
    """

    def __init__(self, macd_name: str = "MACD(12,26,9)") -> None:
        self._macd_name = macd_name
        self._prev_histogram: dict[str, float] = {}  # symbol → previous histogram

    @property
    def name(self) -> str:
        return "MACD_Exhaustion"

    def evaluate(self, symbol: str, timeframe: str, indicators: dict[str, Any]) -> Signal | None:
        macd_data = indicators.get(self._macd_name)
        if not macd_data:
            return None

        histogram = macd_data.get("histogram")
        macd_val = macd_data.get("macd")
        if histogram is None or macd_val is None:
            return None
        if not math.isfinite(histogram) or not math.isfinite(macd_val):
            return None

        key = f"{symbol}:{timeframe}"
        prev_hist = self._prev_histogram.get(key)
        self._prev_histogram[key] = histogram

        # Limit history size to prevent unbounded growth / 限制历史大小防止无限增长
        if len(self._prev_histogram) > 200:
            # Keep only recent half / 只保留最近一半
            keys = list(self._prev_histogram.keys())
            for k in keys[:100]:
                del self._prev_histogram[k]

        if prev_hist is None:
            return None

        # Attach V2 metadata for downstream strategies / 为下游策略附加 V2 元数据
        adx_val = indicators.get("ADX(14)", {}).get("adx")
        volume_ratio_val = indicators.get("VolumeRatio(20)", {}).get("volume_ratio")

        # Histogram was positive and shrinking → momentum fading → close_long
        if prev_hist > 0 and histogram > 0 and histogram < prev_hist * 0.6:
            meta: dict[str, Any] = {}
            if adx_val is not None:
                meta["adx"] = adx_val
            if volume_ratio_val is not None:
                meta["volume_ratio"] = volume_ratio_val
            return Signal(
                symbol=symbol,
                direction=DIRECTION_CLOSE_LONG,
                confidence=min(1.0, (prev_hist - histogram) / (abs(prev_hist) + 1e-10) * 0.5 + 0.2),
                source=self.name,
                timeframe=timeframe,
                reasoning=f"MACD hist fading: {prev_hist:.2f}→{histogram:.2f} (momentum exhaustion/动量衰竭)",
                metadata=meta,
            )

        # Histogram was negative and shrinking (toward zero) → close_short
        if prev_hist < 0 and histogram < 0 and histogram > prev_hist * 0.6:
            meta = {}
            if adx_val is not None:
                meta["adx"] = adx_val
            if volume_ratio_val is not None:
                meta["volume_ratio"] = volume_ratio_val
            return Signal(
                symbol=symbol,
                direction=DIRECTION_CLOSE_SHORT,
                confidence=min(1.0, (histogram - prev_hist) / (abs(prev_hist) + 1e-10) * 0.5 + 0.2),
                source=self.name,
                timeframe=timeframe,
                reasoning=f"MACD hist recovering: {prev_hist:.2f}→{histogram:.2f} (momentum exhaustion/动量衰竭)",
                metadata=meta,
            )

        return None


class RSIDivergenceRule(SignalRule):
    """
    RSI Divergence detection signal.
    RSI 背离检测信号。

    Logic:
    - Bearish divergence: price makes higher high but RSI makes lower high → close_long / short
    - Bullish divergence: price makes lower low but RSI makes higher low → close_short / long

    Tracks recent price and RSI peaks/troughs to detect divergence.
    追踪近期价格和 RSI 的高低点以检测背离。
    """

    def __init__(
        self,
        rsi_name: str = "RSI(14)",
        lookback: int = 5,  # Number of recent evaluations to compare
    ) -> None:
        self._rsi_name = rsi_name
        self._lookback = lookback
        # Track recent price and RSI values per symbol:timeframe
        self._history: dict[str, list[tuple[float, float]]] = {}  # key → [(price, rsi), ...]
        self._max_history = 20

    @property
    def name(self) -> str:
        return "RSI_Divergence"

    def evaluate(self, symbol: str, timeframe: str, indicators: dict[str, Any]) -> Signal | None:
        rsi_data = indicators.get(self._rsi_name)
        if not rsi_data or "rsi" not in rsi_data:
            return None
        rsi = rsi_data["rsi"]
        if not isinstance(rsi, (int, float)) or not math.isfinite(rsi):
            return None

        # Need a price reference — get from EMA or BB middle
        price = None
        for ind_name, ind_data in indicators.items():
            if ind_data and "ema" in ind_data:
                price = ind_data["ema"]
                break
            if ind_data and "middle" in ind_data:
                price = ind_data["middle"]
                break
        if price is None or not math.isfinite(price):
            return None

        key = f"{symbol}:{timeframe}"
        history = self._history.setdefault(key, [])
        history.append((price, rsi))
        if len(history) > self._max_history:
            history[:] = history[-self._max_history:]

        # Limit total keys to prevent unbounded growth / 限制总键数防止无限增长
        if len(self._history) > 200:
            keys = list(self._history.keys())
            for k in keys[:100]:
                del self._history[k]

        if len(history) < self._lookback + 1:
            return None

        recent = history[-self._lookback:]
        older = history[-(self._lookback + 1)]

        # Find highest price and corresponding RSI in recent window
        max_price_entry = max(recent, key=lambda x: x[0])
        min_price_entry = min(recent, key=lambda x: x[0])

        # Bearish divergence: recent price higher than older, but RSI lower
        if max_price_entry[0] > older[0] and max_price_entry[1] < older[1] - 3:
            # Price making higher high, RSI making lower high
            if rsi > 55:  # Only in overbought-ish zone
                return Signal(
                    symbol=symbol,
                    direction=DIRECTION_CLOSE_LONG,
                    confidence=min(1.0, (older[1] - max_price_entry[1]) / 20 + 0.3),
                    source=self.name,
                    timeframe=timeframe,
                    reasoning=(
                        f"Bearish divergence: price high={max_price_entry[0]:.2f} > prev={older[0]:.2f} "
                        f"but RSI={max_price_entry[1]:.1f} < prev_RSI={older[1]:.1f}"
                    ),
                    # V2 metadata: attach RSI for downstream use / 附加 RSI 供下游使用
                    metadata={"rsi": rsi},
                )

        # Bullish divergence: recent price lower than older, but RSI higher
        if min_price_entry[0] < older[0] and min_price_entry[1] > older[1] + 3:
            if rsi < 45:  # Only in oversold-ish zone
                return Signal(
                    symbol=symbol,
                    direction=DIRECTION_CLOSE_SHORT,
                    confidence=min(1.0, (min_price_entry[1] - older[1]) / 20 + 0.3),
                    source=self.name,
                    timeframe=timeframe,
                    reasoning=(
                        f"Bullish divergence: price low={min_price_entry[0]:.2f} < prev={older[0]:.2f} "
                        f"but RSI={min_price_entry[1]:.1f} > prev_RSI={older[1]:.1f}"
                    ),
                    # V2 metadata: attach RSI for downstream use / 附加 RSI 供下游使用
                    metadata={"rsi": rsi},
                )

        return None


def create_default_signal_rules() -> list[SignalRule]:
    """
    Create the default set of signal rules / 创建默认信号规则集

    Returns a balanced set of rules covering trend-following, mean-reversion,
    regime detection, and exit signals.
    返回一组平衡的规则，涵盖趋势跟踪、均值回归、regime 检测和退出信号。
    """
    return [
        # Entry rules / 入场规则
        RSIOverboughtOversoldRule(),
        MACrossoverRule(),
        KAMACrossoverRule(),        # B1: KAMA adaptive crossover / KAMA 自適應交叉
        BollingerBandReversionRule(),
        MACDCrossoverRule(),
        # Exit rules / 出场规则
        RSIExitRule(),
        MACDExhaustionRule(),
        RSIDivergenceRule(),
        # Regime detection / Regime 检测
        RegimeDetectorRule(),
    ]


# =============================================================================
# Signal Callback Type / 信号回调类型
# =============================================================================

# callback(signal)
SignalCallback = Callable[[Signal], None]


# =============================================================================
# SignalEngine — Unified Signal Evaluation / 统一信号评估引擎
# =============================================================================

class SignalEngine:
    """
    Manages signal rules, evaluates them on indicator updates, records history.
    管理信号规则，在指标更新时评估，记录历史。

    Integrates with IndicatorEngine: register as on_update callback.
    与 IndicatorEngine 集成：注册为 on_update 回调。

    Usage:
      se = SignalEngine()
      indicator_engine.register_on_update(se.on_indicators_update)
      se.register_on_signal(my_strategy.on_signal)
    """

    def __init__(
        self,
        rules: list[SignalRule] | None = None,
        history_capacity: int = SIGNAL_HISTORY_CAPACITY,
    ) -> None:
        self._rules = list(rules or create_default_signal_rules())
        self._lock = threading.Lock()

        # Signal history (newest last) / 信号历史（最新的在最后）
        self._history: deque[Signal] = deque(maxlen=history_capacity)

        # Latest signal per (symbol, source) / 每个 (交易对, 来源) 的最新信号
        # Bounded to prevent unbounded growth for delisted symbols / 有上限防止已下架交易对的无限增长
        self._latest: dict[tuple[str, str], Signal] = {}
        self._latest_max_size = 500

        # Downstream callbacks / 下游回调
        self._on_signal_callbacks: list[SignalCallback] = []

        # Statistics / 统计
        self._stats = {
            "total_evaluations": 0,
            "signals_generated": 0,
            "rule_errors": 0,
            "signals_by_direction": {d: 0 for d in ALL_DIRECTIONS},
            "signals_by_source": {},
        }

    # ── Registration / 注册 ──

    def register_rule(self, rule: SignalRule) -> None:
        """Register a new signal rule / 注册新信号规则"""
        with self._lock:
            self._rules.append(rule)
        logger.info("Registered signal rule / 注册信号规则: %s", rule.name)

    def register_on_signal(self, callback: SignalCallback) -> None:
        """
        Register a callback for new signals / 注册新信号回调

        Called whenever an actionable signal is generated.
        每当生成可执行信号时调用。
        """
        with self._lock:
            self._on_signal_callbacks.append(callback)

    # ── Core: Indicator Update Handler / 核心：指标更新处理 ──

    def on_indicators_update(
        self,
        symbol: str,
        timeframe: str,
        indicators: dict[str, Any],
    ) -> list[Signal]:
        """
        Evaluate all rules against updated indicators.
        使用更新的指标评估所有规则。

        This is designed to be registered as IndicatorEngine.register_on_update callback.
        设计为注册为 IndicatorEngine.register_on_update 的回调。

        Args:
          symbol     — trading pair / 交易对
          timeframe  — timeframe / 时间框架
          indicators — {indicator_name: result_dict} / 指标结果字典

        Returns:
          List of signals generated (may be empty) / 生成的信号列表（可能为空）
        """
        generated: list[Signal] = []

        with self._lock:
            rules = list(self._rules)

        for rule in rules:
            try:
                signal = rule.evaluate(symbol, timeframe, indicators)
                # Allow Regime_Detector neutral signals through for dispatch
                # 允许 Regime_Detector 的中性信号通过以便分发
                if signal is not None and (signal.is_actionable or signal.source == "Regime_Detector"):
                    generated.append(signal)
                    with self._lock:
                        self._history.append(signal)
                        self._latest[(symbol, rule.name)] = signal
                        # Evict oldest entries if _latest exceeds max size
                        # 超过上限时淘汰最旧条目
                        if len(self._latest) > self._latest_max_size:
                            oldest_key = next(iter(self._latest))
                            del self._latest[oldest_key]
                        self._stats["signals_generated"] += 1
                        self._stats["signals_by_direction"][signal.direction] = (
                            self._stats["signals_by_direction"].get(signal.direction, 0) + 1
                        )
                        self._stats["signals_by_source"][rule.name] = (
                            self._stats["signals_by_source"].get(rule.name, 0) + 1
                        )
            except Exception:
                logger.exception(
                    "Signal rule evaluation error / 信号规则评估异常: %s",
                    rule.name,
                )
                with self._lock:
                    self._stats["rule_errors"] += 1

        with self._lock:
            self._stats["total_evaluations"] += 1

        # Notify downstream (snapshot callbacks under lock) / 通知下游（在锁内快照回调列表）
        with self._lock:
            callbacks = list(self._on_signal_callbacks)
        for signal in generated:
            for cb in callbacks:
                try:
                    cb(signal)
                except Exception:
                    logger.exception("Signal callback error / 信号回调异常")

        return generated

    # ── Query Interface / 查询接口 ──

    def get_latest_signals(self, symbol: str | None = None, n: int = 20) -> list[dict[str, Any]]:
        """
        Get latest N signals (optionally filtered by symbol).
        获取最近 N 个信号（可选按交易对过滤）。
        """
        with self._lock:
            if symbol:
                filtered = [s for s in self._history if s.symbol == symbol]
            else:
                filtered = list(self._history)
            recent = filtered[-n:] if n < len(filtered) else filtered
            return [s.to_dict() for s in recent]

    def get_latest_for_symbol(self, symbol: str) -> dict[str, dict[str, Any]]:
        """
        Get the latest signal from each rule for a specific symbol.
        获取指定交易对每个规则的最新信号。

        Returns:
          {rule_name: signal_dict} / {规则名称: 信号字典}
        """
        with self._lock:
            result = {}
            for (sym, source), signal in self._latest.items():
                if sym == symbol:
                    result[source] = signal.to_dict()
            return result

    def get_signal_summary(self, symbol: str) -> dict[str, Any]:
        """
        Get a weighted consensus summary for a symbol.
        获取加权共识摘要。

        Weights signals by confidence, freshness, and regime context.
        按置信度、新鲜度和 regime 上下文加权。
        """
        now_ms = int(time.time() * 1000)
        FRESHNESS_DECAY_MS = 300_000  # 5 minutes full weight, then decay / 5 分钟内全权重

        with self._lock:
            signals = [
                s for (sym, _), s in self._latest.items()
                if sym == symbol and s.is_actionable
            ]
            # Also get regime info if available
            regime_signal = None
            for (sym, src), s in self._latest.items():
                if sym == symbol and s.source == "Regime_Detector":
                    regime_signal = s
                    break

        # Determine regime for weighting
        regime = "unknown"
        if regime_signal and regime_signal.metadata:
            regime = regime_signal.metadata.get("regime", "unknown")

        # Regime-based rule weight multipliers
        # 趋势市场：MA/MACD 权重高，RSI/BB 权重低
        # 震荡市场：RSI/BB 权重高，MA/MACD 权重低
        REGIME_WEIGHTS = {
            "trending": {"MA_Cross": 1.5, "MACD_Cross": 1.3, "RSI_OB_OS": 0.5, "BB_Reversion": 0.5},
            "ranging":  {"MA_Cross": 0.5, "MACD_Cross": 0.5, "RSI_OB_OS": 1.5, "BB_Reversion": 1.5},
            "squeeze":  {"MA_Cross": 0.3, "MACD_Cross": 0.3, "RSI_OB_OS": 0.3, "BB_Reversion": 0.3},
            "volatile": {"MA_Cross": 0.7, "MACD_Cross": 0.7, "RSI_OB_OS": 0.7, "BB_Reversion": 0.7},
        }
        regime_mults = REGIME_WEIGHTS.get(regime, {})

        long_score = 0.0
        short_score = 0.0

        for s in signals:
            # Base weight = confidence
            weight = s.confidence

            # Freshness decay: signals older than 5 min lose weight linearly
            age_ms = now_ms - s.ts_ms
            if age_ms > FRESHNESS_DECAY_MS:
                freshness = max(0.1, 1.0 - (age_ms - FRESHNESS_DECAY_MS) / FRESHNESS_DECAY_MS)
                weight *= freshness

            # Regime multiplier: match source prefix to regime weights
            for prefix, mult in regime_mults.items():
                if prefix in s.source:
                    weight *= mult
                    break

            if s.direction == DIRECTION_LONG:
                long_score += weight
            elif s.direction == DIRECTION_SHORT:
                short_score += weight

        total_score = long_score + short_score
        if total_score > 0:
            if long_score > short_score * 1.2:  # Need 20% margin for conviction
                consensus = DIRECTION_LONG
            elif short_score > long_score * 1.2:
                consensus = DIRECTION_SHORT
            else:
                consensus = DIRECTION_NEUTRAL  # Insufficient conviction / 信念不足
        else:
            consensus = DIRECTION_NEUTRAL

        return {
            "symbol": symbol,
            "long_score": round(long_score, 4),
            "short_score": round(short_score, 4),
            "long_count": sum(1 for s in signals if s.direction == DIRECTION_LONG),
            "short_count": sum(1 for s in signals if s.direction == DIRECTION_SHORT),
            "total_signals": len(signals),
            "avg_confidence": round(sum(s.confidence for s in signals) / len(signals), 4) if signals else 0.0,
            "consensus_direction": consensus,
            "regime": regime,
            "signals": [s.to_dict() for s in signals],
        }

    def get_stats(self) -> dict[str, Any]:
        """Get signal engine statistics / 获取信号引擎统计"""
        with self._lock:
            return {
                "component": "signal_engine",
                "rules_registered": [r.name for r in self._rules],
                "rule_count": len(self._rules),
                "history_size": len(self._history),
                "stats": {
                    k: (dict(v) if isinstance(v, dict) else v)
                    for k, v in self._stats.items()
                },
            }

    def clear_history(self) -> None:
        """Clear signal history / 清空信号历史"""
        with self._lock:
            self._history.clear()
            self._latest.clear()
