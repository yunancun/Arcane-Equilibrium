"""
MODULE_NOTE (中文):
  5-Agent 多智能体框架核心模块（Scout / Strategist / Guardian / Analyst / Executor + Conductor 编排）。
  实现结构化 Agent 间消息协议（MessageBus 发布/订阅）、冲突仲裁（Guardian 永远优先于 Strategist）、
  Agent 生命周期管理（INITIALIZING→RUNNING→DEGRADED→PAUSED→STOPPED）以及数据质量标记（fact/inference/hypothesis）。
  属于治理层（Governance T2.07），是原则 15（多 Agent 协作）的底层基础设施。

MODULE_NOTE (English):
  Core 5-agent multi-agent framework (Scout / Strategist / Guardian / Analyst / Executor + Conductor orchestration).
  Implements structured inter-agent message protocol (MessageBus pub/sub), conflict arbitration (Guardian always
  wins over Strategist), agent lifecycle management (INITIALIZING->RUNNING->DEGRADED->PAUSED->STOPPED), and
  data quality marking (fact/inference/hypothesis). Part of the governance layer (T2.07); foundational
  infrastructure for Principle 15 (multi-agent collaboration).

T2.07 — Scout Agent + Conductor Framework (GAP-H2)
===================================================
Governance refs: EX-06 §2-§10, DOC-04 §G Multi-Agent
Implements:
  - Structured inter-agent message protocol (EX-06 §8)
  - Scout Agent: intel_object + event_alert output (EX-06 §3)
  - Conductor/Orchestrator: task distribution, conflict arbitration,
    resource allocation, agent lifecycle (EX-06 §2)
  - 5-role agent architecture: Scout, Strategist, Guardian, Analyst, Executor
  - Conflict resolution: Guardian always wins over Strategist (EX-06 §9)
  - Resource-constrained mode: single model multi-role (EX-06 §10)
  - Data quality marking: fact / inference / hypothesis (EX-06 §3.4)
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Callable, Dict, List, Optional, Tuple

# ─────────────────────────────────────────────
# 1. Enums
# ─────────────────────────────────────────────

class AgentRole(str, Enum):
    """EX-06 §1 — five agent roles + conductor."""
    SCOUT = "scout"
    STRATEGIST = "strategist"
    GUARDIAN = "guardian"
    ANALYST = "analyst"
    EXECUTOR = "executor"
    CONDUCTOR = "conductor"  # OpenClaw orchestrator, not a 6th agent


class MessageType(str, Enum):
    """EX-06 §8.2 — structured inter-agent message types."""
    INTEL_OBJECT = "intel_object"         # Scout → Strategist
    EVENT_ALERT = "event_alert"           # Scout → Guardian
    TRADE_INTENT = "trade_intent"         # Strategist → Guardian
    RISK_VERDICT = "risk_verdict"         # Guardian → Strategist
    APPROVED_INTENT = "approved_intent"   # Strategist → Executor
    EXECUTION_REPORT = "execution_report" # Executor → Analyst
    ROUND_TRIP_COMPLETE = "round_trip_complete"  # Executor → Analyst
    PATTERN_INSIGHT = "pattern_insight"   # Analyst → Strategist
    RISK_PATTERN = "risk_pattern"         # Analyst → Guardian
    STRATEGY_PROPOSAL = "strategy_proposal"  # Analyst → OpenClaw
    SYSTEM_DIRECTIVE = "system_directive" # OpenClaw → All


class DataQualityLevel(str, Enum):
    """EX-06 §3.4 — cognitive level marking (aligns DOC-01 §5.10)."""
    FACT = "fact"              # Exchange API confirmed data
    INFERENCE = "inference"    # Derived from multiple facts
    HYPOTHESIS = "hypothesis"  # Limited-information guess


class SentimentScore(str, Enum):
    """EX-06 §3.1 — sentiment classification."""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class RiskVerdictResult(str, Enum):
    """EX-06 §8.2 — Guardian review outcomes."""
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


class AgentState(str, Enum):
    """Agent lifecycle states (EX-06 §2.3)."""
    INITIALIZING = "initializing"
    RUNNING = "running"
    DEGRADED = "degraded"
    PAUSED = "paused"
    STOPPED = "stopped"


class ResourcePriority(IntEnum):
    """EX-06 §9 TABLE 4 — AI compute priority."""
    GUARDIAN = 0          # Highest
    SCOUT_URGENT = 1
    STRATEGIST = 2
    ANALYST = 3
    SCOUT_ROUTINE = 4    # Lowest


# ─────────────────────────────────────────────
# 2. Structured Message Objects
# ─────────────────────────────────────────────

@dataclass
class AgentMessage:
    """EX-06 §8.1 — base structured communication object.

    All inter-agent communication must use structured objects,
    not free text. Every message has sender/receiver/timestamp/type/priority.
    """
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    sender: AgentRole = AgentRole.CONDUCTOR
    receiver: AgentRole = AgentRole.CONDUCTOR
    message_type: MessageType = MessageType.SYSTEM_DIRECTIVE
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    priority: int = 5  # 0=highest, 9=lowest
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "sender": self.sender.value,
            "receiver": self.receiver.value,
            "message_type": self.message_type.value,
            "timestamp_ms": self.timestamp_ms,
            "priority": self.priority,
            "payload": self.payload,
        }


@dataclass
class IntelObject:
    """EX-06 §3.2 — Scout's structured intelligence output."""
    intel_id: str = field(default_factory=lambda: f"intel_{uuid.uuid4().hex[:12]}")
    source: str = ""
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    freshness_seconds: int = 0
    data_quality: DataQualityLevel = DataQualityLevel.FACT
    sentiment: SentimentScore = SentimentScore.NEUTRAL
    relevance_score: float = 0.0  # 0.0 to 1.0
    content: str = ""
    symbols: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intel_id": self.intel_id,
            "source": self.source,
            "timestamp_ms": self.timestamp_ms,
            "freshness_seconds": self.freshness_seconds,
            "data_quality": self.data_quality.value,
            "sentiment": self.sentiment.value,
            "relevance_score": self.relevance_score,
            "content": self.content,
            "symbols": list(self.symbols),
            "metadata": dict(self.metadata),
        }


@dataclass
class EventAlert:
    """EX-06 §3.2 — Scout's major event alert."""
    alert_id: str = field(default_factory=lambda: f"alert_{uuid.uuid4().hex[:12]}")
    event_type: str = ""  # e.g. "fomc", "token_unlock", "protocol_upgrade", "cpi"
    severity: str = "medium"  # low / medium / high / critical
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    event_time_ms: int = 0  # When the event will occur
    lead_time_hours: float = 0.0
    affected_symbols: List[str] = field(default_factory=list)
    data_quality: DataQualityLevel = DataQualityLevel.INFERENCE
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "event_type": self.event_type,
            "severity": self.severity,
            "timestamp_ms": self.timestamp_ms,
            "event_time_ms": self.event_time_ms,
            "lead_time_hours": self.lead_time_hours,
            "affected_symbols": list(self.affected_symbols),
            "data_quality": self.data_quality.value,
            "description": self.description,
            "metadata": dict(self.metadata),
        }


@dataclass
class TradeIntent:
    """EX-06 §4.2 — Strategist's structured trade intent."""
    intent_id: str = field(default_factory=lambda: f"intent_{uuid.uuid4().hex[:12]}")
    symbol: str = ""
    strategy: str = ""
    direction: str = ""  # "long" / "short"
    size: float = 0.0
    params: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0  # 0.0 to 1.0
    thesis: str = ""
    invalidation_condition: str = ""
    data_quality: DataQualityLevel = DataQualityLevel.INFERENCE
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "symbol": self.symbol,
            "strategy": self.strategy,
            "direction": self.direction,
            "size": self.size,
            "params": dict(self.params),
            "confidence": self.confidence,
            "thesis": self.thesis,
            "invalidation_condition": self.invalidation_condition,
            "data_quality": self.data_quality.value,
            "metadata": dict(self.metadata),
        }


@dataclass
class RiskVerdict:
    """EX-06 §5/§8.2 — Guardian's review conclusion."""
    verdict_id: str = field(default_factory=lambda: f"verdict_{uuid.uuid4().hex[:12]}")
    intent_id: str = ""  # references TradeIntent
    result: RiskVerdictResult = RiskVerdictResult.REJECTED
    reason: str = ""
    modified_params: Dict[str, Any] = field(default_factory=dict)
    risk_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict_id": self.verdict_id,
            "intent_id": self.intent_id,
            "result": self.result.value,
            "reason": self.reason,
            "modified_params": dict(self.modified_params),
            "risk_score": self.risk_score,
            "metadata": dict(self.metadata),
        }


# ─────────────────────────────────────────────
# 3. Message Bus (Inter-Agent Communication)
# ─────────────────────────────────────────────

# Valid communication routes (EX-06 §8.2 TABLE 3)
VALID_ROUTES: Dict[Tuple[AgentRole, AgentRole], List[MessageType]] = {
    (AgentRole.SCOUT, AgentRole.STRATEGIST): [MessageType.INTEL_OBJECT],
    (AgentRole.SCOUT, AgentRole.GUARDIAN): [MessageType.EVENT_ALERT],
    (AgentRole.STRATEGIST, AgentRole.GUARDIAN): [MessageType.TRADE_INTENT],
    (AgentRole.GUARDIAN, AgentRole.STRATEGIST): [MessageType.RISK_VERDICT],
    (AgentRole.STRATEGIST, AgentRole.EXECUTOR): [MessageType.APPROVED_INTENT],
    (AgentRole.EXECUTOR, AgentRole.ANALYST): [
        MessageType.EXECUTION_REPORT,
        MessageType.ROUND_TRIP_COMPLETE,
    ],
    (AgentRole.ANALYST, AgentRole.STRATEGIST): [MessageType.PATTERN_INSIGHT],
    (AgentRole.ANALYST, AgentRole.GUARDIAN): [MessageType.RISK_PATTERN],
    (AgentRole.ANALYST, AgentRole.CONDUCTOR): [MessageType.STRATEGY_PROPOSAL],
    # Conductor can broadcast to all
    (AgentRole.CONDUCTOR, AgentRole.SCOUT): [MessageType.SYSTEM_DIRECTIVE],
    (AgentRole.CONDUCTOR, AgentRole.STRATEGIST): [MessageType.SYSTEM_DIRECTIVE],
    (AgentRole.CONDUCTOR, AgentRole.GUARDIAN): [MessageType.SYSTEM_DIRECTIVE],
    (AgentRole.CONDUCTOR, AgentRole.ANALYST): [MessageType.SYSTEM_DIRECTIVE],
    (AgentRole.CONDUCTOR, AgentRole.EXECUTOR): [MessageType.SYSTEM_DIRECTIVE],
}


class MessageBus:
    """Thread-safe inter-agent message bus with audit trail.

    EX-06 §8.1: all communication must be through structured objects,
    persisted for audit.
    """

    def __init__(self, *, audit_callback: Optional[Callable] = None):
        self._lock = threading.Lock()
        self._messages: List[AgentMessage] = []
        self._subscribers: Dict[AgentRole, List[Callable]] = {}
        self._audit_callback = audit_callback

    def validate_route(
        self, sender: AgentRole, receiver: AgentRole, msg_type: MessageType
    ) -> bool:
        """Check if this communication route is valid per EX-06 TABLE 3."""
        route = (sender, receiver)
        allowed = VALID_ROUTES.get(route, [])
        return msg_type in allowed

    def send(self, message: AgentMessage) -> bool:
        """Send a structured message. Returns True if delivered."""
        if not self.validate_route(
            message.sender, message.receiver, message.message_type
        ):
            return False

        with self._lock:
            self._messages.append(message)
            if self._audit_callback:
                try:
                    self._audit_callback(
                        "message_sent", message.to_dict()
                    )
                except Exception:
                    pass

            # Notify subscribers
            subs = self._subscribers.get(message.receiver, [])
            for cb in subs:
                try:
                    cb(message)
                except Exception:
                    pass

        return True

    def subscribe(self, role: AgentRole, callback: Callable) -> None:
        """Register a handler for messages delivered to *role*."""
        with self._lock:
            self._subscribers.setdefault(role, []).append(callback)

    def get_messages(
        self,
        *,
        receiver: Optional[AgentRole] = None,
        msg_type: Optional[MessageType] = None,
        since_ms: int = 0,
    ) -> List[AgentMessage]:
        """Query message history."""
        with self._lock:
            result = list(self._messages)
        if receiver:
            result = [m for m in result if m.receiver == receiver]
        if msg_type:
            result = [m for m in result if m.message_type == msg_type]
        if since_ms:
            result = [m for m in result if m.timestamp_ms >= since_ms]
        return result

    @property
    def total_messages(self) -> int:
        with self._lock:
            return len(self._messages)


# ─────────────────────────────────────────────
# 4. Scout Agent (EX-06 §3)
# ─────────────────────────────────────────────

@dataclass
class ScoutConfig:
    """Configuration for Scout Agent."""
    news_scan_interval_minutes: int = 30
    event_calendar_lead_hours: float = 24.0
    fomc_lead_hours: float = 2.0
    token_unlock_lead_hours: float = 24.0
    relevance_threshold: float = 0.3


class ScoutAgent:
    """EX-06 §3 — system's "eyes and ears".

    Responsibilities:
    - News search (every 30min via search degradation)
    - Event calendar (Token Unlock / listing / protocol upgrade / FOMC / CPI)
    - Sentiment analysis (positive / negative / neutral)
    - Exchange anomaly monitoring (large liquidation / funding rate spike / OI shift)
    - Data quality marking: fact / inference / hypothesis (§3.4)

    Scout CANNOT:
    - Generate trade signals (only provides intel, Strategist decides)
    - Modify risk parameters (only notifies Guardian of major events)
    - Directly call exchange API for trading
    """

    def __init__(
        self,
        config: Optional[ScoutConfig] = None,
        message_bus: Optional[MessageBus] = None,
    ):
        self.config = config or ScoutConfig()
        self.bus = message_bus
        self.state = AgentState.INITIALIZING
        self._lock = threading.Lock()
        self._intel_log: List[IntelObject] = []
        self._alert_log: List[EventAlert] = []
        self._stats = {"intel_produced": 0, "alerts_produced": 0, "scans_completed": 0}

    # ── lifecycle ──

    def start(self) -> None:
        self.state = AgentState.RUNNING

    def pause(self) -> None:
        self.state = AgentState.PAUSED

    def stop(self) -> None:
        self.state = AgentState.STOPPED

    # ── core capabilities ──

    def produce_intel(
        self,
        source: str,
        content: str,
        symbols: List[str],
        *,
        data_quality: DataQualityLevel = DataQualityLevel.FACT,
        sentiment: SentimentScore = SentimentScore.NEUTRAL,
        relevance_score: float = 0.5,
        freshness_seconds: int = 0,
        metadata: Optional[Dict] = None,
    ) -> IntelObject:
        """Create and dispatch an intel_object (§3.2).

        All outputs carry data_quality marking (§3.4).
        """
        intel = IntelObject(
            source=source,
            content=content,
            symbols=symbols,
            data_quality=data_quality,
            sentiment=sentiment,
            relevance_score=relevance_score,
            freshness_seconds=freshness_seconds,
            metadata=metadata or {},
        )

        with self._lock:
            self._intel_log.append(intel)
            self._stats["intel_produced"] += 1

        # Route to Strategist via bus
        if self.bus and relevance_score >= self.config.relevance_threshold:
            msg = AgentMessage(
                sender=AgentRole.SCOUT,
                receiver=AgentRole.STRATEGIST,
                message_type=MessageType.INTEL_OBJECT,
                priority=3,
                payload=intel.to_dict(),
            )
            self.bus.send(msg)

        return intel

    def produce_event_alert(
        self,
        event_type: str,
        severity: str,
        affected_symbols: List[str],
        *,
        event_time_ms: int = 0,
        lead_time_hours: float = 0.0,
        data_quality: DataQualityLevel = DataQualityLevel.INFERENCE,
        description: str = "",
        metadata: Optional[Dict] = None,
    ) -> EventAlert:
        """Create and dispatch an event_alert (§3.2).

        Major event alerts go to Guardian for risk tightening.
        """
        alert = EventAlert(
            event_type=event_type,
            severity=severity,
            affected_symbols=affected_symbols,
            event_time_ms=event_time_ms,
            lead_time_hours=lead_time_hours,
            data_quality=data_quality,
            description=description,
            metadata=metadata or {},
        )

        with self._lock:
            self._alert_log.append(alert)
            self._stats["alerts_produced"] += 1

        # Route to Guardian via bus
        if self.bus:
            msg = AgentMessage(
                sender=AgentRole.SCOUT,
                receiver=AgentRole.GUARDIAN,
                message_type=MessageType.EVENT_ALERT,
                priority=1 if severity in ("high", "critical") else 3,
                payload=alert.to_dict(),
            )
            self.bus.send(msg)

        return alert

    def record_scan(self) -> None:
        """Record that a news/market scan cycle completed."""
        with self._lock:
            self._stats["scans_completed"] += 1

    def get_recent_intel(self, limit: int = 20) -> List[IntelObject]:
        with self._lock:
            return list(self._intel_log[-limit:])

    def get_recent_alerts(self, limit: int = 10) -> List[EventAlert]:
        with self._lock:
            return list(self._alert_log[-limit:])

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "role": AgentRole.SCOUT.value,
                "state": self.state.value,
                **dict(self._stats),
            }


# ─────────────────────────────────────────────
# 5. Conflict Arbitration (EX-06 §9)
# ─────────────────────────────────────────────

# Arbitration result
@dataclass
class ArbitrationResult:
    winner: AgentRole
    decision: str  # "guardian_veto", "guardian_tighten", "strategist_autonomy", etc.
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "winner": self.winner.value,
            "decision": self.decision,
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


def arbitrate_conflict(
    scenario: str,
    strategist_action: Optional[Dict] = None,
    guardian_action: Optional[Dict] = None,
) -> ArbitrationResult:
    """EX-06 §9 TABLE 4 — conflict resolution.

    Core principle: Guardian's risk conclusion ALWAYS overrides
    Strategist's trade intent. Safety > Profit.

    Supported scenarios:
    - "open_vs_tighten": Strategist wants open, Guardian says tighten
    - "scout_bearish_strategist_bullish": Scout bearish, Strategist bullish
    - "analyst_vs_strategist": Analyst suggests, Strategist disagrees
    - "executor_anomaly": Executor reports anomaly, Guardian wants circuit-breaker
    - "resource_contention": Multiple agents request AI compute
    """
    if scenario == "open_vs_tighten":
        return ArbitrationResult(
            winner=AgentRole.GUARDIAN,
            decision="guardian_veto",
            reason="Guardian wins — risk control priority over profit (EX-06 §9)",
        )

    if scenario == "scout_bearish_strategist_bullish":
        return ArbitrationResult(
            winner=AgentRole.GUARDIAN,
            decision="guardian_tighten",
            reason="Guardian intervenes — at minimum tighten risk params (EX-06 §9)",
        )

    if scenario == "analyst_vs_strategist":
        return ArbitrationResult(
            winner=AgentRole.STRATEGIST,
            decision="strategist_autonomy",
            reason="Analyst suggestion recorded but not forced — Strategist has strategy autonomy (EX-06 §9)",
        )

    if scenario == "executor_anomaly":
        return ArbitrationResult(
            winner=AgentRole.GUARDIAN,
            decision="guardian_circuit_breaker",
            reason="Guardian wins — can trigger CIRCUIT_BREAKER on execution anomaly (EX-06 §9)",
        )

    if scenario == "resource_contention":
        # Priority: Guardian > Scout(urgent) > Strategist > Analyst > Scout(routine)
        return ArbitrationResult(
            winner=AgentRole.CONDUCTOR,
            decision="conductor_priority_allocation",
            reason="Conductor allocates by priority: Guardian > Scout(urgent) > Strategist > Analyst > Scout(routine) (EX-06 §9)",
        )

    return ArbitrationResult(
        winner=AgentRole.CONDUCTOR,
        decision="conductor_default",
        reason=f"Unknown scenario '{scenario}' — Conductor makes default call",
    )


# ─────────────────────────────────────────────
# 6. Agent Registry
# ─────────────────────────────────────────────

@dataclass
class AgentInfo:
    """Metadata about a registered agent."""
    role: AgentRole
    state: AgentState = AgentState.INITIALIZING
    resource_mode: str = "local"  # "local" / "cloud" / "hybrid"
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


# ─────────────────────────────────────────────
# 7. Conductor (EX-06 §2)
# ─────────────────────────────────────────────

class Conductor:
    """EX-06 §2 — OpenClaw as central orchestrator.

    Responsibilities (§2.3):
    - Task distribution: receive market events, decide which agent intervenes
    - Conflict arbitration: when Strategist vs Guardian, rule by priority
    - Resource allocation: manage AI compute budget across agents
    - Agent lifecycle: start, health-check, degrade, restart

    Conductor CANNOT (§2.4):
    - Directly place orders (must go via Executor → unified entry)
    - Override Guardian's risk veto
    - Modify P0/P1 hard limits
    - Bypass H0 gate
    """

    def __init__(
        self,
        *,
        message_bus: Optional[MessageBus] = None,
        audit_callback: Optional[Callable] = None,
    ):
        self.bus = message_bus or MessageBus(audit_callback=audit_callback)
        self._lock = threading.Lock()
        self._agents: Dict[AgentRole, AgentInfo] = {}
        self._audit_callback = audit_callback
        self._directives_issued: int = 0
        self._arbitrations: int = 0
        self._resource_budget_usd: float = 2.0  # DOC-04 §C conservative daily ceiling

    # ── Agent Lifecycle (§2.3) ──

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
            info.state = state
            info.last_heartbeat_ms = int(time.time() * 1000)
        return True

    def heartbeat(self, role: AgentRole) -> bool:
        """Record a heartbeat from an agent."""
        with self._lock:
            info = self._agents.get(role)
            if not info:
                return False
            info.last_heartbeat_ms = int(time.time() * 1000)
        return True

    def get_agent_info(self, role: AgentRole) -> Optional[AgentInfo]:
        with self._lock:
            return self._agents.get(role)

    def get_all_agents(self) -> Dict[AgentRole, AgentInfo]:
        with self._lock:
            return dict(self._agents)

    # ── Task Distribution (§2.3) ──

    def dispatch_market_event(
        self, event_data: Dict[str, Any]
    ) -> List[AgentRole]:
        """Decide which agents should handle a market event.

        Returns list of agents that were notified.
        """
        notified: List[AgentRole] = []
        event_type = event_data.get("type", "")

        # Scout always gets market events for scanning
        if self._is_agent_available(AgentRole.SCOUT):
            notified.append(AgentRole.SCOUT)

        # Price events → Strategist + Guardian
        if event_type in ("price_update", "funding_rate", "oi_change", "liquidation"):
            if self._is_agent_available(AgentRole.STRATEGIST):
                notified.append(AgentRole.STRATEGIST)
            if self._is_agent_available(AgentRole.GUARDIAN):
                notified.append(AgentRole.GUARDIAN)

        # Execution events → Executor + Analyst
        if event_type in ("fill", "partial_fill", "reject", "cancel"):
            if self._is_agent_available(AgentRole.EXECUTOR):
                notified.append(AgentRole.EXECUTOR)
            if self._is_agent_available(AgentRole.ANALYST):
                notified.append(AgentRole.ANALYST)

        # Risk events → Guardian (priority)
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

    # ── Conflict Arbitration (§2.3 / §9) ──

    def resolve_conflict(
        self,
        scenario: str,
        strategist_action: Optional[Dict] = None,
        guardian_action: Optional[Dict] = None,
    ) -> ArbitrationResult:
        """Arbitrate a conflict between agents (EX-06 §9)."""
        result = arbitrate_conflict(scenario, strategist_action, guardian_action)
        with self._lock:
            self._arbitrations += 1

        if self._audit_callback:
            try:
                self._audit_callback("conflict_arbitration", {
                    "scenario": scenario,
                    "result": result.to_dict(),
                })
            except Exception:
                pass

        return result

    # ── Resource Allocation (§2.3) ──

    def allocate_resource(
        self, requests: List[Tuple[AgentRole, float]]
    ) -> Dict[AgentRole, float]:
        """Allocate AI compute budget across agents.

        EX-06 §9 TABLE 4: Guardian > Scout(urgent) > Strategist > Analyst > Scout(routine)
        Returns {role: allocated_usd}.
        """
        # Sort by priority
        priority_map = {
            AgentRole.GUARDIAN: ResourcePriority.GUARDIAN,
            AgentRole.SCOUT: ResourcePriority.SCOUT_ROUTINE,  # default
            AgentRole.STRATEGIST: ResourcePriority.STRATEGIST,
            AgentRole.ANALYST: ResourcePriority.ANALYST,
            AgentRole.EXECUTOR: ResourcePriority.STRATEGIST,  # same as strategist
        }
        sorted_requests = sorted(
            requests, key=lambda r: priority_map.get(r[0], 9)
        )

        allocated: Dict[AgentRole, float] = {}
        remaining = self._resource_budget_usd

        for role, requested in sorted_requests:
            grant = min(requested, remaining)
            allocated[role] = grant
            remaining -= grant
            if remaining <= 0:
                break

        # Any agents not allocated get 0
        for role, _ in requests:
            if role not in allocated:
                allocated[role] = 0.0

        return allocated

    def set_resource_budget(self, usd: float) -> None:
        self._resource_budget_usd = usd

    # ── System Directives (§8.2) ──

    def broadcast_directive(
        self,
        directive_type: str,
        payload: Dict[str, Any],
        *,
        targets: Optional[List[AgentRole]] = None,
    ) -> int:
        """Broadcast a system_directive to agents (EX-06 §8.2).

        Returns number of messages sent.
        """
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

    # ── Trade Intent Pipeline ──

    def process_trade_intent(
        self, intent: TradeIntent, guardian_review: Callable
    ) -> Tuple[bool, RiskVerdict]:
        """Full trade intent pipeline: Strategist → Guardian review → Executor.

        EX-06 §4.3: Strategist cannot bypass Guardian review.
        EX-06 §5.2: Guardian's risk verdict takes priority.
        """
        # Step 1: Guardian reviews
        verdict = guardian_review(intent)

        # Step 2: Dispatch based on verdict
        if verdict.result == RiskVerdictResult.APPROVED:
            # Send approved_intent to Executor
            if self.bus:
                msg = AgentMessage(
                    sender=AgentRole.STRATEGIST,
                    receiver=AgentRole.EXECUTOR,
                    message_type=MessageType.APPROVED_INTENT,
                    priority=2,
                    payload=intent.to_dict(),
                )
                self.bus.send(msg)
            return (True, verdict)

        elif verdict.result == RiskVerdictResult.MODIFIED:
            # Apply modifications, then send
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
                msg = AgentMessage(
                    sender=AgentRole.STRATEGIST,
                    receiver=AgentRole.EXECUTOR,
                    message_type=MessageType.APPROVED_INTENT,
                    priority=2,
                    payload=modified_intent.to_dict(),
                )
                self.bus.send(msg)
            return (True, verdict)

        else:
            # REJECTED — do not forward
            return (False, verdict)

    # ── Status ──

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
                    1
                    for i in self._agents.values()
                    if i.state == AgentState.RUNNING
                ),
                "total_messages": self.bus.total_messages,
                "directives_issued": self._directives_issued,
                "arbitrations": self._arbitrations,
                "resource_budget_usd": self._resource_budget_usd,
            }
