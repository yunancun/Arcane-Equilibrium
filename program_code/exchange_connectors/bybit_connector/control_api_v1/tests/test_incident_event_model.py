"""
Tests for Incident Event Model + Formal Event Schema — DOC-07 / GAP-H5 + GAP-M1
事故事件模型 + 正式事件架构测试

Covers:
  - Event object creation and serialization
  - Severity hierarchy and ordering
  - IncidentRecord creation and properties
  - Severity→Action mapping (DOC-07 §3-§5)
  - IncidentPolicy event processing
  - State machine integration callbacks (auth + risk)
  - Incident recovery flow
  - Reconciliation report → Event conversion
  - Audit callback integration
  - Queries (open incidents, by severity, stats)
  - Thread safety
  - Edge cases
"""

import sys
import threading
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.incident_event_model import (
    Event,
    EventSeverity,
    IncidentActionType,
    IncidentPolicy,
    IncidentRecord,
    IntegrityStatus,
    RootCauseFamily,
    SEVERITY_ACTION_MAP,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def policy():
    return IncidentPolicy()


def _make_event(
    severity=EventSeverity.NOTICE,
    event_type="test_event",
    source="test_module",
    reason_code="unknown",
) -> Event:
    return Event(
        event_type=event_type,
        severity=severity,
        source=source,
        triggered_by="System",
        reason_code=reason_code,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Event Object / 事件对象测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestEventObject:
    def test_event_has_id(self):
        e = Event(event_type="test")
        assert e.event_id.startswith("evt:")
        assert len(e.event_id) > 10

    def test_event_has_timestamp(self):
        e = Event(event_type="test")
        assert e.triggered_at_ms > 0

    def test_event_to_dict(self):
        e = Event(event_type="test", severity=EventSeverity.INCIDENT, source="risk")
        d = e.to_dict()
        assert d["event_type"] == "test"
        assert d["severity"] == "INCIDENT"
        assert d["severity_level"] == 3
        assert d["source"] == "risk"

    def test_event_factory(self):
        e = IncidentPolicy.create_event(
            event_type="reconciliation_mismatch",
            severity=EventSeverity.INCIDENT,
            source="reconciliation_engine",
            triggered_by="ReconciliationEngine",
            affected_objects=["BTCUSDT"],
            reason_code="state_conflict",
        )
        assert e.event_type == "reconciliation_mismatch"
        assert e.severity == EventSeverity.INCIDENT
        assert "BTCUSDT" in e.affected_objects


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Severity Hierarchy / 严重度层级测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestSeverityHierarchy:
    def test_ordering(self):
        assert EventSeverity.NOTICE < EventSeverity.ANOMALY
        assert EventSeverity.ANOMALY < EventSeverity.NEAR_MISS
        assert EventSeverity.NEAR_MISS < EventSeverity.INCIDENT
        assert EventSeverity.INCIDENT < EventSeverity.CRITICAL_INCIDENT

    def test_five_levels(self):
        assert len(EventSeverity) == 5

    def test_int_values(self):
        assert int(EventSeverity.NOTICE) == 0
        assert int(EventSeverity.CRITICAL_INCIDENT) == 4


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Incident Record / 事故记录测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestIncidentRecord:
    def test_record_has_id(self):
        r = IncidentRecord(severity=EventSeverity.INCIDENT)
        assert r.incident_id.startswith("inc:")

    def test_record_not_resolved_initially(self):
        r = IncidentRecord()
        assert not r.is_resolved

    def test_record_is_critical(self):
        r = IncidentRecord(severity=EventSeverity.CRITICAL_INCIDENT)
        assert r.is_critical

    def test_record_not_critical(self):
        r = IncidentRecord(severity=EventSeverity.INCIDENT)
        assert not r.is_critical

    def test_record_to_dict(self):
        r = IncidentRecord(
            severity=EventSeverity.INCIDENT,
            detected_by="reconciliation",
            root_cause_family=RootCauseFamily.STATE_CONFLICT,
        )
        d = r.to_dict()
        assert d["severity"] == "INCIDENT"
        assert d["root_cause_family"] == "state_conflict"
        assert d["is_resolved"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Severity → Action Mapping / 严重度→动作映射测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestSeverityActionMapping:
    def test_notice_only_records(self):
        actions = SEVERITY_ACTION_MAP[EventSeverity.NOTICE]
        assert IncidentActionType.RECORD_ONLY in actions
        assert len(actions) == 1

    def test_anomaly_includes_monitoring(self):
        actions = SEVERITY_ACTION_MAP[EventSeverity.ANOMALY]
        assert IncidentActionType.INCREASE_MONITORING in actions
        assert IncidentActionType.RISK_ESCALATE_CAUTIOUS in actions

    def test_near_miss_includes_restrict(self):
        actions = SEVERITY_ACTION_MAP[EventSeverity.NEAR_MISS]
        assert IncidentActionType.AUTH_RESTRICT in actions
        assert IncidentActionType.RISK_ESCALATE_REDUCED in actions

    def test_incident_includes_freeze(self):
        actions = SEVERITY_ACTION_MAP[EventSeverity.INCIDENT]
        assert IncidentActionType.AUTH_FREEZE in actions
        assert IncidentActionType.RISK_ESCALATE_DEFENSIVE in actions
        assert IncidentActionType.MANUAL_REVIEW in actions

    def test_critical_includes_circuit_breaker(self):
        actions = SEVERITY_ACTION_MAP[EventSeverity.CRITICAL_INCIDENT]
        assert IncidentActionType.RISK_CIRCUIT_BREAKER in actions
        assert IncidentActionType.TRADING_FREEZE in actions
        assert IncidentActionType.AUTH_FREEZE in actions

    def test_all_severities_have_mapping(self):
        for sev in EventSeverity:
            assert sev in SEVERITY_ACTION_MAP


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Incident Policy Processing / 事故策略处理测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestIncidentPolicyProcessing:
    def test_notice_no_incident_created(self, policy):
        event = _make_event(severity=EventSeverity.NOTICE)
        result = policy.process_event(event)
        assert result["incident_id"] is None
        assert "RECORD_ONLY" in result["actions_taken"]

    def test_anomaly_no_incident_created(self, policy):
        event = _make_event(severity=EventSeverity.ANOMALY)
        result = policy.process_event(event)
        assert result["incident_id"] is None

    def test_near_miss_creates_incident(self, policy):
        event = _make_event(severity=EventSeverity.NEAR_MISS)
        result = policy.process_event(event)
        assert result["incident_id"] is not None
        assert result["incident_id"].startswith("inc:")

    def test_incident_creates_record(self, policy):
        event = _make_event(severity=EventSeverity.INCIDENT)
        result = policy.process_event(event)
        assert result["incident_id"] is not None
        assert result["severity"] == "INCIDENT"

    def test_critical_creates_record(self, policy):
        event = _make_event(severity=EventSeverity.CRITICAL_INCIDENT)
        result = policy.process_event(event)
        assert result["incident_id"] is not None
        assert "RISK_CIRCUIT_BREAKER" in result["actions_taken"]
        assert "AUTH_FREEZE" in result["actions_taken"]


# ═══════════════════════════════════════════════════════════════════════════════
# 6. State Machine Integration / 状态机集成测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestStateMachineIntegration:
    def test_auth_callback_on_incident(self):
        auth_actions = []
        policy = IncidentPolicy(
            on_auth_action=lambda action, ctx: auth_actions.append((action, ctx)),
        )
        event = _make_event(severity=EventSeverity.INCIDENT)
        policy.process_event(event)
        assert len(auth_actions) > 0
        assert auth_actions[0][0] == "AUTH_FREEZE"

    def test_risk_callback_on_incident(self):
        risk_actions = []
        policy = IncidentPolicy(
            on_risk_action=lambda action, ctx: risk_actions.append((action, ctx)),
        )
        event = _make_event(severity=EventSeverity.INCIDENT)
        policy.process_event(event)
        assert len(risk_actions) > 0
        assert risk_actions[0][0] == "RISK_ESCALATE_DEFENSIVE"

    def test_critical_triggers_circuit_breaker(self):
        risk_actions = []
        auth_actions = []
        policy = IncidentPolicy(
            on_auth_action=lambda action, ctx: auth_actions.append(action),
            on_risk_action=lambda action, ctx: risk_actions.append(action),
        )
        event = _make_event(severity=EventSeverity.CRITICAL_INCIDENT)
        policy.process_event(event)
        assert "RISK_CIRCUIT_BREAKER" in risk_actions
        assert "AUTH_FREEZE" in auth_actions

    def test_operator_alert_on_near_miss(self):
        alerts = []
        policy = IncidentPolicy(
            on_operator_alert=lambda ctx: alerts.append(ctx),
        )
        event = _make_event(severity=EventSeverity.NEAR_MISS)
        policy.process_event(event)
        assert len(alerts) == 1
        assert "event_id" in alerts[0]

    def test_anomaly_triggers_risk_cautious(self):
        risk_actions = []
        policy = IncidentPolicy(
            on_risk_action=lambda action, ctx: risk_actions.append(action),
        )
        event = _make_event(severity=EventSeverity.ANOMALY)
        policy.process_event(event)
        assert "RISK_ESCALATE_CAUTIOUS" in risk_actions


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Incident Recovery / 事故恢复测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestIncidentRecovery:
    def test_approve_recovery(self, policy):
        event = _make_event(severity=EventSeverity.INCIDENT)
        result = policy.process_event(event)
        inc_id = result["incident_id"]

        ok = policy.approve_recovery(inc_id, approved_by="Operator", notes="All clear")
        assert ok

        inc = policy.get_incident(inc_id)
        assert inc["is_resolved"]
        assert inc["recovery_approved_by"] == "Operator"

    def test_cannot_recover_twice(self, policy):
        event = _make_event(severity=EventSeverity.INCIDENT)
        result = policy.process_event(event)
        inc_id = result["incident_id"]

        assert policy.approve_recovery(inc_id, "Operator")
        assert not policy.approve_recovery(inc_id, "Operator")  # Already resolved

    def test_recovery_nonexistent(self, policy):
        assert not policy.approve_recovery("inc:fake", "Operator")

    def test_recovery_audit(self):
        audits = []
        policy = IncidentPolicy(audit_callback=lambda r: audits.append(r))
        event = _make_event(severity=EventSeverity.INCIDENT)
        result = policy.process_event(event)
        policy.approve_recovery(result["incident_id"], "Operator")

        recovery_audits = [a for a in audits if a.get("event_type") == "incident_recovery_approved"]
        assert len(recovery_audits) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Reconciliation → Event Conversion / 对账→事件转换测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestReconciliationConversion:
    def test_no_discrepancies_is_notice(self):
        report = {"discrepancy_count": 0, "critical_count": 0, "report_id": "r1"}
        event = IncidentPolicy.from_reconciliation_report(report)
        assert event.severity == EventSeverity.NOTICE
        assert event.event_type == "reconciliation_pass"

    def test_minor_discrepancies_is_anomaly(self):
        report = {"discrepancy_count": 1, "critical_count": 0, "report_id": "r2"}
        event = IncidentPolicy.from_reconciliation_report(report)
        assert event.severity == EventSeverity.ANOMALY

    def test_multiple_discrepancies_is_near_miss(self):
        report = {"discrepancy_count": 3, "critical_count": 0, "report_id": "r3"}
        event = IncidentPolicy.from_reconciliation_report(report)
        assert event.severity == EventSeverity.NEAR_MISS

    def test_critical_discrepancy_is_incident(self):
        report = {"discrepancy_count": 2, "critical_count": 1, "report_id": "r4"}
        event = IncidentPolicy.from_reconciliation_report(report)
        assert event.severity == EventSeverity.INCIDENT

    def test_many_criticals_is_critical_incident(self):
        report = {"discrepancy_count": 5, "critical_count": 3, "report_id": "r5"}
        event = IncidentPolicy.from_reconciliation_report(report)
        assert event.severity == EventSeverity.CRITICAL_INCIDENT

    def test_conversion_has_metadata(self):
        report = {"discrepancy_count": 1, "critical_count": 0, "report_id": "r6", "overall_result": "MISMATCH_MINOR"}
        event = IncidentPolicy.from_reconciliation_report(report)
        assert event.metadata["report_id"] == "r6"
        assert event.source == "reconciliation_engine"


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Audit Callback / 审计回调测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditCallback:
    def test_audit_on_process(self):
        audits = []
        policy = IncidentPolicy(audit_callback=lambda r: audits.append(r))
        policy.process_event(_make_event())
        assert len(audits) == 1
        assert audits[0]["event_type"] == "incident_policy_processed"

    def test_audit_contains_event_id(self):
        audits = []
        policy = IncidentPolicy(audit_callback=lambda r: audits.append(r))
        event = _make_event()
        policy.process_event(event)
        assert audits[0]["event_id"] == event.event_id


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Queries / 查询测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestQueries:
    def test_get_open_incidents(self, policy):
        policy.process_event(_make_event(severity=EventSeverity.INCIDENT))
        policy.process_event(_make_event(severity=EventSeverity.INCIDENT))
        open_incs = policy.get_open_incidents()
        assert len(open_incs) == 2

    def test_get_open_incidents_excludes_resolved(self, policy):
        result = policy.process_event(_make_event(severity=EventSeverity.INCIDENT))
        policy.approve_recovery(result["incident_id"], "Operator")
        policy.process_event(_make_event(severity=EventSeverity.INCIDENT))
        open_incs = policy.get_open_incidents()
        assert len(open_incs) == 1

    def test_get_events_by_severity(self, policy):
        policy.process_event(_make_event(severity=EventSeverity.NOTICE))
        policy.process_event(_make_event(severity=EventSeverity.INCIDENT))
        policy.process_event(_make_event(severity=EventSeverity.ANOMALY))

        incidents = policy.get_events_by_severity(EventSeverity.INCIDENT)
        assert len(incidents) == 1

    def test_get_stats(self, policy):
        policy.process_event(_make_event(severity=EventSeverity.NOTICE))
        policy.process_event(_make_event(severity=EventSeverity.INCIDENT))
        stats = policy.get_stats()
        assert stats["events_processed"] == 2
        assert stats["notices"] == 1
        assert stats["incidents"] == 1

    def test_get_recent_events(self, policy):
        for _ in range(5):
            policy.process_event(_make_event())
        events = policy.get_recent_events(3)
        assert len(events) == 3


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Thread Safety / 线程安全测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestThreadSafety:
    def test_concurrent_processing(self, policy):
        errors = []

        def worker():
            try:
                for sev in EventSeverity:
                    event = _make_event(severity=sev)
                    result = policy.process_event(event)
                    assert "event_id" in result
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0
        assert policy.get_stats()["events_processed"] == 25  # 5 threads * 5 severities


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Edge Cases / 边界情况测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_root_cause_families(self):
        """All root cause families should be valid / 所有根因分类应有效"""
        for family in RootCauseFamily:
            r = IncidentRecord(root_cause_family=family)
            assert r.to_dict()["root_cause_family"] == family.value

    def test_integrity_statuses(self):
        for status in IntegrityStatus:
            r = IncidentRecord(truth_source_integrity=status)
            assert r.to_dict()["truth_source_integrity"] == status.value

    def test_event_with_parent(self):
        parent = Event(event_type="parent")
        child = Event(event_type="child", parent_event_id=parent.event_id)
        assert child.parent_event_id == parent.event_id

    def test_callback_error_does_not_crash(self):
        """Failing callback should not crash processing / 回调失败不应崩溃"""
        def bad_callback(data):
            raise RuntimeError("callback failed")

        policy = IncidentPolicy(on_auth_action=bad_callback)
        event = _make_event(severity=EventSeverity.INCIDENT)
        result = policy.process_event(event)
        # Should still complete with FAILED actions noted
        assert any("FAILED" in a for a in result["actions_taken"])

    def test_get_incident_nonexistent(self, policy):
        assert policy.get_incident("inc:fake") is None
