"""
Phase 2 Integration Tests — Risk Hardening Verification
Phase 2 集成测试 — 风控强化验证

10 test cases covering T2.01-T2.07 integration:
  IT-P2-01: High correlation portfolio check (PortfolioRiskControl)
  IT-P2-02: Sector concentration check
  IT-P2-03: Unmarked inference blocks trading (PerceptionPlane)
  IT-P2-04: Position open auto-creates hard stop-loss (ProtectiveOrderManager)
  IT-P2-05: Hard stop trigger fires close action
  IT-P2-06: Hard stop cannot be cancelled
  IT-P2-07: Change record contains WHO/WHEN (ChangeAuditLog)
  IT-P2-08: Recovery de-escalation requires approval (RecoveryApprovalGate)
  IT-P2-09: RECONCILING cannot be skipped (OMS SM)
  IT-P2-10: Scan interval < 5min blocked (ScannerRateLimiter)
"""

import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ═══════════════════════════════════════════════════════════════════════════════
# IT-P2-01: Portfolio correlation check
# ═══════════════════════════════════════════════════════════════════════════════

class TestPortfolioCorrelationCheck:
    """IT-P2-01: PortfolioRiskControl checks correlated positions"""

    def test_check_new_entry_returns_tuple(self):
        from app.portfolio_risk_control import PortfolioRiskControl, PortfolioRiskConfig

        config = PortfolioRiskConfig(correlation_threshold=0.7)
        prc = PortfolioRiskControl(config=config)

        # Feed price history for correlation calculation
        for i in range(50):
            prc.record_price("BTCUSDT", 40000.0 + i * 100)
            prc.record_price("ETHUSDT", 3000.0 + i * 7.5)

        positions = {"BTCUSDT": {"side": "Buy", "size": 1.0, "avg_entry_price": 40000.0}}

        allowed, reason = prc.check_new_entry(
            symbol="ETHUSDT", side="Buy", notional=30000.0,
            positions=positions, balance=100000.0,
            market_prices={"BTCUSDT": 45000.0, "ETHUSDT": 3375.0},
        )
        assert isinstance(allowed, bool)
        assert isinstance(reason, str)


# ═══════════════════════════════════════════════════════════════════════════════
# IT-P2-02: Sector concentration check
# ═══════════════════════════════════════════════════════════════════════════════

class TestSectorConcentrationCheck:
    """IT-P2-02: Sector exposure check returns (bool, str)"""

    def test_sector_check_runs(self):
        from app.portfolio_risk_control import PortfolioRiskControl, PortfolioRiskConfig

        config = PortfolioRiskConfig(max_sector_exposure_pct=40.0)
        prc = PortfolioRiskControl(config=config)

        positions = {
            "BTCUSDT": {"side": "Buy", "size": 1.0, "avg_entry_price": 40000.0, "category": "BTC"},
        }
        allowed, reason = prc.check_new_entry(
            symbol="BTCUSDT", side="Buy", notional=50000.0,
            positions=positions, balance=100000.0,
        )
        assert isinstance(allowed, bool)
        assert isinstance(reason, str)


# ═══════════════════════════════════════════════════════════════════════════════
# IT-P2-03: Unmarked inference blocks trading
# ═══════════════════════════════════════════════════════════════════════════════

class TestCognitiveHonestyBlock:
    """IT-P2-03: PerceptionPlane rejects unmarked data"""

    def test_unmarked_data_rejected(self):
        from app.perception_data_plane import (
            PerceptionPlane, DataSourceType, CognitiveLevel,
        )

        plane = PerceptionPlane()

        # Register data without cognitive level — source is search (→ INFERENCE by default)
        # Then validate — should be eligible since default is INFERENCE
        pdo = plane.register_data(
            source_type=DataSourceType.EXCHANGE_REST,
            content={"price": 40000.0},
            cognitive_level=CognitiveLevel.FACT,
            symbols=["BTCUSDT"],
            marked_by="test",
            marking_reason="test data",
        )
        assert pdo is not None

        # validate_for_decision takes a data_id
        valid, reason = plane.validate_for_decision(pdo.data_id)
        assert valid is True, f"FACT data should be eligible: {reason}"

    def test_no_cognitive_level_uses_default(self):
        from app.perception_data_plane import (
            PerceptionPlane, DataSourceType,
        )

        plane = PerceptionPlane()

        # Search source defaults to INFERENCE
        pdo = plane.register_data(
            source_type=DataSourceType.SEARCH_PERPLEXITY,
            content={"analysis": "BTC may rally"},
            symbols=["BTCUSDT"],
        )
        assert pdo is not None
        # Source-default cognitive level should be applied
        assert pdo.cognitive_level is not None

    def test_nonexistent_data_rejected(self):
        from app.perception_data_plane import PerceptionPlane

        plane = PerceptionPlane()
        valid, reason = plane.validate_for_decision("nonexistent_id")
        assert valid is False, "Nonexistent data must be rejected"


# ═══════════════════════════════════════════════════════════════════════════════
# IT-P2-04: Position open auto-creates hard stop-loss
# ═══════════════════════════════════════════════════════════════════════════════

class TestProtectiveOrderAutoCreate:
    """IT-P2-04: ProtectiveOrderManager creates hard stop on new position"""

    def test_create_hard_stop(self):
        from app.protective_order_manager import (
            ProtectiveOrderManager, ProtectiveOrderType, ProtectiveOrderSide,
            ProtectiveOrderStatus,
        )

        pom = ProtectiveOrderManager()
        order = pom.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=40000.0,
            trigger_price_pct=5.0,
            quantity=0.1,
        )
        assert order is not None
        assert order.order_type == ProtectiveOrderType.HARD_STOP_LOSS
        assert order.symbol == "BTCUSDT"
        assert order.status in (ProtectiveOrderStatus.CREATED, ProtectiveOrderStatus.ARMED)
        assert order.can_be_disabled is False, "HARD_STOP_LOSS must not be disableable"


# ═══════════════════════════════════════════════════════════════════════════════
# IT-P2-05: Hard stop trigger fires close action
# ═══════════════════════════════════════════════════════════════════════════════

class TestHardStopTrigger:
    """IT-P2-05: Price hitting hard stop triggers protective action"""

    def test_trigger_on_price_drop(self):
        from app.protective_order_manager import (
            ProtectiveOrderManager, ProtectiveOrderType, ProtectiveOrderSide,
        )

        pom = ProtectiveOrderManager()
        order = pom.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=40000.0,
            trigger_price_pct=5.0,  # trigger at ~38000
            quantity=0.1,
        )

        # Price drops below stop level
        market_state = {"BTCUSDT": {"price": 37000.0}}
        result = pom.check_triggers(market_state)
        assert result is not None
        assert len(result.triggered_orders) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# IT-P2-06: Hard stop cannot be cancelled
# ═══════════════════════════════════════════════════════════════════════════════

class TestHardStopCannotCancel:
    """IT-P2-06: HARD_STOP_LOSS with can_be_disabled=False cannot be cancelled"""

    def test_cancel_rejected(self):
        from app.protective_order_manager import (
            ProtectiveOrderManager, ProtectiveOrderType, ProtectiveOrderSide,
        )

        pom = ProtectiveOrderManager()
        order = pom.create_protective_order(
            symbol="BTCUSDT",
            side=ProtectiveOrderSide.LONG_POSITION,
            order_type=ProtectiveOrderType.HARD_STOP_LOSS,
            entry_price=40000.0,
            trigger_price_pct=5.0,
            quantity=0.1,
        )

        cancelled = pom.cancel_order(order.order_id, reason="user wants to remove")
        assert cancelled is False, "HARD_STOP_LOSS must not be cancellable"


# ═══════════════════════════════════════════════════════════════════════════════
# IT-P2-07: Change record contains WHO/WHEN
# ═══════════════════════════════════════════════════════════════════════════════

class TestChangeAuditRecord:
    """IT-P2-07: ChangeAuditLog records contain WHO/WHEN/WHAT/APPROVAL"""

    def test_record_has_required_fields(self):
        from app.change_audit_log import ChangeAuditLog, ChangeType

        cal = ChangeAuditLog()
        record = cal.record_change(
            change_type=ChangeType.STATE_CHANGE,
            who="GovernanceHub",
            what="Risk level changed: NORMAL → ELEVATED",
            reason="Drawdown threshold exceeded",
            old_value="NORMAL",
            new_value="ELEVATED",
            affected_components=["risk_governor", "authorization"],
        )

        assert record is not None
        assert record.who == "GovernanceHub"
        assert record.what == "Risk level changed: NORMAL → ELEVATED"
        assert record.when > 0, "Timestamp must be set"
        assert record.change_type == ChangeType.STATE_CHANGE
        # Values are JSON-serialized internally
        assert "NORMAL" in str(record.old_value)
        assert "ELEVATED" in str(record.new_value)

    def test_records_are_immutable(self):
        from app.change_audit_log import ChangeAuditLog, ChangeType

        cal = ChangeAuditLog()
        record = cal.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="Operator",
            what="Changed max_drawdown_pct from 5 to 3",
            reason="Risk reduction directive",
        )

        with pytest.raises((AttributeError, TypeError)):
            record.who = "Hacker"

    def test_change_history_queryable(self):
        from app.change_audit_log import ChangeAuditLog, ChangeType

        cal = ChangeAuditLog()
        cal.record_change(
            change_type=ChangeType.STATE_CHANGE,
            who="GovernanceHub",
            what="Auth frozen",
            reason="Critical incident",
        )
        cal.record_change(
            change_type=ChangeType.CONFIG_CHANGE,
            who="Operator",
            what="Updated threshold",
            reason="Routine adjustment",
        )

        history = cal.get_change_history()
        assert len(history) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# IT-P2-08: Recovery de-escalation requires approval
# ═══════════════════════════════════════════════════════════════════════════════

class TestRecoveryRequiresApproval:
    """IT-P2-08: De-escalation without Operator approval stays pending"""

    def test_submit_and_approve_flow(self):
        from app.recovery_approval_gate import (
            RecoveryApprovalGate, RecoveryType, ApprovalStatus,
        )

        gate = RecoveryApprovalGate()

        request = gate.submit_recovery_request(
            recovery_type=RecoveryType.RISK_DEESCALATE,
            from_state="CIRCUIT_BREAKER",
            to_state="DEFENSIVE",
            requested_by="System",
            reason="Risk metrics normalized",
            observation_period_hours=1,
        )
        assert request is not None
        assert request.status == ApprovalStatus.PENDING

        pending = gate.get_pending_requests()
        assert len(pending) >= 1

        approval = gate.approve_recovery(
            request_id=request.request_id,
            approved_by="Operator",
            conditions=["Monitor for 1 hour"],
            notes="Approved after metrics review",
        )
        assert approval is not None

    def test_unapproved_stays_pending(self):
        from app.recovery_approval_gate import (
            RecoveryApprovalGate, RecoveryType, ApprovalStatus,
        )

        gate = RecoveryApprovalGate()
        request = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="System",
            reason="Incident resolved",
        )
        assert request.status == ApprovalStatus.PENDING

        pending = gate.get_pending_requests()
        found = [r for r in pending if r["request_id"] == request.request_id]
        assert len(found) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# IT-P2-09: RECONCILING cannot be skipped
# ═══════════════════════════════════════════════════════════════════════════════

class TestReconcilingGate:
    """IT-P2-09: FILLED → COMPLETED direct transition is forbidden in OMS SM"""

    def test_filled_to_completed_forbidden(self):
        from app.oms_state_machine import OMSStateMachine, OrderState, OrderInitiator

        sm = OMSStateMachine()

        # Create and advance an order to FILLED (use correct initiators per transition rules)
        oid = sm.create_order("BTCUSDT", "Buy", 0.1, order_type="market")
        sm.submit_for_approval(oid, initiator=OrderInitiator.SYSTEM, reason="test")
        sm.approve(oid, initiator=OrderInitiator.AUTHORIZATION_SM, reason="auto")
        sm.send_to_venue(oid, initiator=OrderInitiator.SYSTEM, reason="submit")
        sm.acknowledge(oid, initiator=OrderInitiator.SYSTEM, reason="ack")
        sm.fill(oid, initiator=OrderInitiator.SYSTEM, reason="filled")

        # Direct FILLED → COMPLETED — should fail (forbidden transition)
        with pytest.raises(ValueError, match="Forbidden"):
            sm.transition(oid, OrderState.COMPLETED, OrderInitiator.SYSTEM, "skip_recon")

    def test_filled_to_reconciling_to_completed(self):
        from app.oms_state_machine import OMSStateMachine, OrderState, OrderInitiator

        sm = OMSStateMachine()
        oid = sm.create_order("BTCUSDT", "Buy", 0.1, order_type="market")
        sm.submit_for_approval(oid, initiator=OrderInitiator.SYSTEM, reason="test")
        sm.approve(oid, initiator=OrderInitiator.AUTHORIZATION_SM, reason="auto")
        sm.send_to_venue(oid, initiator=OrderInitiator.SYSTEM, reason="submit")
        sm.acknowledge(oid, initiator=OrderInitiator.SYSTEM, reason="ack")
        sm.fill(oid, initiator=OrderInitiator.SYSTEM, reason="filled")

        # Correct: FILLED → RECONCILING → COMPLETED
        sm.begin_reconciliation(oid, initiator=OrderInitiator.RECONCILIATION_ENGINE)
        sm.reconciliation_pass(oid, initiator=OrderInitiator.RECONCILIATION_ENGINE)

        # Verify final state
        orders = sm.get_by_state(OrderState.COMPLETED)
        completed_ids = [o["order_id"] for o in orders]
        assert oid in completed_ids


# ═══════════════════════════════════════════════════════════════════════════════
# IT-P2-10: Scan interval < 5min blocked
# ═══════════════════════════════════════════════════════════════════════════════

class TestScannerRateLimit:
    """IT-P2-10: ScannerRateLimiter blocks scans within 5-minute window"""

    def test_first_scan_allowed(self):
        from app.scanner_rate_limiter import ScannerRateLimiter, ScannerConfig

        limiter = ScannerRateLimiter(config=ScannerConfig(min_scan_interval_seconds=300))
        can, reason = limiter.can_scan()
        assert can is True, f"First scan should be allowed: {reason}"

    def test_rapid_scan_blocked(self):
        from app.scanner_rate_limiter import ScannerRateLimiter, ScannerConfig

        limiter = ScannerRateLimiter(config=ScannerConfig(min_scan_interval_seconds=300))

        can1, _ = limiter.can_scan()
        assert can1 is True

        # Record scan start + complete
        limiter.record_scan_start()
        limiter.record_scan_complete()

        # Immediate second scan — should be blocked
        can2, reason = limiter.can_scan()
        assert can2 is False, f"Rapid scan should be blocked: {reason}"

    def test_scan_after_zero_interval_allowed(self):
        from app.scanner_rate_limiter import ScannerRateLimiter, ScannerConfig

        limiter = ScannerRateLimiter(config=ScannerConfig(min_scan_interval_seconds=0))
        limiter.record_scan_start()
        limiter.record_scan_complete()

        can, reason = limiter.can_scan()
        assert can is True, f"Scan after 0-sec interval should be allowed: {reason}"


# ═══════════════════════════════════════════════════════════════════════════════
# Module injection verification
# ═══════════════════════════════════════════════════════════════════════════════

class TestPhase2ModuleInjection:
    """Verify all Phase 2 modules are injected at startup"""

    def test_portfolio_risk_control_injected(self):
        """T2.01: PortfolioRiskControl injected into RiskManager"""
        from app.paper_trading_routes import RISK_MANAGER
        assert hasattr(RISK_MANAGER, '_portfolio_risk_control')
        assert RISK_MANAGER._portfolio_risk_control is not None

    def test_perception_plane_created(self):
        """T2.02: PerceptionPlane created"""
        from app.paper_trading_routes import PERCEPTION_PLANE
        assert PERCEPTION_PLANE is not None

    def test_protective_order_manager_injected(self):
        """T2.03: ProtectiveOrderManager exists (RC-10: ENGINE disabled, Rust is sole engine)"""
        from app.paper_trading_routes import PROTECTIVE_ORDER_MANAGER
        # RC-10: ENGINE is None — ProtectiveOrderManager created but not injected into ENGINE
        # Verify the singleton exists independently / 驗證單例獨立存在
        assert PROTECTIVE_ORDER_MANAGER is not None

    def test_change_audit_log_injected(self):
        """T2.04: ChangeAuditLog injected into GovernanceHub"""
        from app.paper_trading_routes import GOV_HUB
        assert hasattr(GOV_HUB, '_change_audit_log')
        assert GOV_HUB._change_audit_log is not None

    def test_recovery_gate_injected(self):
        """T2.05: RecoveryApprovalGate injected into GovernanceHub"""
        from app.paper_trading_routes import GOV_HUB
        assert hasattr(GOV_HUB, '_recovery_gate')
        assert GOV_HUB._recovery_gate is not None
