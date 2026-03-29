"""
Tests for OMS State Machine Supplement — EX-02 / GAP-H1
OMS 订单执行状态机补充测试

Covers:
  - 11 states, 16 transitions, 12 forbidden
  - Pre-execution flow (CREATED → PENDING → APPROVED)
  - Execution flow (SUBMITTED → WORKING → FILLED)
  - Post-execution flow (FILLED → RECONCILING → COMPLETED)
  - Forbidden transitions (skip auth, skip reconciliation, terminal exit)
  - Guard conditions (initiator checks)
  - Audit callback integration
  - Paper Engine state mapping
  - Persistence (export/import)
  - Thread safety
  - Full lifecycle scenarios
"""

import sys
import threading
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.oms_state_machine import (
    ACTIVE_STATES,
    FORBIDDEN_TRANSITIONS,
    OMS_TRANSITION_RULES,
    TERMINAL_STATES,
    OMSOrder,
    OMSStateMachine,
    OMSTransitionRule,
    OrderEvent,
    OrderInitiator,
    OrderState,
)

# Import shared fixtures and helpers from conftest
from conftest import (
    oms_state_machine as sm,
    _create_and_advance_oms_order,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Constants / 常量测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestConstants:
    def test_eleven_states(self):
        assert len(OrderState) == 11

    def test_terminal_states(self):
        assert TERMINAL_STATES == frozenset({
            OrderState.COMPLETED, OrderState.CANCELED, OrderState.REJECTED,
        })

    def test_active_states(self):
        assert OrderState.PENDING in ACTIVE_STATES
        assert OrderState.RECONCILING in ACTIVE_STATES
        assert OrderState.COMPLETED not in ACTIVE_STATES

    def test_transition_count(self):
        assert len(OMS_TRANSITION_RULES) == 16

    def test_forbidden_count(self):
        assert len(FORBIDDEN_TRANSITIONS) == 12

    def test_no_overlap(self):
        """Valid and forbidden transitions should not overlap / 有效与禁止不应重叠"""
        valid_keys = set(OMS_TRANSITION_RULES.keys())
        assert valid_keys.isdisjoint(FORBIDDEN_TRANSITIONS)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Order Creation / 订单创建测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestOrderCreation:
    def test_create_order(self, sm):
        oid = sm.create_order(symbol="BTCUSDT", side="Buy", qty=0.1)
        order = sm.get(oid)
        assert order is not None
        assert order["state"] == "CREATED"
        assert order["symbol"] == "BTCUSDT"

    def test_order_id_prefix(self, sm):
        oid = sm.create_order(symbol="BTCUSDT", side="Buy", qty=0.1)
        assert oid.startswith("oms:")

    def test_created_is_not_active(self, sm):
        oid = sm.create_order(symbol="BTCUSDT", side="Buy", qty=0.1)
        order = sm.get(oid)
        assert not order["is_active"]
        assert not order["is_terminal"]


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Pre-Execution Flow / 执行前流程测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestPreExecutionFlow:
    def test_created_to_pending(self, sm):
        oid = _create_and_advance_oms_order(sm, OrderState.PENDING)
        assert sm.get(oid)["state"] == "PENDING"

    def test_pending_to_approved(self, sm):
        oid = _create_and_advance_oms_order(sm, OrderState.APPROVED)
        assert sm.get(oid)["state"] == "APPROVED"
        assert sm.get(oid)["approved_by"] == "AuthorizationSM"

    def test_pending_to_rejected(self, sm):
        oid = _create_and_advance_oms_order(sm, OrderState.PENDING)
        sm.reject(oid, OrderInitiator.AUTHORIZATION_SM, reason="Risk limit exceeded")
        assert sm.get(oid)["state"] == "REJECTED"
        assert sm.get(oid)["is_terminal"]

    def test_pending_to_canceled(self, sm):
        oid = _create_and_advance_oms_order(sm, OrderState.PENDING)
        sm.cancel(oid, OrderInitiator.OPERATOR)
        assert sm.get(oid)["state"] == "CANCELED"

    def test_approved_to_canceled(self, sm):
        oid = _create_and_advance_oms_order(sm, OrderState.APPROVED)
        sm.cancel(oid, OrderInitiator.OPERATOR)
        assert sm.get(oid)["state"] == "CANCELED"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Execution Flow / 执行流程测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestExecutionFlow:
    def test_approved_to_submitted(self, sm):
        oid = _create_and_advance_oms_order(sm, OrderState.SUBMITTED)
        assert sm.get(oid)["state"] == "SUBMITTED"

    def test_submitted_to_working(self, sm):
        oid = _create_and_advance_oms_order(sm, OrderState.WORKING)
        assert sm.get(oid)["state"] == "WORKING"

    def test_submitted_to_rejected(self, sm):
        oid = _create_and_advance_oms_order(sm, OrderState.SUBMITTED)
        sm.transition(oid, OrderState.REJECTED, OrderInitiator.EXECUTION_VENUE, reason="Insufficient margin")
        assert sm.get(oid)["state"] == "REJECTED"

    def test_working_to_partial_fill(self, sm):
        oid = _create_and_advance_oms_order(sm, OrderState.PARTIALLY_FILLED)
        assert sm.get(oid)["state"] == "PARTIALLY_FILLED"

    def test_working_to_filled(self, sm):
        oid = _create_and_advance_oms_order(sm, OrderState.FILLED)
        assert sm.get(oid)["state"] == "FILLED"

    def test_partial_to_filled(self, sm):
        oid = _create_and_advance_oms_order(sm, OrderState.PARTIALLY_FILLED)
        sm.fill(oid, OrderInitiator.EXECUTION_VENUE)
        assert sm.get(oid)["state"] == "FILLED"

    def test_working_to_canceled(self, sm):
        oid = _create_and_advance_oms_order(sm, OrderState.WORKING)
        sm.cancel(oid, OrderInitiator.OPERATOR)
        assert sm.get(oid)["state"] == "CANCELED"

    def test_partial_to_canceled(self, sm):
        oid = _create_and_advance_oms_order(sm, OrderState.PARTIALLY_FILLED)
        sm.cancel(oid, OrderInitiator.RISK_GOVERNOR, reason="Risk limit")
        assert sm.get(oid)["state"] == "CANCELED"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Post-Execution Flow / 执行后流程测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestPostExecutionFlow:
    def test_filled_to_reconciling(self, sm):
        oid = _create_and_advance_oms_order(sm, OrderState.RECONCILING)
        assert sm.get(oid)["state"] == "RECONCILING"
        assert sm.get(oid)["is_active"]

    def test_reconciling_to_completed(self, sm):
        oid = _create_and_advance_oms_order(sm, OrderState.RECONCILING)
        sm.reconciliation_pass(oid, OrderInitiator.RECONCILIATION_ENGINE)
        order = sm.get(oid)
        assert order["state"] == "COMPLETED"
        assert order["is_terminal"]

    def test_reconciling_to_rejected(self, sm):
        oid = _create_and_advance_oms_order(sm, OrderState.RECONCILING)
        sm.reconciliation_fail(oid, OrderInitiator.RECONCILIATION_ENGINE, reason="Position mismatch")
        assert sm.get(oid)["state"] == "REJECTED"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Forbidden Transitions / 禁止转换测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestForbiddenTransitions:
    def test_cannot_skip_authorization(self, sm):
        """CREATED → SUBMITTED is forbidden / 不可跳过授权"""
        oid = sm.create_order(symbol="BTCUSDT", side="Buy", qty=0.1)
        with pytest.raises(ValueError, match="Forbidden"):
            sm.transition(oid, OrderState.SUBMITTED, OrderInitiator.SYSTEM)

    def test_cannot_skip_pending(self, sm):
        """CREATED → APPROVED is forbidden / 不可跳过 PENDING"""
        oid = sm.create_order(symbol="BTCUSDT", side="Buy", qty=0.1)
        with pytest.raises(ValueError, match="Forbidden"):
            sm.transition(oid, OrderState.APPROVED, OrderInitiator.SYSTEM)

    def test_cannot_skip_reconciliation(self, sm):
        """FILLED → COMPLETED is forbidden / 不可跳过对账"""
        oid = _create_and_advance_oms_order(sm, OrderState.FILLED)
        with pytest.raises(ValueError, match="Forbidden"):
            sm.transition(oid, OrderState.COMPLETED, OrderInitiator.SYSTEM)

    def test_completed_cannot_exit(self, sm):
        """COMPLETED is terminal / COMPLETED 为终态"""
        oid = _create_and_advance_oms_order(sm, OrderState.COMPLETED)
        with pytest.raises(ValueError):
            sm.transition(oid, OrderState.RECONCILING, OrderInitiator.SYSTEM)

    def test_canceled_cannot_restart(self, sm):
        """CANCELED cannot go back to PENDING / CANCELED 不可重回 PENDING"""
        oid = _create_and_advance_oms_order(sm, OrderState.PENDING)
        sm.cancel(oid, OrderInitiator.OPERATOR)
        with pytest.raises(ValueError):
            sm.transition(oid, OrderState.PENDING, OrderInitiator.SYSTEM)

    def test_working_cannot_go_back(self, sm):
        """WORKING → SUBMITTED is forbidden / 不可倒退"""
        oid = _create_and_advance_oms_order(sm, OrderState.WORKING)
        with pytest.raises(ValueError, match="Forbidden"):
            sm.transition(oid, OrderState.SUBMITTED, OrderInitiator.SYSTEM)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Guards / 守卫条件测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestGuards:
    def test_wrong_initiator_for_approval(self, sm):
        """AI_AGENT cannot approve orders / AI_AGENT 不可审批订单"""
        oid = _create_and_advance_oms_order(sm, OrderState.PENDING)
        with pytest.raises(ValueError, match="not allowed"):
            sm.approve(oid, OrderInitiator.AI_AGENT)

    def test_wrong_initiator_for_fill(self, sm):
        """OPERATOR cannot directly fill / OPERATOR 不可直接成交"""
        oid = _create_and_advance_oms_order(sm, OrderState.WORKING)
        with pytest.raises(ValueError, match="not allowed"):
            sm.fill(oid, OrderInitiator.OPERATOR)

    def test_wrong_initiator_for_reconciliation(self, sm):
        """AI_AGENT cannot begin reconciliation / AI_AGENT 不可开始对账"""
        oid = _create_and_advance_oms_order(sm, OrderState.FILLED)
        with pytest.raises(ValueError, match="not allowed"):
            sm.begin_reconciliation(oid, OrderInitiator.AI_AGENT)

    def test_nonexistent_order(self, sm):
        with pytest.raises(KeyError):
            sm.transition("fake_id", OrderState.PENDING, OrderInitiator.SYSTEM)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Audit Callback / 审计回调测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditCallback:
    def test_callback_on_transition(self):
        audits = []
        sm = OMSStateMachine(audit_callback=lambda r: audits.append(r))
        oid = sm.create_order(symbol="BTCUSDT", side="Buy", qty=0.1)
        sm.submit_for_approval(oid, OrderInitiator.AI_AGENT)
        assert len(audits) == 1
        assert audits[0]["from_state"] == "CREATED"
        assert audits[0]["to_state"] == "PENDING"
        sm.close()

    def test_audit_has_order_id(self):
        audits = []
        sm = OMSStateMachine(audit_callback=lambda r: audits.append(r))
        oid = sm.create_order(symbol="BTCUSDT", side="Buy", qty=0.1)
        sm.submit_for_approval(oid, OrderInitiator.AI_AGENT)
        assert audits[0]["order_id"] == oid
        assert audits[0]["symbol"] == "BTCUSDT"
        sm.close()


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Queries / 查询测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestQueries:
    def test_get_active_orders(self, sm):
        oid1 = _create_and_advance_oms_order(sm, OrderState.WORKING)
        oid2 = _create_and_advance_oms_order(sm, OrderState.PENDING)
        oid3 = _create_and_advance_oms_order(sm, OrderState.COMPLETED)

        active = sm.get_active_orders()
        active_ids = {o["order_id"] for o in active}
        assert oid1 in active_ids
        assert oid2 in active_ids
        assert oid3 not in active_ids

    def test_get_reconciling(self, sm):
        oid = _create_and_advance_oms_order(sm, OrderState.RECONCILING)
        recon = sm.get_reconciling_orders()
        assert len(recon) == 1
        assert recon[0]["order_id"] == oid

    def test_get_pending_approval(self, sm):
        oid = _create_and_advance_oms_order(sm, OrderState.PENDING)
        pending = sm.get_pending_approval()
        assert len(pending) == 1

    def test_status_summary(self, sm):
        _create_and_advance_oms_order(sm, OrderState.WORKING)
        _create_and_advance_oms_order(sm, OrderState.COMPLETED)
        summary = sm.status_summary()
        assert summary["WORKING"] == 1
        assert summary["COMPLETED"] == 1

    def test_get_nonexistent(self, sm):
        assert sm.get("fake_id") is None


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Paper Engine Mapping / Paper Engine 映射测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestPaperEngineMapping:
    def test_map_from_paper_state(self):
        assert OMSStateMachine.map_from_paper_state("paper_order_created") == OrderState.CREATED
        assert OMSStateMachine.map_from_paper_state("paper_order_working") == OrderState.WORKING
        assert OMSStateMachine.map_from_paper_state("paper_order_filled") == OrderState.FILLED

    def test_map_to_paper_state(self):
        assert OMSStateMachine.map_to_paper_state(OrderState.CREATED) == "paper_order_created"
        assert OMSStateMachine.map_to_paper_state(OrderState.FILLED) == "paper_order_filled"

    def test_new_states_have_no_paper_equivalent(self):
        for state in (OrderState.PENDING, OrderState.APPROVED, OrderState.RECONCILING, OrderState.COMPLETED):
            with pytest.raises(ValueError, match="no paper engine equivalent"):
                OMSStateMachine.map_to_paper_state(state)

    def test_unknown_paper_state_raises(self):
        with pytest.raises(ValueError, match="Unknown paper state"):
            OMSStateMachine.map_from_paper_state("paper_order_unknown")


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Persistence / 持久化测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestPersistence:
    def test_export_import_roundtrip(self, sm):
        oid = _create_and_advance_oms_order(sm, OrderState.RECONCILING)
        exported = sm.export_state()

        sm2 = OMSStateMachine()
        count = sm2.import_state(exported)
        assert count == 1

        order = sm2.get(oid)
        assert order is not None
        assert order["state"] == "RECONCILING"
        sm2.close()


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Thread Safety / 线程安全测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestThreadSafety:
    def test_concurrent_lifecycle(self, sm):
        """Concurrent order lifecycles should not corrupt state / 并发生命周期不应损坏状态"""
        errors = []

        def worker(thread_id):
            try:
                for i in range(5):
                    oid = sm.create_order(symbol="BTCUSDT", side="Buy", qty=0.01)
                    sm.submit_for_approval(oid, OrderInitiator.AI_AGENT)
                    sm.approve(oid, OrderInitiator.AUTHORIZATION_SM)
                    sm.send_to_venue(oid, OrderInitiator.SYSTEM)
                    sm.acknowledge(oid, OrderInitiator.EXECUTION_VENUE)
                    sm.fill(oid, OrderInitiator.EXECUTION_VENUE)
                    sm.begin_reconciliation(oid, OrderInitiator.RECONCILIATION_ENGINE)
                    sm.reconciliation_pass(oid, OrderInitiator.RECONCILIATION_ENGINE)
                    assert sm.get(oid)["state"] == "COMPLETED"
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0
        summary = sm.status_summary()
        assert summary.get("COMPLETED", 0) == 25


# ═══════════════════════════════════════════════════════════════════════════════
# 13. Full Lifecycle / 完整生命周期测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestFullLifecycle:
    def test_happy_path(self, sm):
        """Full happy path: CREATED → ... → COMPLETED / 完整正常路径"""
        oid = _create_and_advance_oms_order(sm, OrderState.COMPLETED)
        order = sm.get(oid)
        assert order["state"] == "COMPLETED"
        assert order["is_terminal"]
        assert order["transition_count"] == 7  # 7 transitions (no partial fill in happy path)

    def test_early_rejection_at_pending(self, sm):
        """Rejection at authorization / 授权阶段拒绝"""
        oid = _create_and_advance_oms_order(sm, OrderState.PENDING)
        sm.reject(oid, OrderInitiator.RISK_GOVERNOR, reason="Position limit exceeded")
        assert sm.get(oid)["state"] == "REJECTED"
        assert sm.get(oid)["transition_count"] == 2

    def test_reconciliation_failure(self, sm):
        """Reconciliation fails → REJECTED / 对账失败 → REJECTED"""
        oid = _create_and_advance_oms_order(sm, OrderState.RECONCILING)
        sm.reconciliation_fail(oid, OrderInitiator.RECONCILIATION_ENGINE, reason="Position mismatch detected")
        order = sm.get(oid)
        assert order["state"] == "REJECTED"
        assert order["is_terminal"]

    def test_cancel_at_working(self, sm):
        """Cancel while working on book / 挂单时取消"""
        oid = _create_and_advance_oms_order(sm, OrderState.WORKING)
        sm.cancel(oid, OrderInitiator.RISK_GOVERNOR, reason="Emergency stop")
        assert sm.get(oid)["state"] == "CANCELED"

    def test_partial_fill_then_cancel(self, sm):
        """Partial fill then cancel / 部分成交后取消"""
        oid = _create_and_advance_oms_order(sm, OrderState.PARTIALLY_FILLED)
        sm.cancel(oid, OrderInitiator.OPERATOR)
        assert sm.get(oid)["state"] == "CANCELED"
