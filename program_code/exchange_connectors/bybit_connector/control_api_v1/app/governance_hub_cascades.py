"""
Governance Hub Status & Cascade Mixin — get_status, events, and cross-SM cascade handlers.
治理集線器狀態與級聯 Mixin — get_status、事件和跨 SM 級聯處理器。

MODULE_NOTE (EN): Extracted from governance_hub.py (FIX-08 file size).
  Contains get_status(), get_governance_events(), _append_governance_event(),
  and cross-SM cascade callbacks: _on_risk_escalation, _on_reconciliation_mismatch,
  _on_auth_frozen, handle_incident_auth_action, handle_incident_risk_action,
  handle_incident_operator_alert, _auth_permits_scope.
MODULE_NOTE (中): 從 governance_hub.py 提取（FIX-08 文件大小）。
  包含 get_status()、事件方法和跨 SM 級聯回調方法。
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .change_audit_log import ChangeType
from .governance_events import risk_event, recon_event, auth_event, lease_event
from .utils.time_utils import now_ms

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Types (shared with governance_hub.py) / 类型（與 governance_hub.py 共享）
# ═══════════════════════════════════════════════════════════════════════════════

class GovernanceMode(str, Enum):
    """Global governance mode / 全局治理模式"""
    NORMAL = "NORMAL"           # All SMs active / 所有 SM 激活
    RESTRICTED = "RESTRICTED"   # Restricted operations allowed / 允许受限操作
    FROZEN = "FROZEN"           # All operations denied / 拒绝所有操作
    MANUAL_REVIEW = "MANUAL_REVIEW"  # Awaiting operator intervention / 等待操作员介入


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
# Mixin Class / Mixin 類
# ═══════════════════════════════════════════════════════════════════════════════

class GovernanceHubStatusCascadeMixin:
    """
    Mixin providing status query and cross-SM cascade handlers for GovernanceHub.
    為 GovernanceHub 提供狀態查詢和跨 SM 級聯處理器的 Mixin。

    These methods are tightly coupled to GovernanceHub internals (self._lock,
    self._authorization_sm, self._risk_governor_sm, etc.) and are separated
    purely for file size management (FIX-08).
    這些方法與 GovernanceHub 內部緊密耦合，分離純粹為文件大小管理。
    """

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
                    logger.debug("Cross-SM callback error: %s", e)
                with self._lock:
                    self._callback_errors += 1

        # Gather all necessary state under lock in a single shot
        with self._lock:
            timestamp_ms = now_ms()
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
            # 获取授权状态：先读有效授权（ACTIVE/RESTRICTED），再检查待审批
            # Get auth state: read effective (ACTIVE/RESTRICTED), then check pending approvals.
            auth_pending_approval_flag = False
            if self._authorization_sm is not None:
                try:
                    effective_auths = self._authorization_sm.get_effective()
                    if effective_auths:
                        # Prefer live-mode authorization when multiple are active
                        # (e.g. paper still ACTIVE alongside live).
                        # 多個有效授權並存時優先顯示 live 模式授權（如 paper 仍 ACTIVE）。
                        auth = next(
                            (a for a in effective_auths
                             if isinstance(getattr(a, "scope", None), dict)
                             and a.scope.get("mode") == "live"),
                            effective_auths[0],
                        )
                        auth_state = auth.state.value
                        auth_expires_at_ms = auth.expires_at_ms
                        auth_scope = auth.scope
                    else:
                        auth_state = "NONE"
                        # Check for pending approvals so approve endpoint works
                        # 检查是否有待审批授权，确保 approve 端点的 auth_pending_approval 检查正确
                        try:
                            all_auths = self._authorization_sm.list_all()
                            auth_pending_approval_flag = any(
                                a.state.value == "PENDING_APPROVAL" for a in all_auths
                            )
                        except Exception:
                            pass
                except Exception as e:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug("Error reading auth state: %s", e)

            # Get Risk state
            if self._risk_governor_sm is not None:
                try:
                    risk_state = self._risk_governor_sm.get_state()
                    risk_level = int(risk_state.level)
                    risk_level_name = risk_state.level.name
                except Exception as e:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug("Error reading risk state: %s", e)

            # Get Lease counts
            if self._lease_sm is not None:
                try:
                    leases = self._lease_sm.get_all()
                    live_leases = self._lease_sm.get_live()
                    active_leases_count = len(live_leases)
                    total_leases_tracked = len(leases)
                except Exception as e:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug("Error reading lease state: %s", e)

        # Construct status object outside of lock
        status = GovernanceStatus(
            timestamp_ms=timestamp_ms,
            enabled=enabled,
            mode=mode_value,
            auth_state=auth_state,
            auth_expires_at_ms=auth_expires_at_ms,
            auth_scope=auth_scope,
            auth_pending_approval=auth_pending_approval_flag,
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
            # T11.03: Generate correlation_id for entire cascade chain
            import uuid as _uuid
            cascade_correlation_id = str(_uuid.uuid4())
            risk_event_id = None

            with self._lock:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("Risk escalated: %s → %s", old_level, new_level)
                self._incident_count += 1

                # T9A.02: Emit governance event for risk escalation
                try:
                    event = risk_event(
                        level_from=old_level,
                        level_to=new_level,
                        initiator="SYSTEM",
                        reason=f"Automatic risk escalation triggered",
                        correlation_id=cascade_correlation_id,
                    )
                    risk_event_id = event.event_id
                    self._append_governance_event(event.to_dict())
                except Exception as e:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug("Error emitting risk escalation event: %s", e)

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
                            auto_approve=True,
                        )
                    except Exception as e:
                        logger.error("ChangeAuditLog record failed (non-fatal): %s", e)

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
                            logger.debug("Error collecting auth IDs on risk escalation: %s", e)
                        self._callback_errors += 1

                # Risk level 4 (CIRCUIT_BREAKER) or higher → freeze auth
                if new_level >= 4 and self._authorization_sm is not None:
                    try:
                        effective_auths = self._authorization_sm.get_effective()
                        auth_ids_to_freeze = [auth.authorization_id for auth in effective_auths]
                        should_freeze_auth = True
                    except Exception as e:
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug("Error collecting auth IDs for freeze: %s", e)
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
                    # T10.01 + T11.03: Emit auth_event with correlation chain
                    for auth_id in auth_ids_to_restrict:
                        try:
                            evt = auth_event(
                                state_from="ACTIVE",
                                state_to="RESTRICTED",
                                initiator="GovernanceHub",
                                message=f"Auth {auth_id} restricted: risk escalation to level {new_level}",
                                correlation_id=cascade_correlation_id,
                                parent_event_id=risk_event_id,
                            )
                            self._append_governance_event(evt.to_dict())
                        except Exception as _evt_err:
                            pass  # Non-fatal: event emission failure does not block governance action
                except Exception as e:
                    with self._lock:
                        self._callback_errors += 1
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug("Error restricting auth on risk escalation: %s", e)

            if auth_ids_to_freeze:
                try:
                    with self._lock:
                        for auth_id in auth_ids_to_freeze:
                            self._authorization_sm.freeze(
                                auth_id,
                                reason=f"Circuit breaker triggered at risk level {new_level}",
                            )
                        self._invalidate_auth_cache()
                    # T10.01 + T11.03: Emit auth_event with correlation chain
                    for auth_id in auth_ids_to_freeze:
                        try:
                            evt = auth_event(
                                state_from="ACTIVE",
                                state_to="FROZEN",
                                initiator="GovernanceHub",
                                message=f"Auth {auth_id} frozen: circuit breaker at risk level {new_level}",
                                correlation_id=cascade_correlation_id,
                                parent_event_id=risk_event_id,
                            )
                            self._append_governance_event(evt.to_dict())
                        except Exception as _evt_err:
                            pass  # Non-fatal: event emission failure does not block governance action
                    if should_freeze_auth:
                        self._on_auth_frozen(correlation_id=cascade_correlation_id, parent_event_id=risk_event_id)
                except Exception as e:
                    with self._lock:
                        self._callback_errors += 1
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug("Error freezing auth on circuit breaker: %s", e)

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
                        logger.debug("Error sending risk escalation alert: %s", e)

        except Exception as e:
            with self._lock:
                self._callback_errors += 1
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Error in _on_risk_escalation: %s", e)

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
            # T11.03: Generate correlation_id for recon cascade
            import uuid as _uuid
            recon_correlation_id = str(_uuid.uuid4())
            recon_event_id = None

            with self._lock:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("Reconciliation mismatch (%s): %s", severity, details)
                self._incident_count += 1

                # T9A.02: Emit governance event for reconciliation mismatch
                try:
                    event = recon_event(
                        result=severity,
                        initiator="SYSTEM",
                        message=f"Reconciliation mismatch detected: {severity}",
                        correlation_id=recon_correlation_id,
                        **details,
                    )
                    recon_event_id = event.event_id
                    self._append_governance_event(event.to_dict())
                except Exception as e:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug("Error emitting reconciliation event: %s", e)

                # T5.06: Determine escalation level based on severity / 根据严重性确定升级级别
                if severity == "MISMATCH_MINOR":
                    # Minor mismatch - log warning only
                    logger.warning("Reconciliation warning (minor): %s", details)
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
                                logger.debug("Error getting risk level for major mismatch: %s", e)
                            self._callback_errors += 1

                elif severity == "FATAL":
                    # Fatal mismatch → escalate to CIRCUIT_BREAKER + cascade
                    if self._risk_governor_sm is not None:
                        try:
                            from .risk_governor_state_machine import RiskLevel
                            target_risk_level = RiskLevel.CIRCUIT_BREAKER
                        except Exception as e:
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug("Error setting fatal escalation: %s", e)
                            self._callback_errors += 1

                    # Collect auth IDs for freeze
                    if self._authorization_sm is not None:
                        try:
                            effective_auths = self._authorization_sm.get_effective()
                            auth_ids_to_freeze = [auth.authorization_id for auth in effective_auths]
                        except Exception as e:
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug("Error collecting auth IDs for fatal mismatch: %s", e)
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
                                logger.debug("Risk escalated to %s due to %s", target_risk_level.name, severity)
                except Exception as e:
                    with self._lock:
                        self._callback_errors += 1
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug("Error escalating risk for %s: %s", severity, e)

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
                            self._on_auth_frozen(correlation_id=recon_correlation_id, parent_event_id=recon_event_id)
                    # T10.01 + T11.03: Emit auth_event with correlation chain
                    for auth_id in auth_ids_to_freeze:
                        try:
                            evt = auth_event(
                                state_from="ACTIVE",
                                state_to="FROZEN",
                                initiator="GovernanceHub",
                                message=f"Auth {auth_id} frozen: fatal reconciliation mismatch cascade",
                                correlation_id=recon_correlation_id,
                                parent_event_id=recon_event_id,
                            )
                            self._append_governance_event(evt.to_dict())
                        except Exception as _evt_err:
                            pass  # Non-fatal: event emission failure does not block governance action
                except Exception as e:
                    with self._lock:
                        self._callback_errors += 1
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug("Error freezing auth for fatal mismatch: %s", e)

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
                        logger.debug("Error sending fatal reconciliation alert: %s", e)

            # Batch 12: Record reconciliation mismatch to ChangeAuditLog
            # Dedup: only create a new entry if no identical PENDING entry exists.
            # After operator approves/rejects, the entry leaves PENDING state,
            # so a new occurrence of the same issue will create a fresh entry.
            # 去重：仅当不存在相同的 PENDING 条目时才创建新记录。
            # 操作员批准/拒绝后条目离开 PENDING 状态，相同问题再次出现时会创建新条目。
            if self._change_audit_log:
                try:
                    recon_what = f"Reconciliation mismatch detected: {severity}"
                    pending = self._change_audit_log.get_pending_approvals()
                    already_pending = any(p.what == recon_what for p in pending)
                    if already_pending:
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug("Reconciliation mismatch already pending, skipping duplicate")
                    else:
                        self._change_audit_log.record_change(
                            change_type=ChangeType.STATE_CHANGE,
                            who="GovernanceHub",
                            what=recon_what,
                            reason=str(details.get('reason', 'reconciliation_mismatch')),
                            old_value="consistent",
                            new_value="mismatch",
                            auto_approve=True,
                        )
                except Exception as e:
                    logger.warning("ChangeAuditLog record failed for reconciliation mismatch (non-fatal): %s", e)

        except Exception as e:
            with self._lock:
                self._callback_errors += 1
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Error in _on_reconciliation_mismatch: %s", e)

    def _on_auth_frozen(self, correlation_id: str | None = None, parent_event_id: str | None = None) -> None:
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
                            logger.debug("Error collecting leases on auth freeze: %s", e)
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
                    # T10.02 + T11.03: Emit lease_event with correlation chain
                    for lease_id in lease_ids:
                        try:
                            evt = lease_event(
                                state_from="ACTIVE",
                                state_to="REVOKED",
                                lease_id=lease_id,
                                initiator="GovernanceHub",
                                message=f"Lease {lease_id} revoked: authorization frozen cascade",
                                correlation_id=correlation_id,
                                parent_event_id=parent_event_id,
                            )
                            self._append_governance_event(evt.to_dict())
                        except Exception as _evt_err:
                            pass  # Non-fatal: event emission failure does not block governance action

                    # Batch 12: Record auth freeze to ChangeAuditLog
                    if self._change_audit_log:
                        try:
                            self._change_audit_log.record_change(
                                change_type=ChangeType.STATE_CHANGE,
                                who="GovernanceHub",
                                what=f"Authorization frozen: {len(lease_ids)} active leases revoked",
                                reason="Authorization frozen cascade",
                                old_value="ACTIVE",
                                new_value="FROZEN",
                                auto_approve=True,
                            )
                        except Exception as e:
                            logger.warning("ChangeAuditLog record failed for auth freeze (non-fatal): %s", e)
                except Exception as e:
                    with self._lock:
                        self._callback_errors += 1
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug("Error revoking leases on auth freeze: %s", e)

        except Exception as e:
            with self._lock:
                self._callback_errors += 1
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Error in _on_auth_frozen: %s", e)

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

                logger.info("Incident auth action executed: %s", action)
        except Exception as e:
            with self._lock:
                self._callback_errors += 1
            logger.error("Error in handle_incident_auth_action(%s): %s", action, e)

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

                logger.info("Incident risk action executed: %s", action)
        except Exception as e:
            with self._lock:
                self._callback_errors += 1
            logger.error("Error in handle_incident_risk_action(%s): %s", action, e)

    def handle_incident_operator_alert(self, context: dict[str, Any]) -> None:
        """
        Handle operator alerts triggered by IncidentPolicy.
        處理 IncidentPolicy 觸發的運營商警報。

        Args:
            context: Event context dict
        """
        logger.critical(
            "OPERATOR_ALERT: Incident %s severity=%s reason=%s",
            context.get('event_id'), context.get('severity'), context.get('reason_code'),
        )
        # NOTE: Notification integration handled by TelegramAlerter (set_alerter, T8.06).
        # Additional notification channels (Slack, webhook) deferred to future enhancement.

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


