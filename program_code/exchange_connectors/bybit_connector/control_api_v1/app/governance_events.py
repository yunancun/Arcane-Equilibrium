"""
MODULE_NOTE (中文):
  統一治理事件模型 — 提供 GovernanceEvent 基類和 EventCategory 分類體系，
  用於跨模組事件處理。各 SM 模組保留自己的事件枚舉，本模組提供統一抽象層。
  屬於治理層（GAP-M1），涵蓋授權/風控/租約/訂單管理/對賬等事件類別。

MODULE_NOTE (English):
  Unified Governance Event Model — provides a base GovernanceEvent class and
  EventCategory taxonomy for cross-module event handling. Individual SM event
  enums remain in their respective modules; this module provides the unified
  abstraction layer. Part of governance layer (GAP-M1).

Spec References: SM-01, SM-02, SM-04, EX-02, EX-04
"""

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


class EventCategory(enum.Enum):
    """Top-level event category taxonomy for governance events."""
    AUTHORIZATION = "authorization"       # SM-01
    RISK_GOVERNOR = "risk_governor"       # SM-04
    DECISION_LEASE = "decision_lease"     # SM-02
    ORDER_MANAGEMENT = "order_management" # EX-02
    RECONCILIATION = "reconciliation"     # EX-04
    INCIDENT = "incident"                 # Incident response
    GOVERNANCE_HUB = "governance_hub"     # Cross-SM hub events
    AUDIT = "audit"                       # Audit persistence events


class EventSeverity(enum.Enum):
    """Event severity levels."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    FATAL = "fatal"


class EventDirection(enum.Enum):
    """Whether event represents restriction or expansion."""
    RESTRICT = "restrict"    # Conservative direction (auto-allowed)
    EXPAND = "expand"        # Expansion direction (requires approval)
    NEUTRAL = "neutral"      # No direction change


@dataclass
class GovernanceEvent:
    """
    Unified base class for all governance events.

    All state machine transitions, incidents, and audit entries
    can be represented as GovernanceEvent instances for unified
    logging, filtering, and cross-SM event handling.
    """
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    # Classification
    category: EventCategory = EventCategory.GOVERNANCE_HUB
    severity: EventSeverity = EventSeverity.INFO
    direction: EventDirection = EventDirection.NEUTRAL

    # Source identification
    source_sm: str = ""            # e.g. "SM-01", "SM-04", "EX-04"
    source_module: str = ""        # e.g. "authorization_state_machine"
    initiator: str = ""            # e.g. "OPERATOR", "RISK_GOVERNOR", "SYSTEM"

    # State change (optional)
    state_from: str | None = None
    state_to: str | None = None

    # Payload
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    # Correlation
    correlation_id: str | None = None   # Links related cross-SM events
    parent_event_id: str | None = None  # Causal chain

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON/audit output."""
        return {
            "event_id": self.event_id,
            "timestamp_ms": self.timestamp_ms,
            "category": self.category.value,
            "severity": self.severity.value,
            "direction": self.direction.value,
            "source_sm": self.source_sm,
            "source_module": self.source_module,
            "initiator": self.initiator,
            "state_from": self.state_from,
            "state_to": self.state_to,
            "message": self.message,
            "details": self.details,
            "correlation_id": self.correlation_id,
            "parent_event_id": self.parent_event_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GovernanceEvent":
        """Deserialize from dictionary."""
        return cls(
            event_id=data.get("event_id", str(uuid.uuid4())),
            timestamp_ms=data.get("timestamp_ms", int(time.time() * 1000)),
            category=EventCategory(data.get("category", "governance_hub")),
            severity=EventSeverity(data.get("severity", "info")),
            direction=EventDirection(data.get("direction", "neutral")),
            source_sm=data.get("source_sm", ""),
            source_module=data.get("source_module", ""),
            initiator=data.get("initiator", ""),
            state_from=data.get("state_from"),
            state_to=data.get("state_to"),
            message=data.get("message", ""),
            details=data.get("details", {}),
            correlation_id=data.get("correlation_id"),
            parent_event_id=data.get("parent_event_id"),
        )

    def is_critical(self) -> bool:
        """Check if event is critical or fatal severity."""
        return self.severity in (EventSeverity.CRITICAL, EventSeverity.FATAL)

    def is_restriction(self) -> bool:
        """Check if event represents a conservative (restriction) action."""
        return self.direction == EventDirection.RESTRICT


# Factory helpers for common event types

def auth_event(
    state_from: str, state_to: str, initiator: str,
    message: str = "", severity: EventSeverity = EventSeverity.INFO,
    correlation_id: str | None = None,
    parent_event_id: str | None = None,
    **details
) -> GovernanceEvent:
    """Create an authorization state machine event."""
    direction = EventDirection.RESTRICT if state_to in ("RESTRICTED", "FROZEN", "REVOKED") else \
                EventDirection.EXPAND if state_to in ("ACTIVE",) else EventDirection.NEUTRAL
    return GovernanceEvent(
        category=EventCategory.AUTHORIZATION,
        severity=severity,
        direction=direction,
        source_sm="SM-01",
        source_module="authorization_state_machine",
        initiator=initiator,
        state_from=state_from,
        state_to=state_to,
        message=message or f"Auth: {state_from} → {state_to}",
        details=details,
        correlation_id=correlation_id,
        parent_event_id=parent_event_id,
    )


def risk_event(
    level_from: int, level_to: int, initiator: str,
    reason: str = "",
    correlation_id: str | None = None,
    parent_event_id: str | None = None,
    **details
) -> GovernanceEvent:
    """Create a risk governor state machine event."""
    NAMES = ["NORMAL", "CAUTIOUS", "REDUCED", "DEFENSIVE", "CIRCUIT_BREAKER", "MANUAL_REVIEW"]
    severity = EventSeverity.CRITICAL if level_to >= 4 else \
               EventSeverity.WARNING if level_to >= 2 else EventSeverity.INFO
    direction = EventDirection.RESTRICT if level_to > level_from else \
                EventDirection.EXPAND if level_to < level_from else EventDirection.NEUTRAL
    return GovernanceEvent(
        category=EventCategory.RISK_GOVERNOR,
        severity=severity,
        direction=direction,
        source_sm="SM-04",
        source_module="risk_governor_state_machine",
        initiator=initiator,
        state_from=NAMES[level_from] if 0 <= level_from < len(NAMES) else str(level_from),
        state_to=NAMES[level_to] if 0 <= level_to < len(NAMES) else str(level_to),
        message=reason or f"Risk: {NAMES[level_from] if 0 <= level_from < len(NAMES) else level_from} → {NAMES[level_to] if 0 <= level_to < len(NAMES) else level_to}",
        details=details,
        correlation_id=correlation_id,
        parent_event_id=parent_event_id,
    )


def lease_event(
    state_from: str, state_to: str, initiator: str,
    lease_id: str = "", message: str = "",
    correlation_id: str | None = None,
    parent_event_id: str | None = None,
    **details
) -> GovernanceEvent:
    """Create a decision lease state machine event."""
    direction = EventDirection.RESTRICT if state_to in ("FROZEN", "REVOKED", "EXPIRED") else \
                EventDirection.EXPAND if state_to in ("ACTIVE",) else EventDirection.NEUTRAL
    return GovernanceEvent(
        category=EventCategory.DECISION_LEASE,
        severity=EventSeverity.INFO,
        direction=direction,
        source_sm="SM-02",
        source_module="decision_lease_state_machine",
        initiator=initiator,
        state_from=state_from,
        state_to=state_to,
        message=message or f"Lease {lease_id}: {state_from} → {state_to}",
        details={"lease_id": lease_id, **details},
        correlation_id=correlation_id,
        parent_event_id=parent_event_id,
    )


def oms_event(
    order_id: str, state_from: str, state_to: str, initiator: str,
    message: str = "",
    correlation_id: str | None = None,
    parent_event_id: str | None = None,
    **details
) -> GovernanceEvent:
    """Create an OMS (Order Management System) state machine event."""
    terminal_states = ("COMPLETED", "REJECTED", "CANCELLED", "ABORTED", "EXPIRED")
    severity = EventSeverity.WARNING if state_to in ("REJECTED", "ABORTED") else EventSeverity.INFO
    direction = EventDirection.RESTRICT if state_to in ("REJECTED", "ABORTED", "CANCELLED") else EventDirection.NEUTRAL
    return GovernanceEvent(
        category=EventCategory.ORDER_MANAGEMENT,
        severity=severity,
        direction=direction,
        source_sm="EX-02",
        source_module="oms_state_machine",
        initiator=initiator,
        state_from=state_from,
        state_to=state_to,
        message=message or f"Order {order_id}: {state_from} → {state_to}",
        details={"order_id": order_id, **details},
        correlation_id=correlation_id,
        parent_event_id=parent_event_id,
    )


def recon_event(
    result: str, initiator: str = "SYSTEM",
    message: str = "", severity: EventSeverity = EventSeverity.INFO,
    correlation_id: str | None = None,
    parent_event_id: str | None = None,
    **details
) -> GovernanceEvent:
    """Create a reconciliation event."""
    return GovernanceEvent(
        category=EventCategory.RECONCILIATION,
        severity=severity,
        direction=EventDirection.RESTRICT if result in ("MISMATCH_MAJOR", "FATAL") else EventDirection.NEUTRAL,
        source_sm="EX-04",
        source_module="reconciliation_engine",
        initiator=initiator,
        message=message or f"Reconciliation: {result}",
        details={"result": result, **details},
        correlation_id=correlation_id,
        parent_event_id=parent_event_id,
    )
