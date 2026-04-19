"""
Tests for ScoutAgent audit_callback wiring — E5-FN-3-FUP-d
=============================================================
ScoutAgent 審計回調接線測試（E5-FN-3-FUP-d）

MODULE_NOTE (中文):
  驗證 ScoutAgent 的 __init__ 接受 audit_callback 參數，且當 strategy_wiring.py
  的 agent_audit_bridge 產出的 callback 被注入後，Scout 新增的兩個 _audit(...)
  呼叫點（produce_intel / produce_event_alert）會觸發 GOV_HUB._change_audit_log
  的 record_change（對應 PARAMETER_CHANGE 語義，Scout 輸出屬決策級事件）。

  背景（E5-FN-3 / E5-FN-3-FUP-a/b/c/d）：
    - E5-FN-3（commit 19f3d85）新增 agent_audit_bridge，AnalystAgent pilot 接線
    - FUP-a/b/c（commit 46b351a）接 Strategist / Guardian / Executor
    - FUP-d（本任務）接 Scout。Scout 是 5-Agent 體系唯一沒有 _audit() 呼叫點的
      agent，其 ctor 原將 audit_callback 硬編碼為 None。FUP-d 同時新增：
        1. ctor 接受 audit_callback（keyword-only，向後兼容）
        2. produce_intel / produce_event_alert 各加 1 個 _audit 呼叫點
        3. strategy_wiring.py 注入 bridge callback

  覆蓋場景：
    1. Contract: ScoutAgent(..., audit_callback=cb) 建構不拋異常，且 BaseAgent
       儲存回調到 self._audit_callback
    2. Integration (produce_intel): 呼叫 produce_intel(...) 後 ChangeAuditLog
       新增一條記錄，who="ScoutAgent"，what 含 "intel_produced"
    3. Integration (produce_event_alert): 呼叫 produce_event_alert(...) 後
       ChangeAuditLog 新增一條記錄，who="ScoutAgent"，what 含
       "event_alert_produced"

  Fail-open 驗證：預設 audit_callback=None 時 produce_intel / produce_event_alert
  不 raise，也不寫入（由 BaseAgent._audit 的 None-guard 保證，本測試驗未破壞此語義）。

MODULE_NOTE (English):
  Verify ScoutAgent.__init__ accepts audit_callback and the two new
  _audit(...) call-sites (produce_intel / produce_event_alert) forward events
  into ChangeAuditLog via the bridge (classified as PARAMETER_CHANGE per
  agent_audit_bridge._DECISION_EVENT_KEYWORDS).

  Background (E5-FN-3 / E5-FN-3-FUP-a/b/c/d):
    - E5-FN-3 (commit 19f3d85) introduced agent_audit_bridge + AnalystAgent pilot
    - FUP-a/b/c (commit 46b351a) wired Strategist / Guardian / Executor
    - FUP-d (this task) wires Scout. Scout was the only 5-Agent with zero
      _audit() call-sites and a hardcoded audit_callback=None. FUP-d adds:
        1. Ctor accepts audit_callback (keyword-only, backward-compatible)
        2. produce_intel / produce_event_alert each emit one _audit call
        3. strategy_wiring.py injects the bridge callback

  Coverage:
    1. Contract: ScoutAgent(..., audit_callback=cb) constructs without error,
       and BaseAgent stores the callback on self._audit_callback.
    2. Integration (produce_intel): calling produce_intel(...) writes +1 row
       to ChangeAuditLog with who="ScoutAgent" and what containing
       "intel_produced".
    3. Integration (produce_event_alert): calling produce_event_alert(...)
       writes +1 row with who="ScoutAgent" and what containing
       "event_alert_produced".

  Fail-open: default audit_callback=None → produce_intel / produce_event_alert
  neither raise nor write (guaranteed by BaseAgent._audit None-guard; this
  test class asserts the FUP-d change did not break that invariant).

Governance refs: CLAUDE.md §二 Root Principle #8 "Trade Explainability",
                 DOC-06 §5 (change_audit_log), E5-FN-3-FUP-d brief
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent_audit_bridge import make_agent_audit_callback
from app.change_audit_log import (
    ChangeAuditLog,
    ChangeApprovalStatus,
    ChangeType,
)
from app.multi_agent_framework import (
    MessageBus,
    ScoutAgent,
    ScoutConfig,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers / 輔助
# ═══════════════════════════════════════════════════════════════════════════════

class _FakeGovHub:
    """
    Minimal GovernanceHub stub — only exposes the attribute the bridge reads
    (`_change_audit_log`). Mirrors test_agent_audit_bridge._FakeGovHub and
    the FUP-a/b/c test files (intentional duplication — each test file owns
    its own stub to avoid coupling).

    最小 GovernanceHub stub，僅暴露 bridge 讀取的 `_change_audit_log` 屬性。
    刻意與其他 audit_wiring 測試檔各持一份，避免耦合。
    """

    def __init__(self, change_audit_log=None):
        self._change_audit_log = change_audit_log


# ═══════════════════════════════════════════════════════════════════════════════
# Tests / 測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestScoutAcceptsAuditCallback:
    """
    Contract: ScoutAgent.__init__ must accept audit_callback kwarg and
    forward it to BaseAgent; construction must not raise.
    契約：ScoutAgent.__init__ 必須接受 audit_callback 參數並轉發給 BaseAgent；
    建構不得拋異常。
    """

    def test_ctor_accepts_audit_callback_kwarg(self):
        """
        Minimal ctor smoke: inject a bridge callback built from a fake GovHub +
        real ChangeAuditLog; confirm BaseAgent stores the callback.
        最小建構冒煙：注入由假 GovHub + 真實 ChangeAuditLog 建的 bridge callback，
        確認 BaseAgent 儲存該 callback。
        """
        cal = ChangeAuditLog()
        hub = _FakeGovHub(cal)
        cb = make_agent_audit_callback(hub, "ScoutAgent")

        scout = ScoutAgent(
            config=ScoutConfig(),
            message_bus=None,
            audit_callback=cb,
        )
        # BaseAgent stores the callback under _audit_callback (see base_agent.py).
        # BaseAgent 將 callback 儲存於 _audit_callback（見 base_agent.py）。
        assert scout._audit_callback is cb

    def test_ctor_default_audit_callback_is_none(self):
        """
        Backward-compat: ScoutAgent() with no audit_callback must keep
        _audit_callback=None (fail-open: _audit() becomes a no-op).
        向後兼容：ScoutAgent() 預設 _audit_callback=None（_audit 為 no-op）。
        """
        scout = ScoutAgent()
        assert scout._audit_callback is None

    def test_ctor_legacy_positional_signature_still_works(self):
        """
        Back-compat regression guard: legacy callers pass (config, message_bus)
        positionally — this must still work after the keyword-only
        audit_callback addition.
        向後兼容回歸守護：舊呼叫 (config, message_bus) 位置參數在新增
        keyword-only audit_callback 後仍可正常工作。
        """
        bus = MessageBus()
        # Legacy call pattern seen in strategy_wiring.py before FUP-d.
        # 舊呼叫模式（FUP-d 前的 strategy_wiring.py）。
        scout = ScoutAgent(ScoutConfig(), bus)
        assert scout._audit_callback is None
        assert scout.bus is bus


class TestScoutAuditWritesOnProduceIntel:
    """
    Integration: Scout.produce_intel(...) writes +1 audit row via the bridge.
    集成：Scout.produce_intel(...) 經 bridge 寫入 1 條審計記錄。
    """

    def test_produce_intel_emits_audit_row(self):
        """
        Build ScoutAgent with bridge callback; call produce_intel(...); confirm
        one row in ChangeAuditLog attributed to ScoutAgent with
        "intel_produced" in `what`.
        用 bridge callback 建 ScoutAgent；呼叫 produce_intel(...)；驗 ChangeAuditLog
        新增一條 who=ScoutAgent 且 what 含 "intel_produced" 的記錄。
        """
        cal = ChangeAuditLog()
        hub = _FakeGovHub(cal)
        cb = make_agent_audit_callback(hub, "ScoutAgent")

        # bus=None: we want to verify audit fires even without bus routing.
        # bus=None：驗證即使沒有匯流排路由，審計仍會觸發。
        scout = ScoutAgent(
            config=ScoutConfig(),
            message_bus=None,
            audit_callback=cb,
        )

        # Precondition: no audit rows yet. / 前置：尚無審計記錄。
        assert cal.record_count() == 0

        scout.produce_intel(
            source="twitter",
            content="BTC unlock rumor",
            symbols=["BTCUSDT"],
            relevance_score=0.8,
        )

        assert cal.record_count() >= 1
        rows = cal.get_all_changes()
        scout_rows = [r for r in rows if r.who == "ScoutAgent"]
        assert len(scout_rows) >= 1, (
            f"Expected ScoutAgent rows; got who={[r.who for r in rows]}"
        )

        intel_rows = [r for r in scout_rows if "intel_produced" in r.what]
        assert len(intel_rows) >= 1, (
            f"Expected intel_produced row; got what="
            f"{[r.what for r in scout_rows]}"
        )

        row = intel_rows[0]
        # "intel_produced" matches the _DECISION_EVENT_KEYWORDS list → PARAMETER_CHANGE.
        # "intel_produced" 符合 _DECISION_EVENT_KEYWORDS → PARAMETER_CHANGE。
        assert row.change_type == ChangeType.PARAMETER_CHANGE
        assert row.approval_status == ChangeApprovalStatus.AUTO_APPROVED
        assert "ScoutAgent" in row.affected_components

    def test_produce_intel_audit_fires_before_bus_routing(self):
        """
        Regression guard: audit should fire even when relevance below threshold
        (bus routing skipped). This prevents a future refactor from silently
        moving the _audit call behind the bus-routing `if` block.
        回歸守護：當 relevance 低於閾值、bus 路由被跳過時，審計仍應觸發。
        防未來重構誤將 _audit 移到 bus-routing `if` 之後而導致靜默漏審。
        """
        cal = ChangeAuditLog()
        hub = _FakeGovHub(cal)
        cb = make_agent_audit_callback(hub, "ScoutAgent")

        bus = MessageBus()
        scout = ScoutAgent(
            config=ScoutConfig(relevance_threshold=0.9),  # high bar
            message_bus=bus,
            audit_callback=cb,
        )

        scout.produce_intel(
            source="twitter",
            content="low relevance",
            symbols=[],
            relevance_score=0.1,  # below threshold → bus skipped
        )

        # Bus routing skipped (relevance_score < threshold).
        # 匯流排路由被跳過（relevance_score < 閾值）。
        assert bus.total_messages == 0
        # Audit STILL fires. / 但審計仍觸發。
        assert cal.record_count() >= 1
        rows = cal.get_all_changes()
        intel_rows = [
            r for r in rows
            if r.who == "ScoutAgent" and "intel_produced" in r.what
        ]
        assert len(intel_rows) >= 1


class TestScoutAuditWritesOnProduceEventAlert:
    """
    Integration: Scout.produce_event_alert(...) writes +1 audit row via the bridge.
    集成：Scout.produce_event_alert(...) 經 bridge 寫入 1 條審計記錄。
    """

    def test_produce_event_alert_emits_audit_row(self):
        cal = ChangeAuditLog()
        hub = _FakeGovHub(cal)
        cb = make_agent_audit_callback(hub, "ScoutAgent")

        scout = ScoutAgent(
            config=ScoutConfig(),
            message_bus=None,
            audit_callback=cb,
        )

        assert cal.record_count() == 0

        scout.produce_event_alert(
            event_type="fomc",
            severity="high",
            affected_symbols=["BTCUSDT", "ETHUSDT"],
            lead_time_hours=2.0,
            description="FOMC meeting in 2 hours",
        )

        assert cal.record_count() >= 1
        rows = cal.get_all_changes()
        scout_rows = [r for r in rows if r.who == "ScoutAgent"]
        assert len(scout_rows) >= 1, (
            f"Expected ScoutAgent rows; got who={[r.who for r in rows]}"
        )

        alert_rows = [
            r for r in scout_rows if "event_alert_produced" in r.what
        ]
        assert len(alert_rows) >= 1, (
            f"Expected event_alert_produced row; got what="
            f"{[r.what for r in scout_rows]}"
        )

        row = alert_rows[0]
        # "event_alert_produced" has no direct match in _DECISION_EVENT_KEYWORDS
        # and no _STATE_EVENT_KEYWORDS substring match — classifier falls back
        # to PARAMETER_CHANGE default (conservative "better over-record than
        # miss"; see agent_audit_bridge._classify_event).
        # "event_alert_produced" 未命中 _DECISION_EVENT_KEYWORDS 且未命中
        # _STATE_EVENT_KEYWORDS，分類器落回 PARAMETER_CHANGE 預設（保守策略：
        # 寧可多錄不可漏錄，見 agent_audit_bridge._classify_event）。
        assert row.change_type == ChangeType.PARAMETER_CHANGE
        assert row.approval_status == ChangeApprovalStatus.AUTO_APPROVED
        assert "ScoutAgent" in row.affected_components


class TestScoutAuditFailOpen:
    """
    Fail-open regression: default audit_callback=None must not raise and must
    not write. Guards the FUP-d change from accidentally introducing a hard
    coupling to audit plumbing.
    Fail-open 回歸：預設 audit_callback=None 時不 raise、不寫入。守護 FUP-d
    未意外引入對審計接線的強耦合。
    """

    def test_produce_intel_no_callback_does_not_raise(self):
        scout = ScoutAgent()  # audit_callback defaults to None
        # Must not raise. / 不得拋例外。
        intel = scout.produce_intel(
            source="twitter",
            content="test",
            symbols=["BTCUSDT"],
            relevance_score=0.5,
        )
        assert intel is not None

    def test_produce_event_alert_no_callback_does_not_raise(self):
        scout = ScoutAgent()
        alert = scout.produce_event_alert(
            event_type="cpi",
            severity="medium",
            affected_symbols=["BTCUSDT"],
        )
        assert alert is not None
