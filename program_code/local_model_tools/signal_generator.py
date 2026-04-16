"""
STUB: Signal Generator / 信号生成器 stub.

MODULE_NOTE (EN): Signal generation runs in Rust
  `openclaw_core::signals::{mod, rules}`. Python `Signal` / `SignalRule` /
  concrete rule classes are retained solely for legacy imports and type
  hints. Rule `evaluate()` always returns None; the Rust engine is
  authoritative.
MODULE_NOTE (中): 信号生成已迁移至 Rust `openclaw_core::signals`。
  Python 的 `Signal` / `SignalRule` / 具体规则类仅为兼容旧 import 与
  类型标注保留；`evaluate()` 恒返回 None，Rust 引擎为唯一真值源。
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

DIRECTION_LONG = "long"
DIRECTION_SHORT = "short"
DIRECTION_CLOSE_LONG = "close_long"
DIRECTION_CLOSE_SHORT = "close_short"
DIRECTION_NEUTRAL = "neutral"
ALL_DIRECTIONS = {
    DIRECTION_LONG,
    DIRECTION_SHORT,
    DIRECTION_CLOSE_LONG,
    DIRECTION_CLOSE_SHORT,
    DIRECTION_NEUTRAL,
}
SIGNAL_HISTORY_CAPACITY = 1000


class Signal:
    __slots__ = (
        "symbol",
        "direction",
        "confidence",
        "edge_bps",
        "source",
        "timeframe",
        "reasoning",
        "ts_ms",
        "metadata",
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
        self.symbol = symbol
        self.direction = direction
        self.confidence = confidence
        self.edge_bps = edge_bps
        self.source = source
        self.timeframe = timeframe
        self.reasoning = reasoning
        self.ts_ms = ts_ms if ts_ms is not None else int(time.time() * 1000)
        self.metadata = dict(metadata) if metadata else {}

    @property
    def is_actionable(self) -> bool:
        return self.direction in ALL_DIRECTIONS and self.direction != DIRECTION_NEUTRAL

    @property
    def is_entry(self) -> bool:
        return self.direction in (DIRECTION_LONG, DIRECTION_SHORT)

    @property
    def is_exit(self) -> bool:
        return self.direction in (DIRECTION_CLOSE_LONG, DIRECTION_CLOSE_SHORT)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "confidence": self.confidence,
            "edge_bps": self.edge_bps,
            "source": self.source,
            "timeframe": self.timeframe,
            "reasoning": self.reasoning,
            "ts_ms": self.ts_ms,
            "metadata": self.metadata,
        }


class SignalRule(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def evaluate(
        self, symbol: str, timeframe: str, indicators: dict[str, Any]
    ) -> Signal | None:
        ...


class _StubRule(SignalRule):
    _stub_name = "StubRule"

    @property
    def name(self) -> str:
        return self._stub_name

    def evaluate(
        self, symbol: str, timeframe: str, indicators: dict[str, Any]
    ) -> Signal | None:
        return None


class RSIOverboughtOversoldRule(_StubRule):
    _stub_name = "RSIOverboughtOversold"

    def __init__(
        self,
        rsi_indicator_name: str = "RSI(14)",
        oversold: float = 30.0,
        overbought: float = 70.0,
    ) -> None:
        self.rsi_indicator_name = rsi_indicator_name
        self.oversold = oversold
        self.overbought = overbought


class MACrossoverRule(_StubRule):
    _stub_name = "MACrossover"

    def __init__(self, fast_name: str = "EMA(12)", slow_name: str = "EMA(26)") -> None:
        self.fast_name = fast_name
        self.slow_name = slow_name


class KAMACrossoverRule(_StubRule):
    _stub_name = "KAMACrossover"

    def __init__(self, kama_name: str = "KAMA(10)", ema_name: str = "EMA(12)") -> None:
        self.kama_name = kama_name
        self.ema_name = ema_name


class BollingerBandReversionRule(_StubRule):
    _stub_name = "BollingerBandReversion"

    def __init__(
        self,
        bb_name: str = "BB(20,2.0)",
        rsi_name: str = "RSI(14)",
        bb_lower_threshold: float = 0.1,
        bb_upper_threshold: float = 0.9,
        rsi_confirm: bool = True,
    ) -> None:
        self.bb_name = bb_name
        self.rsi_name = rsi_name
        self.bb_lower_threshold = bb_lower_threshold
        self.bb_upper_threshold = bb_upper_threshold
        self.rsi_confirm = rsi_confirm

    def _build_bb_metadata(
        self,
        pct_b: float,
        bandwidth: float,
        rsi_val: float | None,
        indicators: dict[str, Any],
    ) -> dict[str, Any]:
        return {}


class MACDCrossoverRule(_StubRule):
    _stub_name = "MACDCrossover"

    def __init__(self, macd_name: str = "MACD(12,26,9)") -> None:
        self.macd_name = macd_name


class RegimeDetectorRule(_StubRule):
    _stub_name = "RegimeDetector"

    def __init__(
        self,
        atr_name: str = "ATR(14)",
        bb_name: str = "BB(20,2.0)",
        ema_fast_name: str = "EMA(12)",
        ema_slow_name: str = "EMA(26)",
        trend_spread_threshold: float = 0.3,
        bb_squeeze_threshold: float = 0.02,
    ) -> None:
        self.atr_name = atr_name
        self.bb_name = bb_name
        self.ema_fast_name = ema_fast_name
        self.ema_slow_name = ema_slow_name
        self.trend_spread_threshold = trend_spread_threshold
        self.bb_squeeze_threshold = bb_squeeze_threshold


class RSIExitRule(_StubRule):
    _stub_name = "RSIExit"

    def __init__(
        self,
        rsi_name: str = "RSI(14)",
        exit_overbought: float = 65.0,
        exit_oversold: float = 35.0,
    ) -> None:
        self.rsi_name = rsi_name
        self.exit_overbought = exit_overbought
        self.exit_oversold = exit_oversold


class MACDExhaustionRule(_StubRule):
    _stub_name = "MACDExhaustion"

    def __init__(self, macd_name: str = "MACD(12,26,9)") -> None:
        self.macd_name = macd_name


class RSIDivergenceRule(_StubRule):
    _stub_name = "RSIDivergence"

    def __init__(self, rsi_name: str = "RSI(14)", lookback: int = 5) -> None:
        self.rsi_name = rsi_name
        self.lookback = lookback


def create_default_signal_rules() -> list[SignalRule]:
    return [
        RSIOverboughtOversoldRule(),
        MACrossoverRule(),
        MACDCrossoverRule(),
    ]


# Back-compat re-export so legacy `from .signal_generator import SignalEngine` works.
from .signal_engine import SignalEngine  # noqa: E402

__all__ = [
    "DIRECTION_LONG",
    "DIRECTION_SHORT",
    "DIRECTION_CLOSE_LONG",
    "DIRECTION_CLOSE_SHORT",
    "DIRECTION_NEUTRAL",
    "ALL_DIRECTIONS",
    "SIGNAL_HISTORY_CAPACITY",
    "Signal",
    "SignalRule",
    "RSIOverboughtOversoldRule",
    "MACrossoverRule",
    "KAMACrossoverRule",
    "BollingerBandReversionRule",
    "MACDCrossoverRule",
    "RegimeDetectorRule",
    "RSIExitRule",
    "MACDExhaustionRule",
    "RSIDivergenceRule",
    "create_default_signal_rules",
    "SignalEngine",
]
