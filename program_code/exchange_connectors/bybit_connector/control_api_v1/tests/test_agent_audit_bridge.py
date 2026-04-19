"""
Tests for agent_audit_bridge — E5-FN-3 5-Agent Decision Audit Trail
====================================================================
5-Agent 決策審計跟踪橋接測試

MODULE_NOTE (中文):
  驗證 agent_audit_bridge.make_agent_audit_callback(...) 正確將
  BaseAgent._audit(event_type, data) 事件橋接到 ChangeAuditLog.record_change(...)。

  覆蓋場景：
    1. make_agent_audit_callback 返回簽名為 (str, Any)->None 的 callable
    2. Pilot: AnalystAgent.analyze_trade(...) → ChangeAuditLog 新增一條記錄
    3. 決策事件（trade_analyzed / verdict 類）→ ChangeType.PARAMETER_CHANGE
    4. 被動接收事件（*_received / directive_received）→ ChangeType.STATE_CHANGE
    5. Fail-open：gov_hub=None / _change_audit_log=None / 序列化失敗皆靜默
    6. who 欄位 = 建構時傳入的 role_name，affected_components 包含 role_name

MODULE_NOTE (English):
  Verify agent_audit_bridge.make_agent_audit_callback(...) correctly bridges
  BaseAgent._audit(event_type, data) events into ChangeAuditLog.record_change(...).

  Coverage:
    1. make_agent_audit_callback returns callable with signature (str, Any)->None
    2. Pilot: AnalystAgent.analyze_trade(...) → +1 row in ChangeAuditLog
    3. Decision events (trade_analyzed / verdict class) → PARAMETER_CHANGE
    4. Passive-receipt events (*_received / directive_received) → STATE_CHANGE
    5. Fail-open: gov_hub=None / _change_audit_log=None / serialization errors
       are all swallowed silently
    6. who column == role_name passed at construction, affected_components
       contains role_name

Governance refs: CLAUDE.md §二 Root Principle #8, DOC-06 §5
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent_audit_bridge import make_agent_audit_callback
from app.change_audit_log import (
    ChangeAuditLog,
    ChangeType,
    ChangeApprovalStatus,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers / 輔助
# ═══════════════════════════════════════════════════════════════════════════════

class _FakeGovHub:
    """
    Minimal stub mimicking GovernanceHub's attribute surface used by the bridge.
    僅暴露 bridge 用到的屬性，不模擬 governance 業務邏輯。
    """

    def __init__(self, change_audit_log=None):
        self._change_audit_log = change_audit_log


# ═══════════════════════════════════════════════════════════════════════════════
# Tests / 測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestBridgeReturnsCallable:
    """Factory returns a (event_type, data) callable compatible with BaseAgent._audit."""

    def test_returns_callable(self):
        cb = make_agent_audit_callback(_FakeGovHub(), "AnalystAgent")
        assert callable(cb)

    def test_signature_accepts_str_and_any(self):
        cb = make_agent_audit_callback(_FakeGovHub(ChangeAuditLog()), "AnalystAgent")
        # Should not raise on (str, dict), (str, None), (str, list), (str, int)
        cb("trade_analyzed", {"pnl": 100.0})
        cb("directive_received", None)
        cb("shadow_intent", [1, 2, 3])
        cb("intent_produced", 42)


class TestBridgeWritesToChangeAuditLog:
    """Events flow into ChangeAuditLog.record_change(...) as append-only rows."""

    def test_single_event_appends_one_row(self):
        cal = ChangeAuditLog()
        assert cal.record_count() == 0

        cb = make_agent_audit_callback(_FakeGovHub(cal), "AnalystAgent")
        cb("trade_analyzed", {"pnl": 100.0, "symbol": "BTCUSDT"})

        assert cal.record_count() == 1
        rec = cal.get_all_changes()[0]
        assert rec.who == "AnalystAgent"
        assert "trade_analyzed" in rec.what
        assert rec.approval_status == ChangeApprovalStatus.AUTO_APPROVED
        assert "AnalystAgent" in rec.affected_components

    def test_decision_event_is_parameter_change(self):
        cal = ChangeAuditLog()
        cb = make_agent_audit_callback(_FakeGovHub(cal), "AnalystAgent")

        cb("trade_analyzed", {"pnl": 100.0})
        cb("l2_pattern_insight", {"pattern": "mean_reversion"})
        cb("verdict", {"result": "APPROVED"})
        cb("edge_evaluation", {"edge_bps": 12.3})

        for rec in cal.get_all_changes():
            assert rec.change_type == ChangeType.PARAMETER_CHANGE, (
                f"expected PARAMETER_CHANGE for {rec.what}, got {rec.change_type}"
            )

    def test_passive_receipt_is_state_change(self):
        cal = ChangeAuditLog()
        cb = make_agent_audit_callback(_FakeGovHub(cal), "StrategistAgent")

        cb("risk_verdict_received", {"intent_id": "abc"})
        cb("pattern_insight_received", {"pattern": "x"})
        cb("directive_received", {"directive_type": "pause"})
        cb("execution_report_received", {"status": "filled"})

        for rec in cal.get_all_changes():
            assert rec.change_type == ChangeType.STATE_CHANGE, (
                f"expected STATE_CHANGE for {rec.what}, got {rec.change_type}"
            )

    def test_multiple_events_are_all_persisted(self):
        cal = ChangeAuditLog()
        cb = make_agent_audit_callback(_FakeGovHub(cal), "AnalystAgent")

        events = [
            ("trade_analyzed", {"pnl": 1.0}),
            ("trade_analyzed", {"pnl": 2.0}),
            ("trade_analyzed", {"pnl": 3.0}),
            ("directive_received", {"cmd": "flush"}),
        ]
        for et, data in events:
            cb(et, data)

        assert cal.record_count() == 4

    def test_unknown_event_type_defaults_to_parameter_change(self):
        """
        NIT-2 contract-lock: unknown event_type (no keyword match) must fall
        through _classify_event()'s conservative default → PARAMETER_CHANGE.
        This defends against a future silent behavior-shift if someone flips
        the default to STATE_CHANGE.

        NIT-2 契約鎖定：未匹配任何 keyword 的未知 event_type 必須命中
        _classify_event() 的保守默認分支 → PARAMETER_CHANGE。防止未來有人
        把默認分支靜默改成 STATE_CHANGE。
        """
        cal = ChangeAuditLog()
        cb = make_agent_audit_callback(_FakeGovHub(cal), "AnalystAgent")

        # Genuinely opaque: contains NO substring from _DECISION_EVENT_KEYWORDS
        # or _STATE_EVENT_KEYWORDS (no "verdict", "edge_evaluation",
        # "intent_produced", "shadow_intent", "trade_analyzed",
        # "execution_report", "l2_pattern_insight", "l2_analysis_triggered",
        # "knowledge_update", "event_assessed", "_received", "directive",
        # "risk_verdict", "pattern_insight_received", "risk_pattern_received").
        cb("opaque_event_xyz", {"foo": "bar"})

        assert cal.record_count() == 1
        rec = cal.get_all_changes()[0]
        assert rec.change_type == ChangeType.PARAMETER_CHANGE, (
            f"unknown event_type must default to PARAMETER_CHANGE; "
            f"got {rec.change_type}"
        )
        assert "opaque_event_xyz" in rec.what


class TestBridgeFailOpen:
    """Any bridge failure must NOT propagate to the agent."""

    def test_none_gov_hub_drops_silently(self):
        cb = make_agent_audit_callback(None, "AnalystAgent")
        # Should not raise
        cb("trade_analyzed", {"pnl": 100.0})

    def test_gov_hub_without_audit_log_drops_silently(self):
        cb = make_agent_audit_callback(_FakeGovHub(change_audit_log=None), "AnalystAgent")
        # Should not raise
        cb("trade_analyzed", {"pnl": 100.0})

    def test_record_change_exception_is_swallowed(self):
        # Stub that raises on record_change
        class _BoomLog:
            def record_change(self, **kwargs):
                raise RuntimeError("boom")

        cb = make_agent_audit_callback(_FakeGovHub(_BoomLog()), "AnalystAgent")
        # Must not propagate
        cb("trade_analyzed", {"pnl": 100.0})

    def test_late_binding_of_audit_log(self):
        """If _change_audit_log is attached AFTER the bridge is built, it still works."""
        hub = _FakeGovHub(change_audit_log=None)
        cb = make_agent_audit_callback(hub, "AnalystAgent")
        # First call: drops (no log yet)
        cb("trade_analyzed", {"pnl": 1.0})

        # Now attach a real log
        cal = ChangeAuditLog()
        hub._change_audit_log = cal
        cb("trade_analyzed", {"pnl": 2.0})
        assert cal.record_count() == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Pilot integration: AnalystAgent decision → audit row
# Pilot 集成：AnalystAgent 決策 → 產生審計記錄
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnalystPilotIntegration:
    """
    End-to-end pilot: an AnalystAgent wired with the bridge emits ChangeAuditLog
    rows when its decision methods fire. This is the acceptance proof for E5-FN-3
    per task brief.

    端到端 pilot：裝配了橋接的 AnalystAgent 在決策方法觸發時寫入
    ChangeAuditLog；這是 E5-FN-3 的驗收證據。
    """

    def test_analyst_analyze_trade_emits_audit_row(self):
        from app.analyst_agent import AnalystAgent, TradeRecord

        cal = ChangeAuditLog()
        hub = _FakeGovHub(cal)
        audit_cb = make_agent_audit_callback(hub, "AnalystAgent")

        agent = AnalystAgent(audit_callback=audit_cb)
        agent.start()

        record = TradeRecord(
            trade_id="e5fn3_pilot_001",
            symbol="BTCUSDT",
            strategy="pilot_test",
            direction="long",
            entry_price=60000.0,
            exit_price=61000.0,
            pnl=1000.0,
            hold_ms=3_600_000,
            regime="trending",
            timestamp_ms=int(time.time() * 1000),
        )

        # Precondition: no audit rows
        assert cal.record_count() == 0

        # Decision: analyze a completed round-trip
        agent.analyze_trade(record)

        # Acceptance: at least one audit row attributed to AnalystAgent
        assert cal.record_count() >= 1
        rows = cal.get_all_changes()
        analyst_rows = [r for r in rows if r.who == "AnalystAgent"]
        assert len(analyst_rows) >= 1

        trade_analyzed_rows = [
            r for r in analyst_rows if "trade_analyzed" in r.what
        ]
        assert len(trade_analyzed_rows) >= 1, (
            f"Expected trade_analyzed audit row; got rows: "
            f"{[r.what for r in analyst_rows]}"
        )

        row = trade_analyzed_rows[0]
        assert row.change_type == ChangeType.PARAMETER_CHANGE
        assert row.approval_status == ChangeApprovalStatus.AUTO_APPROVED
        assert "AnalystAgent" in row.affected_components

    def test_analyst_handle_execution_report_emits_state_change(self):
        from app.analyst_agent import AnalystAgent
        from app.multi_agent_framework import AgentMessage, AgentRole, MessageType

        cal = ChangeAuditLog()
        hub = _FakeGovHub(cal)
        audit_cb = make_agent_audit_callback(hub, "AnalystAgent")

        agent = AnalystAgent(audit_callback=audit_cb)
        agent.start()

        msg = AgentMessage(
            sender=AgentRole.EXECUTOR,
            receiver=AgentRole.ANALYST,
            message_type=MessageType.EXECUTION_REPORT,
            priority=3,
            payload={"status": "filled", "symbol": "ETHUSDT"},
        )
        agent.on_message(msg)

        rows = cal.get_all_changes()
        assert len(rows) >= 1
        exec_rows = [r for r in rows if "execution_report" in r.what]
        assert len(exec_rows) >= 1
        assert exec_rows[0].change_type == ChangeType.STATE_CHANGE
