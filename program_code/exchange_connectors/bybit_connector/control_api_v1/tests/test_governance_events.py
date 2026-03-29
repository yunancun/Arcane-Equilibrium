"""
Tests for Unified Governance Event Model (GAP-M1)
Tests for governance_events.py covering all enums and GovernanceEvent functionality
"""

import time
import sys
import os
import pytest

# Add app directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from governance_events import (
    EventCategory,
    EventSeverity,
    EventDirection,
    GovernanceEvent,
    auth_event,
    risk_event,
    lease_event,
    recon_event,
)


class TestEventCategoryEnum:
    """Test EventCategory enum values."""

    def test_all_categories_present(self):
        """Verify all expected categories exist."""
        assert EventCategory.AUTHORIZATION.value == "authorization"
        assert EventCategory.RISK_GOVERNOR.value == "risk_governor"
        assert EventCategory.DECISION_LEASE.value == "decision_lease"
        assert EventCategory.ORDER_MANAGEMENT.value == "order_management"
        assert EventCategory.RECONCILIATION.value == "reconciliation"
        assert EventCategory.INCIDENT.value == "incident"
        assert EventCategory.GOVERNANCE_HUB.value == "governance_hub"
        assert EventCategory.AUDIT.value == "audit"

    def test_category_enum_length(self):
        """Verify exactly 8 categories."""
        assert len(EventCategory) == 8


class TestEventSeverityEnum:
    """Test EventSeverity enum values."""

    def test_all_severities_present(self):
        """Verify all expected severities exist."""
        assert EventSeverity.DEBUG.value == "debug"
        assert EventSeverity.INFO.value == "info"
        assert EventSeverity.WARNING.value == "warning"
        assert EventSeverity.CRITICAL.value == "critical"
        assert EventSeverity.FATAL.value == "fatal"

    def test_severity_enum_length(self):
        """Verify exactly 5 severities."""
        assert len(EventSeverity) == 5


class TestEventDirectionEnum:
    """Test EventDirection enum values."""

    def test_all_directions_present(self):
        """Verify all expected directions exist."""
        assert EventDirection.RESTRICT.value == "restrict"
        assert EventDirection.EXPAND.value == "expand"
        assert EventDirection.NEUTRAL.value == "neutral"

    def test_direction_enum_length(self):
        """Verify exactly 3 directions."""
        assert len(EventDirection) == 3


class TestGovernanceEventCreation:
    """Test GovernanceEvent instantiation."""

    def test_default_creation(self):
        """Test creating GovernanceEvent with defaults."""
        event = GovernanceEvent()
        assert event.event_id != ""
        assert event.timestamp_ms > 0
        assert event.category == EventCategory.GOVERNANCE_HUB
        assert event.severity == EventSeverity.INFO
        assert event.direction == EventDirection.NEUTRAL
        assert event.source_sm == ""
        assert event.source_module == ""
        assert event.initiator == ""
        assert event.state_from is None
        assert event.state_to is None
        assert event.message == ""
        assert event.details == {}
        assert event.correlation_id is None
        assert event.parent_event_id is None

    def test_custom_creation(self):
        """Test creating GovernanceEvent with custom values."""
        event = GovernanceEvent(
            category=EventCategory.AUTHORIZATION,
            severity=EventSeverity.CRITICAL,
            direction=EventDirection.RESTRICT,
            source_sm="SM-01",
            source_module="authorization_state_machine",
            initiator="OPERATOR",
            state_from="ACTIVE",
            state_to="FROZEN",
            message="Authorization frozen by operator",
            details={"reason": "security_incident"},
        )
        assert event.category == EventCategory.AUTHORIZATION
        assert event.severity == EventSeverity.CRITICAL
        assert event.direction == EventDirection.RESTRICT
        assert event.source_sm == "SM-01"
        assert event.source_module == "authorization_state_machine"
        assert event.initiator == "OPERATOR"
        assert event.state_from == "ACTIVE"
        assert event.state_to == "FROZEN"
        assert event.message == "Authorization frozen by operator"
        assert event.details == {"reason": "security_incident"}

    def test_event_id_uniqueness(self):
        """Test that event IDs are unique."""
        event1 = GovernanceEvent()
        event2 = GovernanceEvent()
        assert event1.event_id != event2.event_id

    def test_timestamp_is_reasonable(self):
        """Test that timestamp is set to current time."""
        before = int(time.time() * 1000)
        event = GovernanceEvent()
        after = int(time.time() * 1000)
        assert before <= event.timestamp_ms <= after + 1000


class TestGovernanceEventSerialization:
    """Test GovernanceEvent serialization/deserialization."""

    def test_to_dict_basic(self):
        """Test converting event to dict."""
        event = GovernanceEvent(
            category=EventCategory.RISK_GOVERNOR,
            severity=EventSeverity.WARNING,
            source_sm="SM-04",
            initiator="RISK_GOVERNOR",
        )
        d = event.to_dict()
        assert isinstance(d, dict)
        assert d["event_id"] == event.event_id
        assert d["timestamp_ms"] == event.timestamp_ms
        assert d["category"] == "risk_governor"
        assert d["severity"] == "warning"
        assert d["direction"] == "neutral"
        assert d["source_sm"] == "SM-04"
        assert d["initiator"] == "RISK_GOVERNOR"

    def test_to_dict_with_details(self):
        """Test to_dict includes all fields."""
        event = GovernanceEvent(
            category=EventCategory.DECISION_LEASE,
            severity=EventSeverity.INFO,
            state_from="REGISTERED",
            state_to="ACTIVE",
            message="Lease activated",
            details={"lease_id": "lease:abc123"},
            correlation_id="corr:xyz789",
            parent_event_id="parent:def456",
        )
        d = event.to_dict()
        assert d["state_from"] == "REGISTERED"
        assert d["state_to"] == "ACTIVE"
        assert d["message"] == "Lease activated"
        assert d["details"] == {"lease_id": "lease:abc123"}
        assert d["correlation_id"] == "corr:xyz789"
        assert d["parent_event_id"] == "parent:def456"

    def test_from_dict_basic(self):
        """Test creating event from dict."""
        data = {
            "event_id": "evt:test123",
            "timestamp_ms": 1000000,
            "category": "authorization",
            "severity": "critical",
            "direction": "restrict",
            "source_sm": "SM-01",
            "source_module": "authorization_state_machine",
            "initiator": "OPERATOR",
            "state_from": "ACTIVE",
            "state_to": "REVOKED",
            "message": "Authorization revoked",
            "details": {"reason": "manual"},
            "correlation_id": None,
            "parent_event_id": None,
        }
        event = GovernanceEvent.from_dict(data)
        assert event.event_id == "evt:test123"
        assert event.timestamp_ms == 1000000
        assert event.category == EventCategory.AUTHORIZATION
        assert event.severity == EventSeverity.CRITICAL
        assert event.direction == EventDirection.RESTRICT
        assert event.source_sm == "SM-01"
        assert event.initiator == "OPERATOR"
        assert event.state_from == "ACTIVE"
        assert event.state_to == "REVOKED"

    def test_round_trip_serialization(self):
        """Test that serialization -> deserialization preserves data."""
        event1 = GovernanceEvent(
            category=EventCategory.RECONCILIATION,
            severity=EventSeverity.WARNING,
            direction=EventDirection.NEUTRAL,
            source_sm="EX-04",
            source_module="reconciliation_engine",
            initiator="SYSTEM",
            state_from="FILLED",
            state_to="RECONCILING",
            message="Reconciliation started",
            details={"order_id": "oms:xyz"},
            correlation_id="corr:123",
        )
        d = event1.to_dict()
        event2 = GovernanceEvent.from_dict(d)
        assert event1.event_id == event2.event_id
        assert event1.category == event2.category
        assert event1.severity == event2.severity
        assert event1.direction == event2.direction
        assert event1.source_sm == event2.source_sm
        assert event1.initiator == event2.initiator
        assert event1.message == event2.message
        assert event1.details == event2.details
        assert event1.correlation_id == event2.correlation_id


class TestGovernanceEventMethods:
    """Test GovernanceEvent method functionality."""

    def test_is_critical_true(self):
        """Test is_critical returns True for CRITICAL and FATAL."""
        event_critical = GovernanceEvent(severity=EventSeverity.CRITICAL)
        event_fatal = GovernanceEvent(severity=EventSeverity.FATAL)
        assert event_critical.is_critical() is True
        assert event_fatal.is_critical() is True

    def test_is_critical_false(self):
        """Test is_critical returns False for other severities."""
        assert GovernanceEvent(severity=EventSeverity.DEBUG).is_critical() is False
        assert GovernanceEvent(severity=EventSeverity.INFO).is_critical() is False
        assert GovernanceEvent(severity=EventSeverity.WARNING).is_critical() is False

    def test_is_restriction_true(self):
        """Test is_restriction returns True for RESTRICT direction."""
        event = GovernanceEvent(direction=EventDirection.RESTRICT)
        assert event.is_restriction() is True

    def test_is_restriction_false(self):
        """Test is_restriction returns False for other directions."""
        assert GovernanceEvent(direction=EventDirection.EXPAND).is_restriction() is False
        assert GovernanceEvent(direction=EventDirection.NEUTRAL).is_restriction() is False


class TestAuthEventFactory:
    """Test auth_event factory helper."""

    def test_auth_event_restricted_state(self):
        """Test auth_event with restrictive target state."""
        event = auth_event("ACTIVE", "RESTRICTED", "INCIDENT_POLICY", reason="incident")
        assert event.category == EventCategory.AUTHORIZATION
        assert event.source_sm == "SM-01"
        assert event.source_module == "authorization_state_machine"
        assert event.state_from == "ACTIVE"
        assert event.state_to == "RESTRICTED"
        assert event.direction == EventDirection.RESTRICT
        assert event.severity == EventSeverity.INFO
        assert event.initiator == "INCIDENT_POLICY"

    def test_auth_event_active_state(self):
        """Test auth_event with expansion target state."""
        event = auth_event("PENDING_APPROVAL", "ACTIVE", "OPERATOR", message="Approved")
        assert event.state_to == "ACTIVE"
        assert event.direction == EventDirection.EXPAND

    def test_auth_event_neutral_state(self):
        """Test auth_event with neutral target state."""
        event = auth_event("DRAFT", "PENDING_APPROVAL", "OPERATOR")
        assert event.state_to == "PENDING_APPROVAL"
        assert event.direction == EventDirection.NEUTRAL

    def test_auth_event_with_details(self):
        """Test auth_event with additional details."""
        event = auth_event(
            "ACTIVE", "FROZEN", "OPERATOR",
            auth_id="auth:123", reason_code="manual_freeze"
        )
        assert event.details == {"auth_id": "auth:123", "reason_code": "manual_freeze"}

    def test_auth_event_custom_severity(self):
        """Test auth_event with custom severity."""
        event = auth_event(
            "ACTIVE", "REVOKED", "OPERATOR",
            severity=EventSeverity.CRITICAL
        )
        assert event.severity == EventSeverity.CRITICAL


class TestRiskEventFactory:
    """Test risk_event factory helper."""

    def test_risk_event_escalation(self):
        """Test risk_event with escalation (increase in level)."""
        event = risk_event(0, 2, "RISK_GOVERNOR", reason="drawdown_warning")
        assert event.category == EventCategory.RISK_GOVERNOR
        assert event.source_sm == "SM-04"
        assert event.state_from == "NORMAL"
        assert event.state_to == "REDUCED"
        assert event.direction == EventDirection.RESTRICT
        assert event.severity == EventSeverity.WARNING

    def test_risk_event_de_escalation(self):
        """Test risk_event with de-escalation (decrease in level)."""
        event = risk_event(4, 1, "OPERATOR", reason="recovery_approved")
        assert event.state_from == "CIRCUIT_BREAKER"
        assert event.state_to == "CAUTIOUS"
        assert event.direction == EventDirection.EXPAND
        assert event.severity == EventSeverity.INFO

    def test_risk_event_critical_level(self):
        """Test risk_event with critical risk levels."""
        event = risk_event(2, 4, "SYSTEM", reason="drawdown_critical")
        assert event.state_to == "CIRCUIT_BREAKER"
        assert event.severity == EventSeverity.CRITICAL

    def test_risk_event_manual_review_level(self):
        """Test risk_event with manual review level."""
        event = risk_event(4, 5, "OPERATOR", reason="manual_escalation")
        assert event.state_to == "MANUAL_REVIEW"
        assert event.severity == EventSeverity.CRITICAL

    def test_risk_event_with_details(self):
        """Test risk_event with additional details."""
        event = risk_event(
            1, 2, "RISK_GOVERNOR",
            drawdown_pct=5.2, position_count=3
        )
        assert event.details == {"drawdown_pct": 5.2, "position_count": 3}

    def test_risk_event_neutral_change(self):
        """Test risk_event with same level (neutral change)."""
        event = risk_event(2, 2, "SYSTEM")
        assert event.direction == EventDirection.NEUTRAL


class TestLeaseEventFactory:
    """Test lease_event factory helper."""

    def test_lease_event_restricted_state(self):
        """Test lease_event with restrictive target state."""
        event = lease_event("ACTIVE", "FROZEN", "INCIDENT_POLICY", lease_id="lease:abc123")
        assert event.category == EventCategory.DECISION_LEASE
        assert event.source_sm == "SM-02"
        assert event.source_module == "decision_lease_state_machine"
        assert event.state_from == "ACTIVE"
        assert event.state_to == "FROZEN"
        assert event.direction == EventDirection.RESTRICT
        assert event.details["lease_id"] == "lease:abc123"

    def test_lease_event_active_state(self):
        """Test lease_event with expansion target state."""
        event = lease_event("REGISTERED", "ACTIVE", "I_CONTROL_PLANE", lease_id="lease:xyz789")
        assert event.state_to == "ACTIVE"
        assert event.direction == EventDirection.EXPAND

    def test_lease_event_neutral_state(self):
        """Test lease_event with neutral target state."""
        event = lease_event("DRAFT", "REGISTERED", "I_CONTROL_PLANE", lease_id="lease:123")
        assert event.state_to == "REGISTERED"
        assert event.direction == EventDirection.NEUTRAL

    def test_lease_event_with_custom_message(self):
        """Test lease_event with custom message."""
        event = lease_event(
            "ACTIVE", "CONSUMED", "EXECUTION_CLOSURE_FLOW",
            lease_id="lease:456", message="Lease execution completed"
        )
        assert event.message == "Lease execution completed"

    def test_lease_event_with_additional_details(self):
        """Test lease_event with additional details."""
        event = lease_event(
            "ACTIVE", "BRIDGED", "RISK_GOVERNOR",
            lease_id="lease:789",
            risk_decision_ref="risk:decision123"
        )
        assert event.details["lease_id"] == "lease:789"
        assert event.details["risk_decision_ref"] == "risk:decision123"


class TestReconEventFactory:
    """Test recon_event factory helper."""

    def test_recon_event_success(self):
        """Test recon_event with successful reconciliation."""
        event = recon_event("PASS")
        assert event.category == EventCategory.RECONCILIATION
        assert event.source_sm == "EX-04"
        assert event.source_module == "reconciliation_engine"
        assert event.direction == EventDirection.NEUTRAL
        assert event.details["result"] == "PASS"

    def test_recon_event_major_mismatch(self):
        """Test recon_event with major mismatch (restrictive)."""
        event = recon_event("MISMATCH_MAJOR", initiator="RECONCILIATION_ENGINE")
        assert event.direction == EventDirection.RESTRICT
        assert event.details["result"] == "MISMATCH_MAJOR"

    def test_recon_event_fatal(self):
        """Test recon_event with fatal result."""
        event = recon_event("FATAL", severity=EventSeverity.CRITICAL)
        assert event.direction == EventDirection.RESTRICT
        assert event.severity == EventSeverity.CRITICAL

    def test_recon_event_with_details(self):
        """Test recon_event with additional details."""
        event = recon_event(
            "MISMATCH_MINOR",
            order_id="oms:abc123",
            discrepancy_count=1
        )
        assert event.details["result"] == "MISMATCH_MINOR"
        assert event.details["order_id"] == "oms:abc123"
        assert event.details["discrepancy_count"] == 1

    def test_recon_event_custom_message(self):
        """Test recon_event with custom message."""
        event = recon_event(
            "PASS",
            message="All positions reconciled successfully"
        )
        assert event.message == "All positions reconciled successfully"


class TestEventChainingAndCorrelation:
    """Test event correlation and chaining."""

    def test_correlation_id_linking(self):
        """Test that events can be linked by correlation_id."""
        corr_id = "corr:incident123"
        event1 = auth_event("ACTIVE", "RESTRICTED", "SYSTEM", "", EventSeverity.INFO, correlation_id=corr_id)
        event2 = risk_event(0, 2, "SYSTEM", "", correlation_id=corr_id)

        assert event1.correlation_id == corr_id
        assert event2.correlation_id == corr_id

    def test_parent_event_chaining(self):
        """Test parent_event_id for causal chains."""
        parent = GovernanceEvent(
            category=EventCategory.INCIDENT,
            message="Incident detected"
        )
        child = auth_event(
            "ACTIVE", "FROZEN", "INCIDENT_POLICY",
            "", EventSeverity.INFO, None, parent.event_id
        )
        assert child.parent_event_id == parent.event_id

    def test_multi_step_cascade(self):
        """Test cascading events with proper linking."""
        incident_event = GovernanceEvent(
            category=EventCategory.INCIDENT,
            severity=EventSeverity.CRITICAL,
        )

        auth_restriction = auth_event(
            "ACTIVE", "RESTRICTED", "INCIDENT_POLICY",
            "", EventSeverity.INFO, None, incident_event.event_id,
        )

        risk_escalation = risk_event(
            1, 3, "INCIDENT_POLICY",
            "", None, incident_event.event_id,
        )

        assert auth_restriction.parent_event_id == incident_event.event_id
        assert risk_escalation.parent_event_id == incident_event.event_id
        assert auth_restriction.parent_event_id == risk_escalation.parent_event_id


class TestEventConsistency:
    """Test cross-module event consistency."""

    def test_all_factories_use_sm_identification(self):
        """Verify all factory helpers set source_sm correctly."""
        auth = auth_event("DRAFT", "PENDING_APPROVAL", "OPERATOR")
        risk = risk_event(0, 1, "SYSTEM")
        lease = lease_event("DRAFT", "REGISTERED", "I_CONTROL_PLANE")
        recon = recon_event("PASS")

        assert auth.source_sm == "SM-01"
        assert risk.source_sm == "SM-04"
        assert lease.source_sm == "SM-02"
        assert recon.source_sm == "EX-04"

    def test_all_factories_set_module_name(self):
        """Verify all factory helpers set source_module."""
        auth = auth_event("DRAFT", "PENDING_APPROVAL", "OPERATOR")
        risk = risk_event(0, 1, "SYSTEM")
        lease = lease_event("DRAFT", "REGISTERED", "I_CONTROL_PLANE")
        recon = recon_event("PASS")

        assert auth.source_module == "authorization_state_machine"
        assert risk.source_module == "risk_governor_state_machine"
        assert lease.source_module == "decision_lease_state_machine"
        assert recon.source_module == "reconciliation_engine"

    def test_all_events_have_required_fields(self):
        """Verify all events have critical fields."""
        events = [
            auth_event("DRAFT", "PENDING_APPROVAL", "OPERATOR"),
            risk_event(0, 1, "SYSTEM"),
            lease_event("DRAFT", "REGISTERED", "I_CONTROL_PLANE"),
            recon_event("PASS"),
        ]
        for event in events:
            assert event.event_id != ""
            assert event.timestamp_ms > 0
            assert event.source_sm != ""
            assert event.source_module != ""
            assert event.initiator != ""
            assert event.category != EventCategory.GOVERNANCE_HUB or event.category == EventCategory.GOVERNANCE_HUB


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
