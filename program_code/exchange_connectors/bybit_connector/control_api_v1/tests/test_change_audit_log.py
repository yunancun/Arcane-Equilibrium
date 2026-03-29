"""
Tests for Change Audit Log — DOC-06 / T2.14
變更審計日誌測試

Covers:
  - ChangeType and ChangeApprovalStatus enums
  - ChangeRecord creation and immutability
  - Change recording (normal, auto-approved, emergency)
  - Change approval/rejection workflow
  - Query filters (time range, type, initiator, status)
  - Pending approvals and emergency review
  - Thread safety
  - JSON serialization/deserialization
  - Audit callbacks
"""

import json
import sys
import threading
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.change_audit_log import (
    ChangeAuditLog,
    ChangeRecord,
    ChangeType,
    ChangeApprovalStatus,
)

# Import shared fixtures from conftest
from conftest import (
    change_audit_log,
    change_audit_log_with_callback as audit_log_with_callback,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Test-Specific Fixtures / 测试特定夹具
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def audit_log(change_audit_log):
    """Alias for change_audit_log for backward compatibility"""
    return change_audit_log


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Enum Tests / 枚举测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestChangeTypeEnum:
    def test_all_change_types_defined(self):
        """Verify all required change types exist."""
        required = {
            "CONFIG_CHANGE",
            "PARAMETER_CHANGE",
            "STATE_CHANGE",
            "PERMISSION_CHANGE",
            "CODE_DEPLOYMENT",
            "ROLLBACK",
            "EMERGENCY_CHANGE",
        }
        actual = {e.name for e in ChangeType}
        assert required == actual

    def test_change_type_string_values(self):
        """Verify change types have correct string values."""
        assert ChangeType.CONFIG_CHANGE.value == "CONFIG_CHANGE"
        assert ChangeType.PARAMETER_CHANGE.value == "PARAMETER_CHANGE"
        assert ChangeType.EMERGENCY_CHANGE.value == "EMERGENCY_CHANGE"


class TestChangeApprovalStatusEnum:
    def test_all_approval_statuses_defined(self):
        """Verify all required approval statuses exist."""
        required = {
            "PENDING",
            "APPROVED",
            "REJECTED",
            "AUTO_APPROVED",
            "EMERGENCY_BYPASSED",
        }
        actual = {e.name for e in ChangeApprovalStatus}
        assert required == actual

    def test_approval_status_string_values(self):
        """Verify approval statuses have correct string values."""
        assert ChangeApprovalStatus.PENDING.value == "PENDING"
        assert ChangeApprovalStatus.APPROVED.value == "APPROVED"
        assert ChangeApprovalStatus.EMERGENCY_BYPASSED.value == "EMERGENCY_BYPASSED"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. ChangeRecord Tests / 变更记录测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestChangeRecord:
    def test_record_immutability(self):
        """Verify ChangeRecord is frozen (immutable)."""
        now = time.time()
        record = ChangeRecord(
            change_id="chg:00000001",
            change_type=ChangeType.CONFIG_CHANGE,
            who="test_agent",
            when=now,
            when_ms=int(now * 1000),
            what="Test change",
            reason="Testing",
        )

        # Attempting to modify should raise FrozenInstanceError
        with pytest.raises(Exception):  # FrozenInstanceError
            record.change_type = ChangeType.PARAMETER_CHANGE

    def test_record_to_dict(self):
        """Verify record serialization to dict."""
        now = time.time()
        record = ChangeRecord(
            change_id="chg:00000001",
            change_type=ChangeType.CONFIG_CHANGE,
            who="operator_john",
            when=now,
            when_ms=int(now * 1000),
            what="Changed max_loss",
            reason="Risk adjustment",
            old_value="100",
            new_value="200",
            affected_components=["risk_governor"],
            approval_status=ChangeApprovalStatus.APPROVED,
            approved_by="supervisor",
        )

        d = record.to_dict()
        assert d["change_id"] == "chg:00000001"
        assert d["change_type"] == "CONFIG_CHANGE"
        assert d["who"] == "operator_john"
        assert d["what"] == "Changed max_loss"
        assert d["approval_status"] == "APPROVED"
        assert d["approved_by"] == "supervisor"

    def test_record_from_dict(self):
        """Verify record deserialization from dict."""
        now = time.time()
        data = {
            "change_id": "chg:00000001",
            "change_type": "CONFIG_CHANGE",
            "who": "test_agent",
            "when": now,
            "when_ms": int(now * 1000),
            "what": "Test change",
            "reason": "Testing",
            "old_value": '100',
            "new_value": '200',
            "affected_components": ["component1"],
            "approval_status": "APPROVED",
            "approved_by": "supervisor",
            "approval_timestamp": now,
            "approval_reason": "OK",
            "rollback_info": None,
            "recorded_at_ms": int(now * 1000),
        }

        record = ChangeRecord.from_dict(data)
        assert record.change_id == "chg:00000001"
        assert record.change_type == ChangeType.CONFIG_CHANGE
        assert record.approval_status == ChangeApprovalStatus.APPROVED


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Basic Record Change Tests / 基本记录变更测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestRecordChange:
    def test_record_simple_change(self, audit_log):
        """Test recording a simple change."""
        record = audit_log.record_change(
            change_type=ChangeType.PARAMETER_CHANGE,
            who="agent_01",
            what="Adjusted strategy parameter",
            reason="Optimization",
        )

        assert record.change_id == "chg:00000001"
        assert record.change_type == ChangeType.PARAMETER_CHANGE
        assert record.who == "agent_01"
        assert record.what == "Adjusted strategy parameter"
        assert record.approval_status == ChangeApprovalStatus.PENDING
        assert audit_log.record_count() == 1

    def test_record_change_with_values(self, audit_log):
        """Test recording a change with old/new values."""
        record = audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="operator",
            what="Updated max_daily_loss",
            reason="Risk reduction",
            old_value={"limit": 1000},
            new_value={"limit": 500},
        )

        assert record.old_value is not None
        assert record.new_value is not None
        assert json.loads(record.old_value)["limit"] == 1000
        assert json.loads(record.new_value)["limit"] == 500

    def test_record_change_with_components(self, audit_log):
        """Test recording a change with affected components."""
        components = ["risk_governor", "guardian", "auth_sm"]
        record = audit_log.record_change(
            change_type=ChangeType.STATE_CHANGE,
            who="system",
            what="Changed system_mode",
            reason="Emergency",
            affected_components=components,
        )

        assert record.affected_components == components

    def test_record_auto_approved_change(self, audit_log):
        """Test recording an auto-approved (GREEN) change."""
        record = audit_log.record_change(
            change_type=ChangeType.PARAMETER_CHANGE,
            who="agent_01",
            what="Auto-adjusted adaptive parameter",
            reason="Market conditions",
            auto_approve=True,
        )

        assert record.approval_status == ChangeApprovalStatus.AUTO_APPROVED
        assert record.approved_by == "system"
        assert record.approval_timestamp is not None

    def test_sequential_change_ids(self, audit_log):
        """Verify change IDs are sequential."""
        r1 = audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="test",
            what="Change 1",
            reason="Test",
        )
        r2 = audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="test",
            what="Change 2",
            reason="Test",
        )
        r3 = audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="test",
            what="Change 3",
            reason="Test",
        )

        assert r1.change_id == "chg:00000001"
        assert r2.change_id == "chg:00000002"
        assert r3.change_id == "chg:00000003"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Emergency Change Tests / 紧急变更测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmergencyChange:
    def test_record_emergency_change(self, audit_log):
        """Test recording an emergency change that bypasses approval."""
        record = audit_log.record_emergency_change(
            change_type=ChangeType.EMERGENCY_CHANGE,
            who="emergency_system",
            what="Disabled circuit breaker during market crash",
            reason="Market volatility spike detected",
            old_value={"breaker_enabled": True},
            new_value={"breaker_enabled": False},
            affected_components=["circuit_breaker"],
        )

        assert record.approval_status == ChangeApprovalStatus.EMERGENCY_BYPASSED
        assert record.approved_by is None
        assert "post-review required" in record.approval_reason or "post-review" in record.approval_reason.lower()
        assert record.rollback_info is not None
        assert record.rollback_info["requires_post_review"] is True

    def test_emergency_change_requires_post_review(self, audit_log):
        """Verify emergency changes appear in post-review queue."""
        # Record an emergency change
        audit_log.record_emergency_change(
            change_type=ChangeType.EMERGENCY_CHANGE,
            who="emergency_system",
            what="Emergency freeze",
            reason="System failure",
        )

        # Emergency changes should appear in pending approvals
        pending = audit_log.get_pending_approvals()
        assert len(pending) == 1
        assert pending[0].approval_status == ChangeApprovalStatus.EMERGENCY_BYPASSED


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Approval Workflow Tests / 批准工作流测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestApprovalWorkflow:
    def test_approve_pending_change(self, audit_log):
        """Test approving a pending change."""
        # Record a change (not auto-approved)
        change = audit_log.record_change(
            change_type=ChangeType.PARAMETER_CHANGE,
            who="agent_01",
            what="Proposed parameter change",
            reason="Testing",
        )

        assert change.approval_status == ChangeApprovalStatus.PENDING

        # Approve it
        approved = audit_log.approve_change(
            change_id="chg:00000001",
            approved_by="operator_john",
            approval_reason="Looks good",
        )

        assert approved is not None
        assert approved.approval_status == ChangeApprovalStatus.APPROVED
        assert approved.approved_by == "operator_john"
        assert approved.approval_reason == "Looks good"
        assert approved.approval_timestamp is not None

    def test_reject_pending_change(self, audit_log):
        """Test rejecting a pending change."""
        # Record a change
        change = audit_log.record_change(
            change_type=ChangeType.PARAMETER_CHANGE,
            who="agent_01",
            what="Proposed parameter change",
            reason="Testing",
        )

        # Reject it
        rejected = audit_log.reject_change(
            change_id="chg:00000001",
            rejected_by="operator_john",
            rejection_reason="Risk too high",
        )

        assert rejected is not None
        assert rejected.approval_status == ChangeApprovalStatus.REJECTED
        assert rejected.approved_by == "operator_john"
        assert rejected.approval_reason == "Risk too high"

    def test_cannot_approve_already_approved_change(self, audit_log):
        """Verify cannot re-approve an already approved change."""
        audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="test",
            what="Change",
            reason="Test",
        )

        # Approve once
        audit_log.approve_change("chg:00000001", "op1", "First approval")

        # Try to approve again
        result = audit_log.approve_change("chg:00000001", "op2", "Second approval")

        # Should return the original approved record
        assert result.approved_by == "op1"

    def test_cannot_reject_already_approved_change(self, audit_log):
        """Verify cannot reject an already approved change."""
        audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="test",
            what="Change",
            reason="Test",
        )

        audit_log.approve_change("chg:00000001", "op1", "Approved")
        result = audit_log.reject_change("chg:00000001", "op2", "Rejecting")

        assert result.approval_status == ChangeApprovalStatus.APPROVED

    def test_approve_nonexistent_change(self, audit_log):
        """Verify approving nonexistent change returns None."""
        result = audit_log.approve_change("chg:99999999", "op1")
        assert result is None

    def test_reject_nonexistent_change(self, audit_log):
        """Verify rejecting nonexistent change returns None."""
        result = audit_log.reject_change("chg:99999999", "op1", "reason")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Query and Filter Tests / 查询和筛选测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestQueryAndFilter:
    def test_get_change_by_id(self, audit_log):
        """Test retrieving a specific change by ID."""
        record = audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="test",
            what="Change",
            reason="Test",
        )

        retrieved = audit_log.get_change_by_id("chg:00000001")
        assert retrieved is not None
        assert retrieved.change_id == record.change_id

    def test_get_nonexistent_change_by_id(self, audit_log):
        """Test retrieving nonexistent change by ID."""
        result = audit_log.get_change_by_id("chg:99999999")
        assert result is None

    def test_filter_by_change_type(self, audit_log):
        """Test filtering changes by type."""
        audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="test",
            what="Config change",
            reason="Test",
        )
        audit_log.record_change(
            change_type=ChangeType.PARAMETER_CHANGE,
            who="test",
            what="Param change",
            reason="Test",
        )
        audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="test",
            what="Another config change",
            reason="Test",
        )

        configs = audit_log.get_change_history(change_type=ChangeType.CONFIG_CHANGE)
        assert len(configs) == 2
        assert all(c.change_type == ChangeType.CONFIG_CHANGE for c in configs)

    def test_filter_by_initiator(self, audit_log):
        """Test filtering changes by initiator."""
        audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="agent_01",
            what="Change",
            reason="Test",
        )
        audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="agent_02",
            what="Change",
            reason="Test",
        )
        audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="agent_01",
            what="Change",
            reason="Test",
        )

        agent_01_changes = audit_log.get_change_history(initiator="agent_01")
        assert len(agent_01_changes) == 2
        assert all(c.who == "agent_01" for c in agent_01_changes)

    def test_filter_by_approval_status(self, audit_log):
        """Test filtering changes by approval status."""
        audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="test",
            what="Change 1",
            reason="Test",
            auto_approve=False,
        )
        audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="test",
            what="Change 2",
            reason="Test",
            auto_approve=True,
        )

        pending = audit_log.get_change_history(approval_status=ChangeApprovalStatus.PENDING)
        assert len(pending) == 1

        auto_approved = audit_log.get_change_history(
            approval_status=ChangeApprovalStatus.AUTO_APPROVED
        )
        assert len(auto_approved) == 1

    def test_filter_by_time_range(self, audit_log):
        """Test filtering changes by time range."""
        start = time.time()

        audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="test",
            what="Early change",
            reason="Test",
        )

        time.sleep(0.1)
        mid_time = time.time()
        time.sleep(0.1)

        audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="test",
            what="Late change",
            reason="Test",
        )

        # Should include both
        both = audit_log.get_change_history(start_time=start)
        assert len(both) == 2

        # Should include only the late change
        late_only = audit_log.get_change_history(start_time=mid_time)
        assert len(late_only) == 1
        assert "Late" in late_only[0].what

    def test_combined_filters(self, audit_log):
        """Test combining multiple filters."""
        audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="agent_01",
            what="Change 1",
            reason="Test",
            auto_approve=False,
        )
        audit_log.record_change(
            change_type=ChangeType.PARAMETER_CHANGE,
            who="agent_01",
            what="Change 2",
            reason="Test",
            auto_approve=False,
        )
        audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="agent_02",
            what="Change 3",
            reason="Test",
            auto_approve=False,
        )

        results = audit_log.get_change_history(
            change_type=ChangeType.CONFIG_CHANGE,
            initiator="agent_01",
            approval_status=ChangeApprovalStatus.PENDING,
        )

        assert len(results) == 1
        assert results[0].what == "Change 1"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Pending Approvals Tests / 待批准变更测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestPendingApprovals:
    def test_get_pending_approvals(self, audit_log):
        """Test retrieving pending changes."""
        # Auto-approved change (should not appear in pending)
        audit_log.record_change(
            change_type=ChangeType.PARAMETER_CHANGE,
            who="agent_01",
            what="Auto change",
            reason="Test",
            auto_approve=True,
        )

        # Pending changes (should appear)
        audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="agent_01",
            what="Pending change 1",
            reason="Test",
        )
        audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="agent_01",
            what="Pending change 2",
            reason="Test",
        )

        # Approved change (should not appear)
        audit_log.approve_change("chg:00000002", "op1")

        pending = audit_log.get_pending_approvals()
        assert len(pending) == 1
        assert pending[0].what == "Pending change 2"

    def test_pending_with_emergency_bypassed(self, audit_log):
        """Test that emergency bypassed changes appear in pending."""
        # Regular pending change
        audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="agent",
            what="Pending",
            reason="Test",
        )

        # Emergency bypassed change
        audit_log.record_emergency_change(
            change_type=ChangeType.EMERGENCY_CHANGE,
            who="system",
            what="Emergency",
            reason="Crash",
        )

        pending = audit_log.get_pending_approvals()
        assert len(pending) == 2
        statuses = {c.approval_status for c in pending}
        assert ChangeApprovalStatus.PENDING in statuses
        assert ChangeApprovalStatus.EMERGENCY_BYPASSED in statuses


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Emergency Review Tests / 紧急审查测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmergencyReview:
    def test_get_emergency_changes_pending_review(self, audit_log):
        """Test getting emergency changes older than 24 hours."""
        # Record an old emergency change by manipulating time
        audit_log.record_emergency_change(
            change_type=ChangeType.EMERGENCY_CHANGE,
            who="system",
            what="Old emergency",
            reason="Crash",
        )

        # Manually override the timestamp to be 25 hours old
        old_record = audit_log._changes[0]
        old_time = time.time() - (25 * 3600)  # 25 hours ago
        old_record_dict = old_record.to_dict()
        old_record_dict['when'] = old_time
        old_record_dict['when_ms'] = int(old_time * 1000)
        audit_log._changes[0] = ChangeRecord.from_dict(old_record_dict)

        # Recent emergency change
        audit_log.record_emergency_change(
            change_type=ChangeType.EMERGENCY_CHANGE,
            who="system",
            what="Recent emergency",
            reason="Crash",
        )

        # Only the old one should appear
        pending_review = audit_log.get_emergency_changes_pending_review()
        assert len(pending_review) == 1
        assert "Old" in pending_review[0].what


# ═══════════════════════════════════════════════════════════════════════════════
# 9. JSON Serialization Tests / JSON 序列化测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestJSONSerialization:
    def test_export_to_json(self, audit_log):
        """Test exporting change history to JSON."""
        audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="test",
            what="Change 1",
            reason="Test",
            old_value={"param": 100},
            new_value={"param": 200},
        )
        audit_log.record_change(
            change_type=ChangeType.PARAMETER_CHANGE,
            who="test",
            what="Change 2",
            reason="Test",
        )

        json_str = audit_log.export_to_json()
        data = json.loads(json_str)

        assert len(data) == 2
        assert data[0]["change_type"] == "CONFIG_CHANGE"
        assert data[1]["change_type"] == "PARAMETER_CHANGE"

    def test_export_to_json_pretty(self, audit_log):
        """Test pretty-printing JSON export."""
        audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="test",
            what="Change",
            reason="Test",
        )

        json_str = audit_log.export_to_json(pretty=True)
        # Pretty format should have indentation
        assert "  " in json_str or "\n" in json_str


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Audit Callback Tests / 审计回调测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditCallback:
    def test_callback_on_record_change(self, audit_log_with_callback):
        """Test that callback is invoked when recording changes."""
        log, callbacks = audit_log_with_callback

        log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="test",
            what="Change 1",
            reason="Test",
        )

        assert len(callbacks) == 1
        assert callbacks[0].what == "Change 1"

    def test_callback_on_approve_change(self, audit_log_with_callback):
        """Test that callback is invoked when approving changes."""
        log, callbacks = audit_log_with_callback

        log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="test",
            what="Change",
            reason="Test",
        )

        # Clear callbacks from recording
        callbacks.clear()

        log.approve_change("chg:00000001", "op1", "OK")

        assert len(callbacks) == 1
        assert callbacks[0].approval_status == ChangeApprovalStatus.APPROVED

    def test_callback_on_reject_change(self, audit_log_with_callback):
        """Test that callback is invoked when rejecting changes."""
        log, callbacks = audit_log_with_callback

        log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="test",
            what="Change",
            reason="Test",
        )

        callbacks.clear()

        log.reject_change("chg:00000001", "op1", "Risk too high")

        assert len(callbacks) == 1
        assert callbacks[0].approval_status == ChangeApprovalStatus.REJECTED

    def test_callback_on_emergency_change(self, audit_log_with_callback):
        """Test that callback is invoked for emergency changes."""
        log, callbacks = audit_log_with_callback

        log.record_emergency_change(
            change_type=ChangeType.EMERGENCY_CHANGE,
            who="system",
            what="Emergency",
            reason="Crash",
        )

        assert len(callbacks) == 1
        assert callbacks[0].approval_status == ChangeApprovalStatus.EMERGENCY_BYPASSED


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Thread Safety Tests / 线程安全测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestThreadSafety:
    def test_concurrent_record_changes(self, audit_log):
        """Test thread-safe concurrent recording of changes."""
        def record_many(start_id: int, count: int):
            for i in range(count):
                audit_log.record_change(
                    change_type=ChangeType.CONFIG_CHANGE,
                    who=f"agent_{start_id}",
                    what=f"Change {i}",
                    reason="Concurrent test",
                )

        threads = []
        for i in range(5):
            t = threading.Thread(target=record_many, args=(i, 10))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Should have exactly 50 changes
        assert audit_log.record_count() == 50

    def test_concurrent_approval_and_query(self, audit_log):
        """Test concurrent approval and query operations."""
        # Record some changes
        for i in range(20):
            audit_log.record_change(
                change_type=ChangeType.CONFIG_CHANGE,
                who="test",
                what=f"Change {i}",
                reason="Test",
            )

        results = []

        def approve_some(start: int, count: int):
            for i in range(start, start + count):
                audit_log.approve_change(f"chg:{i:08d}", "op1")

        def query_some():
            for _ in range(5):
                items = audit_log.get_change_history()
                results.append(len(items))

        t1 = threading.Thread(target=approve_some, args=(1, 10))
        t2 = threading.Thread(target=query_some)

        t1.start()
        t2.start()

        t1.join()
        t2.join()

        # All queries should see consistent result count
        assert all(r == 20 for r in results)

    def test_concurrent_mixed_operations(self, audit_log):
        """Test concurrent mix of all operations."""
        def mixed_ops():
            for i in range(10):
                audit_log.record_change(
                    change_type=ChangeType.CONFIG_CHANGE,
                    who="agent",
                    what=f"Change {i}",
                    reason="Concurrent",
                )
                audit_log.get_all_changes()
                if i % 2 == 0:
                    audit_log.get_pending_approvals()

        threads = [threading.Thread(target=mixed_ops) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should complete without deadlock
        assert audit_log.record_count() == 30


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Utility Methods Tests / 实用方法测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestUtilityMethods:
    def test_get_all_changes(self, audit_log):
        """Test retrieving all changes."""
        for i in range(5):
            audit_log.record_change(
                change_type=ChangeType.CONFIG_CHANGE,
                who="test",
                what=f"Change {i}",
                reason="Test",
            )

        all_changes = audit_log.get_all_changes()
        assert len(all_changes) == 5

    def test_record_count(self, audit_log):
        """Test getting the record count."""
        assert audit_log.record_count() == 0

        audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="test",
            what="Change",
            reason="Test",
        )
        assert audit_log.record_count() == 1

        audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="test",
            what="Change 2",
            reason="Test",
        )
        assert audit_log.record_count() == 2

    def test_clear(self, audit_log):
        """Test clearing the log (for testing only)."""
        audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="test",
            what="Change",
            reason="Test",
        )
        assert audit_log.record_count() == 1

        audit_log.clear()
        assert audit_log.record_count() == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 13. Integration Tests / 集成测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntegration:
    def test_complete_workflow(self, audit_log):
        """Test a complete change workflow."""
        # Record a YELLOW change (needs approval)
        change = audit_log.record_change(
            change_type=ChangeType.PARAMETER_CHANGE,
            who="agent_01",
            what="Proposed AI budget increase",
            reason="Positive performance metrics",
            old_value={"budget": 100},
            new_value={"budget": 150},
            affected_components=["ai_budget_allocator"],
        )

        assert change.approval_status == ChangeApprovalStatus.PENDING

        # Get pending approvals
        pending = audit_log.get_pending_approvals()
        assert len(pending) == 1

        # Operator reviews and approves
        approved = audit_log.approve_change(
            change_id="chg:00000001",
            approved_by="operator_nancun",
            approval_reason="Performance justified. Approved per DOC-06 §3.5",
        )

        assert approved.approval_status == ChangeApprovalStatus.APPROVED
        assert approved.approved_by == "operator_nancun"

        # No more pending
        pending = audit_log.get_pending_approvals()
        assert len(pending) == 0

        # Can retrieve the approved change
        retrieved = audit_log.get_change_by_id("chg:00000001")
        assert retrieved.approval_status == ChangeApprovalStatus.APPROVED

    def test_mixed_change_types_workflow(self, audit_log):
        """Test workflow with mixed change types."""
        # GREEN: Auto-approved
        audit_log.record_change(
            change_type=ChangeType.PARAMETER_CHANGE,
            who="agent_01",
            what="Adaptive parameter adjustment",
            reason="Market conditions",
            auto_approve=True,
        )

        # YELLOW: Pending approval
        audit_log.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="agent_01",
            what="Proposed new product family",
            reason="Market opportunity",
            auto_approve=False,
        )

        # EMERGENCY: Bypass approval
        audit_log.record_emergency_change(
            change_type=ChangeType.EMERGENCY_CHANGE,
            who="emergency_system",
            what="Circuit breaker engaged",
            reason="Market crash",
        )

        # Check counts
        all_changes = audit_log.get_all_changes()
        assert len(all_changes) == 3

        pending = audit_log.get_pending_approvals()
        assert len(pending) == 2  # YELLOW is PENDING and EMERGENCY is EMERGENCY_BYPASSED

        auto_approved = audit_log.get_change_history(
            approval_status=ChangeApprovalStatus.AUTO_APPROVED
        )
        assert len(auto_approved) == 1

        emergency = audit_log.get_change_history(
            approval_status=ChangeApprovalStatus.EMERGENCY_BYPASSED
        )
        assert len(emergency) == 1

        yellow_pending = audit_log.get_change_history(
            approval_status=ChangeApprovalStatus.PENDING
        )
        assert len(yellow_pending) == 1
