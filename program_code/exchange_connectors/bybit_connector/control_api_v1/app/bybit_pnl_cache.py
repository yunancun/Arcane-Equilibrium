"""Bybit closed-PnL TTL cache.

MODULE_NOTE (中): Demo closed-PnL GUI 讀模型的小型進程內 TTL cache。它只緩存
  Bybit REST 讀取結果，不寫 trading.fills，也不改任何交易狀態。RLock + Condition
  用於同一 uvicorn worker 內的 in-flight 去重，避免多個 GUI refresh 同時打 Bybit。
MODULE_NOTE (EN): Small in-process TTL cache for the demo closed-PnL read model.
  It caches Bybit REST reads only and never writes trading.fills or trading state.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Condition, RLock
from typing import Any, Callable, Hashable


@dataclass(frozen=True)
class PnlCacheResult:
    """Cache result envelope used by route code."""

    value: list[dict[str, Any]]
    source_ts: int
    cache_age: float
    hit: bool


@dataclass
class _CacheEntry:
    value: list[dict[str, Any]]
    source_ts: int
    monotonic_ts: float


class ClosedPnlCache:
    """Thread-safe TTL cache with per-key in-flight fetch deduplication."""

    def __init__(self, ttl_sec: float = 8.0):
        self._ttl_sec = float(ttl_sec)
        self._lock = RLock()
        self._ready = Condition(self._lock)
        self._entries: dict[Hashable, _CacheEntry] = {}
        self._inflight: set[Hashable] = set()

    def clear(self) -> None:
        """Clear all cached rows and wake any waiters."""
        with self._lock:
            self._entries.clear()
            self._inflight.clear()
            self._ready.notify_all()

    def get_any(self, key: Hashable) -> PnlCacheResult | None:
        """Return cached data even when stale, for degraded Bybit-failure paths."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            return self._result(entry, hit=True)

    def get_or_fetch(
        self,
        key: Hashable,
        fetcher: Callable[[], list[dict[str, Any]]],
        *,
        force_refresh: bool = False,
    ) -> PnlCacheResult:
        """Return a fresh cached value or run one fetcher while siblings wait."""
        with self._lock:
            if not force_refresh:
                entry = self._entries.get(key)
                if entry is not None and self._is_fresh(entry):
                    return self._result(entry, hit=True)

            while key in self._inflight:
                self._ready.wait()
                entry = self._entries.get(key)
                if entry is not None and self._is_fresh(entry):
                    return self._result(entry, hit=True)

            self._inflight.add(key)

        try:
            value = [dict(row) for row in fetcher()]
            entry = _CacheEntry(
                value=value,
                source_ts=int(time.time() * 1000),
                monotonic_ts=time.monotonic(),
            )
            with self._lock:
                self._entries[key] = entry
                return self._result(entry, hit=False)
        finally:
            with self._lock:
                self._inflight.discard(key)
                self._ready.notify_all()

    def _is_fresh(self, entry: _CacheEntry) -> bool:
        return (time.monotonic() - entry.monotonic_ts) <= self._ttl_sec

    @staticmethod
    def _result(entry: _CacheEntry, *, hit: bool) -> PnlCacheResult:
        age = max(0.0, time.monotonic() - entry.monotonic_ts)
        return PnlCacheResult(
            value=[dict(row) for row in entry.value],
            source_ts=entry.source_ts,
            cache_age=round(age, 3),
            hit=hit,
        )
