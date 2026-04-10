"""
Integration Tests Phase 10: Auth/Lease Event Emission + LearningTierGate Enforcement + REST
整合测试第 10 阶段：授权/租约事件发射 + 学习层级门控强制执行 + REST 端点

Test Suite:
- IT-P10-01: Auth events emitted on risk escalation restrict
- IT-P10-02: Auth events emitted on circuit breaker freeze
- IT-P10-03: Lease events emitted on auth frozen cascade
- IT-P10-04: Events filterable by category=authorization
- IT-P10-05: Events filterable by category=decision_lease
- IT-P10-06: LearningTierGate L1 can_record_observations=True
- IT-P10-07: LearningTierGate L1 can_discover_patterns=False
- IT-P10-08: GovernanceHub check_learning_tier_capability helper
- IT-P10-09: GET /learning-tier/status returns status
- IT-P10-10: GET /oms/orders returns order list
- IT-P10-11: Bounded event buffer respects max size
- IT-P10-12: Full cascade emits risk + auth + lease events
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from unittest.mock import Mock, patch, MagicMock

import pytest

logger = logging.getLogger(__name__)


class TestAuthEventEmission:
    """IT-P10-01/02: Auth events emitted on risk escalation"""

    def test_risk_escalation_restrict_emits_auth_events(self):
        """Auth restrict events emitted when risk >= 2"""
        from app.governance_hub import GovernanceHub
        from app.authorization_state_machine import AuthorizationStateMachine

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir, enabled=True)

            # Create mock auth SM that returns active auths
            mock_auth = Mock()
            mock_auth_record = Mock()
            mock_auth_record.authorization_id = "auth-001"
            mock_auth_record.state = Mock()
            mock_auth_record.state.value = "ACTIVE"
            mock_auth.get_effective.return_value = [mock_auth_record]
            mock_auth.restrict = Mock()

            hub._authorization_sm = mock_auth
            hub._initialized = True

            # Trigger risk escalation to level 2 (REDUCED → restrict)
            hub._on_risk_escalation(0, 2)

            # Find auth events in stream
            auth_events = [
                e for e in hub._governance_events
                if e.get("category") == "authorization"
            ]
            assert len(auth_events) > 0, "Expected auth events after restrict"
            assert auth_events[0].get("state_to") == "RESTRICTED"

    def test_circuit_breaker_freeze_emits_auth_events(self):
        """Auth freeze events emitted when risk >= 4 (CIRCUIT_BREAKER)"""
        from app.governance_hub import GovernanceHub

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir, enabled=True)

            mock_auth = Mock()
            mock_auth_record = Mock()
            mock_auth_record.authorization_id = "auth-002"
            mock_auth_record.state = Mock()
            mock_auth_record.state.value = "ACTIVE"
            mock_auth.get_effective.return_value = [mock_auth_record]
            mock_auth.freeze = Mock()

            hub._authorization_sm = mock_auth
            hub._lease_sm = Mock()
            hub._lease_sm.get_live.return_value = []
            hub._initialized = True

            # Trigger circuit breaker
            hub._on_risk_escalation(0, 4)

            # Find auth freeze events
            auth_events = [
                e for e in hub._governance_events
                if e.get("category") == "authorization" and e.get("state_to") == "FROZEN"
            ]
            assert len(auth_events) > 0, "Expected FROZEN auth events on circuit breaker"


class TestLeaseEventEmission:
    """IT-P10-03: Lease events emitted on auth frozen cascade"""

    def test_auth_frozen_cascade_emits_lease_events(self):
        """Lease revoke events emitted when auth is frozen"""
        from app.governance_hub import GovernanceHub

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir, enabled=True)

            # Mock lease SM with active leases
            mock_lease = Mock()
            mock_lease_record = Mock()
            mock_lease_record.lease_id = "lease-001"
            mock_lease.get_live.return_value = [mock_lease_record]
            mock_lease.revoke = Mock()

            hub._lease_sm = mock_lease
            hub._initialized = True

            # Trigger auth frozen → lease revocation
            hub._on_auth_frozen()

            # Find lease events in stream
            lease_events = [
                e for e in hub._governance_events
                if e.get("category") == "decision_lease"
            ]
            assert len(lease_events) > 0, "Expected lease events after auth frozen cascade"
            assert lease_events[0].get("state_to") == "REVOKED"

    def test_auth_frozen_with_multiple_leases(self):
        """Multiple lease revoke events for multiple active leases"""
        from app.governance_hub import GovernanceHub

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir, enabled=True)

            mock_lease = Mock()
            leases = []
            for i in range(3):
                lr = Mock()
                lr.lease_id = f"lease-{i:03d}"
                leases.append(lr)
            mock_lease.get_live.return_value = leases
            mock_lease.revoke = Mock()

            hub._lease_sm = mock_lease
            hub._initialized = True

            hub._on_auth_frozen()

            lease_events = [
                e for e in hub._governance_events
                if e.get("category") == "decision_lease"
            ]
            assert len(lease_events) == 3, f"Expected 3 lease events, got {len(lease_events)}"


class TestEventCategoryFilter:
    """IT-P10-04/05: Events filterable by category"""

    def test_filter_by_authorization_category(self):
        """get_governance_events with event_type=authorization"""
        from app.governance_hub import GovernanceHub

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir)

            # Add mixed events
            hub._governance_events.append({"category": "risk_governor", "event_id": "r1"})
            hub._governance_events.append({"category": "authorization", "event_id": "a1"})
            hub._governance_events.append({"category": "reconciliation", "event_id": "c1"})
            hub._governance_events.append({"category": "authorization", "event_id": "a2"})

            events = hub.get_governance_events(event_type="authorization")
            assert all(e["category"] == "authorization" for e in events), "Filter should only return auth events"
            assert len(events) == 2, f"Expected 2 auth events, got {len(events)}"

    def test_filter_by_decision_lease_category(self):
        """get_governance_events with event_type=decision_lease"""
        from app.governance_hub import GovernanceHub

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir)

            hub._governance_events.append({"category": "decision_lease", "event_id": "l1"})
            hub._governance_events.append({"category": "risk_governor", "event_id": "r1"})
            hub._governance_events.append({"category": "decision_lease", "event_id": "l2"})

            events = hub.get_governance_events(event_type="decision_lease")
            assert all(e["category"] == "decision_lease" for e in events), "Filter should only return lease events"
            assert len(events) == 2


class TestLearningTierGateCapabilities:
    """IT-P10-06/07: LearningTierGate capability checks at L1"""

    def test_l1_can_record_observations(self):
        """L1 tier allows observation recording"""
        from app.learning_tier_gate import LearningTierGate

        gate = LearningTierGate()
        # Default tier is L1
        assert gate.can_record_observations() is True, "L1 should allow observation recording"

    def test_l1_cannot_discover_patterns(self):
        """L1 tier does NOT allow pattern discovery (requires L2+)"""
        from app.learning_tier_gate import LearningTierGate

        gate = LearningTierGate()
        assert gate.can_discover_patterns() is False, "L1 should NOT allow pattern discovery"

    def test_l1_cannot_evolve_strategies(self):
        """L1 tier does NOT allow strategy evolution (requires L4+)"""
        from app.learning_tier_gate import LearningTierGate

        gate = LearningTierGate()
        assert gate.can_evolve_strategies() is False, "L1 should NOT allow strategy evolution"

    def test_can_modify_live_config_always_false(self):
        """can_modify_live_config is always False across all tiers"""
        from app.learning_tier_gate import LearningTierGate

        gate = LearningTierGate()
        assert gate.can_modify_live_config() is False, "can_modify_live_config should always be False"


class TestGovernanceHubTierEnforcement:
    """IT-P10-08: GovernanceHub check_learning_tier_capability helper"""

    def test_check_capability_with_no_gate(self):
        """No gate = always allowed (backward compat)"""
        from app.governance_hub import GovernanceHub

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir)
            assert hub._learning_tier_gate is None
            assert hub.check_learning_tier_capability("can_discover_patterns") is True

    def test_check_capability_with_gate_allows(self):
        """Gate L1 + can_record_observations = True"""
        from app.governance_hub import GovernanceHub
        from app.learning_tier_gate import LearningTierGate

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir)
            gate = LearningTierGate()
            hub.set_learning_tier_gate(gate)

            assert hub.check_learning_tier_capability("can_record_observations") is True

    def test_check_capability_with_gate_denies(self):
        """Gate L1 + can_discover_patterns = False"""
        from app.governance_hub import GovernanceHub
        from app.learning_tier_gate import LearningTierGate

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir)
            gate = LearningTierGate()
            hub.set_learning_tier_gate(gate)

            assert hub.check_learning_tier_capability("can_discover_patterns") is False

    def test_check_unknown_capability_allows(self):
        """Unknown capability = allowed"""
        from app.governance_hub import GovernanceHub
        from app.learning_tier_gate import LearningTierGate

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir)
            gate = LearningTierGate()
            hub.set_learning_tier_gate(gate)

            assert hub.check_learning_tier_capability("nonexistent_method") is True

    def test_de_escalation_denied_at_low_tier(self):
        """De-escalation request denied when tier < L4"""
        from app.governance_hub import GovernanceHub
        from app.learning_tier_gate import LearningTierGate

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir, enabled=True)
            gate = LearningTierGate()  # L1 by default
            hub.set_learning_tier_gate(gate)
            hub._initialized = True

            # Mock recovery gate
            hub._recovery_gate = Mock()

            result = hub.request_de_escalation(
                target_level=0,
                requested_by="test_user",
                reason="test"
            )
            assert result is None, "De-escalation should be denied at L1 tier"


class TestLearningTierRESTEndpoint:
    """IT-P10-09: GET /learning-tier/status"""

    def test_learning_tier_status_endpoint_exists(self):
        """Verify /learning-tier/status route is registered"""
        from app.governance_routes import governance_router

        routes = [route for route in governance_router.routes if '/learning-tier/status' in route.path]
        assert len(routes) > 0, "Missing /learning-tier/status endpoint"

    def test_learning_tier_status_via_hub(self):
        """GovernanceHub.get_learning_tier_status returns correct structure"""
        from app.governance_hub import GovernanceHub
        from app.learning_tier_gate import LearningTierGate

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir)
            gate = LearningTierGate()
            hub.set_learning_tier_gate(gate)

            status = hub.get_learning_tier_status()
            assert status["available"] is True
            assert "capabilities" in status
            assert status["capabilities"]["can_record_observations"] is True
            assert status["capabilities"]["can_discover_patterns"] is False

    def test_learning_tier_status_without_gate(self):
        """GovernanceHub.get_learning_tier_status returns unavailable when no gate"""
        from app.governance_hub import GovernanceHub

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir)

            status = hub.get_learning_tier_status()
            assert status["available"] is False

    def test_promote_endpoint_exists(self):
        """Verify /learning-tier/promote route is registered"""
        from app.governance_routes import governance_router

        routes = [route for route in governance_router.routes if '/learning-tier/promote' in route.path]
        assert len(routes) > 0, "Missing /learning-tier/promote endpoint"


class TestOMSOrdersEndpoint:
    """IT-P10-10: GET /oms/orders — Python OMS removed 2026-04-10, returns empty list + note"""

    def test_oms_orders_endpoint_exists(self):
        """Verify /oms/orders route is still registered (deprecated stub)"""
        from app.governance_routes import governance_router

        routes = [route for route in governance_router.routes if '/oms/orders' in route.path]
        assert len(routes) > 0, "Missing /oms/orders endpoint"

    def test_oms_orders_returns_empty_migrated(self):
        """GET /oms/orders returns empty list with migration note; get_oms_orders removed from hub"""
        from app.governance_hub import GovernanceHub

        hub = GovernanceHub.__new__(GovernanceHub)
        # get_oms_orders no longer exists — order tracking in Rust trading.orders
        assert not hasattr(hub, "get_oms_orders"), "get_oms_orders must be removed from GovernanceHub"


class TestBoundedEventBuffer:
    """IT-P10-11: Bounded event buffer"""

    def test_event_buffer_does_not_exceed_max(self):
        """Event list stays bounded at max_size"""
        from app.governance_hub import GovernanceHub

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir)

            # Add 1050 events (exceeding 1000 max)
            for i in range(1050):
                hub._append_governance_event({"event_id": f"evt_{i}", "category": "test"})

            assert len(hub._governance_events) <= 1000, \
                f"Event list should be bounded at 1000, got {len(hub._governance_events)}"


class TestFullCascadeEventEmission:
    """IT-P10-12: Full cascade emits risk + auth + lease events"""

    def test_circuit_breaker_cascade_emits_all_event_types(self):
        """Risk CIRCUIT_BREAKER triggers risk_event + auth_event + lease_event"""
        from app.governance_hub import GovernanceHub

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir, enabled=True)

            # Setup mock auth SM
            mock_auth = Mock()
            mock_auth_record = Mock()
            mock_auth_record.authorization_id = "auth-cascade"
            mock_auth_record.state = Mock()
            mock_auth_record.state.value = "ACTIVE"
            mock_auth.get_effective.return_value = [mock_auth_record]
            mock_auth.freeze = Mock()

            # Setup mock lease SM
            mock_lease = Mock()
            mock_lease_record = Mock()
            mock_lease_record.lease_id = "lease-cascade"
            mock_lease.get_live.return_value = [mock_lease_record]
            mock_lease.revoke = Mock()

            hub._authorization_sm = mock_auth
            hub._lease_sm = mock_lease
            hub._initialized = True

            # Trigger full cascade: risk → auth freeze → lease revoke
            hub._on_risk_escalation(0, 4)

            # Collect categories
            categories = set(e.get("category") for e in hub._governance_events)

            assert "risk_governor" in categories, "Missing risk_governor event"
            assert "authorization" in categories, "Missing authorization event"
            assert "decision_lease" in categories, "Missing decision_lease event"

            # Verify event count: 1 risk + 1 auth freeze + 1 lease revoke = at least 3
            assert len(hub._governance_events) >= 3, \
                f"Expected at least 3 events in cascade, got {len(hub._governance_events)}"
