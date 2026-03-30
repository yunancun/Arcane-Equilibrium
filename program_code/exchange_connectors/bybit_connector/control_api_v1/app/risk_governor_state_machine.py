"""
Risk Governor State Machine — 6-Level Risk Governance Implementation
风控总督状态机 — 6 级风控治理实现

MODULE_NOTE (中文):
  本模块实现 EX-01 §7 / GAP-C3 要求的 6 级正式风控状态机：
  - NORMAL: 正常运营，所有功能可用
  - CAUTIOUS: 谨慎模式，缩减仓位规模，提高警觉
  - REDUCED: 收缩模式，仅允许减仓和保护性操作
  - DEFENSIVE: 防守模式，主动平仓高风险头寸
  - CIRCUIT_BREAKER: 熔断模式，所有交易暂停，紧急止损生效
  - MANUAL_REVIEW: 人工审核模式，系统等待操作员介入

  核心安全不变量：
  - 升级（更严格）可以自动触发
  - 降级（更宽松）通常需要审批
  - 熔断和人工审核状态的退出必须有操作员确认
  - 每次状态迁移生成 risk_governor_transition 审计对象
  - 与现有 RiskManager 的 risk_pressure 和 check_positions_on_tick 集成

MODULE_NOTE (English):
  Implements the 6-level Risk Governor State Machine per EX-01 §7 / GAP-C3:
  - NORMAL: Full operations, all features available
  - CAUTIOUS: Reduced sizing, heightened alertness
  - REDUCED: Reduce-only mode, protective actions only
  - DEFENSIVE: Active de-risking of high-risk positions
  - CIRCUIT_BREAKER: All trading halted, emergency stops active
  - MANUAL_REVIEW: System awaits operator intervention

  Core safety invariants:
  - Escalation (stricter) can be automatic
  - De-escalation (looser) generally requires approval
  - Circuit breaker and manual review exit requires operator confirmation
  - Each transition emits a risk_governor_transition audit object
  - Integrates with existing RiskManager risk_pressure and check_positions_on_tick

Safety invariant:
  - Escalation can happen automatically, de-escalation requires governance
  - CIRCUIT_BREAKER cannot be bypassed — only MANUAL_REVIEW or NORMAL via operator
  - The governor NEVER loosens risk beyond what RiskManager P0/P1 allows
  - GUI / Learning / Strategy layers CANNOT directly modify governor state
"""

from __future__ import annotations

import copy
import hashlib
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Risk Levels / 风控等级
# ═══════════════════════════════════════════════════════════════════════════════

class RiskLevel(IntEnum):
    """
    6-level risk governance scale. Higher value = stricter.
    6 级风控治理等级。数值越高 = 越严格。

    EX-01 §7 + §3 + GAP-C3:
      NORMAL(0) < CAUTIOUS(1) < REDUCED(2) < DEFENSIVE(3) < CIRCUIT_BREAKER(4) < MANUAL_REVIEW(5)
    """
    NORMAL = 0
    CAUTIOUS = 1
    REDUCED = 2
    DEFENSIVE = 3
    CIRCUIT_BREAKER = 4
    MANUAL_REVIEW = 5


# ═══════════════════════════════════════════════════════════════════════════════
# Risk Events / 风控事件
# ═══════════════════════════════════════════════════════════════════════════════

class RiskEvent(str, Enum):
    """Formal events that can trigger risk level transitions / 触发风控等级迁移的正式事件"""

    # Escalation events / 升级事件
    DRAWDOWN_WARNING = "drawdown_warning"
    DRAWDOWN_CRITICAL = "drawdown_critical"
    DAILY_LOSS_WARNING = "daily_loss_warning"
    DAILY_LOSS_BREACH = "daily_loss_breach"
    CONSECUTIVE_LOSSES = "consecutive_loss_threshold"
    CORRELATION_BREACH = "correlation_breach"
    MARGIN_UTILIZATION_HIGH = "margin_utilization_high"
    HEALTH_DEGRADED = "health_degraded"
    MARKET_DATA_STALE = "market_data_stale"
    API_CONNECTIVITY_LOSS = "api_connectivity_loss"
    INCIDENT_TRIGGERED = "incident_triggered"
    OPERATOR_ESCALATION = "operator_escalation"

    # De-escalation events / 降级事件
    CONDITIONS_IMPROVED = "conditions_improved"
    OPERATOR_DE_ESCALATION = "operator_de_escalation"
    RECOVERY_APPROVED = "recovery_approved"
    MANUAL_REVIEW_COMPLETED = "manual_review_completed"

    # Direct transitions / 直接迁移
    OPERATOR_CIRCUIT_BREAK = "operator_circuit_break"
    OPERATOR_MANUAL_REVIEW = "operator_manual_review"
    OPERATOR_RESET_NORMAL = "operator_reset_normal"


class RiskInitiator(str, Enum):
    """Who can initiate risk level transitions / 风控等级迁移发起者"""
    RISK_GOVERNOR = "RiskGovernor"
    OPERATOR = "Operator"
    INCIDENT_POLICY = "IncidentPolicy"
    HEALTH_MONITOR = "HealthMonitor"
    EXPIRY_GUARDIAN = "ExpiryGuardian"


# ═══════════════════════════════════════════════════════════════════════════════
# Transition Rules / 迁移规则
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class RiskTransitionRule:
    """Defines a valid risk level transition / 定义合法风控等级迁移"""
    from_level: RiskLevel
    to_level: RiskLevel
    direction: str  # "escalation" | "de_escalation" | "lateral"
    requires_approval: bool
    allowed_initiators: frozenset[RiskInitiator]
    description: str = ""


RISK_TRANSITION_RULES: dict[tuple[RiskLevel, RiskLevel], RiskTransitionRule] = {}


def _reg(from_l: RiskLevel, to_l: RiskLevel, direction: str, approval: bool,
         initiators: frozenset[RiskInitiator], desc: str = "") -> None:
    RISK_TRANSITION_RULES[(from_l, to_l)] = RiskTransitionRule(
        from_level=from_l, to_level=to_l,
        direction=direction,
        requires_approval=approval,
        allowed_initiators=initiators,
        description=desc,
    )


_AUTO = frozenset({RiskInitiator.RISK_GOVERNOR, RiskInitiator.OPERATOR,
                    RiskInitiator.INCIDENT_POLICY, RiskInitiator.HEALTH_MONITOR})
_OPERATOR_GOV = frozenset({RiskInitiator.OPERATOR, RiskInitiator.RISK_GOVERNOR})
_OPERATOR_ONLY = frozenset({RiskInitiator.OPERATOR})
_ALL = frozenset({RiskInitiator.RISK_GOVERNOR, RiskInitiator.OPERATOR,
                   RiskInitiator.INCIDENT_POLICY, RiskInitiator.HEALTH_MONITOR,
                   RiskInitiator.EXPIRY_GUARDIAN})

# ── Escalation (auto, no approval needed) / 升级（自动，不需审批）──
_reg(RiskLevel.NORMAL, RiskLevel.CAUTIOUS, "escalation", False, _AUTO,
     "Enter cautious mode / 进入谨慎模式")
_reg(RiskLevel.NORMAL, RiskLevel.REDUCED, "escalation", False, _AUTO,
     "Skip to reduced mode / 跳级至收缩模式")
_reg(RiskLevel.NORMAL, RiskLevel.DEFENSIVE, "escalation", False, _AUTO,
     "Skip to defensive mode / 跳级至防守模式")
_reg(RiskLevel.NORMAL, RiskLevel.CIRCUIT_BREAKER, "escalation", False, _AUTO,
     "Emergency circuit break / 紧急熔断")
_reg(RiskLevel.NORMAL, RiskLevel.MANUAL_REVIEW, "escalation", False, _OPERATOR_GOV,
     "Direct to manual review / 直接进入人工审核")

_reg(RiskLevel.CAUTIOUS, RiskLevel.REDUCED, "escalation", False, _AUTO,
     "Escalate to reduced / 升级至收缩模式")
_reg(RiskLevel.CAUTIOUS, RiskLevel.DEFENSIVE, "escalation", False, _AUTO,
     "Skip to defensive / 跳级至防守模式")
_reg(RiskLevel.CAUTIOUS, RiskLevel.CIRCUIT_BREAKER, "escalation", False, _AUTO,
     "Emergency circuit break / 紧急熔断")
_reg(RiskLevel.CAUTIOUS, RiskLevel.MANUAL_REVIEW, "escalation", False, _OPERATOR_GOV,
     "Manual review from cautious / 从谨慎进入人工审核")

_reg(RiskLevel.REDUCED, RiskLevel.DEFENSIVE, "escalation", False, _AUTO,
     "Escalate to defensive / 升级至防守模式")
_reg(RiskLevel.REDUCED, RiskLevel.CIRCUIT_BREAKER, "escalation", False, _AUTO,
     "Emergency circuit break / 紧急熔断")
_reg(RiskLevel.REDUCED, RiskLevel.MANUAL_REVIEW, "escalation", False, _OPERATOR_GOV,
     "Manual review from reduced / 从收缩进入人工审核")

_reg(RiskLevel.DEFENSIVE, RiskLevel.CIRCUIT_BREAKER, "escalation", False, _AUTO,
     "Escalate to circuit breaker / 升级至熔断")
_reg(RiskLevel.DEFENSIVE, RiskLevel.MANUAL_REVIEW, "escalation", False, _OPERATOR_GOV,
     "Manual review from defensive / 从防守进入人工审核")

_reg(RiskLevel.CIRCUIT_BREAKER, RiskLevel.MANUAL_REVIEW, "lateral", False, _OPERATOR_GOV,
     "Circuit breaker to manual review / 熔断转人工审核")

# ── De-escalation (requires approval) / 降级（需要审批）──
_reg(RiskLevel.CAUTIOUS, RiskLevel.NORMAL, "de_escalation", True, _OPERATOR_GOV,
     "Return to normal from cautious / 从谨慎恢复正常")
_reg(RiskLevel.REDUCED, RiskLevel.CAUTIOUS, "de_escalation", True, _OPERATOR_GOV,
     "De-escalate to cautious / 降级至谨慎")
_reg(RiskLevel.REDUCED, RiskLevel.NORMAL, "de_escalation", True, _OPERATOR_ONLY,
     "Skip de-escalate to normal / 跳级降至正常（仅操作员）")
_reg(RiskLevel.DEFENSIVE, RiskLevel.REDUCED, "de_escalation", True, _OPERATOR_GOV,
     "De-escalate to reduced / 降级至收缩")
_reg(RiskLevel.DEFENSIVE, RiskLevel.CAUTIOUS, "de_escalation", True, _OPERATOR_ONLY,
     "Skip de-escalate to cautious / 跳级降至谨慎（仅操作员）")
_reg(RiskLevel.CIRCUIT_BREAKER, RiskLevel.DEFENSIVE, "de_escalation", True, _OPERATOR_ONLY,
     "De-escalate from circuit breaker to defensive / 从熔断降级至防守（仅操作员）")
_reg(RiskLevel.CIRCUIT_BREAKER, RiskLevel.MANUAL_REVIEW, "lateral", False, _OPERATOR_GOV,
     "Move to manual review / 转入人工审核")
_reg(RiskLevel.MANUAL_REVIEW, RiskLevel.DEFENSIVE, "de_escalation", True, _OPERATOR_ONLY,
     "Resume to defensive after review / 审核后恢复至防守")
_reg(RiskLevel.MANUAL_REVIEW, RiskLevel.REDUCED, "de_escalation", True, _OPERATOR_ONLY,
     "Resume to reduced after review / 审核后恢复至收缩")
_reg(RiskLevel.MANUAL_REVIEW, RiskLevel.CAUTIOUS, "de_escalation", True, _OPERATOR_ONLY,
     "Resume to cautious after review / 审核后恢复至谨慎")
_reg(RiskLevel.MANUAL_REVIEW, RiskLevel.NORMAL, "de_escalation", True, _OPERATOR_ONLY,
     "Full reset to normal after review / 审核后完全恢复正常")


# ═══════════════════════════════════════════════════════════════════════════════
# Level Behavior Constraints / 等级行为约束
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class LevelConstraints:
    """
    Behavioral constraints for each risk level.
    每个风控等级的行为约束。
    """
    new_entries_allowed: bool
    position_size_multiplier: float  # 0.0 - 1.0 applied on top of P2
    reduce_only: bool
    active_de_risking: bool  # Governor actively seeks to close positions
    emergency_stops: bool    # Hard emergency stops placed
    requires_operator: bool  # System waits for operator action
    description: str = ""


LEVEL_CONSTRAINTS: dict[RiskLevel, LevelConstraints] = {
    RiskLevel.NORMAL: LevelConstraints(
        new_entries_allowed=True,
        position_size_multiplier=1.0,
        reduce_only=False,
        active_de_risking=False,
        emergency_stops=False,
        requires_operator=False,
        description="Full operations / 正常运营",
    ),
    RiskLevel.CAUTIOUS: LevelConstraints(
        new_entries_allowed=True,
        position_size_multiplier=0.7,
        reduce_only=False,
        active_de_risking=False,
        emergency_stops=False,
        requires_operator=False,
        description="Reduced sizing, heightened alertness / 缩减仓位，提高警觉",
    ),
    RiskLevel.REDUCED: LevelConstraints(
        new_entries_allowed=False,
        position_size_multiplier=0.5,
        reduce_only=True,
        active_de_risking=False,
        emergency_stops=False,
        requires_operator=False,
        description="Reduce-only mode / 仅允许减仓",
    ),
    RiskLevel.DEFENSIVE: LevelConstraints(
        new_entries_allowed=False,
        position_size_multiplier=0.0,
        reduce_only=True,
        active_de_risking=True,
        emergency_stops=False,
        requires_operator=False,
        description="Active de-risking / 主动去风险化",
    ),
    RiskLevel.CIRCUIT_BREAKER: LevelConstraints(
        new_entries_allowed=False,
        position_size_multiplier=0.0,
        reduce_only=True,
        active_de_risking=True,
        emergency_stops=True,
        requires_operator=True,
        description="All trading halted, emergency stops / 交易全停，紧急止损",
    ),
    RiskLevel.MANUAL_REVIEW: LevelConstraints(
        new_entries_allowed=False,
        position_size_multiplier=0.0,
        reduce_only=True,
        active_de_risking=False,
        emergency_stops=True,
        requires_operator=True,
        description="Awaiting operator intervention / 等待操作员介入",
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
# Escalation Thresholds / 升级阈值
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class EscalationThresholds:
    """
    Configurable thresholds for automatic risk level escalation.
    可配置的自动风控等级升级阈值。

    Based on EX-01 §3 (Guardian adaptive), §7 (Circuit Breakers), Table 5, Table 10.
    """
    # Drawdown thresholds (% from peak) / 回撤阈值（距峰值%）
    drawdown_cautious_pct: float = 5.0
    drawdown_reduced_pct: float = 8.0
    drawdown_defensive_pct: float = 12.0
    drawdown_circuit_breaker_pct: float = 15.0  # EX-01 Table 10: max_drawdown_pct

    # Daily loss thresholds / 日内亏损阈值
    daily_loss_cautious_pct: float = 2.0
    daily_loss_reduced_pct: float = 3.5
    daily_loss_circuit_breaker_pct: float = 5.0  # EX-01 Table 10: max_daily_loss

    # Consecutive losses / 连续亏损
    consecutive_loss_cautious: int = 3
    consecutive_loss_reduced: int = 5
    consecutive_loss_circuit_breaker: int = 10  # EX-01 Table 10

    # Risk pressure (from RiskManager.get_risk_context_for_ai) / 风险压力
    pressure_cautious: float = 0.3
    pressure_reduced: float = 0.5
    pressure_defensive: float = 0.7
    pressure_circuit_breaker: float = 0.9

    # System health / 系统健康
    health_degraded_triggers_level: RiskLevel = RiskLevel.REDUCED
    market_data_stale_triggers_level: RiskLevel = RiskLevel.CIRCUIT_BREAKER
    api_loss_triggers_level: RiskLevel = RiskLevel.CIRCUIT_BREAKER

    # Cooldown before de-escalation (seconds) / 降级前冷却时间（秒）
    min_hold_time_seconds: float = 300.0  # Must stay at level ≥5 min before de-escalating

    def to_dict(self) -> dict[str, Any]:
        d = {}
        for k, v in self.__dict__.items():
            if isinstance(v, RiskLevel):
                d[k] = v.name
            else:
                d[k] = v
        return d


# ═══════════════════════════════════════════════════════════════════════════════
# Governor State / 总督状态
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class GovernorState:
    """Snapshot of the Risk Governor's current state / 风控总督当前状态快照"""
    level: RiskLevel = RiskLevel.NORMAL
    level_entered_at_ms: int = 0
    consecutive_escalations: int = 0
    last_event: str = ""
    last_initiator: str = ""
    last_reason: str = ""
    transitions: list[dict[str, Any]] = field(default_factory=list)
    version: int = 1

    def __post_init__(self) -> None:
        if not self.level_entered_at_ms:
            self.level_entered_at_ms = int(time.time() * 1000)


# ═══════════════════════════════════════════════════════════════════════════════
# Transition Record / 迁移记录
# ═══════════════════════════════════════════════════════════════════════════════

def _build_risk_transition_record(
    state: GovernorState,
    to_level: RiskLevel,
    event: RiskEvent,
    initiator: RiskInitiator,
    reason_codes: list[str] | None = None,
    approved_by: str | None = None,
    metrics_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build risk_governor_transition audit object / 构建风控迁移审计对象"""
    now_ms = int(time.time() * 1000)
    tid = f"rgt:{uuid.uuid4().hex[:12]}"
    return {
        "transition_id": tid,
        "previous_level": state.level.name,
        "next_level": to_level.name,
        "trigger_event": event.value,
        "trigger_event_id": f"revt:{uuid.uuid4().hex[:8]}",
        "initiated_by": initiator.value,
        "reason_codes": reason_codes or [],
        "direction": "escalation" if to_level > state.level else "de_escalation" if to_level < state.level else "lateral",
        "approval_required": RISK_TRANSITION_RULES.get(
            (state.level, to_level), RiskTransitionRule(state.level, to_level, "lateral", False, frozenset())
        ).requires_approval,
        "approved_by": approved_by,
        "effective_at_ms": now_ms,
        "level_held_ms": now_ms - state.level_entered_at_ms,
        "metrics_snapshot": metrics_snapshot or {},
        "audit_event_ref": f"raud:{hashlib.sha256(tid.encode()).hexdigest()[:16]}",
        "version_before": state.version,
        "version_after": state.version + 1,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Risk Governor Error / 风控总督异常
# ═══════════════════════════════════════════════════════════════════════════════

class RiskGovernorError(Exception):
    """Raised when an invalid risk level transition is attempted / 非法风控迁移"""
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# Risk Governor State Machine / 风控总督状态机
# ═══════════════════════════════════════════════════════════════════════════════

class RiskGovernorStateMachine:
    """
    6-Level Risk Governor with automatic escalation and governed de-escalation.
    6 级风控总督，自动升级 + 受治理降级。

    Thread-safe. Integrates with RiskManager risk_pressure for auto-escalation.
    线程安全。与 RiskManager risk_pressure 集成进行自动升级。
    """

    def __init__(
        self,
        thresholds: EscalationThresholds | None = None,
        audit_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._state = GovernorState()
        self._thresholds = thresholds or EscalationThresholds()
        self._audit_callback = audit_callback
        self._change_audit_log = None  # T5.02: Optional ChangeAuditLog for WHO/WHEN/APPROVAL tracking

    # ── T5.02: Change Audit Log Injection / 變更審計日誌注入 ──

    def set_change_audit_log(self, cal: Any) -> None:
        """Inject ChangeAuditLog for WHO/WHEN/APPROVAL tracking / 注入變更審計日誌"""
        with self._lock:
            self._change_audit_log = cal

    # ── Properties ──

    @property
    def level(self) -> RiskLevel:
        with self._lock:
            return self._state.level

    @property
    def constraints(self) -> LevelConstraints:
        return LEVEL_CONSTRAINTS[self.level]

    # ── Core Transition ──

    def transition(
        self,
        to_level: RiskLevel,
        *,
        event: RiskEvent,
        initiator: RiskInitiator,
        reason_codes: list[str] | None = None,
        approved_by: str | None = None,
        reason: str = "",
        metrics_snapshot: dict[str, Any] | None = None,
    ) -> GovernorState:
        """
        Execute a risk level transition.
        执行风控等级迁移。

        Validates:
        1. Transition is in the valid transition table
        2. Initiator is allowed
        3. If approval required, approved_by must be provided
        4. For de-escalation, min hold time must be met
        """
        with self._lock:
            from_level = self._state.level

            # Same level = no-op
            if from_level == to_level:
                return copy.deepcopy(self._state)

            # Check valid transition
            rule = RISK_TRANSITION_RULES.get((from_level, to_level))
            if rule is None:
                raise RiskGovernorError(
                    f"Invalid transition: {from_level.name} → {to_level.name} "
                    f"(not in transition table) / 非法迁移"
                )

            # Check initiator
            if initiator not in rule.allowed_initiators:
                raise RiskGovernorError(
                    f"Initiator {initiator.value} not allowed for "
                    f"{from_level.name} → {to_level.name}. "
                    f"Allowed: {[i.value for i in rule.allowed_initiators]} / 发起者不被允许"
                )

            # Check approval for de-escalation
            if rule.requires_approval and not approved_by:
                raise RiskGovernorError(
                    f"Transition {from_level.name} → {to_level.name} requires "
                    f"explicit approval (approved_by must be provided) / 需要审批"
                )

            # Check min hold time for de-escalation
            if rule.direction == "de_escalation":
                now_ms = int(time.time() * 1000)
                held_ms = now_ms - self._state.level_entered_at_ms
                min_hold_ms = int(self._thresholds.min_hold_time_seconds * 1000)
                if held_ms < min_hold_ms:
                    remaining_s = (min_hold_ms - held_ms) / 1000
                    raise RiskGovernorError(
                        f"Must hold at {from_level.name} for at least "
                        f"{self._thresholds.min_hold_time_seconds}s before de-escalation. "
                        f"Remaining: {remaining_s:.0f}s / 降级前需保持最低时间"
                    )

            # Build audit record
            record = _build_risk_transition_record(
                self._state, to_level, event, initiator,
                reason_codes=reason_codes,
                approved_by=approved_by,
                metrics_snapshot=metrics_snapshot,
            )

            # Execute transition
            self._state.level = to_level
            self._state.level_entered_at_ms = int(time.time() * 1000)
            self._state.version += 1
            self._state.last_event = event.value
            self._state.last_initiator = initiator.value
            self._state.last_reason = reason
            self._state.transitions.append(record)

            if to_level > from_level:
                self._state.consecutive_escalations += 1
            else:
                self._state.consecutive_escalations = 0

            # T5.02: Record state change to ChangeAuditLog if available
            if self._change_audit_log:
                try:
                    from .change_audit_log import ChangeType  # noqa: E402
                    self._change_audit_log.record_change(
                        change_type=ChangeType.STATE_CHANGE,
                        who=str(approved_by or initiator.value),
                        what=f"RiskGovernor: {from_level.name} → {to_level.name}",
                        reason=reason or "",
                        old_value=from_level.name,
                        new_value=to_level.name,
                    )
                except Exception as e:
                    logger.error(f"Failed to record change audit: {e}")

            result = copy.deepcopy(self._state)

        self._emit_audit(record)
        logger.info(
            "Risk Governor: %s → %s (event=%s, by=%s) / 风控等级迁移",
            from_level.name, to_level.name, event.value, initiator.value,
        )
        return result

    # ── Convenience: Escalation / 便捷：升级 ──

    def escalate_to(self, level: RiskLevel, *, reason: str,
                    event: RiskEvent = RiskEvent.OPERATOR_ESCALATION,
                    initiator: RiskInitiator = RiskInitiator.RISK_GOVERNOR,
                    metrics_snapshot: dict[str, Any] | None = None) -> GovernorState:
        """Escalate to a higher risk level / 升级至更高风控等级"""
        return self.transition(
            level, event=event, initiator=initiator,
            reason=reason, reason_codes=["escalation"],
            metrics_snapshot=metrics_snapshot,
        )

    def de_escalate_to(self, level: RiskLevel, *, approved_by: str, reason: str = "",
                       initiator: RiskInitiator = RiskInitiator.OPERATOR) -> GovernorState:
        """De-escalate to a lower risk level (requires approval) / 降级（需审批）"""
        return self.transition(
            level, event=RiskEvent.RECOVERY_APPROVED, initiator=initiator,
            approved_by=approved_by, reason=reason,
            reason_codes=["de_escalation_approved"],
        )

    def circuit_break(self, *, reason: str,
                      initiator: RiskInitiator = RiskInitiator.RISK_GOVERNOR,
                      metrics_snapshot: dict[str, Any] | None = None) -> GovernorState:
        """Emergency circuit breaker activation / 紧急熔断"""
        return self.transition(
            RiskLevel.CIRCUIT_BREAKER,
            event=RiskEvent.OPERATOR_CIRCUIT_BREAK if initiator == RiskInitiator.OPERATOR
                  else RiskEvent.INCIDENT_TRIGGERED,
            initiator=initiator,
            reason=reason,
            reason_codes=["circuit_breaker"],
            metrics_snapshot=metrics_snapshot,
        )

    def request_manual_review(self, *, reason: str,
                              initiator: RiskInitiator = RiskInitiator.OPERATOR) -> GovernorState:
        """Request manual review / 请求人工审核"""
        return self.transition(
            RiskLevel.MANUAL_REVIEW,
            event=RiskEvent.OPERATOR_MANUAL_REVIEW,
            initiator=initiator,
            reason=reason,
            reason_codes=["manual_review_requested"],
        )

    def complete_manual_review(self, *, approved_by: str, resume_to: RiskLevel,
                               reason: str = "") -> GovernorState:
        """Complete manual review and resume operations / 完成人工审核恢复运营"""
        return self.transition(
            resume_to,
            event=RiskEvent.MANUAL_REVIEW_COMPLETED,
            initiator=RiskInitiator.OPERATOR,
            approved_by=approved_by,
            reason=reason,
            reason_codes=["manual_review_completed"],
        )

    # ── Auto-Evaluation / 自动评估 ──

    def evaluate_risk_context(self, risk_context: dict[str, Any]) -> GovernorState | None:
        """
        Evaluate current risk metrics and auto-escalate if thresholds are breached.
        评估当前风控指标，超阈值时自动升级。

        This should be called on each tick with RiskManager.get_risk_context_for_ai() output.
        应在每次 tick 时用 RiskManager.get_risk_context_for_ai() 的输出调用。

        Returns new state if a transition occurred, None otherwise.
        如果发生迁移返回新状态，否则返回 None。
        """
        t = self._thresholds
        current = self.level

        # Determine target level based on metrics / 根据指标确定目标等级
        target = RiskLevel.NORMAL
        reason_parts: list[str] = []

        # 1. Risk pressure (composite metric) / 风险压力（综合指标）
        pressure = risk_context.get("risk_pressure", 0.0)
        if pressure >= t.pressure_circuit_breaker:
            target = max(target, RiskLevel.CIRCUIT_BREAKER)
            reason_parts.append(f"pressure={pressure:.2f}>=CB")
        elif pressure >= t.pressure_defensive:
            target = max(target, RiskLevel.DEFENSIVE)
            reason_parts.append(f"pressure={pressure:.2f}>=DEF")
        elif pressure >= t.pressure_reduced:
            target = max(target, RiskLevel.REDUCED)
            reason_parts.append(f"pressure={pressure:.2f}>=RED")
        elif pressure >= t.pressure_cautious:
            target = max(target, RiskLevel.CAUTIOUS)
            reason_parts.append(f"pressure={pressure:.2f}>=CAU")

        # 2. Drawdown / 回撤
        dd = risk_context.get("drawdown_pct", 0.0)
        if dd >= t.drawdown_circuit_breaker_pct:
            target = max(target, RiskLevel.CIRCUIT_BREAKER)
            reason_parts.append(f"dd={dd:.1f}%>=CB")
        elif dd >= t.drawdown_defensive_pct:
            target = max(target, RiskLevel.DEFENSIVE)
            reason_parts.append(f"dd={dd:.1f}%>=DEF")
        elif dd >= t.drawdown_reduced_pct:
            target = max(target, RiskLevel.REDUCED)
            reason_parts.append(f"dd={dd:.1f}%>=RED")
        elif dd >= t.drawdown_cautious_pct:
            target = max(target, RiskLevel.CAUTIOUS)
            reason_parts.append(f"dd={dd:.1f}%>=CAU")

        # 3. Daily loss / 日内亏损
        dl = risk_context.get("daily_loss_pct", 0.0)
        if dl >= t.daily_loss_circuit_breaker_pct:
            target = max(target, RiskLevel.CIRCUIT_BREAKER)
            reason_parts.append(f"daily_loss={dl:.1f}%>=CB")
        elif dl >= t.daily_loss_reduced_pct:
            target = max(target, RiskLevel.REDUCED)
            reason_parts.append(f"daily_loss={dl:.1f}%>=RED")
        elif dl >= t.daily_loss_cautious_pct:
            target = max(target, RiskLevel.CAUTIOUS)
            reason_parts.append(f"daily_loss={dl:.1f}%>=CAU")

        # 4. Consecutive losses / 连续亏损
        cl = risk_context.get("consecutive_losses", 0)
        if cl >= t.consecutive_loss_circuit_breaker:
            target = max(target, RiskLevel.CIRCUIT_BREAKER)
            reason_parts.append(f"consec_loss={cl}>=CB")
        elif cl >= t.consecutive_loss_reduced:
            target = max(target, RiskLevel.REDUCED)
            reason_parts.append(f"consec_loss={cl}>=RED")
        elif cl >= t.consecutive_loss_cautious:
            target = max(target, RiskLevel.CAUTIOUS)
            reason_parts.append(f"consec_loss={cl}>=CAU")

        # 5. Session halted → circuit breaker / session 已暂停 → 熔断
        if risk_context.get("session_halted"):
            target = max(target, RiskLevel.CIRCUIT_BREAKER)
            reason_parts.append("session_halted")

        # 6. Cooldown active → at least reduced / 冷却中 → 至少收缩
        if risk_context.get("cooldown_active"):
            target = max(target, RiskLevel.REDUCED)
            reason_parts.append("cooldown_active")

        # Only escalate (never auto-de-escalate) / 仅升级（不自动降级）
        if target > current:
            reason = "; ".join(reason_parts)
            try:
                return self.escalate_to(
                    target, reason=reason,
                    event=RiskEvent.DRAWDOWN_CRITICAL if dd >= t.drawdown_defensive_pct
                          else RiskEvent.DAILY_LOSS_BREACH if dl >= t.daily_loss_reduced_pct
                          else RiskEvent.CONSECUTIVE_LOSSES if cl >= t.consecutive_loss_reduced
                          else RiskEvent.DRAWDOWN_WARNING,
                    metrics_snapshot=risk_context,
                )
            except RiskGovernorError as e:
                logger.warning("Auto-escalation failed: %s", e)
                return None

        return None

    # ── Health Event Handlers / 健康事件处理 ──

    def on_health_degraded(self, *, reason: str = "system health degraded") -> GovernorState | None:
        """Handle system health degradation / 处理系统健康降级"""
        target = self._thresholds.health_degraded_triggers_level
        if target > self.level:
            return self.escalate_to(
                target, reason=reason,
                event=RiskEvent.HEALTH_DEGRADED,
                initiator=RiskInitiator.HEALTH_MONITOR,
            )
        return None

    def on_market_data_stale(self, *, reason: str = "market data stale > 2min") -> GovernorState | None:
        """Handle stale market data / 处理市场数据过期"""
        target = self._thresholds.market_data_stale_triggers_level
        if target > self.level:
            return self.escalate_to(
                target, reason=reason,
                event=RiskEvent.MARKET_DATA_STALE,
                initiator=RiskInitiator.HEALTH_MONITOR,
            )
        return None

    def on_api_connectivity_loss(self, *, reason: str = "API connectivity lost > 60s") -> GovernorState | None:
        """Handle API connectivity loss / 处理 API 连接丢失"""
        target = self._thresholds.api_loss_triggers_level
        if target > self.level:
            return self.escalate_to(
                target, reason=reason,
                event=RiskEvent.API_CONNECTIVITY_LOSS,
                initiator=RiskInitiator.HEALTH_MONITOR,
            )
        return None

    # ── Query / 查询 ──

    def get_state(self) -> GovernorState:
        """Get a copy of current governor state / 获取当前状态副本"""
        with self._lock:
            return copy.deepcopy(self._state)

    def get_constraints(self) -> LevelConstraints:
        """Get behavioral constraints for current level / 获取当前等级行为约束"""
        return LEVEL_CONSTRAINTS[self.level]

    def get_status(self) -> dict[str, Any]:
        """Get status summary for API/GUI / 获取状态摘要"""
        with self._lock:
            now_ms = int(time.time() * 1000)
            # Get constraints without calling self.level (which acquires lock again)
            constraints_obj = LEVEL_CONSTRAINTS[self._state.level]
            return {
                "level": self._state.level.name,
                "level_value": self._state.level.value,
                "level_entered_at_ms": self._state.level_entered_at_ms,
                "level_held_seconds": (now_ms - self._state.level_entered_at_ms) / 1000,
                "consecutive_escalations": self._state.consecutive_escalations,
                "last_event": self._state.last_event,
                "last_initiator": self._state.last_initiator,
                "last_reason": self._state.last_reason,
                "version": self._state.version,
                "transition_count": len(self._state.transitions),
                "constraints": {
                    "new_entries_allowed": constraints_obj.new_entries_allowed,
                    "position_size_multiplier": constraints_obj.position_size_multiplier,
                    "reduce_only": constraints_obj.reduce_only,
                    "active_de_risking": constraints_obj.active_de_risking,
                    "emergency_stops": constraints_obj.emergency_stops,
                    "requires_operator": constraints_obj.requires_operator,
                },
            }

    def is_order_allowed(self, is_reducing: bool = False) -> tuple[bool, str]:
        """
        Check if an order is allowed under current risk level.
        检查当前风控等级下订单是否被允许。

        Returns (allowed, reason).
        """
        c = self.constraints
        if c.requires_operator:
            return False, f"risk_level_{self.level.name}_requires_operator_intervention"
        if not is_reducing:
            if not c.new_entries_allowed:
                return False, f"risk_level_{self.level.name}_no_new_entries"
        return True, "ok"

    # ── Persistence / 持久化 ──

    def export_state(self) -> dict[str, Any]:
        """Export state for persistence / 导出状态"""
        with self._lock:
            return {
                "level": self._state.level.name,
                "level_entered_at_ms": self._state.level_entered_at_ms,
                "consecutive_escalations": self._state.consecutive_escalations,
                "last_event": self._state.last_event,
                "last_initiator": self._state.last_initiator,
                "last_reason": self._state.last_reason,
                "transitions": self._state.transitions,
                "version": self._state.version,
                "thresholds": self._thresholds.to_dict(),
            }

    def import_state(self, data: dict[str, Any]) -> None:
        """Import state from persistence / 从持久化数据导入"""
        with self._lock:
            try:
                self._state.level = RiskLevel[data.get("level", "NORMAL")]
            except (KeyError, ValueError):
                self._state.level = RiskLevel.NORMAL
            self._state.level_entered_at_ms = data.get("level_entered_at_ms", int(time.time() * 1000))
            self._state.consecutive_escalations = data.get("consecutive_escalations", 0)
            self._state.last_event = data.get("last_event", "")
            self._state.last_initiator = data.get("last_initiator", "")
            self._state.last_reason = data.get("last_reason", "")
            self._state.transitions = data.get("transitions", [])
            self._state.version = data.get("version", 1)

    # ── Internal / 内部 ──

    def _emit_audit(self, record: dict[str, Any]) -> None:
        if self._audit_callback:
            try:
                self._audit_callback(record)
            except Exception:
                logger.exception("Risk governor audit callback error / 审计回调异常")
