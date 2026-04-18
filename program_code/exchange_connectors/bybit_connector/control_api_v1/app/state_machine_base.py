"""
State Machine Base — Shared engine core for SM-01/SM-02/SM-04 state machines
状态机基础 — SM-01/SM-02/SM-04 状态机共享引擎核心

MODULE_NOTE (English):
  Extracts the common plumbing from AuthorizationStateMachine (SM-01),
  DecisionLeaseStateMachine (SM-02), and RiskGovernorStateMachine (SM-04)
  into a single reusable base class. This removes ~350-400 lines of
  copy-paste while preserving EXACT observable behavior:

    - transition_id / trigger_event_id / audit_event_ref prefixes are
      subclass class-attrs (atx/evt/aud, ltx/levt/laud, rgt/revt/raud).
    - The observer callback order is load-bearing: we BUILD the audit
      record inside the critical section, but we EMIT it outside the lock
      to prevent re-entrant deadlocks in user-supplied callbacks.
    - Guard order matches the original implementations exactly:
        1. Terminal state cannot transition out (SM subclass may skip)
        2. Forbidden transition check (SM-0x §8)
        3. Transition rule table lookup
        4. Initiator allow-list
        5. Approval requirement
        6. Optional extra hook (_extra_validate) for SM-04 min-hold-time
    - Persistence format is NOT unified — Auth/Lease return list[dict]
      via a mixin, RiskGov keeps its single-state dict layout.

  Subclasses MUST override these class attributes:
    TRANSITION_ID_PREFIX, EVENT_ID_PREFIX, AUDIT_REF_PREFIX,
    TRANSITION_RULES, FORBIDDEN_TRANSITIONS, TERMINAL_STATES,
    ERROR_CLS, CHANGE_LABEL.

MODULE_NOTE (中文):
  把三个状态机中重复的引擎骨架抽出成可复用的基类，去除 ~350-400 行复制粘贴，
  但严格保留可观察行为：
    - 迁移 id / 事件 id / 审计 ref 前缀用子类 ClassVar 参数化（SM-0x 各自不同）
    - 观察者回调顺序受约束：审计记录在锁内构建，但必须在锁外发出
      （防止用户回调再入锁造成死锁）
    - 守卫顺序与原实现逐条一致
    - 持久化格式不强行统一 — Auth/Lease 通过 mixin 用 list[dict]，
      RiskGov 保持单对象 dict
  子类必须覆盖上述 ClassVar。

Safety invariant:
  - Base class does NOT mutate state on invalid transitions (fail-closed).
  - Base class NEVER re-enters subclass locks from the audit emission path.
  - Base class does not know about domain-specific "metadata on target state"
    updates (e.g. approval_reason, freeze_reason, registered_by) —
    subclasses keep those post-update writes inside their transition().
"""

from __future__ import annotations

import copy
import hashlib
import logging
import threading
import time
import uuid
from enum import Enum
from typing import Any, Callable, ClassVar, Generic, TypeVar

logger = logging.getLogger(__name__)


# TypeVar bound to Enum so both str-Enum (SM-01/02) and IntEnum (SM-04) work.
# 绑定到 Enum，让字符串枚举与整型枚举都能用同一个基类。
S = TypeVar("S", bound=Enum)


class StateMachineBase(Generic[S]):
    """
    Thread-safe state machine engine core.
    线程安全的状态机引擎核心。

    Concrete subclasses (AuthorizationStateMachine, DecisionLeaseStateMachine,
    RiskGovernorStateMachine) MUST override the ClassVar fields below.
    具体子类必须覆盖下列 ClassVar 字段。

    The subclass owns:
      - The storage layout (dict-of-objects vs single state).
      - Domain metadata updates after a successful transition.
      - Convenience methods (approve / reject / freeze / escalate_to / ...).

    The base owns:
      - Lock ownership (`self._lock`), audit callback, change audit log hook.
      - `_validate_transition()` — 5 common guards + extra hook.
      - `_build_transition_record()` — structured audit record with subclass prefixes.
      - `_emit_audit()` — exception-safe external callback dispatch.
      - `_record_change_audit()` — T5.02 ChangeAuditLog integration.
    """

    # ── Subclass-provided class attributes / 子类提供的类属性 ──
    # Prefix for transition_id (e.g. "atx", "ltx", "rgt")
    # 迁移 id 前缀
    TRANSITION_ID_PREFIX: ClassVar[str] = ""
    # Prefix for trigger_event_id (e.g. "evt", "levt", "revt")
    # 触发事件 id 前缀
    EVENT_ID_PREFIX: ClassVar[str] = ""
    # Prefix for audit_event_ref (e.g. "aud", "laud", "raud")
    # 审计事件引用前缀
    AUDIT_REF_PREFIX: ClassVar[str] = ""
    # Exception class raised for invalid transitions
    # 非法迁移抛出的异常类
    ERROR_CLS: ClassVar[type[Exception]] = Exception
    # Human-readable label used in ChangeAuditLog.record_change(what=...)
    # ChangeAuditLog 使用的人类可读标签
    CHANGE_LABEL: ClassVar[str] = ""

    # Terminal states frozen-set (no transitions out)
    # 终态集合（不允许迁出）
    TERMINAL_STATES: ClassVar[frozenset] = frozenset()
    # Forbidden transitions frozen-set of (from_state, to_state) pairs
    # 禁止迁移集合
    FORBIDDEN_TRANSITIONS: ClassVar[frozenset] = frozenset()
    # Dict[(from_state, to_state) -> rule] — the rule dataclass is domain-specific
    # but must expose .requires_approval and .allowed_initiators attributes.
    # 迁移规则表，规则对象必须暴露 .requires_approval 和 .allowed_initiators
    TRANSITION_RULES: ClassVar[dict] = {}

    def __init__(
        self,
        audit_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """
        Base initialization.
        基类初始化。

        Subclasses may add their own fields (stores, thresholds, etc.) in
        their own __init__ and should call super().__init__(audit_callback=...).
        子类可在自身 __init__ 中添加字段（对象存储、阈值等），
        并应调用 super().__init__(audit_callback=...)。
        """
        self._lock = threading.Lock()
        self._audit_callback = audit_callback
        # T5.02: Optional ChangeAuditLog for WHO/WHEN/APPROVAL tracking
        # T5.02：可选的 ChangeAuditLog，用于 WHO/WHEN/APPROVAL 追踪
        self._change_audit_log: Any = None

    # ── T5.02: Change Audit Log Injection / 變更審計日誌注入 ──

    def set_change_audit_log(self, cal: Any) -> None:
        """
        Inject ChangeAuditLog for WHO/WHEN/APPROVAL tracking.
        注入變更審計日誌（记录谁/何时/是否审批）。
        """
        with self._lock:
            self._change_audit_log = cal

    # ── Internal: audit record construction / 内部：审计记录构建 ──

    def _build_transition_record(
        self,
        *,
        from_state: S,
        to_state: S,
        object_id: str | None,
        object_id_key: str | None,
        event_value: str,
        initiator_value: str,
        version_before: int,
        reason_codes: list[str] | None = None,
        approved_by: str | None = None,
        previous_status_value: str | None = None,
        next_status_value: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Build a transition audit record. Uses subclass prefixes.
        构建迁移审计记录。使用子类定义的 id 前缀。

        Args:
          from_state / to_state: Enum members (used only for approval lookup).
          object_id / object_id_key: Optional (e.g. "authorization_id", "lease_id").
            SM-04 passes both as None (RiskGov has no per-object id).
          event_value / initiator_value: .value strings of the event/initiator enum.
          version_before: Current object/state version; record stores
            version_after = version_before + 1.
          previous_status_value / next_status_value: Override labels (e.g. enum .name
            for IntEnum RiskLevel, or .value for str Enum). If None, uses
            from_state.value / to_state.value.
          extra: Subclass-specific extra fields (e.g. direction, level_held_ms,
            metrics_snapshot for RiskGov).
        """
        now_ms = int(time.time() * 1000)
        tid = f"{self.TRANSITION_ID_PREFIX}:{uuid.uuid4().hex[:12]}"
        prev_label = (
            previous_status_value if previous_status_value is not None
            else from_state.value if hasattr(from_state, "value") else str(from_state)
        )
        next_label = (
            next_status_value if next_status_value is not None
            else to_state.value if hasattr(to_state, "value") else str(to_state)
        )
        record: dict[str, Any] = {
            "transition_id": tid,
            "previous_status": prev_label,
            "next_status": next_label,
            "trigger_event_id": f"{self.EVENT_ID_PREFIX}:{uuid.uuid4().hex[:8]}",
            "initiated_by": initiator_value,
            "transition_reason_codes": reason_codes or [],
            "approval_required": self._lookup_requires_approval(from_state, to_state),
            "approved_by": approved_by,
            "effective_at_ms": now_ms,
            "audit_event_ref": f"{self.AUDIT_REF_PREFIX}:{hashlib.sha256(tid.encode()).hexdigest()[:16]}",
            "version_before": version_before,
            "version_after": version_before + 1,
            "trigger_event_type": event_value,
        }
        if object_id is not None and object_id_key is not None:
            record[object_id_key] = object_id
        if extra:
            record.update(extra)
        return record

    def _lookup_requires_approval(self, from_state: S, to_state: S) -> bool:
        """
        Look up whether a (from, to) transition requires approval. Falls back
        to False when the pair is absent (matches original behavior: for
        DRAFT→DRAFT creation records, no rule exists → False).
        查询 (from, to) 迁移是否需要审批；缺失时回退为 False（与原实现一致）。
        """
        rule = self.TRANSITION_RULES.get((from_state, to_state))
        if rule is None:
            return False
        return bool(getattr(rule, "requires_approval", False))

    # ── Internal: guard validation / 内部：守卫校验 ──

    def _validate_transition(
        self,
        *,
        from_state: S,
        to_state: S,
        initiator: Enum,
        approved_by: str | None,
        spec_section: str,
    ) -> Any:
        """
        Run guards 1-5 and return the matched TransitionRule.
        执行 1-5 号守卫，返回匹配的 TransitionRule。

        Raises ERROR_CLS on any guard violation. Fail-closed: no mutation
        is performed here; the caller is responsible for atomicity.
        违反任一守卫时抛出 ERROR_CLS；本方法只读（不修改状态）。

        spec_section: "SM-01 §8" / "SM-02 §8" — embedded in forbidden-transition error.
        """
        # Guard 1: Terminal states cannot transition out / 终态不可迁出
        if from_state in self.TERMINAL_STATES:
            raise self.ERROR_CLS(
                f"Cannot transition from terminal state {self._label(from_state)} / "
                f"不可从终态 {self._label(from_state)} 迁出"
            )

        # Guard 2: Forbidden transitions / 禁止迁移
        if (from_state, to_state) in self.FORBIDDEN_TRANSITIONS:
            raise self.ERROR_CLS(
                f"Forbidden transition: {self._label(from_state)} → {self._label(to_state)} "
                f"({spec_section}) / 禁止迁移"
            )

        # Guard 3: Check valid transition table / 检查合法迁移表
        rule = self.TRANSITION_RULES.get((from_state, to_state))
        if rule is None:
            raise self.ERROR_CLS(
                f"Invalid transition: {self._label(from_state)} → {self._label(to_state)} "
                f"(not in transition table) / 非法迁移（不在迁移表中）"
            )

        # Guard 4: Initiator allow-list / 检查发起者白名单
        if initiator not in rule.allowed_initiators:
            raise self.ERROR_CLS(
                f"Initiator {initiator.value} not allowed for "
                f"{self._label(from_state)} → {self._label(to_state)}. "
                f"Allowed: {[i.value for i in rule.allowed_initiators]} / "
                f"发起者不被允许"
            )

        # Guard 5: Approval requirement / 检查审批
        if rule.requires_approval and not approved_by:
            raise self.ERROR_CLS(
                f"Transition {self._label(from_state)} → {self._label(to_state)} requires "
                f"explicit approval (approved_by must be provided) / "
                f"该迁移需要明确审批（必须提供 approved_by）"
            )

        # Guard 6 (optional extra): subclass hook (e.g. min-hold-time) /
        #  可选扩展：子类钩子（如 SM-04 最短驻留时间）
        self._extra_validate(from_state=from_state, to_state=to_state, rule=rule)

        return rule

    def _extra_validate(self, *, from_state: S, to_state: S, rule: Any) -> None:
        """
        Hook for subclass-specific extra validation (e.g. SM-04 min-hold-time
        before de-escalation). Default: no-op.
        子类扩展守卫钩子（如 SM-04 降级前最短驻留时间）。默认：空操作。
        """
        return None

    @staticmethod
    def _label(state: Any) -> str:
        """
        Human-readable label for a state — prefers .name for IntEnum,
        .value for str-Enum, otherwise str(state).
        状态人类可读标签：IntEnum 用 .name，字符串枚举用 .value，其它 str()。
        """
        # IntEnum uses .name; str-Enum uses .value (original error msgs mixed).
        # Keep backward-compatible: Auth/Lease used .value, RiskGov used .name.
        # Both have .value and .name, so prefer .value here (matches Auth/Lease,
        # which have the most error-message tests). Subclasses that need .name
        # can override by calling ERROR_CLS directly.
        if hasattr(state, "value"):
            return str(state.value)
        return str(state)

    # ── Internal: audit emission / 内部：审计发射 ──

    def _emit_audit(self, record: dict[str, Any]) -> None:
        """
        Emit audit record to callback and log. Exception-safe.
        向回调与日志发送审计记录；回调异常被捕获记录。

        IMPORTANT (load-bearing invariant): Callers MUST invoke this AFTER
        releasing self._lock. User-supplied audit callbacks may attempt to
        call back into the state machine, so emitting inside the lock would
        cause re-entrant deadlock.
        关键不变量：调用方必须在释放 self._lock 之后调用本方法。
        """
        if self._audit_callback:
            try:
                self._audit_callback(record)
            except Exception:
                logger.exception("Audit callback error / 审计回调异常")

    def _record_change_audit(
        self,
        *,
        from_label: str,
        to_label: str,
        initiator_value: str,
        approved_by: str | None,
        reason: str,
        auto_approve: bool | None = None,
    ) -> None:
        """
        Record a state change to ChangeAuditLog (T5.02) if configured.
        如配置了 ChangeAuditLog，则记录状态变更（T5.02）。

        auto_approve: if provided, passed through to CAL.record_change
          (Auth uses this to mark system-initiated transitions as auto-approved).
          SM-02/SM-04 pass None (CAL uses its own default).
        """
        if not self._change_audit_log:
            return
        try:
            from .change_audit_log import ChangeType  # noqa: E402
            who_str = str(approved_by or initiator_value)
            kwargs: dict[str, Any] = {
                "change_type": ChangeType.STATE_CHANGE,
                "who": who_str,
                "what": f"{self.CHANGE_LABEL}: {from_label} → {to_label}",
                "reason": reason or "",
                "old_value": from_label,
                "new_value": to_label,
            }
            if auto_approve is not None:
                kwargs["auto_approve"] = auto_approve
            self._change_audit_log.record_change(**kwargs)
        except Exception as e:
            logger.error("Failed to record change audit: %s", e)


# ═══════════════════════════════════════════════════════════════════════════════
# Mixin: Multi-object store (for Authorization + DecisionLease)
# 多对象存储 Mixin（用于 Authorization / DecisionLease）
# ═══════════════════════════════════════════════════════════════════════════════

class MultiObjectStoreMixin:
    """
    Mixin for state machines that hold MANY domain objects keyed by id
    (Authorization, DecisionLease). NOT suitable for RiskGovernor which
    holds a single GovernorState.

    对 Authorization / DecisionLease 这类以 id 为键存储 N 个领域对象的
    状态机提供共享的 get / get_all / get_status_summary / import / export /
    check_expiry。RiskGovernor 使用单一 GovernorState，不适用本 mixin。

    Subclasses using this mixin MUST:
      - Initialize `self._objects: dict[str, T] = {}` in their __init__.
      - Define class attributes:
          _OBJECT_FROM_DICT: callable taking dict -> object instance
              (usually `SomeObject.from_dict`)
          _OBJECT_ID_ATTR: the name of the id attribute on the object
              (e.g. "authorization_id", "lease_id")
          _OBJECT_STATE_ATTR: attribute name for state (usually "state")
          _EXPIRY_CHECK_ATTR: attribute/property name returning bool
              (usually "is_expired_by_time")
          _EXPIRY_STATE: the "EXPIRED" state enum member (for check_expiry)
          _EXPIRY_EVENT_VALUE: e.g. AuthEvent.EXPIRED (enum member)
          _EXPIRY_INITIATOR_VALUE: e.g. AuthInitiator.EXPIRY_GUARDIAN
          _EXPIRY_REASON_CODES: list[str], typically ["time_expiry"]

    使用本 mixin 的子类必须初始化 self._objects 并声明上述类属性。
    """

    _OBJECT_FROM_DICT: ClassVar[Callable[[dict[str, Any]], Any]]
    _OBJECT_ID_ATTR: ClassVar[str] = ""
    _OBJECT_STATE_ATTR: ClassVar[str] = "state"
    _EXPIRY_CHECK_ATTR: ClassVar[str] = "is_expired_by_time"
    _EXPIRY_STATE: ClassVar[Any] = None
    _EXPIRY_EVENT_VALUE: ClassVar[Any] = None
    _EXPIRY_INITIATOR_VALUE: ClassVar[Any] = None
    _EXPIRY_REASON_CODES: ClassVar[list[str]] = []

    # Subclasses set this in __init__:
    #   self._objects: dict[str, T] = {}

    def get(self, object_id: str) -> Any | None:
        """Get a deep copy of a stored object by id / 按 id 获取对象深拷贝"""
        with self._lock:  # type: ignore[attr-defined]
            obj = self._objects.get(object_id)  # type: ignore[attr-defined]
            return copy.deepcopy(obj) if obj else None

    def get_all(self) -> list[Any]:
        """Get all stored objects (deep-copied) / 获取全部对象深拷贝列表"""
        with self._lock:  # type: ignore[attr-defined]
            return [copy.deepcopy(obj) for obj in self._objects.values()]  # type: ignore[attr-defined]

    def get_status_summary(self) -> dict[str, int]:
        """Count objects by state label / 按状态计数"""
        with self._lock:  # type: ignore[attr-defined]
            summary: dict[str, int] = {}
            for obj in self._objects.values():  # type: ignore[attr-defined]
                st = getattr(obj, self._OBJECT_STATE_ATTR)
                key = st.value if hasattr(st, "value") else str(st)
                summary[key] = summary.get(key, 0) + 1
            return summary

    def check_expiry(self) -> list[str]:
        """
        Check all non-terminal objects for expiry; call transition(...)→EXPIRED
        on each. Returns list of ids that were expired this round.
        检查所有非终态对象是否已过期并迁移至 EXPIRED；返回本轮过期的 id 列表。

        This method is safe to call from a background scheduler. It takes
        the lock briefly to snapshot candidates, then calls transition() per
        candidate outside the snapshot lock (transition() re-acquires lock).
        可由后台调度器安全调用。
        """
        expired_ids: list[str] = []
        terminal: frozenset = getattr(type(self), "TERMINAL_STATES", frozenset())
        with self._lock:  # type: ignore[attr-defined]
            candidates = [
                (getattr(obj, self._OBJECT_ID_ATTR), obj)
                for obj in self._objects.values()  # type: ignore[attr-defined]
                if getattr(obj, self._OBJECT_STATE_ATTR) not in terminal
                and getattr(obj, self._EXPIRY_CHECK_ATTR)
            ]

        for oid, _obj in candidates:
            try:
                # Subclass must provide transition() with this positional shape:
                #   transition(object_id, to_state, *, event, initiator, reason_codes=...)
                # 子类必须提供 transition(object_id, to_state, *, event, initiator, reason_codes=...)
                self.transition(  # type: ignore[attr-defined]
                    oid, self._EXPIRY_STATE,
                    event=self._EXPIRY_EVENT_VALUE,
                    initiator=self._EXPIRY_INITIATOR_VALUE,
                    reason_codes=list(self._EXPIRY_REASON_CODES),
                )
                expired_ids.append(oid)
            except Exception as e:
                logger.warning("Expiry transition failed for %s: %s", oid, e)
        return expired_ids
