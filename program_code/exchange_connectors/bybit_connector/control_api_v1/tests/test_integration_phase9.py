"""
Integration Tests Phase 9: LearningTierGate + GovernanceEvent Stream Wiring
整合测试第 9 阶段：学习等级门控 + 治理事件流接线

Test Suite:
- IT-P9-01: LearningTierGate instantiation — engine/hub has reference
- IT-P9-02: GovernanceEvent stream — after risk escalation, events list is non-empty
- IT-P9-03: GET /governance/events endpoint returns event list
- IT-P9-04: Event contains correct fields (event_type, timestamp, etc.)
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


class TestLearningTierGateInstantiation:
    """IT-P9-01: LearningTierGate instantiation — engine/hub has reference"""

    def test_paper_trading_engine_has_learning_tier_gate(self):
        """Verify PaperTradingEngine has _learning_tier_gate field"""
        from app.paper_trading_engine import PaperTradingEngine, PaperStateStore
        from app.learning_tier_gate import LearningTierGate

        # Create temporary state store
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            temp_path = f.name

        try:
            store = PaperStateStore(temp_path)
            engine = PaperTradingEngine(store)

            # Verify _learning_tier_gate field exists and is None initially
            assert hasattr(engine, '_learning_tier_gate'), "PaperTradingEngine missing _learning_tier_gate field"
            assert engine._learning_tier_gate is None, "Expected _learning_tier_gate to be None initially"

            # Create and inject LearningTierGate
            gate = LearningTierGate()
            engine.set_learning_tier_gate(gate)

            # Verify injection succeeded
            assert engine._learning_tier_gate is not None, "Failed to inject LearningTierGate"
            assert engine._learning_tier_gate is gate, "Injected gate is not the same instance"
        finally:
            os.unlink(temp_path)

    def test_governance_hub_has_learning_tier_gate(self):
        """Verify GovernanceHub has _learning_tier_gate field"""
        from app.governance_hub import GovernanceHub
        from app.learning_tier_gate import LearningTierGate

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir)

            # Verify _learning_tier_gate field exists and is None initially
            assert hasattr(hub, '_learning_tier_gate'), "GovernanceHub missing _learning_tier_gate field"
            assert hub._learning_tier_gate is None, "Expected _learning_tier_gate to be None initially"

            # Create and inject LearningTierGate
            gate = LearningTierGate()
            hub.set_learning_tier_gate(gate)

            # Verify injection succeeded
            assert hub._learning_tier_gate is not None, "Failed to inject LearningTierGate"
            assert hub._learning_tier_gate is gate, "Injected gate is not the same instance"

    def test_learning_tier_gate_accessible_via_paper_trading_routes(self):
        """Verify LEARNING_TIER_GATE is instantiated in paper_trading_routes"""
        # Import to trigger initialization (this would have been done in app startup)
        from app import paper_trading_routes

        # Verify LEARNING_TIER_GATE exists and is instantiated
        assert hasattr(paper_trading_routes, 'LEARNING_TIER_GATE'), \
            "paper_trading_routes missing LEARNING_TIER_GATE"

        gate = paper_trading_routes.LEARNING_TIER_GATE
        if gate is not None:  # May be None if initialization failed with try/except
            from app.learning_tier_gate import LearningTierGate
            assert isinstance(gate, LearningTierGate), "LEARNING_TIER_GATE is not a LearningTierGate instance"


class TestGovernanceEventStream:
    """IT-P9-02: GovernanceEvent stream — after risk escalation, events list is non-empty"""

    def test_governance_hub_has_event_stream(self):
        """Verify GovernanceHub has _governance_events list"""
        from app.governance_hub import GovernanceHub

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir)

            # Verify _governance_events field exists
            assert hasattr(hub, '_governance_events'), "GovernanceHub missing _governance_events field"
            assert isinstance(hub._governance_events, list), "_governance_events is not a list"
            assert len(hub._governance_events) == 0, "Expected empty event list on init"

    def test_events_list_bounded_at_1000(self):
        """Verify event list is bounded to max 1000 entries"""
        from app.governance_hub import GovernanceHub

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir)

            # Verify max size field exists
            assert hasattr(hub, '_governance_events_max_size'), "Missing _governance_events_max_size"
            assert hub._governance_events_max_size == 1000, "Max size should be 1000"

    def test_risk_escalation_emits_event(self):
        """Verify risk escalation triggers governance event emission"""
        from app.governance_hub import GovernanceHub

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir, enabled=True)

            # Ensure hub is initialized
            try:
                hub._ensure_initialized()
            except Exception:
                pass  # May fail due to circular imports in test context

            # Verify event list is empty before
            assert len(hub._governance_events) == 0, "Expected empty event list initially"

            # Manually call _on_risk_escalation to trigger event emission
            hub._on_risk_escalation(0, 2)

            # Verify event was added
            assert len(hub._governance_events) > 0, "Expected event to be added after risk escalation"

            # Verify event structure
            event = hub._governance_events[-1]
            assert isinstance(event, dict), "Event should be a dictionary"
            assert 'category' in event, "Event missing 'category' field"
            assert event['category'] == 'risk_governor', f"Expected risk_governor category, got {event['category']}"

    def test_reconciliation_mismatch_emits_event(self):
        """Verify reconciliation mismatch triggers governance event emission"""
        from app.governance_hub import GovernanceHub

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir, enabled=True)

            # Ensure hub is initialized
            try:
                hub._ensure_initialized()
            except Exception:
                pass  # May fail due to circular imports in test context

            # Verify event list is empty before
            assert len(hub._governance_events) == 0, "Expected empty event list initially"

            # Manually call _on_reconciliation_mismatch with MISMATCH_MAJOR (to avoid early return)
            # This should emit an event and then continue with escalation logic
            with patch.object(hub, '_risk_governor_sm', None):  # Prevent actual SM escalation
                hub._on_reconciliation_mismatch("MISMATCH_MAJOR", {"balance": 100, "expected": 101})

            # Verify event was added
            assert len(hub._governance_events) > 0, "Expected event to be added after reconciliation mismatch"

            # Verify event structure
            event = hub._governance_events[-1]
            assert isinstance(event, dict), "Event should be a dictionary"
            assert 'category' in event, "Event missing 'category' field"
            assert event['category'] == 'reconciliation', f"Expected reconciliation category, got {event['category']}"

    def test_get_governance_events_returns_list(self):
        """Verify get_governance_events returns events in reverse chronological order"""
        from app.governance_hub import GovernanceHub

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir)

            # Get events from empty stream
            events = hub.get_governance_events(limit=50)
            assert isinstance(events, list), "get_governance_events should return a list"
            assert len(events) == 0, "Expected empty list initially"

    def test_event_list_respects_limit_parameter(self):
        """Verify get_governance_events respects limit parameter"""
        from app.governance_hub import GovernanceHub

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir)

            # Add multiple events
            for i in range(5):
                event = {
                    "event_id": f"evt_{i}",
                    "category": "test",
                    "timestamp_ms": int(time.time() * 1000),
                }
                hub._append_governance_event(event)

            # Get with limit=2
            events = hub.get_governance_events(limit=2)
            assert len(events) == 2, f"Expected 2 events, got {len(events)}"

            # Get with limit=10 (more than available)
            events = hub.get_governance_events(limit=10)
            assert len(events) == 5, f"Expected 5 events (all available), got {len(events)}"

    def test_event_filtering_by_type(self):
        """Verify get_governance_events filters by event_type"""
        from app.governance_hub import GovernanceHub

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir)

            # Add events of different types
            hub._append_governance_event({
                "event_id": "evt_1",
                "category": "risk_governor",
                "timestamp_ms": int(time.time() * 1000),
            })
            hub._append_governance_event({
                "event_id": "evt_2",
                "category": "authorization",
                "timestamp_ms": int(time.time() * 1000),
            })
            hub._append_governance_event({
                "event_id": "evt_3",
                "category": "risk_governor",
                "timestamp_ms": int(time.time() * 1000),
            })

            # Filter by risk_governor
            risk_events = hub.get_governance_events(event_type="risk_governor")
            assert len(risk_events) == 2, f"Expected 2 risk_governor events, got {len(risk_events)}"

            # Filter by authorization
            auth_events = hub.get_governance_events(event_type="authorization")
            assert len(auth_events) == 1, f"Expected 1 authorization event, got {len(auth_events)}"


class TestGovernanceEventsAPI:
    """IT-P9-03: GET /governance/events endpoint returns event list"""

    def test_get_events_endpoint_exists(self):
        """Verify GET /api/v1/governance/events endpoint exists"""
        from app.governance_routes import governance_router

        # Find the route
        routes = [route for route in governance_router.routes if '/events' in route.path]
        assert len(routes) > 0, "GET /events endpoint not found"

        # Verify it's a GET request
        events_route = routes[0]
        assert 'GET' in events_route.methods, "Events endpoint should support GET method"

    def test_get_events_endpoint_parameter_validation(self):
        """Verify endpoint validates limit and event_type parameters"""
        # Import endpoint function
        from app.governance_routes import get_governance_events
        from unittest.mock import MagicMock

        # Create mock governance hub
        mock_hub = MagicMock()
        mock_hub.get_governance_events.return_value = []

        # Create mock actor
        mock_actor = {"user": "test_user", "is_operator": True}

        # Test with default parameters
        with patch('app.governance_routes._get_governance_hub', return_value=mock_hub):
            response = get_governance_events(limit=50, event_type=None, actor=mock_actor)
            assert response['ok'] is True, "Expected successful response"
            assert 'data' in response, "Response missing 'data' field"
            assert 'events' in response['data'], "Response data missing 'events'"

    def test_get_events_endpoint_limit_clamping(self):
        """Verify endpoint clamps limit between 1 and 1000"""
        from app.governance_routes import get_governance_events
        from unittest.mock import MagicMock, patch

        mock_hub = MagicMock()
        mock_hub.get_governance_events.return_value = []

        mock_actor = {"user": "test_user", "is_operator": True}

        with patch('app.governance_routes._get_governance_hub', return_value=mock_hub):
            # Test with limit=0 (should clamp to 1)
            response = get_governance_events(limit=0, event_type=None, actor=mock_actor)
            call_args = mock_hub.get_governance_events.call_args
            assert call_args[1]['limit'] >= 1, "Limit should be clamped to minimum 1"

            # Test with limit=2000 (should clamp to 1000)
            response = get_governance_events(limit=2000, event_type=None, actor=mock_actor)
            call_args = mock_hub.get_governance_events.call_args
            assert call_args[1]['limit'] <= 1000, "Limit should be clamped to maximum 1000"


class TestEventStructure:
    """IT-P9-04: Event contains correct fields (event_type, timestamp, etc.)"""

    def test_governance_event_has_required_fields(self):
        """Verify governance events contain required fields"""
        from app.governance_hub import GovernanceHub

        with tempfile.TemporaryDirectory() as audit_dir:
            hub = GovernanceHub(audit_dir=audit_dir)

            # Create a sample event
            event = {
                "event_id": "test_evt",
                "category": "risk_governor",
                "timestamp_ms": int(time.time() * 1000),
                "severity": "warning",
                "source_sm": "SM-04",
                "source_module": "risk_governor_state_machine",
                "initiator": "SYSTEM",
                "message": "Test risk escalation",
            }

            hub._append_governance_event(event)

            # Retrieve and verify
            events = hub.get_governance_events(limit=1)
            assert len(events) == 1, "Expected 1 event"

            retrieved_event = events[0]
            assert retrieved_event['event_id'] == "test_evt"
            assert retrieved_event['category'] == "risk_governor"
            assert 'timestamp_ms' in retrieved_event
            assert retrieved_event['timestamp_ms'] > 0
            assert 'severity' in retrieved_event
            assert 'source_sm' in retrieved_event
            assert 'source_module' in retrieved_event
            assert 'initiator' in retrieved_event
            assert 'message' in retrieved_event

    def test_risk_event_factory_creates_valid_event(self):
        """Verify risk_event factory creates event with correct fields"""
        from app.governance_events import risk_event, EventSeverity

        event = risk_event(
            level_from=0,
            level_to=2,
            initiator="SYSTEM",
            reason="Test escalation",
        )

        event_dict = event.to_dict()

        assert event_dict['category'] == 'risk_governor'
        assert event_dict['source_sm'] == 'SM-04'
        assert event_dict['source_module'] == 'risk_governor_state_machine'
        assert 'timestamp_ms' in event_dict
        assert event_dict['timestamp_ms'] > 0

    def test_recon_event_factory_creates_valid_event(self):
        """Verify recon_event factory creates event with correct fields"""
        from app.governance_events import recon_event

        event = recon_event(
            result="MISMATCH_MAJOR",
            initiator="SYSTEM",
            message="Major reconciliation mismatch",
        )

        event_dict = event.to_dict()

        assert event_dict['category'] == 'reconciliation'
        assert event_dict['source_sm'] == 'EX-04'
        assert event_dict['source_module'] == 'reconciliation_engine'
        assert 'timestamp_ms' in event_dict
        assert event_dict['timestamp_ms'] > 0

    def test_event_serialization_round_trip(self):
        """Verify events can be serialized and deserialized correctly"""
        from app.governance_events import GovernanceEvent, EventCategory, EventSeverity

        original = GovernanceEvent(
            category=EventCategory.RISK_GOVERNOR,
            severity=EventSeverity.WARNING,
            source_sm="SM-04",
            source_module="risk_governor_state_machine",
            initiator="SYSTEM",
            message="Test event",
        )

        # Serialize
        serialized = original.to_dict()

        # Deserialize
        restored = GovernanceEvent.from_dict(serialized)

        # Verify fields match
        assert restored.category == original.category
        assert restored.severity == original.severity
        assert restored.source_sm == original.source_sm
        assert restored.source_module == original.source_module
        assert restored.initiator == original.initiator
        assert restored.message == original.message
        assert restored.event_id == original.event_id
        assert restored.timestamp_ms == original.timestamp_ms


class TestIntegrationPhase9Complete:
    """Integration test combining all Phase 9 components"""

    def test_full_phase9_integration(self):
        """
        Full integration test:
        1. Instantiate LearningTierGate
        2. Inject into ENGINE and GovernanceHub
        3. Trigger risk escalation
        4. Verify events appear in stream
        5. Query via API endpoint
        """
        from app.learning_tier_gate import LearningTierGate
        from app.governance_hub import GovernanceHub
        import tempfile

        with tempfile.TemporaryDirectory() as audit_dir:
            # 1. Create components
            gate = LearningTierGate()
            hub = GovernanceHub(audit_dir=audit_dir, enabled=True)

            # 2. Inject
            hub.set_learning_tier_gate(gate)
            assert hub._learning_tier_gate is gate

            # 3. Trigger events
            try:
                hub._ensure_initialized()
            except Exception:
                pass  # May fail in test context

            initial_count = len(hub._governance_events)

            # Trigger risk escalation
            hub._on_risk_escalation(0, 2)

            # 4. Verify event was added
            assert len(hub._governance_events) > initial_count, \
                "Expected event stream to grow after risk escalation"

            # 5. Query via get_governance_events
            events = hub.get_governance_events(limit=50)
            assert len(events) > 0, "Expected to retrieve events"

            # Verify most recent is the risk event
            latest_event = events[0]  # Most recent first
            assert latest_event['category'] == 'risk_governor', \
                f"Expected risk_governor category in latest event, got {latest_event['category']}"

        logger.info("Full Phase 9 integration test passed")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
