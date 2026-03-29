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

import copy
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

        # Tracking for callbacks
        self._callback_errors = 0
        self._incident_count = 0

        # Lazy initialization flag
        self._initialized = False

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

            # Create audit callbacks
            auth_callback = self._make_audit_callback("authorization")
            risk_callback = self._make_audit_callback("risk_governor")
            lease_callback = self._make_audit_callback("decision_lease")
            recon_callback = self._make_audit_callback("reconciliation")

            # Initialize SMs
            self._authorization_sm = AuthorizationStateMachine(audit_callback=auth_callback)
            self._risk_governor_sm = RiskGovernorStateMachine(audit_callback=risk_callback)
            self._lease_sm = DecisionLeaseStateMachine(audit_callback=lease_callback)
            self._reconciliation_engine = ReconciliationEngine(
                config=ReconciliationConfig(),
                audit_callback=recon_callback,
            )

            # Wire cross-SM callbacks
            self._wire_callbacks()

            self._initialized = True
            logger.info("GovernanceHub initialized with all 4 SMs")
        except Exception as e:
            logger.error(f"Failed to initialize GovernanceHub: {e}", exc_info=True)
            self._enabled = False
            raise

    def _make_audit_callback(self, sm_name: str) -> Callable[[dict[str, Any]], None]:
        """Factory for audit callbacks that persist to files / 审计回调工厂"""
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
            except Exception as e:
                logger.error(f"Audit callback error for {sm_name}: {e}")
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
        except Exception as e:
            logger.warning(f"Failed to wire risk escalation callback: {e}")

    def is_authorized(self) -> bool:
        """
        H0 gate check. Returns False (fail-closed) if disabled or auth not in ACTIVE/RESTRICTED.
        H0 门检。如果禁用或授权不在 ACTIVE/RESTRICTED，返回 False（fail-closed）。

        Returns:
            True if governance permits operations; False otherwise
        """
        if not self._enabled or self._mode == GovernanceMode.FROZEN:
            return False

        if not self._initialized:
            try:
                self._ensure_initialized()
            except Exception:
                return False

        try:
            with self._lock:
                if self._authorization_sm is None:
                    return False

                # Get authorization state
                auth_dict = self._authorization_sm.get_state_dict()
                current_state = auth_dict.get("current_state")

                # Check if in effective state (ACTIVE or RESTRICTED both allow operations)
                effective_states = {"ACTIVE", "RESTRICTED"}
                return current_state in effective_states
        except Exception as e:
            logger.error(f"Error in is_authorized: {e}")
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
                return state.current_level if hasattr(state, "current_level") else None
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

                # Escalate if needed (this is risk governor's responsibility)
                # Metrics interpretation is governor's internal logic
                old_level = self._risk_governor_sm.get_state().current_level
                self._risk_governor_sm.check_and_escalate(metrics)
                new_level = self._risk_governor_sm.get_state().current_level

                if new_level > old_level:
                    self._on_risk_escalation(old_level, new_level)

                return new_level
        except Exception as e:
            logger.error(f"Error in check_risk_and_act: {e}")
            return None

    def acquire_lease(self, intent_id: str, scope: str, ttl_seconds: float = 30.0) -> Optional[str]:
        """
        Acquire a decision lease for a specific intent.
        为特定意图获取决策租约。

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
                if self._lease_sm is None:
                    return None

                # Check if auth permits this scope
                auth_state = self._authorization_sm.get_state_dict()
                if not self._auth_permits_scope(auth_state, scope):
                    logger.warning(f"Authorization does not permit lease scope: {scope}")
                    return None

                # Create lease draft and activate it
                lease_obj = self._lease_sm.create_draft(
                    intent={"intent_id": intent_id, "scope": scope},
                    created_by="GovernanceHub",
                )
                lease_id = lease_obj.lease_id

                # Register and activate
                self._lease_sm.transition(lease_id, "register", actor="GovernanceHub")
                self._lease_sm.transition(lease_id, "activate", actor="GovernanceHub")

                logger.info(f"Lease acquired: {lease_id} for intent {intent_id}")
                return lease_id
        except Exception as e:
            logger.error(f"Error acquiring lease for {intent_id}: {e}")
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

                target_state = "CONSUMED" if consumed else "REVOKED"
                self._lease_sm.transition(lease_id, target_state.lower(), actor="GovernanceHub")

                logger.info(f"Lease released: {lease_id} as {target_state}")
                return True
        except Exception as e:
            logger.error(f"Error releasing lease {lease_id}: {e}")
            return False

    def reconcile(
        self,
        paper_state: dict[str, Any],
        demo_state: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Run reconciliation against demo/exchange state.
        针对 demo/交易所状态运行对账。

        Args:
            paper_state: Local paper trading state
            demo_state: Demo/exchange state (None for demo-only check)

        Returns:
            Reconciliation report dict
        """
        if not self._enabled or not self._initialized:
            return {"ok": False, "reason": "governance_disabled"}

        try:
            with self._lock:
                if self._reconciliation_engine is None:
                    return {"ok": False, "reason": "reconciliation_engine_unavailable"}

                report = self._reconciliation_engine.reconcile(
                    paper_state=paper_state,
                    demo_state=demo_state or paper_state,
                )

                # Check for major mismatches and escalate risk
                if report.get("severity") in ["CRITICAL", "FATAL"]:
                    self._on_reconciliation_mismatch(report["severity"], report)

                logger.info(f"Reconciliation complete: {report.get('result')}")
                return report
        except Exception as e:
            logger.error(f"Error in reconciliation: {e}")
            return {"ok": False, "reason": "reconciliation_error", "error": str(e)}

    def get_status(self) -> GovernanceStatus:
        """
        Get combined governance status for API/GUI.
        获取联合治理状态供 API/GUI 使用。

        Returns:
            GovernanceStatus object
        """
        if not self._initialized:
            try:
                self._ensure_initialized()
            except Exception:
                pass

        with self._lock:
            status = GovernanceStatus(
                timestamp_ms=int(time.time() * 1000),
                enabled=self._enabled,
                mode=self._mode.value,
                callback_errors=self._callback_errors,
                incident_count=self._incident_count,
            )

            # Get Auth state
            if self._authorization_sm is not None:
                try:
                    auth_dict = self._authorization_sm.get_state_dict()
                    status.auth_state = auth_dict.get("current_state")
                    status.auth_expires_at_ms = auth_dict.get("expires_at_ms")
                    status.auth_scope = auth_dict.get("scope", {})
                    status.auth_pending_approval = auth_dict.get("pending_approval", False)
                except Exception as e:
                    logger.warning(f"Error reading auth state: {e}")

            # Get Risk state
            if self._risk_governor_sm is not None:
                try:
                    risk_state = self._risk_governor_sm.get_state()
                    status.risk_level = getattr(risk_state, "current_level", None)
                    status.risk_level_name = getattr(risk_state, "level_name", None)
                    status.risk_escalation_reason = getattr(risk_state, "escalation_reason", None)
                except Exception as e:
                    logger.warning(f"Error reading risk state: {e}")

            # Get Lease counts
            if self._lease_sm is not None:
                try:
                    lease_dict = self._lease_sm.get_all_leases()
                    status.active_leases_count = sum(
                        1 for l in lease_dict.values()
                        if l.get("state") in ["ACTIVE", "BRIDGED"]
                    )
                    status.total_leases_tracked = len(lease_dict)
                except Exception as e:
                    logger.warning(f"Error reading lease state: {e}")

            return status

    def _on_risk_escalation(self, old_level: int, new_level: int) -> None:
        """
        Callback: risk escalated → restrict/freeze auth, revoke leases if severe.
        回调：风险升级 → 限制/冻结授权，如果严重则撤销租约。
        """
        if not self._enabled or not self._initialized:
            return

        try:
            with self._lock:
                logger.warning(f"Risk escalated: {old_level} → {new_level}")
                self._incident_count += 1

                # Risk level 2 (REDUCED) or higher → restrict auth
                if new_level >= 2:
                    try:
                        if self._authorization_sm is not None:
                            auth_dict = self._authorization_sm.get_state_dict()
                            if auth_dict.get("current_state") == "ACTIVE":
                                self._authorization_sm.transition(
                                    auth_dict["auth_id"],
                                    "restrict",
                                    actor="GovernanceHub",
                                    reason=f"Risk escalation to level {new_level}",
                                )
                    except Exception as e:
                        logger.error(f"Error restricting auth on risk escalation: {e}")
                        self._callback_errors += 1

                # Risk level 4 (CIRCUIT_BREAKER) or higher → freeze auth
                if new_level >= 4:
                    try:
                        if self._authorization_sm is not None:
                            auth_dict = self._authorization_sm.get_state_dict()
                            if auth_dict.get("current_state") in ["ACTIVE", "RESTRICTED"]:
                                self._authorization_sm.transition(
                                    auth_dict["auth_id"],
                                    "freeze",
                                    actor="GovernanceHub",
                                    reason=f"Circuit breaker triggered at risk level {new_level}",
                                )
                                self._on_auth_frozen()
                    except Exception as e:
                        logger.error(f"Error freezing auth on circuit breaker: {e}")
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

        except Exception as e:
            logger.error(f"Error in _on_risk_escalation: {e}")
            self._callback_errors += 1

    def _on_reconciliation_mismatch(self, severity: str, details: dict[str, Any]) -> None:
        """
        Callback: reconciliation found mismatch → escalate risk if major.
        回调：对账发现不一致 → 如果重大则升级风险。
        """
        if not self._enabled or not self._initialized:
            return

        try:
            with self._lock:
                logger.warning(f"Reconciliation mismatch ({severity}): {details}")
                self._incident_count += 1

                # MAJOR mismatch → escalate risk
                if severity == "MAJOR":
                    try:
                        if self._risk_governor_sm is not None:
                            self._risk_governor_sm.escalate_for_reason(
                                reason="reconciliation_mismatch_major",
                                actor="GovernanceHub",
                            )
                    except Exception as e:
                        logger.error(f"Error escalating risk for major mismatch: {e}")
                        self._callback_errors += 1

                # FATAL mismatch → freeze auth and pause trading
                if severity == "FATAL":
                    try:
                        if self._authorization_sm is not None:
                            auth_dict = self._authorization_sm.get_state_dict()
                            if auth_dict.get("current_state") in ["ACTIVE", "RESTRICTED"]:
                                self._authorization_sm.transition(
                                    auth_dict["auth_id"],
                                    "freeze",
                                    actor="GovernanceHub",
                                    reason="Fatal reconciliation mismatch",
                                )
                                self._on_auth_frozen()
                        self._mode = GovernanceMode.FROZEN
                    except Exception as e:
                        logger.error(f"Error freezing auth for fatal mismatch: {e}")
                        self._callback_errors += 1

        except Exception as e:
            logger.error(f"Error in _on_reconciliation_mismatch: {e}")
            self._callback_errors += 1

    def _on_auth_frozen(self) -> None:
        """
        Callback: auth frozen → revoke all active leases.
        回调：授权冻结 → 撤销所有活跃租约。
        """
        if not self._enabled or not self._initialized:
            return

        try:
            with self._lock:
                logger.warning("Authorization frozen, revoking all active leases")

                if self._lease_sm is not None:
                    try:
                        lease_dict = self._lease_sm.get_all_leases()
                        for lease_id, lease_obj in lease_dict.items():
                            if lease_obj.get("state") in ["ACTIVE", "BRIDGED"]:
                                self._lease_sm.transition(
                                    lease_id,
                                    "revoke",
                                    actor="GovernanceHub",
                                    reason="Authorization frozen",
                                )
                    except Exception as e:
                        logger.error(f"Error revoking leases on auth freeze: {e}")
                        self._callback_errors += 1

        except Exception as e:
            logger.error(f"Error in _on_auth_frozen: {e}")
            self._callback_errors += 1

    def _auth_permits_scope(self, auth_dict: dict[str, Any], scope: str) -> bool:
        """Check if authorization permits lease scope / 检查授权是否允许租约范围"""
        try:
            if auth_dict.get("current_state") not in ["ACTIVE", "RESTRICTED"]:
                return False

            permitted_scopes = auth_dict.get("scope", {}).get("lease_scopes", [])
            return scope in permitted_scopes if permitted_scopes else True
        except Exception:
            return False


__all__ = ["GovernanceHub", "GovernanceStatus", "GovernanceMode"]
