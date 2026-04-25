"""
G3-03 Phase B — ExecutorConfigCache unit tests.
Coverage:
  1. Initial fail-closed default (shadow_mode=True before any IPC fetch).
  2. Successful IPC fetch updates snapshot + marks initialized.
  3. Polling refresh (interval-driven re-fetch).
  4. IPC error after init: retains previous good snapshot.
  5. IPC error before init: stays on fail-closed default.
  6. Lifecycle stop_polling joins thread cleanly.
  7. shadow_mode_provider() returns current shadow_mode (live read).
  8. Concurrent reads stay safe under interleaved polls.
  9. Malformed IPC response (missing executor) treated as error → fail-closed.
 10. Module singleton dedup via get_executor_config_cache().
"""

from __future__ import annotations

import os
import sys
import threading
import time
import unittest
from unittest.mock import patch

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app import executor_config_cache as ecc_mod
from app.executor_config_cache import (
    ExecutorConfigCache,
    ExecutorRuntimeConfig,
    get_executor_config_cache,
)


def _make_response(
    *,
    shadow: bool = False,
    max_pos: float = 0.10,
    per_symbol: dict | None = None,
    version: int = 7,
) -> dict:
    """Helper: build a get_risk_config-shaped IPC response."""
    return {
        "config": {
            "executor": {
                "shadow_mode": shadow,
                "max_position_pct": max_pos,
                "per_symbol_position_cap": per_symbol or {},
            },
        },
        "version": version,
    }


class TestInitialFailClosedDefault(unittest.TestCase):
    """1. Pre-fetch state must be safe (shadow_mode=True)."""

    def test_default_snapshot_is_shadow_mode_true(self):
        cache = ExecutorConfigCache()
        snap = cache.get()
        self.assertTrue(snap.shadow_mode)
        self.assertFalse(cache.is_initialized())
        self.assertEqual(snap.config_version, 0)

    def test_provider_callable_returns_true_initially(self):
        cache = ExecutorConfigCache()
        provider = cache.shadow_mode_provider()
        self.assertTrue(provider())


class TestSuccessfulFetch(unittest.TestCase):
    """2. Successful single-poll updates snapshot."""

    def test_poll_once_success_updates_snapshot(self):
        cache = ExecutorConfigCache()
        with patch.object(
            cache, "_fetch_via_ipc_blocking",
            return_value=ExecutorRuntimeConfig(
                shadow_mode=False,
                max_position_pct=0.20,
                per_symbol_position_cap={"BTCUSDT": 0.50},
                config_version=42,
                fetched_at_ms=int(time.time() * 1000),
            ),
        ):
            cache._poll_once()
        snap = cache.get()
        self.assertFalse(snap.shadow_mode)
        self.assertAlmostEqual(snap.max_position_pct, 0.20)
        self.assertEqual(snap.per_symbol_position_cap.get("BTCUSDT"), 0.50)
        self.assertEqual(snap.config_version, 42)
        self.assertTrue(cache.is_initialized())

    def test_response_parser_extracts_executor_subslice(self):
        resp = _make_response(shadow=False, max_pos=0.07, version=11)
        snap = ExecutorConfigCache._parse_response(resp)
        self.assertFalse(snap.shadow_mode)
        self.assertAlmostEqual(snap.max_position_pct, 0.07)
        self.assertEqual(snap.config_version, 11)


class TestPollingRefresh(unittest.TestCase):
    """3. Polling daemon re-fetches at interval."""

    def test_poll_loop_refreshes_at_interval(self):
        cache = ExecutorConfigCache(poll_interval_s=0.05)
        responses = [
            ExecutorRuntimeConfig(shadow_mode=True, config_version=1, fetched_at_ms=1),
            ExecutorRuntimeConfig(shadow_mode=False, config_version=2, fetched_at_ms=2),
            ExecutorRuntimeConfig(shadow_mode=False, config_version=3, fetched_at_ms=3),
        ]
        idx = {"i": 0}

        def fake_fetch():
            i = idx["i"]
            idx["i"] = min(i + 1, len(responses) - 1)
            return responses[i]

        with patch.object(cache, "_fetch_via_ipc_blocking", side_effect=lambda: fake_fetch()):
            cache.start_polling()
            try:
                # Wait until we observe at least 2 successful polls.
                deadline = time.time() + 2.0
                while time.time() < deadline:
                    if cache._stats_snapshot_for_tests()["successes"] >= 2:
                        break
                    time.sleep(0.01)
            finally:
                cache.stop_polling()
        stats = cache._stats_snapshot_for_tests()
        self.assertGreaterEqual(stats["successes"], 2)
        # Final snapshot should be one of the later entries (shadow=False).
        self.assertFalse(cache.get().shadow_mode)


class TestIpcErrorRetainsPrevious(unittest.TestCase):
    """4. After successful init, transient errors retain previous snapshot."""

    def test_post_init_error_retains_prev_snapshot(self):
        cache = ExecutorConfigCache()
        good = ExecutorRuntimeConfig(
            shadow_mode=False, max_position_pct=0.30, config_version=99, fetched_at_ms=1,
        )
        with patch.object(cache, "_fetch_via_ipc_blocking", return_value=good):
            cache._poll_once()
        self.assertTrue(cache.is_initialized())
        # Now simulate a transient failure.
        with patch.object(
            cache, "_fetch_via_ipc_blocking",
            side_effect=ConnectionError("socket closed"),
        ):
            cache._poll_once()
        snap = cache.get()
        # Previous good snapshot retained.
        self.assertFalse(snap.shadow_mode)
        self.assertAlmostEqual(snap.max_position_pct, 0.30)
        self.assertEqual(snap.config_version, 99)


class TestIpcErrorBeforeInit(unittest.TestCase):
    """5. Errors before first success leave fail-closed default in place."""

    def test_pre_init_error_stays_fail_closed(self):
        cache = ExecutorConfigCache()
        with patch.object(
            cache, "_fetch_via_ipc_blocking",
            side_effect=ConnectionError("socket missing"),
        ):
            cache._poll_once()
        self.assertFalse(cache.is_initialized())
        # Default fail-closed: shadow_mode True.
        self.assertTrue(cache.get().shadow_mode)


class TestLifecycleStopPolling(unittest.TestCase):
    """6. stop_polling() joins the daemon thread cleanly."""

    def test_stop_polling_joins_cleanly(self):
        cache = ExecutorConfigCache(poll_interval_s=0.05)
        with patch.object(
            cache, "_fetch_via_ipc_blocking",
            return_value=ExecutorRuntimeConfig(shadow_mode=True),
        ):
            cache.start_polling()
            time.sleep(0.05)
            self.assertTrue(cache.stop_polling(join_timeout=2.0))
        # Idempotent second call.
        self.assertTrue(cache.stop_polling(join_timeout=2.0))


class TestProviderLambda(unittest.TestCase):
    """7. shadow_mode_provider() always reads current snapshot."""

    def test_provider_reads_live(self):
        cache = ExecutorConfigCache()
        provider = cache.shadow_mode_provider()
        self.assertTrue(provider())  # initial fail-closed
        cache._inject_snapshot_for_tests(
            ExecutorRuntimeConfig(shadow_mode=False, config_version=1, fetched_at_ms=1)
        )
        self.assertFalse(provider())  # reads new snapshot
        cache._inject_snapshot_for_tests(
            ExecutorRuntimeConfig(shadow_mode=True, config_version=2, fetched_at_ms=2)
        )
        self.assertTrue(provider())  # reads back to True


class TestConcurrentReads(unittest.TestCase):
    """8. Concurrent reads under interleaving polls remain safe."""

    def test_concurrent_reads_atomic(self):
        cache = ExecutorConfigCache()
        good_a = ExecutorRuntimeConfig(shadow_mode=False, config_version=1, fetched_at_ms=1)
        good_b = ExecutorRuntimeConfig(shadow_mode=True, config_version=2, fetched_at_ms=2)
        cache._inject_snapshot_for_tests(good_a)
        results: list[bool] = []
        stop = threading.Event()

        def reader():
            while not stop.is_set():
                results.append(cache.get().shadow_mode)

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        # Flip snapshot a few times.
        for _ in range(50):
            cache._inject_snapshot_for_tests(good_a)
            cache._inject_snapshot_for_tests(good_b)
        stop.set()
        t.join(timeout=1.0)
        # Either bool is fine; the goal is no crash + only valid bool values.
        self.assertTrue(all(isinstance(v, bool) for v in results))


class TestMalformedResponse(unittest.TestCase):
    """9. Malformed/missing executor section → ValueError → fail-closed retain."""

    def test_missing_executor_raises(self):
        with self.assertRaises(ValueError):
            ExecutorConfigCache._parse_response({"config": {}, "version": 1})

    def test_non_dict_raises(self):
        with self.assertRaises(ValueError):
            ExecutorConfigCache._parse_response("not a dict")

    def test_malformed_falls_back_after_init(self):
        cache = ExecutorConfigCache()
        good = ExecutorRuntimeConfig(shadow_mode=False, config_version=5, fetched_at_ms=1)
        with patch.object(cache, "_fetch_via_ipc_blocking", return_value=good):
            cache._poll_once()
        self.assertFalse(cache.get().shadow_mode)
        with patch.object(
            cache, "_fetch_via_ipc_blocking",
            side_effect=ValueError("missing executor"),
        ):
            cache._poll_once()
        # Retained previous good shadow=False (post-init graceful degrade).
        self.assertFalse(cache.get().shadow_mode)


class TestModuleSingleton(unittest.TestCase):
    """10. get_executor_config_cache() returns the same instance."""

    def setUp(self):
        ecc_mod._reset_for_tests()

    def tearDown(self):
        ecc_mod._reset_for_tests()

    def test_singleton_dedup(self):
        a = get_executor_config_cache()
        b = get_executor_config_cache()
        self.assertIs(a, b)

    def test_reset_for_tests_drops_singleton(self):
        a = get_executor_config_cache()
        ecc_mod._reset_for_tests()
        b = get_executor_config_cache()
        self.assertIsNot(a, b)


if __name__ == "__main__":
    unittest.main()
