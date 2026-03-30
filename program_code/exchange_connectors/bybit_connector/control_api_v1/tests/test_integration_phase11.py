"""
Integration Tests Phase 11: OMS Event + Engine Tier Enforcement + Correlation Chaining
整合测试第 11 阶段：OMS 事件 + 引擎层级强制 + 关联链

Test Suite:
- IT-P11-01: oms_event() factory creates ORDER_MANAGEMENT events
- IT-P11-02: OMS reconciliation pass emits COMPLETED event
- IT-P11-03: OMS reconciliation fail emits REJECTED event
- IT-P11-04: Engine submit_order rejected at L1 tier
- IT-P11-05: Engine submit_order allowed without gate (backward compat)
- IT-P11-06: Engine tick blocked at L0 (no can_record_observations)
- IT-P11-07: Engine cancel_order rejected at L1 tier
- IT-P11-08: Engine _check_tier_capability helper
- IT-P11-09: Risk escalation events have correlation_id
- IT-P11-10: Auth events share correlation_id with parent risk event
- IT-P11-11: Lease events share correlation_id with parent risk event
- IT-P11-12: Recon cascade events have correlation_id
- IT-P11-13: Events have parent_event_id linking to trigger
- IT-P11-14: Full cascade all events share same correlation_id
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


class TestOMSEventFactory:
    """IT-P11-01: oms_event() factory creates ORDER_MANAGEMENT events"""

    def test_oms_event_factory_exists(self):
        """oms_event() factory function is importable"""
        from app.governance_events import oms_event
        assert callable(oms_event)

    def test_oms_event_creates_correct_category(self):
        """oms_event() creates event with ORDER_MANAGEMENT category"""
        from app.governance_events import oms_event
        evt = oms_event(
            order_id="ord-001",
            state_from="RECONCILING",
            state_to="COMPLETED",
            initiator="ReconciliationEngine",
        )
        assert evt.category.value == "order_management"
        assert evt.state_from == "RECONCILING"
        assert evt.state_to == "COMPLETED"
        d = evt.to_dict()
        assert d["details"]["order_id"] == "ord-001"

    def test_oms_event_rejected_state_is_warning(self):
        """REJECTED state gets WARNING severity"""
        from app.governance_events import oms_event
        evt = oms_event(
            order_id="ord-002",
            state_from="RECONCILING",
            state_to="REJECTED",
            initiator="ReconciliationEngine",
        )
        assert evt.severity.value == "warning"
        assert evt.direction.value == "restrict"


class TestOMSEventEmission:
    """IT-P11-02/03: OMS events emitted on reconciliation"""

    def test_oms_reconciliation_pass_emits_event(self):
        """Reconciliation PASS emits OMS COMPLETED event"""
        from app.governance_hub import GovernanceHub

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir, enabled=True)
            hub._initialized = True

            mock_oms = Mock()
            mock_order = {"order_id": "ord-pass-001"}
            mock_oms.get_by_state.return_value = [mock_order]
            mock_oms.reconciliation_pass = Mock()
            hub._oms_sm = mock_oms

            hub._handle_oms_reconciliation({"overall_result": "PASS"})

            oms_events = [
                e for e in hub._governance_events
                if e.get("category") == "order_management"
            ]
            assert len(oms_events) > 0, "Expected OMS event after recon pass"
            assert oms_events[0]["state_to"] == "COMPLETED"

    def test_oms_reconciliation_fail_emits_event(self):
        """Reconciliation FAIL emits OMS REJECTED event"""
        from app.governance_hub import GovernanceHub

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir, enabled=True)
            hub._initialized = True

            mock_oms = Mock()
            mock_order = {"order_id": "ord-fail-001"}
            mock_oms.get_by_state.return_value = [mock_order]
            mock_oms.reconciliation_fail = Mock()
            hub._oms_sm = mock_oms

            hub._handle_oms_reconciliation({"overall_result": "MISMATCH_MAJOR"})

            oms_events = [
                e for e in hub._governance_events
                if e.get("category") == "order_management"
            ]
            assert len(oms_events) > 0, "Expected OMS event after recon fail"
            assert oms_events[0]["state_to"] == "REJECTED"


class TestEngineTierEnforcement:
    """IT-P11-04..08: LearningTierGate enforcement in PaperTradingEngine"""

    def _make_engine(self):
        from app.paper_trading_engine import PaperTradingEngine, PaperStateStore
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            temp_path = f.name
        store = PaperStateStore(temp_path)
        engine = PaperTradingEngine(store)
        return engine, temp_path

    def test_submit_order_rejected_at_l1(self):
        """L1 tier blocks submit_order (requires L3+)"""
        from app.learning_tier_gate import LearningTierGate

        engine, temp_path = self._make_engine()
        try:
            gate = LearningTierGate()  # L1 default
            engine.set_learning_tier_gate(gate)

            result = engine.submit_order("BTCUSDT", "Buy", "Market", 0.01)
            assert result["rejected_reason"] is not None
            assert "tier too low" in result["rejected_reason"].lower()
        finally:
            os.unlink(temp_path)

    def test_submit_order_allowed_without_gate(self):
        """No gate = no restriction (backward compat) — tier check passes, session check fails"""
        engine, temp_path = self._make_engine()
        try:
            # Don't set gate — tier check should pass (returns True)
            # But will raise ValueError because session not started
            try:
                result = engine.submit_order("BTCUSDT", "Buy", "Market", 0.01)
                # If we get here, tier check passed (no tier rejection)
                assert result.get("rejected_reason") != "Learning tier too low for autonomous order submission (requires L3+)"
            except (ValueError, KeyError):
                # Expected: session not started, but tier gate did NOT block
                pass
        finally:
            os.unlink(temp_path)

    def test_cancel_order_rejected_at_l1(self):
        """L1 tier blocks cancel_order"""
        from app.learning_tier_gate import LearningTierGate

        engine, temp_path = self._make_engine()
        try:
            gate = LearningTierGate()
            engine.set_learning_tier_gate(gate)

            result = engine.cancel_order("fake-order-id")
            assert result["reason"] is not None
            assert "tier too low" in result["reason"].lower()
        finally:
            os.unlink(temp_path)

    def test_tick_blocked_without_observation_capability(self):
        """Gate that denies can_record_observations blocks tick"""
        engine, temp_path = self._make_engine()
        try:
            mock_gate = Mock()
            mock_gate.can_record_observations.return_value = False
            engine.set_learning_tier_gate(mock_gate)

            result = engine.tick({"BTCUSDT": 50000.0})
            assert result["orders_filled"] == 0
            assert result["fills"] == []
        finally:
            os.unlink(temp_path)

    def test_check_tier_capability_helper(self):
        """_check_tier_capability returns correct values"""
        from app.learning_tier_gate import LearningTierGate

        engine, temp_path = self._make_engine()
        try:
            gate = LearningTierGate()
            engine.set_learning_tier_gate(gate)

            assert engine._check_tier_capability("can_record_observations") is True
            assert engine._check_tier_capability("can_discover_patterns") is False
            assert engine._check_tier_capability("nonexistent") is True  # Unknown = allow
        finally:
            os.unlink(temp_path)


class TestCorrelationIdChaining:
    """IT-P11-09..14: Cross-event correlation_id propagation"""

    def test_risk_event_has_correlation_id(self):
        """Risk escalation event gets a correlation_id"""
        from app.governance_hub import GovernanceHub

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir, enabled=True)
            hub._initialized = True

            hub._on_risk_escalation(0, 2)

            risk_events = [
                e for e in hub._governance_events
                if e.get("category") == "risk_governor"
            ]
            assert len(risk_events) > 0
            assert risk_events[0].get("correlation_id") is not None

    def test_auth_events_share_correlation_with_risk(self):
        """Auth restrict events share correlation_id with trigger risk event"""
        from app.governance_hub import GovernanceHub

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir, enabled=True)
            hub._initialized = True

            mock_auth = Mock()
            mock_auth_record = Mock()
            mock_auth_record.authorization_id = "auth-corr-001"
            mock_auth_record.state = Mock()
            mock_auth_record.state.value = "ACTIVE"
            mock_auth.get_effective.return_value = [mock_auth_record]
            mock_auth.restrict = Mock()
            hub._authorization_sm = mock_auth

            hub._on_risk_escalation(0, 2)

            risk_events = [e for e in hub._governance_events if e.get("category") == "risk_governor"]
            auth_events = [e for e in hub._governance_events if e.get("category") == "authorization"]

            assert len(risk_events) > 0
            assert len(auth_events) > 0

            risk_corr_id = risk_events[0].get("correlation_id")
            auth_corr_id = auth_events[0].get("correlation_id")

            assert risk_corr_id is not None
            assert auth_corr_id == risk_corr_id, "Auth event should share correlation_id with risk event"

    def test_auth_events_have_parent_event_id(self):
        """Auth events reference risk event as parent"""
        from app.governance_hub import GovernanceHub

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir, enabled=True)
            hub._initialized = True

            mock_auth = Mock()
            mock_auth_record = Mock()
            mock_auth_record.authorization_id = "auth-parent-001"
            mock_auth_record.state = Mock()
            mock_auth_record.state.value = "ACTIVE"
            mock_auth.get_effective.return_value = [mock_auth_record]
            mock_auth.restrict = Mock()
            hub._authorization_sm = mock_auth

            hub._on_risk_escalation(0, 2)

            risk_events = [e for e in hub._governance_events if e.get("category") == "risk_governor"]
            auth_events = [e for e in hub._governance_events if e.get("category") == "authorization"]

            risk_event_id = risk_events[0].get("event_id")
            auth_parent_id = auth_events[0].get("parent_event_id")

            assert auth_parent_id == risk_event_id, "Auth event parent should be the risk event"

    def test_lease_events_share_correlation_in_cascade(self):
        """Lease revoke events share correlation_id in full cascade"""
        from app.governance_hub import GovernanceHub

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir, enabled=True)
            hub._initialized = True

            mock_auth = Mock()
            mock_auth_record = Mock()
            mock_auth_record.authorization_id = "auth-cascade-001"
            mock_auth_record.state = Mock()
            mock_auth_record.state.value = "ACTIVE"
            mock_auth.get_effective.return_value = [mock_auth_record]
            mock_auth.freeze = Mock()

            mock_lease = Mock()
            mock_lease_record = Mock()
            mock_lease_record.lease_id = "lease-cascade-001"
            mock_lease.get_live.return_value = [mock_lease_record]
            mock_lease.revoke = Mock()

            hub._authorization_sm = mock_auth
            hub._lease_sm = mock_lease

            hub._on_risk_escalation(0, 4)

            risk_events = [e for e in hub._governance_events if e.get("category") == "risk_governor"]
            lease_events = [e for e in hub._governance_events if e.get("category") == "decision_lease"]

            assert len(risk_events) > 0
            assert len(lease_events) > 0

            risk_corr_id = risk_events[0].get("correlation_id")
            lease_corr_id = lease_events[0].get("correlation_id")

            assert risk_corr_id is not None
            assert lease_corr_id == risk_corr_id, "Lease event should share correlation_id with risk event"

    def test_recon_cascade_has_correlation(self):
        """Reconciliation FATAL cascade events have correlation_id"""
        from app.governance_hub import GovernanceHub

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir, enabled=True)
            hub._initialized = True

            mock_auth = Mock()
            mock_auth_record = Mock()
            mock_auth_record.authorization_id = "auth-recon-001"
            mock_auth_record.state = Mock()
            mock_auth_record.state.value = "ACTIVE"
            mock_auth.get_effective.return_value = [mock_auth_record]
            mock_auth.freeze = Mock()

            mock_lease = Mock()
            mock_lease.get_live.return_value = []

            hub._authorization_sm = mock_auth
            hub._lease_sm = mock_lease

            hub._on_reconciliation_mismatch("FATAL", {"balance": 100})

            recon_events = [e for e in hub._governance_events if e.get("category") == "reconciliation"]
            auth_events = [e for e in hub._governance_events if e.get("category") == "authorization"]

            assert len(recon_events) > 0
            recon_corr_id = recon_events[0].get("correlation_id")
            assert recon_corr_id is not None, "Recon event should have correlation_id"

            if auth_events:
                assert auth_events[0].get("correlation_id") == recon_corr_id
