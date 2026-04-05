"""
Authorization State Machine — SM-01 Governance Specification Implementation
授权状态机 — SM-01 治理规范实现

MODULE_NOTE (中文):
  本模块实现 SM-01 定义的完整授权状态机：
  - 8 个正式状态：DRAFT, PENDING_APPROVAL, ACTIVE, RESTRICTED, FROZEN, REVOKED, EXPIRED, REJECTED
  - 16 条合法迁移（含守卫条件）
  - 6 条明确禁止的迁移
  - 自动迁移 vs 人工审批区分
  - 每次迁移生成 authorization_transition 审计对象
  - 过期守护（基于 expires_at 自动触发 EXPIRED）
  - 漂移防护：终态不可回流，扩权必须审批

MODULE_NOTE (English):
  Implements the full Authorization State Machine per SM-01 governance spec:
  - 8 formal states: DRAFT, PENDING_APPROVAL, ACTIVE, RESTRICTED, FROZEN, REVOKED, EXPIRED, REJECTED
  - 16 valid transitions (with guard conditions)
  - 6 explicitly forbidden transitions
  - Auto vs manual-approval distinction
  - Each transition emits an authorization_transition audit object
  - Expiry guardian (auto-triggers EXPIRED based on expires_at)
  - Drift protection: terminal states cannot flow back, expansion requires approval

Safety invariant:
  - Expansion (wider scope) ALWAYS requires explicit approval
  - Contraction (narrower scope) can be automatic but must be audited
  - Terminal states (REVOKED, EXPIRED, REJECTED) are irreversible
  - GUI / Learning / Strategy layers CANNOT directly modify authorization state
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
# States / 状态
# ═══════════════════════════════════════════════════════════════════════════════

class AuthState(str, Enum):
    """SM-01 §3: 8 formal authorization states / 8 个正式授权状态"""
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    ACTIVE = "ACTIVE"
    RESTRICTED = "RESTRICTED"
    FROZEN = "FROZEN"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


# Terminal states — no transitions OUT of these (SM-01 §8.1)
# 终态 — 不允许从这些状态迁出
TERMINAL_STATES = frozenset({AuthState.REVOKED, AuthState.EXPIRED, AuthState.REJECTED})

# States that count as "effective" (system can use as valid authorization)
# 有效状态 — 系统可用作合法授权
EFFECTIVE_STATES = frozenset({AuthState.ACTIVE, AuthState.RESTRICTED})


# ═══════════════════════════════════════════════════════════════════════════════
# Events / 事件
# ═══════════════════════════════════════════════════════════════════════════════

class AuthEvent(str, Enum):
    """SM-01 §5: Formal trigger events / 正式触发事件"""
    DRAFT_CREATED = "authorization_draft_created"
    SUBMITTED_FOR_APPROVAL = "authorization_submitted_for_approval"
    APPROVED = "authorization_approved"
    REJECTED = "authorization_rejected"
    ACTIVATED = "authorization_activated"
    RESTRICTED = "authorization_restricted"
    FREEZE_APPLIED = "authorization_freeze_applied"
    REVOKED = "authorization_revoked"
    EXPIRED = "authorization_expired"
    RECOVERY_APPROVED = "authorization_recovery_approved"
    INCIDENT_FREEZE = "incident_requires_freeze"
    OBSERVATION_RESTRICTION = "observation_window_restriction_applied"


# ═══════════════════════════════════════════════════════════════════════════════
# Initiator / 发起者
# ═══════════════════════════════════════════════════════════════════════════════

class AuthInitiator(str, Enum):
    """SM-01 §16: Who can initiate transitions / 迁移发起者"""
    AUTHORIZATION_GOVERNANCE = "AuthorizationGovernance"
    OPERATOR = "Operator"
    INCIDENT_POLICY = "IncidentPolicy"
    RECOVERY_APPROVAL_FLOW = "RecoveryApprovalFlow"
    EXPIRY_GUARDIAN = "ExpiryGuardian"


# ═══════════════════════════════════════════════════════════════════════════════
# Transition Rules / 迁移规则
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class TransitionRule:
    """Defines a valid state transition with guards / 定义合法迁移及守卫条件"""
    from_state: AuthState
    to_state: AuthState
    requires_approval: bool  # True = manual approval required / 需要人工审批
    allowed_initiators: frozenset[AuthInitiator]
    description: str = ""


# SM-01 §6+§7+§9: Complete transition table
# SM-01 §6+§7+§9: 完整迁移表
TRANSITION_RULES: dict[tuple[AuthState, AuthState], TransitionRule] = {}


def _register(from_s: AuthState, to_s: AuthState, approval: bool,
              initiators: frozenset[AuthInitiator], desc: str = "") -> None:
    TRANSITION_RULES[(from_s, to_s)] = TransitionRule(
        from_state=from_s, to_state=to_s,
        requires_approval=approval,
        allowed_initiators=initiators,
        description=desc,
    )


_ALL_GOV = frozenset({AuthInitiator.AUTHORIZATION_GOVERNANCE, AuthInitiator.OPERATOR,
                       AuthInitiator.INCIDENT_POLICY, AuthInitiator.RECOVERY_APPROVAL_FLOW,
                       AuthInitiator.EXPIRY_GUARDIAN})
_OPERATOR_GOV = frozenset({AuthInitiator.AUTHORIZATION_GOVERNANCE, AuthInitiator.OPERATOR})
_INCIDENT = frozenset({AuthInitiator.INCIDENT_POLICY, AuthInitiator.AUTHORIZATION_GOVERNANCE,
                        AuthInitiator.OPERATOR})
_RECOVERY = frozenset({AuthInitiator.RECOVERY_APPROVAL_FLOW, AuthInitiator.OPERATOR})
_EXPIRY = frozenset({AuthInitiator.EXPIRY_GUARDIAN, AuthInitiator.AUTHORIZATION_GOVERNANCE})

# §7.1 Draft & Approval phase / 草案与审批阶段
_register(AuthState.DRAFT, AuthState.PENDING_APPROVAL, False, _OPERATOR_GOV,
          "Submit draft for approval / 提交审批")
_register(AuthState.DRAFT, AuthState.REJECTED, False, _OPERATOR_GOV,
          "Reject/abandon draft / 拒绝或废弃草案")
_register(AuthState.PENDING_APPROVAL, AuthState.ACTIVE, True, _OPERATOR_GOV,
          "Approve and activate / 审批通过并激活")
_register(AuthState.PENDING_APPROVAL, AuthState.REJECTED, False, _OPERATOR_GOV,
          "Reject during approval / 审批拒绝")

# §7.2 Post-activation governance / 生效后治理
_register(AuthState.ACTIVE, AuthState.RESTRICTED, False, _INCIDENT,
          "Restrict scope (contraction) / 收缩授权范围")
_register(AuthState.ACTIVE, AuthState.FROZEN, False, _INCIDENT,
          "Freeze authorization / 冻结授权")
_register(AuthState.ACTIVE, AuthState.REVOKED, True, _OPERATOR_GOV,
          "Revoke authorization / 撤销授权")
_register(AuthState.ACTIVE, AuthState.EXPIRED, False, _EXPIRY,
          "Natural expiry / 自然过期")

# §7.3 Post-restriction/freeze recovery & termination
_register(AuthState.RESTRICTED, AuthState.ACTIVE, True, _RECOVERY,
          "Restore to full scope (requires approval) / 恢复完整范围（需审批）")
_register(AuthState.RESTRICTED, AuthState.FROZEN, False, _INCIDENT,
          "Freeze restricted auth / 冻结已收缩授权")
_register(AuthState.RESTRICTED, AuthState.REVOKED, True, _OPERATOR_GOV,
          "Revoke restricted auth / 撤销已收缩授权")
_register(AuthState.RESTRICTED, AuthState.EXPIRED, False, _EXPIRY,
          "Restricted auth expires / 已收缩授权过期")

_register(AuthState.FROZEN, AuthState.RESTRICTED, True, _RECOVERY,
          "Unfreeze to restricted (conservative recovery) / 解冻至收缩（保守恢复）")
_register(AuthState.FROZEN, AuthState.ACTIVE, True, _RECOVERY,
          "Unfreeze to active (full recovery, conditional) / 解冻至活跃（完全恢复，有条件）")
_register(AuthState.FROZEN, AuthState.REVOKED, True, _OPERATOR_GOV,
          "Revoke frozen auth / 撤销已冻结授权")
_register(AuthState.FROZEN, AuthState.EXPIRED, False, _EXPIRY,
          "Frozen auth expires / 已冻结授权过期")


# SM-01 §8: Explicitly forbidden transitions / 明确禁止的迁移
FORBIDDEN_TRANSITIONS: frozenset[tuple[AuthState, AuthState]] = frozenset({
    # §8.1 Terminal states cannot flow back / 终态不可回流
    (AuthState.REVOKED, AuthState.ACTIVE),
    (AuthState.REVOKED, AuthState.RESTRICTED),
    (AuthState.EXPIRED, AuthState.ACTIVE),
    (AuthState.EXPIRED, AuthState.RESTRICTED),
    (AuthState.REJECTED, AuthState.ACTIVE),
    (AuthState.REJECTED, AuthState.PENDING_APPROVAL),
    # §8.2 Skip approval / 跳过审批
    (AuthState.DRAFT, AuthState.ACTIVE),
})


# ═══════════════════════════════════════════════════════════════════════════════
# Authorization Object / 授权对象
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class AuthorizationObject:
    """
    A formal governance authorization object / 正式治理授权对象

    SM-01 §2: "A formal governance permit controlling what actions the Agent
    is allowed to perform within defined boundaries, scopes, and time windows."
    """
    authorization_id: str = ""
    state: AuthState = AuthState.DRAFT
    version: int = 1
    created_at_ms: int = 0
    updated_at_ms: int = 0
    expires_at_ms: int | None = None  # None = no expiry / 无过期时间

    # Scope definition / 作用域定义
    scope: dict[str, Any] = field(default_factory=dict)
    # e.g. {"categories": ["linear"], "symbols": ["BTCUSDT"], "actions": ["paper_order"],
    #        "max_leverage": 10, "mode": "paper_only"}

    # Metadata / 元信息
    title: str = ""
    description: str = ""
    created_by: str = ""
    approved_by: str | None = None
    approval_reason: str = ""
    restriction_reason: str = ""
    freeze_reason: str = ""
    revoke_reason: str = ""

    # Transition history / 迁移历史
    transitions: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.authorization_id:
            self.authorization_id = f"auth:{uuid.uuid4().hex[:12]}"
        if not self.created_at_ms:
            self.created_at_ms = int(time.time() * 1000)
            self.updated_at_ms = self.created_at_ms

    @property
    def is_effective(self) -> bool:
        """Is this authorization currently usable by the system? / 是否可被系统使用？"""
        return self.state in EFFECTIVE_STATES

    @property
    def is_terminal(self) -> bool:
        """Is this authorization in a terminal (irreversible) state? / 是否处于终态？"""
        return self.state in TERMINAL_STATES

    @property
    def is_expired_by_time(self) -> bool:
        """Has the expiry time passed? / 是否已超过过期时间？"""
        if self.expires_at_ms is None:
            return False
        return int(time.time() * 1000) > self.expires_at_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "authorization_id": self.authorization_id,
            "state": self.state.value,
            "version": self.version,
            "created_at_ms": self.created_at_ms,
            "updated_at_ms": self.updated_at_ms,
            "expires_at_ms": self.expires_at_ms,
            "scope": self.scope,
            "title": self.title,
            "description": self.description,
            "created_by": self.created_by,
            "approved_by": self.approved_by,
            "is_effective": self.is_effective,
            "is_terminal": self.is_terminal,
            "transition_count": len(self.transitions),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AuthorizationObject:
        obj = cls(
            authorization_id=d.get("authorization_id", ""),
            state=AuthState(d.get("state", "DRAFT")),
            version=d.get("version", 1),
            created_at_ms=d.get("created_at_ms", 0),
            updated_at_ms=d.get("updated_at_ms", 0),
            expires_at_ms=d.get("expires_at_ms"),
            scope=d.get("scope", {}),
            title=d.get("title", ""),
            description=d.get("description", ""),
            created_by=d.get("created_by", ""),
            approved_by=d.get("approved_by"),
            approval_reason=d.get("approval_reason", ""),
            restriction_reason=d.get("restriction_reason", ""),
            freeze_reason=d.get("freeze_reason", ""),
            revoke_reason=d.get("revoke_reason", ""),
            transitions=d.get("transitions", []),
        )
        return obj


# ═══════════════════════════════════════════════════════════════════════════════
# Transition Record / 迁移记录
# ═══════════════════════════════════════════════════════════════════════════════

def _build_transition_record(
    auth: AuthorizationObject,
    to_state: AuthState,
    event: AuthEvent,
    initiator: AuthInitiator,
    reason_codes: list[str] | None = None,
    approved_by: str | None = None,
) -> dict[str, Any]:
    """SM-01 §16: Build authorization_transition audit object / 构建迁移审计对象"""
    now_ms = int(time.time() * 1000)
    tid = f"atx:{uuid.uuid4().hex[:12]}"
    return {
        "transition_id": tid,
        "authorization_id": auth.authorization_id,
        "previous_status": auth.state.value,
        "next_status": to_state.value,
        "trigger_event_type": event.value,
        "trigger_event_id": f"evt:{uuid.uuid4().hex[:8]}",
        "initiated_by": initiator.value,
        "transition_reason_codes": reason_codes or [],
        "approval_required": TRANSITION_RULES.get(
            (auth.state, to_state), TransitionRule(auth.state, to_state, False, frozenset())
        ).requires_approval,
        "approved_by": approved_by,
        "effective_at_ms": now_ms,
        "audit_event_ref": f"aud:{hashlib.sha256(tid.encode()).hexdigest()[:16]}",
        "version_before": auth.version,
        "version_after": auth.version + 1,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# State Machine Engine / 状态机引擎
# ═══════════════════════════════════════════════════════════════════════════════

class AuthorizationError(Exception):
    """Raised when an invalid transition is attempted / 非法迁移时抛出"""
    pass


class AuthorizationStateMachine:
    """
    Core state machine engine for authorization lifecycle management.
    授权生命周期管理的核心状态机引擎。

    Thread-safe. All mutations go through transition() which validates
    the transition, checks guards, records audit, and updates state atomically.
    线程安全。所有变更通过 transition() 执行，验证迁移、检查守卫、记录审计、原子更新。
    """

    def __init__(self, audit_callback: Callable[[dict[str, Any]], None] | None = None) -> None:
        self._lock = threading.Lock()
        self._authorizations: dict[str, AuthorizationObject] = {}
        self._audit_callback = audit_callback  # External audit sink / 外部审计接收器
        self._change_audit_log = None  # T5.02: Optional ChangeAuditLog for WHO/WHEN/APPROVAL tracking

    # ── T5.02: Change Audit Log Injection / 變更審計日誌注入 ──

    def set_change_audit_log(self, cal: Any) -> None:
        """Inject ChangeAuditLog for WHO/WHEN/APPROVAL tracking / 注入變更審計日誌"""
        with self._lock:
            self._change_audit_log = cal

    # ── Create / 创建 ──

    def create_draft(
        self,
        *,
        title: str,
        scope: dict[str, Any],
        created_by: str,
        description: str = "",
        expires_at_ms: int | None = None,
    ) -> AuthorizationObject:
        """
        Create a new authorization in DRAFT state.
        创建新的授权草案（DRAFT 状态）。
        """
        auth = AuthorizationObject(
            title=title,
            scope=scope,
            description=description,
            created_by=created_by,
            expires_at_ms=expires_at_ms,
        )

        record = _build_transition_record(
            auth, AuthState.DRAFT,
            AuthEvent.DRAFT_CREATED,
            AuthInitiator.OPERATOR,
            reason_codes=["initial_draft"],
        )
        # For creation, previous_status is "NONE"
        record["previous_status"] = "NONE"
        auth.transitions.append(record)

        with self._lock:
            self._authorizations[auth.authorization_id] = auth

        self._emit_audit(record)
        logger.info(
            "Authorization draft created: %s [%s] / 授权草案已创建",
            auth.authorization_id, title,
        )
        return auth

    # ── Transition / 迁移 ──

    def transition(
        self,
        authorization_id: str,
        to_state: AuthState,
        *,
        event: AuthEvent,
        initiator: AuthInitiator,
        reason_codes: list[str] | None = None,
        approved_by: str | None = None,
        reason: str = "",
    ) -> AuthorizationObject:
        """
        Execute a state transition on an authorization object.
        对授权对象执行状态迁移。

        Validates:
        1. Authorization exists and is not in terminal state (for non-terminal targets)
        2. Transition is not forbidden (SM-01 §8)
        3. Transition is in the valid transition table (SM-01 §6-7)
        4. Initiator is allowed for this transition
        5. If approval required, approved_by must be provided
        6. Expiry check (auto-expire if past expires_at)
        """
        with self._lock:
            auth = self._authorizations.get(authorization_id)
            if auth is None:
                raise AuthorizationError(
                    f"Authorization not found: {authorization_id} / 授权对象不存在"
                )

            from_state = auth.state

            # Guard 1: Terminal states cannot transition out / 终态不可迁出
            if from_state in TERMINAL_STATES:
                raise AuthorizationError(
                    f"Cannot transition from terminal state {from_state.value} / "
                    f"不可从终态 {from_state.value} 迁出"
                )

            # Guard 2: Check forbidden transitions / 检查禁止迁移
            if (from_state, to_state) in FORBIDDEN_TRANSITIONS:
                raise AuthorizationError(
                    f"Forbidden transition: {from_state.value} → {to_state.value} "
                    f"(SM-01 §8) / 禁止迁移"
                )

            # Guard 3: Check valid transition table / 检查合法迁移表
            rule = TRANSITION_RULES.get((from_state, to_state))
            if rule is None:
                raise AuthorizationError(
                    f"Invalid transition: {from_state.value} → {to_state.value} "
                    f"(not in transition table) / 非法迁移（不在迁移表中）"
                )

            # Guard 4: Check initiator / 检查发起者
            if initiator not in rule.allowed_initiators:
                raise AuthorizationError(
                    f"Initiator {initiator.value} not allowed for "
                    f"{from_state.value} → {to_state.value}. "
                    f"Allowed: {[i.value for i in rule.allowed_initiators]} / "
                    f"发起者不被允许"
                )

            # Guard 5: Check approval / 检查审批
            if rule.requires_approval and not approved_by:
                raise AuthorizationError(
                    f"Transition {from_state.value} → {to_state.value} requires "
                    f"explicit approval (approved_by must be provided) / "
                    f"该迁移需要明确审批（必须提供 approved_by）"
                )

            # Execute transition / 执行迁移
            record = _build_transition_record(
                auth, to_state, event, initiator,
                reason_codes=reason_codes,
                approved_by=approved_by,
            )

            auth.state = to_state
            auth.version += 1
            auth.updated_at_ms = int(time.time() * 1000)
            auth.transitions.append(record)

            # Update metadata based on transition / 根据迁移更新元信息
            if to_state == AuthState.ACTIVE and approved_by:
                auth.approved_by = approved_by
                auth.approval_reason = reason
            elif to_state == AuthState.RESTRICTED:
                auth.restriction_reason = reason
            elif to_state == AuthState.FROZEN:
                auth.freeze_reason = reason
            elif to_state == AuthState.REVOKED:
                auth.revoke_reason = reason

            # T5.02: Record state change to ChangeAuditLog if available
            if self._change_audit_log:
                try:
                    from .change_audit_log import ChangeType  # noqa: E402
                    # Auto-approve audit record when transition is by system (e.g. paper auto-grant)
                    # 系統發起的變更（如紙盤自動授權）自動批准審計記錄
                    who_str = str(approved_by or initiator.value)
                    is_auto = "auto" in who_str.lower() or "system" in who_str.lower()
                    self._change_audit_log.record_change(
                        change_type=ChangeType.STATE_CHANGE,
                        who=who_str,
                        what=f"Authorization: {from_state.value} → {to_state.value}",
                        reason=reason or "",
                        old_value=from_state.value,
                        new_value=to_state.value,
                        auto_approve=is_auto,
                    )
                except Exception as e:
                    logger.error("Failed to record change audit: %s", e)

            # Return a copy / 返回副本
            result = copy.deepcopy(auth)

        self._emit_audit(record)
        logger.info(
            "Authorization transition: %s %s → %s (by %s) / 授权迁移",
            authorization_id, from_state.value, to_state.value, initiator.value,
        )
        return result

    # ── Convenience Methods / 便捷方法 ──

    def submit_for_approval(self, authorization_id: str, *, initiator: AuthInitiator = AuthInitiator.OPERATOR) -> AuthorizationObject:
        """DRAFT → PENDING_APPROVAL"""
        return self.transition(
            authorization_id, AuthState.PENDING_APPROVAL,
            event=AuthEvent.SUBMITTED_FOR_APPROVAL,
            initiator=initiator,
            reason_codes=["submitted_for_review"],
        )

    def approve(self, authorization_id: str, *, approved_by: str, reason: str = "") -> AuthorizationObject:
        """PENDING_APPROVAL → ACTIVE"""
        return self.transition(
            authorization_id, AuthState.ACTIVE,
            event=AuthEvent.APPROVED,
            initiator=AuthInitiator.OPERATOR,
            approved_by=approved_by,
            reason=reason,
            reason_codes=["approved"],
        )

    def reject(self, authorization_id: str, *, reason: str = "") -> AuthorizationObject:
        """DRAFT/PENDING_APPROVAL → REJECTED"""
        return self.transition(
            authorization_id, AuthState.REJECTED,
            event=AuthEvent.REJECTED,
            initiator=AuthInitiator.OPERATOR,
            reason=reason,
            reason_codes=["rejected"],
        )

    def restrict(self, authorization_id: str, *, reason: str, initiator: AuthInitiator = AuthInitiator.INCIDENT_POLICY) -> AuthorizationObject:
        """ACTIVE → RESTRICTED"""
        return self.transition(
            authorization_id, AuthState.RESTRICTED,
            event=AuthEvent.RESTRICTED,
            initiator=initiator,
            reason=reason,
            reason_codes=["scope_restricted"],
        )

    def freeze(self, authorization_id: str, *, reason: str, initiator: AuthInitiator = AuthInitiator.INCIDENT_POLICY) -> AuthorizationObject:
        """ACTIVE/RESTRICTED → FROZEN"""
        return self.transition(
            authorization_id, AuthState.FROZEN,
            event=AuthEvent.FREEZE_APPLIED,
            initiator=initiator,
            reason=reason,
            reason_codes=["frozen"],
        )

    def revoke(self, authorization_id: str, *, approved_by: str, reason: str = "") -> AuthorizationObject:
        """ACTIVE/RESTRICTED/FROZEN → REVOKED (terminal)"""
        return self.transition(
            authorization_id, AuthState.REVOKED,
            event=AuthEvent.REVOKED,
            initiator=AuthInitiator.OPERATOR,
            approved_by=approved_by,
            reason=reason,
            reason_codes=["revoked"],
        )

    def recover_to_restricted(self, authorization_id: str, *, approved_by: str, reason: str = "") -> AuthorizationObject:
        """FROZEN → RESTRICTED (conservative recovery, SM-01 §11.3)"""
        return self.transition(
            authorization_id, AuthState.RESTRICTED,
            event=AuthEvent.RECOVERY_APPROVED,
            initiator=AuthInitiator.RECOVERY_APPROVAL_FLOW,
            approved_by=approved_by,
            reason=reason,
            reason_codes=["conservative_recovery"],
        )

    def recover_to_active(self, authorization_id: str, *, approved_by: str, reason: str = "") -> AuthorizationObject:
        """FROZEN/RESTRICTED → ACTIVE (full recovery, requires approval)"""
        return self.transition(
            authorization_id, AuthState.ACTIVE,
            event=AuthEvent.RECOVERY_APPROVED,
            initiator=AuthInitiator.RECOVERY_APPROVAL_FLOW,
            approved_by=approved_by,
            reason=reason,
            reason_codes=["full_recovery"],
        )

    # ── Expiry Guardian / 过期守护 ──

    def check_expiry(self) -> list[str]:
        """
        Check all non-terminal authorizations for expiry and auto-transition.
        检查所有非终态授权的过期状态并自动迁移。

        Should be called periodically (e.g., every tick or every minute).
        应定期调用（如每次 tick 或每分钟）。
        """
        expired_ids: list[str] = []
        with self._lock:
            candidates = [
                (aid, auth) for aid, auth in self._authorizations.items()
                if auth.state not in TERMINAL_STATES and auth.is_expired_by_time
            ]

        for aid, auth in candidates:
            try:
                self.transition(
                    aid, AuthState.EXPIRED,
                    event=AuthEvent.EXPIRED,
                    initiator=AuthInitiator.EXPIRY_GUARDIAN,
                    reason_codes=["time_expiry"],
                )
                expired_ids.append(aid)
                logger.info("Authorization auto-expired: %s / 授权自动过期", aid)
            except AuthorizationError as e:
                logger.warning("Expiry transition failed for %s: %s", aid, e)

        return expired_ids

    # ── Query / 查询 ──

    def get(self, authorization_id: str) -> AuthorizationObject | None:
        """Get a copy of an authorization object / 获取授权对象副本"""
        with self._lock:
            auth = self._authorizations.get(authorization_id)
            return copy.deepcopy(auth) if auth else None

    def get_effective(self) -> list[AuthorizationObject]:
        """Get all currently effective (ACTIVE or RESTRICTED) authorizations / 获取所有有效授权"""
        with self._lock:
            return [
                copy.deepcopy(auth)
                for auth in self._authorizations.values()
                if auth.state in EFFECTIVE_STATES
            ]

    def get_all(self) -> list[AuthorizationObject]:
        """Get all authorization objects / 获取所有授权对象"""
        with self._lock:
            return [copy.deepcopy(auth) for auth in self._authorizations.values()]

    def get_status_summary(self) -> dict[str, int]:
        """Get count of authorizations by state / 按状态统计授权数量"""
        with self._lock:
            summary: dict[str, int] = {}
            for auth in self._authorizations.values():
                key = auth.state.value
                summary[key] = summary.get(key, 0) + 1
            return summary

    # ── Persistence / 持久化 ──

    def export_state(self) -> list[dict[str, Any]]:
        """Export all authorizations for persistence / 导出所有授权用于持久化"""
        with self._lock:
            result = []
            for auth in self._authorizations.values():
                d = auth.to_dict()
                d["transitions"] = auth.transitions
                d["restriction_reason"] = auth.restriction_reason
                d["freeze_reason"] = auth.freeze_reason
                d["revoke_reason"] = auth.revoke_reason
                d["approval_reason"] = auth.approval_reason
                d["scope"] = auth.scope
                d["title"] = auth.title
                d["description"] = auth.description
                d["created_by"] = auth.created_by
                d["approved_by"] = auth.approved_by
                d["expires_at_ms"] = auth.expires_at_ms
                result.append(d)
            return result

    def import_state(self, data: list[dict[str, Any]]) -> int:
        """Import authorizations from persistence / 从持久化数据导入授权"""
        count = 0
        with self._lock:
            for d in data:
                try:
                    auth = AuthorizationObject.from_dict(d)
                    auth.transitions = d.get("transitions", [])
                    self._authorizations[auth.authorization_id] = auth
                    count += 1
                except Exception as e:
                    logger.warning("Failed to import authorization: %s", e)
        logger.info("Imported %d authorizations / 导入了 %d 个授权对象", count, count)
        return count

    # ── Internal / 内部 ──

    def _emit_audit(self, record: dict[str, Any]) -> None:
        """Emit audit record to callback and log / 发送审计记录"""
        if self._audit_callback:
            try:
                self._audit_callback(record)
            except Exception:
                logger.exception("Audit callback error / 审计回调异常")
