"""
Test suite for Recovery Approval Gate
恢复批准门禁测试套件

Coverage targets:
- All public methods
- All state transitions
- All edge cases
- Audit callbacks
- Thread safety
- Observation period logic
"""

import pytest
import threading
import time
from unittest.mock import Mock, call

from app.recovery_approval_gate import (
    RecoveryApprovalGate,
    RecoveryType,
    ApprovalStatus,
    ObservationPeriodStatus,
    RecoveryRequest,
    RecoveryApproval,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def audit_callback():
    """Mock audit callback"""
    return Mock()


@pytest.fixture
def gate(audit_callback):
    """Create gate instance with mocked audit"""
    return RecoveryApprovalGate(audit_callback=audit_callback)


# ═══════════════════════════════════════════════════════════════════════════════
# RecoveryRequest Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestRecoveryRequest:
    """Test RecoveryRequest dataclass"""

    def test_request_creation_basic(self):
        """Test creating a recovery request with minimal params"""
        req = RecoveryRequest(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test recovery",
        )
        assert req.request_id.startswith("rec_req:")
        assert req.recovery_type == RecoveryType.AUTH_UNFREEZE
        assert req.from_state == "FROZEN"
        assert req.to_state == "RESTRICTED"
        assert req.requested_by == "Operator:test"
        assert req.status == ApprovalStatus.PENDING
        assert req.requested_at_ms > 0

    def test_request_auto_id_generation(self):
        """Test that request IDs are auto-generated and unique"""
        req1 = RecoveryRequest(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
        )
        req2 = RecoveryRequest(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
        )
        assert req1.request_id != req2.request_id

    def test_request_with_observation_period(self):
        """Test request with observation period"""
        req = RecoveryRequest(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
            observation_period_hours=24,
        )
        assert req.observation_period_hours == 24

    def test_request_with_evidence(self):
        """Test request with supporting evidence"""
        evidence = {"root_cause": "issue resolved", "verified": True}
        req = RecoveryRequest(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
            evidence=evidence,
        )
        assert req.evidence == evidence

    def test_request_to_dict(self):
        """Test request serialization"""
        req = RecoveryRequest(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test recovery",
            observation_period_hours=12,
        )
        d = req.to_dict()
        assert d["request_id"] == req.request_id
        assert d["recovery_type"] == "auth_unfreeze"
        assert d["from_state"] == "FROZEN"
        assert d["to_state"] == "RESTRICTED"
        assert d["requested_by"] == "Operator:test"
        assert d["status"] == "pending"
        assert d["observation_period_hours"] == 12


# ═══════════════════════════════════════════════════════════════════════════════
# RecoveryApproval Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestRecoveryApproval:
    """Test RecoveryApproval dataclass"""

    def test_approval_creation_basic(self):
        """Test creating an approval"""
        approval = RecoveryApproval(
            request_id="rec_req:123",
            approved_by="Operator:nancun",
        )
        assert approval.request_id == "rec_req:123"
        assert approval.approved_by == "Operator:nancun"
        assert approval.approval_id.startswith("rec_app:")
        assert approval.approved_at_ms > 0

    def test_approval_with_observation(self):
        """Test approval with observation period"""
        now_ms = int(time.time() * 1000)
        end_ms = now_ms + 24 * 3600 * 1000
        approval = RecoveryApproval(
            request_id="rec_req:123",
            approved_by="Operator:nancun",
            observation_start_ms=now_ms,
            observation_end_ms=end_ms,
        )
        assert approval.has_observation_period is True
        assert approval.is_observation_complete is False

    def test_approval_observation_complete(self):
        """Test observation period completion check"""
        now_ms = int(time.time() * 1000)
        past_ms = now_ms - 1000  # 1 second ago
        approval = RecoveryApproval(
            request_id="rec_req:123",
            approved_by="Operator:nancun",
            observation_start_ms=past_ms - 100,
            observation_end_ms=past_ms,
        )
        assert approval.has_observation_period is True
        assert approval.is_observation_complete is True

    def test_approval_no_observation(self):
        """Test approval without observation period"""
        approval = RecoveryApproval(
            request_id="rec_req:123",
            approved_by="Operator:nancun",
        )
        assert approval.has_observation_period is False
        assert approval.is_observation_complete is True

    def test_approval_with_conditions(self):
        """Test approval with conditions"""
        conditions = ["No new anomalies", "Health check passed"]
        approval = RecoveryApproval(
            request_id="rec_req:123",
            approved_by="Operator:nancun",
            conditions=conditions,
        )
        assert approval.conditions == conditions

    def test_approval_to_dict(self):
        """Test approval serialization"""
        now_ms = int(time.time() * 1000)
        approval = RecoveryApproval(
            request_id="rec_req:123",
            approved_by="Operator:nancun",
            approved_at_ms=now_ms,
            observation_start_ms=now_ms,
            observation_end_ms=now_ms + 86400000,
            conditions=["Test condition"],
            notes="Test approval",
        )
        d = approval.to_dict()
        assert d["request_id"] == "rec_req:123"
        assert d["approved_by"] == "Operator:nancun"
        assert d["conditions"] == ["Test condition"]
        assert d["notes"] == "Test approval"
        assert d["has_observation_period"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# Gate Request Submission Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestGateSubmitRequest:
    """Test RecoveryApprovalGate.submit_recovery_request()"""

    def test_submit_basic_request(self, gate, audit_callback):
        """Test submitting a basic recovery request"""
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test recovery",
        )
        assert req.request_id.startswith("rec_req:")
        assert req.recovery_type == RecoveryType.AUTH_UNFREEZE
        assert req.status == ApprovalStatus.PENDING

        # Verify audit callback was called
        audit_callback.assert_called_once()
        audit_call = audit_callback.call_args[0][0]
        assert audit_call["event_type"] == "recovery_request_submitted"
        assert audit_call["request_id"] == req.request_id

    def test_submit_request_with_observation(self, gate, audit_callback):
        """Test submitting request with observation period requirement"""
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.INCIDENT_RESOLVE,
            from_state="DEFENSIVE",
            to_state="REDUCED",
            requested_by="Operator:test",
            reason="Incident resolved",
            observation_period_hours=24,
        )
        assert req.observation_period_hours == 24
        audit_call = audit_callback.call_args[0][0]
        assert audit_call["observation_period_hours"] == 24

    def test_submit_request_with_evidence(self, gate):
        """Test submitting request with evidence"""
        evidence = {"verified": True, "checks_passed": 5}
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
            evidence=evidence,
        )
        assert req.evidence == evidence

    def test_submit_all_recovery_types(self, gate):
        """Test submitting all recovery types"""
        recovery_types = [
            RecoveryType.AUTH_UNFREEZE,
            RecoveryType.AUTH_RESTORE,
            RecoveryType.RISK_DEESCALATE,
            RecoveryType.RISK_UNFREEZE,
            RecoveryType.INCIDENT_RESOLVE,
            RecoveryType.TRADING_RESUME,
        ]
        for rec_type in recovery_types:
            req = gate.submit_recovery_request(
                recovery_type=rec_type,
                from_state="FROZEN",
                to_state="ACTIVE",
                requested_by="Operator:test",
                reason="Test",
            )
            assert req.recovery_type == rec_type

    def test_submit_updates_stats(self, gate):
        """Test that submission updates stats"""
        gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
        )
        stats = gate.get_stats()
        assert stats["requests_submitted"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Gate Approval Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestGateApproveRecovery:
    """Test RecoveryApprovalGate.approve_recovery()"""

    def test_approve_basic_request(self, gate, audit_callback):
        """Test Operator approving a recovery request"""
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
        )
        audit_callback.reset_mock()

        approval = gate.approve_recovery(
            request_id=req.request_id,
            approved_by="Operator:nancun",
        )
        assert approval is not None
        assert approval.request_id == req.request_id
        assert approval.approved_by == "Operator:nancun"

        # Verify audit
        audit_call = audit_callback.call_args[0][0]
        assert audit_call["event_type"] == "recovery_approved"
        assert audit_call["approved_by"] == "Operator:nancun"

    def test_approve_with_conditions(self, gate):
        """Test approval with conditions"""
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
        )
        conditions = ["No new near-miss", "Health check passed"]
        approval = gate.approve_recovery(
            request_id=req.request_id,
            approved_by="Operator:nancun",
            conditions=conditions,
        )
        assert approval.conditions == conditions

    def test_approve_with_observation_period(self, gate):
        """Test approval with observation period"""
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
            observation_period_hours=24,
        )
        approval = gate.approve_recovery(
            request_id=req.request_id,
            approved_by="Operator:nancun",
            observation_period_hours=24,
        )
        assert approval.has_observation_period is True
        assert approval.observation_end_ms > approval.observation_start_ms

    def test_approve_override_observation_period(self, gate):
        """Test approving with observation period override"""
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
            observation_period_hours=24,
        )
        approval = gate.approve_recovery(
            request_id=req.request_id,
            approved_by="Operator:nancun",
            observation_period_hours=12,  # Override to shorter period
        )
        expected_duration = 12 * 3600 * 1000
        actual_duration = approval.observation_end_ms - approval.observation_start_ms
        assert abs(actual_duration - expected_duration) < 100  # Allow 100ms variance

    def test_approve_updates_request_status(self, gate):
        """Test that approval updates request status"""
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
        )
        assert req.status == ApprovalStatus.PENDING

        gate.approve_recovery(
            request_id=req.request_id,
            approved_by="Operator:nancun",
        )

        updated_req = gate.get_request(req.request_id)
        assert updated_req["status"] == "approved"

    def test_approve_nonexistent_request(self, gate):
        """Test approving a request that doesn't exist"""
        approval = gate.approve_recovery(
            request_id="rec_req:nonexistent",
            approved_by="Operator:nancun",
        )
        assert approval is None

    def test_approve_already_approved_request(self, gate):
        """Test approving a request that's already approved"""
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
        )
        gate.approve_recovery(
            request_id=req.request_id,
            approved_by="Operator:nancun",
        )

        # Try to approve again
        approval2 = gate.approve_recovery(
            request_id=req.request_id,
            approved_by="Operator:other",
        )
        assert approval2 is None

    def test_approve_updates_stats(self, gate):
        """Test that approval updates stats"""
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
        )
        gate.approve_recovery(
            request_id=req.request_id,
            approved_by="Operator:nancun",
        )
        stats = gate.get_stats()
        assert stats["requests_approved"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Gate Rejection Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestGateRejectRecovery:
    """Test RecoveryApprovalGate.reject_recovery()"""

    def test_reject_basic_request(self, gate, audit_callback):
        """Test Operator rejecting a recovery request"""
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
        )
        audit_callback.reset_mock()

        result = gate.reject_recovery(
            request_id=req.request_id,
            rejected_by="Operator:nancun",
            reason="Conditions not met",
        )
        assert result is True

        # Verify request status
        updated_req = gate.get_request(req.request_id)
        assert updated_req["status"] == "rejected"

        # Verify audit
        audit_call = audit_callback.call_args[0][0]
        assert audit_call["event_type"] == "recovery_rejected"
        assert audit_call["rejected_by"] == "Operator:nancun"

    def test_reject_nonexistent_request(self, gate):
        """Test rejecting a request that doesn't exist"""
        result = gate.reject_recovery(
            request_id="rec_req:nonexistent",
            rejected_by="Operator:nancun",
        )
        assert result is False

    def test_reject_already_approved_request(self, gate):
        """Test rejecting a request that's already approved"""
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
        )
        gate.approve_recovery(
            request_id=req.request_id,
            approved_by="Operator:nancun",
        )

        # Try to reject approved request
        result = gate.reject_recovery(
            request_id=req.request_id,
            rejected_by="Operator:other",
        )
        assert result is False

    def test_reject_updates_stats(self, gate):
        """Test that rejection updates stats"""
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
        )
        gate.reject_recovery(
            request_id=req.request_id,
            rejected_by="Operator:nancun",
        )
        stats = gate.get_stats()
        assert stats["requests_rejected"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Observation Period Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestObservationPeriod:
    """Test observation period checking"""

    def test_check_observation_not_required(self, gate):
        """Test observation period check when not required"""
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
        )
        gate.approve_recovery(
            request_id=req.request_id,
            approved_by="Operator:nancun",
            observation_period_hours=0,
        )

        status = gate.check_observation_period(req.request_id)
        assert status == ObservationPeriodStatus.NOT_REQUIRED

    def test_check_observation_pending(self, gate):
        """Test observation period check when pending"""
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
            observation_period_hours=24,
        )
        gate.approve_recovery(
            request_id=req.request_id,
            approved_by="Operator:nancun",
            observation_period_hours=24,
        )

        status = gate.check_observation_period(req.request_id)
        assert status == ObservationPeriodStatus.PENDING

    def test_check_observation_completed(self, gate):
        """Test observation period check when completed"""
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
        )

        # Manually set approval with past end time
        now_ms = int(time.time() * 1000)
        gate.approve_recovery(
            request_id=req.request_id,
            approved_by="Operator:nancun",
            observation_period_hours=0,  # Will have no observation
        )

        # Get approval and manually set past end time
        approval = gate._approvals[req.request_id]
        approval.observation_end_ms = now_ms - 1000  # 1 second ago

        status = gate.check_observation_period(req.request_id)
        assert status == ObservationPeriodStatus.COMPLETED

    def test_check_observation_nonexistent_request(self, gate):
        """Test observation check for nonexistent request"""
        status = gate.check_observation_period("rec_req:nonexistent")
        assert status == ObservationPeriodStatus.NOT_REQUIRED

    def test_mark_observation_failed(self, gate, audit_callback):
        """Test marking observation period as failed"""
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
            observation_period_hours=24,
        )
        gate.approve_recovery(
            request_id=req.request_id,
            approved_by="Operator:nancun",
            observation_period_hours=24,
        )
        audit_callback.reset_mock()

        result = gate.mark_observation_failed(
            request_id=req.request_id,
            reason="Near-miss detected",
        )
        assert result is True

        stats = gate.get_stats()
        assert stats["observations_failed"] == 1

        # Verify audit
        audit_call = audit_callback.call_args[0][0]
        assert audit_call["event_type"] == "observation_period_failed"

    def test_mark_observation_failed_nonexistent(self, gate):
        """Test marking nonexistent observation as failed"""
        result = gate.mark_observation_failed(
            request_id="rec_req:nonexistent",
        )
        assert result is False

    def test_get_pending_observations(self, gate):
        """Test retrieving pending observations"""
        req1 = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
            observation_period_hours=24,
        )
        gate.approve_recovery(
            request_id=req1.request_id,
            approved_by="Operator:nancun",
            observation_period_hours=24,
        )

        # Create a request with no observation
        req2 = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_RESTORE,
            from_state="RESTRICTED",
            to_state="ACTIVE",
            requested_by="Operator:test",
            reason="Test",
        )
        gate.approve_recovery(
            request_id=req2.request_id,
            approved_by="Operator:nancun",
        )

        pending = gate.get_pending_observations()
        assert len(pending) == 1
        assert pending[0]["request_id"] == req1.request_id


# ═══════════════════════════════════════════════════════════════════════════════
# Query Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestGateQueries:
    """Test gate query methods"""

    def test_get_pending_requests(self, gate):
        """Test retrieving pending requests"""
        req1 = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test1",
        )
        req2 = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_RESTORE,
            from_state="RESTRICTED",
            to_state="ACTIVE",
            requested_by="Operator:test",
            reason="Test2",
        )
        gate.approve_recovery(
            request_id=req2.request_id,
            approved_by="Operator:nancun",
        )

        pending = gate.get_pending_requests()
        assert len(pending) == 1
        assert pending[0]["request_id"] == req1.request_id

    def test_get_approved_requests(self, gate):
        """Test retrieving approved requests"""
        req1 = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test1",
        )
        req2 = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_RESTORE,
            from_state="RESTRICTED",
            to_state="ACTIVE",
            requested_by="Operator:test",
            reason="Test2",
        )
        gate.approve_recovery(
            request_id=req1.request_id,
            approved_by="Operator:nancun",
        )

        approved = gate.get_approved_requests()
        assert len(approved) == 1
        assert approved[0]["request_id"] == req1.request_id

    def test_get_request(self, gate):
        """Test retrieving specific request"""
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
        )
        retrieved = gate.get_request(req.request_id)
        assert retrieved is not None
        assert retrieved["request_id"] == req.request_id

    def test_get_request_nonexistent(self, gate):
        """Test retrieving nonexistent request"""
        retrieved = gate.get_request("rec_req:nonexistent")
        assert retrieved is None

    def test_get_approval(self, gate):
        """Test retrieving approval"""
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
        )
        gate.approve_recovery(
            request_id=req.request_id,
            approved_by="Operator:nancun",
        )
        approval = gate.get_approval(req.request_id)
        assert approval is not None
        assert approval["approved_by"] == "Operator:nancun"

    def test_get_approval_nonexistent(self, gate):
        """Test retrieving approval for nonexistent request"""
        approval = gate.get_approval("rec_req:nonexistent")
        assert approval is None

    def test_get_requests_by_type(self, gate):
        """Test retrieving requests by type"""
        req1 = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test1",
        )
        req2 = gate.submit_recovery_request(
            recovery_type=RecoveryType.RISK_DEESCALATE,
            from_state="DEFENSIVE",
            to_state="REDUCED",
            requested_by="Operator:test",
            reason="Test2",
        )

        auth_reqs = gate.get_requests_by_type(RecoveryType.AUTH_UNFREEZE)
        assert len(auth_reqs) == 1
        assert auth_reqs[0]["request_id"] == req1.request_id

        risk_reqs = gate.get_requests_by_type(RecoveryType.RISK_DEESCALATE)
        assert len(risk_reqs) == 1
        assert risk_reqs[0]["request_id"] == req2.request_id

    def test_get_stats(self, gate):
        """Test retrieving stats"""
        gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test1",
        )
        req2 = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_RESTORE,
            from_state="RESTRICTED",
            to_state="ACTIVE",
            requested_by="Operator:test",
            reason="Test2",
        )
        gate.approve_recovery(
            request_id=req2.request_id,
            approved_by="Operator:nancun",
        )

        stats = gate.get_stats()
        assert stats["requests_submitted"] == 2
        assert stats["requests_approved"] == 1
        assert stats["requests_rejected"] == 0
        assert stats["pending_requests"] == 1
        assert stats["total_approvals"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Thread Safety Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestThreadSafety:
    """Test thread safety"""

    def test_concurrent_submissions(self, gate):
        """Test concurrent request submissions"""
        request_ids = []
        lock = threading.Lock()

        def submit_request(index):
            req = gate.submit_recovery_request(
                recovery_type=RecoveryType.AUTH_UNFREEZE,
                from_state="FROZEN",
                to_state="RESTRICTED",
                requested_by=f"Operator:test{index}",
                reason=f"Test {index}",
            )
            with lock:
                request_ids.append(req.request_id)

        threads = [
            threading.Thread(target=submit_request, args=(i,))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify all requests were created
        assert len(request_ids) == 10
        assert len(set(request_ids)) == 10  # All unique

    def test_concurrent_approval_and_rejection(self, gate):
        """Test concurrent approval and rejection"""
        reqs = [
            gate.submit_recovery_request(
                recovery_type=RecoveryType.AUTH_UNFREEZE,
                from_state="FROZEN",
                to_state="RESTRICTED",
                requested_by="Operator:test",
                reason=f"Test {i}",
            )
            for i in range(10)
        ]

        def approve_or_reject(index):
            if index % 2 == 0:
                gate.approve_recovery(
                    request_id=reqs[index].request_id,
                    approved_by="Operator:nancun",
                )
            else:
                gate.reject_recovery(
                    request_id=reqs[index].request_id,
                    rejected_by="Operator:nancun",
                )

        threads = [
            threading.Thread(target=approve_or_reject, args=(i,))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify stats
        stats = gate.get_stats()
        assert stats["requests_approved"] == 5
        assert stats["requests_rejected"] == 5


# ═══════════════════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntegration:
    """Integration tests for full recovery workflow"""

    def test_full_recovery_workflow_with_observation(self, gate):
        """Test complete recovery workflow with observation period"""
        # 1. Submit recovery request
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.INCIDENT_RESOLVE,
            from_state="DEFENSIVE",
            to_state="REDUCED",
            requested_by="System:incident_policy",
            reason="Incident contained, entering observation",
            observation_period_hours=24,
            evidence={"incident_id": "inc:test123"},
        )

        # 2. Check pending requests
        pending = gate.get_pending_requests()
        assert len(pending) == 1

        # 3. Operator approves with conditions
        approval = gate.approve_recovery(
            request_id=req.request_id,
            approved_by="Operator:nancun",
            conditions=[
                "No new incidents during observation",
                "Health metrics stable",
            ],
            observation_period_hours=24,
            notes="Incident recovery approved, starting 24h observation",
        )

        # 4. Verify observation is pending
        obs_status = gate.check_observation_period(req.request_id)
        assert obs_status == ObservationPeriodStatus.PENDING

        # 5. Verify pending observations list
        pending_obs = gate.get_pending_observations()
        assert len(pending_obs) == 1

    def test_rejected_recovery_workflow(self, gate):
        """Test recovery request rejection workflow"""
        # 1. Submit recovery request
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="System:recovery",
            reason="Test recovery",
        )

        # 2. Operator rejects
        gate.reject_recovery(
            request_id=req.request_id,
            rejected_by="Operator:nancun",
            reason="Conditions not met",
        )

        # 3. Verify it's not in pending
        pending = gate.get_pending_requests()
        assert len(pending) == 0

        # 4. Verify request status is rejected
        req_data = gate.get_request(req.request_id)
        assert req_data["status"] == "rejected"

    def test_multiple_recovery_types_workflow(self, gate):
        """Test handling multiple recovery types"""
        # Submit various recovery types
        types_and_states = [
            (RecoveryType.AUTH_UNFREEZE, "FROZEN", "RESTRICTED"),
            (RecoveryType.AUTH_RESTORE, "RESTRICTED", "ACTIVE"),
            (RecoveryType.RISK_DEESCALATE, "DEFENSIVE", "REDUCED"),
            (RecoveryType.RISK_UNFREEZE, "CIRCUIT_BREAKER", "DEFENSIVE"),
            (RecoveryType.INCIDENT_RESOLVE, "DEFENSIVE", "REDUCED"),
            (RecoveryType.TRADING_RESUME, "FROZEN", "ACTIVE"),
        ]

        for rec_type, from_state, to_state in types_and_states:
            gate.submit_recovery_request(
                recovery_type=rec_type,
                from_state=from_state,
                to_state=to_state,
                requested_by="System:test",
                reason="Test",
            )

        # Verify all types are tracked
        for rec_type, _, _ in types_and_states:
            reqs = gate.get_requests_by_type(rec_type)
            assert len(reqs) == 1
            assert reqs[0]["recovery_type"] == rec_type.value


# ═══════════════════════════════════════════════════════════════════════════════
# Error Handling and Edge Cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditErrorHandling:
    """Test audit callback error handling"""

    def test_no_audit_callback(self):
        """Test gate without audit callback (should not crash)"""
        gate = RecoveryApprovalGate(audit_callback=None)
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
        )
        # Should not raise despite no callback
        assert req.request_id.startswith("rec_req:")

    def test_audit_callback_exception(self):
        """Test gate handles audit callback exceptions gracefully"""
        def bad_callback(event_dict):
            raise RuntimeError("Audit error")

        gate = RecoveryApprovalGate(audit_callback=bad_callback)
        # Should not raise even though callback raises
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
        )
        assert req.request_id.startswith("rec_req:")

    def test_audit_on_approval_with_exception(self):
        """Test audit callback exception during approval"""
        def bad_callback(event_dict):
            raise RuntimeError("Audit error")

        gate = RecoveryApprovalGate(audit_callback=bad_callback)
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
        )
        # Should not raise even though callback raises
        approval = gate.approve_recovery(
            request_id=req.request_id,
            approved_by="Operator:nancun",
        )
        assert approval is not None

    def test_audit_on_rejection_with_exception(self):
        """Test audit callback exception during rejection"""
        def bad_callback(event_dict):
            raise RuntimeError("Audit error")

        gate = RecoveryApprovalGate(audit_callback=bad_callback)
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:test",
            reason="Test",
        )
        # Should not raise even though callback raises
        result = gate.reject_recovery(
            request_id=req.request_id,
            rejected_by="Operator:nancun",
        )
        assert result is True


class TestEnumValues:
    """Test enum values for JSON serialization"""

    def test_recovery_type_values(self):
        """Test RecoveryType enum values"""
        assert RecoveryType.AUTH_UNFREEZE.value == "auth_unfreeze"
        assert RecoveryType.AUTH_RESTORE.value == "auth_restore"
        assert RecoveryType.RISK_DEESCALATE.value == "risk_deescalate"
        assert RecoveryType.RISK_UNFREEZE.value == "risk_unfreeze"
        assert RecoveryType.INCIDENT_RESOLVE.value == "incident_resolve"
        assert RecoveryType.TRADING_RESUME.value == "trading_resume"

    def test_approval_status_values(self):
        """Test ApprovalStatus enum values"""
        assert ApprovalStatus.PENDING.value == "pending"
        assert ApprovalStatus.APPROVED.value == "approved"
        assert ApprovalStatus.REJECTED.value == "rejected"
        assert ApprovalStatus.CANCELLED.value == "cancelled"

    def test_observation_period_status_values(self):
        """Test ObservationPeriodStatus enum values"""
        assert ObservationPeriodStatus.NOT_REQUIRED.value == "not_required"
        assert ObservationPeriodStatus.PENDING.value == "pending"
        assert ObservationPeriodStatus.COMPLETED.value == "completed"
        assert ObservationPeriodStatus.FAILED.value == "failed"


class TestRecoveryApprovalPostInit:
    """Test RecoveryApproval post-init logic for observation_start_ms"""

    def test_observation_start_ms_auto_set(self):
        """Test observation_start_ms is auto-set when observation_end_ms provided"""
        now_ms = int(time.time() * 1000)
        end_ms = now_ms + 86400000

        # Create approval with end_ms but no start_ms
        approval = RecoveryApproval(
            request_id="rec_req:test",
            approved_by="Operator:test",
            approved_at_ms=now_ms,
            observation_end_ms=end_ms,
        )

        # observation_start_ms should be set to approved_at_ms
        assert approval.observation_start_ms == now_ms
        assert approval.observation_end_ms == end_ms
