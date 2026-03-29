"""
Tests for Authorization State Machine — SM-01 Governance Spec
授权状态机测试 — SM-01 治理规范

Covers:
  - All 16 valid transitions
  - All 7 forbidden transitions
  - Terminal state immutability
  - Guard conditions (initiator, approval)
  - Expiry guardian
  - Thread safety
  - Persistence (export/import)
  - Convenience methods
  - Audit trail generation
"""

import sys
import threading
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.authorization_state_machine import (
    AuthEvent,
    AuthInitiator,
    AuthorizationError,
    AuthorizationObject,
    AuthorizationStateMachine,
    AuthState,
    EFFECTIVE_STATES,
    FORBIDDEN_TRANSITIONS,
    TERMINAL_STATES,
    TRANSITION_RULES,
)

# Import shared fixtures and helpers from conftest
from conftest import (
    auth_state_machine as sm,
    auth_sm_with_audit as sm_with_audit,
    _create_draft_auth,
    _activate_auth,
    _make_active,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Test-Specific Fixtures / 测试特定夹具
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def draft_auth(sm):
    """Create a DRAFT authorization / 创建 DRAFT 授权"""
    return _create_draft_auth(sm, title="Test Auth")


@pytest.fixture
def active_auth(sm, draft_auth):
    """Create an ACTIVE authorization (draft → pending → active) / 创建 ACTIVE 授权"""
    return _activate_auth(sm, draft_auth)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Constants & Enum Tests / 常量与枚举测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestConstants:
    def test_eight_states(self):
        assert len(AuthState) == 8

    def test_terminal_states(self):
        assert TERMINAL_STATES == frozenset({AuthState.REVOKED, AuthState.EXPIRED, AuthState.REJECTED})

    def test_effective_states(self):
        assert EFFECTIVE_STATES == frozenset({AuthState.ACTIVE, AuthState.RESTRICTED})

    def test_sixteen_valid_transitions(self):
        assert len(TRANSITION_RULES) == 16

    def test_seven_forbidden_transitions(self):
        assert len(FORBIDDEN_TRANSITIONS) == 7

    def test_no_overlap_valid_forbidden(self):
        """Valid and forbidden transition sets must not overlap / 合法与禁止迁移不可重叠"""
        valid_keys = set(TRANSITION_RULES.keys())
        assert valid_keys.isdisjoint(FORBIDDEN_TRANSITIONS)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Draft Creation / 草案创建
# ═══════════════════════════════════════════════════════════════════════════════

class TestDraftCreation:
    def test_create_draft(self, sm):
        auth = sm.create_draft(
            title="New Auth", scope={"mode": "paper"}, created_by="op1",
        )
        assert auth.state == AuthState.DRAFT
        assert auth.authorization_id.startswith("auth:")
        assert auth.version == 1
        assert auth.created_by == "op1"
        assert len(auth.transitions) == 1
        assert auth.transitions[0]["previous_status"] == "NONE"

    def test_draft_not_effective(self, sm):
        auth = sm.create_draft(title="X", scope={}, created_by="op")
        assert not auth.is_effective
        assert not auth.is_terminal

    def test_multiple_drafts_independent(self, sm):
        a1 = sm.create_draft(title="A1", scope={}, created_by="op")
        a2 = sm.create_draft(title="A2", scope={}, created_by="op")
        assert a1.authorization_id != a2.authorization_id


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Valid Transition Tests (all 16) / 合法迁移测试（全部 16 条）
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidTransitions:
    """Test each of the 16 valid transitions defined in SM-01 §6-7"""

    # §7.1 Draft & Approval phase
    def test_draft_to_pending_approval(self, sm, draft_auth):
        """T1: DRAFT → PENDING_APPROVAL"""
        result = sm.submit_for_approval(draft_auth.authorization_id)
        assert result.state == AuthState.PENDING_APPROVAL
        assert result.version == 2

    def test_draft_to_rejected(self, sm, draft_auth):
        """T2: DRAFT → REJECTED"""
        result = sm.reject(draft_auth.authorization_id, reason="not needed")
        assert result.state == AuthState.REJECTED
        assert result.is_terminal

    def test_pending_to_active(self, sm, draft_auth):
        """T3: PENDING_APPROVAL → ACTIVE"""
        sm.submit_for_approval(draft_auth.authorization_id)
        result = sm.approve(draft_auth.authorization_id, approved_by="op1", reason="approved")
        assert result.state == AuthState.ACTIVE
        assert result.is_effective
        assert result.approved_by == "op1"

    def test_pending_to_rejected(self, sm, draft_auth):
        """T4: PENDING_APPROVAL → REJECTED"""
        sm.submit_for_approval(draft_auth.authorization_id)
        result = sm.reject(draft_auth.authorization_id, reason="denied")
        assert result.state == AuthState.REJECTED

    # §7.2 Post-activation
    def test_active_to_restricted(self, sm, active_auth):
        """T5: ACTIVE → RESTRICTED"""
        result = sm.restrict(active_auth.authorization_id, reason="risk event")
        assert result.state == AuthState.RESTRICTED
        assert result.is_effective

    def test_active_to_frozen(self, sm, active_auth):
        """T6: ACTIVE → FROZEN"""
        result = sm.freeze(active_auth.authorization_id, reason="incident")
        assert result.state == AuthState.FROZEN
        assert not result.is_effective

    def test_active_to_revoked(self, sm, active_auth):
        """T7: ACTIVE → REVOKED"""
        result = sm.revoke(active_auth.authorization_id, approved_by="op1", reason="permanent revoke")
        assert result.state == AuthState.REVOKED
        assert result.is_terminal

    def test_active_to_expired(self, sm, active_auth):
        """T8: ACTIVE → EXPIRED"""
        result = sm.transition(
            active_auth.authorization_id, AuthState.EXPIRED,
            event=AuthEvent.EXPIRED,
            initiator=AuthInitiator.EXPIRY_GUARDIAN,
            reason_codes=["time_expiry"],
        )
        assert result.state == AuthState.EXPIRED
        assert result.is_terminal

    # §7.3 Post-restriction recovery & termination
    def test_restricted_to_active(self, sm, active_auth):
        """T9: RESTRICTED → ACTIVE (full recovery)"""
        sm.restrict(active_auth.authorization_id, reason="risk")
        result = sm.recover_to_active(active_auth.authorization_id, approved_by="op1", reason="recovered")
        assert result.state == AuthState.ACTIVE

    def test_restricted_to_frozen(self, sm, active_auth):
        """T10: RESTRICTED → FROZEN"""
        sm.restrict(active_auth.authorization_id, reason="risk")
        result = sm.freeze(active_auth.authorization_id, reason="escalated")
        assert result.state == AuthState.FROZEN

    def test_restricted_to_revoked(self, sm, active_auth):
        """T11: RESTRICTED → REVOKED"""
        sm.restrict(active_auth.authorization_id, reason="risk")
        result = sm.revoke(active_auth.authorization_id, approved_by="op1")
        assert result.state == AuthState.REVOKED

    def test_restricted_to_expired(self, sm, active_auth):
        """T12: RESTRICTED → EXPIRED"""
        sm.restrict(active_auth.authorization_id, reason="risk")
        result = sm.transition(
            active_auth.authorization_id, AuthState.EXPIRED,
            event=AuthEvent.EXPIRED,
            initiator=AuthInitiator.EXPIRY_GUARDIAN,
            reason_codes=["time_expiry"],
        )
        assert result.state == AuthState.EXPIRED

    def test_frozen_to_restricted(self, sm, active_auth):
        """T13: FROZEN → RESTRICTED (conservative recovery)"""
        sm.freeze(active_auth.authorization_id, reason="incident")
        result = sm.recover_to_restricted(active_auth.authorization_id, approved_by="op1", reason="partial recovery")
        assert result.state == AuthState.RESTRICTED

    def test_frozen_to_active(self, sm, active_auth):
        """T14: FROZEN → ACTIVE (full recovery)"""
        sm.freeze(active_auth.authorization_id, reason="incident")
        result = sm.recover_to_active(active_auth.authorization_id, approved_by="op1", reason="full recovery")
        assert result.state == AuthState.ACTIVE

    def test_frozen_to_revoked(self, sm, active_auth):
        """T15: FROZEN → REVOKED"""
        sm.freeze(active_auth.authorization_id, reason="incident")
        result = sm.revoke(active_auth.authorization_id, approved_by="op1")
        assert result.state == AuthState.REVOKED

    def test_frozen_to_expired(self, sm, active_auth):
        """T16: FROZEN → EXPIRED"""
        sm.freeze(active_auth.authorization_id, reason="incident")
        result = sm.transition(
            active_auth.authorization_id, AuthState.EXPIRED,
            event=AuthEvent.EXPIRED,
            initiator=AuthInitiator.EXPIRY_GUARDIAN,
            reason_codes=["time_expiry"],
        )
        assert result.state == AuthState.EXPIRED


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Forbidden Transitions (SM-01 §8) / 禁止迁移测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestForbiddenTransitions:
    """All 7 explicitly forbidden transitions must raise AuthorizationError"""

    def _make_in_state(self, sm, target_state: AuthState) -> str:
        """Helper: create an auth and move it to target_state"""
        auth = sm.create_draft(title="Test", scope={}, created_by="op")
        aid = auth.authorization_id
        if target_state == AuthState.DRAFT:
            return aid
        sm.submit_for_approval(aid)
        if target_state == AuthState.PENDING_APPROVAL:
            return aid
        if target_state == AuthState.REJECTED:
            sm.reject(aid)
            return aid
        sm.approve(aid, approved_by="op1")
        if target_state == AuthState.ACTIVE:
            return aid
        if target_state == AuthState.RESTRICTED:
            sm.restrict(aid, reason="risk")
            return aid
        if target_state == AuthState.FROZEN:
            sm.freeze(aid, reason="incident")
            return aid
        if target_state == AuthState.REVOKED:
            sm.revoke(aid, approved_by="op1")
            return aid
        if target_state == AuthState.EXPIRED:
            sm.transition(aid, AuthState.EXPIRED,
                          event=AuthEvent.EXPIRED,
                          initiator=AuthInitiator.EXPIRY_GUARDIAN,
                          reason_codes=["time_expiry"])
            return aid
        raise ValueError(f"Unexpected target state: {target_state}")

    def test_revoked_to_active(self, sm):
        """F1: REVOKED → ACTIVE is forbidden"""
        aid = self._make_in_state(sm, AuthState.REVOKED)
        with pytest.raises(AuthorizationError, match="terminal"):
            sm.transition(aid, AuthState.ACTIVE, event=AuthEvent.RECOVERY_APPROVED,
                          initiator=AuthInitiator.OPERATOR, approved_by="op1")

    def test_revoked_to_restricted(self, sm):
        """F2: REVOKED → RESTRICTED is forbidden"""
        aid = self._make_in_state(sm, AuthState.REVOKED)
        with pytest.raises(AuthorizationError, match="terminal"):
            sm.transition(aid, AuthState.RESTRICTED, event=AuthEvent.RESTRICTED,
                          initiator=AuthInitiator.OPERATOR)

    def test_expired_to_active(self, sm):
        """F3: EXPIRED → ACTIVE is forbidden"""
        aid = self._make_in_state(sm, AuthState.EXPIRED)
        with pytest.raises(AuthorizationError, match="terminal"):
            sm.transition(aid, AuthState.ACTIVE, event=AuthEvent.RECOVERY_APPROVED,
                          initiator=AuthInitiator.OPERATOR, approved_by="op1")

    def test_expired_to_restricted(self, sm):
        """F4: EXPIRED → RESTRICTED is forbidden"""
        aid = self._make_in_state(sm, AuthState.EXPIRED)
        with pytest.raises(AuthorizationError, match="terminal"):
            sm.transition(aid, AuthState.RESTRICTED, event=AuthEvent.RESTRICTED,
                          initiator=AuthInitiator.OPERATOR)

    def test_rejected_to_active(self, sm):
        """F5: REJECTED → ACTIVE is forbidden"""
        aid = self._make_in_state(sm, AuthState.REJECTED)
        with pytest.raises(AuthorizationError, match="terminal"):
            sm.transition(aid, AuthState.ACTIVE, event=AuthEvent.APPROVED,
                          initiator=AuthInitiator.OPERATOR, approved_by="op1")

    def test_rejected_to_pending_approval(self, sm):
        """F6: REJECTED → PENDING_APPROVAL is forbidden"""
        aid = self._make_in_state(sm, AuthState.REJECTED)
        with pytest.raises(AuthorizationError, match="terminal"):
            sm.transition(aid, AuthState.PENDING_APPROVAL,
                          event=AuthEvent.SUBMITTED_FOR_APPROVAL,
                          initiator=AuthInitiator.OPERATOR)

    def test_draft_to_active_skip(self, sm):
        """F7: DRAFT → ACTIVE is forbidden (skip approval)"""
        auth = sm.create_draft(title="Skip", scope={}, created_by="op")
        with pytest.raises(AuthorizationError, match="not in transition table|Forbidden"):
            sm.transition(auth.authorization_id, AuthState.ACTIVE,
                          event=AuthEvent.APPROVED,
                          initiator=AuthInitiator.OPERATOR,
                          approved_by="op1")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Guard Condition Tests / 守卫条件测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestGuardConditions:
    def test_approval_required_without_approver(self, sm, draft_auth):
        """Approval transitions fail without approved_by / 需审批迁移没有审批者应失败"""
        sm.submit_for_approval(draft_auth.authorization_id)
        with pytest.raises(AuthorizationError, match="requires.*approval"):
            sm.transition(
                draft_auth.authorization_id, AuthState.ACTIVE,
                event=AuthEvent.APPROVED,
                initiator=AuthInitiator.OPERATOR,
                # No approved_by!
            )

    def test_wrong_initiator(self, sm, active_auth):
        """Wrong initiator should be rejected / 错误发起者应被拒绝"""
        with pytest.raises(AuthorizationError, match="not allowed"):
            sm.transition(
                active_auth.authorization_id, AuthState.EXPIRED,
                event=AuthEvent.EXPIRED,
                initiator=AuthInitiator.INCIDENT_POLICY,  # Wrong — should be EXPIRY_GUARDIAN
                reason_codes=["time_expiry"],
            )

    def test_nonexistent_authorization(self, sm):
        """Transition on non-existent auth should fail / 对不存在的授权迁移应失败"""
        with pytest.raises(AuthorizationError, match="not found"):
            sm.transition(
                "auth:nonexistent", AuthState.ACTIVE,
                event=AuthEvent.APPROVED,
                initiator=AuthInitiator.OPERATOR,
                approved_by="op1",
            )

    def test_invalid_transition_not_in_table(self, sm, draft_auth):
        """Transition not in table should fail / 不在表中的迁移应失败"""
        with pytest.raises(AuthorizationError):
            sm.transition(
                draft_auth.authorization_id, AuthState.FROZEN,
                event=AuthEvent.FREEZE_APPLIED,
                initiator=AuthInitiator.INCIDENT_POLICY,
            )

    def test_revoke_requires_approval(self, sm, active_auth):
        """ACTIVE → REVOKED requires approved_by / 撤销需要审批"""
        with pytest.raises(AuthorizationError, match="requires.*approval"):
            sm.transition(
                active_auth.authorization_id, AuthState.REVOKED,
                event=AuthEvent.REVOKED,
                initiator=AuthInitiator.OPERATOR,
                # No approved_by!
            )

    def test_recovery_requires_approval(self, sm, active_auth):
        """FROZEN → ACTIVE recovery requires approval / 恢复需要审批"""
        sm.freeze(active_auth.authorization_id, reason="incident")
        with pytest.raises(AuthorizationError, match="requires.*approval"):
            sm.transition(
                active_auth.authorization_id, AuthState.ACTIVE,
                event=AuthEvent.RECOVERY_APPROVED,
                initiator=AuthInitiator.RECOVERY_APPROVAL_FLOW,
                # No approved_by!
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Expiry Guardian / 过期守护测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestExpiryGuardian:
    def test_auto_expire_past_expiry(self, sm):
        """Authorization past its expires_at should auto-expire / 超过过期时间应自动过期"""
        auth = sm.create_draft(
            title="Will Expire", scope={}, created_by="op",
            expires_at_ms=int(time.time() * 1000) - 1000,  # Already expired
        )
        sm.submit_for_approval(auth.authorization_id)
        sm.approve(auth.authorization_id, approved_by="op1")

        expired = sm.check_expiry()
        assert auth.authorization_id in expired
        assert sm.get(auth.authorization_id).state == AuthState.EXPIRED

    def test_no_expire_if_not_past_time(self, sm):
        """Authorization not past expiry should remain / 未到过期时间不应过期"""
        auth = sm.create_draft(
            title="Not Yet", scope={}, created_by="op",
            expires_at_ms=int(time.time() * 1000) + 3600_000,
        )
        sm.submit_for_approval(auth.authorization_id)
        sm.approve(auth.authorization_id, approved_by="op1")

        expired = sm.check_expiry()
        assert auth.authorization_id not in expired
        assert sm.get(auth.authorization_id).state == AuthState.ACTIVE

    def test_no_expire_if_no_expiry_set(self, sm):
        """Authorization without expires_at never auto-expires / 无过期时间的授权不自动过期"""
        auth = sm.create_draft(
            title="Permanent", scope={}, created_by="op",
            expires_at_ms=None,
        )
        sm.submit_for_approval(auth.authorization_id)
        sm.approve(auth.authorization_id, approved_by="op1")

        expired = sm.check_expiry()
        assert len(expired) == 0

    def test_terminal_states_not_expired_again(self, sm):
        """Already terminal auths should not be touched / 已终态的授权不应再被过期"""
        auth = sm.create_draft(
            title="Already Revoked", scope={}, created_by="op",
            expires_at_ms=int(time.time() * 1000) - 1000,
        )
        sm.submit_for_approval(auth.authorization_id)
        sm.approve(auth.authorization_id, approved_by="op1")
        sm.revoke(auth.authorization_id, approved_by="op1")

        expired = sm.check_expiry()
        assert auth.authorization_id not in expired

    def test_expire_multiple(self, sm):
        """Multiple expired auths should all be transitioned / 多个过期授权都应被迁移"""
        past_ms = int(time.time() * 1000) - 1000
        ids = []
        for i in range(3):
            auth = sm.create_draft(title=f"Exp{i}", scope={}, created_by="op", expires_at_ms=past_ms)
            sm.submit_for_approval(auth.authorization_id)
            sm.approve(auth.authorization_id, approved_by="op1")
            ids.append(auth.authorization_id)

        expired = sm.check_expiry()
        assert set(ids) == set(expired)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Audit Trail / 审计轨迹测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditTrail:
    def test_audit_callback_invoked(self, sm_with_audit):
        """Audit callback should be called on every transition / 每次迁移都应调用审计回调"""
        machine, records = sm_with_audit
        auth = machine.create_draft(title="Aud", scope={}, created_by="op")
        machine.submit_for_approval(auth.authorization_id)
        machine.approve(auth.authorization_id, approved_by="op1")
        # create_draft(1) + submit(1) + approve(1) = 3
        assert len(records) == 3

    def test_audit_record_fields(self, sm_with_audit):
        """Audit records should contain required fields / 审计记录应包含必要字段"""
        machine, records = sm_with_audit
        auth = machine.create_draft(title="Fields", scope={}, created_by="op")
        record = records[0]
        required_fields = [
            "transition_id", "authorization_id", "previous_status",
            "next_status", "trigger_event_type", "trigger_event_id",
            "initiated_by", "transition_reason_codes", "approval_required",
            "approved_by", "effective_at_ms", "audit_event_ref",
            "version_before", "version_after",
        ]
        for f in required_fields:
            assert f in record, f"Missing field: {f}"

    def test_audit_records_on_authorization(self, sm, draft_auth):
        """Transitions stored in authorization.transitions / 迁移记录存储在授权对象中"""
        sm.submit_for_approval(draft_auth.authorization_id)
        sm.approve(draft_auth.authorization_id, approved_by="op1")
        auth = sm.get(draft_auth.authorization_id)
        # creation + submit + approve = 3
        assert len(auth.transitions) == 3
        assert auth.transitions[-1]["next_status"] == "ACTIVE"

    def test_version_increments(self, sm, draft_auth):
        """Version should increment on every transition / 每次迁移版本号递增"""
        sm.submit_for_approval(draft_auth.authorization_id)
        auth = sm.get(draft_auth.authorization_id)
        assert auth.version == 2
        sm.approve(auth.authorization_id, approved_by="op1")
        auth = sm.get(auth.authorization_id)
        assert auth.version == 3


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Persistence (Export/Import) / 持久化测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestPersistence:
    def test_export_import_roundtrip(self, sm, active_auth):
        """Export → Import should preserve state / 导出→导入应保持状态"""
        sm.restrict(active_auth.authorization_id, reason="test restriction")
        data = sm.export_state()
        assert len(data) == 1

        sm2 = AuthorizationStateMachine()
        count = sm2.import_state(data)
        assert count == 1

        imported = sm2.get(active_auth.authorization_id)
        assert imported is not None
        assert imported.state == AuthState.RESTRICTED
        assert imported.authorization_id == active_auth.authorization_id
        assert imported.restriction_reason == "test restriction"

    def test_export_multiple(self, sm):
        """Export should handle multiple authorizations / 导出应处理多个授权"""
        for i in range(3):
            sm.create_draft(title=f"Auth{i}", scope={}, created_by="op")
        data = sm.export_state()
        assert len(data) == 3

    def test_import_preserves_transitions(self, sm, active_auth):
        """Import should preserve transition history / 导入应保留迁移历史"""
        data = sm.export_state()
        sm2 = AuthorizationStateMachine()
        sm2.import_state(data)
        imported = sm2.get(active_auth.authorization_id)
        assert len(imported.transitions) == 3  # create + submit + approve

    def test_import_bad_data_skips(self, sm):
        """Import should skip malformed entries / 导入应跳过错误数据"""
        bad_data = [{"state": "INVALID_STATE"}]
        count = sm.import_state(bad_data)
        assert count == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Query Methods / 查询方法测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestQueryMethods:
    def test_get_returns_copy(self, sm, draft_auth):
        """get() should return a copy, not the original / get() 应返回副本"""
        auth = sm.get(draft_auth.authorization_id)
        auth.title = "MUTATED"
        original = sm.get(draft_auth.authorization_id)
        assert original.title == "Test Auth"

    def test_get_nonexistent_returns_none(self, sm):
        assert sm.get("auth:doesnotexist") is None

    def test_get_effective(self, sm):
        """get_effective should return only ACTIVE and RESTRICTED / 仅返回有效授权"""
        a1 = _make_active(sm)
        a2 = _make_active(sm)
        sm.restrict(a2.authorization_id, reason="risk")
        # Draft one more — not effective
        sm.create_draft(title="Draft", scope={}, created_by="op")

        effective = sm.get_effective()
        effective_ids = {a.authorization_id for a in effective}
        assert a1.authorization_id in effective_ids
        assert a2.authorization_id in effective_ids
        assert len(effective) == 2

    def test_get_all(self, sm):
        sm.create_draft(title="A", scope={}, created_by="op")
        sm.create_draft(title="B", scope={}, created_by="op")
        assert len(sm.get_all()) == 2

    def test_status_summary(self, sm):
        a1 = _make_active(sm)
        _make_active(sm)
        sm.create_draft(title="D", scope={}, created_by="op")
        sm.freeze(a1.authorization_id, reason="test")

        summary = sm.get_status_summary()
        assert summary.get("ACTIVE", 0) == 1
        assert summary.get("FROZEN", 0) == 1
        assert summary.get("DRAFT", 0) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Thread Safety / 线程安全测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestThreadSafety:
    def test_concurrent_transitions(self, sm):
        """Concurrent transitions should not corrupt state / 并发迁移不应破坏状态"""
        errors = []
        success_count = [0]

        def worker():
            try:
                auth = sm.create_draft(title="Concurrent", scope={}, created_by="op")
                sm.submit_for_approval(auth.authorization_id)
                sm.approve(auth.authorization_id, approved_by="op1")
                sm.restrict(auth.authorization_id, reason="concurrent test")
                success_count[0] += 1
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"Errors: {errors}"
        assert success_count[0] == 10
        assert len(sm.get_all()) == 10

    def test_concurrent_expiry_check(self, sm):
        """Concurrent expiry checks should not double-expire / 并发过期检查不应双重过期"""
        past_ms = int(time.time() * 1000) - 1000
        auth = sm.create_draft(title="ConcExp", scope={}, created_by="op", expires_at_ms=past_ms)
        sm.submit_for_approval(auth.authorization_id)
        sm.approve(auth.authorization_id, approved_by="op1")

        results = []

        def check():
            results.extend(sm.check_expiry())

        threads = [threading.Thread(target=check) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # Should appear exactly once in results (others get "terminal state" guard)
        assert results.count(auth.authorization_id) == 1
        assert sm.get(auth.authorization_id).state == AuthState.EXPIRED


# ═══════════════════════════════════════════════════════════════════════════════
# 11. AuthorizationObject Properties / 授权对象属性测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthorizationObject:
    def test_to_dict(self):
        auth = AuthorizationObject(
            title="Dict Test", scope={"mode": "paper"}, created_by="op",
        )
        d = auth.to_dict()
        assert d["state"] == "DRAFT"
        assert d["is_effective"] is False
        assert d["is_terminal"] is False
        assert "authorization_id" in d

    def test_from_dict_roundtrip(self):
        auth = AuthorizationObject(
            title="RT", scope={"mode": "paper"}, created_by="op",
            approved_by="op1", restriction_reason="risk",
        )
        d = auth.to_dict()
        d["restriction_reason"] = auth.restriction_reason
        d["approval_reason"] = auth.approval_reason
        d["freeze_reason"] = auth.freeze_reason
        d["revoke_reason"] = auth.revoke_reason
        d["transitions"] = auth.transitions

        restored = AuthorizationObject.from_dict(d)
        assert restored.title == "RT"
        assert restored.restriction_reason == "risk"

    def test_is_expired_by_time(self):
        auth = AuthorizationObject(
            expires_at_ms=int(time.time() * 1000) - 1000,
        )
        assert auth.is_expired_by_time

    def test_not_expired_by_time(self):
        auth = AuthorizationObject(
            expires_at_ms=int(time.time() * 1000) + 3600_000,
        )
        assert not auth.is_expired_by_time

    def test_no_expiry_never_expired(self):
        auth = AuthorizationObject(expires_at_ms=None)
        assert not auth.is_expired_by_time


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Full Lifecycle Integration / 完整生命周期集成测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestFullLifecycle:
    def test_happy_path_to_revoke(self, sm):
        """DRAFT → PENDING → ACTIVE → RESTRICTED → FROZEN → REVOKED"""
        auth = sm.create_draft(title="Lifecycle", scope={"mode": "paper"}, created_by="op")
        aid = auth.authorization_id

        sm.submit_for_approval(aid)
        sm.approve(aid, approved_by="op1", reason="approved")
        sm.restrict(aid, reason="risk event")
        sm.freeze(aid, reason="escalated")
        result = sm.revoke(aid, approved_by="op1", reason="permanent")

        assert result.state == AuthState.REVOKED
        assert result.version == 6  # 1 (create) + 5 transitions
        assert len(result.transitions) == 6

    def test_happy_path_freeze_recover(self, sm):
        """DRAFT → PENDING → ACTIVE → FROZEN → RESTRICTED → ACTIVE"""
        auth = sm.create_draft(title="Recovery", scope={}, created_by="op")
        aid = auth.authorization_id

        sm.submit_for_approval(aid)
        sm.approve(aid, approved_by="op1")
        sm.freeze(aid, reason="incident")
        sm.recover_to_restricted(aid, approved_by="op1", reason="partial")
        result = sm.recover_to_active(aid, approved_by="op1", reason="full")

        assert result.state == AuthState.ACTIVE
        assert result.is_effective

    def test_reject_early(self, sm):
        """DRAFT → REJECTED (no further transitions possible)"""
        auth = sm.create_draft(title="Quick Reject", scope={}, created_by="op")
        sm.reject(auth.authorization_id, reason="bad idea")

        with pytest.raises(AuthorizationError, match="terminal"):
            sm.transition(
                auth.authorization_id, AuthState.PENDING_APPROVAL,
                event=AuthEvent.SUBMITTED_FOR_APPROVAL,
                initiator=AuthInitiator.OPERATOR,
            )
