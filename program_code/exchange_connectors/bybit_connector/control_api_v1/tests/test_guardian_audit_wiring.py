"""
Tests for GuardianAgent audit_callback wiring — E5-FN-3-FUP-b
============================================================
GuardianAgent audit_callback 接線測試（E5-FN-3-FUP-b）

MODULE_NOTE (中文):
  驗證 GuardianAgent 的 4 個 `self._audit(...)` call-site 在建構時注入
  `audit_callback` 後，能將事件成功橋接到 ChangeAuditLog.record_change(...)。

  覆蓋場景：
    1. GuardianAgent ctor 接受 audit_callback kwarg（無 TypeError）
    2. review_intent(...) → _audit("verdict", record) → ChangeAuditLog +1 row
    3. SYSTEM_DIRECTIVE 消息 → _audit("directive_received", ...) → +1 row
    4. audit_callback=None（預設）→ 不 raise、不寫入

MODULE_NOTE (English):
  Verify GuardianAgent's 4 `self._audit(...)` call-sites bridge into
  ChangeAuditLog.record_change(...) when audit_callback is injected via ctor.

  Coverage:
    1. GuardianAgent ctor accepts audit_callback kwarg (no TypeError)
    2. review_intent(...) → _audit("verdict", record) → +1 ChangeAuditLog row
    3. SYSTEM_DIRECTIVE on_message → _audit("directive_received", ...) → +1 row
    4. audit_callback=None (default) → no raise, no write

Governance refs: CLAUDE.md §二 Root Principle #8, DOC-06 §5, E5-FN-3-FUP-b brief
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent_audit_bridge import make_agent_audit_callback
from app.change_audit_log import (
    ChangeAuditLog,
    ChangeApprovalStatus,
    ChangeType,
)
from app.guardian_agent import GuardianAgent, GuardianConfig
from app.multi_agent_framework import (
    AgentMessage,
    AgentRole,
    MessageType,
    TradeIntent,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers / 輔助
# ═══════════════════════════════════════════════════════════════════════════════

class _FakeGovHub:
    """
    Minimal GovernanceHub stub — only exposes the attribute the bridge reads
    (`_change_audit_log`). Mirrors the pattern in test_agent_audit_bridge.py.

    最小 GovernanceHub stub，僅暴露 bridge 讀取的屬性 `_change_audit_log`。
    """

    def __init__(self, change_audit_log=None):
        self._change_audit_log = change_audit_log


def _make_guardian(audit_callback=None) -> GuardianAgent:
    """
    Build a bare GuardianAgent without MessageBus/RiskManager/Ollama side effects.
    For audit-wiring tests we only care about the ctor + `_audit(...)` plumbing.

    構建最小 GuardianAgent（無 MessageBus/RiskManager/Ollama 依賴），
    只驗 ctor 和 _audit 接線。
    """
    return GuardianAgent(
        config=GuardianConfig(),
        message_bus=None,
        risk_manager=None,
        ollama_client=None,
        governance_hub=None,
        audit_callback=audit_callback,
    )


def _make_simple_intent() -> TradeIntent:
    """
    TradeIntent that should survive all 5 Guardian checks → APPROVED verdict.
    Low leverage + no conflicting positions → fastest path to a `verdict` audit row.

    一筆能通過全部 5 項檢查的 TradeIntent → APPROVED 裁決，
    最短路徑觸發 `verdict` 審計記錄。
    """
    return TradeIntent(
        symbol="BTCUSDT",
        strategy="audit_wiring_test",
        direction="long",
        size=0.01,
        params={"leverage": 1.0},
        confidence=0.8,
        thesis="audit-wiring smoke test",
        invalidation_condition="stop_loss",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Tests / 測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestGuardianCtorAcceptsAuditCallback:
    """GuardianAgent ctor must accept the audit_callback kwarg without TypeError."""

    def test_ctor_with_audit_callback_kwarg(self):
        """ctor 接受 audit_callback kwarg / ctor accepts audit_callback kwarg."""
        cal = ChangeAuditLog()
        cb = make_agent_audit_callback(_FakeGovHub(cal), "GuardianAgent")
        agent = _make_guardian(audit_callback=cb)
        assert agent is not None
        # audit_callback is stored on BaseAgent; verify the bridge reference
        # is attached (attribute name defined by BaseAgent).
        # audit_callback 由 BaseAgent 保存；驗 bridge 參考已綁定。
        assert getattr(agent, "_audit_callback", None) is cb

    def test_ctor_with_default_none_callback(self):
        """Backwards compat: no audit_callback → no raise / 無 callback 向後相容。"""
        agent = _make_guardian(audit_callback=None)
        assert agent is not None


class TestGuardianVerdictEmitsAuditRow:
    """
    review_intent(APPROVED path) → _audit("verdict", record) → ChangeAuditLog +1 row.
    This is the acceptance proof for E5-FN-3-FUP-b per task brief.

    review_intent(APPROVED 路徑) → _audit("verdict", record) → ChangeAuditLog 新增一條，
    為 E5-FN-3-FUP-b 任務簡報的驗收證據。
    """

    def test_verdict_writes_audit_row_via_bridge(self):
        cal = ChangeAuditLog()
        hub = _FakeGovHub(cal)
        cb = make_agent_audit_callback(hub, "GuardianAgent")
        agent = _make_guardian(audit_callback=cb)
        agent.start()

        # Precondition: no rows / 前置條件：零條
        assert cal.record_count() == 0

        # Trigger: review a simple intent (should APPROVE)
        # 觸發：審查一筆簡單 intent（應 APPROVE）
        intent = _make_simple_intent()
        verdict = agent.review_intent(intent)
        assert verdict is not None

        # Acceptance: at least one audit row attributed to GuardianAgent
        # 驗收：至少一條歸屬於 GuardianAgent 的審計記錄
        assert cal.record_count() >= 1
        rows = cal.get_all_changes()
        guardian_rows = [r for r in rows if r.who == "GuardianAgent"]
        assert len(guardian_rows) >= 1

        verdict_rows = [r for r in guardian_rows if "verdict" in r.what]
        assert len(verdict_rows) >= 1, (
            f"Expected verdict audit row; got rows: "
            f"{[r.what for r in guardian_rows]}"
        )

        row = verdict_rows[0]
        # Decision events classify as PARAMETER_CHANGE in agent_audit_bridge.
        # 決策類事件在 bridge 中歸類為 PARAMETER_CHANGE。
        assert row.change_type == ChangeType.PARAMETER_CHANGE
        assert row.approval_status == ChangeApprovalStatus.AUTO_APPROVED
        assert "GuardianAgent" in row.affected_components


class TestGuardianDirectiveEmitsStateChange:
    """
    SYSTEM_DIRECTIVE → _handle_directive(...) → _audit("directive_received", ...).
    Passive-receipt events classify as STATE_CHANGE in the bridge.

    SYSTEM_DIRECTIVE → _handle_directive(...) → _audit("directive_received", ...)，
    被動接收類事件歸類為 STATE_CHANGE。
    """

    def test_directive_received_is_state_change(self):
        cal = ChangeAuditLog()
        hub = _FakeGovHub(cal)
        cb = make_agent_audit_callback(hub, "GuardianAgent")
        agent = _make_guardian(audit_callback=cb)
        agent.start()

        msg = AgentMessage(
            sender=AgentRole.CONDUCTOR,
            receiver=AgentRole.GUARDIAN,
            message_type=MessageType.SYSTEM_DIRECTIVE,
            priority=3,
            payload={"directive_type": "pause", "source": "audit_test"},
        )
        agent.on_message(msg)

        rows = cal.get_all_changes()
        assert len(rows) >= 1
        directive_rows = [r for r in rows if "directive_received" in r.what]
        assert len(directive_rows) >= 1, (
            f"Expected directive_received audit row; got rows: "
            f"{[r.what for r in rows]}"
        )
        assert directive_rows[0].change_type == ChangeType.STATE_CHANGE
        assert directive_rows[0].who == "GuardianAgent"


class TestGuardianAuditFailOpen:
    """
    Fail-open invariant: audit_callback=None / gov_hub=None / missing log must
    NOT raise from Guardian's core review or message-handling paths.

    fail-open 不變量：audit_callback=None / gov_hub=None / 缺 audit log
    絕不可讓 Guardian 核心審查或訊息處理路徑拋出。
    """

    def test_no_callback_does_not_raise_on_verdict(self):
        agent = _make_guardian(audit_callback=None)
        agent.start()
        # Should not raise, should return a verdict.
        # 不可 raise，應回傳 verdict。
        verdict = agent.review_intent(_make_simple_intent())
        assert verdict is not None

    def test_bridge_with_none_hub_does_not_raise(self):
        cb = make_agent_audit_callback(None, "GuardianAgent")
        agent = _make_guardian(audit_callback=cb)
        agent.start()
        verdict = agent.review_intent(_make_simple_intent())
        assert verdict is not None
