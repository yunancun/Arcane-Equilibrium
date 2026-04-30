"""
Agent heartbeat contract tests — covers the GUI roster ``last_heartbeat_ms``
contract for all 5 runtime agents (Scout / Guardian / Analyst / Executor /
Strategist) end-to-end.
Agent 心跳契約測試 — 覆蓋 5 個 runtime agent 對 GUI roster 的
``last_heartbeat_ms`` 契約。

MODULE_NOTE (EN): Verifies the two-tier contract:
  Tier 1 (agent-side):
    * ``__init__`` leaves ``_last_heartbeat_ms == 0`` ("never active").
    * ``start()`` stamps a non-zero ms-epoch.
    * Each agent's "active code path" (record_scan / on_message /
      review_intent / analyze_trade / _handle_intel) refreshes the field.
    * ``get_stats()`` returns ``"last_heartbeat_ms"`` as int.
  Tier 2 (route helper):
    * ``_build_<role>_card`` reads ``stats["last_heartbeat_ms"]`` and
      converts to ISO-8601 in ``card["last_heartbeat_ts"]`` (None when 0).
    * ``_build_strategist_card`` falls back to stats heartbeat when the
      eval-log derived heartbeat is None (cold-start path).
  Hermetic: no real PG / Rust IPC; no FastAPI client. Pure agent ctor +
  helper level patches. Mac-dev-friendly.

MODULE_NOTE (中): 驗證雙層契約：
  Tier 1（agent 側）：__init__ 後 0 / start() 後 > 0 / 各活躍路徑刷新 /
    get_stats() 回 int。
  Tier 2（route helper 側）：_build_<role>_card 讀 stats 並 ISO 化；
    Strategist eval-log 為空時 fallback 到 stats heartbeat。
  封閉測試：無真 PG/Rust IPC；純 ctor + helper patch；Mac 友好。
"""

from __future__ import annotations

import os
import sys
import time
import types
import unittest
from typing import Any
from unittest.mock import MagicMock

# Path bootstrap mirrors the other agent unit-tests (control_api_v1 root on
# sys.path so ``from app.<X>`` resolves).
# Path bootstrap：對齊現有 agent unit-test 的 sys.path 注入。
_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)


from app.multi_agent_framework import (  # noqa: E402
    AgentMessage,
    AgentRole,
    AgentState,
    MessageType,
    TradeIntent,
)
from app.scout_agent import ScoutAgent  # noqa: E402
from app.guardian_agent import GuardianAgent  # noqa: E402
from app.analyst_agent import AnalystAgent, TradeRecord  # noqa: E402
from app.executor_agent import ExecutorAgent  # noqa: E402
from app.strategist_agent import StrategistAgent  # noqa: E402

from app import agents_routes_helpers as ar_helpers  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════════
# Tier 1 — Agent class contract / Agent class 層契約
# ═══════════════════════════════════════════════════════════════════════════════


class TestAgentInitHeartbeatZero(unittest.TestCase):
    """All 5 agents start with ``_last_heartbeat_ms == 0``.
    5 個 agent ctor 後 _last_heartbeat_ms 為 0。"""

    def test_scout_init_zero(self):
        agent = ScoutAgent()
        self.assertEqual(agent._last_heartbeat_ms, 0)

    def test_guardian_init_zero(self):
        agent = GuardianAgent()
        self.assertEqual(agent._last_heartbeat_ms, 0)

    def test_analyst_init_zero(self):
        agent = AnalystAgent()
        self.assertEqual(agent._last_heartbeat_ms, 0)

    def test_executor_init_zero(self):
        agent = ExecutorAgent()
        self.assertEqual(agent._last_heartbeat_ms, 0)

    def test_strategist_init_zero(self):
        agent = StrategistAgent()
        self.assertEqual(agent._last_heartbeat_ms, 0)


class TestAgentStartStampsHeartbeat(unittest.TestCase):
    """``start()`` stamps a non-zero ms-epoch on every agent.
    start() 為每個 agent 蓋上非零 ms-epoch。"""

    def test_scout_start_stamps(self):
        agent = ScoutAgent()
        before = int(time.time() * 1000)
        agent.start()
        after = int(time.time() * 1000)
        self.assertGreaterEqual(agent._last_heartbeat_ms, before)
        self.assertLessEqual(agent._last_heartbeat_ms, after)

    def test_guardian_start_stamps(self):
        agent = GuardianAgent()
        agent.start()
        self.assertGreater(agent._last_heartbeat_ms, 0)

    def test_analyst_start_stamps(self):
        agent = AnalystAgent()
        agent.start()
        self.assertGreater(agent._last_heartbeat_ms, 0)

    def test_executor_start_stamps(self):
        agent = ExecutorAgent()
        agent.start()
        self.assertGreater(agent._last_heartbeat_ms, 0)

    def test_strategist_start_stamps(self):
        agent = StrategistAgent()
        agent.start()
        self.assertGreater(agent._last_heartbeat_ms, 0)


class TestAgentActivityRefreshesHeartbeat(unittest.TestCase):
    """Each agent's canonical active path refreshes ``_last_heartbeat_ms``.
    每個 agent 的標準活躍路徑刷新 _last_heartbeat_ms。"""

    def _assert_strictly_increases(self, before: int, after: int) -> None:
        self.assertGreater(
            after,
            before,
            "heartbeat did not advance after activity / 活動後心跳未推進",
        )

    def test_scout_record_scan_refreshes(self):
        agent = ScoutAgent()
        agent.start()
        before = agent._last_heartbeat_ms
        time.sleep(0.002)  # ensure ms-resolution clock advances / 確保 ms 時鐘前進
        agent.record_scan()
        self._assert_strictly_increases(before, agent._last_heartbeat_ms)

    def test_scout_produce_intel_does_not_stamp(self):
        """MED-2 collapse: produce_intel does NOT stamp heartbeat (only
        record_scan does — canonical cycle-completion signal).
        MED-2 收斂：produce_intel 不蓋章；只有 record_scan 蓋章。"""
        agent = ScoutAgent()
        agent.start()
        before = agent._last_heartbeat_ms
        time.sleep(0.002)
        agent.produce_intel(
            source="test", content="x", symbols=["BTCUSDT"],
        )
        # heartbeat must NOT advance (produce_intel no longer stamps).
        # 心跳不應前進（produce_intel 不再蓋章）。
        self.assertEqual(
            agent._last_heartbeat_ms,
            before,
            "produce_intel should not stamp after MED-2 collapse / "
            "MED-2 收斂後 produce_intel 不應蓋章",
        )

    def test_scout_produce_event_alert_does_not_stamp(self):
        """MED-2 collapse: produce_event_alert does NOT stamp heartbeat.
        MED-2 收斂：produce_event_alert 不蓋章。"""
        agent = ScoutAgent()
        agent.start()
        before = agent._last_heartbeat_ms
        time.sleep(0.002)
        agent.produce_event_alert(
            event_type="news", severity="medium",
            affected_symbols=["BTCUSDT"], description="x",
        )
        self.assertEqual(
            agent._last_heartbeat_ms,
            before,
            "produce_event_alert should not stamp after MED-2 collapse / "
            "MED-2 收斂後 produce_event_alert 不應蓋章",
        )

    def test_guardian_review_intent_refreshes(self):
        agent = GuardianAgent()
        agent.start()
        before = agent._last_heartbeat_ms
        time.sleep(0.002)
        intent = TradeIntent(
            symbol="BTCUSDT", strategy="test", direction="long", size=0.01,
            params={"leverage": 1.0}, confidence=0.7,
        )
        agent.review_intent(intent)
        self._assert_strictly_increases(before, agent._last_heartbeat_ms)

    def test_guardian_on_message_refreshes(self):
        agent = GuardianAgent()
        agent.start()
        before = agent._last_heartbeat_ms
        time.sleep(0.002)
        # Send a directive (won't change verdict counters but must stamp)
        # 發送 directive（不改變裁決計數但必須蓋章）
        msg = AgentMessage(
            sender=AgentRole.CONDUCTOR,
            receiver=AgentRole.GUARDIAN,
            message_type=MessageType.SYSTEM_DIRECTIVE,
            payload={"directive_type": "noop"},
        )
        agent.on_message(msg)
        self._assert_strictly_increases(before, agent._last_heartbeat_ms)

    def test_analyst_on_message_refreshes(self):
        agent = AnalystAgent()
        agent.start()
        before = agent._last_heartbeat_ms
        time.sleep(0.002)
        msg = AgentMessage(
            sender=AgentRole.CONDUCTOR,
            receiver=AgentRole.ANALYST,
            message_type=MessageType.SYSTEM_DIRECTIVE,
            payload={"directive_type": "noop"},
        )
        agent.on_message(msg)
        self._assert_strictly_increases(before, agent._last_heartbeat_ms)

    def test_analyst_analyze_trade_refreshes(self):
        agent = AnalystAgent()
        agent.start()
        before = agent._last_heartbeat_ms
        time.sleep(0.002)
        record = TradeRecord(
            trade_id="t1", symbol="BTCUSDT", strategy="test", direction="long",
            entry_price=100.0, exit_price=101.0, pnl=1.0, hold_ms=1000,
            regime="trending",
        )
        agent.analyze_trade(record)
        self._assert_strictly_increases(before, agent._last_heartbeat_ms)

    def test_executor_on_message_refreshes(self):
        agent = ExecutorAgent()
        agent.start()
        before = agent._last_heartbeat_ms
        time.sleep(0.002)
        msg = AgentMessage(
            sender=AgentRole.CONDUCTOR,
            receiver=AgentRole.EXECUTOR,
            message_type=MessageType.SYSTEM_DIRECTIVE,
            payload={},
        )
        agent.on_message(msg)
        self._assert_strictly_increases(before, agent._last_heartbeat_ms)

    def test_strategist_on_message_refreshes(self):
        agent = StrategistAgent()
        agent.start()
        before = agent._last_heartbeat_ms
        time.sleep(0.002)
        msg = AgentMessage(
            sender=AgentRole.CONDUCTOR,
            receiver=AgentRole.STRATEGIST,
            message_type=MessageType.SYSTEM_DIRECTIVE,
            payload={"directive_type": "noop"},
        )
        agent.on_message(msg)
        self._assert_strictly_increases(before, agent._last_heartbeat_ms)


class TestAgentGetStatsExposesHeartbeat(unittest.TestCase):
    """``get_stats()`` returns ``"last_heartbeat_ms"`` as int on all agents.
    5 個 agent 的 get_stats() 都回傳 int 型 last_heartbeat_ms。"""

    def test_scout_get_stats(self):
        agent = ScoutAgent()
        agent.start()
        stats = agent.get_stats()
        self.assertIn("last_heartbeat_ms", stats)
        self.assertIsInstance(stats["last_heartbeat_ms"], int)
        self.assertGreater(stats["last_heartbeat_ms"], 0)

    def test_guardian_get_stats(self):
        agent = GuardianAgent()
        agent.start()
        stats = agent.get_stats()
        self.assertIn("last_heartbeat_ms", stats)
        self.assertIsInstance(stats["last_heartbeat_ms"], int)
        self.assertGreater(stats["last_heartbeat_ms"], 0)

    def test_analyst_get_stats(self):
        agent = AnalystAgent()
        agent.start()
        stats = agent.get_stats()
        self.assertIn("last_heartbeat_ms", stats)
        self.assertIsInstance(stats["last_heartbeat_ms"], int)
        self.assertGreater(stats["last_heartbeat_ms"], 0)

    def test_executor_get_stats(self):
        agent = ExecutorAgent()
        agent.start()
        stats = agent.get_stats()
        self.assertIn("last_heartbeat_ms", stats)
        self.assertIsInstance(stats["last_heartbeat_ms"], int)
        self.assertGreater(stats["last_heartbeat_ms"], 0)

    def test_strategist_get_stats(self):
        agent = StrategistAgent()
        agent.start()
        stats = agent.get_stats()
        self.assertIn("last_heartbeat_ms", stats)
        self.assertIsInstance(stats["last_heartbeat_ms"], int)
        self.assertGreater(stats["last_heartbeat_ms"], 0)


# ═══════════════════════════════════════════════════════════════════════════════
# Tier 2 — Route helper contract / route helper 層契約
# ═══════════════════════════════════════════════════════════════════════════════


def _install_fake_strategy_wiring(
    *,
    scout: Any = None,
    strategist: Any = None,
    guardian: Any = None,
    executor: Any = None,
    analyst: Any = None,
) -> tuple[Any, Any]:
    """Install a fake ``app.strategy_wiring`` module with the supplied mocks.
    安裝 fake ``app.strategy_wiring`` 模組以注入 mock agent。

    Returns (saved_module_or_None, fake_module) so the caller can restore.
    回傳 (原模組或 None, fake)，呼叫端負責還原。
    """
    fake_mod = types.ModuleType("app.strategy_wiring")
    fake_mod.SCOUT_AGENT = scout  # type: ignore[attr-defined]
    fake_mod.STRATEGIST_AGENT = strategist  # type: ignore[attr-defined]
    fake_mod.GUARDIAN_AGENT = guardian  # type: ignore[attr-defined]
    fake_mod.EXECUTOR_AGENT = executor  # type: ignore[attr-defined]
    fake_mod.ANALYST_AGENT = analyst  # type: ignore[attr-defined]
    saved = sys.modules.get("app.strategy_wiring")
    sys.modules["app.strategy_wiring"] = fake_mod
    return saved, fake_mod


def _restore_strategy_wiring(saved: Any) -> None:
    """Restore the previously saved ``app.strategy_wiring`` module.
    還原 _install_fake_strategy_wiring 之前儲存的模組。"""
    if saved is None:
        sys.modules.pop("app.strategy_wiring", None)
    else:
        sys.modules["app.strategy_wiring"] = saved


class TestRoleCardSurfacesHeartbeatTs(unittest.TestCase):
    """Each ``_build_<role>_card`` converts stats heartbeat → ISO ts.
    每個 _build_<role>_card 把 stats 心跳轉成 ISO ts。"""

    def setUp(self) -> None:
        self._now_ms = int(time.time() * 1000)

    def _stub(self, *, state: str = "running", **extra: Any) -> Any:
        return types.SimpleNamespace(
            get_stats=lambda: {"state": state, "last_heartbeat_ms": self._now_ms, **extra},
        )

    def test_scout_card_ts_is_iso(self):
        scout = self._stub(intel_produced=3)
        saved, _ = _install_fake_strategy_wiring(scout=scout)
        try:
            card = ar_helpers._build_scout_card(
                today_costs_by_role={}, today_intent_total=0, scan_interval_s=60,
            )
        finally:
            _restore_strategy_wiring(saved)
        self.assertIsNotNone(card["last_heartbeat_ts"])
        self.assertIsInstance(card["last_heartbeat_ts"], str)
        # Sanity: ISO-8601 has 'T' separator.
        self.assertIn("T", card["last_heartbeat_ts"])

    def test_guardian_card_ts_is_iso(self):
        guardian = self._stub()
        saved, _ = _install_fake_strategy_wiring(guardian=guardian)
        try:
            card = ar_helpers._build_guardian_card(
                today_costs_by_role={}, today_verdicts={"approved": 1},
            )
        finally:
            _restore_strategy_wiring(saved)
        self.assertIsNotNone(card["last_heartbeat_ts"])
        self.assertIsInstance(card["last_heartbeat_ts"], str)
        self.assertIn("T", card["last_heartbeat_ts"])

    def test_analyst_card_ts_is_iso(self):
        analyst = self._stub(trades_analyzed=5)
        saved, _ = _install_fake_strategy_wiring(analyst=analyst)
        try:
            card = ar_helpers._build_analyst_card(
                today_costs_by_role={}, scan_interval_s=60,
            )
        finally:
            _restore_strategy_wiring(saved)
        self.assertIsNotNone(card["last_heartbeat_ts"])
        self.assertIsInstance(card["last_heartbeat_ts"], str)
        self.assertIn("T", card["last_heartbeat_ts"])

    def test_executor_card_ts_is_iso(self):
        executor = self._stub(shadow_mode=True, orders_submitted=2)
        saved, _ = _install_fake_strategy_wiring(executor=executor)
        try:
            card = ar_helpers._build_executor_card(
                today_costs_by_role={}, today_intent_total=0,
            )
        finally:
            _restore_strategy_wiring(saved)
        self.assertIsNotNone(card["last_heartbeat_ts"])
        self.assertIsInstance(card["last_heartbeat_ts"], str)
        self.assertIn("T", card["last_heartbeat_ts"])

    def test_card_ts_is_none_when_heartbeat_zero(self):
        """``last_heartbeat_ms=0`` (never active) → card ts stays None.
        last_heartbeat_ms=0（從未活動）→ 卡片 ts 維持 None。"""
        scout = types.SimpleNamespace(
            get_stats=lambda: {"state": "running", "last_heartbeat_ms": 0},
        )
        saved, _ = _install_fake_strategy_wiring(scout=scout)
        try:
            card = ar_helpers._build_scout_card(
                today_costs_by_role={}, today_intent_total=0, scan_interval_s=60,
            )
        finally:
            _restore_strategy_wiring(saved)
        self.assertIsNone(card["last_heartbeat_ts"])


class TestStrategistFallbackToStatsHeartbeat(unittest.TestCase):
    """``_build_strategist_card`` falls back to stats heartbeat when eval log
    is empty. _build_strategist_card eval log 為空時 fallback 到 stats 心跳。"""

    def test_fallback_when_eval_log_empty(self):
        now_ms = int(time.time() * 1000)
        strategist = types.SimpleNamespace(
            get_stats=lambda: {
                "state": "running",
                "intel_evaluated": 0,
                "h1_budget_skip": 0,
                "evaluations_rejected": 0,
                "intents_produced": 0,
                # Stats heartbeat populated, eval-log not / 統計心跳有，eval log 空
                "last_heartbeat_ms": now_ms,
            },
            get_recent_evaluations=lambda limit=20: [],  # empty eval log
            get_scan_interval_seconds=lambda: 60,
        )
        saved, _ = _install_fake_strategy_wiring(strategist=strategist)
        try:
            card = ar_helpers._build_strategist_card(
                today_costs_by_role={}, today_intent_total=0,
                today_verdicts={}, scan_interval_s=60,
            )
        finally:
            _restore_strategy_wiring(saved)
        self.assertIsNotNone(card["last_heartbeat_ts"])
        self.assertIn("T", str(card["last_heartbeat_ts"]))

    def test_eval_log_takes_precedence_over_stats(self):
        """When eval log has an entry, its ts wins (precise over fallback).
        eval log 有條目時優先（精確優於 fallback）。"""
        eval_ts = int(time.time() * 1000) - 5000  # 5s ago
        stats_ts = int(time.time() * 1000)        # now
        strategist = types.SimpleNamespace(
            get_stats=lambda: {
                "state": "running",
                "intel_evaluated": 1,
                "h1_budget_skip": 0,
                "evaluations_rejected": 0,
                "intents_produced": 0,
                "last_heartbeat_ms": stats_ts,
            },
            get_recent_evaluations=lambda limit=20: [
                {"timestamp_ms": eval_ts, "symbols": ["BTCUSDT"]},
            ],
            get_scan_interval_seconds=lambda: 60,
        )
        saved, _ = _install_fake_strategy_wiring(strategist=strategist)
        try:
            card = ar_helpers._build_strategist_card(
                today_costs_by_role={}, today_intent_total=0,
                today_verdicts={}, scan_interval_s=60,
            )
        finally:
            _restore_strategy_wiring(saved)
        # Card ts is from eval log (older), not stats fallback (newer).
        # 卡片 ts 來自 eval log（較舊），非 stats fallback（較新）。
        self.assertIsNotNone(card["last_heartbeat_ts"])
        # Convert ISO back to ms-epoch for compare.
        # 把 ISO 轉回 ms-epoch 比較。
        from datetime import datetime
        parsed = datetime.fromisoformat(card["last_heartbeat_ts"].replace("Z", "+00:00"))
        card_ms = int(parsed.timestamp() * 1000)
        # Allow 1ms slack for floating-point round-trip.
        # 允許 1ms 容差（浮點 round-trip）。
        self.assertLess(abs(card_ms - eval_ts), 1500)
        self.assertGreater(abs(card_ms - stats_ts), 1500)

    def test_fallback_returns_none_when_both_empty(self):
        """Both eval-log and stats heartbeat empty → card ts = None.
        eval-log 與 stats 都為空 → 卡片 ts 維持 None。"""
        strategist = types.SimpleNamespace(
            get_stats=lambda: {
                "state": "running",
                "intel_evaluated": 0,
                "h1_budget_skip": 0,
                "evaluations_rejected": 0,
                "intents_produced": 0,
                "last_heartbeat_ms": 0,  # never active
            },
            get_recent_evaluations=lambda limit=20: [],
            get_scan_interval_seconds=lambda: 60,
        )
        saved, _ = _install_fake_strategy_wiring(strategist=strategist)
        try:
            card = ar_helpers._build_strategist_card(
                today_costs_by_role={}, today_intent_total=0,
                today_verdicts={}, scan_interval_s=60,
            )
        finally:
            _restore_strategy_wiring(saved)
        self.assertIsNone(card["last_heartbeat_ts"])


class TestStoppedAgentDoesNotStampOnMessage(unittest.TestCase):
    """M-1 strict (round 2): non-RUNNING agents must NOT stamp heartbeat
    when on_message is invoked. CLAUDE.md 原則 #10 認知誠實 > debug 便利：
    GUI 看到 stopped + fresh ts 是矛盾訊號，違反 fail-loud。
    M-1 嚴格化（round 2）：stopped agent 收到 message 不蓋章 — 避免 GUI
    狀態與心跳矛盾。eval_log 真停滯時 stats fallback 也為 0 → ISO=None →
    GUI 紅 chip 正確反映 stopped 狀態。"""

    def test_guardian_on_message_does_not_stamp_when_stopped(self):
        """Build agent → don't start (state=stopped) → send message →
        verify _last_heartbeat_ms remains 0.
        建 agent → 不 start → 灌訊息 → 驗 _last_heartbeat_ms 為 0。"""
        agent = GuardianAgent()
        # Agent is not started — state stays at default (stopped/initialized).
        # 未呼叫 start() — state 維持預設（stopped/initialized）。
        self.assertNotEqual(agent.state, AgentState.RUNNING)
        msg = AgentMessage(
            sender=AgentRole.CONDUCTOR,
            receiver=AgentRole.GUARDIAN,
            message_type=MessageType.SYSTEM_DIRECTIVE,
            payload={"directive_type": "noop"},
        )
        agent.on_message(msg)
        self.assertEqual(
            agent._last_heartbeat_ms,
            0,
            "stopped Guardian should not stamp on_message / "
            "stopped Guardian 不應於 on_message 蓋章",
        )

    def test_analyst_on_message_does_not_stamp_when_stopped(self):
        agent = AnalystAgent()
        self.assertNotEqual(agent.state, AgentState.RUNNING)
        msg = AgentMessage(
            sender=AgentRole.CONDUCTOR,
            receiver=AgentRole.ANALYST,
            message_type=MessageType.SYSTEM_DIRECTIVE,
            payload={"directive_type": "noop"},
        )
        agent.on_message(msg)
        self.assertEqual(
            agent._last_heartbeat_ms,
            0,
            "stopped Analyst should not stamp on_message / "
            "stopped Analyst 不應於 on_message 蓋章",
        )

    def test_executor_on_message_does_not_stamp_when_stopped(self):
        agent = ExecutorAgent()
        self.assertNotEqual(agent.state, AgentState.RUNNING)
        msg = AgentMessage(
            sender=AgentRole.CONDUCTOR,
            receiver=AgentRole.EXECUTOR,
            message_type=MessageType.SYSTEM_DIRECTIVE,
            payload={},
        )
        agent.on_message(msg)
        self.assertEqual(
            agent._last_heartbeat_ms,
            0,
            "stopped Executor should not stamp on_message / "
            "stopped Executor 不應於 on_message 蓋章",
        )

    def test_strategist_on_message_does_not_stamp_when_stopped(self):
        agent = StrategistAgent()
        self.assertNotEqual(agent.state, AgentState.RUNNING)
        msg = AgentMessage(
            sender=AgentRole.CONDUCTOR,
            receiver=AgentRole.STRATEGIST,
            message_type=MessageType.SYSTEM_DIRECTIVE,
            payload={"directive_type": "noop"},
        )
        agent.on_message(msg)
        self.assertEqual(
            agent._last_heartbeat_ms,
            0,
            "stopped Strategist should not stamp on_message / "
            "stopped Strategist 不應於 on_message 蓋章",
        )


if __name__ == "__main__":
    unittest.main()
