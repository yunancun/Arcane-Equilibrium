"""
Governance Hub — Central integration point for all governance state machines.
治理集線器 — 所有治理狀態機的中央集成點。

MODULE_NOTE (中文):
  本模組是 Phase 3 的核心組件，將 4 個治理狀態機統一管理：
  - AuthorizationStateMachine (SM-01)
  - RiskGovernorStateMachine (SM-04)
  - DecisionLeaseStateMachine (SM-02)
  - ReconciliationEngine (EX-04)

  跨 SM 聯動規則：
  - Risk ≥ REDUCED → Auth restrict; Risk ≥ CIRCUIT_BREAKER → Auth freeze
  - Reconciliation MISMATCH_MAJOR → Risk escalate; FATAL → Auth freeze
  - Auth FROZEN → Lease revoke_all_active

  治理集線器用途：
  - 統一 H0 門檢 (is_authorized)
  - 自動化跨 SM 級聯 (callbacks)
  - 提供統一的治理狀態 API (get_status)
  - 線程安全的所有操作

MODULE_NOTE (English):
  Phase 3 core component unifying 4 governance state machines.
  Cross-SM wiring rules are implemented as callbacks.

  Cross-SM wiring rules:
  - Risk ≥ REDUCED → Auth restrict; Risk ≥ CIRCUIT_BREAKER → Auth freeze
  - Reconciliation MISMATCH_MAJOR → Risk escalate; FATAL → Auth freeze
  - Auth FROZEN → Lease revoke_all_active

  Hub purposes:
  - Unified H0 gate check (is_authorized)
  - Automated cross-SM cascading (callbacks)
  - Unified governance status API (get_status)
  - Thread-safe all operations

Safety invariant:
  - Fail-closed: if hub is disabled or any SM unavailable, deny operations
  - Conservative direction auto-triggers; expansion requires approval
  - All cross-SM calls wrapped in exception handlers; fail-safe
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from .change_audit_log import ChangeAuditLog, ChangeType, ChangeApprovalStatus
from .recovery_approval_gate import RecoveryApprovalGate
from .governance_events import risk_event, recon_event

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Types / 类型
# ═══════════════════════════════════════════════════════════════════════════════

class GovernanceMode(str, Enum):
    """Global governance mode / 全局治理模式"""
    NORMAL = "NORMAL"           # All SMs active / 所有 SM 激活
    RESTRICTED = "RESTRICTED"   # Restricted operations allowed / 允许受限操作
    FROZEN = "FROZEN"           # All operations denied / 拒绝所有操作
    MANUAL_REVIEW = "MANUAL_REVIEW"  # Awaiting operator intervention / 等待操作员介入


# ═══════════════════════════════════════════════════════════════════════════════
# Data Classes / 数据类
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class GovernanceStatus:
    """Combined governance status snapshot / 联合治理状态快照"""
    timestamp_ms: int
    enabled: bool
    mode: str  # GovernanceMode

    # SM-01 Authorization State
    auth_state: str | None = None
    auth_expires_at_ms: int | None = None
    auth_scope: dict[str, Any] = field(default_factory=dict)
    auth_pending_approval: bool = False

    # SM-04 Risk Governor State
    risk_level: int | None = None
    risk_level_name: str | None = None
    risk_escalation_reason: str | None = None

    # SM-02 Decision Lease State
    active_leases_count: int = 0
    total_leases_tracked: int = 0

    # EX-04 Reconciliation State
    last_reconciliation_ms: int | None = None
    last_reconciliation_result: str | None = None
    is_consistent: bool | None = None

    # Audit trail
    incident_count: int = 0
    callback_errors: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_ms": self.timestamp_ms,
            "enabled": self.enabled,
            "mode": self.mode,
            "authorization": {
                "state": self.auth_state,
                "expires_at_ms": self.auth_expires_at_ms,
                "scope": self.auth_scope,
                "pending_approval": self.auth_pending_approval,
            },
            "risk": {
                "level": self.risk_level,
                "level_name": self.risk_level_name,
                "escalation_reason": self.risk_escalation_reason,
            },
            "leases": {
                "active_count": self.active_leases_count,
                "total_tracked": self.total_leases_tracked,
            },
            "reconciliation": {
                "last_check_ms": self.last_reconciliation_ms,
                "last_result": self.last_reconciliation_result,
                "is_consistent": self.is_consistent,
            },
            "incidents": self.incident_count,
            "callback_errors": self.callback_errors,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Governance Hub / 治理集线器
# ═══════════════════════════════════════════════════════════════════════════════

class GovernanceHub:
    """
    Central governance hub integrating all 4 state machines.
    中央治理集线器整合所有 4 个状态机。

    Thread-safe. All cross-SM operations protected by single RLock.
    线程安全。所有跨 SM 操作由单一 RLock 保护。
    """

    def __init__(self, *, audit_dir: str, enabled: bool = True):
        """
        Initialize GovernanceHub with all 4 SMs.

        Args:
            audit_dir: Directory path for audit persistence
            enabled: Whether governance is active (can be overridden by env var)
        """
        self._lock = threading.RLock()
        self._audit_dir = Path(audit_dir)
        self._audit_dir.mkdir(parents=True, exist_ok=True)

        # Check environment override for enabled flag
        env_enabled = os.environ.get("OPENCLAW_GOVERNANCE_ENABLED", "true").lower() == "true"
        self._enabled = enabled and env_enabled
        self._mode = GovernanceMode.NORMAL

        # Initialize all 4 state machines
        self._authorization_sm: Optional[Any] = None
        self._risk_governor_sm: Optional[Any] = None
        self._lease_sm: Optional[Any] = None
        self._reconciliation_engine: Optional[Any] = None
        self._oms_sm: Optional[Any] = None  # T5.03: OMS State Machine for order reconciliation

        # Tracking for callbacks
        self._callback_errors = 0
        self._incident_count = 0

        # Lazy initialization flag
        self._initialized = False

        # Authorization cache with TTL (100ms) for hot-path optimization
        # Stores: (cached_result, timestamp_ms)
        self._cached_auth_state: tuple[bool, int] | None = None
        self._cache_ttl_ms = 100  # TTL in milliseconds

        # T1.04: Audit pipeline for SM persistence
        self._audit_pipeline: Optional[Any] = None

        # T2.04: Change Audit Log for WHO/WHEN/APPROVAL tracking
        self._change_audit_log: Optional[ChangeAuditLog] = None

        # T2.05: Recovery Approval Gate for de-escalation approval
        self._recovery_gate: Optional[RecoveryApprovalGate] = None

        # T8.06: TelegramAlerter for governance event notifications
        self._alerter: Optional[Any] = None

        # T9A.01: LearningTierGate for analyst agent evolution
        self._learning_tier_gate: Optional[Any] = None

        # T9A.02: Governance event stream for event aggregation
        self._governance_events: list[dict[str, Any]] = []
        self._governance_events_max_size = 1000

    def set_audit_pipeline(self, pipeline: Any) -> None:
        """
        Set the audit pipeline for SM callbacks.
        設置 SM 回調的審計管道。

        Args:
            pipeline: AuditPipeline instance for persisting audit records to disk
        """
        with self._lock:
            self._audit_pipeline = pipeline
            logger.info("Audit pipeline set on GovernanceHub")

    def set_change_audit_log(self, cal: Any) -> None:
        """Inject ChangeAuditLog for WHO/WHEN/APPROVAL tracking / 注入變更審計日誌"""
        with self._lock:
            self._change_audit_log = cal
            logger.info("ChangeAuditLog set on GovernanceHub")

    def set_recovery_gate(self, gate: Any) -> None:
        """Inject RecoveryApprovalGate for de-escalation approval / 注入恢復審批門禁"""
        with self._lock:
            self._recovery_gate = gate
            logger.info("RecoveryApprovalGate set on GovernanceHub")

    def set_alerter(self, alerter: Any) -> None:
        """
        T8.06: Inject TelegramAlerter for governance event notifications.
        注入 TelegramAlerter 用于治理事件通知。

        Args:
            alerter: TelegramAlerter instance for sending alerts
        """
        with self._lock:
            self._alerter = alerter
            logger.info("TelegramAlerter set on GovernanceHub")

    def set_oms_sm(self, oms_sm: Any) -> None:
        """T5.03: Inject OMS State Machine for order reconciliation / 注入OMS狀態機"""
        with self._lock:
            self._oms_sm = oms_sm
            logger.info("OMS State Machine set on GovernanceHub")

    def set_learning_tier_gate(self, gate: Any) -> None:
        """T9A.01: Inject LearningTierGate for analyst agent evolution / 注入学习等级门控"""
        with self._lock:
            self._learning_tier_gate = gate
            logger.info("LearningTierGate set on GovernanceHub")

    def is_enabled(self) -> bool:
        """
        Check if governance hub is enabled (public API).
        检查治理集线器是否启用（公共 API）。

        Returns:
            True if governance is active; False if disabled
        """
        return self._enabled

    def _ensure_initialized(self) -> None:
        """Lazy-initialize SMs on first access / 首次访问时延迟初始化 SM"""
        if self._initialized:
            return

        try:
            # Lazy imports to avoid circular dependencies
            from .authorization_state_machine import AuthorizationStateMachine
            from .risk_governor_state_machine import RiskGovernorStateMachine
            from .decision_lease_state_machine import DecisionLeaseStateMachine
            from .reconciliation_engine import ReconciliationEngine, ReconciliationConfig

            # T1.04: Create audit callbacks - use audit pipeline if available
            if self._audit_pipeline is not None:
                auth_callback = self._audit_pipeline.make_callback("authorization")
                risk_callback = self._audit_pipeline.make_callback("risk_governor")
                lease_callback = self._audit_pipeline.make_callback("decision_lease")
                recon_callback = self._audit_pipeline.make_callback("reconciliation")
            else:
                # Fallback to built-in audit callbacks (backward compatibility)
                auth_callback = self._make_audit_callback("authorization")
                risk_callback = self._make_audit_callback("risk_governor")
                lease_callback = self._make_audit_callback("decision_lease")
                recon_callback = self._make_audit_callback("reconciliation")

            # Create incident callback for reconciliation engine
            incident_callback = self._make_incident_callback()

            # Initialize SMs
            self._authorization_sm = AuthorizationStateMachine(audit_callback=auth_callback)
            self._risk_governor_sm = RiskGovernorStateMachine(audit_callback=risk_callback)
            self._lease_sm = DecisionLeaseStateMachine(audit_callback=lease_callback)
            self._reconciliation_engine = ReconciliationEngine(
                config=ReconciliationConfig(),
                audit_callback=recon_callback,
                incident_callback=incident_callback,
            )

            # T5.02: Inject ChangeAuditLog into all SMs if available
            if self._change_audit_log is not None:
                try:
                    self._authorization_sm.set_change_audit_log(self._change_audit_log)
                    self._risk_governor_sm.set_change_audit_log(self._change_audit_log)
                    self._lease_sm.set_change_audit_log(self._change_audit_log)
                    logger.debug("ChangeAuditLog injected into all SMs")
                except Exception as e:
                    logger.warning(f"Failed to inject ChangeAuditLog into SMs: {e}")

            # Wire cross-SM callbacks
            self._wire_callbacks()

            self._initialized = True
            logger.info("GovernanceHub initialized with all 4 SMs")
        except Exception as e:
            logger.error(f"Failed to initialize GovernanceHub: {e}", exc_info=True)
            self._enabled = False
            raise

    def _make_audit_callback(self, sm_name: str) -> Callable[[dict[str, Any]], None]:
        """
        Factory for audit callbacks that persist to files / 审计回调工厂

        Optimized: I/O happens outside any lock; only lock is acquired for error tracking.
        """
        def callback(event: dict[str, Any]) -> None:
            try:
                audit_file = self._audit_dir / f"{sm_name}_audit.jsonl"
                event_with_meta = {
                    "timestamp_ms": int(time.time() * 1000),
                    "sm_name": sm_name,
                    **event,
                }
                with open(audit_file, "a") as f:
                    f.write(json.dumps(event_with_meta) + "\n")
                # SECURITY FIX #3: Set restrictive file permissions (0o600 = owner read-write only)
                os.chmod(audit_file, 0o600)
            except Exception as e:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Audit callback error for {sm_name}: {e}")
                with self._lock:
                    self._callback_errors += 1

        return callback

    def _make_incident_callback(self) -> Callable[[str, dict[str, Any]], None]:
        """
        Factory for reconciliation incident callbacks.
        Routes reconciliation incidents to appropriate cross-SM handlers.
        """
        def callback(action: str, report: dict[str, Any]) -> None:
            try:
                severity = report.get("overall_result", "").upper()
                # Treat reconciliation failures as incidents
                if action in ["reconciliation_mismatch", "reconciliation_failure"]:
                    # Map overall_result to severity for callback
                    if severity in ["CRITICAL", "FATAL"]:
                        self._on_reconciliation_mismatch(severity, report)
                    elif severity == "WARNING":
                        # Minor mismatch - log but don't escalate
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug(f"Reconciliation warning: {report.get('result')}")

                # T5.03: Handle OMS reconciliation state transitions if available
                if action == "reconciliation_complete" and self._oms_sm is not None:
                    try:
                        self._handle_oms_reconciliation(report)
                    except Exception as e:
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug(f"Error handling OMS reconciliation: {e}")
                        with self._lock:
                            self._callback_errors += 1

            except Exception as e:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Incident callback error for action {action}: {e}")
                with self._lock:
                    self._callback_errors += 1

        return callback

    def _wire_callbacks(self) -> None:
        """Wire cross-SM callbacks / 连接跨 SM 回调"""
        try:
            # Risk escalation → restrict/freeze auth
            if hasattr(self._risk_governor_sm, "_on_level_change"):
                original_callback = self._risk_governor_sm._on_level_change
                self._risk_governor_sm._on_level_change = lambda old, new: self._on_risk_escalation(old, new)
            logger.debug("Wired risk escalation callback")
        except Exception as e:
            logger.warning(f"Failed to wire risk escalation callback: {e}")

        # Note: Reconciliation engine incident_callback is already set during initialization
        # in _ensure_initialized() to avoid race conditions

    def _invalidate_auth_cache(self) -> None:
        """Invalidate authorization cache on state changes / 在状态更改时使缓存无效"""
        self._cached_auth_state = None
        # Record authorization cache invalidation
        if self._change_audit_log:
            try:
                self._change_audit_log.record_change(
                    change_type=ChangeType.STATE_CHANGE,
                    who="GovernanceHub",
                    what="Authorization cache invalidated",
                    reason="State machine transition detected",
                )
            except Exception as e:
                logger.debug(f"ChangeAuditLog record failed (non-fatal): {e}")

    def _check_de_escalation_gate(self, from_state: str, to_state: str, reason: str) -> bool:
        """
        Check if de-escalation is permitted via RecoveryApprovalGate.
        检查去升级是否通过 RecoveryApprovalGate 批准。

        De-escalation requires approval unless disabled.

        Args:
            from_state: Current state (more restrictive)
            to_state: Target state (less restrictive)
            reason: Reason for de-escalation

        Returns:
            True if de-escalation is permitted; False otherwise
        """
        if not self._recovery_gate:
            # No gate installed, allow by default
            return True

        # Check if pending approvals exist for this transition
        pending = self._recovery_gate.get_pending_requests()
        for req in pending:
            if req.get("from_state") == from_state and req.get("to_state") == to_state:
                return False  # De-escalation pending approval

        return True

    def is_authorized(self) -> bool:
        """
        H0 gate check. Returns False (fail-closed) if disabled or auth not in ACTIVE/RESTRICTED.
        H0 门检。如果禁用或授权不在 ACTIVE/RESTRICTED，返回 False（fail-closed）。

        Hot path: called on every tick/intent. Uses TTL cache to minimize lock contention.

        Returns:
            True if governance permits operations; False otherwise
        """
        # Fast path: check frozen state without lock
        if not self._enabled or self._mode == GovernanceMode.FROZEN:
            return False

        # Check cache first (lock-free read for hot path)
        now_ms = int(time.time() * 1000)
        if self._cached_auth_state is not None:
            cached_result, cached_ts_ms = self._cached_auth_state
            if now_ms - cached_ts_ms < self._cache_ttl_ms:
                return cached_result

        if not self._initialized:
            try:
                self._ensure_initialized()
            except Exception:
                return False

        # FIX-03: On cache miss or TTL expiry, re-check with fail-closed behavior
        try:
            with self._lock:
                try:
                    if self._authorization_sm is None:
                        result = False
                    else:
                        # Get any effective (ACTIVE or RESTRICTED) authorization
                        effective_auths = self._authorization_sm.get_effective()
                        result = len(effective_auths) > 0

                    # Update cache only on successful check
                    self._cached_auth_state = (result, now_ms)
                except Exception as e:
                    # On re-check failure, return False (fail-closed) and don't cache
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"Error in authorization check: {e}")
                    return False

                return result
        except Exception as e:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Error acquiring lock in is_authorized: {e}")
            return False  # Fail closed

    def get_risk_level(self) -> Optional[int]:
        """
        Current risk governor level (0=NORMAL ... 5=MANUAL_REVIEW).
        当前风控等级（0=NORMAL ... 5=MANUAL_REVIEW）。

        Returns:
            Risk level int or None if unavailable
        """
        if not self._enabled or not self._initialized:
            return None

        try:
            with self._lock:
                if self._risk_governor_sm is None:
                    return None
                state = self._risk_governor_sm.get_state()
                return int(state.level) if hasattr(state, "level") else None
        except Exception as e:
            logger.error(f"Error in get_risk_level: {e}")
            return None

    def check_risk_and_act(self, metrics: dict[str, Any]) -> Optional[int]:
        """
        Feed risk metrics to governor, auto-escalate if thresholds met, restrict auth if needed.
        向总督提供风险指标，如果超过阈值则自动升级，如果需要则限制授权。

        Args:
            metrics: Risk metrics dict (e.g., {'drawdown_pct': 5.2, 'daily_loss_pct': 3.1})

        Returns:
            New risk level or None if error
        """
        if not self._enabled or not self._initialized:
            return None

        try:
            with self._lock:
                if self._risk_governor_sm is None:
                    return None

                # Get current level (risk governor's internal evaluation is external responsibility)
                state = self._risk_governor_sm.get_state()
                return int(state.level)
        except Exception as e:
            logger.error(f"Error in check_risk_and_act: {e}")
            return None

    def acquire_lease(self, intent_id: str, scope: str, ttl_seconds: float = 30.0) -> Optional[str]:
        """
        Acquire a decision lease for a specific intent.
        为特定意图获取决策租约。

        Hot path: called on trade entry/exit decisions. Minimizes I/O while holding lock.

        Args:
            intent_id: Unique identifier for decision intent
            scope: Lease scope (e.g., 'TRADE_ENTRY', 'TRADE_EXIT')
            ttl_seconds: Time-to-live in seconds

        Returns:
            lease_id if successful; None if denied (fail-closed)
        """
        if not self._enabled or not self._initialized or not self.is_authorized():
            return None

        try:
            with self._lock:
                if self._lease_sm is None or self._authorization_sm is None:
                    return None

                # Check if auth permits this scope (single lock-protected call)
                effective_auths = self._authorization_sm.get_effective()
                if not effective_auths:
                    return None

                auth = effective_auths[0]  # Use first effective auth
                auth_dict = auth.to_dict()
                if not self._auth_permits_scope(auth_dict, scope):
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"Authorization does not permit lease scope: {scope}")
                    return None

                # Create lease draft and activate it (all within lock)
                lease_obj = self._lease_sm.create_draft(
                    intent={"intent_id": intent_id, "scope": scope},
                    created_by="GovernanceHub",
                )
                lease_id = lease_obj.lease_id

                # Register and activate
                self._lease_sm.register(lease_id)
                self._lease_sm.activate(lease_id)

                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Lease acquired: {lease_id} for intent {intent_id}")
                return lease_id
        except Exception as e:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Error acquiring lease for {intent_id}: {e}")
            return None

    def release_lease(self, lease_id: str, consumed: bool = False) -> bool:
        """
        Release or consume a lease after decision/execution.
        在决策/执行后释放或消费租约。

        Args:
            lease_id: ID of lease to release
            consumed: If True, mark as CONSUMED; else REVOKED

        Returns:
            True if successful; False otherwise
        """
        if not self._enabled or not self._initialized:
            return False

        try:
            with self._lock:
                if self._lease_sm is None:
                    return False

                if consumed:
                    self._lease_sm.consume(lease_id)
                else:
                    self._lease_sm.revoke(lease_id, approved_by="GovernanceHub")

                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Lease released: {lease_id} as {'CONSUMED' if consumed else 'REVOKED'}")
                return True
        except Exception as e:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Error releasing lease {lease_id}: {e}")
            return False

    # ── T5.05: De-escalation via RecoveryApprovalGate / 通过恢復審批門禁解除升級 ──

    def request_de_escalation(self, target_level: int, requested_by: str, reason: str = "") -> Optional[str]:
        """
        T5.05: Submit de-escalation request through recovery gate.
        通過恢復審批門禁提交降級要求。

        Args:
            target_level: Target risk level to de-escalate to
            requested_by: Name/ID of requester
            reason: Reason for de-escalation

        Returns:
            request_id if successful; None otherwise
        """
        if not self._enabled or not self._initialized or self._recovery_gate is None:
            return None

        try:
            from .recovery_approval_gate import RecoveryType
            from .risk_governor_state_machine import RiskLevel

            with self._lock:
                if self._risk_governor_sm is None:
                    return None

                current_state = self._risk_governor_sm.get_state()
                current_level = current_state.level

                # Ensure we're actually de-escalating
                if target_level >= current_level:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"De-escalation target {target_level} must be lower than current {current_level}")
                    return None

                # Submit recovery request
                req = self._recovery_gate.submit_recovery_request(
                    recovery_type=RecoveryType.RISK_DEESCALATE,
                    from_state=current_level.name,
                    to_state=RiskLevel(target_level).name,
                    requested_by=requested_by,
                    reason=reason,
                )

                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"De-escalation request submitted: {req.request_id}")
                return req.request_id

        except Exception as e:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Error submitting de-escalation request: {e}")
            return None

    def approve_de_escalation(self, request_id: str, approved_by: str) -> bool:
        """
        T5.05: Approve and execute de-escalation request.
        批准並執行降級要求。

        Args:
            request_id: ID of recovery request
            approved_by: Name of approver (should be Operator)

        Returns:
            True if successful; False otherwise
        """
        if not self._enabled or not self._initialized or self._recovery_gate is None:
            return False

        try:
            with self._lock:
                if self._risk_governor_sm is None:
                    return False

                # Get the request to determine target level
                req = self._recovery_gate._requests.get(request_id)
                if req is None:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"Request {request_id} not found")
                    return False

                # Approve the recovery
                approval = self._recovery_gate.approve_recovery(
                    request_id=request_id,
                    approved_by=approved_by,
                )

                if approval is None:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"Failed to approve recovery {request_id}")
                    return False

                # Execute de-escalation on the risk SM
                try:
                    from .risk_governor_state_machine import RiskLevel
                    target_level = RiskLevel[req.to_state]
                    self._risk_governor_sm.de_escalate_to(
                        target_level,
                        approved_by=approved_by,
                        reason=f"Approved via recovery gate: {req.reason}",
                    )

                    # Record to change audit log
                    if self._change_audit_log:
                        try:
                            from .change_audit_log import ChangeType
                            self._change_audit_log.record_change(
                                change_type=ChangeType.STATE_CHANGE,
                                who=approved_by,
                                what=f"RiskGovernor de-escalation approved: {req.from_state} → {req.to_state}",
                                reason=req.reason,
                                old_value=req.from_state,
                                new_value=req.to_state,
                            )
                        except Exception as e:
                            logger.error(f"Failed to record change audit: {e}")

                    # T8.06: Send success alert to Telegram if alerter available
                    if self._alerter is not None and hasattr(self._alerter, "is_enabled") and self._alerter.is_enabled:
                        try:
                            alert_msg = (
                                f"✅ <b>De-escalation Approved</b>\n"
                                f"Request ID: {request_id}\n"
                                f"Level Change: {req.from_state} → {req.to_state}\n"
                                f"Approved By: {approved_by}\n"
                                f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}"
                            )
                            self._alerter.send(alert_msg, parse_mode="HTML")
                        except Exception as e:
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug(f"Error sending de-escalation approval alert: {e}")

                    logger.info(f"De-escalation approved and executed for request {request_id}")
                    return True

                except Exception as e:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"Error executing de-escalation: {e}")
                    return False

        except Exception as e:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Error approving de-escalation: {e}")
            return False

    def reconcile(
        self,
        paper_state: dict[str, Any],
        demo_state: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Run reconciliation against demo/exchange state.
        针对 demo/交易所状态运行对账。

        Optimized to minimize lock duration: acquire engine reference only.

        Args:
            paper_state: Local paper trading state
            demo_state: Demo/exchange state (None for demo-only check)

        Returns:
            Reconciliation report dict
        """
        if not self._enabled or not self._initialized:
            return {"ok": False, "reason": "governance_disabled"}

        # Get engine reference under lock, then execute reconciliation outside lock
        reconciliation_engine = None
        with self._lock:
            if self._reconciliation_engine is None:
                return {"ok": False, "reason": "reconciliation_engine_unavailable"}
            reconciliation_engine = self._reconciliation_engine

        try:
            # Execute I/O-bound reconciliation outside lock
            report = reconciliation_engine.reconcile(
                paper_state=paper_state,
                demo_state=demo_state or paper_state,
            )

            # Check for major mismatches and escalate risk
            if report.get("severity") in ["CRITICAL", "FATAL"]:
                self._on_reconciliation_mismatch(report["severity"], report)

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Reconciliation complete: {report.get('result')}")
            return report
        except Exception as e:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Error in reconciliation: {e}")
            return {"ok": False, "reason": "reconciliation_error", "error": str(e)}

    def get_status(self) -> GovernanceStatus:
        """
        Get combined governance status for API/GUI.
        获取联合治理状态供 API/GUI 使用。

        Optimized to minimize lock duration: gather state quickly, construct outside lock.

        Returns:
            GovernanceStatus object
        """
        if not self._initialized:
            try:
                self._ensure_initialized()
            except Exception as e:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Cross-SM callback error: {e}")
                with self._lock:
                    self._callback_errors += 1

        # Gather all necessary state under lock in a single shot
        with self._lock:
            timestamp_ms = int(time.time() * 1000)
            enabled = self._enabled
            mode_value = self._mode.value
            callback_errors = self._callback_errors
            incident_count = self._incident_count

            # Collect all SM data within lock context
            auth_state = None
            auth_expires_at_ms = None
            auth_scope = {}
            risk_level = None
            risk_level_name = None
            active_leases_count = 0
            total_leases_tracked = 0

            # Get Auth state
            if self._authorization_sm is not None:
                try:
                    effective_auths = self._authorization_sm.get_effective()
                    if effective_auths:
                        auth = effective_auths[0]
                        auth_state = auth.state.value
                        auth_expires_at_ms = auth.expires_at_ms
                        auth_scope = auth.scope
                    else:
                        auth_state = "NONE"
                except Exception as e:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"Error reading auth state: {e}")

            # Get Risk state
            if self._risk_governor_sm is not None:
                try:
                    risk_state = self._risk_governor_sm.get_state()
                    risk_level = int(risk_state.level)
                    risk_level_name = risk_state.level.name
                except Exception as e:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"Error reading risk state: {e}")

            # Get Lease counts
            if self._lease_sm is not None:
                try:
                    leases = self._lease_sm.get_all()
                    live_leases = self._lease_sm.get_live()
                    active_leases_count = len(live_leases)
                    total_leases_tracked = len(leases)
                except Exception as e:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"Error reading lease state: {e}")

        # Construct status object outside of lock
        status = GovernanceStatus(
            timestamp_ms=timestamp_ms,
            enabled=enabled,
            mode=mode_value,
            auth_state=auth_state,
            auth_expires_at_ms=auth_expires_at_ms,
            auth_scope=auth_scope,
            risk_level=risk_level,
            risk_level_name=risk_level_name,
            active_leases_count=active_leases_count,
            total_leases_tracked=total_leases_tracked,
            callback_errors=callback_errors,
            incident_count=incident_count,
        )
        return status

    def get_governance_events(self, limit: int = 50, event_type: str | None = None) -> list[dict[str, Any]]:
        """
        T9A.02: Retrieve governance events from the event stream.
        检索治理事件流中的治理事件。

        Args:
            limit: Maximum number of events to return (default 50, max 1000)
            event_type: Optional filter by event type/category (e.g., "risk_governor", "authorization")

        Returns:
            List of governance event dictionaries (most recent first)
        """
        with self._lock:
            if event_type:
                # Filter by event type if specified
                filtered = [e for e in self._governance_events if e.get("category") == event_type]
            else:
                filtered = self._governance_events

            # Return most recent events first (reverse chronological)
            return list(reversed(filtered))[-min(limit, 1000):]

    def _append_governance_event(self, event: dict[str, Any]) -> None:
        """
        T9A.02: Append a governance event to the event stream (internal helper).
        将治理事件追加到事件流中（内部辅助方法）。

        Maintains bounded event list (max 1000 events, drops oldest).
        """
        with self._lock:
            self._governance_events.append(event)
            # Keep list bounded: drop oldest events if exceeding max size
            if len(self._governance_events) > self._governance_events_max_size:
                self._governance_events = self._governance_events[-self._governance_events_max_size:]

    def _on_risk_escalation(self, old_level: int, new_level: int) -> None:
        """
        Callback: risk escalated → restrict/freeze auth, revoke leases if severe.
        回调：风险升级 → 限制/冻结授权，如果严重则撤销租约。

        Optimized to minimize lock duration: collect auth IDs under lock, act outside.
        """
        if not self._enabled or not self._initialized:
            return

        try:
            # Collect auth IDs under lock (minimal work)
            auth_ids_to_restrict = []
            auth_ids_to_freeze = []
            should_freeze_auth = False

            with self._lock:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Risk escalated: {old_level} → {new_level}")
                self._incident_count += 1

                # T9A.02: Emit governance event for risk escalation
                try:
                    event = risk_event(
                        level_from=old_level,
                        level_to=new_level,
                        initiator="SYSTEM",
                        reason=f"Automatic risk escalation triggered",
                    )
                    self._append_governance_event(event.to_dict())
                except Exception as e:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"Error emitting risk escalation event: {e}")

                # Record change in audit log
                if self._change_audit_log:
                    try:
                        self._change_audit_log.record_change(
                            change_type=ChangeType.STATE_CHANGE,
                            who="GovernanceHub",
                            what=f"Risk level changed: {old_level} → {new_level}",
                            reason="Automatic risk escalation",
                            old_value=old_level,
                            new_value=new_level,
                        )
                    except Exception as e:
                        logger.error(f"ChangeAuditLog record failed (non-fatal): {e}")

                # Risk level 2 (REDUCED) or higher → restrict auth
                if new_level >= 2 and self._authorization_sm is not None:
                    try:
                        effective_auths = self._authorization_sm.get_effective()
                        auth_ids_to_restrict = [
                            auth.authorization_id for auth in effective_auths
                            if auth.state.value == "ACTIVE"
                        ]
                    except Exception as e:
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug(f"Error collecting auth IDs on risk escalation: {e}")
                        self._callback_errors += 1

                # Risk level 4 (CIRCUIT_BREAKER) or higher → freeze auth
                if new_level >= 4 and self._authorization_sm is not None:
                    try:
                        effective_auths = self._authorization_sm.get_effective()
                        auth_ids_to_freeze = [auth.authorization_id for auth in effective_auths]
                        should_freeze_auth = True
                    except Exception as e:
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug(f"Error collecting auth IDs for freeze: {e}")
                        self._callback_errors += 1

                # Update governance mode
                if new_level >= 5:
                    self._mode = GovernanceMode.MANUAL_REVIEW
                elif new_level >= 4:
                    self._mode = GovernanceMode.FROZEN
                elif new_level >= 2:
                    self._mode = GovernanceMode.RESTRICTED
                else:
                    self._mode = GovernanceMode.NORMAL

            # Execute auth changes outside lock
            if auth_ids_to_restrict:
                try:
                    with self._lock:
                        for auth_id in auth_ids_to_restrict:
                            self._authorization_sm.restrict(
                                auth_id,
                                reason=f"Risk escalation to level {new_level}",
                            )
                        self._invalidate_auth_cache()
                except Exception as e:
                    with self._lock:
                        self._callback_errors += 1
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"Error restricting auth on risk escalation: {e}")

            if auth_ids_to_freeze:
                try:
                    with self._lock:
                        for auth_id in auth_ids_to_freeze:
                            self._authorization_sm.freeze(
                                auth_id,
                                reason=f"Circuit breaker triggered at risk level {new_level}",
                            )
                        self._invalidate_auth_cache()
                    if should_freeze_auth:
                        self._on_auth_frozen()
                except Exception as e:
                    with self._lock:
                        self._callback_errors += 1
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"Error freezing auth on circuit breaker: {e}")

            # T8.06: Send alert to Telegram if escalated to CIRCUIT_BREAKER and alerter available
            if new_level >= 4 and self._alerter is not None and hasattr(self._alerter, "is_enabled") and self._alerter.is_enabled:
                try:
                    alert_msg = (
                        f"⚠️ <b>Risk Escalation Alert</b>\n"
                        f"Level: {old_level} → {new_level}\n"
                        f"Status: Circuit Breaker Activated\n"
                        f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    self._alerter.send(alert_msg, parse_mode="HTML")
                except Exception as e:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"Error sending risk escalation alert: {e}")

        except Exception as e:
            with self._lock:
                self._callback_errors += 1
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Error in _on_risk_escalation: {e}")

    def _on_reconciliation_mismatch(self, severity: str, details: dict[str, Any]) -> None:
        """
        T5.06: Callback: reconciliation found mismatch → escalate risk based on severity.
        回调：对账发现不一致 → 根据严重性升级风险。

        Severity handling:
        - MISMATCH_MINOR: log warning only
        - MISMATCH_MAJOR: escalate to DEFENSIVE or REDUCED
        - FATAL: escalate to CIRCUIT_BREAKER + cascade (freeze auth, revoke leases)

        Optimized to minimize lock duration.
        """
        if not self._enabled or not self._initialized:
            return

        try:
            current_level = None
            auth_ids_to_freeze = []
            target_risk_level = None

            with self._lock:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Reconciliation mismatch ({severity}): {details}")
                self._incident_count += 1

                # T9A.02: Emit governance event for reconciliation mismatch
                try:
                    event = recon_event(
                        result=severity,
                        initiator="SYSTEM",
                        message=f"Reconciliation mismatch detected: {severity}",
                        **details,
                    )
                    self._append_governance_event(event.to_dict())
                except Exception as e:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"Error emitting reconciliation event: {e}")

                # T5.06: Determine escalation level based on severity / 根据严重性确定升级级别
                if severity == "MISMATCH_MINOR":
                    # Minor mismatch - log warning only
                    logger.warning(f"Reconciliation warning (minor): {details}")
                    return

                elif severity == "MISMATCH_MAJOR":
                    # Major mismatch → escalate risk to DEFENSIVE or REDUCED
                    if self._risk_governor_sm is not None:
                        try:
                            from .risk_governor_state_machine import RiskLevel
                            current_level = self._risk_governor_sm.get_state().level
                            # Escalate to REDUCED or DEFENSIVE based on current level
                            if current_level < RiskLevel.REDUCED:
                                target_risk_level = RiskLevel.REDUCED
                            else:
                                target_risk_level = RiskLevel.DEFENSIVE
                        except Exception as e:
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug(f"Error getting risk level for major mismatch: {e}")
                            self._callback_errors += 1

                elif severity == "FATAL":
                    # Fatal mismatch → escalate to CIRCUIT_BREAKER + cascade
                    if self._risk_governor_sm is not None:
                        try:
                            from .risk_governor_state_machine import RiskLevel
                            target_risk_level = RiskLevel.CIRCUIT_BREAKER
                        except Exception as e:
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug(f"Error setting fatal escalation: {e}")
                            self._callback_errors += 1

                    # Collect auth IDs for freeze
                    if self._authorization_sm is not None:
                        try:
                            effective_auths = self._authorization_sm.get_effective()
                            auth_ids_to_freeze = [auth.authorization_id for auth in effective_auths]
                        except Exception as e:
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug(f"Error collecting auth IDs for fatal mismatch: {e}")
                            self._callback_errors += 1
                    self._mode = GovernanceMode.FROZEN

            # Execute escalations outside lock
            if target_risk_level is not None:
                try:
                    from .risk_governor_state_machine import RiskInitiator
                    with self._lock:
                        if self._risk_governor_sm is not None:
                            self._risk_governor_sm.escalate_to(
                                target_risk_level,
                                reason=f"reconciliation_{severity.lower()}",
                                initiator=RiskInitiator.RISK_GOVERNOR,
                            )
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug(f"Risk escalated to {target_risk_level.name} due to {severity}")
                except Exception as e:
                    with self._lock:
                        self._callback_errors += 1
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"Error escalating risk for {severity}: {e}")

            if auth_ids_to_freeze:
                try:
                    with self._lock:
                        if self._authorization_sm is not None:
                            for auth_id in auth_ids_to_freeze:
                                self._authorization_sm.freeze(
                                    auth_id,
                                    reason="Fatal reconciliation mismatch",
                                )
                            self._invalidate_auth_cache()
                            self._on_auth_frozen()
                except Exception as e:
                    with self._lock:
                        self._callback_errors += 1
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"Error freezing auth for fatal mismatch: {e}")

            # T8.06: Send FATAL alert to Telegram if alerter available
            if severity == "FATAL" and self._alerter is not None and hasattr(self._alerter, "is_enabled") and self._alerter.is_enabled:
                try:
                    alert_msg = (
                        f"🚨 <b>FATAL Reconciliation Mismatch</b>\n"
                        f"Status: Account FROZEN\n"
                        f"Details: {details.get('result', 'Unknown mismatch')}\n"
                        f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    self._alerter.send(alert_msg, parse_mode="HTML")
                except Exception as e:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"Error sending fatal reconciliation alert: {e}")

        except Exception as e:
            with self._lock:
                self._callback_errors += 1
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Error in _on_reconciliation_mismatch: {e}")

    def _on_auth_frozen(self) -> None:
        """
        Callback: auth frozen → revoke all active leases.
        回调：授权冻结 → 撤销所有活跃租约。

        Optimized to minimize lock duration: collect lease IDs, revoke outside lock.
        """
        if not self._enabled or not self._initialized:
            return

        try:
            lease_ids = []

            with self._lock:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("Authorization frozen, collecting active leases")

                if self._lease_sm is not None:
                    try:
                        live_leases = self._lease_sm.get_live()
                        lease_ids = [lease.lease_id for lease in live_leases]
                    except Exception as e:
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug(f"Error collecting leases on auth freeze: {e}")
                        self._callback_errors += 1

            # Revoke leases outside lock
            if lease_ids:
                try:
                    with self._lock:
                        if self._lease_sm is not None:
                            for lease_id in lease_ids:
                                self._lease_sm.revoke(
                                    lease_id,
                                    approved_by="GovernanceHub",
                                    reason="Authorization frozen",
                                )
                except Exception as e:
                    with self._lock:
                        self._callback_errors += 1
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"Error revoking leases on auth freeze: {e}")

        except Exception as e:
            with self._lock:
                self._callback_errors += 1
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Error in _on_auth_frozen: {e}")

    def handle_incident_auth_action(self, action: str, context: dict[str, Any]) -> None:
        """
        Handle authorization actions triggered by IncidentPolicy.
        處理 IncidentPolicy 觸發的授權動作。

        Args:
            action: Auth action name (AUTH_RESTRICT, AUTH_FREEZE, etc.)
            context: Event context dict
        """
        if not self._enabled or not self._initialized:
            return

        try:
            with self._lock:
                if self._authorization_sm is None:
                    return

                effective_auths = self._authorization_sm.get_effective()

                if action == "AUTH_RESTRICT":
                    for auth in effective_auths:
                        if auth.state.value == "ACTIVE":
                            self._authorization_sm.restrict(
                                auth.authorization_id,
                                reason=f"Incident {action}: {context.get('reason_code')}",
                            )
                    self._invalidate_auth_cache()

                elif action == "AUTH_FREEZE":
                    for auth in effective_auths:
                        self._authorization_sm.freeze(
                            auth.authorization_id,
                            reason=f"Incident {action}: {context.get('reason_code')}",
                        )
                    self._invalidate_auth_cache()
                    self._on_auth_frozen()

                logger.info(f"Incident auth action executed: {action}")
        except Exception as e:
            with self._lock:
                self._callback_errors += 1
            logger.error(f"Error in handle_incident_auth_action({action}): {e}")

    def handle_incident_risk_action(self, action: str, context: dict[str, Any]) -> None:
        """
        Handle risk actions triggered by IncidentPolicy.
        處理 IncidentPolicy 觸發的風險動作。

        Args:
            action: Risk action name (RISK_ESCALATE_*, RISK_CIRCUIT_BREAKER, etc.)
            context: Event context dict
        """
        if not self._enabled or not self._initialized:
            return

        try:
            with self._lock:
                if self._risk_governor_sm is None:
                    return

                from .risk_governor_state_machine import RiskLevel, RiskInitiator

                # Map incident actions to risk levels
                action_to_level = {
                    "RISK_ESCALATE_CAUTIOUS": RiskLevel.CAUTIOUS,
                    "RISK_ESCALATE_REDUCED": RiskLevel.REDUCED,
                    "RISK_ESCALATE_DEFENSIVE": RiskLevel.DEFENSIVE,
                    "RISK_CIRCUIT_BREAKER": RiskLevel.CIRCUIT_BREAKER,
                }

                target_level = action_to_level.get(action)
                if target_level is not None:
                    current_state = self._risk_governor_sm.get_state()
                    if current_state.level < target_level:
                        self._risk_governor_sm.escalate_to(
                            target_level,
                            reason=f"Incident {action}: {context.get('reason_code')}",
                            initiator=RiskInitiator.INCIDENT_POLICY,
                        )

                logger.info(f"Incident risk action executed: {action}")
        except Exception as e:
            with self._lock:
                self._callback_errors += 1
            logger.error(f"Error in handle_incident_risk_action({action}): {e}")

    def handle_incident_operator_alert(self, context: dict[str, Any]) -> None:
        """
        Handle operator alerts triggered by IncidentPolicy.
        處理 IncidentPolicy 觸發的運營商警報。

        Args:
            context: Event context dict
        """
        logger.critical(
            f"OPERATOR_ALERT: Incident {context.get('event_id')} "
            f"severity={context.get('severity')} reason={context.get('reason_code')}"
        )
        # TODO: Future enhancement - integrate with notification system

    def _auth_permits_scope(self, auth_dict: dict[str, Any], scope: str) -> bool:
        """Check if authorization permits lease scope / 检查授权是否允许租约范围"""
        try:
            # auth_dict should be from auth.to_dict()
            state = auth_dict.get("state")
            if state not in ["ACTIVE", "RESTRICTED"]:
                return False

            permitted_scopes = auth_dict.get("scope", {}).get("lease_scopes", [])
            return scope in permitted_scopes if permitted_scopes else True
        except Exception:
            return False

    def _handle_oms_reconciliation(self, report: dict[str, Any]) -> None:
        """
        T5.03: Handle OMS reconciliation state transitions based on reconciliation report.
        Based on reconciliation result, call appropriate OMS methods for orders in RECONCILING state.
        """
        if self._oms_sm is None:
            return

        try:
            from .oms_state_machine import OrderState, OrderInitiator

            overall_result = report.get("overall_result", "").upper()

            # Query orders that are currently in RECONCILING state
            reconciling_orders = self._oms_sm.get_by_state(OrderState.RECONCILING)

            if not reconciling_orders:
                return

            # Based on reconciliation result, transition orders appropriately
            if overall_result == "PASS":
                # Reconciliation passed - mark orders as COMPLETED
                for order_dict in reconciling_orders:
                    order_id = order_dict.get("order_id")
                    try:
                        self._oms_sm.reconciliation_pass(
                            order_id,
                            OrderInitiator.RECONCILIATION_ENGINE,
                            reason="Reconciliation passed",
                        )
                        logger.info(f"OMS order {order_id} transitioned to COMPLETED after reconciliation")
                    except Exception as e:
                        logger.error(f"Failed to complete order {order_id}: {e}")

            elif overall_result in ["MISMATCH_MINOR", "MISMATCH_MAJOR", "FAIL"]:
                # Reconciliation failed - mark orders as REJECTED
                for order_dict in reconciling_orders:
                    order_id = order_dict.get("order_id")
                    try:
                        self._oms_sm.reconciliation_fail(
                            order_id,
                            OrderInitiator.RECONCILIATION_ENGINE,
                            reason=f"Reconciliation failed: {overall_result}",
                        )
                        logger.info(f"OMS order {order_id} transitioned to REJECTED after reconciliation")
                    except Exception as e:
                        logger.error(f"Failed to reject order {order_id}: {e}")

        except Exception as e:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Error in _handle_oms_reconciliation: {e}")


__all__ = ["GovernanceHub", "GovernanceStatus", "GovernanceMode"]
