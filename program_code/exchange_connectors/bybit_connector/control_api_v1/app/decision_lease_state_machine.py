"""
Decision Lease State Machine — SM-02 Governance Specification Implementation
决策租约状态机 — SM-02 治理规范实现

MODULE_NOTE (中文):
  本模块实现 SM-02 定义的完整决策租约状态机：
  - 9 个正式状态：DRAFT, REGISTERED, ACTIVE, BRIDGED, FROZEN, REVOKED, EXPIRED, REJECTED, CONSUMED
  - 20+ 条合法迁移（含守卫条件）
  - 明确禁止的迁移（终态回流、跳过注册、跳过活跃直接桥接）
  - 自动迁移 vs 人工审批区分
  - 每次迁移生成 lease_transition 审计对象（SM-02 §11）
  - 过期守护（基于 expires_at 自动触发 EXPIRED）
  - Lease 不是订单、不是风险批准、不是执行状态

MODULE_NOTE (English):
  Implements the full Decision Lease State Machine per SM-02 governance spec:
  - 9 formal states: DRAFT, REGISTERED, ACTIVE, BRIDGED, FROZEN, REVOKED, EXPIRED, REJECTED, CONSUMED
  - 20+ valid transitions (with guard conditions)
  - Explicitly forbidden transitions (terminal backflow, skip registration, skip active)
  - Auto vs manual-approval distinction
  - Each transition emits a lease_transition audit object (SM-02 §11)
  - Expiry guardian (auto-triggers EXPIRED based on expires_at)
  - Lease is NOT an order, NOT a risk approval, NOT an execution state

Safety invariant:
  - Terminal states (REVOKED, EXPIRED, REJECTED, CONSUMED) are irreversible
  - BRIDGED must close to terminal — cannot linger indefinitely
  - Expansion (wider scope / re-activation) requires governance approval
  - GUI / Learning / Strategy layers CANNOT directly modify Lease state
  - Lease ACTIVE ≠ execution; BRIDGED ≠ order submitted
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# States / 状态 (SM-02 §3)
# ═══════════════════════════════════════════════════════════════════════════════

class LeaseState(str, Enum):
    """SM-02 §3: 9 formal Decision Lease states / 9 个正式租约状态"""
    DRAFT = "DRAFT"
    REGISTERED = "REGISTERED"
    ACTIVE = "ACTIVE"
    BRIDGED = "BRIDGED"
    FROZEN = "FROZEN"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"
    CONSUMED = "CONSUMED"


# Terminal states — no transitions OUT (SM-02 §4.6-4.9, §8.1)
TERMINAL_STATES = frozenset({
    LeaseState.REVOKED, LeaseState.EXPIRED,
    LeaseState.REJECTED, LeaseState.CONSUMED,
})

# States where Lease is "live" (usable in governance chain)
LIVE_STATES = frozenset({
    LeaseState.REGISTERED, LeaseState.ACTIVE, LeaseState.BRIDGED,
})

# States where Lease can be bridged downstream
BRIDGEABLE_STATES = frozenset({LeaseState.ACTIVE})


# ═══════════════════════════════════════════════════════════════════════════════
# Events / 事件 (SM-02 §5)
# ═══════════════════════════════════════════════════════════════════════════════

class LeaseEvent(str, Enum):
    """SM-02 §5: Formal trigger events / 正式触发事件"""
    DRAFT_CREATED = "lease_draft_created"
    REGISTRATION_ACCEPTED = "lease_registration_accepted"
    REGISTRATION_REJECTED = "lease_registration_rejected"
    ACTIVATION_WINDOW_OPEN = "lease_activation_window_open"
    BRIDGE_APPROVED = "lease_bridge_approved"
    BRIDGE_REJECTED = "lease_bridge_rejected"
    FREEZE_REQUESTED = "lease_freeze_requested"
    REVOKE_REQUESTED = "lease_revoke_requested"
    INVALIDATED = "lease_invalidated"
    EXPIRED_BY_TIME = "lease_expired_by_time"
    CONSUMED_BY_EXECUTION = "lease_consumed_by_execution_flow"
    AUTHORIZATION_REVOKED = "authorization_scope_revoked"
    INCIDENT_FREEZE = "incident_freeze_applied"
    RECOVERY_APPROVED = "lease_recovery_approved"


class LeaseInitiator(str, Enum):
    """SM-02 §11: Who can initiate transitions / 迁移发起者"""
    I_CONTROL_PLANE = "I"  # Decision Lease Control Plane
    OPERATOR = "Operator"
    AUTHORIZATION_GOVERNANCE = "AuthorizationGovernance"
    INCIDENT_POLICY = "IncidentPolicy"
    EXECUTION_CLOSURE_FLOW = "ExecutionClosureFlow"
    EXPIRY_GUARDIAN = "ExpiryGuardian"
    RISK_GOVERNOR = "RiskGovernor"


# ═══════════════════════════════════════════════════════════════════════════════
# Transition Rules / 迁移规则 (SM-02 §6-7)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class LeaseTransitionRule:
    from_state: LeaseState
    to_state: LeaseState
    requires_approval: bool
    allowed_initiators: frozenset[LeaseInitiator]
    description: str = ""


LEASE_TRANSITION_RULES: dict[tuple[LeaseState, LeaseState], LeaseTransitionRule] = {}


def _reg(from_s: LeaseState, to_s: LeaseState, approval: bool,
         initiators: frozenset[LeaseInitiator], desc: str = "") -> None:
    LEASE_TRANSITION_RULES[(from_s, to_s)] = LeaseTransitionRule(
        from_state=from_s, to_state=to_s,
        requires_approval=approval,
        allowed_initiators=initiators,
        description=desc,
    )


_I_OP = frozenset({LeaseInitiator.I_CONTROL_PLANE, LeaseInitiator.OPERATOR})
_GOV = frozenset({LeaseInitiator.I_CONTROL_PLANE, LeaseInitiator.OPERATOR,
                   LeaseInitiator.AUTHORIZATION_GOVERNANCE, LeaseInitiator.INCIDENT_POLICY})
_FREEZE = frozenset({LeaseInitiator.OPERATOR, LeaseInitiator.INCIDENT_POLICY,
                      LeaseInitiator.AUTHORIZATION_GOVERNANCE, LeaseInitiator.I_CONTROL_PLANE})
_REVOKE = frozenset({LeaseInitiator.OPERATOR, LeaseInitiator.AUTHORIZATION_GOVERNANCE,
                      LeaseInitiator.INCIDENT_POLICY, LeaseInitiator.I_CONTROL_PLANE})
_EXPIRY = frozenset({LeaseInitiator.EXPIRY_GUARDIAN, LeaseInitiator.I_CONTROL_PLANE})
_RECOVERY = frozenset({LeaseInitiator.OPERATOR, LeaseInitiator.I_CONTROL_PLANE})
_EXECUTION = frozenset({LeaseInitiator.EXECUTION_CLOSURE_FLOW, LeaseInitiator.I_CONTROL_PLANE})
_RISK_GOV = frozenset({LeaseInitiator.RISK_GOVERNOR, LeaseInitiator.I_CONTROL_PLANE,
                        LeaseInitiator.OPERATOR})

# §7.1 Draft acceptance phase / 草案接纳阶段
_reg(LeaseState.DRAFT, LeaseState.REGISTERED, False, _I_OP,
     "Accept draft into formal registry / 接纳草案为正式控制对象")
_reg(LeaseState.DRAFT, LeaseState.REJECTED, False, _I_OP,
     "Reject draft / 拒绝草案")

# §7.2 Registration to activation / 注册到激活
_reg(LeaseState.REGISTERED, LeaseState.ACTIVE, False, _I_OP,
     "Activate registered lease / 激活已注册租约")
_reg(LeaseState.REGISTERED, LeaseState.FROZEN, False, _FREEZE,
     "Freeze registered lease / 冻结已注册租约")
_reg(LeaseState.REGISTERED, LeaseState.REVOKED, True, _REVOKE,
     "Revoke registered lease / 撤销已注册租约")
_reg(LeaseState.REGISTERED, LeaseState.EXPIRED, False, _EXPIRY,
     "Registered lease expires / 已注册租约过期")
_reg(LeaseState.REGISTERED, LeaseState.REJECTED, False, _GOV,
     "Post-validation rejection / 后置校验拒绝")

# §7.3 Active to downstream / 活跃到下游
_reg(LeaseState.ACTIVE, LeaseState.BRIDGED, False, _RISK_GOV,
     "Bridge to downstream governance / 桥接至下游治理链")
_reg(LeaseState.ACTIVE, LeaseState.FROZEN, False, _FREEZE,
     "Freeze active lease / 冻结活跃租约")
_reg(LeaseState.ACTIVE, LeaseState.REVOKED, True, _REVOKE,
     "Revoke active lease / 撤销活跃租约")
_reg(LeaseState.ACTIVE, LeaseState.EXPIRED, False, _EXPIRY,
     "Active lease expires / 活跃租约过期")
_reg(LeaseState.ACTIVE, LeaseState.REJECTED, False, _GOV,
     "Post-risk rejection / 后置风险拒绝")

# §7.4 Frozen recovery & termination / 冻结后恢复与终止
_reg(LeaseState.FROZEN, LeaseState.REGISTERED, True, _RECOVERY,
     "Unfreeze to registered (awaiting re-activation) / 解冻至已注册")
_reg(LeaseState.FROZEN, LeaseState.ACTIVE, True, _RECOVERY,
     "Unfreeze to active (conditions still met) / 解冻至活跃")
_reg(LeaseState.FROZEN, LeaseState.REVOKED, True, _REVOKE,
     "Revoke frozen lease / 撤销已冻结租约")
_reg(LeaseState.FROZEN, LeaseState.EXPIRED, False, _EXPIRY,
     "Frozen lease expires / 已冻结租约过期")

# §7.5 Bridged closure / 桥接后闭合
_reg(LeaseState.BRIDGED, LeaseState.CONSUMED, False, _EXECUTION,
     "Execution closure — lease consumed / 执行闭环 — 租约已消费")
_reg(LeaseState.BRIDGED, LeaseState.REVOKED, True, _REVOKE,
     "Revoke bridged lease (before irreversible closure) / 撤销已桥接租约")

# ═══════════════════════════════════════════════════════════════════════════════
# Forbidden Transitions / 禁止的迁移 (SM-02 §8)
# ═══════════════════════════════════════════════════════════════════════════════

FORBIDDEN_TRANSITIONS: frozenset[tuple[LeaseState, LeaseState]] = frozenset({
    # §8.1 Terminal backflow / 终态回流
    (LeaseState.REVOKED, LeaseState.ACTIVE),
    (LeaseState.REVOKED, LeaseState.BRIDGED),
    (LeaseState.EXPIRED, LeaseState.ACTIVE),
    (LeaseState.EXPIRED, LeaseState.BRIDGED),
    (LeaseState.REJECTED, LeaseState.REGISTERED),
    (LeaseState.REJECTED, LeaseState.ACTIVE),
    (LeaseState.CONSUMED, LeaseState.ACTIVE),
    (LeaseState.CONSUMED, LeaseState.BRIDGED),
    # §8.2 Skip registration / 跳过注册
    (LeaseState.DRAFT, LeaseState.ACTIVE),
    (LeaseState.DRAFT, LeaseState.BRIDGED),
    (LeaseState.DRAFT, LeaseState.CONSUMED),
    # §8.3 Skip active directly to bridged / 跳过活跃直接桥接
    (LeaseState.REGISTERED, LeaseState.BRIDGED),
})


# ═══════════════════════════════════════════════════════════════════════════════
# Lease Object / 租约对象
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class DecisionLeaseObject:
    """
    SM-02 §2: A formal governance permit for a controlled trading intent.
    受控交易意图的正式治理许可对象。
    """
    lease_id: str = ""
    state: LeaseState = LeaseState.DRAFT
    version: int = 1
    created_at_ms: int = 0
    updated_at_ms: int = 0

    # Time window / 时间窗口 (SM-02 §12)
    valid_from_ms: int | None = None
    expires_at_ms: int | None = None

    # Intent definition / 意图定义
    intent: dict[str, Any] = field(default_factory=dict)
    # e.g. {"direction": "long", "symbol": "BTCUSDT", "category": "linear",
    #        "target_qty": 0.01, "confidence": 0.72, "strategy": "momentum"}

    # Source / 来源
    source_pipeline_stage: str = ""  # e.g. "H5"
    source_deliberation_id: str = ""
    created_by: str = ""

    # Governance metadata / 治理元数据
    registered_by: str | None = None
    activated_by: str | None = None
    bridged_by: str | None = None
    consumed_by: str | None = None
    freeze_reason: str = ""
    revoke_reason: str = ""
    rejection_reason: str = ""

    # Risk governance / 风控治理
    risk_decision_ref: str | None = None  # Reference to Risk Governor decision

    # Transition history / 迁移历史
    transitions: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.lease_id:
            self.lease_id = f"lease:{uuid.uuid4().hex[:12]}"
        if not self.created_at_ms:
            self.created_at_ms = int(time.time() * 1000)
            self.updated_at_ms = self.created_at_ms

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def is_live(self) -> bool:
        return self.state in LIVE_STATES

    @property
    def is_bridgeable(self) -> bool:
        return self.state in BRIDGEABLE_STATES

    @property
    def is_expired_by_time(self) -> bool:
        if self.expires_at_ms is None:
            return False
        return int(time.time() * 1000) > self.expires_at_ms

    @property
    def is_within_valid_window(self) -> bool:
        now = int(time.time() * 1000)
        if self.valid_from_ms and now < self.valid_from_ms:
            return False
        if self.expires_at_ms and now > self.expires_at_ms:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "state": self.state.value,
            "version": self.version,
            "created_at_ms": self.created_at_ms,
            "updated_at_ms": self.updated_at_ms,
            "valid_from_ms": self.valid_from_ms,
            "expires_at_ms": self.expires_at_ms,
            "intent": self.intent,
            "source_pipeline_stage": self.source_pipeline_stage,
            "created_by": self.created_by,
            "is_terminal": self.is_terminal,
            "is_live": self.is_live,
            "is_bridgeable": self.is_bridgeable,
            "transition_count": len(self.transitions),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DecisionLeaseObject:
        return cls(
            lease_id=d.get("lease_id", ""),
            state=LeaseState(d.get("state", "DRAFT")),
            version=d.get("version", 1),
            created_at_ms=d.get("created_at_ms", 0),
            updated_at_ms=d.get("updated_at_ms", 0),
            valid_from_ms=d.get("valid_from_ms"),
            expires_at_ms=d.get("expires_at_ms"),
            intent=d.get("intent", {}),
            source_pipeline_stage=d.get("source_pipeline_stage", ""),
            source_deliberation_id=d.get("source_deliberation_id", ""),
            created_by=d.get("created_by", ""),
            registered_by=d.get("registered_by"),
            activated_by=d.get("activated_by"),
            bridged_by=d.get("bridged_by"),
            consumed_by=d.get("consumed_by"),
            freeze_reason=d.get("freeze_reason", ""),
            revoke_reason=d.get("revoke_reason", ""),
            rejection_reason=d.get("rejection_reason", ""),
            risk_decision_ref=d.get("risk_decision_ref"),
            transitions=d.get("transitions", []),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Transition Record / 迁移记录 (SM-02 §11)
# ═══════════════════════════════════════════════════════════════════════════════

def _build_lease_transition_record(
    lease: DecisionLeaseObject,
    to_state: LeaseState,
    event: LeaseEvent,
    initiator: LeaseInitiator,
    reason_codes: list[str] | None = None,
    approved_by: str | None = None,
) -> dict[str, Any]:
    now_ms = int(time.time() * 1000)
    tid = f"ltx:{uuid.uuid4().hex[:12]}"
    return {
        "transition_id": tid,
        "lease_id": lease.lease_id,
        "previous_status": lease.state.value,
        "next_status": to_state.value,
        "trigger_event_type": event.value,
        "trigger_event_id": f"levt:{uuid.uuid4().hex[:8]}",
        "initiated_by": initiator.value,
        "transition_reason_codes": reason_codes or [],
        "approval_required": LEASE_TRANSITION_RULES.get(
            (lease.state, to_state),
            LeaseTransitionRule(lease.state, to_state, False, frozenset())
        ).requires_approval,
        "approved_by": approved_by,
        "effective_at_ms": now_ms,
        "audit_event_ref": f"laud:{hashlib.sha256(tid.encode()).hexdigest()[:16]}",
        "version_before": lease.version,
        "version_after": lease.version + 1,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Errors / 异常
# ═══════════════════════════════════════════════════════════════════════════════

class LeaseError(Exception):
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# Decision Lease State Machine / 决策租约状态机
# ═══════════════════════════════════════════════════════════════════════════════

class DecisionLeaseStateMachine:
    """
    Core state machine for Decision Lease lifecycle management.
    决策租约生命周期管理核心状态机。

    Thread-safe. All mutations go through transition().
    线程安全。所有变更通过 transition() 执行。
    """

    def __init__(self, audit_callback: Callable[[dict[str, Any]], None] | None = None) -> None:
        self._lock = threading.Lock()
        self._leases: dict[str, DecisionLeaseObject] = {}
        self._audit_callback = audit_callback

    # ── Create / 创建 ──

    def create_draft(
        self,
        *,
        intent: dict[str, Any],
        created_by: str,
        source_pipeline_stage: str = "H5",
        source_deliberation_id: str = "",
        valid_from_ms: int | None = None,
        expires_at_ms: int | None = None,
    ) -> DecisionLeaseObject:
        lease = DecisionLeaseObject(
            intent=intent,
            created_by=created_by,
            source_pipeline_stage=source_pipeline_stage,
            source_deliberation_id=source_deliberation_id,
            valid_from_ms=valid_from_ms,
            expires_at_ms=expires_at_ms,
        )
        record = _build_lease_transition_record(
            lease, LeaseState.DRAFT, LeaseEvent.DRAFT_CREATED,
            LeaseInitiator.I_CONTROL_PLANE, reason_codes=["initial_draft"],
        )
        record["previous_status"] = "NONE"
        lease.transitions.append(record)

        with self._lock:
            self._leases[lease.lease_id] = lease

        self._emit_audit(record)
        logger.info("Lease draft created: %s / 租约草案已创建", lease.lease_id)
        return lease

    # ── Core Transition / 核心迁移 ──

    def transition(
        self,
        lease_id: str,
        to_state: LeaseState,
        *,
        event: LeaseEvent,
        initiator: LeaseInitiator,
        reason_codes: list[str] | None = None,
        approved_by: str | None = None,
        reason: str = "",
    ) -> DecisionLeaseObject:
        with self._lock:
            lease = self._leases.get(lease_id)
            if lease is None:
                raise LeaseError(f"Lease not found: {lease_id} / 租约不存在")

            from_state = lease.state

            # Guard 1: Terminal states
            if from_state in TERMINAL_STATES:
                raise LeaseError(
                    f"Cannot transition from terminal state {from_state.value} / "
                    f"不可从终态 {from_state.value} 迁出"
                )

            # Guard 2: Forbidden
            if (from_state, to_state) in FORBIDDEN_TRANSITIONS:
                raise LeaseError(
                    f"Forbidden transition: {from_state.value} → {to_state.value} "
                    f"(SM-02 §8) / 禁止迁移"
                )

            # Guard 3: Valid table
            rule = LEASE_TRANSITION_RULES.get((from_state, to_state))
            if rule is None:
                raise LeaseError(
                    f"Invalid transition: {from_state.value} → {to_state.value} "
                    f"(not in transition table) / 非法迁移"
                )

            # Guard 4: Initiator
            if initiator not in rule.allowed_initiators:
                raise LeaseError(
                    f"Initiator {initiator.value} not allowed for "
                    f"{from_state.value} → {to_state.value} / 发起者不被允许"
                )

            # Guard 5: Approval
            if rule.requires_approval and not approved_by:
                raise LeaseError(
                    f"Transition {from_state.value} → {to_state.value} requires "
                    f"approval / 需要审批"
                )

            # Execute
            record = _build_lease_transition_record(
                lease, to_state, event, initiator,
                reason_codes=reason_codes, approved_by=approved_by,
            )

            lease.state = to_state
            lease.version += 1
            lease.updated_at_ms = int(time.time() * 1000)
            lease.transitions.append(record)

            # Update metadata
            if to_state == LeaseState.REGISTERED:
                lease.registered_by = initiator.value
            elif to_state == LeaseState.ACTIVE:
                lease.activated_by = initiator.value
            elif to_state == LeaseState.BRIDGED:
                lease.bridged_by = initiator.value
            elif to_state == LeaseState.CONSUMED:
                lease.consumed_by = initiator.value
            elif to_state == LeaseState.FROZEN:
                lease.freeze_reason = reason
            elif to_state == LeaseState.REVOKED:
                lease.revoke_reason = reason
            elif to_state == LeaseState.REJECTED:
                lease.rejection_reason = reason

            result = copy.deepcopy(lease)

        self._emit_audit(record)
        logger.info("Lease transition: %s %s → %s / 租约迁移",
                     lease_id, from_state.value, to_state.value)
        return result

    # ── Convenience Methods / 便捷方法 ──

    def register(self, lease_id: str) -> DecisionLeaseObject:
        """DRAFT → REGISTERED"""
        return self.transition(
            lease_id, LeaseState.REGISTERED,
            event=LeaseEvent.REGISTRATION_ACCEPTED,
            initiator=LeaseInitiator.I_CONTROL_PLANE,
            reason_codes=["registration_accepted"],
        )

    def reject(self, lease_id: str, *, reason: str = "") -> DecisionLeaseObject:
        """DRAFT/REGISTERED/ACTIVE → REJECTED"""
        return self.transition(
            lease_id, LeaseState.REJECTED,
            event=LeaseEvent.REGISTRATION_REJECTED,
            initiator=LeaseInitiator.I_CONTROL_PLANE,
            reason=reason, reason_codes=["rejected"],
        )

    def activate(self, lease_id: str) -> DecisionLeaseObject:
        """REGISTERED → ACTIVE"""
        return self.transition(
            lease_id, LeaseState.ACTIVE,
            event=LeaseEvent.ACTIVATION_WINDOW_OPEN,
            initiator=LeaseInitiator.I_CONTROL_PLANE,
            reason_codes=["activation_window_open"],
        )

    def bridge(self, lease_id: str, *, risk_decision_ref: str = "") -> DecisionLeaseObject:
        """ACTIVE → BRIDGED"""
        result = self.transition(
            lease_id, LeaseState.BRIDGED,
            event=LeaseEvent.BRIDGE_APPROVED,
            initiator=LeaseInitiator.RISK_GOVERNOR,
            reason_codes=["bridge_approved"],
        )
        if risk_decision_ref:
            with self._lock:
                lease = self._leases.get(lease_id)
                if lease:
                    lease.risk_decision_ref = risk_decision_ref
        return result

    def consume(self, lease_id: str) -> DecisionLeaseObject:
        """BRIDGED → CONSUMED"""
        return self.transition(
            lease_id, LeaseState.CONSUMED,
            event=LeaseEvent.CONSUMED_BY_EXECUTION,
            initiator=LeaseInitiator.EXECUTION_CLOSURE_FLOW,
            reason_codes=["execution_closure"],
        )

    def freeze(self, lease_id: str, *, reason: str,
               initiator: LeaseInitiator = LeaseInitiator.INCIDENT_POLICY) -> DecisionLeaseObject:
        """REGISTERED/ACTIVE → FROZEN"""
        return self.transition(
            lease_id, LeaseState.FROZEN,
            event=LeaseEvent.FREEZE_REQUESTED,
            initiator=initiator,
            reason=reason, reason_codes=["frozen"],
        )

    def revoke(self, lease_id: str, *, approved_by: str, reason: str = "",
               initiator: LeaseInitiator = LeaseInitiator.OPERATOR) -> DecisionLeaseObject:
        """Any live state → REVOKED"""
        return self.transition(
            lease_id, LeaseState.REVOKED,
            event=LeaseEvent.REVOKE_REQUESTED,
            initiator=initiator,
            approved_by=approved_by,
            reason=reason, reason_codes=["revoked"],
        )

    def unfreeze_to_registered(self, lease_id: str, *, approved_by: str,
                                reason: str = "") -> DecisionLeaseObject:
        """FROZEN → REGISTERED"""
        return self.transition(
            lease_id, LeaseState.REGISTERED,
            event=LeaseEvent.RECOVERY_APPROVED,
            initiator=LeaseInitiator.OPERATOR,
            approved_by=approved_by,
            reason=reason, reason_codes=["unfrozen_to_registered"],
        )

    def unfreeze_to_active(self, lease_id: str, *, approved_by: str,
                            reason: str = "") -> DecisionLeaseObject:
        """FROZEN → ACTIVE"""
        return self.transition(
            lease_id, LeaseState.ACTIVE,
            event=LeaseEvent.RECOVERY_APPROVED,
            initiator=LeaseInitiator.OPERATOR,
            approved_by=approved_by,
            reason=reason, reason_codes=["unfrozen_to_active"],
        )

    # ── Expiry Guardian / 过期守护 (SM-02 §12) ──

    def check_expiry(self) -> list[str]:
        expired_ids: list[str] = []
        with self._lock:
            candidates = [
                (lid, lease) for lid, lease in self._leases.items()
                if lease.state not in TERMINAL_STATES and lease.is_expired_by_time
            ]

        for lid, lease in candidates:
            try:
                self.transition(
                    lid, LeaseState.EXPIRED,
                    event=LeaseEvent.EXPIRED_BY_TIME,
                    initiator=LeaseInitiator.EXPIRY_GUARDIAN,
                    reason_codes=["time_expiry"],
                )
                expired_ids.append(lid)
            except LeaseError as e:
                logger.warning("Lease expiry failed for %s: %s", lid, e)

        return expired_ids

    # ── Query / 查询 ──

    def get(self, lease_id: str) -> DecisionLeaseObject | None:
        with self._lock:
            lease = self._leases.get(lease_id)
            return copy.deepcopy(lease) if lease else None

    def get_live(self) -> list[DecisionLeaseObject]:
        with self._lock:
            return [copy.deepcopy(l) for l in self._leases.values() if l.state in LIVE_STATES]

    def get_bridgeable(self) -> list[DecisionLeaseObject]:
        with self._lock:
            return [copy.deepcopy(l) for l in self._leases.values() if l.is_bridgeable]

    def get_all(self) -> list[DecisionLeaseObject]:
        with self._lock:
            return [copy.deepcopy(l) for l in self._leases.values()]

    def get_status_summary(self) -> dict[str, int]:
        with self._lock:
            summary: dict[str, int] = {}
            for l in self._leases.values():
                summary[l.state.value] = summary.get(l.state.value, 0) + 1
            return summary

    # ── Persistence / 持久化 ──

    def export_state(self) -> list[dict[str, Any]]:
        with self._lock:
            result = []
            for lease in self._leases.values():
                d = lease.to_dict()
                d["transitions"] = lease.transitions
                d["source_deliberation_id"] = lease.source_deliberation_id
                d["registered_by"] = lease.registered_by
                d["activated_by"] = lease.activated_by
                d["bridged_by"] = lease.bridged_by
                d["consumed_by"] = lease.consumed_by
                d["freeze_reason"] = lease.freeze_reason
                d["revoke_reason"] = lease.revoke_reason
                d["rejection_reason"] = lease.rejection_reason
                d["risk_decision_ref"] = lease.risk_decision_ref
                d["valid_from_ms"] = lease.valid_from_ms
                d["expires_at_ms"] = lease.expires_at_ms
                result.append(d)
            return result

    def import_state(self, data: list[dict[str, Any]]) -> int:
        count = 0
        with self._lock:
            for d in data:
                try:
                    lease = DecisionLeaseObject.from_dict(d)
                    self._leases[lease.lease_id] = lease
                    count += 1
                except Exception as e:
                    logger.warning("Failed to import lease: %s", e)
        return count

    # ── Internal ──

    def _emit_audit(self, record: dict[str, Any]) -> None:
        if self._audit_callback:
            try:
                self._audit_callback(record)
            except Exception:
                logger.exception("Lease audit callback error")
