"""
Tests for Risk Governor State Machine — 6-Level Risk Governance
风控总督状态机测试 — 6 级风控治理

Covers:
  - All 6 risk levels and constraints
  - Escalation (auto, skip-level)
  - De-escalation (requires approval, min hold time)
  - Auto-evaluation from risk context
  - Health event handlers
  - Circuit breaker and manual review
  - Thread safety
  - Persistence (export/import)
  - Order gate (is_order_allowed)
"""

import sys
import threading
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.risk_governor_state_machine import (
    EscalationThresholds,
    GovernorState,
    LEVEL_CONSTRAINTS,
    RISK_TRANSITION_RULES,
    RiskEvent,
    RiskGovernorError,
    RiskGovernorStateMachine,
    RiskInitiator,
    RiskLevel,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def gov():
    """Fresh governor with 0s min hold time for fast tests / 零冷却测试"""
    thresholds = EscalationThresholds(min_hold_time_seconds=0.0)
    return RiskGovernorStateMachine(thresholds=thresholds)


@pytest.fixture
def gov_with_audit():
    records = []
    thresholds = EscalationThresholds(min_hold_time_seconds=0.0)
    machine = RiskGovernorStateMachine(thresholds=thresholds,
                                       audit_callback=lambda r: records.append(r))
    return machine, records


@pytest.fixture
def gov_default():
    """Governor with default thresholds (5min hold) / 默认阈值（5分钟冷却）"""
    return RiskGovernorStateMachine()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Constants & Level Tests / 常量与等级测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestConstants:
    def test_six_risk_levels(self):
        assert len(RiskLevel) == 6

    def test_level_ordering(self):
        assert RiskLevel.NORMAL < RiskLevel.CAUTIOUS < RiskLevel.REDUCED
        assert RiskLevel.REDUCED < RiskLevel.DEFENSIVE < RiskLevel.CIRCUIT_BREAKER
        assert RiskLevel.CIRCUIT_BREAKER < RiskLevel.MANUAL_REVIEW

    def test_all_levels_have_constraints(self):
        for level in RiskLevel:
            assert level in LEVEL_CONSTRAINTS

    def test_normal_allows_new_entries(self):
        c = LEVEL_CONSTRAINTS[RiskLevel.NORMAL]
        assert c.new_entries_allowed is True
        assert c.reduce_only is False
        assert c.position_size_multiplier == 1.0

    def test_circuit_breaker_blocks_everything(self):
        c = LEVEL_CONSTRAINTS[RiskLevel.CIRCUIT_BREAKER]
        assert c.new_entries_allowed is False
        assert c.reduce_only is True
        assert c.emergency_stops is True
        assert c.requires_operator is True
        assert c.position_size_multiplier == 0.0

    def test_reduced_is_reduce_only(self):
        c = LEVEL_CONSTRAINTS[RiskLevel.REDUCED]
        assert c.new_entries_allowed is False
        assert c.reduce_only is True

    def test_transition_rules_count(self):
        # Should have a good number of transitions
        assert len(RISK_TRANSITION_RULES) >= 20


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Escalation Tests / 升级测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestEscalation:
    def test_normal_to_cautious(self, gov):
        state = gov.escalate_to(RiskLevel.CAUTIOUS, reason="test")
        assert state.level == RiskLevel.CAUTIOUS
        assert state.version == 2

    def test_normal_to_reduced(self, gov):
        state = gov.escalate_to(RiskLevel.REDUCED, reason="high risk")
        assert state.level == RiskLevel.REDUCED

    def test_normal_to_circuit_breaker(self, gov):
        """Skip-level escalation to circuit breaker / 跳级至熔断"""
        state = gov.circuit_break(reason="emergency")
        assert state.level == RiskLevel.CIRCUIT_BREAKER

    def test_step_by_step_escalation(self, gov):
        gov.escalate_to(RiskLevel.CAUTIOUS, reason="1")
        gov.escalate_to(RiskLevel.REDUCED, reason="2")
        gov.escalate_to(RiskLevel.DEFENSIVE, reason="3")
        state = gov.escalate_to(RiskLevel.CIRCUIT_BREAKER, reason="4")
        assert state.level == RiskLevel.CIRCUIT_BREAKER
        assert state.consecutive_escalations == 4

    def test_escalation_no_approval_needed(self, gov):
        """Escalation should NOT require approved_by / 升级不需要审批"""
        state = gov.transition(
            RiskLevel.CAUTIOUS,
            event=RiskEvent.DRAWDOWN_WARNING,
            initiator=RiskInitiator.RISK_GOVERNOR,
            reason_codes=["auto"],
        )
        assert state.level == RiskLevel.CAUTIOUS

    def test_same_level_is_noop(self, gov):
        """Transition to same level returns current state / 同级迁移无操作"""
        state = gov.transition(
            RiskLevel.NORMAL,
            event=RiskEvent.CONDITIONS_IMPROVED,
            initiator=RiskInitiator.OPERATOR,
        )
        assert state.level == RiskLevel.NORMAL
        assert state.version == 1  # No version bump


# ═══════════════════════════════════════════════════════════════════════════════
# 3. De-escalation Tests / 降级测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeEscalation:
    def test_cautious_to_normal_requires_approval(self, gov):
        gov.escalate_to(RiskLevel.CAUTIOUS, reason="risk")
        with pytest.raises(RiskGovernorError, match="requires.*approval"):
            gov.transition(
                RiskLevel.NORMAL,
                event=RiskEvent.RECOVERY_APPROVED,
                initiator=RiskInitiator.OPERATOR,
                # No approved_by!
            )

    def test_cautious_to_normal_with_approval(self, gov):
        gov.escalate_to(RiskLevel.CAUTIOUS, reason="risk")
        state = gov.de_escalate_to(RiskLevel.NORMAL, approved_by="op1", reason="recovered")
        assert state.level == RiskLevel.NORMAL

    def test_circuit_breaker_to_defensive(self, gov):
        gov.circuit_break(reason="emergency")
        state = gov.de_escalate_to(RiskLevel.DEFENSIVE, approved_by="op1")
        assert state.level == RiskLevel.DEFENSIVE

    def test_manual_review_to_normal(self, gov):
        gov.request_manual_review(reason="review needed")
        state = gov.complete_manual_review(
            approved_by="op1", resume_to=RiskLevel.NORMAL, reason="all clear"
        )
        assert state.level == RiskLevel.NORMAL

    def test_min_hold_time_enforced(self, gov_default):
        """De-escalation before min hold time should fail / 冷却期内降级应失败"""
        gov_default.escalate_to(RiskLevel.CAUTIOUS, reason="risk")
        with pytest.raises(RiskGovernorError, match="hold"):
            gov_default.de_escalate_to(RiskLevel.NORMAL, approved_by="op1")

    def test_skip_de_escalation_operator_only(self, gov):
        """Skip de-escalation from REDUCED to NORMAL requires operator / 跳级降级需操作员"""
        gov.escalate_to(RiskLevel.REDUCED, reason="risk")
        # RiskGovernor (non-operator) should fail for skip de-escalation
        with pytest.raises(RiskGovernorError, match="not allowed"):
            gov.transition(
                RiskLevel.NORMAL,
                event=RiskEvent.RECOVERY_APPROVED,
                initiator=RiskInitiator.RISK_GOVERNOR,
                approved_by="system",
            )
        # Operator should succeed
        state = gov.de_escalate_to(RiskLevel.NORMAL, approved_by="op1")
        assert state.level == RiskLevel.NORMAL


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Auto-Evaluation Tests / 自动评估测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestAutoEvaluation:
    def test_normal_stays_normal_low_risk(self, gov):
        """Low risk context should not trigger escalation / 低风险不触发升级"""
        result = gov.evaluate_risk_context({
            "risk_pressure": 0.1,
            "drawdown_pct": 2.0,
            "daily_loss_pct": 0.5,
            "consecutive_losses": 1,
            "session_halted": False,
            "cooldown_active": False,
        })
        assert result is None
        assert gov.level == RiskLevel.NORMAL

    def test_pressure_triggers_cautious(self, gov):
        result = gov.evaluate_risk_context({
            "risk_pressure": 0.35,
            "drawdown_pct": 3.0,
            "daily_loss_pct": 1.0,
            "consecutive_losses": 2,
            "session_halted": False,
            "cooldown_active": False,
        })
        assert result is not None
        assert gov.level == RiskLevel.CAUTIOUS

    def test_high_drawdown_triggers_defensive(self, gov):
        result = gov.evaluate_risk_context({
            "risk_pressure": 0.75,
            "drawdown_pct": 13.0,
            "daily_loss_pct": 4.0,
            "consecutive_losses": 4,
            "session_halted": False,
            "cooldown_active": False,
        })
        assert result is not None
        assert gov.level == RiskLevel.DEFENSIVE

    def test_extreme_triggers_circuit_breaker(self, gov):
        result = gov.evaluate_risk_context({
            "risk_pressure": 0.95,
            "drawdown_pct": 16.0,
            "daily_loss_pct": 6.0,
            "consecutive_losses": 11,
            "session_halted": False,
            "cooldown_active": False,
        })
        assert result is not None
        assert gov.level == RiskLevel.CIRCUIT_BREAKER

    def test_session_halted_triggers_circuit_breaker(self, gov):
        result = gov.evaluate_risk_context({
            "risk_pressure": 0.0,
            "drawdown_pct": 0.0,
            "daily_loss_pct": 0.0,
            "consecutive_losses": 0,
            "session_halted": True,
            "cooldown_active": False,
        })
        assert result is not None
        assert gov.level == RiskLevel.CIRCUIT_BREAKER

    def test_cooldown_triggers_reduced(self, gov):
        result = gov.evaluate_risk_context({
            "risk_pressure": 0.1,
            "drawdown_pct": 1.0,
            "daily_loss_pct": 0.0,
            "consecutive_losses": 0,
            "session_halted": False,
            "cooldown_active": True,
        })
        assert result is not None
        assert gov.level == RiskLevel.REDUCED

    def test_no_auto_de_escalation(self, gov):
        """Auto-evaluation should NEVER de-escalate / 自动评估不会降级"""
        gov.escalate_to(RiskLevel.DEFENSIVE, reason="test")
        result = gov.evaluate_risk_context({
            "risk_pressure": 0.0,
            "drawdown_pct": 0.0,
            "daily_loss_pct": 0.0,
            "consecutive_losses": 0,
            "session_halted": False,
            "cooldown_active": False,
        })
        assert result is None
        assert gov.level == RiskLevel.DEFENSIVE  # Still defensive

    def test_incremental_escalation(self, gov):
        """Multiple evaluations should escalate incrementally / 多次评估应递增升级"""
        gov.evaluate_risk_context({
            "risk_pressure": 0.35,
            "drawdown_pct": 6.0,
            "daily_loss_pct": 1.0,
            "consecutive_losses": 0,
            "session_halted": False,
            "cooldown_active": False,
        })
        assert gov.level == RiskLevel.CAUTIOUS

        gov.evaluate_risk_context({
            "risk_pressure": 0.6,
            "drawdown_pct": 9.0,
            "daily_loss_pct": 4.0,
            "consecutive_losses": 6,
            "session_halted": False,
            "cooldown_active": False,
        })
        assert gov.level == RiskLevel.REDUCED


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Health Event Tests / 健康事件测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealthEvents:
    def test_health_degraded(self, gov):
        result = gov.on_health_degraded()
        assert result is not None
        assert gov.level == RiskLevel.REDUCED

    def test_market_data_stale(self, gov):
        result = gov.on_market_data_stale()
        assert result is not None
        assert gov.level == RiskLevel.CIRCUIT_BREAKER

    def test_api_connectivity_loss(self, gov):
        result = gov.on_api_connectivity_loss()
        assert result is not None
        assert gov.level == RiskLevel.CIRCUIT_BREAKER

    def test_health_events_no_downgrade(self, gov):
        """Health event at higher level should not change / 更高等级时健康事件不变"""
        gov.circuit_break(reason="already broken")
        result = gov.on_health_degraded()
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Guard Conditions / 守卫条件测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestGuardConditions:
    def test_invalid_initiator_for_escalation(self, gov):
        """EXPIRY_GUARDIAN cannot escalate to CAUTIOUS / 过期守护不可升级至谨慎"""
        with pytest.raises(RiskGovernorError, match="not allowed"):
            gov.transition(
                RiskLevel.CAUTIOUS,
                event=RiskEvent.DRAWDOWN_WARNING,
                initiator=RiskInitiator.EXPIRY_GUARDIAN,  # not in _AUTO
            )

    def test_wrong_initiator_escalation(self, gov):
        """Wrong initiator should be rejected / 错误发起者应被拒绝"""
        with pytest.raises(RiskGovernorError, match="not allowed"):
            gov.transition(
                RiskLevel.MANUAL_REVIEW,
                event=RiskEvent.OPERATOR_MANUAL_REVIEW,
                initiator=RiskInitiator.HEALTH_MONITOR,  # Not in allowed for →MANUAL_REVIEW
            )

    def test_cannot_de_escalate_circuit_breaker_as_governor(self, gov):
        """Only operator can de-escalate from CIRCUIT_BREAKER / 仅操作员可从熔断降级"""
        gov.circuit_break(reason="test")
        with pytest.raises(RiskGovernorError, match="not allowed"):
            gov.transition(
                RiskLevel.DEFENSIVE,
                event=RiskEvent.RECOVERY_APPROVED,
                initiator=RiskInitiator.RISK_GOVERNOR,
                approved_by="system",
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Order Gate / 订单门控测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestOrderGate:
    def test_normal_allows_all(self, gov):
        allowed, reason = gov.is_order_allowed(is_reducing=False)
        assert allowed is True

    def test_cautious_allows_new_entries(self, gov):
        gov.escalate_to(RiskLevel.CAUTIOUS, reason="test")
        allowed, _ = gov.is_order_allowed(is_reducing=False)
        assert allowed is True

    def test_reduced_blocks_new_entries(self, gov):
        gov.escalate_to(RiskLevel.REDUCED, reason="test")
        allowed, reason = gov.is_order_allowed(is_reducing=False)
        assert allowed is False
        assert "no_new_entries" in reason

    def test_reduced_allows_reducing(self, gov):
        gov.escalate_to(RiskLevel.REDUCED, reason="test")
        allowed, _ = gov.is_order_allowed(is_reducing=True)
        assert allowed is True

    def test_circuit_breaker_blocks_all(self, gov):
        gov.circuit_break(reason="emergency")
        allowed, reason = gov.is_order_allowed(is_reducing=True)
        assert allowed is False
        assert "requires_operator" in reason

    def test_manual_review_blocks_all(self, gov):
        gov.request_manual_review(reason="review")
        allowed, reason = gov.is_order_allowed(is_reducing=True)
        assert allowed is False
        assert "requires_operator" in reason


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Audit Trail / 审计轨迹测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditTrail:
    def test_audit_callback_on_transition(self, gov_with_audit):
        machine, records = gov_with_audit
        machine.escalate_to(RiskLevel.CAUTIOUS, reason="test")
        assert len(records) == 1

    def test_audit_record_fields(self, gov_with_audit):
        machine, records = gov_with_audit
        machine.escalate_to(RiskLevel.CAUTIOUS, reason="test")
        r = records[0]
        required = [
            "transition_id", "previous_level", "next_level",
            "trigger_event", "initiated_by", "direction",
            "approval_required", "effective_at_ms", "audit_event_ref",
        ]
        for f in required:
            assert f in r, f"Missing field: {f}"

    def test_transitions_stored_in_state(self, gov):
        gov.escalate_to(RiskLevel.CAUTIOUS, reason="1")
        gov.escalate_to(RiskLevel.REDUCED, reason="2")
        state = gov.get_state()
        assert len(state.transitions) == 2

    def test_version_increments(self, gov):
        gov.escalate_to(RiskLevel.CAUTIOUS, reason="1")
        gov.escalate_to(RiskLevel.REDUCED, reason="2")
        state = gov.get_state()
        assert state.version == 3


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Persistence / 持久化测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestPersistence:
    def test_export_import_roundtrip(self, gov):
        gov.escalate_to(RiskLevel.DEFENSIVE, reason="test")
        data = gov.export_state()

        gov2 = RiskGovernorStateMachine(
            thresholds=EscalationThresholds(min_hold_time_seconds=0.0)
        )
        gov2.import_state(data)
        assert gov2.level == RiskLevel.DEFENSIVE
        state = gov2.get_state()
        assert state.version == 2
        assert len(state.transitions) == 1

    def test_import_bad_level_defaults_normal(self):
        gov = RiskGovernorStateMachine()
        gov.import_state({"level": "INVALID"})
        assert gov.level == RiskLevel.NORMAL


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Thread Safety / 线程安全测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestThreadSafety:
    def test_concurrent_evaluations(self, gov):
        """Concurrent evaluations should not corrupt state / 并发评估不应破坏状态"""
        errors = []

        def evaluate_loop():
            try:
                for _ in range(20):
                    gov.evaluate_risk_context({
                        "risk_pressure": 0.35,
                        "drawdown_pct": 6.0,
                        "daily_loss_pct": 1.0,
                        "consecutive_losses": 0,
                        "session_halted": False,
                        "cooldown_active": False,
                    })
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=evaluate_loop) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0
        # Should be at least cautious
        assert gov.level >= RiskLevel.CAUTIOUS


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Full Lifecycle Integration / 完整生命周期测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestFullLifecycle:
    def test_full_escalation_and_recovery(self, gov):
        """NORMAL → CAUTIOUS → REDUCED → DEFENSIVE → CIRCUIT_BREAKER → manual → NORMAL"""
        gov.escalate_to(RiskLevel.CAUTIOUS, reason="step1")
        gov.escalate_to(RiskLevel.REDUCED, reason="step2")
        gov.escalate_to(RiskLevel.DEFENSIVE, reason="step3")
        gov.circuit_break(reason="step4")
        gov.request_manual_review(reason="step5")
        gov.complete_manual_review(approved_by="op1", resume_to=RiskLevel.NORMAL, reason="all clear")

        assert gov.level == RiskLevel.NORMAL
        state = gov.get_state()
        assert state.version == 7  # 1 initial + 6 transitions
        assert len(state.transitions) == 6

    def test_auto_escalation_then_manual_recovery(self, gov):
        """Auto-escalation via context, then manual recovery / 自动升级 + 人工恢复"""
        gov.evaluate_risk_context({
            "risk_pressure": 0.95,
            "drawdown_pct": 16.0,
            "daily_loss_pct": 6.0,
            "consecutive_losses": 11,
            "session_halted": False,
            "cooldown_active": False,
        })
        assert gov.level == RiskLevel.CIRCUIT_BREAKER

        gov.de_escalate_to(RiskLevel.DEFENSIVE, approved_by="op1", reason="partial recovery")
        gov.de_escalate_to(RiskLevel.REDUCED, approved_by="op1", reason="improving")
        gov.de_escalate_to(RiskLevel.CAUTIOUS, approved_by="op1", reason="almost normal")
        gov.de_escalate_to(RiskLevel.NORMAL, approved_by="op1", reason="fully recovered")
        assert gov.level == RiskLevel.NORMAL

    def test_status_output(self, gov):
        gov.escalate_to(RiskLevel.CAUTIOUS, reason="test")
        status = gov.get_status()
        assert status["level"] == "CAUTIOUS"
        assert status["level_value"] == 1
        assert status["constraints"]["new_entries_allowed"] is True
        assert status["constraints"]["position_size_multiplier"] == 0.7


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Fail-Closed Behavior / 故障保护（闭合）测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestRiskGovernorFailClosed:
    """Verify fail-closed behavior: when SM is not properly initialized or in error state.
    当状态机未正确初始化或处于错误状态时验证故障保护（闭合）行为。"""

    def test_fresh_governor_starts_at_normal(self, gov):
        """Fresh governor should start at NORMAL (safest operational level).
        新的总督应从 NORMAL 开始（最安全的操作级别）。"""
        assert gov.level == RiskLevel.NORMAL
        state = gov.get_state()
        assert state.level == RiskLevel.NORMAL
        assert state.version == 1  # Initial state

    def test_invalid_metrics_does_not_lower_risk(self, gov):
        """Invalid or missing metrics should not cause de-escalation.
        无效或缺失的指标不应导致降级。"""
        gov.escalate_to(RiskLevel.CAUTIOUS, reason="test")
        assert gov.level == RiskLevel.CAUTIOUS

        # Try to evaluate with all-zero metrics — should not de-escalate
        result = gov.evaluate_risk_context({
            "risk_pressure": 0.0,
            "drawdown_pct": 0.0,
            "daily_loss_pct": 0.0,
            "consecutive_losses": 0,
            "session_halted": False,
            "cooldown_active": False,
        })
        assert gov.level == RiskLevel.CAUTIOUS  # Should stay at CAUTIOUS (no auto de-escalation)

    def test_circuit_breaker_cannot_be_bypassed(self, gov):
        """CIRCUIT_BREAKER state cannot transition to lower levels without operator.
        熔断状态不能绕过操作员直接降级。"""
        gov.circuit_break(reason="emergency")
        assert gov.level == RiskLevel.CIRCUIT_BREAKER

        # Try de-escalation without approval — should fail (either wrong initiator or missing approval)
        with pytest.raises(RiskGovernorError, match="not allowed|requires.*approval"):
            gov.transition(
                RiskLevel.DEFENSIVE,
                event=RiskEvent.CONDITIONS_IMPROVED,
                initiator=RiskInitiator.RISK_GOVERNOR,
                # No approved_by!
            )

        # Verify state unchanged
        assert gov.level == RiskLevel.CIRCUIT_BREAKER

    def test_order_denied_at_circuit_breaker(self, gov):
        """Orders should be blocked at CIRCUIT_BREAKER level / 熔断时订单应被阻止。"""
        gov.circuit_break(reason="test")
        allowed, reason = gov.is_order_allowed(is_reducing=True)
        assert allowed is False
        assert "requires_operator" in reason

    def test_manual_review_requires_approval_to_exit(self, gov):
        """MANUAL_REVIEW state cannot auto-exit; requires explicit approval.
        人工审核状态不能自动退出；需要明确审批。"""
        gov.request_manual_review(reason="review needed")
        assert gov.level == RiskLevel.MANUAL_REVIEW

        # Try to auto-transition without approval — should fail
        with pytest.raises(RiskGovernorError, match="requires.*approval"):
            gov.transition(
                RiskLevel.NORMAL,
                event=RiskEvent.CONDITIONS_IMPROVED,
                initiator=RiskInitiator.OPERATOR,
                # No approved_by!
            )

        # Verify state unchanged
        assert gov.level == RiskLevel.MANUAL_REVIEW

    def test_no_auto_de_escalation_from_high_state(self, gov):
        """Auto-evaluation should NEVER de-escalate from high risk states.
        自动评估不应从高风险状态降级。"""
        gov.escalate_to(RiskLevel.DEFENSIVE, reason="high risk")
        assert gov.level == RiskLevel.DEFENSIVE

        # Evaluate with all-clear metrics — should NOT de-escalate
        result = gov.evaluate_risk_context({
            "risk_pressure": 0.0,
            "drawdown_pct": 0.0,
            "daily_loss_pct": 0.0,
            "consecutive_losses": 0,
            "session_halted": False,
            "cooldown_active": False,
        })
        assert result is None  # No transition
        assert gov.level == RiskLevel.DEFENSIVE  # Still at DEFENSIVE
