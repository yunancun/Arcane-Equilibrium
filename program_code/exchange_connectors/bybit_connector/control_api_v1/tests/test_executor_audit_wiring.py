"""
Tests for ExecutorAgent audit_callback wiring — E5-FN-3-FUP-c
=============================================================
E5-FN-3-FUP-c：ExecutorAgent audit_callback 接線測試

MODULE_NOTE (中文):
  驗證 ExecutorAgent 建構時接受 audit_callback，且至少一個
  self._audit(...) 呼叫點會經由 agent_audit_bridge 寫入到
  _FakeGovHub._change_audit_log（ChangeAuditLog）。

  這是 E5-FN-3 AnalystAgent pilot 的 pattern 擴展，目的：
    - 落實根原則 #8「交易可解釋」
    - 關閉 Executor 2 個 _audit() 呼叫點靜默 no-op 的缺口
      （directive_received / execution_report）

MODULE_NOTE (English):
  Verify ExecutorAgent's constructor accepts audit_callback and that at
  least one self._audit(...) call-site bridges into _FakeGovHub
  ._change_audit_log (ChangeAuditLog) via agent_audit_bridge.

  Pattern extends the E5-FN-3 AnalystAgent pilot to satisfy:
    - Root Principle #8 "Trade Explainability"
    - Close the silent no-op gap at Executor's 2 _audit() call-sites
      (directive_received / execution_report)

Governance refs: CLAUDE.md §二 Root Principle #8, DOC-06 §5
"""

import sys
from pathlib import Path

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
from app.executor_agent import ExecutorAgent, ExecutorConfig
from app.multi_agent_framework import AgentMessage, AgentRole, MessageType


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

class TestExecutorAcceptsAuditCallback:
    """
    ExecutorAgent's __init__ must accept an audit_callback kwarg (inherited via
    BaseAgent.__init__). Regression guard: if the kwarg is ever removed, the
    wiring at strategy_wiring.py:EXECUTOR_AGENT = ExecutorAgent(...) will blow
    up with TypeError at import time.

    ExecutorAgent.__init__ 必須接受 audit_callback kwarg（透過 BaseAgent 繼承）。
    回歸守門：若此 kwarg 被移除，strategy_wiring.py 的 wiring 會在 import 階段
    TypeError 爆炸。
    """

    def test_ctor_accepts_audit_callback_kwarg(self):
        cal = ChangeAuditLog()
        hub = _FakeGovHub(cal)
        cb = make_agent_audit_callback(hub, "ExecutorAgent")

        # Must not raise
        agent = ExecutorAgent(
            config=ExecutorConfig(),
            message_bus=None,
            paper_engine=None,
            governance_hub=hub,
            audit_callback=cb,
        )
        assert agent is not None

    def test_ctor_accepts_none_audit_callback(self):
        """Without audit_callback, ExecutorAgent still constructs fine (fail-open)."""
        # 沒傳 audit_callback 時也必須可構造（fail-open）
        agent = ExecutorAgent(
            config=ExecutorConfig(),
            message_bus=None,
            paper_engine=None,
            governance_hub=None,
            audit_callback=None,
        )
        assert agent is not None


class TestExecutorAuditCallSiteWritesToLog:
    """
    End-to-end: when ExecutorAgent processes a SYSTEM_DIRECTIVE message, its
    self._audit("directive_received", ...) call flows through agent_audit_bridge
    into ChangeAuditLog. This is the acceptance proof for E5-FN-3-FUP-c.

    端到端：當 ExecutorAgent 處理 SYSTEM_DIRECTIVE 訊息時，
    self._audit("directive_received", ...) 會透過 agent_audit_bridge 寫入
    ChangeAuditLog。這是 E5-FN-3-FUP-c 的驗收證據。
    """

    def test_directive_received_triggers_record_change(self):
        cal = ChangeAuditLog()
        hub = _FakeGovHub(cal)
        audit_cb = make_agent_audit_callback(hub, "ExecutorAgent")

        agent = ExecutorAgent(
            config=ExecutorConfig(),
            message_bus=None,
            paper_engine=None,
            governance_hub=hub,
            audit_callback=audit_cb,
        )
        agent.start()

        # Precondition: no audit rows
        # 前置條件：無審計記錄
        assert cal.record_count() == 0

        # Dispatch a SYSTEM_DIRECTIVE — triggers self._audit("directive_received", ...)
        # 派發 SYSTEM_DIRECTIVE — 觸發 self._audit("directive_received", ...)
        msg = AgentMessage(
            sender=AgentRole.CONDUCTOR,
            receiver=AgentRole.EXECUTOR,
            message_type=MessageType.SYSTEM_DIRECTIVE,
            priority=3,
            payload={"directive_type": "pause", "reason": "e5fn3_fup_c_test"},
        )
        agent.on_message(msg)

        # Acceptance: at least one audit row attributed to ExecutorAgent with
        # "directive_received" in its `what` field.
        # 驗收：至少一筆 ExecutorAgent 的審計記錄，what 欄位含 "directive_received"。
        assert cal.record_count() >= 1
        rows = cal.get_all_changes()
        executor_rows = [r for r in rows if r.who == "ExecutorAgent"]
        assert len(executor_rows) >= 1

        directive_rows = [
            r for r in executor_rows if "directive_received" in r.what
        ]
        assert len(directive_rows) >= 1, (
            f"Expected directive_received audit row; got rows: "
            f"{[r.what for r in executor_rows]}"
        )

        row = directive_rows[0]
        # _audit() events named *_received → STATE_CHANGE (see bridge classification)
        # 以 *_received 結尾的事件 → STATE_CHANGE（bridge 分類規則）
        assert row.change_type == ChangeType.STATE_CHANGE
        assert row.approval_status == ChangeApprovalStatus.AUTO_APPROVED
        assert "ExecutorAgent" in row.affected_components
