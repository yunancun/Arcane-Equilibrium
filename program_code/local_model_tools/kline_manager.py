"""
STUB: Kline Manager / K线管理器 stub.

MODULE_NOTE (EN): Kline aggregation lives in
  `rust/openclaw_engine/src/market_data_client/`. This Python module is
  retained so `strategy_wiring.py` can still instantiate KLINE_MANAGER and
  so `strategy_read_routes.py` has a harmless fallback. All getters return
  empty data.
MODULE_NOTE (中): K线聚合由 Rust `openclaw_engine::market_data_client`
  承担。Python 模块仅保留用于 wiring 实例化和降级备援，所有 getter 返回空。
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

TIMEFRAME_DURATIONS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}
DEFAULT_TIMEFRAMES: list[str] = ["1m", "5m", "15m", "1h", "4h"]
DEFAULT_BUFFER_CAPACITY: int = 500


class KlineBar:
    __slots__ = (
        "open_time_ms",
        "close_time_ms",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "turnover",
        "tick_count",
        "is_closed",
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
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += volume
        self.turnover += turnover
        self.tick_count += 1

    def to_dict(self) -> dict[str, Any]:
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
        return f"<KlineBar stub open={self.open} close={self.close}>"


KlineCloseCallback = Callable[[str, str, KlineBar], None]


class KlineBuffer:
    def __init__(self, capacity: int = DEFAULT_BUFFER_CAPACITY) -> None:
        self._capacity = capacity

    @property
    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        return 0

    def append(self, bar: KlineBar) -> None:
        return None

    def latest(self, n: int = 1) -> list[KlineBar]:
        return []

    def close_array(self, n: int | None = None) -> list[float]:
        return []

    def high_array(self, n: int | None = None) -> list[float]:
        return []

    def low_array(self, n: int | None = None) -> list[float]:
        return []

    def open_array(self, n: int | None = None) -> list[float]:
        return []

    def volume_array(self, n: int | None = None) -> list[float]:
        return []

    def ohlcv_arrays(self, n: int | None = None) -> dict[str, list[float]]:
        return {"open": [], "high": [], "low": [], "close": [], "volume": []}

    def clear(self) -> None:
        return None

    def to_list(self) -> list[dict[str, Any]]:
        return []


class KlineManager:
    def __init__(
        self,
        symbols: list[str] | None = None,
        timeframes: list[str] | None = None,
        buffer_capacity: int = DEFAULT_BUFFER_CAPACITY,
    ) -> None:
        self._symbols: list[str] = list(symbols or [])
        self._timeframes: list[str] = list(timeframes or DEFAULT_TIMEFRAMES)
        self._buffer_capacity = buffer_capacity
        self._callbacks: list[KlineCloseCallback] = []

    def register_on_kline_close(self, callback: KlineCloseCallback) -> None:
        self._callbacks.append(callback)

    def on_price_event(self, event: Any) -> None:
        return None

    def on_tick(
        self,
        symbol: str,
        price: float,
        ts_ms: int | None = None,
        volume: float = 0.0,
        turnover: float = 0.0,
    ) -> None:
        return None

    def get_tracked_symbols(self) -> list[str]:
        return list(self._symbols)

    def get_timeframes(self) -> list[str]:
        return list(self._timeframes)

    def add_symbol(self, symbol: str) -> None:
        if symbol not in self._symbols:
            self._symbols.append(symbol)

    def remove_symbol(self, symbol: str) -> None:
        if symbol in self._symbols:
            self._symbols.remove(symbol)

    def get_buffer(self, symbol: str, timeframe: str) -> KlineBuffer | None:
        return None

    def get_current_bar(self, symbol: str, timeframe: str) -> KlineBar | None:
        return None

    def get_latest_klines(
        self, symbol: str, timeframe: str, n: int = 20
    ) -> list[dict[str, Any]]:
        return []

    def get_ohlcv(
        self, symbol: str, timeframe: str, n: int | None = None
    ) -> dict[str, list[float]]:
        return {"open": [], "high": [], "low": [], "close": [], "volume": []}

    def get_stats(self) -> dict[str, Any]:
        return {
            "stub": True,
            "source": "rust_engine_primary",
            "tracked_symbols": len(self._symbols),
            "timeframes": list(self._timeframes),
        }

    def get_status(self) -> dict[str, Any]:
        return self.get_stats()

    def clear_all(self) -> None:
        return None

    def bootstrap_from_rest(
        self, limit: int = 200, base_url: str = "https://api.bybit.com"
    ) -> dict[str, int]:
        return {}

    def get_staleness(self, max_age_ms: int = 120_000) -> dict[str, Any]:
        return {"stub": True, "stale_count": 0, "details": {}}


__all__ = [
    "TIMEFRAME_DURATIONS",
    "DEFAULT_TIMEFRAMES",
    "DEFAULT_BUFFER_CAPACITY",
    "KlineBar",
    "KlineBuffer",
    "KlineManager",
    "KlineCloseCallback",
]
