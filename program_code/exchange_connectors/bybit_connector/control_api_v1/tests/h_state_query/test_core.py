from .common import *  # noqa: F401,F403

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


