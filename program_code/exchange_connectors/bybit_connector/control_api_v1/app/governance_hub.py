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

# PARTIALLY DEPRECATED (R-07 + RC-11):
#   Deterministic cascade logic migrated to Rust GovernanceCore.
#   Rust: openclaw_core/src/governance_core.rs (is_authorized, cascading all-or-nothing)
#
#   STILL ACTIVE in Python (12+ importers):
#     - grant_paper_authorization, de_escalation, reconcile
#     - is_authorized (startup reauth), acquire/release_lease
#     - get_status, get_governance_events
#     - All set_*() dependency injection methods
#
#   DEPRECATED (RC-11, no callers):
#     - check_learning_tier_capability, is_enabled, get_risk_level
#     - check_risk_and_act, trigger_risk_upgrade
#
#   DO NOT DELETE — 12+ importers depend on this module.
#   Future: 18/29 governance_routes endpoints can become IPC relay to Rust.

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from .change_audit_log import ChangeAuditLog, ChangeType, ChangeApprovalStatus
from .governance_hub_cascades import (  # FIX-08: types + mixin extracted for file size
    GovernanceHubStatusCascadeMixin,
    GovernanceMode,
    GovernanceStatus,
)
from .recovery_approval_gate import RecoveryApprovalGate
from .governance_events import risk_event, recon_event, auth_event, lease_event
from .utils.time_utils import now_ms

logger = logging.getLogger(__name__)


# GovernanceMode, GovernanceStatus: see governance_hub_cascades.py (FIX-08)


# ═══════════════════════════════════════════════════════════════════════════════
# Governance Hub / 治理集线器
# ═══════════════════════════════════════════════════════════════════════════════

class GovernanceHub(GovernanceHubStatusCascadeMixin):
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

        # P1-2: env var override removed — governance cannot be disabled via environment variable
        self._enabled = enabled
        self._mode = GovernanceMode.NORMAL

        # Initialize all 4 state machines
        self._authorization_sm: Optional[Any] = None
        self._risk_governor_sm: Optional[Any] = None
        self._lease_sm: Optional[Any] = None
        self._reconciliation_engine: Optional[Any] = None
        # _oms_sm removed 2026-04-10: Python OMS deprecated, order tracking moved to Rust DB

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

    def set_audit_pipeline(self, pipeline: 'Any') -> None:
        """
        Set the audit pipeline for SM callbacks.
        設置 SM 回調的審計管道。

        Args:
            pipeline: AuditPipeline instance for persisting audit records to disk.
                      Type: audit_persistence.AuditPipeline (lazy import to avoid circular dep)
        """
        with self._lock:
            self._audit_pipeline = pipeline
            logger.info("Audit pipeline set on GovernanceHub")

    def set_change_audit_log(self, cal: 'ChangeAuditLog') -> None:
        """Inject ChangeAuditLog for WHO/WHEN/APPROVAL tracking / 注入變更審計日誌"""
        with self._lock:
            self._change_audit_log = cal
            logger.info("ChangeAuditLog set on GovernanceHub")

    def set_recovery_gate(self, gate: 'RecoveryApprovalGate') -> None:
        """Inject RecoveryApprovalGate for de-escalation approval / 注入恢復審批門禁"""
        with self._lock:
            self._recovery_gate = gate
            logger.info("RecoveryApprovalGate set on GovernanceHub")

    def set_alerter(self, alerter: 'Any') -> None:
        """
        T8.06: Inject TelegramAlerter for governance event notifications.
        注入 TelegramAlerter 用于治理事件通知。

        Args:
            alerter: TelegramAlerter instance with .send() and .is_enabled property.
                     Type: telegram_alerter.TelegramAlerter (lazy import to avoid circular dep)
        """
        with self._lock:
            self._alerter = alerter
            logger.info("TelegramAlerter set on GovernanceHub")

    def set_learning_tier_gate(self, gate: 'Any') -> None:
        """
        T9A.01: Inject LearningTierGate for analyst agent evolution.
        注入學習等級門控用於分析師代理演進。

        Args:
            gate: LearningTierGate instance with can_*() capability check methods.
                  Type: learning_tier_gate.LearningTierGate (lazy import to avoid circular dep)
        """
        with self._lock:
            self._learning_tier_gate = gate
            logger.info("LearningTierGate set on GovernanceHub")

    def check_learning_tier_capability(self, capability: str) -> bool:
        """
        DEPRECATED (RC-11): No callers found. Rust GovernanceCore handles capability checks.
        已棄用（RC-11）：無調用者。Rust GovernanceCore 處理能力檢查。

        T10.03: Check if the current learning tier permits a given capability.
        检查当前学习层级是否允许指定的能力。

        Args:
            capability: Name of capability method (e.g. "can_discover_patterns")

        Returns:
            True if allowed or gate not configured; False if tier too low.
        """
        gate = self._learning_tier_gate
        if gate is None:
            return True  # Backward-compatible: no gate = no restriction
        try:
            method = getattr(gate, capability, None)
            if method is None:
                return True  # Unknown capability = allow
            return bool(method())
        except Exception as e:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Error checking learning tier capability %s: %s", capability, e)
            return False  # Fail-closed

    def get_learning_tier_status(self) -> dict[str, Any]:
        """
        T10.04: Return current learning tier state for REST exposure.
        返回当前学习层级状态供 REST 端点使用。
        """
        gate = self._learning_tier_gate
        if gate is None:
            return {"available": False, "message": "LearningTierGate not configured"}
        try:
            state = gate.export_state()
            return {
                "available": True,
                "current_tier": state.get("current_tier", "UNKNOWN"),
                "tier_name": state.get("tier_name", "UNKNOWN"),
                "capabilities": {
                    "can_record_observations": gate.can_record_observations(),
                    "can_discover_patterns": gate.can_discover_patterns(),
                    "can_generate_hypotheses": gate.can_generate_hypotheses(),
                    "can_design_experiments": gate.can_design_experiments(),
                    "can_evolve_strategies": gate.can_evolve_strategies(),
                    "can_propose_strategy_variants": gate.can_propose_strategy_variants(),
                    "can_auto_deploy_to_paper": gate.can_auto_deploy_to_paper(),
                    "can_modify_live_config": gate.can_modify_live_config(),
                },
                "promotion_history": state.get("promotion_history", []),
            }
        except Exception as e:
            return {"available": True, "error": str(e)}

    def is_enabled(self) -> bool:
        """
        DEPRECATED (RC-11): No external callers found. Use is_globally_enabled() instead.
        已棄用（RC-11）：無外部調用者。請改用 is_globally_enabled()。

        Returns:
            True if governance is active; False if disabled
        """
        return self._enabled

    def is_globally_enabled(self) -> bool:
        """
        Check if governance is globally enabled. Public accessor for _enabled.
        全局治理是否啟用。_enabled 私有屬性的公開訪問方法。

        This method is the canonical public API for checking the global enabled flag.
        External callers (e.g. governance_routes.py) MUST use this method instead of
        accessing hub._enabled directly to preserve encapsulation and allow future
        refactoring of the internal attribute without breaking callers.

        此方法是檢查全局啟用標誌的標準公開 API。
        外部調用方（如 governance_routes.py）必須使用此方法，而非直接訪問
        hub._enabled，以保持封裝性並允許未來在不破壞調用方的情況下重構內部屬性。

        Returns:
            True if governance is globally active; False if disabled.
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
                    logger.warning("Failed to inject ChangeAuditLog into SMs: %s", e)

            # Wire cross-SM callbacks
            self._wire_callbacks()

            self._initialized = True
            logger.info("GovernanceHub initialized with all 4 SMs")
        except Exception as e:
            logger.error("Failed to initialize GovernanceHub: %s", e, exc_info=True)
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
                    "timestamp_ms": now_ms(),
                    "sm_name": sm_name,
                    **event,
                }
                with open(audit_file, "a") as f:
                    f.write(json.dumps(event_with_meta) + "\n")
                # SECURITY FIX #3: Set restrictive file permissions (0o600 = owner read-write only)
                os.chmod(audit_file, 0o600)
            except Exception as e:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("Audit callback error for %s: %s", sm_name, e)
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
                            logger.debug("Reconciliation warning: %s", report.get('result'))


            except Exception as e:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("Incident callback error for action %s: %s", action, e)
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
            logger.warning("Failed to wire risk escalation callback: %s", e)

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
                    auto_approve=True,
                )
            except Exception as e:
                logger.debug("ChangeAuditLog record failed (non-fatal): %s", e)

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
        # P1-17 FIX: Assign to local variable first to avoid race with _invalidate_auth_cache()
        # setting _cached_auth_state to None between the `is not None` check and the unpack.
        # After local assignment, the tuple reference is stable even if the field is cleared.
        now_ms_val = now_ms()
        _cached = self._cached_auth_state  # single read into local var
        if _cached is not None:
            cached_result, cached_ts_ms = _cached
            if now_ms_val - cached_ts_ms < self._cache_ttl_ms:
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
                    self._cached_auth_state = (result, now_ms())
                except Exception as e:
                    # On re-check failure, return False (fail-closed) and don't cache
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug("Error in authorization check: %s", e)
                    return False

                return result
        except Exception as e:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Error acquiring lock in is_authorized: %s", e)
            return False  # Fail closed

    def get_risk_level(self) -> Optional[int]:
        """
        DEPRECATED (RC-11): No external callers. Rust GovernanceCore provides risk level
        via IPC get_risk_check. Use get_status()["risk"] instead.
        已棄用（RC-11）：無外部調用者。Rust GovernanceCore 通過 IPC get_risk_check 提供風控等級。
        請改用 get_status()["risk"]。

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
            logger.error("Error in get_risk_level: %s", e)
            return None

    def check_risk_and_act(self, metrics: dict[str, Any]) -> Optional[int]:
        """
        DEPRECATED (RC-11): No callers found. Rust GovernanceCore handles risk cascade
        via evaluate_and_cascade() on every tick. This Python method is dead code.
        已棄用（RC-11）：無調用者。Rust GovernanceCore 在每個 tick 通過
        evaluate_and_cascade() 處理風控級聯。此 Python 方法為死代碼。

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
            logger.error("Error in check_risk_and_act: %s", e)
            return None

    def trigger_risk_upgrade(self, event_record: dict[str, Any]) -> None:
        """
        DEPRECATED (RC-11): No callers found. Risk escalation is handled by Rust GovernanceCore
        cascade (risk → auth restrict → auth freeze → lease revoke).
        已棄用（RC-11）：無調用者。風控升級由 Rust GovernanceCore 級聯處理
        （risk → auth restrict → auth freeze → lease revoke）。

        Args:
            event_record: Dict with event_type, risk_level, severity, affected_symbols etc.
        """
        if not self._enabled or not self._initialized:
            logger.warning("GovernanceHub disabled — cannot trigger risk upgrade / 治理禁用 — 无法触发风控升级")
            return

        risk_level = event_record.get("risk_level", "medium")
        event_type = event_record.get("event_type", "unknown")

        try:
            with self._lock:
                if self._risk_governor_sm is None:
                    logger.warning("RiskGovernorSM is None — cannot escalate / 风控状态机为 None — 无法升级")
                    return

                from .risk_governor_state_machine import RiskLevel
                current_state = self._risk_governor_sm.get_state()
                current_level = int(current_state.level)

                # Determine target level based on event risk / 根据事件风险确定目标级别
                # critical → CIRCUIT_BREAKER (4), high → REDUCED (2) or CAUTIOUS (1)
                if risk_level == "critical":
                    target = RiskLevel.CIRCUIT_BREAKER
                elif risk_level == "high":
                    target = RiskLevel.REDUCED if current_level < 2 else RiskLevel(min(current_level + 1, 4))
                else:
                    # medium or low — log only, no escalation
                    logger.info("Guardian event %s risk=%s — no escalation needed / 无需升级", event_type, risk_level)
                    return

                if int(target) <= current_level:
                    logger.info("Risk already at level %d, target %d — no action / 风控已在目标级别", current_level, int(target))
                    return

                # Escalate via risk governor SM / 通过风控状态机升级
                self._risk_governor_sm.escalate_to(
                    target,
                    reason=f"Guardian event: {event_type} (risk={risk_level})",
                    initiator="GuardianAgent",
                )
                logger.info(
                    "SM-04 risk escalated %d → %d by Guardian event %s / SM-04 风控由 Guardian 事件升级",
                    current_level, int(target), event_type,
                )

                # Record governance event / 记录治理事件
                try:
                    from .governance_events import risk_event
                    ev = risk_event(
                        level_from=current_level,
                        level_to=int(target),
                        initiator="GuardianAgent",
                        reason=f"Event: {event_type}, risk_level: {risk_level}",
                    )
                    self._append_governance_event(ev.to_dict())
                except Exception as e:
                    # Log governance event append failure (non-blocking audit trail)
                    logger.warning("Failed to record governance event for risk escalation: %s", e)

        except Exception as e:
            logger.error("trigger_risk_upgrade error: %s / 触发风控升级错误: %s", e, e)

    def grant_paper_authorization(
        self,
        ttl_hours: int = 24,
        max_position_usd: float = 10_000.0,
    ) -> bool:
        """
        Auto-grant paper trading authorization (DRAFT → PENDING_APPROVAL → ACTIVE).
        自动批准纸盘交易授权（DRAFT → PENDING_APPROVAL → ACTIVE）。

        Paper trading carries zero real financial risk, so authorization is auto-approved
        by the system without requiring Operator manual approval.
        纸盘交易不涉及真实资金风险，因此系统自动批准，无需操作员手动审批。

        Safe to call multiple times — skips if an ACTIVE authorization already exists.
        可安全多次调用 — 如果 ACTIVE 授权已存在则跳过。

        Args:
            ttl_hours: Authorization TTL in hours (default 24h) / 授权有效期（小时，默认 24h）
            max_position_usd: Per-position USD ceiling for this authorization scope.
                Callers should pass RiskConfig.limits.max_order_notional_usdt (from Rust) when
                available; falls back to 10 000 USD. Only informational — real enforcement is
                in the Rust engine.
                單筆倉位 USD 上限（授权 scope 展示用）。呼叫方應傳入 Rust
                RiskConfig.limits.max_order_notional_usdt；不可用時回退為 10 000。
                僅供展示，真實執行由 Rust 引擎強制。

        Returns:
            True if authorization is ACTIVE after call; False on any failure (never raises)
            调用后授权为 ACTIVE 则返回 True；任何失败返回 False（永不抛出异常）
        """
        # Guard: hub must be initialized / 前置检查：Hub 必须已初始化
        if self._authorization_sm is None or not self._initialized:
            logger.warning(
                "grant_paper_authorization: hub not ready — skipping / 纸盘授权：Hub 未就绪 — 跳过"
            )
            return False

        try:
            with self._lock:
                # Skip if already ACTIVE — idempotent call / 如果已 ACTIVE 则跳过（幂等）
                effective_auths = self._authorization_sm.get_effective()
                if effective_auths:
                    logger.debug(
                        "grant_paper_authorization: ACTIVE auth already exists — no-op / 已有 ACTIVE 授权 — 跳过"
                    )
                    return True

                # Step 1: Create DRAFT authorization with paper-only scope
                # 步骤 1：创建仅限纸盘的 DRAFT 授权
                import time as _time
                paper_scope = {
                    "mode": "paper_only",
                    "execution": ["paper_submit"],
                    "max_position_usd": max_position_usd,
                    "auto_approved": True,
                }
                # expires_at_ms: current time + ttl_hours in milliseconds
                # 到期时间：当前时间 + ttl_hours（毫秒）
                expires_at_ms = int((_time.time() + ttl_hours * 3600) * 1000)
                auth_obj = self._authorization_sm.create_draft(
                    title="Paper Trading Auto-Authorization / 纸盘交易自动授权",
                    scope=paper_scope,
                    created_by="system_paper_auto",
                    description="Auto-granted on paper session start. No real funds at risk. / 纸盘 session 启动时自动授权，无真实资金风险。",
                    expires_at_ms=expires_at_ms,
                )
                auth_id = auth_obj.authorization_id

                # Step 2: Submit (DRAFT → PENDING_APPROVAL)
                # 步骤 2：提交（DRAFT → PENDING_APPROVAL）
                self._authorization_sm.submit_for_approval(auth_id)

                # Step 3: Auto-approve (PENDING_APPROVAL → ACTIVE)
                # 步骤 3：自动批准（PENDING_APPROVAL → ACTIVE）
                self._authorization_sm.approve(
                    auth_id,
                    approved_by="system_paper_auto",
                    reason="Paper trading carries zero real-funds risk; auto-approved by system. / 纸盘无真实资金风险，系统自动批准。",
                )

                # P3-TECH-3: Invalidate cache inside the lock so is_authorized() picks up
                # the new ACTIVE auth immediately with no stale-cache window.
                # 使缓存失效移入 lock 內，讓 is_authorized() 立即感知新 ACTIVE 授权（無短暫舊快取視窗）
                # RLock is reentrant — safe to call _invalidate_auth_cache() here.
                self._invalidate_auth_cache()

            logger.info(
                "Paper trading authorization auto-granted (id=%s, ttl=%dh) / "
                "纸盘交易授权已自动批准（id=%s，有效期=%dh）",
                auth_id, ttl_hours, auth_id, ttl_hours,
            )
            return True

        except Exception as e:
            logger.error(
                "grant_paper_authorization failed: %s / 纸盘授权失败: %s", e, e
            )
            return False

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
                        logger.debug("Authorization does not permit lease scope: %s", scope)
                    return None

                # Create lease draft and activate it (all within lock)
                # TTL close-loop: set expires_at_ms so ExpiryGuardian can auto-EXPIRE
                # TTL 閉環：設定 expires_at_ms，讓 ExpiryGuardian 可自動 EXPIRE
                now_ms_val = now_ms()
                expires_at_ms = now_ms_val + int(ttl_seconds * 1000)
                lease_obj = self._lease_sm.create_draft(
                    intent={"intent_id": intent_id, "scope": scope},
                    created_by="GovernanceHub",
                    expires_at_ms=expires_at_ms,
                )
                lease_id = lease_obj.lease_id

                # Register and activate
                self._lease_sm.register(lease_id)
                self._lease_sm.activate(lease_id)

                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("Lease acquired: %s for intent %s", lease_id, intent_id)
                return lease_id
        except Exception as e:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Error acquiring lease for %s: %s", intent_id, e)
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
                    logger.debug("Lease released: %s as %s", lease_id, 'CONSUMED' if consumed else 'REVOKED')
                return True
        except Exception as e:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Error releasing lease %s: %s", lease_id, e)
            return False

    def get_lease(self, lease_id: str) -> Any:
        """查詢指定 ID 的 Decision Lease（P3-TECH-1）。
        Returns the lease object, or None if not found or hub not ready.
        Query a specific Decision Lease by ID without accessing private SM.
        """
        with self._lock:
            if self._lease_sm is None:
                return None
            return self._lease_sm.get(lease_id)

    def drive_lease_expiry(self) -> list:
        """驅動 lease 到期狀態機，返回已過期的 lease ID 列表（P3-TECH-1）。
        Drive the lease state machine expiry check without accessing private SM.
        Returns list of expired lease IDs, or empty list if hub not ready.
        """
        with self._lock:
            if self._lease_sm is None:
                return []
            return self._lease_sm.check_expiry()

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

        # T10.03: LearningTierGate enforcement — de-escalation requires L4+ (can_evolve_strategies)
        if not self.check_learning_tier_capability("can_evolve_strategies"):
            logger.warning("De-escalation request denied: learning tier too low for %s", requested_by)
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
                        logger.debug("De-escalation target %s must be lower than current %s", target_level, current_level)
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
                    logger.debug("De-escalation request submitted: %s", req.request_id)
                return req.request_id

        except Exception as e:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Error submitting de-escalation request: %s", e)
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
                        logger.debug("Request %s not found", request_id)
                    return False

                # Approve the recovery
                approval = self._recovery_gate.approve_recovery(
                    request_id=request_id,
                    approved_by=approved_by,
                )

                if approval is None:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug("Failed to approve recovery %s", request_id)
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
                                auto_approve=True,
                            )
                        except Exception as e:
                            logger.error("Failed to record change audit: %s", e)

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
                                logger.debug("Error sending de-escalation approval alert: %s", e)

                    logger.info("De-escalation approved and executed for request %s", request_id)
                    return True

                except Exception as e:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug("Error executing de-escalation: %s", e)
                    return False

        except Exception as e:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Error approving de-escalation: %s", e)
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
                remote_state=demo_state or paper_state,
            )

            # Convert dataclass to dict for downstream consumers
            report_dict = report.to_dict() if hasattr(report, "to_dict") else report

            # Check for major mismatches and escalate risk
            if report.critical_count > 0 if hasattr(report, "critical_count") else False:
                severity = "CRITICAL"
                self._on_reconciliation_mismatch(severity, report_dict)

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Reconciliation complete: %s", report_dict.get("overall_result", "unknown"))
            return report_dict
        except Exception as e:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Error in reconciliation: %s", e)
            return {"ok": False, "reason": "reconciliation_error", "error": str(e)}


    # get_status, events, cascades, incident handlers: see GovernanceHubStatusCascadeMixin
    # in governance_hub_cascades.py (FIX-08 file size split).

__all__ = ["GovernanceHub", "GovernanceStatus", "GovernanceMode"]
