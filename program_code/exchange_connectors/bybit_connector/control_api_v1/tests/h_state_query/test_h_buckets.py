from .common import *  # noqa: F401,F403

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


