"""Replay prepare admission policy.

This module keeps replay preparation routes from owning environment-switch
semantics directly. It is intentionally pure: callers translate
``ReplayPrepareRejection`` into their transport-level error type.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Optional


_TRUTHY = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ReplayPrepareRejection:
    """Structured rejection returned by the replay prepare policy."""

    status_code: int
    reason_code: str
    message: str

    def as_detail(self) -> dict[str, object]:
        return {
            "reason_codes": [self.reason_code],
            "message": self.message,
        }


@dataclass(frozen=True)
class ReplayPreparePolicy:
    """Admission limits and fail-closed gates for replay fixture preparation."""

    quick_max_bars: int
    full_chain_max_events: int
    full_chain_prepare_enabled: bool
    full_chain_bulk_prod_ip_allowed: bool
    full_chain_max_bars_per_symbol: int
    full_chain_fetch_concurrency: int

    @classmethod
    def from_env(
        cls,
        getenv: Optional[Callable[[str, Optional[str]], Optional[str]]] = None,
    ) -> "ReplayPreparePolicy":
        env_get = getenv or os.environ.get
        return cls(
            quick_max_bars=_bounded_int(
                env_get("OPENCLAW_REPLAY_QUICK_MAX_BARS", "5000"),
                default=5000,
                lower=200,
                upper=20_000,
            ),
            full_chain_max_events=_bounded_int(
                env_get("OPENCLAW_REPLAY_FULL_CHAIN_MAX_EVENTS", "100000"),
                default=100_000,
                lower=1_000,
                upper=300_000,
            ),
            full_chain_prepare_enabled=_truthy(
                env_get("OPENCLAW_REPLAY_PREPARE_ENABLED", "0"),
            ),
            full_chain_bulk_prod_ip_allowed=_truthy(
                env_get("OPENCLAW_REPLAY_BULK_ALLOW_PROD_IP", "0"),
            ),
            full_chain_max_bars_per_symbol=_bounded_int(
                env_get("OPENCLAW_REPLAY_FULL_CHAIN_MAX_BARS_PER_SYMBOL", "12000"),
                default=12_000,
                lower=200,
                upper=50_000,
            ),
            full_chain_fetch_concurrency=_bounded_int(
                env_get("OPENCLAW_REPLAY_FULL_CHAIN_FETCH_CONCURRENCY", "3"),
                default=3,
                lower=1,
                upper=5,
            ),
        )

    def validate_quick_window(self, *, estimated_bars: int) -> Optional[ReplayPrepareRejection]:
        if estimated_bars <= self.quick_max_bars:
            return None
        return ReplayPrepareRejection(
            status_code=400,
            reason_code="replay_quick_window_too_large",
            message=(
                f"requested window estimates {estimated_bars} bars; "
                f"quick replay limit is {self.quick_max_bars}"
            ),
        )

    def validate_full_chain_prepare_enabled(self) -> Optional[ReplayPrepareRejection]:
        if self.full_chain_prepare_enabled:
            return None
        return ReplayPrepareRejection(
            status_code=403,
            reason_code="replay_full_chain_prepare_disabled",
            message=(
                "full-chain replay prepare is disabled; set "
                "OPENCLAW_REPLAY_PREPARE_ENABLED=1 only for governed R1 hardening"
            ),
        )

    def validate_full_chain_bulk_prod_ip(
        self,
        *,
        is_live_release_profile: bool,
    ) -> Optional[ReplayPrepareRejection]:
        if not is_live_release_profile or self.full_chain_bulk_prod_ip_allowed:
            return None
        return ReplayPrepareRejection(
            status_code=403,
            reason_code="replay_full_chain_prod_ip_blocked",
            message=(
                "full-chain replay prepare is enabled, but bulk Bybit fetches "
                "from the live release host are blocked unless "
                "OPENCLAW_REPLAY_BULK_ALLOW_PROD_IP=1 is set for a governed run"
            ),
        )

    def validate_full_chain_bars_per_symbol(
        self,
        *,
        estimated_bars_per_symbol: int,
    ) -> Optional[ReplayPrepareRejection]:
        if estimated_bars_per_symbol <= self.full_chain_max_bars_per_symbol:
            return None
        return ReplayPrepareRejection(
            status_code=400,
            reason_code="replay_full_chain_window_too_large_per_symbol",
            message=(
                f"requested window estimates {estimated_bars_per_symbol} "
                f"bars per symbol; full-chain per-symbol limit is "
                f"{self.full_chain_max_bars_per_symbol}"
            ),
        )

    def validate_full_chain_event_window(
        self,
        *,
        estimated_events: int,
        symbol_count: int,
    ) -> Optional[ReplayPrepareRejection]:
        if estimated_events <= self.full_chain_max_events:
            return None
        return ReplayPrepareRejection(
            status_code=400,
            reason_code="replay_full_chain_window_too_large",
            message=(
                f"requested window estimates {estimated_events} events across "
                f"{symbol_count} symbols; full-chain limit is "
                f"{self.full_chain_max_events}"
            ),
        )


def _truthy(raw: Optional[str]) -> bool:
    return str(raw or "").strip().lower() in _TRUTHY


def _bounded_int(raw: Optional[str], *, default: int, lower: int, upper: int) -> int:
    try:
        parsed = int(str(raw))
    except (TypeError, ValueError):
        parsed = default
    return max(lower, min(parsed, upper))

