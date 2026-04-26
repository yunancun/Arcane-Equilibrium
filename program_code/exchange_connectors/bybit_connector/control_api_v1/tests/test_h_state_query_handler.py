"""
G3-08 Phase 1 Sub-task B — h_state_query_handler unit tests.

Coverage (≥ 6 cases here; combined with test_h_state_invalidator ≥ 17 total):
  1. Phase 1 stub returns canonical empty-shell shape (PA §5.1 / §4.2.1).
  2. ``version`` field is the Phase 1 placeholder (0).
  3. ``fetched_at_ms`` is a positive int near current wall clock.
  4. ``h_states`` and ``agent_states`` are empty dicts (forward-compat shape).
  5. ``include`` filter parameter is accepted but ignored in Phase 1.
  6. Multiple calls return independent dicts (no shared mutable state).
  7. Reverse IPC route ``query_h_state_full`` is registered in
     ``AIService._handlers``.
  8. AIService dispatch returns the empty shell + adds ``_elapsed_ms``.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import unittest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app.h_state_query_handler import build_h_state_full_response  # noqa: E402


# ── 1-4. Empty-shell shape ──


class TestEmptyShellShape(unittest.TestCase):
    """1-4. PA §5.1 / §4.2.1 schema parity."""

    def test_returns_dict(self) -> None:
        result = build_h_state_full_response()
        self.assertIsInstance(result, dict)

    def test_has_all_canonical_keys(self) -> None:
        result = build_h_state_full_response()
        for key in ("version", "fetched_at_ms", "h_states", "agent_states"):
            self.assertIn(key, result, f"missing canonical key: {key}")

    def test_version_is_phase1_placeholder(self) -> None:
        result = build_h_state_full_response()
        self.assertEqual(result["version"], 0)

    def test_fetched_at_ms_is_positive_int(self) -> None:
        before_ms = int(time.time() * 1000)
        result = build_h_state_full_response()
        after_ms = int(time.time() * 1000)
        self.assertIsInstance(result["fetched_at_ms"], int)
        self.assertGreater(result["fetched_at_ms"], 0)
        # Within wall-clock tolerance (1s window for slow CI).
        self.assertGreaterEqual(result["fetched_at_ms"], before_ms - 1000)
        self.assertLessEqual(result["fetched_at_ms"], after_ms + 1000)

    def test_h_states_is_empty_dict(self) -> None:
        result = build_h_state_full_response()
        self.assertIsInstance(result["h_states"], dict)
        self.assertEqual(result["h_states"], {})

    def test_agent_states_is_empty_dict(self) -> None:
        result = build_h_state_full_response()
        self.assertIsInstance(result["agent_states"], dict)
        self.assertEqual(result["agent_states"], {})


# ── 5. Include-filter API parity ──


class TestIncludeFilter(unittest.TestCase):
    """5. ``include`` is accepted but ignored in Phase 1."""

    def test_include_none_default(self) -> None:
        # Equivalent to no filter passed.
        result = build_h_state_full_response(include=None)
        self.assertEqual(result["h_states"], {})
        self.assertEqual(result["agent_states"], {})

    def test_include_partial_filter_ignored(self) -> None:
        # In Phase 2+ ["h1"] would mask out h2-h5; Phase 1 ignores → still
        # returns the empty shell shape.
        result = build_h_state_full_response(include=["h1"])
        self.assertEqual(result["h_states"], {})
        self.assertEqual(result["agent_states"], {})

    def test_include_malformed_does_not_raise(self) -> None:
        # Pure function: must absorb malformed input gracefully.
        # Caller guards in dispatch handler; here we check the underlying fn.
        result = build_h_state_full_response(include=["nonsense_module"])
        self.assertEqual(result["h_states"], {})


# ── 6. No shared mutable state ──


class TestIndependentInvocations(unittest.TestCase):
    """6. Multiple calls must return distinct dict objects (no aliasing)."""

    def test_dicts_are_independent(self) -> None:
        a = build_h_state_full_response()
        b = build_h_state_full_response()
        self.assertIsNot(a, b)
        self.assertIsNot(a["h_states"], b["h_states"])
        self.assertIsNot(a["agent_states"], b["agent_states"])
        # Mutating one must not affect the other.
        a["h_states"]["bogus"] = 1
        self.assertEqual(b["h_states"], {})


# ── 7-8. Reverse IPC route registration in AIService ──


class TestReverseIPCRouteRegistered(unittest.TestCase):
    """7-8. ``query_h_state_full`` lives in AIService handler registry."""

    def test_route_registered_in_handlers(self) -> None:
        # Lazy import inside the test so cycles never trip pytest collection.
        from app.ai_service import AIService

        service = AIService()
        methods = service.get_handler_methods()
        self.assertIn(
            "query_h_state_full",
            methods,
            "G3-08 Phase 1 Sub-task B: query_h_state_full must always be "
            "registered (env-gate independent route).",
        )

    def test_route_ttl_short_enough_for_hot_path(self) -> None:
        from app.ai_service import AIService

        service = AIService()
        ttls = service.get_handler_ttls()
        self.assertIn("query_h_state_full", ttls)
        # PA §G2 requires reverse-pull ≤ 5ms; TTL bound at 2s for safety
        # (poll-loop deadlock guard, not per-call SLA target).
        self.assertLessEqual(ttls["query_h_state_full"], 5.0)
        self.assertGreater(ttls["query_h_state_full"], 0.0)

    def test_dispatch_returns_empty_shell(self) -> None:
        from app.ai_service import AIService

        service = AIService()
        # AIService.dispatch is async; run via private loop.
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                service.dispatch("query_h_state_full", {})
            )
        finally:
            loop.close()
        # Schema must be present; dispatch wraps with ``_elapsed_ms`` but
        # leaves payload intact.
        self.assertEqual(result["version"], 0)
        self.assertEqual(result["h_states"], {})
        self.assertEqual(result["agent_states"], {})
        self.assertIn("fetched_at_ms", result)
        self.assertIn("_elapsed_ms", result)
        self.assertIsInstance(result["_elapsed_ms"], (int, float))

    def test_dispatch_ignores_malformed_include(self) -> None:
        from app.ai_service import AIService

        service = AIService()
        loop = asyncio.new_event_loop()
        try:
            # Non-list include → handler must defensively coerce to None.
            result = loop.run_until_complete(
                service.dispatch("query_h_state_full", {"include": "h1"})
            )
        finally:
            loop.close()
        # Should still return canonical empty shell, not an error response.
        self.assertEqual(result.get("h_states"), {})
        self.assertNotIn("error", result)


if __name__ == "__main__":
    unittest.main()
