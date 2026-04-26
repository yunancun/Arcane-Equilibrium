"""
G3-08 Phase 2 — h_state_query_handler unit tests (real H1+H3).

Phase 1 covered the empty-shell stub (version=0, empty buckets). Phase 2
adds:
  9. env=0 + singletons present → still returns empty shell version=0.
 10. env=1 + STRATEGIST_AGENT not importable → empty shell fallback.
 11. env=1 + STRATEGIST_AGENT.h1_gate raises in get_h1_snapshot → drop key.
 12. env=1 + both H1+H3 snapshots present → h_states has both keys, version=1.
 13. env=1 + include=["h1"] → h_states has only h1.
 14. env=1 + include=["h3"] → h_states has only h3.
 15. env=1 + include=[] empty list → h_states empty, version=0 fallback.
 16. _safe_snapshot returns None for missing attribute / method.

Tests use a fake ``strategy_wiring.STRATEGIST_AGENT`` injected into
``sys.modules`` so we don't transitively boot the real agent stack.

Mac dev-only safe: no real socket / DB / engine needed.
"""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
import time
import types
import unittest
from unittest.mock import patch

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app.h_state_query_handler import build_h_state_full_response  # noqa: E402


# ── Helpers / 輔助 ──


class _FakeH1Gate:
    """Minimal stub matching H1ThoughtGate.get_h1_snapshot contract."""

    def __init__(self, snapshot=None, raises=None):
        self._snapshot = snapshot if snapshot is not None else {
            "total_decisions": 7,
            "ai_calls_allowed": 4,
            "budget_skip": 1,
            "complexity_skip": 1,
            "cooldown_skip": 1,
            "cooldown_dict_size": 3,
            "budget_remaining_pct": 42.0,
        }
        self._raises = raises

    def get_h1_snapshot(self):
        if self._raises is not None:
            raise self._raises
        return self._snapshot


class _FakeModelRouter:
    """Minimal stub matching ModelRouter.get_h3_snapshot contract."""

    def __init__(self, snapshot=None, raises=None):
        self._snapshot = snapshot if snapshot is not None else {
            "total_routes": 12,
            "l1_9b_count": 6,
            "l1_27b_count": 4,
            "l1_5_count": 1,
            "l2_count": 1,
            "budget_denied_count": 0,
            "l2_cache_hit": 2,
            "l2_cache_expired": 0,
            "l2_cache_stored": 1,
            "cache_size": 5,
        }
        self._raises = raises

    def get_h3_snapshot(self):
        if self._raises is not None:
            raise self._raises
        return self._snapshot


class _FakeStrategist:
    """Minimal stub mirroring strategy_wiring.STRATEGIST_AGENT shape."""

    def __init__(self, h1_gate=None, model_router=None):
        self._h1_gate = h1_gate
        self._model_router = model_router


def _install_fake_strategy_wiring(strategist):
    """Replace ``app.strategy_wiring`` in sys.modules with a stub.

    Returns the previous module (or ``None``) so caller can restore.
    """
    prev = sys.modules.get("app.strategy_wiring")
    fake_mod = types.ModuleType("app.strategy_wiring")
    fake_mod.STRATEGIST_AGENT = strategist
    sys.modules["app.strategy_wiring"] = fake_mod
    return prev


def _restore_strategy_wiring(prev):
    if prev is None:
        sys.modules.pop("app.strategy_wiring", None)
    else:
        sys.modules["app.strategy_wiring"] = prev


# ── 1-4. Phase 1 fallback — empty-shell shape (env=0) ──


class TestEmptyShellShape(unittest.TestCase):
    """Phase 1 + 9. env=0 (default) → fallback shape with version=0."""

    def setUp(self):
        # Make sure env is unset — Phase 1 fallback expected.
        self._prev_env = os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)

    def tearDown(self):
        if self._prev_env is not None:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._prev_env

    def test_returns_dict(self):
        result = build_h_state_full_response()
        self.assertIsInstance(result, dict)

    def test_has_all_canonical_keys(self):
        result = build_h_state_full_response()
        for key in ("version", "fetched_at_ms", "h_states", "agent_states"):
            self.assertIn(key, result, f"missing canonical key: {key}")

    def test_version_is_phase1_placeholder(self):
        # env=0 → fallback to phase 1 version 0.
        result = build_h_state_full_response()
        self.assertEqual(result["version"], 0)

    def test_fetched_at_ms_is_positive_int(self):
        before_ms = int(time.time() * 1000)
        result = build_h_state_full_response()
        after_ms = int(time.time() * 1000)
        self.assertIsInstance(result["fetched_at_ms"], int)
        self.assertGreater(result["fetched_at_ms"], 0)
        self.assertGreaterEqual(result["fetched_at_ms"], before_ms - 1000)
        self.assertLessEqual(result["fetched_at_ms"], after_ms + 1000)

    def test_h_states_is_empty_dict(self):
        result = build_h_state_full_response()
        self.assertIsInstance(result["h_states"], dict)
        self.assertEqual(result["h_states"], {})

    def test_agent_states_is_empty_dict(self):
        result = build_h_state_full_response()
        self.assertIsInstance(result["agent_states"], dict)
        self.assertEqual(result["agent_states"], {})


# ── 5. Include-filter API parity (env=0 fallback) ──


class TestIncludeFilterEnvOff(unittest.TestCase):
    """5. ``include`` accepted; env=0 → still empty shell."""

    def setUp(self):
        self._prev_env = os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)

    def tearDown(self):
        if self._prev_env is not None:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._prev_env

    def test_include_none_default(self):
        result = build_h_state_full_response(include=None)
        self.assertEqual(result["h_states"], {})
        self.assertEqual(result["agent_states"], {})

    def test_include_partial_filter_env_off(self):
        # Even with include filter, env=0 yields empty shell.
        result = build_h_state_full_response(include=["h1"])
        self.assertEqual(result["h_states"], {})
        self.assertEqual(result["version"], 0)

    def test_include_malformed_does_not_raise(self):
        result = build_h_state_full_response(include=["nonsense_module"])
        self.assertEqual(result["h_states"], {})

    def test_include_non_list_treated_as_none(self):
        # Non-list include → handler must defensively coerce to None.
        # Functionally identical to None (empty shell because env=0).
        result = build_h_state_full_response(include="not-a-list")  # type: ignore
        self.assertEqual(result["h_states"], {})
        self.assertNotIn("error", result)


# ── 6. No shared mutable state ──


class TestIndependentInvocations(unittest.TestCase):
    """6. Multiple calls return distinct dict objects (no aliasing)."""

    def setUp(self):
        self._prev_env = os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)

    def tearDown(self):
        if self._prev_env is not None:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._prev_env

    def test_dicts_are_independent(self):
        a = build_h_state_full_response()
        b = build_h_state_full_response()
        self.assertIsNot(a, b)
        self.assertIsNot(a["h_states"], b["h_states"])
        self.assertIsNot(a["agent_states"], b["agent_states"])
        a["h_states"]["bogus"] = 1
        self.assertEqual(b["h_states"], {})


# ── 7-8. Reverse IPC route registration in AIService ──


class TestReverseIPCRouteRegistered(unittest.TestCase):
    """7-8. ``query_h_state_full`` lives in AIService handler registry."""

    def test_route_registered_in_handlers(self):
        from app.ai_service import AIService

        service = AIService()
        methods = service.get_handler_methods()
        self.assertIn(
            "query_h_state_full",
            methods,
            "G3-08: query_h_state_full must always be registered "
            "(env-gate independent route).",
        )

    def test_route_ttl_short_enough_for_hot_path(self):
        from app.ai_service import AIService

        service = AIService()
        ttls = service.get_handler_ttls()
        self.assertIn("query_h_state_full", ttls)
        self.assertLessEqual(ttls["query_h_state_full"], 5.0)
        self.assertGreater(ttls["query_h_state_full"], 0.0)

    def test_dispatch_returns_empty_shell_when_env_off(self):
        # Env unset → expected fallback shape via dispatch.
        prev_env = os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        try:
            from app.ai_service import AIService

            service = AIService()
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(
                    service.dispatch("query_h_state_full", {})
                )
            finally:
                loop.close()
            self.assertEqual(result["version"], 0)
            self.assertEqual(result["h_states"], {})
            self.assertEqual(result["agent_states"], {})
            self.assertIn("fetched_at_ms", result)
            self.assertIn("_elapsed_ms", result)
        finally:
            if prev_env is not None:
                os.environ["OPENCLAW_H_STATE_GATEWAY"] = prev_env

    def test_dispatch_ignores_malformed_include(self):
        prev_env = os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        try:
            from app.ai_service import AIService

            service = AIService()
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(
                    service.dispatch("query_h_state_full", {"include": "h1"})
                )
            finally:
                loop.close()
            self.assertEqual(result.get("h_states"), {})
            self.assertNotIn("error", result)
        finally:
            if prev_env is not None:
                os.environ["OPENCLAW_H_STATE_GATEWAY"] = prev_env


# ── 9. env=0 + singletons present → still empty shell ──


class TestEnvOffWithSingletons(unittest.TestCase):
    """9. env=0 → empty shell even when STRATEGIST_AGENT is wired."""

    def test_env_off_yields_empty_shell_even_with_strategist(self):
        prev_env = os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(_FakeH1Gate(), _FakeModelRouter())
        )
        try:
            result = build_h_state_full_response()
            # Env disabled → short-circuit to empty shell, ignoring fakes.
            self.assertEqual(result["version"], 0)
            self.assertEqual(result["h_states"], {})
        finally:
            _restore_strategy_wiring(prev_sw)
            if prev_env is not None:
                os.environ["OPENCLAW_H_STATE_GATEWAY"] = prev_env


# ── 10. env=1 + strategy_wiring not importable → empty fallback ──


class TestEnvOnNoStrategyWiring(unittest.TestCase):
    """10. env=1 but STRATEGIST_AGENT singleton not wired → empty fallback."""

    def test_strategy_wiring_module_present_but_strategist_none(self):
        prev_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"
        # Inject a strategy_wiring module without STRATEGIST_AGENT — empty.
        prev_sw = sys.modules.get("app.strategy_wiring")
        bare_mod = types.ModuleType("app.strategy_wiring")
        # No STRATEGIST_AGENT attribute at all → getattr returns None.
        sys.modules["app.strategy_wiring"] = bare_mod
        try:
            result = build_h_state_full_response()
            # No buckets populated → version stays at fallback 0.
            self.assertEqual(result["version"], 0)
            self.assertEqual(result["h_states"], {})
        finally:
            if prev_sw is None:
                sys.modules.pop("app.strategy_wiring", None)
            else:
                sys.modules["app.strategy_wiring"] = prev_sw
            if prev_env is None:
                os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
            else:
                os.environ["OPENCLAW_H_STATE_GATEWAY"] = prev_env


# ── 11. env=1 + H1 snapshot raises → drop key ──


class TestSnapshotRaiseDropsKey(unittest.TestCase):
    """11. Snapshot exception → defensively drop bucket key, no crash."""

    def test_h1_raises_drops_h1_bucket(self):
        prev_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(raises=RuntimeError("h1 boom")),
                _FakeModelRouter(),
            )
        )
        try:
            result = build_h_state_full_response()
            # H1 raised → its key dropped; H3 still present.
            self.assertIn("h3", result["h_states"])
            self.assertNotIn("h1", result["h_states"])
            # Version still 1 because at least h3 populated.
            self.assertEqual(result["version"], 1)
        finally:
            _restore_strategy_wiring(prev_sw)
            if prev_env is None:
                os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
            else:
                os.environ["OPENCLAW_H_STATE_GATEWAY"] = prev_env

    def test_both_raise_drops_both_keys_version_zero(self):
        prev_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(raises=RuntimeError("h1 boom")),
                _FakeModelRouter(raises=RuntimeError("h3 boom")),
            )
        )
        try:
            result = build_h_state_full_response()
            # Both raised → empty h_states + version stays at 0.
            self.assertEqual(result["h_states"], {})
            self.assertEqual(result["version"], 0)
        finally:
            _restore_strategy_wiring(prev_sw)
            if prev_env is None:
                os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
            else:
                os.environ["OPENCLAW_H_STATE_GATEWAY"] = prev_env


# ── 12-14. env=1 + real H1+H3 snapshots → version=1 ──


class TestEnvOnRealSnapshots(unittest.TestCase):
    """12-14. env=1 + STRATEGIST_AGENT wired → real H1+H3 snapshots."""

    def setUp(self):
        self._prev_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"
        self._prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(_FakeH1Gate(), _FakeModelRouter())
        )

    def tearDown(self):
        _restore_strategy_wiring(self._prev_sw)
        if self._prev_env is None:
            os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        else:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._prev_env

    def test_both_buckets_populated_version_1(self):
        result = build_h_state_full_response()
        self.assertEqual(result["version"], 1)
        self.assertIn("h1", result["h_states"])
        self.assertIn("h3", result["h_states"])
        # Spot-check H1 schema fidelity.
        self.assertEqual(result["h_states"]["h1"]["total_decisions"], 7)
        # Spot-check H3 schema fidelity.
        self.assertEqual(result["h_states"]["h3"]["total_routes"], 12)
        self.assertEqual(result["h_states"]["h3"]["cache_size"], 5)
        # Agent bucket still empty (Phase 4 fills it).
        self.assertEqual(result["agent_states"], {})

    def test_include_h1_only(self):
        result = build_h_state_full_response(include=["h1"])
        self.assertIn("h1", result["h_states"])
        self.assertNotIn("h3", result["h_states"])
        self.assertEqual(result["version"], 1)

    def test_include_h3_only(self):
        result = build_h_state_full_response(include=["h3"])
        self.assertNotIn("h1", result["h_states"])
        self.assertIn("h3", result["h_states"])
        self.assertEqual(result["version"], 1)

    def test_include_unknown_keys_silently_ignored(self):
        # Phase 3+ adds h2/h4/h5 — including them now is harmless.
        result = build_h_state_full_response(include=["h1", "h2", "h4"])
        self.assertIn("h1", result["h_states"])
        self.assertNotIn("h3", result["h_states"])
        self.assertNotIn("h2", result["h_states"])  # not yet wired


# ── 15. include=[] → empty buckets ──


class TestIncludeEmptyList(unittest.TestCase):
    """15. ``include=[]`` → no buckets requested; version stays at 0."""

    def test_empty_include_skips_all(self):
        prev_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(_FakeH1Gate(), _FakeModelRouter())
        )
        try:
            result = build_h_state_full_response(include=[])
            self.assertEqual(result["h_states"], {})
            self.assertEqual(result["version"], 0)
        finally:
            _restore_strategy_wiring(prev_sw)
            if prev_env is None:
                os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
            else:
                os.environ["OPENCLAW_H_STATE_GATEWAY"] = prev_env


# ── 16. _safe_snapshot defensive paths ──


class TestSafeSnapshotDefensive(unittest.TestCase):
    """16. _safe_snapshot returns None on missing attribute / method."""

    def test_missing_attribute_returns_none(self):
        from app.h_state_query_handler import _safe_snapshot

        class _Empty:
            pass

        self.assertIsNone(_safe_snapshot(_Empty(), "_h1_gate", "get_h1_snapshot"))

    def test_missing_method_returns_none(self):
        from app.h_state_query_handler import _safe_snapshot

        class _StubGate:
            pass

        class _Parent:
            _h1_gate = _StubGate()

        self.assertIsNone(_safe_snapshot(_Parent(), "_h1_gate", "get_h1_snapshot"))

    def test_non_callable_method_returns_none(self):
        from app.h_state_query_handler import _safe_snapshot

        class _StubGate:
            get_h1_snapshot = "not-callable"

        class _Parent:
            _h1_gate = _StubGate()

        self.assertIsNone(_safe_snapshot(_Parent(), "_h1_gate", "get_h1_snapshot"))

    def test_non_dict_return_value_dropped(self):
        from app.h_state_query_handler import _safe_snapshot

        class _StubGate:
            def get_h1_snapshot(self):
                return [1, 2, 3]  # not a dict — dropped

        class _Parent:
            _h1_gate = _StubGate()

        self.assertIsNone(_safe_snapshot(_Parent(), "_h1_gate", "get_h1_snapshot"))


if __name__ == "__main__":
    unittest.main()
