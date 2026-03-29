"""
Scanner Rate Limiter — T2.22 GAP-L3 Implementation

Enforces the 5-minute minimum interval between full market scans per DOC-02 §9.2.

This module implements the ScannerRateLimiter engine that:
  - Prevents scanning more frequently than the minimum interval (300 seconds default)
  - Tracks scan lifecycle (pending, active, complete, failed)
  - Enforces error cooldowns after failed scans
  - Provides audit trails and scheduling recommendations
  - Thread-safe with optional audit callback support

Requirements from DOC-02:
  - Line 122: "Scanner cycle: 5-minute minimum interval between full market scans"
  - Table 9: Scanner cooldown in operational timing boundaries
  - Scout Agent (Table 3): "scans 650+ symbols every 5 min"

典范符合 / Specification Compliance:
  - DOC-02 §9.2 (Temporal Boundaries — Cooldown)
  - DOC-02 Table 9 (Operational Latency Budget)
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from typing import Optional, Callable, Dict, Any


@dataclass
class ScannerConfig:
    """
    Configuration for the Scanner Rate Limiter.

    Attributes:
        min_scan_interval_seconds: Minimum seconds between consecutive scans (default 300 = 5 min).
        max_concurrent_scans: Maximum number of concurrent scans allowed (default 1).
        scan_cooldown_after_error_seconds: Cooldown period after a failed scan (default 600 = 10 min).
    """
    min_scan_interval_seconds: int = 300  # 5 minutes per DOC-02
    max_concurrent_scans: int = 1
    scan_cooldown_after_error_seconds: int = 600  # 10 minutes


@dataclass
class ScanStats:
    """Statistics about scan activity."""
    total_scans: int = 0
    total_errors: int = 0
    total_successes: int = 0
    average_interval_seconds: float = 0.0
    last_scan_time_ms: Optional[int] = None
    last_error_time_ms: Optional[int] = None


class ScannerRateLimiter:
    """
    Thread-safe rate limiter for market scanner operations.

    Enforces the 5-minute minimum interval between full market scans and
    provides scheduling guidance, error handling, and audit trails.
    """

    def __init__(
        self,
        config: ScannerConfig = None,
        audit_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ):
        """
        Initialize the Scanner Rate Limiter.

        Args:
            config: ScannerConfig instance (defaults to ScannerConfig()).
            audit_callback: Optional callback for audit logging.
                           Called as: audit_callback(event_type: str, event_data: dict)
        """
        self.config = config or ScannerConfig()
        self.audit_callback = audit_callback

        # Thread safety
        self._lock = threading.RLock()

        # Scan state tracking
        self._last_scan_start_ms: Optional[int] = None
        self._last_scan_complete_ms: Optional[int] = None
        self._last_error_time_ms: Optional[int] = None
        self._active_scans: int = 0

        # Statistics
        self._total_scans: int = 0
        self._total_errors: int = 0
        self._scan_intervals: list[float] = []

    def can_scan(self) -> tuple[bool, str]:
        """
        Check if a scan can be started now.

        Returns:
            (can_scan: bool, reason: str)
                - If True: can start a scan immediately
                - If False: reason explains why (e.g., "min interval not reached", "error cooldown active", etc.)
        """
        with self._lock:
            # Check if error cooldown is active
            if self._last_error_time_ms is not None:
                time_since_error_ms = self._current_time_ms() - self._last_error_time_ms
                if time_since_error_ms < (self.config.scan_cooldown_after_error_seconds * 1000):
                    remaining_cooldown_s = (
                        (self.config.scan_cooldown_after_error_seconds * 1000 - time_since_error_ms) / 1000
                    )
                    return False, f"error_cooldown_active (remaining {remaining_cooldown_s:.1f}s)"

            # Check if max concurrent scans reached
            if self._active_scans >= self.config.max_concurrent_scans:
                return False, f"max_concurrent_scans_reached ({self._active_scans}/{self.config.max_concurrent_scans})"

            # Check if minimum interval has elapsed since last scan completion
            if self._last_scan_complete_ms is not None:
                time_since_last_complete_ms = self._current_time_ms() - self._last_scan_complete_ms
                min_interval_ms = self.config.min_scan_interval_seconds * 1000

                if time_since_last_complete_ms < min_interval_ms:
                    remaining_s = (min_interval_ms - time_since_last_complete_ms) / 1000
                    return False, f"min_interval_not_reached (remaining {remaining_s:.1f}s)"

            return True, "ok"

    def record_scan_start(self) -> bool:
        """
        Record the start of a scan operation.

        Returns:
            True if scan was recorded, False if rejected due to rate limits.
        """
        with self._lock:
            can, reason = self.can_scan()
            if not can:
                self._audit_event("scan_start_rejected", {"reason": reason})
                return False

            self._last_scan_start_ms = self._current_time_ms()
            self._active_scans += 1
            self._audit_event("scan_start", {"active_scans": self._active_scans})
            return True

    def record_scan_complete(self) -> None:
        """
        Record the completion of a successful scan.

        Updates the last completion time and success statistics.
        """
        with self._lock:
            if self._last_scan_start_ms is None:
                self._audit_event("scan_complete_no_start", {})
                return

            now_ms = self._current_time_ms()
            self._last_scan_complete_ms = now_ms
            self._last_error_time_ms = None  # Clear error cooldown on success

            # Update interval tracking - record time between start and complete
            interval_s = (now_ms - self._last_scan_start_ms) / 1000
            self._scan_intervals.append(interval_s)
            # Keep rolling window of last 100 intervals
            if len(self._scan_intervals) > 100:
                self._scan_intervals.pop(0)

            self._total_scans += 1
            self._active_scans = max(0, self._active_scans - 1)

            self._audit_event(
                "scan_complete",
                {
                    "total_scans": self._total_scans,
                    "active_scans": self._active_scans,
                    "duration_ms": now_ms - self._last_scan_start_ms,
                },
            )

    def record_scan_error(self) -> None:
        """
        Record a failed scan attempt.

        Activates the error cooldown period, preventing new scans for
        scan_cooldown_after_error_seconds.
        """
        with self._lock:
            self._last_error_time_ms = self._current_time_ms()
            self._total_errors += 1
            self._active_scans = max(0, self._active_scans - 1)

            self._audit_event(
                "scan_error",
                {
                    "total_errors": self._total_errors,
                    "active_scans": self._active_scans,
                    "cooldown_seconds": self.config.scan_cooldown_after_error_seconds,
                },
            )

    def get_next_scan_time_ms(self) -> Optional[int]:
        """
        Calculate when the next scan can start (in milliseconds since epoch).

        Returns:
            ISO-like timestamp (milliseconds) when scan can proceed, or None if now.
        """
        with self._lock:
            # Check error cooldown
            if self._last_error_time_ms is not None:
                error_cooldown_ms = self.config.scan_cooldown_after_error_seconds * 1000
                next_time_after_error = self._last_error_time_ms + error_cooldown_ms
                return next_time_after_error

            # Check normal interval
            if self._last_scan_complete_ms is not None:
                min_interval_ms = self.config.min_scan_interval_seconds * 1000
                next_time_after_interval = self._last_scan_complete_ms + min_interval_ms
                return next_time_after_interval

            # No prior scan, can go now
            return None

    def time_until_next_scan_seconds(self) -> float:
        """
        Time remaining before next scan is allowed.

        Returns:
            Seconds to wait. Returns 0.0 if a scan can start immediately.
        """
        with self._lock:
            next_time_ms = self.get_next_scan_time_ms()
            if next_time_ms is None:
                return 0.0

            now_ms = self._current_time_ms()
            time_remaining_ms = max(0, next_time_ms - now_ms)
            return time_remaining_ms / 1000.0

    def get_scan_stats(self) -> ScanStats:
        """
        Get current scan statistics.

        Returns:
            ScanStats object with totals and averages.
        """
        with self._lock:
            avg_interval = (
                sum(self._scan_intervals) / len(self._scan_intervals)
                if self._scan_intervals
                else 0.0
            )

            return ScanStats(
                total_scans=self._total_scans,
                total_errors=self._total_errors,
                total_successes=self._total_scans - self._total_errors,
                average_interval_seconds=avg_interval,
                last_scan_time_ms=self._last_scan_complete_ms,
                last_error_time_ms=self._last_error_time_ms,
            )

    def _current_time_ms(self) -> int:
        """Get current time in milliseconds since epoch."""
        return int(time.time() * 1000)

    def _audit_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """Emit an audit event if callback is registered."""
        if self.audit_callback:
            self.audit_callback(event_type, event_data)
