"""
G3-08 Phase 1 Sub-task B — h_state_invalidator unit tests.

Coverage (≥ 12 cases here; combined with test_h_state_query_handler ≥ 17):
  1. is_gateway_enabled strict "1" check (true/false/missing/typo).
  2. init_h_state_invalidator no-op when env disabled.
  3. init_h_state_invalidator constructs singleton when env enabled.
  4. init_h_state_invalidator constructs when force=True (test override).
  5. Multiple init calls return the same instance (singleton dedup).
  6. invalidate_async no-op when singleton not initialised.
  7. invalidate_async dispatches via daemon thread (factory injected mock).
  8. invalidate_async never raises even if factory raises (outer guard).
  9. Daemon thread silences IPC connect failures (DEBUG log only).
 10. Stats counters increment correctly (attempted / dispatched / failed).
 11. _reset_for_tests drops singleton + new instance after re-init.
 12. Concurrent init calls do not race (multi-thread → single instance).
 13. invalidate_async on disabled env-gate stays no-op (no thread spawn).

Mac dev-only: uses mock IPC client factory throughout — no real socket needed.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import unittest
from typing import Any
from unittest.mock import patch

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app import h_state_invalidator as inv_mod  # noqa: E402
from app.h_state_invalidator import (  # noqa: E402
    HStateInvalidator,
    init_h_state_invalidator,
    invalidate_async,
    is_gateway_enabled,
    get_invalidator,
)


# ── Helper: in-memory mock IPC client ──


class _MockIPCClient:
    """Captures connect/call/disconnect invocations for assertions."""

    def __init__(self) -> None:
        self.connect_calls = 0
        self.call_args: list[tuple[str, dict | None, float | None]] = []
        self.disconnect_calls = 0
        self.connect_should_raise: BaseException | None = None
        self.call_should_raise: BaseException | None = None

    async def connect(self) -> bool:
        self.connect_calls += 1
        if self.connect_should_raise is not None:
            raise self.connect_should_raise
        return True

    async def call(
        self,
        method: str,
        params: dict | None = None,
        timeout: float | None = None,
    ) -> dict:
        self.call_args.append((method, params, timeout))
        if self.call_should_raise is not None:
            raise self.call_should_raise
        return {"ack": True}

    async def disconnect(self) -> None:
        self.disconnect_calls += 1


def _make_factory(client: _MockIPCClient | None = None) -> tuple[Any, _MockIPCClient]:
    """Return (factory_callable, the_mock_client_used)."""
    if client is None:
        client = _MockIPCClient()
    factory_calls = {"n": 0}

    def factory() -> _MockIPCClient:
        factory_calls["n"] += 1
        # Each invalidate spawns one client. Phase 1 expects per-call clients;
        # tests inspect the original ``client`` for state since factory
        # returns same instance (cheaper for unit test verification).
        return client

    return factory, client


def _wait_until(predicate, timeout_s: float = 2.0, sleep_s: float = 0.01) -> bool:
    """Poll ``predicate()`` until True or timeout."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(sleep_s)
    return predicate()


# ── 1. Env-gate semantics ──


class TestEnvGate(unittest.TestCase):
    """1. Strict ``"1"`` env check semantics."""

    def setUp(self) -> None:
        # Snapshot env so each test starts clean.
        self._orig_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")

    def tearDown(self) -> None:
        if self._orig_env is None:
            os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        else:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._orig_env
        inv_mod._reset_for_tests()

    def test_missing_env_var_disabled(self) -> None:
        os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        self.assertFalse(is_gateway_enabled())

    def test_env_var_one_enabled(self) -> None:
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"
        self.assertTrue(is_gateway_enabled())

    def test_env_var_zero_disabled(self) -> None:
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "0"
        self.assertFalse(is_gateway_enabled())

    def test_env_var_true_string_disabled(self) -> None:
        # Strict equality with "1" — "true" must NOT enable. Documented
        # behaviour mirroring ExecutorConfigCache pattern.
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "true"
        self.assertFalse(is_gateway_enabled())

    def test_env_var_empty_string_disabled(self) -> None:
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = ""
        self.assertFalse(is_gateway_enabled())


# ── 2-5. Singleton init behaviour ──


class TestSingletonInit(unittest.TestCase):
    """2-5. Init-time singleton construction + dedup."""

    def setUp(self) -> None:
        self._orig_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
        inv_mod._reset_for_tests()

    def tearDown(self) -> None:
        if self._orig_env is None:
            os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        else:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._orig_env
        inv_mod._reset_for_tests()

    def test_init_no_op_when_disabled(self) -> None:
        os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        result = init_h_state_invalidator()
        self.assertIsNone(result)
        self.assertIsNone(get_invalidator())

    def test_init_constructs_when_enabled(self) -> None:
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"
        result = init_h_state_invalidator()
        self.assertIsNotNone(result)
        self.assertIsInstance(result, HStateInvalidator)
        self.assertIs(get_invalidator(), result)

    def test_init_force_overrides_disabled_env(self) -> None:
        # Useful for unit tests + dry-run scenarios.
        os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        result = init_h_state_invalidator(force=True)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, HStateInvalidator)

    def test_init_dedup_returns_same_instance(self) -> None:
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"
        a = init_h_state_invalidator()
        b = init_h_state_invalidator()
        c = init_h_state_invalidator()
        self.assertIs(a, b)
        self.assertIs(b, c)

    def test_reset_for_tests_drops_singleton(self) -> None:
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"
        a = init_h_state_invalidator()
        inv_mod._reset_for_tests()
        self.assertIsNone(get_invalidator())
        b = init_h_state_invalidator()
        self.assertIsNotNone(b)
        self.assertIsNot(a, b)


# ── 6. invalidate_async no-op when uninitialised ──


class TestInvalidateAsyncNoOp(unittest.TestCase):
    """6 + 13. ``invalidate_async`` no-op paths."""

    def setUp(self) -> None:
        self._orig_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
        inv_mod._reset_for_tests()

    def tearDown(self) -> None:
        if self._orig_env is None:
            os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        else:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._orig_env
        inv_mod._reset_for_tests()

    def test_no_op_when_not_initialised(self) -> None:
        # No init called → invalidate_async must be silent no-op.
        with patch.object(threading, "Thread") as mock_thread:
            invalidate_async("test_reason")
            mock_thread.assert_not_called()

    def test_no_op_when_env_disabled_and_not_initialised(self) -> None:
        os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        # init returns None (no singleton constructed).
        init_h_state_invalidator()
        with patch.object(threading, "Thread") as mock_thread:
            invalidate_async("test_reason")
            mock_thread.assert_not_called()

    def test_invalidate_async_returns_none(self) -> None:
        # Even on the no-op path, function must return ``None`` (never raise).
        result = invalidate_async("anything")
        self.assertIsNone(result)


# ── 7-9. Fire-and-forget dispatch ──


class TestFireAndForgetDispatch(unittest.TestCase):
    """7-9. Daemon thread dispatch + IPC error swallowing."""

    def setUp(self) -> None:
        self._orig_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"
        inv_mod._reset_for_tests()

    def tearDown(self) -> None:
        if self._orig_env is None:
            os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        else:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._orig_env
        inv_mod._reset_for_tests()

    def test_invalidate_dispatches_via_thread(self) -> None:
        factory, mock_client = _make_factory()
        init_h_state_invalidator(ipc_client_factory=factory)
        invalidate_async("budget_skip")
        # Wait for the daemon thread to complete one full cycle.
        ok = _wait_until(lambda: mock_client.connect_calls >= 1)
        self.assertTrue(ok, "daemon thread did not call connect within 2s")
        # Verify the IPC method + payload + cleanup.
        self.assertEqual(mock_client.connect_calls, 1)
        self.assertEqual(len(mock_client.call_args), 1)
        method, params, timeout = mock_client.call_args[0]
        self.assertEqual(method, "invalidate_h_state")
        self.assertEqual(params, {"reason": "budget_skip"})
        self.assertEqual(timeout, 2.0)
        # Wait for disconnect to ensure cleanup ran.
        ok = _wait_until(lambda: mock_client.disconnect_calls >= 1)
        self.assertTrue(ok, "daemon thread did not call disconnect within 2s")

    def test_invalidate_swallows_connect_error(self) -> None:
        client = _MockIPCClient()
        client.connect_should_raise = ConnectionRefusedError("socket missing")
        factory, _ = _make_factory(client=client)
        init_h_state_invalidator(ipc_client_factory=factory)
        # MUST NOT raise — fire-and-forget contract.
        invalidate_async("budget_skip")
        # Wait for failure to be recorded in stats.
        inv = get_invalidator()
        self.assertIsNotNone(inv)
        ok = _wait_until(lambda: inv.stats_snapshot()["failed"] >= 1)
        self.assertTrue(ok, "failure was not recorded in stats")
        self.assertEqual(client.connect_calls, 1)
        self.assertEqual(len(client.call_args), 0)  # never reached call

    def test_invalidate_swallows_call_error(self) -> None:
        client = _MockIPCClient()
        client.call_should_raise = TimeoutError("ipc timeout")
        factory, _ = _make_factory(client=client)
        init_h_state_invalidator(ipc_client_factory=factory)
        invalidate_async("h5_claude_call")
        inv = get_invalidator()
        self.assertIsNotNone(inv)
        ok = _wait_until(lambda: inv.stats_snapshot()["failed"] >= 1)
        self.assertTrue(ok, "TimeoutError was not silenced into stats")
        # Even on call error, disconnect should still run (finally block).
        ok = _wait_until(lambda: client.disconnect_calls >= 1)
        self.assertTrue(ok, "disconnect did not run after call error")

    def test_invalidate_async_outer_guard_silent_on_thread_failure(self) -> None:
        # Simulate thread-spawn failure (e.g. resource exhaustion). The outer
        # guard in ``invalidate_async`` must keep the function silent.
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"
        init_h_state_invalidator(ipc_client_factory=lambda: _MockIPCClient())
        with patch.object(
            HStateInvalidator,
            "invalidate",
            side_effect=RuntimeError("thread spawn failed"),
        ):
            # Must NOT raise even though the inner ``invalidate`` does.
            try:
                invalidate_async("any_reason")
            except Exception as exc:  # pragma: no cover — would fail test
                self.fail(f"invalidate_async raised: {exc!r}")


# ── 10. Stats counters ──


class TestStatsCounters(unittest.TestCase):
    """10. Stats counter correctness across attempts/dispatches/failures."""

    def setUp(self) -> None:
        self._orig_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"
        inv_mod._reset_for_tests()

    def tearDown(self) -> None:
        if self._orig_env is None:
            os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        else:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._orig_env
        inv_mod._reset_for_tests()

    def test_attempted_increments_on_each_call(self) -> None:
        factory, _ = _make_factory()
        inv = init_h_state_invalidator(ipc_client_factory=factory)
        self.assertIsNotNone(inv)
        for _ in range(5):
            invalidate_async("x")
        # ``attempted`` increments synchronously inside ``invalidate``.
        ok = _wait_until(lambda: inv.stats_snapshot()["attempted"] == 5)
        self.assertTrue(ok)

    def test_dispatched_increments_on_success(self) -> None:
        factory, mock_client = _make_factory()
        inv = init_h_state_invalidator(ipc_client_factory=factory)
        invalidate_async("x")
        ok = _wait_until(lambda: inv.stats_snapshot()["dispatched"] == 1)
        self.assertTrue(ok)
        self.assertEqual(inv.stats_snapshot()["failed"], 0)

    def test_failed_increments_on_error(self) -> None:
        client = _MockIPCClient()
        client.call_should_raise = TimeoutError("boom")
        factory, _ = _make_factory(client=client)
        inv = init_h_state_invalidator(ipc_client_factory=factory)
        invalidate_async("x")
        ok = _wait_until(lambda: inv.stats_snapshot()["failed"] == 1)
        self.assertTrue(ok)
        self.assertEqual(inv.stats_snapshot()["dispatched"], 0)


# ── 12. Concurrent init thread-safety ──


class TestConcurrentInit(unittest.TestCase):
    """12. Multi-thread init must not race; one instance survives."""

    def setUp(self) -> None:
        self._orig_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"
        inv_mod._reset_for_tests()

    def tearDown(self) -> None:
        if self._orig_env is None:
            os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        else:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._orig_env
        inv_mod._reset_for_tests()

    def test_concurrent_init_returns_single_instance(self) -> None:
        results: list[HStateInvalidator] = []
        results_lock = threading.Lock()

        def worker() -> None:
            inv = init_h_state_invalidator()
            if inv is not None:
                with results_lock:
                    results.append(inv)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=2.0)
        # All threads should have constructed (env=1) but received the same
        # singleton.
        self.assertEqual(len(results), 20)
        first = results[0]
        for inv in results[1:]:
            self.assertIs(inv, first)


if __name__ == "__main__":
    unittest.main()
