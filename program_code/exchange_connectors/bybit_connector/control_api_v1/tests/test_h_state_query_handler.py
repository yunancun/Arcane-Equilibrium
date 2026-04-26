"""
G3-08 Phase 2/3 — h_state_query_handler unit tests (real H1+H2+H3+H4).

Phase 1 covered the empty-shell stub (version=0, empty buckets). Phase 2
added:
  9. env=0 + singletons present → still returns empty shell version=0.
 10. env=1 + STRATEGIST_AGENT not importable → empty shell fallback.
 11. env=1 + STRATEGIST_AGENT.h1_gate raises in get_h1_snapshot → drop key.
 12. env=1 + both H1+H3 snapshots present → h_states has both keys, version=1.
 13. env=1 + include=["h1"] → h_states has only h1.
 14. env=1 + include=["h3"] → h_states has only h3.
 15. env=1 + include=[] empty list → h_states empty, version=0 fallback.
 16. _safe_snapshot returns None for missing attribute / method.

Phase 3 Sub-task 3-1 adds (per PA RFC `2026-04-26--g3_08_phase3_subtask_split.md` §4):
 17. env=1 + cost_tracker present → h_states has h2 with 3 PA-spec fields.
 18. env=1 + cost_tracker None → h2 key dropped (graceful degradation).
 19. env=1 + cost_tracker.get_h2_snapshot raises → h2 key dropped.
 20. env=1 + include=["h2"] → h_states has only h2.
 21. env=1 + 3-bucket roundtrip include=["h1", "h2", "h3"] → all three keys.

Phase 3 Sub-task 3-2 adds (per PA RFC §5):
 22. env=1 + strategist.get_h4_snapshot present → h_states has h4 with 2 PA-spec fields.
 23. env=1 + strategist.get_h4_snapshot missing → h4 key dropped (silent skip).
 24. env=1 + strategist.get_h4_snapshot raises → h4 key dropped.
 25. env=1 + include=["h4"] → h_states has only h4.
 26. env=1 + 4-bucket roundtrip include=["h1", "h2", "h3", "h4"] → all four keys.
 27. include=None default still picks up h4 bucket (parity with h1/h2/h3).
 28. _safe_snapshot_self returns None for missing / non-callable / non-dict / raise.

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


class _FakeCostTracker:
    """Minimal stub matching Layer2CostTracker.get_h2_snapshot contract.
    Schema mirrors Rust H2BudgetState (3 fields)."""

    def __init__(self, snapshot=None, raises=None):
        self._snapshot = snapshot if snapshot is not None else {
            "daily_remaining_usd": 1.75,
            "hard_cap_usd": 2.0,
            "adaptive_multiplier": 0.85,
        }
        self._raises = raises

    def get_h2_snapshot(self):
        if self._raises is not None:
            raise self._raises
        return self._snapshot


class _FakeStrategist:
    """Minimal stub mirroring strategy_wiring.STRATEGIST_AGENT shape.

    Phase 3 Sub-task 3-1 adds ``cost_tracker`` (public attribute, no
    underscore prefix — matches BaseAgent.__init__ contract).
    Phase 3 Sub-task 3-2 adds opt-in ``with_h4`` / ``h4_snapshot`` /
    ``h4_raises`` to drive the strategist-self ``get_h4_snapshot()``
    accessor (caller-side counters, distinct from H1/H3 sub-attribute
    pattern). Default ``with_h4=False`` mirrors ``cost_tracker=None``
    silent-skip default — Phase 2 / Sub-task 3-1 tests stay unaffected.
    Phase 3 Sub-task 3-2 加 opt-in ``with_h4`` 等參數。預設 with_h4=False
    與 cost_tracker=None 預設靜默跳過對齊 — Phase 2 / Sub-task 3-1 測試
    不受影響。
    """

    def __init__(
        self,
        h1_gate=None,
        model_router=None,
        cost_tracker=None,
        with_h4=False,
        h4_snapshot=None,
        h4_raises=None,
    ):
        self._h1_gate = h1_gate
        self._model_router = model_router
        # Public attribute (no underscore) — mirrors BaseAgent.cost_tracker.
        # 公開屬性（無底線）—— 鏡射 BaseAgent.cost_tracker。
        self.cost_tracker = cost_tracker
        # Phase 3 Sub-task 3-2: H4 snapshot is on the strategist itself.
        # Default with_h4=False — opt in so existing Phase 2 tests
        # (which expect h_states without h4) keep their semantics.
        # Phase 3 Sub-task 3-2：H4 snapshot 在 strategist 自身。
        # 預設 with_h4=False — opt in，避免 Phase 2 測試（預期 h_states 無 h4）
        # 語義被破壞。
        self._h4_snapshot = h4_snapshot if h4_snapshot is not None else {
            "validation_fail": 3,
            "validation_pass": 17,
        }
        self._h4_raises = h4_raises
        if with_h4:
            def _get(_self=self):
                if _self._h4_raises is not None:
                    raise _self._h4_raises
                return _self._h4_snapshot
            # Bind as instance method
            self.get_h4_snapshot = _get


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
        """Phase 2 test extended for Phase 3: when ALL snapshot accessors raise
        (H1+H2+H3+H4), h_states stays empty and version falls back to 0.
        Originally Phase 2 only had H1+H3; Phase 3 Sub-task 3-1 (H2) and 3-2 (H4)
        added bucket sources, so the "all-raise → empty" invariant now requires
        all 4 to raise. Mirrors the original test intent under expanded coverage.
        Phase 2 測試延伸到 Phase 3：所有 snapshot accessor（H1+H2+H3+H4）皆拋例外時，
        h_states 仍空，version 退回 0。Phase 2 原僅 H1+H3；Sub-task 3-1（H2）+
        3-2（H4）擴充來源後，「全 raise → 空」不變式需 4 桶皆 raise。
        """
        prev_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(raises=RuntimeError("h1 boom")),
                _FakeModelRouter(raises=RuntimeError("h3 boom")),
                cost_tracker=_FakeCostTracker(raises=RuntimeError("h2 boom")),
                h4_raises=RuntimeError("h4 boom"),
            )
        )
        try:
            result = build_h_state_full_response()
            # All raised → empty h_states + version stays at 0.
            # 全 raise → h_states 空 + version 退回 0。
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


# ── 17-21. Phase 3 Sub-task 3-1: H2 budget integration ──


class TestH2BudgetIntegration(unittest.TestCase):
    """17-19. Phase 3 Sub-task 3-1: H2 bucket population + degradation paths.
    PA RFC `2026-04-26--g3_08_phase3_subtask_split.md` §4。
    """

    def setUp(self):
        self._prev_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"

    def tearDown(self):
        if self._prev_env is None:
            os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        else:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._prev_env

    def test_h2_populated_when_cost_tracker_present(self):
        """17. env=1 + cost_tracker wired → h2 bucket present with PA-spec fields."""
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(),
            )
        )
        try:
            result = build_h_state_full_response()
            self.assertIn("h2", result["h_states"])
            h2 = result["h_states"]["h2"]
            # Schema parity with Rust H2BudgetState (3 fields).
            self.assertEqual(set(h2.keys()), {
                "daily_remaining_usd",
                "hard_cap_usd",
                "adaptive_multiplier",
            })
            self.assertEqual(h2["daily_remaining_usd"], 1.75)
            self.assertEqual(h2["hard_cap_usd"], 2.0)
            self.assertEqual(h2["adaptive_multiplier"], 0.85)
            # 3 buckets all populated → version 1.
            self.assertEqual(result["version"], 1)
            self.assertIn("h1", result["h_states"])
            self.assertIn("h3", result["h_states"])
        finally:
            _restore_strategy_wiring(prev_sw)

    def test_h2_dropped_when_cost_tracker_none(self):
        """18. env=1 + cost_tracker=None → h2 absent; H1+H3 still present, version=1."""
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(_FakeH1Gate(), _FakeModelRouter(), cost_tracker=None)
        )
        try:
            result = build_h_state_full_response()
            self.assertNotIn("h2", result["h_states"])
            # H1+H3 unaffected.
            self.assertIn("h1", result["h_states"])
            self.assertIn("h3", result["h_states"])
            self.assertEqual(result["version"], 1)
        finally:
            _restore_strategy_wiring(prev_sw)

    def test_h2_dropped_when_get_h2_snapshot_raises(self):
        """19. env=1 + cost_tracker.get_h2_snapshot raises → h2 dropped, H1+H3 ok."""
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(raises=RuntimeError("h2 boom")),
            )
        )
        try:
            result = build_h_state_full_response()
            self.assertNotIn("h2", result["h_states"])
            # H1+H3 still populate; version stays at 1 because at least one
            # bucket was real.
            self.assertIn("h1", result["h_states"])
            self.assertIn("h3", result["h_states"])
            self.assertEqual(result["version"], 1)
        finally:
            _restore_strategy_wiring(prev_sw)


class TestH2IncludeFilter(unittest.TestCase):
    """20-21. Phase 3 Sub-task 3-1: include filter honours h2 bucket selection."""

    def setUp(self):
        self._prev_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"
        self._prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(),
            )
        )

    def tearDown(self):
        _restore_strategy_wiring(self._prev_sw)
        if self._prev_env is None:
            os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        else:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._prev_env

    def test_include_h2_only(self):
        """20. include=["h2"] → h_states has only h2, version=1."""
        result = build_h_state_full_response(include=["h2"])
        self.assertIn("h2", result["h_states"])
        self.assertNotIn("h1", result["h_states"])
        self.assertNotIn("h3", result["h_states"])
        self.assertEqual(result["version"], 1)

    def test_3bucket_roundtrip(self):
        """21. include=["h1", "h2", "h3"] → all 3 buckets present, version=1."""
        result = build_h_state_full_response(include=["h1", "h2", "h3"])
        self.assertEqual(set(result["h_states"].keys()), {"h1", "h2", "h3"})
        self.assertEqual(result["version"], 1)
        # Spot-check H2 schema.
        h2 = result["h_states"]["h2"]
        self.assertIn("daily_remaining_usd", h2)
        self.assertIn("hard_cap_usd", h2)
        self.assertIn("adaptive_multiplier", h2)

    def test_include_default_none_includes_h2(self):
        """include=None default still picks up h2 bucket (parity with h1/h3)."""
        result = build_h_state_full_response(include=None)
        self.assertIn("h2", result["h_states"])


# ── 22-28. Phase 3 Sub-task 3-2: H4 validator integration ──


class TestH4ValidatorIntegration(unittest.TestCase):
    """22-24. Phase 3 Sub-task 3-2: H4 bucket population + degradation paths.
    PA RFC `2026-04-26--g3_08_phase3_subtask_split.md` §5.

    H4 differs from H1/H2/H3 in that the snapshot accessor lives directly
    on the strategist (caller-side counters) rather than on a sub-attribute,
    because ``h4_validator.validate_ai_output`` is a stateless pure function.
    H4 與 H1/H2/H3 不同：snapshot accessor 在 strategist 自身（caller-side
    計數），非子屬性，因 ``h4_validator`` 為 stateless 純函式。
    """

    def setUp(self):
        self._prev_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"

    def tearDown(self):
        if self._prev_env is None:
            os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        else:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._prev_env

    def test_h4_populated_when_strategist_has_get_h4_snapshot(self):
        """22. env=1 + strategist.get_h4_snapshot present → h4 bucket present."""
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(),
                with_h4=True,
            )
        )
        try:
            result = build_h_state_full_response()
            self.assertIn("h4", result["h_states"])
            h4 = result["h_states"]["h4"]
            # Schema parity with Rust H4ValidationStats (2 fields).
            self.assertEqual(set(h4.keys()), {
                "validation_fail",
                "validation_pass",
            })
            self.assertEqual(h4["validation_fail"], 3)
            self.assertEqual(h4["validation_pass"], 17)
            # 4 buckets all populated → version 1.
            self.assertEqual(result["version"], 1)
            self.assertIn("h1", result["h_states"])
            self.assertIn("h2", result["h_states"])
            self.assertIn("h3", result["h_states"])
        finally:
            _restore_strategy_wiring(prev_sw)

    def test_h4_dropped_when_get_h4_snapshot_missing(self):
        """23. env=1 + strategist lacks get_h4_snapshot → h4 absent (silent skip).

        Models the Phase 2 deploy scenario where Sub-task 3-2 hasn't landed yet:
        strategist.get_h4_snapshot doesn't exist → silent skip preserves the
        never-raise contract.
        模擬 Phase 2 部署但 Sub-task 3-2 未 land 的情境：strategist 無
        get_h4_snapshot → 靜默跳過保 never-raise 合約。
        """
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(),
                # with_h4 default False → no get_h4_snapshot bound
            )
        )
        try:
            result = build_h_state_full_response()
            self.assertNotIn("h4", result["h_states"])
            # H1+H2+H3 unaffected.
            self.assertIn("h1", result["h_states"])
            self.assertIn("h2", result["h_states"])
            self.assertIn("h3", result["h_states"])
            self.assertEqual(result["version"], 1)
        finally:
            _restore_strategy_wiring(prev_sw)

    def test_h4_dropped_when_get_h4_snapshot_raises(self):
        """24. env=1 + strategist.get_h4_snapshot raises → h4 dropped, others ok."""
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(),
                with_h4=True,
                h4_raises=RuntimeError("h4 boom"),
            )
        )
        try:
            result = build_h_state_full_response()
            self.assertNotIn("h4", result["h_states"])
            # H1+H2+H3 still populate; version stays at 1.
            self.assertIn("h1", result["h_states"])
            self.assertIn("h2", result["h_states"])
            self.assertIn("h3", result["h_states"])
            self.assertEqual(result["version"], 1)
        finally:
            _restore_strategy_wiring(prev_sw)


class TestH4IncludeFilter(unittest.TestCase):
    """25-27. Phase 3 Sub-task 3-2: include filter honours h4 bucket selection."""

    def setUp(self):
        self._prev_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"
        self._prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(),
                with_h4=True,
            )
        )

    def tearDown(self):
        _restore_strategy_wiring(self._prev_sw)
        if self._prev_env is None:
            os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        else:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._prev_env

    def test_include_h4_only(self):
        """25. include=["h4"] → h_states has only h4, version=1."""
        result = build_h_state_full_response(include=["h4"])
        self.assertIn("h4", result["h_states"])
        self.assertNotIn("h1", result["h_states"])
        self.assertNotIn("h2", result["h_states"])
        self.assertNotIn("h3", result["h_states"])
        self.assertEqual(result["version"], 1)

    def test_4bucket_roundtrip(self):
        """26. include=["h1","h2","h3","h4"] → all 4 buckets present, version=1."""
        result = build_h_state_full_response(
            include=["h1", "h2", "h3", "h4"]
        )
        self.assertEqual(
            set(result["h_states"].keys()),
            {"h1", "h2", "h3", "h4"},
        )
        self.assertEqual(result["version"], 1)
        # Spot-check H4 schema.
        h4 = result["h_states"]["h4"]
        self.assertIn("validation_fail", h4)
        self.assertIn("validation_pass", h4)

    def test_include_default_none_includes_h4(self):
        """27. include=None default still picks up h4 bucket (parity with h1/h2/h3)."""
        result = build_h_state_full_response(include=None)
        self.assertIn("h4", result["h_states"])


class TestSafeSnapshotSelfDefensive(unittest.TestCase):
    """28. _safe_snapshot_self defensive paths (sibling of TestSafeSnapshotDefensive)."""

    def test_missing_method_returns_none(self):
        from app.h_state_query_handler import _safe_snapshot_self

        class _Empty:
            pass

        self.assertIsNone(_safe_snapshot_self(_Empty(), "get_h4_snapshot"))

    def test_non_callable_method_returns_none(self):
        from app.h_state_query_handler import _safe_snapshot_self

        class _Stub:
            get_h4_snapshot = "not-callable"

        self.assertIsNone(_safe_snapshot_self(_Stub(), "get_h4_snapshot"))

    def test_non_dict_return_value_dropped(self):
        from app.h_state_query_handler import _safe_snapshot_self

        class _Stub:
            def get_h4_snapshot(self):
                return [1, 2, 3]  # not a dict — dropped

        self.assertIsNone(_safe_snapshot_self(_Stub(), "get_h4_snapshot"))

    def test_method_raise_returns_none(self):
        from app.h_state_query_handler import _safe_snapshot_self

        class _Stub:
            def get_h4_snapshot(self):
                raise RuntimeError("snapshot bug")

        self.assertIsNone(_safe_snapshot_self(_Stub(), "get_h4_snapshot"))

    def test_valid_dict_passes_through(self):
        from app.h_state_query_handler import _safe_snapshot_self

        class _Stub:
            def get_h4_snapshot(self):
                return {"validation_fail": 1, "validation_pass": 2}

        result = _safe_snapshot_self(_Stub(), "get_h4_snapshot")
        self.assertEqual(result, {"validation_fail": 1, "validation_pass": 2})


if __name__ == "__main__":
    unittest.main()
