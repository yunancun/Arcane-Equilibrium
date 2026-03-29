"""
Test suite for Scanner Rate Limiter — T2.22 GAP-L3

Comprehensive tests covering ~100% of scanner_rate_limiter.py functionality.
Tests cover:
  - Configuration and initialization
  - Rate limiting enforcement (5-minute minimum interval)
  - Error cooldown handling (10-minute default)
  - Concurrent scan limits
  - Audit callbacks
  - Statistics tracking
  - Thread-safety
  - Edge cases and state transitions
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch, call

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.scanner_rate_limiter import ScannerConfig, ScannerRateLimiter, ScanStats


class TestScannerConfig:
    """Test ScannerConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ScannerConfig()
        assert config.min_scan_interval_seconds == 300  # 5 minutes
        assert config.max_concurrent_scans == 1
        assert config.scan_cooldown_after_error_seconds == 600  # 10 minutes

    def test_custom_config(self):
        """Test custom configuration values."""
        config = ScannerConfig(
            min_scan_interval_seconds=60,
            max_concurrent_scans=3,
            scan_cooldown_after_error_seconds=120,
        )
        assert config.min_scan_interval_seconds == 60
        assert config.max_concurrent_scans == 3
        assert config.scan_cooldown_after_error_seconds == 120

    def test_partial_config(self):
        """Test partial configuration override."""
        config = ScannerConfig(min_scan_interval_seconds=120)
        assert config.min_scan_interval_seconds == 120
        assert config.max_concurrent_scans == 1
        assert config.scan_cooldown_after_error_seconds == 600


class TestScanStats:
    """Test ScanStats dataclass."""

    def test_default_stats(self):
        """Test default statistics initialization."""
        stats = ScanStats()
        assert stats.total_scans == 0
        assert stats.total_errors == 0
        assert stats.total_successes == 0
        assert stats.average_interval_seconds == 0.0
        assert stats.last_scan_time_ms is None
        assert stats.last_error_time_ms is None

    def test_custom_stats(self):
        """Test custom statistics values."""
        stats = ScanStats(
            total_scans=5,
            total_errors=1,
            total_successes=4,
            average_interval_seconds=310.5,
            last_scan_time_ms=1000000,
            last_error_time_ms=999000,
        )
        assert stats.total_scans == 5
        assert stats.total_errors == 1
        assert stats.total_successes == 4
        assert stats.average_interval_seconds == 310.5
        assert stats.last_scan_time_ms == 1000000
        assert stats.last_error_time_ms == 999000


class TestScannerRateLimiterBasics:
    """Test basic rate limiter initialization and configuration."""

    def test_init_default_config(self):
        """Test initialization with default config."""
        limiter = ScannerRateLimiter()
        assert limiter.config.min_scan_interval_seconds == 300
        assert limiter.config.max_concurrent_scans == 1
        assert limiter.audit_callback is None

    def test_init_custom_config(self):
        """Test initialization with custom config."""
        config = ScannerConfig(min_scan_interval_seconds=60)
        limiter = ScannerRateLimiter(config=config)
        assert limiter.config.min_scan_interval_seconds == 60

    def test_init_with_audit_callback(self):
        """Test initialization with audit callback."""
        callback = Mock()
        limiter = ScannerRateLimiter(audit_callback=callback)
        assert limiter.audit_callback is callback

    def test_init_none_config_uses_default(self):
        """Test that None config defaults correctly."""
        limiter = ScannerRateLimiter(config=None)
        assert limiter.config.min_scan_interval_seconds == 300


class TestCanScan:
    """Test can_scan() method for rate limit checks."""

    def test_can_scan_first_call(self):
        """Test that first scan is always allowed."""
        limiter = ScannerRateLimiter()
        can, reason = limiter.can_scan()
        assert can is True
        assert reason == "ok"

    def test_can_scan_before_interval_elapsed(self):
        """Test that scan is blocked before minimum interval."""
        limiter = ScannerRateLimiter(
            config=ScannerConfig(min_scan_interval_seconds=10)
        )

        # Simulate first scan
        with patch.object(limiter, "_current_time_ms") as mock_time:
            mock_time.return_value = 0
            assert limiter.record_scan_start()
            limiter.record_scan_complete()

            # Try scan within 5 seconds (before 10 second minimum)
            mock_time.return_value = 5000
            can, reason = limiter.can_scan()
            assert can is False
            assert "min_interval_not_reached" in reason
            assert "remaining" in reason

    def test_can_scan_after_interval_elapsed(self):
        """Test that scan is allowed after minimum interval."""
        limiter = ScannerRateLimiter(
            config=ScannerConfig(min_scan_interval_seconds=10)
        )

        with patch.object(limiter, "_current_time_ms") as mock_time:
            # First scan
            mock_time.return_value = 0
            limiter.record_scan_start()
            limiter.record_scan_complete()

            # After 10 seconds, scan should be allowed
            mock_time.return_value = 10000
            can, reason = limiter.can_scan()
            assert can is True
            assert reason == "ok"

    def test_max_concurrent_scans_limit(self):
        """Test that max concurrent scans limit is enforced."""
        limiter = ScannerRateLimiter(
            config=ScannerConfig(max_concurrent_scans=1)
        )

        # First scan starts
        assert limiter.record_scan_start()

        # Second scan should be blocked
        can, reason = limiter.can_scan()
        assert can is False
        assert "max_concurrent_scans_reached" in reason

    def test_error_cooldown_blocks_scan(self):
        """Test that error cooldown prevents scanning."""
        limiter = ScannerRateLimiter(
            config=ScannerConfig(scan_cooldown_after_error_seconds=10)
        )

        with patch.object(limiter, "_current_time_ms") as mock_time:
            mock_time.return_value = 0
            limiter.record_scan_error()

            # Try to scan within 5 seconds (before 10 second cooldown)
            mock_time.return_value = 5000
            can, reason = limiter.can_scan()
            assert can is False
            assert "error_cooldown_active" in reason

    def test_error_cooldown_expires(self):
        """Test that error cooldown expires after specified time."""
        limiter = ScannerRateLimiter(
            config=ScannerConfig(scan_cooldown_after_error_seconds=10)
        )

        with patch.object(limiter, "_current_time_ms") as mock_time:
            mock_time.return_value = 0
            limiter.record_scan_error()

            # After 10 seconds, cooldown should expire
            mock_time.return_value = 10000
            can, reason = limiter.can_scan()
            assert can is True
            assert reason == "ok"


class TestRecordScanStart:
    """Test record_scan_start() method."""

    def test_record_scan_start_success(self):
        """Test successful scan start recording."""
        limiter = ScannerRateLimiter()
        result = limiter.record_scan_start()
        assert result is True

    def test_record_scan_start_rate_limited(self):
        """Test that scan start is rejected when rate limited."""
        limiter = ScannerRateLimiter(
            config=ScannerConfig(min_scan_interval_seconds=10)
        )

        with patch.object(limiter, "_current_time_ms") as mock_time:
            mock_time.return_value = 0
            limiter.record_scan_start()
            limiter.record_scan_complete()

            # Try within 5 seconds
            mock_time.return_value = 5000
            result = limiter.record_scan_start()
            assert result is False

    def test_record_scan_start_increments_active(self):
        """Test that active scan count is incremented."""
        limiter = ScannerRateLimiter(
            config=ScannerConfig(max_concurrent_scans=2)
        )

        assert limiter.record_scan_start()
        # Check that internal state incremented
        assert limiter._active_scans == 1

        assert limiter.record_scan_start()
        assert limiter._active_scans == 2

    def test_record_scan_start_with_audit_callback(self):
        """Test audit callback on scan start."""
        callback = Mock()
        limiter = ScannerRateLimiter(audit_callback=callback)

        limiter.record_scan_start()
        callback.assert_called()
        # Find the call for scan_start
        found = False
        for call_obj in callback.call_args_list:
            if call_obj[0][0] == "scan_start":
                found = True
        assert found


class TestRecordScanComplete:
    """Test record_scan_complete() method."""

    def test_record_scan_complete(self):
        """Test recording a successful scan completion."""
        limiter = ScannerRateLimiter()

        limiter.record_scan_start()
        limiter.record_scan_complete()

        stats = limiter.get_scan_stats()
        assert stats.total_scans == 1
        assert stats.total_errors == 0

    def test_record_scan_complete_clears_error_cooldown(self):
        """Test that successful scan clears error cooldown."""
        limiter = ScannerRateLimiter(
            config=ScannerConfig(scan_cooldown_after_error_seconds=10)
        )

        with patch.object(limiter, "_current_time_ms") as mock_time:
            # Record error at t=0
            mock_time.return_value = 0
            limiter.record_scan_error()
            assert limiter._last_error_time_ms is not None

            # Record successful scan at t=11s (after cooldown expires)
            mock_time.return_value = 11000
            assert limiter.record_scan_start()
            limiter.record_scan_complete()
            assert limiter._last_error_time_ms is None

    def test_record_scan_complete_decrements_active(self):
        """Test that active scan count is decremented."""
        limiter = ScannerRateLimiter()

        limiter.record_scan_start()
        assert limiter._active_scans == 1

        limiter.record_scan_complete()
        assert limiter._active_scans == 0

    def test_record_scan_complete_without_start(self):
        """Test recording completion without a start."""
        limiter = ScannerRateLimiter()
        limiter.record_scan_complete()
        # Should handle gracefully without error
        stats = limiter.get_scan_stats()
        assert stats.total_scans == 0

    def test_record_scan_complete_tracks_intervals(self):
        """Test that scan intervals are tracked."""
        limiter = ScannerRateLimiter()

        with patch.object(limiter, "_current_time_ms") as mock_time:
            # First scan: 0 to 500 ms
            mock_time.return_value = 0
            limiter.record_scan_start()
            mock_time.return_value = 500
            limiter.record_scan_complete()

            # Second scan: 5500 to 6000 ms (interval ~5s)
            mock_time.return_value = 5500
            limiter.record_scan_start()
            mock_time.return_value = 6000
            limiter.record_scan_complete()

            stats = limiter.get_scan_stats()
            assert stats.total_scans == 2
            # Average should include the interval timing
            assert stats.average_interval_seconds > 0


class TestRecordScanError:
    """Test record_scan_error() method."""

    def test_record_scan_error(self):
        """Test recording a scan error."""
        limiter = ScannerRateLimiter()

        limiter.record_scan_error()

        stats = limiter.get_scan_stats()
        assert stats.total_errors == 1

    def test_record_scan_error_activates_cooldown(self):
        """Test that error activates cooldown."""
        limiter = ScannerRateLimiter()

        limiter.record_scan_error()
        assert limiter._last_error_time_ms is not None

    def test_record_scan_error_decrements_active(self):
        """Test that active scan count is decremented on error."""
        limiter = ScannerRateLimiter()

        limiter.record_scan_start()
        assert limiter._active_scans == 1

        limiter.record_scan_error()
        assert limiter._active_scans == 0

    def test_multiple_errors_update_stats(self):
        """Test multiple errors are tracked."""
        limiter = ScannerRateLimiter()

        limiter.record_scan_error()
        limiter.record_scan_error()
        limiter.record_scan_error()

        stats = limiter.get_scan_stats()
        assert stats.total_errors == 3


class TestGetNextScanTimeMs:
    """Test get_next_scan_time_ms() method."""

    def test_next_scan_time_first_call_none(self):
        """Test that no prior scan returns None."""
        limiter = ScannerRateLimiter()
        next_time = limiter.get_next_scan_time_ms()
        assert next_time is None

    def test_next_scan_time_after_completion(self):
        """Test next scan time calculation after completion."""
        limiter = ScannerRateLimiter(
            config=ScannerConfig(min_scan_interval_seconds=10)
        )

        with patch.object(limiter, "_current_time_ms") as mock_time:
            mock_time.return_value = 1000
            limiter.record_scan_start()
            limiter.record_scan_complete()

            next_time = limiter.get_next_scan_time_ms()
            assert next_time == 1000 + (10 * 1000)  # 10 seconds later

    def test_next_scan_time_after_error(self):
        """Test next scan time calculation after error."""
        limiter = ScannerRateLimiter(
            config=ScannerConfig(scan_cooldown_after_error_seconds=10)
        )

        with patch.object(limiter, "_current_time_ms") as mock_time:
            mock_time.return_value = 2000
            limiter.record_scan_error()

            next_time = limiter.get_next_scan_time_ms()
            assert next_time == 2000 + (10 * 1000)  # 10 seconds later

    def test_next_scan_time_error_takes_priority(self):
        """Test that error cooldown takes priority over interval."""
        limiter = ScannerRateLimiter(
            config=ScannerConfig(
                min_scan_interval_seconds=5,
                scan_cooldown_after_error_seconds=20,
            )
        )

        with patch.object(limiter, "_current_time_ms") as mock_time:
            # Complete a scan
            mock_time.return_value = 0
            limiter.record_scan_start()
            limiter.record_scan_complete()

            # Record an error
            mock_time.return_value = 1000
            limiter.record_scan_error()

            next_time = limiter.get_next_scan_time_ms()
            # Should be based on error cooldown (20s), not interval (5s)
            assert next_time == 1000 + (20 * 1000)


class TestTimeUntilNextScan:
    """Test time_until_next_scan_seconds() method."""

    def test_time_until_next_scan_zero_when_ready(self):
        """Test zero time when scan is ready."""
        limiter = ScannerRateLimiter()
        time_remaining = limiter.time_until_next_scan_seconds()
        assert time_remaining == 0.0

    def test_time_until_next_scan_after_completion(self):
        """Test time calculation after scan completion."""
        limiter = ScannerRateLimiter(
            config=ScannerConfig(min_scan_interval_seconds=10)
        )

        with patch.object(limiter, "_current_time_ms") as mock_time:
            mock_time.return_value = 1000
            limiter.record_scan_start()
            limiter.record_scan_complete()

            # At 3 seconds, should have ~7 seconds to wait
            mock_time.return_value = 4000
            time_remaining = limiter.time_until_next_scan_seconds()
            assert 6.9 < time_remaining < 7.1

    def test_time_until_next_scan_after_error(self):
        """Test time calculation after error."""
        limiter = ScannerRateLimiter(
            config=ScannerConfig(scan_cooldown_after_error_seconds=10)
        )

        with patch.object(limiter, "_current_time_ms") as mock_time:
            mock_time.return_value = 2000
            limiter.record_scan_error()

            # At 5 seconds, should have ~5 seconds to wait
            mock_time.return_value = 7000
            time_remaining = limiter.time_until_next_scan_seconds()
            assert 4.9 < time_remaining < 5.1


class TestGetScanStats:
    """Test get_scan_stats() method."""

    def test_get_scan_stats_initial(self):
        """Test initial scan stats."""
        limiter = ScannerRateLimiter()
        stats = limiter.get_scan_stats()

        assert stats.total_scans == 0
        assert stats.total_errors == 0
        assert stats.total_successes == 0
        assert stats.average_interval_seconds == 0.0
        assert stats.last_scan_time_ms is None
        assert stats.last_error_time_ms is None

    def test_get_scan_stats_after_scan(self):
        """Test scan stats after successful scan."""
        limiter = ScannerRateLimiter()

        limiter.record_scan_start()
        limiter.record_scan_complete()

        stats = limiter.get_scan_stats()
        assert stats.total_scans == 1
        assert stats.total_successes == 1
        assert stats.total_errors == 0
        assert stats.last_scan_time_ms is not None

    def test_get_scan_stats_multiple_scans(self):
        """Test stats with multiple scans."""
        limiter = ScannerRateLimiter()

        with patch.object(limiter, "_current_time_ms") as mock_time:
            # Scan 1
            mock_time.return_value = 0
            limiter.record_scan_start()
            mock_time.return_value = 100
            limiter.record_scan_complete()

            # Scan 2
            mock_time.return_value = 5100
            limiter.record_scan_start()
            mock_time.return_value = 5200
            limiter.record_scan_complete()

            stats = limiter.get_scan_stats()
            assert stats.total_scans == 2
            assert stats.total_successes == 2
            assert stats.average_interval_seconds > 0

    def test_get_scan_stats_with_errors(self):
        """Test stats with errors mixed in."""
        limiter = ScannerRateLimiter(
            config=ScannerConfig(
                min_scan_interval_seconds=1,
                scan_cooldown_after_error_seconds=1
            )
        )

        with patch.object(limiter, "_current_time_ms") as mock_time:
            # First scan: success
            mock_time.return_value = 0
            limiter.record_scan_start()
            mock_time.return_value = 100
            limiter.record_scan_complete()

            # Second scan: error (no cooldown yet)
            mock_time.return_value = 1100
            limiter.record_scan_start()
            limiter.record_scan_error()

            # Third scan: success (after 1s cooldown)
            mock_time.return_value = 2100
            limiter.record_scan_start()
            mock_time.return_value = 2200
            limiter.record_scan_complete()

            stats = limiter.get_scan_stats()
            assert stats.total_scans == 2  # Only counts complete scans
            assert stats.total_errors == 1  # One error during a scan attempt
            assert stats.total_successes == 1  # 2 complete scans - 1 error = 1


class TestThreadSafety:
    """Test thread-safety of the rate limiter."""

    def test_concurrent_scan_starts(self):
        """Test that concurrent scan starts are properly synchronized."""
        limiter = ScannerRateLimiter(
            config=ScannerConfig(max_concurrent_scans=10)
        )

        results = []

        def attempt_scan():
            result = limiter.record_scan_start()
            results.append(result)

        threads = [threading.Thread(target=attempt_scan) for _ in range(15)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Only 10 should succeed (max_concurrent_scans=10)
        assert sum(results) == 10

    def test_concurrent_stats_read(self):
        """Test that stats can be safely read while scanning."""
        limiter = ScannerRateLimiter()

        limiter.record_scan_start()

        stats = limiter.get_scan_stats()
        assert stats is not None

        limiter.record_scan_complete()

    def test_concurrent_can_scan_check(self):
        """Test that can_scan is thread-safe."""
        limiter = ScannerRateLimiter()

        def check_scan():
            for _ in range(100):
                limiter.can_scan()

        threads = [threading.Thread(target=check_scan) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should complete without deadlock


class TestAuditCallbacks:
    """Test audit callback functionality."""

    def test_audit_on_scan_start(self):
        """Test audit callback on scan start."""
        callback = Mock()
        limiter = ScannerRateLimiter(audit_callback=callback)

        limiter.record_scan_start()

        # Find scan_start call
        found = False
        for call_obj in callback.call_args_list:
            if call_obj[0][0] == "scan_start":
                found = True
                assert "active_scans" in call_obj[0][1]
        assert found

    def test_audit_on_scan_complete(self):
        """Test audit callback on scan completion."""
        callback = Mock()
        limiter = ScannerRateLimiter(audit_callback=callback)

        limiter.record_scan_start()
        limiter.record_scan_complete()

        # Find scan_complete call
        found = False
        for call_obj in callback.call_args_list:
            if call_obj[0][0] == "scan_complete":
                found = True
                assert "total_scans" in call_obj[0][1]
                assert "duration_ms" in call_obj[0][1]
        assert found

    def test_audit_on_scan_error(self):
        """Test audit callback on scan error."""
        callback = Mock()
        limiter = ScannerRateLimiter(audit_callback=callback)

        limiter.record_scan_error()

        # Find scan_error call
        found = False
        for call_obj in callback.call_args_list:
            if call_obj[0][0] == "scan_error":
                found = True
                assert "total_errors" in call_obj[0][1]
        assert found

    def test_audit_on_scan_start_rejected(self):
        """Test audit callback when scan start is rejected."""
        callback = Mock()
        limiter = ScannerRateLimiter(
            config=ScannerConfig(max_concurrent_scans=1),
            audit_callback=callback,
        )

        limiter.record_scan_start()
        limiter.record_scan_start()  # Should be rejected

        # Find scan_start_rejected call
        found = False
        for call_obj in callback.call_args_list:
            if call_obj[0][0] == "scan_start_rejected":
                found = True
                assert "reason" in call_obj[0][1]
        assert found

    def test_no_callback_when_none(self):
        """Test that no errors occur when callback is None."""
        limiter = ScannerRateLimiter(audit_callback=None)

        limiter.record_scan_start()
        limiter.record_scan_complete()
        limiter.record_scan_error()

        # Should complete without errors


class TestIntegrationScenarios:
    """Integration tests for realistic usage scenarios."""

    def test_successful_scan_cycle(self):
        """Test a complete successful scan cycle."""
        limiter = ScannerRateLimiter(
            config=ScannerConfig(min_scan_interval_seconds=5)
        )

        # First scan
        can, reason = limiter.can_scan()
        assert can is True

        assert limiter.record_scan_start()
        limiter.record_scan_complete()

        stats = limiter.get_scan_stats()
        assert stats.total_scans == 1
        assert stats.total_errors == 0

        # Check wait time
        wait_time = limiter.time_until_next_scan_seconds()
        assert 4.9 < wait_time < 5.1

    def test_error_recovery_scenario(self):
        """Test recovery from an error."""
        limiter = ScannerRateLimiter(
            config=ScannerConfig(
                min_scan_interval_seconds=5,
                scan_cooldown_after_error_seconds=10,
            )
        )

        # Successful scan
        limiter.record_scan_start()
        limiter.record_scan_complete()

        # Failed scan
        limiter.record_scan_start()
        limiter.record_scan_error()

        # Should be blocked by error cooldown
        can, reason = limiter.can_scan()
        assert can is False
        assert "error_cooldown" in reason

    def test_state_recovery_after_successful_scan(self):
        """Test that successful scan clears error state."""
        limiter = ScannerRateLimiter(
            config=ScannerConfig(scan_cooldown_after_error_seconds=5)
        )

        with patch.object(limiter, "_current_time_ms") as mock_time:
            # Record error at t=0
            mock_time.return_value = 0
            limiter.record_scan_error()
            error_time = limiter._last_error_time_ms
            assert error_time is not None

            # Record successful scan at t=6s (after cooldown expires)
            mock_time.return_value = 6000
            assert limiter.record_scan_start()
            limiter.record_scan_complete()

            # Error state should be cleared
            assert limiter._last_error_time_ms is None

    def test_rapid_consecutive_scans_blocked(self):
        """Test that rapid consecutive scans are blocked."""
        limiter = ScannerRateLimiter(
            config=ScannerConfig(min_scan_interval_seconds=10)
        )

        with patch.object(limiter, "_current_time_ms") as mock_time:
            # First scan at t=0
            mock_time.return_value = 0
            assert limiter.record_scan_start()
            limiter.record_scan_complete()

            # Try second scan at t=1 (too soon)
            mock_time.return_value = 1000
            assert not limiter.record_scan_start()

            # Try at t=10 (should work)
            mock_time.return_value = 10000
            assert limiter.record_scan_start()
