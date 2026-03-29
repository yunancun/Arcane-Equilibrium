"""
Tests for Decision Lease State Machine — SM-02 Governance Spec
决策租约状态机测试 — SM-02 治理规范

Covers:
  - All 9 states, 19 valid transitions
  - 12 forbidden transitions
  - Terminal state immutability
  - Guard conditions (initiator, approval)
  - Expiry guardian
  - Full lifecycle (happy path, freeze/recovery, consume)
  - Persistence (export/import)
  - Thread safety
  - Audit trail
"""

import sys
import threading
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.decision_lease_state_machine import (
    DecisionLeaseStateMachine,
    DecisionLeaseObject,
    FORBIDDEN_TRANSITIONS,
    LEASE_TRANSITION_RULES,
    LeaseError,
    LeaseEvent,
    LeaseInitiator,
    LeaseState,
    TERMINAL_STATES,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def sm():
    return DecisionLeaseStateMachine()


@pytest.fixture
def sm_with_audit():
    records = []
    machine = DecisionLeaseStateMachine(audit_callback=lambda r: records.append(r))
    return machine, records


@pytest.fixture
def draft_lease(sm):
    return sm.create_draft(
        intent={"direction": "long", "symbol": "BTCUSDT", "category": "linear"},
        created_by="H5_pipeline",
        expires_at_ms=int(time.time() * 1000) + 3600_000,
    )


@pytest.fixture
def active_lease(sm, draft_lease):
    sm.register(draft_lease.lease_id)
    return sm.activate(draft_lease.lease_id)


def _make_active(sm) -> DecisionLeaseObject:
    lease = sm.create_draft(intent={"symbol": "ETHUSDT"}, created_by="test")
    sm.register(lease.lease_id)
    sm.activate(lease.lease_id)
    return sm.get(lease.lease_id)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Constants
# ═══════════════════════════════════════════════════════════════════════════════

class TestConstants:
    def test_nine_states(self):
        assert len(LeaseState) == 9

    def test_terminal_states(self):
        assert TERMINAL_STATES == frozenset({
            LeaseState.REVOKED, LeaseState.EXPIRED,
            LeaseState.REJECTED, LeaseState.CONSUMED,
        })

    def test_transition_count(self):
        assert len(LEASE_TRANSITION_RULES) == 18

    def test_forbidden_count(self):
        assert len(FORBIDDEN_TRANSITIONS) == 12

    def test_no_overlap(self):
        assert set(LEASE_TRANSITION_RULES.keys()).isdisjoint(FORBIDDEN_TRANSITIONS)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Draft Creation
# ═══════════════════════════════════════════════════════════════════════════════

class TestDraft:
    def test_create_draft(self, sm):
        lease = sm.create_draft(intent={"symbol": "BTC"}, created_by="test")
        assert lease.state == LeaseState.DRAFT
        assert lease.lease_id.startswith("lease:")
        assert len(lease.transitions) == 1

    def test_draft_not_live(self, sm):
        lease = sm.create_draft(intent={}, created_by="t")
        assert not lease.is_live
        assert not lease.is_terminal


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Valid Transitions (all 19)
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidTransitions:
    # §7.1 Draft
    def test_draft_to_registered(self, sm, draft_lease):
        r = sm.register(draft_lease.lease_id)
        assert r.state == LeaseState.REGISTERED

    def test_draft_to_rejected(self, sm, draft_lease):
        r = sm.reject(draft_lease.lease_id, reason="bad")
        assert r.state == LeaseState.REJECTED

    # §7.2 Registered
    def test_registered_to_active(self, sm, draft_lease):
        sm.register(draft_lease.lease_id)
        r = sm.activate(draft_lease.lease_id)
        assert r.state == LeaseState.ACTIVE

    def test_registered_to_frozen(self, sm, draft_lease):
        sm.register(draft_lease.lease_id)
        r = sm.freeze(draft_lease.lease_id, reason="incident")
        assert r.state == LeaseState.FROZEN

    def test_registered_to_revoked(self, sm, draft_lease):
        sm.register(draft_lease.lease_id)
        r = sm.revoke(draft_lease.lease_id, approved_by="op1")
        assert r.state == LeaseState.REVOKED

    def test_registered_to_expired(self, sm, draft_lease):
        sm.register(draft_lease.lease_id)
        r = sm.transition(draft_lease.lease_id, LeaseState.EXPIRED,
                          event=LeaseEvent.EXPIRED_BY_TIME,
                          initiator=LeaseInitiator.EXPIRY_GUARDIAN,
                          reason_codes=["time_expiry"])
        assert r.state == LeaseState.EXPIRED

    def test_registered_to_rejected(self, sm, draft_lease):
        sm.register(draft_lease.lease_id)
        r = sm.reject(draft_lease.lease_id, reason="post-validation")
        assert r.state == LeaseState.REJECTED

    # §7.3 Active
    def test_active_to_bridged(self, sm, active_lease):
        r = sm.bridge(active_lease.lease_id)
        assert r.state == LeaseState.BRIDGED

    def test_active_to_frozen(self, sm, active_lease):
        r = sm.freeze(active_lease.lease_id, reason="incident")
        assert r.state == LeaseState.FROZEN

    def test_active_to_revoked(self, sm, active_lease):
        r = sm.revoke(active_lease.lease_id, approved_by="op1")
        assert r.state == LeaseState.REVOKED

    def test_active_to_expired(self, sm, active_lease):
        r = sm.transition(active_lease.lease_id, LeaseState.EXPIRED,
                          event=LeaseEvent.EXPIRED_BY_TIME,
                          initiator=LeaseInitiator.EXPIRY_GUARDIAN,
                          reason_codes=["time_expiry"])
        assert r.state == LeaseState.EXPIRED

    def test_active_to_rejected(self, sm, active_lease):
        r = sm.reject(active_lease.lease_id, reason="risk rejection")
        assert r.state == LeaseState.REJECTED

    # §7.4 Frozen
    def test_frozen_to_registered(self, sm, active_lease):
        sm.freeze(active_lease.lease_id, reason="test")
        r = sm.unfreeze_to_registered(active_lease.lease_id, approved_by="op1")
        assert r.state == LeaseState.REGISTERED

    def test_frozen_to_active(self, sm, active_lease):
        sm.freeze(active_lease.lease_id, reason="test")
        r = sm.unfreeze_to_active(active_lease.lease_id, approved_by="op1")
        assert r.state == LeaseState.ACTIVE

    def test_frozen_to_revoked(self, sm, active_lease):
        sm.freeze(active_lease.lease_id, reason="test")
        r = sm.revoke(active_lease.lease_id, approved_by="op1")
        assert r.state == LeaseState.REVOKED

    def test_frozen_to_expired(self, sm, active_lease):
        sm.freeze(active_lease.lease_id, reason="test")
        r = sm.transition(active_lease.lease_id, LeaseState.EXPIRED,
                          event=LeaseEvent.EXPIRED_BY_TIME,
                          initiator=LeaseInitiator.EXPIRY_GUARDIAN,
                          reason_codes=["time_expiry"])
        assert r.state == LeaseState.EXPIRED

    # §7.5 Bridged
    def test_bridged_to_consumed(self, sm, active_lease):
        sm.bridge(active_lease.lease_id)
        r = sm.consume(active_lease.lease_id)
        assert r.state == LeaseState.CONSUMED

    def test_bridged_to_revoked(self, sm, active_lease):
        sm.bridge(active_lease.lease_id)
        r = sm.revoke(active_lease.lease_id, approved_by="op1")
        assert r.state == LeaseState.REVOKED


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Forbidden Transitions
# ═══════════════════════════════════════════════════════════════════════════════

class TestForbiddenTransitions:
    def test_draft_to_active_forbidden(self, sm, draft_lease):
        with pytest.raises(LeaseError, match="Forbidden|not in transition"):
            sm.transition(draft_lease.lease_id, LeaseState.ACTIVE,
                          event=LeaseEvent.ACTIVATION_WINDOW_OPEN,
                          initiator=LeaseInitiator.I_CONTROL_PLANE)

    def test_draft_to_bridged_forbidden(self, sm, draft_lease):
        with pytest.raises(LeaseError, match="Forbidden|not in transition"):
            sm.transition(draft_lease.lease_id, LeaseState.BRIDGED,
                          event=LeaseEvent.BRIDGE_APPROVED,
                          initiator=LeaseInitiator.RISK_GOVERNOR)

    def test_registered_to_bridged_forbidden(self, sm, draft_lease):
        sm.register(draft_lease.lease_id)
        with pytest.raises(LeaseError, match="Forbidden|not in transition"):
            sm.transition(draft_lease.lease_id, LeaseState.BRIDGED,
                          event=LeaseEvent.BRIDGE_APPROVED,
                          initiator=LeaseInitiator.RISK_GOVERNOR)

    def test_revoked_cannot_reactivate(self, sm, active_lease):
        sm.revoke(active_lease.lease_id, approved_by="op1")
        with pytest.raises(LeaseError, match="terminal"):
            sm.transition(active_lease.lease_id, LeaseState.ACTIVE,
                          event=LeaseEvent.RECOVERY_APPROVED,
                          initiator=LeaseInitiator.OPERATOR, approved_by="op1")

    def test_consumed_cannot_re_bridge(self, sm, active_lease):
        sm.bridge(active_lease.lease_id)
        sm.consume(active_lease.lease_id)
        with pytest.raises(LeaseError, match="terminal"):
            sm.transition(active_lease.lease_id, LeaseState.BRIDGED,
                          event=LeaseEvent.BRIDGE_APPROVED,
                          initiator=LeaseInitiator.RISK_GOVERNOR)

    def test_expired_cannot_reactivate(self, sm, active_lease):
        sm.transition(active_lease.lease_id, LeaseState.EXPIRED,
                      event=LeaseEvent.EXPIRED_BY_TIME,
                      initiator=LeaseInitiator.EXPIRY_GUARDIAN,
                      reason_codes=["time_expiry"])
        with pytest.raises(LeaseError, match="terminal"):
            sm.activate(active_lease.lease_id)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Guard Conditions
# ═══════════════════════════════════════════════════════════════════════════════

class TestGuards:
    def test_revoke_requires_approval(self, sm, active_lease):
        with pytest.raises(LeaseError, match="approval"):
            sm.transition(active_lease.lease_id, LeaseState.REVOKED,
                          event=LeaseEvent.REVOKE_REQUESTED,
                          initiator=LeaseInitiator.OPERATOR)

    def test_unfreeze_requires_approval(self, sm, active_lease):
        sm.freeze(active_lease.lease_id, reason="test")
        with pytest.raises(LeaseError, match="approval"):
            sm.transition(active_lease.lease_id, LeaseState.ACTIVE,
                          event=LeaseEvent.RECOVERY_APPROVED,
                          initiator=LeaseInitiator.OPERATOR)

    def test_wrong_initiator(self, sm, active_lease):
        with pytest.raises(LeaseError, match="not allowed"):
            sm.transition(active_lease.lease_id, LeaseState.BRIDGED,
                          event=LeaseEvent.BRIDGE_APPROVED,
                          initiator=LeaseInitiator.EXPIRY_GUARDIAN)

    def test_nonexistent_lease(self, sm):
        with pytest.raises(LeaseError, match="not found"):
            sm.transition("lease:fake", LeaseState.ACTIVE,
                          event=LeaseEvent.ACTIVATION_WINDOW_OPEN,
                          initiator=LeaseInitiator.I_CONTROL_PLANE)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Expiry Guardian
# ═══════════════════════════════════════════════════════════════════════════════

class TestExpiry:
    def test_auto_expire(self, sm):
        lease = sm.create_draft(
            intent={}, created_by="t",
            expires_at_ms=int(time.time() * 1000) - 1000,
        )
        sm.register(lease.lease_id)
        sm.activate(lease.lease_id)
        expired = sm.check_expiry()
        assert lease.lease_id in expired

    def test_no_expire_if_valid(self, sm):
        lease = sm.create_draft(
            intent={}, created_by="t",
            expires_at_ms=int(time.time() * 1000) + 3600_000,
        )
        sm.register(lease.lease_id)
        sm.activate(lease.lease_id)
        expired = sm.check_expiry()
        assert lease.lease_id not in expired

    def test_terminal_not_expired_again(self, sm):
        lease = sm.create_draft(
            intent={}, created_by="t",
            expires_at_ms=int(time.time() * 1000) - 1000,
        )
        sm.register(lease.lease_id)
        sm.activate(lease.lease_id)
        sm.revoke(lease.lease_id, approved_by="op1")
        expired = sm.check_expiry()
        assert lease.lease_id not in expired


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Audit Trail
# ═══════════════════════════════════════════════════════════════════════════════

class TestAudit:
    def test_callback_invoked(self, sm_with_audit):
        machine, records = sm_with_audit
        lease = machine.create_draft(intent={}, created_by="t")
        machine.register(lease.lease_id)
        assert len(records) == 2

    def test_record_fields(self, sm_with_audit):
        machine, records = sm_with_audit
        machine.create_draft(intent={}, created_by="t")
        r = records[0]
        for f in ["transition_id", "lease_id", "previous_status", "next_status",
                   "trigger_event_type", "initiated_by", "audit_event_ref"]:
            assert f in r


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Query Methods
# ═══════════════════════════════════════════════════════════════════════════════

class TestQuery:
    def test_get_returns_copy(self, sm, draft_lease):
        lease = sm.get(draft_lease.lease_id)
        lease.intent["MUTATED"] = True
        assert "MUTATED" not in sm.get(draft_lease.lease_id).intent

    def test_get_live(self, sm):
        a = _make_active(sm)
        sm.create_draft(intent={}, created_by="t")  # draft - not live
        live = sm.get_live()
        assert len(live) == 1
        assert live[0].lease_id == a.lease_id

    def test_get_bridgeable(self, sm):
        a = _make_active(sm)
        live = sm.get_bridgeable()
        assert len(live) == 1

    def test_status_summary(self, sm):
        _make_active(sm)
        sm.create_draft(intent={}, created_by="t")
        s = sm.get_status_summary()
        assert s.get("ACTIVE", 0) == 1
        assert s.get("DRAFT", 0) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Persistence
# ═══════════════════════════════════════════════════════════════════════════════

class TestPersistence:
    def test_roundtrip(self, sm, active_lease):
        sm.bridge(active_lease.lease_id)
        data = sm.export_state()
        sm2 = DecisionLeaseStateMachine()
        count = sm2.import_state(data)
        assert count == 1
        imported = sm2.get(active_lease.lease_id)
        assert imported.state == LeaseState.BRIDGED


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Thread Safety
# ═══════════════════════════════════════════════════════════════════════════════

class TestThreadSafety:
    def test_concurrent_lifecycle(self, sm):
        errors = []
        success = [0]

        def worker():
            try:
                l = sm.create_draft(intent={"t": True}, created_by="thread")
                sm.register(l.lease_id)
                sm.activate(l.lease_id)
                sm.bridge(l.lease_id)
                sm.consume(l.lease_id)
                success[0] += 1
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0
        assert success[0] == 10


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Full Lifecycle
# ═══════════════════════════════════════════════════════════════════════════════

class TestFullLifecycle:
    def test_happy_path_consume(self, sm):
        """DRAFT → REGISTERED → ACTIVE → BRIDGED → CONSUMED"""
        l = sm.create_draft(intent={"symbol": "BTC"}, created_by="H5")
        sm.register(l.lease_id)
        sm.activate(l.lease_id)
        sm.bridge(l.lease_id)
        result = sm.consume(l.lease_id)
        assert result.state == LeaseState.CONSUMED
        assert result.is_terminal
        assert result.version == 5

    def test_freeze_and_recovery(self, sm):
        """DRAFT → REG → ACTIVE → FROZEN → ACTIVE → BRIDGED → CONSUMED"""
        l = sm.create_draft(intent={}, created_by="t")
        sm.register(l.lease_id)
        sm.activate(l.lease_id)
        sm.freeze(l.lease_id, reason="incident")
        sm.unfreeze_to_active(l.lease_id, approved_by="op1")
        sm.bridge(l.lease_id)
        result = sm.consume(l.lease_id)
        assert result.state == LeaseState.CONSUMED
        assert result.version == 7

    def test_early_rejection(self, sm):
        l = sm.create_draft(intent={}, created_by="t")
        sm.reject(l.lease_id, reason="invalid")
        with pytest.raises(LeaseError, match="terminal"):
            sm.register(l.lease_id)


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Fail-Closed Behavior / 故障保护（闭合）测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestLeaseFailClosed:
    """Verify fail-closed behavior: leases deny by default.
    验证故障保护（闭合）行为：租约默认拒绝。"""

    def test_draft_lease_is_not_active(self, sm):
        """DRAFT lease should not be usable for decisions.
        DRAFT 租约不应可用于决策。"""
        lease = sm.create_draft(intent={"symbol": "BTC"}, created_by="test")
        assert lease.state == LeaseState.DRAFT
        assert lease.is_live is False
        assert lease.is_bridgeable is False

    def test_draft_lease_cannot_be_bridged(self, sm):
        """DRAFT lease cannot be bridged directly (not in live states).
        DRAFT 租约不能直接桥接。"""
        lease = sm.create_draft(intent={}, created_by="test")
        with pytest.raises(LeaseError, match="Forbidden|not in transition"):
            sm.bridge(lease.lease_id)

    def test_registered_lease_is_not_bridgeable(self, sm):
        """REGISTERED lease cannot be bridged (not in BRIDGEABLE_STATES).
        REGISTERED 租约不能桥接。"""
        lease = sm.create_draft(intent={}, created_by="test")
        sm.register(lease.lease_id)
        registered = sm.get(lease.lease_id)
        assert registered.state == LeaseState.REGISTERED
        assert registered.is_live is True
        assert registered.is_bridgeable is False

    def test_expired_lease_is_terminal(self, sm):
        """Expired lease is terminal and cannot be reactivated.
        过期的租约是终态，不能重新激活。"""
        lease = sm.create_draft(
            intent={}, created_by="test",
            expires_at_ms=int(time.time() * 1000) - 1000,  # Already expired
        )
        sm.register(lease.lease_id)
        sm.activate(lease.lease_id)

        # Auto-expire
        expired = sm.check_expiry()
        assert lease.lease_id in expired

        expired_lease = sm.get(lease.lease_id)
        assert expired_lease.state == LeaseState.EXPIRED
        assert expired_lease.is_terminal is True
        assert expired_lease.is_live is False

    def test_expired_lease_cannot_be_reactivated(self, sm):
        """Expired lease cannot return to active.
        过期租约不能返回活跃状态。"""
        lease = sm.create_draft(
            intent={}, created_by="test",
            expires_at_ms=int(time.time() * 1000) - 1000,
        )
        sm.register(lease.lease_id)
        sm.activate(lease.lease_id)
        sm.check_expiry()

        # Try to reactivate — should fail
        with pytest.raises(LeaseError, match="terminal"):
            sm.activate(lease.lease_id)

    def test_revoked_lease_is_terminal(self, sm):
        """Revoked lease is terminal and cannot transition.
        撤销的租约是终态，不能迁移。"""
        lease = _make_active(sm)
        sm.revoke(lease.lease_id, approved_by="op1")

        revoked = sm.get(lease.lease_id)
        assert revoked.state == LeaseState.REVOKED
        assert revoked.is_terminal is True
        assert revoked.is_live is False

        # Try to bridge — should fail
        with pytest.raises(LeaseError, match="terminal"):
            sm.bridge(lease.lease_id)

    def test_consumed_lease_is_terminal(self, sm):
        """Consumed lease is terminal and cannot be re-bridged or re-activated.
        已消费的租约是终态，不能重新桥接或激活。"""
        lease = _make_active(sm)
        sm.bridge(lease.lease_id)
        sm.consume(lease.lease_id)

        consumed = sm.get(lease.lease_id)
        assert consumed.state == LeaseState.CONSUMED
        assert consumed.is_terminal is True
        assert consumed.is_live is False

        # Try to activate — should fail
        with pytest.raises(LeaseError, match="terminal"):
            sm.activate(lease.lease_id)

    def test_rejected_lease_is_terminal(self, sm):
        """Rejected lease is terminal and cannot proceed.
        被拒绝的租约是终态，不能继续。"""
        lease = sm.create_draft(intent={}, created_by="test")
        sm.reject(lease.lease_id, reason="invalid")

        rejected = sm.get(lease.lease_id)
        assert rejected.state == LeaseState.REJECTED
        assert rejected.is_terminal is True
        assert rejected.is_live is False

        # Try to register — should fail
        with pytest.raises(LeaseError, match="terminal"):
            sm.register(lease.lease_id)

    def test_only_live_leases_are_in_live_states(self, sm):
        """Only REGISTERED, ACTIVE, BRIDGED are in LIVE_STATES.
        只有 REGISTERED, ACTIVE, BRIDGED 在 LIVE_STATES 中。"""
        lease = sm.create_draft(intent={}, created_by="test")
        assert lease.is_live is False

        sm.register(lease.lease_id)
        assert sm.get(lease.lease_id).is_live is True

        sm.activate(lease.lease_id)
        assert sm.get(lease.lease_id).is_live is True

        sm.bridge(lease.lease_id)
        assert sm.get(lease.lease_id).is_live is True

        sm.consume(lease.lease_id)
        assert sm.get(lease.lease_id).is_live is False  # Terminal
