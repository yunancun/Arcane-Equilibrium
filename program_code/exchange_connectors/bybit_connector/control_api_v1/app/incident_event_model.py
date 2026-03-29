"""
Incident Event Model + Formal Event Schema — DOC-07 / SM cross-cutting / GAP-H5 + GAP-M1
事故事件模型 + 正式事件架构

MODULE_NOTE (中文):
  实现 DOC-07 §2-§8 规范的正式事件模型和事故管理系统：
  - 5 级事件严重度：NOTICE → ANOMALY → NEAR_MISS → INCIDENT → CRITICAL_INCIDENT
  - 正式事件对象（Event）带唯一 ID、类型、时间戳、审计链引用
  - 事故记录（IncidentRecord）带影响范围、根因分类、恢复状态
  - 事故策略引擎（IncidentPolicy）：事件→状态机转换自动触发
  - 与 Authorization SM / Risk Governor SM / Reconciliation Engine 集成
  - 线程安全设计

MODULE_NOTE (English):
  Implements DOC-07 §2-§8 formal event model and incident management:
  - 5-level severity: NOTICE → ANOMALY → NEAR_MISS → INCIDENT → CRITICAL_INCIDENT
  - Formal Event object with unique ID, type, timestamp, audit chain ref
  - IncidentRecord with affected scope, root cause, recovery status
  - IncidentPolicy engine: event → state machine transition auto-triggering
  - Integrates with Authorization SM / Risk Governor SM / Reconciliation Engine
  - Thread-safe design

Safety invariant:
  - 升级（保守方向）= 自动，无需审批
  - 降级（宽松方向）= 需要审批 + 观察期
  - 事故记录不可删除不可修改（仅追加）
  - CRITICAL_INCIDENT 必须 CIRCUIT_BREAKER + FROZEN
"""

from __future__ import annotations

import copy
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum, Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Enums / 枚举
# ═══════════════════════════════════════════════════════════════════════════════

class EventSeverity(IntEnum):
    """5-level event severity hierarchy (DOC-07 §3) / 5 级事件严重度"""
    NOTICE = 0              # Observable, non-critical / 可观察，非关键
    ANOMALY = 1             # Deviation, warrants attention / 偏差，需关注
    NEAR_MISS = 2           # Would have caused incident / 险些事故
    INCIDENT = 3            # Real damage to behavior/safety / 真实影响
    CRITICAL_INCIDENT = 4   # Threatens account viability / 威胁账户安全


class RootCauseFamily(str, Enum):
    """Root cause classification (DOC-07 §8) / 根因分类"""
    STATE_CONFLICT = "state_conflict"       # Inconsistent state between systems
    EXECUTION_FAILURE = "execution_failure"  # Orders/fills not as expected
    RISK_GAP = "risk_gap"                   # Risk model failure or edge case
    AUDIT_GAP = "audit_gap"                 # Missing/incomplete audit trail
    AUTH_GAP = "auth_gap"                   # Authorization not enforced
    LOGIC_ERROR = "logic_error"             # Code/algorithm error
    EXTERNAL_FAILURE = "external_failure"   # Exchange/API/network failure
    UNKNOWN = "unknown"                     # Not yet determined


class IntegrityStatus(str, Enum):
    """System integrity assessment / 系统完整性评估"""
    INTACT = "intact"
    DEGRADED = "degraded"
    BROKEN = "broken"


class IncidentActionType(str, Enum):
    """Actions that IncidentPolicy can trigger / 事故策略可触发的动作"""
    RECORD_ONLY = "RECORD_ONLY"               # 仅记录
    INCREASE_MONITORING = "INCREASE_MONITORING" # 提升监控
    AUTH_RESTRICT = "AUTH_RESTRICT"             # 授权限制
    AUTH_FREEZE = "AUTH_FREEZE"                # 授权冻结
    RISK_ESCALATE_CAUTIOUS = "RISK_ESCALATE_CAUTIOUS"
    RISK_ESCALATE_REDUCED = "RISK_ESCALATE_REDUCED"
    RISK_ESCALATE_DEFENSIVE = "RISK_ESCALATE_DEFENSIVE"
    RISK_CIRCUIT_BREAKER = "RISK_CIRCUIT_BREAKER"
    TRADING_FREEZE = "TRADING_FREEZE"          # 交易冻结
    MANUAL_REVIEW = "MANUAL_REVIEW"            # 需人工审核
    OPERATOR_ALERT = "OPERATOR_ALERT"          # 运营商警报


# ═══════════════════════════════════════════════════════════════════════════════
# Formal Event Object (GAP-M1) / 正式事件对象
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Event:
    """
    Formal Event object — the canonical unit of system communication.
    正式事件对象 — 系统通信的基本单元。

    All state machine transitions, incident detections, and system signals
    are expressed as Events with unique IDs and full audit traceability.
    """
    event_id: str = ""
    event_type: str = ""              # e.g. "incident_confirmed", "risk_escalation"
    severity: EventSeverity = EventSeverity.NOTICE
    source: str = ""                  # Module that emitted: "risk_governor", "reconciliation", etc.
    triggered_at_ms: int = 0
    triggered_by: str = ""            # Actor: "Operator", "IncidentPolicy", "System"
    affected_objects: list = field(default_factory=list)  # IDs of affected entities
    reason_code: str = ""             # Classification: "state_conflict", "risk_gap"
    reason_detail: str = ""           # Human-readable description
    metadata: dict = field(default_factory=dict)
    audit_chain_ref: str = ""         # Reference to parent audit context
    parent_event_id: str = ""         # Causal parent event (if cascading)

    def __post_init__(self):
        if not self.event_id:
            self.event_id = f"evt:{uuid.uuid4().hex[:16]}"
        if not self.triggered_at_ms:
            self.triggered_at_ms = int(time.time() * 1000)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "severity": self.severity.name,
            "severity_level": int(self.severity),
            "source": self.source,
            "triggered_at_ms": self.triggered_at_ms,
            "triggered_by": self.triggered_by,
            "affected_objects": self.affected_objects,
            "reason_code": self.reason_code,
            "reason_detail": self.reason_detail,
            "metadata": self.metadata,
            "audit_chain_ref": self.audit_chain_ref,
            "parent_event_id": self.parent_event_id,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Incident Record (DOC-07 §8) / 事故记录
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class IncidentRecord:
    """
    Formal incident record — mandatory for INCIDENT and CRITICAL_INCIDENT.
    正式事故记录 — INCIDENT 和 CRITICAL_INCIDENT 级别必须创建。
    """
    incident_id: str = ""
    severity: EventSeverity = EventSeverity.INCIDENT
    trigger_event_id: str = ""         # The Event that caused this incident
    detected_at_ms: int = 0
    detected_by: str = ""              # Module or operator

    # Scope of impact / 影响范围
    affected_symbols: list = field(default_factory=list)
    affected_strategies: list = field(default_factory=list)
    affected_objects: list = field(default_factory=list)

    # Actions taken / 已采取的动作
    initial_actions: list = field(default_factory=list)
    actions_triggered: list = field(default_factory=list)

    # Root cause / 根因
    root_cause_family: RootCauseFamily = RootCauseFamily.UNKNOWN
    root_cause_detail: str = ""

    # Impact assessment / 影响评估
    pnl_impact: Optional[float] = None
    risk_impact: str = ""

    # Integrity / 完整性
    truth_source_integrity: IntegrityStatus = IntegrityStatus.INTACT
    audit_integrity: IntegrityStatus = IntegrityStatus.INTACT

    # Containment / 控制
    containment_complete: bool = False
    remediation_required: bool = True
    authorization_freeze_required: bool = False

    # Recovery / 恢复
    recovery_approved_by: Optional[str] = None
    recovery_approved_at_ms: Optional[int] = None
    resolved_at_ms: Optional[int] = None
    resolution_notes: str = ""

    def __post_init__(self):
        if not self.incident_id:
            self.incident_id = f"inc:{uuid.uuid4().hex[:12]}"
        if not self.detected_at_ms:
            self.detected_at_ms = int(time.time() * 1000)

    @property
    def is_resolved(self) -> bool:
        return self.resolved_at_ms is not None

    @property
    def is_critical(self) -> bool:
        return self.severity >= EventSeverity.CRITICAL_INCIDENT

    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "severity": self.severity.name,
            "severity_level": int(self.severity),
            "trigger_event_id": self.trigger_event_id,
            "detected_at_ms": self.detected_at_ms,
            "detected_by": self.detected_by,
            "affected_symbols": self.affected_symbols,
            "affected_strategies": self.affected_strategies,
            "affected_objects": self.affected_objects,
            "initial_actions": self.initial_actions,
            "actions_triggered": self.actions_triggered,
            "root_cause_family": self.root_cause_family.value,
            "root_cause_detail": self.root_cause_detail,
            "pnl_impact": self.pnl_impact,
            "risk_impact": self.risk_impact,
            "truth_source_integrity": self.truth_source_integrity.value,
            "audit_integrity": self.audit_integrity.value,
            "containment_complete": self.containment_complete,
            "remediation_required": self.remediation_required,
            "authorization_freeze_required": self.authorization_freeze_required,
            "recovery_approved_by": self.recovery_approved_by,
            "recovery_approved_at_ms": self.recovery_approved_at_ms,
            "is_resolved": self.is_resolved,
            "resolved_at_ms": self.resolved_at_ms,
            "resolution_notes": self.resolution_notes,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Severity → Action Mapping (DOC-07 §3-§5) / 严重度→动作映射
# ═══════════════════════════════════════════════════════════════════════════════

SEVERITY_ACTION_MAP: dict[EventSeverity, list[IncidentActionType]] = {
    EventSeverity.NOTICE: [
        IncidentActionType.RECORD_ONLY,
    ],
    EventSeverity.ANOMALY: [
        IncidentActionType.RECORD_ONLY,
        IncidentActionType.INCREASE_MONITORING,
        IncidentActionType.RISK_ESCALATE_CAUTIOUS,
    ],
    EventSeverity.NEAR_MISS: [
        IncidentActionType.RECORD_ONLY,
        IncidentActionType.AUTH_RESTRICT,
        IncidentActionType.RISK_ESCALATE_REDUCED,
        IncidentActionType.OPERATOR_ALERT,
    ],
    EventSeverity.INCIDENT: [
        IncidentActionType.AUTH_FREEZE,
        IncidentActionType.RISK_ESCALATE_DEFENSIVE,
        IncidentActionType.MANUAL_REVIEW,
        IncidentActionType.OPERATOR_ALERT,
    ],
    EventSeverity.CRITICAL_INCIDENT: [
        IncidentActionType.AUTH_FREEZE,
        IncidentActionType.RISK_CIRCUIT_BREAKER,
        IncidentActionType.TRADING_FREEZE,
        IncidentActionType.MANUAL_REVIEW,
        IncidentActionType.OPERATOR_ALERT,
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# Incident Policy Engine / 事故策略引擎
# ═══════════════════════════════════════════════════════════════════════════════

class IncidentPolicy:
    """
    Incident policy engine — processes events and triggers state machine transitions.
    事故策略引擎 — 处理事件并触发状态机转换。

    DOC-07 principles:
    - Escalation (conservative) = automatic, no approval needed
    - De-escalation = requires approval + observation period
    - Incident/Critical → immediate state machine freeze/circuit-break
    - All actions audited

    Usage:
        policy = IncidentPolicy(
            audit_callback=pipeline.make_callback("incident_policy"),
            on_auth_action=auth_sm.handle_incident,
            on_risk_action=risk_governor.handle_incident,
        )
        event = Event(event_type="reconciliation_mismatch", severity=EventSeverity.INCIDENT, ...)
        result = policy.process_event(event)
    """

    def __init__(
        self,
        audit_callback: Optional[Callable[[dict], None]] = None,
        on_auth_action: Optional[Callable[[str, dict], None]] = None,
        on_risk_action: Optional[Callable[[str, dict], None]] = None,
        on_operator_alert: Optional[Callable[[dict], None]] = None,
    ) -> None:
        self._audit_callback = audit_callback
        self._on_auth_action = on_auth_action
        self._on_risk_action = on_risk_action
        self._on_operator_alert = on_operator_alert
        self._lock = threading.Lock()
        self._event_log: list[Event] = []
        self._incident_log: list[IncidentRecord] = []
        self._max_log = 10000
        self._stats = {
            "events_processed": 0,
            "incidents_created": 0,
            "actions_triggered": 0,
            "notices": 0,
            "anomalies": 0,
            "near_misses": 0,
            "incidents": 0,
            "critical_incidents": 0,
        }

    # ───────────────────────────────────────────────────────────────────────
    # Event Processing / 事件处理
    # ───────────────────────────────────────────────────────────────────────

    def process_event(self, event: Event) -> dict:
        """
        Process an event through the incident policy.
        通过事故策略处理事件。

        Returns dict with: event_id, severity, actions_taken, incident_id (if created)
        """
        with self._lock:
            self._event_log.append(event)
            if len(self._event_log) > self._max_log:
                self._event_log = self._event_log[-self._max_log:]

            self._stats["events_processed"] += 1
            severity_key = event.severity.name.lower() + "s"
            if event.severity == EventSeverity.NEAR_MISS:
                severity_key = "near_misses"
            elif event.severity == EventSeverity.CRITICAL_INCIDENT:
                severity_key = "critical_incidents"
            if severity_key in self._stats:
                self._stats[severity_key] += 1

            # Determine actions
            actions = SEVERITY_ACTION_MAP.get(event.severity, [])
            actions_taken: list[str] = []
            incident_record: Optional[IncidentRecord] = None

            # Create incident record if severity >= NEAR_MISS
            if event.severity >= EventSeverity.NEAR_MISS:
                incident_record = IncidentRecord(
                    severity=event.severity,
                    trigger_event_id=event.event_id,
                    detected_by=event.source,
                    affected_symbols=[
                        obj for obj in event.affected_objects
                        if isinstance(obj, str) and "USDT" in obj.upper()
                    ],
                    affected_objects=event.affected_objects,
                    root_cause_family=RootCauseFamily(event.reason_code)
                    if event.reason_code in [e.value for e in RootCauseFamily]
                    else RootCauseFamily.UNKNOWN,
                    root_cause_detail=event.reason_detail,
                    authorization_freeze_required=event.severity >= EventSeverity.INCIDENT,
                )
                self._incident_log.append(incident_record)
                if len(self._incident_log) > self._max_log:
                    self._incident_log = self._incident_log[-self._max_log:]
                self._stats["incidents_created"] += 1

            # Execute actions
            for action in actions:
                try:
                    self._execute_action(action, event, incident_record)
                    actions_taken.append(action.value)
                    self._stats["actions_triggered"] += 1
                except Exception as e:
                    logger.error("Incident action %s failed: %s", action.value, e)
                    actions_taken.append(f"{action.value}:FAILED")

            # Update incident record with actions
            if incident_record:
                incident_record.actions_triggered = actions_taken

            # Audit
            self._emit_audit(event, actions_taken, incident_record)

            result = {
                "event_id": event.event_id,
                "severity": event.severity.name,
                "actions_taken": actions_taken,
                "incident_id": incident_record.incident_id if incident_record else None,
            }
            return result

    def _execute_action(
        self,
        action: IncidentActionType,
        event: Event,
        incident: Optional[IncidentRecord],
    ) -> None:
        """Execute a single incident action / 执行单个事故动作"""
        context = {
            "event_id": event.event_id,
            "severity": event.severity.name,
            "source": event.source,
            "reason_code": event.reason_code,
            "reason_detail": event.reason_detail,
            "affected_objects": event.affected_objects,
            "incident_id": incident.incident_id if incident else None,
        }

        if action == IncidentActionType.RECORD_ONLY:
            pass  # Already recorded

        elif action == IncidentActionType.INCREASE_MONITORING:
            logger.info("Incident policy: increasing monitoring for %s", event.source)

        elif action in (IncidentActionType.AUTH_RESTRICT, IncidentActionType.AUTH_FREEZE):
            if self._on_auth_action:
                self._on_auth_action(action.value, context)

        elif action in (
            IncidentActionType.RISK_ESCALATE_CAUTIOUS,
            IncidentActionType.RISK_ESCALATE_REDUCED,
            IncidentActionType.RISK_ESCALATE_DEFENSIVE,
            IncidentActionType.RISK_CIRCUIT_BREAKER,
        ):
            if self._on_risk_action:
                self._on_risk_action(action.value, context)

        elif action == IncidentActionType.TRADING_FREEZE:
            if self._on_risk_action:
                self._on_risk_action(IncidentActionType.RISK_CIRCUIT_BREAKER.value, context)
            if self._on_auth_action:
                self._on_auth_action(IncidentActionType.AUTH_FREEZE.value, context)

        elif action == IncidentActionType.MANUAL_REVIEW:
            logger.warning("Incident policy: MANUAL_REVIEW required for %s", event.event_id)

        elif action == IncidentActionType.OPERATOR_ALERT:
            if self._on_operator_alert:
                self._on_operator_alert(context)

    # ───────────────────────────────────────────────────────────────────────
    # Event Creation Helpers / 事件创建助手
    # ───────────────────────────────────────────────────────────────────────

    @staticmethod
    def create_event(
        event_type: str,
        severity: EventSeverity,
        source: str,
        triggered_by: str = "System",
        affected_objects: Optional[list] = None,
        reason_code: str = "",
        reason_detail: str = "",
        metadata: Optional[dict] = None,
        parent_event_id: str = "",
    ) -> Event:
        """Factory method to create a well-formed Event / 创建标准事件的工厂方法"""
        return Event(
            event_type=event_type,
            severity=severity,
            source=source,
            triggered_by=triggered_by,
            affected_objects=affected_objects or [],
            reason_code=reason_code,
            reason_detail=reason_detail,
            metadata=metadata or {},
            parent_event_id=parent_event_id,
        )

    @staticmethod
    def from_reconciliation_report(report: dict) -> Event:
        """Create event from a ReconciliationEngine report / 从对账报告创建事件"""
        critical_count = report.get("critical_count", 0)
        disc_count = report.get("discrepancy_count", 0)

        if critical_count >= 3:
            severity = EventSeverity.CRITICAL_INCIDENT
        elif critical_count >= 1:
            severity = EventSeverity.INCIDENT
        elif disc_count >= 3:
            severity = EventSeverity.NEAR_MISS
        elif disc_count >= 1:
            severity = EventSeverity.ANOMALY
        else:
            severity = EventSeverity.NOTICE

        return Event(
            event_type="reconciliation_mismatch" if disc_count > 0 else "reconciliation_pass",
            severity=severity,
            source="reconciliation_engine",
            triggered_by="ReconciliationEngine",
            affected_objects=[],
            reason_code="state_conflict" if disc_count > 0 else "",
            reason_detail=f"Reconciliation: {disc_count} discrepancies, {critical_count} critical",
            metadata={
                "report_id": report.get("report_id", ""),
                "overall_result": report.get("overall_result", ""),
                "discrepancy_count": disc_count,
                "critical_count": critical_count,
            },
        )

    # ───────────────────────────────────────────────────────────────────────
    # Incident Recovery / 事故恢复
    # ───────────────────────────────────────────────────────────────────────

    def approve_recovery(
        self,
        incident_id: str,
        approved_by: str,
        notes: str = "",
    ) -> bool:
        """
        Approve incident recovery (operator-only action).
        批准事故恢复（仅运营商操作）。
        """
        with self._lock:
            for incident in self._incident_log:
                if incident.incident_id == incident_id:
                    if incident.is_resolved:
                        return False  # Already resolved
                    now_ms = int(time.time() * 1000)
                    incident.recovery_approved_by = approved_by
                    incident.recovery_approved_at_ms = now_ms
                    incident.resolved_at_ms = now_ms
                    incident.resolution_notes = notes
                    incident.containment_complete = True

                    if self._audit_callback:
                        self._audit_callback({
                            "event_type": "incident_recovery_approved",
                            "incident_id": incident_id,
                            "approved_by": approved_by,
                            "notes": notes,
                            "timestamp_ms": now_ms,
                        })
                    return True
            return False  # Not found

    # ───────────────────────────────────────────────────────────────────────
    # Queries / 查询
    # ───────────────────────────────────────────────────────────────────────

    def get_open_incidents(self) -> list[dict]:
        """Get unresolved incidents / 获取未解决事故"""
        with self._lock:
            return [
                i.to_dict() for i in self._incident_log
                if not i.is_resolved
            ]

    def get_incident(self, incident_id: str) -> Optional[dict]:
        """Get specific incident / 获取指定事故"""
        with self._lock:
            for i in self._incident_log:
                if i.incident_id == incident_id:
                    return i.to_dict()
            return None

    def get_recent_events(self, count: int = 50) -> list[dict]:
        """Get recent events / 获取最近事件"""
        with self._lock:
            return [e.to_dict() for e in self._event_log[-count:]]

    def get_events_by_severity(self, min_severity: EventSeverity) -> list[dict]:
        """Get events at or above given severity / 获取指定严重度以上的事件"""
        with self._lock:
            return [
                e.to_dict() for e in self._event_log
                if e.severity >= min_severity
            ]

    def get_stats(self) -> dict:
        """Get processing statistics / 获取处理统计"""
        with self._lock:
            return {
                **self._stats,
                "open_incidents": sum(
                    1 for i in self._incident_log if not i.is_resolved
                ),
                "total_incidents": len(self._incident_log),
                "event_log_size": len(self._event_log),
            }

    # ───────────────────────────────────────────────────────────────────────
    # Audit / 审计
    # ───────────────────────────────────────────────────────────────────────

    def _emit_audit(
        self,
        event: Event,
        actions_taken: list[str],
        incident: Optional[IncidentRecord],
    ) -> None:
        """Emit audit record / 发送审计记录"""
        if self._audit_callback:
            try:
                self._audit_callback({
                    "event_type": "incident_policy_processed",
                    "event_id": event.event_id,
                    "event_type_original": event.event_type,
                    "severity": event.severity.name,
                    "source": event.source,
                    "actions_taken": actions_taken,
                    "incident_id": incident.incident_id if incident else None,
                    "incident_severity": incident.severity.name if incident else None,
                    "timestamp_ms": int(time.time() * 1000),
                })
            except Exception as e:
                logger.error("Incident policy audit error: %s", e)
