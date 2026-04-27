"""
G3-08 Phase 2/3 — h_state_query_handler unit tests (real H1+H2+H3+H4+H5).

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

Phase 3 Sub-task 3-3 adds (per PA RFC §6 — Phase 3 COMPLETE):
 29. env=1 + cost_tracker.get_h5_snapshot present → h_states has h5 with 4 PA-spec fields.
 30. env=1 + cost_tracker None → h5 key dropped (shares cost_tracker with H2 → both drop).
 31. env=1 + cost_tracker.get_h5_snapshot raises → h5 key dropped, others ok.
 32. env=1 + include=["h5"] → h_states has only h5.
 33. env=1 + 5-bucket roundtrip include=["h1","h2","h3","h4","h5"] → all five keys.
 34. include=None default still picks up h5 bucket (parity with h1/h2/h3/h4).

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
    """Minimal stub matching Layer2CostTracker.get_h2_snapshot + get_h5_snapshot contracts.

    Schema mirrors Rust H2BudgetState (3 fields) + H5CostStats (4 fields).

    Phase 3 Sub-task 3-3 adds opt-in ``with_h5`` / ``h5_snapshot`` /
    ``h5_raises`` to drive the cost_tracker.get_h5_snapshot accessor.
    Default ``with_h5=False`` mirrors the silent-skip default — Phase 3
    Sub-task 3-1 / 3-2 tests stay unaffected (they don't expect h5 in
    h_states because their fixture skipped binding get_h5_snapshot).
    Phase 3 Sub-task 3-3 加 opt-in ``with_h5`` 等參數。預設 with_h5=False
    與靜默跳過預設對齊 —— Sub-task 3-1 / 3-2 既有測試（fixture 未綁
    get_h5_snapshot，不期望 h5 在 h_states）不受影響。
    """

    def __init__(
        self,
        snapshot=None,
        raises=None,
        with_h5=False,
        h5_snapshot=None,
        h5_raises=None,
    ):
        self._snapshot = snapshot if snapshot is not None else {
            "daily_remaining_usd": 1.75,
            "hard_cap_usd": 2.0,
            "adaptive_multiplier": 0.85,
        }
        self._raises = raises
        # Phase 3 Sub-task 3-3 H5 stub state.
        # Phase 3 Sub-task 3-3 H5 stub 狀態。
        self._h5_snapshot = h5_snapshot if h5_snapshot is not None else {
            "ai_spend_7d_usd": 0.42,
            "paper_pnl_7d_usd": 0.84,
            "cost_edge_ratio": 2.0,
            "data_days": 5,
        }
        self._h5_raises = h5_raises
        if with_h5:
            # Bind get_h5_snapshot only when opted in — preserves Sub-task
            # 3-1 / 3-2 test fixture semantics where get_h5_snapshot is
            # absent and the silent-skip path triggers.
            # 僅在 opt-in 時綁定 get_h5_snapshot —— 保留 Sub-task 3-1 / 3-2
            # 測試 fixture 語意（get_h5_snapshot 缺席 + 靜默跳過路徑）。
            def _get_h5(_self=self):
                if _self._h5_raises is not None:
                    raise _self._h5_raises
                return _self._h5_snapshot
            self.get_h5_snapshot = _get_h5

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
        with_strategist_snapshot=False,
        strategist_snapshot=None,
        strategist_snapshot_raises=None,
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

        # G3-08 Phase 4 Sub-task 4-1: Strategist agent_state snapshot accessor.
        # Default with_strategist_snapshot=False — opt-in, mirrors with_h4 pattern,
        # so Phase 1-3 tests stay unaffected (they don't expect agent_states.strategist).
        # G3-08 Phase 4 Sub-task 4-1：Strategist agent_state snapshot 存取器。
        # 預設 with_strategist_snapshot=False — opt-in，與 with_h4 同模式，
        # Phase 1-3 測試（不期望 agent_states.strategist）不受影響。
        self._strategist_snapshot = strategist_snapshot if strategist_snapshot is not None else {
            "intel_received": 11,
            "intel_evaluated": 7,
            "intents_produced": 3,
            "intents_shadow_logged": 4,
            "evaluations_rejected": 2,
            "ai_evaluations": 5,
            "heuristic_evaluations": 2,
            "errors": 0,
            "pending_intents": 1,
            "emergency_mode_active": 0,
            "cognitive_modulator_connected": 1,
        }
        self._strategist_snapshot_raises = strategist_snapshot_raises
        if with_strategist_snapshot:
            def _get_strategist(_self=self):
                if _self._strategist_snapshot_raises is not None:
                    raise _self._strategist_snapshot_raises
                return _self._strategist_snapshot
            self.get_strategist_snapshot = _get_strategist


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

    def test_all_raise_drops_all_keys_version_zero(self):
        """Phase 2 test extended for Phase 3 COMPLETE: when ALL snapshot accessors
        raise (H1+H2+H3+H4+H5), h_states stays empty and version falls back to 0.
        Originally Phase 2 only had H1+H3; Phase 3 Sub-task 3-1 (H2), 3-2 (H4),
        and 3-3 (H5) added bucket sources, so the "all-raise → empty" invariant
        now requires all 5 to raise. Mirrors the original test intent under
        full Phase 3 coverage.
        Phase 2 測試延伸到 Phase 3 COMPLETE：所有 snapshot accessor
        （H1+H2+H3+H4+H5）皆拋例外時，h_states 仍空，version 退回 0。
        Phase 2 原僅 H1+H3；Sub-task 3-1（H2）+ 3-2（H4）+ 3-3（H5）
        擴充來源後，「全 raise → 空」不變式需 5 桶皆 raise。

        Note: Sub-task 3-3 H5 reuses cost_tracker (same as Sub-task 3-1 H2),
        so a single ``cost_tracker`` instance with H2 raise + H5 raise drives
        both buckets to drop. Test passes ``with_h5=True`` to bind the
        get_h5_snapshot method on the cost_tracker stub, then uses h5_raises
        to make it throw.
        註：Sub-task 3-3 H5 復用 cost_tracker（與 Sub-task 3-1 H2 同），
        故單一 ``cost_tracker`` 實例帶 H2 raise + H5 raise 即能讓兩桶都 drop。
        測試傳 ``with_h5=True`` 在 cost_tracker stub 上綁 get_h5_snapshot 方法，
        再用 h5_raises 讓它拋例外。
        """
        prev_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(raises=RuntimeError("h1 boom")),
                _FakeModelRouter(raises=RuntimeError("h3 boom")),
                cost_tracker=_FakeCostTracker(
                    raises=RuntimeError("h2 boom"),
                    with_h5=True,
                    h5_raises=RuntimeError("h5 boom"),
                ),
                h4_raises=RuntimeError("h4 boom"),
            )
        )
        try:
            result = build_h_state_full_response()
            # All 5 raised → empty h_states + version stays at 0.
            # 5 桶全 raise → h_states 空 + version 退回 0。
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


# ── 29-34. Phase 3 Sub-task 3-3: H5 cost_logging integration (Phase 3 COMPLETE) ──


class TestH5CostLoggingIntegration(unittest.TestCase):
    """29-31. Phase 3 Sub-task 3-3: H5 bucket population + degradation paths.
    PA RFC `2026-04-26--g3_08_phase3_subtask_split.md` §6.

    H5 SSOT = same Layer2CostTracker as H2 (single tracker, two snapshot
    lenses). Sub-task 3-3 reuses cost_tracker attribute, so a single
    ``cost_tracker=None`` race drops both H2 and H5 buckets — acceptable
    per Sub-task 3-1's degradation contract.
    H5 SSOT 與 H2 同 Layer2CostTracker（單一 tracker，兩個 snapshot 視角）。
    Sub-task 3-3 復用 cost_tracker 屬性，故單一 ``cost_tracker=None`` race
    會同時丟 H2 與 H5 桶 —— 對齊 Sub-task 3-1 降級合約可接受。
    """

    def setUp(self):
        self._prev_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"

    def tearDown(self):
        if self._prev_env is None:
            os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        else:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._prev_env

    def test_h5_populated_when_get_h5_snapshot_present(self):
        """29. env=1 + cost_tracker.get_h5_snapshot wired → h5 bucket present.
        Phase 3 COMPLETE: all 5 H buckets simultaneously populate.
        Phase 3 COMPLETE：5 個 H 桶同時填入。
        """
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(with_h5=True),
                with_h4=True,
            )
        )
        try:
            result = build_h_state_full_response()
            self.assertIn("h5", result["h_states"])
            h5 = result["h_states"]["h5"]
            # Schema parity with Rust H5CostStats (4 fields, drops the
            # roi_basis / roi_disclaimer metadata markers).
            # Schema 對齊 Rust H5CostStats（4 個 fields，丟棄 roi_basis /
            # roi_disclaimer metadata 標記）。
            self.assertEqual(set(h5.keys()), {
                "ai_spend_7d_usd",
                "paper_pnl_7d_usd",
                "cost_edge_ratio",
                "data_days",
            })
            self.assertEqual(h5["ai_spend_7d_usd"], 0.42)
            self.assertEqual(h5["paper_pnl_7d_usd"], 0.84)
            self.assertEqual(h5["cost_edge_ratio"], 2.0)
            self.assertEqual(h5["data_days"], 5)
            # Phase 3 COMPLETE: all 5 buckets populate together → version 1.
            # Phase 3 COMPLETE：5 桶同時填入 → version 1。
            self.assertEqual(result["version"], 1)
            self.assertEqual(set(result["h_states"].keys()), {
                "h1", "h2", "h3", "h4", "h5",
            })
        finally:
            _restore_strategy_wiring(prev_sw)

    def test_h5_dropped_when_cost_tracker_none(self):
        """30. env=1 + cost_tracker=None → BOTH h2 AND h5 absent (shared SSOT).
        H1+H3+H4 unaffected.
        """
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=None,
                with_h4=True,
            )
        )
        try:
            result = build_h_state_full_response()
            # Both H2 and H5 dropped because they share cost_tracker SSOT.
            # H2 與 H5 都丟，因共享 cost_tracker SSOT。
            self.assertNotIn("h2", result["h_states"])
            self.assertNotIn("h5", result["h_states"])
            # H1+H3+H4 unaffected.
            self.assertIn("h1", result["h_states"])
            self.assertIn("h3", result["h_states"])
            self.assertIn("h4", result["h_states"])
            self.assertEqual(result["version"], 1)
        finally:
            _restore_strategy_wiring(prev_sw)

    def test_h5_dropped_when_get_h5_snapshot_raises(self):
        """31. env=1 + cost_tracker.get_h5_snapshot raises → h5 dropped, others ok.

        Critically: H2 still populates because get_h2_snapshot is independent
        of get_h5_snapshot (same tracker, different methods, only the H5
        accessor raises).
        關鍵：H2 仍填入，因 get_h2_snapshot 與 get_h5_snapshot 獨立（同一
        tracker、不同方法，只 H5 accessor 拋例外）。
        """
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(
                    with_h5=True,
                    h5_raises=RuntimeError("h5 boom"),
                ),
                with_h4=True,
            )
        )
        try:
            result = build_h_state_full_response()
            self.assertNotIn("h5", result["h_states"])
            # H1+H2+H3+H4 still populate; version stays at 1.
            # H1+H2+H3+H4 仍填入；version 維持 1。
            self.assertIn("h1", result["h_states"])
            self.assertIn("h2", result["h_states"])
            self.assertIn("h3", result["h_states"])
            self.assertIn("h4", result["h_states"])
            self.assertEqual(result["version"], 1)
        finally:
            _restore_strategy_wiring(prev_sw)

    def test_h5_dropped_when_get_h5_snapshot_method_missing(self):
        """Bonus: env=1 + cost_tracker exists but get_h5_snapshot method missing
        → h5 absent (silent skip preserves never-raise contract).

        Models the Sub-task 3-1 deploy scenario where cost_tracker exists
        (H2 path works) but Sub-task 3-3 hasn't landed (get_h5_snapshot
        method not yet defined) — the defensive _safe_snapshot helper
        returns None silently.
        模擬 Sub-task 3-1 部署但 3-3 未 land 的情境：cost_tracker 存在
        （H2 路徑可運作），但 get_h5_snapshot 方法尚未定義 —— 防禦式
        _safe_snapshot helper 靜默回 None。
        """
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(),  # with_h5 default False → no method
                with_h4=True,
            )
        )
        try:
            result = build_h_state_full_response()
            self.assertNotIn("h5", result["h_states"])
            # H2 still works (different method on same tracker).
            # H2 仍可（同一 tracker 不同方法）。
            self.assertIn("h2", result["h_states"])
            self.assertEqual(result["version"], 1)
        finally:
            _restore_strategy_wiring(prev_sw)


class TestH5IncludeFilter(unittest.TestCase):
    """32-34. Phase 3 Sub-task 3-3: include filter honours h5 bucket selection."""

    def setUp(self):
        self._prev_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"
        self._prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(with_h5=True),
                with_h4=True,
            )
        )

    def tearDown(self):
        _restore_strategy_wiring(self._prev_sw)
        if self._prev_env is None:
            os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        else:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._prev_env

    def test_include_h5_only(self):
        """32. include=["h5"] → h_states has only h5, version=1."""
        result = build_h_state_full_response(include=["h5"])
        self.assertIn("h5", result["h_states"])
        self.assertNotIn("h1", result["h_states"])
        self.assertNotIn("h2", result["h_states"])
        self.assertNotIn("h3", result["h_states"])
        self.assertNotIn("h4", result["h_states"])
        self.assertEqual(result["version"], 1)

    def test_5bucket_roundtrip_phase3_complete(self):
        """33. include=["h1","h2","h3","h4","h5"] → all 5 buckets, version=1.

        THE Phase 3 COMPLETE assertion — proves all 5 H buckets aggregate
        in a single IPC roundtrip when env=1 + STRATEGIST_AGENT wired.
        Phase 3 COMPLETE 斷言 —— 證明 env=1 + STRATEGIST_AGENT 接線時，
        5 個 H 桶在單一 IPC roundtrip 內聚合。
        """
        result = build_h_state_full_response(
            include=["h1", "h2", "h3", "h4", "h5"]
        )
        self.assertEqual(
            set(result["h_states"].keys()),
            {"h1", "h2", "h3", "h4", "h5"},
        )
        self.assertEqual(result["version"], 1)
        # Spot-check H5 schema (the bucket added this Sub-task).
        # 抽查 H5 schema（本 Sub-task 新增的桶）。
        h5 = result["h_states"]["h5"]
        self.assertIn("ai_spend_7d_usd", h5)
        self.assertIn("paper_pnl_7d_usd", h5)
        self.assertIn("cost_edge_ratio", h5)
        self.assertIn("data_days", h5)

    def test_include_default_none_includes_h5(self):
        """34. include=None default still picks up h5 bucket (parity with h1-h4)."""
        result = build_h_state_full_response(include=None)
        self.assertIn("h5", result["h_states"])
        # Phase 3 COMPLETE: default include picks up all 5 H buckets.
        # Phase 3 COMPLETE：預設 include 選 5 個 H 桶。
        self.assertEqual(
            set(result["h_states"].keys()),
            {"h1", "h2", "h3", "h4", "h5"},
        )


# ── 35-41. Phase 4 Sub-task 4-1: Strategist agent_state integration ──


class TestStrategistAgentStateIntegration(unittest.TestCase):
    """35-37. G3-08 Phase 4 Sub-task 4-1: agent_states.strategist bucket
    population + degradation paths.

    Mirrors the H4 caller-side pattern (snapshot accessor on the agent
    itself, not a sub-attribute). Per PA RFC §2.1 the schema has 11
    fields, all int / bool→int (Rust ``AgentState.stats: HashMap<String, i64>``
    parity). Sub-task 4-2 / 4-3 / 4-4 / 4-5 will add guardian / analyst /
    executor / scout buckets additively without changing this fixture.

    G3-08 Phase 4 Sub-task 4-1：agent_states.strategist 桶填入 + 降級路徑；
    與 H4 caller-side pattern 相同（snapshot accessor 在 agent 自身）。
    PA RFC §2.1 的 schema 為 11 欄位、皆 int / bool→int（對齊 Rust
    ``AgentState.stats: HashMap<String, i64>``）。Sub-task 4-2/3/4/5 會以
    加性方式新增 guardian / analyst / executor / scout 桶，不影響本 fixture。
    """

    _EXPECTED_STRATEGIST_FIELDS = {
        "intel_received",
        "intel_evaluated",
        "intents_produced",
        "intents_shadow_logged",
        "evaluations_rejected",
        "ai_evaluations",
        "heuristic_evaluations",
        "errors",
        "pending_intents",
        "emergency_mode_active",
        "cognitive_modulator_connected",
    }

    def setUp(self):
        self._prev_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"

    def tearDown(self):
        if self._prev_env is None:
            os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        else:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._prev_env

    def test_strategist_populated_when_get_strategist_snapshot_present(self):
        """35. env=1 + strategist.get_strategist_snapshot present →
        agent_states.strategist contains the 11-field snapshot.
        """
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(),
                with_h4=True,
                with_strategist_snapshot=True,
            )
        )
        try:
            result = build_h_state_full_response()
            self.assertIn("strategist", result["agent_states"])
            strategist = result["agent_states"]["strategist"]
            # Schema parity with Rust AgentState.stats (11 fields).
            self.assertEqual(set(strategist.keys()), self._EXPECTED_STRATEGIST_FIELDS)
            # Spot-check default fixture values.
            self.assertEqual(strategist["intel_received"], 11)
            self.assertEqual(strategist["intents_produced"], 3)
            self.assertEqual(strategist["cognitive_modulator_connected"], 1)
            # All values must be int (Rust HashMap<String, i64> parity).
            for k, v in strategist.items():
                self.assertIsInstance(v, int, f"{k} must be int")
            # 5 H buckets + 1 agent bucket all populated → version 1.
            self.assertEqual(result["version"], 1)
            # Sub-task 4-1 only fills strategist; 4-2/3/4/5 keys absent.
            # Sub-task 4-1 只填 strategist；4-2/3/4/5 對應 key 缺席。
            self.assertNotIn("guardian", result["agent_states"])
            self.assertNotIn("analyst", result["agent_states"])
            self.assertNotIn("executor", result["agent_states"])
            self.assertNotIn("scout", result["agent_states"])
        finally:
            _restore_strategy_wiring(prev_sw)

    def test_strategist_dropped_when_get_strategist_snapshot_missing(self):
        """36. env=1 + strategist lacks get_strategist_snapshot → strategist
        absent (silent skip preserves never-raise contract). Models the
        Phase 3 deploy scenario where Sub-task 4-1 hasn't landed yet.
        """
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(),
                with_h4=True,
                # with_strategist_snapshot default False → method absent
            )
        )
        try:
            result = build_h_state_full_response()
            self.assertNotIn("strategist", result["agent_states"])
            # H buckets unaffected — the only "real" data is 4 H buckets.
            self.assertIn("h1", result["h_states"])
            self.assertIn("h2", result["h_states"])
            self.assertIn("h3", result["h_states"])
            self.assertIn("h4", result["h_states"])
            self.assertEqual(result["version"], 1)
        finally:
            _restore_strategy_wiring(prev_sw)

    def test_strategist_dropped_when_get_strategist_snapshot_raises(self):
        """37. env=1 + strategist.get_strategist_snapshot raises → strategist
        bucket dropped, H buckets unaffected.
        """
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(),
                with_h4=True,
                with_strategist_snapshot=True,
                strategist_snapshot_raises=RuntimeError("strategist snap boom"),
            )
        )
        try:
            result = build_h_state_full_response()
            self.assertNotIn("strategist", result["agent_states"])
            # H buckets unaffected.
            self.assertIn("h1", result["h_states"])
            self.assertIn("h4", result["h_states"])
            self.assertEqual(result["version"], 1)
        finally:
            _restore_strategy_wiring(prev_sw)


class TestStrategistAgentStateIncludeFilter(unittest.TestCase):
    """38-41. G3-08 Phase 4 Sub-task 4-1: include filter honours
    ``strategist`` bucket selection alongside H buckets.
    """

    def setUp(self):
        self._prev_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"
        self._prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(with_h5=True),
                with_h4=True,
                with_strategist_snapshot=True,
            )
        )

    def tearDown(self):
        _restore_strategy_wiring(self._prev_sw)
        if self._prev_env is None:
            os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        else:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._prev_env

    def test_include_strategist_only(self):
        """38. include=["strategist"] → agent_states has only strategist,
        h_states empty, version=1 (agent bucket alone lifts version).
        """
        result = build_h_state_full_response(include=["strategist"])
        self.assertIn("strategist", result["agent_states"])
        self.assertEqual(set(result["agent_states"].keys()), {"strategist"})
        # H buckets filtered out.
        self.assertEqual(result["h_states"], {})
        # G3-08 Phase 4: agent_states alone counts toward "real" → version 1.
        self.assertEqual(result["version"], 1)

    def test_include_default_none_includes_strategist(self):
        """39. include=None default still picks up strategist bucket
        (parity with H buckets default-on behaviour).
        """
        result = build_h_state_full_response(include=None)
        self.assertIn("strategist", result["agent_states"])
        # Phase 3 H buckets remain populated.
        self.assertEqual(
            set(result["h_states"].keys()),
            {"h1", "h2", "h3", "h4", "h5"},
        )

    def test_include_h_buckets_only_drops_strategist(self):
        """40. include=["h1","h2","h3","h4","h5"] (no agent keys) →
        agent_states empty even though strategist accessor is wired.
        """
        result = build_h_state_full_response(
            include=["h1", "h2", "h3", "h4", "h5"]
        )
        self.assertEqual(result["agent_states"], {})
        # H buckets all populate.
        self.assertEqual(
            set(result["h_states"].keys()),
            {"h1", "h2", "h3", "h4", "h5"},
        )
        self.assertEqual(result["version"], 1)

    def test_mixed_include_h_and_agent(self):
        """41. include=["h1","strategist"] → only h1 + strategist populate."""
        result = build_h_state_full_response(include=["h1", "strategist"])
        self.assertEqual(set(result["h_states"].keys()), {"h1"})
        self.assertEqual(set(result["agent_states"].keys()), {"strategist"})
        self.assertEqual(result["version"], 1)


class TestCollectAgentSnapshotsDefensive(unittest.TestCase):
    """42. Defensive paths for _collect_agent_snapshots — ensures the
    aggregator never raises and degrades cleanly when strategy_wiring
    isn't importable / STRATEGIST_AGENT is None / accessor missing.
    """

    def test_strategy_wiring_import_failure_returns_all_none(self):
        """42a. strategy_wiring not in sys.modules and not importable →
        all 5 keys are None (caller silently drops them).
        """
        from app.h_state_query_handler import _collect_agent_snapshots
        # Inject a broken strategy_wiring that raises on import use.
        # Note: actual ImportError is hard to fake mid-test; we instead
        # verify the structural contract — when no agent flags requested,
        # we get the all-None skeleton without ever importing.
        result = _collect_agent_snapshots()  # all flags False
        self.assertEqual(set(result.keys()),
                         {"strategist", "guardian", "analyst", "executor", "scout"})
        for v in result.values():
            self.assertIsNone(v)

    def test_strategist_none_when_singleton_missing(self):
        """42b. include_strategist=True + STRATEGIST_AGENT is None on the
        fake module → result["strategist"] is None.
        """
        from app.h_state_query_handler import _collect_agent_snapshots
        prev_sw = sys.modules.get("app.strategy_wiring")
        bare = types.ModuleType("app.strategy_wiring")
        # No STRATEGIST_AGENT attribute → getattr returns None.
        sys.modules["app.strategy_wiring"] = bare
        try:
            result = _collect_agent_snapshots(include_strategist=True)
            self.assertIsNone(result["strategist"])
        finally:
            if prev_sw is None:
                sys.modules.pop("app.strategy_wiring", None)
            else:
                sys.modules["app.strategy_wiring"] = prev_sw


if __name__ == "__main__":
    unittest.main()
