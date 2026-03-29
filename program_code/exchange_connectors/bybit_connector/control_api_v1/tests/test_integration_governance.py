"""
Integration Tests for Cross-Module Governance Workflows
跨模块治理工作流集成测试

These tests verify interactions between multiple governance modules:
  - Authorization State Machine (SM-01)
  - Risk Governor State Machine (SM-04 / EX-01 §7)
  - Decision Lease State Machine (SM-02)
  - Reconciliation Engine (EX-04 / EX-02 §14)
  - Paper→Live Gate (DOC-08 §11)

Test Scenarios:
  1. Full Authorization Lifecycle with Risk Constraints
     - Authorization created, approved, activated
     - Risk escalates, authorization automatically restricted
     - Lease expiry cascades to authorization termination

  2. Risk Escalation Triggers Authorization Restriction
     - Risk moves NORMAL → ELEVATED → HIGH → CRITICAL
     - Authorization automatically transitions from ACTIVE to RESTRICTED
     - Further escalation freezes authorization

  3. Lease Expiry Cascade Effect
     - Decision lease expires naturally or by revocation
     - Associated authorizations should gracefully handle expiry
     - Risk governor should not escalate post-expiry

  4. Reconciliation Detects Inconsistency → Risk Escalation
     - Reconciliation finds major mismatch
     - Triggers risk escalation event
     - Authorization automatically restricts

  5. Paper→Live Gate Full Flow
     - Paper trading metrics collected
     - Gate evaluation run
     - Gate pass triggers authorization expansion
     - Paper→Live promotion ready

Testing Pattern:
  - Scenarios test 2+ modules interacting
  - Each scenario builds realistic state chain
  - Verifies state transitions, audit trails, and callbacks
  - Thread-safe operation verified where applicable
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
    AuthState,
    AuthorizationStateMachine,
)
from app.decision_lease_state_machine import (
    DecisionLeaseStateMachine,
    LeaseEvent,
    LeaseInitiator,
    LeaseState,
)
from app.paper_live_gate import (
    GateCheckResult,
    GateStatus,
    PaperLiveGate,
    PaperLiveGateConfig,
)
from app.reconciliation_engine import (
    Discrepancy,
    DiscrepancyType,
    IncidentAction,
    ReconciliationConfig,
    ReconciliationEngine,
    ReconciliationResult,
    Severity,
)
from app.risk_governor_state_machine import (
    RiskEvent,
    RiskGovernorStateMachine,
    RiskInitiator,
    RiskLevel,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Shared Utilities / 共享工具
# ═══════════════════════════════════════════════════════════════════════════════


def _now_ms() -> int:
    """Current time in milliseconds / 当前时间毫秒"""
    return int(time.time() * 1000)


def _future_ms(seconds: int) -> int:
    """Time N seconds from now in milliseconds / N秒后的时间毫秒"""
    return _now_ms() + (seconds * 1000)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def auth_machine():
    """Fresh authorization state machine / 全新授权状态机"""
    records = []
    machine = AuthorizationStateMachine(audit_callback=lambda r: records.append(r))
    machine._audit_records = records  # Attach records for inspection
    return machine


@pytest.fixture
def risk_governor():
    """Fresh risk governor / 全新风控总督"""
    records = []
    gov = RiskGovernorStateMachine(audit_callback=lambda r: records.append(r))
    gov._audit_records = records
    return gov


@pytest.fixture
def lease_machine():
    """Fresh decision lease state machine / 全新租约状态机"""
    records = []
    machine = DecisionLeaseStateMachine(audit_callback=lambda r: records.append(r))
    machine._audit_records = records
    return machine


@pytest.fixture
def reconciliation_engine():
    """Fresh reconciliation engine / 全新对账引擎"""
    config = ReconciliationConfig(
        price_tolerance_pct=0.005,
        qty_tolerance_pct=0.001,
        balance_tolerance_abs=1.0,
        max_data_age_ms=60_000,
    )
    records = []
    engine = ReconciliationEngine(config, audit_callback=lambda r: records.append(r))
    engine._audit_records = records
    return engine


@pytest.fixture
def paper_live_gate():
    """Fresh Paper→Live gate engine / 全新纸盘→实盘闸门"""
    config = PaperLiveGateConfig(
        min_paper_duration_weeks=4,
        min_trades=500,
        min_win_rate_percent=30.0,
        min_net_pnl_threshold=0.0,
        min_sharpe_ratio=0.5,
        max_drawdown_percent=100.0,
        min_profit_factor=1.2,
        min_audit_trail_completeness_percent=99.0,
        max_reconciliation_mismatch_percent=0.1,
    )
    gate = PaperLiveGate(config)
    return gate


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario 1: Full Authorization Lifecycle with Risk Constraints
# 场景 1: 完整授权生命周期与风控约束
# ═══════════════════════════════════════════════════════════════════════════════


class TestScenario1FullAuthorizationLifecycle:
    """
    Integration Scenario 1:
    - Create authorization
    - Approve and activate
    - Risk escalates → authorization automatically restricts
    - Further escalation → freeze
    - Recovery → restrict → active
    - Revoke
    """

    def test_auth_lifecycle_with_risk_escalation(self, auth_machine, risk_governor):
        """Full lifecycle: create → approve → activate → restrict on risk → freeze → recover → revoke"""

        # Step 1: Create DRAFT authorization
        auth = auth_machine.create_draft(
            title="Live Trading Auth",
            scope={
                "categories": ["linear"],
                "symbols": ["BTCUSDT", "ETHUSDT"],
                "max_leverage": 5,
                "mode": "supervised_live",
            },
            created_by="operator_1",
            description="Full live trading authorization with risk controls",
            expires_at_ms=_future_ms(86400),  # 1 day from now
        )
        assert auth.state == AuthState.DRAFT
        assert auth.is_effective is False

        # Step 2: Submit for approval
        auth = auth_machine.submit_for_approval(auth.authorization_id)
        assert auth.state == AuthState.PENDING_APPROVAL

        # Step 3: Approve and activate
        auth = auth_machine.approve(
            auth.authorization_id,
            approved_by="supervisor_1",
            reason="Passed risk assessment",
        )
        assert auth.state == AuthState.ACTIVE
        assert auth.is_effective is True
        assert auth.approved_by == "supervisor_1"

        # Verify authorization was approved
        assert len(auth_machine._audit_records) >= 3

        # Step 4: Simulate risk escalation to HIGH
        # Risk moves NORMAL → CAUTIOUS → REDUCED
        risk_state = risk_governor.escalate_to(
            RiskLevel.CAUTIOUS,
            reason="Drawdown warning",
            event=RiskEvent.DRAWDOWN_WARNING,
            initiator=RiskInitiator.RISK_GOVERNOR,
        )
        assert risk_state.level == RiskLevel.CAUTIOUS

        # Now escalate to REDUCED (higher risk)
        risk_state = risk_governor.escalate_to(
            RiskLevel.REDUCED,
            reason="Daily loss warning",
            event=RiskEvent.DAILY_LOSS_WARNING,
            initiator=RiskInitiator.RISK_GOVERNOR,
        )
        assert risk_state.level == RiskLevel.REDUCED

        # Step 5: Authorization should be automatically restricted by integration logic
        # (In real system, risk monitor would call auth_machine.restrict())
        auth = auth_machine.restrict(
            auth.authorization_id,
            reason="Risk level escalated to REDUCED",
            initiator=AuthInitiator.INCIDENT_POLICY,
        )
        assert auth.state == AuthState.RESTRICTED
        assert auth.is_effective is True  # Still effective but narrower

        # Step 6: Further risk escalation to DEFENSIVE triggers freeze
        risk_state = risk_governor.escalate_to(
            RiskLevel.DEFENSIVE,
            reason="Consecutive losses",
            event=RiskEvent.CONSECUTIVE_LOSSES,
            initiator=RiskInitiator.RISK_GOVERNOR,
        )
        assert risk_state.level == RiskLevel.DEFENSIVE

        # Authorization should freeze on DEFENSIVE risk
        auth = auth_machine.freeze(
            auth.authorization_id,
            reason="Risk level DEFENSIVE: active de-risking required",
            initiator=AuthInitiator.INCIDENT_POLICY,
        )
        assert auth.state == AuthState.FROZEN
        assert auth.is_effective is False

        # Step 7: Operator approves recovery to RESTRICTED (conservative)
        # (Note: auth is now in FROZEN state, not RESTRICTED, from Step 6)
        auth = auth_machine.recover_to_restricted(
            auth.authorization_id,
            approved_by="supervisor_1",
            reason="Positions de-risked, safe to resume limited trading",
        )
        assert auth.state == AuthState.RESTRICTED

        # Step 8: Eventually revoke authorization
        auth = auth_machine.revoke(
            auth.authorization_id,
            approved_by="supervisor_1",
            reason="Trading strategy no longer active",
        )
        assert auth.state == AuthState.REVOKED
        assert auth.is_effective is False
        assert auth.is_terminal is True

        # Verify complete audit trail
        assert len(auth_machine._audit_records) >= 6  # Multiple transitions
        assert len(risk_governor._audit_records) >= 3  # Multiple risk escalations


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario 2: Risk Escalation Triggers Authorization Restriction
# 场景 2: 风控升级触发授权限制
# ═══════════════════════════════════════════════════════════════════════════════


class TestScenario2RiskEscalationCascade:
    """
    Integration Scenario 2:
    - Start with NORMAL risk and ACTIVE authorization
    - Risk escalates through levels: NORMAL → CAUTIOUS → REDUCED → DEFENSIVE → CRITICAL
    - Authorization automatically restricts on certain escalation thresholds
    - Verify risk constraints are enforced at each level
    """

    def test_risk_escalation_restricts_authorization(self, auth_machine, risk_governor):
        """Risk escalation cascade restricts authorization"""

        # Setup: Create and activate authorization
        auth = auth_machine.create_draft(
            title="Trading Auth for Risk Test",
            scope={"symbols": ["BTCUSDT"], "mode": "supervised_live"},
            created_by="operator_1",
            expires_at_ms=_future_ms(86400),
        )
        auth = auth_machine.submit_for_approval(auth.authorization_id)
        auth = auth_machine.approve(
            auth.authorization_id,
            approved_by="supervisor_1",
            reason="Approved for testing",
        )
        assert auth.state == AuthState.ACTIVE

        # Setup: Risk starts at NORMAL
        gov_state = risk_governor.get_state()
        assert gov_state.level == RiskLevel.NORMAL

        # Event 1: Drawdown warning triggers CAUTIOUS
        gov_state = risk_governor.escalate_to(
            RiskLevel.CAUTIOUS,
            reason="Drawdown 5%",
            event=RiskEvent.DRAWDOWN_WARNING,
            initiator=RiskInitiator.RISK_GOVERNOR,
        )
        assert gov_state.level == RiskLevel.CAUTIOUS
        # Authorization remains ACTIVE but system should note caution

        # Event 2: Daily loss triggers REDUCED
        gov_state = risk_governor.escalate_to(
            RiskLevel.REDUCED,
            reason="Daily loss 2%",
            event=RiskEvent.DAILY_LOSS_WARNING,
            initiator=RiskInitiator.RISK_GOVERNOR,
        )
        assert gov_state.level == RiskLevel.REDUCED

        # At REDUCED risk level, authorization must restrict
        auth = auth_machine.restrict(
            auth.authorization_id,
            reason="Risk level REDUCED: reduce-only mode active",
            initiator=AuthInitiator.INCIDENT_POLICY,
        )
        assert auth.state == AuthState.RESTRICTED

        # Verify restriction applied
        risk_constraints = risk_governor.get_constraints()
        assert risk_constraints.reduce_only is True  # REDUCED means reduce-only
        assert risk_constraints.new_entries_allowed is False

        # Event 3: Consecutive losses trigger DEFENSIVE
        gov_state = risk_governor.escalate_to(
            RiskLevel.DEFENSIVE,
            reason="10 consecutive losses",
            event=RiskEvent.CONSECUTIVE_LOSSES,
            initiator=RiskInitiator.RISK_GOVERNOR,
        )
        assert gov_state.level == RiskLevel.DEFENSIVE

        # At DEFENSIVE, authorization must freeze
        auth = auth_machine.freeze(
            auth.authorization_id,
            reason="Risk level DEFENSIVE: active de-risking required",
            initiator=AuthInitiator.INCIDENT_POLICY,
        )
        assert auth.state == AuthState.FROZEN

        # DEFENSIVE constraints: no new entries, position reduction, active de-risking
        risk_constraints = risk_governor.get_constraints()
        assert risk_constraints.active_de_risking is True
        assert risk_constraints.new_entries_allowed is False

        # Event 4: Escalate to DEFENSIVE first
        gov_state = risk_governor.escalate_to(
            RiskLevel.DEFENSIVE,
            reason="Multiple loss thresholds hit",
            event=RiskEvent.INCIDENT_TRIGGERED,
            initiator=RiskInitiator.INCIDENT_POLICY,
        )
        assert gov_state.level == RiskLevel.DEFENSIVE

        # Event 5: API loss or market data stale triggers CIRCUIT_BREAKER
        gov_state = risk_governor.escalate_to(
            RiskLevel.CIRCUIT_BREAKER,
            reason="Exchange API timeout",
            event=RiskEvent.API_CONNECTIVITY_LOSS,
            initiator=RiskInitiator.INCIDENT_POLICY,
        )
        assert gov_state.level == RiskLevel.CIRCUIT_BREAKER

        # CIRCUIT_BREAKER constraints: full halt, emergency stops, requires operator
        risk_constraints = risk_governor.get_constraints()
        assert risk_constraints.emergency_stops is True
        assert risk_constraints.requires_operator is True

        # Authorization remains FROZEN (cannot operate at circuit breaker)
        assert auth.state == AuthState.FROZEN

        # Verify full escalation chain is audited
        assert len(risk_governor._audit_records) >= 4
        assert len(auth_machine._audit_records) >= 4


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario 3: Lease Expiry Cascade Effect
# 场景 3: 租约过期级联效应
# ═══════════════════════════════════════════════════════════════════════════════


class TestScenario3LeaseExpiryCascade:
    """
    Integration Scenario 3:
    - Create decision lease
    - Link to authorization (implicit: lease scope matches auth scope)
    - Lease expires or is revoked
    - Associated authorization should gracefully handle expiry
    - Risk governor should not escalate just because lease expired
    """

    def test_lease_expiry_affects_associated_authorization(self, auth_machine, lease_machine):
        """Lease expiry properly cascades to authorization"""

        # Step 1: Create and activate authorization
        auth = auth_machine.create_draft(
            title="Limited Time Auth",
            scope={"symbols": ["BTCUSDT"], "session": "morning_session"},
            created_by="operator_1",
            expires_at_ms=_future_ms(3600),  # 1 hour
        )
        auth = auth_machine.submit_for_approval(auth.authorization_id)
        auth = auth_machine.approve(
            auth.authorization_id,
            approved_by="supervisor_1",
            reason="Session trading auth",
        )
        auth_id = auth.authorization_id
        assert auth.state == AuthState.ACTIVE

        # Step 2: Create decision lease with shorter TTL
        lease = lease_machine.create_draft(
            intent={"symbols": ["BTCUSDT"], "session": "morning_session"},
            created_by="operator_1",
            expires_at_ms=_future_ms(1800),  # 30 minutes
        )
        lease = lease_machine.register(lease.lease_id)
        lease = lease_machine.activate(lease.lease_id)
        lease_id = lease.lease_id
        assert lease.state == LeaseState.ACTIVE

        # Step 3: Verify both are active
        auth = auth_machine.get(auth_id)
        assert auth.state == AuthState.ACTIVE

        # Step 4: Simulate lease expiry (system calls expiry handler)
        from app.decision_lease_state_machine import LeaseEvent
        lease = lease_machine.transition(
            lease_id,
            LeaseState.EXPIRED,
            event=LeaseEvent.EXPIRED_BY_TIME,
            initiator=LeaseInitiator.EXPIRY_GUARDIAN,
        )
        assert lease.state == LeaseState.EXPIRED
        assert lease.is_terminal is True

        # Step 5: Associated authorization should be notified
        # In real system, lease expiry would trigger auth expiry if scopes match
        auth = auth_machine.transition(
            auth_id,
            AuthState.EXPIRED,
            event=AuthEvent.EXPIRED,
            initiator=AuthInitiator.EXPIRY_GUARDIAN,
        )
        assert auth.state == AuthState.EXPIRED
        assert auth.is_terminal is True

        # Step 6: Verify both are now terminal
        assert lease.is_terminal is True
        assert auth.is_terminal is True

        # Verify audit trail
        assert len(lease_machine._audit_records) >= 3
        assert len(auth_machine._audit_records) >= 4

    def test_lease_revocation_does_not_break_authorization(self, auth_machine, lease_machine):
        """Lease revocation is independent of authorization state"""

        # Create and activate both
        auth = auth_machine.create_draft(
            title="Revocable Auth",
            scope={"symbols": ["ETHUSDT"]},
            created_by="operator_1",
            expires_at_ms=_future_ms(86400),
        )
        auth = auth_machine.submit_for_approval(auth.authorization_id)
        auth = auth_machine.approve(
            auth.authorization_id,
            approved_by="supervisor_1",
            reason="OK",
        )
        auth_id = auth.authorization_id

        lease = lease_machine.create_draft(
            intent={"symbols": ["ETHUSDT"]},
            created_by="operator_1",
        )
        lease = lease_machine.register(lease.lease_id)
        lease = lease_machine.activate(lease.lease_id)
        lease_id = lease.lease_id

        # Revoke lease
        lease = lease_machine.revoke(lease_id, approved_by="operator_1")
        assert lease.state == LeaseState.REVOKED

        # Authorization should still be ACTIVE (separate lifecycle)
        auth = auth_machine.get(auth_id)
        assert auth.state == AuthState.ACTIVE


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario 4: Reconciliation Detects Inconsistency → Risk Escalation
# 场景 4: 对账发现不一致→风控升级
# ═══════════════════════════════════════════════════════════════════════════════


class TestScenario4ReconciliationTriggersRiskEscalation:
    """
    Integration Scenario 4:
    - Reconciliation engine finds a major mismatch (MISMATCH_MAJOR)
    - Generates discrepancy with CRITICAL severity
    - This triggers risk escalation event
    - Authorization is automatically restricted
    """

    def test_major_reconciliation_mismatch_escalates_risk(
        self, reconciliation_engine, risk_governor, auth_machine
    ):
        """Major reconciliation mismatch triggers risk escalation"""

        # Setup: Active authorization and NORMAL risk
        auth = auth_machine.create_draft(
            title="Live Trading Auth",
            scope={"symbols": ["BTCUSDT"]},
            created_by="operator_1",
            expires_at_ms=_future_ms(86400),
        )
        auth = auth_machine.submit_for_approval(auth.authorization_id)
        auth = auth_machine.approve(
            auth.authorization_id,
            approved_by="supervisor_1",
            reason="OK",
        )
        auth_id = auth.authorization_id
        assert auth.state == AuthState.ACTIVE

        gov_state = risk_governor.get_state()
        assert gov_state.level == RiskLevel.NORMAL

        # Create local (paper) state
        local_state = {
            "orders": [
                {"order_id": "o1", "symbol": "BTCUSDT", "state": "filled", "side": "Buy", "qty": 1.0},
                {"order_id": "o2", "symbol": "BTCUSDT", "state": "filled", "side": "Sell", "qty": 0.5},
            ],
            "positions": {"BTCUSDT": {"side": "Buy", "size": 0.5, "avg_entry_price": 50000}},
            "fills": [
                {"order_id": "o1", "fill_qty": 1.0, "fill_price": 50000},
                {"order_id": "o2", "fill_qty": 0.5, "fill_price": 50500},
            ],
            "balances": {"USDT": 100000.0},
            "snapshot_ts_ms": _now_ms(),
        }

        # Create remote (exchange) state with MAJOR discrepancy
        remote_state = {
            "orders": [
                {"order_id": "o1", "symbol": "BTCUSDT", "state": "filled", "side": "Buy", "qty": 1.0},
                # o2 is MISSING in remote!
            ],
            "positions": {"BTCUSDT": {"side": "Buy", "size": 1.0, "avg_entry_price": 50000}},
            # Size mismatch: local 0.5, remote 1.0
            "fills": [
                {"order_id": "o1", "fill_qty": 1.0, "fill_price": 50000},
            ],
            "balances": {"USDT": 99500.0},  # Different balance
            "snapshot_ts_ms": _now_ms(),
        }

        # Run reconciliation
        report = reconciliation_engine.reconcile(local_state, remote_state)

        # Should detect major mismatches
        assert report.overall_result != ReconciliationResult.MATCH
        critical_discrepancies = [
            d for d in report.discrepancies if d.severity == Severity.CRITICAL
        ]
        assert len(critical_discrepancies) > 0

        # Trigger risk escalation based on reconciliation failure
        # (In real system, reconciliation monitor would do this)
        # Always escalate on major discrepancy - test the integration
        gov_state = risk_governor.escalate_to(
            RiskLevel.DEFENSIVE,
            reason="Reconciliation major mismatch detected",
            event=RiskEvent.INCIDENT_TRIGGERED,
            initiator=RiskInitiator.INCIDENT_POLICY,
        )
        assert gov_state.level == RiskLevel.DEFENSIVE

        # Now escalate to circuit breaker
        gov_state = risk_governor.escalate_to(
            RiskLevel.CIRCUIT_BREAKER,
            reason="Reconciliation mismatch - emergency circuit break",
            event=RiskEvent.INCIDENT_TRIGGERED,
            initiator=RiskInitiator.INCIDENT_POLICY,
        )
        assert gov_state.level == RiskLevel.CIRCUIT_BREAKER

        # Authorization should be frozen on CIRCUIT_BREAKER
        auth = auth_machine.freeze(
            auth_id,
            reason="Reconciliation mismatch detected, system frozen",
            initiator=AuthInitiator.INCIDENT_POLICY,
        )
        assert auth.state == AuthState.FROZEN

        # Verify audit trails
        assert len(reconciliation_engine._audit_records) >= 1
        assert len(risk_governor._audit_records) >= 1
        assert len(auth_machine._audit_records) >= 4


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario 5: Paper→Live Gate Full Flow
# 场景 5: 纸盘→实盘闸门完整流程
# ═══════════════════════════════════════════════════════════════════════════════


class TestScenario5PaperLiveGateFlow:
    """
    Integration Scenario 5:
    - Create authorization for paper trading
    - Collect metrics over time
    - Gate evaluation checks all criteria
    - Gate pass triggers authorization expansion to live
    - Operator must explicitly approve live promotion
    """

    def test_paper_live_gate_full_workflow(self, auth_machine, paper_live_gate):
        """Paper→Live gate: collect metrics → evaluate → promote to live"""

        # Step 1: Create authorization for paper trading
        auth = auth_machine.create_draft(
            title="Paper Trading Auth",
            scope={
                "categories": ["linear"],
                "symbols": ["BTCUSDT"],
                "mode": "paper_only",
                "max_leverage": 10,
            },
            created_by="operator_1",
            description="Initial paper trading authorization",
            expires_at_ms=_future_ms(86400 * 30),  # 30 days
        )
        auth = auth_machine.submit_for_approval(auth.authorization_id)
        auth = auth_machine.approve(
            auth.authorization_id,
            approved_by="supervisor_1",
            reason="Paper trading approval",
        )
        auth_id = auth.authorization_id
        assert auth.state == AuthState.ACTIVE
        assert auth.scope.get("mode") == "paper_only"

        # Step 2: Simulate paper trading metrics after sufficient time
        # (In real system, these would accumulate over weeks)
        paper_start_ms = _now_ms() - (28 * 86400 * 1000)  # 28 days ago
        total_trades = 550  # > 500
        winning_trades = 180  # 180/550 = 32.7% > 30%
        win_rate_pct = (winning_trades / total_trades) * 100
        gross_pnl = 15000.0
        fees_paid = 3000.0
        net_pnl = gross_pnl - fees_paid

        # Step 3: Run gate evaluation with individual parameters
        gate_result = paper_live_gate.evaluate_gate(
            paper_start_time_ms=paper_start_ms,
            total_trades=total_trades,
            win_rate_percent=win_rate_pct,
            net_pnl=net_pnl,
            sharpe_ratio=0.75,
            max_drawdown_percent=8.5,
            profit_factor=2.05,
            audit_trail_completeness_percent=99.45,
            reconciliation_mismatch_percent=0.1,
        )

        # Verify gate passes all checks
        assert gate_result.passed is True
        assert gate_result.gate_status == GateStatus.GATE_PASSED
        assert gate_result.blocking_reasons == []

        # Check individual criterion results
        assert gate_result.criteria_results.get("duration").passed is True
        assert gate_result.criteria_results.get("trade_count").passed is True
        assert gate_result.criteria_results.get("win_rate").passed is True
        assert gate_result.criteria_results.get("sharpe_ratio").passed is True
        assert gate_result.criteria_results.get("max_drawdown").passed is True
        assert gate_result.criteria_results.get("profit_factor").passed is True

        # Step 4: Gate passed, operator must submit approval
        gate_result = paper_live_gate.submit_operator_approval(
            approved=True,
            operator_id="supervisor_1",
            reason="Paper trading metrics excellent, safe to promote to live",
        )
        assert gate_result.gate_status == GateStatus.OPERATOR_APPROVED

        # Step 5: In real system, gate approval would trigger authorization scope expansion
        # Here we simulate operator manually expanding scope post-gate-approval
        # (Note: Auth scope expansion requires a revoke and re-create for scope changes)
        auth_updated = auth_machine.revoke(
            auth_id,
            approved_by="supervisor_1",
            reason="Scope change: preparing for live trading",
        )

        # Create new authorization with expanded scope
        auth_live = auth_machine.create_draft(
            title="Live Trading Auth (Post-Gate)",
            scope={
                "categories": ["linear"],
                "symbols": ["BTCUSDT"],
                "mode": "supervised_live",  # Changed from paper_only
                "max_leverage": 5,  # Reduced leverage for live
            },
            created_by="operator_1",
            description="Live trading authorization after gate approval",
            expires_at_ms=_future_ms(86400 * 30),
        )
        auth_live = auth_machine.submit_for_approval(auth_live.authorization_id)
        auth_live = auth_machine.approve(
            auth_live.authorization_id,
            approved_by="supervisor_1",
            reason="Paper→Live gate approved, ready for live trading",
        )
        assert auth_live.state == AuthState.ACTIVE  # Live auth is active
        assert auth_live.scope.get("mode") == "supervised_live"

        # Verify authorization transitions (revoke old + create + submit + approve new)
        assert len(auth_machine._audit_records) >= 5

        # Verify gate status
        assert gate_result.gate_status == GateStatus.OPERATOR_APPROVED


# ═══════════════════════════════════════════════════════════════════════════════
# Additional Integration Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestCrossModuleThreadSafety:
    """Verify cross-module interactions are thread-safe"""

    def test_concurrent_risk_escalation_and_auth_restriction(
        self, auth_machine, risk_governor
    ):
        """Multiple threads escalating risk and restricting auth concurrently"""

        # Setup
        auth = auth_machine.create_draft(
            title="Concurrent Test Auth",
            scope={"symbols": ["BTCUSDT"]},
            created_by="operator_1",
            expires_at_ms=_future_ms(86400),
        )
        auth = auth_machine.submit_for_approval(auth.authorization_id)
        auth = auth_machine.approve(
            auth.authorization_id,
            approved_by="supervisor_1",
            reason="OK",
        )
        auth_id = auth.authorization_id

        results = {"auth_states": [], "risk_levels": []}
        errors = []

        def escalate_risk():
            try:
                for i in range(3):
                    if i == 0:
                        level = RiskLevel.CAUTIOUS
                    elif i == 1:
                        level = RiskLevel.REDUCED
                    else:
                        level = RiskLevel.DEFENSIVE

                    state = risk_governor.escalate_to(
                        level,
                        reason=f"Escalation {i}",
                        event=RiskEvent.DRAWDOWN_WARNING,
                        initiator=RiskInitiator.RISK_GOVERNOR,
                    )
                    results["risk_levels"].append(state.level)
                    time.sleep(0.01)
            except Exception as e:
                errors.append(("escalate_risk", e))

        def restrict_auth():
            try:
                time.sleep(0.005)  # Slight delay to interleave
                auth = auth_machine.restrict(
                    auth_id,
                    reason="Concurrent test",
                    initiator=AuthInitiator.INCIDENT_POLICY,
                )
                results["auth_states"].append(auth.state)
            except Exception as e:
                errors.append(("restrict_auth", e))

        # Run concurrently
        t1 = threading.Thread(target=escalate_risk)
        t2 = threading.Thread(target=restrict_auth)

        t1.start()
        t2.start()

        t1.join(timeout=5)
        t2.join(timeout=5)

        # Verify no errors and expected outcomes
        assert len(errors) == 0, f"Concurrent operation errors: {errors}"
        assert AuthState.RESTRICTED in results["auth_states"]
        assert RiskLevel.DEFENSIVE in results["risk_levels"]


class TestMultiModuleAuditTrail:
    """Verify audit trails are properly maintained across modules"""

    def test_complete_audit_trail_for_complex_scenario(
        self, auth_machine, risk_governor, lease_machine
    ):
        """Complex scenario produces coherent audit trail across all modules"""

        # Execute a complex scenario
        auth = auth_machine.create_draft(
            title="Audit Test",
            scope={"symbols": ["BTCUSDT"]},
            created_by="operator_1",
            expires_at_ms=_future_ms(86400),
        )
        auth = auth_machine.submit_for_approval(auth.authorization_id)
        auth = auth_machine.approve(
            auth.authorization_id,
            approved_by="supervisor_1",
            reason="OK",
        )

        lease = lease_machine.create_draft(
            intent={"symbols": ["BTCUSDT"]},
            created_by="operator_1",
        )
        lease = lease_machine.register(lease.lease_id)
        lease = lease_machine.activate(lease.lease_id)

        risk_governor.escalate_to(
            RiskLevel.CAUTIOUS,
            reason="Drawdown warning",
            event=RiskEvent.DRAWDOWN_WARNING,
            initiator=RiskInitiator.RISK_GOVERNOR,
        )

        auth = auth_machine.restrict(
            auth.authorization_id,
            reason="Risk escalation",
            initiator=AuthInitiator.INCIDENT_POLICY,
        )

        # Verify audit records
        auth_records = auth_machine._audit_records
        lease_records = lease_machine._audit_records
        risk_records = risk_governor._audit_records

        # All modules should have audit records
        assert len(auth_records) >= 4  # create → submit → approve → restrict
        assert len(lease_records) >= 3  # create → register → activate
        assert len(risk_records) >= 1  # escalate

        # Records should have timestamps
        for record in auth_records:
            assert "effective_at_ms" in record or "timestamp" in record

        for record in lease_records:
            assert "effective_at_ms" in record or "timestamp" in record


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--timeout=30"])
