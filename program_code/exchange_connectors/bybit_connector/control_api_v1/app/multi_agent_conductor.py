"""Conductor orchestration extracted from multi_agent_framework.py."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .multi_agent_framework import (
    AgentMessage,
    AgentRole,
    AgentState,
    ArbitrationResult,
    MessageBus,
    MessageType,
    ResourcePriority,
    RiskVerdict,
    RiskVerdictResult,
    TradeIntent,
    arbitrate_conflict,
)


@dataclass
class AgentInfo:
    """Metadata about a registered agent."""

    role: AgentRole
    state: AgentState = AgentState.INITIALIZING
    resource_mode: str = "local"
    last_heartbeat_ms: int = 0
    messages_sent: int = 0
    messages_received: int = 0
    errors: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role.value,
            "state": self.state.value,
            "resource_mode": self.resource_mode,
            "last_heartbeat_ms": self.last_heartbeat_ms,
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
            "errors": self.errors,
        }


class Conductor:
    """EX-06 §2 — OpenClaw as central orchestrator."""

    def __init__(
        self,
        *,
        message_bus: Optional[MessageBus] = None,
        audit_callback: Optional[Callable] = None,
        event_store: Optional[Any] = None,
    ):
        self.bus = message_bus or MessageBus(audit_callback=audit_callback)
        self._lock = threading.Lock()
        self._agents: Dict[AgentRole, AgentInfo] = {}
        self._audit_callback = audit_callback
        self.event_store = event_store
        self._directives_issued: int = 0
        self._arbitrations: int = 0
        self._resource_budget_usd: float = 2.0

    def register_agent(
        self,
        role: AgentRole,
        *,
        resource_mode: str = "local",
        metadata: Optional[Dict] = None,
    ) -> AgentInfo:
        """Register an agent with the conductor."""
        info = AgentInfo(
            role=role,
            state=AgentState.INITIALIZING,
            resource_mode=resource_mode,
            metadata=metadata or {},
        )
        with self._lock:
            self._agents[role] = info
        return info

    def set_agent_state(self, role: AgentRole, state: AgentState) -> bool:
        """Update an agent's lifecycle state."""
        with self._lock:
            info = self._agents.get(role)
            if not info:
                return False
            old_state = info.state
            info.state = state
            info.last_heartbeat_ms = int(time.time() * 1000)
        self._record_state_change(role, old_state, state, "set_agent_state")
        return True

    def _record_state_change(
        self,
        role: AgentRole,
        from_state: AgentState,
        to_state: AgentState,
        trigger_event: str,
    ) -> None:
        """Fail-soft state persistence for conductor-observed lifecycle."""
        if self.event_store is None:
            return
        try:
            record_fn = getattr(self.event_store, "record_state_change", None)
            if record_fn is None:
                return
            record_fn(
                agent_name=f"conductor:{role.value}",
                from_state=from_state.value,
                to_state=to_state.value,
                trigger_event=trigger_event,
                details={"source": "Conductor.set_agent_state", "role": role.value},
            )
        except Exception:
            pass

    def heartbeat(self, role: AgentRole) -> bool:
        """Record a heartbeat from an agent."""
        with self._lock:
            info = self._agents.get(role)
            if not info:
                return False
            info.last_heartbeat_ms = int(time.time() * 1000)
        return True

    def on_agent_message_received(self, role: AgentRole) -> None:
        """Track delivery heartbeat and message count for an agent role."""
        with self._lock:
            info = self._agents.get(role)
            if info is not None:
                info.last_heartbeat_ms = int(time.time() * 1000)
                info.messages_received += 1

    def make_tracked_subscriber(self, role: AgentRole, callback: Callable) -> Callable:
        """Wrap a MessageBus subscriber callback to auto-track heartbeats."""

        def _tracked_callback(message: AgentMessage) -> None:
            self.on_agent_message_received(role)
            callback(message)

        return _tracked_callback

    def get_agent_info(self, role: AgentRole) -> Optional[AgentInfo]:
        with self._lock:
            return self._agents.get(role)

    def get_all_agents(self) -> Dict[AgentRole, AgentInfo]:
        with self._lock:
            return dict(self._agents)

    def dispatch_market_event(self, event_data: Dict[str, Any]) -> List[AgentRole]:
        """Decide which agents should handle a market event."""
        notified: List[AgentRole] = []
        event_type = event_data.get("type", "")

        if self._is_agent_available(AgentRole.SCOUT):
            notified.append(AgentRole.SCOUT)

        if event_type in ("price_update", "funding_rate", "oi_change", "liquidation"):
            if self._is_agent_available(AgentRole.STRATEGIST):
                notified.append(AgentRole.STRATEGIST)
            if self._is_agent_available(AgentRole.GUARDIAN):
                notified.append(AgentRole.GUARDIAN)

        if event_type in ("fill", "partial_fill", "reject", "cancel"):
            if self._is_agent_available(AgentRole.EXECUTOR):
                notified.append(AgentRole.EXECUTOR)
            if self._is_agent_available(AgentRole.ANALYST):
                notified.append(AgentRole.ANALYST)

        if event_type in ("risk_alert", "anomaly", "circuit_breaker"):
            if AgentRole.GUARDIAN not in notified and self._is_agent_available(
                AgentRole.GUARDIAN
            ):
                notified.append(AgentRole.GUARDIAN)

        return notified

    def _is_agent_available(self, role: AgentRole) -> bool:
        with self._lock:
            info = self._agents.get(role)
            return info is not None and info.state in (
                AgentState.RUNNING,
                AgentState.DEGRADED,
            )

    def resolve_conflict(
        self,
        scenario: str,
        strategist_action: Optional[Dict] = None,
        guardian_action: Optional[Dict] = None,
    ) -> ArbitrationResult:
        """Arbitrate a conflict between agents."""
        result = arbitrate_conflict(scenario, strategist_action, guardian_action)
        with self._lock:
            self._arbitrations += 1

        if self._audit_callback:
            try:
                self._audit_callback(
                    "conflict_arbitration",
                    {"scenario": scenario, "result": result.to_dict()},
                )
            except Exception:
                pass
        return result

    def allocate_resource(
        self, requests: List[Tuple[AgentRole, float]]
    ) -> Dict[AgentRole, float]:
        """Allocate AI compute budget across agents."""
        priority_map = {
            AgentRole.GUARDIAN: ResourcePriority.GUARDIAN,
            AgentRole.SCOUT: ResourcePriority.SCOUT_ROUTINE,
            AgentRole.STRATEGIST: ResourcePriority.STRATEGIST,
            AgentRole.ANALYST: ResourcePriority.ANALYST,
            AgentRole.EXECUTOR: ResourcePriority.STRATEGIST,
        }
        sorted_requests = sorted(requests, key=lambda r: priority_map.get(r[0], 9))

        allocated: Dict[AgentRole, float] = {}
        remaining = self._resource_budget_usd
        for role, requested in sorted_requests:
            grant = min(requested, remaining)
            allocated[role] = grant
            remaining -= grant
            if remaining <= 0:
                break

        for role, _ in requests:
            if role not in allocated:
                allocated[role] = 0.0
        return allocated

    def set_resource_budget(self, usd: float) -> None:
        self._resource_budget_usd = usd

    def broadcast_directive(
        self,
        directive_type: str,
        payload: Dict[str, Any],
        *,
        targets: Optional[List[AgentRole]] = None,
    ) -> int:
        """Broadcast a system_directive to agents."""
        if targets is None:
            targets = [
                AgentRole.SCOUT,
                AgentRole.STRATEGIST,
                AgentRole.GUARDIAN,
                AgentRole.ANALYST,
                AgentRole.EXECUTOR,
            ]

        sent = 0
        full_payload = {"directive_type": directive_type, **payload}
        for target in targets:
            msg = AgentMessage(
                sender=AgentRole.CONDUCTOR,
                receiver=target,
                message_type=MessageType.SYSTEM_DIRECTIVE,
                priority=0,
                payload=full_payload,
            )
            if self.bus.send(msg):
                sent += 1

        with self._lock:
            self._directives_issued += sent
        return sent

    def process_trade_intent(
        self, intent: TradeIntent, guardian_review: Callable
    ) -> Tuple[bool, RiskVerdict]:
        """Run Strategist → Guardian review → Executor routing."""
        verdict = guardian_review(intent)

        if verdict.result == RiskVerdictResult.APPROVED:
            if self.bus:
                self.bus.send(
                    AgentMessage(
                        sender=AgentRole.STRATEGIST,
                        receiver=AgentRole.EXECUTOR,
                        message_type=MessageType.APPROVED_INTENT,
                        priority=2,
                        payload=intent.to_dict(),
                    )
                )
            return (True, verdict)

        if verdict.result == RiskVerdictResult.MODIFIED:
            modified_intent = TradeIntent(
                intent_id=intent.intent_id,
                symbol=intent.symbol,
                strategy=intent.strategy,
                direction=intent.direction,
                size=verdict.modified_params.get("size", intent.size),
                params={**intent.params, **verdict.modified_params},
                confidence=intent.confidence,
                thesis=intent.thesis,
                invalidation_condition=intent.invalidation_condition,
                data_quality=intent.data_quality,
                metadata={**intent.metadata, "guardian_modified": True},
            )
            if self.bus:
                self.bus.send(
                    AgentMessage(
                        sender=AgentRole.STRATEGIST,
                        receiver=AgentRole.EXECUTOR,
                        message_type=MessageType.APPROVED_INTENT,
                        priority=2,
                        payload=modified_intent.to_dict(),
                    )
                )
            return (True, verdict)

        return (False, verdict)

    _TASK_TYPE_TO_ROLE: Dict[str, AgentRole] = {
        "SCAN": AgentRole.SCOUT,
        "EVALUATE": AgentRole.STRATEGIST,
        "RISK_CHECK": AgentRole.GUARDIAN,
        "ANALYZE": AgentRole.ANALYST,
        "EXECUTE": AgentRole.EXECUTOR,
    }

    def dispatch_to_agent(self, task_type: str, payload: Dict[str, Any]) -> bool:
        """Route a task to the best-fit available agent."""
        target_role = self._TASK_TYPE_TO_ROLE.get(task_type.upper() if task_type else "")
        if target_role is None or not self._is_agent_available(target_role):
            return False

        msg = AgentMessage(
            sender=AgentRole.CONDUCTOR,
            receiver=target_role,
            message_type=MessageType.SYSTEM_DIRECTIVE,
            priority=2,
            payload={"directive_type": "task_dispatch", "task_type": task_type, **payload},
        )
        sent = self.bus.send(msg)
        if sent:
            with self._lock:
                self._directives_issued += 1
                info = self._agents.get(target_role)
                if info is not None:
                    info.messages_received += 1
        return sent

    def get_agent_health(self) -> Dict[str, Dict[str, Any]]:
        """Return health status for all registered agents."""
        now_ms = int(time.time() * 1000)
        result: Dict[str, Dict[str, Any]] = {}
        with self._lock:
            for role, info in self._agents.items():
                heartbeat_age_ms = (
                    now_ms - info.last_heartbeat_ms if info.last_heartbeat_ms > 0 else -1
                )
                result[role.value] = {
                    "last_heartbeat": info.last_heartbeat_ms,
                    "heartbeat_age_ms": heartbeat_age_ms,
                    "status": info.state.value,
                    "message_count": info.messages_received,
                    "errors": info.errors,
                    "stale": heartbeat_age_ms > 60_000 if heartbeat_age_ms >= 0 else True,
                }
        return result

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            agents_summary = {
                role.value: info.to_dict() for role, info in self._agents.items()
            }
            return {
                "role": AgentRole.CONDUCTOR.value,
                "agents": agents_summary,
                "agents_registered": len(self._agents),
                "agents_running": sum(
                    1 for i in self._agents.values() if i.state == AgentState.RUNNING
                ),
                "total_messages": self.bus.total_messages,
                "directives_issued": self._directives_issued,
                "arbitrations": self._arbitrations,
                "resource_budget_usd": self._resource_budget_usd,
            }
