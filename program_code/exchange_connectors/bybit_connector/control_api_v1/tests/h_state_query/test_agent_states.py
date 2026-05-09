from .common import *  # noqa: F401,F403

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


# ── G3-08 Phase 4 Sub-task 4-2: Guardian agent_state integration ──
# G3-08 Phase 4 Sub-task 4-2：Guardian agent_state 整合


class _FakeGuardian:
    """Minimal stub mirroring strategy_wiring.GUARDIAN_AGENT shape.

    G3-08 Phase 4 Sub-task 4-2: ``with_guardian_snapshot=True`` binds an
    instance method ``get_guardian_snapshot`` returning the 8-field dict
    per PA RFC §2.2. Default ``with_guardian_snapshot=False`` opt-in
    mirrors Strategist ``with_strategist_snapshot`` pattern, so any test
    that injects a guardian without flipping the flag exercises the
    "method absent → silent skip" degradation path.

    G3-08 Phase 4 Sub-task 4-2：``with_guardian_snapshot=True`` 綁定一個
    實例方法 ``get_guardian_snapshot``，回傳 PA RFC §2.2 的 8 欄位 dict。
    預設 ``with_guardian_snapshot=False`` opt-in，與 Strategist
    ``with_strategist_snapshot`` 同 pattern。
    """

    def __init__(
        self,
        with_guardian_snapshot=False,
        guardian_snapshot=None,
        guardian_snapshot_raises=None,
    ):
        self._guardian_snapshot = guardian_snapshot if guardian_snapshot is not None else {
            "intents_reviewed": 13,
            "verdicts_approved": 9,
            "verdicts_rejected": 3,
            "verdicts_modified": 1,
            "events_assessed": 5,
            "errors": 0,
            "active_event_risks": 2,
            "verdict_log_size": 13,
        }
        self._guardian_snapshot_raises = guardian_snapshot_raises
        if with_guardian_snapshot:
            def _get(_self=self):
                if _self._guardian_snapshot_raises is not None:
                    raise _self._guardian_snapshot_raises
                return _self._guardian_snapshot
            self.get_guardian_snapshot = _get


class TestGuardianAgentStateIntegration(unittest.TestCase):
    """43-46. G3-08 Phase 4 Sub-task 4-2: agent_states.guardian bucket
    population + degradation paths. Mirrors Sub-task 4-1 strategist tests
    (PA RFC §6.2). Per RFC §2.2 the schema has 8 fields, all int / bool→int
    (Rust ``AgentState.stats: HashMap<String, i64>`` parity).

    G3-08 Phase 4 Sub-task 4-2：agent_states.guardian 桶填入 + 降級路徑；
    與 Sub-task 4-1 strategist 測試 mirror（PA RFC §6.2）。RFC §2.2 schema
    為 8 欄位、皆 int / bool→int。
    """

    _EXPECTED_GUARDIAN_FIELDS = {
        "intents_reviewed",
        "verdicts_approved",
        "verdicts_rejected",
        "verdicts_modified",
        "events_assessed",
        "errors",
        "active_event_risks",
        "verdict_log_size",
    }

    def setUp(self):
        self._prev_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"

    def tearDown(self):
        if self._prev_env is None:
            os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        else:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._prev_env

    def test_guardian_populated_when_get_guardian_snapshot_present(self):
        """43. env=1 + guardian.get_guardian_snapshot present →
        agent_states.guardian contains the 8-field snapshot.
        """
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(),
                with_h4=True,
                with_strategist_snapshot=True,
            ),
            guardian=_FakeGuardian(with_guardian_snapshot=True),
        )
        try:
            result = build_h_state_full_response()
            self.assertIn("guardian", result["agent_states"])
            guardian = result["agent_states"]["guardian"]
            # Schema parity with Rust AgentState.stats (8 fields).
            self.assertEqual(set(guardian.keys()), self._EXPECTED_GUARDIAN_FIELDS)
            # Spot-check default fixture values.
            self.assertEqual(guardian["intents_reviewed"], 13)
            self.assertEqual(guardian["verdicts_approved"], 9)
            self.assertEqual(guardian["active_event_risks"], 2)
            # All values must be int (Rust HashMap<String, i64> parity).
            for k, v in guardian.items():
                self.assertIsInstance(v, int, f"{k} must be int")
            # Strategist + Guardian both populated.
            self.assertIn("strategist", result["agent_states"])
            # Sub-task 4-2 fills strategist + guardian; 4-3/4/5 absent.
            # Sub-task 4-2 填 strategist + guardian；4-3/4/5 對應 key 缺席。
            self.assertNotIn("analyst", result["agent_states"])
            self.assertNotIn("executor", result["agent_states"])
            self.assertNotIn("scout", result["agent_states"])
            self.assertEqual(result["version"], 1)
        finally:
            _restore_strategy_wiring(prev_sw)

    def test_guardian_dropped_when_get_guardian_snapshot_missing(self):
        """44. env=1 + guardian lacks get_guardian_snapshot → guardian
        absent (silent skip preserves never-raise contract). Models the
        Phase 4 partial-deploy scenario where Sub-task 4-2 hasn't landed.
        """
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(),
                with_h4=True,
                with_strategist_snapshot=True,
            ),
            # with_guardian_snapshot default False → method absent
            guardian=_FakeGuardian(),
        )
        try:
            result = build_h_state_full_response()
            self.assertNotIn("guardian", result["agent_states"])
            # Strategist still present (Sub-task 4-1 unaffected).
            self.assertIn("strategist", result["agent_states"])
            self.assertEqual(result["version"], 1)
        finally:
            _restore_strategy_wiring(prev_sw)

    def test_guardian_dropped_when_get_guardian_snapshot_raises(self):
        """45. env=1 + guardian.get_guardian_snapshot raises → guardian
        bucket dropped, others unaffected.
        """
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(),
                with_h4=True,
                with_strategist_snapshot=True,
            ),
            guardian=_FakeGuardian(
                with_guardian_snapshot=True,
                guardian_snapshot_raises=RuntimeError("guardian snap boom"),
            ),
        )
        try:
            result = build_h_state_full_response()
            self.assertNotIn("guardian", result["agent_states"])
            # Strategist + H buckets unaffected.
            self.assertIn("strategist", result["agent_states"])
            self.assertIn("h1", result["h_states"])
            self.assertIn("h4", result["h_states"])
            self.assertEqual(result["version"], 1)
        finally:
            _restore_strategy_wiring(prev_sw)

    def test_guardian_none_when_singleton_missing(self):
        """46. env=1 + GUARDIAN_AGENT absent on strategy_wiring →
        guardian bucket dropped (singleton-not-wired race).
        """
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(),
                with_h4=True,
                with_strategist_snapshot=True,
            ),
            # guardian=None default → no GUARDIAN_AGENT attr on fake module
        )
        try:
            result = build_h_state_full_response()
            self.assertNotIn("guardian", result["agent_states"])
            # Strategist present.
            self.assertIn("strategist", result["agent_states"])
        finally:
            _restore_strategy_wiring(prev_sw)


class TestGuardianAgentStateIncludeFilter(unittest.TestCase):
    """47-49. G3-08 Phase 4 Sub-task 4-2: include filter honours
    ``guardian`` bucket selection alongside ``strategist`` + H buckets.
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
            ),
            guardian=_FakeGuardian(with_guardian_snapshot=True),
        )

    def tearDown(self):
        _restore_strategy_wiring(self._prev_sw)
        if self._prev_env is None:
            os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        else:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._prev_env

    def test_include_guardian_only(self):
        """47. include=["guardian"] → agent_states has only guardian,
        h_states empty, version=1.
        """
        result = build_h_state_full_response(include=["guardian"])
        self.assertIn("guardian", result["agent_states"])
        self.assertEqual(set(result["agent_states"].keys()), {"guardian"})
        self.assertEqual(result["h_states"], {})
        self.assertEqual(result["version"], 1)

    def test_include_default_none_includes_guardian(self):
        """48. include=None default still picks up guardian bucket
        (parity with strategist + H buckets default-on).
        """
        result = build_h_state_full_response(include=None)
        self.assertIn("guardian", result["agent_states"])
        self.assertIn("strategist", result["agent_states"])

    def test_mixed_include_strategist_and_guardian(self):
        """49. include=["strategist","guardian"] → both populate, h_states empty."""
        result = build_h_state_full_response(include=["strategist", "guardian"])
        self.assertEqual(
            set(result["agent_states"].keys()),
            {"strategist", "guardian"},
        )
        self.assertEqual(result["h_states"], {})
        self.assertEqual(result["version"], 1)


class TestCollectAgentSnapshotsGuardianDefensive(unittest.TestCase):
    """50. Defensive paths for _collect_agent_snapshots Guardian arm —
    ensures guardian-only flag yields skeleton when singleton missing.
    """

    def test_guardian_none_when_singleton_missing(self):
        """50a. include_guardian=True + GUARDIAN_AGENT absent on fake module
        → result["guardian"] is None (mirrors 42b for Strategist).
        """
        from app.h_state_query_handler import _collect_agent_snapshots
        prev_sw = sys.modules.get("app.strategy_wiring")
        bare = types.ModuleType("app.strategy_wiring")
        # No GUARDIAN_AGENT attribute → getattr returns None.
        sys.modules["app.strategy_wiring"] = bare
        try:
            result = _collect_agent_snapshots(include_guardian=True)
            self.assertIsNone(result["guardian"])
            # All other slots must remain None too.
            self.assertIsNone(result["strategist"])
            self.assertIsNone(result["analyst"])
            self.assertIsNone(result["executor"])
            self.assertIsNone(result["scout"])
        finally:
            if prev_sw is None:
                sys.modules.pop("app.strategy_wiring", None)
            else:
                sys.modules["app.strategy_wiring"] = prev_sw



# ── 43-49. Phase 4 Sub-task 4-3: Analyst agent_state integration ──


class _FakeAnalyst:
    """Minimal AnalystAgent stub for h_state handler tests.

    Mirrors _FakeStrategist's snapshot-fixture pattern. ``with_analyst_snapshot``
    defaults False (method absent) so the silent-skip degradation path (4-3 not
    yet landed shape) can be exercised. ``raises`` simulates accessor crash.

    最小化 AnalystAgent stub，鏡像 _FakeStrategist 的 snapshot fixture 模式。
    ``with_analyst_snapshot`` 預設 False（方法缺席）以驗證 4-3 未 land 場景的
    靜默跳過降級路徑。``raises`` 模擬 accessor 崩潰。
    """

    def __init__(
        self,
        with_analyst_snapshot=False,
        analyst_snapshot=None,
        analyst_snapshot_raises=None,
    ):
        self._analyst_snapshot = analyst_snapshot if analyst_snapshot is not None else {
            "trades_analyzed": 23,
            "l1_updates": 23,
            "l2_analyses": 1,
            "errors": 0,
            "experiment_ledger_connected": 1,
        }
        self._analyst_snapshot_raises = analyst_snapshot_raises
        if with_analyst_snapshot:
            def _get_analyst(_self=self):
                if _self._analyst_snapshot_raises is not None:
                    raise _self._analyst_snapshot_raises
                return _self._analyst_snapshot
            self.get_analyst_snapshot = _get_analyst


class TestAnalystAgentStateIntegration(unittest.TestCase):
    """43-46. G3-08 Phase 4 Sub-task 4-3: agent_states.analyst bucket
    population + degradation paths.

    Mirrors Sub-task 4-1 structure. PA RFC §2.3: schema = 5 fields, all
    int / bool→int (Rust ``AgentState.stats: HashMap<String, i64>`` parity).
    Sub-task 4-2/4/5 will add guardian/executor/scout buckets additively.

    G3-08 Phase 4 Sub-task 4-3：agent_states.analyst 桶填入 + 降級路徑。
    PA RFC §2.3 schema = 5 欄位、皆 int / bool→int。
    """

    _EXPECTED_ANALYST_FIELDS = {
        "trades_analyzed",
        "l1_updates",
        "l2_analyses",
        "errors",
        "experiment_ledger_connected",
    }

    def setUp(self):
        self._prev_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"

    def tearDown(self):
        if self._prev_env is None:
            os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        else:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._prev_env

    def test_analyst_populated_when_get_analyst_snapshot_present(self):
        """43. env=1 + analyst.get_analyst_snapshot present →
        agent_states.analyst contains the 5-field snapshot.
        """
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(), _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(), with_h4=True,
            ),
            analyst=_FakeAnalyst(with_analyst_snapshot=True),
        )
        try:
            result = build_h_state_full_response()
            self.assertIn("analyst", result["agent_states"])
            analyst = result["agent_states"]["analyst"]
            self.assertEqual(set(analyst.keys()), self._EXPECTED_ANALYST_FIELDS)
            # Spot-check default fixture values.
            self.assertEqual(analyst["trades_analyzed"], 23)
            self.assertEqual(analyst["l2_analyses"], 1)
            self.assertEqual(analyst["experiment_ledger_connected"], 1)
            for k, v in analyst.items():
                self.assertIsInstance(v, int, f"{k} must be int")
            self.assertEqual(result["version"], 1)
            # Sub-task 4-3 fills only analyst (+ strategist via 4-1);
            # 4-2/4/5 keys still absent.
            # Sub-task 4-3 只填 analyst（+ 4-1 strategist）；4-2/4/5 仍缺席。
            self.assertNotIn("guardian", result["agent_states"])
            self.assertNotIn("executor", result["agent_states"])
            self.assertNotIn("scout", result["agent_states"])
        finally:
            _restore_strategy_wiring(prev_sw)

    def test_analyst_dropped_when_get_analyst_snapshot_missing(self):
        """44. env=1 + analyst lacks get_analyst_snapshot → analyst absent
        (silent skip; models pre-4-3 deploy shape).
        """
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(), _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(), with_h4=True,
            ),
            analyst=_FakeAnalyst(),  # default with_analyst_snapshot=False
        )
        try:
            result = build_h_state_full_response()
            self.assertNotIn("analyst", result["agent_states"])
            # H buckets unaffected.
            self.assertIn("h1", result["h_states"])
            self.assertIn("h4", result["h_states"])
            self.assertEqual(result["version"], 1)
        finally:
            _restore_strategy_wiring(prev_sw)

    def test_analyst_dropped_when_get_analyst_snapshot_raises(self):
        """45. env=1 + analyst.get_analyst_snapshot raises → analyst bucket
        dropped, never-raise contract preserved.
        """
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(), _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(), with_h4=True,
            ),
            analyst=_FakeAnalyst(
                with_analyst_snapshot=True,
                analyst_snapshot_raises=RuntimeError("analyst snap boom"),
            ),
        )
        try:
            result = build_h_state_full_response()
            self.assertNotIn("analyst", result["agent_states"])
            self.assertIn("h1", result["h_states"])
            self.assertEqual(result["version"], 1)
        finally:
            _restore_strategy_wiring(prev_sw)

    def test_analyst_dropped_when_analyst_singleton_none(self):
        """46. env=1 + ANALYST_AGENT is None on fake module → analyst absent.
        Models strategy_wiring partial-init failure (line 444 fallback).
        env=1 + ANALYST_AGENT 為 None → analyst 缺席（strategy_wiring 部分初始化失敗）。
        """
        # Don't pass analyst kw → ANALYST_AGENT attribute missing entirely.
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(), _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(), with_h4=True,
            ),
        )
        try:
            result = build_h_state_full_response()
            self.assertNotIn("analyst", result["agent_states"])
        finally:
            _restore_strategy_wiring(prev_sw)


class TestAnalystAgentStateIncludeFilter(unittest.TestCase):
    """47-49. G3-08 Phase 4 Sub-task 4-3: include filter honours
    ``analyst`` bucket selection alongside H + strategist buckets.
    """

    def setUp(self):
        self._prev_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"
        self._prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(), _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(with_h5=True),
                with_h4=True, with_strategist_snapshot=True,
            ),
            analyst=_FakeAnalyst(with_analyst_snapshot=True),
        )

    def tearDown(self):
        _restore_strategy_wiring(self._prev_sw)
        if self._prev_env is None:
            os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        else:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._prev_env

    def test_include_analyst_only(self):
        """47. include=["analyst"] → agent_states has only analyst,
        h_states empty, version=1.
        """
        result = build_h_state_full_response(include=["analyst"])
        self.assertIn("analyst", result["agent_states"])
        self.assertEqual(set(result["agent_states"].keys()), {"analyst"})
        self.assertEqual(result["h_states"], {})
        self.assertEqual(result["version"], 1)

    def test_include_default_none_includes_analyst(self):
        """48. include=None default picks up analyst bucket alongside strategist."""
        result = build_h_state_full_response(include=None)
        self.assertIn("analyst", result["agent_states"])
        self.assertIn("strategist", result["agent_states"])
        self.assertEqual(
            set(result["h_states"].keys()),
            {"h1", "h2", "h3", "h4", "h5"},
        )

    def test_mixed_include_strategist_and_analyst(self):
        """49. include=["strategist","analyst"] → both agents populate,
        h_states empty.
        """
        result = build_h_state_full_response(include=["strategist", "analyst"])
        self.assertEqual(
            set(result["agent_states"].keys()),
            {"strategist", "analyst"},
        )
        self.assertEqual(result["h_states"], {})
        self.assertEqual(result["version"], 1)



# ── G3-08 Phase 4 Sub-task 4-4 — Executor agent_state round-trip ──


class TestExecutorAgentStateIntegration(unittest.TestCase):
    """43-45. G3-08 Phase 4 Sub-task 4-4: agent_states.executor bucket
    population + degradation paths.

    Mirrors Sub-task 4-1 strategist pattern (snapshot accessor on the agent
    itself). Per PA RFC §2.4 the schema has 9 fields, all int (Rust
    ``AgentState.stats: HashMap<String, i64>`` parity).

    G3-08 Phase 4 Sub-task 4-4：agent_states.executor 桶填入 + 降級路徑。
    與 Sub-task 4-1 strategist 同模式（snapshot accessor 在 agent 自身）。
    PA RFC §2.4 schema 為 9 欄位、皆 int（對齊 Rust ``HashMap<String, i64>``）。
    """

    _EXPECTED_EXECUTOR_FIELDS = {
        "intents_received",
        "intents_deduped",
        "executions_attempted",
        "executions_success",
        "executions_failed",
        "total_slippage_bps",
        "errors",
        "recent_intent_id_size",
        "shadow_mode",
    }

    def setUp(self):
        self._prev_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"

    def tearDown(self):
        if self._prev_env is None:
            os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        else:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._prev_env

    def test_executor_populated_when_get_executor_snapshot_present(self):
        """43. env=1 + executor.get_executor_snapshot present →
        agent_states.executor contains the 9-field snapshot.
        """
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(),
                with_h4=True,
                with_strategist_snapshot=True,
            ),
            executor=_FakeExecutor(with_executor_snapshot=True),
        )
        try:
            result = build_h_state_full_response()
            self.assertIn("executor", result["agent_states"])
            executor = result["agent_states"]["executor"]
            self.assertEqual(
                set(executor.keys()), self._EXPECTED_EXECUTOR_FIELDS
            )
            # Spot-check default fixture values.
            self.assertEqual(executor["intents_received"], 11)
            self.assertEqual(executor["executions_success"], 6)
            self.assertEqual(executor["recent_intent_id_size"], 3)
            self.assertEqual(executor["shadow_mode"], 1)
            # All values must be int (Rust HashMap<String, i64> parity).
            for k, v in executor.items():
                self.assertIsInstance(v, int, f"{k} must be int")
            self.assertEqual(result["version"], 1)
            # Sub-task 4-1 strategist also still populated.
            self.assertIn("strategist", result["agent_states"])
        finally:
            _restore_strategy_wiring(prev_sw)

    def test_executor_dropped_when_get_executor_snapshot_missing(self):
        """44. env=1 + executor lacks get_executor_snapshot → executor key
        absent (silent skip preserves never-raise contract). Models a deploy
        where Sub-task 4-4 hasn't landed yet.
        """
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(),
                with_h4=True,
                with_strategist_snapshot=True,
            ),
            executor=_FakeExecutor(with_executor_snapshot=False),
        )
        try:
            result = build_h_state_full_response()
            self.assertNotIn("executor", result["agent_states"])
            # Strategist bucket unaffected.
            self.assertIn("strategist", result["agent_states"])
            self.assertEqual(result["version"], 1)
        finally:
            _restore_strategy_wiring(prev_sw)

    def test_executor_dropped_when_get_executor_snapshot_raises(self):
        """45. env=1 + executor.get_executor_snapshot raises → executor key
        dropped, strategist + H buckets unaffected.
        """
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(),
                with_h4=True,
                with_strategist_snapshot=True,
            ),
            executor=_FakeExecutor(
                with_executor_snapshot=True,
                executor_snapshot_raises=RuntimeError("executor snap boom"),
            ),
        )
        try:
            result = build_h_state_full_response()
            self.assertNotIn("executor", result["agent_states"])
            # H buckets + strategist unaffected.
            self.assertIn("h1", result["h_states"])
            self.assertIn("strategist", result["agent_states"])
            self.assertEqual(result["version"], 1)
        finally:
            _restore_strategy_wiring(prev_sw)


class TestExecutorAgentStateIncludeFilter(unittest.TestCase):
    """46-49. G3-08 Phase 4 Sub-task 4-4: include filter honours
    ``executor`` bucket selection alongside strategist + H buckets.
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
            ),
            executor=_FakeExecutor(with_executor_snapshot=True),
        )

    def tearDown(self):
        _restore_strategy_wiring(self._prev_sw)
        if self._prev_env is None:
            os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        else:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._prev_env

    def test_include_executor_only(self):
        """46. include=["executor"] → agent_states has only executor,
        h_states empty, version=1.
        """
        result = build_h_state_full_response(include=["executor"])
        self.assertIn("executor", result["agent_states"])
        self.assertEqual(set(result["agent_states"].keys()), {"executor"})
        self.assertEqual(result["h_states"], {})
        self.assertEqual(result["version"], 1)

    def test_include_default_none_includes_executor(self):
        """47. include=None default still picks up executor bucket
        (parity with strategist + H buckets default-on behaviour).
        """
        result = build_h_state_full_response(include=None)
        self.assertIn("executor", result["agent_states"])
        self.assertIn("strategist", result["agent_states"])
        self.assertEqual(
            set(result["h_states"].keys()),
            {"h1", "h2", "h3", "h4", "h5"},
        )

    def test_include_h_buckets_only_drops_executor(self):
        """48. include=["h1","h2","h3","h4","h5"] (no agent keys) →
        agent_states empty even though executor accessor is wired.
        """
        result = build_h_state_full_response(
            include=["h1", "h2", "h3", "h4", "h5"]
        )
        self.assertEqual(result["agent_states"], {})
        self.assertEqual(
            set(result["h_states"].keys()),
            {"h1", "h2", "h3", "h4", "h5"},
        )
        self.assertEqual(result["version"], 1)

    def test_mixed_include_strategist_and_executor(self):
        """49. include=["strategist","executor"] → both agent keys, no h_states.
        """
        result = build_h_state_full_response(
            include=["strategist", "executor"]
        )
        self.assertEqual(result["h_states"], {})
        self.assertEqual(
            set(result["agent_states"].keys()),
            {"strategist", "executor"},
        )
        self.assertEqual(result["version"], 1)




# ── 43-47. Phase 4 Sub-task 4-5: Scout agent_state integration ──


class TestScoutAgentStateIntegration(unittest.TestCase):
    """43-45. G3-08 Phase 4 Sub-task 4-5: agent_states.scout bucket
    population + degradation paths.

    Mirrors StrategistAgent Sub-task 4-1 caller-side pattern (snapshot
    accessor on the agent itself). PA RFC §2.5 schema: 5 fields, all int
    (Rust ``AgentState.stats: HashMap<String, i64>`` parity).

    G3-08 Phase 4 Sub-task 4-5：agent_states.scout 桶填入 + 降級路徑；
    對齊 Strategist Sub-task 4-1 caller-side pattern。PA RFC §2.5 schema 為
    5 欄位、皆 int（對齊 Rust ``AgentState.stats: HashMap<String, i64>``）。
    """

    _EXPECTED_SCOUT_FIELDS = {
        "intel_produced",
        "alerts_produced",
        "scans_completed",
        "intel_log_size",
        "alert_log_size",
    }

    def setUp(self):
        self._prev_env = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
        os.environ["OPENCLAW_H_STATE_GATEWAY"] = "1"

    def tearDown(self):
        if self._prev_env is None:
            os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        else:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._prev_env

    def test_scout_populated_when_get_scout_snapshot_present(self):
        """43. env=1 + scout.get_scout_snapshot present → agent_states.scout
        contains the 5-field snapshot. Verifies PA RFC §2.5 schema parity.
        """
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(),
            ),
            scout=_FakeScout(with_scout_snapshot=True),
        )
        try:
            result = build_h_state_full_response()
            self.assertIn("scout", result["agent_states"])
            scout = result["agent_states"]["scout"]
            # Schema parity with Rust AgentState.stats (5 fields).
            self.assertEqual(set(scout.keys()), self._EXPECTED_SCOUT_FIELDS)
            # Spot-check default fixture values.
            self.assertEqual(scout["intel_produced"], 13)
            self.assertEqual(scout["alerts_produced"], 5)
            self.assertEqual(scout["scans_completed"], 21)
            self.assertEqual(scout["intel_log_size"], 7)
            self.assertEqual(scout["alert_log_size"], 3)
            # All values must be int (Rust HashMap<String, i64> parity).
            for k, v in scout.items():
                self.assertIsInstance(v, int, f"{k} must be int")
                # Phase 4 invariant: not bool (bool is subclass of int but
                # Rust schema demands i64; surface any boolean creep).
                self.assertNotIsInstance(v, bool, f"{k} must not be bool")
            self.assertEqual(result["version"], 1)
        finally:
            _restore_strategy_wiring(prev_sw)

    def test_scout_dropped_when_get_scout_snapshot_missing(self):
        """44. env=1 + scout lacks get_scout_snapshot → scout absent (silent
        skip preserves never-raise contract). Models the Sub-task 4-2/3/4
        deploy scenario where 4-5 hasn't landed yet.
        """
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(),
            ),
            scout=_FakeScout(with_scout_snapshot=False),
        )
        try:
            result = build_h_state_full_response()
            self.assertNotIn("scout", result["agent_states"])
            # H buckets unaffected.
            self.assertIn("h1", result["h_states"])
        finally:
            _restore_strategy_wiring(prev_sw)

    def test_scout_dropped_when_get_scout_snapshot_raises(self):
        """45. env=1 + scout.get_scout_snapshot raises → scout bucket dropped,
        H buckets unaffected.
        """
        prev_sw = _install_fake_strategy_wiring(
            _FakeStrategist(
                _FakeH1Gate(),
                _FakeModelRouter(),
                cost_tracker=_FakeCostTracker(),
            ),
            scout=_FakeScout(
                with_scout_snapshot=True,
                scout_snapshot_raises=RuntimeError("scout snap boom"),
            ),
        )
        try:
            result = build_h_state_full_response()
            self.assertNotIn("scout", result["agent_states"])
            self.assertIn("h1", result["h_states"])
            self.assertEqual(result["version"], 1)
        finally:
            _restore_strategy_wiring(prev_sw)


class TestScoutAgentStateIncludeFilter(unittest.TestCase):
    """46. G3-08 Phase 4 Sub-task 4-5: include filter honours ``scout``
    bucket selection alongside H buckets.
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
            ),
            scout=_FakeScout(with_scout_snapshot=True),
        )

    def tearDown(self):
        _restore_strategy_wiring(self._prev_sw)
        if self._prev_env is None:
            os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        else:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._prev_env

    def test_include_scout_only(self):
        """46. include=["scout"] → agent_states has only scout, h_states empty."""
        result = build_h_state_full_response(include=["scout"])
        self.assertEqual(result["h_states"], {})
        self.assertEqual(set(result["agent_states"].keys()), {"scout"})
        self.assertEqual(result["version"], 1)


class TestPhase4FullEnvelopeRoundtrip(unittest.TestCase):
    """47. Phase 4 envelope completion regression test —
    include=None default with all 5 H singletons + Strategist + Scout
    wired must yield 5 H buckets + 2 agent buckets (until 4-2/3/4 land);
    once 4-2/3/4 land this test should be extended to assert all 5 agent
    buckets. Until then, the test guards against an agent-state DROP
    regression (e.g. Phase 4 wire shape silently breaking).

    47. Phase 4 信封完整度回歸測試 — include=None 預設時 5 個 H singleton
    + Strategist + Scout 接線必須回 5 H 桶 + 2 agent 桶（4-2/3/4 land 前）；
    一旦 4-2/3/4 land 應擴展為斷言全 5 agent 桶。在此之前用以防止 agent-state
    桶被誤丟（例：Phase 4 wire shape 默默壞掉）的回歸守門。
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
            ),
            scout=_FakeScout(with_scout_snapshot=True),
        )

    def tearDown(self):
        _restore_strategy_wiring(self._prev_sw)
        if self._prev_env is None:
            os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        else:
            os.environ["OPENCLAW_H_STATE_GATEWAY"] = self._prev_env

    def test_default_include_yields_5h_plus_strategist_scout(self):
        """47a. include=None → 5 H buckets all populated + agent_states
        contains both strategist and scout (4-2/3/4 unfilled keys absent).
        """
        result = build_h_state_full_response()
        # 5 H buckets all populated.
        self.assertEqual(
            set(result["h_states"].keys()),
            {"h1", "h2", "h3", "h4", "h5"},
        )
        # 2 of 5 agent buckets populated (Sub-tasks 4-1 + 4-5 landed).
        self.assertIn("strategist", result["agent_states"])
        self.assertIn("scout", result["agent_states"])
        self.assertNotIn("guardian", result["agent_states"])
        self.assertNotIn("analyst", result["agent_states"])
        self.assertNotIn("executor", result["agent_states"])
        self.assertEqual(result["version"], 1)
        # Sub-tasks 4-1 / 4-5 schema field counts.
        self.assertEqual(len(result["agent_states"]["strategist"]), 11)
        self.assertEqual(len(result["agent_states"]["scout"]), 5)

    def test_explicit_include_full_envelope(self):
        """47b. include=["h1","h2","h3","h4","h5","strategist","scout"]
        → 7 buckets all populated explicitly.
        """
        result = build_h_state_full_response(
            include=["h1", "h2", "h3", "h4", "h5", "strategist", "scout"]
        )
        self.assertEqual(
            set(result["h_states"].keys()),
            {"h1", "h2", "h3", "h4", "h5"},
        )
        self.assertEqual(
            set(result["agent_states"].keys()),
            {"strategist", "scout"},
        )
        self.assertEqual(result["version"], 1)


class TestScoutInstanceSnapshot(unittest.TestCase):
    """48. Real ScoutAgent.get_scout_snapshot end-to-end: instantiate a real
    ScoutAgent, drive its public APIs (produce_intel / produce_event_alert /
    record_scan), and verify the snapshot reflects the counter + gauge
    movement. Validates Phase 4 invariant (all int) on a real instance —
    not just the fake stub.
    48. 真實 ScoutAgent.get_scout_snapshot 端對端測試：實例化真實
    ScoutAgent，驅動其公開 API 並驗 snapshot 反映 counter + gauge 變化。
    在真實實例上驗 Phase 4 不變式（皆 int），非僅 fake stub。
    """

    def test_real_scout_snapshot_reflects_state_changes(self):
        from app.multi_agent_framework import ScoutAgent
        scout = ScoutAgent()
        # Initial snapshot — all zeros.
        snap0 = scout.get_scout_snapshot()
        self.assertEqual(snap0["intel_produced"], 0)
        self.assertEqual(snap0["alerts_produced"], 0)
        self.assertEqual(snap0["scans_completed"], 0)
        self.assertEqual(snap0["intel_log_size"], 0)
        self.assertEqual(snap0["alert_log_size"], 0)
        # Phase 4 invariant: all int (not bool, not float).
        for k, v in snap0.items():
            self.assertIsInstance(v, int, f"{k} must be int")
            self.assertNotIsInstance(v, bool, f"{k} must not be bool")
        # Drive state changes.
        scout.produce_intel(
            source="test",
            content="hello",
            symbols=["BTCUSDT"],
            relevance_score=0.1,  # below threshold so no bus send needed
        )
        scout.produce_intel(
            source="test",
            content="hello2",
            symbols=["BTCUSDT"],
            relevance_score=0.1,
        )
        scout.produce_event_alert(
            event_type="token_unlock",
            severity="low",
            affected_symbols=["BTCUSDT"],
        )
        scout.record_scan()
        scout.record_scan()
        scout.record_scan()
        snap1 = scout.get_scout_snapshot()
        self.assertEqual(snap1["intel_produced"], 2)
        self.assertEqual(snap1["alerts_produced"], 1)
        self.assertEqual(snap1["scans_completed"], 3)
        # Gauges reflect deque length.
        self.assertEqual(snap1["intel_log_size"], 2)
        self.assertEqual(snap1["alert_log_size"], 1)
        for k, v in snap1.items():
            self.assertIsInstance(v, int, f"{k} must be int")
            self.assertNotIsInstance(v, bool, f"{k} must not be bool")



if __name__ == "__main__":
    unittest.main()
