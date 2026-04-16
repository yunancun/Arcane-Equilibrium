"""
STUB: Market Scanner / 市场扫描器 stub.

MODULE_NOTE (EN): Symbol discovery is handled by
  `rust/openclaw_engine/src/scanner/`. This Python class is retained only
  so `strategy_wiring.py` can still instantiate MARKET_SCANNER and so
  `strategy_read_routes.py` has a harmless fallback. `start()` / `stop()`
  are no-ops; getters return empty lists.
MODULE_NOTE (中): 符号发现由 Rust `openclaw_engine::scanner` 承担。
  Python 类仅保留用于 wiring 实例化与 API 降级备援；`start/stop` 为空操作，
  getter 返回空。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

MIN_VOLUME_24H_USDT: int = 5_000_000
MIN_PRICE_USDT: float = 0.01
MAX_SYMBOLS_TO_TRADE: int = 25


@dataclass
class SymbolOpportunity:
    symbol: str = ""
    score: float = 0.0
    category: str = ""
    funding_rate: float = 0.0
    funding_rate_abs_bps: float = 0.0
    volume_24h: float = 0.0
    price: float = 0.0
    price_change_pct_24h: float = 0.0
    volatility_hint: str = ""
    reason: str = ""
    api_category: str = "linear"


class MarketScanner:
    def __init__(
        self,
        *,
        scan_interval_sec: float = 300.0,
        min_volume: float = MIN_VOLUME_24H_USDT,
        max_symbols: int = MAX_SYMBOLS_TO_TRADE,
        base_url: str = "https://api.bybit.com",
        categories: list[str] | None = None,
    ) -> None:
        self._scan_interval_sec = scan_interval_sec
        self._min_volume = min_volume
        self._max_symbols = max_symbols
        self._base_url = base_url
        self._categories = list(categories or ["linear"])
        self._callbacks: list[Any] = []

    def register_on_scan(self, callback: Any) -> None:
        self._callbacks.append(callback)

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def scan(self) -> list[SymbolOpportunity]:
        return []

    def get_latest_opportunities(self) -> list[dict[str, Any]]:
        return []

    def get_stats(self) -> dict[str, Any]:
        return {
            "stub": True,
            "source": "rust_engine_primary",
            "max_symbols": self._max_symbols,
            "categories": list(self._categories),
        }


__all__ = [
    "MIN_VOLUME_24H_USDT",
    "MIN_PRICE_USDT",
    "MAX_SYMBOLS_TO_TRADE",
    "SymbolOpportunity",
    "MarketScanner",
]
