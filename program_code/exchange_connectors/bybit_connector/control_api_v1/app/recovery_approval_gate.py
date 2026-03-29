"""
Recovery Approval Gating — State Machine Recovery requires Operator approval
恢复批准门禁 — 状态机恢复需运营商批准

Task: GAP-M9
Governance refs: SM-01, SM-04, DOC-07
Module: T2.18

MODULE_NOTE (中文):
  实现 DOC-07 和 SM-01/SM-04 中关于恢复批准的治理要求：
  - 升级（保守方向）= 自动，无需审批
  - 降级（宽松方向）= 需要 Operator 审批 + 观察期
  - 恢复请求与批准的正式对象化
  - 支持多种恢复类型：授权、风险、事故、交易
  - 线程安全设计
  - 完整审计链

MODULE_NOTE (English):
  Implements DOC-07 and SM-01/SM-04 governance for recovery approval:
  - Escalation (conservative) = automatic, no approval needed
  - De-escalation (relaxing) = requires Operator approval + observation period
  - Formal recovery request and approval objects
  - Multiple recovery types: auth, risk, incident, trading
  - Thread-safe design
  - Full audit chain
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════════

class RecoveryType(str, Enum):
    """Recovery operation types / 恢复操作类型"""
    AUTH_UNFREEZE = "auth_unfreeze"           # FROZEN → RESTRICTED/ACTIVE
    AUTH_RESTORE = "auth_restore"             # RESTRICTED → ACTIVE
    RISK_DEESCALATE = "risk_deescalate"       # DEFENSIVE/REDUCED/CAUTIOUS → less conservative
    RISK_UNFREEZE = "risk_unfreeze"           # CIRCUIT_BREAKER/DEFENSIVE → less conservative
    INCIDENT_RESOLVE = "incident_resolve"     # Close incident, approve recovery path
    TRADING_RESUME = "trading_resume"         # Resume trading after freeze


class ApprovalStatus(str, Enum):
    """Recovery approval status / 恢复批准状态"""
    PENDING = "pending"                       # Waiting for approval
    APPROVED = "approved"                     # Operator approved
    REJECTED = "rejected"                     # Operator rejected
    CANCELLED = "cancelled"                   # Requester cancelled


class ObservationPeriodStatus(str, Enum):
    """Observation period status / 观察期状态"""
    NOT_REQUIRED = "not_required"             # No observation period needed
    PENDING = "pending"                       # Observation period in progress
    COMPLETED = "completed"                   # Observation period completed
    FAILED = "failed"                         # Observation period failed (violation)


# ═══════════════════════════════════════════════════════════════════════════════
# Formal Objects
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class RecoveryRequest:
    """
    Formal recovery request object.
    正式恢复请求对象。

    Represents a request to recover from a frozen/restricted state.
    These are always created first and require approval before becoming effective.
    """
    request_id: str = ""
    recovery_type: RecoveryType = RecoveryType.AUTH_UNFREEZE
    from_state: str = ""                      # Current state (FROZEN, DEFENSIVE, etc.)
    to_state: str = ""                        # Desired state (RESTRICTED, ACTIVE, NORMAL, etc.)
    requested_by: str = ""                    # Actor submitting request
    requested_at_ms: int = 0                  # Timestamp (ms)
    reason: str = ""                          # Justification for recovery
    observation_period_hours: int = 0         # Required observation period (0 = none)
    evidence: dict = field(default_factory=dict)  # Supporting evidence/context
    status: ApprovalStatus = ApprovalStatus.PENDING

    def __post_init__(self):
        if not self.request_id:
            self.request_id = f"rec_req:{uuid.uuid4().hex[:12]}"
        if not self.requested_at_ms:
            self.requested_at_ms = int(time.time() * 1000)

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "recovery_type": self.recovery_type.value,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "requested_by": self.requested_by,
            "requested_at_ms": self.requested_at_ms,
            "reason": self.reason,
            "observation_period_hours": self.observation_period_hours,
            "evidence": self.evidence,
            "status": self.status.value,
        }


@dataclass
class RecoveryApproval:
    """
    Formal recovery approval object.
    正式恢复批准对象。

    Created when Operator approves a RecoveryRequest.
    Includes conditions and observation window details.
    """
    request_id: str = ""
    approved_by: str = ""                     # Operator name
    approved_at_ms: int = 0                   # Timestamp (ms)
    conditions: list = field(default_factory=list)  # Approval conditions (list of strings)
    observation_start_ms: int = 0             # Observation period start
    observation_end_ms: int = 0               # Observation period end (0 = N/A)
    notes: str = ""                           # Approval notes
    approval_id: str = ""                     # Unique approval ID

    def __post_init__(self):
        if not self.approval_id:
            self.approval_id = f"rec_app:{uuid.uuid4().hex[:12]}"
        if not self.approved_at_ms:
            self.approved_at_ms = int(time.time() * 1000)
        if not self.observation_start_ms and self.observation_end_ms > 0:
            self.observation_start_ms = self.approved_at_ms

    @property
    def has_observation_period(self) -> bool:
        """Returns True if approval requires observation period"""
        return self.observation_end_ms > 0

    @property
    def is_observation_complete(self) -> bool:
        """Returns True if observation period has elapsed"""
        if not self.has_observation_period:
            return True
        now_ms = int(time.time() * 1000)
        return now_ms >= self.observation_end_ms

    def to_dict(self) -> dict:
        return {
            "approval_id": self.approval_id,
            "request_id": self.request_id,
            "approved_by": self.approved_by,
            "approved_at_ms": self.approved_at_ms,
            "conditions": self.conditions,
            "observation_start_ms": self.observation_start_ms,
            "observation_end_ms": self.observation_end_ms,
            "has_observation_period": self.has_observation_period,
            "is_observation_complete": self.is_observation_complete,
            "notes": self.notes,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Recovery Approval Gate Engine
# ═══════════════════════════════════════════════════════════════════════════════

class RecoveryApprovalGate:
    """
    Recovery Approval Gate — Formal gating for state machine recovery.
    恢复批准门禁 — 状态机恢复的正式门禁。

    Key principles (from DOC-07 § 9):
    - Escalation (moving to more conservative state) = automatic, no approval needed
    - De-escalation (moving to less conservative state) = requires Operator approval
    - Some recoveries require observation period before full restore
    - All actions are audited
    - Thread-safe with lock

    Usage:
        gate = RecoveryApprovalGate(audit_callback=my_audit_func)

        # Submit recovery request
        req = gate.submit_recovery_request(
            recovery_type=RecoveryType.AUTH_UNFREEZE,
            from_state="FROZEN",
            to_state="RESTRICTED",
            requested_by="Operator:nancun",
            reason="Incident resolved, entering 24h observation",
            observation_period_hours=24,
        )

        # Operator approves
        approval = gate.approve_recovery(
            request_id=req.request_id,
            approved_by="Operator:nancun",
            conditions=["No new near-miss during observation"],
            observation_period_hours=24,
        )

        # Check observation status
        status = gate.check_observation_period(req.request_id)
    """

    def __init__(
        self,
        audit_callback: Optional[Callable[[dict], None]] = None,
    ) -> None:
        self._audit_callback = audit_callback
        self._lock = threading.Lock()

        # Storage
        self._requests: dict[str, RecoveryRequest] = {}  # request_id -> RecoveryRequest
        self._approvals: dict[str, RecoveryApproval] = {}  # request_id -> RecoveryApproval

        # Stats
        self._stats = {
            "requests_submitted": 0,
            "requests_approved": 0,
            "requests_rejected": 0,
            "observations_completed": 0,
            "observations_failed": 0,
        }

    # ───────────────────────────────────────────────────────────────────────
    # Request Submission (anybody can submit)
    # ───────────────────────────────────────────────────────────────────────

    def submit_recovery_request(
        self,
        recovery_type: RecoveryType,
        from_state: str,
        to_state: str,
        requested_by: str,
        reason: str,
        observation_period_hours: int = 0,
        evidence: Optional[dict] = None,
    ) -> RecoveryRequest:
        """
        Submit a recovery request.
        提交恢复请求。

        Args:
            recovery_type: Type of recovery (AUTH_UNFREEZE, RISK_DEESCALATE, etc.)
            from_state: Current frozen/restricted state
            to_state: Target recovery state
            requested_by: Name/ID of requester
            reason: Justification
            observation_period_hours: Required observation period (0 = none)
            evidence: Supporting context dict

        Returns:
            RecoveryRequest object (status=PENDING)
        """
        req = RecoveryRequest(
            recovery_type=recovery_type,
            from_state=from_state,
            to_state=to_state,
            requested_by=requested_by,
            reason=reason,
            observation_period_hours=observation_period_hours,
            evidence=evidence or {},
            status=ApprovalStatus.PENDING,
        )

        with self._lock:
            self._requests[req.request_id] = req
            self._stats["requests_submitted"] += 1

        self._emit_audit({
            "event_type": "recovery_request_submitted",
            "request_id": req.request_id,
            "recovery_type": recovery_type.value,
            "from_state": from_state,
            "to_state": to_state,
            "requested_by": requested_by,
            "observation_period_hours": observation_period_hours,
            "timestamp_ms": req.requested_at_ms,
        })

        logger.info(
            "Recovery request %s submitted: %s %s→%s (by %s)",
            req.request_id, recovery_type.value, from_state, to_state, requested_by,
        )

        return req

    # ───────────────────────────────────────────────────────────────────────
    # Approval by Operator (requires Operator role)
    # ───────────────────────────────────────────────────────────────────────

    def approve_recovery(
        self,
        request_id: str,
        approved_by: str,
        conditions: Optional[list] = None,
        observation_period_hours: Optional[int] = None,
        notes: str = "",
    ) -> Optional[RecoveryApproval]:
        """
        Operator approves recovery request.
        运营商批准恢复请求。

        This is the formal approval gate. Only Operator role should call this.

        Args:
            request_id: ID of recovery request
            approved_by: Operator name (should have "Operator" role)
            conditions: List of approval conditions
            observation_period_hours: Override observation period (if None, use request value)
            notes: Approval notes

        Returns:
            RecoveryApproval object if successful, None otherwise
        """
        with self._lock:
            if request_id not in self._requests:
                logger.warning("Approval: request %s not found", request_id)
                return None

            req = self._requests[request_id]

            # Check request is still pending
            if req.status != ApprovalStatus.PENDING:
                logger.warning(
                    "Approval: request %s already %s",
                    request_id, req.status.value,
                )
                return None

            # Determine observation period
            obs_hours = observation_period_hours
            if obs_hours is None:
                obs_hours = req.observation_period_hours

            # Create approval
            now_ms = int(time.time() * 1000)
            approval = RecoveryApproval(
                request_id=request_id,
                approved_by=approved_by,
                approved_at_ms=now_ms,
                conditions=conditions or [],
                observation_start_ms=now_ms if obs_hours > 0 else 0,
                observation_end_ms=(now_ms + obs_hours * 3600 * 1000) if obs_hours > 0 else 0,
                notes=notes,
            )

            self._approvals[request_id] = approval
            req.status = ApprovalStatus.APPROVED
            self._stats["requests_approved"] += 1

        self._emit_audit({
            "event_type": "recovery_approved",
            "request_id": request_id,
            "approved_by": approved_by,
            "approved_at_ms": now_ms,
            "conditions": conditions or [],
            "observation_period_hours": obs_hours,
            "has_observation": obs_hours > 0,
            "observation_end_ms": approval.observation_end_ms,
            "notes": notes,
        })

        logger.info(
            "Recovery approved: %s by %s (obs_hours=%d)",
            request_id, approved_by, obs_hours,
        )

        return approval

    # ───────────────────────────────────────────────────────────────────────
    # Rejection by Operator
    # ───────────────────────────────────────────────────────────────────────

    def reject_recovery(
        self,
        request_id: str,
        rejected_by: str,
        reason: str = "",
    ) -> bool:
        """
        Operator rejects recovery request.
        运营商拒绝恢复请求。

        Args:
            request_id: ID of recovery request
            rejected_by: Operator name
            reason: Rejection reason

        Returns:
            True if rejected successfully, False otherwise
        """
        with self._lock:
            if request_id not in self._requests:
                logger.warning("Rejection: request %s not found", request_id)
                return False

            req = self._requests[request_id]

            if req.status != ApprovalStatus.PENDING:
                logger.warning(
                    "Rejection: request %s already %s",
                    request_id, req.status.value,
                )
                return False

            now_ms = int(time.time() * 1000)
            req.status = ApprovalStatus.REJECTED
            self._stats["requests_rejected"] += 1

        self._emit_audit({
            "event_type": "recovery_rejected",
            "request_id": request_id,
            "rejected_by": rejected_by,
            "reason": reason,
            "timestamp_ms": now_ms,
        })

        logger.info(
            "Recovery rejected: %s by %s (reason: %s)",
            request_id, rejected_by, reason or "not provided",
        )

        return True

    # ───────────────────────────────────────────────────────────────────────
    # Observation Period Checking
    # ───────────────────────────────────────────────────────────────────────

    def check_observation_period(self, request_id: str) -> ObservationPeriodStatus:
        """
        Check observation period status for a recovery request.
        检查恢复请求的观察期状态。

        Some recoveries require a mandatory observation period before
        allowing full restoration. This method checks the status.

        Returns:
            NOT_REQUIRED: no observation period needed
            PENDING: observation period in progress
            COMPLETED: observation period has elapsed
            FAILED: observation period failed (would indicate violation)
        """
        with self._lock:
            if request_id not in self._approvals:
                return ObservationPeriodStatus.NOT_REQUIRED

            approval = self._approvals[request_id]

            if not approval.has_observation_period:
                return ObservationPeriodStatus.NOT_REQUIRED

            if approval.is_observation_complete:
                self._stats["observations_completed"] += 1
                return ObservationPeriodStatus.COMPLETED

            return ObservationPeriodStatus.PENDING

    def mark_observation_failed(self, request_id: str, reason: str = "") -> bool:
        """
        Mark observation period as failed (violation occurred).
        标记观察期失败（违反发生）。

        If a violation occurs during observation period, this marks it as failed
        and may require re-submission of recovery request.

        Args:
            request_id: ID of recovery request
            reason: Failure reason

        Returns:
            True if marked successfully, False otherwise
        """
        with self._lock:
            if request_id not in self._approvals:
                return False

            now_ms = int(time.time() * 1000)
            self._stats["observations_failed"] += 1

        self._emit_audit({
            "event_type": "observation_period_failed",
            "request_id": request_id,
            "reason": reason,
            "timestamp_ms": now_ms,
        })

        logger.warning(
            "Observation period failed for %s: %s",
            request_id, reason or "not specified",
        )

        return True

    # ───────────────────────────────────────────────────────────────────────
    # Query Methods
    # ───────────────────────────────────────────────────────────────────────

    def get_pending_requests(self) -> list[dict]:
        """Get all pending (unapproved) recovery requests / 获取所有待审批恢复请求"""
        with self._lock:
            return [
                req.to_dict()
                for req in self._requests.values()
                if req.status == ApprovalStatus.PENDING
            ]

    def get_approved_requests(self) -> list[dict]:
        """Get all approved recovery requests / 获取所有已批准恢复请求"""
        with self._lock:
            return [
                req.to_dict()
                for req in self._requests.values()
                if req.status == ApprovalStatus.APPROVED
            ]

    def get_request(self, request_id: str) -> Optional[dict]:
        """Get specific recovery request / 获取指定恢复请求"""
        with self._lock:
            if request_id in self._requests:
                return self._requests[request_id].to_dict()
            return None

    def get_approval(self, request_id: str) -> Optional[dict]:
        """Get approval for recovery request / 获取恢复批准"""
        with self._lock:
            if request_id in self._approvals:
                return self._approvals[request_id].to_dict()
            return None

    def get_requests_by_type(self, recovery_type: RecoveryType) -> list[dict]:
        """Get recovery requests of specific type / 获取特定类型的恢复请求"""
        with self._lock:
            return [
                req.to_dict()
                for req in self._requests.values()
                if req.recovery_type == recovery_type
            ]

    def get_pending_observations(self) -> list[dict]:
        """Get requests with pending observation periods / 获取待观察期的请求"""
        with self._lock:
            pending = []
            for req_id, approval in self._approvals.items():
                if approval.has_observation_period and not approval.is_observation_complete:
                    if req_id in self._requests:
                        req_dict = self._requests[req_id].to_dict()
                        req_dict["approval"] = approval.to_dict()
                        pending.append(req_dict)
            return pending

    def get_stats(self) -> dict:
        """Get processing statistics / 获取处理统计"""
        with self._lock:
            return {
                **self._stats,
                "total_requests": len(self._requests),
                "pending_requests": sum(
                    1 for r in self._requests.values()
                    if r.status == ApprovalStatus.PENDING
                ),
                "total_approvals": len(self._approvals),
            }

    # ───────────────────────────────────────────────────────────────────────
    # Audit Emission
    # ───────────────────────────────────────────────────────────────────────

    def _emit_audit(self, event_dict: dict) -> None:
        """Emit audit event / 发送审计事件"""
        if not self._audit_callback:
            return

        try:
            self._audit_callback(event_dict)
        except Exception as e:
            logger.error("Recovery gate audit error: %s", e)
