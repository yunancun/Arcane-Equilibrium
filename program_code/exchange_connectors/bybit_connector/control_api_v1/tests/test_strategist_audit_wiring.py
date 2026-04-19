"""
Tests for StrategistAgent audit_callback wiring — E5-FN-3-FUP-a
==================================================================
StrategistAgent 審計回調接線測試

MODULE_NOTE (中文):
  驗證 StrategistAgent 的 __init__ 接受 audit_callback 參數，且當
  strategy_wiring.py 的 agent_audit_bridge 產出的 callback 被注入後，
  至少一個 self._audit(...) 呼叫點會觸發 GOV_HUB._change_audit_log
  的 record_change（PARAMETER_CHANGE 或 STATE_CHANGE 依事件分類而定）。

  這是 E5-FN-3（commit 19f3d85）AnalystAgent pilot 的 Strategist 擴展
  驗收測試，落實根原則 #8「交易可解釋」。

  覆蓋場景：
    1. Contract: StrategistAgent(..., audit_callback=cb) 建構不拋異常
    2. Integration: _handle_directive(...) 呼叫 self._audit("directive_received", ...)
       後 ChangeAuditLog 新增一條 STATE_CHANGE 記錄，who="StrategistAgent"

MODULE_NOTE (English):
  Verify StrategistAgent.__init__ accepts audit_callback, and that when a
  bridge callback from strategy_wiring.py's agent_audit_bridge is injected,
  at least one self._audit(...) call-site triggers GOV_HUB._change_audit_log
  .record_change (PARAMETER_CHANGE or STATE_CHANGE per event classification).

  This is the Strategist extension acceptance test for the AnalystAgent pilot
  (E5-FN-3, commit 19f3d85), implementing Root Principle #8 "Trade
  Explainability".

  Coverage:
    1. Contract: StrategistAgent(..., audit_callback=cb) constructs without error
    2. Integration: _handle_directive(...) → self._audit("directive_received", ...)
       → +1 STATE_CHANGE row in ChangeAuditLog, who="StrategistAgent"

Governance refs: CLAUDE.md §二 Root Principle #8, DOC-06 §5
"""

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


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers / 輔助
# ═══════════════════════════════════════════════════════════════════════════════

class _FakeGovHub:
    """
    Minimal stub mirroring the attribute surface required by agent_audit_bridge.
    仅暴露 bridge 用到的属性，不模拟 governance 业务逻辑。

    Mirrors test_agent_audit_bridge._FakeGovHub (intentional duplication —
    each test file owns its own stub to avoid coupling).
    與 test_agent_audit_bridge._FakeGovHub 對齊（刻意重複 — 每個測試檔自持 stub，
    避免耦合）。
    """

    def __init__(self, change_audit_log=None):
        self._change_audit_log = change_audit_log


# ═══════════════════════════════════════════════════════════════════════════════
# Tests / 測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestStrategistAcceptsAuditCallback:
    """
    Contract: StrategistAgent.__init__ must accept audit_callback kwarg and
    pass it to BaseAgent; construction must not raise.
    契約：StrategistAgent.__init__ 必須接受 audit_callback 參數並傳給 BaseAgent；
    建構不得拋異常。
    """

    def test_constructs_with_audit_callback(self):
        """
        Minimal ctor smoke: inject bridge callback built from fake GovHub +
        real ChangeAuditLog; confirm BaseAgent stores the callback.
        最小建構冒煙測試：注入由假 GovHub + 真實 ChangeAuditLog 建的 bridge
        callback，確認 BaseAgent 儲存了該 callback。
        """
        from app.strategist_agent import StrategistAgent, StrategistConfig

        cal = ChangeAuditLog()
        hub = _FakeGovHub(cal)
        cb = make_agent_audit_callback(hub, "StrategistAgent")

        agent = StrategistAgent(
            config=StrategistConfig(shadow=True),
            audit_callback=cb,
        )
        # BaseAgent stores the callback under _audit_callback (see base_agent.py).
        # BaseAgent 將 callback 存於 _audit_callback（見 base_agent.py）。
        assert agent._audit_callback is cb


class TestStrategistAuditWritesOnDirective:
    """
    Integration: a Strategist._audit(...) call-site (directive_received) writes
    a STATE_CHANGE row into ChangeAuditLog via the bridge.
    集成：Strategist._audit(...) 呼叫點（directive_received）經 bridge 寫入
    一條 STATE_CHANGE 記錄到 ChangeAuditLog。

    We pick _handle_directive because it has no dependencies on MessageBus
    routing, LLM clients, or Guardian wiring — just build an AgentMessage
    and call the handler directly.
    選 _handle_directive 是因為它不依賴 MessageBus 路由、LLM 客戶端或 Guardian
    接線 — 只需建 AgentMessage 後直呼 handler。
    """

    def test_directive_received_emits_audit_row(self):
        from app.strategist_agent import StrategistAgent, StrategistConfig
        from app.multi_agent_framework import (
            AgentMessage,
            AgentRole,
            MessageType,
        )

        cal = ChangeAuditLog()
        hub = _FakeGovHub(cal)
        cb = make_agent_audit_callback(hub, "StrategistAgent")

        agent = StrategistAgent(
            config=StrategistConfig(shadow=True),
            audit_callback=cb,
        )

        # Precondition: no audit rows yet / 前置：尚無審計記錄
        assert cal.record_count() == 0

        # Build a directive message and invoke the handler directly — this
        # call path hits self._audit("directive_received", payload) at
        # strategist_agent.py:569.
        # 構建 directive 訊息並直呼 handler — 此路徑觸發
        # strategist_agent.py:569 的 self._audit("directive_received", payload)。
        msg = AgentMessage(
            sender=AgentRole.CONDUCTOR,
            receiver=AgentRole.STRATEGIST,
            message_type=MessageType.SYSTEM_DIRECTIVE,
            priority=3,
            payload={"directive_type": "shadow_on"},
        )
        agent._handle_directive(msg)

        # Acceptance: at least one audit row attributed to StrategistAgent for
        # the directive_received event, classified as STATE_CHANGE (passive
        # receipt per agent_audit_bridge._STATE_EVENT_KEYWORDS).
        # 驗收：至少一條歸因 StrategistAgent 的 directive_received 審計記錄，
        # 分類為 STATE_CHANGE（依 agent_audit_bridge._STATE_EVENT_KEYWORDS 屬被動接收）。
        assert cal.record_count() >= 1
        rows = cal.get_all_changes()
        strat_rows = [r for r in rows if r.who == "StrategistAgent"]
        assert len(strat_rows) >= 1, (
            f"Expected StrategistAgent rows; got who={[r.who for r in rows]}"
        )

        directive_rows = [
            r for r in strat_rows if "directive_received" in r.what
        ]
        assert len(directive_rows) >= 1, (
            f"Expected directive_received row; got what="
            f"{[r.what for r in strat_rows]}"
        )

        row = directive_rows[0]
        assert row.change_type == ChangeType.STATE_CHANGE
        assert row.approval_status == ChangeApprovalStatus.AUTO_APPROVED
        assert "StrategistAgent" in row.affected_components
