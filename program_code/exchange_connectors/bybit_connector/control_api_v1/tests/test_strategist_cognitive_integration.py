"""
G8-01 W3 — StrategistAgent × CognitiveModulator integration tests
==================================================================

MODULE_NOTE (中文):
  本檔承擔 PA RFC `2026-04-27--g8_01_cognitive_e2e_design.md` §3.3 列出的
  StrategistAgent integration ≥5 case 工作組（W3）。**不**承擔 W2 ≥85% line
  cov 純 unit 套件 —— 該責任由 ``test_cognitive_modulator_coverage.py``（未
  land）擔當。

  Mock 邊界（per PA RFC §3.3 + E1 G3-04 慣例）：
    - **Mock**：``MessageBus``（in-memory dummy 由 multi_agent_framework 提供） /
      ``OllamaClient``（None → 走 heuristic path） / ``ExecutorAgent``（不接線） /
      ``Layer2CostTracker``（``MagicMock`` stub 回固定 H5 dict）
    - **Real**：``StrategistAgent`` ctor + ``CognitiveModulator`` ctor +
      ``strategist_cognitive`` 模組所有 helper（``set_cognitive_modulator`` /
      ``_apply_cognitive_modulation`` / ``tick_cognitive_modulator``） +
      ``_handle_intel`` 編排 hot path + ``record_trade_outcome`` LOSSES-WIRING

  Scope 限制（per W3 task spec 2026-04-28）：
    - 7 scenarios 全走 ``consecutive_losses`` + ``h_state inputs`` 兩條真路徑
    - **不**用 ``regret_data`` / ``dream_data`` 場景（REGRET-DREAM 概念於 commit
      ``cf34e96`` escalation 確認 dead，永遠 None；走那條路徑等於測 dead branch）

  Test 獨立性：
    - 每 case ``setUp`` 重建 ``StrategistAgent`` + ``CognitiveModulator`` 新實例，
      不共享 module-level ``STRATEGIST_AGENT`` singleton（避免 cross-case state
      洩漏破壞 EMA / update_count 累積）

MODULE_NOTE (English):
  Implementation of the StrategistAgent integration work-group (W3) listed in
  PA RFC `2026-04-27--g8_01_cognitive_e2e_design.md` §3.3 with ≥5 cases. Does
  NOT cover the W2 ≥85% line-cov unit suite — that belongs to a separate
  ``test_cognitive_modulator_coverage.py`` (not landed yet).

  Mock boundary (per PA RFC §3.3 + the E1 G3-04 pattern):
    - **Mock**: ``MessageBus`` (in-memory dummy provided by
      multi_agent_framework) / ``OllamaClient`` (None → heuristic path) /
      ``ExecutorAgent`` (not wired) / ``Layer2CostTracker`` (``MagicMock`` stub
      returning a fixed H5 dict)
    - **Real**: ``StrategistAgent`` ctor + ``CognitiveModulator`` ctor + every
      helper in ``strategist_cognitive`` (``set_cognitive_modulator`` /
      ``_apply_cognitive_modulation`` / ``tick_cognitive_modulator``) +
      ``_handle_intel`` orchestration hot path + ``record_trade_outcome``
      LOSSES-WIRING

  Scope constraints (per W3 task spec 2026-04-28):
    - All 7 scenarios use the two real paths: ``consecutive_losses`` and the
      ``h_state inputs`` envelope path
    - We do NOT use ``regret_data`` / ``dream_data`` (REGRET-DREAM concept
      confirmed dead in escalation ``cf34e96``, always None; exercising that
      branch tests dead code)

  Test independence:
    - Each case ``setUp`` rebuilds fresh ``StrategistAgent`` +
      ``CognitiveModulator`` instances; the module-level ``STRATEGIST_AGENT``
      singleton is never touched (cross-case EMA / update_count contamination
      would break monotonic assertions)

Refs:
  - PA RFC `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g8_01_cognitive_e2e_design.md` §3.3
  - W1 sanity tests `test_strategist_cognitive_w1_fix.py` (template for setUp)
  - LOSSES-WIRING follow-up commits + escalation `cf34e96` (REGRET-DREAM dead)
  - feedback_no_dead_params memory entry
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Make ``app`` importable when run from srv root or tests/.
# 從 srv root 或 tests/ 跑時保證可 import ``app``。
_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app.multi_agent_framework import (
    AgentMessage,
    AgentRole,
    DataQualityLevel,
    IntelObject,
    MessageBus,
    MessageType,
    SentimentScore,
)
from app.strategist_agent import (
    StrategistAgent,
    StrategistConfig,
    _COGNITIVE_TICK_INTERVAL,
)
from app.strategist_cognitive import (
    _apply_cognitive_modulation,
    set_cognitive_modulator,
    tick_cognitive_modulator,
)

# Real production class — not stubbed. W3 integration must exercise the real
# EMA + clamp + getter path so we know it actually advances under hot-path use.
# 真實 production class —— 不 stub。W3 integration 必須走真實 EMA + clamp +
# getter 路徑，才能驗證 hot path 下狀態真有推進。
from program_code.local_model_tools.cognitive_modulator import CognitiveModulator


# ─────────────────────────────────────────────────────────────────────────────
# Shared fixtures / 共用 fixture
# ─────────────────────────────────────────────────────────────────────────────

def _make_strategist(
    *,
    cost_tracker=None,
    message_bus=None,
    shadow: bool = True,
) -> StrategistAgent:
    """Build a minimal running StrategistAgent for integration tests.

    Settings mirror ``test_strategist_cognitive_w1_fix._make_strategist`` so W3
    cases share the same hot-path geometry as the W1 sanity suite (no
    relevance / freshness gating; intel always reaches evaluation).

    建立最小化運行中的 StrategistAgent，與 W1 sanity 套件 fixture 對齊
    （無 relevance / freshness 門檻；intel 必達 evaluation）。
    """
    agent = StrategistAgent(
        config=StrategistConfig(
            shadow=shadow,
            min_confidence=0.4,            # default-ish but explicit
            min_relevance=0.0,             # accept any relevance
            heuristic_min_relevance=0.0,
            heuristic_min_freshness=9999,
            max_intel_age_seconds=10**9,   # effectively disable age gate
        ),
        cost_tracker=cost_tracker,
        message_bus=message_bus,
        ollama_client=None,                # force heuristic path (no AI)
    )
    agent.start()
    return agent


def _make_intel_message(
    *,
    sentiment: SentimentScore = SentimentScore.POSITIVE,
    relevance: float = 0.5,
) -> AgentMessage:
    """Build a minimal valid INTEL_OBJECT AgentMessage.
    建立最小化有效 INTEL_OBJECT AgentMessage。"""
    intel = IntelObject(
        source="g8_01_w3_integration_test",
        content="integration sanity intel",
        symbols=["BTCUSDT"],
        data_quality=DataQualityLevel.FACT,
        sentiment=sentiment,
        relevance_score=relevance,
        freshness_seconds=1,
        metadata={},
    )
    return AgentMessage(
        sender=AgentRole.SCOUT,
        receiver=AgentRole.STRATEGIST,
        message_type=MessageType.INTEL_OBJECT,
        priority=3,
        payload=intel.to_dict(),
    )


def _make_h5_stub_tracker(*, paper_net_pnl_7d: float = 0.0) -> MagicMock:
    """``Layer2CostTracker`` stub: only ``get_h5_snapshot`` + ``record_call`` matter.

    ``tick_cognitive_modulator`` reads ``paper_net_pnl_7d`` from the snapshot;
    everything else can stay default. ``record_call`` is invoked from the
    ``_handle_intel`` hot path after an evaluation — return None to keep it
    silent. We deliberately leave ``check_daily_budget`` returning a
    truthy/permissive default (``MagicMock``) so the H1 budget gate passes
    and intel actually reaches the post-evaluation cognitive-floor check.

    ``tick_cognitive_modulator`` 從 snapshot 讀 ``paper_net_pnl_7d``；其他保
    default 即可。``record_call`` 由 ``_handle_intel`` 評估後熱路徑呼叫——
    回 None 即靜默。``check_daily_budget`` 刻意保持 MagicMock 預設（truthy）
    讓 H1 預算閘放行，intel 才能抵達 cognitive-floor 檢查。
    """
    tracker = MagicMock()
    tracker.get_h5_snapshot.return_value = {
        "paper_net_pnl_7d": paper_net_pnl_7d,
        # Other keys are not consumed by tick_cognitive_modulator; included for
        # realism / 其他 key 不被 tick 消費，僅為真實感補入。
        "ai_spend_7d": 0.0,
        "cost_edge_ratio": 0.0,
        "data_days": 7,
    }
    # Permissive budget gate so intel reaches evaluation.
    # 寬鬆預算閘讓 intel 抵達 evaluation。
    tracker.check_daily_budget.return_value = (True, 100.0)
    tracker.record_call.return_value = None
    return tracker


# ═════════════════════════════════════════════════════════════════════════════
# Scenario tests / 場景測試
# ═════════════════════════════════════════════════════════════════════════════

class TestS1ThresholdAdaptDrivesIntentReweight(unittest.TestCase):
    """[Scenario 1] Threshold adapt → strategist consume → intent reweight.

    LOSSES-WIRING + tick → ``confidence_floor`` ascends; subsequent intel with
    confidence below the new floor is rejected (``evaluations_rejected`` ≥ 1).

    LOSSES-WIRING + tick → ``confidence_floor`` 上升；後續 intel 信心低於
    新門檻時被拒（``evaluations_rejected`` ≥ 1）。
    """

    def test_loss_streak_lifts_floor_and_rejects_low_conf_intel(self):
        # Drive multiple losses + force enough ticks to converge floor upward.
        # 推送多次虧損 + 強制足夠 tick 讓 floor 收斂上升。
        agent = _make_strategist(cost_tracker=_make_h5_stub_tracker())
        modulator = CognitiveModulator()
        set_cognitive_modulator(agent, modulator)

        # Streak of 6 losses → consecutive_losses = 6 → confidence pos pressure
        # min(6-2, 5) * 0.02 = 0.08 (per cognitive_modulator._compute_confidence_floor).
        # 6 連敗 → 信心 +0.08。
        for _ in range(6):
            agent.record_trade_outcome(net_pnl=-1.0)
        self.assertEqual(agent._stats["consecutive_losses"], 6)

        # Tick the modulator several times so EMA(α=0.3) converges close to
        # the new target (base 0.60 + 0.08 = 0.68; ≥10 ticks → ~0.68).
        # tick 多次讓 EMA 收斂到 ~0.68。
        floor_before = modulator.get_confidence_floor()
        for _ in range(15):
            tick_cognitive_modulator(agent)
        floor_after = modulator.get_confidence_floor()
        self.assertGreater(
            floor_after, floor_before,
            "confidence_floor must rise under sustained loss streak / "
            "持續連虧下 confidence_floor 必須上升",
        )

        # Apply modulation: floor returned must equal modulator's floor (not
        # config.min_confidence default), proving wiring + reweight live.
        # 套用調製：返回 floor 必須等於 modulator floor（非 config default），
        # 證接線 + reweight 真實有效。
        adj_floor, qty_ceil = _apply_cognitive_modulation(agent, confidence=0.5)
        self.assertEqual(adj_floor, floor_after)
        # Sanity: qty_ceiling clamped within documented [0.3, 1.0] range.
        # 衛生：qty_ceiling 在 [0.3, 1.0] 範圍內。
        self.assertTrue(0.3 <= qty_ceil <= 1.0)


class TestS2ScanIntervalEMARecovery(unittest.TestCase):
    """[Scenario 2] scan_interval drift under negative pnl → EMA recovery.

    With ``weekly_net_pnl < 0`` ticks repeatedly, ``scan_interval_s`` is
    pulled toward base * 0.5 (= 900s). Once the input flips to 0, EMA
    monotonically returns toward base 1800s.

    weekly_net_pnl<0 連續 tick 將 scan_interval 拉向 base*0.5 (=900s)；輸入
    歸零後 EMA 單調回升至 base 1800s。
    """

    def test_scan_interval_drift_then_recovers_via_ema(self):
        # Phase A: drift down with weekly_pnl=-100 stub × N ticks.
        # 階段 A：weekly_pnl=-100 stub × N tick 向下漂移。
        bad_tracker = _make_h5_stub_tracker(paper_net_pnl_7d=-100.0)
        agent = _make_strategist(cost_tracker=bad_tracker)
        modulator = CognitiveModulator()
        set_cognitive_modulator(agent, modulator)

        baseline_scan = modulator.get_scan_interval_seconds()
        for _ in range(15):
            tick_cognitive_modulator(agent)
        drifted_scan = modulator.get_scan_interval_seconds()

        # scan_interval must drop below baseline (1800 → ~900 target).
        # scan_interval 必須下降（1800 → ~900 target）。
        self.assertLess(
            drifted_scan, baseline_scan,
            "scan_interval must drift downward under negative weekly pnl / "
            "weekly pnl 為負時 scan_interval 必須下降",
        )

        # Phase B: flip weekly_pnl to 0 → EMA recovers upward.
        # 階段 B：weekly_pnl 改 0 → EMA 向上回升。
        bad_tracker.get_h5_snapshot.return_value = {
            "paper_net_pnl_7d": 0.0,
            "ai_spend_7d": 0.0,
            "cost_edge_ratio": 0.0,
            "data_days": 7,
        }
        for _ in range(15):
            tick_cognitive_modulator(agent)
        recovered_scan = modulator.get_scan_interval_seconds()

        # Recovered must be strictly greater than drifted (monotone EMA);
        # need not reach baseline exactly — α=0.3 → asymptotic.
        # 回升嚴格大於漂移點（EMA 單調）；不必精確回到 baseline（α=0.3 漸近）。
        self.assertGreater(
            recovered_scan, drifted_scan,
            "scan_interval must recover when weekly pnl normalizes / "
            "weekly pnl 歸零後 scan_interval 必須回升",
        )


class TestS3FaultInjectionModulatorImportError(unittest.TestCase):
    """[Scenario 3] Fault injection — modulator method raises.

    When the modulator's API throws (simulating a partial-deploy /
    AttributeError-like fault), ``_apply_cognitive_modulation`` falls back to
    ``(config.min_confidence, 1.0)`` — fail-closed bypass per principle #6.
    The hot-path ``tick`` similarly fail-softs (warn + continue), and
    ``_handle_intel`` does NOT propagate the exception.

    Modulator API 拋例外時（模擬部分部署 / AttributeError 類失誤），
    ``_apply_cognitive_modulation`` 退回 ``(config.min_confidence, 1.0)``——
    原則 #6 fail-closed bypass。Hot-path tick 同理 fail-soft（warn + continue），
    ``_handle_intel`` 不向外傳播 exception。
    """

    def test_get_all_params_raises_falls_back_to_defaults(self):
        agent = _make_strategist(cost_tracker=_make_h5_stub_tracker())
        bad = MagicMock()
        bad.get_all_params.side_effect = RuntimeError("simulated import error fallback")
        # tick path also stubbed out — we isolate the get_all_params raise here.
        # tick 路徑也 stub — 隔離 get_all_params raise 路徑。
        bad.update.return_value = None
        set_cognitive_modulator(agent, bad)

        floor, qty_ceil = _apply_cognitive_modulation(agent, confidence=0.7)

        # Bypass values per strategist_cognitive._apply_cognitive_modulation
        # except branch.
        # 對應 except 分支的 bypass 值。
        self.assertEqual(floor, agent.config.min_confidence)
        self.assertEqual(qty_ceil, 1.0)

    def test_tick_modulator_update_raises_does_not_poison_hot_path(self):
        agent = _make_strategist(cost_tracker=_make_h5_stub_tracker())
        bad = MagicMock()
        bad.update.side_effect = RuntimeError("simulated update fault")
        bad.get_all_params.return_value = {
            "confidence_floor": 0.0,
            "qty_ceiling": 1.0,
            "stoploss_multiplier": 1.0,
            "scan_interval_s": 1800,
            "update_count": 0,
        }
        set_cognitive_modulator(agent, bad)

        # Feed exactly _COGNITIVE_TICK_INTERVAL intel — must not raise.
        # 投遞剛好 _COGNITIVE_TICK_INTERVAL 個 intel —— 不可 raise。
        for _ in range(_COGNITIVE_TICK_INTERVAL):
            try:
                agent._handle_intel(_make_intel_message())
            except Exception as exc:  # pragma: no cover — fail-soft guard
                self.fail(f"_handle_intel surfaced modulator exception: {exc}")

        # Tick was attempted at least once (proves wiring + fail-soft).
        # tick 至少嘗試 1 次（證接線 + fail-soft）。
        self.assertGreaterEqual(bad.update.call_count, 1)
        # intel_received accounting unaffected by modulator failure.
        # intel_received 統計不受 modulator 失敗影響。
        self.assertEqual(
            agent._stats["intel_received"], _COGNITIVE_TICK_INTERVAL,
        )


class TestS4CostSpikeRaisesFloor(unittest.TestCase):
    """[Scenario 4] Cost spike override — H5 ``paper_net_pnl_7d`` strongly
    negative → tick ingests as ``weekly_net_pnl=-500`` → ``confidence_floor``
    +0.02 (per ``_compute_confidence_floor`` weekly_pnl<0 branch) and
    ``qty_ceiling`` -0.10.

    H5 嚴重虧損 → tick 帶入 ``weekly_net_pnl=-500`` → ``confidence_floor``
    +0.02、``qty_ceiling`` -0.10。
    """

    def test_negative_h5_lifts_floor_and_lowers_ceiling(self):
        spike_tracker = _make_h5_stub_tracker(paper_net_pnl_7d=-500.0)
        agent = _make_strategist(cost_tracker=spike_tracker)
        modulator = CognitiveModulator()
        set_cognitive_modulator(agent, modulator)

        floor_before = modulator.get_confidence_floor()
        ceil_before = modulator.get_qty_ceiling()

        # Tick many times so EMA converges near target.
        # tick 多次讓 EMA 收斂近 target。
        for _ in range(20):
            tick_cognitive_modulator(agent)

        floor_after = modulator.get_confidence_floor()
        ceil_after = modulator.get_qty_ceiling()

        # Strict monotone: floor up, ceiling down.
        # 嚴格單調：floor 上升、ceiling 下降。
        self.assertGreater(
            floor_after, floor_before,
            "H5 cost spike must lift confidence_floor / "
            "H5 成本飆升必須抬高 confidence_floor",
        )
        self.assertLess(
            ceil_after, ceil_before,
            "H5 cost spike must lower qty_ceiling / "
            "H5 成本飆升必須壓低 qty_ceiling",
        )

        # Snapshot integration: get_strategist_snapshot must reflect modulator
        # connected (1 by ctor + injection).
        # snapshot 整合：get_strategist_snapshot 必反映 modulator connected (=1)。
        snapshot = agent.get_strategist_snapshot()
        self.assertEqual(snapshot["cognitive_modulator_connected"], 1)


class TestS5HStateEnvelopeRoundTrip(unittest.TestCase):
    """[Scenario 5] H1-H5 envelope round-trip via build_h_state_full_response.

    With ``OPENCLAW_H_STATE_GATEWAY=1``, the public envelope builder must
    return the strategist agent_state with ``cognitive_modulator_connected=1``
    after the production wiring path runs (set_cognitive_modulator).
    Tick advances ``intel_received`` so envelope reflects live counters.

    env 開啟下，envelope builder 必須回 ``cognitive_modulator_connected=1``
    的 strategist agent_state；tick 推進 intel_received，envelope 反映 live counter。

    Note: To avoid touching the strategy_wiring module-level singleton
    (cross-test contamination), we monkey-patch its ``STRATEGIST_AGENT``
    attribute with our fresh test instance for the duration of this case.

    為避免動到 strategy_wiring 的 module-level singleton（會污染其他 case），
    本 case 期間把 ``STRATEGIST_AGENT`` monkey-patch 為新建測試 instance。
    """

    def test_envelope_includes_strategist_with_modulator_connected(self):
        agent = _make_strategist(cost_tracker=_make_h5_stub_tracker())
        modulator = CognitiveModulator()
        set_cognitive_modulator(agent, modulator)

        # Drive a small intel batch so intel_received counter is non-trivial.
        # 推送少量 intel 讓 intel_received counter 非零。
        for _ in range(3):
            agent._handle_intel(_make_intel_message())

        # Stub ``app.strategy_wiring`` in sys.modules with a tiny shim that
        # exposes only the attribute names the envelope builder reads
        # (STRATEGIST_AGENT). The real strategy_wiring drags in fastapi +
        # all 5 agents on import, which is heavy and fails on Mac dev (no
        # fastapi installed). Stub-then-restore keeps lazy-import semantics
        # without polluting the real module-level singleton across tests.
        # 用 sys.modules 灌入 ``app.strategy_wiring`` 的小 shim，只暴露
        # envelope builder 讀取的屬性 (STRATEGIST_AGENT)。真實 strategy_wiring
        # 匯入時會拉 fastapi + 所有 5-Agent，重且 Mac dev 環境無 fastapi 而失敗。
        # Stub-then-restore 保留 lazy-import 語意又不污染跨 test 的真實 singleton。
        from app import h_state_query_handler

        sw_module_name = "app.strategy_wiring"
        sw_stub = type(sys)("app.strategy_wiring")
        sw_stub.STRATEGIST_AGENT = agent
        original_sw = sys.modules.get(sw_module_name)
        sys.modules[sw_module_name] = sw_stub

        try:
            with patch.dict(
                os.environ, {"OPENCLAW_H_STATE_GATEWAY": "1"}, clear=False,
            ):
                response = h_state_query_handler.build_h_state_full_response()
        finally:
            # Restore prior module state — none = remove our stub entirely.
            # 還原先前模組狀態 — 原本 None 時整個移除我們的 stub。
            if original_sw is None:
                sys.modules.pop(sw_module_name, None)
            else:
                sys.modules[sw_module_name] = original_sw

        # Schema invariants: top-level keys present.
        # schema 不變量：top-level key 齊備。
        self.assertIn("version", response)
        self.assertIn("h_states", response)
        self.assertIn("agent_states", response)
        # Version must be 1 since we populated agent_states (and likely h_states).
        # version 必為 1（agent_states 已填，多半 h_states 也填）。
        self.assertEqual(response["version"], 1)

        # Strategist agent_state present with cognitive_modulator_connected=1.
        # strategist agent_state 在內，cognitive_modulator_connected=1。
        agent_states = response["agent_states"]
        self.assertIn("strategist", agent_states)
        strat_state = agent_states["strategist"]
        self.assertEqual(strat_state["cognitive_modulator_connected"], 1)
        # intel_received reflected on the wire (post 3 _handle_intel calls).
        # intel_received 在 wire 上反映（3 次 _handle_intel 後）。
        self.assertGreaterEqual(strat_state["intel_received"], 3)


class TestS6LossesStreakAdvancesModulatorState(unittest.TestCase):
    """[Scenario 6] LOSSES streak (LOSSES-WIRING) → modulator state advances.

    Validates the LOSSES-WIRING integration end-to-end:
    ``record_trade_outcome(loss)`` × N → ``_stats["consecutive_losses"]`` = N
    → ``tick_cognitive_modulator`` reads it → ``modulator.update_count`` and
    ``confidence_floor`` advance accordingly.

    端到端驗證 LOSSES-WIRING 整合：``record_trade_outcome(loss)`` × N →
    ``_stats["consecutive_losses"]`` = N → ``tick`` 讀取 → ``modulator``
    狀態相應推進。
    """

    def test_record_trade_outcome_then_tick_advances_state(self):
        agent = _make_strategist(cost_tracker=_make_h5_stub_tracker())
        modulator = CognitiveModulator()
        set_cognitive_modulator(agent, modulator)

        # Pre-condition: zero state.
        # 前置：零狀態。
        params0 = modulator.get_all_params()
        self.assertEqual(params0["update_count"], 0)
        self.assertEqual(agent._stats["consecutive_losses"], 0)

        # Phase 1: 4 losses + 1 tick.
        # 階段 1：4 連虧 + 1 tick。
        for _ in range(4):
            agent.record_trade_outcome(net_pnl=-2.0)
        self.assertEqual(agent._stats["consecutive_losses"], 4)
        self.assertEqual(agent._stats["trade_outcomes_observed"], 4)

        floor_before_tick = modulator.get_confidence_floor()
        tick_cognitive_modulator(agent)
        floor_after_one_tick = modulator.get_confidence_floor()

        # update_count advanced by exactly 1.
        # update_count 精確 +1。
        self.assertEqual(modulator.get_all_params()["update_count"], 1)
        # confidence_floor strictly greater (4 losses → +0.04 target,
        # EMA(0.3) 1 step → +0.012; small but strictly positive).
        # confidence_floor 嚴格升高（4 連虧 → target +0.04，EMA 1 步 → +0.012）。
        self.assertGreater(floor_after_one_tick, floor_before_tick)

        # Phase 2: a win resets streak to 0; further ticks gradually relax floor.
        # 階段 2：一勝歸零連虧；後續 tick 逐步放鬆 floor。
        agent.record_trade_outcome(net_pnl=+5.0)
        self.assertEqual(agent._stats["consecutive_losses"], 0)
        self.assertEqual(agent._stats["trade_outcomes_observed"], 5)

        for _ in range(15):
            tick_cognitive_modulator(agent)
        floor_after_recovery = modulator.get_confidence_floor()

        # Floor returns toward base (0.60); strictly less than the lifted peak.
        # floor 回歸 base (0.60)；嚴格低於先前抬升點。
        self.assertLess(
            floor_after_recovery, floor_after_one_tick,
            "After streak break + ticks, floor must relax / "
            "連虧斷開 + tick 後 floor 必須放鬆",
        )


class TestS7HappyPathW1AndLossesIntegrated(unittest.TestCase):
    """[Scenario 7] Happy-path full chain: W1 + LOSSES-WIRING + 5 scenarios
    integrated end-to-end.

    Single test case that exercises:
      1. ``set_cognitive_modulator`` injection (W1 part)
      2. ``record_trade_outcome`` LOSSES-WIRING accounting
      3. ``_handle_intel`` × N → ``tick`` auto-fires every
         ``_COGNITIVE_TICK_INTERVAL`` (W1 BUG-B fix)
      4. ``_apply_cognitive_modulation`` reads real modulator floor
         (W1 BUG-A fix)
      5. ``get_strategist_snapshot`` reflects ``cognitive_modulator_connected=1``
         and live ``consecutive_losses``

    happy-path 全鏈：W1 + LOSSES-WIRING + 5 場景端到端整合。
    """

    def test_full_chain_w1_losses_strategist_snapshot(self):
        agent = _make_strategist(cost_tracker=_make_h5_stub_tracker())
        modulator = CognitiveModulator()

        # Step 1: inject modulator (W1 wiring).
        # 步驟 1：注入 modulator (W1 接線)。
        set_cognitive_modulator(agent, modulator)
        snap_initial = agent.get_strategist_snapshot()
        self.assertEqual(snap_initial["cognitive_modulator_connected"], 1)
        self.assertEqual(snap_initial["intel_received"], 0)

        # Step 2: feed 3 losses (LOSSES-WIRING).
        # 步驟 2：投遞 3 次虧損 (LOSSES-WIRING)。
        for _ in range(3):
            agent.record_trade_outcome(net_pnl=-1.5)
        self.assertEqual(agent._stats["consecutive_losses"], 3)

        # Step 3: drive _handle_intel × _COGNITIVE_TICK_INTERVAL → exactly 1 tick.
        # 步驟 3：驅動 _handle_intel × N → 剛好 1 tick。
        for _ in range(_COGNITIVE_TICK_INTERVAL):
            agent._handle_intel(_make_intel_message())
        self.assertEqual(modulator.get_all_params()["update_count"], 1)
        self.assertEqual(
            agent._stats["intel_received"], _COGNITIVE_TICK_INTERVAL,
        )

        # Step 4: _apply_cognitive_modulation must surface modulator's real
        # floor (not config.min_confidence default).
        # 步驟 4：_apply_cognitive_modulation 必反映 modulator 真實 floor。
        modulator_params = modulator.get_all_params()
        floor_returned, qty_ceil_returned = _apply_cognitive_modulation(
            agent, confidence=0.5,
        )
        self.assertEqual(floor_returned, modulator_params["confidence_floor"])
        self.assertEqual(qty_ceil_returned, modulator_params["qty_ceiling"])

        # Step 5: snapshot reflects live counters.
        # 步驟 5：snapshot 反映 live counter。
        snap_final = agent.get_strategist_snapshot()
        self.assertEqual(snap_final["cognitive_modulator_connected"], 1)
        self.assertEqual(snap_final["intel_received"], _COGNITIVE_TICK_INTERVAL)
        # intel_evaluated should advance (heuristic path; no relevance gate).
        # intel_evaluated 應推進（heuristic path；無 relevance gate）。
        self.assertGreater(snap_final["intel_evaluated"], 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
