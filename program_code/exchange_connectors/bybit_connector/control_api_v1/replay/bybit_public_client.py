"""Dedicated Bybit public-data client for replay fixture building.

This module is intentionally isolated from the production Bybit client and
KlineManager. REF-21 full-chain replay may fetch a large amount of historical
public data, so it must use its own endpoint allowlist, rate policy, retry
budget, and user agent rather than sharing live trading runtime state.
"""

from __future__ import annotations

import json
import os
import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Optional


_BYBIT_PUBLIC_BASE_URL = "https://api.bybit.com"
_KLINE_ENDPOINT = "/v5/market/kline"
_KLINE_LIMIT = 200
_ALLOWED_ENDPOINTS = {_KLINE_ENDPOINT}
_RETRIABLE_HTTP_CODES = {429, 500, 502, 503, 504}
_RETRIABLE_BYBIT_RETCODES = {10006, 10016, 10018}
_TIMEFRAMES: dict[str, tuple[str, int]] = {
    "1m": ("1", 60_000),
    "3m": ("3", 180_000),
    "5m": ("5", 300_000),
    "15m": ("15", 900_000),
    "1h": ("60", 3_600_000),
    "4h": ("240", 14_400_000),
    "1d": ("D", 86_400_000),
}


class ReplayBybitPublicClientError(RuntimeError):
    """Raised when replay public-data fetch cannot complete safely."""


@dataclass(frozen=True)
class ReplayPublicRatePolicy:
    """Replay public-data rate policy.

    Bybit public-data fixture building is capped independently from any live
    trading REST pools. The global default is the REF-21 hard ceiling; the
    kline endpoint default is deliberately lower to leave margin for future
    full-chain metadata endpoints.
    """

    global_rps: float = 50.0
    kline_rps: float = 20.0


@dataclass(frozen=True)
class ReplayPublicRetryPolicy:
    max_attempts: int = 3
    base_backoff_ms: int = 250
    timeout_seconds: float = 12.0


def _env_float(name: str, default: float, *, lower: float, upper: float) -> float:
    raw = os.environ.get(name, "").strip()
    try:
        parsed = float(raw) if raw else default
    except ValueError:
        parsed = default
    return max(lower, min(parsed, upper))


def _env_int(name: str, default: int, *, lower: int, upper: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        parsed = int(raw) if raw else default
    except ValueError:
        parsed = default
    return max(lower, min(parsed, upper))


def current_replay_public_rate_policy() -> ReplayPublicRatePolicy:
    """Return the current replay-only Bybit public-data rate policy."""
    global_rps = _env_float(
        "OPENCLAW_REPLAY_PUBLIC_GLOBAL_RPS",
        50.0,
        lower=0.1,
        upper=50.0,
    )
    default_kline_rps = min(20.0, global_rps)
    kline_rps = _env_float(
        "OPENCLAW_REPLAY_PUBLIC_KLINE_RPS",
        default_kline_rps,
        lower=0.1,
        upper=global_rps,
    )
    if global_rps > 1.0 and kline_rps >= global_rps:
        kline_rps = max(0.1, global_rps - 1.0)
    return ReplayPublicRatePolicy(global_rps=global_rps, kline_rps=kline_rps)


def current_replay_public_retry_policy() -> ReplayPublicRetryPolicy:
    return ReplayPublicRetryPolicy(
        max_attempts=_env_int(
            "OPENCLAW_REPLAY_PUBLIC_RETRY_MAX_ATTEMPTS",
            3,
            lower=1,
            upper=5,
        ),
        base_backoff_ms=_env_int(
            "OPENCLAW_REPLAY_PUBLIC_BACKOFF_BASE_MS",
            250,
            lower=50,
            upper=2_000,
        ),
        timeout_seconds=_env_float(
            "OPENCLAW_REPLAY_PUBLIC_TIMEOUT_SECONDS",
            12.0,
            lower=2.0,
            upper=30.0,
        ),
    )


class ReplayPublicRateLimiter:
    """Thread-safe in-process limiter for replay public-data fetches."""

    def __init__(
        self,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._sleeper = sleeper
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._next_global_at = 0.0
        self._next_endpoint_at: dict[str, float] = {}

    def wait(self, endpoint: str, policy: ReplayPublicRatePolicy) -> None:
        if endpoint not in _ALLOWED_ENDPOINTS:
            raise ReplayBybitPublicClientError(
                f"replay_bybit_endpoint_not_allowed:{endpoint}"
            )
        endpoint_rps = policy.kline_rps if endpoint == _KLINE_ENDPOINT else policy.global_rps
        global_interval = 1.0 / max(policy.global_rps, 0.1)
        endpoint_interval = 1.0 / max(endpoint_rps, 0.1)
        with self._lock:
            now = self._monotonic()
            next_endpoint_at = self._next_endpoint_at.get(endpoint, 0.0)
            wait_for = max(self._next_global_at - now, next_endpoint_at - now, 0.0)
            if wait_for > 0:
                self._sleeper(wait_for)
                now = self._monotonic()
            self._next_global_at = now + global_interval
            self._next_endpoint_at[endpoint] = now + endpoint_interval


class ReplayBybitPublicClient:
    """Dedicated replay client for Bybit public market-data endpoints."""

    def __init__(
        self,
        *,
        urlopen: Callable[..., Any] = urllib.request.urlopen,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        base_url: str = _BYBIT_PUBLIC_BASE_URL,
    ) -> None:
        self._urlopen = urlopen
        self._sleeper = sleeper
        self._base_url = base_url.rstrip("/")
        self._limiter = ReplayPublicRateLimiter(
            sleeper=sleeper,
            monotonic=monotonic,
        )

    def fetch_klines_sync(
        self,
        *,
        symbol: str,
        category: str,
        timeframe: str,
        start_ms: int,
        end_ms: int,
        max_bars: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """Fetch Bybit public klines and return replay MarketEvent dictionaries."""
        interval_tuple = _TIMEFRAMES.get(timeframe)
        if interval_tuple is None:
            raise ReplayBybitPublicClientError(
                f"replay_bybit_unsupported_timeframe:{timeframe}"
            )
        interval = interval_tuple[0]
        events_by_ts: dict[int, dict[str, Any]] = {}
        end_cursor = end_ms
        request_bar_budget = max_bars if max_bars is not None else 5_000
        max_requests = int((request_bar_budget + _KLINE_LIMIT - 1) / _KLINE_LIMIT) + 2

        for _ in range(max_requests):
            data = self._request_json(
                _KLINE_ENDPOINT,
                {
                    "category": category,
                    "symbol": symbol,
                    "interval": interval,
                    "start": str(start_ms),
                    "end": str(end_cursor),
                    "limit": str(_KLINE_LIMIT),
                },
            )
            ret_code = data.get("retCode")
            if ret_code != 0:
                raise ReplayBybitPublicClientError(
                    "bybit_public_kline_error:"
                    + str(data.get("retMsg") or ret_code or "unknown")
                )
            rows = data.get("result", {}).get("list", [])
            if not rows:
                break

            parsed_ts: list[int] = []
            for row in rows:
                ts = int(row[0])
                parsed_ts.append(ts)
                if ts < start_ms or ts > end_ms:
                    continue
                events_by_ts[ts] = {
                    "ts_ms": ts,
                    "symbol": symbol,
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                }

            oldest = min(parsed_ts)
            if oldest <= start_ms or len(rows) < _KLINE_LIMIT:
                break
            next_cursor = oldest - 1
            if next_cursor >= end_cursor:
                break
            end_cursor = next_cursor

        return [events_by_ts[k] for k in sorted(events_by_ts)]

    def _request_json(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if endpoint not in _ALLOWED_ENDPOINTS:
            raise ReplayBybitPublicClientError(
                f"replay_bybit_endpoint_not_allowed:{endpoint}"
            )
        retry_policy = current_replay_public_retry_policy()
        url = self._build_url(endpoint, params)
        last_error: Optional[BaseException] = None
        for attempt in range(1, retry_policy.max_attempts + 1):
            self._limiter.wait(endpoint, current_replay_public_rate_policy())
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "OpenClawReplayPublicData/1.0"},
            )
            try:
                with self._urlopen(req, timeout=retry_policy.timeout_seconds) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code in _RETRIABLE_HTTP_CODES and attempt < retry_policy.max_attempts:
                    self._sleep_before_retry(attempt, retry_policy)
                    continue
                raise ReplayBybitPublicClientError(
                    f"bybit_public_http_error:{exc.code}"
                ) from exc
            except urllib.error.URLError as exc:
                last_error = exc
                if attempt < retry_policy.max_attempts:
                    self._sleep_before_retry(attempt, retry_policy)
                    continue
                raise ReplayBybitPublicClientError(
                    f"bybit_public_url_error:{exc.reason}"
                ) from exc

            ret_code = data.get("retCode")
            if ret_code in _RETRIABLE_BYBIT_RETCODES and attempt < retry_policy.max_attempts:
                last_error = ReplayBybitPublicClientError(
                    f"bybit_public_retriable_retcode:{ret_code}"
                )
                self._sleep_before_retry(attempt, retry_policy)
                continue
            return data

        raise ReplayBybitPublicClientError(
            f"bybit_public_retry_exhausted:{last_error}"
        )

    def _build_url(self, endpoint: str, params: dict[str, str]) -> str:
        if endpoint not in _ALLOWED_ENDPOINTS:
            raise ReplayBybitPublicClientError(
                f"replay_bybit_endpoint_not_allowed:{endpoint}"
            )
        query = urllib.parse.urlencode(params)
        return f"{self._base_url}{endpoint}?{query}"

    def _sleep_before_retry(
        self,
        attempt: int,
        retry_policy: ReplayPublicRetryPolicy,
    ) -> None:
        base_seconds = retry_policy.base_backoff_ms / 1000.0
        jitter = random.uniform(0.0, base_seconds * 0.25)
        self._sleeper(base_seconds * (2 ** (attempt - 1)) + jitter)


__all__ = [
    "ReplayBybitPublicClient",
    "ReplayBybitPublicClientError",
    "ReplayPublicRateLimiter",
    "ReplayPublicRatePolicy",
    "ReplayPublicRetryPolicy",
    "current_replay_public_rate_policy",
    "current_replay_public_retry_policy",
]
